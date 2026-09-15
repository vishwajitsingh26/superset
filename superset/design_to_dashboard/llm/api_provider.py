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
import contextlib
import logging
import mimetypes
import os
import pathlib
import re
import time
from typing import Any

from .base import LLMError, LLMResponse, LLMTimeoutError, LLMTruncatedError

logger = logging.getLogger(__name__)

DEFAULT_MAX_TOKENS = 32000
DEFAULT_EFFORT = "high"
# The budget a reply cut off at `max_tokens` is re-sent with, once. Adaptive
# thinking spends from the same budget as the answer, so a call that reasons at
# length can exhaust it before the answer is half written.
DEFAULT_MAX_TOKENS_CEILING = 64000
# `max_tokens` can be escalated; a full context window cannot, so a reply that
# stops on it is reported without a re-send.
ESCALATABLE_STOP_REASON = "max_tokens"
TRUNCATION_STOP_REASONS = frozenset(
    {ESCALATABLE_STOP_REASON, "model_context_window_exceeded"}
)

# Server-side failures worth another attempt. The SDK's own retries cover only
# the initial HTTP response; once a stream has started, Bedrock reports these as
# an exception *event* mid-stream, which surfaces as a plain error and is never
# retried. A design-step call can die this way minutes in on a request that
# succeeds unchanged on the next try.
RETRYABLE_ERRORS = (
    "internalserverexception",
    "modelstreamerrorexception",
    "serviceunavailableexception",
    "throttlingexception",
    "overloaded_error",
    "api_error",
)
DEFAULT_MAX_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = 5.0


def is_retryable(ex: Exception) -> bool:
    """Whether `ex` is a transient server-side failure rather than a bad request."""
    message = str(ex).lower()
    return any(marker in message for marker in RETRYABLE_ERRORS)


def _usage_dict(message: Any) -> dict[str, Any]:
    usage = getattr(message, "usage", None)
    if usage is not None and hasattr(usage, "model_dump"):
        return usage.model_dump()
    return {}


def _thinking_tokens(usage: dict[str, Any]) -> int | None:
    details = usage.get("output_tokens_details") or {}
    return details.get("thinking_tokens") if isinstance(details, dict) else None


