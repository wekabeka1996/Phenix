"""
LLM Judge — Config Validation Tests (Phase 1 + Phase 2 + Phase 3 + Phase 4)

Tests JudgeCortexConfig, expert config models, shadow admission,
ChamberConfig validation, VerdictConfig validation, and cross-config
invariants.
"""

import pytest

from apps.reference.domains.alpha_search.judge.config_models import (
    ChamberConfig,
    ConfidenceLadderTier,
    FeatureNeutralsExpertConfig,
    JudgeCortexConfig,
    JudgeExpertsConfig,
    JudgeShadowLogConfig,
    ShadowPlanConfig,
    SignalWeightsExpertConfig,
    VerdictConfig,
)
from apps.reference.domains.alpha_search.config_models import (
    AlphaSearchConfig,
    JudgeExpertProviderConfig,
    ProviderConfig,
    load_alpha_search_config,
)


# ---------------------------------------------------------------------------
# A. JudgeCortexConfig validation (Phase 1 + Phase 2 admission)
# ---------------------------------------------------------------------------

class TestJudgeCortexConfig:
    def test_valid_off_mode(self):
        cfg = JudgeCortexConfig(enabled=False, mode="off")
        assert cfg.mode == "off"
        assert cfg.enabled is False

    def test_enabled_true_mode_off_valid(self):
        cfg = JudgeCortexConfig(enabled=True, mode="off")
        assert cfg.enabled is True

    def test_defaults(self):
        cfg = JudgeCortexConfig()
        assert cfg.enabled is False
        assert cfg.mode == "off"
        assert cfg.experts is None
        assert cfg.shadow_log is None

    def test_shadow_admitted_phase2(self):
        cfg = JudgeCortexConfig(enabled=True, mode="shadow")
        assert cfg.mode == "shadow"

    def test_hybrid_advisory_rejected(self):
        with pytest.raises(ValueError, match="not admitted"):
            JudgeCortexConfig(enabled=False, mode="hybrid_advisory")

    def test_guarded_entry_rejected(self):
        with pytest.raises(ValueError, match="not admitted"):
            JudgeCortexConfig(enabled=False, mode="guarded_entry_authority")

    def test_guarded_lifecycle_rejected(self):
        with pytest.raises(ValueError, match="not admitted"):
            JudgeCortexConfig(
                enabled=False, mode="guarded_lifecycle_authority")

    def test_unknown_mode_rejected(self):
        with pytest.raises(Exception):
            JudgeCortexConfig(enabled=False, mode="unknown_mode")

    def test_extra_field_rejected(self):
        with pytest.raises(Exception):
            JudgeCortexConfig(enabled=False, mode="off", unknown="bad")

    def test_frozen_immutability(self):
        cfg = JudgeCortexConfig(enabled=False, mode="off")
        with pytest.raises(Exception):
            cfg.enabled = True

    def test_shadow_with_experts_and_log(self):
        cfg = JudgeCortexConfig(
            enabled=True,
            mode="shadow",
            experts=JudgeExpertsConfig(),
            shadow_log=JudgeShadowLogConfig(),
        )
        assert cfg.experts is not None
        assert cfg.shadow_log is not None


# ---------------------------------------------------------------------------
# B. SignalWeightsExpertConfig validation
# ---------------------------------------------------------------------------

_SW_WEIGHTS = {"obi": 0.42, "tfi": 0.15, "delta_price": 0.15}
_SW_NEUTRALS = {"obi": 0.0, "tfi": 0.0, "delta_price": 0.0}


