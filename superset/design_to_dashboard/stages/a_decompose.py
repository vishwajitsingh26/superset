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
"""Stage A - read the design and describe what is visually there.

The first stage, and the one every later stage joins against: `region_id` is
the key B binds, C decides on, D configures and E places. A malformed reading
here is not caught by anything downstream -- it surfaces as a chart that cannot
be created, twenty minutes and several dollars later. So this module validates
its own output before the run is allowed to continue.
"""

from __future__ import annotations

import logging
import pathlib
import re
from typing import Any

from superset.design_to_dashboard.llm.base import LLMProvider
from superset.design_to_dashboard.pipeline.tool_loop import extract_json

logger = logging.getLogger(__name__)

# `r<NN>_<slug>`, per the stage prompt. The optional `:<N>` suffix is the
# pipeline's shared grammar for one child of a composite region -- stage A does
# not mint those (it emits the parent card as one region) but the grammar is
# shared with stage B, which does, so the pattern accepts them.
REGION_ID = re.compile(r"^r\d{2}_[a-z0-9_]+(:\d+)?$")

ROLES = {"kpi", "chart", "table", "filter", "nav", "header", "text", "decoration"}
COMPOSITIONS = {"atomic", "composite", "control", "container"}

# Boxes are read off a picture by eye, so they do not land on exact pixels.
# This slack is for rounding, not for a different coordinate space: a box in
# the wrong space is out by tens of percent and must still be caught.
BBOX_SLACK = 0.02


def build_system_prompt(prompts_dir: pathlib.Path) -> str:
    """Assemble the stage A system prompt: preamble, then the stage."""
    preamble = (prompts_dir / "shared" / "_preamble.md").read_text(encoding="utf-8")
    stage = (prompts_dir / "A_decompose_design.md").read_text(encoding="utf-8")
    return "\n\n---\n\n".join([preamble, stage])


def build_user_prompt(requirement: str) -> str:
    """The user's requirement. The images are attached by the provider."""
    return f"USER_REQUIREMENT:\n{requirement}"


def _image_size(path: str) -> tuple[int, int] | None:
    """The image's dimensions, or None when they cannot be read.

    A missing Pillow or an unreadable file must not fail a run: the checks that
    depend on this are skipped instead.
    """
    try:
        from PIL import Image

        with Image.open(path) as image:
            return int(image.size[0]), int(image.size[1])
    except Exception:  # noqa: BLE001 - an unreadable image is checked elsewhere
        logger.info("could not read the size of %s", path)
        return None


def _check_canvas_matches_image(  # noqa: C901
    canvas: dict[str, Any], image_paths: list[str]
) -> list[str]:
    """Confirm the boxes are in the coordinate space they claim to be in.

    The design image is handed to the model through a tool that downscales it
    and reports the original dimensions, so the model is always in a position
    to report boxes in either space. Either one works on its own -- the crop
    converts between them -- but a reading that rescales the boxes and reports
    the *other* canvas is out by the scale factor everywhere, and every
    consumer downstream silently believes it.

    `crop.region_crop` cannot catch this: it derives the scale from this very
    canvas, so a consistent lie and an inconsistent one look identical to it.
    Comparing against the file on disk is the only independent check available.
    """
    if not image_paths:
        return []
    size = _image_size(image_paths[0])
    if size is None:
        return []
    width, height = size
    declared_w = float(canvas.get("w") or 0)
    declared_h = float(canvas.get("h") or 0)
    if declared_w <= 0 or declared_h <= 0:
        return []

    problems = []
    for axis, declared, actual in (
        ("w", declared_w, width),
        ("h", declared_h, height),
    ):
        if abs(declared - actual) > actual * BBOX_SLACK:
            problems.append(
                f"global.canvas.{axis} is {declared:g} but the design image is "
                f"{actual}px -- the bboxes are in neither the image's space nor "
                f"a space anything can convert from. Report the size you were "
                f"shown, and boxes in that same space."
            )
    return problems


