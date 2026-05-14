from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from apps.reference.domains.decision_making.intent.flip import FlipOrchestrator
from apps.reference.domains.execution_position.flows.close.close_producer_bridge import (
    adapt_cmd_close_to_dec_close,
    build_close_producer_bridge_trace_ref,
)
from apps.reference.domains.execution_position.flows.close.fsm_close import CloseFlowFSM
from apps.reference.domains.execution_position.flows.open.intent_router import IntentRouter
from apps.reference.domains.execution_position.sidecar.position_policy_mediator import (
    PositionPolicyMediator,
)
from apps.reference.domains.execution_position.sidecar.position_policy_sidecar import (
    CLOSE_REQUEST_COMMAND_TOPIC,
)
from apps.reference.domains.execution_position.state.order_index import OrderIndex
from apps.reference.domains.execution_position.telemetry.lifecycle_stats_ledger import (
    ExecutionLifecycleStatsLedger,
)
from apps.reference.domains.execution_position.state.truth_hardening import (
    CloseGuardDecision,
)
from vfoundation.core.protocol import Message


def _cmd_close_message(
    *,
    rid: str = "rid-close-1",
    why: str = "manual_close",
    payload: dict | None = None,
) -> Message:
    return Message(
        op="CMD",
        verb="CLOSE",
        src="decision_making",
        dst="execution_position",
        rid=rid,
        pld=dict(payload or {}),
        why=why,
    )


def test_malformed_cmd_close_rejects_before_dec_close_and_attaches_reject_trace() -> None:
    flow = CloseFlowFSM()
    msg = _cmd_close_message(
        payload={"symbol": "BTCUSDT", "reason": "bad_qty", "qty": "abc"}
    )

    result = flow.handle(msg)

    assert result is None
    metrics = flow.get_metrics()
    assert metrics["fsm_close_bridge_rejects_total"] == 1
    assert metrics["fsm_errors_total"] == 1
    reject_ref = build_close_producer_bridge_trace_ref(
        status="reject",
        qty_present=False,
        preserved_idempotent_key=False,
        preserved_command_trigger=False,
        reason="intake_validation",
    )
    assert reject_ref in list(msg.data_ref or [])


def test_intent_router_style_cmd_close_normalizes_and_preserves_fields() -> None:
    flow = CloseFlowFSM()
    msg = _cmd_close_message(
        rid="rid-intent-close",
        why="intent_reduce_only:rid-intent-close",
        payload={
            "symbol": "BTCUSDT",
            "reason": "intent_reduce_only",
            "idempotent_key": "idem-intent-1",
            "retry_key": "rk-intent-1",
            "qty": "0.010",
            "trace": {"source": "intent_router", "kind": "reduce_only"},
        },
    )

    result = flow.handle(msg)

    assert result is not None
    assert result.op == "DEC"
    assert result.verb == "CLOSE"
    assert result.idempotent_key == "idem-intent-1"
    assert result.pld["idempotent_key"] == "idem-intent-1"
    assert result.pld["symbol"] == "BTCUSDT"
    assert result.pld["reason"] == "intent_reduce_only"
    assert result.pld["qty"] == "0.010"
    assert result.pld["retry_key"] == "rk-intent-1"
    assert result.pld["trace"] == {
        "source": "intent_router",
        "kind": "reduce_only",
    }
    assert result.pld["trigger"] == "CMD:CLOSE"
    assert result.pld["close_guard_prevalidated"] is False
    assert "command_trigger" not in result.pld
    success_ref = build_close_producer_bridge_trace_ref(
        status="success",
        qty_present=True,
        preserved_idempotent_key=True,
        preserved_command_trigger=False,
    )
    assert success_ref in list(result.data_ref or [])


