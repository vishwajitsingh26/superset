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
"""Telling a spent turn budget apart from every other Agent SDK error.

A bare `LLMError` here read to `run_one` as an ordinary failure and got no
retry -- indistinguishable from a model that refused outright. In run
dc2e58c1 (2026-09-14) this dropped 8 of 11 stage-F plugins from one dashboard.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from superset.design_to_dashboard.llm.agent_sdk import (
    _is_max_turns_error,
    _preview,
    ClaudeAgentSdkProvider,
    TOOL_RESULT_PREVIEW_LENGTH,
)


def test_the_sdk_s_own_wording_is_recognised() -> None:
    assert _is_max_turns_error("['Reached maximum number of turns (6)']")


def test_case_does_not_matter() -> None:
    assert _is_max_turns_error("Maximum Number Of Turns reached")


def test_an_unrelated_error_is_not_mistaken_for_it() -> None:
    assert not _is_max_turns_error("['API Error: rate limited']")
    assert not _is_max_turns_error("")


# --- _preview: what of a tool result survives into the trace ----------------


def test_plain_text_is_kept_as_is() -> None:
    assert _preview("file not found") == "file not found"


def test_none_stays_none() -> None:
    assert _preview(None) is None


def test_a_long_result_is_cut_with_a_marker() -> None:
    text = "x" * (TOOL_RESULT_PREVIEW_LENGTH + 50)
    result = _preview(text)
    assert result is not None
    assert len(result) == TOOL_RESULT_PREVIEW_LENGTH
    assert result.endswith("…")


def test_an_image_result_is_summarised_by_block_type_not_its_bytes() -> None:
    # A `Read` on an image returns its bytes as base64 under `source` -- never
    # touched, or every trace would be megabytes of unreadable text.
    blocks = [{"type": "image", "source": {"data": "…lots of base64…"}}]
    assert _preview(blocks) == "image"


def test_whitespace_is_collapsed() -> None:
    assert _preview("a\n\nb   c") == "a b c"


# --- ClaudeAgentSdkProvider: turn-by-turn tool-call telemetry ---------------


def _agent_sdk_types() -> Any:
    from claude_agent_sdk import types

    return types


async def _fake_query(**_: Any) -> Any:
    """A canned turn sequence: one Read call, its result, a final answer."""
    types = _agent_sdk_types()
    for message in [
        types.AssistantMessage(
            content=[types.ToolUseBlock(id="t1", name="Read", input={"path": "a.png"})],
            model="claude-sonnet-5",
        ),
        types.UserMessage(
            content=[
                types.ToolResultBlock(
                    tool_use_id="t1",
                    content=[{"type": "image", "source": {"data": "…"}}],
                    is_error=False,
                )
            ]
        ),
        types.AssistantMessage(
            content=[types.TextBlock(text='{"ok": true}')],
            model="claude-sonnet-5",
        ),
        types.ResultMessage(
            subtype="success",
            duration_ms=100,
            duration_api_ms=100,
            is_error=False,
            num_turns=2,
            session_id="s1",
            total_cost_usd=0.01,
            usage={"input_tokens": 10, "output_tokens": 5},
            result='{"ok": true}',
            terminal_reason="completed",
        ),
    ]:
        yield message


def test_a_read_call_and_its_result_are_recorded_against_the_same_turn() -> None:
    with patch("claude_agent_sdk.query", _fake_query):
        provider = ClaudeAgentSdkProvider(max_turns=6)
        response = provider.complete("system", "user")

    assert len(response.tool_calls) == 1
    call = response.tool_calls[0]
    assert call["turn"] == 1
    assert call["tool"] == "Read"
    assert call["input"] == {"path": "a.png"}
    assert call["result_is_error"] is False
    # The image bytes never reach the trace -- only what kind of block it was.
    assert call["result_preview"] == "image"


def test_num_turns_and_terminal_reason_reach_the_response_usage() -> None:
    with patch("claude_agent_sdk.query", _fake_query):
        provider = ClaudeAgentSdkProvider(max_turns=6)
        response = provider.complete("system", "user")

    assert response.usage["num_turns"] == 2
    assert response.usage["terminal_reason"] == "completed"
    assert response.usage["result_subtype"] == "success"
    # The real token usage the SDK reported is not clobbered by the above.
    assert response.usage["input_tokens"] == 10


def test_unlimited_max_turns_is_accepted() -> None:
    """`None` must reach `ClaudeAgentOptions` unchanged, not crash the call --
    it is how observation mode asks for no cap at all."""
    with patch("claude_agent_sdk.query", _fake_query):
        provider = ClaudeAgentSdkProvider(max_turns=None)
        response = provider.complete("system", "user")

    assert response.text == '{"ok": true}'


@pytest.mark.parametrize(
    "detail",
    [
        "['Reached maximum number of turns (6)']",
        "Maximum Number Of Turns reached",
    ],
)
def test_a_max_turns_result_still_carries_no_tool_calls_lost_before_the_error(
    detail: str,
) -> None:
    """Documents current behaviour: an error path returns nothing (no
    LLMResponse is constructed), so the tool-call trace gathered before the
    failure is lost -- same as thinking/text today. Observation mode is
    aimed at the success path; a stuck call that errors out still won't show
    its tool calls in the trace."""
    from superset.design_to_dashboard.llm.base import LLMMaxTurnsError

    types = _agent_sdk_types()

    async def failing_query(**_: Any) -> Any:
        yield types.AssistantMessage(
            content=[types.ToolUseBlock(id="t1", name="Read", input={"path": "a.png"})],
            model="claude-sonnet-5",
        )
        yield types.ResultMessage(
            subtype="error_max_turns",
            duration_ms=100,
            duration_api_ms=100,
            is_error=True,
            num_turns=6,
            session_id="s1",
            result=detail,
        )

    with patch("claude_agent_sdk.query", failing_query):
        provider = ClaudeAgentSdkProvider(max_turns=6)
        with pytest.raises(LLMMaxTurnsError):
            provider.complete("system", "user")
