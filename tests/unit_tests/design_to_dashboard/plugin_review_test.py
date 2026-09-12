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
"""What the user is shown before stage F writes any code."""

from __future__ import annotations

import pathlib
from typing import Any

from superset.design_to_dashboard import plugin_review


def _design() -> dict[str, Any]:
    return {
        "regions": [
            {
                "region_id": "r01_title",
                "title": "Database Spend",
                "role": "header",
                "bbox": {"x": 0.0, "y": 0.0, "w": 1.0, "h": 0.03},
            },
            {
                "region_id": "r02_aws",
                "title": "AWS Database",
                "role": "kpi",
                "bbox": {"x": 0.0, "y": 0.05, "w": 0.32, "h": 0.04},
            },
            {
                "region_id": "r03_gcp",
                "title": "GCP Database",
                "role": "kpi",
                "bbox": {"x": 0.34, "y": 0.05, "w": 0.32, "h": 0.04},
            },
            {
                "region_id": "r04_azure",
                "title": "Azure Database",
                "role": "kpi",
                "bbox": {"x": 0.67, "y": 0.05, "w": 0.32, "h": 0.04},
            },
            {
                "region_id": "r05_coverage",
                "title": "Coverage",
                "role": "wrapper",
                "bbox": {"x": 0.0, "y": 0.42, "w": 0.48, "h": 0.08},
            },
            {
                "region_id": "r06_trend",
                "title": "Cost Trend",
                "role": "chart",
                "bbox": {"x": 0.0, "y": 0.18, "w": 1.0, "h": 0.08},
            },
            {
                "region_id": "r07_logo",
                "title": None,
                "role": "decoration",
                "bbox": {"x": 0.9, "y": 0.0, "w": 0.08, "h": 0.02},
            },
        ]
    }


def _bindings() -> dict[str, Any]:
    return {
        "shared_dataset_id": 9,
        "fact_tables": [{"name": "spend_by_day", "dataset_id": 20}],
        "views": [{"name": "spend_by_provider", "dataset_id": 31}],
        "bindings": [
            {"region_id": "r01_title", "dataset_id": 9},
            {"region_id": "r02_aws", "dataset_id": 31},
            {"region_id": "r03_gcp", "dataset_id": 31},
            {"region_id": "r04_azure", "dataset_id": 31},
            {"region_id": "r05_coverage", "dataset_id": 9},
            {"region_id": "r06_trend", "dataset_id": 20},
        ],
    }


def _plan() -> dict[str, Any]:
    return {
        "decisions": [
            {
                "region_id": "r01_title",
                "ref": "c1",
                "decision": "grid_text",
                "text": "# Database Spend",
            },
            {
                "region_id": "r02_aws",
                "ref": "c2",
                "decision": "new_plugin",
                "viz_type": "custom_provider_card",
                "plugin_archetype": "viz",
                "slice_name": "Provider spend card",
            },
            {
                "region_id": "r03_gcp",
                "ref": "c3",
                "decision": "new_plugin",
                "viz_type": "custom_provider_card",
                "plugin_archetype": "viz",
                "slice_name": "Provider spend card",
            },
            {
                "region_id": "r04_azure",
                "ref": "c4",
                "decision": "new_plugin",
                "viz_type": "custom_provider_card",
                "plugin_archetype": "viz",
                "slice_name": "Provider spend card",
            },
            {
                "region_id": "r05_coverage",
                "ref": "c5",
                "decision": "new_plugin",
                "viz_type": "custom_coverage_panel",
                "plugin_archetype": "container",
                "children": ["c6"],
                "slice_name": "Coverage panel",
            },
            {
                "region_id": "r06_trend",
                "ref": "c6",
                "decision": "configure",
                "viz_type": "echarts_timeseries_line",
                "slice_name": "Cost trend",
            },
            {
                "region_id": "r07_logo",
                "ref": None,
                "decision": "drop",
                "rationale": "decoration",
            },
        ]
    }


def _review(tmp_path: pathlib.Path) -> dict[str, Any]:
    return plugin_review.build(_design(), _bindings(), _plan(), [], tmp_path / "crops")


