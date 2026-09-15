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
import threading
from typing import Any, Callable, TYPE_CHECKING

from superset.design_to_dashboard import (
    chrome,
    contact_sheet,
    crop,
    plugin_review,
    trace,
    visual_verify,
)

if TYPE_CHECKING:
    from superset.design_to_dashboard.registry import Registry
    from superset.design_to_dashboard.stages.d_configure import ChartSpecResult

logger = logging.getLogger(__name__)


def _config() -> dict[str, Any]:
    from flask import current_app

    return current_app.config.get("DESIGN_TO_DASHBOARD_LLM") or {}


def _build_registry(session: Any, announce: bool = True) -> Registry:
    """Scan the source for every chart type, and save what was found.

    Runs at the start of every run, so no stage reads a registry older than the
    plugins on disk, and again after stage F: stage D reads a new plugin's
    settings panel through the registry, so a plugin written moments ago is
    invisible until this runs. It takes a fraction of a second, and runs in
    process, so what it returns is exactly what the stages are given.

    The snapshot is saved with the run, so a later look at the run sees the
    registry it was decided against.
    """
    from superset.design_to_dashboard import registry as registry_module

    built = registry_module.build(REPO_ROOT)
    session.save_stage("registry", built.snapshot())
    if built.dropped:
        session.publish(
            "registry_dropped",
            label=f"Ignored {len(built.dropped)} chart type(s) with no files",
            detail=", ".join(built.dropped),
        )
    if announce:
        session.publish("registry_rebuilt", label="Chart registry updated")
    return built


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
    charts = getattr(checks, "charts", [])
    broken = [c for c in charts if not c.ok]
    if broken:
        caveats.append(f"{len(broken)} of {len(charts)} charts not right")
    # A custom plugin the data API cannot query and no browser rendered is not
    # known to work; counted silently among the working, the headline claims
    # more than the run found out.
    if unchecked := [c for c in charts if c.ok and not getattr(c, "checked", True)]:
        caveats.append(f"{len(unchecked)} of {len(charts)} charts not checked")
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


# What a section the run gave up on is marked. Written only through
# `_drop_decision`, so no site can mark a drop and forget what it hosted.
DROPPED = "drop"


def _add_loss(decision: dict[str, Any], text: str) -> None:
    """Append to a decision's `fidelity_loss` without losing the reason it has."""
    existing = decision.get("fidelity_loss")
    decision["fidelity_loss"] = f"{existing}; {text}" if existing else text


def _released_note(refs: list[str]) -> str:
    return (
        f"the chart(s) it held ({', '.join(refs)}) are laid out on the grid on "
        "their own"
    )


def release_dropped_children(decisions: list[dict[str, Any]]) -> list[str]:  # noqa: C901
    """Undo every hosting relation a dropped decision is part of, in place.

    `children` is how every later stage learns a chart is drawn inside a
    parent rather than on the grid: stage E removes its grid node, the chrome
    pass skips its holder, stage D requires the parent to reference it. A
    dropped parent draws nothing, so what it listed is hosted by nobody --
    left in place, the list deleted eight of eleven built charts from the
    layout as "drawn by its parent". The other direction matters as much: a
    live parent still naming a dropped child is asked to render a chart that
    never gets an id.

    A live parent left with no children stays live. A generated container
    draws its own title, value and caption from controls of its own, and
    stage D configures it with no chart ids; dropping it would take that
    header with the cards it lost. What it lost is recorded in its
    `fidelity_loss` only: stage D is handed the whole decision, and a list of
    refs there reads as charts to reference. The loop repeats until nothing
    changes, since a note correction can follow a later drop.

    What a dropped parent released is kept on it (`released_children`), so a
    later drop of one of those charts -- in the same batch or a later one --
    corrects the note instead of leaving it promising a chart on the grid that
    is not there.

    Idempotent, so it runs after every drop and once more before the stages
    that read `children` -- which also covers a drop stage C wrote itself and
    a plan restored from an earlier run.
    """
    notes: list[str] = []
    changed = True
    while changed:
        changed = False
        dropped = {
            str(d.get("ref"))
            for d in decisions
            if isinstance(d, dict) and d.get("decision") == DROPPED and d.get("ref")
        }
        for decision in decisions:
            if not isinstance(decision, dict):
                continue
            region_id = decision.get("region_id")
            if decision.get("decision") == DROPPED:
                changed |= _correct_released(decision, dropped)
                if not decision.get("children"):
                    continue
                children = [str(c) for c in decision.pop("children")]
                if released := [c for c in children if c not in dropped]:
                    decision["released_children"] = released
                    _add_loss(decision, _released_note(released))
                    notes.append(f"{region_id}: dropped, so {released} go on the grid")
                changed = True
                continue
            if not decision.get("children"):
                continue
            children = list(decision["children"])
            if not (gone := [str(c) for c in children if str(c) in dropped]):
                continue
            decision["children"] = [c for c in children if str(c) not in dropped]
            _add_loss(
                decision,
                f"it no longer holds {', '.join(gone)}, which could not be built",
            )
            notes.append(f"{region_id}: no longer hosts dropped {gone}")
            if not decision["children"]:
                del decision["children"]
                _add_loss(
                    decision,
                    "every chart it held is missing, so it draws only what it "
                    "renders itself",
                )
                notes.append(f"{region_id}: kept with none of the charts it held")
            changed = True
    return notes


