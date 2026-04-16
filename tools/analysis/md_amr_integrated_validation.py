#!/usr/bin/env python3
from __future__ import annotations
from tools.calibration import calibrate_md_amr_weights as calibrator

import argparse
from collections import Counter
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
import math
from pathlib import Path
import sys
from typing import Any, Sequence

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


A1_MAX_HOLD_BARS = 16
A1_TARGET_APPROACH_PCT = 0.0
TF_SEC = 900
TIMEOUT_REASONS = {"ZOMBIE_POSITION_TIMEOUT"}
FORCE_CLOSE_REASONS = {"SEGMENT_END_FORCE_CLOSE"}
STOP_REASONS = {"STOP_PRICE_HIT", "TPSL_AMBIGUOUS_STOP_FIRST"}
TARGET_REASONS = {"TARGET_PRICE_HIT"}
WEAK_CONTEXT_STATES = {"WEAKENING", "INVALID", "UNKNOWN"}
VALID_CONTEXT_STATE = "VALID"

REGIME_ALIAS_MAP = {
    "LOW_FLAT": "FLAT_LOW",
    "HIGH_FLAT": "FLAT_HIGH",
    "HIGHT_FLAT": "FLAT_HIGH",
    "NORMAL_FLAT": "FLAT_NORMAL",
    "HIGH_VOLATILYTY": "HIGH_VOLATILITY",
    "LOW_VOLATILYTY": "LOW_VOLATILITY",
    "HIGHT_VOLATILITY": "HIGH_VOLATILITY",
}

REGIME_COMPATIBILITY_MAP = {
    "FLAT_LOW": ("FLAT_LOW", "LOW_VOLATILITY"),
    "LOW_VOLATILITY": ("LOW_VOLATILITY", "FLAT_LOW"),
    "FLAT_NORMAL": ("FLAT_NORMAL", "MEAN_REVERSION"),
    "MEAN_REVERSION": ("MEAN_REVERSION", "FLAT_NORMAL"),
    "FLAT_HIGH": ("FLAT_HIGH", "HIGH_VOLATILITY"),
    "HIGH_VOLATILITY": ("HIGH_VOLATILITY", "FLAT_HIGH"),
}


@dataclass(frozen=True)
class ValidationArm:
    name: str
    attach_anchors: bool
    attach_context: bool
    collect_overlay_metrics: bool
    description: str


BASELINE_ARM = ValidationArm(
    name="baseline_a1",
    attach_anchors=False,
    attach_context=False,
    collect_overlay_metrics=False,
    description="A.1 semantics on current md_amr core with overlay position inputs withheld.",
)

INTEGRATED_ARM = ValidationArm(
    name="integrated_c1234",
    attach_anchors=True,
    attach_context=True,
    collect_overlay_metrics=True,
    description="Current integrated C.1/C.2/C.3/C.4 line with anchors and regime context supplied.",
)


def _parse_date(raw: str) -> date:
    return date.fromisoformat(raw)


def _to_decimal(value: Any) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(
            f"Unable to coerce numeric value to Decimal: {value}") from exc
    if not result.is_finite():
        raise ValueError(f"Non-finite Decimal input: {value}")
    return result


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _normalize_regime_label(value: Any) -> str | None:
    label = str(value or "").strip().upper()
    if not label or label == "NAN":
        return None
    return REGIME_ALIAS_MAP.get(label, label)


def _expand_allowed_regimes(allowed_regimes: list[str]) -> list[str]:
    expanded: list[str] = []
    seen: set[str] = set()
    for raw_regime in allowed_regimes:
        normalized = _normalize_regime_label(raw_regime)
        if normalized is None:
            continue
        compatible = REGIME_COMPATIBILITY_MAP.get(normalized, (normalized,))
        for regime in compatible:
            if regime not in seen:
                seen.add(regime)
                expanded.append(regime)
    return expanded


def _extract_result_trace(result: dict[str, Any]) -> dict[str, Any]:
    if result.get("status") == "SIGNAL":
        signal = result.get("signal")
        if signal is not None:
            return dict(getattr(signal, "trace", {}) or {})
    return dict(result.get("trace", {}) or {})


def _trade_signature(record: dict[str, Any]) -> str:
    return "|".join(
        [
            str(record["symbol"]),
            str(record["side"]),
            str(int(record["entry_ts_ms"])),
            str(int(record["exit_ts_ms"])),
            str(record.get("primary_exit_reason") or ""),
            f"{float(record.get('net_return_ratio', 0.0)):.12f}",
            str(int(record.get("leg_count", 0))),
        ]
    )


def _initial_trade_state(
    *,
    arm: ValidationArm,
    symbol: str,
    trade_id: str,
    side: str,
    entry_ts_ms: int,
    entry_price: Decimal,
    entry_trace: dict[str, Any],
) -> dict[str, Any]:
    state = {
        "arm": arm.name,
        "symbol": symbol,
        "trade_id": trade_id,
        "side": str(side).upper(),
        "entry_ts_ms": int(entry_ts_ms),
        "entry_price": float(entry_price),
        "exit_ts_ms": int(entry_ts_ms),
        "exit_price": float(entry_price),
        "leg_count": 0,
        "gross_return_ratio": 0.0,
        "net_return_ratio": 0.0,
        "exit_reasons": [],
        "primary_exit_reason": None,
        "entry_setup_quality": None,
        "entry_sq_penetration": None,
        "entry_sq_channel_quality": None,
        "entry_sq_coherence": None,
        "entry_sq_volatility": None,
        "observed_overlay_bars": 0,
        "max_elapsed_hold_frac": None,
        "max_progress_pct": None,
        "min_progress_pct": None,
        "exit_progress_pct": None,
        "exit_progress_state": None,
        "min_hold_quality": None,
        "exit_hold_quality": None,
        "min_context_validity": None,
        "exit_context_validity": None,
        "exit_context_validity_state": None,
        "bars_with_low_hold_quality": 0,
        "bars_with_weak_context": 0,
        "bars_with_invalid_context": 0,
        "bars_with_unknown_context": 0,
        "bars_with_reversing_progress": 0,
    }
    if arm.collect_overlay_metrics:
        state["entry_setup_quality"] = _safe_float(
            entry_trace.get("setup_quality"))
        state["entry_sq_penetration"] = _safe_float(
            entry_trace.get("sq_penetration"))
        state["entry_sq_channel_quality"] = _safe_float(
            entry_trace.get("sq_channel_quality"))
        state["entry_sq_coherence"] = _safe_float(
            entry_trace.get("sq_coherence"))
        state["entry_sq_volatility"] = _safe_float(
            entry_trace.get("sq_volatility"))
    return state


