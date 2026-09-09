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
"""Claude Agent SDK provider.

Uses the Claude Code credentials already on the host -- no API key -- while
still accepting ``thinking={"type": "adaptive", "display": "summarized"}``,
which the `claude -p` CLI does not expose. That combination is what makes
readable reasoning available before API credentials are provisioned.

Same ``LLMProvider`` protocol as every other provider, so switching to
``anthropic_api`` or ``bedrock`` later is a config change only.
"""

from __future__ import annotations

import asyncio
import logging
import pathlib
from typing import Any

from .base import LLMError, LLMResponse, LLMTimeoutError

logger = logging.getLogger(__name__)


class ClaudeAgentSdkProvider:
    """Runs a single stateless query through the Claude Agent SDK."""

    name = "claude_agent_sdk"

    def __init__(
        self,
        model: str = "claude-opus-5",
        timeout: int = 600,
        max_turns: int = 6,
        display: str = "summarized",
    ) -> None:
        try:
            import claude_agent_sdk  # noqa: F401
        except ImportError as ex:  # pragma: no cover
            raise LLMError(
                "claude-agent-sdk is not installed. `uv pip install claude-agent-sdk`"
            ) from ex
        self.model = model
        self.timeout = timeout
        self.max_turns = max_turns
        self.display = display

    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        image_paths: list[str] | None = None,
        timeout: int | None = None,
        on_thinking: Any = None,
    ) -> LLMResponse:
        return asyncio.run(
            self._complete_async(
                system_prompt,
                user_prompt,
                image_paths or [],
                timeout or self.timeout,
                on_thinking,
            )
        )

    async def _complete_async(  # noqa: C901
        self,
        system_prompt: str,
        user_prompt: str,
        image_paths: list[str],
        timeout: int,
        on_thinking: Any,
    ) -> LLMResponse:
        from claude_agent_sdk import query
        from claude_agent_sdk.types import (
            AssistantMessage,
            ClaudeAgentOptions,
            ResultMessage,
            StreamEvent,
            TextBlock,
            ThinkingBlock,
        )

        prompt = self._compose(user_prompt, image_paths)
        options = ClaudeAgentOptions(
            model=self.model,
            system_prompt=system_prompt,
            max_turns=self.max_turns,
            # Reading an image needs the Read tool; a text-only stage gets none,
            # so a stray tool attempt cannot consume the turn budget.
            allowed_tools=["Read"] if image_paths else [],
            permission_mode="bypassPermissions" if image_paths else "default",
            thinking={"type": "adaptive", "display": self.display},
            # Without this, ThinkingBlock only arrives inside the completed
            # AssistantMessage -- i.e. at the very end of the stage, which is
            # useless for a live view. Partial messages stream the deltas.
            include_partial_messages=True,
            # Messages travel as JSON over stdio. An image returned by the Read
            # tool is base64 in that payload, and the default 1 MB buffer is
            # exceeded by a contact sheet of any size -- the failure is
            # "JSON message exceeded maximum buffer size".
            max_buffer_size=32 * 1024 * 1024,
        )

        thinking_parts: list[str] = []
        streamed: list[str] = []
        text_parts: list[str] = []
        cost: float | None = None
        usage: dict[str, Any] = {}
        session_id: str | None = None
        result_text: str | None = None

        async def run() -> None:  # noqa: C901
            nonlocal cost, usage, session_id, result_text
            async for message in query(prompt=prompt, options=options):
                if isinstance(message, StreamEvent):
                    # Raw Anthropic stream event: thinking_delta carries the
                    # summarized reasoning as it is produced.
                    event = message.event or {}
                    if event.get("type") == "content_block_delta":
                        delta = event.get("delta") or {}
                        if delta.get("type") == "thinking_delta":
                            chunk = delta.get("thinking") or ""
                            if chunk:
                                streamed.append(chunk)
                                if on_thinking:
                                    on_thinking(
                                        {
                                            "phase": "thinking",
                                            "text": "".join(streamed),
                                        }
                                    )
                    continue
                if isinstance(message, AssistantMessage):
                    session_id = message.session_id or session_id
                    for block in message.content:
                        if isinstance(block, ThinkingBlock):
                            chunk = block.thinking or ""
                            # Only used when partial streaming produced nothing,
                            # so the same text is not emitted twice.
                            if chunk and not streamed:
                                thinking_parts.append(chunk)
                                if on_thinking:
                                    on_thinking(
                                        {
                                            "phase": "thinking",
                                            "text": "\n".join(thinking_parts),
                                        }
                                    )
                        elif isinstance(block, TextBlock):
                            text_parts.append(block.text or "")
                elif isinstance(message, ResultMessage):
                    cost = message.total_cost_usd
                    usage = message.usage or {}
                    session_id = message.session_id or session_id
                    if message.is_error:
                        raise LLMError(
                            f"Agent SDK reported an error: "
                            f"{message.result or message.errors}"
                        )
                    # `result` is the authoritative final text.
                    if isinstance(message.result, str) and message.result.strip():
                        result_text = message.result

        try:
            await asyncio.wait_for(run(), timeout=timeout)
        except asyncio.TimeoutError as ex:
            raise LLMTimeoutError(f"Agent SDK timed out after {timeout}s") from ex
        except LLMError:
            raise
        except Exception as ex:  # noqa: BLE001
            raise LLMError(f"Agent SDK request failed: {ex}") from ex

        text = result_text or "".join(text_parts)
        if not text.strip():
            raise LLMError("Agent SDK returned no text content")

        return LLMResponse(
            text=text,
            cost_usd=cost,
            usage=usage if isinstance(usage, dict) else {},
            session_id=session_id,
            provider=self.name,
        )

    @staticmethod
    def _compose(user_prompt: str, image_paths: list[str]) -> str:
        """Point the model at design images on disk.

        The SDK takes a text prompt, so images are referenced by absolute path
        and read with the Read tool -- the same approach the CLI provider uses.
        """
        if not image_paths:
            return user_prompt
        for path in image_paths:
            if not pathlib.Path(path).exists():
                raise LLMError(f"Image not found: {path}")
            if not pathlib.Path(path).is_absolute():
                raise LLMError(f"Image path must be absolute: {path}")
        listed = "\n".join(f"- {p}" for p in image_paths)
        return (
            f"{user_prompt}\n\n"
            f"Read the following design image(s) before answering:\n{listed}"
        )
