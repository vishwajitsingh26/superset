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
"""What stage F is about to build, shown to the user before it builds it.

Stage C's plan is approved as prose. That is the right shape for "is this the
right dashboard", and the wrong shape for "is this the right set of plugins":
a person cannot tell from a sentence whether three cards really are one
component, and that single judgement decides how many plugins get written.

So this assembles the same decisions into something a person can check by
looking -- each distinct thing being built, the design cropped to it with its
own edge outlined, and the facts that cost something: how many of the design's
sections share it, how many queries it adds to every dashboard load, and
whether it reads data at all.

Nothing here calls a model. Every fact is already in stage A's regions, stage
B's bindings and stage C's decisions; the work is grouping them the way a
reviewer reads the page, top to bottom.
"""

from __future__ import annotations

import logging
import pathlib
from typing import Any

from superset.design_to_dashboard import crop

logger = logging.getLogger(__name__)

# Decisions that produce nothing to review. `drop` is still reported, as the
# list of sections that will not exist -- silence there reads as agreement.
DROPPED = "drop"

# What each archetype is, for someone who does not know the word. The review
# exists to be read by a person deciding whether to spend ten minutes of
# generation on it, and "container" does not tell them anything.
ARCHETYPE_LABELS = {
    "viz": "a chart",
    "container": "a panel that holds other charts",
    "table": "a table with drawn cells, not plain text",
    "filter_widget": "a filter that drives the rest of the dashboard",
    "navigation": "navigation between dashboard states",
}


def _label_for(decision: dict[str, Any]) -> str:
    archetype = decision.get("plugin_archetype") or "viz"
    return ARCHETYPE_LABELS.get(archetype, archetype)


def _group_key(decision: dict[str, Any]) -> str:
    """What makes two decisions the same thing to build.

    A viz type, for anything that becomes a chart: stage C names one plugin
    per distinct component, so three provider cards carrying the same
    `viz_type` are one entry with three regions behind it -- which is exactly
    the judgement this review exists to let someone check.

    Text is keyed by region instead. Two headings are not one component; they
    are two different strings that happen to render the same way.
    """
    kind = decision.get("decision")
    if kind == "grid_text":
        return f"text:{decision.get('region_id')}"
    if kind == "reuse":
        return f"reuse:{decision.get('existing_chart_id')}"
    return f"{kind}:{decision.get('viz_type')}"


def _queries(
    decision: dict[str, Any], binding: dict[str, Any], shared_dataset_id: Any
) -> tuple[int, str]:
    """How many queries this adds to every dashboard load, and why.

    The number a user is paying for is per *load*, forever -- not the tool
    calls the pipeline spends once. A container is zero because it draws no
    data of its own; the charts inside it are separate entries with their own
    queries, and counting them twice would overstate the page.
    """
    if decision.get("decision") == "grid_text":
        return 0, "static text, no query"
    if decision.get("plugin_archetype") == "container":
        return 0, "draws no data itself; the charts it holds query on their own"
    dataset_id = binding.get("dataset_id")
    if dataset_id and shared_dataset_id and dataset_id == shared_dataset_id:
        return 0, "attached to the shared dataset because Superset requires one"
    return 1, "one query per region that draws data"


def _dataset_name(
    binding: dict[str, Any], binding_set: dict[str, Any]
) -> tuple[str, bool]:
    """The dataset behind a region, and whether it is really read.

    Returns the shared dataset under its own name rather than an id, because
    "shared_no_query" is the one answer a reviewer should notice: a section
    pointed at it is a section that will render nothing from the warehouse.
    """
    dataset_id = binding.get("dataset_id")
    if not dataset_id:
        return "none yet", False
    if dataset_id == binding_set.get("shared_dataset_id"):
        return "shared (draws no data)", False
    for group in ("views", "fact_tables"):
        for entry in binding_set.get(group) or []:
            if entry.get("dataset_id") == dataset_id:
                return str(entry.get("name") or dataset_id), True
    return str(dataset_id), True


