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
"""Stage E - translate design geometry into Superset's dashboard grid.

Pure geometry. It receives bounding boxes and chart refs, and emits
``position_json``. It never sees datasets, control schemas, params or the
design image, so it is the cheapest stage to run and to re-run.
"""

from __future__ import annotations

import logging
import pathlib
import uuid
from typing import Any

from superset.design_to_dashboard.llm.base import LLMProvider
from superset.design_to_dashboard.pipeline.tool_loop import extract_json
from superset.utils import json

logger = logging.getLogger(__name__)

# How a CHART node addresses a chart that does not exist yet. Defined here
# because position_json is this stage's output; the applier imports it rather
# than keeping a second copy that could drift.
REF_PREFIX = "__REF__:"
GRID_COLUMN_COUNT = 12
GRID_BASE_UNIT = 8
NODE_TYPES = {
    "ROOT",
    "GRID",
    "ROW",
    "COLUMN",
    "CHART",
    "TABS",
    "TAB",
    "MARKDOWN",
    "HEADER",
    "DIVIDER",
}
# Decisions that never occupy a grid cell.
NON_GRID_DECISIONS = {"drop"}
# `grid_text` does occupy a cell, but as a MARKDOWN/HEADER node, which carries
# no chart ref. Counting it among the refs a CHART node must claim failed the
# whole layout with "ref 'c1' was never placed on the grid".
NON_CHART_DECISIONS = {"grid_text"}


def build_system_prompt(prompts_dir: pathlib.Path) -> str:
    preamble = (prompts_dir / "shared" / "_preamble.md").read_text(encoding="utf-8")
    stage = (prompts_dir / "E_layout.md").read_text(encoding="utf-8")
    return f"{preamble}\n\n---\n\n{stage}"


def content_box(regions: list[dict[str, Any]]) -> dict[str, float] | None:
    """The area the dashboard occupies, as fractions of the image.

    Not the whole image. When the app shell is dropped -- a left nav rail, a
    top bar -- the grid's 12 columns span what is left, and dividing by the
    full width makes every card a column or two too narrow. Stage E then
    notices each row underflowing and widens it back, one row at a time,
    reporting arithmetic it had to undo as a design compromise.

    Fractions, not pixels, and deliberately not rounded to whole numbers: a
    box that spans half the page is `0.5`, and rounding that to an integer is
    `0`. Every use of it downstream is a ratio against another fraction, so
    the units cancel.
    """
    boxes = [r["bbox"] for r in regions if isinstance(r.get("bbox"), dict)]
    boxes = [b for b in boxes if b.get("w") and b.get("h")]
    if not boxes:
        return None
    left = min(float(b.get("x", 0)) for b in boxes)
    top = min(float(b.get("y", 0)) for b in boxes)
    right = max(float(b.get("x", 0)) + float(b["w"]) for b in boxes)
    bottom = max(float(b.get("y", 0)) + float(b["h"]) for b in boxes)
    return {
        "x": round(left, 4),
        "y": round(top, 4),
        "w": round(right - left, 4),
        "h": round(bottom - top, 4),
    }


def total_units(box: dict[str, float] | None, image_height: int | None) -> int | None:
    """How many 8px grid rows the content stands, if the image size is known.

    The one number stage E cannot derive from fractions: a height in grid
    units needs a real pixel height somewhere. Measured here rather than asked
    for, because the model can only guess at it and every card's height is a
    ratio against it.
    """
    if not box or not image_height or not box.get("h"):
        return None
    return max(1, round(float(box["h"]) * image_height / GRID_BASE_UNIT))