class TestSignalWeightsExpertConfig:
    def test_valid_enabled(self):
        cfg = SignalWeightsExpertConfig(
            enabled=True,
            signal_weights=_SW_WEIGHTS,
            feature_neutrals=_SW_NEUTRALS,
        )
        assert cfg.enabled is True
        assert cfg.expert_id == "judge.signal_weights_v1"

    def test_disabled_skips_validation(self):
        cfg = SignalWeightsExpertConfig(enabled=False)
        assert cfg.signal_weights == {}

    def test_defaults(self):
        cfg = SignalWeightsExpertConfig()
        assert cfg.enabled is False
        assert cfg.signal_threshold == 0.162
        assert cfg.normalize_mode == "off"
        assert cfg.min_active_features == 1

    def test_empty_weights_when_enabled_fails(self):
        with pytest.raises(ValueError, match="signal_weights must be non-empty"):
            SignalWeightsExpertConfig(
                enabled=True,
                feature_neutrals=_SW_NEUTRALS,
            )

    def test_empty_neutrals_when_enabled_fails(self):
        with pytest.raises(ValueError, match="feature_neutrals must be non-empty"):
            SignalWeightsExpertConfig(
                enabled=True,
                signal_weights=_SW_WEIGHTS,
            )

    def test_weighted_feature_missing_neutral_fails(self):
        with pytest.raises(ValueError, match="no corresponding neutral"):
            SignalWeightsExpertConfig(
                enabled=True,
                signal_weights={"obi": 0.42, "missing_feat": 0.3},
                feature_neutrals={"obi": 0.0},
            )

    def test_zero_weight_feature_no_neutral_ok(self):
        cfg = SignalWeightsExpertConfig(
            enabled=True,
            signal_weights={"obi": 0.42, "unused": 0.0},
            feature_neutrals={"obi": 0.0},
        )
        assert cfg.signal_weights["unused"] == 0.0

    def test_essential_not_in_weights_fails(self):
        with pytest.raises(ValueError, match="Essential feature"):
            SignalWeightsExpertConfig(
                enabled=True,
                signal_weights=_SW_WEIGHTS,
                feature_neutrals=_SW_NEUTRALS,
                essential_features=["nonexistent"],
            )

    def test_signal_threshold_zero_fails(self):
        with pytest.raises(ValueError, match="signal_threshold must be > 0"):
            SignalWeightsExpertConfig(signal_threshold=0.0)

    def test_signal_threshold_negative_fails(self):
        with pytest.raises(ValueError, match="signal_threshold must be > 0"):
            SignalWeightsExpertConfig(signal_threshold=-0.1)

    def test_invalid_normalize_mode_fails(self):
        with pytest.raises(Exception):
            SignalWeightsExpertConfig(normalize_mode="invalid")

    def test_frozen_immutability(self):
        cfg = SignalWeightsExpertConfig()
        with pytest.raises(Exception):
            cfg.enabled = True

    def test_extra_field_rejected(self):
        with pytest.raises(Exception):
            SignalWeightsExpertConfig(unknown="bad")

    def test_symbols_list(self):
        cfg = SignalWeightsExpertConfig(
            enabled=True,
            signal_weights=_SW_WEIGHTS,
            feature_neutrals=_SW_NEUTRALS,
            symbols=["BTCUSDT", "ETHUSDT"],
        )
        assert cfg.symbols == ["BTCUSDT", "ETHUSDT"]

    def test_min_active_features_zero_fails(self):
        with pytest.raises(ValueError, match="min_active_features must be > 0"):
            SignalWeightsExpertConfig(min_active_features=0)

    def test_min_active_features_above_weighted_feature_count_fails(self):
        with pytest.raises(ValueError, match="min_active_features must be <="):
            SignalWeightsExpertConfig(
                enabled=True,
                signal_weights=_SW_WEIGHTS,
                feature_neutrals=_SW_NEUTRALS,
                min_active_features=10,
            )


# ---------------------------------------------------------------------------
# C. FeatureNeutralsExpertConfig validation
# ---------------------------------------------------------------------------

_FN_DIR = ["obi", "tfi", "delta_price"]
_FN_STR = ["volume_spike"]
_FN_WEIGHTS = {"obi": 0.42, "tfi": 0.15,
               "delta_price": 0.15, "volume_spike": 0.1}
_FN_NEUTRALS = {"obi": 0.0, "tfi": 0.0,
                "delta_price": 0.0, "volume_spike": 0.0}


