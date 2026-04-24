"""Tests for aurora_policy.py — Package 2 policy layer.

Tests policy interpretation in isolation: thresholds, hysteresis, side-bias.
No math transforms, no execution, no handler state.
"""
from __future__ import annotations

import decimal
import pytest

from apps.reference.shared.decision_primitives.aurora_policy import (
    AuroraPolicyInput,
    AuroraPolicyDecision,
    SideBiasState,
    apply_aurora_policy,
    resolve_regime_factor,
    compute_side_bias_multipliers,
    determine_side,
)


# ── resolve_regime_factor ───────────────────────────────────────────


class TestResolveRegimeFactor:
    def test_named_regime(self):
        f = resolve_regime_factor(
            "TREND_UP", {"TREND_UP": 0.8, "DEFAULT": 1.0})
        assert f == decimal.Decimal("0.8")

    def test_default_fallback(self):
        f = resolve_regime_factor("UNKNOWN", {"DEFAULT": 1.0})
        assert f == decimal.Decimal("1.0")

    def test_missing_both(self):
        assert resolve_regime_factor("UNKNOWN", {}) is None

    def test_none_regime_uses_default(self):
        f = resolve_regime_factor(None, {"DEFAULT": 1.2})
        assert f == decimal.Decimal("1.2")

    def test_negative_factor_returns_none(self):
        assert resolve_regime_factor("BAD", {"BAD": -1.0}) is None

    def test_zero_factor_returns_none(self):
        assert resolve_regime_factor("ZERO", {"ZERO": 0}) is None

    def test_inf_factor_returns_none(self):
        assert resolve_regime_factor("INF", {"INF": float("inf")}) is None


# ── compute_side_bias_multipliers ───────────────────────────────────


class TestSideBiasMultipliers:
    def test_none_state(self):
        buy, sell = compute_side_bias_multipliers(None)
        assert buy == decimal.Decimal("1.0")
        assert sell == decimal.Decimal("1.0")

    def test_below_min_intents(self):
        state = SideBiasState(buy_count=5, sell_count=5, min_intents=18)
        buy, sell = compute_side_bias_multipliers(state)
        assert buy == decimal.Decimal("1.0")
        assert sell == decimal.Decimal("1.0")

    def test_sell_heavy_widens_sell(self):
        state = SideBiasState(
            buy_count=5, sell_count=15, min_intents=18,
            target_ratio=0.72, penalty_factor=0.25,
        )
        buy, sell = compute_side_bias_multipliers(state)
        assert buy == decimal.Decimal("1.0")
        assert sell > decimal.Decimal("1.0")

    def test_buy_heavy_widens_buy(self):
        state = SideBiasState(
            buy_count=15, sell_count=5, min_intents=18,
            target_ratio=0.72, penalty_factor=0.25,
        )
        buy, sell = compute_side_bias_multipliers(state)
        assert buy > decimal.Decimal("1.0")
        assert sell == decimal.Decimal("1.0")

    def test_balanced_no_penalty(self):
        state = SideBiasState(
            buy_count=10, sell_count=10, min_intents=18,
            target_ratio=0.72, penalty_factor=0.25,
        )
        buy, sell = compute_side_bias_multipliers(state)
        assert buy == decimal.Decimal("1.0")
        assert sell == decimal.Decimal("1.0")


# ── determine_side (3-zone hysteresis) ──────────────────────────────