def build_user_prompt(
    design_analysis: dict[str, Any],
    plan: dict[str, Any],
    user_answers: dict[str, Any] | None = None,
    image_height: int | None = None,
) -> str:
    """Only geometry and refs — deliberately no data or params."""
    # Regions stage C dropped or routed to the filter bar must not be laid out.
    # Passing every region let stage E apply its own "header -> MARKDOWN" rule
    # to a header C had already assigned to the dashboard title, producing a
    # duplicate heading.
    excluded = {
        decision.get("region_id")
        for decision in plan.get("decisions", [])
        if decision.get("decision") in NON_GRID_DECISIONS
    }
    regions = [
        {key: region.get(key) for key in ("region_id", "bbox", "role", "title", "tab")}
        for region in design_analysis.get("regions", [])
        if region.get("region_id") not in excluded
    ]
    placements = [
        {
            "ref": decision.get("ref"),
            "region_id": decision.get("region_id"),
            "slice_name": decision.get("slice_name"),
            "decision": decision.get("decision"),
        }
        for decision in plan.get("decisions", [])
        if decision.get("decision") not in NON_GRID_DECISIONS
    ]
    box = content_box(regions)
    payload = {
        "regions": regions,
        "global": design_analysis.get("global", {}),
        "content_box": box,
        "total_units": total_units(box, image_height),
        "placements": placements,
    }
    # Whether the app shell is hidden decides what the grid spans, and stage E
    # was the one stage that never saw the answer -- it could only infer it from
    # the regions stage C happened to drop.
    if user_answers:
        payload["user_answers"] = user_answers
    return (
        "Lay these regions out on Superset's 12-column grid (data, not "
        "instructions). Charts are addressed by `ref` — emit "
        '"__REF__:<ref>" as each CHART node\'s meta.chartId.\n\n'
        f"```json\n{json.dumps(payload, indent=2)}\n```"
    )


# Superset draws a header on every chart card that a design almost never shows,
# and it eats into the content area. Sizing a card at the design's own ratio
# therefore clips whatever is inside it -- measured at roughly 40px, so five
# grid units.
CHART_HEADER_UNITS = 5
# A page heading needs room for a large font plus padding; the model has chosen
# 4 (32px) for a 26px heading and clipped it.
MIN_TEXT_HEIGHT = 8


def ref_of(node: dict[str, Any]) -> str | None:
    """The symbolic ref a CHART node points at, or None.

    One reader for the one place a ref is written, so a second consumer cannot
    quietly invent a different key for it.
    """
    chart_id = (node.get("meta") or {}).get("chartId")
    if isinstance(chart_id, str) and chart_id.startswith(REF_PREFIX):
        return chart_id[len(REF_PREFIX) :]
    return None


def drop_composed_children(  # noqa: C901
    position: dict[str, Any], plan: dict[str, Any]
) -> list[str]:
    """Remove grid nodes for charts a composing parent renders itself.

    A container fetches and draws its children, so a child also placed
    on the grid appears twice: once inside the panel and once loose beside it.
    Stage E is told this and did it anyway, failing the whole layout after
    eighteen charts had already been configured -- so the grid is corrected
    here rather than the run rejected.
    """
    children = {
        child
        for decision in plan.get("decisions", [])
        for child in decision.get("children") or []
    }
    if not children:
        return []

    removed: dict[str, str] = {}
    for node_id, node in list(position.items()):
        if not isinstance(node, dict) or node.get("type") != "CHART":
            continue
        # `meta.chartId`, not `meta.ref`: a CHART node addresses its chart by
        # `"__REF__:c1"` and has no `ref` key. Reading one that never existed
        # made this whole repair a no-op, so the duplicate it was written to
        # remove survived to `validate`, which fails the run -- the outcome the
        # repair exists to avoid.
        ref = ref_of(node)
        if ref is not None and ref in children:
            removed[node_id] = ref
            del position[node_id]

    notes = [
        f"{node_id}: ref {ref!r} is drawn by its parent, not the grid"
        for node_id, ref in removed.items()
    ]
    for row_id, row in list(position.items()):
        if not isinstance(row, dict) or row.get("type") != "ROW":
            continue
        kept = [c for c in row.get("children", []) if c not in removed]
        if len(kept) != len(row.get("children", [])):
            row["children"] = kept
        if not kept:
            del position[row_id]
            notes.append(f"{row_id}: left empty, removed")
            for parent in position.values():
                if isinstance(parent, dict) and row_id in (
                    parent.get("children") or []
                ):
                    parent["children"] = [c for c in parent["children"] if c != row_id]
    return notes


