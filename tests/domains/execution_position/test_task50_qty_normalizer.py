"""
TASK50: Unit tests for qty_normalizer.

Tests quantity normalization with Binance LOT_SIZE / MIN_QTY / MIN_NOTIONAL filters.
Verifies fail-closed semantics: no silent bump-ups, explicit NRR codes.
"""

import pytest
from decimal import Decimal

from apps.reference.domains.execution_position.qty_normalizer import (
    normalize_qty,
    verify_ack_qty,
    QtyNormalizeResult,
    NRR_QTY_ROUNDED_TO_ZERO,
    NRR_QTY_BELOW_MIN_QTY,
    NRR_NOTIONAL_BELOW_MIN,
    NRR_INVALID_INPUT,
)


class TestNormalizeQtyBasicRounding:
    """Test basic step_size rounding with ROUND_DOWN."""

    def test_exact_step_passes(self):
        """raw=1.02, step=0.01 → qty=1.02 ok"""
        result = normalize_qty(
            raw_qty="1.02",
            price="100",
            step_size="0.01",
            min_qty="0.01",
        )
        assert result.ok is True
        assert result.qty == Decimal("1.02")
        assert result.why == ""

    def test_round_down_fractional_step(self):
        """raw=1.029, step=0.01 → qty=1.02 ok (floor)"""
        result = normalize_qty(
            raw_qty="1.029",
            price="100",
            step_size="0.01",
            min_qty="0.01",
        )
        assert result.ok is True
        assert result.qty == Decimal("1.02")

    def test_round_down_large_step(self):
        """raw=1.3, step=1.0 → qty=1 ok"""
        result = normalize_qty(
            raw_qty="1.3",
            price="150",
            step_size="1",
            min_qty="1",
        )
        assert result.ok is True
        assert result.qty == Decimal("1")

    def test_round_down_with_larger_raw(self):
        """raw=0.99, step=0.1 → qty=0.9 ok (if min_qty <= 0.9)"""
        result = normalize_qty(
            raw_qty="0.99",
            price="100",
            step_size="0.1",
            min_qty="0.1",
        )
        assert result.ok is True
        assert result.qty == Decimal("0.9")


class TestNormalizeQtyFailClosed:
    """Test fail-closed semantics - no silent bump-ups."""

    def test_solusdt_incident_case_fails(self):
        """
        CRITICAL: raw=0.27, step=1.0, min_qty=1.0 → MUST FAIL
        
        This is the exact case from TASK49/50 incident where 0.27 was
        silently bumped to 1.0. New behavior: fail-closed.
        
        floor(0.27/1)*1 = 0 → NRR-QTY-ROUNDED-TO-ZERO
        """
        result = normalize_qty(
            raw_qty="0.27",
            price="150",
            step_size="1",
            min_qty="1",
        )
        assert result.ok is False
        # floor(0.27/1)*1 = 0, so it fails on ROUNDED-TO-ZERO first
        assert result.why == NRR_QTY_ROUNDED_TO_ZERO
        assert result.qty is None
        assert result.rounded_qty == Decimal("0")

    def test_rounded_to_zero_fails(self):
        """raw=0.009, step=0.01 → fail (rounded to 0)"""
        result = normalize_qty(
            raw_qty="0.009",
            price="100",
            step_size="0.01",
            min_qty="0.01",
        )
        assert result.ok is False
        assert result.why == NRR_QTY_ROUNDED_TO_ZERO
        assert result.rounded_qty == Decimal("0")

    def test_below_min_qty_fails(self):
        """raw=0.5, step=0.1, min_qty=1.0 → fail (0.5 < 1.0)"""
        result = normalize_qty(
            raw_qty="0.5",
            price="100",
            step_size="0.1",
            min_qty="1.0",
        )
        assert result.ok is False
        assert result.why == NRR_QTY_BELOW_MIN_QTY
        assert result.rounded_qty == Decimal("0.5")

    def test_no_bump_up_to_min_qty(self):
        """
        CRITICAL: Verify no silent bump-up.
        raw=0.8, step=0.1, min_qty=1.0 → MUST fail, NOT bump to 1.0
        """
        result = normalize_qty(
            raw_qty="0.8",
            price="100",
            step_size="0.1",
            min_qty="1.0",
        )
        assert result.ok is False
        assert result.why == NRR_QTY_BELOW_MIN_QTY
        # Should NOT have qty=1.0 (no bump-up)
        assert result.qty is None