def _text_of(message: Any) -> str:
    return "".join(
        block.text
        for block in getattr(message, "content", None) or []
        if block.type == "text"
    )


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
        request_overrides: dict[str, Any] | None = None,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        max_tokens_ceiling: int | None = None,
    ) -> None:
        self.model = model
        self.timeout = timeout
        self.max_tokens = max_tokens
        self.max_tokens_ceiling = (
            DEFAULT_MAX_TOKENS_CEILING
            if max_tokens_ceiling is None
            else max_tokens_ceiling
        )
        self.effort = effort
        self.max_attempts = max(1, max_attempts)
        self.request_overrides = request_overrides or {}
        self._client = self._build_client()

    def _build_client(self) -> Any:  # pragma: no cover - overridden
        raise NotImplementedError

    def _client_for_request(self, timeout: int) -> Any:
        """A client with the per-call timeout applied.

        ``with_options`` copies the client cheaply, which is right for the
        direct API. The Bedrock subclass overrides this because that copy drops
        ``aws_profile`` and would strand the request without credentials.
        """
        return self._client.with_options(timeout=timeout)

    def _apply_request_overrides(self, request: dict[str, Any]) -> dict[str, Any]:
        """Merge `request_overrides` into the request body.

        An escape hatch for endpoints that accept a narrower body than the
        first-party API: a value of ``None`` drops the key entirely, anything
        else replaces it. Bedrock in particular gates newer top-level fields
        (`output_config`, adaptive `thinking`) on the model and the
        `anthropic_version` it was onboarded with, and rejecting one is a 400
        rather than something the SDK can negotiate.
        """
        for key, value in self.request_overrides.items():
            if value is None:
                request.pop(key, None)
            else:
                request[key] = value
        return request

    def _stream_once(
        self, request: dict[str, Any], timeout: int | None, on_thinking: Any
    ) -> Any:
        client = self._client_for_request(timeout or self.timeout)
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
                        on_thinking({"phase": "thinking", "text": "".join(thinking)})
            return stream.get_final_message()

    def _stream_with_retries(
        self,
        request: dict[str, Any],
        timeout: int | None,
        on_thinking: Any,
        restart: bool = False,
    ) -> Any:
        """Run the stream, re-sending the request after a transient server error.

        The whole request is re-sent: a broken stream cannot be resumed, and the
        partial reasoning it produced is discarded along with it. Every attempt
        after the first -- and the first too when `restart` says an earlier
        stream of the same call was discarded -- is announced to `on_thinking`
        as a `restart`, so a listener keeping the reasoning does not pair the
        discarded attempt's with the reply that is kept.
        """
        for attempt in range(1, self.max_attempts + 1):
            if on_thinking and (restart or attempt > 1):
                on_thinking({"phase": "restart", "text": ""})
            try:
                return self._stream_once(request, timeout, on_thinking)
            except Exception as ex:  # noqa: BLE001 - normalised below
                if "timeout" in str(ex).lower():
                    raise LLMTimeoutError(f"{self.name} timed out: {ex}") from ex
                if attempt < self.max_attempts and is_retryable(ex):
                    delay = RETRY_BACKOFF_SECONDS * attempt
                    logger.warning(
                        "%s: transient error on attempt %d/%d, retrying in %.0fs: %s",
                        self.name,
                        attempt,
                        self.max_attempts,
                        delay,
                        ex,
                    )
                    time.sleep(delay)
                    continue
                raise LLMError(f"{self.name} request failed: {ex}") from ex
        raise LLMError(f"{self.name} request failed")  # pragma: no cover

    @staticmethod
    def _raise_if_refused(message: Any) -> None:
        if getattr(message, "stop_reason", None) == "refusal":
            details = getattr(message, "stop_details", None)
            raise LLMError(
                f"Request refused ({getattr(details, 'category', 'unknown')}): "
                f"{getattr(details, 'explanation', '')}"
            )

    def _raise_if_truncated(
        self,
        message: Any,
        budget: int | None,
        earlier: list[dict[str, Any]],
    ) -> None:
        """Raise when the reply stopped short of finishing.

        `earlier` holds the usage of attempts already discarded for the same
        reason, so the error accounts for everything the call was billed for.
        """
        stop_reason = getattr(message, "stop_reason", None)
        if stop_reason not in TRUNCATION_STOP_REASONS:
            return
        usage = _usage_dict(message)
        attempts = [*earlier, usage]
        output_tokens = usage.get("output_tokens")
        thinking_tokens = _thinking_tokens(usage)
        raise LLMTruncatedError(
            f"{self.name} reply was cut off ({stop_reason}) at "
            f"max_tokens={budget}: {output_tokens} output tokens, "
            f"{thinking_tokens} of them reasoning, over {len(attempts)} "
            f"attempt(s). The partial reply was discarded; raise "
            f"max_tokens_ceiling or lower the effort for this stage.",
            max_tokens=budget,
            output_tokens=output_tokens,
            thinking_tokens=thinking_tokens,
            stop_reason=str(stop_reason),
            partial_text=_text_of(message),
            attempts=attempts,
        )

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
        request = self._apply_request_overrides(request)

        message = self._stream_with_retries(request, timeout, on_thinking)
        self._raise_if_refused(message)

        # Read from the request rather than `self.max_tokens`: an override may
        # have set the budget, and that is the one the reply ran out of.
        budget = request.get("max_tokens")
        truncated: list[dict[str, Any]] = []
        # A budget set through `request_overrides` is the endpoint's limit, not
        # a starting point: those overrides exist for endpoints that reject
        # what the first-party API accepts, and a larger re-send there is a
        # non-retryable 400 in place of the truncation it was meant to cure.
        overridden = self.request_overrides.get("max_tokens") is not None
        if (
            getattr(message, "stop_reason", None) == ESCALATABLE_STOP_REASON
            and isinstance(budget, int)
            and budget < self.max_tokens_ceiling
            and not overridden
        ):
            # Straight to the ceiling in a single re-send rather than a ladder
            # of small steps: every attempt repeats the whole generation, so
            # each rung would cost as much as the reply it failed to finish.
            first = _usage_dict(message)
            truncated.append(first)
            logger.warning(
                "%s: reply stopped at max_tokens=%d (%s output tokens, %s of "
                "them reasoning); re-sending once with max_tokens=%d",
                self.name,
                budget,
                first.get("output_tokens"),
                _thinking_tokens(first),
                self.max_tokens_ceiling,
            )
            first_budget, first_text = budget, _text_of(message)
            budget = request["max_tokens"] = self.max_tokens_ceiling
            try:
                message = self._stream_with_retries(
                    request, timeout, on_thinking, restart=True
                )
            except LLMError as ex:
                # The budget is still the cause. Raised as the re-send's own
                # failure, the first attempt's usage and partial reply vanished
                # from the record, and a caller retrying "a transient error"
                # started over at the budget that was already too small.
                raise LLMTruncatedError(
                    f"{self.name} reply was cut off ({ESCALATABLE_STOP_REASON}) "
                    f"at max_tokens={first_budget}: {first.get('output_tokens')} "
                    f"output tokens, {_thinking_tokens(first)} of them reasoning. "
                    f"The re-send at max_tokens={budget} failed: {ex}",
                    max_tokens=first_budget,
                    output_tokens=first.get("output_tokens"),
                    thinking_tokens=_thinking_tokens(first),
                    stop_reason=ESCALATABLE_STOP_REASON,
                    partial_text=first_text,
                    attempts=truncated,
                ) from ex
            self._raise_if_refused(message)

        self._raise_if_truncated(message, budget, truncated)

        text = _text_of(message)
        if not text:
            raise LLMError(f"{self.name} returned no text content")

        usage_dict = _usage_dict(message)
        if truncated:
            # The discarded attempt was billed like any other. Kept beside the
            # successful attempt's usage so a recording of the call, and anyone
            # totting up tokens from it, sees both.
            usage_dict["truncated_attempts"] = truncated
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


