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
"""Who draws the card: Superset's chart holder, or nobody.

Superset wraps every chart in a holder that paints a background, pads it, and
puts a title and an overflow menu on top. A design almost never draws that
menu, and often does not draw the card either -- a page heading and a filter
band sit directly on the page. The pipeline used to answer this by telling
each generated plugin to paint the design's card *inside* Superset's, which
produced two cards, two titles, and a heading whose caption was clipped by a
card it never asked for.

It could not have worked. The plugin rules reject a literal colour in plugin
source, and a design's card is a literal colour: `1px solid #E2E8F0`. A plugin
either matched the design and failed validation, or passed validation with
theme tokens and did not match the design. The dashboard's own `css` field is
the one writable surface where the design's hex is legal, and every holder
already carries a `dashboard-chart-id-<id>` class put there for exactly this.

So the holder *becomes* the design's card, restyled once from the contract,
and regions the design draws bare have it taken away again. Plugins draw
content and nothing else.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

# What stage A may say about the surface a region sits on. The question put to
# it is a counterfactual rather than a taxonomy -- "if Superset drew its
# standard card here, would the design change?" -- because that is a question
# about pixels, which is what stage A is looking at.
SURFACES = {"card", "bare"}

# Whether a title is drawn inside the region, and whether Superset could draw
# it. Superset's slice header renders plain text only, so a label with an icon
# before it is `decorated` and the plugin has to own it.
TITLE_KINDS = {"none", "plain", "decorated"}

# The answers to the one question this module puts to the user.
MENU_ALL = "all"
MENU_NONE = "none"
MENU_DATA_ONLY = "data_only"
MENU_CHOICES = (MENU_DATA_ONLY, MENU_ALL, MENU_NONE)

# The key the user's answer comes back under.
MENU_QUESTION_ID = "chrome_menus"

# Decisions that never reach the grid, so never carry chrome.
NOT_ON_GRID = {"drop"}

# Decisions that become a text node rather than a chart. A text node has no
# slice header to hide and no holder title to duplicate.
TEXT_DECISIONS = {"grid_text"}

# What a viewer loses when the overflow menu goes. Named here rather than in
# the prompt because the user asked to be told what removing it costs, and a
# list the model rewrites each run is a list that quietly drops an entry.
MENU_AFFORDANCES = (
    "drill to detail",
    "drill by",
    "view as table",
    "view query",
    "export to CSV, XLSX and image",
    "full screen",
    "force refresh",
)

# Actions a plugin can genuinely rebind to a control the design draws. The rest
# of `MENU_AFFORDANCES` lives in Superset's own header and cannot be reached
# from inside a viz plugin, which is the honest half of the answer.
REBINDABLE = {"refresh", "filter", "cross_filter", "expand", "link", "download"}


@dataclass
class RegionChrome:
    """What Superset should draw around one region, and what that costs."""

    region_id: str
    ref: str | None = None
    surface: str = "card"
    # Who draws the title: `superset` (its slice header), `plugin` (the region
    # draws its own, so Superset's is hidden), or `none`.
    title: str = "superset"
    menu: bool = True
    # Controls the design itself draws on this region, carried through so
    # stage F builds them and so the disclosure can say which were rebound.
    drawn_actions: list[dict[str, Any]] = field(default_factory=list)
    why: str = ""

    @property
    def is_chart(self) -> bool:
        return self.ref is not None


def _chrome_of(region: dict[str, Any]) -> dict[str, Any]:
    value = region.get("chrome")
    return value if isinstance(value, dict) else {}


def _hosted_refs(plan: dict[str, Any]) -> set[str]:
    """Refs a wrapper renders inside itself rather than beside itself."""
    return {
        str(child)
        for decision in plan.get("decisions") or []
        if isinstance(decision, dict)
        for child in decision.get("children") or []
    }


def _surface_of(observed: dict[str, Any]) -> str:
    """Whether Superset's holder should paint a card here.

    Unread chrome keeps Superset's own behaviour. A missing field is a reading
    this stage did not get, not a licence to strip a card off a design.
    """
    surface = observed.get("surface")
    return surface if surface in SURFACES else "card"


def _title_of(observed: dict[str, Any], surface: str, is_text: bool) -> str:
    """Who draws the title: Superset's slice header, the region, or nobody."""
    if is_text:
        # A text node has no slice header at all; saying `superset` here would
        # emit a rule selecting nothing.
        return "none"
    kind = observed.get("title")
    if kind not in TITLE_KINDS:
        kind = "plain"
    if kind == "none":
        return "none"
    # Superset's header renders plain text, so anything decorated is the
    # region's to draw -- and so is a title on a surface Superset is not
    # painting, since there is no header row to put it in.
    return "superset" if kind == "plain" and surface == "card" else "plugin"


