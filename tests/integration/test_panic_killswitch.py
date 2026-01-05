"""
Integration tests for Panic Killswitch blocking CMD:OPEN.
"""

import pytest
from vfoundation.core.protocol import Message
from apps.reference.domains.execution_position.fsm import ExecPosFSM


class MockTradingConfig:
    def get(self, key, default=None):
        if key == "risk":
            return {
                "daily": {
                    "max_drawdown_pct": 8,
                    "reset_time_utc": "00:00",
                }
            }
        elif key == "execution":
            return {"cooldown_ms": 1000, "guard_enabled": True}
        return default


class MockConfigWithOps:
    def __init__(self, panic_on=False, quiet_hours=None, allowlist=None):
        self.trading = MockTradingConfig()
        self._ops = {
            "panic_killswitch": panic_on,
            "quiet_hours_utc": quiet_hours or [],
            "allowlist_symbols": allowlist or [],
        }

    def get(self, key, default=None):
        if key == "risk":
            return {
                "daily": {
                    "max_drawdown_pct": 8,
                    "reset_time_utc": "00:00",
                }
            }
        elif key == "ops":
            return self._ops
        return default


@pytest.mark.skip(reason="Requires complex FSM portfolio state initialization")
class TestPanicKillswitchIntegration:
    """Test Panic Killswitch integration with ExecPosFSM."""

    def test_panic_killswitch_blocks_open(self):
        """Test that Panic Killswitch blocks all CMD:OPEN when enabled."""
        config = MockConfigWithOps(panic_on=True)
        fsm = ExecPosFSM(config, None, shadow_mode=True)

        # Try to open position - should be blocked by panic killswitch
        open_msg = Message(
            op="CMD",
            verb="OPEN",
            src="decision_making",
            dst="execution_position",
            rid="test_panic",
            pld={
                "symbol": "BTCUSDT",
                "side": "BUY",
                "qty": "0.001",
                "price_ref": "50000",
                "idempotent_key": "test_key_panic",
            },
        )
        result = fsm.handle(open_msg)

        # Should return ERR:OPEN with PANIC_ON
        assert result is not None
        assert result.op == "ERR"
        assert result.verb == "OPEN"
        assert result.pld["reason"] == "PANIC_ON"

    def test_panic_killswitch_allows_when_disabled(self):
        """Test that trades are allowed when panic killswitch is disabled."""
        config = MockConfigWithOps(panic_on=False)
        fsm = ExecPosFSM(config, None, shadow_mode=True)

        # Set sufficient equity to pass exposure guard
        portfolio_msg = Message(
            op="EVT",
            verb="PORTFOLIO_STATE_UPDATED",
            src="portfolio",
            dst="execution_position",
            rid="test_portfolio_normal",
            pld={"equity_free_usdt": "10000"},  # High equity
        )
        fsm.handle(portfolio_msg)

        # Try to open position - should pass panic check and go to open_flow
        open_msg = Message(
            op="CMD",
            verb="OPEN",
            src="decision_making",
            dst="execution_position",
            rid="test_normal",
            pld={
                "symbol": "BTCUSDT",
                "side": "BUY",
                "qty": "0.001",
                "price_ref": "50000",
                "idempotent_key": "test_key_normal",
            },
        )
        result = fsm.handle(open_msg)

        # Should return DEC:OPEN (passes panic check, goes to open_flow)
        assert result is not None
        assert result.op == "DEC"
        assert result.verb == "OPEN"

    def test_quiet_hours_blocks_open(self):
        """Test that Quiet Hours blocks CMD:OPEN during specified times."""
        # Use a time range that should always be active for testing
        config = MockConfigWithOps(panic_on=False, quiet_hours=["00:00-23:59"])
        fsm = ExecPosFSM(config, None, shadow_mode=True)

        # Set sufficient equity
        portfolio_msg = Message(
            op="EVT",
            verb="PORTFOLIO_STATE_UPDATED",
            src="portfolio",
            dst="execution_position",
            rid="test_portfolio_quiet",
            pld={"equity_free_usdt": "10000"},
        )
        fsm.handle(portfolio_msg)

        # Try to open position - should be blocked by quiet hours
        open_msg = Message(
            op="CMD",
            verb="OPEN",
            src="decision_making",
            dst="execution_position",
            rid="test_quiet",
            pld={
                "symbol": "BTCUSDT",
                "side": "BUY",
                "qty": "0.001",
                "price_ref": "50000",
                "idempotent_key": "test_key_quiet",
            },
        )
        result = fsm.handle(open_msg)

        # Should return ERR:OPEN with QUIET_HOURS
        assert result is not None
        assert result.op == "ERR"
        assert result.verb == "OPEN"
        assert result.pld["reason"] == "QUIET_HOURS"

    def test_allowlist_blocks_non_allowed_symbol(self):
        """Test that allowlist blocks symbols not in the list."""
        config = MockConfigWithOps(panic_on=False, allowlist=["ETHUSDT"])
        fsm = ExecPosFSM(config, None, shadow_mode=True)

        # Set sufficient equity
        portfolio_msg = Message(
            op="EVT",
            verb="PORTFOLIO_STATE_UPDATED",
            src="portfolio",
            dst="execution_position",
            rid="test_portfolio_allowlist_block",
            pld={"equity_free_usdt": "10000"},
        )
        fsm.handle(portfolio_msg)

        # Try to open BTC position - should be blocked (not in allowlist)
        open_msg = Message(
            op="CMD",
            verb="OPEN",
            src="decision_making",
            dst="execution_position",
            rid="test_allowlist_block",
            pld={
                "symbol": "BTCUSDT",  # Not in allowlist
                "side": "BUY",
                "qty": "0.001",
                "price_ref": "50000",
                "idempotent_key": "test_key_allowlist_block",
            },
        )
        result = fsm.handle(open_msg)

        # Should return ERR:OPEN with SYMBOL_NOT_ALLOWED
        assert result is not None
        assert result.op == "ERR"
        assert result.verb == "OPEN"
        assert result.pld["reason"] == "SYMBOL_NOT_ALLOWED"
        assert result.pld["symbol"] == "BTCUSDT"
        assert "ETHUSDT" in result.pld["allow"]

    def test_allowlist_allows_allowed_symbol(self):
        """Test that allowlist allows symbols in the list."""
        config = MockConfigWithOps(panic_on=False, allowlist=["BTCUSDT"])
        fsm = ExecPosFSM(config, None, shadow_mode=True)

        # Set sufficient equity
        portfolio_msg = Message(
            op="EVT",
            verb="PORTFOLIO_STATE_UPDATED",
            src="portfolio",
            dst="execution_position",
            rid="test_portfolio_allowlist_allow",
            pld={"equity_free_usdt": "10000"},
        )
        fsm.handle(portfolio_msg)

        # Try to open BTC position - should be allowed (in allowlist)
        open_msg = Message(
            op="CMD",
            verb="OPEN",
            src="decision_making",
            dst="execution_position",
            rid="test_allowlist_allow",
            pld={
                "symbol": "BTCUSDT",  # In allowlist
                "side": "BUY",
                "qty": "0.001",
                "price_ref": "50000",
                "idempotent_key": "test_key_allowlist_allow",
            },
        )
        result = fsm.handle(open_msg)

        # Should return DEC:OPEN (passes allowlist check)
        assert result is not None
        assert result.op == "DEC"
        assert result.verb == "OPEN"

    def test_empty_allowlist_allows_all(self):
        """Test that empty allowlist allows all symbols."""
        config = MockConfigWithOps(panic_on=False, allowlist=[])
        fsm = ExecPosFSM(config, None, shadow_mode=True)

        # Set sufficient equity
        portfolio_msg = Message(
            op="EVT",
            verb="PORTFOLIO_STATE_UPDATED",
            src="portfolio",
            dst="execution_position",
            rid="test_portfolio_empty_allowlist",
            pld={"equity_free_usdt": "10000"},
        )
        fsm.handle(portfolio_msg)

        # Try to open any position - should be allowed (empty allowlist = no restrictions)
        open_msg = Message(
            op="CMD",
            verb="OPEN",
            src="decision_making",
            dst="execution_position",
            rid="test_empty_allowlist",
            pld={
                "symbol": "ANYUSDT",
                "side": "BUY",
                "qty": "0.001",
                "price_ref": "50000",
                "idempotent_key": "test_key_empty_allowlist",
            },
        )
        result = fsm.handle(open_msg)

        # Should return DEC:OPEN (passes empty allowlist check)
        assert result is not None
        assert result.op == "DEC"
        assert result.verb == "OPEN"
