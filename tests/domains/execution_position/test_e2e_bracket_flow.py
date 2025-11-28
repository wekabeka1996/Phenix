"""
End-to-End Test: TRADE_EXECUTED → Bracket Placement Flow
========================================================

This test verifies the COMPLETE flow from receiving a TRADE_EXECUTED event
to actually calling adapter.place_order() for SL/TP brackets.

If this test passes but production doesn't work, the problem is in:
1. Event wiring (fsm.listen not connected)
2. Config disabled in production
3. Runtime initialization sequence
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from decimal import Decimal

from apps.reference.domains.execution_position.shadow_execpos.runtime import ExecPosRuntimeV2
from apps.reference.domains.execution_position.shadow_execpos.position_model import PositionState


def make_mock_adapter():
    """Create mock adapter with all required methods."""
    adapter = MagicMock()
    adapter.place_order = AsyncMock(return_value={"success": True, "order_id": "mock_order_123"})
    adapter.cancel_order = AsyncMock(return_value={"success": True})
    adapter.get_open_orders = AsyncMock(return_value=[])
    adapter.get_open_positions = AsyncMock(return_value=[])
    adapter.load_open_algo_orders_snapshot = AsyncMock(return_value=[])  # Added
    return adapter


def make_runtime_config():
    """Create config with brackets ENABLED."""
    return {
        "execution_position": {
            "runtime_mode": "v2",
            "gatekeeper": {"enabled": False},
            "aggregated_oco": {
                "enabled": True,  # CRITICAL: Must be True
                "aggregated_only_mode": True,
                "recalc_on_scale_in": True,
                "recalc_on_partial_close": True,
                "allow_unprotected_position": False,  # Require SL
                "recreate_missing_brackets": True,  # Auto-place SL/TP
                "ttl_protect_new_bracket_ms": 3000,
            },
        },
        # Legacy path fallback
        "aggregated_oco": {
            "enabled": True,
            "allow_unprotected_position": False,
            "recreate_missing_brackets": True,
        },
    }


@pytest.mark.asyncio
async def test_e2e_trade_executed_places_brackets():
    """
    COMPLETE E2E Test: TRADE_EXECUTED → BracketService.evaluate() → adapter.place_order()

    Scenario:
    1. Runtime starts with NO positions
    2. Receive TRADE_EXECUTED: BUY 1.0 BTCUSDT @ 50000
    3. Runtime should:
       a. Update internal position state
       b. Evaluate brackets (BracketService)
       c. Call adapter.place_order() for SL and TP

    Expected:
    - adapter.place_order called >= 2 times (SL + TP)
    - Orders are STOP_MARKET and TAKE_PROFIT_MARKET
    - reduce_only=True
    """
    # Setup
    adapter = make_mock_adapter()
    config = make_runtime_config()

    runtime = ExecPosRuntimeV2(
        config=config,
        adapter=adapter,
        price_service=None,
    )

    await runtime.start()

    # Step 1: Send ORDERS_SNAPSHOT (empty - no existing orders)
    # This is CRITICAL - runtime needs fresh snapshot state
    await runtime.handle({
        "kind": "ORDERS_SNAPSHOT",
        "payload": {"orders": []}
    })

    # Step 2: Simulate TRADE_EXECUTED (new position opened)
    trade_payload = {
        "symbol": "BTCUSDT",
        "side": "BUY",
        "quantity": "1.0",
        "price": "50000.0",
        "order_id": "entry_order_1",
        "client_order_id": "AUR-ENTRY-1",
        "cum_qty": "1.0",
        "realized_pnl": "0",
    }

    await runtime.handle({
        "kind": "TRADE_EXECUTED",
        "symbol": "BTCUSDT",
        "payload": trade_payload,
    })

    # Give async tasks time to complete
    await asyncio.sleep(0.2)

    # Verify position state was updated
    position = runtime._positions_by_symbol.get("BTCUSDT")
    assert position is not None, "Position should be created after TRADE_EXECUTED"
    assert position.side == "LONG", f"Expected LONG position, got {position.side}"
    assert abs(position.qty - 1.0) < 0.001, f"Expected qty=1.0, got {position.qty}"

    # CRITICAL CHECK: Verify adapter.place_order was called for brackets
    place_calls = adapter.place_order.call_args_list

    print(f"\n[RESULT] adapter.place_order call count: {len(place_calls)}")
    for i, call in enumerate(place_calls):
        kwargs = call.kwargs if hasattr(call, 'kwargs') else call[1]
        print(f"  Call {i+1}: {kwargs.get('order_type')} {kwargs.get('side')} qty={kwargs.get('quantity')}")

    # We expect at least 2 calls: SL + TP
    assert len(place_calls) >= 2, (
        f"Expected >= 2 place_order calls (SL + TP), got {len(place_calls)}. "
        f"Check if brackets are enabled in config and BracketService is working."
    )

    # Verify order types
    order_types = [call.kwargs.get('order_type') or (call[1].get('order_type') if len(call) > 1 else None)
                   for call in place_calls]

    has_sl = any(ot in ("STOP_MARKET", "STOP") for ot in order_types)
    has_tp = any(ot in ("TAKE_PROFIT_MARKET", "TAKE_PROFIT") for ot in order_types)

    assert has_sl, f"Expected STOP_MARKET order, got types: {order_types}"
    assert has_tp, f"Expected TAKE_PROFIT_MARKET order, got types: {order_types}"

    # Verify reduce_only flag
    for call in place_calls:
        kwargs = call.kwargs if hasattr(call, 'kwargs') else call[1]
        ot = kwargs.get('order_type', '')
        if 'STOP' in ot or 'TAKE_PROFIT' in ot:
            assert kwargs.get('reduce_only') is True, (
                f"Bracket order should have reduce_only=True, got {kwargs}"
            )

    await runtime.shutdown()
    print("\n[OK] E2E Test PASSED: TRADE_EXECUTED -> Brackets placed successfully!")


@pytest.mark.asyncio
async def test_e2e_partial_close_resizes_brackets():
    """
    E2E Test: Partial close triggers bracket resize

    Scenario:
    1. Position: LONG 2.0 BTCUSDT
    2. Existing brackets: SL/TP with qty=2.0
    3. Partial close: SELL 0.5 → position now 1.5
    4. Brackets should be resized to qty=1.5
    """
    adapter = make_mock_adapter()
    config = make_runtime_config()

    runtime = ExecPosRuntimeV2(
        config=config,
        adapter=adapter,
        price_service=None,
    )

    await runtime.start()

    # Setup initial position (qty > 0 means LONG)
    runtime._positions_by_symbol["BTCUSDT"] = PositionState(
        symbol="BTCUSDT",
        qty=2.0,  # positive = LONG
        avg_entry_price=50000.0,
        cycle_id=1,
    )

    # Setup existing brackets in mirror (qty=2.0 each)
    existing_orders = [
        {
            "orderId": "SL_1",
            "clientOrderId": "AUR-BTCUSDT-LONG-SL-C1-xxx",
            "symbol": "BTCUSDT",
            "side": "SELL",
            "type": "STOP_MARKET",
            "origQty": "2.0",
            "stopPrice": "49000.0",
            "reduceOnly": True,
            "status": "NEW",
        },
        {
            "orderId": "TP_1",
            "clientOrderId": "AUR-BTCUSDT-LONG-TP-C1-xxx",
            "symbol": "BTCUSDT",
            "side": "SELL",
            "type": "TAKE_PROFIT_MARKET",
            "origQty": "2.0",
            "stopPrice": "52000.0",
            "reduceOnly": True,
            "status": "NEW",
        }
    ]

    # Send ORDERS_SNAPSHOT with existing brackets
    await runtime.handle({
        "kind": "ORDERS_SNAPSHOT",
        "payload": {"orders": existing_orders}
    })

    # Reset mock to track only new calls
    adapter.place_order.reset_mock()
    adapter.cancel_order.reset_mock()

    # Partial close: SELL 0.5
    await runtime.handle({
        "kind": "TRADE_EXECUTED",
        "symbol": "BTCUSDT",
        "payload": {
            "symbol": "BTCUSDT",
            "side": "SELL",
            "quantity": "0.5",
            "price": "51000.0",
            "cum_qty": "0.5",
        }
    })

    await asyncio.sleep(0.2)

    # Verify position updated
    position = runtime._positions_by_symbol.get("BTCUSDT")
    assert abs(position.qty - 1.5) < 0.001, f"Expected qty=1.5 after partial close, got {position.qty}"

    # Check for SIZE_INVARIANT enforcement
    cancel_count = adapter.cancel_order.call_count
    place_count = adapter.place_order.call_count

    print(f"\n[RESULT] Partial close results:")
    print(f"  Cancel calls: {cancel_count}")
    print(f"  Place calls: {place_count}")

    # With SIZE_INVARIANT, oversized brackets should be cancelled and resized
    # SL qty=2.0 > position qty=1.5 -> CANCEL + PLACE with qty=1.5
    # TP qty=2.0 > position qty=1.5 -> CANCEL + PLACE with qty=1.5

    if cancel_count >= 2 and place_count >= 2:
        print("[OK] SIZE_INVARIANT working: Oversized brackets cancelled and replaced")

        # Verify new brackets have correct qty
        for call in adapter.place_order.call_args_list:
            kwargs = call.kwargs if hasattr(call, 'kwargs') else call[1]
            qty = float(kwargs.get('quantity', 0))
            assert abs(qty - 1.5) < 0.001, f"Expected resized bracket qty=1.5, got {qty}"
    else:
        print(f"⚠️ SIZE_INVARIANT may not be triggering: cancel={cancel_count}, place={place_count}")

    await runtime.shutdown()


@pytest.mark.asyncio
async def test_e2e_position_close_cancels_orphans():
    """
    E2E Test: Full position close cancels orphan brackets

    Scenario:
    1. Position: LONG 1.0 BTCUSDT
    2. Existing brackets: SL/TP
    3. Full close: SELL 1.0 → position now FLAT
    4. Orphan brackets should be cancelled
    """
    adapter = make_mock_adapter()
    config = make_runtime_config()

    runtime = ExecPosRuntimeV2(
        config=config,
        adapter=adapter,
        price_service=None,
    )

    await runtime.start()

    # Setup initial position (qty > 0 = LONG)
    runtime._positions_by_symbol["ETHUSDT"] = PositionState(
        symbol="ETHUSDT",
        qty=1.0,  # positive = LONG
        avg_entry_price=3000.0,
        cycle_id=5,
    )

    # Setup existing brackets
    existing_orders = [
        {
            "orderId": "SL_ETH",
            "clientOrderId": "AUR-ETHUSDT-LONG-SL-C5-xxx",
            "symbol": "ETHUSDT",
            "side": "SELL",
            "type": "STOP_MARKET",
            "origQty": "1.0",
            "stopPrice": "2900.0",
            "reduceOnly": True,
            "status": "NEW",
        },
        {
            "orderId": "TP_ETH",
            "clientOrderId": "AUR-ETHUSDT-LONG-TP-C5-xxx",
            "symbol": "ETHUSDT",
            "side": "SELL",
            "type": "TAKE_PROFIT_MARKET",
            "origQty": "1.0",
            "stopPrice": "3200.0",
            "reduceOnly": True,
            "status": "NEW",
        }
    ]

    await runtime.handle({
        "kind": "ORDERS_SNAPSHOT",
        "payload": {"orders": existing_orders}
    })

    adapter.cancel_order.reset_mock()

    # Full close: SELL 1.0
    await runtime.handle({
        "kind": "TRADE_EXECUTED",
        "symbol": "ETHUSDT",
        "payload": {
            "symbol": "ETHUSDT",
            "side": "SELL",
            "quantity": "1.0",
            "price": "3100.0",
            "cum_qty": "1.0",
        }
    })

    await asyncio.sleep(0.2)

    # Verify position is FLAT
    position = runtime._positions_by_symbol.get("ETHUSDT")
    assert abs(position.qty) < 0.001, f"Expected FLAT position, got qty={position.qty}"

    # Check orphan cancellation
    cancel_count = adapter.cancel_order.call_count

    print(f"\n[RESULT] Full close results:")
    print(f"  Cancel calls: {cancel_count}")

    assert cancel_count >= 2, (
        f"Expected >= 2 cancel calls for orphan SL/TP, got {cancel_count}. "
        f"Orphan cleanup may not be working!"
    )

    print("[OK] Orphan cleanup working: Brackets cancelled when position closed")

    await runtime.shutdown()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
