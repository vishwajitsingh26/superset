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
"""Which proposed datasets a run may create, and which it must ask about."""

from __future__ import annotations

from typing import Any

import pytest

from superset.design_to_dashboard.runner import gate_datasets, RunCancelledError

DERIVED: dict[str, Any] = {
    "name": "sales_by_genre",
    "kind": "derived",
    "database_id": 1,
    "sql": "SELECT genre, SUM(global_sales) FROM sales GROUP BY genre",
    "region_ids": ["r07_sales:1"],
    "reason": "the master table has row-level sales; the card needs them by genre",
}
PLACEHOLDER: dict[str, Any] = {
    "name": "d2d_provider_spend",
    "kind": "placeholder",
    "database_id": 1,
    "rows": [["AWS", 1], ["GCP", 2]],
    "region_ids": ["r03_card:1"],
    "reason": "no table holds cloud spend",
}


class FakeSession:
    """Records what was asked and announced, and answers with `reply`."""

    def __init__(self, reply: dict[str, Any] | None = None) -> None:
        self.reply = reply or {}
        self.asked: list[tuple[str, dict[str, Any]]] = []
        self.published: list[tuple[str, dict[str, Any]]] = []

    def ask(self, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.asked.append((kind, payload))
        return self.reply

    def publish(self, event: str, **payload: Any) -> None:
        self.published.append((event, payload))


def test_derived_is_created_without_asking() -> None:
    """Nothing is written and the numbers are real, so there is nothing the
    user could act on by being asked."""
    session = FakeSession()
    assert gate_datasets(session, [DERIVED]) == [DERIVED]
    assert session.asked == []


def test_derived_is_announced() -> None:
    session = FakeSession()
    gate_datasets(session, [DERIVED])
    assert session.published[0][0] == "datasets_planned"


def test_placeholder_is_always_asked_about() -> None:
    session = FakeSession({"approved": True})
    gate_datasets(session, [DERIVED, PLACEHOLDER])
    assert len(session.asked) == 1
    assert session.asked[0][0] == "datasets"


def test_only_placeholders_are_put_to_the_user() -> None:
    session = FakeSession({"approved": True})
    gate_datasets(session, [DERIVED, PLACEHOLDER])
    assert session.asked[0][1]["datasets"] == [PLACEHOLDER]


def test_approval_creates_both_kinds() -> None:
    session = FakeSession({"approved": True})
    assert gate_datasets(session, [DERIVED, PLACEHOLDER]) == [DERIVED, PLACEHOLDER]


def test_declining_cancels_the_run() -> None:
    """Every section that needed one has no data, so there is no smaller
    dashboard to build."""
    session = FakeSession({"approved": False})
    with pytest.raises(RunCancelledError, match="Point me at a database"):
        gate_datasets(session, [DERIVED, PLACEHOLDER])


def test_a_reply_without_approved_declines() -> None:
    """The safe default: never write tables on an ambiguous answer."""
    session = FakeSession({"answers": {}})
    with pytest.raises(RunCancelledError):
        gate_datasets(session, [PLACEHOLDER])


def test_nothing_proposed_asks_nothing() -> None:
    session = FakeSession()
    assert gate_datasets(session, []) == []
    assert session.asked == []
    assert session.published == []
