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

from superset.design_to_dashboard.stages.c_resolve import (
    _wrappers_without_children,
)
from superset.design_to_dashboard.stages.e_layout import (
    _reject_overlong_grid_text,
    _row_underflow_problems,
    action_link_refs,
    ACTION_LINK_UNITS,
    add_action_link_allowance,
    build_user_prompt,
    content_box,
    drop_composed_children,
    enforce_min_width,
    GRID_MIN_FILTER_COLUMNS,
    hosted_refs,
    min_width_refs,
    normalise,
    ref_of,
    REF_PREFIX,
    validate,
)
from superset.utils import json


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


DESIGN = {
    "regions": [
        {"region_id": "r07_card", "role": "wrapper", "children": [8]},
        {"region_id": "r08_inner", "role": "chart", "children": []},
    ]
}


def test_a_wrapper_resolved_without_children_is_reported() -> None:
    """`children` is the only thing telling the layout a piece is drawn inside
    the card. Without it the piece gets its own node and appears twice, and no
    check anywhere else says so."""
    decisions = [
        {"ref": "c2", "region_id": "r07_card", "decision": "new_plugin"},
        {"ref": "c1", "region_id": "r08_inner", "decision": "configure"},
    ]
    assert any(
        "holding 1 other section" in p
        for p in _wrappers_without_children(decisions, DESIGN)
    )


def test_naming_the_children_clears_it() -> None:
    decisions: list[dict[str, Any]] = [
        {"ref": "c1", "region_id": "r08_inner", "decision": "configure"},
        {
            "ref": "c2",
            "region_id": "r07_card",
            "decision": "new_plugin",
            "children": ["c1"],
        },
    ]
    assert _wrappers_without_children(decisions, DESIGN) == []


def test_a_dropped_wrapper_needs_no_children() -> None:
    """A frame the plan discards holds nothing by definition."""
    decisions: list[dict[str, Any]] = [
        {"ref": "c1", "region_id": "r08_inner", "decision": "configure"},
        {"ref": "c2", "region_id": "r07_card", "decision": "drop"},
    ]
    assert _wrappers_without_children(decisions, DESIGN) == []


def test_children_on_a_region_stage_a_read_as_a_leaf_is_reported() -> None:
    """The other direction: a card about one subject is one chart, however
    much it draws."""
    decisions: list[dict[str, Any]] = [
        {
            "ref": "c1",
            "region_id": "r08_inner",
            "decision": "new_plugin",
            "children": ["c2"],
        },
        {"ref": "c2", "region_id": "r07_card", "decision": "configure"},
    ]
    assert any(
        "stage A read no sections inside it" in p
        for p in _wrappers_without_children(decisions, DESIGN)
    )


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


# --- a parent the run dropped hosts nothing ----------------------------------


@pytest.fixture
def dropped_plan() -> dict[str, Any]:
    """A panel (`c9`) the run gave up on, still listing the charts it held."""
    return {
        "decisions": [
            {"ref": "c1", "region_id": "r02_trend", "decision": "configure"},
            {"ref": "c2", "region_id": "r03_bars", "decision": "configure"},
            {
                "ref": "c9",
                "region_id": "r01_panel",
                "decision": "drop",
                "children": ["c1", "c2"],
            },
        ]
    }


def test_hosted_refs_ignores_a_dropped_parent(dropped_plan: dict[str, Any]) -> None:
    assert hosted_refs(dropped_plan) == set()


def test_hosted_refs_reads_a_live_parent(plan: dict[str, Any]) -> None:
    assert hosted_refs(plan) == {"c1"}


def test_children_of_a_dropped_parent_keep_their_grid_nodes(
    dropped_plan: dict[str, Any],
) -> None:
    """The bug: every chart a dropped panel had listed was deleted as "drawn by
    its parent", its row emptied and removed, and Superset appended the charts
    at the foot of the page."""
    position = _grid("c1", "c2")
    before = copy.deepcopy(position)
    assert drop_composed_children(position, dropped_plan) == []
    assert position == before
    assert position["ROW-1"]["children"] == ["CHART-C1", "CHART-C2"]


def test_validate_expects_the_children_of_a_dropped_parent(
    dropped_plan: dict[str, Any],
) -> None:
    placed = validate({"position_json": _grid("c1", "c2")}, dropped_plan)
    assert not any("unknown ref" in p for p in placed)
    missing = validate({"position_json": _grid("c1")}, dropped_plan)
    assert any("'c2' was never placed" in p for p in missing)


def test_a_dropped_parent_does_not_excuse_an_unplaced_child(
    dropped_plan: dict[str, Any],
) -> None:
    layout = {
        "position_json": _grid("c1", "c2"),
        "unplaced": [{"ref": "c1", "reason": "drawn inside c9"}],
    }
    assert any("unplaced" in p for p in validate(layout, dropped_plan))


