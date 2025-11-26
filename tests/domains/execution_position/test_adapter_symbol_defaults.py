import asyncio
from types import SimpleNamespace

import pytest

from apps.reference.domains.execution_position.binance_execution_adapter import (
    BinanceExecutionAdapter,
)


@pytest.mark.asyncio
async def test_cancel_order_without_symbol_fails_closed():
    adapter = BinanceExecutionAdapter(fsm=None, config={}, shadow_mode=True)
    msg = SimpleNamespace(pld={"orderId": "123"})  # missing symbol

    result = await adapter.cancel_order(msg)

    assert result.get("success") is False
    assert "symbol" in result.get("error", "").lower()
