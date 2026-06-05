from __future__ import annotations

from copy import deepcopy

import pytest
from pydantic import ValidationError

from apps.reference.domains.strategies.runtimes.mean_reversion.native_expert_adapter import (
    EvidenceFreshness,
    MeanReversionEvidence,
    MeanReversionExpertOutput,
    Missingness,
    RegimeContextRef,
    SourceRefs,
    build_mean_reversion_expert_output,
    classify_freshness,
)


def _valid_output(**overrides):
    payload = {
        "expert_id": "mean_reversion.native_v1",
        "symbol": "BTCUSDT",
        "ts_ms": 1_700_000_000_000,
        "side_opinion": "BUY",
        "confidence": None,
        "confidence_source": "not_available",
        "horizon": None,
        "mean_reversion_evidence": MeanReversionEvidence(),
        "regime_context_ref": RegimeContextRef(),
        "evidence_freshness": EvidenceFreshness(
            feature_ts_ms=None,
            decision_ts_ms=1_700_000_000_000,
            age_ms=None,
            freshness_state="UNKNOWN",
        ),
        "missingness": Missingness(per_field={}),
        "invalidates_if": [],
        "reason_codes": [],
        "source_refs": SourceRefs(
            decision_id=None,
            rid="rid-1",
            trace_id=None,
            source_event="EVT:STRATEGY_SIGNAL_PRODUCED",
        ),
    }
    payload.update(overrides)
    return MeanReversionExpertOutput(**payload)


def _representative_payload(**overrides):
    payload = {
        "strategy_id": "mean_reversion",
        "symbol": "BTCUSDT",
        "ts_ms": 1_700_000_000_000,
        "bar_close_ts": 1_700_000_000_000,
        "side": "BUY",
        "confidence": 0.72,
        "why": "price_below_lower_bb:pct_b=0.012;rsi_oversold:28.1",
        "rid": "mr-rid-1",
        "trace_id": "trace-1",
        "source_event": "EVT:STRATEGY_SIGNAL_PRODUCED",
        "bb": {
            "upper": "105.0",
            "mid": "100.0",
            "lower": "95.0",
            "width": "0.041",
            "pct_b": "0.012",
        },
        "rsi": 28.1,
        "volatility": {"atr_14": "1.8"},
        "funding": {"rate": "-0.0001", "cost": "0.12"},
        "price_ctx": {
            "entry_price": "94.8",
            "target_price": "100.0",
            "stop_price": "92.5",
        },
        "regime_ctx": {
            "regime": "MEAN_REVERSION",
            "confidence": "0.66",
            "basis_tf_sec": 300,
            "regime_ts_ms": 1_699_999_999_000,
        },
    }
    payload.update(overrides)
    return payload


def test_valid_minimal_output_validates() -> None:
    output = _valid_output()

    assert output.schema_version == "1.0.0"
    assert output.strategy_id == "mean_reversion"
    assert output.question_type == "entry"
    assert output.authority_status == "opinion_only"


def test_extra_unknown_fields_rejected() -> None:
    with pytest.raises(ValidationError):
        _valid_output(unexpected="blocked")


def test_authority_status_cannot_differ_from_opinion_only() -> None:
    with pytest.raises(ValidationError):
        _valid_output(authority_status="live")


def test_missing_mr_fields_are_listed_in_missingness() -> None:
    output = build_mean_reversion_expert_output(
        {"symbol": "ETHUSDT", "ts_ms": 1, "features": {"rsi": 41.0}},
        now_ms=1,
    )

    assert output.mean_reversion_evidence.rsi == 41.0
    assert "mean_reversion_evidence.rsi" not in output.missingness.per_field
    assert output.missingness.per_field["mean_reversion_evidence.pct_b"] == "MISSING"
    assert output.missingness.per_field["mean_reversion_evidence.invalidation_level"] == "MISSING"


