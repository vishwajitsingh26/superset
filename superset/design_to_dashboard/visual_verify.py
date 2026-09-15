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
"""Look at the dashboard that was built and say how close it came.

`verify.py` asks whether each chart returns rows. This asks the different and
harder question: does it *look* like the design. Nothing else in the pipeline
ever sees the result, so without this a run can report six charts returning
data while the dashboard resembles the design only loosely.

Report only. It changes nothing on this run -- it records what differs so the
user knows where to look and the next run has something to aim at.

Playwright is driven directly rather than through Superset's thumbnail
machinery, which is gated behind the `PLAYWRIGHT_REPORTS_AND_THUMBNAILS`
feature flag and defaults to a Selenium driver that is not installed here.
"""

from __future__ import annotations

import logging
import pathlib
import re
import urllib.parse
from dataclasses import dataclass, field
from typing import Any

from superset.design_to_dashboard import crop
from superset.design_to_dashboard.llm.base import LLMError, LLMProvider
from superset.design_to_dashboard.pipeline.tool_loop import extract_json
from superset.design_to_dashboard.verify import api_error
from superset.utils import json

logger = logging.getLogger(__name__)

# Wide enough that a 12-column dashboard is not stacked into a phone layout,
# which would read as a fidelity failure that only the viewport caused.
# Fallback only. The real width is the design's own, because the 12-column
# grid reflows with it: judging "position" and "proportions" from a 1600px
# render of a 1139px design compares two different layouts and reports the
# difference as a fidelity problem.
VIEWPORT = {"width": 1600, "height": 1200}
# Superset's grid stops behaving below roughly a laptop width, and a very wide
# render makes every card short. The design's width is used inside this range.
MIN_WIDTH, MAX_WIDTH = 1000, 2400
# Each chart card in the dashboard grid, and the tab strip.
CHART_HOLDER = ".dashboard-chart-id-{chart_id}"
TAB_STRIP = '[data-test="dashboard-component-tabs"] [data-test="nav-list"]'
TAB_ITEM = f"{TAB_STRIP} .ant-tabs-tab"
# Charts fetch their own data after the page loads; the screenshot is worthless
# until they have painted.
CHART_SETTLE_MS = 12000
NAV_TIMEOUT_MS = 60000
# Requests that fetch a chart's data: the v1 API, and the legacy endpoint older
# viz types still use.
CHART_DATA_PATHS = ("/api/v1/chart/data", "/superset/explore_json")
# A card in an error state draws an error alert inside its holder.
CARD_ERROR = ".ant-alert-error"
# The development build's full-screen error overlays -- React Refresh's and the
# webpack dev server's, both iframes -- and any other overlay iframe.
OVERLAY_SELECTOR = (
    "#react-refresh-overlay, #webpack-dev-server-client-overlay, "
    "iframe[id*='overlay' i]"
)
# Reads each overlay's text, then removes it. Same-origin `about:blank` frames,
# so the document inside is readable.
OVERLAY_SCRIPT = """(selector) =>
  Array.from(document.querySelectorAll(selector)).map((element) => {
    let text = '';
    try {
      const inner = element.contentDocument;
      text = (inner && inner.body ? inner.body.innerText : element.innerText) || '';
    } catch (error) {
      text = '';
    }
    element.remove();
    return text.slice(0, 4000);
  })"""
OVERLAY_ATTEMPTS = 2
OVERLAY_RECHECK_MS = 750
# One chart alone, the view Superset's own chart screenshots use.
STANDALONE_CHART = "/explore/?slice_id={chart_id}&standalone=true"
CHART_ELEMENT = ".chart-container"
LOADING_ELEMENT = ".chart-container .loading"
ISOLATED_TIMEOUT_MS = 30000
ISOLATED_SETTLE_MS = 3000


@dataclass
class VisualResult:
    verdict: str = "unknown"
    score: int = 0
    scores: dict[str, int] = field(default_factory=dict)
    findings: list[dict[str, Any]] = field(default_factory=list)
    summary: str = ""
    blocked: str | None = None
    screenshot_path: str | None = None
    cost_usd: float = 0.0
    error: str | None = None
    # Ways the report broke its own contract -- a total that does not match the
    # dimensions, a verdict that does not match the total.
    problems: list[str] = field(default_factory=list)
    # chart id -> how it rendered in the browser. The data API cannot see a
    # script crash, so this is the only record of one.
    render: dict[int, ChartRender] = field(default_factory=dict)
    # The development error overlay's errors, summarised, when one was found.
    overlays: list[str] = field(default_factory=list)
    # Charts were captured one at a time because the overlay would not close.
    isolated: bool = False
    # Regions the close-up image budget could not afford a pair for. A finding
    # against one of these was judged from the full-page screenshot alone.
    not_verified: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.error is None and self.blocked is None

    @property
    def render_failures(self) -> list[str]:
        """One line per chart the browser saw fail."""
        return [
            f"chart {chart_id} failed to render: {render.failure}"
            for chart_id, render in sorted(self.render.items())
            if render.failure
        ]


# The six dimensions the stage prompt asks for, each scored 0-10.
DIMENSIONS = ("presence", "position", "chart_type", "labels", "numbers", "styling")
MAX_DIMENSION = 10
# The bands the prompt defines. A verdict is derived from the score rather than
# taken alongside it, so the two cannot disagree.
BANDS = ((54, "pass"), (40, "needs_improvement"), (0, "fail"))


def band_for(score: int) -> str:
    """The verdict a score earns."""
    for floor, verdict in BANDS:
        if score >= floor:
            return verdict
    return "fail"


