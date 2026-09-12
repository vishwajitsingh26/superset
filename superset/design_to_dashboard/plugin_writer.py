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
"""Write a generated plugin to disk and register it.

Three artifacts are required or the plugin will not load:

1. the package files themselves
2. a ``file:`` dependency in ``superset-frontend/package.json`` -- webpack only
   aliases a scoped ``file:`` dependency to its ``src/``; without the entry the
   import resolves to ``main: lib/index.js``, which dev never builds
3. a registration call inside ``setupPluginsExtra()`` -- the deployment override
   hook, so ``MainPreset.ts`` (upstream) stays untouched

Every step is idempotent, so re-running a plugin does not duplicate entries.
"""

from __future__ import annotations

import logging
import os
import pathlib
import re
import shutil
from dataclasses import dataclass, field
from typing import Any

from superset.design_to_dashboard import plugin_skeleton
from superset.utils import json

logger = logging.getLogger(__name__)

PACKAGE_JSON = "superset-frontend/package.json"
SETUP_EXTRA = "superset-frontend/src/setup/setupPluginsExtra.ts"


class PluginWriteError(Exception):
    """Raised when a scaffold cannot be written safely."""


@dataclass
class WriteResult:
    viz_type: str
    directory: str
    files_written: list[str] = field(default_factory=list)
    dependency_added: bool = False
    registered: bool = False
    notes: list[str] = field(default_factory=list)


