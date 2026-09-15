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
from typing import Any, TYPE_CHECKING

from superset.design_to_dashboard import chrome, filter_scope
from superset.design_to_dashboard.stages.e_layout import (
    ensure_uuids,
    hosted_refs,
    REF_PREFIX,
)
from superset.utils import json

if TYPE_CHECKING:
    from superset.design_to_dashboard.registry import Registry

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
    # What matching the design's chrome cost, in plain words. Returned rather
    # than logged because the user asked to be told, not to have it decided.
    chrome_effects: list[str] = field(default_factory=list)


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


def is_custom_viz_type(viz_type: str | None) -> bool:
    """Whether a viz type is a plugin this fork generated rather than a stock one.

    The same rule the registry scan applies, so the applier and the verifier
    never disagree with the registry about which charts are custom.
    """
    return bool(viz_type) and (
        str(viz_type).startswith("custom_") or viz_type == "container_chart"
    )


@dataclass(frozen=True)
class QueryControls:
    """The controls a custom plugin's ``buildQuery`` reads its query from."""

    metrics: tuple[str, ...] = ()
    columns: tuple[str, ...] = ()


# Shared controls by what they hold. A generated plugin spreads one of these
# into a control of its own name (`metricCoverage: {...sharedControls.metric}`),
# so the spread, not the name, says what the control's value is.
_METRIC_SHARED_CONTROLS = frozenset(
    {
        "metric",
        "metrics",
        "metric_2",
        "secondary_metric",
        "percent_metrics",
        "size",
        "x",
        "y",
    }
)
_DIMENSION_SHARED_CONTROLS = frozenset(
    {"groupby", "columns", "all_columns", "series", "entity", "x_axis"}
)
_METRIC_CONTROL_TYPES = frozenset({"MetricsControl", "DndMetricSelect"})
_DIMENSION_CONTROL_TYPES = frozenset({"DndColumnSelect", "DndColumnSelectControl"})
# A shared control listed by name in a row (`['metrics']`). One-letter names are
# left out: `'x'` and `'y'` are just as often a select's choice values.
_BARE_ROW_CONTROLS = (_METRIC_SHARED_CONTROLS | _DIMENSION_SHARED_CONTROLS) - {
    "x",
    "y",
    "size",
}
_NAMED_CONTROL = re.compile(r"\bname:\s*['\"]([A-Za-z_]\w*)['\"]")
_SHARED_SPREAD = re.compile(
    r"sharedControls(?:\.([A-Za-z_]\w*)|\[\s*['\"]([A-Za-z_]\w*)['\"]\s*\])"
)
_CONTROL_TYPE = re.compile(r"\btype:\s*['\"]([A-Za-z_]\w*)['\"]")
_BARE_ROW_ITEM = re.compile(r"(?<=[\[,])\s*['\"]([A-Za-z_]\w*)['\"]\s*(?=[,\]])")


def query_controls(source: str) -> QueryControls:  # noqa: C901
    """Which of a control panel's controls hold metrics and which dimensions.

    Read from the panel's source text: each named control is classified by the
    shared control it spreads, or failing that by its control ``type``, and a
    shared control listed by bare name keeps its own meaning. Anything else --
    a label, a colour, a link -- is display configuration and never queried.
    """
    metrics: list[str] = []
    columns: list[str] = []

    def add(name: str, kind: str | None) -> None:
        target = metrics if kind == "metric" else columns if kind == "column" else None
        if target is not None and name not in metrics and name not in columns:
            target.append(name)

    named = list(_NAMED_CONTROL.finditer(source))
    for index, match in enumerate(named):
        # The control's own config runs until the next control is named.
        end = named[index + 1].start() if index + 1 < len(named) else len(source)
        body = source[match.end() : end]
        spread = _SHARED_SPREAD.search(body)
        control_type = _CONTROL_TYPE.search(body)
        # Whichever comes first is the control's own: a later one belongs to
        # a row or a nested object that follows it.
        kind: str | None = None
        if spread and (not control_type or spread.start() < control_type.start()):
            shared = spread.group(1) or spread.group(2)
            if shared in _METRIC_SHARED_CONTROLS:
                kind = "metric"
            elif shared in _DIMENSION_SHARED_CONTROLS:
                kind = "column"
        elif control_type:
            if control_type.group(1) in _METRIC_CONTROL_TYPES:
                kind = "metric"
            elif control_type.group(1) in _DIMENSION_CONTROL_TYPES:
                kind = "column"
        add(match.group(1), kind)

    for match in _BARE_ROW_ITEM.finditer(source):
        name = match.group(1)
        if name in _BARE_ROW_CONTROLS:
            add(name, "metric" if name in _METRIC_SHARED_CONTROLS else "column")
    return QueryControls(metrics=tuple(metrics), columns=tuple(columns))


