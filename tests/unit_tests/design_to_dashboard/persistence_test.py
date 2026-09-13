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
"""Whether a run outlives the process that started it.

Written after a restart lost a run that had already spent twenty minutes
reading a design and binding its data.
"""

from __future__ import annotations

from typing import Any

import pytest

from superset.design_to_dashboard import persistence, session_store


@pytest.fixture
def store(tmp_path: Any, app_context: Any) -> Any:
    """A real database, on disk, addressed by url like the live one is."""
    from flask import current_app

    current_app.config["DESIGN_TO_DASHBOARD_PERSISTENCE"] = {
        "enabled": True,
        "url": f"sqlite:///{tmp_path}/runs.db",
        "schema": "main",  # sqlite's own schema; the DDL is otherwise identical
    }
    assert persistence.ensure_ready()
    return persistence


def _session(session_id: str = "run-1", user_id: int = 7) -> session_store.Session:
    session = session_store.Session(id=session_id, user_id=user_id)
    session.requirement = "Rebuild this dashboard"
    session.status = "running"
    session.events = [{"type": "stage_complete", "stage": "A"}]
    return session


def test_a_run_survives_the_process_that_made_it(store: Any) -> None:
    session = _session()
    session.save_stage("A", {"regions": [{"n": 1, "role": "kpi"}]})

    back = store.load_run("run-1")
    assert back is not None
    assert back["requirement"] == "Rebuild this dashboard"
    assert back["stages"]["A"]["regions"][0]["role"] == "kpi"


def test_each_stage_is_stored_separately(store: Any) -> None:
    """A resume wants the finished stages, not one blob to re-parse."""
    session = _session()
    session.save_stage("A", {"regions": []})
    session.save_stage("B", {"datasets": ["a"]})
    assert sorted(store.load_run("run-1")["stages"]) == ["A", "B"]


def test_rerunning_a_stage_replaces_its_output(store: Any) -> None:
    """Stage C replans in place, so a second attempt must not duplicate."""
    session = _session()
    session.save_stage("C", {"attempt": 1})
    session.save_stage("C", {"attempt": 2})
    assert store.load_run("run-1")["stages"]["C"]["attempt"] == 2


def test_a_run_caught_mid_stage_is_reported_interrupted(store: Any) -> None:
    """The worker is gone, so `running` would be a lie the UI acts on."""
    _session().save_stage("A", {"regions": []})
    session_store._sessions.pop("run-1", None)

    restored = session_store.get("run-1", user_id=7)
    assert restored is not None
    assert restored.status == "interrupted"
    assert sorted(restored.stages) == ["A"]


def test_a_finished_run_keeps_its_own_status(store: Any) -> None:
    session = _session()
    session.status = "done"
    session.save()
    session_store._sessions.pop("run-1", None)
    restored = session_store.get("run-1", user_id=7)
    assert restored is not None
    assert restored.status == "done"


def test_a_restored_run_still_belongs_to_its_owner(store: Any) -> None:
    _session().save()
    session_store._sessions.pop("run-1", None)
    assert session_store.get("run-1", user_id=99) is None


def test_an_unknown_run_is_not_invented(store: Any) -> None:
    assert store.load_run("never-existed") is None
    assert session_store.get("never-existed", user_id=7) is None


def test_runs_are_listed_for_their_owner_only(store: Any) -> None:
    _session("run-1", user_id=7).save()
    _session("run-2", user_id=7).save()
    _session("run-3", user_id=8).save()
    assert {r["session_id"] for r in store.list_runs(7)} == {"run-1", "run-2"}
    assert {r["session_id"] for r in store.list_runs(8)} == {"run-3"}


# --- storage must never be the thing that kills a run ------------------------


def test_storage_off_writes_nothing_and_raises_nothing(app_context: Any) -> None:
    from flask import current_app

    current_app.config["DESIGN_TO_DASHBOARD_PERSISTENCE"] = {"enabled": False}
    assert not persistence.enabled()
    session = _session("quiet-run")
    session.save()
    session.save_stage("A", {"regions": []})
    assert persistence.load_run("quiet-run") is None
    assert persistence.list_runs(7) == []


def test_an_unreachable_store_does_not_raise(app_context: Any) -> None:
    """Forty minutes of work is not traded for a write that timed out."""
    from flask import current_app

    current_app.config["DESIGN_TO_DASHBOARD_PERSISTENCE"] = {
        "enabled": True,
        "url": "postgresql://nobody:nobody@127.0.0.1:1/nothing",
        "schema": "main",
    }
    assert not persistence.ensure_ready()
    _session("doomed").save()  # must not raise
    assert persistence.load_run("doomed") is None


def test_persistence_on_with_no_destination_is_inert(app_context: Any) -> None:
    from flask import current_app

    current_app.config["DESIGN_TO_DASHBOARD_PERSISTENCE"] = {"enabled": True}
    _session("nowhere").save()
    assert persistence.load_run("nowhere") is None


@pytest.mark.parametrize("name", ["d2d runs", "d2d-runs", "DROP TABLE x", "1runs"])
def test_a_schema_name_is_validated_not_escaped(name: str, app_context: Any) -> None:
    """The name is interpolated into DDL, so it can only ever be an identifier."""
    from flask import current_app

    current_app.config["DESIGN_TO_DASHBOARD_PERSISTENCE"] = {
        "enabled": True,
        "schema": name,
    }
    with pytest.raises(ValueError, match="invalid persistence schema"):
        persistence.schema()


