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
            ["lsof", "-nP", f"-iTCP:{DEV_SERVER_PORT}", "-sTCP:LISTEN", "-t"],
            capture_output=True,
            text=True,
            check=False,
            shell=False,
        )
    except FileNotFoundError:
        return None
    pids = [line for line in completed.stdout.split() if line.isdigit()]
    return int(pids[0]) if pids else None


def link_plugins(repo_root: str | pathlib.Path, timeout: int = 600) -> dict[str, Any]:
    """Run `npm install` so new `file:` dependencies are linked into node_modules."""
    frontend = pathlib.Path(repo_root) / "superset-frontend"
    env = dict(os.environ)
    if NODE_BIN.is_dir():
        env["PATH"] = f"{NODE_BIN}:{env.get('PATH', '')}"
    try:
        completed = subprocess.run(  # noqa: S603
            ["npm", "install", "--no-audit", "--no-fund"],
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
    with log.open("ab") as handle:
        subprocess.Popen(  # noqa: S603
            ["npm", "run", "dev-server"],
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
                    return {"restarted": True, "port": DEV_SERVER_PORT}
        except (urllib.error.URLError, OSError):
            time.sleep(2)
    return {
        "restarted": True,
        "port": DEV_SERVER_PORT,
        "reason": "restarted but did not answer /health in time; check the log",
    }
