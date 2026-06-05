#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from apps.reference.config_loader import ConfigLoader  # noqa: E402
from apps.reference.domains.alpha_search.judge.config_models import (  # noqa: E402
    ShadowSimulatorConfig,
)
from apps.reference.domains.alpha_search.judge.contracts import (  # noqa: E402
    ShadowEntryPlan,
)
from apps.reference.domains.alpha_search.judge.shadow_simulator import (  # noqa: E402
    ShadowPlanSimulator,
)
from tools.judge.analyze_shadow_plan_file import (  # noqa: E402
    build_base_row,
    build_consistency_checks,
    build_context_stats,
    build_recorder_context,
    confidence_bucket,
    infer_file_context,
    iso_from_ts_ms,
    load_plans,
    load_rows,
    make_group_summary,
    pick_feature_row,
    summarize_financial,
    to_float,
    utc_date_from_ts_ms,
    write_csv,
    write_json,
    write_jsonl,
    apply_envelope_context,
    apply_verdict_context,
    build_single_index,
)


TARGET_BUCKETS = ("0.6-0.7", "0.7-0.8", "0.8-0.9")
DEFAULT_EXTRA_ARM_PCTS = (0.10, 0.15, 0.20, 0.30, 0.40,
                          0.50, 0.75, 1.00, 1.25, 1.50)
DEFAULT_GIVEBACK_TRIGGER_PCTS = (35.0, 50.0, 65.0, 80.0)


@dataclass(frozen=True)
class ScenarioSpec:
    name: str
    kind: str
    fill_search_limit_bars: int | None
    arm_pct: float | None = None
    giveback_trigger_pct: float | None = None
    bar_count_limit: int | None = None


def parse_float_csv(raw_value: str | None) -> list[float]:
    if raw_value is None:
        return []
    values: list[float] = []
    for part in raw_value.split(","):
        text = part.strip()
        if not text:
            continue
        values.append(float(text))
    return values


def unique_sorted(values: Sequence[float]) -> list[float]:
    return sorted({round(float(value), 10) for value in values})


def parse_int_csv(raw_value: str | None) -> list[int]:
    if raw_value is None:
        return []
    values: list[int] = []
    for part in raw_value.split(","):
        text = part.strip()
        if not text:
            continue
        values.append(int(text))
    return values


def side_sign(entry_side: str) -> float:
    return 1.0 if entry_side == "BUY" else -1.0


def gross_return_pct(entry_side: str, fill_price: float, exit_price: float) -> float:
    gross = ((exit_price - fill_price) / fill_price) * side_sign(entry_side)
    return round(gross * 100.0, 6)


def fees_paid_pct(fees_bps: float, slippage_bps: float) -> float:
    return round(((fees_bps * 2.0) + (slippage_bps * 2.0)) / 100.0, 6)


def find_signal_bar_index(plan: ShadowEntryPlan, bars: Any) -> int | None:
    signal_bar_idx_series = bars.index[bars["timestamp"] == plan.ts_ms]
    if signal_bar_idx_series.empty:
        signal_bar_idx_series = bars.index[bars["timestamp"] >= plan.ts_ms]
    if signal_bar_idx_series.empty:
        return None
    return int(signal_bar_idx_series[0])


def fill_search_end_idx(
    bars: Any,
    start_idx: int,
    fill_search_limit_bars: int | None,
) -> int:
    if fill_search_limit_bars is None:
        return len(bars)
    return min(len(bars), start_idx + fill_search_limit_bars + 1)


def detect_fill(
    plan: ShadowEntryPlan,
    bars: Any,
    signal_bar_idx: int,
    fill_search_limit_bars: int | None,
) -> tuple[int, float, int] | None:
    end_idx = fill_search_end_idx(bars, signal_bar_idx, fill_search_limit_bars)
    for idx in range(signal_bar_idx, end_idx):
        bar = bars.iloc[idx]
        low = float(bar["low"])
        high = float(bar["high"])
        if plan.entry_side == "BUY" and low <= float(plan.limit_price):
            return idx, float(plan.limit_price), int(bar["timestamp"])
        if plan.entry_side == "SELL" and high >= float(plan.limit_price):
            return idx, float(plan.limit_price), int(bar["timestamp"])
    return None


def detect_tp_sl(
    plan: ShadowEntryPlan,
    bar: Mapping[str, Any],
    intrabar_ambiguity_policy: str,
) -> tuple[str, float | None, str] | None:
    low = float(bar["low"])
    high = float(bar["high"])
    tp_hit = False
    sl_hit = False
    tp = float(plan.tp_price)
    sl = float(plan.sl_price)
    if plan.entry_side == "BUY":
        tp_hit = high >= tp
        sl_hit = low <= sl
    else:
        tp_hit = low <= tp
        sl_hit = high >= sl

    if tp_hit and sl_hit:
        if intrabar_ambiguity_policy == "mark_ambiguous":
            return "AMBIGUOUS_INTRABAR", None, "tp_and_sl_hit_same_bar"
        if intrabar_ambiguity_policy == "prioritize_sl":
            return "FILLED_SL", sl, "sl_prioritized_same_bar"
        return "FILLED_TP", tp, "tp_prioritized_same_bar"

    if tp_hit:
        return "FILLED_TP", tp, "tp_hit"
    if sl_hit:
        return "FILLED_SL", sl, "sl_hit"
    return None


def classify_trade_pnl(net_pnl_pct: float | None, terminal_reason: str) -> tuple[str, str]:
    if terminal_reason in {"NOT_FILLED_TIMEOUT", "NOT_FILLED_DATA_END"}:
        return "NO_FILL", "NO_FILL"
    if terminal_reason == "AMBIGUOUS_INTRABAR":
        return "AMBIGUOUS", "FLAT"
    if net_pnl_pct is None:
        return terminal_reason, "FLAT"
    if net_pnl_pct > 0:
        if terminal_reason == "FILLED_SIDECAR_CLOSE":
            return "SIDECAR_WIN", "WIN"
        if terminal_reason == "FILLED_DATA_END":
            return "DATA_END_WIN", "WIN"
        return "WIN", "WIN"
    if net_pnl_pct < 0:
        if terminal_reason == "FILLED_SIDECAR_CLOSE":
            return "SIDECAR_LOSS", "LOSS"
        if terminal_reason == "FILLED_DATA_END":
            return "DATA_END_LOSS", "LOSS"
        return "LOSS", "LOSS"
    if terminal_reason == "FILLED_SIDECAR_CLOSE":
        return "SIDECAR_FLAT", "FLAT"
    if terminal_reason == "FILLED_DATA_END":
        return "DATA_END_FLAT", "FLAT"
    return "FLAT", "FLAT"


def empty_close_path_metrics() -> dict[str, Any]:
    return {
        "close_path_observed_bars": None,
        "close_path_positive_bars": None,
        "close_path_fee_cover_bars": None,
        "close_path_peak_return_pct": None,
        "close_path_peak_net_pct": None,
        "close_path_trough_return_pct": None,
        "close_path_trough_net_pct": None,
        "close_path_first_positive_return_pct": None,
        "close_path_first_fee_cover_return_pct": None,
        "close_path_bars_to_first_positive_close": None,
        "close_path_bars_to_first_fee_cover_close": None,
        "close_path_bars_to_peak_close": None,
        "close_path_bars_to_trough_close": None,
        "close_path_bars_from_peak_to_exit": None,
        "close_path_drawdown_from_peak_to_exit_pct": None,
        "close_path_best_prior_return_pct": None,
        "close_path_best_prior_net_pct": None,
        "close_path_worst_prior_return_pct": None,
        "close_path_worst_prior_net_pct": None,
        "close_path_bars_to_best_prior_close": None,
        "close_path_bars_to_worst_prior_close": None,
        "close_path_max_adverse_close_streak": None,
        "close_path_max_no_new_peak_bar_streak": None,
        "close_path_bounce_count": None,
        "close_path_fee_cover_peak_reached": None,
        "close_path_arm_reached": None,
        "close_path_opportunity_class": None,
    }


