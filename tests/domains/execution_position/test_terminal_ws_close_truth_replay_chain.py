import json
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock

from vfoundation.core.protocol import Message

from apps.reference.adapters.binance_ws_client import BinanceWebSocketClient
from apps.reference.domains.execution_position.fsm_manage import ManageState
from apps.reference.domains.execution_position.order_guardian import (
    InMemoryStore,
    OrderGuardian,
)
from apps.reference.domains.execution_position.order_index import OrderIndex
from apps.reference.domains.position_tracking.position_tracking import PositionTracking
from apps.reference.core.time import get_clock


class _TrackerFSM:
    def __init__(self, exec_pos):
        self.domains = {"execution_position": exec_pos}
        self.listen = MagicMock()
        self.emit = MagicMock()


class _BridgeCore:
    def __init__(self, exec_pos_fsm, tracker, guardian):
        self.exec_pos_fsm = exec_pos_fsm
        self.tracker = tracker
        self.order_guardian = guardian
        self.order_index = OrderIndex(ttl_sec=3600)
        self.emitted: list[tuple[str, dict, str]] = []

    def emit(self, event_name: str, payload: dict, rid: str) -> None:
        self.emitted.append((event_name, payload, rid))
        if event_name != "EVT:TRADE_EXECUTED":
            return

        msg = Message(
            op="EVT",
            verb="TRADE_EXECUTED",
            src="binance_ws_client",
            dst="execution_position",
            rid=rid,
            why="WS_ORDER_UPDATE_FILLED",
            pld=payload,
        )
        self.exec_pos_fsm._on_trade_executed(msg)
        self.tracker.on_trade_executed(msg)


def _account_update_event() -> Message:
    return Message(
        op="EVT",
        verb="ACCOUNT_UPDATE_RECEIVED",
        src="binance_ws_client",
        dst="position_tracking",
        rid="acct-update-1",
        pld={
            "totalWalletBalance": "10000",
            "totalUnrealizedProfit": "0",
            "positions": [],
        },
    )


def test_eth_terminal_ws_replay_restores_close_truth_end_to_end(
    fsm_harness,
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    fsm, _, cfg = fsm_harness
    log_path = tmp_path / "logs" / "trade_lifecycle.jsonl"
    fsm._trade_lifecycle_log_path = lambda: str(log_path)

    eth_spec = MagicMock()
    eth_spec.execution.target_leverage = 20
    cfg.instruments["ETHUSDT"] = eth_spec
    cfg.domains.position_tracking.enable_market_tick_subscription = False
    cfg.domains.position_tracking.precision.quantity_min_threshold = 0.0001
    cfg.domains.position_tracking.precision.flat_position_threshold = 0.0001
    cfg.domains.position_tracking.precision.decimal_places = 4

    manage = fsm.manage_flow("ETHUSDT")
    manage.symbol = "ETHUSDT"
    manage.state = ManageState.BRACKETS_PLACED
    manage.position_qty = Decimal("0.10")
    manage.position_entry_price = Decimal("2000")
    manage.position_side = "BUY"
    manage.position_open_ts = get_clock().now_sec() - 5
    manage.entry_order_id = "entry-eth-1"
    manage.entry_client_order_id = "ENTRY-ETHUSDT-1"
    manage.sl_order_id = "1000000041481020"
    manage.tp_order_id = "1000000041481025"
    manage.sl_algo_client_id = "SJGknqkssjcrviz2pCUMMi"

    tracker = PositionTracking(_TrackerFSM(fsm), cfg)
    tracker.alert_manager = MagicMock()
    tracker._positions["ETHUSDT"] = {
        "quantity": Decimal("0.10"),
        "avg_price": Decimal("2000"),
        "venues": ["binance"],
    }

    guardian = OrderGuardian(
        adapter=None,
        store=InMemoryStore(),
        bus=None,
        config=None,
    )
    guardian.register_entry(
        symbol="ETHUSDT",
        order_id="entry-eth-1",
        client_order_id="ENTRY-ETHUSDT-1",
        side="BUY",
        qty=0.10,
        corr_id="corr-eth-1",
        rid="aurora_ETHUSDT_1775247901546",
    )
    guardian.register_bracket(
        symbol="ETHUSDT",
        parent_order_id="entry-eth-1",
        order_id="1000000041481020",
        client_order_id="SJGknqkssjcrviz2pCUMMi",
        kind="SL",
        corr_id="corr-eth-1",
        rid="aurora_ETHUSDT_1775247901546",
    )
    fsm.order_guardian = guardian

    # Register bracket child in OrderIndex with clientAlgoId as clientOrderId
    # (this is what the WS fill will send as clientOrderId)
    bridge_core = _BridgeCore(fsm, tracker, guardian)
    bridge_core.order_index.register_bracket_child(
        rid="aurora_ETHUSDT_1775247901546",
        idempotent_key="idem-eth-1",
        clientOrderId="SJGknqkssjcrviz2pCUMMi",  # clientAlgoId -> WS fill c field
        exchangeOrderId="1000000041481020",        # algoId
        symbol="ETHUSDT",
        side="SELL",
        order_type="STOP_MARKET",
        order_kind="SL",
    )

    client = BinanceWebSocketClient(
        api_key="k",
        base_url="http://example.invalid",
        use_testnet=True,
        fsm_core=bridge_core,
    )

    client._handle_ws_message(
        {
            "e": "ORDER_TRADE_UPDATE",
            "T": get_clock().now_ms(),
            "o": {
                "c": "SJGknqkssjcrviz2pCUMMi",
                "i": "8631145709",
                "X": "FILLED",
                "s": "ETHUSDT",
                "z": "0.10",
                "l": "0.10",
                "S": "SELL",
                "o": "STOP_MARKET",
                "q": "0.10",
                "ap": "1990.0",
                "p": "1990.0",
            },
        }
    )

    proof = fsm.get_recent_terminal_close_proof("ETHUSDT")
    assert proof is not None
    assert proof["close_reason"] == "SL"
    assert proof["tracked_bracket_order_id"] == "1000000041481020"
    assert manage.state == ManageState.FLAT
    assert tracker._positions["ETHUSDT"]["quantity"] == Decimal("0.00")

    tracker._positions["ETHUSDT"] = {
        "quantity": Decimal("0.10"),
        "avg_price": Decimal("2000"),
        "venues": ["binance"],
    }
    tracker.on_account_update(_account_update_event())

    tracker.alert_manager.check_position_disappearance.assert_not_called()
    tracker.alert_manager.check_manual_intervention.assert_not_called()

    rows = [
        json.loads(line)
        for line in log_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    event_types = [row.get("event_type") for row in rows]
    assert "EXECUTION_WS_TERMINAL_CORRELATED" in event_types
    assert "POSITION_DISAPPEARANCE_ATTRIBUTED" in event_types

    ingress_row = next(
        row for row in rows if row.get("record_kind") == "execution_fill_ingress"
    )
    assert ingress_row["manage_state_before"] == ManageState.BRACKETS_PLACED.value
    assert ingress_row["manage_state_after"] == ManageState.FLAT.value

    disappearance_row = next(
        row for row in rows if row.get("record_kind") == "position_disappearance"
    )
    assert disappearance_row["attribution"] == "proven_exchange_bracket_close"
    assert disappearance_row["close_reason"] == "SL"