def test_sidecar_style_cmd_close_preserves_command_trigger_and_policy_context() -> None:
    flow = CloseFlowFSM()
    msg = _cmd_close_message(
        rid="ppsreq:BTCUSDT:1",
        why="position_policy_sidecar_soft_close",
        payload={
            "symbol": "BTCUSDT",
            "reason": "position_policy_sidecar_soft_close",
            "trigger": CLOSE_REQUEST_COMMAND_TOPIC,
            "trace": "pps:BTCUSDT:1:1",
            "idempotent_key": "ppsreq:BTCUSDT:1",
            "close_guard_prevalidated": True,
            "policy_context": {
                "symbol": "BTCUSDT",
                "policy_source": "position_policy_sidecar",
            },
        },
    )

    result = flow.handle(msg)

    assert result is not None
    assert result.idempotent_key == "ppsreq:BTCUSDT:1"
    assert result.pld["idempotent_key"] == "ppsreq:BTCUSDT:1"
    assert result.pld["trigger"] == "CMD:CLOSE"
    assert result.pld["command_trigger"] == CLOSE_REQUEST_COMMAND_TOPIC
    assert result.pld["close_guard_prevalidated"] is True
    assert result.pld["trace"] == "pps:BTCUSDT:1:1"
    assert result.pld["policy_context"]["policy_source"] == "position_policy_sidecar"
    success_ref = build_close_producer_bridge_trace_ref(
        status="success",
        qty_present=False,
        preserved_idempotent_key=True,
        preserved_command_trigger=True,
    )
    assert success_ref in list(result.data_ref or [])


def test_flip_compatibility_payload_rid_becomes_stable_dec_idempotent_key() -> None:
    flow = CloseFlowFSM()
    msg = _cmd_close_message(
        rid="bus-envelope-rid",
        why="flip_close",
        payload={
            "symbol": "ETHUSDT",
            "reason": "FLIP_CLOSE",
            "retry_key": "flip:ETHUSDT:BUY:test-rid",
            "rid": "test-rid",
        },
    )

    result = flow.handle(msg)

    assert result is not None
    assert result.idempotent_key == "test-rid"
    assert result.pld["idempotent_key"] == "test-rid"
    assert result.pld["retry_key"] == "flip:ETHUSDT:BUY:test-rid"
    assert "rid" not in result.pld


class _RouterFSM:
    def __init__(self) -> None:
        self.close_flow = CloseFlowFSM()
        self.log_adapter = SimpleNamespace(log_trade_intent=lambda **_: None)
        self.captured: list[Message | None] = []
        self._intent_boundary_audit = None

    def handle(self, msg: Message):
        result = self.close_flow.handle(msg)
        self.captured.append(result)
        return result


def test_intent_router_reduce_only_path_reaches_typed_close_bridge() -> None:
    fsm = _RouterFSM()
    router = IntentRouter(fsm)
    intent = Message(
        op="EVT",
        verb="TRADE_INTENT_PROPOSED",
        src="decision_making",
        dst="execution_position",
        rid="intent-rid-1",
        pld={
            "rid": "intent-rid-1",
            "instrument": "BTCUSDT",
            "strategy": "aurora",
            "side": "SELL",
            "reason": "intent_reduce_only",
            "idempotent_key": "idem-intent-rt-1",
            "retry_key": "rk-intent-rt-1",
            "trace": {"path": "intent_router"},
            "order": {"qty": "0.01", "reduce_only": True},
        },
        why="trade_intent",
    )

    with patch(
        "apps.reference.domains.execution_position.flows.close.fsm_close.adapt_cmd_close_to_dec_close",
        wraps=adapt_cmd_close_to_dec_close,
    ) as wrapped:
        router.on_trade_intent_proposed(intent)

    assert wrapped.call_count == 1
    assert len(fsm.captured) == 1
    decision = fsm.captured[0]
    assert decision is not None
    assert decision.pld["idempotent_key"] == "idem-intent-rt-1"
    assert decision.pld["retry_key"] == "rk-intent-rt-1"


def test_execpos_cmd_close_ingress_consults_hardening_and_sets_closing_flag_before_delegation(
    fsm_harness,
) -> None:
    fsm, _bus, _cfg = fsm_harness
    fsm._latest_portfolio_state = {
        "positions": [{"symbol": "BTCUSDT", "positionAmt": "0.010"}]
    }
    fsm._get_or_create_flows("BTCUSDT")
    close_flow = fsm.close_flows["BTCUSDT"]
    manage = fsm.manage_flows["BTCUSDT"]
    hardening = fsm._execution_truth_hardening
    msg = _cmd_close_message(
        rid="rid-explicit-close-1",
        payload={
            "symbol": "BTCUSDT",
            "reason": "MANUAL_CLOSE",
            "idempotent_key": "explicit-close-1",
            "qty": "0.010",
        },
    )

    original_handle = close_flow.handle

    def _delegating_handle(incoming: Message):
        assert manage._closing_position is True
        return original_handle(incoming)

    with patch.object(
        hardening,
        "evaluate_close_command",
        return_value=CloseGuardDecision(
            suppress=False,
            key="close:BTCUSDT",
            reason="allow_cmd_close",
        ),
    ) as evaluate_mock, patch.object(
        close_flow,
        "handle",
        side_effect=_delegating_handle,
    ) as handle_mock:
        result = fsm.handle(msg)

    assert result is not None
    assert result.op == "DEC"
    assert result.verb == "CLOSE"
    assert result.pld["idempotent_key"] == "explicit-close-1"
    assert manage._closing_position is True
    expected_signature = fsm._get_portfolio_position_signature("BTCUSDT")
    evaluate_mock.assert_called_once_with(
        symbol="BTCUSDT",
        requested_qty="0.010",
        position_signature=expected_signature,
        rid="rid-explicit-close-1",
    )
    handle_mock.assert_called_once()