def validate(report: dict[str, Any]) -> list[str]:  # noqa: C901
    """Check the report against its own contract.

    Nothing here judges the dashboard; it judges the judgement. `score` and
    `verdict` were taken on trust, so a report could rate six dimensions at
    five apiece and call the total 58, or score 43 and call it a pass -- and
    the prompt's closing instruction is exactly that a generous score "becomes
    a dashboard nobody re-checks". Scored arithmetic is checkable, so it is
    checked.
    """
    problems: list[str] = []
    if report.get("blocked"):
        # A render that could not be judged is not a fidelity result, and the
        # prompt says to score nothing. There is no arithmetic to check.
        return problems

    scores = report.get("scores")
    if not isinstance(scores, dict):
        return ["scores is missing"]
    for dimension in DIMENSIONS:
        value = scores.get(dimension)
        if not isinstance(value, int) or not 0 <= value <= MAX_DIMENSION:
            problems.append(
                f"scores.{dimension} is {value!r}, expected 0-{MAX_DIMENSION}"
            )
    if unknown := sorted(set(scores) - set(DIMENSIONS)):
        problems.append(f"scores has dimensions that are not scored: {unknown}")

    total = sum(v for v in scores.values() if isinstance(v, int))
    reported = report.get("score")
    if not isinstance(reported, int):
        problems.append(f"score is {reported!r}, expected an integer")
    elif reported != total:
        problems.append(f"score is {reported} but the six dimensions sum to {total}")

    if (verdict := report.get("verdict")) != (earned := band_for(total)):
        problems.append(f"verdict is {verdict!r} but {total}/60 is {earned!r}")

    for index, finding in enumerate(report.get("findings") or []):
        if not isinstance(finding, dict):
            problems.append(f"finding {index} is not an object")
            continue
        if finding.get("severity") not in {"critical", "medium", "low"}:
            problems.append(
                f"finding {index}: severity {finding.get('severity')!r} is not "
                "critical, medium or low"
            )
    return problems


def _cap_unverified_findings(
    findings: list[dict[str, Any]], not_verified: list[str]
) -> None:
    """Mark, in place, a finding the model made without its close-up pair.

    The prompt already tells the model not to assert a defect on these regions;
    this is the check on that instruction rather than trust in it. A finding
    that ignored the caveat is not dropped -- a genuine defect the image budget
    could not afford to show closely should still reach the report -- but its
    severity is capped and a note says why, so it reads as unconfirmed rather
    than as fact.
    """
    unverified = set(not_verified)
    if not unverified:
        return
    for finding in findings:
        if not isinstance(finding, dict):
            continue
        if str(finding.get("region_id")) not in unverified:
            continue
        if finding.get("severity") == "critical":
            finding["severity"] = "medium"
        note = " (no close-up was available; judged from the full-page screenshot only)"
        shown = str(finding.get("screenshot_shows") or "")
        if note not in shown:
            finding["screenshot_shows"] = shown + note


def _enforce_geometry_findings(
    findings: list[dict[str, Any]], geometry_mismatches: dict[str, str]
) -> None:
    """A custom plugin's measured shape drift is `critical`, in place -- not
    left to whether the model's own read of two images agreed.

    Colour is allowed to differ for a custom plugin; shape, placement and
    size are the one thing it exists to get exactly right, and this is
    measured from the same crop pair the model was shown, not asserted. A
    region this check finds a mismatch for keeps whatever the model said
    about it -- upgraded to `critical` if it said less -- and gets a finding
    of its own if the model said nothing at all, the same way a render
    failure always gets one regardless of what the report chose to mention.
    """
    if not geometry_mismatches:
        return
    covered: set[str] = set()
    for finding in findings:
        if not isinstance(finding, dict):
            continue
        region_id = str(finding.get("region_id"))
        mismatch = geometry_mismatches.get(region_id)
        if mismatch is None:
            continue
        covered.add(region_id)
        finding["severity"] = "critical"
        shown = str(finding.get("screenshot_shows") or "")
        if mismatch not in shown:
            finding["screenshot_shows"] = f"{shown} Measured: {mismatch}.".strip()
        finding.setdefault("likely_fix", "plugin")
    for region_id, mismatch in geometry_mismatches.items():
        if region_id in covered:
            continue
        findings.append(
            {
                "region_id": region_id,
                "severity": "critical",
                "design_shows": "the design's own crop of this section",
                "screenshot_shows": f"Measured: {mismatch}.",
                "likely_fix": "plugin",
            }
        )


@dataclass
class DataCall:
    """One chart-data request the page made, and how it was answered."""

    slice_id: int | None
    status: int
    error: str | None = None
    # Rows the response carried, for a call that succeeded. None when the
    # call failed (the status already says so) or the body could not be read.
    rows: int | None = None


@dataclass
class ChartRender:
    """What the browser saw of one chart.

    The data API cannot see a JavaScript crash, and cannot check a custom
    plugin at all, so this is the evidence for whether a chart renders: the
    card's own error, the status of every data request it made, and any
    uncaught script error that names its plugin -- unless a sibling's card
    already claims that error.
    """

    chart_id: int
    on_page: bool = False
    statuses: list[int] = field(default_factory=list)
    data_error: str | None = None
    card_error: str | None = None
    # Rows the chart's last successful data call returned. A rendering check
    # cannot see a JavaScript crash's absence as evidence of anything, but a
    # call that succeeded and carried zero rows is the one case it can call a
    # failure on its own: a custom plugin the data API cannot query at all,
    # drawing "No data" with no thrown error, used to read as a chart that
    # "rendered without an error" -- true, and not the same as working.
    data_rows: int | None = None
    script_errors: list[str] = field(default_factory=list)
    # Kept as evidence, never as a failure on their own: React's development
    # warnings are console errors too, and a missing `key` does not stop a
    # chart from drawing.
    console_errors: list[str] = field(default_factory=list)
    # An uncaught error naming this chart's plugin, while another chart of the
    # same plugin shows the error card. The stack names the plugin; the card
    # names the chart that threw. Evidence here, not a failure: this card drew.
    plugin_errors: list[str] = field(default_factory=list)
    # Captured on its own standalone page because the dashboard was covered.
    isolated: bool = False

    @property
    def failure(self) -> str | None:
        """Why the chart did not render, or None when nothing says it failed.

        The card's own error first, because it is what the viewer reads; then
        the chart's last data request, since a chart re-queries and only the
        answer it drew from counts; then a script error attributed to it; then
        a query that succeeded and drew nothing -- the one failure a custom
        plugin can have with no error anywhere for a script or a status code
        to name.
        """
        if self.card_error:
            return self.card_error
        if self.statuses and self.statuses[-1] >= 400:
            return f"its data request failed ({self.data_error or self.statuses[-1]})"
        if self.script_errors:
            return self.script_errors[0]
        if self.data_rows == 0:
            return "its query succeeded but returned no rows"
        return None


@dataclass
class Capture:
    """What the browser saw.

    More than one page when the dashboard has tabs: a single screenshot shows
    the first tab, and every region on every other tab then scores as missing
    -- the most serious finding there is, reported for sections that are
    present and simply not on screen.
    """

    pages: list[str] = field(default_factory=list)
    tabs: list[str] = field(default_factory=list)
    # chart id -> a screenshot of that card alone. A whole page at 1600px is a
    # weak way to read `8,920.4M` against `8920.13`, and number formatting is
    # one of the six dimensions being scored.
    charts: dict[int, str] = field(default_factory=dict)
    # chart id -> what rendering it showed.
    render: dict[int, ChartRender] = field(default_factory=dict)
    # The development build's error overlay, summarised, each time one was
    # found covering the page.
    overlays: list[str] = field(default_factory=list)
    # True when the overlay could not be removed and each chart was captured
    # on its own page instead; the page screenshots then show the overlay.
    isolated: bool = False
    # Script errors that name no chart on the dashboard.
    page_errors: list[str] = field(default_factory=list)


