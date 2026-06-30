from __future__ import annotations

import json
from collections import deque
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import apps.reference.config.domains.decision_making as domain_dm
from apps.reference.config_loader import ConfigLoader, get_config
from apps.reference.domains.decision_making.core.facade import DecisionMaking
from apps.reference.domains.decision_making.gates.safety_gates import apply_safety_gates
from apps.reference.telemetry.regime_confidence_audit import emit_regime_decision_audit
from vfoundation.core.fsm_core import FSMCore


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _regime_cache_snapshot(*, confidence: str, regime: str = "TREND_UP") -> dict:
    return {
        "regime": regime,
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
        "pre_cutoff_regime": regime,
        "pre_cutoff_confidence": confidence,
        "pre_cutoff_clamped_to_min": False,
        "pre_cutoff_clamped_to_max": False,
        "pre_cutoff_boundary_reason": None,
        "uncertain_cutoff": "0.22",
        "demoted_to_uncertain": False,
        "raw_regime": regime,
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
                "regime": regime,
                "confidence": confidence,
                "stable_confidence": confidence,
                "source_model": "sma_trend_v1",
                "pre_cutoff_source_model": "sma_trend_v1",
                "confidence_min": "0.15",
                "confidence_max": "0.85",
                "pre_cutoff_regime": regime,
                "pre_cutoff_confidence": confidence,
                "pre_cutoff_clamped_to_min": False,
                "pre_cutoff_clamped_to_max": False,
                "pre_cutoff_boundary_reason": None,
                "uncertain_cutoff": "0.22",
                "demoted_to_uncertain": False,
                "raw_regime": regime,
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
                "regime": regime,
                "confidence": float(confidence),
            },
        },
    }


def _configured_dm(*, enable_nrr026: bool = False) -> DecisionMaking:
    cfg = _fresh_config()
    cfg.strategies.aurora.safety_gates.enabled = True
    cfg.domains.decision_making.directional_sanity.enabled = True
    cfg.domains.decision_making.directional_sanity.min_abs_delta_price = 0.0
    cfg.domains.decision_making.directional_sanity.min_confidence = 0.0
    cfg.domains.decision_making.directional_sanity.nrr026_enabled = enable_nrr026
    cfg.domains.decision_making.directional_sanity.consecutive_bars = 1
    cfg.domains.decision_making.price_motion_sanity.enabled = False
    cfg.strategies.aurora.safety_gates.regime_confidence = None
    return DecisionMaking(fsm=FSMCore(), config=cfg)


def _fresh_config():
    return ConfigLoader(Path("config/aurora")).load_config()


def _current_domain_max_regime_confidence_by_regime() -> dict[str, float]:
    max_by_regime = _fresh_config(
    ).domains.decision_making.directional_sanity.max_regime_confidence_by_regime
    assert max_by_regime is not None
    return dict(max_by_regime)


def _current_domain_band_activation_cases() -> list[tuple[str, float, str, str | None, str, float, float | None]]:
    max_by_regime = _current_domain_max_regime_confidence_by_regime()
    return [
        ("TREND_UP", 0.19, "DENY", "NRR-026",
         "below_min", 0.20, max_by_regime["TREND_UP"]),
        ("TREND_UP", 0.25, "ALLOW", None, "none",
         0.20, max_by_regime["TREND_UP"]),
        (
            "TREND_UP",
            round(max_by_regime["TREND_UP"] + 0.01, 2),
            "DENY",
            "NRR-063",
            "above_max",
            0.20,
            max_by_regime["TREND_UP"],
        ),
        ("TREND_DOWN", 0.19, "DENY", "NRR-026",
         "below_min", 0.20, max_by_regime["TREND_DOWN"]),
        ("TREND_DOWN", 0.25, "ALLOW", None, "none",
         0.20, max_by_regime["TREND_DOWN"]),
        (
            "TREND_DOWN",
            round(max_by_regime["TREND_DOWN"] + 0.01, 2),
            "DENY",
            "NRR-063",
            "above_max",
            0.20,
            max_by_regime["TREND_DOWN"],
        ),
        ("MEAN_REVERSION", 0.34, "DENY", "NRR-026", "below_min", 0.35, None),
        ("MEAN_REVERSION", 0.36, "ALLOW", None, "none", 0.35, None),
        ("MEAN_REVERSION", 0.90, "ALLOW", None, "none", 0.35, None),
    ]


def _enable_regime_confidence_floor_gate(cfg) -> None:
    cfg.domains.decision_making.directional_sanity.nrr026_enabled = True


def _audit_sg(
    *,
    confidence: float,
    threshold: float,
    source: str,
    source_strategy_id: str | None,
    regime_key: str | None,
    gate_verdict: str,
) -> SimpleNamespace:
    return SimpleNamespace(
        intent_side="LONG",
        trace_ts_ms=1_700_000_000_999,
        regime="TREND_UP",
        regime_confidence=confidence,
        regime_provenance=_regime_cache_snapshot(confidence=str(confidence))[
            "regime_provenance"],
        resolved_regime_confidence_strategy_id=source_strategy_id,
        resolved_regime_confidence_symbol="BTCUSDT",
        resolved_regime_confidence_regime_key=regime_key,
        min_regime_confidence=0.45,
        resolved_min_regime_confidence=threshold,
        resolved_min_regime_confidence_source=source,
        resolved_min_regime_confidence_strategy_id=source_strategy_id,
        resolved_min_regime_confidence_regime_key=regime_key,
        resolved_max_regime_confidence=None,
        resolved_max_regime_confidence_source=None,
        resolved_max_regime_confidence_strategy_id=None,
        resolved_max_regime_confidence_regime_key=None,
        resolved_regime_confidence_band_active=True,
        regime_confidence_breach_kind="none",
        regime_confidence_gate_verdict=gate_verdict,
        threshold_applied=True,
        threshold_verdict="BLOCK" if gate_verdict == "DENY" else "PASS",
        threshold_reason=f"regime_confidence={confidence} threshold={threshold}",
        deny_reason="NRR-018" if gate_verdict == "DENY" else None,
        why_short="audit-source-test",
    )


