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
