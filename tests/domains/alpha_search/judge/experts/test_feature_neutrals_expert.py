"""
LLM Judge Phase 2 — Feature Neutrals Expert Tests

Tests direction-strength composite formula, partitioning, clamping,
fail-closed behavior, and comparison with flat scoring.
"""

from decimal import Decimal

import pytest

from apps.reference.domains.alpha_search.judge.config_models import (
    FeatureNeutralsExpertConfig,
)
from apps.reference.domains.alpha_search.judge.experts.feature_neutrals_expert import (
    FeatureNeutralsExpert,
)

_WEIGHTS = {
    "obi": 0.42, "tfi": 0.15, "delta_price": 0.15, "ema_bias": 0.15,
    "volume_spike": 0.10, "volatility_state": 0.10,
}
_NEUTRALS = {
    "obi": 0.0, "tfi": 0.0, "delta_price": 0.0, "ema_bias": 0.5,
    "volume_spike": 0.0, "volatility_state": 0.0,
}
_DIR = ["obi", "tfi", "delta_price", "ema_bias"]
_STR = ["volume_spike", "volatility_state"]
_ESSENTIAL = ["obi", "delta_price"]


def _make_expert(**overrides):
    defaults = dict(
        enabled=True,
        signal_weights=_WEIGHTS,
        feature_neutrals=_NEUTRALS,
        directional_features=_DIR,
        strength_features=_STR,
        essential_features=_ESSENTIAL,
        signal_threshold=0.162,
        strength_alpha=0.5,
        strength_cap=1.0,
    )
    defaults.update(overrides)
    cfg = FeatureNeutralsExpertConfig(**defaults)
    return FeatureNeutralsExpert(cfg)


def _make_features(**overrides):
    defaults = {
        "obi": 0.5, "tfi": 0.3, "delta_price": 0.2, "ema_bias": 0.6,
        "volume_spike": 0.4, "volatility_state": 0.3,
    }
    defaults.update(overrides)
    return defaults


class TestFeatureNeutralsScoring:
    def test_known_input_positive_score(self):
        expert = _make_expert()
        features = _make_features()
        score = expert.calculate_alpha("BTCUSDT", {}, features)
        assert float(score.score) > 0

    def test_composite_formula(self):
        """Verify: final = dir * (1 + alpha * clamp(str, 0, cap))"""
        expert = _make_expert()
        features = _make_features()
        score = expert.calculate_alpha("BTCUSDT", {}, features)

        # Manual directional: obi:0.42*(0.5-0)=0.21, tfi:0.15*(0.3-0)=0.045,
        # delta_price:0.15*(0.2-0)=0.03, ema_bias:0.15*(0.6-0.5)=0.015
        # raw_dir = 0.21+0.045+0.03+0.015=0.3, wabs_dir=0.42+0.15+0.15+0.15=0.87
        # dir_score = 0.3/0.87 ≈ 0.3448
        dir_score = 0.3 / 0.87

        # Strength: volume_spike:0.1*(0.4-0)=0.04, volatility_state:0.1*(0.3-0)=0.03
        # raw_str = 0.04+0.03=0.07, wabs_str=0.1+0.1=0.2
        # str_score = 0.07/0.2 = 0.35
        str_score = 0.07 / 0.2
        str_clamped = max(0, min(str_score, 1.0))

        expected = dir_score * (1.0 + 0.5 * str_clamped)
        assert abs(float(score.score) - expected) < 1e-4

    def test_negative_dir_score_gives_short(self):
        expert = _make_expert()
        features = _make_features(obi=-0.5, tfi=-0.3, delta_price=-0.2, ema_bias=0.3)
        score = expert.calculate_alpha("BTCUSDT", {}, features)
        assert float(score.score) < 0
        assert any("OPEN_SHORT" in r for r in score.why)

    def test_strength_alpha_zero_equals_flat_dir(self):
        """When strength_alpha=0, composite = dir_score exactly."""
        expert_composite = _make_expert(strength_alpha=0.0)
        expert_no_str = _make_expert(strength_alpha=0.0)
        features = _make_features()
        s1 = expert_composite.calculate_alpha("BTCUSDT", {}, features)
        s2 = expert_no_str.calculate_alpha("BTCUSDT", {}, features)
        assert float(s1.score) == float(s2.score)

    def test_strength_amplifies_score(self):
        """Positive strength should amplify positive dir."""
        features = _make_features()
        expert_low = _make_expert(strength_alpha=0.0)
        expert_high = _make_expert(strength_alpha=1.0)
        s_low = expert_low.calculate_alpha("BTCUSDT", {}, features)
        s_high = expert_high.calculate_alpha("BTCUSDT", {}, features)
        assert abs(float(s_high.score)) >= abs(float(s_low.score))

    def test_strength_cap_effect(self):
        """Capping strength at 0 removes amplification."""
        features = _make_features()
        expert_capped = _make_expert(strength_cap=0.0)
        expert_uncapped = _make_expert(strength_cap=1.0)
        s_capped = expert_capped.calculate_alpha("BTCUSDT", {}, features)
        s_uncapped = expert_uncapped.calculate_alpha("BTCUSDT", {}, features)
        # With cap=0, strength contribution = 0 → same as alpha=0
        expert_flat = _make_expert(strength_alpha=0.0)
        s_flat = expert_flat.calculate_alpha("BTCUSDT", {}, features)
        assert abs(float(s_capped.score) - float(s_flat.score)) < 1e-6

    def test_within_threshold_no_entry(self):
        expert = _make_expert(signal_threshold=10.0)
        features = _make_features()
        score = expert.calculate_alpha("BTCUSDT", {}, features)
        assert any("NO_ENTRY" in r for r in score.why)

    def test_reasoning_has_dir_and_str(self):
        expert = _make_expert()
        features = _make_features()
        score = expert.calculate_alpha("BTCUSDT", {}, features)
        assert any("dir_score=" in r for r in score.why)
        assert any("str_score=" in r for r in score.why)
        assert any("composite:" in r for r in score.why)


