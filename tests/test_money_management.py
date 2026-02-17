"""
Unit Tests for Phase 9 Money Management.

- InstrumentQuantizer (exposure → sizing)
- Risk-based sizing logic (risk % → notional)
- EntryPlan structural stops (ATR multiplier scaling)
- Sizing compatibility (metrics_max_notional_cap)
"""
import decimal
from decimal import Decimal
import pytest

from apps.reference.domains.decision_making.instrument_quantizer import (
    InstrumentSpec,
    QuantizedPosition,
    compute_risk_adjusted_notional,
    quantize_exposure,
)
from apps.reference.domains.decision_making.sizing_margin_first import (
    compute_exposure_based_qty,
)
from apps.reference.domains.decision_making.entry_plan import (
    EntryPlan,
    EntryPlanParams,
    ObiMissingPolicy,
)


# =============================================================================
# Instrument Quantizer Tests
# =============================================================================

class TestInstrumentQuantizer:
    @pytest.fixture
    def spec(self):
        return InstrumentSpec(
            step_size=Decimal("0.001"),
            min_qty=Decimal("0.001"),
            min_notional=Decimal("5.0"),
            tick_size=Decimal("0.01"),
        )

    def test_quantize_basic_buy(self, spec):
        # exposure=0.5, max_notional=1000 → target 500
        # price=50 → qty=10
        qp = quantize_exposure(
            exposure=0.5,
            price=Decimal("50"),
            max_notional=Decimal("1000"),
            leverage=1,
            spec=spec,
        )
        assert qp.side == "buy"
        assert qp.notional == pytest.approx(Decimal("499.5"), abs=0.1)  # -0.1% fee buffer
        assert qp.reject_reason is None

    def test_quantize_basic_sell(self, spec):
        qp = quantize_exposure(
            exposure=-0.8,
            price=Decimal("100"),
            max_notional=Decimal("1000"),
            leverage=2,
            spec=spec,
        )
        assert qp.side == "sell"
        assert qp.exposure_abs == 0.8
        # 1000 * 0.8 * 0.999 = 799.2
        assert qp.notional == pytest.approx(Decimal("799.2"), abs=0.1)

    def test_min_qty_reject(self, spec):
        # exposure=0.00001 → tiny notional
        qp = quantize_exposure(
            exposure=0.00001,
            price=Decimal("50000"),
            max_notional=Decimal("100"),
            leverage=1,
            spec=spec,
        )
        assert qp.reject_reason is not None
        assert "MIN_QTY" in qp.reject_reason or "MIN_NOTIONAL" in qp.reject_reason or "ZERO_QUANTITY" in qp.reject_reason

    def test_exposure_cap(self, spec):
        # exposure=1.5 clipped to 1.0 (default cap)
        qp = quantize_exposure(
            exposure=1.5,
            price=Decimal("10"),
            max_notional=Decimal("100"),
            leverage=1,
            spec=spec,
            exposure_cap=0.8,
        )
        assert qp.exposure_abs == 0.8
        
    def test_fee_buffer(self, spec):
        # max_notional=100, buffer=0.1 (10%)
        # exposure=1.0 → notional=90
        qp = quantize_exposure(
            exposure=1.0,
            price=Decimal("1"),
            max_notional=Decimal("100"),
            leverage=1,
            spec=spec,
            fee_buffer=Decimal("0.1"),
        )
        assert qp.notional == pytest.approx(Decimal("90"), abs=0.01)


class TestRiskAdjustedSizing:
    def test_basic_risk_calc(self):
        # Equity=1000, Risk=1% ($10), Stop=1%
        # Notional = 10 / 0.01 = 1000
        notional = compute_risk_adjusted_notional(
            equity=Decimal("1000"),
            exposure_abs=1.0,
            risk_per_trade_pct=Decimal("0.01"),
            stop_distance_pct=Decimal("0.01"),
            leverage=5,
        )
        assert notional == Decimal("1000")

    def test_exposure_scaling(self):
        # Same but exposure=0.5 → Risk $5 → Notional 500
        notional = compute_risk_adjusted_notional(
            equity=Decimal("1000"),
            exposure_abs=0.5,
            risk_per_trade_pct=Decimal("0.01"),
            stop_distance_pct=Decimal("0.01"),
            leverage=5,
        )
        assert notional == Decimal("500")

    def test_leverage_cap(self):
        # Size > Equity*Lev
        # Risk=10% ($100), Stop=1% → Aim 10,000
        # Equity=1000, Lev=5 → Max 5,000
        notional = compute_risk_adjusted_notional(
            equity=Decimal("1000"),
            exposure_abs=1.0,
            risk_per_trade_pct=Decimal("0.10"),
            stop_distance_pct=Decimal("0.01"),
            leverage=5,
        )
        assert notional == Decimal("5000")


