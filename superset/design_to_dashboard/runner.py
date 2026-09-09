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
"""Runs the pipeline for a chat session, emitting progress events.

Executes in a worker thread. Flask contexts do not cross threads, so the
worker pushes its own request context and re-loads the user: the MCP gateway
and the applier both require ``g.user`` inside a request context.
"""

from __future__ import annotations

import logging
import pathlib
import sys
import threading
from typing import Any, Callable

from superset.design_to_dashboard import trace, visual_verify

logger = logging.getLogger(__name__)


def _config() -> dict[str, Any]:
    from flask import current_app

    return current_app.config.get("DESIGN_TO_DASHBOARD_LLM") or {}


def _regenerate_registry(session: Any) -> None:
    """Rebuild the viz-type manifest after a plugin lands on disk.

    Stage D validates params against the manifest and reads the control panel
    from it, so a freshly written plugin is invisible until this runs.
    """
    import subprocess  # noqa: S404 - fixed argv, no shell

    script = REPO_ROOT / "design-to-dashboard" / "scripts" / "build_viz_registry.py"
    completed = subprocess.run(  # noqa: S603
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        check=False,
        shell=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"could not regenerate the viz registry: "
            f"{(completed.stderr or completed.stdout)[-400:]}"
        )
    session.publish("registry_rebuilt", label="Chart registry updated")


def _retry(session: Any, label: str, attempts: int, call: Any) -> Any:
    """Retry a single-shot stage.

    These calls are non-deterministic: the same prompt can end on
    ``stop_reason: tool_use`` once and answer cleanly the next time. Losing an
    entire multi-dollar run to one flaky turn is not acceptable, so each
    single-shot stage gets a second chance before the run fails.
    """
    from superset.design_to_dashboard.llm.base import LLMError

    last: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return call()
        except LLMError as ex:
            last = ex
            logger.warning("%s attempt %d/%d failed: %s", label, attempt, attempts, ex)
            if attempt < attempts:
                session.publish(
                    "retry",
                    label=f"{label} hit a transient error — retrying",
                    detail=str(ex)[:200],
                )
    raise last  # type: ignore[misc]


PROMPTS = (
    pathlib.Path(__file__).resolve().parents[2] / "design-to-dashboard" / "prompts"
)
REGISTRY = (
    pathlib.Path(__file__).resolve().parents[2]
    / "design-to-dashboard"
    / "fixtures"
    / "viz_registry.json"
)
REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
# One labelled image of every plugin's thumbnail. A plugin is a UI component, so
# its thumbnail is the most direct evidence of whether it matches a design
# section -- better than a text description, and one image rather than 46.
THUMBNAIL_SHEET = (
    pathlib.Path(__file__).resolve().parents[2]
    / "design-to-dashboard"
    / "fixtures"
    / "plugin_thumbnails.png"
)


def start(app: Any, session: Any) -> None:
    """Kick off the pipeline for ``session`` in a background thread."""
    thread = threading.Thread(
        target=_run, args=(app, session), name=f"d2d-{session.id[:8]}", daemon=True
    )
    thread.start()


