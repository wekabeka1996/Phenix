import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.reference.adapters.binance_adapter import BinanceAPIError
from apps.reference.adapters.binance_ws_client import BinanceWebSocketClient
from apps.reference.main import build_emit_with_monitoring
from apps.reference.domains.execution_position.contract_layer.terminal_order_contracts import (
    emit_canonical_terminal_order_event,
)
from apps.reference.domains.execution_position.flows.open.entry_manager import EntryManager
from apps.reference.domains.execution_position.fsm import ExecPosFSM
from apps.reference.domains.execution_position.flows.open.open_executor import OpenExecutor
from apps.reference.domains.execution_position.flows.open.open_executor import UncertainSubmitRecoveryError
from apps.reference.domains.execution_position.flows.open.open_submission_adapter import (
    OpenSubmissionPayload,
)
from apps.reference.telemetry.shadow_journal import (
    DEFAULT_CRITICAL_EVENTS,
    attach_shadow_journal,
)
from apps.reference.telemetry.trade_lifecycle_logger import TradeLifecycleLogger
from vfoundation.core.fsm_core import FSMCore
from vfoundation.core.protocol import Message


def _shadow_cfg(path: Path):
    return SimpleNamespace(
        observability=SimpleNamespace(
            shadow_journal=SimpleNamespace(
                enabled=True,
                path=str(path),
                schema_version="1.0.0",
                instrumentation_version="1.0.0",
                critical_events=list(DEFAULT_CRITICAL_EVENTS),
            )
        )
    )


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


class _Deadline:
    def __init__(self, *, symbol: str, order_id: str, rid: str, client_order_id: str) -> None:
        self.symbol = symbol
        self.order_id = order_id
        self.rid = rid
        self.client_order_id = client_order_id
        self.corr_id = "corr-1"
        self.timeout_type = SimpleNamespace(value="fill_timeout")


class _MakerOnlyReject(Exception):
    def __init__(self, code: int) -> None:
        super().__init__("maker only reject")
        self.code = code


class _OrderRef:
    def __init__(self, *, rid: str, idempotent_key: str, client_order_id: str) -> None:
        self.rid = rid
        self.idempotent_key = idempotent_key
        self.clientOrderId = client_order_id
        self.order_kind = "ENTRY"
        self.created_ts = 0.0


class _OrderIndex:
    def __init__(self, ref: _OrderRef) -> None:
        self._ref = ref
        self.marked_terminal = []

    def get(self, clientOrderId=None, exchangeOrderId=None):
        return self._ref

    def mark_terminal(self, ref):
        self.marked_terminal.append(ref)


