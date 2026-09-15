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
from superset.design_to_dashboard.gate_a import GAP_AMBIGUITY
from superset.design_to_dashboard.llm.base import LLMProvider
from superset.design_to_dashboard.pipeline.tool_loop import extract_json
from superset.design_to_dashboard.registry import Registry
from superset.utils import json

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

# A wrapper claiming its children are switched rather than just grouped has to
# say what actually differs between them -- a different query or a different
# renderer, not merely a control that happens to switch views. "none" needs no
# such claim: it is not asserting the children are interchangeable.
FRAMES_NEEDING_WHY = {"tabs", "toggle"}

# Boxes are read off a picture by eye, so they do not land exactly. This slack
# is for that, not for a different coordinate system.
BBOX_SLACK = 0.02

# How much of a child has to lie within its declared parent. Cards butt up
# against the frames around them and a border has thickness, so this is
# deliberately short of total containment.
INSIDE = 0.9

# How much two siblings under the same parent may overlap each other, as a
# fraction of the smaller one's area. A shared border or a rounding slack
# explains a sliver; two boxes drawn mostly on top of each other means one of
# them is in the wrong place, not that the design overlaps its own sections.
SIBLING_OVERLAP_MAX = 0.15

# One repair pass. Reading the design is the longest call in the pipeline, so a
# blind re-ask was rightly refused -- but the problems are mechanical and now
# in hand, and losing a whole run to a single bad enum value is worse than one
# extra call. Every other stage already repairs this way.
MAX_ATTEMPTS = 2

# Regions whose `stock_candidate` is meaningless: a wrapper is a frame we write
# ourselves, and no registered viz type composes one.
NO_STOCK_CANDIDATE = {"wrapper"}

# --- fields the stage A / stage B gate adds on a revision pass ----------------
#
# Absent (`None`/not present) on a first-pass reading -- `run()` does not ask
# for them, and old readings without them still validate. They exist so the
# gate in `gate_a.py` has somewhere to write the user's answers back onto the
# region stage B will eventually read; stage B itself does not consume them
# yet (that is the deferred follow-up).

# Whether a region is built against a real, registered viz type or a plugin
# generated for it. Meaningless on a wrapper, which is never in the registry.
PLUGIN_CHOICES = {"stock", "custom"}

# What kind of control a `filter` region is, closing the gap where stage B
# otherwise infers this from prose (`B_design_data.md` Step 5).
FILTER_KINDS = {"date_range", "select", "search", "other"}


