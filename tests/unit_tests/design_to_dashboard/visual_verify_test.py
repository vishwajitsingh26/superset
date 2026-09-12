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
