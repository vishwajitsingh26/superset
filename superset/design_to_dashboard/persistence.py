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
"""Where a run lives when the process that started it does not.

Sessions were held in a dict in the worker's memory, which meant a run ended
when the server restarted and could not be reopened in another tab. A design
that takes forty minutes to rebuild is not something to lose to a reload.

Two tables, in a schema of their own beside the one stage B writes its fact
tables into:

``runs`` is the whole conversation as one row -- what was asked, what was
answered, which stage it reached, every event the browser needs to redraw the
page. ``stage_outputs`` is one row per stage, holding exactly what that stage
returned. The split is deliberate: the run row is rewritten constantly and
stays small, while a stage output is written once and is the expensive thing a
resumed run wants back.

Writes happen at stage boundaries rather than per event. A run publishes
thousands of events and a round trip each would show up in the wall clock; the
unit worth not losing is a stage, which is also the unit a resume starts from.

Storage is addressed by URL so it can move. It defaults to the database stage
B already writes to, and `url` overrides that outright -- which is the handle
for pointing conversation history somewhere else later without touching this
file.
"""

from __future__ import annotations

import contextlib
import logging
import re
from collections.abc import Iterator
from typing import Any

from superset.utils import json

logger = logging.getLogger(__name__)

# Same rule the applier uses for the schema it materialises fact tables into:
# the name is interpolated into DDL, so it is validated rather than escaped.
# The schema name is interpolated into SQL, so it must be a plain identifier;
# that check is why the statements below carry `noqa: S608`.
_IDENTIFIER = re.compile(r"^[a-z_][a-z0-9_]{0,60}$")

DEFAULT_SCHEMA = "d2d_runs"

# Long enough to hold a design's whole reading. Postgres does not need a
# length, but naming the type keeps the DDL readable on databases that do.
RUNS_DDL = """
CREATE TABLE IF NOT EXISTS {schema}.runs (
    session_id   TEXT PRIMARY KEY,
    user_id      INTEGER,
    status       TEXT,
    requirement  TEXT,
    created_at   DOUBLE PRECISION,
    updated_at   DOUBLE PRECISION,
    image_paths  TEXT,
    events       TEXT,
    artifacts    TEXT,
    pending      TEXT,
    result       TEXT,
    error        TEXT
)
"""

STAGE_DDL = """
CREATE TABLE IF NOT EXISTS {schema}.stage_outputs (
    session_id   TEXT,
    stage        TEXT,
    updated_at   DOUBLE PRECISION,
    payload      TEXT,
    PRIMARY KEY (session_id, stage)
)
"""


def _config() -> dict[str, Any]:
    from flask import current_app

    return current_app.config.get("DESIGN_TO_DASHBOARD_PERSISTENCE") or {}


def enabled() -> bool:
    return bool(_config().get("enabled"))


def schema() -> str:
    name = str(_config().get("schema") or DEFAULT_SCHEMA)
    if not _IDENTIFIER.fullmatch(name):
        raise ValueError(f"invalid persistence schema {name!r}")
    return name


@contextlib.contextmanager
def _engine() -> Iterator[Any]:
    """The engine runs are stored on, or None when storage is off.

    A context manager because that is what Superset's own `get_sqla_engine` is:
    it owns the connection's lifetime and expects to close it. Resolved per use
    rather than cached, since `database_id` points at a `Database` whose URI an
    administrator can change under us.
    """
    if not enabled():
        yield None
        return
    config = _config()
    if url := config.get("url"):
        from sqlalchemy import create_engine

        engine = create_engine(url, pool_pre_ping=True)
        try:
            yield engine
        finally:
            engine.dispose()
        return

    database_id = config.get("database_id")
    if not database_id:
        logger.warning(
            "design-to-dashboard persistence is on but has neither `url` nor "
            "`database_id`; runs will not be saved"
        )
        yield None
        return
    from superset import db as superset_db
    from superset.models.core import Database

    database = superset_db.session.query(Database).get(database_id)
    if database is None:
        logger.warning("persistence database %s not found", database_id)
        yield None
        return
    with database.get_sqla_engine() as engine:
        yield engine


def ensure_ready() -> bool:
    """Create the schema and tables if they are not there yet.

    Called before the first write of a run rather than at import: the database
    may not be reachable when the app boots, and a feature that is off should
    touch nothing.
    """
    from sqlalchemy import text

    name = schema()
    try:
        with _engine() as engine:
            if engine is None:
                return False
            with engine.begin() as connection:
                # SQLite has no CREATE SCHEMA -- it calls its single schema
                # `main` and rejects the statement outright. Everything after
                # this is portable, so the create is the only thing skipped.
                if engine.dialect.name != "sqlite":
                    connection.execute(text(f"CREATE SCHEMA IF NOT EXISTS {name}"))
                connection.execute(text(RUNS_DDL.format(schema=name)))
                connection.execute(text(STAGE_DDL.format(schema=name)))
        return True
    except Exception:  # noqa: BLE001 - storage is an aid, never the run
        logger.exception("could not prepare the design-to-dashboard run store")
        return False


