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
"""A plugin that did not compile is patched, not generated again.

The repair used to regenerate the whole plugin from memory with the errors
appended, for files the model could not see. It re-architected what compiled,
lost the previous round's fixes and spent a full generation on an unused
`React` import. These pin the replacement: a deterministic fix for unused
imports, and a patch over the files on disk that returns only what changes.
"""

from __future__ import annotations

import pathlib
import re
import shutil
from typing import Any

import pytest

from superset.design_to_dashboard import (
    frontend,
    plugin_skeleton,
    plugin_writer,
    runner,
)
from superset.design_to_dashboard.import_autofix import (
    fix_plugin,
    remove_unused_imports,
)
from superset.design_to_dashboard.llm.base import LLMResponse, LLMTruncatedError
from superset.design_to_dashboard.stages import f_scaffold
from superset.design_to_dashboard.stages.f_scaffold import (
    build_repair_prompt,
    merge_patch,
    relative_imports,
    repair_one,
)
from superset.utils import json

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
PROMPTS = REPO_ROOT / "design-to-dashboard" / "prompts"


def _unused(line: int, name: str, code: str = "TS6133") -> dict[str, str]:
    message = (
        f"'{name}' is declared but never used."
        if code == "TS6196"
        else f"'{name}' is declared but its value is never read."
    )
    return {"file": "plugins/x/src/A.tsx", "detail": f"line {line}: {code}: {message}"}


# --- unused imports are removed without a model -------------------------------


def test_a_default_react_import_goes_and_its_named_imports_stay() -> None:
    source = "import React, { useMemo } from 'react';\nconst a = useMemo;\n"
    fixed, removed = remove_unused_imports(source, [_unused(1, "React")])
    assert fixed == "import { useMemo } from 'react';\nconst a = useMemo;\n"
    assert removed == 1


def test_one_named_specifier_goes() -> None:
    source = "import { useEffect, useMemo, useState } from 'react';\n"
    fixed, _ = remove_unused_imports(source, [_unused(1, "useMemo")])
    assert fixed == "import { useEffect, useState } from 'react';\n"


def test_a_declaration_left_with_nothing_goes_whole() -> None:
    source = (
        "/** licence */\nimport React from 'react';\nimport { t } from './a';\n"
        "export const x = t;\n"
    )
    fixed, removed = remove_unused_imports(source, [_unused(2, "React")])
    assert fixed == "/** licence */\nimport { t } from './a';\nexport const x = t;\n"
    assert removed == 1


def test_an_import_type_binding_goes() -> None:
    source = "import type { ReactNode, FC } from 'react';\nlet f: FC;\n"
    fixed, _ = remove_unused_imports(source, [_unused(1, "ReactNode", "TS6196")])
    assert fixed == "import type { FC } from 'react';\nlet f: FC;\n"


def test_an_aliased_specifier_is_removed_by_the_name_it_binds() -> None:
    source = "import { styled as s, useTheme as u } from './adapter';\nu();\n"
    fixed, _ = remove_unused_imports(source, [_unused(1, "s")])
    assert fixed == "import { useTheme as u } from './adapter';\nu();\n"


def test_a_multi_line_import_keeps_its_shape() -> None:
    source = (
        "import {\n"
        "  Behavior,\n"
        "  ChartMetadata,\n"
        "  getMetricLabel,\n"
        "} from '../adapters/supersetAdapter';\n"
        "\n"
        "export const b = [Behavior, getMetricLabel];\n"
    )
    fixed, removed = remove_unused_imports(source, [_unused(3, "ChartMetadata")])
    assert fixed == (
        "import {\n"
        "  Behavior,\n"
        "  getMetricLabel,\n"
        "} from '../adapters/supersetAdapter';\n"
        "\n"
        "export const b = [Behavior, getMetricLabel];\n"
    )
    assert removed == 1


