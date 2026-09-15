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
import re
import time
from typing import Any

import pytest

from superset.design_to_dashboard import plugin_skeleton, plugin_writer
from superset.design_to_dashboard.frontend import (
    _compile_verdict,
    compile_errors,
    typecheck_errors,
)
from superset.design_to_dashboard.llm.base import (
    LLMError,
    LLMMaxTurnsError,
    LLMResponse,
    LLMTruncatedError,
)
from superset.design_to_dashboard.runner import _plugins_in_errors, _restart_label
from superset.design_to_dashboard.stages.c_resolve import design_system
from superset.design_to_dashboard.stages.f_scaffold import (
    _axis_format_note,
    _broken_rules,
    _check_exemplar,
    _chrome_note,
    _image_legend,
    _investigation_note,
    _missing_imports,
    _native_filter_without_scope,
    _reference_source,
    _renamed_prop_pattern,
    _unusual_note,
    build_user_prompt,
    repair_one,
    resolve_children,
    run_one,
    SCAFFOLD_TIMEOUT,
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


def test_axis_formats_are_named_as_what_each_axis_actually_is() -> None:
    note = _axis_format_note(
        {
            "axis_formats": [
                {"axis": "x", "kind": "date", "pattern": "MMM YYYY"},
                {"axis": "y", "kind": "number", "pattern": ",.0f", "prefix": "$"},
            ]
        }
    )
    assert "date" in note
    assert "MMM YYYY" in note
    assert "prefix `$`" in note


def test_no_axis_formats_means_no_note() -> None:
    assert _axis_format_note({"axis_formats": []}) == ""
    assert _axis_format_note({}) == ""


# --- the design and the crop, told apart -------------------------------------


def test_both_images_are_labelled_first_and_second() -> None:
    note = _image_legend(has_design_image=True, has_region_image=True)
    assert "FIRST" in note
    assert "whole design" in note
    assert "SECOND" in note
    assert "cropped" in note
    assert "pixel" not in note  # the pixel-perfect framing lives in the caller


def test_the_crop_wins_when_the_two_disagree() -> None:
    note = _image_legend(has_design_image=True, has_region_image=True)
    assert "the crop wins" in note


def test_only_the_crop_says_no_full_design_was_available() -> None:
    note = _image_legend(has_design_image=False, has_region_image=True)
    assert "No full-design image" in note
    assert "FIRST" not in note


def test_neither_image_is_no_legend_at_all() -> None:
    assert _image_legend(has_design_image=False, has_region_image=False) == ""
    assert _image_legend(has_design_image=True, has_region_image=False) == ""


def test_the_legend_reaches_the_full_user_prompt() -> None:
    prompt = build_user_prompt(
        {}, {}, {}, {}, has_design_image=True, has_region_image=True
    )
    assert "Two images are attached" in prompt


def test_the_pixel_perfect_bar_is_always_stated() -> None:
    """Stated whether or not an image is attached at all -- it is the goal,
    not a caveat that depends on what this call happens to be given."""
    prompt = build_user_prompt({}, {}, {}, {})
    assert "pixel-perfect" in prompt
    assert "should not be able to tell them apart" in prompt


# --- one contract every parallel worker obeys --------------------------------


def test_the_contract_is_backfilled_from_what_stage_a_saw() -> None:
    """C is asked for chrome; when it omits it, A's observation still lands."""
    contract = design_system(
        {"design_system": {"palette": ["#111"]}},
        {
            "global": {
                "card_chrome": {"radius": "8px"},
                "typography": {"value": "24px/700"},
            }
        },
    )
    assert contract["card_chrome"] == {"radius": "8px"}
    assert contract["typography"] == {"value": "24px/700"}
    assert contract["palette"] == ["#111"]


def test_stage_a_s_prose_is_not_handed_to_plugin_authors() -> None:
    """A describes, and is never validated; a range backfilled from it reached
    every parallel worker, each of which picked its own end."""
    contract = design_system(
        {"design_system": {"palette": ["#111"]}},
        {
            "global": {
                "card_chrome": "White fill, subtle drop shadow",
                "typography": {"big_number": "22-24px bold", "label": "12px/500"},
            }
        },
    )
    assert "card_chrome" not in contract
    assert contract["typography"] == {"label": "12px/500"}


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


def test_a_tsc_error_keeps_the_lines_that_elaborate_it() -> None:
    """The first line of a TS2322 says the object is wrong; the indented lines
    under it say which property, which is what a patch needs."""
    output = (
        "plugins/p/src/Donut.tsx(85,14): error TS2322: Type '{ type: \"text\"; }' "
        "is not assignable to type 'Opt'.\n"
        "  The types of 'style.textAlign' are incompatible between these types.\n"
        "    Type 'string' is not assignable to type '\"center\" | \"left\"'.\n"
        "plugins/p/src/a.ts(1,1): error TS6133: 'React' is declared but its value "
        "is never read.\n"
        "\n"
        "  Found 2 errors in 2 files.\n"
    )
    errors = typecheck_errors(output)
    assert [error["file"] for error in errors] == [
        "plugins/p/src/Donut.tsx",
        "plugins/p/src/a.ts",
    ]
    assert errors[0]["detail"].split("\n") == [
        "line 85: TS2322: Type '{ type: \"text\"; }' is not assignable to type 'Opt'.",
        "  The types of 'style.textAlign' are incompatible between these types.",
        "    Type 'string' is not assignable to type '\"center\" | \"left\"'.",
    ]
    # A blank line ends a diagnostic, so the summary is nobody's elaboration.
    assert errors[1]["detail"] == (
        "line 1: TS6133: 'React' is declared but its value is never read."
    )


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


def test_a_hook_named_in_a_comment_is_not_a_use() -> None:
    """The false positive that cost a run four regions of its dashboard.

    Three plugins generated cleanly and were rejected over one prose line
    explaining where their theme tokens came from. Every region they served
    was dropped, and the reason was never written down.
    """
    assert not _missing_imports(
        "src/constants.ts",
        "// theme token read from `useTheme()`, so the table follows "
        "light and dark.\nexport const GAP = 8;\n",
    )


def test_a_hook_used_in_code_is_still_caught() -> None:
    """Stripping comments must not blind the check to the real thing."""
    assert _missing_imports("src/C.tsx", "const theme = useTheme();")


def test_a_commented_out_import_does_not_satisfy_the_check() -> None:
    """Reading imports from stripped source closes the opposite hole too."""
    assert _missing_imports(
        "src/C.tsx",
        "// import { useTheme } from '@superset-ui/core';\nconst theme = useTheme();",
    )


@pytest.mark.parametrize(
    "source",
    [
        "const visible = slices.slice(0, sliceCount - 1);",
        "let visible = true;",
        "const { visible = true } = props;",
        "state.visible = false;",
        "if (a.visible === b) {}",
    ],
)
def test_an_ordinary_variable_is_not_an_antd_prop(source: str) -> None:
    """`visible` is an antd v4 prop and an ordinary English word.

    A bare word-boundary match rejected a working donut plugin over a local
    holding the non-`Others` slices.
    """
    assert not re.search(_renamed_prop_pattern("visible"), source)


@pytest.mark.parametrize(
    "stale,source",
    [
        ("visible", "<Modal visible={open} />"),
        ("visible", "<Tooltip\n  visible={isOpen}\n/>"),
        ("dropdownMatchSelectWidth", "<Select dropdownMatchSelectWidth={false} />"),
        ("bodyStyle", "<Card bodyStyle={{ padding: 0 }} />"),
    ],
)
def test_a_renamed_prop_in_jsx_is_still_caught(stale: str, source: str) -> None:
    assert re.search(_renamed_prop_pattern(stale), source)


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


def test_a_child_whose_plugin_was_dropped_is_no_longer_hosted() -> None:
    """Children resolved after a failed plugin's decision was rewritten to
    `drop` must not include it."""
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


def test_the_author_is_told_to_read_metrics_through_the_helpers() -> None:
    """A shared plugin's sibling leaves a metric empty, and `getMetricLabel`
    throws on it -- so the prompt names the helpers the skeleton owns."""
    plugin = plugin_skeleton.identity("custom_tile", "t")
    prompt = build_user_prompt({}, {}, {}, {}, plugin=plugin, skeleton={})
    assert plugin_skeleton.OPTIONAL_METRICS_PATH in prompt
    for name in ("metricLabelOrNull", "metricValue", "presentMetrics"):
        assert name in prompt


REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]


