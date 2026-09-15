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
"""The datasource every chart needs, including the ones that read nothing.

A run died at apply with `no dataset exists with id(s) [0]`. The chart was the
page title: stage A read it as `role: header`, stage B correctly bound nothing
to it, stage C decided to render it with the `custom_text` plugin, and stage D
-- handed an empty binding -- copied `"datasource_id": 0` out of the skeleton in
its own prompt. Every other placeholder there is `"..."`, which cannot be
mistaken for a value; a zero can. The one check that would have caught it was
skipped precisely because the binding was empty, so the chart was reported
ready and the run was paid for in full before Superset refused it.
"""

from __future__ import annotations

import pathlib
import re
from typing import Any
from unittest.mock import MagicMock

import pytest

from superset.design_to_dashboard.stages.d_configure import (
    _axis_format_note,
    build_user_prompt,
    fallback_dataset,
    metric_controls,
    run_all,
    run_one,
    same_as_consistency,
    unfillable_metrics,
    validate,
)
from superset.utils import json


def _spec(**body_overrides: Any) -> dict[str, Any]:
    body = {
        "slice_name": "Global Sales",
        "viz_type": "big_number_total",
        "datasource_id": 20,
        "datasource_type": "table",
        "params": json.dumps({"metric": "sum__global_sales"}),
        "query_context": None,
    }
    body.update(body_overrides)
    return {
        "ref": "c1",
        "region_id": "r03_global_sales",
        "request": {"method": "POST", "path": "/api/v1/chart/", "body": body},
        "params_decoded": {"metric": "sum__global_sales"},
        "confidence": "high",
    }


DECISION = {"viz_type": "big_number_total"}
BOUND = {"dataset_id": 20}


def _problems(spec: dict[str, Any], binding: dict[str, Any]) -> list[str]:
    return validate(spec, binding, DECISION)


# --- the zero ----------------------------------------------------------------


def test_a_zero_datasource_is_rejected_even_with_no_binding() -> None:
    """The exact failure: an unbound region keeps the skeleton's placeholder."""
    problems = _problems(_spec(datasource_id=0), {})
    assert any("is not a dataset" in p for p in problems)


def test_a_zero_datasource_is_rejected_with_a_binding_too() -> None:
    assert any(
        "is not a dataset" in p for p in _problems(_spec(datasource_id=0), BOUND)
    )


@pytest.mark.parametrize("value", [-1, None, "20", 3.0])
def test_a_datasource_that_is_not_a_positive_integer_is_rejected(value: Any) -> None:
    assert any("datasource_id" in p for p in _problems(_spec(datasource_id=value), {}))


def test_a_boolean_is_not_a_dataset_id() -> None:
    """`True` is an `int` in Python and would otherwise pass as dataset 1."""
    assert any(
        "is not an integer" in p for p in _problems(_spec(datasource_id=True), {})
    )


def test_a_real_datasource_with_no_binding_is_accepted() -> None:
    """An unbound region is not an error -- it just needs a real dataset."""
    assert not any("datasource_id" in p for p in _problems(_spec(), {}))


def test_a_datasource_disagreeing_with_the_binding_is_still_caught() -> None:
    assert any(
        "does not match the binding's" in p
        for p in _problems(_spec(datasource_id=7), BOUND)
    )


# --- where the fallback comes from -------------------------------------------


def test_the_fallback_is_the_dataset_stage_b_built_for_it() -> None:
    """Not a guess at the most-bound dataset: stage B names the one."""
    binding_set = {
        "shared_dataset_id": 9,
        "bindings": [
            {"region_id": "r03", "dataset_id": 20},
            {"region_id": "r04", "dataset_id": 20},
            {"region_id": "r05", "dataset_id": 31},
        ],
    }
    assert fallback_dataset(binding_set) == 9


def test_the_most_bound_dataset_is_not_the_fallback() -> None:
    """The old heuristic is now actively wrong.

    Stage B binds every wrapper, nav, header and text region to the shared
    dataset, so the shared one is usually the most-bound -- and where it is
    not, the guess attaches a chart to whichever real view happened to win.
    """
    binding_set = {
        "shared_dataset_id": 9,
        "bindings": [{"region_id": f"r{n:02d}", "dataset_id": 20} for n in range(6)],
    }
    assert fallback_dataset(binding_set) == 9


def test_a_run_with_no_shared_dataset_has_no_fallback() -> None:
    """Stage B's validator requires one; if it is missing, do not invent it."""
    assert (
        fallback_dataset({"bindings": [{"region_id": "r03", "dataset_id": 20}]}) is None
    )


def test_a_zero_is_never_offered_as_a_fallback() -> None:
    assert fallback_dataset({"shared_dataset_id": 0}) is None
    assert fallback_dataset({"shared_dataset_id": True}) is None


# --- the worker is told what the dataset is for ------------------------------


def test_an_attached_dataset_is_explained_to_the_worker() -> None:
    """Otherwise the binding reads as data to query and the model writes
    metrics for a title."""
    prompt = build_user_prompt(
        {"region_id": "r01_title", "role": "header"},
        {"dataset_id": 20, "attached_only": True},
        {"viz_type": "custom_text"},
        {},
    )
    assert "reads no data of its own" in prompt
    assert "Do not invent metrics" in prompt


