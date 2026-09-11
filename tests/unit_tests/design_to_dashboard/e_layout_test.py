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
"""The grid, and the piece a card draws rather than the grid.

`drop_composed_children` read a `meta.ref` that no node has ever carried, so it
removed nothing from the moment it was written. Nothing tested it, and a dead
repair looks exactly like a working one from the outside -- hence this file.
"""

from __future__ import annotations

import copy
from typing import Any

import pytest

from superset.design_to_dashboard.stages.c_resolve import _split_composites
from superset.design_to_dashboard.stages.e_layout import (
    content_box,
    drop_composed_children,
    normalise,
    ref_of,
    REF_PREFIX,
    validate,
)


def _chart(node_id: str, ref: str, **meta: Any) -> dict[str, Any]:
    payload = {"chartId": f"{REF_PREFIX}{ref}", "uuid": "u", "width": 6, "height": 50}
    payload.update(meta)
    return {"type": "CHART", "id": node_id, "children": [], "meta": payload}


def _grid(*refs: str) -> dict[str, Any]:
    ids = [f"CHART-{ref.upper()}" for ref in refs]
    return {
        "ROOT_ID": {"type": "ROOT", "id": "ROOT_ID", "children": ["GRID_ID"]},
        "GRID_ID": {"type": "GRID", "id": "GRID_ID", "children": ["ROW-1"]},
        "ROW-1": {"type": "ROW", "id": "ROW-1", "children": ids},
        **{
            node_id: _chart(node_id, ref)
            for node_id, ref in zip(ids, refs, strict=True)
        },
    }


@pytest.fixture
def plan() -> dict[str, Any]:
    """A card (`c2`) that draws one piece (`c1`) inside itself."""
    return {
        "decisions": [
            {"ref": "c1", "region_id": "r07_card:2", "decision": "configure"},
            {
                "ref": "c2",
                "region_id": "r07_card",
                "decision": "configure",
                "children": ["c1"],
            },
        ]
    }


# --- a ref is read from the one key that carries it --------------------------


def test_ref_of_reads_chart_id() -> None:
    assert ref_of(_chart("CHART-1", "c9")) == "c9"


def test_ref_of_ignores_a_ref_key_that_does_not_exist() -> None:
    """The bug: `meta.ref` is not part of the contract and never was."""
    assert ref_of({"meta": {"ref": "c9"}}) is None


def test_ref_of_ignores_a_real_chart_id() -> None:
    assert ref_of(_chart("CHART-1", "c9", chartId=42)) is None


# --- the repair actually repairs ---------------------------------------------


def test_a_composed_child_loses_its_grid_node(plan: dict[str, Any]) -> None:
    position = _grid("c1", "c2")
    notes = drop_composed_children(position, plan)
    assert "CHART-C1" not in position, "the child is drawn by its parent"
    assert "CHART-C2" in position, "the parent stays"
    assert any("drawn by its parent" in note for note in notes)


def test_the_row_stops_listing_a_removed_child(plan: dict[str, Any]) -> None:
    position = _grid("c1", "c2")
    drop_composed_children(position, plan)
    assert position["ROW-1"]["children"] == ["CHART-C2"]


def test_a_row_emptied_by_the_repair_is_removed(plan: dict[str, Any]) -> None:
    position = _grid("c1")
    drop_composed_children(position, plan)
    assert "ROW-1" not in position
    assert position["GRID_ID"]["children"] == []


def test_nothing_to_remove_reports_nothing(plan: dict[str, Any]) -> None:
    assert drop_composed_children(_grid("c2"), plan) == []


def test_a_plan_with_no_children_is_left_alone() -> None:
    position = _grid("c1", "c2")
    before = copy.deepcopy(position)
    assert drop_composed_children(position, {"decisions": []}) == []
    assert position == before


# --- stage C has to say which pieces a card draws ----------------------------


DESIGN = {"regions": [{"region_id": "r07_card", "composition": "composite"}]}


def test_a_composing_configure_without_children_is_reported() -> None:
    """`children` is the only thing that tells the layout a piece is drawn
    inside the card. Without it the piece gets its own node and appears twice,
    and no check anywhere says so."""
    decisions = [
        {"ref": "c2", "region_id": "r07_card", "decision": "configure"},
        {"ref": "c1", "region_id": "r07_card:2", "decision": "configure"},
    ]
    assert any("names no `children`" in p for p in _split_composites(decisions, DESIGN))


def test_naming_the_children_clears_it() -> None:
    decisions: list[dict[str, Any]] = [
        {
            "ref": "c2",
            "region_id": "r07_card",
            "decision": "configure",
            "children": ["c1"],
        },
        {"ref": "c1", "region_id": "r07_card:2", "decision": "configure"},
    ]
    assert _split_composites(decisions, DESIGN) == []


def test_a_composite_whose_pieces_have_no_decisions_is_fine() -> None:
    """The card draws them itself and no separate chart was planned."""
    decisions: list[dict[str, Any]] = [
        {"ref": "c2", "region_id": "r07_card", "decision": "configure"}
    ]
    assert _split_composites(decisions, DESIGN) == []


# --- unplaced distinguishes "nowhere" from "inside its parent" ---------------


def test_a_composed_child_may_be_reported_unplaced(plan: dict[str, Any]) -> None:
    layout = {
        "position_json": _grid("c2"),
        "unplaced": [{"ref": "c1", "reason": "drawn inside c2"}],
    }
    assert not any("unplaced" in p for p in validate(layout, plan))


def test_a_genuinely_homeless_ref_still_fails(plan: dict[str, Any]) -> None:
    layout = {
        "position_json": _grid("c2"),
        "unplaced": [{"ref": "c9", "reason": "no room"}],
    }
    assert any("unplaced" in p for p in validate(layout, plan))


def test_a_duplicated_child_is_still_caught(plan: dict[str, Any]) -> None:
    """The backstop, for a grid that reached validate without the repair."""
    layout = {"position_json": _grid("c1", "c2")}
    assert any("unknown ref" in p for p in validate(layout, plan))


# --- the arithmetic nobody should be asked to do by hand ----------------------


def test_siblings_in_a_row_share_the_tallest_height() -> None:
    """Three roundings of the same number came back 27, 28, 28."""
    position = _grid("c1", "c2")
    position["CHART-C1"]["meta"]["height"] = 27
    position["CHART-C2"]["meta"]["height"] = 28
    notes = normalise(position)
    assert position["CHART-C1"]["meta"]["height"] == 28
    assert any("heights" in note for note in notes)


def test_content_box_excludes_nothing_it_was_not_given() -> None:
    """The grid spans the regions that survive, not the canvas."""
    regions = [
        {"bbox": {"x": 200, "y": 100, "w": 400, "h": 50}},
        {"bbox": {"x": 200, "y": 200, "w": 600, "h": 50}},
    ]
    assert content_box(regions) == {"x": 200, "y": 100, "w": 600, "h": 150}


def test_content_box_of_nothing_is_none() -> None:
    assert content_box([]) is None