class _Gateway:
    """A stub gateway. None of these tests exercise a real tool call -- the
    fake providers below answer with a bare `final` on the first round, so
    `run_tool_loop` never reaches `_execute` -- but `run_one` now always
    needs one to pass through."""

    name = "stub"

    def call(self, tool: str, arguments: dict[str, Any]) -> Any:
        raise AssertionError(f"unexpected tool call in a test: {tool}({arguments})")


class _FailingProvider:
    name = "fake"

    def __init__(self, error: Exception) -> None:
        self.error = error

    def complete(self, *args: Any, **kwargs: Any) -> Any:
        raise self.error


def _generate(error: Exception) -> Any:
    return run_one(
        _FailingProvider(error),
        _Gateway(),
        {},
        {},
        {"region_id": "r1", "viz_type": "custom_tile", "plugin_archetype": "viz"},
        {},
        REPO_ROOT / "design-to-dashboard" / "prompts",
        REPO_ROOT,
        set(),
        tag="t",
    )


def test_a_truncated_reply_reaches_the_runner_s_retry() -> None:
    """Swallowed into a result, it read as a bad scaffold and was dropped."""
    with pytest.raises(LLMTruncatedError):
        _generate(LLMTruncatedError("cut off", max_tokens=64000))


def test_an_exhausted_turn_budget_reaches_the_runner_s_retry() -> None:
    """Swallowed into a result the way a plain LLMError is, it would read as
    an ordinary failure and get zero retries -- in one run this dropped 8 of
    11 plugins the same way."""
    with pytest.raises(LLMMaxTurnsError):
        _generate(
            LLMMaxTurnsError(
                "Agent SDK reported an error: ['Reached maximum number of turns (6)']",
                max_turns=6,
            )
        )


