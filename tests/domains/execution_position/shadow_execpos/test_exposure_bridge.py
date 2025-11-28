"""
Unit tests for ExposureBridge
==============================

Tests exposure bridge with mocked emit function to verify:
- EXEC_POS_EXPOSURE_UPDATED events are emitted correctly
- Direction normalization (LONG/SHORT/FLAT)
- Exposure calculation (position_size * entry_price)
- Fail-closed behavior (emission failures don't crash)
"""
import pytest
from typing import Any, Dict, List

from apps.reference.domains.execution_position.shadow_execpos.exposure_bridge import ExposureBridge
from apps.reference.domains.execution_position.contracts import EVT_EXEC_POS_EXPOSURE_UPDATED


class MockEmitFn:
    """Mock emit function that collects emitted events."""

    def __init__(self):
        self.events: List[Dict[str, Any]] = []
        self.should_fail = False

    def __call__(self, event_kind: str, payload: Dict[str, Any]) -> None:
        if self.should_fail:
            raise RuntimeError("Simulated emit failure")
        # Reconstruct event for verification
        self.events.append({
            "kind": event_kind,
            "source": "execution_position_v2",
            "payload": payload
        })


def test_emit_exposure_update_long():
    """Test emitting exposure update for LONG position."""
    mock_emit = MockEmitFn()
    bridge = ExposureBridge(emit_fn=mock_emit)

    position_state = {
        "symbol": "BTCUSDT",
        "position_size": "2.5",
        "qty": "2.5",
        "entry_price": "50000.0",
        "avg_price": "50000.0",
        "direction": "LONG",
        "leverage": 2,
        "realized_pnl": "100.0",
        "unrealized_pnl": "200.0",
    }

    result = bridge.emit_exposure_update(position_state)

    assert result is True
    assert len(mock_emit.events) == 1

    event = mock_emit.events[0]
    assert event["kind"] == EVT_EXEC_POS_EXPOSURE_UPDATED
    assert event["source"] == "execution_position_v2"

    payload = event["payload"]
    assert payload["symbol"] == "BTCUSDT"
    assert payload["net_position_size"] == "2.5"
    assert payload["direction"] == "LONG"
    assert payload["exposure_usdt"] == "125000.00"  # 2.5 * 50000
    assert payload["leverage"] == 2
    assert payload["realized_pnl"] == "100.0"
    assert payload["unrealized_pnl"] == "200.0"
    assert "update_time" in payload


def test_emit_exposure_update_short():
    """Test emitting exposure update for SHORT position."""
    mock_emit = MockEmitFn()
    bridge = ExposureBridge(emit_fn=mock_emit)

    position_state = {
        "symbol": "ETHUSDT",
        "position_size": "-10.0",
        "entry_price": "3000.0",
        "side": "SHORT",
    }

    result = bridge.emit_exposure_update(position_state)

    assert result is True
    payload = mock_emit.events[0]["payload"]
    assert payload["direction"] == "SHORT"
    assert payload["net_position_size"] == "-10.0"
    assert payload["exposure_usdt"] == "30000.00"  # abs(-10 * 3000)


def test_emit_exposure_update_flat():
    """Test emitting exposure update for FLAT position (closed)."""
    mock_emit = MockEmitFn()
    bridge = ExposureBridge(emit_fn=mock_emit)

    position_state = {
        "symbol": "SOLUSDT",
        "position_size": "0",
        "qty": "0",
        "avg_price": "0",
        "direction": "FLAT",
    }

    result = bridge.emit_exposure_update(position_state)

    assert result is True
    payload = mock_emit.events[0]["payload"]
    assert payload["direction"] == "FLAT"
    assert payload["net_position_size"] == "0"
    assert payload["exposure_usdt"] == "0"


def test_emit_exposure_update_scale_in():
    """Test emitting exposure update after scaling in (position increase)."""
    mock_emit = MockEmitFn()
    bridge = ExposureBridge(emit_fn=mock_emit)

    # Original position: 1.0 BTC @ 50000
    # Scale in: +0.5 BTC @ 51000
    # New position: 1.5 BTC @ ~50333 avg
    position_state = {
        "symbol": "BTCUSDT",
        "position_size": "1.5",
        "entry_price": "50333.0",
        "direction": "LONG",
    }

    result = bridge.emit_exposure_update(position_state)

    assert result is True
    payload = mock_emit.events[0]["payload"]
    assert payload["net_position_size"] == "1.5"
    assert float(payload["exposure_usdt"]) > 75000  # 1.5 * 50333


def test_emit_exposure_update_partial_close():
    """Test emitting exposure update after partial close (position decrease)."""
    mock_emit = MockEmitFn()
    bridge = ExposureBridge(emit_fn=mock_emit)

    # Original position: 2.0 ETH @ 3000
    # Partial close: -0.5 ETH
    # New position: 1.5 ETH @ 3000
    position_state = {
        "symbol": "ETHUSDT",
        "position_size": "1.5",
        "entry_price": "3000.0",
        "direction": "LONG",
        "realized_pnl": "50.0",  # Profit from partial close
    }

    result = bridge.emit_exposure_update(position_state)

    assert result is True
    payload = mock_emit.events[0]["payload"]
    assert payload["net_position_size"] == "1.5"
    assert payload["exposure_usdt"] == "4500.00"  # 1.5 * 3000
    assert payload["realized_pnl"] == "50.0"


def test_direction_normalization():
    """Test direction normalization from various formats."""
    mock_emit = MockEmitFn()
    bridge = ExposureBridge(emit_fn=mock_emit)

    # Test lowercase -> uppercase
    bridge.emit_exposure_update({"symbol": "BTC", "position_size": "1", "side": "long"})
    assert mock_emit.events[-1]["payload"]["direction"] == "LONG"

    # Test inferred from positive position_size
    bridge.emit_exposure_update({"symbol": "ETH", "position_size": "5"})
    assert mock_emit.events[-1]["payload"]["direction"] == "LONG"

    # Test inferred from negative position_size
    bridge.emit_exposure_update({"symbol": "SOL", "position_size": "-10"})
    assert mock_emit.events[-1]["payload"]["direction"] == "SHORT"

    # Test inferred from zero position_size
    bridge.emit_exposure_update({"symbol": "ADA", "position_size": "0"})
    assert mock_emit.events[-1]["payload"]["direction"] == "FLAT"


def test_exposure_emit_failure_logged():
    """Test that exposure emit failure is logged and doesn't raise."""
    mock_emit = MockEmitFn()
    mock_emit.should_fail = True
    bridge = ExposureBridge(emit_fn=mock_emit)

    position_state = {
        "symbol": "BTCUSDT",
        "position_size": "1.0",
        "entry_price": "50000.0",
    }

    # Should not raise, just log and return False
    result = bridge.emit_exposure_update(position_state)

    assert result is False
    assert len(mock_emit.events) == 0  # No event emitted
    assert bridge.get_metrics()["emit_errors"] == 1


def test_exposure_bridge_metrics():
    """Test exposure bridge metrics tracking."""
    mock_emit = MockEmitFn()
    bridge = ExposureBridge(emit_fn=mock_emit)

    # Emit 3 exposure updates
    bridge.emit_exposure_update({"symbol": "BTC", "position_size": "1"})
    bridge.emit_exposure_update({"symbol": "ETH", "position_size": "10"})
    bridge.emit_exposure_update({"symbol": "SOL", "position_size": "0"})

    metrics = bridge.get_metrics()
    assert metrics["exposures_emitted"] == 3
    assert metrics["emit_errors"] == 0
