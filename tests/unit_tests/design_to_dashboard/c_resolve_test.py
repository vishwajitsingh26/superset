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

from superset.design_to_dashboard.stages.c_resolve import validate
from superset.design_to_dashboard.stages.f_scaffold import (
    build_user_prompt,
    resolve_children,
)

REGISTRY = str(
    pathlib.Path(__file__).resolve().parents[3]
    / "design-to-dashboard"
    / "fixtures"
    / "viz_registry.json"
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
