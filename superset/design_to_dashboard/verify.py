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

The first is checked two ways. A stock chart is queried through the chart data
API with its saved query context. A custom plugin is not: its query is built in
the browser by its own TypeScript ``buildQuery``, and the context saved for it
is Python's approximation, so querying that reports the approximation's faults
as the chart's -- nine charts read "Empty query?" on a dashboard where six of
them loaded fine. A custom plugin is judged by rendering instead: the visual
stage loads the dashboard in a browser, records each chart's data requests,
error card and script errors, and `VerifyResult.apply_render` folds that in.

The second is reported from the plan's own recorded fidelity notes -- honest,
and free.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING

from superset.design_to_dashboard.applier import is_custom_viz_type
from superset.utils import json

if TYPE_CHECKING:
    from superset.design_to_dashboard.visual_verify import ChartRender

logger = logging.getLogger(__name__)

UNCHECKED_CUSTOM = (
    "custom plugin: its query is built in the browser, so the data API cannot "
    "check it -- it is checked by rendering the dashboard"
)


@dataclass
class ChartCheck:
    chart_id: int
    slice_name: str
    viz_type: str
    ok: bool
    rows: int | None = None
    expected_rows: int | None = None
    error: str | None = None
    note: str | None = None
    # False while nothing has been able to check the chart -- a custom plugin
    # the browser has not rendered. `ok` is then only "no failure seen", so an
    # unchecked chart is never counted as working.
    checked: bool = True
    # The status of a failed data API call. A 4xx or 5xx is a real failure,
    # and the status is what tells a bad request from a broken server.
    status_code: int | None = None
    # What went wrong when the dashboard was rendered in a browser.
    render_error: str | None = None


@dataclass
class VerifyResult:
    dashboard_id: int
    charts: list[ChartCheck] = field(default_factory=list)
    fidelity_notes: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    # Whether a browser render has been folded in.
    rendered_in_browser: bool = False

    @property
    def rendering(self) -> str:
        checked = [c for c in self.charts if c.checked]
        working = sum(1 for c in checked if c.ok)
        what = "charts working" if self.rendered_in_browser else "charts returning data"
        summary = f"{working}/{len(checked)} {what}"
        if unchecked := len(self.charts) - len(checked):
            why = (
                "custom plugins that were not seen rendering"
                if self.rendered_in_browser
                else "custom plugins, checked by rendering"
            )
            summary += f"; {unchecked} not checked ({why})"
        return summary

    @property
    def all_ok(self) -> bool:
        return bool(self.charts) and all(c.ok and c.checked for c in self.charts)

    @property
    def render_failures(self) -> list[str]:
        """One line per chart the browser saw fail, for the run's report."""
        return [
            f"chart {c.chart_id} ({c.slice_name}) failed to render: {c.render_error}"
            for c in self.charts
            if c.render_error
        ]

    def apply_render(self, render: Mapping[int, ChartRender]) -> None:
        """Fold in what a browser saw when it rendered the dashboard.

        The browser runs each plugin's real ``buildQuery`` and its real
        component, so for whether a chart *renders* it is the authority: a
        chart that crashed or whose data request failed is a failure however
        the data API answered, and a custom plugin the API could not check is
        judged here. A data API failure on a chart that rendered cleanly stays
        on record as a note -- the saved query context is still broken for
        alerts, reports and API consumers -- but the chart works. A row count
        that disagrees with the design is not overturned: rendering cleanly
        says nothing about whether the right rows came back.

        A failure counts wherever it was seen. A chart drawn inside a container
        has no grid holder, so it is never `on_page`, yet its data requests and
        script errors are its own. Only "rendered cleanly" needs the chart seen
        on the page: the absence of an error is evidence of nothing for a
        chart nobody looked at.
        """
        self.rendered_in_browser = True
        for check in self.charts:
            evidence = render.get(check.chart_id)
            if evidence is None:
                continue
            if failure := evidence.failure:
                check.render_error = failure
                check.ok = False
                check.checked = True
                if not check.error:
                    check.error = f"failed to render: {failure}"
                continue
            if not evidence.on_page:
                continue
            if not check.checked:
                check.checked = True
                check.ok = True
                check.note = "rendered in the browser without an error"
            elif check.status_code and check.status_code >= 400:
                check.note = (
                    f"renders on the dashboard, but its saved query context "
                    f"fails the data API ({check.error}), so alerts, reports "
                    "and API consumers will fail"
                )
                check.error = None
                check.ok = True