def _is_adhoc_metric(value: Any) -> bool:
    """An adhoc metric object, told apart from an adhoc filter by its shape."""
    if not isinstance(value, dict) or "clause" in value or "operator" in value:
        return False
    if value.get("expressionType") == "SIMPLE":
        return bool(value.get("aggregate")) and bool(value.get("column"))
    return value.get("expressionType") == "SQL" and bool(value.get("sqlExpression"))


def _control_values(params: dict[str, Any], names: tuple[str, ...]) -> list[Any]:
    """The non-empty values held by the named controls, flattened."""
    values: list[Any] = []
    for name in names:
        value = params.get(name)
        for item in value if isinstance(value, list) else [value]:
            # An unset optional control is `None` or `""`; the plugin's own
            # `buildQuery` filters those out, and a query carrying one fails.
            if item not in (None, "", [], {}):
                values.append(item)
    return values


def _custom_query_fields(
    params: dict[str, Any], controls: QueryControls | None
) -> tuple[list[Any], list[Any]]:
    """Metrics and columns a custom plugin's own controls hold.

    With the control panel, exactly the controls it types as metrics and
    dimensions. Without it, only values whose shape is unmistakably a metric --
    an adhoc metric object -- because a bare string could as well be a label.
    """
    if controls is not None:
        return (
            _control_values(params, controls.metrics),
            _control_values(params, controls.columns),
        )
    metrics = [
        item
        for key, value in params.items()
        if key not in _GENERIC_QUERY_KEYS
        for item in (value if isinstance(value, list) else [value])
        if _is_adhoc_metric(item)
    ]
    return metrics, []


# The form-data keys the generic derivation already reads.
_GENERIC_QUERY_KEYS = frozenset(
    {"metrics", "metric", "groupby", "columns", "all_columns", "x_axis"}
)


def build_query_context(  # noqa: C901
    params: dict[str, Any],
    datasource_id: int,
    datasource_type: str = "table",
    viz_type: str | None = None,
    controls: QueryControls | None = None,
) -> dict[str, Any]:
    """Derive a query context from a chart's form data.

    Superset normally builds this in the browser, via each viz plugin's
    ``buildQuery``. A chart saved without one renders in a dashboard (the
    frontend rebuilds it) but fails ``GET /api/v1/chart/<id>/data/`` with
    "Chart has no query context saved", which breaks thumbnails, alerts and
    any API consumer.

    This derives the common shape — metrics, grouping columns, filters, limit,
    ordering — which covers the stock viz types this pipeline emits. Stage D may
    also supply its own; that takes precedence.

    A custom plugin keeps its query in controls of its own naming
    (`metricCoverage`), which the generic keys never see, and its ``buildQuery``
    is TypeScript that cannot run here. So its metrics and dimensions are read
    from the controls its panel types as such (``controls``, parsed by
    `query_controls`). Where that finds nothing, the plugin draws no data --
    the convention stage F follows is to emit no query object at all -- and the
    context carries no queries: one empty query object only fails every
    consumer with "Empty query?". The result approximates the plugin's query
    for API consumers; it is not the plugin's query, which is why the verifier
    judges custom plugins by rendering them rather than through this context.
    """
    metrics = params.get("metrics")
    if metrics is None and params.get("metric") is not None:
        metrics = [params["metric"]]
    metrics = list(metrics or [])

    columns: list[Any] = []
    for key in ("groupby", "columns", "all_columns"):
        value = params.get(key)
        if isinstance(value, list):
            columns.extend(value)
    x_axis = params.get("x_axis")
    if x_axis and x_axis not in columns:
        columns.insert(0, x_axis)

    custom = is_custom_viz_type(viz_type)
    if custom:
        extra_metrics, extra_columns = _custom_query_fields(params, controls)
        metrics.extend(m for m in extra_metrics if m not in metrics)
        columns.extend(c for c in extra_columns if c not in columns)
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
        "queries": [] if custom and not metrics and not ordered_columns else [query],
        "form_data": params,
        "result_format": "json",
        "result_type": "full",
    }


def _order_charts(
    specs: list[dict[str, Any]], plan: dict[str, Any]
) -> list[dict[str, Any]]:
    """Children before the parent that references them.

    Read through `hosted_refs` rather than off `wrap` decisions: a generated
    container is re-marked `configure` once its plugin is built, so its children
    were created after it and its `__REF__`s had no id to resolve to. A dropped
    parent hosts nothing, so its charts wait behind nothing.
    """
    children = hosted_refs(plan)
    return sorted(specs, key=lambda spec: 0 if spec.get("ref") in children else 1)


