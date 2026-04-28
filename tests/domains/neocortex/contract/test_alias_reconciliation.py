from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import pytest

from apps.reference.domains.neocortex.config_models import load_config
from apps.reference.domains.neocortex.contracts.causal_time import (
    CausalTimeProvenance,
    coerce_causal_time_provenance,
    make_causal_decision,
)
from apps.reference.domains.neocortex.contracts.failure_taxonomy import (
    FailureOutcomeTaxonomy,
    FailureReasonCode,
    get_failure_outcome_total,
    reset_failure_outcomes,
)
from apps.reference.domains.neocortex.contracts.observation_envelope import (
    build_observation_envelope,
    resolve_alias_value,
)
from apps.reference.domains.neocortex.logic.ingest.state_aggregator_v2 import (
    NeocortexStateAggregator,
)


CONFIG_DIR = Path("apps/reference/domains/neocortex/config")


def _causal_snapshot():
    config = load_config(CONFIG_DIR)
    aggregator = NeocortexStateAggregator(
        config.ingest,
        strict_clock=True,
        neocortex_enforcement_mode="disabled",
    )
    feature_event = {
        "event_name": "EVT:FEATURES_CALCULATED",
        "captured_ts_ms": 1_700_000_000_000,
        "payload": {
            "symbol": "BTCUSDT",
            "timestamp_ms": 1_700_000_000_000,
            "time_provenance": "aurora_event",
            "features": {
                "price": 100.0,
                "obi": 0.25,
                "delta_price": 1.0,
            },
        },
    }
    snapshot = aggregator.ingest_event(feature_event)
    assert snapshot is not None
    return snapshot


def setup_function() -> None:
    reset_failure_outcomes()


def test_canonical_time_aliases_resolve_deterministically() -> None:
    assert coerce_causal_time_provenance("timestamp") is CausalTimeProvenance.AURORA_EVENT
    assert coerce_causal_time_provenance("ts") is CausalTimeProvenance.AURORA_EVENT
    assert coerce_causal_time_provenance("legacy_non_causal_file_offset") is CausalTimeProvenance.FILE_OFFSET_LEGACY


def test_duplicate_aliases_follow_explicit_precedence() -> None:
    source = {
        "observation_id": "decision-a",
        "decision_id": "decision-b",
        "rid": "decision-c",
    }
    assert resolve_alias_value(
        source,
        "observation_id",
        ("observation_id", "decision_id", "rid"),
        required=True,
    ) == "decision-a"
    assert resolve_alias_value(
        source,
        "observation_id",
        ("decision_id", "rid", "observation_id"),
        required=True,
    ) == "decision-b"


def test_unknown_alias_fails_closed() -> None:
    with pytest.raises(ValueError, match="Missing required alias for observation_id"):
        resolve_alias_value(
            {},
            "observation_id",
            ("observation_id", "decision_id", "rid"),
            required=True,
        )
    assert get_failure_outcome_total(
        taxonomy=FailureOutcomeTaxonomy.BLOCK,
        reason_code=FailureReasonCode.MISSING_REQUIRED_STATE,
    ) == 1


def test_unknown_time_alias_does_not_become_safe_business_value() -> None:
    decision = make_causal_decision(
        1_700_000_000_000,
        coerce_causal_time_provenance("does_not_exist"),
    )
    assert decision.event_time_source is CausalTimeProvenance.UNKNOWN
    assert decision.trainable is False
    assert decision.dataset_visibility == "diagnostics_only"


def test_observation_envelope_builder_uses_explicit_alias_precedence() -> None:
    snapshot = _causal_snapshot()
    envelope = build_observation_envelope(
        snapshot,
        {
            "decision_id": "decision-a",
            "rid": "decision-b",
            "frame_id": "frame-c",
            "event_name": "EVT:BAR_CLOSED",
            "timestamp_ms": 1_700_000_000_100,
            "observation": {"features": {"price": 100.0}},
        },
    )
    assert envelope.observation_id == "decision-a"
    assert envelope.source_event_id == "decision-a"
    assert envelope.source_event_name == "EVT:BAR_CLOSED"
    assert envelope.decision_basis_ts_ms == 1_700_000_000_100