def test_allow_path_writes_regime_decision_audit_and_threshold_metadata(
    tmp_path: Path,
    monkeypatch,
) -> None:
    audit_path = tmp_path / "regime_confidence_audit_v1.jsonl"
    monkeypatch.setenv("REGIME_CONFIDENCE_AUDIT_LOG_FILE", str(audit_path))

    dm = _configured_dm()
    expected_trend_up_max = _current_domain_max_regime_confidence_by_regime()[
        "TREND_UP"]
    dm.symbol_states["BTCUSDT"] = {
        "_delta_price_hist": deque([1.0], maxlen=20)}
    dm._per_symbol_regimes["BTCUSDT"] = _regime_cache_snapshot(
        confidence="0.25")
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
    decision_records = [
        record for record in records if record["record_type"] == "decision"]
    assert len(decision_records) == 1

    decision = decision_records[0]
    assert decision["outcome"] == "ALLOW"
    assert decision["threshold_verdict"] == "PASS"
    assert decision["threshold_applied"] is True
    assert decision["min_regime_confidence"] == 0.35
    assert decision["resolved_min_regime_confidence"] == 0.20
    assert decision["resolved_min_regime_confidence_source"] == "domain_regime_specific"
    assert decision["resolved_min_regime_confidence_strategy_id"] is None
    assert decision["resolved_min_regime_confidence_regime_key"] == "TREND_UP"
    assert decision["resolved_max_regime_confidence"] == expected_trend_up_max
    assert decision["resolved_max_regime_confidence_source"] == "domain_regime_specific"
    assert decision["regime_confidence_gate_verdict"] == "ALLOW"
    assert decision["regime_confidence_used"] == 0.25
    assert decision["raw_confidence"] == 0.25
    assert decision["stable_confidence"] == 0.25
    assert decision["bar_close_ts_ms"] == 1_700_000_000_000
    assert decision["operator_visible_mismatch"] is False
    assert decision["lifecycle_id"] is not None

    metadata = mock_order_write.call_args[0][0]["metadata"]
    assert metadata["threshold_verdict"] == "PASS"
    assert metadata["threshold_applied"] is True
    assert metadata["min_regime_confidence"] == 0.35
    assert metadata["resolved_min_regime_confidence"] == 0.20
    assert metadata["resolved_min_regime_confidence_source"] == "domain_regime_specific"
    assert metadata["resolved_min_regime_confidence_strategy_id"] is None
    assert metadata["resolved_min_regime_confidence_regime_key"] == "TREND_UP"
    assert metadata["resolved_max_regime_confidence"] == expected_trend_up_max
    assert metadata["resolved_max_regime_confidence_source"] == "domain_regime_specific"
    assert metadata["regime_confidence_gate_verdict"] == "ALLOW"


def test_deny_path_writes_regime_decision_audit_for_threshold_block(
    tmp_path: Path,
    monkeypatch,
) -> None:
    audit_path = tmp_path / "regime_confidence_audit_v1.jsonl"
    monkeypatch.setenv("REGIME_CONFIDENCE_AUDIT_LOG_FILE", str(audit_path))

    dm = _configured_dm(enable_nrr026=True)
    dm.symbol_states["BTCUSDT"] = {
        "_delta_price_hist": deque([1.0], maxlen=20)}
    dm._builder._warmup_gate = lambda **_kw: False
    expected_trend_up_max = _current_domain_max_regime_confidence_by_regime()[
        "TREND_UP"]
    dm._per_symbol_regimes["BTCUSDT"] = _regime_cache_snapshot(
        confidence="0.19")

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
    decision_records = [
        record for record in records if record["record_type"] == "decision"]
    assert len(decision_records) == 1

    decision = decision_records[0]
    assert decision["outcome"] == "DENY"
    assert decision["threshold_verdict"] == "BLOCK"
    assert decision["threshold_applied"] is True
    assert decision["min_regime_confidence"] == 0.35
    assert decision["resolved_min_regime_confidence"] == 0.20
    assert decision["resolved_min_regime_confidence_source"] == "domain_regime_specific"
    assert decision["resolved_min_regime_confidence_strategy_id"] is None
    assert decision["resolved_min_regime_confidence_regime_key"] == "TREND_UP"
    assert decision["resolved_max_regime_confidence"] == expected_trend_up_max
    assert decision["resolved_max_regime_confidence_source"] == "domain_regime_specific"
    assert decision["regime_confidence_gate_verdict"] == "DENY"
    assert decision["regime_confidence_used"] == 0.19
    assert "0.19 <= min=0.2" in decision["threshold_reason"]
    assert decision["bar_close_ts_ms"] == 1_700_000_000_000


def test_deny_path_writes_block_metadata_for_minimum_guard_when_nrr026_disabled(
    tmp_path: Path,
    monkeypatch,
) -> None:
    audit_path = tmp_path / "regime_confidence_audit_v1.jsonl"
    monkeypatch.setenv("REGIME_CONFIDENCE_AUDIT_LOG_FILE", str(audit_path))

    dm = _configured_dm(enable_nrr026=False)
    dm.symbol_states["BTCUSDT"] = {
        "_delta_price_hist": deque([1.0], maxlen=20)}
    dm._builder._warmup_gate = lambda **_kw: False
    dm._per_symbol_regimes["BTCUSDT"] = _regime_cache_snapshot(
        confidence="0.20")

    with patch(
        "apps.reference.domains.decision_making.core.facade.order_logger.write"
    ) as mock_order_write:
        dm._propose_trade_intent(
            symbol="BTCUSDT",
            side="BUY",
            qty=Decimal("0.01"),
            price=Decimal("50000"),
            why_chain=["regime_confidence_audit",
                       "nrr026_disabled_minimum_guard"],
            rid="rid-block-audit-nrr026-disabled",
            reduce_only=False,
            strategy_id="aurora",
            decision_ts_ms=1_700_000_000_999,
        )

    records = _read_jsonl(audit_path)
    decision_records = [
        record for record in records if record["record_type"] == "decision"]
    assert len(decision_records) == 1

    decision = decision_records[0]
    assert decision["outcome"] == "DENY"
    assert decision["threshold_applied"] is True
    assert decision["threshold_verdict"] == "BLOCK"
    assert decision["regime_confidence_gate_verdict"] == "DENY"
    assert decision["threshold_reason"].startswith(
        "REGIME_CONFIDENCE_AT_OR_BELOW_MINIMUM:"
    )

    logged_row = mock_order_write.call_args[0][0]
    assert "REGIME_CONFIDENCE_AT_OR_BELOW_MINIMUM" in logged_row["why"]
    assert logged_row["metadata"]["threshold_applied"] is True
    assert logged_row["metadata"]["threshold_verdict"] == "BLOCK"
    assert logged_row["metadata"]["regime_confidence_gate_verdict"] == "DENY"
    assert logged_row["metadata"]["threshold_reason"].startswith(
        "REGIME_CONFIDENCE_AT_OR_BELOW_MINIMUM:"
    )