def _update_extrema(state: dict[str, Any], key_min: str, key_max: str | None, key_last: str, value: float | None) -> None:
    if value is None:
        return
    state[key_last] = value
    current_min = _safe_float(state.get(key_min))
    if current_min is None or value < current_min:
        state[key_min] = value
    if key_max is not None:
        current_max = _safe_float(state.get(key_max))
        if current_max is None or value > current_max:
            state[key_max] = value


def _update_trade_overlay(state: dict[str, Any], trace: dict[str, Any], *, arm: ValidationArm) -> None:
    if not arm.collect_overlay_metrics:
        return
    if not trace:
        return
    observed = False
    progress_pct = _safe_float(trace.get("progress_pct"))
    hold_quality = _safe_float(trace.get("hold_quality"))
    context_validity = _safe_float(trace.get("context_validity"))
    elapsed_hold_frac = _safe_float(trace.get("elapsed_hold_frac"))
    if progress_pct is not None or hold_quality is not None or context_validity is not None:
        observed = True
    if observed:
        state["observed_overlay_bars"] = int(
            state["observed_overlay_bars"]) + 1
    _update_extrema(state, "min_progress_pct", "max_progress_pct",
                    "exit_progress_pct", progress_pct)
    _update_extrema(state, "min_hold_quality", None,
                    "exit_hold_quality", hold_quality)
    _update_extrema(state, "min_context_validity", None,
                    "exit_context_validity", context_validity)
    if elapsed_hold_frac is not None:
        current_max_elapsed = _safe_float(state.get("max_elapsed_hold_frac"))
        if current_max_elapsed is None or elapsed_hold_frac > current_max_elapsed:
            state["max_elapsed_hold_frac"] = elapsed_hold_frac
    progress_state = trace.get("progress_state")
    if progress_state is not None:
        state["exit_progress_state"] = str(progress_state)
        if str(progress_state) == "REVERSING_AGAINST":
            state["bars_with_reversing_progress"] = int(
                state["bars_with_reversing_progress"]) + 1
    context_state = trace.get("context_validity_state")
    if context_state is not None:
        context_state = str(context_state)
        state["exit_context_validity_state"] = context_state
        if context_state in WEAK_CONTEXT_STATES:
            state["bars_with_weak_context"] = int(
                state["bars_with_weak_context"]) + 1
        if context_state == "INVALID":
            state["bars_with_invalid_context"] = int(
                state["bars_with_invalid_context"]) + 1
        if context_state == "UNKNOWN":
            state["bars_with_unknown_context"] = int(
                state["bars_with_unknown_context"]) + 1
    if hold_quality is not None and hold_quality <= 0.35:
        state["bars_with_low_hold_quality"] = int(
            state["bars_with_low_hold_quality"]) + 1


def _realize_leg(
    *,
    side: str,
    entry_price: Decimal,
    exit_price: Decimal,
    fraction_closed: float,
    per_side_cost_ratio: float,
) -> tuple[float, float]:
    if entry_price <= 0:
        gross_return_ratio = 0.0
    elif str(side).upper() == "BUY":
        gross_return_ratio = float((exit_price - entry_price) / entry_price)
    else:
        gross_return_ratio = float((entry_price - exit_price) / entry_price)
    gross_return_ratio *= float(fraction_closed)
    net_return_ratio = float(fraction_closed) * (
        (gross_return_ratio / max(float(fraction_closed), 1.0e-12))
        - 2.0 * float(per_side_cost_ratio)
    )
    return gross_return_ratio, net_return_ratio


def _finalize_trade(state: dict[str, Any], *, tf_sec: int) -> dict[str, Any]:
    exit_reasons = list(state.get("exit_reasons", []))
    holding_bars = max(
        1,
        int(
            round(
                (int(state["exit_ts_ms"]) - int(state["entry_ts_ms"]))
                / (int(tf_sec) * 1000.0)
            )
        ),
    )
    result = dict(state)
    result["holding_bars"] = holding_bars
    result["exit_reasons"] = "|".join(str(item) for item in exit_reasons)
    result["is_win"] = bool(float(result["net_return_ratio"]) > 0.0)
    result["has_scaleout"] = bool("FEE_AWARE_SCALEOUT" in exit_reasons)
    result["has_timeout"] = bool(
        any(reason in TIMEOUT_REASONS for reason in exit_reasons))
    result["has_segment_force_close"] = bool(
        any(reason in FORCE_CLOSE_REASONS for reason in exit_reasons))
    result["has_stop_hit"] = bool(
        any(reason in STOP_REASONS for reason in exit_reasons))
    result["has_target_hit"] = bool(
        any(reason in TARGET_REASONS for reason in exit_reasons))
    result["has_killswitch"] = bool("EDGE_GONE_KILLSWITCH" in exit_reasons)
    result["trade_signature"] = _trade_signature(result)
    return result


def _resolve_row_context(row: Any, *, effective_allowed_regimes: list[str]) -> dict[str, Any]:
    regime = _normalize_regime_label(getattr(row, "regime", None))
    regime_confidence = _safe_float(getattr(row, "regime_conf", None))
    context_regime_allowed = None
    if regime is not None:
        context_regime_allowed = bool(regime in set(effective_allowed_regimes))
    return {
        "context_regime": regime,
        "context_regime_confidence": regime_confidence,
        "context_regime_allowed": context_regime_allowed,
    }


def _build_position_ctx(
    *,
    position: dict[str, Any],
    arm: ValidationArm,
    row: Any,
    effective_allowed_regimes: list[str],
) -> dict[str, Any]:
    side = str(position.get("side") or "")
    remaining_fraction = float(position.get("remaining_fraction", 0.0) or 0.0)
    qty_signed = 0.0
    if bool(position.get("is_open")):
        qty_signed = remaining_fraction if side == "BUY" else -remaining_fraction
    ctx = {
        "qty_signed": float(qty_signed),
        "bars_held": int(position.get("bars_held", 0) or 0),
    }
    if arm.attach_anchors and bool(position.get("is_open")):
        entry_anchor = position.get("entry_anchor") or {}
        if entry_anchor:
            ctx.update(entry_anchor)
    if arm.attach_context and bool(position.get("is_open")):
        ctx.update(_resolve_row_context(
            row, effective_allowed_regimes=effective_allowed_regimes))
    return ctx


