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
import threading
from typing import Any, Callable

from superset.design_to_dashboard import (
    chrome,
    crop,
    plugin_review,
    trace,
    visual_verify,
)

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
    from superset.design_to_dashboard.stages import c_resolve, f_scaffold

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
                c_resolve.design_system(plan, design_analysis),
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
        try:
            plugin_writer.write(retry.scaffold, REPO_ROOT, retry.plugin, decision)
        except Exception:  # noqa: BLE001 - the first attempt stays on disk
            logger.exception("could not write the repair of %s", viz_type)
            continue
        # The repair supersedes the attempt that did not compile. Only its
        # files used to be kept, so a later removal addressed the superseded
        # attempt, the repair's own generation never reached the run's cost,
        # and stage D was handed the first attempt's `params_hint` and told
        # it was authoritative -- for controls the repair may have renamed.
        scaffolds[viz_type].scaffold = retry.scaffold
        scaffolds[viz_type].plugin = retry.plugin
        scaffolds[viz_type].cost_usd += retry.cost_usd
        if hint := retry.scaffold.get("params_hint"):
            for sibling in by_type[viz_type]:
                sibling["params_hint"] = hint
        repaired.append(viz_type)

    if not repaired:
        return outcome
    session.publish(
        "plugin_repaired",
        label=f"Rewrote {len(repaired)} plugin(s) — rechecking",
        detail=", ".join(repaired),
    )
    # Re-link first: a repair can rename the package, and an unlinked package
    # fails to resolve in a way that reads as the author's fault rather than
    # as a missing symlink.
    frontend.link_plugins(REPO_ROOT)
    return frontend.typecheck(REPO_ROOT)


# How many times a plugin that did not compile is handed its own errors and
# asked again. A compiler error names the file, the line and the rule, so the
# first pass clears most of them; a second catches the case where fixing one
# fault exposed another. Beyond that the author is guessing, and the plugin is
# removed instead.
REPAIR_ROUNDS = 2


