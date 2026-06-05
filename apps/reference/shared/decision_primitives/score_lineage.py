from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


RAW_SIGNED_LINEAR = "raw_signed_linear"
SIGNED_DECISION_SCORE = "signed_decision_score"
SIGNED_OBJECTIVE_SCORE = "signed_objective_score"
NORMALIZED_CONFIDENCE_0_1 = "normalized_confidence_0_1"
GATE_RESOLVED_CONFIDENCE = "gate_resolved_confidence"

NONE_THRESHOLD_FAMILY = "none"
AURORA_ADMISSION_THRESHOLD_FAMILY = "aurora_admission"
OBJECTIVE_GATE_THRESHOLD_FAMILY = "objective_gate"
LOW_VOL_DIRECTION_CONFIDENCE_THRESHOLD_FAMILY = "low_vol_direction_confidence"

LIVE_AUTHORITATIVE = "live_authoritative"
SHADOW_ONLY = "shadow_only"
COMPATIBILITY_ONLY = "compatibility_only"
DEPRECATED_ALIAS = "deprecated_alias"

SCORE_SCALE_FAMILIES = frozenset(
    {
        RAW_SIGNED_LINEAR,
        SIGNED_DECISION_SCORE,
        SIGNED_OBJECTIVE_SCORE,
        NORMALIZED_CONFIDENCE_0_1,
        GATE_RESOLVED_CONFIDENCE,
    }
)

THRESHOLD_FAMILIES = frozenset(
    {
        NONE_THRESHOLD_FAMILY,
        AURORA_ADMISSION_THRESHOLD_FAMILY,
        OBJECTIVE_GATE_THRESHOLD_FAMILY,
        LOW_VOL_DIRECTION_CONFIDENCE_THRESHOLD_FAMILY,
    }
)

LIVE_AUTHORITY_STATUSES = frozenset(
    {
        LIVE_AUTHORITATIVE,
        SHADOW_ONLY,
        COMPATIBILITY_ONLY,
        DEPRECATED_ALIAS,
    }
)

LIVE_SCORE_LINEAGE_PATH = (
    "pillar_sum -> QuadraticScoringKernel.compute() -> Aurora scoring payload -> "
    "StrategyGateway strategy_trace -> low_vol_cost_floor -> SafetyGateResult / decision trace"
)


@dataclass(frozen=True, slots=True)
class ScoreFieldContract:
    field: str
    producer: str
    consumer: str
    scale: str
    numeric_contract: str
    threshold_family: str
    live_authority_status: str
    allowed_as_direction_confidence: bool
    notes: str


PRIMARY_SCORE_FIELDS = (
    "pillar_sum",
    "decision_score",
    "score",
    "signal_score",
    "final_score_raw",
    "final_score",
    "direction_confidence",
    "strategy_confidence",
    "judge_confidence",
    "aurora_pillar_confidence_candidate",
)


def _contract(
    *,
    field: str,
    producer: str,
    consumer: str,
    scale: str,
    numeric_contract: str,
    threshold_family: str,
    live_authority_status: str,
    allowed_as_direction_confidence: bool,
    notes: str,
) -> ScoreFieldContract:
    return ScoreFieldContract(
        field=field,
        producer=producer,
        consumer=consumer,
        scale=scale,
        numeric_contract=numeric_contract,
        threshold_family=threshold_family,
        live_authority_status=live_authority_status,
        allowed_as_direction_confidence=allowed_as_direction_confidence,
        notes=notes,
    )