def test_an_untyped_provider_error_also_reaches_the_runner_s_retry() -> None:
    """A plain `LLMError` -- not one of the four named subclasses -- used to
    be swallowed into a failed result with zero retries, no different from a
    model refusing outright. It now reaches `_retry`'s generic
    `except LLMError` branch the same as any other untyped `LLMError`."""
    with pytest.raises(LLMError):
        _generate(LLMError("refused"))


class _NotAnLLMError(Exception):
    """Stands in for a provider failure of a kind nothing here has named yet."""


def test_a_wholly_unclassified_failure_type_still_gets_a_retry() -> None:
    """The documented bug: a scaffold call once returned non-JSON garbage
    that matched none of the four named error types and got no second chance
    while every other failure in the same run got one. Any exception type at
    all -- not just an `LLMError` subclass -- must now reach the retry path,
    wrapped so `_retry` can still recognise it."""
    with pytest.raises(LLMError) as excinfo:
        _generate(_NotAnLLMError("garbage that matched nothing"))
    assert "garbage that matched nothing" in str(excinfo.value)
    assert "_NotAnLLMError" in str(excinfo.value)


def test_a_broken_exemplar_still_fails_fast_with_no_retry() -> None:
    """The deny-list: a vendored exemplar that breaks the shared code rules
    is a defect in this checkout, not in the model's reply. A retry would
    send the identical request against the identical broken file and fail at
    the identical line, so this is reported directly as a result rather than
    raised for `_retry` to spend a second call rediscovering it."""
    unreachable = LLMError("unreachable -- fails before the provider is called")
    result = run_one(
        _FailingProvider(unreachable),
        _Gateway(),
        {},
        {},
        {"region_id": "r1", "viz_type": "custom_tile", "plugin_archetype": "viz"},
        {},
        REPO_ROOT / "design-to-dashboard" / "prompts",
        REPO_ROOT / "does" / "not" / "exist",
        set(),
        tag="t",
    )
    assert not result.ok
    assert result.error


# --- run_one sends the design before the crop --------------------------------