def _menu_of(
    drawn: list[dict[str, Any]], surface: str, is_text: bool, menus: str
) -> bool:
    """Whether Superset's overflow menu is shown on this region."""
    if is_text:
        return False
    if drawn:
        # The design drew its own control for these. Superset's menu would be
        # a second one sitting beside it.
        return False
    if menus == MENU_ALL:
        return True
    if menus == MENU_NONE:
        return False
    return surface == "card"


def resolve(
    design_analysis: dict[str, Any],
    plan: dict[str, Any],
    menus: str = MENU_DATA_ONLY,
) -> list[RegionChrome]:
    """What to draw around each region, from what stage A saw.

    Derived here rather than asked of a model: every input is already decided
    by the time this runs, so a third opinion would only add a way to disagree
    with stage A about a design stage A is the one that looked at.
    """
    regions = {
        str(r.get("region_id")): r
        for r in design_analysis.get("regions") or []
        if isinstance(r, dict)
    }
    hosted = _hosted_refs(plan)
    resolved: list[RegionChrome] = []
    for decision in plan.get("decisions") or []:
        if not isinstance(decision, dict):
            continue
        if decision.get("decision") in NOT_ON_GRID:
            continue
        if decision.get("ref") in hosted:
            # A section rendered inside a wrapper is not a chart on the grid,
            # so it has no holder and no slice header. Every rule written for
            # it would select nothing. Its card is the wrapper's job to draw,
            # which is what the stage F prompt tells the wrapper to do.
            continue
        region_id = str(decision.get("region_id"))
        observed = _chrome_of(regions.get(region_id, {}))
        is_text = decision.get("decision") in TEXT_DECISIONS
        surface = _surface_of(observed)
        drawn = [a for a in observed.get("actions") or [] if isinstance(a, dict)]
        resolved.append(
            RegionChrome(
                region_id=region_id,
                ref=None if is_text else (decision.get("ref") or None),
                surface=surface,
                title=_title_of(observed, surface, is_text),
                menu=_menu_of(drawn, surface, is_text, menus),
                drawn_actions=drawn,
                why=str(observed.get("why") or ""),
            )
        )
    return resolved


# A contract value reaches the stylesheet verbatim, so it is checked first.
# Stage C writes these, but stage C is a model, and one stray brace would take
# the rest of the dashboard's styling down with it.
_SAFE_CSS_VALUE = re.compile(r"^[#\w\s,.()%/-]{1,120}$")


def _safe(value: Any) -> str | None:
    """A contract value that can be written into a declaration, or None."""
    if not isinstance(value, str):
        return None
    text = value.strip().rstrip(";").strip()
    return text if text and _SAFE_CSS_VALUE.fullmatch(text) else None


def _card_rules(card_chrome: dict[str, Any]) -> list[str]:
    """The design's card, as declarations for Superset's holder."""
    declarations: list[str] = []
    for key, prop in (
        ("border", "border"),
        ("radius", "border-radius"),
        ("shadow", "box-shadow"),
        ("padding", "padding"),
        ("background", "background-color"),
    ):
        if safe := _safe(card_chrome.get(key)):
            declarations.append(f"  {prop}: {safe};")
    return declarations


def _selector(entry: RegionChrome, chart_id: int) -> str:
    return f".dashboard-chart-id-{chart_id}"


def compile_css(
    entries: list[RegionChrome],
    ref_to_id: dict[str, int],
    design_system: dict[str, Any] | None = None,
    page_background: str | None = None,
) -> str:
    """The dashboard's `css` field, from the resolved chrome.

    Only charts get per-region rules: a text node's holder is addressed by a
    component id the applier rewrites, while a chart's is addressed by the
    `dashboard-chart-id-<id>` class Superset adds for the CSS editor.
    """
    contract = design_system or {}
    blocks: list[str] = [
        "/* Generated from the design. Edit the design, not this. */",
    ]

    if background := _safe(page_background):
        blocks.append(f".dashboard-content {{\n  background-color: {background};\n}}")

    card_chrome = contract.get("card_chrome")
    if isinstance(card_chrome, dict) and (rules := _card_rules(card_chrome)):
        joined = "\n".join(rules)
        blocks.append(
            "/* The holder is the design's card, so no plugin draws a second "
            "one. */\n.dashboard-component-chart-holder {\n" + joined + "\n}"
        )

    for entry in entries:
        if not entry.ref or entry.ref not in ref_to_id:
            continue
        selector = _selector(entry, ref_to_id[entry.ref])
        if entry.surface == "bare":
            blocks.append(
                f"/* {entry.region_id}: the design draws no card here. */\n"
                f"{selector} {{\n"
                "  background-color: transparent;\n"
                "  border: none;\n"
                "  box-shadow: none;\n"
                "  padding: 0;\n"
                "}"
            )
        hide_title = entry.title != "superset"
        if hide_title and not entry.menu:
            blocks.append(
                f"{selector} [data-test='slice-header'] {{\n  display: none;\n}}"
            )
            continue
        if hide_title:
            blocks.append(f"{selector} .header-title {{\n  display: none;\n}}")
        if not entry.menu:
            blocks.append(f"{selector} .header-controls {{\n  display: none;\n}}")

    return "\n\n".join(blocks) + "\n"


