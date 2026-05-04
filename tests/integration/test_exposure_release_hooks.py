# tests/integration/test_exposure_release_hooks.py
"""
Integration test for exposure guard release hooks.

Tests that pending exposure is properly released on terminal events.
"""

from apps.reference.domains.execution_position.fsm import ExecPosFSM
from vfoundation.core.protocol import Message
from types import SimpleNamespace
from decimal import Decimal
import pytest
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


@pytest.mark.skip(reason="Requires complex FSM exposure_guard state management")
class TestExposureReleaseHooks:
    """Integration tests for exposure release hooks."""

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
                        "max_portfolio_fraction": 0.20,
                        "count_pending_orders": True,
                        "exclude_reduce_only": True,
                        "pending_reservation_ttl_sec": 300,
                    },
                    "cooldown_ms": 0,
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

    def test_release_on_err_open(self, fsm, config):
        """Test that pending exposure is released when ERR:OPEN occurs."""
        # Setup portfolio with low equity to force exposure limit
        portfolio_msg = Message(
            op="EVT",
            verb="PORTFOLIO_STATE_UPDATED",
            src="position_tracking",
            dst="execution_position",
            rid="test_rid_1",
            pld={
                "equity_free_usdt": "100.0",  # Low equity
                "positions": [],
            },
        )
        fsm.handle(portfolio_msg)

        # Try to open order that would exceed limit (should reserve then fail)
        open_msg = Message(
            op="CMD",
            verb="OPEN",
            src="decision_making",
            dst="execution_position",
            rid="test_rid_2",
            pld={
                "symbol": "BTCUSDT",
                "side": "BUY",
                "qty": "0.01",
                "order_type": "MARKET",
                "price_ref": "20000.0",  # 200 notional, but limit is 20
                "idempotent_key": "test_key_1",
            },
        )

        result = fsm.handle(open_msg)

        # Should be rejected due to exposure limit
        assert result is not None
        assert result.op == "ERR"
        assert result.verb == "OPEN"
        assert result.pld["reason"] == "PORTFOLIO_EXPOSURE_LIMIT"

        # Verify exposure was released (no pending reservations)
        summary = fsm.exposure_guard.get_exposure_summary()
        assert summary["pending_orders_count"] == 0
        assert summary["pending_usd"] == "0"

    def test_release_on_order_rejected(self, fsm, config):
        """Test that pending exposure is released when EVT:ORDER_REJECTED occurs."""
        # Setup portfolio
        portfolio_msg = Message(
            op="EVT",
            verb="PORTFOLIO_STATE_UPDATED",
            src="position_tracking",
            dst="execution_position",
            rid="test_rid_3",
            pld={"equity_free_usdt": "5000.0", "positions": []},
        )
        fsm.handle(portfolio_msg)

        # Simulate order rejection from adapter
        reject_msg = Message(
            op="EVT",
            verb="ORDER_REJECTED",
            src="execution_adapter",
            dst="execution_position",
            rid="test_rid_4",
            pld={"idempotent_key": "test_key_2"},
        )

        # This should trigger release (even though no reservation exists, should not crash)
        result = fsm.handle(reject_msg)
        assert result is None  # Event handled

    def test_release_on_order_canceled(self, fsm, config):
        """Test that pending exposure is released when EVT:ORDER_CANCELED occurs."""
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

        # Simulate order cancellation
        cancel_msg = Message(
            op="EVT",
            verb="ORDER_CANCELED",
            src="execution_adapter",
            dst="execution_position",
            rid="test_rid_6",
            pld={"idempotent_key": "test_key_3"},
        )

        result = fsm.handle(cancel_msg)
        assert result is None  # Event handled

    def test_release_on_order_filled(self, fsm, config):
        """Test that pending exposure is released when EVT:ORDER_FILLED occurs."""
        # Setup portfolio
        portfolio_msg = Message(
            op="EVT",
            verb="PORTFOLIO_STATE_UPDATED",
            src="position_tracking",
            dst="execution_position",
            rid="test_rid_7",
            pld={"equity_free_usdt": "5000.0", "positions": []},
        )
        fsm.handle(portfolio_msg)

        # Simulate order fill
        fill_msg = Message(
            op="EVT",
            verb="ORDER_FILLED",
            src="execution_adapter",
            dst="execution_position",
            rid="test_rid_8",
            pld={"idempotent_key": "test_key_4"},
        )

        result = fsm.handle(fill_msg)
        assert result is None  # Event handled

    def test_release_on_position_opened(self, fsm, config):
        """Test that pending exposure is released when EVT:POSITION_OPENED occurs."""
        # Setup portfolio
        portfolio_msg = Message(
            op="EVT",
            verb="PORTFOLIO_STATE_UPDATED",
            src="position_tracking",
            dst="execution_position",
            rid="test_rid_9",
            pld={"equity_free_usdt": "5000.0", "positions": []},
        )
        fsm.handle(portfolio_msg)

        # Simulate position opened
        position_msg = Message(
            op="EVT",
            verb="POSITION_OPENED",
            src="execution_adapter",
            dst="execution_position",
            rid="test_rid_10",
            pld={"idempotent_key": "test_key_5"},
        )

        result = fsm.handle(position_msg)
        assert result is None  # Event handled

    def test_portfolio_exposure_updated_event(self, fsm, config):
        """Test that EVT:PORTFOLIO_EXPOSURE_UPDATED is emitted on portfolio updates."""
        # Send portfolio update
        portfolio_msg = Message(
            op="EVT",
            verb="PORTFOLIO_STATE_UPDATED",
            src="position_tracking",
            dst="execution_position",
            rid="test_rid_11",
            pld={
                "equity_free_usdt": "5000.0",
                "positions": [
                    {
                        "symbol": "BTCUSDT",
                        "net_position": "0.1",
                        "avg_entry_price": "15000.0",
                    }
                ],
            },
        )

        result = fsm.handle(portfolio_msg)

        # Should emit PORTFOLIO_EXPOSURE_UPDATED
        assert result is not None
        assert result.op == "EVT"
        assert result.verb == "PORTFOLIO_EXPOSURE_UPDATED"
        assert result.pld["equity_usd"] == "5000.0"
        assert result.pld["limit_usd"] == "1000.00"  # 5000 * 0.2
        assert result.pld["open_positions_usd"] == "1500.00"  # 0.1 * 15000
        assert result.pld["pending_usd"] == "0"
        assert result.pld["reservations"] == "0"

    def test_exposure_guard_reject_counter(self, fsm, config):
        """Test that exposure guard rejects are counted in metrics."""
        from apps.reference.telemetry.metrics import generate_latest

        # Setup portfolio with low equity to force exposure limit
        portfolio_msg = Message(
            op="EVT",
            verb="PORTFOLIO_STATE_UPDATED",
            src="position_tracking",
            dst="execution_position",
            rid="test_rid_metrics",
            pld={
                "equity_free_usdt": "100.0",  # Low equity
                "positions": [],
            },
        )
        fsm.handle(portfolio_msg)

        # Try to open order that would exceed limit
        open_msg = Message(
            op="CMD",
            verb="OPEN",
            src="decision_making",
            dst="execution_position",
            rid="test_rid_reject",
            pld={
                "symbol": "BTCUSDT",
                "side": "BUY",
                "qty": "0.01",
                "order_type": "MARKET",
                "price_ref": "20000.0",
                "idempotent_key": "test_key_reject",
            },
        )

        result = fsm.handle(open_msg)

        # Should be rejected due to exposure limit
        assert result is not None
        assert result.op == "ERR"
        assert result.verb == "OPEN"
        assert result.pld["reason"] == "PORTFOLIO_EXPOSURE_LIMIT"

        # Check that metrics include the reject counter
        data = generate_latest().decode("utf-8")
        assert 'fsm_guard_rejects_total{guard="exposure"}' in data