def test_apply_safety_gates_marks_threshold_bypass_when_strategy_gate_disabled() -> None:
    cfg = _fresh_config()
    expected_trend_up_max = _current_domain_max_regime_confidence_by_regime()[
        "TREND_UP"]
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
        symbol_states={"BTCUSDT": {
            "_delta_price_hist": deque([1.0], maxlen=20)}},
        per_symbol_regimes={
            "BTCUSDT": _regime_cache_snapshot(confidence="0.30")},
        system_stress_states={},
    )

    assert result.outcome == "ALLOW"
    assert result.threshold_applied is False
    assert result.threshold_verdict == "BYPASS"
    assert result.regime_confidence_gate_verdict == "BYPASS"
    assert result.threshold_reason == "safety_gates_disabled"
    assert result.min_regime_confidence == 0.35
    assert result.resolved_min_regime_confidence == 0.20
    assert result.resolved_min_regime_confidence_source == "domain_regime_specific"
    assert result.resolved_min_regime_confidence_strategy_id is None
    assert result.resolved_min_regime_confidence_regime_key == "TREND_UP"
    assert result.resolved_max_regime_confidence == expected_trend_up_max
    assert result.resolved_max_regime_confidence_source == "domain_regime_specific"


@pytest.mark.parametrize(
    (
        "outcome",
        "gate_verdict",
        "source",
        "source_strategy_id",
        "regime_key",
        "threshold",
        "confidence",
    ),
    [
        ("DENY", "DENY", "strategy_symbol_regime_specific",
         "aurora", "TREND_UP", 0.975, 0.94),
        ("ALLOW", "ALLOW", "strategy_regime_specific",
         "aurora", "TREND_UP", 0.65, 0.66),
        ("DENY", "DENY", "strategy_regime_specific",
         "aurora", "TREND_UP", 0.65, 0.61),
        ("DENY", "DENY", "domain_regime_specific", None, "TREND_UP", 0.60, 0.59),
        ("ALLOW", "ALLOW", "scalar_legacy", None, None, 0.45, 0.87),
    ],
)
def test_regime_decision_audit_records_threshold_resolution_source_metadata(
    tmp_path: Path,
    outcome: str,
    gate_verdict: str,
    source: str,
    source_strategy_id: str | None,
    regime_key: str | None,
    threshold: float,
    confidence: float,
) -> None:
    audit_path = tmp_path / "regime_confidence_audit_v1.jsonl"

    emit_regime_decision_audit(
        logger=None,
        symbol="BTCUSDT",
        rid=f"rid-{source}-{outcome}",
        lifecycle_id="lifecycle-audit-source",
        strategy_id="aurora",
        sg=_audit_sg(
            confidence=confidence,
            threshold=threshold,
            source=source,
            source_strategy_id=source_strategy_id,
            regime_key=regime_key,
            gate_verdict=gate_verdict,
        ),
        outcome=outcome,
        log_file=audit_path,
    )

    [record] = _read_jsonl(audit_path)
    assert record["outcome"] == outcome
    assert record["strategy_id"] == "aurora"
    assert record["resolved_min_regime_confidence"] == threshold
    assert record["resolved_min_regime_confidence_source"] == source
    assert record["resolved_min_regime_confidence_strategy_id"] == source_strategy_id
    assert record["resolved_min_regime_confidence_regime_key"] == regime_key
    assert record["regime_confidence_gate_verdict"] == gate_verdict


def test_apply_safety_gates_uses_regime_specific_confidence_threshold() -> None:
    cfg = _fresh_config()
    cfg.strategies.aurora.safety_gates.enabled = True
    cfg.domains.decision_making.directional_sanity.enabled = True
    cfg.domains.decision_making.directional_sanity.min_abs_delta_price = 0.0
    cfg.domains.decision_making.directional_sanity.min_confidence = 0.0
    _enable_regime_confidence_floor_gate(cfg)
    cfg.domains.decision_making.directional_sanity.min_regime_confidence = 0.45
    cfg.domains.decision_making.directional_sanity.min_regime_confidence_by_regime = {
        "DEFAULT": 0.45,
        "TREND_UP": 0.52,
    }
    cfg.domains.decision_making.directional_sanity.max_regime_confidence_by_regime = None
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
        symbol_states={"BTCUSDT": {
            "_delta_price_hist": deque([1.0], maxlen=20)}},
        per_symbol_regimes={
            "BTCUSDT": _regime_cache_snapshot(confidence="0.45")},
        system_stress_states={},
    )

    assert result.outcome == "DENY"
    assert result.threshold_verdict == "BLOCK"
    assert result.min_regime_confidence == 0.45
    assert result.resolved_min_regime_confidence == 0.52
    assert result.resolved_min_regime_confidence_source == "domain_regime_specific"
    assert result.resolved_min_regime_confidence_strategy_id is None
    assert result.resolved_min_regime_confidence_regime_key == "TREND_UP"
    assert result.regime_confidence_gate_verdict == "DENY"
    assert "0.45 <= min=0.52" in result.threshold_reason


def test_apply_safety_gates_strategy_regime_confidence_override_denies_below_threshold() -> None:
    cfg = _fresh_config()
    cfg.strategies.aurora.safety_gates.enabled = True
    cfg.strategies.aurora.safety_gates.regime_confidence = SimpleNamespace(
        min_by_regime={"DEFAULT": 0.45, "TREND_UP": 0.65}
    )
    cfg.domains.decision_making.directional_sanity.enabled = True
    cfg.domains.decision_making.directional_sanity.min_abs_delta_price = 0.0
    cfg.domains.decision_making.directional_sanity.min_confidence = 0.0
    _enable_regime_confidence_floor_gate(cfg)
    cfg.domains.decision_making.directional_sanity.min_regime_confidence = 0.45
    cfg.domains.decision_making.directional_sanity.min_regime_confidence_by_regime = {
        "DEFAULT": 0.45,
        "TREND_UP": 0.52,
    }
    cfg.domains.decision_making.directional_sanity.max_regime_confidence_by_regime = None
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
        symbol_states={"BTCUSDT": {
            "_delta_price_hist": deque([1.0], maxlen=20)}},
        per_symbol_regimes={
            "BTCUSDT": _regime_cache_snapshot(confidence="0.61")},
        system_stress_states={},
    )

    assert result.outcome == "DENY"
    assert result.resolved_min_regime_confidence == 0.65
    assert result.resolved_min_regime_confidence_source == "strategy_regime_specific"
    assert result.resolved_min_regime_confidence_strategy_id == "aurora"
    assert result.resolved_min_regime_confidence_regime_key == "TREND_UP"
    assert result.regime_confidence_gate_verdict == "DENY"


