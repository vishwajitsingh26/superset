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
"""A custom plugin's query context, derived from the controls it defines.

The generic derivation reads `metrics`, `groupby`, `x_axis` and friends. A
generated plugin names its own (`metricCoverage`), so every custom chart got a
query context with one empty query, and every consumer of it read "Empty
query?".
"""

from __future__ import annotations

from typing import Any

from superset.design_to_dashboard.applier import (
    _label_colors,
    _order_charts,
    _unhosted_ids,
    build_query_context,
    is_custom_viz_type,
    query_controls,
    QueryControls,
)

# The shape stage F writes: shared controls spread into controls of the
# plugin's own naming, next to display-only text controls.
TILE_PANEL = """
import { ControlPanelConfig, sharedControls, t } from '../adapters/supersetAdapter';

const config: ControlPanelConfig = {
  controlPanelSections: [
    {
      label: t('Query'),
      controlSetRows: [
        [{ name: 'metricPrimary', config: { ...sharedControls.metric, label: 'A' } }],
        [{ name: 'metricSecondary', config: { ...sharedControls.metric } }],
        [{ name: 'splitBy', config: { ...sharedControls.groupby } }],
        ['adhoc_filters'],
        [{ name: 'row_limit', config: { ...sharedControls.row_limit, default: 1 } }],
      ],
    },
    {
      label: t('Display'),
      controlSetRows: [
        [{ name: 'label', config: { type: 'TextControl', default: 'Total' } }],
        [{ name: 'captionColor', config: { type: 'TextControl', default: '' } }],
      ],
    },
  ],
};
export default config;
"""

ADHOC = {
    "expressionType": "SIMPLE",
    "column": {"column_name": "amount"},
    "aggregate": "SUM",
    "label": "Amount",
}
FILTER = {
    "expressionType": "SIMPLE",
    "subject": "provider",
    "operator": "==",
    "comparator": "A",
    "clause": "WHERE",
}


def _query(context: dict[str, Any]) -> dict[str, Any]:
    assert len(context["queries"]) == 1
    return context["queries"][0]


def test_custom_viz_types_follow_the_registry_rule() -> None:
    assert is_custom_viz_type("custom_kpi_tile")
    assert is_custom_viz_type("container_chart")
    assert not is_custom_viz_type("echarts_timeseries_line")
    assert not is_custom_viz_type(None)


def test_spread_shared_controls_type_a_plugin_s_own_controls() -> None:
    controls = query_controls(TILE_PANEL)
    assert controls.metrics == ("metricPrimary", "metricSecondary")
    assert controls.columns == ("splitBy",)


def test_display_controls_are_never_queried() -> None:
    controls = query_controls(TILE_PANEL)
    assert "label" not in controls.metrics + controls.columns
    assert "row_limit" not in controls.metrics + controls.columns


def test_a_control_type_classifies_a_control_without_a_spread() -> None:
    panel = """
      [{ name: 'measures', config: { type: 'DndMetricSelect', multi: true } }],
      [{ name: 'dimension', config: { type: 'DndColumnSelect' } }],
    """
    assert query_controls(panel) == QueryControls(
        metrics=("measures",), columns=("dimension",)
    )


def test_a_shared_control_listed_by_name_keeps_its_meaning() -> None:
    controls = query_controls("controlSetRows: [['metrics'], ['groupby'], ['x']]")
    assert controls.metrics == ("metrics",)
    assert controls.columns == ("groupby",)


def test_a_later_spread_does_not_retype_a_text_control() -> None:
    panel = """
      [{ name: 'caption', config: { type: 'TextControl' } }],
      [{ ...sharedControls.metric }],
    """
    assert query_controls(panel) == QueryControls()


def test_a_custom_chart_queries_the_metrics_its_controls_hold() -> None:
    params = {
        "metricPrimary": ADHOC,
        "metricSecondary": "saved_metric",
        "splitBy": ["provider"],
        "label": "Coverage",
        "adhoc_filters": [FILTER],
    }
    query = _query(
        build_query_context(
            params, 7, viz_type="custom_tile", controls=query_controls(TILE_PANEL)
        )
    )
    assert query["metrics"] == [ADHOC, "saved_metric"]
    assert query["columns"] == ["provider"]
    assert query["filters"] == [{"col": "provider", "op": "==", "val": "A"}]


def test_an_unset_optional_metric_is_left_out() -> None:
    """A `null` in the query fails it; the plugin's own buildQuery drops it."""
    params = {"metricPrimary": ADHOC, "metricSecondary": None}
    query = _query(
        build_query_context(
            params, 7, viz_type="custom_tile", controls=query_controls(TILE_PANEL)
        )
    )
    assert query["metrics"] == [ADHOC]


def test_a_plugin_that_draws_no_data_saves_no_query() -> None:
    """One empty query object is exactly what reads "Empty query?"."""
    context = build_query_context(
        {"bodyText": "Hello", "row_limit": 1},
        7,
        viz_type="custom_banner",
        controls=QueryControls(),
    )
    assert context["queries"] == []


