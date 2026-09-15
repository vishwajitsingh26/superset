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
"""Provider-agnostic LLM interface for the Design-to-Dashboard pipeline.

Every pipeline stage talks to this interface, never to a vendor SDK, so the
local `claude -p` provider and a future Bedrock provider are interchangeable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


class LLMError(Exception):
    """Raised when a provider fails to produce a usable completion."""


class LLMTimeoutError(LLMError):
    """Raised when a provider exceeds its configured timeout."""


class LLMTruncatedError(LLMError):
    """Raised when a completion stopped at its output-token budget.

    The partial reply is usually JSON cut off mid-object. Handed on as a normal
    response it surfaces downstream as a parse error: the stage blames the
    model's formatting, the retry logic sees a bad answer rather than a spent
    budget, and nothing records that the budget was the problem. Raised as its
    own type, the caller can tell the two apart -- and knows that sending the
    identical request again will most likely be cut off at the same place.
    """

    def __init__(
        self,
        message: str,
        *,
        max_tokens: int | None,
        output_tokens: int | None = None,
        thinking_tokens: int | None = None,
        stop_reason: str = "max_tokens",
        partial_text: str = "",
        attempts: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(message)
        self.max_tokens = max_tokens
        self.output_tokens = output_tokens
        self.thinking_tokens = thinking_tokens
        self.stop_reason = stop_reason
        self.partial_text = partial_text
        # Usage of every attempt that was cut off, oldest first. A truncated
        # reply is billed in full, so this is what keeps it on the record.
        self.attempts = attempts or []


class LLMMalformedReplyError(LLMError):
    """Raised when a completion finished normally but does not parse as JSON.

    A sibling of `LLMTruncatedError`, not a subclass: the two look alike from
    the caller's side (both end in a stage failing to get usable JSON) but
    call for different retries. A truncated reply's fix is a smaller budget
    for reasoning -- a lower `effort` -- because reasoning is what filled the
    budget it ran out of. A malformed-but-complete reply was never a budget
    problem, so retrying it at lower effort is a guess with no evidence behind
    it; it gets the same plain retry any other transient `LLMError` gets,
    same effort, and nothing more.
    """


class LLMMaxTurnsError(LLMError):
    """Raised when an agent-loop provider exhausts its turn budget unanswered.

    Another sibling of `LLMTruncatedError`, not a subclass: both mean the
    model was cut off before it finished, but the lever that fixes each is
    different. A truncated reply ran out of *output* budget mid-answer --
    reasoning is what filled it, so a lower `effort` is the fix. This is cut
    off before it ever typed an answer, having spent its turns on tool calls
    instead -- for a stage given design images and only the `Read` tool, that
    is almost always opening them -- so a lower `effort` changes nothing and
    an identical retry burns the same budget on the same reads and fails the
    same way. What is left to try is a larger turn budget.
    """

    def __init__(self, message: str, *, max_turns: int | None = None) -> None:
        super().__init__(message)
        self.max_turns = max_turns


# Effort levels in increasing order of how hard the model thinks.
EFFORT_LEVELS = ("low", "medium", "high", "xhigh", "max")


def lower_effort(effort: str) -> str | None:
    """The next effort level down, or None at the bottom or for an unknown one.

    Reasoning is the part of an output budget that grows with effort, so this
    is the lever left once a reply is cut off at the largest budget allowed.
    """
    if effort not in EFFORT_LEVELS:
        return None
    index = EFFORT_LEVELS.index(effort)
    return EFFORT_LEVELS[index - 1] if index else None


@dataclass
class LLMResponse:
    """A single completion plus whatever telemetry the provider exposes."""

    text: str
    cost_usd: float | None = None
    usage: dict[str, Any] = field(default_factory=dict)
    session_id: str | None = None
    provider: str = ""
    # Every tool call an agent-loop provider made getting to this answer, in
    # order: {"turn": int, "tool": str, "input": dict, "result_is_error":
    # bool | None, "result_preview": str}. Empty for a provider with no tool
    # loop (anthropic_api, bedrock). This is what turns "the call took 14
    # turns" into "it re-read the same image four times" -- a turn count
    # alone cannot tell a stage's genuine need for more turns apart from one
    # thrashing on the same call, and deciding where turn budgets actually
    # need raising (or a prompt needs fixing instead) needs to see which.
    tool_calls: list[dict[str, Any]] = field(default_factory=list)


class LLMProvider(Protocol):
    """The contract every provider implements.

    Stages pass a system prompt, a user prompt, and optionally absolute paths
    to design images. Providers are responsible for making the images visible
    to the model; callers never deal with encoding.
    """

    name: str

    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        image_paths: list[str] | None = None,
        timeout: int | None = None,
        on_thinking: Any = None,
    ) -> LLMResponse: ...


# The Agent SDK bills two uncached input tokens for every model turn, so a call
# that ran more than one turn opened something with a tool. For a call whose
# only tool is `Read`, that something is an attached image.
AGENT_SDK_PROVIDER = "claude_agent_sdk"
AGENT_SDK_INPUT_TOKENS_PER_TURN = 2


def images_opened(response: LLMResponse) -> bool | None:
    """Whether a call that was given image paths actually opened them.

    Path-based providers hand the model a file path, not a picture, and the
    model decides whether to open it. Stage B's tool loop was told any image
    was "already attached" and never once opened the design, so the rule that
    the picture wins over stage A's text never ran -- and nothing noticed,
    because a call that skips the image still returns a plausible answer.

    Returns None when the provider gives no way to tell. This reads the Agent
    SDK's turn count, which is an inference from billing rather than a record
    of the tool call; pair it with a check on the answer itself.
    """
    if response.provider != AGENT_SDK_PROVIDER:
        return None
    input_tokens = response.usage.get("input_tokens")
    if not isinstance(input_tokens, int):
        return None
    return input_tokens // AGENT_SDK_INPUT_TOKENS_PER_TURN > 1
