"""
LLM Judge Phase 2 — No Live Aurora Regression Tests

Verifies that Phase 2 changes do not affect the quadratic scoring kernel,
live Aurora decision path, or existing provider configurations.
"""

import pytest

from apps.reference.domains.alpha_search.backtest_plugin import AlphaSearchBacktestPlugin
from apps.reference.domains.alpha_search.config_models import (
    AlphaSearchConfig,
    ProviderConfig,
    JudgeExpertProviderConfig,
    load_alpha_search_config,
)


class _StubEventBus:
    def emit(self, event_name: str, payload: dict, why: str = ""):
        return None

    def listen(self, event_name: str, handler):
        return None


def _load_repo_runtime_config(
    *,
    judge_enabled: bool,
    judge_mode: str,
    sw_enabled: bool = True,
    fn_enabled: bool = True,
) -> AlphaSearchConfig:
    cfg = load_alpha_search_config("config/alpha_search.yaml")
    raw = cfg.model_dump()
    raw["virtual_trader"]["enabled"] = False
    raw["judge"]["enabled"] = judge_enabled
    raw["judge"]["mode"] = judge_mode
    raw["judge"]["shadow_log"]["enabled"] = False
    raw["judge"]["experts"]["signal_weights"]["enabled"] = sw_enabled
    raw["judge"]["experts"]["feature_neutrals"]["enabled"] = fn_enabled
    return AlphaSearchConfig.model_validate(raw)


class TestQuadraticKernelUnaffected:
    def test_aurora_adapter_still_works(self):
        """Aurora adapter provider config unchanged."""
        cfg = load_alpha_search_config("config/alpha_search.yaml")
        assert "aurora" in cfg.providers
        aurora_cfg = cfg.providers["aurora"]
        assert aurora_cfg.adapter is not None
        assert aurora_cfg.judge_expert is None

    def test_ta_ensemble_still_works(self):
        """TA ensemble provider config unchanged."""
        cfg = load_alpha_search_config("config/alpha_search.yaml")
        assert "ta_ensemble" in cfg.providers
        te_cfg = cfg.providers["ta_ensemble"]
        assert te_cfg.ensemble is not None
        assert te_cfg.judge_expert is None

    def test_non_judge_providers_keep_existing_contracts(self):
        """Existing non-judge providers keep their original provider contracts."""
        cfg = load_alpha_search_config("config/alpha_search.yaml")
        for name in ("aurora", "ta_ensemble"):
            pcfg = cfg.providers[name]
            assert pcfg.judge_expert is None, f"Provider '{name}' has unexpected judge_expert"

    def test_repo_config_declares_explicit_judge_providers(self):
        cfg = load_alpha_search_config("config/alpha_search.yaml")
        assert cfg.providers["judge_sw"].judge_expert is not None
        assert cfg.providers["judge_sw"].judge_expert.expert_type == "signal_weights"
        assert cfg.providers["judge_fn"].judge_expert is not None
        assert cfg.providers["judge_fn"].judge_expert.expert_type == "feature_neutrals"

    def test_mode_off_keeps_repo_judge_providers_inert(self):
        cfg = _load_repo_runtime_config(judge_enabled=False, judge_mode="off")
        plugin = AlphaSearchBacktestPlugin(
            event_bus=_StubEventBus(), config=cfg)
        assert "judge_sw" not in plugin.providers
        assert "judge_fn" not in plugin.providers
        assert all(
            pcfg.judge_expert is None
            for pcfg in plugin.provider_configs.values()
        )

    def test_disabled_repo_expert_is_not_initialized_or_solicited(self):
        cfg = _load_repo_runtime_config(
            judge_enabled=True,
            judge_mode="shadow",
            sw_enabled=True,
            fn_enabled=False,
        )
        plugin = AlphaSearchBacktestPlugin(
            event_bus=_StubEventBus(), config=cfg)
        active_judge_providers = {
            name
            for name, pcfg in plugin.provider_configs.items()
            if pcfg.judge_expert is not None
        }
        assert "judge_fn" in cfg.providers
        assert cfg.providers["judge_fn"].judge_expert is not None
        assert active_judge_providers == {"judge_sw"}
        assert "judge_fn" not in plugin.provider_configs


class TestProviderMutualExclusion:
    def test_adapter_and_judge_expert_rejected(self):
        with pytest.raises(Exception, match="at most one"):
            ProviderConfig(
                adapter={"scoring_version": "v2"},
                judge_expert=JudgeExpertProviderConfig(
                    expert_type="signal_weights"),
            )

    def test_ensemble_and_judge_expert_rejected(self):
        with pytest.raises(Exception, match="at most one"):
            ProviderConfig(
                ensemble={},
                judge_expert=JudgeExpertProviderConfig(
                    expert_type="signal_weights"),
            )

    def test_judge_expert_alone_ok(self):
        pc = ProviderConfig(
            judge_expert=JudgeExpertProviderConfig(
                expert_type="signal_weights"),
        )
        assert pc.judge_expert is not None
        assert pc.adapter is None
        assert pc.ensemble is None


class TestConfigLoadStability:
    def test_full_config_loads(self):
        """Full alpha_search.yaml loads without errors."""
        cfg = load_alpha_search_config("config/alpha_search.yaml")
        assert cfg.enabled is True

    def test_judge_defaults_safe(self):
        """Repo config keeps judge in shadow mode, not live authority."""
        cfg = load_alpha_search_config("config/alpha_search.yaml")
        assert cfg.judge.enabled is True
        assert cfg.judge.mode == "shadow"

    def test_judge_does_not_change_shadow_mode(self):
        """alpha_search shadow_mode unrelated to judge mode."""
        cfg = load_alpha_search_config("config/alpha_search.yaml")
        assert cfg.shadow_mode is True  # unchanged