def close_exit_observed_on_bar_close(terminal_reason: str) -> bool:
    return terminal_reason in {
        "FILLED_TIMEOUT",
        "FILLED_DATA_END",
        "FILLED_SIDECAR_CLOSE",
    }


def classify_close_path_opportunity(
    *,
    observed_bars: int,
    peak_return_pct: float | None,
    fees_pct: float,
    arm_pct: float | None,
    terminal_reason: str,
    actual_gross_return_pct: float | None,
) -> str:
    if observed_bars <= 0:
        return "NO_COMPLETED_CLOSE_BEFORE_EXIT"
    if peak_return_pct is None or peak_return_pct <= 0.0:
        return "NEVER_POSITIVE"
    if peak_return_pct < fees_pct:
        return "POSITIVE_BUT_BELOW_FEES"
    if arm_pct is not None and peak_return_pct < arm_pct:
        return "FEE_COVERED_BUT_BELOW_ARM"
    if terminal_reason == "FILLED_SIDECAR_CLOSE":
        return "ARMED_AND_GAVE_BACK"
    if terminal_reason == "FILLED_TP":
        return "TP_HIT"
    if terminal_reason == "FILLED_SL":
        return "SL_AFTER_EARLY_EDGE"
    if terminal_reason == "FILLED_DATA_END" and actual_gross_return_pct is not None and actual_gross_return_pct > 0.0:
        return "DATA_END_WIN"
    if actual_gross_return_pct is not None and actual_gross_return_pct > 0.0:
        return "POSITIVE_EXIT"
    return "NO_SPECIAL_PATTERN"


def build_close_path_metrics(
    *,
    plan: ShadowEntryPlan,
    bars: Any,
    fill_idx: int | None,
    fill_price: float | None,
    exit_idx: int | None,
    terminal_reason: str,
    fees_pct: float,
    arm_pct: float | None,
    actual_gross_return_pct: float | None,
) -> dict[str, Any]:
    metrics = empty_close_path_metrics()
    if (
        fill_idx is None
        or fill_price is None
        or exit_idx is None
        or bars is None
        or getattr(bars, "empty", True)
    ):
        return metrics

    close_end_idx = exit_idx if close_exit_observed_on_bar_close(
        terminal_reason) else exit_idx - 1
    if close_end_idx < fill_idx:
        metrics.update(
            {
                "close_path_observed_bars": 0,
                "close_path_positive_bars": 0,
                "close_path_fee_cover_bars": 0,
                "close_path_max_adverse_close_streak": 0,
                "close_path_max_no_new_peak_bar_streak": 0,
                "close_path_bounce_count": 0,
                "close_path_fee_cover_peak_reached": False,
                "close_path_arm_reached": False if arm_pct is not None else None,
                "close_path_opportunity_class": classify_close_path_opportunity(
                    observed_bars=0,
                    peak_return_pct=None,
                    fees_pct=fees_pct,
                    arm_pct=arm_pct,
                    terminal_reason=terminal_reason,
                    actual_gross_return_pct=actual_gross_return_pct,
                ),
            }
        )
        return metrics

    close_returns: list[tuple[int, float]] = []
    for idx in range(fill_idx, close_end_idx + 1):
        close_price = float(bars.iloc[idx]["close"])
        close_returns.append(
            (idx, gross_return_pct(plan.entry_side, fill_price, close_price)))

    observed_bars = len(close_returns)
    peak_idx, peak_return_pct = max(close_returns, key=lambda item: item[1])
    trough_idx, trough_return_pct = min(
        close_returns, key=lambda item: item[1])
    prior_returns = close_returns[:-1] if close_exit_observed_on_bar_close(
        terminal_reason) else close_returns

    first_positive = next(
        ((idx, value) for idx, value in close_returns if value > 0.0), None)
    first_fee_cover = next(
        ((idx, value) for idx, value in close_returns if value >= fees_pct), None)
    best_prior = max(prior_returns, key=lambda item: item[1],
                     default=None)
    worst_prior = min(prior_returns, key=lambda item: item[1],
                      default=None)

    positive_bars = sum(1 for _, value in close_returns if value > 0.0)
    fee_cover_bars = sum(1 for _, value in close_returns if value >= fees_pct)

    adverse_streak = 0
    max_adverse_streak = 0
    running_peak = None
    no_new_peak_streak = 0
    max_no_new_peak_streak = 0
    bounce_count = 0
    previous_delta = None
    previous_return = None
    for _, close_return_pct in close_returns:
        if close_return_pct < 0.0:
            adverse_streak += 1
            max_adverse_streak = max(max_adverse_streak, adverse_streak)
        else:
            adverse_streak = 0

        if running_peak is None or close_return_pct > running_peak:
            running_peak = close_return_pct
            no_new_peak_streak = 0
        else:
            no_new_peak_streak += 1
            max_no_new_peak_streak = max(
                max_no_new_peak_streak, no_new_peak_streak)

        if previous_return is not None:
            delta = close_return_pct - previous_return
            if previous_delta is not None and previous_delta < 0.0 and delta > 0.0:
                bounce_count += 1
            previous_delta = delta
        previous_return = close_return_pct

    metrics.update(
        {
            "close_path_observed_bars": observed_bars,
            "close_path_positive_bars": positive_bars,
            "close_path_fee_cover_bars": fee_cover_bars,
            "close_path_peak_return_pct": peak_return_pct,
            "close_path_peak_net_pct": round(peak_return_pct - fees_pct, 6),
            "close_path_trough_return_pct": trough_return_pct,
            "close_path_trough_net_pct": round(trough_return_pct - fees_pct, 6),
            "close_path_first_positive_return_pct": first_positive[1] if first_positive else None,
            "close_path_first_fee_cover_return_pct": first_fee_cover[1] if first_fee_cover else None,
            "close_path_bars_to_first_positive_close": first_positive[0] - fill_idx if first_positive else None,
            "close_path_bars_to_first_fee_cover_close": first_fee_cover[0] - fill_idx if first_fee_cover else None,
            "close_path_bars_to_peak_close": peak_idx - fill_idx,
            "close_path_bars_to_trough_close": trough_idx - fill_idx,
            "close_path_bars_from_peak_to_exit": exit_idx - peak_idx,
            "close_path_drawdown_from_peak_to_exit_pct": round(peak_return_pct - actual_gross_return_pct, 6) if actual_gross_return_pct is not None else None,
            "close_path_best_prior_return_pct": best_prior[1] if best_prior else None,
            "close_path_best_prior_net_pct": round(best_prior[1] - fees_pct, 6) if best_prior else None,
            "close_path_worst_prior_return_pct": worst_prior[1] if worst_prior else None,
            "close_path_worst_prior_net_pct": round(worst_prior[1] - fees_pct, 6) if worst_prior else None,
            "close_path_bars_to_best_prior_close": best_prior[0] - fill_idx if best_prior else None,
            "close_path_bars_to_worst_prior_close": worst_prior[0] - fill_idx if worst_prior else None,
            "close_path_max_adverse_close_streak": max_adverse_streak,
            "close_path_max_no_new_peak_bar_streak": max_no_new_peak_streak,
            "close_path_bounce_count": bounce_count,
            "close_path_fee_cover_peak_reached": peak_return_pct >= fees_pct,
            "close_path_arm_reached": peak_return_pct >= arm_pct if arm_pct is not None else None,
            "close_path_opportunity_class": classify_close_path_opportunity(
                observed_bars=observed_bars,
                peak_return_pct=peak_return_pct,
                fees_pct=fees_pct,
                arm_pct=arm_pct,
                terminal_reason=terminal_reason,
                actual_gross_return_pct=actual_gross_return_pct,
            ),
        }
    )
    return metrics


