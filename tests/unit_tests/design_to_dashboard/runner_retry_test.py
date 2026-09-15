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
"""How the runner reacts to a spent budget, and how it reports what it built.

A reply cut off at its output budget was re-sent as if it were flaky, and a
custom chart nothing could query was counted among the working ones.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

from superset.design_to_dashboard.llm.base import (
    LLMError,
    LLMMaxTurnsError,
    LLMTruncatedError,
)
from superset.design_to_dashboard.llm.recorder import RecordingProvider
from superset.design_to_dashboard.runner import (
    _chart_checks,
    _done_label,
    _higher_turns_provider,
    _lower_effort_provider,
    _retry,
)
from superset.design_to_dashboard.verify import ChartCheck, VerifyResult
from superset.design_to_dashboard.visual_verify import ChartRender

FACTORY = "superset.design_to_dashboard.llm.factory.get_llm_provider"
CONFIG = "superset.design_to_dashboard.runner._config"


class _Session:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, Any]]] = []

    def publish(self, kind: str, **fields: Any) -> None:
        self.events.append((kind, fields))


def _cut_off() -> LLMTruncatedError:
    return LLMTruncatedError(
        "cut off at 64000 tokens", max_tokens=64000, output_tokens=64000
    )


def _raises(error: Exception, calls: list[str], name: str) -> Any:
    def call() -> Any:
        calls.append(name)
        raise error

    return call


def test_a_truncated_reply_is_not_sent_again() -> None:
    calls: list[str] = []
    with pytest.raises(LLMTruncatedError):
        _retry(_Session(), "Building", 2, _raises(_cut_off(), calls, "same"))
    assert calls == ["same"]


def test_a_truncated_reply_is_asked_the_cheaper_way_once() -> None:
    session = _Session()
    calls: list[str] = []

    def cheaper() -> str:
        calls.append("cheaper")
        return "scaffold"

    result = _retry(
        session,
        "Building",
        2,
        _raises(_cut_off(), calls, "same"),
        on_truncated=cheaper,
    )
    assert result == "scaffold"
    assert calls == ["same", "cheaper"]
    assert [kind for kind, _ in session.events] == ["retry"]
    assert "ran out of output budget" in session.events[0][1]["label"]


def test_a_cheaper_attempt_that_is_cut_off_too_is_raised() -> None:
    calls: list[str] = []
    with pytest.raises(LLMTruncatedError):
        _retry(
            _Session(),
            "Building",
            3,
            _raises(_cut_off(), calls, "same"),
            on_truncated=_raises(_cut_off(), calls, "cheaper"),
        )
    assert calls == ["same", "cheaper"]


def _out_of_turns() -> LLMMaxTurnsError:
    return LLMMaxTurnsError(
        "Agent SDK reported an error: ['Reached maximum number of turns (6)']",
        max_turns=6,
    )


def test_an_exhausted_turn_budget_is_not_sent_again() -> None:
    calls: list[str] = []
    with pytest.raises(LLMMaxTurnsError):
        _retry(_Session(), "Building", 2, _raises(_out_of_turns(), calls, "same"))
    assert calls == ["same"]


def test_an_exhausted_turn_budget_is_asked_with_more_turns_once() -> None:
    session = _Session()
    calls: list[str] = []

    def bigger() -> str:
        calls.append("bigger")
        return "scaffold"

    result = _retry(
        session,
        "Building",
        2,
        _raises(_out_of_turns(), calls, "same"),
        on_max_turns=bigger,
    )
    assert result == "scaffold"
    assert calls == ["same", "bigger"]
    assert [kind for kind, _ in session.events] == ["retry"]
    assert "ran out of turns" in session.events[0][1]["label"]


def test_a_bigger_attempt_that_still_runs_out_is_raised() -> None:
    calls: list[str] = []
    with pytest.raises(LLMMaxTurnsError):
        _retry(
            _Session(),
            "Building",
            3,
            _raises(_out_of_turns(), calls, "same"),
            on_max_turns=_raises(_out_of_turns(), calls, "bigger"),
        )
    assert calls == ["same", "bigger"]


def test_a_transient_error_is_still_retried_the_same_way() -> None:
    outcomes: list[Any] = [LLMError("stream reset"), "scaffold"]
    fallback: list[str] = []

    def call() -> Any:
        outcome = outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    result = _retry(
        _Session(), "Building", 2, call, on_truncated=lambda: fallback.append("x")
    )
    assert result == "scaffold"
    assert fallback == []


def test_the_fallback_provider_thinks_one_level_less_hard() -> None:
    built = SimpleNamespace(name="bedrock", effort="low")
    with patch(FACTORY, return_value=built) as factory, patch(CONFIG, return_value={}):
        provider = _lower_effort_provider(SimpleNamespace(effort="medium"), "F", "s")
    assert provider is built
    factory.assert_called_once_with("F", effort="low")


def test_there_is_no_fallback_below_the_lowest_effort() -> None:
    with patch(FACTORY) as factory, patch(CONFIG, return_value={}):
        assert _lower_effort_provider(SimpleNamespace(effort="low"), "F", "s") is None
        assert _lower_effort_provider(SimpleNamespace(), "F", "s") is None
    factory.assert_not_called()


def test_a_fallback_that_cannot_be_built_is_no_fallback() -> None:
    with (
        patch(FACTORY, side_effect=LLMError("bad config")),
        patch(CONFIG, return_value={}),
    ):
        assert _lower_effort_provider(SimpleNamespace(effort="high"), "F", "s") is None


def test_a_recorded_fallback_keeps_its_own_traces() -> None:
    """Numbered from 1 under the stage's own label, it would overwrite F_01."""
    built = SimpleNamespace(name="bedrock", effort="medium")
    with (
        patch(FACTORY, return_value=built),
        patch(CONFIG, return_value={"record_calls": True}),
    ):
        provider = _lower_effort_provider(SimpleNamespace(effort="high"), "F", "s")
    assert isinstance(provider, RecordingProvider)
    assert provider.inner is built
    assert provider.stage == "F-medium"


