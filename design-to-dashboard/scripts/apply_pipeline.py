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
"""Run stage E and apply the plan, creating a real dashboard.

Takes the outputs of stages A-D and produces an actual dashboard in the
configured Superset instance. Requires a real environment: this is the one
script that writes to the database.

    SUPERSET_CONFIG_PATH=... .venv/bin/python \\
        design-to-dashboard/scripts/apply_pipeline.py \\
        --design-analysis a.json --binding-set b.json --plan c.json --charts d.json
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
PROMPTS = REPO_ROOT / "design-to-dashboard" / "prompts"
sys.path.insert(0, str(REPO_ROOT))


def main() -> int:  # noqa: C901
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--design-analysis", required=True)
    parser.add_argument("--binding-set", required=True)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--charts", required=True)
    parser.add_argument(
        "--layout-out", default="design-to-dashboard/fixtures/stage_e_output.json"
    )
    parser.add_argument("--title", default=None)
    parser.add_argument("--model", default="claude-opus-5")
    parser.add_argument(
        "--dry-run", action="store_true", help="run stage E, skip the database write"
    )
    args = parser.parse_args()

    def load(path: str) -> Any:
        return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))

    design_analysis = load(args.design_analysis)
    binding_set = load(args.binding_set)  # noqa: F841 - kept for symmetry/debugging
    plan = load(args.plan)
    charts_payload = load(args.charts)
    chart_specs = charts_payload.get("charts", charts_payload)

    from flask import g

    from superset.app import create_app
    from superset.design_to_dashboard.applier import apply_plan, ApplyError
    from superset.design_to_dashboard.llm.claude_cli import ClaudeCliProvider
    from superset.design_to_dashboard.stages import e_layout
    from superset.extensions import security_manager

    app = create_app()
    with app.test_request_context("/api/v1/design_to_dashboard/"):
        user = security_manager.find_user(username="admin")
        if user is None:
            users = security_manager.get_all_users()
            user = users[0] if users else None
        if user is None:
            print("FAIL: no user in the metadata DB", file=sys.stderr)
            return 2
        g.user = user

        # ---- stage E --------------------------------------------------------
        print("=== STAGE E (layout) ===", file=sys.stderr)
        provider = ClaudeCliProvider(model=args.model)
        layout, cost = e_layout.run(provider, design_analysis, plan, PROMPTS)
        nodes = layout.get("position_json") or {}
        print(
            f"nodes={len(nodes)} adjustments={len(layout.get('adjustments') or [])} "
            f"cost=${cost:.4f}",
            file=sys.stderr,
        )
        for adjustment in layout.get("adjustments") or []:
            print(f"  adj: {adjustment}", file=sys.stderr)

        problems = e_layout.validate(layout, plan)
        if problems:
            print("VALIDATION PROBLEMS:", file=sys.stderr)
            for problem in problems:
                print(f"  - {problem}", file=sys.stderr)
        else:
            print("validation: clean", file=sys.stderr)

        pathlib.Path(args.layout_out).write_text(
            json.dumps(layout, indent=2), encoding="utf-8"
        )
        print(f"wrote {args.layout_out}", file=sys.stderr)

        if problems:
            print("refusing to apply a layout that failed validation", file=sys.stderr)
            return 1
        if args.dry_run:
            print("dry run: not writing to the database", file=sys.stderr)
            return 0

        # ---- apply ----------------------------------------------------------
        print("\n=== APPLY ===", file=sys.stderr)
        try:
            result = apply_plan(
                design_analysis=design_analysis,
                plan=plan,
                chart_specs=chart_specs,
                layout=layout,
                dashboard_title=args.title,
            )
        except ApplyError as ex:
            print(f"FAIL: {ex}", file=sys.stderr)
            return 1

        for warning in result.warnings:
            print(f"  warn: {warning}", file=sys.stderr)
        print(
            json.dumps(
                {
                    "dashboard_id": result.dashboard_id,
                    "dashboard_url": result.dashboard_url,
                    "charts_created": result.charts_created,
                    "charts_reused": result.charts_reused,
                    "ref_to_id": result.ref_to_id,
                    "warnings": result.warnings,
                },
                indent=2,
            )
        )
        return 0


if __name__ == "__main__":
    sys.exit(main())
