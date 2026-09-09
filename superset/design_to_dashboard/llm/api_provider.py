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
"""API-based LLM providers: direct Anthropic API and Amazon Bedrock.

Unlike the local ``claude_cli`` provider, these return **readable reasoning**.
The Claude Code CLI streams thinking blocks with empty text because it uses the
default ``display: "omitted"``; the API accepts
``thinking={"type": "adaptive", "display": "summarized"}``, which returns a
summary of the reasoning as it is produced.

Both classes satisfy the same ``LLMProvider`` protocol as ``ClaudeCliProvider``,
so no pipeline stage changes when you switch.
"""

from __future__ import annotations

import base64
import logging
import mimetypes
import pathlib
from typing import Any

from .base import LLMError, LLMResponse, LLMTimeoutError

logger = logging.getLogger(__name__)

DEFAULT_MAX_TOKENS = 32000
DEFAULT_EFFORT = "high"


def _image_block(path: str) -> dict[str, Any]:
    """Encode a design image as an API image block."""
    file_path = pathlib.Path(path)
    if not file_path.exists():
        raise LLMError(f"Image not found: {path}")
    media_type = mimetypes.guess_type(file_path.name)[0] or "image/png"
    if media_type == "application/pdf":
        return {
            "type": "document",
            "source": {
                "type": "base64",
                "media_type": media_type,
                "data": base64.standard_b64encode(file_path.read_bytes()).decode(),
            },
        }
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": media_type,
            "data": base64.standard_b64encode(file_path.read_bytes()).decode(),
        },
    }


class _BaseApiProvider:
    """Shared request/stream handling for the API-backed providers."""

    name = "api"

    def __init__(
        self,
        model: str,
        timeout: int = 600,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        effort: str = DEFAULT_EFFORT,
    ) -> None:
        self.model = model
        self.timeout = timeout
        self.max_tokens = max_tokens
        self.effort = effort
        self._client = self._build_client()

    def _build_client(self) -> Any:  # pragma: no cover - overridden
        raise NotImplementedError

    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        image_paths: list[str] | None = None,
        timeout: int | None = None,
        on_thinking: Any = None,
    ) -> LLMResponse:
        content: list[dict[str, Any]] = [
            _image_block(path) for path in (image_paths or [])
        ]
        content.append({"type": "text", "text": user_prompt})

        # The system prompt is stable across runs (preamble, stage prompt,
        # envelope, tool catalogue, registry summaries) while only the user turn
        # varies, so one breakpoint at its end caches the whole thing. The Agent
        # SDK does this automatically; on the API it is opt-in, and skipping it
        # measured ~8x more expensive on a repeat call.
        system_blocks: list[dict[str, Any]] = [
            {
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"},
            }
        ]

        request: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "system": system_blocks,
            "messages": [{"role": "user", "content": content}],
            # Reasoning is returned as a readable summary. The default is
            # "omitted", which yields empty thinking blocks -- the exact
            # behaviour the CLI provider is stuck with.
            "thinking": {"type": "adaptive", "display": "summarized"},
            "output_config": {"effort": self.effort},
        }

        client = self._client.with_options(timeout=timeout or self.timeout)
        try:
            # Streaming is required at these max_tokens values and is what lets
            # reasoning surface while the model works.
            with client.messages.stream(**request) as stream:
                thinking: list[str] = []
                for event in stream:
                    if event.type != "content_block_delta":
                        continue
                    delta = event.delta
                    if getattr(delta, "type", None) == "thinking_delta":
                        chunk = getattr(delta, "thinking", "") or ""
                        if chunk and on_thinking:
                            thinking.append(chunk)
                            on_thinking(
                                {"phase": "thinking", "text": "".join(thinking)}
                            )
                message = stream.get_final_message()
        except Exception as ex:  # noqa: BLE001 - normalised below
            if "timeout" in str(ex).lower():
                raise LLMTimeoutError(f"{self.name} timed out: {ex}") from ex
            raise LLMError(f"{self.name} request failed: {ex}") from ex

        if getattr(message, "stop_reason", None) == "refusal":
            details = getattr(message, "stop_details", None)
            raise LLMError(
                f"Request refused ({getattr(details, 'category', 'unknown')}): "
                f"{getattr(details, 'explanation', '')}"
            )

        text = "".join(block.text for block in message.content if block.type == "text")
        if not text:
            raise LLMError(f"{self.name} returned no text content")

        usage = getattr(message, "usage", None)
        usage_dict: dict[str, Any] = (
            usage.model_dump()
            if usage is not None and hasattr(usage, "model_dump")
            else {}
        )
        # A cache_read of zero across repeated calls means something in the
        # prefix is varying -- worth seeing in the logs rather than only in the bill.
        if usage_dict.get("cache_read_input_tokens") == 0:
            logger.info(
                "%s: no cache read (creation=%s) - check the system prompt is stable",
                self.name,
                usage_dict.get("cache_creation_input_tokens"),
            )
        return LLMResponse(
            text=text,
            cost_usd=None,  # billing is reported per-account, not per-response
            usage=usage_dict,
            session_id=getattr(message, "id", None),
            provider=self.name,
        )


class AnthropicApiProvider(_BaseApiProvider):
    """Direct Anthropic API. Credentials from ANTHROPIC_API_KEY or `ant auth login`."""

    name = "anthropic_api"

    def _build_client(self) -> Any:
        try:
            from anthropic import Anthropic
        except ImportError as ex:  # pragma: no cover
            raise LLMError(
                "The 'anthropic' package is not installed. "
                "Add it to requirements and reinstall."
            ) from ex
        # Zero-arg construction resolves ANTHROPIC_API_KEY, then an `ant auth`
        # profile, so no key is required in config.
        return Anthropic()


class BedrockProvider(_BaseApiProvider):
    """Claude on Amazon Bedrock, via the Mantle (Messages API) client."""

    name = "bedrock"

    def __init__(self, aws_region: str = "us-east-1", **kwargs: Any) -> None:
        self.aws_region = aws_region
        super().__init__(**kwargs)

    def _build_client(self) -> Any:
        try:
            from anthropic import AnthropicBedrockMantle
        except ImportError as ex:  # pragma: no cover
            raise LLMError(
                "AnthropicBedrockMantle is unavailable. Install the anthropic "
                "SDK with Bedrock support."
            ) from ex
        return AnthropicBedrockMantle(aws_region=self.aws_region)

    def _build_request_model(self) -> str:
        # Bedrock model ids carry an "anthropic." prefix.
        return (
            self.model
            if self.model.startswith("anthropic.")
            else f"anthropic.{self.model}"
        )

    def complete(self, *args: Any, **kwargs: Any) -> LLMResponse:
        original = self.model
        self.model = self._build_request_model()
        try:
            return super().complete(*args, **kwargs)
        finally:
            self.model = original
