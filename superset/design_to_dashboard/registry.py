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
"""The chart types this deployment has, and what each stage is told about them.

Built from source at the start of every run by :func:`build`, frozen for the
run, and rebuilt once after stage F writes new plugins. A snapshot is saved
with the run so a retry or a resume works from the registry the run started
with.

Every stage used to read one committed JSON file, about eight times a run, and
each got all of it. Now each asks for its own view:

  * stage A names a likely chart type per region, so it gets names grouped by
    category -- about a fifteenth of the text it used to receive;
  * stage C decides, so it gets the summaries, the valid types and capability
    cards for the chart types it is likely to weigh;
  * stage D configures one chart, so it gets that chart's settings panel;
  * stage F must not duplicate a chart type, so it gets the set that exists.
"""

from __future__ import annotations

import logging
import pathlib
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from superset.utils import json

logger = logging.getLogger(__name__)


class RegistryError(Exception):
    """Raised when the manifest is missing or unusable."""


def load(path: str | pathlib.Path) -> list[dict[str, Any]]:
    """Load the manifest and return its viz-type entries."""
    manifest_path = pathlib.Path(path)
    if not manifest_path.exists():
        raise RegistryError(
            f"No viz registry at {manifest_path}. Generate it with "
            f"design-to-dashboard/scripts/build_viz_registry.py"
        )
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    entries = payload.get("viz_types")
    if not entries:
        raise RegistryError(f"Viz registry at {manifest_path} has no viz_types")
    return entries


def render_summaries(
    entries: list[dict[str, Any]], include_filters: bool = False
) -> str:
    """Render entries as compact prompt text.

    Summaries only - key, name, category, tags, one-line description. Stage C
    chooses a viz type from these; it never configures one, so the full control
    schema (which is ~140k tokens across the registry) is deliberately absent.
    """
    charts = [e for e in entries if include_filters or not e.get("is_filter")]
    custom = [e for e in charts if e.get("custom")]
    upstream = [e for e in charts if not e.get("custom")]

    lines: list[str] = []
    if custom:
        lines.append("### Custom plugins (this deployment) — check these first\n")
        lines.extend(_render_group(custom))
        lines.append("")
    lines.append("### Upstream Superset viz types\n")
    lines.extend(_render_group(upstream))
    return "\n".join(lines)


def _render_group(entries: list[dict[str, Any]]) -> list[str]:
    lines = []
    for entry in sorted(
        entries, key=lambda e: (e.get("category") or "~", e["viz_type"])
    ):
        description = (entry.get("description") or "").strip()
        if len(description) > 180:
            description = description[:177].rsplit(" ", 1)[0] + "…"
        tags = ", ".join(entry.get("tags") or [])
        parts = [f"- `{entry['viz_type']}` — **{entry.get('name') or '?'}**"]
        if entry.get("category"):
            parts.append(f"[{entry['category']}]")
        lines.append(" ".join(parts))
        if description:
            lines.append(f"    {description}")
        if tags:
            lines.append(f"    tags: {tags}")
    return lines


def find(entries: list[dict[str, Any]], viz_type: str) -> dict[str, Any]:
    """Return the manifest entry for one viz type."""
    for entry in entries:
        if entry["viz_type"] == viz_type:
            return entry
    raise RegistryError(f"viz_type {viz_type!r} is not in the registry")


def load_control_panel(entry: dict[str, Any], repo_root: str | pathlib.Path) -> str:
    """Read the control-panel source for one viz type.

    Stage D gets the real source rather than a re-derived schema: it is ground
    truth, it cannot drift, and one panel is 2-30 KB against ~140k tokens for
    the whole registry.
    """
    relative = entry.get("control_panel")
    if not relative:
        raise RegistryError(
            f"No control panel recorded for {entry['viz_type']!r}. "
            f"Re-run build_viz_registry.py, or add a CONTROL_PANEL_OVERRIDES entry."
        )
    path = pathlib.Path(repo_root) / relative
    if not path.exists():
        raise RegistryError(f"Control panel missing on disk: {path}")
    return path.read_text(encoding="utf-8")


def filter_types(entries: list[dict[str, Any]]) -> list[str]:
    """Registered native-filter plugin keys, for validating stage C output."""
    return sorted(e["viz_type"] for e in entries if e.get("is_filter"))


def chart_types(entries: list[dict[str, Any]]) -> set[str]:
    """Viz types a chart can actually be configured as.

    A registered viz type with no recorded control panel is not one of them:
    stage D loads that panel to know which controls exist, so without it the
    chart cannot be configured and is dropped from the dashboard. Offering the
    type to stage C and discarding its chart later is the worst order to
    discover that in -- the section is simply missing, after the run is paid
    for. Excluding it here means C picks something it can build, and its
    re-plan loop says why.

    Filter plugins are excluded separately and keep their own list: a native
    filter is configured by the dashboard's filter bar, not by stage D, so a
    missing panel does not stop one being used.
    """
    return {
        e["viz_type"]
        for e in entries
        if not e.get("is_filter") and e.get("control_panel")
    }


# --- the per-run registry ----------------------------------------------------


