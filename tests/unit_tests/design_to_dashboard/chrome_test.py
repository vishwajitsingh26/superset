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
"""Who draws the card, and what matching the design takes away.

The run these tests are written against put a page heading inside a card the
design never drew, printed its title twice, and clipped its caption on the
card's bottom edge -- while four KPI cards each showed their label twice, once
from Superset and once from the plugin.
"""

from __future__ import annotations

import re
from typing import Any

import pytest

from superset.design_to_dashboard import chrome


def _design(**chrome_by_region: dict[str, Any]) -> dict[str, Any]:
    return {
        "regions": [
            {"region_id": region_id, "chrome": value}
            for region_id, value in chrome_by_region.items()
        ]
    }


def _plan(*decisions: tuple[str, str, str | None]) -> dict[str, Any]:
    return {
        "decisions": [
            {"region_id": region_id, "decision": decision, "ref": ref}
            for region_id, decision, ref in decisions
        ]
    }


BARE_TITLE = {"surface": "bare", "title": "plain", "actions": []}
CARD_PLAIN = {"surface": "card", "title": "plain", "actions": []}
CARD_ICON = {"surface": "card", "title": "decorated", "actions": []}


def test_a_bare_region_keeps_no_card() -> None:
    """The failure this whole change exists for."""
    (entry,) = chrome.resolve(
        _design(r01=BARE_TITLE), _plan(("r01", "configure", "c1"))
    )
    assert entry.surface == "bare"
    assert entry.title == "plugin"
    assert entry.menu is False


def test_a_decorated_title_belongs_to_the_plugin() -> None:
    """Superset's slice header renders plain text, so an icon means it hides."""
    (entry,) = chrome.resolve(
        _design(r04=CARD_ICON), _plan(("r04", "new_plugin", "c4"))
    )
    assert entry.surface == "card"
    assert entry.title == "plugin"


def test_a_plain_title_on_a_card_stays_supersets() -> None:
    """Nothing is hidden that Superset can already draw correctly."""
    (entry,) = chrome.resolve(
        _design(r08=CARD_PLAIN), _plan(("r08", "configure", "c8"))
    )
    assert entry.title == "superset"
    assert entry.menu is True


def test_an_unread_chrome_keeps_supersets_own_behaviour() -> None:
    """A reading from before this field existed must not strip a card.

    A missing field is a reading the pipeline did not get, not a licence.
    """
    (entry,) = chrome.resolve(
        {"regions": [{"region_id": "r01"}]}, _plan(("r01", "configure", "c1"))
    )
    assert entry.surface == "card"
    assert entry.title == "superset"


def test_a_dropped_region_carries_no_chrome() -> None:
    assert not chrome.resolve(_design(r09=CARD_PLAIN), _plan(("r09", "drop", None)))


def test_a_text_node_has_no_header_to_hide() -> None:
    """`grid_text` becomes a MARKDOWN/HEADER node, which has no slice header.

    Emitting a rule for one would select nothing and read as a bug later.
    """
    (entry,) = chrome.resolve(
        _design(r01=BARE_TITLE), _plan(("r01", "grid_text", "c1"))
    )
    assert entry.ref is None
    assert entry.title == "none"
    assert entry.menu is False


@pytest.mark.parametrize(
    "menus,expected",
    [
        (chrome.MENU_ALL, True),
        (chrome.MENU_NONE, False),
        (chrome.MENU_DATA_ONLY, True),
    ],
)
def test_the_users_menu_answer_is_obeyed_on_a_card(menus: str, expected: bool) -> None:
    (entry,) = chrome.resolve(
        _design(r08=CARD_PLAIN), _plan(("r08", "configure", "c8")), menus
    )
    assert entry.menu is expected


def test_a_bare_region_never_gets_a_menu_by_default() -> None:
    """`data_only` means the cards the design drew, not every chart."""
    (entry,) = chrome.resolve(
        _design(r03=BARE_TITLE),
        _plan(("r03", "new_plugin", "c3")),
        chrome.MENU_DATA_ONLY,
    )
    assert entry.menu is False


