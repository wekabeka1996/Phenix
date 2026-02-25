from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from vfoundation.core.protocol import Message


def _wire_adapter_for_tp(fsm) -> None:
    adapter = MagicMock()
    adapter.base_url = "https://fapi.binance.com"
    adapter.place_take_profit_market_close_position = AsyncMock(
        side_effect=[{"orderId": "TP-1"}, {"orderId": "TP-2"}]
    )
    fsm.adapter = adapter


def _wire_guardian(fsm) -> None:
    fsm.order_guardian.register_bracket = MagicMock()
    fsm.order_guardian.get_brackets_for_entry = MagicMock(return_value={})


def _tp_decision(*, rid: str, client_id: str, parent_order_id: str) -> Message:
    return Message(
        op="DEC",
        verb="PLACE_ORDER",
        src="execution_position",
        dst="execution_position",
        rid=rid,
        pld={
            "symbol": "BTCUSDT",
            "side": "SELL",
            "qty": "0.004",
            "order_type": "TAKE_PROFIT_MARKET",
            "stopPrice": "66466.5",
            "reduceOnly": True,
            "newClientOrderId": client_id,
            "parent_order_id": parent_order_id,
        },
    )


@pytest.mark.asyncio
async def test_multi_tp_dedup_allows_tp1_tp2_independently(fsm_harness):
    fsm, _, _ = fsm_harness
    parent_order_id = "12539847754"
    fsm.config.get_domain_mode.return_value = "live"

    _wire_adapter_for_tp(fsm)
    _wire_guardian(fsm)

    tp1 = _tp_decision(
        rid="rid-tp-1",
        client_id="TP-BTCUSDT-demo_1",
        parent_order_id=parent_order_id,
    )
    tp2 = _tp_decision(
        rid="rid-tp-2",
        client_id="TP-BTCUSDT-demo_2",
        parent_order_id=parent_order_id,
    )

    await fsm._execute_decision(tp1)
    await fsm._execute_decision(tp2)

    assert fsm.adapter.place_take_profit_market_close_position.call_count == 2
    tp1_key = fsm._bracket_place_key("BTCUSDT", parent_order_id, "TP", "1")
    tp2_key = fsm._bracket_place_key("BTCUSDT", parent_order_id, "TP", "2")
    assert tp1_key in fsm._bracket_place_completed
    assert tp2_key in fsm._bracket_place_completed


@pytest.mark.asyncio
async def test_multi_tp_duplicate_tp1_is_deduped(fsm_harness):
    fsm, _, _ = fsm_harness
    parent_order_id = "12539847754"
    fsm.config.get_domain_mode.return_value = "live"

    _wire_adapter_for_tp(fsm)
    _wire_guardian(fsm)

    tp1_a = _tp_decision(
        rid="rid-tp1-a",
        client_id="TP-BTCUSDT-dup_1",
        parent_order_id=parent_order_id,
    )
    tp1_b = _tp_decision(
        rid="rid-tp1-b",
        client_id="TP-BTCUSDT-dup_1",
        parent_order_id=parent_order_id,
    )

    await fsm._execute_decision(tp1_a)
    await fsm._execute_decision(tp1_b)

    assert fsm.adapter.place_take_profit_market_close_position.call_count == 1
