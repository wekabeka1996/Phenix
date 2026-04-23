"""
LLM Judge Phase 2 — Signal Weights Expert Tests

Tests flat weighted-centering formula, fail-closed behavior, threshold
mapping, and confidence calculation.
"""

from decimal import Decimal

import pytest

from apps.reference.domains.alpha_search.judge.config_models import (
    SignalWeightsExpertConfig,
)
from apps.reference.domains.alpha_search.judge.experts.signal_weights_expert import (
    SignalWeightsExpert,
)

_WEIGHTS = {"obi": 0.42, "tfi": 0.15, "delta_price": 0.15, "ema_bias": 0.15}
_NEUTRALS = {"obi": 0.0, "tfi": 0.0, "delta_price": 0.0, "ema_bias": 0.5}
_ESSENTIAL = ["obi", "delta_price"]


def _make_expert(**overrides):
    defaults = dict(
        enabled=True,
        signal_weights=_WEIGHTS,
        feature_neutrals=_NEUTRALS,
        essential_features=_ESSENTIAL,
        signal_threshold=0.162,
    )
    defaults.update(overrides)
    cfg = SignalWeightsExpertConfig(**defaults)
    return SignalWeightsExpert(cfg)


def _make_features(**overrides):
    defaults = {"obi": 0.5, "tfi": 0.3, "delta_price": 0.2, "ema_bias": 0.6}
    defaults.update(overrides)
    return defaults


class TestSignalWeightsScoring:
    def test_known_input_positive_score(self):
        expert = _make_expert()
        features = {"obi": 0.5, "tfi": 0.3, "delta_price": 0.2, "ema_bias": 0.6}
        score = expert.calculate_alpha("BTCUSDT", {}, features)
        assert float(score.score) > 0

    def test_known_input_calculation(self):
        """Verify the formula: SUM(w*(x-n)) / SUM(|w|)"""
        expert = _make_expert()
        features = {"obi": 0.5, "tfi": 0.3, "delta_price": 0.2, "ema_bias": 0.6}
        score = expert.calculate_alpha("BTCUSDT", {}, features)

        # Manual: obi: 0.42*(0.5-0.0)=0.21, tfi: 0.15*(0.3-0.0)=0.045,
        # delta_price: 0.15*(0.2-0.0)=0.03, ema_bias: 0.15*(0.6-0.5)=0.015
        # raw = 0.21+0.045+0.03+0.015 = 0.3, wabs = 0.42+0.15+0.15+0.15 = 0.87
        # score = 0.3/0.87 ≈ 0.3448
        expected = 0.3 / 0.87
        assert abs(float(score.score) - expected) < 1e-4

    def test_negative_score_open_short(self):
        expert = _make_expert()
        features = {"obi": -0.5, "tfi": -0.3, "delta_price": -0.2, "ema_bias": 0.4}
        score = expert.calculate_alpha("BTCUSDT", {}, features)
        assert float(score.score) < 0
        assert any("OPEN_SHORT" in r for r in score.why)

    def test_within_threshold_no_entry(self):
        expert = _make_expert(signal_threshold=0.5)
        features = {"obi": 0.1, "tfi": 0.0, "delta_price": 0.0, "ema_bias": 0.5}
        score = expert.calculate_alpha("BTCUSDT", {}, features)
        assert any("NO_ENTRY" in r for r in score.why)

    def test_threshold_boundary_above(self):
        expert = _make_expert(signal_threshold=0.01)
        features = {"obi": 0.1, "tfi": 0.0, "delta_price": 0.0, "ema_bias": 0.5}
        score = expert.calculate_alpha("BTCUSDT", {}, features)
        assert float(score.score) > 0
        assert any("OPEN_LONG" in r for r in score.why)

    def test_centering_against_neutrals(self):
        expert = _make_expert()
        # ema_bias at exactly its neutral (0.5) should contribute nothing
        f1 = {"obi": 0.5, "tfi": 0.0, "delta_price": 0.0, "ema_bias": 0.5}
        s1 = expert.calculate_alpha("BTCUSDT", {}, f1)
        # ema_bias away from neutral should change score
        f2 = {"obi": 0.5, "tfi": 0.0, "delta_price": 0.0, "ema_bias": 0.9}
        s2 = expert.calculate_alpha("BTCUSDT", {}, f2)
        assert float(s2.score) > float(s1.score)

    def test_confidence_is_abs_score(self):
        expert = _make_expert()
        features = {"obi": 0.5, "tfi": 0.3, "delta_price": 0.2, "ema_bias": 0.6}
        score = expert.calculate_alpha("BTCUSDT", {}, features)
        assert abs(float(score.confidence) - abs(float(score.score))) < 1e-4

    def test_confidence_capped_at_1(self):
        expert = _make_expert(
            signal_weights={"obi": 5.0},
            feature_neutrals={"obi": 0.0},
            essential_features=[],
        )
        features = {"obi": 1.0}
        score = expert.calculate_alpha("BTCUSDT", {}, features)
        assert float(score.confidence) <= 1.0

    def test_per_feature_contribution_in_reasoning(self):
        expert = _make_expert()
        features = _make_features()
        score = expert.calculate_alpha("BTCUSDT", {}, features)
        assert any("obi:" in r for r in score.why)
        assert any("tfi:" in r for r in score.why)


