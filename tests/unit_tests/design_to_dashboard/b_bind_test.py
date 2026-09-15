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

import pathlib
from typing import Any

import pytest

from superset.design_to_dashboard.llm.base import images_opened, LLMResponse
from superset.design_to_dashboard.stages import b_bind
from superset.design_to_dashboard.stages.b_bind import (
    avoid_taken_names,
    build_design_prompt,
    build_design_system_prompt,
    build_loop_prompt,
    build_loop_system_prompt,
    compact_databases,
    created_dataset_ids,
    DesignedData,
    validate,
    validate_spec,
)
from superset.utils import json

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
    prompt = build_design_prompt(design)
    for region_id in ("r01_coverage", "r02_aws_coverage", "r03_gcp_coverage"):
        assert region_id in prompt


def test_the_dashboard_name_reaches_the_stage(design: dict[str, Any]) -> None:
    """It names the fact tables, so it has to arrive. Non-ASCII is escaped by
    `json.dumps` on the way in and read back by the model, so the assertion is
    on the part that survives verbatim."""
    prompt = build_design_prompt(design)
    assert '"dashboard_title"' in prompt
    assert "Database Spend" in prompt


# --- the design step and the build step -------------------------------------
#
# Stage B used to be one tool loop. The traces showed it never opened the design
# image, designed every table twice, and re-sent stage A's descriptions on every
# round. It is now one call that sees the picture and writes the whole spec, and
# a loop that builds that spec without the picture.


PROMPTS = (
    pathlib.Path(__file__).resolve().parents[3] / "design-to-dashboard" / "prompts"
)

REGIONS = [
    {
        "region_id": "r01_header",
        "n": 1,
        "role": "header",
        "observed": "a bold page title",
        "chrome": {"surface": "bare"},
    },
    {
        "region_id": "r02_filter",
        "n": 2,
        "role": "filter",
        "controls": [
            {
                "kind": "select",
                "options": ["All Regions"],
                "icon": "a map-pin outline",
                "position": "third field in the control band",
            }
        ],
        "unusual_treatment": ["a pill with a chevron"],
    },
    {"region_id": "r03_card", "n": 3, "role": "kpi", "observed": "shows $10,495"},
]
DESIGN = {"global": {"title": "Spend"}, "regions": REGIONS}
DATABASES = [{"id": 1, "database_name": "examples", "backend": "postgresql"}]
# Never opened: the stub provider records the path and reads nothing.
DESIGN_IMAGE = "/designs/page.png"


def _spec(**overrides: Any) -> dict[str, Any]:
    spec: dict[str, Any] = {
        "status": "ok",
        "dashboard_name": "spend",
        "seen_in_design": ["the card prints a red 0.13% chip"],
        "fact_tables": [
            {
                "name": "spend_by_day",
                "columns": [
                    {"name": "usage_date", "type": "DATE"},
                    {"name": "cost", "type": "DOUBLE PRECISION"},
                ],
                "rows": [["2025-09-01", 10.5]],
            },
            {
                "name": "shared_no_query",
                "columns": [{"name": "placeholder", "type": "TEXT"}],
                "rows": [["static"]],
            },
        ],
        "views": [
            {
                "name": "spend_total",
                "sql": "SELECT SUM(cost) AS spend FROM d2d.spend_by_day",
            },
            {
                "name": "spend_options",
                "sql": "SELECT DISTINCT usage_date FROM d2d.spend_by_day",
            },
        ],
        "bindings": [
            {"region_id": "r01_header", "source": "shared_no_query"},
            {
                "region_id": "r02_filter",
                "source": "spend_options",
                "dimensions": ["usage_date"],
            },
            {"region_id": "r03_card", "source": "spend_total", "measures": ["spend"]},
        ],
    }
    spec.update(overrides)
    return spec


