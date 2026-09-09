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
"""In-memory session and event store for the Design-to-Dashboard chat.

Development-grade on purpose: sessions live in the process, so they are lost on
restart and are not shared across workers. Replacing this with the
``DesignSession``/``DesignPlan`` models is the step that makes the feature
deployable; the API surface here is shaped so that swap is local to this file.
"""

from __future__ import annotations

import queue
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

MAX_SESSIONS = 50


@dataclass
class Session:
    """One conversation: its uploaded design, its events, and its result."""

    id: str
    user_id: int
    created_at: float = field(default_factory=time.time)
    requirement: str = ""
    image_paths: list[str] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    queues: list[queue.Queue] = field(default_factory=list)
    status: str = "new"          # new | running | needs_input | done | failed
    result: dict[str, Any] | None = None
    error: str | None = None
    artifacts: dict[str, Any] = field(default_factory=dict)
    # Live reasoning for the stage in flight. Deliberately a single replaceable
    # buffer rather than an event per delta: one stage can emit thousands of
    # thinking tokens, and storing each as an event would bloat the session and
    # be replayed on every reconnect.
    thinking: str = ""
    thinking_stage: str = ""
    lock: threading.Lock = field(default_factory=threading.Lock)

    # --- conversation gates -------------------------------------------------
    # A run pauses here and waits for the user. Questions are only ever asked
    # while planning; once the plan is approved the run executes without
    # stopping, so nothing is written while an answer is outstanding.
    pending: dict[str, Any] | None = None
    reply: dict[str, Any] | None = None
    _replied: threading.Event = field(default_factory=threading.Event)

    def ask(self, kind: str, payload: dict[str, Any], timeout: int = 3600) -> dict[str, Any]:
        """Publish a question and block the worker until the user answers.

        ``kind`` is ``questions`` (stage B could not bind something),
        ``clarify`` (open choices such as embedded mode) or ``plan`` (approve
        the plan before anything is created).
        """
        self.pending = {"kind": kind, **payload}
        self.status = "waiting"
        self._replied.clear()
        self.publish("awaiting_input", kind=kind, **payload)
        if not self._replied.wait(timeout=timeout):
            raise TimeoutError(f"no answer to {kind!r} within {timeout}s")
        answer = self.reply or {}
        self.pending = None
        self.reply = None
        self.status = "running"
        self.publish("input_received", kind=kind, answer=answer)
        return answer

    def answer(self, payload: dict[str, Any]) -> bool:
        """Deliver the user's answer and release the waiting worker."""
        if self.pending is None:
            return False
        self.reply = payload
        self._replied.set()
        return True

    def set_thinking(self, stage: str, text: str) -> None:
        with self.lock:
            self.thinking_stage = stage
            self.thinking = text[-8000:]

    def take_thinking(self) -> str:
        """Return the current reasoning and clear the live buffer.

        The live buffer is for the stage in flight; the text itself is worth
        keeping, so it is attached to that stage's completion event rather than
        discarded.
        """
        with self.lock:
            text = self.thinking
            self.thinking = ""
            self.thinking_stage = ""
        return text

    def clear_thinking(self) -> None:
        with self.lock:
            self.thinking = ""
            self.thinking_stage = ""

    def snapshot(self, since: int = 0) -> dict[str, Any]:
        """Events after ``since``, plus the live thinking buffer.

        Returning a cursor lets the client poll frequently without re-sending
        the whole history each time.
        """
        with self.lock:
            events = self.events[since:]
            return {
                "events": events,
                "cursor": len(self.events),
                "thinking": self.thinking,
                "thinking_stage": self.thinking_stage,
            }

    def publish(self, event_type: str, **payload: Any) -> None:
        """Record an event and fan it out to every attached listener."""
        event = {"type": event_type, "at": time.time(), **payload}
        with self.lock:
            self.events.append(event)
            listeners = list(self.queues)
        for listener in listeners:
            try:
                listener.put_nowait(event)
            except queue.Full:  # pragma: no cover - a slow client is dropped
                pass

    def attach(self) -> queue.Queue:
        """Attach a listener, replaying everything that already happened.

        Replay matters: the browser opens the event stream after the run has
        started, and without it the first stages would be invisible.
        """
        listener: queue.Queue = queue.Queue(maxsize=1000)
        with self.lock:
            for event in self.events:
                listener.put_nowait(event)
            self.queues.append(listener)
        return listener

    def detach(self, listener: queue.Queue) -> None:
        with self.lock:
            if listener in self.queues:
                self.queues.remove(listener)


_sessions: dict[str, Session] = {}
_store_lock = threading.Lock()


def create(user_id: int) -> Session:
    session = Session(id=str(uuid.uuid4()), user_id=user_id)
    with _store_lock:
        _sessions[session.id] = session
        # Bound memory: drop the oldest sessions once past the cap.
        if len(_sessions) > MAX_SESSIONS:
            for stale in sorted(_sessions.values(), key=lambda s: s.created_at)[
                : len(_sessions) - MAX_SESSIONS
            ]:
                _sessions.pop(stale.id, None)
    return session


def get(session_id: str, user_id: int | None = None) -> Session | None:
    session = _sessions.get(session_id)
    if session is None:
        return None
    # A session belongs to the user who created it.
    if user_id is not None and session.user_id != user_id:
        return None
    return session
