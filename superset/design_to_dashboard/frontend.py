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
"""Make a freshly generated plugin visible to the running frontend.

`webpack.config.js` aliases a `file:` dependency to its source, but only if the
package is **already symlinked into `node_modules`**:

    const srcPath = path.join(APP_DIR, `./node_modules/${pkg}/src`);
    if (pkg.startsWith('@superset-ui') && fs.existsSync(srcPath)) { ... }

So a newly written plugin needs **both** steps, in order:

1. `npm install` -- creates the `node_modules` symlink for the new `file:`
   dependency. Without it the `existsSync` check fails, no alias is created, and
   the build fails with `Module not found`.
2. a dev-server **restart** -- the alias map is built when the config is
   evaluated, so a dependency added mid-session is invisible until then.

Restarting alone is not enough, and was the cause of a real `Module not found`
failure.

This restarts a dev server that was started detached. A dev server running in
someone's terminal is left alone; the caller is told to restart it instead.
"""

from __future__ import annotations

import logging
import os
import pathlib
import re
import signal
import subprocess  # noqa: S404 - fixed argv, no shell
import time
from typing import Any

logger = logging.getLogger(__name__)

DEV_SERVER_PORT = 9000
HEALTH_TIMEOUT = 120
NODE_BIN = pathlib.Path.home() / ".local" / "node22" / "bin"


def find_dev_server() -> int | None:
    """PID of the process listening on the dev-server port, if any."""
    try:
        completed = subprocess.run(  # noqa: S603
            ["lsof", "-nP", f"-iTCP:{DEV_SERVER_PORT}", "-sTCP:LISTEN", "-t"],  # noqa: S607
            capture_output=True,
            text=True,
            check=False,
            shell=False,
        )
    except FileNotFoundError:
        return None
    pids = [line for line in completed.stdout.split() if line.isdigit()]
    return int(pids[0]) if pids else None


# What the dev server prints when it finishes a compile. One of these appearing
# after a restart is the only honest signal that the code built -- `/health`
# answers 200 with type errors outstanding, so it reports that the server came
# back, not that the plugin exists.
_COMPILED = "compiled successfully"
_FAILED = re.compile(r"^Found \d+ errors? in ", re.M)
_ERROR_BLOCK = re.compile(
    r"^ERROR in (\S+)(.*?)(?=^ERROR in |^Found \d+ error)", re.M | re.S
)
# A compile of the whole frontend after a restart takes tens of seconds.
COMPILE_TIMEOUT = 300


def compile_errors(log_text: str) -> list[dict[str, str]]:
    """Every `ERROR in <file>` block webpack reported, as file + detail.

    Parsed from the dev server's own output rather than by running `tsc`: the
    compile has already happened, the result is already written to a log this
    module owns, and reading it costs nothing.
    """
    found = []
    for match in _ERROR_BLOCK.finditer(log_text + "\nFound 0 errors in "):
        detail = " ".join(match.group(2).split())
        found.append({"file": match.group(1), "detail": detail[:600]})
    return found


def _compile_verdict(log: pathlib.Path, offset: int, deadline: float) -> dict[str, Any]:
    """Wait for the compile that follows a restart, and say how it went."""
    while time.time() < deadline:
        try:
            with log.open("r", encoding="utf-8", errors="replace") as handle:
                handle.seek(offset)
                appended = handle.read()
        except OSError:
            appended = ""
        if _FAILED.search(appended):
            return {"compiled": False, "errors": compile_errors(appended)}
        if _COMPILED in appended:
            return {"compiled": True, "errors": []}
        time.sleep(2)
    return {
        "compiled": None,
        "errors": [],
        "reason": "the dev server did not report a compile result in time",
    }


# `<path>(line,col): error TSxxxx: <message>` -- one line per fault, unlike
# webpack's multi-line `ERROR in` blocks.
_TSC_ERROR = re.compile(r"^(\S+?)\((\d+),\d+\): error (TS\d+: .*)$", re.M)
# A cold type-check of the whole frontend. Slower than reading a log, and the
# only check that runs whether or not anyone is willing to restart a dev
# server.
TYPECHECK_TIMEOUT = 900


def typecheck_errors(output: str) -> list[dict[str, str]]:
    """Parse `tsc --noEmit` output into the shape the repair path expects.

    Same `{file, detail}` as `compile_errors`, so one repair path serves both
    and a caller never has to know which checker produced a fault.
    """
    return [
        {
            "file": match.group(1),
            "detail": f"line {match.group(2)}: {match.group(3)}"[:600],
        }
        for match in _TSC_ERROR.finditer(output)
    ]