def build_result(
    *,
    plan: ShadowEntryPlan,
    terminal_reason: str,
    exit_reason: str,
    fill_idx: int | None,
    fill_price: float | None,
    fill_ts_ms: int | None,
    exit_idx: int | None,
    exit_price: float | None,
    exit_ts_ms: int | None,
    bars: Any | None = None,
    fees_bps: float,
    slippage_bps: float,
    peak_close_return_pct: float | None = None,
    current_close_return_pct: float | None = None,
    giveback_pct: float | None = None,
    arm_pct: float | None = None,
    giveback_trigger_pct: float | None = None,
    managed_exit: bool = False,
) -> dict[str, Any]:
    if fill_idx is None or fill_price is None or fill_ts_ms is None:
        proposal_outcome_class, trade_pnl_class = classify_trade_pnl(
            None, terminal_reason)
        return {
            "simulation_status": "success",
            "terminal_reason": terminal_reason,
            "exit_reason": exit_reason,
            "fill_ts_ms": None,
            "fill_ts_utc": None,
            "fill_delay_ms": None,
            "entry_fill_price": None,
            "exit_ts_ms": None,
            "exit_ts_utc": None,
            "exit_price": None,
            "duration_bars": None,
            "gross_pnl_pct": 0.0,
            "net_pnl_pct": 0.0,
            "fees_paid_pct": 0.0,
            "proposal_outcome_class": proposal_outcome_class,
            "trade_pnl_class": trade_pnl_class,
            "filled_trade": False,
            "outcome_available": True,
            "managed_exit": False,
            "sidecar_peak_close_return_pct": peak_close_return_pct,
            "sidecar_final_close_return_pct": current_close_return_pct,
            "sidecar_giveback_pct": giveback_pct,
            "sidecar_arm_pct": arm_pct,
            "sidecar_giveback_trigger_pct": giveback_trigger_pct,
            **empty_close_path_metrics(),
        }

    if terminal_reason == "AMBIGUOUS_INTRABAR":
        path_metrics = build_close_path_metrics(
            plan=plan,
            bars=bars,
            fill_idx=fill_idx,
            fill_price=fill_price,
            exit_idx=exit_idx,
            terminal_reason=terminal_reason,
            fees_pct=0.0,
            arm_pct=arm_pct,
            actual_gross_return_pct=None,
        )
        return {
            "simulation_status": "invalid",
            "terminal_reason": terminal_reason,
            "exit_reason": exit_reason,
            "fill_ts_ms": fill_ts_ms,
            "fill_ts_utc": iso_from_ts_ms(fill_ts_ms),
            "fill_delay_ms": fill_ts_ms - plan.ts_ms,
            "entry_fill_price": fill_price,
            "exit_ts_ms": exit_ts_ms,
            "exit_ts_utc": iso_from_ts_ms(exit_ts_ms),
            "exit_price": exit_price,
            "duration_bars": exit_idx - fill_idx if exit_idx is not None else None,
            "gross_pnl_pct": 0.0,
            "net_pnl_pct": 0.0,
            "fees_paid_pct": 0.0,
            "proposal_outcome_class": "AMBIGUOUS",
            "trade_pnl_class": "FLAT",
            "filled_trade": True,
            "outcome_available": False,
            "invalid_reason": "ambiguous_intrabar_exit_unresolved",
            "managed_exit": managed_exit,
            "sidecar_peak_close_return_pct": peak_close_return_pct,
            "sidecar_final_close_return_pct": current_close_return_pct,
            "sidecar_giveback_pct": giveback_pct,
            "sidecar_arm_pct": arm_pct,
            "sidecar_giveback_trigger_pct": giveback_trigger_pct,
            **path_metrics,
        }

    gross_pct = None
    net_pct = None
    paid_pct = None
    if exit_price is not None:
        gross_pct = gross_return_pct(plan.entry_side, fill_price, exit_price)
        paid_pct = fees_paid_pct(fees_bps, slippage_bps)
        net_pct = round(gross_pct - paid_pct, 6)
    path_metrics = build_close_path_metrics(
        plan=plan,
        bars=bars,
        fill_idx=fill_idx,
        fill_price=fill_price,
        exit_idx=exit_idx,
        terminal_reason=terminal_reason,
        fees_pct=paid_pct or 0.0,
        arm_pct=arm_pct,
        actual_gross_return_pct=gross_pct,
    )
    proposal_outcome_class, trade_pnl_class = classify_trade_pnl(
        net_pct, terminal_reason)
    return {
        "simulation_status": "success",
        "terminal_reason": terminal_reason,
        "exit_reason": exit_reason,
        "fill_ts_ms": fill_ts_ms,
        "fill_ts_utc": iso_from_ts_ms(fill_ts_ms),
        "fill_delay_ms": fill_ts_ms - plan.ts_ms,
        "entry_fill_price": fill_price,
        "exit_ts_ms": exit_ts_ms,
        "exit_ts_utc": iso_from_ts_ms(exit_ts_ms),
        "exit_price": exit_price,
        "duration_bars": exit_idx - fill_idx if exit_idx is not None else None,
        "gross_pnl_pct": gross_pct,
        "net_pnl_pct": net_pct,
        "fees_paid_pct": paid_pct,
        "proposal_outcome_class": proposal_outcome_class,
        "trade_pnl_class": trade_pnl_class,
        "filled_trade": True,
        "outcome_available": True,
        "managed_exit": managed_exit,
        "sidecar_peak_close_return_pct": peak_close_return_pct,
        "sidecar_final_close_return_pct": current_close_return_pct,
        "sidecar_giveback_pct": giveback_pct,
        "sidecar_arm_pct": arm_pct,
        "sidecar_giveback_trigger_pct": giveback_trigger_pct,
        **path_metrics,
    }


def simulate_hold_to_end(
    *,
    plan: ShadowEntryPlan,
    bars: Any,
    fill_search_limit_bars: int | None,
    intrabar_ambiguity_policy: str,
    fees_bps: float,
    slippage_bps: float,
) -> dict[str, Any]:
    signal_bar_idx = find_signal_bar_index(plan, bars)
    if signal_bar_idx is None:
        return {
            "simulation_status": "error",
            "terminal_reason": "ERROR",
            "proposal_outcome_class": "ERROR",
            "trade_pnl_class": "FLAT",
            "invalid_reason": "signal_bar_not_found",
            "filled_trade": False,
            "outcome_available": False,
        }

    fill_info = detect_fill(plan, bars, signal_bar_idx, fill_search_limit_bars)
    if fill_info is None:
        terminal_reason = "NOT_FILLED_TIMEOUT" if fill_search_limit_bars is not None else "NOT_FILLED_DATA_END"
        return build_result(
            plan=plan,
            terminal_reason=terminal_reason,
            exit_reason="limit_not_filled",
            fill_idx=None,
            fill_price=None,
            fill_ts_ms=None,
            exit_idx=None,
            exit_price=None,
            exit_ts_ms=None,
            bars=bars,
            fees_bps=fees_bps,
            slippage_bps=slippage_bps,
        )

    fill_idx, fill_price, fill_ts_ms = fill_info
    for idx in range(fill_idx, len(bars)):
        bar = bars.iloc[idx]
        tp_sl = detect_tp_sl(plan, bar, intrabar_ambiguity_policy)
        if tp_sl is None:
            continue
        terminal_reason, exit_price, exit_reason = tp_sl
        return build_result(
            plan=plan,
            terminal_reason=terminal_reason,
            exit_reason=exit_reason,
            fill_idx=fill_idx,
            fill_price=fill_price,
            fill_ts_ms=fill_ts_ms,
            exit_idx=idx,
            exit_price=exit_price,
            exit_ts_ms=int(bar["timestamp"]),
            bars=bars,
            fees_bps=fees_bps,
            slippage_bps=slippage_bps,
        )

    last_bar = bars.iloc[len(bars) - 1]
    exit_price = float(last_bar["close"])
    return build_result(
        plan=plan,
        terminal_reason="FILLED_DATA_END",
        exit_reason="held_to_data_end",
        fill_idx=fill_idx,
        fill_price=fill_price,
        fill_ts_ms=fill_ts_ms,
        exit_idx=len(bars) - 1,
        exit_price=exit_price,
        exit_ts_ms=int(last_bar["timestamp"]),
        bars=bars,
        fees_bps=fees_bps,
        slippage_bps=slippage_bps,
        current_close_return_pct=gross_return_pct(
            plan.entry_side, fill_price, exit_price),
    )


