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
"""The trace says which charts nothing checked, and why a chart did not render."""

from __future__ import annotations

from typing import Any

from superset.design_to_dashboard.trace import render


def _state(
    charts: list[dict[str, Any]], result: dict[str, Any] | None = None
) -> dict[str, Any]:
    return {
        "id": "s1",
        "status": "done",
        "events": [
            {"type": "stage_start", "stage": "verify", "label": "Checking", "at": 1.0},
            {
                "type": "stage_complete",
                "stage": "verify",
                "at": 2.0,
                "summary": "checked",
                "charts": charts,
            },
        ],
        "result": result or {},
    }


def test_a_custom_chart_nothing_queried_is_unchecked_not_ok() -> None:
    text = render(
        _state(
            [
                {
                    "chart_id": 3,
                    "viz_type": "custom_tile",
                    "ok": True,
                    "checked": False,
                    "rows": None,
                }
            ]
        )
    )
    assert "- unchecked `custom_tile` #3" in text


def test_a_check_recorded_before_checked_existed_reads_as_ok() -> None:
    text = render(_state([{"chart_id": 4, "viz_type": "table", "ok": True, "rows": 4}]))
    assert "- ok `table` #4" in text


def test_a_render_error_is_written_under_its_chart() -> None:
    text = render(
        _state(
            [
                {
                    "chart_id": 5,
                    "viz_type": "custom_tile",
                    "ok": False,
                    "checked": True,
                    "rows": None,
                    "error": "failed to render: TypeError: x is null",
                    "render_error": "TypeError: x is null",
                }
            ]
        )
    )
    assert "- **FAILED** `custom_tile` #5" in text
    assert "    - _render_: TypeError: x is null" in text


def test_the_charts_that_failed_to_render_are_listed_with_the_result() -> None:
    failure = "chart 5 (Coverage tile) failed to render: TypeError: x is null"
    text = render(
        _state(
            [],
            {
                "dashboard_id": 9,
                "cost_usd": 1.0,
                "rendering": "1/2 charts working",
                "render_failures": [failure],
            },
        )
    )
    assert f"- **Rendering:** 1/2 charts working\n    - {failure}" in text


def test_regions_the_image_budget_dropped_are_named_in_the_trace() -> None:
    """A region with no close-up pair was judged, if at all, from the
    full-page screenshot alone -- a reader has to be able to tell that apart
    from a region that was actually checked closely and matched."""
    text = render(
        _state(
            [],
            {
                "visual_verdict": "needs_improvement",
                "visual_score": 45,
                "not_verified_close_up": ["r11_cost_by_environment", "r13_usage"],
            },
        )
    )
    assert (
        "_No close-up was affordable within one request's image budget for:_ "
        "`r11_cost_by_environment`, `r13_usage`" in text
    )


def test_nothing_dropped_means_no_unverified_line() -> None:
    text = render(_state([], {"visual_verdict": "pass", "visual_score": 58}))
    assert "image budget" not in text
