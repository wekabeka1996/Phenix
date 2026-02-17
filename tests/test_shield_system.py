"""
Unit Tests for Shield System — Aurora Phase 9, Phase 3.

Tests:
- BaseShield / ShieldResult
- ShieldCascade (multiplicative chaining, early veto, error handling)
- ContextShield (regime mapping)
- MemoryShield (drawdown + loss decay)
- DangerZoneShield (circuit breaker)
- Integration tests
"""

import math
import pytest

from apps.reference.domains.decision_making.shields.base import (
    BaseShield,
    ShieldCascade,
    ShieldResult,
)
from apps.reference.domains.decision_making.shields.null_shield import NullShield
from apps.reference.domains.decision_making.shields.context_shield import ContextShield
from apps.reference.domains.decision_making.shields.memory_shield import MemoryShield
from apps.reference.domains.decision_making.shields.danger_zone import DangerZoneShield


# =============================================================================
# ShieldResult
# =============================================================================

class TestShieldResult:
    def test_defaults(self):
        r = ShieldResult()
        assert r.multiplier == 1.0
        assert r.reasons == []
        assert r.shield_name == ""

    def test_with_values(self):
        r = ShieldResult(multiplier=0.5, reasons=["test"], shield_name="ctx")
        assert r.multiplier == 0.5
        assert r.reasons == ["test"]


# =============================================================================
# NullShield
# =============================================================================

class TestNullShieldPhase3:
    def test_always_passes(self):
        shield = NullShield()
        mult, reasons = shield("BTC", {}, 0.8, 0.64)
        assert mult == 1.0
        assert reasons == []


# =============================================================================
# ContextShield
# =============================================================================

class TestContextShield:
    def test_trending_passes(self):
        shield = ContextShield(regime_multipliers={"trending": 1.0, "crisis": 0.2})
        mult, reasons = shield("BTC", {"regime": "trending"}, 0.5, 0.25)
        assert mult == 1.0
        assert "trending" in reasons[0]

    def test_crisis_attenuates(self):
        shield = ContextShield(regime_multipliers={"trending": 1.0, "crisis": 0.2})
        mult, reasons = shield("BTC", {"regime": "crisis"}, 0.5, 0.25)
        assert mult == 0.2
        assert "crisis" in reasons[0]

    def test_unknown_regime_uses_default(self):
        shield = ContextShield(
            regime_multipliers={"trending": 1.0},
            default_multiplier=0.8,
        )
        mult, reasons = shield("BTC", {"regime": "exotic"}, 0.5, 0.25)
        assert mult == 0.8
        assert "default" in reasons[0]

    def test_no_regime_uses_no_regime_mult(self):
        shield = ContextShield(no_regime_multiplier=0.3)
        mult, reasons = shield("BTC", {}, 0.5, 0.25)
        assert mult == 0.3
        assert "no_regime" in reasons[0]

    def test_none_regime_explicit(self):
        shield = ContextShield(no_regime_multiplier=0.4)
        mult, reasons = shield("BTC", {"regime": None}, 0.5, 0.25)
        assert mult == 0.4


# =============================================================================
# MemoryShield (Doctrine v2.6 — state-familiarity)
# =============================================================================

_FULL_FEATURES = {
    "regime": "TREND_UP",
    "volatility": {"atr_pct": 0.003},
    "pillar_operator": 0.5,
    "pillar_strategist": 0.6,
    "bar_close_ts": 1_700_000_000,
}

_BASE_TS = 1_700_000_000


class TestMemoryShield:
    def test_no_data_returns_unknown(self):
        """Empty features → MISSING_FEATURES → unknown multiplier."""
        shield = MemoryShield()
        mult, reasons = shield("BTC", {}, 0.5, 0.25)
        assert mult == pytest.approx(0.6)  # unknown_multiplier default
        assert "MEMORY" in reasons[0]

    def test_first_visit_unknown(self):
        """First evaluation with full features → UNKNOWN (ev ≈ 0)."""
        shield = MemoryShield()
        result = shield.evaluate("BTC", _FULL_FEATURES, 0.5, 0.25)
        assert result.multiplier == pytest.approx(0.6)
        assert "UNKNOWN" in result.reasons[0]

    def test_visits_accumulate_to_exploring(self):
        """After enough visits, state transitions UNKNOWN → EXPLORING."""
        shield = MemoryShield(unknown_threshold=3, exploring_threshold=8)
        for i in range(4):
            shield.record_visit("BTC", dict(_FULL_FEATURES, bar_close_ts=_BASE_TS + i))
        result = shield.evaluate("BTC", dict(_FULL_FEATURES, bar_close_ts=_BASE_TS + 4), 0.5, 0.25)
        assert result.multiplier == pytest.approx(0.8)
        assert "EXPLORING" in result.reasons[0]

    def test_visits_accumulate_to_known(self):
        """After many visits, state transitions to KNOWN."""
        shield = MemoryShield(unknown_threshold=2, exploring_threshold=5)
        for i in range(6):
            shield.record_visit("BTC", dict(_FULL_FEATURES, bar_close_ts=_BASE_TS + i))
        result = shield.evaluate("BTC", dict(_FULL_FEATURES, bar_close_ts=_BASE_TS + 6), 0.5, 0.25)
        assert result.multiplier == pytest.approx(1.0)
        assert "KNOWN" in result.reasons[0]

    def test_different_regimes_separate(self):
        """Different regime → different state hash → independent counters."""
        shield = MemoryShield(unknown_threshold=2, exploring_threshold=5)
        up = dict(_FULL_FEATURES, regime="TREND_UP")
        down = dict(_FULL_FEATURES, regime="TREND_DOWN")
        for i in range(3):
            shield.record_visit("BTC", dict(up, bar_close_ts=_BASE_TS + i))
        # UP should be exploring now
        r_up = shield.evaluate("BTC", dict(up, bar_close_ts=_BASE_TS + 3), 0.5, 0.25)
        assert r_up.multiplier == pytest.approx(0.8)
        # DOWN still unknown
        r_down = shield.evaluate("BTC", dict(down, bar_close_ts=_BASE_TS + 4), 0.5, 0.25)
        assert r_down.multiplier == pytest.approx(0.6)

    def test_multiplier_clamped_0_1(self):
        """Multiplier always in [0, 1]."""
        shield = MemoryShield()
        result = shield.evaluate("BTC", _FULL_FEATURES, 0.5, 0.25)
        assert 0.0 <= result.multiplier <= 1.0