def _unhosted_ids(
    chart_ids: list[int], ref_to_id: dict[str, int], plan: dict[str, Any]
) -> list[int]:
    """Chart ids that are dashboard members in their own right.

    A chart hosted inside a wrapper is rendered through Superset's own
    container, by id -- it is not a dashboard member in its own right, the
    same distinction `_order_charts` already draws via `hosted_refs` above.
    Left in `dashboard.slices` unfiltered, it is *also* an unpositioned
    member with no entry in `position_json`, and Superset appends every
    unpositioned member to the foot of the page at default size -- so a
    real, correctly-hosted chart shows up a second time as an orphan card
    underneath the dashboard it already renders inside of.
    """
    hosted_ids = {ref_to_id[ref] for ref in hosted_refs(plan) if ref in ref_to_id}
    return [chart_id for chart_id in chart_ids if chart_id not in hosted_ids]


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
    menus: str = chrome.MENU_DATA_ONLY,
    filter_scope_answer: str = filter_scope.SCOPE_EXCEPT_TRENDS,
    registry: Registry | None = None,
) -> ApplyResult:
    """Create the charts and the dashboard described by the plan.

    Must run inside a Flask request context with ``g.user`` set — the same
    requirement the MCP gateway has, and for the same reason.

    ``registry`` supplies each custom plugin's control panel, from which its
    query context is derived. Without it only adhoc metric objects are
    recognised in a custom plugin's params.
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
                    build_query_context(
                        params,
                        body["datasource_id"],
                        datasource_type,
                        viz_type=body.get("viz_type"),
                        controls=_controls_for(body.get("viz_type"), registry),
                    )
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

        design_system = plan.get("design_system") or {}
        metadata: dict[str, Any] = {
            "color_scheme": design_system.get("color_scheme"),
            # A stock chart's own `color_scheme` control only ever picks a
            # *named* scheme, and this pipeline registers none of its own --
            # so a design's exact brand colours reach stock charts here
            # instead, the same surface Superset's own dashboard properties
            # UI writes to. Applied by category label across every chart on
            # the dashboard, independent of each chart's `color_scheme`.
            "label_colors": _label_colors(design_system),
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
        all_ids = _unhosted_ids(
            created_charts + result.charts_reused, result.ref_to_id, plan
        )
        slice_objects = (
            db.session.query(Slice).filter(Slice.id.in_(all_ids)).all()
            if all_ids
            else []
        )
        # The design's card is a literal hex, which plugin source may not
        # carry. This is the one writable surface where it is legal, so the
        # holder is restyled here instead of redrawn inside every plugin.
        # A control in the grid is a cross-filter emitter, and an emitter with
        # no entry here has no scope -- which means its mask reaches every
        # chart on the dashboard. Registering nothing as a *native* filter is
        # what keeps the filter panel from rendering at all.
        metadata["chart_configuration"] = filter_scope.build(
            plan, usable, result.ref_to_id, filter_scope_answer, design_analysis
        )
        result.warnings.extend(
            filter_scope.range_conflicts(
                plan, usable, filter_scope_answer, design_analysis
            )
        )
        entries = chrome.resolve(design_analysis, plan, menus)
        css = chrome.compile_css(
            entries,
            result.ref_to_id,
            design_system,
            (design_analysis.get("global") or {}).get("page_background"),
        )
        result.chrome_effects = chrome.effects(entries) + filter_scope.effects(
            plan, usable, filter_scope_answer, design_analysis
        )
        UpdateDashboardCommand(
            dashboard.id,
            {
                "position_json": json.dumps(position),
                "json_metadata": json.dumps(metadata),
                "slices": slice_objects,
                "css": css,
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


def _controls_for(
    viz_type: str | None, registry: Registry | None
) -> QueryControls | None:
    """A custom plugin's query controls, when its control panel can be read."""
    if registry is None or not viz_type or not is_custom_viz_type(viz_type):
        return None
    from superset.design_to_dashboard.registry import RegistryError

    try:
        _, source = registry.control_panel(viz_type)
    except (RegistryError, OSError, KeyError):
        logger.info("no control panel for %s; deriving its query by shape", viz_type)
        return None
    return query_controls(source)


def _label_colors(design_system: dict[str, Any]) -> dict[str, str]:
    """Stage C's category-to-hex map, cleaned to what Superset's own dashboard
    colour settings actually accept.

    A stock chart type's own `color_scheme` control only ever picks a *named*
    scheme, and this pipeline registers none of its own, so a design's exact
    brand colours have no path to a stock chart through that control at all.
    This is the other one: Superset already lets a dashboard map a category
    label straight to a hex, applied across every chart that draws it
    regardless of `color_scheme`. Only well-formed string pairs pass through
    -- a category or colour of any other shape is a value no chart could read
    back as a category label anyway.
    """
    raw = design_system.get("label_colors")
    if not isinstance(raw, dict):
        return {}
    return {
        str(category): str(hex_value)
        for category, hex_value in raw.items()
        if isinstance(category, str) and isinstance(hex_value, str)
    }


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