class _Provider:
    """Answers every call with the same text, and records what it was sent."""

    def __init__(
        self, text: str, name: str = "stub", usage: dict[str, Any] | None = None
    ) -> None:
        self.name = name
        self.text = text
        self.usage = usage or {}
        self.calls: list[dict[str, Any]] = []

    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        image_paths: list[str] | None = None,
        timeout: int | None = None,
        on_thinking: Any = None,
    ) -> LLMResponse:
        self.calls.append(
            {"system": system_prompt, "user": user_prompt, "image_paths": image_paths}
        )
        return LLMResponse(
            text=self.text, cost_usd=0.5, usage=self.usage, provider=self.name
        )


class _Gateway:
    name = "stub"

    def __init__(self) -> None:
        self.calls: list[str] = []

    def call(self, tool: str, arguments: dict[str, Any]) -> Any:
        self.calls.append(tool)
        return {
            "databases": [
                {
                    "id": 1,
                    "database_name": "examples",
                    "backend": "postgresql",
                    "changed_on": "2026-09-12",
                }
            ],
            "count": 1,
            "columns_available": ["uuid", "id"],
        }


# what the design step checks


def test_a_well_formed_spec_has_no_problems() -> None:
    assert validate_spec(_spec(), DESIGN) == []


def test_a_spec_with_no_proof_of_looking_is_reported() -> None:
    """A path-based provider cannot say whether the image was opened."""
    problems = validate_spec(_spec(seen_in_design=[]), DESIGN)
    assert any("no evidence the design image was read" in p for p in problems)


def test_proof_copied_from_stage_a_is_not_proof() -> None:
    """The old loop worked from stage A's text and never opened the picture."""
    problems = validate_spec(_spec(seen_in_design=["shows $10,495"]), DESIGN)
    assert any("word for word in stage A" in p for p in problems)


def test_a_row_with_the_wrong_number_of_values_is_reported() -> None:
    spec = _spec()
    spec["fact_tables"][0]["rows"].append(["2025-09-02"])
    assert any("do not have 2 values" in p for p in validate_spec(spec, DESIGN))


def test_a_column_type_the_tool_rejects_is_reported() -> None:
    spec = _spec()
    spec["fact_tables"][0]["columns"][1]["type"] = "FLOAT"
    assert any("'FLOAT'" in p for p in validate_spec(spec, DESIGN))


def test_a_table_without_rows_is_reported() -> None:
    """The build step creates what the spec lists and cannot invent rows."""
    spec = _spec()
    spec["fact_tables"][0]["rows"] = []
    assert any("has no rows" in p for p in validate_spec(spec, DESIGN))


def test_a_view_without_a_select_is_reported() -> None:
    spec = _spec()
    spec["views"][0]["sql"] = "DROP TABLE d2d.spend_by_day"
    assert any("has no SELECT" in p for p in validate_spec(spec, DESIGN))


def test_a_binding_to_something_the_spec_does_not_build_is_reported() -> None:
    spec = _spec()
    spec["bindings"][2]["source"] = "spend_nowhere"
    assert any("is not a table or view" in p for p in validate_spec(spec, DESIGN))


def test_a_region_that_draws_nothing_reads_the_shared_table() -> None:
    spec = _spec()
    spec["bindings"][0]["source"] = "spend_total"
    assert any("draws no data" in p for p in validate_spec(spec, DESIGN))


def test_a_region_the_spec_forgot_is_reported() -> None:
    """The build step cannot see the design, so a gap here is a gap for good."""
    spec = _spec()
    spec["bindings"].pop()
    assert "region not bound: r03_card" in validate_spec(spec, DESIGN)


# a temporal column that is not named the one way the design prompt allows


def test_a_time_column_naming_anything_but_d2d_date_is_reported() -> None:
    spec = _spec()
    spec["bindings"][2]["time_column"] = "usage_date"
    problems = validate_spec(spec, DESIGN)
    assert any("not 'd2d_date'" in p for p in problems)


def test_a_time_column_the_bound_views_sql_never_selects_is_reported() -> None:
    spec = _spec()
    spec["bindings"][2]["time_column"] = "d2d_date"
    # spend_total's SQL, unchanged from the base spec, never aliases to
    # d2d_date -- so the name and the view disagree.
    problems = validate_spec(spec, DESIGN)
    assert any("never selects a column under that name" in p for p in problems)