def test_an_ordinary_binding_gets_no_such_note() -> None:
    prompt = build_user_prompt({"region_id": "r03_global_sales"}, BOUND, DECISION, {})
    assert "reads no data of its own" not in prompt


# --- the binding's filters, which nothing used to apply ----------------------
#
# Stage B minimises views on purpose: one view over all three providers, and
# each card's binding carries the clause that scopes it to its own row. Nothing
# made stage D apply them, so three provider cards off one view rendered all
# three providers -- a chart that renders cleanly and is simply wrong.

SCOPED = {
    "dataset_id": 31,
    "dimensions": ["provider_name"],
    "measures": ["spend"],
    "filters": [{"col": "provider_name", "op": "==", "val": "AWS"}],
}


def _with_params(params: dict[str, Any]) -> dict[str, Any]:
    spec = _spec(datasource_id=31, params=json.dumps(params))
    spec["params_decoded"] = params
    return spec


def test_an_unapplied_binding_filter_fails_the_chart() -> None:
    problems = validate(
        _with_params({"metric": "spend", "adhoc_filters": []}), SCOPED, DECISION
    )
    assert any("provider_name" in p and "applies it" in p for p in problems)


def test_a_simple_adhoc_filter_satisfies_it() -> None:
    params = {
        "metric": "spend",
        "adhoc_filters": [
            {
                "expressionType": "SIMPLE",
                "subject": "provider_name",
                "operator": "==",
                "comparator": "AWS",
                "clause": "WHERE",
            }
        ],
    }
    assert not [
        p for p in validate(_with_params(params), SCOPED, DECISION) if "applies it" in p
    ]


def test_a_sql_clause_naming_the_column_satisfies_it() -> None:
    """The operator and value have several legitimate spellings; the column
    is the part that cannot be got right by accident."""
    params = {
        "metric": "spend",
        "adhoc_filters": [
            {
                "expressionType": "SQL",
                "sqlExpression": "provider_name = 'AWS'",
                "clause": "WHERE",
            }
        ],
    }
    assert not [
        p for p in validate(_with_params(params), SCOPED, DECISION) if "applies it" in p
    ]


def test_extra_form_data_satisfies_it_too() -> None:
    params = {
        "metric": "spend",
        "adhoc_filters": [],
        "extra_form_data": {"filters": [{"col": "provider_name", "val": ["AWS"]}]},
    }
    assert not [
        p for p in validate(_with_params(params), SCOPED, DECISION) if "applies it" in p
    ]


def test_a_binding_with_no_filters_demands_nothing() -> None:
    params = {"metric": "spend", "adhoc_filters": []}
    assert not [
        p
        for p in validate(_with_params(params), {"dataset_id": 31}, DECISION)
        if "applies it" in p
    ]


def test_only_the_missing_filter_is_reported() -> None:
    binding = {
        "dataset_id": 31,
        "filters": [
            {"col": "provider_name", "op": "==", "val": "AWS"},
            {"col": "service_category", "op": "==", "val": "Database"},
        ],
    }
    params = {
        "metric": "spend",
        "adhoc_filters": [
            {"expressionType": "SIMPLE", "subject": "provider_name", "operator": "=="}
        ],
    }
    problems = [
        p
        for p in validate(_with_params(params), binding, DECISION)
        if "applies it" in p
    ]
    assert len(problems) == 1
    assert "service_category" in problems[0]


# --- lookups that no longer guess --------------------------------------------


def test_a_shared_binding_is_marked_attached_only() -> None:
    """Stage B binds wrappers and headers to the shared dataset explicitly, so
    they arrive looking like ordinary data unless the id is recognised."""
    results = _run_all_lookups(
        {
            "shared_dataset_id": 9,
            "bindings": [
                {"region_id": "r01_title", "dataset_id": 9},
                {"region_id": "r03_aws", "dataset_id": 31},
            ],
        }
    )
    assert results["r01_title"]["attached_only"] is True
    assert "attached_only" not in results["r03_aws"]


def test_an_unbound_region_falls_back_to_shared() -> None:
    results = _run_all_lookups(
        {"shared_dataset_id": 9, "bindings": []}, region_ids=["r09_mystery"]
    )
    assert results["r09_mystery"] == {"dataset_id": 9, "attached_only": True}


def test_a_colon_id_no_longer_borrows_its_parents_binding() -> None:
    """The `:N` fallback is from a contract stage B no longer has. Silently
    substituting the parent configured a chart against the wrong data."""
    results = _run_all_lookups(
        {
            "shared_dataset_id": 9,
            "bindings": [{"region_id": "r07_card", "dataset_id": 31}],
        },
        region_ids=["r07_card:1"],
    )
    assert results["r07_card:1"] == {"dataset_id": 9, "attached_only": True}


