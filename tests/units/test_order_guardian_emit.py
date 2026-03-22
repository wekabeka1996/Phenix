import logging
from pathlib import Path

import pytest
from unittest.mock import AsyncMock, MagicMock

from apps.reference.domains.execution_position.order_guardian import OrderGuardian, InMemoryStore
import apps.reference.domains.execution_position.order_guardian as order_guardian_module


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

    assert "CRITICAL: Failed to emit EVT:SYMBOL_TIDY" in caplog.text


def test_order_guardian_logs_to_root_logs_dir() -> None:
    expected_log_file = Path(__file__).resolve(
    ).parents[2] / "logs" / "order_guardian.log"

    handler_paths = [
        Path(handler.baseFilename)
        for handler in order_guardian_module.LOG.handlers
        if hasattr(handler, "baseFilename")
    ]

    assert expected_log_file in handler_paths
