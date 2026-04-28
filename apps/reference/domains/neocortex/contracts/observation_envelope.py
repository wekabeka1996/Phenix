from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import cast

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator

from apps.reference.domains.neocortex.contracts.causal_time import (
    DatasetVisibility,
)
from apps.reference.domains.neocortex.contracts.failure_taxonomy import (
    FailureOutcomeTaxonomy,
    FailureReasonCode,
    record_failure_outcome,
)
from apps.reference.domains.neocortex.logic.datasets.time_provenance import (
    CausalTimeProvenance,
)
from apps.reference.domains.neocortex.logic.ingest.state_aggregator_v2 import (
    NeocortexStateSnapshot,
)


OBSERVATION_ENVELOPE_SCHEMA_PASSPORT_ID = "neocortex.observation_envelope.v1"
OBSERVATION_ENVELOPE_VERSION = "1.0.0"

_OBSERVATION_ID_ALIASES = (
    "observation_id",
    "decision_id",
    "rid",
    "frame_id",
)
_SOURCE_EVENT_NAME_ALIASES = (
    "source_event_name",
    "event_name",
    "event_type",
    "trigger_event_type",
)
_SOURCE_EVENT_ID_ALIASES = (
    "source_event_id",
    "event_id",
    "decision_id",
    "rid",
    "frame_id",
)
_DECISION_BASIS_TS_ALIASES = (
    "decision_basis_ts_ms",
    "decision_basis_ts",
    "tick_ts_ms",
    "event_ts_ms",
    "timestamp_ms",
    "timestamp",
    "ts_ms",
    "ts",
)


def _coerce_source_mapping(
    source: Mapping[str, object] | None,
) -> dict[str, object]:
    if source is None:
        return {}
    return {str(key): value for key, value in source.items()}


def resolve_alias_value(
    source: Mapping[str, object],
    field_name: str,
    aliases: Sequence[str],
    *,
    required: bool = True,
    reason_code: FailureReasonCode = FailureReasonCode.MISSING_REQUIRED_STATE,
) -> object | None:
    for alias in aliases:
        if alias not in source:
            continue
        value = source[alias]
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return value

    if not required:
        return None

    record_failure_outcome(
        FailureOutcomeTaxonomy.BLOCK,
        reason_code,
        source="neocortex.contracts.observation_envelope.resolve_alias_value",
        location=f"observation_envelope.{field_name}",
        message=f"Missing required alias for {field_name}",
        recoverable=False,
        fallback_applied=False,
    )
    raise ValueError(f"Missing required alias for {field_name}")


def _optional_mapping(
    source: Mapping[str, object],
    *aliases: str,
) -> dict[str, object]:
    for alias in aliases:
        value = source.get(alias)
        if isinstance(value, Mapping):
            return {str(key): item for key, item in value.items()}
    return {}


def _tuple_from_vector(vector: np.ndarray) -> tuple[float, ...]:
    array = np.asarray(vector, dtype=np.float32).reshape(-1)
    return tuple(float(value) for value in array.tolist())


def _coerce_optional_int(
    value: object | None,
    *,
    field_name: str,
    default: int,
) -> int:
    if value is None:
        return int(default)
    if isinstance(value, bool):
        return int(default)
    if isinstance(value, (int, np.integer)):
        return int(value)
    if isinstance(value, float):
        if np.isfinite(value):
            return int(value)
        return int(default)
    if isinstance(value, str):
        stripped = value.strip()
        if stripped:
            try:
                return int(float(stripped))
            except ValueError:
                pass

    record_failure_outcome(
        FailureOutcomeTaxonomy.BLOCK,
        FailureReasonCode.MISSING_REQUIRED_STATE,
        source="neocortex.contracts.observation_envelope._coerce_optional_int",
        location=f"observation_envelope.{field_name}",
        message=f"Invalid integer value for {field_name}",
        recoverable=False,
        fallback_applied=False,
    )
    raise ValueError(f"Invalid integer value for {field_name}")


def _coerce_dataset_visibility(value: object) -> DatasetVisibility:
    text = str(value).strip()
    if text == "trainable":
        return cast(DatasetVisibility, "trainable")
    if text == "diagnostics_only":
        return cast(DatasetVisibility, "diagnostics_only")
    raise ValueError(f"Invalid dataset_visibility value: {value!r}")


def _feature_vector_payload(snapshot: NeocortexStateSnapshot) -> dict[str, object]:
    return {
        "feature_vector": [float(value) for value in snapshot.observation.features_vector.tolist()],
    }


