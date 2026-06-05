from __future__ import annotations

from copy import deepcopy

import pytest
from pydantic import ValidationError

from apps.reference.domains.regime_detector.context_envelope import (
    RegimeContextEnvelope,
    RegimeDiagnostics,
    RegimeInfo,
    RegimeIntensity,
    RegimeMissingness,
    RegimeSourceRefs,
    RegimeTiming,
    RegimeTransition,
    build_regime_context_envelope,
    classify_regime_freshness,
)


def _valid_envelope(**overrides):
    payload = {
        "context_id": "structural:BTCUSDT:1700000000000",
        "symbol": "BTCUSDT",
        "ts_ms": 1_700_000_000_000,
        "source_event": "EVT:REGIME_DETECTED",
        "regime": RegimeInfo(
            label="TREND_UP",
            confidence=0.84,
            basis_tf_sec=300,
            source="sma_trend_v1",
        ),
        "timing": RegimeTiming(
            regime_ts_ms=1_700_000_000_000,
            decision_ts_ms=1_700_000_001_000,
            age_ms=1000,
            freshness_state="FRESH",
        ),
        "transition": RegimeTransition(
            state="STABLE",
            hysteresis_bars=2,
            bars_in_regime=2,
            switch_count_window=None,
        ),
        "intensity": RegimeIntensity(
            enabled=False,
            value=None,
            method=None,
        ),
        "diagnostics": RegimeDiagnostics(
            liveness_state="full_ready",
            stress_state=None,
            reason_codes=["stable_heartbeat"],
        ),
        "missingness": RegimeMissingness(per_field={}),
        "source_refs": RegimeSourceRefs(
            rid="rd-1",
            trace_id="trace-1",
            bar_close_ts_ms=1_700_000_000_000,
        ),
    }
    payload.update(overrides)
    return RegimeContextEnvelope(**payload)


def _representative_payload(**overrides):
    payload = {
        "ts": 1_700_000_000_000,
        "ts_ms": 1_700_000_000_000,
        "symbol": "BTCUSDT",
        "regime": "TREND_UP",
        "confidence": "0.84",
        "source_model": "sma_trend_v1",
        "regime_layer": "structural",
        "regime_scope": "per_symbol",
        "regime_clock": "bar",
        "structural_regime_ref": "structural:BTCUSDT:1700000000000",
        "basis_tf_sec": 300,
        "bar_close_ts_ms": 1_700_000_000_000,
        "changed": False,
        "last_update_ts_ms": 15_000,
        "stable_confidence": "0.84",
        "vol_ratio": "1.20",
        "vol_ratio_slope": 0.01,
        "storm_rejected": False,
        "hysteresis_bars": 2,
        "hysteresis_confirm_count": 2,
        "carried_previous_stable": False,
        "reason_summary": "stable_heartbeat; hysteresis_confirm=2/2",
        "warmup": {"full_ready": True, "ticks_seen": 250, "reasons": []},
        "data_quality": {"drops": [], "notes": []},
        "regime_event_ts_ms": 1_700_000_000_000,
        "regime_source": "same_bar_detector",
        "regime_provenance_reason": "same_bar_detector_truth",
        "rid": "rd-1",
        "trace_id": "trace-1",
        "source_event": "EVT:REGIME_DETECTED",
    }
    payload.update(overrides)
    return payload


def test_valid_minimal_envelope_validates() -> None:
    envelope = _valid_envelope()

    assert envelope.schema_version == "1.0.0"
    assert envelope.authority_status == "context_only"
    assert envelope.intensity.authority_note == "context_intensity_not_entry_authority"


def test_extra_unknown_fields_are_rejected() -> None:
    with pytest.raises(ValidationError):
        _valid_envelope(unexpected="blocked")


def test_authority_status_cannot_differ_from_context_only() -> None:
    with pytest.raises(ValidationError):
        _valid_envelope(authority_status="live")


def test_missing_regime_label_is_explicit_not_defaulted() -> None:
    envelope = build_regime_context_envelope(
        _representative_payload(regime=None),
        decision_ts_ms=1_700_000_001_000,
        freshness_threshold_ms=30_000,
    )

    assert envelope.regime.label is None
    assert envelope.missingness.per_field["regime.label"] == "MISSING"


def test_no_silent_default_or_uncertain_fallback() -> None:
    envelope = build_regime_context_envelope(
        _representative_payload(regime=None, regime_label=None),
        decision_ts_ms=1_700_000_001_000,
        freshness_threshold_ms=30_000,
    )

    assert envelope.regime.label is None
    assert envelope.regime.label != "DEFAULT"
    assert envelope.regime.label != "UNCERTAIN"


def test_freshness_classification_states() -> None:
    fresh = classify_regime_freshness(1000, 2000, 3000)
    stale = classify_regime_freshness(1000, 5000, 3000)
    missing = classify_regime_freshness(None, 5000, 3000)
    unknown_no_decision_ts = classify_regime_freshness(1000, None, 3000)
    unknown_no_threshold = classify_regime_freshness(1000, 2000, None)

    assert fresh.freshness_state == "FRESH"
    assert stale.freshness_state == "STALE"
    assert missing.freshness_state == "MISSING"
    assert unknown_no_decision_ts.freshness_state == "UNKNOWN"
    assert unknown_no_threshold.freshness_state == "UNKNOWN"
    assert unknown_no_threshold.age_ms == 1000


