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
"""What verify reports, measured against what a browser saw.

A real run read 9 of 11 charts as failed "Empty query?" where six loaded fine,
could not tell the two real HTTP 400s from those, never saw a script crash, and
flagged a 9-day, 3-provider trend for returning 27 rows "where the design draws
3".
"""

from __future__ import annotations

from typing import Any

from superset.design_to_dashboard.verify import (
    api_error,
    ChartCheck,
    confirm_new_plugins,
    first_query,
    judge_rows,
    row_shape,
    RowShape,
    UNCHECKED_CUSTOM,
    VerifyResult,
)
from superset.design_to_dashboard.visual_verify import ChartRender
from superset.utils import json

# --- the row heuristic compares like with like -------------------------------


def _grouped_payload(days: int, series: int) -> dict[str, Any]:
    data = [
        {"day": f"2024-01-{d + 1:02d}", "provider": f"p{s}", "spend": 1.0}
        for d in range(days)
        for s in range(series)
    ]
    return {
        "rowcount": len(data),
        "colnames": ["day", "provider", "spend"],
        "data": data,
    }


GROUPED_QUERY = {"columns": ["day", "provider"], "metrics": ["spend"]}


def test_a_grouped_series_is_counted_by_series_not_rows() -> None:
    """27 rows is 9 days of 3 providers; a design drawing 3 lines agrees."""
    shape = row_shape(_grouped_payload(9, 3), GROUPED_QUERY)
    assert shape == RowShape(rows=27, grouped=True, x_label="day", x_values=9, series=3)
    assert judge_rows(3, shape) == (None, None)


def test_a_grouped_series_is_also_counted_by_x_values() -> None:
    assert judge_rows(9, row_shape(_grouped_payload(9, 3), GROUPED_QUERY)) == (
        None,
        None,
    )


def test_a_grouped_result_matching_nothing_is_a_note() -> None:
    error, note = judge_rows(5, row_shape(_grouped_payload(9, 3), GROUPED_QUERY))
    assert error is None
    assert note is not None
    assert "9 `day` value(s) across 3 series" in note


def test_fewer_rows_than_drawn_marks_is_missing_data_in_any_shape() -> None:
    error, _ = judge_rows(30, row_shape(_grouped_payload(9, 3), GROUPED_QUERY))
    assert error == "returned 27 row(s) but the design shows 30"


def test_a_flat_result_is_one_row_per_mark() -> None:
    payload = {"rowcount": 8, "colnames": ["genre", "sales"], "data": []}
    shape = row_shape(payload, {"columns": ["genre"]})
    assert not shape.grouped
    _, note = judge_rows(5, shape)
    assert note is not None
    assert "check the row limit" in note


def test_a_pivoted_result_is_one_row_per_x_value_across_its_series() -> None:
    """Post-processing keeps only the axis among the query's columns; the
    series are its other columns. A 9-day, 3-line chart is not over its limit."""
    payload = {
        "rowcount": 9,
        "colnames": ["day", "spend, p0", "spend, p1", "spend, p2"],
    }
    shape = row_shape(payload, GROUPED_QUERY)
    assert shape == RowShape(rows=9, grouped=True, x_label="day", x_values=9, series=3)
    assert judge_rows(3, shape) == (None, None)
    assert judge_rows(9, shape) == (None, None)


def test_a_pivoted_result_whose_series_cannot_be_counted_says_nothing() -> None:
    payload = {"rowcount": 9, "colnames": ["day", "a", "b", "c"]}
    query = {"columns": ["day", "provider"], "metrics": ["spend", "count"]}
    shape = row_shape(payload, query)
    assert shape.grouped
    assert shape.series is None
    assert judge_rows(3, shape) == (None, None)


def test_a_grouped_shape_without_its_rows_says_nothing() -> None:
    payload = {"rowcount": 27, "colnames": ["day", "provider", "spend"]}
    assert judge_rows(3, row_shape(payload, GROUPED_QUERY)) == (None, None)


def test_adhoc_columns_are_matched_by_label() -> None:
    query = {"columns": [{"label": "day", "sqlExpression": "ds"}, "provider"]}
    assert row_shape(_grouped_payload(2, 2), query).series == 2