@dataclass
class Registry:
    """One run's chart types, and the view each stage reads."""

    entries: list[dict[str, Any]]
    repo_root: pathlib.Path
    built_at: float = 0.0
    dropped: list[str] = field(default_factory=list)
    warnings: dict[str, list[str]] = field(default_factory=dict)

    # persistence

    def snapshot(self) -> dict[str, Any]:
        """What a retry or a resume needs to use this exact registry again."""
        return {
            "built_at": self.built_at,
            "entries": self.entries,
            "dropped": self.dropped,
            "warnings": self.warnings,
        }

    @classmethod
    def from_snapshot(
        cls, snapshot: dict[str, Any], repo_root: pathlib.Path
    ) -> Registry:
        entries = snapshot.get("entries") or []
        if not entries:
            raise RegistryError("registry snapshot has no entries")
        return cls(
            entries=list(entries),
            repo_root=repo_root,
            built_at=float(snapshot.get("built_at") or 0.0),
            dropped=list(snapshot.get("dropped") or []),
            warnings=dict(snapshot.get("warnings") or {}),
        )

    # lookups every stage shares

    def viz_types(self) -> set[str]:
        return {str(entry["viz_type"]) for entry in self.entries}

    def chart_types(self) -> set[str]:
        return chart_types(self.entries)

    def filter_types(self) -> list[str]:
        return filter_types(self.entries)

    def find(self, viz_type: str) -> dict[str, Any]:
        return find(self.entries, viz_type)

    # stage A

    def stage_a_text(self) -> str:
        """Chart type names grouped by category, for naming a likely candidate.

        No descriptions or tags. Stage A names one type per region at most and
        stage C makes the real decision; the full summaries were most of stage
        A's registry text and the source of the bias its prompt warns about --
        knowing chart names before describing the picture.
        """
        groups: dict[str, list[str]] = defaultdict(list)
        for entry in self.entries:
            if entry.get("is_filter"):
                continue
            group = "Custom" if entry.get("custom") else entry.get("category")
            groups[str(group or "Other")].append(str(entry["viz_type"]))
        return "\n".join(
            f"{group}: {', '.join(sorted(names))}"
            for group, names in sorted(groups.items())
        )

    # stage C

    def stage_c_text(self) -> str:
        return render_summaries(self.entries)

    def capability_card(self, viz_type: str) -> str:
        """One stock chart type's card. Custom plugins get none."""
        from superset.design_to_dashboard import capabilities

        entry = self.find(viz_type)
        if entry.get("custom"):
            raise RegistryError(f"{viz_type!r} is a custom plugin and has no card")
        panel = None
        if entry.get("control_panel"):
            try:
                panel = load_control_panel(entry, self.repo_root)
            except RegistryError:
                panel = None
        return capabilities.card(entry, panel)

    def card_shortlist(self, design_analysis: dict[str, Any]) -> list[str]:
        """The stock chart types stage C is likely to weigh.

        Every stock type stage A named as a candidate, plus the types with
        hand-verified lines, which are the ones designs use most. Anything else
        stage C can look up with its capability tool.
        """
        from superset.design_to_dashboard import capabilities

        stock = {
            str(entry["viz_type"])
            for entry in self.entries
            if not entry.get("custom") and not entry.get("is_filter")
        }
        named = {
            str(region.get("stock_candidate"))
            for region in design_analysis.get("regions") or []
            if isinstance(region, dict) and region.get("stock_candidate")
        }
        return sorted((named | capabilities.carded()) & stock)

    def capability_cards(self, viz_types: list[str]) -> str:
        cards = []
        for viz_type in viz_types:
            try:
                cards.append(self.capability_card(viz_type))
            except RegistryError:
                continue
        return "\n\n".join(cards)

    # stage D

    def control_panel(self, viz_type: str) -> tuple[str, str]:
        """``(path, source)`` of one chart type's settings panel."""
        entry = self.find(viz_type)
        return str(entry["control_panel"]), load_control_panel(entry, self.repo_root)


def _exists(repo_root: pathlib.Path, relative: Any) -> bool:
    return bool(relative) and (repo_root / str(relative)).exists()


def build(repo_root: pathlib.Path) -> Registry:
    """Scan the source, drop what is no longer on disk, and freeze the result.

    A custom plugin whose source file is gone is dropped rather than offered.
    The committed file this replaces still listed one, and the stage that
    loaded its settings panel failed on the missing file. Stock chart types
    ship with Superset, so a missing file there is logged, not dropped.
    """
    from superset.design_to_dashboard import registry_source

    payload = registry_source.scan()
    entries: list[dict[str, Any]] = []
    dropped: list[str] = []
    for entry in payload.get("viz_types") or []:
        source = entry.get("source")
        on_disk = source == "METADATA_OVERRIDES" or _exists(repo_root, source)
        if entry.get("custom") and not on_disk:
            dropped.append(str(entry.get("viz_type")))
            continue
        entries.append(entry)
    if dropped:
        logger.warning("registry dropped chart types with no files: %s", dropped)
    if not entries:
        raise RegistryError("the source scan found no chart types")
    return Registry(
        entries=entries,
        repo_root=repo_root,
        built_at=time.time(),
        dropped=dropped,
        warnings=dict(payload.get("warnings") or {}),
    )
