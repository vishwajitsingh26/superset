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
"""The part of a plugin that is derived rather than generated.

Six names have to agree exactly and are read by five different consumers, and
nothing compared them. A model that spelled one differently produced a plugin
that installed, compiled, and never appeared in the chart picker.
"""

from __future__ import annotations

import pathlib
from typing import Any

import pytest

from superset.design_to_dashboard import plugin_skeleton
from superset.design_to_dashboard.stages.f_scaffold import _broken_rules

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]


def test_every_name_comes_from_the_viz_type() -> None:
    plugin = plugin_skeleton.identity("custom_provider_card", "4d9976")
    assert plugin.directory == (
        "superset-frontend/plugins/plugin-chart-custom-provider-card-4d9976"
    )
    assert plugin.package_name == (
        "@superset-ui/plugin-chart-custom-provider-card-4d9976"
    )
    assert plugin.class_name == "CustomProviderCardPlugin"
    assert plugin.component == "CustomProviderCard"
    assert plugin.form_data_type == "CustomProviderCardFormData"


def test_the_registration_key_is_the_viz_type() -> None:
    """These were written separately and read by different consumers: the
    browser registers by the key, the registry manifest harvests it, and
    stage D is handed `viz_type`. A disagreement was invisible."""
    plugin = plugin_skeleton.identity("custom_kpi_card", "abc123")
    assert f"key: '{plugin.viz_type}'" in plugin.register_line
    assert plugin.class_name in plugin.register_line
    assert plugin.class_name in plugin.import_line
    assert plugin.package_name in plugin.import_line


def test_the_tag_goes_on_the_directory_and_package_and_nowhere_else() -> None:
    """tsconfig resolves the package name to the directory of the same name
    through one wildcard, so tagging one and not the other breaks every
    import. The viz type and class are what a user sees."""
    plugin = plugin_skeleton.identity("custom_card", "4d9976")
    assert plugin.directory.endswith("-4d9976")
    assert plugin.package_name.endswith("-4d9976")
    assert "4d9976" not in plugin.viz_type
    assert "4d9976" not in plugin.class_name
    assert "4d9976" not in plugin.display_name


def test_the_dependency_spec_is_relative_to_the_frontend_package_json() -> None:
    """The `plugins/` segment is part of it. Built from the leaf alone, both
    gates still passed -- npm links the package through the `plugins/*`
    workspace glob and tsc resolves it through tsconfig's own wildcard -- and
    only webpack, which reads the spec, aliased to a path that does not exist
    and took the whole bundle down."""
    plugin = plugin_skeleton.identity("custom_card", "4d9976")
    assert plugin.dependency["name"] == plugin.package_name
    assert plugin.dependency["spec"] == f"file:./plugins/{plugin.leaf}"
    assert plugin.directory == f"superset-frontend/plugins/{plugin.leaf}"


@pytest.mark.parametrize(
    "given,expected",
    [
        ("Custom-Card!!", "custom_card"),
        ("  CUSTOM__CARD  ", "custom_card"),
        ("custom_card", "custom_card"),
    ],
)
def test_a_messy_viz_type_is_cleaned_not_trusted(given: str, expected: str) -> None:
    assert plugin_skeleton.identity(given, "t").viz_type == expected


def test_no_viz_type_is_an_error_not_a_default() -> None:
    """Grouping keyed on viz_type, so an empty one collapsed several
    decisions into a single plugin that then served all of them."""
    with pytest.raises(ValueError, match="viz_type"):
        plugin_skeleton.identity("", "t")
    with pytest.raises(ValueError, match="viz_type"):
        plugin_skeleton.identity("!!!", "t")


def test_an_untagged_run_still_names_everything() -> None:
    plugin = plugin_skeleton.identity("custom_card", "")
    assert plugin.directory.endswith("plugin-chart-custom-card")
    assert plugin.package_name.endswith("plugin-chart-custom-card")


# --- what gets written -------------------------------------------------------


def _rendered(decision: dict[str, Any] | None = None) -> dict[str, str]:
    plugin = plugin_skeleton.identity("custom_card", "4d9976")
    return plugin_skeleton.render(plugin, decision or {}, REPO_ROOT)


def test_the_skeleton_writes_the_files_that_name_the_plugin() -> None:
    files = _rendered()
    leaf = "superset-frontend/plugins/plugin-chart-custom-card-4d9976"
    assert set(files) == {
        f"{leaf}/package.json",
        f"{leaf}/src/index.ts",
        f"{leaf}/src/plugin/index.ts",
        f"{leaf}/src/adapters/supersetAdapter.ts",
    }


def test_the_skeleton_loads_the_component_the_identity_names() -> None:
    """`plugin/index.ts` imports the component by path, so the generated file
    has to land at exactly that name or it fails to resolve at run time."""
    plugin = plugin_skeleton.identity("custom_card", "4d9976")
    source = _rendered()[f"{plugin.directory}/src/plugin/index.ts"]
    assert f"import('../{plugin.component}')" in source
    assert f"class {plugin.class_name} extends ChartPlugin" in source
    assert plugin.form_data_type in source


