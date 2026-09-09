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
"""Render every plugin's thumbnail into one labelled contact sheet.

A plugin *is* a UI component, and its thumbnail is the best available picture of
what it renders. Matching a design section against those pictures is more
reliable than matching against text descriptions -- but 46 separate images per
request is wasteful, so they are composited into a single sheet labelled by
viz_type.

Rendered through headless Chrome from an HTML grid, which avoids an image
library dependency.

    python design-to-dashboard/scripts/build_thumbnail_sheet.py
"""

from __future__ import annotations

import argparse
import base64
import json
import pathlib
import subprocess  # noqa: S404 - fixed argv, no shell
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
# Kept small on purpose: the sheet is base64-encoded into a JSON message when
# the model reads it, and an oversized image breaks the transport before it
# ever reaches the model. Legibility of the mark matters, pixel detail does not.
CELL = 150


def build_html(entries: list[dict], custom_only: bool) -> str:
    cells = []
    for entry in entries:
        thumb = entry.get("thumbnail")
        if not thumb:
            continue
        if custom_only and not entry.get("custom"):
            continue
        data = base64.b64encode((REPO_ROOT / thumb).read_bytes()).decode()
        badge = "custom" if entry.get("custom") else entry.get("category") or ""
        cells.append(
            f'<figure><img src="data:image/png;base64,{data}"/>'
            f'<figcaption><b>{entry["viz_type"]}</b><br/>'
            f'<span>{entry.get("name") or ""}</span><br/>'
            f'<em>{badge}</em></figcaption></figure>'
        )
    return f"""<!doctype html><meta charset="utf-8"><style>
      body {{ margin:0; padding:16px; background:#fff;
              font:10px -apple-system,Helvetica,sans-serif; }}
      .grid {{ display:grid; grid-template-columns:repeat(6,{CELL}px); gap:12px; }}
      figure {{ margin:0; border:1px solid #d9d9d9; border-radius:6px;
                padding:6px; background:#fff; }}
      img {{ width:100%; height:{CELL - 46}px; object-fit:contain;
             background:#fafafa; }}
      figcaption {{ margin-top:5px; line-height:1.35; word-break:break-word; }}
      b {{ font-family:ui-monospace,Menlo,monospace; font-size:11px; }}
      span {{ color:#333; }} em {{ color:#8c8c8c; font-style:normal; }}
    </style><div class="grid">{''.join(cells)}</div>"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--registry",
        default=str(REPO_ROOT / "design-to-dashboard/fixtures/viz_registry.json"),
    )
    parser.add_argument(
        "--out",
        default=str(REPO_ROOT / "design-to-dashboard/fixtures/plugin_thumbnails.png"),
    )
    parser.add_argument("--custom-only", action="store_true")
    args = parser.parse_args()

    entries = json.loads(pathlib.Path(args.registry).read_text())["viz_types"]
    html = build_html(entries, args.custom_only)
    shown = html.count("<figure>")
    if not shown:
        print("no thumbnails to render", file=sys.stderr)
        return 1

    html_path = pathlib.Path(args.out).with_suffix(".html")
    html_path.write_text(html, encoding="utf-8")

    rows = (shown + 5) // 6
    height = rows * (CELL + 20) + 40
    completed = subprocess.run(  # noqa: S603
        [
            CHROME,
            "--headless",
            "--disable-gpu",
            "--no-sandbox",
            "--hide-scrollbars",
            f"--screenshot={args.out}",
            f"--window-size={6 * (CELL + 12) + 36},{height}",
            "--default-background-color=FFFFFFFF",
            f"file://{html_path}",
        ],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
        shell=False,
    )
    out = pathlib.Path(args.out)
    if not out.exists():
        print(f"chrome failed: {completed.stderr[-300:]}", file=sys.stderr)
        return 1
    print(f"wrote {out} ({shown} plugins, {out.stat().st_size // 1024} KB)")
    html_path.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
