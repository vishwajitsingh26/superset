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


def test_the_fallback_is_the_most_used_dataset() -> None:
    """A run spanning two datasets attaches the caption to the dominant one."""
    binding_set = {
        "bindings": [
            {"region_id": "r03", "dataset_id": 20},
            {"region_id": "r04", "dataset_id": 20},
            {"region_id": "r05", "dataset_id": 31},
        ]
    }
    assert fallback_dataset(binding_set) == 20


def test_a_run_with_no_bound_dataset_has_no_fallback() -> None:
    """Every binding is waiting on a dataset this run creates; the applier
    repoints them, so inventing one here would be worse than none."""
    assert (
        fallback_dataset({"bindings": [{"region_id": "r03", "dataset_id": None}]})
        is None
    )


def test_a_zero_is_never_offered_as_a_fallback() -> None:
    assert (
        fallback_dataset({"bindings": [{"region_id": "r03", "dataset_id": 0}]}) is None
    )


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
