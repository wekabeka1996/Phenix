from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from apps.reference.domains.neocortex.config_models import load_config
from apps.reference.domains.neocortex.contracts.failure_taxonomy import (
    FailureOutcomeTaxonomy,
    FailureReasonCode,
    get_failure_outcome_total,
    reset_failure_outcomes,
)
from apps.reference.domains.neocortex.contracts.observation_envelope import (
    ObservationEnvelope,
    build_observation_envelope,
    _coerce_dataset_visibility,
    _coerce_optional_int,
)
from apps.reference.domains.neocortex.logic.datasets.time_provenance import (
    CausalTimeProvenance,
)
from apps.reference.domains.neocortex.logic.ingest.state_aggregator_v2 import (
    NeocortexStateAggregator,
)


CONFIG_DIR = Path("apps/reference/domains/neocortex/config")


def _make_aggregator(*, enforcement_mode: str = "disabled") -> NeocortexStateAggregator:
    config = load_config(CONFIG_DIR)
    return NeocortexStateAggregator(
        config.ingest,
        strict_clock=True,
        neocortex_enforcement_mode=enforcement_mode,
    )


def _feature_event(
    ts_ms: int,
    provenance: CausalTimeProvenance,
) -> dict[str, object]:
    return {
        "event_name": "EVT:FEATURES_CALCULATED",
        "captured_ts_ms": ts_ms,
        "payload": {
            "symbol": "BTCUSDT",
            "timestamp_ms": ts_ms,
            "time_provenance": provenance.value,
            "features": {
                "price": 100.0,
                "obi": 0.25,
                "delta_price": 1.0,
            },
        },
    }


def _trainable_snapshot():
    aggregator = _make_aggregator()
    snapshot = aggregator.ingest_event(
        _feature_event(1_700_000_000_000, CausalTimeProvenance.AURORA_EVENT)
    )
    assert snapshot is not None
    return snapshot


def _non_causal_snapshot():
    aggregator = _make_aggregator()
    snapshot = aggregator.ingest_event(
        _feature_event(1_700_000_000_000, CausalTimeProvenance.CAPTURED_WALLCLOCK)
    )
    assert snapshot is not None
    return snapshot


def setup_function() -> None:
    reset_failure_outcomes()


def test_causal_state_builds_valid_observation_envelope() -> None:
    snapshot = _trainable_snapshot()
    envelope = build_observation_envelope(
        snapshot,
        {
            "decision_id": "decision-a",
            "event_name": "EVT:BAR_CLOSED",
            "observation": {"features": {"price": 100.0}},
            "intent": {"side": "BUY"},
        },
    )
    assert isinstance(envelope, ObservationEnvelope)
    assert envelope.event_time_is_causal is True
    assert envelope.trainable is True
    assert envelope.dataset_visibility == "trainable"
    assert envelope.state_vector
    assert envelope.context_vector


def test_non_causal_state_rejected() -> None:
    snapshot = _non_causal_snapshot()
    with pytest.raises(ValueError, match="ObservationEnvelope requires causal state"):
        build_observation_envelope(snapshot)
    assert get_failure_outcome_total(
        taxonomy=FailureOutcomeTaxonomy.BLOCK,
        reason_code=FailureReasonCode.NON_CAUSAL_TIME,
    ) == 1


def test_trainable_false_state_rejected_for_model_input() -> None:
    snapshot = dataclasses.replace(
        _trainable_snapshot(),
        trainable=False,
        dataset_visibility="diagnostics_only",
    )
    with pytest.raises(ValueError, match="ObservationEnvelope requires trainable state"):
        build_observation_envelope(snapshot)
    assert get_failure_outcome_total(
        taxonomy=FailureOutcomeTaxonomy.BLOCK,
        reason_code=FailureReasonCode.MISSING_REQUIRED_STATE,
    ) == 1


def test_diagnostics_only_state_rejected_for_authority_input() -> None:
    snapshot = dataclasses.replace(
        _trainable_snapshot(),
        dataset_visibility="diagnostics_only",
    )
    with pytest.raises(ValueError, match="ObservationEnvelope requires trainable state"):
        build_observation_envelope(snapshot)
    assert get_failure_outcome_total(
        taxonomy=FailureOutcomeTaxonomy.BLOCK,
        reason_code=FailureReasonCode.MISSING_REQUIRED_STATE,
    ) == 1


def test_missing_required_state_rejected_with_typed_failure() -> None:
    with pytest.raises(ValueError, match="Missing required Neocortex snapshot"):
        build_observation_envelope(None)
    assert get_failure_outcome_total(
        taxonomy=FailureOutcomeTaxonomy.BLOCK,
        reason_code=FailureReasonCode.MISSING_REQUIRED_STATE,
    ) == 1


def test_dataset_visibility_helper_accepts_only_explicit_values() -> None:
    assert _coerce_dataset_visibility("trainable") == "trainable"
    assert _coerce_dataset_visibility("diagnostics_only") == "diagnostics_only"
    with pytest.raises(ValueError, match="Invalid dataset_visibility"):
        _coerce_dataset_visibility("legacy")
    with pytest.raises(ValueError, match="Invalid integer value"):
        _coerce_optional_int(object(), field_name="decision_basis_ts_ms", default=7)
