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
"""Resolves the configured LLM provider."""

from __future__ import annotations

import logging
from typing import Any

from flask import current_app

from .base import LLMError, LLMProvider

logger = logging.getLogger(__name__)

DEFAULTS = {
    "provider": "kiro_cli",
    "model": "claude-opus-5",
    "timeout": 300,
    "max_turns": 6,
    "allow_cli_provider": False,
    # API providers only: the output budget per call, reasoning included, and
    # the budget a reply cut off at it is re-sent with (once). A `stage_models`
    # mapping may set either for one stage. Some stages start above
    # `max_tokens` (see STAGE_MIN_MAX_TOKENS), never above the ceiling: a model
    # whose output limit is below 64000 needs `max_tokens_ceiling` set to it.
    "max_tokens": 32000,
    "max_tokens_ceiling": 64000,
    "effort": "high",
    "aws_region": "us-east-1",
    "aws_profile": None,
    # "auto" | "runtime" | "mantle" -- see BedrockProvider.
    "bedrock_client": "auto",
    # Per-request body edits for endpoints that accept a narrower schema than
    # the first-party API. None as a value drops the key.
    "request_overrides": {},
    # stage -> model. Empty means every stage uses `model`.
    "stage_models": {},
    # API providers only: attempts per call when the server fails mid-request
    # (e.g. Bedrock's internalServerException). 1 disables retrying.
    "max_attempts": 3,
}

# Providers that shell out to a coding CLI as the web server's OS user, using
# the host developer's credentials. Local development only.
CLI_PROVIDERS = {"kiro_cli", "claude_cli"}

# The smallest output budget a stage starts with, whatever top-level
# `max_tokens` says. Stage F writes a whole plugin -- a dozen files -- in one
# reply, and its reasoning alone has measured over 26k tokens: at 32k the reply
# was cut off mid-JSON and the plugin's sections were dropped. Raised again to
# 80000 (2026-09-14): output at 64k has come close enough on real runs
# (~57k output tokens seen) that a bigger plugin would still be cut off, and a
# live probe against this deployment's Bedrock profile confirmed 80000 is
# accepted with no beta header needed. A floor rather than a value, so a
# deployment that sets a larger budget keeps it; capped at the ceiling, so a
# deployment on a model with a smaller output limit is never sent more than it
# declared -- which means the ceiling has to move too (see
# `stage_models["F"]["max_tokens_ceiling"]` in the deployment config) or this
# floor is clipped straight back down to it.
STAGE_MIN_MAX_TOKENS: dict[str, int] = {"F": 80000}

# The floor an agent-loop stage's turn budget starts at, whatever top-level
# `max_turns` says -- mirrors STAGE_MIN_MAX_TOKENS above, for the same reason.
# Every stage listed here is given the whole design image (A and E) or a
# crop of it (F) and only the `Read` tool, spent opening it before the stage
# can reason and produce its final answer -- so every one of them is exposed
# to the same failure, not just F. The top-level default (6) predates all of
# them: on run dc2e58c1 (2026-09-14), 8 of 11 stage-F plugin builds burned
# every turn on image reads and reasoning and never reached a final answer;
# on run 0f656223 (2026-09-14), stage A did the same on its first call and
# ended the run before it built anything, because A had no retry fallback
# for this failure at all until this floor and `runner._retry`'s
# `on_max_turns` were extended to cover it too. A deployment that wants a
# stage's budget lower says so for that stage, rather than inheriting a
# value chosen before any of them existed.
STAGE_MIN_TURNS: dict[str, int] = {"A": 16, "E": 16, "F": 16}

# The effort a stage runs at unless its own `stage_models` entry names one. It
# outranks the top-level `effort`: stage F writes a dozen files of TypeScript
# that must compile against APIs it cannot see, and at medium effort three of
# five plugins in one run failed the compiler through both repair rounds. Its
# goal is pixel-perfect fidelity to a design a human cannot tell apart from
# what gets built, which is worth the extra reasoning `xhigh` buys over `high`
# on top of that. A deployment that wants F cheaper says so for F, rather than
# inheriting a setting chosen for the stages that only transform a schema.
STAGE_DEFAULT_EFFORT: dict[str, str] = {"F": "xhigh"}