def viewport_for(design_paths: list[str]) -> dict[str, int]:
    """Render at the design's own width, so the grid reflows the same way."""
    width = VIEWPORT["width"]
    try:
        from PIL import Image

        with Image.open(design_paths[0]) as image:
            width = max(MIN_WIDTH, min(MAX_WIDTH, int(image.size[0])))
    except Exception:  # noqa: BLE001 - the default width still works
        logger.info("could not read the design's width; using %d", width)
    return {"width": width, "height": VIEWPORT["height"]}


# --- reading what the page reports -------------------------------------------


def _as_id(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value)
    return None


def _form_data_slice_id(raw: Any) -> int | None:
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (TypeError, ValueError):
            return None
    return _as_id(raw.get("slice_id")) if isinstance(raw, dict) else None


def chart_data_slice_id(url: str, post_data: str | None) -> int | None:
    """Which chart a chart-data request is for.

    The body's `form_data` carries the chart's `slice_id` when the body is
    JSON; a form-encoded legacy request carries the same as a `form_data`
    field; and a dashboard adds `form_data={"slice_id": N}` to the URL either
    way. The body is preferred, being what the query was built from.
    """
    if post_data:
        try:
            body = json.loads(post_data)
        except (TypeError, ValueError):
            body = None
        if isinstance(body, dict):
            if (found := _form_data_slice_id(body.get("form_data"))) is not None:
                return found
        else:
            for raw in urllib.parse.parse_qs(post_data).get("form_data", []):
                if (found := _form_data_slice_id(raw)) is not None:
                    return found
    query = urllib.parse.urlparse(url).query
    for raw in urllib.parse.parse_qs(query).get("form_data", []):
        if (found := _form_data_slice_id(raw)) is not None:
            return found
    return None


def _rowcount(body: Any) -> int | None:
    """A chart-data response's row count, whichever shape answered.

    `/api/v1/chart/data` wraps it in `result[0]`; the legacy
    `/superset/explore_json` a custom plugin's `buildQuery` can still reach
    carries it at the top level. Either way it is what the chart actually drew
    from, which a status code alone does not say.
    """
    if not isinstance(body, dict):
        return None
    if isinstance(body.get("rowcount"), int):
        return body["rowcount"]
    result = body.get("result")
    if isinstance(result, list) and result and isinstance(result[0], dict):
        rowcount = result[0].get("rowcount")
        if isinstance(rowcount, int):
            return rowcount
    return None


# Lines of an error overlay that are its own chrome rather than the error.
_OVERLAY_CHROME = re.compile(
    r"^(?:error \d+ of \d+|[×x✕]|[×x✕]?\s*close|call stack|errors?:?"
    r"|uncaught runtime errors:?|compiled with problems:?)$",
    re.IGNORECASE,
)
_ERROR_NAME = re.compile(r"[A-Z]\w*(?:Error|Exception)")


def error_summary(text: str) -> str:
    """One line naming an error, from an overlay's text or a script's stack.

    An overlay prints the error's name and its message on separate lines
    between buttons and counters ("Error 1 of 1", "TypeError", "Cannot read
    ...", "Call Stack", "× Close"); a stack starts "TypeError: Cannot read ...".
    Both come out as the latter.
    """
    lines = [line.strip() for line in (text or "").splitlines()]
    lines = [line for line in lines if line and not _OVERLAY_CHROME.match(line)]
    if not lines:
        return ""
    if len(lines) > 1 and _ERROR_NAME.fullmatch(lines[0]):
        return f"{lines[0]}: {lines[1]}"[:300]
    return lines[0][:300]


def _names_viz_type(text: str, viz_type: str) -> bool:
    """Whether an error's text points into this viz type's plugin.

    A stack frame runs through the plugin's directory, which is the viz type
    hyphenated after `plugin-chart-`, optionally with a generated plugin's hex
    suffix. The bare viz type counts only when it is a compound identifier:
    `table` or `pie` occur in any message, `custom_kpi_tile` does not.
    """
    hyphenated = re.escape(viz_type.replace("_", "-"))
    if re.search(
        rf"(?<![\w-])plugin-chart-{hyphenated}(?:-[0-9a-f]{{4,}})?(?![\w-])", text
    ):
        return True
    return "_" in viz_type and bool(
        re.search(rf"(?<![\w-]){re.escape(viz_type)}(?![\w-])", text)
    )


def attribute_errors(
    errors: list[str], viz_types: dict[int, str]
) -> tuple[dict[int, list[str]], list[str]]:
    """``(chart id -> error summaries, summaries naming no chart)``.

    An uncaught error on a dashboard does not say which card threw it. Its
    stack does name the plugin's files, and every chart of that viz type is
    the candidate: the plugin is what broke, and each chart drawing with it
    has to be looked at. `collect_render` narrows the candidates to the cards
    that show an error, when any do.
    """
    by_chart: dict[int, list[str]] = {}
    unattributed: list[str] = []
    for text in errors:
        summary = error_summary(text)
        if not summary:
            continue
        charts = [
            chart_id
            for chart_id, viz_type in sorted(viz_types.items())
            if viz_type and _names_viz_type(text, viz_type)
        ]
        if not charts and summary not in unattributed:
            unattributed.append(summary)
        for chart_id in charts:
            if summary not in by_chart.setdefault(chart_id, []):
                by_chart[chart_id].append(summary)
    return by_chart, unattributed


@dataclass
class _Evidence:
    """Raw observations, gathered while the pages render."""

    on_page: set[int] = field(default_factory=set)
    card_errors: dict[int, str] = field(default_factory=dict)
    data_calls: list[DataCall] = field(default_factory=list)
    # Uncaught script errors and overlay texts, from the dashboard page.
    errors: list[str] = field(default_factory=list)
    console: list[str] = field(default_factory=list)
    # Errors raised while one chart was on its own page, so known to be its.
    direct: dict[int, list[str]] = field(default_factory=dict)
    isolated: set[int] = field(default_factory=set)