def _expected_rows(region: dict[str, Any]) -> int | None:
    """How many rows the design implies, if it can be told.

    Stage A records what it saw -- "five bars", "four data rows". A chart that
    returns one row where the design shows five is broken, but passes a
    rows > 0 check, so the observed count is worth comparing against.
    """
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
        r"(bars?|rows?|slices?|segments?|categories|items?)\b",
        text,
    ):
        raw = match.group(1)
        value = int(raw) if raw.isdigit() else words.get(raw)
        # Guard against absurd readings from prose.
        if value and 1 <= value <= 200:
            return value
    return None


@dataclass(frozen=True)
class RowShape:
    """What a result's rows are, so a design's count is compared with the
    thing it counts.

    A flat result is one row per drawn mark. A grouped one -- an x axis split
    by series -- is one row per x value per series: 27 rows for 9 days of 3
    providers, which a design drawing 3 lines does not contradict.
    """

    rows: int
    grouped: bool = False
    x_label: str | None = None
    x_values: int | None = None
    series: int | None = None


def _column_label(column: Any) -> str | None:
    if isinstance(column, str):
        return column
    if isinstance(column, dict):
        label = (
            column.get("label")
            or column.get("column_name")
            or column.get("sqlExpression")
        )
        return str(label) if label else None
    return None


def first_query(query_context: str | dict[str, Any] | None) -> dict[str, Any]:
    """The first query object of a saved query context, or an empty one."""
    if isinstance(query_context, str):
        try:
            query_context = json.loads(query_context)
        except (TypeError, ValueError):
            return {}
    if not isinstance(query_context, dict):
        return {}
    queries = query_context.get("queries") or []
    return queries[0] if queries and isinstance(queries[0], dict) else {}


def row_shape(payload: dict[str, Any], query: dict[str, Any]) -> RowShape:
    """Read a data API result's shape from the query that produced it.

    The grouping columns are the query's own columns that came back as columns
    of the result. A pivoted result keeps only the x axis among them, and is
    one row per x value with the series spread across its other columns; an
    unpivoted result with an x axis and a series column is one row per x value
    per series, and its distinct values are counted from the rows. Both are
    grouped: the design's count may be of either. Where the counts cannot be
    read the grouped shape is known but its counts are not.
    """
    rows = int(payload.get("rowcount") or 0)
    colnames = [str(c) for c in payload.get("colnames") or []]
    grouping = [
        label
        for label in (_column_label(c) for c in query.get("columns") or [])
        if label
    ]
    labels = [label for label in grouping if label in colnames]
    if len(grouping) < 2:
        return RowShape(rows=rows)
    if len(labels) < 2:
        # Grouped by two or more columns, but the series came back as columns:
        # post-processing pivoted them, so each row is one x value. The series
        # are counted from the remaining columns -- one per metric per series
        # -- and left unknown when those do not divide evenly, since a count of
        # something else is worse than none.
        if not labels:
            return RowShape(rows=rows, grouped=True)
        others = len([c for c in colnames if c != labels[0]])
        metrics = len(query.get("metrics") or [])
        series = others // metrics if metrics and others % metrics == 0 else None
        return RowShape(
            rows=rows,
            grouped=True,
            x_label=labels[0],
            x_values=rows,
            series=series or None,
        )
    data = payload.get("data")
    if not isinstance(data, list) or not all(isinstance(r, dict) for r in data):
        return RowShape(rows=rows, grouped=True, x_label=labels[0])
    return RowShape(
        rows=rows,
        grouped=True,
        x_label=labels[0],
        x_values=len({json.dumps(r.get(labels[0]), default=str) for r in data}),
        series=len(
            {
                json.dumps([r.get(label) for label in labels[1:]], default=str)
                for r in data
            }
        ),
    )


def judge_rows(expected: int | None, shape: RowShape) -> tuple[str | None, str | None]:
    """``(error, note)`` from comparing the design's count with the result.

    Fewer rows than the design draws marks is missing data whatever the shape:
    every drawn mark needs at least one row. More is only worth a note, and
    only when nothing in the result matches the count -- in a grouped result
    the design may be counting x values, series or rows (a table grouped by
    two dimensions draws one row per pair), and any match is fine.
    """
    if not expected:
        return None, None
    if shape.rows < expected:
        return f"returned {shape.rows} row(s) but the design shows {expected}", None
    if not shape.grouped:
        if shape.rows > expected:
            return None, (
                f"returned {shape.rows} row(s) where the design draws {expected} "
                "-- check the row limit"
            )
        return None, None
    if shape.x_values is None or shape.series is None:
        # Grouped, but the counts cannot be read: saying nothing beats
        # comparing rows against a count of something else.
        return None, None
    if expected in (shape.rows, shape.x_values, shape.series):
        return None, None
    return None, (
        f"returned {shape.x_values} `{shape.x_label}` value(s) across "
        f"{shape.series} series ({shape.rows} rows) where the design draws "
        f"{expected} -- check the time range and the row limit"
    )


