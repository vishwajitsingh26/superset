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
"""Stage C's plan, and what a wrapper is told before it is written."""

from __future__ import annotations

import copy
import pathlib
from typing import Any

import pytest

from superset.design_to_dashboard.applier import _dataset_for
from superset.design_to_dashboard.stages.c_resolve import (
    _unanswered_regions,
    validate,
)
from superset.design_to_dashboard.stages.f_scaffold import (
    build_user_prompt,
    resolve_children,
)
from superset.utils import json

# Recorded stage outputs live beside the tests that assert on them. The viz
# registry does not: it is a runtime asset the pipeline itself loads, and a
# copy here would drift from the one stage C is actually given.
FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures"
REGISTRY = str(
    pathlib.Path(__file__).resolve().parents[3]
    / "design-to-dashboard"
    / "fixtures"
    / "viz_registry.json"
)


def _fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture
def design() -> dict[str, Any]:
    return _fixture("stage_a_output.json")


@pytest.fixture
def bindings() -> dict[str, Any]:
    return _fixture("stage_b_output.json")


@pytest.fixture
def plan() -> dict[str, Any]:
    return _fixture("stage_c_output.json")


def test_reference_plan_is_valid(
    plan: dict[str, Any], design: dict[str, Any], bindings: dict[str, Any]
) -> None:
    assert validate(plan, design, bindings, REGISTRY) == []


def test_container_children_are_not_unknown_regions(
    plan: dict[str, Any], design: dict[str, Any], bindings: dict[str, Any]
) -> None:
    """`_base_region` exists so `r03_kpi_aws:3` resolves to its parent."""
    problems = validate(plan, design, bindings, REGISTRY)
    assert not any("unknown region" in p for p in problems)


# --- decisions and bindings must account for each other ---------------------


def test_a_forgotten_card_is_reported(
    plan: dict[str, Any], design: dict[str, Any], bindings: dict[str, Any]
) -> None:
    """Neither the pieces nor the parent resolved: the bound data is orphaned."""
    plan["decisions"] = [
        d for d in plan["decisions"] if not d["region_id"].startswith("r08_by_service")
    ]
    problems = validate(plan, design, bindings, REGISTRY)
    assert any("r08_by_service:1: stage B bound this piece" in p for p in problems)
    assert any("r08_by_service:2: stage B bound this piece" in p for p in problems)


def test_a_parent_decision_may_absorb_its_pieces(
    plan: dict[str, Any], design: dict[str, Any], bindings: dict[str, Any]
) -> None:
    """The card itself draws the number and the delta, so `:1` and `:2` need no
    decision of their own. Only a piece with no decision *and* no parent is a
    problem."""
    assert not any(
        "r03_kpi_aws:1" in p for p in validate(plan, design, bindings, REGISTRY)
    )


def test_a_decision_with_no_data_anywhere_is_reported(
    plan: dict[str, Any], design: dict[str, Any], bindings: dict[str, Any]
) -> None:
    """A chart whose whole card is unbound reaches stage D with nothing to
    query, and the model invents a datasource_id."""
    bindings["bindings"] = [
        b for b in bindings["bindings"] if b["region_id"] != "r09_cost_detail_table"
    ]
    problems = validate(plan, design, bindings, REGISTRY)
    assert any("bound no data for it" in p for p in problems)


# --- the verdict has to show its working ------------------------------------


def test_missing_thumbnail_evidence_is_reported(
    plan: dict[str, Any], design: dict[str, Any], bindings: dict[str, Any]
) -> None:
    for decision in plan["decisions"]:
        if decision["region_id"] == "r09_cost_detail_table":
            decision["thumbnail_evidence"] = ""
    problems = validate(plan, design, bindings, REGISTRY)
    assert any("without thumbnail_evidence" in p for p in problems)


def test_a_dropped_region_needs_no_thumbnail_evidence(
    plan: dict[str, Any], design: dict[str, Any], bindings: dict[str, Any]
) -> None:
    for decision in plan["decisions"]:
        if decision["decision"] == "drop":
            decision["thumbnail_evidence"] = ""
    assert not any(
        "without thumbnail_evidence" in p
        for p in validate(plan, design, bindings, REGISTRY)
    )


def test_a_tabbed_card_flattened_to_one_chart_is_reported(
    plan: dict[str, Any], design: dict[str, Any], bindings: dict[str, Any]
) -> None:
    """Stage A saw three tabs; a card built as its visible tab alone looks
    correct, which is why nothing noticed."""
    for decision in plan["decisions"]:
        if decision["region_id"] == "r08_by_service":
            decision.update(
                decision="configure",
                viz_type="echarts_timeseries_bar",
                children=[],
                plugin_archetype=None,
            )
    problems = validate(plan, design, bindings, REGISTRY)
    assert any("saw a tab switcher here" in p for p in problems)


