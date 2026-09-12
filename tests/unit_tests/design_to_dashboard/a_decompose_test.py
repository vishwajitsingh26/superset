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
"""Structural validation of stage A's reading of a design.

The fixture is modelled on a real page: a `Coverage` panel holding two metric
cards, a "coming soon" placeholder and a table, with `Instance Runtime` drawn
the same way beside it. That shape is what the contract exists for -- real
nesting, and a component drawn more than once.
"""

from __future__ import annotations

import copy
import pathlib
from typing import Any

import pytest

from superset.design_to_dashboard.llm.base import LLMResponse
from superset.design_to_dashboard.stages.a_decompose import (
    assign_region_ids,
    validate,
)
from superset.utils import json

KNOWN_VIZ = {"table", "big_number_total"}


@pytest.fixture
def analysis() -> dict[str, Any]:
    return {
        "status": "ok",
        "regions": [
            {
                "n": 1,
                "role": "wrapper",
                "title": "Coverage",
                "frame": "none",
                "children": [2, 3, 4, 5],
                "same_as": None,
                "bbox": {"x": 0.01, "y": 0.64, "w": 0.48, "h": 0.14},
                "stock_candidate": None,
            },
            {
                "n": 2,
                "role": "kpi",
                "title": "AWS Coverage",
                "frame": None,
                "children": [],
                "same_as": None,
                "bbox": {"x": 0.02, "y": 0.66, "w": 0.14, "h": 0.03},
                "stock_candidate": "big_number_total",
            },
            {
                "n": 3,
                "role": "kpi",
                "title": "GCP Coverage",
                "frame": None,
                "children": [],
                "same_as": 2,
                "bbox": {"x": 0.17, "y": 0.66, "w": 0.14, "h": 0.03},
                "stock_candidate": "big_number_total",
            },
            {
                "n": 4,
                "role": "kpi",
                "title": "Coming Soon",
                "frame": None,
                "children": [],
                "same_as": 2,
                "bbox": {"x": 0.32, "y": 0.66, "w": 0.14, "h": 0.03},
                "stock_candidate": None,
            },
            {
                "n": 5,
                "role": "table",
                "title": "Top Uncovered Instances",
                "frame": None,
                "children": [],
                "same_as": None,
                "bbox": {"x": 0.02, "y": 0.70, "w": 0.45, "h": 0.07},
                "stock_candidate": None,
            },
            {
                "n": 6,
                "role": "wrapper",
                "title": "Instance Runtime",
                "frame": "none",
                "children": [],
                "same_as": 1,
                "bbox": {"x": 0.51, "y": 0.64, "w": 0.48, "h": 0.14},
                "stock_candidate": None,
            },
        ],
        "global": {"reading_order": [1, 2, 3, 4, 5, 6]},
    }


def test_a_well_formed_reading_has_no_problems(analysis: dict[str, Any]) -> None:
    assert validate(analysis, KNOWN_VIZ) == []


def test_validate_does_not_mutate_its_input(analysis: dict[str, Any]) -> None:
    before = copy.deepcopy(analysis)
    validate(analysis, KNOWN_VIZ)
    assert analysis == before


# --- region ids are minted, never asked for ---------------------------------


def test_ids_come_from_the_number_and_the_visible_title(
    analysis: dict[str, Any],
) -> None:
    """The whole point: `AWS Coverage` cannot come back as `r02_kpi_aws`."""
    ids = [r["region_id"] for r in assign_region_ids(analysis)["regions"]]
    assert ids == [
        "r01_coverage",
        "r02_aws_coverage",
        "r03_gcp_coverage",
        "r04_coming_soon",
        "r05_top_uncovered_instances",
        "r06_instance_runtime",
    ]