def _simulate_symbol_arm(
    df_symbol: pd.DataFrame,
    *,
    symbol: str,
    arm: ValidationArm,
    base_params: dict[str, Any],
    weights: dict[str, float],
    asset_cfg: dict[str, Any],
    tf_sec: int,
    warmup_bars: int,
) -> list[dict[str, Any]]:
    trade_records: list[dict[str, Any]] = []
    trade_seq = 0
    per_side_cost_ratio = (
        float(base_params["fee_bps"]) +
        float(base_params["slippage_buffer_bps"])
    ) / 10000.0
    allowed_regimes = [str(item)
                       for item in asset_cfg.get("allowed_regimes", [])]
    effective_allowed_regimes = _expand_allowed_regimes(allowed_regimes)

    grouped = (
        df_symbol.groupby("segment_id", sort=False)
        if "segment_id" in df_symbol.columns
        else [(0, df_symbol.copy())]
    )
    for _segment_id, segment in grouped:
        strategy = calibrator._make_strategy(base_params, weights)
        bars_seen = 0
        position = {
            "is_open": False,
            "side": None,
            "entry_price": None,
            "entry_ts_ms": None,
            "remaining_fraction": 0.0,
            "bars_held": 0,
            "stop_price": None,
            "target_price": None,
            "trade_state": None,
            "entry_anchor": None,
        }

        for row in segment.itertuples(index=False):
            if position["is_open"]:
                exit_hit = calibrator._resolve_intrabar_tpsl(
                    side=str(position["side"]),
                    bar_high=float(getattr(row, "high")),
                    bar_low=float(getattr(row, "low")),
                    stop_price=position["stop_price"],
                    target_price=position["target_price"],
                )
                if exit_hit is not None:
                    trade_state = dict(position["trade_state"])
                    gross_return_ratio, net_return_ratio = _realize_leg(
                        side=str(position["side"]),
                        entry_price=position["entry_price"],
                        exit_price=exit_hit["exit_price"],
                        fraction_closed=float(position["remaining_fraction"]),
                        per_side_cost_ratio=per_side_cost_ratio,
                    )
                    trade_state["gross_return_ratio"] += float(
                        gross_return_ratio)
                    trade_state["net_return_ratio"] += float(net_return_ratio)
                    trade_state["leg_count"] += 1
                    trade_state["exit_ts_ms"] = int(getattr(row, "timestamp"))
                    trade_state["exit_price"] = float(exit_hit["exit_price"])
                    trade_state["exit_reasons"].append(str(exit_hit["reason"]))
                    trade_state["primary_exit_reason"] = str(
                        exit_hit["reason"])
                    trade_records.append(_finalize_trade(
                        trade_state, tf_sec=tf_sec))
                    position = {
                        "is_open": False,
                        "side": None,
                        "entry_price": None,
                        "entry_ts_ms": None,
                        "remaining_fraction": 0.0,
                        "bars_held": 0,
                        "stop_price": None,
                        "target_price": None,
                        "trade_state": None,
                        "entry_anchor": None,
                    }
                    continue

            bars_seen += 1
            if position["is_open"]:
                position["bars_held"] = int(position["bars_held"]) + 1

            result = strategy.on_bar(
                bar={
                    "open": getattr(row, "open"),
                    "high": getattr(row, "high"),
                    "low": getattr(row, "low"),
                    "close": getattr(row, "close"),
                },
                position_ctx=_build_position_ctx(
                    position=position,
                    arm=arm,
                    row=row,
                    effective_allowed_regimes=effective_allowed_regimes,
                ),
                llm_blocked=False,
            )

            if bars_seen <= int(warmup_bars):
                continue

            trace = _extract_result_trace(result)
            if position["is_open"] and trace:
                _update_trade_overlay(position["trade_state"], trace, arm=arm)

            if result.get("status") != "SIGNAL":
                continue
            signal = result.get("signal")
            if signal is None:
                continue

            signal_side = str(getattr(signal, "side", "")).upper()
            intent_kind = str(getattr(signal, "intent_kind", ""))
            signal_price = _to_decimal(getattr(signal, "price_ref"))

            if intent_kind == "ENTRY" and not position["is_open"]:
                trade_seq += 1
                trade_id = f"{symbol}:{trade_seq}"
                entry_trace = dict(getattr(signal, "trace", {}) or {})
                trade_state = _initial_trade_state(
                    arm=arm,
                    symbol=symbol,
                    trade_id=trade_id,
                    side=signal_side,
                    entry_ts_ms=int(getattr(row, "timestamp")),
                    entry_price=signal_price,
                    entry_trace=entry_trace,
                )
                row_context = _resolve_row_context(
                    row, effective_allowed_regimes=effective_allowed_regimes
                )
                bracket = calibrator._compute_tpsl_from_asset_cfg(
                    entry_price=signal_price,
                    side=signal_side,
                    regime=row_context["context_regime"] or "DEFAULT",
                    asset_cfg=asset_cfg,
                )
                entry_anchor = None
                if arm.attach_anchors:
                    channel_state = dict(
                        getattr(signal, "channel_state", {}) or {})
                    avg_close = _safe_float(channel_state.get("avg_close_12"))
                    if avg_close is not None:
                        entry_anchor = {
                            "entry_price": float(signal_price),
                            "entry_target_price": float(avg_close),
                        }
                position = {
                    "is_open": True,
                    "side": signal_side,
                    "entry_price": signal_price,
                    "entry_ts_ms": int(getattr(row, "timestamp")),
                    "remaining_fraction": 1.0,
                    "bars_held": 0,
                    "stop_price": bracket["stop_price"] if bracket else None,
                    "target_price": bracket["target_price"] if bracket else None,
                    "trade_state": trade_state,
                    "entry_anchor": entry_anchor,
                }
                continue

            if not position["is_open"] or intent_kind not in {"FULL_CLOSE", "PARTIAL_CLOSE"}:
                continue

            if intent_kind == "PARTIAL_CLOSE":
                fraction_closed = min(
                    float(position["remaining_fraction"]),
                    max(0.0, float(getattr(signal, "scaleout_fraction", 0.0) or 0.0)),
                )
                if fraction_closed <= 1.0e-12:
                    continue
            else:
                fraction_closed = float(position["remaining_fraction"])

            gross_return_ratio, net_return_ratio = _realize_leg(
                side=str(position["side"]),
                entry_price=position["entry_price"],
                exit_price=signal_price,
                fraction_closed=fraction_closed,
                per_side_cost_ratio=per_side_cost_ratio,
            )
            trade_state = dict(position["trade_state"])
            _update_trade_overlay(trade_state, dict(
                getattr(signal, "trace", {}) or {}), arm=arm)
            trade_state["gross_return_ratio"] += float(gross_return_ratio)
            trade_state["net_return_ratio"] += float(net_return_ratio)
            trade_state["leg_count"] += 1
            trade_state["exit_ts_ms"] = int(getattr(row, "timestamp"))
            trade_state["exit_price"] = float(signal_price)
            trade_state["exit_reasons"].append(
                str(getattr(signal, "reason_code", intent_kind)))
            trade_state["primary_exit_reason"] = str(
                getattr(signal, "reason_code", intent_kind))

            remaining_fraction = float(
                position["remaining_fraction"]) - float(fraction_closed)
            if remaining_fraction <= 1.0e-9 or intent_kind == "FULL_CLOSE":
                trade_records.append(_finalize_trade(
                    trade_state, tf_sec=tf_sec))
                position = {
                    "is_open": False,
                    "side": None,
                    "entry_price": None,
                    "entry_ts_ms": None,
                    "remaining_fraction": 0.0,
                    "bars_held": 0,
                    "stop_price": None,
                    "target_price": None,
                    "trade_state": None,
                    "entry_anchor": None,
                }
            else:
                position["remaining_fraction"] = remaining_fraction
                position["trade_state"] = trade_state

        if position["is_open"]:
            last_row = segment.iloc[-1]
            trade_state = dict(position["trade_state"])
            final_price = _to_decimal(last_row["close"])
            gross_return_ratio, net_return_ratio = _realize_leg(
                side=str(position["side"]),
                entry_price=position["entry_price"],
                exit_price=final_price,
                fraction_closed=float(position["remaining_fraction"]),
                per_side_cost_ratio=per_side_cost_ratio,
            )
            trade_state["gross_return_ratio"] += float(gross_return_ratio)
            trade_state["net_return_ratio"] += float(net_return_ratio)
            trade_state["leg_count"] += 1
            trade_state["exit_ts_ms"] = int(last_row["timestamp"])
            trade_state["exit_price"] = float(final_price)
            trade_state["exit_reasons"].append("SEGMENT_END_FORCE_CLOSE")
            trade_state["primary_exit_reason"] = "SEGMENT_END_FORCE_CLOSE"
            trade_records.append(_finalize_trade(trade_state, tf_sec=tf_sec))

    return trade_records


