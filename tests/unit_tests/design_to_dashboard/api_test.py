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
"""The crop endpoint: who may reach it, and what name it will serve.

`crop_image` was added after this deployment's roles were last granted FAB's
new permission for it, so every request 403'd -- including the session's own
owner. Nothing here boots a Flask app: `method_permission_name` is a plain
class attribute, and `CROP_NAME` a plain regex, so both are checked directly.
"""

from __future__ import annotations

import pytest

from superset.design_to_dashboard.api import CROP_NAME, DesignToDashboardRestApi

# --- the permission a request needs -----------------------------------------


def test_crop_image_reuses_an_already_granted_permission() -> None:
    """The fix: `can_crop_image` needed a role grant no boot but `superset
    init` ever performs; `can_get_session` already has one, on every role
    that could reach this session in the first place."""
    assert (
        DesignToDashboardRestApi.method_permission_name.get("crop_image")
        == "get_session"
    )


def test_get_asset_reuses_an_already_granted_permission() -> None:
    """Same fix, same reason, for the second read added after this
    deployment's last `superset init`: the uploaded design image itself,
    not a region's crop of it."""
    assert (
        DesignToDashboardRestApi.method_permission_name.get("get_asset")
        == "get_session"
    )


def test_other_methods_are_not_remapped() -> None:
    """The alias is narrow: every other method still earns its own
    permission, named after itself, the way FAB derives one by default."""
    mapping = DesignToDashboardRestApi.method_permission_name
    for method in ("create_session", "upload_asset", "run", "reply", "events"):
        assert mapping.get(method) is None


# --- the name a crop request may ask for ------------------------------------


@pytest.mark.parametrize(
    "name",
    [
        "r01_cloud_cost_analytics.png",
        "r13.png",
        "a-b_c9.png",
    ],
)
def test_a_well_formed_crop_name_matches(name: str) -> None:
    assert CROP_NAME.fullmatch(name)


@pytest.mark.parametrize(
    "name",
    [
        "../../etc/passwd.png",
        "sub/dir.png",
        "no_extension",
        "shell;rm -rf.png",
        "trailing/.png",
        "",
    ],
)
def test_a_path_is_not_a_crop_name(name: str) -> None:
    assert not CROP_NAME.fullmatch(name)