def test_behaviours_follow_the_archetype() -> None:
    """A wrapper hosts charts that cross-filter on their own; a filter is what
    emits the mask. Asked to choose, a model put NativeFilter on a bar chart,
    which lands it in the filter picker."""
    plugin = plugin_skeleton.identity("custom_card", "t")
    path = f"{plugin.directory}/src/plugin/index.ts"
    assert (
        "Behavior.NativeFilter"
        in plugin_skeleton.render(
            plugin, {"plugin_archetype": "filter_widget"}, REPO_ROOT
        )[path]
    )
    assert (
        "Behavior.NativeFilter"
        not in plugin_skeleton.render(plugin, {"plugin_archetype": "viz"}, REPO_ROOT)[
            path
        ]
    )


def test_stage_c_can_name_the_behaviours_itself() -> None:
    plugin = plugin_skeleton.identity("custom_card", "t")
    source = plugin_skeleton.render(
        plugin, {"plugin_archetype": "viz", "behaviors": ["DrillBy"]}, REPO_ROOT
    )[f"{plugin.directory}/src/plugin/index.ts"]
    assert "behaviors: [Behavior.DrillBy]" in source


def test_an_apostrophe_in_the_rationale_does_not_break_the_string() -> None:
    """Stage C's rationale is prose. An apostrophe closes the string and a
    newline breaks the statement, and neither shows up until it fails to
    compile."""
    plugin = plugin_skeleton.identity("custom_card", "t")
    source = plugin_skeleton.render(
        plugin,
        {"rationale": "It's a card\nover two lines with a \\ backslash"},
        REPO_ROOT,
    )[f"{plugin.directory}/src/plugin/index.ts"]
    description = next(line for line in source.splitlines() if "description:" in line)
    assert description.count("'") == 2
    assert "\\" not in description


def test_a_long_rationale_is_truncated() -> None:
    plugin = plugin_skeleton.identity("custom_card", "t")
    source = plugin_skeleton.render(plugin, {"rationale": "x" * 500}, REPO_ROOT)[
        f"{plugin.directory}/src/plugin/index.ts"
    ]
    description = next(line for line in source.splitlines() if "description:" in line)
    assert len(description) < 200


def test_the_skeleton_obeys_the_rules_generated_code_is_held_to() -> None:
    """The skeleton is a second thing that can go stale the way the exemplar
    did, so it is held to the same rules -- and it is what the model copies
    conventions from when writing the rest of the package."""
    for path, contents in _rendered({"rationale": "A card"}).items():
        assert not _broken_rules(contents), path


def test_the_skeleton_imports_nothing_from_a_module_it_moved_out_of() -> None:
    """Superset's own generator scaffolds `import { t } from
    '@superset-ui/core'`, which moved in 6.1 -- so its templates produce a
    plugin this stage rejects, which is why they are not used."""
    plugin = plugin_skeleton.identity("custom_card", "4d9976")
    source = _rendered()[f"{plugin.directory}/src/plugin/index.ts"]
    assert "from '@superset-ui/core'" not in source
    assert "'../adapters/supersetAdapter'" in source


def test_the_spec_matches_how_the_frontend_already_lists_its_plugins() -> None:
    """Checked against the real file rather than a remembered convention."""
    listed = (REPO_ROOT / "superset-frontend" / "package.json").read_text()
    plugin = plugin_skeleton.identity("custom_card", "4d9976")
    prefix = plugin.dependency["spec"].rsplit("/", 1)[0]
    assert f'"{prefix}/' in listed


def test_a_quoted_rationale_does_not_break_package_json() -> None:
    """The description lands in a JSON string as well as in `t('...')`, and a
    double quote is what breaks that one. It failed `npm install` with
    EJSONPARSE while the type-check stayed green."""
    from superset.utils import json

    plugin = plugin_skeleton.identity("custom_card", "t")
    files = plugin_skeleton.render(
        plugin, {"rationale": 'a "hero" KPI that is 12" wide'}, REPO_ROOT
    )
    package = json.loads(files[f"{plugin.directory}/package.json"])
    assert '"' not in package["description"]
    assert "hero" in package["description"]


def test_the_adapter_is_seeded_so_the_skeleton_s_imports_resolve() -> None:
    """`src/plugin/index.ts` takes every symbol through the barrel, so an
    absent barrel is a package that cannot compile before a line is read."""
    plugin = plugin_skeleton.identity("custom_card", "t")
    files = plugin_skeleton.render(plugin, {}, REPO_ROOT)
    adapter = files[f"{plugin.directory}/src/adapters/supersetAdapter.ts"]
    imported = files[f"{plugin.directory}/src/plugin/index.ts"]
    assert "from '../adapters/supersetAdapter'" in imported
    # Every symbol the skeleton takes through the barrel must come back out
    # of it, however it is re-exported.
    for symbol in ("t", "Behavior", "ChartMetadata", "ChartPlugin", "ChartProps"):
        assert f"export const {symbol} =" in adapter or f"  {symbol},\n" in adapter, (
            symbol
        )


def test_the_adapter_may_be_replaced_but_the_naming_files_may_not() -> None:
    """Which symbols the barrel needs depends on what the chart draws."""
    plugin = plugin_skeleton.identity("custom_card", "t")
    owned = plugin_skeleton.owned_paths(plugin, REPO_ROOT)
    assert f"{plugin.directory}/package.json" in owned
    assert f"{plugin.directory}/src/plugin/index.ts" in owned
    assert f"{plugin.directory}/src/adapters/supersetAdapter.ts" not in owned
