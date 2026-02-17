"""
Unit Tests for QuadraticScoringKernel — Aurora Phase 9.

Tests:
- Quadratic transform: sign(Σ)×Σ²
- Shield integration (NullShield, custom shields)
- Threshold / side bias / hysteresis (same contract as aurora kernel)
- Helper functions
- Edge cases (NaN, Inf, missing pillar_sum)
"""

import decimal
import math
import pytest

from apps.reference.domains.decision_making.quadratic_scoring_kernel import (
    QuadraticScoringKernel,
    QuadraticContext,
    _resolve_regime_factor,
    _compute_side_bias_mult,
    _determine_side,
    _null_shield,
)
from apps.reference.domains.decision_making.aurora_scoring_kernel import (
    ScoringResult,
    SideBiasState,
)
from apps.reference.domains.decision_making.shields.null_shield import NullShield


# =============================================================================
# Default call args factory
# =============================================================================

def _base_kwargs(**overrides):
    """Provide sane defaults for QuadraticScoringKernel.compute()."""
    defaults = dict(
        symbol="BTCUSDT",
        features={"pillar_sum": 0.5},
        warmup_readiness={},
        price=decimal.Decimal("50000"),
        signal_weights={},
        feature_neutrals={},
        essential_features=[],
        base_threshold=decimal.Decimal("0.1"),
        regime_name="trending",
        regime_thresholds={"trending": 1.0, "DEFAULT": 1.0},
        side_bias_state=None,
        direction_strength_cfg={},
        delta_price_cap_pct=decimal.Decimal("0.005"),
        neutral_threshold=decimal.Decimal("0.05"),
        current_side="",
    )
    defaults.update(overrides)
    return defaults


# =============================================================================
# Quadratic Transform
# =============================================================================

class TestQuadraticTransform:
    def test_positive_pillar(self):
        r = QuadraticScoringKernel.compute(**_base_kwargs(
            features={"pillar_sum": 0.5}
        ))
        # sign(0.5) × 0.5² = +0.25
        assert float(r.score) == pytest.approx(0.25, abs=1e-6)
        assert r.side == "buy"  # 0.25 > 0.1 threshold

    def test_negative_pillar(self):
        r = QuadraticScoringKernel.compute(**_base_kwargs(
            features={"pillar_sum": -0.5}
        ))
        # sign(-0.5) × 0.5² = -0.25
        assert float(r.score) == pytest.approx(-0.25, abs=1e-6)
        assert r.side == "sell"

    def test_zero_pillar(self):
        r = QuadraticScoringKernel.compute(**_base_kwargs(
            features={"pillar_sum": 0.0}
        ))
        assert float(r.score) == 0.0
        assert r.side == ""  # Neutral

    def test_full_conviction(self):
        r = QuadraticScoringKernel.compute(**_base_kwargs(
            features={"pillar_sum": 1.0}
        ))
        # sign(1) × 1² = 1.0
        assert float(r.score) == pytest.approx(1.0, abs=1e-6)

    def test_weak_signal_penalized(self):
        r = QuadraticScoringKernel.compute(**_base_kwargs(
            features={"pillar_sum": 0.2}
        ))
        # sign(0.2) × 0.2² = 0.04 (well below threshold 0.1)
        assert float(r.score) == pytest.approx(0.04, abs=1e-6)
        assert r.side == ""  # Neutral — too weak

    def test_quadratic_property_symmetry(self):
        pos = QuadraticScoringKernel.compute(**_base_kwargs(
            features={"pillar_sum": 0.7}
        ))
        neg = QuadraticScoringKernel.compute(**_base_kwargs(
            features={"pillar_sum": -0.7}
        ))
        assert float(pos.score) == pytest.approx(-float(neg.score), abs=1e-8)


# =============================================================================
# Missing / Invalid pillar_sum
# =============================================================================