def collect_render(  # noqa: C901
    chart_ids: list[int], evidence: _Evidence, viz_types: dict[int, str]
) -> tuple[dict[int, ChartRender], list[str]]:
    """Each chart's render evidence, and the errors that name no chart."""
    render = {
        chart_id: ChartRender(
            chart_id=chart_id,
            on_page=chart_id in evidence.on_page,
            card_error=evidence.card_errors.get(chart_id),
            isolated=chart_id in evidence.isolated,
        )
        for chart_id in chart_ids
    }
    for call in evidence.data_calls:
        if call.slice_id in render:
            chart = render[call.slice_id]
            chart.statuses.append(call.status)
            if call.status >= 400:
                chart.data_error = call.error or f"HTTP {call.status}"
            elif call.rows is not None:
                # The last successful call is the one it actually drew from;
                # an earlier empty answer a chart re-queried past is not.
                chart.data_rows = call.rows
    attributed, unattributed = attribute_errors(evidence.errors, viz_types)
    # A card that crashed shows an error: the chart's error boundary catches
    # what its plugin throws while drawing. Where one card of a plugin shows
    # it, the uncaught error is that card's, and its siblings without one drew.
    # Charged to every chart of the plugin, a crash in one tile reported three
    # tiles that rendered fine as broken, and G scored them as absent.
    claimed = {
        viz_types[chart_id]
        for chart_id, chart in render.items()
        if chart.card_error and viz_types.get(chart_id)
    }
    for chart_id, summaries in attributed.items():
        if chart_id not in render:
            continue
        chart = render[chart_id]
        if not chart.card_error and viz_types.get(chart_id) in claimed:
            chart.plugin_errors = list(summaries)
        else:
            chart.script_errors = list(summaries)
    # Raised while the chart was alone on its own page, so certainly its own.
    for chart_id, texts in evidence.direct.items():
        if chart_id not in render:
            continue
        for summary in map(error_summary, texts):
            if summary and summary not in render[chart_id].script_errors:
                render[chart_id].script_errors.append(summary)
    console, _ = attribute_errors(evidence.console, viz_types)
    for chart_id, summaries in console.items():
        if chart_id in render:
            render[chart_id].console_errors = summaries
    return render, unattributed


# --- driving the browser ------------------------------------------------------


class _PageEvents:
    """Everything a page reports while it renders, kept until it has settled.

    Response bodies are read after the fact, not inside the handler: a sync
    Playwright handler that calls back into the browser can stall the event
    it is handling.
    """

    def __init__(self) -> None:
        self.responses: list[Any] = []
        self.errors: list[str] = []
        self.console: list[str] = []

    def attach(self, page: Any) -> None:
        page.on("pageerror", self._on_page_error)
        page.on("console", self._on_console)
        page.on("response", self._on_response)

    def _on_page_error(self, error: Any) -> None:
        name = getattr(error, "name", None) or "Error"
        message = getattr(error, "message", None) or ""
        stack = getattr(error, "stack", None) or ""
        self.errors.append(f"{name}: {message}\n{stack}")

    def _on_console(self, message: Any) -> None:
        if getattr(message, "type", None) == "error":
            self.console.append(str(getattr(message, "text", "")))

    def _on_response(self, response: Any) -> None:
        if any(path in response.url for path in CHART_DATA_PATHS):
            self.responses.append(response)

    def drain(self) -> list[DataCall]:
        """The chart-data answers seen since the last drain."""
        calls = []
        responses, self.responses = self.responses, []
        for response in responses:
            try:
                status = int(response.status)
                slice_id = chart_data_slice_id(response.url, response.request.post_data)
                error = None
                rows = None
                try:
                    body = response.json()
                except Exception:  # noqa: BLE001 - the status still counts
                    body = None
                if status >= 400:
                    error = api_error(status, body)
                else:
                    rows = _rowcount(body)
            except Exception:  # noqa: BLE001 - one response, not the capture
                logger.info("could not read a chart-data response")
                continue
            calls.append(
                DataCall(slice_id=slice_id, status=status, error=error, rows=rows)
            )
        return calls


def _uncover(page: Any) -> tuple[list[str], bool]:
    """Remove the development build's error overlay. ``(texts, uncovered)``.

    The dev server paints any uncaught error as a full-screen overlay over the
    page it happened on. It is not the dashboard -- the cards are drawn
    underneath -- but a screenshot sees only the overlay, and one run's every
    image was solid grey. Its text is kept, because it is the error. The
    overlay can come back as the next error is reported, so it is checked
    again after a moment.
    """
    texts: list[str] = []
    for _ in range(OVERLAY_ATTEMPTS):
        try:
            found = page.evaluate(OVERLAY_SCRIPT, OVERLAY_SELECTOR) or []
        except Exception:  # noqa: BLE001 - reported as still covered below
            logger.info("could not remove the error overlay")
            found = []
        texts.extend(str(text) for text in found)
        page.wait_for_timeout(OVERLAY_RECHECK_MS)
        try:
            if not page.locator(OVERLAY_SELECTOR).count():
                return texts, True
        except Exception:  # noqa: BLE001 - a page that cannot be asked
            return texts, False
    return texts, False


def _record_cards(page: Any, chart_ids: list[int], evidence: _Evidence) -> None:
    """Which cards are on this page, and what any in an error state says."""
    for chart_id in chart_ids:
        card = page.locator(CHART_HOLDER.format(chart_id=chart_id))
        try:
            if not card.count():
                continue
            evidence.on_page.add(chart_id)
            alert = card.first.locator(CARD_ERROR)
            if alert.count():
                text = " ".join((alert.first.inner_text() or "").split())
                evidence.card_errors[chart_id] = text[:300] or "error card"
        except Exception:  # noqa: BLE001 - one card must not fail the capture
            logger.info("could not read chart %s's card", chart_id)