class TestDetermineSide:
    D = decimal.Decimal

    def test_enter_buy(self):
        side, why = determine_side(self.D("0.05"), self.D(
            "0.02"), self.D("0.02"), self.D("0.01"), "")
        assert side == "buy"
        assert "enter:buy" in why

    def test_enter_sell(self):
        side, why = determine_side(
            self.D("-0.05"), self.D("0.02"), self.D("0.02"), self.D("0.01"), "")
        assert side == "sell"
        assert "enter:sell" in why

    def test_neutral_no_side(self):
        side, why = determine_side(self.D("0.005"), self.D(
            "0.02"), self.D("0.02"), self.D("0.01"), "")
        assert side == ""
        assert "neutral" in why

    def test_hold_buy(self):
        side, why = determine_side(self.D("0.015"), self.D(
            "0.02"), self.D("0.02"), self.D("0.01"), "buy")
        assert side == "buy"
        assert "hold:buy" in why

    def test_exit_buy_to_neutral(self):
        side, why = determine_side(self.D("0.005"), self.D(
            "0.02"), self.D("0.02"), self.D("0.01"), "buy")
        assert side == ""
        assert "exit:buy->neutral" in why

    def test_flip_buy_to_sell(self):
        side, why = determine_side(
            self.D("-0.03"), self.D("0.02"), self.D("0.02"), self.D("0.01"), "buy")
        assert side == "sell"
        assert "flip:buy->sell" in why

    def test_hold_sell(self):
        side, why = determine_side(
            self.D("-0.015"), self.D("0.02"), self.D("0.02"), self.D("0.01"), "sell")
        assert side == "sell"
        assert "hold:sell" in why

    def test_exit_sell_to_neutral(self):
        side, why = determine_side(
            self.D("-0.005"), self.D("0.02"), self.D("0.02"), self.D("0.01"), "sell")
        assert side == ""
        assert "exit:sell->neutral" in why

    def test_flip_sell_to_buy(self):
        side, why = determine_side(self.D("0.03"), self.D(
            "0.02"), self.D("0.02"), self.D("0.01"), "sell")
        assert side == "buy"
        assert "flip:sell->buy" in why


# ── apply_aurora_policy (integration) ───────────────────────────────


class TestApplyAuroraPolicy:
    D = decimal.Decimal

    def _make_input(self, decision_score=0.16, **kwargs):
        defaults = dict(
            decision_score=decision_score,
            sizing_score=decision_score,
            base_threshold=self.D("0.02"),
            regime_name="DEFAULT",
            regime_thresholds={"DEFAULT": 1.0},
            side_bias_state=None,
            neutral_threshold=self.D("0.01"),
            current_side="",
        )
        defaults.update(kwargs)
        return AuroraPolicyInput(**defaults)

    def test_buy_decision(self):
        out = apply_aurora_policy(self._make_input(0.16))
        assert out.side == "buy"
        assert out.deferred is False
        assert out.thr_buy == self.D("0.02")

    def test_sell_decision(self):
        out = apply_aurora_policy(self._make_input(-0.16))
        assert out.side == "sell"
        assert out.deferred is False

    def test_neutral_decision(self):
        out = apply_aurora_policy(self._make_input(0.005))
        assert out.side == ""

    def test_regime_widens_threshold(self):
        out = apply_aurora_policy(self._make_input(
            0.03,
            regime_name="TREND_UP",
            regime_thresholds={"TREND_UP": 2.0, "DEFAULT": 1.0},
        ))
        assert out.thr_buy == self.D("0.04")  # 0.02 * 2.0
        assert out.side == ""  # 0.03 < 0.04

    def test_missing_regime_defers(self):
        out = apply_aurora_policy(self._make_input(
            0.16, regime_name="MISSING", regime_thresholds={},
        ))
        assert out.deferred is True
        assert "MISSING_REGIME_THRESHOLD" in (out.defer_reason or "")

    def test_side_bias_widens_sell(self):
        bias = SideBiasState(
            buy_count=3, sell_count=17, min_intents=18,
            target_ratio=0.72, penalty_factor=0.25,
        )
        out = apply_aurora_policy(self._make_input(
            -0.025, side_bias_state=bias,
        ))
        assert out.sell_bias_mult > self.D("1.0")
        assert out.thr_sell > self.D("0.02")

    def test_hysteresis_hold_buy(self):
        out = apply_aurora_policy(self._make_input(
            0.015, current_side="buy",
        ))
        assert out.side == "buy"  # Hold: 0.015 >= 0.01 neutral

    def test_output_is_frozen(self):
        out = apply_aurora_policy(self._make_input(0.16))
        with pytest.raises(AttributeError):
            out.side = "sell"

    def test_no_execution_fields(self):
        """Policy must NOT contain execution-ownership fields."""
        out = apply_aurora_policy(self._make_input(0.16))
        assert not hasattr(out, "score")
        assert not hasattr(out, "shield_multiplier")
        assert not hasattr(out, "psi_vector")


# ── Equivalence: old kernel == new math+policy ──────────────────────


