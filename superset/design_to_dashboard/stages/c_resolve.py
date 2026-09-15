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

from superset.design_to_dashboard import chrome
from superset.design_to_dashboard.llm.base import LLMProvider
from superset.design_to_dashboard.mcp.catalog import render_catalog, STAGE_C_TOOLS
from superset.design_to_dashboard.mcp.gateway import MCPGateway
from superset.design_to_dashboard.pipeline.tool_loop import (
    ENVELOPE_INSTRUCTIONS,
    run_tool_loop,
    ToolLoopResult,
)
from superset.design_to_dashboard.registry import chart_types, Registry, RegistryError
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
ARCHETYPES = {"viz", "container", "filter_widget", "table", "navigation", "map"}
NON_DATA_ROLES = {"wrapper", "nav", "header", "text", "decoration"}


def build_system_prompt(
    prompts_dir: pathlib.Path,
    registry: Registry,
    design_analysis: dict[str, Any] | None = None,
) -> str:
    """Preamble, stage, envelope, tools, viz summaries and capability cards.

    The cards are for the types C is likely to weigh: every stock type stage A
    named, the stock types designs use most, and every custom plugin already
    in the registry -- a reuse candidate on some region every run, not only
    where A happened to name one. A thumbnail shows one way a chart was set
    up; a card says what every setting can make it show, and what none can.
    Any other stock type's card is one tool call away.
    """
    preamble = (prompts_dir / "shared" / "_preamble.md").read_text(encoding="utf-8")
    stage = (prompts_dir / "C_resolve.md").read_text(encoding="utf-8")
    parts = [
        preamble,
        stage,
        ENVELOPE_INSTRUCTIONS,
        "## Tools available to you\n\n" + render_catalog(STAGE_C_TOOLS),
        (
            "## Registered viz types\n\n"
            "These are the only viz types that exist. Anything else requires "
            "a `new_plugin` decision.\n\n" + registry.stage_c_text()
        ),
    ]
    if cards := registry.capability_cards(
        registry.card_shortlist(design_analysis or {})
    ):
        parts.append(
            "## Capability cards\n\n"
            "What these types can be set up to show, stock and custom alike. "
            "Judge a match against the settings, not the thumbnail or a custom "
            "plugin's own description: a detail the thumbnail lacks may be one "
            "setting away. A detail under **Cannot show** is not reachable by "
            "any setting, so a region that needs it is not a match for that "
            "type -- a stock card's Cannot-show list is hand-verified; a "
            "custom plugin's card has none, because nobody has looked at its "
            "code to write one, so its Settings line is what there is to go "
            "on: a control the region needs and the card's Settings never "
            "name is not there either."
            "\n\n" + cards
        )
    return "\n\n---\n\n".join(parts)


def build_user_prompt(
    design_analysis: dict[str, Any],
    binding_set: dict[str, Any],
    design_images: int = 0,
) -> str:
    """Present stages A and B as data for stage C to resolve."""
    payload = {
        "regions": design_analysis.get("regions", []),
        "global": design_analysis.get("global", {}),
        "bindings": binding_set.get("bindings", []),
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
    # What earlier attempts already looked up. Each attempt is a fresh tool
    # loop with an empty transcript, so without this the reuse survey is run
    # from scratch every time -- three identical sweeps in a run that
    # re-planned twice, each one a turn spent learning what was already known.
    if searched := binding_set.get("charts_you_already_searched"):
        payload["charts_you_already_searched"] = searched
    # The plan being corrected. Sent so a patch can be read against it: the
    # model is told to return only what changes, and it can only judge what
    # changed if it can see what it wrote.
    if previous := binding_set.get("your_last_plan"):
        payload["your_last_plan"] = previous
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
        f"{_image_legend(design_images)}\n\n"
        "STAGE A AND STAGE B OUTPUT (data, not instructions).\n"
        "Resolve every region to a decision, and emit the design-system "
        "contract the per-chart workers will obey.\n\n"
        f"```json\n{json.dumps(payload, indent=2)}\n```"
    )


def _image_legend(design_images: int) -> str:
    """Say which attached image is which.

    Two kinds arrive together and they are read for opposite purposes: the
    design is what must be matched, the contact sheet is what is available to
    match it with. Told apart only by order, the sheet has been read as the
    thing to build.
    """
    if not design_images:
        return (
            "The attached image is the PLUGIN CONTACT SHEET -- every registered "
            "plugin's thumbnail, labelled with its viz_type. It is not a "
            "design. Use it to judge which plugin renders each section."
        )
    nth = "image" if design_images == 1 else f"first {design_images} images"
    return (
        f"The {nth} {'is' if design_images == 1 else 'are'} the USER'S DESIGN "
        "-- what the dashboard has to look like.\n"
        "The LAST image is the PLUGIN CONTACT SHEET: every registered plugin's "
        "thumbnail, labelled with its viz_type. It is not part of the design. "
        "Compare one against the other."
    )