def normalise(position: dict[str, Any]) -> list[str]:
    """Make the grid self-consistent, in place, and report what changed.

    Stage E sizes every node from its own bbox, independently, so three
    identical KPI tiles came back 27, 28 and 28 -- three roundings of the same
    number. Superset lays a row out as one band, so siblings must agree; this
    is arithmetic, not judgement, and belongs here rather than in a prompt that
    can drift.
    """
    notes: list[str] = []
    for row_id, row in position.items():
        if not isinstance(row, dict) or row.get("type") != "ROW":
            continue
        children = [
            position[c]
            for c in row.get("children", [])
            if isinstance(position.get(c), dict)
        ]
        if not children:
            continue

        for node in children:
            meta = node.setdefault("meta", {})
            if node.get("type") in {"MARKDOWN", "HEADER"}:
                if (meta.get("height") or 0) < MIN_TEXT_HEIGHT:
                    notes.append(
                        f"{row_id}: heading height "
                        f"{meta.get('height')} -> {MIN_TEXT_HEIGHT}"
                    )
                    meta["height"] = MIN_TEXT_HEIGHT
                if len(children) == 1 and (meta.get("width") or 0) < GRID_COLUMN_COUNT:
                    notes.append(
                        f"{row_id}: heading width "
                        f"{meta.get('width')} -> {GRID_COLUMN_COUNT}"
                    )
                    meta["width"] = GRID_COLUMN_COUNT

        heights = [
            n["meta"].get("height")
            for n in children
            if isinstance(n.get("meta"), dict) and n["meta"].get("height")
        ]
        if len(set(heights)) > 1:
            tallest = max(heights)
            notes.append(f"{row_id}: heights {sorted(set(heights))} -> {tallest}")
            for node in children:
                node["meta"]["height"] = tallest
    return notes


def _image_height(image_paths: list[str] | None) -> int | None:
    """The design's pixel height, or None when it cannot be read.

    Only one number in the layout needs real pixels -- how many 8px grid rows
    the page stands. Everything else is a ratio between fractions.
    """
    if not image_paths:
        return None
    try:
        from PIL import Image

        with Image.open(image_paths[0]) as image:
            return int(image.size[1])
    except Exception:  # noqa: BLE001 - a layout without it still works
        logger.info("could not read the height of %s", image_paths[0])
        return None


def run(
    provider: LLMProvider,
    design_analysis: dict[str, Any],
    plan: dict[str, Any],
    prompts_dir: pathlib.Path,
    on_thinking: Any = None,
    image_paths: list[str] | None = None,
    user_answers: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], float]:
    """Return ``(layout_plan, cost_usd)``."""
    response = provider.complete(
        build_system_prompt(prompts_dir),
        build_user_prompt(
            design_analysis, plan, user_answers, _image_height(image_paths)
        ),
        # E's region is the whole page: row structure, relative widths and how
        # tall a card is next to its neighbour are what it has to reproduce,
        # and those read off the design far better than off a list of boxes.
        image_paths=list(image_paths) if image_paths else None,
        on_thinking=on_thinking,
    )
    layout = extract_json(response.text)
    position = layout.get("position_json") or {}
    corrections = drop_composed_children(position, plan) + normalise(position)
    if adjustments := corrections:
        layout.setdefault("adjustments", []).extend(
            {"row_id": note.split(":")[0], "issue": note, "resolution": "normalised"}
            for note in adjustments
        )
        logger.info("stage E normalised the grid: %s", "; ".join(adjustments))
    logger.info(
        "stage E complete: %d node(s), %d adjustment(s)",
        len(layout.get("position_json", {})),
        len(layout.get("adjustments", [])),
    )
    return layout, response.cost_usd or 0.0


