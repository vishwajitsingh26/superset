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
"""Structural validation of stage A's reading of a design."""

from __future__ import annotations

import copy
import pathlib
from typing import Any

import pytest

from superset.design_to_dashboard.llm.base import LLMResponse
from superset.design_to_dashboard.stages.a_decompose import validate
from superset.utils import json


def _region(region_id: str, **overrides: Any) -> dict[str, Any]:
    region = {
        "region_id": region_id,
        "bbox": {"x": 0, "y": 0, "w": 100, "h": 50},
        "role": "chart",
        "composition": "atomic",
        "title": "A chart",
    }
    region.update(overrides)
    return region


@pytest.fixture
def analysis() -> dict[str, Any]:
    """A minimal reading that passes every check."""
    return {
        "status": "ok",
        "regions": [_region("r01_header", role="header"), _region("r02_spend")],
        "global": {
            "canvas": {"w": 1440, "h": 900},
            "reading_order": ["r01_header", "r02_spend"],
        },
        "conflicts": [],
        "notes": "",
    }


def test_valid_analysis_has_no_problems(analysis: dict[str, Any]) -> None:
    assert validate(analysis) == []


def test_status_must_be_ok(analysis: dict[str, Any]) -> None:
    analysis["status"] = "partial"
    assert "invalid status: 'partial'" in validate(analysis)


def test_no_regions_is_fatal(analysis: dict[str, Any]) -> None:
    analysis["regions"] = []
    assert validate(analysis) == ["no regions were read from the design"]


@pytest.mark.parametrize(
    "region_id",
    ["r1_spend", "spend", "R01_Spend", "r01spend", "r01_Spend", ""],
)
def test_malformed_region_id_is_rejected(
    analysis: dict[str, Any], region_id: str
) -> None:
    analysis["regions"][1]["region_id"] = region_id
    analysis["global"]["reading_order"] = ["r01_header", region_id]
    assert any("expected the form" in p for p in validate(analysis))


def test_container_child_id_is_accepted(analysis: dict[str, Any]) -> None:
    """Stage B mints `r07_card:1` for a container; the grammar must allow it."""
    analysis["regions"][1]["region_id"] = "r02_spend:1"
    analysis["global"]["reading_order"] = ["r01_header", "r02_spend:1"]
    assert validate(analysis) == []


def test_duplicate_region_id_is_rejected(analysis: dict[str, Any]) -> None:
    analysis["regions"].append(_region("r02_spend"))
    assert "duplicate region_id: r02_spend" in validate(analysis)


def test_unknown_role_is_rejected(analysis: dict[str, Any]) -> None:
    analysis["regions"][1]["role"] = "sparkline"
    assert any("role 'sparkline' is not one of" in p for p in validate(analysis))


def test_unknown_composition_is_rejected(analysis: dict[str, Any]) -> None:
    analysis["regions"][1]["composition"] = "grid"
    assert any("composition 'grid' is not one of" in p for p in validate(analysis))


def test_missing_canvas_is_rejected(analysis: dict[str, Any]) -> None:
    del analysis["global"]["canvas"]
    assert "global.canvas is missing" in validate(analysis)


@pytest.mark.parametrize("canvas", [{"w": 0, "h": 900}, {"w": 1440, "h": -1}, {}])
def test_canvas_must_have_positive_dimensions(
    analysis: dict[str, Any], canvas: dict[str, Any]
) -> None:
    analysis["global"]["canvas"] = canvas
    assert any("expected positive w and h" in p for p in validate(analysis))


def test_bbox_outside_the_canvas_is_rejected(analysis: dict[str, Any]) -> None:
    analysis["regions"][1]["bbox"] = {"x": 1400, "y": 0, "w": 200, "h": 50}
    assert any("falls outside" in p for p in validate(analysis))


