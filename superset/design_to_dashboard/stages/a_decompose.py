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
# pipeline's shared grammar for one chart inside a container -- stage A does
# not mint those (it emits the frame as one region) but the grammar is shared
# with stage B, which does, so the pattern accepts them.
REGION_ID = re.compile(r"^r\d{2}_[a-z0-9_]+(:\d+)?$")

ROLES = {"kpi", "chart", "table", "filter", "nav", "header", "text", "decoration"}
# `composite` is deliberately absent: it meant "a card holding several
# things", which a rich single card also is, and the ambiguity split KPI
# cards into pieces nothing could reassemble. A card about one subject is
# `atomic` however much it draws; only a frame over separate subjects is a
# `container`.
COMPOSITIONS = {"atomic", "container", "control"}

# Boxes are read off a picture by eye, so they do not land on exact pixels.
# This slack is for rounding, not for a different coordinate space: a box in
# the wrong space is out by tens of percent and must still be caught.
BBOX_SLACK = 0.02

# How much of a region has to sit inside a container before it is that
# container's content rather than its neighbour. Cards butt up against the
# frames around them, so this is deliberately short of total containment.
INSIDE = 0.75

# One repair pass. Reading the design is the longest call in the pipeline, so a
# blind re-ask was rightly refused -- but the problems are mechanical and now
# in hand, and losing a whole run to a single bad enum value is worse than one
# extra call. Every other stage already repairs this way.
MAX_ATTEMPTS = 2

# Roles that draw data, and so are the ones a container would be drawing twice.
# A control *is* allowed to sit inside a container's bbox: a toggle in a panel
# header is its own region by design, and is what makes the frame a container
# in the first place.
DRAWN_ROLES = {"kpi", "chart", "table"}


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


def _box(region: dict[str, Any]) -> tuple[float, float, float, float] | None:
    """`(x, y, w, h)` as floats, or None when the bbox is unusable."""
    bbox = region.get("bbox")
    if not isinstance(bbox, dict):
        return None
    try:
        x, y = float(bbox["x"]), float(bbox["y"])
        w, h = float(bbox["w"]), float(bbox["h"])
    except (KeyError, TypeError, ValueError):
        return None
    return (x, y, w, h) if w > 0 and h > 0 else None


def _inside(
    inner: tuple[float, float, float, float], outer: tuple[float, float, float, float]
) -> float:
    """The fraction of `inner`'s area that lies within `outer`."""
    ix, iy, iw, ih = inner
    ox, oy, ow, oh = outer
    overlap_w = max(0.0, min(ix + iw, ox + ow) - max(ix, ox))
    overlap_h = max(0.0, min(iy + ih, oy + oh) - max(iy, oy))
    return (overlap_w * overlap_h) / (iw * ih)


def _containers_beside_their_contents(regions: list[Any]) -> list[str]:
    """Containers that were emitted *and* had their contents emitted too.

    The prompt used to say both: that four KPI cards in a row are four regions,
    and that a panel around those four cards is a container. Read together that
    is five regions -- the frame and the four things inside it -- with nothing
    in the contract to say which belongs to which. The pipeline's only
    containment mechanism is the `:N` suffix stage B mints, and that assumes the
    frame arrived as one region, so the children are laid out a second time on
    their own.

    Bboxes are the evidence, and the only evidence: nothing else in the reading
    relates one region to another.
    """
    problems: list[str] = []
    boxed = [
        (region, box)
        for region in regions
        if isinstance(region, dict) and (box := _box(region)) is not None
    ]
    for region, outer in boxed:
        if region.get("composition") != "container":
            continue
        swallowed = [
            other["region_id"]
            for other, inner in boxed
            if other is not region
            and other.get("role") in DRAWN_ROLES
            and _inside(inner, outer) >= INSIDE
        ]
        if swallowed:
            problems.append(
                f"{region['region_id']}: is a container and {len(swallowed)} other "
                f"regions are drawn inside it ({', '.join(sorted(swallowed)[:4])}"
                f"{', ...' if len(swallowed) > 4 else ''}). A container is one "
                "region: describe what it holds in `observed` and drop those "
                "regions, or -- if the frame only draws a border -- keep them and "
                "make this region `atomic`, or drop it as `decoration`."
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
    problems += _containers_beside_their_contents(regions)

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


def _repair_note(problems: list[str]) -> str:
    """The previous reading's faults, to be fixed rather than re-derived."""
    listed = "\n".join(f"- {problem}" for problem in problems)
    return (
        "\n\nYour previous reading of this design failed these checks. They are "
        "mechanical, not matters of taste -- an enum value that is not in the "
        "list, a box outside the canvas, a region in `reading_order` that does "
        "not exist. Keep everything that was right and return the whole "
        "analysis again with each of these fixed.\n"
        f"{listed}"
    )


def run(
    provider: LLMProvider,
    requirement: str,
    image_paths: list[str],
    prompts_dir: pathlib.Path,
    on_thinking: Any = None,
    attempts: int = MAX_ATTEMPTS,
) -> tuple[dict[str, Any], float]:
    """Read the design. Returns ``(design_analysis, cost_usd)``.

    Parsing happens here rather than in the caller so that a reply which is not
    JSON is retried with the call, not after it: this stage is the longest
    single call in the pipeline, and losing it to one unparseable turn costs
    the same as losing it to a transient error.

    A reading that parses but fails :func:`validate` is asked again with the
    problems in hand. The caller still validates what it gets back and still
    fails the run if it is wrong -- this only spends one more call first.
    """
    system_prompt = build_system_prompt(prompts_dir)
    user_prompt = build_user_prompt(requirement)
    cost = 0.0
    analysis: dict[str, Any] = {}

    for attempt in range(1, attempts + 1):
        response = provider.complete(
            system_prompt,
            user_prompt,
            image_paths,
            on_thinking=on_thinking,
        )
        cost += response.cost_usd or 0.0
        analysis = extract_json(response.text)

        problems = validate(analysis, image_paths)
        if not problems or attempt == attempts:
            if problems:
                logger.warning(
                    "stage A still has %d problem(s) after %d attempt(s)",
                    len(problems),
                    attempt,
                )
            return analysis, cost

        logger.info(
            "stage A attempt %d had %d problem(s); asking again",
            attempt,
            len(problems),
        )
        user_prompt = build_user_prompt(requirement) + _repair_note(problems)

    return analysis, cost