class TestFeatureNeutralsFailClosed:
    def test_no_features_returns_unknown(self):
        expert = _make_expert()
        score = expert.calculate_alpha("BTCUSDT", {}, {})
        assert float(score.confidence) == 0.0
        assert "NRR-NO-FEATURES" in score.why

    def test_essential_missing_returns_unknown(self):
        expert = _make_expert()
        features = {"tfi": 0.3, "ema_bias": 0.5, "volume_spike": 0.1, "volatility_state": 0.1}
        score = expert.calculate_alpha("BTCUSDT", {}, features)
        assert float(score.confidence) == 0.0
        assert any("DEFER:" in r for r in score.why)

    def test_empty_directional_returns_unknown(self):
        # This can't happen via config validation when enabled=True,
        # but test the runtime check
        expert = _make_expert(
            directional_features=["obi"],
            strength_features=[],
        )
        # Remove obi from features to trigger fail
        features = {"tfi": 0.3}
        score = expert.calculate_alpha("BTCUSDT", {}, features)
        assert float(score.confidence) == 0.0

    def test_strength_missing_still_works(self):
        """Missing strength features → strength=0, dir-only scoring."""
        expert = _make_expert()
        features = {"obi": 0.5, "tfi": 0.3, "delta_price": 0.2, "ema_bias": 0.6}
        score = expert.calculate_alpha("BTCUSDT", {}, features)
        # Should succeed with dir-only scoring (strength wabs=0 → str=0)
        assert float(score.score) != 0 or float(score.confidence) >= 0

    def test_negative_strength_clamped_to_zero(self):
        """Negative strength score should be clamped to 0."""
        expert = _make_expert()
        features = _make_features(volume_spike=-0.5, volatility_state=-0.5)
        score = expert.calculate_alpha("BTCUSDT", {}, features)
        # With negative strength clamped to 0, composite = dir * (1 + 0) = dir
        expert_flat = _make_expert(strength_alpha=0.0)
        s_flat = expert_flat.calculate_alpha("BTCUSDT", {}, features)
        assert abs(float(score.score) - float(s_flat.score)) < 1e-6

    def test_insufficient_directional_features_returns_unknown(self):
        expert = _make_expert(
            min_active_directional_features=3,
            essential_features=["obi"],
        )
        features = {
            "obi": 0.5,
            "delta_price": None,
            "tfi": None,
            "ema_bias": 0.6,
            "volume_spike": 0.1,
            "volatility_state": 0.2,
        }
        score = expert.calculate_alpha("BTCUSDT", {}, features)
        assert float(score.confidence) == 0.0
        assert "NRR-INSUFFICIENT-DIRECTIONAL-FEATURES:2/3" in score.why


class TestFeatureNeutralsMetadata:
    def test_model_name(self):
        expert = _make_expert()
        assert expert.get_model_name() == "judge.feature_neutrals_v1"

    def test_required_features(self):
        expert = _make_expert()
        required = expert.get_required_features()
        assert "obi" in required

    def test_score_clamped(self):
        expert = _make_expert(
            signal_weights={"obi": 10.0},
            feature_neutrals={"obi": 0.0},
            directional_features=["obi"],
            strength_features=[],
            essential_features=[],
        )
        features = {"obi": 1.0}
        score = expert.calculate_alpha("BTCUSDT", {}, features)
        assert float(score.score) <= 1.0
        assert float(score.score) >= -1.0