def _series_mean(df: pd.DataFrame, column: str) -> float | None:
    if column not in df.columns or df.empty:
        return None
    series = pd.to_numeric(df[column], errors="coerce").dropna()
    if series.empty:
        return None
    return float(series.mean())


def _series_quantile(df: pd.DataFrame, column: str, q: float) -> float | None:
    if column not in df.columns or df.empty:
        return None
    series = pd.to_numeric(df[column], errors="coerce").dropna()
    if series.empty:
        return None
    return float(series.quantile(q))


def _count_mask(df: pd.DataFrame, mask: pd.Series) -> int:
    if df.empty:
        return 0
    return int(mask.fillna(False).sum())


def _aggregate_arm_metrics(
    *,
    trades: pd.DataFrame,
    symbol: str,
    arm: ValidationArm,
    row_count: int,
    unique_days: int,
    start_ts_ms: int,
    end_ts_ms: int,
    max_hold_bars: int,
) -> dict[str, Any]:
    total_trades = int(len(trades))
    net_return_ratio = float(
        trades["net_return_ratio"].sum()) if total_trades else 0.0
    gross_return_ratio = float(
        trades["gross_return_ratio"].sum()) if total_trades else 0.0
    avg_trade_return_ratio = net_return_ratio / \
        total_trades if total_trades else 0.0
    avg_holding_bars = float(
        trades["holding_bars"].mean()) if total_trades else 0.0
    median_holding_bars = float(
        trades["holding_bars"].median()) if total_trades else 0.0
    win_rate = float((trades["net_return_ratio"] >
                     0.0).mean()) if total_trades else 0.0
    profitable_slow_reversion = trades[
        (pd.to_numeric(trades["net_return_ratio"], errors="coerce") > 0.0)
        & (pd.to_numeric(trades["holding_bars"], errors="coerce") >= math.ceil(max_hold_bars * 0.75))
    ].copy()
    return {
        "arm": arm.name,
        "symbol": symbol,
        "row_count": int(row_count),
        "unique_days": int(unique_days),
        "start_ts_ms": int(start_ts_ms),
        "end_ts_ms": int(end_ts_ms),
        "total_trades": total_trades,
        "win_rate": float(win_rate),
        "gross_return_ratio": float(gross_return_ratio),
        "net_return_ratio": float(net_return_ratio),
        "net_return_per_1000_bars": float(net_return_ratio * 1000.0 / row_count) if row_count else 0.0,
        "avg_trade_return_ratio": float(avg_trade_return_ratio),
        "avg_holding_bars": float(avg_holding_bars),
        "median_holding_bars": float(median_holding_bars),
        "scaleout_trade_count": int(trades["has_scaleout"].sum()) if total_trades else 0,
        "timeout_trade_count": int(trades["has_timeout"].sum()) if total_trades else 0,
        "segment_force_close_count": int(trades["has_segment_force_close"].sum()) if total_trades else 0,
        "stop_hit_trade_count": int(trades["has_stop_hit"].sum()) if total_trades else 0,
        "target_hit_trade_count": int(trades["has_target_hit"].sum()) if total_trades else 0,
        "killswitch_trade_count": int(trades["has_killswitch"].sum()) if total_trades else 0,
        "profitable_slow_reversion_count": int(len(profitable_slow_reversion)),
        "profitable_slow_reversion_net_return_ratio": float(profitable_slow_reversion["net_return_ratio"].sum()) if not profitable_slow_reversion.empty else 0.0,
        "entry_setup_quality_mean": _series_mean(trades, "entry_setup_quality") if arm.collect_overlay_metrics else None,
        "entry_setup_quality_p25": _series_quantile(trades, "entry_setup_quality", 0.25) if arm.collect_overlay_metrics else None,
        "entry_setup_quality_p75": _series_quantile(trades, "entry_setup_quality", 0.75) if arm.collect_overlay_metrics else None,
        "exit_hold_quality_mean": _series_mean(trades, "exit_hold_quality") if arm.collect_overlay_metrics else None,
        "exit_hold_quality_p25": _series_quantile(trades, "exit_hold_quality", 0.25) if arm.collect_overlay_metrics else None,
        "exit_context_validity_mean": _series_mean(trades, "exit_context_validity") if arm.collect_overlay_metrics else None,
        "exit_context_validity_p25": _series_quantile(trades, "exit_context_validity", 0.25) if arm.collect_overlay_metrics else None,
        "weak_context_exit_count": _count_mask(trades, trades["exit_context_validity_state"].isin(WEAK_CONTEXT_STATES)) if arm.collect_overlay_metrics and total_trades else None,
        "valid_context_exit_count": _count_mask(trades, trades["exit_context_validity_state"] == VALID_CONTEXT_STATE) if arm.collect_overlay_metrics and total_trades else None,
        "overlay_observed_trade_count": int(pd.to_numeric(trades["observed_overlay_bars"], errors="coerce").fillna(0).gt(0).sum()) if arm.collect_overlay_metrics and total_trades else None,
        "profitable_slow_reversion_exit_hold_quality_mean": _series_mean(profitable_slow_reversion, "exit_hold_quality") if arm.collect_overlay_metrics else None,
        "profitable_slow_reversion_exit_context_validity_mean": _series_mean(profitable_slow_reversion, "exit_context_validity") if arm.collect_overlay_metrics else None,
    }