class _RecordingProvider:
    name = "fake"

    def __init__(self, text: str) -> None:
        self.text = text
        self.calls: list[dict[str, Any]] = []

    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        image_paths: list[str] | None = None,
        timeout: int | None = None,
        on_thinking: Any = None,
    ) -> LLMResponse:
        self.calls.append(
            {
                "image_paths": image_paths,
                "user_prompt": user_prompt,
                "timeout": timeout,
            }
        )
        return LLMResponse(text=self.text, cost_usd=0.1, usage={}, provider="fake")


_MINIMAL_SCAFFOLD = json.dumps(
    {"status": "ok", "files": [], "review_notes": "a stub reply"}
)


def _run(provider: _RecordingProvider, **image_kwargs: Any) -> Any:
    return run_one(
        provider,
        _Gateway(),
        {},
        {},
        {"region_id": "r1", "viz_type": "custom_tile", "plugin_archetype": "viz"},
        {},
        REPO_ROOT / "design-to-dashboard" / "prompts",
        REPO_ROOT,
        set(),
        tag="t",
        **image_kwargs,
    )


def test_both_images_reach_the_provider_design_first() -> None:
    provider = _RecordingProvider(_MINIMAL_SCAFFOLD)
    _run(provider, design_image="design.png", region_image="crop.png")
    assert provider.calls[0]["image_paths"] == ["design.png", "crop.png"]
    assert "Two images are attached" in provider.calls[0]["user_prompt"]


def test_only_the_crop_is_sent_when_no_design_image_exists() -> None:
    provider = _RecordingProvider(_MINIMAL_SCAFFOLD)
    _run(provider, region_image="crop.png")
    assert provider.calls[0]["image_paths"] == ["crop.png"]


def test_no_images_sends_none() -> None:
    provider = _RecordingProvider(_MINIMAL_SCAFFOLD)
    _run(provider)
    assert provider.calls[0]["image_paths"] is None


# --- run_one is a tool loop now, not one direct call -------------------------


def test_the_scaffold_timeout_reaches_every_round_of_the_loop() -> None:
    """`run_tool_loop` has no timeout opinion of its own -- without this
    override every round silently fell back to the pipeline's 300s default
    instead of the 1200s this stage's own call is known to need."""
    provider = _RecordingProvider(_MINIMAL_SCAFFOLD)
    _run(provider)
    assert provider.calls[0]["timeout"] == SCAFFOLD_TIMEOUT


def test_a_bound_dataset_is_named_as_the_only_one_tools_may_touch() -> None:
    result = run_one(
        _RecordingProvider(_MINIMAL_SCAFFOLD),
        _Gateway(),
        {},
        {"dataset_id": 42},
        {"region_id": "r1", "viz_type": "custom_tile", "plugin_archetype": "viz"},
        {},
        REPO_ROOT / "design-to-dashboard" / "prompts",
        REPO_ROOT,
        set(),
        tag="t",
    )
    assert result.scaffold is not None


def test_no_dataset_id_omits_the_investigation_note() -> None:
    assert _investigation_note({}) == ""
    assert _investigation_note({"dataset_id": "not-an-int"}) == ""


def test_a_bound_dataset_note_names_it_and_reaches_the_prompt() -> None:
    note = _investigation_note({"dataset_id": 42})
    assert "dataset `42`" in note
    assert "get_dataset_info" in note
    assert "execute_sql" in note


class _ToolCallingProvider:
    """Requests one tool call, reads the observation back, then finishes --
    proving a real round-trip through `run_tool_loop` and the gateway reaches
    `run_one`'s caller, not just a bare first-round `final`."""

    name = "fake"

    def __init__(self, final_text: str) -> None:
        self.final_text = final_text
        self.rounds: list[str] = []

    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        image_paths: list[str] | None = None,
        timeout: int | None = None,
        on_thinking: Any = None,
    ) -> LLMResponse:
        self.rounds.append(user_prompt)
        if len(self.rounds) == 1:
            text = json.dumps(
                {
                    "tool_calls": [
                        {
                            "id": "t1",
                            "tool": "get_dataset_info",
                            "arguments": {"request": {"identifier": 42}},
                        }
                    ]
                }
            )
        else:
            text = self.final_text
        return LLMResponse(text=text, cost_usd=0.05, usage={}, provider="fake")


