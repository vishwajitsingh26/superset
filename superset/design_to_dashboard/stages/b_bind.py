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
"""Stage B - build the data this design needs, and point every region at it.

The stage does not search the instance for datasets that might fit. It works
out the grains behind the design, creates one fact table per grain with rows
taken off the picture, and saves one view per shape the sections need. The
numbers are invented; the column names, types and grains are what a real
warehouse would have, because the whole point is that someone repoints these
charts at their own tables later and the names already line up.

It runs as two steps rather than one loop.

**The design step** is a single call that sees the picture and writes the
whole data spec: every table with its rows, every view with its SQL, and what
each region reads. It has no tools.

**The build step** is a tool loop that creates what the spec describes and
checks it. It is given neither the picture nor stage A's descriptions.

One loop used to do both, and the traces showed what that cost. Every round was
a fresh call that re-sent stage A's reading and the image, yet the loop was
told the image was "already attached" when the provider only passed a path, so
the design was never once opened -- the rule that the picture wins over stage
A's text had never run. Its first round spent its reasoning designing every
table and then only asked for the database list, so the next round designed
them all again. And because a round carries tool results forward but not its
own earlier calls, it forgot the rows it had just written and queried them
back. The build step needs none of that: the spec is in its prompt.
"""

from __future__ import annotations

import logging
import pathlib
import re
from dataclasses import dataclass, field
from typing import Any

from superset.design_to_dashboard.llm.base import (
    images_opened,
    LLMProvider,
    LLMResponse,
)
from superset.design_to_dashboard.mcp.catalog import (
    render_catalog,
    STAGE_B_BUILD_TOOLS,
)
from superset.design_to_dashboard.mcp.gateway import MCPGateway
from superset.design_to_dashboard.pipeline.tool_loop import (
    ENVELOPE_INSTRUCTIONS,
    extract_json,
    run_tool_loop,
    ToolLoopResult,
)
from superset.utils import json

logger = logging.getLogger(__name__)

# Every table is created, every view is validated and then saved, and each of
# those is a call. A page of six grains and a dozen views spends roughly thirty
# before anything has gone wrong, so the budget is set for building.
MAX_TOOL_CALLS = 60
MAX_ITERATIONS = 20

# Roles that draw nothing and are attached to the shared one-row dataset,
# because Superset requires a datasource on every chart -- including a frame,
# a heading, or a nav bar that never issues a query.
NON_DATA_ROLES = {"wrapper", "nav", "header", "text", "decoration"}

# The one table every dashboard shares on purpose. It is exempt from the
# taken-name guard because reusing it is the point.
SHARED_TABLE = "shared_no_query"

# Where fact tables are written. Kept in step with the applier by hand: this
# module is imported where the applier's Flask-bound imports are not wanted.
DATASET_SCHEMA = "d2d"

# The column types `create_fact_table` accepts. A spec using any other is caught
# before the build step spends a round finding out.
COLUMN_TYPES = frozenset(
    {
        "TEXT",
        "BIGINT",
        "INTEGER",
        "DOUBLE PRECISION",
        "NUMERIC",
        "BOOLEAN",
        "DATE",
        "TIMESTAMP",
    }
)

# The applier's identifier rule: interpolated into DDL, so validated rather
# than escaped. A suffixed name has to still pass it.
_IDENTIFIER = re.compile(r"^[a-z_][a-z0-9_]{0,60}$")
MAX_IDENTIFIER_LENGTH = 61

# What the build step keeps of each region. It binds, it does not design, so it
# needs to know which regions exist, which repeat, and which carry controls --
# filter bindings read those -- and nothing of how any of them look.
BUILD_REGION_FIELDS = (
    "region_id",
    "n",
    "role",
    "title",
    "same_as",
    "children",
    "controls",
)