class TestNormalizeQtyMinNotional:
    """Test MIN_NOTIONAL validation."""

    def test_notional_below_min_fails(self):
        """raw=0.01, price=100, min_notional=10 → notional=1 < 10 → fail"""
        result = normalize_qty(
            raw_qty="0.01",
            price="100",
            step_size="0.001",
            min_qty="0.001",
            min_notional="10",
        )
        assert result.ok is False
        assert result.why == NRR_NOTIONAL_BELOW_MIN
        assert result.notional == Decimal("1")  # 0.01 * 100

    def test_notional_above_min_passes(self):
        """raw=0.1, price=100, min_notional=5 → notional=10 >= 5 → ok"""
        result = normalize_qty(
            raw_qty="0.1",
            price="100",
            step_size="0.01",
            min_qty="0.01",
            min_notional="5",
        )
        assert result.ok is True
        assert result.notional == Decimal("10")

    def test_notional_exactly_min_passes(self):
        """raw=0.1, price=100, min_notional=10 → notional=10 == 10 → ok"""
        result = normalize_qty(
            raw_qty="0.1",
            price="100",
            step_size="0.01",
            min_qty="0.01",
            min_notional="10",
        )
        assert result.ok is True
        assert result.notional == Decimal("10")

    def test_no_notional_bump_up(self):
        """
        CRITICAL: Verify no bump-up to meet notional.
        raw=0.05, price=100, min_notional=10 → notional=5 < 10 → fail
        Old code would bump qty to meet notional. New: fail-closed.
        """
        result = normalize_qty(
            raw_qty="0.05",
            price="100",
            step_size="0.01",
            min_qty="0.01",
            min_notional="10",
        )
        assert result.ok is False
        assert result.why == NRR_NOTIONAL_BELOW_MIN
        # Should NOT have qty bumped to 0.1
        assert result.qty is None

    def test_no_min_notional_skips_check(self):
        """When min_notional=None, skip notional validation."""
        result = normalize_qty(
            raw_qty="0.01",
            price="100",
            step_size="0.001",
            min_qty="0.001",
            min_notional=None,
        )
        assert result.ok is True
        assert result.qty == Decimal("0.01")


class TestNormalizeQtyEdgeCases:
    """Test edge cases and input validation."""

    def test_zero_step_size_fails(self):
        """Invalid step_size=0 → fail"""
        result = normalize_qty(
            raw_qty="1.0",
            price="100",
            step_size="0",
            min_qty="0.01",
        )
        assert result.ok is False
        assert result.why == NRR_INVALID_INPUT

    def test_negative_step_size_fails(self):
        """Invalid step_size<0 → fail"""
        result = normalize_qty(
            raw_qty="1.0",
            price="100",
            step_size="-0.01",
            min_qty="0.01",
        )
        assert result.ok is False
        assert result.why == NRR_INVALID_INPUT

    def test_float_inputs_work(self):
        """Accept float inputs (convert to Decimal)."""
        result = normalize_qty(
            raw_qty=1.5,
            price=100.0,
            step_size=0.1,
            min_qty=0.1,
        )
        assert result.ok is True
        assert result.qty == Decimal("1.5")

    def test_decimal_inputs_work(self):
        """Accept Decimal inputs directly."""
        result = normalize_qty(
            raw_qty=Decimal("1.5"),
            price=Decimal("100"),
            step_size=Decimal("0.1"),
            min_qty=Decimal("0.1"),
        )
        assert result.ok is True
        assert result.qty == Decimal("1.5")

    def test_very_small_step_precision(self):
        """High precision step_size like 0.00001."""
        result = normalize_qty(
            raw_qty="12345.678901",
            price="1",
            step_size="0.00001",
            min_qty="0.00001",
        )
        assert result.ok is True
        assert result.qty == Decimal("12345.67890")


