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
"""How close the dashboard came, checked and written down.

The numbers in these tests are the ones a real run produced: six charts of
which two returned the wrong data, 43/60 against the design, and a headline
that said "Dashboard created".
"""

from __future__ import annotations

import pathlib
from typing import Any

import pytest

from superset.design_to_dashboard import trace, visual_verify
from superset.design_to_dashboard.runner import _done_label
from superset.design_to_dashboard.visual_verify import band_for, validate
from superset.utils import json

# Sums to 43 -- the score the one completed run actually earned.
SCORES = {
    "presence": 10,
    "position": 8,
    "chart_type": 8,
    "labels": 7,
    "numbers": 5,
    "styling": 5,
}


@pytest.fixture
def report() -> dict[str, Any]:
    return {
        "verdict": "needs_improvement",
        "score": 43,
        "scores": dict(SCORES),
        "findings": [{"severity": "critical"}],
    }


# --- the report has to agree with itself -------------------------------------


def test_a_consistent_report_is_clean(report: dict[str, Any]) -> None:
    assert validate(report) == []


def test_a_total_higher_than_its_parts_is_caught(report: dict[str, Any]) -> None:
    """`score` was taken on trust, so nothing stopped it being generous."""
    report["score"] = 58
    assert any("sum to 43" in p for p in validate(report))


def test_a_verdict_the_score_did_not_earn_is_caught(report: dict[str, Any]) -> None:
    report["verdict"] = "pass"
    assert any("'needs_improvement'" in p for p in validate(report))


def test_a_dimension_outside_its_range_is_caught(report: dict[str, Any]) -> None:
    report["scores"]["numbers"] = 99
    assert any("expected 0-10" in p for p in validate(report))


def test_a_missing_dimension_is_caught(report: dict[str, Any]) -> None:
    del report["scores"]["styling"]
    assert any("scores.styling" in p for p in validate(report))


def test_an_invented_dimension_is_caught(report: dict[str, Any]) -> None:
    report["scores"]["vibes"] = 5
    assert any("not scored" in p for p in validate(report))


def test_an_unknown_severity_is_caught(report: dict[str, Any]) -> None:
    report["findings"] = [{"severity": "catastrophic"}]
    assert any("critical, medium or low" in p for p in validate(report))


def test_a_blocked_render_is_not_scored() -> None:
    """A failed render is not a fidelity result, so there is no arithmetic."""
    assert validate({"blocked": "the screenshot was blank", "scores": None}) == []


@pytest.mark.parametrize(
    "score,verdict",
    [
        (60, "pass"),
        (54, "pass"),
        (53, "needs_improvement"),
        (40, "needs_improvement"),
        (39, "fail"),
        (0, "fail"),
    ],
)
def test_the_bands_are_the_ones_the_prompt_defines(score: int, verdict: str) -> None:
    assert band_for(score) == verdict


# --- the headline stops omitting what the body says --------------------------


class _Check:
    def __init__(self, ok: bool) -> None:
        self.ok = ok


class _Checks:
    def __init__(self, charts: list[_Check]) -> None:
        self.charts = charts


class _Visual:
    def __init__(self, **kwargs: Any) -> None:
        self.__dict__.update(
            {"blocked": None, "verdict": "pass", "score": 58, **kwargs}
        )


def test_the_real_runs_headline_names_both_problems() -> None:
    """Two of six charts wrong and 43/60 was published as "Dashboard created"."""
    checks = _Checks([_Check(True)] * 4 + [_Check(False)] * 2)
    visual = _Visual(verdict="needs_improvement", score=43)
    assert _done_label(checks, visual) == (
        "Dashboard created — 2 of 6 charts not right, 43/60 against your design"
    )


def test_a_clean_run_keeps_a_plain_headline() -> None:
    assert _done_label(_Checks([_Check(True)] * 6), _Visual()) == "Dashboard created"


