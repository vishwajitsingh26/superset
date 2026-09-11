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
"""Local-development LLM provider that shells out to the Kiro CLI.

WHY THIS EXISTS
---------------
Like ``claude_cli``, it lets the pipeline run end to end on a workstation with
no API credentials: it authenticates as whoever is logged into the ``kiro-cli``
on the host. Unlike ``claude_cli``, the reasoning it streams is readable rather
than redacted, so stage thinking reaches the UI.

HOW IT DIFFERS FROM THE CLAUDE CLI
----------------------------------
The two CLIs are not flag-compatible, and three differences shape this file:

- **There is no ``--system-prompt-file``.** A system prompt only becomes
  authoritative when it arrives as an *agent* definition, so each call writes a
  throwaway agent config into a private workspace and selects it by name.
- **The v3 engine is required.** On v2, ``--model`` is rejected outright
  ("Method not found") and the agent's prompt degrades into ordinary user text
  the model may decline to follow, which would silently unpin both the model
  and the stage contract.
- **Usage is metered in credits, not dollars.** ``cost_usd`` is therefore left
  unset rather than filled with a number in the wrong unit, matching how the
  API providers report per-account billing. Credits land in ``usage``.

NOT FOR PRODUCTION
------------------
- It spawns a subprocess per call, as the web server's OS user.
- It uses the host developer's Kiro credentials for every request, so per-user
  attribution, quotas and audit are impossible.
- Latency and concurrency are bounded by process spawning, and the v3 engine
  starts a Node agent server per call.
- Reading design images requires trusting every tool (see ``_argv``), which is
  broader than the read-only, directory-scoped grant the Claude CLI accepts.

It therefore refuses to start unless the deployment is explicitly in debug mode
or has opted in via ``DESIGN_TO_DASHBOARD_LLM["allow_cli_provider"]``. Swap
``provider`` to an API provider before shipping.
"""

from __future__ import annotations

import logging
import os
import pathlib
import shutil
import subprocess  # noqa: S404
import tempfile
import time
from typing import Any

from superset.utils import json

from .base import LLMError, LLMResponse, LLMTimeoutError

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 300

# The engine that honours --model and treats an agent's prompt as a system
# prompt. Pinned rather than configurable because the pipeline's correctness
# depends on both.
ENGINE = "v3"

# Name of the throwaway agent written per call. Also the config's filename.
AGENT_NAME = "superset_design_to_dashboard"

# Where the CLI looks for workspace agent definitions, relative to its cwd.
AGENT_DIR = pathlib.Path(".kiro") / "agents"


