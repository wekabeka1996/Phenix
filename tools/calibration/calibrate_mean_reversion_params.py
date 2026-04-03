#!/usr/bin/env python3
"""Production-aligned candidate calibrator for active mean_reversion parameters.

This script searches mean_reversion strategy and per-asset parameter overlays from recorder bars,
emits overlay artifacts, and never mutates canonical YAML automatically.
"""
from __future__ import annotations
from tools.objective_calibration.extract_recorder import load_recorder_rows
from apps.reference.domains.feature_engineering.mean_reversion_strategy import (
    MRStrategyConfig,
    MeanReversion1mStrategy,
)
from apps.reference.domains.feature_engineering.bar_resampler import Bar

import argparse
import json
import math
import random
import sys
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


@dataclass(frozen=True)
class SearchCfg:
    horizon_bars: int
    cost_bps_roundtrip: float
    min_trades: int


@dataclass(frozen=True)
class EvalPoint:
    score: float
    metrics: dict[str, Any]
    overlay: dict[str, Any]


def _parse_date(raw: str) -> date:
    return date.fromisoformat(raw)


def _load_mean_reversion_yaml(path: Path) -> dict[str, Any]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not isinstance(raw.get("mean_reversion"), dict):
        raise SystemExit(f"Invalid mean_reversion YAML: {path}")
    return raw["mean_reversion"]


def _extract_symbol_cfg(root: dict[str, Any], symbol: str) -> dict[str, Any]:
    out = dict(root.get("strategy") or {})
    asset_cfg = ((root.get("assets") or {}).get(symbol) or {})
    if isinstance(asset_cfg.get("strategy"), dict):
        out.update(asset_cfg["strategy"])
    return out


def _allowed_regimes(root: dict[str, Any], symbol: str) -> list[str]:
    asset_cfg = ((root.get("assets") or {}).get(symbol) or {})
    regimes = asset_cfg.get("allowed_regimes") or root.get(
        "allowed_regimes") or []
    return [str(regime) for regime in regimes]


def _build_strategy_cfg(*, params: dict[str, Any], allowed_regimes: list[str]) -> MRStrategyConfig:
    return MRStrategyConfig(
        bb_window=int(params["bb_window"]),
        bb_num_std=float(params["bb_num_std"]),
        atr_window=int(params.get("atr_window", 14)),
        rsi_window=int(params.get("rsi_window", 14)),
        min_bars=int(params.get("min_bars", 25)),
        min_bb_width=Decimal(str(params["min_bb_width"])),
        max_bb_width=Decimal(str(params["max_bb_width"])),
        entry_threshold=Decimal(str(params["entry_threshold"])),
        rsi_oversold=Decimal(str(params.get("rsi_oversold", 30))),
        rsi_overbought=Decimal(str(params.get("rsi_overbought", 70))),
        sl_atr_mult=Decimal(str(params["sl_atr_mult"])),
        tp_to_mid=bool(params.get("tp_to_mid", True)),
        cooldown_sec=int(params["cooldown_sec"]),
        allowed_regimes=list(allowed_regimes),
        confidence_base=Decimal(str(params.get("confidence_base", 0.5))),
        confidence_bb_slope=Decimal(
            str(params.get("confidence_bb_slope", 2.0))),
        confidence_rsi_bonus=Decimal(
            str(params.get("confidence_rsi_bonus", 0.2))),
    )


def _build_bar(row: pd.Series, tf_sec: int) -> Bar:
    ts_ms = int(row["timestamp"])
    return Bar(
        symbol=str(row["symbol"]).upper(),
        timeframe_sec=int(tf_sec),
        open=Decimal(str(row["open"])),
        high=Decimal(str(row["high"])),
        low=Decimal(str(row["low"])),
        close=Decimal(str(row["close"])),
        volume=Decimal(str(row.get("volume", 0.0) or 0.0)),
        trade_count=int(row.get("trade_count", 0) or 0),
        start_ts_ms=int(ts_ms - int(tf_sec) * 1000 + 1),
        end_ts_ms=int(ts_ms),
    )