def _run_all_lookups(
    binding_set: dict[str, Any], region_ids: list[str] | None = None
) -> dict[str, Any]:
    """Drive run_all's internal lookups by capturing what each worker got."""
    ids = region_ids or [b["region_id"] for b in binding_set["bindings"]]
    captured: dict[str, Any] = {}

    class _Provider:
        def complete(self, system: str, user: str, **kwargs: Any) -> Any:
            raise AssertionError("no worker should run in this test")

    plan = {
        "decisions": [
            {"region_id": r, "ref": f"c{n}", "decision": "configure", "viz_type": "x"}
            for n, r in enumerate(ids)
        ]
    }

    def _capture(*args: Any, **kwargs: Any) -> Any:
        captured[args[1]["region_id"]] = args[2]
        raise RuntimeError("stop")

    import superset.design_to_dashboard.stages.d_configure as module
    from superset.design_to_dashboard.registry import Registry

    original = module.run_one
    module.run_one = _capture
    try:
        module.run_all(
            _Provider(),  # type: ignore[arg-type]
            {"regions": [{"region_id": r} for r in ids]},
            binding_set,
            plan,
            pathlib.Path("."),
            Registry(entries=[], repo_root=pathlib.Path(".")),
        )
    except Exception:  # noqa: BLE001, S110 - the workers are stubbed to stop
        pass
    finally:
        module.run_one = original
    return captured


# --- metric controls ---------------------------------------------------------
# A column name in a metric control reads as a saved metric that does not
# exist, and the chart's query came back 400. An empty metric in a control a
# generated plugin read unconditionally threw inside it, and the error overlay
# covered the whole dashboard. Both passed every check this stage had.

TILE_PANEL = """
import { ControlPanelConfig, sharedControls, t } from '../adapters/supersetAdapter';

const config: ControlPanelConfig = {
  controlPanelSections: [
    {
      label: t('Query'),
      expanded: true,
      controlSetRows: [
        [{ name: 'headline', config: { ...sharedControls.metric, label: t('Value') } }],
        [
          {
            name: 'subline',
            // optional: a sibling region may have nothing to put here
            config: { ...sharedControls.metric, label: t('Sub-line'), validators: [] },
          },
        ],
        ['adhoc_filters'],
        [{ name: 'row_limit', config: { ...sharedControls.row_limit, default: 1 } }],
        [{ name: 'caption', config: { type: 'TextControl', default: '' } }],
      ],
    },
  ],
};

export default config;
"""
TILE = {"viz_type": "custom_tile"}
TILE_BINDING = {"dataset_id": 20, "dimensions": ["provider"], "measures": ["coverage"]}
SIMPLE = {
    "expressionType": "SIMPLE",
    "column": {"column_name": "coverage"},
    "aggregate": "SUM",
    "label": "Coverage",
}


def _tile(
    binding: dict[str, Any] | None = None, panel: str = TILE_PANEL, **params: Any
) -> list[str]:
    decoded = {"row_limit": 1, "adhoc_filters": [], **params}
    spec = _spec(viz_type="custom_tile", params=json.dumps(decoded))
    spec["params_decoded"] = decoded
    return validate(spec, binding or TILE_BINDING, TILE, panel)


def test_a_column_name_in_a_metric_control_is_rejected() -> None:
    """The 400: `coverage` is a column, and no saved metric carries its name."""
    problems = _tile(headline="coverage", subline=None)
    assert len(problems) == 1
    assert "not a saved metric" in problems[0]
    assert "400" in problems[0]
    # Phrased as the fix, so the repair pass can act on it.
    assert '"column_name": "coverage"' in problems[0]


def test_count_is_the_saved_metric_every_dataset_has() -> None:
    assert _tile(headline="count", subline=None) == []


def test_a_saved_metric_the_binding_names_is_accepted() -> None:
    binding = {**TILE_BINDING, "measures": [{"metric_name": "total_spend"}]}
    assert _tile(binding, headline="total_spend", subline=None) == []


def test_a_complete_adhoc_metric_is_accepted() -> None:
    assert _tile(headline=SIMPLE, subline=None) == []


def test_a_sql_adhoc_metric_is_accepted() -> None:
    sql = {"expressionType": "SQL", "sqlExpression": "AVG(coverage)", "label": "Avg"}
    assert _tile(headline=sql, subline=sql) == []


@pytest.mark.parametrize("empty", ["", None, []])
def test_an_empty_required_metric_is_rejected(empty: Any) -> None:
    """The crash: a spread `sharedControls.metric` is `validateNonEmpty`, and
    the plugin read it whether or not stage D filled it."""
    problems = _tile(headline=empty, subline=None)
    assert len(problems) == 1
    assert "requires a metric here" in problems[0]
    assert "`headline`" in problems[0]


def test_an_absent_required_metric_is_rejected() -> None:
    assert any("`headline` is a required metric control" in p for p in _tile())


def test_an_optional_metric_may_be_null_but_not_an_empty_string() -> None:
    assert _tile(headline=SIMPLE, subline=None) == []
    problems = _tile(headline=SIMPLE, subline="")
    assert len(problems) == 1
    assert "empty string" in problems[0]


def test_an_adhoc_metric_missing_its_parts_is_rejected() -> None:
    problems = _tile(
        headline={"expressionType": "SIMPLE", "column": "coverage"}, subline=None
    )
    assert len(problems) == 1
    for part in ("`column`", "`aggregate`", "`label`"):
        assert part in problems[0]


