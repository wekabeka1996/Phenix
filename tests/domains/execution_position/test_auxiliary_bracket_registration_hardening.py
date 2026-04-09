from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from apps.reference.domains.execution_position.close_executor import CloseExecutor
from apps.reference.domains.execution_position.fsm_manage import ManageFlowFSM, ManageState
from vfoundation.core.protocol import Message


def _make_manage_flow(*, state=ManageState.TRACKING) -> MagicMock:
    manage_flow = MagicMock()
    manage_flow.state = state
    manage_flow.entry_order_id = "entry-1"
    manage_flow.sl_algo_client_id = None
    manage_flow.tp_algo_client_id = None
    manage_flow.set_bracket_ids = MagicMock()
    return manage_flow


def _make_fsm(*, symbol: str = "BTCUSDT", manage_flow: MagicMock | None = None):
    manage_flow = manage_flow or _make_manage_flow()
    order_index = MagicMock()
    guardian = MagicMock()
    adapter = SimpleNamespace(
        place_stop_market_close_position=AsyncMock(),
        place_take_profit_market_close_position=AsyncMock(),
        place_limit_reduce_only=AsyncMock(),
        place_order=AsyncMock(),
    )
    fsm = SimpleNamespace(
        adapter=adapter,
        manage_flows={symbol: manage_flow},
        _symbol_brackets={},
        order_index=order_index,
        fsm=SimpleNamespace(order_index=order_index),
        order_guardian=guardian,
        _persist_restore_artifact_snapshot=MagicMock(),
    )

    def _set_symbol_bracket_order(
        tracked_symbol: str,
        *,
        order_role: str,
        order_id: str,
        truth_source: str = "RUNTIME_LOCAL",
    ) -> None:
        brackets = fsm._symbol_brackets.setdefault(tracked_symbol, {})
        if order_role == "SL":
            brackets["sl_order_id"] = order_id
        elif order_role == "TP":
            brackets["tp_order_id"] = order_id

    fsm._set_symbol_bracket_order = _set_symbol_bracket_order
    return fsm, manage_flow, order_index, guardian


@pytest.mark.asyncio
async def test_auxiliary_sl_place_order_uses_canonical_registration_contract() -> None:
    fsm, manage_flow, order_index, guardian = _make_fsm()
    fsm.adapter.place_stop_market_close_position.return_value = {
        "orderId": "5001",
        "clientAlgoId": "SL-algo-5001",
    }
    executor = CloseExecutor(fsm)
    decision = SimpleNamespace(
        pld={
            "symbol": "BTCUSDT",
            "side": "SELL",
            "qty": "0.10",
            "order_type": "STOP_MARKET",
            "stopPrice": "99.0",
            "newClientOrderId": "SL-aux-1",
        },
        rid="rid-aux-sl",
        corr_id="corr-aux-sl",
        idempotent_key=None,
    )

    await executor.execute_place_order(decision)

    assert fsm._symbol_brackets["BTCUSDT"]["sl_order_id"] == "5001"
    assert order_index.register_bracket_child.call_count == 2
    primary_call = order_index.register_bracket_child.call_args_list[0].kwargs
    secondary_call = order_index.register_bracket_child.call_args_list[1].kwargs
    assert primary_call["clientOrderId"] == "SL-algo-5001"
    assert primary_call["exchangeOrderId"] == "5001"
    assert primary_call["order_kind"] == "SL"
    assert secondary_call["clientOrderId"] == "SL-aux-1"
    guardian.register_bracket.assert_called_once_with(
        symbol="BTCUSDT",
        parent_order_id="entry-1",
        order_id="5001",
        client_order_id="SL-aux-1",
        kind="SL",
        corr_id="corr-aux-sl",
        rid="rid-aux-sl",
    )
    manage_flow.set_bracket_ids.assert_called_once_with(
        sl_order_id="5001",
        tp_order_id=None,
        sl_algo_client_id="SL-algo-5001",
        tp_algo_client_id=None,
    )
    fsm._persist_restore_artifact_snapshot.assert_called_once_with(
        trigger="close_executor:aux_bracket_registered",
        allow_empty=True,
    )


