import asyncio
from typing import Any

import pytest

from apps.reference.adapters.binance_adapter import BinanceAPIError
from apps.reference.services.order_guardian import OrderGuardian


class _DummyBus:
    def __init__(self) -> None:
        self.events: list[tuple[str, Any]] = []

    def emit(self, name: str, payload: Any) -> None:
        self.events.append((name, payload))


class _CleanupAdapter:
    def __init__(self) -> None:
        self.cancelled: list[str] = []
        self._orders: list[dict[str, Any]] = [
            {
                "symbol": "BTCUSDT",
                "orderId": "tp_ok",
                "clientOrderId": "TP-abc",
                "type": "TAKE_PROFIT_MARKET",
                "reduceOnly": True,
                "closePosition": True,
            },
            {
                "symbol": "BTCUSDT",
                "orderId": "sl_unknown",
                "clientOrderId": "SL-xyz",
                "type": "STOP_MARKET",
                "reduceOnly": "true",
                "closePosition": "true",
            },
            {
                "symbol": "BTCUSDT",
                "orderId": "foreign",
                "clientOrderId": "FOREIGN-1",
                "type": "LIMIT",
                "reduceOnly": False,
                "closePosition": False,
            },
        ]

    async def get_open_positions(self) -> list[dict[str, Any]]:
        return []

    async def get_open_orders(self, symbol: str | None = None) -> list[dict[str, Any]]:
        if symbol:
            return [order for order in self._orders if order["symbol"] == symbol]
        return list(self._orders)

    async def cancel_order(self, symbol: str, order_id: str) -> dict[str, Any]:
        if order_id == "tp_ok":
            self.cancelled.append(order_id)
            return {"status": "CANCELED", "orderId": order_id}
        if order_id == "sl_unknown":
            raise BinanceAPIError(-2011, "Unknown order sent")
        raise AssertionError(f"Unexpected cancel request {order_id}")


class _RelinkAdapter:
    async def get_open_positions(self) -> list[dict[str, Any]]:
        return []

    async def get_open_orders(self, symbol: str | None = None) -> list[dict[str, Any]]:
        return [
            {
                "symbol": symbol or "ETHUSDT",
                "orderId": "new_tp",
                "clientOrderId": "TP-relink",
                "type": "TAKE_PROFIT_MARKET",
                "reduceOnly": "true",
                "closePosition": "false",
            }
        ]

    async def cancel_order(self, symbol: str, order_id: str) -> dict[str, Any]:
        raise AssertionError(
            "cancel_order should not be called in relink test")


class _PollAdapter:
    def __init__(self) -> None:
        self.orders: list[dict[str, Any]] = [
            {
                "symbol": "BTCUSDT",
                "orderId": "tp_poll",
                "clientOrderId": "TP-poll",
                "type": "TAKE_PROFIT_MARKET",
                "reduceOnly": True,
                "closePosition": True,
            }
        ]
        self.cancelled: list[str] = []

    async def get_open_positions(self) -> list[dict[str, Any]]:
        return []

    async def get_open_orders(self, symbol: str | None = None) -> list[dict[str, Any]]:
        if symbol:
            return [order for order in self.orders if order["symbol"] == symbol]
        return list(self.orders)

    async def cancel_order(self, symbol: str, order_id: str) -> dict[str, Any]:
        for idx, order in enumerate(self.orders):
            if order["orderId"] == order_id:
                self.orders.pop(idx)
                self.cancelled.append(order_id)
                return {"status": "CANCELED", "orderId": order_id}
        raise BinanceAPIError(-2011, "Unknown order sent")


@pytest.mark.asyncio
async def test_cleanup_orphans_handles_unknown_order_success() -> None:
    adapter = _CleanupAdapter()
    guardian = OrderGuardian(adapter=adapter, poll_interval_ms=0)
    guardian.register_entry(
        symbol="BTCUSDT",
        order_id="entry-1",
        client_order_id="ENTRY-1",
        side="BUY",
        qty=1.0,
    )
    guardian.register_brackets(
        symbol="BTCUSDT",
        entry_order_id="entry-1",
        sl_order_id="sl_unknown",
        sl_client_id="SL-xyz",
        tp_order_id="tp_ok",
        tp_client_id="TP-abc",
    )

    cancelled = await guardian.cleanup_orphans(symbol="BTCUSDT", batch_limit=10)

    metrics = guardian.get_metrics()
    assert cancelled == 2
    assert metrics["guardian_orphans_cancelled_total"] == 2
    assert adapter.cancelled == ["tp_ok"]


@pytest.mark.asyncio
async def test_link_existing_from_rest_tracks_guardian_orders() -> None:
    adapter = _RelinkAdapter()
    guardian = OrderGuardian(adapter=adapter, poll_interval_ms=0)

    await guardian.link_existing_from_rest("ETHUSDT")

    assert guardian.store.get("order:new_tp") is not None
    metrics = guardian.get_metrics()
    assert metrics["guardian_linked_from_rest_total"] == 1


@pytest.mark.asyncio
async def test_guardian_poll_loop_emits_tidy_event() -> None:
    adapter = _PollAdapter()
    bus = _DummyBus()
    guardian = OrderGuardian(adapter=adapter, poll_interval_ms=10, bus=bus)
    guardian.register_entry(
        symbol="BTCUSDT",
        order_id="entry-2",
        client_order_id="ENTRY-2",
        side="BUY",
        qty=1.0,
    )
    guardian.register_brackets(
        symbol="BTCUSDT",
        entry_order_id="entry-2",
        tp_order_id="tp_poll",
        tp_client_id="TP-poll",
    )

    await guardian.start()
    await asyncio.sleep(0.05)
    await guardian.stop()

    metrics = guardian.get_metrics()
    assert "tp_poll" in adapter.cancelled
    assert metrics["guardian_orphans_cancelled_total"] >= 1
    assert any(event[0] == "EVT:SYMBOL_TIDY" for event in bus.events)
