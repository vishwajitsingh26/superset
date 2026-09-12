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
"""The part of a plugin that is the same every time.

A Superset plugin is a package name, a directory, a registration call, an
import line, a dependency entry and a ``ChartPlugin`` subclass -- six things
that must agree exactly, and none of which involve looking at the design. Stage
F used to write all six, and a model that gets one of them subtly wrong
produces a plugin that installs, compiles and never appears: `viz_type` says
one thing, the `.configure({ key })` call says another, and nothing compares
them because they are read by different consumers.

So they are derived here instead, from one value. Naming stops being something
that can disagree with itself, and the generation stage is left with the files
that actually need the picture: the component, its props, its controls and its
query.

The file list follows Superset's own plugin generator
(``packages/generator-superset/generators/plugin-chart``), which is the
canonical answer to what a plugin package contains. Its templates are not used:
they import ``t`` from ``@superset-ui/core``, which moved in 6.1, so a plugin
scaffolded from them fails the very check stage F runs on generated code.
"""

from __future__ import annotations

import logging
import pathlib
import re
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

SKELETON = "design-to-dashboard/assets/plugin-skeleton"
PLUGIN_ROOT = "superset-frontend/plugins"
PACKAGE_SCOPE = "@superset-ui"

# Behaviours a plugin may declare, and the archetype that implies each. A
# wrapper hosts charts that cross-filter on their own; a filter is what emits
# the mask. Asking a model to choose produced `Behavior.NativeFilter` on a
# plain bar chart, which puts it in the filter picker.
ARCHETYPE_BEHAVIORS = {
    "viz": ["InteractiveChart", "DrillToDetail", "DrillBy"],
    "table": ["InteractiveChart", "DrillToDetail"],
    "container": ["InteractiveChart"],
    "filter_widget": ["InteractiveChart", "NativeFilter"],
    "navigation": ["InteractiveChart", "NativeFilter"],
}
ARCHETYPE_CATEGORY = {
    "viz": "Custom Charts",
    "table": "Table",
    "container": "Custom Charts",
    "filter_widget": "Filter",
    "navigation": "Filter",
}


@dataclass(frozen=True)
class PluginIdentity:
    """Every name a plugin needs, derived from its viz type and run tag.

    One source, so the six places a plugin names itself cannot disagree. The
    tag goes on the directory and the package name and nowhere else: those two
    are resolved against each other by one tsconfig wildcard, while the
    `viz_type`, the class and the display name are what a user sees and what a
    later run matches on to reuse the work.
    """

    viz_type: str
    tag: str
    slug: str
    directory: str
    package_name: str
    class_name: str
    component: str
    display_name: str
    form_data_type: str

    @property
    def import_line(self) -> str:
        return f"import {{ {self.class_name} }} from '{self.package_name}';"

    @property
    def register_line(self) -> str:
        return (
            f"new {self.class_name}()"
            f".configure({{ key: '{self.viz_type}' }}).register();"
        )

    @property
    def dependency(self) -> dict[str, str]:
        """The `file:` entry for `superset-frontend/package.json`.

        Relative to that file, so the `plugins/` segment is part of it. Built
        from the leaf alone it was `file:./plugin-chart-x`, and both gates
        passed it: `npm install` still links the package through the
        `plugins/*` workspace glob, and `tsc` resolves the import through
        tsconfig's own wildcard. Only webpack reads the spec -- it aliases
        the package to `superset-frontend/plugin-chart-x/src`, which does not
        exist, and refuses any fallback once an alias matches. The bundle
        fails on `setupPluginsExtra.ts`, so nothing on the page renders.
        """
        return {
            "name": self.package_name,
            "spec": f"file:./{self.directory.removeprefix('superset-frontend/')}",
        }

    @property
    def leaf(self) -> str:
        return self.directory.rsplit("/", 1)[-1]


def _pascal(value: str) -> str:
    return "".join(
        part[:1].upper() + part[1:] for part in re.split(r"[^a-z0-9]+", value) if part
    )


def identity(viz_type: str, tag: str) -> PluginIdentity:
    """Derive every name from the viz type the model chose, plus the run tag.

    The viz type is the only thing the model still names, because it is the
    only one that needs to describe the design. Everything else follows from
    it by rule.
    """
    # Runs collapse: `CUSTOM__CARD` and `Custom-Card!!` are the same plugin,
    # and a doubled underscore in the slug becomes a doubled hyphen in the
    # directory, which no longer matches the package name it is resolved
    # against.
    clean = re.sub(r"_+", "_", re.sub(r"[^a-z0-9]+", "_", (viz_type or "").lower()))
    clean = clean.strip("_")
    if not clean:
        raise ValueError("a plugin needs a viz_type to derive its name from")
    slug = clean.replace("_", "-")
    tagged = f"{slug}-{tag}" if tag else slug
    pascal = _pascal(clean)
    return PluginIdentity(
        viz_type=clean,
        tag=tag,
        slug=slug,
        directory=f"{PLUGIN_ROOT}/plugin-chart-{tagged}",
        package_name=f"{PACKAGE_SCOPE}/plugin-chart-{tagged}",
        class_name=f"{pascal}Plugin",
        component=pascal,
        display_name=" ".join(
            word.capitalize() for word in clean.replace("custom_", "").split("_")
        ).strip()
        or pascal,
        form_data_type=f"{pascal}FormData",
    )


