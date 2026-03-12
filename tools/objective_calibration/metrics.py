from __future__ import annotations

from typing import Any

import pandas as pd


DEFAULT_METRIC_WEIGHTS = {
    "realized_quality_score": 0.35,
    "net_pnl_efficiency": 0.25,
    "inverse_cost_drag": 0.15,
    "gate_precision_on_good_trades": 0.10,
    "inverse_churn": 0.10,
    "regime_stability": 0.05,
}


def _safe_mean(df: pd.DataFrame, column: str, default: float = 0.0) -> float:
    if column not in df.columns or df.empty:
        return float(default)
    series = pd.to_numeric(df[column], errors="coerce").dropna()
    return float(series.mean()) if not series.empty else float(default)


def _max_drawdown(series: pd.Series) -> float:
    if series.empty:
        return 0.0
    cumulative = series.cumsum()
    running_max = cumulative.cummax()
    drawdown = cumulative - running_max
    return float(abs(drawdown.min()))


def compute_candidate_summary(
    *,
    attempted_entries: pd.DataFrame,
    realized_trades: pd.DataFrame,
    metric_weights: dict[str, float] | None = None,
    good_trade_threshold: float = 0.0,
) -> dict[str, Any]:
    metric_weights = metric_weights or DEFAULT_METRIC_WEIGHTS
    accepted = realized_trades
    if "candidate_blocked" in realized_trades.columns:
        accepted = realized_trades[~realized_trades["candidate_blocked"].fillna(False)].copy()

    good_mask = pd.to_numeric(realized_trades.get("realized_quality_score"), errors="coerce").fillna(-1.0) >= float(good_trade_threshold)
    blocked_mask = realized_trades["candidate_blocked"].fillna(False) if "candidate_blocked" in realized_trades.columns else pd.Series(False, index=realized_trades.index)
    accepted_good = int((good_mask & ~blocked_mask).sum())
    total_good = int(good_mask.sum())
    gate_precision = float(accepted_good / total_good) if total_good > 0 else 1.0

    churn_value = 0.0
    for column in ("recent_cancel_replace_count", "recent_blocked_intent_count", "recent_reentry_count"):
        if column in attempted_entries.columns:
            churn_value += _safe_mean(attempted_entries, column)
    inverse_churn = 1.0 / (1.0 + max(0.0, churn_value))

    realized_quality = _safe_mean(accepted, "realized_quality_score")
    net_pnl_efficiency = _safe_mean(accepted, "realized_pnl_efficiency", _safe_mean(accepted, "realized_pnl"))
    cost_drag = _safe_mean(accepted, "realized_cost_drag", _safe_mean(accepted, "fees"))
    inverse_cost_drag = 1.0 / (1.0 + max(0.0, abs(cost_drag)))
    regime_stability = _safe_mean(accepted, "regime_path_stability", 1.0)
    trade_count = int(len(accepted))
    missing_input_rate = _safe_mean(attempted_entries, "missing_objective_input_rate", 0.0)
    duplicate_veto_rate = _safe_mean(attempted_entries, "duplicate_veto_rate", 0.0)
    close_path_regression_rate = _safe_mean(attempted_entries, "close_path_regression_rate", 0.0)
    max_drawdown = _max_drawdown(pd.to_numeric(accepted.get("realized_pnl"), errors="coerce").fillna(0.0))

    score = (
        float(metric_weights["realized_quality_score"]) * realized_quality
        + float(metric_weights["net_pnl_efficiency"]) * net_pnl_efficiency
        + float(metric_weights["inverse_cost_drag"]) * inverse_cost_drag
        + float(metric_weights["gate_precision_on_good_trades"]) * gate_precision
        + float(metric_weights["inverse_churn"]) * inverse_churn
        + float(metric_weights["regime_stability"]) * regime_stability
    )
    return {
        "score": score,
        "realized_quality_score": realized_quality,
        "net_pnl_efficiency": net_pnl_efficiency,
        "inverse_cost_drag": inverse_cost_drag,
        "gate_precision_on_good_trades": gate_precision,
        "inverse_churn": inverse_churn,
        "regime_stability": regime_stability,
        "accepted_trade_count": trade_count,
        "candidate_block_rate": float(blocked_mask.mean()) if len(blocked_mask) else 0.0,
        "missing_input_rate": missing_input_rate,
        "duplicate_veto_rate": duplicate_veto_rate,
        "close_path_regression_rate": close_path_regression_rate,
        "max_drawdown": max_drawdown,
    }


def passes_hard_rejection_gates(
    *,
    summary: dict[str, Any],
    baseline_summary: dict[str, Any] | None,
    min_trade_count: int,
    max_drawdown_worsening_frac: float = 0.10,
) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if float(summary.get("missing_input_rate", 0.0)) > 0.0:
        reasons.append("missing_objective_input_rate")
    if float(summary.get("duplicate_veto_rate", 0.0)) > 0.0:
        reasons.append("duplicate_veto_behavior")
    if float(summary.get("close_path_regression_rate", 0.0)) > 0.0:
        reasons.append("close_reduce_only_regression")
    if int(summary.get("accepted_trade_count", 0)) < int(min_trade_count):
        reasons.append("trade_count_below_minimum")
    if baseline_summary is not None:
        baseline_dd = float(baseline_summary.get("max_drawdown", 0.0))
        candidate_dd = float(summary.get("max_drawdown", 0.0))
        if baseline_dd > 0.0 and candidate_dd > baseline_dd * (1.0 + float(max_drawdown_worsening_frac)):
            reasons.append("max_drawdown_worse_than_baseline")
    return (len(reasons) == 0, reasons)