def test_execpos_cmd_close_ingress_suppression_returns_none_without_close_flow_delegation(
    fsm_harness,
) -> None:
    fsm, _bus, _cfg = fsm_harness
    fsm._latest_portfolio_state = {
        "positions": [{"symbol": "BTCUSDT", "positionAmt": "0.010"}]
    }
    fsm._get_or_create_flows("BTCUSDT")
    close_flow = fsm.close_flows["BTCUSDT"]
    hardening = fsm._execution_truth_hardening
    msg = _cmd_close_message(
        rid="rid-explicit-close-2",
        payload={"symbol": "BTCUSDT", "reason": "MANUAL_CLOSE"},
    )

    with patch.object(
        hardening,
        "evaluate_close_command",
        return_value=CloseGuardDecision(
            suppress=True,
            key="close:BTCUSDT",
            reason="duplicate_cmd_close_same_effective_state",
        ),
    ) as evaluate_mock, patch.object(close_flow, "handle") as handle_mock:
        result = fsm.handle(msg)

    assert result is None
    evaluate_mock.assert_called_once()
    handle_mock.assert_not_called()
    assert fsm.manage_flows["BTCUSDT"]._closing_position is False


def test_execpos_cmd_close_prevalidated_skips_hardening_and_still_delegates(
    fsm_harness,
) -> None:
    fsm, _bus, _cfg = fsm_harness
    fsm._latest_portfolio_state = {
        "positions": [{"symbol": "BTCUSDT", "positionAmt": "0.010"}]
    }
    fsm._get_or_create_flows("BTCUSDT")
    close_flow = fsm.close_flows["BTCUSDT"]
    hardening = fsm._execution_truth_hardening
    msg = _cmd_close_message(
        rid="ppsreq:BTCUSDT:1",
        payload={
            "symbol": "BTCUSDT",
            "reason": "position_policy_sidecar_soft_close",
            "idempotent_key": "ppsreq:BTCUSDT:1",
            "close_guard_prevalidated": True,
            "trigger": CLOSE_REQUEST_COMMAND_TOPIC,
        },
    )

    with patch.object(
        hardening,
        "evaluate_close_command",
    ) as evaluate_mock, patch.object(
        close_flow,
        "handle",
        wraps=close_flow.handle,
    ) as handle_mock:
        result = fsm.handle(msg)

    assert result is not None
    assert result.pld["close_guard_prevalidated"] is True
    assert result.pld["command_trigger"] == CLOSE_REQUEST_COMMAND_TOPIC
    evaluate_mock.assert_not_called()
    handle_mock.assert_called_once()
    assert fsm.manage_flows["BTCUSDT"]._closing_position is True


class _ManageFlow:
    def has_active_lifecycle(self) -> bool:
        return True

    _closing_position = False


class _MediatorFSM:
    def __init__(self, out_path: Path, *, ledger: ExecutionLifecycleStatsLedger | None = None) -> None:
        self.close_flow = CloseFlowFSM()
        self.manage_flows = {"BTCUSDT": _ManageFlow()}
        self.shadow_mode = True
        self.adapter = object()
        self.config = SimpleNamespace()
        self._captured: list[Message | None] = []
        self._emitted: list[tuple[str, dict | None]] = []
        self._out_path = out_path
        self._order_index = OrderIndex()
        self._lifecycle_stats_ledger = ledger
        self._last_lifecycle_ikey_by_symbol = {}

    def _get_portfolio_state_for_symbol(self, _symbol: str) -> str:
        return "OPEN"

    def _get_portfolio_position_signature(self, _symbol: str) -> str:
        return "LONG:0.10"

    def handle(self, msg: Message):
        result = self.close_flow.handle(msg)
        self._captured.append(result)
        return result

    def _emit_execution_bus_event(self, topic: str, payload: dict | None = None, *_args, **_kwargs) -> None:
        self._emitted.append((topic, payload))

    def _trade_lifecycle_log_path(self) -> str:
        return str(self._out_path)