@pytest.mark.asyncio
async def test_timeout_cancel_emits_canonical_order_state_changed_and_hits_shadow(tmp_path):
    journal_path = tmp_path / "shadow_timeout_cancel.jsonl"
    lifecycle_path = tmp_path / "trade_lifecycle_timeout_cancel.jsonl"
    bus = FSMCore()
    attach_shadow_journal(bus, _shadow_cfg(journal_path))

    wal_records: list[dict] = []
    fsm = SimpleNamespace(
        fsm=bus,
        adapter=AsyncMock(),
        shadow_mode=False,
        watchdog=MagicMock(
            cancel_attempt_count=0,
            cancel_success_count=0,
            on_order_cancel=MagicMock(),
        ),
        metrics_collector=MagicMock(),
        alert_manager=None,
        _is_cancel_success_response=MagicMock(return_value=True),
        _is_unknown_order_error=MagicMock(return_value=False),
    )
    fsm._cancel_order = AsyncMock(return_value={"status": "CANCELED"})

    deadline = _Deadline(
        symbol="SOLUSDT",
        order_id="1811569723",
        rid="aurora_SOLUSDT_1774142702617",
        client_order_id="ENTRY-4dc9a0dc9de7",
    )

    lifecycle = TradeLifecycleLogger(
        log_file=str(lifecycle_path), orphan_ttl_sec=3600)
    with patch("vfoundation.dr.wal.append", side_effect=wal_records.append), patch(
        "apps.reference.domains.execution_position.flows.open.entry_manager.order_logger.write"
    ), patch(
        "apps.reference.domains.execution_position.contract_layer.terminal_order_contracts._trade_lifecycle",
        lifecycle,
    ):
        lifecycle.on_intent(
            rid=deadline.rid,
            symbol="SOLUSDT",
            side="BUY",
            strategy_id="aurora",
            entry_type="LIMIT",
        )
        lifecycle.on_order_placed(
            rid=deadline.rid,
            order_id=deadline.order_id,
            price=120.5,
        )
        await EntryManager(fsm).handle_order_timeout(deadline)

    fsm.watchdog.on_order_cancel.assert_called_once_with("1811569723")

    state_changed = [r for r in wal_records if r.get(
        "verb") == "ORDER_STATE_CHANGED"]
    assert len(state_changed) == 1
    payload = state_changed[0]["pld"]
    assert payload["symbol"] == "SOLUSDT"
    assert payload["status"] == "CANCELED"
    assert payload["terminal_non_fill"] is True
    assert payload["terminal_state_kind"] == "CANCELED"
    assert payload["canonical_identity_key"] == (
        "evt:order_state_changed:symbol=SOLUSDT:order_id=1811569723:"
        "client_order_id=ENTRY-4dc9a0dc9de7:terminal_state=CANCELED"
    )

    records = _read_jsonl(journal_path)
    shadow_events = [r for r in records if r["event_name"]
                     == "EVT:ORDER_STATE_CHANGED"]
    assert len(shadow_events) == 1
    fragment = shadow_events[0]["payload_fragment"]
    assert fragment["terminal_non_fill"] is True
    assert fragment["terminal_state_kind"] == "CANCELED"
    assert fragment["canonical_identity_key"] == payload["canonical_identity_key"]

    lifecycle_rows = _read_jsonl(lifecycle_path)
    assert lifecycle_rows[-1]["status"] == "CANCELLED"
    assert lifecycle_rows[-1]["close_reason"] == "timeout_cancellation"


