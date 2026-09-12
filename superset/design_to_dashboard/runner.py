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

import concurrent.futures
import logging
import pathlib
import sys
import tempfile
import threading
from typing import Any, Callable

from superset.design_to_dashboard import crop, trace, visual_verify

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


class RunCancelledError(Exception):
    """The user declined something the run cannot proceed without."""


def _done_label(checks: Any, visual: Any) -> str:
    """What was built, including the ways it is not what was asked for.

    The dashboard exists and is worth having, so the run is `done` rather than
    failed. But "Dashboard created" was published over a result that already
    recorded two charts returning the wrong data and 43/60 against the design,
    and a headline that omits what the body says is not a summary -- it is the
    reason nobody reads the body.
    """
    caveats = []
    broken = [c for c in getattr(checks, "charts", []) if not c.ok]
    if broken:
        caveats.append(f"{len(broken)} of {len(checks.charts)} charts not right")
    if visual.blocked:
        caveats.append("could not be compared with your design")
    elif visual.verdict and visual.verdict not in {"pass", "unknown"}:
        caveats.append(f"{visual.score}/60 against your design")
    if not caveats:
        return "Dashboard created"
    return "Dashboard created — " + ", ".join(caveats)


def _restart_label(outcome: dict[str, Any]) -> str:
    """What the restart actually achieved, rather than that it happened."""
    if not outcome.get("restarted"):
        return "Restart your dev server to load the new chart"
    if outcome.get("compiled") is False:
        return "Frontend restarted, but a plugin does not compile"
    if outcome.get("compiled") is None:
        return "Frontend restarted — could not confirm it compiled"
    return "Frontend restarted — the new chart is live"


def _plugins_in_errors(
    errors: list[dict[str, str]], directories: dict[str, str]
) -> set[str]:
    """Which generated plugins the compiler complained about."""
    blamed = set()
    for error in errors:
        path = error.get("file") or ""
        for viz_type, directory in directories.items():
            leaf = directory.rsplit("/", 1)[-1]
            if leaf and leaf in path:
                blamed.add(viz_type)
    return blamed


def _repair_broken_plugins(  # noqa: C901
    session: Any,
    outcome: dict[str, Any],
    scaffolds: dict[str, Any],
    by_type: dict[str, list[dict[str, Any]]],
    region_for: Callable[[str], dict[str, Any]],
    binding_for: Callable[[str], dict[str, Any]],
    plan: dict[str, Any],
    provider: Any,
    tag: str,
    crops_dir: Any,
    design_analysis: dict[str, Any],
) -> dict[str, Any]:
    """Ask the author of a plugin that did not compile to fix it, once.

    The checks stage F runs are regex over the scaffold's text: they catch a
    wrong import and cannot catch a property invented on a type. Only the
    compiler sees those -- and it already did, into a log nothing read. Two
    plugins shipped that never compiled, which leaves their charts rendering
    "Empty query?" on a dashboard the run called finished.

    One pass, because a compiler error names the file, the line and the rule;
    an author that cannot use that will not do better with a third telling.
    """
    from superset.design_to_dashboard import frontend, plugin_writer
    from superset.design_to_dashboard.stages import f_scaffold

    directories = {
        viz_type: (scaffold.scaffold or {}).get("directory") or ""
        for viz_type, scaffold in scaffolds.items()
        if scaffold.ok
    }
    blamed = _plugins_in_errors(outcome.get("errors") or [], directories)
    if not blamed:
        # The build is broken by something this run did not write.
        return outcome

    session.publish(
        "plugin_repair",
        label=f"{len(blamed)} plugin(s) did not compile — fixing",
        detail=", ".join(sorted(blamed)),
        viz_types=sorted(blamed),
    )
    repaired = []
    for viz_type in sorted(blamed):
        decision = by_type[viz_type][0]
        region_id = decision.get("region_id", "?")
        leaf = directories[viz_type].rsplit("/", 1)[-1]
        mine = [e for e in outcome.get("errors") or [] if leaf in (e.get("file") or "")]
        try:
            retry = f_scaffold.run_one(
                provider,
                region_for(region_id),
                binding_for(region_id),
                decision,
                plan.get("design_system", {}),
                PROMPTS,
                REPO_ROOT,
                set(),
                tag=tag,
                region_image=crop.region_crop(
                    session.image_paths,
                    region_for(region_id),
                    crops_dir,
                ),
                children=f_scaffold.resolve_children(
                    decision, plan.get("decisions", [])
                ),
                build_errors=mine,
            )
        except Exception:  # noqa: BLE001 - a failed repair leaves the first try
            logger.exception("repair of %s failed", viz_type)
            continue
        if not retry.ok or retry.scaffold is None:
            logger.info("repair of %s still invalid: %s", viz_type, retry.problems)
            continue
        plugin_writer.write(retry.scaffold, REPO_ROOT)
        repaired.append(viz_type)

    if not repaired:
        return outcome
    session.publish(
        "plugin_repaired",
        label=f"Rewrote {len(repaired)} plugin(s) — rebuilding",
        detail=", ".join(repaired),
    )
    return frontend.restart_dev_server(REPO_ROOT)


