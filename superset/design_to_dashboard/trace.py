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
"""The written record of one pipeline run.

Renders a session's event history into Markdown: per stage, how long it took,
what it cost, the reasoning it produced, the tools it called, the decisions it
made and the evidence it cited -- plus the questions asked, the plan approved,
and what finally rendered.

The runner writes one at the end of every run. Sessions live in the web
process's memory and are lost on restart, so a run whose trace is never written
leaves no evidence of *why* the pipeline decided what it did. That makes the
trace the only durable artifact for judging how well the model performed.
"""

from __future__ import annotations

import logging
import pathlib
from typing import Any

from superset.utils import json

logger = logging.getLogger(__name__)

TRACE_DIR = pathlib.Path("design-to-dashboard") / "traces"


def humanise(seconds: float) -> str:
    return (
        f"{int(seconds // 60)}m {int(seconds % 60)}s"
        if seconds >= 60
        else f"{seconds:.0f}s"
    )


def render(state: dict[str, Any]) -> str:  # noqa: C901
    events = state.get("events") or []
    out: list[str] = [
        f"# Run trace — {state.get('id')}",
        "",
        f"- **Requirement:** {state.get('requirement') or '(none)'}",
        f"- **Status:** {state.get('status')}",
        f"- **Events:** {len(events)}",
    ]
    if result := state.get("result") or {}:
        out += [
            f"- **Dashboard:** {result.get('dashboard_url')} "
            f"(id {result.get('dashboard_id')})",
            f"- **Charts:** {len(result.get('charts_created') or [])} created, "
            f"{len(result.get('charts_reused') or [])} reused",
            f"- **Cost:** ${result.get('cost_usd', 0):.2f}",
            f"- **Rendering:** {result.get('rendering') or 'not checked'}",
        ]
    if state.get("error"):
        out.append(f"- **Error:** {state['error']}")
    out.append("")

    starts: dict[str, float] = {}
    for event in events:
        kind = event.get("type")
        stage = event.get("stage") or ""
        at = event.get("at")

        if kind == "stage_start":
            starts[stage] = at
            out += [f"## Stage {stage} — {event.get('label')}", ""]

        elif kind == "stage_complete":
            took = at - starts.get(stage, at) if at else 0
            out += [
                f"**Took** {humanise(took)}  ·  **cost so far** "
                f"${event.get('cost') or 0:.2f}",
                "",
                f"**Result:** {event.get('summary') or '—'}",
                "",
            ]
            if event.get("thinking"):
                out += [
                    "<details><summary>Reasoning</summary>",
                    "",
                    "```",
                    event["thinking"].strip(),
                    "```",
                    "",
                    "</details>",
                    "",
                ]
            for decision in event.get("decisions") or []:
                out.append(
                    f"- `{decision.get('region_id')}` → **{decision.get('decision')}**"
                    f" `{decision.get('viz_type') or ''}`"
                )
                for label, key in (
                    ("thumbnails", "thumbnail_evidence"),
                    ("reuse evidence", "reuse_evidence"),
                    ("fidelity loss", "fidelity_loss"),
                ):
                    if decision.get(key):
                        out.append(f"    - _{label}_: {decision[key]}")
            if event.get("decisions"):
                out.append("")
            for check in event.get("charts") or []:
                if not isinstance(check, dict):
                    continue
                if "rows" in check:
                    # The verify stage: a chart that exists, queried for real.
                    mark = "ok" if check.get("ok") else "**FAILED**"
                    out.append(
                        f"- {mark} `{check.get('viz_type')}` #{check.get('chart_id')}"
                        f" rows={check.get('rows')} "
                        f"{check.get('error') or check.get('note') or ''}"
                    )
                elif not check.get("ok"):
                    # Stage D: only the charts that did not come out clean.
                    # Recorded with what was wrong, because the summary line
                    # ("20/23 ready") was the only trace of it and named
                    # neither which three nor why.
                    out.append(
                        f"- **NOT READY** `{check.get('ref')}` "
                        f"`{check.get('viz_type')}` "
                        f"({check.get('region_id') or '?'})"
                    )
                    if check.get("error"):
                        out.append(f"    - _error_: {check['error']}")
                    for problem in check.get("problems") or []:
                        out.append(f"    - _problem_: {problem}")
            out.append("")

        elif kind == "tool_call":
            # The outcome, not just the request. A tool the model reaches for
            # and is refused by every time reads as ordinary activity without
            # it, and the stage that went uninformed looks like it simply
            # chose not to ask.
            error = event.get("error")
            out.append(
                f"- {'❌' if error else '🔧'} `{event.get('tool')}` "
                f"`{json.dumps(event.get('arguments'))[:160]}`"
            )
            if error:
                out.append(f"    - _refused_: {str(error)[:300]}")
        elif kind == "awaiting_input":
            out += ["", f"### ⏸ Asked the user ({event.get('kind')})", ""]
            for question in event.get("questions") or []:
                out += [
                    f"- **{question.get('question')}**",
                    f"    - _why_: {question.get('why_it_matters') or '—'}",
                    f"    - _default_: {question.get('default') or '—'}",
                ]
            for step in event.get("plan") or []:
                out += [
                    f"- **{step.get('step')}. {step.get('what')}**",
                    f"    - _why_: {step.get('why') or '—'}",
                    f"    - _match_: {step.get('exactness') or '—'}",
                    f"    - _cost_: {step.get('cost') or '—'}",
                ]
            out.append("")
        elif kind == "input_received":
            out += [f"**Answered:** `{json.dumps(event.get('answer'))[:400]}`", ""]
        elif kind in (
            "plugin_built",
            "registry_rebuilt",
            "frontend_restarted",
            "frontend_restart_needed",
            "retry",
            "cancelled",
        ):
            out.append(f"- _{kind}_: {event.get('label')}")
        elif kind == "error":
            out += ["", "### ❌ Error", "", f"```\n{event.get('detail')}\n```", ""]

    result = state.get("result") or {}

    # What the comparison actually found, as against the plan's predictions
    # below. This is the only assessment of the built dashboard, and it lived
    # nowhere but an in-memory session: the trace recorded what the pipeline
    # expected to get wrong and omitted what it did get wrong.
    out += _visual_section(result)

    if notes := result.get("fidelity_notes") or []:
        out += [
            "## Differences the plan predicted",
            "",
            "_Written before anything was built._",
            "",
        ]
        for note in notes:
            out.append(f"- `{note.get('region_id')}`: {note.get('difference')}")
        out.append("")
    return "\n".join(out)