def _typecheck_and_quarantine(  # noqa: C901
    session: Any,
    scaffolds: dict[str, Any],
    by_type: dict[str, list[dict[str, Any]]],
    region_for: Callable[[str], dict[str, Any]],
    binding_for: Callable[[str], dict[str, Any]],
    plan: dict[str, Any],
    provider: Any,
    tag: str,
    crops_dir: Any,
    design_analysis: dict[str, Any],
    built: list[str],
) -> float:
    """Returns what the repair generations cost, for the run's total."""
    """Compile what was written, repair what failed, remove what cannot be.

    The guarantee this exists to make is that nobody opens the dashboard to a
    frontend that does not build. A generated plugin is registered globally,
    so one that does not compile takes down every chart on the page and not
    just its own section -- the run would otherwise report success while the
    dev server served a compile error.

    So a plugin gets ``REPAIR_ROUNDS`` attempts with the compiler's own output
    in hand, and if it still fails it is deleted, unregistered, and its
    sections are dropped the way stage C drops a section it cannot build. An
    incomplete dashboard is a worse outcome than a complete one and a far
    better outcome than a broken one.
    """
    from superset.design_to_dashboard import frontend, plugin_writer

    before = sum(s.cost_usd for s in scaffolds.values())
    verdict = frontend.typecheck(REPO_ROOT)
    for _round in range(REPAIR_ROUNDS):
        if verdict.get("compiled") is not False:
            break
        session.publish(
            "typecheck_failed",
            label=f"{len(verdict.get('errors') or [])} type error(s) — fixing",
            detail="; ".join(
                f"{e['file']}: {e['detail'][:120]}"
                for e in (verdict.get("errors") or [])[:6]
            ),
        )
        repaired = _repair_broken_plugins(
            session,
            verdict,
            scaffolds,
            by_type,
            region_for,
            binding_for,
            plan,
            provider,
            tag,
            crops_dir,
            design_analysis,
        )
        # `_repair_broken_plugins` re-checks only when it rewrote something.
        # When it returns the verdict it was given, nothing changed and
        # another round would ask the same question of the same files.
        if repaired is verdict:
            break
        verdict = repaired

    if verdict.get("compiled") is not False:
        session.publish(
            "typecheck_passed",
            label="The generated plugins compile",
            compiled=verdict.get("compiled"),
            detail=verdict.get("reason"),
        )
        return sum(s.cost_usd for s in scaffolds.values()) - before

    # Out of repair attempts. Everything still named in an error goes.
    directories = {
        viz_type: (scaffold.scaffold or {}).get("directory") or ""
        for viz_type, scaffold in scaffolds.items()
        if scaffold.ok
    }
    doomed = _plugins_in_errors(verdict.get("errors") or [], directories)
    if not doomed:
        # The build is broken by something this run did not write. Removing a
        # working plugin would not fix it and would lose a section for no
        # reason, so the fault is reported and left where it is.
        session.publish(
            "typecheck_failed",
            label="The frontend does not compile, but no generated plugin is at fault",
            detail="; ".join(
                f"{e['file']}: {e['detail'][:120]}"
                for e in (verdict.get("errors") or [])[:6]
            ),
        )
        return sum(s.cost_usd for s in scaffolds.values()) - before

    for viz_type in sorted(doomed):
        scaffold = scaffolds[viz_type]
        group = by_type.get(viz_type) or []
        affected = ", ".join(str(d.get("region_id")) for d in group)
        plugin_writer.remove(scaffold.scaffold or {}, REPO_ROOT)
        if viz_type in built:
            built.remove(viz_type)
        for decision in group:
            decision["decision"] = "drop"
            decision["fidelity_loss"] = (
                f"the {viz_type} plugin did not compile after "
                f"{REPAIR_ROUNDS} repair attempt(s), so this section is missing"
            )
        session.publish(
            "plugin_failed",
            label=f"{viz_type} would not compile — removed, dropping {affected}",
            viz_type=viz_type,
            detail="; ".join(
                e["detail"][:120]
                for e in (verdict.get("errors") or [])
                if directories.get(viz_type, "").rsplit("/", 1)[-1]
                in (e.get("file") or "")
            )[:400],
        )

    # The removals changed package.json, so the links have to follow before
    # anything else reads node_modules.
    frontend.link_plugins(REPO_ROOT)
    final = frontend.typecheck(REPO_ROOT)
    session.publish(
        "typecheck_passed"
        if final.get("compiled") is not False
        else "typecheck_failed",
        label=(
            "The frontend compiles with the failed plugin(s) removed"
            if final.get("compiled") is not False
            else "The frontend still does not compile after removing the plugin(s)"
        ),
        compiled=final.get("compiled"),
    )
    return sum(s.cost_usd for s in scaffolds.values()) - before


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
        # `built_by_stage_f`, not `decision == "new_plugin"`: the F block
        # rewrites a built plugin's decision to "configure" before this runs,
        # so the old filter matched nothing and every generated plugin kept
        # the placeholder thumbnail this function exists to replace.
        if d.get("built_by_stage_f") and d.get("viz_type")
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
    if spec.get("kind") in {"fact", "shared"}:
        return (
            f"{name} — {len(spec.get('rows') or [])} invented row(s) written as a "
            f"real table, serving {regions} section(s). {spec.get('reason') or ''}"
        ).strip()
    return (
        f"{name} — a saved query over data you already have, serving "
        f"{regions} section(s). {spec.get('reason') or ''}"
    ).strip()