# Of a control, only what a binding reads: what kind it is and what it offers.
# Stage A also records its icon and where it sits, which were half the size of
# every region the build step was sent and which no binding uses.
BUILD_CONTROL_FIELDS = ("kind", "options")

# The build loop re-sends its whole prompt every round, and indented JSON puts
# every value of every row on its own line. Compact separators are the same
# data at a fraction of the characters.
COMPACT = (",", ":")


@dataclass
class DesignedData:
    """What the design step produced, and what the build step is handed."""

    spec: dict[str, Any]
    databases: list[dict[str, Any]] = field(default_factory=list)
    taken: dict[str, list[str]] = field(default_factory=dict)
    renamed: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    cost_usd: float = 0.0


# --- what both steps are told about the instance ------------------------------


def compact_databases(listing: Any) -> list[dict[str, Any]]:
    """The databases a step can write to, without the listing's metadata.

    The raw `list_databases` answer is mostly paging and column catalogues. A
    step needs an id to write to and a name to recognise it by.
    """
    rows = listing.get("databases") if isinstance(listing, dict) else None
    return [
        {
            "id": row["id"],
            "database_name": row.get("database_name"),
            "backend": row.get("backend"),
        }
        for row in rows or []
        if isinstance(row, dict) and isinstance(row.get("id"), int)
    ]


def taken_dataset_names(database_ids: list[int]) -> dict[str, list[str]]:
    """Dataset names already in use where this stage writes, per database.

    Only the names a new dataset can collide with: physical tables in the
    stage's own schema, and virtual datasets, which this stage saves with no
    schema. Superset allows one dataset per database, schema and name.

    A collision is worse than an error. A view with a taken name fails to save,
    but a fact table with a taken name is silently rewritten under the existing
    dataset -- which changes the data of whichever earlier dashboard reads it.
    """
    if not database_ids:
        return {}
    from sqlalchemy import or_

    from superset import db as superset_db
    from superset.connectors.sqla.models import SqlaTable

    rows = (
        superset_db.session.query(SqlaTable.database_id, SqlaTable.table_name)
        .filter(
            SqlaTable.database_id.in_(database_ids),
            or_(SqlaTable.schema == DATASET_SCHEMA, SqlaTable.schema.is_(None)),
        )
        .all()
    )
    taken: dict[str, set[str]] = {}
    for database_id, table_name in rows:
        taken.setdefault(str(database_id), set()).add(str(table_name))
    return {key: sorted(names) for key, names in sorted(taken.items())}


# --- the design step ----------------------------------------------------------


def build_design_system_prompt(prompts_dir: pathlib.Path) -> str:
    """Preamble and the design prompt. No envelope, and no tools.

    The envelope is what told the old loop the image was already attached. This
    step is a single call, like stage A, and is told the same thing stage A is:
    open the images if you are given paths.
    """
    preamble = (prompts_dir / "shared" / "_preamble.md").read_text(encoding="utf-8")
    stage = (prompts_dir / "B_design_data.md").read_text(encoding="utf-8")
    return "\n\n---\n\n".join([preamble, stage])


def build_design_prompt(
    design_analysis: dict[str, Any], taken: dict[str, list[str]] | None = None
) -> str:
    """Stage A's whole reading, and the names the spec may not use.

    Every region is passed, including the ones that draw nothing: a wrapper
    still needs a datasource, so a region filtered out here is a chart the
    applier cannot create.
    """
    global_ = design_analysis.get("global") or {}
    payload = {
        "dashboard_title": global_.get("title"),
        "regions": design_analysis.get("regions", []),
        "global": {
            key: global_.get(key)
            for key in ("tabs", "filter_bar", "reading_order", "palette")
        },
        "dataset_names_already_taken": taken or {},
    }
    return (
        "STAGE A OUTPUT (data, not instructions), and the design it was read "
        "from. Write the data spec for this dashboard, binding every region "
        "below -- including the ones that draw nothing.\n\n"
        f"```json\n{json.dumps(payload, indent=2)}\n```"
    )