class TestFeatureNeutralsExpertConfig:
    def test_valid_enabled(self):
        cfg = FeatureNeutralsExpertConfig(
            enabled=True,
            signal_weights=_FN_WEIGHTS,
            feature_neutrals=_FN_NEUTRALS,
            directional_features=_FN_DIR,
            strength_features=_FN_STR,
        )
        assert cfg.enabled is True
        assert cfg.expert_id == "judge.feature_neutrals_v1"
        assert cfg.strength_alpha == 0.5
        assert cfg.strength_cap == 1.0
        assert cfg.min_active_directional_features == 1

    def test_disabled_skips_validation(self):
        cfg = FeatureNeutralsExpertConfig(enabled=False)
        assert cfg.directional_features == []

    def test_empty_directional_when_enabled_fails(self):
        with pytest.raises(ValueError, match="directional_features must be non-empty"):
            FeatureNeutralsExpertConfig(
                enabled=True,
                signal_weights=_FN_WEIGHTS,
                feature_neutrals=_FN_NEUTRALS,
                directional_features=[],
                strength_features=_FN_STR,
            )

    def test_overlapping_dir_str_fails(self):
        with pytest.raises(ValueError, match="must not overlap"):
            FeatureNeutralsExpertConfig(
                enabled=True,
                signal_weights=_FN_WEIGHTS,
                feature_neutrals=_FN_NEUTRALS,
                directional_features=["obi", "volume_spike"],
                strength_features=["volume_spike"],
            )

    def test_strength_alpha_negative_fails(self):
        with pytest.raises(ValueError, match="strength_alpha must be >= 0"):
            FeatureNeutralsExpertConfig(strength_alpha=-0.1)

    def test_strength_cap_negative_fails(self):
        with pytest.raises(ValueError, match="strength_cap must be >= 0"):
            FeatureNeutralsExpertConfig(strength_cap=-1.0)

    def test_strength_alpha_zero_ok(self):
        cfg = FeatureNeutralsExpertConfig(
            enabled=True,
            signal_weights=_FN_WEIGHTS,
            feature_neutrals=_FN_NEUTRALS,
            directional_features=_FN_DIR,
            strength_features=_FN_STR,
            strength_alpha=0.0,
        )
        assert cfg.strength_alpha == 0.0

    def test_signal_threshold_zero_fails(self):
        with pytest.raises(ValueError, match="signal_threshold must be > 0"):
            FeatureNeutralsExpertConfig(signal_threshold=0.0)

    def test_weighted_feature_missing_neutral_fails(self):
        with pytest.raises(ValueError, match="no corresponding neutral"):
            FeatureNeutralsExpertConfig(
                enabled=True,
                signal_weights={"obi": 0.42, "missing": 0.3},
                feature_neutrals={"obi": 0.0},
                directional_features=["obi"],
            )

    def test_essential_not_in_weights_fails(self):
        with pytest.raises(ValueError, match="Essential feature"):
            FeatureNeutralsExpertConfig(
                enabled=True,
                signal_weights=_FN_WEIGHTS,
                feature_neutrals=_FN_NEUTRALS,
                directional_features=_FN_DIR,
                strength_features=_FN_STR,
                essential_features=["nonexistent"],
            )

    def test_frozen_immutability(self):
        cfg = FeatureNeutralsExpertConfig()
        with pytest.raises(Exception):
            cfg.enabled = True

    def test_min_active_directional_features_zero_fails(self):
        with pytest.raises(ValueError, match="min_active_directional_features must be > 0"):
            FeatureNeutralsExpertConfig(min_active_directional_features=0)

    def test_min_active_directional_features_above_available_count_fails(self):
        with pytest.raises(ValueError, match="min_active_directional_features must be <="):
            FeatureNeutralsExpertConfig(
                enabled=True,
                signal_weights=_FN_WEIGHTS,
                feature_neutrals=_FN_NEUTRALS,
                directional_features=_FN_DIR,
                strength_features=_FN_STR,
                min_active_directional_features=10,
            )


# ---------------------------------------------------------------------------
# D. JudgeExpertsConfig / JudgeShadowLogConfig
# ---------------------------------------------------------------------------

class TestJudgeExpertsConfig:
    def test_defaults(self):
        cfg = JudgeExpertsConfig()
        assert cfg.signal_weights.enabled is False
        assert cfg.feature_neutrals.enabled is False

    def test_extra_field_rejected(self):
        with pytest.raises(Exception):
            JudgeExpertsConfig(unknown="bad")