def test_several_errors_in_one_file_are_read_against_the_same_lines() -> None:
    """Removing line 1 must not shift the line the second error names."""
    source = (
        "import React from 'react';\n"
        "import { a, b } from './x';\n"
        "import * as echarts from 'echarts';\n"
        "export const y = b;\n"
    )
    fixed, removed = remove_unused_imports(
        source, [_unused(1, "React"), _unused(2, "a"), _unused(3, "echarts")]
    )
    assert fixed == "import { b } from './x';\nexport const y = b;\n"
    assert removed == 3


def test_an_all_unused_declaration_goes_whole() -> None:
    source = "import React, { useMemo } from 'react';\nexport const z = 1;\n"
    errors = [
        {
            "file": "plugins/x/src/A.tsx",
            "detail": "line 1: TS6192: All imports in import declaration are unused.",
        }
    ]
    fixed, removed = remove_unused_imports(source, errors)
    assert fixed == "export const z = 1;\n"
    assert removed == 2


def test_an_unused_local_is_left_for_the_model() -> None:
    """A destructured `theme` is not an import: it may mean a missing use."""
    source = (
        "import { useTheme } from './adapter';\n"
        "export function C() {\n"
        "  const theme = useTheme();\n"
        "  return null;\n"
        "}\n"
    )
    fixed, removed = remove_unused_imports(source, [_unused(3, "theme")])
    assert fixed == source
    assert removed == 0


def test_a_name_on_a_line_with_no_import_of_it_is_left_alone() -> None:
    source = "import { a } from './x';\nexport const b = a;\n"
    assert remove_unused_imports(source, [_unused(1, "React")]) == (source, 0)


def test_import_attributes_go_with_the_declaration_they_belong_to() -> None:
    source = (
        "import data from './d.json' with { type: 'json' };\n"
        "import cfg, { a } from './c.json' assert { type: 'json' };\n"
        "use(a);\n"
    )
    fixed, removed = remove_unused_imports(
        source, [_unused(1, "data"), _unused(2, "cfg")]
    )
    assert fixed == "import { a } from './c.json' assert { type: 'json' };\nuse(a);\n"
    assert removed == 2


def test_import_attributes_it_cannot_read_are_left_for_the_model() -> None:
    source = "import data from './d.json' with { type: { nested: 1 } };\nuse();\n"
    assert remove_unused_imports(source, [_unused(1, "data")]) == (source, 0)


def test_a_clause_it_cannot_read_is_left_for_the_model() -> None:
    source = "import { a, /* b, */ c } from './x';\nexport const d = c;\n"
    assert remove_unused_imports(source, [_unused(1, "a")]) == (source, 0)


@pytest.mark.parametrize(
    "source,errors",
    [
        (
            "import React from 'react';\n"
            "import { a } from './a';\n"
            "export const x = a;\n",
            [_unused(1, "React")],
        ),
        (
            "import React, { b } from 'react';\n"
            "import { a, c } from './a';\nexport const x = [a, c];\n",
            [
                {
                    "file": "plugins/x/src/A.tsx",
                    "detail": "line 1: TS6192: All imports in import declaration "
                    "are unused.",
                }
            ],
        ),
    ],
)
def test_the_fix_is_idempotent(source: str, errors: list[dict[str, str]]) -> None:
    """A second pass over shifted lines must not remove an import in use."""
    once, _ = remove_unused_imports(source, errors)
    twice, removed = remove_unused_imports(once, errors)
    assert twice == once
    assert removed == 0


def test_the_fix_is_applied_to_the_plugin_on_disk(tmp_path: pathlib.Path) -> None:
    directory = "superset-frontend/plugins/plugin-chart-custom-card-t1"
    component = tmp_path / directory / "src" / "CustomCard.tsx"
    owned = tmp_path / directory / "src" / "index.ts"
    component.parent.mkdir(parents=True)
    component.write_text("import React from 'react';\nexport const a = 1;\n")
    owned.write_text("import React from 'react';\n")
    errors = [
        {
            "file": "plugins/plugin-chart-custom-card-t1/src/CustomCard.tsx",
            "detail": "line 1: TS6133: 'React' is declared but its value is never "
            "read.",
        },
        {
            "file": "plugins/plugin-chart-custom-card-t1/src/index.ts",
            "detail": "line 1: TS6133: 'React' is declared but its value is never "
            "read.",
        },
    ]
    fixed = fix_plugin(tmp_path, directory, errors, {f"{directory}/src/index.ts"})
    assert fixed == {f"{directory}/src/CustomCard.tsx": 1}
    assert component.read_text() == "export const a = 1;\n"
    # The skeleton's files are re-rendered on every write; an edit would not last.
    assert owned.read_text() == "import React from 'react';\n"


