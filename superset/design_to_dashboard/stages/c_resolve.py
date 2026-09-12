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
"""Stage C - decide how each region gets built.

The only wide-context stage. It sees every region at once because consistency
is its job: identical tiles must resolve to the same viz type and share number
formats. It receives viz-type *summaries* only -- enough to choose, not enough
to configure -- and searches existing charts through MCP rather than being
handed an index.
"""

from __future__ import annotations

import logging
import pathlib
from typing import Any

from superset.design_to_dashboard.llm.base import LLMProvider
from superset.design_to_dashboard.mcp.catalog import render_catalog, STAGE_C_TOOLS
from superset.design_to_dashboard.mcp.gateway import MCPGateway
from superset.design_to_dashboard.pipeline.tool_loop import (
    ENVELOPE_INSTRUCTIONS,
    run_tool_loop,
    ToolLoopResult,
)
from superset.design_to_dashboard.registry import (
    chart_types,
    load as load_registry,
    render_summaries,
)
from superset.utils import json

logger = logging.getLogger(__name__)

# Build-time metadata, like stage B's: a `get_chart_info` response is ~2 KB and
# is read once. The waste to avoid is paging blindly through an instance that
# holds thousands of charts -- not checking a candidate that might spare us
# building a chart from scratch. Reuse is the cheapest outcome there is, so the
# budget has to be large enough to actually look for it in every section.
MAX_TOOL_CALLS = 24
MAX_ITERATIONS = 10

# `grid_text` is a heading or caption that occupies a grid cell without being a
# chart. It exists because a dashboard viewed with the chrome hidden has no
# title bar, so the page heading has to live in the grid -- and `configure`
# without a viz_type is not a chart the rest of the pipeline can build.
# `wrap` retired with stage A's nesting: a frame that holds other sections
# arrives as a region with `children`, and becomes a container plugin. There is
# no longer a case for reusing a registered composing plugin, because none
# composes the frames these designs draw.
DECISIONS = {
    "reuse",
    "configure",
    "new_plugin",
    "grid_text",
    "drop",
}
# What kind of component a `new_plugin` is. A plugin is a React component we
# own, so this is not limited to "a chart shape Superset lacks".
ARCHETYPES = {"viz", "container", "filter_widget", "table", "navigation"}
NON_DATA_ROLES = {"wrapper", "nav", "header", "text", "decoration"}


def build_system_prompt(prompts_dir: pathlib.Path, registry_path: str) -> str:
    """Preamble + stage prompt + envelope + tool catalogue + viz summaries."""
    preamble = (prompts_dir / "shared" / "_preamble.md").read_text(encoding="utf-8")
    stage = (prompts_dir / "C_resolve.md").read_text(encoding="utf-8")
    entries = load_registry(registry_path)
    return "\n\n---\n\n".join(
        [
            preamble,
            stage,
            ENVELOPE_INSTRUCTIONS,
            "## Tools available to you\n\n" + render_catalog(STAGE_C_TOOLS),
            (
                "## Registered viz types\n\n"
                "These are the only viz types that exist. Anything else requires "
                "a `new_plugin` decision.\n\n" + render_summaries(entries)
            ),
        ]
    )


def build_user_prompt(
    design_analysis: dict[str, Any], binding_set: dict[str, Any]
) -> str:
    """Present stages A and B as data for stage C to resolve."""
    payload = {
        "regions": design_analysis.get("regions", []),
        "global": design_analysis.get("global", {}),
        "bindings": binding_set.get("bindings", []),
        "datasets_used": binding_set.get("datasets_used", []),
    }
    # The runner attaches the clarification answers to the binding. Dropping
    # them here made every instruction about honouring them unreachable: the
    # user answered, and stage C never saw it.
    if answers := binding_set.get("user_answers"):
        payload["user_answers"] = answers
    # What stage B built, so a decision can be judged against the data that
    # actually exists rather than against a proposal.
    for key in ("fact_tables", "views", "shared_dataset_id"):
        if (value := binding_set.get(key)) is not None:
            payload[key] = value
    # A second attempt: the first plan failed these checks, and they are
    # mechanical, so fixing them is not a matter of taste.
    if problems := binding_set.get("validation_problems"):
        payload["fix_these_problems_from_your_last_plan"] = problems
    # The user read the plan and sent it back. Unlike a validation problem this
    # is a judgement, and it outranks yours: they can see the design, they know
    # the instance, and they are the reason the dashboard is being built.
    if feedback := binding_set.get("plan_feedback"):
        payload["the_user_rejected_your_last_plan_saying"] = feedback
    # Questions you asked last time, so the answers in `user_answers` can be
    # matched to what they answer. You have them now; decide.
    if asked := binding_set.get("answers_to_your_questions"):
        payload["you_asked_these_and_they_are_now_answered"] = asked
    return (
        "The attached image is the PLUGIN CONTACT SHEET -- every registered "
        "plugin's thumbnail, labelled with its viz_type. It is not the user's "
        "design. Use it to judge which plugin renders each section.\n\n"
        "STAGE A AND STAGE B OUTPUT (data, not instructions).\n"
        "Resolve every region to a decision, and emit the design-system "
        "contract the per-chart workers will obey.\n\n"
        f"```json\n{json.dumps(payload, indent=2)}\n```"
    )