class _RecordingGateway:
    name = "recording"

    def __init__(self, response: dict[str, Any]) -> None:
        self.response = response
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def call(self, tool: str, arguments: dict[str, Any]) -> Any:
        self.calls.append((tool, arguments))
        return self.response


def test_a_real_tool_round_trip_reaches_the_gateway_and_the_final_scaffold() -> None:
    gateway = _RecordingGateway({"columns": [{"name": "spend", "type": "DOUBLE"}]})
    provider = _ToolCallingProvider(_MINIMAL_SCAFFOLD)
    result = run_one(
        provider,
        gateway,
        {},
        {"dataset_id": 42},
        {"region_id": "r1", "viz_type": "custom_tile", "plugin_archetype": "viz"},
        {},
        REPO_ROOT / "design-to-dashboard" / "prompts",
        REPO_ROOT,
        set(),
        tag="t",
    )
    assert gateway.calls == [("get_dataset_info", {"request": {"identifier": 42}})]
    assert len(provider.rounds) == 2
    # The round-trip is what this test is about; `_MINIMAL_SCAFFOLD`'s empty
    # `files` correctly fails `validate()`'s required-file check on its own
    # merits, unrelated to whether the tool call reached the gateway.
    assert result.scaffold is not None
    assert result.cost_usd == pytest.approx(0.1)


# --- a filter plugin declaring NativeFilter alone has no scope --------------


def test_native_filter_alone_is_rejected() -> None:
    source = (
        "static metadata = new ChartMetadata({\n"
        "  name: 'x',\n"
        "  behaviors: [Behavior.NativeFilter],\n"
        "});"
    )
    problems = _native_filter_without_scope("index.ts", source)
    assert problems
    assert "InteractiveChart" in problems[0]


def test_native_filter_with_interactive_chart_passes() -> None:
    source = (
        "static metadata = new ChartMetadata({\n"
        "  behaviors: [Behavior.NativeFilter, Behavior.InteractiveChart],\n"
        "});"
    )
    assert _native_filter_without_scope("index.ts", source) == []


def test_a_plugin_with_no_behaviors_array_is_not_flagged() -> None:
    assert _native_filter_without_scope("index.ts", "const x = 1;") == []


def test_the_check_reaches_validate() -> None:
    scaffold = {
        "viz_type": "custom_page_filter",
        "package_name": "@superset-ui/plugin-chart-custom-page-filter",
        "directory": "superset-frontend/plugins/plugin-chart-custom-page-filter",
        "files": [
            {
                "path": (
                    "superset-frontend/plugins/plugin-chart-custom-page-filter/"
                    "src/plugin/index.ts"
                ),
                "contents": "behaviors: [Behavior.NativeFilter],",
            }
        ],
        "registration": {"import_line": "import {} from 'x';", "register_line": "r();"},
        "package_json_dependency": {"name": "@superset-ui/x", "spec": "file:./x"},
    }
    problems = " ".join(validate(scaffold, set()))
    assert "InteractiveChart" in problems


def test_axis_formats_never_mentioned_in_review_notes_is_reported() -> None:
    scaffold = {"review_notes": "Renders the trend line and the KPI value."}
    region = {"axis_formats": [{"axis": "x", "kind": "date", "pattern": "MMM YYYY"}]}
    problems = " ".join(validate(scaffold, set(), region=region))
    assert "axis/series format" in problems


def test_axis_formats_mentioned_in_review_notes_is_not_reported() -> None:
    scaffold = {"review_notes": "Built the x axis formatter from the MMM YYYY pattern."}
    region = {"axis_formats": [{"axis": "x", "kind": "date", "pattern": "MMM YYYY"}]}
    problems = " ".join(validate(scaffold, set(), region=region))
    assert "axis/series format" not in problems


def test_no_axis_formats_skips_the_check() -> None:
    scaffold = {"review_notes": "Nothing about axes here."}
    assert "axis/series format" not in " ".join(
        validate(scaffold, set(), region={"axis_formats": []})
    )
    # region defaults to None and must not be required.
    assert "axis/series format" not in " ".join(validate(scaffold, set()))


