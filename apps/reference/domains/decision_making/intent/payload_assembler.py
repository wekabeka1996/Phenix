"""Payload assembly helpers for IntentBuilder."""

import decimal
import uuid
from typing import Any, Optional

from apps.reference.shared.decision_primitives.score_lineage import (
    find_score_lineage_record,
)


def _normalize_intent_side(value: Any) -> str:
    side_u = str(value).upper()
    if side_u == "BUY":
        return "LONG"
    if side_u == "SELL":
        return "SHORT"
    if side_u in {"LONG", "SHORT"}:
        return side_u
    return side_u


def _normalize_order_side(value: Any) -> str | None:
    side_u = str(value).upper()
    if side_u in {"BUY", "SELL"}:
        return side_u
    return None


def _normalize_trend_dir(value: Any) -> str:
    if isinstance(value, (int, float)):
        if float(value) > 0:
            return "UP"
        if float(value) < 0:
            return "DOWN"
        return "UNKNOWN"
    trend_dir = str(value).upper()
    if trend_dir in {"UP", "DOWN", "UNKNOWN"}:
        return trend_dir
    return "UNKNOWN"


def _pick_price_motion_value(sg: Any, field_name: str) -> Any:
    direct_value = getattr(sg, field_name, None)
    if direct_value is not None:
        return direct_value
    low_vol_details = getattr(sg, "low_vol_cost_floor_details", None)
    if isinstance(low_vol_details, dict):
        price_motion_context = low_vol_details.get("price_motion_context")
        if isinstance(price_motion_context, dict):
            return price_motion_context.get(field_name)
    return None


def _build_price_motion_context(sg: Any) -> dict[str, Any]:
    context: dict[str, Any] = {}
    missing: dict[str, bool] = {}
    missing_reason: dict[str, str | None] = {}
    for field_name in (
        "pm_norm_10s",
        "pm_norm_60s",
        "pm_norm_300s",
        "vol_pct_10s",
        "vol_pct_60s",
        "vol_pct_300s",
    ):
        value = _pick_price_motion_value(sg, field_name)
        context[field_name] = value
        is_missing = value is None
        missing[field_name] = is_missing
        missing_reason[field_name] = (
            "absent_from_safety_gate_result" if is_missing else None
        )
    context["missing"] = missing
    context["missing_reason"] = missing_reason
    return context


