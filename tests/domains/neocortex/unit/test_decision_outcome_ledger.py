from __future__ import annotations

import json
from pathlib import Path

from apps.reference.domains.neocortex.contracts.decision_outcome_ledger import (
    DecisionOutcomeLedgerRow,
    DecisionOutcomeTerminalStatus,
)
from apps.reference.domains.neocortex.contracts.observation_envelope import (
    ObservationEnvelope,
)
from apps.reference.domains.neocortex.logic.datasets.time_provenance import (
    CausalTimeProvenance,
)
from apps.reference.domains.neocortex.logic.ledger.decision_outcome_ledger import (
    DecisionOutcomeLedgerSink,
)


def _observation_snapshot() -> dict[str, object]:
    envelope = ObservationEnvelope(
        observation_id="decision-1",
        symbol="BTCUSDT",
        decision_basis_ts_ms=1_700_000_000_000,
        source_event_name="EVT:STRATEGY_SIGNAL_PRODUCED",
        source_event_id="rid-1",
        event_time_source=CausalTimeProvenance.AURORA_EVENT,
        event_time_is_causal=True,
        trainable=True,
        dataset_visibility="trainable",
        freshness={"snapshot_age_ms": 0},
        missingness={"market_features_missing": False},
        market_features={"signal_score": 0.8},
        regime_state={"label": "TREND_UP", "confidence": 0.9},
        risk_state={"risk_score": 0.2},
        portfolio_state={"side": "FLAT"},
        system_stress_state={"trigger_event_type": "EVT:AUTHORITY_DECISION"},
        candidate_intent_summary={"side": "BUY"},
        gate_trace_summary={"final_outcome": "PASS"},
        state_vector=(0.8,),
        context_vector=(1.0,),
    )
    return envelope.model_dump(mode="json")