def test_bbox_touching_the_canvas_edge_is_allowed(analysis: dict[str, Any]) -> None:
    analysis["regions"][1]["bbox"] = {"x": 0, "y": 0, "w": 1440, "h": 900}
    assert validate(analysis) == []


def test_zero_area_bbox_is_rejected(analysis: dict[str, Any]) -> None:
    analysis["regions"][1]["bbox"] = {"x": 10, "y": 10, "w": 0, "h": 50}
    assert any("has no area" in p for p in validate(analysis))


def test_malformed_bbox_is_rejected(analysis: dict[str, Any]) -> None:
    analysis["regions"][1]["bbox"] = {"x": 10, "y": 10, "w": "wide"}
    assert any("is not {x, y, w, h}" in p for p in validate(analysis))


def test_missing_reading_order_is_rejected(analysis: dict[str, Any]) -> None:
    del analysis["global"]["reading_order"]
    assert "global.reading_order is missing" in validate(analysis)


def test_reading_order_must_be_a_permutation(analysis: dict[str, Any]) -> None:
    analysis["global"]["reading_order"] = ["r01_header", "r09_ghost"]
    problems = validate(analysis)
    assert "reading_order omits r02_spend" in problems
    assert "reading_order names an unknown region: r09_ghost" in problems


def test_canvas_matching_the_image_passes(
    analysis: dict[str, Any], tmp_path: pathlib.Path
) -> None:
    image = _write_image(tmp_path, 1440, 900)
    assert validate(analysis, [image]) == []


def test_canvas_disagreeing_with_the_image_is_rejected(
    analysis: dict[str, Any], tmp_path: pathlib.Path
) -> None:
    """The failure that made the boxes unusable: a 1.41x resize reported one
    way and the boxes scaled the other."""
    image = _write_image(tmp_path, 1358, 2819)
    analysis["global"]["canvas"] = {"w": 963, "h": 1999}
    analysis["regions"] = [_region("r01_header", role="header")]
    analysis["global"]["reading_order"] = ["r01_header"]
    problems = validate(analysis, [image])
    assert any("but the design image is 1358px" in p for p in problems)


def test_unreadable_image_skips_the_canvas_check(
    analysis: dict[str, Any], tmp_path: pathlib.Path
) -> None:
    """A missing file must not fail a run on a check it cannot perform."""
    assert validate(analysis, [str(tmp_path / "gone.png")]) == []


def test_validate_does_not_mutate_its_input(analysis: dict[str, Any]) -> None:
    before = copy.deepcopy(analysis)
    validate(analysis)
    assert analysis == before


def _write_image(tmp_path: pathlib.Path, width: int, height: int) -> str:
    pillow = pytest.importorskip("PIL.Image")
    path = tmp_path / f"design_{width}x{height}.png"
    pillow.new("RGB", (width, height)).save(path)
    return str(path)


# --- a container emitted beside the things it contains -----------------------


def _panel(analysis: dict[str, Any], role: str = "kpi") -> dict[str, Any]:
    """A bordered panel, and four cards drawn inside it.

    The reading the old prompt asked for in two different bullets: four KPI
    tiles are four regions, *and* the panel around them is a container.
    """
    analysis["regions"] = [
        _region(
            "r29_coverage",
            composition="container",
            role="chart",
            bbox={"x": 0, "y": 0, "w": 800, "h": 200},
        ),
        *[
            _region(
                f"r3{index}_card",
                role=role,
                bbox={"x": 10 + index * 190, "y": 20, "w": 180, "h": 160},
            )
            for index in range(4)
        ],
    ]
    analysis["global"]["reading_order"] = [r["region_id"] for r in analysis["regions"]]
    return analysis


def test_a_container_drawn_around_other_regions_is_reported(
    analysis: dict[str, Any],
) -> None:
    problems = validate(_panel(analysis))
    assert any(
        "is a container and 4 other regions are drawn inside it" in p for p in problems
    )


