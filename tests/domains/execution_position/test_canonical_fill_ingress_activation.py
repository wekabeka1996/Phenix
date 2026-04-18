import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from apps.reference.config_models import BracketsConfig, SLConfig, TPConfig
from vfoundation.core.protocol import Message


def _trade_executed_message() -> Message:
    return Message(
        op="EVT",
        verb="TRADE_EXECUTED",
        src="adapter",
        dst="execution_position",
        rid="rid-fill-1",
        why="test_fill",
        pld={
            "symbol": "BTCUSDT",
            "orderId": "order-1",
            "clientOrderId": "ENTRY-1",
            "client_order_id": "ENTRY-1",
            "side": "BUY",
            "qty": "0.10",
            "quantity": "0.10",
            "price": "100.5",
        },
    )


def _legacy_order_fill_message() -> Message:
    return Message(
        op="EVT",
        verb="ORDER_FILL",
        src="adapter",
        dst="execution_position",
        rid="rid-fill-legacy",
        why="test_fill",
        pld={
            "symbol": "BTCUSDT",
            "orderId": "order-legacy-1",
            "quantity": "0.10",
        },
    )


def test_trade_executed_canonical_fill_ingress_orders_activation_and_observability(
    fsm_harness,
    tmp_path: Path,
) -> None:
    fsm, _, _ = fsm_harness
    log_path = tmp_path / "trade_lifecycle.jsonl"
    call_order: list[str] = []
    sidecar_payload: dict[str, object] = {}

    manage_flow = MagicMock()
    manage_flow.state = SimpleNamespace(value="FLAT")

    def _handle(msg: Message) -> Message:
        call_order.append("manage_handle")
        manage_flow.state = SimpleNamespace(value="BRACKETS_PENDING")
        return Message(
            op="DEC",
            verb="BATCH",
            src="execution_position",
            dst="adapter",
            rid=msg.rid,
            why="test_batch",
            pld={"messages": []},
        )

    manage_flow.handle.side_effect = _handle

    def _get_or_create(symbol: str):
        call_order.append("get_or_create")
        return MagicMock(), manage_flow, MagicMock()

    def _sidecar_on_trade(msg: Message) -> None:
        call_order.append("sidecar")
        sidecar_payload.update(msg.pld)
        assert manage_flow.state.value == "BRACKETS_PENDING"

    fsm._trade_lifecycle_log_path = lambda: str(log_path)
    fsm._get_or_create_flows = _get_or_create
    fsm._evt_handlers.on_trade_executed = lambda msg: call_order.append(
        "event_trade")
    fsm._evt_handlers.on_order_fill = lambda msg: call_order.append(
        "event_fill")
    fsm._position_policy_sidecar = SimpleNamespace(
        on_trade_executed=_sidecar_on_trade,
        on_order_fill=lambda msg: call_order.append("sidecar_fill"),
    )
    fsm._process_flow_result = lambda result: call_order.append(
        "process_result")

    fsm._on_trade_executed(_trade_executed_message())

    assert call_order == [
        "get_or_create",
        "event_trade",
        "event_fill",
        "manage_handle",
        "sidecar",
        "process_result",
    ]
    assert sidecar_payload["fill_source"] == "trade_executed"
    assert sidecar_payload["manage_flow_created"] is True
    assert sidecar_payload["manage_state_before"] == "FLAT"
    assert sidecar_payload["manage_state_after"] == "BRACKETS_PENDING"
    assert sidecar_payload["canonical_fill_trace_id"].startswith(
        "exec-fill:BTCUSDT:trade_executed:")

    records = [
        json.loads(line)
        for line in log_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(records) == 1
    assert records[0]["record_kind"] == "execution_fill_ingress"
    assert records[0]["trigger_event"] == "TRADE_EXECUTED"
    assert records[0]["fill_source"] == "trade_executed"
    assert records[0]["rid"] == "rid-fill-1"
    assert records[0]["manage_flow_created"] is True
    assert records[0]["manage_state_before"] == "FLAT"
    assert records[0]["manage_state_after"] == "BRACKETS_PENDING"
    assert records[0]["result_op"] == "DEC"
    assert records[0]["result_verb"] == "BATCH"


def test_order_fill_missing_activation_fields_skips_lifecycle_activation_fail_closed(
    fsm_harness,
    tmp_path: Path,
) -> None:
    fsm, _, _ = fsm_harness
    log_path = tmp_path / "trade_lifecycle.jsonl"
    call_order: list[str] = []

    def _unexpected(*args, **kwargs):
        raise AssertionError("lifecycle activation should be skipped")

    fsm._trade_lifecycle_log_path = lambda: str(log_path)
    fsm._get_or_create_flows = _unexpected
    fsm._evt_handlers.on_trade_executed = lambda msg: call_order.append(
        "event_trade")
    fsm._evt_handlers.on_order_fill = lambda msg: call_order.append(
        "event_fill")
    fsm._position_policy_sidecar = SimpleNamespace(
        on_trade_executed=_unexpected,
        on_order_fill=_unexpected,
    )
    fsm._process_flow_result = _unexpected

    fsm._on_order_fill(_legacy_order_fill_message())

    assert call_order == ["event_fill"]

    records = [
        json.loads(line)
        for line in log_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(records) == 1
    assert records[0]["record_kind"] == "execution_fill_ingress"
    assert records[0]["trigger_event"] == "ORDER_FILL"
    assert records[0]["fill_source"] == "order_fill"
    assert records[0]["rid"] == "rid-fill-legacy"
    assert records[0]["activation_skipped_reason"] == "missing_fields:price,side"


def test_trade_executed_typed_brackets_config_still_schedules_deferred_brackets(
    fsm_harness,
) -> None:
    fsm, _, cfg = fsm_harness
    cfg.trading.execution.manage.brackets = BracketsConfig(
        sl=SLConfig(fixed_bps=40),
        tp=TPConfig(fixed_bps=80),
        oco_emulation=True,
        offset_bps=5,
    )

    scheduled: list[str] = []

    async def fake_place_deferred(entry_order_id: str, bracket_data: dict) -> None:
        return None

    def fake_submit_async(coro, _loop) -> None:
        scheduled.append(coro.cr_code.co_name)
        coro.close()

    fsm._get_async_loop = lambda: object()
    fsm._submit_async = fake_submit_async
    fsm._bracket_mgr.place_deferred_brackets = fake_place_deferred
    fsm.order_guardian.cleanup_orphans = fake_place_deferred
    fsm._pending_brackets["order-1"] = {
        "symbol": "BTCUSDT",
        "side": "BUY",
        "sl": "99.5",
        "tp": "101.0",
        "qty": "0.10",
        "rid": "rid-fill-1",
        "idem_key": "rid-fill-1",
        "tick_size": "0.01",
    }

    with patch(
        "apps.reference.domains.execution_position.pending_brackets_wal.write_pending_brackets_cleared"
    ) as pending_cleared:
        result = fsm._handle_canonical_fill_ingress(
            _trade_executed_message(),
            fill_source="trade_executed",
            process_result=False,
        )

    assert result is not None
    assert result.op == "DEC"
    assert result.verb == "BATCH"
    assert "fake_place_deferred" in scheduled
    assert "delayed_cleanup" in scheduled
    assert "order-1" not in fsm._pending_brackets
    pending_cleared.assert_called_once_with(
        entry_order_id="order-1",
        reason="filled",
        symbol="BTCUSDT",
    )
