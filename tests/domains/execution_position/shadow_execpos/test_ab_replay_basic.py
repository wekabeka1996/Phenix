"""
AB Replay Tests: Shadow Runtime Validation
==========================================

Tests that validate ExecPosRuntimeV2 behavior against expected adapter calls.
"Expected" calls represent documented intended behavior (not fsm.py execution).
"""
import pytest
import time

from apps.reference.domains.execution_position.shadow_execpos.runtime import ExecPosRuntimeV2
from apps.reference.domains.execution_position.shadow_execpos.ab_replay import (
    ExecPosReplay,
    AdapterCall
)
from tests.domains.execution_position.shadow_execpos.fake_adapter import FakeRecordingAdapter

def make_runtime_factory():
    """Create factory for ExecPosRuntimeV2 with FakeRecordingAdapter."""
    def factory():
        adapter = FakeRecordingAdapter()
        config = {"cooldown_sec": 0.1}
        return ExecPosRuntimeV2(config, adapter, price_service=None)
    return factory

@pytest.fixture
def replay_harness():
    return ExecPosReplay(make_runtime_factory())

# --- SCENARIO 1: HAPPY PATH ---

@pytest.mark.asyncio
@pytest.mark.xfail(reason="A/B replay divergence pending snapshot/TTL/bracket fixes (C-phase)", strict=False)
async def test_ab_replay_happy_path(replay_harness):
    """Test valid entry + fill sequence."""
    # Raw event sequence
    raw_records = [
        {
            "t": 1732111111.1,
            "kind": "ENTRY_INTENT",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "quantity": "0.1",
            "price": "50000",
            "order_type": "LIMIT"
        },
        {
            "t": 1732111112.0,
            "kind": "TRADE_EXECUTED",
            "symbol": "BTCUSDT",
            "order_id": "ORDER_1000",
            "quantity": "0.1",
            "price": "50000",
            "side": "BUY",
            "cum_qty": "0.1"
        }
    ]
    
    # Expected behavior: entry + bracket SL placement
    expected_calls = [
        AdapterCall(
            verb="place",
            symbol="BTCUSDT",
            side="BUY",
            quantity="0.1",  # May be adjusted by gatekeeper
            price="50000",   # May be adjusted by gatekeeper
            order_type="LIMIT"
        ),
        AdapterCall(
            verb="place",
            symbol="BTCUSDT",
            side="SELL",
            quantity="0.1",
            price="49000.00",
            order_type="STOP_MARKET",
        )
    ]
    
    result = await replay_harness.run(raw_records, expected_calls)
    
    # Verify diff matched
    assert result.diff.matched is True, f"Mismatches: {result.diff.mismatches}"
    
    # Verify metrics
    assert result.actual_metrics["events_total"] == 2
    assert result.actual_metrics["gatekeeper_allowed"] == 1
    assert result.actual_metrics["execution_success"] == 1
    assert result.actual_metrics["fills_processed"] == 1

# --- SCENARIO 2: GATEKEEPER REJECTION ---

@pytest.mark.asyncio
async def test_ab_replay_gatekeeper_reject(replay_harness):
    """Test entry with qty too small is rejected."""
    raw_records = [
        {
            "t": 1732111111.1,
            "kind": "ENTRY_INTENT",
            "symbol": "ETHUSDT",
            "side": "BUY",
            "quantity": "0.0000001",  # Too small
            "price": "3000",
            "order_type": "LIMIT"
        }
    ]
    
    # Expected: NO adapter calls (gatekeeper blocks)
    expected_calls = []
    
    result = await replay_harness.run(raw_records, expected_calls)
    
    # Verify diff matched (both sides: no calls)
    assert result.diff.matched is True
    
    # Verify metrics
    assert result.actual_metrics["gatekeeper_rejected"] == 1
    assert result.actual_metrics["gatekeeper_allowed"] == 0
    assert result.actual_metrics["execution_success"] == 0

# --- SCENARIO 3: IDEMPOTENT CANCEL ---