def test_apply_safety_gates_strategy_regime_confidence_override_allows_above_threshold() -> None:
    cfg = _fresh_config()
    cfg.strategies.aurora.safety_gates.enabled = True
    cfg.strategies.aurora.safety_gates.regime_confidence = SimpleNamespace(
        min_by_regime={"DEFAULT": 0.45, "TREND_UP": 0.65}
    )
    cfg.domains.decision_making.directional_sanity.enabled = True
    cfg.domains.decision_making.directional_sanity.min_abs_delta_price = 0.0
    cfg.domains.decision_making.directional_sanity.min_confidence = 0.0
    _enable_regime_confidence_floor_gate(cfg)
    cfg.domains.decision_making.directional_sanity.min_regime_confidence = 0.45
    cfg.domains.decision_making.directional_sanity.min_regime_confidence_by_regime = {
        "DEFAULT": 0.45,
        "TREND_UP": 0.52,
    }
    cfg.domains.decision_making.directional_sanity.max_regime_confidence_by_regime = None
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
        symbol_states={"BTCUSDT": {
            "_delta_price_hist": deque([1.0], maxlen=20)}},
        per_symbol_regimes={
            "BTCUSDT": _regime_cache_snapshot(confidence="0.66")},
        system_stress_states={},
    )

    assert result.outcome == "ALLOW"
    assert result.resolved_min_regime_confidence == 0.65
    assert result.resolved_min_regime_confidence_source == "strategy_regime_specific"
    assert result.resolved_min_regime_confidence_strategy_id == "aurora"
    assert result.regime_confidence_gate_verdict == "ALLOW"


@pytest.mark.parametrize("strategy_id", [
    "aurora",
    "md_amr",
    "mean_reversion",
    "llm_microstructure",
])
def test_apply_safety_gates_each_strategy_can_use_symbol_specific_thresholds(
    strategy_id: str,
) -> None:
    cfg = _fresh_config()
    strategy_cfg = getattr(cfg.strategies, strategy_id)
    strategy_cfg.safety_gates.enabled = True
    strategy_cfg.safety_gates.regime_confidence = SimpleNamespace(
        min_by_regime={"DEFAULT": 0.45, "TREND_UP": 0.65},
        min_by_symbol={
            "XRPUSDT": {"DEFAULT": 0.675, "TREND_UP": 0.75},
        },
    )
    cfg.domains.decision_making.directional_sanity.enabled = True
    cfg.domains.decision_making.directional_sanity.min_abs_delta_price = 0.0
    cfg.domains.decision_making.directional_sanity.min_confidence = 0.0
    _enable_regime_confidence_floor_gate(cfg)
    cfg.domains.decision_making.directional_sanity.min_regime_confidence = 0.45
    cfg.domains.decision_making.directional_sanity.min_regime_confidence_by_regime = {
        "DEFAULT": 0.45,
        "TREND_UP": 0.52,
    }
    cfg.domains.decision_making.directional_sanity.max_regime_confidence_by_regime = None
    cfg.domains.decision_making.directional_sanity.consecutive_bars = 1
    cfg.domains.decision_making.price_motion_sanity.enabled = False

    result = apply_safety_gates(
        symbol="XRPUSDT",
        side="BUY",
        reduce_only=False,
        strategy_id=strategy_id,
        decision_ts_ms=1_700_000_000_999,
        why_chain=["regime_confidence_audit"],
        config=cfg,
        clock=MagicMock(now_ms=MagicMock(return_value=1_700_000_000_999)),
        symbol_states={"XRPUSDT": {
            "_delta_price_hist": deque([1.0], maxlen=20)}},
        per_symbol_regimes={
            "XRPUSDT": _regime_cache_snapshot(confidence="0.74")},
        system_stress_states={},
    )

    assert result.outcome == "DENY"
    assert result.resolved_min_regime_confidence == 0.75
    assert result.resolved_min_regime_confidence_source == "strategy_symbol_regime_specific"
    assert result.resolved_min_regime_confidence_strategy_id == strategy_id
    assert result.resolved_min_regime_confidence_regime_key == "TREND_UP"
    assert result.regime_confidence_gate_verdict == "DENY"


def test_apply_safety_gates_strategy_symbol_thresholds_are_isolated_per_coin() -> None:
    cfg = _fresh_config()
    cfg.strategies.aurora.safety_gates.enabled = True
    cfg.strategies.aurora.safety_gates.regime_confidence = SimpleNamespace(
        min_by_regime={"DEFAULT": 0.45, "TREND_UP": 0.65},
        min_by_symbol={
            "XRPUSDT": {"DEFAULT": 0.675, "TREND_UP": 0.975},
            "BTCUSDT": {"DEFAULT": 0.55, "TREND_UP": 0.70},
        },
    )
    cfg.domains.decision_making.directional_sanity.enabled = True
    cfg.domains.decision_making.directional_sanity.min_abs_delta_price = 0.0
    cfg.domains.decision_making.directional_sanity.min_confidence = 0.0
    _enable_regime_confidence_floor_gate(cfg)
    cfg.domains.decision_making.directional_sanity.min_regime_confidence = 0.45
    cfg.domains.decision_making.directional_sanity.min_regime_confidence_by_regime = {
        "DEFAULT": 0.45,
        "TREND_UP": 0.52,
    }
    cfg.domains.decision_making.directional_sanity.max_regime_confidence_by_regime = None
    cfg.domains.decision_making.directional_sanity.consecutive_bars = 1
    cfg.domains.decision_making.price_motion_sanity.enabled = False

    xrp_result = apply_safety_gates(
        symbol="XRPUSDT",
        side="BUY",
        reduce_only=False,
        strategy_id="aurora",
        decision_ts_ms=1_700_000_000_999,
        why_chain=["regime_confidence_audit"],
        config=cfg,
        clock=MagicMock(now_ms=MagicMock(return_value=1_700_000_000_999)),
        symbol_states={"XRPUSDT": {
            "_delta_price_hist": deque([1.0], maxlen=20)}},
        per_symbol_regimes={
            "XRPUSDT": _regime_cache_snapshot(confidence="0.80")},
        system_stress_states={},
    )
    btc_result = apply_safety_gates(
        symbol="BTCUSDT",
        side="BUY",
        reduce_only=False,
        strategy_id="aurora",
        decision_ts_ms=1_700_000_000_999,
        why_chain=["regime_confidence_audit"],
        config=cfg,
        clock=MagicMock(now_ms=MagicMock(return_value=1_700_000_000_999)),
        symbol_states={"BTCUSDT": {
            "_delta_price_hist": deque([1.0], maxlen=20)}},
        per_symbol_regimes={
            "BTCUSDT": _regime_cache_snapshot(confidence="0.69")},
        system_stress_states={},
    )
    eth_result = apply_safety_gates(
        symbol="ETHUSDT",
        side="BUY",
        reduce_only=False,
        strategy_id="aurora",
        decision_ts_ms=1_700_000_000_999,
        why_chain=["regime_confidence_audit"],
        config=cfg,
        clock=MagicMock(now_ms=MagicMock(return_value=1_700_000_000_999)),
        symbol_states={"ETHUSDT": {
            "_delta_price_hist": deque([1.0], maxlen=20)}},
        per_symbol_regimes={
            "ETHUSDT": _regime_cache_snapshot(confidence="0.64")},
        system_stress_states={},
    )

    assert xrp_result.resolved_min_regime_confidence == 0.975
    assert xrp_result.resolved_min_regime_confidence_source == "strategy_symbol_regime_specific"
    assert xrp_result.outcome == "DENY"

    assert btc_result.resolved_min_regime_confidence == 0.70
    assert btc_result.resolved_min_regime_confidence_source == "strategy_symbol_regime_specific"
    assert btc_result.outcome == "DENY"

    assert eth_result.resolved_min_regime_confidence == 0.65
    assert eth_result.resolved_min_regime_confidence_source == "strategy_regime_specific"
    assert eth_result.outcome == "DENY"