def _correct_released(decision: dict[str, Any], dropped: set[str]) -> bool:
    """Take charts dropped since from a dropped parent's released list and note."""
    released = decision.get("released_children") or []
    if not (gone := [ref for ref in released if ref in dropped]):
        return False
    remaining = [ref for ref in released if ref not in dropped]
    old_note = _released_note(released)
    loss = str(decision.get("fidelity_loss") or "")
    if remaining:
        decision["released_children"] = remaining
        decision["fidelity_loss"] = loss.replace(old_note, _released_note(remaining))
    else:
        del decision["released_children"]
        decision["fidelity_loss"] = (
            loss.replace(f"; {old_note}", "").replace(old_note, "").strip("; ")
        )
    logger.info("%s: released %s were dropped as well", decision.get("region_id"), gone)
    return True


def _drop_decision(
    decision: dict[str, Any], decisions: list[dict[str, Any]], reason: str
) -> None:
    """Mark a section as missing, and release whatever it hosted.

    A decision already dropped keeps the reason it has: the sweep drops a
    container whose charts all failed, and its own plugin failing afterwards
    changes nothing about why the section is missing.
    """
    if decision.get("decision") == DROPPED:
        return
    decision["decision"] = DROPPED
    decision["fidelity_loss"] = reason
    if notes := release_dropped_children(decisions):
        logger.info("released hosted charts: %s", "; ".join(notes))


def drop_unconfigured_parents(
    charts: list[ChartSpecResult], decisions: list[dict[str, Any]]
) -> list[str]:
    """Drop every parent stage D gave up on, and release what it hosted.

    A chart stage D could not configure -- a failed call, an unparseable
    answer, a control panel that would not load, or a chart left out because
    it would throw -- is skipped by the applier. A parent skipped that way
    still listed its children, so stage E removed their grid nodes as drawn
    inside it: the charts were created and placed nowhere, and Superset
    appended them at the foot of the page at its default size. Dropped here,
    before stage E, its children are ordinary charts on the grid.

    A child configured as hosted was never left out, because its parent's
    params named it. Released, nothing names it, so one that would throw is
    left out here. That can leave out a parent in turn, so this repeats until
    nothing changes.
    """
    from superset.design_to_dashboard.stages.e_layout import hosted_refs

    by_ref = {
        str(d.get("ref")): d for d in decisions if isinstance(d, dict) and d.get("ref")
    }
    notes: list[str] = []
    changed = True
    while changed:
        changed = False
        hosted = hosted_refs({"decisions": decisions})
        for chart in charts:
            decision = by_ref.get(str(chart.ref))
            if decision is None or decision.get("decision") == DROPPED:
                continue
            if chart.error is None and chart.leave_out and chart.ref not in hosted:
                chart.error = chart.leave_out
                notes.append(f"{chart.ref}: no longer hosted, so left out")
                changed = True
            if chart.error and decision.get("children"):
                _drop_decision(
                    decision,
                    decisions,
                    "stage D could not configure it, so this section is "
                    f"missing: {chart.error[:200]}",
                )
                notes.append(f"{chart.ref}: dropped, stage D could not configure it")
                changed = True
    return notes


def resolve_filter_scope(
    session: Any,
    plan: dict[str, Any],
    chart_specs: list[dict[str, Any]],
    design_analysis: dict[str, Any] | None,
) -> str:
    """Ask the one question `filter_scope` exists to ask, if this design raises it.

    Stage D is the earliest point the ambiguity can even be seen: it takes the
    plan's filter decisions (does the page have a picker at all) and the
    params stage D just wrote (do any charts beside it draw a trend), and
    neither is available before D runs. That is also why this is not folded
    into stage C's own question round -- C is asked and re-planned long
    before D's charts exist to compare against.

    Most designs never reach the second `if`: `filter_scope.question` returns
    `None` the moment there is no picker, or no trend chart for it to
    disagree with, and this hands back the module's own default unasked.
    """
    from superset.design_to_dashboard import filter_scope, questions
    from superset.design_to_dashboard.stages import c_resolve

    asked = filter_scope.question(plan, chart_specs, design_analysis)
    if asked is None:
        return filter_scope.SCOPE_EXCEPT_TRENDS
    merged = {"questions": [asked]}
    questions.normalise_questions(merged)
    session.publish(
        "stage_start",
        stage="D",
        label="One more thing before I build this",
    )
    reply = session.ask(
        "questions",
        {
            "label": "One more thing before I build this",
            "questions": merged["questions"],
        },
    )
    return filter_scope.scope_from_answer(
        c_resolve.replies_of(reply).get(filter_scope.SCOPE_QUESTION_ID)
    )


def _plugin_directories(scaffolds: dict[str, Any]) -> dict[str, str]:
    """Each written plugin's directory, by viz type."""
    return {
        viz_type: (scaffold.scaffold or {}).get("directory") or ""
        for viz_type, scaffold in scaffolds.items()
        if scaffold.ok
    }


def _errors_for(errors: list[dict[str, str]], directory: str) -> list[dict[str, str]]:
    """The errors `_plugins_in_errors` blames on the plugin in `directory`."""
    leaf = directory.rsplit("/", 1)[-1]
    return [e for e in errors if leaf and leaf in (e.get("file") or "")]


def _headline(detail: str) -> str:
    """An error's first line, short enough for an event label.

    A type-check error can carry indented lines naming the property at fault;
    those are for the repair prompt, not for a progress message.
    """
    return detail.split("\n", 1)[0][:120]


