"""
Integration Tests for ExecPosRuntimeV2
======================================

Offline replay tests with synthetic events.
"""
import pytest
import asyncio
import time

from apps.reference.domains.execution_position.shadow_execpos.runtime import ExecPosRuntimeV2
from apps.reference.domains.execution_position.shadow_execpos.types import RuntimeEvent
from tests.domains.execution_position.shadow_execpos.fake_adapter import FakeRecordingAdapter

@pytest.fixture
def fake_adapter():
    return FakeRecordingAdapter()

@pytest.fixture
def fake_price_service():
    """Dummy price service for testing."""
    return None

@pytest.fixture
def runtime(fake_adapter, fake_price_service):
    config = {"cooldown_sec": 0.1}  # Short cooldown for tests
    return ExecPosRuntimeV2(config, fake_adapter, fake_price_service)

# --- SCENARIO 1: VALID ENTRY FLOW ---

@pytest.mark.asyncio
async def test_valid_entry_flow(runtime, fake_adapter):
    """Test entry request that passes gatekeeper and executes successfully."""
    event = RuntimeEvent(
        kind="ENTRY_INTENT",
        symbol="BTCUSDT",
        timestamp=time.time(),
        payload={
            "side": "BUY",
            "quantity": "0.1",
            "price": "50000",
            "order_type": "LIMIT"
        }
    )

    await runtime.handle(event)

    # Verify adapter was called
    assert len(fake_adapter.calls) == 1
    assert fake_adapter.calls[0].verb == "place"
    assert fake_adapter.calls[0].symbol == "BTCUSDT"

    # Verify metrics
    metrics = runtime.get_metrics()
    assert metrics["events_total"] == 1
    assert metrics["gatekeeper_allowed"] == 1
    assert metrics["execution_success"] == 1
    assert metrics["gatekeeper_rejected"] == 0

# --- SCENARIO 2: GATEKEEPER REJECTION ---

@pytest.mark.asyncio
async def test_gatekeeper_rejects_small_qty(runtime, fake_adapter):
    """Test entry with qty too small is rejected by gatekeeper."""
    event = RuntimeEvent(
        kind="ENTRY_INTENT",
        symbol="ETHUSDT",
        timestamp=time.time(),
        payload={
            "side": "BUY",
            "quantity": "0.0000001",  # Too small
            "price": "3000",
            "order_type": "LIMIT"
        }
    )

    await runtime.handle(event)

    # Verify adapter was NOT called
    assert len(fake_adapter.calls) == 0

    # Verify metrics
    metrics = runtime.get_metrics()
    assert metrics["gatekeeper_rejected"] == 1
    assert metrics["gatekeeper_allowed"] == 0
    assert metrics["execution_success"] == 0

# --- SCENARIO 3: ORPHAN SL DETECTION ---

@pytest.mark.asyncio
async def test_orphan_sl_detection(runtime):
    """Test watchdog detects orphan SL order (no position)."""
    # Hydrate with position qty=0 but SL order present
    runtime.hydrate({
        "positions": [{"symbol": "BTCUSDT", "qty": 0}],
        "orders": [{
            "symbol": "BTCUSDT",
            "orderId": "sl_orphan",
            "clientOrderId": "epv2_sBTCUSDT_c999_tSL_sSELL_q0.1_p45000",
            "type": "STOP_MARKET",
            "side": "SELL",
            "reduceOnly": True,
            "origQty": "0.1"
        }]
    })

    # Trigger watchdog via snapshot update
    event = RuntimeEvent(
        kind="ORDERS_SNAPSHOT",
        symbol="BTCUSDT",
        timestamp=time.time(),
        payload={
            "orders": [{
                "symbol": "BTCUSDT",
                "orderId": "sl_orphan",
                "clientOrderId": "epv2_sBTCUSDT_c999_tSL_sSELL_q0.1_p45000",
                "type": "STOP_MARKET",
                "side": "SELL",
                "reduceOnly": True,
                "quantity": "0.1",
                "stopPrice": "45000"
            }]
        }
    )

    await runtime.handle(event)

    # Trigger analysis (happens after state update)
    await runtime._run_watchdog_analysis()

    # Verify watchdog violation detected
    metrics = runtime.get_metrics()
    assert metrics["watchdog_violations"] >= 1

# --- SCENARIO 4: IDEMPOTENT CANCEL ---

@pytest.mark.asyncio
async def test_idempotent_cancel(runtime, fake_adapter):
    """Test duplicate cancel is handled idempotently."""
    # Place order first
    entry_event = RuntimeEvent(
        kind="ENTRY_INTENT",
        symbol="SOLUSDT",
        timestamp=time.time(),
        payload={
            "side": "BUY",
            "quantity": "10.0",
            "price": "100",
            "order_type": "LIMIT",
            "client_order_id": "test_client_oid_2"
        }
    )
    await runtime.handle(entry_event)

    # Get order ID from state
    refs = runtime.order_index.get_by_symbol("SOLUSDT")
    orders = [r.to_dict() for r in refs]
    assert len(orders) == 1
    order_id = orders[0]["order_id"]

    # First cancel
    cancel_event = RuntimeEvent(
        kind="CANCEL_INTENT",
        symbol="SOLUSDT",
        timestamp=time.time(),
        payload={"order_id": order_id}
    )
    await runtime.handle(cancel_event)

    # Configure adapter to return -2011 for second cancel
    fake_adapter.set_error_for_order(order_id, -2011)

    # Second cancel (should be idempotent)
    await runtime.handle(cancel_event)

    # Both cancels should succeed (idempotent)
    metrics = runtime.get_metrics()
    print(f"DEBUG: metrics={metrics}")
    assert metrics["execution_success"] == 3  # 1 place + 2 cancels