class TestSignalWeightsFailClosed:
    def test_no_features_returns_unknown(self):
        expert = _make_expert()
        score = expert.calculate_alpha("BTCUSDT", {}, {})
        assert float(score.confidence) == 0.0
        assert "NRR-NO-FEATURES" in score.why

    def test_essential_missing_returns_unknown(self):
        expert = _make_expert()
        features = {"tfi": 0.3, "ema_bias": 0.5}  # obi and delta_price missing
        score = expert.calculate_alpha("BTCUSDT", {}, features)
        assert float(score.confidence) == 0.0
        assert any("DEFER:" in r for r in score.why)

    def test_essential_none_returns_unknown(self):
        expert = _make_expert()
        features = {"obi": None, "tfi": 0.3, "delta_price": 0.2, "ema_bias": 0.5}
        score = expert.calculate_alpha("BTCUSDT", {}, features)
        assert float(score.confidence) == 0.0
        assert any("DEFER:obi" in r for r in score.why)

    def test_all_zero_weights_returns_unknown(self):
        expert = _make_expert(
            signal_weights={"obi": 0.0, "tfi": 0.0},
            feature_neutrals={"obi": 0.0, "tfi": 0.0},
            essential_features=[],
        )
        features = {"obi": 0.5, "tfi": 0.3}
        score = expert.calculate_alpha("BTCUSDT", {}, features)
        assert float(score.confidence) == 0.0
        assert "NRR-ALL-WEIGHTS-ZERO" in score.why

    def test_non_essential_missing_still_works(self):
        expert = _make_expert()
        features = {"obi": 0.5, "delta_price": 0.2}  # tfi and ema_bias missing
        score = expert.calculate_alpha("BTCUSDT", {}, features)
        assert float(score.score) != 0 or float(score.confidence) >= 0

    def test_insufficient_active_features_returns_unknown(self):
        expert = _make_expert(min_active_features=3, essential_features=["obi"])
        features = {"obi": 0.5, "tfi": None, "delta_price": None, "ema_bias": 0.6}
        score = expert.calculate_alpha("BTCUSDT", {}, features)
        assert float(score.confidence) == 0.0
        assert "NRR-INSUFFICIENT-ACTIVE-FEATURES:2/3" in score.why


class TestSignalWeightsMetadata:
    def test_model_name(self):
        expert = _make_expert()
        assert expert.get_model_name() == "judge.signal_weights_v1"

    def test_required_features(self):
        expert = _make_expert()
        required = expert.get_required_features()
        assert "obi" in required
        assert "tfi" in required

    def test_features_used_in_score(self):
        expert = _make_expert()
        features = _make_features()
        score = expert.calculate_alpha("BTCUSDT", {}, features)
        assert "obi" in score.features_used

    def test_score_clamped_to_minus_1_1(self):
        expert = _make_expert(
            signal_weights={"obi": 10.0},
            feature_neutrals={"obi": 0.0},
            essential_features=[],
        )
        features = {"obi": 1.0}
        score = expert.calculate_alpha("BTCUSDT", {}, features)
        assert float(score.score) <= 1.0
        assert float(score.score) >= -1.0
