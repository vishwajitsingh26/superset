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
"""Structural checks on stage C's plan.

The fixture is a wrapper holding a chart and a table, with a second wrapper
drawn the same way -- the shape stage A now produces, and the one the checks
here exist for.
"""

from __future__ import annotations

import copy
import pathlib
from typing import Any

import pytest

from superset.design_to_dashboard.registry import load, Registry
from superset.design_to_dashboard.stages import c_resolve
from superset.design_to_dashboard.stages.c_resolve import (
    _component_groups_split,
    _reused_capability_mismatch,
    annotate_comparisons,
    chart_kind,
    CHART_KIND_CUSTOM_NEW,
    CHART_KIND_CUSTOM_REUSE,
    CHART_KIND_EXISTING_CHART,
    CHART_KIND_STOCK,
    merge_patch,
    split_incompatible_groups,
    stock_fidelity_unasked,
    structural_shape,
    validate,
)
from superset.design_to_dashboard.stages.f_scaffold import (
    build_user_prompt,
    resolve_children,
)

# The committed manifest keeps these tests independent of which plugins happen
# to be on disk; runs build theirs from source.
_ROOT = pathlib.Path(__file__).resolve().parents[3]
REGISTRY = Registry.from_snapshot(
    {"entries": load(_ROOT / "design-to-dashboard" / "fixtures" / "viz_registry.json")},
    _ROOT,
)
SHARED = 23


@pytest.fixture
def design() -> dict[str, Any]:
    return {
        "global": {"title": "Database Spend"},
        "regions": [
            {
                "region_id": "r01_coverage",
                "n": 1,
                "role": "wrapper",
                "frame": "none",
                "children": [2, 3],
                "same_as": None,
            },
            {
                "region_id": "r02_aws_coverage",
                "n": 2,
                "role": "kpi",
                "frame": None,
                "children": [],
                "same_as": None,
            },
            {
                "region_id": "r03_uncovered",
                "n": 3,
                "role": "table",
                "frame": None,
                "children": [],
                "same_as": None,
            },
            {
                "region_id": "r04_heading",
                "n": 4,
                "role": "header",
                "frame": None,
                "children": [],
                "same_as": None,
            },
        ],
    }


@pytest.fixture
def binding_set() -> dict[str, Any]:
    return {
        "status": "ok",
        "shared_dataset_id": SHARED,
        "fact_tables": [{"name": "coverage", "dataset_id": 24}],
        "views": [{"name": "coverage_by_cloud", "dataset_id": 31}],
        "bindings": [
            {"region_id": "r01_coverage", "dataset_id": SHARED},
            {"region_id": "r02_aws_coverage", "dataset_id": 31},
            {"region_id": "r03_uncovered", "dataset_id": 31},
            {"region_id": "r04_heading", "dataset_id": SHARED},
        ],
    }


@pytest.fixture
def plan() -> dict[str, Any]:
    return {
        "status": "needs_approval",
        "design_system": {"palette": ["#0af"]},
        "decisions": [
            {
                "region_id": "r02_aws_coverage",
                "ref": "c1",
                "decision": "new_plugin",
                "viz_type": "custom_metric_card",
                "plugin_archetype": "viz",
                "children": [],
                "thumbnail_evidence": "no stock card draws a red sub-line",
            },
            {
                "region_id": "r03_uncovered",
                "ref": "c2",
                "decision": "new_plugin",
                "viz_type": "custom_ratio_table",
                "plugin_archetype": "table",
                "children": [],
                "thumbnail_evidence": "stock tables render text, not bars",
            },
            {
                "region_id": "r01_coverage",
                "ref": "c3",
                "decision": "new_plugin",
                "viz_type": "custom_panel",
                "plugin_archetype": "container",
                "children": ["c1", "c2"],
                "thumbnail_evidence": "nothing in the registry composes a frame",
            },
            {
                "region_id": "r04_heading",
                "ref": "c4",
                "decision": "grid_text",
                "text": "## Coverage",
            },
        ],
    }


def test_a_well_formed_plan_is_valid(
    plan: dict[str, Any], design: dict[str, Any], binding_set: dict[str, Any]
) -> None:
    assert validate(plan, design, binding_set, REGISTRY) == []


# --- wrappers ---------------------------------------------------------------


def test_a_wrapper_resolved_without_children_is_reported(
    plan: dict[str, Any], design: dict[str, Any], binding_set: dict[str, Any]
) -> None:
    plan["decisions"][2]["children"] = []
    assert any(
        "holding 2 other section" in p
        for p in validate(plan, design, binding_set, REGISTRY)
    )


def test_children_on_a_leaf_are_reported(
    plan: dict[str, Any], design: dict[str, Any], binding_set: dict[str, Any]
) -> None:
    plan["decisions"][0]["children"] = ["c2"]
    assert any(
        "stage A read no sections inside it" in p
        for p in validate(plan, design, binding_set, REGISTRY)
    )


def test_a_child_ref_must_exist(
    plan: dict[str, Any], design: dict[str, Any], binding_set: dict[str, Any]
) -> None:
    plan["decisions"][2]["children"] = ["c1", "c9"]
    assert any(
        "child ref 'c9' not defined" in p
        for p in validate(plan, design, binding_set, REGISTRY)
    )


def test_a_switcher_over_sections_must_be_kept(
    plan: dict[str, Any], design: dict[str, Any], binding_set: dict[str, Any]
) -> None:
    """A tabbed card built as its visible tab alone looks correct -- nobody
    notices the tabs that are not there."""
    design["regions"][0]["frame"] = "tabs"
    plan["decisions"][2]["children"] = []
    plan["decisions"][2]["plugin_archetype"] = "viz"
    assert any(
        "saw a switcher over several sections" in p
        for p in validate(plan, design, binding_set, REGISTRY)
    )


def test_a_switcher_over_one_chart_is_not_a_container(
    plan: dict[str, Any], design: dict[str, Any], binding_set: dict[str, Any]
) -> None:
    """`frame: tabs` with no children refilters one chart; the control belongs
    to that chart, and forcing a container on it is the old trap."""
    design["regions"][1]["frame"] = "tabs"
    assert validate(plan, design, binding_set, REGISTRY) == []


# --- decisions --------------------------------------------------------------