# --- a compiler path is a plugin file ----------------------------------------

DIRECTORY = "superset-frontend/plugins/plugin-chart-custom-card-t1"


def test_read_skips_build_output_only_at_the_package_root(
    tmp_path: pathlib.Path,
) -> None:
    base = tmp_path / "superset-frontend/plugins/p"
    for relative, data in {
        "package.json": b"{}",
        "node_modules/dep/index.js": b"x",
        "lib/index.js": b"x",
        ".cache/a.ts": b"x",
        "src/index.ts": b"export {};",
        "src/lib/format.ts": b"export const f = 1;",
        "src/dist/helper.ts": b"export const g = 1;",
        "src/images/thumbnail.png": b"\x89PNG\xff",
    }.items():
        (base / relative).parent.mkdir(parents=True, exist_ok=True)
        (base / relative).write_bytes(data)

    files = plugin_writer.read("superset-frontend/plugins/p", tmp_path)

    prefix = "superset-frontend/plugins/p/"
    assert sorted(files.sources) == [
        f"{prefix}package.json",
        f"{prefix}src/dist/helper.ts",
        f"{prefix}src/index.ts",
        f"{prefix}src/lib/format.ts",
    ]
    assert files.assets == {f"{prefix}src/images/thumbnail.png": b"\x89PNG\xff"}


@pytest.mark.parametrize(
    "error_file,expected",
    [
        ("plugins/plugin-chart-custom-card-t1/src/a.tsx", f"{DIRECTORY}/src/a.tsx"),
        (
            "./plugins/plugin-chart-custom-card-t1/src/plugin/buildQuery.ts:38:38",
            f"{DIRECTORY}/src/plugin/buildQuery.ts",
        ),
        (
            "/abs/superset-frontend/plugins/plugin-chart-custom-card-t1/src/types.ts",
            f"{DIRECTORY}/src/types.ts",
        ),
        ("plugins/plugin-chart-custom-card-t1x/src/a.tsx", None),
        ("src/dashboard/Existing.tsx", None),
    ],
)
def test_a_tsc_path_maps_to_the_plugin_file(
    error_file: str, expected: str | None
) -> None:
    assert frontend.plugin_file(error_file, DIRECTORY) == expected


# --- what the repair is shown -------------------------------------------------

PLUGIN = plugin_skeleton.identity("custom_card", "t1")
D = PLUGIN.directory
COMPONENT = f"{D}/src/CustomCard.tsx"
ADAPTER = f"{D}/src/adapters/supersetAdapter.ts"
TYPES = f"{D}/src/types.ts"
STYLES = f"{D}/src/CustomCardStyles.ts"
SPARK = f"{D}/src/components/Spark/index.tsx"
BUILD_QUERY = f"{D}/src/plugin/buildQuery.ts"
PLUGIN_INDEX = f"{D}/src/plugin/index.ts"

FILES = {
    COMPONENT: (
        "import { useTheme } from './adapters/supersetAdapter';\n"
        "import { Card } from './CustomCardStyles';\n"
        "import Spark from './components/Spark';\n"
        "export default function CustomCard() {\n"
        "  const theme = useTheme();\n"
        "  return <Card><Spark /></Card>;\n"
        "}\n"
    ),
    ADAPTER: "export { useTheme } from '@apache-superset/core/theme';\n",
    TYPES: "export type CustomCardFormData = { metric: string };\n",
    STYLES: "export const Card = 'div';\n",
    SPARK: "export default function Spark() { return null; }\n",
    BUILD_QUERY: "export default function buildQuery() { return 'BQ_BODY'; }\n",
    PLUGIN_INDEX: "export default class P {}\n",
}
ERRORS = [
    {
        "file": "plugins/plugin-chart-custom-card-t1/src/CustomCard.tsx",
        "detail": "line 5: TS6133: 'theme' is declared but its value is never read.",
    }
]


