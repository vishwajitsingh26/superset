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
"""Structural checks on the data stage B builds.

Stage B creates the tables rather than finding them, so the failures worth
catching changed: not "is this column real" but "did you actually create what
you are binding to, and did you check the SQL runs".
"""

from __future__ import annotations

from typing import Any

import pytest

from superset.design_to_dashboard.stages.b_bind import (
    build_user_prompt,
    created_dataset_ids,
    validate,
)

SHARED = 23


@pytest.fixture
def design() -> dict[str, Any]:
    return {
        "global": {"title": "Database Spend — Multi-Cloud", "reading_order": [1, 2, 3]},
        "regions": [
            {"region_id": "r01_coverage", "n": 1, "role": "wrapper"},
            {"region_id": "r02_aws_coverage", "n": 2, "role": "kpi"},
            {"region_id": "r03_gcp_coverage", "n": 3, "role": "kpi", "same_as": 2},
        ],
    }


@pytest.fixture
def bindings() -> dict[str, Any]:
    return {
        "status": "ok",
        "dashboard_name": "database_spend_multi_cloud",
        "shared_dataset_id": SHARED,
        "fact_tables": [
            {
                "name": "database_coverage",
                "dataset_id": 24,
                "grain": "one row per instance family per cloud",
                "columns": ["instance_family", "cloud", "coverage_pct"],
                "row_count": 3,
            }
        ],
        "views": [
            {
                "name": "coverage_by_cloud",
                "dataset_id": 31,
                "sql": "SELECT cloud, AVG(coverage_pct) AS coverage FROM "
                "d2d.database_coverage GROUP BY cloud",
                "validated": True,
            }
        ],
        "bindings": [
            {"region_id": "r01_coverage", "dataset_id": SHARED},
            {
                "region_id": "r02_aws_coverage",
                "dataset_id": 31,
                "dimensions": ["cloud"],
                "measures": ["coverage"],
            },
            {
                "region_id": "r03_gcp_coverage",
                "dataset_id": 31,
                "dimensions": ["cloud"],
                "measures": ["coverage"],
            },
        ],
    }


def test_a_well_formed_binding_set_has_no_problems(
    bindings: dict[str, Any], design: dict[str, Any]
) -> None:
    assert validate(bindings, design) == []


# --- every region gets exactly one binding ----------------------------------


def test_a_region_left_unbound_is_reported(
    bindings: dict[str, Any], design: dict[str, Any]
) -> None:
    bindings["bindings"] = bindings["bindings"][:2]
    assert "region not bound: r03_gcp_coverage" in validate(bindings, design)


def test_a_binding_for_an_unknown_region_is_reported(
    bindings: dict[str, Any], design: dict[str, Any]
) -> None:
    bindings["bindings"].append({"region_id": "r99_ghost", "dataset_id": SHARED})
    assert "binding for unknown region: r99_ghost" in validate(bindings, design)


def test_one_region_is_one_binding(
    bindings: dict[str, Any], design: dict[str, Any]
) -> None:
    """The `:N` suffix retired with nesting -- a child is a region already."""
    bindings["bindings"].append({"region_id": "r02_aws_coverage", "dataset_id": 31})
    assert any("2 bindings" in p for p in validate(bindings, design))


def test_a_repeated_component_is_not_collapsed(
    bindings: dict[str, Any], design: dict[str, Any]
) -> None:
    """`same_as` means one plugin, never one binding: a coverage panel and a
    runtime panel are built identically and read nothing in common."""
    assert validate(bindings, design) == []
    assert {b["region_id"] for b in bindings["bindings"]} == {
        "r01_coverage",
        "r02_aws_coverage",
        "r03_gcp_coverage",
    }


# --- what was created, and what was only described --------------------------


def test_a_fact_table_without_an_id_was_never_created(
    bindings: dict[str, Any], design: dict[str, Any]
) -> None:
    del bindings["fact_tables"][0]["dataset_id"]
    assert any("has no dataset_id" in p for p in validate(bindings, design))


def test_a_view_without_an_id_was_never_saved(
    bindings: dict[str, Any], design: dict[str, Any]
) -> None:
    del bindings["views"][0]["dataset_id"]
    assert any("create_virtual_dataset" in p for p in validate(bindings, design))


def test_an_unvalidated_view_is_reported(
    bindings: dict[str, Any], design: dict[str, Any]
) -> None:
    """The stage can run its own SQL now, so not running it is a choice."""
    bindings["views"][0]["validated"] = False
    assert any("was not validated" in p for p in validate(bindings, design))


def test_a_view_without_sql_is_reported(
    bindings: dict[str, Any], design: dict[str, Any]
) -> None:
    bindings["views"][0]["sql"] = "  "
    assert any("has no SQL" in p for p in validate(bindings, design))


def test_a_fact_table_without_columns_is_reported(
    bindings: dict[str, Any], design: dict[str, Any]
) -> None:
    bindings["fact_tables"][0]["columns"] = []
    assert any("names no columns" in p for p in validate(bindings, design))


# --- what a binding points at -----------------------------------------------


def test_binding_to_a_dataset_nothing_created_is_reported(
    bindings: dict[str, Any], design: dict[str, Any]
) -> None:
    bindings["bindings"][1]["dataset_id"] = 999
    assert any("was not created by this stage" in p for p in validate(bindings, design))


def test_a_binding_needs_a_real_datasource(
    bindings: dict[str, Any], design: dict[str, Any]
) -> None:
    bindings["bindings"][1]["dataset_id"] = None
    assert any("every chart needs" in p for p in validate(bindings, design))


def test_a_wrapper_takes_the_shared_dataset(
    bindings: dict[str, Any], design: dict[str, Any]
) -> None:
    """Superset needs a datasource on a frame that never queries."""
    bindings["bindings"][0]["dataset_id"] = 31
    assert any(
        "rather than the shared dataset" in p for p in validate(bindings, design)
    )


def test_a_missing_shared_dataset_is_reported(
    bindings: dict[str, Any], design: dict[str, Any]
) -> None:
    del bindings["shared_dataset_id"]
    assert any("shared_dataset_id is missing" in p for p in validate(bindings, design))


def test_a_data_region_must_name_columns(
    bindings: dict[str, Any], design: dict[str, Any]
) -> None:
    bindings["bindings"][1]["dimensions"] = []
    bindings["bindings"][1]["measures"] = []
    assert any("names no columns" in p for p in validate(bindings, design))


def test_status_must_be_known(bindings: dict[str, Any], design: dict[str, Any]) -> None:
    bindings["status"] = "done"
    assert any("invalid status" in p for p in validate(bindings, design))


def test_created_dataset_ids_covers_all_three_kinds(
    bindings: dict[str, Any],
) -> None:
    assert created_dataset_ids(bindings) == {24, 31, SHARED}


# --- what the stage is given ------------------------------------------------


def test_every_region_reaches_the_stage(design: dict[str, Any]) -> None:
    """Wrappers used to be filtered out, which left them with no datasource."""
    prompt = build_user_prompt(design)
    for region_id in ("r01_coverage", "r02_aws_coverage", "r03_gcp_coverage"):
        assert region_id in prompt


def test_the_dashboard_name_reaches_the_stage(design: dict[str, Any]) -> None:
    """It names the fact tables, so it has to arrive. Non-ASCII is escaped by
    `json.dumps` on the way in and read back by the model, so the assertion is
    on the part that survives verbatim."""
    prompt = build_user_prompt(design)
    assert '"dashboard_title"' in prompt
    assert "Database Spend" in prompt
