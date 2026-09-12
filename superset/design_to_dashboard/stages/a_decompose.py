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

The stage reports what it sees and nothing it would have to compute. It numbers
regions; `region_id` is minted here from that number and the visible title, so
the same design read twice produces the same ids by construction rather than by
instruction. It reports boxes as fractions of the image, so pixels are derived
wherever they are needed. Both used to be arithmetic the model did by hand, and
both produced readings that failed validation after the pipeline's longest call.
"""

from __future__ import annotations

import logging
import pathlib
import re
import unicodedata
from typing import Any

from superset.design_to_dashboard import chrome
from superset.design_to_dashboard.llm.base import LLMProvider
from superset.design_to_dashboard.pipeline.tool_loop import extract_json
from superset.design_to_dashboard.registry import (
    load as load_registry,
    render_summaries,
)

logger = logging.getLogger(__name__)

ROLES = {
    "wrapper",
    "kpi",
    "chart",
    "table",
    "filter",
    "nav",
    "header",
    "text",
    "decoration",
}

# What a wrapper's own chrome does to the children it holds. Only a wrapper has
# one; a leaf region draws no frame around anything.
FRAMES = {"none", "tabs", "toggle"}

# Boxes are read off a picture by eye, so they do not land exactly. This slack
# is for that, not for a different coordinate system.
BBOX_SLACK = 0.02

# How much of a child has to lie within its declared parent. Cards butt up
# against the frames around them and a border has thickness, so this is
# deliberately short of total containment.
INSIDE = 0.9

# One repair pass. Reading the design is the longest call in the pipeline, so a
# blind re-ask was rightly refused -- but the problems are mechanical and now
# in hand, and losing a whole run to a single bad enum value is worse than one
# extra call. Every other stage already repairs this way.
MAX_ATTEMPTS = 2

# Regions whose `stock_candidate` is meaningless: a wrapper is a frame we write
# ourselves, and no registered viz type composes one.
NO_STOCK_CANDIDATE = {"wrapper"}


def build_system_prompt(
    prompts_dir: pathlib.Path, registry_path: str | None = None
) -> str:
    """Assemble the stage A system prompt: preamble, stage, and the registry.

    The registry is for `stock_candidate` alone, and the stage prompt orders its
    contract so `observed` and `unusual_treatment` are written before it is
    consulted. A model that knows `echarts_timeseries_bar` exists before it has
    described the picture starts seeing "a bar chart" where the design draws
    bars with their labels above them -- which is the one detail worth having.
    """
    preamble = (prompts_dir / "shared" / "_preamble.md").read_text(encoding="utf-8")
    stage = (prompts_dir / "A_decompose_design.md").read_text(encoding="utf-8")
    parts = [preamble, stage]
    if registry_path:
        parts.append(
            "## Registered viz types\n\n"
            "Consult this only for a leaf region's `stock_candidate`, and only "
            "after you have written what you see. A plugin that is *close* is "
            "not a match.\n\n" + render_summaries(load_registry(registry_path))
        )
    return "\n\n---\n\n".join(parts)


def build_user_prompt(requirement: str) -> str:
    """The user's requirement. The images are attached by the provider.

    Nothing about the images is stated here: boxes are fractions, so the stage
    needs no dimensions and there is nothing a provider has to report.
    """
    return f"USER_REQUIREMENT:\n{requirement}"


def _slug(text: str) -> str:
    """A region id's readable half: the visible title, flattened.

    Accents are folded rather than dropped so a titled section keeps a
    recognisable id; anything still unrepresentable becomes a separator, and a
    title that survives as nothing falls back to the role.
    """
    folded = unicodedata.normalize("NFKD", text)
    ascii_only = folded.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"_+", "_", re.sub(r"[^a-z0-9]+", "_", ascii_only.lower())).strip("_")


def assign_region_ids(design_analysis: dict[str, Any]) -> dict[str, Any]:
    """Mint `region_id` for every region, in place, and return the analysis.

    The stage reports `n` and a visible `title`; the id is derived from those
    here. Deriving rather than asking is what makes the promise downstream
    depends on -- that the same design read twice produces the same ids -- true
    by construction. Asking produced `r03_kpi_aws` for a card titled "AWS"
    often enough to be the rule rather than the exception.
    """
    for region in design_analysis.get("regions") or []:
        if not isinstance(region, dict):
            continue
        try:
            number = int(region["n"])
        except (KeyError, TypeError, ValueError):
            continue
        slug = _slug(str(region.get("title") or "")) or _slug(
            str(region.get("role") or "")
        )
        region["region_id"] = f"r{number:02d}_{slug or 'region'}"
    return design_analysis


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


def _label(region: dict[str, Any]) -> str:
    """How a region is named in a problem, before ids exist."""
    title = region.get("title")
    return f"region {region.get('n')}" + (f" ({title})" if title else "")


def _validate_nesting(  # noqa: C901
    regions: list[dict[str, Any]], by_number: dict[int, dict[str, Any]]
) -> list[str]:
    """`children` must describe a tree, and each child must sit inside it.

    Nesting is the contract's only way to say one section holds another, and
    geometry is the only independent evidence for it: a wrapper claiming a child
    it does not enclose has misread the design, and a child claimed by two
    parents is drawn twice. Containment is also what this check used to
    *forbid*, back when a container replaced its contents rather than holding
    them -- the rule inverted with the contract.
    """
    problems: list[str] = []
    claimed: dict[int, int] = {}

    for region in regions:
        number = region["n"]
        children = region.get("children") or []
        if not isinstance(children, list):
            problems.append(f"{_label(region)}: children is not a list")
            continue
        if children and region.get("role") != "wrapper":
            problems.append(
                f"{_label(region)}: has children but role is "
                f"{region.get('role')!r} -- a section holding other sections "
                "is a wrapper"
            )
        for child in children:
            if child == number:
                problems.append(f"{_label(region)}: lists itself as a child")
                continue
            if child not in by_number:
                problems.append(f"{_label(region)}: child {child!r} is not a region")
                continue
            if child in claimed:
                problems.append(
                    f"region {child} is claimed by both region {claimed[child]} "
                    f"and region {number}"
                )
                continue
            claimed[child] = number

            outer, inner = _box(region), _box(by_number[child])
            if outer and inner and _inside(inner, outer) < INSIDE:
                problems.append(
                    f"{_label(by_number[child])}: is a child of region {number} "
                    "but its bbox is not inside it. A wrapper encloses what it "
                    "holds: correct the boxes, or drop the child if the frame "
                    "does not actually contain it."
                )
    return problems


def _validate_same_as(
    regions: list[dict[str, Any]], by_number: dict[int, dict[str, Any]]
) -> list[str]:
    """`same_as` must point back at a real, earlier, first occurrence.

    The field exists so a component drawn six times is generated once, and the
    grouping is only usable if every repeat names the *same* region. A chain --
    5 pointing at 4 pointing at 3 -- splits one component into several groups
    that each look complete.
    """
    problems: list[str] = []
    for region in regions:
        target = region.get("same_as")
        if target is None:
            continue
        if target not in by_number:
            problems.append(f"{_label(region)}: same_as {target!r} is not a region")
        elif target == region["n"]:
            problems.append(f"{_label(region)}: same_as points at itself")
        elif target > region["n"]:
            problems.append(
                f"{_label(region)}: same_as {target} comes later -- point at the "
                "first region drawn this way, not a later one"
            )
        elif by_number[target].get("same_as") is not None:
            problems.append(
                f"{_label(region)}: same_as {target}, which is itself a repeat. "
                f"Point every copy at the first occurrence "
                f"({by_number[target].get('same_as')})."
            )
    return problems


def _validate_geometry(regions: list[dict[str, Any]]) -> list[str]:
    """Every box is a fraction of its image, so the canvas is the unit square."""
    problems: list[str] = []
    for region in regions:
        box = _box(region)
        if box is None:
            problems.append(
                f"{_label(region)}: bbox {region.get('bbox')!r} is not "
                "{x, y, w, h} with positive w and h, as fractions of the image"
            )
            continue
        x, y, w, h = box
        if (
            x < -BBOX_SLACK
            or y < -BBOX_SLACK
            or x + w > 1 + BBOX_SLACK
            or y + h > 1 + BBOX_SLACK
        ):
            problems.append(
                f"{_label(region)}: bbox {region['bbox']!r} falls outside the "
                "image. Coordinates are fractions from 0.0 to 1.0, not pixels."
            )
    return problems


def _validate_chrome(region: dict[str, Any]) -> list[str]:
    """Whether the reading says what Superset may draw around this section.

    Absent chrome is not an error: a reading from before this field existed
    still describes a usable page, and the compiler falls back to Superset's
    own behaviour. A chrome that is *present and wrong* is the error, because
    "card" and "bare" are the difference between a heading on the page and a
    heading in a box the design never drew.
    """
    value = region.get("chrome")
    if value is None:
        return []
    if not isinstance(value, dict):
        return [f"{_label(region)}: chrome is not an object"]

    problems: list[str] = []
    surface = value.get("surface")
    if surface not in chrome.SURFACES:
        problems.append(
            f"{_label(region)}: chrome.surface {surface!r} is not one of "
            f"{sorted(chrome.SURFACES)} -- say whether the section sits on its "
            "own card or directly on the page"
        )
    title = value.get("title")
    if title not in chrome.TITLE_KINDS:
        problems.append(
            f"{_label(region)}: chrome.title {title!r} is not one of "
            f"{sorted(chrome.TITLE_KINDS)}"
        )
    actions = value.get("actions")
    if actions is not None and not isinstance(actions, list):
        problems.append(f"{_label(region)}: chrome.actions is not a list")
    elif isinstance(actions, list):
        for index, action in enumerate(actions):
            if not isinstance(action, dict) or not action.get("kind"):
                problems.append(
                    f"{_label(region)}: chrome.actions[{index}] needs a `kind` "
                    "naming the affordance the design draws"
                )
    return problems


def validate(  # noqa: C901
    design_analysis: dict[str, Any], known_viz_types: set[str] | None = None
) -> list[str]:
    """Structural checks on the reading, before any stage joins against it.

    Everything here is mechanical. Whether the model read the design *well* is
    not knowable from the JSON; whether it read it into a shape the rest of the
    pipeline can use is, and that is what this checks.

    `known_viz_types` is optional: without it a `stock_candidate` is taken on
    trust, which is what happens when the caller has no registry to hand.
    """
    problems: list[str] = []

    if design_analysis.get("status") != "ok":
        problems.append(f"invalid status: {design_analysis.get('status')!r}")

    raw = design_analysis.get("regions")
    if not isinstance(raw, list) or not raw:
        return problems + ["no regions were read from the design"]

    regions: list[dict[str, Any]] = []
    seen: set[int] = set()
    for index, region in enumerate(raw):
        if not isinstance(region, dict):
            problems.append(f"region at index {index} is not an object")
            continue
        try:
            number = int(region["n"])
        except (KeyError, TypeError, ValueError):
            problems.append(
                f"region at index {index} has n {region.get('n')!r}, expected a "
                "whole number giving its place in reading order"
            )
            continue
        if number < 1:
            problems.append(f"region at index {index}: n must start at 1")
            continue
        if number in seen:
            problems.append(f"duplicate n: {number}")
            continue
        seen.add(number)
        region["n"] = number
        regions.append(region)

    if not regions:
        return problems + ["no usable regions were read from the design"]

    by_number = {region["n"]: region for region in regions}

    for region in regions:
        role = region.get("role")
        if role not in ROLES:
            problems.append(
                f"{_label(region)}: role {role!r} is not one of {sorted(ROLES)}"
            )
        frame = region.get("frame")
        if role == "wrapper":
            if frame not in FRAMES:
                problems.append(
                    f"{_label(region)}: frame {frame!r} is not one of "
                    f"{sorted(FRAMES)} -- say what this wrapper's own chrome "
                    "does to the sections it holds"
                )
        elif frame is not None:
            problems.append(
                f"{_label(region)}: frame is {frame!r} but only a wrapper has "
                "one; a leaf region frames nothing"
            )

        problems += _validate_chrome(region)

        candidate = region.get("stock_candidate")
        if candidate is not None:
            if role in NO_STOCK_CANDIDATE:
                problems.append(
                    f"{_label(region)}: stock_candidate {candidate!r} on a "
                    "wrapper -- no registered viz type composes a frame, so "
                    "this is always null"
                )
            elif known_viz_types and candidate not in known_viz_types:
                problems.append(
                    f"{_label(region)}: stock_candidate {candidate!r} is not a "
                    "registered viz type"
                )

    problems += _validate_geometry(regions)
    problems += _validate_nesting(regions, by_number)
    problems += _validate_same_as(regions, by_number)

    order = (design_analysis.get("global") or {}).get("reading_order")
    if not isinstance(order, list):
        problems.append("global.reading_order is missing")
    else:
        listed = {n for n in order if isinstance(n, int)}
        for missing in sorted(seen - listed):
            problems.append(f"reading_order omits region {missing}")
        for unknown in sorted(listed - seen):
            problems.append(f"reading_order names an unknown region: {unknown}")

    return problems


def _repair_note(problems: list[str]) -> str:
    """The previous reading's faults, to be fixed rather than re-derived."""
    listed = "\n".join(f"- {problem}" for problem in problems)
    return (
        "\n\nYour previous reading of this design failed these checks. They are "
        "mechanical, not matters of taste -- an enum value that is not in the "
        "list, a box outside the image, a child that is not inside its parent. "
        "Keep everything that was right and return the whole analysis again "
        "with each of these fixed.\n"
        f"{listed}"
    )


def run(
    provider: LLMProvider,
    requirement: str,
    image_paths: list[str],
    prompts_dir: pathlib.Path,
    on_thinking: Any = None,
    attempts: int = MAX_ATTEMPTS,
    registry_path: str | None = None,
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
    system_prompt = build_system_prompt(prompts_dir, registry_path)
    user_prompt = build_user_prompt(requirement)
    known = (
        {str(entry.get("viz_type")) for entry in load_registry(registry_path)}
        if registry_path
        else None
    )
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

        # A refusal is an answer, not a fault. Repairing one asks the model to
        # invent regions for a design it has just said it cannot read, and
        # spends a second full-image call doing it.
        if analysis.get("status") in {"unreadable", "separate_designs"}:
            return analysis, cost

        problems = validate(analysis, known)
        if not problems or attempt == attempts:
            if problems:
                logger.warning(
                    "stage A still has %d problem(s) after %d attempt(s)",
                    len(problems),
                    attempt,
                )
            return assign_region_ids(analysis), cost

        logger.info(
            "stage A attempt %d had %d problem(s); asking again",
            attempt,
            len(problems),
        )
        user_prompt = build_user_prompt(requirement) + _repair_note(problems)

    return assign_region_ids(analysis), cost