def test_a_comparison_that_could_not_run_is_named() -> None:
    label = _done_label(_Checks([_Check(True)]), _Visual(blocked="blank screenshot"))
    assert "could not be compared" in label


# --- the findings are written down -------------------------------------------


def _rendered(result: dict[str, Any]) -> str:
    return trace.render(
        {
            "id": "t",
            "requirement": "x",
            "status": "done",
            "error": None,
            "events": [],
            "result": result,
        }
    )


@pytest.fixture
def result() -> dict[str, Any]:
    return {
        "visual_verdict": "needs_improvement",
        "visual_score": 43,
        "visual_scores": dict(SCORES),
        "visual_summary": "Recognisable, with wrong number formatting throughout.",
        "visual_problems": [],
        "visual_findings": [
            {
                "region_id": "r07_sales_by_genre",
                "severity": "critical",
                "design_shows": "genre name above each bar",
                "screenshot_shows": "names in a left axis gutter",
                "likely_fix": "plugin",
            }
        ],
        "screenshot_path": "shots/run.png",
        "fidelity_notes": [
            {"region_id": "r01", "difference": "heading uses the dashboard title style"}
        ],
    }


def test_the_trace_records_the_verdict(result: dict[str, Any]) -> None:
    assert "**needs_improvement** — 43/60" in _rendered(result)


def test_the_trace_records_each_dimension(result: dict[str, Any]) -> None:
    assert "numbers 5/10" in _rendered(result)


def test_the_trace_records_the_finding(result: dict[str, Any]) -> None:
    rendered = _rendered(result)
    assert "genre name above each bar" in rendered
    assert "names in a left axis gutter" in rendered


def test_what_was_found_is_kept_apart_from_what_was_predicted(
    result: dict[str, Any],
) -> None:
    """The trace used to carry only the plan's predictions, written before
    anything was built."""
    rendered = _rendered(result)
    assert "How close it came" in rendered
    assert "Differences the plan predicted" in rendered


def test_a_contract_breach_is_recorded_next_to_the_score(
    result: dict[str, Any],
) -> None:
    result["visual_problems"] = ["score is 58 but the six dimensions sum to 43"]
    assert "broke its own contract" in _rendered(result)


def test_a_run_with_no_comparison_gets_no_section() -> None:
    assert "How close it came" not in _rendered({})


# --- what the comparison is given -------------------------------------------


def _design() -> dict[str, Any]:
    return {
        "regions": [
            {
                "n": 1,
                "region_id": "r01_coverage",
                "title": "Coverage",
                "role": "wrapper",
                "bbox": {"x": 0.0, "y": 0.4, "w": 0.48, "h": 0.08},
                "children": [2, 3],
                "unusual_treatment": ["the Coverage column draws a ratio bar"],
            },
            {
                "n": 2,
                "region_id": "r02_aws",
                "title": "AWS",
                "role": "kpi",
                "bbox": {"x": 0.01, "y": 0.42, "w": 0.2, "h": 0.03},
                "children": [],
            },
            {
                "n": 3,
                "region_id": "r03_gcp",
                "title": "GCP",
                "role": "kpi",
                "bbox": {"x": 0.24, "y": 0.42, "w": 0.2, "h": 0.03},
                "children": [],
            },
        ],
        "global": {"reading_order": [1, 2, 3], "tabs": None},
    }


def _plan() -> dict[str, Any]:
    return {
        "decisions": [
            {"region_id": "r01_coverage", "ref": "c1", "decision": "configure"},
            {
                "region_id": "r02_aws",
                "ref": "c2",
                "decision": "drop",
                "fidelity_loss": "the plugin did not compile",
            },
        ]
    }


def _payload(prompt: str) -> dict[str, Any]:
    """The JSON block the comparison is handed."""
    return json.loads(prompt.split("```json")[1].split("```")[0])


