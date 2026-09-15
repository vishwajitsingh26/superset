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
"""Stage D - configure one chart per worker.

The fan-out stage, and the reason the pipeline is split at all. Each worker
sees exactly one region, one binding, one decision and **one** control-panel
schema, so its context stays around 8k tokens instead of the ~140k a single
agent carrying the whole registry would need.

Workers are independent and run in parallel. Consistency across them comes
from the design-system contract stage C emits, not from shared context.
"""

from __future__ import annotations

import concurrent.futures
import logging
import pathlib
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from superset.design_to_dashboard.llm.base import LLMError, LLMProvider
from superset.design_to_dashboard.pipeline.tool_loop import extract_json
from superset.design_to_dashboard.registry import Registry
from superset.design_to_dashboard.stages.c_resolve import same_as_groups
from superset.design_to_dashboard.stages.e_layout import hosted_refs
from superset.utils import json

logger = logging.getLogger(__name__)

# Decisions that need a chart built. `reuse` already has one, and the rest
# never become charts. A container is not a separate word here: stage F builds
# its plugin, the runner rewrites the decision to `configure`, and it is then
# configured like anything else -- its `children` are what make it compose.
CONFIGURABLE = {"configure"}
MAX_WORKERS = 4
# One repair pass. The problems this stage reports are mechanical, so a second
# attempt with them attached usually clears them; a third rarely adds anything
# a third would not also have to guess at.
MAX_ATTEMPTS = 2


@dataclass
class ChartSpecResult:
    """One worker's output, successful or not."""

    ref: str
    region_id: str
    viz_type: str
    spec: dict[str, Any] | None = None
    error: str | None = None
    cost_usd: float = 0.0
    problems: list[str] = field(default_factory=list)
    # How many passes this chart took. Only set when the last one still had
    # problems, so a reader can tell a first-time pass from an exhausted one.
    attempts: int = 1
    # Why a generated chart would throw if it were created: a required metric
    # its binding cannot fill. It becomes the error unless a live parent names
    # the chart -- and the runner applies it once a parent that stage D could
    # not configure is dropped and the chart is on the grid after all.
    leave_out: str | None = None

    @property
    def ok(self) -> bool:
        return self.spec is not None and not self.problems


def _repair_note(problems: list[str], unfillable: list[str] | None = None) -> str:
    """The previous attempt's faults, to be fixed rather than re-derived.

    A required metric the binding has no measure for is not one of them: no
    answer fills it without inventing a metric, so it is named as settled
    rather than listed as something to fix.
    """
    listed = "\n".join(f"- {problem}" for problem in problems)
    note = (
        "Your previous attempt at this chart failed these checks. They are "
        "mechanical, not matters of taste: fix each one and return the whole "
        "ChartSpec again.\n"
        f"{listed}"
    )
    if unfillable:
        names = ", ".join(f"`{name}`" for name in unfillable)
        note += (
            f"\n\nYour binding has no measure for {names}. Leave it null and "
            'record it in `unmapped` with `confidence: "low"`; do not invent a '
            "metric for it."
        )
    return note


def fallback_dataset(binding_set: dict[str, Any]) -> int | None:
    """The dataset a region with no data of its own is attached to.

    Superset requires a datasource on every chart, including one that draws
    nothing -- a title, a static caption. Stage B builds exactly one dataset
    for this: `shared_no_query`, one row and one column, created per design
    and reported as `shared_dataset_id`.

    This used to guess at the most-bound dataset, because stage B searched for
    existing datasets and left non-drawing regions unbound. Under the current
    contract that guess is actively wrong: stage B binds every wrapper, nav,
    header and text region to the shared dataset, so the shared dataset is
    usually the most-bound one and the guess would attach a real chart to a
    one-column table.
    """
    shared = binding_set.get("shared_dataset_id")
    if isinstance(shared, int) and not isinstance(shared, bool) and shared > 0:
        return shared
    return None


def load_panel(viz_type: str, registry: Registry) -> tuple[str, str]:
    """Return ``(control_panel_path, source)`` for one viz type."""
    return registry.control_panel(viz_type)


def build_system_prompt(
    prompts_dir: pathlib.Path,
    viz_type: str,
    panel_path: str,
    panel: str,
) -> str:
    """Preamble + stage prompt + the control schema for this viz type only."""
    preamble = (prompts_dir / "shared" / "_preamble.md").read_text(encoding="utf-8")
    stage = (prompts_dir / "D_configure_chart.md").read_text(encoding="utf-8")
    return "\n\n---\n\n".join(
        [
            preamble,
            stage,
            (
                f"## Control panel for `{viz_type}`\n\n"
                f"The complete control-panel source for the viz type you are "
                f"configuring is reproduced below (origin: `{panel_path}`). You "
                f"have everything you need here — do not attempt to read files "
                f"or use tools; none are available. Every key you put in "
                f"`params` must be a control defined here (directly, or via the "
                f"shared controls it references). A key that is not defined here is "
                f"silently dropped by Superset and the chart renders wrong with no "
                f"error — so record anything you cannot express in `unmapped` "
                f"instead of inventing a key.\n\n"
                f"```tsx\n{panel}\n```"
            ),
        ]
    )


def _axis_format_note(region: dict[str, Any]) -> str:
    """The exact shape stage A read off each axis or series this region draws.

    Ported from stage F's helper of the same name. Stage F's generated
    plugins get this callout and a validator that checks it was used; stage D
    configures the same axis facts into a stock chart's `params` and had
    neither, so `region.axis_formats` reached this stage only buried inside
    the whole raw region blob -- present, but never named as the thing to
    build the format controls from. A formatter guessed from a control's own
    idea of what a date or number looks like is how a date axis prints
    `0NaN`, or a stock currency chart shows `8.92k` for a value that is
    already in millions -- stage A already looked at the picture; this is
    what it read, not a shape to infer again.
    """
    formats = [f for f in region.get("axis_formats") or [] if isinstance(f, dict)]
    if not formats:
        return ""
    listed = "\n".join(
        f"- {f.get('axis', '?')} axis: {f.get('kind', '?')}"
        f", pattern `{f.get('pattern')}`"
        + (f", prefix `{f['prefix']}`" if f.get("prefix") else "")
        + (f", suffix `{f['suffix']}`" if f.get("suffix") else "")
        for f in formats
    )
    return (
        "\n\n## What each axis actually is\n\n"
        "Stage A read these off the picture -- the real kind and pattern "
        "behind every axis or series this region draws, not a guess your "
        "format controls should make on their own. Set the format control "
        "that corresponds to each entry (`number_format`, `y_axis_format`, "
        "`x_axis_format`, `x_axis_time_format`, `date_format`, `time_format`, "
        "or `currency_format` -- whichever your schema exposes) from its "
        "`pattern`, not from a default. This is checked: a chart configured "
        "against a region that lists axis formats but whose params set none "
        "of them is rejected.\n\n"
        f"{listed}"
    )