def _photograph_new_plugins(session: Any, plan: dict[str, Any]) -> None:
    """Replace each new plugin's placeholder with a picture of itself.

    A generated plugin ships no illustration, so `plugin_writer` copies in a
    placeholder and every one of them wears the same image. Stage C chooses
    between plugins by looking at those images, which means the reuse it is
    told to prefer is decided on no evidence at all.

    The charts exist for the first time only now, after apply, so this is the
    earliest moment a generated plugin can be photographed. It does nothing for
    the run that built it -- it is what makes the *next* run's reuse real, and
    a plugin costs eight to ten minutes to build twice.

    Best-effort throughout: a dashboard that renders is worth more than a
    picture of it, so nothing here may fail the run.
    """
    from superset.design_to_dashboard import thumbnails

    viz_types = {
        d.get("viz_type")
        for d in plan.get("decisions", [])
        if d.get("decision") == "new_plugin" and d.get("viz_type")
    }
    if not viz_types:
        return
    try:
        slice_ids = thumbnails.charts_by_viz_type(viz_types)
        rendered = thumbnails.render(
            slice_ids, REPO_ROOT / "design-to-dashboard" / "fixtures" / "thumbnails"
        )
        if not rendered:
            return
        from superset.design_to_dashboard.registry import load as load_registry

        adopted = thumbnails.adopt(rendered, load_registry(str(REGISTRY)))
        session.publish(
            "thumbnails_captured",
            label=f"Photographed {len(adopted)} new plugin(s)",
            detail=", ".join(adopted),
            viz_types=adopted,
        )
    except Exception:  # noqa: BLE001 - a missing picture never fails a run
        logger.exception("could not photograph the new plugins")


def _describe_dataset(spec: dict[str, Any]) -> str:
    """One line naming a dataset and what it costs the user to accept."""
    name = spec.get("name", "?")
    regions = len(spec.get("region_ids") or [])
    if spec.get("kind") == "placeholder":
        return (
            f"{name} — {len(spec.get('rows') or [])} invented row(s) written as a "
            f"real table, serving {regions} section(s). {spec.get('reason') or ''}"
        ).strip()
    return (
        f"{name} — a saved query over data you already have, serving "
        f"{regions} section(s). {spec.get('reason') or ''}"
    ).strip()