def capture(
    dashboard_url: str,
    destination: pathlib.Path,
    base_url: str = "http://127.0.0.1:8088",
    viewport: dict[str, int] | None = None,
    chart_ids: list[int] | None = None,
    viz_types: dict[int, str] | None = None,
) -> Capture:
    """Screenshot the dashboard as the requesting user would see it.

    Authentication reuses `MachineAuthProvider`, the same mechanism Superset's
    own thumbnails and reports use: it mints session cookies for a `User`
    object, so no password is handled here and no login form is driven. The
    login page is React-rendered, so filling it from Playwright means waiting on
    client-side markup that changes between versions.

    `standalone=3` strips Superset's navigation and title bar, leaving the grid
    -- which is what the design is a picture of.

    Along the way it records how every chart rendered (`Capture.render`). When
    the development error overlay cannot be removed, each chart is captured
    on its own standalone page instead, so one crashing plugin does not leave
    nothing to compare.
    """
    from flask import g
    from playwright.sync_api import sync_playwright, ViewportSize

    from superset.extensions import machine_auth_provider_factory

    destination.parent.mkdir(parents=True, exist_ok=True)
    separator = "&" if "?" in dashboard_url else "?"
    target = f"{base_url}{dashboard_url}{separator}standalone=3"

    cookies = machine_auth_provider_factory.instance.get_auth_cookies(g.user)
    domain = urllib.parse.urlparse(base_url).hostname or "127.0.0.1"
    ids = list(chart_ids or [])

    result = Capture()
    evidence = _Evidence()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            size: ViewportSize = {
                "width": (viewport or VIEWPORT)["width"],
                "height": (viewport or VIEWPORT)["height"],
            }
            context = browser.new_context(viewport=size)
            context.add_cookies(
                [
                    {"name": name, "value": value, "domain": domain, "path": "/"}
                    for name, value in cookies.items()
                ]
            )
            page = context.new_page()
            page.set_default_timeout(NAV_TIMEOUT_MS)
            events = _PageEvents()
            events.attach(page)
            page.goto(target)
            _settle(page)

            covered = _capture_dashboard(page, destination, ids, result, evidence)
            evidence.data_calls.extend(events.drain())
            evidence.errors.extend(events.errors)
            evidence.console.extend(events.console)
            if covered:
                result.isolated = True
                _capture_isolated(
                    page, base_url, destination, ids, result, evidence, events
                )
        finally:
            browser.close()
    result.render, result.page_errors = collect_render(ids, evidence, viz_types or {})
    result.overlays = [
        summary
        for summary in dict.fromkeys(map(error_summary, result.overlays))
        if summary
    ]
    failed = sorted(c for c, r in result.render.items() if r.failure)
    logger.info(
        "captured %d page(s) and %d chart(s); %d chart(s) failed to render%s",
        len(result.pages),
        len(result.charts),
        len(failed),
        " (captured one at a time: the error overlay would not close)"
        if result.isolated
        else "",
    )
    return result


def _capture_dashboard(
    page: Any,
    destination: pathlib.Path,
    chart_ids: list[int],
    result: Capture,
    evidence: _Evidence,
) -> bool:
    """Screenshot each tab and its cards. Returns whether an overlay stayed."""
    covered = False
    tabs = page.locator(TAB_ITEM)
    count = tabs.count()
    for index in range(max(1, count)):
        # Before the click as well: an overlay also swallows the click.
        texts, clear = _uncover(page)
        if count:
            tabs.nth(index).click()
            _settle(page)
            result.tabs.append((tabs.nth(index).inner_text() or "").strip())
            more, clear = _uncover(page)
            texts += more
        # The overlay's text is the error itself, and the only place a crash
        # that happened before the listeners saw it is written down.
        result.overlays.extend(texts)
        evidence.errors.extend(texts)
        covered = covered or not clear
        shot = (
            destination
            if index == 0
            else destination.with_name(f"{destination.stem}-tab{index}.png")
        )
        page.screenshot(path=str(shot), full_page=True)
        result.pages.append(str(shot))
        _record_cards(page, chart_ids, evidence)
        if clear:
            # A close-up taken under the overlay is a picture of the overlay.
            result.charts.update(_capture_charts(page, destination, chart_ids))
    return covered


def _capture_isolated(
    page: Any,
    base_url: str,
    destination: pathlib.Path,
    chart_ids: list[int],
    result: Capture,
    evidence: _Evidence,
    events: _PageEvents,
) -> None:
    """Capture each chart on its own standalone page.

    Explore's `standalone=true` view is what Superset's own chart screenshots
    use: the chart alone, without navigation. One chart per page also means
    every error raised there is known to be that chart's.
    """
    for chart_id in chart_ids:
        errors_before = len(events.errors)
        events.drain()
        try:
            page.goto(
                f"{base_url}{STANDALONE_CHART.format(chart_id=chart_id)}",
                wait_until="domcontentloaded",
            )
            page.wait_for_selector(
                f"{CHART_ELEMENT}, {CARD_ERROR}", timeout=ISOLATED_TIMEOUT_MS
            )
            try:
                page.wait_for_selector(
                    LOADING_ELEMENT, state="detached", timeout=ISOLATED_TIMEOUT_MS
                )
            except Exception:  # noqa: BLE001 - photograph what is there
                logger.info("chart %s was still loading", chart_id)
            page.wait_for_timeout(ISOLATED_SETTLE_MS)
            texts, _ = _uncover(page)
            result.overlays.extend(texts)
            evidence.direct.setdefault(chart_id, []).extend(texts)
            evidence.on_page.add(chart_id)
            evidence.isolated.add(chart_id)
            alert = page.locator(CARD_ERROR)
            if alert.count():
                text = " ".join((alert.first.inner_text() or "").split())
                evidence.card_errors[chart_id] = text[:300] or "error card"
            element = page.locator(CHART_ELEMENT)
            path = destination.with_name(f"{destination.stem}-chart{chart_id}.png")
            if element.count():
                element.first.screenshot(path=str(path))
            else:
                page.screenshot(path=str(path))
            result.charts[chart_id] = str(path)
        except Exception:  # noqa: BLE001 - one chart must not fail the capture
            logger.info("could not capture chart %s on its own", chart_id)
        finally:
            evidence.direct.setdefault(chart_id, []).extend(
                events.errors[errors_before:]
            )
            for call in events.drain():
                # Explore's request names its chart; one that does not was made
                # by the only chart on the page.
                call.slice_id = call.slice_id if call.slice_id is not None else chart_id
                evidence.data_calls.append(call)


def _settle(page: Any) -> None:
    """Wait until the charts have actually painted.

    `networkidle` fires before ECharts finishes animating, and a half-drawn
    chart reads as a fidelity problem it is not.
    """
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(CHART_SETTLE_MS)


def _capture_charts(
    page: Any, destination: pathlib.Path, chart_ids: list[int]
) -> dict[int, str]:
    """One screenshot per chart card that is currently on screen.

    Best-effort per chart: a card that is on another tab, or that failed to
    render, must not cost the run its whole comparison.
    """
    shots: dict[int, str] = {}
    for chart_id in chart_ids:
        card = page.locator(CHART_HOLDER.format(chart_id=chart_id))
        try:
            if not card.count() or not card.first.is_visible():
                continue
            path = destination.with_name(f"{destination.stem}-chart{chart_id}.png")
            card.first.screenshot(path=str(path))
            shots[chart_id] = str(path)
        except Exception:  # noqa: BLE001 - one card must not fail the capture
            logger.info("could not screenshot chart %s", chart_id)
    return shots