def test_the_report_can_tell_a_panel_from_the_cards_inside_it() -> None:
    """A wrapper and its children used to arrive as peers, so "the panel is
    missing" could not be told from "the cards inside it are missing" --
    different findings, pointing at different stages."""
    regions = _payload(visual_verify.build_user_prompt(_design(), _plan()))["regions"]
    by_id = {r["region_id"]: r for r in regions}
    assert by_id["r01_coverage"]["contains"] == ["r02_aws", "r03_gcp"]
    assert by_id["r02_aws"]["contains"] == []


def test_position_is_scored_against_real_coordinates() -> None:
    """`position` is one of the six dimensions and the bboxes were dropped,
    so it could only ever be judged by eye."""
    regions = _payload(visual_verify.build_user_prompt(_design(), _plan()))["regions"]
    assert regions[0]["bbox"] == {"x": 0.0, "y": 0.4, "w": 0.48, "h": 0.08}


def test_the_design_system_contract_reaches_the_payload() -> None:
    """Stage C's own palette/typography/chrome contract was never sent here,
    so a fidelity verdict on colour or chrome could only be judged against
    the pixels, with no record of what the plugins were actually told to
    match."""
    plan = _plan()
    plan["design_system"] = {"palette": ["#0af"], "typography": {"value": "24px/700"}}
    payload = _payload(visual_verify.build_user_prompt(_design(), plan))
    assert payload["design_system"] == plan["design_system"]


def test_the_hard_parts_are_named() -> None:
    payload = visual_verify.build_user_prompt(_design(), _plan())
    assert "the Coverage column draws a ratio bar" in payload


def test_a_deliberate_drop_is_not_reported_as_missing() -> None:
    payload = visual_verify.build_user_prompt(_design(), _plan())
    assert "the plugin did not compile" in payload


def test_one_screenshot_needs_no_legend_beyond_first_and_second() -> None:
    assert "FIRST image" in visual_verify.build_user_prompt(_design(), _plan())


def test_several_screenshots_are_labelled(tmp_path: pathlib.Path) -> None:
    """A tabbed dashboard is several screenshots and a close look is several
    more; an unlabelled pile of images is worse than none."""
    shot = visual_verify.Capture(
        pages=[str(tmp_path / "a.png"), str(tmp_path / "b.png")],
        tabs=["Overview", "Detail"],
    )
    payload = visual_verify.build_user_prompt(
        _design(),
        _plan(),
        shot,
        ["the design", "built — tab 'Overview'", "built — tab 'Detail'"],
    )
    assert "1. the design" in payload
    assert "3. built — tab 'Detail'" in payload
    assert "one screenshot per tab" in payload


def test_the_viewport_is_the_design_s_own_width(tmp_path: pathlib.Path) -> None:
    """The 12-column grid reflows with the width, so rendering a 1139px design
    at 1600px compares two different layouts."""
    from PIL import Image

    design = tmp_path / "d.png"
    Image.new("RGB", (1139, 2592)).save(design)
    assert visual_verify.viewport_for([str(design)])["width"] == 1139


def test_an_extreme_design_width_is_clamped(tmp_path: pathlib.Path) -> None:
    """Superset's grid stops behaving below a laptop width."""
    from PIL import Image

    for width, expected in (
        (320, visual_verify.MIN_WIDTH),
        (5000, visual_verify.MAX_WIDTH),
    ):
        design = tmp_path / f"{width}.png"
        Image.new("RGB", (width, 800)).save(design)
        assert visual_verify.viewport_for([str(design)])["width"] == expected


def test_an_unreadable_design_still_captures() -> None:
    assert visual_verify.viewport_for(["/nope.png"]) == visual_verify.VIEWPORT


# --- what the browser saw each chart do ---------------------------------------


def test_a_dashboard_request_names_its_chart_in_the_url() -> None:
    url = (
        "http://127.0.0.1:8088/api/v1/chart/data?"
        "form_data=%7B%22slice_id%22%3A117%7D&dashboard_id=11"
    )
    assert visual_verify.chart_data_slice_id(url, None) == 117