def test_wrap_is_no_longer_a_decision(
    plan: dict[str, Any], design: dict[str, Any], binding_set: dict[str, Any]
) -> None:
    plan["decisions"][2]["decision"] = "wrap"
    assert any(
        "unknown decision 'wrap'" in p
        for p in validate(plan, design, binding_set, REGISTRY)
    )


def test_native_filter_is_no_longer_a_decision(
    plan: dict[str, Any], design: dict[str, Any], binding_set: dict[str, Any]
) -> None:
    """Filters are grid elements; Superset's own are configured by hand."""
    plan["decisions"][0]["decision"] = "native_filter"
    assert any(
        "unknown decision 'native_filter'" in p
        for p in validate(plan, design, binding_set, REGISTRY)
    )


def test_every_region_needs_a_decision(
    plan: dict[str, Any], design: dict[str, Any], binding_set: dict[str, Any]
) -> None:
    plan["decisions"] = plan["decisions"][:3]
    assert any(
        "region has no decision: r04_heading" in p
        for p in validate(plan, design, binding_set, REGISTRY)
    )


def test_a_new_plugin_needs_a_custom_viz_type(
    plan: dict[str, Any], design: dict[str, Any], binding_set: dict[str, Any]
) -> None:
    plan["decisions"][0]["viz_type"] = "metric_card"
    assert any(
        "must start with 'custom_'" in p
        for p in validate(plan, design, binding_set, REGISTRY)
    )


def test_missing_thumbnail_evidence_is_reported(
    plan: dict[str, Any], design: dict[str, Any], binding_set: dict[str, Any]
) -> None:
    plan["decisions"][0]["thumbnail_evidence"] = ""
    assert any(
        "without thumbnail_evidence" in p
        for p in validate(plan, design, binding_set, REGISTRY)
    )


def test_a_grid_text_decision_needs_its_text(
    plan: dict[str, Any], design: dict[str, Any], binding_set: dict[str, Any]
) -> None:
    plan["decisions"][3]["text"] = ""
    assert any(
        "grid_text without the text" in p
        for p in validate(plan, design, binding_set, REGISTRY)
    )


def test_a_grid_text_decision_with_a_subtitle_is_reported(
    plan: dict[str, Any], design: dict[str, Any], binding_set: dict[str, Any]
) -> None:
    """A HEADER node holds one line; MARKDOWN holds more but always inside a
    scrolling container no design draws -- so more than one line means
    configure: custom_text, not grid_text."""
    plan["decisions"][3]["text"] = "**Title**\n\nSubtitle."
    assert any(
        "more than one line" in p for p in validate(plan, design, binding_set, REGISTRY)
    )


def test_a_single_line_grid_text_decision_is_fine(
    plan: dict[str, Any], design: dict[str, Any], binding_set: dict[str, Any]
) -> None:
    plan["decisions"][3]["text"] = "Title"
    assert not any(
        "more than one line" in p for p in validate(plan, design, binding_set, REGISTRY)
    )


def test_two_decisions_for_the_same_region_is_reported(
    plan: dict[str, Any], design: dict[str, Any], binding_set: dict[str, Any]
) -> None:
    """A patch keys its merge on region_id, so two decisions sharing one
    silently collapse to whichever comes last -- every single merge, from
    the very first patch, with nothing else ever failing loudly about it."""
    duplicate = {**plan["decisions"][1], "ref": "c9"}
    duplicate["region_id"] = plan["decisions"][0]["region_id"]
    plan["decisions"].append(duplicate)
    assert any(
        "two decisions for the same region" in p
        for p in validate(plan, design, binding_set, REGISTRY)
    )


def test_one_decision_per_region_is_fine(
    plan: dict[str, Any], design: dict[str, Any], binding_set: dict[str, Any]
) -> None:
    assert not any(
        "two decisions for the same region" in p
        for p in validate(plan, design, binding_set, REGISTRY)
    )


def test_a_header_resolved_to_a_plugin_is_reported(
    plan: dict[str, Any], design: dict[str, Any], binding_set: dict[str, Any]
) -> None:
    """Text costs no generation; `custom_text` already exists."""
    plan["decisions"][3] = {
        "region_id": "r04_heading",
        "ref": "c4",
        "decision": "new_plugin",
        "viz_type": "custom_heading",
        "plugin_archetype": "viz",
        "thumbnail_evidence": "none fit",
    }
    assert any(
        "draws no data" in p for p in validate(plan, design, binding_set, REGISTRY)
    )


# --- a patch that omits a field vs. one that nulls it -----------------------


def test_an_omitted_field_carries_the_previous_value_forward() -> None:
    previous = {"design_system": {"palette": ["#000"]}, "decisions": []}
    reply = {"revision": "patch", "decisions": []}
    merged = merge_patch(previous, reply)
    assert merged["design_system"] == {"palette": ["#000"]}


def test_an_explicit_null_also_carries_the_previous_value_forward() -> None:
    """A model told a field 'may be omitted' sent it back `null` instead --
    for `design_system`, for `plan_for_review` -- and both must read as
    unchanged, the same as leaving the key out. The alternative wiped a good
    design_system, then a good plan_for_review, on two separate real runs."""
    previous = {
        "design_system": {"palette": ["#000"]},
        "plan_for_review": [{"step": 1}],
        "decisions": [],
    }
    reply: dict[str, Any] = {
        "revision": "patch",
        "design_system": None,
        "plan_for_review": None,
        "decisions": [],
    }
    merged = merge_patch(previous, reply)
    assert merged["design_system"] == {"palette": ["#000"]}
    assert merged["plan_for_review"] == [{"step": 1}]


def test_a_real_value_still_replaces_the_previous_one() -> None:
    previous = {"design_system": {"palette": ["#000"]}, "decisions": []}
    reply = {
        "revision": "patch",
        "design_system": {"palette": ["#fff"]},
        "decisions": [],
    }
    merged = merge_patch(previous, reply)
    assert merged["design_system"] == {"palette": ["#fff"]}


def test_a_full_revision_is_returned_exactly_as_sent() -> None:
    """The null-carries-forward rule is a patch-only safety net -- a full
    plan sending `design_system: null` is a real absence, for validate() to
    catch, not something to paper over here."""
    previous = {"design_system": {"palette": ["#000"]}, "decisions": []}
    reply: dict[str, Any] = {
        "revision": "full",
        "design_system": None,
        "decisions": [],
    }
    assert merge_patch(previous, reply) is reply