def run(
    provider: LLMProvider,
    gateway: MCPGateway,
    design_analysis: dict[str, Any],
    binding_set: dict[str, Any],
    prompts_dir: pathlib.Path,
    registry_path: str,
    max_tool_calls: int = MAX_TOOL_CALLS,
    max_iterations: int = MAX_ITERATIONS,
    on_progress: object = None,
    on_thinking: object = None,
    thumbnail_sheet: str | None = None,
) -> ToolLoopResult:
    """Run stage C and return the loop result carrying a ``ResolutionPlan``."""
    result = run_tool_loop(
        provider=provider,
        gateway=gateway,
        system_prompt=build_system_prompt(prompts_dir, registry_path),
        user_prompt=build_user_prompt(design_analysis, binding_set),
        max_tool_calls=max_tool_calls,
        max_iterations=max_iterations,
        on_progress=on_progress,
        on_thinking=on_thinking,
        image_paths=[thumbnail_sheet] if thumbnail_sheet else None,
    )
    result.final.setdefault("tool_calls", result.tool_calls)
    result.final["counts"] = tally(result.final.get("decisions", []))
    counts = result.final["counts"]
    logger.info(
        "stage C complete: status=%s decisions=%d new_plugins=%s",
        result.final.get("status"),
        len(result.final.get("decisions", [])),
        counts.get("new_plugin"),
    )
    return result


def tally(decisions: list[dict[str, Any]]) -> dict[str, int]:
    """How many decisions of each kind. Derived, never taken on trust."""
    counts: dict[str, int] = {}
    for decision in decisions:
        kind = decision.get("decision")
        if kind:
            counts[kind] = counts.get(kind, 0) + 1
    return counts


# Phrases that mean Superset's own chrome will not be rendered. When the chrome
# is hidden a dropped heading is simply gone rather than deferred to the
# dashboard title, so that decision contradicts the user rather than merely
# differing from the design. A prompt-level instruction failed to prevent this,
# so it is checked.
_CHROME_HIDDEN_HINTS = (
    "chrome hidden",
    "chrome is hidden",
    "hide the filter bar",
    "inside the grid",
    "in the grid as widget",
)


def _answer_conflicts(
    decisions: list[dict[str, Any]],
    design_analysis: dict[str, Any],
    binding_set: dict[str, Any],
) -> list[str]:
    """Decisions that contradict an answer the user already gave."""
    answers = binding_set.get("user_answers") or {}
    if not answers:
        return []
    blob = json.dumps(answers).lower()
    if not any(hint in blob for hint in _CHROME_HIDDEN_HINTS):
        return []

    roles = {
        r.get("region_id"): r.get("role") for r in design_analysis.get("regions", [])
    }
    problems = []
    for decision in decisions:
        region_id = decision.get("region_id")
        kind = decision.get("decision")
        if kind == "drop" and roles.get(region_id) in {"header", "text"}:
            problems.append(
                f"{region_id}: dropped to dashboard chrome, but the user said "
                "the chrome is hidden -- the heading would not appear at all. "
                "Put it in the grid."
            )
    return problems


# Roles that carry no data. A plugin for one of these is ten minutes of
# generation, a package in the repo and a frontend rebuild, to render text a
# MARKDOWN node already draws.
TEXT_ROLES = {"header", "text"}