def test_a_request_body_names_its_chart() -> None:
    body = json.dumps({"queries": [], "form_data": {"slice_id": 118}})
    assert visual_verify.chart_data_slice_id("/api/v1/chart/data", body) == 118


def test_a_form_encoded_legacy_request_names_its_chart() -> None:
    body = "form_data=%7B%22slice_id%22%3A%20%2242%22%7D"
    assert visual_verify.chart_data_slice_id("/superset/explore_json/", body) == 42


def test_a_request_naming_no_chart_is_not_guessed() -> None:
    assert visual_verify.chart_data_slice_id("/api/v1/chart/data", "{}") is None


# What the React Refresh overlay's text reads, as `innerText`.
OVERLAY_TEXT = """Error 1 of 1
TypeError
Cannot read properties of null (reading 'label')
Call Stack
getMetricLabel
packages/superset-ui-core/src/query/getMetricLabel.ts:31:16
transformProps
plugins/plugin-chart-custom-kpi-tile-1a2b3c/src/plugin/transformProps.ts:40:97
× Close"""


def test_an_overlay_is_summarised_as_its_error() -> None:
    assert visual_verify.error_summary(OVERLAY_TEXT) == (
        "TypeError: Cannot read properties of null (reading 'label')"
    )


def test_a_dev_server_overlay_is_summarised_as_its_error() -> None:
    text = "Uncaught runtime errors:\n×\nERROR\nboom is not defined\n    at x (y.js)"
    assert visual_verify.error_summary(text) == "boom is not defined"


def test_a_stack_is_summarised_as_its_first_line() -> None:
    stack = "TypeError: x is null\n    at transformProps (webpack-internal:///a.ts)"
    assert visual_verify.error_summary(stack) == "TypeError: x is null"


def test_an_error_is_attributed_to_every_chart_of_the_plugin_it_names() -> None:
    by_chart, unattributed = visual_verify.attribute_errors(
        [OVERLAY_TEXT],
        {117: "custom_kpi_tile", 118: "custom_kpi_tile", 119: "custom_kpi"},
    )
    assert sorted(by_chart) == [117, 118]
    assert unattributed == []


def test_a_short_stock_name_in_prose_attributes_nothing() -> None:
    """`table` occurs in any message; a compound identifier does not."""
    by_chart, unattributed = visual_verify.attribute_errors(
        ["Error: could not read the table"], {5: "table"}
    )
    assert by_chart == {}
    assert unattributed == ["Error: could not read the table"]


def test_a_compound_viz_type_named_in_a_message_is_attributed() -> None:
    by_chart, _ = visual_verify.attribute_errors(
        ["Error: custom_kpi_tile failed"], {5: "custom_kpi_tile"}
    )
    assert by_chart == {5: ["Error: custom_kpi_tile failed"]}


def _evidence(**kwargs: Any) -> Any:
    evidence = visual_verify._Evidence()
    evidence.__dict__.update(kwargs)
    return evidence


def test_render_evidence_is_mapped_to_each_chart() -> None:
    render, unattributed = visual_verify.collect_render(
        [117, 118, 119],
        _evidence(
            on_page={117, 118, 119},
            card_errors={119: "Data error"},
            data_calls=[
                visual_verify.DataCall(slice_id=117, status=200),
                visual_verify.DataCall(
                    slice_id=118, status=400, error="HTTP 400: no such metric"
                ),
                visual_verify.DataCall(slice_id=None, status=500),
            ],
            errors=[OVERLAY_TEXT, "Error: ResizeObserver loop limit exceeded"],
        ),
        {117: "custom_kpi_tile", 118: "table", 119: "table"},
    )
    assert render[117].failure == (
        "TypeError: Cannot read properties of null (reading 'label')"
    )
    assert render[118].failure == "its data request failed (HTTP 400: no such metric)"
    assert render[119].failure == "Data error"
    assert unattributed == ["Error: ResizeObserver loop limit exceeded"]