# Long enough to be a real description, short enough to stay on one line
# after prettier.
DESCRIPTION_LIMIT = 160


def _one_line(text: str) -> str:
    """Text safe to drop inside `t('...')` **and** inside a JSON string.

    Stage C's rationale is free-form prose and it lands in two places with
    different syntax: a single-quoted TypeScript string, where an apostrophe
    closes it, and `package.json`'s `description`, where a double quote does.
    Escaping only the apostrophe left a rationale quoting the design -- `a
    "hero" KPI` -- writing invalid JSON, which fails `npm install` with
    EJSONPARSE while the type-check stays green. A newline breaks both.

    Both quotes become their typographic form rather than being escaped:
    one value has to be valid in two syntaxes, and a character that needs no
    escaping in either is the only thing that is.
    """
    collapsed = " ".join(str(text).split()).replace("\\", "")
    collapsed = collapsed.replace("'", "\u2019").replace('"', "\u201d")
    if len(collapsed) > DESCRIPTION_LIMIT:
        collapsed = collapsed[: DESCRIPTION_LIMIT - 1].rstrip() + "\u2026"
    return collapsed


def _render(template: str, values: dict[str, str]) -> str:
    for key, value in values.items():
        template = template.replace("{{" + key + "}}", value)
    return template


def render(
    plugin: PluginIdentity,
    decision: dict[str, Any],
    repo_root: str | pathlib.Path,
) -> dict[str, str]:
    """The skeleton files for one plugin, as ``{repo-relative path: contents}``.

    Read from disk rather than held as strings in Python, so the skeleton can
    be read, reviewed and checked as source -- including by the same rules the
    generated files are held to.
    """
    root = pathlib.Path(repo_root) / SKELETON
    archetype = decision.get("plugin_archetype") or "viz"
    behaviors = ARCHETYPE_BEHAVIORS.get(archetype) or ARCHETYPE_BEHAVIORS["viz"]
    # Stage C may name behaviours explicitly; where it does, it has seen the
    # design and the archetype default has not.
    if named := [b for b in decision.get("behaviors") or [] if isinstance(b, str)]:
        behaviors = named
    description = _one_line(
        decision.get("rationale") or f"Generated for {plugin.display_name}."
    )
    values = {
        "package_name": plugin.package_name,
        "class_name": plugin.class_name,
        "component": plugin.component,
        "display_name": _one_line(plugin.display_name),
        "form_data_type": plugin.form_data_type,
        "description": description,
        "category": ARCHETYPE_CATEGORY.get(archetype, "Custom Charts"),
        "behaviors": ", ".join(f"Behavior.{name}" for name in behaviors),
        "tags": ", ".join(f"t('{tag}')" for tag in ("Custom Charts", "Generated")),
    }
    rendered: dict[str, str] = {}
    for template in sorted(root.rglob("*.tmpl")):
        relative = template.relative_to(root).as_posix().removesuffix(".tmpl")
        rendered[f"{plugin.directory}/{relative}"] = _render(
            template.read_text(encoding="utf-8"), values
        )
    if not rendered:
        raise FileNotFoundError(f"no plugin skeleton at {root}")
    return rendered


# Written by the skeleton but NOT owned: a generated file at one of these
# paths replaces it. The adapter is a re-export barrel, and which symbols a
# plugin needs depends on what it draws -- so it is seeded with the ones
# `src/plugin/index.ts` imports, and extended by whoever writes the rest.
#
# Seeding it at all is the fix for the skeleton importing a file nothing
# wrote: `src/plugin/index.ts` takes every symbol through the barrel, so an
# absent barrel is a package that cannot compile before a line of it is read.
SEEDED = ("src/adapters/supersetAdapter.ts",)


def owned_paths(plugin: PluginIdentity, repo_root: str | pathlib.Path) -> set[str]:
    """Skeleton paths a generated file must not replace."""
    seeded = {f"{plugin.directory}/{name}" for name in SEEDED}
    return set(render(plugin, {}, repo_root)) - seeded