class TestJudgeShadowLogConfig:
    def test_defaults(self):
        cfg = JudgeShadowLogConfig()
        assert cfg.enabled is True
        assert cfg.log_dir == "logs/judge_experts"
        assert cfg.max_file_size_mb == 50
        assert cfg.rotation == "daily"

    def test_extra_field_rejected(self):
        with pytest.raises(Exception):
            JudgeShadowLogConfig(unknown="bad")

    def test_frozen_immutability(self):
        cfg = JudgeShadowLogConfig()
        with pytest.raises(Exception):
            cfg.enabled = False


# ---------------------------------------------------------------------------
# E. AlphaSearchConfig integration
# ---------------------------------------------------------------------------

class TestAlphaSearchConfigIntegration:
    def test_judge_none_default(self):
        cfg = AlphaSearchConfig(enabled=False)
        assert cfg.judge is None

    def test_judge_block_validates(self):
        cfg = AlphaSearchConfig(
            enabled=False,
            judge=JudgeCortexConfig(enabled=False, mode="off"),
        )
        assert cfg.judge is not None
        assert cfg.judge.mode == "off"

    def test_load_from_yaml(self):
        cfg = load_alpha_search_config("config/alpha_search.yaml")
        assert cfg.judge is not None
        assert cfg.judge.enabled is True
        assert cfg.judge.mode == "shadow"

    def test_existing_fields_preserved(self):
        cfg = load_alpha_search_config("config/alpha_search.yaml")
        assert cfg.enabled is True
        assert "aurora" in cfg.providers
        assert "ta_ensemble" in cfg.providers

    def test_repo_config_includes_explicit_judge_providers(self):
        cfg = load_alpha_search_config("config/alpha_search.yaml")
        assert "judge_sw" in cfg.providers
        assert "judge_fn" in cfg.providers
        assert cfg.providers["judge_sw"].judge_expert is not None
        assert cfg.providers["judge_sw"].judge_expert.expert_type == "signal_weights"
        assert cfg.providers["judge_fn"].judge_expert is not None
        assert cfg.providers["judge_fn"].judge_expert.expert_type == "feature_neutrals"

    def test_judge_provider_threshold_drift_fails_closed(self):
        with pytest.raises(ValueError, match="threshold drift"):
            AlphaSearchConfig(
                enabled=False,
                providers={
                    "judge_sw": ProviderConfig(
                        enabled=True,
                        threshold=0.10,
                        judge_expert=JudgeExpertProviderConfig(
                            expert_type="signal_weights"
                        ),
                    )
                },
                judge=JudgeCortexConfig(
                    enabled=True,
                    mode="shadow",
                    experts=JudgeExpertsConfig(
                        signal_weights=SignalWeightsExpertConfig(
                            enabled=True,
                            signal_threshold=0.162,
                            signal_weights=_SW_WEIGHTS,
                            feature_neutrals=_SW_NEUTRALS,
                        )
                    ),
                ),
            )


# ---------------------------------------------------------------------------
# F. ChamberConfig validation (Phase 3)
# ---------------------------------------------------------------------------

class TestChamberConfig:
    def test_defaults(self):
        cfg = ChamberConfig()
        assert cfg.min_quorum == 1
        assert cfg.max_staleness_ms == 30000
        assert cfg.entry_enabled is True
        assert cfg.lifecycle_enabled is False

    def test_custom_values(self):
        cfg = ChamberConfig(min_quorum=2, max_staleness_ms=60000)
        assert cfg.min_quorum == 2
        assert cfg.max_staleness_ms == 60000

    def test_min_quorum_zero_allowed(self):
        cfg = ChamberConfig(min_quorum=0)
        assert cfg.min_quorum == 0

    def test_min_quorum_negative_rejected(self):
        with pytest.raises(ValueError, match="min_quorum must be >= 0"):
            ChamberConfig(min_quorum=-1)

    def test_max_staleness_zero_rejected(self):
        with pytest.raises(ValueError, match="max_staleness_ms must be > 0"):
            ChamberConfig(max_staleness_ms=0)

    def test_max_staleness_negative_rejected(self):
        with pytest.raises(ValueError, match="max_staleness_ms must be > 0"):
            ChamberConfig(max_staleness_ms=-1000)

    def test_frozen_immutability(self):
        cfg = ChamberConfig()
        with pytest.raises(Exception):
            cfg.min_quorum = 5

    def test_extra_field_rejected(self):
        with pytest.raises(Exception):
            ChamberConfig(unknown="bad")

    def test_lifecycle_enabled_explicit(self):
        cfg = ChamberConfig(lifecycle_enabled=True)
        assert cfg.lifecycle_enabled is True


