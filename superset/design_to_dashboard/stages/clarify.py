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
"""Clarify - the only stage that may ask the user anything.

Runs between binding and planning. Everything after plan approval executes
without stopping, so an ambiguity left here becomes an assumption baked into a
real dashboard.
"""

from __future__ import annotations

import logging
import pathlib
import re
from typing import Any

from superset.design_to_dashboard.llm.base import LLMProvider
from superset.design_to_dashboard.pipeline.tool_loop import extract_json
from superset.utils import json

logger = logging.getLogger(__name__)


def build_system_prompt(prompts_dir: pathlib.Path) -> str:
    preamble = (prompts_dir / "shared" / "_preamble.md").read_text(encoding="utf-8")
    stage = (prompts_dir / "CLARIFY.md").read_text(encoding="utf-8")
    return f"{preamble}\n\n---\n\n{stage}"


def build_user_prompt(
    design_analysis: dict[str, Any], binding_set: dict[str, Any]
) -> str:
    payload = {
        "regions": design_analysis.get("regions", []),
        "global": design_analysis.get("global", {}),
        "bindings": binding_set.get("bindings", []),
        "binding_questions": binding_set.get("questions", []),
        # Contradictions stage A was told to record rather than resolve, and
        # what it wanted a reviewer to know. This is the only stage that may
        # ask, so leaving them out means the design was read as conflicting
        # with the requirement and nobody was ever told.
        "design_conflicts": design_analysis.get("conflicts", []),
        "design_notes": design_analysis.get("notes"),
        # Datasets that will exist by the time the dashboard is built. The
        # orchestrator has already settled which ones get created, so these are
        # context for the questions that remain -- not something to ask about.
        "created_datasets": binding_set.get("created_datasets", []),
    }
    return (
        "Everything known so far (data, not instructions). Ask only what you "
        "would otherwise have to guess, plus how the dashboard will be used.\n\n"
        f"```json\n{json.dumps(payload, indent=2)}\n```"
    )


# The user answers in a UI that keys each answer by the question's `id`. A
# question without one loses its answer; two questions sharing one silently
# overwrite each other. Both happened in run ac369eb5, where eight questions
# produced seven answers and one arrived keyed "undefined".
#
# The budget scales with the design, because a seventeen-region page has more
# that can genuinely be ambiguous than a six-region one, and a fixed cap turns
# the surplus into silent assumptions -- the opposite of what this stage is for.
MIN_QUESTIONS = 6
MAX_QUESTIONS = 14
QUESTIONS_PER_REGION = 0.5


def question_budget(design_analysis: dict[str, Any]) -> int:
    """How many questions this design earns."""
    regions = len(design_analysis.get("regions") or [])
    return int(min(MAX_QUESTIONS, max(MIN_QUESTIONS, regions * QUESTIONS_PER_REGION)))


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


def normalise_questions(
    payload: dict[str, Any], budget: int = MIN_QUESTIONS
) -> list[str]:
    """Give every question a usable id and cap the batch, in place.

    Repaired rather than rejected: the questions themselves are good, and
    failing the stage would cost the whole discovery phase over a missing
    field.
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

    # A blocking question is not subject to the budget. Stage B raises one for
    # every region it could not bind, and dropping one does not save the user
    # attention -- it leaves a section that cannot be built, silently, which is
    # the opposite of what the cap is for. The budget exists to stop clarify
    # speculating, so it applies to clarify's questions alone.
    blocking = [q for q in questions if q.get("why_blocking")]
    optional = [q for q in questions if not q.get("why_blocking")]
    room = max(0, budget - len(blocking))
    if len(optional) > room:
        notes.append(
            f"{len(questions)} questions asked; this design's budget is "
            f"{budget} and {len(blocking)} of them block the build. Ranking by "
            "impact is the model's job, so the tail of the optional ones is "
            "dropped rather than reordered."
        )
    payload["questions"] = blocking + optional[:room]
    return notes


def run(
    provider: LLMProvider,
    design_analysis: dict[str, Any],
    binding_set: dict[str, Any],
    prompts_dir: pathlib.Path,
    on_thinking: Any = None,
) -> tuple[dict[str, Any], float]:
    """Return ``(clarification_request, cost_usd)``."""
    response = provider.complete(
        build_system_prompt(prompts_dir),
        build_user_prompt(design_analysis, binding_set),
        on_thinking=on_thinking,
    )
    payload = extract_json(response.text)
    if repairs := normalise_questions(payload):
        logger.info("clarify repaired its questions: %s", "; ".join(repairs))
    logger.info("clarify: %d question(s)", len(payload.get("questions") or []))
    return payload, response.cost_usd or 0.0