def test_an_unset_schema_falls_back_to_the_default(app_context: Any) -> None:
    from flask import current_app

    current_app.config["DESIGN_TO_DASHBOARD_PERSISTENCE"] = {"enabled": True}
    assert persistence.schema() == persistence.DEFAULT_SCHEMA


def test_answering_a_question_clears_it_from_storage(store: Any) -> None:
    """Otherwise a run busy working reads back as still waiting.

    The row kept the question until the next stage boundary, so a run three
    minutes into building plugins still looked like it wanted approval it had
    already been given.
    """
    import threading

    session = _session("gated")

    def answer_it() -> None:
        while session.pending is None:
            pass
        session.answer({"approved": True})

    threading.Thread(target=answer_it, daemon=True).start()
    session.ask("plugins", {"label": "approve to continue"}, timeout=10)

    stored = store.load_run("gated")
    assert stored is not None
    assert stored["pending"] is None
    assert stored["status"] == "running"


def test_a_stage_starting_is_written_down(store: Any) -> None:
    """A stage boundary is too coarse for the timeline.

    Stage F ran for twenty minutes and stage D for three, and the whole time
    storage still held the plugin review that came before them -- so a reopened
    run looked like it had gone backwards to a gate it had already passed.
    """
    session = _session("live")
    session.publish("stage_start", stage="F", label="Building 4 plugin(s)")

    stored = store.load_run("live")
    assert stored is not None
    assert stored["events"][-1]["label"] == "Building 4 plugin(s)"


def test_detail_events_do_not_each_cost_a_write(store: Any) -> None:
    """A run publishes thousands of these, inside every stage's inner loop."""
    session = _session("chatty")
    session.publish("stage_start", stage="D", label="Configuring")
    before = store.load_run("chatty")
    assert before is not None

    for _ in range(50):
        session.publish("tool_call", name="execute_sql")

    after = store.load_run("chatty")
    assert after is not None
    assert len(after["events"]) == len(before["events"])


def test_the_terminal_event_is_always_stored(store: Any) -> None:
    session = _session("finished")
    session.status = "done"
    session.publish("done", label="Built your dashboard")

    stored = store.load_run("finished")
    assert stored is not None
    assert stored["events"][-1]["type"] == "done"


def test_a_run_stored_at_a_gate_does_not_come_back_asking(store: Any) -> None:
    """The question belongs to the worker that asked it.

    A run written down while waiting comes back still showing its gate, and
    answering posts to nobody: the reply unblocks a thread that no longer
    exists. The page looks live and accepts clicks that do nothing, and there
    is no way to start over because the gate never clears.
    """
    session = _session("gated-then-died")
    session.status = "waiting"
    session.pending = {"kind": "plugins", "label": "approve to continue"}
    session.save()
    session_store._sessions.pop("gated-then-died", None)

    restored = session_store.get("gated-then-died", user_id=7)
    assert restored is not None
    assert restored.status == "interrupted"
    assert restored.pending is None


def test_a_run_that_finished_keeps_saying_so(store: Any) -> None:
    """Only a finished run has no worker still owing it something."""
    for status in ("done", "failed", "cancelled"):
        session = _session(f"ended-{status}")
        session.status = status
        session.save()
        session_store._sessions.pop(f"ended-{status}", None)
        restored = session_store.get(f"ended-{status}", user_id=7)
        assert restored is not None
        assert restored.status == status


def test_a_run_stored_mid_stage_is_interrupted(store: Any) -> None:
    session = _session("mid-stage")
    session.status = "running"
    session.save()
    session_store._sessions.pop("mid-stage", None)
    restored = session_store.get("mid-stage", user_id=7)
    assert restored is not None
    assert restored.status == "interrupted"


# --- photographs of new plugins wait for a passing dashboard ------------------


def test_new_plugins_are_not_photographed_for_a_dashboard_that_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The photograph becomes the plugin's picture in every later run.

    A plugin from a dashboard that did not look like its design is exactly the
    one whose picture should not be offered to stage C as a match.
    """
    from superset.design_to_dashboard import runner

    taken: list[Any] = []
    monkeypatch.setattr(
        runner, "_photograph_new_plugins", lambda s, p, r=None: taken.append(p)
    )
    session = _session("photo-gate")
    plan = {"decisions": [{"viz_type": "custom_card", "built_by_stage_f": True}]}

    runner._photograph_if_approved(session, plan, "needs_improvement")
    assert taken == []
    assert session.events[-1]["type"] == "thumbnails_skipped"

    runner._photograph_if_approved(session, plan, "pass")
    assert taken == [plan]


def test_a_run_that_built_no_plugins_is_silent_about_photographs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from superset.design_to_dashboard import runner

    monkeypatch.setattr(runner, "_photograph_new_plugins", lambda s, p, r=None: None)
    session = _session("no-plugins")
    before = len(session.events)
    runner._photograph_if_approved(session, {"decisions": []}, "fail")
    assert len(session.events) == before