def verify(  # noqa: C901
    dashboard_id: int,
    plan: dict[str, Any],
    design_analysis: dict[str, Any] | None = None,
) -> VerifyResult:
    """Query every stock chart on the dashboard and report what it returns.

    Custom plugins are recorded as not checked; see the module docstring.

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
            if is_custom_viz_type(chart.viz_type):
                check.ok = True
                check.checked = False
                check.note = UNCHECKED_CUSTOM
            elif not chart.query_context:
                # A chart without one renders inside a dashboard but fails every
                # other consumer: the data API, thumbnails, alerts.
                check.error = "no saved query_context"
            else:
                payload = _fetch(chart.id)
                if payload.get("error"):
                    check.status_code = payload.get("status")
                    check.error = str(payload["error"])[:200]
                else:
                    check.rows = payload.get("rowcount")
                    check.ok = bool(check.rows)
                    if not check.ok:
                        check.error = "query succeeded but returned no rows"
                    else:
                        shape = row_shape(payload, first_query(chart.query_context))
                        error, check.note = judge_rows(check.expected_rows, shape)
                        if error:
                            # Missing data: invisible to a rows > 0 check, and
                            # exactly what a user notices.
                            check.ok = False
                            check.error = error
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


@dataclass
class PluginConfirmation:
    """Whether a plugin this run built to fill a `custom_new` decision is
    actually real, checked independently rather than assumed from the
    decision a model made stages ago.

    Two separate facts, because they fail separately: a plugin that failed to
    compile is quietly dropped from the layout (`applier.prune_unresolved`)
    before ever reaching the registry, so it is unregistered and never
    rendered; one that compiles and registers can still throw at render time
    on data its own `buildQuery` never anticipated.
    """

    region_id: str
    viz_type: str
    chart_id: int | None
    # In the registry stage F rebuilt, whatever the browser or data API saw.
    registered: bool
    # None when no chart was ever created for this decision to check --
    # distinct from `False`, which means one was created and it did not work.
    rendered_ok: bool | None


def confirm_new_plugins(
    plan: dict[str, Any],
    registry_viz_types: set[str],
    charts: list[ChartCheck],
    ref_to_id: Mapping[str, int],
) -> list[PluginConfirmation]:
    """For every region stage C sent to F, whether what came back is real.

    Stage F reporting "built" and the registry rebuild running are not this
    confirmation -- both happen whether or not the plugin actually works. This
    is checked against the registry snapshot stage D and E were actually
    given, and against the same render evidence (`ChartCheck.ok`, folded in
    from both the data API and the browser) every other chart is judged by.
    """
    by_chart_id = {check.chart_id: check for check in charts}
    confirmations: list[PluginConfirmation] = []
    for decision in plan.get("decisions") or []:
        if decision.get("chart_kind") != "custom_new":
            continue
        viz_type = str(decision.get("viz_type") or "")
        chart_id = ref_to_id.get(str(decision.get("ref") or ""))
        check = by_chart_id.get(chart_id) if chart_id is not None else None
        confirmations.append(
            PluginConfirmation(
                region_id=str(decision.get("region_id") or ""),
                viz_type=viz_type,
                chart_id=chart_id,
                registered=viz_type in registry_viz_types,
                rendered_ok=check.ok if check is not None else None,
            )
        )
    return confirmations


def api_error(status: int, body: Any) -> str:
    """The message a failed chart data response carries, with its status."""
    body = body if isinstance(body, dict) else {}
    errors = body.get("errors") or []
    message = (
        errors[0].get("message")
        if errors and isinstance(errors[0], dict)
        else body.get("message")
    )
    return f"HTTP {status}: {message}" if message else f"HTTP {status}"


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
        return {
            "error": api_error(response.status_code, response.get_json(silent=True)),
            "status": response.status_code,
        }

    results = (response.get_json() or {}).get("result") or [{}]
    return results[0]
