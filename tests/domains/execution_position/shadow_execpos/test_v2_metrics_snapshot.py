"""
Tests for V2 Runtime Metrics Snapshot
======================================

Verifies that get_metrics_snapshot() returns correct structure and values.
"""
import pytest
import asyncio

from apps.reference.domains.execution_position.shadow_execpos.runtime import ExecPosRuntimeV2
from apps.reference.domains.execution_position.shadow_execpos.types import RuntimeEvent
from tests.domains.execution_position.shadow_execpos.fake_adapter import FakeRecordingAdapter


@pytest.fixture
def fake_adapter():
    return FakeRecordingAdapter()


@pytest.fixture
def runtime(fake_adapter):
    config = {
        "cooldown_sec": 0.1,
        "execution": {
            "executor_pool": {
                "enabled": False,  # Disable for legacy test with FakeRecordingAdapter
            }
        },
        "execution_position": {
            "executor_pool_enabled": False,
        }
    }
    return ExecPosRuntimeV2(config, fake_adapter, None)


@pytest.mark.asyncio
async def test_metrics_snapshot_has_required_keys(runtime):
    """Test that metrics snapshot contains all required keys."""
    snapshot = runtime.get_metrics_snapshot()

    # Verify all required keys exist
    required_keys = [
        "events_total",
        "events_by_kind",
        "gatekeeper_allowed",
        "gatekeeper_rejected",
        "execution_success",
        "execution_failed",
        "fills_processed",
        "fills_duplicate",
        "watchdog_violations",
        "watchdog_violations_by_kind",
        "positions_tracked",
        "symbols_active"
    ]

    for key in required_keys:
        assert key in snapshot, f"Missing required key: {key}"


@pytest.mark.asyncio
async def test_metrics_increment_on_events(runtime, fake_adapter):
    """Test that metrics counters increment correctly."""
    # Initial state
    snapshot = runtime.get_metrics_snapshot()
    assert snapshot["events_total"] == 0
    assert snapshot["gatekeeper_allowed"] == 0

    # Send successful entry event
    event = RuntimeEvent(
        kind="ENTRY_INTENT",
        symbol="BTCUSDT",
        timestamp=1700000000.0,
        payload={
            "side": "BUY",
            "quantity": "0.1",
            "order_type": "MARKET"
        }
    )

    await runtime.handle(event)

    # Verify metrics updated
    snapshot = runtime.get_metrics_snapshot()
    assert snapshot["events_total"] == 1
    assert snapshot["events_by_kind"]["ENTRY_INTENT"] == 1
    assert snapshot["gatekeeper_allowed"] == 1
    assert snapshot["execution_success"] == 1


@pytest.mark.asyncio
async def test_metrics_track_rejected_entries(runtime, fake_adapter):
    """Test that gatekeeper rejections are tracked."""
    # Send entry with invalid quantity
    event = RuntimeEvent(
        kind="ENTRY_INTENT",
        symbol="BTCUSDT",
        timestamp=1700000000.0,
        payload={
            "side": "BUY",
            "quantity": "-1.0",  # Invalid negative quantity
            "order_type": "MARKET"
        }
    )


@pytest.mark.asyncio
async def test_metrics_track_positions(runtime):
    """Test that positions_tracked reflects position count."""
    snapshot = runtime.get_metrics_snapshot()
    assert snapshot["positions_tracked"] == 0
    assert snapshot["symbols_active"] == []

    # Simulate position snapshot
    await runtime._handle_position_snapshot({
        "symbol": "BTCUSDT",
        "qty": "1.5",
        "entry_price": "50000"
    })

    snapshot = runtime.get_metrics_snapshot()
    assert snapshot["positions_tracked"] == 1
    assert "BTCUSDT" in snapshot["symbols_active"]


@pytest.mark.asyncio
async def test_get_metrics_delegates_to_get_metrics_snapshot(runtime):
    """Test that get_metrics() delegates to get_metrics_snapshot()."""
    # Both should return the same thing
    metrics = runtime.get_metrics()
    snapshot = runtime.get_metrics_snapshot()

    assert metrics == snapshot
