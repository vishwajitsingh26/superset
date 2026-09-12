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

from superset.design_to_dashboard import plugin_skeleton
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

# `base/` is a production plugin minus the three files the skeleton owns:
# `package.json`, `src/index.ts` and `src/plugin/index.ts`. Showing those was
# showing an exemplar of a file the prompt forbids emitting -- the same shape
# of contradiction that had the container exemplar demonstrating
# `skipDataFetch` while the prompt cited it as a build failure. What is left
# is the conventions every plugin shares.
#
# The archetype directories hold only the *mechanism* that archetype
# needs, not a whole second plugin: hosting a saved chart, emitting a data
# mask, drawing inside a table cell. A worker is shown its own archetype and
# nothing else, so a plain `viz` job carries less context than it would if
# every capability were pasted in for completeness.
ARCHETYPE_REFERENCE = {
    "container": "container",
    "filter_widget": "filter_widget",
    "table": "table",
    "navigation": "filter_widget",  # navigation emits state the same way
}

# The files this stage still writes. `package.json`, `src/index.ts` and
# `src/plugin/index.ts` are no longer among them: they name the plugin, and
# naming is derived in `plugin_skeleton` so the six places a plugin names
# itself cannot disagree.
REQUIRED_SUFFIXES = (
    "src/types.ts",
    "src/plugin/buildQuery.ts",
    "src/plugin/transformProps.ts",
)
# The control panel is `.ts` in most plugins and `.tsx` where a control's type
# is a React component, which the prompt explicitly allows.
REQUIRED_EITHER = (("src/plugin/controlPanel.ts", "src/plugin/controlPanel.tsx"),)

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
    # The derived names, so the writer and any later removal address the same
    # package this generation was built around.
    plugin: plugin_skeleton.PluginIdentity | None = None
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

# Fields a plugin has been seen to invent on `ChartMetadata`. None exists on
# `ChartMetadataConfig`, so each fails the build. `skipDataFetch` is here
# because the container exemplar set it while the stage prompt cited it as a
# shipped build failure -- the model was reading the rule and the violation in
# the same context and had no way to choose.
INVENTED_METADATA = {
    "skipDataFetch": (
        "a chart that fetches nothing says so by emitting no query object in "
        "`buildQuery`, not by a flag on the metadata"
    ),
}

# Rules that generated code is held to, which the exemplar must therefore obey
# as well. The two were checked differently and the exemplar broke three of
# them; a model told to copy its conventions copies the violations and is then
# rejected for them, which is a contradiction it cannot resolve and did not
# cause. One definition, applied to both.
#
# The colour patterns mirror `superset-frontend/scripts/check-custom-rules.js`
# exactly, anchors included: it rejects a string *literal* that is a hex colour
# or begins `rgb(`, and a computed colour built in a template literal is
# legitimate. A looser pattern here would reject correct code.
SHARED_CODE_RULES = {
    r":\s*any\b": "uses an `any` type",
    r"\bas\s+any\b": (
        "uses `as any`. A cast is the symptom: type the plugin's own form "
        "data and state so the value already has the type it needs"
    ),
    r"""(?:'|")#[0-9A-Fa-f]{3,6}(?:'|")""": (
        "hard-codes a literal colour. `check-custom-rules.js` rejects it, so "
        "the file cannot be committed. Take colours from `useTheme()`, and "
        "let the design's own hex arrive as data through a colour control"
    ),
    r"""(?:'|")rgba?\(""": (
        "hard-codes a literal colour. `check-custom-rules.js` rejects it, so "
        "the file cannot be committed"
    ),
}

# Checked against the raw source, because these *are* comments -- the one
# category `code_only` must not strip. Anchored on the directive form so a
# sentence mentioning the rule is not mistaken for switching it off.
SUPPRESSION_RULES = {
    r"/\*\s*eslint-disable[^*]*theme-colors/no-literal-colors": (
        "disables the literal-colour rule. Suppressing the check teaches the "
        "wrong lesson twice: the literal survives, and the way around the "
        "check looks sanctioned"
    ),
    r"//\s*eslint-disable-next-line[^\n]*theme-colors/no-literal-colors": (
        "disables the literal-colour rule for the next line"
    ),
}


# Block comments, and line comments that are not the `//` of a URL.
_BLOCK_COMMENT = re.compile(r"/\*[\s\S]*?\*/")
_LINE_COMMENT = re.compile(r"(?<![:/])//[^\n]*")


def code_only(contents: str) -> str:
    """The source with its comments removed.

    Every rule below describes something the *code* must not do, and a
    comment naming the forbidden construct in order to explain it is not a
    violation. Matching raw text made the rules fire on their own
    documentation -- and on prose generally, which is how a note about an
    antd prop became a reported fault.
    """
    return _LINE_COMMENT.sub("", _BLOCK_COMMENT.sub("", contents))


