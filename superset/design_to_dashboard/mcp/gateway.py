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
"""Access to Superset's MCP tools for the Design-to-Dashboard pipeline.

Stages never import MCP tool functions directly. They go through a gateway,
so what a stage calls and how that call reaches Superset stay separable.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Protocol, TYPE_CHECKING

from superset.utils import json
from superset.utils.decorators import transaction

if TYPE_CHECKING:
    from superset.design_to_dashboard.registry import Registry

logger = logging.getLogger(__name__)


class MCPError(Exception):
    """Raised when a tool call fails or is not permitted."""


class MCPGateway(Protocol):
    """Calls one MCP tool by name and returns its decoded result."""

    name: str

    def call(self, tool: str, arguments: dict[str, Any]) -> Any: ...


class InProcessGateway:
    """Calls Superset's MCP tools in-memory via a FastMCP client.

    Runs against the `mcp` app instance rather than a subprocess or socket.

    **Must be called from inside a Flask request context with `g.user` set.**
    `mcp_auth_hook` pushes a *fresh* app context whenever no request context is
    active, which discards any `g.user` set beforehand; with a request context
    it reuses the existing one, so tools execute as the requesting user and
    RBAC is enforced without the gateway doing anything itself. From a bare app
    context the tools raise "No authenticated user found" unless
    `MCP_DEV_USERNAME` is configured.

    Serving the pipeline from an API endpoint satisfies this naturally.
    """

    name = "in_process"

    def __init__(self, timeout: int = 60, registry: Registry | None = None) -> None:
        self.timeout = timeout
        # The run's own registry, so a capability lookup answers from the
        # chart types this run started with rather than a fresh scan.
        self.registry = registry

    def call(self, tool: str, arguments: dict[str, Any]) -> Any:
        if tool == "get_chart_capabilities":
            return chart_capabilities(self.registry, arguments)
        if tool in LOCAL_TOOLS:
            return LOCAL_TOOLS[tool](arguments)
        return asyncio.run(self._call_async(tool, arguments))

    async def _call_async(self, tool: str, arguments: dict[str, Any]) -> Any:
        # Imported lazily: pulls in the whole MCP service, which the fixture
        # gateway must not require.
        from fastmcp import Client

        from superset.mcp_service.app import mcp

        try:
            async with Client(mcp) as client:
                result = await client.call_tool(tool, arguments)
        except Exception as ex:  # noqa: BLE001 - surfaced to the model as an observation
            raise MCPError(f"{tool} failed: {ex}") from ex

        return self._decode(result)

    @staticmethod
    def _decode(result: Any) -> Any:
        """Unwrap a FastMCP tool result into plain JSON-serialisable Python.

        Order matters, and was established against a live instance:

        1. ``structured_content`` — already a plain dict. The right answer.
        2. ``content[0].text`` — the canonical MCP payload, as a JSON string.
        3. ``data`` — a class FastMCP synthesises per tool (``Root``). It is
           **not** a pydantic model and has no ``model_dump``, so it is read
           through ``vars()``. Serialising it directly would yield a Python
           repr rather than JSON, which the tool loop cannot use.
        """
        structured = getattr(result, "structured_content", None)
        if isinstance(structured, dict):
            return structured

        if content := getattr(result, "content", None):
            text = getattr(content[0], "text", None)
            if text is not None:
                try:
                    return json.loads(text)
                except ValueError:
                    return text

        if (data := getattr(result, "data", None)) is not None:
            if isinstance(data, (dict, list, str, int, float, bool)):
                return data
            if hasattr(data, "__dict__"):
                return vars(data)
            return data

        return result


def _create_fact_table(arguments: dict[str, Any]) -> dict[str, Any]:
    """Materialise one fact table and register it as a dataset.

    Not an MCP tool. Creating a table is DDL, and the MCP path runs SQL under
    the database's own `allow_dml` flag -- off by default, and turning it on
    would hand every SQL Lab user DML on that database to let one stage write
    one schema. This writes through the applier instead, which confines it to
    `DATASET_SCHEMA` and validates every identifier before it reaches DDL.

    The table is read back before returning. A stage that is told the table
    exists and is then asked to write SQL against it needs that to be true:
    the row count and the columns come from the warehouse, not from the spec
    that was just submitted.
    """
    from flask import g

    from superset.design_to_dashboard.applier import (
        ApplyError,
        create_dataset,
        DATASET_SCHEMA,
    )

    raw = arguments.get("request")
    spec: dict[str, Any] = dict(raw) if isinstance(raw, dict) else dict(arguments)
    spec.setdefault("kind", "fact")
    if spec["kind"] not in {"fact", "shared"}:
        raise MCPError(
            f"create_fact_table makes a physical table; kind {spec['kind']!r} "
            "is not one. Use create_virtual_dataset for a saved SELECT."
        )
    user = getattr(g, "user", None)
    if user is None:
        raise MCPError("create_fact_table needs a request context with g.user set")

    existing = _existing_dataset(spec)
    if existing is None:
        try:
            dataset_id = create_dataset(spec, user.id)
        except ApplyError as ex:
            raise MCPError(f"create_fact_table failed: {ex}") from ex
    else:
        dataset_id = _refresh(existing, spec)

    return {**_verify_table(spec, dataset_id), "schema": DATASET_SCHEMA}


def _existing_dataset(spec: dict[str, Any]) -> Any:
    """The dataset already registered for this table, if there is one.

    Superset enforces one dataset per (database, schema, table), so a second
    run of the same design cannot simply create it again -- and the failure
    used to arrive *after* the table had been rewritten, leaving a table with
    no dataset. Re-running a design is normal, so it is handled rather than
    refused.
    """
    from superset import db as superset_db
    from superset.connectors.sqla.models import SqlaTable
    from superset.design_to_dashboard.applier import DATASET_SCHEMA

    return (
        superset_db.session.query(SqlaTable)
        .filter_by(
            table_name=spec["name"],
            schema=DATASET_SCHEMA,
            database_id=spec["database_id"],
        )
        .first()
    )


@transaction()
def _refresh(dataset: Any, spec: dict[str, Any]) -> int:
    """Rewrite the table under an existing dataset and re-read its columns.

    The dataset row is kept rather than replaced: charts from an earlier run
    point at this id, and dropping it to get fresh metadata would break every
    one of them. `fetch_metadata` re-reads the columns from the table that has
    just been written, so a design whose shape changed between runs does not
    leave the dataset describing the old one.
    """
    from superset.design_to_dashboard.applier import materialise_fact_table

    materialise_fact_table(spec)
    dataset.fetch_metadata()
    logger.info("refreshed dataset %s (id %s)", spec["name"], dataset.id)
    return int(dataset.id)


def _verify_table(spec: dict[str, Any], dataset_id: int) -> dict[str, Any]:
    """Read the table back, so "created" means the warehouse agrees."""
    from sqlalchemy import text

    from superset import db as superset_db
    from superset.design_to_dashboard.applier import DATASET_SCHEMA
    from superset.models.core import Database

    name = spec["name"]
    database = superset_db.session.query(Database).get(spec["database_id"])
    if database is None:
        raise MCPError(f"database {spec['database_id']} not found")
    with database.get_sqla_engine() as engine, engine.connect() as connection:
        rows = connection.execute(
            text(f"SELECT COUNT(*) FROM {DATASET_SCHEMA}.{name}")  # noqa: S608
        ).scalar()
        columns = [
            row[0]
            for row in connection.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = :s AND table_name = :t "
                    "ORDER BY ordinal_position"
                ),
                {"s": DATASET_SCHEMA, "t": name},
            )
        ]
    return {
        "dataset_id": dataset_id,
        "table_name": name,
        "row_count": int(rows or 0),
        "columns": columns,
    }


def chart_capabilities(
    registry: Registry | None, arguments: dict[str, Any]
) -> dict[str, Any]:
    """One stock chart type's capability card, for stage C's tool loop."""
    from superset.design_to_dashboard.registry import RegistryError

    if registry is None:
        raise MCPError("get_chart_capabilities: this gateway has no registry")
    request = arguments.get("request")
    source = request if isinstance(request, dict) else arguments
    viz_type = str(source.get("viz_type") or "").strip()
    if not viz_type:
        raise MCPError("get_chart_capabilities: 'viz_type' is required")
    try:
        return {"viz_type": viz_type, "card": registry.capability_card(viz_type)}
    except RegistryError as ex:
        raise MCPError(f"get_chart_capabilities: {ex}") from ex


# Tools this pipeline serves itself, before anything reaches Superset's MCP
# surface. Keeping them here rather than registering them as MCP tools means
# they exist for the pipeline only, and not for every MCP client.
LOCAL_TOOLS = {"create_fact_table": _create_fact_table}
