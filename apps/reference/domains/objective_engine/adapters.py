from __future__ import annotations

import decimal
from collections import deque
from typing import Any, Deque, Dict, Iterable

from apps.reference.config_models import AuroraConfig
from apps.reference.domains.decision_making.entry_plan import EntryPlanResult
from apps.reference.domains.decision_making.position_queries import PositionQueries
from apps.reference.domains.objective_engine.types import (
    ObjectiveBehaviorInput,
    ObjectiveExecutionInput,
    ObjectiveExposureInput,
    ObjectiveInput,
    ObjectiveMarketInput,
    ObjectiveSignalInput,
    ObjectiveStructureInput,
)


def _to_float(value: Any, *, field_name: str) -> float:
    try:
        value_f = float(value)
    except Exception as exc:
        raise ValueError(f"objective field missing or invalid: {field_name}") from exc
    if value_f != value_f or value_f in (float("inf"), float("-inf")):
        raise ValueError(f"objective field missing or invalid: {field_name}")
    return value_f


def compute_readiness_completeness(warmup_readiness: Dict[str, Any]) -> float:
    if not isinstance(warmup_readiness, dict) or not warmup_readiness:
        raise ValueError("OBJECTIVE_READINESS_MISSING")
    values = []
    for value in warmup_readiness.values():
        if isinstance(value, bool):
            values.append(1.0 if value else 0.0)
    if not values:
        raise ValueError("OBJECTIVE_READINESS_MISSING")
    return sum(values) / float(len(values))


def build_signal_input(
    *,
    strategy_id: str,
    symbol: str,
    signal_score: float,
    signal_direction: int,
    regime: str,
    regime_age_sec: float,
    regime_confidence: float,
    readiness_completeness: float,
) -> ObjectiveSignalInput:
    return ObjectiveSignalInput(
        strategy_id=strategy_id,
        symbol=symbol,
        signal_score=signal_score,
        signal_direction=signal_direction,
        regime=regime,
        regime_age_sec=regime_age_sec,
        regime_confidence=regime_confidence,
        readiness_completeness=readiness_completeness,
    )


def build_market_input(*, features: Dict[str, Any]) -> ObjectiveMarketInput:
    if not isinstance(features, dict):
        raise ValueError("OBJECTIVE_FEATURES_MISSING")
    return ObjectiveMarketInput(
        price=_to_float(features.get("price"), field_name="price"),
        atr=_to_float(features.get("atr"), field_name="atr"),
        spread_bps=_to_float(features.get("spread_bps"), field_name="spread_bps"),
        liquidity_state=_to_float(features.get("liquidity_kappa"), field_name="liquidity_kappa"),
        volatility_state=_to_float(features.get("volatility_state"), field_name="volatility_state"),
    )


def build_structure_input(
    *,
    signal_score: float,
    active_threshold: float,
    entry_plan: EntryPlanResult,
) -> ObjectiveStructureInput:
    entry_price = decimal.Decimal(str(entry_plan.entry_price))
    stop_price = decimal.Decimal(str(entry_plan.stop_loss_price))
    target_price = decimal.Decimal(str(entry_plan.take_profit_price))
    atr = decimal.Decimal(str(entry_plan.atr))
    if atr <= 0:
        raise ValueError("OBJECTIVE_ENTRY_PLAN_INVALID:atr")

    threshold_margin = max(0.0, (abs(float(signal_score)) - float(active_threshold)) / max(float(active_threshold), 1e-9))
    stop_dist = abs(entry_price - stop_price)
    tp_dist = abs(target_price - entry_price)
    stop_dist_atr = float(stop_dist / atr)
    tp_dist_atr = float(tp_dist / atr)
    if stop_dist_atr <= 0.0:
        raise ValueError("OBJECTIVE_ENTRY_PLAN_INVALID:stop_dist")
    rr_expected = tp_dist_atr / stop_dist_atr
    return ObjectiveStructureInput(
        threshold_margin=threshold_margin,
        rr_expected=rr_expected,
        tp_dist_atr=tp_dist_atr,
        stop_dist_atr=stop_dist_atr,
    )


def build_structure_input_from_prices(
    *,
    signal_score: float,
    active_threshold: float,
    entry_price: decimal.Decimal,
    stop_price: decimal.Decimal,
    target_price: decimal.Decimal,
    atr: decimal.Decimal,
) -> ObjectiveStructureInput:
    if atr <= 0:
        raise ValueError("OBJECTIVE_ENTRY_PLAN_INVALID:atr")
    threshold_margin = max(0.0, (abs(float(signal_score)) - float(active_threshold)) / max(float(active_threshold), 1e-9))
    stop_dist_atr = float(abs(entry_price - stop_price) / atr)
    tp_dist_atr = float(abs(target_price - entry_price) / atr)
    if stop_dist_atr <= 0.0:
        raise ValueError("OBJECTIVE_ENTRY_PLAN_INVALID:stop_dist")
    return ObjectiveStructureInput(
        threshold_margin=threshold_margin,
        rr_expected=tp_dist_atr / stop_dist_atr,
        tp_dist_atr=tp_dist_atr,
        stop_dist_atr=stop_dist_atr,
    )


