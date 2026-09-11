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
"""Stage F - scaffold a viz plugin that renders a region exactly.

Runs when stage C decides a design's structure cannot be produced by any
registered viz type. Emits a complete plugin package plus the three artifacts
needed to register it, then a writer puts them on disk.
"""

from __future__ import annotations

import logging
import pathlib
import re
from dataclasses import dataclass, field
from typing import Any

from superset.design_to_dashboard.llm.base import (
    LLMError,
    LLMProvider,
    LLMTimeoutError,
)
from superset.design_to_dashboard.pipeline.tool_loop import extract_json
from superset.utils import json

logger = logging.getLogger(__name__)

# The local plugin with correct Superset 6.1 imports; used as the exemplar so
# generated code matches this checkout rather than an older convention.
# Generating a whole plugin package is the longest call in the pipeline --
# measured at 8-10 minutes. The pipeline-wide default of 300s is far too tight
# and produced "Agent SDK timed out" mid-generation.
SCAFFOLD_TIMEOUT = 1200

# The exemplar the model copies conventions from. It is vendored into this
# feature's own tree rather than pointed at a live plugin: a registered
# plugin can be deleted (they are meant to be disposable), and stage F must
# not depend on one existing. Refresh it from a real plugin when Superset's
# import paths or plugin class shape change.
# Every plugin a run generates carries a suffix identifying the run, on its
# **directory name only**. That is what makes generated plugins findable for
# cleanup and traceable to the run that wrote them. The package name, the
# `viz_type` and the chart's display name all stay clean: those are what a
# dashboard viewer sees and what a later run matches against when deciding to
# reuse rather than rebuild. npm links by package name and resolves the `file:`
# path to the tagged directory, so the two need not agree.
RUN_TAG_LENGTH = 6


def run_tag(session_id: str) -> str:
    """The suffix identifying the run that generated a plugin, e.g. `4d9976`."""
    return session_id.replace("-", "")[:RUN_TAG_LENGTH].lower()


REFERENCE_PLUGIN = "design-to-dashboard/assets/reference-plugin"

# `base/` is one complete production plugin -- the conventions every plugin
# shares. The archetype directories hold only the *mechanism* that archetype
# needs, not a whole second plugin: hosting a saved chart, emitting a data
# mask, drawing inside a table cell. A worker is shown its own archetype and
# nothing else, so a plain `viz` job carries less context than it would if
# every capability were pasted in for completeness.
ARCHETYPE_REFERENCE = {
    "composite": "composite",
    "filter_widget": "filter_widget",
    "table": "table",
    "navigation": "filter_widget",  # navigation emits state the same way
}

REQUIRED_SUFFIXES = (
    "src/index.ts",
    "src/types.ts",
    "src/plugin/index.ts",
    "src/plugin/buildQuery.ts",
    "src/plugin/transformProps.ts",
    "package.json",
)

# Symbols that moved out of @superset-ui/core in 6.1. Importing them from the
# wrong module makes `styled` an implicit any and fails the build.
# antd v5 renamed these. A model trained on v4 examples reaches for the old
# name, TypeScript rejects it, and the chart renders blank on a dashboard that
# otherwise looks finished.
RENAMED_PROPS = {
    "dropdownMatchSelectWidth": "popupMatchSelectWidth",
    "dropdownClassName": "popupClassName",
    "dropdownStyle": "popupStyle",
    "visible": "open (on Modal, Drawer, Tooltip and Popover)",
    "bodyStyle": "styles.body",
    "overlayClassName": "classNames.root",
}

MOVED_SYMBOLS = {
    "t": "@apache-superset/core/translation",
    "styled": "@apache-superset/core/theme",
    "supersetTheme": "@apache-superset/core/theme",
}


@dataclass
class ScaffoldResult:
    region_id: str
    viz_type: str | None = None
    scaffold: dict[str, Any] | None = None
    error: str | None = None
    cost_usd: float = 0.0
    problems: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.scaffold is not None and not self.problems