def test_the_first_query_is_read_from_the_saved_context() -> None:
    saved = json.dumps({"queries": [GROUPED_QUERY]})
    assert first_query(saved) == GROUPED_QUERY
    assert first_query("not json") == {}
    assert first_query(json.dumps({"queries": []})) == {}


# --- a failed request keeps its status -----------------------------------------


def test_an_api_error_carries_its_status() -> None:
    body = {"errors": [{"message": "metric 'coverage_pct' does not exist"}]}
    assert api_error(400, body) == ("HTTP 400: metric 'coverage_pct' does not exist")
    assert api_error(500, {"message": "boom"}) == "HTTP 500: boom"
    assert api_error(502, None) == "HTTP 502"


# --- the browser's evidence is folded in ---------------------------------------


def _custom(chart_id: int) -> ChartCheck:
    return ChartCheck(
        chart_id=chart_id,
        slice_name=f"tile {chart_id}",
        viz_type="custom_tile",
        ok=True,
        checked=False,
        note=UNCHECKED_CUSTOM,
    )


def _stock(chart_id: int, **kwargs: Any) -> ChartCheck:
    return ChartCheck(
        chart_id=chart_id,
        slice_name=f"chart {chart_id}",
        viz_type="table",
        **{"ok": True, **kwargs},
    )


def test_an_unchecked_custom_chart_is_not_counted_as_working() -> None:
    result = VerifyResult(dashboard_id=1, charts=[_stock(1), _custom(2)])
    assert result.rendering == (
        "1/1 charts returning data; 1 not checked (custom plugins, checked by "
        "rendering)"
    )
    assert not result.all_ok


def test_a_custom_chart_that_rendered_cleanly_is_working() -> None:
    result = VerifyResult(dashboard_id=1, charts=[_custom(2)])
    result.apply_render({2: ChartRender(chart_id=2, on_page=True, statuses=[200])})
    assert result.charts[0].ok
    assert result.charts[0].checked
    assert result.rendering == "1/1 charts working"
    assert result.all_ok


def test_a_crash_the_api_could_not_see_is_a_failure() -> None:
    result = VerifyResult(dashboard_id=1, charts=[_custom(2)])
    crash = "TypeError: Cannot read properties of null (reading 'label')"
    result.apply_render(
        {2: ChartRender(chart_id=2, on_page=True, script_errors=[crash])}
    )
    check = result.charts[0]
    assert not check.ok
    assert check.render_error == crash
    assert result.render_failures == [f"chart 2 (tile 2) failed to render: {crash}"]


def test_a_failed_data_request_in_the_browser_is_a_failure() -> None:
    result = VerifyResult(dashboard_id=1, charts=[_custom(2)])
    result.apply_render(
        {
            2: ChartRender(
                chart_id=2,
                on_page=True,
                statuses=[400],
                data_error="HTTP 400: metric does not exist",
            )
        }
    )
    assert not result.charts[0].ok
    assert "HTTP 400" in (result.charts[0].render_error or "")


def test_a_chart_that_renders_keeps_its_api_failure_as_a_note() -> None:
    """The dashboard works; alerts and reports reading the context do not."""
    check = _stock(1, ok=False, error="HTTP 400: Empty query?", status_code=400)
    result = VerifyResult(dashboard_id=1, charts=[check])
    result.apply_render({1: ChartRender(chart_id=1, on_page=True, statuses=[200])})
    assert check.ok
    assert check.note is not None
    assert "HTTP 400: Empty query?" in check.note


def test_a_row_count_failure_is_not_overturned_by_a_clean_render() -> None:
    check = _stock(1, ok=False, error="returned 1 row(s) but the design shows 5")
    result = VerifyResult(dashboard_id=1, charts=[check])
    result.apply_render({1: ChartRender(chart_id=1, on_page=True, statuses=[200])})
    assert not check.ok


def test_a_chart_the_browser_never_saw_stays_unchecked() -> None:
    result = VerifyResult(dashboard_id=1, charts=[_custom(2)])
    result.apply_render({2: ChartRender(chart_id=2, on_page=False)})
    assert not result.charts[0].checked
    assert "not seen rendering" in result.rendering


