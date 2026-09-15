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
"""The gate between stage A and stage B: show the reading, wait for the user.

Every question this module raises exists because stage B has to guess
something stage A's schema does not yet carry -- see the docstring on each
`_GAP_*` constant for the exact place in `b_bind.py` or `B_design_data.md`
that guesses instead of being told. This module does not change stage B; it
gives the user a chance to answer before stage A hands its reading over, and
`a_decompose.revise` folds the answers back into fields stage B can be taught
to read in a later pass.

The presentation is a tree (so nesting is visible the way it will be built)
plus a flat, deduplicated question list (so the existing `questions` hygiene
-- ids, near-duplicate collapse -- is reused rather than re-invented).
"""

from __future__ import annotations

import re
from typing import Any

from superset.design_to_dashboard.stages.b_bind import NON_DATA_ROLES, SERIES_KEYWORDS

# A real printed value, not a stray digit -- `observed` mentions font sizes
# ("~13px") and hex colours on every region, wrapper included, so "contains a
# digit" fires on all of them. This requires the shape of an actual number: a
# currency amount, a percentage, or a thousands-grouped figure.
_VALUE_PATTERN = re.compile(r"\$\s?\d|\d+(\.\d+)?\s?%|\d{1,3}(,\d{3})+")

# Every clarifying question is tagged with which gap in stage B it closes, so
# the tag survives into `answers_to_your_questions` and a later pass teaching
# stage B to read the new fields knows which answers were about what.
GAP_WRAPPER_READS_DATA = "wrapper_reads_data"  # b_bind.py:525, NON_DATA_ROLES
GAP_EMBEDDED_SERIES = "embedded_series"  # b_bind.py:416,497, keyword match
GAP_SHARED_GRAIN = "shared_grain"  # B_design_data.md Step 1, same_as unused
GAP_FILTER_KIND = "filter_kind"  # B_design_data.md Step 5, inferred from prose
GAP_AMBIGUITY = "ambiguity"  # region.ambiguity; a_decompose.revise() flags it
# unanswered, and C_resolve.md is told not to re-ask it
GAP_PLUGIN_CHOICE = "plugin_choice"  # decided by stage C today, no user input


def _looks_data_bearing(region: dict[str, Any]) -> bool:
    """Whether a non-data-role region's own text suggests it prints a value.

    Heuristic, not authoritative -- it only decides whether to *ask*, the way
    a smoke test decides whether to page someone, not whether the pager is
    right. A false positive costs one skippable question; a false negative
    costs a silently-dropped total, which is the actual defect on record for
    this gap (see GAP_WRAPPER_READS_DATA).
    """
    blob = " ".join(
        str(region.get(field) or "") for field in ("title", "observed", "implied_data")
    )
    return bool(_VALUE_PATTERN.search(blob))


def _mentions_series(region: dict[str, Any]) -> bool:
    treatment = " ".join(str(t) for t in region.get("unusual_treatment") or [])
    return any(kw in treatment.lower() for kw in SERIES_KEYWORDS)


def _plugin_question(region: dict[str, Any]) -> dict[str, Any]:
    """The one question every leaf region gets: build it stock, or custom.

    Deliberately carries no recommendation or default. Stage A's own
    registry match is real information -- it says whether a stock chart
    exists that could render this -- but it is not a suggested answer: it is
    shown the same way whether or not one was found, and stage A never gets
    to have judged stock-vs-custom for the user, only to have looked one
    thing up for them to weigh. The user knows their design; this pipeline
    does not.
    """
    candidate = region.get("stock_candidate")
    note = (
        f"stage A found a registered viz type that could render this as "
        f"drawn: {candidate!r}. That is a lookup, not a recommendation -- "
        "either option is a real choice."
        if candidate
        else "stage A found no registered viz type that renders this as "
        "drawn. That does not settle it either way."
    )
    return {
        "id": f"plugin:{region['region_id']}",
        "options": ["stock", "custom"],
        "stock_candidate": candidate,
        "note": note,
    }


