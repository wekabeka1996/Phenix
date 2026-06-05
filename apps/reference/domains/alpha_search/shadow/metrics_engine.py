"""
Shadow Metrics Engine
======================

Computes per-scenario metrics from shadow virtual lifecycle outputs.

Metrics per scenario:
  signal_count, buy_count, sell_count, neutral_count,
  confidence_mean/std, coverage_by_symbol, coverage_by_regime,
  virtual_win_rate, avg_pnl_bps, median_pnl_bps, total_pnl_bps,
  max_drawdown_bps, profit_factor, fee_impact_bps, slippage_impact_bps,
  expectancy_bps, mfe_mean, mae_mean, duplicate_score_ratio,
  scenario_uniqueness_score
"""

from __future__ import annotations

import math
import statistics
from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional, Tuple


def _mean(vals: List[float]) -> float:
    return sum(vals) / len(vals) if vals else 0.0


def _std(vals: List[float]) -> float:
    if len(vals) < 2:
        return 0.0
    m = _mean(vals)
    return math.sqrt(sum((x - m) ** 2 for x in vals) / (len(vals) - 1))


def _median(vals: List[float]) -> float:
    if not vals:
        return 0.0
    sv = sorted(vals)
    n = len(sv)
    mid = n // 2
    return sv[mid] if n % 2 else (sv[mid - 1] + sv[mid]) / 2


def _max_drawdown_bps(pnl_series: List[float]) -> float:
    """Max peak-to-trough drawdown in bps from cumulative PnL series."""
    if not pnl_series:
        return 0.0
    peak = 0.0
    cum = 0.0
    max_dd = 0.0
    for p in pnl_series:
        cum += p
        if cum > peak:
            peak = cum
        dd = peak - cum
        if dd > max_dd:
            max_dd = dd
    return round(max_dd, 4)


