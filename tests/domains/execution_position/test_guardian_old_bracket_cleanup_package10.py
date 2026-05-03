from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from apps.reference.domains.execution_position.guardian.cancel_submission_adapter import (
    CancelSubmissionAdapterError,
    CancelSubmissionPayload,
)
from apps.reference.domains.execution_position.guardian.order_guardian import (
    InMemoryStore,
    OrderGuardian,
)


def _old_bracket_order(
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


def _tracked_old_bracket_meta(
    *,
    symbol: str,
    parent_entry_id: str,
    client_order_id: str,
    order_type: str = "TAKE_PROFIT_MARKET",
) -> dict[str, object]:
    return {
        "symbol": symbol,
        "type": order_type,
        "reduce_only": True,
        "close_position": False,
        "parent_entry_id": parent_entry_id,
        "client_order_id": client_order_id,
        "kind": order_type.replace("_MARKET", "").upper(),
    }


def test_package4_cancel_intake_accepts_guardian_old_bracket_context() -> None:
    payload = CancelSubmissionPayload.from_dec_cancel(
        payload={
            "symbol": "BTCUSDT",
            "order_id": "tp-old",
            "order_type": "TAKE_PROFIT_MARKET",
            "trigger": "guardian_old_bracket_cleanup",
            "keep_parent_order_id": "parent-keep",
        }
    )
    assert payload.symbol == "BTCUSDT"
    assert payload.order_id == "tp-old"


@pytest.mark.asyncio
async def test_cleanup_other_brackets_routes_through_package4_typed_cancel_intake() -> None:
    symbol = "BTCUSDT"
    adapter = AsyncMock()
    adapter.get_open_orders.return_value = [
        _old_bracket_order(symbol=symbol, order_id="tp-old",
                           client_order_id="TP-OLD"),
    ]
    adapter.cancel_order.return_value = {
        "status": "CANCELED", "orderId": "tp-old"}
    store = InMemoryStore()
    store.put(
        "order:tp-old",
        _tracked_old_bracket_meta(
            symbol=symbol,
            parent_entry_id="parent-old",
            client_order_id="TP-OLD",
        ),
    )
    guardian = OrderGuardian(adapter=adapter, store=store, poll_interval_ms=0)

    with patch.object(
        CancelSubmissionPayload,
        "from_dec_cancel",
        wraps=CancelSubmissionPayload.from_dec_cancel,
    ) as from_dec_cancel:
        cancelled = await guardian.cleanup_other_brackets_for_symbol(
            symbol=symbol,
            keep_parent_order_id="parent-keep",
        )

    assert cancelled == 1
    from_dec_cancel.assert_called_once()
    assert from_dec_cancel.call_args.kwargs["payload"]["order_id"] == "tp-old"
    adapter.cancel_order.assert_awaited_once_with(symbol, "tp-old")


@pytest.mark.asyncio
async def test_cleanup_other_brackets_routes_multiple_outdated_ids_exactly_once_each() -> None:
    symbol = "BTCUSDT"
    adapter = AsyncMock()
    adapter.get_open_orders.return_value = [
        _old_bracket_order(symbol=symbol, order_id="tp-old",
                           client_order_id="TP-OLD"),
        _old_bracket_order(
            symbol=symbol,
            order_id="sl-old",
            client_order_id="SL-OLD",
            order_type="STOP_MARKET",
        ),
    ]
    adapter.cancel_order.side_effect = [
        {"status": "CANCELED", "orderId": "tp-old"},
        {"status": "CANCELED", "orderId": "sl-old"},
    ]
    store = InMemoryStore()
    store.put(
        "order:tp-old",
        _tracked_old_bracket_meta(
            symbol=symbol,
            parent_entry_id="parent-old",
            client_order_id="TP-OLD",
        ),
    )
    store.put(
        "order:sl-old",
        _tracked_old_bracket_meta(
            symbol=symbol,
            parent_entry_id="parent-older",
            client_order_id="SL-OLD",
            order_type="STOP_MARKET",
        ),
    )
    guardian = OrderGuardian(adapter=adapter, store=store, poll_interval_ms=0)

    with patch.object(
        CancelSubmissionPayload,
        "from_dec_cancel",
        wraps=CancelSubmissionPayload.from_dec_cancel,
    ) as from_dec_cancel:
        cancelled = await guardian.cleanup_other_brackets_for_symbol(
            symbol=symbol,
            keep_parent_order_id="parent-keep",
        )

    assert cancelled == 2
    assert from_dec_cancel.call_count == 2
    observed_ids = [call.kwargs["payload"]["order_id"]
                    for call in from_dec_cancel.call_args_list]
    assert observed_ids == ["tp-old", "sl-old"]
    assert adapter.cancel_order.await_count == 2


@pytest.mark.asyncio
async def test_cleanup_other_brackets_fails_closed_without_raw_cancel_fallback() -> None:
    symbol = "BTCUSDT"
    adapter = AsyncMock()
    adapter.get_open_orders.return_value = [
        _old_bracket_order(symbol=symbol, order_id="tp-old",
                           client_order_id="TP-OLD"),
    ]
    store = InMemoryStore()
    store.put(
        "order:tp-old",
        _tracked_old_bracket_meta(
            symbol=symbol,
            parent_entry_id="parent-old",
            client_order_id="TP-OLD",
        ),
    )
    guardian = OrderGuardian(adapter=adapter, store=store, poll_interval_ms=0)

    with patch.object(
        CancelSubmissionPayload,
        "from_dec_cancel",
        side_effect=CancelSubmissionAdapterError("typed reject"),
    ) as from_dec_cancel:
        cancelled = await guardian.cleanup_other_brackets_for_symbol(
            symbol=symbol,
            keep_parent_order_id="parent-keep",
        )

    assert cancelled == 0
    from_dec_cancel.assert_called_once()
    adapter.cancel_order.assert_not_called()


@pytest.mark.asyncio
async def test_background_cleanup_orphans_remains_unchanged() -> None:
    symbol = "BTCUSDT"
    adapter = AsyncMock()
    adapter.get_open_positions.return_value = []
    adapter.get_open_orders.return_value = [
        _old_bracket_order(symbol=symbol, order_id="tp-orphan",
                           client_order_id="TP-ORPHAN"),
    ]
    adapter.cancel_order.return_value = {
        "status": "CANCELED", "orderId": "tp-orphan"}
    store = InMemoryStore()
    store.put(
        "order:tp-orphan",
        _tracked_old_bracket_meta(
            symbol=symbol,
            parent_entry_id="parent-old",
            client_order_id="TP-ORPHAN",
        ),
    )
    guardian = OrderGuardian(adapter=adapter, store=store, poll_interval_ms=0)

    with patch.object(
        CancelSubmissionPayload,
        "from_dec_cancel",
        wraps=CancelSubmissionPayload.from_dec_cancel,
    ) as from_dec_cancel:
        cancelled = await guardian.cleanup_orphans(symbol=symbol, hard=False)

    assert cancelled == 1
    # Package 12 now owns the hard=False path: from_dec_cancel IS invoked.
    from_dec_cancel.assert_called_once()
    assert from_dec_cancel.call_args.kwargs["payload"]["order_id"] == "tp-orphan"
    assert from_dec_cancel.call_args.kwargs["payload"]["trigger"] == "guardian_background_orphan_cancel"
    adapter.cancel_order.assert_awaited_once_with(symbol, "tp-orphan")


@pytest.mark.asyncio
async def test_cleanup_other_brackets_introduces_no_position_amt_or_restart_work() -> None:
    symbol = "BTCUSDT"
    adapter = AsyncMock()
    adapter.get_open_orders.return_value = [
        _old_bracket_order(symbol=symbol, order_id="tp-old",
                           client_order_id="TP-OLD"),
    ]
    adapter.cancel_order.return_value = {
        "status": "CANCELED", "orderId": "tp-old"}
    store = InMemoryStore()
    store.put(
        "order:tp-old",
        _tracked_old_bracket_meta(
            symbol=symbol,
            parent_entry_id="parent-old",
            client_order_id="TP-OLD",
        ),
    )
    guardian = OrderGuardian(adapter=adapter, store=store, poll_interval_ms=0)

    with patch.object(adapter, "get_open_positions", wraps=adapter.get_open_positions) as get_open_positions:
        await guardian.cleanup_other_brackets_for_symbol(
            symbol=symbol,
            keep_parent_order_id="parent-keep",
        )

    get_open_positions.assert_not_called()


@pytest.mark.asyncio
async def test_cleanup_other_brackets_prefers_raw_open_orders_for_bracket_flags() -> None:
    symbol = "BTCUSDT"
    adapter = AsyncMock()
    # Normalized payload lacks reduceOnly/closePosition/type and must not be the only source.
    adapter.get_open_orders.return_value = [
        {
            "symbol": symbol,
            "orderId": "tp-old",
            "clientOrderId": "TP-OLD",
        }
    ]
    adapter.get_open_orders_raw.return_value = [
        _old_bracket_order(symbol=symbol, order_id="tp-old",
                           client_order_id="TP-OLD")
    ]
    adapter.cancel_order.return_value = {
        "status": "CANCELED", "orderId": "tp-old"}

    store = InMemoryStore()
    store.put(
        "order:tp-old",
        _tracked_old_bracket_meta(
            symbol=symbol,
            parent_entry_id="parent-old",
            client_order_id="TP-OLD",
        ),
    )
    guardian = OrderGuardian(adapter=adapter, store=store, poll_interval_ms=0)

    cancelled = await guardian.cleanup_other_brackets_for_symbol(
        symbol=symbol,
        keep_parent_order_id="parent-keep",
    )

    assert cancelled == 1
    adapter.get_open_orders_raw.assert_awaited_once_with(symbol)
    adapter.cancel_order.assert_awaited_once_with(symbol, "tp-old")