def _cohort_metric_row(
    *,
    arm: ValidationArm,
    symbol: str,
    cohort_type: str,
    cohort: str,
    trades: pd.DataFrame,
) -> dict[str, Any]:
    total_trades = int(len(trades))
    return {
        "arm": arm.name,
        "symbol": symbol,
        "cohort_type": cohort_type,
        "cohort": cohort,
        "trade_count": total_trades,
        "win_rate": float((trades["net_return_ratio"] > 0.0).mean()) if total_trades else 0.0,
        "net_return_ratio": float(trades["net_return_ratio"].sum()) if total_trades else 0.0,
        "avg_trade_return_ratio": float(trades["net_return_ratio"].mean()) if total_trades else 0.0,
        "avg_holding_bars": float(trades["holding_bars"].mean()) if total_trades else 0.0,
        "entry_setup_quality_mean": _series_mean(trades, "entry_setup_quality") if arm.collect_overlay_metrics else None,
        "exit_hold_quality_mean": _series_mean(trades, "exit_hold_quality") if arm.collect_overlay_metrics else None,
        "exit_context_validity_mean": _series_mean(trades, "exit_context_validity") if arm.collect_overlay_metrics else None,
    }


def _build_cohort_rows(
    *,
    trades: pd.DataFrame,
    arm: ValidationArm,
    symbol: str,
    max_hold_bars: int,
) -> list[dict[str, Any]]:
    rows = [_cohort_metric_row(
        arm=arm, symbol=symbol, cohort_type="all", cohort="ALL", trades=trades)]
    reason_masks = {
        "TIMEOUT": trades["has_timeout"],
        "SEGMENT_FORCE_CLOSE": trades["has_segment_force_close"],
        "STOP_HIT": trades["has_stop_hit"],
        "TARGET_HIT": trades["has_target_hit"],
        "KILLSWITCH": trades["has_killswitch"],
        "SCALEOUT": trades["has_scaleout"],
    }
    for cohort, mask in reason_masks.items():
        cohort_df = trades[mask.fillna(False)].copy()
        if not cohort_df.empty:
            rows.append(
                _cohort_metric_row(
                    arm=arm,
                    symbol=symbol,
                    cohort_type="exit_reason",
                    cohort=cohort,
                    trades=cohort_df,
                )
            )

    profitable_slow_reversion = trades[
        (pd.to_numeric(trades["net_return_ratio"], errors="coerce") > 0.0)
        & (pd.to_numeric(trades["holding_bars"], errors="coerce") >= math.ceil(max_hold_bars * 0.75))
    ].copy()
    if not profitable_slow_reversion.empty:
        rows.append(
            _cohort_metric_row(
                arm=arm,
                symbol=symbol,
                cohort_type="behavior",
                cohort="PROFITABLE_SLOW_REVERSION",
                trades=profitable_slow_reversion,
            )
        )

    if arm.collect_overlay_metrics and not trades.empty:
        valid_context = trades[trades["exit_context_validity_state"]
                               == VALID_CONTEXT_STATE].copy()
        if not valid_context.empty:
            rows.append(
                _cohort_metric_row(
                    arm=arm,
                    symbol=symbol,
                    cohort_type="overlay",
                    cohort="VALID_CONTEXT_EXIT",
                    trades=valid_context,
                )
            )
        weak_context = trades[trades["exit_context_validity_state"].isin(
            WEAK_CONTEXT_STATES)].copy()
        if not weak_context.empty:
            rows.append(
                _cohort_metric_row(
                    arm=arm,
                    symbol=symbol,
                    cohort_type="overlay",
                    cohort="WEAK_CONTEXT_EXIT",
                    trades=weak_context,
                )
            )
    return rows


def _match_trade_signatures(base_trades: pd.DataFrame, integrated_trades: pd.DataFrame) -> tuple[int, float]:
    base_counter = Counter(str(item)
                           for item in base_trades["trade_signature"].tolist())
    integrated_counter = Counter(
        str(item) for item in integrated_trades["trade_signature"].tolist())
    match_count = sum(
        min(base_counter[key], integrated_counter[key])
        for key in set(base_counter).union(integrated_counter)
    )
    denom = max(int(len(base_trades)), int(len(integrated_trades)), 1)
    return int(match_count), float(match_count / denom)


