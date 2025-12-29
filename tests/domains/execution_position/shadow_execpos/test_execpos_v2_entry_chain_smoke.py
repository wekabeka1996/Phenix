import pytest
from unittest.mock import AsyncMock

from apps.reference.domains.execution_position.shadow_execpos.runtime import ExecPosRuntimeV2


@pytest.mark.asyncio
async def test_entry_chain_reaches_adapter_place_order():
    # Fake adapter with spy
    class FakeAdapter:
        def __init__(self):
            self.place_calls = []
            self.create_order = self.place_order_v2 # Alias

        async def place_order_v2(self, params=None, **kwargs):
            if params:
                kwargs.update({
                    "symbol": params.symbol,
                    "side": params.side,
                    "quantity": params.quantity,
                    "client_order_id": params.client_order_id
                })
            self.place_calls.append(kwargs)
            return {
                "success": True,
                "order_id": "TEST_ORDER",
                "client_order_id": kwargs.get("client_order_id"),
                "status": "FILLED",
                "price": "50000",
                "filled_qty": str(kwargs.get("quantity", "0.001")),
            }

    adapter = FakeAdapter()
    # Disable executor_pool for this legacy test that doesn't simulate fills
    runtime = ExecPosRuntimeV2(
        config={"execution_position": {
            "executor_pool_enabled": False,  # Use legacy non-blocking path

        }},
        adapter=adapter,
        price_service=None
    )
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
    assert str(call["quantity"]) == "0.001"