def test_decisions_still_merge_by_region_id() -> None:
    previous = {
        "decisions": [
            {"region_id": "r1", "decision": "configure", "viz_type": "pie"},
            {"region_id": "r2", "decision": "grid_text", "text": "Title"},
        ]
    }
    reply = {
        "revision": "patch",
        "decisions": [
            {"region_id": "r1", "decision": "configure", "viz_type": "table"}
        ],
    }
    merged = merge_patch(previous, reply)
    by_region = {d["region_id"]: d for d in merged["decisions"]}
    assert by_region["r1"]["viz_type"] == "table"
    assert by_region["r2"]["text"] == "Title"


def test_plan_for_review_merges_by_step_not_replaced_whole() -> None:
    """A patch explaining one step is not the whole plan re-approved -- the
    other steps are still true and the user already saw them. Replacing the
    list wholesale, as design_system correctly is, silently dropped them on
    a real run: four steps became one, and 'nothing to review' but the one
    thing that had not even changed."""
    previous = {
        "decisions": [],
        "plan_for_review": [
            {"step": 1, "what": "KPI cards"},
            {"step": 2, "what": "Spend trend"},
            {"step": 15, "what": "Filters band, four selects"},
        ],
    }
    reply = {
        "revision": "patch",
        "decisions": [],
        "plan_for_review": [{"step": 15, "what": "Filters band, search box folded in"}],
    }
    merged = merge_patch(previous, reply)
    steps = {s["step"]: s["what"] for s in merged["plan_for_review"]}
    assert steps == {
        1: "KPI cards",
        2: "Spend trend",
        15: "Filters band, search box folded in",
    }


def test_plan_for_review_stays_in_step_order_after_a_patch() -> None:
    previous = {
        "decisions": [],
        "plan_for_review": [{"step": 1, "what": "a"}, {"step": 2, "what": "b"}],
    }
    reply = {
        "revision": "patch",
        "decisions": [],
        "plan_for_review": [{"step": 1, "what": "a, corrected"}],
    }
    merged = merge_patch(previous, reply)
    assert [s["step"] for s in merged["plan_for_review"]] == [1, 2]


def test_an_omitted_plan_for_review_carries_the_previous_one_forward() -> None:
    previous = {
        "decisions": [],
        "plan_for_review": [{"step": 1, "what": "a"}],
    }
    reply = {"revision": "patch", "decisions": []}
    merged = merge_patch(previous, reply)
    assert merged["plan_for_review"] == [{"step": 1, "what": "a"}]


# --- a fidelity gap named and never asked about -----------------------------


def test_a_fidelity_loss_with_no_matching_question_is_reported() -> None:
    decisions = [
        {
            "region_id": "r08_pie",
            "decision": "configure",
            "viz_type": "pie",
            "fidelity_loss": "legend has no per-item percentage",
        }
    ]
    problems = stock_fidelity_unasked(decisions, [])
    assert any("r08_pie" in p and "no matching needs question" in p for p in problems)


def test_a_fidelity_loss_with_a_matching_question_is_not_reported() -> None:
    decisions = [
        {
            "region_id": "r08_pie",
            "decision": "configure",
            "viz_type": "pie",
            "fidelity_loss": "legend has no per-item percentage",
        }
    ]
    needs = [{"region_id": "r08_pie", "question": "Accept the stock legend?"}]
    assert stock_fidelity_unasked(decisions, needs) == []


def test_no_fidelity_loss_needs_no_question() -> None:
    decisions = [
        {"region_id": "r08_pie", "decision": "configure", "fidelity_loss": None}
    ]
    assert stock_fidelity_unasked(decisions, []) == []


def test_new_plugin_and_reuse_decisions_are_not_checked() -> None:
    """`fidelity_loss` on a `new_plugin` or `reuse` decision names something
    already the exact match, or already built to match -- there is no stock
    alternative to be asked about."""
    decisions = [
        {"region_id": "r03", "decision": "new_plugin", "fidelity_loss": "n/a"},
        {"region_id": "r09", "decision": "reuse", "fidelity_loss": "n/a"},
    ]
    assert stock_fidelity_unasked(decisions, []) == []


def test_a_question_for_a_different_region_does_not_count() -> None:
    decisions = [
        {
            "region_id": "r08_pie",
            "decision": "configure",
            "fidelity_loss": "legend has no per-item percentage",
        }
    ]
    needs = [{"region_id": "r09_bar", "question": "Something else entirely"}]
    problems = stock_fidelity_unasked(decisions, needs)
    assert any("r08_pie" in p for p in problems)


# --- data behind a chart ----------------------------------------------------


def test_a_chart_bound_to_the_shared_dataset_is_reported(
    plan: dict[str, Any], design: dict[str, Any], binding_set: dict[str, Any]
) -> None:
    """The shared dataset is one row and no data: a chart on it renders empty,
    and nothing else notices until someone opens the dashboard."""
    binding_set["bindings"][1]["dataset_id"] = SHARED
    assert any(
        "would render empty" in p for p in validate(plan, design, binding_set, REGISTRY)
    )


def test_a_wrapper_on_the_shared_dataset_is_fine(
    plan: dict[str, Any], design: dict[str, Any], binding_set: dict[str, Any]
) -> None:
    assert validate(plan, design, binding_set, REGISTRY) == []


def test_a_plan_with_new_plugins_must_ask_for_approval(
    plan: dict[str, Any], design: dict[str, Any], binding_set: dict[str, Any]
) -> None:
    plan["status"] = "ready"
    assert any(
        "expected 'needs_approval'" in p
        for p in validate(plan, design, binding_set, REGISTRY)
    )


def test_a_plan_needs_a_design_system(
    plan: dict[str, Any], design: dict[str, Any], binding_set: dict[str, Any]
) -> None:
    del plan["design_system"]
    assert "no design_system contract emitted" in validate(
        plan, design, binding_set, REGISTRY
    )


def test_a_design_system_value_that_is_not_css_is_sent_back(
    plan: dict[str, Any], design: dict[str, Any], binding_set: dict[str, Any]
) -> None:
    """A range reaches every plugin author, and each picks its own end of it."""
    plan["design_system"]["card_chrome"] = {"padding": "16-20px", "radius": "8px"}
    problems = validate(plan, design, binding_set, REGISTRY)
    assert any(p.startswith("design_system.card_chrome.padding") for p in problems)
    assert not any("card_chrome.radius" in p for p in problems)


