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
import re
from dataclasses import dataclass, field
from typing import Any

from superset.design_to_dashboard.stages.e_layout import ensure_uuids, REF_PREFIX
from superset.utils import json

logger = logging.getLogger(__name__)


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
        if spec.get("kind") not in DATASET_KINDS:
            raise ApplyError(
                f"dataset {spec['name']!r} has kind {spec.get('kind')!r}; "
                f"expected one of {sorted(DATASET_KINDS)}"
            )
        if not spec.get("database_id"):
            raise ApplyError(f"dataset {spec['name']!r} has no database_id")
        if spec["kind"] == "view" and not (spec.get("sql") or "").strip():
            raise ApplyError(f"view dataset {spec['name']!r} has no SQL")
        if spec["kind"] == "fact" and not (spec.get("rows") or []):
            raise ApplyError(f"fact table {spec['name']!r} has no rows")
        specs.append(spec)
    return specs


# Placeholder tables are materialised here rather than as virtual datasets: a
# physical table behaves identically to a real one everywhere in Superset --
# distinct-value fetching for filters, column typing, Explore -- and matching
# the design's behaviour exactly is the point of building it at all. Confining
# them to one schema keeps them obvious and makes cleanup a single DROP SCHEMA.
# One dashboard, one fact table, named after the design it serves. A physical
# table behaves identically to a real one everywhere in Superset -- distinct
# values for filters, column typing, Explore -- so the finished dashboard
# behaves exactly as it will once someone repoints it at real data. Which is
# also why the columns are named as the real table would name them: swapping
# the datasource is only painless when the names already line up.
#
# `view` datasets are saved SELECTs over that table, one per group of sections
# that need the same shape. `shared` is the single row every dashboard borrows
# for a chart that renders but never queries -- a nav bar, a wrapper frame.
#
# Confining all of it to one schema keeps it obvious and makes cleanup a single
# DROP SCHEMA.
DATASET_SCHEMA = "d2d"
DATASET_KINDS = {"fact", "view", "shared"}
_IDENTIFIER = re.compile(r"^[a-z_][a-z0-9_]{0,60}$")
_COLUMN_TYPES = {
    "TEXT",
    "BIGINT",
    "INTEGER",
    "DOUBLE PRECISION",
    "NUMERIC",
    "BOOLEAN",
    "DATE",
    "TIMESTAMP",
}


def _identifier(name: str, what: str) -> str:
    """Reject anything that is not a plain lowercase identifier.

    These names reach DDL, where they cannot be parameterised. The model writes
    them, so they are validated rather than trusted.
    """
    if not _IDENTIFIER.match(name or ""):
        raise ApplyError(f"unsafe {what} name: {name!r}")
    return name


def materialise_fact_table(spec: dict[str, Any], schema: str = DATASET_SCHEMA) -> None:
    """Create a real table holding the design's own values.

    Values are bound as parameters; only identifiers and the column type are
    interpolated, and both are validated first. The table is dropped and
    recreated so a re-run is idempotent.
    """
    from sqlalchemy import text

    from superset import db as superset_db
    from superset.models.core import Database

    table = _identifier(spec["name"], "table")
    schema = _identifier(schema, "schema")
    columns = spec.get("columns") or []
    rows = spec.get("rows") or []
    if not columns or not rows:
        raise ApplyError(f"fact table {table!r} needs columns and rows")

    names = [_identifier(c["name"], "column") for c in columns]
    types = []
    for column in columns:
        column_type = (column.get("type") or "TEXT").upper()
        if column_type not in _COLUMN_TYPES:
            raise ApplyError(f"unsupported column type {column_type!r} in {table!r}")
        types.append(column_type)

    database = superset_db.session.query(Database).get(spec["database_id"])
    if database is None:
        raise ApplyError(f"database {spec['database_id']} not found")

    definition = ", ".join(f"{n} {t}" for n, t in zip(names, types, strict=True))
    placeholders = ", ".join(f":{n}" for n in names)
    with database.get_sqla_engine() as engine, engine.begin() as connection:
        connection.execute(text(f"CREATE SCHEMA IF NOT EXISTS {schema}"))
        connection.execute(text(f"DROP TABLE IF EXISTS {schema}.{table}"))
        connection.execute(text(f"CREATE TABLE {schema}.{table} ({definition})"))
        # S608: every identifier here has passed `_identifier`, and the row
        # values are bound parameters -- DDL and column lists cannot be
        # parameterised, so validation is the control.
        columns_sql = ", ".join(names)
        insert = (
            f"INSERT INTO {schema}.{table} "  # noqa: S608
            f"({columns_sql}) VALUES ({placeholders})"
        )
        connection.execute(
            text(insert),
            [dict(zip(names, row, strict=True)) for row in rows],
        )
    logger.info("materialised %s.%s with %d row(s)", schema, table, len(rows))