SCORE_FIELD_REGISTRY: dict[str, ScoreFieldContract] = {
    "pillar_sum": _contract(
        field="pillar_sum",
        producer="Aurora feature assembly",
        consumer="QuadraticScoringKernel.compute()",
        scale=RAW_SIGNED_LINEAR,
        numeric_contract="finite signed float",
        threshold_family=NONE_THRESHOLD_FAMILY,
        live_authority_status=LIVE_AUTHORITATIVE,
        allowed_as_direction_confidence=False,
        notes="Live Aurora raw input. Not a normalized confidence.",
    ),
    "decision_score": _contract(
        field="decision_score",
        producer="QuadraticScoringKernel.compute()",
        consumer="Aurora admission thresholds / StrategyGateway / decision trace",
        scale=SIGNED_DECISION_SCORE,
        numeric_contract="finite signed float",
        threshold_family=AURORA_ADMISSION_THRESHOLD_FAMILY,
        live_authority_status=LIVE_AUTHORITATIVE,
        allowed_as_direction_confidence=False,
        notes="Pre-objective live admission score compared to thr_buy / thr_sell.",
    ),
    "score": _contract(
        field="score",
        producer="Aurora scoring payload compatibility alias",
        consumer="Legacy scoring consumers",
        scale=SIGNED_DECISION_SCORE,
        numeric_contract="finite signed float",
        threshold_family=AURORA_ADMISSION_THRESHOLD_FAMILY,
        live_authority_status=COMPATIBILITY_ONLY,
        allowed_as_direction_confidence=False,
        notes="Mutable alias. Runtime lineage must mark post-objective overrides explicitly.",
    ),
    "signal_score": _contract(
        field="signal_score",
        producer="StrategyGateway compatibility trace assembly",
        consumer="Legacy strategy_trace consumers",
        scale=SIGNED_DECISION_SCORE,
        numeric_contract="finite signed float",
        threshold_family=NONE_THRESHOLD_FAMILY,
        live_authority_status=COMPATIBILITY_ONLY,
        allowed_as_direction_confidence=False,
        notes="Compatibility surface only. Runtime meaning follows upstream score lineage.",
    ),
    "final_score_raw": _contract(
        field="final_score_raw",
        producer="StrategyGateway compatibility trace assembly",
        consumer="Decision trace / forensic consumers",
        scale=SIGNED_DECISION_SCORE,
        numeric_contract="finite signed float",
        threshold_family=NONE_THRESHOLD_FAMILY,
        live_authority_status=DEPRECATED_ALIAS,
        allowed_as_direction_confidence=False,
        notes="Deprecated alias for pre-objective decision score fallback.",
    ),
    "final_score": _contract(
        field="final_score",
        producer="Aurora / StrategyGateway final-stage score assembly",
        consumer="LOW_VOL_COST_FLOOR observability / decision trace",
        scale=SIGNED_DECISION_SCORE,
        numeric_contract="finite signed float",
        threshold_family=NONE_THRESHOLD_FAMILY,
        live_authority_status=COMPATIBILITY_ONLY,
        allowed_as_direction_confidence=False,
        notes="Compatibility field for the current final signed score at the emitting stage.",
    ),
    "direction_confidence": _contract(
        field="direction_confidence",
        producer="LOW_VOL_COST_FLOOR",
        consumer="Decision trace / low-vol telemetry",
        scale=GATE_RESOLVED_CONFIDENCE,
        numeric_contract="0..1 normalized",
        threshold_family=LOW_VOL_DIRECTION_CONFIDENCE_THRESHOLD_FAMILY,
        live_authority_status=LIVE_AUTHORITATIVE,
        allowed_as_direction_confidence=False,
        notes="Gate-local resolved field, not an upstream producer field.",
    ),
    "strategy_confidence": _contract(
        field="strategy_confidence",
        producer="Strategy-specific helper math",
        consumer="LOW_VOL_COST_FLOOR candidate input",
        scale=NORMALIZED_CONFIDENCE_0_1,
        numeric_contract="0..1 normalized",
        threshold_family=LOW_VOL_DIRECTION_CONFIDENCE_THRESHOLD_FAMILY,
        live_authority_status=SHADOW_ONLY,
        allowed_as_direction_confidence=True,
        notes="Normalized confidence candidate. No proven live Aurora producer in current checkout.",
    ),
    "judge_confidence": _contract(
        field="judge_confidence",
        producer="Objective / judge helper surfaces",
        consumer="LOW_VOL_COST_FLOOR candidate input",
        scale=NORMALIZED_CONFIDENCE_0_1,
        numeric_contract="0..1 normalized",
        threshold_family=LOW_VOL_DIRECTION_CONFIDENCE_THRESHOLD_FAMILY,
        live_authority_status=SHADOW_ONLY,
        allowed_as_direction_confidence=True,
        notes="Normalized confidence candidate. Shadow until a live producer is explicitly proven.",
    ),
    "aurora_pillar_confidence_candidate": _contract(
        field="aurora_pillar_confidence_candidate",
        producer="StrategyGateway trace assembly",
        consumer="Forensic trace only",
        scale=NORMALIZED_CONFIDENCE_0_1,
        numeric_contract="0..1 normalized",
        threshold_family=LOW_VOL_DIRECTION_CONFIDENCE_THRESHOLD_FAMILY,
        live_authority_status=SHADOW_ONLY,
        allowed_as_direction_confidence=False,
        notes="Shadow-only normalized candidate derived from signed score / threshold geometry.",
    ),
    "raw_score": _contract(
        field="raw_score",
        producer="QuadraticScoringKernel.compute()",
        consumer="Aurora scoring payload / quadratic trace",
        scale=RAW_SIGNED_LINEAR,
        numeric_contract="finite signed float",
        threshold_family=NONE_THRESHOLD_FAMILY,
        live_authority_status=LIVE_AUTHORITATIVE,
        allowed_as_direction_confidence=False,
        notes="Appendix field for kernel raw linear score.",
    ),
    "objective_score": _contract(
        field="objective_score",
        producer="objective_gate_evaluator",
        consumer="Aurora final score override / forensic trace",
        scale=SIGNED_OBJECTIVE_SCORE,
        numeric_contract="finite signed float",
        threshold_family=OBJECTIVE_GATE_THRESHOLD_FAMILY,
        live_authority_status=LIVE_AUTHORITATIVE,
        allowed_as_direction_confidence=False,
        notes="Appendix field emitted when objective gate produces a signed override.",
    ),
    "model_confidence": _contract(
        field="model_confidence",
        producer="Objective model helper surfaces",
        consumer="Forensic trace only",
        scale=NORMALIZED_CONFIDENCE_0_1,
        numeric_contract="0..1 normalized",
        threshold_family=NONE_THRESHOLD_FAMILY,
        live_authority_status=SHADOW_ONLY,
        allowed_as_direction_confidence=False,
        notes="Appendix field; not a proven live Aurora input.",
    ),
    "active_threshold": _contract(
        field="active_threshold",
        producer="Aurora threshold selection",
        consumer="StrategyGateway trace / decision trace",
        scale=NORMALIZED_CONFIDENCE_0_1,
        numeric_contract="finite signed float",
        threshold_family=AURORA_ADMISSION_THRESHOLD_FAMILY,
        live_authority_status=LIVE_AUTHORITATIVE,
        allowed_as_direction_confidence=False,
        notes="Appendix threshold field, not a confidence.",
    ),
}


