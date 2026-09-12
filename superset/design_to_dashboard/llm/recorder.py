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
"""Writes each stage's prompt, reasoning and answer to disk.

WHY THIS EXISTS
---------------
A run's durable record is the event log, which says that stage C re-planned
three times but not what it planned or why. The prompt, the reasoning and the
raw answer exist only for the length of the call: the session keeps the last
8000 characters of reasoning and drops the rest, and the answer survives only
as the parsed fields the stage chose to keep. Tuning a prompt means reading the
answer it produced beside the prompt that produced it, so both are written out.

ONE DIRECTORY PER CALL, NOT PER STAGE
-------------------------------------
Stages repeat. A validation failure re-runs C, the tool loop drives B over
several turns, and F fans out across regions. Numbering every call keeps the
attempt that failed next to the one that followed it instead of overwriting it.

WHY IT WRAPS THE PROVIDER
-------------------------
Every stage reaches the model through :class:`LLMProvider.complete`, so one
wrapper there records all of them, including the fan-out in F and the tool
loop's intermediate turns -- none of which the runner sees individually.

NOT FOR PRODUCTION
------------------
Prompts and answers carry whatever the design and the database hold, written
unencrypted under the repository, and nothing prunes them. It stays off unless
``DESIGN_TO_DASHBOARD_LLM["record_calls"]`` is set.
"""

from __future__ import annotations

import logging
import os
import pathlib
import shutil
import threading
import time
from datetime import datetime, timezone
from typing import Any

from superset.utils import json

from .base import LLMProvider, LLMResponse

logger = logging.getLogger(__name__)

RECORD_ROOT = pathlib.Path("design-to-dashboard") / "traces"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class RecordingProvider:
    """Delegates to a real provider, writing every call out as files.

    Recording never changes the outcome of a call: a failure to write is logged
    and swallowed, and a failing call is recorded with its error and then
    re-raised untouched.
    """

    def __init__(
        self,
        inner: LLMProvider,
        stage: str,
        session_id: str,
        root: pathlib.Path,
    ) -> None:
        self.inner = inner
        self.name = inner.name
        self.stage = stage
        self.session_dir = root / RECORD_ROOT / session_id
        self._calls = 0
        self._lock = threading.Lock()

    def __getattr__(self, item: str) -> Any:
        """Expose the wrapped provider's own attributes (`model`, `effort`).

        Only reached for names this class does not define, so the wrapper is a
        drop-in for code that inspects the provider it was handed.
        """
        return getattr(self.inner, item)

    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        image_paths: list[str] | None = None,
        timeout: int | None = None,
        on_thinking: Any = None,
    ) -> LLMResponse:
        with self._lock:
            self._calls += 1
            index = self._calls
        # F resolves one provider and fans out, so two calls can be in flight
        # together; the directory name is taken under the lock above and the
        # rest proceeds in parallel.
        call_dir = self.session_dir / f"{self.stage}_{index:02d}"

        # A sink is passed even when the stage asked for no reasoning: the
        # stages that skip it are the ones whose reasoning is least visible
        # anywhere else.
        thinking = _ThinkingCapture(on_thinking)
        started = time.monotonic()
        response: LLMResponse | None = None
        error: Exception | None = None
        try:
            response = self.inner.complete(
                system_prompt,
                user_prompt,
                image_paths,
                timeout,
                thinking.sink,
            )
            return response
        except Exception as ex:
            error = ex
            raise
        finally:
            try:
                self._write(
                    call_dir=call_dir,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    image_paths=image_paths or [],
                    thinking=thinking.text,
                    response=response,
                    error=error,
                    duration=time.monotonic() - started,
                )
            except Exception:  # noqa: BLE001 - the call's outcome takes priority
                logger.exception("could not record stage %s call %d", self.stage, index)

    def _write(  # noqa: PLR0913
        self,
        call_dir: pathlib.Path,
        system_prompt: str,
        user_prompt: str,
        image_paths: list[str],
        thinking: str,
        response: LLMResponse | None,
        error: Exception | None,
        duration: float,
    ) -> None:
        call_dir.mkdir(parents=True, exist_ok=True)
        text = response.text if response else ""

        _write_text(
            call_dir / "prompt.md",
            f"# {self.stage} — system prompt\n\n{system_prompt}\n\n"
            f"# {self.stage} — user prompt\n\n{user_prompt}\n",
        )
        _write_text(
            call_dir / "thinking.md",
            thinking
            or "_No reasoning was streamed for this call._\n\n"
            "The provider forwards what the model emits; some calls produce "
            "none. Raising `effort` is what changes that.\n",
        )
        if text:
            _write_text(call_dir / "output.txt", text)
            parsed = _as_json(text)
            if parsed is not None:
                _write_text(call_dir / "output.json", json.dumps(parsed, indent=2))

        images = _copy_images(call_dir / "images", image_paths)

        meta = {
            "stage": self.stage,
            "provider": self.name,
            "model": getattr(self.inner, "model", None),
            "effort": getattr(self.inner, "effort", None),
            "recorded_at": _now(),
            "duration_s": round(duration, 1),
            "prompt_chars": {"system": len(system_prompt), "user": len(user_prompt)},
            "thinking_chars": len(thinking),
            "output_chars": len(text),
            "output_is_json": bool(text) and _as_json(text) is not None,
            "images": images,
            "usage": response.usage if response else {},
            "cost_usd": response.cost_usd if response else None,
            "provider_session_id": response.session_id if response else None,
            "error": f"{type(error).__name__}: {error}" if error else None,
        }
        _write_text(call_dir / "meta.json", json.dumps(meta, indent=2, default=str))
        _append_index(self.session_dir / "calls.jsonl", call_dir.name, meta)