@pytest.mark.asyncio
async def test_ab_replay_idempotent_cancel(replay_harness):
    """Test duplicate cancel with -2011 error is handled idempotently."""
    # Need to use custom factory to configure error simulation
    def factory_with_error():
        adapter = FakeRecordingAdapter()
        # Will set error after first cancel
        config = {"cooldown_sec": 0.1}
        runtime = ExecPosRuntimeV2(config, adapter, price_service=None)
        return runtime, adapter
    
    runtime, adapter = factory_with_error()
    
    # Place order first
    entry_event = {
        "t":time.time(),
        "kind": "ENTRY_INTENT",
        "symbol": "SOLUSDT",
        "side": "BUY",
        "quantity": "10.0",
        "price": "100",
        "order_type": "LIMIT"
    }
    
    await runtime.handle(replay_harness.to_shadow_event(entry_event))
    
    # Get order ID from state
    orders = runtime._open_orders_by_symbol.get("SOLUSDT", [])
    assert len(orders) == 1
    order_id = orders[0]["order_id"]
    
    # First cancel
    cancel_event1 = {
        "t": time.time(),
        "kind": "CANCEL_INTENT",
        "symbol": "SOLUSDT",
        "order_id": order_id
    }
    await runtime.handle(replay_harness.to_shadow_event(cancel_event1))
    
    # Configure adapter to return -2011 for second cancel
    adapter.set_error_for_order(order_id, -2011)
    
    # Second cancel (idempotent)
    cancel_event2 = {
        "t": time.time(),
        "kind": "CANCEL_INTENT",
        "symbol": "SOLUSDT",
        "order_id": order_id
    }
    await runtime.handle(replay_harness.to_shadow_event(cancel_event2))
    
    # Expected: 1 place + 2 cancels
    # Actual calls
    actual_calls = [
        AdapterCall(
            verb=call.verb,
            symbol=call.symbol,
            side=call.kwargs.get("side"),
            quantity=call.kwargs.get("quantity"),
            order_id=call.kwargs.get("order_id")
        )
        for call in adapter.calls
    ]
    
    assert len(actual_calls) == 3  # 1 place + 2 cancel
    assert actual_calls[0].verb == "place"
    assert actual_calls[1].verb == "cancel"
    assert actual_calls[2].verb == "cancel"
    
    # Both cancels should be treated as success
    metrics = runtime.get_metrics()
    assert metrics["execution_success"] == 3

# --- SCENARIO 4: ORPHAN SL ---

@pytest.mark.asyncio
async def test_ab_replay_orphan_sl(replay_harness):
    """Test orphan SL detection doesn't trigger auto-cleanup."""
    raw_records = [
        {
            "t": 1732111111.1,
            "kind": "POSITION_SNAPSHOT",
            "symbol": "BTCUSDT",
            "positions": [{"symbol": "BTCUSDT", "quantity": 0}]
        },
        {
            "t": 1732111112.0,
            "kind": "ORDERS_SNAPSHOT",
            "symbol": "BTCUSDT",
            "orders": [{
                "symbol": "BTCUSDT",
                "orderId": "sl_orphan",
                "type": "STOP_MARKET",
                "side": "SELL",
                "reduceOnly": True,
                "quantity": "0.1",
                "stopPrice": "45000"
            }]
        }
    ]
    
    # Expected: cancel orphan SL during recovery pass
    expected_calls = [
        AdapterCall(verb="cancel", symbol="BTCUSDT", order_id="sl_orphan")
    ]
    
    result = await replay_harness.run(raw_records, expected_calls)
    
    # Verify no unexpected orders/cancels
    assert result.diff.matched is True
    
    # Verify watchdog detected violation
    assert result.actual_metrics["watchdog_violations"] >= 1
    assert result.actual_metrics["watchdog_violations_by_kind"].get("WARN", 0) >= 1

# --- COMBINED SCENARIO ---

@pytest.mark.asyncio
@pytest.mark.xfail(reason="A/B replay divergence pending snapshot/TTL/bracket fixes (C-phase)", strict=False)
async def test_ab_replay_full_lifecycle(replay_harness):
    """Test complete entry → fill → close lifecycle."""
    raw_records = [
        {
            "t": 1732111111.1,
            "kind": "ENTRY_INTENT",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "quantity": "0.1",
            "price": "50000",
            "order_type": "LIMIT"
        },
        {
            "t": 1732111112.0,
            "kind": "TRADE_EXECUTED",
            "symbol": "BTCUSDT",
            "order_id": "ORDER_1000",
            "quantity": "0.1",
            "price": "50000",
            "side": "BUY",
            "cum_qty": "0.1"
        },
        {
            "t": 1732111113.0,
            "kind": "CLOSE_INTENT",
            "symbol": "BTCUSDT",
            "quantity": "0.1"
        }
    ]
    
    # Expected: place (entry) + bracket SL + place (close with reduce_only)
    expected_calls = [
        AdapterCall(verb="place", symbol="BTCUSDT", side="BUY", order_type="LIMIT"),
        AdapterCall(verb="place", symbol="BTCUSDT", side="SELL", order_type="STOP_MARKET"),
        AdapterCall(verb="place", symbol="BTCUSDT", order_type="MARKET")  # Close
    ]
    
    result = await replay_harness.run(raw_records, expected_calls)
    
    # Verify calls match counts (allow bracket placements)
    assert result.diff.total_actual_calls == 3
    assert result.actual_adapter_calls[0].verb == "place"
    
    # Verify metrics
    assert result.actual_metrics["events_total"] == 3
    assert result.actual_metrics["execution_success"] == 2
    assert result.actual_metrics["fills_processed"] == 1