def get_score_field_contract(field: str) -> ScoreFieldContract | None:
    return SCORE_FIELD_REGISTRY.get(str(field))


def _normalize_record_value(value: Any) -> Any:
    if value is None or isinstance(value, bool):
        return value
    try:
        return float(value)
    except (TypeError, ValueError):
        return value


def build_score_lineage_record(
    *,
    field: str,
    value: Any,
    producer: str | None = None,
    consumer_stage: str | None = None,
    scale: str | None = None,
    threshold_family: str | None = None,
    live_authority_status: str | None = None,
    compatibility_alias_for: str | None = None,
    post_objective_override: bool = False,
) -> dict[str, Any]:
    contract = get_score_field_contract(field)
    resolved_scale = scale or (contract.scale if contract is not None else None)
    if resolved_scale not in SCORE_SCALE_FAMILIES:
        raise ValueError(f"Unsupported score lineage scale for {field}: {resolved_scale!r}")
    resolved_threshold_family = threshold_family or (
        contract.threshold_family if contract is not None else NONE_THRESHOLD_FAMILY
    )
    if resolved_threshold_family not in THRESHOLD_FAMILIES:
        raise ValueError(
            f"Unsupported score lineage threshold family for {field}: {resolved_threshold_family!r}"
        )
    resolved_authority_status = live_authority_status or (
        contract.live_authority_status if contract is not None else COMPATIBILITY_ONLY
    )
    if resolved_authority_status not in LIVE_AUTHORITY_STATUSES:
        raise ValueError(
            f"Unsupported score lineage authority status for {field}: {resolved_authority_status!r}"
        )
    return {
        "field": str(field),
        "value": _normalize_record_value(value),
        "scale": resolved_scale,
        "producer": producer or (contract.producer if contract is not None else "unknown"),
        "consumer_stage": consumer_stage
        or (contract.consumer if contract is not None else "unknown"),
        "threshold_family": resolved_threshold_family,
        "live_authority_status": resolved_authority_status,
        "compatibility_alias_for": compatibility_alias_for,
        "post_objective_override": bool(post_objective_override),
    }


def build_score_lineage_payload(
    records: list[Mapping[str, Any]] | tuple[Mapping[str, Any], ...],
    *,
    path: str = LIVE_SCORE_LINEAGE_PATH,
) -> dict[str, Any]:
    normalized_records = [
        dict(record) for record in records if isinstance(record, Mapping)
    ]
    return {
        "path": str(path),
        "records": normalized_records,
    }


def extract_score_lineage_records(container: Mapping[str, Any] | None) -> list[Mapping[str, Any]]:
    if not isinstance(container, Mapping):
        return []
    if "records" in container and isinstance(container.get("records"), list):
        return [record for record in container.get("records", []) if isinstance(record, Mapping)]
    score_lineage = container.get("score_lineage")
    if isinstance(score_lineage, Mapping):
        return extract_score_lineage_records(score_lineage)
    return []


def find_score_lineage_record(
    container: Mapping[str, Any] | None,
    field: str,
) -> Mapping[str, Any] | None:
    normalized_field = str(field)
    for record in reversed(extract_score_lineage_records(container)):
        if str(record.get("field")) == normalized_field:
            return record
    return None


def is_signed_score_scale(scale: str | None) -> bool:
    return scale in {
        RAW_SIGNED_LINEAR,
        SIGNED_DECISION_SCORE,
        SIGNED_OBJECTIVE_SCORE,
    }


def is_normalized_confidence_scale(scale: str | None) -> bool:
    return scale in {
        NORMALIZED_CONFIDENCE_0_1,
        GATE_RESOLVED_CONFIDENCE,
    }
