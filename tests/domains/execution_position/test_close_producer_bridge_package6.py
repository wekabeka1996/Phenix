from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from apps.reference.domains.decision_making.flip_orchestration import FlipOrchestrator
from apps.reference.domains.execution_position.close_producer_bridge import (
    adapt_cmd_close_to_dec_close,
    build_close_producer_bridge_trace_ref,
)
from apps.reference.domains.execution_position.fsm_close import CloseFlowFSM
from apps.reference.domains.execution_position.intent_router import IntentRouter
from apps.reference.domains.execution_position.position_policy_mediator import (
    PositionPolicyMediator,
)
from apps.reference.domains.execution_position.position_policy_sidecar import (
    CLOSE_REQUEST_COMMAND_TOPIC,
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
        "apps.reference.domains.execution_position.fsm_close.adapt_cmd_close_to_dec_close",
        wraps=adapt_cmd_close_to_dec_close,
    ) as wrapped:
        router.on_trade_intent_proposed(intent)

    assert wrapped.call_count == 1
    assert len(fsm.captured) == 1
    decision = fsm.captured[0]
    assert decision is not None
    assert decision.pld["idempotent_key"] == "idem-intent-rt-1"
    assert decision.pld["retry_key"] == "rk-intent-rt-1"


class _ManageFlow:
    def has_active_lifecycle(self) -> bool:
        return True

    _closing_position = False


class _MediatorFSM:
    def __init__(self, out_path: Path) -> None:
        self.close_flow = CloseFlowFSM()
        self.manage_flows = {"BTCUSDT": _ManageFlow()}
        self.shadow_mode = True
        self.adapter = object()
        self.config = SimpleNamespace()
        self._captured: list[Message | None] = []
        self._out_path = out_path

    def _get_portfolio_state_for_symbol(self, _symbol: str) -> str:
        return "OPEN"

    def _get_portfolio_position_signature(self, _symbol: str) -> str:
        return "LONG:0.10"

    def handle(self, msg: Message):
        result = self.close_flow.handle(msg)
        self._captured.append(result)
        return result

    def _emit_execution_bus_event(self, *_args, **_kwargs) -> None:
        return

    def _trade_lifecycle_log_path(self) -> str:
        return str(self._out_path)


def test_position_policy_mediator_path_reaches_typed_close_bridge(tmp_path: Path) -> None:
    fsm = _MediatorFSM(tmp_path / "trade_lifecycle.jsonl")
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
        "apps.reference.domains.execution_position.position_policy_mediator.append_trade_lifecycle_record",
        lambda *args, **kwargs: None,
    ), patch(
        "apps.reference.domains.execution_position.fsm_close.adapt_cmd_close_to_dec_close",
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


class _FlipBus:
    def __init__(self) -> None:
        self.emits: list[tuple[str, dict | None, str | None]] = []

    def emit(self, event_name: str, payload: dict | None = None, why: str | None = None) -> None:
        self.emits.append((event_name, payload, why))


def test_flip_close_compatibility_payload_enters_typed_close_bridge() -> None:
    bus = _FlipBus()
    orchestrator = FlipOrchestrator(
        clock=SimpleNamespace(now_ms=lambda: 1_700_000_000_000, now_sec=lambda: 1_700_000_000),
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
    cmd_close_events = [event for event in bus.emits if event[0] == "CMD:CLOSE"]
    assert len(cmd_close_events) == 1
    payload = cmd_close_events[0][1] or {}

    flow = CloseFlowFSM()
    msg = _cmd_close_message(
        rid="bus-envelope-rid",
        why=cmd_close_events[0][2] or "flip_close",
        payload=payload,
    )
    with patch(
        "apps.reference.domains.execution_position.fsm_close.adapt_cmd_close_to_dec_close",
        wraps=adapt_cmd_close_to_dec_close,
    ) as wrapped:
        decision = flow.handle(msg)

    assert wrapped.call_count == 1
    assert decision is not None
    assert decision.pld["reason"] == "FLIP_CLOSE"
    assert decision.pld["retry_key"].startswith("flip:SOLUSDT:BUY:")
    assert decision.pld["idempotent_key"] == "flip-rid-1"
