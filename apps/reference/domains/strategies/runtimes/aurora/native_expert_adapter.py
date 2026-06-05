from __future__ import annotations

import math
from copy import deepcopy
from typing import Any, Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field, model_validator


SCHEMA_VERSION = "1.0.0"
STRATEGY_ID = "aurora"
QUESTION_TYPE = "entry"
AUTHORITY_STATUS = "opinion_only"
LEGACY_SCORE_TRACE_AUTHORITY_NOTE = "legacy_trace_not_judge_canonical"
DEFAULT_STALE_AFTER_MS = 30_000

MICROSTRUCTURE_FIELDS = (
    "obi",
    "tfi",
    "absorption",
    "liquidity_kappa",
    "spread_bps",
    "macro_resid",
    "delta_price",
    "volatility_state",
    "large_trade_imbalance",
)


def _to_float_or_none(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        value_f = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(value_f):
        return None
    return value_f


def _to_int_or_none(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        value_i = int(value)
    except (TypeError, ValueError):
        return None
    return value_i


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _nested_get(container: Mapping[str, Any], *path: str) -> Any:
    current: Any = container
    for key in path:
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
    return current


def _first_present(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


class MicrostructureEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    obi: float | None = None
    tfi: float | None = None
    absorption: float | None = None
    liquidity_kappa: float | None = None
    spread_bps: float | None = None
    macro_resid: float | None = None
    delta_price: float | None = None
    volatility_state: float | None = None
    large_trade_imbalance: float | None = None


class EvidenceFreshness(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    feature_ts_ms: int | None = None
    decision_ts_ms: int | None = None
    age_ms: int | None = None
    freshness_state: Literal["FRESH", "STALE", "MISSING", "UNKNOWN"]


class Missingness(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    per_field: dict[str, str] = Field(default_factory=dict)


class RegimeContextRef(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    regime_label: str | None = None
    regime_confidence: float | None = None
    basis_tf_sec: int | None = None
    regime_age_ms: int | None = None


class LegacyScoreTrace(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    pillar_sum: float | None = None
    raw_score: float | None = None
    decision_score: float | None = None
    sizing_score: float | None = None
    admission_mode: str | None = None
    sizing_mode: str | None = None
    score_lineage_present: bool
    score_trace_authority_note: Literal["legacy_trace_not_judge_canonical"] = (
        LEGACY_SCORE_TRACE_AUTHORITY_NOTE
    )


class SourceRefs(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    decision_id: str | None = None
    rid: str | None = None
    trace_id: str | None = None
    source_event: str | None = None


class AuroraExpertOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0.0"] = SCHEMA_VERSION
    expert_id: str = Field(min_length=1)
    strategy_id: Literal["aurora"] = STRATEGY_ID
    question_type: Literal["entry"] = QUESTION_TYPE
    symbol: str = Field(min_length=1)
    ts_ms: int = Field(ge=0)
    side_opinion: Literal["BUY", "SELL", "NONE", "UNKNOWN"]
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    confidence_source: str = Field(min_length=1)
    horizon: str | None = None
    authority_status: Literal["opinion_only"] = AUTHORITY_STATUS
    microstructure_evidence: MicrostructureEvidence
    evidence_freshness: EvidenceFreshness
    missingness: Missingness
    regime_context_ref: RegimeContextRef
    legacy_score_trace: LegacyScoreTrace
    invalidates_if: list[str] = Field(default_factory=list)
    reason_codes: list[str] = Field(default_factory=list)
    source_refs: SourceRefs

    @model_validator(mode="after")
    def _legacy_trace_is_not_primary_microstructure(self) -> "AuroraExpertOutput":
        dumped = self.microstructure_evidence.model_dump()
        forbidden = {"pillar_sum", "score", "signal_score", "final_score"}
        overlap = forbidden.intersection(dumped)
        if overlap:
            raise ValueError(
                f"legacy score aliases are not microstructure evidence: {sorted(overlap)}"
            )
        return self


def extract_microstructure_evidence(payload: Mapping[str, Any]) -> MicrostructureEvidence:
    features = _mapping(payload.get("features"))
    scoring = _mapping(payload.get("scoring"))
    values: dict[str, float | None] = {}
    for field in MICROSTRUCTURE_FIELDS:
        values[field] = _to_float_or_none(
            _first_present(
                payload.get(field),
                features.get(field),
                scoring.get(field),
                _nested_get(payload, "liquidity", field),
                _nested_get(payload, "volatility", field),
            )
        )
    return MicrostructureEvidence(**values)


def extract_legacy_score_trace(payload: Mapping[str, Any]) -> LegacyScoreTrace:
    scoring = _mapping(payload.get("scoring"))
    psi = _mapping(scoring.get("psi_vector"))
    score_lineage = scoring.get("score_lineage")
    return LegacyScoreTrace(
        pillar_sum=_to_float_or_none(_first_present(
            scoring.get("pillar_sum"),
            psi.get("s_linear"),
            _nested_get(payload, "features", "pillar_sum"),
        )),
        raw_score=_to_float_or_none(scoring.get("raw_score")),
        decision_score=_to_float_or_none(scoring.get("decision_score")),
        sizing_score=_to_float_or_none(scoring.get("sizing_score")),
        admission_mode=(
            str(scoring.get("admission_mode"))
            if scoring.get("admission_mode") is not None
            else None
        ),
        sizing_mode=(
            str(scoring.get("sizing_mode"))
            if scoring.get("sizing_mode") is not None
            else None
        ),
        score_lineage_present=isinstance(score_lineage, Mapping)
        and bool(score_lineage.get("records")),
    )


def classify_freshness(
    feature_ts_ms: int | None,
    decision_ts_ms: int | None,
    now_ms: int | None,
    stale_after_ms: int = DEFAULT_STALE_AFTER_MS,
) -> EvidenceFreshness:
    if feature_ts_ms is None and decision_ts_ms is None:
        return EvidenceFreshness(
            feature_ts_ms=None,
            decision_ts_ms=None,
            age_ms=None,
            freshness_state="MISSING",
        )
    if now_ms is None:
        return EvidenceFreshness(
            feature_ts_ms=feature_ts_ms,
            decision_ts_ms=decision_ts_ms,
            age_ms=None,
            freshness_state="UNKNOWN",
        )
    basis_ts = feature_ts_ms if feature_ts_ms is not None else decision_ts_ms
    if basis_ts is None:
        age_ms = None
        state: Literal["FRESH", "STALE", "MISSING", "UNKNOWN"] = "MISSING"
    else:
        age_ms = max(0, int(now_ms) - int(basis_ts))
        state = "STALE" if age_ms > int(stale_after_ms) else "FRESH"
    return EvidenceFreshness(
        feature_ts_ms=feature_ts_ms,
        decision_ts_ms=decision_ts_ms,
        age_ms=age_ms,
        freshness_state=state,
    )


def build_missingness(
    evidence: MicrostructureEvidence,
    required_field_names: tuple[str, ...] = MICROSTRUCTURE_FIELDS,
) -> Missingness:
    dumped = evidence.model_dump()
    missing: dict[str, str] = {}
    for field in required_field_names:
        if dumped.get(field) is None:
            missing[field] = "MISSING"
    return Missingness(per_field=missing)


def _side_from_payload(payload: Mapping[str, Any], legacy: LegacyScoreTrace) -> tuple[str, list[str]]:
    side_raw = payload.get("side")
    if side_raw is not None:
        side = str(side_raw).strip().upper()
        if side in {"BUY", "SELL"}:
            return side, []
        if side in {"NONE", "NEUTRAL", ""}:
            return "NONE", []
    if legacy.decision_score is not None:
        if legacy.decision_score > 0:
            return "BUY", ["SIDE_FROM_LEGACY_DECISION_SCORE"]
        if legacy.decision_score < 0:
            return "SELL", ["SIDE_FROM_LEGACY_DECISION_SCORE"]
        return "NONE", ["SIDE_FROM_LEGACY_DECISION_SCORE"]
    return "UNKNOWN", []


def _confidence_from_payload(
    payload: Mapping[str, Any],
    legacy: LegacyScoreTrace,
) -> tuple[float | None, str]:
    explicit = _to_float_or_none(
        _first_present(
            payload.get("strategy_confidence"),
            _nested_get(payload, "scoring", "strategy_confidence"),
            _nested_get(payload, "objective", "strategy_confidence"),
        )
    )
    if explicit is not None:
        return max(0.0, min(1.0, explicit)), "explicit_strategy_confidence"
    if legacy.decision_score is not None:
        return max(0.0, min(1.0, abs(legacy.decision_score))), "decision_score_abs_legacy_trace"
    return None, "not_available"


def _regime_context(payload: Mapping[str, Any]) -> RegimeContextRef:
    regime_ctx = _mapping(payload.get("regime_ctx"))
    return RegimeContextRef(
        regime_label=(
            str(_first_present(regime_ctx.get("regime"), payload.get("regime")))
            if _first_present(regime_ctx.get("regime"), payload.get("regime")) is not None
            else None
        ),
        regime_confidence=_to_float_or_none(regime_ctx.get("confidence")),
        basis_tf_sec=_to_int_or_none(_first_present(payload.get("tf_sec"), regime_ctx.get("basis_tf_sec"))),
        regime_age_ms=(
            int(float(regime_ctx["regime_age_sec"]) * 1000)
            if regime_ctx.get("regime_age_sec") is not None
            else _to_int_or_none(regime_ctx.get("regime_age_ms"))
        ),
    )


def _source_refs(payload: Mapping[str, Any]) -> SourceRefs:
    scoring = _mapping(payload.get("scoring"))
    objective = _mapping(scoring.get("objective"))
    return SourceRefs(
        decision_id=(
            str(payload.get("decision_id"))
            if payload.get("decision_id") is not None
            else None
        ),
        rid=str(payload.get("rid")) if payload.get("rid") is not None else None,
        trace_id=(
            str(_first_present(payload.get("trace_id"), objective.get("trace_id")))
            if _first_present(payload.get("trace_id"), objective.get("trace_id")) is not None
            else None
        ),
        source_event=(
            str(payload.get("source_event"))
            if payload.get("source_event") is not None
            else None
        ),
    )


def build_aurora_expert_output(
    payload: Mapping[str, Any],
    *,
    now_ms: int | None = None,
    stale_after_ms: int = DEFAULT_STALE_AFTER_MS,
) -> AuroraExpertOutput:
    payload_copy = deepcopy(dict(payload))
    legacy = extract_legacy_score_trace(payload_copy)
    evidence = extract_microstructure_evidence(payload_copy)
    missingness = build_missingness(evidence)
    decision_ts_ms = _to_int_or_none(payload_copy.get("ts_ms"))
    feature_ts_ms = _to_int_or_none(
        _first_present(
            _nested_get(payload_copy, "features", "ts_ms"),
            _nested_get(payload_copy, "features", "ts"),
            payload_copy.get("features_ts_ms"),
        )
    )
    side_opinion, side_reason_codes = _side_from_payload(payload_copy, legacy)
    confidence, confidence_source = _confidence_from_payload(payload_copy, legacy)
    reason_codes = list(side_reason_codes)
    if missingness.per_field:
        reason_codes.append("MICROSTRUCTURE_FIELDS_MISSING")
    if confidence_source == "decision_score_abs_legacy_trace":
        reason_codes.append("CONFIDENCE_FROM_LEGACY_DECISION_SCORE")
    return AuroraExpertOutput(
        expert_id="aurora.microstructure_native_v1",
        symbol=str(payload_copy.get("symbol") or ""),
        ts_ms=decision_ts_ms if decision_ts_ms is not None else 0,
        side_opinion=side_opinion,  # type: ignore[arg-type]
        confidence=confidence,
        confidence_source=confidence_source,
        horizon=(
            str(payload_copy.get("horizon"))
            if payload_copy.get("horizon") is not None
            else None
        ),
        microstructure_evidence=evidence,
        evidence_freshness=classify_freshness(
            feature_ts_ms,
            decision_ts_ms,
            now_ms,
            stale_after_ms,
        ),
        missingness=missingness,
        regime_context_ref=_regime_context(payload_copy),
        legacy_score_trace=legacy,
        invalidates_if=list(payload_copy.get("invalidates_if") or []),
        reason_codes=reason_codes,
        source_refs=_source_refs(payload_copy),
    )