def _text_as_plugin(
    decisions: list[dict[str, Any]], design_analysis: dict[str, Any]
) -> list[str]:
    """Text regions resolved to a plugin instead of `grid_text`.

    A wrapper is exempt, and the exemption is the whole point: a header row
    that also holds a currency toggle and a date picker is a frame around
    separate sections, not a line of prose, and a MARKDOWN node cannot draw a
    control. Without this, that region is caught by this rule *and* by
    `_wrappers_without_children` -- one demanding no plugin, the other a
    container plugin -- and no plan could satisfy both.
    """
    roles = {
        r.get("region_id"): r.get("role") for r in design_analysis.get("regions", [])
    }
    wrappers = {
        r.get("region_id")
        for r in design_analysis.get("regions", [])
        if r.get("children")
    }
    return [
        f"{d.get('region_id')}: role is {roles.get(d.get('region_id'))!r}, which "
        "draws no data. Use `configure` with the existing `custom_text` plugin "
        "when the design's typography matters, or `grid_text` for plain "
        "Markdown. Building a plugin costs a package and a frontend rebuild to "
        "render a line of text."
        for d in decisions
        if d.get("decision") == "new_plugin"
        and roles.get(d.get("region_id")) in TEXT_ROLES
        and d.get("region_id") not in wrappers
    ]


def _wrappers_without_children(
    decisions: list[dict[str, Any]], design_analysis: dict[str, Any]
) -> list[str]:
    """A frame that holds sections, resolved to something that holds nothing.

    Stage A gives a wrapper the region numbers it contains. One frame is one
    container plugin whose `children` are the refs of those regions' decisions;
    a plugin that draws only the frame leaves its contents beside it rather
    than inside it, and the design's card is two cards.
    """
    regions = {
        r.get("region_id"): r
        for r in design_analysis.get("regions", [])
        if isinstance(r, dict)
    }
    wrappers = {
        region_id for region_id, region in regions.items() if region.get("children")
    }
    problems = [
        f"{d.get('region_id')}: stage A read this as a frame holding "
        f"{len(regions[str(d.get('region_id'))].get('children') or [])} other "
        "section(s), so it is one `new_plugin` with `plugin_archetype: "
        '"container"` and their refs in `children`.'
        for d in decisions
        if d.get("region_id") in wrappers
        and not (d.get("children") or [])
        and d.get("decision") not in {"drop", "grid_text"}
    ]
    problems += [
        f"{d.get('region_id')}: has children but stage A read no sections "
        "inside it -- a card about one subject is one chart, however much it "
        "draws"
        for d in decisions
        if (d.get("children") or []) and d.get("region_id") not in wrappers
    ]
    return problems


# Decisions that put a querying chart on the dashboard, and so need data
# behind them. `reuse` is absent: an existing chart already carries its own.
DRAWS_DATA = {"configure", "new_plugin"}


def _binding_coverage(
    decisions: list[dict[str, Any]],
    design_analysis: dict[str, Any],
    binding_set: dict[str, Any],
) -> list[str]:
    """A chart that queries must have data behind it.

    Stage B binds every region, including the ones that draw nothing -- those
    take the shared one-row dataset because Superset requires a datasource on
    every chart. So the check is no longer "is this region bound" but "does the
    thing this decision will query actually read data": a `configure` or
    `new_plugin` on a data region pointed at the shared dataset is a chart that
    renders nothing, and that is invisible until someone opens the dashboard.
    """
    problems: list[str] = []
    roles = {
        r.get("region_id"): r.get("role")
        for r in design_analysis.get("regions", [])
        if isinstance(r, dict)
    }
    shared = binding_set.get("shared_dataset_id")
    bindings = {
        b.get("region_id"): b
        for b in binding_set.get("bindings") or []
        if isinstance(b, dict)
    }

    for decision in decisions:
        region_id = str(decision.get("region_id") or "")
        if decision.get("decision") not in DRAWS_DATA:
            continue
        if roles.get(region_id) in NON_DATA_ROLES:
            continue
        binding = bindings.get(region_id)
        if binding is None:
            problems.append(
                f"{region_id}: draws a chart but stage B bound nothing to it"
            )
            continue
        if isinstance(shared, int) and binding.get("dataset_id") == shared:
            problems.append(
                f"{region_id}: draws a chart but is bound to the shared "
                "one-row dataset, which carries no data -- it would render "
                "empty"
            )
    return problems