def _composition(region: dict[str, Any], by_n: dict[int, dict[str, Any]]) -> str:
    """What this region consists of, in the vocabulary the gate shows the user."""
    children = [c for c in region.get("children") or [] if isinstance(c, int)]
    if children:
        names = ", ".join(
            by_n[c].get("title") or by_n[c].get("region_id") or str(c)
            for c in children
            if c in by_n
        )
        return f"Holds {len(children)} region(s): {names}."
    observed = str(region.get("observed") or "").strip()
    return (
        observed[:280] + ("…" if len(observed) > 280 else "")
        if observed
        else "No detail recorded."
    )


def _behavior(region: dict[str, Any]) -> str:
    """How this section is expected to behave once built."""
    parts: list[str] = []
    frame = region.get("frame")
    if frame == "toggle":
        parts.append(
            "View switches on a toggle: "
            f"{region.get('frame_why') or 'renderer changes per state'}."
        )
    elif frame == "tabs":
        parts.append(
            "Content switches on tabs: "
            f"{region.get('frame_why') or 'a different query per tab'}."
        )
    if controls := region.get("controls") or []:
        kinds = ", ".join(str(c.get("kind")) for c in controls if isinstance(c, dict))
        parts.append(f"Controls: {kinds}.")
    if interactions := region.get("interactions") or []:
        parts.append("Interactions: " + "; ".join(str(i) for i in interactions) + ".")
    if not parts:
        parts.append(
            "Static display; no interaction beyond what Superset gives every chart."
        )
    return " ".join(parts)


def _questions_for(
    region: dict[str, Any], same_as_group: list[str]
) -> list[dict[str, Any]]:
    """Every clarifying question this region raises, each tagged with its gap."""
    out: list[dict[str, Any]] = []
    region_id = region["region_id"]
    role = region.get("role")

    if role in NON_DATA_ROLES and _looks_data_bearing(region):
        out.append(
            {
                "id": f"q:{region_id}:reads_data",
                "region_id": region_id,
                "gap": GAP_WRAPPER_READS_DATA,
                "text": (
                    f'"{region.get("title") or region_id}" is a {role}, which stage B '
                    "normally binds to no data at all -- but it looks like it prints a "
                    "real value. Does it need to read real data, and if so what?"
                ),
            }
        )

    if (
        role != "wrapper"
        and _mentions_series(region)
        and not region.get("has_embedded_series")
    ):
        out.append(
            {
                "id": f"q:{region_id}:series",
                "region_id": region_id,
                "gap": GAP_EMBEDDED_SERIES,
                "text": (
                    f'"{region.get("title") or region_id}" seems to draw a small '
                    "embedded trend alongside its headline. Should it be wired to real "
                    "time-series data, and over what span?"
                ),
            }
        )

    if role == "filter":
        out.append(
            {
                "id": f"q:{region_id}:filter_kind",
                "region_id": region_id,
                "gap": GAP_FILTER_KIND,
                "text": (
                    f'"{region.get("title") or region_id}" is a filter. What column '
                    "should it filter on, where do its options come from "
                    "(a fixed list vs. your data), and does picking a value apply "
                    "immediately or wait for a commit action?"
                ),
            }
        )

    if len(same_as_group) > 1 and region_id == same_as_group[0]:
        titles = ", ".join(same_as_group)
        out.append(
            {
                "id": f"q:{region_id}:shared_grain",
                "region_id": region_id,
                "gap": GAP_SHARED_GRAIN,
                "text": (
                    f"{titles} are the same component repeated. Should they share one "
                    "underlying table (same grain, filtered differently per card), or "
                    "does each read a genuinely separate data source?"
                ),
            }
        )

    if ambiguity := region.get("ambiguity"):
        out.append(
            {
                "id": f"q:{region_id}:ambiguity",
                "region_id": region_id,
                "gap": GAP_AMBIGUITY,
                "text": (
                    f"Stage A flagged an ambiguity here and guessed: {ambiguity} "
                    "Is that reading right?"
                ),
            }
        )

    return out