def test_the_turns_fallback_doubles_the_budget() -> None:
    built = SimpleNamespace(name="claude_agent_sdk", max_turns=32)
    with patch(FACTORY, return_value=built) as factory, patch(CONFIG, return_value={}):
        provider = _higher_turns_provider(SimpleNamespace(max_turns=16), "F", "s")
    assert provider is built
    factory.assert_called_once_with("F", max_turns=32)


def test_the_turns_fallback_is_capped() -> None:
    built = SimpleNamespace(name="claude_agent_sdk", max_turns=48)
    with patch(FACTORY, return_value=built) as factory, patch(CONFIG, return_value={}):
        provider = _higher_turns_provider(SimpleNamespace(max_turns=40), "F", "s")
    assert provider is built
    factory.assert_called_once_with("F", max_turns=48)


def test_there_is_no_turns_fallback_once_the_cap_is_reached() -> None:
    with patch(FACTORY) as factory, patch(CONFIG, return_value={}):
        assert _higher_turns_provider(SimpleNamespace(max_turns=48), "F", "s") is None
        assert _higher_turns_provider(SimpleNamespace(max_turns=50), "F", "s") is None
        assert _higher_turns_provider(SimpleNamespace(), "F", "s") is None
    factory.assert_not_called()


def test_there_is_no_turns_fallback_for_an_already_unlimited_provider() -> None:
    """Observation mode (`max_turns=None`): doubling nothing is still
    nothing, and this failure cannot occur for it anyway."""
    with patch(FACTORY) as factory, patch(CONFIG, return_value={}):
        assert _higher_turns_provider(SimpleNamespace(max_turns=None), "F", "s") is None
    factory.assert_not_called()


def test_a_turns_fallback_that_cannot_be_built_is_no_fallback() -> None:
    with (
        patch(FACTORY, side_effect=LLMError("bad config")),
        patch(CONFIG, return_value={}),
    ):
        assert _higher_turns_provider(SimpleNamespace(max_turns=16), "F", "s") is None


def test_a_recorded_turns_fallback_keeps_its_own_traces() -> None:
    built = SimpleNamespace(name="claude_agent_sdk", max_turns=32)
    with (
        patch(FACTORY, return_value=built),
        patch(CONFIG, return_value={"record_calls": True}),
    ):
        provider = _higher_turns_provider(SimpleNamespace(max_turns=16), "F", "s")
    assert isinstance(provider, RecordingProvider)
    assert provider.inner is built
    assert provider.stage == "F-turns32"


def _visual(**fields: Any) -> SimpleNamespace:
    return SimpleNamespace(
        **{"blocked": None, "verdict": "pass", "score": 60, **fields}
    )


def test_an_unchecked_chart_is_named_in_the_headline() -> None:
    checks = VerifyResult(
        dashboard_id=1,
        charts=[
            ChartCheck(1, "Coverage tile", "custom_tile", ok=True, checked=False),
            ChartCheck(2, "Accounts", "table", ok=True, rows=4),
        ],
    )
    assert _done_label(checks, _visual()) == (
        "Dashboard created — 1 of 2 charts not checked"
    )


def test_a_chart_that_failed_to_render_is_not_right() -> None:
    checks = VerifyResult(
        dashboard_id=1,
        charts=[ChartCheck(1, "Coverage tile", "custom_tile", ok=True, checked=False)],
    )
    checks.apply_render(
        {1: ChartRender(chart_id=1, on_page=True, card_error="TypeError: x is null")}
    )
    assert _done_label(checks, _visual()) == (
        "Dashboard created — 1 of 1 charts not right"
    )


def test_a_clean_run_has_a_plain_headline() -> None:
    checks = VerifyResult(
        dashboard_id=1, charts=[ChartCheck(2, "Accounts", "table", ok=True, rows=4)]
    )
    assert _done_label(checks, _visual()) == "Dashboard created"


def test_published_checks_carry_what_the_browser_saw() -> None:
    checks = VerifyResult(
        dashboard_id=1,
        charts=[ChartCheck(1, "Coverage tile", "custom_tile", ok=True, checked=False)],
    )
    checks.apply_render(
        {1: ChartRender(chart_id=1, on_page=True, card_error="TypeError: x is null")}
    )
    (published,) = _chart_checks(checks)
    assert published["checked"] is True
    assert published["ok"] is False
    assert "TypeError" in published["render_error"]
    assert published["status_code"] is None
    assert published["name"] == "Coverage tile"