@pytest.mark.asyncio
async def test_auxiliary_tp1_place_order_no_longer_depends_on_legacy_substring_matching() -> None:
    manage_flow = _make_manage_flow()
    manage_flow.sl_algo_client_id = "SL-algo-existing"
    fsm, manage_flow, order_index, guardian = _make_fsm(
        manage_flow=manage_flow)
    fsm._symbol_brackets["BTCUSDT"] = {"sl_order_id": "5001"}
    fsm.adapter.place_take_profit_market_close_position.return_value = {
        "orderId": "6001",
        "clientAlgoId": "TP1-algo-6001",
    }
    executor = CloseExecutor(fsm)
    decision = SimpleNamespace(
        pld={
            "symbol": "BTCUSDT",
            "side": "SELL",
            "qty": "0.05",
            "order_type": "TAKE_PROFIT_MARKET",
            "stopPrice": "101.0",
            "newClientOrderId": "TP1-aux-1",
        },
        rid="rid-aux-tp1",
        corr_id="corr-aux-tp1",
        idempotent_key=None,
    )

    await executor.execute_place_order(decision)

    assert fsm._symbol_brackets["BTCUSDT"]["tp_order_id"] == "6001"
    assert order_index.register_bracket_child.call_count == 2
    primary_call = order_index.register_bracket_child.call_args_list[0].kwargs
    secondary_call = order_index.register_bracket_child.call_args_list[1].kwargs
    assert primary_call["clientOrderId"] == "TP1-algo-6001"
    assert primary_call["order_kind"] == "TP"
    assert secondary_call["clientOrderId"] == "TP1-aux-1"
    guardian.register_bracket.assert_called_once_with(
        symbol="BTCUSDT",
        parent_order_id="entry-1",
        order_id="6001",
        client_order_id="TP1-aux-1",
        kind="TP",
        corr_id="corr-aux-tp1",
        rid="rid-aux-tp1",
    )
    manage_flow.set_bracket_ids.assert_called_once_with(
        sl_order_id="5001",
        tp_order_id="6001",
        sl_algo_client_id="SL-algo-existing",
        tp_algo_client_id="TP1-algo-6001",
    )


@pytest.mark.asyncio
async def test_noncanonical_reduce_only_place_order_does_not_mutate_bracket_truth() -> None:
    fsm, manage_flow, order_index, guardian = _make_fsm()
    fsm.adapter.place_limit_reduce_only.return_value = {"orderId": "7001"}
    executor = CloseExecutor(fsm)
    decision = SimpleNamespace(
        pld={
            "symbol": "BTCUSDT",
            "side": "SELL",
            "qty": "0.10",
            "order_type": "LIMIT",
            "price": "102.0",
            "reduceOnly": True,
            "newClientOrderId": "manual_limit_1",
        },
        rid="rid-manual-limit",
        corr_id=None,
        idempotent_key=None,
    )

    await executor.execute_place_order(decision)

    assert fsm._symbol_brackets == {}
    order_index.register_bracket_child.assert_not_called()
    order_index.upsert_from_open.assert_called_once()
    order_index.attach_exchange_id.assert_called_once_with(
        clientOrderId="manual_limit_1",
        exchangeOrderId="7001",
    )
    guardian.register_bracket.assert_not_called()
    manage_flow.set_bracket_ids.assert_not_called()
    fsm._persist_restore_artifact_snapshot.assert_not_called()


def test_emergency_stop_emit_uses_canonical_sl_prefix(fsm_config) -> None:
    fsm_config.trading.execution.manage.emergency.enabled = True
    manage = ManageFlowFSM(config=fsm_config)
    manage.state = ManageState.TRACKING
    manage.symbol = "BTCUSDT"
    manage.position_side = "BUY"
    manage.position_qty = Decimal("0.10")
    manage.position_entry_price = Decimal("100.0")
    manage.position_open_ts = 1.0
    manage._bar_ms = 300000
    manage._wait_mode_bars = 2

    msg = Message(
        op="UPD",
        verb="MARKET_DATA",
        src="ws",
        dst="execution_position",
        rid="rid-emergency",
        why="test_emergency_stop",
        pld={
            "symbol": "BTCUSDT",
            "price": "98.0",
            "ts": 1770000000000,
        },
        data_ref=[],
    )

    result = manage._check_rules(msg)

    assert result is not None
    assert result.verb == "PLACE_ORDER"
    client_order_id = result.pld["newClientOrderId"]
    assert client_order_id.startswith("SL-")
    assert "_emergency_sl" not in client_order_id


@pytest.mark.parametrize(
    ("client_order_id", "expected_attr"),
    [
        ("TP1-placed-1", "tp1_order_id"),
        ("TP2-placed-1", "tp2_order_id"),
    ],
)
def test_on_bracket_placed_uses_canonical_prefix_roles_for_tp_variants(
    fsm_config,
    client_order_id: str,
    expected_attr: str,
) -> None:
    manage = ManageFlowFSM(config=fsm_config)
    manage.state = ManageState.BRACKETS_PENDING

    sl_msg = Message(
        op="EVT",
        verb="ORDER_UPDATED",
        src="adapter",
        dst="execution_position",
        rid="rid-sl",
        why="sl_placed",
        pld={"clientOrderId": "SL-placed-1", "orderId": "5001"},
        data_ref=[],
    )
    tp_msg = Message(
        op="EVT",
        verb="ORDER_UPDATED",
        src="adapter",
        dst="execution_position",
        rid="rid-tp",
        why="tp_placed",
        pld={"clientOrderId": client_order_id, "orderId": "6001"},
        data_ref=[],
    )

    manage._on_bracket_placed(sl_msg)
    manage._on_bracket_placed(tp_msg)

    assert manage.sl_order_id == "5001"
    assert getattr(manage, expected_attr) == "6001"
    assert manage.tp_order_id == "6001"
    assert manage.state == ManageState.BRACKETS_PLACED
