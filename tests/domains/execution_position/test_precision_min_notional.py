"""
TASK47c-D: Precision / min_notional Invariant Tests.

Tests to verify that min_notional check uses qty AFTER step_size rounding.
GAP-MATH-01: Avoid false rejects due to rounding inconsistencies.

Based on code review of fsm_open.py:
- Line 208-214: qty is rounded FIRST (qty_dec = qty_rounded)
- Line 240-251: LIMIT notional = qty_dec * price_dec (uses rounded qty)
- Line 253-264: MARKET notional = qty_dec * price_ref (uses rounded qty)

The current code is CORRECT - these tests verify the invariant is maintained.
"""
import pytest
from decimal import Decimal
from unittest.mock import MagicMock
from vfoundation.core.protocol import Message


class TestPrecisionMinNotionalInvariant:
    """Tests for min_notional precision invariant in fsm_open."""
    
    def _make_fsm(self, min_notional=5.0, step_size=0.001, tick_size=0.01, min_qty=0.001):
        """Create OpenFlowFSM with mocked config."""
        from apps.reference.domains.execution_position.fsm_open import OpenFlowFSM
        from apps.reference.config_models import AuroraConfig
        
        config = MagicMock(spec=AuroraConfig)
        config.instruments = {
            "BTCUSDT": MagicMock(
                min_qty=Decimal(str(min_qty)),
                step_size=Decimal(str(step_size)),
                tick_size=Decimal(str(tick_size)),
                min_notional=Decimal(str(min_notional)),
            )
        }
        config.domains = MagicMock()
        config.domains.execution_position = MagicMock()
        config.domains.execution_position.fsm_open = MagicMock()
        config.domains.execution_position.fsm_open.idempotency_window_sec = 60
        
        return OpenFlowFSM(config=config, guard_enabled=True, cooldown_sec=0)
    
    def test_min_notional_check_uses_rounded_qty_not_raw_qty(self):
        """
        Invariant: min_notional should use qty AFTER step_size rounding.
        
        Scenario:
        - raw qty = 0.0019 (would give notional = 95 @ price 50000)
        - step_size = 0.001 → rounded qty = 0.001 (notional = 50 @ price 50000)
        - min_notional = 60
        
        Expected: REJECT (computed notional 50 < min_notional 60)
        This is CORRECT behavior - the actual order would have qty=0.001 after rounding.
        """
        fsm = self._make_fsm(min_notional=60, step_size=0.001)
        
        # qty 0.0019 rounded to step_size 0.001 = 0.001
        # notional = 0.001 * 50000 = 50 < 60 → REJECT
        msg = Message(
            op="CMD",
            verb="OPEN",
            src="bridge",
            dst="execution_position",
            rid="test-precision-001",
            pld={
                "symbol": "BTCUSDT",
                "side": "BUY",
                "qty": "0.0019",  # Raw qty that will be rounded down
                "order_type": "MARKET",
                "price_ref": "50000",
            },
        )
        
        result = fsm.handle(msg)
        
        # Should reject due to min_notional
        assert result is not None
        assert result.op == "ERR"
        assert "notional" in result.pld.get("reason", "").lower(), \
            f"Expected min_notional rejection, got: {result.pld}"
        
    def test_rounding_can_trigger_min_notional_reject_with_correct_reason(self):
        """
        When raw notional >= min_notional but rounded notional < min_notional,
        the system should REJECT with correct reason (this is NOT a false reject).
        
        Scenario:
        - raw qty = 0.00129 → raw notional = 64.5 @ price 50000 (>= 60)
        - rounded qty = 0.001 → actual notional = 50 @ price 50000 (< 60)
        
        Expected: REJECT with reason containing "notional" and "<"
        """
        fsm = self._make_fsm(min_notional=60, step_size=0.001)
        
        # raw qty = 0.00129, raw notional = 0.00129 * 50000 = 64.5 >= 60
        # rounded qty = 0.001, actual notional = 0.001 * 50000 = 50 < 60
        msg = Message(
            op="CMD",
            verb="OPEN",
            src="bridge",
            dst="execution_position",
            rid="test-precision-002",
            pld={
                "symbol": "BTCUSDT",
                "side": "BUY",
                "qty": "0.00129",  # Raw notional OK, but rounds down to fail
                "order_type": "MARKET",
                "price_ref": "50000",
            },
        )
        
        result = fsm.handle(msg)
        
        # Should reject
        assert result is not None
        assert result.op == "ERR"
        
        reason = result.pld.get("reason", "")
        assert "notional" in reason.lower(), f"Reason should mention notional: {reason}"
        assert "<" in reason or "estimated" in reason, f"Reason should show comparison: {reason}"
        
    def test_decision_to_open_path_rounding_visible_in_logs(self, caplog):
        """
        Verify that qty rounding is visible in logs when it occurs.
        
        When qty is rounded, the log should contain:
        - GUARD_ADJUST message with original and rounded values
        """
        import logging
        
        fsm = self._make_fsm(min_notional=5, step_size=0.001)
        
        # qty 0.0015 rounded to 0.001 (actual notional = 50, well above min 5)
        msg = Message(
            op="CMD",
            verb="OPEN",
            src="bridge",
            dst="execution_position",
            rid="test-precision-003",
            pld={
                "symbol": "BTCUSDT",
                "side": "BUY",
                "qty": "0.0015",  # Will be rounded to 0.001
                "order_type": "MARKET",
                "price_ref": "50000",
            },
        )
        
        with caplog.at_level(logging.WARNING):
            result = fsm.handle(msg)
        
        # Should succeed (notional = 50 > 5)
        assert result is not None
        assert result.op == "DEC", f"Expected DEC:OPEN, got {result.op}:{result.verb}"
        
        # Check log contains rounding info
        rounding_logged = any("GUARD_ADJUST" in r.message and "rounded" in r.message.lower() 
                             for r in caplog.records)
        assert rounding_logged, "Expected GUARD_ADJUST log for qty rounding"
        
    def test_no_rounding_when_qty_is_already_on_step(self):
        """
        When qty is already a multiple of step_size, no rounding should occur.
        """
        import logging
        
        fsm = self._make_fsm(min_notional=5, step_size=0.001)
        
        # qty 0.002 is already on step_size 0.001
        msg = Message(
            op="CMD",
            verb="OPEN",
            src="bridge",
            dst="execution_position",
            rid="test-precision-004",
            pld={
                "symbol": "BTCUSDT",
                "side": "BUY",
                "qty": "0.002",  # Already on step
                "order_type": "MARKET",
                "price_ref": "50000",
            },
        )
        
        result = fsm.handle(msg)
        
        # Should succeed
        assert result is not None
        assert result.op == "DEC", f"Expected DEC:OPEN, got {result.op}:{result.verb}"
        
        # Qty in result should be unchanged
        assert result.pld.get("qty") == "0.002"
        
    def test_limit_order_uses_rounded_qty_for_notional(self):
        """
        LIMIT orders: notional = rounded_qty * price
        """
        fsm = self._make_fsm(min_notional=60, step_size=0.001, tick_size=0.01)
        
        # qty 0.0019 → rounded = 0.001, notional = 0.001 * 50000 = 50 < 60
        msg = Message(
            op="CMD",
            verb="OPEN",
            src="bridge",
            dst="execution_position",
            rid="test-precision-005",
            pld={
                "symbol": "BTCUSDT",
                "side": "BUY",
                "qty": "0.0019",
                "price": "50000",
                "order_type": "LIMIT",
            },
        )
        
        result = fsm.handle(msg)
        
        # Should reject due to min_notional (LIMIT uses price, not price_ref)
        assert result is not None
        assert result.op == "ERR"
        assert "notional" in result.pld.get("reason", "").lower()