def test_a_concrete_design_system_passes(
    plan: dict[str, Any], design: dict[str, Any], binding_set: dict[str, Any]
) -> None:
    plan["design_system"]["card_chrome"] = {"padding": "16px", "radius": "8px"}
    assert not any(
        "design_system" in p for p in validate(plan, design, binding_set, REGISTRY)
    )


# --- what stage F is told it hosts ------------------------------------------


def test_children_resolve_to_real_charts(plan: dict[str, Any]) -> None:
    hosted = resolve_children(plan["decisions"][2], plan["decisions"])
    assert [c["viz_type"] for c in hosted] == [
        "custom_metric_card",
        "custom_ratio_table",
    ]


def test_unknown_refs_are_dropped_not_guessed(plan: dict[str, Any]) -> None:
    assert resolve_children({"children": ["nope"]}, plan["decisions"]) == []


def test_a_wrapper_is_told_what_it_hosts(plan: dict[str, Any]) -> None:
    prompt = build_user_prompt(
        {"region_id": "r01_coverage"},
        {},
        plan["decisions"][2],
        {},
        children=resolve_children(plan["decisions"][2], plan["decisions"]),
    )
    assert "custom_metric_card" in prompt


def test_build_user_prompt_does_not_mutate_the_decision(
    plan: dict[str, Any],
) -> None:
    decision = plan["decisions"][2]
    before = copy.deepcopy(decision)
    build_user_prompt(
        {},
        {},
        decision,
        {},
        children=[{"ref": "c1", "region_id": "r02", "viz_type": "x"}],
    )
    assert decision == before


# --- stage A's component groups, and its registry candidate -----------------


def _repeated(design: dict[str, Any]) -> dict[str, Any]:
    """Stage A read r02 and r03 as the same component."""
    design["regions"][2]["same_as"] = 2
    design["regions"][2]["role"] = "kpi"
    return design


def test_splitting_a_component_group_without_saying_why_is_reported(
    plan: dict[str, Any], design: dict[str, Any], binding_set: dict[str, Any]
) -> None:
    """Each extra name is another plugin built ten minutes later."""
    problems = validate(plan, _repeated(design), binding_set, REGISTRY)
    assert any("resolve to 2 viz types" in p for p in problems)


def test_one_viz_type_across_the_group_is_fine(
    plan: dict[str, Any], design: dict[str, Any], binding_set: dict[str, Any]
) -> None:
    plan["decisions"][1]["viz_type"] = "custom_metric_card"
    plan["decisions"][1]["plugin_archetype"] = "viz"
    assert validate(plan, _repeated(design), binding_set, REGISTRY) == []


def test_a_split_explained_in_every_rationale_is_allowed(
    plan: dict[str, Any], design: dict[str, Any], binding_set: dict[str, Any]
) -> None:
    """A may judge by pixels; C judges by what one component can render."""
    plan["decisions"][0]["rationale"] = "this one drills and the other does not"
    plan["decisions"][1]["rationale"] = "separate behaviour, so a split"
    assert validate(plan, _repeated(design), binding_set, REGISTRY) == []


def test_overturning_a_candidate_without_naming_it_is_reported(
    plan: dict[str, Any], design: dict[str, Any], binding_set: dict[str, Any]
) -> None:
    """ "Looks fine" used to pass, and a table of coloured bars shipped as
    plain text."""
    design["regions"][2]["stock_candidate"] = "table"
    plan["decisions"][1]["thumbnail_evidence"] = "looks fine"
    assert any(
        "never mentions it" in p for p in validate(plan, design, binding_set, REGISTRY)
    )


def test_naming_the_rejected_candidate_clears_it(
    plan: dict[str, Any], design: dict[str, Any], binding_set: dict[str, Any]
) -> None:
    design["regions"][2]["stock_candidate"] = "table"
    plan["decisions"][1]["thumbnail_evidence"] = (
        "the `table` thumbnail renders every cell as text; the design draws a "
        "coloured bar sized to the percentage"
    )
    assert validate(plan, design, binding_set, REGISTRY) == []


def test_agreeing_with_the_candidate_needs_no_extra_words(
    plan: dict[str, Any], design: dict[str, Any], binding_set: dict[str, Any]
) -> None:
    design["regions"][2]["stock_candidate"] = "table"
    plan["decisions"][1]["decision"] = "configure"
    plan["decisions"][1]["viz_type"] = "table"
    plan["decisions"][1]["plugin_archetype"] = None
    assert validate(plan, design, binding_set, REGISTRY) == []


# --- the user already answered stock-versus-custom at the gate --------------


def _with_plugin_choice(
    binding_set: dict[str, Any], region_id: str, choice: str
) -> dict[str, Any]:
    for binding in binding_set["bindings"]:
        if binding["region_id"] == region_id:
            binding["plugin_choice"] = choice
    return binding_set


def test_overturning_a_candidate_is_not_flagged_once_the_user_answered(
    plan: dict[str, Any], design: dict[str, Any], binding_set: dict[str, Any]
) -> None:
    """The user's own answer to stock-versus-custom is the decision, not a
    verdict stage C reached and has to justify against stage A's guess."""
    design["regions"][2]["stock_candidate"] = "table"
    plan["decisions"][1]["thumbnail_evidence"] = "looks fine"
    _with_plugin_choice(binding_set, "r03_uncovered", "custom")
    assert not any(
        "never mentions it" in p for p in validate(plan, design, binding_set, REGISTRY)
    )


def test_overturning_a_candidate_without_an_answer_is_still_flagged(
    plan: dict[str, Any], design: dict[str, Any], binding_set: dict[str, Any]
) -> None:
    """No regression: a region the gate never asked about still has to name
    and justify overturning stage A's candidate."""
    design["regions"][2]["stock_candidate"] = "table"
    plan["decisions"][1]["thumbnail_evidence"] = "looks fine"
    assert any(
        "never mentions it" in p for p in validate(plan, design, binding_set, REGISTRY)
    )


def test_missing_thumbnail_evidence_is_not_flagged_once_the_user_answered(
    plan: dict[str, Any], design: dict[str, Any], binding_set: dict[str, Any]
) -> None:
    """Nothing was left unproven -- there was nothing for the model to prove
    it looked at, since the user decided, not stage C."""
    plan["decisions"][1]["thumbnail_evidence"] = ""
    _with_plugin_choice(binding_set, "r03_uncovered", "custom")
    assert not any(
        "without thumbnail_evidence" in p
        for p in validate(plan, design, binding_set, REGISTRY)
    )


