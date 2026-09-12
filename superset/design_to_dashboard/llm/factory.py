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
    "max_tokens": 32000,
    "effort": "high",
    "aws_region": "us-east-1",
    # stage -> model. Empty means every stage uses `model`.
    "stage_models": {},
}

# Providers that shell out to a coding CLI as the web server's OS user, using
# the host developer's credentials. Local development only.
CLI_PROVIDERS = {"kiro_cli", "claude_cli"}


def _resolve_stage(conf: dict[str, Any], stage: str | None) -> tuple[str, str]:
    """The model and effort this stage runs at.

    A `stage_models` entry is either a model name or a mapping that may also
    carry `effort`; whatever it omits falls back to the top-level setting.
    """
    model = conf["model"]
    effort = conf.get("effort", "medium")
    override = (conf.get("stage_models") or {}).get(stage) if stage else None
    if isinstance(override, str):
        model = override
    elif isinstance(override, dict):
        model = override.get("model", model)
        effort = override.get("effort", effort)
    if stage and (model, effort) != (conf["model"], conf.get("effort", "medium")):
        logger.info("stage %s uses %s at effort=%s", stage, model, effort)
    return model, effort


def get_llm_provider(stage: str | None = None) -> LLMProvider:
    """Build the provider named by `DESIGN_TO_DASHBOARD_LLM["provider"]`.

    `stage` selects the model and how hard it thinks: the stages differ enough
    in what they ask for that one setting for all of them is either too weak
    where judgment is needed or wasteful where the work is a schema-driven
    transformation. An entry in `stage_models` is either a model name or a
    ``{"model": ..., "effort": ...}`` mapping; anything it leaves out falls
    back to the top-level `model` and `effort`.
    """
    conf = {**DEFAULTS, **(current_app.config.get("DESIGN_TO_DASHBOARD_LLM") or {})}
    provider = conf["provider"]
    model, effort = _resolve_stage(conf, stage)

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
            max_turns=conf["max_turns"],
        )

    if provider == "claude_agent_sdk":
        from .agent_sdk import ClaudeAgentSdkProvider

        return ClaudeAgentSdkProvider(
            model=model,
            timeout=conf["timeout"],
            max_turns=conf["max_turns"],
            display=conf.get("thinking_display", "summarized"),
            effort=effort,
        )

    if provider in {"anthropic_api", "api"}:
        from .api_provider import AnthropicApiProvider

        return AnthropicApiProvider(
            model=model,
            timeout=conf["timeout"],
            max_tokens=conf.get("max_tokens", 32000),
            effort=effort,
        )

    if provider == "bedrock":
        from .api_provider import BedrockProvider

        return BedrockProvider(
            aws_region=conf.get("aws_region", "us-east-1"),
            model=model,
            timeout=conf["timeout"],
            max_tokens=conf.get("max_tokens", 32000),
            effort=effort,
        )

    raise LLMError(
        f"Unknown Design-to-Dashboard LLM provider: {provider!r}. Supported: "
        f"'kiro_cli', 'claude_cli', 'claude_agent_sdk', 'anthropic_api', 'bedrock'."
    )
