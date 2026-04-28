from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping


class FailureOutcomeTaxonomy(str, Enum):
    BLOCK = "BLOCK"
    FALLBACK = "FALLBACK"
    SKIP_ROW = "SKIP_ROW"
    DEGRADED_OBSERVABILITY = "DEGRADED_OBSERVABILITY"
    FATAL_STARTUP = "FATAL_STARTUP"
    LEGACY_DIAGNOSTIC_ONLY = "LEGACY_DIAGNOSTIC_ONLY"


class FailureReasonCode(str, Enum):
    NON_CAUSAL_TIME = "NON_CAUSAL_TIME"
    MISSING_REQUIRED_STATE = "MISSING_REQUIRED_STATE"
    UNJOINABLE_LIFECYCLE = "UNJOINABLE_LIFECYCLE"
    LOW_SUPPORT = "LOW_SUPPORT"
    BASELINE_UNAVAILABLE = "BASELINE_UNAVAILABLE"
    MALFORMED_JSON = "MALFORMED_JSON"
    HANDLER_FAILURE = "HANDLER_FAILURE"
    BRIDGE_UNAVAILABLE = "BRIDGE_UNAVAILABLE"
    MODEL_ARTIFACT_MISMATCH = "MODEL_ARTIFACT_MISMATCH"
    TELEMETRY_FLUSH_FAILED = "TELEMETRY_FLUSH_FAILED"
    BRIDGE_TIMEOUT = "BRIDGE_TIMEOUT"
    SHADOW_GATE_BLOCK = "SHADOW_GATE_BLOCK"
    CONFIG_MISSING = "CONFIG_MISSING"
    CONFIG_INVALID = "CONFIG_INVALID"
    AURORA_CONFIG_MISSING = "AURORA_CONFIG_MISSING"
    AURORA_CONFIG_INVALID = "AURORA_CONFIG_INVALID"
    LEGACY_DIAGNOSTIC_ONLY = "LEGACY_DIAGNOSTIC_ONLY"


@dataclass(frozen=True)
class FailureOutcome:
    taxonomy: FailureOutcomeTaxonomy
    reason_code: FailureReasonCode
    source: str
    message: str
    recoverable: bool
    fallback_applied: bool
    details: Mapping[str, object] = field(default_factory=dict)


def _coerce_taxonomy(value: FailureOutcomeTaxonomy | str) -> FailureOutcomeTaxonomy:
    if isinstance(value, FailureOutcomeTaxonomy):
        return value
    return FailureOutcomeTaxonomy(str(value).strip().upper())


def _coerce_reason_code(value: FailureReasonCode | str) -> FailureReasonCode:
    if isinstance(value, FailureReasonCode):
        return value
    return FailureReasonCode(str(value).strip().upper())


def _default_recoverable(taxonomy: FailureOutcomeTaxonomy) -> bool:
    return taxonomy not in {
        FailureOutcomeTaxonomy.BLOCK,
        FailureOutcomeTaxonomy.FATAL_STARTUP,
    }


def _default_fallback_applied(taxonomy: FailureOutcomeTaxonomy) -> bool:
    return taxonomy == FailureOutcomeTaxonomy.FALLBACK


def _failure_ledger():
    from apps.reference.domains.neocortex.logic.failure_ledger import failure_ledger

    return failure_ledger


def record_failure_outcome(
    taxonomy: FailureOutcomeTaxonomy | str,
    reason_code: FailureReasonCode | str,
    *,
    source: str | None = None,
    location: str | None = None,
    message: str | None = None,
    recoverable: bool | None = None,
    fallback_applied: bool | None = None,
    details: Mapping[str, object] | None = None,
    detail: object | None = None,
) -> FailureOutcome:
    taxonomy_enum = _coerce_taxonomy(taxonomy)
    reason_enum = _coerce_reason_code(reason_code)
    outcome_details: dict[str, object] = dict(details or {})
    if location is not None:
        outcome_details.setdefault("location", str(location))
    if detail is not None:
        outcome_details.setdefault("detail", detail)

    outcome = FailureOutcome(
        taxonomy=taxonomy_enum,
        reason_code=reason_enum,
        source=str(source or location or "unknown"),
        message=str(message or reason_enum.value),
        recoverable=_default_recoverable(taxonomy_enum)
        if recoverable is None
        else bool(recoverable),
        fallback_applied=_default_fallback_applied(taxonomy_enum)
        if fallback_applied is None
        else bool(fallback_applied),
        details=outcome_details,
    )
    _failure_ledger().record_failure(outcome)
    return outcome


def get_failure_outcome_counts() -> Mapping[tuple[FailureOutcomeTaxonomy, FailureReasonCode], int]:
    return _failure_ledger().get_failure_counts()


def get_failure_outcome_total(
    *,
    taxonomy: FailureOutcomeTaxonomy | str,
    reason_code: FailureReasonCode | str,
) -> int:
    taxonomy_enum = _coerce_taxonomy(taxonomy)
    reason_enum = _coerce_reason_code(reason_code)
    return int(
        get_failure_outcome_counts().get((taxonomy_enum, reason_enum), 0)
    )


def reset_failure_outcomes() -> None:
    _failure_ledger().reset_failure_counts()


__all__ = [
    "FailureOutcomeTaxonomy",
    "FailureReasonCode",
    "FailureOutcome",
    "record_failure_outcome",
    "get_failure_outcome_counts",
    "get_failure_outcome_total",
    "reset_failure_outcomes",
]