def test_apply_safety_gates_domain_threshold_applies_without_strategy_override() -> None:
    cfg = _fresh_config()
    cfg.strategies.md_amr.safety_gates.enabled = True
    cfg.strategies.md_amr.safety_gates.regime_confidence = None
    cfg.domains.decision_making.directional_sanity.enabled = True
    cfg.domains.decision_making.directional_sanity.min_abs_delta_price = 0.0
    cfg.domains.decision_making.directional_sanity.min_confidence = 0.0
    _enable_regime_confidence_floor_gate(cfg)
    cfg.domains.decision_making.directional_sanity.min_regime_confidence = 0.45
    cfg.domains.decision_making.directional_sanity.min_regime_confidence_by_regime = {
        "DEFAULT": 0.45,
        "TREND_UP": 0.60,
    }
    cfg.domains.decision_making.directional_sanity.max_regime_confidence_by_regime = None
    cfg.domains.decision_making.directional_sanity.consecutive_bars = 1
    cfg.domains.decision_making.price_motion_sanity.enabled = False

    result = apply_safety_gates(
        symbol="BTCUSDT",
        side="BUY",
        reduce_only=False,
        strategy_id="md_amr",
        decision_ts_ms=1_700_000_000_999,
        why_chain=["regime_confidence_audit"],
        config=cfg,
        clock=MagicMock(now_ms=MagicMock(return_value=1_700_000_000_999)),
        symbol_states={"BTCUSDT": {
            "_delta_price_hist": deque([1.0], maxlen=20)}},
        per_symbol_regimes={
            "BTCUSDT": _regime_cache_snapshot(confidence="0.59")},
        system_stress_states={},
    )

    assert result.outcome == "DENY"
    assert result.resolved_min_regime_confidence == 0.60
    assert result.resolved_min_regime_confidence_source == "domain_regime_specific"
    assert result.resolved_min_regime_confidence_strategy_id is None
    assert result.regime_confidence_gate_verdict == "DENY"


@pytest.mark.parametrize(
    ("regime", "confidence", "expected_outcome", "expected_reason",
     "expected_breach", "expected_min", "expected_max"),
    _current_domain_band_activation_cases(),
)
def test_apply_safety_gates_regime_confidence_band_activation(
    regime: str,
    confidence: float,
    expected_outcome: str,
    expected_reason: str | None,
    expected_breach: str,
    expected_min: float,
    expected_max: float | None,
) -> None:
    cfg = _fresh_config()
    cfg.strategies.aurora.safety_gates.enabled = True
    cfg.strategies.aurora.safety_gates.regime_confidence = None
    cfg.domains.decision_making.directional_sanity.enabled = True
    cfg.domains.decision_making.directional_sanity.min_abs_delta_price = 0.0
    cfg.domains.decision_making.directional_sanity.min_confidence = 0.0
    _enable_regime_confidence_floor_gate(cfg)
    cfg.domains.decision_making.directional_sanity.min_regime_confidence = 0.35
    cfg.domains.decision_making.directional_sanity.min_regime_confidence_by_regime = {
        "DEFAULT": 0.35,
        "TREND_UP": 0.20,
        "TREND_DOWN": 0.20,
    }
    cfg.domains.decision_making.directional_sanity.max_regime_confidence_by_regime = _current_domain_max_regime_confidence_by_regime()
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
        symbol_states={"BTCUSDT": {
            "_delta_price_hist": deque([1.0], maxlen=20)}},
        per_symbol_regimes={
            "BTCUSDT": _regime_cache_snapshot(confidence=f"{confidence}", regime=regime)
        },
        system_stress_states={},
    )

    assert result.outcome == expected_outcome
    assert result.regime_confidence_breach_kind == expected_breach
    assert result.deny_reason == expected_reason
    assert result.threshold_verdict == (
        "BLOCK" if expected_outcome == "DENY" else "PASS")
    assert result.resolved_min_regime_confidence == expected_min
    assert result.resolved_max_regime_confidence == expected_max
    assert result.resolved_regime_confidence_band_active is True


