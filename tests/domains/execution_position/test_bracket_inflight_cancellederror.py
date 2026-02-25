from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest


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


@pytest.mark.asyncio
async def test_inflight_released_on_cancelled_error_deferred_sl(fsm_harness):
    fsm, _, _ = fsm_harness
    order_id = "12539847754"
    symbol = "BTCUSDT"

    bracket_data = _seed_pending_brackets(fsm, entry_order_id=order_id, symbol=symbol)
    _wire_bracket_adapter(fsm)
    _wire_guardian(fsm)
    _wire_bracket_config(fsm)
    fsm._preflight_position_check = AsyncMock(return_value=True)
    fsm.adapter.place_stop_market_close_position = AsyncMock(
        side_effect=asyncio.CancelledError()
    )

    sl_key = fsm._bracket_place_key(symbol, order_id, "SL")

    with pytest.raises(asyncio.CancelledError):
        await fsm._place_deferred_brackets(order_id, bracket_data)

    assert sl_key not in fsm._bracket_place_inflight


@pytest.mark.asyncio
async def test_inflight_released_on_cancelled_error_deferred_tp(fsm_harness):
    fsm, _, _ = fsm_harness
    order_id = "12539847754"
    symbol = "BTCUSDT"

    bracket_data = _seed_pending_brackets(fsm, entry_order_id=order_id, symbol=symbol)
    _wire_bracket_adapter(fsm)
    _wire_guardian(fsm)
    _wire_bracket_config(fsm)
    fsm._preflight_position_check = AsyncMock(return_value=True)
    fsm.adapter.place_take_profit_market_close_position = AsyncMock(
        side_effect=asyncio.CancelledError()
    )

    tp_key = fsm._bracket_place_key(symbol, order_id, "TP")

    with pytest.raises(asyncio.CancelledError):
        await fsm._place_deferred_brackets(order_id, bracket_data)

    assert tp_key not in fsm._bracket_place_inflight


@pytest.mark.asyncio
async def test_inflight_released_on_generic_exception(fsm_harness):
    fsm, _, _ = fsm_harness
    order_id = "12539847754"
    symbol = "BTCUSDT"

    bracket_data = _seed_pending_brackets(fsm, entry_order_id=order_id, symbol=symbol)
    _wire_bracket_adapter(fsm)
    _wire_guardian(fsm)
    _wire_bracket_config(fsm)
    fsm._preflight_position_check = AsyncMock(return_value=True)
    fsm.adapter.place_stop_market_close_position = AsyncMock(
        side_effect=Exception("boom")
    )

    sl_key = fsm._bracket_place_key(symbol, order_id, "SL")

    await fsm._place_deferred_brackets(order_id, bracket_data)

    assert sl_key not in fsm._bracket_place_inflight