def create_dataset(spec: dict[str, Any], user_id: int) -> int:
    """Create the Superset dataset a spec describes.

    A ``derived`` dataset stays virtual -- a saved SELECT over real tables, so
    the numbers are live and nothing is copied. A ``placeholder`` is
    materialised as a real table first, because a physical dataset behaves
    identically to any other everywhere in Superset, and matching the design's
    behaviour exactly is the whole reason for building the section.
    """
    from superset.commands.dataset.create import CreateDatasetCommand

    name = spec["name"]
    if spec["kind"] in {"fact", "shared"}:
        materialise_fact_table(spec)
        properties = {
            "database": spec["database_id"],
            "schema": DATASET_SCHEMA,
            "table_name": name,
            "owners": [user_id],
        }
    else:
        properties = {
            "database": spec["database_id"],
            "table_name": name,
            "sql": spec["sql"].strip(),
            "owners": [user_id],
        }
    dataset = CreateDatasetCommand(properties).run()
    logger.info("created %s dataset %s (id %s)", spec["kind"], name, dataset.id)
    return int(dataset.id)


def prune_unresolved(position: dict[str, Any], ref_to_id: dict[str, int]) -> list[str]:
    """Drop layout nodes whose chart was never created. Returns what went.

    Stages D and E run in parallel, so E places every chart C planned and has
    no way to know which of them D failed to configure. A chart D could not
    produce is skipped at creation, and its `__REF__:` placeholder then had
    nothing to resolve to -- which aborted the whole apply over one missing
    card, throwing away every chart that *had* been built.

    Removing the node instead loses that one section and keeps the dashboard,
    which is the right trade: the section is already unbuildable, and the run
    has been paid for.
    """
    doomed = [
        node_id
        for node_id, node in position.items()
        if isinstance(node, dict)
        and isinstance((node.get("meta") or {}).get("chartId"), str)
        and node["meta"]["chartId"].startswith(REF_PREFIX)
        and node["meta"]["chartId"][len(REF_PREFIX) :] not in ref_to_id
    ]
    if not doomed:
        return []
    for node_id in doomed:
        position.pop(node_id, None)
    # A parent still listing a removed child renders an empty slot, so the
    # references have to go too.
    for node in position.values():
        if isinstance(node, dict) and isinstance(node.get("children"), list):
            node["children"] = [
                child for child in node["children"] if child not in doomed
            ]
    return sorted(doomed)


def _dataset_for(region_dataset: dict[str, int], region_id: str | None) -> int | None:
    """The dataset this run created for a region, matched in either direction.

    A container is one region to stage A, several bindings to stage B
    (`r07_card:1`, `:2`) and -- as the traces show -- decisions for *both* the
    bare parent and some of the children in stage C. Which of those two
    namespaces a created dataset is filed under is not fixed: stage B's prompt
    example once showed the parent, and now asks for the children.

    So the match cannot assume a direction. An exact hit wins; then the
    parent; then any child of the same parent. Matching one way only meant a
    chart kept the `datasource_id` the model invented for a dataset that did
    not exist yet, and Superset rejected it as "Chart parameters are invalid"
    after the run had been paid for.
    """
    if not region_id:
        return None
    if exact := region_dataset.get(region_id):
        return exact
    parent = region_id.split(":")[0]
    if inherited := region_dataset.get(parent):
        return inherited
    # A decision for the bare parent, against a dataset filed under a child.
    # Sorted so the same plan always resolves to the same dataset.
    for key, dataset_id in sorted(region_dataset.items()):
        if key.split(":")[0] == parent:
            return dataset_id
    return None


def _assert_datasets_exist(specs: list[dict[str, Any]]) -> None:
    """Fail before creating anything if a chart points at no real dataset.

    The first check on a `datasource_id` used to be Superset's own command,
    reached one chart at a time after the datasets and the earlier charts were
    already committed. A bad id there costs the entire run and compensation
    deletes the evidence, so the same check runs here, up front, where it costs
    nothing and names every offender at once.
    """
    from superset import db
    from superset.connectors.sqla.models import SqlaTable

    wanted = {
        spec["spec"]["request"]["body"].get("datasource_id")
        for spec in specs
        if spec.get("spec") and not spec.get("error")
    }
    wanted.discard(None)
    if not wanted:
        return
    # Addressed through `__table__.c` rather than the mapped attribute:
    # `SqlaTable` inherits `id: int` from superset_core's `Dataset`, so the
    # attribute resolves to its Python type and loses the column's `in_`.
    # The table's own column carries no such annotation.
    dataset_id = SqlaTable.__table__.c.id
    found = {
        row[0] for row in db.session.query(dataset_id).filter(dataset_id.in_(wanted))
    }
    if missing := sorted(wanted - found):
        raise ApplyError(
            f"no dataset exists with id(s) {missing}: the plan points at "
            "datasets that are neither in this instance nor created by this "
            "run. Nothing was created."
        )