def test_no_fake_zero_or_neutral_defaults_inserted() -> None:
    output = build_mean_reversion_expert_output(
        {"symbol": "ETHUSDT", "ts_ms": 1},
        now_ms=1,
    )

    assert output.mean_reversion_evidence.rsi is None
    assert output.mean_reversion_evidence.pct_b is None
    assert output.confidence is None
    assert output.confidence_source == "not_available"
    assert output.side_opinion == "UNKNOWN"


def test_no_aurora_score_fields_or_pillar_sum_accepted() -> None:
    with pytest.raises(ValidationError):
        MeanReversionEvidence(score=0.5)  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        MeanReversionEvidence(pillar_sum=0.5)  # type: ignore[call-arg]

    output = build_mean_reversion_expert_output(
        _representative_payload(score=0.9, pillar_sum=0.2),
        now_ms=1_700_000_001_000,
    )
    dumped = output.model_dump()

    assert "score" not in dumped["mean_reversion_evidence"]
    assert "pillar_sum" not in dumped["mean_reversion_evidence"]


@pytest.mark.parametrize("side", ["BUY", "SELL", "NONE", "UNKNOWN"])
def test_side_opinion_enum_works(side: str) -> None:
    output = _valid_output(side_opinion=side)

    assert output.side_opinion == side


def test_explicit_confidence_source_is_labeled() -> None:
    strategy_conf = build_mean_reversion_expert_output(
        _representative_payload(strategy_confidence=0.81),
    )
    signal_conf = build_mean_reversion_expert_output(
        _representative_payload(confidence=0.61),
    )

    assert strategy_conf.confidence == 0.81
    assert strategy_conf.confidence_source == "explicit_strategy_confidence"
    assert signal_conf.confidence == 0.61
    assert signal_conf.confidence_source == "explicit_signal_confidence"


def test_source_refs_preserve_decision_id_rid_and_trace_id() -> None:
    output = build_mean_reversion_expert_output(
        _representative_payload(decision_id="decision-1", rid="rid-abc", trace_id="trace-abc")
    )

    assert output.source_refs.decision_id == "decision-1"
    assert output.source_refs.rid == "rid-abc"
    assert output.source_refs.trace_id == "trace-abc"


def test_freshness_classification_states() -> None:
    fresh = classify_freshness(1000, 1000, 2000, stale_after_ms=3000)
    stale = classify_freshness(1000, 1000, 5000, stale_after_ms=3000)
    missing = classify_freshness(None, None, 5000, stale_after_ms=3000)
    unknown = classify_freshness(1000, 1000, None, stale_after_ms=3000)

    assert fresh.freshness_state == "FRESH"
    assert stale.freshness_state == "STALE"
    assert missing.freshness_state == "MISSING"
    assert unknown.freshness_state == "UNKNOWN"


def test_representative_payload_preserves_native_mr_evidence() -> None:
    output = build_mean_reversion_expert_output(
        _representative_payload(),
        now_ms=1_700_000_001_000,
    )
    evidence = output.mean_reversion_evidence

    assert evidence.rsi == 28.1
    assert evidence.pct_b == 0.012
    assert evidence.bb_width == 0.041
    assert evidence.band_upper == 105.0
    assert evidence.band_mid == 100.0
    assert evidence.band_lower == 95.0
    assert evidence.atr == 1.8
    assert evidence.funding_rate == -0.0001
    assert evidence.funding_cost == 0.12
    assert evidence.entry_boundary == 94.8
    assert evidence.expected_reversion_target == 100.0
    assert evidence.invalidation_level == 92.5


def test_builder_does_not_mutate_input() -> None:
    payload = _representative_payload()
    before = deepcopy(payload)

    build_mean_reversion_expert_output(payload, now_ms=1_700_000_001_000)

    assert payload == before


def test_builder_is_deterministic() -> None:
    payload = _representative_payload()

    first = build_mean_reversion_expert_output(payload, now_ms=1_700_000_001_000)
    second = build_mean_reversion_expert_output(payload, now_ms=1_700_000_001_000)

    assert first == second
