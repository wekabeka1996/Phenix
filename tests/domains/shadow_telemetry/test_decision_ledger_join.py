import decimal
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from apps.reference.domains.decision_making.authority_bridge import NeocortexAuthorityBridge
from apps.reference.domains.decision_making.intent.builder import IntentBuilder
from apps.reference.domains.decision_making.schemas.control_decision import (
    ControlDecisionAction,
    ControlDecisionRequest,
    ControlDecisionResponse,
)
from apps.reference.domains.shadow_telemetry.ledger_writer import ShadowTelemetrySink


class _StubEvent:
    def __init__(self, payload):
        self.pld = payload


class _StubFSM:
    def __init__(self) -> None:
        self.listeners: dict[str, list] = {}
        self.emitted: list[dict] = []
        self.order_index = None

    def listen(self, event_name: str, handler) -> None:
        self.listeners.setdefault(event_name, []).append(handler)

    def emit(self, event_name: str, payload: dict | None = None, why: str = "", **kwargs) -> None:
        event_payload = payload if payload is not None else kwargs.get("payload") or {
        }
        self.emitted.append(
            {"event": event_name, "payload": event_payload, "why": why})
        for handler in self.listeners.get(event_name, []):
            handler(_StubEvent(event_payload))


class _FakeSG:
    intent_side = "LONG"
    trace_ts_ms = 1_700_000_000_000
    why_short = ""
    signal_score = 0.5
    regime = "TREND_UP"
    regime_confidence = 0.9
    trend_dir = 1
    trend_run_length = 1
    delta_price = 0
    pm_norm_10s = 0
    pm_norm_60s = 0
    pm_norm_300s = 0
    vol_pct_10s = 0
    vol_pct_60s = 0
    vol_pct_300s = 0


def _safe_decimal(value, default=None):
    if value in (None, "", "None"):
        return default
    return decimal.Decimal(str(value))


def _make_config():
    kelly_cfg = SimpleNamespace(
        base_probability="0.5",
        kelly_cap="0.25",
        kelly_alpha="0.8",
        payoff_ratio_r="1.5",
        p_min="0.45",
        p_max="0.65",
        uplift_factor="0.2",
    )
    strategy_cfg = SimpleNamespace(
        execution=SimpleNamespace(entry_order_type="LIMIT", entry_tif="GTC"),
        decision=SimpleNamespace(kelly=kelly_cfg),
    )
    return SimpleNamespace(strategies=SimpleNamespace(aurora=strategy_cfg))


def _snapshot_provider(**kwargs):
    return (
        {
            "snapshot_contract": "test_neocortex_state_snapshot_v1",
            "symbol": kwargs["symbol"],
            "tick_ts_ms": kwargs["decision_basis_ts"],
            "feature_event_ts_ms": kwargs["decision_basis_ts"],
            "state_vector": [0.1, 0.2, 0.3],
            "context_vector": [1.0, 0.0],
        },
        {
            "supports_counterfactual_join": True,
            "is_projection": False,
        },
    )


def _make_builder(*, fsm: _StubFSM, authority_bridge: NeocortexAuthorityBridge) -> IntentBuilder:
    clock = MagicMock()
    clock.now_ms.return_value = 1_700_000_000_000
    clock.now_sec.return_value = 1_700_000_000
    return IntentBuilder(
        logger=MagicMock(),
        fsm=fsm,
        clock=clock,
        config=_make_config(),
        tca_prefs={
            "max_slippage_bps": 25,
            "max_latency_ms": 3000,
            "maker_preference": "neutral",
        },
        risk_budgets={
            "trade_cvar95_max_bps": 100,
            "session_cvar95_max_bps": 200,
        },
        safe_decimal_fn=_safe_decimal,
        check_strategy_arbitration_fn=MagicMock(
            side_effect=lambda *_, commit=False, **__: {
                "allowed": True, "reason": None}
        ),
        warmup_gate_fn=lambda **_kwargs: False,
        emit_rejected_fn=MagicMock(),
        record_blocked_fn=MagicMock(),
        record_accepted_fn=MagicMock(),
        emit_deferred_fn=MagicMock(),
        get_side_bias_params_fn=MagicMock(return_value=(0, 600, 0.6, 0.9)),
        side_intent_window={},
        get_regime_epoch_ref_fn=lambda symbol: f"epoch:{symbol}:123",
        authority_bridge=authority_bridge,
        authority_deadline_budget_ms=20,
        shadow_emit_fn=lambda event_name, payload, why: fsm.emit(
            event_name, payload=payload, why=why),
        causal_state_snapshot_fn=_snapshot_provider,
    )