def test_relative_imports_resolve_extensions_and_index_files() -> None:
    assert relative_imports(COMPONENT, FILES[COMPONENT], FILES) == [
        ADAPTER,
        STYLES,
        SPARK,
    ]


def test_the_failing_file_is_shown_whole_with_line_numbers_and_the_error() -> None:
    prompt = build_repair_prompt(PROMPTS, PLUGIN, FILES, ERRORS, {PLUGIN_INDEX})
    for number, line in enumerate(FILES[COMPONENT].split("\n"), 1):
        assert f"{number} | {line}" in prompt
    assert "TS6133: 'theme' is declared" in prompt
    # The offending line is marked beside the error.
    assert re.search(r">\s+5 \|   const theme = useTheme\(\);", prompt)


def test_the_repair_sees_what_the_failing_file_leans_on() -> None:
    prompt = build_repair_prompt(PROMPTS, PLUGIN, FILES, ERRORS, {PLUGIN_INDEX})
    for path in (ADAPTER, TYPES, STYLES, SPARK):
        assert f"### `{path}`" in prompt
        assert FILES[path] in prompt


def test_every_other_file_is_named_but_not_shown() -> None:
    prompt = build_repair_prompt(PROMPTS, PLUGIN, FILES, ERRORS, {PLUGIN_INDEX})
    assert f"- `{BUILD_QUERY}`" in prompt
    assert "BQ_BODY" not in prompt
    assert f"- `{PLUGIN_INDEX}` — written by the skeleton" in prompt


def test_the_repair_is_told_to_return_only_what_it_changes() -> None:
    prompt = build_repair_prompt(PROMPTS, PLUGIN, FILES, ERRORS, set())
    assert "only** the files you change" in prompt
    assert "overrides the Output section" in prompt


# --- merging a patch over the files on disk -----------------------------------


def _reply(*files: tuple[str, str]) -> dict[str, Any]:
    return {"status": "ok", "files": [{"path": p, "contents": c} for p, c in files]}


def test_a_patch_replaces_only_the_files_it_returns() -> None:
    fixed = FILES[COMPONENT].replace("  const theme = useTheme();\n", "")
    merged, changed, problems = merge_patch(
        FILES, _reply((COMPONENT, fixed)), PLUGIN, {PLUGIN_INDEX}
    )
    assert problems == []
    assert changed == [COMPONENT]
    assert merged[COMPONENT] == fixed
    assert merged[BUILD_QUERY] == FILES[BUILD_QUERY]
    assert PLUGIN_INDEX not in merged


# A valid change rides along with each bad one: one bad entry rejects it all.
FINE = (STYLES, "export const Card = 'section';\n")


@pytest.mark.parametrize(
    "bad,expected",
    [
        ((PLUGIN_INDEX, "export default 1;\n"), "written by the skeleton"),
        (("superset/app.py", "x = 1\n"), "outside the plugin directory"),
        ((f"{D}/src/../../evil/a.ts", "x\n"), "outside the plugin directory"),
        ((COMPONENT, "  \n"), "never deletes"),
    ],
)
def test_a_patch_with_one_bad_file_is_rejected_whole(
    bad: tuple[str, str], expected: str
) -> None:
    merged, changed, problems = merge_patch(
        FILES, _reply(FINE, bad), PLUGIN, {PLUGIN_INDEX}
    )
    assert (merged, changed) == ({}, [])
    assert expected in " ".join(problems)