def announce_datasets(session: Any, binding_set: dict[str, Any]) -> None:
    """Tell the user what stage B built.

    Nothing is gated here any more. Stage B creates its own tables so it can
    run a view's SQL against them and catch a query that does not execute --
    which means by the time this runs, the datasets exist. Asking permission
    after the fact would be theatre.

    What is left is worth saying plainly: every number in these tables was read
    off the design, not out of the user's warehouse, and someone has to repoint
    these charts before anyone trusts a figure on the dashboard.
    """
    tables = binding_set.get("fact_tables") or []
    views = binding_set.get("views") or []
    if not tables and not views:
        return
    rows = sum(int(t.get("row_count") or 0) for t in tables if isinstance(t, dict))
    session.publish(
        "datasets_created",
        label=(
            f"Built {len(tables)} table(s) and {len(views)} view(s) in the d2d "
            "schema — the numbers in them come from the design, not your data"
        ),
        detail="; ".join(
            f"{t.get('name', '?')} — {t.get('grain') or 'no grain given'}, "
            f"{t.get('row_count', 0)} row(s)"
            for t in tables
            if isinstance(t, dict)
        ),
        tables=tables,
        views=views,
        total_rows=rows,
    )


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
C_MAX_REPLANS = 3
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

            from superset.design_to_dashboard import plugin_writer, questions
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
                    provider = get_llm_provider(stage)
                    if _config().get("record_calls"):
                        # Wrapped rather than recorded stage by stage: every
                        # stage reaches the model through the provider, so this
                        # also catches the tool loop's intermediate turns and
                        # F's per-region calls, which the runner never sees.
                        from superset.design_to_dashboard.llm.recorder import (
                            RecordingProvider,
                        )

                        provider = RecordingProvider(
                            provider, stage, session.id, REPO_ROOT
                        )
                    _provider_cache[stage] = provider
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
                image_paths=session.image_paths,
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
            # Reported, not gated: stage B has already created these, which is
            # what let it validate every view against a real table.
            announce_datasets(session, binding.final)

            _reasoning = session.take_thinking()
            session.publish(
                "stage_complete",
                stage="B",
                thinking=_reasoning,
                label="Built your data",
                # The old contract's `datasets_used` is gone; the new one
                # reports what was created. Reading the removed key left this
                # summary silently empty on every run.
                summary=", ".join(
                    str(dataset.get("name") or "?")
                    for group in ("fact_tables", "views")
                    for dataset in binding.final.get(group) or []
                )
                or "bound",
                bindings=binding.final.get("bindings", []),
                cost=round(total_cost, 4),
            )

            # Nothing is asked before stage C any more. A question is only
            # worth the user's attention once someone knows what it changes,
            # and until C has resolved the page nobody does -- the old stage
            # asked "fidelity or reuse?" in the abstract, where C can ask
            # whether this table is worth a plugin because stock ones cannot
            # draw a bar in a cell. Stage B no longer blocks either: it builds
            # the data rather than reporting that it cannot find any.
            answers: dict[str, Any] = {}

            # ---- C: resolve --------------------------------------------------
            session.publish("stage_start", stage="C", label="Choosing chart types")
            binding_with_answers = dict(binding.final)
            # Stage C plans against the datasets that will actually exist, not
            # the ones stage B wished for.
            binding_with_answers["created_datasets"] = binding.final.get("views") or []
            if answers:
                binding_with_answers["user_answers"] = answers

            # Every chart lookup stage C has made, carried across attempts. A
            # replan runs a fresh tool loop, so without this the reuse survey is
            # repeated in full each time -- the same searches, the same answer,
            # a turn each.
            chart_searches: list[dict[str, Any]] = []

            def _resolve(extra: dict[str, Any] | None = None) -> Any:
                """One stage C attempt. `extra` is what this attempt knows that
                the last one did not -- validation problems, or the user's own
                words about the plan."""
                nonlocal total_cost, chart_searches
                # The plan being corrected. Passing it lets the attempt reply
                # with only what changes; `c_resolve` merges it back to a whole
                # plan, so everything downstream is unaffected.
                previous_plan = session.artifacts.get("plan")
                payload = {**binding_with_answers, **(extra or {})}
                if chart_searches:
                    payload["charts_you_already_searched"] = chart_searches
                if previous_plan:
                    payload["your_last_plan"] = previous_plan
                result = _retry(
                    session,
                    "Choosing chart types",
                    2,
                    lambda: c_resolve.run(
                        provider_for("C"),
                        gateway,
                        design_analysis,
                        payload,
                        PROMPTS,
                        str(REGISTRY),
                        on_progress=_tool_progress,
                        on_thinking=_thinking_for("C"),
                        thumbnail_sheet=str(THUMBNAIL_SHEET)
                        if THUMBNAIL_SHEET.exists()
                        else None,
                        image_paths=session.image_paths,
                        previous_plan=previous_plan,
                    ),
                )
                chart_searches = c_resolve.chart_searches(
                    result.transcript, chart_searches
                )
                total_cost += result.cost_usd
                session.artifacts["plan"] = result.final
                return result

            plan = _resolve()

            # The one place the run asks anything. Stage C has resolved the
            # whole page by now, so it knows what is genuinely undecided and
            # what each answer would change -- for itself and for the stages
            # after it, which never stop.
            #
            # One round. It is re-run with the answers and must then decide,
            # because a stage that can keep asking will, and the user did not
            # come here to be interviewed.
            # Superset's own default until the user says otherwise: a card
            # the design drew keeps its menu, a bare region never had one.
            menus = chrome.MENU_DATA_ONLY

            # Asked from Python, not from stage C: a design never draws
            # Superset's overflow menu, so a model reading the design answers
            # "no menu" every time. Whether the menu is wanted is a fact about
            # who uses the dashboard, not about the picture. It rides along
            # with C's own needs so the user is stopped once, not twice.
            chrome_entries = chrome.resolve(design_analysis, plan.final)
            chrome_question = chrome.question(chrome_entries)
            if needs := [
                n for n in plan.final.get("needs") or [] if isinstance(n, dict)
            ] + ([chrome_question] if chrome_question else []):
                merged_needs = {"questions": needs}
                questions.normalise_questions(merged_needs)
                session.publish(
                    "stage_start",
                    stage="C",
                    label=f"{len(merged_needs['questions'])} thing(s) I need to know",
                )
                need_answers = session.ask(
                    "questions",
                    {
                        "label": "A few things before I build this",
                        "questions": merged_needs["questions"],
                    },
                )
                replies = c_resolve.replies_of(need_answers)
                binding_with_answers["user_answers"] = {
                    **c_resolve.replies_of(binding_with_answers.get("user_answers")),
                    **replies,
                }
                if chrome_question:
                    menus = chrome.menus_from_answer(
                        replies.get(chrome.MENU_QUESTION_ID)
                    )
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
                        "datasets": binding.final.get("fact_tables") or [],
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
                # `.get`, not `[...]`: stage B's validator reports a binding
                # with no region_id as a problem and the runner treats every
                # stage B problem as a warning, so the condition B tolerates
                # reached here as an unhandled KeyError -- after B had written
                # tables and the user had approved the plan.
                bindings = {
                    b["region_id"]: b
                    for b in binding.final.get("bindings", [])
                    if b.get("region_id")
                }
                known = chart_types(load_registry(str(REGISTRY)))
                built: list[str] = []
                tag = f_scaffold.run_tag(session.id)
                crops_dir = crop.session_crops_dir(session.id)

                # Stage C's gate approves the dashboard, in prose. This one
                # approves the build, by eye: whether three cards really are
                # one component is a judgement no sentence can carry, and it
                # decides how many plugins get written. Assembled from work
                # already done -- no model runs to produce it.
                review = plugin_review.build(
                    design_analysis,
                    binding.final,
                    plan.final,
                    session.image_paths,
                    crops_dir,
                )
                session.publish(
                    "stage_start",
                    stage="F",
                    label=(
                        f"{review['counts']['plugins']} plugin(s) to build — "
                        "review before I start"
                    ),
                )
                review_answer = session.ask(
                    "plugins",
                    {
                        "label": "Here is what I will build",
                        "entries": review["entries"],
                        "dropped": review["dropped"],
                        "counts": review["counts"],
                        "crop_url": (
                            f"/api/v1/design_to_dashboard/session/{session.id}/crop/"
                        ),
                    },
                )
                if not review_answer.get("approved", True):
                    session.status = "cancelled"
                    session.publish(
                        "cancelled",
                        label="Plugin build rejected — nothing was created",
                        detail=str(review_answer.get("feedback") or "")[:600],
                    )
                    return
                if noted := plugin_review.apply_feedback(
                    plan.final, review_answer, review
                ):
                    session.publish(
                        "plugin_notes",
                        label=f"Noted your changes to {len(noted)} plugin(s)",
                        detail=", ".join(noted),
                    )
                session.publish(
                    "stage_start",
                    stage="F",
                    label=(
                        f"Building {len(new_plugin_decisions)} custom chart plugin(s)"
                    ),
                )

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
                            c_resolve.design_system(plan.final, design_analysis),
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
                    futures = {
                        pool.submit(_build, viz_type, group[0]): viz_type
                        for viz_type, group in by_type.items()
                    }
                    for future in concurrent.futures.as_completed(futures):
                        # `run_one` reports most failures as a result, but
                        # re-raises a timeout so the retry can see it, and
                        # `_retry` re-raises after its attempts. Unguarded,
                        # that escaped the executor block and ended the run --
                        # discarding stages A, B, C, the plan approval, the
                        # plugin review and every plugin that had generated
                        # cleanly, because one of them ran long twice. A
                        # generation that fails is the same outcome as a
                        # scaffold that fails, so it is recorded as one.
                        viz_type = futures[future]
                        try:
                            viz_type, scaffold = future.result()
                        except Exception as ex:  # noqa: BLE001 - drop one, keep the run
                            logger.exception("generating %s failed", viz_type)
                            scaffold = f_scaffold.ScaffoldResult(
                                region_id=by_type[viz_type][0].get("region_id", "?"),
                                viz_type=viz_type,
                                error=f"{type(ex).__name__}: {ex}",
                            )
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
                    # Writing patches two shared files, so it can fail on its
                    # own -- an unbalanced setupPluginsExtra(), a path that
                    # escapes the plugin directory. Unguarded, that exception
                    # left every plugin after it unwritten and its regions
                    # still marked `new_plugin`, which stage D skips: the run
                    # died holding a half-registered frontend. A write that
                    # fails is the same outcome as a scaffold that fails, so
                    # it gets the same treatment.
                    try:
                        written = plugin_writer.write(
                            scaffold.scaffold,
                            REPO_ROOT,
                            scaffold.plugin,
                            group[0],
                        )
                    except Exception as ex:  # noqa: BLE001 - drop one, keep the run
                        logger.exception("could not write %s", viz_type)
                        affected = ", ".join(str(d.get("region_id")) for d in group)
                        failed_plugins.append(f"{viz_type} ({affected}): {ex}")
                        plugin_writer.remove(scaffold.scaffold, REPO_ROOT)
                        for decision in group:
                            decision["decision"] = "drop"
                            decision["fidelity_loss"] = (
                                f"the {viz_type} plugin could not be written to "
                                "disk, so this section is missing"
                            )
                        session.publish(
                            "plugin_failed",
                            label=f"Could not write {viz_type} — dropping {affected}",
                            viz_type=viz_type,
                            detail=str(ex)[:400],
                        )
                        continue
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

                # webpack resolves a generated plugin through the node_modules
                # symlink only this call creates, so a failure here makes every
                # one of them unresolvable. The return value was discarded, and
                # the run reported the plugins as built.
                linked = frontend.link_plugins(REPO_ROOT)
                if not linked.get("linked"):
                    session.publish(
                        "plugin_link_failed",
                        label="npm install failed — the new plugins will not resolve",
                        detail=str(linked.get("reason") or "")[:400],
                    )

                # Regenerate the manifest so the new viz types are known to
                # stage D's validation and to the layout stage.
                _regenerate_registry(session)

                # Type-checking is not optional. Stage F's own checks are
                # regex over generated text and cannot see an invented field
                # on a type; the compiler can, and used to be reached only
                # through a dev-server restart nobody had opted into. So on
                # the common path a generated plugin was never compiled at
                # all, and the run spent chart configuration, layout and
                # apply before anyone found the frontend would not build.
                total_cost += _typecheck_and_quarantine(
                    session,
                    scaffolds,
                    by_type,
                    _region_for,
                    _binding_for,
                    plan.final,
                    f_provider,
                    tag,
                    crops_dir,
                    design_analysis,
                    built,
                )

                # Restarting is still a choice -- it is someone's dev server --
                # but by here the code on disk is known to compile.
                if _config().get("auto_restart_frontend"):
                    from superset.design_to_dashboard import frontend

                    outcome = frontend.restart_dev_server(REPO_ROOT)
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
            headerless = {
                entry.ref
                for entry in chrome.resolve(design_analysis, plan.final, menus)
                if entry.ref and entry.title != "superset" and not entry.menu
            }
            if given_back := e_layout.strip_header_allowance(
                layout.get("position_json") or {}, headerless
            ):
                layout.setdefault("adjustments", []).extend(
                    {"row_id": note.split(":")[0], "issue": note, "resolution": note}
                    for note in given_back
                )
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
                plan_for_apply = dict(plan.final)
                # Stage B creates its own tables and views -- that is what lets
                # it run a view's SQL against a real table before saving it --
                # so by here every dataset exists and the applier makes none.
                plan_for_apply["created_datasets"] = []

                applied = apply_plan(
                    design_analysis=design_analysis,
                    plan=plan_for_apply,
                    chart_specs=chart_specs,
                    layout=layout,
                    dashboard_title=(design_analysis.get("global") or {}).get("title"),
                    menus=menus,
                )
            except ApplyError as ex:
                raise RuntimeError(str(ex)) from ex

            # The user asked to be told what matching the design costs, rather
            # than to have the trade made quietly. Published as its own event
            # so it survives into the run's write-up.
            if applied.chrome_effects:
                session.publish(
                    "chrome_effects",
                    label="What matching the design's chrome changed",
                    effects=applied.chrome_effects,
                )

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
                # Which chart is which region, so each card can be compared
                # against the design's own crop of the section it came from.
                ref_to_id=applied.ref_to_id,
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
