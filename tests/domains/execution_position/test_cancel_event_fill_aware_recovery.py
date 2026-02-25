from __future__ import annotations

import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.reference.adapters.binance_adapter import BinanceAPIError
from vfoundation.core.protocol import Message


def _seed_pending_brackets(
    fsm,
    *,
    entry_order_id: str = "12539847754",
    symbol: str = "BTCUSDT",
    side: str = "BUY",
) -> dict:
    bracket_data = {
        "symbol": symbol,
        "side": side,
        "sl": "65641.8",
        "tp": "66466.5",
        "qty": 0.004,
        "rid": "rid-btc-fill",
        "idem_key": "idem-btc-fill",
        "tick_size": "0.1",
        "corr_id": "corr-btc-fill",
        "oco_group_id": "oco-btc-fill",
        "entry_client_order_id": "ENTRY-ac29a621d84c",
        "created_at": 0.0,
    }
    fsm._pending_brackets[entry_order_id] = dict(bracket_data)
    return bracket_data


def _wire_bracket_adapter(fsm) -> None:
    adapter = MagicMock()
    adapter.base_url = "https://fapi.binance.com"
    adapter.place_stop_market_close_position = AsyncMock(
        return_value={"orderId": "SL-1001"}
    )
    adapter.place_take_profit_market_close_position = AsyncMock(
        return_value={"orderId": "TP-2002"}
    )
    fsm.adapter = adapter


def _wire_guardian(fsm) -> None:
    fsm.order_guardian.should_place_brackets = AsyncMock(return_value=True)
    fsm.order_guardian.register_bracket = MagicMock()
    fsm.order_guardian.get_brackets_for_entry = MagicMock(return_value={})


def _wire_bracket_config(fsm) -> None:
    cfg = fsm.config.domains.execution_position.bracket_placement
    cfg.tp_widen_first_bps = 10
    cfg.tp_widen_second_bps = 20
    cfg.retry_backoff_ms = [50, 100]
    fsm.config.domains.execution_position.order_lifecycle.fill_settlement_delay_ms = 0


def _capture_submitted_coroutines(fsm) -> list:
    submitted: list = []
    sentinel_loop = object()
    fsm._get_async_loop = MagicMock(return_value=sentinel_loop)

    def _capture(coro, loop=None):
        submitted.append(coro)

    fsm._submit_async = MagicMock(side_effect=_capture)
    return submitted


async def _drain_submitted(submitted: list) -> None:
    idx = 0
    while idx < len(submitted):
        coro = submitted[idx]
        idx += 1
        if asyncio.iscoroutine(coro):
            await coro


@pytest.mark.asyncio
async def test_ws_cancel_event_with_executed_qty_routes_to_recovery(fsm_harness):
    fsm, _, _ = fsm_harness
    order_id = "12539847754"
    symbol = "BTCUSDT"

    _seed_pending_brackets(fsm, entry_order_id=order_id, symbol=symbol)
    _wire_bracket_adapter(fsm)
    _wire_guardian(fsm)
    _wire_bracket_config(fsm)
    fsm._preflight_position_check = AsyncMock(return_value=True)
    fsm._emit_observability_event = MagicMock()

    # Partial brackets case: SL fails, TP succeeds -> guardrail must fire.
    fsm.adapter.place_stop_market_close_position = AsyncMock(
        side_effect=BinanceAPIError(code=-2021, msg="Order would immediately trigger")
    )
    fsm.adapter.place_take_profit_market_close_position = AsyncMock(
        return_value={"orderId": "TP-9001"}
    )

    submitted = _capture_submitted_coroutines(fsm)
    msg = Message(
        op="EVT",
        verb="ORDER_CANCELLED",
        src="exchange",
        dst="execution_position",
        rid="rid-cancel-fill",
        pld={
            "symbol": symbol,
            "order_id": order_id,
            "executedQty": Decimal("0.001"),
        },
    )

    with patch("apps.reference.domains.execution_position.fsm.write_pending_brackets_cleared") as clear_mock:
        fsm._handle_cancel_event(msg)
        await _drain_submitted(submitted)

    assert fsm.adapter.place_stop_market_close_position.call_count == 1
    assert fsm.adapter.place_take_profit_market_close_position.call_count == 1
    assert order_id not in fsm._pending_brackets

    clear_reasons = [str(call.kwargs.get("reason", "")) for call in clear_mock.call_args_list]
    assert clear_reasons
    assert "cancelled" not in clear_reasons

    event_types = [str(call.args[0]) for call in fsm._emit_observability_event.call_args_list if call.args]
    assert "FILLED_ENTRY_WITHOUT_BRACKETS" in event_types


@pytest.mark.asyncio
async def test_ws_cancel_event_with_zero_executed_qty_clears_as_cancelled(fsm_harness):
    fsm, _, _ = fsm_harness
    order_id = "12539847754"
    symbol = "BTCUSDT"

    _seed_pending_brackets(fsm, entry_order_id=order_id, symbol=symbol)
    submitted = _capture_submitted_coroutines(fsm)
    fsm._recover_deferred_brackets_for_filled_entry = AsyncMock(return_value=True)

    msg = Message(
        op="EVT",
        verb="ORDER_CANCELLED",
        src="exchange",
        dst="execution_position",
        rid="rid-cancel-zero",
        pld={
            "symbol": symbol,
            "order_id": order_id,
            "executedQty": "0",
        },
    )

    with patch("apps.reference.domains.execution_position.fsm.write_pending_brackets_cleared") as clear_mock:
        fsm._handle_cancel_event(msg)
        await _drain_submitted(submitted)

    assert order_id not in fsm._pending_brackets
    fsm._recover_deferred_brackets_for_filled_entry.assert_not_called()
    clear_reasons = [str(call.kwargs.get("reason", "")) for call in clear_mock.call_args_list]
    assert "cancelled" in clear_reasons
