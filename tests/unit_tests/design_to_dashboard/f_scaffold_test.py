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
from typing import Any

import pytest

from superset.design_to_dashboard import plugin_writer
from superset.design_to_dashboard.frontend import (
    _compile_verdict,
    compile_errors,
    typecheck_errors,
)
from superset.design_to_dashboard.llm.base import LLMError
from superset.design_to_dashboard.runner import _plugins_in_errors, _restart_label
from superset.design_to_dashboard.stages.c_resolve import design_system
from superset.design_to_dashboard.stages.f_scaffold import (
    _broken_rules,
    _build_failure_note,
    _check_exemplar,
    _chrome_note,
    _unusual_note,
    resolve_children,
    validate,
)
from superset.utils import json

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


# --- what stage A observed, reaching the author ------------------------------
#
# Stage A records a tab strip in `frame` and a toggle in `controls`. The reader
# these replace scanned `interactions` for the substring "tab", which is the one
# field that information was deliberately moved out of.


def test_a_tab_frame_is_read_from_frame_not_prose() -> None:
    note = _chrome_note({"frame": "tabs", "interactions": []})
    assert "tab strip" in note


def test_a_toggle_frame_is_handled_at_all() -> None:
    """`frame: "toggle"` had no branch, so it produced nothing."""
    assert "toggle" in _chrome_note({"frame": "toggle"}).lower()


def test_a_table_in_interactions_is_not_a_tab_strip() -> None:
    """ "tab" matches "table" -- a detail table was read as a tab switcher."""
    note = _chrome_note(
        {"frame": "none", "interactions": ["clicking a row opens a detail table"]}
    )
    assert note == ""


def test_a_leaf_card_is_told_about_its_own_controls() -> None:
    """The old reader ran only for wrappers, so a card's toggles were lost."""
    note = _chrome_note(
        {
            "controls": [
                {
                    "kind": "view_toggle",
                    "options": ["list", "chart", "grid"],
                    "active": "list",
                    "icon": "three stacked lines; three vertical bars; a 3x3 grid",
                    "position": "top-right of the section header",
                }
            ]
        }
    )
    assert "view_toggle" in note
    assert "list, chart, grid" in note
    assert "three stacked lines" in note
    assert "top-right" in note


def test_the_icon_description_is_marked_as_the_only_specification() -> None:
    note = _chrome_note({"controls": [{"kind": "expand", "icon": "outward arrows"}]})
    assert "outward arrows" in note
    assert "only specification" in note


def test_unseen_states_are_still_built() -> None:
    note = _chrome_note({"frame": "tabs"})
    assert "Coming soon" in note


def test_no_chrome_means_no_note() -> None:
    assert _chrome_note({"frame": "none", "controls": []}) == ""
    assert _chrome_note({}) == ""


def test_unusual_treatment_is_named_as_the_reason_to_build() -> None:
    note = _unusual_note(
        {
            "unusual_treatment": [
                "the Trend column draws a sparkline inside each cell",
                "category labels sit above each bar",
            ]
        }
    )
    assert "sparkline inside each cell" in note
    assert "category labels sit above each bar" in note


def test_nothing_unusual_means_no_note() -> None:
    assert _unusual_note({"unusual_treatment": []}) == ""
    assert _unusual_note({}) == ""


# --- one contract every parallel worker obeys --------------------------------


def test_the_contract_is_backfilled_from_what_stage_a_saw() -> None:
    """C is asked for chrome; when it omits it, A's observation still lands."""
    contract = design_system(
        {"design_system": {"palette": ["#111"]}},
        {"global": {"card_chrome": {"radius": "8px"}, "typography": {"value": "24px"}}},
    )
    assert contract["card_chrome"] == {"radius": "8px"}
    assert contract["typography"] == {"value": "24px"}
    assert contract["palette"] == ["#111"]


def test_stage_c_outranks_stage_a() -> None:
    """The contract is a decision; the observation is only the fallback."""
    contract = design_system(
        {"design_system": {"card_chrome": {"radius": "4px"}}},
        {"global": {"card_chrome": {"radius": "8px"}}},
    )
    assert contract["card_chrome"] == {"radius": "4px"}


def test_neither_stage_supplied_it() -> None:
    assert design_system({}, {}) == {}