def is_inference_profile(model: str) -> bool:
    """Whether `model` names a Bedrock inference profile rather than a model.

    Two shapes count. An application inference profile is an ARN, created to
    attach cost-allocation tags or pin a provisioned throughput. A
    system-defined cross-region profile is an ordinary model id behind a
    geography prefix -- ``us.anthropic.claude-...``, ``eu.``, ``apac.`` -- and
    routes the call to whichever region in that geography has capacity.
    """
    return model.startswith("arn:") or bool(
        re.match(r"^[a-z]{2,5}\.anthropic\.", model)
    )


class BedrockProvider(_BaseApiProvider):
    """Claude on Amazon Bedrock, by model id or inference profile.

    `model` is passed to Bedrock as given whenever it already identifies a
    target -- an inference profile ARN, a cross-region profile id, or a
    fully-qualified ``anthropic.*`` model id. A bare name like
    ``claude-sonnet-4-5-20250929-v1:0`` gets the ``anthropic.`` prefix Bedrock
    expects.

    Two clients reach Bedrock and they are not interchangeable here. The
    classic ``AnthropicBedrock`` client calls ``bedrock-runtime`` and puts the
    identifier in the URL path, which is what makes inference profiles usable;
    ``AnthropicBedrockMantle`` calls the newer Mantle endpoint and sends the
    model in the body. `client="auto"` picks runtime for a profile and Mantle
    otherwise.
    """

    name = "bedrock"

    def __init__(
        self,
        aws_region: str = "us-east-1",
        aws_profile: str | None = None,
        client: str = "auto",
        **kwargs: Any,
    ) -> None:
        self.aws_region = aws_region
        self.aws_profile = aws_profile
        self.client_kind = client
        super().__init__(**kwargs)

    def _resolve_client_kind(self) -> str:
        if self.client_kind != "auto":
            return self.client_kind
        return "runtime" if is_inference_profile(self.model) else "mantle"

    @contextlib.contextmanager
    def _suppressed_bearer_token(self) -> Any:
        """Hide AWS_BEARER_TOKEN_BEDROCK from the SDK while a profile is chosen.

        Only when a profile is set; otherwise a deployment that genuinely wants
        bearer-token auth is left untouched. The var is restored afterwards so
        the process environment is unchanged.
        """
        token = os.environ.get("AWS_BEARER_TOKEN_BEDROCK")
        if not (self.aws_profile and token):
            yield
            return
        del os.environ["AWS_BEARER_TOKEN_BEDROCK"]
        logger.info(
            "bedrock: AWS_BEARER_TOKEN_BEDROCK ignored because aws_profile=%r "
            "is set; the profile is used to sign requests.",
            self.aws_profile,
        )
        try:
            yield
        finally:
            os.environ["AWS_BEARER_TOKEN_BEDROCK"] = token

    def _client_for_request(self, timeout: int) -> Any:
        # Not ``with_options``: the SDK's copy() does not carry ``aws_profile``
        # forward, so a copied client loses the profile and cannot resolve
        # credentials. Rebuild instead, which reapplies the profile and lets the
        # timeout be set directly.
        return self._build_client(timeout=timeout)

    def _build_client(self, timeout: int | None = None) -> Any:
        kind = self._resolve_client_kind()
        # Credentials resolve through the standard AWS chain (env vars, the
        # named profile, the instance/task role), so nothing is held in config.
        kwargs: dict[str, Any] = {"aws_region": self.aws_region}
        if self.aws_profile:
            kwargs["aws_profile"] = self.aws_profile
        if timeout is not None:
            kwargs["timeout"] = timeout

        # A configured profile is an explicit choice of identity, so it must win
        # over an ambient AWS_BEARER_TOKEN_BEDROCK. The SDK does the opposite: if
        # that env var is set it silently enters bearer mode and never signs, so
        # every call then fails as the bearer principal regardless of the
        # profile -- and a Bedrock API key additionally needs
        # bedrock:CallWithBearerToken, which an invoke-only role does not carry.
        # The two are also mutually exclusive at construction (the SDK raises on
        # profile + api_key), so the token is cleared for the duration of the
        # build only, then restored.
        with self._suppressed_bearer_token():
            if kind == "runtime":
                try:
                    from anthropic import AnthropicBedrock
                except ImportError as ex:  # pragma: no cover
                    raise LLMError(
                        "AnthropicBedrock is unavailable. Install the anthropic "
                        "SDK with Bedrock support "
                        "(`pip install 'anthropic[bedrock]'`)."
                    ) from ex
                return AnthropicBedrock(**kwargs)

            if kind == "mantle":
                try:
                    from anthropic import AnthropicBedrockMantle
                except ImportError as ex:  # pragma: no cover
                    raise LLMError(
                        "AnthropicBedrockMantle is unavailable. Install the "
                        "anthropic SDK with Bedrock support."
                    ) from ex
                return AnthropicBedrockMantle(**kwargs)

        raise LLMError(
            f"Unknown Bedrock client {self.client_kind!r}. "
            f"Use 'auto', 'runtime' or 'mantle'."
        )

    def _build_request_model(self) -> str:
        if is_inference_profile(self.model) or self.model.startswith("anthropic."):
            return self.model
        # A bare model name; Bedrock model ids carry an "anthropic." prefix.
        return f"anthropic.{self.model}"

    def complete(self, *args: Any, **kwargs: Any) -> LLMResponse:
        original = self.model
        self.model = self._build_request_model()
        # The suppression has to span the request, not just the client build:
        # `complete` copies the client via `with_options(timeout=...)`, and the
        # SDK's copy() does not carry `aws_profile` forward, so the copy re-reads
        # AWS_BEARER_TOKEN_BEDROCK from the environment and silently signs the
        # request as a bearer token again. Keeping the var hidden for the whole
        # call makes the copied client fall back to the profile as intended.
        try:
            with self._suppressed_bearer_token():
                return super().complete(*args, **kwargs)
        finally:
            self.model = original