def test_a_shared_metric_key_is_checked_without_its_control_panel() -> None:
    """A stock panel reaches `metric` through a section it imports, so the key
    in params is the only evidence the control exists."""
    assert any("not a saved metric" in p for p in _problems(_spec(), BOUND))


def test_every_item_of_a_metrics_list_is_checked() -> None:
    spec = _spec(params=json.dumps({"metrics": [SIMPLE, "coverage"]}))
    spec["params_decoded"] = {"metrics": [SIMPLE, "coverage"]}
    problems = validate(spec, TILE_BINDING, DECISION)
    assert [p for p in problems if "metrics[1]" in p]
    assert not [p for p in problems if "metrics[0]" in p]


def test_a_single_metric_control_does_not_take_a_list() -> None:
    assert any("takes one metric" in p for p in _tile(headline=[SIMPLE]))


def test_metric_controls_are_read_from_the_panel_source() -> None:
    controls = metric_controls(TILE_PANEL)
    assert set(controls) == {"headline", "subline"}
    assert controls["headline"].required
    assert not controls["subline"].required
    assert not controls["headline"].multi


def test_a_stock_override_and_a_mode_dependent_control_are_optional() -> None:
    """Superset's table clears `validators` on `metrics` and shows it only in
    aggregate mode; requiring it would reject every raw-mode table."""
    source = """
      [
        {
          name: 'metrics',
          override: { validators: [], visibility: isAggMode },
        },
        { name: 'pct', config: { type: 'MetricsControl', multi: true } },
        { name: 'label', config: { type: 'TextControl' } },
      ]
    """
    controls = metric_controls(source)
    assert set(controls) == {"metrics", "pct"}
    assert not controls["metrics"].required
    assert controls["metrics"].multi
    assert controls["pct"].multi


def test_a_panel_s_own_non_metric_control_is_not_read_as_a_shared_metric() -> None:
    """`size` is a shared metric picker, and also a plausible name for a
    plugin's own font-size control."""
    panel = TILE_PANEL.replace(
        "[{ name: 'caption', config: { type: 'TextControl', default: '' } }],",
        "[{ name: 'size', config: { type: 'TextControl', isInt: true } }],",
    )
    assert _tile(panel=panel, headline=SIMPLE, subline=None, size="24") == []


def test_a_shared_control_configured_from_a_variable_is_still_found() -> None:
    controls = metric_controls("[{ name: 'percent_metrics', config: pctControl }]")
    assert "percent_metrics" in controls
    assert not controls["percent_metrics"].required


# --- a panel built with helpers is read as well as a literal one -------------

# The shape stage F wrote in a real run: every metric control came out of a
# local helper, and not one of them was checked.
FACTORY_PANEL = """
import { sharedControls, t } from '@superset-ui/core';

const metricControl = (name: string, label: string, overrides = {}) => ({
  name,
  config: { ...sharedControls.metric, label: t(label), validators: [], ...overrides },
});

function requiredMetric(name: string, label: string) {
  return { name, config: { ...sharedControls.metric, label: t(label) } };
}

const shareConfig = { type: 'MetricsControl', multi: true, validators: [] };

const config = {
  controlPanelSections: [
    {
      controlSetRows: [
        [requiredMetric('awsMetric', 'AWS')],
        [metricControl('momMetric', 'MoM')],
        [metricControl('gcpMetric', 'GCP', { validators: [validateNonEmpty] })],
        [{ name: 'shares', config: shareConfig }],
        ['adhoc_filters'],
        [{ name: 'row_limit', config: { ...sharedControls.row_limit } }],
        [{ name: 'caption', config: { type: 'TextControl' } }],
      ],
    },
  ],
};

export default config;
"""


def test_metric_controls_built_by_a_helper_are_found() -> None:
    controls = metric_controls(FACTORY_PANEL)
    assert set(controls) == {"awsMetric", "momMetric", "gcpMetric", "shares"}
    assert controls["awsMetric"].required
    assert not controls["momMetric"].required
    # An override passed to the helper outranks the helper's own default.
    assert controls["gcpMetric"].required
    assert controls["shares"].multi
    assert not controls["shares"].required


def test_a_helper_built_control_is_held_to_the_metric_checks() -> None:
    problems = _tile(
        panel=FACTORY_PANEL,
        awsMetric="coverage",
        momMetric="",
        gcpMetric=SIMPLE,
        shares=None,
    )
    assert any("`awsMetric`" in p or "awsMetric" in p for p in problems)
    assert any("not a saved metric" in p for p in problems)
    assert any("empty string" in p for p in problems)


# --- a required metric the binding cannot fill is decided, not retried -------

UNBOUND_TILE = {**TILE_BINDING, "measures": []}
PROMPTS = pathlib.Path(__file__).parents[3] / "design-to-dashboard" / "prompts"


class _Panels:
    def control_panel(self, viz_type: str) -> tuple[str, str]:
        return "controlPanel.ts", TILE_PANEL


