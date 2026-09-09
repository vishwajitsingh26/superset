#!/usr/bin/env python3
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
"""Export one run as a readable trace, for judging how well the model did.

Writes a Markdown file with, per stage: how long it took, what it cost, the
reasoning it produced, the tools it called, the decisions it made and the
evidence it cited -- plus the questions asked, the plan approved, and what
finally rendered.

    python design-to-dashboard/scripts/export_trace.py <session-id> [--out FILE]

Sessions live in the web process's memory, so this runs against the API.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import urllib.error
import urllib.request

API = "http://127.0.0.1:8088/api/v1"


def _post(path: str, payload: dict, token: str | None = None) -> dict:
    request = urllib.request.Request(
        f"{API}{path}",
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            **({"Authorization": f"Bearer {token}"} if token else {}),
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
        return json.load(response)


def _get(path: str, token: str) -> dict:
    request = urllib.request.Request(
        f"{API}{path}", headers={"Authorization": f"Bearer {token}"}
    )
    with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310
        return json.load(response)


def humanise(seconds: float) -> str:
    return f"{int(seconds // 60)}m {int(seconds % 60)}s" if seconds >= 60 else f"{seconds:.0f}s"


def render(state: dict) -> str:  # noqa: C901
    events = state.get("events") or []
    started = next((e["at"] for e in events if e.get("at")), None)
    out: list[str] = [
        f"# Run trace — {state.get('id')}",
        "",
        f"- **Requirement:** {state.get('requirement') or '(none)'}",
        f"- **Status:** {state.get('status')}",
        f"- **Events:** {len(events)}",
    ]
    result = state.get("result") or {}
    if result:
        out += [
            f"- **Dashboard:** {result.get('dashboard_url')} "
            f"(id {result.get('dashboard_id')})",
            f"- **Charts:** {len(result.get('charts_created') or [])} created, "
            f"{len(result.get('charts_reused') or [])} reused",
            f"- **Cost:** ${result.get('cost_usd', 0):.2f}",
            f"- **Rendering:** {result.get('rendering') or 'not checked'}",
        ]
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
                out += ["<details><summary>Reasoning</summary>", "",
                        "```", event["thinking"].strip(), "```", "",
                        "</details>", ""]
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
                if isinstance(check, dict) and "rows" in check:
                    mark = "ok" if check.get("ok") else "**FAILED**"
                    out.append(
                        f"- {mark} `{check.get('viz_type')}` #{check.get('chart_id')}"
                        f" rows={check.get('rows')} {check.get('error') or ''}"
                    )
            out.append("")

        elif kind == "tool_call":
            out.append(
                f"- 🔧 `{event.get('tool')}` "
                f"`{json.dumps(event.get('arguments'))[:160]}`"
            )
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
        elif kind in ("plugin_built", "registry_rebuilt", "frontend_restarted",
                      "frontend_restart_needed", "retry", "cancelled"):
            out.append(f"- _{kind}_: {event.get('label')}")
        elif kind == "error":
            out += ["", f"### ❌ Error", "", f"```\n{event.get('detail')}\n```", ""]

    notes = (state.get("result") or {}).get("fidelity_notes") or []
    if notes:
        out += ["## Known differences from the design", ""]
        for note in notes:
            out.append(f"- `{note.get('region_id')}`: {note.get('difference')}")
        out.append("")
    return "\n".join(out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session_id")
    parser.add_argument("--out")
    parser.add_argument("--username", default="admin")
    parser.add_argument("--password", default="admin")
    args = parser.parse_args()

    try:
        token = _post(
            "/security/login",
            {
                "username": args.username,
                "password": args.password,
                "provider": "db",
                "refresh": True,
            },
        )["access_token"]
        state = _get(f"/design_to_dashboard/session/{args.session_id}/", token)
    except urllib.error.HTTPError as ex:
        print(f"could not read the session: HTTP {ex.code}", file=sys.stderr)
        print("sessions live in the web process's memory and are lost on "
              "restart", file=sys.stderr)
        return 1

    out = pathlib.Path(
        args.out or f"design-to-dashboard/traces/{args.session_id}.md"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(state), encoding="utf-8")
    print(f"wrote {out} ({out.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