# --- the compiler, which is no longer optional -------------------------------
#
# Stage F's own checks are regex over generated text. Only a type-checker sees
# an invented field on a type, and it used to be reachable only through a
# dev-server restart nobody had opted into.

TSC_OUTPUT = """
plugins/plugin-chart-custom-card-558b06/src/plugin/index.ts(40,3): error TS2353: \
Object literal may only specify known properties, and 'skipDataFetch' does not \
exist in type 'ChartMetadataConfig'.
plugins/plugin-chart-custom-forecast-line-chart-558b06/src/plugin/buildQuery.ts(22,5): \
error TS2322: Type 'string | number' is not assignable to type 'number'.
src/dashboard/Existing.tsx(9,1): error TS2304: Cannot find name 'unrelated'.
"""


def test_every_tsc_error_is_parsed() -> None:
    errors = typecheck_errors(TSC_OUTPUT)
    assert len(errors) == 3
    assert errors[0]["file"].endswith("src/plugin/index.ts")
    assert "skipDataFetch" in errors[0]["detail"]
    assert "line 40" in errors[0]["detail"]


def test_tsc_errors_blame_only_generated_plugins() -> None:
    """An unrelated file's error must not cost a plugin its section."""
    directories = {
        "custom_card": "superset-frontend/plugins/plugin-chart-custom-card-558b06",
        "custom_forecast": (
            "superset-frontend/plugins/plugin-chart-custom-forecast-line-chart-558b06"
        ),
        "custom_untouched": (
            "superset-frontend/plugins/plugin-chart-custom-untouched-558b06"
        ),
    }
    blamed = _plugins_in_errors(typecheck_errors(TSC_OUTPUT), directories)
    assert blamed == {"custom_card", "custom_forecast"}


def test_a_clean_typecheck_reports_nothing() -> None:
    assert typecheck_errors("") == []


# --- removal, so a plugin that will not compile leaves no trace --------------


def _write_fake_repo(root: pathlib.Path) -> dict[str, Any]:
    """A repo with one generated plugin already written and registered."""
    directory = "superset-frontend/plugins/plugin-chart-custom-card-558b06"
    (root / directory / "src" / "plugin").mkdir(parents=True)
    (root / directory / "src" / "plugin" / "index.ts").write_text("export {}")
    (root / "superset-frontend").mkdir(exist_ok=True)
    (root / "superset-frontend" / "package.json").write_text(
        '{\n  "dependencies": {\n'
        '    "@superset-ui/plugin-chart-custom-card-558b06": '
        '"file:./plugins/plugin-chart-custom-card-558b06",\n'
        '    "keep-me": "1.0.0"\n  }\n}\n'
    )
    setup = root / "superset-frontend" / "src" / "setup"
    setup.mkdir(parents=True)
    (setup / "setupPluginsExtra.ts").write_text(
        "import { CustomCardPlugin } from "
        "'@superset-ui/plugin-chart-custom-card-558b06';\n\n"
        "export default function setupPluginsExtra(): void {\n"
        "  new CustomCardPlugin().configure({ key: 'custom_card' }).register();\n"
        "}\n"
    )
    return {
        "viz_type": "custom_card",
        "directory": directory,
        "package_json_dependency": {
            "name": "@superset-ui/plugin-chart-custom-card-558b06",
            "spec": "file:./plugins/plugin-chart-custom-card-558b06",
        },
        "registration": {
            "import_line": (
                "import { CustomCardPlugin } from "
                "'@superset-ui/plugin-chart-custom-card-558b06';"
            ),
            "register_line": (
                "new CustomCardPlugin().configure({ key: 'custom_card' }).register();"
            ),
        },
    }


def test_removal_undoes_all_three_artifacts(tmp_path: pathlib.Path) -> None:
    """A registered plugin breaks every chart, not just its own section."""
    scaffold = _write_fake_repo(tmp_path)
    plugin_writer.remove(scaffold, tmp_path)

    assert not (tmp_path / scaffold["directory"]).exists()
    package = json.loads((tmp_path / "superset-frontend" / "package.json").read_text())
    assert "@superset-ui/plugin-chart-custom-card-558b06" not in package["dependencies"]
    assert package["dependencies"]["keep-me"] == "1.0.0"
    setup = (
        tmp_path / "superset-frontend" / "src" / "setup" / "setupPluginsExtra.ts"
    ).read_text()
    assert "CustomCardPlugin" not in setup
    assert "export default function setupPluginsExtra" in setup