@pytest.mark.parametrize(
    "reply,expected",
    [
        ({"status": "ok", "files": []}, "no files"),
        ({"status": "ok"}, "no files"),
        (_reply((TYPES, FILES[TYPES])), "identical"),
    ],
)
def test_an_empty_patch_is_a_failed_repair(
    reply: dict[str, Any], expected: str
) -> None:
    merged, changed, problems = merge_patch(FILES, reply, PLUGIN, {PLUGIN_INDEX})
    assert (merged, changed) == ({}, [])
    assert expected in " ".join(problems)


# --- the patch call itself ----------------------------------------------------


class _Provider:
    """Answers each call with the next reply; records what it was asked."""

    name = "fake"

    def __init__(self, *replies: Any) -> None:
        self.replies = list(replies)
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
            {"system": system_prompt, "user": user_prompt, "images": image_paths}
        )
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        if callable(reply):
            reply = reply(user_prompt)
        return LLMResponse(text=json.dumps(reply), cost_usd=0.5)


def test_the_repair_reuses_stage_f_s_system_prompt_byte_for_byte() -> None:
    """The prompt cache and the house rules both depend on it."""
    fixed = FILES[COMPONENT].replace("  const theme = useTheme();\n", "")
    provider = _Provider(_reply((COMPONENT, fixed)))
    decision = {"viz_type": "custom_card", "plugin_archetype": "viz"}
    result = repair_one(provider, decision, PLUGIN, FILES, ERRORS, PROMPTS, REPO_ROOT)
    assert provider.calls[0]["system"] == f_scaffold.build_system_prompt(
        PROMPTS, REPO_ROOT, "viz"
    )
    assert provider.calls[0]["images"] is None
    assert result.cost_usd == 0.5
    assert result.changed == [COMPONENT]


def test_a_cut_off_repair_is_a_result_not_a_crash() -> None:
    provider = _Provider(LLMTruncatedError("cut off", max_tokens=64000))
    result = repair_one(
        provider, {"plugin_archetype": "viz"}, PLUGIN, FILES, ERRORS, PROMPTS, REPO_ROOT
    )
    assert not result.ok
    assert "LLMTruncatedError" in (result.error or "")


# --- the runner's repair rounds, on a repo on disk ----------------------------


class _Session:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def publish(self, event_type: str, **payload: Any) -> None:
        self.events.append({"type": event_type, **payload})


def _fake_repo(root: pathlib.Path) -> None:
    shutil.copytree(
        REPO_ROOT / "design-to-dashboard" / "assets",
        root / "design-to-dashboard" / "assets",
    )
    (root / "superset-frontend/src/setup").mkdir(parents=True)
    (root / "superset-frontend/package.json").write_text('{"dependencies": {}}\n')
    (root / "superset-frontend/src/setup/setupPluginsExtra.ts").write_text(
        "export default function setupPluginsExtra(): void {}\n"
    )


def _fake_typecheck(root: pathlib.Path, plugin: plugin_skeleton.PluginIdentity) -> Any:
    """A compiler that objects to a bare React import and to any `BAD_` name."""

    def typecheck(_repo_root: Any) -> dict[str, Any]:
        errors = []
        base = root / plugin.directory
        for path in sorted(base.rglob("*.ts*")):
            reported = f"plugins/{plugin.leaf}/{path.relative_to(base).as_posix()}"
            for number, line in enumerate(path.read_text().split("\n"), 1):
                if line == "import React from 'react';":
                    detail = "TS6133: 'React' is declared but its value is never read."
                elif match := re.search(r"\bBAD_\w+", line):
                    detail = f"TS2304: Cannot find name '{match.group(0)}'."
                else:
                    continue
                errors.append({"file": reported, "detail": f"line {number}: {detail}"})
        if not errors:
            return {"compiled": True, "errors": []}
        return {"compiled": False, "errors": errors}

    return typecheck


def _patch_first_failing_file(root: pathlib.Path) -> Any:
    """A model that fixes one file per call, reading it as the prompt shows it."""

    def reply(user_prompt: str) -> dict[str, Any]:
        failing = re.search(
            r"## What the compiler rejected\n\n### `([^`]+)`", user_prompt
        )
        assert failing
        path = failing.group(1)
        contents = (root / path).read_text()
        return _reply((path, re.sub(r"\bBAD_\w+", "1", contents)))

    return reply