# --- stage E is told which refs a parent hosts --------------------------------


def _placements(plan: dict[str, Any]) -> dict[str, dict[str, Any]]:
    prompt = build_user_prompt({"regions": []}, plan)
    payload = json.loads(prompt.split("```json\n", 1)[1].rsplit("\n```", 1)[0])
    return {p["ref"]: p for p in payload["placements"]}


def test_a_live_parent_names_its_children_in_its_placement(
    plan: dict[str, Any],
) -> None:
    """The prompt forbids grid nodes for a parent's children; without the list
    in the placement there was no way to tell which refs those were."""
    placements = _placements(plan)
    assert placements["c2"]["children"] == ["c1"]
    assert "children" not in placements["c1"]


def test_a_dropped_parents_children_are_plain_placements(
    dropped_plan: dict[str, Any],
) -> None:
    placements = _placements(dropped_plan)
    assert set(placements) == {"c1", "c2"}
    assert not any("children" in p for p in placements.values())


def test_a_placement_names_only_children_still_on_the_grid() -> None:
    plan = {
        "decisions": [
            {"ref": "c1", "region_id": "r02", "decision": "drop"},
            {"ref": "c2", "region_id": "r03", "decision": "configure"},
            {
                "ref": "c9",
                "region_id": "r01",
                "decision": "configure",
                "children": ["c1", "c2"],
            },
        ]
    }
    assert _placements(plan)["c9"]["children"] == ["c2"]


# --- a heading's subtitle survives being placed on the grid ------------------


def _heading_plan(text: str) -> dict[str, Any]:
    return {
        "decisions": [
            {"ref": None, "region_id": "r01", "decision": "grid_text", "text": text},
        ]
    }


def test_a_header_node_with_a_subtitle_is_truncated_to_its_title() -> None:
    """Stage C's own validator is supposed to reject this plan before it ever
    gets here -- a subtitle belongs to `configure: custom_text`, not
    `grid_text`. This is the fallback for one that got through anyway: no
    second node type invented to hold the rest, just the title kept."""
    position: dict[str, dict[str, Any]] = {
        "ROOT_ID": {"type": "ROOT", "id": "ROOT_ID", "children": ["GRID_ID"]},
        "GRID_ID": {"type": "GRID", "id": "GRID_ID", "children": ["HEADER-1"]},
        "HEADER-1": {
            "type": "HEADER",
            "id": "HEADER-1",
            "children": [],
            "meta": {"text": "Cloud Cost Analytics", "width": 9, "height": 13},
        },
    }
    plan = _heading_plan("**Cloud Cost Analytics**\n\nTrack your spend.")
    notes = _reject_overlong_grid_text(position, plan)
    assert notes
    assert position["HEADER-1"]["type"] == "HEADER"
    assert position["HEADER-1"]["meta"]["text"] == "Cloud Cost Analytics"


def test_a_single_line_heading_is_left_a_header() -> None:
    position = {
        "HEADER-1": {
            "type": "HEADER",
            "id": "HEADER-1",
            "children": [],
            "meta": {"text": "Cloud Cost Analytics"},
        },
    }
    plan = _heading_plan("Cloud Cost Analytics")
    assert _reject_overlong_grid_text(position, plan) == []
    assert position["HEADER-1"]["type"] == "HEADER"


def test_no_matching_node_leaves_the_grid_alone() -> None:
    position: dict[str, dict[str, Any]] = {
        "HEADER-1": {
            "type": "HEADER",
            "id": "HEADER-1",
            "children": [],
            "meta": {"text": "Something else entirely"},
        },
    }
    plan = _heading_plan("**Title**\n\nSubtitle.")
    assert _reject_overlong_grid_text(position, plan) == []
    assert position["HEADER-1"]["meta"]["text"] == "Something else entirely"


def test_validate_catches_a_grid_text_decision_with_more_than_one_line() -> None:
    layout = {
        "position_json": {
            "ROOT_ID": {"type": "ROOT", "id": "ROOT_ID", "children": []},
            "HEADER-1": {
                "type": "HEADER",
                "id": "HEADER-1",
                "children": [],
                "meta": {"text": "Title"},
            },
        }
    }
    plan = _heading_plan("**Title**\n\nSubtitle.")
    problems = validate(layout, plan)
    assert any("more than one line" in p for p in problems)


def test_validate_rejects_a_markdown_node_outright() -> None:
    """`MARKDOWN` always renders inside a scrolling container this pipeline
    does not want, so it is not a legal node type at all -- not even for a
    plan that carries the full text on one."""
    layout = {
        "position_json": {
            "ROOT_ID": {"type": "ROOT", "id": "ROOT_ID", "children": []},
            "MARKDOWN-1": {
                "type": "MARKDOWN",
                "id": "MARKDOWN-1",
                "children": [],
                "meta": {"text": "**Title**\n\nSubtitle."},
            },
        }
    }
    plan = _heading_plan("**Title**\n\nSubtitle.")
    problems = validate(layout, plan)
    assert any("unknown node type 'MARKDOWN'" in p for p in problems)