def test_a_chart_s_last_request_is_the_one_it_drew() -> None:
    render, _ = visual_verify.collect_render(
        [1],
        _evidence(
            on_page={1},
            data_calls=[
                visual_verify.DataCall(slice_id=1, status=400, error="HTTP 400"),
                visual_verify.DataCall(slice_id=1, status=200),
            ],
        ),
        {},
    )
    assert render[1].failure is None


# --- a query that succeeded and drew nothing is a failure too ---------------


@pytest.mark.parametrize(
    "body,expected",
    [
        ({"rowcount": 0}, 0),
        ({"rowcount": 4}, 4),
        ({"result": [{"rowcount": 0}]}, 0),
        ({"result": [{"rowcount": 12, "data": []}]}, 12),
        ({"result": []}, None),
        ({"data": []}, None),
        (None, None),
        ("not a dict", None),
    ],
)
def test_rowcount_reads_either_response_shape(
    body: object, expected: int | None
) -> None:
    assert visual_verify._rowcount(body) == expected


def test_a_successful_empty_query_is_a_failure() -> None:
    """A custom plugin the data API cannot query is judged by rendering; a
    query that succeeded with zero rows drew nothing, and used to read as
    'rendered without an error' -- true, and not the same as working."""
    render, _ = visual_verify.collect_render(
        [117],
        _evidence(
            on_page={117},
            data_calls=[visual_verify.DataCall(slice_id=117, status=200, rows=0)],
        ),
        {117: "custom_kpi_tile"},
    )
    assert render[117].failure == "its query succeeded but returned no rows"


def test_a_successful_query_with_rows_is_not_a_failure() -> None:
    render, _ = visual_verify.collect_render(
        [117],
        _evidence(
            on_page={117},
            data_calls=[visual_verify.DataCall(slice_id=117, status=200, rows=4)],
        ),
        {117: "custom_kpi_tile"},
    )
    assert render[117].failure is None


def test_only_the_last_successful_call_s_rows_count() -> None:
    """A chart's first query can return nothing before it re-queries with the
    real filters applied; only what it actually drew from matters."""
    render, _ = visual_verify.collect_render(
        [1],
        _evidence(
            on_page={1},
            data_calls=[
                visual_verify.DataCall(slice_id=1, status=200, rows=0),
                visual_verify.DataCall(slice_id=1, status=200, rows=4),
            ],
        ),
        {},
    )
    assert render[1].failure is None


def test_an_error_on_a_chart_s_own_page_is_that_chart_s() -> None:
    render, _ = visual_verify.collect_render(
        [7], _evidence(on_page={7}, direct={7: ["RangeError: bad length\n at x"]}), {}
    )
    assert render[7].failure == "RangeError: bad length"


def test_a_console_error_alone_is_not_a_render_failure() -> None:
    """React's development warnings are console errors too."""
    render, _ = visual_verify.collect_render(
        [117],
        _evidence(on_page={117}, console=[OVERLAY_TEXT]),
        {117: "custom_kpi_tile"},
    )
    assert render[117].console_errors
    assert render[117].failure is None


def test_the_result_lists_each_chart_that_failed_to_render() -> None:
    result = visual_verify.VisualResult(
        render={
            2: visual_verify.ChartRender(chart_id=2, on_page=True, card_error="boom"),
            1: visual_verify.ChartRender(chart_id=1, on_page=True),
        }
    )
    assert result.render_failures == ["chart 2 failed to render: boom"]


def test_the_comparison_is_told_which_charts_failed_to_render() -> None:
    shot = visual_verify.Capture(
        render={
            3: visual_verify.ChartRender(chart_id=3, on_page=True, card_error="boom")
        },
        overlays=["TypeError: x"],
    )
    prompt = visual_verify.build_user_prompt(
        _design(), _plan(), shot, ["the design"], region_of_chart={3: "r03_gcp"}
    )
    render = _payload(prompt)["render"]
    assert render["failed_to_render"] == [
        {"region_id": "r03_gcp", "chart_id": 3, "error": "boom"}
    ]
    assert render["dev_error_overlay"] == "removed before the screenshots were taken"