def test_a_time_column_the_bound_table_has_no_such_column_is_reported() -> None:
    spec = _spec()
    spec["bindings"][2]["source"] = "spend_by_day"
    spec["bindings"][2]["time_column"] = "d2d_date"
    problems = validate_spec(spec, DESIGN)
    assert any("has no column by that name" in p for p in problems)


def test_a_time_column_matching_the_views_own_alias_has_no_problem() -> None:
    spec = _spec()
    spec["views"][0]["sql"] = (
        "SELECT SUM(cost) AS spend, MAX(usage_date) AS d2d_date FROM d2d.spend_by_day"
    )
    spec["bindings"][2]["time_column"] = "d2d_date"
    assert validate_spec(spec, DESIGN) == []


# a sparkline or trendline needs a real time column behind it


def test_a_sparkline_with_no_time_column_is_reported() -> None:
    design = {
        "global": DESIGN["global"],
        "regions": [
            *REGIONS[:2],
            {
                **REGIONS[2],
                "unusual_treatment": ["a sparkline trending up behind the delta"],
            },
        ],
    }
    problems = validate_spec(_spec(), design)
    assert any("sparkline/trendline" in p for p in problems)


def test_a_sparkline_with_a_time_column_has_no_problem() -> None:
    design = {
        "global": DESIGN["global"],
        "regions": [
            *REGIONS[:2],
            {
                **REGIONS[2],
                "unusual_treatment": ["a sparkline trending up behind the delta"],
            },
        ],
    }
    spec = _spec()
    spec["views"][0]["sql"] = (
        "SELECT SUM(cost) AS spend, MAX(usage_date) AS d2d_date FROM d2d.spend_by_day"
    )
    spec["bindings"][2]["time_column"] = "d2d_date"
    assert validate_spec(spec, design) == []


# the stage A/B gate's fields, taught to stage B


def test_has_embedded_series_true_is_decisive_even_with_no_unusual_treatment() -> None:
    """Not just another vote alongside the keyword guess -- checked instead of it."""
    design = {
        "global": DESIGN["global"],
        "regions": [*REGIONS[:2], {**REGIONS[2], "has_embedded_series": True}],
    }
    problems = validate_spec(_spec(), design)
    assert any("gate confirmed an embedded series" in p for p in problems)


def test_has_embedded_series_false_overrides_a_stray_keyword_match() -> None:
    """A region the gate confirmed does NOT need a series is not re-flagged."""
    design = {
        "global": DESIGN["global"],
        "regions": [
            *REGIONS[:2],
            {
                **REGIONS[2],
                "has_embedded_series": False,
                "unusual_treatment": ["a sparkline trending up behind the delta"],
            },
        ],
    }
    assert validate_spec(_spec(), design) == []


def test_wrapper_reads_data_true_requires_a_real_binding() -> None:
    """The gate confirmed this header/wrapper/text prints a real value."""
    design = {
        "global": DESIGN["global"],
        "regions": [
            {**REGIONS[0], "wrapper_reads_data": True},
            *REGIONS[1:],
        ],
    }
    # r01_header still points at shared_no_query in the base spec and names
    # no columns -- the override means it is judged as a real chart now, so
    # it is flagged for naming no columns, not for reading the shared table.
    problems = validate_spec(_spec(), design)
    assert not any(
        "role 'header' draws no data but reads 'shared_no_query'" in p for p in problems
    )
    assert any(
        "wrapper_reads_data says this region reads real data" in p for p in problems
    )


def test_wrapper_reads_data_true_with_a_real_binding_has_no_problem() -> None:
    design = {
        "global": DESIGN["global"],
        "regions": [
            {**REGIONS[0], "wrapper_reads_data": True},
            *REGIONS[1:],
        ],
    }
    spec = _spec()
    spec["bindings"][0] = {
        "region_id": "r01_header",
        "source": "spend_total",
        "measures": ["spend"],
    }
    assert validate_spec(spec, design) == []


