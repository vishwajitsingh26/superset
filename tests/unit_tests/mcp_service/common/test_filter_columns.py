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
"""The filter whitelists, against the models they filter.

Each `*Filter.col` is a hand-maintained `Literal` while the DAO resolves the
column by reflection, so the two can disagree in both directions. A column in
the `Literal` the DAO cannot resolve is accepted by pydantic and then raises
from `apply_column_operators` at query time -- a runtime failure out of a list
that reads as validated. Note that "what the DAO can resolve" is wider than the
model: `owner` and `favorite` are not columns, they are subqueries the DAO
strips out before delegating, and it declares them alongside its reflection.

The other direction is not an error but it is a cost: `get_schema` reports the
reflected columns, so a caller that follows the documentation can be refused by
the tool. That is what happened to `list_charts(filters=[{"col":
"datasource_id"}])`, which was rejected on every call in every run.
"""

from __future__ import annotations

from typing import Any

import pytest


def _filters() -> list[tuple[str, Any, Any]]:
    from superset.daos.chart import ChartDAO
    from superset.daos.dashboard import DashboardDAO
    from superset.daos.database import DatabaseDAO
    from superset.daos.dataset import DatasetDAO
    from superset.mcp_service.chart.schemas import ChartFilter
    from superset.mcp_service.dashboard.schemas import DashboardFilter
    from superset.mcp_service.database.schemas import DatabaseFilter
    from superset.mcp_service.dataset.schemas import DatasetFilter

    return [
        ("chart", ChartFilter, ChartDAO),
        ("dataset", DatasetFilter, DatasetDAO),
        ("database", DatabaseFilter, DatabaseDAO),
        ("dashboard", DashboardFilter, DashboardDAO),
    ]


def _allowed(filter_cls: Any) -> list[str]:
    return list(filter_cls.model_json_schema()["properties"]["col"]["enum"])


@pytest.mark.parametrize("label", ["chart", "dataset", "database", "dashboard"])
def test_every_allowed_column_can_actually_be_filtered(app: Any, label: str) -> None:
    """Otherwise the filter validates and then fails in the query."""
    name, filter_cls, dao = next(f for f in _filters() if f[0] == label)
    resolvable = set(dao.get_filterable_columns_and_operators())
    unresolvable = [col for col in _allowed(filter_cls) if col not in resolvable]
    assert not unresolvable, (
        f"{name} accepts columns {dao.__name__} cannot filter on: {unresolvable}"
    )


def test_charts_can_be_found_by_the_dataset_they_are_built_on(app: Any) -> None:
    """The lookup that decides reuse-or-build.

    Stage C asks what charts already exist on a dataset before deciding to
    scaffold a new plugin, and it holds a dataset id, not a name.
    """
    from superset.mcp_service.chart.schemas import ChartFilter

    assert "datasource_id" in _allowed(ChartFilter)


def test_datasets_can_be_found_by_the_database_they_live_in(app: Any) -> None:
    """The same shape one layer down: stage B holds a database id."""
    from superset.mcp_service.dataset.schemas import DatasetFilter

    assert "database_id" in _allowed(DatasetFilter)


def test_no_secret_is_filterable(app: Any) -> None:
    """A filter is an oracle: `password startswith 'a'` reads it one bit at a
    time. These must stay out of the whitelist however it is maintained."""
    from superset.mcp_service.common.schema_discovery import DATABASE_EXCLUDE_COLUMNS
    from superset.mcp_service.database.schemas import DatabaseFilter

    leaked = set(_allowed(DatabaseFilter)) & DATABASE_EXCLUDE_COLUMNS
    assert not leaked, f"filterable secrets: {sorted(leaked)}"