def test_removal_refuses_a_directory_outside_the_plugin_tree(
    tmp_path: pathlib.Path,
) -> None:
    """The path comes from model output, so it is checked, not trusted."""
    (tmp_path / "superset").mkdir()
    (tmp_path / "superset" / "keep.py").write_text("x = 1")
    plugin_writer.remove({"viz_type": "evil", "directory": "superset"}, tmp_path)
    assert (tmp_path / "superset" / "keep.py").exists()


def test_removal_survives_a_repo_missing_the_files(tmp_path: pathlib.Path) -> None:
    """Best-effort: this runs when something has already gone wrong."""
    assert (
        plugin_writer.remove(
            {
                "viz_type": "custom_gone",
                "directory": (
                    "superset-frontend/plugins/plugin-chart-custom-gone-558b06"
                ),
                "package_json_dependency": {
                    "name": "@superset-ui/x",
                    "spec": "file:./x",
                },
            },
            tmp_path,
        )
        == []
    )


# --- the exemplar is held to the rules its output is held to -----------------
#
# The container exemplar set `skipDataFetch: true` while the stage prompt cited
# that exact field as a shipped build failure; base/ carried `as any` and
# literal colours and disabled the colour lint. A model reading the rule and
# the violation in the same context cannot choose between them.


def _exemplar(tmp_path: pathlib.Path, contents: str) -> pathlib.Path:
    (tmp_path / "src").mkdir(parents=True, exist_ok=True)
    (tmp_path / "src" / "Chart.tsx").write_text(contents)
    return tmp_path


@pytest.mark.parametrize(
    "source,expected",
    [
        ("const x = value as any;", "as any"),
        ("const x: any = value;", "`any` type"),
        ("const c = { color: '#2B2B2B' };", "literal colour"),
        ("const c = { color: 'rgba(0,0,0,0.1)' };", "literal colour"),
        (
            "/* eslint-disable theme-colors/no-literal-colors */\nconst a = 1;",
            "disables",
        ),
    ],
)
def test_an_exemplar_breaking_a_shared_rule_fails_fast(
    tmp_path: pathlib.Path, source: str, expected: str
) -> None:
    with pytest.raises(LLMError, match=expected):
        _check_exemplar(_exemplar(tmp_path, source))


def test_an_exemplar_inventing_a_metadata_field_fails_fast(
    tmp_path: pathlib.Path,
) -> None:
    with pytest.raises(LLMError, match="skipDataFetch"):
        _check_exemplar(
            _exemplar(tmp_path, "const metadata = { skipDataFetch: true };")
        )


def test_a_comment_naming_a_forbidden_construct_is_not_a_violation(
    tmp_path: pathlib.Path,
) -> None:
    """A rule that fires on its own documentation reports the wrong thing.

    This is how a note about an antd prop became a reported fault.
    """
    _check_exemplar(
        _exemplar(
            tmp_path,
            "// never write `as any`, and never a colour like '#2B2B2B'\n"
            "/* the theme-colors rule is never switched off in a plugin */\n"
            "const link = 'https://example.com/#abc123';\n"
            "const ok = 1;\n",
        )
    )


def test_a_computed_colour_is_not_a_literal() -> None:
    """`check-custom-rules.js` anchors on a string literal, so a colour built
    in a template literal is legitimate and must not be rejected."""
    assert not _broken_rules("return `rgb(${mix(r)}, ${mix(g)}, ${mix(b)})`;")
    assert not _broken_rules("const c = `#${r}${g}${b}`;")


