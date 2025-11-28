import asyncio
import pytest

from apps.reference.services.order_guardian import OrderGuardian


@pytest.mark.asyncio
async def test_guardian_on_fill_and_close_entry_minimal():
    # No adapter to avoid network; use in-memory store
    g = OrderGuardian(adapter=None, poll_interval_ms=0)

    # Register an entry
    g.register_entry(
        symbol="BTCUSDT",
        order_id="1001",
        client_order_id="ENTRY-1001",
        side="BUY",
        qty=2.0,
        corr_id="corr-1",
        rid="rid-1",
    )

    # Verify entry listed
    entries = g.list_entries("BTCUSDT")
    assert any(e["order_id"] == "1001" for e in entries)

    # Apply fills in two parts
    g.on_fill(symbol="BTCUSDT", parent_order_id="1001", filled_qty=0.75)
    g.on_fill(symbol="BTCUSDT", parent_order_id="1001", filled_qty=0.25)

    # Check remaining/filled updated
    entries = g.list_entries("BTCUSDT")
    e = next(e for e in entries if e["order_id"] == "1001")
    assert pytest.approx(e["filled_qty"], rel=1e-6) == 1.0
    assert pytest.approx(e["remaining_qty"], rel=1e-6) == 1.0