def _written_plugin(root: pathlib.Path) -> tuple[Any, dict[str, Any]]:
    plugin = plugin_skeleton.identity("custom_card", "t1")
    decision = {
        "region_id": "r1",
        "viz_type": plugin.viz_type,
        "plugin_archetype": "viz",
        "decision": "configure",
    }
    d = plugin.directory
    scaffold = {
        "files": [
            {
                "path": f"{d}/src/CustomCard.tsx",
                "contents": "import React from 'react';\n"
                "export default function CustomCard() {\n"
                "  return BAD_ONE;\n"
                "}\n",
            },
            {"path": f"{d}/src/types.ts", "contents": "export type T = number;\n"},
            {
                "path": f"{d}/src/plugin/transformProps.ts",
                "contents": "export default function transform() {\n"
                "  return BAD_TWO;\n"
                "}\n",
            },
            {
                "path": f"{d}/src/plugin/buildQuery.ts",
                "contents": "export default function b() {\n  return 2;\n}\n",
            },
            {
                "path": f"{d}/src/plugin/controlPanel.ts",
                "contents": "export default {};\n",
            },
            {"path": f"{d}/src/utils/helper.ts", "contents": "export const h = 3;\n"},
            # A folder named like build output, below the root, is source.
            {"path": f"{d}/src/lib/format.ts", "contents": "export const f = 4;\n"},
        ],
        "params_hint": {"metric": "kept"},
        **f_scaffold._identity_fields(plugin),
    }
    plugin_writer.write(scaffold, root, plugin, decision)
    result = f_scaffold.ScaffoldResult(
        region_id="r1", viz_type=plugin.viz_type, scaffold=scaffold, plugin=plugin
    )
    return result, decision


