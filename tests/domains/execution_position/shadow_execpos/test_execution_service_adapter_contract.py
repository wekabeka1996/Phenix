import pytest

from apps.reference.domains.execution_position.shadow_execpos.execution_service import ExecutionService
from apps.reference.domains.execution_position.shadow_execpos.types import ExecutionStatus


class FakeAdapterV2:
    def __init__(self):
        self.calls = []

    async def place_order_v2(self, **kwargs):
        self.calls.append(kwargs)
        return {"status": ExecutionStatus.SUBMITTED, "success": True, "order_id": "ok", "client_order_id": kwargs.get("client_order_id"), "error": None, "metadata": {}}


@pytest.mark.asyncio
async def test_execution_service_prefers_place_order_v2():
    adapter = FakeAdapterV2()
    svc = ExecutionService(adapter)

    await svc._call_adapter(
        "place_order",
        symbol="BTCUSDT",
        side="BUY",
        order_type="MARKET",
        quantity=0.01,
        client_order_id="cid-1",
    )

    assert len(adapter.calls) == 1
    call = adapter.calls[0]
    assert call["symbol"] == "BTCUSDT"
    assert call["side"] == "BUY"
    assert call["quantity"] == 0.01
    assert call["client_order_id"] == "cid-1"
