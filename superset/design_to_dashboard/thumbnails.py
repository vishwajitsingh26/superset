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
"""Photograph a viz type by rendering a real chart of it.

Stage C picks between plugins by looking at their thumbnails, and a plugin's
shipped `thumbnail.png` is an illustration drawn by a designer -- where one
exists at all. A plugin this pipeline generates has no illustration, so
`plugin_writer` copies in a placeholder, and every generated plugin ends up
wearing the same picture. Asking a model to choose between eight identical
placeholders is asking it to guess, and the prompt then records the guess as
`thumbnail_evidence`.

A render of a real chart is the only exact answer: it is the component itself,
drawing data, through the same standalone view Superset's own chart thumbnails
use.
"""

from __future__ import annotations

import logging
import pathlib
import urllib.parse
from typing import Any

logger = logging.getLogger(__name__)

# Roughly a dashboard cell, because that is the shape a thumbnail stands for.
# Explore sizes the chart to the window, so a wide window photographs a chart
# nobody will ever see at that proportion.
VIEWPORT = {"width": 720, "height": 480}
# Explore's standalone view has no chart-holder padding, so a chart that fills
# its container paints flush to the window edge -- `big_number` puts its first
# digit on the border. A dashboard cell supplies that padding; adding it here
# photographs the chart as a dashboard will actually show it.
FRAME_CSS = """
  .chart-container, .slice_container { padding: 20px !important;
    box-sizing: border-box !important; background: transparent !important; }
"""
# The element Superset's own `ChartScreenshot` captures -- the chart alone,
# without Explore's panels.
CHART_ELEMENT = ".chart-container"
# Present while the chart is still fetching; its removal is the paint signal.
LOADING_ELEMENT = ".chart-container .loading"
# A chart that cannot query says so instead of drawing. Watching for this is
# what keeps one broken chart from spending the selector timeout.
ERROR_ELEMENT = ".ant-alert-error, [data-test='alert-container']"
# Long enough for a cold Explore page, short enough that a chart which will
# never draw does not eat the batch.
SELECTOR_TIMEOUT_MS = 45000
# Room around the chart, because several paint outside their own box.
PADDING = 24
# A resize reflows the chart; give it a moment before the shutter.
FRAME_SETTLE_MS = 1200
# ECharts animates after the network goes quiet; a half-drawn chart is a
# misleading photograph, not a slow one.
SETTLE_MS = 6000
NAV_TIMEOUT_MS = 60000


def _capture(page: Any, element: Any, destination: pathlib.Path) -> None:
    """Screenshot the chart with room around it.

    Not `element.screenshot()`: that captures the bounding box to the pixel,
    and several charts paint outside their own box -- `big_number` renders its
    value flush to the left edge and loses the first digit. Clipping the page
    around the box instead keeps whatever overflows, and keeps the chart off
    the edge of its own picture.
    """
    box = element.bounding_box()
    if not box:
        element.screenshot(path=str(destination))
        return
    viewport = page.viewport_size or VIEWPORT
    left = max(0, box["x"] - PADDING)
    top = max(0, box["y"] - PADDING)
    page.screenshot(
        path=str(destination),
        clip={
            "x": left,
            "y": top,
            "width": min(box["width"] + 2 * PADDING, viewport["width"] - left),
            "height": min(box["height"] + 2 * PADDING, viewport["height"] - top),
        },
    )


def charts_by_viz_type(
    viz_types: set[str] | None = None, registered: set[str] | None = None
) -> dict[str, int]:
    """One chart id per viz type, preferring the most recently touched.

    Only charts the run can actually open: a viz type nobody has ever made a
    chart of cannot be photographed, and is better left visibly absent than
    represented by a placeholder that reads as evidence.

    ``registered`` filters out charts whose plugin no longer exists. Those
    outlive the plugin that drew them -- a generated plugin's directory can be
    deleted while its charts stay in the database -- and they render "Data
    error: Empty query?" rather than a picture, after spending the full
    selector timeout getting there.
    """
    from superset import db
    from superset.models.slice import Slice

    query = db.session.query(Slice.viz_type, Slice.id).order_by(
        Slice.viz_type, Slice.changed_on.desc()
    )
    if viz_types:
        query = query.filter(Slice.viz_type.in_(viz_types))
    chosen: dict[str, int] = {}
    for viz_type, slice_id in query.all():
        if registered is not None and viz_type not in registered:
            continue
        chosen.setdefault(viz_type, int(slice_id))
    return chosen