def test_apply_safety_gates_rejects_above_max_regime_confidence() -> None:
    cfg = _fresh_config()
    cfg.strategies.aurora.safety_gates.enabled = True
    cfg.strategies.aurora.safety_gates.regime_confidence = SimpleNamespace(
        min_by_regime={"DEFAULT": 0.45, "TREND_UP": 0.52},
        max_by_regime={"TREND_UP": 0.70},
    )
    cfg.domains.decision_making.directional_sanity.enabled = True
    cfg.domains.decision_making.directional_sanity.min_abs_delta_price = 0.0
    cfg.domains.decision_making.directional_sanity.min_confidence = 0.0
    _enable_regime_confidence_floor_gate(cfg)
    cfg.domains.decision_making.directional_sanity.min_regime_confidence = 0.45
    cfg.domains.decision_making.directional_sanity.min_regime_confidence_by_regime = {
        "DEFAULT": 0.45,
        "TREND_UP": 0.52,
    }
    cfg.domains.decision_making.directional_sanity.max_regime_confidence_by_regime = {
        "TREND_UP": 0.70,
    }
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
        symbol_states={"BTCUSDT": {
            "_delta_price_hist": deque([1.0], maxlen=20)}},
        per_symbol_regimes={
            "BTCUSDT": _regime_cache_snapshot(confidence="0.74")},
        system_stress_states={},
    )

    assert result.outcome == "DENY"
    assert result.deny_reason == "NRR-063"
    assert result.regime_confidence_breach_kind == "above_max"
    assert result.threshold_verdict == "BLOCK"
    assert result.resolved_max_regime_confidence == 0.70
    assert result.resolved_max_regime_confidence_source == "strategy_regime_specific"
    assert result.resolved_regime_confidence_band_active is True


def test_apply_safety_gates_strategy_symbol_regime_side_min_override_is_exact_side_only() -> None:
    cfg = _fresh_config()
    cfg.strategies.aurora.safety_gates.enabled = True
    cfg.strategies.aurora.safety_gates.regime_confidence = domain_dm.RegimeConfidenceGateConfig(
        min_by_regime={"DEFAULT": 0.45, "TREND_DOWN": 0.55},
        min_by_symbol={"ETHUSDT": {"DEFAULT": 0.60, "TREND_DOWN": 0.70}},
        min_by_symbol_regime_side={
            "ETHUSDT": {
                "TREND_DOWN": {
                    "SELL": 0.81,
                }
            }
        },
    )
    cfg.domains.decision_making.directional_sanity.enabled = True
    cfg.domains.decision_making.directional_sanity.min_abs_delta_price = 0.0
    cfg.domains.decision_making.directional_sanity.min_confidence = 0.0
    _enable_regime_confidence_floor_gate(cfg)
    cfg.domains.decision_making.directional_sanity.min_regime_confidence = 0.45
    cfg.domains.decision_making.directional_sanity.min_regime_confidence_by_regime = {
        "DEFAULT": 0.45,
        "TREND_DOWN": 0.52,
    }
    cfg.domains.decision_making.directional_sanity.max_regime_confidence_by_regime = None
    cfg.domains.decision_making.directional_sanity.consecutive_bars = 1
    cfg.domains.decision_making.price_motion_sanity.enabled = False

    sell_result = apply_safety_gates(
        symbol="ETHUSDT",
        side="SELL",
        reduce_only=False,
        strategy_id="aurora",
        decision_ts_ms=1_700_000_000_999,
        why_chain=["regime_confidence_audit"],
        config=cfg,
        clock=MagicMock(now_ms=MagicMock(return_value=1_700_000_000_999)),
        symbol_states={"ETHUSDT": {"_delta_price_hist": deque([1.0], maxlen=20)}},
        per_symbol_regimes={
            "ETHUSDT": _regime_cache_snapshot(confidence="0.79", regime="TREND_DOWN")
        },
        system_stress_states={},
    )
    buy_result = apply_safety_gates(
        symbol="ETHUSDT",
        side="BUY",
        reduce_only=False,
        strategy_id="aurora",
        decision_ts_ms=1_700_000_000_999,
        why_chain=["regime_confidence_audit"],
        config=cfg,
        clock=MagicMock(now_ms=MagicMock(return_value=1_700_000_000_999)),
        symbol_states={"ETHUSDT": {"_delta_price_hist": deque([1.0], maxlen=20)}},
        per_symbol_regimes={
            "ETHUSDT": _regime_cache_snapshot(confidence="0.79", regime="TREND_DOWN")
        },
        system_stress_states={},
    )

    assert sell_result.outcome == "DENY"
    assert sell_result.resolved_min_regime_confidence == 0.81
    assert sell_result.resolved_min_regime_confidence_source == "strategy_symbol_regime_side_specific"
    assert sell_result.resolved_min_regime_confidence_strategy_id == "aurora"
    assert sell_result.regime_confidence_breach_kind == "below_min"

    assert buy_result.outcome == "ALLOW"
    assert buy_result.resolved_min_regime_confidence == 0.70
    assert buy_result.resolved_min_regime_confidence_source == "strategy_symbol_regime_specific"
    assert buy_result.regime_confidence_gate_verdict == "ALLOW"