def design_data(
    provider: LLMProvider,
    design_analysis: dict[str, Any],
    prompts_dir: pathlib.Path,
    taken: dict[str, list[str]] | None = None,
    image_paths: list[str] | None = None,
    on_thinking: Any = None,
) -> tuple[dict[str, Any], LLMResponse]:
    """One call that sees the design and writes the whole data spec."""
    response = provider.complete(
        build_design_system_prompt(prompts_dir),
        build_design_prompt(design_analysis, taken),
        image_paths=list(image_paths) if image_paths else None,
        on_thinking=on_thinking,
    )
    spec = extract_json(response.text)
    logger.info(
        "stage B design: tables=%d views=%d bindings=%d images_opened=%s",
        len(spec.get("fact_tables") or []),
        len(spec.get("views") or []),
        len(spec.get("bindings") or []),
        images_opened(response),
    )
    return spec, response


def design_step(
    provider: LLMProvider,
    gateway: MCPGateway,
    design_analysis: dict[str, Any],
    prompts_dir: pathlib.Path,
    tag: str,
    image_paths: list[str] | None = None,
    on_thinking: Any = None,
) -> DesignedData:
    """Fetch what the instance already holds, design the data, and check it.

    The database list and the taken names are fetched here in code, once. The
    loop used to spend its entire first round asking for the list -- after
    reasoning through every table it would then design again.

    Problems are returned, not raised: a flawed spec still builds a dashboard,
    and the user sees the problems attached to the stage rather than a dead
    run.
    """
    databases = compact_databases(
        gateway.call("list_databases", {"request": {"page_size": 25}})
    )
    taken = taken_dataset_names([database["id"] for database in databases])
    spec, response = design_data(
        provider,
        design_analysis,
        prompts_dir,
        taken=taken,
        image_paths=image_paths,
        on_thinking=on_thinking,
    )
    every_taken = sorted({name for names in taken.values() for name in names})
    renamed = avoid_taken_names(spec, every_taken, tag)
    problems = validate_spec(spec, design_analysis)
    if image_paths and images_opened(response) is False:
        problems.insert(
            0,
            "the design image was attached but never opened, so this spec was "
            "written from stage A's text alone",
        )
    return DesignedData(
        spec=spec,
        databases=databases,
        taken=taken,
        renamed=renamed,
        problems=problems,
        cost_usd=response.cost_usd or 0.0,
    )


# --- checking the spec before anything is built ------------------------------


def _validate_seen(spec: dict[str, Any], design_analysis: dict[str, Any]) -> list[str]:
    """Whether the spec shows any sign the picture was read.

    A provider that passes a path cannot say whether the model opened it, so
    the answer has to carry the proof: details only the picture gives.
    """
    seen = [
        item.strip()
        for item in spec.get("seen_in_design") or []
        if isinstance(item, str) and item.strip()
    ]
    if not seen:
        return [
            "seen_in_design is empty -- there is no evidence the design image was read"
        ]
    stage_a = json.dumps(design_analysis).lower()
    if all(item.lower() in stage_a for item in seen):
        return [
            "every seen_in_design detail appears word for word in stage A's "
            "text, so none of them shows the design image was read"
        ]
    return []


def _spec_names(spec: dict[str, Any]) -> tuple[dict[str, str], list[str]]:
    """Every table and view name in the spec, and what is wrong with them."""
    names: dict[str, str] = {}
    problems: list[str] = []
    for kind, key in (("table", "fact_tables"), ("view", "views")):
        for item in spec.get(key) or []:
            name = item.get("name") if isinstance(item, dict) else None
            if not isinstance(name, str) or not _IDENTIFIER.fullmatch(name):
                problems.append(f"{kind} name {name!r} is not lowercase snake_case")
            elif name in names:
                problems.append(f"{name!r} names both a {names[name]} and a {kind}")
            else:
                names[name] = kind
    return names, problems


