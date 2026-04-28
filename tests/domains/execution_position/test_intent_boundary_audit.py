from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

from apps.reference.config_loader import get_config
from apps.reference.domains.decision_making.core.facade import DecisionMaking
from vfoundation.core.protocol import Message
from vfoundation.core.fsm_core import FSMCore
from vfoundation.core.schema_registry import init_global_registry

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
        config=type("Cfg", (), {
                    "enabled": True, "route_ttl_ms": 2000, "downstream_ttl_ms": 5000})(),
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
    rejects = [event for event in bus.events if event[0]
               == "EVT:TRADE_INTENT_REJECTED"]
    assert rejects == []


def test_boundary_audit_emits_bridge_timeout_reject_when_not_routed() -> None:
    bus = _DispatchingBus()
    audit = IntentBoundaryAudit(
        bus=bus,
        config=type("Cfg", (), {
                    "enabled": True, "route_ttl_ms": 2000, "downstream_ttl_ms": 5000})(),
    )
    audit.register_bus_listeners()

    proposal = _proposal_payload(
        rid="RID-BRIDGE-TIMEOUT", ts_ms=1_700_000_000_000)
    bus.emit("EVT:TRADE_INTENT_PROPOSED", proposal, "test")
    audit.sweep(now_ms=1_700_000_002_000)

    rejects = [event for event in bus.events if event[0]
               == "EVT:TRADE_INTENT_REJECTED"]
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
        config=type("Cfg", (), {
                    "enabled": True, "route_ttl_ms": 2000, "downstream_ttl_ms": 5000})(),
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

    rejects = [event for event in bus.events if event[0]
               == "EVT:TRADE_INTENT_REJECTED"]
    assert len(rejects) == 1
    reject_payload = rejects[0][1]
    assert reject_payload["reason_code"] == "NRR-EXECUTION-NO-DOWNSTREAM-EVENT"
    assert reject_payload["details"]["routed_via"] == "CMD:OPEN"
    assert audit.pending_count == 0


def test_boundary_audit_grants_submit_in_flight_grace_before_reject() -> None:
    bus = _DispatchingBus()
    audit = IntentBoundaryAudit(
        bus=bus,
        config=type("Cfg", (), {
                    "enabled": True, "route_ttl_ms": 2000, "downstream_ttl_ms": 5000})(),
    )
    audit.register_bus_listeners()

    proposal = _proposal_payload(rid="RID-IN-FLIGHT")
    bus.emit("EVT:TRADE_INTENT_PROPOSED", proposal, "test")
    audit.mark_routed(
        rid="RID-IN-FLIGHT",
        symbol="BTCUSDT",
        route="CMD:OPEN",
        strategy_id="aurora",
        side="BUY",
    )
    pending = audit.get_pending("RID-IN-FLIGHT")
    assert pending is not None and pending.routed_ts_ms is not None

    submit_started_ts_ms = pending.routed_ts_ms + 600
    with patch("apps.reference.domains.execution_position.intent_boundary_audit.get_clock") as mock_clock:
        mock_clock.return_value.now_ms.return_value = submit_started_ts_ms
        audit.mark_submit_started(
            rid="RID-IN-FLIGHT",
            symbol="BTCUSDT",
            stage="limit_rest_submit",
            strategy_id="aurora",
            side="BUY",
        )

    audit.sweep(now_ms=pending.routed_ts_ms + 5000)
    rejects = [event for event in bus.events if event[0]
               == "EVT:TRADE_INTENT_REJECTED"]
    assert rejects == []

    audit.sweep(now_ms=submit_started_ts_ms + 7000)
    rejects = [event for event in bus.events if event[0]
               == "EVT:TRADE_INTENT_REJECTED"]
    assert len(rejects) == 1
    reject_payload = rejects[0][1]
    assert reject_payload["reason_code"] == "NRR-EXECUTION-NO-DOWNSTREAM-EVENT"
    assert reject_payload["details"]["submit_in_flight_stage"] == "limit_rest_submit"


def test_boundary_audit_clears_pending_after_trade_executed_without_order_placed() -> None:
    bus = _DispatchingBus()
    audit = IntentBoundaryAudit(
        bus=bus,
        config=type("Cfg", (), {
                    "enabled": True, "route_ttl_ms": 2000, "downstream_ttl_ms": 5000})(),
    )
    audit.register_bus_listeners()

    proposal = _proposal_payload(rid="RID-FILL-DOWNSTREAM")
    bus.emit("EVT:TRADE_INTENT_PROPOSED", proposal, "test")
    audit.mark_routed(
        rid="RID-FILL-DOWNSTREAM",
        symbol="BTCUSDT",
        route="CMD:OPEN",
        strategy_id="aurora",
        side="BUY",
    )
    bus.emit(
        "EVT:TRADE_EXECUTED",
        {
            "rid": "RID-FILL-DOWNSTREAM",
            "symbol": "BTCUSDT",
            "side": "buy",
            "price": "50000",
            "quantity": "0.01",
            "ts": 1_700_000_000_500,
            "venue": "binance",
        },
        "WS_ORDER_UPDATE_FILLED",
    )

    assert audit.pending_count == 0
    rejects = [event for event in bus.events if event[0]
               == "EVT:TRADE_INTENT_REJECTED"]
    assert rejects == []


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


