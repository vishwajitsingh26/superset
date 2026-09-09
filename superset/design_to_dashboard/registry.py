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
"""The viz-type manifest stages C and D read.

Superset's chart registry lives in the frontend, and MCP's
``get_chart_type_schema`` covers only seven abstract families, so the pipeline
carries its own manifest. Regenerate with::

    python design-to-dashboard/scripts/build_viz_registry.py
"""

from __future__ import annotations

import json
import logging
import pathlib
from typing import Any

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


def render_summaries(entries: list[dict[str, Any]], include_filters: bool = False) -> str:
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
    for entry in sorted(entries, key=lambda e: (e.get("category") or "~", e["viz_type"])):
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


def load_control_panel(
    entry: dict[str, Any], repo_root: str | pathlib.Path
) -> str:
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
    """Registered non-filter viz_type keys."""
    return {e["viz_type"] for e in entries if not e.get("is_filter")}
