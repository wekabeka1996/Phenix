import pytest
from unittest.mock import AsyncMock

from vfoundation.core import FSMCore
from apps.reference.domains.execution_position.order_guardian import OrderGuardian, InMemoryStore


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


@pytest.mark.asyncio
async def test_symbol_tidy_delivered_to_fsm_when_monitoring_tidy_suppressed() -> None:
    fsm = FSMCore()
    received_symbol_tidy = []
    received_monitoring_tidy = []

    fsm.listen("EVT:SYMBOL_TIDY", received_symbol_tidy.append)
    fsm.listen("EVT:EXECUTION_TIDY_PERFORMED", received_monitoring_tidy.append)

    adapter = AsyncMock()
    adapter.get_open_positions.return_value = []
    adapter.get_open_orders.return_value = []

    guardian = OrderGuardian(
        adapter=adapter,
        store=InMemoryStore(),
        bus=fsm,
        poll_interval_ms=0,
        emit_tidy_monitoring_event=False,
    )
    guardian.cleanup_orphans = AsyncMock(return_value=0)

    await guardian.reconcile_symbol("BTCUSDT", rid="rid-monitoring-off")

    assert received_monitoring_tidy == []
    assert len(received_symbol_tidy) == 1
    assert received_symbol_tidy[0].pld.get("symbol") == "BTCUSDT"