def test_the_same_regions_without_a_container_are_fine(
    analysis: dict[str, Any],
) -> None:
    """Four cards in a row is the correct reading -- the grid lays them out."""
    panel = _panel(analysis)
    panel["regions"][0]["composition"] = "atomic"
    assert validate(panel) == []


def test_a_control_inside_a_container_is_not_its_content(
    analysis: dict[str, Any],
) -> None:
    """A toggle in a panel header is its own region by design -- it is what
    makes the frame a container rather than a border."""
    panel = _panel(analysis, role="filter")
    assert validate(panel) == []


def test_a_container_beside_its_neighbours_is_fine(analysis: dict[str, Any]) -> None:
    """Adjacency is not containment: a card next to a tabbed panel is its own
    region and must not be read as living inside it."""
    analysis["regions"] = [
        _region(
            "r29_tabs",
            composition="container",
            bbox={"x": 0, "y": 0, "w": 400, "h": 200},
        ),
        _region("r30_next", bbox={"x": 410, "y": 0, "w": 380, "h": 200}),
    ]
    analysis["global"]["reading_order"] = ["r29_tabs", "r30_next"]
    assert validate(analysis) == []


def test_a_card_merely_overlapping_a_container_is_not_reported(
    analysis: dict[str, Any],
) -> None:
    """Boxes are read by eye and bleed into each other; only a region mostly
    inside the frame is the frame's content."""
    analysis["regions"] = [
        _region(
            "r29_panel",
            composition="container",
            bbox={"x": 0, "y": 0, "w": 400, "h": 200},
        ),
        _region("r30_card", bbox={"x": 350, "y": 0, "w": 380, "h": 200}),
    ]
    analysis["global"]["reading_order"] = ["r29_panel", "r30_card"]
    assert validate(analysis) == []


# --- one repair pass ---------------------------------------------------------


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
    """The failure that cost a whole run: `role: 'control'`, which is a
    composition and not a role, in four regions."""
    from superset.design_to_dashboard.stages.a_decompose import run

    broken = copy.deepcopy(analysis)
    broken["regions"][1]["role"] = "control"
    provider = _Provider(broken, analysis)

    result, cost = run(provider, "a dashboard", [], _prompts_dir())

    assert validate(result) == [], "the second reading is the one returned"
    assert cost == 2.0, "both calls are paid for"
    assert len(provider.prompts) == 2


def test_the_repair_names_what_was_wrong(analysis: dict[str, Any]) -> None:
    """A blind re-ask was refused for good reason; this one is not blind."""
    from superset.design_to_dashboard.stages.a_decompose import run

    broken = copy.deepcopy(analysis)
    broken["regions"][1]["role"] = "control"
    provider = _Provider(broken, analysis)
    run(provider, "a dashboard", [], _prompts_dir())

    assert "role 'control' is not one of" in provider.prompts[1]


def test_a_good_reading_is_not_asked_twice(analysis: dict[str, Any]) -> None:
    """Stage A is the longest call in the pipeline -- never spend it twice
    when the first answer was fine."""
    from superset.design_to_dashboard.stages.a_decompose import run

    provider = _Provider(analysis)
    _result, cost = run(provider, "a dashboard", [], _prompts_dir())
    assert len(provider.prompts) == 1
    assert cost == 1.0


def test_a_reading_that_stays_broken_is_returned_for_the_caller_to_reject(
    analysis: dict[str, Any],
) -> None:
    """`run` does not raise: the runner validates and reports the problems."""
    from superset.design_to_dashboard.stages.a_decompose import run

    broken = copy.deepcopy(analysis)
    broken["regions"][1]["role"] = "control"
    provider = _Provider(broken, copy.deepcopy(broken))

    result, _cost = run(provider, "a dashboard", [], _prompts_dir())

    assert len(provider.prompts) == 2, "it stops after the repair pass"
    assert any("role 'control' is not one of" in p for p in validate(result))
