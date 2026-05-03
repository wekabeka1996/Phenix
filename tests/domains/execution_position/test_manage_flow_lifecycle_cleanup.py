from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from vfoundation.core.protocol import Message

from apps.reference.domains.execution_position.flows.close.fsm_close import CloseState
from apps.reference.domains.execution_position.flows.manage.fsm_manage import (
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


def test_authoritative_local_close_reset_clears_runtime_residue_and_is_idempotent(
    fsm_harness,
) -> None:
    fsm, _, _ = fsm_harness
    symbol = "BTCUSDT"
    manage_flow = fsm.manage_flow(symbol)
    close_flow = fsm.close_flow(symbol)

    manage_flow.state = ManageState.BRACKETS_PENDING
    manage_flow.symbol = symbol
    manage_flow.position_qty = Decimal("0.01")
    manage_flow.position_entry_price = Decimal("1000")
    manage_flow.position_side = "BUY"
    manage_flow.entry_order_id = "entry-order"
    manage_flow.entry_client_order_id = "ENTRY-1"
    manage_flow.sl_order_id = "sl-order"
    manage_flow.tp_order_id = "tp-order"

    close_flow.state = CloseState.OPENED
    close_flow.position_active = True
    close_flow.last_close_reason = "position_policy_sidecar_soft_close"

    fsm._set_symbol_brackets_snapshot(
        symbol,
        sl_order_id="sl-order",
        tp_order_id="tp-order",
    )
    fsm._pending_brackets["entry-order"] = {
        "symbol": symbol,
        "sl_price": "990",
        "tp_price": "1010",
    }

    with patch(
        "apps.reference.domains.execution_position.fsm.write_pending_brackets_cleared"
    ) as pending_cleared:
        changed = fsm._apply_authoritative_local_close_reset(
            symbol,
            reason="unit_test_reset",
            source="unit_test",
        )

        assert changed is True
        assert manage_flow.state == ManageState.FLAT
        assert manage_flow.has_active_lifecycle() is False
        assert manage_flow.symbol is None
        assert close_flow.state == CloseState.FLAT
        assert close_flow.last_close_reason is None
        assert symbol not in fsm._symbol_brackets
        assert symbol not in fsm._symbol_bracket_truth_source
        assert "entry-order" not in fsm._pending_brackets
        pending_cleared.assert_called_once_with(
            entry_order_id="entry-order",
            reason="unit_test_reset",
            symbol=symbol,
        )

        changed_again = fsm._apply_authoritative_local_close_reset(
            symbol,
            reason="unit_test_reset",
            source="unit_test",
        )
        assert changed_again is False
        pending_cleared.assert_called_once()


def test_portfolio_close_reset_allows_follow_on_open_guard(fsm_harness) -> None:
    fsm, _, _ = fsm_harness
    symbol = "BTCUSDT"
    manage_flow = fsm.manage_flow(symbol)
    close_flow = fsm.close_flow(symbol)

    manage_flow.state = ManageState.BRACKETS_PENDING
    manage_flow.symbol = symbol
    manage_flow.position_qty = Decimal("0.01")
    manage_flow.position_entry_price = Decimal("1000")
    manage_flow.position_side = "BUY"
    manage_flow.entry_order_id = "entry-order"
    manage_flow.entry_client_order_id = "ENTRY-1"
    manage_flow.sl_order_id = "sl-order"
    manage_flow.tp_order_id = "tp-order"

    close_flow.state = CloseState.OPENED
    close_flow.position_active = True
    close_flow.last_close_reason = "position_policy_sidecar_soft_close"

    fsm._set_symbol_brackets_snapshot(
        symbol,
        sl_order_id="sl-order",
        tp_order_id="tp-order",
    )
    fsm._pending_brackets["entry-order"] = {
        "symbol": symbol,
        "sl_price": "990",
        "tp_price": "1010",
    }
    fsm._prev_position_amts = {symbol: 0.01}
    fsm._last_lifecycle_rid_by_symbol[symbol] = "rid-close"
    fsm._last_lifecycle_fill_price_by_symbol[symbol] = Decimal("1001")
    fsm._last_lifecycle_ikey_by_symbol[symbol] = "lifecycle-1"
    fsm._last_trade_id_by_symbol[symbol] = "trade-1"
    fsm._last_entry_side_by_symbol[symbol] = "BUY"
    fsm._accumulated_fees_by_symbol[symbol] = 0.25
    fsm._get_async_loop = MagicMock(return_value=None)

    event = Message(
        op="EVT",
        verb="PORTFOLIO_STATE_UPDATED",
        src="portfolio",
        dst="execution_position",
        rid="rid-portfolio-close",
        why="test_portfolio_close",
        pld={
            "positions_last_ts_ms": 1_000_000,
            "positions": [],
        },
    )

    with patch(
        "apps.reference.domains.execution_position.orchestration.event_handlers._trade_lifecycle",
        SimpleNamespace(on_close=lambda **kwargs: None),
    ), patch(
        "apps.reference.domains.execution_position.orchestration.event_handlers._get_order_logger",
        return_value=SimpleNamespace(write=lambda payload: None),
    ), patch(
        "apps.reference.domains.execution_position.fsm.write_pending_brackets_cleared"
    ) as pending_cleared:
        fsm._evt_handlers.on_portfolio_state_updated(event)

    assert manage_flow.state == ManageState.FLAT
    assert manage_flow.has_active_lifecycle() is False
    assert close_flow.state == CloseState.FLAT
    assert symbol not in fsm._symbol_brackets
    assert symbol not in fsm._symbol_bracket_truth_source
    assert "entry-order" not in fsm._pending_brackets
    pending_cleared.assert_called_once_with(
        entry_order_id="entry-order",
        reason="position_closed_detected",
        symbol=symbol,
    )

    msg = Message(
        op="CMD",
        verb="OPEN",
        src="decision_making",
        dst="execution_position",
        rid="rid-open-after-close",
        why="test_open_after_close",
        pld={"symbol": symbol, "side": "BUY", "qty": "0.01", "price": "1000"},
    )
    assert fsm._local_open_guard(msg, manage_flow) is None
