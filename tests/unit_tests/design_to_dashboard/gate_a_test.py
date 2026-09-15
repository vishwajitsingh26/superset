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
from __future__ import annotations

from typing import Any

import pytest

from superset.design_to_dashboard import gate_a


@pytest.fixture
def analysis() -> dict[str, Any]:
    return {
        "status": "ok",
        "global": {"title": "Database Spend"},
        "regions": [
            {
                "n": 1,
                "region_id": "r01_database_overall_spend",
                "role": "wrapper",
                "title": "Database - Overall Spend $17,900",
                "frame": "none",
                "children": [2, 3],
                "same_as": None,
                "observed": "A card titled 'Database - Overall Spend' with a "
                "blue $17,900 total beside it (~14px, semibold), holding two "
                "provider cards.",
                "implied_data": "total database spend across providers",
            },
            {
                "n": 2,
                "region_id": "r02_aws_database",
                "role": "kpi",
                "title": "AWS Database",
                "children": [],
                "same_as": None,
                "observed": "$10,495, a sparkline of the last 6 months.",
                "implied_data": "AWS database spend",
                "unusual_treatment": ["a sparkline runs beneath the value"],
                "stock_candidate": None,
            },
            {
                "n": 3,
                "region_id": "r03_gcp_database",
                "role": "kpi",
                "title": "GCP Database",
                "children": [],
                "same_as": 2,
                "observed": "$7,517, a sparkline of the last 6 months.",
                "implied_data": "GCP database spend",
                "stock_candidate": "big_number_total",
            },
            {
                "n": 4,
                "region_id": "r04_filter",
                "role": "filter",
                "title": None,
                "children": [],
                "same_as": None,
                "observed": "A bordered select reading 'All Regions'.",
                "implied_data": "the region a user can filter by",
            },
            {
                "n": 5,
                "region_id": "r05_recent_activity",
                "role": "table",
                "title": "Recent Activity",
                "children": [],
                "same_as": None,
                "observed": "A list of recent events.",
                "implied_data": "recent account activity",
                "ambiguity": "the list is truncated; row count beyond 3 is unknown",
            },
        ],
    }


def test_presentation_nests_children_under_their_wrapper(
    analysis: dict[str, Any],
) -> None:
    presentation = gate_a.build_presentation(analysis)
    assert [r["region_id"] for r in presentation["regions"]] == [
        "r01_database_overall_spend",
        "r04_filter",
        "r05_recent_activity",
    ]
    wrapper = presentation["regions"][0]
    assert [c["region_id"] for c in wrapper["children"]] == [
        "r02_aws_database",
        "r03_gcp_database",
    ]


def test_wrapper_gets_no_plugin_choice_but_leaf_does(
    analysis: dict[str, Any],
) -> None:
    presentation = gate_a.build_presentation(analysis)
    wrapper = presentation["regions"][0]
    assert wrapper["plugin_choice"] is None
    kpi = wrapper["children"][0]
    assert kpi["plugin_choice"]["options"] == ["stock", "custom"]


def test_plugin_choice_carries_the_registry_match_as_information_not_a_default(
    analysis: dict[str, Any],
) -> None:
    """Both options are always offered; a stock match is a neutral note."""
    presentation = gate_a.build_presentation(analysis)
    aws, gcp = presentation["regions"][0]["children"]
    assert "recommendation" not in aws["plugin_choice"]
    assert aws["plugin_choice"]["options"] == ["stock", "custom"]
    assert aws["plugin_choice"]["stock_candidate"] is None
    assert "no registered viz type" in aws["plugin_choice"]["note"]
    assert gcp["plugin_choice"]["options"] == ["stock", "custom"]
    assert gcp["plugin_choice"]["stock_candidate"] == "big_number_total"
    assert "not a recommendation" in gcp["plugin_choice"]["note"]


def test_wrapper_with_a_real_printed_value_gets_a_reads_data_question(
    analysis: dict[str, Any],
) -> None:
    presentation = gate_a.build_presentation(analysis)
    gaps = {
        q["gap"]
        for q in presentation["questions"]
        if q["region_id"] == "r01_database_overall_spend"
    }
    assert gate_a.GAP_WRAPPER_READS_DATA in gaps


def test_a_font_size_number_does_not_trigger_a_reads_data_question() -> None:
    """ "~14px" is a digit; it is not a printed value. Regression for the bug
    where every wrapper's own font-size note made it look data-bearing."""
    region = {
        "n": 1,
        "region_id": "r01_wrapper",
        "role": "wrapper",
        "title": "Coverage",
        "children": [],
        "same_as": None,
        "observed": "Title 'Coverage' at ~14px semibold, no other text.",
        "implied_data": "a coverage panel",
    }
    assert not gate_a._looks_data_bearing(region)


def test_embedded_series_question_only_fires_when_not_already_flagged(
    analysis: dict[str, Any],
) -> None:
    presentation = gate_a.build_presentation(analysis)
    aws_qs = {
        q["gap"]
        for q in presentation["questions"]
        if q["region_id"] == "r02_aws_database"
    }
    assert gate_a.GAP_EMBEDDED_SERIES in aws_qs


def test_filter_region_always_gets_a_filter_kind_question(
    analysis: dict[str, Any],
) -> None:
    presentation = gate_a.build_presentation(analysis)
    filter_qs = [q for q in presentation["questions"] if q["region_id"] == "r04_filter"]
    assert any(q["gap"] == gate_a.GAP_FILTER_KIND for q in filter_qs)


def test_ambiguity_is_surfaced_as_a_question(analysis: dict[str, Any]) -> None:
    presentation = gate_a.build_presentation(analysis)
    matches = [q for q in presentation["questions"] if q["gap"] == gate_a.GAP_AMBIGUITY]
    assert any(q["region_id"] == "r05_recent_activity" for q in matches)


def test_shared_grain_question_is_asked_once_per_group_on_the_first_occurrence(
    analysis: dict[str, Any],
) -> None:
    presentation = gate_a.build_presentation(analysis)
    matches = [
        q for q in presentation["questions"] if q["gap"] == gate_a.GAP_SHARED_GRAIN
    ]
    assert len(matches) == 1
    assert matches[0]["region_id"] == "r02_aws_database"
    assert "r03_gcp_database" in matches[0]["text"]


def test_question_ids_are_unique_across_the_whole_presentation(
    analysis: dict[str, Any],
) -> None:
    presentation = gate_a.build_presentation(analysis)
    ids = [q["id"] for q in presentation["questions"]]
    assert len(ids) == len(set(ids))


def test_build_presentation_does_not_mutate_its_input(
    analysis: dict[str, Any],
) -> None:
    import copy

    before = copy.deepcopy(analysis)
    gate_a.build_presentation(analysis)
    assert analysis == before
