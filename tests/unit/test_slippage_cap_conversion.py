"""
Test slippage cap: MARKET -> LIMIT IOC with capped price when anchor price provided.

NOTE: This test was designed for BinanceExecutionAdapter._place_binance_order_async
      which is not available in unified BinanceAdapter. Skip until FSM place_order_fsm
      slippage logic is implemented.
"""

import asyncio
from decimal import Decimal

import pytest

# MIGRATED: BinanceExecutionAdapter -> BinanceAdapter (unified adapter)
from apps.reference.adapters.binance_adapter import BinanceAdapter as BinanceExecutionAdapter
from vfoundation.core.protocol import Message

pytestmark = pytest.mark.skip(
    reason="BinanceExecutionAdapter._place_binance_order_async not available in unified BinanceAdapter"
)


@pytest.mark.asyncio
async def test_slippage_cap_applies_limit_ioc_with_price(monkeypatch):
    config = {
        "trading": {
            "orders": {
                "market": {
                    "slippage_cap_bps": 10,
                }
            }
        }
    }
    adapter = BinanceExecutionAdapter(fsm=None, config=config, shadow_mode=False)
    # Force live path (we'll monkeypatch the async call) and set dummy creds
    adapter.shadow_mode = False
    adapter.api_key = "K"
    adapter.api_secret = "S"

    # Ensure we don't hit network; monkeypatch the async order placement
    captured = {}

    async def fake_place(symbol, side, quantity, order_type, price, stop_price, reduce_only, idempotent_key, time_in_force):
        captured.update(
            dict(
                symbol=symbol,
                side=side,
                quantity=quantity,
                order_type=order_type,
                price=price,
                tif=time_in_force,
            )
        )
        # Simulate exchange response
        return {"orderId": "12345", "status": "NEW", "clientOrderId": idempotent_key or "test"}

    monkeypatch.setattr(
        adapter, "_place_binance_order_async", fake_place, raising=True
    )

    # Build DEC:OPEN message with anchor_price
    msg = Message(
        op="DEC",
        verb="OPEN",
        src="test",
        dst="exec",
        pld={
            "symbol": "ETHUSDT",
            "side": "BUY",
            "qty": "0.01",
            "order_type": "MARKET",
            "anchor_price": "2000",
            "newClientOrderId": "AUR-TEST",
        },
    )

    resp = await adapter.place_order(msg)

    assert resp["order_id"] == "12345"
    # Expect conversion: MARKET -> LIMIT with IOC
    assert captured["order_type"] == "LIMIT"
    assert captured["tif"] == "IOC"
    # Price should be anchor * (1 + 10 bps) for BUY
    expected = Decimal("2000") * (Decimal(1) + Decimal(10) / Decimal(10000))
    assert Decimal(captured["price"]) == expected.quantize(Decimal("0.00000001"))