class TestPillarSumEdgeCases:
    def test_missing_pillar_sum_defers(self):
        r = QuadraticScoringKernel.compute(**_base_kwargs(
            features={}
        ))
        assert r.deferred is True
        assert r.defer_reason == "PILLAR_SUM_MISSING"

    def test_none_pillar_sum_defers(self):
        r = QuadraticScoringKernel.compute(**_base_kwargs(
            features={"pillar_sum": None}
        ))
        assert r.deferred is True
        assert r.defer_reason == "PILLAR_SUM_MISSING"

    def test_nan_pillar_sum_defers(self):
        r = QuadraticScoringKernel.compute(**_base_kwargs(
            features={"pillar_sum": float("nan")}
        ))
        assert r.deferred is True
        assert r.defer_reason == "PILLAR_SUM_NAN_INF"

    def test_inf_pillar_sum_defers(self):
        r = QuadraticScoringKernel.compute(**_base_kwargs(
            features={"pillar_sum": float("inf")}
        ))
        assert r.deferred is True
        assert r.defer_reason == "PILLAR_SUM_NAN_INF"

    def test_string_pillar_sum_defers(self):
        r = QuadraticScoringKernel.compute(**_base_kwargs(
            features={"pillar_sum": "not_a_number"}
        ))
        assert r.deferred is True
        assert r.defer_reason == "PILLAR_SUM_INVALID"


# =============================================================================
# Shield Integration
# =============================================================================

class TestShieldIntegration:
    def test_null_shield_passes_through(self):
        r = QuadraticScoringKernel.compute(**_base_kwargs(
            features={"pillar_sum": 0.8},
            shield_fn=NullShield(),
        ))
        # NullShield → multiplier = 1.0
        # sign(0.8) × 0.8² = 0.64
        assert float(r.score) == pytest.approx(0.64, abs=1e-6)
        assert r.psi_vector["shield_multiplier"] == 1.0

    def test_custom_shield_attenuates(self):
        def half_shield(sym, feat, psum, raw):
            return 0.5, ["testing_half_attenuation"]

        r = QuadraticScoringKernel.compute(**_base_kwargs(
            features={"pillar_sum": 0.8},
            shield_fn=half_shield,
        ))
        # 0.64 × 0.5 = 0.32
        assert float(r.score) == pytest.approx(0.32, abs=1e-6)
        assert r.psi_vector["shield_multiplier"] == 0.5
        assert "testing_half_attenuation" in r.psi_vector["shield_reasons"]

    def test_shield_veto(self):
        def veto_shield(sym, feat, psum, raw):
            return 0.0, ["danger_zone_veto"]

        r = QuadraticScoringKernel.compute(**_base_kwargs(
            features={"pillar_sum": 0.9},
            shield_fn=veto_shield,
        ))
        assert float(r.score) == 0.0
        assert r.side == ""  # Vetoed → neutral

    def test_shield_multiplier_clamped(self):
        def bad_shield(sym, feat, psum, raw):
            return 1.5, ["over_unity"]  # Should be clamped to 1.0

        r = QuadraticScoringKernel.compute(**_base_kwargs(
            features={"pillar_sum": 0.5},
            shield_fn=bad_shield,
        ))
        assert r.psi_vector["shield_multiplier"] == 1.0  # Clamped

    def test_null_shield_function(self):
        mult, reasons = _null_shield("BTCUSDT", {}, 0.5, 0.25)
        assert mult == 1.0
        assert reasons == []


# =============================================================================
# Explainability (psi_vector)
# =============================================================================

class TestExplainability:
    def test_psi_vector_has_quadratic_fields(self):
        r = QuadraticScoringKernel.compute(**_base_kwargs(
            features={"pillar_sum": 0.6},
            pillar_contribs={"tactician": 0.15, "operator": 0.25, "strategist": 0.2},
        ))
        psi = r.psi_vector
        assert psi["scoring_engine"] == "quadratic_v1"
        assert psi["pillar_sum"] == 0.6
        assert psi["raw_exposure"] == pytest.approx(0.36, abs=1e-6)
        assert "tactician" in psi["pillar_contribs"]
        assert "operator" in psi["pillar_contribs"]


# =============================================================================
# Regime Thresholds
# =============================================================================