def test_a_table_grouped_by_two_dimensions_is_counted_by_its_rows() -> None:
    """Four rows of region by service, where the design draws four rows."""
    data = [
        {"region": region, "service": service, "spend": 1.0}
        for region in ("AWS", "GCP")
        for service in ("Compute", "Storage")
    ]
    payload = {"rowcount": 4, "colnames": ["region", "service", "spend"], "data": data}
    shape = row_shape(payload, {"columns": ["region", "service"], "metrics": ["spend"]})
    assert shape == RowShape(
        rows=4, grouped=True, x_label="region", x_values=2, series=2
    )
    assert judge_rows(4, shape) == (None, None)


def test_a_hosted_chart_that_failed_in_the_browser_is_a_failure() -> None:
    """Drawn inside its container it has no grid holder, but its 400 is its own."""
    result = VerifyResult(dashboard_id=1, charts=[_custom(11)])
    result.apply_render(
        {
            11: ChartRender(
                chart_id=11,
                on_page=False,
                statuses=[400],
                data_error="HTTP 400: bad metric",
            )
        }
    )
    check = result.charts[0]
    assert not check.ok
    assert check.checked
    assert "HTTP 400" in (check.render_error or "")
    assert result.render_failures
    assert result.rendering == "0/1 charts working"


def test_a_hosted_chart_with_a_clean_request_is_not_called_working() -> None:
    result = VerifyResult(dashboard_id=1, charts=[_custom(11)])
    result.apply_render({11: ChartRender(chart_id=11, on_page=False, statuses=[200])})
    assert not result.charts[0].checked


# --- a plugin stage F built is confirmed independently of its own report ----


def _plan_with(*decisions: dict[str, Any]) -> dict[str, Any]:
    return {"decisions": list(decisions)}


def test_a_registered_and_rendered_plugin_is_confirmed() -> None:
    plan = _plan_with(
        {
            "region_id": "r05_total_spend",
            "ref": "c5",
            "decision": "new_plugin",
            "viz_type": "custom_kpi_tile",
            "chart_kind": "custom_new",
        }
    )
    charts = [
        ChartCheck(chart_id=150, slice_name="x", viz_type="custom_kpi_tile", ok=True)
    ]
    confirmations = confirm_new_plugins(plan, {"custom_kpi_tile"}, charts, {"c5": 150})
    assert len(confirmations) == 1
    assert confirmations[0].registered is True
    assert confirmations[0].rendered_ok is True
    assert confirmations[0].chart_id == 150


def test_a_plugin_that_never_reached_the_registry_is_caught() -> None:
    """Dropped by `prune_unresolved` after failing to compile: no chart, no
    registry entry, but stage F still reported it "built"."""
    plan = _plan_with(
        {
            "region_id": "r05_total_spend",
            "ref": "c5",
            "decision": "new_plugin",
            "viz_type": "custom_kpi_tile",
            "chart_kind": "custom_new",
        }
    )
    confirmations = confirm_new_plugins(plan, set(), [], {})
    assert confirmations[0].registered is False
    assert confirmations[0].chart_id is None
    assert confirmations[0].rendered_ok is None


def test_a_registered_plugin_that_crashes_on_render_is_caught() -> None:
    plan = _plan_with(
        {
            "region_id": "r05_total_spend",
            "ref": "c5",
            "decision": "new_plugin",
            "viz_type": "custom_kpi_tile",
            "chart_kind": "custom_new",
        }
    )
    charts = [
        ChartCheck(
            chart_id=150,
            slice_name="x",
            viz_type="custom_kpi_tile",
            ok=False,
            error="crashed",
        )
    ]
    confirmations = confirm_new_plugins(plan, {"custom_kpi_tile"}, charts, {"c5": 150})
    assert confirmations[0].registered is True
    assert confirmations[0].rendered_ok is False


def test_only_new_plugin_decisions_are_confirmed() -> None:
    """A stock reuse or an existing custom plugin was never stage F's to
    build this run, so there is nothing here to confirm about it."""
    plan = _plan_with(
        {
            "region_id": "r09",
            "ref": "c9",
            "decision": "configure",
            "chart_kind": "stock",
        },
        {
            "region_id": "r05",
            "ref": "c5",
            "decision": "configure",
            "chart_kind": "custom_reuse",
        },
    )
    assert confirm_new_plugins(plan, set(), [], {}) == []


def test_no_new_plugins_confirms_nothing() -> None:
    assert confirm_new_plugins({"decisions": []}, set(), [], {}) == []