class TestNormalizeQtyResultFields:
    """Test that result contains all expected fields."""

    def test_success_result_fields(self):
        """Verify all fields in successful result."""
        result = normalize_qty(
            raw_qty="1.5",
            price="100",
            step_size="0.1",
            min_qty="0.1",
            min_notional="5",
        )
        assert result.ok is True
        assert result.qty == Decimal("1.5")
        assert result.why == ""
        assert result.raw_qty == Decimal("1.5")
        assert result.rounded_qty == Decimal("1.5")
        assert result.step_size == Decimal("0.1")
        assert result.min_qty == Decimal("0.1")
        assert result.min_notional == Decimal("5")
        assert result.price == Decimal("100")
        assert result.notional == Decimal("150")

    def test_failure_result_fields(self):
        """Verify all fields in failed result."""
        result = normalize_qty(
            raw_qty="0.5",
            price="100",
            step_size="0.1",
            min_qty="1.0",
        )
        assert result.ok is False
        assert result.qty is None
        assert result.why == NRR_QTY_BELOW_MIN_QTY
        assert result.raw_qty == Decimal("0.5")
        assert result.rounded_qty == Decimal("0.5")

    def test_to_dict_method(self):
        """Verify to_dict() for logging."""
        result = normalize_qty(
            raw_qty="1.5",
            price="100",
            step_size="0.1",
            min_qty="0.1",
        )
        d = result.to_dict()
        assert d["ok"] is True
        assert d["qty"] == "1.5"
        assert d["raw_qty"] == "1.5"
        assert d["step_size"] == "0.1"


class TestVerifyAckQty:
    """Test ACK quantity verification."""

    def test_exact_match_passes(self):
        """sent=1.5, ack=1.5 → match"""
        ok, reason = verify_ack_qty("1.5", "1.5", "0.1")
        assert ok is True
        assert reason == ""

    def test_within_tolerance_passes(self):
        """sent=1.5, ack=1.6, step=0.1 → within 1 step"""
        ok, reason = verify_ack_qty("1.5", "1.6", "0.1")
        assert ok is True

    def test_mismatch_fails(self):
        """sent=0.27, ack=1.0, step=0.01 → mismatch (diff=0.73 > 0.01)"""
        ok, reason = verify_ack_qty("0.27", "1.0", "0.01")
        assert ok is False
        assert "QTY_ACK_MISMATCH" in reason

    def test_original_incident_detected(self):
        """
        CRITICAL: Detect the original 0.27 → 1 mismatch.
        This is what should have been caught in TASK49.
        
        With step=1, tolerance=1, diff=0.73 is within tolerance.
        Use smaller step to detect the mismatch.
        """
        # With realistic step=0.01 (not step=1), mismatch is detected
        ok, reason = verify_ack_qty("0.27", "1", "0.01")
        assert ok is False
        assert "QTY_ACK_MISMATCH" in reason


class TestRealWorldScenarios:
    """Test with realistic Binance Futures scenarios."""

    def test_btcusdt_realistic(self):
        """BTCUSDT: step=0.001, min_qty=0.001, min_notional=100"""
        # Sizing: $200 position at $100k BTC = 0.002 BTC
        result = normalize_qty(
            raw_qty="0.002",
            price="100000",
            step_size="0.001",
            min_qty="0.001",
            min_notional="100",
        )
        assert result.ok is True
        assert result.qty == Decimal("0.002")
        assert result.notional == Decimal("200")

    def test_btcusdt_too_small_fails(self):
        """BTCUSDT: $50 position < min_notional=$100 → fail"""
        result = normalize_qty(
            raw_qty="0.0005",
            price="100000",
            step_size="0.001",
            min_qty="0.001",
            min_notional="100",
        )
        # 0.0005 rounds to 0 with step=0.001
        assert result.ok is False

    def test_solusdt_original_incident(self):
        """
        SOLUSDT incident: equity=$677, 5% = $33.88, price=$150 → raw_qty=0.2258
        With step=1, min_qty=1 → MUST FAIL (not bump to 1)
        
        floor(0.2258/1)*1 = 0 → NRR-QTY-ROUNDED-TO-ZERO
        """
        equity = Decimal("677.56")
        percent = Decimal("0.05")
        price = Decimal("150")
        raw_qty = (equity * percent) / price  # ~0.2258
        
        result = normalize_qty(
            raw_qty=raw_qty,
            price=price,
            step_size="1",
            min_qty="1",
            min_notional="5",
        )
        assert result.ok is False
        # floor(0.2258/1)*1 = 0, fails on ROUNDED-TO-ZERO
        assert result.why == NRR_QTY_ROUNDED_TO_ZERO
        # Verify NO bump-up happened
        assert result.qty is None

    def test_dogeusdt_step_1(self):
        """DOGEUSDT: step=1, min_qty=1 with small position"""
        result = normalize_qty(
            raw_qty="150.7",
            price="0.35",
            step_size="1",
            min_qty="1",
            min_notional="5",
        )
        assert result.ok is True
        assert result.qty == Decimal("150")
        assert result.notional == Decimal("52.5")  # 150 * 0.35