def test_identical_cards_collapse_to_one_entry(tmp_path: pathlib.Path) -> None:
    """Three provider cards are one plugin -- the judgement being reviewed."""
    review = _review(tmp_path)
    cards = [e for e in review["entries"] if e["viz_type"] == "custom_provider_card"]
    assert len(cards) == 1
    assert [u["region_id"] for u in cards[0]["used_by"]] == [
        "r02_aws",
        "r03_gcp",
        "r04_azure",
    ]


def test_entries_run_top_to_bottom(tmp_path: pathlib.Path) -> None:
    review = _review(tmp_path)
    assert [e["key"] for e in review["entries"]] == [
        "text:r01_title",
        "new_plugin:custom_provider_card",
        "configure:echarts_timeseries_line",
        "new_plugin:custom_coverage_panel",
    ]


def test_shared_dataset_is_named_and_costs_nothing(tmp_path: pathlib.Path) -> None:
    """A section on the shared dataset draws no data; say so, and charge 0."""
    review = _review(tmp_path)
    panel = next(
        e for e in review["entries"] if e["viz_type"] == "custom_coverage_panel"
    )
    assert panel["dataset"] == "shared (draws no data)"
    assert panel["draws_data"] is False
    assert panel["queries"] == 0


def test_a_view_is_named_not_numbered(tmp_path: pathlib.Path) -> None:
    review = _review(tmp_path)
    cards = next(
        e for e in review["entries"] if e["viz_type"] == "custom_provider_card"
    )
    assert cards["dataset"] == "spend_by_provider"


def test_queries_count_every_region_not_every_plugin(tmp_path: pathlib.Path) -> None:
    """Three cards sharing one plugin still run three queries per load."""
    review = _review(tmp_path)
    cards = next(
        e for e in review["entries"] if e["viz_type"] == "custom_provider_card"
    )
    assert cards["queries"] == 3
    # 3 cards + 1 trend; the text and the container query nothing.
    assert review["counts"]["queries_per_load"] == 4


def test_counts_describe_the_build(tmp_path: pathlib.Path) -> None:
    review = _review(tmp_path)
    assert review["counts"]["plugins"] == 2
    assert review["counts"]["regions_covered"] == 4


def test_dropped_sections_are_listed_not_hidden(tmp_path: pathlib.Path) -> None:
    review = _review(tmp_path)
    assert [d["region_id"] for d in review["dropped"]] == ["r07_logo"]
    assert all(e["kind"] != "drop" for e in review["entries"])


def test_a_note_reaches_every_region_behind_the_plugin(tmp_path: pathlib.Path) -> None:
    """One note on a shared plugin must reach all three of its decisions."""
    review = _review(tmp_path)
    plan = _plan()
    touched = plugin_review.apply_feedback(
        plan,
        {"notes": {"new_plugin:custom_provider_card": "keep the delta chip outlined"}},
        review,
    )
    assert touched == ["new_plugin:custom_provider_card"]
    noted = [d["region_id"] for d in plan["decisions"] if d.get("build_note")]
    assert noted == ["r02_aws", "r03_gcp", "r04_azure"]


def test_blank_and_unknown_notes_are_ignored(tmp_path: pathlib.Path) -> None:
    review = _review(tmp_path)
    plan = _plan()
    assert (
        plugin_review.apply_feedback(
            plan,
            {"notes": {"new_plugin:custom_provider_card": "   ", "nope": "x"}},
            review,
        )
        == []
    )
    assert all("build_note" not in d for d in plan["decisions"])


def test_no_crop_when_there_is_no_image(tmp_path: pathlib.Path) -> None:
    """The review still assembles; it just has no pictures in it."""
    review = _review(tmp_path)
    assert all(e["crop"] is None for e in review["entries"])


def test_a_note_the_pipeline_cannot_act_on_is_not_reported_as_accepted(
    tmp_path: pathlib.Path,
) -> None:
    """`build_note` has one reader -- stage F, which runs only for a plugin
    being built. A note on a stock chart was attached, counted and reported
    back as noted, and then nothing read it."""
    review = _review(tmp_path)
    plan = _plan()
    touched = plugin_review.apply_feedback(
        plan,
        {"notes": {"configure:echarts_timeseries_line": "make the line thicker"}},
        review,
    )
    assert touched == [
        "configure:echarts_timeseries_line (not applied: nothing is being built here)"
    ]
    assert all("build_note" not in d for d in plan["decisions"])
