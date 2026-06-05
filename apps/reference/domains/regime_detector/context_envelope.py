from __future__ import annotations

import math
from typing import Any, Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field


SCHEMA_VERSION = "1.0.0"
AUTHORITY_STATUS = "context_only"
INTENSITY_AUTHORITY_NOTE = "context_intensity_not_entry_authority"

FORBIDDEN_SCORE_FIELDS = {
    "score",
    "raw_score",
    "decision_score",
    "sizing_score",
    "signal_score",
    "final_score",
    "pillar_sum",
}


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
    if not math.isfinite(value_f):
        return None
    return value_f


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


def _reason_codes_from_payload(payload: Mapping[str, Any]) -> list[str]:
    reason_codes = payload.get("reason_codes")
    if isinstance(reason_codes, list):
        return [str(item) for item in reason_codes]

    reasons: list[str] = []
    reason_summary = payload.get("reason_summary")
    if isinstance(reason_summary, str) and reason_summary:
        reasons.extend(
            item.strip() for item in reason_summary.split(";") if item.strip()
        )

    data_quality = _mapping(payload.get("data_quality"))
    for key in ("drops", "notes"):
        values = data_quality.get(key)
        if isinstance(values, list):
            reasons.extend(f"{key}:{item}" for item in values)

    warmup = _mapping(payload.get("warmup"))
    warmup_reasons = warmup.get("reasons")
    if isinstance(warmup_reasons, list):
        reasons.extend(f"warmup:{item}" for item in warmup_reasons)
    return reasons


