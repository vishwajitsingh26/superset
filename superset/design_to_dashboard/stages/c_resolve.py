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
    filter_types,
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
DECISIONS = {
    "reuse",
    "configure",
    "wrap",
    "new_plugin",
    "native_filter",
    "grid_text",
    "drop",
}
# What kind of component a `new_plugin` is. A plugin is a React component we
# own, so this is not limited to "a chart shape Superset lacks".
ARCHETYPES = {"viz", "composite", "filter_widget", "table", "navigation"}
NON_DATA_ROLES = {"nav", "header", "text", "decoration"}


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
    if datasets := binding_set.get("created_datasets"):
        payload["created_datasets"] = datasets
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
    counts = result.final.get("counts", {})
    logger.info(
        "stage C complete: status=%s decisions=%d new_plugins=%s",
        result.final.get("status"),
        len(result.final.get("decisions", [])),
        counts.get("new_plugin"),
    )
    return result


# Phrases that mean Superset's own chrome will not be rendered. When the chrome
# is hidden a `native_filter` is invisible and a dropped heading is simply gone,
# so those decisions contradict the user rather than merely differing from the
# design. Two prompt-level instructions failed to prevent this, so it is checked.
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
        if kind == "native_filter":
            problems.append(
                f"{region_id}: native_filter, but the user said the dashboard "
                "chrome is hidden -- the filter bar will not render, so this "
                "filter would be invisible. Use a chart_widget in the grid."
            )
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
    """Text regions resolved to a plugin instead of `grid_text`."""
    roles = {
        r.get("region_id"): r.get("role") for r in design_analysis.get("regions", [])
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
    ]


def _split_composites(
    decisions: list[dict[str, Any]], design_analysis: dict[str, Any]
) -> list[str]:
    """Composite regions that became a plugin drawing nothing.

    Stage A marks a card holding several things `composition: composite`. One
    card is one plugin with `children`; splitting it into a frame plugin plus
    sibling plugins for its contents produces two packages and two charts where
    the design draws one card, with the contents beside the frame rather than
    inside it.
    """
    composite = {
        r.get("region_id")
        for r in design_analysis.get("regions", [])
        if r.get("composition") == "composite"
    }
    return [
        f"{d.get('region_id')}: stage A read this as a composite -- one card "
        "holding several things -- so it is one `new_plugin` with "
        '`plugin_archetype: "composite"` and its contents in `children`, '
        "not a plugin that draws only the frame."
        for d in decisions
        if d.get("decision") == "new_plugin"
        and d.get("region_id") in composite
        and d.get("plugin_archetype") != "composite"
        and not (d.get("children") or [])
    ]


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
    known_filters = set(filter_types(entries))

    if plan.get("status") not in {"ready", "needs_approval"}:
        problems.append(f"invalid status: {plan.get('status')!r}")

    decisions = plan.get("decisions", [])
    expected = {r["region_id"] for r in design_analysis.get("regions", [])}
    covered = {d.get("region_id") for d in decisions}
    for missing in sorted(expected - covered):
        problems.append(f"region has no decision: {missing}")
    for extra in sorted(covered - expected):
        problems.append(f"decision for unknown region: {extra}")

    bound_states = {
        b.get("region_id"): b.get("state") for b in binding_set.get("bindings", [])
    }
    problems.extend(_answer_conflicts(decisions, design_analysis, binding_set))
    problems.extend(_text_as_plugin(decisions, design_analysis))
    problems.extend(_split_composites(decisions, design_analysis))

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
        if kind in {"configure", "wrap"}:
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
            elif archetype == "composite" and not (decision.get("children") or []):
                problems.append(
                    f"{region_id}: composite plugin without children -- a wrapper "
                    "that hosts nothing is a plain viz plugin"
                )
        if kind == "wrap":
            children = decision.get("children") or []
            if not children:
                problems.append(f"{region_id}: wrap without children")
            for child in children:
                if child not in refs:
                    problems.append(f"{region_id}: child ref {child!r} not defined")
        if kind != "drop" and bound_states.get(region_id) == "unavailable":
            problems.append(
                f"{region_id}: binding is unavailable but decision is {kind!r}"
            )

    # A wrap parent must come after its children so the applier can build in order.
    order = {d.get("ref"): i for i, d in enumerate(decisions) if d.get("ref")}
    for decision in decisions:
        if decision.get("decision") != "wrap":
            continue
        parent_index = order.get(decision.get("ref"), -1)
        for child in decision.get("children") or []:
            if order.get(child, 10**6) > parent_index:
                problems.append(
                    f"{decision.get('region_id')}: child {child!r} is ordered "
                    f"after its wrap parent"
                )

    for native in plan.get("native_filters", []):
        filter_type = native.get("filterType")
        if filter_type not in known_filters:
            problems.append(
                f"native filter {native.get('name')!r}: unknown filterType "
                f"{filter_type!r} (known: {sorted(known_filters)})"
            )

    counts = plan.get("counts", {})
    actual: dict[str, int] = {}
    for decision in decisions:
        kind = decision.get("decision")
        actual[kind] = actual.get(kind, 0) + 1
    for kind, number in actual.items():
        if counts.get(kind) not in (None, number):
            problems.append(
                f"counts.{kind} is {counts.get(kind)} but {number} decisions say {kind}"
            )

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