def build_presentation(design_analysis: dict[str, Any]) -> dict[str, Any]:
    """Everything the gate shows the user: the region tree and every question.

    Pure and read-only -- it does not mutate `design_analysis`, and calling it
    twice on the same reading produces the same presentation, the same way
    `assign_region_ids` is deterministic. `revise` is what changes state.
    """
    regions = [r for r in design_analysis.get("regions") or [] if isinstance(r, dict)]
    by_n = {r["n"]: r for r in regions if isinstance(r.get("n"), int)}
    groups = _same_as_groups(regions, by_n)

    all_questions: list[dict[str, Any]] = []
    nodes: dict[str, dict[str, Any]] = {}
    for region in regions:
        region_id = region.get("region_id")
        if not region_id:
            continue
        n = region.get("n")
        same_as_group = groups.get(n, []) if isinstance(n, int) else []
        region_questions = _questions_for(region, same_as_group)
        all_questions.extend(region_questions)
        nodes[region_id] = {
            "region_id": region_id,
            "n": region.get("n"),
            "title": region.get("title"),
            "role": region.get("role"),
            "composition": _composition(region, by_n),
            "behavior": _behavior(region),
            "plugin_choice": (
                None if region.get("role") == "wrapper" else _plugin_question(region)
            ),
            "question_ids": [q["id"] for q in region_questions],
            "children": [],
        }

    # `questions.normalise_questions` is not used here: its dedupe treats two
    # questions sharing one `region_id` as the same question, which is right
    # for stage C (one question per region) and wrong here by construction --
    # a single region routinely raises several, one per gap. Ids are already
    # unique (`q:{region_id}:{gap-specific suffix}`, at most one per gap per
    # region), so all that is left to do is trust that and index by region.
    questions_by_region: dict[str, list[dict[str, Any]]] = {}
    for question in all_questions:
        questions_by_region.setdefault(question["region_id"], []).append(question)
    for region_id, node in nodes.items():
        node["question_ids"] = [q["id"] for q in questions_by_region.get(region_id, [])]

    roots = _nest_by_children(regions, nodes, by_n)

    return {
        "label": "Review how I read your design before I build the data",
        "dashboard_title": (design_analysis.get("global") or {}).get("title"),
        "regions": roots,
        "questions": all_questions,
    }


def _same_as_groups(
    regions: list[dict[str, Any]], by_n: dict[int, dict[str, Any]]
) -> dict[int, list[str]]:
    """`same_as` region numbers to the region_ids sharing that group.

    First-occurrence first, so the shared-grain question is asked once per
    group rather than once per repeat.
    """
    groups: dict[int, list[str]] = {}
    for region in regions:
        target = region.get("same_as")
        if target is None or target not in by_n or not region.get("region_id"):
            continue
        head_id = by_n[target].get("region_id")
        if head_id:
            groups.setdefault(target, [head_id]).append(region["region_id"])
    return groups


def _nest_by_children(
    regions: list[dict[str, Any]],
    nodes: dict[str, dict[str, Any]],
    by_n: dict[int, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Nest `nodes` by `children` (region numbers); a region named in
    nobody's `children` is a root.
    """
    child_numbers = {c for region in regions for c in (region.get("children") or [])}
    roots = []
    for region in regions:
        region_id = region.get("region_id")
        if not region_id:
            continue
        node = nodes[region_id]
        node["children"] = [
            nodes[by_n[c]["region_id"]]
            for c in (region.get("children") or [])
            if c in by_n and by_n[c].get("region_id") in nodes
        ]
        if region.get("n") not in child_numbers:
            roots.append(node)
    return roots