def test_validate_passes_a_single_line_heading() -> None:
    layout = {
        "position_json": {
            "ROOT_ID": {"type": "ROOT", "id": "ROOT_ID", "children": []},
            "HEADER-1": {
                "type": "HEADER",
                "id": "HEADER-1",
                "children": [],
                "meta": {"text": "Title"},
            },
        }
    }
    plan = _heading_plan("Title")
    assert validate(layout, plan) == []


# --- a `filter` card has a text floor its own bbox fraction cannot know ------


def _filter_design(role: str = "filter") -> dict[str, Any]:
    return {"regions": [{"region_id": "r05_filter", "role": role}]}


def _filter_plan() -> dict[str, Any]:
    return {
        "decisions": [
            {"ref": "c1", "region_id": "r05_filter", "decision": "configure"},
        ]
    }


def test_min_width_refs_floors_a_filter_role() -> None:
    assert min_width_refs(_filter_design(), _filter_plan()) == {
        "c1": GRID_MIN_FILTER_COLUMNS
    }


def test_min_width_refs_leaves_other_roles_alone() -> None:
    """The bug this deliberately does not fix: a chart's content is stage D's,
    not a fixed string this stage can predict a width for."""
    assert min_width_refs(_filter_design(role="chart"), _filter_plan()) == {}


def test_enforce_min_width_grows_a_narrow_filter() -> None:
    """The bug: a date-range pill drawn at 0.145 of the page rounds to 2
    columns, too narrow to hold "Apr 1, 2025 - Apr 30, 2025" without losing
    the year."""
    position = _grid("c1")
    position["CHART-C1"]["meta"]["width"] = 2
    notes = enforce_min_width(position, {"c1": GRID_MIN_FILTER_COLUMNS})
    assert position["CHART-C1"]["meta"]["width"] == GRID_MIN_FILTER_COLUMNS
    assert any("needs room for its own fixed text" in note for note in notes)


def test_enforce_min_width_leaves_a_wide_enough_filter_alone() -> None:
    position = _grid("c1")
    position["CHART-C1"]["meta"]["width"] = GRID_MIN_FILTER_COLUMNS
    before = copy.deepcopy(position)
    assert enforce_min_width(position, {"c1": GRID_MIN_FILTER_COLUMNS}) == []
    assert position == before


def test_enforce_min_width_shrinks_the_widest_sibling_to_stay_at_12() -> None:
    """Growing the floored card can push its row over 12; the row's widest
    other card gives back exactly what the floor took, the way the prompt's
    own overflow rule already does by hand."""
    position = _grid("c1", "c2")
    position["CHART-C1"]["meta"]["width"] = 2
    position["CHART-C2"]["meta"]["width"] = 11
    enforce_min_width(position, {"c1": GRID_MIN_FILTER_COLUMNS})
    assert position["CHART-C1"]["meta"]["width"] == GRID_MIN_FILTER_COLUMNS
    total = (
        position["CHART-C1"]["meta"]["width"] + position["CHART-C2"]["meta"]["width"]
    )
    assert total == 12


# --- an action drawn in the body still costs a chrome row's worth of height --


def _link_design() -> dict[str, Any]:
    return {
        "regions": [
            {
                "region_id": "r18_recent_activity",
                "role": "chart",
                "chrome": {"actions": [{"kind": "link"}]},
            }
        ]
    }


def _link_plan() -> dict[str, Any]:
    return {
        "decisions": [
            {"ref": "c1", "region_id": "r18_recent_activity", "decision": "configure"},
        ]
    }


def test_action_link_refs_finds_a_link_action() -> None:
    assert action_link_refs(_link_design(), _link_plan()) == {"c1"}


def test_action_link_refs_ignores_other_action_kinds() -> None:
    """Only a `link` has nowhere else to go but the body; a `refresh` or
    `download` icon fits inside a plugin's own header row."""
    design = {
        "regions": [
            {
                "region_id": "r18_recent_activity",
                "role": "chart",
                "chrome": {"actions": [{"kind": "refresh"}]},
            }
        ]
    }
    assert action_link_refs(design, _link_plan()) == set()


def test_action_link_refs_ignores_a_region_with_no_actions() -> None:
    assert action_link_refs(_filter_design(role="chart"), _filter_plan()) == set()