@pytest.mark.asyncio
async def test_live_reject_path_reaches_wal_and_local_shadow_without_emit_compat_fallback(tmp_path):
    journal_path = tmp_path / "shadow_reject.jsonl"
    lifecycle_path = tmp_path / "trade_lifecycle_reject.jsonl"
    bus = FSMCore()
    attach_shadow_journal(bus, _shadow_cfg(journal_path))

    wal_records: list[dict] = []
    adapter = SimpleNamespace(
        place_limit_entry=AsyncMock(side_effect=_MakerOnlyReject(-5022)),
    )
    fsm = SimpleNamespace(fsm=bus, adapter=adapter)
    executor = OpenExecutor(fsm)
    decision = SimpleNamespace(rid="mdamr-shadow-gap-fix")

    lifecycle = TradeLifecycleLogger(
        log_file=str(lifecycle_path), orphan_ttl_sec=3600)
    with patch("vfoundation.dr.wal.append", side_effect=wal_records.append), patch(
        "apps.reference.domains.execution_position.flows.open.open_executor.order_logger.write"
    ), patch(
        "apps.reference.domains.execution_position.contract_layer.terminal_order_contracts.emit_compat",
        new_callable=AsyncMock,
    ) as mock_emit_compat:
        lifecycle.on_intent(
            rid=decision.rid,
            symbol="XRPUSDT",
            side="BUY",
            strategy_id="aurora",
            entry_type="LIMIT",
        )
        with patch(
            "apps.reference.domains.execution_position.contract_layer.terminal_order_contracts._trade_lifecycle",
            lifecycle,
        ):
            entry_resp, returned_submission, price_adjusted = await executor._place_limit_entry(
                decision=decision,
                submission=OpenSubmissionPayload(
                    symbol="XRPUSDT",
                    side="BUY",
                    quantity="6246.7",
                    order_type="LIMIT",
                    price="1.4004",
                    time_in_force="GTX",
                    client_order_id="ENTRY-XRP-1",
                ),
                wal=MagicMock(),
            )

    assert entry_resp is None
    assert returned_submission.client_order_id == "ENTRY-XRP-1"
    assert price_adjusted is False
    mock_emit_compat.assert_not_awaited()

    rejected = [r for r in wal_records if r.get("verb") == "ORDER_REJECTED"]
    assert len(rejected) == 1
    payload = rejected[0]["pld"]
    assert payload["symbol"] == "XRPUSDT"
    assert payload["reject_reason_normalized"] == "MAKER_ONLY_REJECT"
    assert payload["terminal_non_fill"] is True
    assert payload["terminal_state_kind"] == "REJECTED"
    assert payload["canonical_identity_key"] == (
        "evt:order_rejected:symbol=XRPUSDT:rid=mdamr-shadow-gap-fix:"
        "terminal_state=REJECTED:reject_reason=MAKER_ONLY_REJECT"
    )

    records = _read_jsonl(journal_path)
    shadow_events = [r for r in records if r["event_name"]
                     == "EVT:ORDER_REJECTED"]
    assert len(shadow_events) == 1
    fragment = shadow_events[0]["payload_fragment"]
    assert fragment["terminal_state_kind"] == "REJECTED"
    assert fragment["reject_reason_normalized"] == "MAKER_ONLY_REJECT"
    assert fragment["canonical_identity_key"] == payload["canonical_identity_key"]

    lifecycle_rows = _read_jsonl(lifecycle_path)
    assert lifecycle_rows[-1]["status"] == "REJECTED"
    assert lifecycle_rows[-1]["reject_stage"] == "EXECUTION"
    assert lifecycle_rows[-1]["close_reason"] == "MAKER_ONLY_REJECT"


@pytest.mark.asyncio
async def test_monitored_emit_wrapper_preserves_message_path_for_canonical_reject_shadow(tmp_path):
    journal_path = tmp_path / "shadow_wrapper_reject.jsonl"
    lifecycle_path = tmp_path / "trade_lifecycle_wrapper_reject.jsonl"
    bus = FSMCore()
    attach_shadow_journal(bus, _shadow_cfg(journal_path))

    entropy_monitor = MagicMock()
    shadow_publisher = MagicMock()
    wrapped_emit = build_emit_with_monitoring(
        original_emit=bus.emit,
        entropy_monitor=entropy_monitor,
        shadow_event_tap_getter=lambda: shadow_publisher,
        logger=MagicMock(),
    )

    wal_records: list[dict] = []
    lifecycle = TradeLifecycleLogger(
        log_file=str(lifecycle_path), orphan_ttl_sec=3600)
    lifecycle.on_intent(
        rid="rid-wrapper-shadow-fix",
        symbol="DOGEUSDT",
        side="BUY",
        strategy_id="aurora",
        entry_type="LIMIT",
    )
    with patch("vfoundation.dr.wal.append", side_effect=wal_records.append), patch(
        "apps.reference.domains.execution_position.contract_layer.terminal_order_contracts._trade_lifecycle",
        lifecycle,
    ):
        await emit_canonical_terminal_order_event(
            fsm=SimpleNamespace(emit=wrapped_emit),
            event_name="EVT:ORDER_REJECTED",
            payload={
                "symbol": "DOGEUSDT",
                "side": "BUY",
                "reason_code": "ADAPTER_ERROR",
                "reason_text": "Order would immediately trigger.",
                "origin_class": "execution_adapter",
            },
            rid="rid-wrapper-shadow-fix",
            src="execution_position",
            dst="decision_making",
            why="adapter_execution_failed",
            write_wal=True,
            fallback_ts_ms=1775300000000,
        )

    entropy_monitor.track_event.assert_called_once()
    tracked_msg = entropy_monitor.track_event.call_args.args[0]
    assert isinstance(tracked_msg, Message)
    assert tracked_msg.verb == "ORDER_REJECTED"

    shadow_publisher.publish.assert_called_once_with(
        event_name="EVT:ORDER_REJECTED",
        payload=wal_records[0]["pld"],
        why="adapter_execution_failed",
    )

    records = _read_jsonl(journal_path)
    shadow_events = [r for r in records if r["event_name"]
                     == "EVT:ORDER_REJECTED"]
    assert len(shadow_events) == 1
    assert shadow_events[0]["payload_fragment"]["origin_class"] == "execution_adapter"

    lifecycle_rows = _read_jsonl(lifecycle_path)
    assert lifecycle_rows[-1]["status"] == "REJECTED"
    assert lifecycle_rows[-1]["close_reason"] == "ADAPTER_ERROR: ORDER WOULD IMMEDIATELY TRIGGER."


