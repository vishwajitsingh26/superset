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

from superset.design_to_dashboard.stages.a_decompose import validate


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


def test_composite_child_id_is_accepted(analysis: dict[str, Any]) -> None:
    """Stage B mints `r07_card:1`; the shared grammar must allow it."""
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