def test_add_action_link_allowance_grows_a_clipped_body() -> None:
    """The bug: hiding Superset's menu because the card draws its own "View
    all ->" link forces that link into the body, and nothing gave height back
    for it -- the last real row of content got clipped."""
    position = _grid("c1")
    height = position["CHART-C1"]["meta"]["height"]
    notes = add_action_link_allowance(position, {"c1"})
    assert position["CHART-C1"]["meta"]["height"] == height + ACTION_LINK_UNITS
    assert any("no header left to hold it" in note for note in notes)


def test_add_action_link_allowance_ignores_a_ref_not_in_the_set() -> None:
    position = _grid("c1")
    before = copy.deepcopy(position)
    assert add_action_link_allowance(position, set()) == []
    assert position == before


def test_add_action_link_allowance_skips_a_mixed_row() -> None:
    """Superset lays a row out as one band; growing one card without its
    sibling agreeing would trade one clipped card for two disagreeing ones."""
    position = _grid("c1", "c2")
    before = copy.deepcopy(position)
    assert add_action_link_allowance(position, {"c1"}) == []
    assert position == before


# --- hosted refs stay hosted even for a parent the run gave up on -----------
# Regression guard for the D2D fidelity review (6f756597): a dropped
# container's `children` were once trusted regardless, stripping 8 of 11
# built charts from the grid as "drawn by a parent" that no longer existed.
# `dropped_plan`, `hosted_refs`, `drop_composed_children` and `validate` above
# already cover this; this is the same shape at the size the real run hit it,
# named explicitly so a regression here is never mistaken for a new bug.


def test_hosted_refs_survives_a_dropped_parent_with_many_children() -> None:
    plan = {
        "decisions": [
            {
                "ref": "c9",
                "region_id": "r01_panel",
                "decision": "drop",
                "children": [f"c{i}" for i in range(1, 9)],
            },
        ]
    }
    assert hosted_refs(plan) == set()


def test_eight_charts_survive_a_dropped_parent_on_the_grid() -> None:
    refs = [f"c{i}" for i in range(1, 9)]
    plan = {
        "decisions": [
            {"ref": ref, "region_id": f"r{i}", "decision": "configure"}
            for i, ref in enumerate(refs, start=1)
        ]
        + [
            {
                "ref": "c9",
                "region_id": "r01_panel",
                "decision": "drop",
                "children": refs,
            }
        ]
    }
    position = _grid(*refs)
    before = copy.deepcopy(position)
    assert drop_composed_children(position, plan) == []
    assert position == before
    assert set(position["ROW-1"]["children"]) == {
        f"CHART-{ref.upper()}" for ref in refs
    }


# --- a row left short of 12 with nothing on record saying why ---------------


def _row_plan() -> dict[str, Any]:
    return {
        "decisions": [
            {"ref": "c1", "region_id": "r1", "decision": "configure"},
        ]
    }


def test_validate_flags_an_unrecorded_small_underflow() -> None:
    """The bug: a row left at 5 of 12 columns, reasoned away as "the design's
    intent" with no record of it, drew an item left-aligned instead of
    anchored where the design placed it."""
    position = _grid("c1")
    position["CHART-C1"]["meta"]["width"] = 10
    layout = {"position_json": position}
    problems = validate(layout, _row_plan())
    assert any("short of 12" in p for p in problems)


def test_validate_accepts_a_recorded_underflow() -> None:
    position = _grid("c1")
    position["CHART-C1"]["meta"]["width"] = 10
    layout = {
        "position_json": position,
        "adjustments": [
            {
                "row_id": "ROW-1",
                "issue": "10 of 12, design leaves a deliberate gutter",
                "resolution": "left as drawn",
            }
        ],
    }
    problems = validate(layout, _row_plan())
    assert not any("short of 12" in p for p in problems)


def test_validate_ignores_a_full_row() -> None:
    position = _grid("c1")
    position["CHART-C1"]["meta"]["width"] = 12
    layout = {"position_json": position}
    problems = validate(layout, _row_plan())
    assert not any("short of 12" in p for p in problems)


def test_validate_ignores_a_gap_too_large_to_be_rounding() -> None:
    """Only the 1-2 column margin `E_layout.md`'s own rule names is checked --
    a bigger gap is a different problem, not this one."""
    position = _grid("c1")
    position["CHART-C1"]["meta"]["width"] = 5
    layout = {"position_json": position}
    problems = validate(layout, _row_plan())
    assert not any("short of 12" in p for p in problems)


def test_row_underflow_problems_matches_validates_own_wiring() -> None:
    """Called directly, not just through `validate`, so a future refactor of
    `validate`'s own plumbing cannot silently stop calling it."""
    position = _grid("c1")
    position["CHART-C1"]["meta"]["width"] = 11
    assert _row_underflow_problems(position, {}) != []
    assert (
        _row_underflow_problems(position, {"adjustments": [{"row_id": "ROW-1"}]}) == []
    )