def test_apply_safety_gates_strategy_symbol_regime_side_max_disable_skips_above_max_only_for_exact_side() -> None:
    cfg = _fresh_config()
    cfg.strategies.aurora.safety_gates.enabled = True
    cfg.strategies.aurora.safety_gates.regime_confidence = domain_dm.RegimeConfidenceGateConfig(
        min_by_regime={"DEFAULT": 0.45, "TREND_DOWN": 0.52},
        max_by_symbol_regime_side={
            "ETHUSDT": {
                "TREND_DOWN": {
                    "SELL": {
                        "enabled": False,
                    }
                }
            }
        },
    )
    cfg.domains.decision_making.directional_sanity.enabled = True
    cfg.domains.decision_making.directional_sanity.min_abs_delta_price = 0.0
    cfg.domains.decision_making.directional_sanity.min_confidence = 0.0
    _enable_regime_confidence_floor_gate(cfg)
    cfg.domains.decision_making.directional_sanity.min_regime_confidence = 0.45
    cfg.domains.decision_making.directional_sanity.min_regime_confidence_by_regime = {
        "DEFAULT": 0.45,
        "TREND_DOWN": 0.52,
    }
    cfg.domains.decision_making.directional_sanity.max_regime_confidence_by_regime = {
        "TREND_DOWN": 0.70,
    }
    cfg.domains.decision_making.directional_sanity.consecutive_bars = 1
    cfg.domains.decision_making.price_motion_sanity.enabled = False

    sell_result = apply_safety_gates(
        symbol="ETHUSDT",
        side="SELL",
        reduce_only=False,
        strategy_id="aurora",
        decision_ts_ms=1_700_000_000_999,
        why_chain=["regime_confidence_audit"],
        config=cfg,
        clock=MagicMock(now_ms=MagicMock(return_value=1_700_000_000_999)),
        symbol_states={"ETHUSDT": {"_delta_price_hist": deque([1.0], maxlen=20)}},
        per_symbol_regimes={
            "ETHUSDT": _regime_cache_snapshot(confidence="0.80", regime="TREND_DOWN")
        },
        system_stress_states={},
    )
    buy_result = apply_safety_gates(
        symbol="ETHUSDT",
        side="BUY",
        reduce_only=False,
        strategy_id="aurora",
        decision_ts_ms=1_700_000_000_999,
        why_chain=["regime_confidence_audit"],
        config=cfg,
        clock=MagicMock(now_ms=MagicMock(return_value=1_700_000_000_999)),
        symbol_states={"ETHUSDT": {"_delta_price_hist": deque([1.0], maxlen=20)}},
        per_symbol_regimes={
            "ETHUSDT": _regime_cache_snapshot(confidence="0.80", regime="TREND_DOWN")
        },
        system_stress_states={},
    )
    bnb_result = apply_safety_gates(
        symbol="BNBUSDT",
        side="SELL",
        reduce_only=False,
        strategy_id="aurora",
        decision_ts_ms=1_700_000_000_999,
        why_chain=["regime_confidence_audit"],
        config=cfg,
        clock=MagicMock(now_ms=MagicMock(return_value=1_700_000_000_999)),
        symbol_states={"BNBUSDT": {"_delta_price_hist": deque([1.0], maxlen=20)}},
        per_symbol_regimes={
            "BNBUSDT": _regime_cache_snapshot(confidence="0.80", regime="TREND_DOWN")
        },
        system_stress_states={},
    )

    assert sell_result.outcome == "ALLOW"
    assert sell_result.resolved_max_regime_confidence is None
    assert sell_result.resolved_max_regime_confidence_source == "strategy_symbol_regime_side_specific_disabled"
    assert sell_result.nrr063_enabled is False
    assert sell_result.regime_confidence_gate_verdict == "ALLOW"

    assert buy_result.outcome == "DENY"
    assert buy_result.deny_reason == "NRR-063"
    assert buy_result.resolved_max_regime_confidence == 0.70
    assert buy_result.resolved_max_regime_confidence_source == "domain_regime_specific"
    assert buy_result.regime_confidence_breach_kind == "above_max"

    assert bnb_result.outcome == "DENY"
    assert bnb_result.deny_reason == "NRR-063"
    assert bnb_result.resolved_max_regime_confidence == 0.70
    assert bnb_result.resolved_max_regime_confidence_source == "domain_regime_specific"


def test_apply_safety_gates_strategy_regime_side_max_raise_is_exact_side_only() -> None:
    cfg = _fresh_config()
    cfg.strategies.aurora.safety_gates.enabled = True
    cfg.strategies.aurora.safety_gates.regime_confidence = domain_dm.RegimeConfidenceGateConfig(
        min_by_regime={"DEFAULT": 0.45, "TREND_DOWN": 0.52},
        max_by_regime={"TREND_DOWN": 0.70},
        max_by_regime_side={
            "TREND_DOWN": {
                "SELL": {
                    "enabled": True,
                    "threshold": 0.95,
                }
            }
        },
    )
    cfg.domains.decision_making.directional_sanity.enabled = True
    cfg.domains.decision_making.directional_sanity.min_abs_delta_price = 0.0
    cfg.domains.decision_making.directional_sanity.min_confidence = 0.0
    _enable_regime_confidence_floor_gate(cfg)
    cfg.domains.decision_making.directional_sanity.min_regime_confidence = 0.45
    cfg.domains.decision_making.directional_sanity.min_regime_confidence_by_regime = {
        "DEFAULT": 0.45,
        "TREND_DOWN": 0.52,
    }
    cfg.domains.decision_making.directional_sanity.max_regime_confidence_by_regime = {
        "TREND_DOWN": 0.70,
    }
    cfg.domains.decision_making.directional_sanity.consecutive_bars = 1
    cfg.domains.decision_making.price_motion_sanity.enabled = False

    sell_result = apply_safety_gates(
        symbol="ETHUSDT",
        side="SELL",
        reduce_only=False,
        strategy_id="aurora",
        decision_ts_ms=1_700_000_000_999,
        why_chain=["regime_confidence_audit"],
        config=cfg,
        clock=MagicMock(now_ms=MagicMock(return_value=1_700_000_000_999)),
        symbol_states={"ETHUSDT": {"_delta_price_hist": deque([1.0], maxlen=20)}},
        per_symbol_regimes={
            "ETHUSDT": _regime_cache_snapshot(confidence="0.80", regime="TREND_DOWN")
        },
        system_stress_states={},
    )
    buy_result = apply_safety_gates(
        symbol="ETHUSDT",
        side="BUY",
        reduce_only=False,
        strategy_id="aurora",
        decision_ts_ms=1_700_000_000_999,
        why_chain=["regime_confidence_audit"],
        config=cfg,
        clock=MagicMock(now_ms=MagicMock(return_value=1_700_000_000_999)),
        symbol_states={"ETHUSDT": {"_delta_price_hist": deque([1.0], maxlen=20)}},
        per_symbol_regimes={
            "ETHUSDT": _regime_cache_snapshot(confidence="0.80", regime="TREND_DOWN")
        },
        system_stress_states={},
    )

    assert sell_result.outcome == "ALLOW"
    assert sell_result.resolved_max_regime_confidence == 0.95
    assert sell_result.resolved_max_regime_confidence_source == "strategy_regime_side_specific"
    assert sell_result.regime_confidence_gate_verdict == "ALLOW"

    assert buy_result.outcome == "DENY"
    assert buy_result.deny_reason == "NRR-063"
    assert buy_result.resolved_max_regime_confidence == 0.70
    assert buy_result.resolved_max_regime_confidence_source == "strategy_regime_specific"