@pytest.mark.parametrize(
    "title,expected",
    [
        ("Spend by Région", "r01_spend_by_region"),
        ("€ Spend", "r01_spend"),
        ("Top  Regions — by Spend", "r01_top_regions_by_spend"),
        ("50% of Total", "r01_50_of_total"),
    ],
)
def test_a_title_is_flattened_not_rejected(title: str, expected: str) -> None:
    """A non-ASCII title used to produce an id the old grammar refused."""
    out = assign_region_ids({"regions": [{"n": 1, "role": "kpi", "title": title}]})
    assert out["regions"][0]["region_id"] == expected


def test_an_untitled_region_falls_back_to_its_role() -> None:
    out = assign_region_ids(
        {"regions": [{"n": 7, "role": "decoration", "title": None}]}
    )
    assert out["regions"][0]["region_id"] == "r07_decoration"


# --- the region's own fields ------------------------------------------------


def test_a_missing_n_is_rejected(analysis: dict[str, Any]) -> None:
    del analysis["regions"][1]["n"]
    assert any("expected a whole number" in p for p in validate(analysis, KNOWN_VIZ))


def test_a_duplicate_n_is_rejected(analysis: dict[str, Any]) -> None:
    analysis["regions"][2]["n"] = 2
    assert any("duplicate n: 2" in p for p in validate(analysis, KNOWN_VIZ))


def test_an_unknown_role_is_rejected(analysis: dict[str, Any]) -> None:
    analysis["regions"][1]["role"] = "container"
    assert any("role 'container'" in p for p in validate(analysis, KNOWN_VIZ))


def test_a_wrapper_must_say_what_its_frame_does(analysis: dict[str, Any]) -> None:
    analysis["regions"][0]["frame"] = None
    assert any("frame None is not one of" in p for p in validate(analysis, KNOWN_VIZ))


def test_a_leaf_frames_nothing(analysis: dict[str, Any]) -> None:
    analysis["regions"][1]["frame"] = "tabs"
    assert any("only a wrapper has one" in p for p in validate(analysis, KNOWN_VIZ))


def test_a_tabbed_wrapper_is_accepted(analysis: dict[str, Any]) -> None:
    """The card the old `composition` enum had no honest value for."""
    analysis["regions"][0]["frame"] = "tabs"
    assert validate(analysis, KNOWN_VIZ) == []


# --- geometry is the unit square --------------------------------------------


def test_pixels_instead_of_fractions_are_caught(analysis: dict[str, Any]) -> None:
    analysis["regions"][1]["bbox"] = {"x": 24, "y": 138, "w": 337, "h": 143}
    assert any("fractions from 0.0 to 1.0" in p for p in validate(analysis, KNOWN_VIZ))