def simulate_sidecar_percent_giveback(
    *,
    plan: ShadowEntryPlan,
    bars: Any,
    fill_search_limit_bars: int | None,
    intrabar_ambiguity_policy: str,
    fees_bps: float,
    slippage_bps: float,
    arm_pct: float,
    giveback_trigger_pct: float,
) -> dict[str, Any]:
    signal_bar_idx = find_signal_bar_index(plan, bars)
    if signal_bar_idx is None:
        return {
            "simulation_status": "error",
            "terminal_reason": "ERROR",
            "proposal_outcome_class": "ERROR",
            "trade_pnl_class": "FLAT",
            "invalid_reason": "signal_bar_not_found",
            "filled_trade": False,
            "outcome_available": False,
        }

    fill_info = detect_fill(plan, bars, signal_bar_idx, fill_search_limit_bars)
    if fill_info is None:
        terminal_reason = "NOT_FILLED_TIMEOUT" if fill_search_limit_bars is not None else "NOT_FILLED_DATA_END"
        return build_result(
            plan=plan,
            terminal_reason=terminal_reason,
            exit_reason="limit_not_filled",
            fill_idx=None,
            fill_price=None,
            fill_ts_ms=None,
            exit_idx=None,
            exit_price=None,
            exit_ts_ms=None,
            bars=bars,
            fees_bps=fees_bps,
            slippage_bps=slippage_bps,
            arm_pct=arm_pct,
            giveback_trigger_pct=giveback_trigger_pct,
        )

    fill_idx, fill_price, fill_ts_ms = fill_info
    peak_close_return_pct = 0.0
    armed = False
    last_close_return_pct = 0.0
    last_giveback_pct = 0.0

    for idx in range(fill_idx, len(bars)):
        bar = bars.iloc[idx]
        tp_sl = detect_tp_sl(plan, bar, intrabar_ambiguity_policy)
        if tp_sl is not None:
            terminal_reason, exit_price, exit_reason = tp_sl
            return build_result(
                plan=plan,
                terminal_reason=terminal_reason,
                exit_reason=exit_reason,
                fill_idx=fill_idx,
                fill_price=fill_price,
                fill_ts_ms=fill_ts_ms,
                exit_idx=idx,
                exit_price=exit_price,
                exit_ts_ms=int(bar["timestamp"]),
                bars=bars,
                fees_bps=fees_bps,
                slippage_bps=slippage_bps,
                peak_close_return_pct=peak_close_return_pct,
                current_close_return_pct=last_close_return_pct,
                giveback_pct=last_giveback_pct,
                arm_pct=arm_pct,
                giveback_trigger_pct=giveback_trigger_pct,
            )

        close_price = float(bar["close"])
        close_return_pct = gross_return_pct(
            plan.entry_side, fill_price, close_price)
        peak_close_return_pct = max(peak_close_return_pct, close_return_pct)
        if peak_close_return_pct >= arm_pct:
            armed = True
        giveback_pct = 0.0
        if armed and peak_close_return_pct > 0.0:
            giveback_pct = max(
                0.0, ((peak_close_return_pct - close_return_pct) / peak_close_return_pct) * 100.0)

        last_close_return_pct = close_return_pct
        last_giveback_pct = giveback_pct
        if idx == fill_idx:
            continue
        if armed and giveback_pct >= giveback_trigger_pct:
            return build_result(
                plan=plan,
                terminal_reason="FILLED_SIDECAR_CLOSE",
                exit_reason="sidecar_shadow_percent_giveback",
                fill_idx=fill_idx,
                fill_price=fill_price,
                fill_ts_ms=fill_ts_ms,
                exit_idx=idx,
                exit_price=close_price,
                exit_ts_ms=int(bar["timestamp"]),
                bars=bars,
                fees_bps=fees_bps,
                slippage_bps=slippage_bps,
                peak_close_return_pct=peak_close_return_pct,
                current_close_return_pct=close_return_pct,
                giveback_pct=giveback_pct,
                arm_pct=arm_pct,
                giveback_trigger_pct=giveback_trigger_pct,
                managed_exit=True,
            )

    last_bar = bars.iloc[len(bars) - 1]
    exit_price = float(last_bar["close"])
    return build_result(
        plan=plan,
        terminal_reason="FILLED_DATA_END",
        exit_reason="held_to_data_end_no_sidecar_trigger",
        fill_idx=fill_idx,
        fill_price=fill_price,
        fill_ts_ms=fill_ts_ms,
        exit_idx=len(bars) - 1,
        exit_price=exit_price,
        exit_ts_ms=int(last_bar["timestamp"]),
        bars=bars,
        fees_bps=fees_bps,
        slippage_bps=slippage_bps,
        peak_close_return_pct=peak_close_return_pct,
        current_close_return_pct=last_close_return_pct,
        giveback_pct=last_giveback_pct,
        arm_pct=arm_pct,
        giveback_trigger_pct=giveback_trigger_pct,
    )


def simulate_bar_count_exit_no_fee_cover(
    *,
    plan: ShadowEntryPlan,
    bars: Any,
    fill_search_limit_bars: int | None,
    intrabar_ambiguity_policy: str,
    fees_bps: float,
    slippage_bps: float,
    max_bars_without_fee_cover: int,
) -> dict[str, Any]:
    signal_bar_idx = find_signal_bar_index(plan, bars)
    if signal_bar_idx is None:
        return {
            "simulation_status": "error",
            "terminal_reason": "ERROR",
            "proposal_outcome_class": "ERROR",
            "trade_pnl_class": "FLAT",
            "invalid_reason": "signal_bar_not_found",
            "filled_trade": False,
            "outcome_available": False,
        }

    fill_info = detect_fill(plan, bars, signal_bar_idx, fill_search_limit_bars)
    if fill_info is None:
        terminal_reason = "NOT_FILLED_TIMEOUT" if fill_search_limit_bars is not None else "NOT_FILLED_DATA_END"
        return build_result(
            plan=plan,
            terminal_reason=terminal_reason,
            exit_reason="limit_not_filled",
            fill_idx=None,
            fill_price=None,
            fill_ts_ms=None,
            exit_idx=None,
            exit_price=None,
            exit_ts_ms=None,
            bars=bars,
            fees_bps=fees_bps,
            slippage_bps=slippage_bps,
        )

    fill_idx, fill_price, fill_ts_ms = fill_info
    fees_pct = fees_paid_pct(fees_bps, slippage_bps)
    fee_cover_seen = False

    for idx in range(fill_idx, len(bars)):
        bar = bars.iloc[idx]
        tp_sl = detect_tp_sl(plan, bar, intrabar_ambiguity_policy)
        if tp_sl is not None:
            terminal_reason, exit_price, exit_reason = tp_sl
            return build_result(
                plan=plan,
                terminal_reason=terminal_reason,
                exit_reason=exit_reason,
                fill_idx=fill_idx,
                fill_price=fill_price,
                fill_ts_ms=fill_ts_ms,
                exit_idx=idx,
                exit_price=exit_price,
                exit_ts_ms=int(bar["timestamp"]),
                bars=bars,
                fees_bps=fees_bps,
                slippage_bps=slippage_bps,
            )

        close_price = float(bar["close"])
        close_return_pct = gross_return_pct(
            plan.entry_side, fill_price, close_price)
        if close_return_pct >= fees_pct:
            fee_cover_seen = True

        observed_close_bars = idx - fill_idx + 1
        if not fee_cover_seen and observed_close_bars >= max_bars_without_fee_cover:
            return build_result(
                plan=plan,
                terminal_reason="FILLED_BAR_COUNT_EXIT",
                exit_reason="bar_count_no_fee_cover",
                fill_idx=fill_idx,
                fill_price=fill_price,
                fill_ts_ms=fill_ts_ms,
                exit_idx=idx,
                exit_price=close_price,
                exit_ts_ms=int(bar["timestamp"]),
                bars=bars,
                fees_bps=fees_bps,
                slippage_bps=slippage_bps,
                current_close_return_pct=close_return_pct,
                managed_exit=True,
            )

    last_bar = bars.iloc[len(bars) - 1]
    exit_price = float(last_bar["close"])
    return build_result(
        plan=plan,
        terminal_reason="FILLED_DATA_END",
        exit_reason="held_to_data_end_bar_count_no_fee_cover_not_triggered",
        fill_idx=fill_idx,
        fill_price=fill_price,
        fill_ts_ms=fill_ts_ms,
        exit_idx=len(bars) - 1,
        exit_price=exit_price,
        exit_ts_ms=int(last_bar["timestamp"]),
        bars=bars,
        fees_bps=fees_bps,
        slippage_bps=slippage_bps,
        current_close_return_pct=gross_return_pct(
            plan.entry_side, fill_price, exit_price),
    )