def test_missing_thumbnail_evidence_without_an_answer_is_still_flagged(
    plan: dict[str, Any], design: dict[str, Any], binding_set: dict[str, Any]
) -> None:
    """No regression: a region with no `plugin_choice` still needs its
    comparison written down, exactly as before."""
    plan["decisions"][1]["thumbnail_evidence"] = ""
    assert any(
        "without thumbnail_evidence" in p
        for p in validate(plan, design, binding_set, REGISTRY)
    )


# --- one plugin, members reading different numbers of measures ---------------


def _share_one_plugin(plan: dict[str, Any]) -> dict[str, Any]:
    plan["decisions"][1]["viz_type"] = "custom_metric_card"
    plan["decisions"][1]["plugin_archetype"] = "viz"
    return plan


def _measures(binding_set: dict[str, Any], **by_region: list[str]) -> dict[str, Any]:
    for binding in binding_set["bindings"]:
        if binding["region_id"] in by_region:
            binding["measures"] = by_region[binding["region_id"]]
    return binding_set


def test_a_shared_plugin_over_different_measure_counts_is_reported(
    plan: dict[str, Any], design: dict[str, Any], binding_set: dict[str, Any]
) -> None:
    """The plugin is written from one member, and the member with fewer
    measures gets an empty metric control it then crashes on."""
    bound = _measures(
        binding_set,
        r02_aws_coverage=["coverage_pct", "uncovered_cost"],
        r03_uncovered=["runtime_pct"],
    )
    problems = validate(_share_one_plugin(plan), design, bound, REGISTRY)
    shape = [p for p in problems if "different numbers of measures" in p]
    assert len(shape) == 1
    assert "1 measure(s): r03_uncovered" in shape[0]
    assert "2 measure(s): r02_aws_coverage" in shape[0]


def test_a_same_as_group_is_held_to_it_too(
    plan: dict[str, Any], design: dict[str, Any], binding_set: dict[str, Any]
) -> None:
    bound = _measures(binding_set, r02_aws_coverage=["a", "b"], r03_uncovered=["a"])
    problems = validate(_share_one_plugin(plan), _repeated(design), bound, REGISTRY)
    assert any("different numbers of measures" in p for p in problems)


def test_splitting_a_same_as_group_along_measure_counts_needs_no_words(
    plan: dict[str, Any], design: dict[str, Any], binding_set: dict[str, Any]
) -> None:
    """The bindings are the reason, so the split rule must not demand one."""
    bound = _measures(binding_set, r02_aws_coverage=["a", "b"], r03_uncovered=["a"])
    assert validate(plan, _repeated(design), bound, REGISTRY) == []


def test_a_shared_plugin_over_equal_measure_counts_is_fine(
    plan: dict[str, Any], design: dict[str, Any], binding_set: dict[str, Any]
) -> None:
    bound = _measures(binding_set, r02_aws_coverage=["a"], r03_uncovered=["b"])
    assert validate(_share_one_plugin(plan), _repeated(design), bound, REGISTRY) == []


# --- the contract cannot dodge its check by leaving a key out ----------------


def test_leaving_out_typography_stage_a_observed_is_sent_back(
    plan: dict[str, Any], design: dict[str, Any], binding_set: dict[str, Any]
) -> None:
    """Omitted, it was backfilled from A's `22-24px bold` and reached every
    plugin author unchecked."""
    design["global"]["typography"] = {"big_number": "22-24px bold blue or dark"}
    problems = validate(plan, design, binding_set, REGISTRY)
    assert len([p for p in problems if "design_system.typography is missing" in p]) == 1
    assert not any("card_chrome is missing" in p for p in problems)


def test_giving_the_observed_typography_concretely_passes(
    plan: dict[str, Any], design: dict[str, Any], binding_set: dict[str, Any]
) -> None:
    design["global"]["typography"] = {"big_number": "22-24px bold blue or dark"}
    plan["design_system"]["typography"] = {"value": "24px/700"}
    assert not any(
        "design_system" in p for p in validate(plan, design, binding_set, REGISTRY)
    )


# --- a measure-count split excuses only itself -------------------------------

THREE_CARDS = {
    "regions": [
        {"region_id": "r01_a", "n": 1},
        {"region_id": "r02_b", "n": 2, "same_as": 1},
        {"region_id": "r03_c", "n": 3, "same_as": 1},
    ]
}
TWO_TWO_ONE = {
    "bindings": [
        {"region_id": "r01_a", "measures": ["spend", "change"]},
        {"region_id": "r02_b", "measures": ["spend", "change"]},
        {"region_id": "r03_c", "measures": ["spend"]},
    ]
}


def _cards(*viz_types: str) -> list[dict[str, Any]]:
    return [
        {
            "region_id": region["region_id"],
            "decision": "new_plugin",
            "viz_type": viz_type,
            "rationale": "card",
        }
        for region, viz_type in zip(THREE_CARDS["regions"], viz_types, strict=True)
    ]


def test_copies_reading_the_same_measures_are_still_held_together() -> None:
    """One copy reading fewer measures used to waive the rule for the whole
    group, so the two identical copies became two plugins unremarked."""
    problems = _component_groups_split(
        _cards("custom_x", "custom_y", "custom_z"), THREE_CARDS, TWO_TWO_ONE
    )
    assert len(problems) == 1
    assert "r01_a, r02_b, reading 2 measure(s) each" in problems[0]
    assert "resolve to 2 viz types" in problems[0]


def test_splitting_only_along_measure_counts_is_fine() -> None:
    assert (
        _component_groups_split(
            _cards("custom_x", "custom_x", "custom_z"), THREE_CARDS, TWO_TWO_ONE
        )
        == []
    )


# --- reusing a custom plugin for a feature its own card never mentions ------