# =============================================================================
# Sizing Margin First Integration
# =============================================================================

class TestSizingMarginFirstIntegration:
    def test_exposure_based_qty_defaults(self):
        # Equity=1000, Lev=2 → Max 2000
        # Exposure=0.5 → Target 1000
        # Buffer=0.001 → 999
        # Price=10 → Qty 99.9
        qty, rounded = compute_exposure_based_qty(
            equity=Decimal("1000"),
            exposure=0.5,
            leverage=2,
            price=Decimal("10"),
            step_size=Decimal("0.1"),
        )
        assert rounded == Decimal("99.9")

    def test_metrics_cap_override(self):
        # Cap=100
        # Exposure=1.0 → Target 100
        qty, rounded = compute_exposure_based_qty(
            equity=Decimal("1000"),
            exposure=1.0,
            metrics_max_notional_cap=Decimal("100"),
            leverage=2,
            price=Decimal("1"),
            step_size=Decimal("1"),
        )
        assert rounded == Decimal("100")


# =============================================================================
# Structural Stop Tests (EntryPlan)
# =============================================================================

class TestStructuralStops:
    @pytest.fixture
    def params(self):
        return EntryPlanParams(
            atr_period=14,
            entry_k_atr=0.5,
            sl_k_atr=2.0,  # Legacy default
            tp_k_atr=3.0,
            obi_weight=1.0,
            obi_mod_clamp_min=0.8,
            obi_mod_clamp_max=1.2,
            require_atr=True,
            obi_missing_policy=ObiMissingPolicy.NEUTRAL,
            structural_stop_enabled=True,
            base_atr_mult=1.5,
            confidence_scale=0.5,
            min_stop_bps=15,
        )

    def test_high_conviction_tight_stop(self, params):
        # Conf=1.0
        # Mult = 1.5 - 0.5*1.0 = 1.0 ATR
        ep = EntryPlan(params)
        res = ep.compute(
            side="BUY",
            ref_price="100",
            atr="2",
            pillar_confidence=1.0,
        )
        # SL dist = 1.0 * 2 = 2
        # Price = 98 - use approx for robust float comparison
        assert float(res.stop_loss_price) == pytest.approx(98.0)
        assert res.atr_multiplier == 1.0

    def test_zero_conviction_wide_stop(self, params):
        # Conf=0.0
        # Mult = 1.5 - 0.0 = 1.5 ATR
        ep = EntryPlan(params)
        res = ep.compute(
            side="BUY",
            ref_price="100",
            atr="2",
            pillar_confidence=0.0,
        )
        # SL dist = 1.5 * 2 = 3
        # Price = 97
        assert float(res.stop_loss_price) == pytest.approx(97.0)
        assert res.atr_multiplier == 1.5

    def test_legacy_fallback(self, params):
        # Disable structural stop config override
        # Use dataclasses.replace if possible or just fresh params
        p2 = EntryPlanParams(
            **{k: v for k, v in params.__dict__.items() if k != 'structural_stop_enabled'},
            structural_stop_enabled=False
        )
        ep = EntryPlan(p2)
        res = ep.compute(
            side="BUY",
            ref_price="100",
            atr="2",
            pillar_confidence=1.0, # Should be ignored
        )
        # Legacy sl_k_atr = 2.0
        # SL dist = 2.0 * 2 = 4
        # Price = 96
        assert float(res.stop_loss_price) == pytest.approx(96.0)

    def test_min_stop_bps_floor(self, params):
        # ATR very small (0.01)
        # Mult=1.0 (high conf)
        # SL dist raw = 0.01
        # Min bps = 15bps of 100 = 0.15
        ep = EntryPlan(params)
        res = ep.compute(
            side="BUY",
            ref_price="100",
            atr="0.01",
            pillar_confidence=1.0,
        )
        # Should be floored to 0.15
        # Price = 99.85
        assert float(res.stop_loss_price) == pytest.approx(99.85)