def test_repair_rounds_patch_the_disk_and_keep_what_they_fixed(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake_repo(tmp_path)
    scaffold, decision = _written_plugin(tmp_path)
    plugin = scaffold.plugin
    base = tmp_path / plugin.directory
    # A photographed thumbnail and another binary asset must survive a patch.
    (base / "src/images/thumbnail.png").write_bytes(b"\x89PNG photographed")
    (base / "src/images/extra.png").write_bytes(b"\x89PNG extra")

    typecheck = _fake_typecheck(tmp_path, plugin)
    links: list[Any] = []
    monkeypatch.setattr(runner, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(frontend, "typecheck", typecheck)
    monkeypatch.setattr(frontend, "link_plugins", lambda root: links.append(root))
    provider = _Provider(
        _patch_first_failing_file(tmp_path), _patch_first_failing_file(tmp_path)
    )
    session = _Session()
    plan = {"decisions": [decision]}
    built = [plugin.viz_type]

    cost = runner._typecheck_and_quarantine(
        session,
        {plugin.viz_type: scaffold},
        {plugin.viz_type: [decision]},
        plan,
        provider,
        built,
    )

    # Two model calls, one fix each, and the React import never reached one.
    assert len(provider.calls) == 2
    assert all("TS6133" not in call["user"] for call in provider.calls)
    assert cost == 1.0
    # Round one's fix is still there after round two rewrote the package.
    component = (base / "src/CustomCard.tsx").read_text()
    assert "BAD_ONE" not in component
    assert "import React" not in component
    assert "BAD_TWO" not in (base / "src/plugin/transformProps.ts").read_text()
    # Files no patch touched are exactly as they were.
    assert (base / "src/utils/helper.ts").read_text() == "export const h = 3;\n"
    assert (base / "src/lib/format.ts").read_text() == "export const f = 4;\n"
    assert f"{plugin.directory}/src/lib/format.ts" in {
        entry["path"] for entry in scaffold.scaffold["files"]
    }
    assert (base / "src/images/thumbnail.png").read_bytes() == b"\x89PNG photographed"
    assert (base / "src/images/extra.png").read_bytes() == b"\x89PNG extra"
    assert (base / "src/plugin/index.ts").exists()
    # Nothing was removed, nothing relinked, and the params hint survived.
    assert built == [plugin.viz_type]
    assert links == []
    assert scaffold.scaffold["params_hint"] == {"metric": "kept"}
    types = [event["type"] for event in session.events]
    assert "plugin_autofixed" in types
    assert types.count("plugin_patched") == 2
    assert types[-1] == "typecheck_passed"
    labels = [event.get("label") for event in session.events]
    assert "Removed 1 unused import(s) — rechecking" in labels
    assert "Patched 1 file(s) in custom_card" in labels


def test_a_rejected_patch_leaves_the_plugin_as_it_was(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake_repo(tmp_path)
    scaffold, decision = _written_plugin(tmp_path)
    plugin = scaffold.plugin
    before = plugin_writer.read(plugin.directory, tmp_path)
    monkeypatch.setattr(runner, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(frontend, "typecheck", _fake_typecheck(tmp_path, plugin))
    monkeypatch.setattr(frontend, "link_plugins", lambda root: None)
    # React is removed without a model; then the patch reaches for the skeleton.
    provider = _Provider(
        _reply((f"{plugin.directory}/src/plugin/index.ts", "export default 1;\n")),
    )
    session = _Session()
    verdict = frontend.typecheck(tmp_path)

    after_verdict = runner._repair_broken_plugins(
        session,
        verdict,
        {plugin.viz_type: scaffold},
        {plugin.viz_type: [decision]},
        provider,
    )

    after = plugin_writer.read(plugin.directory, tmp_path)
    component = f"{plugin.directory}/src/CustomCard.tsx"
    assert after.sources[component] == before.sources[component].replace(
        "import React from 'react';\n", ""
    )
    assert {p: c for p, c in after.sources.items() if p != component} == {
        p: c for p, c in before.sources.items() if p != component
    }
    assert after_verdict["compiled"] is False
    assert "plugin_repair_rejected" in [event["type"] for event in session.events]


def test_a_repair_that_raises_leaves_the_plugin_for_the_quarantine(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake_repo(tmp_path)
    scaffold, decision = _written_plugin(tmp_path)
    plugin = scaffold.plugin
    monkeypatch.setattr(runner, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(frontend, "typecheck", _fake_typecheck(tmp_path, plugin))
    monkeypatch.setattr(frontend, "link_plugins", lambda root: None)
    provider = _Provider(
        LLMTruncatedError("cut off", max_tokens=1), LLMTruncatedError("x", max_tokens=1)
    )
    session = _Session()
    plan = {"decisions": [decision]}
    built = [plugin.viz_type]

    runner._typecheck_and_quarantine(
        session,
        {plugin.viz_type: scaffold},
        {plugin.viz_type: [decision]},
        plan,
        provider,
        built,
    )

    assert built == []
    assert not (tmp_path / plugin.directory).exists()
    assert decision["decision"] == "drop"
    assert "plugin_failed" in [event["type"] for event in session.events]


def test_the_seeded_adapter_is_repaired_like_any_other_file(
    tmp_path: pathlib.Path,
) -> None:
    """A fix made to the adapter used to be lost when a regeneration left it
    out and the seed came back. A patch merges over the disk instead."""
    _fake_repo(tmp_path)
    scaffold, decision = _written_plugin(tmp_path)
    plugin = scaffold.plugin
    adapter = f"{plugin.directory}/src/adapters/supersetAdapter.ts"
    on_disk = plugin_writer.read(plugin.directory, tmp_path)
    extended = on_disk.sources[adapter] + "export const validateNonEmpty = 1;\n"
    owned = plugin_skeleton.owned_paths(plugin, tmp_path)
    merged, changed, problems = merge_patch(
        on_disk.sources, _reply((adapter, extended)), plugin, owned
    )
    assert problems == []
    assert changed == [adapter]
    plugin_writer.write(
        {"files": [{"path": p, "contents": c} for p, c in merged.items()]},
        tmp_path,
        plugin,
        decision,
    )
    assert "validateNonEmpty" in (tmp_path / adapter).read_text()