def build_user_prompt(
    region: dict[str, Any],
    binding: dict[str, Any],
    decision: dict[str, Any],
    design_system: dict[str, Any],
) -> str:
    """Everything one worker needs, and nothing about any other region."""
    payload = {
        "region": region,
        "binding": binding,
        "decision": decision,
        "design_system": design_system,
    }
    extra = ""
    if binding.get("attached_only"):
        # Otherwise the binding reads as a dataset chosen to be queried, and
        # the model writes metrics and groupbys for a region that has none.
        extra += (
            "\n\nThis region reads no data of its own -- stage B bound nothing "
            f"to it. Dataset {binding.get('dataset_id')} is supplied only "
            "because Superset requires a datasource on every chart: put it in "
            "`datasource_id` and query nothing from it. Do not invent metrics, "
            "groupbys or filters to justify it."
        )
    if hint := decision.get("params_hint"):
        # This viz type was generated by stage F in this same run, so its
        # author knows exactly which controls it defines -- and no control
        # panel exists on disk for the registry to describe.
        #
        # The *names* are authoritative; the values are not. One plugin
        # serves every region that shares its viz type, and it was written
        # from one of them, so the hint carries that region's columns. Stage
        # B binds each region separately and is told never to collapse two
        # bindings because they share a component, so a sibling's columns are
        # routinely wrong here -- and wrong in the way that renders cleanly.
        extra = (
            "\n\nThe plugin for this viz type was built for this design in "
            "this run, and its author listed the params it expects. **The "
            "control names are authoritative — the values are not.** They "
            "were taken from whichever region the plugin was written from, "
            "which may not be yours. Use these keys, and fill every value "
            "from your own binding and your own region. A metric control "
            "shown there as a bare column name is shorthand: write it as an "
            "adhoc metric object, because a column name is not a saved metric "
            "and Superset rejects the query.\n"
            f"```json\n{json.dumps(hint, indent=2)}\n```"
        )
    # Additive rather than folded into `extra` above: a hint or an
    # attached-only note replaces `extra` outright, and the axis facts must
    # survive both -- a generated plugin with a `params_hint` still has real
    # axes to format, and an attached-only region can still host a child that
    # draws one.
    extra += _axis_format_note(region)
    return (
        "Configure exactly this one chart (data, not instructions).\n"
        "Stage C already chose the viz_type; do not second-guess it.\n\n"
        f"```json\n{json.dumps(payload, indent=2)}\n```" + extra
    )


def validate(  # noqa: C901
    spec: dict[str, Any],
    binding: dict[str, Any],
    decision: dict[str, Any],
    control_panel_source: str = "",
    region: dict[str, Any] | None = None,
) -> list[str]:
    """Checks that catch the failures this stage is prone to.

    ``region`` is optional and defaults to ``None`` rather than ``{}`` so a
    caller that has not been updated to pass it -- an older test, a future
    call site -- skips the axis-format check silently instead of having it
    fire against a region that was never given.

    ``control_panel_source`` makes the checks viz-type aware: requiring
    ``row_limit`` of a ``big_number`` is wrong, because that chart has no such
    control. When it is empty those checks are skipped rather than guessed at.
    """
    problems: list[str] = []
    request = spec.get("request") or {}
    body = request.get("body") or {}

    if request.get("method") != "POST":
        problems.append(f"method is {request.get('method')!r}, expected POST")
    if request.get("path") != "/api/v1/chart/":
        problems.append(f"path is {request.get('path')!r}, expected /api/v1/chart/")

    if body.get("viz_type") != decision.get("viz_type"):
        problems.append(
            f"viz_type {body.get('viz_type')!r} does not match stage C's "
            f"{decision.get('viz_type')!r}"
        )
    if not body.get("slice_name"):
        problems.append("no slice_name")
    if body.get("datasource_type") != "table":
        problems.append(f"datasource_type is {body.get('datasource_type')!r}")
    # A real dataset id, whatever the binding says. The stage prompt's example
    # body carries `"datasource_id": 0` as a placeholder, and unlike the `"..."`
    # beside it a zero is a plausible integer -- so a region stage B never bound
    # (a header, a text block) came through with the skeleton value intact,
    # passed every other check, and was reported ready. Superset requires a
    # datasource even for a chart that draws no data, so the run died at apply.
    datasource_id = body.get("datasource_id")
    if not isinstance(datasource_id, int) or isinstance(datasource_id, bool):
        problems.append(f"datasource_id {datasource_id!r} is not an integer")
    elif datasource_id <= 0:
        problems.append(
            f"datasource_id is {datasource_id}, which is not a dataset. Use the "
            "id from this region's binding."
        )
    # Beyond being real, it has to be the one the binding named. Only checkable
    # when the dataset already exists: a binding with no `dataset_id` is waiting
    # on a dataset this run creates, so stage D's id is a placeholder the
    # applier overwrites -- verified there, and in `b_bind.validate`, rather
    # than reported as a fault of this chart.
    elif binding.get("dataset_id") and datasource_id != binding["dataset_id"]:
        problems.append(
            f"datasource_id {datasource_id!r} does not match the "
            f"binding's {binding['dataset_id']!r}"
        )

    # The single most common failure against Superset's API.
    params = body.get("params")
    if not isinstance(params, str):
        problems.append("params must be a JSON-encoded string, not an object")
    else:
        try:
            decoded_from_string = json.loads(params)
        except ValueError:
            problems.append("params is not valid JSON")
            decoded_from_string = None
        decoded = spec.get("params_decoded")
        if not isinstance(decoded, dict):
            problems.append("params_decoded missing or not an object")
        elif decoded_from_string is not None and decoded_from_string != decoded:
            problems.append("params and params_decoded disagree")

    decoded = spec.get("params_decoded") or {}

    # Only require a control the viz type actually has.
    for control in ("row_limit", "adhoc_filters"):
        if control_panel_source and control not in control_panel_source:
            continue
        if control_panel_source and control not in decoded:
            problems.append(f"{control} is a control of this viz type but is unset")

    # Column references, checked only where columns actually live. Scanning
    # every string produced false positives on generated ids such as
    # `filterOptionName` and on format tokens such as `smart_date`.
    allowed: set[str] = set()
    for entry in (binding.get("dimensions") or []) + (binding.get("measures") or []):
        allowed |= _names_of(entry)
    for clause in binding.get("filters") or []:
        if isinstance(clause, dict) and clause.get("col"):
            allowed.add(clause["col"])
    if binding.get("time_column"):
        allowed.add(binding["time_column"])

    if allowed:
        for column in _referenced_columns(decoded):
            if column not in allowed:
                problems.append(
                    f"references column {column!r}, which the binding does not name"
                )

    # A time grain on a non-temporal column makes Superset emit
    # DATE_TRUNC('YEAR', <number>), which the database rejects. Stage B decides
    # whether a grain is valid; stage D must not override that.
    if not binding.get("time_grain"):
        for where, grain in _time_grains(spec, decoded):
            problems.append(
                f"{where} sets a time grain ({grain!r}) but the binding set "
                f"none — column {binding.get('time_column')!r} is not a real "
                f"temporal type, so this emits DATE_TRUNC against a number and "
                f"the chart fails to render"
            )

    if children := decision.get("children") or []:
        blob = json.dumps(decoded)
        for child in children:
            if f"__REF__:{child}" not in blob:
                problems.append(
                    f"child chart {child!r} is not referenced as __REF__:{child}"
                )

    problems.extend(_unapplied_filters(binding, decoded))
    problems.extend(_metric_problems(decoded, binding, control_panel_source))
    problems.extend(_axis_format_problems(region, decoded))

    return problems


# Superset's shared metric pickers, and whether each refuses an empty value
# by default (`validateNonEmpty`). A stock control panel usually reaches them
# through a section it imports rather than by name, so its source cannot say
# they exist; the key appearing in `params` is then the only evidence, and
# these defaults are what it takes.
SHARED_METRIC_CONTROLS: dict[str, bool] = {
    "metric": True,
    "metrics": True,
    "metric_2": True,
    "x": True,
    "y": True,
    "size": True,
    "percent_metrics": False,
    "secondary_metric": False,
    "timeseries_limit_metric": False,
    "series_limit_metric": False,
    "tooltip_metrics": False,
}
MULTI_METRIC_CONTROLS = {"metrics", "percent_metrics", "tooltip_metrics"}

