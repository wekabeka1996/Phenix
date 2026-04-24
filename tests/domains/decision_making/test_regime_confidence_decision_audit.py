from __future__ import annotations

import json
from collections import deque
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

from apps.reference.config_loader import get_config
from apps.reference.domains.decision_making.core.facade import DecisionMaking
from apps.reference.domains.decision_making.gates.safety_gates import apply_safety_gates
from vfoundation.core.fsm_core import FSMCore


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _regime_cache_snapshot(*, confidence: str) -> dict:
    return {
        "regime": "TREND_UP",
        "confidence": confidence,
        "cache_write_ts_ms": 1_700_000_000_456,
        "basis_tf_sec": 300,
        "bar_close_ts_ms": 1_700_000_000_000,
        "changed": False,
        "stable_confidence": confidence,
        "source_model": "sma_trend_v1",
        "pre_cutoff_source_model": "sma_trend_v1",
        "confidence_min": "0.15",
        "confidence_max": "0.85",
        "pre_cutoff_regime": "TREND_UP",
        "pre_cutoff_confidence": confidence,
        "pre_cutoff_clamped_to_min": False,
        "pre_cutoff_clamped_to_max": False,
        "pre_cutoff_boundary_reason": None,
        "uncertain_cutoff": "0.22",
        "demoted_to_uncertain": False,
        "raw_regime": "TREND_UP",
        "raw_confidence": confidence,
        "raw_boundary_reason": None,
        "hysteresis_bars": 3,
        "hysteresis_confirm_count": 3,
        "carried_previous_stable": False,
        "emitted_confidence_kind": "stable_heartbeat",
        "reason_summary": "pre_cutoff_source=sma_trend_v1; hysteresis_confirm=3/3",
        "regime_provenance": {
            "source_kind": "detector_cache",
            "detector_event": {
                "event_name": "EVT:REGIME_DETECTED",
                "rid": "rid-detector-audit-1",
                "ts_ms": 1_700_000_000_000,
                "last_update_ts_ms": 1_700_000_000_123,
                "structural_regime_ref": "structural:BTCUSDT:1700000000000",
                "basis_tf_sec": 300,
                "bar_close_ts_ms": 1_700_000_000_000,
                "changed": False,
                "regime": "TREND_UP",
                "confidence": confidence,
                "stable_confidence": confidence,
                "source_model": "sma_trend_v1",
                "pre_cutoff_source_model": "sma_trend_v1",
                "confidence_min": "0.15",
                "confidence_max": "0.85",
                "pre_cutoff_regime": "TREND_UP",
                "pre_cutoff_confidence": confidence,
                "pre_cutoff_clamped_to_min": False,
                "pre_cutoff_clamped_to_max": False,
                "pre_cutoff_boundary_reason": None,
                "uncertain_cutoff": "0.22",
                "demoted_to_uncertain": False,
                "raw_regime": "TREND_UP",
                "raw_confidence": confidence,
                "raw_boundary_reason": None,
                "hysteresis_bars": 3,
                "hysteresis_confirm_count": 3,
                "carried_previous_stable": False,
                "emitted_confidence_kind": "stable_heartbeat",
                "reason_summary": "pre_cutoff_source=sma_trend_v1; hysteresis_confirm=3/3",
            },
            "cache_snapshot": {
                "cache_write_ts_ms": 1_700_000_000_456,
                "regime": "TREND_UP",
                "confidence": float(confidence),
            },
        },
    }


def _configured_dm() -> DecisionMaking:
    cfg = get_config()
    cfg.strategies.aurora.safety_gates.enabled = True
    cfg.domains.decision_making.directional_sanity.enabled = True
    cfg.domains.decision_making.directional_sanity.min_abs_delta_price = 0.0
    cfg.domains.decision_making.directional_sanity.min_confidence = 0.0
    cfg.domains.decision_making.directional_sanity.consecutive_bars = 1
    cfg.domains.decision_making.price_motion_sanity.enabled = False
    return DecisionMaking(fsm=FSMCore(), config=cfg)


