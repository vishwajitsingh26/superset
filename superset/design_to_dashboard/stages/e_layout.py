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
import re
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
    "HEADER",
    "DIVIDER",
}
# `MARKDOWN` is a real Superset node type, deliberately absent here: its own
# rendering always wraps content in a scrolling container, which no design
# this pipeline builds from ever draws. A `grid_text` decision is always one
# line and always a `HEADER` node; anything longer is stage C's to build as
# `configure: custom_text` instead, never this pipeline's to route around a
# scrollbar for.
# Decisions that never occupy a grid cell.
NON_GRID_DECISIONS = {"drop"}
# `grid_text` does occupy a cell, but as a HEADER node, which carries no chart
# ref. Counting it among the refs a CHART node must claim failed the whole
# layout with "ref 'c1' was never placed on the grid".
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
    # A dropped header region has already been decided; showing it to stage E
    # anyway once produced a duplicate heading built from a region nothing
    # downstream should still be looking at.
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
    on_grid = [
        decision
        for decision in plan.get("decisions", [])
        if decision.get("decision") not in NON_GRID_DECISIONS
    ]
    placed = {str(decision.get("ref")) for decision in on_grid if decision.get("ref")}
    placements: list[dict[str, Any]] = []
    for decision in on_grid:
        placement = {
            "ref": decision.get("ref"),
            "region_id": decision.get("region_id"),
            "slice_name": decision.get("slice_name"),
            "decision": decision.get("decision"),
        }
        # The prompt's rule -- a parent's `children` get no grid node -- can
        # only be followed if the placement says which refs those are. Only
        # refs still on the grid are named: a dropped child has nothing to
        # place, and a dropped parent never reaches this list, so its charts
        # arrive as ordinary placements.
        if hosted := [
            str(c) for c in decision.get("children") or [] if str(c) in placed
        ]:
            placement["children"] = hosted
        placements.append(placement)
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
# Superset's own floor for a grid row, from the frontend's grid constants.
# A card may never be reduced below it, whatever its chrome.
GRID_MIN_ROW_UNITS = 5
# A page heading needs room for a large font plus padding; the model has chosen
# 4 (32px) for a 26px heading and clipped it.
MIN_TEXT_HEIGHT = 8
# A `filter`-role card's width has a floor of its own, for the same reason a
# row's height does: rounding a design's own bbox fraction to columns can draw
# a card narrower than the text it always renders needs, whatever the design's
# geometry says. A date-range pill drawn at 0.145 of the page rounds to 2
# columns -- not enough to hold "Apr 1, 2025 - Apr 30, 2025" without losing the
# year. Unlike a chart, whose content is whatever stage D configures it to
# show, a `filter` widget's text is a fixed shape this stage can predict a
# floor for; no other role gets one, because nothing else is content this
# stage knows in advance is too wide to shrink.
GRID_MIN_FILTER_COLUMNS = 3
# A card whose menu is hidden because it draws its own action -- most often a
# "View all ->" link -- has to draw that action somewhere, and the only
# somewhere left is its own body: there is no header row for it once the menu
# it would have anchored to is gone. `CHART_HEADER_UNITS` only ever gives that
# row's height *back* (see `strip_header_allowance`); this is its mirror,
# adding a chrome row's worth of height back for the row the body has to spend
# on it instead. Sized the same, because both are one chrome row, whichever
# side of the header it ends up drawn on.
ACTION_LINK_UNITS = CHART_HEADER_UNITS


def ref_of(node: dict[str, Any]) -> str | None:
    """The symbolic ref a CHART node points at, or None.

    One reader for the one place a ref is written, so a second consumer cannot
    quietly invent a different key for it.
    """
    chart_id = (node.get("meta") or {}).get("chartId")
    if isinstance(chart_id, str) and chart_id.startswith(REF_PREFIX):
        return chart_id[len(REF_PREFIX) :]
    return None


def hosted_refs(plan: dict[str, Any]) -> set[str]:
    """Refs a composing parent draws inside itself, so the grid must not.

    Only a parent that is itself on the grid hosts anything. A container the
    run gave up on -- stage C dropped it, or its plugin would not generate or
    compile -- draws nothing, and the charts it listed are ordinary charts
    that need a cell of their own. Reading `children` off every decision
    deleted eight of eleven built charts from the grid as "drawn by its
    parent", for parents that did not exist, and Superset appended them at
    the foot of the page at its default size.
    """
    return {
        str(child)
        for decision in plan.get("decisions") or []
        if isinstance(decision, dict)
        and decision.get("decision") not in NON_GRID_DECISIONS
        for child in decision.get("children") or []
    }


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
    children = hosted_refs(plan)
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


