from __future__ import annotations

from decimal import Decimal

from apps.reference.domains.objective_engine.realized_types import (
    ActiveObjectivePosition,
    ObjectiveRealizedEvent,
)


def _safe_ratio(numerator: Decimal, denominator: Decimal) -> float:
    if denominator == 0:
        return 0.0
    return float(numerator / denominator)


def _clip_unit(value: float) -> float:
    return max(-1.0, min(1.0, value))


def evaluate_realized_quality(
    *,
    active: ActiveObjectivePosition,
    close_rid: str,
    exit_price: Decimal,
    close_ts_ms: int,
    closed_qty: Decimal,
    close_reason: str,
) -> ObjectiveRealizedEvent:
    snapshot = active.snapshot
    signed_entry = 1 if snapshot.entry_side.upper() == "BUY" else -1
    gross_move = (exit_price - active.avg_entry_price) * Decimal(str(signed_entry))
    realized_pnl = gross_move * closed_qty
    fees = active.accrued_fees
    entry_price = max(active.avg_entry_price, Decimal("1e-9"))

    if signed_entry > 0:
        favorable_move = active.highest_price - active.avg_entry_price
        adverse_move = active.avg_entry_price - active.lowest_price
    else:
        favorable_move = active.avg_entry_price - active.lowest_price
        adverse_move = active.highest_price - active.avg_entry_price

    favorable_move = max(favorable_move, Decimal("0"))
    adverse_move = max(adverse_move, Decimal("0"))

    target_dist = (
        abs(snapshot.target_price - snapshot.entry_price)
        if snapshot.target_price is not None
        else abs(active.avg_entry_price) * Decimal("0")
    )
    stop_dist = (
        abs(snapshot.entry_price - snapshot.stop_price)
        if snapshot.stop_price is not None
        else abs(active.avg_entry_price) * Decimal("0")
    )

    realized_pnl_efficiency = _clip_unit(
        _safe_ratio(realized_pnl, target_dist * closed_qty)
        if realized_pnl >= 0 and target_dist > 0
        else -_safe_ratio(abs(realized_pnl), stop_dist * closed_qty)
        if stop_dist > 0
        else 0.0
    )
    realized_cost_drag = -_clip_unit(_safe_ratio(fees, abs(active.avg_entry_price * closed_qty)))
    mae_efficiency = _clip_unit(1.0 - _safe_ratio(adverse_move, stop_dist)) if stop_dist > 0 else 0.0
    mfe_efficiency = _clip_unit(_safe_ratio(abs(gross_move), favorable_move)) if favorable_move > 0 else 0.0
    duration_sec = max(0.0, float(close_ts_ms - active.open_ts_ms) / 1000.0)
    duration_efficiency = _clip_unit(_safe_ratio(abs(realized_pnl), max(abs(active.avg_entry_price * closed_qty), Decimal("1"))) / max(duration_sec, 1.0))
    regime_path_stability = _clip_unit(1.0 / (1.0 + float(active.regime_path_changes)))

    realized_components = {
        "realized_pnl_efficiency": realized_pnl_efficiency,
        "realized_cost_drag": realized_cost_drag,
        "mae_efficiency": mae_efficiency,
        "mfe_efficiency": mfe_efficiency,
        "duration_efficiency": duration_efficiency,
        "regime_path_stability": regime_path_stability,
    }
    realized_quality_score = sum(realized_components.values()) / float(len(realized_components))
    mae = _safe_ratio(adverse_move, entry_price)
    mfe = _safe_ratio(favorable_move, entry_price)

    return ObjectiveRealizedEvent(
        strategy_id=snapshot.strategy_id,
        symbol=snapshot.symbol,
        entry_rid=snapshot.entry_rid,
        close_rid=close_rid,
        regime_entry=snapshot.regime_entry,
        regime_exit=str(active.regime_exit or active.last_regime or snapshot.regime_entry),
        pretrade_objective_trace=snapshot.pretrade_objective_trace.model_dump(),
        realized_components=realized_components,
        realized_quality_score=realized_quality_score,
        realized_pnl=float(realized_pnl),
        fees=float(fees),
        duration_sec=duration_sec,
        mae=mae,
        mfe=mfe,
        close_reason=close_reason,
        signal_id=snapshot.signal_id,
    )
