from __future__ import annotations

import pytest
from pydantic import ValidationError

from apps.reference.domains.strategies.runtimes.aurora.native_expert_adapter import (
    AuroraExpertOutput,
    EvidenceFreshness,
    LegacyScoreTrace,
    MicrostructureEvidence,
    Missingness,
    RegimeContextRef,
    SourceRefs,
    build_aurora_expert_output,
    classify_freshness,
)


def _valid_output(**overrides):
    payload = {
        "expert_id": "aurora.microstructure_native_v1",
        "symbol": "BTCUSDT",
        "ts_ms": 1_700_000_000_000,
        "side_opinion": "BUY",
        "confidence": None,
        "confidence_source": "not_available",
        "horizon": None,
        "microstructure_evidence": MicrostructureEvidence(
            obi=None,
            tfi=None,
            absorption=None,
            liquidity_kappa=None,
            spread_bps=None,
            macro_resid=None,
            delta_price=None,
            volatility_state=None,
            large_trade_imbalance=None,
        ),
        "evidence_freshness": EvidenceFreshness(
            feature_ts_ms=None,
            decision_ts_ms=1_700_000_000_000,
            age_ms=None,
            freshness_state="UNKNOWN",
        ),
        "missingness": Missingness(per_field={"obi": "MISSING"}),
        "regime_context_ref": RegimeContextRef(
            regime_label=None,
            regime_confidence=None,
            basis_tf_sec=None,
            regime_age_ms=None,
        ),
        "legacy_score_trace": LegacyScoreTrace(
            pillar_sum=None,
            raw_score=None,
            decision_score=None,
            sizing_score=None,
            admission_mode=None,
            sizing_mode=None,
            score_lineage_present=False,
        ),
        "invalidates_if": [],
        "reason_codes": [],
        "source_refs": SourceRefs(
            decision_id=None,
            rid="aurora_BTCUSDT_1700000000000",
            trace_id=None,
            source_event="EVT:STRATEGY_SIGNAL_PRODUCED",
        ),
    }
    payload.update(overrides)
    return AuroraExpertOutput(**payload)


def test_valid_minimal_output_validates() -> None:
    output = _valid_output()

    assert output.schema_version == "1.0.0"
    assert output.strategy_id == "aurora"
    assert output.question_type == "entry"
    assert output.authority_status == "opinion_only"


def test_extra_unknown_fields_are_rejected() -> None:
    with pytest.raises(ValidationError):
        _valid_output(unexpected="blocked")


def test_authority_status_cannot_be_anything_except_opinion_only() -> None:
    with pytest.raises(ValidationError):
        _valid_output(authority_status="live")


def test_missing_microstructure_fields_are_recorded_in_missingness() -> None:
    output = build_aurora_expert_output(
        {
            "symbol": "BTCUSDT",
            "ts_ms": 1_700_000_000_000,
            "features": {"obi": 0.12},
            "scoring": {},
        },
        now_ms=1_700_000_001_000,
    )

    assert output.microstructure_evidence.obi == 0.12
    assert "obi" not in output.missingness.per_field
    assert output.missingness.per_field["tfi"] == "MISSING"
    assert output.missingness.per_field["large_trade_imbalance"] == "MISSING"


def test_no_fake_zero_or_neutral_defaults_are_inserted() -> None:
    output = build_aurora_expert_output(
        {"symbol": "ETHUSDT", "ts_ms": 1, "features": {}, "scoring": {}},
        now_ms=1,
    )

    assert output.microstructure_evidence.obi is None
    assert output.microstructure_evidence.spread_bps is None
    assert output.confidence is None
    assert output.confidence_source == "not_available"
    assert output.side_opinion == "UNKNOWN"


def test_pillar_sum_appears_only_under_legacy_score_trace() -> None:
    output = build_aurora_expert_output(
        {
            "symbol": "BTCUSDT",
            "ts_ms": 10,
            "features": {"pillar_sum": 0.41, "obi": 0.2},
            "scoring": {"psi_vector": {"s_linear": 0.41}},
        },
        now_ms=10,
    )
    dumped = output.model_dump()

    assert output.legacy_score_trace.pillar_sum == 0.41
    assert "pillar_sum" not in dumped["microstructure_evidence"]


def test_score_aliases_are_not_accepted_as_canonical_microstructure_fields() -> None:
    with pytest.raises(ValidationError):
        MicrostructureEvidence(score=0.8)  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        MicrostructureEvidence(signal_score=0.8)  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        MicrostructureEvidence(final_score=0.8)  # type: ignore[call-arg]


@pytest.mark.parametrize("side", ["BUY", "SELL", "NONE", "UNKNOWN"])
def test_side_opinion_supports_contract_values(side: str) -> None:
    output = _valid_output(side_opinion=side)

    assert output.side_opinion == side


def test_confidence_source_is_explicit() -> None:
    explicit = build_aurora_expert_output(
        {
            "symbol": "BTCUSDT",
            "ts_ms": 10,
            "strategy_confidence": 0.72,
            "features": {},
            "scoring": {"decision_score": 0.44},
        }
    )
    legacy = build_aurora_expert_output(
        {
            "symbol": "BTCUSDT",
            "ts_ms": 10,
            "features": {},
            "scoring": {"decision_score": -0.44},
        }
    )

    assert explicit.confidence == 0.72
    assert explicit.confidence_source == "explicit_strategy_confidence"
    assert legacy.confidence == 0.44
    assert legacy.confidence_source == "decision_score_abs_legacy_trace"


def test_source_refs_preserves_decision_id_and_rid() -> None:
    output = build_aurora_expert_output(
        {
            "symbol": "BTCUSDT",
            "ts_ms": 10,
            "decision_id": "decision-1",
            "rid": "aurora_BTCUSDT_10",
            "trace_id": "trace-1",
            "source_event": "EVT:STRATEGY_SIGNAL_PRODUCED",
            "features": {},
            "scoring": {},
        }
    )

    assert output.source_refs.decision_id == "decision-1"
    assert output.source_refs.rid == "aurora_BTCUSDT_10"
    assert output.source_refs.trace_id == "trace-1"


def test_freshness_classification_states() -> None:
    fresh = classify_freshness(1000, 1000, 2000, stale_after_ms=3000)
    stale = classify_freshness(1000, 1000, 5000, stale_after_ms=3000)
    missing = classify_freshness(None, None, 5000, stale_after_ms=3000)
    unknown = classify_freshness(1000, 1000, None, stale_after_ms=3000)

    assert fresh.freshness_state == "FRESH"
    assert fresh.age_ms == 1000
    assert stale.freshness_state == "STALE"
    assert stale.age_ms == 4000
    assert missing.freshness_state == "MISSING"
    assert missing.age_ms is None
    assert unknown.freshness_state == "UNKNOWN"
    assert unknown.age_ms is None