def gate_datasets(session: Any, specs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Decide which proposed datasets this run may create.

    The two kinds cost the user very differently, so they are not asked about
    the same way.

    A ``derived`` dataset is a saved SELECT over tables the user already has:
    nothing is written, and the numbers are real. Asking permission buys
    nothing they can act on -- it is the same query the chart would run anyway
    -- so it is created and announced rather than gated.

    A ``placeholder`` both invents the numbers and writes a real table into the
    warehouse, so it is always put to the user first. Declining ends the run:
    every section that needed one has no data, and a dashboard of empty cards
    is not a smaller version of what was asked for.
    """
    derived = [s for s in specs if s.get("kind") == "derived"]
    placeholders = [s for s in specs if s.get("kind") == "placeholder"]

    if derived:
        session.publish(
            "datasets_planned",
            label=f"Building {len(derived)} dataset(s) from your existing data",
            detail="; ".join(_describe_dataset(s) for s in derived),
            datasets=derived,
        )
    if not placeholders:
        return derived

    answer = session.ask(
        "datasets",
        {
            "label": (
                f"{len(placeholders)} section(s) need data no dataset here holds. "
                "I can create sample tables so the dashboard is real and "
                "working, but every number in them is read off the design, not "
                "your data — someone must repoint these charts before anyone "
                "trusts the figures."
            ),
            "datasets": placeholders,
            "detail": "; ".join(_describe_dataset(s) for s in placeholders),
            "options": [
                "Create the sample tables — clearly marked to repoint later",
                "Stop, and let me point you at the real data",
            ],
        },
    )
    if not answer.get("approved"):
        raise RunCancelledError(
            "no sample data was created. Point me at a database holding this "
            "data and run it again."
        )
    return derived + placeholders


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
# Plugin generation is the longest stage: eight to ten minutes per plugin, and
# each call is independent. Four at a time keeps a six-plugin design near the
# cost of one rather than six, without opening more concurrent model calls than
# the account's rate limits comfortably allow.
F_MAX_WORKERS = 4
# How many times stage C may be asked again with its problems in hand.
C_MAX_REPLANS = 2
# How many times the user may send the plan back with a reason. Two rounds is
# a conversation; more is a negotiation the user is better off having by
# editing the dashboard afterwards.
PLAN_FEEDBACK_ROUNDS = 2

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


def _stage_a_summary(design_analysis: dict[str, Any], images: list[str]) -> str:
    """One line saying what was read, and from how many images."""
    regions = len(design_analysis.get("regions", []))
    if len(images) < 2:
        return f"{regions} regions found"
    kind = ((design_analysis.get("global") or {}).get("image_set") or {}).get("kind")
    return f"{regions} regions found across {len(images)} images ({kind})"


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
                a_decompose,
                b_bind,
                c_resolve,
                clarify,
                d_configure,
                e_layout,
                f_scaffold,
            )

            # One provider per stage, built on first use: the stages ask for
            # different work, and `stage_models` lets a schema-driven stage run
            # on a smaller model than one that has to exercise judgment.
            _provider_cache: dict[str, Any] = {}

            def provider_for(stage: str) -> Any:
                """The provider for a stage. **Request thread only.**

                Building one reads `current_app.config`, and Flask's app
                context is thread-local: called from a worker thread this
                raises "Working outside of application context". A stage that
                fans out must resolve its provider before starting the pool.
                """
                if stage not in _provider_cache:
                    _provider_cache[stage] = get_llm_provider(stage)
                return _provider_cache[stage]

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
            # Parsing happens inside the retried call, not after it: an
            # unparseable reply is exactly as transient as a failed one, and
            # this is the longest single call in the pipeline to lose.
            design_analysis, stage_a_cost = _retry(
                session,
                "Reading the design",
                2,
                lambda: a_decompose.run(
                    provider_for("A"),
                    session.requirement,
                    session.image_paths,
                    PROMPTS,
                    on_thinking=_thinking_for("A"),
                    registry_path=str(REGISTRY),
                ),
            )
            total_cost += stage_a_cost
            session.artifacts["design_analysis"] = design_analysis

            # Unrelated designs must not be welded into one dashboard. Stage A
            # can see that the images share no chrome; nothing downstream can,
            # and it would silently merge them.
            if design_analysis.get("status") == "separate_designs":
                raise RuntimeError(
                    "these images look like different dashboards, not one: "
                    f"{design_analysis.get('notes') or 'no shared title or chrome'}. "
                    "Run them separately."
                )
            if design_analysis.get("status") == "unreadable":
                raise RuntimeError(
                    f"the design could not be read: {design_analysis.get('notes')}"
                )

            # Stop here rather than re-asking. Every later stage joins on these
            # ids and boxes, so a malformed reading corrupts the whole run --
            # and this is the cheapest point at which to say so. A re-ask would
            # cost another eight-minute call without telling the model what was
            # wrong, so the run fails and the problems are reported instead.
            if problems := a_decompose.validate(
                design_analysis, chart_types(load_registry(str(REGISTRY)))
            ):
                logger.error("stage A validation: %s", "; ".join(problems))
                session.publish(
                    "validation_failed",
                    stage="A",
                    label=f"The design reading has {len(problems)} problem(s)",
                    detail="; ".join(problems)[:1000],
                    problems=problems,
                )
                raise RuntimeError(
                    f"the design reading failed validation: {'; '.join(problems)}"
                )

            _reasoning = session.take_thinking()
            session.publish(
                "stage_complete",
                stage="A",
                thinking=_reasoning,
                label="Read the design",
                summary=_stage_a_summary(design_analysis, session.image_paths),
                regions=design_analysis.get("regions", []),
                cost=round(total_cost, 4),
            )

            # ---- B: bind -----------------------------------------------------
            session.publish("stage_start", stage="B", label="Finding your data")

            def _tool_progress(
                tool: str, arguments: dict[str, Any], error: str | None = None
            ) -> None:
                session.publish(
                    "tool_call", tool=tool, arguments=arguments, error=error
                )

            binding = b_bind.run(
                provider_for("B"),
                gateway,
                design_analysis,
                PROMPTS,
                on_progress=_tool_progress,
                on_thinking=_thinking_for("B"),
            )
            total_cost += binding.cost_usd
            session.artifacts["binding_set"] = binding.final

            # Warn rather than halt. Unlike stage A, whose ids nothing can
            # proceed without, a flawed binding still produces a dashboard --
            # and the user is about to be asked to approve the plan anyway, so
            # the problems are more useful attached to that than as a dead run.
            if problems := b_bind.validate(binding.final, design_analysis):
                logger.warning("stage B validation: %s", "; ".join(problems))
                session.publish(
                    "validation_failed",
                    stage="B",
                    label=f"{len(problems)} problem(s) with the data binding",
                    detail="; ".join(problems)[:1000],
                    problems=problems,
                )
            # Settled before clarify runs, so it neither spends a question on
            # this nor asks something the orchestrator has already decided.
            approved_datasets = gate_datasets(
                session, binding.final.get("created_datasets") or []
            )

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
                provider_for("clarify"),
                design_analysis,
                binding.final,
                PROMPTS,
                on_thinking=_thinking_for("clarify"),
            )
            total_cost += clarify_cost
            # Two producers, two schemas: stage B emits a blocking question
            # per `unavailable` binding (`why_blocking`, no `id`), clarify emits
            # its own (`why_it_matters`, with an `id`). Only clarify's were
            # normalised, inside `clarify.run`, so a stage B question reached
            # the UI with `id: None` and its answer landed under "undefined".
            # Normalising the merged list is the only place that covers both.
            merged = {
                "questions": list(binding_questions)
                + list(clarification.get("questions") or [])
            }
            if repairs := clarify.normalise_questions(
                merged, clarify.question_budget(design_analysis)
            ):
                logger.info("clarify questions repaired: %s", "; ".join(repairs))
            questions = merged["questions"]
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
            # Stage C plans against the datasets that will actually exist, not
            # the ones stage B wished for.
            binding_with_answers["created_datasets"] = approved_datasets
            if answers:
                binding_with_answers["user_answers"] = answers

            def _resolve(extra: dict[str, Any] | None = None) -> Any:
                """One stage C attempt. `extra` is what this attempt knows that
                the last one did not -- validation problems, or the user's own
                words about the plan."""
                nonlocal total_cost
                result = c_resolve.run(
                    provider_for("C"),
                    gateway,
                    design_analysis,
                    {**binding_with_answers, **(extra or {})},
                    PROMPTS,
                    str(REGISTRY),
                    on_progress=_tool_progress,
                    on_thinking=_thinking_for("C"),
                    thumbnail_sheet=str(THUMBNAIL_SHEET)
                    if THUMBNAIL_SHEET.exists()
                    else None,
                )
                total_cost += result.cost_usd
                session.artifacts["plan"] = result.final
                return result

            plan = _resolve()

            # Stage C may say what it could not decide rather than guessing.
            # One round: it is re-run with the answers and must then decide,
            # because a stage that can keep asking will, and the user did not
            # come here to be interviewed.
            if needs := [
                n for n in plan.final.get("needs") or [] if isinstance(n, dict)
            ]:
                merged_needs = {"questions": needs}
                clarify.normalise_questions(
                    merged_needs, clarify.question_budget(design_analysis)
                )
                session.publish(
                    "stage_start",
                    stage="C",
                    label=f"{len(merged_needs['questions'])} thing(s) I need to know",
                )
                need_answers = session.ask(
                    "questions",
                    {
                        "label": "I can't decide these without you",
                        "questions": merged_needs["questions"],
                    },
                )
                binding_with_answers["user_answers"] = {
                    **c_resolve.replies_of(binding_with_answers.get("user_answers")),
                    **c_resolve.replies_of(need_answers),
                }
                plan = _resolve(
                    {"answers_to_your_questions": merged_needs["questions"]}
                )

            # Stage C's validator existed and was never called from here -- only
            # from the smoke test -- so every check written for it was dead in
            # the real pipeline. Its findings are recoverable by asking C again
            # with the problems in hand, which is cheaper than a plan that
            # builds a plugin per heading.
            # Two re-plans, not one: the first attempt is often a rule C
            # misapplied, and a second slip on something else should not throw
            # away the twenty minutes A and B already spent.
            for _attempt in range(C_MAX_REPLANS):
                problems = c_resolve.validate(
                    plan.final, design_analysis, binding_with_answers, str(REGISTRY)
                )
                if not problems:
                    break
                logger.info("stage C validation: %s", "; ".join(problems))
                session.publish(
                    "retry",
                    stage="C",
                    label=f"Re-planning: {len(problems)} problem(s) to fix",
                    detail="; ".join(problems)[:600],
                )
                plan = _resolve({"validation_problems": problems})
            else:
                # Out of attempts. The plan is published anyway, with what is
                # still wrong with it attached: a plan you can look at and
                # reject beats a run that dies holding one.
                still_wrong = c_resolve.validate(
                    plan.final, design_analysis, binding_with_answers, str(REGISTRY)
                )
                if still_wrong:
                    logger.warning(
                        "stage C still invalid after %d re-plans: %s",
                        C_MAX_REPLANS,
                        "; ".join(still_wrong),
                    )
                    session.publish(
                        "validation_failed",
                        stage="C",
                        label=(
                            f"{len(still_wrong)} problem(s) I could not fix — "
                            "review the plan before approving"
                        ),
                        detail="; ".join(still_wrong)[:1000],
                        problems=still_wrong,
                    )
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
            # Rejecting with a reason re-plans rather than ending the run. The
            # feedback used to be collected by the UI, sent to the server, and
            # used as the label on the cancellation -- so the one moment the
            # user has the most context to offer was the one moment nothing
            # listened. Stage C already knows how to be told what is wrong with
            # its plan; this is the same channel, with a person on the other
            # end of it.
            for attempt in range(PLAN_FEEDBACK_ROUNDS + 1):
                approval = session.ask(
                    "plan",
                    {
                        "label": "Here is what I will build — approve to continue",
                        "plan": plan.final.get("plan_for_review") or [],
                        "decisions": plan.final.get("decisions", []),
                        "counts": plan.final.get("counts", {}),
                        # Creating a dataset writes to the user's database, so
                        # it belongs in what they approve, not only in the
                        # answers.
                        "datasets": approved_datasets,
                        "can_revise": attempt < PLAN_FEEDBACK_ROUNDS,
                    },
                )
                if approval.get("approved"):
                    break
                feedback = str(approval.get("feedback") or "").strip()
                if not feedback:
                    session.status = "cancelled"
                    session.publish(
                        "cancelled", label="Plan rejected — nothing was created"
                    )
                    return
                if attempt >= PLAN_FEEDBACK_ROUNDS:
                    session.status = "cancelled"
                    session.publish(
                        "cancelled",
                        label="Plan still not right — nothing was created",
                        detail=feedback,
                    )
                    return
                session.publish(
                    "retry",
                    stage="C",
                    label="Re-planning with your feedback",
                    detail=feedback[:600],
                )
                plan = _resolve({"plan_feedback": feedback})
                counts = plan.final.get("counts", {})
                session.publish(
                    "stage_complete",
                    stage="C",
                    label="Revised the plan",
                    summary=plan.final.get("summary") or "",
                    decisions=plan.final.get("decisions", []),
                    counts=counts,
                    cost=round(total_cost, 4),
                )

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
                tag = f_scaffold.run_tag(session.id)
                crops_dir = pathlib.Path(tempfile.gettempdir()) / "d2d" / session.id
                crops_dir = crops_dir / "crops"

                # Several regions can need the same plugin -- three identical
                # provider cards are three decisions and one plugin. Stage C
                # names each plugin, so the distinct set is known before any
                # generation starts and each one is built exactly once.
                by_type: dict[str, list[dict[str, Any]]] = {}
                for decision in new_plugin_decisions:
                    by_type.setdefault(decision.get("viz_type") or "", []).append(
                        decision
                    )
                for viz_type, group in by_type.items():
                    for extra in group[1:]:
                        session.publish(
                            "plugin_built",
                            label=f"Reused {viz_type} for {extra.get('region_id')}",
                            viz_type=viz_type,
                            reused=True,
                        )

                f_provider = provider_for("F")

                def _region_for(region_id: str) -> dict[str, Any]:
                    """The region a plugin decision describes.

                    A container's charts are resolved under `r07:1`,
                    `r07:2` (`B_bind_data.md`), and stage A's list has no such
                    ids -- so a plain lookup returned {} and the plugin for a
                    child was generated with no description of what it draws
                    and no image, from its decision alone.
                    """
                    return regions.get(region_id) or regions.get(
                        region_id.split(":")[0], {}
                    )

                def _binding_for(region_id: str) -> dict[str, Any]:
                    """The data behind a plugin, matched in either direction.

                    A composing decision names the frame itself, which stage B
                    never bound -- it bound the pieces. Looked up directly, the
                    wrapper was written with no dataset and no column names.
                    """
                    if exact := bindings.get(region_id):
                        return exact
                    parent = region_id.split(":")[0]
                    if inherited := bindings.get(parent):
                        return inherited
                    for key in sorted(bindings):
                        if key.split(":")[0] == parent:
                            return bindings[key]
                    return {}

                def _build(viz_type: str, decision: dict[str, Any]) -> Any:
                    region_id = decision.get("region_id", "?")
                    # F is a single-shot call like A and E, and equally prone to
                    # a transient failure -- losing a long run to one is not
                    # acceptable.
                    return viz_type, _retry(
                        session,
                        f"Building the plugin for {region_id}",
                        2,
                        lambda: f_scaffold.run_one(
                            f_provider,
                            _region_for(region_id),
                            _binding_for(region_id),
                            decision,
                            plan.final.get("design_system", {}),
                            PROMPTS,
                            REPO_ROOT,
                            known,
                            tag=tag,
                            on_thinking=_thinking_for("F"),
                            region_image=crop.region_crop(
                                session.image_paths,
                                _region_for(region_id),
                                crops_dir,
                            ),
                            # Refs mean nothing to the author of a wrapper.
                            # Resolved first, so it knows what it hosts before
                            # it writes a line of it.
                            children=f_scaffold.resolve_children(
                                decision, plan.final.get("decisions", [])
                            ),
                        ),
                    )

                # Generation is the slow part -- eight to ten minutes each --
                # and each call is independent, so they run together. Writing is
                # not: every plugin patches the same package.json and
                # setupPluginsExtra.ts, and concurrent read-modify-write on
                # those loses entries.
                scaffolds: dict[str, Any] = {}
                with concurrent.futures.ThreadPoolExecutor(
                    max_workers=min(len(by_type), F_MAX_WORKERS)
                ) as pool:
                    futures = [
                        pool.submit(_build, viz_type, group[0])
                        for viz_type, group in by_type.items()
                    ]
                    for future in concurrent.futures.as_completed(futures):
                        viz_type, scaffold = future.result()
                        scaffolds[viz_type] = scaffold
                        total_cost += scaffold.cost_usd

                # One bad scaffold used to raise here, before anything was
                # written -- an hour of generation discarded because the last
                # plugin of fifteen named its package wrong. The ones that
                # generated cleanly are kept, and the sections that lost their
                # plugin are dropped the way stage C drops a section it cannot
                # build: the dashboard arrives incomplete rather than not at all.
                failed_plugins: list[str] = []
                for viz_type, group in by_type.items():
                    scaffold = scaffolds[viz_type]
                    if not scaffold.ok:
                        detail = str(scaffold.error or scaffold.problems)
                        affected = ", ".join(str(d.get("region_id")) for d in group)
                        failed_plugins.append(f"{viz_type} ({affected}): {detail}")
                        for decision in group:
                            decision["decision"] = "drop"
                            decision["fidelity_loss"] = (
                                f"the {viz_type} plugin could not be generated, "
                                "so this section is missing from the dashboard"
                            )
                        session.publish(
                            "plugin_failed",
                            label=f"Could not build {viz_type} — dropping {affected}",
                            viz_type=viz_type,
                            detail=detail[:400],
                        )
                        continue
                    written = plugin_writer.write(scaffold.scaffold, REPO_ROOT)
                    built.append(scaffold.viz_type or "?")
                    for decision in group:
                        decision["viz_type"] = scaffold.viz_type
                        if scaffold.scaffold.get("params_hint"):
                            # Stage D needs params for a control panel that did
                            # not exist when the registry manifest was generated.
                            decision["params_hint"] = scaffold.scaffold["params_hint"]
                        # The plugin now exists, so these regions are
                        # configurable like any other. Without this the decision
                        # stays "new_plugin", which stage D skips -- the plugin
                        # gets built and no chart is ever created for it.
                        decision["decision"] = "configure"
                        decision["built_by_stage_f"] = True
                    session.publish(
                        "plugin_built",
                        label=f"Built {scaffold.viz_type}",
                        viz_type=scaffold.viz_type,
                        files=len(written.files_written),
                        registered=written.registered,
                    )

                if failed_plugins and not built:
                    raise RuntimeError(
                        "every plugin failed to build: " + "; ".join(failed_plugins)
                    )

                # Linked once, after every plugin has landed: `plugin_writer`
                # registers each import as it writes, and webpack resolves those
                # through node_modules symlinks that only `npm install` creates.
                # Doing it per plugin left the dev server broken for the rest of
                # the stage.
                from superset.design_to_dashboard import frontend

                frontend.link_plugins(REPO_ROOT)

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
                    if outcome.get("compiled") is False:
                        outcome = _repair_broken_plugins(
                            session,
                            outcome,
                            scaffolds,
                            by_type,
                            _region_for,
                            _binding_for,
                            plan.final,
                            f_provider,
                            tag,
                            crops_dir,
                            design_analysis,
                        )
                    session.publish(
                        "frontend_restarted",
                        label=_restart_label(outcome),
                        detail=outcome.get("reason")
                        or "; ".join(
                            f"{e['file']}: {e['detail'][:120]}"
                            for e in outcome.get("errors") or []
                        )
                        or None,
                        compiled=outcome.get("compiled"),
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
                provider_for("D"),
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
                # Carries what was wrong, not just how many: the count alone
                # named neither which charts nor why, and the per-chart detail
                # lived only in memory.
                charts=[
                    {
                        "ref": c.ref,
                        "region_id": c.region_id,
                        "viz_type": c.viz_type,
                        "ok": c.ok,
                        "problems": c.problems,
                        "error": c.error,
                        "attempts": c.attempts,
                    }
                    for c in charts
                ],
                cost=round(total_cost, 4),
            )
            if failed:
                logger.warning(
                    "stage D: %d chart(s) still had problems after %d attempt(s): %s",
                    len(failed),
                    d_configure.MAX_ATTEMPTS,
                    "; ".join(
                        f"{c.ref}: {c.error or '; '.join(c.problems)}" for c in failed
                    )[:600],
                )

            # ---- E: layout ---------------------------------------------------
            session.publish("stage_start", stage="E", label="Laying out the dashboard")
            layout, cost = _retry(
                session,
                "Laying out the dashboard",
                2,
                lambda: e_layout.run(
                    provider_for("E"),
                    design_analysis,
                    plan.final,
                    PROMPTS,
                    on_thinking=_thinking_for("E"),
                    image_paths=session.image_paths,
                    user_answers=answers or None,
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
                # Only what the user agreed to, never stage B's raw proposal:
                # the specs it wrote are a request, and `gate_datasets` is what
                # answered it.
                plan_for_apply["created_datasets"] = approved_datasets

                applied = apply_plan(
                    design_analysis=design_analysis,
                    plan=plan_for_apply,
                    chart_specs=chart_specs,
                    layout=layout,
                    dashboard_title=(design_analysis.get("global") or {}).get("title"),
                )
            except ApplyError as ex:
                raise RuntimeError(str(ex)) from ex

            _photograph_new_plugins(session, plan.final)

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
                        "note": c.note,
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
                provider_for("G"),
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
                "visual_scores": visual.scores,
                "visual_summary": visual.summary,
                "visual_problems": visual.problems,
                "visual_findings": visual.findings,
                "screenshot_path": visual.screenshot_path,
                "all_charts_ok": checks.all_ok,
                "fidelity_notes": checks.fidelity_notes,
            }
            session.publish("done", label=_done_label(checks, visual), **session.result)

        except RunCancelledError as ex:
            # A declined proposal is an answer, not a fault: the run stops with
            # nothing created and nothing to apologise for.
            logger.info("session %s cancelled: %s", session.id, ex)
            session.status = "cancelled"
            session.publish(
                "cancelled",
                label="Stopped — nothing was created",
                detail=str(ex),
            )
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
