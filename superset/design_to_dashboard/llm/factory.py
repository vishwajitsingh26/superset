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

from flask import current_app

from .base import LLMError, LLMProvider

logger = logging.getLogger(__name__)

DEFAULTS = {
    "provider": "claude_cli",
    "model": "claude-opus-5",
    "timeout": 300,
    "max_turns": 6,
    "allow_cli_provider": False,
    "max_tokens": 32000,
    "effort": "high",
    "aws_region": "us-east-1",
}


def get_llm_provider() -> LLMProvider:
    """Build the provider named by `DESIGN_TO_DASHBOARD_LLM["provider"]`."""
    conf = {**DEFAULTS, **(current_app.config.get("DESIGN_TO_DASHBOARD_LLM") or {})}
    provider = conf["provider"]

    if provider == "claude_cli":
        if not (current_app.debug or conf["allow_cli_provider"]):
            raise LLMError(
                "The claude_cli provider is for local development only. Enable "
                "it explicitly with DESIGN_TO_DASHBOARD_LLM"
                "['allow_cli_provider'] = True, or configure an API provider."
            )
        # Imported lazily so a production deployment never loads the dev path.
        from .claude_cli import ClaudeCliProvider

        logger.warning(
            "Design-to-Dashboard is using the claude_cli provider. This shells "
            "out to the Claude Code CLI as the server's OS user and is not "
            "suitable for production."
        )
        return ClaudeCliProvider(
            model=conf["model"],
            timeout=conf["timeout"],
            max_turns=conf["max_turns"],
        )

    if provider == "claude_agent_sdk":
        from .agent_sdk import ClaudeAgentSdkProvider

        return ClaudeAgentSdkProvider(
            model=conf["model"],
            timeout=conf["timeout"],
            max_turns=conf["max_turns"],
            display=conf.get("thinking_display", "summarized"),
        )

    if provider in {"anthropic_api", "api"}:
        from .api_provider import AnthropicApiProvider

        return AnthropicApiProvider(
            model=conf["model"],
            timeout=conf["timeout"],
            max_tokens=conf.get("max_tokens", 32000),
            effort=conf.get("effort", "high"),
        )

    if provider == "bedrock":
        from .api_provider import BedrockProvider

        return BedrockProvider(
            aws_region=conf.get("aws_region", "us-east-1"),
            model=conf["model"],
            timeout=conf["timeout"],
            max_tokens=conf.get("max_tokens", 32000),
            effort=conf.get("effort", "high"),
        )

    raise LLMError(
        f"Unknown Design-to-Dashboard LLM provider: {provider!r}. "
        f"Supported: 'claude_cli', 'claude_agent_sdk', 'anthropic_api', 'bedrock'."
    )