def _resolve_stage(conf: dict[str, Any], stage: str | None) -> tuple[str, str]:
    """The model and effort this stage runs at.

    A `stage_models` entry is either a model name or a mapping that may also
    carry `effort`. Whatever it omits falls back to the stage's default in
    `STAGE_DEFAULT_EFFORT`, then to the top-level setting.
    """
    model = conf["model"]
    effort = conf.get("effort", "medium")
    if stage in STAGE_DEFAULT_EFFORT:
        effort = STAGE_DEFAULT_EFFORT[stage]
    override = (conf.get("stage_models") or {}).get(stage) if stage else None
    if isinstance(override, str):
        model = override
    elif isinstance(override, dict):
        model = override.get("model", model)
        effort = override.get("effort", effort)
    if stage and (model, effort) != (conf["model"], conf.get("effort", "medium")):
        logger.info("stage %s uses %s at effort=%s", stage, model, effort)
    return model, effort


def _resolve_budget(conf: dict[str, Any], stage: str | None) -> tuple[int, int]:
    """The output budget and escalation ceiling this stage runs with.

    The stage's floor from `STAGE_MIN_MAX_TOKENS` lifts the top-level budget,
    up to the ceiling; an explicit `max_tokens` in the stage's `stage_models`
    mapping replaces it, since a value set for one stage is a deliberate
    choice, lower or not.
    """
    max_tokens = int(conf.get("max_tokens") or 32000)
    ceiling = int(conf.get("max_tokens_ceiling") or 64000)
    override = (conf.get("stage_models") or {}).get(stage) if stage else None
    if isinstance(override, dict):
        ceiling = int(override.get("max_tokens_ceiling", ceiling))
    if stage and (floor := min(STAGE_MIN_MAX_TOKENS.get(stage, 0), ceiling)) > (
        max_tokens
    ):
        logger.info(
            "stage %s starts at max_tokens=%d, its floor; set "
            "stage_models[%r]['max_tokens'] or max_tokens_ceiling to lower it",
            stage,
            floor,
            stage,
        )
        max_tokens = floor
    if isinstance(override, dict):
        max_tokens = int(override.get("max_tokens", max_tokens))
    return max_tokens, ceiling


def _resolve_turns(conf: dict[str, Any], stage: str | None) -> int | None:
    """The agent-loop turn budget this stage runs with, or `None` for no cap.

    Same shape as `_resolve_budget`: the stage's floor from `STAGE_MIN_TURNS`
    lifts the top-level `max_turns`; an explicit `max_turns` in the stage's
    own `stage_models` mapping replaces it outright, since a value set for one
    stage is a deliberate choice, lower or not.

    `max_turns: None` (top-level or per-stage) means observation mode: no
    limit is passed to the provider at all, so a call runs until it answers,
    times out, or the CLI itself fails -- never on a turn count. A floor makes
    no sense against a budget that isn't there, so it is skipped entirely
    once either level says `None`. Turn-by-turn telemetry (`LLMResponse.
    tool_calls`, `usage["num_turns"]`) is what this mode is for: deciding a
    real number, and telling a call that needed more turns apart from one
    wasting them, from evidence instead of another guess.
    """
    override = (conf.get("stage_models") or {}).get(stage) if stage else None
    if isinstance(override, dict) and "max_turns" in override:
        stage_value = override["max_turns"]
        return None if stage_value is None else int(stage_value)

    raw = conf.get("max_turns", 6)
    if raw is None:
        return None

    max_turns = int(raw or 6)
    if stage and (floor := STAGE_MIN_TURNS.get(stage, 0)) > max_turns:
        logger.info(
            "stage %s starts at max_turns=%d, its floor; set "
            "stage_models[%r]['max_turns'] to lower it",
            stage,
            floor,
            stage,
        )
        max_turns = floor
    return max_turns


