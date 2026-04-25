from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from apps.reference.adapters.binance_adapter import BinanceAPIError
from apps.reference.domains.execution_position.cancel_submission_adapter import (
    CancelSubmissionAdapterError,
    CancelSubmissionPayload,
)
from apps.reference.domains.execution_position.guardian_pre_close_cleanup_bridge import (
    GuardianPreCloseCleanupRequest,
    adapt_guardian_pre_close_cleanup_to_dec_cancel,
)
from apps.reference.domains.execution_position.order_guardian import (
    InMemoryStore,
    OrderGuardian,
)


def _register_entry_with_brackets(guardian: OrderGuardian) -> None:
    guardian.register_entry(
        symbol="BTCUSDT",
        order_id="entry-1",
        client_order_id="ENTRY-1",
        side="BUY",
        qty=1.0,
    )
    guardian.register_bracket(
        symbol="BTCUSDT",
        parent_order_id="entry-1",
        order_id="sl-1",
        client_order_id="SL-1",
        kind="SL",
    )
    guardian.register_bracket(
        symbol="BTCUSDT",
        parent_order_id="entry-1",
        order_id="tp-1",
        client_order_id="TP-1",
        kind="TP",
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


def test_guardian_pre_close_bridge_keeps_parent_context_local_and_emits_package4_compatible_payload() -> None:
    request, cancel_decision = adapt_guardian_pre_close_cleanup_to_dec_cancel(
        symbol="BTCUSDT",
        order_id="sl-1",
        bracket_type="SL",
        parent_order_id="entry-1",
    )

    assert request == GuardianPreCloseCleanupRequest(
        symbol="BTCUSDT",
        order_id="sl-1",
        bracket_type="SL",
        parent_order_id="entry-1",
    )
    assert cancel_decision.pld["symbol"] == "BTCUSDT"
    assert cancel_decision.pld["order_id"] == "sl-1"
    assert cancel_decision.pld["bracket_type"] == "SL"
    assert cancel_decision.pld["trigger"] == "guardian_pre_close_cleanup"
    assert "parent_order_id" not in (cancel_decision.pld or {})


@pytest.mark.parametrize(
    ("result", "expected"),
    [
        ({"status": "CANCELED", "orderId": "sl-1"}, True),
        ({"code": -2011, "msg": "Unknown order sent"}, True),
        ({"code": -2013, "msg": "Order does not exist"}, True),
        ({"code": -1000, "msg": "Internal error"}, False),
    ],
)
def test_order_guardian_cancel_classifier_known_cases(
    result: dict[str, object],
    expected: bool,
) -> None:
    guardian = OrderGuardian(
        adapter=AsyncMock(), store=InMemoryStore(), poll_interval_ms=0)
    assert guardian._is_successful_cancel(result) is expected


@pytest.mark.asyncio
async def test_cleanup_before_close_routes_through_package4_typed_cancel_intake() -> None:
    adapter = AsyncMock()
    adapter.cancel_order.side_effect = [
        {"status": "CANCELED", "orderId": "sl-1"},
        {"status": "CANCELED", "orderId": "tp-1"},
    ]
    guardian = OrderGuardian(
        adapter=adapter,
        store=InMemoryStore(),
        poll_interval_ms=0,
    )
    _register_entry_with_brackets(guardian)

    with patch.object(
        CancelSubmissionPayload,
        "from_dec_cancel",
        wraps=CancelSubmissionPayload.from_dec_cancel,
    ) as from_dec_cancel:
        cancelled = await guardian.cleanup_before_close(
            symbol="BTCUSDT",
            parent_order_id="entry-1",
        )

    assert cancelled == 2
    assert from_dec_cancel.call_count == 2
    observed_ids = [call.kwargs["payload"]["order_id"]
                    for call in from_dec_cancel.call_args_list]
    assert observed_ids == ["sl-1", "tp-1"]
    for call in from_dec_cancel.call_args_list:
        assert "parent_order_id" not in call.kwargs["payload"]
        assert call.kwargs["payload"]["trigger"] == "guardian_pre_close_cleanup"
        assert call.kwargs["payload"]["bracket_type"] in {"SL", "TP"}
    assert adapter.cancel_order.await_count == 2


@pytest.mark.asyncio
async def test_cleanup_before_close_multiple_brackets_traverse_once_each() -> None:
    adapter = AsyncMock()
    adapter.cancel_order.side_effect = [
        {"status": "CANCELED", "orderId": "sl-1"},
        {"status": "CANCELED", "orderId": "tp-1"},
    ]
    guardian = OrderGuardian(
        adapter=adapter, store=InMemoryStore(), poll_interval_ms=0)
    _register_entry_with_brackets(guardian)

    with patch.object(
        CancelSubmissionPayload,
        "from_dec_cancel",
        wraps=CancelSubmissionPayload.from_dec_cancel,
    ) as from_dec_cancel:
        await guardian.cleanup_before_close(
            symbol="BTCUSDT",
            parent_order_id="entry-1",
        )

    assert from_dec_cancel.call_count == 2
    assert [call.kwargs["payload"]["order_id"] for call in from_dec_cancel.call_args_list] == [
        "sl-1",
        "tp-1",
    ]


@pytest.mark.asyncio
async def test_cleanup_before_close_fails_closed_without_raw_cancel_fallback() -> None:
    adapter = AsyncMock()
    guardian = OrderGuardian(
        adapter=adapter, store=InMemoryStore(), poll_interval_ms=0)
    _register_entry_with_brackets(guardian)

    with patch.object(
        CancelSubmissionPayload,
        "from_dec_cancel",
        side_effect=CancelSubmissionAdapterError("typed reject"),
    ) as from_dec_cancel:
        cancelled = await guardian.cleanup_before_close(
            symbol="BTCUSDT",
            parent_order_id="entry-1",
        )

    assert cancelled == 0
    assert from_dec_cancel.call_count == 2
    adapter.cancel_order.assert_not_called()


@pytest.mark.asyncio
async def test_cleanup_before_close_treats_2013_exception_as_success() -> None:
    adapter = AsyncMock()
    adapter.cancel_order.side_effect = [
        BinanceAPIError(code=-2013, msg="Order does not exist"),
        BinanceAPIError(code=-2013, msg="Order does not exist"),
    ]
    guardian = OrderGuardian(
        adapter=adapter, store=InMemoryStore(), poll_interval_ms=0)
    _register_entry_with_brackets(guardian)

    with patch.object(
        CancelSubmissionPayload,
        "from_dec_cancel",
        wraps=CancelSubmissionPayload.from_dec_cancel,
    ) as from_dec_cancel:
        cancelled = await guardian.cleanup_before_close(
            symbol="BTCUSDT",
            parent_order_id="entry-1",
        )

    assert cancelled == 2
    assert from_dec_cancel.call_count == 2
    assert adapter.cancel_order.await_count == 2


@pytest.mark.asyncio
async def test_cleanup_other_brackets_for_symbol_remains_unchanged() -> None:
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
    adapter.cancel_order.assert_awaited_once_with(symbol, "tp-old")


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
async def test_cleanup_before_close_introduces_no_position_amt_or_restart_work() -> None:
    adapter = AsyncMock()
    adapter.cancel_order.side_effect = [
        {"status": "CANCELED", "orderId": "sl-1"},
        {"status": "CANCELED", "orderId": "tp-1"},
    ]
    guardian = OrderGuardian(
        adapter=adapter, store=InMemoryStore(), poll_interval_ms=0)
    _register_entry_with_brackets(guardian)

    with patch.object(adapter, "get_open_positions", wraps=adapter.get_open_positions) as get_open_positions:
        await guardian.cleanup_before_close(
            symbol="BTCUSDT",
            parent_order_id="entry-1",
        )

    get_open_positions.assert_not_called()
