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

from typing import Any

import pytest

from superset.design_to_dashboard import trace
from superset.design_to_dashboard.runner import _done_label
from superset.design_to_dashboard.visual_verify import band_for, validate

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
