"""
LLM Judge Phase 2 — Shadow Mode Admission Tests

Tests that shadow mode is correctly admitted, expert gating respects
judge mode, and non-admitted modes are rejected.
"""

import pytest

from apps.reference.domains.alpha_search.judge.config_models import (
    FeatureNeutralsExpertConfig,
    JudgeCortexConfig,
    JudgeExpertsConfig,
    JudgeShadowLogConfig,
    SignalWeightsExpertConfig,
)


_SW_WEIGHTS = {"obi": 0.42, "tfi": 0.15}
_SW_NEUTRALS = {"obi": 0.0, "tfi": 0.0}

_FN_WEIGHTS = {"obi": 0.42, "tfi": 0.15, "volume_spike": 0.1}
_FN_NEUTRALS = {"obi": 0.0, "tfi": 0.0, "volume_spike": 0.0}


class TestShadowModeAdmission:
    def test_off_mode_admitted(self):
        cfg = JudgeCortexConfig(enabled=False, mode="off")
        assert cfg.mode == "off"

    def test_shadow_mode_admitted(self):
        cfg = JudgeCortexConfig(enabled=True, mode="shadow")
        assert cfg.mode == "shadow"

    def test_hybrid_advisory_rejected(self):
        with pytest.raises(ValueError, match="not admitted"):
            JudgeCortexConfig(mode="hybrid_advisory")

    def test_guarded_entry_rejected(self):
        with pytest.raises(ValueError, match="not admitted"):
            JudgeCortexConfig(mode="guarded_entry_authority")

    def test_guarded_lifecycle_rejected(self):
        with pytest.raises(ValueError, match="not admitted"):
            JudgeCortexConfig(mode="guarded_lifecycle_authority")


class TestShadowWithExperts:
    def test_shadow_with_both_experts_enabled(self):
        cfg = JudgeCortexConfig(
            enabled=True,
            mode="shadow",
            experts=JudgeExpertsConfig(
                signal_weights=SignalWeightsExpertConfig(
                    enabled=True,
                    signal_weights=_SW_WEIGHTS,
                    feature_neutrals=_SW_NEUTRALS,
                ),
                feature_neutrals=FeatureNeutralsExpertConfig(
                    enabled=True,
                    signal_weights=_FN_WEIGHTS,
                    feature_neutrals=_FN_NEUTRALS,
                    directional_features=["obi", "tfi"],
                    strength_features=["volume_spike"],
                ),
            ),
            shadow_log=JudgeShadowLogConfig(),
        )
        assert cfg.experts.signal_weights.enabled is True
        assert cfg.experts.feature_neutrals.enabled is True
        assert cfg.shadow_log.enabled is True

    def test_shadow_with_one_expert_disabled(self):
        cfg = JudgeCortexConfig(
            enabled=True,
            mode="shadow",
            experts=JudgeExpertsConfig(
                signal_weights=SignalWeightsExpertConfig(
                    enabled=True,
                    signal_weights=_SW_WEIGHTS,
                    feature_neutrals=_SW_NEUTRALS,
                ),
                feature_neutrals=FeatureNeutralsExpertConfig(enabled=False),
            ),
        )
        assert cfg.experts.feature_neutrals.enabled is False

    def test_off_mode_with_experts_configured_ok(self):
        """Off mode with experts is valid — experts simply won't run."""
        cfg = JudgeCortexConfig(
            enabled=False,
            mode="off",
            experts=JudgeExpertsConfig(
                signal_weights=SignalWeightsExpertConfig(
                    enabled=True,
                    signal_weights=_SW_WEIGHTS,
                    feature_neutrals=_SW_NEUTRALS,
                ),
            ),
        )
        assert cfg.mode == "off"

    def test_shadow_without_experts_ok(self):
        """Shadow mode without experts is valid — just no expert outputs."""
        cfg = JudgeCortexConfig(enabled=True, mode="shadow")
        assert cfg.experts is None
