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
"""Verify a created dashboard actually works.

Runs after the apply. Two questions a plan cannot answer:

* does every chart return data, or did it render an error card?
* does what was built match what the design asked for?

The first is checked deterministically against the chart data API. The second
is reported from the plan's own recorded fidelity notes -- honest, and free.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ChartCheck:
    chart_id: int
    slice_name: str
    viz_type: str
    ok: bool
    rows: int | None = None
    expected_rows: int | None = None
    error: str | None = None


@dataclass
class VerifyResult:
    dashboard_id: int
    charts: list[ChartCheck] = field(default_factory=list)
    fidelity_notes: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def rendering(self) -> str:
        total = len(self.charts)
        ok = sum(1 for c in self.charts if c.ok)
        return f"{ok}/{total} charts returning data"

    @property
    def all_ok(self) -> bool:
        return bool(self.charts) and all(c.ok for c in self.charts)


def _expected_rows(region: dict[str, Any]) -> int | None:
    """How many rows the design implies, if it can be told.

    Stage A records what it saw -- "five bars", "four data rows". A chart that
    returns one row where the design shows five is broken, but passes a
    rows > 0 check, so the observed count is worth comparing against.
    """
    import re

    text = " ".join(
        str(region.get(key) or "") for key in ("observed", "implied_data", "title")
    ).lower()
    words = {
        "one": 1,
        "two": 2,
        "three": 3,
        "four": 4,
        "five": 5,
        "six": 6,
        "seven": 7,
        "eight": 8,
        "nine": 9,
        "ten": 10,
    }
    # Allow a couple of adjectives between the count and the noun:
    # "five horizontal bars", "four data rows".
    for match in re.finditer(
        r"\b(\d{1,3}|one|two|three|four|five|six|seven|eight|nine|ten)\s+"
        r"(?:[a-z-]+\s+){0,3}"
        r"(bars?|rows?|slices?|segments?|categories|items?|tiles?|cards?)\b",
        text,
    ):
        raw = match.group(1)
        value = int(raw) if raw.isdigit() else words.get(raw)
        # Guard against absurd readings from prose.
        if value and 1 <= value <= 200:
            return value
    return None


def verify(  # noqa: C901
    dashboard_id: int,
    plan: dict[str, Any],
    design_analysis: dict[str, Any] | None = None,
) -> VerifyResult:
    """Query every chart on the dashboard and report what actually renders.

    Must run inside a Flask request context with ``g.user`` set, like the rest
    of the write path.
    """
    from superset import db
    from superset.models.dashboard import Dashboard

    result = VerifyResult(dashboard_id=dashboard_id)
    dashboard = db.session.query(Dashboard).get(dashboard_id)
    if dashboard is None:
        result.warnings.append(f"dashboard {dashboard_id} not found")
        return result

    # region_id -> expected row count, keyed by the chart the plan produced.
    expectations: dict[str, int] = {}
    if design_analysis:
        by_region = {r["region_id"]: r for r in design_analysis.get("regions", [])}
        for decision in plan.get("decisions", []):
            region = by_region.get(decision.get("region_id"))
            expected = _expected_rows(region) if region else None
            if expected and decision.get("slice_name"):
                expectations[decision["slice_name"]] = expected

    for chart in dashboard.slices:
        check = ChartCheck(
            chart_id=chart.id,
            slice_name=chart.slice_name,
            viz_type=chart.viz_type,
            ok=False,
            expected_rows=expectations.get(chart.slice_name),
        )
        try:
            if not chart.query_context:
                # A chart without one renders inside a dashboard but fails every
                # other consumer: the data API, thumbnails, alerts.
                check.error = "no saved query_context"
            else:
                payload = _fetch(chart.id)
                if payload.get("error"):
                    check.error = str(payload["error"])[:200]
                else:
                    check.rows = payload.get("rowcount")
                    check.ok = bool(check.rows)
                    if not check.ok:
                        check.error = "query succeeded but returned no rows"
                    elif check.expected_rows and check.rows != check.expected_rows:
                        # Right shape, wrong amount of data -- invisible to a
                        # rows > 0 check, and exactly what a user notices.
                        check.ok = False
                        check.error = (
                            f"returned {check.rows} row(s) but the design shows "
                            f"{check.expected_rows}"
                        )
        except Exception as ex:  # noqa: BLE001 - reported, never raised
            check.error = f"{type(ex).__name__}: {ex}"[:200]
        result.charts.append(check)

    # Carry the plan's own admissions forward so the user sees, in one place,
    # every way the result knowingly differs from the design.
    for decision in plan.get("decisions", []):
        if decision.get("fidelity_loss"):
            result.fidelity_notes.append(
                {
                    "region_id": decision.get("region_id"),
                    "viz_type": decision.get("viz_type"),
                    "difference": decision["fidelity_loss"],
                }
            )

    logger.info(
        "verified dashboard %s: %s, %d fidelity note(s)",
        dashboard_id,
        result.rendering,
        len(result.fidelity_notes),
    )
    return result


def _fetch(chart_id: int) -> dict[str, Any]:
    """Ask the chart data API what this chart returns.

    Deliberately the real endpoint rather than building a query context by
    hand: it is the path every consumer uses, so it catches exactly the
    failures a user would see.
    """
    from flask import current_app, g

    with current_app.test_client() as client:
        with client.session_transaction() as flask_session:
            flask_session["_user_id"] = str(g.user.id)
            flask_session["_fresh"] = True
        response = client.get(f"/api/v1/chart/{chart_id}/data/")

    if response.status_code != 200:
        body = response.get_json() or {}
        errors = body.get("errors") or []
        message = (
            errors[0].get("message")
            if errors
            else body.get("message") or f"HTTP {response.status_code}"
        )
        return {"error": message}

    results = (response.get_json() or {}).get("result") or [{}]
    return results[0]