_CLOSED_ICON_CONTROL_PANEL = """
const config = {
  controlPanelSections: [
    {
      controlSetRows: [
        [
          {
            name: "icon",
            config: {
              type: "SelectControl",
              label: t("Icon"),
              choices: [
                ["coins", "Coins"],
                ["cloud", "Cloud"],
                ["database", "Database"],
              ],
              default: "coins",
            },
          },
        ],
      ],
    },
  ],
};
export default config;
"""

_URL_ICON_CONTROL_PANEL = """
const config = {
  controlPanelSections: [
    {
      controlSetRows: [
        [
          {
            name: "iconUrl",
            config: {
              type: "TextControl",
              label: t("Icon URL"),
              default: "",
              description: t("An SVG or image URL for this card's icon."),
            },
          },
        ],
      ],
    },
  ],
};
export default config;
"""


def _icon_scaffold(control_panel_source: str) -> dict[str, Any]:
    return {
        "review_notes": "",
        "files": [
            {"path": "src/plugin/controlPanel.ts", "contents": control_panel_source}
        ],
    }


def test_a_named_brand_with_only_a_closed_icon_enum_is_flagged() -> None:
    region = {"observed": "A spend total card with the AWS logo in the corner."}
    problems = " ".join(
        validate(_icon_scaffold(_CLOSED_ICON_CONTROL_PANEL), set(), region=region)
    )
    assert "closed enum" in problems
    assert "AWS" in problems


def test_a_named_brand_with_a_real_url_option_is_not_flagged() -> None:
    region = {"unusual_treatment": ["Draws the GCP logo, not a generic icon"]}
    problems = " ".join(
        validate(_icon_scaffold(_URL_ICON_CONTROL_PANEL), set(), region=region)
    )
    assert "closed enum" not in problems


def test_no_named_brand_is_never_flagged_regardless_of_the_icon_control() -> None:
    region = {"observed": "A spend total card with a generic coin icon."}
    problems = " ".join(
        validate(_icon_scaffold(_CLOSED_ICON_CONTROL_PANEL), set(), region=region)
    )
    assert "closed enum" not in problems
    # No region at all must not be required either -- the check is opt-in on
    # `region`, the same as the axis-format check above.
    assert "closed enum" not in " ".join(
        validate(_icon_scaffold(_CLOSED_ICON_CONTROL_PANEL), set())
    )


def test_a_referenced_delta_column_is_not_flagged() -> None:
    binding = {"measures": [{"metric_name": "spend_pct_change"}]}
    scaffold = {
        "review_notes": "",
        "files": [
            {
                "path": "src/plugin/transformProps.ts",
                "contents": (
                    "const delta = data[0].spend_pct_change;\nexport default { delta };"
                ),
            }
        ],
    }
    problems = " ".join(validate(scaffold, set(), binding=binding))
    assert "precomputed change column" not in problems


def test_an_unreferenced_delta_column_is_flagged() -> None:
    binding = {"measures": [{"metric_name": "spend_pct_change"}]}
    scaffold = {
        "review_notes": "Computed the delta by splitting the series in half.",
        "files": [
            {
                "path": "src/plugin/transformProps.ts",
                "contents": (
                    "const half = Math.floor(series.length / 2);\n"
                    "const delta = sum(series.slice(half)) "
                    "- sum(series.slice(0, half));"
                ),
            }
        ],
    }
    problems = " ".join(validate(scaffold, set(), binding=binding))
    assert "precomputed change column" in problems
    assert "spend_pct_change" in problems


