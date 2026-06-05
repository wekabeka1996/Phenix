from __future__ import annotations

from copy import deepcopy

import pytest
from pydantic import ValidationError

from apps.reference.domains.strategies.runtimes.md_amr.native_expert_adapter import (
    EvidenceFreshness,
    MDAMREvidence,
    MDAMRExpertOutput,
    Missingness,
    RegimeContextRef,
    SourceRefs,
    build_md_amr_expert_output,
    classify_freshness,
)


def _valid_output(**overrides):
    payload = {
        "expert_id": "md_amr.native_v1",
        "question_type": "entry",
        "symbol": "BTCUSDT",
        "ts_ms": 1_700_000_000_000,
        "side_opinion": "BUY",
        "lifecycle_opinion": None,
        "confidence": None,
        "confidence_source": "not_available",
        "horizon": None,
        "md_amr_evidence": MDAMREvidence(),
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
    return MDAMRExpertOutput(**payload)


def _representative_payload(**overrides):
    payload = {
        "strategy_id": "md_amr",
        "symbol": "ETHUSDT",
        "ts_ms": 1_700_000_000_000,
        "bar_close_ts": 1_700_000_000_000,
        "side": "BUY",
        "intent_kind": "ENTRY",
        "conf_ratio": 0.74,
        "reason_code": "MD_AMR_ENTRY_LONG",
        "rid": "md-rid-1",
        "trace_id": "trace-1",
        "source_event": "EVT:STRATEGY_SIGNAL_PRODUCED",
        "trace": {
            "conf_ratio": 0.74,
            "setup_quality": 0.82,
            "progress_state": "EARLY_PROGRESS",
            "hold_quality": 0.58,
            "context_validity": 0.91,
            "atr_zscore": 1.4,
            "channel_width_pct": 0.72,
            "channel_position": 0.31,
            "target_approach_pct": 0.04,
            "entry_anchor": {
                "entry_price": 100.0,
                "entry_target_price": 102.0,
            },
            "invalidation": {"stop_price": 96.5},
        },
        "channel_state": {
            "avg_low_12": 98.0,
            "avg_high_12": 103.0,
            "avg_close_12": 101.0,
        },
        "volatility": {"atr_14": 2.1},
        "liquidity": {"obi_close": -0.18},
        "regime_ctx": {
            "regime": "LOW_VOLATILITY",
            "confidence": 0.63,
            "basis_tf_sec": 300,
            "regime_ts_ms": 1_699_999_999_000,
        },
    }
    payload.update(overrides)
    return payload


def test_valid_minimal_output_validates() -> None:
    output = _valid_output()

    assert output.schema_version == "1.0.0"
    assert output.strategy_id == "md_amr"
    assert output.authority_status == "opinion_only"


def test_extra_unknown_fields_rejected() -> None:
    with pytest.raises(ValidationError):
        _valid_output(unexpected="blocked")


def test_authority_status_cannot_differ_from_opinion_only() -> None:
    with pytest.raises(ValidationError):
        _valid_output(authority_status="live")


def test_missing_md_amr_fields_are_listed_in_missingness() -> None:
    output = build_md_amr_expert_output(
        {"symbol": "ETHUSDT", "ts_ms": 1, "trace": {"setup_quality": 0.5}},
        now_ms=1,
    )

    assert output.md_amr_evidence.setup_quality == 0.5
    assert "md_amr_evidence.setup_quality" not in output.missingness.per_field
    assert output.missingness.per_field["md_amr_evidence.progress_state"] == "MISSING"
    assert output.missingness.per_field["md_amr_evidence.invalidation"] == "MISSING"


def test_native_fields_are_copied_only_when_present() -> None:
    empty = build_md_amr_expert_output({"symbol": "ETHUSDT", "ts_ms": 1})

    assert empty.md_amr_evidence.sentiment_state is None
    assert empty.md_amr_evidence.entry_anchor is None
    assert empty.md_amr_evidence.progress_state is None

    full = build_md_amr_expert_output(
        _representative_payload(sentiment_state="macro_clear"),
        now_ms=1_700_000_001_000,
    )
    evidence = full.md_amr_evidence

    assert evidence.sentiment_state == "macro_clear"
    assert evidence.entry_anchor == {"entry_price": 100.0, "entry_target_price": 102.0}
    assert evidence.progress_state == "EARLY_PROGRESS"
    assert evidence.setup_quality == 0.82
    assert evidence.hold_quality == 0.58
    assert evidence.context_validity == 0.91
    assert evidence.obi_close == -0.18
    assert evidence.target_approach_pct == 0.04
    assert evidence.channel_position == 0.31
    assert evidence.channel_width_pct == 0.72
    assert evidence.volatility_z == 1.4
    assert evidence.atr == 2.1
    assert evidence.invalidation == {"stop_price": 96.5}


def test_lifecycle_opinion_not_invented_for_entry_payloads() -> None:
    entry = build_md_amr_expert_output(_representative_payload(intent_kind="ENTRY"))
    exit_signal = build_md_amr_expert_output(_representative_payload(intent_kind="FULL_CLOSE"))

    assert entry.question_type == "entry"
    assert entry.lifecycle_opinion is None
    assert exit_signal.question_type == "lifecycle"
    assert exit_signal.lifecycle_opinion == "EXIT"


def test_no_aurora_score_fields_or_pillar_sum_accepted() -> None:
    with pytest.raises(ValidationError):
        MDAMREvidence(score=0.5)  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        MDAMREvidence(pillar_sum=0.5)  # type: ignore[call-arg]

    output = build_md_amr_expert_output(
        _representative_payload(score=0.9, pillar_sum=0.2, signal_score=0.3),
        now_ms=1_700_000_001_000,
    )
    dumped = output.model_dump()

    assert "score" not in dumped["md_amr_evidence"]
    assert "pillar_sum" not in dumped["md_amr_evidence"]
    assert "signal_score" not in dumped["md_amr_evidence"]


def test_explicit_confidence_source_is_labeled() -> None:
    strategy_conf = build_md_amr_expert_output(
        _representative_payload(strategy_confidence=0.81)
    )
    conf_ratio = build_md_amr_expert_output(_representative_payload(conf_ratio=0.62))

    assert strategy_conf.confidence == 0.81
    assert strategy_conf.confidence_source == "explicit_strategy_confidence"
    assert conf_ratio.confidence == 0.62
    assert conf_ratio.confidence_source == "explicit_conf_ratio"


def test_source_refs_preserve_decision_id_rid_and_trace_id() -> None:
    output = build_md_amr_expert_output(
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


def test_builder_does_not_mutate_input() -> None:
    payload = _representative_payload()
    before = deepcopy(payload)

    build_md_amr_expert_output(payload, now_ms=1_700_000_001_000)

    assert payload == before


def test_builder_is_deterministic() -> None:
    payload = _representative_payload()

    first = build_md_amr_expert_output(payload, now_ms=1_700_000_001_000)
    second = build_md_amr_expert_output(payload, now_ms=1_700_000_001_000)

    assert first == second
