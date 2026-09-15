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
"""A dropped section hosts nothing, and nothing hosts a dropped section.

The runner re-marked failed containers `drop` and left their `children` in
place, so stage E deleted eight of eleven built charts from the grid as "drawn
by its parent" -- for a parent that was never built.
"""

from __future__ import annotations

from typing import Any

from superset.design_to_dashboard.runner import (
    _drop_decision,
    drop_unconfigured_parents,
    release_dropped_children,
)
from superset.design_to_dashboard.stages.d_configure import ChartSpecResult
from superset.design_to_dashboard.stages.e_layout import (
    drop_composed_children,
    hosted_refs,
)


def _decisions() -> list[dict[str, Any]]:
    return [
        {"ref": "c1", "region_id": "r02_trend", "decision": "configure"},
        {"ref": "c2", "region_id": "r03_bars", "decision": "configure"},
        {
            "ref": "c9",
            "region_id": "r01_panel",
            "decision": "configure",
            "children": ["c1", "c2"],
        },
    ]


def test_dropping_a_parent_clears_its_children() -> None:
    decisions = _decisions()
    _drop_decision(decisions[2], decisions, "the plugin did not compile")
    assert decisions[2]["decision"] == "drop"
    assert "children" not in decisions[2]
    assert decisions[2]["fidelity_loss"].startswith("the plugin did not compile")
    assert "c1, c2" in decisions[2]["fidelity_loss"]


def test_dropping_a_parent_leaves_its_children_buildable() -> None:
    decisions = _decisions()
    _drop_decision(decisions[2], decisions, "gone")
    assert [d["decision"] for d in decisions[:2]] == ["configure", "configure"]


def test_dropping_a_child_detaches_it_from_a_live_parent() -> None:
    """A parent still naming it is asked to render a chart with no id."""
    decisions = _decisions()
    _drop_decision(decisions[0], decisions, "gone")
    assert decisions[2]["children"] == ["c2"]
    assert "c1" in decisions[2]["fidelity_loss"]


def test_a_drop_stage_c_wrote_is_released_by_the_sweep() -> None:
    decisions = _decisions()
    decisions[2]["decision"] = "drop"
    notes = release_dropped_children(decisions)
    assert "children" not in decisions[2]
    assert len(notes) == 1
    assert "r01_panel" in notes[0]


def test_the_release_is_idempotent() -> None:
    decisions = _decisions()
    _drop_decision(decisions[2], decisions, "gone")
    loss = decisions[2]["fidelity_loss"]
    assert release_dropped_children(decisions) == []
    assert decisions[2]["fidelity_loss"] == loss


def test_a_plan_without_drops_is_left_alone() -> None:
    decisions = _decisions()
    assert release_dropped_children(decisions) == []
    assert decisions == _decisions()


def test_the_layout_keeps_the_charts_of_a_dropped_parent() -> None:
    """End to end over the two halves: the runner's drop, then E's repair."""
    decisions = _decisions()
    _drop_decision(decisions[2], decisions, "gone")
    position: dict[str, Any] = {
        "ROOT_ID": {"type": "ROOT", "id": "ROOT_ID", "children": ["GRID_ID"]},
        "GRID_ID": {"type": "GRID", "id": "GRID_ID", "children": ["ROW-1"]},
        "ROW-1": {"type": "ROW", "id": "ROW-1", "children": ["CHART-1", "CHART-2"]},
        "CHART-1": {
            "type": "CHART",
            "id": "CHART-1",
            "meta": {"chartId": "__REF__:c1"},
        },
        "CHART-2": {
            "type": "CHART",
            "id": "CHART-2",
            "meta": {"chartId": "__REF__:c2"},
        },
    }
    assert drop_composed_children(position, {"decisions": decisions}) == []
    assert position["ROW-1"]["children"] == ["CHART-1", "CHART-2"]


def test_a_parent_dropped_before_its_child_stops_promising_it_on_the_grid() -> None:
    """Drops run in viz-type order, so a container often goes before the chart
    it released -- whose note then named a chart the dashboard does not have."""
    decisions = _decisions()
    _drop_decision(decisions[2], decisions, "the container did not compile")
    assert "c1, c2" in decisions[2]["fidelity_loss"]
    _drop_decision(decisions[0], decisions, "the tile did not compile")
    loss = decisions[2]["fidelity_loss"]
    assert loss.startswith("the container did not compile")
    assert "(c2)" in loss
    assert "c1" not in loss
    assert decisions[2]["released_children"] == ["c2"]