def test_generated_code_is_held_to_the_same_rules() -> None:
    """The exemplar and the output were checked differently, and drifted."""
    scaffold = {
        "viz_type": "custom_card",
        "package_name": "@superset-ui/plugin-chart-custom-card",
        "directory": "superset-frontend/plugins/plugin-chart-custom-card",
        "files": [
            {
                "path": "superset-frontend/plugins/plugin-chart-custom-card/src/C.tsx",
                "contents": "const c = { color: '#2B2B2B' };\nconst d = x as any;",
            }
        ],
        "registration": {"import_line": "import {} from 'x';", "register_line": "r();"},
        "package_json_dependency": {"name": "@superset-ui/x", "spec": "file:./x"},
    }
    problems = " ".join(validate(scaffold, set()))
    assert "literal colour" in problems
    assert "as any" in problems


def test_the_shipped_exemplar_obeys_every_rule() -> None:
    """The whole point: what the model is told to copy must be copyable."""
    _check_exemplar(pathlib.Path("design-to-dashboard/assets/reference-plugin"))


# --- what a wrapper is told it hosts -----------------------------------------


def test_a_wrapper_hosts_only_children_that_become_charts() -> None:
    """A wrapper renders its children through Superset's chart container by
    id. A `grid_text` child is a markdown node that never gets an id, and a
    dropped one does not exist -- both carry `viz_type: null`, so describing
    them produced "(`None`)" and a wrapper written to fetch nothing."""
    decisions: list[dict[str, Any]] = [
        {"ref": "c1", "region_id": "r1", "decision": "configure", "viz_type": "bar"},
        {"ref": "c2", "region_id": "r2", "decision": "grid_text", "viz_type": None},
        {"ref": "c3", "region_id": "r3", "decision": "drop", "viz_type": None},
        {"ref": "c4", "region_id": "r4", "decision": "configure", "viz_type": "pie"},
    ]
    resolved = resolve_children({"children": ["c1", "c2", "c3", "c4"]}, decisions)
    assert [c["ref"] for c in resolved] == ["c1", "c4"]


def test_a_plugin_dropped_on_the_repair_pass_is_no_longer_hosted() -> None:
    """Children are re-resolved during repair, after a failed plugin's
    decision has already been rewritten to `drop`."""
    decisions: list[dict[str, Any]] = [
        {"ref": "c1", "region_id": "r1", "decision": "drop", "viz_type": "custom_x"}
    ]
    assert resolve_children({"children": ["c1"]}, decisions) == []


# --- a rewrite replaces the package rather than adding to it -----------------


def test_a_repair_removes_the_previous_attempt_s_files(tmp_path: pathlib.Path) -> None:
    """`write` only ever added files, and the one path that calls it twice is
    the compile repair -- where the file set is most likely to change. A
    helper the first attempt split out and the repair inlined stayed on disk,
    still type-checked, still able to fail the build the repair was fixing."""
    import shutil

    from superset.design_to_dashboard import plugin_skeleton

    (tmp_path / "superset-frontend/src/setup").mkdir(parents=True)
    (tmp_path / "superset-frontend/package.json").write_text('{"dependencies":{}}')
    (tmp_path / "superset-frontend/src/setup/setupPluginsExtra.ts").write_text(
        "export default function setupPluginsExtra(): void {}\n"
    )
    shutil.copytree(
        "design-to-dashboard/assets/plugin-skeleton",
        tmp_path / "design-to-dashboard/assets/plugin-skeleton",
    )
    shutil.copy(
        "design-to-dashboard/assets/plugin-thumbnail-placeholder.png",
        tmp_path / "design-to-dashboard/assets/",
    )
    plugin = plugin_skeleton.identity("custom_card", "t1")
    decision = {"plugin_archetype": "viz"}

    def _write(paths: list[str]) -> None:
        plugin_writer.write(
            {"files": [{"path": p, "contents": "x"} for p in paths]},
            tmp_path,
            plugin,
            decision,
        )

    component = f"{plugin.directory}/src/{plugin.component}.tsx"
    _write([component, f"{plugin.directory}/src/utils/stale.ts"])
    _write([component])

    source = tmp_path / plugin.directory / "src"
    assert not (source / "utils" / "stale.ts").exists()
    assert (source / f"{plugin.component}.tsx").exists()
    # The skeleton and the thumbnail survive the replacement.
    assert (source / "plugin" / "index.ts").exists()
    assert (source / "images" / "thumbnail.png").exists()
    setup = (tmp_path / "superset-frontend/src/setup/setupPluginsExtra.ts").read_text()
    assert setup.count("register();") == 1