def strip_header_allowance(
    position: dict[str, Any], headerless_refs: set[str]
) -> list[str]:
    """Give back the height reserved for a chart header that is hidden.

    Stage E adds `CHART_HEADER_UNITS` to every card because Superset's slice
    header eats into the content area. Where the chrome pass hides that header,
    the allowance reserves space for nothing and the card stands taller than
    the design draws it -- which is how a page heading ended up in a box twice
    its height with its caption still clipped by the bottom edge.

    Done a whole row at a time, and only when *every* chart in that row is
    headerless. Superset lays a row out as one band, so shrinking one card in a
    mixed row would leave its siblings disagreeing about their own height --
    the exact fault `normalise` exists to prevent, reintroduced after it ran.

    Mechanical, and done here rather than in the prompt: the model cannot see
    the chrome decision, and a rule it applies by hand is a rule it applies
    inconsistently across twelve regions.
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
        charts = [c for c in children if c.get("type") == "CHART"]
        if not charts or len(charts) != len(children):
            # A row holding anything but charts -- a markdown heading, a
            # divider -- keeps its height: those carry no header allowance to
            # give back, so the row's band is already theirs.
            continue
        if not all(ref_of(chart) in headerless_refs for chart in charts):
            continue
        heights = {
            chart["meta"].get("height")
            for chart in charts
            if isinstance(chart.get("meta"), dict)
        }
        if len(heights) != 1 or not isinstance(next(iter(heights)), int):
            continue
        height = next(iter(heights))
        # Never below the grid's own floor: a card with no header still has to
        # hold its content.
        reduced = max(GRID_MIN_ROW_UNITS, height - CHART_HEADER_UNITS)
        if reduced == height:
            continue
        for chart in charts:
            chart["meta"]["height"] = reduced
        notes.append(
            f"{row_id}: height {height} -> {reduced}, no chart header is drawn "
            "on this row"
        )
    return notes


def min_width_refs(
    design_analysis: dict[str, Any], plan: dict[str, Any]
) -> dict[str, int]:
    """Refs that need a column floor independent of their measured bbox, and
    how wide.

    Only `filter`-role regions today -- the one documented case (a date-range
    pill truncating its year). A chart's content is whatever stage D
    configures it to show, which this stage never sees, so it has no basis to
    second-guess the design's own fraction for anything else; widening a
    heading or a KPI tile on the same theory would be a guess with no
    evidence behind it.
    """
    regions = {
        str(r.get("region_id")): r
        for r in design_analysis.get("regions") or []
        if isinstance(r, dict)
    }
    floors: dict[str, int] = {}
    for decision in plan.get("decisions") or []:
        if not isinstance(decision, dict):
            continue
        if decision.get("decision") in NON_GRID_DECISIONS:
            continue
        ref = decision.get("ref")
        if not ref:
            continue
        region = regions.get(str(decision.get("region_id")))
        if isinstance(region, dict) and region.get("role") == "filter":
            floors[str(ref)] = GRID_MIN_FILTER_COLUMNS
    return floors


def enforce_min_width(position: dict[str, Any], floors: dict[str, int]) -> list[str]:
    """Raise a CHART's width to its role's column floor, mechanically.

    `E_layout.md` computes width as a direct fraction of the design's bbox --
    correct for a chart, wrong for a widget whose content is fixed text a
    narrow design draws too small for. Left to a prompt rule the model could
    round past every time; enforced here instead.

    Done a row at a time, mirroring `strip_header_allowance`: growing the
    floored card can push its row over the grid's own 12-column ceiling, so
    the widest other sibling gives back exactly what the floor took, the same
    trade the prompt's own overflow rule already makes by hand.
    """
    if not floors:
        return []
    notes: list[str] = []
    for row_id, row in position.items():
        if not isinstance(row, dict) or row.get("type") != "ROW":
            continue
        charts = [
            position[c]
            for c in row.get("children", [])
            if isinstance(position.get(c), dict) and position[c].get("type") == "CHART"
        ]
        grown: list[dict[str, Any]] = []
        for chart in charts:
            ref = ref_of(chart)
            meta = chart.get("meta") or {}
            width = meta.get("width")
            floor = floors.get(ref) if ref is not None else None
            if floor is None or not isinstance(width, int) or width >= floor:
                continue
            meta["width"] = floor
            grown.append(chart)
            notes.append(
                f"{row_id}: width {width} -> {floor}, {ref!r} is a filter "
                "and needs room for its own fixed text, not the design's "
                "narrower fraction"
            )
        if not grown:
            continue
        total = sum((c.get("meta") or {}).get("width") or 0 for c in charts)
        overflow = total - GRID_COLUMN_COUNT
        if overflow > 0:
            widest = max(
                (c for c in charts if c not in grown),
                key=lambda c: (c.get("meta") or {}).get("width") or 0,
                default=None,
            )
            if widest is not None:
                meta = widest["meta"]
                reduced = max(1, (meta.get("width") or 0) - overflow)
                notes.append(
                    f"{row_id}: width {meta.get('width')} -> {reduced}, "
                    "shrunk to keep the row at 12 after the filter's own floor"
                )
                meta["width"] = reduced
    return notes


def action_link_refs(design_analysis: dict[str, Any], plan: dict[str, Any]) -> set[str]:
    """Refs whose card draws a `link` action -- e.g. "View all ->" -- with no
    header of its own left to hold it.

    Stage A's own chrome reading already answers this without asking the
    runner's global menu setting (`menus`), which never reaches this stage:
    the chrome resolver hides Superset's overflow menu unconditionally
    whenever a region draws its own action, whatever that setting is -- the
    design drew its own control, and Superset's menu would be a second one
    sitting beside it. A `link` action is therefore always rendered inside
    the plugin's own body, never in a header that no longer exists for it.
    """
    regions = {
        str(r.get("region_id")): r
        for r in design_analysis.get("regions") or []
        if isinstance(r, dict)
    }
    refs: set[str] = set()
    for decision in plan.get("decisions") or []:
        if not isinstance(decision, dict):
            continue
        if decision.get("decision") in NON_GRID_DECISIONS:
            continue
        ref = decision.get("ref")
        if not ref:
            continue
        region = regions.get(str(decision.get("region_id")))
        chrome_value = region.get("chrome") if isinstance(region, dict) else None
        if not isinstance(chrome_value, dict):
            continue
        actions = chrome_value.get("actions")
        if not isinstance(actions, list):
            continue
        if any(isinstance(a, dict) and a.get("kind") == "link" for a in actions):
            refs.add(str(ref))
    return refs


def add_action_link_allowance(position: dict[str, Any], refs: set[str]) -> list[str]:
    """Give height back for a `link` action drawn in the body instead of a
    header -- the mirror of `strip_header_allowance`, which only ever takes
    height away.

    Same row-at-a-time restriction and for the same reason: Superset lays a
    row out as one band, so growing one card without its siblings agreeing
    would trade one clipped card for a row of mismatched ones.
    """
    if not refs:
        return []
    notes: list[str] = []
    for row_id, row in position.items():
        if not isinstance(row, dict) or row.get("type") != "ROW":
            continue
        children = [
            position[c]
            for c in row.get("children", [])
            if isinstance(position.get(c), dict)
        ]
        charts = [c for c in children if c.get("type") == "CHART"]
        if not charts or len(charts) != len(children):
            continue
        if not all(ref_of(chart) in refs for chart in charts):
            continue
        heights = {
            chart["meta"].get("height")
            for chart in charts
            if isinstance(chart.get("meta"), dict)
        }
        if len(heights) != 1 or not isinstance(next(iter(heights)), int):
            continue
        height = next(iter(heights))
        grown = height + ACTION_LINK_UNITS
        for chart in charts:
            chart["meta"]["height"] = grown
        notes.append(
            f"{row_id}: height {height} -> {grown}, a link action is drawn "
            "in this row's body with no header left to hold it"
        )
    return notes


_MARKDOWN_EMPHASIS = re.compile(r"^[*_#\s]+|[*_\s]+$")


def _first_line(text: str) -> str:
    """`text`'s first non-blank line, its markdown emphasis stripped.

    A `grid_text` decision's `text` is markdown -- `"**Title**\n\nSubtitle."`
    -- and a placed node's own `meta.text` carries only the plain title. This
    is the plain form of that first line, so the two can be matched by content
    rather than by a ref neither node type carries.
    """
    for line in text.splitlines():
        if stripped := _MARKDOWN_EMPHASIS.sub("", line).strip():
            return stripped
    return ""


def _reject_overlong_grid_text(
    position: dict[str, Any], plan: dict[str, Any]
) -> list[str]:
    """Flag a `grid_text` decision that reached layout carrying more than one
    line -- and make sure the `HEADER` node built from it never grows a
    second line it has nowhere to put.

    Stage C's own validator is supposed to catch this before a plan ever gets
    here: a heading with a subtitle is `configure: custom_text`, not
    `grid_text`, precisely because neither native node this pipeline is
    willing to build can hold it -- `HEADER` takes one line, and `MARKDOWN`
    takes more but always renders inside a scrolling container no design
    draws. This is the fallback for a plan that slipped through anyway: it
    does not invent a second node type to work around the gap, it truncates
    to the title alone (a `HEADER` node can always hold at least that) and
    says so, the same way a lost section is recorded rather than silently
    dropped.
    """
    notes: list[str] = []
    for decision in plan.get("decisions") or []:
        if not isinstance(decision, dict):
            continue
        if decision.get("decision") not in NON_CHART_DECISIONS:
            continue
        text = str(decision.get("text") or "")
        if "\n" not in text.strip():
            continue
        heading = _first_line(text)
        if not heading:
            continue
        for node_id, node in position.items():
            if not isinstance(node, dict) or node.get("type") != "HEADER":
                continue
            meta = node.get("meta")
            if not isinstance(meta, dict):
                continue
            if _first_line(str(meta.get("text") or "")) != heading:
                continue
            meta["text"] = heading
            notes.append(
                f"{node_id}: kept to its title alone -- {decision.get('region_id')} "
                "carries more than one line, which belongs in a "
                "configure: custom_text decision, not grid_text"
            )
            break
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
            if node.get("type") == "HEADER":
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
    corrections = (
        drop_composed_children(position, plan)
        + _reject_overlong_grid_text(position, plan)
        + enforce_min_width(position, min_width_refs(design_analysis, plan))
        + normalise(position)
        + add_action_link_allowance(position, action_link_refs(design_analysis, plan))
    )
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
    child_refs = hosted_refs(plan)
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

    problems.extend(_text_content_problems(position, plan))
    problems.extend(_row_underflow_problems(position, layout))

    return problems


# How far under 12 a row's widths may fall before it is treated as unfinished
# arithmetic rather than a deliberate gap. Matches `E_layout.md`'s own rule --
# "if it underflows by 1-2, widen the widest child" -- so a check and the
# prompt it backs up cannot silently drift apart.
ROW_UNDERFLOW_MARGIN = 2


def _row_underflow_problems(
    position: dict[str, Any], layout: dict[str, Any]
) -> list[str]:
    """A row left short of the grid's 12 columns, with nothing on record
    saying why.

    `E_layout.md` already tells the model to widen the widest child when a
    row underflows by 1-2 columns -- but a prompt rule is not a check, and a
    real run left a row at 5 of 12 with the underflow reasoned away as "the
    design's intent", while the actual page drew the item left-aligned
    instead of anchored where the design placed it. `adjustments` is where a
    genuine, deliberate gap belongs on record -- the same place an overflow
    shrink is recorded; a row underflowing with no entry there is not a
    documented design choice, it is arithmetic nobody finished. This is the
    same single severity tier every other check in this function uses: a
    problem fails the run, so a real underflow either gets fixed or gets
    written down as `adjustments` say why.
    """
    justified = {
        str(entry.get("row_id"))
        for entry in layout.get("adjustments") or []
        if isinstance(entry, dict)
    }
    problems: list[str] = []
    for node_id, node in position.items():
        if not isinstance(node, dict) or node.get("type") != "ROW":
            continue
        children = node.get("children") or []
        if not children:
            continue
        total = sum(
            ((position.get(c) or {}).get("meta") or {}).get("width") or 0
            for c in children
        )
        gap = GRID_COLUMN_COUNT - total
        if 1 <= gap <= ROW_UNDERFLOW_MARGIN and node_id not in justified:
            problems.append(
                f"{node_id}: child widths sum to {total}, {gap} short of "
                f"{GRID_COLUMN_COUNT} with no adjustment on record -- widen "
                "the widest child or record why the gap is deliberate"
            )
    return problems


def _text_content_problems(position: dict[str, Any], plan: dict[str, Any]) -> list[str]:
    """A `grid_text` decision carrying more than the one line a `HEADER` node
    can hold.

    Stage C's own validator is supposed to reject this before it ever reaches
    layout -- a heading with a subtitle is `configure: custom_text`, never
    `grid_text` -- so a decision still shaped this way here is a plan that
    got through anyway. `_reject_overlong_grid_text` has already truncated
    whatever `HEADER` node it built down to the title alone rather than
    inventing a second node type to hold the rest, so the fault to report is
    the decision itself, not a node that failed to reproduce it.
    """
    return [
        f"{decision.get('region_id')}: grid_text carries more than one line "
        "-- a HEADER node can only hold the title; this needs "
        "configure: custom_text instead"
        for decision in plan.get("decisions") or []
        if isinstance(decision, dict)
        and decision.get("decision") in NON_CHART_DECISIONS
        and "\n" in str(decision.get("text") or "").strip()
    ]


def ensure_uuids(position: dict[str, Any]) -> dict[str, Any]:
    """Fill in any missing CHART uuid so the frontend can drag nodes."""
    for node in position.values():
        if isinstance(node, dict) and node.get("type") == "CHART":
            meta = node.setdefault("meta", {})
            if not meta.get("uuid"):
                meta["uuid"] = str(uuid.uuid4())
    return position