def test_a_control_the_design_draws_replaces_supersets_menu() -> None:
    """The user's instruction: bind the options to their own control."""
    drawn = {
        "surface": "card",
        "title": "plain",
        "actions": [{"kind": "overflow_menu", "does": "export and refresh"}],
    }
    (entry,) = chrome.resolve(
        _design(r08=drawn), _plan(("r08", "new_plugin", "c8")), chrome.MENU_ALL
    )
    assert entry.menu is False
    assert entry.drawn_actions[0]["kind"] == "overflow_menu"


# --- the stylesheet ----------------------------------------------------------

CARD_CHROME = {
    "border": "1px solid #E2E8F0",
    "radius": "12px",
    "shadow": "0 1px 2px rgba(15,23,42,0.05)",
    "padding": "20px",
}


def test_the_holder_becomes_the_designs_card() -> None:
    """One rule for the whole page, instead of one card per plugin."""
    css = chrome.compile_css([], {}, {"card_chrome": CARD_CHROME})
    assert ".dashboard-component-chart-holder {" in css
    assert "border: 1px solid #E2E8F0;" in css
    assert "border-radius: 12px;" in css


def test_a_bare_chart_loses_the_holders_card() -> None:
    entries = chrome.resolve(_design(r01=BARE_TITLE), _plan(("r01", "configure", "c1")))
    css = chrome.compile_css(entries, {"c1": 104})
    assert ".dashboard-chart-id-104 {" in css
    assert "background-color: transparent;" in css
    assert ".dashboard-chart-id-104 [data-test='slice-header']" in css


def test_a_card_keeping_its_menu_hides_only_the_duplicate_title() -> None:
    """The four KPI cards: keep the card and the menu, drop the second title."""
    entries = chrome.resolve(
        _design(r04=CARD_ICON), _plan(("r04", "new_plugin", "c4")), chrome.MENU_ALL
    )
    css = chrome.compile_css(entries, {"c4": 106})
    assert ".dashboard-chart-id-106 .header-title" in css
    assert ".header-controls" not in css
    assert ".dashboard-chart-id-106 {" not in css


def test_a_chart_that_was_never_created_emits_no_rule() -> None:
    """A ref with no id is a chart the applier pruned, not a selector."""
    entries = chrome.resolve(_design(r01=BARE_TITLE), _plan(("r01", "configure", "c1")))
    assert ".dashboard-chart-id" not in chrome.compile_css(entries, {})


@pytest.mark.parametrize(
    "value",
    [
        "red; } body { display: none",
        "url('https://example.com/x.png')",
        "<script>",
        "a" * 200,
    ],
)
def test_a_contract_value_cannot_break_out_of_its_rule(value: str) -> None:
    """Stage C writes these and stage C is a model.

    One stray brace would take the rest of the dashboard's styling with it.
    """
    css = chrome.compile_css([], {}, {"card_chrome": {"border": value}})
    assert value not in css


def test_the_page_background_is_written_when_the_design_names_one() -> None:
    css = chrome.compile_css([], {}, {}, "#F8FAFC")
    assert ".dashboard-content {" in css
    assert "background-color: #F8FAFC;" in css


# --- what it costs -----------------------------------------------------------


def test_hiding_the_menu_says_what_it_takes_away() -> None:
    """The user asked to be told, not to have the trade made quietly."""
    entries = chrome.resolve(
        _design(r08=CARD_PLAIN), _plan(("r08", "configure", "c8")), chrome.MENU_NONE
    )
    (note, *_) = chrome.effects(entries)
    assert "drill to detail" in note
    assert "view query" in note


def test_a_control_that_cannot_be_rebound_is_named_as_such() -> None:
    """The honest half: drill-to-detail lives in Superset's header.

    A plugin cannot drive it, so a drawn kebab is visual only.
    """
    drawn = {
        "surface": "card",
        "title": "plain",
        "actions": [{"kind": "overflow_menu"}],
    }
    entries = chrome.resolve(_design(r08=drawn), _plan(("r08", "new_plugin", "c8")))
    assert any("visual only" in note for note in chrome.effects(entries))