def _metric_tile_registry(tmp_path: pathlib.Path) -> Registry:
    """A stand-in for `custom_provider_metric_tile`: a coverage-percentage and
    an uncovered-cost control, and nothing that draws an icon or a sparkline."""
    panel = tmp_path / "controlPanel.ts"
    panel.write_text(
        "const config = { controlPanelSections: [{ controlSetRows: ["
        "[{ name: 'metricCoverage', config: { label: t('Coverage metric') } }],"
        "[{ name: 'metricUncovered', config: { label: t('Uncovered cost metric') } }],"
        "] }] };",
        encoding="utf-8",
    )
    return Registry(
        entries=[
            {
                "viz_type": "custom_provider_metric_tile",
                "name": "Provider Metric Tile",
                "custom": True,
                "is_filter": False,
                "control_panel": "controlPanel.ts",
            }
        ],
        repo_root=tmp_path,
    )


def _sparkline_region(region_id: str = "r05_total_spend") -> dict[str, Any]:
    return {
        "region_id": region_id,
        "unusual_treatment": ["sparkline embedded within KPI card, no axis"],
    }


def test_a_capability_the_card_never_mentions_is_flagged(
    tmp_path: pathlib.Path,
) -> None:
    registry = _metric_tile_registry(tmp_path)
    decisions = [
        {
            "region_id": "r05_total_spend",
            "decision": "configure",
            "viz_type": "custom_provider_metric_tile",
        }
    ]
    design_analysis = {"regions": [_sparkline_region()]}
    problems = _reused_capability_mismatch(decisions, design_analysis, registry)
    assert len(problems) == 1
    assert "sparkline" in problems[0]
    assert "custom_provider_metric_tile" in problems[0]


def test_a_capability_the_card_does_mention_is_not_flagged(
    tmp_path: pathlib.Path,
) -> None:
    """The plugin genuinely has a sparkline control this time."""
    panel = tmp_path / "controlPanel.ts"
    panel.write_text(
        "const config = { controlPanelSections: [{ controlSetRows: ["
        "[{ name: 'sparkline', config: { label: t('Sparkline') } }],"
        "] }] };",
        encoding="utf-8",
    )
    registry = Registry(
        entries=[
            {
                "viz_type": "custom_kpi_spark",
                "custom": True,
                "is_filter": False,
                "control_panel": "controlPanel.ts",
            }
        ],
        repo_root=tmp_path,
    )
    decisions = [
        {
            "region_id": "r05_total_spend",
            "decision": "configure",
            "viz_type": "custom_kpi_spark",
        }
    ]
    design_analysis = {"regions": [_sparkline_region()]}
    assert _reused_capability_mismatch(decisions, design_analysis, registry) == []


def test_a_stock_viz_type_is_not_checked(tmp_path: pathlib.Path) -> None:
    """The check only holds a reused *custom* plugin to its own card; a stock
    type's fit is judged by its capability card in the prompt, not here."""
    registry = _metric_tile_registry(tmp_path)
    decisions = [
        {"region_id": "r05_total_spend", "decision": "configure", "viz_type": "pie"}
    ]
    design_analysis = {"regions": [_sparkline_region()]}
    assert _reused_capability_mismatch(decisions, design_analysis, registry) == []


def test_a_new_plugin_decision_is_not_checked(tmp_path: pathlib.Path) -> None:
    """Freshly built this run, so there is no existing card to hold it to."""
    registry = _metric_tile_registry(tmp_path)
    decisions = [
        {
            "region_id": "r05_total_spend",
            "decision": "new_plugin",
            "viz_type": "custom_provider_metric_tile",
        }
    ]
    design_analysis = {"regions": [_sparkline_region()]}
    assert _reused_capability_mismatch(decisions, design_analysis, registry) == []


def test_an_unregistered_viz_type_is_skipped_rather_than_raising(
    tmp_path: pathlib.Path,
) -> None:
    registry = _metric_tile_registry(tmp_path)
    decisions = [
        {
            "region_id": "r05_total_spend",
            "decision": "configure",
            "viz_type": "custom_gone",
        }
    ]
    design_analysis = {"regions": [_sparkline_region()]}
    assert _reused_capability_mismatch(decisions, design_analysis, registry) == []


# --- what kind of chart a decision actually produces ------------------------


def test_configure_of_a_stock_type_is_stock() -> None:
    assert chart_kind({"decision": "configure", "viz_type": "pie"}, REGISTRY) == (
        CHART_KIND_STOCK
    )


def test_configure_of_an_existing_custom_plugin_is_custom_reuse(
    tmp_path: pathlib.Path,
) -> None:
    registry = _metric_tile_registry(tmp_path)
    decision = {"decision": "configure", "viz_type": "custom_provider_metric_tile"}
    assert chart_kind(decision, registry) == CHART_KIND_CUSTOM_REUSE


def test_new_plugin_is_custom_new(tmp_path: pathlib.Path) -> None:
    registry = _metric_tile_registry(tmp_path)
    decision = {"decision": "new_plugin", "viz_type": "custom_kpi_card"}
    assert chart_kind(decision, registry) == CHART_KIND_CUSTOM_NEW


def test_reuse_is_an_existing_chart() -> None:
    decision = {"decision": "reuse", "existing_chart_id": 42}
    assert chart_kind(decision, REGISTRY) == CHART_KIND_EXISTING_CHART


@pytest.mark.parametrize("decision_kind", ["grid_text", "drop"])
def test_a_non_chart_decision_has_no_kind(decision_kind: str) -> None:
    assert chart_kind({"decision": decision_kind}, REGISTRY) is None


def test_an_unregistered_viz_type_has_no_kind(tmp_path: pathlib.Path) -> None:
    registry = _metric_tile_registry(tmp_path)
    decision = {"decision": "configure", "viz_type": "custom_gone"}
    assert chart_kind(decision, registry) is None


def test_annotate_comparisons_attaches_the_real_card(tmp_path: pathlib.Path) -> None:
    """The point: the card attached is the registry's own, not the model's
    `thumbnail_evidence` -- a reader can check one against the other."""
    registry = _metric_tile_registry(tmp_path)
    decisions = [
        {
            "region_id": "r05_total_spend",
            "decision": "configure",
            "viz_type": "custom_provider_metric_tile",
            "thumbnail_evidence": "matches an icon badge and sparkline",
        }
    ]
    annotate_comparisons(decisions, registry)
    assert decisions[0]["chart_kind"] == CHART_KIND_CUSTOM_REUSE
    assert "Coverage metric" in decisions[0]["capability_card_compared"]


