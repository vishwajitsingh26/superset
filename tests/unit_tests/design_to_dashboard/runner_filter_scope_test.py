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
"""`filter_scope.question` was written and never called: `apply_plan`'s
`filter_scope_answer` sat on its hardcoded default on every run, whatever the
design actually showed. These tests are on the wiring in `runner.py`, not on
`filter_scope` itself -- its own module has that coverage already.
"""

from __future__ import annotations

from typing import Any

from superset.design_to_dashboard import filter_scope
from superset.design_to_dashboard.runner import resolve_filter_scope


class _Session:
    """A stand-in for `Session`: records what was published, answers what
    was asked."""

    def __init__(self, answer: dict[str, Any] | None = None) -> None:
        self.events: list[tuple[str, dict[str, Any]]] = []
        self.asked: list[tuple[str, dict[str, Any]]] = []
        self._answer = answer or {}

    def publish(self, kind: str, **fields: Any) -> None:
        self.events.append((kind, fields))

    def ask(self, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.asked.append((kind, payload))
        return self._answer


def _plan(*decisions: tuple[str, str, str | None]) -> dict[str, Any]:
    return {
        "decisions": [
            {
                "region_id": region_id,
                "decision": "new_plugin",
                "ref": ref,
                "plugin_archetype": archetype,
                "slice_name": region_id.replace("_", " ").title(),
            }
            for region_id, archetype, ref in decisions
        ]
    }


def _spec(region_id: str, ref: str, **params: Any) -> dict[str, Any]:
    return {"region_id": region_id, "ref": ref, "params_decoded": params}


def _design(**roles: str) -> dict[str, Any]:
    return {
        "regions": [
            {"region_id": region_id, "role": role} for region_id, role in roles.items()
        ]
    }


# A page with no ambiguity: no filter control at all, so `filter_scope`
# has nothing to ask about.
PLAIN_PLAN = _plan(("r04_card", "viz", "c4"), ("r11_table", "table", "c11"))
PLAIN_SPECS = [_spec("r04_card", "c4"), _spec("r11_table", "c11")]
PLAIN_DESIGN = _design(r04_card="kpi", r11_table="table")

# A page that draws the exact ambiguity `filter_scope` exists to catch: a
# filter control beside a chart that plots a trend over time.
AMBIGUOUS_PLAN = _plan(("r02_filter", "filter_widget", "c2"), ("r08_bars", "viz", "c8"))
AMBIGUOUS_SPECS = [
    _spec("r02_filter", "c2"),
    _spec("r08_bars", "c8", x_axis="usage_month"),
]
AMBIGUOUS_DESIGN = _design(r02_filter="filter", r08_bars="chart")


def test_no_ambiguity_means_no_ask_and_the_module_default() -> None:
    """The common case: nothing is asked, and the answer is the same default
    `apply_plan` always used before this wiring existed."""
    assert filter_scope.question(PLAIN_PLAN, PLAIN_SPECS, PLAIN_DESIGN) is None

    session = _Session()
    scope = resolve_filter_scope(session, PLAIN_PLAN, PLAIN_SPECS, PLAIN_DESIGN)

    assert scope == filter_scope.SCOPE_EXCEPT_TRENDS
    assert session.asked == []
    assert session.events == []


def test_an_ambiguous_design_asks_and_the_answer_reaches_the_caller() -> None:
    """A real ambiguity blocks on `session.ask`, and the reply -- in the
    envelope shape `session.ask` actually returns -- becomes the scope
    `apply_plan` is called with."""
    assert filter_scope.question(AMBIGUOUS_PLAN, AMBIGUOUS_SPECS, AMBIGUOUS_DESIGN)

    session = _Session(
        answer={"answers": {filter_scope.SCOPE_QUESTION_ID: "Yes, filter every chart"}}
    )
    scope = resolve_filter_scope(
        session, AMBIGUOUS_PLAN, AMBIGUOUS_SPECS, AMBIGUOUS_DESIGN
    )

    assert scope == filter_scope.SCOPE_ALL
    assert len(session.asked) == 1
    kind, payload = session.asked[0]
    assert kind == "questions"
    asked_questions = payload["questions"]
    assert len(asked_questions) == 1
    assert asked_questions[0]["id"] == filter_scope.SCOPE_QUESTION_ID
    # A stage_start was published so the UI shows something is happening
    # while this one extra question waits on an answer.
    assert any(kind == "stage_start" for kind, _fields in session.events)


def test_declining_to_filter_everything_keeps_trends_excluded() -> None:
    """The default option on the question itself: leave the trend charts out."""
    session = _Session(
        answer={
            "answers": {
                filter_scope.SCOPE_QUESTION_ID: (
                    "No, leave them out so they keep their full history"
                )
            }
        }
    )
    scope = resolve_filter_scope(
        session, AMBIGUOUS_PLAN, AMBIGUOUS_SPECS, AMBIGUOUS_DESIGN
    )

    assert scope == filter_scope.SCOPE_EXCEPT_TRENDS