def test_without_a_panel_only_an_unmistakable_metric_is_recognised() -> None:
    """A bare string could be a label as easily as a metric."""
    params = {
        "headlineMetric": ADHOC,
        "headline": "coverage_pct",
        "adhoc_filters": [FILTER],
    }
    query = _query(build_query_context(params, 7, viz_type="custom_tile"))
    assert query["metrics"] == [ADHOC]
    assert query["columns"] == []


def test_a_stock_chart_is_derived_as_before() -> None:
    params = {
        "x_axis": "day",
        "metrics": [ADHOC],
        "groupby": ["provider"],
        "headlineMetric": ADHOC,
    }
    query = _query(build_query_context(params, 7, viz_type="echarts_timeseries"))
    assert query["columns"] == ["day", "provider"]
    assert query["metrics"] == [ADHOC]


def test_a_stock_chart_with_nothing_to_query_keeps_its_query() -> None:
    """Only a custom plugin can legitimately query nothing."""
    context = build_query_context({}, 7, viz_type="table")
    assert len(context["queries"]) == 1


def test_a_generated_container_s_charts_are_created_before_it() -> None:
    """Stage F re-marks a built container `configure`, never `wrap`."""
    plan = {
        "decisions": [
            {"ref": "c9", "decision": "configure", "children": ["c1"]},
            {"ref": "c1", "decision": "configure"},
        ]
    }
    specs = [{"ref": "c9"}, {"ref": "c1"}]
    assert [spec["ref"] for spec in _order_charts(specs, plan)] == ["c1", "c9"]


def test_a_dropped_parent_puts_nothing_ahead_of_anything() -> None:
    plan = {
        "decisions": [
            {"ref": "c1", "decision": "configure"},
            {"ref": "c2", "decision": "configure"},
            {"ref": "c9", "decision": "drop", "children": ["c2"]},
        ]
    }
    specs = [{"ref": "c1"}, {"ref": "c2"}]
    assert [spec["ref"] for spec in _order_charts(specs, plan)] == ["c1", "c2"]


# --- a hosted chart is not a second, unpositioned dashboard member ---------


def test_a_hosted_child_is_not_in_the_dashboards_own_slice_list() -> None:
    """Regression: it used to also land as an orphan card at the page's foot."""
    plan = {
        "decisions": [
            {"ref": "c9", "decision": "configure", "children": ["c1"]},
            {"ref": "c1", "decision": "configure"},
        ]
    }
    ref_to_id = {"c9": 100, "c1": 101}
    assert _unhosted_ids([100, 101], ref_to_id, plan) == [100]


def test_a_chart_under_a_dropped_parent_stays_a_dashboard_member() -> None:
    """A dropped parent hosts nothing, so its children are not hosted either."""
    plan = {
        "decisions": [
            {"ref": "c9", "decision": "drop", "children": ["c1"]},
            {"ref": "c1", "decision": "configure"},
        ]
    }
    ref_to_id = {"c9": 100, "c1": 101}
    assert _unhosted_ids([100, 101], ref_to_id, plan) == [100, 101]


def test_reused_charts_are_filtered_the_same_way_as_created_ones() -> None:
    plan = {
        "decisions": [
            {"ref": "c9", "decision": "reuse", "children": ["c1"]},
            {"ref": "c1", "decision": "reuse"},
        ]
    }
    ref_to_id = {"c9": 5, "c1": 6}
    assert _unhosted_ids([5, 6], ref_to_id, plan) == [5]


def test_no_hosted_children_leaves_every_id_in_place() -> None:
    plan = {"decisions": [{"ref": "c1", "decision": "configure"}]}
    assert _unhosted_ids([1, 2, 3], {"c1": 1}, plan) == [1, 2, 3]


# --- the design's exact colours, seeded into Superset's own per-dashboard
# colour settings for the stock charts that color_scheme cannot reach -------


def test_label_colors_pass_through() -> None:
    design_system = {"label_colors": {"AWS": "#2563EB", "Azure": "#7C3AED"}}
    assert _label_colors(design_system) == {"AWS": "#2563EB", "Azure": "#7C3AED"}


def test_a_missing_label_colors_key_is_an_empty_map() -> None:
    assert _label_colors({}) == {}


def test_a_non_dict_label_colors_is_an_empty_map() -> None:
    """A model can hand back anything; nothing here should ever raise."""
    assert _label_colors({"label_colors": None}) == {}
    assert _label_colors({"label_colors": ["AWS", "#2563EB"]}) == {}
    assert _label_colors({"label_colors": "AWS"}) == {}


def test_an_entry_that_is_not_a_string_pair_is_dropped() -> None:
    design_system = {
        "label_colors": {
            "AWS": "#2563EB",
            "Azure": 123,
            "GCP": None,
            42: "#10B981",
        }
    }
    assert _label_colors(design_system) == {"AWS": "#2563EB"}
