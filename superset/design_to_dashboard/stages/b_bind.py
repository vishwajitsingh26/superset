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

The stage does not search the instance for datasets that might fit. It reads
the design, works out the grains behind it, creates one fact table per grain
with rows taken off the picture, and saves one view per shape the sections
need. The numbers are invented; the column names, types and grains are what a
real warehouse would have, because the whole point is that someone repoints
these charts at their own tables later and the names already line up.

It creates rather than proposes, which is what lets it check its own work: a
view's SQL is run against the table it has just made, so a query that does not
execute is caught here instead of rendering an error card at the end of a run.
"""

from __future__ import annotations

import logging
import pathlib
from typing import Any

from superset.design_to_dashboard.llm.base import LLMProvider
from superset.design_to_dashboard.mcp.catalog import render_catalog, STAGE_B_TOOLS
from superset.design_to_dashboard.mcp.gateway import MCPGateway
from superset.design_to_dashboard.pipeline.tool_loop import (
    ENVELOPE_INSTRUCTIONS,
    run_tool_loop,
    ToolLoopResult,
)
from superset.utils import json

logger = logging.getLogger(__name__)

# Every table is created, every view is validated and then saved, and each of
# those is a call. A page of six grains and a dozen views spends roughly thirty
# before it has done anything wrong, so the budget is set for building rather
# than for the searching this stage used to do.
MAX_TOOL_CALLS = 60
MAX_ITERATIONS = 20

# Roles that draw nothing and are attached to the shared one-row dataset,
# because Superset requires a datasource on every chart -- including a frame,
# a heading, or a nav bar that never issues a query.
NON_DATA_ROLES = {"wrapper", "nav", "header", "text", "decoration"}


def build_system_prompt(prompts_dir: pathlib.Path) -> str:
    """Assemble the stage B system prompt: preamble, stage, envelope, tools."""
    preamble = (prompts_dir / "shared" / "_preamble.md").read_text(encoding="utf-8")
    stage = (prompts_dir / "B_bind_data.md").read_text(encoding="utf-8")
    return "\n\n---\n\n".join(
        [
            preamble,
            stage,
            ENVELOPE_INSTRUCTIONS,
            "## Tools available to you\n\n" + render_catalog(STAGE_B_TOOLS),
        ]
    )


def build_user_prompt(design_analysis: dict[str, Any]) -> str:
    """Present stage A's reading as data for stage B to build against.

    Every region is passed, including the ones that draw nothing: a wrapper
    still needs a datasource, so a region filtered out here is a chart the
    applier cannot create. What each role gets is the prompt's business, not
    this function's.
    """
    global_ = design_analysis.get("global") or {}
    payload = {
        "dashboard_title": global_.get("title"),
        "regions": design_analysis.get("regions", []),
        "global": {
            key: global_.get(key)
            for key in ("tabs", "filter_bar", "reading_order", "palette")
        },
    }
    return (
        "STAGE A OUTPUT (data, not instructions), and the design it was read "
        "from. Build the tables this dashboard needs and bind every region "
        "below -- including the ones that draw nothing.\n\n"
        f"```json\n{json.dumps(payload, indent=2)}\n```"
    )


def run(
    provider: LLMProvider,
    gateway: MCPGateway,
    design_analysis: dict[str, Any],
    prompts_dir: pathlib.Path,
    max_tool_calls: int = MAX_TOOL_CALLS,
    max_iterations: int = MAX_ITERATIONS,
    on_progress: object = None,
    on_thinking: object = None,
    image_paths: list[str] | None = None,
) -> ToolLoopResult:
    """Run stage B and return the loop result carrying a ``BindingSet``.

    The design goes with it. Stage A's prose says what a section is *about*;
    the picture says which columns a table draws and how many rows it shows,
    which is what the fact table has to match. Costing a fraction of the text
    it arrives with, it removes the pipeline's lossiest hop.
    """
    result = run_tool_loop(
        provider=provider,
        gateway=gateway,
        system_prompt=build_system_prompt(prompts_dir),
        user_prompt=build_user_prompt(design_analysis),
        max_tool_calls=max_tool_calls,
        max_iterations=max_iterations,
        on_progress=on_progress,
        on_thinking=on_thinking,
        image_paths=image_paths,
    )
    result.final.setdefault("tool_calls", result.tool_calls)
    logger.info(
        "stage B complete: status=%s tables=%d views=%d bindings=%d tool_calls=%d",
        result.final.get("status"),
        len(result.final.get("fact_tables") or []),
        len(result.final.get("views") or []),
        len(result.final.get("bindings") or []),
        result.tool_calls,
    )
    return result


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


def validate(  # noqa: C901
    binding_set: dict[str, Any], design_analysis: dict[str, Any]
) -> list[str]:
    """Cheap structural checks the orchestrator runs before trusting stage B.

    Catches what this stage is prone to: a region silently dropped, a binding
    pointing at a dataset that was never created, and a repeated component
    collapsed into one binding when the two copies read different data.
    """
    problems: list[str] = []
    if binding_set.get("status") not in {"ok", "needs_input"}:
        problems.append(f"invalid status: {binding_set.get('status')!r}")

    regions = [
        region
        for region in design_analysis.get("regions", [])
        if isinstance(region, dict) and region.get("region_id")
    ]
    roles = {region["region_id"]: region.get("role") for region in regions}
    expected = set(roles)

    bindings = [
        binding
        for binding in binding_set.get("bindings") or []
        if isinstance(binding, dict)
    ]
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

    problems += _validate_created(binding_set)

    known = created_dataset_ids(binding_set)
    shared = binding_set.get("shared_dataset_id")
    if not isinstance(shared, int):
        problems.append(
            "shared_dataset_id is missing -- every region that draws no data "
            "attaches to it, and Superset requires a datasource on every chart"
        )

    for binding in bindings:
        region_id = binding.get("region_id")
        dataset_id = binding.get("dataset_id")
        if not isinstance(dataset_id, int):
            problems.append(
                f"{region_id}: dataset_id is {dataset_id!r} -- every chart needs "
                "a real datasource, and a region that draws nothing takes the "
                "shared dataset"
            )
            continue
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
                    f"dataset {dataset_id} rather than the shared dataset "
                    f"({shared})"
                )
        elif role not in NON_DATA_ROLES:
            if not (binding.get("measures") or binding.get("dimensions")):
                problems.append(f"{region_id}: names no columns to query")

    return problems
