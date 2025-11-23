import pytest
from unittest.mock import AsyncMock

from apps.reference.domains.execution_position.shadow_execpos.runtime import ExecPosRuntimeV2


@pytest.mark.asyncio
async def test_entry_chain_reaches_adapter_place_order():
    # Fake adapter with spy
    class FakeAdapter:
        def __init__(self):
            self.place_calls = []

        async def place_order_v2(self, **kwargs):
            self.place_calls.append(kwargs)
            return {"success": True, "order_id": "TEST_ORDER", "client_order_id": kwargs.get("client_order_id")}

    adapter = FakeAdapter()
    runtime = ExecPosRuntimeV2(config={}, adapter=adapter, price_service=None)
    runtime.execution_service.execute_command = AsyncMock(side_effect=runtime.execution_service.execute_command)

    event = {
        "kind": "ENTRY_INTENT",
        "symbol": "BTCUSDT",
        "payload": {
            "symbol": "BTCUSDT",
            "side": "BUY",
            "quantity": "0.001",
            "order_type": "MARKET",
        },
    }

    await runtime.handle(event)

    # Ensure ExecutionService attempted PLACE
    assert runtime.execution_service.execute_command.await_count == 1
    # Ensure adapter.place_order_v2 was called
    assert len(adapter.place_calls) == 1
    call = adapter.place_calls[0]
    assert call["symbol"] == "BTCUSDT"
    assert call["side"] == "BUY"
    assert call["quantity"] == "0.001"