def test_a_clean_render_adds_nothing_to_the_prompt() -> None:
    shot = visual_verify.Capture(
        render={3: visual_verify.ChartRender(chart_id=3, on_page=True)}
    )
    prompt = visual_verify.build_user_prompt(_design(), _plan(), shot, ["x"])
    assert "render" not in _payload(prompt)


def test_charts_captured_one_at_a_time_are_explained() -> None:
    shot = visual_verify.Capture(pages=["p.png"], isolated=True, overlays=["x"])
    prompt = visual_verify.build_user_prompt(_design(), _plan(), shot, ["a", "b"])
    assert "could not be removed" in prompt


# --- every chart on the page is compared close up -----------------------------


def _regions() -> dict[str, dict[str, Any]]:
    return {
        "r01_trend": {"role": "chart", "bbox": {"x": 0.0, "y": 0.2}},
        "r02_kpi": {"role": "kpi", "bbox": {"x": 0.5, "y": 0.6}},
        "r03_banner": {"role": "text", "bbox": {"x": 0.0, "y": 0.1}},
        "r04_bars": {"role": "chart", "bbox": {"x": 0.5, "y": 0.2}},
    }


def test_close_ups_are_not_limited_to_number_bearing_roles() -> None:
    """Only KPI tiles were compared close up; a trend chart, a bar chart and a
    banner never were."""
    shot = visual_verify.Capture(
        charts={1: "1.png", 2: "2.png", 3: "3.png", 4: "4.png"}
    )
    order = visual_verify.close_up_order(
        {1: "r01_trend", 2: "r02_kpi", 3: "r03_banner", 4: "r04_bars"},
        _regions(),
        shot,
    )
    assert order == [
        (2, "r02_kpi"),
        (3, "r03_banner"),
        (1, "r01_trend"),
        (4, "r04_bars"),
    ]


def test_a_chart_that_failed_to_render_is_compared_last() -> None:
    shot = visual_verify.Capture(
        charts={1: "1.png", 2: "2.png"},
        render={2: visual_verify.ChartRender(chart_id=2, on_page=True, card_error="x")},
    )
    order = visual_verify.close_up_order(
        {1: "r01_trend", 2: "r02_kpi"}, _regions(), shot
    )
    assert [chart_id for chart_id, _ in order] == [1, 2]


def test_a_chart_with_no_capture_or_region_gets_no_close_up() -> None:
    shot = visual_verify.Capture(charts={1: "1.png"})
    order = visual_verify.close_up_order(
        {1: "r01_trend", 2: "r02_kpi", 5: None}, _regions(), shot
    )
    assert order == [(1, "r01_trend")]


# --- a tight image budget spends its slots on distinct things first ---------


def test_stock_viz_types_maps_configure_decisions_only() -> None:
    plan = {
        "decisions": [
            {
                "region_id": "r08",
                "decision": "configure",
                "chart_kind": "stock",
                "viz_type": "pie",
            },
            {
                "region_id": "r11",
                "decision": "configure",
                "chart_kind": "stock",
                "viz_type": "pie",
            },
            {
                "region_id": "r15",
                "decision": "new_plugin",
                "chart_kind": "custom_new",
                "viz_type": "custom_provider_breakdown_toggle",
            },
        ]
    }
    assert visual_verify._stock_viz_types(plan) == {"r08": "pie", "r11": "pie"}


def test_nothing_is_demoted_when_the_budget_covers_everything() -> None:
    ordered = [(1, "r08"), (2, "r11")]
    kept, dropped = visual_verify._prioritise_for_budget(
        ordered, {"r08": "pie", "r11": "pie"}, cap=5
    )
    assert kept == ordered
    assert dropped == []