class _Answers:
    def __init__(self, spec: dict[str, Any]) -> None:
        self.spec = spec
        self.calls = 0

    def complete(self, system: str, user: str, **kwargs: Any) -> Any:
        self.calls += 1
        return MagicMock(text=json.dumps(self.spec), cost_usd=0.0)


def _unfilled_tile_spec() -> dict[str, Any]:
    decoded = {"row_limit": 1, "adhoc_filters": [], "headline": None, "subline": None}
    spec = _spec(viz_type="custom_tile", params=json.dumps(decoded))
    spec["params_decoded"] = decoded
    return spec


def test_a_required_metric_with_no_measure_behind_it_is_unfillable() -> None:
    decoded = _unfilled_tile_spec()["params_decoded"]
    assert unfillable_metrics(decoded, UNBOUND_TILE, TILE_PANEL) == ["headline"]
    # With a measure to put there, asking again can fix it.
    assert unfillable_metrics(decoded, TILE_BINDING, TILE_PANEL) == []


def test_a_generated_chart_that_would_throw_is_left_out_after_one_attempt() -> None:
    """Created anyway, its transformProps threw and the overlay covered the
    dashboard -- after a second call that could not have helped."""
    provider = _Answers(_unfilled_tile_spec())
    result = run_one(
        provider,  # type: ignore[arg-type]
        {"region_id": "r01"},
        UNBOUND_TILE,
        {**TILE, "ref": "c1", "region_id": "r01", "built_by_stage_f": True},
        {},
        PROMPTS,
        _Panels(),  # type: ignore[arg-type]
    )
    assert provider.calls == 1
    assert result.error is not None
    assert "headline" in result.error
    assert any("requires a metric here" in p for p in result.problems)


def test_a_hosted_chart_is_never_left_out() -> None:
    """Its parent names it, and a reference to a chart that was never created
    fails the whole apply."""
    provider = _Answers(_unfilled_tile_spec())
    result = run_one(
        provider,  # type: ignore[arg-type]
        {"region_id": "r01"},
        UNBOUND_TILE,
        {**TILE, "ref": "c1", "region_id": "r01", "built_by_stage_f": True},
        {},
        PROMPTS,
        _Panels(),  # type: ignore[arg-type]
        hosted=True,
    )
    assert provider.calls == 1
    assert result.error is None
    assert result.problems


# --- an unfillable metric does not stop the repair of everything else ---------

TWO_METRIC_PANEL = TILE_PANEL.replace(
    "validators: [] },",
    "},",
)


class _Sequence:
    """Answers in turn, and keeps the user prompt each call was sent."""

    def __init__(self, *specs: dict[str, Any]) -> None:
        self.specs = list(specs)
        self.prompts: list[str] = []

    def complete(self, system: str, user: str, **kwargs: Any) -> Any:
        self.prompts.append(user)
        spec = self.specs[min(len(self.prompts), len(self.specs)) - 1]
        return MagicMock(text=json.dumps(spec), cost_usd=0.0)


class _TwoMetricPanels:
    def control_panel(self, viz_type: str) -> tuple[str, str]:
        return "controlPanel.ts", TWO_METRIC_PANEL


def _tile_spec(**params: Any) -> dict[str, Any]:
    decoded = {"row_limit": 1, "adhoc_filters": [], **params}
    spec = _spec(viz_type="custom_tile", params=json.dumps(decoded))
    spec["params_decoded"] = decoded
    return spec


def _run_two_metric(provider: _Sequence, hosted: bool) -> Any:
    return run_one(
        provider,  # type: ignore[arg-type]
        {"region_id": "r01"},
        TILE_BINDING,
        {**TILE, "ref": "c1", "region_id": "r01", "built_by_stage_f": True},
        {},
        PROMPTS,
        _TwoMetricPanels(),  # type: ignore[arg-type]
        hosted=hosted,
    )


def test_an_unfillable_metric_beside_a_fixable_problem_still_gets_a_repair() -> None:
    """One measure for two required metrics: the empty one cannot be filled,
    but the bare column name in the other is the 400 the second pass fixes."""
    provider = _Sequence(
        _tile_spec(headline="coverage", subline=None),
        _tile_spec(headline=SIMPLE, subline=None),
    )
    result = _run_two_metric(provider, hosted=True)
    assert len(provider.prompts) == 2
    repair = provider.prompts[1]
    assert "not a saved metric" in repair
    assert "requires a metric here" not in repair
    assert "no measure for `subline`" in repair
    assert result.spec["params_decoded"]["headline"] == SIMPLE
    # Hosted: reported, never left out.
    assert result.error is None
    assert result.leave_out is not None
    assert result.attempts == 2


def test_a_chart_still_unfillable_after_its_repair_is_left_out() -> None:
    provider = _Sequence(
        _tile_spec(headline="coverage", subline=None),
        _tile_spec(headline=SIMPLE, subline=None),
    )
    result = _run_two_metric(provider, hosted=False)
    assert len(provider.prompts) == 2
    assert result.error is not None
    assert result.error.startswith("left out: subline")