def test_a_box_touching_the_edge_is_allowed(analysis: dict[str, Any]) -> None:
    analysis["regions"][0]["bbox"] = {"x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0}
    assert validate(analysis, KNOWN_VIZ) == []


def test_a_zero_area_box_is_rejected(analysis: dict[str, Any]) -> None:
    analysis["regions"][1]["bbox"] = {"x": 0.1, "y": 0.1, "w": 0.0, "h": 0.1}
    assert any("positive w and h" in p for p in validate(analysis, KNOWN_VIZ))


# --- nesting ----------------------------------------------------------------


def test_a_child_must_sit_inside_its_parent(analysis: dict[str, Any]) -> None:
    """The check that inverted: containment used to be the failure."""
    analysis["regions"][1]["bbox"] = {"x": 0.02, "y": 0.10, "w": 0.14, "h": 0.03}
    assert any("not inside it" in p for p in validate(analysis, KNOWN_VIZ))


def test_two_parents_cannot_claim_one_child(analysis: dict[str, Any]) -> None:
    analysis["regions"][5]["children"] = [2]
    assert any("claimed by both" in p for p in validate(analysis, KNOWN_VIZ))


def test_only_a_wrapper_has_children(analysis: dict[str, Any]) -> None:
    analysis["regions"][4]["children"] = [2]
    assert any("is a wrapper" in p for p in validate(analysis, KNOWN_VIZ))


def test_a_child_that_is_not_a_region_is_rejected(analysis: dict[str, Any]) -> None:
    analysis["regions"][0]["children"] = [2, 3, 4, 5, 99]
    assert any("child 99 is not a region" in p for p in validate(analysis, KNOWN_VIZ))


def test_a_region_cannot_contain_itself(analysis: dict[str, Any]) -> None:
    analysis["regions"][0]["children"] = [1]
    assert any("lists itself" in p for p in validate(analysis, KNOWN_VIZ))


def test_nesting_can_go_deeper_than_two_levels(analysis: dict[str, Any]) -> None:
    """The design decides the depth, not the contract."""
    analysis["regions"][4]["role"] = "wrapper"
    analysis["regions"][4]["frame"] = "none"
    analysis["regions"][4]["children"] = [7]
    analysis["regions"].append(
        {
            "n": 7,
            "role": "chart",
            "title": "Coverage bar",
            "frame": None,
            "children": [],
            "same_as": None,
            "bbox": {"x": 0.03, "y": 0.71, "w": 0.10, "h": 0.02},
            "stock_candidate": None,
        }
    )
    analysis["global"]["reading_order"].append(7)
    assert validate(analysis, KNOWN_VIZ) == []


# --- the component graph ----------------------------------------------------


def test_same_as_must_point_backwards(analysis: dict[str, Any]) -> None:
    analysis["regions"][1]["same_as"] = 5
    assert any("comes later" in p for p in validate(analysis, KNOWN_VIZ))


def test_same_as_cannot_chain(analysis: dict[str, Any]) -> None:
    """Every copy names the first occurrence, or one component reads as two."""
    analysis["regions"][3]["same_as"] = 3
    assert any("itself a repeat" in p for p in validate(analysis, KNOWN_VIZ))


def test_same_as_cannot_point_at_itself(analysis: dict[str, Any]) -> None:
    analysis["regions"][2]["same_as"] = 3
    assert any("points at itself" in p for p in validate(analysis, KNOWN_VIZ))


def test_a_wrapper_may_repeat_another_wrapper(analysis: dict[str, Any]) -> None:
    """Instance Runtime is the Coverage panel drawn again -- one plugin, two uses."""
    assert analysis["regions"][5]["same_as"] == 1
    assert validate(analysis, KNOWN_VIZ) == []


# --- stock_candidate --------------------------------------------------------


def test_a_wrapper_never_names_a_stock_viz_type(analysis: dict[str, Any]) -> None:
    analysis["regions"][0]["stock_candidate"] = "table"
    assert any("on a wrapper" in p for p in validate(analysis, KNOWN_VIZ))


def test_an_unregistered_viz_type_is_rejected(analysis: dict[str, Any]) -> None:
    analysis["regions"][4]["stock_candidate"] = "custom_made_up"
    assert any("not a registered viz type" in p for p in validate(analysis, KNOWN_VIZ))


def test_without_a_registry_a_candidate_is_taken_on_trust(
    analysis: dict[str, Any],
) -> None:
    analysis["regions"][4]["stock_candidate"] = "anything_at_all"
    assert validate(analysis) == []


# --- the reading as a whole -------------------------------------------------


def test_status_must_be_ok(analysis: dict[str, Any]) -> None:
    analysis["status"] = "partial"
    assert any("invalid status" in p for p in validate(analysis, KNOWN_VIZ))


def test_no_regions_is_fatal(analysis: dict[str, Any]) -> None:
    analysis["regions"] = []
    assert validate(analysis, KNOWN_VIZ) == ["no regions were read from the design"]


def test_reading_order_must_name_every_region(analysis: dict[str, Any]) -> None:
    analysis["global"]["reading_order"] = [1, 2, 3, 4, 5]
    assert any("omits region 6" in p for p in validate(analysis, KNOWN_VIZ))


def test_reading_order_cannot_name_an_unknown_region(
    analysis: dict[str, Any],
) -> None:
    analysis["global"]["reading_order"].append(99)
    assert any("unknown region: 99" in p for p in validate(analysis, KNOWN_VIZ))


def test_missing_reading_order_is_rejected(analysis: dict[str, Any]) -> None:
    del analysis["global"]["reading_order"]
    assert "global.reading_order is missing" in validate(analysis, KNOWN_VIZ)


# --- the call ---------------------------------------------------------------


class _Provider:
    """Replies with each payload in turn, recording the prompts it was given.

    The parameter names match `LLMProvider.complete` exactly: a Protocol is
    satisfied structurally, and a renamed keyword argument does not satisfy it.
    """

    name = "stub"

    def __init__(self, *payloads: dict[str, Any]) -> None:
        self._payloads = list(payloads)
        self.prompts: list[str] = []

    def complete(
        self, system_prompt: str, user_prompt: str, *_args: Any, **_kwargs: Any
    ) -> LLMResponse:
        self.prompts.append(user_prompt)
        return LLMResponse(text=json.dumps(self._payloads.pop(0)), cost_usd=1.0)


def _prompts_dir() -> pathlib.Path:
    import superset.design_to_dashboard.stages.a_decompose as module

    root = pathlib.Path(module.__file__).parents[3]
    return root / "design-to-dashboard" / "prompts"


def test_a_bad_reading_is_asked_again(analysis: dict[str, Any]) -> None:
    from superset.design_to_dashboard.stages.a_decompose import run

    broken = copy.deepcopy(analysis)
    broken["regions"][1]["role"] = "container"
    provider = _Provider(broken, analysis)

    result, cost = run(provider, "a dashboard", [], _prompts_dir())

    assert validate(result) == [], "the second reading is the one returned"
    assert cost == 2.0, "both calls are paid for"


def test_the_repair_names_what_was_wrong(analysis: dict[str, Any]) -> None:
    from superset.design_to_dashboard.stages.a_decompose import run

    broken = copy.deepcopy(analysis)
    broken["regions"][1]["bbox"] = {"x": 24, "y": 138, "w": 337, "h": 143}
    provider = _Provider(broken, analysis)

    run(provider, "a dashboard", [], _prompts_dir())

    assert "fractions from 0.0 to 1.0" in provider.prompts[1]


def test_a_good_reading_is_not_asked_twice(analysis: dict[str, Any]) -> None:
    from superset.design_to_dashboard.stages.a_decompose import run

    provider = _Provider(analysis)

    _, cost = run(provider, "a dashboard", [], _prompts_dir())

    assert cost == 1.0
    assert len(provider.prompts) == 1


def test_the_returned_reading_carries_region_ids(analysis: dict[str, Any]) -> None:
    from superset.design_to_dashboard.stages.a_decompose import run

    result, _ = run(_Provider(analysis), "a dashboard", [], _prompts_dir())

    assert result["regions"][0]["region_id"] == "r01_coverage"


@pytest.mark.parametrize("status", ["unreadable", "separate_designs"])
def test_a_refusal_is_not_repaired(status: str) -> None:
    """Asking again would spend a second full-image call pressing the model to
    invent regions for a design it has just said it cannot read."""
    from superset.design_to_dashboard.stages.a_decompose import run

    refusal = {"status": status, "regions": [], "notes": "why"}
    provider = _Provider(refusal)

    result, cost = run(provider, "a dashboard", [], _prompts_dir())

    assert result["status"] == status
    assert cost == 1.0
    assert len(provider.prompts) == 1


def test_a_reading_that_stays_broken_is_returned_for_the_caller_to_reject(
    analysis: dict[str, Any],
) -> None:
    from superset.design_to_dashboard.stages.a_decompose import run

    broken = copy.deepcopy(analysis)
    broken["regions"][1]["role"] = "container"
    provider = _Provider(broken, copy.deepcopy(broken))

    result, _ = run(provider, "a dashboard", [], _prompts_dir())

    assert validate(result) != [], "the caller still fails the run"