def build_system_prompt(
    prompts_dir: pathlib.Path, registry: Registry | None = None
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
    if registry:
        # Names only. Stage C makes the decision and gets the descriptions;
        # stage A needs just enough to spell a candidate correctly.
        parts.append(
            "## Registered viz types\n\n"
            "Consult this only for a leaf region's `stock_candidate`, and only "
            "after you have written what you see. A plugin that is *close* is "
            "not a match.\n\n" + registry.stage_a_text()
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


def _overlap_fraction(
    a: tuple[float, float, float, float], b: tuple[float, float, float, float]
) -> float:
    """How much two boxes overlap, as a fraction of the smaller one's area."""
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    overlap_w = max(0.0, min(ax + aw, bx + bw) - max(ax, bx))
    overlap_h = max(0.0, min(ay + ah, by + bh) - max(ay, by))
    return (overlap_w * overlap_h) / min(aw * ah, bw * bh)


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


def _validate_sibling_overlap(
    regions: list[dict[str, Any]], by_number: dict[int, dict[str, Any]]
) -> list[str]:
    """Two children of the same parent should not be drawn on top of each other.

    Containment only checks a child against its own parent, so a block of
    sibling boxes that all drifted the same direction -- a KPI tile's box
    landing on the table drawn below it, say -- passes it cleanly: each box is
    still inside the wrapper, just not where its own title says it is. This
    check is a different, complementary signal: it does not know whether a box
    is *accurate*, only whether two boxes that are supposed to be different
    sections have been drawn overlapping each other, which a design never
    draws on purpose.
    """
    problems: list[str] = []
    for region in regions:
        children = [
            c
            for c in (region.get("children") or [])
            if isinstance(c, int) and c in by_number
        ]
        for i, first in enumerate(children):
            for second in children[i + 1 :]:
                a, b = _box(by_number[first]), _box(by_number[second])
                if not a or not b:
                    continue
                overlap = _overlap_fraction(a, b)
                if overlap > SIBLING_OVERLAP_MAX:
                    problems.append(
                        f"{_label(by_number[first])} and "
                        f"{_label(by_number[second])}: both children of "
                        f"{_label(region)}, but their boxes overlap by "
                        f"{overlap:.0%} -- siblings should not draw over each "
                        "other; recheck both boxes against the image"
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


def _validate_gate_fields(region: dict[str, Any]) -> list[str]:
    """The optional fields a stage A/B gate revision may add.

    Absent is always fine -- a first-pass reading never sets these. Present
    and wrong is the only failure, the same posture `_validate_chrome` takes
    toward `chrome`.
    """
    problems: list[str] = []
    if (choice := region.get("plugin_choice")) is not None:
        if region.get("role") == "wrapper":
            problems.append(
                f"{_label(region)}: plugin_choice {choice!r} on a wrapper -- a "
                "wrapper is a frame this pipeline writes itself, not a plugin"
            )
        elif choice not in PLUGIN_CHOICES:
            problems.append(
                f"{_label(region)}: plugin_choice {choice!r} is not one of "
                f"{sorted(PLUGIN_CHOICES)}"
            )

    if (kind := region.get("filter_kind")) is not None:
        if region.get("role") != "filter":
            problems.append(
                f"{_label(region)}: filter_kind {kind!r} on a {region.get('role')!r} "
                "region -- only a filter region has one"
            )
        elif kind not in FILTER_KINDS:
            problems.append(
                f"{_label(region)}: filter_kind {kind!r} is not one of "
                f"{sorted(FILTER_KINDS)}"
            )

    reads_data = region.get("wrapper_reads_data")
    if reads_data is not None and not isinstance(reads_data, bool):
        problems.append(
            f"{_label(region)}: wrapper_reads_data {reads_data!r} is not true or false"
        )

    series = region.get("has_embedded_series")
    if series is not None and not isinstance(series, bool):
        problems.append(
            f"{_label(region)}: has_embedded_series {series!r} is not true or false"
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


def _validate_tabs(regions: list[dict[str, Any]], global_: dict[str, Any]) -> list[str]:
    """Every region has a `tab` when the design switches between tabs, and it
    names one of `global.tabs`'s own labels.

    `global.image_set.kind == "tabs"` is the model's explicit verdict on the
    multi-image case this only applies to; `global.tabs` being a non-empty
    list is the corroborating fact -- the prompt has the model set both
    together, so either alone is reason enough to check, and a design with
    neither is a single-page reading with nothing to check at all. The prompt
    is explicit that "every region" gets a `tab` in this case (`A_decompose_
    design.md`'s "When you are given more than one image" section), so a
    region silently missing one is a section that would not appear under any
    tab a user actually clicks.
    """
    image_set_kind = (global_.get("image_set") or {}).get("kind")
    tabs = global_.get("tabs")
    labels = [str(t) for t in tabs] if isinstance(tabs, list) else []
    if image_set_kind != "tabs" and not labels:
        return []

    label_set = set(labels)
    problems: list[str] = []
    for region in regions:
        tab = region.get("tab")
        if not tab:
            problems.append(
                f"{_label(region)}: no tab set, but this design switches "
                "between tabs -- every region needs one, or it never appears "
                "under any of them"
            )
        elif label_set and str(tab) not in label_set:
            problems.append(
                f"{_label(region)}: tab {tab!r} does not match any label in "
                f"global.tabs ({labels})"
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
        frame_why = region.get("frame_why")
        if role == "wrapper":
            if frame not in FRAMES:
                problems.append(
                    f"{_label(region)}: frame {frame!r} is not one of "
                    f"{sorted(FRAMES)} -- say what this wrapper's own chrome "
                    "does to the sections it holds"
                )
            if frame in FRAMES_NEEDING_WHY and not (
                isinstance(frame_why, str) and frame_why.strip()
            ):
                problems.append(
                    f"{_label(region)}: frame is {frame!r} but frame_why is "
                    f"{frame_why!r} -- name what actually differs between the "
                    "children (a different query, a different renderer), not "
                    "just that a control switches them"
                )
        elif frame is not None:
            problems.append(
                f"{_label(region)}: frame is {frame!r} but only a wrapper has "
                "one; a leaf region frames nothing"
            )

        problems += _validate_chrome(region)
        problems += _validate_gate_fields(region)

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
    problems += _validate_sibling_overlap(regions, by_number)
    problems += _validate_same_as(regions, by_number)

    global_ = design_analysis.get("global") or {}
    order = global_.get("reading_order")
    if not isinstance(order, list):
        problems.append("global.reading_order is missing")
    else:
        listed = {n for n in order if isinstance(n, int)}
        for missing in sorted(seen - listed):
            problems.append(f"reading_order omits region {missing}")
        for unknown in sorted(listed - seen):
            problems.append(f"reading_order names an unknown region: {unknown}")

    problems += _validate_tabs(regions, global_)

    return problems


_REGION_IN_PROBLEM = re.compile(r"\bregion (\d+)\b")


def _regions_named_in(problems: list[str]) -> set[int]:
    """Every region number a validation problem was actually about.

    `_label` writes every per-region problem as `"region {n} ..."`, so this is
    the same text read backwards: the numbers a repair pass was asked to fix.
    A region absent from this set had nothing wrong with it last attempt.
    """
    found: set[int] = set()
    for problem in problems:
        found.update(int(n) for n in _REGION_IN_PROBLEM.findall(problem))
    return found


def _restore_untouched_chrome(
    regions: list[dict[str, Any]],
    previous: list[dict[str, Any]],
    named: set[int],
) -> list[str]:
    """Undo a chrome or frame change a repair pass was never asked to make.

    A repair prompt lists what was wrong and says "keep everything that was
    right", but the reply is the whole analysis regenerated, not a patch --
    stage C's `merge_patch` exists for exactly this reason, and stage A has no
    equivalent. A retry meant to fix one region's `chrome.actions` has been
    seen to silently flip an unrelated region's `chrome.surface` from `bare`
    to `card` in the same reply, its own `why` still describing a bare region
    -- corrupting the one field that decides whether Superset draws a card the
    design never showed. `frame`/`frame_why` get the same guard, for the same
    reason: it decides whether a section becomes a wrapper with children at
    all. Mechanical here because a model correcting what it was told is not
    the same act as a model changing what it was not told to, and only the
    first one earns the trust `_repair_note` asks for.
    """
    notes: list[str] = []
    before = {region["n"]: region for region in previous if isinstance(region, dict)}
    for region in regions:
        number = region.get("n")
        if not isinstance(number, int) or number in named:
            continue
        prior = before.get(number)
        if not isinstance(prior, dict):
            continue
        was, now = prior.get("chrome"), region.get("chrome")
        if isinstance(was, dict) and was != now:
            region["chrome"] = was
            notes.append(
                f"region {number}: chrome reverted to the previous attempt's "
                f"reading ({was.get('surface')!r}) -- this region was not named "
                "in what the repair was asked to fix"
            )

        was_frame, now_frame = prior.get("frame"), region.get("frame")
        if was_frame is not None and was_frame != now_frame:
            region["frame"] = was_frame
            region["frame_why"] = prior.get("frame_why")
            notes.append(
                f"region {number}: frame reverted to the previous attempt's "
                f"reading ({was_frame!r}) -- this region was not named in what "
                "the repair was asked to fix"
            )
    return notes


def _repair_note(problems: list[str]) -> str:
    """The previous reading's faults, to be fixed rather than re-derived."""
    listed = "\n".join(f"- {problem}" for problem in problems)
    return (
        "\n\nYour previous reading of this design failed these checks. They are "
        "mechanical, not matters of taste -- an enum value that is not in the "
        "list, a box outside the image, a child that is not inside its parent. "
        "Keep everything that was right and return the whole analysis again "
        "with each of these fixed. A region not named below had nothing wrong "
        "with it: repeat its fields exactly, `chrome` included -- a `bare` "
        "reading changed to `card` in this pass, for a region the list below "
        "never mentions, is a second fault this repair introduced, checked "
        "the same as the first.\n"
        f"{listed}"
    )


def run(
    provider: LLMProvider,
    requirement: str,
    image_paths: list[str],
    prompts_dir: pathlib.Path,
    on_thinking: Any = None,
    attempts: int = MAX_ATTEMPTS,
    registry: Registry | None = None,
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
    system_prompt = build_system_prompt(prompts_dir, registry)
    user_prompt = build_user_prompt(requirement)
    known = registry.viz_types() if registry else None
    cost = 0.0
    analysis: dict[str, Any] = {}
    # What the previous attempt read, and which regions its problems actually
    # named -- so a region a repair pass was not asked to touch can have any
    # drift in its chrome undone rather than shipped.
    previous_regions: list[dict[str, Any]] | None = None
    named: set[int] = set()

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

        if previous_regions is not None and isinstance(analysis.get("regions"), list):
            if reverted := _restore_untouched_chrome(
                analysis["regions"], previous_regions, named
            ):
                logger.info("stage A repair regressed unasked regions: %s", reverted)

        problems = validate(analysis, known)
        previous_regions = list(analysis.get("regions") or [])
        named = _regions_named_in(problems)
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


# --- revising a reading with the gate's answers --------------------------------
#
# `run()` reads the design cold. This is the second pass: the same model is
# shown its own reading, the questions the gate raised from it (see
# `gate_a.py`), and what the user answered, and is asked to return the whole
# analysis again with the new gate fields set and anything an answer corrected
# fixed in place -- the same "keep what was right, redo the whole document"
# shape `_repair_note` already uses for a failed validation, because the two
# situations are the same request: the model was told what to change, not
# given a diff to apply.

REVISION_INSTRUCTIONS = """\
## Revising your reading

You are looking at this design again. Below is your own previous reading of
it, a list of questions raised against specific regions, and the user's
answers. Return the whole analysis again, in the same shape as before, with:

- **Every region unchanged except where an answer bears on it.** An answer
  about region 6 is not licence to also change region 9's `chrome` -- the same
  rule the repair pass follows.
- **`plugin_choice` set on every leaf region** (never on a wrapper): `"stock"`
  or `"custom"`. Use the user's answer where one was given for that region;
  otherwise keep the recommendation you were shown (their `stock_candidate`
  reading if one exists, `"custom"` otherwise).
- **`wrapper_reads_data`** (`true`/`false`) set on any region a
  `wrapper_reads_data` question was asked about, from the answer. Where the
  answer says it does read data, also update `implied_data` to say what, and
  clear `role`/`chrome` inconsistencies that follow from it.
- **`has_embedded_series`** (`true`/`false`) set on any region a
  `wrapper_reads_data`-adjacent embedded-series question was asked about.
  Where true, make sure `axis_formats` and `implied_data` describe that
  series, not just the headline value.
- **`filter_kind`** (`"date_range"|"select"|"search"|"other"`) set on every
  `filter` region from its answer, defaulting to your own best reading of
  `observed` where the user did not say.
- **`data_notes`** — a short string on any region an answer changed the data
  story for (e.g. "shares one table with r07/r08, filtered by provider" for a
  shared-grain answer). `null` where nothing changed.
- Where an answer resolved an `ambiguity`, clear it (`null`) and fold the
  resolution into `observed`/`implied_data` instead of leaving it flagged.

Everything else about the contract -- roles, nesting, `same_as`, geometry --
still applies and is still checked.
"""

# Prefix `_mark_unanswered_ambiguities` puts on a region's surviving
# `ambiguity` so a later stage can tell "never asked" from "asked at the gate
# and the user skipped it" -- the two look identical otherwise, since both
# leave the field untouched.
UNANSWERED_AMBIGUITY_PREFIX = "(asked at review, left unanswered) "


def _mark_unanswered_ambiguities(
    regions: list[dict[str, Any]],
    questions: list[dict[str, Any]],
    answers: dict[str, str],
) -> None:
    """Flag, in place, an ambiguity the gate put to the user and got no
    answer to.

    An `ambiguity` question the user skips is not withdrawn -- `revise`'s own
    instructions leave it in `region.ambiguity` exactly as it read before,
    because nothing resolved it. That is indistinguishable from a region the
    gate never asked about at all, and stage C is told to ask about "anything
    still ambiguous", so it re-raises the identical question the user already
    passed on. Marked here, deterministically, rather than left to the model
    to remember on every revision pass: this is a fact about which questions
    were asked and answered, not a judgement the model has any latitude on.
    """
    asked_and_unanswered = {
        q.get("region_id")
        for q in questions
        if isinstance(q, dict)
        and q.get("gap") == GAP_AMBIGUITY
        and q.get("region_id")
        and q.get("id") not in answers
    }
    if not asked_and_unanswered:
        return
    for region in regions:
        if not isinstance(region, dict) or region.get("region_id") not in (
            asked_and_unanswered
        ):
            continue
        ambiguity = region.get("ambiguity")
        if (
            isinstance(ambiguity, str)
            and ambiguity
            and not ambiguity.startswith(UNANSWERED_AMBIGUITY_PREFIX)
        ):
            region["ambiguity"] = UNANSWERED_AMBIGUITY_PREFIX + ambiguity


def build_revision_user_prompt(
    design_analysis: dict[str, Any],
    questions: list[dict[str, Any]],
    answers: dict[str, str],
    plugin_choices: dict[str, str] | None = None,
) -> str:
    """The prior reading, what was asked, and what the user said.

    `plugin_choices` is separate from free-text `answers` because it is a
    structured choice the gate's UI collects directly (a two-option control,
    not a text box) -- keeping it out of the same dict as prose answers means
    the model is never asked to parse "stock" back out of a sentence.
    """
    answered = [
        {**q, "answer": answers.get(q["id"], "(not answered)")} for q in questions
    ]
    payload = {
        "previous_reading": design_analysis,
        "questions_and_answers": answered,
        "plugin_choices": plugin_choices or {},
    }
    return REVISION_INSTRUCTIONS + f"\n```json\n{json.dumps(payload, indent=2)}\n```"


def revise(
    provider: LLMProvider,
    design_analysis: dict[str, Any],
    questions: list[dict[str, Any]],
    answers: dict[str, str],
    prompts_dir: pathlib.Path,
    plugin_choices: dict[str, str] | None = None,
    image_paths: list[str] | None = None,
    on_thinking: Any = None,
    attempts: int = MAX_ATTEMPTS,
    registry: Registry | None = None,
) -> tuple[dict[str, Any], float]:
    """Fold the gate's answers into the reading. Returns ``(revised, cost_usd)``.

    One call, validated and repaired exactly the way `run()` repairs a first
    reading -- the failure modes are the same JSON, so the machinery is. The
    design image is passed again, not just the previous text: an answer like
    "yes, wire the sparkline" is instruction stage A still has to read the
    span and shape of off the picture, the same as on the first pass.
    """
    system_prompt = build_system_prompt(prompts_dir, registry)
    user_prompt = build_revision_user_prompt(
        design_analysis, questions, answers, plugin_choices
    )
    known = registry.viz_types() if registry else None
    cost = 0.0
    analysis: dict[str, Any] = {}
    previous_regions: list[dict[str, Any]] | None = None
    named: set[int] = set()

    for attempt in range(1, attempts + 1):
        response = provider.complete(
            system_prompt,
            user_prompt,
            image_paths or [],
            on_thinking=on_thinking,
        )
        cost += response.cost_usd or 0.0
        analysis = extract_json(response.text)

        if analysis.get("status") in {"unreadable", "separate_designs"}:
            return analysis, cost

        if previous_regions is not None and isinstance(analysis.get("regions"), list):
            _restore_untouched_chrome(analysis["regions"], previous_regions, named)

        problems = validate(analysis, known)
        previous_regions = list(analysis.get("regions") or [])
        named = _regions_named_in(problems)
        if not problems or attempt == attempts:
            if problems:
                logger.warning(
                    "stage A revision still has %d problem(s) after %d attempt(s)",
                    len(problems),
                    attempt,
                )
            analysis = assign_region_ids(analysis)
            if isinstance(analysis.get("regions"), list):
                _mark_unanswered_ambiguities(analysis["regions"], questions, answers)
            return analysis, cost

        logger.info(
            "stage A revision attempt %d had %d problem(s); asking again",
            attempt,
            len(problems),
        )
        user_prompt = build_revision_user_prompt(
            design_analysis, questions, answers, plugin_choices
        ) + _repair_note(problems)

    analysis = assign_region_ids(analysis)
    if isinstance(analysis.get("regions"), list):
        _mark_unanswered_ambiguities(analysis["regions"], questions, answers)
    return analysis, cost