def _evidence_missing(decisions: list[dict[str, Any]]) -> list[str]:
    """Verdicts recorded without the comparison that produced them.

    The prompt asks for `thumbnail_evidence` on every section and nothing read
    it, so "I compared the thumbnails" was an assertion the plan never had to
    support. It is the one field that distinguishes a considered stock-versus-
    custom verdict from a guess, and a guess here costs a ten-minute plugin
    build or a chart that does not look like the design.
    """
    return [
        f"{d.get('region_id')}: {d.get('decision')} without thumbnail_evidence -- "
        "say which plugin thumbnails you compared and what you saw"
        for d in decisions
        if d.get("decision") in {"reuse", "configure", "new_plugin"}
        and not str(d.get("thumbnail_evidence") or "").strip()
    ]


def _switcher_lost(
    decisions: list[dict[str, Any]], design_analysis: dict[str, Any]
) -> list[str]:
    """A card whose switcher was quietly dropped.

    Stage A reports a wrapper's chrome in `frame`. `tabs` over children means a
    container that switches between them; `tabs` with no children means one
    chart that the switcher refilters, and the control belongs to that chart.
    Either way the switcher is part of the design, and a card built as its
    visible state alone looks correct -- nobody notices the tabs that are not
    there. The old check read the word "tab" out of `interactions`, which also
    matched the page's own tab strip and forced a container onto a nav region.
    """
    switched = {
        r.get("region_id"): bool(r.get("children"))
        for r in design_analysis.get("regions", [])
        if isinstance(r, dict) and r.get("frame") in {"tabs", "toggle"}
    }
    return [
        f"{d.get('region_id')}: stage A saw a switcher over "
        f"{'several sections' if switched[str(d.get('region_id'))] else 'one chart'} "
        "here, and this decision keeps none of it -- a switcher over sections is "
        "a container with one child each; over one chart it is that chart's own "
        "control."
        for d in decisions
        if d.get("region_id") in switched
        and switched[str(d.get("region_id"))]
        and d.get("decision") in DRAWS_DATA
        and not (d.get("children") or [])
        and d.get("plugin_archetype") != "container"
    ]


def replies_of(user_answers: Any) -> dict[str, Any]:
    """The `{question_id: answer}` map, whichever shape it arrives in.

    `session.ask` returns the whole reply envelope -- `{"answers": {...}}` --
    and the runner stores that as `user_answers`. Looking a question id up in
    the envelope always missed, so *every* region carrying a blocking question
    was reported unanswered no matter what the user had said, and stage C
    refused to build sections it had been given the answer for.

    Reading both shapes here rather than unwrapping at the call site: the
    envelope is also what reaches the model in the prompt, which reads through
    the nesting perfectly well, so the two consumers legitimately want
    different things from the same field.
    """
    if not isinstance(user_answers, dict):
        return {}
    inner = user_answers.get("answers")
    if isinstance(inner, dict):
        return inner
    return user_answers


