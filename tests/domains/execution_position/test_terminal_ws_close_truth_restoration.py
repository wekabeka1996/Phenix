import json
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock

from vfoundation.core.protocol import Message

from apps.reference.core.time import get_clock
from apps.reference.domains.execution_position.fsm_manage import ManageState


def test_recovered_sl_fill_flattens_manage_lifecycle_and_records_close_proof(
    fsm_harness,
    tmp_path: Path,
) -> None:
    fsm, _, cfg = fsm_harness
    symbol = "ETHUSDT"
    log_path = tmp_path / "trade_lifecycle.jsonl"
    fsm._trade_lifecycle_log_path = lambda: str(log_path)
    eth_spec = MagicMock()
    eth_spec.execution.target_leverage = 20
    cfg.instruments["ETHUSDT"] = eth_spec

    manage = fsm.manage_flow(symbol)
    manage.symbol = symbol
    manage.state = ManageState.BRACKETS_PLACED
    manage.position_qty = Decimal("0.10")
    manage.position_entry_price = Decimal("2000")
    manage.position_side = "BUY"
    manage.position_open_ts = get_clock().now_sec() - 5
    manage.entry_order_id = "entry-eth-1"
    manage.entry_client_order_id = "ENTRY-ETHUSDT-1"
    manage.sl_order_id = "1000000041481020"
    manage.tp_order_id = "1000000041481025"

    event = Message(
        op="EVT",
        verb="TRADE_EXECUTED",
        src="binance_ws_client",
        dst="execution_position",
        rid="aurora_ETHUSDT_1775247901546",
        why="WS_ORDER_UPDATE_FILLED",
        pld={
            "symbol": symbol,
            "orderId": "8631145709",
            "exchangeOrderId": "8631145709",
            "clientOrderId": "SJGknqkssjcrviz2pCUMMi",
            "client_order_id": "SJGknqkssjcrviz2pCUMMi",
            "side": "SELL",
            "qty": "0.10",
            "quantity": "0.10",
            "price": "1990.0",
            "status": "FILLED",
            "order_type": "STOP_MARKET",
            "close_reason": "SL",
            "bracket_role": "SL",
            "tracked_bracket_order_id": "1000000041481020",
            "parent_entry_order_id": "entry-eth-1",
            "terminal_correlation_source": "order_guardian_client_order_id",
            "correlation_recovered": True,
            "ts_ms": get_clock().now_ms(),
            "ts": get_clock().now_ms(),
        },
    )

    fsm._on_trade_executed(event)

    assert manage.state == ManageState.FLAT
    assert manage.symbol is None
    assert manage.sl_order_id is None
    assert manage.tp_order_id is None

    proof = fsm.get_recent_terminal_close_proof(symbol)
    assert proof is not None
    assert proof["close_reason"] == "SL"
    assert proof["tracked_bracket_order_id"] == "1000000041481020"
    assert proof["terminal_correlation_source"] == "order_guardian_client_order_id"

    records = [
        json.loads(line)
        for line in log_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(records) == 1
    assert records[0]["record_kind"] == "execution_fill_ingress"
    assert records[0]["trigger_event"] == "TRADE_EXECUTED"
    assert records[0]["manage_state_before"] == ManageState.BRACKETS_PLACED.value
    assert records[0]["manage_state_after"] == ManageState.FLAT.value
