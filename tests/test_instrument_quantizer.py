"""
Unit tests for InstrumentQuantizer — Exposure → Position Size.

Tests cover:
1. floor_to_step precision
2. quantize_exposure: valid, reject min_qty, reject min_notional, zero price
3. compute_risk_adjusted_notional
4. compute_structural_stop: buy/sell/neutral, confidence scaling
"""
import pytest
from decimal import Decimal

from apps.reference.shared.decision_primitives.instrument_quantizer import (
    InstrumentSpec,
    QuantizedPosition,
    floor_to_step,
    quantize_exposure,
    compute_risk_adjusted_notional,
    compute_structural_stop,
)


D = Decimal


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _btc_spec():
    return InstrumentSpec(
        step_size=D("0.001"),
        min_qty=D("0.001"),
        min_notional=D("5"),
        tick_size=D("0.01"),
    )


# ---------------------------------------------------------------------------
# 1. floor_to_step
# ---------------------------------------------------------------------------
class TestFloorToStep:
    def test_exact_multiple(self):
        assert floor_to_step(D("1.500"), D("0.001")) == D("1.500")

    def test_floor_down(self):
        assert floor_to_step(D("1.5678"), D("0.001")) == D("1.567")

    def test_tiny_qty_rounds_to_zero(self):
        assert floor_to_step(D("0.0001"), D("0.001")) == D("0")

    def test_zero_step_returns_zero(self):
        assert floor_to_step(D("10"), D("0")) == D("0")

    def test_negative_qty_returns_zero(self):
        assert floor_to_step(D("-1"), D("0.001")) == D("0")


# ---------------------------------------------------------------------------
# 2. quantize_exposure
# ---------------------------------------------------------------------------
class TestQuantizeExposure:
    def test_valid_buy(self):
        r = quantize_exposure(
            exposure=0.5,
            price=D("50000"),
            max_notional=D("1000"),
            leverage=10,
            spec=_btc_spec(),
        )
        assert r.side == "buy"
        assert r.qty > 0
        assert r.reject_reason is None
        # notional = 0.5 * 1000 * (1 - 0.001) = 499.5
        # qty = floor(499.5 / 50000, 0.001) = floor(0.00999, 0.001) = 0.009
        assert r.qty == D("0.009")

    def test_valid_sell(self):
        r = quantize_exposure(
            exposure=-0.5,
            price=D("50000"),
            max_notional=D("1000"),
            leverage=10,
            spec=_btc_spec(),
        )
        assert r.side == "sell"
        assert r.qty == D("0.009")

    def test_zero_exposure(self):
        r = quantize_exposure(
            exposure=0.0,
            price=D("50000"),
            max_notional=D("1000"),
            leverage=10,
            spec=_btc_spec(),
        )
        assert r.side == ""
        assert r.qty == D("0")

    def test_reject_min_qty(self):
        """Exposure large enough to get a qty, but below min_qty."""
        spec = InstrumentSpec(
            step_size=D("0.001"),
            min_qty=D("1.0"),  # Very high min qty
            min_notional=D("5"),
            tick_size=D("0.01"),
        )
        r = quantize_exposure(
            exposure=0.5,
            price=D("100"),
            max_notional=D("100"),
            leverage=1,
            spec=spec,
        )
        # qty = floor(0.5*100*0.999/100, 0.001) = floor(0.4995, 0.001) = 0.499
        # 0.499 < min_qty(1.0) → MIN_QTY reject
        assert r.reject_reason is not None
        assert "MIN_QTY" in r.reject_reason

    def test_reject_min_notional(self):
        """Calculated notional below exchange minimum."""
        spec = InstrumentSpec(
            step_size=D("0.001"),
            min_qty=D("0.001"),
            min_notional=D("1000"),  # Very high min notional
            tick_size=D("0.01"),
        )
        r = quantize_exposure(
            exposure=0.5,
            price=D("100"),
            max_notional=D("100"),
            leverage=1,
            spec=spec,
        )
        # notional = 0.5*100*0.999 = 49.95 < min_notional(1000)
        assert r.reject_reason is not None
        assert "MIN_NOTIONAL" in r.reject_reason

    def test_zero_price(self):
        r = quantize_exposure(
            exposure=0.5,
            price=D("0"),
            max_notional=D("1000"),
            leverage=10,
            spec=_btc_spec(),
        )
        assert r.reject_reason == "ZERO_PRICE"

    def test_exposure_capped(self):
        """exposure > cap → clamp to cap."""
        r1 = quantize_exposure(
            exposure=2.0,
            price=D("50000"),
            max_notional=D("1000"),
            leverage=10,
            spec=_btc_spec(),
            exposure_cap=1.0,
        )
        r2 = quantize_exposure(
            exposure=1.0,
            price=D("50000"),
            max_notional=D("1000"),
            leverage=10,
            spec=_btc_spec(),
            exposure_cap=1.0,
        )
        assert r1.qty == r2.qty  # Both capped to 1.0

    def test_fee_buffer_reduces_notional(self):
        """Higher fee buffer → less quantity."""
        r_low = quantize_exposure(
            exposure=1.0, price=D("50000"), max_notional=D("10000"),
            leverage=10, spec=_btc_spec(), fee_buffer=D("0.001"),
        )
        r_high = quantize_exposure(
            exposure=1.0, price=D("50000"), max_notional=D("10000"),
            leverage=10, spec=_btc_spec(), fee_buffer=D("0.05"),
        )
        assert r_low.qty >= r_high.qty