class RegimeInfo(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    label: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    basis_tf_sec: int | None = Field(default=None, ge=0)
    source: str | None = None


class RegimeTiming(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    regime_ts_ms: int | None = Field(default=None, ge=0)
    decision_ts_ms: int | None = Field(default=None, ge=0)
    age_ms: int | None = Field(default=None, ge=0)
    freshness_state: Literal["FRESH", "STALE", "MISSING", "UNKNOWN"]


class RegimeTransition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    state: Literal["STABLE", "PENDING", "TRANSITIONING", "UNKNOWN"]
    hysteresis_bars: int | None = Field(default=None, ge=0)
    bars_in_regime: int | None = Field(default=None, ge=0)
    switch_count_window: int | None = Field(default=None, ge=0)


class RegimeIntensity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    enabled: bool
    value: float | None = None
    method: str | None = None
    authority_note: Literal["context_intensity_not_entry_authority"] = (
        INTENSITY_AUTHORITY_NOTE
    )


class RegimeDiagnostics(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    liveness_state: str | None = None
    stress_state: str | None = None
    reason_codes: list[str] = Field(default_factory=list)


class RegimeMissingness(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    per_field: dict[str, str] = Field(default_factory=dict)


class RegimeSourceRefs(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    rid: str | None = None
    trace_id: str | None = None
    bar_close_ts_ms: int | None = Field(default=None, ge=0)


class RegimeContextEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0.0"] = SCHEMA_VERSION
    context_id: str | None = None
    symbol: str = Field(min_length=1)
    ts_ms: int = Field(ge=0)
    source_event: str | None = None
    authority_status: Literal["context_only"] = AUTHORITY_STATUS
    regime: RegimeInfo
    timing: RegimeTiming
    transition: RegimeTransition
    intensity: RegimeIntensity
    diagnostics: RegimeDiagnostics
    missingness: RegimeMissingness
    source_refs: RegimeSourceRefs


def classify_regime_freshness(
    regime_ts_ms: int | None,
    decision_ts_ms: int | None,
    freshness_threshold_ms: int | None = None,
) -> RegimeTiming:
    if regime_ts_ms is None:
        return RegimeTiming(
            regime_ts_ms=None,
            decision_ts_ms=decision_ts_ms,
            age_ms=None,
            freshness_state="MISSING",
        )

    if decision_ts_ms is None:
        return RegimeTiming(
            regime_ts_ms=regime_ts_ms,
            decision_ts_ms=None,
            age_ms=None,
            freshness_state="UNKNOWN",
        )

    age_ms = max(0, int(decision_ts_ms) - int(regime_ts_ms))
    if freshness_threshold_ms is None:
        state: Literal["FRESH", "STALE", "MISSING", "UNKNOWN"] = "UNKNOWN"
    else:
        state = "STALE" if age_ms > int(freshness_threshold_ms) else "FRESH"
    return RegimeTiming(
        regime_ts_ms=regime_ts_ms,
        decision_ts_ms=decision_ts_ms,
        age_ms=age_ms,
        freshness_state=state,
    )


def classify_transition_state(payload: Mapping[str, Any]) -> RegimeTransition:
    transition = _mapping(payload.get("transition"))
    explicit = _first_present(payload.get("transition_state"), transition.get("state"))
    hysteresis_bars = _to_int_or_none(
        _first_present(payload.get("hysteresis_bars"), transition.get("hysteresis_bars"))
    )
    bars_in_regime = _to_int_or_none(
        _first_present(
            payload.get("bars_in_regime"),
            payload.get("hysteresis_confirm_count"),
            transition.get("bars_in_regime"),
        )
    )
    switch_count_window = _to_int_or_none(
        _first_present(
            payload.get("switch_count_window"),
            transition.get("switch_count_window"),
        )
    )

    state: Literal["STABLE", "PENDING", "TRANSITIONING", "UNKNOWN"]
    if explicit is not None:
        raw_state = str(explicit).strip().upper()
        state = raw_state if raw_state in {"STABLE", "PENDING", "TRANSITIONING"} else "UNKNOWN"  # type: ignore[assignment]
    elif any(key in payload for key in ("changed", "carried_previous_stable")):
        if bool(payload.get("changed")):
            state = "TRANSITIONING"
        elif bool(payload.get("carried_previous_stable")):
            state = "PENDING"
        else:
            state = "STABLE"
    else:
        state = "UNKNOWN"

    return RegimeTransition(
        state=state,
        hysteresis_bars=hysteresis_bars,
        bars_in_regime=bars_in_regime,
        switch_count_window=switch_count_window,
    )


def extract_regime_diagnostics(payload: Mapping[str, Any]) -> RegimeDiagnostics:
    warmup = _mapping(payload.get("warmup"))
    diagnostics = _mapping(payload.get("diagnostics"))
    rd_diag = _mapping(diagnostics.get("rd"))
    data_quality = _mapping(payload.get("data_quality"))

    liveness_state = _to_str_or_none(
        _first_present(
            payload.get("liveness_state"),
            "lagging" if rd_diag.get("rd_lagging_expected_fe_basis_cadence") is True else None,
            "full_ready" if warmup.get("full_ready") is True else None,
        )
    )
    stress_state = _to_str_or_none(
        _first_present(
            payload.get("stress_state"),
            "storm_rejected" if payload.get("storm_rejected") is True else None,
        )
    )

    reason_codes = _reason_codes_from_payload(payload)
    drops = data_quality.get("drops")
    if isinstance(drops, list) and drops and "data_quality_drops" not in reason_codes:
        reason_codes.append("data_quality_drops")

    return RegimeDiagnostics(
        liveness_state=liveness_state,
        stress_state=stress_state,
        reason_codes=reason_codes,
    )


def _extract_intensity(payload: Mapping[str, Any]) -> RegimeIntensity:
    intensity = _mapping(payload.get("intensity"))
    value = _to_float_or_none(
        _first_present(
            payload.get("intensity_score"),
            payload.get("regime_intensity"),
            intensity.get("value"),
        )
    )
    method = _to_str_or_none(
        _first_present(payload.get("intensity_method"), intensity.get("method"))
    )
    return RegimeIntensity(enabled=value is not None, value=value, method=method)


def build_regime_missingness(
    *,
    regime: RegimeInfo,
    timing: RegimeTiming,
    transition: RegimeTransition,
    intensity: RegimeIntensity,
    diagnostics: RegimeDiagnostics,
    source_refs: RegimeSourceRefs,
) -> RegimeMissingness:
    missing: dict[str, str] = {}
    checks = {
        "regime.label": regime.label,
        "regime.confidence": regime.confidence,
        "regime.basis_tf_sec": regime.basis_tf_sec,
        "regime.source": regime.source,
        "timing.regime_ts_ms": timing.regime_ts_ms,
        "timing.decision_ts_ms": timing.decision_ts_ms,
        "timing.age_ms": timing.age_ms,
        "transition.state": None if transition.state == "UNKNOWN" else transition.state,
        "transition.hysteresis_bars": transition.hysteresis_bars,
        "transition.bars_in_regime": transition.bars_in_regime,
        "transition.switch_count_window": transition.switch_count_window,
        "intensity.value": intensity.value,
        "intensity.method": intensity.method,
        "diagnostics.liveness_state": diagnostics.liveness_state,
        "diagnostics.stress_state": diagnostics.stress_state,
        "source_refs.rid": source_refs.rid,
        "source_refs.trace_id": source_refs.trace_id,
        "source_refs.bar_close_ts_ms": source_refs.bar_close_ts_ms,
    }
    for field, value in checks.items():
        if value is None:
            missing[field] = "MISSING"
    return RegimeMissingness(per_field=missing)


def build_regime_context_envelope(
    payload: Mapping[str, Any],
    *,
    decision_ts_ms: int | None = None,
    freshness_threshold_ms: int | None = None,
) -> RegimeContextEnvelope:
    event = _mapping(payload)
    symbol = _to_str_or_none(event.get("symbol"))
    ts_ms = _to_int_or_none(_first_present(event.get("ts_ms"), event.get("ts")))
    if symbol is None:
        raise ValueError("RegimeContextEnvelope requires source-backed symbol")
    if ts_ms is None:
        raise ValueError("RegimeContextEnvelope requires source-backed ts_ms or ts")

    regime_ts_ms = _to_int_or_none(
        _first_present(
            event.get("regime_event_ts_ms"),
            event.get("ts_ms"),
            event.get("ts"),
            event.get("bar_close_ts_ms"),
        )
    )
    confidence = _to_float_or_none(
        _first_present(event.get("confidence"), event.get("stable_confidence"))
    )
    basis_tf_sec = _to_int_or_none(event.get("basis_tf_sec"))
    source_refs = RegimeSourceRefs(
        rid=_to_str_or_none(event.get("rid")),
        trace_id=_to_str_or_none(event.get("trace_id")),
        bar_close_ts_ms=_to_int_or_none(event.get("bar_close_ts_ms")),
    )
    regime = RegimeInfo(
        label=_to_str_or_none(_first_present(event.get("regime"), event.get("regime_label"))),
        confidence=confidence,
        basis_tf_sec=basis_tf_sec,
        source=_to_str_or_none(event.get("source_model")),
    )
    timing = classify_regime_freshness(
        regime_ts_ms,
        _to_int_or_none(decision_ts_ms),
        freshness_threshold_ms,
    )
    transition = classify_transition_state(event)
    intensity = _extract_intensity(event)
    diagnostics = extract_regime_diagnostics(event)
    missingness = build_regime_missingness(
        regime=regime,
        timing=timing,
        transition=transition,
        intensity=intensity,
        diagnostics=diagnostics,
        source_refs=source_refs,
    )
    return RegimeContextEnvelope(
        context_id=_to_str_or_none(
            _first_present(event.get("context_id"), event.get("structural_regime_ref"))
        ),
        symbol=symbol,
        ts_ms=ts_ms,
        source_event=_to_str_or_none(event.get("source_event")),
        regime=regime,
        timing=timing,
        transition=transition,
        intensity=intensity,
        diagnostics=diagnostics,
        missingness=missingness,
        source_refs=source_refs,
    )