class TestEquivalenceWithKernel:
    """Verify that the decomposed path produces identical results to the
    original monolithic QuadraticScoringKernel.compute()."""
    D = decimal.Decimal

    def _compute_via_kernel(self, pillar_sum, shield_mult=1.0, **kw):
        from apps.reference.shared.decision_primitives.scoring_kernel import (
            QuadraticScoringKernel,
        )
        return QuadraticScoringKernel.compute(
            symbol="ETHUSDT",
            features={"pillar_sum": pillar_sum},
            warmup_readiness={},
            price=self.D("100"),
            signal_weights={},
            feature_neutrals={},
            essential_features=[],
            base_threshold=self.D("0.02"),
            regime_name="DEFAULT",
            regime_thresholds={"DEFAULT": 1.0},
            side_bias_state=None,
            direction_strength_cfg={},
            delta_price_cap_pct=self.D("0.02"),
            neutral_threshold=self.D("0.01"),
            current_side=kw.get("current_side", ""),
            shield_fn=lambda *_args: (shield_mult, ["TEST_SHIELD"]),
            score_multiplier=kw.get("score_multiplier", 1.0),
            **{k: v for k, v in kw.items() if k not in ("current_side", "score_multiplier")},
        )

    @pytest.mark.parametrize("pillar_sum", [0.4, -0.3, 0.0, 0.01, -0.99, 1.0])
    def test_score_equivalence(self, pillar_sum):
        result = self._compute_via_kernel(pillar_sum, shield_mult=0.6)
        # Verify the kernel still works identically
        expected_clamped = max(-1.0, min(1.0, pillar_sum))
        expected_pre_shield = (1 if expected_clamped >=
                               0 else -1) * (abs(expected_clamped) ** 2)
        expected_decision = expected_pre_shield * 0.6
        assert float(result.decision_score) == pytest.approx(
            expected_decision, abs=1e-7)
        assert float(result.sizing_score) == pytest.approx(
            expected_pre_shield * 0.6, abs=1e-7)

    def test_side_preserved(self):
        result = self._compute_via_kernel(0.4, shield_mult=0.6)
        assert result.side == "buy"

    def test_deferred_on_missing_pillar(self):
        from apps.reference.shared.decision_primitives.scoring_kernel import QuadraticScoringKernel
        result = QuadraticScoringKernel.compute(
            symbol="ETHUSDT",
            features={},
            warmup_readiness={},
            price=self.D("100"),
            signal_weights={},
            feature_neutrals={},
            essential_features=[],
            base_threshold=self.D("0.02"),
            regime_name="DEFAULT",
            regime_thresholds={"DEFAULT": 1.0},
            side_bias_state=None,
            direction_strength_cfg={},
            delta_price_cap_pct=self.D("0.02"),
        )
        assert result.deferred is True
        assert result.defer_reason == "PILLAR_WARMUP"

    def test_hysteresis_equivalence(self):
        # 0.015 quadratic → 0.000225 decision_score, which is < 0.01 neutral threshold
        # So even with current_side="buy", it exits to neutral
        result = self._compute_via_kernel(
            0.015, shield_mult=1.0, current_side="buy")
        assert result.side == ""  # Exit: 0.000225 < 0.01 neutral

    def test_regime_threshold_equivalence(self):
        result = self._compute_via_kernel(0.03, shield_mult=1.0)
        # 0.03 quadratic → 0.0009 decision_score < 0.02 threshold → neutral
        assert result.side == ""

    def test_psi_vector_fields_preserved(self):
        result = self._compute_via_kernel(0.4, shield_mult=0.6)
        psi = result.psi_vector
        required_keys = {
            "scoring_engine", "source", "s_linear", "multiplier",
            "s_scaled_raw", "s_clamped", "clamped",
            "admission_mode", "sizing_mode",
            "admission_pre_shield", "sizing_pre_shield",
            "decision_score", "sizing_score",
            "shield_multiplier", "shield_reasons",
            "threshold_factor", "thr_buy", "thr_sell",
            "buy_bias_mult", "sell_bias_mult", "side_why",
        }
        missing = required_keys - set(psi.keys())
        assert not missing, f"psi_vector missing keys: {missing}"