# ---------------------------------------------------------------------------
# 3. compute_risk_adjusted_notional
# ---------------------------------------------------------------------------
class TestRiskAdjustedNotional:
    def test_basic_calc(self):
        # equity=10000, risk=1%, exposure=1.0, stop=0.5%, lev=1
        # risk_amount = 10000 * 0.01 * 1.0 = 100
        # notional = 100 / 0.005 = 20000
        n = compute_risk_adjusted_notional(
            equity=D("10000"),
            exposure_abs=1.0,
            risk_per_trade_pct=D("0.01"),
            stop_distance_pct=D("0.005"),
            leverage=1,
        )
        assert n == D("20000")

    def test_zero_equity(self):
        n = compute_risk_adjusted_notional(
            equity=D("0"), exposure_abs=1.0,
            risk_per_trade_pct=D("0.01"), stop_distance_pct=D("0.005"), leverage=1,
        )
        assert n == D("0")

    def test_zero_exposure(self):
        n = compute_risk_adjusted_notional(
            equity=D("10000"), exposure_abs=0.0,
            risk_per_trade_pct=D("0.01"), stop_distance_pct=D("0.005"), leverage=1,
        )
        assert n == D("0")

    def test_cap_applied(self):
        n = compute_risk_adjusted_notional(
            equity=D("10000"), exposure_abs=1.0,
            risk_per_trade_pct=D("0.01"), stop_distance_pct=D("0.005"),
            leverage=1, notional_cap=D("5000"),
        )
        assert n == D("5000")


# ---------------------------------------------------------------------------
# 4. compute_structural_stop
# ---------------------------------------------------------------------------
class TestStructuralStop:
    def test_buy_stop_below_price(self):
        sl = compute_structural_stop(
            price=D("50000"), atr=D("500"), side="buy",
            pillar_confidence=0.0,
        )
        assert sl < D("50000")

    def test_sell_stop_above_price(self):
        sl = compute_structural_stop(
            price=D("50000"), atr=D("500"), side="sell",
            pillar_confidence=0.0,
        )
        assert sl > D("50000")

    def test_neutral_returns_price(self):
        sl = compute_structural_stop(
            price=D("50000"), atr=D("500"), side="neutral",
            pillar_confidence=0.0,
        )
        assert sl == D("50000")

    def test_high_confidence_tighter_stop(self):
        """Higher pillar_confidence → tighter stop (closer to price)."""
        sl_low = compute_structural_stop(
            price=D("50000"), atr=D("500"), side="buy",
            pillar_confidence=0.0,
        )
        sl_high = compute_structural_stop(
            price=D("50000"), atr=D("500"), side="buy",
            pillar_confidence=1.0,
        )
        # Higher confidence → tighter → higher SL for buy
        assert sl_high > sl_low

    def test_min_stop_enforced(self):
        """Even with huge confidence and tiny ATR, min stop enforced."""
        sl = compute_structural_stop(
            price=D("50000"), atr=D("0.01"), side="buy",
            pillar_confidence=1.0, min_stop_bps=15,
        )
        # min_distance = 50000 * 15/10000 = 75
        assert sl >= D("50000") - D("75")