def test_a_rebindable_control_is_not_flagged() -> None:
    drawn = {"surface": "card", "title": "plain", "actions": [{"kind": "refresh"}]}
    entries = chrome.resolve(_design(r08=drawn), _plan(("r08", "new_plugin", "c8")))
    assert not any("visual only" in note for note in chrome.effects(entries))


def test_nothing_hidden_means_nothing_to_disclose() -> None:
    entries = chrome.resolve(
        _design(r08=CARD_PLAIN), _plan(("r08", "configure", "c8")), chrome.MENU_ALL
    )
    assert chrome.effects(entries) == []


# --- the one question --------------------------------------------------------


def test_the_menu_question_is_asked_when_there_are_charts() -> None:
    entries = chrome.resolve(_design(r08=CARD_PLAIN), _plan(("r08", "configure", "c8")))
    question = chrome.question(entries)
    assert question is not None
    assert len(question["options"]) == 3


def test_a_page_of_text_is_not_asked_about_menus() -> None:
    entries = chrome.resolve(_design(r01=BARE_TITLE), _plan(("r01", "grid_text", "c1")))
    assert chrome.question(entries) is None


@pytest.mark.parametrize(
    "answer,expected",
    [
        ("Keep them everywhere", chrome.MENU_ALL),
        ("Hide them everywhere, match the design exactly", chrome.MENU_NONE),
        ("Only on charts the design draws as cards", chrome.MENU_DATA_ONLY),
        ("hide them everywhere please", chrome.MENU_NONE),
        ("keep the menus", chrome.MENU_ALL),
        (None, chrome.MENU_DATA_ONLY),
        ("something else entirely", chrome.MENU_DATA_ONLY),
    ],
)
def test_the_answer_is_read_for_intent(answer: Any, expected: str) -> None:
    """A free-typed reply must not silently fall to the default."""
    assert chrome.menus_from_answer(answer) == expected


# --- what stage A is held to ------------------------------------------------


def _region(**chrome_value: Any) -> dict[str, Any]:
    return {
        "n": 1,
        "role": "kpi",
        "bbox": {"x": 0.0, "y": 0.0, "w": 0.5, "h": 0.5},
        "chrome": chrome_value or None,
    }


def test_an_absent_chrome_is_not_a_fault() -> None:
    """A reading from before the field existed still describes a usable page."""
    from superset.design_to_dashboard.stages.a_decompose import _validate_chrome

    assert _validate_chrome({"n": 1, "role": "kpi"}) == []


def test_a_surface_outside_the_pair_is_a_fault() -> None:
    """`card` and `bare` are the whole question; a third answer is a misread."""
    from superset.design_to_dashboard.stages.a_decompose import _validate_chrome

    problems = _validate_chrome(_region(surface="panel", title="plain"))
    assert any("chrome.surface" in p for p in problems)


def test_a_drawn_action_without_a_kind_is_a_fault() -> None:
    from superset.design_to_dashboard.stages.a_decompose import _validate_chrome

    problems = _validate_chrome(
        _region(surface="card", title="plain", actions=[{"icon": "three dots"}])
    )
    assert any("actions[0]" in p for p in problems)


def test_a_well_read_chrome_passes() -> None:
    from superset.design_to_dashboard.stages.a_decompose import _validate_chrome

    assert not _validate_chrome(
        _region(surface="bare", title="none", actions=[], why="sits on the page")
    )


# --- the height the header no longer needs ----------------------------------


def test_a_headerless_row_gives_back_its_header_allowance() -> None:
    """The heading was in a box twice its height, caption still clipped."""
    from superset.design_to_dashboard.stages.e_layout import (
        CHART_HEADER_UNITS,
        strip_header_allowance,
    )

    position: dict[str, Any] = {
        "ROW-1": {"type": "ROW", "children": ["CHART-1", "CHART-2"]},
        "CHART-1": {"type": "CHART", "meta": {"chartId": "__REF__:c1", "height": 13}},
        "CHART-2": {"type": "CHART", "meta": {"chartId": "__REF__:c2", "height": 13}},
    }
    notes = strip_header_allowance(position, {"c1", "c2"})
    assert position["CHART-1"]["meta"]["height"] == 13 - CHART_HEADER_UNITS
    assert position["CHART-2"]["meta"]["height"] == 13 - CHART_HEADER_UNITS
    assert len(notes) == 1