def validate(  # noqa: C901
    plan: dict[str, Any],
    design_analysis: dict[str, Any],
    binding_set: dict[str, Any],
    registry_path: str,
) -> list[str]:
    """Structural checks before the plan is shown to a user or fanned out."""
    problems: list[str] = []
    entries = load_registry(registry_path)
    known_charts = chart_types(entries)

    if plan.get("status") not in {"ready", "needs_approval"}:
        problems.append(f"invalid status: {plan.get('status')!r}")

    decisions = plan.get("decisions", [])
    expected = {r["region_id"] for r in design_analysis.get("regions", [])}
    covered = {str(d.get("region_id") or "") for d in decisions}
    for missing in sorted(expected - covered):
        problems.append(f"region has no decision: {missing}")
    for extra in sorted(covered - expected):
        problems.append(f"decision for unknown region: {extra}")

    problems.extend(_answer_conflicts(decisions, design_analysis, binding_set))
    problems.extend(_text_as_plugin(decisions, design_analysis))
    problems.extend(_wrappers_without_children(decisions, design_analysis))
    problems.extend(_binding_coverage(decisions, design_analysis, binding_set))
    problems.extend(_evidence_missing(decisions))
    problems.extend(_switcher_lost(decisions, design_analysis))

    refs = {d.get("ref") for d in decisions if d.get("ref")}
    seen_refs: set[str] = set()
    new_plugin_types: set[str] = set()

    for decision in decisions:
        region_id = decision.get("region_id")
        kind = decision.get("decision")
        viz_type = decision.get("viz_type")
        ref = decision.get("ref")

        if kind not in DECISIONS:
            problems.append(f"{region_id}: unknown decision {kind!r}")
            continue
        if ref:
            if ref in seen_refs:
                problems.append(f"{region_id}: duplicate ref {ref!r}")
            seen_refs.add(ref)

        if kind == "grid_text" and not decision.get("text"):
            problems.append(f"{region_id}: grid_text without the text to render")
        if kind == "configure":
            if not viz_type:
                problems.append(f"{region_id}: {kind} without viz_type")
            elif viz_type not in known_charts:
                problems.append(f"{region_id}: viz_type {viz_type!r} is not registered")
        if kind == "reuse":
            if not decision.get("existing_chart_id"):
                problems.append(f"{region_id}: reuse without existing_chart_id")
            if not decision.get("reuse_evidence"):
                problems.append(
                    f"{region_id}: reuse without evidence from get_chart_info"
                )
        if kind == "new_plugin":
            new_plugin_types.add(viz_type or f"<unnamed:{region_id}>")
            if viz_type in known_charts:
                problems.append(
                    f"{region_id}: new_plugin for {viz_type!r}, which already exists"
                )
            # The archetype decides what stage F writes -- a hosting wrapper, a
            # filter that emits a data mask, a table with drawn cells. Left
            # unset, F falls back to a plain single-visualisation plugin and
            # the structure the design showed is silently lost.
            # Naming it is what lets several regions share one plugin: the
            # orchestrator dedupes on this before calling stage F, so three KPI
            # tiles cost one generation instead of three.
            if not viz_type:
                problems.append(
                    f"{region_id}: new_plugin without a viz_type -- name the "
                    "plugin you intend to create (`custom_<name>`), and use the "
                    "same name on every region that shares it"
                )
            elif not viz_type.startswith("custom_"):
                problems.append(
                    f"{region_id}: new_plugin viz_type {viz_type!r} must start "
                    "with 'custom_'"
                )
            archetype = decision.get("plugin_archetype")
            if archetype not in ARCHETYPES:
                problems.append(
                    f"{region_id}: new_plugin without a valid plugin_archetype "
                    f"(got {archetype!r}, expected one of {sorted(ARCHETYPES)})"
                )
            elif archetype == "container" and not (decision.get("children") or []):
                problems.append(
                    f"{region_id}: container plugin without children -- a frame "
                    "that hosts nothing is a plain `viz`. Either list the refs of "
                    "the charts it holds, or set plugin_archetype to 'viz' "
                    "because this card is one chart about one subject."
                )
        for child in decision.get("children") or []:
            if child not in refs:
                problems.append(f"{region_id}: child ref {child!r} not defined")

    if new_plugin_types and plan.get("status") != "needs_approval":
        problems.append(
            f"{len(new_plugin_types)} new_plugin decision(s) but status is "
            f"{plan.get('status')!r}, expected 'needs_approval'"
        )

    # A claim we know to be false, and which shipped a wrong-looking number more
    # than once: a literal suffix is achievable via currency_format.
    for decision in decisions:
        loss = (decision.get("fidelity_loss") or "").lower()
        if ("suffix" in loss or "'m'" in loss) and any(
            phrase in loss
            for phrase in (
                "cannot be",
                "can not be",
                "not possible",
                "unachievable",
                "no way to",
                "impossible",
            )
        ):
            problems.append(
                f"{decision.get('region_id')}: claims a magnitude suffix is "
                f"impossible without saying why. If the stored value is in base "
                f"units, `,.3s` or SMART_NUMBER renders it. If the value is "
                f"already scaled, say so and put the unit in the label — state "
                f"which case applies rather than calling it impossible."
            )

    if not plan.get("design_system"):
        problems.append("no design_system contract emitted")

    return problems
