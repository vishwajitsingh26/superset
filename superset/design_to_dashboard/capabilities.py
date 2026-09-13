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
"""What a stock chart can and cannot be set up to show.

A thumbnail shows one way a chart was set up once. Its settings decide every
other way it can look, and stage C, deciding whether a stock chart matches a
design, was judging from the picture alone. It is an easy mistake to make even
reading the code: this pipeline's own review claimed the pie chart could not
put a total in a donut's centre, and it can.

A card has two halves.

**Settings** are generated from the chart's settings panel source on every
build: each control's label, and the choices a select offers. They cannot go
stale, and they cannot claim a setting the code does not have.

**Cannot** lines are written by hand and verified against the chart's code,
because code cannot reliably show that something is absent -- and the absences
are exactly what decide a match: a legend with no value column, centre text
whose wording is fixed. Only the chart types designs use most carry them.
"""

from __future__ import annotations

import re
from typing import Any

# A control's label, and the human half of each select choice.
_NAME = re.compile(r"""\bname:\s*['"]([A-Za-z0-9_]+)['"]""")
_LABEL = re.compile(r"""\blabel:\s*t\(\s*(['"])(.+?)\1\s*[,)]""", re.S)
_CHOICES = re.compile(r"\bchoices:\s*\[(.*?)\]\s*,?\s*\n\s*(?:[a-zA-Z_]+:|\})", re.S)
_CHOICE_LABEL = re.compile(r"""\[\s*[^,\]]+,\s*t\(\s*(['"])(.+?)\1\s*\)\s*\]""")

# Shared control sections spread into a panel by name. Their controls live in
# another file, so the panel's own source only shows the spread.
SHARED_SECTIONS = {
    "legendSection": (
        "Legend: shown or hidden, on any side, plain or scrolling, sorted, "
        "with a margin"
    ),
}

# Labels that describe the query rather than what the chart draws. A card is
# about appearance; stage D reads the full panel when it configures a chart.
QUERY_LABELS = {
    "Metric",
    "Metrics",
    "Dimensions",
    "Filters",
    "Row limit",
    "Series limit",
    "Sort by",
    "Time grain",
    "X-axis",
    "Query mode",
    "Columns",
    "Percentage metrics",
}

MAX_SETTINGS = 40

# Verified against each chart's settings panel and drawing code. A line here is
# a claim that no setting produces it; add one only with the code open.
NOTES: dict[str, list[str]] = {
    "pie": [
        "Show Total draws 'Total: <value>' in bold 16px text, in the centre of "
        "a donut and at the top of a full pie",
    ],
    "echarts_timeseries_bar": [
        "a stacked bar can carry a total label on top (only_total)",
        "Contribution mode Row with stacking gives 100% bars",
    ],
    "echarts_timeseries_line": [
        "smooth and step lines are the separate types echarts_timeseries_smooth "
        "and echarts_timeseries_step",
    ],
    "big_number": [
        "a caption line below the value and the change (subtitle), the metric "
        "name as a label above it, and font sizes from Tiny to Huge for each",
        "the trendline is its own block across the bottom third, below the text",
        "the percent change reads like '+12.3%' and is never coloured",
    ],
    "table": [
        "cells can render sanitised HTML, so the data itself can carry an "
        "image or a styled badge",
    ],
}

# Shared by the three time-series charts: their extra options box replaces a
# series list wholesale rather than styling it, and accepts only plain colours.
_TIMESERIES_CANNOT = [
    "a fixed colour per series set in the chart; only a colour scheme, or "
    "label_colors in the dashboard's metadata",
    "a gradient fill",
    "a dashed or dotted line for a forecast or a second series",
    "values beside the names in the legend",
]

CANNOT: dict[str, list[str]] = {
    "pie": [
        "centre text worded any other way than 'Total: <value>'",
        "centre text on two lines, or styled other than bold 16px",
        "a legend with a value or percentage column beside each name",
    ],
    "echarts_timeseries_bar": [
        *_TIMESERIES_CANNOT,
        "rounded bar corners",
        "a chosen value label position; labels sit on top, or right when horizontal",
    ],
    "echarts_timeseries_line": [
        *_TIMESERIES_CANNOT,
        "smooth or step lines",
        "horizontal orientation",
    ],
    "echarts_area": [
        *_TIMESERIES_CANNOT,
        "a forecast confidence band, because the area is always stacked or filled",
        "horizontal orientation",
    ],
    "big_number": [
        "a red or green percent change",
        "a value coloured by rules",
        "a sparkline beside or behind the value",
        "an icon beside the label",
        "the change styled as a chip or pill",
        "the absolute change next to the percent",
    ],
    "big_number_total": [
        "a trendline, comparison, percent change or timestamp",
        "an icon beside the label, a change chip, or two numbers side by side",
    ],
    "table": [
        "sparklines or small charts in cells",
        "expandable rows or a hierarchy",
        "pinned columns",
        "a totals row styled apart from bold text",
        "a bar with an unfilled track, or fraction text like '435/720'",
        "comparison shown as triangle chips; only a plain coloured arrow",
    ],
    "pivot_table_v2": [
        "pagination, a search box or bars in cells",
        "time comparison columns",
    ],
}


def settings(source: str) -> list[str]:
    """Each control's label, with a select's choices, in panel order."""
    found: list[str] = []
    seen: set[str] = set()
    for section, line in SHARED_SECTIONS.items():
        if f"...{section}" in source:
            found.append(line)
            seen.add(line)
    names = list(_NAME.finditer(source))
    for index, match in enumerate(names):
        end = names[index + 1].start() if index + 1 < len(names) else len(source)
        block = source[match.end() : end]
        label = _LABEL.search(block)
        if not label:
            continue
        text = re.sub(r"\s+", " ", label.group(2)).strip()
        if text in QUERY_LABELS or text in seen:
            continue
        seen.add(text)
        if choices := _CHOICES.search(block):
            options = [c.group(2) for c in _CHOICE_LABEL.finditer(choices.group(1))]
            if options:
                text = f"{text} ({', '.join(options)})"
        found.append(text)
        if len(found) >= MAX_SETTINGS:
            break
    return found


def card(entry: dict[str, Any], panel_source: str | None) -> str:
    """One chart type's capability card, as prompt text."""
    viz_type = str(entry.get("viz_type"))
    lines = [f"### `{viz_type}` — {entry.get('name') or viz_type}"]
    if entry.get("category"):
        lines[0] += f" [{entry['category']}]"
    if panel_source:
        if found := settings(panel_source):
            lines.append("Settings: " + "; ".join(found))
    for note in NOTES.get(viz_type, []):
        lines.append(f"Note: {note}")
    if cannot := CANNOT.get(viz_type):
        lines.append("Cannot show:")
        lines.extend(f"- {item}" for item in cannot)
    return "\n".join(lines)


def carded() -> set[str]:
    """Chart types with hand-verified lines, which stage C always sees."""
    return set(CANNOT) | set(NOTES)