def _why(ex: Exception) -> str:
    """The detail Superset's own errors carry but do not print.

    `ChartInvalidError` says only "Chart parameters are invalid" -- which field
    of which chart is in its `exceptions` list, and losing it means the next
    run repeats the failure with nothing to act on.
    """
    parts: list[str] = []
    for sub in (
        getattr(ex, "_exceptions", None) or getattr(ex, "exceptions", None) or []
    ):
        messages = getattr(sub, "normalized_messages", None)
        try:
            parts.append(str(messages() if callable(messages) else sub))
        except Exception:  # noqa: BLE001 - reporting must not raise
            parts.append(repr(sub))
    return f" -- {'; '.join(parts)}" if parts else ""


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
        dataset_id = create_dataset(spec, user_id)
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
    # A chart that failed stage D's checks is still created -- skipping it
    # would leave a hole in a layout built around it -- but it is created
    # knowingly. Without this the only record was a count in a progress line.
    for spec in usable:
        if problems := spec.get("problems"):
            result.warnings.append(
                f"chart {spec.get('ref')} created with "
                f"{len(problems)} unresolved problem(s): {'; '.join(problems)[:300]}"
            )

    # Repoint every chart at the dataset this run created for it *before*
    # anything is written, so the existence check below sees the ids the charts
    # will really be created with rather than the placeholders stage D wrote.
    for entry in usable:
        if created_id := _dataset_for(region_dataset, entry.get("region_id")):
            body = entry["spec"]["request"]["body"]
            body["datasource_id"] = created_id
            body["datasource_type"] = "table"
    _assert_datasets_exist(usable)

    created_charts: list[int] = []
    created_dashboard_id: int | None = None
    # What the failing chart was, kept outside the loop: `_compensate` deletes
    # every chart, dataset and table this run made, so once it has run there is
    # nothing left to inspect. Without this a failed apply reports only that
    # something was invalid.
    attempting: dict[str, Any] = {}

    try:
        for entry in _order_charts(usable, plan):
            # Already repointed at any dataset this run created, and every id
            # confirmed to exist, before the loop started.
            body = dict(entry["spec"]["request"]["body"])
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

            attempting = {
                "region_id": entry.get("region_id"),
                "ref": entry.get("ref"),
                "slice_name": body.get("slice_name"),
                "viz_type": body.get("viz_type"),
                "datasource_id": body.get("datasource_id"),
                "datasource_type": datasource_type,
            }
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

        position = dict(layout.get("position_json") or {})
        for dropped in prune_unresolved(position, result.ref_to_id):
            result.warnings.append(
                f"layout node {dropped} removed: its chart was not created"
            )
        position = substitute_refs(position, result.ref_to_id)
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

        metadata: dict[str, Any] = {
            "color_scheme": (plan.get("design_system") or {}).get("color_scheme"),
            # Native filters are configured by hand afterwards by whoever
            # wants them; nothing in this pipeline creates one.
            "native_filter_configuration": [],
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
        logger.error("apply failed while creating chart %s", attempting)
        _compensate(created_charts, created_dashboard_id, created_datasets)
        raise ApplyError(
            f"apply failed after {len(created_charts)} chart(s); "
            f"created objects were removed: {ex}{_why(ex)}"
            + (f" -- while creating {attempting}" if attempting else "")
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
    from sqlalchemy import text

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
        # Datasets this run created are ours and nothing else references them
        # yet. A placeholder also left a real table behind, which deleting the
        # Superset dataset does not remove, so drop that too.
        for dataset_id in dataset_ids or []:
            dataset = db.session.query(SqlaTable).get(dataset_id)
            if dataset is None:
                continue
            if dataset.schema == DATASET_SCHEMA and dataset.database:
                try:
                    with (
                        dataset.database.get_sqla_engine() as engine,
                        engine.begin() as connection,
                    ):
                        connection.execute(
                            text(
                                "DROP TABLE IF EXISTS "
                                f"{DATASET_SCHEMA}.{dataset.table_name}"
                            )
                        )
                except Exception:  # noqa: BLE001 - cleanup is best-effort
                    logger.exception(
                        "could not drop placeholder table %s.%s",
                        DATASET_SCHEMA,
                        dataset.table_name,
                    )
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