def test_a_chart_whose_repair_fills_nothing_new_is_not_left_out_by_mistake() -> None:
    """A later attempt with every required metric filled clears the verdict."""
    provider = _Sequence(
        _tile_spec(headline="coverage", subline=None),
        _tile_spec(headline=SIMPLE, subline=SIMPLE),
    )
    result = _run_two_metric(provider, hosted=False)
    assert result.ok
    assert result.error is None
    assert result.leave_out is None


# --- axis_formats: the design's own answer, not a shape to guess -------------
#
# Stage F has both an explicit prompt callout for `region.axis_formats` and a
# validator that fails a plugin whose own `review_notes` never mention an
# axis. Stage D had neither: the fact reached it only buried inside the whole
# region blob, so nothing forced a stock chart's format params to reflect what
# stage A actually read off the design.

DATE_AXIS_REGION = {
    "region_id": "r05_trend",
    "axis_formats": [
        {
            "axis": "x",
            "kind": "date",
            "pattern": "MMM YYYY",
            "prefix": None,
            "suffix": None,
        }
    ],
}
NUMBER_AXIS_REGION = {
    "region_id": "r06_sales",
    "axis_formats": [
        {
            "axis": "y",
            "kind": "number",
            "pattern": ",.1f",
            "prefix": None,
            "suffix": "M",
        }
    ],
}
NO_AXIS_REGION = {"region_id": "r07_table", "axis_formats": []}


def test_the_axis_format_note_names_every_entry() -> None:
    note = _axis_format_note(DATE_AXIS_REGION)
    assert "x axis: date" in note
    assert "pattern `MMM YYYY`" in note
    assert "checked" in note.lower()


def test_no_axis_formats_gets_no_note() -> None:
    assert _axis_format_note(NO_AXIS_REGION) == ""
    assert _axis_format_note({}) == ""


def test_the_note_reaches_the_worker_prompt() -> None:
    prompt = build_user_prompt(DATE_AXIS_REGION, BOUND, DECISION, {})
    assert "MMM YYYY" in prompt
    assert "What each axis actually is" in prompt


# (a) axis_formats present, no relevant format param set at all -- flagged.
def test_a_chart_with_no_format_param_is_flagged_when_axis_formats_are_named() -> None:
    problems = validate(
        _with_params({"metric": "spend", "adhoc_filters": []}),
        SCOPED,
        DECISION,
        region=DATE_AXIS_REGION,
    )
    assert any(
        "axis_formats" in p and "sets none of the format controls" in p
        for p in problems
    )


# (b) axis_formats present, and the spec does set a relevant param -- no
# false positive.
def test_a_chart_that_sets_the_matching_format_param_is_not_flagged() -> None:
    problems = validate(
        _with_params(
            {
                "metric": "spend",
                "adhoc_filters": [],
                "x_axis_time_format": "%b %Y",
            }
        ),
        SCOPED,
        DECISION,
        region=DATE_AXIS_REGION,
    )
    assert not [p for p in problems if "sets none of the format controls" in p]


def test_a_number_axis_is_satisfied_by_number_format_too() -> None:
    problems = validate(
        _with_params({"metric": "spend", "adhoc_filters": [], "number_format": ",.1f"}),
        SCOPED,
        DECISION,
        region=NUMBER_AXIS_REGION,
    )
    assert not [p for p in problems if "sets none of the format controls" in p]


# (c) no axis_formats (empty, absent, or region not passed at all) -- never
# flagged, regardless of the chart spec's params.
def test_an_empty_axis_formats_never_fires_the_check() -> None:
    problems = validate(
        _with_params({"metric": "spend", "adhoc_filters": []}),
        SCOPED,
        DECISION,
        region=NO_AXIS_REGION,
    )
    assert not [p for p in problems if "axis_formats" in p]


def test_a_missing_region_never_fires_the_check() -> None:
    """A caller that has not been updated to pass `region` gets no check --
    not a spurious one against a region that was never given."""
    problems = validate(
        _with_params({"metric": "spend", "adhoc_filters": []}), SCOPED, DECISION
    )
    assert not [p for p in problems if "axis_formats" in p]


def test_an_si_format_on_an_already_scaled_axis_is_flagged() -> None:
    """The `8.92k` trap: the axis's own `M` suffix says the value is already
    scaled, so an SI/SMART_NUMBER format reapplies the scaling."""
    problems = validate(
        _with_params({"metric": "spend", "adhoc_filters": [], "number_format": ",.3s"}),
        SCOPED,
        DECISION,
        region=NUMBER_AXIS_REGION,
    )
    assert any("already scaled" in p for p in problems)


def test_a_plain_format_on_an_already_scaled_axis_is_not_flagged() -> None:
    problems = validate(
        _with_params({"metric": "spend", "adhoc_filters": [], "number_format": ",.1f"}),
        SCOPED,
        DECISION,
        region=NUMBER_AXIS_REGION,
    )
    assert not any("already scaled" in p for p in problems)