# What a control's own config says about it, when the panel defines it by
# name. The `dnd*` names are the shared configs a panel may spread directly
# instead of going through `sharedControls`.
_METRIC_MARKERS = re.compile(
    r"sharedControls(?:\.|\[\s*['\"])(?P<shared>\w+)"
    r"|type:\s*['\"](?:MetricsControl|DndMetricSelect)['\"]"
    r"|\b(?P<dnd>dnd\w*(?:Metric|SortBy|Size|X|Y)\w*Control)\b"
)
_REQUIRED_DND = {
    "dndAdhocMetricsControl": True,
    "dndAdhocMetricControl": True,
    "dndAdhocMetricControl2": True,
    "dndSizeControl": True,
    "dndXControl": True,
    "dndYControl": True,
}
_CONTROL_NAME = re.compile(r"\bname:\s*['\"](\w+)['\"]")
_BLOCK_COMMENT = re.compile(r"/\*[\s\S]*?\*/")
_LINE_COMMENT = re.compile(r"(?<![:/])//[^\n]*")

# Every dataset Superset creates gets this one saved metric, and stage D is
# told about no other: a binding names columns, not the dataset's metrics.
DEFAULT_SAVED_METRICS = {"count"}
ADHOC_AGGREGATES = {"AVG", "COUNT", "COUNT_DISTINCT", "MAX", "MIN", "SUM"}


@dataclass(frozen=True)
class MetricControl:
    """A metric picker a control panel defines, as far as its source says."""

    name: str
    required: bool
    multi: bool
    # Defined by name in the panel's own source, rather than inferred from a
    # shared control's key turning up in `params`.
    declared: bool


def _enclosing_object(source: str, index: int) -> str:
    """The `{ ... }` literal around `index`, braces counted, strings ignored.

    Good enough for a control panel, whose object literals are what nests; a
    brace inside a description string is balanced in every panel seen.
    """
    depth, start = 0, 0
    for position in range(index, -1, -1):
        char = source[position]
        if char == "}":
            depth += 1
        elif char == "{":
            if depth == 0:
                start = position
                break
            depth -= 1
    depth = 0
    for position in range(start, len(source)):
        char = source[position]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[start : position + 1]
    return source[start:]


# A control configured from a variable (`config: percentMetrics`), and the
# declaration that variable is read from.
_CONFIG_REFERENCE = re.compile(r"config:\s*([A-Za-z_]\w*)\s*[,}]")
# A local function a panel builds controls with: `const metricControl = (name,
# label) => ({ ... })`, or `function metricControl(name) { ... }`.
_FACTORY_DEFINITION = re.compile(
    r"\b(?:const|let|var)\s+(?P<arrow>[A-Za-z_]\w*)\s*=\s*"
    r"(?:\([^)]*\)|[A-Za-z_]\w*)[^=;{]*=>"
    r"|\bfunction\s+(?P<function>[A-Za-z_]\w*)\s*\([^)]*\)[^{;]*"
)


def _object_after(source: str, index: int) -> str | None:
    """The `{ ... }` literal starting at `index`, past whitespace and `(`."""
    position = index
    while position < len(source) and (
        source[position].isspace() or source[position] == "("
    ):
        position += 1
    if position < len(source) and source[position] == "{":
        return _enclosing_object(source, position + 1)
    return None


def _declaration(source: str, identifier: str) -> str | None:
    """The object literal `const <identifier> = { ... }` holds, if there is one."""
    if match := re.search(
        rf"\b(?:const|let|var)\s+{re.escape(identifier)}\b[^=;]*=", source
    ):
        return _object_after(source, match.end())
    return None


def _call_arguments(source: str, index: int) -> str:
    """What a call passes, from `index` inside its parentheses to their close."""
    depth = 1
    for position in range(index, len(source)):
        if source[position] == "(":
            depth += 1
        elif source[position] == ")":
            depth -= 1
            if depth == 0:
                return source[index:position]
    return source[index:]


def _metric_control(name: str, block: str) -> MetricControl | None:  # noqa: C901
    """`name` as a metric control, from the source that configures it, or None."""
    markers = list(_METRIC_MARKERS.finditer(block))
    shared = [m.group("shared") for m in markers if m.group("shared")]
    dnd = [m.group("dnd") for m in markers if m.group("dnd")]
    # A shared control named with only an `override`, or configured from a
    # variable defined elsewhere in the file (`config: percentMetrics`).
    by_name = name in SHARED_METRIC_CONTROLS and (
        "config:" not in block or _CONFIG_REFERENCE.search(block) is not None
    )
    if not markers and not by_name:
        return None
    if shared and not any(s in SHARED_METRIC_CONTROLS for s in shared) and not dnd:
        # A spread of some other shared control -- `groupby`, `row_limit`.
        if not re.search(r"MetricsControl|DndMetricSelect", block):
            return None
    if validators := re.search(r"validators:\s*\[([^\]]*)\]", block):
        required = "validateNonEmpty" in validators.group(1)
    elif spread := next((s for s in shared if s in SHARED_METRIC_CONTROLS), None):
        required = SHARED_METRIC_CONTROLS[spread]
    elif dnd:
        required = any(_REQUIRED_DND.get(d, False) for d in dnd)
    else:
        required = SHARED_METRIC_CONTROLS.get(name, False)
    # A control shown only in some modes is legitimately empty in others.
    if re.search(r"\bvisibility\s*:", block):
        required = False
    if multi_flag := re.search(r"\bmulti:\s*(true|false)", block):
        multi = multi_flag.group(1) == "true"
    else:
        multi = name in MULTI_METRIC_CONTROLS or any(
            s in MULTI_METRIC_CONTROLS for s in shared
        )
        multi = multi or "dndAdhocMetricsControl" in dnd
    return MetricControl(name, required, multi, declared=True)


def _metric_factories(source: str) -> dict[str, str]:
    """Local functions whose body builds a metric control, and those bodies."""
    factories: dict[str, str] = {}
    for match in _FACTORY_DEFINITION.finditer(source):
        name = match.group("arrow") or match.group("function")
        body = _object_after(source, match.end())
        if body and _metric_control("", body) is not None:
            factories[name] = body
    return factories


def metric_controls(control_panel_source: str) -> dict[str, MetricControl]:
    """The metric controls a control panel defines, keyed by control name.

    Read from the source because that is all this stage has: a generated
    plugin's panel exists nowhere else, and it is the file whose `validators`
    decide whether the plugin may be handed an empty metric. Shared metric
    controls referenced only through an imported section are not found here;
    `SHARED_METRIC_CONTROLS` covers those by key.

    A panel is not always a list of literals. A control configured from a
    variable is read through that variable's declaration, and one built by a
    local helper -- `metricControl('awsMetric', 'AWS')` -- through the helper's
    body. Missing either, every check on those controls silently did not run:
    bare column names and empty required metrics went out unflagged.
    """
    source = _LINE_COMMENT.sub("", _BLOCK_COMMENT.sub("", control_panel_source or ""))
    found: dict[str, MetricControl] = {}
    for match in _CONTROL_NAME.finditer(source):
        name = match.group(1)
        block = _enclosing_object(source, match.start())
        if (reference := _CONFIG_REFERENCE.search(block)) and (
            declared := _declaration(source, reference.group(1))
        ):
            block = f"{block}\n{declared}"
        if control := _metric_control(name, block):
            found[name] = control
    for factory, body in _metric_factories(source).items():
        for call in re.finditer(
            rf"(?<![\w.]){re.escape(factory)}\(\s*['\"](\w+)['\"]", source
        ):
            name = call.group(1)
            if name in found:
                continue
            # The call's own arguments first, so an override passed to the
            # helper (`{ validators: [] }`) outranks the helper's default.
            block = f"{_call_arguments(source, call.end())}\n{body}"
            if control := _metric_control(name, block):
                found[name] = control
    return found