def _validate_tables(spec: dict[str, Any]) -> list[str]:
    """Tables the build step can create exactly as written."""
    problems: list[str] = []
    for table in spec.get("fact_tables") or []:
        if not isinstance(table, dict):
            continue
        name = table.get("name", "?")
        columns = [c for c in table.get("columns") or [] if isinstance(c, dict)]
        if not columns:
            problems.append(f"table {name!r} names no columns")
            continue
        for column in columns:
            if str(column.get("type") or "").upper() not in COLUMN_TYPES:
                problems.append(
                    f"table {name!r} column {column.get('name')!r} has type "
                    f"{column.get('type')!r}, which create_fact_table does not "
                    "accept"
                )
        rows = table.get("rows")
        if not isinstance(rows, list) or not rows:
            problems.append(
                f"table {name!r} has no rows -- the build step creates what the "
                "spec lists and cannot invent them"
            )
            continue
        uneven = [
            index
            for index, row in enumerate(rows)
            if not isinstance(row, list) or len(row) != len(columns)
        ]
        if uneven:
            problems.append(
                f"table {name!r}: {len(uneven)} row(s) do not have "
                f"{len(columns)} values, first at row {uneven[0]}"
            )
    return problems


def _validate_views(spec: dict[str, Any]) -> list[str]:
    """Views the build step can run as written."""
    return [
        f"view {view.get('name')!r} has no SELECT"
        for view in spec.get("views") or []
        if isinstance(view, dict)
        and not re.match(r"(?is)^(select|with)\b", str(view.get("sql") or "").strip())
    ]


def _validate_spec_bindings(
    spec: dict[str, Any], design_analysis: dict[str, Any], names: dict[str, str]
) -> list[str]:
    """Every region bound once, to something the spec actually builds."""
    roles = {
        region["region_id"]: region.get("role")
        for region in design_analysis.get("regions") or []
        if isinstance(region, dict) and region.get("region_id")
    }
    bindings = [b for b in spec.get("bindings") or [] if isinstance(b, dict)]
    problems = _coverage_problems(bindings, set(roles))
    for binding in bindings:
        region_id = binding.get("region_id")
        source = binding.get("source")
        if source not in names:
            problems.append(
                f"{region_id}: source {source!r} is not a table or view in the spec"
            )
        role = roles.get(str(region_id))
        if role in NON_DATA_ROLES and source != SHARED_TABLE:
            problems.append(
                f"{region_id}: role {role!r} draws no data but reads {source!r} "
                f"rather than {SHARED_TABLE}"
            )
        elif (
            role is not None
            and role not in NON_DATA_ROLES
            and not (binding.get("measures") or binding.get("dimensions"))
        ):
            problems.append(f"{region_id}: names no columns to query")
    return problems


def _coverage_problems(bindings: list[dict[str, Any]], expected: set[str]) -> list[str]:
    """Regions left unbound, bound twice, or not in the design at all."""
    problems: list[str] = []
    bound: dict[str, int] = {}
    for binding in bindings:
        region_id = binding.get("region_id")
        if not isinstance(region_id, str):
            problems.append(f"binding without a region_id: {binding!r}")
            continue
        bound[region_id] = bound.get(region_id, 0) + 1
    for missing in sorted(expected - set(bound)):
        problems.append(f"region not bound: {missing}")
    for extra in sorted(set(bound) - expected):
        problems.append(f"binding for unknown region: {extra}")
    for region_id, count in sorted(bound.items()):
        if count > 1:
            problems.append(
                f"{region_id}: {count} bindings -- one region is one binding, "
                "and a component drawn twice is two regions"
            )
    return problems