def _autofix_plugins(
    session: Any, outcome: dict[str, Any], scaffolds: dict[str, Any]
) -> dict[str, Any]:
    """Remove the unused imports the compiler named, then check again.

    No model call: `import React from 'react'` under the automatic JSX
    runtime is an edit that needs no judgement, and handing it to a model
    cost a whole generation. Returns the verdict it was given when nothing
    changed, so the caller can tell that no re-check happened.
    """
    from superset.design_to_dashboard import (
        frontend,
        import_autofix,
        plugin_skeleton,
        plugin_writer,
    )

    errors = outcome.get("errors") or []
    directories = _plugin_directories(scaffolds)
    fixed: dict[str, int] = {}
    for viz_type in sorted(_plugins_in_errors(errors, directories)):
        current = scaffolds[viz_type]
        if current.plugin is None:
            continue
        try:
            owned = plugin_skeleton.owned_paths(current.plugin, REPO_ROOT)
            removed = import_autofix.fix_plugin(
                REPO_ROOT, directories[viz_type], errors, owned
            )
            if removed:
                # Kept in step with the disk, so what is held in memory is
                # never an older plugin than the one that was checked.
                on_disk = plugin_writer.read(directories[viz_type], REPO_ROOT)
                current.scaffold["files"] = [
                    {"path": path, "contents": contents}
                    for path, contents in sorted(on_disk.sources.items())
                    if path not in owned
                ]
        except Exception:  # noqa: BLE001 - the model repair still runs
            logger.exception("could not remove unused imports from %s", viz_type)
            continue
        if removed:
            fixed[viz_type] = sum(removed.values())

    if not fixed:
        return outcome
    session.publish(
        "plugin_autofixed",
        label=f"Removed {sum(fixed.values())} unused import(s) — rechecking",
        detail=", ".join(f"{viz_type} ({n})" for viz_type, n in sorted(fixed.items())),
        viz_types=sorted(fixed),
    )
    return frontend.typecheck(REPO_ROOT)


def _repair_broken_plugins(  # noqa: C901
    session: Any,
    outcome: dict[str, Any],
    scaffolds: dict[str, Any],
    by_type: dict[str, list[dict[str, Any]]],
    provider: Any,
) -> dict[str, Any]:
    """One repair round for every plugin that did not compile.

    The checks stage F runs are regex over the scaffold's text: they catch a
    wrong import and cannot catch a property invented on a type. Only the
    compiler sees those.

    Unused imports are removed first, without a model. What the compiler
    still rejects is then patched: the author is shown the files as they are
    on disk with the errors against their lines, and returns only the files
    it changes. Everything else stays exactly as it was, so a round cannot
    undo what the previous one fixed, or rewrite what already compiled.

    Returns the verdict it was given when it changed nothing, and a fresh
    type-check otherwise.
    """
    from superset.design_to_dashboard import frontend, plugin_writer
    from superset.design_to_dashboard.stages import f_scaffold

    checked = _autofix_plugins(session, outcome, scaffolds)
    if checked.get("compiled") is not False:
        return checked
    errors = checked.get("errors") or []
    directories = _plugin_directories(scaffolds)
    blamed = _plugins_in_errors(errors, directories)
    if not blamed:
        # The build is broken by something this run did not write.
        return checked

    session.publish(
        "plugin_repair",
        label=f"{len(blamed)} plugin(s) did not compile — patching",
        detail=", ".join(sorted(blamed)),
        viz_types=sorted(blamed),
    )
    patched: dict[str, list[str]] = {}
    relink = False
    for viz_type in sorted(blamed):
        current = scaffolds[viz_type]
        plugin = current.plugin
        if plugin is None:
            continue
        decision = by_type[viz_type][0]
        on_disk = plugin_writer.read(directories[viz_type], REPO_ROOT)
        result = f_scaffold.repair_one(
            provider,
            decision,
            plugin,
            on_disk.sources,
            _errors_for(errors, directories[viz_type]),
            PROMPTS,
            REPO_ROOT,
        )
        # Billed whether or not the patch is usable.
        current.cost_usd += result.cost_usd
        if not result.ok or result.scaffold is None:
            reason = result.error or "; ".join(result.problems)
            logger.warning("repair of %s not applied: %s", viz_type, reason)
            session.publish(
                "plugin_repair_rejected",
                label=f"Could not patch {viz_type} — left as it was",
                viz_type=viz_type,
                detail=reason[:400],
            )
            continue
        try:
            # The merged file set, so every file the patch did not touch
            # survives the writer's replacement of `src/`; the binary assets
            # beside them are put back the same way.
            written = plugin_writer.write(
                result.scaffold, REPO_ROOT, plugin, decision, assets=on_disk.assets
            )
        except Exception:  # noqa: BLE001 - the quarantine handles what is left
            logger.exception("could not write the repair of %s", viz_type)
            continue
        relink = relink or written.dependency_added
        # Only what the patch returned replaces what was held; a `params_hint`
        # it did not return is still the one stage D should use.
        current.scaffold = {**(current.scaffold or {}), **result.scaffold}
        if hint := result.scaffold.get("params_hint"):
            for sibling in by_type[viz_type]:
                sibling["params_hint"] = hint
        patched[viz_type] = result.changed
        session.publish(
            "plugin_patched",
            label=f"Patched {len(result.changed)} file(s) in {viz_type}",
            viz_type=viz_type,
            detail=", ".join(path.rsplit("/src/", 1)[-1] for path in result.changed),
        )

    if not patched:
        return checked
    session.publish(
        "plugin_repaired",
        label=f"Patched {len(patched)} plugin(s) — rechecking",
        detail=", ".join(sorted(patched)),
    )
    # The package name comes from the skeleton, which a patch cannot touch,
    # so this is a guard rather than an expected step: an unlinked package
    # fails to resolve in a way that reads as the author's fault.
    if relink:
        frontend.link_plugins(REPO_ROOT)
    return frontend.typecheck(REPO_ROOT)


# How many repair rounds a plugin that did not compile gets. Each round
# patches the state the previous one left, so its fixes accumulate: the first
# clears what the compiler listed, and a second catches a fault the first
# exposed. Beyond that the author is guessing, and the plugin is removed.
REPAIR_ROUNDS = 2