def compute_projected_order_notional(
    *,
    symbol: str,
    side: str,
    entry_price: decimal.Decimal,
    position_queries: PositionQueries | None,
    portfolio: Dict[str, Any],
    features_payload: Dict[str, Any] | None,
    margin_pct_mult: decimal.Decimal | None = None,
) -> float:
    if position_queries is None:
        raise ValueError("OBJECTIVE_SIZING_UNAVAILABLE:position_queries")
    qty_dec, why_sizing, sizing_rej, sizing_dbg = position_queries.calculate_position_size(
        symbol=symbol,
        price=entry_price,
        side=side,
        context={"portfolio": portfolio, "features": features_payload or {}},
        margin_pct_mult=margin_pct_mult,
    )
    if qty_dec is None or sizing_rej is not None:
        raise ValueError(f"OBJECTIVE_SIZING_UNAVAILABLE:{sizing_rej or why_sizing}")
    try:
        order_notional = sizing_dbg["order_notional"]
    except Exception as exc:
        raise ValueError("OBJECTIVE_SIZING_UNAVAILABLE:order_notional") from exc
    return _to_float(order_notional, field_name="order_notional")


def build_exposure_input(
    *,
    config: AuroraConfig,
    portfolio: Dict[str, Any],
    exposure_summary: Dict[str, Any],
    projected_order_notional_usd: float,
) -> ObjectiveExposureInput:
    if not isinstance(portfolio, dict):
        raise ValueError("OBJECTIVE_PORTFOLIO_MISSING")
    if not isinstance(exposure_summary, dict):
        raise ValueError("OBJECTIVE_EXPOSURE_SUMMARY_MISSING")

    equity_free_usdt = _to_float(portfolio.get("equity_free_usdt"), field_name="equity_free_usdt")
    open_positions_usd = _to_float(portfolio.get("open_positions_usd"), field_name="open_positions_usd")
    reservations_usd = _to_float(exposure_summary.get("reservations_usd"), field_name="reservations_usd")
    max_portfolio_fraction = float(config.domains.execution_position.exposure_guard.max_portfolio_fraction)
    max_exposure_usd = equity_free_usdt * max_portfolio_fraction
    current_exposure_usd = open_positions_usd + reservations_usd
    projected_exposure_usd = current_exposure_usd + projected_order_notional_usd
    return ObjectiveExposureInput(
        current_exposure_usd=current_exposure_usd,
        projected_exposure_usd=projected_exposure_usd,
        max_exposure_usd=max_exposure_usd,
    )


def prune_recent_timestamps(timestamps: Deque[int], *, now_ms: int, window_sec: float) -> None:
    cutoff_ms = int(now_ms - (window_sec * 1000.0))
    while timestamps and int(timestamps[0]) < cutoff_ms:
        timestamps.popleft()


def build_behavior_input(
    *,
    now_ms: int,
    window_sec: float,
    cancel_replace_ts_ms: Deque[int],
    blocked_intent_ts_ms: Deque[int],
    reentry_ts_ms: Deque[int],
) -> ObjectiveBehaviorInput:
    for bucket in (cancel_replace_ts_ms, blocked_intent_ts_ms, reentry_ts_ms):
        prune_recent_timestamps(bucket, now_ms=now_ms, window_sec=window_sec)
    return ObjectiveBehaviorInput(
        recent_cancel_replace_count=len(cancel_replace_ts_ms),
        recent_blocked_intent_count=len(blocked_intent_ts_ms),
        recent_reentry_count=len(reentry_ts_ms),
    )


def build_execution_input(*, expected_fee_bps: float, expected_slippage_bps: float) -> ObjectiveExecutionInput:
    return ObjectiveExecutionInput(
        expected_fee_bps=expected_fee_bps,
        expected_slippage_bps=expected_slippage_bps,
    )


def build_objective_input(
    *,
    signal: ObjectiveSignalInput,
    market: ObjectiveMarketInput,
    structure: ObjectiveStructureInput,
    exposure: ObjectiveExposureInput,
    behavior: ObjectiveBehaviorInput,
    execution: ObjectiveExecutionInput,
) -> ObjectiveInput:
    return ObjectiveInput(
        signal=signal,
        market=market,
        structure=structure,
        exposure=exposure,
        behavior=behavior,
        execution=execution,
    )
