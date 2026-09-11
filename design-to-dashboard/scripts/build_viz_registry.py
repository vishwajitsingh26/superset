#!/usr/bin/env python3
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
"""Generate the viz-type manifest that stages C and D read.

Superset's chart registry lives in the frontend, and MCP's
``get_chart_type_schema`` covers only seven abstract families -- so the
pipeline needs its own manifest. This derives it from source:

  * ``VizType.ts``            enum member -> viz_type key
  * ``MainPreset.ts``         plugin class -> registered key
  * ``setupPluginsExtra.ts``  custom plugin class -> registered key (forks)
  * each plugin's ``ChartMetadata``  name, category, tags, description

Writes ``design-to-dashboard/fixtures/viz_registry.json``.

    python design-to-dashboard/scripts/build_viz_registry.py
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
from typing import Any

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
FRONTEND = REPO_ROOT / "superset-frontend"
VIZ_TYPE_TS = FRONTEND / "packages/superset-ui-core/src/chart/types/VizType.ts"
PRESETS = [
    FRONTEND / "src/visualizations/presets/MainPreset.ts",
    FRONTEND / "src/visualizations/presets/MainPreset.js",
    FRONTEND / "src/setup/setupPluginsExtra.ts",
]
PLUGIN_ROOTS = [
    FRONTEND / "plugins",
    FRONTEND / "src/visualizations",
    FRONTEND / "src/filters",
]
CONSTANTS_TS = FRONTEND / "src/constants.ts"

# A few plugins are re-exported under an alias, so the class name in
# MainPreset never appears in a `class X extends` declaration. The parser
# reports anything it cannot resolve, so this list stays honest.
# Viz types whose panel the source walk cannot reach. Without an entry here a
# viz type is registered with `control_panel: null`, stage D cannot load a
# schema for it, and any chart of that type is dropped from the dashboard --
# so the registry must either name the panel or not offer the viz type at all.
CONTROL_PANEL_OVERRIDES = {
    "pivot_table_v2": (
        "superset-frontend/plugins/plugin-chart-pivot-table/src/plugin/controlPanel.tsx"
    ),
    "echarts_timeseries": (
        "superset-frontend/plugins/plugin-chart-echarts/src/Timeseries/Regular/Line/"
        "controlPanel.tsx"
    ),
    # Native-filter plugins live under `src/filters`, not `plugins/`, and these
    # three register without a discoverable source path. `filter_range` and
    # `filter_time` resolve on their own; these do not.
    "filter_select": "superset-frontend/src/filters/components/Select/controlPanel.ts",
    "filter_timecolumn": (
        "superset-frontend/src/filters/components/TimeColumn/controlPanel.ts"
    ),
    "filter_timegrain": (
        "superset-frontend/src/filters/components/TimeGrain/controlPanel.ts"
    ),
    # Its panel sits a directory deeper than the walk looks, beside a re-export
    # of the same name.
    "time_table": (
        "superset-frontend/src/visualizations/TimeTable/config/controlPanel/"
        "controlPanel.ts"
    ),
}

METADATA_OVERRIDES = {
    "big_number": {
        "name": "Big Number with Trendline",
        "category": "KPI",
        "description": (
            "Showcases a single number accompanied by a simple line chart, "
            "to call attention to an important metric along with its change "
            "over time or other dimension."
        ),
        "tags": ["Advanced-Analytics", "Line", "Report", "Trend", "Featured"],
        "control_panel": (
            "superset-frontend/plugins/plugin-chart-echarts/src/BigNumber/"
            "BigNumberWithTrendline/controlPanel.tsx"
        ),
    },
    "mixed_timeseries": {
        "name": "Mixed Chart",
        "category": "Evolution",
        "description": (
            "Visualize two different series using the same x-axis. Note that "
            "both series can be visualized with a different chart type "
            "(e.g. 1 using bars and 1 using a line)."
        ),
        "tags": ["ECharts", "Line", "Bar", "Advanced-Analytics"],
        "control_panel": (
            "superset-frontend/plugins/plugin-chart-echarts/src/MixedTimeseries/"
            "controlPanel.tsx"
        ),
    },
    "pop_kpi": {
        "name": "Big Number with Time Comparison",
        "category": "KPI",
        "description": (
            "Showcases a single metric alongside its value in a comparison "
            "period, with the delta between them."
        ),
        "tags": ["Report", "Comparison", "Experimental"],
        "control_panel": (
            "superset-frontend/plugins/plugin-chart-echarts/src/BigNumber/"
            "BigNumberPeriodOverPeriod/controlPanel.ts"
        ),
    },
}

# `new FooChartPlugin().configure({ key: VizType.Foo })` or `key: 'custom_foo'`
REGISTER_RE = re.compile(
    r"new\s+(\w+)\s*\([^)]*\)\s*(?:\.\w+\([^)]*\)\s*)*?"
    r"\.configure\(\s*\{\s*key:\s*(VizType\.\w+|FilterPlugins\.\w+|'[^']+'|\"[^\"]+\")",
    re.S,
)
ENUM_RE = re.compile(r"^\s*(\w+)\s*=\s*'([^']+)'", re.M)
FILTER_ENUM_RE = re.compile(r"export enum FilterPlugins \{(.*?)\}", re.S)
CLASS_RE = re.compile(r"class\s+(\w+)\s+extends\s+\w+", re.M)
# Two metadata idioms in the wild: `new ChartMetadata({...})` and a plain
# `const metadata = {...}` passed to super().
META_STARTS = [
    re.compile(r"new\s+ChartMetadata\(\s*\{"),
    re.compile(r"const\s+metadata\s*(?::\s*[\w<>,\s]+)?\s*=\s*\{"),
    re.compile(r"\bmetadata:\s*\{"),
]


def _balanced(text: str, open_index: int) -> str:
    """Return the {...} block starting at ``open_index`` (index of the brace)."""
    depth = 0
    for pos in range(open_index, len(text)):
        char = text[pos]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[open_index + 1 : pos]
    return ""


def _field(block: str, key: str) -> str | None:
    match = re.search(rf"\b{key}:\s*t\(\s*(['\"])(.*?)\1\s*[,)]", block, re.S)
    if not match:
        match = re.search(rf"\b{key}:\s*(['\"])(.*?)\1", block, re.S)
    if not match:
        return None
    # Collapse TypeScript string concatenation across lines.
    value = re.sub(r"['\"]\s*\+\s*['\"]", "", match.group(2))
    return re.sub(r"\s+", " ", value).strip()


def _tags(block: str) -> list[str]:
    match = re.search(r"\btags:\s*\[(.*?)\]", block, re.S)
    if not match:
        return []
    return re.findall(r"t\(\s*['\"](.*?)['\"]", match.group(1))


def _behaviors(block: str) -> list[str]:
    match = re.search(r"\bbehaviors:\s*\[(.*?)\]", block, re.S)
    if not match:
        return []
    return re.findall(r"Behavior\.(\w+)", match.group(1))


def collect_enum() -> dict[str, str]:
    """Prefixed enum member -> viz_type key, for VizType and FilterPlugins."""
    out: dict[str, str] = {}
    if VIZ_TYPE_TS.exists():
        for name, value in ENUM_RE.findall(VIZ_TYPE_TS.read_text(encoding="utf-8")):
            out[f"VizType.{name}"] = value
    if CONSTANTS_TS.exists():
        match = FILTER_ENUM_RE.search(CONSTANTS_TS.read_text(encoding="utf-8"))
        if match:
            for name, value in ENUM_RE.findall(match.group(1)):
                out[f"FilterPlugins.{name}"] = value
    return out


def collect_registrations(enum: dict[str, str]) -> dict[str, str]:
    """class name -> registered viz_type key."""
    out: dict[str, str] = {}
    for preset in PRESETS:
        if not preset.exists():
            continue
        for cls, raw in REGISTER_RE.findall(preset.read_text(encoding="utf-8")):
            if raw.startswith(("'", '"')):
                out[cls] = raw.strip("'\"")
            elif raw in enum:
                out[cls] = enum[raw]
    return out


def collect_metadata() -> dict[str, dict[str, Any]]:  # noqa: C901
    """class name -> metadata fields, found in the file that defines the class."""
    out: dict[str, dict[str, Any]] = {}
    for root in PLUGIN_ROOTS:
        if not root.exists():
            continue
        for path in root.rglob("*.ts*"):
            parts = set(path.parts)
            if parts & {"node_modules", "lib", "esm", "test", "__tests__"}:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue

            blocks = []
            for pattern in META_STARTS:
                for match in pattern.finditer(text):
                    brace = text.index("{", match.end() - 1)
                    block = _balanced(text, brace)
                    if block and ("name:" in block or "category:" in block):
                        blocks.append((match.start(), block))
            if not blocks:
                continue
            blocks.sort()

            classes = CLASS_RE.findall(text)
            if not classes:
                continue

            # One class per file is the overwhelming norm; when a file holds
            # several, pair them positionally with the metadata blocks.
            for index, cls in enumerate(classes):
                block = blocks[index][1] if index < len(blocks) else blocks[0][1]
                if cls in out:
                    continue
                out[cls] = {
                    "name": _field(block, "name"),
                    "category": _field(block, "category"),
                    "description": _field(block, "description"),
                    "tags": _tags(block),
                    "behaviors": _behaviors(block),
                    "source": str(path.relative_to(REPO_ROOT)),
                }
    return out


def _find_thumbnail(source: str | None) -> str | None:
    """Locate the plugin's thumbnail.

    Every plugin ships one for the viz-type gallery, so it is the best available
    picture of what the chart actually looks like -- far more useful for
    matching a design than a text description.
    """
    if not source:
        return None
    start = (REPO_ROOT / source).parent
    candidates = [start, *list(start.parents)[:3]]
    for directory in candidates:
        if not directory.is_dir():
            continue
        for name in ("images/thumbnail.png", "images/thumbnail.jpg"):
            candidate = directory / name
            if candidate.exists():
                try:
                    return str(candidate.relative_to(REPO_ROOT))
                except ValueError:
                    return None
    return None


def _verified(path: str | None) -> str | None:
    """Drop a control-panel path that is not actually on disk.

    An override that silently rots is worse than a reported gap: stage D would
    fail at run time instead of the generator failing here.
    """
    if path and (REPO_ROOT / path).exists():
        return path
    if path:
        print(f"  WARNING: control panel path does not exist: {path}", file=sys.stderr)
    return None


def _find_control_panel(source: str | None) -> str | None:
    """Locate the controlPanel file for the plugin that owns ``source``.

    Stage D needs the real control schema for exactly one viz type. Rather than
    lossily re-deriving it, the manifest records where it lives and the stage
    reads the source itself.
    """
    if not source:
        return None
    start = (REPO_ROOT / source).parent
    # Walk up a few levels: controlPanel sits beside index.ts, or one level up
    # in `plugin/`, depending on the plugin's layout.
    # Path.parents is not sliceable before Python 3.10.
    candidates = [start, start / "plugin", *list(start.parents)[:3]]
    for directory in candidates:
        if not directory.is_dir():
            continue
        for suffix in (".tsx", ".ts"):
            candidate = directory / f"controlPanel{suffix}"
            if candidate.exists():
                try:
                    return str(candidate.relative_to(REPO_ROOT))
                except ValueError:
                    return None
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        default=str(REPO_ROOT / "design-to-dashboard/fixtures/viz_registry.json"),
    )
    args = parser.parse_args()

    enum = collect_enum()
    registrations = collect_registrations(enum)
    metadata = collect_metadata()

    entries = []
    for cls, key in sorted(registrations.items(), key=lambda kv: kv[1]):
        meta = dict(metadata.get(cls, {}))
        if not meta and key in METADATA_OVERRIDES:
            meta = {**METADATA_OVERRIDES[key], "source": "METADATA_OVERRIDES"}
        entries.append(
            {
                "viz_type": key,
                "plugin_class": cls,
                "name": meta.get("name") or cls,
                "category": meta.get("category"),
                "description": meta.get("description"),
                "tags": meta.get("tags", []),
                "behaviors": meta.get("behaviors", []),
                "custom": key.startswith("custom_") or key == "container_chart",
                "is_filter": key.startswith("filter_"),
                "source": meta.get("source"),
                "thumbnail": _find_thumbnail(meta.get("source")),
                "control_panel": _verified(
                    meta.get("control_panel")
                    or CONTROL_PANEL_OVERRIDES.get(key)
                    or _find_control_panel(meta.get("source"))
                ),
                "metadata_found": bool(meta),
            }
        )

    unmatched = sorted(set(metadata) - set(registrations))
    warnings: dict[str, list[str]] = {
        "registered_without_metadata": sorted(
            e["viz_type"] for e in entries if not e["metadata_found"]
        ),
        "registered_without_thumbnail": sorted(
            e["viz_type"] for e in entries if not e["thumbnail"]
        ),
        "registered_without_control_panel": sorted(
            e["viz_type"] for e in entries if not e["control_panel"]
        ),
        "metadata_without_registration": unmatched,
    }
    payload = {
        "generated_from": "source",
        "count": len(entries),
        "viz_types": entries,
        "warnings": warnings,
    }

    out_path = pathlib.Path(args.out)
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"wrote {out_path} ({len(entries)} viz types)", file=sys.stderr)
    if missing := warnings["registered_without_metadata"]:
        print(f"  no metadata for {len(missing)}: {missing[:8]}", file=sys.stderr)
    if no_panel := warnings["registered_without_control_panel"]:
        print(
            f"  no control panel for {len(no_panel)}: {no_panel[:8]}", file=sys.stderr
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
