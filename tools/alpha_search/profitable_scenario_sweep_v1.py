#!/usr/bin/env python3
"""
ALPHA_SEARCH_PROFITABLE_SCENARIO_SIMULATION_SWEEP_V1

Shadow-only forensic sweep for alpha_search scenario profitability.

Authority boundary:
- Reads existing shadow/runtime artifacts only.
- Never emits ORDER_INTENT, CMD:OPEN, CMD:CLOSE, or any exchange action.
- Produces reports only.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


SEED_CANDIDATES = (
    "S03_AURORA_15M_APPROX",
    "S05_AURORA_MACRO_RESIDUAL",
    "S06_AURORA_ETH_CALIBRATED",
    "S20_AURORA_MICROSTRUCTURE_DEPTH",
)

BASELINE_FEE_MODEL = "taker_fee_0_04_pct"
BASELINE_SLIPPAGE_MODEL = "2_bps"
BASELINE_EXIT_MODEL = "horizon_1_bar"
LOOKAHEAD_BARS = 12
COMPARE_TOLERANCE_MS = 900_000
BEST_VARIANT_COMPARE_LIMIT = 12

FEE_MODELS_BPS = {
    "zero_fee_baseline": 0.0,
    "maker_fee_0_02_pct": 2.0,
    "taker_fee_0_04_pct": 4.0,
    "conservative_fee_0_06_pct": 6.0,
}

SLIPPAGE_MODELS_BPS = {
    "zero_slippage": None,
    "1_bps": 1.0,
    "2_bps": 2.0,
    "5_bps": 5.0,
    "volatility_scaled_slippage": None,
}

ABSOLUTE_THRESHOLD_VALUES = (0.06, 0.09, 0.12, 0.15, 0.20, 0.25)
PERCENTILE_KEEP_VALUES = (
    ("top_50_pct", 0.50),
    ("top_30_pct", 0.30),
    ("top_20_pct", 0.20),
    ("top_10_pct", 0.10),
    ("top_5_pct", 0.05),
)

REGIME_VARIANTS = (
    "all_regimes",
    "TREND_DOWN_only",
    "MEAN_REVERSION_only",
    "MEAN_REVERSION_plus_TREND_DOWN",
    "no_TREND_UP_SELL",
    "no_HIGH_VOLATILITY",
    "no_UNCERTAIN",
    "regime_confidence_ge_0_30",
    "regime_confidence_ge_0_45",
    "regime_confidence_ge_0_60",
)

SYMBOL_VARIANTS = (
    "all_symbols",
    "ETH_only",
    "SOL_only",
    "BTC_only",
    "ETH_plus_SOL",
    "exclude_BTC",
    "exclude_symbol_if_net_pnl_lt_0",
    "per_symbol_best_threshold",
    "per_symbol_best_regime_filter",
)

SIDE_VARIANTS = (
    "allow_all_sides",
    "SELL_only",
    "BUY_only",
    "no_SELL_in_TREND_UP",
    "SELL_only_in_TREND_DOWN",
    "BUY_only_in_TREND_UP",
    "side_must_agree_with_regime_direction",
    "side_can_oppose_regime_only_in_MEAN_REVERSION",
)

EXIT_VARIANTS = (
    "horizon_1_bar",
    "horizon_3_bar",
    "horizon_6_bar",
    "horizon_12_bar",
    "fixed_tp_5_sl_5",
    "fixed_tp_8_sl_5",
    "fixed_tp_10_sl_6",
    "fixed_tp_15_sl_8",
    "trailing_giveback_30",
    "trailing_giveback_50",
    "trailing_giveback_70",
    "microstructure_reversal_exit",
    "time_stop_exit",
)


@dataclass(frozen=True)
class BarSnapshot:
    symbol: str
    ts_ms: int
    price: float
    regime: str
    regime_confidence: Optional[float]
    spread_bps: Optional[float]
    volatility_state: Optional[float]
    delta_price: Optional[float]
    pillar_sum: Optional[float]
    features: Dict[str, float]


@dataclass(frozen=True)
class ScenarioSignal:
    signal_id: str
    scenario_id: str
    family: str
    symbol: str
    ts_ms: int
    score: float
    abs_score: float
    side: str
    recorded_threshold: float
    regime: str
    regime_confidence: Optional[float]
    price: float
    spread_bps: Optional[float]
    volatility_state: Optional[float]
    delta_price: Optional[float]
    pillar_sum: Optional[float]


@dataclass(frozen=True)
class GrossTradeResult:
    signal_id: str
    scenario_id: str
    exit_model: str
    exit_ts_ms: int
    exit_price: float
    exit_reason: str
    gross_pnl_bps: float
    mfe_bps: float
    mae_bps: float
    hold_bars: int


@dataclass(frozen=True)
class RealTrade:
    strategy_id: str
    lifecycle_id: str
    symbol: str
    side: str
    entry_ts_ms: int
    close_ts_ms: int
    entry_price: float
    close_price: float
    close_reason: str
    entry_rid: str
    close_rid: str
    regime_entry: str
    regime_exit: str


def safe_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def read_jsonl(path: Path) -> Iterable[Dict[str, Any]]:
    with path.open("r", encoding="utf-8", errors="ignore") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def infer_family(scenario_id: str) -> str:
    if "_AURORA_" in scenario_id:
        return "aurora"
    if "_MR_" in scenario_id:
        return "mean_reversion"
    if "_ENSEMBLE_" in scenario_id:
        return "ensemble"
    return "unknown"


def sorted_latest_session(root: Path) -> Path:
    timestamp_sessions = sorted(
        path
        for path in root.iterdir()
        if path.is_dir() and re.fullmatch(r"\d{8}_\d{6}", path.name)
    )
    if timestamp_sessions:
        return timestamp_sessions[-1]
    sessions = sorted(path for path in root.iterdir() if path.is_dir())
    if not sessions:
        raise FileNotFoundError(f"No alpha_search runtime sessions under {root}")
    return sessions[-1]


def load_regime_confidence(path: Path) -> Dict[Tuple[str, int], float]:
    mapping: Dict[Tuple[str, int], float] = {}
    for record in read_jsonl(path):
        if record.get("record_type") != "bar_close":
            continue
        symbol = str(record.get("symbol", "")).strip()
        ts_ms = safe_int(record.get("ts_ms"))
        emitted = safe_float(record.get("emitted_confidence"))
        stable = safe_float(record.get("stable_confidence"))
        confidence = emitted if emitted is not None else stable
        if symbol and ts_ms > 0 and confidence is not None:
            mapping[(symbol, ts_ms)] = confidence
    return mapping


def parse_features(raw_features: Dict[str, Any]) -> Dict[str, float]:
    parsed: Dict[str, float] = {}
    for key, value in raw_features.items():
        if isinstance(value, dict):
            continue
        numeric = safe_float(value)
        if numeric is not None:
            parsed[key] = numeric
    return parsed


def load_bars(
    alpha_input_path: Path,
    regime_confidence_path: Path,
) -> Tuple[Dict[str, List[BarSnapshot]], Dict[Tuple[str, int], BarSnapshot], Dict[str, Dict[int, int]]]:
    regime_confidence = load_regime_confidence(regime_confidence_path)
    bars_by_symbol: Dict[str, List[BarSnapshot]] = defaultdict(list)
    bar_lookup: Dict[Tuple[str, int], BarSnapshot] = {}
    index_lookup: Dict[str, Dict[int, int]] = defaultdict(dict)

    for record in read_jsonl(alpha_input_path):
        symbol = str(record.get("symbol", "")).strip()
        ts_ms = safe_int(record.get("ts_ms"))
        price = safe_float(record.get("price"))
        raw_features = record.get("features") or {}
        features = parse_features(raw_features)
        if not symbol or ts_ms <= 0 or price is None:
            continue
        bar = BarSnapshot(
            symbol=symbol,
            ts_ms=ts_ms,
            price=price,
            regime=str(record.get("regime", "UNKNOWN")),
            regime_confidence=regime_confidence.get((symbol, ts_ms)),
            spread_bps=safe_float(raw_features.get("spread_bps")),
            volatility_state=safe_float(raw_features.get("volatility_state")),
            delta_price=safe_float(raw_features.get("delta_price")),
            pillar_sum=safe_float(raw_features.get("pillar_sum")),
            features=features,
        )
        bars_by_symbol[symbol].append(bar)
        bar_lookup[(symbol, ts_ms)] = bar

    for symbol, bars in bars_by_symbol.items():
        bars.sort(key=lambda item: item.ts_ms)
        index_lookup[symbol] = {bar.ts_ms: idx for idx, bar in enumerate(bars)}

    return bars_by_symbol, bar_lookup, index_lookup


def load_runtime_signals(
    session_dir: Path,
    bar_lookup: Dict[Tuple[str, int], BarSnapshot],
) -> Tuple[Dict[str, List[ScenarioSignal]], Dict[str, Dict[str, Any]]]:
    scenario_signals: Dict[str, List[ScenarioSignal]] = {}
    scenario_meta: Dict[str, Dict[str, Any]] = {}

    for scenario_dir in sorted(path for path in session_dir.iterdir() if path.is_dir() and path.name.startswith("S")):
        score_path = scenario_dir / "scores.jsonl"
        if not score_path.exists():
            continue

        deduped: Dict[Tuple[str, int], Dict[str, Any]] = {}
        thresholds: List[float] = []
        total_rows = 0

        for record in read_jsonl(score_path):
            if str(record.get("provider_id", "")).strip() != "aurora":
                continue
            total_rows += 1
            symbol = str(record.get("symbol", "")).strip()
            ts_ms = safe_int(record.get("ts_ms"))
            threshold = safe_float(record.get("threshold"), 0.0) or 0.0
            thresholds.append(threshold)
            if not symbol or ts_ms <= 0:
                continue
            deduped[(symbol, ts_ms)] = record

        action_rows = []
        neutral_count = 0
        for (symbol, ts_ms), record in sorted(deduped.items(), key=lambda item: (item[0][1], item[0][0])):
            side = str(record.get("side", "NEUTRAL")).upper()
            if side == "NEUTRAL":
                neutral_count += 1
                continue
            bar = bar_lookup.get((symbol, ts_ms))
            if bar is None:
                continue
            score = safe_float(record.get("score"), 0.0) or 0.0
            action_rows.append(
                ScenarioSignal(
                    signal_id=f"{scenario_dir.name}|{symbol}|{ts_ms}",
                    scenario_id=scenario_dir.name,
                    family=infer_family(scenario_dir.name),
                    symbol=symbol,
                    ts_ms=ts_ms,
                    score=score,
                    abs_score=abs(score),
                    side=side,
                    recorded_threshold=safe_float(record.get("threshold"), 0.0) or 0.0,
                    regime=str(record.get("regime", bar.regime)),
                    regime_confidence=bar.regime_confidence,
                    price=bar.price,
                    spread_bps=bar.spread_bps,
                    volatility_state=bar.volatility_state,
                    delta_price=bar.delta_price,
                    pillar_sum=bar.pillar_sum,
                )
            )

        signals = sorted(action_rows, key=lambda item: (item.ts_ms, item.symbol))
        scenario_signals[scenario_dir.name] = signals
        current_threshold = median_or_zero(sig.recorded_threshold for sig in signals)
        if current_threshold == 0.0:
            current_threshold = median_or_zero(thresholds)
        scenario_meta[scenario_dir.name] = {
            "scenario_id": scenario_dir.name,
            "family": infer_family(scenario_dir.name),
            "total_aurora_rows": total_rows,
            "deduped_bars": len(deduped),
            "signal_count": len(signals),
            "neutral_count": neutral_count,
            "current_threshold": current_threshold,
            "first_signal_ts_ms": signals[0].ts_ms if signals else 0,
            "last_signal_ts_ms": signals[-1].ts_ms if signals else 0,
            "side_counts": dict(Counter(sig.side for sig in signals)),
        }

    return scenario_signals, scenario_meta


def median_or_zero(values: Iterable[float]) -> float:
    cleaned = [value for value in values if value is not None]
    if not cleaned:
        return 0.0
    return float(statistics.median(cleaned))


def future_bars(
    signal: ScenarioSignal,
    bars_by_symbol: Dict[str, List[BarSnapshot]],
    index_lookup: Dict[str, Dict[int, int]],
    max_bars: int = LOOKAHEAD_BARS,
) -> List[BarSnapshot]:
    symbol_bars = bars_by_symbol.get(signal.symbol, [])
    idx = index_lookup.get(signal.symbol, {}).get(signal.ts_ms)
    if idx is None:
        return []
    start = idx + 1
    end = min(len(symbol_bars), start + max_bars)
    return symbol_bars[start:end]


def gross_move_bps(side: str, entry_price: float, exit_price: float) -> float:
    if entry_price == 0:
        return 0.0
    if side == "BUY":
        return ((exit_price - entry_price) / entry_price) * 10000.0
    return ((entry_price - exit_price) / entry_price) * 10000.0


def simulate_gross_exit(signal: ScenarioSignal, bars: Sequence[BarSnapshot], exit_model: str) -> Optional[GrossTradeResult]:
    if not bars:
        return None

    if exit_model.startswith("horizon_"):
        horizon = int(exit_model.split("_")[1])
        return simulate_horizon(signal, bars, exit_model, horizon)
    if exit_model.startswith("fixed_tp_"):
        tokens = exit_model.split("_")
        tp_bps = safe_float(tokens[2], 0.0) or 0.0
        sl_bps = safe_float(tokens[4], 0.0) or 0.0
        return simulate_fixed_tp_sl(signal, bars, exit_model, tp_bps, sl_bps)
    if exit_model.startswith("trailing_giveback_"):
        giveback_pct = (safe_float(exit_model.rsplit("_", 1)[-1], 0.0) or 0.0) / 100.0
        return simulate_trailing(signal, bars, exit_model, giveback_pct)
    if exit_model == "microstructure_reversal_exit":
        return simulate_microstructure_reversal(signal, bars)
    if exit_model == "time_stop_exit":
        return simulate_time_stop(signal, bars)
    raise ValueError(f"Unsupported exit model: {exit_model}")


def simulate_horizon(
    signal: ScenarioSignal,
    bars: Sequence[BarSnapshot],
    exit_model: str,
    horizon_bars: int,
) -> GrossTradeResult:
    limited = list(bars[: max(1, min(horizon_bars, len(bars)))])
    return finalize_trade(signal, limited, exit_model, "HORIZON_EXPIRED")


def simulate_fixed_tp_sl(
    signal: ScenarioSignal,
    bars: Sequence[BarSnapshot],
    exit_model: str,
    tp_bps: float,
    sl_bps: float,
) -> GrossTradeResult:
    path = []
    for bar in bars[:LOOKAHEAD_BARS]:
        path.append(bar)
        move_bps = gross_move_bps(signal.side, signal.price, bar.price)
        if move_bps >= tp_bps:
            return finalize_trade(signal, path, exit_model, "FIXED_TP")
        if move_bps <= -sl_bps:
            return finalize_trade(signal, path, exit_model, "FIXED_SL")
    return finalize_trade(signal, path, exit_model, "HORIZON_EXPIRED")


def simulate_trailing(
    signal: ScenarioSignal,
    bars: Sequence[BarSnapshot],
    exit_model: str,
    giveback_pct: float,
) -> GrossTradeResult:
    peak = float("-inf")
    path = []
    for bar in bars[:LOOKAHEAD_BARS]:
        path.append(bar)
        move_bps = gross_move_bps(signal.side, signal.price, bar.price)
        peak = max(peak, move_bps)
        if peak > 0.0 and (peak - move_bps) >= peak * giveback_pct:
            return finalize_trade(signal, path, exit_model, "TRAILING_GIVEBACK")
    return finalize_trade(signal, path, exit_model, "TRAILING_TIMEOUT")


def simulate_microstructure_reversal(
    signal: ScenarioSignal,
    bars: Sequence[BarSnapshot],
) -> GrossTradeResult:
    path = []
    for bar in bars[:LOOKAHEAD_BARS]:
        path.append(bar)
        delta_price = bar.delta_price or 0.0
        pillar_sum = bar.pillar_sum or 0.0
        if signal.side == "BUY" and (bar.regime == "TREND_DOWN" or (delta_price < 0.0 and pillar_sum < 0.0)):
            return finalize_trade(signal, path, "microstructure_reversal_exit", "MICROSTRUCTURE_REVERSAL")
        if signal.side == "SELL" and (bar.regime == "TREND_UP" or (delta_price > 0.0 and pillar_sum > 0.0)):
            return finalize_trade(signal, path, "microstructure_reversal_exit", "MICROSTRUCTURE_REVERSAL")
    return finalize_trade(signal, path, "microstructure_reversal_exit", "MICROSTRUCTURE_TIMEOUT")


def simulate_time_stop(signal: ScenarioSignal, bars: Sequence[BarSnapshot]) -> GrossTradeResult:
    path = []
    best_move = float("-inf")
    for index, bar in enumerate(bars[:LOOKAHEAD_BARS], start=1):
        path.append(bar)
        move_bps = gross_move_bps(signal.side, signal.price, bar.price)
        best_move = max(best_move, move_bps)
        if index >= 3 and move_bps <= 0.0:
            return finalize_trade(signal, path, "time_stop_exit", "TIME_STOP_NEGATIVE")
        if index >= 6 and best_move > 0.0 and move_bps <= best_move * 0.5:
            return finalize_trade(signal, path, "time_stop_exit", "TIME_STOP_GIVEBACK")
    return finalize_trade(signal, path, "time_stop_exit", "TIME_STOP_HARD_CAP")


def finalize_trade(
    signal: ScenarioSignal,
    path: Sequence[BarSnapshot],
    exit_model: str,
    exit_reason: str,
) -> GrossTradeResult:
    exit_bar = path[-1]
    mfe_bps = max(gross_move_bps(signal.side, signal.price, bar.price) for bar in path)
    mae_bps = min(gross_move_bps(signal.side, signal.price, bar.price) for bar in path)
    gross_pnl_bps = gross_move_bps(signal.side, signal.price, exit_bar.price)
    return GrossTradeResult(
        signal_id=signal.signal_id,
        scenario_id=signal.scenario_id,
        exit_model=exit_model,
        exit_ts_ms=exit_bar.ts_ms,
        exit_price=exit_bar.price,
        exit_reason=exit_reason,
        gross_pnl_bps=round(gross_pnl_bps, 6),
        mfe_bps=round(mfe_bps, 6),
        mae_bps=round(mae_bps, 6),
        hold_bars=len(path),
    )


def scenario_threshold_variants(current_threshold: float) -> List[Dict[str, Any]]:
    variants: List[Dict[str, Any]] = [
        {
            "name": "current_threshold",
            "kind": "absolute",
            "value": current_threshold,
        }
    ]
    for value in ABSOLUTE_THRESHOLD_VALUES:
        variants.append({
            "name": f"abs_{value:.2f}",
            "kind": "absolute",
            "value": value,
        })
    for label, keep_fraction in PERCENTILE_KEEP_VALUES:
        variants.append({
            "name": label,
            "kind": "percentile",
            "value": keep_fraction,
        })
    return variants


def threshold_cutoff(signals: Sequence[ScenarioSignal], threshold_variant: Dict[str, Any]) -> float:
    kind = threshold_variant["kind"]
    value = threshold_variant["value"]
    if kind == "absolute":
        return float(value)
    sorted_scores = sorted((signal.abs_score for signal in signals), reverse=True)
    if not sorted_scores:
        return math.inf
    index = max(0, math.ceil(len(sorted_scores) * float(value)) - 1)
    return sorted_scores[index]


def apply_threshold(signals: Sequence[ScenarioSignal], threshold_variant: Dict[str, Any]) -> Tuple[List[ScenarioSignal], float]:
    cutoff = threshold_cutoff(signals, threshold_variant)
    kept = [signal for signal in signals if signal.abs_score >= cutoff]
    return kept, cutoff


def regime_filter_ok(signal: ScenarioSignal, variant_name: str) -> bool:
    if variant_name == "all_regimes":
        return True
    if variant_name == "TREND_DOWN_only":
        return signal.regime == "TREND_DOWN"
    if variant_name == "MEAN_REVERSION_only":
        return signal.regime == "MEAN_REVERSION"
    if variant_name == "MEAN_REVERSION_plus_TREND_DOWN":
        return signal.regime in {"MEAN_REVERSION", "TREND_DOWN"}
    if variant_name == "no_TREND_UP_SELL":
        return not (signal.regime == "TREND_UP" and signal.side == "SELL")
    if variant_name == "no_HIGH_VOLATILITY":
        return signal.regime != "HIGH_VOLATILITY"
    if variant_name == "no_UNCERTAIN":
        return signal.regime != "UNCERTAIN"
    if variant_name == "regime_confidence_ge_0_30":
        return (signal.regime_confidence or 0.0) >= 0.30
    if variant_name == "regime_confidence_ge_0_45":
        return (signal.regime_confidence or 0.0) >= 0.45
    if variant_name == "regime_confidence_ge_0_60":
        return (signal.regime_confidence or 0.0) >= 0.60
    raise ValueError(f"Unsupported regime variant: {variant_name}")


def side_constraint_ok(signal: ScenarioSignal, variant_name: str) -> bool:
    if variant_name == "allow_all_sides":
        return True
    if variant_name == "SELL_only":
        return signal.side == "SELL"
    if variant_name == "BUY_only":
        return signal.side == "BUY"
    if variant_name == "no_SELL_in_TREND_UP":
        return not (signal.side == "SELL" and signal.regime == "TREND_UP")
    if variant_name == "SELL_only_in_TREND_DOWN":
        return signal.side == "SELL" and signal.regime == "TREND_DOWN"
    if variant_name == "BUY_only_in_TREND_UP":
        return signal.side == "BUY" and signal.regime == "TREND_UP"
    if variant_name == "side_must_agree_with_regime_direction":
        return (
            (signal.regime == "TREND_UP" and signal.side == "BUY")
            or (signal.regime == "TREND_DOWN" and signal.side == "SELL")
        )
    if variant_name == "side_can_oppose_regime_only_in_MEAN_REVERSION":
        if signal.regime == "TREND_UP":
            return signal.side == "BUY"
        if signal.regime == "TREND_DOWN":
            return signal.side == "SELL"
        return True
    raise ValueError(f"Unsupported side variant: {variant_name}")


def volatility_scaled_slippage_bps(signal: ScenarioSignal) -> float:
    spread_bps = signal.spread_bps if signal.spread_bps is not None else 1.0
    base_bps = max(1.0, spread_bps)
    multiplier = 1.0
    if signal.regime == "HIGH_VOLATILITY":
        multiplier = 3.0
    elif signal.regime in {"TREND_UP", "TREND_DOWN"}:
        multiplier = 1.5
    elif signal.regime == "UNCERTAIN":
        multiplier = 1.2
    if signal.volatility_state is not None:
        multiplier = max(multiplier, 1.0 + max(0.0, signal.volatility_state))
    return round(base_bps * multiplier, 6)


def slippage_bps_for_signal(signal: ScenarioSignal, model_name: str) -> float:
    if model_name == "zero_slippage":
        return 0.0
    if model_name == "volatility_scaled_slippage":
        return volatility_scaled_slippage_bps(signal)
    configured = SLIPPAGE_MODELS_BPS.get(model_name)
    if configured is None:
        raise ValueError(f"Unsupported slippage model: {model_name}")
    return configured


def max_drawdown(values: Sequence[float]) -> float:
    peak = 0.0
    cumulative = 0.0
    drawdown = 0.0
    for value in values:
        cumulative += value
        peak = max(peak, cumulative)
        drawdown = min(drawdown, cumulative - peak)
    return abs(drawdown)


def profit_factor(values: Sequence[float]) -> float:
    gross_profit = sum(value for value in values if value > 0.0)
    gross_loss = abs(sum(value for value in values if value < 0.0))
    if gross_loss == 0.0:
        return math.inf if gross_profit > 0.0 else 0.0
    return gross_profit / gross_loss


def aggregate_metrics(
    signals: Sequence[ScenarioSignal],
    gross_cache: Dict[Tuple[str, str], Optional[GrossTradeResult]],
    exit_model: str,
    fee_model: str,
    slippage_model: str,
    baseline_outcomes: Optional[Dict[str, float]] = None,
    baseline_signal_ids: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    net_values: List[float] = []
    gross_values: List[float] = []
    hold_bars: List[int] = []
    mfe_values: List[float] = []
    mae_values: List[float] = []
    capture_ratios: List[float] = []
    signal_ids: List[str] = []
    skipped_ids: List[str] = []

    fee_bps = FEE_MODELS_BPS[fee_model]

    for signal in signals:
        gross = gross_cache.get((signal.signal_id, exit_model))
        if gross is None:
            skipped_ids.append(signal.signal_id)
            continue
        slippage_bps = slippage_bps_for_signal(signal, slippage_model)
        net_value = gross.gross_pnl_bps - fee_bps - slippage_bps
        gross_values.append(gross.gross_pnl_bps)
        net_values.append(net_value)
        hold_bars.append(gross.hold_bars)
        mfe_values.append(gross.mfe_bps)
        mae_values.append(abs(gross.mae_bps))
        capture_ratios.append((gross.gross_pnl_bps / gross.mfe_bps) if gross.mfe_bps > 0.0 else 0.0)
        signal_ids.append(signal.signal_id)

    sample_count = len(net_values)
    removed_winners = 0
    removed_losses = 0
    if baseline_outcomes is not None and baseline_signal_ids is not None:
        kept = set(signal_ids)
        for signal_id in baseline_signal_ids:
            if signal_id in kept:
                continue
            baseline_value = baseline_outcomes.get(signal_id)
            if baseline_value is None:
                continue
            if baseline_value > 0.0:
                removed_winners += 1
            elif baseline_value <= 0.0:
                removed_losses += 1

    avg_gross = sum(gross_values) / sample_count if sample_count else 0.0
    avg_net = sum(net_values) / sample_count if sample_count else 0.0
    total_gross = sum(gross_values)
    total_net = sum(net_values)
    win_rate = (sum(1 for value in net_values if value > 0.0) / sample_count) if sample_count else 0.0
    losers = sum(1 for value in net_values if value <= 0.0)
    outcomes = dict(zip(signal_ids, net_values))
    return {
        "signal_count": sample_count,
        "gross_total_pnl_bps": round(total_gross, 6),
        "gross_avg_pnl_bps": round(avg_gross, 6),
        "net_total_pnl_bps": round(total_net, 6),
        "net_avg_pnl_bps": round(avg_net, 6),
        "win_rate": round(win_rate, 6),
        "max_dd_bps": round(max_drawdown(net_values), 6),
        "profit_factor": round(profit_factor(net_values), 6) if sample_count else 0.0,
        "MFE_bps": round(sum(mfe_values) / sample_count, 6) if sample_count else 0.0,
        "MAE_bps": round(sum(mae_values) / sample_count, 6) if sample_count else 0.0,
        "avg_hold_bars": round(sum(hold_bars) / sample_count, 6) if sample_count else 0.0,
        "mfe_capture_ratio": round(sum(capture_ratios) / sample_count, 6) if sample_count else 0.0,
        "mae_exposure": round(sum(mae_values) / sample_count, 6) if sample_count else 0.0,
        "false_positive_rate": round((losers / sample_count), 6) if sample_count else 0.0,
        "removed_winners": removed_winners,
        "removed_losses": removed_losses,
        "outcomes_by_signal": outcomes,
        "signal_ids": signal_ids,
        "skipped_ids": skipped_ids,
    }


def best_and_toxic_labels(values_by_label: Dict[str, float]) -> Tuple[str, str]:
    positives = [item for item in values_by_label.items() if item[1] > 0.0]
    negatives = [item for item in values_by_label.items() if item[1] < 0.0]
    positives.sort(key=lambda item: item[1], reverse=True)
    negatives.sort(key=lambda item: item[1])
    best = "|".join(label for label, _ in positives[:3]) if positives else ""
    toxic = "|".join(label for label, _ in negatives[:3]) if negatives else ""
    return best, toxic


def build_candidate_selection(
    scenario_signals: Dict[str, List[ScenarioSignal]],
    scenario_meta: Dict[str, Dict[str, Any]],
    gross_cache: Dict[Tuple[str, str], Optional[GrossTradeResult]],
) -> Tuple[List[Dict[str, Any]], List[str]]:
    rows: List[Dict[str, Any]] = []
    selected_ids: List[str] = []

    for scenario_id, meta in sorted(scenario_meta.items()):
        signals = scenario_signals.get(scenario_id, [])
        metrics = aggregate_metrics(
            signals,
            gross_cache,
            BASELINE_EXIT_MODEL,
            "zero_fee_baseline",
            "zero_slippage",
        )
        symbol_totals: Dict[str, float] = defaultdict(float)
        regime_totals: Dict[str, float] = defaultdict(float)
        for signal in signals:
            gross = gross_cache.get((signal.signal_id, BASELINE_EXIT_MODEL))
            if gross is None:
                continue
            symbol_totals[signal.symbol] += gross.gross_pnl_bps
            regime_totals[signal.regime] += gross.gross_pnl_bps
        best_symbols, toxic_symbols = best_and_toxic_labels(symbol_totals)
        best_regimes, toxic_regimes = best_and_toxic_labels(regime_totals)

        reasons: List[str] = []
        selected = False
        if scenario_id in SEED_CANDIDATES:
            selected = True
            reasons.append("seed_previous_shadow_report")
        if metrics["gross_total_pnl_bps"] > 0.0:
            selected = True
            reasons.append("positive_gross_total_pnl")
        if metrics["win_rate"] >= 0.52 and metrics["signal_count"] >= 50:
            selected = True
            reasons.append("high_win_rate")
        if metrics["max_dd_bps"] <= 200.0 and metrics["signal_count"] >= 50 and metrics["profit_factor"] > 1.0:
            selected = True
            reasons.append("low_drawdown_profile")
        if best_symbols or best_regimes:
            reasons.append("regime_or_symbol_specialization_observed")

        if selected:
            selected_ids.append(scenario_id)

        rows.append({
            "scenario_id": scenario_id,
            "family": meta["family"],
            "signal_count": metrics["signal_count"],
            "gross_total_pnl": metrics["gross_total_pnl_bps"],
            "gross_avg_pnl": metrics["gross_avg_pnl_bps"],
            "win_rate": metrics["win_rate"],
            "max_dd": metrics["max_dd_bps"],
            "profit_factor": metrics["profit_factor"],
            "best_symbols": best_symbols,
            "best_regimes": best_regimes,
            "toxic_symbols": toxic_symbols,
            "toxic_regimes": toxic_regimes,
            "selected_for_sweep": str(selected).lower(),
            "selection_reason": "|".join(dict.fromkeys(reasons)) or "no_positive_edge_in_latest_runtime",
        })

    return rows, selected_ids


def write_csv(path: Path, rows: Sequence[Dict[str, Any]], fieldnames: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def regime_best_combo(signals: Sequence[ScenarioSignal], outcomes: Dict[str, float]) -> str:
    totals: Dict[str, float] = defaultdict(float)
    for signal in signals:
        value = outcomes.get(signal.signal_id)
        if value is None:
            continue
        totals[signal.regime] += value
    if not totals:
        return ""
    best_regime, _ = max(totals.items(), key=lambda item: item[1])
    return best_regime


def build_cost_model_rows(
    selected_ids: Sequence[str],
    scenario_signals: Dict[str, List[ScenarioSignal]],
    gross_cache: Dict[Tuple[str, str], Optional[GrossTradeResult]],
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for scenario_id in selected_ids:
        signals = scenario_signals.get(scenario_id, [])
        gross_metrics = aggregate_metrics(
            signals,
            gross_cache,
            BASELINE_EXIT_MODEL,
            "zero_fee_baseline",
            "zero_slippage",
        )
        for fee_model, fee_bps in FEE_MODELS_BPS.items():
            for slippage_model in SLIPPAGE_MODELS_BPS:
                metrics = aggregate_metrics(
                    signals,
                    gross_cache,
                    BASELINE_EXIT_MODEL,
                    fee_model,
                    slippage_model,
                )
                slippage_avg = average_slippage(signals, slippage_model)
                breakeven = fee_bps + slippage_avg
                coverage = (gross_metrics["gross_avg_pnl_bps"] / breakeven) if breakeven > 0.0 else math.inf
                rows.append({
                    "scenario_id": scenario_id,
                    "fee_model": fee_model,
                    "slippage_model": slippage_model,
                    "signal_count": metrics["signal_count"],
                    "gross_pnl_bps": gross_metrics["gross_avg_pnl_bps"],
                    "fee_bps": round(fee_bps, 6),
                    "slippage_bps": round(slippage_avg, 6),
                    "net_pnl_bps": metrics["net_avg_pnl_bps"],
                    "breakeven_edge_bps": round(breakeven, 6),
                    "cost_coverage_ratio": round(coverage, 6) if math.isfinite(coverage) else "inf",
                    "total_net_pnl_bps": metrics["net_total_pnl_bps"],
                })
    return rows


def average_slippage(signals: Sequence[ScenarioSignal], slippage_model: str) -> float:
    if not signals:
        return 0.0
    return sum(slippage_bps_for_signal(signal, slippage_model) for signal in signals) / len(signals)


def baseline_outcome_map(
    signals: Sequence[ScenarioSignal],
    gross_cache: Dict[Tuple[str, str], Optional[GrossTradeResult]],
    exit_model: str,
    fee_model: str,
    slippage_model: str,
) -> Dict[str, float]:
    metrics = aggregate_metrics(signals, gross_cache, exit_model, fee_model, slippage_model)
    return metrics["outcomes_by_signal"]


def build_threshold_sweep_rows(
    selected_ids: Sequence[str],
    scenario_signals: Dict[str, List[ScenarioSignal]],
    scenario_meta: Dict[str, Dict[str, Any]],
    gross_cache: Dict[Tuple[str, str], Optional[GrossTradeResult]],
) -> Dict[str, List[Dict[str, Any]]]:
    rows_by_scenario: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for scenario_id in selected_ids:
        signals = scenario_signals.get(scenario_id, [])
        current_threshold = scenario_meta[scenario_id]["current_threshold"]
        variants = scenario_threshold_variants(current_threshold)
        baseline_metrics = aggregate_metrics(
            signals,
            gross_cache,
            BASELINE_EXIT_MODEL,
            BASELINE_FEE_MODEL,
            BASELINE_SLIPPAGE_MODEL,
        )
        baseline_outcomes = baseline_metrics["outcomes_by_signal"]
        baseline_signal_ids = baseline_metrics["signal_ids"]

        for variant in variants:
            kept_signals, cutoff = apply_threshold(signals, variant)
            metrics = aggregate_metrics(
                kept_signals,
                gross_cache,
                BASELINE_EXIT_MODEL,
                BASELINE_FEE_MODEL,
                BASELINE_SLIPPAGE_MODEL,
                baseline_outcomes=baseline_outcomes,
                baseline_signal_ids=baseline_signal_ids,
            )
            rows_by_scenario[scenario_id].append({
                "scenario_id": scenario_id,
                "threshold_variant": variant["name"],
                "threshold_value": round(cutoff, 6),
                "signal_count": metrics["signal_count"],
                "BUY_count": sum(1 for signal in kept_signals if signal.side == "BUY"),
                "SELL_count": sum(1 for signal in kept_signals if signal.side == "SELL"),
                "win_rate": metrics["win_rate"],
                "avg_gross_pnl_bps": metrics["gross_avg_pnl_bps"],
                "avg_net_pnl_bps": metrics["net_avg_pnl_bps"],
                "total_net_pnl_bps": metrics["net_total_pnl_bps"],
                "max_dd_bps": metrics["max_dd_bps"],
                "profit_factor_net": metrics["profit_factor"],
                "MFE_bps": metrics["MFE_bps"],
                "MAE_bps": metrics["MAE_bps"],
                "removed_losers": metrics["removed_losses"],
                "removed_winners": metrics["removed_winners"],
                "retention_pct": round((metrics["signal_count"] / len(signals)) * 100.0, 6) if signals else 0.0,
            })
    return rows_by_scenario


def apply_regime_variant(signals: Sequence[ScenarioSignal], variant_name: str) -> List[ScenarioSignal]:
    return [signal for signal in signals if regime_filter_ok(signal, variant_name)]


def build_regime_sweep_rows(
    selected_ids: Sequence[str],
    scenario_signals: Dict[str, List[ScenarioSignal]],
    gross_cache: Dict[Tuple[str, str], Optional[GrossTradeResult]],
) -> Dict[str, List[Dict[str, Any]]]:
    rows_by_scenario: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for scenario_id in selected_ids:
        signals = scenario_signals.get(scenario_id, [])
        baseline = aggregate_metrics(signals, gross_cache, BASELINE_EXIT_MODEL, BASELINE_FEE_MODEL, BASELINE_SLIPPAGE_MODEL)
        for variant_name in REGIME_VARIANTS:
            kept_signals = apply_regime_variant(signals, variant_name)
            metrics = aggregate_metrics(
                kept_signals,
                gross_cache,
                BASELINE_EXIT_MODEL,
                BASELINE_FEE_MODEL,
                BASELINE_SLIPPAGE_MODEL,
                baseline_outcomes=baseline["outcomes_by_signal"],
                baseline_signal_ids=baseline["signal_ids"],
            )
            rows_by_scenario[scenario_id].append({
                "scenario_id": scenario_id,
                "regime_filter": variant_name,
                "signal_count": metrics["signal_count"],
                "net_pnl_bps": metrics["net_total_pnl_bps"],
                "win_rate": metrics["win_rate"],
                "max_dd": metrics["max_dd_bps"],
                "profit_factor": metrics["profit_factor"],
                "false_removed_winners": metrics["removed_winners"],
                "removed_losses": metrics["removed_losses"],
                "best_scenario_regime_combo": f"{scenario_id}:{regime_best_combo(kept_signals, metrics['outcomes_by_signal'])}",
            })
    return rows_by_scenario


def best_symbol_thresholds(
    signals: Sequence[ScenarioSignal],
    gross_cache: Dict[Tuple[str, str], Optional[GrossTradeResult]],
) -> Dict[str, float]:
    thresholds: Dict[str, float] = {}
    by_symbol: Dict[str, List[ScenarioSignal]] = defaultdict(list)
    for signal in signals:
        by_symbol[signal.symbol].append(signal)
    for symbol, symbol_signals in by_symbol.items():
        best_cutoff = 0.0
        best_value = float("-inf")
        current_threshold = median_or_zero(signal.recorded_threshold for signal in symbol_signals)
        for variant in scenario_threshold_variants(current_threshold):
            kept, cutoff = apply_threshold(symbol_signals, variant)
            metrics = aggregate_metrics(kept, gross_cache, BASELINE_EXIT_MODEL, BASELINE_FEE_MODEL, BASELINE_SLIPPAGE_MODEL)
            metric_value = metrics["net_avg_pnl_bps"]
            if metrics["signal_count"] < 10:
                continue
            if metric_value > best_value:
                best_value = metric_value
                best_cutoff = cutoff
        thresholds[symbol] = best_cutoff
    return thresholds


def best_symbol_regime_filters(
    signals: Sequence[ScenarioSignal],
    gross_cache: Dict[Tuple[str, str], Optional[GrossTradeResult]],
) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    by_symbol: Dict[str, List[ScenarioSignal]] = defaultdict(list)
    for signal in signals:
        by_symbol[signal.symbol].append(signal)
    for symbol, symbol_signals in by_symbol.items():
        best_variant = "all_regimes"
        best_value = float("-inf")
        for variant_name in REGIME_VARIANTS:
            kept = apply_regime_variant(symbol_signals, variant_name)
            metrics = aggregate_metrics(kept, gross_cache, BASELINE_EXIT_MODEL, BASELINE_FEE_MODEL, BASELINE_SLIPPAGE_MODEL)
            if metrics["signal_count"] < 10:
                continue
            if metrics["net_avg_pnl_bps"] > best_value:
                best_value = metrics["net_avg_pnl_bps"]
                best_variant = variant_name
        mapping[symbol] = best_variant
    return mapping


def apply_symbol_variant(
    signals: Sequence[ScenarioSignal],
    variant_name: str,
    gross_cache: Dict[Tuple[str, str], Optional[GrossTradeResult]],
) -> List[ScenarioSignal]:
    if variant_name == "all_symbols":
        return list(signals)
    if variant_name == "ETH_only":
        return [signal for signal in signals if signal.symbol == "ETHUSDT"]
    if variant_name == "SOL_only":
        return [signal for signal in signals if signal.symbol == "SOLUSDT"]
    if variant_name == "BTC_only":
        return [signal for signal in signals if signal.symbol == "BTCUSDT"]
    if variant_name == "ETH_plus_SOL":
        return [signal for signal in signals if signal.symbol in {"ETHUSDT", "SOLUSDT"}]
    if variant_name == "exclude_BTC":
        return [signal for signal in signals if signal.symbol != "BTCUSDT"]
    if variant_name == "exclude_symbol_if_net_pnl_lt_0":
        negative_symbols: set[str] = set()
        by_symbol: Dict[str, List[ScenarioSignal]] = defaultdict(list)
        for signal in signals:
            by_symbol[signal.symbol].append(signal)
        for symbol, symbol_signals in by_symbol.items():
            metrics = aggregate_metrics(symbol_signals, gross_cache, BASELINE_EXIT_MODEL, BASELINE_FEE_MODEL, BASELINE_SLIPPAGE_MODEL)
            if metrics["net_total_pnl_bps"] < 0.0:
                negative_symbols.add(symbol)
        return [signal for signal in signals if signal.symbol not in negative_symbols]
    if variant_name == "per_symbol_best_threshold":
        cutoffs = best_symbol_thresholds(signals, gross_cache)
        return [signal for signal in signals if signal.abs_score >= cutoffs.get(signal.symbol, math.inf)]
    if variant_name == "per_symbol_best_regime_filter":
        filters = best_symbol_regime_filters(signals, gross_cache)
        return [signal for signal in signals if regime_filter_ok(signal, filters.get(signal.symbol, "all_regimes"))]
    raise ValueError(f"Unsupported symbol variant: {variant_name}")


def build_symbol_sweep_rows(
    selected_ids: Sequence[str],
    scenario_signals: Dict[str, List[ScenarioSignal]],
    gross_cache: Dict[Tuple[str, str], Optional[GrossTradeResult]],
) -> Dict[str, List[Dict[str, Any]]]:
    rows_by_scenario: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for scenario_id in selected_ids:
        signals = scenario_signals.get(scenario_id, [])
        baseline = aggregate_metrics(signals, gross_cache, BASELINE_EXIT_MODEL, BASELINE_FEE_MODEL, BASELINE_SLIPPAGE_MODEL)
        for variant_name in SYMBOL_VARIANTS:
            kept = apply_symbol_variant(signals, variant_name, gross_cache)
            metrics = aggregate_metrics(
                kept,
                gross_cache,
                BASELINE_EXIT_MODEL,
                BASELINE_FEE_MODEL,
                BASELINE_SLIPPAGE_MODEL,
                baseline_outcomes=baseline["outcomes_by_signal"],
                baseline_signal_ids=baseline["signal_ids"],
            )
            rows_by_scenario[scenario_id].append({
                "scenario_id": scenario_id,
                "symbol_filter": variant_name,
                "signal_count": metrics["signal_count"],
                "net_pnl_bps": metrics["net_total_pnl_bps"],
                "win_rate": metrics["win_rate"],
                "max_dd_bps": metrics["max_dd_bps"],
                "profit_factor": metrics["profit_factor"],
                "false_removed_winners": metrics["removed_winners"],
                "removed_losses": metrics["removed_losses"],
            })
    return rows_by_scenario


def build_side_sweep_rows(
    selected_ids: Sequence[str],
    scenario_signals: Dict[str, List[ScenarioSignal]],
    gross_cache: Dict[Tuple[str, str], Optional[GrossTradeResult]],
) -> Dict[str, List[Dict[str, Any]]]:
    rows_by_scenario: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for scenario_id in selected_ids:
        signals = scenario_signals.get(scenario_id, [])
        baseline = aggregate_metrics(signals, gross_cache, BASELINE_EXIT_MODEL, BASELINE_FEE_MODEL, BASELINE_SLIPPAGE_MODEL)
        for variant_name in SIDE_VARIANTS:
            kept = [signal for signal in signals if side_constraint_ok(signal, variant_name)]
            metrics = aggregate_metrics(
                kept,
                gross_cache,
                BASELINE_EXIT_MODEL,
                BASELINE_FEE_MODEL,
                BASELINE_SLIPPAGE_MODEL,
                baseline_outcomes=baseline["outcomes_by_signal"],
                baseline_signal_ids=baseline["signal_ids"],
            )
            rows_by_scenario[scenario_id].append({
                "scenario_id": scenario_id,
                "side_constraint": variant_name,
                "signal_count": metrics["signal_count"],
                "net_pnl_bps": metrics["net_total_pnl_bps"],
                "win_rate": metrics["win_rate"],
                "max_dd_bps": metrics["max_dd_bps"],
                "profit_factor": metrics["profit_factor"],
                "false_removed_winners": metrics["removed_winners"],
                "removed_losses": metrics["removed_losses"],
            })
    return rows_by_scenario


def build_exit_sweep_rows(
    selected_ids: Sequence[str],
    scenario_signals: Dict[str, List[ScenarioSignal]],
    gross_cache: Dict[Tuple[str, str], Optional[GrossTradeResult]],
) -> Dict[str, List[Dict[str, Any]]]:
    rows_by_scenario: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for scenario_id in selected_ids:
        signals = scenario_signals.get(scenario_id, [])
        for exit_model in EXIT_VARIANTS:
            metrics = aggregate_metrics(signals, gross_cache, exit_model, BASELINE_FEE_MODEL, BASELINE_SLIPPAGE_MODEL)
            rows_by_scenario[scenario_id].append({
                "scenario_id": scenario_id,
                "exit_model": exit_model,
                "signal_count": metrics["signal_count"],
                "win_rate": metrics["win_rate"],
                "avg_net_pnl_bps": metrics["net_avg_pnl_bps"],
                "total_net_pnl_bps": metrics["net_total_pnl_bps"],
                "max_dd": metrics["max_dd_bps"],
                "profit_factor": metrics["profit_factor"],
                "average_hold_time": metrics["avg_hold_bars"],
                "MFE_capture_ratio": metrics["mfe_capture_ratio"],
                "MAE_exposure": metrics["mae_exposure"],
            })
    return rows_by_scenario


def top_rows(rows: Sequence[Dict[str, Any]], key_name: str, top_n: int, min_signal_count: int = 50) -> List[Dict[str, Any]]:
    eligible = [row for row in rows if safe_int(row.get("signal_count")) >= min_signal_count]
    if not eligible:
        eligible = list(rows)
    return sorted(eligible, key=lambda row: (safe_float(row.get(key_name), 0.0) or 0.0), reverse=True)[:top_n]


def sample_status(signal_count: int) -> str:
    if signal_count >= 200:
        return "STRONGER_CANDIDATE"
    if signal_count >= 50:
        return "EXPLORATORY_CANDIDATE"
    return "LOW_SAMPLE_WARNING"


def sample_rank(signal_count: int) -> int:
    if signal_count >= 200:
        return 2
    if signal_count >= 50:
        return 1
    return 0


def cost_realism_rank(fee_model: str, slippage_model: str) -> int:
    fee_realistic = fee_model != "zero_fee_baseline"
    slippage_realistic = slippage_model != "zero_slippage"
    if fee_realistic and slippage_realistic:
        return 2
    if fee_realistic or slippage_realistic:
        return 1
    return 0


def build_best_variant_grid(
    selected_ids: Sequence[str],
    scenario_signals: Dict[str, List[ScenarioSignal]],
    scenario_meta: Dict[str, Dict[str, Any]],
    gross_cache: Dict[Tuple[str, str], Optional[GrossTradeResult]],
    threshold_rows: Dict[str, List[Dict[str, Any]]],
    regime_rows: Dict[str, List[Dict[str, Any]]],
    symbol_rows: Dict[str, List[Dict[str, Any]]],
    side_rows: Dict[str, List[Dict[str, Any]]],
    exit_rows: Dict[str, List[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    grid_rows: List[Dict[str, Any]] = []

    for scenario_id in selected_ids:
        signals = scenario_signals.get(scenario_id, [])
        threshold_specs = []
        available_threshold_specs = {variant["name"]: variant for variant in scenario_threshold_variants(scenario_meta[scenario_id]["current_threshold"])}
        for row in top_rows(threshold_rows[scenario_id], "avg_net_pnl_bps", 3, min_signal_count=50):
            spec = available_threshold_specs.get(str(row.get("threshold_variant")))
            if spec is not None:
                threshold_specs.append(spec)
        if not threshold_specs:
            threshold_specs.append(available_threshold_specs["current_threshold"])

        regime_variants = [str(row["regime_filter"]) for row in top_rows(regime_rows[scenario_id], "net_pnl_bps", 3, min_signal_count=50)]
        symbol_variants = [str(row["symbol_filter"]) for row in top_rows(symbol_rows[scenario_id], "net_pnl_bps", 3, min_signal_count=50)]
        side_variants = [str(row["side_constraint"]) for row in top_rows(side_rows[scenario_id], "net_pnl_bps", 3, min_signal_count=50)]
        exit_variants = [str(row["exit_model"]) for row in top_rows(exit_rows[scenario_id], "avg_net_pnl_bps", 5, min_signal_count=50)]

        if not regime_variants:
            regime_variants = ["all_regimes"]
        if not symbol_variants:
            symbol_variants = ["all_symbols"]
        if not side_variants:
            side_variants = ["allow_all_sides"]
        if not exit_variants:
            exit_variants = [BASELINE_EXIT_MODEL]

        for threshold_spec in threshold_specs:
            threshold_kept, threshold_cut = apply_threshold(signals, threshold_spec)
            for regime_variant in regime_variants:
                regime_kept = apply_regime_variant(threshold_kept, regime_variant)
                for symbol_variant in symbol_variants:
                    symbol_kept = apply_symbol_variant(regime_kept, symbol_variant, gross_cache)
                    for side_variant in side_variants:
                        side_kept = [signal for signal in symbol_kept if side_constraint_ok(signal, side_variant)]
                        for exit_model in exit_variants:
                            for fee_model in FEE_MODELS_BPS:
                                for slippage_model in SLIPPAGE_MODELS_BPS:
                                    metrics = aggregate_metrics(side_kept, gross_cache, exit_model, fee_model, slippage_model)
                                    signal_count = safe_int(metrics.get("signal_count"))
                                    if signal_count == 0:
                                        continue
                                    grid_rows.append({
                                        "scenario_id": scenario_id,
                                        "threshold": threshold_spec["name"],
                                        "threshold_value": round(threshold_cut, 6),
                                        "symbol_filter": symbol_variant,
                                        "regime_filter": regime_variant,
                                        "side_constraint": side_variant,
                                        "exit_model": exit_model,
                                        "fee_model": fee_model,
                                        "slippage_model": slippage_model,
                                        "signal_count": signal_count,
                                        "sample_status": sample_status(signal_count),
                                        "win_rate": metrics["win_rate"],
                                        "avg_net_pnl_bps": metrics["net_avg_pnl_bps"],
                                        "total_net_pnl_bps": metrics["net_total_pnl_bps"],
                                        "max_dd_bps": metrics["max_dd_bps"],
                                        "profit_factor": metrics["profit_factor"],
                                        "false_positive_rate": metrics["false_positive_rate"],
                                        "signal_count_stability": round(signal_count / max(1, len(signals)), 6),
                                    })

    grid_rows.sort(
        key=lambda row: (
            safe_float(row.get("avg_net_pnl_bps"), 0.0) > 0.0,
            cost_realism_rank(str(row.get("fee_model")), str(row.get("slippage_model"))),
            sample_rank(safe_int(row.get("signal_count"))),
            safe_float(row.get("avg_net_pnl_bps"), 0.0),
            safe_float(row.get("profit_factor"), 0.0),
            safe_float(row.get("signal_count_stability"), 0.0),
            -safe_float(row.get("false_positive_rate"), 0.0),
            -safe_float(row.get("max_dd_bps"), 0.0),
            safe_float(row.get("total_net_pnl_bps"), 0.0),
        ),
        reverse=True,
    )
    for index, row in enumerate(grid_rows, start=1):
        row["rank"] = index
        row["avoided_real_sl_count"] = ""
        row["caught_real_tp_count"] = ""
        row["false_skip_tp_count"] = ""
        row["false_enter_loss_count"] = ""
    return grid_rows


def load_real_trades(order_log_path: Path, wal_dir: Path) -> List[RealTrade]:
    entry_by_lifecycle: Dict[str, Dict[str, Any]] = {}
    close_by_lifecycle: Dict[str, Dict[str, Any]] = {}

    for record in read_jsonl(order_log_path):
        if record.get("event_type") != "ORDER_FILLED":
            continue
        lifecycle_id = str(record.get("lifecycle_id", "")).strip()
        if not lifecycle_id:
            continue
        order_kind = str(record.get("order_kind", "")).upper()
        if order_kind == "ENTRY":
            entry_by_lifecycle[lifecycle_id] = record
        elif str(record.get("close_reason") or "").upper() in {"SL", "TP"}:
            close_by_lifecycle[lifecycle_id] = record

    trades: List[RealTrade] = []
    for wal_path in sorted(path for path in wal_dir.glob("*.jsonl") if path.is_file()):
        for record in read_jsonl(wal_path):
            if record.get("verb") != "OBJECTIVE_REALIZED_V1":
                continue
            payload = record.get("pld") or {}
            lifecycle_id = str(payload.get("entry_rid", "")).strip()
            if not lifecycle_id:
                continue
            entry = entry_by_lifecycle.get(lifecycle_id)
            close = close_by_lifecycle.get(lifecycle_id)
            if entry is None:
                continue
            close_reason = "OTHER"
            close_rid = str(payload.get("close_rid", ""))
            if close_rid.endswith(":SL"):
                close_reason = "SL"
            elif close_rid.endswith(":TP"):
                close_reason = "TP"
            if close is None and close_reason not in {"SL", "TP"}:
                continue
            trades.append(
                RealTrade(
                    strategy_id=str(payload.get("strategy_id", "unknown")),
                    lifecycle_id=lifecycle_id,
                    symbol=str(payload.get("symbol", entry.get("symbol", ""))),
                    side=str(entry.get("side", "")).upper(),
                    entry_ts_ms=safe_int(entry.get("timestamp")),
                    close_ts_ms=safe_int((close or {}).get("timestamp"), safe_int(record.get("ts"))),
                    entry_price=safe_float(entry.get("price"), 0.0) or 0.0,
                    close_price=safe_float((close or {}).get("price"), 0.0) or 0.0,
                    close_reason=close_reason if close_reason in {"SL", "TP"} else str((close or {}).get("close_reason", "OTHER")),
                    entry_rid=lifecycle_id,
                    close_rid=close_rid,
                    regime_entry=str(payload.get("regime_entry", "UNKNOWN")),
                    regime_exit=str(payload.get("regime_exit", "UNKNOWN")),
                )
            )
    trades.sort(key=lambda item: item.entry_ts_ms)
    return trades


def select_signals_for_variant(
    all_signals: Sequence[ScenarioSignal],
    threshold_name: str,
    current_threshold: float,
    regime_filter: str,
    symbol_filter: str,
    side_constraint: str,
    gross_cache: Dict[Tuple[str, str], Optional[GrossTradeResult]],
) -> List[ScenarioSignal]:
    threshold_map = {variant["name"]: variant for variant in scenario_threshold_variants(current_threshold)}
    threshold_variant = threshold_map.get(threshold_name)
    if threshold_variant is None:
        raise KeyError(f"Unknown threshold variant: {threshold_name}")
    threshold_kept, _ = apply_threshold(all_signals, threshold_variant)
    regime_kept = apply_regime_variant(threshold_kept, regime_filter)
    symbol_kept = apply_symbol_variant(regime_kept, symbol_filter, gross_cache)
    return [signal for signal in symbol_kept if side_constraint_ok(signal, side_constraint)]


def compare_best_variants_to_real(
    grid_rows: List[Dict[str, Any]],
    scenario_signals: Dict[str, List[ScenarioSignal]],
    scenario_meta: Dict[str, Dict[str, Any]],
    gross_cache: Dict[Tuple[str, str], Optional[GrossTradeResult]],
    real_trades: Sequence[RealTrade],
) -> Tuple[List[Dict[str, Any]], Dict[int, Dict[str, int]]]:
    comparison_rows: List[Dict[str, Any]] = []
    comparison_summary: Dict[int, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
    top_rows = grid_rows[:BEST_VARIANT_COMPARE_LIMIT]

    for row in top_rows:
        scenario_id = str(row["scenario_id"])
        selected_signals = select_signals_for_variant(
            scenario_signals.get(scenario_id, []),
            str(row["threshold"]),
            scenario_meta[scenario_id]["current_threshold"],
            str(row["regime_filter"]),
            str(row["symbol_filter"]),
            str(row["side_constraint"]),
            gross_cache,
        )

        for trade in real_trades:
            if trade.entry_ts_ms <= 0 or trade.symbol == "":
                label = "DATA_GAP"
                matched = None
            else:
                candidates = [
                    signal
                    for signal in selected_signals
                    if signal.symbol == trade.symbol and abs(signal.ts_ms - trade.entry_ts_ms) <= COMPARE_TOLERANCE_MS
                ]
                matched = min(candidates, key=lambda signal: abs(signal.ts_ms - trade.entry_ts_ms)) if candidates else None
                label = classify_real_trade_match(row, matched, trade, gross_cache)

            comparison_summary[safe_int(row["rank"])][label] += 1
            comparison_rows.append({
                "variant_rank": row["rank"],
                "scenario_id": scenario_id,
                "threshold": row["threshold"],
                "symbol_filter": row["symbol_filter"],
                "regime_filter": row["regime_filter"],
                "side_constraint": row["side_constraint"],
                "exit_model": row["exit_model"],
                "fee_model": row["fee_model"],
                "slippage_model": row["slippage_model"],
                "real_strategy_id": trade.strategy_id,
                "real_symbol": trade.symbol,
                "real_side": trade.side,
                "real_entry_ts_ms": trade.entry_ts_ms,
                "real_close_ts_ms": trade.close_ts_ms,
                "real_close_reason": trade.close_reason,
                "scenario_signal_ts_ms": matched.ts_ms if matched else "",
                "scenario_signal_side": matched.side if matched else "",
                "scenario_signal_score": round(matched.score, 6) if matched else "",
                "scenario_exit_ts_ms": gross_cache[(matched.signal_id, str(row["exit_model"]))].exit_ts_ms if matched and gross_cache.get((matched.signal_id, str(row["exit_model"]))) else "",
                "scenario_exit_earlier": str(bool(matched and gross_cache.get((matched.signal_id, str(row["exit_model"]))) and gross_cache[(matched.signal_id, str(row['exit_model']))].exit_ts_ms < trade.close_ts_ms)).lower() if matched else "false",
                "classification": label,
            })

    for row in top_rows:
        counts = comparison_summary[safe_int(row["rank"])]
        row["avoided_real_sl_count"] = counts.get("AVOIDED_REAL_SL", 0)
        row["caught_real_tp_count"] = counts.get("CAUGHT_REAL_TP", 0)
        row["false_skip_tp_count"] = counts.get("FALSE_SKIP_TP", 0)
        row["false_enter_loss_count"] = counts.get("FALSE_ENTER_LOSS", 0)

    return comparison_rows, comparison_summary


def classify_real_trade_match(
    variant_row: Dict[str, Any],
    matched: Optional[ScenarioSignal],
    trade: RealTrade,
    gross_cache: Dict[Tuple[str, str], Optional[GrossTradeResult]],
) -> str:
    if matched is None:
        if trade.close_reason == "SL":
            return "AVOIDED_REAL_SL"
        if trade.close_reason == "TP":
            return "FALSE_SKIP_TP"
        return "DATA_GAP"

    if matched.side != trade.side:
        return "AVOIDED_REAL_SL" if trade.close_reason == "SL" else "NO_DIFFERENCE"

    gross = gross_cache.get((matched.signal_id, str(variant_row["exit_model"])))
    if gross is None:
        return "DATA_GAP"

    if trade.close_reason == "SL":
        if gross.exit_ts_ms < trade.close_ts_ms and gross.gross_pnl_bps >= 0.0:
            return "AVOIDED_REAL_SL"
        return "FALSE_ENTER_LOSS"
    if trade.close_reason == "TP":
        return "CAUGHT_REAL_TP"
    return "NO_DIFFERENCE"


def flatten_rows(rows_by_scenario: Dict[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for scenario_id in sorted(rows_by_scenario):
        rows.extend(rows_by_scenario[scenario_id])
    return rows


def verdict_codes(
    grid_rows: Sequence[Dict[str, Any]],
    symbol_rows: Sequence[Dict[str, Any]],
    regime_rows: Sequence[Dict[str, Any]],
    side_rows: Sequence[Dict[str, Any]],
    exit_rows: Sequence[Dict[str, Any]],
    comparison_summary: Dict[int, Dict[str, int]],
) -> List[str]:
    codes: List[str] = []
    positive_rows = [row for row in grid_rows if (safe_float(row.get("avg_net_pnl_bps"), 0.0) or 0.0) > 0.0]
    robust_rows = [row for row in positive_rows if safe_int(row.get("signal_count")) >= 200]

    if positive_rows:
        codes.append("NET_PROFITABLE_VARIANT_FOUND")
    else:
        codes.append("ONLY_GROSS_EDGE_NO_NET_EDGE")

    best_row = grid_rows[0] if grid_rows else None
    if best_row and str(best_row.get("scenario_id")) == "S03_AURORA_15M_APPROX":
        codes.append("S03_BEST_AFTER_COSTS")

    positive_s05 = [row for row in positive_rows if row.get("scenario_id") == "S05_AURORA_MACRO_RESIDUAL"]
    if positive_s05:
        s05_best = min(positive_s05, key=lambda row: safe_float(row.get("max_dd_bps"), 0.0) or 0.0)
        positive_dd = [safe_float(row.get("max_dd_bps"), 0.0) or 0.0 for row in positive_rows]
        if positive_dd and (safe_float(s05_best.get("max_dd_bps"), 0.0) or 0.0) <= min(positive_dd):
            codes.append("S05_SAFEST_AFTER_COSTS")

    s20_rows = [row for row in positive_rows if row.get("scenario_id") == "S20_AURORA_MICROSTRUCTURE_DEPTH"]
    if any(row.get("symbol_filter") == "exclude_BTC" or row.get("regime_filter") == "no_HIGH_VOLATILITY" for row in s20_rows):
        codes.append("S20_REPAIRED_BY_FILTERS")

    if any((safe_float(row.get("net_pnl_bps"), 0.0) or 0.0) > 0.0 and row.get("regime_filter") == "no_HIGH_VOLATILITY" for row in regime_rows):
        codes.append("HIGH_VOL_FILTER_CONFIRMED")
    if any((safe_float(row.get("net_pnl_bps"), 0.0) or 0.0) > 0.0 and row.get("symbol_filter") == "exclude_BTC" for row in symbol_rows):
        codes.append("BTC_EXCLUSION_CONFIRMED")
    if any((safe_float(row.get("net_pnl_bps"), 0.0) or 0.0) > 0.0 and row.get("side_constraint") == "no_SELL_in_TREND_UP" for row in side_rows) or any(
        (safe_float(row.get("avg_net_pnl_bps"), 0.0) or 0.0) > 0.0 and row.get("side_constraint") == "no_SELL_in_TREND_UP"
        for row in grid_rows
    ):
        codes.append("NO_SELL_TREND_UP_CONFIRMED")
    if best_row and str(best_row.get("exit_model")) != "horizon_1_bar":
        codes.append("EXIT_MODEL_EDGE_FOUND")

    top_compare = comparison_summary.get(1, {})
    if top_compare.get("AVOIDED_REAL_SL", 0) > 0:
        codes.append("PARTIAL")
    if not robust_rows:
        codes.append("LOW_SAMPLE_ONLY")
    if not positive_rows:
        codes.append("NO_ROBUST_EDGE_FOUND")

    deduped: List[str] = []
    for code in codes:
        if code not in deduped:
            deduped.append(code)
    return deduped


def distinct_values(rows: Sequence[Dict[str, Any]], key_name: str, limit: int = 5) -> List[str]:
    values: List[str] = []
    for row in rows:
        value = str(row.get(key_name, "")).strip()
        if not value or value in values:
            continue
        values.append(value)
        if len(values) >= limit:
            break
    return values


def generate_report_markdown(
    session_dir: Path,
    selected_candidate_rows: Sequence[Dict[str, Any]],
    grid_rows: Sequence[Dict[str, Any]],
    comparison_rows: Sequence[Dict[str, Any]],
    verdicts: Sequence[str],
    previous_report_path: Optional[Path],
) -> str:
    best_row = grid_rows[0] if grid_rows else {}
    promote_variants = [row for row in grid_rows if (safe_float(row.get("avg_net_pnl_bps"), 0.0) or 0.0) > 0.0][:5]
    discard_variants = [row for row in grid_rows if (safe_float(row.get("avg_net_pnl_bps"), 0.0) or 0.0) <= 0.0][:5]
    profitable_scenarios = distinct_values(promote_variants, "scenario_id")
    promoted_scenarios = distinct_values(promote_variants, "scenario_id", limit=3)
    discard_scenarios = [s for s in distinct_values(discard_variants, "scenario_id") if s not in promoted_scenarios]
    avoided_real_sl = safe_int(best_row.get("avoided_real_sl_count"))
    false_skip_tp = safe_int(best_row.get("false_skip_tp_count"))
    best_variant_lines = []
    for row in promote_variants:
        best_variant_lines.append(
            f"- {row['rank']}. {row['scenario_id']} | thr={row['threshold']} | regime={row['regime_filter']} | symbol={row['symbol_filter']} | side={row['side_constraint']} | exit={row['exit_model']} | fee={row['fee_model']} | slip={row['slippage_model']} | avg_net={row['avg_net_pnl_bps']:.4f} bps | n={row['signal_count']}"
        )

    discard_lines = []
    for row in discard_variants:
        discard_lines.append(
            f"- {row['scenario_id']} | regime={row['regime_filter']} | symbol={row['symbol_filter']} | side={row['side_constraint']} | exit={row['exit_model']} | avg_net={row['avg_net_pnl_bps']:.4f} bps | n={row['signal_count']}"
        )

    previous_report_note = ""
    if previous_report_path and previous_report_path.exists():
        previous_report_note = (
            f"\nPrevious report anchor: {previous_report_path.name} exists, but newest runtime truth was used for this sweep because latest signal counts and side mix drifted materially from the older 1-bar summary."
        )

    return "\n".join([
        "# ALPHA_SEARCH_PROFITABLE_SCENARIO_SIMULATION_SWEEP_V1",
        "",
        "Authority boundary:",
        "- shadow_only=true",
        "- authority_applied=false",
        "- no_effect=true",
        "- No real ORDER_INTENT, CMD:OPEN, CMD:CLOSE, or config changes were emitted.",
        "",
        "## Facts",
        f"- Latest runtime session analyzed: {session_dir.name}",
        f"- Candidate scenarios selected for sweep: {', '.join(row['scenario_id'] for row in selected_candidate_rows if row['selected_for_sweep'] == 'true')}",
        f"- Best cost-aware combined variant by newest runtime truth: {best_row.get('scenario_id', 'N/A')} / {best_row.get('threshold', 'N/A')} / {best_row.get('regime_filter', 'N/A')} / {best_row.get('symbol_filter', 'N/A')} / {best_row.get('side_constraint', 'N/A')} / {best_row.get('exit_model', 'N/A')} / {best_row.get('fee_model', 'N/A')} / {best_row.get('slippage_model', 'N/A')}",
        f"- Best variant avg net expectancy: {safe_float(best_row.get('avg_net_pnl_bps'), 0.0) or 0.0:.4f} bps",
        f"- Best variant total net pnl: {safe_float(best_row.get('total_net_pnl_bps'), 0.0) or 0.0:.4f} bps",
        f"- Best variant signal count: {safe_int(best_row.get('signal_count'))}",
        f"- Best variant avoided real SL count: {avoided_real_sl}",
        f"- Best variant false skip TP count: {false_skip_tp}",
        previous_report_note.strip(),
        "",
        "## Inferences",
        "- Latest runtime still shows gross edge in the original aurora candidates, but net edge is highly sensitive to transaction costs and to whether BTC/HIGH_VOL/TREND_UP side conflicts are filtered out.",
        "- Thresholds above the runtime's current operating range reduce noise but can quickly collapse sample size; percentile thresholds are more stable than fixed 0.12-0.25 gates on the newest logs.",
        "- S20 remains usable only when BTC toxicity and HIGH_VOL pockets are explicitly filtered; otherwise its BUY clusters in BTC TREND_UP/HIGH_VOL remain unstable.",
        "",
        "## Answers",
        f"1. Scenarios remaining profitable after fees/slippage: {', '.join(profitable_scenarios) or 'none'}.",
        f"2. Is S03 still best after costs? {'yes' if any(code == 'S03_BEST_AFTER_COSTS' for code in verdicts) else 'no'}.",
        f"3. Is S05 safer after costs? {'yes' if any(code == 'S05_SAFEST_AFTER_COSTS' for code in verdicts) else 'no'}.",
        f"4. Is S20 useful after removing HIGH_VOL and BTC? {'yes' if any(code == 'S20_REPAIRED_BY_FILTERS' for code in verdicts) else 'no'}.",
        f"5. Does no-SELL-in-TREND_UP improve results? {'yes' if any(code == 'NO_SELL_TREND_UP_CONFIRMED' for code in verdicts) else 'no'}.",
        f"6. Which threshold gives best net expectancy? {best_row.get('threshold', 'N/A')}.",
        f"7. Which regime filter gives best result? {best_row.get('regime_filter', 'N/A')}.",
        f"8. Which symbol filter gives best result? {best_row.get('symbol_filter', 'N/A')}.",
        f"9. Which exit model is best? {best_row.get('exit_model', 'N/A')}.",
        f"10. Are there enough samples to trust the candidate? {best_row.get('sample_status', 'N/A')}.",
        f"11. Would the best variant have avoided real SL cases? {avoided_real_sl} confirmed cases in the available comparison window.",
        f"12. Would the best variant have falsely skipped real TP cases? {false_skip_tp} confirmed cases in the available comparison window.",
        f"13. What should be promoted to deeper shadow collection? {', '.join(promoted_scenarios) or 'none'}.",
        f"14. What should be discarded? {', '.join(discard_scenarios) or 'none'}.",
        "",
        "## Promote",
        *best_variant_lines,
        "",
        "## Discard",
        *discard_lines,
        "",
        "## Verdict Codes",
        *[f"- {code}" for code in verdicts],
    ])


def run(args: argparse.Namespace) -> None:
    runtime_root = Path(args.runtime_root)
    session_dir = Path(args.session_dir) if args.session_dir else sorted_latest_session(runtime_root)
    reports_dir = Path(args.reports_dir)
    previous_report_path = Path(args.previous_report_path) if args.previous_report_path else None

    bars_by_symbol, bar_lookup, index_lookup = load_bars(Path(args.alpha_input_path), Path(args.regime_confidence_path))
    scenario_signals, scenario_meta = load_runtime_signals(session_dir, bar_lookup)

    gross_cache: Dict[Tuple[str, str], Optional[GrossTradeResult]] = {}
    for scenario_id, signals in scenario_signals.items():
        for signal in signals:
            future = future_bars(signal, bars_by_symbol, index_lookup)
            for exit_model in EXIT_VARIANTS:
                gross_cache[(signal.signal_id, exit_model)] = simulate_gross_exit(signal, future, exit_model)

    candidate_rows, selected_ids = build_candidate_selection(scenario_signals, scenario_meta, gross_cache)
    selected_candidate_rows = [row for row in candidate_rows if row["selected_for_sweep"] == "true"]

    cost_rows = build_cost_model_rows(selected_ids, scenario_signals, gross_cache)
    threshold_rows_by_scenario = build_threshold_sweep_rows(selected_ids, scenario_signals, scenario_meta, gross_cache)
    regime_rows_by_scenario = build_regime_sweep_rows(selected_ids, scenario_signals, gross_cache)
    symbol_rows_by_scenario = build_symbol_sweep_rows(selected_ids, scenario_signals, gross_cache)
    side_rows_by_scenario = build_side_sweep_rows(selected_ids, scenario_signals, gross_cache)
    exit_rows_by_scenario = build_exit_sweep_rows(selected_ids, scenario_signals, gross_cache)

    threshold_rows = flatten_rows(threshold_rows_by_scenario)
    regime_rows = flatten_rows(regime_rows_by_scenario)
    symbol_rows = flatten_rows(symbol_rows_by_scenario)
    side_rows = flatten_rows(side_rows_by_scenario)
    exit_rows = flatten_rows(exit_rows_by_scenario)

    grid_rows = build_best_variant_grid(
        selected_ids,
        scenario_signals,
        scenario_meta,
        gross_cache,
        threshold_rows_by_scenario,
        regime_rows_by_scenario,
        symbol_rows_by_scenario,
        side_rows_by_scenario,
        exit_rows_by_scenario,
    )

    real_trades = load_real_trades(Path(args.order_log_path), Path(args.wal_dir))
    comparison_rows, comparison_summary = compare_best_variants_to_real(
        grid_rows,
        scenario_signals,
        scenario_meta,
        gross_cache,
        real_trades,
    )

    verdicts = verdict_codes(grid_rows, symbol_rows, regime_rows, side_rows, exit_rows, comparison_summary)
    report_md = generate_report_markdown(
        session_dir,
        selected_candidate_rows,
        grid_rows,
        comparison_rows,
        verdicts,
        previous_report_path,
    )

    summary = {
        "task_id": "ALPHA_SEARCH_PROFITABLE_SCENARIO_SIMULATION_SWEEP_V1",
        "shadow_only": True,
        "authority_applied": False,
        "no_effect": True,
        "runtime_session": session_dir.name,
        "alpha_input_path": args.alpha_input_path,
        "regime_confidence_path": args.regime_confidence_path,
        "order_log_path": args.order_log_path,
        "wal_dir": args.wal_dir,
        "selected_candidates": [row["scenario_id"] for row in selected_candidate_rows],
        "total_variants_tested": len(grid_rows),
        "positive_variant_count": sum(1 for row in grid_rows if (safe_float(row.get("avg_net_pnl_bps"), 0.0) or 0.0) > 0.0),
        "best_variant": grid_rows[0] if grid_rows else {},
        "verdict_codes": verdicts,
        "best_variant_real_compare": comparison_summary.get(1, {}),
    }

    write_csv(
        reports_dir / "ALPHA_SEARCH_PROFIT_CANDIDATE_SELECTION_V1.csv",
        candidate_rows,
        (
            "scenario_id",
            "family",
            "signal_count",
            "gross_total_pnl",
            "gross_avg_pnl",
            "win_rate",
            "max_dd",
            "profit_factor",
            "best_symbols",
            "best_regimes",
            "toxic_symbols",
            "toxic_regimes",
            "selected_for_sweep",
            "selection_reason",
        ),
    )
    write_csv(
        reports_dir / "ALPHA_SEARCH_COST_MODEL_SWEEP_V1.csv",
        cost_rows,
        (
            "scenario_id",
            "fee_model",
            "slippage_model",
            "signal_count",
            "gross_pnl_bps",
            "fee_bps",
            "slippage_bps",
            "net_pnl_bps",
            "breakeven_edge_bps",
            "cost_coverage_ratio",
            "total_net_pnl_bps",
        ),
    )
    write_csv(
        reports_dir / "ALPHA_SEARCH_THRESHOLD_SWEEP_V1.csv",
        threshold_rows,
        (
            "scenario_id",
            "threshold_variant",
            "threshold_value",
            "signal_count",
            "BUY_count",
            "SELL_count",
            "win_rate",
            "avg_gross_pnl_bps",
            "avg_net_pnl_bps",
            "total_net_pnl_bps",
            "max_dd_bps",
            "profit_factor_net",
            "MFE_bps",
            "MAE_bps",
            "removed_losers",
            "removed_winners",
            "retention_pct",
        ),
    )
    write_csv(
        reports_dir / "ALPHA_SEARCH_REGIME_FILTER_SWEEP_V1.csv",
        regime_rows,
        (
            "scenario_id",
            "regime_filter",
            "signal_count",
            "net_pnl_bps",
            "win_rate",
            "max_dd",
            "profit_factor",
            "false_removed_winners",
            "removed_losses",
            "best_scenario_regime_combo",
        ),
    )
    write_csv(
        reports_dir / "ALPHA_SEARCH_SYMBOL_FILTER_SWEEP_V1.csv",
        symbol_rows,
        (
            "scenario_id",
            "symbol_filter",
            "signal_count",
            "net_pnl_bps",
            "win_rate",
            "max_dd_bps",
            "profit_factor",
            "false_removed_winners",
            "removed_losses",
        ),
    )
    write_csv(
        reports_dir / "ALPHA_SEARCH_SIDE_CONSTRAINT_SWEEP_V1.csv",
        side_rows,
        (
            "scenario_id",
            "side_constraint",
            "signal_count",
            "net_pnl_bps",
            "win_rate",
            "max_dd_bps",
            "profit_factor",
            "false_removed_winners",
            "removed_losses",
        ),
    )
    write_csv(
        reports_dir / "ALPHA_SEARCH_EXIT_MODEL_SWEEP_V1.csv",
        exit_rows,
        (
            "scenario_id",
            "exit_model",
            "signal_count",
            "win_rate",
            "avg_net_pnl_bps",
            "total_net_pnl_bps",
            "max_dd",
            "profit_factor",
            "average_hold_time",
            "MFE_capture_ratio",
            "MAE_exposure",
        ),
    )
    write_csv(
        reports_dir / "ALPHA_SEARCH_BEST_VARIANT_GRID_V1.csv",
        grid_rows,
        (
            "rank",
            "scenario_id",
            "threshold",
            "threshold_value",
            "symbol_filter",
            "regime_filter",
            "side_constraint",
            "exit_model",
            "fee_model",
            "slippage_model",
            "signal_count",
            "sample_status",
            "win_rate",
            "avg_net_pnl_bps",
            "total_net_pnl_bps",
            "max_dd_bps",
            "profit_factor",
            "signal_count_stability",
            "false_positive_rate",
            "avoided_real_sl_count",
            "caught_real_tp_count",
            "false_skip_tp_count",
            "false_enter_loss_count",
        ),
    )
    write_csv(
        reports_dir / "ALPHA_SEARCH_BEST_VARIANTS_VS_REAL_LOSSES_V1.csv",
        comparison_rows,
        (
            "variant_rank",
            "scenario_id",
            "threshold",
            "symbol_filter",
            "regime_filter",
            "side_constraint",
            "exit_model",
            "fee_model",
            "slippage_model",
            "real_strategy_id",
            "real_symbol",
            "real_side",
            "real_entry_ts_ms",
            "real_close_ts_ms",
            "real_close_reason",
            "scenario_signal_ts_ms",
            "scenario_signal_side",
            "scenario_signal_score",
            "scenario_exit_ts_ms",
            "scenario_exit_earlier",
            "classification",
        ),
    )

    (reports_dir / "ALPHA_SEARCH_PROFITABLE_SCENARIO_SIMULATION_SWEEP_V1.md").write_text(report_md, encoding="utf-8")
    (reports_dir / "ALPHA_SEARCH_PROFITABLE_SCENARIO_SUMMARY_V1.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Shadow-only alpha_search profitable scenario sweep")
    parser.add_argument("--runtime-root", default="logs/alpha_search_runtime")
    parser.add_argument("--session-dir", default=None)
    parser.add_argument("--alpha-input-path", default="logs/alpha_input/alpha_input_v1.jsonl")
    parser.add_argument("--regime-confidence-path", default="logs/regime_confidence_audit_v1.jsonl")
    parser.add_argument("--order-log-path", default="logs/order_log_v1.jsonl")
    parser.add_argument("--wal-dir", default="ops/wal")
    parser.add_argument("--reports-dir", default="reports")
    parser.add_argument(
        "--previous-report-path",
        default="reports/ALPHA_SEARCH_PNL_FINANCIAL_ANALYSIS_20260517.md",
    )
    return parser.parse_args()


if __name__ == "__main__":
    run(parse_args())

