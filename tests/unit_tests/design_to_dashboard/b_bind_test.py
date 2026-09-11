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
"""Structural validation of stage B's bindings, and the joins that read them."""

from __future__ import annotations

import copy
from typing import Any

import pytest

from superset.design_to_dashboard.applier import _dataset_for
from superset.design_to_dashboard.stages.b_bind import parent_of, validate
from superset.design_to_dashboard.stages.clarify import _dedupe


@pytest.fixture
def design() -> dict[str, Any]:
    """Two atomic regions and one composite card."""
    return {
        "regions": [
            {"region_id": "r01_title", "role": "header", "composition": "atomic"},
            {"region_id": "r02_trend", "role": "chart", "composition": "atomic"},
            {"region_id": "r03_card", "role": "kpi", "composition": "composite"},
        ]
    }


def _binding(region_id: str, **overrides: Any) -> dict[str, Any]:
    binding = {
        "region_id": region_id,
        "state": "bound",
        "dataset_id": 42,
        "measures": ["total_cost"],
        "dimensions": [],
    }
    binding.update(overrides)
    return binding


@pytest.fixture
def bindings() -> dict[str, Any]:
    """A binding set that satisfies every rule."""
    return {
        "status": "ok",
        "bindings": [
            _binding("r02_trend"),
            _binding("r03_card:1"),
            _binding("r03_card:2"),
        ],
        "questions": [],
        "created_datasets": [],
    }


def test_valid_binding_set(bindings: dict[str, Any], design: dict[str, Any]) -> None:
    assert validate(bindings, design) == []


def test_composite_children_are_not_unknown_regions(
    bindings: dict[str, Any], design: dict[str, Any]
) -> None:
    """The `:N` suffix is the contract, not an error."""
    assert not any("unknown region" in p for p in validate(bindings, design))


def test_dropped_region_is_reported(
    bindings: dict[str, Any], design: dict[str, Any]
) -> None:
    bindings["bindings"] = [
        b for b in bindings["bindings"] if b["region_id"] != "r02_trend"
    ]
    assert "region not bound: r02_trend" in validate(bindings, design)


def test_binding_for_unknown_region_is_reported(
    bindings: dict[str, Any], design: dict[str, Any]
) -> None:
    bindings["bindings"].append(_binding("r09_ghost"))
    assert "binding for unknown region: r09_ghost" in validate(bindings, design)


def test_composite_bound_as_a_single_measure_is_reported(
    bindings: dict[str, Any], design: dict[str, Any]
) -> None:
    bindings["bindings"] = [_binding("r02_trend"), _binding("r03_card")]
    assert any(
        "is composite but has one unsuffixed" in p for p in validate(bindings, design)
    )


def test_atomic_region_split_into_children_is_reported(
    bindings: dict[str, Any], design: dict[str, Any]
) -> None:
    bindings["bindings"].append(_binding("r02_trend:1"))
    assert any(
        "is not composite but has 2 bindings" in p for p in validate(bindings, design)
    )


def test_invalid_status_is_reported(
    bindings: dict[str, Any], design: dict[str, Any]
) -> None:
    bindings["status"] = "done"
    assert any("invalid status" in p for p in validate(bindings, design))


def test_bound_without_columns_is_reported(
    bindings: dict[str, Any], design: dict[str, Any]
) -> None:
    bindings["bindings"][0]["measures"] = []
    assert any("names no columns" in p for p in validate(bindings, design))


def test_unavailable_binding_requires_needs_input(
    bindings: dict[str, Any], design: dict[str, Any]
) -> None:
    bindings["bindings"][0]["state"] = "unavailable"
    assert any("status is not 'needs_input'" in p for p in validate(bindings, design))


# --- created datasets: the join that caused the apply failure ---------------


def _pending(bindings: dict[str, Any], region_ids: list[str]) -> dict[str, Any]:
    """Composite children waiting on a dataset this run will create."""
    pending = copy.deepcopy(bindings)
    for binding in pending["bindings"]:
        if binding["region_id"].startswith("r03_card"):
            binding["dataset_id"] = None
            binding["state"] = "placeholder"
    pending["created_datasets"] = [
        {
            "name": "d2d_card",
            "kind": "placeholder",
            "database_id": 1,
            "region_ids": region_ids,
        }
    ]
    return pending