# --- the dataset join, in both directions -----------------------------------


@pytest.mark.parametrize(
    "mapping,region_id,expected",
    [
        ({"r07": 5}, "r07:2", 5),  # child inherits the parent's dataset
        ({"r07:1": 9}, "r07", 9),  # parent decision, dataset filed under a child
        ({"r07": 5, "r07:1": 9}, "r07", 5),  # an exact hit always wins
        ({"r07:2": 8, "r07:1": 9}, "r07", 9),  # deterministic: lowest child
        ({"r07": 5}, "r08:1", None),
        ({"r07": 5}, None, None),
    ],
)
def test_dataset_for_matches_in_either_direction(
    mapping: dict[str, int], region_id: str | None, expected: int | None
) -> None:
    assert _dataset_for(mapping, region_id) == expected


# --- what a wrapper knows before it is written ------------------------------


def test_children_resolve_to_real_charts(plan: dict[str, Any]) -> None:
    """A ref means nothing to the author of a container."""
    resolved = resolve_children({"children": ["c5"]}, plan["decisions"])
    assert resolved[0]["region_id"] == "r08_by_service:1"
    assert resolved[0]["viz_type"] == "echarts_timeseries_bar"
    assert resolved[0]["slice_name"]


def test_unknown_refs_are_dropped_not_guessed(plan: dict[str, Any]) -> None:
    assert resolve_children({"children": ["c999"]}, plan["decisions"]) == []


def test_a_wrapper_is_told_what_it_hosts(plan: dict[str, Any]) -> None:
    children = resolve_children({"children": ["c5"]}, plan["decisions"])
    prompt = build_user_prompt({}, {}, {"children": ["c5"]}, {}, None, children)
    assert "What this wrapper hosts" in prompt
    assert "echarts_timeseries_bar" in prompt
    assert "do not re-implement what they draw" in prompt


def test_a_wrapper_is_told_about_tabs(plan: dict[str, Any]) -> None:
    region = {
        "interactions": [
            "tab switcher with three options (Compute / Storage / Network)"
        ]
    }
    children = resolve_children({"children": ["c5"]}, plan["decisions"])
    prompt = build_user_prompt(region, {}, {"children": ["c5"]}, {}, None, children)
    assert "Compute / Storage / Network" in prompt
    assert "Coming soon" in prompt


def test_a_plain_plugin_gets_no_hosting_note() -> None:
    prompt = build_user_prompt({}, {}, {"children": []}, {}, None, [])
    assert "What this wrapper hosts" not in prompt


def test_build_user_prompt_does_not_mutate_the_decision() -> None:
    decision = {"children": ["c1"], "viz_type": "custom_kpi_card"}
    before = copy.deepcopy(decision)
    build_user_prompt({}, {}, decision, {}, None, [])
    assert decision == before


# --- the user's answers have to actually reach the check -------------------


def test_an_answered_blocking_question_is_not_reported_unanswered() -> None:
    """`session.ask` returns the whole reply envelope, and the runner stores
    that. Looking a question id up in the envelope always missed, so every
    region carrying a blocking question was reported unanswered however it had
    been answered -- and stage C refused to build sections it had the answer
    for."""
    binding_set = {
        "questions": [
            {"id": "q2", "region_id": "r03_filter"},
            {"id": "q7", "region_id": "r05_currency"},
        ],
        "user_answers": {"answers": {"q2": "cloud provider, region", "q7": "a column"}},
    }
    assert _unanswered_regions(binding_set) == set()


def test_the_inner_map_is_also_accepted() -> None:
    binding_set = {
        "questions": [{"id": "q2", "region_id": "r03_filter"}],
        "user_answers": {"q2": "cloud provider"},
    }
    assert _unanswered_regions(binding_set) == set()


def test_a_question_left_blank_is_still_unanswered() -> None:
    binding_set = {
        "questions": [
            {"id": "q2", "region_id": "r03_filter"},
            {"id": "q7", "region_id": "r05_currency"},
        ],
        "user_answers": {"answers": {"q2": "   ", "q7": "a column"}},
    }
    assert _unanswered_regions(binding_set) == {"r03_filter"}


def test_no_answers_leaves_every_question_unanswered() -> None:
    binding_set = {
        "questions": [{"id": "q2", "region_id": "r03_filter"}],
        "user_answers": None,
    }
    assert _unanswered_regions(binding_set) == {"r03_filter"}