def typecheck(repo_root: str | pathlib.Path) -> dict[str, Any]:
    """Type-check the frontend, and say which files are wrong.

    Stage F's own checks are regex over generated text: they catch a wrong
    import path and cannot catch a property invented on a type. Only a
    compiler sees those, and the compiler used to be the dev server -- which
    is opt-in, because restarting someone's dev server uninvited is rude.
    So on the common path nothing type-checked a generated plugin at all, and
    the run continued through chart configuration, layout and apply before
    anyone discovered the frontend would not build.

    Running `tsc` separates the two: checking is always safe and now always
    happens, while restarting stays a choice. Requires `npm install` to have
    linked the new plugins first, or every import of one is unresolvable.
    """
    frontend = pathlib.Path(repo_root) / "superset-frontend"
    env = dict(os.environ)
    if NODE_BIN.is_dir():
        env["PATH"] = f"{NODE_BIN}:{env.get('PATH', '')}"
    try:
        completed = subprocess.run(  # noqa: S603
            ["npx", "tsc", "--noEmit", "-p", "tsconfig.json"],  # noqa: S607
            cwd=str(frontend),
            env=env,
            capture_output=True,
            text=True,
            timeout=TYPECHECK_TIMEOUT,
            check=False,
            shell=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as ex:
        # Unknown, not clean. A checker that could not run must never read as
        # a pass -- that is the failure this whole function exists to remove.
        return {"compiled": None, "errors": [], "reason": f"tsc did not run: {ex}"}
    output = f"{completed.stdout}\n{completed.stderr}"
    errors = typecheck_errors(output)
    if completed.returncode == 0:
        return {"compiled": True, "errors": []}
    if not errors:
        return {
            "compiled": None,
            "errors": [],
            "reason": f"tsc exited {completed.returncode} with no parseable errors",
        }
    return {"compiled": False, "errors": errors}


def link_plugins(repo_root: str | pathlib.Path, timeout: int = 600) -> dict[str, Any]:
    """Run `npm install` so new `file:` dependencies are linked into node_modules."""
    frontend = pathlib.Path(repo_root) / "superset-frontend"
    env = dict(os.environ)
    if NODE_BIN.is_dir():
        env["PATH"] = f"{NODE_BIN}:{env.get('PATH', '')}"
    try:
        completed = subprocess.run(  # noqa: S603
            ["npm", "install", "--no-audit", "--no-fund"],  # noqa: S607
            cwd=str(frontend),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            shell=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as ex:
        return {"linked": False, "reason": f"npm install failed: {ex}"}
    if completed.returncode != 0:
        return {
            "linked": False,
            "reason": f"npm install exited {completed.returncode}: "
            f"{(completed.stderr or completed.stdout)[-300:]}",
        }
    return {"linked": True}


def restart_dev_server(repo_root: str | pathlib.Path) -> dict[str, Any]:
    """Link new plugins, then restart the dev server so aliases are rebuilt."""
    root = pathlib.Path(repo_root)
    frontend = root / "superset-frontend"

    linked = link_plugins(root)
    if not linked.get("linked"):
        return {"restarted": False, "reason": linked.get("reason")}

    pid = find_dev_server()

    if pid is None:
        return {
            "restarted": False,
            "reason": "no dev server is listening; start it to pick up the plugin",
        }

    env = dict(os.environ)
    if NODE_BIN.is_dir():
        env["PATH"] = f"{NODE_BIN}:{env.get('PATH', '')}"
    env["supersetPort"] = str(env.get("supersetPort") or 8088)

    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    # Give the port time to release before rebinding.
    for _ in range(20):
        if find_dev_server() is None:
            break
        time.sleep(0.5)

    log = root / "design-to-dashboard" / ".devserver.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    # Only this restart's output counts: the log is appended to across runs and
    # still holds the errors of every previous one.
    offset = log.stat().st_size if log.exists() else 0
    with log.open("ab") as handle:
        subprocess.Popen(  # noqa: S603
            ["npm", "run", "dev-server"],  # noqa: S607
            cwd=str(frontend),
            env=env,
            stdout=handle,
            stderr=handle,
            start_new_session=True,
            shell=False,
        )

    # Wait for the first compile so the caller knows the plugin is live.
    import urllib.error
    import urllib.request

    deadline = time.time() + HEALTH_TIMEOUT
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(  # noqa: S310 - fixed localhost URL
                f"http://127.0.0.1:{DEV_SERVER_PORT}/health", timeout=3
            ) as response:
                if response.status == 200:
                    # Up, but not necessarily built. Webpack answers /health
                    # with type errors outstanding, so reporting success here
                    # said the server restarted and was read as "the plugin is
                    # live" -- two plugins shipped that never compiled.
                    verdict = _compile_verdict(
                        log, offset, time.time() + COMPILE_TIMEOUT
                    )
                    return {"restarted": True, "port": DEV_SERVER_PORT, **verdict}
        except (urllib.error.URLError, OSError):
            time.sleep(2)
    return {
        "restarted": True,
        "port": DEV_SERVER_PORT,
        "compiled": None,
        "errors": [],
        "reason": "restarted but did not answer /health in time; check the log",
    }