def test_a_second_look_at_an_already_represented_stock_type_is_dropped_first() -> None:
    """r11 is the same stock `pie` as r08; a genuinely distinct region (r13)
    is worth a slot more than a second look at a shortfall already seen."""
    ordered = [(1, "r08"), (2, "r11"), (3, "r13")]
    kept, dropped = visual_verify._prioritise_for_budget(
        ordered, {"r08": "pie", "r11": "pie"}, cap=2
    )
    assert kept == [(1, "r08"), (3, "r13")]
    assert dropped == ["r11"]


def test_a_custom_plugin_region_is_never_treated_as_a_repeat() -> None:
    """Two regions sharing a custom plugin may still differ per instance --
    only a stock type's shortfall generalises from one look to the next."""
    ordered = [(1, "r03"), (2, "r04")]
    kept, dropped = visual_verify._prioritise_for_budget(ordered, {}, cap=1)
    assert kept == [(1, "r03")]
    assert dropped == ["r04"]


def test_a_repeat_still_fills_the_budget_once_every_first_look_fits() -> None:
    ordered = [(1, "r08"), (2, "r13"), (3, "r11"), (4, "r17")]
    stock_viz_type = {"r08": "pie", "r11": "pie", "r17": "pie"}
    kept, dropped = visual_verify._prioritise_for_budget(ordered, stock_viz_type, cap=3)
    assert kept == [(1, "r08"), (2, "r13"), (3, "r11")]
    assert dropped == ["r17"]


# --- a custom plugin's measured shape, not asked of the model ---------------


def _png(path: pathlib.Path, size: tuple[int, int]) -> str:
    from PIL import Image

    Image.new("RGB", size, "white").save(path)
    return str(path)


def test_custom_new_regions_are_named() -> None:
    plan = {
        "decisions": [
            {"region_id": "r15", "chart_kind": "custom_new"},
            {"region_id": "r08", "chart_kind": "stock"},
            {"region_id": "r09", "chart_kind": "custom_reuse"},
        ]
    }
    assert visual_verify._custom_new_regions(plan) == {"r15"}


def test_aspect_ratio_reads_a_real_image(tmp_path: pathlib.Path) -> None:
    wide = _png(tmp_path / "wide.png", (400, 100))
    assert visual_verify._aspect_ratio(wide) == pytest.approx(4.0)


def test_aspect_ratio_of_a_missing_file_is_none() -> None:
    assert visual_verify._aspect_ratio("/no/such/file.png") is None


def test_a_drifted_shape_is_measured(tmp_path: pathlib.Path) -> None:
    design_crop = _png(tmp_path / "design.png", (400, 100))
    built_crop = _png(tmp_path / "built.png", (400, 250))
    mismatch = visual_verify._geometry_mismatch(design_crop, built_crop)
    assert mismatch is not None
    assert "1.60" in mismatch
    assert "4.00" in mismatch


def test_a_shape_within_tolerance_is_not_a_mismatch(tmp_path: pathlib.Path) -> None:
    design_crop = _png(tmp_path / "design.png", (400, 100))
    built_crop = _png(tmp_path / "built.png", (408, 98))
    assert visual_verify._geometry_mismatch(design_crop, built_crop) is None


def test_a_measured_mismatch_upgrades_an_existing_finding() -> None:
    findings = [
        {
            "region_id": "r15",
            "severity": "low",
            "screenshot_shows": "slightly off",
        }
    ]
    visual_verify._enforce_geometry_findings(findings, {"r15": "built at 4.00 vs 1.60"})
    assert findings[0]["severity"] == "critical"
    assert "Measured: built at 4.00 vs 1.60" in findings[0]["screenshot_shows"]
    assert len(findings) == 1


def test_a_measured_mismatch_with_no_finding_gets_its_own() -> None:
    findings: list[dict[str, Any]] = []
    visual_verify._enforce_geometry_findings(findings, {"r15": "built at 4.00 vs 1.60"})
    assert len(findings) == 1
    assert findings[0]["region_id"] == "r15"
    assert findings[0]["severity"] == "critical"


