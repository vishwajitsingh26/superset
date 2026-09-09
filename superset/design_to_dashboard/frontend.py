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

`webpack.config.js` builds `resolve.alias` from `package.json`'s `file:`
dependencies **when the config is evaluated**, and points each alias straight at
the package's `src/`. Two consequences:

* `npm install` is not what matters -- the alias bypasses `node_modules`.
* A dependency added after the dev server started is invisible until the dev
  server is **restarted**, because that is when the alias map is rebuilt.

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


def restart_dev_server(repo_root: str | pathlib.Path) -> dict[str, Any]:
    """Restart the webpack dev server so new plugin aliases are picked up."""
    root = pathlib.Path(repo_root)
    frontend = root / "superset-frontend"
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