def test_a_mixed_row_is_left_alone() -> None:
    """Superset lays a row out as one band.

    Shrinking one card whose neighbour keeps its header would reintroduce the
    very disagreement `normalise` exists to remove, after it had run.
    """
    from superset.design_to_dashboard.stages.e_layout import strip_header_allowance

    position: dict[str, Any] = {
        "ROW-1": {"type": "ROW", "children": ["CHART-1", "CHART-2"]},
        "CHART-1": {"type": "CHART", "meta": {"chartId": "__REF__:c1", "height": 42}},
        "CHART-2": {"type": "CHART", "meta": {"chartId": "__REF__:c2", "height": 42}},
    }
    assert strip_header_allowance(position, {"c1"}) == []
    assert position["CHART-1"]["meta"]["height"] == 42


def test_a_row_is_never_reduced_below_the_grids_floor() -> None:
    from superset.design_to_dashboard.stages.e_layout import (
        GRID_MIN_ROW_UNITS,
        strip_header_allowance,
    )

    position: dict[str, Any] = {
        "ROW-1": {"type": "ROW", "children": ["CHART-1"]},
        "CHART-1": {"type": "CHART", "meta": {"chartId": "__REF__:c1", "height": 6}},
    }
    strip_header_allowance(position, {"c1"})
    assert position["CHART-1"]["meta"]["height"] == GRID_MIN_ROW_UNITS


def test_a_row_holding_a_text_node_keeps_its_height() -> None:
    """A markdown heading carries no header allowance to give back."""
    from superset.design_to_dashboard.stages.e_layout import strip_header_allowance

    position: dict[str, Any] = {
        "ROW-1": {"type": "ROW", "children": ["CHART-1", "MARKDOWN-1"]},
        "CHART-1": {"type": "CHART", "meta": {"chartId": "__REF__:c1", "height": 13}},
        "MARKDOWN-1": {"type": "MARKDOWN", "meta": {"height": 13}},
    }
    assert strip_header_allowance(position, {"c1"}) == []


def test_a_section_a_wrapper_hosts_gets_no_rules_of_its_own() -> None:
    """A hosted child is not a chart on the grid, so it has no holder.

    Every rule written for one selects nothing. Its card is the wrapper's to
    draw, which is what the stage F prompt now tells the wrapper to do.
    """
    design = _design(r04=CARD_ICON, r05=CARD_ICON)
    plan = {
        "decisions": [
            {
                "region_id": "r04",
                "decision": "new_plugin",
                "ref": "c4",
                "children": ["c5"],
            },
            {"region_id": "r05", "decision": "new_plugin", "ref": "c5"},
        ]
    }
    (entry,) = chrome.resolve(design, plan)
    assert entry.region_id == "r04"
    assert ".dashboard-chart-id-101" not in chrome.compile_css(
        [entry], {"c4": 100, "c5": 101}
    )


def test_a_wrapper_with_no_children_is_unaffected() -> None:
    design = _design(r08=CARD_PLAIN)
    plan = {
        "decisions": [
            {"region_id": "r08", "decision": "configure", "ref": "c8", "children": []}
        ]
    }
    assert len(chrome.resolve(design, plan)) == 1


def test_a_dropped_wrappers_children_are_charts_on_the_grid_again() -> None:
    """The runner drops a wrapper whose plugin failed and keeps its `children`.

    Those sections are back on the grid, so they need the holder's card and
    their own title rules -- skipping them left them styled as nothing.
    """
    design = _design(r04=CARD_ICON, r05=CARD_ICON)
    plan = {
        "decisions": [
            {"region_id": "r04", "decision": "drop", "ref": "c4", "children": ["c5"]},
            {"region_id": "r05", "decision": "new_plugin", "ref": "c5"},
        ]
    }
    assert chrome._hosted_refs(plan) == set()
    (entry,) = chrome.resolve(design, plan, chrome.MENU_ALL)
    assert entry.region_id == "r05"
    css = chrome.compile_css([entry], {"c5": 101})
    assert ".dashboard-chart-id-101 .header-title" in css