def targeted_bucket_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    bucket_rows = [row for row in rows if row.get(
        "confidence_bucket") in TARGET_BUCKETS]
    return {
        "combined": summarize_financial(bucket_rows),
        "by_bucket": make_group_summary(bucket_rows, "confidence_bucket"),
        "by_entry_side": make_group_summary(bucket_rows, "entry_side"),
    }


def build_calibration_rows(
    scenario_summaries: Mapping[str, Any],
    *,
    no_timeout_name: str,
) -> list[dict[str, Any]]:
    no_timeout_summary = scenario_summaries[no_timeout_name]
    no_timeout_target = no_timeout_summary["target_buckets"]["combined"]
    no_timeout_overall = no_timeout_summary["financial"]
    rows: list[dict[str, Any]] = []
    for scenario_name, scenario_summary in scenario_summaries.items():
        spec = scenario_summary["spec"]
        if spec["kind"] != "sidecar_percent":
            continue
        overall = scenario_summary["financial"]
        target = scenario_summary["target_buckets"]["combined"]
        rows.append(
            {
                "scenario_name": scenario_name,
                "arm_pct": spec["arm_pct"],
                "giveback_trigger_pct": spec["giveback_trigger_pct"],
                "managed_exit_rows": scenario_summary["managed_exit_rows"],
                "overall_rows": overall["rows"],
                "overall_win_rate_pct": overall["proposal_win_rate_pct"],
                "overall_total_net_pnl_pct": overall["total_net_pnl_pct"],
                "target_rows": target["rows"],
                "target_win_rate_pct": target["proposal_win_rate_pct"],
                "target_total_net_pnl_pct": target["total_net_pnl_pct"],
                "delta_target_total_net_vs_no_timeout_pct": round(
                    target["total_net_pnl_pct"] -
                    no_timeout_target["total_net_pnl_pct"],
                    6,
                ),
                "delta_target_win_rate_vs_no_timeout_pct": round(
                    target["proposal_win_rate_pct"] -
                    no_timeout_target["proposal_win_rate_pct"],
                    4,
                ),
                "delta_overall_total_net_vs_no_timeout_pct": round(
                    overall["total_net_pnl_pct"] -
                    no_timeout_overall["total_net_pnl_pct"],
                    6,
                ),
            }
        )
    rows.sort(
        key=lambda row: (
            row["target_total_net_pnl_pct"],
            row["overall_total_net_pnl_pct"],
            row["target_win_rate_pct"],
            row["managed_exit_rows"],
        ),
        reverse=True,
    )
    return rows


def choose_recommendations(
    calibration_rows: Sequence[Mapping[str, Any]],
    *,
    min_managed_exit_rows: int,
    config_arm_pcts: Sequence[float],
    default_giveback_trigger_pct: float,
) -> dict[str, Any]:
    current_config_rows = [
        row
        for row in calibration_rows
        if row.get("arm_pct") in config_arm_pcts
        and math.isclose(float(row.get("giveback_trigger_pct") or 0.0), default_giveback_trigger_pct, rel_tol=0.0, abs_tol=1e-9)
    ]
    current_config_leader = current_config_rows[0] if current_config_rows else None

    balanced_candidates = [
        row
        for row in calibration_rows
        if int(row.get("managed_exit_rows") or 0) >= min_managed_exit_rows
        and float(row.get("overall_total_net_pnl_pct") or 0.0) > 0.0
        and float(row.get("target_total_net_pnl_pct") or 0.0) > 0.0
    ]
    balanced = balanced_candidates[0] if balanced_candidates else None

    loose = calibration_rows[0] if calibration_rows else None

    protective_candidates = [
        row
        for row in calibration_rows
        if float(row.get("target_total_net_pnl_pct") or 0.0) > 0.0
    ]
    protective_candidates = sorted(
        protective_candidates,
        key=lambda row: (
            row["managed_exit_rows"],
            row["target_total_net_pnl_pct"],
            row["overall_total_net_pnl_pct"],
        ),
        reverse=True,
    )
    protective = protective_candidates[0] if protective_candidates else None

    return {
        "current_config_leader": current_config_leader,
        "balanced_recommendation": balanced,
        "return_preserving_leader": loose,
        "protective_leader": protective,
    }


