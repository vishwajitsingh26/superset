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
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from superset.design_to_dashboard.llm import api_provider
from superset.design_to_dashboard.llm.api_provider import (
    _BaseApiProvider,
    is_retryable,
)
from superset.design_to_dashboard.llm.base import (
    LLMError,
    LLMTimeoutError,
    LLMTruncatedError,
)

BEDROCK_500 = (
    "Bad response code, expected 200: {'status_code': 400, 'headers': "
    "{':exception-type': 'internalServerException'}, 'body': b'{}'}"
)


class _FakeProvider(_BaseApiProvider):
    name = "fake"

    def __init__(self, outcomes: list[Any], **kwargs: Any) -> None:
        self.outcomes = outcomes
        self.calls = 0
        self.budgets: list[int] = []
        super().__init__(model="m", **kwargs)

    def _build_client(self) -> Any:
        return MagicMock()

    def _stream_once(
        self, request: dict[str, Any], timeout: int | None, on_thinking: Any
    ) -> Any:
        outcome = self.outcomes[self.calls]
        self.calls += 1
        self.budgets.append(request["max_tokens"])
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _message(text: str = '{"final": {}}') -> MagicMock:
    block = MagicMock(type="text", text=text)
    return MagicMock(content=[block], stop_reason="end_turn", usage=None, id="msg")


def _truncated(
    output_tokens: int = 32000,
    thinking_tokens: int = 26591,
    stop_reason: str = "max_tokens",
) -> MagicMock:
    block = MagicMock(type="text", text='{"final": {"files": [{"path": "a.ts", "con')
    usage = MagicMock()
    usage.model_dump.return_value = {
        "output_tokens": output_tokens,
        "output_tokens_details": {"thinking_tokens": thinking_tokens},
    }
    return MagicMock(content=[block], stop_reason=stop_reason, usage=usage, id="msg")


def test_is_retryable_recognises_bedrock_stream_exception() -> None:
    assert is_retryable(Exception(BEDROCK_500))
    assert not is_retryable(Exception("validationException: bad field"))


@patch.object(api_provider.time, "sleep")
def test_transient_error_is_retried(sleep: MagicMock) -> None:
    provider = _FakeProvider([Exception(BEDROCK_500), _message("ok")])

    response = provider.complete("system", "user")

    assert response.text == "ok"
    assert provider.calls == 2
    sleep.assert_called_once()


@patch.object(api_provider.time, "sleep")
def test_gives_up_after_max_attempts(sleep: MagicMock) -> None:
    provider = _FakeProvider([Exception(BEDROCK_500)] * 3, max_attempts=2)

    with pytest.raises(LLMError, match="request failed"):
        provider.complete("system", "user")
    assert provider.calls == 2


@patch.object(api_provider.time, "sleep")
def test_bad_request_is_not_retried(sleep: MagicMock) -> None:
    provider = _FakeProvider([Exception("validationException: bad field")])

    with pytest.raises(LLMError, match="request failed"):
        provider.complete("system", "user")
    assert provider.calls == 1
    sleep.assert_not_called()


def test_max_tokens_stop_escalates_once_then_succeeds() -> None:
    provider = _FakeProvider([_truncated(), _message("ok")])

    response = provider.complete("system", "user")

    assert response.text == "ok"
    assert provider.budgets == [32000, 64000]
    # The discarded attempt was billed; its usage stays on the record.
    assert response.usage["truncated_attempts"][0]["output_tokens"] == 32000


def test_max_tokens_stop_after_escalation_raises_truncated() -> None:
    provider = _FakeProvider(
        [_truncated(), _truncated(output_tokens=64000, thinking_tokens=60000)]
    )

    with pytest.raises(LLMTruncatedError) as caught:
        provider.complete("system", "user")

    error = caught.value
    assert provider.calls == 2
    assert error.max_tokens == 64000
    assert error.output_tokens == 64000
    assert error.thinking_tokens == 60000
    assert [a["output_tokens"] for a in error.attempts] == [32000, 64000]
    assert error.partial_text.startswith('{"final"')
    assert "max_tokens=64000" in str(error)
    # A truncation is an LLMError, but never mistaken for a timeout.
    assert isinstance(error, LLMError)
    assert not isinstance(error, LLMTimeoutError)


