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
    assert row.terminal_status == DecisionOutcomeTerminalStatus.EXECUTED_AND_CLOSED
    assert row.invalid_reason_code is None
    assert row.data_quality_flags["capture_mode"] == "journal_only"
    assert row.data_quality_flags["authority_applied"] is False
    assert row.data_quality_flags["no_effect"] is True
    assert row.support_quality["capture_mode"] == "journal_only"
    assert row.support_quality["authority_applied"] is False
    assert row.support_quality["no_effect"] is True