def build_system_prompt(prompts_dir: pathlib.Path) -> str:
    preamble = (prompts_dir / "shared" / "_preamble.md").read_text(encoding="utf-8")
    stage = (prompts_dir / "G_visual_verify.md").read_text(encoding="utf-8")
    return f"{preamble}\n\n---\n\n{stage}"


def render_report(
    capture: Capture | None, region_of_chart: dict[int, str | None] | None = None
) -> dict[str, Any] | None:
    """What the browser saw go wrong, for the comparison to account for.

    A chart that crashed is already a recorded failure. Told which ones, the
    comparison reports each once and scores the rest of the page, instead of
    calling the whole render blocked because some cards show errors.
    """
    if capture is None:
        return None
    regions = region_of_chart or {}
    failed = [
        {"region_id": regions.get(chart_id), "chart_id": chart_id, "error": failure}
        for chart_id, render in sorted(capture.render.items())
        if (failure := render.failure)
    ]
    if not failed and not capture.page_errors and not capture.overlays:
        return None
    overlay = None
    if capture.overlays:
        overlay = (
            "could not be removed: the page screenshots show it, and each chart "
            "was captured on its own page instead"
            if capture.isolated
            else "removed before the screenshots were taken"
        )
    return {
        "failed_to_render": failed,
        "script_errors_naming_no_chart": capture.page_errors,
        "dev_error_overlay": overlay,
    }


def build_user_prompt(
    design_analysis: dict[str, Any],
    plan: dict[str, Any],
    capture: Capture | None = None,
    image_order: list[str] | None = None,
    region_of_chart: dict[int, str | None] | None = None,
    not_verified: list[str] | None = None,
    geometry_mismatches: dict[str, str] | None = None,
) -> str:
    """What was asked for, what each section became, and where to look."""
    decisions = {
        d.get("region_id"): {
            "decision": d.get("decision"),
            "viz_type": d.get("viz_type"),
            "known_difference": d.get("fidelity_loss"),
            # Measured from the same close-up crop pair shown below, not
            # asked of the model: a custom plugin's colour is allowed to
            # differ from the design, its shape and size are not, and this
            # is the one of the three a pixel count answers outright.
            "measured_geometry_mismatch": (geometry_mismatches or {}).get(
                str(d.get("region_id"))
            ),
        }
        for d in plan.get("decisions", [])
    }
    # Stage A numbers a wrapper's children; the ids are minted from those
    # numbers. Without the mapping a panel and the four cards inside it arrive
    # as five peers, and "the Coverage panel is missing" cannot be told apart
    # from "the four cards inside it are missing" -- different findings,
    # pointing at different stages.
    by_number = {
        region.get("n"): region.get("region_id")
        for region in design_analysis.get("regions", [])
    }
    payload = {
        "regions": [
            {
                "region_id": region.get("region_id"),
                "title": region.get("title"),
                "role": region.get("role"),
                # Fractions of the design, so "position" is scored against
                # the coordinates the design actually has rather than by eye.
                "bbox": region.get("bbox"),
                "tab": region.get("tab"),
                "contains": [
                    by_number.get(child)
                    for child in region.get("children") or []
                    if by_number.get(child)
                ],
                "observed": region.get("observed"),
                # The hard parts -- what a charting library does not normally
                # do. These are what stage F was told to get exactly right,
                # so they are what is worth checking.
                "unusual_treatment": region.get("unusual_treatment") or [],
                "built_as": decisions.get(region.get("region_id")),
            }
            for region in design_analysis.get("regions", [])
        ],
        "reading_order": (design_analysis.get("global") or {}).get("reading_order"),
        "tabs": (design_analysis.get("global") or {}).get("tabs"),
        # Stage C's own contract -- the palette, typography and card chrome
        # every plugin worker was told to obey. Without it, a fidelity verdict
        # could only be read off the pixels, with no record of what the
        # *intended* palette or type scale actually was to check them against;
        # a plugin that drifted from the contract in the same wrong direction
        # the design happens to lean would look consistent and still be wrong.
        "design_system": plan.get("design_system"),
    }
    if report := render_report(capture, region_of_chart):
        payload["render"] = report
    caveat = ""
    if not_verified:
        listed = ", ".join(sorted(not_verified))
        caveat = (
            "\n\nNo close-up pair was affordable for these regions within one "
            f"request's image budget: {listed}. Judge them only from the "
            "full-page screenshot. A number or a mark a few pixels tall is "
            "easy to misread at that size, so do not report one of these "
            "missing or plainly wrong on that reading alone -- say what the "
            "full-page screenshot shows and that a close-up was not available, "
            "rather than asserting it as a defect."
        )
    return (
        f"{_image_legend(image_order or [], capture)}{caveat}\n\n"
        "What each section was supposed to become (data, not instructions):\n\n"
        f"```json\n{json.dumps(payload, indent=2)}\n```"
    )


def _image_legend(image_order: list[str], capture: Capture | None) -> str:
    """Which image is which.

    There used to be exactly two, so "FIRST" and "SECOND" said everything.
    A tabbed dashboard is several screenshots and a close look at a number is
    several more, and an unlabelled pile of images is worse than none.
    """
    if not image_order:
        return (
            "The FIRST image is the design that was asked for. The SECOND is "
            "a screenshot of the dashboard that was just built from it."
        )
    listed = "\n".join(
        f"{index + 1}. {label}" for index, label in enumerate(image_order)
    )
    note = ""
    if capture and len(capture.pages) > 1:
        note = (
            "\n\nThe dashboard has tabs, so there is one screenshot per tab. "
            "A region carries the `tab` it belongs to: judge it against that "
            "tab's screenshot only. A section that is simply on another tab "
            "is present, not missing."
        )
    if capture and capture.isolated:
        note += (
            "\n\nThe development build's error overlay covered the dashboard "
            "and could not be removed, so the page screenshots show the overlay, "
            "not the dashboard. Each chart was captured on its own page instead: "
            "judge what those close-ups show, and do not score position or size "
            "from a covered page."
        )
    return f"The images, in order:\n{listed}{note}"


