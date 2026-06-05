from __future__ import annotations

import math
from typing import Any, Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field


SCHEMA_VERSION = "1.0.0"
STRATEGY_ID = "md_amr"
AUTHORITY_STATUS = "opinion_only"
DEFAULT_STALE_AFTER_MS = 30_000

EVIDENCE_FIELDS = (
    "sentiment_state",
    "entry_anchor",
    "progress_state",
    "setup_quality",
    "hold_quality",
    "context_validity",
    "obi_close",
    "target_approach_pct",
    "channel_position",
    "channel_width_pct",
    "volatility_z",
    "atr",
    "invalidation",
)


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


def _to_float_or_none(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        value_f = float(value)
    except (TypeError, ValueError):
        return None
    return value_f if math.isfinite(value_f) else None


def _to_int_or_none(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _to_str_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _dict_or_none(value: Any) -> dict[str, Any] | None:
    return dict(value) if isinstance(value, Mapping) else None


def _reason_codes(payload: Mapping[str, Any]) -> list[str]:
    raw = payload.get("reason_codes")
    if isinstance(raw, list):
        return [str(item) for item in raw]
    why_chain = payload.get("why_chain")
    if isinstance(why_chain, list):
        return [str(item) for item in why_chain]
    why = _first_present(payload.get("why"), payload.get("reason_code"))
    if isinstance(why, str) and why:
        return [item.strip() for item in why.split(";") if item.strip()]
    return []


class MDAMREvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    sentiment_state: str | None = None
    entry_anchor: dict[str, Any] | None = None
    progress_state: str | None = None
    setup_quality: float | None = Field(default=None, ge=0.0, le=1.0)
    hold_quality: float | None = Field(default=None, ge=0.0, le=1.0)
    context_validity: float | None = Field(default=None, ge=0.0, le=1.0)
    obi_close: float | None = None
    target_approach_pct: float | None = None
    channel_position: float | None = None
    channel_width_pct: float | None = None
    volatility_z: float | None = None
    atr: float | None = None
    invalidation: dict[str, Any] | None = None


class EvidenceFreshness(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    feature_ts_ms: int | None = Field(default=None, ge=0)
    decision_ts_ms: int | None = Field(default=None, ge=0)
    age_ms: int | None = Field(default=None, ge=0)
    freshness_state: Literal["FRESH", "STALE", "MISSING", "UNKNOWN"]


class Missingness(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    per_field: dict[str, str] = Field(default_factory=dict)


class RegimeContextRef(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    regime_label: str | None = None
    regime_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    basis_tf_sec: int | None = Field(default=None, ge=0)
    regime_age_ms: int | None = Field(default=None, ge=0)


class SourceRefs(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    decision_id: str | None = None
    rid: str | None = None
    trace_id: str | None = None
    source_event: str | None = None


class MDAMRExpertOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0.0"] = SCHEMA_VERSION
    expert_id: str = Field(min_length=1)
    strategy_id: Literal["md_amr"] = STRATEGY_ID
    question_type: Literal["entry", "lifecycle"]
    symbol: str = Field(min_length=1)
    ts_ms: int = Field(ge=0)
    side_opinion: Literal["BUY", "SELL", "NONE", "UNKNOWN"]
    lifecycle_opinion: Literal["HOLD", "PROTECT", "EXIT", "SUPPRESS", "UNKNOWN"] | None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    confidence_source: str = Field(min_length=1)
    horizon: str | None = None
    authority_status: Literal["opinion_only"] = AUTHORITY_STATUS
    md_amr_evidence: MDAMREvidence
    regime_context_ref: RegimeContextRef
    evidence_freshness: EvidenceFreshness
    missingness: Missingness
    invalidates_if: list[str] = Field(default_factory=list)
    reason_codes: list[str] = Field(default_factory=list)
    source_refs: SourceRefs


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
        return EvidenceFreshness(
            feature_ts_ms=feature_ts_ms,
            decision_ts_ms=decision_ts_ms,
            age_ms=None,
            freshness_state="MISSING",
        )
    age_ms = max(0, int(now_ms) - int(basis_ts))
    return EvidenceFreshness(
        feature_ts_ms=feature_ts_ms,
        decision_ts_ms=decision_ts_ms,
        age_ms=age_ms,
        freshness_state="STALE" if age_ms > int(stale_after_ms) else "FRESH",
    )


def extract_md_amr_evidence(payload: Mapping[str, Any]) -> MDAMREvidence:
    trace = _mapping(payload.get("trace"))
    features = _mapping(payload.get("features"))
    liquidity = _mapping(_first_present(payload.get("liquidity"), features.get("liquidity")))
    volatility = _mapping(payload.get("volatility"))
    channel_state = _mapping(payload.get("channel_state"))

    return MDAMREvidence(
        sentiment_state=_to_str_or_none(
            _first_present(payload.get("sentiment_state"), trace.get("sentiment_state"))
        ),
        entry_anchor=_dict_or_none(
            _first_present(payload.get("entry_anchor"), trace.get("entry_anchor"))
        ),
        progress_state=_to_str_or_none(
            _first_present(payload.get("progress_state"), trace.get("progress_state"))
        ),
        setup_quality=_to_float_or_none(
            _first_present(payload.get("setup_quality"), trace.get("setup_quality"))
        ),
        hold_quality=_to_float_or_none(
            _first_present(payload.get("hold_quality"), trace.get("hold_quality"))
        ),
        context_validity=_to_float_or_none(
            _first_present(payload.get("context_validity"), trace.get("context_validity"))
        ),
        obi_close=_to_float_or_none(
            _first_present(payload.get("obi_close"), liquidity.get("obi_close"), features.get("obi_close"))
        ),
        target_approach_pct=_to_float_or_none(
            _first_present(payload.get("target_approach_pct"), trace.get("target_approach_pct"))
        ),
        channel_position=_to_float_or_none(
            _first_present(payload.get("channel_position"), trace.get("channel_position"))
        ),
        channel_width_pct=_to_float_or_none(
            _first_present(
                payload.get("channel_width_pct"),
                trace.get("channel_width_pct"),
                channel_state.get("channel_width_pct"),
            )
        ),
        volatility_z=_to_float_or_none(
            _first_present(
                payload.get("volatility_z"),
                payload.get("atr_zscore"),
                trace.get("atr_zscore"),
            )
        ),
        atr=_to_float_or_none(
            _first_present(payload.get("atr"), volatility.get("atr_14"), volatility.get("atr"))
        ),
        invalidation=_dict_or_none(
            _first_present(payload.get("invalidation"), trace.get("invalidation"))
        ),
    )


def build_missingness(evidence: MDAMREvidence) -> Missingness:
    dumped = evidence.model_dump()
    return Missingness(
        per_field={
            f"md_amr_evidence.{field}": "MISSING"
            for field in EVIDENCE_FIELDS
            if dumped.get(field) is None
        }
    )


def _side_opinion(payload: Mapping[str, Any]) -> str:
    side = _to_str_or_none(_first_present(payload.get("side"), payload.get("side_opinion")))
    if side is None:
        return "UNKNOWN"
    side_norm = side.upper()
    if side_norm in {"BUY", "SELL", "NONE", "UNKNOWN"}:
        return side_norm
    if side_norm == "LONG":
        return "BUY"
    if side_norm == "SHORT":
        return "SELL"
    return "UNKNOWN"


def _question_and_lifecycle(
    payload: Mapping[str, Any],
) -> tuple[Literal["entry", "lifecycle"], str | None]:
    explicit_question = _to_str_or_none(payload.get("question_type"))
    intent = _to_str_or_none(_first_present(payload.get("intent_kind"), payload.get("lifecycle_intent")))
    lifecycle = _to_str_or_none(payload.get("lifecycle_opinion"))
    if lifecycle is not None:
        lifecycle_norm = lifecycle.upper()
        if lifecycle_norm in {"HOLD", "PROTECT", "EXIT", "SUPPRESS", "UNKNOWN"}:
            return "lifecycle", lifecycle_norm
    if intent is not None:
        intent_norm = intent.upper()
        if intent_norm == "ENTRY":
            return "entry", None
        if intent_norm in {"FULL_CLOSE", "PARTIAL_CLOSE", "EXIT"}:
            return "lifecycle", "EXIT"
        if intent_norm in {"HOLD", "PROTECT", "SUPPRESS"}:
            return "lifecycle", intent_norm
        return "lifecycle", "UNKNOWN"
    if explicit_question == "lifecycle":
        return "lifecycle", "UNKNOWN"
    return "entry", None


def _confidence(payload: Mapping[str, Any]) -> tuple[float | None, str]:
    strategy_confidence = _to_float_or_none(payload.get("strategy_confidence"))
    if strategy_confidence is not None:
        return strategy_confidence, "explicit_strategy_confidence"
    explicit_confidence = _to_float_or_none(payload.get("confidence"))
    if explicit_confidence is not None:
        return explicit_confidence, "explicit_strategy_confidence"
    conf_ratio = _to_float_or_none(
        _first_present(payload.get("conf_ratio"), _nested_get(payload, "trace", "conf_ratio"))
    )
    if conf_ratio is not None:
        return conf_ratio, "explicit_conf_ratio"
    return None, "not_available"


def _regime_context_ref(payload: Mapping[str, Any], decision_ts_ms: int | None) -> RegimeContextRef:
    regime_ctx = _mapping(payload.get("regime_ctx"))
    regime_ts_ms = _to_int_or_none(
        _first_present(regime_ctx.get("regime_ts_ms"), regime_ctx.get("regime_event_ts_ms"))
    )
    regime_age_ms = None
    if regime_ts_ms is not None and decision_ts_ms is not None:
        regime_age_ms = max(0, int(decision_ts_ms) - int(regime_ts_ms))
    return RegimeContextRef(
        regime_label=_to_str_or_none(
            _first_present(
                regime_ctx.get("regime"),
                regime_ctx.get("regime_label"),
                payload.get("regime"),
            )
        ),
        regime_confidence=_to_float_or_none(
            _first_present(regime_ctx.get("confidence"), payload.get("regime_confidence"))
        ),
        basis_tf_sec=_to_int_or_none(regime_ctx.get("basis_tf_sec")),
        regime_age_ms=regime_age_ms,
    )


def build_md_amr_expert_output(
    payload: Mapping[str, Any],
    *,
    now_ms: int | None = None,
    stale_after_ms: int = DEFAULT_STALE_AFTER_MS,
) -> MDAMRExpertOutput:
    event = _mapping(payload)
    symbol = _to_str_or_none(event.get("symbol"))
    ts_ms = _to_int_or_none(_first_present(event.get("ts_ms"), event.get("bar_close_ts")))
    if symbol is None:
        raise ValueError("MDAMRExpertOutput requires source-backed symbol")
    if ts_ms is None:
        raise ValueError("MDAMRExpertOutput requires source-backed ts_ms")

    question_type, lifecycle_opinion = _question_and_lifecycle(event)
    evidence = extract_md_amr_evidence(event)
    confidence, confidence_source = _confidence(event)
    feature_ts_ms = _to_int_or_none(
        _first_present(
            event.get("feature_ts_ms"),
            _nested_get(event, "bar_identity", "bar_end_ts_ms"),
            event.get("bar_close_ts"),
        )
    )
    decision_ts_ms = _to_int_or_none(event.get("ts_ms"))

    return MDAMRExpertOutput(
        expert_id="md_amr.native_v1",
        question_type=question_type,
        symbol=symbol,
        ts_ms=ts_ms,
        side_opinion=_side_opinion(event),  # type: ignore[arg-type]
        lifecycle_opinion=lifecycle_opinion,  # type: ignore[arg-type]
        confidence=confidence,
        confidence_source=confidence_source,
        horizon=_to_str_or_none(event.get("horizon")),
        md_amr_evidence=evidence,
        regime_context_ref=_regime_context_ref(event, decision_ts_ms),
        evidence_freshness=classify_freshness(
            feature_ts_ms,
            decision_ts_ms,
            now_ms,
            stale_after_ms,
        ),
        missingness=build_missingness(evidence),
        invalidates_if=[
            str(item) for item in event.get("invalidates_if", [])
        ] if isinstance(event.get("invalidates_if"), list) else [],
        reason_codes=_reason_codes(event),
        source_refs=SourceRefs(
            decision_id=_to_str_or_none(event.get("decision_id")),
            rid=_to_str_or_none(event.get("rid")),
            trace_id=_to_str_or_none(event.get("trace_id")),
            source_event=_to_str_or_none(event.get("source_event")),
        ),
    )