# --- same_as groups are configured consistently ------------------------------
#
# A real run configured four copies of one KPI tile in complete isolation --
# stage D's fan-out gave each worker only its own region, binding and decision
# -- and got `SUM` on one card, `MAX` on its sibling, `row_limit` 1000 against
# 1, and a caption colour set on one of two literally-identical "Coming Soon"
# placeholder tiles and left blank on the other. Every chart passed every
# check that only ever looked at it alone. These tests drive `run_all` end to
# end over a `same_as` group and confirm the group comes out matching on the
# fields that are properties of the repeated component, while each member
# still keeps the data-scoping that is the entire reason they are separate
# regions -- and that `same_as_consistency` catches it mechanically if a
# member ignores the prompt's instruction and drifts anyway.


def _group_design_analysis() -> dict[str, Any]:
    """Three regions stage A read as the same repeated KPI tile, plus one
    unrelated banner region that shares nothing with them."""
    return {
        "regions": [
            {"region_id": "r_aws", "n": 1, "same_as": 1},
            {"region_id": "r_gcp", "n": 2, "same_as": 1},
            {"region_id": "r_azure", "n": 3, "same_as": 1},
            {"region_id": "r_banner", "n": 4},
        ]
    }


def _group_binding_set() -> dict[str, Any]:
    return {
        "bindings": [
            {
                "region_id": "r_aws",
                "dataset_id": 20,
                "measures": ["spend"],
                "filters": [{"col": "provider_name", "op": "==", "val": "AWS"}],
            },
            {
                "region_id": "r_gcp",
                "dataset_id": 20,
                "measures": ["spend"],
                "filters": [{"col": "provider_name", "op": "==", "val": "GCP"}],
            },
            {
                "region_id": "r_azure",
                "dataset_id": 20,
                "measures": ["spend"],
                "filters": [{"col": "provider_name", "op": "==", "val": "Azure"}],
            },
            {"region_id": "r_banner", "dataset_id": 21, "measures": ["spend"]},
        ]
    }


def _group_plan() -> dict[str, Any]:
    return {
        "decisions": [
            {
                "region_id": region_id,
                "ref": ref,
                "decision": "configure",
                "viz_type": "custom_tile",
            }
            for ref, region_id in (
                ("c1", "r_aws"),
                ("c2", "r_gcp"),
                ("c3", "r_azure"),
                ("c4", "r_banner"),
            )
        ],
        "design_system": {},
    }


class _GroupRegistry:
    def control_panel(self, viz_type: str) -> tuple[str, str]:
        return "controlPanel.ts", TILE_PANEL


_GROUP_FILTER_CLAUSE: dict[str, dict[str, str | None]] = {
    "r_aws": {"col": "provider_name", "val": "AWS"},
    "r_gcp": {"col": "provider_name", "val": "GCP"},
    "r_azure": {"col": "provider_name", "val": "Azure"},
    "r_banner": {"col": None, "val": None},
}


class _WellBehavedGroupProvider:
    """Every follower faithfully copies the leader's shared choices, as asked.

    Not driven by call order: each answer is derived from the region_id
    embedded in its own prompt, so it behaves the same whichever member
    `run_all` happens to configure first.
    """

    def __init__(self) -> None:
        self.prompts: dict[str, str] = {}

    def complete(self, system: str, user: str, **kwargs: Any) -> Any:
        match = re.search(r'"region_id":\s*"(\w+)"', user)
        assert match, "worker prompt must name its own region_id"
        region_id = match.group(1)
        self.prompts[region_id] = user
        clause = _GROUP_FILTER_CLAUSE[region_id]
        decoded = {
            # The shared choices every member of the group must agree on.
            "row_limit": 5,
            "captionColor": "#111111",
            "headline": {
                "expressionType": "SIMPLE",
                "column": {"column_name": "spend"},
                "aggregate": "SUM",
                "label": region_id,
            },
            "subline": None,
            # Each member's own data-scoping, which must NOT match its
            # siblings'.
            "adhoc_filters": (
                [
                    {
                        "expressionType": "SIMPLE",
                        "subject": clause["col"],
                        "operator": "==",
                        "comparator": clause["val"],
                        "clause": "WHERE",
                    }
                ]
                if clause["col"]
                else []
            ),
        }
        spec = _spec(
            viz_type="custom_tile",
            slice_name=f"Spend ({region_id})",
            datasource_id=20 if region_id != "r_banner" else 21,
            params=json.dumps(decoded),
        )
        spec["params_decoded"] = decoded
        return MagicMock(text=json.dumps(spec), cost_usd=0.0)


def test_a_same_as_group_ends_up_consistent_and_correctly_scoped() -> None:
    """(a) shared choices agree across the group; (b) each member still gets
    its own correct, differing data-scoping."""
    provider = _WellBehavedGroupProvider()
    charts = run_all(
        provider,  # type: ignore[arg-type]
        _group_design_analysis(),
        _group_binding_set(),
        _group_plan(),
        PROMPTS,
        _GroupRegistry(),  # type: ignore[arg-type]
    )
    by_ref = {c.ref: c for c in charts}
    group_refs = ["c1", "c2", "c3"]
    assert all(by_ref[ref].ok for ref in group_refs), [
        (ref, by_ref[ref].problems, by_ref[ref].error) for ref in group_refs
    ]

    decoded = {ref: (by_ref[ref].spec or {})["params_decoded"] for ref in group_refs}
    assert len({decoded[ref]["row_limit"] for ref in group_refs}) == 1
    assert len({decoded[ref]["captionColor"] for ref in group_refs}) == 1
    assert len({decoded[ref]["headline"]["aggregate"] for ref in group_refs}) == 1

    comparators = {
        ref: decoded[ref]["adhoc_filters"][0]["comparator"] for ref in group_refs
    }
    assert comparators == {"c1": "AWS", "c2": "GCP", "c3": "Azure"}