def test_position_policy_mediator_path_reaches_typed_close_bridge(tmp_path: Path) -> None:
    ledger = ExecutionLifecycleStatsLedger(
        log_file=str(tmp_path / "execution_lifecycle_stats_v1.jsonl"),
        clock_ms_fn=lambda: 1_700_000_000_000,
    )
    ledger.seed_entry(
        lifecycle_id="lifecycle-1",
        entry_rid="entry-rid-1",
        symbol="BTCUSDT",
        side="BUY",
        entry_ts_ms=1_700_000_000_000,
        entry_price=100.0,
        qty=0.10,
        source="test_seed",
    )
    fsm = _MediatorFSM(tmp_path / "trade_lifecycle.jsonl", ledger=ledger)
    fsm._order_index.upsert_from_open(
        rid="entry-rid-1",
        idempotent_key="lifecycle-1",
        clientOrderId="ENTRY-recovered-1",
        symbol="BTCUSDT",
        side="BUY",
        order_type="LIMIT",
        order_kind="ENTRY",
    )
    mediator = PositionPolicyMediator(fsm)
    event = Message(
        op="EVT",
        verb="POSITION_POLICY_SIDECAR_CLOSE_REQUESTED",
        src="execution_position.position_policy_sidecar",
        dst="execution_position",
        rid="ppsreq:BTCUSDT:1",
        pld={
            "request_id": "ppsreq:BTCUSDT:1",
            "trace_id": "pps:BTCUSDT:1:1",
            "symbol": "BTCUSDT",
            "fill_correlation": {
                "rid": "entry-rid-1",
                "client_order_id": "ENTRY-recovered-1",
            },
            "position_snapshot": {"symbol": "BTCUSDT", "unrealized_pnl_usdt": "12.5"},
        },
        why="position_policy_sidecar_request",
    )

    with patch.object(
        mediator,
        "_position_policy_allowed_scope",
        return_value={
            "soft_close_symbol_current_net_only": True,
            "partial_reduce": False,
            "bracket_mutation": False,
            "exact_targeting": False,
        },
    ), patch(
        "apps.reference.domains.execution_position.sidecar.position_policy_mediator.append_trade_lifecycle_record",
        lambda *args, **kwargs: None,
    ), patch(
        "apps.reference.domains.execution_position.flows.close.fsm_close.adapt_cmd_close_to_dec_close",
        wraps=adapt_cmd_close_to_dec_close,
    ) as wrapped:
        mediator.on_position_policy_close_request(event)

    assert wrapped.call_count == 1
    assert len(fsm._captured) == 1
    decision = fsm._captured[0]
    assert decision is not None
    assert decision.pld["command_trigger"] == CLOSE_REQUEST_COMMAND_TOPIC
    assert decision.pld["close_guard_prevalidated"] is True
    assert decision.pld["policy_context"]["policy_source"] == "position_policy_sidecar"
    assert decision.pld["policy_context"]["lifecycle_id"] == "lifecycle-1"
    assert decision.pld["policy_context"]["fill_correlation"]["lifecycle_id"] == "lifecycle-1"
    assert fsm._last_lifecycle_ikey_by_symbol["BTCUSDT"] == "lifecycle-1"
    latest_row = ledger.get_latest(lifecycle_id="lifecycle-1")
    assert latest_row is not None
    assert latest_row.provisional_status == "close_requested"
    assert latest_row.current_unrealized_at_close_request == 12.5
    assert latest_row.close_actor == "POSITION_POLICY_SIDECAR"