def _summary_row(
    *,
    scope: str,
    baseline_row: dict[str, Any],
    integrated_row: dict[str, Any],
    match_count: int,
    match_rate: float,
) -> dict[str, Any]:
    baseline_trades = int(baseline_row["total_trades"])
    integrated_trades = int(integrated_row["total_trades"])
    net_return_delta = float(
        integrated_row["net_return_ratio"] - baseline_row["net_return_ratio"])
    net_return_per_1000_bars_delta = float(
        integrated_row["net_return_per_1000_bars"] -
        baseline_row["net_return_per_1000_bars"]
    )
    avg_holding_delta = float(
        integrated_row["avg_holding_bars"] - baseline_row["avg_holding_bars"])
    timeout_delta = int(
        integrated_row["timeout_trade_count"] - baseline_row["timeout_trade_count"])
    economic_parity = bool(
        baseline_trades == integrated_trades
        and abs(net_return_delta) <= 1.0e-12
        and abs(net_return_per_1000_bars_delta) <= 1.0e-12
        and abs(avg_holding_delta) <= 1.0e-12
        and abs(match_rate - 1.0) <= 1.0e-12
    )
    return {
        "scope": scope,
        "baseline_total_trades": baseline_trades,
        "integrated_total_trades": integrated_trades,
        "trade_count_delta": int(integrated_trades - baseline_trades),
        "baseline_net_return_ratio": float(baseline_row["net_return_ratio"]),
        "integrated_net_return_ratio": float(integrated_row["net_return_ratio"]),
        "net_return_ratio_delta": float(net_return_delta),
        "baseline_net_return_per_1000_bars": float(baseline_row["net_return_per_1000_bars"]),
        "integrated_net_return_per_1000_bars": float(integrated_row["net_return_per_1000_bars"]),
        "net_return_per_1000_bars_delta": float(net_return_per_1000_bars_delta),
        "baseline_win_rate": float(baseline_row["win_rate"]),
        "integrated_win_rate": float(integrated_row["win_rate"]),
        "win_rate_delta": float(integrated_row["win_rate"] - baseline_row["win_rate"]),
        "baseline_avg_holding_bars": float(baseline_row["avg_holding_bars"]),
        "integrated_avg_holding_bars": float(integrated_row["avg_holding_bars"]),
        "avg_holding_bars_delta": float(avg_holding_delta),
        "baseline_timeout_trade_count": int(baseline_row["timeout_trade_count"]),
        "integrated_timeout_trade_count": int(integrated_row["timeout_trade_count"]),
        "timeout_trade_count_delta": int(timeout_delta),
        "exact_trade_match_count": int(match_count),
        "exact_trade_match_rate": float(match_rate),
        "explainability_gain": bool(
            integrated_row.get("overlay_observed_trade_count")
            and int(integrated_row["overlay_observed_trade_count"] or 0) > 0
        ),
        "economic_parity": economic_parity,
    }


def _fmt_number(value: Any, digits: int = 4) -> str:
    if value is None:
        return "n/a"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if not math.isfinite(number):
        return "n/a"
    return f"{number:.{digits}f}"