def render(
    slice_ids: dict[str, int],
    out_dir: pathlib.Path,
    base_url: str = "http://127.0.0.1:8088",
) -> dict[str, str]:
    """Render each chart and return ``{viz_type: png path}``.

    One browser for the whole batch: launching chromium costs more than every
    screenshot in a run put together. A viz type whose chart fails to paint is
    left out rather than saved half-drawn -- the caller falls back to whatever
    the plugin shipped.

    Must run inside a request context with ``g.user`` set: cookies are minted
    for that user, so a chart they cannot read is never photographed.
    """
    if not slice_ids:
        return {}

    from flask import g
    from playwright.sync_api import sync_playwright

    from superset.extensions import machine_auth_provider_factory

    out_dir.mkdir(parents=True, exist_ok=True)
    cookies = machine_auth_provider_factory.instance.get_auth_cookies(g.user)
    domain = urllib.parse.urlparse(base_url).hostname or "127.0.0.1"
    rendered: dict[str, str] = {}

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            context = browser.new_context(viewport=VIEWPORT)
            context.add_cookies(
                [
                    {"name": name, "value": value, "domain": domain, "path": "/"}
                    for name, value in cookies.items()
                ]
            )
            page = context.new_page()
            page.set_default_timeout(NAV_TIMEOUT_MS)
            for viz_type, slice_id in sorted(slice_ids.items()):
                destination = out_dir / f"{viz_type}.png"
                try:
                    # `standalone=true` is what Superset's own ChartScreenshot
                    # uses: Explore without its navigation or control panels.
                    page.goto(
                        f"{base_url}/explore/?slice_id={slice_id}&standalone=true",
                        wait_until="domcontentloaded",
                    )
                    # Not `networkidle`: Superset holds connections open, so it
                    # can never fire, and waiting for it burns the whole
                    # navigation budget before the chart is ever looked for.
                    # Whichever appears first settles it -- a chart that cannot
                    # query shows an alert and never shows a container, so
                    # waiting only for the container pays the full timeout to
                    # learn nothing.
                    page.wait_for_selector(
                        f"{CHART_ELEMENT}, {ERROR_ELEMENT}",
                        timeout=SELECTOR_TIMEOUT_MS,
                    )
                    if page.locator(CHART_ELEMENT).count() == 0:
                        message = ""
                        if page.locator(ERROR_ELEMENT).count():
                            message = page.locator(ERROR_ELEMENT).first.inner_text()
                        logger.info(
                            "%s (chart %s) did not render: %s",
                            viz_type,
                            slice_id,
                            " ".join(message.split())[:120] or "no chart container",
                        )
                        continue
                    element = page.locator(CHART_ELEMENT).first
                    # The container appears while the chart is still loading;
                    # the spinner going away is what says it has drawn.
                    page.wait_for_selector(
                        LOADING_ELEMENT, state="detached", timeout=SELECTOR_TIMEOUT_MS
                    )
                    page.wait_for_timeout(SETTLE_MS)
                    # After the chart has drawn: adding it earlier changes the
                    # box the chart measures itself against.
                    page.add_style_tag(content=FRAME_CSS)
                    page.wait_for_timeout(FRAME_SETTLE_MS)
                    _capture(page, element, destination)
                except Exception:  # noqa: BLE001 - one bad chart, not a failed run
                    logger.exception("could not photograph %s", viz_type)
                    continue
                rendered[viz_type] = str(destination)
        finally:
            browser.close()

    logger.info("photographed %d/%d viz type(s)", len(rendered), len(slice_ids))
    return rendered


def adopt(rendered: dict[str, str], registry: list[dict[str, Any]]) -> list[str]:
    """Write each render over the plugin's own `thumbnail.png`.

    Superset reads that file for the chart-picker gallery, so a generated
    plugin stops showing a placeholder there too -- not only on the contact
    sheet this pipeline builds.
    """
    by_type = {entry.get("viz_type"): entry for entry in registry}
    adopted = []
    for viz_type, source in sorted(rendered.items()):
        entry = by_type.get(viz_type)
        thumbnail = entry.get("thumbnail") if entry else None
        if not thumbnail:
            continue
        try:
            pathlib.Path(thumbnail).write_bytes(pathlib.Path(source).read_bytes())
        except OSError:
            logger.exception("could not write the thumbnail for %s", viz_type)
            continue
        adopted.append(viz_type)
    return adopted