def test_position_policy_mediator_recovers_canonical_fill_rid_without_order_index_entry(tmp_path: Path) -> None:
    canonical_lifecycle_id = "aurora_BTCUSDT_1778613004676"
    ledger = ExecutionLifecycleStatsLedger(
        log_file=str(tmp_path / "execution_lifecycle_stats_v1.jsonl"),
        clock_ms_fn=lambda: 1_700_000_000_000,
    )
    ledger.seed_entry(
        lifecycle_id=canonical_lifecycle_id,
        entry_rid=canonical_lifecycle_id,
        symbol="BTCUSDT",
        side="BUY",
        entry_ts_ms=1_700_000_000_000,
        entry_price=100.0,
        qty=0.10,
        source="test_seed",
    )
    fsm = _MediatorFSM(tmp_path / "trade_lifecycle.jsonl", ledger=ledger)
    mediator = PositionPolicyMediator(fsm)
    event = Message(
        op="EVT",
        verb="POSITION_POLICY_SIDECAR_CLOSE_REQUESTED",
        src="execution_position.position_policy_sidecar",
        dst="execution_position",
        rid="ppsreq:BTCUSDT:residual-1",
        pld={
            "request_id": "ppsreq:BTCUSDT:residual-1",
            "trace_id": "pps:BTCUSDT:residual-1",
            "symbol": "BTCUSDT",
            "fill_correlation": {
                "rid": canonical_lifecycle_id,
                "client_order_id": "ENTRY-expired-or-missing",
            },
            "position_snapshot": {"symbol": "BTCUSDT", "unrealized_pnl_usdt": "7.5"},
        },
        why="position_policy_sidecar_request",
    )

    with patch.object(
        mediator,
        "_position_policy_allowed_scope",
        return_value={
            "soft_close_symbol_current_net_only": True,
            "partial_reduce": False,
            "bracket_mutation": False,
            "exact_targeting": False,
        },
    ), patch(
        "apps.reference.domains.execution_position.sidecar.position_policy_mediator.append_trade_lifecycle_record",
        lambda *args, **kwargs: None,
    ), patch(
        "apps.reference.domains.execution_position.flows.close.fsm_close.adapt_cmd_close_to_dec_close",
        wraps=adapt_cmd_close_to_dec_close,
    ):
        mediator.on_position_policy_close_request(event)

    assert len(fsm._captured) == 1
    decision = fsm._captured[0]
    assert decision is not None
    assert decision.pld["policy_context"]["lifecycle_id"] == canonical_lifecycle_id
    assert (
        decision.pld["policy_context"]["fill_correlation"]["lifecycle_id"]
        == canonical_lifecycle_id
    )
    assert fsm._last_lifecycle_ikey_by_symbol["BTCUSDT"] == canonical_lifecycle_id
    latest_row = ledger.get_latest(lifecycle_id=canonical_lifecycle_id)
    assert latest_row is not None
    assert latest_row.provisional_status == "close_requested"
    assert latest_row.current_unrealized_at_close_request == 7.5
    emitted_states = [
        payload
        for topic, payload in fsm._emitted
        if topic == "EVT:POSITION_POLICY_SIDECAR_CLOSE_REQUEST_STATE"
    ]
    assert all(payload["request_state"] !=
               "identity_recovery_failed" for payload in emitted_states)


def test_position_policy_mediator_prefers_explicit_lifecycle_id_over_fill_rid(tmp_path: Path) -> None:
    ledger = ExecutionLifecycleStatsLedger(
        log_file=str(tmp_path / "execution_lifecycle_stats_v1.jsonl"),
        clock_ms_fn=lambda: 1_700_000_000_000,
    )
    ledger.seed_entry(
        lifecycle_id="explicit-life-1",
        entry_rid="ENTRY-BTCUSDT-explicit-1",
        symbol="BTCUSDT",
        side="BUY",
        entry_ts_ms=1_700_000_000_000,
        entry_price=100.0,
        qty=0.10,
        source="test_seed",
    )
    fsm = _MediatorFSM(tmp_path / "trade_lifecycle.jsonl", ledger=ledger)
    mediator = PositionPolicyMediator(fsm)
    event = Message(
        op="EVT",
        verb="POSITION_POLICY_SIDECAR_CLOSE_REQUESTED",
        src="execution_position.position_policy_sidecar",
        dst="execution_position",
        rid="ppsreq:BTCUSDT:explicit-1",
        pld={
            "request_id": "ppsreq:BTCUSDT:explicit-1",
            "trace_id": "pps:BTCUSDT:explicit-1",
            "symbol": "BTCUSDT",
            "lifecycle_id": "explicit-life-1",
            "fill_correlation": {
                "rid": "aurora_BTCUSDT_1778613004676",
            },
            "position_snapshot": {"symbol": "BTCUSDT", "unrealized_pnl_usdt": "4.0"},
        },
        why="position_policy_sidecar_request",
    )

    with patch.object(
        mediator,
        "_position_policy_allowed_scope",
        return_value={
            "soft_close_symbol_current_net_only": True,
            "partial_reduce": False,
            "bracket_mutation": False,
            "exact_targeting": False,
        },
    ), patch(
        "apps.reference.domains.execution_position.sidecar.position_policy_mediator.append_trade_lifecycle_record",
        lambda *args, **kwargs: None,
    ):
        mediator.on_position_policy_close_request(event)

    decision = fsm._captured[0]
    assert decision is not None
    assert decision.pld["policy_context"]["lifecycle_id"] == "explicit-life-1"
    assert decision.pld["policy_context"]["fill_correlation"]["lifecycle_id"] == "explicit-life-1"
    assert fsm._last_lifecycle_ikey_by_symbol["BTCUSDT"] == "explicit-life-1"
    latest_row = ledger.get_latest(lifecycle_id="explicit-life-1")
    assert latest_row is not None
    assert latest_row.provisional_status == "close_requested"