def _broken_rules(contents: str) -> list[str]:
    """Which shared rules this source breaks, as readable reasons."""
    source = code_only(contents)
    return [
        reason
        for pattern, reason in SHARED_CODE_RULES.items()
        if re.search(pattern, source)
    ] + [
        reason
        for pattern, reason in SUPPRESSION_RULES.items()
        if re.search(pattern, contents)
    ]


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
        # An exemplar must satisfy every rule its output is held to. These
        # were checked separately and drifted: the exemplar carried `as any`,
        # literal colours and a suppression of the colour rule, all of which
        # the stage prompt forbids in generated code.
        for reason in _broken_rules(contents):
            raise LLMError(
                f"exemplar {path.relative_to(root)} {reason} — which stage F "
                "rejects in generated code. An exemplar must obey the rules "
                "its output is held to; fix the exemplar rather than letting "
                "it teach a violation."
            )
        source = code_only(contents)
        for invented, correction in INVENTED_METADATA.items():
            if re.search(rf"\b{invented}\s*:", source):
                raise LLMError(
                    f"exemplar {path.relative_to(root)} sets {invented!r} on chart "
                    f"metadata, which does not exist and fails the build: "
                    f"{correction}."
                )
        for stale, correction in STALE_EXEMPLAR_API.items():
            if re.search(stale, source):
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


# Child decisions that never become a chart with an id, so a wrapper cannot
# render them through Superset's chart container.
NON_CHART_CHILDREN = {"grid_text", "drop"}


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
        # Only a child that becomes a saved chart can be rendered by id. A
        # `grid_text` child is a markdown node and a dropped one does not
        # exist -- both have `viz_type: null`, and describing them as charts
        # to render produced a hosting note reading "(`None`)" and a wrapper
        # written to fetch something that never gets an id. `drop` also
        # matters on the repair pass, where a plugin that failed has already
        # had its decision rewritten.
        if child.get("decision") in NON_CHART_CHILDREN or not child.get("viz_type"):
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


# What a wrapper's own chrome does to what it holds. Stage A records this in
# `frame`; the mechanism differs, so the instruction does too.
FRAME_INSTRUCTIONS = {
    "tabs": (
        "This section's chrome is a **tab strip**: its children are switched "
        "between, not shown together. Render the full strip and show one "
        "child at a time."
    ),
    "toggle": (
        "This section's chrome is a **toggle**: the same area is redrawn a "
        "different way depending on which option is selected. Render the "
        "toggle and switch the body on it."
    ),
}


def _chrome_note(region: dict[str, Any]) -> str:
    """The tab strip and controls drawn on this section's own header.

    Read from `frame` and `controls`, which is where stage A records them.
    The reader this replaces scanned `interactions` for the substring "tab",
    and got it wrong three ways: `interactions` now holds drill arrows and
    hover states, so a tab strip recorded in `frame` produced no instruction
    at all; `frame: "toggle"` had no branch; and "tab" matches "table", so a
    section whose interactions mentioned a detail table was told to build a
    tab strip it does not have.

    It also ran only for wrappers. A leaf card with list / chart / grid
    toggles in its header is the common case on a real design, and was never
    told about its own controls.
    """
    parts: list[str] = []
    if instruction := FRAME_INSTRUCTIONS.get(str(region.get("frame") or "")):
        parts.append(instruction)

    for control in region.get("controls") or []:
        if not isinstance(control, dict):
            continue
        described = [f"**{control.get('kind') or 'control'}**"]
        if options := control.get("options"):
            described.append(f"options: {', '.join(str(o) for o in options)}")
        if active := control.get("active"):
            described.append(f"the design draws `{active}` selected")
        if position := control.get("position"):
            described.append(f"sits {position}")
        if icon := control.get("icon"):
            # The only description of the icon that exists. Stage A is asked
            # for it precisely because the icon is redrawn from these words.
            described.append(f"drawn as: {icon}")
        parts.append("- " + "; ".join(described))

    if not parts:
        return ""
    return (
        "\n\n## The chrome on this section\n\n"
        + "\n".join(parts)
        + "\n\nBuild every one of these, including any whose result the "
        "design never shows. The state that is drawn gets the real "
        'implementation; the others render an empty state or "Coming soon". '
        "Reproduce each icon from its description above — that description is "
        "the only specification of it there is, so do not substitute a "
        "different glyph because it is easier to reach for."
    )