# ---------------------------------------------------------------------------
# G. JudgeCortexConfig with ChamberConfig (Phase 3 integration)
# ---------------------------------------------------------------------------

class TestJudgeCortexConfigChamber:
    def test_chamber_none_default(self):
        cfg = JudgeCortexConfig()
        assert cfg.chamber is None

    def test_chamber_block_accepted(self):
        cfg = JudgeCortexConfig(
            enabled=False,
            mode="off",
            chamber=ChamberConfig(),
        )
        assert cfg.chamber is not None
        assert cfg.chamber.min_quorum == 1

    def test_chamber_backward_compat_no_chamber(self):
        """Existing configs without chamber: block still load."""
        cfg = JudgeCortexConfig(
            enabled=True,
            mode="shadow",
            experts=JudgeExpertsConfig(),
            shadow_log=JudgeShadowLogConfig(),
        )
        assert cfg.chamber is None

    def test_chamber_with_shadow_mode(self):
        cfg = JudgeCortexConfig(
            enabled=True,
            mode="shadow",
            chamber=ChamberConfig(min_quorum=2, max_staleness_ms=15000),
        )
        assert cfg.chamber.min_quorum == 2
        assert cfg.chamber.max_staleness_ms == 15000

    def test_load_yaml_with_chamber(self):
        """YAML config loads with the new chamber: block."""
        cfg = load_alpha_search_config("config/alpha_search.yaml")
        assert cfg.judge is not None
        assert cfg.judge.chamber is not None
        assert cfg.judge.chamber.min_quorum == 1
        assert cfg.judge.chamber.max_staleness_ms == 30000
        assert cfg.judge.chamber.entry_enabled is True
        assert cfg.judge.chamber.lifecycle_enabled is False
        assert cfg.judge.experts.signal_weights.min_active_features == 4
        assert cfg.judge.experts.feature_neutrals.min_active_directional_features == 4


# ---------------------------------------------------------------------------
# H. VerdictConfig validation (Phase 4)
# ---------------------------------------------------------------------------

class TestVerdictConfig:
    def test_defaults(self):
        cfg = VerdictConfig()
        assert cfg.entry_enabled is True
        assert cfg.lifecycle_enabled is False
        assert cfg.strategy_id == "aurora"
        assert cfg.cortex_version == "phase4_shadow_v1"
        assert cfg.split_confidence_discount == 0.5
        assert cfg.shadow_plan is None

    def test_custom_values(self):
        cfg = VerdictConfig(
            entry_enabled=False,
            lifecycle_enabled=False,
            strategy_id="custom_strat",
            cortex_version="v2",
            split_confidence_discount=0.3,
        )
        assert cfg.strategy_id == "custom_strat"
        assert cfg.split_confidence_discount == 0.3

    def test_split_discount_zero_ok(self):
        cfg = VerdictConfig(split_confidence_discount=0.0)
        assert cfg.split_confidence_discount == 0.0

    def test_split_discount_one_ok(self):
        cfg = VerdictConfig(split_confidence_discount=1.0)
        assert cfg.split_confidence_discount == 1.0

    def test_split_discount_negative_rejected(self):
        with pytest.raises(ValueError, match="split_confidence_discount must be in"):
            VerdictConfig(split_confidence_discount=-0.1)

    def test_split_discount_above_one_rejected(self):
        with pytest.raises(ValueError, match="split_confidence_discount must be in"):
            VerdictConfig(split_confidence_discount=1.1)

    def test_frozen_immutability(self):
        cfg = VerdictConfig()
        with pytest.raises(Exception):
            cfg.entry_enabled = False

    def test_extra_field_rejected(self):
        with pytest.raises(Exception):
            VerdictConfig(unknown="bad")

    def test_lifecycle_enabled_explicit(self):
        cfg = VerdictConfig(lifecycle_enabled=True)
        assert cfg.lifecycle_enabled is True

    def test_shadow_plan_block_accepted(self):
        cfg = VerdictConfig(
            shadow_plan=ShadowPlanConfig(
                enabled=True,
                confidence_ladder=[
                    ConfidenceLadderTier(
                        name="low",
                        min_confidence=0.2,
                        limit_offset_bps=0,
                        tp_offset_pct=0.01,
                        sl_offset_pct=0.006,
                    ),
                    ConfidenceLadderTier(
                        name="high",
                        min_confidence=0.5,
                        limit_offset_bps=5,
                        tp_offset_pct=0.02,
                        sl_offset_pct=0.01,
                    ),
                ],
            )
        )
        assert cfg.shadow_plan is not None
        assert cfg.shadow_plan.enabled is True
        assert cfg.shadow_plan.confidence_ladder[1].name == "high"