def _read_tree(root: pathlib.Path, label: str) -> list[str]:
    """Every source file under `root`, as labelled fenced blocks."""
    blocks = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.suffix in {".ts", ".tsx", ".json"}:
            relative = path.relative_to(root)
            blocks.append(
                f"### {label}/{relative}\n```\n{path.read_text(encoding='utf-8')}\n```"
            )
    return blocks


# Fields and props the vendored exemplars are known to have carried from the
# fork's older Superset. An exemplar showing one of these teaches the model an
# API this version rejects, and the model is right to copy it -- so the
# exemplar is what must be fixed.
# Matched as regexes, because the same field name is right on one object and
# wrong on another: a slice entity really does carry `form_data`, while
# `ChartState` renamed it in 6.1. Only the `initChart` spread is the error.
STALE_EXEMPLAR_API = {
    r"\.\.\.initChart[\s\S]{0,400}?\bform_data\s*:": (
        "ChartState calls this `latestQueryFormData` in 6.1"
    ),
    r"\bdropdownMatchSelectWidth\s*=": ("antd v5 calls this `popupMatchSelectWidth`"),
}


def _check_exemplar(root: pathlib.Path) -> None:
    """Fail if an exemplar teaches an import or API `validate` will reject.

    The exemplars are vendored from a fork running an older Superset, where
    `t` and `styled` still lived in `@superset-ui/core`. A model told to copy
    the exemplar's conventions copies those too, and then its output is
    rejected by the very rules this stage enforces -- a contradiction the model
    cannot resolve and did not cause. Catch it here, where the message can name
    the file, rather than after a ten-minute generation.
    """
    pattern = re.compile(
        r"import\s+(?:type\s+)?\{([^}]*)\}\s+from\s+'@superset-ui/core'", re.S
    )
    for path in sorted(root.rglob("*")):
        if path.suffix not in {".ts", ".tsx"}:
            continue
        contents = path.read_text(encoding="utf-8")
        # An exemplar must satisfy the rules its output is held to. `any` was
        # in the exemplar's `mapStateToProps` while `validate` rejected it in
        # generated code, so the model avoided `any`, invented a narrower type
        # and produced something that did not compile. A contradiction the
        # model cannot win.
        if re.search(r":\s*any\b", contents):
            raise LLMError(
                f"exemplar {path.relative_to(root)} uses an `any` type, which "
                "stage F rejects in generated code. An exemplar must obey the "
                "rules its output is held to."
            )
        for stale, correction in STALE_EXEMPLAR_API.items():
            if re.search(stale, contents):
                raise LLMError(
                    f"exemplar {path.relative_to(root)} teaches an API this "
                    f"Superset rejects: {correction}. Refresh the exemplar "
                    "rather than letting it teach a dead API."
                )
        for match in pattern.finditer(contents):
            names = {
                n.strip().split(" as ")[0].strip() for n in match.group(1).split(",")
            }
            stale_imports = sorted(names & set(MOVED_SYMBOLS))
            if stale_imports:
                raise LLMError(
                    f"exemplar {path.relative_to(root)} imports {stale_imports} from "
                    "@superset-ui/core, which stage F rejects in generated code. "
                    "Refresh the exemplar to this Superset version."
                )


def _reference_source(repo_root: pathlib.Path, archetype: str | None) -> str:
    """The exemplars this archetype needs: the base plugin, plus its mechanism."""
    root = repo_root / REFERENCE_PLUGIN
    _check_exemplar(root)
    blocks = _read_tree(root / "base", "reference-plugin")
    if not blocks:
        raise LLMError(f"Reference plugin not found at {root / 'base'}")

    if supplement := ARCHETYPE_REFERENCE.get(archetype or ""):
        extra = _read_tree(root / supplement, f"reference-{supplement}")
        if extra:
            blocks.append(
                f"## How a `{archetype}` plugin works\n\n"
                "Production code for this archetype. The mechanism here is the "
                "point -- reproduce it; the styling around it is not."
            )
            blocks.extend(extra)
    return "\n\n".join(blocks)