_SEVERITY_MARK = {"critical": "🔴", "medium": "🟠", "low": "🟡"}


def _visual_section(result: dict[str, Any]) -> list[str]:  # noqa: C901
    """How close the built dashboard came, and every way it did not."""
    verdict = result.get("visual_verdict")
    findings = result.get("visual_findings") or []
    if not verdict and not findings:
        return []

    out = ["## How close it came", ""]
    if (score := result.get("visual_score")) is not None:
        out.append(f"**{verdict}** — {score}/60")
    else:
        out.append(f"**{verdict}**")
    if scores := result.get("visual_scores") or {}:
        out.append("")
        out.append(
            " · ".join(f"{name} {value}/10" for name, value in sorted(scores.items()))
        )
    if summary := result.get("visual_summary"):
        out += ["", summary]
    if problems := result.get("visual_problems") or []:
        out += ["", "_The report broke its own contract:_ " + "; ".join(problems)]
    out.append("")

    for finding in findings:
        if not isinstance(finding, dict):
            continue
        mark = _SEVERITY_MARK.get(str(finding.get("severity")), "")
        out.append(
            f"- {mark} `{finding.get('region_id') or '?'}` "
            f"({finding.get('likely_fix') or 'unknown'})"
        )
        if finding.get("design_shows"):
            out.append(f"    - _design_: {finding['design_shows']}")
        if finding.get("screenshot_shows"):
            out.append(f"    - _built_: {finding['screenshot_shows']}")
    if shot := result.get("screenshot_path"):
        out += ["", f"_Screenshot:_ `{shot}`"]
    out.append("")
    return out


def path_for(session_id: str, repo_root: pathlib.Path) -> pathlib.Path:
    """Where a session's trace lands. Derived from the id, so it is knowable
    before the run ends and can be handed to the client with the final event."""
    return repo_root / TRACE_DIR / f"{session_id}.md"


def state_of(session: Any) -> dict[str, Any]:
    """The same shape `GET /session/<id>/` returns, built in-process."""
    return {
        "id": session.id,
        "status": session.status,
        "requirement": session.requirement,
        "result": session.result,
        "error": session.error,
        **session.snapshot(),
    }


def write(session: Any, repo_root: pathlib.Path) -> pathlib.Path | None:
    """Write the run's trace to disk, returning the path.

    Never raises: a run that produced a dashboard must not be reported as
    failed because its trace could not be saved. A failure is logged and the
    caller carries on.
    """
    destination = path_for(session.id, repo_root)
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(render(state_of(session)), encoding="utf-8")
    except Exception:  # noqa: BLE001 - the run's own outcome takes precedence
        logger.exception("could not write the trace for session %s", session.id)
        return None
    logger.info(
        "wrote trace for session %s to %s (%d KB)",
        session.id,
        destination,
        destination.stat().st_size // 1024,
    )
    return destination
