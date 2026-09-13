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
"""Write the chart-type registry to a file, for inspection or test fixtures.

Pipeline runs do not read this file. Each run scans the source itself through
``superset.design_to_dashboard.registry.build``; this wrapper only saves the
same scan to disk.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from superset.design_to_dashboard import registry_source  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        default=str(REPO_ROOT / "design-to-dashboard/fixtures/viz_registry.json"),
    )
    args = parser.parse_args()
    payload = registry_source.scan()
    out_path = pathlib.Path(args.out)
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"wrote {out_path} ({payload['count']} viz types)", file=sys.stderr)
    for name, items in payload["warnings"].items():
        if items:
            print(f"  {name}: {items[:8]}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