def build_system_prompt(
    prompts_dir: pathlib.Path,
    repo_root: pathlib.Path,
    archetype: str | None = None,
) -> str:
    preamble = (prompts_dir / "shared" / "_preamble.md").read_text(encoding="utf-8")
    stage = (prompts_dir / "F_scaffold_plugin.md").read_text(encoding="utf-8")
    return "\n\n---\n\n".join(
        [
            preamble,
            stage,
            (
                "## Reference plugin\n\n"
                "A working plugin from this checkout. Its import paths, plugin "
                "class shape and package.json are correct for this Superset "
                "version -- copy those conventions rather than recalling "
                "older ones.\n\n" + _reference_source(repo_root, archetype)
            ),
        ]
    )


def resolve_children(
    decision: dict[str, Any], decisions: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """What a wrapper actually hosts, resolved before a line is written.

    A composing decision names its children by symbolic ref -- `["c1", "c4"]`
    -- because no chart has an id until apply time. Passed through as-is, the
    author of the wrapper is told it hosts two things and nothing about what
    they are: not the chart type, not the title, not how many. It then invents
    a child contract, and the children are built separately against a different
    one.

    Resolving the refs first is what makes the wrapper's job knowable: each
    child arrives as the chart type it will really be, under the name it will
    really have.
    """
    by_ref = {d.get("ref"): d for d in decisions if d.get("ref")}
    resolved = []
    for ref in decision.get("children") or []:
        child = by_ref.get(ref)
        if not child:
            continue
        resolved.append(
            {
                "ref": ref,
                "region_id": child.get("region_id"),
                "viz_type": child.get("viz_type"),
                "slice_name": child.get("slice_name"),
                "draws": child.get("rationale"),
            }
        )
    return resolved


def _hosting_note(region: dict[str, Any], children: list[dict[str, Any]]) -> str:
    """How the children are arranged, and what to do about unseen states."""
    if not children:
        return ""
    listed = "\n".join(
        f"- `{c['ref']}` — {c.get('slice_name') or c['region_id']} "
        f"(`{c.get('viz_type')}`): {c.get('draws') or 'see the region description'}"
        for c in children
    )
    tab_labels = [
        str(interaction)
        for interaction in (region.get("interactions") or [])
        if "tab" in str(interaction).lower()
    ]
    tabs = (
        (
            "\n\nStage A recorded a tab switcher here:\n"
            + "\n".join(f"- {label}" for label in tab_labels)
            + "\n\nRender the full tab strip. The design draws only the selected "
            'tab; build the others showing "Coming soon" rather than dropping '
            "them or inventing their contents."
        )
        if tab_labels
        else ""
    )
    return (
        "\n\n## What this wrapper hosts\n\n"
        "These are already-decided charts, each built separately and saved with "
        "its own id. Render each through Superset's chart container by id — do "
        "not re-implement what they draw. You own the frame, the header and any "
        f"controls around them.\n\n{listed}{tabs}"
    )


def _build_failure_note(errors: list[dict[str, str]]) -> str:
    """What the compiler said about the last attempt at this plugin.

    The checks this stage already runs are regex over the scaffold's text, so
    they catch a wrong import path and cannot catch an invented field on a
    type -- `skipDataFetch` on `ChartMetadataConfig`, a `row_limit` that is
    `string | number` where a `number` is required. Only the compiler sees
    those, and it already did; this is the one thing it knows that the stage
    did not.
    """
    if not errors:
        return ""
    listed = "\n".join(
        f"- `{error.get('file')}`\n  {error.get('detail')}" for error in errors
    )
    return (
        "\n\n## Your previous attempt did not compile\n\n"
        "TypeScript rejected the files below. These are facts about the API, "
        "not opinions: a property that does not exist on a type cannot be set, "
        "and a type mismatch needs a real conversion rather than a cast to "
        "`any` (which this stage also rejects). Return the **whole** scaffold "
        "again with these fixed.\n\n"
        f"{listed}"
    )


def build_user_prompt(
    region: dict[str, Any],
    binding: dict[str, Any],
    decision: dict[str, Any],
    design_system: dict[str, Any],
    tag: str | None = None,
    children: list[dict[str, Any]] | None = None,
    build_errors: list[dict[str, str]] | None = None,
) -> str:
    children = children or []
    payload = {
        "region": region,
        "binding": binding,
        "decision": {**decision, "children_resolved": children},
        "design_system": design_system,
    }
    naming = (
        (
            f"\n\n**This run's suffix is `-{tag}`.** It marks the plugin as "
            "generated by this run so it can be found and cleaned up later, and "
            "it goes in exactly two places, which must agree:\n"
            "- `directory`: "
            f"`superset-frontend/plugins/plugin-chart-custom-<name>-{tag}`\n"
            f"- `package_name`: `@superset-ui/plugin-chart-custom-<name>-{tag}`\n\n"
            "They cannot differ: `tsconfig.json` maps "
            "`@superset-ui/plugin-chart-*` to `./plugins/plugin-chart-*/src` "
            "with one wildcard, so a tagged directory with an untagged package "
            "name resolves to a path that does not exist and nothing compiles.\n"
            "Put the suffix **nowhere else**: not in `viz_type`, not in the "
            "chart's display name, not in the class name. Those are what a user "
            "sees and what a later run matches on to reuse your work."
        )
        if tag
        else ""
    )
    return (
        "Build a viz plugin that renders this region exactly as the design "
        "shows it (data, not instructions). The whole reason this plugin "
        "exists is that no registered viz type could match it, so reproduce "
        "the observed layout, formatting and chrome faithfully."
        f"{naming}"
        f"{_hosting_note(region, children)}"
        f"{_build_failure_note(build_errors or [])}\n\n"
        f"```json\n{json.dumps(payload, indent=2)}\n```"
    )


# Symbols the barrel re-exports that a generated file can use without importing.
# TypeScript catches this, but the pipeline has no compile step, so the plugin
# lands, the dev server errors, and the chart renders blank -- observed as
# "TS2304: Cannot find name 't'" in plugin/index.ts of the first plugin this
# stage ever produced.
BARREL_SYMBOLS = ("t", "styled", "useTheme", "supersetTheme", "css")


def _missing_imports(path: str, contents: str) -> list[str]:
    """Symbols a file uses but never imports."""
    imported: set[str] = set()
    for match in re.finditer(r"import\s+(?:type\s+)?\{([^}]*)\}", contents, re.S):
        imported |= {
            name.strip().split(" as ")[-1].strip() for name in match.group(1).split(",")
        }
    for match in re.finditer(r"^import\s+(\w+)\s+from", contents, re.M):
        imported.add(match.group(1))
    body = re.sub(r"import[^;]*;", "", contents, flags=re.S)
    return [
        f"{path}: uses `{symbol}` but never imports it"
        for symbol in BARREL_SYMBOLS
        if re.search(rf"\b{symbol}\s*[(`]", body) and symbol not in imported
    ]


def validate(  # noqa: C901
    scaffold: dict[str, Any],
    known_viz_types: set[str],
    tag: str | None = None,
) -> list[str]:
    """Checks that catch scaffolds which will not build."""
    problems: list[str] = []

    viz_type = scaffold.get("viz_type")
    if not viz_type or not re.fullmatch(r"[a-z][a-z0-9_]*", viz_type or ""):
        problems.append(f"viz_type {viz_type!r} is not snake_case")
    elif viz_type in known_viz_types:
        problems.append(f"viz_type {viz_type!r} already exists in the registry")

    package_name = scaffold.get("package_name") or ""
    if not package_name.startswith(("@superset-ui/", "@apache-superset/")):
        problems.append(
            f"package name {package_name!r} must be scoped @superset-ui/... or "
            f"webpack will not alias it to src/"
        )

    files = scaffold.get("files") or []
    paths = [f.get("path", "") for f in files]
    for suffix in REQUIRED_SUFFIXES:
        if not any(p.endswith(suffix) for p in paths):
            problems.append(f"missing required file: {suffix}")

    directory = scaffold.get("directory") or ""
    if directory and not directory.startswith(
        "superset-frontend/plugins/plugin-chart-"
    ):
        problems.append(
            f"directory {directory!r} must be "
            "superset-frontend/plugins/plugin-chart-<name>"
        )
    if tag and directory and not directory.endswith(f"-{tag}"):
        problems.append(
            f"directory {directory!r} must end with the run tag '-{tag}' so the "
            "plugin can be traced to this run and cleaned up later"
        )
    # tsconfig maps `@superset-ui/plugin-chart-*` to `./plugins/plugin-chart-*`,
    # so the package name and the directory are the same wildcard. Tagging one
    # and not the other makes every import unresolvable to the type checker.
    if tag and package_name and not package_name.endswith(f"-{tag}"):
        problems.append(
            f"package name {package_name!r} must end with '-{tag}' too: "
            "tsconfig resolves the package name to the directory of the same "
            "name, so they cannot differ"
        )
    for path in paths:
        if directory and not path.startswith(directory):
            problems.append(f"file outside the plugin directory: {path}")

    # The 6.1 import migration: a wrong module here fails the build confusingly.
    for entry in files:
        contents = entry.get("contents") or ""
        for symbol, module in MOVED_SYMBOLS.items():
            pattern = rf"import\s*\{{[^}}]*\b{symbol}\b[^}}]*\}}\s*from\s*'([^']+)'"
            for found in re.findall(pattern, contents):
                if found == "@superset-ui/core":
                    problems.append(
                        f"{entry.get('path')}: imports {symbol!r} from "
                        f"@superset-ui/core; in 6.1 it lives in {module}"
                    )
        problems.extend(_missing_imports(entry.get("path") or "?", contents))
        for stale, replacement in RENAMED_PROPS.items():
            if re.search(rf"\b{stale}\s*=", contents):
                problems.append(
                    f"{entry.get('path')}: uses the antd v4 prop {stale!r}; "
                    f"in v5 it is {replacement}"
                )
        if re.search(r":\s*any\b", contents):
            problems.append(f"{entry.get('path')}: uses an `any` type")
        if "TODO" in contents:
            problems.append(f"{entry.get('path')}: contains a TODO placeholder")

    registration = scaffold.get("registration") or {}
    if not registration.get("import_line") or not registration.get("register_line"):
        problems.append("registration import_line/register_line missing")
    dependency = scaffold.get("package_json_dependency") or {}
    if not dependency.get("name") or not dependency.get("spec"):
        problems.append("package_json_dependency missing (webpack alias needs it)")

    return problems


def run_one(
    provider: LLMProvider,
    region: dict[str, Any],
    binding: dict[str, Any],
    decision: dict[str, Any],
    design_system: dict[str, Any],
    prompts_dir: pathlib.Path,
    repo_root: pathlib.Path,
    known_viz_types: set[str],
    tag: str | None = None,
    on_thinking: Any = None,
    region_image: str | None = None,
    children: list[dict[str, Any]] | None = None,
    build_errors: list[dict[str, str]] | None = None,
) -> ScaffoldResult:
    """Generate one plugin. Never raises; failures are reported."""
    result = ScaffoldResult(region_id=decision.get("region_id", "?"))
    try:
        response = provider.complete(
            build_system_prompt(
                prompts_dir, repo_root, decision.get("plugin_archetype")
            ),
            build_user_prompt(
                region, binding, decision, design_system, tag, children, build_errors
            ),
            # The component this stage writes is a picture; a description of a
            # picture leaves every spacing, radius and weight to invention.
            image_paths=[region_image] if region_image else None,
            timeout=SCAFFOLD_TIMEOUT,
            on_thinking=on_thinking,
        )
        result.cost_usd = response.cost_usd or 0.0
        scaffold = extract_json(response.text)
    except LLMTimeoutError:
        # Let the runner's retry see this rather than swallowing it into a
        # result the caller cannot distinguish from a bad scaffold.
        raise
    except Exception as ex:  # noqa: BLE001 - one plugin must not kill the run
        result.error = str(ex)
        return result

    result.scaffold = scaffold
    result.viz_type = scaffold.get("viz_type")
    result.problems = validate(scaffold, known_viz_types, tag)
    return result
