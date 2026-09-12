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
"""Whether a refused tool call is visible to anyone reading the run.

`list_charts` was rejected on every call, in every run, for as long as the
pipeline had existed: the model asked to filter charts by `datasource_id` and a
hand-maintained whitelist said no. The only record was a `logger.info` line.
The trace -- the artifact a run is reviewed from -- showed the request and not
the outcome, so a tool that never once answered looked exactly like one that
always did, and stage C went on inventing plugins it had no way to know already
existed.
"""

from __future__ import annotations

from typing import Any

from superset.design_to_dashboard.llm.base import LLMResponse
from superset.design_to_dashboard.mcp.gateway import MCPError
from superset.design_to_dashboard.pipeline.tool_loop import run_tool_loop
from superset.design_to_dashboard.trace import render


class _Provider:
    """Asks for one tool call, then settles for whatever came back."""

    name = "stub"

    def __init__(self, *replies: str) -> None:
        self._replies = list(replies)

    def complete(self, *_args: Any, **_kwargs: Any) -> LLMResponse:
        return LLMResponse(text=self._replies.pop(0), cost_usd=0.0)


class _RefusingGateway:
    """The shape of the real failure: the call is rejected, not the tool."""

    def call(self, tool: str, arguments: dict[str, Any]) -> Any:
        raise MCPError(
            f"{tool} failed: 1 validation error for call[{tool}]\n"
            "request.filters.col\n  Input should be 'slice_name'"
        )


class _WorkingGateway:
    def call(self, tool: str, arguments: dict[str, Any]) -> Any:
        return {"charts": []}


ASK = (
    '{"tool_calls": [{"id": "t1", "tool": "list_charts", '
    '"arguments": {"filters": [{"col": "datasource_id"}]}}]}'
)
DONE = '{"final": {"ok": true}}'


def _run(gateway: Any) -> list[tuple[str, dict[str, Any], str | None]]:
    seen: list[tuple[str, dict[str, Any], str | None]] = []

    def on_progress(
        tool: str, arguments: dict[str, Any], error: str | None = None
    ) -> None:
        seen.append((tool, arguments, error))

    run_tool_loop(
        _Provider(ASK, DONE),
        gateway,
        "system",
        "user",
        max_tool_calls=4,
        on_progress=on_progress,
    )
    return seen


def test_a_refused_call_reports_its_error() -> None:
    (_tool, _arguments, error) = _run(_RefusingGateway())[0]
    assert error is not None
    assert "validation error" in error


def test_a_successful_call_reports_no_error() -> None:
    assert _run(_WorkingGateway())[0][2] is None


def test_progress_still_names_the_tool_and_arguments() -> None:
    tool, arguments, _error = _run(_RefusingGateway())[0]
    assert tool == "list_charts"
    assert arguments["filters"][0]["col"] == "datasource_id"


def test_a_refusal_does_not_stop_the_loop() -> None:
    """A failed call is information the model can act on, not a crash."""
    assert len(_run(_RefusingGateway())) == 1


# --- the trace has to show it ------------------------------------------------


def _event(**overrides: Any) -> dict[str, Any]:
    event = {
        "type": "tool_call",
        "tool": "list_charts",
        "arguments": {"filters": [{"col": "datasource_id"}]},
    }
    event.update(overrides)
    return event


def _rendered(**overrides: Any) -> str:
    return render({"events": [_event(**overrides)]})


def test_the_trace_shows_a_refusal() -> None:
    text = _rendered(error="Input should be 'slice_name'")
    assert "slice_name" in text, "the reason the call was refused"
    assert "❌" in text, "and that it was refused at all"


def test_the_trace_marks_a_working_call_differently() -> None:
    """The whole point: the two must not look the same."""
    assert _rendered(error="nope") != _rendered()
    assert "❌" not in _rendered()


def test_a_long_refusal_is_truncated_not_dropped() -> None:
    text = _rendered(error="x" * 5000)
    assert "_refused_" in text
    assert len(text) < 1000