def effects(entries: list[RegionChrome]) -> list[str]:
    """What matching the design costs, in plain words.

    The user asked to be told this rather than to trade it away, so it is
    returned as a result of the run and not buried in a rationale field.
    """
    notes: list[str] = []
    hidden = [e for e in entries if e.is_chart and not e.menu]
    if hidden:
        affordances = ", ".join(MENU_AFFORDANCES)
        notes.append(
            f"The chart menu is hidden on {len(hidden)} chart(s) because the "
            f"design draws none. Those charts lose {affordances}. The data and "
            "the charts themselves are untouched, and showing the menu again "
            "is one edit to the dashboard's CSS."
        )
    silent = [e for e in entries if e.is_chart and e.title != "superset"]
    if silent:
        notes.append(
            f"Superset's own title is hidden on {len(silent)} chart(s), either "
            "because the design draws the title itself or draws none. Renaming "
            "a chart in place on the dashboard is no longer possible there; "
            "renaming still works from the chart list."
        )
    bare = [e for e in entries if e.surface == "bare"]
    if bare:
        named = ", ".join(sorted(e.region_id for e in bare))
        notes.append(
            f"The card is removed from {named}, which the design draws "
            "directly on the page background."
        )
    for entry in entries:
        for action in entry.drawn_actions:
            kind = str(action.get("kind") or "control")
            if kind not in REBINDABLE:
                notes.append(
                    f"{entry.region_id} draws its own {kind}. It is built as "
                    "the design shows it, but Superset's equivalent lives in "
                    "the chart header and cannot be driven from inside a "
                    "plugin, so the control is visual only."
                )
    return notes


def question(entries: list[RegionChrome]) -> dict[str, Any] | None:
    """The one thing about chrome only the user can decide.

    Asked from here rather than left to stage C: a design never draws
    Superset's overflow menu, so a model reading the design will answer "no
    menu" every time, and whether the menu is wanted is a fact about who uses
    the dashboard, not about the picture.
    """
    if not any(e.is_chart for e in entries):
        return None
    drawn = sorted(
        {str(a.get("kind")) for e in entries for a in e.drawn_actions if a.get("kind")}
    )
    context = (
        f" The design draws its own {', '.join(drawn)}, which will be built either way."
        if drawn
        else ""
    )
    return {
        # A stable id, not one `normalise_questions` invents: the runner reads
        # the answer back by this key, and a positional id would move the
        # moment stage C raises one more question of its own.
        "id": MENU_QUESTION_ID,
        "region_id": None,
        "question": (
            "The design draws no per-chart menu. Keep Superset's chart menus "
            "on this dashboard?" + context
        ),
        "why_it_matters": (
            "The menu is how a viewer reaches "
            + ", ".join(MENU_AFFORDANCES)
            + ". Hiding it matches the design exactly and takes those away."
        ),
        "options": [
            "Only on charts the design draws as cards",
            "Keep them everywhere",
            "Hide them everywhere, match the design exactly",
        ],
        "default": "Only on charts the design draws as cards",
    }


# The option text above, in the order it is offered, mapped to what it means.
ANSWER_TO_MENUS = {
    "only on charts the design draws as cards": MENU_DATA_ONLY,
    "keep them everywhere": MENU_ALL,
    "hide them everywhere, match the design exactly": MENU_NONE,
}


def menus_from_answer(answer: Any) -> str:
    """The user's reply, as one of `MENU_CHOICES`."""
    if not isinstance(answer, str):
        return MENU_DATA_ONLY
    text = answer.strip().lower()
    if choice := ANSWER_TO_MENUS.get(text):
        return choice
    if text in MENU_CHOICES:
        return text
    # A free-typed answer. Read it for intent rather than dropping to the
    # default, which would silently ignore what the user actually said.
    if "everywhere" in text and ("hide" in text or "no" in text):
        return MENU_NONE
    if "keep" in text or "show" in text:
        return MENU_ALL
    return MENU_DATA_ONLY