def write(  # noqa: C901
    scaffold: dict[str, Any],
    repo_root: str | pathlib.Path,
    plugin: plugin_skeleton.PluginIdentity | None = None,
    decision: dict[str, Any] | None = None,
) -> WriteResult:
    """Write the skeleton and the generated files, and register the plugin.

    ``plugin`` carries the derived names. When it is given, the directory,
    package name, dependency entry and registration lines all come from it
    rather than from the scaffold: those six names have to agree exactly, and
    nothing downstream compares them, so a model that spells one differently
    produces a plugin that installs, compiles and never appears.
    """
    root = pathlib.Path(repo_root).resolve()
    viz_type = plugin.viz_type if plugin else scaffold["viz_type"]
    directory = plugin.directory if plugin else scaffold["directory"]
    result = WriteResult(viz_type=viz_type, directory=directory)

    # ---- 1. files -----------------------------------------------------------
    # The skeleton first: a generated file at one of its paths is discarded
    # rather than merged, because rewriting `package.json` renames the package
    # out from under the directory it is resolved against.
    files: dict[str, str] = {}
    owned: set[str] = set()
    if plugin is not None:
        files = plugin_skeleton.render(plugin, decision or {}, root)
        # Not every skeleton file is owned. The adapter barrel is seeded so
        # the package compiles before anything is generated, and replaced
        # when the author extends it with the symbols their chart needs.
        owned = plugin_skeleton.owned_paths(plugin, root)
    for entry in scaffold.get("files") or []:
        relative = entry["path"]
        if relative in owned:
            result.notes.append(f"kept the skeleton's {relative}")
            continue
        files[relative] = entry.get("contents") or ""

    # A rewrite replaces the package rather than adding to it. `write` only
    # ever added files, and the one path that calls it twice is the compile
    # repair -- exactly where the file set is most likely to change. A helper
    # the first attempt split out and the repair inlined stayed on disk,
    # still imported by nothing, still type-checked, and still able to fail
    # the build the repair was meant to fix.
    if plugin is not None:
        previous = (root / directory / "src").resolve()
        if previous.is_dir():
            shutil.rmtree(previous, ignore_errors=True)
            result.notes.append("replaced the previous attempt's src/")

    for relative, contents in files.items():
        target = (root / relative).resolve()
        # Never write outside the plugin directory. `os.path.commonpath`
        # rather than a string prefix: `plugin-chart-card-x` is a prefix of
        # `plugin-chart-card-xy`, so a sibling directory escaped the check.
        plugin_dir = (root / directory).resolve()
        if os.path.commonpath([str(target), str(plugin_dir)]) != str(plugin_dir):
            raise PluginWriteError(f"refusing to write outside {directory}: {relative}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(contents, encoding="utf-8")
        result.files_written.append(relative)

    # plugin/index.ts imports a thumbnail; without the file the build fails.
    # The placeholder lives in this feature's own tree rather than being
    # borrowed from another plugin, so deleting any plugin cannot break the
    # generator.
    thumbnail = root / directory / "src" / "images" / "thumbnail.png"
    if not thumbnail.exists():
        thumbnail.parent.mkdir(parents=True, exist_ok=True)
        reference = root / "design-to-dashboard/assets/plugin-thumbnail-placeholder.png"
        if reference.exists():
            thumbnail.write_bytes(reference.read_bytes())
            result.notes.append("copied a placeholder thumbnail.png")
        else:
            result.notes.append("WARNING: no thumbnail.png and no reference to copy")

    # ---- 2. package.json dependency ----------------------------------------
    dependency = (
        plugin.dependency if plugin else (scaffold.get("package_json_dependency") or {})
    )
    name, spec = dependency.get("name"), dependency.get("spec")
    if name and spec:
        pkg_path = root / PACKAGE_JSON
        payload = json.loads(pkg_path.read_text(encoding="utf-8"))
        deps = payload.setdefault("dependencies", {})
        if deps.get(name) != spec:
            deps[name] = spec
            # Keep dependencies sorted, as the file already is, so the diff is
            # one line rather than a reordering of the whole block.
            payload["dependencies"] = dict(sorted(deps.items()))
            pkg_path.write_text(
                json.dumps(payload, indent=2) + "\n",
                encoding="utf-8",
            )
            result.dependency_added = True

    # ---- 3. registration ----------------------------------------------------
    if plugin is not None:
        import_line, register_line = plugin.import_line, plugin.register_line
    else:
        registration = scaffold.get("registration") or {}
        import_line = (registration.get("import_line") or "").strip()
        register_line = (registration.get("register_line") or "").strip()
    if import_line and register_line:
        setup_path = root / SETUP_EXTRA
        source = setup_path.read_text(encoding="utf-8")
        if register_line in source:
            result.notes.append("already registered")
        else:
            if import_line not in source:
                # Imports go after the licence header, before the function.
                marker = "export default function setupPluginsExtra"
                index = source.index(marker)
                source = source[:index] + import_line + "\n\n" + source[index:]
            source = _insert_into_setup(source, register_line)
            setup_path.write_text(source, encoding="utf-8")
            result.registered = True

    logger.info(
        "wrote plugin %s: %d file(s), dependency=%s registered=%s",
        viz_type,
        len(result.files_written),
        result.dependency_added,
        result.registered,
    )
    return result


def _insert_into_setup(source: str, register_line: str) -> str:
    """Add a registration call inside setupPluginsExtra()'s body.

    Handles both shapes the file takes: the empty `{}` it ships with, and a
    populated multi-line body once plugins have been added.
    """
    signature = re.compile(
        r"export default function setupPluginsExtra\(\)\s*(?::\s*void\s*)?\{"
    )
    match = signature.search(source)
    if not match:
        raise PluginWriteError(
            "could not find setupPluginsExtra() to register the plugin"
        )

    open_brace = match.end() - 1
    depth = 0
    close_brace = None
    for index in range(open_brace, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                close_brace = index
                break
    if close_brace is None:
        raise PluginWriteError("setupPluginsExtra() body is unbalanced")

    body = source[open_brace + 1 : close_brace].rstrip()
    # Prettier runs over this file in pre-commit, and it expects the two-space
    # indent of a function body. Writing the call flush left fails the hook.
    call = f"  {register_line}"
    new_body = f"{body}\n{call}\n" if body else f"\n{call}\n"
    return source[: open_brace + 1] + new_body + source[close_brace:]


def remove(scaffold: dict[str, Any], repo_root: str | pathlib.Path) -> list[str]:
    """Undo `write`, so a plugin that will not compile leaves no trace.

    A generated plugin that fails the type-checker and cannot be repaired is
    worse than a missing one: it is registered, so it breaks the build for
    every chart on the page, not just its own section. Dropping the section
    costs one card; leaving the plugin costs the dashboard.

    Best-effort by design -- each of the three artifacts is undone
    independently and a failure to undo one is reported rather than raised,
    because this runs on the path where something has already gone wrong.
    """
    root = pathlib.Path(repo_root).resolve()
    directory = scaffold.get("directory") or ""
    undone: list[str] = []

    if directory.startswith("superset-frontend/plugins/plugin-chart-"):
        target = (root / directory).resolve()
        # The prefix check above is what makes this safe; resolve() then
        # confirms no symlink walked the path somewhere else entirely.
        if target.is_dir() and str(target).startswith(
            str((root / "superset-frontend" / "plugins").resolve())
        ):
            shutil.rmtree(target, ignore_errors=True)
            undone.append(f"deleted {directory}")

    name = (scaffold.get("package_json_dependency") or {}).get("name")
    if name:
        pkg_path = root / PACKAGE_JSON
        try:
            payload = json.loads(pkg_path.read_text(encoding="utf-8"))
            if payload.get("dependencies", {}).pop(name, None) is not None:
                pkg_path.write_text(
                    json.dumps(payload, indent=2) + "\n", encoding="utf-8"
                )
                undone.append(f"unlisted {name}")
        except (OSError, ValueError) as ex:
            logger.warning("could not remove %s from package.json: %s", name, ex)

    registration = scaffold.get("registration") or {}
    lines = [
        (registration.get("import_line") or "").strip(),
        (registration.get("register_line") or "").strip(),
    ]
    if any(lines):
        setup_path = root / SETUP_EXTRA
        try:
            source = setup_path.read_text(encoding="utf-8")
            kept = [
                line
                for line in source.splitlines()
                if line.strip() not in {item for item in lines if item}
            ]
            rewritten = "\n".join(kept).rstrip() + "\n"
            if rewritten != source:
                setup_path.write_text(rewritten, encoding="utf-8")
                undone.append("unregistered")
        except OSError as ex:
            logger.warning("could not unregister %s: %s", name, ex)

    logger.info("removed plugin %s: %s", scaffold.get("viz_type"), "; ".join(undone))
    return undone
