"""Payload assembly helpers for IntentBuilder."""

import decimal
import uuid
from typing import Any, Optional


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
    symbol: str,
    strategy_id: str,
    trace_ts_ms: int,
    intent_side: str,
    sg: Any,
    regime_provenance: Optional[dict],
    tpsl_owner_ctx: Optional[dict],
) -> dict[str, Any]:
    """Build the side-channel decision trace payload emitted before the trade intent."""
    trace_payload = {
        "symbol": symbol,
        "strategy_id": strategy_id,
        "ts": trace_ts_ms,
        "intent_side": intent_side,
        "signal_score": sg.signal_score,
        "regime": sg.regime,
        "regime_confidence": sg.regime_confidence,
        "min_regime_confidence": getattr(sg, "min_regime_confidence", None),
        "resolved_min_regime_confidence": getattr(sg, "resolved_min_regime_confidence", None),
        "resolved_min_regime_confidence_source": getattr(sg, "resolved_min_regime_confidence_source", None),
        "resolved_min_regime_confidence_strategy_id": getattr(sg, "resolved_min_regime_confidence_strategy_id", None),
        "resolved_min_regime_confidence_regime_key": getattr(sg, "resolved_min_regime_confidence_regime_key", None),
        "regime_confidence_gate_verdict": getattr(sg, "regime_confidence_gate_verdict", None),
        "trend_dir": sg.trend_dir,
        "trend_run_length": sg.trend_run_length,
        "delta_price": sg.delta_price,
        "pm_norm_10s": sg.pm_norm_10s,
        "pm_norm_60s": sg.pm_norm_60s,
        "pm_norm_300s": sg.pm_norm_300s,
        "vol_pct_10s": sg.vol_pct_10s,
        "vol_pct_60s": sg.vol_pct_60s,
        "vol_pct_300s": sg.vol_pct_300s,
        "gate_outcome": "ALLOW",
        "deny_reason": None,
        "why": (str(sg.why_short)[:80] if sg.why_short else ""),
    }
    if isinstance(regime_provenance, dict) and regime_provenance:
        trace_payload["regime_provenance"] = regime_provenance
    if tpsl_owner_ctx is not None:
        trace_payload["tpsl_owner_ctx"] = tpsl_owner_ctx
    low_vol_cost_floor = getattr(sg, "low_vol_cost_floor_details", None)
    if isinstance(low_vol_cost_floor, dict) and low_vol_cost_floor:
        trace_payload["low_vol_cost_floor"] = dict(low_vol_cost_floor)
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
        "min_regime_confidence": getattr(sg, "min_regime_confidence", None),
        "resolved_min_regime_confidence": getattr(sg, "resolved_min_regime_confidence", None),
        "resolved_min_regime_confidence_source": getattr(sg, "resolved_min_regime_confidence_source", None),
        "resolved_min_regime_confidence_strategy_id": getattr(sg, "resolved_min_regime_confidence_strategy_id", None),
        "resolved_min_regime_confidence_regime_key": getattr(sg, "resolved_min_regime_confidence_regime_key", None),
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
