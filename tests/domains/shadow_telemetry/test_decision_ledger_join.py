import json
import re
from pathlib import Path
from typing import Any

from apps.reference.domains.neocortex.contracts.failure_taxonomy import (
    FailureOutcomeTaxonomy,
    FailureReasonCode,
    get_failure_outcome_total,
    reset_failure_outcomes,
)
from apps.reference.telemetry.metrics import generate_latest
from apps.reference.domains.shadow_telemetry.ledger_writer import ShadowTelemetrySink


def _metric_value(metric_name: str, **labels: str) -> float:
    exposition = generate_latest().decode("utf-8")
    label_fragments = [f'{key}="{value}"' for key, value in labels.items()]
    pattern = re.compile(r" (-?[0-9]+(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?)$")
    for line in exposition.splitlines():
        if labels:
            if not line.startswith(f"{metric_name}{{"):
                continue
            if not all(fragment in line for fragment in label_fragments):
                continue
        elif not line.startswith(f"{metric_name} "):
            continue
        match = pattern.search(line)
        if match is not None:
            return float(match.group(1))
    return 0.0


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


def _read_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _causal_snapshot(
    values: list[float],
    *,
    tick_ts_ms: int = 1_700_000_000_000,
) -> dict[str, object]:
    return {
        "tick_ts_ms": tick_ts_ms,
        "state_vector": values,
        "event_time_source": "aurora_event",
        "event_time_is_causal": True,
        "trainable": True,
        "dataset_visibility": "trainable",
    }


def _decision_trace_payload(
    *,
    decision_id: str,
    rid: str,
    symbol: str,
    accepted_or_rejected: str,
    gate_chain_result: str,
    reject_reason: str | None = None,
) -> dict[str, object]:
    return {
        "rid": rid,
        "decision_id": decision_id,
        "cycle_key": f"ENTRY:{symbol}:300:1700000000000",
        "symbol": symbol,
        "side": "BUY",
        "strategy_id": "aurora",
        "ts": 1_700_000_001_234,
        "event_ts_ms": 1_700_000_001_234,
        "tf_sec": 300,
        "bar_close_ts_ms": 1_700_000_000_000,
        "intent_side": "LONG",
        "lifecycle_id": f"LIFE:{decision_id}",
        "intent_id": f"LIFE:{decision_id}",
        "raw_score": 0.88,
        "decision_score": 0.91,
        "active_threshold": 0.45,
        "score_to_threshold_ratio": 2.022222222222222,
        "decision_surface": "aurora_quadratic",
        "gate_chain_result": gate_chain_result,
        "accepted_or_rejected": accepted_or_rejected,
        "reject_reason": reject_reason,
        "regime": "TREND_UP",
        "regime_confidence": 0.82,
    }


def _make_sink(path: Path, **kwargs: Any) -> ShadowTelemetrySink:
    sink_kwargs = {
        "queue_maxsize": 8,
        "overflow_policy": "fail_closed",
        "enqueue_timeout_ms": 0,
        "shutdown_timeout_ms": 2000,
    }
    sink_kwargs.update(kwargs)
    return ShadowTelemetrySink(path=path, **sink_kwargs)


