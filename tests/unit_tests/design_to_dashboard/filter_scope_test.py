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
"""What a control drawn in the grid is allowed to filter.

Written against the run where a date picker set to one month emptied every
chart on the page: it was in neither scope table, and a mask in neither table
is applied to everything.
"""

from __future__ import annotations

from typing import Any

import pytest

from superset.design_to_dashboard import filter_scope


def _plan(*decisions: tuple[str, str, str | None]) -> dict[str, Any]:
    return {
        "decisions": [
            {
                "region_id": region_id,
                "decision": "new_plugin",
                "ref": ref,
                "plugin_archetype": archetype,
                "slice_name": region_id.replace("_", " ").title(),
            }
            for region_id, archetype, ref in decisions
        ]
    }


def _spec(region_id: str, ref: str, **params: Any) -> dict[str, Any]:
    return {"region_id": region_id, "ref": ref, "params_decoded": params}


def _design(**roles: str) -> dict[str, Any]:
    return {
        "regions": [
            {"region_id": region_id, "role": role} for region_id, role in roles.items()
        ]
    }


PLAN = _plan(
    ("r02_filter", "filter_widget", "c2"),
    ("r04_card", "viz", "c4"),
    ("r08_bars", "viz", "c8"),
    ("r11_table", "table", "c11"),
)
SPECS = [
    _spec("r02_filter", "c2"),
    _spec("r04_card", "c4", x_axis="usage_month"),
    _spec("r08_bars", "c8", x_axis="usage_month"),
    _spec("r11_table", "c11"),
]
DESIGN = _design(
    r02_filter="filter", r04_card="kpi", r08_bars="chart", r11_table="table"
)
IDS = {"c2": 100, "c4": 101, "c8": 102, "c11": 103}


def test_the_control_region_is_found_from_its_archetype() -> None:
    """A chart spec knows its region but not what kind of thing it is."""
    assert filter_scope.filter_region_ids(PLAN) == {"r02_filter"}


def test_only_a_chart_that_cannot_widen_stays_out_of_scope() -> None:
    """A stock time-series chart is one query and one range.

    Window it to a month and it draws a point, and nothing in its config can
    ask for more. A KPI card draws a series too, but it is a generated plugin
    and can issue a second query over a wider window -- so it follows the
    dashboard's date like everything else.
    """
    trends = filter_scope.trend_regions(SPECS, {"r02_filter"}, DESIGN)
    assert trends == ["r08_bars"]


def test_a_chart_with_no_time_axis_is_not_a_trend() -> None:
    assert "r11_table" not in filter_scope.trend_regions(SPECS, set(), DESIGN)


def test_without_a_reading_nothing_is_treated_as_a_trend() -> None:
    """No roles known means no scope narrowing, which is Superset's default."""
    assert filter_scope.trend_regions(SPECS, {"r02_filter"}, None) == []


def test_the_emitter_excludes_itself() -> None:
    """Only the global-scope pointer drops a chart from its own reach.

    A picker that filters itself windows the very query its calendar bounds
    are read from, so the calendar shrinks to the selection on every use.
    """
    config = filter_scope.build(PLAN, SPECS, IDS, design_analysis=DESIGN)
    assert 100 in config["100"]["crossFilters"]["scope"]["excluded"]


def test_a_card_follows_the_date_but_a_stock_series_does_not() -> None:
    config = filter_scope.build(PLAN, SPECS, IDS, design_analysis=DESIGN)
    excluded = config["100"]["crossFilters"]["scope"]["excluded"]
    assert 102 in excluded, "a stock series chart cannot widen its own window"
    assert 101 not in excluded, "a card widens its sparkline query itself"
    assert 103 not in excluded, "a plain table has no series to lose"


def test_filtering_everything_still_spares_the_emitter() -> None:
    config = filter_scope.build(
        PLAN, SPECS, IDS, filter_scope.SCOPE_ALL, design_analysis=DESIGN
    )
    assert config["100"]["crossFilters"]["scope"]["excluded"] == [100]


def test_charts_in_scope_is_left_for_superset_to_compute() -> None:
    """`calculateScopes` recomputes it on every load from `excluded`.

    A value written here is stale as soon as a chart moves.
    """
    config = filter_scope.build(PLAN, SPECS, IDS, design_analysis=DESIGN)
    assert config["100"]["crossFilters"]["chartsInScope"] == []


def test_the_scope_is_rooted_so_superset_reads_it() -> None:
    """`calculateScopes` returns an empty scope unless `excluded` is a list."""
    scope = filter_scope.build(PLAN, SPECS, IDS, design_analysis=DESIGN)["100"][
        "crossFilters"
    ]["scope"]
    assert scope["rootPath"] == [filter_scope.DASHBOARD_ROOT_ID]
    assert isinstance(scope["excluded"], list)


def test_a_page_with_no_control_configures_nothing() -> None:
    plan = _plan(("r04_card", "viz", "c4"))
    assert filter_scope.build(plan, SPECS, IDS, design_analysis=DESIGN) == {}


def test_a_control_that_was_never_created_is_skipped() -> None:
    """A ref with no id is a chart the applier pruned, not a selector."""
    assert filter_scope.build(PLAN, SPECS, {}, design_analysis=DESIGN) == {}


# --- what the user is told ---------------------------------------------------


def test_the_skipped_charts_are_named() -> None:
    """A filter that silently skips two charts reads as a bug.

    The user asked to be told what matching the design costs, not to have the
    trade made quietly.
    """
    notes = " ".join(filter_scope.effects(PLAN, SPECS, design_analysis=DESIGN))
    assert "R08 Bars" in notes
    assert "full history" in notes


def test_the_silent_case_is_explained() -> None:
    """A chart with no time filter of its own is unreachable by a date range.

    Worth saying out loud, because it looks identical to a scoping bug.
    """
    notes = " ".join(filter_scope.effects(PLAN, SPECS, design_analysis=DESIGN))
    assert "time filter of its own" in notes


def test_filtering_everything_says_so() -> None:
    notes = " ".join(filter_scope.effects(PLAN, SPECS, filter_scope.SCOPE_ALL, DESIGN))
    assert "every chart" in notes


def test_a_page_with_no_control_discloses_nothing() -> None:
    plan = _plan(("r04_card", "viz", "c4"))
    assert filter_scope.effects(plan, SPECS, design_analysis=DESIGN) == []


@pytest.mark.parametrize(
    "answer,expected",
    [
        ("Yes, filter every chart on the page", filter_scope.SCOPE_ALL),
        (
            "No, leave them out so they keep their full history",
            filter_scope.SCOPE_EXCEPT_TRENDS,
        ),
        (None, filter_scope.SCOPE_EXCEPT_TRENDS),
    ],
)
def test_the_answer_is_read_for_intent(answer: Any, expected: str) -> None:
    assert filter_scope.scope_from_answer(answer) == expected