def test_transition_state_unknown_when_not_source_backed() -> None:
    payload = _representative_payload()
    for key in ("changed", "carried_previous_stable", "hysteresis_bars", "hysteresis_confirm_count"):
        payload.pop(key, None)

    envelope = build_regime_context_envelope(
        payload,
        decision_ts_ms=1_700_000_001_000,
        freshness_threshold_ms=30_000,
    )

    assert envelope.transition.state == "UNKNOWN"
    assert envelope.missingness.per_field["transition.state"] == "MISSING"


def test_explicit_transition_and_hysteresis_fields_are_preserved() -> None:
    transitioning = build_regime_context_envelope(
        _representative_payload(changed=True, hysteresis_bars=3, hysteresis_confirm_count=1),
        decision_ts_ms=1_700_000_001_000,
        freshness_threshold_ms=30_000,
    )
    pending = build_regime_context_envelope(
        _representative_payload(changed=False, carried_previous_stable=True),
        decision_ts_ms=1_700_000_001_000,
        freshness_threshold_ms=30_000,
    )

    assert transitioning.transition.state == "TRANSITIONING"
    assert transitioning.transition.hysteresis_bars == 3
    assert transitioning.transition.bars_in_regime == 1
    assert pending.transition.state == "PENDING"


def test_absent_intensity_is_disabled_without_value() -> None:
    envelope = build_regime_context_envelope(
        _representative_payload(),
        decision_ts_ms=1_700_000_001_000,
        freshness_threshold_ms=30_000,
    )

    assert envelope.intensity.enabled is False
    assert envelope.intensity.value is None
    assert envelope.intensity.method is None


def test_explicit_intensity_is_preserved_as_context_only() -> None:
    envelope = build_regime_context_envelope(
        _representative_payload(
            intensity_score="0.67",
            intensity_method="source_backed_test_fixture",
        ),
        decision_ts_ms=1_700_000_001_000,
        freshness_threshold_ms=30_000,
    )

    assert envelope.intensity.enabled is True
    assert envelope.intensity.value == 0.67
    assert envelope.intensity.method == "source_backed_test_fixture"
    assert envelope.intensity.authority_note == "context_intensity_not_entry_authority"


def test_score_and_pillar_sum_fields_are_not_accepted_by_contract_or_output() -> None:
    with pytest.raises(ValidationError):
        RegimeInfo(label="TREND_UP", confidence=0.8, pillar_sum=0.5)  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        _valid_envelope(score=0.5)

    envelope = build_regime_context_envelope(
        _representative_payload(score=0.7, pillar_sum=0.4, decision_score=0.2),
        decision_ts_ms=1_700_000_001_000,
        freshness_threshold_ms=30_000,
    )
    dumped = envelope.model_dump()

    assert "score" not in str(dumped)
    assert "pillar_sum" not in str(dumped)
    assert "decision_score" not in str(dumped)


def test_missingness_records_absent_context_fields() -> None:
    envelope = build_regime_context_envelope(
        _representative_payload(source_model=None, basis_tf_sec=None, trace_id=None),
        decision_ts_ms=1_700_000_001_000,
        freshness_threshold_ms=30_000,
    )

    assert envelope.missingness.per_field["regime.source"] == "MISSING"
    assert envelope.missingness.per_field["regime.basis_tf_sec"] == "MISSING"
    assert envelope.missingness.per_field["source_refs.trace_id"] == "MISSING"


def test_source_refs_preserve_identity_fields() -> None:
    envelope = build_regime_context_envelope(
        _representative_payload(
            rid="rid-abc",
            trace_id="trace-abc",
            bar_close_ts_ms=1_700_000_000_999,
        ),
        decision_ts_ms=1_700_000_001_000,
        freshness_threshold_ms=30_000,
    )

    assert envelope.source_refs.rid == "rid-abc"
    assert envelope.source_refs.trace_id == "trace-abc"
    assert envelope.source_refs.bar_close_ts_ms == 1_700_000_000_999


def test_builder_does_not_mutate_input_payload() -> None:
    payload = _representative_payload()
    before = deepcopy(payload)

    build_regime_context_envelope(
        payload,
        decision_ts_ms=1_700_000_001_000,
        freshness_threshold_ms=30_000,
    )

    assert payload == before


def test_builder_is_deterministic() -> None:
    payload = _representative_payload()

    first = build_regime_context_envelope(
        payload,
        decision_ts_ms=1_700_000_001_000,
        freshness_threshold_ms=30_000,
    )
    second = build_regime_context_envelope(
        payload,
        decision_ts_ms=1_700_000_001_000,
        freshness_threshold_ms=30_000,
    )

    assert first == second