def test_attach_gate_fields_copies_present_fields_onto_the_matching_binding() -> None:
    spec = _spec()
    design = {
        "global": DESIGN["global"],
        "regions": [
            {**REGIONS[0], "wrapper_reads_data": True, "data_notes": "a real total"},
            REGIONS[1],
            {**REGIONS[2], "plugin_choice": "custom", "has_embedded_series": False},
        ],
    }
    b_bind.attach_gate_fields(spec, design)
    header, _, card = spec["bindings"]
    assert header["wrapper_reads_data"] is True
    assert header["data_notes"] == "a real total"
    assert card["plugin_choice"] == "custom"
    assert card["has_embedded_series"] is False


def test_attach_gate_fields_leaves_bindings_alone_when_nothing_is_set() -> None:
    spec = _spec()
    before = json.dumps(spec["bindings"])
    b_bind.attach_gate_fields(spec, DESIGN)
    assert json.dumps(spec["bindings"]) == before


# keeping clear of datasets earlier dashboards own


def test_a_taken_table_name_is_renamed_everywhere_it_is_read() -> None:
    """A fact table with a taken name silently rewrites another dashboard's data."""
    spec = _spec()
    spec["bindings"].append({"region_id": "r09_raw", "source": "spend_by_day"})
    notes = avoid_taken_names(spec, ["spend_by_day"], "ab12cd")

    assert spec["fact_tables"][0]["name"] == "spend_by_day_ab12cd"
    assert all("d2d.spend_by_day_ab12cd" in view["sql"] for view in spec["views"])
    assert spec["bindings"][-1]["source"] == "spend_by_day_ab12cd"
    assert len(notes) == 1


def test_a_taken_view_name_is_renamed_and_its_binding_follows() -> None:
    """A view with a taken name fails to save."""
    spec = _spec()
    avoid_taken_names(spec, ["spend_total"], "ab12cd")
    assert spec["views"][0]["name"] == "spend_total_ab12cd"
    assert spec["bindings"][2]["source"] == "spend_total_ab12cd"


def test_the_shared_table_is_never_renamed() -> None:
    """Every dashboard shares it on purpose."""
    spec = _spec()
    assert avoid_taken_names(spec, ["shared_no_query"], "ab12cd") == []
    assert spec["fact_tables"][1]["name"] == "shared_no_query"


def test_a_name_nobody_uses_is_left_alone() -> None:
    spec = _spec()
    assert avoid_taken_names(spec, ["something_else"], "ab12cd") == []
    assert spec == _spec()


def test_a_column_sharing_a_table_name_is_not_rewritten() -> None:
    spec = _spec()
    spec["views"][0]["sql"] = "SELECT spend_by_day FROM d2d.spend_by_day"
    avoid_taken_names(spec, ["spend_by_day"], "ab12cd")
    assert spec["views"][0]["sql"] == (
        "SELECT spend_by_day FROM d2d.spend_by_day_ab12cd"
    )


def test_an_unqualified_table_after_from_or_join_is_rewritten() -> None:
    spec = _spec()
    spec["views"][0]["sql"] = (
        "SELECT a.cost FROM spend_by_day a JOIN spend_by_day b ON a.cost = b.cost"
    )
    avoid_taken_names(spec, ["spend_by_day"], "ab12cd")
    assert spec["views"][0]["sql"].count("spend_by_day_ab12cd") == 2


def test_a_renamed_name_is_still_an_identifier_ddl_accepts() -> None:
    long_name = "a" * 60
    spec = _spec()
    spec["fact_tables"][0]["name"] = long_name
    avoid_taken_names(spec, [long_name], "ab12cd")
    renamed = spec["fact_tables"][0]["name"]
    assert len(renamed) <= b_bind.MAX_IDENTIFIER_LENGTH
    assert b_bind._IDENTIFIER.fullmatch(renamed)


def test_a_suffixed_name_that_is_also_taken_gets_a_counter() -> None:
    spec = _spec()
    avoid_taken_names(spec, ["spend_total", "spend_total_ab12cd"], "ab12cd")
    assert spec["views"][0]["name"] == "spend_total_ab12cd2"