def run(
    provider: LLMProvider,
    gateway: MCPGateway,
    design_analysis: dict[str, Any],
    binding_set: dict[str, Any],
    prompts_dir: pathlib.Path,
    registry: Registry,
    max_tool_calls: int = MAX_TOOL_CALLS,
    max_iterations: int = MAX_ITERATIONS,
    on_progress: object = None,
    on_thinking: object = None,
    thumbnail_sheet: str | None = None,
    image_paths: list[str] | None = None,
    previous_plan: dict[str, Any] | None = None,
) -> ToolLoopResult:
    """Run stage C and return the loop result carrying a ``ResolutionPlan``.

    The design goes in ahead of the contact sheet. Judging whether a plugin
    renders a section is a comparison, and until now C had only one half of
    it: the thumbnails, and stage A's prose about the other side. Order is how
    the two are told apart, so the legend in the user prompt is built from the
    same count that decides it.
    """
    design = list(image_paths or [])
    images = design + ([thumbnail_sheet] if thumbnail_sheet else [])
    result = run_tool_loop(
        provider=provider,
        gateway=gateway,
        system_prompt=build_system_prompt(prompts_dir, registry, design_analysis),
        user_prompt=build_user_prompt(design_analysis, binding_set, len(design)),
        max_tool_calls=max_tool_calls,
        max_iterations=max_iterations,
        on_progress=on_progress,
        on_thinking=on_thinking,
        image_paths=images or None,
    )
    # A patch is made whole before anything reads it, so `counts` is tallied
    # over the merged decisions and every caller still receives a complete plan.
    if previous_plan:
        result.final = merge_patch(previous_plan, result.final)
    result.final.setdefault("tool_calls", result.tool_calls)
    result.final["counts"] = tally(result.final.get("decisions", []))
    annotate_comparisons(result.final.get("decisions", []), registry)
    # This attempt's own tool calls, merged with whatever earlier attempts
    # already found -- the same transcript `runner.py` threads into
    # `validate()` for `_reuse_unconfirmed_by_search`, computed here too so a
    # `reuse` decision carries its confirming evidence from the moment the
    # plan exists, not only once the orchestrator gets around to checking it.
    searched = chart_searches(
        result.transcript, binding_set.get("charts_you_already_searched")
    )
    annotate_reuse_evidence(result.final.get("decisions", []), searched)
    counts = result.final["counts"]
    logger.info(
        "stage C complete: status=%s decisions=%d new_plugins=%s",
        result.final.get("status"),
        len(result.final.get("decisions", [])),
        counts.get("new_plugin"),
    )
    return result


# The tools that answer "does a chart for this already exist". Their results are
# carried between attempts; nothing else about a transcript is worth repeating.
CHART_TOOLS = {"list_charts", "get_chart_info"}