def _typecheck_and_quarantine(  # noqa: C901
    session: Any,
    scaffolds: dict[str, Any],
    by_type: dict[str, list[dict[str, Any]]],
    plan: dict[str, Any],
    provider: Any,
    built: list[str],
) -> float:
    """Compile what was written, repair what failed, remove what cannot be.

    The guarantee this exists to make is that nobody opens the dashboard to a
    frontend that does not build. A generated plugin is registered globally,
    so one that does not compile takes down every chart on the page and not
    just its own section -- the run would otherwise report success while the
    dev server served a compile error.

    So a plugin gets ``REPAIR_ROUNDS`` rounds with the compiler's own output
    in hand, and if it still fails it is deleted, unregistered, and its
    sections are dropped the way stage C drops a section it cannot build. An
    incomplete dashboard is a worse outcome than a complete one and a far
    better outcome than a broken one.

    Returns what the repairs cost, for the run's total.
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
                f"{e['file']}: {_headline(e['detail'])}"
                for e in (verdict.get("errors") or [])[:6]
            ),
        )
        repaired = _repair_broken_plugins(
            session, verdict, scaffolds, by_type, provider
        )
        # `_repair_broken_plugins` re-checks only when it changed something.
        # When it returns the verdict it was given, another round would ask
        # the same question of the same files.
        if repaired is verdict:
            break
        verdict = repaired
    if verdict.get("compiled") is False:
        # The last round's patch is checked, never repaired. An import it
        # stopped using is still not worth a section of the dashboard.
        verdict = _autofix_plugins(session, verdict, scaffolds)

    if verdict.get("compiled") is not False:
        session.publish(
            "typecheck_passed",
            label="The generated plugins compile",
            compiled=verdict.get("compiled"),
            detail=verdict.get("reason"),
        )
        return sum(s.cost_usd for s in scaffolds.values()) - before

    # Out of repair rounds. Everything still named in an error goes.
    directories = _plugin_directories(scaffolds)
    doomed = _plugins_in_errors(verdict.get("errors") or [], directories)
    if not doomed:
        # The build is broken by something this run did not write. Removing a
        # working plugin would not fix it and would lose a section for no
        # reason, so the fault is reported and left where it is.
        session.publish(
            "typecheck_failed",
            label="The frontend does not compile, but no generated plugin is at fault",
            detail="; ".join(
                f"{e['file']}: {_headline(e['detail'])}"
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
            _drop_decision(
                decision,
                plan.get("decisions") or [],
                f"the {viz_type} plugin did not compile after "
                f"{REPAIR_ROUNDS} repair attempt(s), so this section is missing",
            )
        session.publish(
            "plugin_failed",
            label=f"{viz_type} would not compile — removed, dropping {affected}",
            viz_type=viz_type,
            detail="; ".join(
                _headline(e["detail"])
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


# The verdict a dashboard has to earn before its new plugins are photographed.
PHOTOGRAPH_VERDICT = "pass"


def _photograph_if_approved(
    session: Any,
    plan: dict[str, Any],
    verdict: str,
    registry: Registry | None = None,
) -> None:
    """Photograph the plugins stage F built, but only for a dashboard that passed.

    The photograph becomes that plugin's picture in every later run's contact
    sheet, where stage C decides whether to reuse it. A plugin from a dashboard
    that did not look like its design is exactly the one whose picture should
    not be offered as a match.
    """
    built = [d for d in plan.get("decisions", []) if d.get("built_by_stage_f")]
    if not built:
        return
    if verdict != PHOTOGRAPH_VERDICT:
        session.publish(
            "thumbnails_skipped",
            label=f"New plugins not photographed: the dashboard was judged "
            f"{verdict!r}, not {PHOTOGRAPH_VERDICT!r}",
            verdict=verdict,
        )
        return
    _photograph_new_plugins(session, plan, registry)


def _photograph_new_plugins(
    session: Any, plan: dict[str, Any], registry: Registry | None = None
) -> None:
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
        if registry is None:
            from superset.design_to_dashboard.registry import build

            registry = build(REPO_ROOT)
        adopted = thumbnails.adopt(rendered, registry.entries)
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


def _retry(
    session: Any,
    label: str,
    attempts: int,
    call: Callable[[], Any],
    on_truncated: Callable[[], Any] | None = None,
    on_max_turns: Callable[[], Any] | None = None,
) -> Any:
    """Retry a single-shot stage.

    These calls are non-deterministic: the same prompt can end on
    ``stop_reason: tool_use`` once and answer cleanly the next time. Losing an
    entire multi-dollar run to one flaky turn is not acceptable, so each
    single-shot stage gets a second chance before the run fails.

    A reply cut off at its output budget is not flaky. The provider has already
    re-sent it once at the largest budget allowed, so the same request again
    stops at the same place and bills another full budget. It goes to
    `on_truncated` -- a cheaper way to ask -- exactly once, or is raised when
    the stage has none.

    An agent loop that exhausted its turn budget without answering is not
    flaky either, for the same reason in a different shape: an identical
    retry spends the identical turns on the identical `Read` calls and fails
    the identical way. It goes to `on_max_turns` -- a larger budget to ask
    with -- exactly once, or is raised when the stage has none.
    """
    from superset.design_to_dashboard.llm.base import (
        LLMError,
        LLMMaxTurnsError,
        LLMTruncatedError,
    )

    last: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return call()
        except LLMTruncatedError as ex:
            logger.warning("%s ran out of output budget: %s", label, ex)
            if on_truncated is None:
                raise
            session.publish(
                "retry",
                label=f"{label} ran out of output budget — retrying at lower effort",
                detail=str(ex)[:200],
            )
            return on_truncated()
        except LLMMaxTurnsError as ex:
            logger.warning("%s exhausted its turn budget: %s", label, ex)
            if on_max_turns is None:
                raise
            session.publish(
                "retry",
                label=f"{label} ran out of turns — retrying with a larger budget",
                detail=str(ex)[:200],
            )
            return on_max_turns()
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


def _lower_effort_provider(provider: Any, stage: str, session_id: str) -> Any:
    """The stage's provider one effort level down, or None. **Request thread only.**

    For a reply cut off at the largest output budget allowed: reasoning is what
    fills that budget, and it shrinks with effort. Built before a stage fans
    out rather than when a truncation happens, because building a provider
    reads `current_app.config` and a worker thread has no app context. Recorded
    under its own label, so its numbered traces do not overwrite the stage's.
    """
    from superset.design_to_dashboard.llm.base import lower_effort
    from superset.design_to_dashboard.llm.factory import get_llm_provider

    lower = lower_effort(getattr(provider, "effort", None) or "")
    if lower is None:
        return None
    try:
        lowered: Any = get_llm_provider(stage, effort=lower)
    except Exception:  # noqa: BLE001 - a missing fallback must not end the run
        logger.exception("could not build a lower-effort provider for %s", stage)
        return None
    if _config().get("record_calls"):
        from superset.design_to_dashboard.llm.recorder import RecordingProvider

        lowered = RecordingProvider(lowered, f"{stage}-{lower}", session_id, REPO_ROOT)
    return lowered


# The most turns a retry will ask for, however small the budget it started at.
# A ceiling rather than a fixed step: doubling is meaningless past some size,
# and without one a stage whose floor is already large could ask for an
# unbounded number of turns on every retry.
MAX_RETRY_TURNS = 48


def _higher_turns_provider(provider: Any, stage: str, session_id: str) -> Any:
    """The stage's provider with a larger turn budget, or None. **Request thread only.**

    For an agent loop that exhausted its turns before answering: unlike a
    truncated reply, this was never a reasoning-budget problem, so a lower
    `effort` is not the fix -- a larger turn budget is. Doubled rather than
    incremented, so a retry actually changes the shape of the request instead
    of asking for one turn more than a call that just burned every one it had.
    Built before a stage fans out, for the same app-context reason as
    `_lower_effort_provider`, and recorded under its own label so its traces
    do not overwrite the stage's.
    """
    from superset.design_to_dashboard.llm.factory import get_llm_provider

    current = getattr(provider, "max_turns", None)
    if not isinstance(current, int):
        return None
    higher = min(current * 2, MAX_RETRY_TURNS)
    if higher <= current:
        return None
    try:
        lifted: Any = get_llm_provider(stage, max_turns=higher)
    except Exception:  # noqa: BLE001 - a missing fallback must not end the run
        logger.exception("could not build a higher-turn-budget provider for %s", stage)
        return None
    if _config().get("record_calls"):
        from superset.design_to_dashboard.llm.recorder import RecordingProvider

        lifted = RecordingProvider(
            lifted, f"{stage}-turns{higher}", session_id, REPO_ROOT
        )
    return lifted


def _chart_checks(checks: Any) -> list[dict[str, Any]]:
    """Each chart's check as published: what the API and the browser saw."""
    return [
        {
            "chart_id": c.chart_id,
            "name": c.slice_name,
            "viz_type": c.viz_type,
            "ok": c.ok,
            # False for a custom plugin nothing has rendered: its `ok` then
            # means only that no failure was seen.
            "checked": c.checked,
            "rows": c.rows,
            "error": c.error,
            "note": c.note,
            "status_code": c.status_code,
            "render_error": c.render_error,
        }
        for c in checks.charts
    ]


