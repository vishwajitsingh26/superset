# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.
"""REST API for the Design-to-Dashboard chat."""

from __future__ import annotations

import logging
import mimetypes
import os
import pathlib
import queue
import re
import tempfile
from collections.abc import Iterator

from flask import current_app, g, request, Response
from flask_appbuilder.api import BaseApi, expose, protect, safe

from superset.design_to_dashboard import crop, runner, session_store
from superset.extensions import event_logger
from superset.superset_typing import FlaskResponse
from superset.utils import json

logger = logging.getLogger(__name__)

ALLOWED_IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp", "application/pdf"}
# A crop is named after its region, which is minted from a number and a slug.
# Matched rather than trusted: the name arrives in a URL, and a path is the
# one thing it must not be able to become.
CROP_NAME = re.compile(r"[A-Za-z0-9_-]{1,120}\.png")
MAX_UPLOAD_BYTES = 12 * 1024 * 1024
SSE_KEEPALIVE_SECONDS = 15


class DesignToDashboardRestApi(BaseApi):
    """Chat sessions that turn a design into a dashboard."""

    resource_name = "design_to_dashboard"
    openapi_spec_tag = "Design to Dashboard"
    class_permission_name = "DesignToDashboard"
    allow_browser_login = True
    # FAB grants each exposed method its own permission, named after the
    # method, the first time an operator runs `superset init` after it is
    # added -- and only that command grants a new permission to a role, not
    # an ordinary restart. `crop_image` was added after this deployment's
    # last `superset init`, so its own `can_crop_image` permission existed on
    # nobody's role and every request 403'd, including the session's owner.
    # Reusing `get_session`'s permission -- another owner-gated read on this
    # same resource -- means a method added here needs no separate grant, on
    # this deployment or the next one that forgets to re-run `superset init`.
    method_permission_name = {"crop_image": "get_session", "get_asset": "get_session"}

    @expose("/session/", methods=("POST",))
    @protect()
    @safe
    @event_logger.log_this
    def create_session(self) -> FlaskResponse:
        """Start a new conversation."""
        session = session_store.create(user_id=g.user.id)
        return self.response(201, id=session.id, status=session.status)

    @expose("/session/<session_id>/asset/", methods=("POST",))
    @protect()
    @safe
    @event_logger.log_this
    def upload_asset(self, session_id: str) -> FlaskResponse:
        """Attach a design image to the session."""
        session = session_store.get(session_id, user_id=g.user.id)
        if session is None:
            return self.response_404()

        file = request.files.get("file")
        if file is None:
            return self.response_400(message="no file uploaded")
        if file.mimetype not in ALLOWED_IMAGE_TYPES:
            return self.response_400(
                message=f"unsupported type {file.mimetype!r}; "
                f"allowed: {sorted(ALLOWED_IMAGE_TYPES)}"
            )

        blob = file.read()
        if len(blob) > MAX_UPLOAD_BYTES:
            return self.response_400(
                message=f"file is {len(blob)} bytes, over the "
                f"{MAX_UPLOAD_BYTES} byte limit"
            )

        # Stored outside the web root, in a per-session directory.
        directory = pathlib.Path(tempfile.gettempdir()) / "d2d" / session.id
        directory.mkdir(parents=True, exist_ok=True)
        suffix = pathlib.Path(file.filename or "design.png").suffix or ".png"
        path = directory / f"design_{len(session.image_paths)}{suffix}"
        path.write_bytes(blob)
        os.chmod(path, 0o600)
        session.image_paths.append(str(path))

        return self.response(
            201, path=str(path), count=len(session.image_paths), bytes=len(blob)
        )

    @expose("/session/<session_id>/run/", methods=("POST",))
    @protect()
    @safe
    @event_logger.log_this
    def run(self, session_id: str) -> FlaskResponse:
        """Start the pipeline for this session."""
        session = session_store.get(session_id, user_id=g.user.id)
        if session is None:
            return self.response_404()
        if session.status == "running":
            return self.response_400(message="this session is already running")
        if not session.image_paths:
            return self.response_400(message="upload a design image first")

        payload = request.json or {}
        session.requirement = (payload.get("requirement") or "").strip() or (
            "Rebuild this dashboard in Superset."
        )
        runner.start(current_app._get_current_object(), session)  # noqa: SLF001
        return self.response(202, id=session.id, status="running")

    @expose("/session/<session_id>/reply/", methods=("POST",))
    @protect()
    @safe
    @event_logger.log_this
    def reply(self, session_id: str) -> FlaskResponse:
        """Answer whatever the run is waiting on, and let it continue."""
        session = session_store.get(session_id, user_id=g.user.id)
        if session is None:
            return self.response_404()
        if session.pending is None:
            return self.response_400(message="this run is not waiting for input")

        payload = request.json or {}
        kind = session.pending.get("kind")
        # A plan and a set of sample tables must both be explicitly approved;
        # anything else is a rejection and stops the run rather than proceeding
        # on an assumption. Rejecting the reply outright, rather than reading a
        # missing field as "no", keeps a malformed client from quietly
        # cancelling a run the user meant to continue.
        if kind in {"plan", "datasets"} and "approved" not in payload:
            return self.response_400(
                message=f"{kind} replies need an 'approved' boolean"
            )

        delivered = session.answer(payload)
        if not delivered:
            return self.response_400(message="nothing was waiting for that answer")
        return self.response(200, id=session.id, status=session.status)

    @expose("/session/<session_id>/events/", methods=("GET",))
    @protect()
    @safe
    def events(self, session_id: str) -> FlaskResponse:
        """Server-sent events for this session's progress."""
        session = session_store.get(session_id, user_id=g.user.id)
        if session is None:
            return self.response_404()

        listener = session.attach()

        def stream() -> Iterator[str]:
            try:
                while True:
                    try:
                        event = listener.get(timeout=SSE_KEEPALIVE_SECONDS)
                    except queue.Empty:
                        # Keep proxies from closing an idle connection: stages
                        # can run for minutes without emitting anything.
                        yield ": keepalive\n\n"
                        continue
                    yield f"data: {json.dumps(event)}\n\n"
                    if event.get("type") in {
                        "done",
                        "error",
                        "needs_input",
                        "needs_approval",
                    }:
                        break
            finally:
                session.detach(listener)

        return Response(
            stream(),
            mimetype="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "Connection": "keep-alive",
            },
        )

    @expose("/session/<session_id>/crop/<name>/", methods=("GET",))
    @protect()
    @safe
    def crop_image(self, session_id: str, name: str) -> FlaskResponse:
        """One region's crop, for the review shown before plugins are built.

        Served rather than embedded: the event log is replayed in full to
        every reconnecting client, so a dozen base64 images in it would cross
        the wire again on each refresh.
        """
        session = session_store.get(session_id, user_id=g.user.id)
        if session is None or not CROP_NAME.fullmatch(name):
            return self.response_404()
        path = crop.session_crops_dir(session_id) / name
        if not path.is_file():
            return self.response_404()
        return Response(
            path.read_bytes(),
            mimetype="image/png",
            headers={"Cache-Control": "private, max-age=3600"},
        )

    @expose("/session/<session_id>/asset/<int:index>/", methods=("GET",))
    @protect()
    @safe
    def get_asset(self, session_id: str, index: int) -> FlaskResponse:
        """The design image at this index, exactly as uploaded.

        Both panes on the frontend draw a design thumbnail from this, and
        neither has anything else to draw one from after a reload: the local
        blob URL a chosen `File` was previewed from dies with the tab, and
        the browser holds no memory of what was uploaded, only this session
        does. Served rather than replayed through the event log, for the same
        reason as `crop_image` -- an upload can be several megabytes, and
        every reconnecting client would otherwise cross that wire again.
        """
        session = session_store.get(session_id, user_id=g.user.id)
        if session is None or not 0 <= index < len(session.image_paths):
            return self.response_404()
        path = pathlib.Path(session.image_paths[index])
        if not path.is_file():
            return self.response_404()
        mimetype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        return Response(
            path.read_bytes(),
            mimetype=mimetype,
            headers={"Cache-Control": "private, max-age=3600"},
        )

    @expose("/session/<session_id>/", methods=("GET",))
    @protect()
    @safe
    def get_session(self, session_id: str) -> FlaskResponse:
        """Current state, for reconnecting clients."""
        session = session_store.get(session_id, user_id=g.user.id)
        if session is None:
            return self.response_404()

        try:
            since = max(0, int(request.args.get("since", 0)))
        except (TypeError, ValueError):
            since = 0
        snapshot = session.snapshot(since)

        return self.response(
            200,
            id=session.id,
            status=session.status,
            requirement=session.requirement,
            images=len(session.image_paths),
            result=session.result,
            error=session.error,
            pending=session.pending,
            **snapshot,
        )
