import asyncio
from typing import Any, Dict, List, Optional
import pytest

from apps.reference.domains.execution_position.fsm import ExecPosFSM
from vfoundation.core.fsm_emit_compat import Message


class FakeAdapter:
    """Minimal async adapter stub to drive orphan cleanup tests."""

    def __init__(self):
        self._positions: List[Dict[str, Any]] = []
        self._open_orders: List[Dict[str, Any]] = []
        self.cancel_calls: List[tuple[str, str]] = []  # (symbol, orderId)
        self.cancel_side_effect: Optional[Exception] = None

    # --- Scenario controls ---
    def set_positions(self, positions: List[Dict[str, Any]]):
        self._positions = positions

    def set_open_orders(self, orders: List[Dict[str, Any]]):
        self._open_orders = orders

    def set_cancel_side_effect(self, exc: Optional[Exception]):
        self.cancel_side_effect = exc

    # --- Async API ---
    async def get_open_positions(self) -> List[Dict[str, Any]]:
        return self._positions

    async def get_open_orders(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        if symbol:
            return [o for o in self._open_orders if o.get("symbol") == symbol]
        return self._open_orders

    async def cancel_order(self, symbol: str, order_id: str) -> Dict[str, Any]:
        self.cancel_calls.append((symbol, order_id))
        if self.cancel_side_effect:
            raise self.cancel_side_effect
        return {"symbol": symbol, "orderId": order_id, "status": "CANCELED"}


@pytest.mark.asyncio
async def test_cleanup_orphans_when_no_position_cancels_reduce_only_orders():
    fsm = ExecPosFSM(config={}, fsm=None, shadow_mode=True)
    adapter = FakeAdapter()
    adapter.set_positions([])  # no positions at all
    adapter.set_open_orders([
        {"symbol": "BTCUSDT", "orderId": "1",
            "type": "STOP_MARKET", "closePosition": "true"},
        {"symbol": "BTCUSDT", "orderId": "2",
            "type": "TAKE_PROFIT_MARKET", "reduceOnly": "true"},
        {"symbol": "ETHUSDT", "orderId": "3",
            "type": "LIMIT", "reduceOnly": "true"},
        {"symbol": "BTCUSDT", "orderId": "4", "type": "LIMIT",
            "reduceOnly": "false"},  # should be ignored
    ])
    fsm.adapter = adapter
    # Initialize OrderGuardian for the test
    from apps.reference.services.order_guardian import OrderGuardian
    fsm.order_guardian = OrderGuardian(adapter)

    # Register the bracket orders in OrderGuardian so they are recognized as "ours"
    fsm.order_guardian.store.put("order:1", {
        "symbol": "BTCUSDT",
        "type": "STOP_MARKET",
        "reduce_only": True,
        "close_position": True,
        "parent_entry_id": None
    })
    fsm.order_guardian.store.put("order:2", {
        "symbol": "BTCUSDT",
        "type": "TAKE_PROFIT_MARKET",
        "reduce_only": True,
        "close_position": False,
        "parent_entry_id": None
    })
    fsm.order_guardian.store.put("order:3", {
        "symbol": "ETHUSDT",
        "type": "LIMIT",
        "reduce_only": True,
        "close_position": False,
        "parent_entry_id": None
    })
    # Order 4 is not registered, so it should be ignored

    await fsm.order_guardian.cleanup_orphans()

    # We expect orders 1,2,3 to be canceled; 4 ignored
    assert ("BTCUSDT", "1") in adapter.cancel_calls
    assert ("BTCUSDT", "2") in adapter.cancel_calls
    assert ("ETHUSDT", "3") in adapter.cancel_calls
    assert ("BTCUSDT", "4") not in adapter.cancel_calls


@pytest.mark.asyncio
async def test_cleanup_skips_when_position_exists():
    fsm = ExecPosFSM(config={}, fsm=None, shadow_mode=True)
    adapter = FakeAdapter()
    adapter.set_positions([
        {"symbol": "BTCUSDT", "positionAmt": "0.01"},  # has open position
    ])
    adapter.set_open_orders([
        {"symbol": "BTCUSDT", "orderId": "1",
            "type": "STOP_MARKET", "closePosition": "true"},
        {"symbol": "BTCUSDT", "orderId": "2",
            "type": "TAKE_PROFIT_MARKET", "reduceOnly": "true"},
    ])
    fsm.adapter = adapter
    # Initialize OrderGuardian for the test
    from apps.reference.services.order_guardian import OrderGuardian
    fsm.order_guardian = OrderGuardian(adapter)

    # Register the orders in OrderGuardian
    fsm.order_guardian.store.put("order:1", {
        "symbol": "BTCUSDT",
        "type": "STOP_MARKET",
        "reduce_only": False,
        "close_position": True,
        "parent_entry_id": None
    })
    fsm.order_guardian.store.put("order:2", {
        "symbol": "BTCUSDT",
        "type": "TAKE_PROFIT_MARKET",
        "reduce_only": True,
        "close_position": False,
        "parent_entry_id": None
    })

    await fsm.order_guardian.cleanup_orphans()

    # Since position exists, no orphan cleanup for BTCUSDT
    assert adapter.cancel_calls == []


@pytest.mark.asyncio
async def test_cleanup_only_target_symbol():
    fsm = ExecPosFSM(config={}, fsm=None, shadow_mode=True)
    adapter = FakeAdapter()
    adapter.set_positions([])
    adapter.set_open_orders([
        {"symbol": "BTCUSDT", "orderId": "1",
            "type": "STOP_MARKET", "closePosition": "true"},
        {"symbol": "ETHUSDT", "orderId": "2",
            "type": "TAKE_PROFIT_MARKET", "reduceOnly": "true"},
    ])
    fsm.adapter = adapter
    # Initialize OrderGuardian for the test
    from apps.reference.services.order_guardian import OrderGuardian
    fsm.order_guardian = OrderGuardian(adapter)

    # Register the orders in OrderGuardian
    fsm.order_guardian.store.put("order:1", {
        "symbol": "BTCUSDT",
        "type": "STOP_MARKET",
        "reduce_only": False,
        "close_position": True,
        "parent_entry_id": None
    })
    fsm.order_guardian.store.put("order:2", {
        "symbol": "ETHUSDT",
        "type": "TAKE_PROFIT_MARKET",
        "reduce_only": True,
        "close_position": False,
        "parent_entry_id": None
    })

    await fsm.order_guardian.cleanup_orphans(symbol="BTCUSDT")

    # Only BTCUSDT should be canceled in targeted cleanup
    assert adapter.cancel_calls == [("BTCUSDT", "1")]


@pytest.mark.asyncio
async def test_sync_open_orders_and_positions_cancels_orphans_on_startup():
    """Test that startup sync calls order_guardian.cleanup_orphans (new behavior)."""
    fsm = ExecPosFSM(config={}, fsm=None, shadow_mode=True)
    adapter = FakeAdapter()
    # No positions at all - so orphan cleanup should run
    adapter.set_positions([])
    # Orders that should be considered orphans
    adapter.set_open_orders([
        {"symbol": "BTCUSDT", "orderId": "1",
            "type": "STOP_MARKET", "closePosition": "true"},
        {"symbol": "SOLUSDT", "orderId": "2",
            "type": "LIMIT", "reduceOnly": "true"},
    ])
    fsm.adapter = adapter
    # Initialize OrderGuardian for the test
    from apps.reference.services.order_guardian import OrderGuardian
    fsm.order_guardian = OrderGuardian(adapter)

    # Register the orders in OrderGuardian so they are recognized as "ours"
    fsm.order_guardian.store.put("order:1", {
        "symbol": "BTCUSDT",
        "type": "STOP_MARKET",
        "reduce_only": False,
        "close_position": True,
        "parent_entry_id": None
    })
    fsm.order_guardian.store.put("order:2", {
        "symbol": "SOLUSDT",
        "type": "LIMIT",
        "reduce_only": True,
        "close_position": False,
        "parent_entry_id": None
    })

    await fsm.sync_open_orders_and_positions()

    # order_guardian.cleanup_orphans() should have canceled orphaned orders
    # No positions exist, so all our bracket orders should be canceled
    assert ("BTCUSDT", "1") in adapter.cancel_calls
    assert ("SOLUSDT", "2") in adapter.cancel_calls


@pytest.mark.asyncio
async def test_cleanup_resilient_on_cancel_error():
    fsm = ExecPosFSM(config={}, fsm=None, shadow_mode=True)
    adapter = FakeAdapter()
    adapter.set_positions([])
    adapter.set_open_orders([
        {"symbol": "BTCUSDT", "orderId": "1",
            "type": "STOP_MARKET", "closePosition": "true"},
        {"symbol": "BTCUSDT", "orderId": "2",
            "type": "TAKE_PROFIT_MARKET", "reduceOnly": "true"},
    ])
    adapter.set_cancel_side_effect(RuntimeError("cancel failed"))
    fsm.adapter = adapter
    # Initialize OrderGuardian for the test
    from apps.reference.services.order_guardian import OrderGuardian
    fsm.order_guardian = OrderGuardian(adapter)

    # Register the orders in OrderGuardian
    fsm.order_guardian.store.put("order:1", {
        "symbol": "BTCUSDT",
        "type": "STOP_MARKET",
        "reduce_only": False,
        "close_position": True,
        "parent_entry_id": None
    })
    fsm.order_guardian.store.put("order:2", {
        "symbol": "BTCUSDT",
        "type": "TAKE_PROFIT_MARKET",
        "reduce_only": True,
        "close_position": False,
        "parent_entry_id": None
    })

    # Even if cancel raises, method should swallow and continue scanning next orders
    await fsm.order_guardian.cleanup_orphans()

    # Both attempts were made
    assert ("BTCUSDT", "1") in adapter.cancel_calls
    assert ("BTCUSDT", "2") in adapter.cancel_calls


def test_on_order_fill_schedules_best_effort_cleanup(monkeypatch):
    fsm = ExecPosFSM(config={}, fsm=None, shadow_mode=True)
    adapter = FakeAdapter()
    fsm.adapter = adapter

    scheduled: Dict[str, Any] = {"count": 0}

    class DummyLoop:
        def create_task(self, coro):
            scheduled["count"] += 1
            # Don't actually run it
            return None

    def fake_get_event_loop():
        return DummyLoop()

    monkeypatch.setattr(asyncio, "get_event_loop", fake_get_event_loop)

    msg = Message(
        op="EVT",
        verb="ORDER_FILL",
        src="adapter",
        dst="execution_position",
        rid="r1",
        pld={"orderId": "abc", "symbol": "BTCUSDT", "quantity": 1.0},
    )

    # Call internal event handler
    fsm._on_order_fill(msg)

    assert scheduled["count"] == 1, "cleanup task should be scheduled on ORDER_FILL"