def test_allow_path_writes_regime_decision_audit_and_threshold_metadata(
    tmp_path: Path,
    monkeypatch,
) -> None:
    audit_path = tmp_path / "regime_confidence_audit_v1.jsonl"
    monkeypatch.setenv("REGIME_CONFIDENCE_AUDIT_LOG_FILE", str(audit_path))

    dm = _configured_dm()
    dm.symbol_states["BTCUSDT"] = {"_delta_price_hist": deque([1.0], maxlen=20)}
    dm._per_symbol_regimes["BTCUSDT"] = _regime_cache_snapshot(confidence="0.87")
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
    dm._builder._resolve_order_policy = MagicMock(return_value=("MARKET", None, None))
    dm._builder._check_strategy_arbitration = MagicMock(return_value={"allowed": True})

    with patch(
        "apps.reference.domains.decision_making.intent.builder.wal.append",
        return_value="wal-ok",
    ), patch(
        "apps.reference.domains.decision_making.intent.builder.order_logger.write"
    ) as mock_order_write, patch(
        "apps.reference.domains.decision_making.intent.builder.print"
    ):
        dm._propose_trade_intent(
            symbol="BTCUSDT",
            side="BUY",
            qty=Decimal("0.01"),
            price=Decimal("50000"),
            why_chain=["regime_confidence_audit", "signal_score=0.93"],
            rid="rid-allow-audit-1",
            reduce_only=False,
            strategy_id="aurora",
            decision_ts_ms=1_700_000_000_999,
            stop_price=Decimal("49000"),
            target_price=Decimal("51000"),
        )

    records = _read_jsonl(audit_path)
    decision_records = [record for record in records if record["record_type"] == "decision"]
    assert len(decision_records) == 1

    decision = decision_records[0]
    assert decision["outcome"] == "ALLOW"
    assert decision["threshold_verdict"] == "PASS"
    assert decision["threshold_applied"] is True
    assert decision["min_regime_confidence"] == 0.42
    assert decision["regime_confidence_used"] == 0.87
    assert decision["raw_confidence"] == 0.87
    assert decision["stable_confidence"] == 0.87
    assert decision["bar_close_ts_ms"] == 1_700_000_000_000
    assert decision["operator_visible_mismatch"] is False
    assert decision["lifecycle_id"] is not None

    metadata = mock_order_write.call_args[0][0]["metadata"]
    assert metadata["threshold_verdict"] == "PASS"
    assert metadata["threshold_applied"] is True
    assert metadata["min_regime_confidence"] == 0.42


def test_deny_path_writes_regime_decision_audit_for_threshold_block(
    tmp_path: Path,
    monkeypatch,
) -> None:
    audit_path = tmp_path / "regime_confidence_audit_v1.jsonl"
    monkeypatch.setenv("REGIME_CONFIDENCE_AUDIT_LOG_FILE", str(audit_path))

    dm = _configured_dm()
    dm._per_symbol_regimes["BTCUSDT"] = _regime_cache_snapshot(confidence="0.30")

    with patch(
        "apps.reference.domains.decision_making.core.facade.order_logger.write"
    ):
        dm._propose_trade_intent(
            symbol="BTCUSDT",
            side="BUY",
            qty=Decimal("0.01"),
            price=Decimal("50000"),
            why_chain=["regime_confidence_audit"],
            rid="rid-block-audit-1",
            reduce_only=False,
            strategy_id="aurora",
            decision_ts_ms=1_700_000_000_999,
        )

    records = _read_jsonl(audit_path)
    decision_records = [record for record in records if record["record_type"] == "decision"]
    assert len(decision_records) == 1

    decision = decision_records[0]
    assert decision["outcome"] == "DENY"
    assert decision["threshold_verdict"] == "BLOCK"
    assert decision["threshold_applied"] is True
    assert decision["min_regime_confidence"] == 0.42
    assert decision["regime_confidence_used"] == 0.3
    assert "0.3 < min=0.42" in decision["threshold_reason"]
    assert decision["bar_close_ts_ms"] == 1_700_000_000_000


def test_apply_safety_gates_marks_threshold_bypass_when_strategy_gate_disabled() -> None:
    cfg = get_config()
    cfg.strategies.aurora.safety_gates.enabled = False
    cfg.domains.decision_making.directional_sanity.enabled = True
    cfg.domains.decision_making.directional_sanity.min_abs_delta_price = 0.0
    cfg.domains.decision_making.directional_sanity.min_confidence = 0.0
    cfg.domains.decision_making.directional_sanity.consecutive_bars = 1
    cfg.domains.decision_making.price_motion_sanity.enabled = False

    result = apply_safety_gates(
        symbol="BTCUSDT",
        side="BUY",
        reduce_only=False,
        strategy_id="aurora",
        decision_ts_ms=1_700_000_000_999,
        why_chain=["regime_confidence_audit"],
        config=cfg,
        clock=MagicMock(now_ms=MagicMock(return_value=1_700_000_000_999)),
        symbol_states={"BTCUSDT": {"_delta_price_hist": deque([1.0], maxlen=20)}},
        per_symbol_regimes={"BTCUSDT": _regime_cache_snapshot(confidence="0.30")},
        system_stress_states={},
    )

    assert result.outcome == "ALLOW"
    assert result.threshold_applied is False
    assert result.threshold_verdict == "BYPASS"
    assert result.threshold_reason == "safety_gates_disabled"
    assert result.min_regime_confidence == 0.42
