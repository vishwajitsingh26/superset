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
"""Which design image a region came from, whole or cropped.

`source_image_path` is the lookup `region_crop` always did inline; it is
pulled out here because a caller building stage F's plugin now needs the same
answer for a different purpose -- the design, not a crop of it.
"""

from __future__ import annotations

import pathlib
from typing import Any

from superset.design_to_dashboard.crop import region_crop, source_image_path


def _png(path: pathlib.Path, size: tuple[int, int] = (400, 300)) -> str:
    from PIL import Image

    Image.new("RGB", size, "white").save(path)
    return str(path)


def _region(**overrides: Any) -> dict[str, Any]:
    region = {
        "region_id": "r01_card",
        "bbox": {"x": 0.1, "y": 0.1, "w": 0.3, "h": 0.2},
        "source_image": 0,
    }
    region.update(overrides)
    return region


# --- which image a region reads from ------------------------------------


def test_the_default_source_image_is_the_first() -> None:
    assert source_image_path(["a.png", "b.png"], _region(source_image=None)) == "a.png"


def test_a_named_source_image_is_selected() -> None:
    assert source_image_path(["a.png", "b.png"], _region(source_image=1)) == "b.png"


def test_an_out_of_range_index_falls_back_to_the_first() -> None:
    assert source_image_path(["a.png", "b.png"], _region(source_image=5)) == "a.png"


def test_no_images_at_all_is_none() -> None:
    assert source_image_path([], _region()) is None


# --- cropping still works the same way after the shared lookup ----------


def test_a_region_is_cropped_from_its_own_source_image(tmp_path: pathlib.Path) -> None:
    first = _png(tmp_path / "design_0.png", (400, 300))
    second = _png(tmp_path / "design_1.png", (200, 200))
    out_dir = tmp_path / "crops"
    result = region_crop([first, second], _region(source_image=1), out_dir)
    assert result is not None
    assert pathlib.Path(result).exists()


def test_no_bbox_produces_no_crop(tmp_path: pathlib.Path) -> None:
    design = _png(tmp_path / "design.png")
    assert region_crop([design], _region(bbox=None), tmp_path / "crops") is None


def test_no_images_produces_no_crop(tmp_path: pathlib.Path) -> None:
    assert region_crop([], _region(), tmp_path / "crops") is None


def test_a_tiny_box_is_rejected_as_unusable(tmp_path: pathlib.Path) -> None:
    design = _png(tmp_path / "design.png", (400, 300))
    region = _region(bbox={"x": 0.0, "y": 0.0, "w": 0.01, "h": 0.01})
    assert region_crop([design], region, tmp_path / "crops") is None