def test_dataset_listing_only_the_parent_is_reported(
    bindings: dict[str, Any], design: dict[str, Any]
) -> None:
    """The confirmed apply failure: `region_ids: ["r03_card"]` while the
    bindings are `r03_card:1` and `:2`, so neither child is ever repointed."""
    problems = validate(_pending(bindings, ["r03_card"]), design)
    assert any("no created dataset lists it" in p for p in problems)


def test_dataset_listing_the_children_is_accepted(
    bindings: dict[str, Any], design: dict[str, Any]
) -> None:
    assert validate(_pending(bindings, ["r03_card:1", "r03_card:2"]), design) == []


def test_derived_dataset_may_leave_the_binding_bound(
    bindings: dict[str, Any], design: dict[str, Any]
) -> None:
    """A `derived` dataset carries real data, so its regions stay `bound` even
    though the dataset has no id yet -- the stage prompt says so explicitly."""
    pending = _pending(bindings, ["r03_card:1", "r03_card:2"])
    for binding in pending["bindings"]:
        if binding["region_id"].startswith("r03_card"):
            binding["state"] = "bound"
    assert validate(pending, design) == []


def test_dataset_naming_an_unknown_region_is_reported(
    bindings: dict[str, Any], design: dict[str, Any]
) -> None:
    bindings["created_datasets"] = [
        {"name": "ghost", "kind": "derived", "database_id": 1, "region_ids": ["r99_no"]}
    ]
    assert any("names an unknown region" in p for p in validate(bindings, design))


def test_dataset_serving_no_region_is_reported(
    bindings: dict[str, Any], design: dict[str, Any]
) -> None:
    bindings["created_datasets"] = [
        {"name": "orphan", "kind": "derived", "database_id": 1, "region_ids": []}
    ]
    assert any("serves no region" in p for p in validate(bindings, design))


# --- the applier's side of the same join ------------------------------------


@pytest.mark.parametrize(
    "mapping,region_id,expected",
    [
        ({"r13_top": 7}, "r13_top:1", 7),
        ({"r13_top": 7}, "r13_top", 7),
        ({"r13_top": 7, "r13_top:1": 9}, "r13_top:1", 9),
        ({"r13_top": 7}, "r14_other:1", None),
        ({"r13_top": 7}, None, None),
    ],
)
def test_dataset_for_falls_back_to_the_parent(
    mapping: dict[str, int], region_id: str | None, expected: int | None
) -> None:
    assert _dataset_for(mapping, region_id) == expected


def test_parent_of() -> None:
    assert parent_of("r07_card:2") == "r07_card"
    assert parent_of("r07_card") == "r07_card"


# --- duplicate questions ----------------------------------------------------


def test_questions_about_the_same_region_collapse() -> None:
    kept, notes = _dedupe(
        [
            {
                "region_id": "r05_f",
                "question": "The Filter button never shows its contents. Drop it?",
            },
            {
                "region_id": "r05_f",
                "question": "The Filter button never shows what it filters. "
                "Drop it or wire it?",
                "why_it_matters": "it would ship a dead control",
                "default": "use the native filter bar",
            },
        ]
    )
    assert len(kept) == 1
    assert kept[0]["default"] == "use the native filter bar", "the fuller one wins"
    assert notes


def test_reworded_questions_without_a_region_collapse() -> None:
    kept, _ = _dedupe(
        [
            {
                "question": "None of the 21 datasets hold cloud cost data. "
                "Create placeholder tables, or point me at your billing database?"
            },
            {
                "question": "None of the 21 datasets visible hold cloud cost "
                "data. Should I create placeholder tables, or do you have a "
                "database with real billing data?"
            },
        ]
    )
    assert len(kept) == 1


def test_distinct_questions_are_kept() -> None:
    kept, notes = _dedupe(
        [
            {"region_id": "r01", "question": "Embedded or standalone?"},
            {
                "region_id": "r02",
                "question": "Dotted forecast line on the trend chart?",
            },
        ]
    )
    assert len(kept) == 2
    assert not notes