def test_journal_only_capture_rows_remain_diagnostics_only(tmp_path: Path) -> None:
    ledger_path = tmp_path / "decision_ledger_v1.jsonl"
    sink = DecisionOutcomeLedgerSink(
        path=ledger_path,
        queue_maxsize=8,
        overflow_policy="fail_closed",
        enqueue_timeout_ms=0,
        shutdown_timeout_ms=1_000,
    )
    sink.start()
    try:
        shadow_payload = {
            "decision_id": "decision-1",
            "rid": "rid-1",
            "symbol": "BTCUSDT",
            "request_ts_ms": 1_700_000_000_000,
            "response_ts_ms": 1_700_000_000_001,
            "authority_mode": "shadow",
            "action": "allow",
            "apply_result": "SHADOW_RECORDED",
            "reason_code": "JOURNAL_ONLY_CAPTURE",
            "reason_text": "journal-only capture",
            "causal_state_snapshot": _observation_snapshot(),
            "data_quality_flags": {
                "authority_mode": "shadow",
                "reason_code": "JOURNAL_ONLY_CAPTURE",
                "capture_mode": "journal_only",
                "authority_applied": False,
                "no_effect": True,
                "supports_counterfactual_join": True,
                "snapshot_provider_configured": True,
                "snapshot_missing": False,
                "has_nan": False,
                "is_stale": False,
            },
        }
        sink._on_shadow_decision_logged({"payload": shadow_payload})
        sink._on_terminal_event(
            "EVT:POSITION_CLOSED",
            {
                "payload": {
                    "decision_id": "decision-1",
                    "rid": "rid-1",
                    "lifecycle_id": "life-1",
                    "trade_id": "trade-1",
                    "realized_pnl_net": 12.5,
                    "fees": 0.25,
                }
            },
        )

        assert sink.wait_until_idle(timeout_sec=2.0) is True
    finally:
        sink.stop()

    rows = [
        DecisionOutcomeLedgerRow.model_validate(json.loads(line))
        for line in ledger_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(rows) == 1
    row = rows[0]
    assert row.dataset_visibility == "diagnostics_only"
    assert row.counterfactual_support == "unsupported"
    assert row.terminal_status == DecisionOutcomeTerminalStatus.EXECUTED_AND_CLOSED
    assert row.invalid_reason_code is None
    assert row.data_quality_flags["capture_mode"] == "journal_only"
    assert row.data_quality_flags["authority_applied"] is False
    assert row.data_quality_flags["no_effect"] is True
    assert row.support_quality["capture_mode"] == "journal_only"
    assert row.support_quality["authority_applied"] is False
    assert row.support_quality["no_effect"] is True
    assert row.support_quality["observation_provenance_present"] is True
    assert row.support_quality["observation_provenance_causal"] is True
    assert row.support_quality["observation_time_source"] == CausalTimeProvenance.AURORA_EVENT.value
    assert row.support_quality["observation_time_is_causal"] is True
    assert row.support_quality["observation_trainable"] is True
    assert row.support_quality["observation_dataset_visibility"] == "trainable"
    assert row.support_quality["observation_event_ts_present"] is True
    assert row.support_quality["observation_event_ts_ms"] == 1_700_000_000_000


def test_shadow_counterfactual_capture_rows_can_support_counterfactual_join(
    tmp_path: Path,
) -> None:
    ledger_path = tmp_path / "decision_ledger_v1.jsonl"
    sink = DecisionOutcomeLedgerSink(
        path=ledger_path,
        queue_maxsize=8,
        overflow_policy="fail_closed",
        enqueue_timeout_ms=0,
        shutdown_timeout_ms=1_000,
    )
    sink.start()
    try:
        shadow_payload = {
            "decision_id": "decision-2",
            "rid": "rid-2",
            "symbol": "BTCUSDT",
            "request_ts_ms": 1_700_000_000_000,
            "response_ts_ms": 1_700_000_000_001,
            "authority_mode": "shadow",
            "action": "deny",
            "apply_result": "SHADOW_RECORDED",
            "reason_code": "MODEL_DENY",
            "reason_text": "counterfactual deny",
            "causal_state_snapshot": _observation_snapshot(),
            "data_quality_flags": {
                "authority_mode": "shadow",
                "reason_code": "MODEL_DENY",
                "capture_mode": "shadow_counterfactual",
                "authority_applied": False,
                "no_effect": True,
                "supports_counterfactual_join": True,
                "counterfactual_evaluation": True,
                "returned_action": "ALLOW",
                "snapshot_provider_configured": True,
                "snapshot_missing": False,
                "has_nan": False,
                "is_stale": False,
            },
        }
        sink._on_shadow_decision_logged({"payload": shadow_payload})
        sink._on_terminal_event(
            "EVT:POSITION_CLOSED",
            {
                "payload": {
                    "decision_id": "decision-2",
                    "rid": "rid-2",
                    "lifecycle_id": "life-2",
                    "trade_id": "trade-2",
                    "realized_pnl_net": 6.25,
                    "fees": 0.1,
                }
            },
        )

        assert sink.wait_until_idle(timeout_sec=2.0) is True
    finally:
        sink.stop()

    rows = [
        DecisionOutcomeLedgerRow.model_validate(json.loads(line))
        for line in ledger_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(rows) == 1
    row = rows[0]
    assert row.dataset_visibility == "diagnostics_only"
    assert row.counterfactual_support == "supported"
    assert row.invalid_reason_code is None
    assert row.neocortex_action == "BLOCK"
    assert row.support_quality["counterfactual_support"] == "supported"
    assert row.support_quality["counterfactual_evaluation"] is True
    assert row.support_quality["returned_action_present"] is True


def test_unresolved_position_closed_row_is_invalid_for_dataset(tmp_path: Path) -> None:
    ledger_path = tmp_path / "decision_ledger_v1.jsonl"
    sink = DecisionOutcomeLedgerSink(
        path=ledger_path,
        queue_maxsize=8,
        overflow_policy="fail_closed",
        enqueue_timeout_ms=0,
        shutdown_timeout_ms=1_000,
    )
    sink.start()
    try:
        shadow_payload = {
            "decision_id": "decision-1",
            "rid": "rid-1",
            "symbol": "BTCUSDT",
            "request_ts_ms": 1_700_000_000_000,
            "response_ts_ms": 1_700_000_000_001,
            "authority_mode": "gated",
            "action": "allow",
            "apply_result": "ENFORCE_ALLOW",
            "causal_state_snapshot": _observation_snapshot(),
            "data_quality_flags": {
                "authority_mode": "gated",
                "supports_counterfactual_join": True,
                "snapshot_provider_configured": True,
                "snapshot_missing": False,
                "has_nan": False,
                "is_stale": False,
                "authority_applied": True,
                "no_effect": False,
            },
        }
        sink._on_shadow_decision_logged({"payload": shadow_payload})
        sink._on_terminal_event(
            "EVT:POSITION_CLOSED",
            {
                "payload": {
                    "decision_id": "decision-1",
                    "rid": "rid-1",
                    "lifecycle_id": "life-1",
                    "trade_id": "trade-1",
                    "pnl_status": "unresolved",
                    "realized_pnl_net": None,
                    "fees": None,
                }
            },
        )

        assert sink.wait_until_idle(timeout_sec=2.0) is True
    finally:
        sink.stop()

    rows = [
        DecisionOutcomeLedgerRow.model_validate(json.loads(line))
        for line in ledger_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(rows) == 1
    row = rows[0]
    assert row.terminal_status == DecisionOutcomeTerminalStatus.INVALID_FOR_DATASET
    assert row.invalid_reason_code == "TERMINAL_PNL_MISSING"
    assert row.dataset_visibility == "diagnostics_only"
    assert row.data_quality_flags["pnl_missing"] is True


def test_non_causal_snapshot_remains_blocked_without_journal_only_gate(tmp_path: Path) -> None:
    ledger_path = tmp_path / "decision_ledger_v1.jsonl"
    sink = DecisionOutcomeLedgerSink(
        path=ledger_path,
        queue_maxsize=8,
        overflow_policy="fail_closed",
        enqueue_timeout_ms=0,
        shutdown_timeout_ms=1_000,
    )
    sink.start()
    try:
        shadow_payload = {
            "decision_id": "decision-1",
            "rid": "rid-1",
            "symbol": "BTCUSDT",
            "request_ts_ms": 1_700_000_000_000,
            "response_ts_ms": 1_700_000_000_001,
            "authority_mode": "gated",
            "action": "allow",
            "apply_result": "ENFORCE_ALLOW",
            "causal_state_snapshot": {
                "observation_id": "decision-1",
                "symbol": "BTCUSDT",
                "decision_basis_ts_ms": 1_700_000_000_000,
                "event_time_source": CausalTimeProvenance.UNKNOWN.value,
                "event_time_is_causal": False,
                "trainable": False,
                "dataset_visibility": "diagnostics_only",
            },
            "data_quality_flags": {
                "authority_mode": "gated",
                "supports_counterfactual_join": True,
                "snapshot_provider_configured": True,
                "snapshot_missing": False,
                "has_nan": False,
                "is_stale": False,
                "authority_applied": True,
                "no_effect": False,
                "capture_mode": "gated",
            },
        }
        sink._on_shadow_decision_logged({"payload": shadow_payload})
        sink._on_terminal_event(
            "EVT:POSITION_CLOSED",
            {
                "payload": {
                    "decision_id": "decision-1",
                    "rid": "rid-1",
                    "lifecycle_id": "life-1",
                    "trade_id": "trade-1",
                    "pnl_status": "resolved",
                    "realized_pnl_net": 12.5,
                    "fees": 0.25,
                }
            },
        )

        assert sink.wait_until_idle(timeout_sec=2.0) is True
    finally:
        sink.stop()

    rows = [
        DecisionOutcomeLedgerRow.model_validate(json.loads(line))
        for line in ledger_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(rows) == 1
    row = rows[0]
    assert row.dataset_visibility == "diagnostics_only"
    assert row.invalid_reason_code == "NON_CAUSAL_TIME"
    assert row.support_quality["observation_provenance_present"] is True
    assert row.support_quality["observation_provenance_causal"] is False
    assert row.support_quality["observation_time_source"] == CausalTimeProvenance.UNKNOWN.value
    assert row.support_quality["observation_time_is_causal"] is False
    assert row.support_quality["observation_trainable"] is False