def validate(  # noqa: C901
    design_analysis: dict[str, Any], image_paths: list[str] | None = None
) -> list[str]:
    """Structural checks on the reading, before any stage joins against it.

    Everything here is mechanical. Whether the model read the design *well* is
    not knowable from the JSON; whether it read it into a shape the rest of the
    pipeline can use is, and that is what this checks.
    """
    problems: list[str] = []

    if design_analysis.get("status") != "ok":
        problems.append(f"invalid status: {design_analysis.get('status')!r}")

    regions = design_analysis.get("regions")
    if not isinstance(regions, list) or not regions:
        return problems + ["no regions were read from the design"]

    seen: set[str] = set()
    for index, region in enumerate(regions):
        if not isinstance(region, dict):
            problems.append(f"region at index {index} is not an object")
            continue
        region_id = region.get("region_id")
        if not isinstance(region_id, str) or not REGION_ID.match(region_id):
            problems.append(
                f"region at index {index} has region_id {region_id!r}, "
                "expected the form 'r01_some_slug'"
            )
            continue
        if region_id in seen:
            problems.append(f"duplicate region_id: {region_id}")
        seen.add(region_id)

        if region.get("role") not in ROLES:
            problems.append(
                f"{region_id}: role {region.get('role')!r} is not one of "
                f"{sorted(ROLES)}"
            )
        if region.get("composition") not in COMPOSITIONS:
            problems.append(
                f"{region_id}: composition {region.get('composition')!r} is not "
                f"one of {sorted(COMPOSITIONS)}"
            )

    problems += _validate_geometry(design_analysis, regions, seen, image_paths or [])

    order = (design_analysis.get("global") or {}).get("reading_order")
    if not isinstance(order, list):
        problems.append("global.reading_order is missing")
    elif seen and set(order) != seen:
        for missing in sorted(seen - set(order)):
            problems.append(f"reading_order omits {missing}")
        for unknown in sorted(set(order) - seen):
            problems.append(f"reading_order names an unknown region: {unknown}")

    return problems


def _validate_geometry(
    design_analysis: dict[str, Any],
    regions: list[Any],
    known: set[str],
    image_paths: list[str],
) -> list[str]:
    """The canvas, and every box that claims to sit inside it."""
    problems: list[str] = []
    canvas = (design_analysis.get("global") or {}).get("canvas")
    if not isinstance(canvas, dict):
        return ["global.canvas is missing"]

    width = float(canvas.get("w") or 0)
    height = float(canvas.get("h") or 0)
    if width <= 0 or height <= 0:
        return [f"global.canvas is {canvas!r}, expected positive w and h"]

    problems += _check_canvas_matches_image(canvas, image_paths)

    for region in regions:
        if not isinstance(region, dict) or region.get("region_id") not in known:
            continue
        region_id = region["region_id"]
        bbox = region.get("bbox")
        if not isinstance(bbox, dict):
            problems.append(f"{region_id}: bbox is missing")
            continue
        try:
            x, y = float(bbox["x"]), float(bbox["y"])
            w, h = float(bbox["w"]), float(bbox["h"])
        except (KeyError, TypeError, ValueError):
            problems.append(f"{region_id}: bbox {bbox!r} is not {{x, y, w, h}}")
            continue
        if w <= 0 or h <= 0:
            problems.append(f"{region_id}: bbox has no area ({w:g}x{h:g})")
        if (
            x < -width * BBOX_SLACK
            or y < -height * BBOX_SLACK
            or x + w > width * (1 + BBOX_SLACK)
            or y + h > height * (1 + BBOX_SLACK)
        ):
            problems.append(
                f"{region_id}: bbox {bbox!r} falls outside the "
                f"{width:g}x{height:g} canvas"
            )
    return problems


def run(
    provider: LLMProvider,
    requirement: str,
    image_paths: list[str],
    prompts_dir: pathlib.Path,
    on_thinking: Any = None,
) -> tuple[dict[str, Any], float]:
    """Read the design. Returns ``(design_analysis, cost_usd)``.

    Parsing happens here rather than in the caller so that a reply which is not
    JSON is retried with the call, not after it: this stage is the longest
    single call in the pipeline, and losing it to one unparseable turn costs
    the same as losing it to a transient error.
    """
    response = provider.complete(
        build_system_prompt(prompts_dir),
        build_user_prompt(requirement),
        image_paths,
        on_thinking=on_thinking,
    )
    return extract_json(response.text), response.cost_usd or 0.0
