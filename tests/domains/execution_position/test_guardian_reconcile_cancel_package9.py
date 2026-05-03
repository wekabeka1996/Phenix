from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.reference.domains.execution_position.guardian.cancel_submission_adapter import (
    CancelSubmissionAdapterError,
    CancelSubmissionPayload,
)
from apps.reference.domains.execution_position.guardian.order_guardian import (
    InMemoryStore,
    OrderGuardian,
)


def _orphan_order(
    *,
    symbol: str,
    order_id: str,
    client_order_id: str,
    order_type: str = "TAKE_PROFIT_MARKET",
) -> dict[str, object]:
    return {
        "symbol": symbol,
        "orderId": order_id,
        "clientOrderId": client_order_id,
        "type": order_type,
        "reduceOnly": True,
        "closePosition": False,
    }


def _event_topics(bus: MagicMock) -> list[str]:
    return [call.args[0] for call in bus.emit.call_args_list]


def test_package4_cancel_intake_accepts_guardian_reconcile_context() -> None:
    payload = CancelSubmissionPayload.from_dec_cancel(
        payload={
            "symbol": "BTCUSDT",
            "order_id": "tp-1",
            "order_type": "TAKE_PROFIT_MARKET",
            "trigger": "guardian_reconcile_cancel",
        }
    )
    assert payload.symbol == "BTCUSDT"
    assert payload.order_id == "tp-1"


@pytest.mark.asyncio
async def test_reconcile_symbol_routes_orphans_through_package4_typed_cancel_intake() -> None:
    symbol = "BTCUSDT"
    adapter = AsyncMock()
    adapter.get_open_positions.return_value = []
    adapter.get_open_orders.side_effect = [
        [_orphan_order(symbol=symbol, order_id="tp-1", client_order_id="TP-1")],
        [],
    ]
    adapter.cancel_order.return_value = {"status": "CANCELED", "orderId": "tp-1"}
    bus = MagicMock()
    guardian = OrderGuardian(
        adapter=adapter,
        store=InMemoryStore(),
        bus=bus,
        poll_interval_ms=0,
    )

    with patch.object(
        CancelSubmissionPayload,
        "from_dec_cancel",
        wraps=CancelSubmissionPayload.from_dec_cancel,
    ) as from_dec_cancel:
        await guardian.reconcile_symbol(symbol, rid="rid-close-1")

    from_dec_cancel.assert_called_once()
    assert from_dec_cancel.call_args.kwargs["payload"]["order_id"] == "tp-1"
    adapter.cancel_order.assert_awaited_once_with(symbol, "tp-1")
    assert "EVT:SYMBOL_TIDY" in _event_topics(bus)
    assert "EVT:EXECUTION_CLOSE_RECONCILED" in _event_topics(bus)


@pytest.mark.asyncio
async def test_reconcile_symbol_routes_multiple_orphans_exactly_once_each() -> None:
    symbol = "BTCUSDT"
    adapter = AsyncMock()
    adapter.get_open_positions.return_value = []
    adapter.get_open_orders.side_effect = [
        [
            _orphan_order(symbol=symbol, order_id="tp-1", client_order_id="TP-1"),
            _orphan_order(
                symbol=symbol,
                order_id="sl-1",
                client_order_id="SL-1",
                order_type="STOP_MARKET",
            ),
        ],
        [],
    ]
    adapter.cancel_order.side_effect = [
        {"status": "CANCELED", "orderId": "tp-1"},
        {"status": "CANCELED", "orderId": "sl-1"},
    ]
    guardian = OrderGuardian(
        adapter=adapter,
        store=InMemoryStore(),
        bus=MagicMock(),
        poll_interval_ms=0,
    )

    with patch.object(
        CancelSubmissionPayload,
        "from_dec_cancel",
        wraps=CancelSubmissionPayload.from_dec_cancel,
    ) as from_dec_cancel:
        await guardian.reconcile_symbol(symbol, rid="rid-close-2")

    assert from_dec_cancel.call_count == 2
    observed_ids = [call.kwargs["payload"]["order_id"] for call in from_dec_cancel.call_args_list]
    assert observed_ids == ["tp-1", "sl-1"]
    assert adapter.cancel_order.await_count == 2


@pytest.mark.asyncio
async def test_reconcile_symbol_fails_closed_without_raw_cancel_fallback() -> None:
    symbol = "BTCUSDT"
    adapter = AsyncMock()
    adapter.get_open_positions.return_value = []
    adapter.get_open_orders.side_effect = [
        [_orphan_order(symbol=symbol, order_id="tp-1", client_order_id="TP-1")],
        [],
    ]
    guardian = OrderGuardian(
        adapter=adapter,
        store=InMemoryStore(),
        bus=MagicMock(),
        poll_interval_ms=0,
    )

    with patch.object(
        CancelSubmissionPayload,
        "from_dec_cancel",
        side_effect=CancelSubmissionAdapterError("typed reject"),
    ) as from_dec_cancel:
        await guardian.reconcile_symbol(symbol, rid="rid-close-3")

    from_dec_cancel.assert_called_once()
    adapter.cancel_order.assert_not_called()


@pytest.mark.asyncio
async def test_reconcile_symbol_still_respects_legacy_position_amt_and_skips_cancel() -> None:
    adapter = AsyncMock()
    adapter.get_open_positions.return_value = [{"symbol": "BTCUSDT", "positionAmt": "0.10"}]
    guardian = OrderGuardian(
        adapter=adapter,
        store=InMemoryStore(),
        bus=MagicMock(),
        poll_interval_ms=0,
    )

    with patch.object(
        CancelSubmissionPayload,
        "from_dec_cancel",
        wraps=CancelSubmissionPayload.from_dec_cancel,
    ) as from_dec_cancel:
        await guardian.reconcile_symbol("BTCUSDT", rid="rid-position-still-open")

    from_dec_cancel.assert_not_called()
    adapter.cancel_order.assert_not_called()
