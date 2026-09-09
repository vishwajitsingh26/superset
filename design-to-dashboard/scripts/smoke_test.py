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
"""Run one Design-to-Dashboard stage against the local Claude CLI.

Exercises stages without booting Superset, so prompts can be iterated on
directly.

    python design-to-dashboard/scripts/smoke_test.py --stage ping
    python design-to-dashboard/scripts/smoke_test.py --stage A --image <path>
    python design-to-dashboard/scripts/smoke_test.py --stage B          # fixtures
    python design-to-dashboard/scripts/smoke_test.py --stage B --live   # real MCP

Stage B defaults to the fixture gateway. ``--live`` uses the in-process MCP
gateway and therefore needs a configured Superset and an app context.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import pathlib
import sys
import types

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
DOCS = REPO_ROOT / "design-to-dashboard"
PROMPTS = DOCS / "prompts"
FIXTURES = DOCS / "fixtures"

# Fixture mode registers `superset` as a bare namespace package pointing at the
# source tree, WITHOUT executing superset/__init__.py — that module imports
# Flask and the rest of the app, and skipping it lets prompts be iterated on
# with no virtualenv.
#
# Live mode must NOT do this: the stub shadows the real package, so
# `superset.config` and `security_manager` fail to resolve. `--live` is read
# from argv here because the stub has to be decided before any import below.
LIVE = "--live" in sys.argv

if not LIVE and "superset" not in sys.modules:
    _pkg = types.ModuleType("superset")
    _pkg.__path__ = [str(REPO_ROOT / "superset")]  # type: ignore[attr-defined]
    sys.modules["superset"] = _pkg
elif LIVE:
    sys.path.insert(0, str(REPO_ROOT))

from superset.design_to_dashboard.llm.base import LLMError  # noqa: E402
from superset.design_to_dashboard.llm.claude_cli import (  # noqa: E402
    ClaudeCliProvider,
)
from superset.design_to_dashboard.mcp.gateway import (  # noqa: E402
    FixtureGateway,
    InProcessGateway,
)
from superset.design_to_dashboard.stages import (  # noqa: E402
    b_bind,
    c_resolve,
    d_configure,
)

STAGE_FILES = {
    "A": "A_decompose_design.md",
    "D": "D_configure_chart.md",
    "E": "E_layout.md",
    "F": "F_scaffold_plugin.md",
}


def simple_system_prompt(stage: str) -> str:
    preamble = (PROMPTS / "shared" / "_preamble.md").read_text(encoding="utf-8")
    stage_prompt = (PROMPTS / STAGE_FILES[stage]).read_text(encoding="utf-8")
    return f"{preamble}\n\n---\n\n{stage_prompt}"


@contextlib.contextmanager
def _live_context():
    """A Flask request context with g.user set.

    `mcp_auth_hook` pushes a fresh app context when no request context is
    active, discarding any g.user set beforehand — so the tools must be called
    from inside a request. Production gets this from serving an API request.
    """
    from flask import g

    from superset.app import create_app

    app = create_app()
    with app.test_request_context("/api/v1/design_to_dashboard/"):
        user = app.appbuilder.sm.find_user(username="admin")
        if user is None:
            users = app.appbuilder.sm.get_all_users()
            user = users[0] if users else None
        if user is None:
            raise SystemExit("live mode needs a user in the metadata DB")
        g.user = user
        yield


def emit(obj: object) -> None:
    print(json.dumps(obj, indent=2, default=str))


def _dump_calls(gateway: object) -> None:
    """Show what the model actually called - the first thing to check when a
    tool loop misbehaves."""
    calls = getattr(gateway, "calls", None)
    if not calls:
        return
    print(f"tool calls made ({len(calls)}):", file=sys.stderr)
    for index, call in enumerate(calls, start=1):
        print(f"  {index}. {call['tool']} {json.dumps(call['arguments'])}",
              file=sys.stderr)


def main() -> int:  # noqa: C901
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--stage", default="ping", choices=[*STAGE_FILES, "B", "C", "D", "ping"]
    )
    parser.add_argument("--image", action="append", default=[], help="absolute path")
    parser.add_argument("--requirement", default="Rebuild this dashboard in Superset.")
    parser.add_argument(
        "--design-analysis",
        default=str(FIXTURES / "stage_a_output.json"),
        help="stage A output feeding stage B",
    )
    parser.add_argument(
        "--binding-set",
        default=str(FIXTURES / "stage_b_output.json"),
        help="stage B output feeding stage C",
    )
    parser.add_argument(
        "--plan",
        default=str(FIXTURES / "stage_c_output.json"),
        help="stage C output feeding stage D",
    )
    parser.add_argument("--max-workers", type=int, default=4)
    parser.add_argument(
        "--registry",
        default=str(FIXTURES / "viz_registry.json"),
        help="viz-type manifest for stages C and D",
    )
    parser.add_argument(
        "--live", action="store_true", help="use real MCP instead of fixtures"
    )
    parser.add_argument("--max-tool-calls", type=int, default=8)
    parser.add_argument("--model", default="claude-opus-5")
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--out", help="write the stage output to this path")
    parser.add_argument("--raw", action="store_true", help="print text, skip JSON parse")
    args = parser.parse_args()

    try:
        provider = ClaudeCliProvider(model=args.model, timeout=args.timeout)
    except LLMError as ex:
        print(f"FAIL: {ex}", file=sys.stderr)
        return 2

    # ---- stage D: per-chart fan-out -----------------------------------------
    if args.stage == "D":
        needed = {
            "stage A": args.design_analysis,
            "stage B": args.binding_set,
            "stage C": args.plan,
        }
        for label, path_str in needed.items():
            if not pathlib.Path(path_str).exists():
                print(f"FAIL: no {label} output at {path_str}", file=sys.stderr)
                return 2
        design_analysis = json.loads(
            pathlib.Path(args.design_analysis).read_text(encoding="utf-8")
        )
        binding_set = json.loads(
            pathlib.Path(args.binding_set).read_text(encoding="utf-8")
        )
        plan = json.loads(pathlib.Path(args.plan).read_text(encoding="utf-8"))

        jobs = [
            d
            for d in plan.get("decisions", [])
            if d.get("decision") in d_configure.CONFIGURABLE
        ]
        print(
            f"stage=D charts={len(jobs)} workers={args.max_workers} "
            f"registry={pathlib.Path(args.registry).name}",
            file=sys.stderr,
        )

        results = d_configure.run_all(
            provider=provider,
            design_analysis=design_analysis,
            binding_set=binding_set,
            plan=plan,
            prompts_dir=PROMPTS,
            registry_path=args.registry,
            repo_root=REPO_ROOT,
            max_workers=args.max_workers,
        )

        total_cost = sum(r.cost_usd for r in results)
        failed = [r for r in results if not r.ok]
        print(f"cost=${total_cost:.4f}", file=sys.stderr)
        for result in results:
            status = "ok" if result.ok else "FAIL"
            print(
                f"  [{status}] {result.ref} {result.region_id} ({result.viz_type})",
                file=sys.stderr,
            )
            if result.error:
                print(f"      error: {result.error[:200]}", file=sys.stderr)
            for problem in result.problems:
                print(f"      - {problem}", file=sys.stderr)

        payload = {
            "charts": [
                {
                    "ref": r.ref,
                    "region_id": r.region_id,
                    "viz_type": r.viz_type,
                    "spec": r.spec,
                    "problems": r.problems,
                    "error": r.error,
                }
                for r in results
            ],
            "summary": {
                "total": len(results),
                "ok": len(results) - len(failed),
                "failed": len(failed),
                "cost_usd": round(total_cost, 4),
            },
        }
        if args.out:
            pathlib.Path(args.out).write_text(
                json.dumps(payload, indent=2), encoding="utf-8"
            )
            print(f"wrote {args.out}", file=sys.stderr)
        emit(payload)
        return 1 if failed else 0

    # ---- stage C: tool loop -------------------------------------------------
    if args.stage == "C":
        for label, path_str in (
            ("stage A", args.design_analysis),
            ("stage B", args.binding_set),
        ):
            if not pathlib.Path(path_str).exists():
                print(f"FAIL: no {label} output at {path_str}", file=sys.stderr)
                return 2
        design_analysis = json.loads(
            pathlib.Path(args.design_analysis).read_text(encoding="utf-8")
        )
        binding_set = json.loads(
            pathlib.Path(args.binding_set).read_text(encoding="utf-8")
        )
        gateway = (
            InProcessGateway() if args.live else FixtureGateway(FIXTURES / "mcp")
        )
        context = _live_context() if args.live else contextlib.nullcontext()
        print(
            f"stage=C gateway={gateway.name} "
            f"regions={len(design_analysis.get('regions', []))} "
            f"bindings={len(binding_set.get('bindings', []))} "
            f"budget={args.max_tool_calls}",
            file=sys.stderr,
        )
        try:
            with context:
                result = c_resolve.run(
                    provider=provider,
                    gateway=gateway,
                    design_analysis=design_analysis,
                    binding_set=binding_set,
                    prompts_dir=PROMPTS,
                    registry_path=args.registry,
                    max_tool_calls=args.max_tool_calls,
                )
        except LLMError as ex:
            print(f"FAIL: {ex}", file=sys.stderr)
            _dump_calls(gateway)
            return 1

        print(
            f"iterations={result.iterations} tool_calls={result.tool_calls} "
            f"cost=${result.cost_usd:.4f}",
            file=sys.stderr,
        )
        _dump_calls(gateway)
        print(f"counts={result.final.get('counts')}", file=sys.stderr)

        problems = c_resolve.validate(
            result.final, design_analysis, binding_set, args.registry
        )
        if problems:
            print("\nVALIDATION PROBLEMS:", file=sys.stderr)
            for problem in problems:
                print(f"  - {problem}", file=sys.stderr)
        else:
            print("validation: clean", file=sys.stderr)

        if args.out:
            pathlib.Path(args.out).write_text(
                json.dumps(result.final, indent=2), encoding="utf-8"
            )
            print(f"wrote {args.out}", file=sys.stderr)
        emit(result.final)
        return 1 if problems else 0

    # ---- stage B: tool loop -------------------------------------------------
    if args.stage == "B":
        analysis_path = pathlib.Path(args.design_analysis)
        if not analysis_path.exists():
            print(f"FAIL: no stage A output at {analysis_path}", file=sys.stderr)
            return 2
        design_analysis = json.loads(analysis_path.read_text(encoding="utf-8"))

        gateway = (
            InProcessGateway() if args.live else FixtureGateway(FIXTURES / "mcp")
        )
        context = _live_context() if args.live else contextlib.nullcontext()
        print(
            f"stage=B gateway={gateway.name} regions="
            f"{len(design_analysis.get('regions', []))} "
            f"budget={args.max_tool_calls}",
            file=sys.stderr,
        )

        try:
            with context:
                result = b_bind.run(
                    provider=provider,
                    gateway=gateway,
                    design_analysis=design_analysis,
                    prompts_dir=PROMPTS,
                    max_tool_calls=args.max_tool_calls,
                )
        except LLMError as ex:
            print(f"FAIL: {ex}", file=sys.stderr)
            _dump_calls(gateway)
            return 1

        print(
            f"iterations={result.iterations} tool_calls={result.tool_calls} "
            f"cost=${result.cost_usd:.4f}",
            file=sys.stderr,
        )
        _dump_calls(gateway)

        problems = b_bind.validate(result.final, design_analysis)
        if problems:
            print("\nVALIDATION PROBLEMS:", file=sys.stderr)
            for problem in problems:
                print(f"  - {problem}", file=sys.stderr)
        else:
            print("validation: clean", file=sys.stderr)

        if args.out:
            pathlib.Path(args.out).write_text(
                json.dumps(result.final, indent=2), encoding="utf-8"
            )
            print(f"wrote {args.out}", file=sys.stderr)
        emit(result.final)
        return 1 if problems else 0

    # ---- single-shot stages -------------------------------------------------
    if args.stage == "ping":
        system_prompt = "You are a test harness. Reply with JSON only."
        user_prompt = 'Reply with exactly: {"ok": true, "stage": "ping"}'
        images: list[str] = []
    else:
        system_prompt = simple_system_prompt(args.stage)
        user_prompt = f"USER_REQUIREMENT:\n{args.requirement}"
        images = [str(pathlib.Path(p).resolve()) for p in args.image]
        if args.stage == "A" and not images:
            print("FAIL: stage A needs --image", file=sys.stderr)
            return 2

    print(f"stage={args.stage} model={args.model} images={len(images)}", file=sys.stderr)
    print(f"system_prompt={len(system_prompt)} chars", file=sys.stderr)

    try:
        response = provider.complete(system_prompt, user_prompt, images)
    except LLMError as ex:
        print(f"FAIL: {ex}", file=sys.stderr)
        return 1

    print(
        f"cost=${response.cost_usd or 0:.4f} session={response.session_id}",
        file=sys.stderr,
    )

    if args.raw:
        print(response.text)
        return 0

    from superset.design_to_dashboard.pipeline.tool_loop import extract_json

    try:
        payload = extract_json(response.text)
    except LLMError:
        print("WARN: response was not valid JSON; printing raw\n", file=sys.stderr)
        print(response.text)
        return 1

    if args.out:
        pathlib.Path(args.out).write_text(
            json.dumps(payload, indent=2), encoding="utf-8"
        )
        print(f"wrote {args.out}", file=sys.stderr)
    emit(payload)
    return 0


if __name__ == "__main__":
    sys.exit(main())