# what each step is told


def test_the_design_step_is_never_told_the_image_is_already_attached() -> None:
    """That sentence is why the old loop never once opened the design."""
    system = build_design_system_prompt(PROMPTS)
    assert "already attached to this message" not in system
    assert "open every one with `Read`" in system


def test_the_build_loop_cannot_spend_a_round_on_the_database_list() -> None:
    system = build_loop_system_prompt(PROMPTS)
    assert "### list_databases" not in system
    assert "### create_fact_table" in system


def test_the_design_step_sees_the_names_it_may_not_use() -> None:
    prompt = build_design_prompt(DESIGN, {"1": ["cloud_spend_trend"]})
    assert "cloud_spend_trend" in prompt
    assert "a bold page title" in prompt


def test_the_build_loop_gets_the_spec_and_not_stage_as_descriptions() -> None:
    """Stage A's reading was most of every round's prompt, re-sent each round."""
    prompt = build_loop_prompt(DESIGN, _spec(), DATABASES, {"1": []})
    assert "spend_by_day" in prompt
    assert '"controls"' in prompt, "filter bindings need a region's controls"
    assert "All Regions" in prompt, "a select's options are what its view offers"
    for description in (
        "a bold page title",
        "shows $10,495",
        "chrome",
        "unusual",
        "map-pin",
        "control band",
    ):
        assert description not in prompt


def test_the_database_listing_is_reduced_to_what_a_step_needs() -> None:
    listing = _Gateway().call("list_databases", {})
    listing["databases"].append({"database_name": "no id"})
    assert compact_databases(listing) == DATABASES


# whether an image was really opened


@pytest.mark.parametrize(
    "provider,usage,expected",
    [
        ("claude_agent_sdk", {"input_tokens": 2}, False),
        ("claude_agent_sdk", {"input_tokens": 4}, True),
        ("claude_agent_sdk", {}, None),
        ("kiro_cli", {"input_tokens": 4}, None),
    ],
)
def test_whether_an_image_was_opened_is_read_only_where_it_can_be(
    provider: str, usage: dict[str, Any], expected: bool | None
) -> None:
    response = LLMResponse(text="{}", usage=usage, provider=provider)
    assert images_opened(response) is expected


# the steps end to end, with stubs


def test_the_design_step_sees_the_image_and_keeps_clear_of_taken_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        b_bind, "taken_dataset_names", lambda ids: {"1": ["spend_total"]}
    )
    provider = _Provider(json.dumps(_spec()))
    gateway = _Gateway()

    designed = b_bind.design_step(
        provider, gateway, DESIGN, PROMPTS, tag="ab12cd", image_paths=[DESIGN_IMAGE]
    )

    assert provider.calls[0]["image_paths"] == [DESIGN_IMAGE]
    assert gateway.calls == ["list_databases"]
    assert designed.databases == DATABASES
    assert designed.spec["views"][0]["name"] == "spend_total_ab12cd"
    assert designed.renamed
    assert designed.problems == []
    assert designed.cost_usd == 0.5


def test_the_design_step_reports_an_image_it_never_opened(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(b_bind, "taken_dataset_names", lambda ids: {})
    provider = _Provider(
        json.dumps(_spec()), name="claude_agent_sdk", usage={"input_tokens": 2}
    )
    designed = b_bind.design_step(
        provider, _Gateway(), DESIGN, PROMPTS, tag="ab12cd", image_paths=[DESIGN_IMAGE]
    )
    assert "never opened" in designed.problems[0]


def test_the_build_step_never_sends_the_image(bindings: dict[str, Any]) -> None:
    provider = _Provider(json.dumps({"final": bindings}))
    designed = DesignedData(spec=_spec(), databases=DATABASES, taken={"1": []})

    result = b_bind.build_step(provider, _Gateway(), DESIGN, designed, PROMPTS)

    assert provider.calls[0]["image_paths"] is None
    assert result.final["dashboard_name"] == "database_spend_multi_cloud"
