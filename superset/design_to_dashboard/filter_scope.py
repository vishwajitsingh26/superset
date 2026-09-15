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
"""What a filter drawn in the grid is allowed to filter.

A design that draws its own date picker wants two things Superset normally
puts in different places: the control at a particular spot on the page, and no
filter panel at all. Both come free from the same decision -- register nothing
in `native_filter_configuration`, and let the control be what Superset already
calls a chart in the grid that filters other charts: a cross-filter emitter.

The panel then does not render, and nothing has to hide it. `nativeFiltersEnabled`
is false for a viewer when a dashboard has no native filters and no chart
customizations, so the bar has no reason to exist.

What the control does need is a scope, and that is the whole point of this
module. Scope is resolved by id: a mask is looked up in the native filter
table, then in `chart_configuration`, and failing both it is applied to every
chart on the dashboard. A generated picker declaring only `NativeFilter` was in
neither table, which is how one month ended up across a whole page. The entry
this module writes is what puts it in the second.

Two things are worth knowing before reading the scope it produces.

A time range does not filter on its own. `_apply_filters` overwrites the value
of a chart's existing `TEMPORAL_RANGE` filters and does nothing when a chart
has none, so the blast radius is already limited to charts that opted in by
carrying one. Scope narrows that further; it cannot widen it.

And an explicit scope does not exclude the emitter. Only the global-scope
pointer drops a chart from its own reach, so a picker with a real scope has to
list itself, or its own bounds query is windowed by the range the user just
picked.
"""

from __future__ import annotations

from typing import Any

# Superset's own root, from the frontend's dashboard constants. `scope` is read
# by `calculateScopes`, which returns an empty scope unless `excluded` is a
# list -- so it is always written, even when nothing is excluded.
DASHBOARD_ROOT_ID = "ROOT_ID"

# Decisions that put a control on the page rather than a reading of data.
FILTER_ARCHETYPES = {"filter_widget"}

# A chart that plots a series over time is the one thing a page-level date
# range usually must not touch: the design shows the picker on one month while
# the trend beside it draws four. Detected from the chart's own params rather
# than guessed from its title.
TREND_KEYS = ("x_axis", "granularity_sqla")

# Roles whose whole output is a series, and which have no way to ask for more
# data than the filter gives them.
#
# A stock time-series chart is one query and one range. Window it to a single
# month and it draws a single point, and nothing in its configuration can widen
# it back. Keeping it out of the date filter's scope is the only lever there
# is.
#
# A `kpi` card is deliberately *not* here, though it draws a series too. A card
# is a generated plugin, and a generated plugin can issue a second query over a
# wider window -- so it follows the dashboard's date like everything else while
# its sparkline keeps enough periods to be a sparkline. That requirement lives
# in the stage F prompt; this set is for the charts that cannot.
TREND_ROLES = {"chart"}


def is_filter(decision: dict[str, Any]) -> bool:
    """Whether this decision puts a filter control on the page."""
    return (
        decision.get("plugin_archetype") in FILTER_ARCHETYPES
        and decision.get("decision") != "drop"
    )


def filter_decisions(plan: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        d for d in plan.get("decisions") or [] if isinstance(d, dict) and is_filter(d)
    ]


def filter_region_ids(plan: dict[str, Any]) -> set[str]:
    """The regions that carry a filter control.

    Chart specs know their region but not their archetype -- that lives on the
    plan's decision -- so every consumer that starts from a spec has to come
    back here to find out what it is looking at.
    """
    return {str(d.get("region_id")) for d in filter_decisions(plan)}


def _params_of(spec: dict[str, Any]) -> dict[str, Any]:
    params = spec.get("params_decoded")
    return params if isinstance(params, dict) else {}


def _roles(design_analysis: dict[str, Any] | None) -> dict[str, str]:
    return {
        str(r.get("region_id")): str(r.get("role") or "")
        for r in (design_analysis or {}).get("regions") or []
        if isinstance(r, dict)
    }