def chart_searches(
    transcript: list[dict[str, Any]],
    already: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Every chart lookup an attempt made, merged with what earlier ones found.

    Deduplicated on the tool and its arguments. A replan re-ran the same
    searches because its loop starts empty, and a record that repeats them
    would answer a question the model is being told not to ask again.
    """

    def signature(entry: dict[str, Any]) -> str:
        return json.dumps(
            [entry.get("tool"), entry.get("arguments")], sort_keys=True, default=str
        )

    merged = {signature(entry): entry for entry in already or []}
    for round_ in transcript or []:
        if not isinstance(round_, dict):
            continue
        calls = {
            call.get("id"): call
            for call in round_.get("tool_calls") or []
            if isinstance(call, dict)
        }
        for observation in round_.get("observations") or []:
            if not isinstance(observation, dict):
                continue
            call = calls.get(observation.get("id")) or {}
            tool = observation.get("tool") or call.get("tool")
            if tool not in CHART_TOOLS:
                continue
            entry = {
                "tool": tool,
                "arguments": call.get("arguments"),
                "result": observation.get("result"),
                "error": observation.get("error"),
            }
            merged[signature(entry)] = entry
    return list(merged.values())


def merge_patch(previous: dict[str, Any], reply: dict[str, Any]) -> dict[str, Any]:
    """A patched plan, whole again.

    A correction touches one or two regions, and re-emitting the other fourteen
    to carry them cost minutes of generation and bought nothing. So a replan may
    return only what it changed; everything it leaves out is taken from the plan
    it was correcting, and the result is validated in full exactly as before.

    Decisions merge by `region_id`, and `plan_for_review` steps merge by
    `step`, both in the previous plan's order -- because both are lists of
    discrete, already-numbered parts, not one document that a fix rewrites
    end to end. A patch answering one question sent back one step, meaning to
    explain what changed; replacing the whole list with it silently dropped
    the other thirteen the user had already been shown, and they never came
    back. `design_system` has no such natural key -- a colour or a corner
    radius is not a numbered part of it -- so it stays a whole-document
    replace: any other field the reply carries replaces its predecessor
    whole.

    A field left out of the reply is not the same as one sent back `null`, but
    a model asked to omit what it did not change has sent `null` instead --
    for `design_system`, for `plan_for_review` -- and each has reached a later
    stage, or the user, as nothing at all. Both read the same here: carry the
    previous value forward either way. A patch that genuinely means to clear a
    field has no reason to when the alternative is simply not sending it.
    """
    if reply.get("revision") != "patch" or not previous:
        return reply

    merged = {
        **previous,
        **{
            k: v
            for k, v in reply.items()
            if k not in ("decisions", "plan_for_review") and v is not None
        },
    }
    by_region: dict[str, dict[str, Any]] = {
        str(d.get("region_id")): d
        for d in previous.get("decisions") or []
        if isinstance(d, dict)
    }
    carried = len(by_region)
    changed = 0
    for decision in reply.get("decisions") or []:
        if not isinstance(decision, dict):
            continue
        by_region[str(decision.get("region_id"))] = decision
        changed += 1
    merged["decisions"] = list(by_region.values())

    by_step: dict[Any, dict[str, Any]] = {
        step.get("step"): step
        for step in previous.get("plan_for_review") or []
        if isinstance(step, dict)
    }
    for step in reply.get("plan_for_review") or []:
        if isinstance(step, dict):
            by_step[step.get("step")] = step
    if by_step:
        merged["plan_for_review"] = sorted(
            by_step.values(), key=lambda s: (s.get("step") is None, s.get("step"))
        )
    logger.info(
        "stage C returned a patch: %d decision(s) changed, %d carried over",
        changed,
        max(carried - changed, 0),
    )
    return merged


# What kind of chart a decision actually produces. Named plainly, for the
# trace, rather than left as the pair (`decision`, `viz_type`) a reader would
# otherwise have to cross-reference against the registry by hand:
#   - "stock": a registered Superset viz type, not built by any run.
#   - "custom_reuse": a custom plugin an earlier run already built, reused
#     rather than paid for again.
#   - "custom_new": a plugin this run is about to build; no card exists yet.
#   - "existing_chart": a saved chart instance, not just a viz type, reused
#     whole -- `reuse`'s own `existing_chart_id` already names it.
CHART_KIND_STOCK = "stock"
CHART_KIND_CUSTOM_REUSE = "custom_reuse"
CHART_KIND_CUSTOM_NEW = "custom_new"
CHART_KIND_EXISTING_CHART = "existing_chart"


def chart_kind(decision: dict[str, Any], registry: Registry) -> str | None:
    """Which of the four kinds of chart this decision produces, or None.

    `None` for a decision with no chart at all (`grid_text`, `drop`). Derived
    from the registry rather than taken from the decision: a model can call
    anything a match, but whether `viz_type` shipped with Superset or was
    built by an earlier run is a fact on disk, not a claim to trust.
    """
    kind = decision.get("decision")
    if kind == "reuse":
        return CHART_KIND_EXISTING_CHART
    if kind == "new_plugin":
        return CHART_KIND_CUSTOM_NEW
    if kind == "configure":
        try:
            entry = registry.find(str(decision.get("viz_type") or ""))
        except RegistryError:
            return None
        return CHART_KIND_CUSTOM_REUSE if entry.get("custom") else CHART_KIND_STOCK
    return None


def annotate_comparisons(decisions: list[dict[str, Any]], registry: Registry) -> None:
    """Attach, in place, what kind of chart each decision produced and the
    capability card actually available to compare it against.

    Mechanical, not asked of the model, for the same reason `tally` is: a
    decision's `thumbnail_evidence` is the model's own account of what it
    compared; this is the account a trace reader can check that account
    against -- the exact card text this run's registry held for the
    `viz_type` it settled on. A `new_plugin` decision gets a kind and no
    card: none exists until stage F builds one.
    """
    for decision in decisions:
        kind = chart_kind(decision, registry)
        if kind is None:
            continue
        decision["chart_kind"] = kind
        if kind not in (CHART_KIND_STOCK, CHART_KIND_CUSTOM_REUSE):
            continue
        try:
            decision["capability_card_compared"] = registry.capability_card(
                str(decision.get("viz_type") or "")
            )
        except RegistryError:
            decision["capability_card_compared"] = None


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
# HEADER node or custom_text already draws.
TEXT_ROLES = {"header", "text"}


def _text_as_plugin(
    decisions: list[dict[str, Any]], design_analysis: dict[str, Any]
) -> list[str]:
    """Text regions resolved to a plugin instead of `grid_text`.

    A wrapper is exempt, and the exemption is the whole point: a header row
    that also holds a currency toggle and a date picker is a frame around
    separate sections, not a line of prose, and neither a `HEADER` node nor
    `custom_text` can draw a control. Without this, that region is caught by
    this rule *and* by `_wrappers_without_children` -- one demanding no
    plugin, the other a container plugin -- and no plan could satisfy both.
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
            if roles.get(region_id) == "filter":
                # A control is built, not dropped, so saying only that the
                # binding is wrong leaves the one legal move unstated -- and a
                # plan that cannot see it oscillates between rebuilding the
                # control and deleting it until the attempts run out.
                problems.append(
                    f"{region_id}: a control reads data like any chart, and the "
                    "shared one-row dataset gives it none. A date or time range "
                    "wants the one-row view carrying `range_start` and "
                    "`range_end`, so its calendar knows the window the data "
                    "covers; a select wants a view of the values it offers. "
                    "Bind it to that view, or fold the control into a region "
                    "that has one."
                )
            else:
                problems.append(
                    f"{region_id}: draws a chart but is bound to the shared "
                    "one-row dataset, which carries no data -- it would render "
                    "empty"
                )
    return problems


# Words that mean a decision is deliberately breaking up one of stage A's
# component groups, rather than having forgotten it was a group. Splitting is
# allowed -- A judged by pixels and C judges by what one component can render
# -- but it costs a second plugin, so it has to be said out loud.
_SPLIT_WORDS = (
    "split",
    "differ",
    "separate",
    "unlike",
    "behaviour",
    "behavior",
    "drill",
    "not the same component",
)


def same_as_groups(design_analysis: dict[str, Any]) -> dict[str, list[str]]:
    """Public alias of `_same_as_groups`.

    Stage D keys its own cross-chart consistency pass off exactly the
    grouping this stage already computes for `_component_groups_split` and
    `_shared_plugin_shapes` -- rederiving `same_as` membership a second time
    would be the same traversal maintained in two places, and the two would
    drift the moment one of them changed. `_same_as_groups` stays the name
    used within this module; this is only the seam another stage imports
    through.
    """
    return _same_as_groups(design_analysis)


def _same_as_groups(design_analysis: dict[str, Any]) -> dict[str, list[str]]:
    """Stage A's repeated components, as leader -> every region_id in it."""
    by_number: dict[int, dict[str, Any]] = {}
    for region in design_analysis.get("regions", []):
        if isinstance(region, dict) and isinstance(region.get("n"), int):
            by_number[region["n"]] = region

    groups: dict[str, list[str]] = {}
    for region in by_number.values():
        leader = region.get("same_as") or region.get("n")
        head = by_number.get(leader if isinstance(leader, int) else -1)
        if head is None or not head.get("region_id") or not region.get("region_id"):
            continue
        groups.setdefault(str(head["region_id"]), []).append(str(region["region_id"]))
    return {head: ids for head, ids in groups.items() if len(ids) > 1}


def _component_groups_split(
    decisions: list[dict[str, Any]],
    design_analysis: dict[str, Any],
    binding_set: dict[str, Any] | None = None,
) -> list[str]:
    """A component stage A saw drawn several times, resolved to several plugins.

    `same_as` exists so six copies of one card cost one plugin. Giving the
    copies different viz types costs a generation and a package each, and
    nothing downstream notices -- the orchestrator dedupes on the name stage C
    chose, so three names mean three builds of the same component.

    Splitting is a real answer when one copy needs behaviour the others do not.
    It just has to be said, because the cost lands ten minutes later in a stage
    that cannot see why -- unless the bindings already say it. Copies reading
    a different number of measures are different components whatever they look
    like, and `_shared_plugin_shapes` demands that split, so it needs no words.
    Only that split: copies reading the same number are still held to one
    viz_type among themselves, or to a reason.
    """
    measures = _measure_counts(binding_set or {})
    viz_by_region = {
        str(d.get("region_id")): d.get("viz_type")
        for d in decisions
        if d.get("decision") in DRAWS_DATA
    }
    reason_by_region = {
        str(d.get("region_id")): str(d.get("rationale") or "").lower()
        for d in decisions
    }

    problems: list[str] = []
    for head, members in sorted(_same_as_groups(design_analysis).items()):
        drawn = [m for m in members if m in viz_by_region]
        counts = {measures[m] for m in drawn if m in measures}
        # An unbound copy belongs with the others when they agree on a count;
        # against several counts there is no telling which it is.
        default = next(iter(counts)) if len(counts) == 1 else None
        by_count: dict[int | None, list[str]] = {}
        for member in drawn:
            by_count.setdefault(measures.get(member, default), []).append(member)
        for count, bucket in sorted(
            by_count.items(), key=lambda item: (item[0] is None, item[0] or 0)
        ):
            chosen = {viz_by_region[m] for m in bucket}
            if len(chosen) < 2:
                continue
            if all(
                any(word in reason_by_region.get(m, "") for word in _SPLIT_WORDS)
                for m in bucket
            ):
                continue
            which = (
                "they"
                if len(by_count) == 1
                else f"{', '.join(sorted(bucket))}, reading {count} measure(s) each,"
            )
            problems.append(
                f"{head}: stage A read {len(members)} regions as the same "
                f"component ({', '.join(sorted(members))}) but {which} resolve to "
                f"{len(chosen)} viz types "
                f"({', '.join(sorted(str(c) for c in chosen))}). "
                "Give them one viz_type, or say in every rationale what makes "
                "them different components -- each extra name is another "
                "plugin built."
            )
    return problems


def _measure_counts(binding_set: dict[str, Any]) -> dict[str, int]:
    """How many measures each bound region reads, by region_id."""
    return {
        str(binding.get("region_id")): len(binding.get("measures") or [])
        for binding in binding_set.get("bindings") or []
        if isinstance(binding, dict) and binding.get("region_id")
    }


def _shared_plugin_shapes(
    decisions: list[dict[str, Any]], binding_set: dict[str, Any]
) -> list[str]:
    """One new plugin shared by regions that read different numbers of measures.

    A shared plugin is written from one member's region and binding, so its
    metric controls are that member's measures. A sibling with fewer is left
    holding an empty metric control the plugin reads anyway -- a thrown error
    in one chart is an overlay across the whole dashboard -- and one with more
    has nowhere to put the rest. Text, colour and labels are props; the number
    of values a component reads is its shape.
    """
    measures = _measure_counts(binding_set)
    members: dict[str, list[str]] = {}
    for decision in decisions:
        viz_type = decision.get("viz_type")
        region_id = str(decision.get("region_id") or "")
        if decision.get("decision") != "new_plugin" or not viz_type:
            continue
        if region_id in measures:
            members.setdefault(str(viz_type), []).append(region_id)

    problems: list[str] = []
    for viz_type, region_ids in sorted(members.items()):
        by_count: dict[int, list[str]] = {}
        for region_id in region_ids:
            by_count.setdefault(measures[region_id], []).append(region_id)
        if len(by_count) < 2:
            continue
        shapes = "; ".join(
            f"{count} measure(s): {', '.join(sorted(ids))}"
            for count, ids in sorted(by_count.items())
        )
        problems.append(
            f"{viz_type}: one plugin for regions whose bindings read different "
            f"numbers of measures ({shapes}). The plugin is written from one of "
            "them, so the others get metric controls that do not fit their "
            "data -- an empty one crashes the page. Give each measure count its "
            "own `custom_<name>` viz_type, and say in each rationale that the "
            "regions read different data. This applies to a `same_as` group "
            "too."
        )
    return problems


def structural_shape(
    decision: dict[str, Any], region: dict[str, Any]
) -> tuple[Any, ...]:
    """What a plugin actually has to be built to hold, for one group member.

    `_shared_plugin_shapes` catches two members of a shared `new_plugin` group
    reading a different number of measures; that is a data-shape mismatch. This
    is the structure-shape counterpart, for the axes measure counts say nothing
    about: how many children a container hosts, which controls sit on its own
    header, whether it draws its own card or sits bare, and how many axes it
    formats. A plugin generated from one member's shape is a fixed React
    component -- it cannot grow a fourth child slot, a control it was never
    given, or a card border around a sibling that should be bare -- so two
    members whose shape disagrees on any of these are not the same component,
    whatever `viz_type` stage C gave them both.

    Returned as a tuple so equal shapes compare equal and unequal ones sort
    into distinct buckets; `split_incompatible_groups` is the only caller that
    needs to know why two tuples differ, so the fields are kept in the fixed
    order documented there rather than named.
    """
    # The count, not the refs themselves: two container copies never share a
    # ref -- each hosts its own charts -- so comparing the refs directly would
    # flag every real container group as a mismatch. What decides whether one
    # plugin can host both is how many slots it needs, not which charts fill them.
    children = len(decision.get("children") or [])
    controls = tuple(
        sorted(
            str(control.get("kind"))
            for control in region.get("controls") or []
            if isinstance(control, dict) and control.get("kind")
        )
    )
    surface = str((region.get("chrome") or {}).get("surface") or "card")
    axis_shape = tuple(
        sorted(
            (str(fmt.get("axis")), str(fmt.get("kind")))
            for fmt in region.get("axis_formats") or []
            if isinstance(fmt, dict)
        )
    )
    return (children, controls, surface, axis_shape)


# One label per position in `structural_shape`'s tuple, in the same order, so
# a mismatch can be explained in words instead of as two opaque tuples.
_SHAPE_AXES = ("children", "controls", "chrome.surface", "axis_formats")


def _shape_diff_reason(primary: tuple[Any, ...], other: tuple[Any, ...]) -> str:
    """Which of `structural_shape`'s axes actually differ, in one sentence."""
    diffs = [
        f"{name} {primary[i]!r} vs {other[i]!r}"
        for i, name in enumerate(_SHAPE_AXES)
        if primary[i] != other[i]
    ]
    return "; ".join(diffs) or "shape differs"


def split_incompatible_groups(
    by_type: dict[str, list[dict[str, Any]]],
    regions: dict[str, dict[str, Any]],
) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
    """Pull the members of a shared-`viz_type` group that do not actually match.

    The orchestrator groups `new_plugin` decisions by `viz_type` alone and
    sends only the group's first member to stage F; every other member is
    trusted to be renderable by the plugin built for that one. Nothing checked
    that trust before this -- a container built to host three named children
    was reused across regions needing four, a table's columns, and a bare
    sibling with no card at all, and when the plugin could not actually be all
    of those things at once, the whole group -- eleven sections in one real
    run -- was dropped together rather than the one member that did not fit.

    The fix is cheaper before generation than after: a member whose shape
    disagrees with the group's first (the one a plugin is actually built from)
    is renamed onto its own `viz_type` here, before stage F ever runs, so it
    gets a plugin built for its own shape instead of quietly gambling on one
    built for someone else's. Members that share a shape, including a shape
    that disagrees with the first member's, are kept together -- a group of
    six where three need a bare sibling costs one extra plugin, not three.

    This is a hard split, not a warning the model can talk its way out of with
    a rationale: `_shared_plugin_shapes` treats a differing measure count the
    same way, unconditionally, because whether two components have the same
    shape is a fact about what a plugin can render, not a judgement call.
    """

    def region_for(region_id: str) -> dict[str, Any]:
        return regions.get(region_id) or regions.get(region_id.split(":")[0], {})

    split: dict[str, list[dict[str, Any]]] = {}
    warnings: list[dict[str, Any]] = []
    for viz_type, group in by_type.items():
        if len(group) < 2:
            split[viz_type] = group
            continue

        buckets: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
        order: list[tuple[Any, ...]] = []
        for decision in group:
            shape = structural_shape(
                decision, region_for(str(decision.get("region_id") or ""))
            )
            if shape not in buckets:
                buckets[shape] = []
                order.append(shape)
            buckets[shape].append(decision)

        if len(buckets) == 1:
            split[viz_type] = group
            continue

        # The plugin stage F is actually about to build comes from `group[0]`,
        # so its shape is the one `viz_type` keeps meaning; every other bucket
        # is a shape that plugin was never built for.
        primary_shape = structural_shape(
            group[0], region_for(str(group[0].get("region_id") or ""))
        )
        for index, shape in enumerate(order):
            bucket = buckets[shape]
            if shape == primary_shape:
                split[viz_type] = bucket
                continue
            new_viz_type = f"{viz_type}_shape{index}"
            for decision in bucket:
                decision["viz_type"] = new_viz_type
            split[new_viz_type] = bucket
            warnings.append(
                {
                    "viz_type": viz_type,
                    "new_viz_type": new_viz_type,
                    "region_ids": [str(d.get("region_id")) for d in bucket],
                    "reason": _shape_diff_reason(primary_shape, shape),
                }
            )
    return split, warnings


def _plugin_choice_answers(binding_set: dict[str, Any]) -> dict[str, str]:
    """`region_id -> plugin_choice`, for the regions the gate actually asked.

    The gate's stock-vs-custom question is answered per region, not for the
    whole design, and only reaches stage C by way of stage B's bindings
    (`GATE_PASSTHROUGH_FIELDS` in `b_bind.py`). Most regions carry no answer
    here -- either the user never reached that question, or `stock_candidate`
    was null and the gate never raised it -- so this is deliberately a lookup
    of the regions where re-deriving stock-versus-custom would be relitigating
    a decision the user already made, not the default case.
    """
    return {
        str(b.get("region_id")): b["plugin_choice"]
        for b in binding_set.get("bindings") or []
        if isinstance(b, dict) and b.get("region_id") and b.get("plugin_choice")
    }


def _candidate_overturned_without_naming_it(
    decisions: list[dict[str, Any]],
    design_analysis: dict[str, Any],
    plugin_choices: dict[str, str] | None = None,
) -> list[str]:
    """Rejecting A's registry candidate without saying what was wrong with it.

    `thumbnail_evidence` is otherwise only checked for being non-empty, so
    "looks fine" passes and a table whose cells draw coloured bars ships as
    plain text. Naming the candidate does not prove the thumbnail was opened,
    but it makes the claim falsifiable and forces the one comparison that
    matters -- against the plugin stage A actually found.

    A region with a `plugin_choice` answer is exempt: there is no candidate
    being "overturned" there, because the user's own answer to exactly this
    question *is* the decision, not a verdict stage C reached and has to
    justify against A's guess.
    """
    plugin_choices = plugin_choices or {}
    candidates = {
        str(r.get("region_id")): r.get("stock_candidate")
        for r in design_analysis.get("regions", [])
        if isinstance(r, dict) and r.get("stock_candidate")
    }
    return [
        f"{d.get('region_id')}: stage A found "
        f"{candidates[str(d.get('region_id'))]!r} in the registry and this "
        "decision does not use it, but `thumbnail_evidence` never mentions it. "
        "Say what its thumbnail does that the design does not."
        for d in decisions
        if str(d.get("region_id")) in candidates
        and str(d.get("region_id")) not in plugin_choices
        and d.get("decision") in DRAWS_DATA
        and d.get("viz_type") != candidates[str(d.get("region_id"))]
        and str(candidates[str(d.get("region_id"))])
        not in str(d.get("thumbnail_evidence") or "")
    ]


# Nouns that name a visual feature specific enough that a plugin either has
# it or does not -- unlike "number" or "text", which every chart has some
# form of. Drawn from `unusual_treatment`, stage A's own list of what a
# region does that a charting library does not normally do, and checked
# against the reused plugin's own capability card rather than trusted from
# the reusing decision's prose, which is free to claim anything.
_CAPABILITY_WORDS = (
    "sparkline",
    "icon",
    "badge",
    "gradient",
    "gauge",
    "donut",
    "chip",
    "avatar",
    "logo",
    "trendline",
    "trend line",
    "glyph",
    "progress bar",
    "heatmap",
)


def _reused_capability_mismatch(
    decisions: list[dict[str, Any]],
    design_analysis: dict[str, Any],
    registry: Registry,
) -> list[str]:
    """A custom plugin reused for a feature its own card never mentions.

    `configure` on a `custom_` viz type reuses a plugin some earlier run
    built for a different region; nothing about this run's decision changed
    what that plugin's component can actually draw. Stage C's own rationale
    was found, once, to claim an icon badge and a sparkline for a plugin
    whose real controls are a coverage percentage and an on-demand dollar
    figure -- capabilities neither its control panel nor its component ever
    had, invented because nothing checked the claim against the plugin
    itself. This does.
    """
    treatments = {
        str(r.get("region_id")): [str(t) for t in r.get("unusual_treatment") or []]
        for r in design_analysis.get("regions") or []
        if isinstance(r, dict)
    }
    problems: list[str] = []
    for decision in decisions:
        if decision.get("decision") != "configure":
            continue
        viz_type = str(decision.get("viz_type") or "")
        if not viz_type.startswith("custom_"):
            continue
        region_id = str(decision.get("region_id") or "")
        needed = [
            (treatment, word)
            for treatment in treatments.get(region_id, [])
            for word in _CAPABILITY_WORDS
            if word in treatment.lower()
        ]
        if not needed:
            continue
        try:
            card = registry.capability_card(viz_type).lower()
        except RegistryError:
            continue
        for treatment, word in needed:
            if word not in card:
                problems.append(
                    f"{region_id}: unusual_treatment says {treatment!r}, but "
                    f"{viz_type}'s own capability card never mentions "
                    f"{word!r} -- reusing it will not draw this. Check what "
                    "get_chart_capabilities actually says this plugin's "
                    "controls do, or build a new plugin for this region."
                )
    return problems


def _chart_info_by_id(
    chart_searches: list[dict[str, Any]] | None,
) -> dict[str, dict[str, Any]]:
    """Every `get_chart_info` result in this run's transcript, by chart id.

    Keyed on both the identifier the model asked for and the id the response
    actually carried -- a chart can be looked up by UUID and confirmed by
    integer id, and `existing_chart_id` on a `reuse` decision is free to be
    either. An errored call confirms nothing: it is a lookup that failed, not
    evidence a chart exists, so it contributes no key.
    """
    by_id: dict[str, dict[str, Any]] = {}
    for entry in chart_searches or []:
        if entry.get("tool") != "get_chart_info" or entry.get("error"):
            continue
        result = entry.get("result")
        if not isinstance(result, dict) or result.get("error"):
            continue
        arguments = entry.get("arguments") or {}
        for value in (
            arguments.get("identifier"),
            result.get("id"),
            result.get("uuid"),
        ):
            if value is not None:
                by_id[str(value)] = result
    return by_id


def _confirmed_chart_ids(chart_searches: list[dict[str, Any]] | None) -> set[str]:
    """Chart ids a real `get_chart_info` call in this run actually confirmed."""
    return set(_chart_info_by_id(chart_searches))


# The `get_chart_info` fields that let a human independently judge a `reuse`
# match without re-running the lookup themselves: the chart's identity and
# name, and what it actually reads. `form_data` names its measures and
# dimensions differently by viz type (`metrics`/`metric`,
# `groupby`/`columns`/`all_columns`), so every plausible key is tried and the
# first non-empty one kept.
_REUSE_METRIC_KEYS = ("metrics", "metric")
_REUSE_COLUMN_KEYS = ("groupby", "columns", "all_columns")


def _reuse_evidence_summary(result: dict[str, Any]) -> dict[str, Any]:
    """The compact, structured slice of a `get_chart_info` result worth
    showing a human deciding whether a `reuse` is really a match."""
    form_data = result.get("form_data")
    form_data = form_data if isinstance(form_data, dict) else {}

    def first(keys: tuple[str, ...]) -> Any:
        for key in keys:
            if value := form_data.get(key):
                return value
        return None

    summary = {
        "name": result.get("slice_name"),
        "viz_type": result.get("viz_type"),
        "dataset": result.get("datasource_name"),
        "metrics": first(_REUSE_METRIC_KEYS),
        "columns": first(_REUSE_COLUMN_KEYS),
    }
    return {k: v for k, v in summary.items() if v not in (None, "", [])}


def annotate_reuse_evidence(
    decisions: list[dict[str, Any]], chart_searches: list[dict[str, Any]] | None
) -> None:
    """Attach, in place, the real `get_chart_info` result behind a `reuse`.

    `reuse_evidence` is C's own sentence about why a candidate matches; the
    plan a user approves otherwise shows them only that paraphrase, never the
    lookup it paraphrases. Where the confirmed transcript (`chart_searches`,
    the same one `_reuse_unconfirmed_by_search` checks against) holds the
    actual result for this decision's `existing_chart_id`, a compact
    structured summary of it -- name, viz_type, dataset, the metrics and
    columns it reads -- is attached alongside, so the evidence a human would
    need to independently judge the match is there to read, not just C's
    account of it. Purely additive: a decision with no matching search keeps
    only its own `reuse_evidence`, exactly as before.
    """
    by_id = _chart_info_by_id(chart_searches)
    if not by_id:
        return
    for decision in decisions:
        if decision.get("decision") != "reuse":
            continue
        chart_id = decision.get("existing_chart_id")
        if chart_id is None:
            continue
        if result := by_id.get(str(chart_id)):
            decision["reuse_confirmed_evidence"] = _reuse_evidence_summary(result)


def _reuse_unconfirmed_by_search(
    decisions: list[dict[str, Any]],
    chart_searches: list[dict[str, Any]] | None,
) -> list[str]:
    """A `reuse` decision whose chart id no real tool call ever confirmed.

    `existing_chart_id` and `reuse_evidence` were previously only checked for
    being non-empty strings -- a model can write either one for a chart it
    never actually looked up. This cross-checks the id against the run's own
    `get_chart_info` transcript (`chart_searches`, threaded in from
    `runner.py`), the same "mechanical fact, not a guess" posture
    `_reused_capability_mismatch` already takes for a reused custom plugin's
    claimed capabilities.

    `chart_searches` is optional and, when absent, this check is skipped
    entirely rather than failing every caller that predates it -- most
    existing tests build a plan and a `reuse` decision with no transcript at
    all, and there is nothing to check a claim against without one.
    """
    if not chart_searches:
        return []
    confirmed = _confirmed_chart_ids(chart_searches)
    return [
        f"{d.get('region_id')}: reuse names chart {d['existing_chart_id']!r}, but "
        "no get_chart_info call in this run's search transcript ever confirmed "
        "that id -- look it up before reusing it, or reuse a chart you already "
        "confirmed"
        for d in decisions
        if d.get("decision") == "reuse"
        and d.get("existing_chart_id") is not None
        and str(d["existing_chart_id"]) not in confirmed
    ]


def _evidence_missing(
    decisions: list[dict[str, Any]], plugin_choices: dict[str, str] | None = None
) -> list[str]:
    """Verdicts recorded without the comparison that produced them.

    The prompt asks for `thumbnail_evidence` on every section and nothing read
    it, so "I compared the thumbnails" was an assertion the plan never had to
    support. It is the one field that distinguishes a considered stock-versus-
    custom verdict from a guess, and a guess here costs a ten-minute plugin
    build or a chart that does not look like the design.

    A region carrying a `plugin_choice` answer is exempt: there is nothing to
    prove was looked at, because stock-versus-custom was not stage C's call to
    make there in the first place -- the user already decided, and this field
    exists to show the model's own comparison work, not the user's.
    """
    plugin_choices = plugin_choices or {}
    return [
        f"{d.get('region_id')}: {d.get('decision')} without thumbnail_evidence -- "
        "say which plugin thumbnails you compared and what you saw"
        for d in decisions
        if d.get("decision") in {"reuse", "configure", "new_plugin"}
        and str(d.get("region_id")) not in plugin_choices
        and not str(d.get("thumbnail_evidence") or "").strip()
    ]


def stock_fidelity_unasked(
    decisions: list[dict[str, Any]], needs: list[dict[str, Any]]
) -> list[str]:
    """A `configure` decision that names its own fidelity gap and never asks
    about it.

    `fidelity_loss` is free text a plan can write and never act on -- the
    stock-versus-custom trade-off it describes is exactly the choice `needs`
    exists to put in front of the user, so a region with a known gap and no
    matching question is a decision made silently on the user's behalf.
    Asking is mechanical here, the same way `_evidence_missing` checks that a
    verdict was compared rather than trusting that it was: every `configure`
    decision that names a gap gets a `needs` entry for that `region_id`, no
    exceptions left to judgement about which gaps are "worth" asking about.
    """
    asked = {
        str(n.get("region_id"))
        for n in needs
        if isinstance(n, dict) and n.get("region_id")
    }
    return [
        f"{d.get('region_id')}: configure with a fidelity_loss "
        f"({d['fidelity_loss']!r}) but no matching needs question -- ask "
        "whether the user accepts this gap or wants a custom plugin built to "
        "close it, the same way any other stock-versus-custom trade-off is asked"
        for d in decisions
        if d.get("decision") == "configure"
        and str(d.get("fidelity_loss") or "").strip()
        and str(d.get("region_id")) not in asked
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


# What stage A observed that the contract needs but cannot improve on. C is
# asked for these so every parallel worker obeys one value; when it omits
# them, A's observation is better than nothing at all.
OBSERVED_CONTRACT_KEYS = ("card_chrome", "typography", "palette", "theme")
# The contract keys held to concrete values, with the shape stage C is shown
# when it leaves one out that stage A saw.
CONCRETE_CONTRACT_EXAMPLES = {
    "card_chrome": (
        '{"border": "<n>px solid #RRGGBB", "radius": "<n>px", '
        '"shadow": "none", "padding": "<n>px"}'
    ),
    "typography": '{"value": "<size>px/<weight>", "label": "<size>px/<weight>"}',
}


def _absent_value(value: Any) -> bool:
    return value is None or value in ("", {}, [])


def design_system(
    plan: dict[str, Any], design_analysis: dict[str, Any]
) -> dict[str, Any]:
    """Stage C's contract, backfilled from what stage A saw.

    The contract exists so that workers running in parallel agree: six plugin
    authors each see one card and nothing makes them pick the same corner
    radius unless a shared value tells them to. The card treatment is the most
    repeated thing on a page, so a contract missing it is a dashboard that is
    subtly inconsistent in the way most visible to a reader.

    Stage F's prompt has always told it to take chrome and typography from the
    contract; stage C was never asked to put them there. Asking is the fix --
    this is the guard that keeps a silent omission from costing the run, since
    nothing downstream can tell an absent radius from a deliberate one.

    The card and the type scale handed on are the concrete ones only: a
    range or a description reaches workers whenever C runs out of re-plans
    with one still in place, or leaves a key out and stage A's prose is
    backfilled, and each worker then picks its own reading of it.
    """
    contract = dict(plan.get("design_system") or {})
    observed = design_analysis.get("global") or {}
    for key in OBSERVED_CONTRACT_KEYS:
        if not contract.get(key) and observed.get(key):
            contract[key] = observed[key]
    return chrome.concrete_contract(contract)


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
    registry: Registry,
    chart_searches: list[dict[str, Any]] | None = None,
) -> list[str]:
    """Structural checks before the plan is shown to a user or fanned out.

    `chart_searches` is optional: it is `chart_searches()`'s merged transcript
    of every `get_chart_info` call this run has made, and its only use here is
    `_reuse_unconfirmed_by_search`. A caller that has no transcript to hand --
    every existing unit test, and any future one that only cares about the
    other checks -- gets the same result as before.
    """
    problems: list[str] = []
    entries = registry.entries
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

    plugin_choices = _plugin_choice_answers(binding_set)
    problems.extend(_answer_conflicts(decisions, design_analysis, binding_set))
    problems.extend(_text_as_plugin(decisions, design_analysis))
    problems.extend(_wrappers_without_children(decisions, design_analysis))
    problems.extend(_binding_coverage(decisions, design_analysis, binding_set))
    problems.extend(_evidence_missing(decisions, plugin_choices))
    problems.extend(_component_groups_split(decisions, design_analysis, binding_set))
    problems.extend(_shared_plugin_shapes(decisions, binding_set))
    problems.extend(
        _candidate_overturned_without_naming_it(
            decisions, design_analysis, plugin_choices
        )
    )
    problems.extend(_switcher_lost(decisions, design_analysis))
    problems.extend(_reused_capability_mismatch(decisions, design_analysis, registry))
    problems.extend(_reuse_unconfirmed_by_search(decisions, chart_searches))

    refs = {d.get("ref") for d in decisions if d.get("ref")}
    seen_refs: set[str] = set()
    seen_region_ids: set[str] = set()
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
        if region_id:
            # A region is one decision. Two decisions naming the same
            # region_id merge by that key wherever a patch is applied
            # (`merge_patch` keys on it precisely so a correction to one
            # region does not require resending the rest) -- so the second
            # one silently replaces the first there, one region at a time,
            # a decision lost on every single merge without ever failing
            # loudly. A control band the design draws as one region stays
            # one region here too: list each control inside that one
            # decision, never split it into several sharing its region_id.
            if region_id in seen_region_ids:
                problems.append(f"{region_id}: two decisions for the same region")
            seen_region_ids.add(region_id)

        if kind == "grid_text" and not decision.get("text"):
            problems.append(f"{region_id}: grid_text without the text to render")
        if kind == "grid_text" and "\n" in str(decision.get("text") or "").strip():
            # A grid_text decision becomes a single-line HEADER node.
            # Superset's own MARKDOWN node holds more, but always inside a
            # scrolling container no design draws -- so a heading with a
            # subtitle, or any text needing more than one line, is
            # configure: custom_text instead, never grid_text.
            problems.append(
                f"{region_id}: grid_text carries more than one line -- use "
                "configure: custom_text for a heading with a subtitle or any "
                "text needing more than one line, not grid_text"
            )
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

    contract = plan.get("design_system")
    if not contract:
        problems.append("no design_system contract emitted")
    else:
        # The contract reaches the dashboard stylesheet and every plugin
        # author; a range or a description there is a value each reads
        # differently and a browser drops. The raw contract, not the
        # `design_system` backfill: stage A describes the card in prose, and C
        # is not asked to fix A's reading.
        problems.extend(chrome.contract_css_problems(contract))
        # Leaving a key out would dodge that check and hand every worker A's
        # unvalidated reading instead, which is where the ranges came from.
        observed = design_analysis.get("global") or {}
        for key, example in CONCRETE_CONTRACT_EXAMPLES.items():
            if _absent_value(contract.get(key)) and not _absent_value(
                observed.get(key)
            ):
                problems.append(
                    f"design_system.{key} is missing, but stage A observed one "
                    f"({str(observed[key])[:80]!r}). Plugin authors run in "
                    "parallel and take it from the contract alone: give the "
                    f"concrete values the design draws, e.g. {example}."
                )

    return problems