def test_a_chart_outside_any_group_is_configured_independently() -> None:
    """(c) a region with no `same_as` sibling is unaffected: no group-reference
    note in its prompt, and it comes out with its own data untouched."""
    provider = _WellBehavedGroupProvider()
    charts = run_all(
        provider,  # type: ignore[arg-type]
        _group_design_analysis(),
        _group_binding_set(),
        _group_plan(),
        PROMPTS,
        _GroupRegistry(),  # type: ignore[arg-type]
    )
    by_ref = {c.ref: c for c in charts}
    assert by_ref["c4"].ok
    assert (by_ref["c4"].spec or {})["params_decoded"]["adhoc_filters"] == []
    assert "Part of a `same_as` group" not in provider.prompts["r_banner"]

    # The group's own first-configured member is solo too -- there is nothing
    # to reference yet -- only the members configured after it carry the note.
    leader_prompts = [p for rid, p in provider.prompts.items() if rid == "r_aws"]
    follower_prompts = [
        p for rid, p in provider.prompts.items() if rid in ("r_gcp", "r_azure")
    ]
    assert leader_prompts
    assert "Part of a `same_as` group" not in leader_prompts[0]
    assert follower_prompts
    assert all("Part of a `same_as` group" in p for p in follower_prompts)


class _MisbehavedGroupProvider(_WellBehavedGroupProvider):
    """`r_gcp` ignores the shared reference and drifts anyway."""

    def complete(self, system: str, user: str, **kwargs: Any) -> Any:
        response = super().complete(system, user, **kwargs)
        match = re.search(r'"region_id":\s*"(\w+)"', user)
        if match and match.group(1) == "r_gcp":
            spec = json.loads(response.text)
            spec["params_decoded"]["row_limit"] = 999
            spec["params_decoded"]["headline"]["aggregate"] = "MAX"
            spec["request"]["body"]["params"] = json.dumps(spec["params_decoded"])
            return MagicMock(text=json.dumps(spec), cost_usd=0.0)
        return response


def test_run_all_catches_a_group_that_still_drifted() -> None:
    """(d), end to end: the prompt is only ever advisory, so a member that
    ignores it and drifts anyway must still be caught mechanically."""
    provider = _MisbehavedGroupProvider()
    charts = run_all(
        provider,  # type: ignore[arg-type]
        _group_design_analysis(),
        _group_binding_set(),
        _group_plan(),
        PROMPTS,
        _GroupRegistry(),  # type: ignore[arg-type]
    )
    by_ref = {c.ref: c for c in charts}
    assert not by_ref["c1"].ok
    assert not by_ref["c2"].ok
    assert any("row_limit" in p for p in by_ref["c2"].problems)
    assert any("aggregate function" in p for p in by_ref["c2"].problems)
    # Unrelated to the group, untouched by its drift.
    assert by_ref["c4"].ok


# --- (d) the validator itself, against hand-built specs ----------------------


def test_same_as_consistency_flags_a_drifted_group() -> None:
    """The exact drift a real run hit: `SUM` vs `MAX`, `row_limit` 1000 vs 1,
    a caption colour set on one member and blank on the other."""
    leader = (
        "c1",
        {
            "row_limit": 1000,
            "captionColor": "#e74c3c",
            "headline": {**SIMPLE, "aggregate": "SUM"},
            "adhoc_filters": [],
        },
    )
    drifted = (
        "c2",
        {
            "row_limit": 1,
            "captionColor": "",
            "headline": {**SIMPLE, "aggregate": "MAX"},
            "adhoc_filters": [],
        },
    )
    problems = same_as_consistency([leader, drifted])
    assert any("row_limit" in p for p in problems)
    assert any("aggregate function `headline`" in p for p in problems)
    assert any("captionColor" in p for p in problems)


def test_same_as_consistency_is_silent_on_a_matching_pair() -> None:
    member = (
        "c1",
        {
            "row_limit": 5,
            "headline": {**SIMPLE, "aggregate": "SUM"},
            "adhoc_filters": [],
        },
    )
    other = (
        "c2",
        {
            "row_limit": 5,
            "headline": {**SIMPLE, "aggregate": "SUM"},
            "adhoc_filters": [],
        },
    )
    assert same_as_consistency([member, other]) == []


def test_same_as_consistency_needs_at_least_two_usable_members() -> None:
    """A member stage D could not configure at all is skipped, not treated as
    a drift of its own -- it already has an `error` reported elsewhere."""
    assert same_as_consistency([("c1", {"row_limit": 5})]) == []
    assert same_as_consistency([("c1", {"row_limit": 5}), ("c2", None)]) == []