def test_position_policy_mediator_falls_back_to_cached_lifecycle_id_when_fill_rid_is_not_canonical(tmp_path: Path) -> None:
    ledger = ExecutionLifecycleStatsLedger(
        log_file=str(tmp_path / "execution_lifecycle_stats_v1.jsonl"),
        clock_ms_fn=lambda: 1_700_000_000_000,
    )
    ledger.seed_entry(
        lifecycle_id="cached-life-1",
        entry_rid="ENTRY-BTCUSDT-cached-1",
        symbol="BTCUSDT",
        side="BUY",
        entry_ts_ms=1_700_000_000_000,
        entry_price=100.0,
        qty=0.10,
        source="test_seed",
    )
    fsm = _MediatorFSM(tmp_path / "trade_lifecycle.jsonl", ledger=ledger)
    fsm._last_lifecycle_ikey_by_symbol["BTCUSDT"] = "cached-life-1"
    mediator = PositionPolicyMediator(fsm)
    event = Message(
        op="EVT",
        verb="POSITION_POLICY_SIDECAR_CLOSE_REQUESTED",
        src="execution_position.position_policy_sidecar",
        dst="execution_position",
        rid="ppsreq:BTCUSDT:cached-1",
        pld={
            "request_id": "ppsreq:BTCUSDT:cached-1",
            "trace_id": "pps:BTCUSDT:cached-1",
            "symbol": "BTCUSDT",
            "fill_correlation": {
                "rid": "ppsreq:btc:noncanonical",
            },
            "position_snapshot": {"symbol": "BTCUSDT", "unrealized_pnl_usdt": "3.5"},
        },
        why="position_policy_sidecar_request",
    )

    with patch.object(
        mediator,
        "_position_policy_allowed_scope",
        return_value={
            "soft_close_symbol_current_net_only": True,
            "partial_reduce": False,
            "bracket_mutation": False,
            "exact_targeting": False,
        },
    ), patch(
        "apps.reference.domains.execution_position.sidecar.position_policy_mediator.append_trade_lifecycle_record",
        lambda *args, **kwargs: None,
    ):
        mediator.on_position_policy_close_request(event)

    decision = fsm._captured[0]
    assert decision is not None
    assert decision.pld["policy_context"]["lifecycle_id"] == "cached-life-1"
    assert decision.pld["policy_context"]["fill_correlation"]["lifecycle_id"] == "cached-life-1"
    latest_row = ledger.get_latest(lifecycle_id="cached-life-1")
    assert latest_row is not None
    assert latest_row.provisional_status == "close_requested"


