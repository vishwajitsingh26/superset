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

Stages never import MCP tool functions directly. They go through a gateway so
the same stage code runs against a live Superset (`InProcessGateway`) or
against recorded fixtures (`FixtureGateway`) with no changes.
"""

from __future__ import annotations

import asyncio
import logging
import pathlib
from typing import Any, Protocol

from superset.utils import json

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

    def __init__(self, timeout: int = 60) -> None:
        self.timeout = timeout

    def call(self, tool: str, arguments: dict[str, Any]) -> Any:
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


class FixtureGateway:
    """Serves recorded tool responses from a directory of JSON files.

    Lets stages and prompts be developed and tested without a running Superset.
    Files are named `<tool>.json`; a file may hold either a single response or
    a mapping of argument-signature to response.
    """

    name = "fixture"

    def __init__(self, directory: str | pathlib.Path) -> None:
        self.directory = pathlib.Path(directory)
        if not self.directory.is_dir():
            raise MCPError(f"Fixture directory not found: {self.directory}")
        self.calls: list[dict[str, Any]] = []

    def call(self, tool: str, arguments: dict[str, Any]) -> Any:
        self.calls.append({"tool": tool, "arguments": arguments})
        path = self.directory / f"{tool}.json"
        if not path.exists():
            raise MCPError(f"No fixture for tool {tool!r} at {path}")

        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict) and "__by_argument__" in payload:
            # MCP tools take a single `request` model, so the key we switch on
            # is nested one level down. Accept both shapes.
            flat = arguments.get("request")
            flat = flat if isinstance(flat, dict) else arguments
            key = str(flat.get(payload.get("__key__", "identifier"), ""))
            responses = payload["__by_argument__"]
            if key not in responses:
                raise MCPError(
                    f"Fixture {path.name} has no entry for {key!r}. "
                    f"Available: {sorted(responses)}"
                )
            return responses[key]
        return payload