@pytest.mark.asyncio
async def test_uncertain_submit_unrecovered_emits_single_canonical_reject_from_fsm_seam(tmp_path):
    journal_path = tmp_path / "shadow_uncertain_submit_reject.jsonl"
    lifecycle_path = tmp_path / "trade_lifecycle_uncertain_submit_reject.jsonl"
    bus = FSMCore()
    attach_shadow_journal(bus, _shadow_cfg(journal_path))

    wal_records: list[dict] = []
    lifecycle = TradeLifecycleLogger(
        log_file=str(lifecycle_path), orphan_ttl_sec=3600)
    fsm = ExecPosFSM.__new__(ExecPosFSM)
    fsm.config = SimpleNamespace(get_domain_mode=lambda _domain: "testnet")
    fsm.fsm = bus
    fsm.alert_manager = None
    fsm.adapter = SimpleNamespace(base_url="https://testnet.binance.example")
    fsm._open_exec = SimpleNamespace(
        execute_open=AsyncMock(
            side_effect=UncertainSubmitRecoveryError(
                symbol="BTCUSDT",
                entry_id="ENTRY-BTC-UNCERTAIN-1",
                original_error=BinanceAPIError(
                    code=-1007,
                    msg="Timeout waiting for response from backend server. Send status unknown; execution status unknown.",
                ),
                attempts=3,
            )
        )
    )
    decision = Message(
        op="DEC",
        verb="OPEN",
        src="decision_making",
        dst="execution_position",
        rid="rid-uncertain-submit-fsm-seam",
        pld={"symbol": "BTCUSDT", "side": "BUY", "qty": "1.0"},
    )

    with patch("vfoundation.dr.wal.append", side_effect=wal_records.append), patch(
        "apps.reference.domains.execution_position.fsm.order_logger.write"
    ), patch(
        "apps.reference.domains.execution_position.fsm.emit_compat",
        new_callable=AsyncMock,
    ) as mock_emit_compat, patch(
        "apps.reference.domains.execution_position.contract_layer.terminal_order_contracts._trade_lifecycle",
        lifecycle,
    ):
        lifecycle.on_intent(
            rid=decision.rid,
            symbol="BTCUSDT",
            side="BUY",
            strategy_id="aurora",
            entry_type="LIMIT",
        )
        await fsm._execute_decision(decision)

    rejected = [r for r in wal_records if r.get("verb") == "ORDER_REJECTED"]
    assert len(rejected) == 1
    payload = rejected[0]["pld"]
    assert payload["reason_code"] == "UNCERTAIN_SUBMIT_UNRECOVERED"
    assert payload["uncertain_submit"] is True
    assert payload["client_order_id"] == "ENTRY-BTC-UNCERTAIN-1"
    assert payload["recovery_attempts"] == 3
    assert payload["binance_code"] == -1007
    assert payload["origin_class"] == "execution_adapter"
    assert payload["reject_reason_normalized"].startswith(
        "UNCERTAIN_SUBMIT_UNRECOVERED:"
    )

    records = _read_jsonl(journal_path)
    shadow_events = [r for r in records if r["event_name"]
                     == "EVT:ORDER_REJECTED"]
    assert len(shadow_events) == 1
    fragment = shadow_events[0]["payload_fragment"]
    assert fragment["canonical_identity_key"] == payload["canonical_identity_key"]
    assert fragment["reject_reason_normalized"].startswith(
        "UNCERTAIN_SUBMIT_UNRECOVERED:"
    )

    mock_emit_compat.assert_awaited_once()
    exec_failed_msg = mock_emit_compat.await_args.args[1]
    assert exec_failed_msg.verb == "EXECUTION_FAILED"

    lifecycle_rows = _read_jsonl(lifecycle_path)
    assert lifecycle_rows[-1]["status"] == "REJECTED"
    assert lifecycle_rows[-1]["close_reason"].startswith(
        "UNCERTAIN_SUBMIT_UNRECOVERED:"
    )


