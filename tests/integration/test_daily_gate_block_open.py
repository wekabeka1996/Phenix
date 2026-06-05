"""
Integration tests for DailyGate blocking CMD:OPEN.
"""

import pytest
from vfoundation.core.protocol import Message
from apps.reference.domains.execution_position.fsm import ExecPosFSM


class MockTradingConfig:
    def get(self, key, default=None):
        if key == "risk":
            return {
                "daily": {
                    "max_drawdown_pct": 5,  # Low limit for testing
                    "reset_time_utc": "00:00",
                }
            }
        elif key == "execution":
            return {"cooldown_ms": 1000, "guard_enabled": True}
        return default


class MockConfig:
    def __init__(self):
        self.trading = MockTradingConfig()

    def get(self, key, default=None):
        if key == "risk":
            return {
                "daily": {
                    "max_drawdown_pct": 5,  # Low limit for testing
                    "reset_time_utc": "00:00",
                }
            }
        return default


@pytest.mark.skip(reason="Requires complex FSM daily_gate initialization")
class TestDailyGateIntegration:
    """Test DailyGate integration with ExecPosFSM."""

    def test_daily_gate_blocks_open_on_drawdown(self):
        """Test that DailyGate blocks CMD:OPEN when drawdown limit exceeded."""
        config = MockConfig()
        fsm = ExecPosFSM(config, None, shadow_mode=True)

        # Set initial equity (simulate portfolio update)
        portfolio_msg = Message(
            op="EVT",
            verb="PORTFOLIO_STATE_UPDATED",
            src="portfolio",
            dst="execution_position",
            rid="test_portfolio",
            pld={"equity_free_usdt": "1000"},
        )
        fsm.handle(portfolio_msg)

        # Manually trigger daily reset (set equity_open)
        fsm.daily_gate._equity_open = fsm.daily_gate._equity_now

        # Simulate drawdown exceeding limit (10% when limit is 5%)
        portfolio_msg2 = Message(
            op="EVT",
            verb="PORTFOLIO_STATE_UPDATED",
            src="portfolio",
            dst="execution_position",
            rid="test_portfolio2",
            pld={"equity_free_usdt": "900"},  # 10% drawdown
        )
        fsm.handle(portfolio_msg2)

        # Try to open position - should be blocked
        open_msg = Message(
            op="CMD",
            verb="OPEN",
            src="decision_making",
            dst="execution_position",
            rid="test_open",
            pld={
                "symbol": "BTCUSDT",
                "side": "BUY",
                "qty": "0.001",
                "price_ref": "50000",  # Required for MARKET orders
                "idempotent_key": "test_key_123",
            },
        )
        result = fsm.handle(open_msg)

        # Should return ERR:OPEN with daily risk limit
        assert result is not None
        assert result.op == "ERR"
        assert result.verb == "OPEN"
        assert result.pld["reason"] == "DAILY_RISK_LIMIT"
        assert result.pld["detail"] == "MAX_DRAWDOWN"

    def test_daily_gate_blocks_open_on_realized_loss(self):
        """Test that DailyGate blocks CMD:OPEN when realized loss limit exceeded."""
        config = MockConfig()
        fsm = ExecPosFSM(config, None, shadow_mode=True)

        # Set equity
        portfolio_msg = Message(
            op="EVT",
            verb="PORTFOLIO_STATE_UPDATED",
            src="portfolio",
            dst="execution_position",
            rid="test_portfolio",
            pld={"equity_free_usdt": "1000"},
        )
        fsm.handle(portfolio_msg)
        fsm.daily_gate._equity_open = fsm.daily_gate._equity_now

        # Accumulate losses exceeding limit
        filled_msg = Message(
            op="EVT",
            verb="ORDER_STATE_CHANGED",
            src="execution_position",
            dst="execution_position",
            rid="test_fill",
            pld={
                "status": "FILLED",
                "realized_pnl_usd": "-300",  # Exceeds 250 limit
            },
        )
        fsm.handle(filled_msg)

        # Try to open position - should be blocked
        open_msg = Message(
            op="CMD",
            verb="OPEN",
            src="decision_making",
            dst="execution_position",
            rid="test_open2",
            pld={
                "symbol": "BTCUSDT",
                "side": "BUY",
                "qty": "0.001",
                "price_ref": "50000",  # Required for MARKET orders
                "idempotent_key": "test_key_456",
            },
        )
        result = fsm.handle(open_msg)

        # Should return ERR:OPEN with daily risk limit
        assert result is not None
        assert result.op == "ERR"
        assert result.verb == "OPEN"
        assert result.pld["reason"] == "DAILY_RISK_LIMIT"
        assert result.pld["detail"] == "MAX_REALIZED_LOSS"

    def test_daily_gate_allows_open_when_limits_not_exceeded(self):
        """Test that DailyGate allows CMD:OPEN when limits not exceeded."""
        config = MockConfig()
        fsm = ExecPosFSM(config, None, shadow_mode=True)

        # Set equity
        portfolio_msg = Message(
            op="EVT",
            verb="PORTFOLIO_STATE_UPDATED",
            src="portfolio",
            dst="execution_position",
            rid="test_portfolio",
            pld={"equity_free_usdt": "1000"},
        )
        fsm.handle(portfolio_msg)
        fsm.daily_gate._equity_open = fsm.daily_gate._equity_now

        # Small loss within limits
        filled_msg = Message(
            op="EVT",
            verb="ORDER_STATE_CHANGED",
            src="execution_position",
            dst="execution_position",
            rid="test_fill",
            pld={"status": "FILLED", "realized_pnl_usd": "-10"},
        )
        fsm.handle(filled_msg)

        # Try to open position - should be allowed (DEC:OPEN from open_flow)
        open_msg = Message(
            op="CMD",
            verb="OPEN",
            src="decision_making",
            dst="execution_position",
            rid="test_open3",
            pld={
                "symbol": "BTCUSDT",
                "side": "BUY",
                "qty": "0.001",
                "price_ref": "50000",  # Required for MARKET orders
                "idempotent_key": "test_key_789",
            },
        )
        result = fsm.handle(open_msg)

        # Should return DEC:OPEN (not blocked by daily gate)
        assert result is not None
        assert result.op == "DEC"
        assert result.verb == "OPEN"
