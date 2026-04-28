import logging
from pathlib import Path

import pytest
from unittest.mock import AsyncMock, MagicMock

from apps.reference.domains.execution_position.order_guardian import OrderGuardian, InMemoryStore
import apps.reference.domains.execution_position.order_guardian as order_guardian_module


class _OrphanCleanupAdapter:
    def __init__(self) -> None:
        self.cancelled: list[tuple[str, str]] = []

    async def get_open_positions(self):
        return []

    async def get_open_orders(self, symbol=None):
        return [
            {
                "symbol": symbol or "BTCUSDT",
                "orderId": "orphan-bracket-1",
                "clientOrderId": "TP1-orphan",
                "type": "TAKE_PROFIT_MARKET",
                "reduceOnly": True,
                "closePosition": False,
            }
        ]

    async def cancel_order(self, symbol, order_id):
        self.cancelled.append((symbol, order_id))
        return {"status": "CANCELED", "orderId": order_id}


def _emitted_event_names(bus: MagicMock) -> list[str]:
    return [call.args[0] for call in bus.emit.call_args_list]


@pytest.mark.asyncio
async def test_emit_symbol_tidy_includes_why_parameter() -> None:
    adapter = AsyncMock()
    adapter.get_open_positions.return_value = []
    adapter.get_open_orders.return_value = []

    bus = MagicMock()
    guardian = OrderGuardian(
        adapter=adapter,
        store=InMemoryStore(),
        bus=bus,
        poll_interval_ms=0,
    )
    guardian.cleanup_orphans = AsyncMock(return_value=0)

    await guardian.reconcile_symbol("BTCUSDT", rid="rid-1")

    assert bus.emit.called
    args, kwargs = bus.emit.call_args
    assert len(args) >= 3 or "why" in kwargs


@pytest.mark.asyncio
async def test_emit_tidy_monitoring_enabled_emits_monitoring_and_symbol_tidy() -> None:
    adapter = AsyncMock()
    adapter.get_open_positions.return_value = []
    adapter.get_open_orders.return_value = []

    bus = MagicMock()
    guardian = OrderGuardian(
        adapter=adapter,
        store=InMemoryStore(),
        bus=bus,
        poll_interval_ms=0,
        emit_tidy_monitoring_event=True,
    )
    guardian.cleanup_orphans = AsyncMock(return_value=0)

    await guardian.reconcile_symbol("BTCUSDT", rid="rid-monitoring-on")

    events = _emitted_event_names(bus)
    assert "EVT:EXECUTION_TIDY_PERFORMED" in events
    assert "EVT:SYMBOL_TIDY" in events


@pytest.mark.asyncio
async def test_emit_tidy_monitoring_disabled_suppresses_only_monitoring_event() -> None:
    adapter = AsyncMock()
    adapter.get_open_positions.return_value = []
    adapter.get_open_orders.return_value = []

    bus = MagicMock()
    guardian = OrderGuardian(
        adapter=adapter,
        store=InMemoryStore(),
        bus=bus,
        poll_interval_ms=0,
        emit_tidy_monitoring_event=False,
    )
    guardian.cleanup_orphans = AsyncMock(return_value=0)

    await guardian.reconcile_symbol("BTCUSDT", rid="rid-monitoring-off")

    events = _emitted_event_names(bus)
    assert "EVT:EXECUTION_TIDY_PERFORMED" not in events
    assert "EVT:SYMBOL_TIDY" in events
    assert "EVT:EXECUTION_CLOSE_RECONCILED" in events


@pytest.mark.asyncio
async def test_cleanup_orphans_still_tidies_when_monitoring_event_suppressed() -> None:
    adapter = _OrphanCleanupAdapter()
    bus = MagicMock()
    guardian = OrderGuardian(
        adapter=adapter,
        store=InMemoryStore(),
        bus=bus,
        poll_interval_ms=0,
        emit_tidy_monitoring_event=False,
    )

    cancelled = await guardian.cleanup_orphans(symbol="BTCUSDT", hard=True)

    events = _emitted_event_names(bus)
    assert cancelled == 1
    assert adapter.cancelled == [("BTCUSDT", "orphan-bracket-1")]
    assert "EVT:EXECUTION_TIDY_PERFORMED" not in events
    assert "EVT:SYMBOL_TIDY" in events


@pytest.mark.asyncio
async def test_emit_failure_logged_not_swallowed(caplog: pytest.LogCaptureFixture) -> None:
    adapter = AsyncMock()
    adapter.get_open_positions.return_value = []
    adapter.get_open_orders.return_value = []

    bus = MagicMock()
    bus.emit.side_effect = TypeError("Missing argument 'why'")

    guardian = OrderGuardian(
        adapter=adapter,
        store=InMemoryStore(),
        bus=bus,
        poll_interval_ms=0,
    )
    guardian.cleanup_orphans = AsyncMock(return_value=0)

    with caplog.at_level(logging.ERROR, logger="order_guardian"):
        await guardian.reconcile_symbol("BTCUSDT", rid="rid-1")

    assert "CRITICAL: Failed to emit tidy events" in caplog.text
    assert "CRITICAL: Failed to emit close reconcile event" in caplog.text


def test_order_guardian_logs_to_root_logs_dir() -> None:
    expected_log_file = Path(__file__).resolve(
    ).parents[2] / "logs" / "order_guardian.log"

    handler_paths = [
        Path(handler.baseFilename)
        for handler in order_guardian_module.LOG.handlers
        if hasattr(handler, "baseFilename")
    ]

    assert expected_log_file in handler_paths
