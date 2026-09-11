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
import time
from typing import Any

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
# Kept small on purpose: the sheet is base64-encoded into a JSON message when
# the model reads it, and an oversized image breaks the transport before it
# ever reaches the model. Legibility of the mark matters, pixel detail does not.
CELL = 150
# Long enough for a cold Chrome start on a large sheet; the loop below
# usually returns well inside it.
RENDER_TIMEOUT = 300


# Files that are not a picture of anything: the placeholder `plugin_writer`
# copies in so a build will not break, a blank, a corrupt write. Drawn on the
# sheet they are worse than nothing -- they look like evidence, and the stage
# comparing them records having compared them.
PLACEHOLDER = REPO_ROOT / "design-to-dashboard/assets/plugin-thumbnail-placeholder.png"


def _placeholder_bytes() -> bytes | None:
    try:
        return PLACEHOLDER.read_bytes()
    except OSError:
        return None


def _is_informative(path: pathlib.Path) -> bool:
    """Whether this file shows something a plugin can be recognised by.

    Matched against the placeholder byte-for-byte rather than by how plain it
    looks: several legitimate illustrations are flat line art in a handful of
    colours -- `table`'s is eleven -- and a colour threshold low enough to keep
    those is too low to catch anything.
    """
    try:
        data = path.read_bytes()
    except OSError:
        return False
    if data == _placeholder_bytes():
        return False
    try:
        from PIL import Image

        with Image.open(path) as image:
            colours = image.convert("RGB").getcolors(maxcolors=1_000_000)
    except Exception:  # noqa: BLE001 - unreadable is uninformative
        return False
    # One or two colours is a blank, whatever it was meant to be.
    return colours is None or len(colours) > 2


def _preview(
    entry: dict[str, Any], previews: pathlib.Path | None
) -> pathlib.Path | None:
    """The best picture of this viz type: a real render, else its illustration.

    A render is the component itself drawing data, so it is preferred whenever
    one exists. The shipped illustration is a stylised drawing and a reasonable
    fallback -- but only when it actually depicts something.
    """
    viz_type = entry.get("viz_type") or ""
    if previews:
        rendered = previews / f"{viz_type}.png"
        if rendered.exists() and _is_informative(rendered):
            return rendered
    if thumbnail := entry.get("thumbnail"):
        shipped = REPO_ROOT / thumbnail
        if shipped.exists() and _is_informative(shipped):
            return shipped
    return None


def build_html(
    entries: list[dict[str, Any]],
    custom_only: bool,
    previews: pathlib.Path | None = None,
) -> str:
    cells = []
    for entry in entries:
        if custom_only and not entry.get("custom"):
            continue
        source = _preview(entry, previews)
        badge = "custom" if entry.get("custom") else entry.get("category") or ""
        if source is None:
            # Named, and visibly not shown. A viz type absent from the sheet
            # entirely would read as one that does not exist.
            picture = '<div class="none">no preview</div>'
            badge = f"{badge} · NO PREVIEW".strip(" ·")
        else:
            data = base64.b64encode(source.read_bytes()).decode()
            picture = f'<img src="data:image/png;base64,{data}"/>'
        cells.append(
            f"<figure>{picture}"
            f"<figcaption><b>{entry['viz_type']}</b><br/>"
            f"<span>{entry.get('name') or ''}</span><br/>"
            f"<em>{badge}</em></figcaption></figure>"
        )
    return f"""<!doctype html><meta charset="utf-8"><style>
      body {{ margin:0; padding:16px; background:#fff;
              font:10px -apple-system,Helvetica,sans-serif; }}
      .grid {{ display:grid; grid-template-columns:repeat(6,{CELL}px); gap:12px; }}
      figure {{ margin:0; border:1px solid #d9d9d9; border-radius:6px;
                padding:6px; background:#fff; }}
      img {{ width:100%; height:{CELL - 46}px; object-fit:contain;
             background:#fafafa; }}
      .none {{ width:100%; height:{CELL - 46}px; background:#fafafa;
               border:1px dashed #d9d9d9; box-sizing:border-box;
               display:flex; align-items:center; justify-content:center;
               color:#bfbfbf; font-size:10px; }}
      figcaption {{ margin-top:5px; line-height:1.35; word-break:break-word; }}
      b {{ font-family:ui-monospace,Menlo,monospace; font-size:11px; }}
      span {{ color:#333; }} em {{ color:#8c8c8c; font-style:normal; }}
    </style><div class="grid">{"".join(cells)}</div>"""


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
    parser.add_argument(
        "--previews",
        default=str(REPO_ROOT / "design-to-dashboard/fixtures/thumbnails"),
        help="directory of rendered <viz_type>.png previews; these win over "
        "the illustration a plugin ships",
    )
    args = parser.parse_args()

    entries = json.loads(pathlib.Path(args.registry).read_text())["viz_types"]
    previews = pathlib.Path(args.previews) if args.previews else None
    html = build_html(
        entries, args.custom_only, previews if previews and previews.is_dir() else None
    )
    shown = html.count("<figure>")
    if not shown:
        print("no thumbnails to render", file=sys.stderr)
        return 1

    html_path = pathlib.Path(args.out).with_suffix(".html")
    html_path.write_text(html, encoding="utf-8")

    rows = (shown + 5) // 6
    height = rows * (CELL + 20) + 40
    out = pathlib.Path(args.out)
    out.unlink(missing_ok=True)
    # Popen rather than run(): headless Chrome writes the screenshot and then
    # lingers, so waiting for it to exit waits minutes past the work being
    # done. The file appearing is the real completion signal.
    chrome = subprocess.Popen(  # noqa: S603
        [
            CHROME,
            "--headless",
            "--disable-gpu",
            "--no-sandbox",
            "--hide-scrollbars",
            f"--screenshot={out}",
            f"--window-size={6 * (CELL + 12) + 36},{height}",
            "--default-background-color=FFFFFFFF",
            f"file://{html_path}",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=False,
    )
    try:
        deadline = time.monotonic() + RENDER_TIMEOUT
        while time.monotonic() < deadline:
            # A size that stops growing means the write has finished.
            size = out.stat().st_size if out.exists() else 0
            if size:
                time.sleep(1.0)
                if out.stat().st_size == size:
                    break
            if chrome.poll() is not None:
                break
            time.sleep(0.5)
    finally:
        chrome.terminate()
        try:
            chrome.wait(timeout=10)
        except subprocess.TimeoutExpired:
            chrome.kill()

    html_path.unlink(missing_ok=True)
    if not out.exists():
        print("chrome produced no screenshot", file=sys.stderr)
        return 1
    print(f"wrote {out} ({shown} plugins, {out.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
