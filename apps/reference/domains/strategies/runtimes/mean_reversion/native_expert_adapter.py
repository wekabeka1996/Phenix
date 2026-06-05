from __future__ import annotations

import math
from typing import Any, Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field


SCHEMA_VERSION = "1.0.0"
STRATEGY_ID = "mean_reversion"
QUESTION_TYPE = "entry"
AUTHORITY_STATUS = "opinion_only"
DEFAULT_STALE_AFTER_MS = 30_000

EVIDENCE_FIELDS = (
    "rsi",
    "pct_b",
    "bb_width",
    "band_upper",
    "band_mid",
    "band_lower",
    "atr",
    "funding_rate",
    "funding_cost",
    "entry_boundary",
    "expected_reversion_target",
    "invalidation_level",
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


def _reason_codes(payload: Mapping[str, Any]) -> list[str]:
    raw = payload.get("reason_codes")
    if isinstance(raw, list):
        return [str(item) for item in raw]
    why_chain = payload.get("why_chain")
    if isinstance(why_chain, list):
        return [str(item) for item in why_chain]
    why = payload.get("why")
    if isinstance(why, str) and why:
        return [item.strip() for item in why.split(";") if item.strip()]
    return []


class MeanReversionEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    rsi: float | None = None
    pct_b: float | None = None
    bb_width: float | None = None
    band_upper: float | None = None
    band_mid: float | None = None
    band_lower: float | None = None
    atr: float | None = None
    funding_rate: float | None = None
    funding_cost: float | None = None
    entry_boundary: float | None = None
    expected_reversion_target: float | None = None
    invalidation_level: float | None = None


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


class MeanReversionExpertOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0.0"] = SCHEMA_VERSION
    expert_id: str = Field(min_length=1)
    strategy_id: Literal["mean_reversion"] = STRATEGY_ID
    question_type: Literal["entry"] = QUESTION_TYPE
    symbol: str = Field(min_length=1)
    ts_ms: int = Field(ge=0)
    side_opinion: Literal["BUY", "SELL", "NONE", "UNKNOWN"]
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    confidence_source: str = Field(min_length=1)
    horizon: str | None = None
    authority_status: Literal["opinion_only"] = AUTHORITY_STATUS
    mean_reversion_evidence: MeanReversionEvidence
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


def extract_mean_reversion_evidence(payload: Mapping[str, Any]) -> MeanReversionEvidence:
    features = _mapping(payload.get("features"))
    bb = _mapping(_first_present(payload.get("bb"), payload.get("bands")))
    price_ctx = _mapping(payload.get("price_ctx"))
    volatility = _mapping(payload.get("volatility"))
    funding = _mapping(payload.get("funding"))

    return MeanReversionEvidence(
        rsi=_to_float_or_none(_first_present(payload.get("rsi"), features.get("rsi"))),
        pct_b=_to_float_or_none(_first_present(payload.get("pct_b"), bb.get("pct_b"))),
        bb_width=_to_float_or_none(
            _first_present(payload.get("bb_width"), bb.get("width"))
        ),
        band_upper=_to_float_or_none(
            _first_present(payload.get("band_upper"), bb.get("upper"))
        ),
        band_mid=_to_float_or_none(
            _first_present(payload.get("band_mid"), bb.get("mid"))
        ),
        band_lower=_to_float_or_none(
            _first_present(payload.get("band_lower"), bb.get("lower"))
        ),
        atr=_to_float_or_none(
            _first_present(payload.get("atr"), volatility.get("atr"), volatility.get("atr_14"))
        ),
        funding_rate=_to_float_or_none(
            _first_present(payload.get("funding_rate"), funding.get("rate"))
        ),
        funding_cost=_to_float_or_none(
            _first_present(payload.get("funding_cost"), funding.get("cost"))
        ),
        entry_boundary=_to_float_or_none(
            _first_present(payload.get("entry_boundary"), price_ctx.get("entry_price"))
        ),
        expected_reversion_target=_to_float_or_none(
            _first_present(
                payload.get("expected_reversion_target"),
                price_ctx.get("target_price"),
            )
        ),
        invalidation_level=_to_float_or_none(
            _first_present(payload.get("invalidation_level"), price_ctx.get("stop_price"))
        ),
    )


def build_missingness(evidence: MeanReversionEvidence) -> Missingness:
    dumped = evidence.model_dump()
    return Missingness(
        per_field={
            f"mean_reversion_evidence.{field}": "MISSING"
            for field in EVIDENCE_FIELDS
            if dumped.get(field) is None
        }
    )


def _side_opinion(payload: Mapping[str, Any], reason_codes: list[str]) -> str:
    side = _to_str_or_none(_first_present(payload.get("side"), payload.get("side_opinion")))
    if side is not None:
        side_norm = side.upper()
        if side_norm in {"BUY", "SELL", "NONE", "UNKNOWN"}:
            return side_norm
        if side_norm == "LONG":
            reason_codes.append("SIDE_FROM_MR_SIGNAL_DIRECTION")
            return "BUY"
        if side_norm == "SHORT":
            reason_codes.append("SIDE_FROM_MR_SIGNAL_DIRECTION")
            return "SELL"
    signal_type = _to_str_or_none(payload.get("signal_type"))
    if signal_type is not None:
        signal_norm = signal_type.upper()
        if signal_norm == "LONG":
            reason_codes.append("SIDE_FROM_MR_SIGNAL_TYPE")
            return "BUY"
        if signal_norm == "SHORT":
            reason_codes.append("SIDE_FROM_MR_SIGNAL_TYPE")
            return "SELL"
        if signal_norm == "NEUTRAL":
            return "NONE"
    return "UNKNOWN"


def _confidence(payload: Mapping[str, Any]) -> tuple[float | None, str]:
    strategy_confidence = _to_float_or_none(payload.get("strategy_confidence"))
    if strategy_confidence is not None:
        return strategy_confidence, "explicit_strategy_confidence"
    signal_confidence = _to_float_or_none(payload.get("confidence"))
    if signal_confidence is not None:
        return signal_confidence, "explicit_signal_confidence"
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
        regime_confidence=_to_float_or_none(regime_ctx.get("confidence")),
        basis_tf_sec=_to_int_or_none(regime_ctx.get("basis_tf_sec")),
        regime_age_ms=regime_age_ms,
    )


