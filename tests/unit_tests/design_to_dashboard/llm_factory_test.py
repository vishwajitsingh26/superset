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
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from superset.design_to_dashboard.llm import api_provider, factory
from superset.design_to_dashboard.llm.base import lower_effort


def _conf(**overrides: Any) -> dict[str, Any]:
    return {**factory.DEFAULTS, **overrides}


def _provider(stage: str | None, **conf: Any) -> Any:
    app = MagicMock()
    app.config = {"DESIGN_TO_DASHBOARD_LLM": conf}
    with (
        patch.object(factory, "current_app", app),
        patch.object(
            api_provider.AnthropicApiProvider, "_build_client", return_value=None
        ),
        patch.object(api_provider.BedrockProvider, "_build_client", return_value=None),
    ):
        return factory.get_llm_provider(stage)


def test_stage_f_budget_is_lifted_to_its_floor() -> None:
    """The floor alone is not enough: the top-level ceiling here (64000, the
    default) still caps it, same as before this floor was raised to 80000 --
    a deployment has to raise `max_tokens_ceiling` too, which is what
    `test_the_ceiling_has_to_rise_with_the_floor_for_it_to_take_effect`
    below is about."""
    assert factory._resolve_budget(_conf(max_tokens=32000), "F") == (64000, 64000)


def test_the_ceiling_has_to_rise_with_the_floor_for_it_to_take_effect() -> None:
    conf = _conf(max_tokens=32000, stage_models={"F": {"max_tokens_ceiling": 80000}})
    assert factory._resolve_budget(conf, "F") == (80000, 80000)


def test_other_stages_keep_the_top_level_budget() -> None:
    assert factory._resolve_budget(_conf(max_tokens=32000), "C") == (32000, 64000)
    assert factory._resolve_budget(_conf(max_tokens=32000), None) == (32000, 64000)


def test_a_larger_top_level_budget_is_not_lowered_for_stage_f() -> None:
    conf = _conf(max_tokens=128000, max_tokens_ceiling=128000)
    assert factory._resolve_budget(conf, "F") == (128000, 128000)


def test_stage_models_mapping_sets_the_budget_for_one_stage() -> None:
    conf = _conf(
        stage_models={"F": {"model": "m", "max_tokens": 48000}},
        max_tokens_ceiling=96000,
    )
    assert factory._resolve_budget(conf, "F") == (48000, 96000)

    conf = _conf(stage_models={"D": {"max_tokens_ceiling": 32000}})
    assert factory._resolve_budget(conf, "D") == (32000, 32000)


def test_api_provider_receives_the_stage_budget() -> None:
    provider = _provider("F", provider="anthropic_api", max_tokens=32000)

    assert provider.max_tokens == 64000
    assert provider.max_tokens_ceiling == 64000


def test_api_provider_receives_the_raised_stage_budget_once_the_ceiling_allows_it() -> (
    None
):
    provider = _provider(
        "F",
        provider="anthropic_api",
        max_tokens=32000,
        stage_models={"F": {"max_tokens_ceiling": 80000}},
    )

    assert provider.max_tokens == 80000
    assert provider.max_tokens_ceiling == 80000


def test_bedrock_provider_receives_the_configured_ceiling() -> None:
    provider = _provider(
        "C", provider="bedrock", model="claude-opus-5", max_tokens_ceiling=100000
    )

    assert provider.max_tokens == 32000
    assert provider.max_tokens_ceiling == 100000


def test_effort_argument_overrides_the_configured_effort() -> None:
    app = MagicMock()
    app.config = {
        "DESIGN_TO_DASHBOARD_LLM": {"provider": "anthropic_api", "effort": "high"}
    }
    with (
        patch.object(factory, "current_app", app),
        patch.object(
            api_provider.AnthropicApiProvider, "_build_client", return_value=None
        ),
    ):
        provider: Any = factory.get_llm_provider("F", effort="low")

    assert provider.effort == "low"


