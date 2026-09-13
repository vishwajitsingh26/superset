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
"""The picture of every chart type stage C compares a design against.

Built at the start of every run, from the registry regenerated moments before.

The sheet used to be a committed image rebuilt by hand with headless Chrome,
and three things went wrong with it at once. It went stale: generated before
most custom plugins existed, so stage C could not see the plugins earlier runs
had built and built them again. Its height was a guess at tile size, so the
last row's names were cut off. And ten chart types showed "no preview" --
including the KPI, pivot table and filter types a dashboard design most often
needs -- because their pictures sat where the generator did not look.

What each tile shows, in order of preference:

  * **a stock chart's own example screenshot.** Every Superset plugin ships
    screenshots of itself rendering real data for the chart gallery; for the
    ECharts plugins that is ECharts drawing. It shows labels, legends and
    layout that the stylised thumbnail beside it leaves out.
  * **a custom plugin's thumbnail**, which is a photograph of the plugin itself
    once a dashboard using it has passed visual verification.
  * **the shipped thumbnail**, where there is nothing better.

A placeholder is never shown. The tile is named and says "no preview", because
a chart type missing from the sheet reads as one that does not exist, and a
placeholder drawn as a picture reads as evidence.
"""

from __future__ import annotations

import logging
import pathlib
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

COLUMNS = 6
CELL_WIDTH = 200
PICTURE_HEIGHT = 124
CAPTION_LINES = 3
LINE_HEIGHT = 15
PADDING = 8
GAP = 10
MARGIN = 16

# The file `plugin_writer` copies into every generated plugin so a build does
# not break. Compared byte for byte: several real illustrations are flat line
# art in a handful of colours, so no colour threshold can tell them apart.
PLACEHOLDER = "design-to-dashboard/assets/plugin-thumbnail-placeholder.png"


@dataclass
class Layout:
    """Where every tile goes, measured rather than guessed."""

    width: int
    height: int
    cell_height: int
    positions: list[tuple[int, int]] = field(default_factory=list)


def cell_height() -> int:
    """One tile: its picture, its caption lines, and the padding around both."""
    return PADDING + PICTURE_HEIGHT + 4 + CAPTION_LINES * LINE_HEIGHT + PADDING


def layout(count: int) -> Layout:
    """The sheet's size and each tile's top-left corner.

    Height comes from the same tile size the drawing uses. The old sheet
    computed it from a smaller one, and the ninth row fell off the bottom.
    """
    rows = max(1, (count + COLUMNS - 1) // COLUMNS)
    tile = cell_height()
    width = 2 * MARGIN + COLUMNS * CELL_WIDTH + (COLUMNS - 1) * GAP
    height = 2 * MARGIN + rows * tile + (rows - 1) * GAP
    positions = [
        (
            MARGIN + (index % COLUMNS) * (CELL_WIDTH + GAP),
            MARGIN + (index // COLUMNS) * (tile + GAP),
        )
        for index in range(count)
    ]
    return Layout(width=width, height=height, cell_height=tile, positions=positions)


def is_informative(path: pathlib.Path, placeholder: bytes | None) -> bool:
    """Whether this file shows something a chart type can be recognised by."""
    try:
        data = path.read_bytes()
    except OSError:
        return False
    if placeholder is not None and data == placeholder:
        return False
    try:
        from PIL import Image

        with Image.open(path) as image:
            colours = image.convert("RGB").getcolors(maxcolors=1_000_000)
    except Exception:  # noqa: BLE001 - unreadable is uninformative
        return False
    # One or two colours is a blank, whatever it was meant to be.
    return colours is None or len(colours) > 2


def best_picture(
    entry: dict[str, Any], repo_root: pathlib.Path, placeholder: bytes | None
) -> pathlib.Path | None:
    """The most telling picture of one chart type, read from disk now."""
    candidates: list[str] = []
    if not entry.get("custom"):
        candidates += [str(path) for path in entry.get("examples") or []]
    if entry.get("thumbnail"):
        candidates.append(str(entry["thumbnail"]))
    for relative in candidates:
        path = repo_root / relative
        if path.exists() and is_informative(path, placeholder):
            return path
    return None


def ordered(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Custom plugins first, the way the registry text lists them for stage C."""
    return sorted(
        entries,
        key=lambda entry: (not entry.get("custom"), str(entry.get("viz_type"))),
    )


def _fit(draw: Any, text: str, font: Any, width: int) -> str:
    """`text`, shortened with an ellipsis until it fits `width` pixels."""
    if draw.textlength(text, font=font) <= width:
        return text
    while text and draw.textlength(f"{text}…", font=font) > width:
        text = text[:-1]
    return f"{text}…"


def build(
    entries: list[dict[str, Any]], repo_root: pathlib.Path, out_path: pathlib.Path
) -> pathlib.Path | None:
    """Draw the sheet and return its path, or None if it could not be drawn.

    Never raises: a run without a sheet still resolves every region from the
    registry text, and losing that to a picture would be the wrong trade.
    """
    try:
        from PIL import Image, ImageDraw, ImageFont, ImageOps
    except ImportError:
        logger.warning("Pillow is not installed; no contact sheet this run")
        return None

    try:
        placeholder = (repo_root / PLACEHOLDER).read_bytes()
    except OSError:
        placeholder = None

    tiles = ordered(entries)
    geometry = layout(len(tiles))
    try:
        sheet = Image.new("RGB", (geometry.width, geometry.height), "white")
        draw = ImageDraw.Draw(sheet)
        bold = ImageFont.load_default(size=12)
        regular = ImageFont.load_default(size=11)
        text_width = CELL_WIDTH - 2 * PADDING
        for entry, (x, y) in zip(tiles, geometry.positions, strict=False):
            draw.rounded_rectangle(
                (x, y, x + CELL_WIDTH, y + geometry.cell_height),
                radius=6,
                outline="#d9d9d9",
                fill="white",
            )
            box = (x + PADDING, y + PADDING, text_width, PICTURE_HEIGHT)
            picture = best_picture(entry, repo_root, placeholder)
            badge = "custom" if entry.get("custom") else entry.get("category") or ""
            if picture is not None:
                with Image.open(picture) as source:
                    fitted = ImageOps.contain(source.convert("RGB"), box[2:])
                sheet.paste(
                    fitted,
                    (
                        box[0] + (box[2] - fitted.width) // 2,
                        box[1] + (box[3] - fitted.height) // 2,
                    ),
                )
            else:
                draw.rectangle(
                    (box[0], box[1], box[0] + box[2], box[1] + box[3]),
                    fill="#fafafa",
                    outline="#d9d9d9",
                )
                draw.text(
                    (box[0] + box[2] // 2, box[1] + box[3] // 2),
                    "no preview",
                    font=regular,
                    fill="#9a9a9a",
                    anchor="mm",
                )
                badge = f"{badge} · NO PREVIEW".strip(" ·")
            caption = box[1] + PICTURE_HEIGHT + 4
            for line, (text, font, colour) in enumerate(
                (
                    (str(entry.get("viz_type") or "?"), bold, "#111111"),
                    (str(entry.get("name") or ""), regular, "#333333"),
                    (badge, regular, "#8c8c8c"),
                )
            ):
                draw.text(
                    (box[0], caption + line * LINE_HEIGHT),
                    _fit(draw, text, font, text_width),
                    font=font,
                    fill=colour,
                )
        out_path.parent.mkdir(parents=True, exist_ok=True)
        sheet.save(out_path, optimize=True)
    except Exception:  # noqa: BLE001 - a missing picture never fails a run
        logger.exception("could not draw the contact sheet")
        return None
    return out_path
