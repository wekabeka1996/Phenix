from __future__ import annotations

from pathlib import Path

import yaml

from apps.reference.domains.alpha_search.runtime.contracts import ScenarioMatrixConfig
from apps.reference.domains.alpha_search.runtime.override_allowlist import validate_overrides
from apps.reference.domains.alpha_search.shadow.registry_adapter import _normalise_override_key


def test_shadow_registry_supports_strategy_mean_reversion_override_prefix():
    assert (
        _normalise_override_key("strategy.mean_reversion.strategy.entry_threshold")
        == "mean_reversion.strategy.entry_threshold"
    )
    assert (
        _normalise_override_key("mean_reversion.weights.rsi")
        == "alpha_search_system.mean_reversion.weights.rsi"
    )


def test_live_mr_mirror_scenarios_exist_in_matrix_and_are_rule_style():
    data = yaml.safe_load(Path("config/alpha_search/scenario_matrix.yaml").read_text(encoding="utf-8"))
    ScenarioMatrixConfig.model_validate(data)
    scenarios = {item["scenario_id"]: item for item in data["scenarios"]}
    expected = {
        "S31_LIVE_MR_BASELINE",
        "S32_LIVE_MR_RSI_STRICT",
        "S33_LIVE_MR_EXTREME_DEVIATION",
        "S34_LIVE_MR_LOW_VOL_SAFE",
    }
    assert expected <= set(scenarios)
    for scenario_id in expected:
        overrides = scenarios[scenario_id]["overrides"]
        assert all(not key.startswith("alpha_search_system.mean_reversion.weights") for key in overrides)
        assert any(key.startswith("mean_reversion.strategy.") for key in overrides)
        assert validate_overrides("mean_reversion", overrides) == []
