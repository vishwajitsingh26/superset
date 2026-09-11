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
from typing import Any

logger = logging.getLogger(__name__)

# A tight bounding box clips the card's own border and shadow, which is exactly
# the chrome the plugin has to reproduce.
MARGIN = 12
# Below this a crop carries no usable detail and is more likely a bad bbox.
MIN_SIDE = 24


def _scale(canvas: dict[str, Any] | None, width: int, height: int) -> float:
    """How many image pixels to one design pixel.

    Stage A reports boxes in the design's own coordinates and the canvas they
    belong to. Usually that is the image's own size, but a design exported at
    2x would put every box at half the pixels it should be.
    """
    declared = float((canvas or {}).get("w") or 0)
    if declared <= 0:
        return 1.0
    ratio = width / declared
    # A canvas that disagrees wildly is a misread, not a scale factor.
    return ratio if 0.2 <= ratio <= 5.0 else 1.0


def region_crop(
    image_paths: list[str],
    region: dict[str, Any],
    canvas: dict[str, Any] | None,
    out_dir: pathlib.Path,
) -> str | None:
    """Write the region's pixels to a PNG and return its path.

    Returns None whenever the crop cannot be trusted -- no box, a degenerate
    box, an unreadable image. The caller then runs as it always did, on the
    description alone, rather than on a misleading picture.
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
            ratio = _scale(canvas, width, height)
            left = int(float(bbox.get("x", 0)) * ratio) - MARGIN
            top = int(float(bbox.get("y", 0)) * ratio) - MARGIN
            right = left + int(float(bbox.get("w", 0)) * ratio) + 2 * MARGIN
            bottom = top + int(float(bbox.get("h", 0)) * ratio) + 2 * MARGIN
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
            image.convert("RGB").crop(box).save(destination)
    except Exception:  # noqa: BLE001 - a missing crop must never fail a run
        logger.exception("could not crop %s", region.get("region_id"))
        return None

    logger.info("cropped %s to %s", region.get("region_id"), destination)
    return str(destination)