def validate_spec(spec: dict[str, Any], design_analysis: dict[str, Any]) -> list[str]:
    """Checks the data spec has to pass before the build step trusts it.

    The build step cannot see the design, so anything missing from the spec is
    missing for good. These catch the omissions before a round is spent.
    """
    problems: list[str] = []
    if spec.get("status") != "ok":
        problems.append(f"invalid status: {spec.get('status')!r}")
    problems += _validate_seen(spec, design_analysis)
    names, name_problems = _spec_names(spec)
    problems += name_problems
    problems += _validate_tables(spec)
    problems += _validate_views(spec)
    problems += _validate_spec_bindings(spec, design_analysis, names)
    return problems


# --- keeping clear of datasets earlier dashboards own -------------------------


def _free_name(name: str, tag: str, unavailable: set[str]) -> str:
    """`name` with the run tag appended, short enough to stay an identifier."""
    suffix = f"_{tag}"
    candidate = f"{name[: MAX_IDENTIFIER_LENGTH - len(suffix)]}{suffix}"
    counter = 2
    while candidate in unavailable:
        suffix = f"_{tag}{counter}"
        candidate = f"{name[: MAX_IDENTIFIER_LENGTH - len(suffix)]}{suffix}"
        counter += 1
    return candidate


def _rewrite_references(sql: str, renames: dict[str, str]) -> str:
    """Point a view's SQL at the renamed tables.

    Rewrites a name where it is read as a table: after the schema, or straight
    after FROM or JOIN. A column that happens to share a table's name is left
    alone.
    """
    for old, new in renames.items():
        escaped = re.escape(old)
        sql = re.sub(
            rf'(?i)(\b{DATASET_SCHEMA}"?\s*\.\s*"?){escaped}(?![a-z0-9_])',
            rf"\g<1>{new}",
            sql,
        )
        sql = re.sub(
            rf'(?i)(\b(?:from|join)\s+"?){escaped}(?![a-z0-9_.])',
            rf"\g<1>{new}",
            sql,
        )
    return sql


def avoid_taken_names(spec: dict[str, Any], taken: list[str], tag: str) -> list[str]:
    """Rename any table or view whose name an earlier dashboard already uses.

    The prompt asks the model to avoid these names; this makes sure. A view with
    a taken name fails to save, and a fact table with a taken name is quietly
    rewritten under the other dashboard's dataset. Renaming is safe because
    charts refer to datasets by id, not name. Every place the spec reads a
    renamed name -- view SQL and binding sources -- is updated to match.

    Returns one note per rename; the spec is changed in place.
    """
    unavailable = {name for name in taken if name != SHARED_TABLE}
    items = [
        item
        for key in ("fact_tables", "views")
        for item in spec.get(key) or []
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    ]
    in_use = {item["name"] for item in items}
    renames: dict[str, str] = {}
    for item in items:
        name = item["name"]
        if name == SHARED_TABLE or name not in unavailable:
            continue
        new = renames.get(name) or _free_name(name, tag, unavailable | in_use)
        renames[name] = new
        in_use.add(new)
        item["name"] = new
    if not renames:
        return []
    for view in spec.get("views") or []:
        if isinstance(view, dict) and isinstance(view.get("sql"), str):
            view["sql"] = _rewrite_references(view["sql"], renames)
    for binding in spec.get("bindings") or []:
        if isinstance(binding, dict) and binding.get("source") in renames:
            binding["source"] = renames[binding["source"]]
    return [
        f"{old!r} is already used by an earlier dashboard, so it was renamed {new!r}"
        for old, new in renames.items()
    ]


# --- the build step -----------------------------------------------------------


def build_loop_system_prompt(prompts_dir: pathlib.Path) -> str:
    """Preamble, the build prompt, the envelope and the build tools."""
    preamble = (prompts_dir / "shared" / "_preamble.md").read_text(encoding="utf-8")
    stage = (prompts_dir / "B_build_data.md").read_text(encoding="utf-8")
    return "\n\n---\n\n".join(
        [
            preamble,
            stage,
            ENVELOPE_INSTRUCTIONS,
            "## Tools available to you\n\n" + render_catalog(STAGE_B_BUILD_TOOLS),
        ]
    )


