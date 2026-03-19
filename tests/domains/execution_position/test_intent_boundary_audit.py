from __future__ import annotations

from vfoundation.core.protocol import Message

from apps.reference.domains.execution_position.intent_boundary_audit import (
    IntentBoundaryAudit,
)

pytest_plugins = ("tests.domains.execution_position.conftest",)


class _DispatchingBus:
    def __init__(self) -> None:
        self.listeners: dict[str, list] = {}
        self.events: list[tuple[str, dict, str | None, object]] = []

    def listen(self, topic: str, handler) -> None:
        self.listeners.setdefault(topic, []).append(handler)

    def emit(self, topic: str, payload=None, why=None, data_ref=None) -> None:
        payload_dict = payload or {}
        self.events.append((topic, payload_dict, why, data_ref))
        for handler in self.listeners.get(topic, []):
            handler(payload_dict)


def _proposal_payload(rid: str = "RID-AUDIT-1", ts_ms: int = 1_700_000_000_000) -> dict:
    return {
        "rid": rid,
        "symbol": "BTCUSDT",
        "side": "BUY",
        "strategy_id": "aurora",
        "ts_ms": ts_ms,
        "order": {"qty": "0.01", "order_type": "MARKET"},
    }


def test_boundary_audit_clears_pending_after_routed_order_event() -> None:
    bus = _DispatchingBus()
    audit = IntentBoundaryAudit(
        bus=bus,
        config=type("Cfg", (), {"enabled": True, "route_ttl_ms": 2000, "downstream_ttl_ms": 5000})(),
    )
    audit.register_bus_listeners()

    proposal = _proposal_payload(rid="RID-SUCCESS")
    bus.emit("EVT:TRADE_INTENT_PROPOSED", proposal, "test")
    audit.mark_routed(
        rid="RID-SUCCESS",
        symbol="BTCUSDT",
        route="CMD:OPEN",
        strategy_id="aurora",
        side="BUY",
    )
    bus.emit(
        "EVT:ORDER_PLACED",
        {"rid": "RID-SUCCESS", "symbol": "BTCUSDT", "order_id": "123"},
        "order_placed",
    )

    assert audit.pending_count == 0
    rejects = [event for event in bus.events if event[0] == "EVT:TRADE_INTENT_REJECTED"]
    assert rejects == []


def test_boundary_audit_emits_bridge_timeout_reject_when_not_routed() -> None:
    bus = _DispatchingBus()
    audit = IntentBoundaryAudit(
        bus=bus,
        config=type("Cfg", (), {"enabled": True, "route_ttl_ms": 2000, "downstream_ttl_ms": 5000})(),
    )
    audit.register_bus_listeners()

    proposal = _proposal_payload(rid="RID-BRIDGE-TIMEOUT", ts_ms=1_700_000_000_000)
    bus.emit("EVT:TRADE_INTENT_PROPOSED", proposal, "test")
    audit.sweep(now_ms=1_700_000_002_000)

    rejects = [event for event in bus.events if event[0] == "EVT:TRADE_INTENT_REJECTED"]
    assert len(rejects) == 1
    reject_payload = rejects[0][1]
    assert reject_payload["reason_code"] == "NRR-EXECUTION-BRIDGE-TIMEOUT"
    assert reject_payload["stage"] == "EXECUTION"
    assert reject_payload["context"] == "trade_intent_boundary_audit"
    assert audit.pending_count == 0


def test_boundary_audit_emits_no_downstream_reject_when_routed_but_stalled() -> None:
    bus = _DispatchingBus()
    audit = IntentBoundaryAudit(
        bus=bus,
        config=type("Cfg", (), {"enabled": True, "route_ttl_ms": 2000, "downstream_ttl_ms": 5000})(),
    )
    audit.register_bus_listeners()

    proposal = _proposal_payload(rid="RID-NO-DOWNSTREAM")
    bus.emit("EVT:TRADE_INTENT_PROPOSED", proposal, "test")
    audit.mark_routed(
        rid="RID-NO-DOWNSTREAM",
        symbol="BTCUSDT",
        route="CMD:OPEN",
        strategy_id="aurora",
        side="BUY",
    )
    pending = audit.get_pending("RID-NO-DOWNSTREAM")
    assert pending is not None and pending.routed_ts_ms is not None

    audit.sweep(now_ms=pending.routed_ts_ms + 5000)

    rejects = [event for event in bus.events if event[0] == "EVT:TRADE_INTENT_REJECTED"]
    assert len(rejects) == 1
    reject_payload = rejects[0][1]
    assert reject_payload["reason_code"] == "NRR-EXECUTION-NO-DOWNSTREAM-EVENT"
    assert reject_payload["details"]["routed_via"] == "CMD:OPEN"
    assert audit.pending_count == 0


def test_intent_router_marks_open_intents_as_routed(fsm_harness) -> None:
    fsm, _bus, _cfg = fsm_harness
    portfolio_state = {
        "positions_last_ts_ms": 9_999_999_999_999,
        "equity_free_usdt": "10000",
        "open_positions_margin_usd": "0",
        "positions": [],
    }
    fsm._latest_portfolio_state = dict(portfolio_state)
    fsm.exposure_guard.on_portfolio(dict(portfolio_state))

    msg = Message(
        op="EVT",
        verb="TRADE_INTENT_PROPOSED",
        src="decision_making",
        dst="*",
        pld={
            "rid": "RID-ROUTED-OPEN",
            "instrument": "BTCUSDT",
            "side": "BUY",
            "order": {
                "qty": "0.01",
                "order_type": "MARKET",
            },
            "idempotent_key": "KEY-ROUTED-OPEN",
        },
        why="test_route",
    )

    fsm._on_trade_intent_proposed(msg)

    pending = fsm._intent_boundary_audit.get_pending("RID-ROUTED-OPEN")
    assert pending is not None
    assert pending.routed_via == "CMD:OPEN"