def _freshness_payload(snapshot: NeocortexStateSnapshot) -> dict[str, object]:
    freshness: dict[str, object] = {
        "snapshot_age_ms": 0,
        "feature_age_ms": int(snapshot.tick_ts_ms) - int(snapshot.feature_event_ts_ms),
    }
    if snapshot.regime_event_ts_ms is not None:
        freshness["regime_age_ms"] = int(snapshot.tick_ts_ms) - int(snapshot.regime_event_ts_ms)
    else:
        freshness["regime_age_ms"] = None
    if snapshot.portfolio_event_ts_ms is not None:
        freshness["portfolio_age_ms"] = int(snapshot.tick_ts_ms) - int(snapshot.portfolio_event_ts_ms)
    else:
        freshness["portfolio_age_ms"] = None
    return freshness


class ObservationEnvelope(BaseModel):
    """Causal-only envelope for the pre-authority Neocortex state."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: str = Field(default=OBSERVATION_ENVELOPE_VERSION, min_length=1)
    schema_passport_id: str = Field(
        default=OBSERVATION_ENVELOPE_SCHEMA_PASSPORT_ID,
        min_length=1,
    )
    observation_id: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    decision_basis_ts_ms: int = Field(ge=1)
    source_event_name: str = Field(min_length=1)
    source_event_id: str = Field(min_length=1)
    event_time_source: CausalTimeProvenance
    event_time_is_causal: bool
    trainable: bool
    dataset_visibility: DatasetVisibility
    freshness: dict[str, object] = Field(default_factory=dict)
    missingness: dict[str, bool] = Field(default_factory=dict)
    market_features: dict[str, object] = Field(default_factory=dict)
    regime_state: dict[str, object] = Field(default_factory=dict)
    risk_state: dict[str, object] = Field(default_factory=dict)
    portfolio_state: dict[str, object] = Field(default_factory=dict)
    system_stress_state: dict[str, object] = Field(default_factory=dict)
    candidate_intent_summary: dict[str, object] = Field(default_factory=dict)
    gate_trace_summary: dict[str, object] = Field(default_factory=dict)
    state_vector: tuple[float, ...] = Field(min_length=1)
    context_vector: tuple[float, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_causal_only(self) -> "ObservationEnvelope":
        if not self.event_time_is_causal:
            raise ValueError("ObservationEnvelope requires causal state")
        if not self.trainable:
            raise ValueError("ObservationEnvelope requires trainable state")
        if self.dataset_visibility != "trainable":
            raise ValueError(
                "ObservationEnvelope requires dataset_visibility='trainable'"
            )
        return self

    @classmethod
    def from_snapshot(
        cls,
        snapshot: NeocortexStateSnapshot | None,
        source_frame: Mapping[str, object] | None = None,
    ) -> "ObservationEnvelope":
        if snapshot is None:
            record_failure_outcome(
                FailureOutcomeTaxonomy.BLOCK,
                FailureReasonCode.MISSING_REQUIRED_STATE,
                source="neocortex.contracts.observation_envelope.ObservationEnvelope.from_snapshot",
                location="observation_envelope.from_snapshot",
                message="Missing required Neocortex snapshot",
                recoverable=False,
                fallback_applied=False,
            )
            raise ValueError("Missing required Neocortex snapshot")

        if not snapshot.event_time_is_causal:
            record_failure_outcome(
                FailureOutcomeTaxonomy.BLOCK,
                FailureReasonCode.NON_CAUSAL_TIME,
                source="neocortex.contracts.observation_envelope.ObservationEnvelope.from_snapshot",
                location="observation_envelope.from_snapshot",
                detail=snapshot.symbol,
                message="Non-causal snapshot rejected",
                recoverable=False,
                fallback_applied=False,
            )
            raise ValueError("ObservationEnvelope requires causal state")

        if not snapshot.trainable or snapshot.dataset_visibility != "trainable":
            record_failure_outcome(
                FailureOutcomeTaxonomy.BLOCK,
                FailureReasonCode.MISSING_REQUIRED_STATE,
                source="neocortex.contracts.observation_envelope.ObservationEnvelope.from_snapshot",
                location="observation_envelope.from_snapshot",
                detail=snapshot.symbol,
                message="Trainable snapshot required for ObservationEnvelope",
                recoverable=False,
                fallback_applied=False,
            )
            raise ValueError("ObservationEnvelope requires trainable state")

        source = _coerce_source_mapping(source_frame)
        observation_id = resolve_alias_value(
            source,
            "observation_id",
            _OBSERVATION_ID_ALIASES,
            required=False,
        )
        source_event_name = resolve_alias_value(
            source,
            "source_event_name",
            _SOURCE_EVENT_NAME_ALIASES,
            required=False,
        )
        source_event_id = resolve_alias_value(
            source,
            "source_event_id",
            _SOURCE_EVENT_ID_ALIASES,
            required=False,
        )
        decision_basis_ts_ms = resolve_alias_value(
            source,
            "decision_basis_ts_ms",
            _DECISION_BASIS_TS_ALIASES,
            required=False,
        )

        source_event_name_text = str(
            source_event_name or snapshot.trigger_event_type
        ).strip()
        observation_id_text = str(
            observation_id or f"{snapshot.symbol}:{snapshot.tick_ts_ms}:{source_event_name_text}"
        ).strip()
        source_event_id_text = str(
            source_event_id or observation_id_text
        ).strip()
        decision_basis_ts_ms_int = _coerce_optional_int(
            decision_basis_ts_ms,
            field_name="decision_basis_ts_ms",
            default=int(snapshot.tick_ts_ms),
        )

        market_features = _optional_mapping(
            source,
            "market_features",
            "features",
            "observation_features",
        )
        if not market_features:
            observation_block = source.get("observation")
            if isinstance(observation_block, Mapping):
                market_features = _optional_mapping(
                    observation_block,
                    "features",
                    "market_features",
                )
        if not market_features:
            market_features = _feature_vector_payload(snapshot)

        regime_state = _optional_mapping(source, "regime_state")
        if not regime_state:
            regime_state = {
                "label": snapshot.regime_label,
                "confidence": float(snapshot.regime_confidence),
            }

        portfolio_state = _optional_mapping(
            source,
            "portfolio_state",
            "portfolio_position",
        )
        if not portfolio_state:
            portfolio_state = {
                "side": snapshot.position_side,
            }

        candidate_intent_summary = _optional_mapping(
            source,
            "candidate_intent_summary",
            "intent",
        )
        if not candidate_intent_summary:
            candidate_intent_summary = {
                "side": snapshot.intent_side,
            }

        return cls(
            observation_id=observation_id_text,
            symbol=str(snapshot.symbol),
            decision_basis_ts_ms=decision_basis_ts_ms_int,
            source_event_name=source_event_name_text,
            source_event_id=source_event_id_text,
            event_time_source=snapshot.feature_time_provenance,
            event_time_is_causal=bool(snapshot.event_time_is_causal),
            trainable=bool(snapshot.trainable),
            dataset_visibility=_coerce_dataset_visibility(
                snapshot.dataset_visibility
            ),
            freshness=_freshness_payload(snapshot),
            missingness={
                "regime_state_missing": snapshot.regime_label is None,
                "portfolio_state_missing": snapshot.position_side is None,
                "intent_state_missing": snapshot.intent_side is None,
            },
            market_features=market_features,
            regime_state=regime_state,
            risk_state={
                "trainable": bool(snapshot.trainable),
                "dataset_visibility": snapshot.dataset_visibility,
                "event_time_is_causal": bool(snapshot.event_time_is_causal),
            },
            portfolio_state=portfolio_state,
            system_stress_state={
                "trigger_event_type": snapshot.trigger_event_type,
                "context_vector_dim": int(len(snapshot.context_vector)),
            },
            candidate_intent_summary=candidate_intent_summary,
            gate_trace_summary={
                "schema_passport_id": OBSERVATION_ENVELOPE_SCHEMA_PASSPORT_ID,
                "version": OBSERVATION_ENVELOPE_VERSION,
                "feature_event_ts_ms": int(snapshot.feature_event_ts_ms),
            },
            state_vector=_tuple_from_vector(snapshot.state_vector),
            context_vector=_tuple_from_vector(snapshot.context_vector),
        )


def build_observation_envelope(
    snapshot: NeocortexStateSnapshot | None,
    source_frame: Mapping[str, object] | None = None,
) -> ObservationEnvelope:
    return ObservationEnvelope.from_snapshot(snapshot, source_frame)


__all__ = [
    "OBSERVATION_ENVELOPE_SCHEMA_PASSPORT_ID",
    "OBSERVATION_ENVELOPE_VERSION",
    "ObservationEnvelope",
    "build_observation_envelope",
    "resolve_alias_value",
]