# =============================================================================
# DangerZoneShield
# =============================================================================

class TestDangerZoneShield:
    def test_normal_passes(self):
        shield = DangerZoneShield()
        mult, reasons = shield("BTC", {}, 0.5, 0.25)
        assert mult == 1.0
        assert reasons == []

    def test_high_vol_vetoes(self):
        shield = DangerZoneShield(vol_threshold=0.9)
        mult, reasons = shield(
            "BTC", {"volatility_state": 0.95}, 0.5, 0.25,
        )
        assert mult == 0.0
        assert "DANGER_ZONE:vol" in reasons[0]

    def test_high_spread_vetoes(self):
        shield = DangerZoneShield(spread_threshold=30.0)
        mult, reasons = shield(
            "BTC", {"spread_bps": 50.0}, 0.5, 0.25,
        )
        assert mult == 0.0
        assert "DANGER_ZONE:spread" in reasons[0]

    def test_extreme_motion_vetoes(self):
        shield = DangerZoneShield(motion_threshold=3.0)
        mult, reasons = shield(
            "BTC", {"price_motion_norm": 4.5}, 0.5, 0.25,
        )
        assert mult == 0.0
        assert "DANGER_ZONE:motion" in reasons[0]

    def test_negative_motion_also_vetoes(self):
        shield = DangerZoneShield(motion_threshold=3.0)
        mult, reasons = shield(
            "BTC", {"price_motion_norm": -4.0}, 0.5, 0.25,
        )
        assert mult == 0.0

    def test_below_threshold_passes(self):
        shield = DangerZoneShield(vol_threshold=0.95)
        mult, reasons = shield(
            "BTC", {"volatility_state": 0.8}, 0.5, 0.25,
        )
        assert mult == 1.0

    def test_priority_vol_over_spread(self):
        """Vol check runs first and wins."""
        shield = DangerZoneShield(vol_threshold=0.9, spread_threshold=30.0)
        mult, reasons = shield(
            "BTC",
            {"volatility_state": 0.95, "spread_bps": 50.0},
            0.5, 0.25,
        )
        assert mult == 0.0
        assert "vol" in reasons[0]  # Vol triggered first


# =============================================================================
# ShieldCascade
# =============================================================================

class TestShieldCascade:
    def test_empty_cascade_passes(self):
        cascade = ShieldCascade([])
        result = cascade.evaluate("BTC", {}, 0.5, 0.25)
        assert result.multiplier == 1.0

    def test_single_shield(self):
        cascade = ShieldCascade([NullShield()])
        mult, reasons = cascade("BTC", {}, 0.5, 0.25)
        assert mult == 1.0

    def test_multiplicative_chaining(self):
        """Two shields: 0.7 × 0.6(UNKNOWN) = 0.42"""
        ctx = ContextShield(regime_multipliers={"ranging": 0.7})
        mem = MemoryShield()  # first visit → UNKNOWN → 0.6
        cascade = ShieldCascade([ctx, mem])
        mult, reasons = cascade(
            "BTC",
            {
                "regime": "ranging",
                "volatility": {"atr_pct": 0.003},
                "pillar_operator": 0.5,
                "pillar_strategist": 0.6,
                "bar_close_ts": 1_700_000_000,
            },
            0.5, 0.25,
        )
        # context: 0.7, memory: UNKNOWN → 0.6
        # cascade: 0.7 * 0.6 = 0.42
        assert mult == pytest.approx(0.42, abs=1e-3)

    def test_veto_short_circuits(self):
        """DangerZone veto stops cascade early."""
        dz = DangerZoneShield(vol_threshold=0.9)
        ctx = ContextShield(regime_multipliers={"trending": 1.0})
        cascade = ShieldCascade([dz, ctx])
        mult, reasons = cascade(
            "BTC",
            {"volatility_state": 0.99, "regime": "trending"},
            0.5, 0.25,
        )
        assert mult == 0.0
        assert any("VETOED_BY" in r for r in reasons)

    def test_error_handling_fail_open(self):
        """Shield that raises → fail-open, continue cascade."""
        class BrokenShield(BaseShield):
            @property
            def name(self):
                return "BrokenShield"
            def evaluate(self, symbol, features, pillar_sum, raw_exposure):
                raise RuntimeError("oops")

        cascade = ShieldCascade([BrokenShield(), NullShield()])
        result = cascade.evaluate("BTC", {}, 0.5, 0.25)
        assert result.multiplier == 1.0  # Error → pass-through
        assert any("SHIELD_ERROR" in r for r in result.reasons)

    def test_repr(self):
        cascade = ShieldCascade([
            DangerZoneShield(),
            ContextShield(),
            MemoryShield(),  # Doctrine v2.6: keyword-only args
        ])
        r = repr(cascade)
        assert "DangerZoneShield" in r
        assert "ContextShield" in r
        assert "MEMORY" in r