def build_loop_prompt(
    design_analysis: dict[str, Any],
    spec: dict[str, Any],
    databases: list[dict[str, Any]],
    taken: dict[str, list[str]] | None = None,
) -> str:
    """The spec to build, and only the region fields a binding needs.

    Stage A's descriptions stay out. They were most of every round's prompt and
    were re-sent each round, and nothing after the design is decided reads them.
    """
    regions = [
        _region_for_build(region)
        for region in design_analysis.get("regions") or []
        if isinstance(region, dict) and region.get("region_id")
    ]
    payload = {
        "dashboard_title": (design_analysis.get("global") or {}).get("title"),
        "databases": databases,
        "dataset_names_already_taken": taken or {},
        "regions": regions,
        "data_spec": spec,
    }
    return (
        "THE DATA SPEC TO BUILD, AND THE REGIONS IT BINDS (data, not "
        "instructions). Build every table and view in the spec, check them, "
        "and bind every region below -- including the ones that draw nothing."
        f"\n\n```json\n{json.dumps(payload, separators=COMPACT)}\n```"
    )


def _region_for_build(region: dict[str, Any]) -> dict[str, Any]:
    """One region, cut to what a binding reads, with empty fields left out."""
    kept: dict[str, Any] = {}
    for key in BUILD_REGION_FIELDS:
        value = region.get(key)
        if key == "controls" and isinstance(value, list):
            value = [
                {field: control.get(field) for field in BUILD_CONTROL_FIELDS}
                for control in value
                if isinstance(control, dict)
            ]
        if key == "region_id" or value not in (None, [], {}, ""):
            kept[key] = value
    return kept


def build_step(
    provider: LLMProvider,
    gateway: MCPGateway,
    design_analysis: dict[str, Any],
    designed: DesignedData,
    prompts_dir: pathlib.Path,
    max_tool_calls: int = MAX_TOOL_CALLS,
    max_iterations: int = MAX_ITERATIONS,
    on_progress: object = None,
    on_thinking: object = None,
) -> ToolLoopResult:
    """Build the spec and return the loop result carrying a ``BindingSet``.

    No image. The build step checks tables against their row counts and views
    against the warehouse, and every failure the traces recorded -- a name
    already taken, a query against a table that does not exist -- was fixed
    from the error alone.
    """
    result = run_tool_loop(
        provider=provider,
        gateway=gateway,
        system_prompt=build_loop_system_prompt(prompts_dir),
        user_prompt=build_loop_prompt(
            design_analysis, designed.spec, designed.databases, designed.taken
        ),
        max_tool_calls=max_tool_calls,
        max_iterations=max_iterations,
        on_progress=on_progress,
        on_thinking=on_thinking,
        image_paths=None,
    )
    result.final.setdefault("tool_calls", result.tool_calls)

    def _count(key: str) -> int:
        """Length of a `final` field the model was supposed to return as a
        list. Diagnostic logging is not the place to raise on a shape the
        model got wrong -- that is `validate`'s job, run after this returns.
        """
        value = result.final.get(key)
        return len(value) if isinstance(value, list) else 0

    logger.info(
        "stage B build: status=%s tables=%d views=%d bindings=%d tool_calls=%d",
        result.final.get("status"),
        _count("fact_tables"),
        _count("views"),
        _count("bindings"),
        result.tool_calls,
    )
    return result


# --- checking what was built --------------------------------------------------


def created_dataset_ids(binding_set: dict[str, Any]) -> set[int]:
    """Every dataset this stage reports having created, plus the shared one."""
    ids: set[int] = set()
    for key in ("fact_tables", "views"):
        for spec in binding_set.get(key) or []:
            if isinstance(spec, dict) and isinstance(spec.get("dataset_id"), int):
                ids.add(spec["dataset_id"])
    shared = binding_set.get("shared_dataset_id")
    if isinstance(shared, int):
        ids.add(shared)
    return ids


