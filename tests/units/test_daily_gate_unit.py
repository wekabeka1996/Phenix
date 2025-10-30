"""
Unit tests for DailyGate risk management.
"""

import pytest
from datetime import datetime, timezone
from vfoundation.apps.reference.domains.risk_management.daily_gate import (
    DailyRiskState,
    _d,
)


class TestDailyGate:
    """Test DailyRiskState functionality."""

    def test_initialization(self):
        """Test DailyRiskState initialization with config."""
        cfg = {
            "risk": {
                "daily": {
                    "max_realized_loss_usd": 500,
                    "max_drawdown_pct": 10,
                    "reset_time_utc": "01:00",
                }
            }
        }
        gate = DailyRiskState(cfg)

        assert gate.cfg.max_realized_loss_usd == 500
        assert gate.cfg.max_drawdown_pct == 10
        assert gate.cfg.reset_h == 1
        assert gate.cfg.reset_m == 0
        assert gate._equity_open == 0
        assert gate._equity_now == 0
        assert gate._realized_pnl == 0

    def test_defaults(self):
        """Test default values when config is missing."""
        cfg = {}
        gate = DailyRiskState(cfg)

        assert gate.cfg.max_realized_loss_usd == 250
        assert gate.cfg.max_drawdown_pct == 8
        assert gate.cfg.reset_h == 0
        assert gate.cfg.reset_m == 0

    def test_on_portfolio_updates_equity(self):
        """Test portfolio updates set current equity."""
        cfg = {}
        gate = DailyRiskState(cfg)

        gate.on_portfolio({"equity_free_usdt": "1000"})
        assert gate._equity_now == 1000

        gate.on_portfolio({"equity_free_usdt": "1200"})
        assert gate._equity_now == 1200

    def test_daily_reset(self):
        """Test daily reset logic."""
        cfg = {"risk": {"daily": {"reset_time_utc": "12:00"}}}
        gate = DailyRiskState(cfg)

        # Set initial equity
        gate.on_portfolio({"equity_free_usdt": "1000"})
        assert gate._equity_open == 1000

        # Simulate reset time (12:00)
        reset_time = datetime(2025, 10, 30, 12, 0, 0, tzinfo=timezone.utc)
        gate._maybe_reset(reset_time)

        # Should have reset
        assert gate._last_reset_date is not None
        assert gate._realized_pnl == 0

    def test_can_open_blocks_without_equity(self):
        """Test fail-closed behavior without equity data."""
        cfg = {}
        gate = DailyRiskState(cfg)

        ok, data = gate.can_open()
        assert ok is False
        assert data["reason"] == "DAILY_RISK_LIMIT"
        assert data["detail"] == "NO_EQUITY"

    def test_can_open_blocks_on_realized_loss_limit(self):
        """Test blocking when realized loss exceeds limit."""
        cfg = {"risk": {"daily": {"max_realized_loss_usd": 100}}}
        gate = DailyRiskState(cfg)

        # Set equity
        gate.on_portfolio({"equity_free_usdt": "1000"})
        gate._equity_open = gate._equity_now  # Simulate reset

        # Accumulate losses
        gate.on_order_filled({"realized_pnl_usd": "-50"})
        gate.on_order_filled({"realized_pnl_usd": "-60"})

        ok, data = gate.can_open()
        assert ok is False
        assert data["reason"] == "DAILY_RISK_LIMIT"
        assert data["detail"] == "MAX_REALIZED_LOSS"
        assert data["realized_pnl_usd"] == "-110"

    def test_can_open_blocks_on_drawdown_limit(self):
        """Test blocking when drawdown exceeds limit."""
        cfg = {"risk": {"daily": {"max_drawdown_pct": 5}}}
        gate = DailyRiskState(cfg)

        # Set initial equity
        gate.on_portfolio({"equity_free_usdt": "1000"})
        gate._equity_open = gate._equity_now  # Simulate reset

        # Simulate 10% drawdown
        gate.on_portfolio({"equity_free_usdt": "900"})

        ok, data = gate.can_open()
        assert ok is False
        assert data["reason"] == "DAILY_RISK_LIMIT"
        assert data["detail"] == "MAX_DRAWDOWN"
        assert data["drawdown_pct"] == "10"

    def test_can_open_allows_when_limits_not_exceeded(self):
        """Test allowing trades when limits not exceeded."""
        cfg = {
            "risk": {"daily": {"max_realized_loss_usd": 100, "max_drawdown_pct": 10}}
        }
        gate = DailyRiskState(cfg)

        # Set equity
        gate.on_portfolio({"equity_free_usdt": "1000"})
        gate._equity_open = gate._equity_now  # Simulate reset

        # Small loss and drawdown
        gate.on_order_filled({"realized_pnl_usd": "-10"})
        gate.on_portfolio({"equity_free_usdt": "950"})  # 5% drawdown

        ok, data = gate.can_open()
        assert ok is True
        assert data["equity_open_usd"] == "1000"
        assert data["equity_now_usd"] == "950"
        assert data["realized_pnl_usd"] == "-10"
        assert data["drawdown_pct"] == "5"

    def test_decimal_conversion(self):
        """Test decimal conversion helper."""
        assert _d("123.45") == 123.45
        assert _d(123) == 123
        assert _d(None) == 0
        assert _d("invalid") == 0