def _build_kwargs(*, symbol: str, rid: str) -> dict:
    return {
        "symbol": symbol,
        "side": "BUY",
        "qty": decimal.Decimal("1.5"),
        "price": decimal.Decimal("50000.25"),
        "why_chain": ["shadow_ledger_test"],
        "rid": rid,
        "reduce_only": False,
        "strategy_id": "aurora",
        "decision_ts_ms": 1_700_000_000_999,
        "stop_price": "49000.50",
        "target_price": decimal.Decimal("51000.75"),
        "entry_plan_trace": {"plan": "maker_pullback"},
        "tf_sec": 300,
        "max_slippage_bps": None,
        "max_latency_ms": None,
        "risk_score": 0.33,
        "tpsl_owner_ctx": None,
        "strategy_trace": {"objective": {"score": 0.9}},
        "normalize_mode": "signed_v2",
        "sg": _FakeSG(),
    }


def _read_rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


@patch("apps.reference.domains.decision_making.intent.builder.order_logger.write")
@patch("apps.reference.domains.decision_making.intent.builder.print")
@patch("apps.reference.domains.decision_making.intent.builder.emit_regime_decision_audit")
@patch("apps.reference.domains.decision_making.intent.builder._trade_lifecycle", None)
@patch("apps.reference.domains.decision_making.intent.builder.IntentBuilder._resolve_order_policy")
@patch("apps.reference.domains.decision_making.intent.builder.wal.append")
def test_fsm_block_is_joined_to_allow_decision(
    mock_wal,
    mock_policy,
    _mock_emit_regime_decision_audit,
    _mock_print,
    _mock_order_logger_write,
    tmp_path: Path,
) -> None:
    async def _allow(req: ControlDecisionRequest) -> ControlDecisionResponse:
        return ControlDecisionResponse(
            decision_id=req.decision_id,
            action=ControlDecisionAction.ALLOW,
            apply_result="ALLOW",
            fallback_reason=None,
            ttl_ms=10,
        )

    ledger_path = tmp_path / "decision_ledger_v1.jsonl"
    fsm = _StubFSM()
    sink = ShadowTelemetrySink(
        path=ledger_path, pending_ttl_ms=10_000, clock_ms_fn=lambda: 1_700_000_000_000)
    sink.start()
    sink.register(fsm)

    mock_policy.return_value = ("LIMIT", "GTC", 10_000)
    mock_wal.return_value = "wal-ok"
    builder = _make_builder(
        fsm=fsm, authority_bridge=NeocortexAuthorityBridge(authority_fn=_allow))
    builder.build_and_emit(
        **_build_kwargs(symbol="BTCUSDT", rid="RID-FSM-BLOCK"))

    fsm.emit(
        "EVT:EXECUTION_GUARD_BLOCKED",
        payload={"rid": "RID-FSM-BLOCK", "symbol": "BTCUSDT",
                 "reason_code": "GUARD_TEST"},
        why="guard_blocked",
    )
    assert sink.wait_until_idle(2.0)
    sink.stop()

    rows = _read_rows(ledger_path)
    assert len(rows) == 1
    row = rows[0]
    assert row["neocortex_action"] == "ALLOW"
    assert row["execution_outcome"] == "FSM_BLOCKED"
    assert row["rid"] == "RID-FSM-BLOCK"