class TestShadowPlanConfig:
    def test_defaults(self):
        cfg = ShadowPlanConfig()
        assert cfg.enabled is False
        assert cfg.order_type == "HYPOTHETICAL_LIMIT"
        assert cfg.emit_all_tiers is True
        assert cfg.price_ref_source == "verdict_context"
        assert cfg.confidence_ladder == []

    def test_enabled_requires_non_empty_ladder(self):
        with pytest.raises(ValueError, match="requires non-empty confidence_ladder"):
            ShadowPlanConfig(enabled=True)

    def test_ladder_must_be_sorted_ascending(self):
        with pytest.raises(ValueError, match="sorted ascending"):
            ShadowPlanConfig(
                enabled=True,
                confidence_ladder=[
                    ConfidenceLadderTier(
                        name="high",
                        min_confidence=0.5,
                        limit_offset_bps=5,
                        tp_offset_pct=0.02,
                        sl_offset_pct=0.01,
                    ),
                    ConfidenceLadderTier(
                        name="low",
                        min_confidence=0.2,
                        limit_offset_bps=0,
                        tp_offset_pct=0.01,
                        sl_offset_pct=0.006,
                    ),
                ],
            )

    def test_duplicate_tier_names_rejected(self):
        with pytest.raises(ValueError, match="tier names must be unique"):
            ShadowPlanConfig(
                enabled=True,
                confidence_ladder=[
                    ConfidenceLadderTier(
                        name="low",
                        min_confidence=0.2,
                        limit_offset_bps=0,
                        tp_offset_pct=0.01,
                        sl_offset_pct=0.006,
                    ),
                    ConfidenceLadderTier(
                        name="low",
                        min_confidence=0.5,
                        limit_offset_bps=5,
                        tp_offset_pct=0.02,
                        sl_offset_pct=0.01,
                    ),
                ],
            )


# ---------------------------------------------------------------------------
# I. JudgeCortexConfig with VerdictConfig (Phase 4 integration)
# ---------------------------------------------------------------------------

class TestJudgeCortexConfigVerdict:
    def test_verdict_none_default(self):
        cfg = JudgeCortexConfig()
        assert cfg.verdict is None

    def test_verdict_block_accepted(self):
        cfg = JudgeCortexConfig(
            enabled=False,
            mode="off",
            chamber=ChamberConfig(),
            verdict=VerdictConfig(),
        )
        assert cfg.verdict is not None
        assert cfg.verdict.entry_enabled is True
        assert cfg.verdict.strategy_id == "aurora"

    def test_verdict_backward_compat_no_verdict(self):
        """Existing configs without verdict: block still load."""
        cfg = JudgeCortexConfig(
            enabled=True,
            mode="shadow",
            experts=JudgeExpertsConfig(),
            shadow_log=JudgeShadowLogConfig(),
            chamber=ChamberConfig(),
        )
        assert cfg.verdict is None

    def test_verdict_with_shadow_mode(self):
        cfg = JudgeCortexConfig(
            enabled=True,
            mode="shadow",
            chamber=ChamberConfig(),
            verdict=VerdictConfig(
                strategy_id="test_strat",
                split_confidence_discount=0.7,
            ),
        )
        assert cfg.verdict.strategy_id == "test_strat"
        assert cfg.verdict.split_confidence_discount == 0.7

    def test_load_yaml_with_verdict(self):
        """YAML config loads with the new verdict: block."""
        cfg = load_alpha_search_config("config/alpha_search.yaml")
        assert cfg.judge is not None
        assert cfg.judge.verdict is not None
        assert cfg.judge.verdict.entry_enabled is True
        assert cfg.judge.verdict.lifecycle_enabled is False
        assert cfg.judge.verdict.strategy_id == "aurora"
        assert cfg.judge.verdict.cortex_version == "phase4_shadow_v1"
        assert cfg.judge.verdict.split_confidence_discount == 0.5
        assert cfg.judge.verdict.shadow_plan is not None
        assert cfg.judge.verdict.shadow_plan.enabled is True
        assert len(cfg.judge.verdict.shadow_plan.confidence_ladder) == 3
        assert cfg.judge.verdict.shadow_plan.confidence_ladder[1].name == "medium"