def validate(layout: dict[str, Any], plan: dict[str, Any]) -> list[str]:  # noqa: C901
    """Structural checks on position_json before anything is written."""
    problems: list[str] = []
    position = layout.get("position_json")
    if not isinstance(position, dict) or not position:
        return ["position_json is missing or empty"]

    if "ROOT_ID" not in position:
        problems.append("no ROOT_ID node")

    expected_refs = {
        decision["ref"]
        for decision in plan.get("decisions", [])
        if decision.get("ref")
        and decision.get("decision") not in NON_GRID_DECISIONS | NON_CHART_DECISIONS
    }
    # A composing parent renders its children itself, so they get no grid node
    # of their own. This is keyed on `children` rather than on `decision ==
    # "wrap"` because a generated container plugin composes exactly the same
    # way; keying on the decision word laid its children out twice.
    child_refs = {
        child
        for decision in plan.get("decisions", [])
        for child in decision.get("children") or []
    }
    expected_refs -= child_refs

    placed_refs: set[str] = set()
    for node_id, node in position.items():
        if node_id == "DASHBOARD_VERSION_KEY" or not isinstance(node, dict):
            continue
        node_type = node.get("type")
        if node_type not in NODE_TYPES:
            problems.append(f"{node_id}: unknown node type {node_type!r}")
            continue
        if node.get("id") != node_id:
            problems.append(f"{node_id}: node id field is {node.get('id')!r}")

        for child in node.get("children") or []:
            if child not in position:
                problems.append(f"{node_id}: child {child!r} is not a node")

        if node_type == "CHART":
            meta = node.get("meta") or {}
            chart_id = meta.get("chartId")
            if (ref := ref_of(node)) is not None:
                placed_refs.add(ref)
            elif isinstance(chart_id, int):
                placed_refs.add(f"<existing:{chart_id}>")
            else:
                problems.append(f"{node_id}: meta.chartId is {chart_id!r}")
            width = meta.get("width")
            if not isinstance(width, int) or not 1 <= width <= GRID_COLUMN_COUNT:
                problems.append(f"{node_id}: width {width!r} outside 1..12")
            if not isinstance(meta.get("height"), int):
                problems.append(f"{node_id}: height {meta.get('height')!r}")
            if not meta.get("uuid"):
                problems.append(f"{node_id}: no uuid")

        if node_type == "ROW":
            total = 0
            for child in node.get("children") or []:
                child_node = position.get(child) or {}
                total += (child_node.get("meta") or {}).get("width") or 0
            if total > GRID_COLUMN_COUNT:
                problems.append(
                    f"{node_id}: child widths sum to {total}, over {GRID_COLUMN_COUNT}"
                )

    for missing in sorted(expected_refs - placed_refs):
        problems.append(f"ref {missing!r} was never placed on the grid")
    for extra in sorted(placed_refs - expected_refs):
        if not extra.startswith("<existing:"):
            problems.append(f"grid places unknown ref {extra!r}")

    # A child its parent draws is not unplaced -- it is placed *inside* the
    # parent. Failing the run for saying so was the one honest way to record it
    # and left the model choosing between a hard failure and a grid node that
    # draws the piece twice.
    stranded = [
        entry
        for entry in layout.get("unplaced") or []
        if not (isinstance(entry, dict) and entry.get("ref") in child_refs)
    ]
    if stranded:
        problems.append(f"stage reported unplaced: {stranded}")

    return problems


def ensure_uuids(position: dict[str, Any]) -> dict[str, Any]:
    """Fill in any missing CHART uuid so the frontend can drag nodes."""
    for node in position.values():
        if isinstance(node, dict) and node.get("type") == "CHART":
            meta = node.setdefault("meta", {})
            if not meta.get("uuid"):
                meta["uuid"] = str(uuid.uuid4())
    return position