def build(  # noqa: C901
    design_analysis: dict[str, Any],
    binding_set: dict[str, Any],
    plan: dict[str, Any],
    image_paths: list[str],
    crops_dir: pathlib.Path,
) -> dict[str, Any]:
    """Assemble the review payload, in the order the page is read.

    Every entry names a `crop_region_id` rather than carrying the image, so
    the picture is fetched once by the browser instead of riding in an event
    that is replayed on every reconnect.
    """
    regions = {
        region.get("region_id"): region
        for region in design_analysis.get("regions") or []
        if region.get("region_id")
    }
    bindings = {
        binding.get("region_id"): binding
        for binding in binding_set.get("bindings") or []
        if binding.get("region_id")
    }
    shared_dataset_id = binding_set.get("shared_dataset_id")

    grouped: dict[str, dict[str, Any]] = {}
    dropped: list[dict[str, Any]] = []

    for decision in plan.get("decisions") or []:
        region_id = decision.get("region_id") or ""
        region = regions.get(region_id) or {}
        if decision.get("decision") == DROPPED:
            dropped.append(
                {
                    "region_id": region_id,
                    "title": region.get("title") or region.get("role") or region_id,
                    "why": decision.get("rationale") or "",
                }
            )
            continue

        key = _group_key(decision)
        binding = bindings.get(region_id) or {}
        member = {
            "region_id": region_id,
            "title": region.get("title") or region.get("role") or region_id,
            "y": float((region.get("bbox") or {}).get("y") or 0),
        }
        if key in grouped:
            entry = grouped[key]
            entry["used_by"].append(member)
            queries, _ = _queries(decision, binding, shared_dataset_id)
            entry["queries"] += queries
            continue

        queries, query_note = _queries(decision, binding, shared_dataset_id)
        dataset, draws_data = _dataset_name(binding, binding_set)
        grouped[key] = {
            "key": key,
            "kind": decision.get("decision"),
            "title": decision.get("slice_name") or member["title"],
            "viz_type": decision.get("viz_type"),
            "what": _label_for(decision),
            "rationale": decision.get("rationale") or "",
            "fidelity_loss": decision.get("fidelity_loss") or "",
            "used_by": [member],
            "queries": queries,
            "query_note": query_note,
            "dataset": dataset,
            "draws_data": draws_data,
            # The crop shown is the first region's: entries are built in stage
            # C's order, which puts a container's children before it, so the
            # first member is the earliest one on the page.
            "crop_region_id": region_id,
            "text": decision.get("text") or "",
        }

    entries = sorted(grouped.values(), key=lambda e: min(m["y"] for m in e["used_by"]))

    for entry in entries:
        entry["used_by"].sort(key=lambda m: m["y"])
        entry["crop_region_id"] = entry["used_by"][0]["region_id"]
        entry["crop"] = _crop_for(
            regions.get(entry["crop_region_id"]) or {}, image_paths, crops_dir
        )

    built = [e for e in entries if e["kind"] == "new_plugin"]
    return {
        "entries": entries,
        "dropped": dropped,
        "counts": {
            "plugins": len(built),
            "regions_covered": sum(len(e["used_by"]) for e in built),
            "queries_per_load": sum(e["queries"] for e in entries),
        },
    }


def _crop_for(
    region: dict[str, Any], image_paths: list[str], crops_dir: pathlib.Path
) -> str | None:
    """The review thumbnail for one region, outlined, or None."""
    if not region:
        return None
    path = crop.region_crop(
        image_paths,
        region,
        crops_dir,
        highlight=True,
        max_width=crop.REVIEW_MAX_WIDTH,
    )
    return pathlib.Path(path).name if path else None


def apply_feedback(
    plan: dict[str, Any], answer: dict[str, Any], review: dict[str, Any]
) -> list[str]:
    """Attach the reviewer's notes to the decisions they were written about.

    A note here is build guidance -- "render all three toggles", "keep the
    icon outlined" -- and rides into stage F's prompt for that plugin only.
    Anything structural belongs at stage C's gate, which runs immediately
    before this one and can re-plan; by the time the plugins are being built
    the dataset work is already done.

    Returns the keys that carried a note, for the event log.
    """
    notes = answer.get("notes") or {}
    if not isinstance(notes, dict):
        return []
    by_key = {entry["key"]: entry for entry in review.get("entries") or []}
    touched: list[str] = []
    for key, note in notes.items():
        text = str(note or "").strip()
        entry = by_key.get(key)
        if not text or not entry:
            continue
        # `build_note` has exactly one reader -- stage F, which runs only for
        # a plugin being built. A note on a reused chart or a text block was
        # attached, counted, and reported back as "noted", and then nothing
        # read it. Saying so is the honest outcome: the user can still act on
        # it, and a silent drop is the one thing they cannot.
        if entry["kind"] != "new_plugin":
            touched.append(f"{key} (not applied: nothing is being built here)")
            continue
        members = {member["region_id"] for member in entry["used_by"]}
        for decision in plan.get("decisions") or []:
            if decision.get("region_id") in members:
                decision["build_note"] = text
        touched.append(key)
    return touched