@pytest.mark.asyncio
async def test_close_adapter_error_outer_sink_has_stage_and_linkage_markers(tmp_path):
    journal_path = tmp_path / "shadow_close_outer_reject.jsonl"
    bus = FSMCore()
    attach_shadow_journal(bus, _shadow_cfg(journal_path))

    wal_records: list[dict] = []
    retained_rows: list[dict] = []

    fsm = ExecPosFSM.__new__(ExecPosFSM)
    fsm.config = SimpleNamespace(get_domain_mode=lambda _domain: "testnet")
    fsm.fsm = bus
    fsm.alert_manager = None
    fsm.adapter = SimpleNamespace(base_url="https://testnet.binance.example")

    async def _close_fail(_decision):
        retained_rows.append(
            {
                "rid": "rid-close-outer-propagation",
                "event_type": "ORDER_REJECTED",
                "symbol": "BTCUSDT",
                "side": "SELL",
                "quantity": 0.5,
                "client_order_id": "CLOSE-BTC-1",
                "source_fsm": "CloseExecutor",
                "metadata": {
                    "trace_kind": "CLOSE_SUBMIT_OUTCOME",
                    "outcome": "rejected",
                },
            }
        )
        raise BinanceAPIError(code=-4116, msg="Duplicate order sent.")

    fsm._close_exec = SimpleNamespace(
        execute_close=AsyncMock(side_effect=_close_fail))
    fsm._open_exec = SimpleNamespace(execute_open=AsyncMock())

    decision = Message(
        op="DEC",
        verb="CLOSE",
        src="decision_making",
        dst="execution_position",
        rid="rid-close-outer-propagation",
        pld={"symbol": "BTCUSDT"},
    )

    with patch("vfoundation.dr.wal.append", side_effect=wal_records.append), patch(
        "apps.reference.domains.execution_position.fsm.order_logger.write",
        side_effect=lambda row: retained_rows.append(dict(row)),
    ), patch(
        "apps.reference.domains.execution_position.fsm.emit_compat",
        new_callable=AsyncMock,
    ) as mock_emit_compat:
        await fsm._execute_decision(decision)

    outer_rows = [
        row
        for row in retained_rows
        if row.get("event_type") == "ORDER_REJECTED"
        and row.get("source_fsm") == "ExecPosFSM"
    ]
    assert len(outer_rows) == 1
    outer_row = outer_rows[0]
    outer_meta = outer_row["metadata"]
    assert outer_meta["reject_stage"] == "outer_propagation"
    assert outer_meta["link_to_inner_reject"] is True
    assert outer_meta["inner_reject_owner"] == "CloseExecutor"
    assert outer_meta["correlation_basis"] == "rid+symbol+reject_stage"

    inner_rows = [
        row
        for row in retained_rows
        if row.get("event_type") == "ORDER_REJECTED"
        and row.get("source_fsm") == "CloseExecutor"
    ]
    assert len(inner_rows) == 1
    assert inner_rows[0]["metadata"]["trace_kind"] == "CLOSE_SUBMIT_OUTCOME"

    rejected = [record for record in wal_records if record.get(
        "verb") == "ORDER_REJECTED"]
    assert len(rejected) == 1
    payload = rejected[0]["pld"]
    assert payload["reject_stage"] == "outer_propagation"
    assert payload["link_to_inner_reject"] is True
    assert payload["correlation_basis"] == "rid+symbol+reject_stage"
    assert payload["side"] == "UNKNOWN_CLOSE_SIDE"

    mock_emit_compat.assert_awaited_once()
    exec_failed_msg = mock_emit_compat.await_args.args[1]
    assert exec_failed_msg.verb == "EXECUTION_FAILED"
    assert exec_failed_msg.pld["reject_stage"] == "outer_propagation"


