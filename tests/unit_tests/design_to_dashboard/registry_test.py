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
"""The per-run registry, its stage views and its capability cards."""

from __future__ import annotations

import pathlib
from typing import Any

import pytest

from superset.design_to_dashboard import capabilities, registry, registry_source
from superset.design_to_dashboard.mcp.gateway import (
    chart_capabilities,
    MCPError,
)
from superset.design_to_dashboard.registry import Registry, RegistryError

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]

PANEL = """
const config = {
  controlPanelSections: [
    {
      controlSetRows: [
        ['metric'],
        [{ name: 'donut', config: { type: 'CheckboxControl', label: t('Donut') } }],
        [
          {
            name: 'label_type',
            config: {
              type: 'SelectControl',
              label: t('Label Type'),
              choices: [
                ['key', t('Category Name')],
                ['value', t('Value')],
              ],
              default: 'key',
            },
          },
        ],
        [{ name: 'row_limit', config: { label: t('Row limit') } }],
        ...legendSection,
      ],
    },
  ],
};
"""


def _entry(viz_type: str, **extra: Any) -> dict[str, Any]:
    return {
        "viz_type": viz_type,
        "name": viz_type.title(),
        "category": "Part of a Whole",
        "custom": False,
        "is_filter": False,
        **extra,
    }


def _registry(tmp_path: pathlib.Path) -> Registry:
    panel = tmp_path / "Pie" / "controlPanel.tsx"
    panel.parent.mkdir(parents=True)
    panel.write_text(PANEL, encoding="utf-8")
    return Registry(
        entries=[
            _entry("pie", control_panel="Pie/controlPanel.tsx"),
            _entry("table", category="Table"),
            _entry("custom_kpi", custom=True, category=None),
            _entry("filter_select", is_filter=True),
        ],
        repo_root=tmp_path,
    )


# --- building ----------------------------------------------------------------


def test_a_custom_plugin_whose_files_are_gone_is_dropped(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "kept.ts").write_text("", encoding="utf-8")
    scanned = [
        _entry("custom_kept", custom=True, source="kept.ts"),
        _entry("custom_deleted", custom=True, source="deleted.ts"),
        _entry("pie", source="missing-but-stock.ts"),
    ]
    monkeypatch.setattr(
        registry_source, "scan", lambda: {"viz_types": scanned, "warnings": {}}
    )
    built = registry.build(tmp_path)
    assert built.viz_types() == {"custom_kept", "pie"}
    assert built.dropped == ["custom_deleted"]


def test_a_scan_that_finds_nothing_fails_loudly(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(registry_source, "scan", lambda: {"viz_types": []})
    with pytest.raises(RegistryError):
        registry.build(tmp_path)


def test_the_real_source_builds() -> None:
    built = registry.build(REPO_ROOT)
    assert {"pie", "table", "big_number"} <= built.viz_types()
    assert built.control_panel("pie")[1]


def test_a_snapshot_restores_the_same_registry(tmp_path: pathlib.Path) -> None:
    original = _registry(tmp_path)
    restored = Registry.from_snapshot(original.snapshot(), tmp_path)
    assert restored.entries == original.entries
    with pytest.raises(RegistryError):
        Registry.from_snapshot({"entries": []}, tmp_path)


# --- stage views ------------------------------------------------------------


def test_stage_a_gets_names_grouped_without_descriptions(
    tmp_path: pathlib.Path,
) -> None:
    text = _registry(tmp_path).stage_a_text()
    assert "Part of a Whole: pie" in text
    assert "Custom: custom_kpi" in text
    assert "filter_select" not in text


def test_stage_d_gets_one_panel(tmp_path: pathlib.Path) -> None:
    path, source = _registry(tmp_path).control_panel("pie")
    assert path == "Pie/controlPanel.tsx"
    assert "label_type" in source


def test_chart_types_leave_out_filters_and_types_without_panels(
    tmp_path: pathlib.Path,
) -> None:
    reg = _registry(tmp_path)
    assert reg.chart_types() == {"pie"}
    assert reg.filter_types() == ["filter_select"]


# --- capability cards --------------------------------------------------------


def test_settings_come_from_the_panel_without_query_controls() -> None:
    found = capabilities.settings(PANEL)
    assert "Donut" in found
    assert "Label Type (Category Name, Value)" in found
    assert not any(line.startswith("Row limit") for line in found)
    assert found[0].startswith("Legend:")


def test_a_card_carries_verified_cannot_lines(tmp_path: pathlib.Path) -> None:
    card = _registry(tmp_path).capability_card("pie")
    assert "Settings:" in card
    assert "Cannot show:" in card
    assert "Total: <value>" in card


def test_a_custom_plugin_without_a_panel_gets_a_bare_card(
    tmp_path: pathlib.Path,
) -> None:
    """No exception, and nothing invented: just the header, since there is no
    control panel to draw Settings from and no hand-verified Cannot-show line
    for a plugin nobody has written one for."""
    card = _registry(tmp_path).capability_card("custom_kpi")
    assert card.startswith("### `custom_kpi`")
    assert "Settings:" not in card
    assert "Cannot show:" not in card


def test_a_custom_plugin_with_a_panel_gets_its_real_settings(
    tmp_path: pathlib.Path,
) -> None:
    """The point of the fix: a custom plugin's card is drawn from its own
    control panel exactly like a stock type's, so stage C sees what the
    plugin's controls are actually labelled rather than a description the
    same model that reuses it gets to write."""
    reg = _registry(tmp_path)
    reg.entries.append(
        _entry("custom_metric_tile", custom=True, control_panel="Pie/controlPanel.tsx")
    )
    card = reg.capability_card("custom_metric_tile")
    assert "Settings:" in card
    assert "Donut" in card
    assert "Cannot show:" not in card


def test_the_shortlist_adds_every_custom_plugin_to_the_carded_stock_ones(
    tmp_path: pathlib.Path,
) -> None:
    reg = _registry(tmp_path)
    design = {
        "regions": [
            {"stock_candidate": "table"},
            {"stock_candidate": "custom_kpi"},
            {"stock_candidate": "not_registered"},
        ]
    }
    assert reg.card_shortlist(design) == ["custom_kpi", "pie", "table"]


def test_every_hand_written_line_names_a_real_chart_type() -> None:
    built = registry.build(REPO_ROOT)
    assert capabilities.carded() <= built.viz_types()


# --- the tool ----------------------------------------------------------------


def test_the_capability_tool_answers_from_the_runs_registry(
    tmp_path: pathlib.Path,
) -> None:
    reg = _registry(tmp_path)
    result = chart_capabilities(reg, {"viz_type": "pie"})
    assert "Cannot show:" in result["card"]
    nested = chart_capabilities(reg, {"request": {"viz_type": "pie"}})
    assert nested == result
    # A custom plugin answers too, now that its card is drawn the same way a
    # stock type's is: stage C can look one up before deciding to reuse it.
    custom = chart_capabilities(reg, {"viz_type": "custom_kpi"})
    assert custom["card"].startswith("### `custom_kpi`")
    with pytest.raises(MCPError):
        chart_capabilities(reg, {"viz_type": "not_registered"})
    with pytest.raises(MCPError):
        chart_capabilities(None, {"viz_type": "pie"})