# =============================================================================
# BaseShield __call__ error handling
# =============================================================================

class TestBaseShieldErrorHandling:
    def test_call_catches_exception(self):
        class FailShield(BaseShield):
            @property
            def name(self):
                return "FailShield"
            def evaluate(self, symbol, features, pillar_sum, raw_exposure):
                raise ValueError("boom")

        shield = FailShield()
        mult, reasons = shield("BTC", {}, 0.5, 0.25)
        assert mult == 1.0  # Fail-open
        assert any("SHIELD_ERROR" in r for r in reasons)

    def test_call_clamps_multiplier(self):
        class OverShield(BaseShield):
            @property
            def name(self):
                return "OverShield"
            def evaluate(self, symbol, features, pillar_sum, raw_exposure):
                return ShieldResult(multiplier=2.0, reasons=["over"])

        mult, reasons = OverShield()("BTC", {}, 0.5, 0.25)
        assert mult == 1.0  # Clamped to max


# =============================================================================
# Integration: Full cascade with QuadraticScoringKernel
# =============================================================================

class TestFullIntegration:
    def test_cascade_with_quadratic_kernel(self):
        """End-to-end: pillars → quadratic → shields → final score."""
        import decimal
        from apps.reference.domains.decision_making.quadratic_scoring_kernel import (
            QuadraticScoringKernel,
        )

        cascade = ShieldCascade([
            DangerZoneShield(vol_threshold=0.95),
            ContextShield(regime_multipliers={"trending": 0.9}),
            MemoryShield(),  # Doctrine v2.6: first visit → UNKNOWN → 0.6
        ])

        result = QuadraticScoringKernel.compute(
            symbol="BTCUSDT",
            features={
                "pillar_sum": 0.8,
                "regime": "trending",
                "volatility": {"atr_pct": 0.003},
                "pillar_operator": 0.5,
                "pillar_strategist": 0.6,
                "bar_close_ts": 1_700_000_000,
            },
            warmup_readiness={},
            price=decimal.Decimal("50000"),
            signal_weights={},
            feature_neutrals={},
            essential_features=[],
            base_threshold=decimal.Decimal("0.1"),
            regime_name="trending",
            regime_thresholds={"trending": 1.0},
            side_bias_state=None,
            direction_strength_cfg={},
            delta_price_cap_pct=decimal.Decimal("0.005"),
            neutral_threshold=decimal.Decimal("0.05"),
            current_side="",
            shield_fn=cascade,
        )

        # raw: sign(0.8) × 0.8² = 0.64
        # shields: DZ passes, Context: 0.9, Memory: UNKNOWN → 0.6
        # final: 0.64 × 0.9 × 0.6 = 0.3456
        assert float(result.score) == pytest.approx(0.64 * 0.9 * 0.6, abs=0.01)
        assert result.psi_vector["scoring_engine"] == "quadratic_v1"
        assert result.side == "buy"

    def test_danger_zone_vetoes_everything(self):
        """DangerZone veto → score=0, neutral."""
        import decimal
        from apps.reference.domains.decision_making.quadratic_scoring_kernel import (
            QuadraticScoringKernel,
        )

        cascade = ShieldCascade([
            DangerZoneShield(vol_threshold=0.9),
        ])

        result = QuadraticScoringKernel.compute(
            symbol="BTCUSDT",
            features={
                "pillar_sum": 1.0,  # Max conviction
                "volatility_state": 0.99,  # DANGER
            },
            warmup_readiness={},
            price=decimal.Decimal("50000"),
            signal_weights={},
            feature_neutrals={},
            essential_features=[],
            base_threshold=decimal.Decimal("0.1"),
            regime_name="trending",
            regime_thresholds={"trending": 1.0},
            side_bias_state=None,
            direction_strength_cfg={},
            delta_price_cap_pct=decimal.Decimal("0.005"),
            neutral_threshold=decimal.Decimal("0.05"),
            current_side="",
            shield_fn=cascade,
        )

        assert float(result.score) == 0.0
        assert result.side == ""  # Neutral despite max conviction
