from decimal import Decimal

from vfoundation.core.protocol import Message

from apps.reference.domains.execution_position.fsm_manage import (
    ManageFlowFSM,
    ManageState,
)


def _exit_fill_message(symbol: str = "BTCUSDT") -> Message:
    return Message(
        op="EVT",
        verb="TRADE_EXECUTED",
        src="adapter",
        dst="execution_position",
        rid="rid-exit-fill",
        why="test_exit_fill",
        pld={
            "symbol": symbol,
            "orderId": "tp-order",
            "clientOrderId": "TP1-test",
            "client_order_id": "TP1-test",
            "side": "SELL",
            "qty": "0.01",
            "quantity": "0.01",
            "price": "1000",
            "order_type": "TAKE_PROFIT_MARKET",
            "reduceOnly": True,
        },
    )


def test_flat_exit_fill_clears_lifecycle_residue(fsm_config) -> None:
    manage = ManageFlowFSM(config=fsm_config)
    manage.state = ManageState.FLAT
    manage.symbol = "BTCUSDT"
    manage.position_qty = Decimal("0.01")
    manage.position_entry_price = Decimal("1000")
    manage.position_side = "BUY"
    manage.entry_order_id = "entry-order"
    manage.entry_client_order_id = "ENTRY-1"
    manage.sl_order_id = "sl-order"
    manage.tp_order_id = "tp-order"
    manage.tp1_order_id = "tp1-order"
    manage.tp2_order_id = "tp2-order"
    manage.sl_price = Decimal("990")
    manage.tp_price = Decimal("1010")
    manage.tp1_price = Decimal("1010")
    manage.tp2_price = Decimal("1020")
    manage._closing_position = True
    manage._closing_position_ts = 123.0

    out = manage.handle(_exit_fill_message())

    assert out is None
    assert manage.state == ManageState.FLAT
    assert manage.has_active_lifecycle() is False
    assert manage.symbol is None
    assert manage.entry_order_id is None
    assert manage.sl_order_id is None
    assert manage.tp1_order_id is None
    assert manage.tp2_order_id is None
    assert manage._closing_position is False


def test_local_open_guard_allows_flat_flat_when_no_residue(fsm_harness) -> None:
    fsm, _, _ = fsm_harness
    symbol = "BTCUSDT"
    manage_flow = fsm.manage_flow(symbol)
    manage_flow.state = ManageState.FLAT
    manage_flow.symbol = symbol
    manage_flow.reset()

    msg = Message(
        op="CMD",
        verb="OPEN",
        src="decision_making",
        dst="execution_position",
        rid="rid-open-clean",
        why="test_open",
        pld={"symbol": symbol, "side": "BUY", "qty": "0.01", "price": "1000"},
    )

    assert fsm._local_open_guard(msg, manage_flow) is None


def test_local_open_guard_blocks_real_active_lifecycle(fsm_harness) -> None:
    fsm, bus, _ = fsm_harness
    symbol = "BTCUSDT"
    manage_flow = fsm.manage_flow(symbol)
    manage_flow.state = ManageState.TRACKING
    manage_flow.symbol = symbol
    manage_flow.position_qty = Decimal("0.01")
    manage_flow.entry_order_id = "entry-order"

    msg = Message(
        op="CMD",
        verb="OPEN",
        src="decision_making",
        dst="execution_position",
        rid="rid-open-conflict",
        why="test_open",
        pld={"symbol": symbol, "side": "BUY", "qty": "0.01", "price": "1000"},
    )

    out = fsm._local_open_guard(msg, manage_flow)

    assert out is not None
    assert out.pld["reason"] == "local_manage_state_conflict"
    guard_payload = next(
        args[0]
        for topic, args, _kwargs in bus.events
        if topic == "EVT:EXECUTION_GUARD_BLOCKED"
    )
    assert guard_payload["has_active_lifecycle"] is True
    assert guard_payload["entry_order_id"] == "entry-order"
    assert guard_payload["position_qty"] == "0.01"