def _resolve_score_lineage_payload(
    sg: Any,
    strategy_trace: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if isinstance(strategy_trace, dict):
        score_lineage = strategy_trace.get("score_lineage")
        if isinstance(score_lineage, dict):
            return dict(score_lineage)
    score_lineage = getattr(sg, "score_lineage", None)
    if isinstance(score_lineage, dict):
        return dict(score_lineage)
    return None


def _resolve_lineage_value(
    score_lineage: dict[str, Any] | None,
    field: str,
) -> Any:
    record = find_score_lineage_record(score_lineage, field)
    if record is None:
        return None
    return record.get("value")


def _build_missing_inputs(
    sg: Any,
    strategy_trace: dict[str, Any] | None,
) -> dict[str, str | None]:
    price_motion_context = _build_price_motion_context(sg)
    score_lineage = _resolve_score_lineage_payload(sg, strategy_trace)
    low_vol_details = getattr(sg, "low_vol_cost_floor_details", None)
    low_vol_score_context = (
        low_vol_details.get("score_context")
        if isinstance(low_vol_details, dict) and isinstance(low_vol_details.get("score_context"), dict)
        else {}
    )
    signal_score_present = any(
        candidate is not None
        for candidate in (
            _resolve_lineage_value(score_lineage, "signal_score"),
            strategy_trace.get("signal_score") if isinstance(strategy_trace, dict) else None,
            low_vol_score_context.get("signal_score") if isinstance(low_vol_score_context, dict) else None,
        )
    )
    return {
        "regime_confidence": (
            "absent_from_safety_gate_result"
            if getattr(sg, "regime_confidence", None) is None
            else None
        ),
        "trend_dir": (
            "absent_from_safety_gate_result"
            if getattr(sg, "trend_dir", None) is None
            else None
        ),
        "trend_confidence": (
            "absent_from_safety_gate_result"
            if getattr(sg, "trend_confidence", None) is None
            else None
        ),
        "trend_run_length": (
            "absent_from_safety_gate_result"
            if getattr(sg, "trend_run_length", None) is None
            else None
        ),
        "pm_norm_10s": price_motion_context["missing_reason"]["pm_norm_10s"],
        "pm_norm_60s": price_motion_context["missing_reason"]["pm_norm_60s"],
        "pm_norm_300s": price_motion_context["missing_reason"]["pm_norm_300s"],
        "vol_pct_10s": price_motion_context["missing_reason"]["vol_pct_10s"],
        "vol_pct_60s": price_motion_context["missing_reason"]["vol_pct_60s"],
        "vol_pct_300s": price_motion_context["missing_reason"]["vol_pct_300s"],
        "signal_score": None if signal_score_present else "absent_from_attached_score_lineage",
        "low_vol_cost_floor": (
            None
            if isinstance(getattr(sg, "low_vol_cost_floor_details", None), dict)
            else "not_evaluated_or_not_attached"
        ),
    }


def _build_safety_gate_snapshot(sg: Any) -> dict[str, Any]:
    return {
        "apply_safety_gates": getattr(sg, "apply_safety_gates", None),
        "directional_sanity_enabled": getattr(sg, "directional_sanity_enabled", None),
        "nrr026_enabled": getattr(sg, "nrr026_enabled", None),
        "nrr026_effective_enforced": getattr(sg, "nrr026_effective_enforced", None),
        "nrr027_enabled": getattr(sg, "nrr027_enabled", None),
        "nrr027_effective_enforced": getattr(sg, "nrr027_effective_enforced", None),
        "price_motion_sanity_enabled": getattr(sg, "price_motion_sanity_enabled", None),
        "price_motion_backtest_bypass": getattr(sg, "price_motion_backtest_bypass", None),
        "nrr028_enabled": getattr(sg, "nrr028_enabled", None),
        "nrr028_effective_enforced": getattr(sg, "nrr028_effective_enforced", None),
        "nrr029_enabled": getattr(sg, "nrr029_enabled", None),
        "nrr029_effective_enforced": getattr(sg, "nrr029_effective_enforced", None),
        "nrr030_enabled": getattr(sg, "nrr030_enabled", None),
        "nrr030_effective_enforced": getattr(sg, "nrr030_effective_enforced", None),
        "nrr063_enabled": getattr(sg, "nrr063_enabled", None),
        "nrr063_effective_enforced": getattr(sg, "nrr063_effective_enforced", None),
        "regime_confidence_gate_verdict": getattr(sg, "regime_confidence_gate_verdict", None),
        "threshold_verdict": getattr(sg, "threshold_verdict", None),
        "threshold_reason": getattr(sg, "threshold_reason", None),
    }


def build_trade_intent_payload(
    *,
    symbol: str,
    side: str,
    strategy_id: str,
    rid: str,
    qty: decimal.Decimal,
    price: decimal.Decimal,
    reduce_only: bool,
    order_type: str,
    tif: Optional[str],
    max_slippage_bps: str,
    max_latency_ms: Any,
    maker_preference: str,
    risk_score: Optional[float],
    trade_cvar95_max_bps: str,
    session_cvar95_max_bps: str,
    p: str,
    payoff_ratio_r: str,
    kelly_fraction: str,
    kelly_provenance: Optional[dict[str, Any]],
    valid_for_ms: Optional[int],
    why_chain: list,
    stop_price: Optional[str],
    target_price: Optional[str],
    entry_plan_trace: Optional[dict],
    regime: Any,
    regime_confidence: Any,
    regime_provenance: Optional[dict],
    regime_epoch_ref: Optional[str],
    tpsl_owner_ctx: Optional[dict],
    strategy_trace: Optional[dict],
    authority_context: Optional[dict[str, Any]] = None,
    idempotent_key: Optional[str] = None,
) -> dict[str, Any]:
    """Build the canonical TRADE_INTENT_PROPOSED payload."""
    trade_intent = {
        "rid": str(rid),
        "instrument": symbol,
        "side": side,
        "strategy": strategy_id,
        "order": {
            "qty": str(qty),
            "price": str(price),
            "price_ref": str(price),
            "reduce_only": reduce_only,
            "order_type": order_type,
            "tif": tif,
        },
        "p": p,
        "payoff_ratio_r": payoff_ratio_r,
        "tca_budget": {
            "max_slippage_bps": max_slippage_bps,
            "max_latency_ms": max_latency_ms,
            "maker_preference": maker_preference,
        },
        "risk_context": {"risk_score": risk_score if risk_score is not None else 0.0},
        "risk_budget": {
            "trade_cvar95_max_bps": trade_cvar95_max_bps,
            "session_cvar95_max_bps": session_cvar95_max_bps,
        },
        "size": {
            "notional_cap_usd": str(qty * price),
            "kelly_fraction": kelly_fraction,
        },
        "valid_for_ms": valid_for_ms,
        "why": why_chain,
        "dto_version": "1.0.0",
        "schema_ref": "trade_intent_v1.json",
        "idempotent_key": str(idempotent_key or uuid.uuid4()),
        "stop_price": stop_price,
        "target_price": target_price,
        "entry_plan": entry_plan_trace,
        "regime": regime,
        "regime_confidence": regime_confidence,
        "regime_provenance": None,
    }
    if isinstance(regime_provenance, dict) and regime_provenance:
        trade_intent["regime_provenance"] = regime_provenance
    trade_intent["regime_epoch_ref"] = regime_epoch_ref
    if tpsl_owner_ctx is not None:
        trade_intent["tpsl_owner_ctx"] = tpsl_owner_ctx
    trace_payload: Optional[dict[str, Any]] = None
    if isinstance(strategy_trace, dict) and strategy_trace:
        trace_payload = dict(strategy_trace)
    if isinstance(kelly_provenance, dict) and kelly_provenance:
        trace_payload = dict(trace_payload or {})
        trace_payload["kelly_provenance"] = kelly_provenance
    if trace_payload is not None:
        trade_intent["trace"] = trace_payload
    if isinstance(authority_context, dict) and authority_context:
        trade_intent["authority_context"] = dict(authority_context)
    return trade_intent


def build_decision_trace_payload(
    *,
    rid: str,
    symbol: str,
    strategy_id: str,
    trace_ts_ms: int,
    intent_side: str,
    order_side: Optional[str],
    lifecycle_id: Optional[str],
    sg: Any,
    strategy_trace: Optional[dict[str, Any]],
    regime_provenance: Optional[dict],
    tpsl_owner_ctx: Optional[dict],
    tf_sec: Optional[int] = None,
    gate_outcome: str = "ALLOW",
    deny_reason: Optional[str] = None,
    why: Optional[str] = None,
) -> dict[str, Any]:
    """Build the side-channel decision trace payload emitted before the trade intent."""
    trace_context = dict(strategy_trace) if isinstance(
        strategy_trace, dict) else {}
    score_lineage = _resolve_score_lineage_payload(sg, trace_context)
    detector_event = trace_context.get("detector_event")
    if not isinstance(detector_event, dict) and isinstance(regime_provenance, dict):
        candidate_detector_event = regime_provenance.get("detector_event")
        detector_event = candidate_detector_event if isinstance(
            candidate_detector_event, dict) else {}
    if not isinstance(detector_event, dict):
        detector_event = {}

    decision_surface = trace_context.get("decision_surface")
    if not isinstance(decision_surface, str) or not decision_surface.strip():
        decision_surface = "decision_trace"

    accepted_or_rejected = "ACCEPTED" if gate_outcome == "ALLOW" else "REJECTED"
    signal_score_value = (
        trace_context.get("signal_score")
        if trace_context.get("signal_score") is not None
        else _resolve_lineage_value(score_lineage, "signal_score")
    )
    decision_score_value = (
        trace_context.get("decision_score")
        if trace_context.get("decision_score") is not None
        else _resolve_lineage_value(score_lineage, "decision_score")
    )
    raw_score_value = (
        trace_context.get("final_score_raw")
        if trace_context.get("final_score_raw") is not None
        else _resolve_lineage_value(score_lineage, "final_score_raw")
    )
    trace_payload = {
        "rid": rid,
        "decision_id": trace_context.get("decision_id"),
        "cycle_key": trace_context.get("cycle_key"),
        "symbol": symbol,
        "side": _normalize_order_side(order_side),
        "strategy_id": strategy_id,
        "ts": trace_ts_ms,
        "event_ts_ms": trace_ts_ms,
        "tf_sec": tf_sec,
        "bar_close_ts_ms": detector_event.get("bar_close_ts_ms") or detector_event.get("bar_close_ts"),
        "intent_side": _normalize_intent_side(intent_side),
        "signal_score": signal_score_value if signal_score_value is not None else getattr(sg, "signal_score", None),
        "raw_score": raw_score_value,
        "decision_score": decision_score_value if decision_score_value is not None else signal_score_value,
        "active_threshold": trace_context.get("active_threshold"),
        "score_to_threshold_ratio": trace_context.get("aurora_raw_score_to_threshold_ratio"),
        "decision_surface": decision_surface,
        "gate_chain_result": gate_outcome,
        "accepted_or_rejected": accepted_or_rejected,
        "reject_reason": deny_reason,
        "regime": sg.regime,
        "regime_confidence": sg.regime_confidence,
        "resolved_regime_confidence_strategy_id": getattr(sg, "resolved_regime_confidence_strategy_id", None),
        "resolved_regime_confidence_symbol": getattr(sg, "resolved_regime_confidence_symbol", None),
        "resolved_regime_confidence_regime_key": getattr(sg, "resolved_regime_confidence_regime_key", None),
        "min_regime_confidence": getattr(sg, "min_regime_confidence", None),
        "resolved_min_regime_confidence": getattr(sg, "resolved_min_regime_confidence", None),
        "resolved_min_regime_confidence_source": getattr(sg, "resolved_min_regime_confidence_source", None),
        "resolved_min_regime_confidence_strategy_id": getattr(sg, "resolved_min_regime_confidence_strategy_id", None),
        "resolved_min_regime_confidence_regime_key": getattr(sg, "resolved_min_regime_confidence_regime_key", None),
        "resolved_max_regime_confidence": getattr(sg, "resolved_max_regime_confidence", None),
        "resolved_max_regime_confidence_source": getattr(sg, "resolved_max_regime_confidence_source", None),
        "resolved_max_regime_confidence_strategy_id": getattr(sg, "resolved_max_regime_confidence_strategy_id", None),
        "resolved_max_regime_confidence_regime_key": getattr(sg, "resolved_max_regime_confidence_regime_key", None),
        "resolved_regime_confidence_band_active": getattr(sg, "resolved_regime_confidence_band_active", None),
        "regime_confidence_breach_kind": getattr(sg, "regime_confidence_breach_kind", None),
        "regime_confidence_gate_verdict": getattr(sg, "regime_confidence_gate_verdict", None),
        "trend_dir": _normalize_trend_dir(getattr(sg, "trend_dir", None)),
        "trend_confidence": getattr(sg, "trend_confidence", None),
        "trend_run_length": sg.trend_run_length,
        "delta_price": sg.delta_price,
        "pm_norm_10s": sg.pm_norm_10s,
        "pm_norm_60s": sg.pm_norm_60s,
        "pm_norm_300s": sg.pm_norm_300s,
        "vol_pct_10s": sg.vol_pct_10s,
        "vol_pct_60s": sg.vol_pct_60s,
        "vol_pct_300s": sg.vol_pct_300s,
        "gate_outcome": gate_outcome,
        "deny_reason": deny_reason,
        "why": (str(why if why is not None else getattr(sg, "why_short", ""))[:80]),
        "price_motion_context": _build_price_motion_context(sg),
        "missing_inputs": _build_missing_inputs(sg, trace_context),
        "safety_gate_snapshot": _build_safety_gate_snapshot(sg),
    }
    if score_lineage is not None:
        trace_payload["score_lineage"] = score_lineage
    if lifecycle_id is not None:
        trace_payload["lifecycle_id"] = lifecycle_id
        trace_payload["intent_id"] = lifecycle_id
    if isinstance(regime_provenance, dict) and regime_provenance:
        trace_payload["regime_provenance"] = regime_provenance
    if tpsl_owner_ctx is not None:
        trace_payload["tpsl_owner_ctx"] = tpsl_owner_ctx
    low_vol_cost_floor = getattr(sg, "low_vol_cost_floor_details", None)
    if isinstance(low_vol_cost_floor, dict) and low_vol_cost_floor:
        trace_payload["low_vol_cost_floor"] = dict(low_vol_cost_floor)
    anti_peak_obs = trace_context.get("anti_peak_observability")
    if isinstance(anti_peak_obs, dict):
        trace_payload["anti_peak_observability"] = dict(anti_peak_obs)
    return trace_payload


def build_order_intent_log_entry(
    *,
    rid: str,
    lifecycle_id: str,
    symbol: str,
    strategy_id: str,
    side: str,
    qty: decimal.Decimal,
    price: decimal.Decimal,
    sg: Any,
    regime_provenance: Optional[dict],
    normalize_mode: str,
) -> dict[str, Any]:
    """Build the ORDER_INTENT payload written to OrderLogger."""
    metadata = {
        "intent_proposed": True,
        "idempotent_key": lifecycle_id,
        "normalize_mode_effective": normalize_mode,
        "resolved_regime_confidence_strategy_id": getattr(sg, "resolved_regime_confidence_strategy_id", None),
        "resolved_regime_confidence_symbol": getattr(sg, "resolved_regime_confidence_symbol", None),
        "resolved_regime_confidence_regime_key": getattr(sg, "resolved_regime_confidence_regime_key", None),
        "min_regime_confidence": getattr(sg, "min_regime_confidence", None),
        "resolved_min_regime_confidence": getattr(sg, "resolved_min_regime_confidence", None),
        "resolved_min_regime_confidence_source": getattr(sg, "resolved_min_regime_confidence_source", None),
        "resolved_min_regime_confidence_strategy_id": getattr(sg, "resolved_min_regime_confidence_strategy_id", None),
        "resolved_min_regime_confidence_regime_key": getattr(sg, "resolved_min_regime_confidence_regime_key", None),
        "resolved_max_regime_confidence": getattr(sg, "resolved_max_regime_confidence", None),
        "resolved_max_regime_confidence_source": getattr(sg, "resolved_max_regime_confidence_source", None),
        "resolved_max_regime_confidence_strategy_id": getattr(sg, "resolved_max_regime_confidence_strategy_id", None),
        "resolved_max_regime_confidence_regime_key": getattr(sg, "resolved_max_regime_confidence_regime_key", None),
        "resolved_regime_confidence_band_active": getattr(sg, "resolved_regime_confidence_band_active", None),
        "regime_confidence_breach_kind": getattr(sg, "regime_confidence_breach_kind", None),
        "regime_confidence_gate_verdict": getattr(sg, "regime_confidence_gate_verdict", None),
        "threshold_applied": getattr(sg, "threshold_applied", None),
        "threshold_verdict": getattr(sg, "threshold_verdict", None),
        "threshold_reason": getattr(sg, "threshold_reason", None),
    }
    low_vol_cost_floor = getattr(sg, "low_vol_cost_floor_details", None)
    if isinstance(low_vol_cost_floor, dict) and low_vol_cost_floor:
        metadata["low_vol_cost_floor"] = dict(low_vol_cost_floor)
    return {
        "rid": rid,
        "event_type": "ORDER_INTENT",
        "lifecycle_id": lifecycle_id,
        "symbol": symbol,
        "strategy_id": strategy_id,
        "side": side.upper(),
        "quantity": float(qty),
        "price": float(price),
        "source_fsm": "DecisionMaking",
        "regime": sg.regime,
        "regime_confidence": sg.regime_confidence,
        "regime_provenance": regime_provenance if isinstance(regime_provenance, dict) else None,
        "metadata": metadata,
    }