def test_annotate_comparisons_gives_a_new_plugin_no_card(
    tmp_path: pathlib.Path,
) -> None:
    """Nothing exists to compare against yet -- stage F has not built it."""
    registry = _metric_tile_registry(tmp_path)
    decisions = [
        {
            "region_id": "r05_total_spend",
            "decision": "new_plugin",
            "viz_type": "custom_kpi_card",
        }
    ]
    annotate_comparisons(decisions, registry)
    assert decisions[0]["chart_kind"] == CHART_KIND_CUSTOM_NEW
    assert "capability_card_compared" not in decisions[0]


def test_annotate_comparisons_skips_decisions_with_no_kind(
    tmp_path: pathlib.Path,
) -> None:
    registry = _metric_tile_registry(tmp_path)
    decisions = [{"region_id": "r01_heading", "decision": "grid_text", "text": "Hi"}]
    annotate_comparisons(decisions, registry)
    assert "chart_kind" not in decisions[0]


# --- a shared plugin split by shape, not just by measures --------------------
#
# `_shared_plugin_shapes` catches two group members that read a different
# number of measures. It says nothing about a container built to host three
# children meeting a sibling needing four, a plugin drawn as a card meeting a
# bare sibling, or a header control one member has and another does not --
# every one of those is still "one viz_type" to the orchestrator, which sends
# only the group's first member to stage F and trusts the rest to fit the
# plugin built for it. `split_incompatible_groups` is the check the runner
# makes before that trust is spent on a generation call.


def _decision(
    region_id: str, viz_type: str, children: list[str] | None = None
) -> dict[str, Any]:
    return {
        "region_id": region_id,
        "decision": "new_plugin",
        "viz_type": viz_type,
        "plugin_archetype": "container" if children else "viz",
        "children": children or [],
    }


def test_a_group_that_genuinely_matches_is_not_split() -> None:
    """Same children count, same controls, same surface: one plugin really
    does fit every member, so nothing about the group changes."""
    regions = {
        "r01": {"chrome": {"surface": "card"}, "controls": [{"kind": "toggle"}]},
        "r02": {"chrome": {"surface": "card"}, "controls": [{"kind": "toggle"}]},
    }
    by_type = {
        "custom_panel": [
            _decision("r01", "custom_panel", ["c1", "c2"]),
            _decision("r02", "custom_panel", ["c3", "c4"]),
        ]
    }
    split, warnings = split_incompatible_groups(by_type, regions)
    assert warnings == []
    assert set(split) == {"custom_panel"}
    assert len(split["custom_panel"]) == 2


def test_a_container_with_a_different_number_of_children_is_split() -> None:
    """The documented failure: a plugin built to host 3 children was reused
    for a sibling needing 4, and both were dropped together when it broke."""
    regions: dict[str, dict[str, Any]] = {"r01": {}, "r02": {}}
    by_type = {
        "custom_panel": [
            _decision("r01", "custom_panel", ["c1", "c2", "c3"]),
            _decision("r02", "custom_panel", ["c1", "c2", "c3", "c4"]),
        ]
    }
    split, warnings = split_incompatible_groups(by_type, regions)
    assert len(warnings) == 1
    assert warnings[0]["viz_type"] == "custom_panel"
    assert warnings[0]["region_ids"] == ["r02"]
    assert "children" in warnings[0]["reason"]

    # group[0]'s own region keeps the plugin's original name -- it is the one
    # stage F is actually about to build a plugin from.
    assert split["custom_panel"][0]["region_id"] == "r01"
    assert split["custom_panel"][0]["viz_type"] == "custom_panel"

    # the mismatched member is renamed onto its own viz_type, in place, so it
    # gets a plugin built for its own shape instead of quietly sharing r01's.
    new_viz_type = warnings[0]["new_viz_type"]
    assert new_viz_type != "custom_panel"
    [renamed] = split[new_viz_type]
    assert renamed["region_id"] == "r02"
    assert renamed["viz_type"] == new_viz_type


def test_a_bare_sibling_of_a_card_plugin_is_split() -> None:
    """A plugin built to draw its own card cannot skip it for a bare sibling,
    and one built bare cannot grow a card around a sibling that wants one."""
    regions = {
        "r01": {"chrome": {"surface": "card"}},
        "r02": {"chrome": {"surface": "bare"}},
    }
    by_type = {
        "custom_tile": [
            _decision("r01", "custom_tile"),
            _decision("r02", "custom_tile"),
        ]
    }
    _, warnings = split_incompatible_groups(by_type, regions)
    assert len(warnings) == 1
    assert "chrome.surface" in warnings[0]["reason"]


def test_a_control_one_member_lacks_is_split() -> None:
    """A control drawn on one member's own header has no slot in a plugin
    built for a sibling that never shows one."""
    regions: dict[str, dict[str, Any]] = {
        "r01": {"controls": [{"kind": "date_range"}]},
        "r02": {"controls": []},
    }
    by_type = {
        "custom_header": [
            _decision("r01", "custom_header"),
            _decision("r02", "custom_header"),
        ]
    }
    _, warnings = split_incompatible_groups(by_type, regions)
    assert len(warnings) == 1
    assert "controls" in warnings[0]["reason"]


def test_a_group_of_three_where_two_share_the_mismatched_shape_extra_plugin() -> None:
    """Three regions, two shapes: the two that agree keep sharing a plugin,
    so the split costs one extra generation, not two."""
    regions: dict[str, dict[str, Any]] = {"r01": {}, "r02": {}, "r03": {}}
    by_type = {
        "custom_panel": [
            _decision("r01", "custom_panel", ["c1", "c2"]),
            _decision("r02", "custom_panel", ["c1", "c2", "c3"]),
            _decision("r03", "custom_panel", ["c1", "c2", "c3"]),
        ]
    }
    split, warnings = split_incompatible_groups(by_type, regions)
    assert len(warnings) == 1
    assert sorted(warnings[0]["region_ids"]) == ["r02", "r03"]
    assert len(split) == 2
    assert len(split["custom_panel"]) == 1
    [extra_group] = [group for name, group in split.items() if name != "custom_panel"]
    assert len(extra_group) == 2


def test_structural_shape_ignores_cosmetic_fields() -> None:
    """Only the axes that decide what a plugin can render are compared -- a
    title or a role differing between two regions is not a reason to split."""
    region_a = {"title": "AWS", "role": "kpi", "chrome": {"surface": "card"}}
    region_b = {"title": "GCP", "role": "kpi", "chrome": {"surface": "card"}}
    shape_a = structural_shape(_decision("r01", "custom_x"), region_a)
    shape_b = structural_shape(_decision("r02", "custom_x"), region_b)
    assert shape_a == shape_b