PROMPTS = (
    pathlib.Path(__file__).resolve().parents[2] / "design-to-dashboard" / "prompts"
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

            from superset.design_to_dashboard import gate_a, plugin_writer, questions
            from superset.design_to_dashboard.applier import apply_plan, ApplyError
            from superset.design_to_dashboard.llm.factory import get_llm_provider
            from superset.design_to_dashboard.mcp.gateway import InProcessGateway
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

            # The registry and the picture of every chart type are built from
            # source for this run, so it compares against the plugins on disk
            # rather than whatever a committed file last recorded. There is no
            # fallback: a scan that finds no chart types means the checkout is
            # broken, and a run against a guessed list would only hide that.
            registry = _build_registry(session, announce=False)
            gateway.registry = registry
            plugin_sheet = contact_sheet.build(
                registry.entries,
                REPO_ROOT,
                pathlib.Path(session.image_paths[0]).parent / "plugin_sheet.png",
            )

            # ---- A: decompose ------------------------------------------------
            session.publish("stage_start", stage="A", label="Reading the design")
            a_provider = provider_for("A")
            # Same two fallbacks stage F gets, for the same reasons: A is
            # given the design image(s) and only the `Read` tool, so it is
            # exposed to the identical turn-budget failure, and a reply cut
            # off at its output budget is no more fixable by an identical
            # retry here than it is there.
            a_provider_lower = _lower_effort_provider(a_provider, "A", session.id)
            a_provider_more_turns = _higher_turns_provider(a_provider, "A", session.id)

            def _read_design(provider: Any) -> Any:
                return a_decompose.run(
                    provider,
                    session.requirement,
                    session.image_paths,
                    PROMPTS,
                    on_thinking=_thinking_for("A"),
                    registry=registry,
                )

            # Parsing happens inside the retried call, not after it: an
            # unparseable reply is exactly as transient as a failed one, and
            # this is the longest single call in the pipeline to lose.
            design_analysis, stage_a_cost = _retry(
                session,
                "Reading the design",
                2,
                lambda: _read_design(a_provider),
                on_truncated=(
                    (lambda: _read_design(a_provider_lower))
                    if a_provider_lower is not None
                    else None
                ),
                on_max_turns=(
                    (lambda: _read_design(a_provider_more_turns))
                    if a_provider_more_turns is not None
                    else None
                ),
            )
            total_cost += stage_a_cost
            session.artifacts["design_analysis"] = design_analysis
            session.save_stage("A", design_analysis)

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
                design_analysis, registry.chart_types()
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

            # ---- gate: review the reading before B binds it to data -----------
            #
            # Every stage after this one joins on `region_id`. Once B has
            # designed a data spec against today's reading, a correction here
            # means redoing B too -- so this is the one point where fixing a
            # misread region, or answering what B would otherwise guess, is
            # nearly free. The run genuinely stops: `session.ask` blocks this
            # worker thread until a human calls `session.answer`, the same
            # primitive stage C's questions already use, with no timeout that
            # lets the run continue unanswered.
            presentation = gate_a.build_presentation(design_analysis)
            session.publish(
                "stage_start",
                stage="A_gate",
                label="Waiting for your review of the design reading",
            )
            gate_answer = session.ask("region_review", presentation)
            plugin_choices = {
                str(k): str(v)
                for k, v in (gate_answer.get("plugin_choices") or {}).items()
            }
            free_answers = {
                str(k): str(v) for k, v in (gate_answer.get("answers") or {}).items()
            }
            revised_analysis, gate_cost = a_decompose.revise(
                provider_for("A"),
                design_analysis,
                presentation["questions"],
                free_answers,
                PROMPTS,
                plugin_choices=plugin_choices,
                image_paths=session.image_paths,
                on_thinking=_thinking_for("A"),
                registry=registry,
            )
            total_cost += gate_cost
            if gate_problems := a_decompose.validate(
                revised_analysis, registry.chart_types()
            ):
                # The pre-gate reading already passed validation and is known
                # usable; a revision that fails is a worse answer than the one
                # the user was shown, so it is logged and discarded rather than
                # sent on to bind against.
                logger.error(
                    "stage A revision validation: %s", "; ".join(gate_problems)
                )
                session.publish(
                    "validation_failed",
                    stage="A_gate",
                    label=f"The revised reading has {len(gate_problems)} problem(s)",
                    detail="; ".join(gate_problems)[:1000],
                    problems=gate_problems,
                )
            else:
                design_analysis = revised_analysis
                session.artifacts["design_analysis"] = design_analysis
                session.save_stage("A", design_analysis)
            session.publish(
                "stage_complete",
                stage="A_gate",
                label="Reading confirmed",
                regions=design_analysis.get("regions", []),
                cost=round(total_cost, 4),
            )

            # ---- B: bind -----------------------------------------------------
            session.publish("stage_start", stage="B", label="Designing your data")

            def _tool_progress(
                tool: str, arguments: dict[str, Any], error: str | None = None
            ) -> None:
                session.publish(
                    "tool_call", tool=tool, arguments=arguments, error=error
                )

            # Two steps. The design step is the only one that sees the picture,
            # and it writes the whole data spec; the build step creates that
            # spec without the picture or stage A's descriptions. The spec is
            # saved in between, so a failed build never has to design again.
            designed = b_bind.design_step(
                provider_for("B"),
                gateway,
                design_analysis,
                PROMPTS,
                tag=f_scaffold.run_tag(session.id),
                image_paths=session.image_paths,
                on_thinking=_thinking_for("B"),
            )
            total_cost += designed.cost_usd
            session.artifacts["data_spec"] = designed.spec
            session.save_stage(
                "B_design",
                {
                    "spec": designed.spec,
                    "databases": designed.databases,
                    "taken": designed.taken,
                    "renamed": designed.renamed,
                    "problems": designed.problems,
                },
            )
            if designed.renamed:
                session.publish(
                    "names_adjusted",
                    stage="B",
                    label=f"Renamed {len(designed.renamed)} dataset(s) that "
                    "earlier dashboards already use",
                    detail="; ".join(designed.renamed),
                )
            if designed.problems:
                logger.warning(
                    "stage B design validation: %s", "; ".join(designed.problems)
                )
                session.publish(
                    "validation_failed",
                    stage="B",
                    label=f"{len(designed.problems)} problem(s) with the data spec",
                    detail="; ".join(designed.problems)[:1000],
                    problems=designed.problems,
                )

            binding = b_bind.build_step(
                provider_for("B"),
                gateway,
                design_analysis,
                designed,
                PROMPTS,
                on_progress=_tool_progress,
                on_thinking=_thinking_for("B"),
            )
            total_cost += binding.cost_usd
            session.artifacts["binding_set"] = binding.final
            session.save_stage("B", binding.final)

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
            # the ones stage B wished for -- already true without a separate
            # key: `binding.final["views"]` is stage B's own record of what it
            # actually created, and `c_resolve.build_user_prompt` reads `views`
            # straight off `binding_set` already. A `created_datasets` key
            # holding the exact same list under a name nothing read was dead
            # weight, not a second copy serving a different reader.
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
                        registry,
                        on_progress=_tool_progress,
                        on_thinking=_thinking_for("C"),
                        thumbnail_sheet=str(plugin_sheet) if plugin_sheet else None,
                        image_paths=session.image_paths,
                        previous_plan=previous_plan,
                    ),
                )
                chart_searches = c_resolve.chart_searches(
                    result.transcript, chart_searches
                )
                total_cost += result.cost_usd
                session.artifacts["plan"] = result.final
                session.save_stage("C", result.final)
                return result

            plan = _resolve()

            # A `configure` decision that names its own fidelity_loss and asks
            # nothing about it is a stock-versus-custom trade-off settled on
            # the user's behalf without them. Folded in here, before the one
            # round the run asks anything: a question this loop adds to
            # `needs` reaches the user in the same round as every other one
            # C wrote itself, rather than being found too late to ask at all.
            for _attempt in range(C_MAX_REPLANS):
                fidelity_problems = c_resolve.stock_fidelity_unasked(
                    plan.final.get("decisions") or [], plan.final.get("needs") or []
                )
                if not fidelity_problems:
                    break
                logger.info("stage C fidelity check: %s", "; ".join(fidelity_problems))
                plan = _resolve({"validation_problems": fidelity_problems})

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
                    plan.final,
                    design_analysis,
                    binding_with_answers,
                    registry,
                    chart_searches,
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
                    plan.final,
                    design_analysis,
                    binding_with_answers,
                    registry,
                    chart_searches,
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
                known = registry.chart_types()
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
                # Sharing a `viz_type` name is not the same as sharing a shape:
                # only `group[0]` is ever sent to stage F, and grouping on the
                # name alone trusted every other member to fit the plugin built
                # for it with nothing checking that they actually did. Checked,
                # and split, here -- before a generation call is spent on a
                # group that was never going to hold together -- rather than
                # after a scaffold built for three children meets a sibling
                # needing four and the whole group is dropped together.
                by_type, shape_splits = c_resolve.split_incompatible_groups(
                    by_type, regions
                )
                for split in shape_splits:
                    session.publish(
                        "plugin_group_split",
                        label=(
                            f"{split['viz_type']} does not fit every region that "
                            f"named it — building {split['new_viz_type']} for "
                            f"{', '.join(split['region_ids'])}"
                        ),
                        viz_type=split["viz_type"],
                        new_viz_type=split["new_viz_type"],
                        region_ids=split["region_ids"],
                        detail=split["reason"],
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
                # Resolved here, on the request thread, for the one failure a
                # second identical request cannot fix: a reply cut off at the
                # largest output budget allowed.
                f_provider_lower = _lower_effort_provider(f_provider, "F", session.id)
                # Same reasoning, for the other failure a second identical
                # request cannot fix: an agent loop that exhausted its turns
                # -- almost always spent opening the attached images -- before
                # it ever answered.
                f_provider_more_turns = _higher_turns_provider(
                    f_provider, "F", session.id
                )

                def _region_for(region_id: str) -> dict[str, Any]:
                    """The region a plugin decision describes.

                    A container's charts are resolved under `r07:1` and
                    `r07:2` by stage C's container decisions, and stage A's list
                    has no such ids -- so a plain lookup returned {} and the
                    plugin for a child was generated with no description of
                    what it draws and no image, from its decision alone.
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

                    def _generate(provider: Any) -> Any:
                        return f_scaffold.run_one(
                            provider,
                            gateway,
                            _region_for(region_id),
                            _binding_for(region_id),
                            decision,
                            c_resolve.design_system(plan.final, design_analysis),
                            PROMPTS,
                            REPO_ROOT,
                            known,
                            tag=tag,
                            on_thinking=_thinking_for("F"),
                            on_progress=_tool_progress,
                            region_image=crop.region_crop(
                                session.image_paths,
                                _region_for(region_id),
                                crops_dir,
                            ),
                            # The whole design the crop was cut from, so a
                            # pixel-perfect build can check this region's
                            # chrome against the page's own repeated
                            # treatment rather than inventing one in
                            # isolation.
                            design_image=crop.source_image_path(
                                session.image_paths, _region_for(region_id)
                            ),
                            # Refs mean nothing to the author of a wrapper.
                            # Resolved first, so it knows what it hosts before
                            # it writes a line of it.
                            children=f_scaffold.resolve_children(
                                decision, plan.final.get("decisions", [])
                            ),
                        )

                    # F is a single-shot call like A and E, and equally prone to
                    # a transient failure -- losing a long run to one is not
                    # acceptable.
                    return viz_type, _retry(
                        session,
                        f"Building the plugin for {region_id}",
                        2,
                        lambda: _generate(f_provider),
                        # Reasoning is what fills a plugin's budget, so thinking
                        # one level less hard is what is left to try.
                        on_truncated=(
                            (lambda: _generate(f_provider_lower))
                            if f_provider_lower is not None
                            else None
                        ),
                        # Turns, not reasoning, are what ran out here -- almost
                        # always spent on the `Read` calls for the attached
                        # images -- so a larger turn budget is what is left to
                        # try.
                        on_max_turns=(
                            (lambda: _generate(f_provider_more_turns))
                            if f_provider_more_turns is not None
                            else None
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
                        # re-raises a timeout or a truncated reply so the retry
                        # can see it, and
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
                            _drop_decision(
                                decision,
                                plan.final.get("decisions", []),
                                f"the {viz_type} plugin could not be generated, "
                                "so this section is missing from the dashboard",
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
                            _drop_decision(
                                decision,
                                plan.final.get("decisions", []),
                                f"the {viz_type} plugin could not be written to "
                                "disk, so this section is missing",
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
                        if decision.get("decision") == DROPPED:
                            # A container every hosted chart of which failed
                            # was dropped with them; a plugin that built does
                            # not give it anything to hold.
                            continue
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

                # Rebuild so the new viz types are known to stage D, which
                # reads their settings panels, and to the layout stage.
                registry = _build_registry(session)
                gateway.registry = registry

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
                    plan.final,
                    f_provider,
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
                            f"{e['file']}: {_headline(e['detail'])}"
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

                # Stage F rewrites the plan in place: a plugin that could not
                # be generated turns its regions into drops. The plan stored
                # under C was serialised before that, so it no longer describes
                # what D and E are about to build from -- and a resume reading
                # it would try to build plugins this run has already given up
                # on. Both the outcome and the corrected plan are recorded.
                session.save_stage(
                    "F", {"built": built, "failed": failed_plugins, "plan": plan.final}
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
            # Every drop this run made has already released what it hosted.
            # This catches the ones it did not make: stage C dropping a frame
            # it still listed children for, or a plan restored from a run that
            # predates the release.
            if released := release_dropped_children(plan.final.get("decisions", [])):
                logger.info("released hosted charts: %s", "; ".join(released))
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
                registry,
                on_chart=_chart_done,
            )
            total_cost += sum(c.cost_usd for c in charts)
            if dropped_parents := drop_unconfigured_parents(
                charts, plan.final.get("decisions", [])
            ):
                logger.info("after stage D: %s", "; ".join(dropped_parents))
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
            session.save_stage("D", chart_specs)
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

            # Only now do the charts stage D wrote exist to compare against the
            # picker stage A/C placed, so this is the earliest the page's one
            # filter-scope ambiguity can be asked -- and the only place it is.
            filter_scope_answer = resolve_filter_scope(
                session, plan.final, chart_specs, design_analysis
            )

            # ---- E: layout ---------------------------------------------------
            session.publish("stage_start", stage="E", label="Laying out the dashboard")
            e_provider = provider_for("E")
            # Same fallbacks as A and F: E is given the design image(s) and
            # only the `Read` tool too, so the identical turn-budget failure
            # reaches it the same way.
            e_provider_lower = _lower_effort_provider(e_provider, "E", session.id)
            e_provider_more_turns = _higher_turns_provider(e_provider, "E", session.id)

            def _lay_out(provider: Any) -> Any:
                return e_layout.run(
                    provider,
                    design_analysis,
                    plan.final,
                    PROMPTS,
                    on_thinking=_thinking_for("E"),
                    image_paths=session.image_paths,
                    user_answers=answers or None,
                )

            layout, cost = _retry(
                session,
                "Laying out the dashboard",
                2,
                lambda: _lay_out(e_provider),
                on_truncated=(
                    (lambda: _lay_out(e_provider_lower))
                    if e_provider_lower is not None
                    else None
                ),
                on_max_turns=(
                    (lambda: _lay_out(e_provider_more_turns))
                    if e_provider_more_turns is not None
                    else None
                ),
            )
            total_cost += cost
            session.artifacts["layout"] = layout
            session.save_stage("E", layout)
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
                    # Rebuilt after stage F, so a custom plugin written this
                    # run has a control panel its saved query is read from.
                    registry=registry,
                    filter_scope_answer=filter_scope_answer,
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
            # A layout node the applier had to drop, or a chart it created
            # despite an unresolved problem, used to reach nobody but the log.
            # Surfaced here so a run that "succeeded" still says what it quietly
            # gave up on.
            if applied.warnings:
                session.publish(
                    "apply_warnings",
                    label="What the applier could not build as planned",
                    warnings=applied.warnings,
                )

            session.publish(
                "stage_start", stage="verify", label="Checking the dashboard renders"
            )
            from superset.design_to_dashboard.verify import (
                confirm_new_plugins,
                verify as verify_dashboard,
            )

            if applied.dashboard_id is None:
                raise RuntimeError("apply succeeded without a dashboard id")
            checks = verify_dashboard(applied.dashboard_id, plan.final, design_analysis)
            session.publish(
                "stage_complete",
                stage="verify",
                label="Checked the dashboard",
                summary=checks.rendering,
                charts=_chart_checks(checks),
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
            # The data API cannot see a script crash and cannot query a custom
            # plugin at all; the browser saw both. Folded into the verify
            # result, so the headline, the result and the trace count a chart
            # that failed to render as broken rather than as working.
            if visual.render:
                checks.apply_render(visual.render)
                session.publish(
                    "stage_start",
                    stage="render",
                    label="Checking how each chart rendered in the browser",
                )
                session.publish(
                    "stage_complete",
                    stage="render",
                    label="Rendered the dashboard in a browser",
                    summary=checks.rendering,
                    charts=_chart_checks(checks),
                    failures=checks.render_failures,
                )

            # Stage F reporting a plugin "built" is not evidence it works --
            # only the registry it actually landed in, and a real render, are.
            # Checked once, here, against the registry snapshot D and E were
            # given and the same render evidence every other chart is judged
            # by, and written to the trace as its own entry rather than left
            # implied by the overall "N/N charts working" summary.
            confirmations = confirm_new_plugins(
                plan.final, registry.viz_types(), checks.charts, applied.ref_to_id
            )
            if confirmations:
                session.publish(
                    "plugin_confirmations",
                    label="Confirming new plugins actually registered and rendered",
                    confirmations=[
                        {
                            "region_id": c.region_id,
                            "viz_type": c.viz_type,
                            "chart_id": c.chart_id,
                            "registered": c.registered,
                            "rendered_ok": c.rendered_ok,
                        }
                        for c in confirmations
                    ],
                )

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
            _photograph_if_approved(session, plan.final, visual.verdict, registry)

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
                "render_failures": checks.render_failures,
                "dev_error_overlay": visual.overlays,
                "fidelity_notes": checks.fidelity_notes,
                "apply_warnings": applied.warnings,
                "not_verified_close_up": visual.not_verified,
                "plugin_confirmations": [
                    {
                        "region_id": c.region_id,
                        "viz_type": c.viz_type,
                        "chart_id": c.chart_id,
                        "registered": c.registered,
                        "rendered_ok": c.rendered_ok,
                    }
                    for c in confirmations
                ],
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
            # Same reasoning for storage: the final status and every event are
            # what a reopened run is redrawn from, so this is the one save that
            # must happen however the run ended.
            session.save()
