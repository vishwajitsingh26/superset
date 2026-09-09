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
"""Local-development LLM provider that shells out to the Claude Code CLI.

WHY THIS EXISTS
---------------
It lets the pipeline run end to end on a workstation before any API
credentials are provisioned. It authenticates as whoever is logged into the
`claude` CLI on the host.

NOT FOR PRODUCTION
------------------
- It spawns a subprocess per call, as the web server's OS user.
- It uses the host developer's Claude credentials for every request, so
  per-user attribution, quotas and audit are impossible.
- Latency and concurrency are bounded by process spawning.

It therefore refuses to start unless the deployment is explicitly in debug
mode or has opted in via `DESIGN_TO_DASHBOARD_LLM["allow_cli_provider"]`.
Swap `provider` to a real API provider before shipping.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess  # noqa: S404
import tempfile
import time
from typing import Any

from .base import LLMError, LLMResponse, LLMTimeout

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 300


class ClaudeCliProvider:
    """Runs `claude -p` and returns the completion text.

    The prompt is written to stdin and the system prompt to a temp file, so
    neither is exposed on the process command line (where it would be visible
    to `ps` and subject to ARG_MAX limits — stage prompts are large).
    """

    name = "claude_cli"

    def __init__(
        self,
        model: str = "claude-opus-5",
        timeout: int = DEFAULT_TIMEOUT,
        max_turns: int = 6,
        binary: str = "claude",
    ) -> None:
        self.model = model
        self.timeout = timeout
        self.max_turns = max_turns
        self.binary = shutil.which(binary) or binary
        if not shutil.which(binary):
            raise LLMError(
                f"Claude CLI '{binary}' not found on PATH. Install Claude Code "
                f"or set DESIGN_TO_DASHBOARD_LLM['provider'] to an API provider."
            )

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

        # Written to a temp file rather than passed as an argv value: stage
        # prompts routinely exceed comfortable command-line lengths.
        with tempfile.NamedTemporaryFile(
            "w", suffix=".md", delete=False, encoding="utf-8"
        ) as handle:
            handle.write(system_prompt)
            system_prompt_path = handle.name

        # Turn budget matters twice over: each image costs a Read tool-use turn,
        # and even a text-only call can end on `stop_reason: tool_use` if the
        # model reaches for a tool. A budget of 1 turns that into a hard failure
        # with an opaque exit 1, so the floor is never 1.
        max_turns = max(self.max_turns, 6)
        if image_paths:
            max_turns = max(max_turns, len(image_paths) + 4)

        # Streaming mode is used only when someone is listening for reasoning:
        # it costs an extra parse pass and a reader thread, and the plain json
        # form is simpler when the output is all that matters.
        streaming = on_thinking is not None

        argv = [
            self.binary,
            "-p",
            "--output-format",
            "stream-json" if streaming else "json",
            "--model",
            self.model,
            "--max-turns",
            str(max_turns),
            "--system-prompt-file",
            system_prompt_path,
        ]

        if image_paths:
            # The model reads images off disk, so it needs the Read tool and
            # access to the directories holding the uploads — nothing more.
            argv += ["--allowed-tools", "Read"]
            for directory in sorted({os.path.dirname(p) for p in image_paths}):
                argv += ["--add-dir", directory]
        else:
            argv += ["--allowed-tools", ""]

        if streaming:
            argv += ["--include-partial-messages", "--verbose"]

        try:
            if streaming:
                completed = self._run_streaming(
                    argv, prompt, timeout or self.timeout, on_thinking
                )
            else:
                completed = subprocess.run(  # noqa: S603
                    argv,
                    input=prompt,
                    capture_output=True,
                    text=True,
                    timeout=timeout or self.timeout,
                    check=False,
                    shell=False,
                )
        except subprocess.TimeoutExpired as ex:
            raise LLMTimeout(
                f"Claude CLI timed out after {timeout or self.timeout}s"
            ) from ex
        finally:
            os.unlink(system_prompt_path)

        if completed.returncode != 0:
            # The CLI reports some failures on stdout and exits non-zero with an
            # empty stderr, so include both or the error is undiagnosable.
            detail = completed.stderr.strip() or completed.stdout.strip()
            raise LLMError(
                f"Claude CLI exited {completed.returncode}: "
                f"{detail[:800] or '<no output on stdout or stderr>'}"
            )

        return self._parse(completed.stdout)

    def _run_streaming(
        self, argv: list[str], prompt: str, timeout: int, on_thinking: Any
    ) -> subprocess.CompletedProcess:
        """Run the CLI in stream-json mode, forwarding reasoning as it arrives.

        Each stdout line is one JSON envelope. Thinking arrives as
        ``stream_event`` deltas; the terminal ``result`` envelope carries the
        same payload the non-streaming mode returns, so the caller's parsing is
        unchanged.
        """
        process = subprocess.Popen(  # noqa: S603
            argv,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            shell=False,
        )
        assert process.stdin is not None and process.stdout is not None

        final_line = ""
        thinking_tokens = 0
        answer_chars = 0
        deadline = time.monotonic() + timeout

        try:
            process.stdin.write(prompt)
            process.stdin.close()

            for line in process.stdout:
                if time.monotonic() > deadline:
                    process.kill()
                    raise subprocess.TimeoutExpired(argv, timeout)
                line = line.strip()
                if not line:
                    continue
                try:
                    envelope = json.loads(line)
                except ValueError:
                    continue

                if envelope.get("type") == "result":
                    final_line = line
                    continue
                if envelope.get("type") != "stream_event":
                    continue

                event = (envelope.get("event") or {})
                delta = event.get("delta") or {}

                # The CLI REDACTS reasoning text: thinking_delta arrives as
                # {"thinking": "", "estimated_tokens": N} plus an encrypted
                # signature_delta. So the text is unavailable here and only the
                # volume of reasoning can be reported. An API-based provider
                # (Bedrock) does return the content, and can override this.
                if delta.get("type") == "thinking_delta":
                    tokens = delta.get("estimated_tokens")
                    if isinstance(tokens, int):
                        thinking_tokens = max(thinking_tokens, tokens)
                    on_thinking(
                        {"phase": "thinking", "tokens": thinking_tokens, "text": ""}
                    )
                elif delta.get("type") == "text_delta":
                    # The answer itself is raw JSON; report only its growth so
                    # the UI can show that output is being produced.
                    answer_chars += len(delta.get("text") or "")
                    on_thinking(
                        {
                            "phase": "writing",
                            "tokens": thinking_tokens,
                            "chars": answer_chars,
                            "text": "",
                        }
                    )
        finally:
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()

        stderr = process.stderr.read() if process.stderr else ""
        return subprocess.CompletedProcess(
            argv, process.returncode or 0, stdout=final_line, stderr=stderr
        )

    @staticmethod
    def _build_prompt(user_prompt: str, image_paths: list[str]) -> str:
        if not image_paths:
            return user_prompt
        listed = "\n".join(f"- {path}" for path in image_paths)
        return (
            f"{user_prompt}\n\n"
            f"Read the following design image(s) before answering:\n{listed}"
        )

    def _parse(self, stdout: str) -> LLMResponse:
        try:
            payload: dict[str, Any] = json.loads(stdout)
        except ValueError as ex:
            raise LLMError(f"Claude CLI returned non-JSON output: {stdout[:500]}") from ex

        if payload.get("is_error"):
            raise LLMError(f"Claude CLI reported an error: {payload.get('result')}")

        text = payload.get("result")
        if not isinstance(text, str):
            raise LLMError(f"Claude CLI response has no 'result' string: {payload!r}")

        return LLMResponse(
            text=text,
            cost_usd=payload.get("total_cost_usd"),
            usage=payload.get("usage") or {},
            session_id=payload.get("session_id"),
            provider=self.name,
        )