# --- only concrete CSS reaches the stylesheet --------------------------------

# The contract of the run this is written against, as stage C emitted it.
DRIFTED_CARD = {
    "border": "1px solid #E0E3E8",
    "radius": "8px",
    "shadow": "subtle drop shadow",
    "padding": "16-20px",
    "header": "14px/600, #1a1a2e, separated from body by whitespace",
}


@pytest.mark.parametrize(
    "prop,value",
    [
        ("border", "1px solid #E2E8F0"),
        ("border", "none"),
        ("border", "0"),
        ("border", "thin dashed grey"),
        ("border", "solid 2px rgb(0, 0, 0)"),
        ("border-radius", "12px"),
        ("border-radius", "8px 8px 0 0"),
        ("border-radius", "50%"),
        ("border-radius", "10px / 5px"),
        ("box-shadow", "none"),
        ("box-shadow", "0 1px 2px rgba(15,23,42,0.05)"),
        ("box-shadow", "inset 0 0 0 1px #000"),
        ("box-shadow", "0 -1px 0 hsl(210, 20%, 90%)"),
        ("box-shadow", "0 1px 2px #0001, 0 4px 8px rgba(0 0 0 / 10%)"),
        ("padding", "20px"),
        ("padding", "0"),
        ("padding", "12px 16px"),
        ("padding", "1rem 2rem 1rem 2rem"),
        ("background-color", "#F8FAFC"),
        ("background-color", "white"),
        ("background-color", "transparent"),
        ("background-color", "rgba(255, 255, 255, 0.9)"),
        ("background-color", "rgb(0 0 0 / 50%)"),
        ("background-color", "hsl(210deg 20% 90% / 0.5)"),
        ("background-color", "rgb(10%, 20%, 30%)"),
        ("box-shadow", "0 1px 2px rgba(0, 0, 0, .1)"),
    ],
)
def test_a_concrete_css_value_passes_through(prop: str, value: str) -> None:
    assert chrome.css_value(prop, value) == value


def test_a_trailing_semicolon_and_stray_spacing_are_tidied() -> None:
    assert chrome.css_value("padding", "  12px   16px; ") == "12px 16px"


@pytest.mark.parametrize(
    "prop,value",
    [
        ("box-shadow", "subtle drop shadow"),
        ("box-shadow", "0 1px 2px rgba(0,0,0,0.05) soft"),
        ("box-shadow", "0 1px red 2px"),
        ("box-shadow", "0 1px -2px #000"),
        ("padding", "16-20px"),
        ("padding", "~16px"),
        ("padding", "16"),
        ("padding", "-4px"),
        ("padding", "1px 2px 3px 4px 5px"),
        ("border-radius", "about 8px"),
        ("border-radius", "none"),
        ("border", "1px solid light grey"),
        ("border", "1px solid solid"),
        ("background-color", "var(--card)"),
        ("background-color", "rgb(0, 0)"),
        # Four space-separated values: the alpha of that form follows a `/`.
        ("box-shadow", "0 1px 2px rgba(0 0 0 0.1)"),
        ("background-color", "rgb(1 2 3 4)"),
        ("background-color", "rgb(10deg 0 0)"),
        ("background-color", "rgb(0, 0, 0 / 0.5)"),
        ("background-color", "rgb(10%, 0, 0)"),
        ("background-color", "hsl(210, 20, 90)"),
        ("background-color", "rgba(0 0 0 / 0.1 0.2)"),
        ("background-color", "#GGGGGG"),
        ("background-color", "white fill"),
        ("padding", "22-24px/700"),
        ("padding", 16),
        ("unknown-property", "16px"),
    ],
)
def test_prose_ranges_and_non_values_are_rejected(prop: str, value: Any) -> None:
    assert chrome.css_value(prop, value) is None


