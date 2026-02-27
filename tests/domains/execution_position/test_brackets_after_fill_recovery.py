from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.reference.adapters.binance_adapter import BinanceAPIError
from apps.reference.domains.execution_position.idempotent_cancel import (
    IdempotentCancelResult,
)
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
    adapter.get_open_positions = AsyncMock(
        return_value=[{"symbol": "BTCUSDT", "positionAmt": "0.004"}]
    )
    adapter.get_order = AsyncMock(
        return_value={
            "orderId": "12539847754",
            "symbol": "BTCUSDT",
            "status": "FILLED",
            "executedQty": "0.004",
            "avgPrice": "65971.7",
            "side": "BUY",
            "clientOrderId": "ENTRY-ac29a621d84c",
        }
    )
    adapter.get_open_orders = AsyncMock(return_value=[])
    fsm.adapter = adapter


def _wire_guardian(fsm) -> None:
    fsm.order_guardian.should_place_brackets = AsyncMock(return_value=True)
    fsm.order_guardian.register_bracket = MagicMock()
    fsm.order_guardian.get_brackets_for_entry = MagicMock(return_value={})
    fsm.order_guardian.link_existing_from_rest = AsyncMock()
    fsm.order_guardian.cleanup_orphans = AsyncMock()


def _wire_bracket_config(fsm) -> None:
    cfg = fsm.config.domains.execution_position.bracket_placement
    cfg.tp_widen_first_bps = 10
    cfg.tp_widen_second_bps = 20
    cfg.retry_backoff_ms = [50, 100]
    # Avoid unrelated delayed cleanup coroutine failures from MagicMock config.
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
async def test_cancel_path_terminal_filled_triggers_bracket_recovery(fsm_harness):
    fsm, _, _ = fsm_harness
    order_id = "12539847754"
    symbol = "BTCUSDT"

    fsm._pending_brackets.clear()
    _seed_pending_brackets(fsm, entry_order_id=order_id, symbol=symbol)
    _wire_bracket_adapter(fsm)
    _wire_guardian(fsm)
    _wire_bracket_config(fsm)
    fsm._preflight_position_check = AsyncMock(return_value=True)
    fsm.shadow_mode = False

    fsm.watchdog = MagicMock()
    fsm.watchdog.pending_orders = {order_id: SimpleNamespace(symbol=symbol, rid="rid-btc-fill")}
    fsm.watchdog.acked_orders = {}

    fsm._cancel_order = AsyncMock(
        return_value=IdempotentCancelResult(
            success=True,
            reason="PRE_CHECK_TERMINAL_FILLED",
            order_status_before="FILLED",
            order_status_after="FILLED",
            is_idempotent_success=True,
            order_data={
                "orderId": order_id,
                "symbol": symbol,
                "status": "FILLED",
                "executedQty": "0.004",
                "avgPrice": "65971.7",
                "side": "BUY",
                "clientOrderId": "ENTRY-ac29a621d84c",
            },
        )
    )

    submitted = _capture_submitted_coroutines(fsm)
    with patch("apps.reference.domains.execution_position.fsm.write_pending_brackets_cleared") as clear_mock, patch(
        "apps.reference.domains.execution_position.fsm.order_logger.write"
    ):
        fsm._cancel_pending_entries_for_symbol(
            symbol=symbol,
            reason="CANCEL_SUPERSEDED",
            context="test_cancel_path_terminal_filled",
        )
        await _drain_submitted(submitted)

    assert fsm.adapter.place_stop_market_close_position.call_count == 1
    assert fsm.adapter.place_take_profit_market_close_position.call_count == 1
    assert fsm.order_guardian.register_bracket.call_count == 2
    assert order_id not in fsm._pending_brackets

    clear_reasons = [str(call.kwargs.get("reason", "")) for call in clear_mock.call_args_list]
    assert clear_reasons
    assert "cancelled" not in clear_reasons


@pytest.mark.asyncio
async def test_timeout_path_recovery_stays_intact(fsm_harness):
    fsm, _, _ = fsm_harness
    order_id = "12515510665"
    symbol = "BTCUSDT"

    fsm._pending_brackets.clear()
    _seed_pending_brackets(fsm, entry_order_id=order_id, symbol=symbol)
    _wire_bracket_adapter(fsm)
    _wire_guardian(fsm)
    _wire_bracket_config(fsm)
    fsm._preflight_position_check = AsyncMock(return_value=True)
    fsm.shadow_mode = False
    fsm.handle = MagicMock()

    fsm.watchdog = MagicMock()
    fsm.watchdog.cancel_attempt_count = 0
    fsm.watchdog.cancel_success_count = 0

    fsm._cancel_order = AsyncMock(
        return_value=IdempotentCancelResult(
            success=True,
            reason="PRE_CHECK_TERMINAL_FILLED",
            order_status_before="FILLED",
            order_status_after="FILLED",
            is_idempotent_success=True,
            order_data={
                "orderId": order_id,
                "symbol": symbol,
                "status": "FILLED",
                "executedQty": "0.004",
                "avgPrice": "66111.0",
                "side": "BUY",
                "clientOrderId": "ENTRY-xyz",
            },
        )
    )

    deadline = SimpleNamespace(
        order_id=order_id,
        symbol=symbol,
        timeout_type=SimpleNamespace(value="fill_timeout"),
        corr_id="corr-timeout",
        rid="rid-timeout",
        client_order_id="ENTRY-xyz",
    )

    submitted = _capture_submitted_coroutines(fsm)
    with patch("apps.reference.domains.execution_position.fsm.order_logger.write"):
        await fsm._handle_order_timeout(deadline)
        await _drain_submitted(submitted)

    assert fsm.adapter.place_stop_market_close_position.call_count == 1
    assert fsm.adapter.place_take_profit_market_close_position.call_count == 1
    assert fsm.order_guardian.register_bracket.call_count == 2
    assert order_id not in fsm._pending_brackets