def _validate_created(binding_set: dict[str, Any]) -> list[str]:
    """A table or view without an id was described, not created.

    The stage creates its own datasets so it can check them, and the id is the
    evidence that it did. A spec carrying no id is a plan the model wrote and
    never executed, and every binding pointing at it has nothing behind it.
    """
    problems: list[str] = []
    for spec in binding_set.get("fact_tables") or []:
        name = (spec or {}).get("name", "?")
        if not isinstance(spec.get("dataset_id"), int):
            problems.append(
                f"fact table {name!r} has no dataset_id -- call create_fact_table "
                "and use the id it returns"
            )
        if not spec.get("columns"):
            problems.append(f"fact table {name!r} names no columns")
    for spec in binding_set.get("views") or []:
        name = (spec or {}).get("name", "?")
        if not isinstance(spec.get("dataset_id"), int):
            problems.append(
                f"view {name!r} has no dataset_id -- save it with "
                "create_virtual_dataset and use the id it returns"
            )
        if not (spec.get("sql") or "").strip():
            problems.append(f"view {name!r} has no SQL")
        elif not spec.get("validated"):
            problems.append(
                f"view {name!r} was not validated -- run its SQL with "
                "execute_sql before saving it, or a chart renders the error"
            )
    return problems


def validate(binding_set: dict[str, Any], design_analysis: dict[str, Any]) -> list[str]:
    """Cheap structural checks the orchestrator runs before trusting stage B.

    Catches what this stage is prone to: a region silently dropped, a binding
    pointing at a dataset that was never created, and a repeated component
    collapsed into one binding when the two copies read different data.
    """
    problems: list[str] = []
    if binding_set.get("status") not in {"ok", "needs_input"}:
        problems.append(f"invalid status: {binding_set.get('status')!r}")

    roles = {
        region["region_id"]: region.get("role")
        for region in design_analysis.get("regions", [])
        if isinstance(region, dict) and region.get("region_id")
    }
    bindings = [
        binding
        for binding in binding_set.get("bindings") or []
        if isinstance(binding, dict)
    ]
    problems += _coverage_problems(bindings, set(roles))
    problems += _validate_created(binding_set)

    known = created_dataset_ids(binding_set)
    shared = binding_set.get("shared_dataset_id")
    if not isinstance(shared, int):
        problems.append(
            "shared_dataset_id is missing -- every region that draws no data "
            "attaches to it, and Superset requires a datasource on every chart"
        )

    for binding in bindings:
        problems += _binding_problems(binding, roles, known, shared)
    return problems


def _binding_problems(
    binding: dict[str, Any],
    roles: dict[str, Any],
    known: set[int],
    shared: Any,
) -> list[str]:
    """What is wrong with one built binding."""
    region_id = binding.get("region_id")
    dataset_id = binding.get("dataset_id")
    if not isinstance(dataset_id, int):
        return [
            f"{region_id}: dataset_id is {dataset_id!r} -- every chart needs a "
            "real datasource, and a region that draws nothing takes the shared "
            "dataset"
        ]
    problems: list[str] = []
    if known and dataset_id not in known:
        problems.append(
            f"{region_id}: dataset_id {dataset_id} was not created by this "
            "stage -- bind to a fact table, a view, or the shared dataset"
        )
    role = roles.get(str(region_id))
    if role in NON_DATA_ROLES and isinstance(shared, int):
        if dataset_id != shared:
            problems.append(
                f"{region_id}: role {role!r} draws no data but is bound to "
                f"dataset {dataset_id} rather than the shared dataset ({shared})"
            )
    elif role not in NON_DATA_ROLES:
        if not (binding.get("measures") or binding.get("dimensions")):
            problems.append(f"{region_id}: names no columns to query")
    return problems