def _declarations(css: str) -> list[tuple[str, str]]:
    return re.findall(r"^\s+([a-z-]+):\s*(.*?);$", css, re.MULTILINE)


@pytest.mark.parametrize(
    "card",
    [
        DRIFTED_CARD,
        CARD_CHROME,
        {"border": "1px solid", "radius": 8, "shadow": None, "padding": ""},
        {"background": "light grey", "shadow": "0 1px 2px", "padding": "16px 20px"},
    ],
)
def test_compile_css_never_writes_an_invalid_declaration(
    card: dict[str, Any],
) -> None:
    entries = chrome.resolve(
        _design(r01=BARE_TITLE, r04=CARD_ICON),
        _plan(("r01", "configure", "c1"), ("r04", "new_plugin", "c4")),
        chrome.MENU_NONE,
    )
    css = chrome.compile_css(
        entries, {"c1": 1, "c4": 4}, {"card_chrome": card}, "#F5F6FA"
    )
    declarations = _declarations(css)
    assert declarations
    for prop, value in declarations:
        if prop == "display":
            assert value == "none"
        else:
            assert chrome.css_value(prop, value) == value, (prop, value)


def test_a_spoiled_value_is_left_out_and_named() -> None:
    """The browser would drop it anyway; the comment says which and why."""
    css = chrome.compile_css([], {}, {"card_chrome": DRIFTED_CARD})
    assert "subtle drop shadow" not in css
    assert "16-20px" not in css
    assert "box-shadow:" not in css
    assert "padding:" not in css
    assert "border: 1px solid #E0E3E8;" in css
    assert "border-radius: 8px;" in css
    assert "design_system.card_chrome.shadow was not a CSS value" in css
    assert "design_system.card_chrome.padding was not a CSS value" in css


def test_an_invalid_page_background_is_left_out() -> None:
    css = chrome.compile_css([], {}, {}, "off-white")
    assert ".dashboard-content" not in css
    assert "off-white" not in css


# --- what stage C is held to -------------------------------------------------


def test_the_drifted_contract_is_sent_back_with_what_to_fix() -> None:
    problems = chrome.contract_css_problems(
        {
            "card_chrome": DRIFTED_CARD,
            "typography": {"value": "22-24px/700", "label": "13px/500"},
        }
    )
    assert len(problems) == 3
    shadow, padding, value = problems
    assert "card_chrome.shadow" in shadow
    assert "subtle drop shadow" in shadow
    assert "box-shadow" in shadow
    assert "card_chrome.padding" in padding
    assert "a range" in padding
    assert "typography.value" in value
    assert "a range" in value


def test_a_concrete_contract_has_no_problems() -> None:
    assert (
        chrome.contract_css_problems(
            {
                "card_chrome": {
                    **CARD_CHROME,
                    "background": "#FFFFFF",
                    "header": "13px/500, #6B7280, 8px below",
                },
                "typography": {
                    "value": "24px/700",
                    "label": "13px/500, #6B7280",
                    "caption": "11px/normal",
                },
                "theme": "light",
            }
        )
        == []
    )


@pytest.mark.parametrize(
    "value",
    [
        "22-24px/700",
        "12-13px/500, grey",
        "24px bold blue",
        "24px",
        "~24px/700",
        "24px/700, blue or dark",
    ],
)
def test_a_type_style_that_is_not_size_and_weight_is_a_problem(value: str) -> None:
    (problem,) = chrome.contract_css_problems({"typography": {"value": value}})
    assert "design_system.typography.value" in problem


@pytest.mark.parametrize(
    "value",
    [
        "11px/500, #6B7280, uppercase",
        "14px/600 #1a1a2e",
        "14px/semibold",
        "12px/Medium, letter-spacing 0.5px",
    ],
)
def test_a_type_style_may_carry_guidance_after_its_size_and_weight(
    value: str,
) -> None:
    """Typography is read by plugin authors, never compiled into CSS."""
    assert chrome.contract_css_problems({"typography": {"label": value}}) == []