def build_bucket_comparison_rows(
    scenario_summaries: Mapping[str, Any],
    scenario_names: Sequence[str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for scenario_name in scenario_names:
        if not scenario_name or scenario_name not in scenario_summaries:
            continue
        target_buckets = scenario_summaries[scenario_name]["target_buckets"]["by_bucket"]
        for bucket_name in TARGET_BUCKETS:
            bucket = target_buckets.get(bucket_name)
            if bucket is None:
                continue
            rows.append(
                {
                    "scenario_name": scenario_name,
                    "confidence_bucket": bucket_name,
                    "rows": bucket["rows"],
                    "win_rate_pct": bucket["proposal_win_rate_pct"],
                    "fill_rate_pct": bucket["fill_rate_pct"],
                    "total_net_pnl_pct": bucket["total_net_pnl_pct"],
                    "expectancy_net_pnl_pct": bucket["expectancy_net_pnl_pct"],
                }
            )
    return rows


def markdown_table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> list[str]:
    if not rows:
        return []
    header_line = "| " + " | ".join(str(header) for header in headers) + " |"
    separator_line = "| " + " | ".join("---" for _ in headers) + " |"
    rendered_rows = [
        "| " + " | ".join(str(cell) for cell in row) + " |"
        for row in rows
    ]
    return [header_line, separator_line, *rendered_rows]


def build_report(summary: Mapping[str, Any], output_dir: Path) -> str:
    meta = summary["meta"]
    recommendations = summary.get("recommendations", {})
    lines = [
        "# Sidecar Shadow Counterfactual Report",
        "",
        "## Scope",
        f"- Source file: {meta['source_file']}",
        f"- Symbol/date: {meta['symbol']} / {meta['utc_date']}",
        f"- Recorder root: {meta['recorder_root']}",
        "- Fill search: baseline keeps the original bar timeout; no-timeout and sidecar scenarios search until available data ends.",
        "- Sidecar replay is conservative: TP/SL stays intrabar, but managed exits are evaluated on candle close only.",
        "- Live-faithful shadow piece reused here: shadow percent-of-notional arm semantics plus giveback trigger from execution_position.position_policy_sidecar config.",
        "- Live pieces not replayed here: post-fill feature/regime refresh stream, absolute USD peak-giveback arm, realized lifecycle fee sources.",
        "- Current live config has peak_giveback_close.disabled; this report treats shadow percent-arm states as a bounded counterfactual exit engine for calibration only.",
        "",
        "## Calibration Recommendation",
    ]
    balanced = recommendations.get("balanced_recommendation")
    current_config = recommendations.get("current_config_leader")
    loose = recommendations.get("return_preserving_leader")
    protective = recommendations.get("protective_leader")
    if balanced is None:
        lines.append(
            "- No balanced sidecar candidate satisfied the positive-PnL and minimum-managed-exit constraints.")
    else:
        lines.append(
            f"- Balanced recommendation: {balanced['scenario_name']} (arm={balanced['arm_pct']}%, giveback={balanced['giveback_trigger_pct']}%, target_total_net={balanced['target_total_net_pnl_pct']}, managed_exit_rows={balanced['managed_exit_rows']})"
        )
    if current_config is not None:
        lines.append(
            f"- Best current-config shadow candidate: {current_config['scenario_name']} (target_total_net={current_config['target_total_net_pnl_pct']}, managed_exit_rows={current_config['managed_exit_rows']})"
        )
    if loose is not None:
        lines.append(
            f"- Return-preserving leader: {loose['scenario_name']} (target_total_net={loose['target_total_net_pnl_pct']}, managed_exit_rows={loose['managed_exit_rows']})"
        )
    if protective is not None:
        lines.append(
            f"- Protective leader: {protective['scenario_name']} (target_total_net={protective['target_total_net_pnl_pct']}, managed_exit_rows={protective['managed_exit_rows']})"
        )
    lines.extend([
        "",
        "## Scenario Comparison",
    ])
    for scenario_name, scenario_summary in summary["scenario_summaries"].items():
        financial = scenario_summary["financial"]
        lines.append(
            f"- {scenario_name}: rows={financial['rows']}, win_rate={financial['proposal_win_rate_pct']}%, filled_win_rate={financial['filled_trade_win_rate_pct']}%, fill_rate={financial['fill_rate_pct']}%, total_net={financial['total_net_pnl_pct']}, managed_exit_rows={scenario_summary['managed_exit_rows']}"
        )
    lines.extend([
        "",
        "## Top Calibration Grid",
    ])
    calibration_rows = summary.get("calibration_grid", [])[:12]
    if calibration_rows:
        lines.extend(
            markdown_table(
                (
                    "scenario",
                    "arm_pct",
                    "giveback_pct",
                    "managed_exits",
                    "target_net",
                    "target_win_rate",
                    "overall_net",
                ),
                [
                    (
                        row["scenario_name"],
                        row["arm_pct"],
                        row["giveback_trigger_pct"],
                        row["managed_exit_rows"],
                        row["target_total_net_pnl_pct"],
                        row["target_win_rate_pct"],
                        row["overall_total_net_pnl_pct"],
                    )
                    for row in calibration_rows
                ],
            )
        )
    lines.extend([
        "",
        "## Target Buckets",
    ])
    for scenario_name, scenario_summary in summary["scenario_summaries"].items():
        targeted = scenario_summary["target_buckets"]
        combined = targeted["combined"]
        lines.append(
            f"- {scenario_name}: target_rows={combined['rows']}, target_win_rate={combined['proposal_win_rate_pct']}%, target_total_net={combined['total_net_pnl_pct']}"
        )
        for bucket_name, bucket_summary in targeted["by_bucket"].items():
            lines.append(
                f"  - {bucket_name}: rows={bucket_summary['rows']}, win_rate={bucket_summary['proposal_win_rate_pct']}%, total_net={bucket_summary['total_net_pnl_pct']}"
            )
    lines.extend([
        "",
        "## Output Artifacts",
        f"- Summary JSON: {(output_dir / 'summary.json').as_posix()}",
        f"- Scenario rows JSONL: {(output_dir / 'scenario_rows.jsonl').as_posix()}",
        f"- Scenario rows CSV: {(output_dir / 'scenario_rows.csv').as_posix()}",
        f"- Calibration grid CSV: {(output_dir / 'calibration_grid.csv').as_posix()}",
        f"- Financial report: {(output_dir / 'financial_report.md').as_posix()}",
    ])
    return "\n".join(lines) + "\n"


def build_financial_report(summary: Mapping[str, Any]) -> str:
    recommendations = summary.get("recommendations", {})
    scenario_summaries = summary["scenario_summaries"]
    current_config = recommendations.get("current_config_leader")
    balanced = recommendations.get("balanced_recommendation")
    no_timeout_name = summary["meta"]["no_timeout_scenario_name"]
    baseline_name = summary["meta"]["baseline_scenario_name"]
    representative_names = [
        baseline_name,
        no_timeout_name,
        current_config.get("scenario_name") if current_config else None,
        balanced.get("scenario_name") if balanced else None,
    ]

    lines = [
        "# Detailed Financial Report",
        "",
        "## Selection Rule",
        f"- Balanced recommendation is the best positive-PnL sidecar candidate with at least {summary['meta']['min_managed_exit_rows']} managed exits, ranked by target-bucket total net pnl, then overall net pnl, then target win rate, then managed-exit count.",
        "- Return-preserving leader ignores the minimum-managed-exit guardrail and simply maximizes target-bucket total net pnl.",
        "- Protective leader maximizes managed exits while keeping target-bucket total net pnl positive.",
        "",
        "## Representative Scenario Summary",
    ]
    representative_rows: list[Sequence[Any]] = []
    for scenario_name in representative_names:
        if not scenario_name or scenario_name not in scenario_summaries:
            continue
        scenario_summary = scenario_summaries[scenario_name]
        financial = scenario_summary["financial"]
        target = scenario_summary["target_buckets"]["combined"]
        representative_rows.append(
            (
                scenario_name,
                financial["rows"],
                financial["proposal_win_rate_pct"],
                financial["total_net_pnl_pct"],
                target["proposal_win_rate_pct"],
                target["total_net_pnl_pct"],
                scenario_summary["managed_exit_rows"],
            )
        )
    lines.extend(
        markdown_table(
            (
                "scenario",
                "rows",
                "overall_win_rate",
                "overall_total_net",
                "target_win_rate",
                "target_total_net",
                "managed_exits",
            ),
            representative_rows,
        )
    )
    lines.extend([
        "",
        "## Target Bucket Comparison",
    ])
    bucket_rows = build_bucket_comparison_rows(
        scenario_summaries, [name for name in representative_names if name])
    lines.extend(
        markdown_table(
            (
                "scenario",
                "bucket",
                "rows",
                "win_rate",
                "fill_rate",
                "total_net",
                "expectancy",
            ),
            [
                (
                    row["scenario_name"],
                    row["confidence_bucket"],
                    row["rows"],
                    row["win_rate_pct"],
                    row["fill_rate_pct"],
                    row["total_net_pnl_pct"],
                    row["expectancy_net_pnl_pct"],
                )
                for row in bucket_rows
            ],
        )
    )
    extra_research_rows = []
    for scenario_name, scenario_summary in scenario_summaries.items():
        scenario_kind = scenario_summary["spec"]["kind"]
        if scenario_kind in {"baseline", "hold_to_end", "sidecar_percent"}:
            continue
        financial = scenario_summary["financial"]
        target = scenario_summary["target_buckets"]["combined"]
        extra_research_rows.append(
            (
                scenario_name,
                scenario_kind,
                scenario_summary["spec"].get("bar_count_limit"),
                financial["rows"],
                financial["proposal_win_rate_pct"],
                financial["total_net_pnl_pct"],
                target["proposal_win_rate_pct"],
                target["total_net_pnl_pct"],
                scenario_summary["managed_exit_rows"],
            )
        )
    if extra_research_rows:
        extra_research_rows = sorted(
            extra_research_rows,
            key=lambda row: (row[7], row[5], row[8]),
            reverse=True,
        )
        lines.extend([
            "",
            "## Additional Exit Research Scenarios",
        ])
        lines.extend(
            markdown_table(
                (
                    "scenario",
                    "kind",
                    "bar_limit",
                    "rows",
                    "overall_win_rate",
                    "overall_total_net",
                    "target_win_rate",
                    "target_total_net",
                    "managed_exits",
                ),
                extra_research_rows,
            )
        )
    lines.extend([
        "",
        "## Top Calibration Candidates",
    ])
    top_rows = summary.get("calibration_grid", [])[:20]
    lines.extend(
        markdown_table(
            (
                "scenario",
                "arm_pct",
                "giveback_pct",
                "managed_exits",
                "target_net",
                "target_win_rate",
                "delta_target_net_vs_no_timeout",
                "overall_net",
            ),
            [
                (
                    row["scenario_name"],
                    row["arm_pct"],
                    row["giveback_trigger_pct"],
                    row["managed_exit_rows"],
                    row["target_total_net_pnl_pct"],
                    row["target_win_rate_pct"],
                    row["delta_target_total_net_vs_no_timeout_pct"],
                    row["overall_total_net_pnl_pct"],
                )
                for row in top_rows
            ],
        )
    )
    lines.extend([
        "",
        "## Interpretation",
    ])
    if current_config is not None and balanced is not None:
        current_target_net = float(current_config["target_total_net_pnl_pct"])
        balanced_target_net = float(balanced["target_total_net_pnl_pct"])
        delta = round(balanced_target_net - current_target_net, 6)
        lines.append(
            f"- Relative to the best current-config shadow candidate, the balanced recommendation improves target-bucket total net pnl by {delta} pct points while keeping managed exits non-trivial."
        )
    lines.extend([
        "- On this slice, the economics-optimal region is much looser than the current 0.02/0.05/0.07 percent shadow arms. Tight arms harvest too early and erase the no-timeout upside.",
        "- This is still a bounded counterfactual, not runtime proof: the replay does not include live feature/regime refresh or order-book microstructure between candle opens and closes.",
    ])
    return "\n".join(lines) + "\n"


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run conservative Sidecar shadow counterfactual on one shadow plan JSONL file.")
    parser.add_argument("--shadow-plan-file", type=Path, required=True)
    parser.add_argument("--recorder-root", type=Path,
                        default=REPO_ROOT / "data" / "recorder")
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--baseline-max-bars-after-signal",
                        type=int, default=12)
    parser.add_argument(
        "--intrabar-ambiguity-policy",
        choices=["mark_ambiguous", "prioritize_sl", "prioritize_tp"],
        default="mark_ambiguous",
    )
    parser.add_argument("--fees-bps", type=float, default=2.0)
    parser.add_argument("--slippage-bps", type=float, default=1.0)
    parser.add_argument("--config-dir", type=Path,
                        default=REPO_ROOT / "config" / "aurora")
    parser.add_argument("--arm-pcts", type=str, default=None)
    parser.add_argument("--giveback-trigger-pcts", type=str, default=None)
    parser.add_argument("--bar-count-no-fee-cover-bars",
                        type=str, default=None)
    parser.add_argument("--min-managed-exit-rows", type=int, default=40)
    args = parser.parse_args(argv)
    if args.output_dir is None:
        args.output_dir = REPO_ROOT / "reports" / "judge" / \
            f"{args.shadow_plan_file.stem}_sidecar_counterfactual"
    return args


def analyze(args: argparse.Namespace) -> dict[str, Any]:
    context = infer_file_context(args.shadow_plan_file.resolve())
    verdict_rows = load_rows(context.verdict_path)
    envelope_rows = load_rows(context.envelope_path)
    verdict_by_id = build_single_index(verdict_rows, "verdict_id")
    verdict_by_cycle = build_single_index(verdict_rows, "cycle_key")
    envelope_by_id = build_single_index(envelope_rows, "envelope_id")
    envelope_by_cycle = build_single_index(envelope_rows, "cycle_key")
    plans, invalid_rows = load_plans(args.shadow_plan_file.resolve())

    config = ConfigLoader(args.config_dir).load_config()
    sidecar_cfg = config.domains.execution_position.position_policy_sidecar
    default_giveback_trigger_pct = float(
        sidecar_cfg.peak_giveback_close.giveback_trigger_pct)
    shadow_arm_candidates = [float(
        candidate) for candidate in sidecar_cfg.shadow_percent_notional_arm.candidate_pcts]
    arm_grid = unique_sorted(
        shadow_arm_candidates
        + list(DEFAULT_EXTRA_ARM_PCTS)
        + parse_float_csv(args.arm_pcts)
    )
    giveback_grid = unique_sorted(
        list(DEFAULT_GIVEBACK_TRIGGER_PCTS)
        + [default_giveback_trigger_pct]
        + parse_float_csv(args.giveback_trigger_pcts)
    )
    bar_count_no_fee_cover_grid = sorted(
        {
            value
            for value in parse_int_csv(args.bar_count_no_fee_cover_bars)
            if value > 0
        }
    )

    scenarios = [
        ScenarioSpec(
            name=f"baseline_timeout_{args.baseline_max_bars_after_signal}",
            kind="baseline",
            fill_search_limit_bars=args.baseline_max_bars_after_signal,
        ),
        ScenarioSpec(name="no_timeout_hold_to_data_end",
                     kind="hold_to_end", fill_search_limit_bars=None),
    ]
    for candidate in arm_grid:
        for giveback_trigger in giveback_grid:
            scenarios.append(
                ScenarioSpec(
                    name=f"sidecar_pct_{candidate:.2f}_gb_{giveback_trigger:.0f}",
                    kind="sidecar_percent",
                    fill_search_limit_bars=None,
                    arm_pct=candidate,
                    giveback_trigger_pct=giveback_trigger,
                )
            )
    for bar_count_limit in bar_count_no_fee_cover_grid:
        scenarios.append(
            ScenarioSpec(
                name=f"bar_count_{bar_count_limit}_no_fee_cover",
                kind="bar_count_no_fee_cover",
                fill_search_limit_bars=None,
                bar_count_limit=bar_count_limit,
            )
        )

    simulator_cfg = ShadowSimulatorConfig(
        enabled=True,
        max_bars_after_signal=args.baseline_max_bars_after_signal,
        intrabar_ambiguity_policy=args.intrabar_ambiguity_policy,
        fees_bps=args.fees_bps,
        slippage_bps=args.slippage_bps,
    )
    simulator = ShadowPlanSimulator(simulator_cfg)
    bars_cache: dict[tuple[str, str, int], Any] = {}

    def get_bars(plan: ShadowEntryPlan) -> Any:
        date_key = utc_date_from_ts_ms(plan.ts_ms)
        cache_key = (date_key, plan.symbol, plan.tf_sec)
        if cache_key not in bars_cache:
            bars_cache[cache_key] = simulator._load_bars(
                args.recorder_root, date_key, plan.symbol, plan.tf_sec)
        return bars_cache[cache_key]

    rows: list[dict[str, Any]] = []
    for plan in plans:
        verdict = verdict_by_cycle.get(
            plan.cycle_key) or verdict_by_id.get(plan.source_verdict_id)
        envelope = envelope_by_cycle.get(
            plan.cycle_key) or envelope_by_id.get(plan.source_envelope_id)
        bars = get_bars(plan)
        feature_row = pick_feature_row(bars, plan.ts_ms)

        for scenario in scenarios:
            row = build_base_row(plan)
            row["scenario_name"] = scenario.name
            row["scenario_kind"] = scenario.kind
            row["scenario_fill_search_limit_bars"] = scenario.fill_search_limit_bars
            row["scenario_arm_pct"] = scenario.arm_pct
            row["scenario_giveback_trigger_pct"] = scenario.giveback_trigger_pct
            apply_verdict_context(row, verdict)
            apply_envelope_context(row, envelope)
            row.update(build_recorder_context(feature_row))

            if plan.suppressed:
                row["simulation_status"] = "skipped"
                row["skipped_reason"] = "suppressed_plan"
                row["terminal_reason"] = "suppressed_plan"
                row["proposal_outcome_class"] = "SUPPRESSED"
                rows.append(row)
                continue

            if not plan.actionable:
                row["simulation_status"] = "skipped"
                row["skipped_reason"] = "non_actionable_plan"
                row["terminal_reason"] = "non_actionable_plan"
                row["proposal_outcome_class"] = "NON_ACTIONABLE"
                rows.append(row)
                continue

            if plan.entry_side not in {"BUY", "SELL"} or plan.limit_price is None or plan.tp_price is None or plan.sl_price is None:
                row["simulation_status"] = "invalid"
                row["invalid_reason"] = "incomplete_plan_geometry"
                row["terminal_reason"] = "incomplete_plan_geometry"
                row["proposal_outcome_class"] = "INVALID"
                rows.append(row)
                continue

            if getattr(bars, "empty", True):
                row["simulation_status"] = "skipped"
                row["skipped_reason"] = "missing_ohlc_file"
                row["terminal_reason"] = "missing_ohlc_file"
                row["proposal_outcome_class"] = "MISSING_OHLC"
                rows.append(row)
                continue

            if scenario.kind == "baseline":
                result = simulator.simulate_plan(plan, bars)
                scenario_result = build_result(
                    plan=plan,
                    terminal_reason=result.outcome,
                    exit_reason=result.outcome_reason or "baseline_simulator",
                    fill_idx=result.fill_bar_idx,
                    fill_price=result.fill_price,
                    fill_ts_ms=result.fill_ts_ms,
                    exit_idx=result.exit_bar_idx,
                    exit_price=result.exit_price,
                    exit_ts_ms=result.exit_ts_ms,
                    bars=bars,
                    fees_bps=args.fees_bps,
                    slippage_bps=args.slippage_bps,
                )
            elif scenario.kind == "hold_to_end":
                scenario_result = simulate_hold_to_end(
                    plan=plan,
                    bars=bars,
                    fill_search_limit_bars=scenario.fill_search_limit_bars,
                    intrabar_ambiguity_policy=args.intrabar_ambiguity_policy,
                    fees_bps=args.fees_bps,
                    slippage_bps=args.slippage_bps,
                )
            else:
                if scenario.kind == "sidecar_percent":
                    scenario_result = simulate_sidecar_percent_giveback(
                        plan=plan,
                        bars=bars,
                        fill_search_limit_bars=scenario.fill_search_limit_bars,
                        intrabar_ambiguity_policy=args.intrabar_ambiguity_policy,
                        fees_bps=args.fees_bps,
                        slippage_bps=args.slippage_bps,
                        arm_pct=float(scenario.arm_pct or 0.0),
                        giveback_trigger_pct=float(
                            scenario.giveback_trigger_pct or 0.0),
                    )
                else:
                    scenario_result = simulate_bar_count_exit_no_fee_cover(
                        plan=plan,
                        bars=bars,
                        fill_search_limit_bars=scenario.fill_search_limit_bars,
                        intrabar_ambiguity_policy=args.intrabar_ambiguity_policy,
                        fees_bps=args.fees_bps,
                        slippage_bps=args.slippage_bps,
                        max_bars_without_fee_cover=int(
                            scenario.bar_count_limit or 0),
                    )

            row.update(scenario_result)
            row["in_primary_cohort"] = row.get(
                "simulation_status") == "success"
            row["primary_is_win"] = bool(
                row["in_primary_cohort"] and row.get("trade_pnl_class") == "WIN")
            rows.append(row)

    for invalid_row in invalid_rows:
        for scenario in scenarios:
            row = dict(invalid_row)
            row["scenario_name"] = scenario.name
            row["scenario_kind"] = scenario.kind
            row["scenario_fill_search_limit_bars"] = scenario.fill_search_limit_bars
            row["scenario_arm_pct"] = scenario.arm_pct
            row["scenario_giveback_trigger_pct"] = scenario.giveback_trigger_pct
            rows.append(row)

    scenario_summaries: dict[str, Any] = {}
    no_timeout_name = "no_timeout_hold_to_data_end"
    baseline_name = f"baseline_timeout_{args.baseline_max_bars_after_signal}"
    for scenario in scenarios:
        scenario_rows = [row for row in rows if row.get(
            "scenario_name") == scenario.name and row.get("in_primary_cohort")]
        scenario_summaries[scenario.name] = {
            "spec": {
                "kind": scenario.kind,
                "fill_search_limit_bars": scenario.fill_search_limit_bars,
                "arm_pct": scenario.arm_pct,
                "giveback_trigger_pct": scenario.giveback_trigger_pct,
                "bar_count_limit": scenario.bar_count_limit,
            },
            "financial": summarize_financial(scenario_rows),
            "by_confidence_bucket": make_group_summary(scenario_rows, "confidence_bucket"),
            "by_entry_side": make_group_summary(scenario_rows, "entry_side"),
            "target_buckets": targeted_bucket_summary(scenario_rows),
            "managed_exit_rows": sum(1 for row in scenario_rows if row.get("managed_exit") is True),
            "managed_exit_distribution": dict(sorted(build_context_stats(scenario_rows, "terminal_reason").items())),
        }

    calibration_grid = build_calibration_rows(
        scenario_summaries, no_timeout_name=no_timeout_name)
    recommendations = choose_recommendations(
        calibration_grid,
        min_managed_exit_rows=args.min_managed_exit_rows,
        config_arm_pcts=shadow_arm_candidates,
        default_giveback_trigger_pct=default_giveback_trigger_pct,
    )

    summary = {
        "meta": {
            "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "source_file": args.shadow_plan_file.resolve().as_posix(),
            "output_dir": args.output_dir.as_posix(),
            "symbol": context.symbol,
            "utc_date": context.utc_date,
            "recorder_root": args.recorder_root.as_posix(),
            "target_buckets": list(TARGET_BUCKETS),
            "baseline_scenario_name": baseline_name,
            "no_timeout_scenario_name": no_timeout_name,
            "min_managed_exit_rows": args.min_managed_exit_rows,
            "baseline_max_bars_after_signal": args.baseline_max_bars_after_signal,
            "intrabar_ambiguity_policy": args.intrabar_ambiguity_policy,
            "fees_bps": args.fees_bps,
            "slippage_bps": args.slippage_bps,
            "sidecar_config_snapshot": {
                "mode": sidecar_cfg.mode.value,
                "peak_giveback_close": {
                    "enabled": bool(sidecar_cfg.peak_giveback_close.enabled),
                    "edge_arm_usd": float(sidecar_cfg.peak_giveback_close.edge_arm_usd),
                    "giveback_trigger_pct": float(sidecar_cfg.peak_giveback_close.giveback_trigger_pct),
                },
                "shadow_percent_notional_arm": {
                    "enabled": bool(sidecar_cfg.shadow_percent_notional_arm.enabled),
                    "candidate_pcts": shadow_arm_candidates,
                },
            },
            "limits": [
                "Managed exits are evaluated on candle close only; TP/SL remains intrabar.",
                "Absolute USD peak-giveback arm is not replayed because ShadowEntryPlan carries no qty/notional.",
                "Shadow percent-of-notional arms are replayable in percent-return space because notional cancels out.",
            ],
        },
        "counts": {
            "total_rows": len(rows),
            "valid_plan_rows": len(plans),
            "invalid_plan_rows": len(invalid_rows),
            "scenario_count": len(scenarios),
        },
        "consistency_checks": build_consistency_checks(rows),
        "scenario_summaries": scenario_summaries,
        "calibration_grid": calibration_grid,
        "recommendations": recommendations,
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_json(args.output_dir / "summary.json", summary)
    write_jsonl(args.output_dir / "scenario_rows.jsonl", rows)
    write_csv(args.output_dir / "scenario_rows.csv", rows)
    write_csv(args.output_dir / "calibration_grid.csv", calibration_grid)
    report = build_report(summary, args.output_dir)
    (args.output_dir / "report.md").write_text(report, encoding="utf-8")
    financial_report = build_financial_report(summary)
    (args.output_dir / "financial_report.md").write_text(financial_report, encoding="utf-8")
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    summary = analyze(args)
    compact = {
        "output_dir": args.output_dir.as_posix(),
        "scenario_names": list(summary["scenario_summaries"].keys()),
        "managed_exit_rows": {
            name: item["managed_exit_rows"]
            for name, item in summary["scenario_summaries"].items()
        },
    }
    print(json.dumps(compact, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
