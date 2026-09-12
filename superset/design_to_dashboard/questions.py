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
"""Question hygiene for the one place the run stops to ask.

Stage C asks, once, after it has resolved the whole page: a question is only
worth the user's attention when someone knows what it changes, and until the
page is resolved nobody does. This module is what makes that batch usable --
ids the UI can key an answer to, near-duplicates removed, and a cap so a long
design does not become an interview.

It was a stage of its own until the pipeline changed around it. Running
between B and C, it asked about data that stage B now builds, about chrome
that no longer decides anything, and about fidelity in the abstract, because
nothing had been decided yet for it to be concrete about.
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


# The user answers in a UI that keys each answer by the question's `id`. A
# question without one loses its answer; two questions sharing one silently
# overwrite each other. Both happened in run ac369eb5, where eight questions
# produced seven answers and one arrived keyed "undefined".
#
# The budget scales with the design, because a seventeen-region page has more
# that can genuinely be ambiguous than a six-region one, and a fixed cap turns
# the surplus into silent assumptions -- the opposite of what this stage is for.


# Two words in ten differing is the same question rephrased; half the words
# differing is a different question about the same thing.
_SAME_QUESTION = 0.6
_NOISE = frozenset(
    "a an the is are was were be been do does did or and to of in on for it its "
    "this that these those i you should would could can will shall me my your "
    "with as at by from if so than then there here what which who whom how why "
    "when where not no yes but also they them their".split()
)


def _words(text: str) -> set[str]:
    """The distinctive words of a question, for comparing two of them."""
    return {
        word
        for word in re.findall(r"[a-z0-9_]+", text.lower())
        if word not in _NOISE and len(word) > 2
    }


def _detail(question: dict[str, Any]) -> int:
    """How much a question gives the user to decide with."""
    return sum(
        1
        for key in ("why_it_matters", "why_blocking", "default", "options", "topic")
        if question.get(key)
    )


def _same(left: dict[str, Any], right: dict[str, Any]) -> bool:
    """Whether two questions ask the same thing.

    Stage B raises a blocking question per unavailable binding and clarify
    raises its own, having been shown stage B's. Nothing told it not to restate
    them, so the user was asked about the same card twice in one batch -- which
    reads as the system having lost track of itself.
    """
    left_region = str(left.get("region_id") or "").strip()
    right_region = str(right.get("region_id") or "").strip()
    if left_region and left_region == right_region:
        return True
    left_words = _words(str(left.get("question") or ""))
    right_words = _words(str(right.get("question") or ""))
    if not left_words or not right_words:
        return False
    overlap = len(left_words & right_words) / len(left_words | right_words)
    return overlap >= _SAME_QUESTION


def _dedupe(questions: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    """Collapse questions that ask the same thing, keeping the fuller one."""
    kept: list[dict[str, Any]] = []
    notes: list[str] = []
    for question in questions:
        for index, existing in enumerate(kept):
            if not _same(existing, question):
                continue
            notes.append(
                "dropped a duplicate question about "
                f"{question.get('region_id') or 'the same subject'}"
            )
            if _detail(question) > _detail(existing):
                # Keep whichever gives the user more to decide with, but in the
                # position the first one held: order is impact ranking.
                kept[index] = question
            break
        else:
            kept.append(question)
    return kept, notes


def normalise_questions(payload: dict[str, Any]) -> list[str]:
    """Give every question a usable id and drop the repeats, in place.

    Nothing is capped. Stage C is asked once, after it has resolved the page,
    and every question it raises is an ambiguity that would otherwise be
    decided by guessing -- dropping the tail of that list does not save the
    user attention, it spends it later on a dashboard built on assumptions.
    A design with thirty ambiguous sections has thirty things worth asking.

    Repaired rather than rejected: the questions themselves are good, and
    failing the stage would cost the whole planning pass over a missing field.
    """
    questions = [q for q in (payload.get("questions") or []) if isinstance(q, dict)]
    questions, duplicates = _dedupe(questions)
    payload["questions"] = questions
    notes: list[str] = list(duplicates)

    # Keep the ids the model chose wherever they are usable, so an answer still
    # names something meaningful; only the broken ones are replaced.
    taken = {
        str(q.get("id") or "").strip()
        for q in questions
        if str(q.get("id") or "").strip()
    }
    used: set[str] = set()
    counter = 1
    for position, question in enumerate(questions, 1):
        given = str(question.get("id") or "").strip()
        if given and given not in used:
            used.add(given)
            continue
        while f"q{counter}" in taken or f"q{counter}" in used:
            counter += 1
        replacement = f"q{counter}"
        notes.append(
            f"question {position} had id {given or None!r}; using {replacement!r}"
        )
        question["id"] = replacement
        used.add(replacement)

    payload["questions"] = questions
    return notes
