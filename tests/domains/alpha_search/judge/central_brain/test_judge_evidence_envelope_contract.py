from __future__ import annotations

import pytest
from pydantic import ValidationError

from apps.reference.domains.alpha_search.judge.central_brain.contracts import (
    DisagreementMap,
    ExecutionReadinessBlock,
    FreshnessMissingnessMap,
    HistoricalSurfaceEvidenceBlock,
    JudgeEvidenceEnvelopeV2,
    MarketContext,
    PortfolioContextBlock,
    RegimeContextBlock,
    RiskContextBlock,
    StrategyOpinions,
    EnvelopeProvenanceV2,
)
from apps.reference.domains.alpha_search.judge.central_brain.envelope_builder import (
    build_judge_evidence_envelope,
)
from apps.reference.domains.regime_detector.context_envelope import (
    build_regime_context_envelope,
)
from apps.reference.domains.strategies.runtimes.aurora.native_expert_adapter import (
    build_aurora_expert_output,
)


def _aurora_output():
    return build_aurora_expert_output(
        {
            "symbol": "BTCUSDT",
            "ts_ms": 1000,
            "side": "BUY",
            "features": {"ts_ms": 990, "obi": 0.3},
            "scoring": {"decision_score": 0.6, "pillar_sum": 0.4},
            "rid": "rid-1",
        },
        now_ms=1000,
    )


def _regime_context():
    return build_regime_context_envelope(
        {
            "symbol": "BTCUSDT",
            "ts_ms": 980,
            "regime": "LOW_VOLATILITY",
            "confidence": 0.7,
            "basis_tf_sec": 60,
            "rid": "rid-1",
        },
        decision_ts_ms=1000,
        freshness_threshold_ms=30_000,
    )


def _minimal_envelope() -> JudgeEvidenceEnvelopeV2:
    return JudgeEvidenceEnvelopeV2(
        envelope_id="env-1",
        created_ts_ms=1000,
        symbol="BTCUSDT",
        question_type="entry",
        market_context=MarketContext(
            symbol="BTCUSDT",
            ts_ms=1000,
            data_freshness_state="UNKNOWN",
            source_refs={},
        ),
        regime_context=RegimeContextBlock(
            present=False,
            envelope=None,
            missing_reason="not_supplied",
        ),
        strategy_opinions=StrategyOpinions(),
        risk_context=RiskContextBlock(
            present=False,
            missing_reason="not_supplied",
        ),
        portfolio_context=PortfolioContextBlock(
            present=False,
            missing_reason="not_supplied",
        ),
        execution_readiness=ExecutionReadinessBlock(
            present=False,
            blocking_reasons=[],
            missing_reason="not_supplied",
        ),
        historical_surface_evidence=HistoricalSurfaceEvidenceBlock(
            present=False,
            missing_reason="not_supplied",
        ),
        freshness_missingness_map=FreshnessMissingnessMap(),
        disagreement_map=DisagreementMap(
            agreement_state="NO_EXPERTS",
        ),
        provenance=EnvelopeProvenanceV2(
            input_contract_versions={"judge_evidence_envelope": "2.0.0"},
            builder_version="judge_evidence_envelope_builder_v1",
            source_refs={},
        ),
    )


def test_valid_minimal_envelope_validates():
    envelope = _minimal_envelope()
    assert envelope.schema_version == "2.0.0"
    assert envelope.authority_status == "evidence_only"


def test_extra_fields_are_rejected():
    payload = _minimal_envelope().model_dump()
    payload["verdict"] = "OPEN_LONG"
    with pytest.raises(ValidationError):
        JudgeEvidenceEnvelopeV2.model_validate(payload)


def test_authority_status_cannot_differ_from_evidence_only():
    payload = _minimal_envelope().model_dump()
    payload["authority_status"] = "live_gated"
    with pytest.raises(ValidationError):
        JudgeEvidenceEnvelopeV2.model_validate(payload)


@pytest.mark.parametrize(
    "field,value",
    [
        ("verdict", "OPEN_LONG"),
        ("judge_confidence", 0.9),
        ("final_confidence", 0.9),
        ("action", "allow"),
        ("cmd", "OPEN"),
    ],
)
def test_final_authority_fields_are_rejected(field, value):
    payload = _minimal_envelope().model_dump()
    payload[field] = value
    with pytest.raises(ValidationError):
        JudgeEvidenceEnvelopeV2.model_validate(payload)


def test_missing_blocks_require_explicit_missing_reason():
    with pytest.raises(ValidationError):
        RiskContextBlock(present=False)
    with pytest.raises(ValidationError):
        RegimeContextBlock(present=False, envelope=None)


def test_strategy_opinions_preserve_native_contract_instances():
    aurora = _aurora_output()
    envelope = build_judge_evidence_envelope(
        symbol="BTCUSDT",
        created_ts_ms=1000,
        aurora=aurora,
        regime_context=_regime_context(),
    )
    assert envelope.strategy_opinions.aurora is aurora
    assert envelope.strategy_opinions.aurora.strategy_id == "aurora"


def test_aurora_legacy_score_trace_remains_nested_only():
    envelope = build_judge_evidence_envelope(
        symbol="BTCUSDT",
        created_ts_ms=1000,
        aurora=_aurora_output(),
    )
    dumped = envelope.model_dump()
    assert dumped["strategy_opinions"]["aurora"]["legacy_score_trace"]["pillar_sum"] == 0.4
    assert "pillar_sum" not in dumped
    assert "score" not in dumped


def test_agreement_state_enum_validates():
    for state in (
        "AGREE_LONG",
        "AGREE_SHORT",
        "DISAGREE",
        "SINGLE_EXPERT",
        "NO_EXPERTS",
        "UNKNOWN",
    ):
        assert DisagreementMap(agreement_state=state).agreement_state == state
    with pytest.raises(ValidationError):
        DisagreementMap(agreement_state="OPEN_LONG")


def test_provenance_includes_contract_versions():
    envelope = build_judge_evidence_envelope(
        symbol="BTCUSDT",
        created_ts_ms=1000,
        aurora=_aurora_output(),
        regime_context=_regime_context(),
    )
    versions = envelope.provenance.input_contract_versions
    assert versions["judge_evidence_envelope"] == "2.0.0"
    assert versions["aurora_expert_output"] == "1.0.0"
    assert versions["regime_context_envelope"] == "1.0.0"