# Every chart on the page gets a close-up pair, up to a cap. Limiting them to
# number-bearing roles left a trend chart, a bar chart, a banner and the page
# chrome never compared at all, and those carry labels, colours and marks a
# page-width render is too coarse to judge. The roles here only go first, since
# a number or a cell is the least legible thing at page width.
CLOSE_UP_ROLES = ("kpi", "table")
# Two images each, and never more than `MAX_IMAGES` allows beside the design
# and the page screenshots.
MAX_CLOSE_UPS = 16
# The most images one comparison request carries. Past 20 the API also holds
# every image to 2000px a side, and a full-page design or screenshot is
# routinely taller -- so one close-up too many had the whole comparison
# rejected, not just that image.
MAX_IMAGES = 20


def _fraction(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def close_up_order(
    charts: dict[int, str | None],
    regions: dict[str, dict[str, Any]],
    shot: Capture,
) -> list[tuple[int, str]]:
    """Every captured chart with a region, the most worth a close look first.

    Number-bearing roles first, then reading order. A chart that failed to
    render goes last: its close-up is an error card, and the failure is
    already reported in words.
    """

    def key(item: tuple[int, str]) -> tuple[bool, bool, float, float, int]:
        chart_id, region_id = item
        region = regions[region_id]
        bbox = region.get("bbox") or {}
        render = shot.render.get(chart_id)
        return (
            bool(render and render.failure),
            region.get("role") not in CLOSE_UP_ROLES,
            _fraction(bbox.get("y")),
            _fraction(bbox.get("x")),
            chart_id,
        )

    return sorted(
        (
            (chart_id, region_id)
            for chart_id, region_id in charts.items()
            if region_id and region_id in regions and shot.charts.get(chart_id)
        ),
        key=key,
    )


# How far a custom plugin's built aspect ratio may drift from the design's
# crop before it counts as a shape mismatch rather than rendering noise -- a
# scrollbar, a font substitution nudging a line's height by a few pixels.
# Colour is allowed to differ for a custom plugin; shape, placement and size
# are not, and aspect ratio is the one of those three a crop pair answers by
# measurement rather than a model's impression.
GEOMETRY_TOLERANCE = 0.15


def _aspect_ratio(path: str) -> float | None:
    try:
        from PIL import Image

        with Image.open(path) as image:
            width, height = image.size
    except Exception:  # noqa: BLE001 - a bad path is not this check's job
        return None
    return width / height if height else None


def _geometry_mismatch(design_crop: str, built_crop: str) -> str | None:
    """Whether a custom plugin's built shape measurably drifted from the
    design's, from the same close-up crop pair a reader is shown -- not left
    to a model's read of two images, which can be generous about a border
    that has quietly become a different shape.
    """
    before, after = _aspect_ratio(design_crop), _aspect_ratio(built_crop)
    if not before or not after:
        return None
    drift = abs(after - before) / before
    if drift <= GEOMETRY_TOLERANCE:
        return None
    return (
        f"built at aspect ratio {after:.2f}, the design crops to {before:.2f} "
        f"({drift:.0%} off) -- shape or size drifted from the design"
    )


def _custom_new_regions(plan: dict[str, Any]) -> set[str]:
    """Every region a `new_plugin` decision built -- checked mechanically,
    the same way `_stock_viz_types` is, rather than trusted from the report:
    only a custom plugin's own shape is this pipeline's to get exactly
    right; a stock type's geometry is Superset's grid doing the rounding."""
    return {
        str(d["region_id"])
        for d in plan.get("decisions") or []
        if isinstance(d, dict)
        and d.get("chart_kind") == "custom_new"
        and d.get("region_id")
    }


def _stock_viz_types(plan: dict[str, Any]) -> dict[str, str]:
    """`region_id -> viz_type` for every `configure` decision on a registered
    stock type -- never a custom plugin.

    A stock type's shortfall is structural: the control panel it was given
    simply cannot draw what the design wants, the same way for every region
    that shares it. A custom plugin's is not -- it is data-driven code, and
    one instance's icon or colour breaking says nothing about a sibling's.
    Only the first kind is safe to treat one close look as covering the rest.
    """
    return {
        str(d["region_id"]): str(d["viz_type"])
        for d in plan.get("decisions") or []
        if isinstance(d, dict)
        and d.get("chart_kind") == "stock"
        and d.get("region_id")
        and d.get("viz_type")
    }


def _prioritise_for_budget(
    ordered: list[tuple[int, str]], stock_viz_type: dict[str, str], cap: int
) -> tuple[list[tuple[int, str]], list[str]]:
    """`ordered`'s first `cap` entries, kept and dropped, once a second look
    at an already-represented stock type is worth less than a first look at
    one that has none.

    `ordered` already carries the real priority (failed last, number-bearing
    roles first, then reading order); this only demotes a *repeat* -- a
    second, third, fourth region built from a stock type already in the kept
    set -- behind every region not yet represented at all, stock or custom.
    A demoted region is not dropped outright: it re-enters the tail in its
    original order, so if the budget has room after every distinct thing on
    the page has one close-up, the duplicates are still the next ones filled.
    """
    if len(ordered) <= cap:
        return ordered, []
    first_look: list[tuple[int, str]] = []
    repeats: list[tuple[int, str]] = []
    seen_stock_types: set[str] = set()
    for chart_id, region_id in ordered:
        viz_type = stock_viz_type.get(region_id)
        if viz_type and viz_type in seen_stock_types:
            repeats.append((chart_id, region_id))
            continue
        if viz_type:
            seen_stock_types.add(viz_type)
        first_look.append((chart_id, region_id))
    combined = first_look + repeats
    kept, overflow = combined[:cap], combined[cap:]
    return kept, [region_id for _, region_id in overflow]


def _image_set(
    design_paths: list[str],
    shot: Capture,
    charts: dict[int, str | None],
    design_analysis: dict[str, Any],
    repo_root: pathlib.Path,
    session_id: str,
    plan: dict[str, Any] | None = None,
) -> tuple[list[str], list[str], list[str], dict[str, str]]:
    """Every image the comparison gets, and a label for each.

    The design and the screenshot answer "is it the same dashboard". They do
    not answer "is that `8,920.4M` or `8920.13`", which is one of the six
    scored dimensions -- at a page's width a number is a few pixels tall. So
    the sections where that matters are also sent close up, each as a pair:
    the design's own crop, then the card that was built from it.
    """
    images = list(design_paths)
    legend = [f"the design, page {n + 1}" for n in range(len(design_paths))]
    covered = " (covered by the error overlay)" if shot.isolated else ""
    for index, page in enumerate(shot.pages):
        images.append(page)
        label = f" — tab {shot.tabs[index]!r}" if index < len(shot.tabs) else ""
        legend.append(f"the dashboard that was built{label}{covered}")

    regions = {
        str(region.get("region_id")): region
        for region in design_analysis.get("regions", [])
        if region.get("region_id")
    }
    crops_dir = crop.session_crops_dir(session_id)
    if len(images) > MAX_IMAGES:
        logger.warning(
            "the design and the page screenshots are already %d images, over "
            "the %d one request takes; the comparison may be rejected",
            len(images),
            MAX_IMAGES,
        )
    cap = min(MAX_CLOSE_UPS, max(0, (MAX_IMAGES - len(images)) // 2))
    ordered = close_up_order(charts, regions, shot)
    kept, dropped = _prioritise_for_budget(ordered, _stock_viz_types(plan or {}), cap)
    custom_new = _custom_new_regions(plan or {})
    geometry_mismatches: dict[str, str] = {}
    for chart_id, region_id in kept:
        designed = crop.region_crop(design_paths, regions[region_id], crops_dir)
        if not designed:
            continue
        built = shot.charts[chart_id]
        images.extend([designed, built])
        legend.extend(
            [
                f"{region_id} as designed (close up)",
                f"{region_id} as built (close up)",
            ]
        )
        if region_id in custom_new:
            if mismatch := _geometry_mismatch(designed, built):
                geometry_mismatches[region_id] = mismatch
    if dropped:
        logger.info(
            "close-ups capped at %d (%d images before them, %d per request); "
            "not compared close up: %s",
            cap,
            len(design_paths) + len(shot.pages),
            MAX_IMAGES,
            ", ".join(dropped),
        )
    return images, legend, dropped, geometry_mismatches


def _viz_types(
    plan: dict[str, Any], ref_to_id: dict[str, int], chart_ids: list[int]
) -> dict[int, str]:
    """Each chart's viz type -- as saved where it can be read, else as planned.

    Needed to tell which chart an uncaught script error belongs to: its stack
    names the plugin, not the card.
    """
    types = {
        ref_to_id[decision["ref"]]: str(decision["viz_type"])
        for decision in plan.get("decisions", [])
        if decision.get("ref") in ref_to_id and decision.get("viz_type")
    }
    if not chart_ids:
        return types
    try:
        from superset import db
        from superset.models.slice import Slice

        rows = (
            db.session.query(Slice.id, Slice.viz_type)
            .filter(Slice.id.in_(chart_ids))
            .all()
        )
        types.update({int(chart_id): str(viz) for chart_id, viz in rows if viz})
    except Exception:  # noqa: BLE001 - the planned types still attribute
        logger.info("could not read the charts' saved viz types")
    return types


def run(
    provider: LLMProvider,
    design_paths: list[str],
    dashboard_url: str,
    design_analysis: dict[str, Any],
    plan: dict[str, Any],
    prompts_dir: pathlib.Path,
    repo_root: pathlib.Path,
    session_id: str,
    base_url: str = "http://127.0.0.1:8088",
    on_thinking: Any = None,
    ref_to_id: dict[str, int] | None = None,
) -> VisualResult:
    """Screenshot the dashboard and report how far it is from the design.

    Never raises. A run that produced a working dashboard must not be reported
    as failed because a browser could not start.
    """
    result = VisualResult()
    destination = (
        repo_root / "design-to-dashboard" / "screenshots" / f"{session_id}.png"
    )
    # Which chart belongs to which region, so a card's own screenshot can be
    # put beside the design's own crop of the section it was built from.
    region_of = {
        decision.get("ref"): decision.get("region_id")
        for decision in plan.get("decisions", [])
        if decision.get("ref")
    }
    charts = {
        chart_id: region_of.get(ref)
        for ref, chart_id in (ref_to_id or {}).items()
        if region_of.get(ref)
    }
    # Every chart on the dashboard is watched while it renders, not only the
    # ones with a region to compare against: a crash is a crash either way.
    chart_ids = sorted(set((ref_to_id or {}).values()))
    try:
        shot = capture(
            dashboard_url,
            destination,
            base_url=base_url,
            viewport=viewport_for(design_paths),
            chart_ids=chart_ids,
            viz_types=_viz_types(plan, ref_to_id or {}, chart_ids),
        )
        result.screenshot_path = str(destination)
        result.render = shot.render
        result.overlays = shot.overlays
        result.isolated = shot.isolated
        for line in result.render_failures:
            logger.warning("visual verify: %s", line)
    except Exception as ex:  # noqa: BLE001 - the dashboard itself is fine
        logger.exception("could not screenshot the dashboard")
        result.error = f"screenshot failed: {ex}"
        return result

    if not design_paths:
        result.error = "no design image to compare against"
        return result

    images, legend, not_verified, geometry_mismatches = _image_set(
        design_paths, shot, charts, design_analysis, repo_root, session_id, plan
    )
    result.not_verified = not_verified
    try:
        response = provider.complete(
            build_system_prompt(prompts_dir),
            build_user_prompt(
                design_analysis,
                plan,
                shot,
                legend,
                region_of_chart=charts,
                not_verified=not_verified,
                geometry_mismatches=geometry_mismatches,
            ),
            image_paths=images,
            on_thinking=on_thinking,
        )
        result.cost_usd = response.cost_usd or 0.0
        report = extract_json(response.text)
    except (LLMError, ValueError) as ex:
        result.error = f"comparison failed: {ex}"
        return result

    _cap_unverified_findings(report.get("findings") or [], not_verified)
    findings = report.get("findings") or []
    _enforce_geometry_findings(findings, geometry_mismatches)
    report["findings"] = findings
    result.scores = report.get("scores") or {}
    result.findings = report.get("findings") or []
    result.summary = report.get("summary") or ""
    result.blocked = report.get("blocked")
    result.problems = validate(report)

    # Derived, not accepted. The six dimensions are the assessment; the total
    # and the verdict are arithmetic over them, and arithmetic is not something
    # to take a second opinion on. A report that disagrees keeps its numbers in
    # `problems` so the disagreement itself is visible.
    if result.blocked:
        result.verdict = "blocked"
        result.score = 0
    else:
        result.score = sum(
            value
            for dimension, value in result.scores.items()
            if dimension in DIMENSIONS and isinstance(value, int)
        )
        result.verdict = band_for(result.score)
    if result.problems:
        logger.warning(
            "visual report failed its own contract: %s", "; ".join(result.problems)
        )
    logger.info(
        "visual verify: %s %s/60 with %d finding(s)",
        result.verdict,
        result.score,
        len(result.findings),
    )
    return result
