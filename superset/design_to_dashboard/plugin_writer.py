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
import pathlib
import re
from dataclasses import dataclass, field
from typing import Any

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


def write(scaffold: dict[str, Any], repo_root: str | pathlib.Path) -> WriteResult:
    root = pathlib.Path(repo_root).resolve()
    viz_type = scaffold["viz_type"]
    directory = scaffold["directory"]
    result = WriteResult(viz_type=viz_type, directory=directory)

    # ---- 1. files -----------------------------------------------------------
    for entry in scaffold.get("files") or []:
        relative = entry["path"]
        target = (root / relative).resolve()
        # Never write outside the plugin directory the scaffold declared.
        if not str(target).startswith(str((root / directory).resolve())):
            raise PluginWriteError(f"refusing to write outside {directory}: {relative}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(entry.get("contents") or "", encoding="utf-8")
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
    dependency = scaffold.get("package_json_dependency") or {}
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