def test_trade_executed_is_alias_only_until_position_closed(
    tmp_path: Path,
) -> None:
    ledger_path = tmp_path / "decision_ledger_v1.jsonl"
    fsm = _StubFSM()
    sink = _make_sink(
        ledger_path,
        pending_ttl_ms=10_000,
        clock_ms_fn=lambda: 1_700_000_000_000,
    )
    sink.start()
    sink.register(fsm)

    fsm.emit(
        "SHADOW:NEOCORTEX_DECISION_LOGGED",
        payload={
            "decision_id": "decision-close-1",
            "rid": "RID-CLOSE-1",
            "symbol": "ETHUSDT",
            "authority_mode": "gated",
            "request_ts_ms": 1_700_000_000_000,
            "response_ts_ms": 1_700_000_000_010,
            "apply_result": "GATED_ALLOW",
            "action": "ALLOW",
            "fallback_reason": None,
            "causal_state_snapshot": {
                "snapshot_contract": "test_neocortex_state_snapshot_v1",
                **_causal_snapshot([0.1, 0.2, 0.3]),
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

    fsm.emit(
        "EVT:TRADE_INTENT_PROPOSED",
        payload={
            "rid": "RID-CLOSE-1",
            "symbol": "ETHUSDT",
            "idempotent_key": "LIFE-CLOSE-1",
            "lifecycle_id": "LIFE-CLOSE-1",
            "authority_context": {
                "decision_id": "decision-close-1",
                "authority_mode": "gated",
                "action": "allow",
                "apply_result": "GATED_ALLOW",
            },
        },
        why="trade_intent",
    )
    fsm.emit(
        "EVT:TRADE_EXECUTED",
        payload={
            "rid": "RID-CLOSE-1",
            "symbol": "ETHUSDT",
            "trade_id": "TRADE-CLOSE-1",
            "realized_pnl_net": 12.75,
        },
        why="trade_executed",
    )

    assert sink.wait_until_idle(0.5)
    assert _read_rows(ledger_path) == []

    fsm.emit(
        "EVT:POSITION_CLOSED",
        payload={
            "symbol": "ETHUSDT",
            "lifecycle_id": "LIFE-CLOSE-1",
            "trade_id": "TRADE-CLOSE-1",
            "realized_pnl_net": 12.75,
            "fees": 0.25,
            "close_reason": "TP_HIT",
        },
        why="position_closed",
    )

    assert sink.wait_until_idle(2.0)
    sink.stop()

    rows = _read_rows(ledger_path)
    assert len(rows) == 1
    row = rows[0]
    assert row["neocortex_action"] == "ALLOW"
    assert row["terminal_status"] == "EXECUTED_AND_CLOSED"
    assert row["execution_outcome"] == "EXECUTED"
    assert row["lifecycle_id"] == "LIFE-CLOSE-1"
    assert row["trade_id"] == "TRADE-CLOSE-1"
    assert row["realized_pnl_net"] == 12.75
    assert row["fees"] == 0.25
    assert row["data_quality_flags"]["joined_by_lifecycle_id"] is True


def test_decision_blocked_finalizes_vetoed_row(
    tmp_path: Path,
) -> None:
    ledger_path = tmp_path / "decision_ledger_v1.jsonl"
    fsm = _StubFSM()
    sink = _make_sink(
        ledger_path,
        pending_ttl_ms=10_000,
        clock_ms_fn=lambda: 1_700_000_000_000,
    )
    sink.start()
    sink.register(fsm)

    fsm.emit(
        "SHADOW:NEOCORTEX_DECISION_LOGGED",
        payload={
            "decision_id": "decision-veto-1",
            "rid": "RID-VETO-1",
            "symbol": "BTCUSDT",
            "authority_mode": "gated",
            "request_ts_ms": 1_700_000_000_000,
            "response_ts_ms": 1_700_000_000_010,
            "apply_result": "GATED_DENY",
            "action": "BLOCK",
            "fallback_reason": None,
            "causal_state_snapshot": _causal_snapshot([0.1]),
            "data_quality_flags": {
                "snapshot_missing": False,
                "supports_counterfactual_join": True,
                "has_nan": False,
                "is_stale": False,
            },
        },
        why="decision_logged",
    )

    fsm.emit(
        "EVT:DECISION_BLOCKED",
        payload={
            "rid": "RID-VETO-1",
            "symbol": "BTCUSDT",
            "reason_code": "NEOCORTEX_VETO",
            "details": {
                "decision_id": "decision-veto-1",
                "apply_result": "GATED_DENY",
            },
        },
        why="decision_blocked",
    )

    assert sink.wait_until_idle(2.0)
    sink.stop()

    rows = _read_rows(ledger_path)
    assert len(rows) == 1
    row = rows[0]
    assert row["terminal_status"] == "VETOED"
    assert row["execution_outcome"] == "FSM_BLOCKED"
    assert row["apply_result"] == "GATED_DENY"
    assert row["dataset_visibility"] == "trainable"


def test_fallback_reject_becomes_baseline_fallback_no_execution(
    tmp_path: Path,
) -> None:
    ledger_path = tmp_path / "decision_ledger_v1.jsonl"
    fsm = _StubFSM()
    sink = _make_sink(
        ledger_path,
        pending_ttl_ms=10_000,
        clock_ms_fn=lambda: 1_700_000_000_000,
    )
    sink.start()
    sink.register(fsm)

    fsm.emit(
        "SHADOW:NEOCORTEX_DECISION_LOGGED",
        payload={
            "decision_id": "decision-fallback-1",
            "rid": "RID-FALLBACK-1",
            "symbol": "SOLUSDT",
            "authority_mode": "shadow",
            "request_ts_ms": 1_700_000_000_000,
            "response_ts_ms": 1_700_000_000_010,
            "apply_result": "FALLBACK_BASELINE",
            "action": "FALLBACK",
            "fallback_reason": "BASELINE_UNAVAILABLE",
            "causal_state_snapshot": _causal_snapshot([0.2]),
            "data_quality_flags": {
                "snapshot_missing": False,
                "supports_counterfactual_join": True,
                "has_nan": False,
                "is_stale": False,
            },
        },
        why="decision_logged",
    )
    fsm.emit(
        "EVT:TRADE_INTENT_PROPOSED",
        payload={
            "rid": "RID-FALLBACK-1",
            "symbol": "SOLUSDT",
            "lifecycle_id": "LIFE-FALLBACK-1",
            "authority_context": {
                "decision_id": "decision-fallback-1",
                "authority_mode": "shadow",
                "action": "fallback",
                "apply_result": "FALLBACK_BASELINE",
                "fallback_reason": "BASELINE_UNAVAILABLE",
            },
        },
        why="trade_intent",
    )
    fsm.emit(
        "EVT:ORDER_REJECTED",
        payload={
            "symbol": "SOLUSDT",
            "lifecycle_id": "LIFE-FALLBACK-1",
            "reason_code": "EXCHANGE_REJECT",
        },
        why="order_rejected",
    )

    assert sink.wait_until_idle(2.0)
    sink.stop()

    rows = _read_rows(ledger_path)
    assert len(rows) == 1
    row = rows[0]
    assert row["terminal_status"] == "BASELINE_FALLBACK_NO_EXECUTION"
    assert row["execution_outcome"] == "FSM_BLOCKED"
    assert row["fallback_reason"] == "BASELINE_UNAVAILABLE"


def test_pending_decision_times_out_and_flushes(tmp_path: Path) -> None:
    ledger_path = tmp_path / "decision_ledger_v1.jsonl"
    now_holder = {"now_ms": 1_700_000_000_000}
    fsm = _StubFSM()
    sink = _make_sink(
        ledger_path,
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
            "authority_mode": "gated",
            "request_ts_ms": now_holder["now_ms"],
            "response_ts_ms": now_holder["now_ms"] + 5,
            "apply_result": "GATED_ALLOW",
            "action": "ALLOW",
            "fallback_reason": None,
            "causal_state_snapshot": {
                "snapshot_contract": "test_neocortex_state_snapshot_v1",
                **_causal_snapshot([0.5, 0.1], tick_ts_ms=now_holder["now_ms"]),
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
    assert row["terminal_status"] == "INVALID_FOR_DATASET"
    assert row["execution_outcome"] == "PENDING_TIMEOUT"
    assert row["invalid_reason_code"] == "TERMINAL_EVENT_MISSING"
    assert row["realized_pnl_net"] is None
    assert row["data_quality_flags"]["terminal_event_missing"] is True


def test_fallback_execution_becomes_baseline_fallback_executed(
    tmp_path: Path,
) -> None:
    ledger_path = tmp_path / "decision_ledger_v1.jsonl"
    fsm = _StubFSM()
    sink = _make_sink(
        ledger_path,
        pending_ttl_ms=10_000,
        clock_ms_fn=lambda: 1_700_000_000_000,
    )
    sink.start()
    sink.register(fsm)

    fsm.emit(
        "SHADOW:NEOCORTEX_DECISION_LOGGED",
        payload={
            "decision_id": "decision-fallback-exec-1",
            "rid": "RID-FALLBACK-EXEC-1",
            "symbol": "ADAUSDT",
            "authority_mode": "shadow",
            "request_ts_ms": 1_700_000_000_000,
            "response_ts_ms": 1_700_000_000_010,
            "apply_result": "FALLBACK_BASELINE",
            "action": "FALLBACK",
            "fallback_reason": "BASELINE_UNAVAILABLE",
            "causal_state_snapshot": _causal_snapshot([0.2]),
            "data_quality_flags": {
                "snapshot_missing": False,
                "supports_counterfactual_join": True,
                "has_nan": False,
                "is_stale": False,
            },
        },
        why="decision_logged",
    )
    fsm.emit(
        "EVT:TRADE_INTENT_PROPOSED",
        payload={
            "rid": "RID-FALLBACK-EXEC-1",
            "symbol": "ADAUSDT",
            "lifecycle_id": "LIFE-FALLBACK-EXEC-1",
            "authority_context": {
                "decision_id": "decision-fallback-exec-1",
                "authority_mode": "shadow",
                "action": "fallback",
                "apply_result": "FALLBACK_BASELINE",
                "fallback_reason": "BASELINE_UNAVAILABLE",
            },
        },
        why="trade_intent",
    )
    fsm.emit(
        "EVT:TRADE_EXECUTED",
        payload={
            "rid": "RID-FALLBACK-EXEC-1",
            "symbol": "ADAUSDT",
            "trade_id": "TRADE-FALLBACK-EXEC-1",
            "realized_pnl_net": 4.5,
        },
        why="trade_executed",
    )
    fsm.emit(
        "EVT:POSITION_CLOSED",
        payload={
            "symbol": "ADAUSDT",
            "lifecycle_id": "LIFE-FALLBACK-EXEC-1",
            "trade_id": "TRADE-FALLBACK-EXEC-1",
            "realized_pnl_net": 4.5,
            "fees": 0.1,
        },
        why="position_closed",
    )

    assert sink.wait_until_idle(2.0)
    sink.stop()

    rows = _read_rows(ledger_path)
    assert len(rows) == 1
    row = rows[0]
    assert row["terminal_status"] == "BASELINE_FALLBACK_EXECUTED"
    assert row["execution_outcome"] == "EXECUTED"
    assert row["dataset_visibility"] == "trainable"
    assert row["trade_id"] == "TRADE-FALLBACK-EXEC-1"


def test_upstream_reject_becomes_rejected_upstream(tmp_path: Path) -> None:
    ledger_path = tmp_path / "decision_ledger_v1.jsonl"
    fsm = _StubFSM()
    sink = _make_sink(
        ledger_path,
        pending_ttl_ms=10_000,
        clock_ms_fn=lambda: 1_700_000_000_000,
    )
    sink.start()
    sink.register(fsm)

    fsm.emit(
        "SHADOW:NEOCORTEX_DECISION_LOGGED",
        payload={
            "decision_id": "decision-reject-1",
            "rid": "RID-REJECT-1",
            "symbol": "XRPUSDT",
            "authority_mode": "gated",
            "request_ts_ms": 1_700_000_000_000,
            "response_ts_ms": 1_700_000_000_010,
            "apply_result": "GATED_ALLOW",
            "action": "ALLOW",
            "fallback_reason": None,
            "causal_state_snapshot": _causal_snapshot([0.3]),
            "data_quality_flags": {
                "snapshot_missing": False,
                "supports_counterfactual_join": True,
                "has_nan": False,
                "is_stale": False,
            },
        },
        why="decision_logged",
    )
    fsm.emit(
        "EVT:ORDER_REJECTED",
        payload={
            "decision_id": "decision-reject-1",
            "rid": "RID-REJECT-1",
            "symbol": "XRPUSDT",
            "reason_code": "EXCHANGE_REJECT",
        },
        why="order_rejected",
    )

    assert sink.wait_until_idle(2.0)
    sink.stop()

    rows = _read_rows(ledger_path)
    assert len(rows) == 1
    row = rows[0]
    assert row["terminal_status"] == "REJECTED_UPSTREAM"
    assert row["execution_outcome"] == "EXCHANGE_REJECTED"
    assert row["dataset_visibility"] == "trainable"


def test_decision_trace_accept_seed_emits_unresolved_row_before_terminal_event(tmp_path: Path) -> None:
    ledger_path = tmp_path / "decision_ledger_v1.jsonl"
    fsm = _StubFSM()
    sink = _make_sink(
        ledger_path,
        pending_ttl_ms=10_000,
        clock_ms_fn=lambda: 1_700_000_000_000,
    )
    sink.start()
    sink.register(fsm)

    fsm.emit(
        "SHADOW:NEOCORTEX_DECISION_LOGGED",
        payload={
            "decision_id": "decision-seed-accept-1",
            "rid": "RID-SEED-ACCEPT-1",
            "symbol": "BTCUSDT",
            "authority_mode": "gated",
            "request_ts_ms": 1_700_000_000_000,
            "response_ts_ms": 1_700_000_000_010,
            "apply_result": "GATED_ALLOW",
            "action": "ALLOW",
            "fallback_reason": None,
            "causal_state_snapshot": _causal_snapshot([0.2, 0.3]),
            "data_quality_flags": {
                "snapshot_missing": False,
                "supports_counterfactual_join": True,
                "has_nan": False,
                "is_stale": False,
            },
        },
        why="decision_logged",
    )
    fsm.emit(
        "EVT:DECISION_TRACE_EMITTED",
        payload=_decision_trace_payload(
            decision_id="decision-seed-accept-1",
            rid="RID-SEED-ACCEPT-1",
            symbol="BTCUSDT",
            accepted_or_rejected="ACCEPTED",
            gate_chain_result="ALLOW",
        ),
        why="decision_trace",
    )

    assert sink.wait_until_idle(2.0)
    sink.stop()

    rows = _read_rows(ledger_path)
    assert len(rows) == 1
    row = rows[0]
    assert row["terminal_status"] == "INVALID_FOR_DATASET"
    assert row["invalid_reason_code"] == "OUTCOME_UNRESOLVED"
    assert row["revision_status"] == "SEED_PENDING_OUTCOME"
    assert row["outcome_status"] == "UNRESOLVED_ACCEPTED"
    assert row["execution_outcome"] == "PENDING_TIMEOUT"
    assert row["dataset_visibility"] == "diagnostics_only"
    assert row["accepted_or_rejected"] == "ACCEPTED"
    assert row["cycle_key"] == "ENTRY:BTCUSDT:300:1700000000000"
    assert row["intent_id"] == "LIFE:decision-seed-accept-1"
    assert row["decision_surface"] == "aurora_quadratic"
    assert row["realized_pnl_net"] is None
    assert row["realized_pnl_gross"] is None
    assert row["fees"] is None
    assert row["close_reason"] is None
    assert row["close_ts_ms"] is None
    assert row["close_actor"] is None


def test_decision_trace_reject_seed_emits_vetoed_row_without_terminal_event(tmp_path: Path) -> None:
    ledger_path = tmp_path / "decision_ledger_v1.jsonl"
    fsm = _StubFSM()
    sink = _make_sink(
        ledger_path,
        pending_ttl_ms=10_000,
        clock_ms_fn=lambda: 1_700_000_000_000,
    )
    sink.start()
    sink.register(fsm)

    fsm.emit(
        "SHADOW:NEOCORTEX_DECISION_LOGGED",
        payload={
            "decision_id": "decision-seed-reject-1",
            "rid": "RID-SEED-REJECT-1",
            "symbol": "BTCUSDT",
            "authority_mode": "gated",
            "request_ts_ms": 1_700_000_000_000,
            "response_ts_ms": 1_700_000_000_010,
            "apply_result": "GATED_DENY",
            "action": "BLOCK",
            "fallback_reason": None,
            "causal_state_snapshot": _causal_snapshot([0.2, 0.3]),
            "data_quality_flags": {
                "snapshot_missing": False,
                "supports_counterfactual_join": True,
                "has_nan": False,
                "is_stale": False,
            },
        },
        why="decision_logged",
    )
    fsm.emit(
        "EVT:DECISION_TRACE_EMITTED",
        payload=_decision_trace_payload(
            decision_id="decision-seed-reject-1",
            rid="RID-SEED-REJECT-1",
            symbol="BTCUSDT",
            accepted_or_rejected="REJECTED",
            gate_chain_result="BLOCK",
            reject_reason="SAFETY_GATE_DENY",
        ),
        why="decision_trace",
    )

    assert sink.wait_until_idle(2.0)
    sink.stop()

    rows = _read_rows(ledger_path)
    assert len(rows) == 1
    row = rows[0]
    assert row["terminal_status"] == "VETOED"
    assert row["revision_status"] == "DECISION_TERMINAL"
    assert row["outcome_status"] == "NOT_APPLICABLE"
    assert row["execution_outcome"] == "FSM_BLOCKED"
    assert row["dataset_visibility"] == "trainable"
    assert row["accepted_or_rejected"] == "REJECTED"
    assert row["reject_reason"] == "SAFETY_GATE_DENY"
    assert row["realized_pnl_net"] is None
    assert row["fees"] is None


def test_first_terminal_event_wins_and_emits_single_row(tmp_path: Path) -> None:
    ledger_path = tmp_path / "decision_ledger_v1.jsonl"
    fsm = _StubFSM()
    sink = _make_sink(
        ledger_path,
        pending_ttl_ms=10_000,
        clock_ms_fn=lambda: 1_700_000_000_000,
    )
    sink.start()
    sink.register(fsm)

    fsm.emit(
        "SHADOW:NEOCORTEX_DECISION_LOGGED",
        payload={
            "decision_id": "decision-single-terminal-1",
            "rid": "RID-SINGLE-1",
            "symbol": "DOGEUSDT",
            "authority_mode": "gated",
            "request_ts_ms": 1_700_000_000_000,
            "response_ts_ms": 1_700_000_000_010,
            "apply_result": "GATED_ALLOW",
            "action": "ALLOW",
            "fallback_reason": None,
            "causal_state_snapshot": _causal_snapshot([0.4]),
            "data_quality_flags": {
                "snapshot_missing": False,
                "supports_counterfactual_join": True,
                "has_nan": False,
                "is_stale": False,
            },
        },
        why="decision_logged",
    )
    fsm.emit(
        "EVT:ORDER_REJECTED",
        payload={
            "decision_id": "decision-single-terminal-1",
            "rid": "RID-SINGLE-1",
            "symbol": "DOGEUSDT",
            "reason_code": "EXCHANGE_REJECT",
        },
        why="order_rejected",
    )
    fsm.emit(
        "EVT:DECISION_BLOCKED",
        payload={
            "decision_id": "decision-single-terminal-1",
            "rid": "RID-SINGLE-1",
            "symbol": "DOGEUSDT",
            "reason_code": "NEOCORTEX_VETO",
        },
        why="decision_blocked",
    )

    assert sink.wait_until_idle(2.0)
    sink.stop()

    rows = _read_rows(ledger_path)
    assert len(rows) == 1
    assert {row["decision_id"]
            for row in rows} == {"decision-single-terminal-1"}
    assert rows[0]["terminal_status"] == "REJECTED_UPSTREAM"


def test_dataset_visibility_downgrades_without_counterfactual_join(
    tmp_path: Path,
) -> None:
    ledger_path = tmp_path / "decision_ledger_v1.jsonl"
    fsm = _StubFSM()
    sink = _make_sink(
        ledger_path,
        pending_ttl_ms=10_000,
        clock_ms_fn=lambda: 1_700_000_000_000,
    )
    sink.start()
    sink.register(fsm)

    fsm.emit(
        "SHADOW:NEOCORTEX_DECISION_LOGGED",
        payload={
            "decision_id": "decision-dataset-1",
            "rid": "RID-DATASET-1",
            "symbol": "BNBUSDT",
            "authority_mode": "gated",
            "request_ts_ms": 1_700_000_000_000,
            "response_ts_ms": 1_700_000_000_010,
            "apply_result": "GATED_DENY",
            "action": "BLOCK",
            "fallback_reason": None,
            "causal_state_snapshot": _causal_snapshot([0.5]),
            "data_quality_flags": {
                "snapshot_missing": False,
                "supports_counterfactual_join": False,
                "has_nan": False,
                "is_stale": False,
            },
        },
        why="decision_logged",
    )
    fsm.emit(
        "EVT:DECISION_BLOCKED",
        payload={
            "decision_id": "decision-dataset-1",
            "rid": "RID-DATASET-1",
            "symbol": "BNBUSDT",
            "reason_code": "NEOCORTEX_VETO",
        },
        why="decision_blocked",
    )

    assert sink.wait_until_idle(2.0)
    sink.stop()

    rows = _read_rows(ledger_path)
    assert len(rows) == 1
    row = rows[0]
    assert row["terminal_status"] == "VETOED"
    assert row["dataset_visibility"] == "diagnostics_only"
    assert row["invalid_reason_code"] is None


def test_decision_id_match_wins_over_colliding_rid_alias(tmp_path: Path) -> None:
    ledger_path = tmp_path / "decision_ledger_v1.jsonl"
    fsm = _StubFSM()
    sink = _make_sink(
        ledger_path,
        pending_ttl_ms=10_000,
        clock_ms_fn=lambda: 1_700_000_000_000,
    )
    sink.start()
    sink.register(fsm)

    fsm.emit(
        "SHADOW:NEOCORTEX_DECISION_LOGGED",
        payload={
            "decision_id": "decision-collision-a",
            "rid": "RID-COLLISION-1",
            "symbol": "BTCUSDT",
            "authority_mode": "gated",
            "request_ts_ms": 1_700_000_000_000,
            "response_ts_ms": 1_700_000_000_010,
            "apply_result": "GATED_DENY",
            "action": "BLOCK",
            "fallback_reason": None,
            "causal_state_snapshot": _causal_snapshot([0.6]),
            "data_quality_flags": {
                "snapshot_missing": False,
                "supports_counterfactual_join": True,
                "has_nan": False,
                "is_stale": False,
            },
        },
        why="decision_logged_a",
    )
    fsm.emit(
        "SHADOW:NEOCORTEX_DECISION_LOGGED",
        payload={
            "decision_id": "decision-collision-b",
            "rid": "RID-COLLISION-1",
            "symbol": "ETHUSDT",
            "authority_mode": "gated",
            "request_ts_ms": 1_700_000_000_100,
            "response_ts_ms": 1_700_000_000_110,
            "apply_result": "GATED_ALLOW",
            "action": "ALLOW",
            "fallback_reason": None,
            "causal_state_snapshot": _causal_snapshot([0.7]),
            "data_quality_flags": {
                "snapshot_missing": False,
                "supports_counterfactual_join": True,
                "has_nan": False,
                "is_stale": False,
            },
        },
        why="decision_logged_b",
    )
    fsm.emit(
        "EVT:DECISION_BLOCKED",
        payload={
            "decision_id": "decision-collision-a",
            "rid": "RID-COLLISION-1",
            "symbol": "BTCUSDT",
            "reason_code": "NEOCORTEX_VETO",
        },
        why="decision_blocked_a",
    )
    fsm.emit(
        "EVT:ORDER_REJECTED",
        payload={
            "decision_id": "decision-collision-b",
            "rid": "RID-COLLISION-1",
            "symbol": "ETHUSDT",
            "reason_code": "EXCHANGE_REJECT",
        },
        why="order_rejected_b",
    )

    assert sink.wait_until_idle(2.0)
    sink.stop()

    rows = sorted(_read_rows(ledger_path), key=lambda row: row["decision_id"])
    assert len(rows) == 2
    assert rows[0]["decision_id"] == "decision-collision-a"
    assert rows[0]["terminal_status"] == "VETOED"
    assert rows[1]["decision_id"] == "decision-collision-b"
    assert rows[1]["terminal_status"] == "REJECTED_UPSTREAM"


def test_writer_failure_records_degraded_observability(
    tmp_path: Path,
    monkeypatch,
) -> None:
    reset_failure_outcomes()
    metric_before = _metric_value(
        "neocortex_ledger_write_failed_total",
        reason_code="TELEMETRY_FLUSH_FAILED",
    )
    ledger_path = tmp_path / "decision_ledger_v1.jsonl"
    fsm = _StubFSM()
    sink = _make_sink(
        ledger_path,
        pending_ttl_ms=10_000,
        clock_ms_fn=lambda: 1_700_000_000_000,
    )
    sink.start()
    sink.register(fsm)

    def _raising_open(*args, **kwargs):
        raise OSError("decision ledger unavailable")

    monkeypatch.setattr("builtins.open", _raising_open)

    fsm.emit(
        "SHADOW:NEOCORTEX_DECISION_LOGGED",
        payload={
            "decision_id": "decision-writer-failure-1",
            "rid": "RID-WRITER-FAILURE-1",
            "symbol": "SOLUSDT",
            "authority_mode": "gated",
            "request_ts_ms": 1_700_000_000_000,
            "response_ts_ms": 1_700_000_000_010,
            "apply_result": "GATED_DENY",
            "action": "BLOCK",
            "fallback_reason": None,
            "causal_state_snapshot": _causal_snapshot([0.8]),
            "data_quality_flags": {
                "snapshot_missing": False,
                "supports_counterfactual_join": True,
                "has_nan": False,
                "is_stale": False,
            },
        },
        why="decision_logged",
    )
    fsm.emit(
        "EVT:DECISION_BLOCKED",
        payload={
            "decision_id": "decision-writer-failure-1",
            "rid": "RID-WRITER-FAILURE-1",
            "symbol": "SOLUSDT",
            "reason_code": "NEOCORTEX_VETO",
        },
        why="decision_blocked",
    )

    assert sink.wait_until_idle(2.0)
    sink.stop()
    monkeypatch.undo()

    assert _read_rows(ledger_path) == []
    assert get_failure_outcome_total(
        taxonomy=FailureOutcomeTaxonomy.DEGRADED_OBSERVABILITY,
        reason_code=FailureReasonCode.TELEMETRY_FLUSH_FAILED,
    ) == 1
    assert _metric_value(
        "neocortex_ledger_write_failed_total",
        reason_code="TELEMETRY_FLUSH_FAILED",
    ) == metric_before + 1.0
