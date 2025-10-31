from apps.reference.domains.execution_position.simulated_adapter import (
    SimulatedExecutionAdapter,
)
from vfoundation.core.protocol import Message


def test_simulated_place_and_cancel_and_status():
    adapter = SimulatedExecutionAdapter(fsm=None, config={})
    dec = Message(
        op="DEC",
        verb="OPEN",
        src="t",
        dst="sim",
        rid="r1",
        pld={"symbol": "ETHUSDT", "qty": "0.5", "side": "BUY", "price": "100"},
    )
    res = adapter.place_order(dec)
    assert res["status"] == "ACCEPTED"
    assert res["exchange_order_id"].startswith("sim_")

    cancel_msg = Message(
        op="DEC",
        verb="CANCEL",
        src="t",
        dst="sim",
        rid="r2",
        pld={"exchange_order_id": res["exchange_order_id"]},
    )
    cres = adapter.cancel_order(cancel_msg)
    assert cres["status"] == "ACCEPTED"
    assert cres["exchange_order_id"] == res["exchange_order_id"]

    assert adapter.get_status() == "CONNECTED"


"""
Unit tests for SimulatedExecutionAdapter.

Tests the mock execution adapter used in shadow mode for validating
execution flow without making real exchange calls.
"""
import pytest
import sys
from pathlib import Path
from decimal import Decimal
from unittest.mock import MagicMock

# Add apps to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "apps"))

from vfoundation.core.protocol import Message


@pytest.fixture
def mock_fsm():
    """Mock FSM for adapter."""
    return MagicMock()


@pytest.fixture
def mock_config():
    """Mock config for adapter."""
    return {
        "trading_mode": "testnet",
        "binance_api": {
            "testnet": {
                "api_key": "test_key",
                "api_secret": "test_secret",
                "rest_url": "https://testnet.binance.vision",
            }
        },
    }


@pytest.fixture
def adapter(mock_fsm, mock_config):
    """Fixture providing a SimulatedExecutionAdapter instance."""
    from apps.reference.domains.execution_position.simulated_adapter import (
        SimulatedExecutionAdapter,
    )

    return SimulatedExecutionAdapter(fsm=mock_fsm, config=mock_config)


def test_simulated_adapter_get_status(adapter):
    """Test that get_status always returns CONNECTED."""
    status = adapter.get_status()
    assert status == "CONNECTED"


def test_simulated_adapter_place_order_basic(adapter):
    """Test basic place_order returns ACCEPTED with mock order ID."""
    dec_msg = Message(
        op="DEC",
        verb="OPEN",
        src="decision_making",
        dst="execution_position",
        rid="test-place-001",
        why="test order placement",
        pld={"symbol": "BTCUSDT", "side": "BUY", "qty": "0.001", "price": "50000.00"},
    )

    result = adapter.place_order(dec_msg)

    assert result["status"] == "ACCEPTED"
    assert result["exchange_order_id"].startswith("sim_")
    assert result["filled_qty"] == "0.001"
    assert "message" in result
    assert "timestamp" in result


def test_simulated_adapter_place_order_precision_preservation(adapter):
    """Test that decimal precision is preserved in filled_qty."""
    dec_msg = Message(
        op="DEC",
        verb="OPEN",
        src="decision_making",
        dst="execution_position",
        rid="test-precision-001",
        why="test precision",
        pld={
            "symbol": "ETHUSDT",
            "side": "SELL",
            "qty": "0.123456789",
            "price": "3000.00",
        },
    )

    result = adapter.place_order(dec_msg)

    # Verify Decimal precision preserved
    filled_decimal = Decimal(result["filled_qty"])
    expected_decimal = Decimal("0.123456789")
    assert filled_decimal == expected_decimal


def test_simulated_adapter_cancel_order(adapter):
    """Test cancel_order returns ACCEPTED with echoed order ID."""
    dec_msg = Message(
        op="DEC",
        verb="CANCEL",
        src="execution_position",
        dst="execution_position",
        rid="test-cancel-001",
        why="test order cancellation",
        pld={"exchange_order_id": "sim_1234567890", "symbol": "BTCUSDT"},
    )

    result = adapter.cancel_order(dec_msg)

    assert result["status"] == "ACCEPTED"
    assert result["exchange_order_id"] == "sim_1234567890"
    assert result["filled_qty"] == "0.0"
    assert "message" in result
    assert "timestamp" in result


def test_simulated_adapter_unique_order_ids(adapter):
    """Test that consecutive place_order calls generate unique order IDs."""
    import time

    dec_msg = Message(
        op="DEC",
        verb="OPEN",
        src="decision_making",
        dst="execution_position",
        rid="test-unique-001",
        why="test unique IDs",
        pld={"symbol": "BTCUSDT", "side": "BUY", "qty": "0.01", "price": "50000.00"},
    )

    result1 = adapter.place_order(dec_msg)
    time.sleep(0.001)  # Ensure timestamp difference
    result2 = adapter.place_order(dec_msg)

    # Order IDs should be different (timestamp-based)
    assert result1["exchange_order_id"] != result2["exchange_order_id"]


def test_simulated_adapter_handles_missing_fields_gracefully(adapter):
    """Test adapter handles messages with missing optional fields."""
    dec_msg = Message(
        op="DEC",
        verb="OPEN",
        src="decision_making",
        dst="execution_position",
        rid="test-missing-001",
        why="test missing fields",
        pld={},  # Empty payload
    )

    # Should not raise, uses defaults
    result = adapter.place_order(dec_msg)

    assert result["status"] == "ACCEPTED"
    assert "exchange_order_id" in result
    assert result["filled_qty"] == "0.0"  # Default qty


def test_simulated_adapter_integration_with_fsm(adapter):
    """Integration test: ExecPosFSM can inject SimulatedExecutionAdapter."""
    from apps.reference.domains.execution_position.fsm import ExecPosFSM

    # Use proper config dict instead of MagicMock
    config = {
        "domain_fsm_settings": {
            "execution_position": {
                "timeout_ms": 5000,
                "hot_path_max_ms": 100,
                "fail_closed": True,
            }
        },
        "trading": {
            "execution": {
                "exposure": {
                    "max_portfolio_fraction": "0.20",
                    "pending_ttl_sec": 90,
                    "post_fill_hold_ttl_sec": 5,
                    "positions_stale_ttl_sec": 5,
                }
            }
        }
    }

    # Create FSM in shadow mode (no real adapter created)
    fsm = ExecPosFSM(config=config, fsm=None, shadow_mode=True)

    # Manually inject simulated adapter
    fsm.adapter = adapter

    # Verify FSM has adapter attached
    assert fsm.adapter is adapter
    assert fsm.adapter.get_status() == "CONNECTED"


def test_simulated_adapter_cancel_with_empty_order_id(adapter):
    """Test cancel_order handles empty/missing order ID gracefully."""
    dec_msg = Message(
        op="DEC",
        verb="CANCEL",
        src="execution_position",
        dst="execution_position",
        rid="test-cancel-empty-001",
        why="test empty order ID",
        pld={"symbol": "BTCUSDT"},  # Missing exchange_order_id
    )

    result = adapter.cancel_order(dec_msg)

    # Should use default "UNKNOWN"
    assert result["status"] == "ACCEPTED"
    assert result["exchange_order_id"] == "UNKNOWN"