def test_max_tokens_stop_at_the_ceiling_is_not_resent() -> None:
    provider = _FakeProvider([_truncated(output_tokens=64000)], max_tokens=64000)

    with pytest.raises(LLMTruncatedError):
        provider.complete("system", "user")
    assert provider.budgets == [64000]


def test_escalation_ceiling_is_configurable() -> None:
    provider = _FakeProvider([_truncated(), _message("ok")], max_tokens_ceiling=128000)

    provider.complete("system", "user")

    assert provider.budgets == [32000, 128000]


def test_escalation_starts_from_an_overridden_budget() -> None:
    provider = _FakeProvider(
        [_truncated(output_tokens=64000)],
        request_overrides={"max_tokens": 64000},
    )

    with pytest.raises(LLMTruncatedError, match="max_tokens=64000"):
        provider.complete("system", "user")
    assert provider.budgets == [64000]


def test_context_window_stop_is_truncated_without_a_resend() -> None:
    provider = _FakeProvider([_truncated(stop_reason="model_context_window_exceeded")])

    with pytest.raises(LLMTruncatedError) as caught:
        provider.complete("system", "user")
    assert caught.value.stop_reason == "model_context_window_exceeded"
    assert provider.calls == 1


def test_refusal_is_reported_as_before() -> None:
    refusal = MagicMock(
        content=[],
        stop_reason="refusal",
        stop_details=MagicMock(category="cyber", explanation="no"),
        usage=None,
    )
    provider = _FakeProvider([refusal])

    with pytest.raises(LLMError, match=r"Request refused \(cyber\): no") as caught:
        provider.complete("system", "user")
    assert not isinstance(caught.value, LLMTruncatedError)
    assert provider.calls == 1


def test_refusal_on_the_escalated_resend_is_reported_as_a_refusal() -> None:
    refusal = MagicMock(
        content=[],
        stop_reason="refusal",
        stop_details=MagicMock(category="bio", explanation="no"),
        usage=None,
    )
    provider = _FakeProvider([_truncated(), refusal])

    with pytest.raises(LLMError, match="Request refused") as caught:
        provider.complete("system", "user")
    assert not isinstance(caught.value, LLMTruncatedError)
    assert provider.calls == 2


def test_an_overridden_budget_below_the_ceiling_is_never_raised() -> None:
    """An override is the endpoint's limit; a larger re-send is a 400."""
    provider = _FakeProvider(
        [_truncated(output_tokens=16000)],
        request_overrides={"max_tokens": 16000},
    )

    with pytest.raises(LLMTruncatedError, match="max_tokens=16000"):
        provider.complete("system", "user")
    assert provider.budgets == [16000]


def test_a_failed_resend_is_still_reported_as_the_truncation() -> None:
    """The first attempt was billed and the budget is the cause; neither may
    vanish because the re-send failed for a reason of its own."""
    provider = _FakeProvider(
        [_truncated(), Exception("validationException: max_tokens too large")]
    )

    with pytest.raises(LLMTruncatedError) as caught:
        provider.complete("system", "user")

    error = caught.value
    assert provider.budgets == [32000, 64000]
    assert error.max_tokens == 32000
    assert [a["output_tokens"] for a in error.attempts] == [32000]
    assert error.partial_text.startswith('{"final"')
    assert "re-send at max_tokens=64000 failed" in str(error)
    assert isinstance(error.__cause__, LLMError)


def test_a_resend_announces_a_restart_to_the_reasoning_listener() -> None:
    updates: list[dict[str, Any]] = []
    provider = _FakeProvider([_truncated(), _message("ok")])

    provider.complete("system", "user", on_thinking=updates.append)

    assert updates == [{"phase": "restart", "text": ""}]


@patch.object(api_provider.time, "sleep")
def test_a_retried_stream_announces_a_restart(sleep: MagicMock) -> None:
    updates: list[dict[str, Any]] = []
    provider = _FakeProvider([Exception(BEDROCK_500), _message("ok")])

    provider.complete("system", "user", on_thinking=updates.append)

    assert updates == [{"phase": "restart", "text": ""}]
