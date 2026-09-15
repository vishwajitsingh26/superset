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
"""A call cut off at its budget is billed in full, so it is recorded in full."""

from __future__ import annotations

import pathlib
from typing import Any

import pytest

from superset.design_to_dashboard.llm.base import LLMError, LLMTruncatedError
from superset.design_to_dashboard.llm.recorder import (
    _ThinkingCapture,
    RECORD_ROOT,
    RecordingProvider,
)
from superset.utils import json

PARTIAL = '{"final": {"files": [{"path": "a.ts", "con'


class _Failing:
    name = "bedrock"
    model = "m"
    effort = "medium"

    def __init__(self, error: Exception) -> None:
        self.error = error

    def complete(self, *args: Any, **kwargs: Any) -> Any:
        raise self.error


def _call(tmp_path: pathlib.Path, error: Exception) -> pathlib.Path:
    provider = RecordingProvider(_Failing(error), "F", "s1", tmp_path)
    with pytest.raises(type(error)):
        provider.complete("system", "user")
    return tmp_path / RECORD_ROOT / "s1" / "F_01"


def test_a_truncated_call_keeps_its_partial_reply_and_usage(
    tmp_path: pathlib.Path,
) -> None:
    attempts = [{"output_tokens": 32000}, {"output_tokens": 64000}]
    call = _call(
        tmp_path,
        LLMTruncatedError(
            "cut off",
            max_tokens=64000,
            output_tokens=64000,
            thinking_tokens=51000,
            partial_text=PARTIAL,
            attempts=attempts,
        ),
    )
    assert (call / "output.txt").read_text() == PARTIAL
    meta = json.loads((call / "meta.json").read_text())
    assert meta["usage"]["truncated_attempts"] == attempts
    assert meta["usage"]["max_tokens"] == 64000
    assert meta["usage"]["thinking_tokens"] == 51000
    assert meta["usage"]["stop_reason"] == "max_tokens"
    assert meta["output_chars"] == len(PARTIAL)
    assert meta["error"].startswith("LLMTruncatedError")


def test_any_other_failure_is_recorded_as_before(tmp_path: pathlib.Path) -> None:
    call = _call(tmp_path, LLMError("stream reset"))
    assert not (call / "output.txt").exists()
    meta = json.loads((call / "meta.json").read_text())
    assert meta["usage"] == {}
    assert meta["error"] == "LLMError: stream reset"


def test_the_reasoning_of_every_attempt_is_kept_apart() -> None:
    """The discarded attempt ran out of room, so its reasoning shows how; the
    kept one answered. Both are recorded, never one beside the other's reply."""
    passed: list[dict[str, Any]] = []
    capture = _ThinkingCapture(passed.append)
    capture.sink({"phase": "thinking", "text": "x" * 500})
    capture.sink({"phase": "restart", "text": ""})
    capture.sink({"phase": "thinking", "text": "y" * 100})
    text = capture.text
    first = text.index("## Attempt 1 of 2 (re-sent)")
    second = text.index("## Attempt 2 of 2")
    assert first < text.index("x" * 500) < second < text.index("y" * 100)
    assert "x" * 501 not in text
    assert len(passed) == 3


def test_a_single_attempt_is_recorded_as_it_streamed() -> None:
    capture = _ThinkingCapture()
    capture.sink({"phase": "thinking", "text": "ab"})
    capture.sink({"phase": "thinking", "text": "abcd"})
    assert capture.text == "abcd"


def test_restarts_that_streamed_no_reasoning_record_none() -> None:
    capture = _ThinkingCapture()
    capture.sink({"phase": "restart", "text": ""})
    assert capture.text == ""


def test_a_failed_re_send_keeps_the_cut_off_attempts_reasoning(
    tmp_path: pathlib.Path,
) -> None:
    """The recorded reply is the first attempt's, so its reasoning must be there."""

    class _EscalatedThenFailed:
        name = "fake"
        model = "m"
        effort = "medium"

        def complete(self, *args: Any, **kwargs: Any) -> Any:
            sink = args[4]
            sink({"phase": "thinking", "text": "spent the budget"})
            sink({"phase": "restart", "text": ""})
            sink({"phase": "thinking", "text": "re-sent"})
            raise LLMTruncatedError("cut off", max_tokens=32000, partial_text=PARTIAL)

    provider = RecordingProvider(_EscalatedThenFailed(), "C", "s1", tmp_path)
    with pytest.raises(LLMTruncatedError):
        provider.complete("system", "user")
    call = tmp_path / RECORD_ROOT / "s1" / "C_01"
    thinking = (call / "thinking.md").read_text()
    assert "spent the budget" in thinking
    assert "re-sent" in thinking
    assert (call / "output.txt").read_text() == PARTIAL