def _run(app: Any, session: Any) -> None:  # noqa: C901
    from flask import g

    with app.test_request_context("/api/v1/design_to_dashboard/"):
        try:
            user = app.appbuilder.sm.get_user_by_id(session.user_id)
            if user is None:
                raise RuntimeError(f"user {session.user_id} not found")
            g.user = user

            from superset.design_to_dashboard import plugin_writer
            from superset.design_to_dashboard.applier import apply_plan, ApplyError
            from superset.design_to_dashboard.llm.factory import get_llm_provider
            from superset.design_to_dashboard.mcp.gateway import InProcessGateway
            from superset.design_to_dashboard.registry import (
                chart_types,
                load as load_registry,
            )
            from superset.design_to_dashboard.stages import (
                b_bind,
                c_resolve,
                clarify,
                d_configure,
                e_layout,
                f_scaffold,
            )

            provider = get_llm_provider()
            gateway = InProcessGateway()
            session.status = "running"
            total_cost = 0.0

            def _thinking_for(stage: str) -> Callable[[dict[str, Any]], None]:
                """Route a stage's reasoning into the session's live buffer.

                The buffer is replaceable rather than appended as events: a
                single stage can emit thousands of thinking tokens, and storing
                each as an event would bloat the session and be replayed on
                every reconnect.
                """

                def sink(update: dict[str, Any]) -> None:
                    if text := (update or {}).get("text") or "":
                        session.set_thinking(stage, text)

                return sink

            # ---- A: decompose ------------------------------------------------
            session.publish("stage_start", stage="A", label="Reading the design")
            system_prompt = "\n\n---\n\n".join(
                [
                    (PROMPTS / "shared" / "_preamble.md").read_text(encoding="utf-8"),
                    (PROMPTS / "A_decompose_design.md").read_text(encoding="utf-8"),
                ]
            )
            response = _retry(
                session,
                "Reading the design",
                2,
                lambda: provider.complete(
                    system_prompt,
                    f"USER_REQUIREMENT:\n{session.requirement}",
                    session.image_paths,
                    on_thinking=_thinking_for("A"),
                ),
            )
            total_cost += response.cost_usd or 0.0
            from superset.design_to_dashboard.pipeline.tool_loop import extract_json

            design_analysis = extract_json(response.text)
            session.artifacts["design_analysis"] = design_analysis
            _reasoning = session.take_thinking()
            session.publish(
                "stage_complete",
                stage="A",
                thinking=_reasoning,
                label="Read the design",
                summary=f"{len(design_analysis.get('regions', []))} regions found",
                regions=design_analysis.get("regions", []),
                cost=round(total_cost, 4),
            )

            # ---- B: bind -----------------------------------------------------
            session.publish("stage_start", stage="B", label="Finding your data")

            def _tool_progress(tool: str, arguments: dict[str, Any]) -> None:
                session.publish("tool_call", tool=tool, arguments=arguments)

            binding = b_bind.run(
                provider,
                gateway,
                design_analysis,
                PROMPTS,
                on_progress=_tool_progress,
                on_thinking=_thinking_for("B"),
            )
            total_cost += binding.cost_usd
            session.artifacts["binding_set"] = binding.final
            binding_questions = binding.final.get("questions", [])
            _reasoning = session.take_thinking()
            session.publish(
                "stage_complete",
                stage="B",
                thinking=_reasoning,
                label="Matched your data",
                summary=", ".join(
                    d.get("name", "?") for d in binding.final.get("datasets_used", [])
                )
                or "bound",
                bindings=binding.final.get("bindings", []),
                cost=round(total_cost, 4),
            )

            # ---- Clarify: the only place the run asks anything ----------------
            session.publish(
                "stage_start", stage="clarify", label="Checking for anything unclear"
            )
            clarification, clarify_cost = clarify.run(
                provider,
                design_analysis,
                binding.final,
                PROMPTS,
                on_thinking=_thinking_for("clarify"),
            )
            total_cost += clarify_cost
            questions = list(binding_questions) + list(
                clarification.get("questions") or []
            )
            _reasoning = session.take_thinking()
            session.publish(
                "stage_complete",
                stage="clarify",
                label="Checked for anything unclear",
                thinking=_reasoning,
                summary=(
                    f"{len(questions)} question(s)" if questions else "nothing unclear"
                ),
                cost=round(total_cost, 4),
            )

            answers: dict[str, Any] = {}
            if questions:
                # Blocks here. Everything past plan approval runs without
                # stopping, so this is the last chance to remove a guess.
                answers = session.ask(
                    "questions",
                    {
                        "label": "A few things before I plan this",
                        "questions": questions,
                    },
                )

            # ---- C: resolve --------------------------------------------------
            session.publish("stage_start", stage="C", label="Choosing chart types")
            binding_with_answers = dict(binding.final)
            if answers:
                binding_with_answers["user_answers"] = answers
            plan = c_resolve.run(
                provider,
                gateway,
                design_analysis,
                binding_with_answers,
                PROMPTS,
                str(REGISTRY),
                on_progress=_tool_progress,
                on_thinking=_thinking_for("C"),
                thumbnail_sheet=str(THUMBNAIL_SHEET)
                if THUMBNAIL_SHEET.exists()
                else None,
            )
            total_cost += plan.cost_usd
            session.artifacts["plan"] = plan.final
            counts = plan.final.get("counts", {})
            _reasoning = session.take_thinking()
            session.publish(
                "stage_complete",
                stage="C",
                thinking=_reasoning,
                label="Chose chart types",
                summary=plan.final.get("summary")
                or ", ".join(f"{v} {k}" for k, v in counts.items() if v),
                decisions=plan.final.get("decisions", []),
                counts=counts,
                cost=round(total_cost, 4),
            )
            # ---- Approve the plan; nothing is created before this ------------
            approval = session.ask(
                "plan",
                {
                    "label": "Here is what I will build — approve to continue",
                    "plan": plan.final.get("plan_for_review") or [],
                    "decisions": plan.final.get("decisions", []),
                    "counts": plan.final.get("counts", {}),
                    # Creating a dataset writes to the user's database, so it
                    # belongs in what they approve, not only in the answers.
                    "datasets": binding.final.get("created_datasets") or [],
                },
            )
            if not approval.get("approved"):
                session.status = "cancelled"
                session.publish(
                    "cancelled",
                    label="Plan rejected — nothing was created",
                    detail=approval.get("feedback"),
                )
                return

            # ---- F: scaffold plugins the design actually needs ---------------
            new_plugin_decisions = [
                d
                for d in plan.final.get("decisions", [])
                if d.get("decision") == "new_plugin"
            ]
            if new_plugin_decisions:
                regions = {
                    r["region_id"]: r for r in design_analysis.get("regions", [])
                }
                bindings = {
                    b["region_id"]: b for b in binding.final.get("bindings", [])
                }
                known = chart_types(load_registry(str(REGISTRY)))
                session.publish(
                    "stage_start",
                    stage="F",
                    label=(
                        f"Building {len(new_plugin_decisions)} custom chart plugin(s)"
                    ),
                )
                built: list[str] = []
                # Several regions can need the same plugin -- four identical KPI
                # tiles are four decisions and one plugin. Build each distinct
                # type once: generating it again would both waste 5-10 minutes
                # and fail validation, since the viz_type now exists.
                built_types: dict[str, dict[str, Any]] = {}

                for decision in new_plugin_decisions:
                    region_id = decision.get("region_id", "?")
                    proposed = decision.get("viz_type")
                    if proposed and proposed in built_types:
                        earlier = built_types[proposed]
                        decision["viz_type"] = proposed
                        decision["decision"] = "configure"
                        decision["built_by_stage_f"] = True
                        if earlier.get("params_hint"):
                            decision["params_hint"] = earlier["params_hint"]
                        session.publish(
                            "plugin_built",
                            label=f"Reused {proposed} for {region_id}",
                            viz_type=proposed,
                            reused=True,
                        )
                        continue
                    # F is a single-shot call like A and E, and equally prone
                    # to a transient failure -- losing a 40-minute run to one is
                    # not acceptable.
                    scaffold = _retry(
                        session,
                        f"Building the plugin for {region_id}",
                        2,
                        lambda region_id=region_id, decision=decision: (
                            f_scaffold.run_one(
                                provider,
                                regions.get(region_id, {}),
                                bindings.get(region_id, {}),
                                decision,
                                plan.final.get("design_system", {}),
                                PROMPTS,
                                REPO_ROOT,
                                known,
                                on_thinking=_thinking_for("F"),
                            )
                        ),
                    )
                    total_cost += scaffold.cost_usd
                    if not scaffold.ok:
                        raise RuntimeError(
                            f"plugin for {region_id} failed: "
                            f"{scaffold.error or scaffold.problems}"
                        )
                    # The model may land on a type it already produced this
                    # run; reuse rather than rewriting or failing.
                    if scaffold.viz_type in built_types:
                        decision["viz_type"] = scaffold.viz_type
                        decision["decision"] = "configure"
                        decision["built_by_stage_f"] = True
                        continue

                    written = plugin_writer.write(scaffold.scaffold, REPO_ROOT)
                    # `plugin_writer` adds the import to setupPluginsExtra.ts as
                    # soon as the plugin lands, but webpack resolves that import
                    # through a node_modules symlink that only `npm install`
                    # creates. Linking now rather than once at the end of the
                    # stage closes the window where the dev server reports
                    # "Module not found" for every remaining plugin's build.
                    from superset.design_to_dashboard import frontend

                    frontend.link_plugins(REPO_ROOT)
                    built.append(scaffold.viz_type or "?")
                    # Deliberately NOT added to `known`. `known` is what stage F
                    # validates against, and a type built moments ago in this
                    # same run is not a name clash -- it is the shared plugin
                    # two regions asked for. Adding it made the second region
                    # fail with "already exists in the registry", killing the
                    # run before the dedup below could reuse it.
                    built_types[scaffold.viz_type or ""] = {
                        "params_hint": scaffold.scaffold.get("params_hint")
                    }
                    # Stage D needs params for a control panel that did not exist
                    # when the registry manifest was generated.
                    if scaffold.scaffold.get("params_hint"):
                        decision["params_hint"] = scaffold.scaffold["params_hint"]
                    decision["viz_type"] = scaffold.viz_type
                    # The plugin now exists, so this region is configurable like
                    # any other. Without this the decision stays "new_plugin",
                    # which stage D skips -- the plugin gets built and no chart
                    # is ever created for it.
                    decision["decision"] = "configure"
                    decision["built_by_stage_f"] = True
                    session.publish(
                        "plugin_built",
                        label=f"Built {scaffold.viz_type}",
                        viz_type=scaffold.viz_type,
                        files=len(written.files_written),
                        registered=written.registered,
                    )

                # Regenerate the manifest so the new viz types are known to
                # stage D's validation and to the layout stage.
                _regenerate_registry(session)

                # webpack builds its alias map from package.json when the config
                # is evaluated, so a dependency added mid-session is invisible
                # until the dev server restarts. Opt-in: restarting someone's
                # dev server is not something to do unasked.
                if _config().get("auto_restart_frontend"):
                    from superset.design_to_dashboard import frontend

                    outcome = frontend.restart_dev_server(REPO_ROOT)
                    session.publish(
                        "frontend_restarted",
                        label=(
                            "Frontend restarted — the new chart is live"
                            if outcome.get("restarted")
                            else "Restart your dev server to load the new chart"
                        ),
                        detail=outcome.get("reason"),
                    )
                else:
                    session.publish(
                        "frontend_restart_needed",
                        label="Restart the frontend dev server to load the new chart",
                        detail=(
                            "webpack reads plugin aliases from package.json at "
                            "startup, so a new plugin needs a dev-server restart."
                        ),
                    )

                _reasoning = session.take_thinking()
                session.publish(
                    "stage_complete",
                    stage="F",
                    label="Built custom chart plugins",
                    thinking=_reasoning,
                    summary=", ".join(built),
                    cost=round(total_cost, 4),
                )

            # ---- D: configure ------------------------------------------------
            jobs = [
                d
                for d in plan.final.get("decisions", [])
                if d.get("decision") in d_configure.CONFIGURABLE
            ]
            session.publish(
                "stage_start", stage="D", label=f"Configuring {len(jobs)} charts"
            )

            def _chart_done(ref: str, viz_type: str, ok: bool, done: int) -> None:
                session.publish(
                    "chart_done",
                    label=f"{done}/{len(jobs)} charts configured",
                    ref=ref,
                    viz_type=viz_type,
                    ok=ok,
                )

            charts = d_configure.run_all(
                provider,
                design_analysis,
                binding.final,
                plan.final,
                PROMPTS,
                str(REGISTRY),
                REPO_ROOT,
                on_chart=_chart_done,
            )
            total_cost += sum(c.cost_usd for c in charts)
            failed = [c for c in charts if not c.ok]
            chart_specs = [
                {
                    "ref": c.ref,
                    "region_id": c.region_id,
                    "viz_type": c.viz_type,
                    "spec": c.spec,
                    "problems": c.problems,
                    "error": c.error,
                }
                for c in charts
            ]
            session.artifacts["charts"] = chart_specs
            _reasoning = session.take_thinking()
            session.publish(
                "stage_complete",
                stage="D",
                thinking=_reasoning,
                label="Configured charts",
                summary=f"{len(charts) - len(failed)}/{len(charts)} ready",
                charts=[
                    {"ref": c.ref, "viz_type": c.viz_type, "ok": c.ok} for c in charts
                ],
                cost=round(total_cost, 4),
            )

            # ---- E: layout ---------------------------------------------------
            session.publish("stage_start", stage="E", label="Laying out the dashboard")
            layout, cost = _retry(
                session,
                "Laying out the dashboard",
                2,
                lambda: e_layout.run(
                    provider,
                    design_analysis,
                    plan.final,
                    PROMPTS,
                    on_thinking=_thinking_for("E"),
                ),
            )
            total_cost += cost
            session.artifacts["layout"] = layout
            problems = e_layout.validate(layout, plan.final)
            _reasoning = session.take_thinking()
            session.publish(
                "stage_complete",
                stage="E",
                thinking=_reasoning,
                label="Laid out the dashboard",
                summary=f"{len(layout.get('position_json', {}))} nodes, "
                f"{len(layout.get('adjustments') or [])} adjustments",
                adjustments=layout.get("adjustments") or [],
                problems=problems,
                cost=round(total_cost, 4),
            )
            if problems:
                raise RuntimeError(f"layout failed validation: {problems}")

            # ---- apply -------------------------------------------------------
            session.publish(
                "stage_start", stage="apply", label="Creating the dashboard"
            )
            try:
                # Stage B proposes the datasets a section needs; the applier
                # creates them. C is not asked to echo the specs through --
                # a stage that merely copies data is a stage that can drop it.
                plan_for_apply = dict(plan.final)
                if datasets := binding.final.get("created_datasets"):
                    plan_for_apply["created_datasets"] = datasets

                applied = apply_plan(
                    design_analysis=design_analysis,
                    plan=plan_for_apply,
                    chart_specs=chart_specs,
                    layout=layout,
                    dashboard_title=(design_analysis.get("global") or {}).get("title"),
                )
            except ApplyError as ex:
                raise RuntimeError(str(ex)) from ex

            session.publish(
                "stage_start", stage="verify", label="Checking the dashboard renders"
            )
            from superset.design_to_dashboard.verify import verify as verify_dashboard

            if applied.dashboard_id is None:
                raise RuntimeError("apply succeeded without a dashboard id")
            checks = verify_dashboard(applied.dashboard_id, plan.final, design_analysis)
            session.publish(
                "stage_complete",
                stage="verify",
                label="Checked the dashboard",
                summary=checks.rendering,
                charts=[
                    {
                        "chart_id": c.chart_id,
                        "name": c.slice_name,
                        "viz_type": c.viz_type,
                        "ok": c.ok,
                        "rows": c.rows,
                        "error": c.error,
                    }
                    for c in checks.charts
                ],
                fidelity_notes=checks.fidelity_notes,
            )

            # ---- visual verify: does it look like the design? -------------
            # Report only. `verify` above proves the charts return data; this
            # is the only place anything looks at the result, and it must not
            # turn a working dashboard into a failed run.
            session.publish(
                "stage_start", stage="visual", label="Comparing with your design"
            )
            visual = visual_verify.run(
                provider,
                session.image_paths,
                applied.dashboard_url or "",
                design_analysis,
                plan.final,
                PROMPTS,
                REPO_ROOT,
                session.id,
                on_thinking=_thinking_for("visual"),
            )
            total_cost += visual.cost_usd
            session.publish(
                "stage_complete",
                stage="visual",
                label="Compared with your design",
                summary=(
                    visual.error
                    or visual.blocked
                    or f"{visual.verdict} — {visual.score}/60, "
                    f"{len(visual.findings)} finding(s)"
                ),
                score=visual.score,
                scores=visual.scores,
                verdict=visual.verdict,
                findings=visual.findings,
                screenshot=visual.screenshot_path,
                cost=round(total_cost, 4),
            )

            session.status = "done"
            session.result = {
                "trace_path": str(trace.path_for(session.id, REPO_ROOT)),
                "dashboard_id": applied.dashboard_id,
                "dashboard_url": applied.dashboard_url,
                "charts_created": applied.charts_created,
                "charts_reused": applied.charts_reused,
                "cost_usd": round(total_cost, 4),
                "rendering": checks.rendering,
                "visual_verdict": visual.verdict,
                "visual_score": visual.score,
                "visual_findings": visual.findings,
                "screenshot_path": visual.screenshot_path,
                "all_charts_ok": checks.all_ok,
                "fidelity_notes": checks.fidelity_notes,
            }
            session.publish("done", label="Dashboard created", **session.result)

        except Exception as ex:  # noqa: BLE001 - surfaced to the user, not swallowed
            logger.exception("pipeline failed for session %s", session.id)
            session.status = "failed"
            session.error = str(ex)
            session.publish(
                "error",
                label="Something went wrong",
                detail=str(ex)[:600],
                trace_path=str(trace.path_for(session.id, REPO_ROOT)),
            )
        finally:
            # Every run leaves a trace, including one that failed or was
            # cancelled -- a failed run is precisely the one worth reading.
            # Written last so the terminal event is part of the record.
            trace.write(session, REPO_ROOT)
