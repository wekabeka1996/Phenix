# tests/integration/test_open_exposure_guard.py
"""
Integration test for portfolio exposure guard in open flow.
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import pytest
from decimal import Decimal
from types import SimpleNamespace
from vfoundation.core.protocol import Message
from vfoundation.apps.reference.domains.execution_position.fsm import ExecPosFSM
from vfoundation.apps.reference.domains.execution_position.exposure_guard import (
    ExposureGuard,
)


class TestOpenExposureGuard:
    """Integration tests for exposure guard in open flow."""

    @pytest.fixture
    def config(self):
        """Test configuration with exposure settings."""

        class Cfg:
            def get(self, key, default=None):
                config_data = {
                    "instruments": {
                        "BTCUSDT": {
                            "step_size": "0.001",
                            "min_qty": "0.001",
                            "tick_size": "0.01",
                            "min_notional": "10",
                        }
                    }
                }
                return config_data.get(key, default)

        cfg = Cfg()
        cfg.trading = SimpleNamespace(
            get=lambda key, default=None: {
                "execution": {
                    "exposure": {
                        "max_portfolio_fraction": 0.20,  # 20% limit
                        "count_pending_orders": True,
                        "exclude_reduce_only": True,
                    },
                    "cooldown_ms": 0,  # No cooldown for tests
                    "guard_enabled": True,
                },
                "instruments": {
                    "BTCUSDT": {
                        "step_size": "0.001",
                        "min_qty": "0.001",
                        "tick_size": "0.01",
                        "min_notional": "10",
                    }
                },
            }.get(key, default)
        )
        return cfg

    @pytest.fixture
    def fsm(self, config):
        """Create ExecPosFSM with exposure guard."""
        return ExecPosFSM(config=config, fsm=None, shadow_mode=True)

    def test_exposure_guard_blocks_over_limit(self, fsm, config):
        """Test that exposure guard blocks orders exceeding 20% limit."""
        # Step 1: Send portfolio update with equity=5000 and position worth 1500
        portfolio_msg = Message(
            op="EVT",
            verb="PORTFOLIO_STATE_UPDATED",
            src="position_tracking",
            dst="execution_position",
            rid="test_rid_1",
            pld={
                "equity_free_usdt": "5000.0",
                "positions": [
                    {
                        "symbol": "BTCUSDT",
                        "net_position": "0.1",  # 0.1 BTC
                        "avg_entry_price": "15000.0",  # 0.1 * 15000 = 1500 notional
                    }
                ],
            },
        )
        fsm.handle(portfolio_msg)

        # Verify exposure guard state
        summary = fsm.exposure_guard.get_exposure_summary()
        assert summary["equity_usd"] == "5000.0"
        assert summary["limit_usd"] == "1000.00"  # 5000 * 0.20
        assert summary["positions_usd"] == "1500.00"  # Current position
        assert summary["current_exposure_usd"] == "1500.00"

        # Step 2: Try to open new position worth 200 (1500 + 200 = 1700 > 1000 limit)
        open_msg = Message(
            op="CMD",
            verb="OPEN",
            src="decision_making",
            dst="execution_position",
            rid="test_rid_2",
            pld={
                "symbol": "BTCUSDT",
                "side": "BUY",
                "qty": "0.01",  # 0.01 BTC
                "order_type": "MARKET",
                "price_ref": "20000.0",  # 0.01 * 20000 = 200 notional
                "idempotent_key": "test_key_1",
            },
        )

        result = fsm.handle(open_msg)

        # Should be rejected with PORTFOLIO_EXPOSURE_LIMIT
        assert result is not None
        assert result.op == "ERR"
        assert result.verb == "OPEN"
        assert result.pld["reason"] == "PORTFOLIO_EXPOSURE_LIMIT"
        assert result.pld["equity_usd"] == "5000.0"
        assert result.pld["limit_usd"] == "1000.00"
        assert result.pld["positions_usd"] == "1500.00"
        assert result.pld["pending_usd"] == "0"
        assert result.pld["new_usd"] == "200.000"
        assert result.pld["exposure_will_be_usd"] == "1700.000"

        # Verify exposure was released (no pending reservations)
        summary_after = fsm.exposure_guard.get_exposure_summary()
        assert summary_after["pending_orders_count"] == 0

    def test_exposure_guard_allows_under_limit(self, fsm, config):
        """Test that exposure guard allows orders under 20% limit."""
        # Step 1: Send portfolio update with equity=5000 and small position worth 300
        portfolio_msg = Message(
            op="EVT",
            verb="PORTFOLIO_STATE_UPDATED",
            src="position_tracking",
            dst="execution_position",
            rid="test_rid_3",
            pld={
                "equity_free_usdt": "5000.0",
                "positions": [
                    {
                        "symbol": "BTCUSDT",
                        "net_position": "0.02",  # 0.02 BTC
                        "avg_entry_price": "15000.0",  # 0.02 * 15000 = 300 notional
                    }
                ],
            },
        )
        fsm.handle(portfolio_msg)

        # Step 2: Try to open new position worth 200 (300 + 200 = 500 < 1000 limit)
        open_msg = Message(
            op="CMD",
            verb="OPEN",
            src="decision_making",
            dst="execution_position",
            rid="test_rid_4",
            pld={
                "symbol": "BTCUSDT",
                "side": "BUY",
                "qty": "0.01",  # 0.01 BTC
                "order_type": "MARKET",
                "price_ref": "20000.0",  # 0.01 * 20000 = 200 notional
                "idempotent_key": "test_key_2",
            },
        )

        result = fsm.handle(open_msg)

        # Should be accepted
        assert result is not None
        assert result.op == "DEC"
        assert result.verb == "OPEN"
        assert result.pld["symbol"] == "BTCUSDT"
        assert result.pld["qty"] == "0.01"
        assert result.pld["order_type"] == "MARKET"

        # Verify exposure was reserved
        summary_after = fsm.exposure_guard.get_exposure_summary()
        assert summary_after["pending_orders_count"] == 1
        assert summary_after["pending_usd"] == "200.000"

    def test_market_order_requires_price_ref(self, fsm, config):
        """Test that MARKET orders require price_ref (fail-closed)."""
        # Setup portfolio
        portfolio_msg = Message(
            op="EVT",
            verb="PORTFOLIO_STATE_UPDATED",
            src="position_tracking",
            dst="execution_position",
            rid="test_rid_5",
            pld={"equity_free_usdt": "5000.0", "positions": []},
        )
        fsm.handle(portfolio_msg)

        # Try MARKET order without price_ref
        open_msg = Message(
            op="CMD",
            verb="OPEN",
            src="decision_making",
            dst="execution_position",
            rid="test_rid_6",
            pld={
                "symbol": "BTCUSDT",
                "side": "BUY",
                "qty": "0.01",
                "order_type": "MARKET",
                # Missing price_ref
            },
        )

        result = fsm.handle(open_msg)

        # Should be rejected with NO_PRICE_REF
        assert result is not None
        assert result.op == "ERR"
        assert result.verb == "OPEN"
        assert result.why == "NO_PRICE_REF"
        assert result.pld["reason"] == "MARKET order requires price_ref"