def _dump(value: Any) -> str | None:
    if value is None:
        return None
    try:
        return json.dumps(value, default=str)
    except (TypeError, ValueError):
        logger.warning("a run field could not be serialised; storing nothing")
        return None


def save_run(session: Any) -> None:
    """Write the whole conversation as one row.

    Never raises. Storage failing is a lost resume, which is a nuisance; a run
    dying at stage F because a write timed out is forty minutes of work, so the
    two are not traded against each other.
    """
    import time

    from sqlalchemy import text

    name = schema()
    row = {
        "session_id": session.id,
        "user_id": getattr(session, "user_id", None),
        "status": getattr(session, "status", None),
        "requirement": getattr(session, "requirement", "") or "",
        "created_at": getattr(session, "created_at", None),
        "updated_at": time.time(),
        "image_paths": _dump(list(getattr(session, "image_paths", []) or [])),
        "events": _dump(list(getattr(session, "events", []) or [])),
        "artifacts": _dump(dict(getattr(session, "artifacts", {}) or {})),
        "pending": _dump(getattr(session, "pending", None)),
        "result": _dump(getattr(session, "result", None)),
        "error": getattr(session, "error", None),
    }
    columns = ", ".join(row)
    binds = ", ".join(f":{key}" for key in row)
    updates = ", ".join(f"{key} = EXCLUDED.{key}" for key in row if key != "session_id")
    statement = text(
        f"INSERT INTO {name}.runs ({columns}) VALUES ({binds}) "  # noqa: S608
        f"ON CONFLICT (session_id) DO UPDATE SET {updates}"
    )
    try:
        with _engine() as engine:
            if engine is None:
                return
            with engine.begin() as connection:
                connection.execute(statement, row)
    except Exception:  # noqa: BLE001 - never take the run down with the store
        logger.exception("could not save run %s", session.id)


def save_stage(session_id: str, stage: str, payload: Any) -> None:
    """Write one stage's output, which is the expensive thing to lose."""
    import time

    from sqlalchemy import text

    name = schema()
    row = {
        "session_id": session_id,
        "stage": stage,
        "updated_at": time.time(),
        "payload": _dump(payload),
    }
    statement = text(
        f"INSERT INTO {name}.stage_outputs (session_id, stage, updated_at, payload) "  # noqa: S608
        "VALUES (:session_id, :stage, :updated_at, :payload) "
        "ON CONFLICT (session_id, stage) DO UPDATE SET "
        "updated_at = EXCLUDED.updated_at, payload = EXCLUDED.payload"
    )
    try:
        with _engine() as engine:
            if engine is None:
                return
            with engine.begin() as connection:
                connection.execute(statement, row)
    except Exception:  # noqa: BLE001
        logger.exception("could not save stage %s of run %s", stage, session_id)


def _loads(value: Any, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return fallback


def load_run(session_id: str) -> dict[str, Any] | None:
    """Everything needed to redraw a run the process never saw."""
    from sqlalchemy import text

    name = schema()
    run_sql = text(
        "SELECT session_id, user_id, status, requirement, created_at, "  # noqa: S608
        "image_paths, events, artifacts, pending, result, error "
        f"FROM {name}.runs WHERE session_id = :sid"
    )
    stage_sql = text(
        f"SELECT stage, payload FROM {name}.stage_outputs WHERE session_id = :sid"  # noqa: S608
    )
    try:
        with _engine() as engine:
            if engine is None:
                return None
            with engine.connect() as connection:
                found = (
                    connection.execute(run_sql, {"sid": session_id}).mappings().first()
                )
                if found is None:
                    return None
                stages = (
                    connection.execute(stage_sql, {"sid": session_id}).mappings().all()
                )
                run = dict(found)
    except Exception:  # noqa: BLE001 - a lost resume, never a lost run
        logger.exception("could not load run %s", session_id)
        return None

    return {
        "id": run["session_id"],
        "user_id": run["user_id"],
        "status": run["status"],
        "requirement": run["requirement"] or "",
        "created_at": run["created_at"],
        "image_paths": _loads(run["image_paths"], []),
        "events": _loads(run["events"], []),
        "artifacts": _loads(run["artifacts"], {}),
        "pending": _loads(run["pending"], None),
        "result": _loads(run["result"], None),
        "error": run["error"],
        "stages": {row["stage"]: _loads(row["payload"], None) for row in stages},
    }


def list_runs(user_id: int, limit: int = 25) -> list[dict[str, Any]]:
    """Recent runs for one user, newest first, for reopening one."""
    from sqlalchemy import text

    name = schema()
    statement = text(
        "SELECT session_id, status, requirement, created_at, updated_at "  # noqa: S608
        f"FROM {name}.runs WHERE user_id = :uid "
        "ORDER BY updated_at DESC LIMIT :limit"
    )
    try:
        with _engine() as engine:
            if engine is None:
                return []
            with engine.connect() as connection:
                rows = (
                    connection.execute(statement, {"uid": user_id, "limit": limit})
                    .mappings()
                    .all()
                )
                return [dict(row) for row in rows]
    except Exception:  # noqa: BLE001
        logger.exception("could not list runs for user %s", user_id)
        return []