def test_ws_terminal_cancel_writes_wal_and_shadow(tmp_path):
    journal_path = tmp_path / "shadow_ws_cancel.jsonl"
    lifecycle_path = tmp_path / "trade_lifecycle_ws_cancel.jsonl"
    bus = FSMCore()
    attach_shadow_journal(bus, _shadow_cfg(journal_path))

    order_ref = _OrderRef(
        rid="aurora_SOLUSDT_phase4_cancel_fix",
        idempotent_key="idem-phase4-cancel-fix",
        client_order_id="ENTRY-SOL-PHASE4-1",
    )
    bus.order_index = _OrderIndex(order_ref)
    ws_client = BinanceWebSocketClient(
        api_key="test",
        base_url="https://test",
        use_testnet=True,
        fsm_core=bus,
        main_loop=None,
    )

    wal_records: list[dict] = []
    ws_msg = {
        "e": "ORDER_TRADE_UPDATE",
        "T": 1775300100000,
        "o": {
            "s": "SOLUSDT",
            "c": "ENTRY-SOL-PHASE4-1",
            "i": "1836000001",
            "X": "CANCELED",
            "S": "BUY",
            "o": "LIMIT",
            "z": "0",
            "q": "4",
            "p": "120.50",
            "f": "GTC",
        },
    }

    lifecycle = TradeLifecycleLogger(
        log_file=str(lifecycle_path), orphan_ttl_sec=3600)
    lifecycle.on_intent(
        rid="aurora_SOLUSDT_phase4_cancel_fix",
        symbol="SOLUSDT",
        side="BUY",
        strategy_id="aurora",
        entry_type="LIMIT",
    )
    lifecycle.on_order_placed(
        rid="aurora_SOLUSDT_phase4_cancel_fix",
        order_id="1836000001",
        price=120.5,
    )
    with patch("vfoundation.dr.wal.append", side_effect=wal_records.append), patch(
        "apps.reference.domains.execution_position.contract_layer.terminal_order_contracts._trade_lifecycle",
        lifecycle,
    ):
        ws_client._handle_order_trade_update(ws_msg)

    state_changed = [r for r in wal_records if r.get(
        "verb") == "ORDER_STATE_CHANGED"]
    assert len(state_changed) == 1
    payload = state_changed[0]["pld"]
    assert payload["rid"] == "aurora_SOLUSDT_phase4_cancel_fix"
    assert payload["orderId"] == "1836000001"
    assert payload["clientOrderId"] == "ENTRY-SOL-PHASE4-1"
    assert payload["terminal_non_fill"] is True
    assert payload["terminal_state_kind"] == "CANCELED"

    records = _read_jsonl(journal_path)
    shadow_events = [r for r in records if r["event_name"]
                     == "EVT:ORDER_STATE_CHANGED"]
    assert len(shadow_events) == 1
    fragment = shadow_events[0]["payload_fragment"]
    assert fragment["canonical_identity_key"] == payload["canonical_identity_key"]
    assert fragment["terminal_state_kind"] == "CANCELED"

    lifecycle_rows = _read_jsonl(lifecycle_path)
    assert lifecycle_rows[-1]["status"] == "CANCELLED"
    assert lifecycle_rows[-1]["close_reason"] == "CANCELED"