def compute_scenario_metrics(
    scenario_id: str,
    signal_rows: List[Dict[str, Any]],
    lifecycle_rows: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Compute full metrics for one scenario.

    Args:
        signal_rows: List of raw score rows (from scores.jsonl or materializer).
        lifecycle_rows: List of VirtualLifecycle.to_dict() for completed trades.
    """
    total = len(signal_rows)
    buy_count = sum(1 for r in signal_rows if r.get("side") == "BUY")
    sell_count = sum(1 for r in signal_rows if r.get("side") == "SELL")
    neutral_count = sum(1 for r in signal_rows if r.get("side", "NEUTRAL") == "NEUTRAL")

    confs = [float(r.get("confidence", 0)) for r in signal_rows]
    conf_mean = _mean(confs)
    conf_std = _std(confs)

    # Coverage
    sym_counter: Counter = Counter(r.get("symbol", "?") for r in signal_rows)
    regime_counter: Counter = Counter(r.get("regime", "?") for r in signal_rows)

    # Virtual trade metrics
    pnl_list = [float(lc["virtual_pnl_bps"]) for lc in lifecycle_rows
                if lc.get("virtual_pnl_bps") is not None]
    fee_list = [float(lc.get("virtual_fee_bps", 0)) * 2 for lc in lifecycle_rows]  # round-trip
    slip_list = [float(lc.get("virtual_slippage_bps", 0)) * 2 for lc in lifecycle_rows]
    mfe_list = [float(lc.get("max_favorable_excursion_bps", 0)) for lc in lifecycle_rows]
    mae_list = [float(lc.get("max_adverse_excursion_bps", 0)) for lc in lifecycle_rows]

    n_trades = len(pnl_list)
    wins = [p for p in pnl_list if p > 0]
    losses = [p for p in pnl_list if p <= 0]
    win_rate = len(wins) / n_trades if n_trades else 0.0

    avg_pnl = _mean(pnl_list)
    median_pnl = _median(pnl_list)
    total_pnl = sum(pnl_list)
    max_dd = _max_drawdown_bps(pnl_list)

    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    profit_factor = round(gross_profit / gross_loss, 4) if gross_loss > 0 else (
        float("inf") if gross_profit > 0 else 0.0
    )

    fee_impact = _mean(fee_list)
    slip_impact = _mean(slip_list)
    expectancy = avg_pnl  # net, after fees already included

    # Sharpe (trade-level)
    pnl_std = _std(pnl_list)
    sharpe = round(avg_pnl / pnl_std, 4) if pnl_std > 0 else 0.0

    # Duplicate score ratio: fraction of signal rows with same score as previous
    scores = [r.get("score", r.get("raw_score", 0)) for r in signal_rows]
    dup_count = sum(1 for i in range(1, len(scores)) if scores[i] == scores[i - 1])
    dup_ratio = round(dup_count / max(total - 1, 1), 4)

    # Uniqueness score: 1 - dup_ratio, scaled by signal rate
    signal_rate = (buy_count + sell_count) / max(total, 1)
    uniqueness = round((1 - dup_ratio) * signal_rate * 10, 4)  # 0-10 scale

    return {
        "scenario_id": scenario_id,
        "signal_count": total,
        "buy_count": buy_count,
        "sell_count": sell_count,
        "neutral_count": neutral_count,
        "confidence_mean": round(conf_mean, 4),
        "confidence_std": round(conf_std, 4),
        "coverage_by_symbol": dict(sym_counter.most_common(10)),
        "coverage_by_regime": dict(regime_counter.most_common(10)),
        "virtual_trade_count": n_trades,
        "virtual_win_rate": round(win_rate, 4),
        "avg_virtual_pnl_bps": round(avg_pnl, 4),
        "median_virtual_pnl_bps": round(median_pnl, 4),
        "total_virtual_pnl_bps": round(total_pnl, 4),
        "max_drawdown_bps": round(max_dd, 4),
        "profit_factor": profit_factor,
        "fee_impact_bps": round(fee_impact, 4),
        "slippage_impact_bps": round(slip_impact, 4),
        "expectancy_bps": round(expectancy, 4),
        "sharpe_ratio": sharpe,
        "mfe_mean_bps": round(_mean(mfe_list), 4),
        "mae_mean_bps": round(_mean(mae_list), 4),
        "duplicate_score_ratio": dup_ratio,
        "scenario_uniqueness_score": uniqueness,
    }


def compute_aggregate_metrics(
    all_metrics: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Cross-scenario aggregate: best/worst/families."""
    if not all_metrics:
        return {}

    by_expectancy = sorted(all_metrics, key=lambda x: x.get("expectancy_bps", 0), reverse=True)
    best = by_expectancy[0]
    worst = by_expectancy[-1]

    # Best BUY scenario (most buy signals + positive expectancy)
    best_buy = sorted(
        [m for m in all_metrics if m.get("buy_count", 0) > 0],
        key=lambda x: x.get("expectancy_bps", 0), reverse=True
    )
    best_sell = sorted(
        [m for m in all_metrics if m.get("sell_count", 0) > 0],
        key=lambda x: x.get("expectancy_bps", 0), reverse=True
    )

    # Duplicate-heavy scenarios
    high_dup = [m for m in all_metrics if m.get("duplicate_score_ratio", 0) > 0.9]

    # Low-signal scenarios
    low_signal = [m for m in all_metrics if m.get("signal_count", 0) < 10]

    return {
        "total_scenarios": len(all_metrics),
        "best_scenario_by_expectancy": best.get("scenario_id"),
        "best_scenario_expectancy_bps": best.get("expectancy_bps"),
        "worst_scenario_by_expectancy": worst.get("scenario_id"),
        "worst_scenario_expectancy_bps": worst.get("expectancy_bps"),
        "best_buy_scenario": best_buy[0].get("scenario_id") if best_buy else None,
        "best_sell_scenario": best_sell[0].get("scenario_id") if best_sell else None,
        "high_duplicate_scenarios": [m["scenario_id"] for m in high_dup],
        "low_signal_scenarios": [m["scenario_id"] for m in low_signal],
        "total_virtual_pnl_bps": round(sum(m.get("total_virtual_pnl_bps", 0) for m in all_metrics), 4),
    }


def compute_pairwise_correlations(
    all_metrics: List[Dict[str, Any]],
    score_series_by_id: Dict[str, List[float]],
) -> List[Dict[str, Any]]:
    """
    Compute Pearson correlation between scenario score series.
    Returns list of (scen_a, scen_b, correlation) for all pairs.
    """
    ids = list(score_series_by_id.keys())
    results = []

    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            a_id, b_id = ids[i], ids[j]
            sa = score_series_by_id[a_id]
            sb = score_series_by_id[b_id]
            n = min(len(sa), len(sb))
            if n < 10:
                continue
            sa, sb = sa[:n], sb[:n]
            mean_a, mean_b = _mean(sa), _mean(sb)
            num = sum((sa[k] - mean_a) * (sb[k] - mean_b) for k in range(n))
            denom_a = math.sqrt(sum((x - mean_a) ** 2 for x in sa))
            denom_b = math.sqrt(sum((x - mean_b) ** 2 for x in sb))
            if denom_a * denom_b == 0:
                corr = 1.0 if denom_a == denom_b else 0.0
            else:
                corr = num / (denom_a * denom_b)
            results.append({
                "scenario_a": a_id,
                "scenario_b": b_id,
                "correlation": round(corr, 4),
            })

    return sorted(results, key=lambda x: -abs(x["correlation"]))