# --- SCENARIO 5: FILL PROCESSING WITH IDEMPOTENCY ---

@pytest.mark.asyncio
async def test_fill_idempotency(runtime):
    """Test duplicate fills are filtered by idempotency."""
    # First fill
    fill_event = RuntimeEvent(
        kind="TRADE_EXECUTED",
        symbol="BTCUSDT",
        timestamp=time.time(),
        payload={
            "order_id": "order_123",
            "quantity": "0.1",
            "price": "50000",
            "side": "BUY",
            "cum_qty": "0.1"
        }
    )
    await runtime.handle(fill_event)

    # Duplicate fill (same cum_qty)
    await runtime.handle(fill_event)

    # Verify metrics
    metrics = runtime.get_metrics()
    assert metrics["fills_processed"] == 1
    assert metrics["fills_duplicate"] == 1

    # Verify position updated only once
    pos = runtime._positions_by_symbol.get("BTCUSDT")
    assert pos is not None
    assert float(pos.qty) == 0.1

# --- SCENARIO 6: MISSING SL DETECTION ---

@pytest.mark.asyncio
async def test_missing_sl_detection(runtime):
    """Test watchdog detects position without SL."""
    # Simulate fill that opens position
    fill_event = RuntimeEvent(
        kind="TRADE_EXECUTED",
        symbol="ETHUSDT",
        timestamp=time.time(),
        payload={
            "order_id": "entry_order",
            "quantity": "1.0",
            "price": "3000",
            "side": "BUY",
            "cum_qty": "1.0"
        }
    )
    await runtime.handle(fill_event)

    # Update with empty orders snapshot (no SL)
    orders_event = RuntimeEvent(
        kind="ORDERS_SNAPSHOT",
        symbol="ETHUSDT",
        timestamp=time.time(),
        payload={"orders": []}
    )
    await runtime.handle(orders_event)

    # Verify watchdog detected violation
    metrics = runtime.get_metrics()
    assert metrics["watchdog_violations"] >= 1
    assert metrics["watchdog_violations_by_kind"].get("ALERT", 0) >= 1

# --- COMBINED SCENARIO ---

@pytest.mark.asyncio
async def test_complete_lifecycle(runtime, fake_adapter):
    """Test complete entry → fill → close lifecycle."""
    # Reset gatekeeper cooldown
    runtime.gatekeeper.reset_cooldown("BTCUSDT")

    # Entry
    entry_event = RuntimeEvent(
        kind="ENTRY_INTENT",
        symbol="BTCUSDT",
        timestamp=time.time(),
        payload={"side": "BUY", "quantity": "0.1", "price": "50000", "order_type": "LIMIT"}
    )
    await runtime.handle(entry_event)

    # Fill
    fill_event = RuntimeEvent(
        kind="TRADE_EXECUTED",
        symbol="BTCUSDT",
        timestamp=time.time(),
        payload={"order_id": "ORDER_1000", "quantity": "0.1", "price": "50000", "side": "BUY", "cum_qty": "0.1"}
    )
    await runtime.handle(fill_event)

    # Close
    close_event = RuntimeEvent(
        kind="CLOSE_INTENT",
        symbol="BTCUSDT",
        timestamp=time.time(),
        payload={"quantity": "0.1"}
    )
    await runtime.handle(close_event)

    # Verify full lifecycle
    metrics = runtime.get_metrics()
    assert metrics["events_total"] == 3
    assert metrics["execution_success"] == 2  # Entry + close
    assert metrics["fills_processed"] == 1

    # Verify adapter calls (entry + bracket placements + close)
    assert len(fake_adapter.calls) >= 2
    assert fake_adapter.calls[0].verb == "place"
    # Ensure a close/market reduce-only order exists
    assert any(call.kwargs.get("order_type") == "MARKET" and call.kwargs.get("reduce_only") for call in fake_adapter.calls)

# --- METRICS ---

@pytest.mark.asyncio
async def test_metrics_tracking(runtime):
    """Test metrics are tracked correctly."""
    metrics = runtime.get_metrics()

    # Initial state
    assert metrics["events_total"] == 0
    assert metrics["gatekeeper_allowed"] == 0
    assert metrics["positions_tracked"] == 0

    # After hydration
    runtime.hydrate({
        "positions": [{"symbol": "BTC USDT", "qty": "0.1"}],
        "orders": []
    })

    metrics = runtime.get_metrics()
    assert metrics["positions_tracked"] == 1