class KiroCliProvider:
    """Runs ``kiro-cli chat`` non-interactively and returns the completion text.

    The user prompt goes in on stdin and the system prompt travels in an agent
    config on disk, so neither is exposed on the process command line (where it
    would be visible to ``ps`` and subject to ARG_MAX limits -- stage prompts
    are large).
    """

    name = "kiro_cli"

    def __init__(
        self,
        model: str = "claude-opus-5",
        timeout: int = DEFAULT_TIMEOUT,
        effort: str = "high",
        binary: str = "kiro-cli",
    ) -> None:
        self.model = model
        self.timeout = timeout
        self.effort = effort
        resolved = shutil.which(binary)
        if not resolved:
            raise LLMError(
                f"Kiro CLI '{binary}' not found on PATH. Install the Kiro CLI or "
                f"set DESIGN_TO_DASHBOARD_LLM['provider'] to an API provider."
            )
        self.binary = resolved

    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        image_paths: list[str] | None = None,
        timeout: int | None = None,
        on_thinking: Any = None,
    ) -> LLMResponse:
        image_paths = image_paths or []
        for path in image_paths:
            if not os.path.isabs(path):
                raise LLMError(f"Image path must be absolute: {path}")
            if not os.path.exists(path):
                raise LLMError(f"Image not found: {path}")

        prompt = self._build_prompt(user_prompt, image_paths)

        # A private, empty workspace per call. It carries the agent definition
        # and nothing else: the model is given no incidental access to the
        # Superset checkout, matching what the Claude CLI provider allows.
        workspace = pathlib.Path(tempfile.mkdtemp(prefix="superset-d2d-"))
        try:
            self._write_agent(workspace, system_prompt, bool(image_paths))
            stdout, stderr, returncode = self._run(
                self._argv(bool(image_paths)),
                prompt,
                workspace,
                timeout or self.timeout,
                on_thinking,
            )
        finally:
            shutil.rmtree(workspace, ignore_errors=True)

        return self._parse(stdout, stderr, returncode)

    def _write_agent(
        self, workspace: pathlib.Path, system_prompt: str, wants_images: bool
    ) -> None:
        """Write the agent definition that carries the system prompt.

        A missing or misnamed agent is not an error to the CLI -- it falls back
        to its default agent and exits zero, which would run the stage with no
        system prompt at all and produce confidently wrong output. So the file
        is verified to exist before the call is made.
        """
        agent_dir = workspace / AGENT_DIR
        agent_dir.mkdir(parents=True, exist_ok=True)
        config = {
            "name": AGENT_NAME,
            "description": "Superset Design-to-Dashboard pipeline stage",
            "prompt": system_prompt,
            "mcpServers": {},
            # Reading design images is the only tool the pipeline needs. Stages
            # without images get no tools at all.
            "tools": ["*"] if wants_images else [],
            "toolAliases": {},
            "allowedTools": ["*"] if wants_images else [],
            "resources": [],
            "toolsSettings": {},
            # The pipeline supplies its own context; never inherit the host's
            # MCP configuration into a stage call.
            "includeMcpJson": False,
            "model": None,
            "permissions": {"rules": []},
        }
        destination = agent_dir / f"{AGENT_NAME}.json"
        destination.write_text(json.dumps(config, indent=2), encoding="utf-8")
        if not destination.is_file():
            raise LLMError(f"Could not write the Kiro agent config to {destination}")

    def _argv(self, wants_images: bool) -> list[str]:
        argv = [
            self.binary,
            "chat",
            "--no-interactive",
            "--output-format",
            "stream-json",
            "--agent-engine",
            ENGINE,
            "--agent",
            AGENT_NAME,
            "--model",
            self.model,
            "--effort",
            self.effort,
        ]
        if wants_images:
            # The model reads design images off disk with its file-reading tool.
            # Kiro's v3 engine offers no way to trust that tool alone: every
            # narrower form (--trust-tools=read, and allowlisting in the agent
            # config) leaves the call awaiting a confirmation that can never
            # arrive without a terminal, and the read is refused. Trusting all
            # tools is the only grant that works, which is a real widening --
            # it is why this provider is gated to local development.
            argv.append("--trust-all-tools")
        return argv

    def _run(  # noqa: C901
        self,
        argv: list[str],
        prompt: str,
        workspace: pathlib.Path,
        timeout: int,
        on_thinking: Any,
    ) -> tuple[str, str, int]:
        """Run the CLI, forwarding reasoning as it arrives.

        Each stdout line is one self-describing JSON envelope; the CLI's own
        logging goes to stderr. Returns the collected stdout, stderr and exit
        code so the caller's error handling sees everything.

        stderr is captured to a file rather than a pipe: the v3 engine is chatty
        enough to fill a pipe buffer, and nothing drains it until stdout closes,
        which would deadlock the call.
        """
        stderr_file = workspace / "stderr.log"
        collected: list[str] = []
        thinking: list[str] = []
        answer_chars = 0
        deadline = time.monotonic() + timeout

        with stderr_file.open("w", encoding="utf-8") as stderr_sink:
            process = subprocess.Popen(  # noqa: S603
                argv,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=stderr_sink,
                text=True,
                bufsize=1,
                shell=False,
                cwd=str(workspace),
            )
            assert process.stdin is not None
            assert process.stdout is not None

            try:
                process.stdin.write(prompt)
                process.stdin.close()

                for line in process.stdout:
                    if time.monotonic() > deadline:
                        process.kill()
                        raise LLMTimeoutError(f"Kiro CLI timed out after {timeout}s")
                    line = line.strip()
                    if not line:
                        continue
                    collected.append(line)
                    try:
                        envelope = json.loads(line)
                    except ValueError:
                        continue
                    if not on_thinking:
                        continue

                    data = envelope.get("data")
                    update = (
                        (data.get("update") or {}) if isinstance(data, dict) else {}
                    )
                    if not isinstance(update, dict):
                        continue
                    kind = update.get("sessionUpdate")

                    # Unlike the Claude CLI, which redacts reasoning and can
                    # only report its volume, Kiro streams the text itself. The
                    # accumulated string is sent each time because the consumer
                    # replaces its buffer rather than appending.
                    if kind == "agent_thought_chunk":
                        if text := self._content_text(update.get("content")):
                            thinking.append(text)
                            on_thinking(
                                {"phase": "thinking", "text": "".join(thinking)}
                            )
                    elif kind == "agent_message_chunk":
                        # The answer itself is raw JSON; report only its growth
                        # so the UI can show that output is being produced.
                        answer_chars += len(self._content_text(update.get("content")))
                        on_thinking(
                            {
                                "phase": "writing",
                                "chars": answer_chars,
                                "text": "".join(thinking),
                            }
                        )
            finally:
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()

        stderr = stderr_file.read_text(encoding="utf-8", errors="replace")
        return "\n".join(collected), stderr, process.returncode or 0

    @staticmethod
    def _content_text(content: Any) -> str:
        """Text out of an ACP content field, which is a block or a list of them.

        Message and thought chunks carry a single block, while tool calls carry
        a list, so a shape-blind reader would crash on the ones it did not
        expect.
        """
        if isinstance(content, dict):
            return content.get("text") or ""
        if isinstance(content, list):
            return "".join(
                block.get("text") or "" for block in content if isinstance(block, dict)
            )
        return ""

    @staticmethod
    def _build_prompt(user_prompt: str, image_paths: list[str]) -> str:
        if not image_paths:
            return user_prompt
        listed = "\n".join(f"- {path}" for path in image_paths)
        return (
            f"{user_prompt}\n\n"
            f"Read the following design image(s) before answering:\n{listed}"
        )

    def _parse(  # noqa: C901
        self, stdout: str, stderr: str, returncode: int
    ) -> LLMResponse:
        """Turn the JSON Lines transcript into a response.

        The terminal ``runFinished`` envelope carries the answer. A ``runError``
        can arrive instead, and the exit code alone is not a reliable signal, so
        both are inspected.
        """
        final: dict[str, Any] = {}
        error: dict[str, Any] = {}
        session_id: str | None = None
        credits: float | None = None
        elapsed_ms: int | None = None
        chunks: list[str] = []

        for line in stdout.splitlines():
            try:
                envelope = json.loads(line)
            except ValueError:
                continue
            kind = envelope.get("type")
            data = envelope.get("data")
            if not isinstance(data, dict):
                continue
            if data.get("sessionId"):
                session_id = data["sessionId"]

            if kind == "runFinished":
                final = data
            elif kind == "runError":
                error = data
                continue

            update = data.get("update") or {}
            if not isinstance(update, dict):
                continue
            if update.get("sessionUpdate") == "agent_message_chunk":
                chunks.append(self._content_text(update.get("content")))

            meta = (update.get("_meta") or {}).get("kiro") or {}
            if meta.get("kind") == "turn_completion":
                elapsed_ms = meta.get("elapsedTime")
                for summary in meta.get("promptTurnSummaries") or []:
                    if summary.get("unit") == "credit":
                        credits = summary.get("usage")
            # The v2 engine reports metering on a plain envelope. Read it too so
            # a transcript from either engine yields usage.
            for metering in data.get("meteringUsage") or []:
                if metering.get("unit") == "credit":
                    credits = metering.get("value")

        if error:
            raise LLMError(
                f"Kiro CLI failed at stage {error.get('stage') or 'unknown'}: "
                f"{error.get('message') or '<no message>'}"
            )

        if not final:
            detail = stderr.strip() or stdout.strip()
            raise LLMError(
                f"Kiro CLI exited {returncode} without completing a run: "
                f"{detail[-800:] or '<no output on stdout or stderr>'}"
            )

        if final.get("status") != "success":
            raise LLMError(
                f"Kiro CLI run ended with status {final.get('status')!r} "
                f"(stop reason {final.get('stopReason')!r}): "
                f"{stderr.strip()[-500:] or '<no detail on stderr>'}"
            )

        text = final.get("finalText")
        if not isinstance(text, str) or not text:
            raise LLMError(f"Kiro CLI returned no final text: {final!r}")

        # finalText is a convenience field the CLI may cut short. The streamed
        # chunks are the complete answer, and stages parse JSON out of this, so
        # a truncated value would fail schema validation further down.
        if final.get("finalTextTruncated") and (joined := "".join(chunks)):
            logger.info("Kiro CLI truncated finalText; using the streamed chunks")
            text = joined

        usage: dict[str, Any] = {}
        if credits is not None:
            # Deliberately not reported as cost_usd: Kiro meters in credits, and
            # the conversion to currency is an account-level concern.
            usage["credits"] = credits
        if elapsed_ms is not None:
            usage["elapsed_ms"] = elapsed_ms

        return LLMResponse(
            text=text,
            cost_usd=None,  # metered in credits; see usage["credits"]
            usage=usage,
            session_id=session_id,
            provider=self.name,
        )
