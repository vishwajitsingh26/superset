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
"""The picture of every chart type stage C compares a design against.

Written after finding the committed sheet two days stale, missing the plugins
earlier runs had built, cut off along its last row, and showing "no preview"
for the KPI, pivot table and filter types a dashboard most often needs.
"""

from __future__ import annotations

import pathlib
from typing import Any

import pytest
from PIL import Image

from superset.design_to_dashboard import contact_sheet

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]


def _png(path: pathlib.Path, colours: int) -> pathlib.Path:
    """An image with `colours` distinct colours."""
    image = Image.new("RGB", (40, 20), (255, 255, 255))
    for index in range(colours):
        image.putpixel((index % 40, index // 40), (index * 7 % 256, 40, 90))
    image.save(path)
    return path


@pytest.fixture
def placeholder(tmp_path: pathlib.Path) -> bytes:
    return _png(tmp_path / "placeholder.png", 20).read_bytes()


# what counts as a picture


def test_the_placeholder_is_never_taken_for_a_picture(
    tmp_path: pathlib.Path, placeholder: bytes
) -> None:
    """Drawn as a picture it reads as evidence of a plugin that has none."""
    copied = tmp_path / "thumbnail.png"
    copied.write_bytes(placeholder)
    assert not contact_sheet.is_informative(copied, placeholder)


def test_a_blank_image_is_not_a_picture(tmp_path: pathlib.Path) -> None:
    assert not contact_sheet.is_informative(_png(tmp_path / "blank.png", 1), None)


def test_a_real_image_is_a_picture(tmp_path: pathlib.Path) -> None:
    assert contact_sheet.is_informative(_png(tmp_path / "chart.png", 30), None)


# which picture a tile shows


def test_a_stock_chart_shows_its_example_screenshot_over_its_thumbnail(
    tmp_path: pathlib.Path, placeholder: bytes
) -> None:
    """The screenshot is the chart rendering data; the thumbnail is a drawing."""
    _png(tmp_path / "thumbnail.png", 30)
    _png(tmp_path / "Pie1.png", 40)
    entry = {"viz_type": "pie", "thumbnail": "thumbnail.png", "examples": ["Pie1.png"]}
    assert contact_sheet.best_picture(entry, tmp_path, placeholder) == tmp_path / (
        "Pie1.png"
    )


def test_a_custom_plugin_shows_its_photographed_thumbnail(
    tmp_path: pathlib.Path, placeholder: bytes
) -> None:
    _png(tmp_path / "thumbnail.png", 30)
    entry = {"viz_type": "custom_card", "custom": True, "thumbnail": "thumbnail.png"}
    assert contact_sheet.best_picture(entry, tmp_path, placeholder) == tmp_path / (
        "thumbnail.png"
    )


def test_a_plugin_still_wearing_the_placeholder_has_no_picture(
    tmp_path: pathlib.Path, placeholder: bytes
) -> None:
    (tmp_path / "thumbnail.png").write_bytes(placeholder)
    entry = {"viz_type": "custom_card", "custom": True, "thumbnail": "thumbnail.png"}
    assert contact_sheet.best_picture(entry, tmp_path, placeholder) is None


def test_a_missing_file_falls_through_to_the_next_candidate(
    tmp_path: pathlib.Path, placeholder: bytes
) -> None:
    _png(tmp_path / "thumbnail.png", 30)
    entry = {"viz_type": "pie", "thumbnail": "thumbnail.png", "examples": ["gone.png"]}
    assert contact_sheet.best_picture(entry, tmp_path, placeholder) == tmp_path / (
        "thumbnail.png"
    )


# the sheet itself


@pytest.mark.parametrize("count", [1, 6, 7, 61, 100])
def test_every_tile_fits_inside_the_sheet(count: int) -> None:
    """The old sheet computed its height from a smaller tile than it drew."""
    geometry = contact_sheet.layout(count)
    assert len(geometry.positions) == count
    for x, y in geometry.positions:
        assert x + contact_sheet.CELL_WIDTH <= geometry.width
        assert y + geometry.cell_height <= geometry.height


def test_custom_plugins_come_first() -> None:
    entries: list[dict[str, Any]] = [
        {"viz_type": "pie"},
        {"viz_type": "custom_card", "custom": True},
        {"viz_type": "bar"},
    ]
    assert [e["viz_type"] for e in contact_sheet.ordered(entries)] == [
        "custom_card",
        "bar",
        "pie",
    ]


def test_the_sheet_is_drawn_with_a_tile_for_every_chart_type(
    tmp_path: pathlib.Path,
) -> None:
    _png(tmp_path / "Pie1.png", 40)
    entries: list[dict[str, Any]] = [
        {"viz_type": "pie", "name": "Pie Chart", "examples": ["Pie1.png"]},
        {"viz_type": "pop_kpi", "name": "Big Number with Time Comparison"},
    ]
    out = contact_sheet.build(entries, tmp_path, tmp_path / "run" / "sheet.png")
    assert out is not None
    with Image.open(out) as sheet:
        geometry = contact_sheet.layout(2)
        assert sheet.size == (geometry.width, geometry.height)


def test_a_sheet_that_cannot_be_drawn_does_not_fail_the_run(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(*_args: Any, **_kwargs: Any) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(Image.Image, "save", broken)
    out = contact_sheet.build([{"viz_type": "pie"}], tmp_path, tmp_path / "s.png")
    assert out is None


# the registry knows where the pictures are


def _generator() -> Any:
    from superset.design_to_dashboard import registry_source

    return registry_source


def test_a_plugins_example_gallery_is_read_from_its_imports(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    generator = _generator()
    monkeypatch.setattr(generator, "REPO_ROOT", tmp_path)
    images = tmp_path / "plugin" / "images"
    images.mkdir(parents=True)
    (images / "Pie1.jpg").write_bytes(b"x")
    (images / "Pie1-dark.jpg").write_bytes(b"x")
    source = tmp_path / "plugin" / "index.ts"
    source.write_text(
        "import example1 from './images/Pie1.jpg';\n"
        "import example1Dark from './images/Pie1-dark.jpg';\n"
        "const metadata = new ChartMetadata({\n"
        "  exampleGallery: [{ url: example1, urlDark: example1Dark }],\n"
        "});\n",
        encoding="utf-8",
    )
    assert generator._examples_in(source) == ["plugin/images/Pie1.jpg"]


def test_the_chart_types_that_had_no_picture_now_find_theirs() -> None:
    """KPI, pivot table and filter types were offered with no picture at all."""
    generator = _generator()
    for viz_type, directory in generator.IMAGE_DIR_OVERRIDES.items():
        assert generator._find_thumbnail(None, directory), viz_type
    assert generator._find_examples(
        "METADATA_OVERRIDES", generator.IMAGE_DIR_OVERRIDES["big_number"]
    )