def test_current_aurora_yaml_activates_only_eth_trend_down_sell_nrr063_exception() -> None:
    cfg = _fresh_config()
    assert cfg.domains.decision_making.directional_sanity.nrr026_enabled is True
    assert cfg.strategies.aurora.assets["XRPUSDT"].enabled is True
    assert cfg.strategies.aurora.safety_gates.regime_confidence is not None
    assert "DOGEUSDT" not in cfg.strategies.aurora.safety_gates.regime_confidence.max_by_symbol_regime_side

    common_kwargs = dict(
        reduce_only=False,
        strategy_id="aurora",
        decision_ts_ms=1_700_000_000_999,
        why_chain=["regime_confidence_audit", "variant_b_testnet_activation"],
        config=cfg,
        clock=MagicMock(now_ms=MagicMock(return_value=1_700_000_000_999)),
        system_stress_states={},
    )

    eth_sell = apply_safety_gates(
        symbol="ETHUSDT",
        side="SELL",
        symbol_states={"ETHUSDT": {"_delta_price_hist": deque([1.0], maxlen=20)}},
        per_symbol_regimes={
            "ETHUSDT": _regime_cache_snapshot(confidence="0.41", regime="TREND_DOWN")
        },
        **common_kwargs,
    )
    eth_buy = apply_safety_gates(
        symbol="ETHUSDT",
        side="BUY",
        symbol_states={"ETHUSDT": {"_delta_price_hist": deque([1.0], maxlen=20)}},
        per_symbol_regimes={
            "ETHUSDT": _regime_cache_snapshot(confidence="0.41", regime="TREND_DOWN")
        },
        **common_kwargs,
    )
    bnb_sell = apply_safety_gates(
        symbol="BNBUSDT",
        side="SELL",
        symbol_states={"BNBUSDT": {"_delta_price_hist": deque([1.0], maxlen=20)}},
        per_symbol_regimes={
            "BNBUSDT": _regime_cache_snapshot(confidence="0.41", regime="TREND_DOWN")
        },
        **common_kwargs,
    )
    btc_sell = apply_safety_gates(
        symbol="BTCUSDT",
        side="SELL",
        symbol_states={"BTCUSDT": {"_delta_price_hist": deque([1.0], maxlen=20)}},
        per_symbol_regimes={
            "BTCUSDT": _regime_cache_snapshot(confidence="0.41", regime="TREND_DOWN")
        },
        **common_kwargs,
    )

    assert eth_sell.outcome == "DENY"
    assert eth_sell.deny_reason == "NRR-028"
    assert eth_sell.resolved_min_regime_confidence == 0.20
    assert eth_sell.resolved_min_regime_confidence_source == "domain_regime_specific"
    assert eth_sell.resolved_max_regime_confidence is None
    assert eth_sell.resolved_max_regime_confidence_source == "strategy_symbol_regime_side_specific_disabled"
    assert eth_sell.nrr063_enabled is False
    assert eth_sell.regime_confidence_gate_verdict == "ALLOW"
    assert eth_sell.regime_confidence_breach_kind == "none"

    assert eth_buy.outcome == "DENY"
    assert eth_buy.deny_reason == "NRR-063"
    assert eth_buy.resolved_min_regime_confidence == 0.20
    assert eth_buy.resolved_max_regime_confidence == 0.40
    assert eth_buy.resolved_max_regime_confidence_source == "domain_regime_specific"
    assert eth_buy.regime_confidence_breach_kind == "above_max"

    assert bnb_sell.outcome == "DENY"
    assert bnb_sell.deny_reason == "NRR-063"
    assert bnb_sell.resolved_max_regime_confidence == 0.40
    assert bnb_sell.resolved_max_regime_confidence_source == "domain_regime_specific"

    assert btc_sell.outcome == "DENY"
    assert btc_sell.deny_reason == "NRR-063"
    assert btc_sell.resolved_max_regime_confidence == 0.40
    assert btc_sell.resolved_max_regime_confidence_source == "domain_regime_specific"


def test_apply_safety_gates_allows_confidence_inside_band() -> None:
    cfg = _fresh_config()
    cfg.strategies.aurora.safety_gates.enabled = True
    cfg.strategies.aurora.safety_gates.regime_confidence = SimpleNamespace(
        min_by_regime={"DEFAULT": 0.45, "TREND_UP": 0.52},
        max_by_regime={"TREND_UP": 0.70},
    )
    cfg.domains.decision_making.directional_sanity.enabled = True
    cfg.domains.decision_making.directional_sanity.min_abs_delta_price = 0.0
    cfg.domains.decision_making.directional_sanity.min_confidence = 0.0
    _enable_regime_confidence_floor_gate(cfg)
    cfg.domains.decision_making.directional_sanity.min_regime_confidence = 0.45
    cfg.domains.decision_making.directional_sanity.min_regime_confidence_by_regime = {
        "DEFAULT": 0.45,
        "TREND_UP": 0.52,
    }
    cfg.domains.decision_making.directional_sanity.max_regime_confidence_by_regime = {
        "TREND_UP": 0.70,
    }
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
        symbol_states={"BTCUSDT": {
            "_delta_price_hist": deque([1.0], maxlen=20)}},
        per_symbol_regimes={
            "BTCUSDT": _regime_cache_snapshot(confidence="0.64")},
        system_stress_states={},
    )

    assert result.outcome == "ALLOW"
    assert result.regime_confidence_breach_kind == "none"
    assert result.threshold_verdict == "PASS"
    assert result.resolved_max_regime_confidence == 0.70
    assert result.regime_confidence_gate_verdict == "ALLOW"


def test_apply_safety_gates_missing_confidence_with_active_band_denies() -> None:
    cfg = _fresh_config()
    cfg.strategies.aurora.safety_gates.enabled = True
    cfg.strategies.aurora.safety_gates.regime_confidence = SimpleNamespace(
        min_by_regime={"DEFAULT": 0.45, "TREND_UP": 0.52},
        max_by_regime={"TREND_UP": 0.70},
    )
    cfg.domains.decision_making.directional_sanity.enabled = True
    cfg.domains.decision_making.directional_sanity.min_abs_delta_price = 0.0
    cfg.domains.decision_making.directional_sanity.min_confidence = 0.0
    _enable_regime_confidence_floor_gate(cfg)
    cfg.domains.decision_making.directional_sanity.min_regime_confidence = 0.45
    cfg.domains.decision_making.directional_sanity.min_regime_confidence_by_regime = {
        "DEFAULT": 0.45,
        "TREND_UP": 0.52,
    }
    cfg.domains.decision_making.directional_sanity.max_regime_confidence_by_regime = {
        "TREND_UP": 0.70,
    }
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
        symbol_states={"BTCUSDT": {
            "_delta_price_hist": deque([1.0], maxlen=20)}},
        per_symbol_regimes={"BTCUSDT": {
            "regime": "TREND_UP", "confidence": None}},
        system_stress_states={},
    )

    assert result.outcome == "DENY"
    assert result.regime_confidence_breach_kind == "missing"
    assert result.deny_reason == "NRR-026"
    assert result.threshold_verdict == "BLOCK"
