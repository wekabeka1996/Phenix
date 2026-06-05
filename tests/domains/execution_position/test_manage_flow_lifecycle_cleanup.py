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


def _close_reconciled_message(symbol: str = "BTCUSDT", rid: str = "rid-close-reconciled") -> Message:
    return Message(
        op="EVT",
        verb="EXECUTION_CLOSE_RECONCILED",
        src="execution_position",
        dst="execution_position",
        rid=rid,
        why="guardian:close_reconciled",
        pld={
            "symbol": symbol,
            "rid": rid,
            "source": "guardian_reconcile",
            "ts_ms": 1_775_000_000_000,
            "business_close_reconciled": True,
            "why": "guardian:close_reconciled",
        },
    )


def _prime_stale_brackets_pending(fsm, symbol: str = "BTCUSDT"):
    manage_flow = fsm.manage_flow(symbol)
    manage_flow.state = ManageState.BRACKETS_PENDING
    manage_flow.symbol = symbol
    manage_flow.position_qty = Decimal("0.01")
    manage_flow.position_entry_price = Decimal("1000")
    manage_flow.position_side = "BUY"
    manage_flow.position_open_ts = 123.0
    manage_flow.entry_order_id = "entry-order"
    manage_flow.entry_client_order_id = "ENTRY-1"
    manage_flow.sl_order_id = "sl-order"
    manage_flow.tp_order_id = "tp-order"
    manage_flow.tp1_order_id = "tp1-order"
    manage_flow.tp2_order_id = "tp2-order"
    fsm._last_lifecycle_rid_by_symbol[symbol] = "rid-stale"
    fsm._last_lifecycle_ikey_by_symbol[symbol] = "lifecycle-stale"
    fsm._last_entry_side_by_symbol[symbol] = "BUY"
    fsm._set_symbol_brackets_snapshot(
        symbol,
        sl_order_id="sl-order",
        tp_order_id="tp-order",
    )
    return manage_flow


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


def test_execution_close_reconciled_clears_local_lifecycle_and_reopen_guard(fsm_harness) -> None:
    fsm, _, _ = fsm_harness
    symbol = "BTCUSDT"
    manage_flow = _prime_stale_brackets_pending(fsm, symbol)
    fsm._latest_portfolio_state = {
        "positions": [{"symbol": symbol, "positionAmt": "0"}],
        "positions_last_ts_ms": 1_775_000_000_000,
    }

    fsm._on_execution_close_reconciled(_close_reconciled_message(symbol=symbol))

    assert manage_flow.state == ManageState.FLAT
    assert manage_flow.has_active_lifecycle() is False
    assert manage_flow.symbol is None
    assert manage_flow.entry_order_id is None
    assert manage_flow.sl_order_id is None
    assert manage_flow.tp_order_id is None
    assert symbol not in fsm._symbol_brackets
    assert symbol not in fsm._last_lifecycle_rid_by_symbol
    assert symbol not in fsm._last_lifecycle_ikey_by_symbol

    msg = Message(
        op="CMD",
        verb="OPEN",
        src="decision_making",
        dst="execution_position",
        rid="rid-open-after-reconcile",
        why="test_open",
        pld={"symbol": symbol, "side": "BUY", "qty": "0.01", "price": "1000"},
    )

    assert fsm._local_open_guard(msg, manage_flow) is None


def test_execution_close_reconciled_removes_symbol_from_restore_artifact_records(fsm_harness) -> None:
    fsm, _, _ = fsm_harness
    symbol = "BTCUSDT"
    _prime_stale_brackets_pending(fsm, symbol)

    before = [
        record.model_dump(mode="json", exclude_none=True)
        for record in fsm._build_execution_restore_artifact_records()
    ]
    assert any(record["symbol"] == symbol for record in before)

    fsm._on_execution_close_reconciled(_close_reconciled_message(symbol=symbol))

    after = [
        record.model_dump(mode="json", exclude_none=True)
        for record in fsm._build_execution_restore_artifact_records()
    ]
    assert not any(record["symbol"] == symbol for record in after)