def unfillable_metrics(
    decoded: Any, binding: dict[str, Any], control_panel_source: str
) -> list[str]:
    """Required metric controls left empty that the binding has no measure for.

    The plugin was written for a region reading more measures than this one.
    Asking stage D again cannot help -- it is told not to invent a metric, and
    obeying is what left the control empty -- so the answer is decided here.
    """
    if not isinstance(decoded, dict):
        return []
    required = [
        name
        for name, control in metric_controls(control_panel_source).items()
        if control.required
    ]
    empty = [name for name in required if _is_empty(decoded.get(name))]
    measures = len(binding.get("measures") or [])
    return empty if empty and measures < len(required) else []


def _is_empty(value: Any) -> bool:
    return value is None or value == "" or value == [] or value == {}


def _adhoc_example(column: str) -> str:
    return json.dumps(
        {
            "expressionType": "SIMPLE",
            "column": {"column_name": column},
            "aggregate": "SUM",
            "label": "<what the design calls it>",
        }
    )


_SQL_EXAMPLE = json.dumps(
    {
        "expressionType": "SQL",
        "sqlExpression": "SUM(<column>) / COUNT(*)",
        "label": "<what the design calls it>",
    }
)


def _one_metric_problem(  # noqa: C901
    where: str, value: Any, saved: set[str], columns: set[str]
) -> str | None:
    """What is wrong with one metric value, phrased as the fix, or None."""
    if isinstance(value, str):
        if value in saved:
            return None
        if value in columns:
            fix = (
                f"write it as an adhoc metric over that column: {_adhoc_example(value)}"
            )
        else:
            fix = (
                f"write it as an adhoc metric: {_adhoc_example('<column>')} for a "
                f"column in your binding, or {_SQL_EXAMPLE} for an expression"
            )
        return (
            f"`{where}` is the bare string {value!r}, which is not a saved metric. "
            "A metric control takes a saved metric's name or an adhoc metric "
            "object, and a column name is neither: Superset rejects the chart's "
            "query with a 400. The only saved metric this stage can rely on is "
            f"`count`, which every dataset gets -- so {fix}, choosing the "
            "aggregate the region actually reads (SUM, AVG, MAX, ...)."
        )
    if not isinstance(value, dict):
        return (
            f"`{where}` is {value!r}, which is neither a saved metric name nor an "
            f"adhoc metric object such as {_adhoc_example('<column>')}"
        )
    kind = value.get("expressionType")
    missing: list[str] = []
    if kind == "SIMPLE":
        column = value.get("column")
        if not (isinstance(column, dict) and column.get("column_name")):
            missing.append('`column` as {"column_name": "<column>"}')
        if str(value.get("aggregate") or "").upper() not in ADHOC_AGGREGATES:
            missing.append(
                f"`aggregate` (one of {', '.join(sorted(ADHOC_AGGREGATES))})"
            )
    elif kind == "SQL":
        if not str(value.get("sqlExpression") or "").strip():
            missing.append("`sqlExpression`")
    else:
        missing.append('`expressionType` ("SIMPLE" or "SQL")')
    if not str(value.get("label") or "").strip():
        missing.append("`label`")
    if not missing:
        return None
    return (
        f"`{where}` is an adhoc metric missing {', '.join(missing)}. A SIMPLE "
        f"metric is {_adhoc_example('<column>')}; a SQL metric is {_SQL_EXAMPLE}."
    )


def _metric_problems(  # noqa: C901
    decoded: dict[str, Any], binding: dict[str, Any], control_panel_source: str
) -> list[str]:
    """Metric controls holding something Superset or the plugin cannot use.

    Two failures, both invisible to every other check. A column name in a
    metric control reads as a saved metric that does not exist, and the chart
    answers with a 400. An empty metric in a control the plugin reads
    unconditionally -- typically one written for a sibling region with more
    measures than this one -- throws inside the plugin, and a thrown error in
    one chart is an overlay across the whole dashboard.
    """
    controls = metric_controls(control_panel_source)
    # A panel may define its own `x` or `size` as a number or a text: a key it
    # declares and `metric_controls` did not recognise is not a metric.
    declared = set(
        _CONTROL_NAME.findall(_BLOCK_COMMENT.sub("", control_panel_source or ""))
    )
    for name, required in SHARED_METRIC_CONTROLS.items():
        if name not in controls and name not in declared and name in decoded:
            controls[name] = MetricControl(
                name, required, name in MULTI_METRIC_CONTROLS, declared=False
            )

    saved = set(DEFAULT_SAVED_METRICS)
    columns: set[str] = set()
    for entry in binding.get("measures") or []:
        if isinstance(entry, dict) and isinstance(entry.get("metric_name"), str):
            saved.add(entry["metric_name"])
    for entry in (binding.get("dimensions") or []) + (binding.get("measures") or []):
        columns |= _names_of(entry)
    if binding.get("time_column"):
        columns.add(binding["time_column"])

    problems: list[str] = []
    for name, control in sorted(controls.items()):
        if name not in decoded:
            # Only a control the panel names itself is known to exist; a
            # shared key absent from params may belong to a section this
            # viz type does not have.
            if control.required and control.declared:
                problems.append(_unset_required_problem(name))
            continue
        value = decoded[name]
        if _is_empty(value):
            if control.required:
                problems.append(_empty_required_problem(name, value))
            elif value == "":
                problems.append(
                    f"`{name}` is an empty string. Leave an optional metric "
                    "control `null` when this region draws no such value -- an "
                    "empty string is sent to the query as a metric named ''."
                )
            continue
        if isinstance(value, list):
            if not control.multi:
                problems.append(
                    f"`{name}` takes one metric, not a list; set it to the "
                    "single metric object itself"
                )
                continue
            for index, item in enumerate(value):
                if problem := _one_metric_problem(
                    f"{name}[{index}]", item, saved, columns
                ):
                    problems.append(problem)
            continue
        if problem := _one_metric_problem(name, value, saved, columns):
            problems.append(problem)
    return problems


def _unset_required_problem(name: str) -> str:
    return (
        f"`{name}` is a required metric control of this viz type "
        "(validateNonEmpty) but is unset. The plugin reads it to "
        "draw, so an absent metric fails the query or throws. Set "
        "it to an adhoc metric over a measure in your binding."
    )


def _empty_required_problem(name: str, value: Any) -> str:
    return (
        f"`{name}` is {value!r}, but the control panel requires a "
        "metric here (validateNonEmpty) and the plugin reads it "
        "unconditionally: an empty metric fails the query or "
        "crashes the page. Set it to an adhoc metric over a measure "
        "in your binding. If your binding has no measure for it, "
        "the plugin was written for a region reading more measures "
        "than yours -- say so in `unmapped` with confidence low; "
        "do not invent a metric."
    )


def _unfillable_problems(decoded: Any, unfillable: list[str]) -> set[str]:
    """The exact problem texts `_metric_problems` reports for `unfillable`."""
    values = decoded if isinstance(decoded, dict) else {}
    return {
        text
        for name in unfillable
        for text in (
            _unset_required_problem(name),
            _empty_required_problem(name, values.get(name)),
        )
    }


# Every param name across Superset's stock control panels that a `number` or
# `date` axis_formats entry could plausibly be expressed through. Not every
# viz type has all of these -- `control_panel_source` is not threaded through
# this check the way it is for `row_limit`/`adhoc_filters`, because the point
# is narrower: not "does this control exist" but "was any format control
# touched at all", which is checkable without the panel.
NUMBER_FORMAT_PARAMS = ("number_format", "y_axis_format", "currency_format")
DATE_FORMAT_PARAMS = (
    "date_format",
    "x_axis_format",
    "x_axis_time_format",
    "time_format",
)

