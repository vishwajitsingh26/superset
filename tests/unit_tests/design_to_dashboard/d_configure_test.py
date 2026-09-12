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
from typing import Any

import pytest

from superset.design_to_dashboard.stages.d_configure import (
    build_user_prompt,
    fallback_dataset,
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

    original = module.run_one
    module.run_one = _capture
    try:
        module.run_all(
            _Provider(),  # type: ignore[arg-type]
            {"regions": [{"region_id": r} for r in ids]},
            binding_set,
            plan,
            pathlib.Path("."),
            "registry.json",
            ".",
        )
    except Exception:  # noqa: BLE001, S110 - the workers are stubbed to stop
        pass
    finally:
        module.run_one = original
    return captured
