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
"""Turn an approved plan into real charts and a real dashboard.

No LLM runs here. The stages produce a plan; this executes it through
Superset's own command layer after re-validating server-side. Model output is
untrusted input.

**On atomicity.** Superset's commands are decorated with ``@transaction``, so
each one commits on its own. Wrapping them in an outer ``begin_nested()`` does
not make them atomic — the first command's commit ends the nested transaction
and the next command fails against it, leaving the first chart committed. So
this module does not pretend to be transactional: it records what it creates
and *compensates* by deleting those objects if a later step fails.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from superset.design_to_dashboard.stages.e_layout import ensure_uuids
from superset.utils import json

logger = logging.getLogger(__name__)

REF_PREFIX = "__REF__:"


class ApplyError(Exception):
    """Raised when a plan cannot be applied. Nothing is left behind."""


@dataclass
class ApplyResult:
    dashboard_id: int | None = None
    dashboard_url: str | None = None
    charts_created: list[int] = field(default_factory=list)
    charts_reused: list[int] = field(default_factory=list)
    ref_to_id: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    created_datasets: list[dict[str, Any]] = field(default_factory=list)


def substitute_refs(value: Any, ref_to_id: dict[str, int]) -> Any:
    """Replace every ``__REF__:<ref>`` with the real chart id."""
    if isinstance(value, str) and value.startswith(REF_PREFIX):
        ref = value[len(REF_PREFIX) :]
        if ref not in ref_to_id:
            raise ApplyError(f"unresolved chart ref {ref!r}")
        return ref_to_id[ref]
    if isinstance(value, dict):
        return {k: substitute_refs(v, ref_to_id) for k, v in value.items()}
    if isinstance(value, list):
        return [substitute_refs(item, ref_to_id) for item in value]
    return value


# Physical types that DATE_TRUNC cannot be applied to, whatever the dataset's
# `is_dttm` flag claims. Superset lets a column be marked temporal while its
# column type stays numeric -- the bundled `video_game_sales.year` is BIGINT
# with `is_dttm = true` -- and every stage downstream believes the flag.
_NON_TEMPORAL_TYPES = (
    "INT",
    "BIGINT",
    "SMALLINT",
    "FLOAT",
    "DOUBLE",
    "NUMERIC",
    "DECIMAL",
    "REAL",
)


def _numeric_columns(datasource_id: int) -> set[str]:
    """Column names whose physical type cannot take a time grain."""
    from superset import db
    from superset.connectors.sqla.models import TableColumn

    rows = (
        db.session.query(TableColumn.column_name, TableColumn.type)
        .filter(TableColumn.table_id == datasource_id)
        .all()
    )
    return {
        name
        for name, type_ in rows
        if type_ and any(t in type_.upper() for t in _NON_TEMPORAL_TYPES)
    }


def strip_invalid_grains(payload: Any, numeric: set[str]) -> Any:
    """Remove time grains that target a numerically-typed column.

    A grain on such a column makes Superset emit `DATE_TRUNC('year', <number>)`,
    which the database rejects and the chart renders as an error. Stage D is
    told not to do this, and stage B is told not to bind the grain, but both
    read the same `is_dttm` flag the dataset gets wrong -- so this last check is
    deterministic rather than another instruction.
    """
    if isinstance(payload, dict):
        column = payload.get("sqlExpression") or payload.get("column_name")
        if payload.get("timeGrain") and column in numeric:
            payload = {k: v for k, v in payload.items() if k != "timeGrain"}
        return {k: strip_invalid_grains(v, numeric) for k, v in payload.items()}
    if isinstance(payload, list):
        return [strip_invalid_grains(item, numeric) for item in payload]
    return payload


def build_query_context(  # noqa: C901
    params: dict[str, Any], datasource_id: int, datasource_type: str = "table"
) -> dict[str, Any]:
    """Derive a query context from a chart's form data.

    Superset normally builds this in the browser, via each viz plugin's
    ``buildQuery``. A chart saved without one renders in a dashboard (the
    frontend rebuilds it) but fails ``GET /api/v1/chart/<id>/data/`` with
    "Chart has no query context saved", which breaks thumbnails, alerts and
    any API consumer.

    This derives the common shape — metrics, grouping columns, filters, limit,
    ordering — which covers the viz types this pipeline emits. Stage D may also
    supply its own; that takes precedence.
    """
    metrics = params.get("metrics")
    if metrics is None and params.get("metric") is not None:
        metrics = [params["metric"]]
    metrics = metrics or []

    columns: list[Any] = []
    for key in ("groupby", "columns", "all_columns"):
        value = params.get(key)
        if isinstance(value, list):
            columns.extend(value)
    x_axis = params.get("x_axis")
    if x_axis and x_axis not in columns:
        columns.insert(0, x_axis)
    # Never carry a grain onto the axis column: on an integer "year" column it
    # emits DATE_TRUNC against a number and the chart fails to render.
    columns = [
        {k: v for k, v in c.items() if k != "timeGrain"} if isinstance(c, dict) else c
        for c in columns
    ]
    # De-duplicate while preserving order.
    seen: set[str] = set()
    ordered_columns = []
    for column in columns:
        key = (
            json.dumps(column, sort_keys=True)
            if not isinstance(column, str)
            else column
        )
        if key not in seen:
            seen.add(key)
            ordered_columns.append(column)

    query: dict[str, Any] = {
        "filters": [],
        "extras": {"having": "", "where": ""},
        "applied_time_extras": {},
        "columns": ordered_columns,
        "metrics": metrics,
        "annotation_layers": [],
        "series_limit": 0,
        "order_desc": bool(params.get("order_desc", True)),
        "url_params": {},
        "custom_params": {},
        "custom_form_data": {},
        "row_limit": params.get("row_limit") or 1000,
    }

    for clause in params.get("adhoc_filters") or []:
        if not isinstance(clause, dict):
            continue
        if clause.get("operator") == "TEMPORAL_RANGE":
            query["filters"].append(
                {
                    "col": clause.get("subject"),
                    "op": "TEMPORAL_RANGE",
                    "val": clause.get("comparator", "No filter"),
                }
            )
        elif clause.get("expressionType") == "SIMPLE" and clause.get("subject"):
            query["filters"].append(
                {
                    "col": clause["subject"],
                    "op": clause.get("operator", "=="),
                    "val": clause.get("comparator"),
                }
            )

    if metrics:
        query["orderby"] = [[metrics[0], not query["order_desc"]]]

    return {
        "datasource": {"id": datasource_id, "type": datasource_type},
        "force": False,
        "queries": [query],
        "form_data": params,
        "result_format": "json",
        "result_type": "full",
    }


def _order_charts(
    specs: list[dict[str, Any]], plan: dict[str, Any]
) -> list[dict[str, Any]]:
    """Children before the wrapper that references them."""
    children: set[str] = {
        child
        for decision in plan.get("decisions", [])
        if decision.get("decision") == "wrap"
        for child in decision.get("children") or []
    }
    return sorted(specs, key=lambda spec: 0 if spec.get("ref") in children else 1)


def plan_datasets(plan: dict[str, Any]) -> list[dict[str, Any]]:
    """Virtual datasets this run must create before any chart points at one.

    Two kinds, and the difference matters to whoever reads the dashboard:

    - ``derived`` — real data, reshaped. A master table exists but the
      dashboard needs a different grain, so the SQL aggregates or joins it.
      The numbers are true.
    - ``placeholder`` — literal rows taken from the design, because no table
      holds this at all. The layout is real; the numbers are not.

    Both are virtual, so neither writes a table into the warehouse and both are
    repointed later by editing the chart's datasource. One dataset may serve
    several regions -- three KPI tiles reading one summary is one dataset, not
    three.
    """
    specs = []
    for spec in plan.get("created_datasets") or []:
        if not isinstance(spec, dict) or not spec.get("name"):
            continue
        if spec.get("kind") not in {"derived", "placeholder"}:
            raise ApplyError(
                f"dataset {spec['name']!r} has kind {spec.get('kind')!r}; "
                "expected 'derived' or 'placeholder'"
            )
        if not spec.get("database_id"):
            raise ApplyError(f"dataset {spec['name']!r} has no database_id")
        if not (spec.get("sql") or "").strip():
            raise ApplyError(f"dataset {spec['name']!r} has no SQL")
        specs.append(spec)
    return specs


PLACEHOLDER_PREFIX = "d2d_placeholder_"


def create_virtual_dataset(spec: dict[str, Any], user_id: int) -> int:
    """Create one virtual dataset from a SQL statement.

    Virtual means a saved SELECT, not a table: no DDL runs, nothing is written
    to the source database, and swapping a chart onto real data later is a
    datasource change rather than a migration.

    A ``placeholder`` is name-prefixed so it is unmistakable in the dataset
    list, in Explore's datasource picker, and in any audit of what this
    pipeline created. A ``derived`` dataset holds real data and is named for
    what it contains.
    """
    from superset.commands.dataset.create import CreateDatasetCommand

    name = spec["name"]
    if spec["kind"] == "placeholder" and not name.startswith(PLACEHOLDER_PREFIX):
        name = f"{PLACEHOLDER_PREFIX}{name}"
    dataset = CreateDatasetCommand(
        {
            "database": spec["database_id"],
            "table_name": name,
            "sql": spec["sql"].strip(),
            "owners": [user_id],
        }
    ).run()
    logger.info("created %s dataset %s (id %s)", spec["kind"], name, dataset.id)
    return int(dataset.id)


def apply_plan(  # noqa: C901
    design_analysis: dict[str, Any],
    plan: dict[str, Any],
    chart_specs: list[dict[str, Any]],
    layout: dict[str, Any],
    dashboard_title: str | None = None,
) -> ApplyResult:
    """Create the charts and the dashboard described by the plan.

    Must run inside a Flask request context with ``g.user`` set — the same
    requirement the MCP gateway has, and for the same reason.
    """
    from flask import g

    from superset import db
    from superset.commands.chart.create import CreateChartCommand
    from superset.commands.dashboard.create import CreateDashboardCommand
    from superset.commands.dashboard.update import UpdateDashboardCommand
    from superset.models.slice import Slice

    result = ApplyResult()
    created_datasets: list[int] = []
    user_id = getattr(g.user, "id", None)
    if user_id is None:
        raise ApplyError("apply_plan needs a request context with g.user set")

    # ---- virtual datasets, before any chart that points at one -------------
    # A section the instance cannot serve at the right grain still gets built:
    # either on a `derived` dataset that reshapes a real master table, or on a
    # `placeholder` of literal rows. Created first because the charts reference
    # the resulting id, and one dataset may serve several regions.
    region_dataset: dict[str, int] = {}
    for spec in plan_datasets(plan):
        dataset_id = create_virtual_dataset(spec, user_id)
        created_datasets.append(dataset_id)
        for region_id in spec.get("region_ids") or []:
            region_dataset[region_id] = dataset_id
        result.created_datasets.append(
            {
                "dataset_id": dataset_id,
                "name": spec["name"],
                "kind": spec["kind"],
                "reason": spec.get("reason"),
                "region_ids": spec.get("region_ids") or [],
            }
        )

    # ---- reuse decisions map straight to existing ids ----------------------
    for decision in plan.get("decisions", []):
        if decision.get("decision") == "reuse" and decision.get("ref"):
            chart_id = decision.get("existing_chart_id")
            if not isinstance(chart_id, int):
                raise ApplyError(
                    f"reuse decision for {decision['region_id']} has no chart id"
                )
            if db.session.query(Slice).filter(Slice.id == chart_id).first() is None:
                raise ApplyError(f"reused chart {chart_id} does not exist")
            result.ref_to_id[decision["ref"]] = chart_id
            result.charts_reused.append(chart_id)

    usable = [
        spec for spec in chart_specs if spec.get("spec") and not spec.get("error")
    ]
    skipped = [spec for spec in chart_specs if spec not in usable]
    for spec in skipped:
        result.warnings.append(
            f"chart {spec.get('ref')} skipped: {spec.get('error') or 'no spec'}"
        )

    created_charts: list[int] = []
    created_dashboard_id: int | None = None

    try:
        for entry in _order_charts(usable, plan):
            body = dict(entry["spec"]["request"]["body"])
            # A chart on a dataset this run creates cannot know its id: the
            # dataset was created moments ago, in this function. Stage D wrote
            # whatever it was given, so the real id is substituted here.
            if created_id := region_dataset.get(entry.get("region_id") or ""):
                body["datasource_id"] = created_id
                body["datasource_type"] = "table"
            params = entry["spec"].get("params_decoded")
            if not isinstance(params, dict):
                params = json.loads(body.get("params") or "{}")
            params = substitute_refs(params, result.ref_to_id)

            datasource_type = body.get("datasource_type", "table")
            # Prefer a query context from stage D; derive one otherwise so the
            # chart is queryable through the API, not only inside a dashboard.
            numeric = _numeric_columns(body["datasource_id"])
            axis = params.get("x_axis")
            if params.get("time_grain_sqla") and (axis in numeric or not axis):
                params.pop("time_grain_sqla", None)

            raw_qc = body.get("query_context")
            if isinstance(raw_qc, str) and raw_qc.strip():
                decoded_qc = strip_invalid_grains(json.loads(raw_qc), numeric)
                for query in decoded_qc.get("queries") or []:
                    extras = query.get("extras")
                    if isinstance(extras, dict) and axis in numeric:
                        extras.pop("time_grain_sqla", None)
                query_context = json.dumps(decoded_qc)
            else:
                query_context = json.dumps(
                    build_query_context(params, body["datasource_id"], datasource_type)
                )

            chart = CreateChartCommand(
                {
                    "slice_name": body["slice_name"],
                    "viz_type": body["viz_type"],
                    "datasource_id": body["datasource_id"],
                    "datasource_type": datasource_type,
                    "params": json.dumps(params),
                    "query_context": query_context,
                    "owners": [user_id],
                }
            ).run()
            created_charts.append(chart.id)
            result.ref_to_id[entry["ref"]] = chart.id

        position = substitute_refs(
            dict(layout.get("position_json") or {}), result.ref_to_id
        )
        position = ensure_uuids(position)

        title = dashboard_title or _derive_title(design_analysis)
        dashboard = CreateDashboardCommand(
            {
                "dashboard_title": title,
                "owners": [user_id],
                "published": False,
            }
        ).run()
        created_dashboard_id = dashboard.id

        metadata = {
            "color_scheme": (plan.get("design_system") or {}).get("color_scheme"),
            "native_filter_configuration": _build_native_filters(plan),
            "chart_configuration": {},
            "global_chart_configuration": {
                "scope": {"rootPath": ["ROOT_ID"], "excluded": []},
                "chartsInScope": [],
            },
            "expanded_slices": {},
            "refresh_frequency": 0,
        }
        # `slices` is a SQLAlchemy relationship: it takes Slice objects, not
        # ids. The update command setattr's the value straight onto the model,
        # so ints raise "'int' object has no attribute '_sa_instance_state'".
        all_ids = created_charts + result.charts_reused
        slice_objects = (
            db.session.query(Slice).filter(Slice.id.in_(all_ids)).all()
            if all_ids
            else []
        )
        UpdateDashboardCommand(
            dashboard.id,
            {
                "position_json": json.dumps(position),
                "json_metadata": json.dumps(metadata),
                "slices": slice_objects,
            },
        ).run()

        result.charts_created = created_charts
        result.dashboard_id = dashboard.id
        result.dashboard_url = f"/superset/dashboard/{dashboard.id}/"

    except Exception as ex:  # noqa: BLE001
        _compensate(created_charts, created_dashboard_id, created_datasets)
        raise ApplyError(
            f"apply failed after {len(created_charts)} chart(s); "
            f"created objects were removed: {ex}"
        ) from ex

    logger.info(
        "applied plan: dashboard=%s created=%d reused=%d",
        result.dashboard_id,
        len(result.charts_created),
        len(result.charts_reused),
    )
    return result


def _derive_title(design_analysis: dict[str, Any]) -> str:
    """Name the dashboard after the design's own heading.

    Stage A records the page title as a `header` region, not in `global`, so
    reading `global["title"]` always fell through to the generic fallback.
    """
    regions = design_analysis.get("regions") or []
    for region in regions:
        if region.get("role") == "header" and region.get("title"):
            return str(region["title"])[:200]
    for region in regions:
        if region.get("title"):
            return str(region["title"])[:200]
    return "Design to Dashboard"


def _compensate(
    chart_ids: list[int],
    dashboard_id: int | None,
    dataset_ids: list[int] | None = None,
) -> None:
    """Undo a partial apply.

    Superset's commands commit as they go, so a failure halfway through leaves
    real rows behind. There is no transaction to roll back — the objects are
    deleted explicitly instead.
    """
    from superset import db
    from superset.connectors.sqla.models import SqlaTable
    from superset.models.dashboard import Dashboard
    from superset.models.slice import Slice

    try:
        if dashboard_id is not None:
            dashboard = db.session.query(Dashboard).get(dashboard_id)
            if dashboard is not None:
                db.session.delete(dashboard)
        for chart_id in chart_ids:
            chart = db.session.query(Slice).get(chart_id)
            if chart is not None:
                db.session.delete(chart)
        # Placeholder datasets are ours and nothing else can reference them yet,
        # so a failed apply must not leave them in the dataset list.
        for dataset_id in dataset_ids or []:
            dataset = db.session.query(SqlaTable).get(dataset_id)
            if dataset is not None:
                db.session.delete(dataset)
        # Not a @transaction: this runs *after* the commands that created the
        # charts have already committed, so there is no unit of work left to
        # roll back -- the cleanup is itself the compensating write.
        db.session.commit()  # pylint: disable=consider-using-transaction
        logger.info(
            "compensated: removed %d chart(s) and %s dashboard",
            len(chart_ids),
            "1" if dashboard_id else "0",
        )
    except Exception:  # noqa: BLE001
        db.session.rollback()  # pylint: disable=consider-using-transaction
        logger.exception(
            "compensation failed; charts %s and dashboard %s may remain",
            chart_ids,
            dashboard_id,
        )


def _build_native_filters(plan: dict[str, Any]) -> list[dict[str, Any]]:
    """Translate stage C's native filters into dashboard metadata."""
    filters: list[dict[str, Any]] = []
    for index, native in enumerate(plan.get("native_filters") or []):
        filter_id = f"NATIVE_FILTER-d2d-{index}"
        filters.append(
            {
                "id": filter_id,
                "name": native.get("name") or f"Filter {index + 1}",
                "filterType": native.get("filterType") or "filter_select",
                "type": "NATIVE_FILTER",
                "targets": native.get("targets") or [],
                "defaultDataMask": {
                    "extraFormData": {},
                    "filterState": {},
                    "ownState": {},
                },
                "controlValues": {"multiSelect": True, "enableEmptyFilter": False},
                "scope": {"rootPath": ["ROOT_ID"], "excluded": []},
                "cascadeParentIds": [],
            }
        )
    return filters