@patch("apps.reference.domains.decision_making.intent.builder.order_logger.write")
@patch("apps.reference.domains.decision_making.intent.builder.print")
@patch("apps.reference.domains.decision_making.intent.builder.emit_regime_decision_audit")
@patch("apps.reference.domains.decision_making.intent.builder._trade_lifecycle", None)
@patch("apps.reference.domains.decision_making.intent.builder.IntentBuilder._resolve_order_policy")
@patch("apps.reference.domains.decision_making.intent.builder.wal.append")
def test_trade_executed_writes_realized_pnl(
    mock_wal,
    mock_policy,
    _mock_emit_regime_decision_audit,
    _mock_print,
    _mock_order_logger_write,
    tmp_path: Path,
) -> None:
    async def _allow(req: ControlDecisionRequest) -> ControlDecisionResponse:
        return ControlDecisionResponse(
            decision_id=req.decision_id,
            action=ControlDecisionAction.ALLOW,
            apply_result="ALLOW",
            fallback_reason=None,
            ttl_ms=10,
        )

    ledger_path = tmp_path / "decision_ledger_v1.jsonl"
    fsm = _StubFSM()
    sink = ShadowTelemetrySink(
        path=ledger_path, pending_ttl_ms=10_000, clock_ms_fn=lambda: 1_700_000_000_000)
    sink.start()
    sink.register(fsm)

    mock_policy.return_value = ("LIMIT", "GTC", 10_000)
    mock_wal.return_value = "wal-ok"
    builder = _make_builder(
        fsm=fsm, authority_bridge=NeocortexAuthorityBridge(authority_fn=_allow))
    builder.build_and_emit(
        **_build_kwargs(symbol="ETHUSDT", rid="RID-EXECUTED"))

    fsm.emit(
        "EVT:TRADE_EXECUTED",
        payload={
            "rid": "RID-EXECUTED",
            "symbol": "ETHUSDT",
            "realized_pnl_net": 12.75,
        },
        why="trade_executed",
    )
    assert sink.wait_until_idle(2.0)
    sink.stop()

    rows = _read_rows(ledger_path)
    assert len(rows) == 1
    row = rows[0]
    assert row["neocortex_action"] == "ALLOW"
    assert row["execution_outcome"] == "EXECUTED"
    assert row["realized_pnl_net"] == 12.75


def test_pending_decision_times_out_and_flushes(tmp_path: Path) -> None:
    ledger_path = tmp_path / "decision_ledger_v1.jsonl"
    now_holder = {"now_ms": 1_700_000_000_000}
    fsm = _StubFSM()
    sink = ShadowTelemetrySink(
        path=ledger_path,
        pending_ttl_ms=1_000,
        cleanup_interval_ms=60_000,
        clock_ms_fn=lambda: now_holder["now_ms"],
    )
    sink.start()
    sink.register(fsm)

    fsm.emit(
        "SHADOW:NEOCORTEX_DECISION_LOGGED",
        payload={
            "decision_id": "decision-timeout-1",
            "rid": "RID-TIMEOUT",
            "symbol": "SOLUSDT",
            "decision_ts_ms": now_holder["now_ms"],
            "action": "ALLOW",
            "fallback_reason": None,
            "causal_state_snapshot": {
                "snapshot_contract": "test_neocortex_state_snapshot_v1",
                "tick_ts_ms": now_holder["now_ms"],
                "state_vector": [0.5, 0.1],
            },
            "data_quality_flags": {
                "snapshot_missing": False,
                "supports_counterfactual_join": True,
                "has_nan": False,
                "is_stale": False,
            },
        },
        why="decision_logged",
    )

    now_holder["now_ms"] += 1_500
    assert sink.flush_expired(now_ms=now_holder["now_ms"]) == 1
    assert sink.wait_until_idle(2.0)
    sink.stop()

    rows = _read_rows(ledger_path)
    assert len(rows) == 1
    row = rows[0]
    assert row["execution_outcome"] == "PENDING_TIMEOUT"
    assert row["realized_pnl_net"] is None
    assert row["data_quality_flags"]["terminal_event_missing"] is True