@pytest.mark.asyncio
async def test_no_double_bracket_placement_when_two_paths_fire(fsm_harness):
    fsm, _, _ = fsm_harness
    order_id = "12539248014"

    fsm._pending_brackets.clear()
    bracket_data = _seed_pending_brackets(fsm, entry_order_id=order_id)
    _wire_bracket_adapter(fsm)
    _wire_guardian(fsm)
    _wire_bracket_config(fsm)
    fsm._preflight_position_check = AsyncMock(return_value=True)
    fsm.shadow_mode = False
    fsm.config.get_domain_mode.return_value = "live"

    await fsm._place_deferred_brackets(order_id, bracket_data)
    assert fsm.adapter.place_stop_market_close_position.call_count == 1
    assert fsm.adapter.place_take_profit_market_close_position.call_count == 1

    sl_msg = Message(
        op="DEC",
        verb="PLACE_ORDER",
        src="execution_position",
        dst="execution_position",
        rid="rid-race-sl",
        pld={
            "symbol": "BTCUSDT",
            "side": "SELL",
            "qty": "0.004",
            "order_type": "STOP_MARKET",
            "stopPrice": "65641.8",
            "reduceOnly": True,
            "newClientOrderId": "SL-RACE-01",
            "parent_order_id": order_id,
        },
    )
    tp_msg = Message(
        op="DEC",
        verb="PLACE_ORDER",
        src="execution_position",
        dst="execution_position",
        rid="rid-race-tp",
        pld={
            "symbol": "BTCUSDT",
            "side": "SELL",
            "qty": "0.004",
            "order_type": "TAKE_PROFIT_MARKET",
            "stopPrice": "66466.5",
            "reduceOnly": True,
            "newClientOrderId": "TP-RACE-01",
            "parent_order_id": order_id,
        },
    )

    await fsm._execute_decision(sl_msg)
    await fsm._execute_decision(tp_msg)

    assert fsm.adapter.place_stop_market_close_position.call_count == 1
    assert fsm.adapter.place_take_profit_market_close_position.call_count == 1


@pytest.mark.asyncio
async def test_partial_brackets_case(fsm_harness):
    fsm, _, _ = fsm_harness
    order_id = "12508695170"

    fsm._pending_brackets.clear()
    bracket_data = _seed_pending_brackets(fsm, entry_order_id=order_id)
    _wire_bracket_adapter(fsm)
    _wire_guardian(fsm)
    _wire_bracket_config(fsm)
    fsm._preflight_position_check = AsyncMock(return_value=True)
    fsm.adapter.place_stop_market_close_position = AsyncMock(
        side_effect=BinanceAPIError(code=-2021, msg="Order would immediately trigger")
    )
    fsm.adapter.place_take_profit_market_close_position = AsyncMock(
        return_value={"orderId": "TP-9001"}
    )
    fsm._emit_observability_event = MagicMock()

    await fsm._place_deferred_brackets(order_id, bracket_data)

    assert fsm.adapter.place_stop_market_close_position.call_count == 1
    assert fsm.adapter.place_take_profit_market_close_position.call_count == 1
    assert fsm._emit_observability_event.call_count >= 1

    event_types = [str(call.args[0]) for call in fsm._emit_observability_event.call_args_list if call.args]
    assert "FILLED_ENTRY_WITHOUT_BRACKETS" in event_types
    assert fsm._filled_entries_missing_brackets
    assert any(
        entry.get("parent_order_id") == order_id and entry.get("missing_count") == 1
        for entry in fsm._filled_entries_missing_brackets.values()
    )


@pytest.mark.asyncio
async def test_wal_replay_after_restart_places_missing_brackets(fsm_harness):
    fsm, _, _ = fsm_harness
    order_id = "1730380112"

    fsm._pending_brackets.clear()
    _seed_pending_brackets(fsm, entry_order_id=order_id, symbol="SOLUSDT", side="SELL")
    _wire_bracket_adapter(fsm)
    _wire_guardian(fsm)
    _wire_bracket_config(fsm)
    fsm._preflight_position_check = AsyncMock(return_value=True)

    fsm.adapter.get_order = AsyncMock(
        return_value={
            "orderId": order_id,
            "symbol": "SOLUSDT",
            "status": "FILLED",
            "executedQty": "2.0",
            "avgPrice": "130.0",
            "side": "SELL",
            "clientOrderId": "ENTRY-sol-123",
        }
    )
    fsm.adapter.get_open_positions = AsyncMock(return_value=[])
    fsm.adapter.get_open_orders = AsyncMock(return_value=[])

    with patch("apps.reference.domains.execution_position.fsm.write_pending_brackets_cleared") as clear_mock:
        await fsm._startup_order_guardian_reconcile()

    assert fsm.adapter.place_stop_market_close_position.call_count == 1
    assert fsm.adapter.place_take_profit_market_close_position.call_count == 1
    assert order_id not in fsm._pending_brackets
    assert clear_mock.call_count >= 1