def test_position_policy_mediator_emits_identity_recovery_failed_when_no_canonical_candidate_exists(tmp_path: Path) -> None:
    ledger = ExecutionLifecycleStatsLedger(
        log_file=str(tmp_path / "execution_lifecycle_stats_v1.jsonl"),
        clock_ms_fn=lambda: 1_700_000_000_000,
    )
    fsm = _MediatorFSM(tmp_path / "trade_lifecycle.jsonl", ledger=ledger)
    mediator = PositionPolicyMediator(fsm)
    event = Message(
        op="EVT",
        verb="POSITION_POLICY_SIDECAR_CLOSE_REQUESTED",
        src="execution_position.position_policy_sidecar",
        dst="execution_position",
        rid="ppsreq:BTCUSDT:no-life-1",
        pld={
            "request_id": "ppsreq:BTCUSDT:no-life-1",
            "trace_id": "pps:BTCUSDT:no-life-1",
            "symbol": "BTCUSDT",
            "fill_correlation": {
                "rid": "ppsreq:btc:noncanonical",
                "client_order_id": "CLOSE-BTCUSDT-1",
            },
            "position_snapshot": {"symbol": "BTCUSDT", "unrealized_pnl_usdt": "1.5"},
        },
        why="position_policy_sidecar_request",
    )

    with patch.object(
        mediator,
        "_position_policy_allowed_scope",
        return_value={
            "soft_close_symbol_current_net_only": True,
            "partial_reduce": False,
            "bracket_mutation": False,
            "exact_targeting": False,
        },
    ), patch(
        "apps.reference.domains.execution_position.sidecar.position_policy_mediator.append_trade_lifecycle_record",
        lambda *args, **kwargs: None,
    ):
        mediator.on_position_policy_close_request(event)

    decision = fsm._captured[0]
    assert decision is not None
    assert decision.pld["policy_context"]["lifecycle_id"] is None
    emitted_states = [
        payload
        for topic, payload in fsm._emitted
        if topic == "EVT:POSITION_POLICY_SIDECAR_CLOSE_REQUEST_STATE"
    ]
    failure_state = next(
        payload for payload in emitted_states if payload["request_state"] == "identity_recovery_failed"
    )
    assert failure_state["recovery_reason"] == "no_canonical_lifecycle_candidate"
    assert failure_state["lifecycle_recovery_candidates"]["fill_correlation_rid"] == "ppsreq:btc:noncanonical"
    assert ledger.get_latest(lifecycle_id="ppsreq:BTCUSDT:no-life-1") is None


class _FlipBus:
    def __init__(self) -> None:
        self.emits: list[tuple[str, dict | None, str | None]] = []

    def emit(self, event_name: str, payload: dict | None = None, why: str | None = None) -> None:
        self.emits.append((event_name, payload, why))


def test_flip_close_compatibility_payload_enters_typed_close_bridge() -> None:
    bus = _FlipBus()
    orchestrator = FlipOrchestrator(
        clock=SimpleNamespace(now_ms=lambda: 1_700_000_000_000,
                              now_sec=lambda: 1_700_000_000),
        config=SimpleNamespace(
            domains=SimpleNamespace(
                position_tracking=SimpleNamespace(positions_stale_ttl_sec=15)
            )
        ),
        fsm=bus,
        get_position_state=lambda _symbol: "SHORT",
        get_portfolio_position_qty_signed=lambda _symbol: (None, None),
        get_flip_config=lambda _symbol: (True, 1.0),
        propose_trade_intent=lambda **_: None,
        emit_intent_deferred_v1=lambda **_: None,
        logger=SimpleNamespace(info=lambda *args, **kwargs: None),
    )

    result = orchestrator.initiate_flip_close(
        symbol="SOLUSDT",
        intent_side="BUY",
        original_pld={"rid": "flip-rid-1"},
        source="aurora",
    )

    assert result == "FLIP_CLOSE_PENDING"
    cmd_close_events = [
        event for event in bus.emits if event[0] == "CMD:CLOSE"]
    assert len(cmd_close_events) == 1
    payload = cmd_close_events[0][1] or {}

    flow = CloseFlowFSM()
    msg = _cmd_close_message(
        rid="bus-envelope-rid",
        why=cmd_close_events[0][2] or "flip_close",
        payload=payload,
    )
    with patch(
        "apps.reference.domains.execution_position.flows.close.fsm_close.adapt_cmd_close_to_dec_close",
        wraps=adapt_cmd_close_to_dec_close,
    ) as wrapped:
        decision = flow.handle(msg)

    assert wrapped.call_count == 1
    assert decision is not None
    assert decision.pld["reason"] == "FLIP_CLOSE"
    assert decision.pld["retry_key"].startswith("flip:SOLUSDT:BUY:")
    assert decision.pld["idempotent_key"] == "flip-rid-1"
