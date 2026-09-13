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


@dataclass
class LLMResponse:
    """A single completion plus whatever telemetry the provider exposes."""

    text: str
    cost_usd: float | None = None
    usage: dict[str, Any] = field(default_factory=dict)
    session_id: str | None = None
    provider: str = ""


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