# A suffix drawn beside an axis's values that means the underlying number is
# already scaled -- `global_sales` summing to `8920.13` and drawn as
# `8,920.4M`. D3's SI notation (`,.2s`/`,.3s`) or Superset's `SMART_NUMBER`
# read that as a raw value and print `8.92k`, wrong by three orders of
# magnitude -- the exact trap `D_configure_chart.md` names in its own
# magnitude-suffix step.
_ALREADY_SCALED_SUFFIXES = {"k", "m", "b", "t"}
_SI_FORMAT_MARKERS = (",.1s", ",.2s", ",.3s", ",.4s", "smart_number")


def _axis_format_problems(
    region: dict[str, Any] | None, decoded: dict[str, Any]
) -> list[str]:
    """Params that ignore, or contradict, the axis facts stage A read off.

    Ported from stage F's equivalent, which fails a scaffolded plugin whose
    own `review_notes` never mention "axis" once `region.axis_formats` is
    non-empty -- proof the fact was read, not proof the formatter is right.
    Stage D produces real `params` rather than free text, so the check is
    adapted to that shape: the clearest, lowest-false-positive version is that
    *some* format control was set at all, and -- where the pattern is cheap to
    read mechanically -- that an SI/`SMART_NUMBER` format was not chosen for
    an axis whose own suffix says the value is already scaled.
    """
    raw_formats = (region or {}).get("axis_formats") or []
    formats = [f for f in raw_formats if isinstance(f, dict)]
    relevant = [f for f in formats if f.get("kind") in ("number", "date")]
    if not relevant:
        return []

    problems: list[str] = []
    touched = any(
        decoded.get(name) for name in (*NUMBER_FORMAT_PARAMS, *DATE_FORMAT_PARAMS)
    )
    if not touched:
        described = "; ".join(
            f"{f.get('axis', '?')} axis ({f.get('kind')}, pattern `{f.get('pattern')}`)"
            for f in relevant
        )
        all_params = ", ".join(NUMBER_FORMAT_PARAMS + DATE_FORMAT_PARAMS)
        problems.append(
            f"region.axis_formats lists {len(relevant)} axis/series format(s) "
            f"that stage A read off the design ({described}), but params sets "
            f"none of the format controls this stage can check ({all_params}). "
            "A formatter left at its default is how a date axis prints "
            "`0NaN`, or a number prints with the wrong decimals -- set the "
            "control this viz type exposes from the pattern named above."
        )

    for entry in relevant:
        if entry.get("kind") != "number":
            continue
        suffix = str(entry.get("suffix") or "").strip().lower()
        if suffix not in _ALREADY_SCALED_SUFFIXES:
            continue
        for name in NUMBER_FORMAT_PARAMS:
            value = decoded.get(name)
            if isinstance(value, str) and any(
                marker in value.lower() for marker in _SI_FORMAT_MARKERS
            ):
                problems.append(
                    f"`{name}` is {value!r}, an SI/SMART_NUMBER format, but "
                    f"the {entry.get('axis', '?')} axis's own suffix "
                    f"(`{entry['suffix']}`) says the value is already "
                    "scaled -- SI notation reapplies the scaling and prints "
                    "a number wrong by orders of magnitude (`8.92k` for a "
                    "value already in millions). Use a plain format such as "
                    "`,.1f` and keep the unit in the label or subheader."
                )

    return problems


def _unapplied_filters(binding: dict[str, Any], decoded: dict[str, Any]) -> list[str]:
    """Binding filters that never made it into `adhoc_filters`.

    Stage B minimises views deliberately: one view over all three providers,
    and each card's binding carries the clause that scopes it to its own row.
    Nothing made stage D apply them, so three provider cards configured off
    one view all rendered all three providers -- a chart that renders cleanly
    and is simply wrong, which no other check can see.

    Matched on the column alone. The operator and value have legitimate
    spellings stage D may pick (`==` against `IN` with one entry, a number as
    a string), and rejecting those would fail correct charts; a clause on the
    right column is the part that cannot be got right by accident.
    """
    required = {
        clause["col"]
        for clause in binding.get("filters") or []
        if isinstance(clause, dict) and clause.get("col")
    }
    if not required:
        return []
    applied: set[str] = set()
    for clause in decoded.get("adhoc_filters") or []:
        if not isinstance(clause, dict):
            continue
        if subject := clause.get("subject"):
            applied.add(subject)
        # A SQL clause names its column inside the expression rather than in
        # a field, so it is credited when the column appears in the text.
        if expression := clause.get("sqlExpression"):
            applied |= {column for column in required if column in str(expression)}
    # `extra_form_data` is the other place a scope can legitimately live.
    for clause in (decoded.get("extra_form_data") or {}).get("filters") or []:
        if isinstance(clause, dict) and clause.get("col"):
            applied.add(clause["col"])
    return [
        f"the binding filters on {column!r} and nothing in params applies it. "
        f"The dataset is shared with other regions, so without this clause "
        f"the chart renders every other region's rows too."
        for column in sorted(required - applied)
    ]


# Params keys that actually carry column names. Scanning every string in
# `params` produced false positives on generated ids (`filterOptionName`) and
# on format tokens (`smart_date`), so the check is scoped to these.
COLUMN_FIELDS = (
    "groupby",
    "columns",
    "all_columns",
    "series",
    "series_columns",
    "entity",
    "x_axis",
    "granularity_sqla",
    "metric",
    "metrics",
)


def _names_of(entry: Any) -> set[str]:
    """Names a binding entry makes available.

    A dimension or measure is either a plain column/metric name, or — when
    stage B marked the region ``derivable`` — an adhoc definition object such
    as ``{"type": "adhoc", "label": ..., "column": ..., "aggregate": ...}``.
    Both shapes are legitimate, so both contribute names.
    """
    if isinstance(entry, str):
        return {entry}
    if isinstance(entry, dict):
        names = set()
        for key in ("label", "column", "column_name", "metric_name", "name"):
            value = entry.get(key)
            if isinstance(value, str):
                names.add(value)
            elif isinstance(value, dict) and isinstance(value.get("column_name"), str):
                names.add(value["column_name"])
        return names
    return set()


def _time_grains(
    spec: dict[str, Any], decoded: dict[str, Any]
) -> list[tuple[str, str]]:
    """Every place a time grain can hide.

    `params.time_grain_sqla` is the obvious one, but a grain is also carried on
    an adhoc x-axis column inside the query context
    (`queries[].columns[].timeGrain`) -- which is where a real failure came
    from, invisible to a params-only check.
    """
    found: list[tuple[str, str]] = []
    if grain := decoded.get("time_grain_sqla"):
        found.append(("params.time_grain_sqla", grain))

    raw = (spec.get("request") or {}).get("body", {}).get("query_context")
    context = spec.get("query_context_decoded")
    if isinstance(raw, str) and raw.strip() and not isinstance(context, dict):
        try:
            context = json.loads(raw)
        except ValueError:
            context = None
    if isinstance(context, dict):
        for index, query in enumerate(context.get("queries") or []):
            for column in query.get("columns") or []:
                if isinstance(column, dict) and column.get("timeGrain"):
                    found.append(
                        (
                            f"query_context.queries[{index}].columns[].timeGrain",
                            column["timeGrain"],
                        )
                    )
    return found