def get_llm_provider(
    stage: str | None = None,
    effort: str | None = None,
    max_turns: int | None = None,
) -> LLMProvider:
    """Build the provider named by `DESIGN_TO_DASHBOARD_LLM["provider"]`.

    `stage` selects the model, how hard it thinks and, for API providers, its
    output budget: the stages differ enough in what they ask for that one
    setting for all of them is either too weak where judgment is needed or
    wasteful where the work is a schema-driven transformation. An entry in
    `stage_models` is either a model name or a mapping of ``model``,
    ``effort``, ``max_tokens``, ``max_tokens_ceiling`` and ``max_turns``;
    anything it leaves out falls back to the top-level settings.

    `effort` overrides whatever the configuration resolves to, for a caller
    re-running a stage more cheaply -- e.g. after a reply was cut off at the
    largest output budget allowed. `max_turns` does the same for an agent-loop
    provider's turn budget, for a caller re-running a stage after it exhausted
    that budget without answering.
    """
    conf = {**DEFAULTS, **(current_app.config.get("DESIGN_TO_DASHBOARD_LLM") or {})}
    provider = conf["provider"]
    model, resolved_effort = _resolve_stage(conf, stage)
    effort = effort or resolved_effort
    max_tokens, max_tokens_ceiling = _resolve_budget(conf, stage)
    max_turns = max_turns if max_turns is not None else _resolve_turns(conf, stage)

    if provider in CLI_PROVIDERS and not (
        current_app.debug or conf["allow_cli_provider"]
    ):
        raise LLMError(
            f"The {provider} provider is for local development only. Enable "
            f"it explicitly with DESIGN_TO_DASHBOARD_LLM"
            f"['allow_cli_provider'] = True, or configure an API provider."
        )

    if provider == "kiro_cli":
        # Imported lazily so a production deployment never loads the dev path.
        from .kiro_cli import KiroCliProvider

        logger.warning(
            "Design-to-Dashboard is using the kiro_cli provider. This shells "
            "out to the Kiro CLI as the server's OS user and is not suitable "
            "for production."
        )
        return KiroCliProvider(
            model=model,
            timeout=conf["timeout"],
            effort=effort,
        )

    if provider == "claude_cli":
        # Imported lazily so a production deployment never loads the dev path.
        from .claude_cli import ClaudeCliProvider

        logger.warning(
            "Design-to-Dashboard is using the claude_cli provider. This shells "
            "out to the Claude Code CLI as the server's OS user and is not "
            "suitable for production."
        )
        return ClaudeCliProvider(
            model=model,
            timeout=conf["timeout"],
            max_turns=max_turns,
        )

    if provider == "claude_agent_sdk":
        from .agent_sdk import ClaudeAgentSdkProvider

        return ClaudeAgentSdkProvider(
            model=model,
            timeout=conf["timeout"],
            max_turns=max_turns,
            display=conf.get("thinking_display", "summarized"),
            effort=effort,
        )

    if provider in {"anthropic_api", "api"}:
        from .api_provider import AnthropicApiProvider

        return AnthropicApiProvider(
            model=model,
            timeout=conf["timeout"],
            max_tokens=max_tokens,
            max_tokens_ceiling=max_tokens_ceiling,
            effort=effort,
            request_overrides=conf.get("request_overrides"),
            max_attempts=conf.get("max_attempts", 3),
        )

    if provider == "bedrock":
        from .api_provider import BedrockProvider

        return BedrockProvider(
            aws_region=conf.get("aws_region", "us-east-1"),
            aws_profile=conf.get("aws_profile"),
            client=conf.get("bedrock_client", "auto"),
            model=model,
            timeout=conf["timeout"],
            max_tokens=max_tokens,
            max_tokens_ceiling=max_tokens_ceiling,
            effort=effort,
            request_overrides=conf.get("request_overrides"),
            max_attempts=conf.get("max_attempts", 3),
        )

    raise LLMError(
        f"Unknown Design-to-Dashboard LLM provider: {provider!r}. Supported: "
        f"'kiro_cli', 'claude_cli', 'claude_agent_sdk', 'anthropic_api', 'bedrock'."
    )