class TestRegimeThresholds:
    def test_known_regime(self):
        factor = _resolve_regime_factor("trending", {"trending": 0.8, "DEFAULT": 1.0})
        assert factor == decimal.Decimal("0.8")

    def test_unknown_regime_falls_back_to_default(self):
        factor = _resolve_regime_factor("crisis", {"trending": 0.8, "DEFAULT": 1.0})
        assert factor == decimal.Decimal("1.0")

    def test_no_default_returns_none(self):
        factor = _resolve_regime_factor("crisis", {"trending": 0.8})
        assert factor is None

    def test_invalid_factor_returns_none(self):
        factor = _resolve_regime_factor("trending", {"trending": -1.0})
        assert factor is None

    def test_missing_regime_defers(self):
        r = QuadraticScoringKernel.compute(**_base_kwargs(
            regime_name="unknown",
            regime_thresholds={"trending": 1.0},  # No DEFAULT
        ))
        assert r.deferred is True
        assert "MISSING_REGIME_THRESHOLD" in r.defer_reason


# =============================================================================
# Side Bias
# =============================================================================

class TestSideBias:
    def test_no_bias(self):
        buy, sell = _compute_side_bias_mult(None)
        assert buy == decimal.Decimal("1.0")
        assert sell == decimal.Decimal("1.0")

    def test_below_min_intents(self):
        state = SideBiasState(buy_count=5, sell_count=5, min_intents=20)
        buy, sell = _compute_side_bias_mult(state)
        assert buy == decimal.Decimal("1.0")  # Not enough data

    def test_sell_heavy_penalizes_sell(self):
        state = SideBiasState(buy_count=5, sell_count=25, min_intents=18)
        buy, sell = _compute_side_bias_mult(state)
        assert sell > decimal.Decimal("1.0")  # Sell penalty
        assert buy == decimal.Decimal("1.0")  # Buy unchanged


# =============================================================================
# Hysteresis Side Determination
# =============================================================================

class TestHysteresis:
    def test_enter_buy(self):
        side, _ = _determine_side(
            decimal.Decimal("0.2"),
            decimal.Decimal("0.1"),
            decimal.Decimal("0.1"),
            decimal.Decimal("0.05"),
            "",
        )
        assert side == "buy"

    def test_enter_sell(self):
        side, _ = _determine_side(
            decimal.Decimal("-0.2"),
            decimal.Decimal("0.1"),
            decimal.Decimal("0.1"),
            decimal.Decimal("0.05"),
            "",
        )
        assert side == "sell"

    def test_neutral_zone(self):
        side, _ = _determine_side(
            decimal.Decimal("0.05"),
            decimal.Decimal("0.1"),
            decimal.Decimal("0.1"),
            decimal.Decimal("0.05"),
            "",
        )
        assert side == ""

    def test_hold_buy(self):
        side, _ = _determine_side(
            decimal.Decimal("0.06"),
            decimal.Decimal("0.1"),
            decimal.Decimal("0.1"),
            decimal.Decimal("0.05"),
            "buy",
        )
        assert side == "buy"  # Above neutral threshold, hold

    def test_exit_buy(self):
        side, _ = _determine_side(
            decimal.Decimal("0.03"),
            decimal.Decimal("0.1"),
            decimal.Decimal("0.1"),
            decimal.Decimal("0.05"),
            "buy",
        )
        assert side == ""  # Below neutral threshold, exit

    def test_flip_buy_to_sell(self):
        side, _ = _determine_side(
            decimal.Decimal("-0.15"),
            decimal.Decimal("0.1"),
            decimal.Decimal("0.1"),
            decimal.Decimal("0.05"),
            "buy",
        )
        assert side == "sell"  # Strong opposite → flip


# =============================================================================
# NullShield Class
# =============================================================================

class TestNullShield:
    def test_callable(self):
        shield = NullShield()
        mult, reasons = shield("BTCUSDT", {}, 0.5, 0.25)
        assert mult == 1.0
        assert reasons == []

    def test_repr(self):
        assert repr(NullShield()) == "NullShield()"