# --- reuse confirmed against the real search transcript ---------------------


def _reuse_design() -> dict[str, Any]:
    return {
        "global": {"title": "Reuse test"},
        "regions": [
            {
                "region_id": "r01",
                "n": 1,
                "role": "kpi",
                "frame": None,
                "children": [],
                "same_as": None,
            }
        ],
    }


def _reuse_binding_set() -> dict[str, Any]:
    return {
        "status": "ok",
        "shared_dataset_id": SHARED,
        "bindings": [{"region_id": "r01", "dataset_id": 31}],
    }


def _reuse_plan(chart_id: int = 42) -> dict[str, Any]:
    return {
        "status": "needs_approval",
        "design_system": {"palette": ["#0af"]},
        "decisions": [
            {
                "region_id": "r01",
                "ref": "c1",
                "decision": "reuse",
                "existing_chart_id": chart_id,
                "reuse_evidence": "get_chart_info confirmed viz_type=big_number",
                "thumbnail_evidence": "matches the KPI thumbnail",
            }
        ],
    }


def _get_chart_info_search(
    chart_id: int, result_id: int | None = None, error: str | None = None
) -> dict[str, Any]:
    return {
        "tool": "get_chart_info",
        "arguments": {"identifier": chart_id},
        "result": None
        if error
        else {
            "id": result_id if result_id is not None else chart_id,
            "slice_name": "AWS Coverage",
            "viz_type": "big_number",
            "datasource_name": "coverage_by_cloud",
        },
        "error": error,
    }


def test_reuse_confirmed_by_a_real_search_passes() -> None:
    """A `get_chart_info` call in the transcript that actually named this
    chart id makes the claim a fact, not a guess."""
    problems = validate(
        _reuse_plan(42),
        _reuse_design(),
        _reuse_binding_set(),
        REGISTRY,
        chart_searches=[_get_chart_info_search(42)],
    )
    assert not any("no get_chart_info call" in p for p in problems)


def test_reuse_never_confirmed_by_a_search_is_flagged() -> None:
    """A transcript that exists but never looked up this id is exactly the
    case the old check could not see: a plausible id nobody confirmed."""
    problems = validate(
        _reuse_plan(42),
        _reuse_design(),
        _reuse_binding_set(),
        REGISTRY,
        chart_searches=[_get_chart_info_search(99)],
    )
    assert any("no get_chart_info call" in p for p in problems)


def test_reuse_with_no_transcript_is_not_checked() -> None:
    """`chart_searches` is optional. Every caller that predates this check --
    including the plan/design/binding_set fixtures above -- calls `validate`
    without it, and must keep passing."""
    problems = validate(
        _reuse_plan(42), _reuse_design(), _reuse_binding_set(), REGISTRY
    )
    assert not any("no get_chart_info call" in p for p in problems)


def test_reuse_flagged_when_the_only_search_errored() -> None:
    """A failed lookup confirms nothing -- it is a call that came back with an
    error, not evidence the chart exists."""
    problems = validate(
        _reuse_plan(42),
        _reuse_design(),
        _reuse_binding_set(),
        REGISTRY,
        chart_searches=[_get_chart_info_search(42, error="not found")],
    )
    assert any("no get_chart_info call" in p for p in problems)


def test_reuse_confirmed_by_uuid_lookup_matches_on_the_returned_id() -> None:
    """The model may look a chart up by UUID and reuse it by its integer id
    -- either one on the call is enough to confirm the other."""
    problems = validate(
        _reuse_plan(42),
        _reuse_design(),
        _reuse_binding_set(),
        REGISTRY,
        chart_searches=[
            {
                "tool": "get_chart_info",
                "arguments": {"identifier": "a1b2c3d4"},
                "result": {"id": 42, "uuid": "a1b2c3d4", "slice_name": "AWS Coverage"},
                "error": None,
            }
        ],
    )
    assert not any("no get_chart_info call" in p for p in problems)


# --- structured reuse evidence, for a human to judge independently ----------


def test_annotate_reuse_evidence_attaches_the_real_lookup() -> None:
    """The user reading the plan gets the actual `get_chart_info` result, not
    only C's paraphrase of why it matches."""
    decisions: list[dict[str, Any]] = [
        {
            "region_id": "r01",
            "decision": "reuse",
            "existing_chart_id": 42,
            "reuse_evidence": "same dataset, same metric",
        }
    ]
    chart_searches = [
        {
            "tool": "get_chart_info",
            "arguments": {"identifier": 42},
            "result": {
                "id": 42,
                "slice_name": "AWS Coverage",
                "viz_type": "big_number",
                "datasource_name": "coverage_by_cloud",
                "form_data": {"metrics": ["count"], "groupby": ["provider"]},
            },
            "error": None,
        }
    ]
    c_resolve.annotate_reuse_evidence(decisions, chart_searches)
    evidence = decisions[0]["reuse_confirmed_evidence"]
    assert evidence["name"] == "AWS Coverage"
    assert evidence["viz_type"] == "big_number"
    assert evidence["dataset"] == "coverage_by_cloud"
    assert evidence["metrics"] == ["count"]
    assert evidence["columns"] == ["provider"]
    # Additive: C's own rationale is left exactly as written.
    assert decisions[0]["reuse_evidence"] == "same dataset, same metric"


def test_annotate_reuse_evidence_without_a_matching_search_leaves_no_field() -> None:
    decisions = [
        {
            "region_id": "r01",
            "decision": "reuse",
            "existing_chart_id": 42,
            "reuse_evidence": "same dataset, same metric",
        }
    ]
    c_resolve.annotate_reuse_evidence(decisions, chart_searches=[])
    assert "reuse_confirmed_evidence" not in decisions[0]


def test_annotate_reuse_evidence_ignores_non_reuse_decisions() -> None:
    decisions = [
        {"region_id": "r01", "decision": "configure", "viz_type": "big_number"}
    ]
    chart_searches = [
        {
            "tool": "get_chart_info",
            "arguments": {"identifier": 42},
            "result": {"id": 42, "slice_name": "AWS Coverage"},
            "error": None,
        }
    ]
    c_resolve.annotate_reuse_evidence(decisions, chart_searches)
    assert "reuse_confirmed_evidence" not in decisions[0]
