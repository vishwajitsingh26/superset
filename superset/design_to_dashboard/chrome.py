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

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

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
    """Refs a wrapper renders inside itself rather than beside itself.

    A dropped wrapper hosts nothing. The runner drops a container whose plugin
    failed to build and leaves its `children` in place, so those sections are
    back on the grid as charts of their own -- each with a holder that needs
    the design's card like any other.
    """
    return {
        str(child)
        for decision in plan.get("decisions") or []
        if isinstance(decision, dict) and decision.get("decision") not in NOT_ON_GRID
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


# A contract value reaches the stylesheet verbatim, so it is checked first --
# against what the property accepts, not against a set of harmless characters.
# Stage C is a model: one stray brace would take the rest of the dashboard's
# styling down with it, and a description (`subtle drop shadow`, `16-20px`) is
# harmless to write but is not CSS, so the browser drops the declaration and
# the card quietly loses the treatment the contract promised every plugin.
_MAX_CSS_VALUE = 120

_NUMBER = r"(?:\d+(?:\.\d+)?|\.\d+)"
_UNITS = "px|rem|em|pt|pc|cm|mm|in|vh|vw|vmin|vmax|ch|ex"
_LENGTH = re.compile(rf"(?:0+(?:\.0+)?|{_NUMBER}(?:{_UNITS}))", re.IGNORECASE)
_PERCENT = re.compile(rf"{_NUMBER}%")
_HEX = re.compile(r"#(?:[0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})")
_COLOR_FUNCTION = re.compile(r"(rgba?|hsla?)\((.*)\)", re.IGNORECASE)
_COLOR_NUMBER = re.compile(rf"[+-]?{_NUMBER}")
_COLOR_PERCENT = re.compile(rf"[+-]?{_NUMBER}%")
_HUE = re.compile(rf"[+-]?{_NUMBER}(?:deg|grad|rad|turn)?", re.IGNORECASE)
_FONT_WEIGHT = re.compile(r"[1-9]\d{0,2}|1000|normal|bold|bolder|lighter")

# A span of numbers where CSS takes one: `16-20px`, `12px – 14px`, `8 to 12px`.
# A bare hyphen needs no space on either side, so a negative shadow offset
# (`0 -1px`) is not mistaken for one.
_RANGE = re.compile(r"\d[a-z%]*(?:-|\s+-\s+|\s*[–—]\s*|\s+to\s+)~?\.?\d", re.IGNORECASE)

_NAMED_COLORS = frozenset(
    """
    aliceblue antiquewhite aqua aquamarine azure beige bisque black
    blanchedalmond blue blueviolet brown burlywood cadetblue chartreuse
    chocolate coral cornflowerblue cornsilk crimson cyan darkblue darkcyan
    darkgoldenrod darkgray darkgreen darkgrey darkkhaki darkmagenta
    darkolivegreen darkorange darkorchid darkred darksalmon darkseagreen
    darkslateblue darkslategray darkslategrey darkturquoise darkviolet deeppink
    deepskyblue dimgray dimgrey dodgerblue firebrick floralwhite forestgreen
    fuchsia gainsboro ghostwhite gold goldenrod gray green greenyellow grey
    honeydew hotpink indianred indigo ivory khaki lavender lavenderblush
    lawngreen lemonchiffon lightblue lightcoral lightcyan lightgoldenrodyellow
    lightgray lightgreen lightgrey lightpink lightsalmon lightseagreen
    lightskyblue lightslategray lightslategrey lightsteelblue lightyellow lime
    limegreen linen magenta maroon mediumaquamarine mediumblue mediumorchid
    mediumpurple mediumseagreen mediumslateblue mediumspringgreen
    mediumturquoise mediumvioletred midnightblue mintcream mistyrose moccasin
    navajowhite navy oldlace olive olivedrab orange orangered orchid
    palegoldenrod palegreen paleturquoise palevioletred papayawhip peachpuff
    peru pink plum powderblue purple rebeccapurple red rosybrown royalblue
    saddlebrown salmon sandybrown seagreen seashell sienna silver skyblue
    slateblue slategray slategrey snow springgreen steelblue tan teal thistle
    tomato turquoise violet wheat white whitesmoke yellow yellowgreen
    transparent currentcolor
    """.split()
)

_BORDER_STYLES = frozenset(
    "none hidden dotted dashed solid double groove ridge inset outset".split()
)
_BORDER_WIDTHS = frozenset({"thin", "medium", "thick"})


def _split_top_level(text: str, separator: str) -> list[str] | None:
    """`text` split on `separator` outside parentheses, or None if unbalanced.

    `rgba(0, 0, 0, 0.1)` is one token of a shadow, not four.
    """
    parts: list[str] = []
    current: list[str] = []
    depth = 0
    for char in text:
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth < 0:
                return None
        if depth == 0 and (char.isspace() if separator == " " else char == separator):
            parts.append("".join(current).strip())
            current = []
        else:
            current.append(char)
    if depth:
        return None
    parts.append("".join(current).strip())
    return parts


def _tokens(text: str) -> list[str]:
    parts = _split_top_level(text, " ")
    return [part for part in parts if part] if parts is not None else []


def _is_length(token: str, *, signed: bool = False, percent: bool = True) -> bool:
    if signed and token.startswith(("-", "+")):
        token = token[1:]
    return bool(_LENGTH.fullmatch(token) or (percent and _PERCENT.fullmatch(token)))


def _is_channel(token: str) -> bool:
    return bool(_COLOR_NUMBER.fullmatch(token) or _COLOR_PERCENT.fullmatch(token))


def _is_color(token: str) -> bool:
    """A named colour, a hex, or `rgb()`/`hsl()` in one of CSS's two syntaxes.

    Counting arguments is not enough: `rgba(0 0 0 0.1)` has four numbers and
    no browser accepts it, because the space-separated form puts its alpha
    after a `/`. Either commas throughout with an optional fourth value, or
    spaces with an optional `/ alpha`; an angle only on an `hsl` hue.
    """
    if token.lower() in _NAMED_COLORS or _HEX.fullmatch(token):
        return True
    match = _COLOR_FUNCTION.fullmatch(token)
    if not match:
        return False
    hsl = match.group(1).lower().startswith("hsl")
    body = match.group(2).strip()
    if "," in body:
        if "/" in body:
            return False
        args = [arg.strip() for arg in body.split(",")]
        if len(args) not in (3, 4):
            return False
        channels, alpha = args[:3], args[3:]
        if hsl:
            valid = bool(_HUE.fullmatch(channels[0])) and all(
                _COLOR_PERCENT.fullmatch(c) for c in channels[1:]
            )
        else:
            valid = all(_COLOR_NUMBER.fullmatch(c) for c in channels) or all(
                _COLOR_PERCENT.fullmatch(c) for c in channels
            )
    else:
        main, slash, rest = body.partition("/")
        channels, alpha = main.split(), rest.split()
        if len(channels) != 3 or (slash and len(alpha) != 1):
            return False
        valid = (
            bool(_HUE.fullmatch(channels[0])) if hsl else _is_channel(channels[0])
        ) and all(_is_channel(c) for c in channels[1:])
    return valid and all(_is_channel(a) for a in alpha)


def _is_border(value: str) -> bool:
    """`<width> || <style> || <colour>`: each at most once, in any order."""
    tokens = _tokens(value)
    if not 1 <= len(tokens) <= 3:
        return False
    seen: set[str] = set()
    for token in tokens:
        if token.lower() in _BORDER_STYLES:
            kind = "style"
        elif token.lower() in _BORDER_WIDTHS or _is_length(token, percent=False):
            kind = "width"
        elif _is_color(token):
            kind = "color"
        else:
            return False
        if kind in seen:
            return False
        seen.add(kind)
    return True


def _is_box(value: str) -> bool:
    """One to four non-negative lengths, as `padding` takes them."""
    tokens = _tokens(value)
    return 1 <= len(tokens) <= 4 and all(_is_length(token) for token in tokens)


def _is_radius(value: str) -> bool:
    """One to four radii, optionally `/` and one to four more."""
    corners = value.split("/")
    return len(corners) <= 2 and all(_is_box(corner) for corner in corners)


def _is_shadow_layer(layer: str) -> bool:
    tokens = _tokens(layer)
    at = [
        i
        for i, token in enumerate(tokens)
        if _is_length(token, signed=True, percent=False)
    ]
    # Offsets, blur and spread are one run: a colour between them is invalid.
    if not 2 <= len(at) <= 4 or at != list(range(at[0], at[0] + len(at))):
        return False
    if len(at) >= 3 and tokens[at[2]].startswith("-"):
        return False
    rest = [token for i, token in enumerate(tokens) if i not in at]
    insets = [token for token in rest if token.lower() == "inset"]
    colors = [token for token in rest if _is_color(token)]
    return len(insets) <= 1 and len(colors) <= 1 and len(insets + colors) == len(rest)


def _is_shadow(value: str) -> bool:
    if value.lower() == "none":
        return True
    layers = _split_top_level(value, ",")
    return layers is not None and all(_is_shadow_layer(layer) for layer in layers)


# Weights a type scale is written in besides CSS's own keywords. Typography
# is read by plugin authors, never compiled, so a name they all read alike is
# as concrete as a number.
_WEIGHT_NAMES = frozenset(
    """
    thin hairline extralight ultralight light regular book medium semibold
    demibold extrabold ultrabold heavy black
    """.split()
)
_TYPE_HEAD = re.compile(r"([^\s,/]+)\s*/\s*([^\s,]+)")


def _names_one_value(value: str) -> bool:
    """No range, approximation or alternative: one reading for every author."""
    return not (
        _RANGE.search(value)
        or "~" in value
        or re.search(r"\bor\b", value, re.IGNORECASE)
    )


def _is_type_style(value: str) -> bool:
    """`<size>/<weight>` first -- the contract's type.

    What follows (a colour, `uppercase`, letter-spacing) is guidance and is
    kept, held only to naming one value: the check exists so parallel plugin
    authors agree, not to make the entry a CSS declaration it never becomes.
    """
    head = _TYPE_HEAD.match(value.strip())
    if not head:
        return False
    size, weight = head.groups()
    return (
        _is_length(size, percent=False)
        and bool(
            _FONT_WEIGHT.fullmatch(weight.lower()) or weight.lower() in _WEIGHT_NAMES
        )
        and _names_one_value(value)
    )


_GRAMMARS: dict[str, Callable[[str], bool]] = {
    "border": _is_border,
    "border-radius": _is_radius,
    "box-shadow": _is_shadow,
    "padding": _is_box,
    "background-color": _is_color,
    "color": _is_color,
}

# How each property is written, for a problem stage C can act on. Placeholders
# rather than sample values: a model handed `8px` as an example has been known
# to copy it in place of measuring.
_EXAMPLES = {
    "border": '"<n>px solid #RRGGBB" or "none"',
    "border-radius": '"<n>px"',
    "box-shadow": '"<x>px <y>px <blur>px rgba(r, g, b, a)" or "none"',
    "padding": '"<n>px" or "<vertical>px <horizontal>px"',
    "background-color": '"#RRGGBB"',
    "color": '"#RRGGBB"',
    "type": '"<size>px/<weight>", optionally followed by ", #RRGGBB, uppercase"',
}

# The contract's card keys, and the property each styles on Superset's holder.
CARD_CHROME_PROPERTIES = (
    ("border", "border"),
    ("radius", "border-radius"),
    ("shadow", "box-shadow"),
    ("padding", "padding"),
    ("background", "background-color"),
)


def _clean(value: str) -> str:
    return " ".join(value.strip().rstrip(";").split())


def css_value(prop: str, value: Any) -> str | None:
    """`value` as it can be declared for `prop`, or None when it is not CSS.

    Nothing is repaired. A range has no one value to pick without looking at
    the design again, and a midpoint chosen here would be a guess carrying the
    contract's authority, so a value this cannot accept is left out and named.
    """
    if not isinstance(value, str):
        return None
    text = _clean(value)
    grammar = _GRAMMARS.get(prop)
    if not text or len(text) > _MAX_CSS_VALUE or grammar is None:
        return None
    return text if grammar(text) else None


def _absent(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _card_rules(
    card_chrome: dict[str, Any],
) -> tuple[list[str], list[tuple[str, Any]]]:
    """The design's card as declarations for the holder, and what was left out."""
    declarations: list[str] = []
    rejected: list[tuple[str, Any]] = []
    for key, prop in CARD_CHROME_PROPERTIES:
        value = card_chrome.get(key)
        if _absent(value):
            continue
        if text := css_value(prop, value):
            declarations.append(f"  {prop}: {text};")
        else:
            rejected.append((key, value))
    return declarations, rejected


def _left_out(field_name: str, value: Any) -> str:
    """A comment standing where a declaration the contract spoiled would be.

    The value goes to the log, never into the comment: it is exactly the text
    that failed validation, and inside a comment it could close it.
    """
    logger.warning(
        "%s is not a CSS value; left out of the dashboard CSS: %r", field_name, value
    )
    return f"/* {field_name} was not a CSS value and was left out. */"


def _problem(field_name: str, value: Any, what: str, example: str) -> str:
    if not isinstance(value, str):
        return (
            f"{field_name} must be a string holding {what}, e.g. {example}; "
            f"got {type(value).__name__} {value!r}."
        )
    shown = value if len(value) <= 80 else value[:77] + "..."
    if _RANGE.search(value):
        return (
            f"{field_name} is {shown!r}, a range. CSS takes one value and every "
            f"plugin author reads this one: give the value the design draws, "
            f"e.g. {example}."
        )
    return (
        f"{field_name} is {shown!r}, which is not {what}, so a browser drops "
        f"it. Write the concrete value the design draws, e.g. {example}."
    )


def _card_problems(card: Any) -> list[str]:
    if _absent(card):
        return []
    if not isinstance(card, dict):
        keys = ", ".join(key for key, _ in CARD_CHROME_PROPERTIES)
        return [
            "design_system.card_chrome must be an object of CSS values keyed "
            f"{keys}, not {type(card).__name__}: the dashboard stylesheet is "
            "written from it."
        ]
    problems: list[str] = []
    for key, prop in CARD_CHROME_PROPERTIES:
        value = card.get(key)
        if not _absent(value) and css_value(prop, value) is None:
            problems.append(
                _problem(
                    f"design_system.card_chrome.{key}",
                    value,
                    f"a CSS {prop} value",
                    _EXAMPLES[prop],
                )
            )
    # Held to the same test `_concrete_card` withholds on: a value rejected
    # there and accepted here reaches no plugin author, and C is never told.
    described = set(card) - {key for key, _ in CARD_CHROME_PROPERTIES}
    for key in sorted(described):
        value = card[key]
        if not isinstance(value, str) or _names_one_value(value):
            continue
        if _RANGE.search(value):
            problems.append(
                f"design_system.card_chrome.{key} is {value!r}, which gives a "
                "range. Name the one size the design draws."
            )
        else:
            problems.append(
                f"design_system.card_chrome.{key} is {value!r}, which offers "
                "more than one reading (an approximation with `~`, or an "
                "alternative with `or`). Every plugin author reads it in "
                "parallel and each would pick its own: name the one treatment "
                "the design draws, or leave the alternative out."
            )
    return problems


def _typography_problems(typography: Any) -> list[str]:
    if _absent(typography):
        return []
    if not isinstance(typography, dict):
        return [
            "design_system.typography must be an object mapping each text role "
            f"to {_EXAMPLES['type']}, not {type(typography).__name__}."
        ]
    return [
        _type_problem(f"design_system.typography.{role}", value)
        for role, value in typography.items()
        if not (isinstance(value, str) and _is_type_style(_clean(value)))
    ]


def _type_problem(field_name: str, value: Any) -> str:
    """Why a type style is sent back. Never compiled, so no browser drops it:
    the fault is that parallel plugin authors would each read it differently."""
    example = _EXAMPLES["type"]
    if not isinstance(value, str):
        return (
            f"{field_name} must be a string holding {example}; got "
            f"{type(value).__name__} {value!r}."
        )
    shown = value if len(value) <= 80 else value[:77] + "..."
    if _RANGE.search(value):
        return (
            f"{field_name} is {shown!r}, a range. Every plugin author reads this "
            f"one value, in parallel: give the size and weight the design draws, "
            f"e.g. {example}."
        )
    return (
        f"{field_name} is {shown!r}, which does not start with one size/weight "
        f"pair or offers more than one reading. Every plugin author reads this "
        f"value, in parallel, and each would pick its own: start it with the "
        f"size and weight the design draws, e.g. {example}."
    )


def contract_css_problems(design_system: Any) -> list[str]:
    """What in stage C's contract is not concrete CSS, worded for C to fix.

    Checked when C emits the contract, not only when the stylesheet compiles:
    by then the plan has fanned out to plugin authors who each read `16-20px`
    and pick their own end of it, and `compile_css` can only leave it out.
    Covers the card, which reaches a declaration, and the type scale, which
    workers apply by hand and so diverge on in the same way. Keys the prompt
    lets C describe in words (the card's `header`) are held only to naming
    one value where CSS would take one.
    """
    if not isinstance(design_system, dict):
        return []
    return _card_problems(design_system.get("card_chrome")) + _typography_problems(
        design_system.get("typography")
    )


def _concrete_card(card: Any, withheld: list[str]) -> dict[str, Any]:
    """The card values that are one concrete value; the rest named in `withheld`."""
    if not isinstance(card, dict):
        withheld.append("card_chrome")
        return {}
    properties = dict(CARD_CHROME_PROPERTIES)
    kept: dict[str, Any] = {}
    for key, value in card.items():
        if key in properties:
            keep = _absent(value) or css_value(properties[key], value) is not None
        else:
            keep = not isinstance(value, str) or _names_one_value(value)
        if keep:
            kept[key] = value
        else:
            withheld.append(f"card_chrome.{key}")
    return kept


def _concrete_type(typography: Any, withheld: list[str]) -> dict[str, Any]:
    """The type styles that are one concrete value; the rest named in `withheld`."""
    if not isinstance(typography, dict):
        withheld.append("typography")
        return {}
    kept: dict[str, Any] = {}
    for role, value in typography.items():
        if isinstance(value, str) and _is_type_style(_clean(value)):
            kept[role] = value
        else:
            withheld.append(f"typography.{role}")
    return kept


def concrete_contract(design_system: Any) -> dict[str, Any]:
    """The contract with every value `contract_css_problems` rejects left out.

    What plugin authors are handed. The check on stage C's own contract can
    run out of re-plans, and a key C omits is backfilled from stage A, which
    describes rather than measures -- either way a range reaches every worker
    and each picks its own end of it. A value left out is the smaller fault:
    it asks each worker nothing it could answer differently.
    """
    if not isinstance(design_system, dict):
        return {}
    contract = dict(design_system)
    withheld: list[str] = []
    for key, concrete in (
        ("card_chrome", _concrete_card),
        ("typography", _concrete_type),
    ):
        if _absent(contract.get(key)):
            continue
        if kept := concrete(contract[key], withheld):
            contract[key] = kept
        else:
            contract.pop(key)
    if withheld:
        logger.warning(
            "design_system values that are not one concrete value were withheld "
            "from plugin authors: %s",
            ", ".join(withheld),
        )
    return contract


def _selector(entry: RegionChrome, chart_id: int) -> str:
    return f".dashboard-chart-id-{chart_id}"


def _page_blocks(contract: dict[str, Any], page_background: Any) -> list[str]:
    """The page ground and the holder's card: the rules every chart shares."""
    blocks: list[str] = []
    if not _absent(page_background):
        if background := css_value("background-color", page_background):
            blocks.append(
                f".dashboard-content {{\n  background-color: {background};\n}}"
            )
        else:
            blocks.append(_left_out("global.page_background", page_background))

    card_chrome = contract.get("card_chrome")
    if isinstance(card_chrome, dict):
        rules, rejected = _card_rules(card_chrome)
        blocks.extend(
            _left_out(f"design_system.card_chrome.{key}", value)
            for key, value in rejected
        )
        if rules:
            joined = "\n".join(rules)
            blocks.append(
                "/* The holder is the design's card, so no plugin draws a second "
                "one. */\n.dashboard-component-chart-holder {\n" + joined + "\n}"
            )
    return blocks


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

    blocks.extend(_page_blocks(contract, page_background))

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