def test_lower_effort_steps_down_one_level() -> None:
    assert lower_effort("max") == "xhigh"
    assert lower_effort("medium") == "low"
    assert lower_effort("low") is None
    assert lower_effort("unknown") is None


def test_a_stage_floor_never_exceeds_the_ceiling() -> None:
    """A model with a 32k output limit is declared once, and every stage obeys."""
    conf = _conf(max_tokens=32000, max_tokens_ceiling=32000)
    assert factory._resolve_budget(conf, "F") == (32000, 32000)


def test_a_stage_ceiling_caps_that_stage_s_floor() -> None:
    conf = _conf(stage_models={"F": {"max_tokens_ceiling": 48000}})
    assert factory._resolve_budget(conf, "F") == (48000, 48000)


def test_stage_f_runs_at_xhigh_effort_over_a_lower_top_level_effort() -> None:
    conf = _conf(model="m", effort="medium")
    assert factory._resolve_stage(conf, "F") == ("m", "xhigh")


def test_other_stages_keep_the_top_level_effort() -> None:
    conf = _conf(model="m", effort="medium")
    assert factory._resolve_stage(conf, "C") == ("m", "medium")
    assert factory._resolve_stage(conf, None) == ("m", "medium")


def test_a_stage_models_effort_outranks_the_stage_default() -> None:
    conf = _conf(model="m", effort="medium", stage_models={"F": {"effort": "low"}})
    assert factory._resolve_stage(conf, "F") == ("m", "low")


def test_a_model_name_override_keeps_the_stage_default_effort() -> None:
    conf = _conf(model="m", effort="medium", stage_models={"F": "other"})
    assert factory._resolve_stage(conf, "F") == ("other", "xhigh")


def test_the_stage_f_provider_is_built_at_xhigh_effort() -> None:
    provider = _provider("F", provider="anthropic_api", effort="medium")
    assert provider.effort == "xhigh"


def test_stage_f_turns_is_lifted_to_its_floor() -> None:
    assert factory._resolve_turns(_conf(max_turns=6), "F") == 16


def test_other_stages_keep_the_top_level_turns() -> None:
    assert factory._resolve_turns(_conf(max_turns=6), "C") == 6
    assert factory._resolve_turns(_conf(max_turns=6), None) == 6


def test_a_larger_top_level_turns_is_not_lowered_for_stage_f() -> None:
    assert factory._resolve_turns(_conf(max_turns=20), "F") == 20


def test_stage_models_mapping_sets_turns_for_one_stage() -> None:
    conf = _conf(stage_models={"F": {"model": "m", "max_turns": 10}})
    assert factory._resolve_turns(conf, "F") == 10

    conf = _conf(stage_models={"D": {"max_turns": 12}})
    assert factory._resolve_turns(conf, "D") == 12


def test_max_turns_none_means_no_cap_for_every_stage() -> None:
    """Observation mode: no floor applies once there is no ceiling to lift."""
    conf = _conf(max_turns=None)
    assert factory._resolve_turns(conf, "F") is None
    assert factory._resolve_turns(conf, "A") is None
    assert factory._resolve_turns(conf, None) is None


def test_a_stage_can_be_uncapped_while_others_stay_capped() -> None:
    conf = _conf(max_turns=6, stage_models={"F": {"max_turns": None}})
    assert factory._resolve_turns(conf, "F") is None
    assert factory._resolve_turns(conf, "C") == 6


def test_max_turns_argument_bypasses_the_resolver() -> None:
    """A caller re-running a stage after it exhausted its turns names the
    budget it wants directly -- the same override `effort` already gets for a
    reply cut off at its output budget."""
    app = MagicMock()
    app.config = {
        "DESIGN_TO_DASHBOARD_LLM": {"provider": "anthropic_api", "max_turns": 6}
    }
    with (
        patch.object(factory, "current_app", app),
        patch.object(factory, "_resolve_turns") as resolve_turns,
        patch.object(
            api_provider.AnthropicApiProvider, "_build_client", return_value=None
        ),
    ):
        factory.get_llm_provider("F", max_turns=30)
    resolve_turns.assert_not_called()
