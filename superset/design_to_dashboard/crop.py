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
"""Cut one section out of the design, so the stage building it can see it.

Stage A converts the design into English, and every stage that builds anything
worked only from that English: F wrote a plugin's markup and CSS, and E placed
the grid, without either having seen the picture. Fidelity was capped at
whatever survived a prose description -- a "light grey pill" has no radius, no
padding and no gap, so the stage writing the component invented all three.

A crop is the smallest fix that raises that cap: the region's own pixels, at
the moment the component for it is written.
"""

from __future__ import annotations

import logging
import pathlib
import tempfile
from typing import Any

logger = logging.getLogger(__name__)


def session_crops_dir(session_id: str) -> pathlib.Path:
    """Where one run's crops live.

    One definition, because the run writes them and the API serves them back
    to the browser; two spellings of the same path would fail as a missing
    image rather than as an error anyone could read.
    """
    return pathlib.Path(tempfile.gettempdir()) / "d2d" / session_id / "crops"


# A tight bounding box clips the card's own border and shadow, which is exactly
# the chrome the plugin has to reproduce.
MARGIN = 12
# Below this a crop carries no usable detail and is more likely a bad bbox.
MIN_SIDE = 24
# The outline drawn on a review crop. A warm accent rather than a theme colour:
# it has to read as an annotation against whatever the design's own palette is,
# and every dashboard palette in practice is blues and greys.
HIGHLIGHT_RGB = (233, 84, 32)
HIGHLIGHT_WIDTH = 3
# Review crops are shown in a side panel, not read for detail, and every one of
# them crosses the wire. A full-width band of a 1139px design is 1133px of PNG
# for no gain.
REVIEW_MAX_WIDTH = 560


def region_crop(
    image_paths: list[str],
    region: dict[str, Any],
    out_dir: pathlib.Path,
    highlight: bool = False,
    max_width: int | None = None,
) -> str | None:
    """Write the region's pixels to a PNG and return its path.

    Returns None whenever the crop cannot be trusted -- no box, a degenerate
    box, an unreadable image. The caller then runs as it always did, on the
    description alone, rather than on a misleading picture.

    ``highlight`` outlines where the region itself ends, since the crop carries
    a margin of its neighbours for context and a reviewer cannot otherwise tell
    the section from the bleed. ``max_width`` scales the result down; a review
    thumbnail does not need the design's full resolution.
    """
    bbox = region.get("bbox") or {}
    if not image_paths or not bbox:
        return None

    index = region.get("source_image") or 0
    if not 0 <= index < len(image_paths):
        index = 0

    try:
        from PIL import Image

        with Image.open(image_paths[index]) as image:
            width, height = image.size
            # Stage A reports fractions of the image, so the image's own size
            # is the only scale there is -- and it is right per image, which
            # matters when a scrolled capture is a different size to the first.
            left = int(float(bbox.get("x", 0)) * width) - MARGIN
            top = int(float(bbox.get("y", 0)) * height) - MARGIN
            right = left + int(float(bbox.get("w", 0)) * width) + 2 * MARGIN
            bottom = top + int(float(bbox.get("h", 0)) * height) + 2 * MARGIN
            box = (
                max(0, left),
                max(0, top),
                min(width, right),
                min(height, bottom),
            )
            if box[2] - box[0] < MIN_SIDE or box[3] - box[1] < MIN_SIDE:
                logger.info(
                    "crop for %s is %dx%d -- too small to be useful",
                    region.get("region_id"),
                    box[2] - box[0],
                    box[3] - box[1],
                )
                return None
            out_dir.mkdir(parents=True, exist_ok=True)
            destination = out_dir / f"{region.get('region_id', 'region')}.png"
            cropped = image.convert("RGB").crop(box)
            if highlight:
                _outline(cropped, box, (left, top, right, bottom))
            if max_width and cropped.width > max_width:
                ratio = max_width / cropped.width
                cropped = cropped.resize(
                    (max_width, max(1, round(cropped.height * ratio)))
                )
            cropped.save(destination)
    except Exception:  # noqa: BLE001 - a missing crop must never fail a run
        logger.exception("could not crop %s", region.get("region_id"))
        return None

    logger.info("cropped %s to %s", region.get("region_id"), destination)
    return str(destination)


def _outline(
    cropped: Any,
    box: tuple[int, int, int, int],
    region_px: tuple[int, int, int, int],
) -> None:
    """Draw the region's own edge onto the crop.

    ``region_px`` is the margin-inflated rectangle before clamping, so the
    region's true edge is one margin inside it. Subtracting the clamped
    origin keeps the outline correct for a section flush against the page
    edge, where the crop lost its margin on one side and a fixed inset would
    draw the line in the wrong place.
    """
    from PIL import ImageDraw

    left, top, right, bottom = region_px
    ImageDraw.Draw(cropped).rectangle(
        [
            (left + MARGIN - box[0], top + MARGIN - box[1]),
            (right - MARGIN - box[0] - 1, bottom - MARGIN - box[1] - 1),
        ],
        outline=HIGHLIGHT_RGB,
        width=HIGHLIGHT_WIDTH,
    )
