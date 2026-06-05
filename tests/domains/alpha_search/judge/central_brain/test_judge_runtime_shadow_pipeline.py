from __future__ import annotations

from copy import deepcopy

import pytest

from apps.reference.config.domains.decision_making import JudgeBridgeConfig
from apps.reference.domains.alpha_search.judge.central_brain.shadow_pipeline import (
    build_runtime_shadow_artifacts,
)
from tests.config.test_judge_bridge_config_contract import valid_payload
from tests.domains.alpha_search.judge.central_brain.test_judge_policy_verdict_contract import (
    valid_config,
)


def bridge_config() -> JudgeBridgeConfig:
    payload = valid_payload()
    payload["enabled"] = True
    payload["shadow_capture"]["enabled"] = True
    return JudgeBridgeConfig.model_validate(payload)


def aurora_payload(**overrides):
    payload = {
        "strategy_id": "aurora",
        "symbol": "BTCUSDT",
        "ts_ms": 1000,
        "side": "BUY",
        "strategy_confidence": 0.82,
        "features": {"ts_ms": 990, "obi": 0.2, "tfi": 0.1},
        "scoring": {"decision_score": 0.82, "pillar_sum": 0.4},
        "rid": "rid-1",
        "decision_id": "decision-1",
    }
    payload.update(overrides)
    return payload


def regime_payload():
    return {
        "symbol": "BTCUSDT",
        "ts_ms": 1000,
        "regime": "LOW_VOLATILITY",
        "confidence": 0.8,
        "basis_tf_sec": 60,
        "rid": "rid-regime",
    }


def candidate(**overrides):
    payload = {
        "decision_id": "decision-1",
        "symbol": "BTCUSDT",
        "side": "BUY",
        "rid": "rid-1",
        "cycle_key": "cycle-1",
        "candidate_exists": True,
        "hard_gate_results": {
            "panic_killswitch": True,
            "exchange_filter_fail": True,
            "exposure_limit": True,
            "stale_features": True,
            "stale_regime": True,
            "order_guardian_block": True,
        },
        "hard_gate_blocking_reasons": [],
    }
    payload.update(overrides)
    return payload


def build(**overrides):
    return build_runtime_shadow_artifacts(
        strategy_payload=overrides.get("strategy_payload", aurora_payload()),
        regime_payload=overrides.get("regime_payload", regime_payload()),
        meta_config=valid_config(),
        bridge_config=bridge_config(),
        runtime_mode="testnet",
        candidate_context=overrides.get("candidate_context", candidate()),
        market_context=overrides.get(
            "market_context",
            {
                "symbol": "BTCUSDT",
                "ts_ms": 1000,
                "data_freshness_state": "FRESH",
                "source_refs": {"fixture": "market"},
            },
        ),
        now_ms=1000,
    )


def test_pipeline_builds_envelope_from_aurora_and_regime():
    artifacts = build()
    assert artifacts.envelope.authority_status == "evidence_only"
    assert artifacts.envelope.strategy_opinions.aurora is not None
    assert artifacts.envelope.regime_context.present is True


def test_pipeline_produces_shadow_verdict_with_applied_false():
    artifacts = build()
    assert artifacts.verdict.authority_status == "shadow_only"
    assert artifacts.verdict.applied is False


def test_pipeline_evaluates_bridge_in_shadow_no_effect():
    artifacts = build()
    assert artifacts.bridge_decision.authority_mode == "shadow"
    assert artifacts.bridge_decision.bridge_action == "record_only"
    assert artifacts.bridge_decision.applied is False
    assert artifacts.bridge_decision.no_effect is True


def test_pipeline_never_creates_candidate_if_candidate_missing():
    artifacts = build(candidate_context=candidate(candidate_exists=False))
    assert artifacts.bridge_decision.bridge_action == "record_only"
    assert artifacts.bridge_decision.no_effect is True


def test_pipeline_produces_unresolved_shadow_calibration_row():
    artifacts = build()
    assert artifacts.calibration_row.outcome.outcome_status == "UNRESOLVED"
    assert artifacts.calibration_row.bridge.no_effect is True


def test_pipeline_preserves_refs_and_does_not_mutate_inputs():
    payload = aurora_payload()
    original = deepcopy(payload)
    artifacts = build(strategy_payload=payload)
    assert payload == original
    assert artifacts.envelope.decision_id == "decision-1"
    assert artifacts.calibration_row.source_refs.rid == "rid-1"