def test_binding_with_no_delta_like_column_is_never_flagged() -> None:
    binding = {"measures": [{"metric_name": "total_spend"}]}
    scaffold = {
        "review_notes": "Renders the headline total.",
        "files": [
            {
                "path": "src/plugin/transformProps.ts",
                "contents": "const total = data[0].total_spend;",
            }
        ],
    }
    problems = " ".join(validate(scaffold, set(), binding=binding))
    assert "precomputed change column" not in problems

    # A binding with nothing delta-shaped is never flagged, no matter what
    # the generated code does or omits.
    scaffold_no_reference = {
        "review_notes": "",
        "files": [{"path": "src/plugin/transformProps.ts", "contents": "// nothing"}],
    }
    problems = " ".join(validate(scaffold_no_reference, set(), binding=binding))
    assert "precomputed change column" not in problems

    # binding defaults to None and must not be required.
    assert "precomputed change column" not in " ".join(validate(scaffold, set()))


# --- the filter_widget exemplar demonstrates the bounds-query mechanism -----


def test_filter_widget_exemplar_has_buildquery_and_controlpanel() -> None:
    """The exemplar used to stop at `emitPeriod.ts`/`index.ts`/`transformProps.ts`
    -- no `buildQuery.ts`, no `controlPanel.ts`, even though `transformProps.ts`
    imports `MIN_PERIOD_LABEL`/`MAX_PERIOD_LABEL` from a `./buildQuery` that did
    not exist. A model shown that directory had to invent the one thing that is
    genuinely different about a filter -- how it queries its own bounds -- from
    prose alone."""
    root = REPO_ROOT / "design-to-dashboard" / "assets" / "reference-plugin"
    filter_dir = root / "filter_widget"
    assert (filter_dir / "buildQuery.ts").exists()
    assert (filter_dir / "controlPanel.ts").exists() or (
        filter_dir / "controlPanel.tsx"
    ).exists()

    build_query = (filter_dir / "buildQuery.ts").read_text(encoding="utf-8")
    transform_props = (filter_dir / "transformProps.ts").read_text(encoding="utf-8")
    # `transformProps.ts` is left untouched -- fix the dangling import by
    # making `buildQuery.ts` actually export what it already expects.
    assert "MIN_PERIOD_LABEL, MAX_PERIOD_LABEL" in re.sub(
        r"\s+", " ", transform_props
    ) or "MAX_PERIOD_LABEL, MIN_PERIOD_LABEL" in re.sub(r"\s+", " ", transform_props)
    assert "export const MIN_PERIOD_LABEL" in build_query
    assert "export const MAX_PERIOD_LABEL" in build_query


def test_filter_widget_exemplar_shows_the_bounds_query_pattern() -> None:
    """The mechanism the exemplar exists to teach: a MIN/MAX SQL-expression
    metric pair, not a groupby -- matching the technique a real, working
    filter plugin uses to anchor its dropdown to what the data contains."""
    build_query = (
        REPO_ROOT
        / "design-to-dashboard"
        / "assets"
        / "reference-plugin"
        / "filter_widget"
        / "buildQuery.ts"
    ).read_text(encoding="utf-8")
    assert "MIN(" in build_query
    assert "MAX(" in build_query
    assert "expressionType" in build_query


def test_filter_widget_exemplar_uses_a_dataset_aware_column_control() -> None:
    """Matches the committed date-range fixture's own idiom for a column
    pointer: `sharedControls.entity`, dataset-aware, not a hand-rolled
    `mapStateToProps` that risks an `any`-typed callback parameter."""
    control_panel = (
        REPO_ROOT
        / "design-to-dashboard"
        / "assets"
        / "reference-plugin"
        / "filter_widget"
        / "controlPanel.ts"
    ).read_text(encoding="utf-8")
    assert "sharedControls.entity" in control_panel


def test_the_shipped_filter_widget_exemplar_obeys_every_rule() -> None:
    """The new buildQuery/controlPanel files are exemplars too, and the whole
    point of `_check_exemplar` is that an exemplar cannot teach a violation
    of the rules its own output is held to."""
    _check_exemplar(REPO_ROOT / "design-to-dashboard" / "assets" / "reference-plugin")


def test_filter_widget_archetype_reference_includes_the_new_files() -> None:
    """`_reference_source` is what actually reaches the model; a file added to
    the exemplar directory that never surfaces there teaches nothing."""
    text = _reference_source(REPO_ROOT, "filter_widget")
    assert "filter_widget/buildQuery.ts" in text
    assert "filter_widget/controlPanel.ts" in text