def _signal_return_bps(
    *,
    signal_side: str,
    entry_price: Decimal,
    stop_price: Decimal | None,
    target_price: Decimal | None,
    future_bars: pd.DataFrame,
    cfg: SearchCfg,
) -> float:
    exit_price = Decimal(str(future_bars.iloc[min(
        len(future_bars) - 1, max(0, cfg.horizon_bars - 1))]["close"]))
    for _, row in future_bars.head(max(1, int(cfg.horizon_bars))).iterrows():
        high = Decimal(str(row["high"]))
        low = Decimal(str(row["low"]))
        if signal_side == "BUY":
            if stop_price is not None and low <= stop_price:
                exit_price = stop_price
                break
            if target_price is not None and high >= target_price:
                exit_price = target_price
                break
        else:
            if stop_price is not None and high >= stop_price:
                exit_price = stop_price
                break
            if target_price is not None and low <= target_price:
                exit_price = target_price
                break
    if entry_price <= 0:
        return 0.0
    if signal_side == "BUY":
        gross = float(((exit_price - entry_price) /
                      entry_price) * Decimal("10000"))
    else:
        gross = float(((entry_price - exit_price) /
                      entry_price) * Decimal("10000"))
    return gross - float(cfg.cost_bps_roundtrip)


def _max_drawdown(values: list[float]) -> float:
    if not values:
        return 0.0
    cumulative = 0.0
    running_max = 0.0
    worst = 0.0
    for value in values:
        cumulative += float(value)
        running_max = max(running_max, cumulative)
        worst = min(worst, cumulative - running_max)
    return abs(worst)


def _evaluate_symbol(*, df_symbol: pd.DataFrame, params: dict[str, Any], cfg: SearchCfg) -> dict[str, Any]:
    strategy = MeanReversion1mStrategy(
        config=_build_strategy_cfg(
            params=params, allowed_regimes=params["allowed_regimes"]),
        timeframe_sec=int(params["timeframe_sec"]),
    )
    trades: list[float] = []
    signals = 0
    ordered = df_symbol.sort_values(
        "timestamp", kind="mergesort").reset_index(drop=True)
    for idx, row in ordered.iterrows():
        strategy.set_regime(str(row["symbol"]).upper(),
                            str(row.get("regime") or ""))
        bar = _build_bar(row, int(params["timeframe_sec"]))
        signal = strategy.on_bar(str(bar.symbol), bar, int(bar.end_ts_ms))
        if signal is None or not signal.is_signal:
            continue
        signals += 1
        future = ordered.iloc[idx + 1:]
        if future.empty:
            continue
        trades.append(
            _signal_return_bps(
                signal_side=str(signal.side),
                entry_price=Decimal(str(signal.entry_price or signal.price)),
                stop_price=Decimal(str(signal.stop_price)
                                   ) if signal.stop_price is not None else None,
                target_price=Decimal(
                    str(signal.target_price)) if signal.target_price is not None else None,
                future_bars=future,
                cfg=cfg,
            )
        )
    total = float(sum(trades))
    trade_count = len(trades)
    avg = total / trade_count if trade_count else 0.0
    wins = sum(1 for trade in trades if trade > 0.0)
    win_rate = float(wins / trade_count) if trade_count else 0.0
    max_dd = _max_drawdown(trades)
    score = total - max_dd + \
        (win_rate * 100.0) if trade_count >= int(cfg.min_trades) else 0.0
    return {
        "score": score,
        "signal_count": signals,
        "trade_count": trade_count,
        "net_pnl_bps": total,
        "avg_pnl_bps": avg,
        "win_rate": win_rate,
        "max_drawdown_bps": max_dd,
    }