# ---------------------------------------------------------------------------
# J. Cross-config invariant: verdict ⊆ chamber (Phase 4)
# ---------------------------------------------------------------------------

class TestVerdictChamberInvariant:
    def test_entry_wider_than_chamber_rejected(self):
        """verdict.entry_enabled=true + chamber.entry_enabled=false → error."""
        with pytest.raises(ValueError, match="verdict.entry_enabled=true requires"):
            JudgeCortexConfig(
                enabled=False,
                mode="off",
                chamber=ChamberConfig(entry_enabled=False),
                verdict=VerdictConfig(entry_enabled=True),
            )

    def test_lifecycle_wider_than_chamber_rejected(self):
        """verdict.lifecycle_enabled=true + chamber.lifecycle_enabled=false → error."""
        with pytest.raises(ValueError, match="verdict.lifecycle_enabled=true requires"):
            JudgeCortexConfig(
                enabled=False,
                mode="off",
                chamber=ChamberConfig(lifecycle_enabled=False),
                verdict=VerdictConfig(lifecycle_enabled=True),
            )

    def test_verdict_without_chamber_rejected(self):
        """verdict config present but chamber absent → error."""
        with pytest.raises(ValueError, match="verdict config requires chamber"):
            JudgeCortexConfig(
                enabled=False,
                mode="off",
                chamber=None,
                verdict=VerdictConfig(),
            )

    def test_verdict_narrower_than_chamber_ok(self):
        """verdict narrower than chamber is allowed."""
        cfg = JudgeCortexConfig(
            enabled=False,
            mode="off",
            chamber=ChamberConfig(entry_enabled=True, lifecycle_enabled=True),
            verdict=VerdictConfig(entry_enabled=True, lifecycle_enabled=False),
        )
        assert cfg.verdict.lifecycle_enabled is False
        assert cfg.chamber.lifecycle_enabled is True

    def test_verdict_absent_with_chamber_ok(self):
        """No verdict config + chamber present → Phase 3 behavior."""
        cfg = JudgeCortexConfig(
            enabled=False,
            mode="off",
            chamber=ChamberConfig(),
            verdict=None,
        )
        assert cfg.verdict is None
        assert cfg.chamber is not None

    def test_both_enabled_matching(self):
        """Both entry and lifecycle match between verdict and chamber."""
        cfg = JudgeCortexConfig(
            enabled=True,
            mode="shadow",
            chamber=ChamberConfig(entry_enabled=True, lifecycle_enabled=True),
            verdict=VerdictConfig(entry_enabled=True, lifecycle_enabled=True),
        )
        assert cfg.verdict.entry_enabled is True
        assert cfg.verdict.lifecycle_enabled is True

    def test_both_disabled_ok(self):
        """Both entry and lifecycle disabled in verdict → valid (no-op verdict)."""
        cfg = JudgeCortexConfig(
            enabled=False,
            mode="off",
            chamber=ChamberConfig(entry_enabled=False,
                                  lifecycle_enabled=False),
            verdict=VerdictConfig(entry_enabled=False,
                                  lifecycle_enabled=False),
        )
        assert cfg.verdict.entry_enabled is False