def test_a_note_naming_only_dropped_charts_is_removed() -> None:
    decisions = _decisions()
    _drop_decision(decisions[2], decisions, "gone")
    _drop_decision(decisions[0], decisions, "gone")
    _drop_decision(decisions[1], decisions, "gone")
    assert decisions[2]["fidelity_loss"] == "gone"
    assert "released_children" not in decisions[2]
    assert release_dropped_children(decisions) == []


def test_a_container_that_loses_every_child_keeps_what_it_draws_itself() -> None:
    """A generated container draws its own title and value; dropping it with
    its cards took a header the dashboard could still show."""
    decisions = _decisions()
    _drop_decision(decisions[0], decisions, "gone")
    _drop_decision(decisions[1], decisions, "gone")
    assert decisions[2]["decision"] == "configure"
    assert "children" not in decisions[2]
    loss = decisions[2]["fidelity_loss"]
    assert "c1" in loss
    assert "c2" in loss
    assert "every chart it held is missing" in loss


def test_emptying_a_container_leaves_the_one_above_it_alone() -> None:
    decisions = [
        *_decisions(),
        {
            "ref": "c10",
            "region_id": "r00_page",
            "decision": "configure",
            "children": ["c9"],
        },
    ]
    _drop_decision(decisions[0], decisions, "gone")
    _drop_decision(decisions[1], decisions, "gone")
    assert decisions[3]["decision"] == "configure"
    assert decisions[3]["children"] == ["c9"]


# --- a parent stage D could not configure ------------------------------------


def _charts(**errors: str) -> list[ChartSpecResult]:
    return [
        ChartSpecResult(
            ref=ref,
            region_id=region,
            viz_type="custom_tile",
            spec=None if ref in errors else {"ok": True},
            error=errors.get(ref),
        )
        for ref, region in (
            ("c1", "r02_trend"),
            ("c2", "r03_bars"),
            ("c9", "r01_panel"),
        )
    ]


def _position() -> dict[str, Any]:
    return {
        "ROOT_ID": {"type": "ROOT", "id": "ROOT_ID", "children": ["GRID_ID"]},
        "GRID_ID": {"type": "GRID", "id": "GRID_ID", "children": ["ROW-1"]},
        "ROW-1": {"type": "ROW", "id": "ROW-1", "children": ["CHART-1", "CHART-2"]},
        "CHART-1": {
            "type": "CHART",
            "id": "CHART-1",
            "meta": {"chartId": "__REF__:c1"},
        },
        "CHART-2": {
            "type": "CHART",
            "id": "CHART-2",
            "meta": {"chartId": "__REF__:c2"},
        },
    }


def test_a_parent_stage_d_failed_on_releases_its_children_to_the_grid() -> None:
    """Skipped by the applier but still listing children, it had stage E delete
    their grid nodes: created charts, placed nowhere."""
    decisions = _decisions()
    charts = _charts(c9="LLMError: stream reset")
    notes = drop_unconfigured_parents(charts, decisions)
    assert notes
    assert decisions[2]["decision"] == "drop"
    assert "stage D could not configure it" in decisions[2]["fidelity_loss"]
    assert "LLMError: stream reset" in decisions[2]["fidelity_loss"]
    assert hosted_refs({"decisions": decisions}) == set()
    position = _position()
    assert drop_composed_children(position, {"decisions": decisions}) == []
    assert position["ROW-1"]["children"] == ["CHART-1", "CHART-2"]


def test_a_released_child_that_would_throw_is_left_out() -> None:
    decisions = _decisions()
    charts = _charts(c9="left out: header must hold a metric")
    charts[0].leave_out = "left out: headline must hold a metric"
    drop_unconfigured_parents(charts, decisions)
    assert charts[0].error == "left out: headline must hold a metric"
    assert charts[1].error is None


def test_a_hosted_child_that_would_throw_stays_while_its_parent_lives() -> None:
    """Its parent's params name it, and an unresolved reference fails the apply."""
    decisions = _decisions()
    charts = _charts()
    charts[0].leave_out = "left out: headline must hold a metric"
    assert drop_unconfigured_parents(charts, decisions) == []
    assert charts[0].error is None
    assert decisions[2]["children"] == ["c1", "c2"]


def test_a_chart_stage_d_failed_on_with_no_children_stays_in_the_plan() -> None:
    decisions = _decisions()
    assert drop_unconfigured_parents(_charts(c1="bad json"), decisions) == []
    assert [d["decision"] for d in decisions] == ["configure"] * 3


def test_dropping_a_section_twice_keeps_the_first_reason() -> None:
    decisions = _decisions()
    _drop_decision(decisions[0], decisions, "its plugin could not be generated")
    _drop_decision(decisions[0], decisions, "its plugin did not compile")
    assert decisions[0]["fidelity_loss"] == "its plugin could not be generated"