def _evaluate_dataset(*, df: pd.DataFrame, root_cfg: dict[str, Any], candidate: dict[str, Any], cfg: SearchCfg) -> dict[str, Any]:
    symbol_metrics: dict[str, dict[str, Any]] = {}
    aggregate = {
        "score": 0.0,
        "signal_count": 0,
        "trade_count": 0,
        "net_pnl_bps": 0.0,
        "avg_pnl_bps": 0.0,
        "win_rate": 0.0,
        "max_drawdown_bps": 0.0,
    }
    per_symbol_win_rates: list[float] = []
    for symbol, df_symbol in df.groupby("symbol", sort=False):
        params = _extract_symbol_cfg(root_cfg, str(symbol))
        params.update(candidate)
        params["allowed_regimes"] = _allowed_regimes(root_cfg, str(symbol))
        params["timeframe_sec"] = int(root_cfg.get("timeframe_sec", 300))
        metrics = _evaluate_symbol(df_symbol=df_symbol, params=params, cfg=cfg)
        symbol_metrics[str(symbol)] = metrics
        aggregate["score"] += float(metrics["score"])
        aggregate["signal_count"] += int(metrics["signal_count"])
        aggregate["trade_count"] += int(metrics["trade_count"])
        aggregate["net_pnl_bps"] += float(metrics["net_pnl_bps"])
        aggregate["max_drawdown_bps"] += float(metrics["max_drawdown_bps"])
        if int(metrics["trade_count"]) > 0:
            per_symbol_win_rates.append(float(metrics["win_rate"]))
    aggregate["avg_pnl_bps"] = aggregate["net_pnl_bps"] / \
        aggregate["trade_count"] if aggregate["trade_count"] > 0 else 0.0
    aggregate["win_rate"] = float(sum(
        per_symbol_win_rates) / len(per_symbol_win_rates)) if per_symbol_win_rates else 0.0
    aggregate["per_symbol"] = symbol_metrics
    return aggregate


def _mutate_candidate(base: dict[str, Any], rng: random.Random) -> dict[str, Any]:
    return {
        "bb_window": int(min(60, max(10, round(float(base["bb_window"]) * rng.uniform(0.75, 1.25))))),
        "bb_num_std": round(min(3.5, max(1.2, float(base["bb_num_std"]) * rng.uniform(0.8, 1.2))), 4),
        "entry_threshold": round(min(0.40, max(0.01, float(base["entry_threshold"]) * rng.uniform(0.7, 1.3))), 6),
        "sl_atr_mult": round(min(4.0, max(0.5, float(base["sl_atr_mult"]) * rng.uniform(0.75, 1.25))), 4),
        "cooldown_sec": int(min(3600, max(0, round(float(base["cooldown_sec"]) * rng.uniform(0.5, 1.5))))),
        "min_bb_width": round(min(0.05, max(0.0001, float(base["min_bb_width"]) * rng.uniform(0.7, 1.3))), 6),
        "max_bb_width": round(min(0.30, max(0.01, float(base["max_bb_width"]) * rng.uniform(0.7, 1.3))), 6),
    }


def _split_train_test(df: pd.DataFrame, frac: float) -> tuple[pd.DataFrame, pd.DataFrame]:
    ordered = df.sort_values(["timestamp", "symbol"],
                             kind="mergesort").reset_index(drop=True)
    split_idx = max(1, int(len(ordered) * frac))
    split_idx = min(split_idx, len(ordered))
    return ordered.iloc[:split_idx].copy(), ordered.iloc[split_idx:].copy()


def _overlay_from_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        "mean_reversion": {
            "strategy": {
                "bb_window": int(candidate["bb_window"]),
                "bb_num_std": float(candidate["bb_num_std"]),
                "entry_threshold": float(candidate["entry_threshold"]),
                "sl_atr_mult": float(candidate["sl_atr_mult"]),
                "cooldown_sec": int(candidate["cooldown_sec"]),
                "min_bb_width": float(candidate["min_bb_width"]),
                "max_bb_width": float(candidate["max_bb_width"]),
            }
        }
    }