def test_no_mismatches_leaves_findings_untouched() -> None:
    findings = [{"region_id": "r15", "severity": "low"}]
    visual_verify._enforce_geometry_findings(findings, {})
    assert findings == [{"region_id": "r15", "severity": "low"}]


def test_close_ups_past_the_cap_are_logged(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(visual_verify, "MAX_CLOSE_UPS", 1)
    monkeypatch.setattr(
        visual_verify.crop, "region_crop", lambda paths, region, out: "crop.png"
    )
    shot = visual_verify.Capture(pages=["page.png"], charts={1: "1.png", 2: "2.png"})
    design = {
        "regions": [
            {"region_id": region_id, **region}
            for region_id, region in _regions().items()
        ]
    }
    with caplog.at_level("INFO", logger=visual_verify.logger.name):
        images, legend, dropped, _geometry = visual_verify._image_set(
            ["design.png"],
            shot,
            {1: "r01_trend", 2: "r02_kpi"},
            design,
            tmp_path,
            "session",
        )
    assert images == ["design.png", "page.png", "crop.png", "2.png"]
    assert "r01_trend" in caplog.text
    assert dropped == ["r01_trend"]


# --- a crash one card shows is that card's -----------------------------------

TILES = {117: "custom_kpi_tile", 118: "custom_kpi_tile", 120: "custom_kpi_tile"}


def test_a_crash_one_card_shows_is_not_charged_to_its_siblings() -> None:
    """Four tiles shared a plugin; one threw, and the three that drew were
    reported broken and scored as absent."""
    render, _ = visual_verify.collect_render(
        list(TILES),
        _evidence(
            on_page=set(TILES),
            card_errors={118: "Unexpected error"},
            errors=[OVERLAY_TEXT],
        ),
        TILES,
    )
    assert render[118].failure == "Unexpected error"
    assert render[117].failure is None
    assert render[120].failure is None
    assert render[117].plugin_errors == [
        "TypeError: Cannot read properties of null (reading 'label')"
    ]


def test_with_no_card_claiming_it_every_chart_of_the_plugin_is_a_candidate() -> None:
    render, _ = visual_verify.collect_render(
        list(TILES), _evidence(on_page=set(TILES), errors=[OVERLAY_TEXT]), TILES
    )
    assert all(render[chart_id].failure for chart_id in TILES)


def test_an_error_on_a_chart_s_own_page_counts_beside_a_claimed_crash() -> None:
    render, _ = visual_verify.collect_render(
        list(TILES),
        _evidence(
            on_page=set(TILES),
            card_errors={118: "Unexpected error"},
            errors=[OVERLAY_TEXT],
            direct={117: ["RangeError: bad length\n at x"]},
        ),
        TILES,
    )
    assert render[117].failure == "RangeError: bad length"


def test_close_ups_never_take_the_request_past_its_image_budget(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Past 20 images every image is held to 2000px a side, and a full-page
    design is taller: the whole comparison was rejected."""
    monkeypatch.setattr(
        visual_verify.crop, "region_crop", lambda paths, region, out: "crop.png"
    )
    count = 12
    regions = [
        {"region_id": f"r{n:02d}", "role": "chart", "bbox": {"x": 0.0, "y": n / 20}}
        for n in range(count)
    ]
    shot = visual_verify.Capture(
        pages=["page.png"], charts={n + 1: f"{n + 1}.png" for n in range(count)}
    )
    images, legend, dropped, _geometry = visual_verify._image_set(
        ["design.png"],
        shot,
        {n + 1: f"r{n:02d}" for n in range(count)},
        {"regions": regions},
        tmp_path,
        "session",
    )
    assert len(images) == len(legend)
    assert dropped
    assert len(images) <= visual_verify.MAX_IMAGES
    assert len(images) == 2 + 2 * ((visual_verify.MAX_IMAGES - 2) // 2)