def trend_regions(
    chart_specs: list[dict[str, Any]],
    skip: set[str] | None = None,
    design_analysis: dict[str, Any] | None = None,
) -> list[str]:
    """Regions that plot a series over time, as their output.

    Two facts are needed and they live in different stages. Whether the chart
    has a temporal axis comes from the params stage D wrote, so it describes
    the chart that will really be built. Whether the region *is* a series comes
    from stage A's role, because a KPI card has a temporal axis too and is not
    one. `skip` carries the filter regions, which are controls, not charts.

    Without a reading, no role is known and nothing is treated as a trend: the
    filter then covers the whole page, which is Superset's own behaviour.
    """
    ignore = skip or set()
    roles = _roles(design_analysis)
    found: list[str] = []
    for spec in chart_specs:
        region_id = str(spec.get("region_id"))
        if region_id in ignore or roles.get(region_id) not in TREND_ROLES:
            continue
        if any(_params_of(spec).get(key) for key in TREND_KEYS):
            found.append(region_id)
    return found


# The answers to the one question this module puts to the user.
SCOPE_ALL = "all"
SCOPE_EXCEPT_TRENDS = "except_trends"
SCOPE_QUESTION_ID = "filter_scope"


def question(
    plan: dict[str, Any],
    chart_specs: list[dict[str, Any]],
    design_analysis: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Which charts the page-level filter governs.

    A genuine ambiguity in the design rather than something to infer: the
    mockup draws the picker on one month while the trend charts beside it draw
    four, and no pixel says whether the trends are meant to ignore the picker
    or whether the mockup is simply inconsistent with itself. Asked once, for
    the whole page, because a per-chart interrogation is not what the user came
    for.
    """
    if not filter_decisions(plan):
        return None
    trends = trend_regions(chart_specs, filter_region_ids(plan), design_analysis)
    if not trends:
        return None
    named = ", ".join(_title_of(plan, region_id) for region_id in trends)
    return {
        "id": SCOPE_QUESTION_ID,
        "region_id": None,
        "question": (
            "Should the page's date range also filter the charts that plot a "
            f"trend over time ({named})?"
        ),
        "why_it_matters": (
            "The design shows the picker on a single month while those charts "
            "draw several, so the two disagree. Filtering them collapses each "
            "to one point; leaving them out keeps their history and matches "
            "what the design draws."
        ),
        "options": [
            "No, leave them out so they keep their full history",
            "Yes, filter every chart on the page",
        ],
        "default": "No, leave them out so they keep their full history",
    }


def _title_of(plan: dict[str, Any], region_id: str) -> str:
    for decision in plan.get("decisions") or []:
        if isinstance(decision, dict) and decision.get("region_id") == region_id:
            return str(decision.get("slice_name") or region_id)
    return region_id


def scope_from_answer(answer: Any) -> str:
    """The user's reply, as one of the scope choices."""
    if not isinstance(answer, str):
        return SCOPE_EXCEPT_TRENDS
    text = answer.strip().lower()
    if text in (SCOPE_ALL, SCOPE_EXCEPT_TRENDS):
        return text
    if text.startswith("yes") or "every chart" in text:
        return SCOPE_ALL
    return SCOPE_EXCEPT_TRENDS


def build(
    plan: dict[str, Any],
    chart_specs: list[dict[str, Any]],
    ref_to_id: dict[str, int],
    scope: str = SCOPE_EXCEPT_TRENDS,
    design_analysis: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """The dashboard's `chart_configuration`, keyed by chart id.

    `chartsInScope` is deliberately left empty: `calculateScopes` recomputes it
    from `scope.excluded` on every load, so a value written here would be stale
    the moment a chart is added or moved.
    """
    own = filter_region_ids(plan)
    excluded_regions = (
        set()
        if scope == SCOPE_ALL
        else set(trend_regions(chart_specs, own, design_analysis))
    )
    by_region = {
        str(spec.get("region_id")): ref_to_id.get(str(spec.get("ref")))
        for spec in chart_specs
    }
    configuration: dict[str, Any] = {}
    for region_id in sorted(own):
        emitter_id = by_region.get(region_id)
        if emitter_id is None:
            continue
        # The emitter is listed in its own `excluded`: only the global-scope
        # pointer drops a chart from its own reach, and a control that filters
        # itself windows the query its own options are read from.
        excluded = sorted(
            {
                chart_id
                for region, chart_id in by_region.items()
                if chart_id is not None
                and (region in excluded_regions or region == region_id)
            }
        )
        configuration[str(emitter_id)] = {
            "id": emitter_id,
            "crossFilters": {
                "scope": {
                    "rootPath": [DASHBOARD_ROOT_ID],
                    "excluded": excluded,
                },
                "chartsInScope": [],
            },
        }
    return configuration


def effects(
    plan: dict[str, Any],
    chart_specs: list[dict[str, Any]],
    scope: str = SCOPE_EXCEPT_TRENDS,
    design_analysis: dict[str, Any] | None = None,
) -> list[str]:
    """What the filter governs, in plain words.

    Scope is chosen mechanically here rather than asked, because the fact it
    turns on -- whether a chart draws a series over time -- is already decided
    by the time anything could be asked. Saying so out loud is the part that
    matters: a filter that silently skips two charts looks like a bug until
    someone explains it was deliberate.
    """
    own = filter_region_ids(plan)
    if not own:
        return []
    notes: list[str] = []
    names = {
        str(d.get("region_id")): str(d.get("slice_name") or d.get("region_id"))
        for d in plan.get("decisions") or []
        if isinstance(d, dict)
    }
    controls = ", ".join(names.get(r, r) for r in sorted(own))
    if scope == SCOPE_ALL:
        notes.append(
            f"{controls} filters every chart on the page that carries a time "
            "filter of its own."
        )
        return notes
    if trends := trend_regions(chart_specs, own, design_analysis):
        listed = ", ".join(names.get(r, r) for r in trends)
        notes.append(
            f"{controls} does not filter {listed}, which draw a series over "
            "time and would collapse to a single point. They keep their full "
            "history, as the design draws them."
        )
    notes.append(
        "A chart is only reachable by a date filter if it carries a time "
        "filter of its own; one that does not is unaffected whatever the "
        "scope says."
    )
    return notes


def _temporal_comparators(spec: dict[str, Any]) -> list[str]:
    """Every `TEMPORAL_RANGE` comparator a chart's own adhoc filters carry."""
    return [
        str(clause.get("comparator"))
        for clause in _params_of(spec).get("adhoc_filters") or []
        if isinstance(clause, dict) and clause.get("operator") == "TEMPORAL_RANGE"
    ]


# A comparator left this way carries no range of its own -- the chart is
# either unfiltered by design, or it is meant to follow a page-level control
# through the cross-filter mask (`_apply_filters` overwrites this value; it
# never reads it). Either reading is consistent with a chart kept out of the
# date filter's scope so it keeps its full history.
_NO_RANGE = {"", "no filter", "none"}


def range_conflicts(
    plan: dict[str, Any],
    chart_specs: list[dict[str, Any]],
    scope: str = SCOPE_EXCEPT_TRENDS,
    design_analysis: dict[str, Any] | None = None,
) -> list[str]:
    """A chart's own configured range that contradicts why it is excluded.

    `trend_regions` keeps a chart out of the page filter's reach so it draws
    its full history, as the design shows it. A chart pinned to one narrow
    span of its own -- a literal comparator rather than a placeholder --
    already contradicts that before the page filter ever runs, and drew the
    same single point the exclusion exists to prevent. This is the mechanical
    half of "does the built range match what the design draws"; there is no
    render this deterministic check can see, only the parameters that will
    produce one.
    """
    if scope == SCOPE_ALL:
        return []
    own = filter_region_ids(plan)
    trends = set(trend_regions(chart_specs, own, design_analysis))
    if not trends:
        return []
    names = {
        str(d.get("region_id")): str(d.get("slice_name") or d.get("region_id"))
        for d in plan.get("decisions") or []
        if isinstance(d, dict)
    }
    problems: list[str] = []
    for spec in chart_specs:
        region_id = str(spec.get("region_id"))
        if region_id not in trends:
            continue
        for comparator in _temporal_comparators(spec):
            if comparator.strip().lower() not in _NO_RANGE:
                problems.append(
                    f"{names.get(region_id, region_id)}: kept out of the page "
                    f"filter's scope to draw its full history, but its own "
                    f"TEMPORAL_RANGE filter is pinned to {comparator!r} -- it "
                    "will still draw a single point"
                )
    return problems