class _ThinkingCapture:
    """Keeps the reasoning a call produced, and passes updates through.

    Providers send the reasoning accumulated so far rather than deltas, which
    is what lets the session replace its buffer instead of appending, so the
    longest update seen is the whole trace. Unlike the session's copy this one
    is not truncated.
    """

    def __init__(self, downstream: Any = None) -> None:
        self.text = ""
        self._downstream = downstream

    def sink(self, update: dict[str, Any]) -> None:
        candidate = (update or {}).get("text") or ""
        if len(candidate) > len(self.text):
            self.text = candidate
        if self._downstream is not None:
            self._downstream(update)


def _as_json(text: str) -> Any:
    """The reply as a JSON document, or None if it does not hold one."""
    from superset.design_to_dashboard.pipeline.tool_loop import extract_json

    try:
        return extract_json(text)
    except Exception:  # noqa: BLE001 - prose replies are recorded as text
        return None


def _write_text(path: pathlib.Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")


def _copy_images(directory: pathlib.Path, image_paths: list[str]) -> list[str]:
    """Put the images a call was given beside its prompt and answer.

    Hard-linked where the filesystem allows it: a design is megabytes and every
    image stage is handed the same one, so copying would multiply it by the
    number of calls in a run.
    """
    if not image_paths:
        return []
    directory.mkdir(parents=True, exist_ok=True)
    saved = []
    for position, source in enumerate(image_paths):
        name = f"{position}_{pathlib.Path(source).name}"
        destination = directory / name
        try:
            if not destination.exists():
                try:
                    os.link(source, destination)
                except OSError:
                    shutil.copy2(source, destination)
            saved.append(name)
        except OSError as ex:
            logger.warning("could not record image %s: %s", source, ex)
    return saved


def _append_index(path: pathlib.Path, call: str, meta: dict[str, Any]) -> None:
    """One line per call, so a run can be scanned without opening every file."""
    entry = {
        "call": call,
        "stage": meta["stage"],
        "at": meta["recorded_at"],
        "duration_s": meta["duration_s"],
        "thinking_chars": meta["thinking_chars"],
        "output_chars": meta["output_chars"],
        "credits": (meta.get("usage") or {}).get("credits"),
        "error": meta["error"],
    }
    with path.open("a", encoding="utf-8") as sink:
        sink.write(json.dumps(entry, default=str) + "\n")