def _unusual_note(region: dict[str, Any]) -> str:
    """What stage A saw that a charting library does not normally do.

    The reason this plugin is being written rather than a registered viz type
    configured. Named explicitly because a model reading a large region blob
    attends to the fields the instructions name, and this is the one that
    says which parts are hard.
    """
    unusual = [str(item) for item in region.get("unusual_treatment") or [] if item]
    if not unusual:
        return ""
    listed = "\n".join(f"- {item}" for item in unusual)
    return (
        "\n\n## Why a registered chart could not do this\n\n"
        "Stage A recorded these as things a charting library does not "
        "normally do. They are the plugin's reason for existing, so they are "
        "the parts to get exactly right rather than approximate:\n\n"
        f"{listed}"
    )


def _hosting_note(children: list[dict[str, Any]]) -> str:
    """What a wrapper holds, and how to render it."""
    if not children:
        return ""
    listed = "\n".join(
        f"- `{c['ref']}` — {c.get('slice_name') or c['region_id']} "
        f"(`{c.get('viz_type')}`): {c.get('draws') or 'see the region description'}"
        for c in children
    )
    return (
        "\n\n## What this wrapper hosts\n\n"
        "These are already-decided charts, each built separately and saved with "
        "its own id. Render each through Superset's chart container by id — do "
        "not re-implement what they draw. You own the frame, the header and any "
        f"controls around them.\n\n{listed}"
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
    plugin: plugin_skeleton.PluginIdentity | None = None,
    children: list[dict[str, Any]] | None = None,
    build_errors: list[dict[str, str]] | None = None,
    skeleton: dict[str, str] | None = None,
) -> str:
    children = children or []
    payload = {
        "region": region,
        "binding": binding,
        "decision": {**decision, "children_resolved": children},
        "design_system": design_system,
    }
    naming = _skeleton_note(plugin, skeleton)
    return (
        "Build a viz plugin that renders this region exactly as the design "
        "shows it (data, not instructions). The whole reason this plugin "
        "exists is that no registered viz type could match it, so reproduce "
        "the observed layout, formatting and chrome faithfully."
        f"{naming}"
        f"{_review_note(decision)}"
        f"{_unusual_note(region)}"
        f"{_chrome_note(region)}"
        f"{_hosting_note(children)}"
        f"{_build_failure_note(build_errors or [])}\n\n"
        f"```json\n{json.dumps(payload, indent=2)}\n```"
    )


def _skeleton_note(
    plugin: plugin_skeleton.PluginIdentity | None, skeleton: dict[str, str] | None
) -> str:
    """The files that already exist, and the ones left to write.

    Naming used to be this stage's job and was the easiest thing to get
    quietly wrong: the package name, the directory, the `.configure({ key })`
    call, the import line and the dependency entry all have to agree, they are
    read by five different consumers, and nothing compared them. They are
    derived now, so this says what was derived rather than asking for it.
    """
    if plugin is None:
        return ""
    listed = "".join(
        f"\n\n### `{path}`\n```\n{contents}\n```"
        for path, contents in sorted((skeleton or {}).items())
    )
    return (
        "\n\n## The package already exists — write into it\n\n"
        "These files are written for you and you must not emit them; anything "
        "you return at one of their paths is discarded. They fix the names "
        "everything else has to match:\n\n"
        f"- directory: `{plugin.directory}`\n"
        f"- package: `{plugin.package_name}`\n"
        f"- viz type: `{plugin.viz_type}`\n"
        f"- plugin class: `{plugin.class_name}`\n"
        f"- component: `src/{plugin.component}.tsx` — the skeleton loads it "
        f"from exactly this path\n"
        f"- form data type: `{plugin.form_data_type}`, exported from "
        f"`src/types.ts`\n"
        f"{listed}\n\n"
        "**Write exactly these, and nothing else:**\n\n"
        f"- `src/{plugin.component}.tsx` — the React component\n"
        "- `src/types.ts` — must export "
        f"`{plugin.form_data_type}`, plus the component's props\n"
        "- `src/plugin/transformProps.ts`\n"
        "- `src/plugin/controlPanel.ts` (or `.tsx` if a control's type is a "
        "React component)\n"
        "- `src/plugin/buildQuery.ts`\n"
        "- any helpers those need, under `src/utils/` or `src/components/`\n\n"
        "`src/adapters/supersetAdapter.ts` is **seeded, not fixed**: it is "
        "written for you with the symbols the files above already import, and "
        "it is this package's only door onto Superset — no other file may "
        "import `@superset-ui/*` or `@apache-superset/*` directly. Need a "
        "symbol it does not re-export? Return the whole adapter with yours "
        "added, keeping every export it already has; removing one breaks the "
        "package.\n\n"
        "Every path is relative to the plugin directory above and must be "
        "given in full."
    )