def _referenced_columns(params: dict[str, Any]) -> set[str]:  # noqa: C901
    """Column and metric names referenced by ``params``."""
    found: set[str] = set()

    def add(value: Any) -> None:
        if isinstance(value, str):
            found.add(value)
        elif isinstance(value, dict):
            # Simple adhoc metric: {"column": {"column_name": ...}, ...}
            column = value.get("column")
            if isinstance(column, dict) and column.get("column_name"):
                found.add(column["column_name"])
            if value.get("column_name"):
                found.add(value["column_name"])
            # A SQL adhoc metric carries an expression, not a column name.
        elif isinstance(value, list):
            for item in value:
                add(item)

    for column_field in COLUMN_FIELDS:
        if column_field in params:
            add(params[column_field])

    for clause in params.get("adhoc_filters") or []:
        if not isinstance(clause, dict):
            continue
        if clause.get("expressionType") == "SIMPLE" and clause.get("subject"):
            found.add(clause["subject"])

    return found


def _group_reference_note(reference: dict[str, Any]) -> str:
    """The leader's finished spec, for a `same_as` group's remaining members.

    Stage C already forces a `same_as` group onto one viz_type
    (`_component_groups_split`, `_shared_plugin_shapes`), so every member
    shares one control schema. That is what makes a shared reference useful
    rather than misleading, the same reasoning `decision.get("params_hint")`
    already relies on for a stage-F-built plugin: the control *names* are
    authoritative because the schema is shared, even though the *values* were
    read off one particular member.

    Unlike `params_hint`, this is not "the plugin author's example" -- it is a
    sibling region in this same run, already configured, and the fields named
    below are not a suggestion: a real run configured four copies of one KPI
    tile in isolation and got `SUM` on one, `MAX` on another, one `row_limit`
    of 1000 against a sibling's 1, and a caption colour set on one of two
    otherwise-identical placeholder tiles and left blank on the other. None of
    that was visible to any single chart's own checks -- each one, taken
    alone, was internally consistent.
    """
    decoded = reference.get("params_decoded") or {}
    return (
        "\n\n## Part of a `same_as` group -- match your sibling's shared choices\n\n"
        "Stage A read this region as the same repeated component as "
        f"`{reference.get('ref')}`, configured just before this call. "
        "The two must agree on everything that is "
        "a property of the *component* rather than of the data either copy happens "
        "to be scoped to: the aggregate function every metric control uses, "
        "`row_limit`, and any colour, palette, font-size or number/date format "
        "field. Copy those verbatim from the reference below instead of deciding "
        "them again.\n\n"
        "What must still be your own: `adhoc_filters` (and any other scoping "
        "clause) drawn from **your own** binding, `datasource_id`, and any label "
        'or caption text that names this region\'s own slice of the data ("AWS" '
        'vs "GCP") -- that difference is the entire reason these are separate '
        "regions rather than one chart. A mechanical check compares your finished "
        "`params_decoded` against your sibling's afterwards and rejects the pair "
        "if a shared field like these has drifted.\n\n"
        f"Reference `params_decoded` from `{reference.get('ref')}`:\n"
        f"```json\n{json.dumps(decoded, indent=2)}\n```"
    )


def run_one(
    provider: LLMProvider,
    region: dict[str, Any],
    binding: dict[str, Any],
    decision: dict[str, Any],
    design_system: dict[str, Any],
    prompts_dir: pathlib.Path,
    registry: Registry,
    attempts: int = MAX_ATTEMPTS,
    hosted: bool = False,
    group_reference: dict[str, Any] | None = None,
) -> ChartSpecResult:
    """Configure a single chart. Never raises - failures are reported.

    A chart that fails validation is asked again with what was wrong with it.
    The problems are mechanical -- a key that is not a control, a column the
    binding does not name, params that disagree with `params_decoded` -- so a
    second pass with them in hand is the cheapest repair available: one chart's
    worth of tokens, against a chart that renders wrong on the finished
    dashboard.

    `hosted` marks a chart a live parent draws. Its parent's params name it,
    and the applier refuses a reference to a chart that was never created, so
    such a chart is never left out -- only reported.

    `group_reference` is set only for a chart that is not the first member
    configured in its `same_as` group: the first member's finished spec, so
    this call copies its shared choices instead of reinventing them. `None`
    for every solo chart and for a group's own first member, which is
    configured exactly as it always was.
    """
    ref = decision.get("ref") or decision.get("region_id", "?")
    viz_type = decision.get("viz_type") or ""
    result = ChartSpecResult(
        ref=ref, region_id=decision.get("region_id", "?"), viz_type=viz_type
    )
    try:
        panel_path, panel = load_panel(viz_type, registry)
    except Exception as ex:  # noqa: BLE001 - one worker must not kill the fan-out
        result.error = str(ex)
        return result

    system_prompt = build_system_prompt(prompts_dir, viz_type, panel_path, panel)
    base_prompt = build_user_prompt(region, binding, decision, design_system)
    if group_reference:
        base_prompt += _group_reference_note(group_reference)

    early_result, unfillable = _run_attempts(
        provider,
        system_prompt,
        base_prompt,
        result,
        binding,
        decision,
        panel,
        region,
        attempts,
        ref,
        viz_type,
    )
    if early_result is not None:
        return early_result
    if unfillable:
        logger.info("%s: required metric(s) %s cannot be filled", ref, unfillable)
    if result.leave_out and not hosted:
        result.error = result.leave_out
    return result


def _run_attempts(
    provider: LLMProvider,
    system_prompt: str,
    base_prompt: str,
    result: ChartSpecResult,
    binding: dict[str, Any],
    decision: dict[str, Any],
    panel: str,
    region: dict[str, Any],
    attempts: int,
    ref: str,
    viz_type: str,
) -> tuple[ChartSpecResult | None, list[str]]:
    """The attempt loop of `run_one`, mutating `result` in place.

    Split out because `run_one` mixed this retry machinery with the
    once-per-call setup and teardown around it. Returns a result to return
    immediately from `run_one` (a hard failure, or a clean pass), or `None`
    to fall through to `run_one`'s own post-loop handling -- along with
    whichever metrics turned out unfillable, since `run_one` logs those too.
    """
    unfillable: list[str] = []
    for attempt in range(1, max(1, attempts) + 1):
        user_prompt = _attempt_prompt(base_prompt, result, unfillable)
        try:
            response = provider.complete(system_prompt, user_prompt)
            result.cost_usd += response.cost_usd or 0.0
            spec = extract_json(response.text)
        except (LLMError, Exception) as ex:  # noqa: BLE001 - reported, not raised
            result.error = str(ex)
            return result, unfillable

        result.spec = spec
        result.error = None
        result.leave_out = None
        try:
            result.problems = validate(spec, binding, decision, panel, region)
        except Exception as ex:  # noqa: BLE001 - a validator bug is not a failure
            logger.exception("validate() raised for %s", ref)
            result.problems = [f"validator crashed: {type(ex).__name__}: {ex}"]
            return result, unfillable
        if not result.problems:
            return result, unfillable
        decoded = spec.get("params_decoded") if isinstance(spec, dict) else None
        unfillable = unfillable_metrics(decoded, binding, panel)
        if unfillable:
            result.leave_out = _leave_out_reason(
                decision, viz_type, unfillable, binding
            )
            settled = _unfillable_problems(decoded, unfillable)
            if all(problem in settled for problem in result.problems):
                # Asking again cannot fill it, and nothing else is wrong. A
                # second pass is kept whenever something else is: a bare
                # column name or a missing filter is exactly what it repairs.
                result.attempts = attempt
                break
        logger.info(
            "%s attempt %d/%d has %d problem(s): %s",
            ref,
            attempt,
            attempts,
            len(result.problems),
            "; ".join(result.problems)[:300],
        )
    else:
        result.attempts = attempts
    return None, unfillable


