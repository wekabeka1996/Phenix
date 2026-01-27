import pytest
from unittest.mock import AsyncMock

from vfoundation.core import FSMCore
from apps.reference.services.order_guardian import OrderGuardian, InMemoryStore


@pytest.mark.asyncio
async def test_tidy_event_delivered_to_fsm() -> None:
    fsm = FSMCore()
    received = []

    def _capture(event):
        received.append(event)

    fsm.listen("EVT:SYMBOL_TIDY", _capture)

    adapter = AsyncMock()
    adapter.get_open_positions.return_value = []
    adapter.get_open_orders.return_value = []

    guardian = OrderGuardian(
        adapter=adapter,
        store=InMemoryStore(),
        bus=fsm,
        poll_interval_ms=0,
    )
    guardian.cleanup_orphans = AsyncMock(return_value=0)

    await guardian.reconcile_symbol("BTCUSDT", rid="rid-1")

    assert len(received) == 1
    assert received[0].pld.get("symbol") == "BTCUSDT"