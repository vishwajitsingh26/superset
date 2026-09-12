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
"""What the user is told about the data stage B built.

There is nothing left to approve: stage B creates its own tables so it can run
a view's SQL against them, so by the time this runs the datasets exist. The
check that matters is that the user is told, and told the part that costs them
something -- the numbers came from the design, not their warehouse.
"""

from __future__ import annotations

from typing import Any

from superset.design_to_dashboard.runner import announce_datasets


class _Session:
    """Records what the run published."""

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def publish(self, kind: str, **payload: Any) -> None:
        self.events.append({"kind": kind, **payload})


def _binding_set(**overrides: Any) -> dict[str, Any]:
    return {
        "fact_tables": [
            {
                "name": "database_spend_by_day",
                "dataset_id": 24,
                "grain": "one row per day per provider",
                "row_count": 60,
            },
            {
                "name": "database_coverage",
                "dataset_id": 25,
                "grain": "one row per instance family per cloud",
                "row_count": 3,
            },
        ],
        "views": [{"name": "spend_by_provider", "dataset_id": 31}],
        **overrides,
    }


def test_the_user_is_told_what_was_built() -> None:
    session = _Session()

    announce_datasets(session, _binding_set())

    assert len(session.events) == 1
    event = session.events[0]
    assert event["kind"] == "datasets_created"
    assert "2 table(s) and 1 view(s)" in event["label"]


def test_the_label_says_the_numbers_are_not_the_users() -> None:
    """The one thing a reviewer has to know before trusting a figure."""
    session = _Session()

    announce_datasets(session, _binding_set())

    assert "not your data" in session.events[0]["label"]


def test_each_table_is_named_with_its_grain_and_size() -> None:
    session = _Session()

    announce_datasets(session, _binding_set())

    detail = session.events[0]["detail"]
    assert "database_spend_by_day — one row per day per provider, 60 row(s)" in detail
    assert "database_coverage" in detail


def test_the_row_total_is_reported() -> None:
    session = _Session()

    announce_datasets(session, _binding_set())

    assert session.events[0]["total_rows"] == 63


def test_a_table_with_no_grain_still_reads() -> None:
    session = _Session()

    announce_datasets(
        session, _binding_set(fact_tables=[{"name": "x", "dataset_id": 1}])
    )

    assert "no grain given" in session.events[0]["detail"]


def test_nothing_built_says_nothing() -> None:
    """A design served entirely by the shared dataset publishes no event."""
    session = _Session()

    announce_datasets(session, {"fact_tables": [], "views": []})

    assert session.events == []


def test_announcing_never_blocks() -> None:
    """It cannot ask, so it cannot cancel: there is no `ask` to call."""
    session = _Session()

    announce_datasets(session, _binding_set())

    assert not hasattr(session, "ask"), "the stub has no ask, and none was needed"