def _attempt_prompt(
    base_prompt: str, previous: ChartSpecResult, unfillable: list[str]
) -> str:
    """The prompt for the next attempt: the base, plus what the last one got wrong.

    The problems of a required metric no measure can fill are left out of the
    repair list and named as settled instead, so the repair pass spends itself
    on what it can fix.
    """
    if not previous.problems:
        return base_prompt
    settled = _unfillable_problems(
        (previous.spec or {}).get("params_decoded"), unfillable
    )
    fixable = [problem for problem in previous.problems if problem not in settled]
    return f"{base_prompt}\n\n{_repair_note(fixable, unfillable)}"


def _leave_out_reason(
    decision: dict[str, Any],
    viz_type: str,
    unfillable: list[str],
    binding: dict[str, Any],
) -> str | None:
    """Why a chart is left out rather than created, or None to create it.

    A generated plugin reads its required metrics unconditionally, and a chart
    that throws covers the whole dashboard with the error overlay. The applier
    skips a chart with an error, and a missing tile is the smaller loss. A
    stock chart answers an empty metric with an error card of its own.
    """
    if not (decision.get("built_by_stage_f") or viz_type.startswith("custom_")):
        return None
    return (
        f"left out: {', '.join(unfillable)} must hold a metric the plugin reads "
        f"unconditionally, and the binding has "
        f"{len(binding.get('measures') or [])} measure(s) for them; the chart "
        "would throw on the dashboard. The plugin was written for a region "
        "reading more measures than this one."
    )


# Fields a same_as group's members must agree on, matched by name rather than
# enumerated per viz type: `_component_groups_split`/`_shared_plugin_shapes`
# already force a same_as group onto one viz_type, so its members share one
# control schema, and a key on one member's `params_decoded` is a control
# every other member has too. A stock chart's own `number_format` and
# `currency_format` are named directly; a generated plugin's arbitrary colour,
# palette or typography keys (`captionColor`, `fontSize`) are caught by
# pattern rather than by name, because stage F may call them anything.
_SHARED_VISUAL_PATTERN = re.compile(
    r"color|colour|palette|fontsize|font_size|typography", re.IGNORECASE
)
_GROUP_VISUAL_NAMES = {*NUMBER_FORMAT_PARAMS, *DATE_FORMAT_PARAMS}
# Fields that are the whole reason a same_as group has more than one region:
# each member's own slice of the data. These are never compared, however they
# are named.
_GROUP_SCOPING_KEYS = {
    "adhoc_filters",
    "filters",
    "extra_form_data",
    "datasource_id",
    "slice_name",
    "groupby",
    "columns",
    "all_columns",
    "entity",
    "granularity_sqla",
    "x_axis",
}


def _group_metric_aggregates(decoded: dict[str, Any]) -> dict[str, str]:
    """The aggregate function each metric control in ``decoded`` uses.

    A bare saved-metric name (``"count"``) carries no aggregate of its own and
    is skipped rather than compared: two members legitimately share `count`
    without that implying anything about the rest of their params. Where a
    control holds a list of adhoc metrics, its aggregates are joined so two
    members using a different mix are still caught rather than silently
    matching on an empty intersection.
    """
    aggregates: dict[str, str] = {}
    for name, value in decoded.items():
        items = value if isinstance(value, list) else [value]
        found = [
            str(item["aggregate"]).upper()
            for item in items
            if isinstance(item, dict) and item.get("aggregate")
        ]
        if found:
            aggregates[name] = ",".join(sorted(set(found)))
    return aggregates


def same_as_consistency(members: list[tuple[str, dict[str, Any] | None]]) -> list[str]:
    """A `same_as` group's chart specs, checked for the drift stage D must not have.

    Not a judgement call, the same posture `_shared_plugin_shapes` takes one
    stage up: `row_limit`, a metric control's aggregate, and any colour or
    format field are properties of the repeated *component* stage A
    photographed once, not of whichever slice of the data any one copy is
    scoped to, so they must agree across every member. A real run disagreed on
    exactly these -- `SUM` against `MAX`, `row_limit` 1000 against 1, a caption
    colour set on one of two literally-identical placeholder tiles and left
    blank on the other -- and every chart involved passed every check that
    only ever looked at it alone.

    ``members`` is ``(ref, params_decoded)`` pairs, in whatever order the
    group's charts finished. A member stage D could not configure at all
    contributes no `params_decoded` and is skipped rather than treated as a
    drift of its own -- it already has an `error` reported elsewhere. Fewer
    than two usable members is not a disagreement, because there is nothing
    left to disagree with.
    """
    usable = [(ref, decoded) for ref, decoded in members if isinstance(decoded, dict)]
    if len(usable) < 2:
        return []

    problems: list[str] = []

    limits = {
        ref: decoded["row_limit"] for ref, decoded in usable if "row_limit" in decoded
    }
    if len({repr(limit) for limit in limits.values()}) > 1:
        listed = ", ".join(f"{ref}={limit}" for ref, limit in sorted(limits.items()))
        problems.append(
            "same_as group disagrees on row_limit, a property of the repeated "
            f"component rather than of any one copy's data: {listed}"
        )

    per_ref_aggregates = {
        ref: _group_metric_aggregates(decoded) for ref, decoded in usable
    }
    control_names = {name for aggs in per_ref_aggregates.values() for name in aggs}
    for name in sorted(control_names):
        values = {
            ref: aggs[name] for ref, aggs in per_ref_aggregates.items() if name in aggs
        }
        if len(values) > 1 and len({repr(v) for v in values.values()}) > 1:
            listed = ", ".join(f"{ref}={agg}" for ref, agg in sorted(values.items()))
            problems.append(
                f"same_as group disagrees on the aggregate function `{name}` "
                f"uses: {listed}. A repeated component reads the same "
                "aggregate everywhere; only the data it is scoped to differs."
            )

    shared_keys = {
        key
        for _, decoded in usable
        for key in decoded
        if key not in _GROUP_SCOPING_KEYS
        and (key in _GROUP_VISUAL_NAMES or _SHARED_VISUAL_PATTERN.search(key))
    }
    for key in sorted(shared_keys):
        values = {ref: decoded[key] for ref, decoded in usable if key in decoded}
        if len(values) > 1 and len({repr(v) for v in values.values()}) > 1:
            listed = ", ".join(f"{ref}={values[ref]!r}" for ref in sorted(values))
            problems.append(
                f"same_as group disagrees on `{key}`, a visual property of the "
                f"repeated component: {listed}. Match it across every member; "
                "only fields scoping each copy to its own data should differ."
            )

    return problems


def _consistency_groups(
    jobs: list[dict[str, Any]], design_analysis: dict[str, Any]
) -> list[list[dict[str, Any]]]:
    """Jobs that must be configured consistently with each other, grouped.

    Keyed off stage C's own `same_as` grouping rather than a new one: this
    stage should ask the same question C already answered, not re-derive it
    from `design_analysis` a second time. A `same_as` group is further split
    by `viz_type`, because stage C's own validators
    (`_component_groups_split`, `_shared_plugin_shapes`) allow a group to
    legitimately resolve to more than one viz_type when its members read
    different numbers of measures -- and forcing consistency across two
    different control schemas is not a mechanical fact, it is a category
    error. A bucket of one is not a group: nothing to be consistent with.
    """
    by_region = {d.get("region_id"): d for d in jobs}
    groups: list[list[dict[str, Any]]] = []
    for _head, region_ids in same_as_groups(design_analysis).items():
        by_viz: dict[Any, list[dict[str, Any]]] = {}
        for region_id in region_ids:
            if decision := by_region.get(region_id):
                by_viz.setdefault(decision.get("viz_type"), []).append(decision)
        groups.extend(bucket for bucket in by_viz.values() if len(bucket) > 1)
    return groups


