from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

LOG = logging.getLogger(__name__)
_DEFAULT_LOG_FILE = Path("logs/regime_confidence_audit_v1.jsonl")
_EPS = 1e-9


def _coerce_float(value: Any) -> Optional[float]:
    if value in (None, "", "None"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_int(value: Any) -> Optional[int]:
    if value in (None, "", "None"):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _coerce_bool(value: Any) -> Optional[bool]:
    if value in (None, "", "None"):
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes"}:
            return True
        if lowered in {"false", "0", "no"}:
            return False
    return None


def _fmt_float(value: Optional[float]) -> str:
    return "null" if value is None else f"{value:.6f}"


def _fmt_bool(value: Optional[bool]) -> str:
    if value is None:
        return "null"
    return "yes" if value else "no"


class BarCloseAuditRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    record_type: Literal["bar_close"] = "bar_close"
    schema_version: str = "1.0.0"
    ts_ms: int = Field(..., ge=0)
    symbol: str = Field(..., min_length=1)
    basis_tf_sec: int = Field(..., ge=1)
    bar_close_ts_ms: int = Field(..., ge=0)
    structural_regime_ref: Optional[str] = Field(default=None)
    changed: bool
    regime: str = Field(..., min_length=1)
    raw_regime: Optional[str] = Field(default=None)
    source_model: str = Field(..., min_length=1)
    pre_cutoff_source_model: Optional[str] = Field(default=None)
    confidence_min: float = Field(..., ge=0.0, le=1.0)
    confidence_max: float = Field(..., ge=0.0, le=1.0)
    pre_cutoff_regime: Optional[str] = Field(default=None)
    pre_cutoff_confidence: Optional[float] = Field(
        default=None, ge=0.0, le=1.0
    )
    raw_confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    stable_confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    emitted_confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    pre_cutoff_clamped_to_min: bool = False
    pre_cutoff_clamped_to_max: bool = False
    pre_cutoff_boundary_reason: Optional[str] = Field(default=None)
    raw_boundary_reason: Optional[str] = Field(default=None)
    uncertain_cutoff: float = Field(..., ge=0.0, le=1.0)
    demoted_to_uncertain: bool = False
    hysteresis_bars: int = Field(..., ge=1)
    hysteresis_confirm_count: int = Field(..., ge=0)
    carried_previous_stable: bool = False
    emitted_confidence_kind: str = Field(..., min_length=1)
    reason_summary: str = Field(..., min_length=1)
    warmup_full_ready: Optional[bool] = Field(default=None)
    data_quality_drops: list[str] = Field(default_factory=list)
    data_quality_notes: list[str] = Field(default_factory=list)


class DecisionAuditRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    record_type: Literal["decision"] = "decision"
    schema_version: str = "1.0.0"
    ts_ms: int = Field(..., ge=0)
    symbol: str = Field(..., min_length=1)
    rid: str = Field(..., min_length=1)
    lifecycle_id: Optional[str] = Field(default=None)
    strategy_id: Optional[str] = Field(default=None)
    intent_side: str = Field(..., min_length=1)
    outcome: str = Field(..., min_length=1)
    regime_used: Optional[str] = Field(default=None)
    regime_confidence_used: Optional[float] = Field(
        default=None, ge=0.0, le=1.0
    )
    confidence_used_stage: str = Field(..., min_length=1)
    detector_event_rid: Optional[str] = Field(default=None)
    detector_event_ts_ms: Optional[int] = Field(default=None, ge=0)
    bar_close_ts_ms: Optional[int] = Field(default=None, ge=0)
    basis_tf_sec: Optional[int] = Field(default=None, ge=1)
    structural_regime_ref: Optional[str] = Field(default=None)
    source_model: Optional[str] = Field(default=None)
    pre_cutoff_source_model: Optional[str] = Field(default=None)
    pre_cutoff_regime: Optional[str] = Field(default=None)
    pre_cutoff_confidence: Optional[float] = Field(
        default=None, ge=0.0, le=1.0
    )
    raw_regime: Optional[str] = Field(default=None)
    raw_confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    stable_confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    confidence_min: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    confidence_max: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    pre_cutoff_clamped_to_min: Optional[bool] = Field(default=None)
    pre_cutoff_clamped_to_max: Optional[bool] = Field(default=None)
    pre_cutoff_boundary_reason: Optional[str] = Field(default=None)
    raw_boundary_reason: Optional[str] = Field(default=None)
    uncertain_cutoff: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    demoted_to_uncertain: Optional[bool] = Field(default=None)
    hysteresis_confirm_count: Optional[int] = Field(default=None, ge=0)
    carried_previous_stable: Optional[bool] = Field(default=None)
    emitted_confidence_kind: Optional[str] = Field(default=None)
    min_regime_confidence: Optional[float] = Field(
        default=None, ge=0.0, le=1.0
    )
    threshold_applied: bool = False
    threshold_verdict: Literal["PASS", "BLOCK", "BYPASS"] = "BYPASS"
    threshold_reason: str = Field(..., min_length=1)
    deny_reason: Optional[str] = Field(default=None)
    why_short: Optional[str] = Field(default=None)
    operator_visible_mismatch: bool = False
    operator_visible_mismatch_reason: Optional[str] = Field(default=None)


def _resolve_log_file(log_file: Optional[str | Path] = None) -> Path:
    if log_file is not None:
        return Path(log_file)
    env_path = os.getenv("REGIME_CONFIDENCE_AUDIT_LOG_FILE", "").strip()
    if env_path:
        return Path(env_path)
    return _DEFAULT_LOG_FILE


def append_regime_confidence_audit_record(
    record: BarCloseAuditRecord | DecisionAuditRecord,
    *,
    log_file: Optional[str | Path] = None,
) -> Dict[str, Any]:
    payload = record.model_dump()
    target = _resolve_log_file(log_file=log_file)
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")
    return payload


def _extract_detector_event(regime_provenance: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(regime_provenance, dict):
        return {}
    detector_event = regime_provenance.get("detector_event")
    return dict(detector_event) if isinstance(detector_event, dict) else {}


def _build_mismatch(
    *,
    detector_event: Dict[str, Any],
    regime_used: Optional[str],
    regime_confidence_used: Optional[float],
) -> tuple[bool, Optional[str]]:
    raw_regime = detector_event.get("raw_regime")
    raw_confidence = _coerce_float(detector_event.get("raw_confidence"))
    if regime_used is None and regime_confidence_used is None:
        return False, None
    regime_differs = bool(raw_regime) and bool(regime_used) and raw_regime != regime_used
    confidence_differs = (
        raw_confidence is not None
        and regime_confidence_used is not None
        and abs(raw_confidence - regime_confidence_used) > _EPS
    )
    mismatch = regime_differs or confidence_differs
    if not mismatch:
        return False, None
    if _coerce_bool(detector_event.get("carried_previous_stable")):
        return True, "hysteresis_carried_previous_stable"
    if _coerce_bool(detector_event.get("demoted_to_uncertain")):
        return True, "uncertain_cutoff_changed_pre_hysteresis_candidate"
    return True, "decision_uses_stable_confidence"


def emit_regime_bar_close_audit(
    *,
    logger: Optional[logging.Logger],
    symbol: str,
    ts_ms: int,
    basis_tf_sec: int,
    bar_close_ts_ms: int,
    structural_regime_ref: Optional[str],
    changed: bool,
    regime: str,
    raw_regime: Optional[str],
    source_model: str,
    pre_cutoff_source_model: Optional[str],
    confidence_min: float,
    confidence_max: float,
    pre_cutoff_regime: Optional[str],
    pre_cutoff_confidence: Optional[float],
    raw_confidence: Optional[float],
    stable_confidence: Optional[float],
    emitted_confidence: Optional[float],
    pre_cutoff_clamped_to_min: bool,
    pre_cutoff_clamped_to_max: bool,
    pre_cutoff_boundary_reason: Optional[str],
    raw_boundary_reason: Optional[str],
    uncertain_cutoff: float,
    demoted_to_uncertain: bool,
    hysteresis_bars: int,
    hysteresis_confirm_count: int,
    carried_previous_stable: bool,
    emitted_confidence_kind: str,
    reason_summary: str,
    warmup_full_ready: Optional[bool],
    data_quality_drops: list[str],
    data_quality_notes: list[str],
    log_file: Optional[str | Path] = None,
) -> Dict[str, Any]:
    record = BarCloseAuditRecord(
        ts_ms=int(ts_ms),
        symbol=str(symbol),
        basis_tf_sec=int(basis_tf_sec),
        bar_close_ts_ms=int(bar_close_ts_ms),
        structural_regime_ref=structural_regime_ref,
        changed=bool(changed),
        regime=str(regime),
        raw_regime=raw_regime,
        source_model=str(source_model),
        pre_cutoff_source_model=pre_cutoff_source_model,
        confidence_min=float(confidence_min),
        confidence_max=float(confidence_max),
        pre_cutoff_regime=pre_cutoff_regime,
        pre_cutoff_confidence=pre_cutoff_confidence,
        raw_confidence=raw_confidence,
        stable_confidence=stable_confidence,
        emitted_confidence=emitted_confidence,
        pre_cutoff_clamped_to_min=bool(pre_cutoff_clamped_to_min),
        pre_cutoff_clamped_to_max=bool(pre_cutoff_clamped_to_max),
        pre_cutoff_boundary_reason=pre_cutoff_boundary_reason,
        raw_boundary_reason=raw_boundary_reason,
        uncertain_cutoff=float(uncertain_cutoff),
        demoted_to_uncertain=bool(demoted_to_uncertain),
        hysteresis_bars=int(hysteresis_bars),
        hysteresis_confirm_count=int(hysteresis_confirm_count),
        carried_previous_stable=bool(carried_previous_stable),
        emitted_confidence_kind=str(emitted_confidence_kind),
        reason_summary=str(reason_summary),
        warmup_full_ready=warmup_full_ready,
        data_quality_drops=list(data_quality_drops or []),
        data_quality_notes=list(data_quality_notes or []),
    )
    payload = append_regime_confidence_audit_record(record, log_file=log_file)
    sink = logger or LOG
    sink.info(
        "[%s] REGIME_AUDIT bar_close bar_ts=%s tf=%s regime=%s raw=%s pre_cutoff=%s "
        "pre_cutoff_conf=%s raw_conf=%s stable_conf=%s emitted_conf=%s min=%s max=%s "
        "cutoff=%s demoted=%s carry=%s changed=%s kind=%s reason=%s",
        symbol,
        payload["bar_close_ts_ms"],
        payload["basis_tf_sec"],
        payload["regime"],
        payload["raw_regime"],
        payload["pre_cutoff_regime"],
        _fmt_float(payload.get("pre_cutoff_confidence")),
        _fmt_float(payload.get("raw_confidence")),
        _fmt_float(payload.get("stable_confidence")),
        _fmt_float(payload.get("emitted_confidence")),
        _fmt_float(payload.get("confidence_min")),
        _fmt_float(payload.get("confidence_max")),
        _fmt_float(payload.get("uncertain_cutoff")),
        _fmt_bool(payload.get("demoted_to_uncertain")),
        _fmt_bool(payload.get("carried_previous_stable")),
        _fmt_bool(payload.get("changed")),
        payload["emitted_confidence_kind"],
        payload["reason_summary"],
    )
    return payload


def emit_regime_decision_audit(
    *,
    logger: Optional[logging.Logger],
    symbol: str,
    rid: str,
    lifecycle_id: Optional[str],
    strategy_id: Optional[str],
    sg: Any,
    outcome: str,
    log_file: Optional[str | Path] = None,
) -> Dict[str, Any]:
    regime_provenance = getattr(sg, "regime_provenance", None)
    detector_event = _extract_detector_event(regime_provenance)
    regime_used = getattr(sg, "regime", None)
    regime_confidence_used = _coerce_float(getattr(sg, "regime_confidence", None))
    mismatch, mismatch_reason = _build_mismatch(
        detector_event=detector_event,
        regime_used=regime_used,
        regime_confidence_used=regime_confidence_used,
    )
    record = DecisionAuditRecord(
        ts_ms=int(getattr(sg, "trace_ts_ms", 0) or 0),
        symbol=str(symbol),
        rid=str(rid),
        lifecycle_id=lifecycle_id,
        strategy_id=str(strategy_id) if strategy_id is not None else None,
        intent_side=str(getattr(sg, "intent_side", "UNKNOWN")),
        outcome=str(outcome),
        regime_used=regime_used,
        regime_confidence_used=regime_confidence_used,
        confidence_used_stage="stable_confidence",
        detector_event_rid=detector_event.get("rid"),
        detector_event_ts_ms=_coerce_int(detector_event.get("ts_ms")),
        bar_close_ts_ms=_coerce_int(
            detector_event.get("bar_close_ts_ms") or detector_event.get("ts_ms")
        ),
        basis_tf_sec=_coerce_int(detector_event.get("basis_tf_sec")),
        structural_regime_ref=detector_event.get("structural_regime_ref"),
        source_model=detector_event.get("source_model"),
        pre_cutoff_source_model=detector_event.get("pre_cutoff_source_model"),
        pre_cutoff_regime=detector_event.get("pre_cutoff_regime"),
        pre_cutoff_confidence=_coerce_float(detector_event.get("pre_cutoff_confidence")),
        raw_regime=detector_event.get("raw_regime"),
        raw_confidence=_coerce_float(detector_event.get("raw_confidence")),
        stable_confidence=_coerce_float(
            detector_event.get("stable_confidence") or detector_event.get("confidence")
        ),
        confidence_min=_coerce_float(detector_event.get("confidence_min")),
        confidence_max=_coerce_float(detector_event.get("confidence_max")),
        pre_cutoff_clamped_to_min=_coerce_bool(
            detector_event.get("pre_cutoff_clamped_to_min")
        ),
        pre_cutoff_clamped_to_max=_coerce_bool(
            detector_event.get("pre_cutoff_clamped_to_max")
        ),
        pre_cutoff_boundary_reason=detector_event.get("pre_cutoff_boundary_reason"),
        raw_boundary_reason=detector_event.get("raw_boundary_reason"),
        uncertain_cutoff=_coerce_float(detector_event.get("uncertain_cutoff")),
        demoted_to_uncertain=_coerce_bool(detector_event.get("demoted_to_uncertain")),
        hysteresis_confirm_count=_coerce_int(
            detector_event.get("hysteresis_confirm_count")
        ),
        carried_previous_stable=_coerce_bool(
            detector_event.get("carried_previous_stable")
        ),
        emitted_confidence_kind=detector_event.get("emitted_confidence_kind"),
        min_regime_confidence=_coerce_float(
            getattr(sg, "min_regime_confidence", None)
        ),
        threshold_applied=bool(getattr(sg, "threshold_applied", False)),
        threshold_verdict=str(getattr(sg, "threshold_verdict", "BYPASS") or "BYPASS"),
        threshold_reason=str(
            getattr(sg, "threshold_reason", "threshold_not_evaluated")
            or "threshold_not_evaluated"
        ),
        deny_reason=getattr(sg, "deny_reason", None),
        why_short=getattr(sg, "why_short", None),
        operator_visible_mismatch=bool(mismatch),
        operator_visible_mismatch_reason=mismatch_reason,
    )
    payload = append_regime_confidence_audit_record(record, log_file=log_file)
    sink = logger or LOG
    sink.info(
        "[%s] REGIME_AUDIT decision rid=%s strategy=%s outcome=%s regime=%s conf=%s "
        "raw_conf=%s stable_conf=%s threshold=%s verdict=%s applied=%s reason=%s "
        "bar_ts=%s ref=%s mismatch=%s mismatch_reason=%s",
        symbol,
        payload["rid"],
        payload.get("strategy_id"),
        payload["outcome"],
        payload.get("regime_used"),
        _fmt_float(payload.get("regime_confidence_used")),
        _fmt_float(payload.get("raw_confidence")),
        _fmt_float(payload.get("stable_confidence")),
        _fmt_float(payload.get("min_regime_confidence")),
        payload["threshold_verdict"],
        _fmt_bool(payload.get("threshold_applied")),
        payload["threshold_reason"],
        payload.get("bar_close_ts_ms"),
        payload.get("structural_regime_ref"),
        _fmt_bool(payload.get("operator_visible_mismatch")),
        payload.get("operator_visible_mismatch_reason"),
    )
    return payload