def _render_report(
    *,
    symbols: list[str],
    yaml_params: dict[str, Any],
    by_symbol_df: pd.DataFrame,
    summary_df: pd.DataFrame,
    cohort_df: pd.DataFrame,
    data_ranges: dict[str, tuple[str, str]],
) -> str:
    combined = summary_df[summary_df["scope"] == "COMBINED"].iloc[0].to_dict()
    lines: list[str] = [
        "# MD_AMR Integrated Validation Report",
        "",
        "## Scope",
        "- Objective: compare accepted safe baseline A.1 against current integrated C.1/C.2/C.3/C.4 line.",
        "- Symbols: " + ", ".join(symbols),
        "- Validation surface: recorder-based md_amr strategy-core replay plus asset TP/SL projection.",
        "- Output artifacts:",
        "  - reports/md_amr_integrated_validation_by_symbol.csv",
        "  - reports/md_amr_integrated_validation_cohorts.csv",
        "  - reports/md_amr_integrated_validation_summary.csv",
        "",
        "## FACT",
        f"- Current YAML still holds the accepted A.1 baseline values: max_hold_bars={yaml_params['max_hold_bars']}, target_approach_pct={yaml_params['target_approach_pct']}.",
        "- Package C.3 and C.4 remain advisory-only at package boundary; they do not own exit or execution truth.",
        "- Runtime forensic evidence already proves md_amr activity on XRPUSDT and BNBUSDT in the 21h report.",
    ]
    for symbol in symbols:
        start_date, end_date = data_ranges[symbol]
        symbol_summary = summary_df[summary_df["scope"]
                                    == symbol].iloc[0].to_dict()
        lines.append(
            f"- {symbol}: recorder range {start_date}..{end_date}, exact trade match rate={_fmt_number(symbol_summary['exact_trade_match_rate'])}, net-return delta={_fmt_number(symbol_summary['net_return_ratio_delta'])}."
        )
    lines.extend(
        [
            f"- Combined exact trade match rate={_fmt_number(combined['exact_trade_match_rate'])}; trade-count delta={int(combined['trade_count_delta'])}; net-return delta={_fmt_number(combined['net_return_ratio_delta'])}.",
            f"- Combined timeout delta={int(combined['timeout_trade_count_delta'])}; avg-holding delta={_fmt_number(combined['avg_holding_bars_delta'])}.",
        ]
    )

    integrated_rows = by_symbol_df[by_symbol_df["arm"]
                                   == INTEGRATED_ARM.name].copy()
    for symbol in symbols:
        row = integrated_rows[integrated_rows["symbol"]
                              == symbol].iloc[0].to_dict()
        lines.append(
            f"- {symbol} integrated overlay coverage: observed_overlay_trades={int(row.get('overlay_observed_trade_count') or 0)}, exit_hold_quality_mean={_fmt_number(row.get('exit_hold_quality_mean'))}, exit_context_validity_mean={_fmt_number(row.get('exit_context_validity_mean'))}."
        )

    lines.extend(
        [
            "",
            "## INFERENCE",
            "- Explainability without economic harm is supported at the recorder core-replay layer because the integrated arm preserved exact trade parity while exposing additional C.1/C.3/C.4 trace state.",
            "- Trade-quality improvement is not proven as a realized economic outcome because the integrated overlays are advisory-only and therefore do not change entry/exit behavior.",
            "- Stale/zombie reduction is not proven as a realized runtime effect because timeout counts and trade lifecycles remain unchanged between arms.",
        ]
    )

    slow_rows = cohort_df[
        (cohort_df["arm"] == INTEGRATED_ARM.name)
        & (cohort_df["cohort"] == "PROFITABLE_SLOW_REVERSION")
    ].copy()
    if not slow_rows.empty:
        for row in slow_rows.to_dict(orient="records"):
            lines.append(
                f"- {row['symbol']} profitable slow reversions remain present under the integrated line: trade_count={int(row['trade_count'])}, avg_holding_bars={_fmt_number(row['avg_holding_bars'])}, exit_hold_quality_mean={_fmt_number(row.get('exit_hold_quality_mean'))}, exit_context_validity_mean={_fmt_number(row.get('exit_context_validity_mean'))}."
            )
        lines.append(
            "- That profitable slow-reversion cohort is the main promotion risk: if C.3/C.4 are promoted into hard gating without broader evidence, valid slow mean reversions could be cut early."
        )

    weak_context = cohort_df[
        (cohort_df["arm"] == INTEGRATED_ARM.name)
        & (cohort_df["cohort"] == "WEAK_CONTEXT_EXIT")
    ].copy()
    valid_context = cohort_df[
        (cohort_df["arm"] == INTEGRATED_ARM.name)
        & (cohort_df["cohort"] == "VALID_CONTEXT_EXIT")
    ].copy()
    if not weak_context.empty or not valid_context.empty:
        lines.extend(["", "## Cohort Readout"])
        for row in valid_context.to_dict(orient="records"):
            lines.append(
                f"- {row['symbol']} VALID_CONTEXT_EXIT: trade_count={int(row['trade_count'])}, net_return_ratio={_fmt_number(row['net_return_ratio'])}, win_rate={_fmt_number(row['win_rate'])}."
            )
        for row in weak_context.to_dict(orient="records"):
            lines.append(
                f"- {row['symbol']} WEAK_CONTEXT_EXIT: trade_count={int(row['trade_count'])}, net_return_ratio={_fmt_number(row['net_return_ratio'])}, win_rate={_fmt_number(row['win_rate'])}."
            )

    lines.extend(
        [
            "",
            "## ASSUMPTION",
            "- This validation replays md_amr strategy-core decisions plus asset TP/SL projection from recorder OHLCV bars.",
            "- It uses recorder regime/regime_conf columns as the handler-owned context feed for the integrated arm.",
            "- It does not reconstruct full live warmup, objective-engine, gateway, or exchange-side state machines.",
            "",
            "## UNKNOWN",
            "- Full end-to-end economic impact under the complete DecisionMaking/Execution stack remains unknown because the repo does not contain a general md_amr backtest engine or config-isolation harness for A.1 vs integrated overlays.",
            "- Post-patch live or testnet runtime economics for integrated C.1/C.2/C.3/C.4 remain unknown beyond the existing 21h forensic activation proof.",
            "",
            "## Verdict",
            "- Economic promotion: not justified from this package. The integrated line is economically neutral on the bounded recorder replay surface, not economically superior.",
            "- Explainability: justified. The integrated line adds interpretable trade-state segmentation without measured economic drift on the bounded replay surface.",
            "- Stale/zombie reduction: not proven because overlays are advisory-only.",
            "- Over-penalization risk: still open if future promotion turns hold/context overlays into hard gates.",
        ]
    )
    return "\n".join(lines) + "\n"


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate md_amr integrated C.1/C.2/C.3/C.4 overlays against baseline A.1 on recorder data."
    )
    parser.add_argument(
        "--md-amr-yaml", default="config/aurora/strategies/md_amr.yaml")
    parser.add_argument("--recorder-dir", default="data/recorder")
    parser.add_argument("--symbols", nargs="+", default=["XRPUSDT", "BNBUSDT"])
    parser.add_argument("--start", type=_parse_date, default=None)
    parser.add_argument("--end", type=_parse_date, default=None)
    parser.add_argument("--tf-sec", type=int, default=TF_SEC)
    parser.add_argument("--warmup-bars", type=int, default=96)
    parser.add_argument(
        "--by-symbol-out",
        default="reports/md_amr_integrated_validation_by_symbol.csv",
    )
    parser.add_argument(
        "--cohorts-out",
        default="reports/md_amr_integrated_validation_cohorts.csv",
    )
    parser.add_argument(
        "--summary-out",
        default="reports/md_amr_integrated_validation_summary.csv",
    )
    parser.add_argument(
        "--report-out",
        default="config/docs/MD_AMR_INTEGRATED_VALIDATION_REPORT.md",
    )
    parser.add_argument(
        "--trades-out",
        default="reports/md_amr_integrated_validation_trades.csv",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if int(args.tf_sec) != TF_SEC:
        raise SystemExit(
            "Only tf_sec=900 is supported for md_amr integrated validation.")

    symbols = [str(symbol).upper() for symbol in args.symbols]
    calibrator._require_md_amr_runtime()

    md_amr_cfg = calibrator._load_md_amr_yaml(Path(args.md_amr_yaml))
    base_params = calibrator._extract_base_params(md_amr_cfg)
    weights = calibrator._extract_baseline_weights(md_amr_cfg)
    asset_cfgs = calibrator._extract_asset_configs(md_amr_cfg, symbols)

    baseline_params = dict(base_params)
    baseline_params["max_hold_bars"] = A1_MAX_HOLD_BARS
    baseline_params["target_approach_pct"] = A1_TARGET_APPROACH_PCT
    integrated_params = dict(base_params)

    df = calibrator._LOAD_RECORDER_900(
        Path(args.recorder_dir),
        symbols=symbols,
        start=args.start,
        end=args.end,
        basis_tf_sec=int(args.tf_sec),
    )
    if df.empty:
        raise SystemExit(
            "No recorder rows found for requested symbols/date range.")

    trade_rows: list[dict[str, Any]] = []
    by_symbol_rows: list[dict[str, Any]] = []
    cohort_rows: list[dict[str, Any]] = []
    data_ranges: dict[str, tuple[str, str]] = {}

    for symbol in symbols:
        df_symbol = df[df["symbol"].astype(str) == symbol].copy()
        if df_symbol.empty:
            raise SystemExit(
                f"Recorder dataset contains no rows for symbol {symbol}.")
        data_ranges[symbol] = (
            str(pd.to_datetime(
                int(df_symbol["timestamp"].min()), unit="ms", utc=True).date()),
            str(pd.to_datetime(
                int(df_symbol["timestamp"].max()), unit="ms", utc=True).date()),
        )

        symbol_trade_rows = {
            BASELINE_ARM.name: _simulate_symbol_arm(
                df_symbol,
                symbol=symbol,
                arm=BASELINE_ARM,
                base_params=baseline_params,
                weights=weights,
                asset_cfg=asset_cfgs[symbol],
                tf_sec=int(args.tf_sec),
                warmup_bars=int(args.warmup_bars),
            ),
            INTEGRATED_ARM.name: _simulate_symbol_arm(
                df_symbol,
                symbol=symbol,
                arm=INTEGRATED_ARM,
                base_params=integrated_params,
                weights=weights,
                asset_cfg=asset_cfgs[symbol],
                tf_sec=int(args.tf_sec),
                warmup_bars=int(args.warmup_bars),
            ),
        }

        for arm in (BASELINE_ARM, INTEGRATED_ARM):
            arm_trades = pd.DataFrame(symbol_trade_rows[arm.name])
            if arm_trades.empty:
                arm_trades = pd.DataFrame(columns=[
                    "trade_id",
                    "symbol",
                    "side",
                    "entry_ts_ms",
                    "exit_ts_ms",
                    "gross_return_ratio",
                    "net_return_ratio",
                    "holding_bars",
                    "trade_signature",
                ])
            trade_rows.extend(arm_trades.to_dict(orient="records"))
            by_symbol_rows.append(
                _aggregate_arm_metrics(
                    trades=arm_trades,
                    symbol=symbol,
                    arm=arm,
                    row_count=int(len(df_symbol)),
                    unique_days=int(pd.to_datetime(
                        df_symbol["timestamp"], unit="ms", utc=True).dt.date.nunique()),
                    start_ts_ms=int(df_symbol["timestamp"].min()),
                    end_ts_ms=int(df_symbol["timestamp"].max()),
                    max_hold_bars=A1_MAX_HOLD_BARS,
                )
            )
            cohort_rows.extend(
                _build_cohort_rows(
                    trades=arm_trades,
                    arm=arm,
                    symbol=symbol,
                    max_hold_bars=A1_MAX_HOLD_BARS,
                )
            )

    trade_df = pd.DataFrame(trade_rows)
    by_symbol_df = pd.DataFrame(by_symbol_rows)
    cohort_df = pd.DataFrame(cohort_rows)

    summary_rows: list[dict[str, Any]] = []
    for scope in symbols + ["COMBINED"]:
        if scope == "COMBINED":
            base_trades = trade_df[trade_df["arm"] == BASELINE_ARM.name].copy()
            integrated_trades = trade_df[trade_df["arm"]
                                         == INTEGRATED_ARM.name].copy()
            baseline_row = _aggregate_arm_metrics(
                trades=base_trades,
                symbol=scope,
                arm=BASELINE_ARM,
                row_count=int(len(df)),
                unique_days=int(pd.to_datetime(
                    df["timestamp"], unit="ms", utc=True).dt.date.nunique()),
                start_ts_ms=int(df["timestamp"].min()),
                end_ts_ms=int(df["timestamp"].max()),
                max_hold_bars=A1_MAX_HOLD_BARS,
            )
            integrated_row = _aggregate_arm_metrics(
                trades=integrated_trades,
                symbol=scope,
                arm=INTEGRATED_ARM,
                row_count=int(len(df)),
                unique_days=int(pd.to_datetime(
                    df["timestamp"], unit="ms", utc=True).dt.date.nunique()),
                start_ts_ms=int(df["timestamp"].min()),
                end_ts_ms=int(df["timestamp"].max()),
                max_hold_bars=A1_MAX_HOLD_BARS,
            )
        else:
            base_trades = trade_df[
                (trade_df["arm"] == BASELINE_ARM.name) & (
                    trade_df["symbol"] == scope)
            ].copy()
            integrated_trades = trade_df[
                (trade_df["arm"] == INTEGRATED_ARM.name) & (
                    trade_df["symbol"] == scope)
            ].copy()
            baseline_row = by_symbol_df[
                (by_symbol_df["arm"] == BASELINE_ARM.name) & (
                    by_symbol_df["symbol"] == scope)
            ].iloc[0].to_dict()
            integrated_row = by_symbol_df[
                (by_symbol_df["arm"] == INTEGRATED_ARM.name) & (
                    by_symbol_df["symbol"] == scope)
            ].iloc[0].to_dict()
        match_count, match_rate = _match_trade_signatures(
            base_trades, integrated_trades)
        summary_rows.append(
            _summary_row(
                scope=scope,
                baseline_row=baseline_row,
                integrated_row=integrated_row,
                match_count=match_count,
                match_rate=match_rate,
            )
        )

    summary_df = pd.DataFrame(summary_rows)
    report_text = _render_report(
        symbols=symbols,
        yaml_params={
            "max_hold_bars": integrated_params["max_hold_bars"],
            "target_approach_pct": integrated_params["target_approach_pct"],
        },
        by_symbol_df=by_symbol_df,
        summary_df=summary_df,
        cohort_df=cohort_df,
        data_ranges=data_ranges,
    )

    by_symbol_out = Path(args.by_symbol_out)
    cohorts_out = Path(args.cohorts_out)
    summary_out = Path(args.summary_out)
    report_out = Path(args.report_out)
    trades_out = Path(args.trades_out)
    for path in (by_symbol_out, cohorts_out, summary_out, report_out, trades_out):
        _ensure_parent(path)

    trade_df.to_csv(trades_out, index=False)
    by_symbol_df.sort_values(["symbol", "arm"], kind="mergesort").to_csv(
        by_symbol_out, index=False)
    cohort_df.sort_values(["symbol", "arm", "cohort_type", "cohort"],
                          kind="mergesort").to_csv(cohorts_out, index=False)
    summary_df.sort_values(["scope"], kind="mergesort").to_csv(
        summary_out, index=False)
    report_out.write_text(report_text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