def test_a_type_style_problem_names_the_real_reason() -> None:
    (problem,) = chrome.contract_css_problems({"typography": {"value": "24px bold"}})
    assert "browser" not in problem
    assert "parallel" in problem


def test_plugin_authors_are_handed_only_concrete_values() -> None:
    contract = chrome.concrete_contract(
        {
            "card_chrome": {
                "border": "1px solid #E0E3E8",
                "radius": "8px",
                "shadow": "subtle drop shadow",
                "padding": "16-20px",
                "header": "13-14px/500",
            },
            "typography": {"value": "22-24px/700", "label": "13px/500, #6B7280"},
            "palette": ["#111"],
        }
    )
    assert contract == {
        "card_chrome": {"border": "1px solid #E0E3E8", "radius": "8px"},
        "typography": {"label": "13px/500, #6B7280"},
        "palette": ["#111"],
    }


def test_a_contract_in_prose_is_withheld_entirely() -> None:
    contract = chrome.concrete_contract(
        {
            "card_chrome": "White fill, 1px light-grey border, subtle drop shadow",
            "typography": {"big_number": "22-24px bold blue or dark"},
            "theme": "light",
        }
    )
    assert contract == {"theme": "light"}


def test_a_range_in_the_described_card_header_is_a_problem() -> None:
    (problem,) = chrome.contract_css_problems(
        {"card_chrome": {"header": "13-14px/500, 8px below"}}
    )
    assert "card_chrome.header" in problem


def test_a_card_described_in_prose_is_a_problem() -> None:
    """Stage A writes its card as a sentence; the contract cannot be one."""
    (problem,) = chrome.contract_css_problems(
        {"card_chrome": "White fill, 1px light-grey border, subtle drop shadow"}
    )
    assert "must be an object" in problem


def test_a_number_where_css_wants_a_length_says_so() -> None:
    (problem,) = chrome.contract_css_problems({"card_chrome": {"radius": 8}})
    assert "must be a string" in problem


def test_an_absent_contract_is_left_to_the_existing_check() -> None:
    """`no design_system contract emitted` is stage C's own problem to raise."""
    assert chrome.contract_css_problems(None) == []
    assert chrome.contract_css_problems({}) == []


def test_an_alternative_in_the_described_card_header_is_a_problem() -> None:
    (problem,) = chrome.contract_css_problems(
        {
            "card_chrome": {
                "header": "14px/600, #1a1a2e, separated by whitespace or a divider"
            }
        }
    )
    assert "card_chrome.header" in problem
    assert "more than one reading" in problem


@pytest.mark.parametrize(
    "contract",
    [
        {
            "card_chrome": {
                "shadow": "none",
                "padding": "16px",
                "header": "14px/600, #1a1a2e, whitespace or a thin divider",
            },
            "typography": {"value": "24px/700"},
        },
        {"card_chrome": {"header": "~14px/600", "radius": "8px"}},
        {"card_chrome": {"padding": "16-20px", "header": "13-14px/500"}},
        {"typography": {"value": "22-24px/700", "label": "13px/500 or 14px/500"}},
        {"card_chrome": "White fill, subtle drop shadow", "typography": "bold"},
        {"card_chrome": {"border": "1px solid #E0E3E8", "header": "13px/500"}},
    ],
)
def test_every_value_withheld_from_plugin_authors_was_reported_to_c(
    contract: dict[str, Any],
) -> None:
    """One predicate for both: C is told about everything workers lose."""
    problems = " ".join(chrome.contract_css_problems(contract))
    concrete = chrome.concrete_contract(contract)
    for key in ("card_chrome", "typography"):
        given = contract.get(key)
        kept = concrete.get(key)
        if not isinstance(given, dict):
            if given is not None and kept is None:
                assert f"design_system.{key}" in problems
            continue
        for entry in set(given) - set(kept or {}):
            assert f"design_system.{key}.{entry}" in problems