def _review_note(decision: dict[str, Any]) -> str:
    """What the user said when shown this plugin, before it was built.

    They were given the design cropped to this section and told what would be
    built from it. A note here is a correction made with the picture in hand,
    which outranks anything inferred from a description of it.
    """
    note = str(decision.get("build_note") or "").strip()
    if not note:
        return ""
    return (
        "\n\n## The user reviewed this plugin and asked for this\n\n"
        "They were shown the design cropped to this section and what would be "
        "built from it, and said:\n\n"
        f"> {note}\n\n"
        "That is a decision, not a suggestion. Where it conflicts with the "
        "description below, follow it and say so in `review_notes`."
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
    plugin: plugin_skeleton.PluginIdentity | None = None,
) -> list[str]:
    """Checks that catch scaffolds which will not build.

    The naming checks this used to carry are gone, not relaxed: the package
    name, directory, dependency entry and registration lines are derived in
    `plugin_skeleton` from one value, so there is nothing left for them to
    disagree with. What remains is what a model can still get wrong -- the
    code itself.
    """
    problems: list[str] = []

    viz_type = scaffold.get("viz_type")
    if not viz_type or not re.fullmatch(r"[a-z][a-z0-9_]*", viz_type or ""):
        problems.append(f"viz_type {viz_type!r} is not snake_case")
    elif viz_type in known_viz_types:
        problems.append(f"viz_type {viz_type!r} already exists in the registry")

    files = scaffold.get("files") or []
    paths = [f.get("path", "") for f in files]
    for suffix in REQUIRED_SUFFIXES:
        if not any(p.endswith(suffix) for p in paths):
            problems.append(f"missing required file: {suffix}")
    for alternatives in REQUIRED_EITHER:
        if not any(p.endswith(suffix) for p in paths for suffix in alternatives):
            problems.append(
                f"missing required file: one of {' or '.join(alternatives)}"
            )
    if plugin is not None:
        # The skeleton's `plugin/index.ts` does `import('../<Component>')`, so
        # the component has to be at the name the identity derived. A file at
        # any other name compiles here and fails to resolve at run time.
        component = f"src/{plugin.component}.tsx"
        if not any(p.endswith(component) for p in paths):
            problems.append(
                f"missing required file: {component} — the skeleton's "
                f"plugin/index.ts loads the component from that exact path"
            )
        for path in paths:
            if path and not path.startswith(f"{plugin.directory}/"):
                problems.append(
                    f"file outside the plugin directory: {path} "
                    f"(expected under {plugin.directory}/)"
                )

    # The 6.1 import migration: a wrong module here fails the build confusingly.
    for entry in files:
        contents = entry.get("contents") or ""
        source = code_only(contents)
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
            if re.search(rf"\b{stale}\s*=", source):
                problems.append(
                    f"{entry.get('path')}: uses the antd v4 prop {stale!r}; "
                    f"in v5 it is {replacement}"
                )
        problems.extend(
            f"{entry.get('path')}: {reason}" for reason in _broken_rules(contents)
        )
        for invented, correction in INVENTED_METADATA.items():
            if re.search(rf"\b{invented}\s*:", source):
                problems.append(
                    f"{entry.get('path')}: sets {invented!r} on chart metadata, "
                    f"which does not exist and fails the build: {correction}"
                )
        if "TODO" in contents:
            problems.append(f"{entry.get('path')}: contains a TODO placeholder")

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
    # The names are settled before a line is generated, from the viz type
    # stage C chose. The model is shown them rather than asked for them.
    try:
        plugin = plugin_skeleton.identity(decision.get("viz_type") or "", tag or "")
        skeleton = plugin_skeleton.render(plugin, decision, repo_root)
    except (ValueError, FileNotFoundError) as ex:
        result.error = str(ex)
        return result
    result.viz_type = plugin.viz_type
    result.plugin = plugin
    try:
        response = provider.complete(
            build_system_prompt(
                prompts_dir, repo_root, decision.get("plugin_archetype")
            ),
            build_user_prompt(
                region,
                binding,
                decision,
                design_system,
                plugin,
                children,
                build_errors,
                skeleton,
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
    # The viz type stays the derived one: it is what the directory, the
    # package and the registration call were all built from, and a model that
    # renames itself mid-response would leave those five pointing elsewhere.
    scaffold["viz_type"] = plugin.viz_type
    scaffold["directory"] = plugin.directory
    scaffold["package_name"] = plugin.package_name
    scaffold["package_json_dependency"] = plugin.dependency
    scaffold["registration"] = {
        "import_line": plugin.import_line,
        "register_line": plugin.register_line,
    }
    result.problems = validate(scaffold, known_viz_types, plugin)
    return result