def test_pipeline_preserves_decision_cycle_lifecycle_and_trace_when_supplied():
    artifacts = build(
        strategy_payload=aurora_payload(trace_id="trace-1", source_event="EVT:STRATEGY_SIGNAL_PRODUCED"),
        candidate_context=candidate(
            decision_id="decision-x",
            cycle_key="cycle-x",
            lifecycle_id="life-x",
            order_id="order-x",
            trace_id="trace-candidate",
        ),
    )
    assert artifacts.envelope.decision_id == "decision-x"
    assert artifacts.envelope.cycle_key == "cycle-x"
    assert artifacts.verdict.source_refs.decision_id == "decision-x"
    assert artifacts.verdict.source_refs.cycle_key == "cycle-x"
    assert artifacts.bridge_decision.decision_id == "decision-x"
    assert artifacts.bridge_decision.source_refs.cycle_key == "cycle-x"
    assert artifacts.calibration_row.source_refs.decision_id == "decision-x"
    assert artifacts.calibration_row.source_refs.rid == "rid-1"
    assert artifacts.calibration_row.source_refs.lifecycle_id == "life-x"
    assert artifacts.calibration_row.source_refs.order_id == "order-x"
    assert artifacts.calibration_row.source_refs.trace_id == "trace-candidate"


def test_pipeline_marks_missing_identity_without_synthesizing_from_rid():
    artifacts = build(
        strategy_payload=aurora_payload(
            decision_id=None,
            rid="aurora_ETHUSDT_1779968400764",
            symbol="ETHUSDT",
        ),
        regime_payload={
            "symbol": "ETHUSDT",
            "ts_ms": 1000,
            "regime": "LOW_VOLATILITY",
            "confidence": 0.8,
        },
        candidate_context=candidate(
            decision_id=None,
            cycle_key=None,
            lifecycle_id=None,
            rid="aurora_ETHUSDT_1779968400764",
            symbol="ETHUSDT",
        ),
        market_context={
            "symbol": "ETHUSDT",
            "ts_ms": 1000,
            "data_freshness_state": "FRESH",
            "source_refs": {"fixture": "market"},
        },
    )
    missing = artifacts.calibration_row.diagnostics.missing_fields
    assert artifacts.calibration_row.source_refs.rid == "aurora_ETHUSDT_1779968400764"
    assert artifacts.calibration_row.source_refs.decision_id is None
    assert artifacts.calibration_row.source_refs.lifecycle_id is None
    assert "source_refs.decision_id" in missing
    assert "source_refs.lifecycle_id" in missing


def test_pipeline_is_deterministic():
    first = build()
    second = build()
    assert first.envelope.envelope_id == second.envelope.envelope_id
    assert first.verdict.verdict_id == second.verdict.verdict_id
    assert first.calibration_row.row_id == second.calibration_row.row_id


def test_regime_ctx_missing_symbol_is_enriched_from_candidate_symbol():
    payload = aurora_payload(symbol="ETHUSDT", rid="aurora_ETHUSDT_1779918604693")
    regime = {
        "ts_ms": 1779918600000,
        "regime": "LOW_VOLATILITY",
        "confidence": 0.8,
        "rid": "regime-rid",
    }
    artifacts = build(
        strategy_payload=payload,
        regime_payload=regime,
        candidate_context=candidate(symbol="ETHUSDT", rid="aurora_ETHUSDT_1779918604693"),
        market_context={
            "symbol": "ETHUSDT",
            "ts_ms": 1779918600000,
            "data_freshness_state": "FRESH",
            "source_refs": {"fixture": "market"},
        },
    )
    assert artifacts.envelope.regime_context.present is True
    assert artifacts.envelope.regime_context.envelope.symbol == "ETHUSDT"
    assert artifacts.bridge_decision.applied is False
    assert artifacts.bridge_decision.no_effect is True


def test_regime_symbol_conflict_is_not_silently_repaired():
    with pytest.raises(ValueError, match="REGIME_CONTEXT_SYMBOL_CONFLICT"):
        build(
            strategy_payload=aurora_payload(symbol="BTCUSDT"),
            regime_payload={"ts_ms": 1000, "regime": "LOW_VOLATILITY", "symbol": "ETHUSDT"},
            candidate_context=candidate(symbol="BTCUSDT"),
            market_context={
                "symbol": "BTCUSDT",
                "ts_ms": 1000,
                "data_freshness_state": "FRESH",
                "source_refs": {"fixture": "market"},
            },
        )


def test_missing_regime_symbol_source_fails_contained():
    with pytest.raises(ValueError, match="REGIME_CONTEXT_SYMBOL_MISSING"):
        build(
            strategy_payload={},
            regime_payload={"ts_ms": 1000, "regime": "LOW_VOLATILITY"},
            candidate_context=candidate(symbol=None),
            market_context=None,
        )


def test_no_default_regime_label_is_inserted():
    artifacts = build(
        regime_payload={"symbol": "BTCUSDT", "ts_ms": 1000, "confidence": 0.7},
    )
    assert artifacts.envelope.regime_context.envelope.regime.label is None
    assert "regime.label" in artifacts.envelope.regime_context.envelope.missingness.per_field


def test_missing_regime_confidence_remains_missing():
    artifacts = build(
        regime_payload={"symbol": "BTCUSDT", "ts_ms": 1000, "regime": "LOW_VOLATILITY"},
    )
    assert artifacts.envelope.regime_context.envelope.regime.confidence is None
    assert "regime.confidence" in artifacts.envelope.regime_context.envelope.missingness.per_field
