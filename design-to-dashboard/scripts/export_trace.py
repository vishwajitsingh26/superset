#!/usr/bin/env python3
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
"""Export one run as a readable trace, for judging how well the model did.

Writes a Markdown file with, per stage: how long it took, what it cost, the
reasoning it produced, the tools it called, the decisions it made and the
evidence it cited -- plus the questions asked, the plan approved, and what
finally rendered.

    python design-to-dashboard/scripts/export_trace.py <session-id> [--out FILE]

The runner already writes this file at the end of every run. Use this script
to re-export a run that is still in memory -- to pick up events published after
the trace was written, or to place the report somewhere else with `--out`.

Sessions live in the web process's memory, so this runs against the API, and a
session is gone once the server restarts. `render` is imported from
`superset.design_to_dashboard.trace` so the two reports cannot drift.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import urllib.error
import urllib.request
from typing import Any

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from superset.design_to_dashboard.trace import render  # noqa: E402

API = "http://127.0.0.1:8088/api/v1"


def _post(
    path: str, payload: dict[str, Any], token: str | None = None
) -> dict[str, Any]:
    request = urllib.request.Request(  # noqa: S310
        f"{API}{path}",
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            **({"Authorization": f"Bearer {token}"} if token else {}),
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
        return json.load(response)


def _get(path: str, token: str) -> dict[str, Any]:
    request = urllib.request.Request(  # noqa: S310
        f"{API}{path}", headers={"Authorization": f"Bearer {token}"}
    )
    with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310
        return json.load(response)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session_id")
    parser.add_argument("--out")
    parser.add_argument("--username", default="admin")
    parser.add_argument("--password", default="admin")
    args = parser.parse_args()

    try:
        token = _post(
            "/security/login",
            {
                "username": args.username,
                "password": args.password,
                "provider": "db",
                "refresh": True,
            },
        )["access_token"]
        state = _get(f"/design_to_dashboard/session/{args.session_id}/", token)
    except urllib.error.HTTPError as ex:
        print(f"could not read the session: HTTP {ex.code}", file=sys.stderr)
        print(
            "sessions live in the web process's memory and are lost on restart",
            file=sys.stderr,
        )
        return 1

    out = pathlib.Path(args.out or f"design-to-dashboard/traces/{args.session_id}.md")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(state), encoding="utf-8")
    print(f"wrote {out} ({out.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