def _write_outputs(
    *,
    out_dir: Path,
    args: argparse.Namespace,
    baseline_train: dict[str, Any],
    best_train: dict[str, Any],
    baseline_test: dict[str, Any],
    best_test: dict[str, Any],
    best_overlay: dict[str, Any],
    candidates: list[EvalPoint],
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    report = f"""# Mean Reversion Parameter Calibration Report

## Context
- Symbols: {args.symbols}
- Start: {args.start}
- End: {args.end}
- TF: {args.tf_sec}
- Train fraction: {args.train_frac}
- Horizon bars: {args.horizon_bars}
- Trials: {args.trials}
- Seed: {args.seed}

## Baseline Train
- Score: {baseline_train['score']}
- Trades: {baseline_train['trade_count']}
- Net pnl bps: {baseline_train['net_pnl_bps']}
- Avg pnl bps: {baseline_train['avg_pnl_bps']}
- Win rate: {baseline_train['win_rate']}
- Max drawdown bps: {baseline_train['max_drawdown_bps']}

## Best Train
- Score: {best_train['score']}
- Trades: {best_train['trade_count']}
- Net pnl bps: {best_train['net_pnl_bps']}
- Avg pnl bps: {best_train['avg_pnl_bps']}
- Win rate: {best_train['win_rate']}
- Max drawdown bps: {best_train['max_drawdown_bps']}

## Baseline Test
- Score: {baseline_test['score']}
- Trades: {baseline_test['trade_count']}
- Net pnl bps: {baseline_test['net_pnl_bps']}
- Avg pnl bps: {baseline_test['avg_pnl_bps']}
- Win rate: {baseline_test['win_rate']}
- Max drawdown bps: {baseline_test['max_drawdown_bps']}

## Best Test
- Score: {best_test['score']}
- Trades: {best_test['trade_count']}
- Net pnl bps: {best_test['net_pnl_bps']}
- Avg pnl bps: {best_test['avg_pnl_bps']}
- Win rate: {best_test['win_rate']}
- Max drawdown bps: {best_test['max_drawdown_bps']}

## Rollout Reminder
- Calibration class: production-aligned candidate for active mean_reversion parameters.
- This report writes overlays only.
- It does not mutate canonical YAML automatically.
- Scope caveat: recorder-bar proxy metrics do not prove execution-routing or fill-quality behavior.
"""
    (out_dir / "report.md").write_text(report, encoding="utf-8")
    (out_dir / "candidate_mean_reversion_overlay.yaml").write_text(
        yaml.safe_dump(best_overlay, sort_keys=False, allow_unicode=False),
        encoding="utf-8",
    )
    (out_dir / "best_trial.json").write_text(
        json.dumps(
            {
                "overlay": best_overlay,
                "metrics_train": best_train,
                "metrics_test": best_test,
                "seed": args.seed,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (out_dir / "candidate_bundle.json").write_text(
        json.dumps(
            {
                "candidates": [
                    {"score": point.score, "metrics": point.metrics,
                        "overlay": point.overlay}
                    for point in candidates
                ]
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Production-aligned candidate calibrator for active mean_reversion strategy parameters. "
            "Emits overlay artifacts only and never mutates canonical YAML automatically."
        )
    )
    parser.add_argument(
        "--mr-yaml", default="config/aurora/strategies/mean_reversion.yaml")
    parser.add_argument("--recorder-dir", default="data/recorder")
    parser.add_argument("--symbols", nargs="+", required=True)
    parser.add_argument("--start", type=_parse_date, required=True)
    parser.add_argument("--end", type=_parse_date, required=True)
    parser.add_argument("--tf-sec", type=int, default=300)
    parser.add_argument("--train-frac", type=float, default=0.6)
    parser.add_argument("--horizon-bars", type=int, default=6)
    parser.add_argument("--cost-bps-roundtrip", type=float, default=6.0)
    parser.add_argument("--trials", type=int, default=120)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--min-trades", type=int, default=4)
    parser.add_argument("--out-dir", type=str, default=None)
    args = parser.parse_args(argv)

    root_cfg = _load_mean_reversion_yaml(Path(args.mr_yaml))
    df = load_recorder_rows(
        Path(args.recorder_dir),
        start=args.start,
        end=args.end,
        symbols=[str(symbol).upper() for symbol in args.symbols],
        tf_sec=int(args.tf_sec),
    )
    if df.empty:
        raise SystemExit(
            "No recorder rows found for requested symbols/date range")
    required_cols = {"symbol", "timestamp",
                     "open", "high", "low", "close", "regime"}
    missing = sorted(required_cols.difference(df.columns))
    if missing:
        raise SystemExit(
            f"Recorder dataset missing required columns: {missing}")

    df = df.sort_values(["timestamp", "symbol"],
                        kind="mergesort").reset_index(drop=True)
    train_df, test_df = _split_train_test(df, float(args.train_frac))
    search_cfg = SearchCfg(
        horizon_bars=int(args.horizon_bars),
        cost_bps_roundtrip=float(args.cost_bps_roundtrip),
        min_trades=int(args.min_trades),
    )

    base_strategy = _extract_symbol_cfg(root_cfg, str(args.symbols[0]).upper())
    baseline_candidate = {
        "bb_window": int(base_strategy["bb_window"]),
        "bb_num_std": float(base_strategy["bb_num_std"]),
        "entry_threshold": float(base_strategy["entry_threshold"]),
        "sl_atr_mult": float(base_strategy["sl_atr_mult"]),
        "cooldown_sec": int(base_strategy["cooldown_sec"]),
        "min_bb_width": float(base_strategy["min_bb_width"]),
        "max_bb_width": float(base_strategy["max_bb_width"]),
    }

    baseline_train = _evaluate_dataset(
        df=train_df, root_cfg=root_cfg, candidate=baseline_candidate, cfg=search_cfg)
    best = EvalPoint(score=float(
        baseline_train["score"]), metrics=baseline_train, overlay=_overlay_from_candidate(baseline_candidate))
    candidates = [best]
    rng = random.Random(int(args.seed))
    for _ in range(max(1, int(args.trials))):
        candidate = _mutate_candidate(baseline_candidate, rng)
        metrics = _evaluate_dataset(
            df=train_df, root_cfg=root_cfg, candidate=candidate, cfg=search_cfg)
        point = EvalPoint(score=float(
            metrics["score"]), metrics=metrics, overlay=_overlay_from_candidate(candidate))
        candidates.append(point)
        if point.score > best.score:
            best = point

    baseline_test = _evaluate_dataset(df=test_df, root_cfg=root_cfg, candidate=baseline_candidate,
                                      cfg=search_cfg) if not test_df.empty else baseline_train
    best_candidate_payload = next(iter(best.overlay.values()))
    best_params = dict(best_candidate_payload.get("strategy") or {})
    best_test = _evaluate_dataset(df=test_df, root_cfg=root_cfg, candidate=best_params,
                                  cfg=search_cfg) if not test_df.empty else best.metrics

    candidates = sorted(candidates, key=lambda item: item.score, reverse=True)[
        : max(1, int(args.top_k))]
    out_dir = Path(args.out_dir) if args.out_dir else Path(
        f"reports/strategy_calibration/{datetime.now().strftime('%Y%m%d_%H%M%S')}_mean_reversion_{'_'.join(str(symbol).upper() for symbol in args.symbols)}")
    _write_outputs(
        out_dir=out_dir,
        args=args,
        baseline_train=baseline_train,
        best_train=best.metrics,
        baseline_test=baseline_test,
        best_test=best_test,
        best_overlay=best.overlay,
        candidates=candidates,
    )
    print(f"Mean reversion calibration complete. Report saved to {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