def build_mean_reversion_expert_output(
    payload: Mapping[str, Any],
    *,
    now_ms: int | None = None,
    stale_after_ms: int = DEFAULT_STALE_AFTER_MS,
) -> MeanReversionExpertOutput:
    event = _mapping(payload)
    symbol = _to_str_or_none(event.get("symbol"))
    ts_ms = _to_int_or_none(_first_present(event.get("ts_ms"), event.get("bar_close_ts")))
    if symbol is None:
        raise ValueError("MeanReversionExpertOutput requires source-backed symbol")
    if ts_ms is None:
        raise ValueError("MeanReversionExpertOutput requires source-backed ts_ms")

    reason_codes = _reason_codes(event)
    evidence = extract_mean_reversion_evidence(event)
    confidence, confidence_source = _confidence(event)
    feature_ts_ms = _to_int_or_none(
        _first_present(
            event.get("feature_ts_ms"),
            _nested_get(event, "bar_identity", "bar_end_ts_ms"),
            event.get("bar_close_ts"),
        )
    )
    decision_ts_ms = _to_int_or_none(event.get("ts_ms"))
    return MeanReversionExpertOutput(
        expert_id="mean_reversion.native_v1",
        symbol=symbol,
        ts_ms=ts_ms,
        side_opinion=_side_opinion(event, reason_codes),  # type: ignore[arg-type]
        confidence=confidence,
        confidence_source=confidence_source,
        horizon=_to_str_or_none(event.get("horizon")),
        mean_reversion_evidence=evidence,
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
        reason_codes=reason_codes,
        source_refs=SourceRefs(
            decision_id=_to_str_or_none(event.get("decision_id")),
            rid=_to_str_or_none(event.get("rid")),
            trace_id=_to_str_or_none(event.get("trace_id")),
            source_event=_to_str_or_none(event.get("source_event")),
        ),
    )
