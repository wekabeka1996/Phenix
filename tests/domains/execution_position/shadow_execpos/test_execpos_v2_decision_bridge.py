import asyncio

import pytest

from apps.reference.domains.execution_position.runtime_factory import V2RuntimeFacade


class SimpleMessage:
    def __init__(self, payload):
        self.pld = payload


class FakeAdapter:
    def __init__(self):
        self.place_order_calls = []

    async def place_order(self, symbol, side, order_type, quantity, **kwargs):
        self.place_order_calls.append(
            {
                "symbol": symbol,
                "side": side,
                "order_type": order_type,
                "quantity": quantity,
                "kwargs": kwargs,
            }
        )
        return {
            "success": True,
            "orderId": "TEST_ORDER",
            "clientOrderId": kwargs.get("client_order_id", "TEST_COID"),
        }


@pytest.mark.asyncio
async def test_trade_intent_proposed_triggers_entry_place():
    adapter = FakeAdapter()
    facade = V2RuntimeFacade(
        config={},
        adapter=adapter,
        price_service=None,
        fsm=None,
        loop=asyncio.get_running_loop(),
    )

    intent_payload = {
        "symbol": "SOLUSDT",
        "side": "BUY",
        "quantity": "1.3",
        "price": 130.0,
        "metadata": {"idempotent_key": "test-key-1"},
        "rid": "RID-TEST-1",
    }
    msg = SimpleMessage(intent_payload)

    scheduled = facade.on_trade_intent_proposed(msg)
    if scheduled is not None:
        # Task or concurrent future
        if hasattr(scheduled, "__await__"):
            await scheduled
        else:
            await asyncio.wrap_future(scheduled)

    assert len(adapter.place_order_calls) == 1
    call = adapter.place_order_calls[0]
    assert call["symbol"] == "SOLUSDT"
    assert call["side"] == "BUY"
    assert call["order_type"] == "LIMIT"
    assert str(call["quantity"]) == "1.3"
    assert call["kwargs"].get("tif") == "GTC"
