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
"""Whether a generated plugin actually compiled, and what to do when it did not.

Stage F's own checks are regex over the scaffold's text: they catch a wrong
import path and cannot catch a property invented on a type. The compiler sees
those, and already did -- into a log nothing read, while the run reported the
plugin as built.
"""

from __future__ import annotations

import pathlib
import time

import pytest

from superset.design_to_dashboard.frontend import _compile_verdict, compile_errors
from superset.design_to_dashboard.runner import _plugins_in_errors, _restart_label
from superset.design_to_dashboard.stages.f_scaffold import _build_failure_note

# Taken verbatim from a real dev-server log, after a run that reported success.
BROKEN_BUILD = """
ERROR in ./plugins/plugin-chart-custom-card-panel-558b06/src/plugin/index.ts:40:3
TS2353: Object literal may only specify known properties, and 'skipDataFetch'
does not exist in type 'ChartMetadataConfig'.
    40 |   skipDataFetch: true,

ERROR in ./plugins/plugin-chart-custom-forecast-line-chart-558b06/src/plugin/\
buildQuery.ts:38:38
TS2345: Types of property 'row_limit' are incompatible.
  Type 'string' is not assignable to type 'number'.

Found 2 errors in 19648 ms.
"""

DIRECTORIES = {
    "custom_card_panel": (
        "superset-frontend/plugins/plugin-chart-custom-card-panel-558b06"
    ),
    "custom_metric_table": (
        "superset-frontend/plugins/plugin-chart-custom-metric-table-558b06"
    ),
}


# --- reading the compiler's verdict ------------------------------------------


def test_every_error_block_is_parsed() -> None:
    errors = compile_errors(BROKEN_BUILD)
    assert len(errors) == 2
    assert "card-panel" in errors[0]["file"]
    assert "forecast-line-chart" in errors[1]["file"]


def test_the_error_detail_survives() -> None:
    """The detail is what the repair pass has to work from."""
    assert "skipDataFetch" in compile_errors(BROKEN_BUILD)[0]["detail"]


def test_a_clean_build_reports_nothing() -> None:
    assert compile_errors("webpack 5.105.4 compiled successfully in 4132 ms") == []


def test_only_this_restart_is_read(tmp_path: pathlib.Path) -> None:
    """The log is appended to across runs and still holds every old failure."""
    log = tmp_path / "dev.log"
    log.write_text("ERROR in ./old/thing.ts\nFound 1 error in 10 ms.\n")
    offset = log.stat().st_size
    log.write_text(log.read_text() + "webpack compiled successfully in 200 ms\n")
    verdict = _compile_verdict(log, offset, time.time() + 5)
    assert verdict["compiled"] is True
    assert verdict["errors"] == []


def test_a_failure_after_the_offset_is_reported(tmp_path: pathlib.Path) -> None:
    log = tmp_path / "dev.log"
    log.write_text("old output\n")
    offset = log.stat().st_size
    log.write_text(log.read_text() + BROKEN_BUILD)
    verdict = _compile_verdict(log, offset, time.time() + 5)
    assert verdict["compiled"] is False
    assert len(verdict["errors"]) == 2


def test_no_verdict_yet_is_not_a_pass(tmp_path: pathlib.Path) -> None:
    """Unknown must not read as success -- that was the original bug."""
    log = tmp_path / "dev.log"
    log.write_text("starting up\n")
    verdict = _compile_verdict(log, log.stat().st_size, time.time() + 2)
    assert verdict["compiled"] is None


# --- blaming the right plugin ------------------------------------------------


def test_only_the_plugin_named_in_an_error_is_repaired() -> None:
    blamed = _plugins_in_errors(compile_errors(BROKEN_BUILD), DIRECTORIES)
    assert blamed == {"custom_card_panel"}


def test_an_error_elsewhere_blames_no_plugin() -> None:
    """A broken build this run did not cause must not trigger a rewrite."""
    errors = [{"file": "./src/setup/setupPluginsExtra.ts", "detail": "x"}]
    assert _plugins_in_errors(errors, DIRECTORIES) == set()


# --- the label stops claiming success ----------------------------------------


@pytest.mark.parametrize(
    "outcome,expected",
    [
        ({"restarted": True, "compiled": True}, "live"),
        ({"restarted": True, "compiled": False}, "does not compile"),
        ({"restarted": True, "compiled": None}, "could not confirm"),
        ({"restarted": False}, "Restart your dev server"),
    ],
)
def test_restart_label_reports_the_compile_not_the_restart(
    outcome: dict[str, object], expected: str
) -> None:
    assert expected in _restart_label(outcome)


# --- what the author is told -------------------------------------------------


def test_the_repair_note_carries_every_error() -> None:
    note = _build_failure_note(compile_errors(BROKEN_BUILD))
    assert "card-panel" in note
    assert "forecast-line-chart" in note
    assert "skipDataFetch" in note


def test_the_repair_note_closes_the_any_escape_hatch() -> None:
    """`any` is rejected by this stage, so it cannot be the way out."""
    assert "`any`" in _build_failure_note(compile_errors(BROKEN_BUILD))


def test_no_errors_means_no_note() -> None:
    assert _build_failure_note([]) == ""