def run_all(
    provider: LLMProvider,
    design_analysis: dict[str, Any],
    binding_set: dict[str, Any],
    plan: dict[str, Any],
    prompts_dir: pathlib.Path,
    registry: Registry,
    max_workers: int = MAX_WORKERS,
    on_chart: Any = None,
) -> list[ChartSpecResult]:
    """Fan out one worker per chart that needs configuring.

    Every chart outside a `same_as` group is configured exactly as before:
    independent, parallel, no visibility into any other chart. A `same_as`
    group -- stage A's repeated component, several regions that must render
    consistently -- gets its first member configured on its own, and its
    remaining members configured with that finished spec as a reference for
    the choices that are properties of the component rather than of any one
    copy's data (aggregate function, `row_limit`, colour/format fields). Those
    members still run in parallel with each other, with every other group's
    members, and with every solo chart; only "after its own group's first
    member" is enforced, because that is the one ordering the consistency
    guarantee actually depends on. `same_as_consistency` is the safety net
    behind the prompt: it compares the group's finished specs afterwards and
    fails every member of a group that still drifted, whatever caused it.
    """
    regions = {r["region_id"]: r for r in design_analysis.get("regions", [])}
    bindings = {b["region_id"]: b for b in binding_set.get("bindings", [])}
    design_system = plan.get("design_system", {})
    fallback = fallback_dataset(binding_set)

    def region_for(region_id: str) -> dict[str, Any]:
        """The region a decision draws.

        A direct lookup. This used to fall back to `region_id.split(":")[0]`,
        from when stage B split a container into `r07_card:1`, `:2` -- ids
        stage A never emitted. Stage A now emits every child as a region of
        its own, so the fallback can only fire on a genuine mismatch, where
        silently substituting the parent configures a chart against the wrong
        section's description.
        """
        return regions.get(region_id, {})

    def binding_for(region_id: str) -> dict[str, Any]:
        """The data a decision reads.

        Stage B emits exactly one binding per `region_id` and binds every
        region, including those that draw nothing. So a miss here is not the
        normal case it once was -- it means stage B and stage C disagree about
        what exists -- and the chart still needs a datasource, which is what
        the shared dataset is for.

        `attached_only` marks a binding whose dataset is there only to satisfy
        Superset, and the prompt turns it into "query nothing from this". It
        is set from the dataset id rather than from a missed lookup, because
        stage B now binds wrappers, nav, headers and text to the shared
        dataset explicitly: they arrive looking like ordinary data bindings,
        and a worker handed a one-column table without being told writes a
        `SUM()` and a groupby to justify it.
        """
        binding = bindings.get(region_id)
        if binding is None:
            return {"dataset_id": fallback, "attached_only": True} if fallback else {}
        if fallback and binding.get("dataset_id") == fallback:
            return {**binding, "attached_only": True}
        return binding

    jobs = [
        decision
        for decision in plan.get("decisions", [])
        if decision.get("decision") in CONFIGURABLE
    ]
    if not jobs:
        return []

    hosted = hosted_refs(plan)
    groups = _consistency_groups(jobs, design_analysis)
    # A group's own leader is the first member configured -- solo, exactly
    # like any other chart -- so the rest have something finished to match.
    leader_group: dict[str, list[dict[str, Any]]] = {
        group[0]["ref"]: group for group in groups if group[0].get("ref")
    }
    grouped_refs = {d.get("ref") for group in groups for d in group}
    solo_jobs = [d for d in jobs if d.get("ref") not in grouped_refs]
    logger.info(
        "stage D: %d chart(s) to configure (%d in %d same_as group(s))",
        len(jobs),
        len(grouped_refs),
        len(groups),
    )

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:

        def submit(
            decision: dict[str, Any], reference: dict[str, Any] | None = None
        ) -> concurrent.futures.Future[ChartSpecResult]:
            return pool.submit(
                run_one,
                provider,
                region_for(decision["region_id"]),
                binding_for(decision["region_id"]),
                decision,
                design_system,
                prompts_dir,
                registry,
                hosted=decision.get("ref") in hosted,
                group_reference=reference,
            )

        results = _dispatch_fan_out(submit, solo_jobs, groups, leader_group, on_chart)

    _apply_group_consistency(groups, results)

    order = {d.get("ref"): i for i, d in enumerate(jobs)}
    results.sort(key=lambda r: order.get(r.ref, 0))
    return results


def _dispatch_fan_out(
    submit: Callable[
        [dict[str, Any], dict[str, Any] | None],
        concurrent.futures.Future[ChartSpecResult],
    ],
    solo_jobs: list[dict[str, Any]],
    groups: list[list[dict[str, Any]]],
    leader_group: dict[str, list[dict[str, Any]]],
    on_chart: Any,
) -> list[ChartSpecResult]:
    """Run every solo chart and every group's leader in parallel, queuing
    each group's followers as soon as its own leader lands.

    Split out of `run_all` because the scheduling loop -- submit, wait for
    whichever finishes first, decide what that unblocks -- is one self
    contained job that `run_all` was otherwise interleaving with the
    plain setup before it and the consistency check after it.

    A dynamic queue rather than one `as_completed` pass: a group's followers
    are not known to be safe to submit until its own leader finishes, so
    they are added to the pool as that happens rather than all up front.
    Every solo chart and every group's leader are submitted together up
    front and so still run fully in parallel with each other, and once a
    leader lands, its followers run in parallel with everything else still
    outstanding -- the only ordering this enforces is "after your own
    group's leader".
    """
    results: list[ChartSpecResult] = []
    pending: dict[concurrent.futures.Future[ChartSpecResult], dict[str, Any]] = {
        submit(decision, None): decision for decision in solo_jobs
    }
    for group in groups:
        leader = group[0]
        pending[submit(leader, None)] = leader

    while pending:
        done, _ = concurrent.futures.wait(
            pending, return_when=concurrent.futures.FIRST_COMPLETED
        )
        for future in done:
            decision = pending.pop(future)
            result = future.result()
            results.append(result)
            if on_chart:
                # Per-chart events rather than streamed reasoning: workers
                # run concurrently, so their thinking would interleave into
                # one unreadable buffer.
                on_chart(result.ref, result.viz_type, result.ok, len(results))

            leader_ref = decision.get("ref")
            followers = (
                leader_group.get(leader_ref) if isinstance(leader_ref, str) else None
            )
            if not followers:
                continue
            # A leader stage D could not configure at all leaves nothing to
            # copy -- its followers are still configured, just as
            # independently as they would have been with no group at all,
            # rather than being left out over a sibling's failure.
            reference = (
                {
                    "ref": result.ref,
                    "params_decoded": (result.spec or {}).get("params_decoded"),
                }
                if result.spec is not None
                else None
            )
            for follower in followers[1:]:
                pending[submit(follower, reference)] = follower
    return results


def _apply_group_consistency(
    groups: list[list[dict[str, Any]]], results: list[ChartSpecResult]
) -> None:
    """Compare each `same_as` group's finished specs and attach `drift`
    problems, in place, to every member of a group that disagreed.

    Split out of `run_all` as the one step that runs after the whole fan-out
    finishes rather than during it, and is unrelated to how the charts were
    scheduled.
    """
    if not groups:
        return
    by_ref = {r.ref: r for r in results}
    for group in groups:
        refs = [
            ref
            for ref in (d.get("ref") for d in group)
            if isinstance(ref, str) and ref in by_ref
        ]
        members = [
            (ref, (by_ref[ref].spec or {}).get("params_decoded")) for ref in refs
        ]
        drift = same_as_consistency(members)
        if not drift:
            continue
        # Attributed to every member rather than to whichever one "looks"
        # wrong: the group disagreed, and there is no mechanical way to say
        # which member is the outlier -- only that they must be made to
        # match.
        for ref in refs:
            by_ref[ref].problems = [*by_ref[ref].problems, *drift]
