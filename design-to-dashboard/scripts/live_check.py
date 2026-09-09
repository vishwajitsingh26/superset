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
"""Verify Design-to-Dashboard against a real Superset instance.

Everything else in this feature has only been exercised against fixtures.
This checks the parts that fixtures cannot: that the SPA route serves, that
the feature flag gates it, and that ``InProcessGateway`` really talks to
Superset's MCP tools and decodes what they return.

    SUPERSET_CONFIG_PATH=... .venv/bin/python design-to-dashboard/scripts/live_check.py
"""

from __future__ import annotations

import json
import sys
import traceback

PASS, FAIL, SKIP = "PASS", "FAIL", "SKIP"
results: list[tuple[str, str, str]] = []


def record(name: str, status: str, detail: str = "") -> None:
    results.append((name, status, detail))
    marker = {PASS: "  ok  ", FAIL: " FAIL ", SKIP: " skip "}[status]
    print(f"[{marker}] {name}" + (f"\n           {detail}" if detail else ""))


def main() -> int:  # noqa: C901
    from superset.app import create_app

    app = create_app()

    # ---- the SPA route ------------------------------------------------------
    with app.test_client() as client:
        response = client.get("/design-to-dashboard/", follow_redirects=False)
        # 302 to /login/ is the correct answer for an anonymous user: the view
        # exists and @has_access is doing its job. A 404 means the flag gate
        # rejected it or the view was never registered.
        if response.status_code in (200, 302):
            record(
                "route /design-to-dashboard/ registered",
                PASS,
                f"HTTP {response.status_code}"
                + (
                    f" -> {response.headers.get('Location')}"
                    if response.status_code == 302
                    else ""
                ),
            )
        else:
            record(
                "route /design-to-dashboard/ registered",
                FAIL,
                f"HTTP {response.status_code} (404 => flag gate or registration)",
            )

    # ---- the feature flag actually gates ------------------------------------
    with app.app_context():
        from superset.views.design_to_dashboard import DesignToDashboardView

        record(
            "feature flag reads True",
            PASS if DesignToDashboardView.is_enabled() else FAIL,
            f"is_enabled() = {DesignToDashboardView.is_enabled()}",
        )

    # ---- MCP gateway against real tools -------------------------------------
    # The user must be loaded in the same context that uses it; loading it in a
    # separate app context detaches it and `roles` fails to lazy-load.
    with app.test_request_context("/api/v1/design_to_dashboard/"):
        from flask import g

        from superset.design_to_dashboard.mcp.gateway import InProcessGateway, MCPError

        security_manager = app.appbuilder.sm
        admin = security_manager.find_user(username="admin")
        if admin is None:
            admins = security_manager.get_all_users()
            admin = admins[0] if admins else None
        if admin is None:
            record("MCP gateway", SKIP, "no user in the metadata DB yet")
            return summarise()

        gateway = InProcessGateway()
        if True:
            g.user = admin
            for tool, arguments, describe in (
                (
                    "list_datasets",
                    {"request": {"page_size": 5}},
                    lambda r: f"{len(_rows(r))} dataset(s)",
                ),
                (
                    "list_charts",
                    {"request": {"page_size": 5}},
                    lambda r: f"{len(_rows(r))} chart(s)",
                ),
            ):
                try:
                    result = gateway.call(tool, arguments)
                except MCPError as ex:
                    record(f"MCP {tool}", FAIL, str(ex)[:300])
                    continue
                except Exception as ex:  # noqa: BLE001
                    record(f"MCP {tool}", FAIL, f"{type(ex).__name__}: {ex}"[:300])
                    continue
                record(f"MCP {tool}", PASS, describe(result))
                _remember(tool, result)

            # get_dataset_info on a real id proves the decode path end to end.
            dataset_id = _first_id("list_datasets")
            if dataset_id is None:
                record("MCP get_dataset_info", SKIP, "no datasets loaded")
            else:
                try:
                    info = gateway.call(
                        "get_dataset_info", {"request": {"identifier": dataset_id}}
                    )
                    # get_dataset_info nests its payload under "result".
                    payload = info.get("result", info)
                    columns = payload.get("columns") or []
                    metrics = payload.get("metrics") or []
                    record(
                        "MCP get_dataset_info",
                        PASS,
                        f"dataset {dataset_id}: {len(columns)} columns, "
                        f"{len(metrics)} metrics",
                    )
                except Exception as ex:  # noqa: BLE001
                    record(
                        "MCP get_dataset_info", FAIL, f"{type(ex).__name__}: {ex}"[:300]
                    )

    return summarise()


_seen: dict[str, object] = {}


def _remember(tool: str, result: object) -> None:
    _seen[tool] = result


def _rows(result: object) -> list:
    if isinstance(result, dict):
        for key in ("charts", "datasets", "databases", "dashboards", "result", "results", "data", "items"):
            value = result.get(key)
            if isinstance(value, list):
                return value
    return result if isinstance(result, list) else []


def _first_id(tool: str) -> int | None:
    for row in _rows(_seen.get(tool)):
        if isinstance(row, dict) and isinstance(row.get("id"), int):
            return row["id"]
    return None


def summarise() -> int:
    print("\n" + "-" * 60)
    failed = [r for r in results if r[1] == FAIL]
    skipped = [r for r in results if r[1] == SKIP]
    print(
        f"{len(results) - len(failed) - len(skipped)} passed, "
        f"{len(failed)} failed, {len(skipped)} skipped"
    )
    return 1 if failed else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        sys.exit(2)