def test_map_archetype_reaches_the_choropleth_mechanism() -> None:
    """A `map` job needs Datamaps' real mechanism, not a guess at how to draw
    a world map from scratch."""
    text = _reference_source(REPO_ROOT, "map")
    assert "map/Choropleth.tsx" in text
    assert "map/projection.ts" in text
    assert "datamaps/dist/datamaps.all.min" in text


def test_navigation_gets_its_own_mechanism_not_filter_widgets() -> None:
    """A breadcrumb does not filter this dashboard -- it posts to the parent
    app. Showing it filter_widget's setDataMask mechanism taught the wrong
    tool for the job; it must reach its own `postMessage` exemplar instead."""
    text = _reference_source(REPO_ROOT, "navigation")
    assert "navigation/Breadcrumb.tsx" in text
    assert "postMessage" in text
    assert "filter_widget/buildQuery.ts" not in text


# --- a scope-leaking filter is gated with the same severity as a compiler ---
# --- failure: never shipped, generation-time or repair-time --------------


_NATIVE_FILTER_ONLY_SOURCE = (
    "const metadata = new ChartMetadata({\n"
    "  name: t('x'),\n"
    "  behaviors: [Behavior.NativeFilter],\n"
    "});\n"
)


def test_a_native_filter_only_scaffold_never_reaches_scaffold_ok() -> None:
    """`run_one` is the generation-time gate: a scaffold whose `validate()`
    finds a scope-leaking filter is not `.ok`, which is exactly what the
    runner checks before writing a plugin to disk (`if not scaffold.ok`) --
    the same field a compile failure would also have left false. This is the
    gate the historical `plugin-chart-custom-date-range-filter-b3d605`
    fixture predates: `_native_filter_without_scope` did not exist in the
    stage F revision that generated it."""
    reply = json.dumps(
        {
            "status": "ok",
            "review_notes": "n/a",
            "files": [
                {"path": "src/plugin/index.ts", "contents": _NATIVE_FILTER_ONLY_SOURCE}
            ],
        }
    )
    provider = _RecordingProvider(reply)
    result = run_one(
        provider,
        _Gateway(),
        {},
        {},
        {
            "region_id": "r1",
            "viz_type": "custom_filter",
            "plugin_archetype": "filter_widget",
        },
        {},
        REPO_ROOT / "design-to-dashboard" / "prompts",
        REPO_ROOT,
        set(),
        tag="t",
    )
    assert not result.ok
    assert any("NativeFilter" in p and "InteractiveChart" in p for p in result.problems)


def test_a_repair_that_introduces_the_scope_leak_is_rejected_not_applied() -> None:
    """`repair_one` re-validates the whole merged file set, not just the
    files it patched, and its `result.ok` is exactly what
    `_repair_broken_plugins` checks before writing a patch to disk (`if not
    result.ok or result.scaffold is None: ... continue`). Introducing the
    same scope-leak through a repair patch is refused with the same severity
    as a patch that still does not compile -- it is never applied."""
    plugin = plugin_skeleton.identity("custom_filter", "t1")
    # `src/plugin/index.ts` is skeleton-owned (the template that actually
    # carries `behaviors`) and a patch cannot touch it; the component file is
    # not, and `validate()`'s `behaviors` regex does not care which file it
    # finds the array in -- it is exercised here on an ordinary source file
    # so the test does not depend on ownership rules that are not this
    # fix's concern.
    component_path = f"{plugin.directory}/src/{plugin.component}.tsx"
    files = {component_path: "export default function Comp() { return null; }"}

    reply = json.dumps(
        {
            "review_notes": "patched",
            "files": [{"path": component_path, "contents": _NATIVE_FILTER_ONLY_SOURCE}],
        }
    )
    provider = _RecordingProvider(reply)
    result = repair_one(
        provider,
        {"plugin_archetype": "filter_widget"},
        plugin,
        files,
        [{"file": component_path, "detail": "does not compile"}],
        REPO_ROOT / "design-to-dashboard" / "prompts",
        REPO_ROOT,
    )
    assert not result.ok
    assert any("NativeFilter" in p and "InteractiveChart" in p for p in result.problems)