class _AllowSafetyGate:
    outcome = "ALLOW"
    intent_side = "LONG"
    trace_ts_ms = 1_700_000_000_000
    why_short = "boundary_hardening"
    signal_score = 0.91
    regime = "TREND_UP"
    regime_confidence = 0.87
    trend_dir = "1"
    trend_run_length = 0
    delta_price = 0
    pm_norm_10s = 0
    pm_norm_60s = 0
    pm_norm_300s = 0
    vol_pct_10s = 0
    vol_pct_60s = 0
    vol_pct_300s = 0
    regime_provenance = {
        "source_kind": "detector_cache",
        "detector_event": {
            "event_name": "EVT:REGIME_DETECTED",
            "rid": "rid-detector-btc-proof",
            "ts_ms": 1_700_000_000_000,
            "last_update_ts_ms": 1_700_000_000_123,
            "structural_regime_ref": "structural:BTCUSDT:1700000000000",
            "changed": False,
            "regime": "TREND_UP",
            "confidence": "0.87",
            "raw_regime": "TREND_UP",
            "raw_confidence": "0.87",
        },
        "cache_snapshot": {
            "cache_write_ts_ms": 1_700_000_000_456,
            "regime": "TREND_UP",
            "confidence": 0.87,
        },
    }


def test_decision_making_trace_intent_crosses_validated_boundary_and_starts_execpos_routing() -> None:
    init_global_registry(project_root=".")
    cfg = get_config()
    bus = FSMCore()
    observed_intents: list[dict] = []
    observed_open: list[Message] = []
    bus.listen("EVT:TRADE_INTENT_PROPOSED",
               lambda msg: observed_intents.append(msg.pld))
    bus.listen("DEC:OPEN", lambda msg: observed_open.append(msg))

    with patch("apps.reference.domains.execution_position.fsm.OrderGuardian"), \
            patch("apps.reference.domains.execution_position.fsm.OrderTimeoutWatchdog"), \
            patch("apps.reference.domains.execution_position.fsm.MetricsCollector"), \
            patch("apps.reference.domains.execution_position.fsm.read_pending_brackets_from_wal", return_value={}):
        from apps.reference.domains.execution_position.fsm import ExecPosFSM

        ep = ExecPosFSM(config=cfg, fsm=bus, shadow_mode=True)
        ep.log_adapter = MagicMock()
        portfolio_state = {
            "positions_last_ts_ms": 9_999_999_999_999,
            "equity_free_usdt": "10000",
            "open_positions_margin_usd": "0",
            "positions": [],
        }
        ep._latest_portfolio_state = dict(portfolio_state)
        ep.exposure_guard.on_portfolio(dict(portfolio_state))

        dm = DecisionMaking(fsm=bus, config=cfg)
        dm._builder._warmup_gate = lambda **_kw: False
        dm._builder._tca_prefs = {
            "max_slippage_bps": 10,
            "max_latency_ms": 100,
            "maker_preference": False,
        }
        dm._builder._risk_budgets = {
            "trade_cvar95_max_bps": 50,
            "session_cvar95_max_bps": 100,
        }
        dm._builder._resolve_order_policy = MagicMock(
            return_value=("MARKET", None, None))
        dm._builder._check_strategy_arbitration = MagicMock(
            return_value={"allowed": True})

        strategy_trace = {
            "objective": {"score": 0.93, "winner": "aurora"},
            "model": "aurora",
        }

        with patch(
            "apps.reference.domains.decision_making.core.facade.apply_safety_gates",
            return_value=_AllowSafetyGate(),
        ), patch(
            "apps.reference.domains.decision_making.intent.builder.wal.append",
            return_value="wal-ok",
        ), patch(
            "apps.reference.domains.decision_making.intent.builder.order_logger.write",
        ), patch(
            "apps.reference.domains.decision_making.intent.builder.print",
        ):
            dm._propose_trade_intent(
                symbol="BTCUSDT",
                side="BUY",
                qty=Decimal("0.01"),
                price=Decimal("50000"),
                stop_price=Decimal("49000"),
                target_price=Decimal("51000"),
                why_chain=["boundary_hardening"],
                rid="RID-TRACE-BOUNDARY",
                reduce_only=False,
                strategy_id="aurora",
                decision_ts_ms=1_700_000_000_000,
                strategy_trace=strategy_trace,
            )

    assert observed_intents
    assert observed_intents[0]["trace"]["objective"] == strategy_trace["objective"]
    assert observed_intents[0]["trace"]["model"] == strategy_trace["model"]
    assert observed_intents[0]["trace"]["kelly_provenance"]["source_path"] == "config.strategies.aurora.decision.kelly"
    assert observed_intents[0]["regime_provenance"]["source_kind"] == "detector_cache"
    assert observed_intents[0]["regime_provenance"]["detector_event"][
        "structural_regime_ref"] == "structural:BTCUSDT:1700000000000"
    pending = ep._intent_boundary_audit.get_pending("RID-TRACE-BOUNDARY")
    assert pending is not None
    assert pending.routed_via == "CMD:OPEN"
    assert observed_open
    assert observed_open[0].rid == "RID-TRACE-BOUNDARY"
    assert observed_open[0].pld["symbol"] == "BTCUSDT"
    assert observed_open[0].pld["order_type"] == "MARKET"
    assert observed_open[0].pld["regime"] == "TREND_UP"
    assert observed_open[0].pld["regime_confidence"] == 0.87
    # Verify regime_provenance is faithfully passed through the boundary.
    # The DEC:OPEN path may add additional None-valued optional fields from the
    # expanded EVT:REGIME_DETECTED schema; verify subset containment only.
    open_prov = observed_open[0].pld["regime_provenance"]
    intent_prov = observed_intents[0]["regime_provenance"]
    assert open_prov["source_kind"] == intent_prov["source_kind"]
    assert open_prov["cache_snapshot"] == intent_prov["cache_snapshot"]
    for k, v in intent_prov["detector_event"].items():
        assert open_prov["detector_event"][k] == v
    assert "rid" not in (observed_open[0].pld or {})
    assert "trace" not in (observed_open[0].pld or {})
