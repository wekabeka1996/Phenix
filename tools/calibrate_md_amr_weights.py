#!/usr/bin/env python3
"""
Calibrate MD-AMR directional weights from recorder data.

This script mirrors the workflow style of `calibrate_aurora_signal_weights.py`:
1) load recorder 900s data,
2) build MD-AMR features,
3) split train/test chronologically,
4) search recommended weights (w_d1/w_h1/w_m30/w_m15),
5) print diagnostics and YAML snippet for `config/aurora/strategies/md_amr.yaml`.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import json
import math
from pathlib import Path
from typing import Any, Dict, Iterable
from urllib.parse import urlencode
from urllib.request import urlopen

import numpy as np
import pandas as pd
import yaml

try:
    from tools.md_amr_data_adapter import load_recorder_900, compute_md_amr_features
    from tools.md_amr_vector_backtest import run_vector_backtest, BacktestResult
except ModuleNotFoundError:  # pragma: no cover
    from md_amr_data_adapter import load_recorder_900, compute_md_amr_features
    from md_amr_vector_backtest import run_vector_backtest, BacktestResult


@dataclass(frozen=True)
class SearchCfg:
    min_trades: int
    max_dd_limit: float
    warmup_bars: int


@dataclass(frozen=True)
class EvalPoint:
    score: float
    result: BacktestResult
    weights: Dict[str, float]


def _parse_date(s: str) -> date:
    return date.fromisoformat(s)


def _date_to_ms(d: date, *, end_exclusive: bool) -> int:
    dt = datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
    if end_exclusive:
        dt = dt + timedelta(days=1)
    return int(dt.timestamp() * 1000)


def _fetch_binance_futures_klines(
    *,
    symbol: str,
    interval: str,
    interval_ms: int,
    start_close_ms: int,
    end_close_ms: int,
    base_url: str,
    timeout_sec: float,
    pause_sec: float,
) -> pd.DataFrame:
    start_open_ms = max(0, int(start_close_ms) - int(interval_ms))
    end_open_ms = int(end_close_ms)
    limit = 1500
    cursor = start_open_ms
    rows: list[list[Any]] = []

    while cursor <= end_open_ms:
        params = {
            "symbol": str(symbol).upper(),
            "interval": str(interval),
            "limit": int(limit),
            "startTime": int(cursor),
            "endTime": int(end_open_ms),
        }
        url = f"{base_url.rstrip('/')}/fapi/v1/klines?{urlencode(params)}"
        with urlopen(url, timeout=float(timeout_sec)) as resp:  # nosec B310 - intentional Binance public endpoint
            payload = json.loads(resp.read().decode("utf-8"))
        if not isinstance(payload, list) or not payload:
            break
        rows.extend(payload)
        last_open = int(payload[-1][0])
        next_cursor = last_open + int(interval_ms)
        if next_cursor <= cursor:
            break
        cursor = next_cursor
        if len(payload) < limit:
            break
        if pause_sec > 0:
            import time

            time.sleep(float(pause_sec))

    if not rows:
        return pd.DataFrame()

    out = pd.DataFrame(
        {
            "symbol": str(symbol).upper(),
            "timestamp": [int(r[6]) for r in rows],
            "open": [float(r[1]) for r in rows],
            "high": [float(r[2]) for r in rows],
            "low": [float(r[3]) for r in rows],
            "close": [float(r[4]) for r in rows],
            "volume": [float(r[5]) for r in rows],
            "tf_sec": 900,
        }
    )
    out = out[(out["timestamp"] >= int(start_close_ms)) & (out["timestamp"] <= int(end_close_ms))]
    out = out.drop_duplicates(subset=["symbol", "timestamp"], keep="last")
    out = out.sort_values(["symbol", "timestamp"], kind="mergesort").reset_index(drop=True)
    return out


def _canonicalize_ohlcv_900(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["symbol", "timestamp", "open", "high", "low", "close", "volume", "tf_sec"])
    required = {"symbol", "timestamp", "open", "high", "low", "close"}
    missing = sorted(required.difference(df.columns))
    if missing:
        raise SystemExit(f"Dataset missing required OHLC columns: {missing}")
    out = pd.DataFrame()
    out["symbol"] = df["symbol"].astype(str).str.upper()
    for c in ("timestamp", "open", "high", "low", "close"):
        out[c] = pd.to_numeric(df[c], errors="coerce")
    if "volume" in df.columns:
        out["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0.0)
    else:
        out["volume"] = 0.0
    out["tf_sec"] = 900
    out = out[np.isfinite(out["timestamp"])].copy()
    out["timestamp"] = out["timestamp"].astype(np.int64)
    out = out.dropna(subset=["open", "high", "low", "close"])
    out = out.drop_duplicates(subset=["symbol", "timestamp"], keep="last")
    out = out.sort_values(["symbol", "timestamp"], kind="mergesort").reset_index(drop=True)
    return out


def _recompute_segments(df: pd.DataFrame, *, basis_tf_sec: int = 900) -> pd.DataFrame:
    if df.empty:
        out = df.copy()
        out["gap_reset"] = False
        out["segment_id"] = 0
        return out
    out = df.sort_values(["symbol", "timestamp"], kind="mergesort").copy()
    out["_prev_ts"] = out.groupby("symbol")["timestamp"].shift(1)
    out["_gap_ms"] = out["timestamp"] - out["_prev_ts"]
    out["gap_reset"] = out["_gap_ms"] > (int(basis_tf_sec) * 2 * 1000)
    out["segment_id"] = out.groupby("symbol")["gap_reset"].cumsum().astype(int)
    out = out.drop(columns=["_prev_ts", "_gap_ms"])
    return out.reset_index(drop=True)


def _maybe_hydrate_missing_from_binance(
    *,
    local_df: pd.DataFrame,
    symbols: list[str],
    start: date | None,
    end: date | None,
    enable: bool,
    lookback_bars: int,
    base_url: str,
    timeout_sec: float,
    pause_sec: float,
) -> pd.DataFrame:
    canonical_local = _canonicalize_ohlcv_900(local_df)
    if not enable:
        return _recompute_segments(canonical_local, basis_tf_sec=900)

    interval_ms = 900_000
    symbols_u = [str(s).upper() for s in symbols]
    sym_frames: list[pd.DataFrame] = []
    total_added = 0

    start_from_arg = _date_to_ms(start, end_exclusive=False) if start else None
    end_from_arg = (_date_to_ms(end, end_exclusive=True) - 1) if end else None

    for symbol in symbols_u:
        local_sym = canonical_local[canonical_local["symbol"] == symbol].copy()
        if local_sym.empty and start_from_arg is None:
            print(f"[{symbol}] binance backfill skipped: no local rows and --start not provided")
            continue

        local_min = int(local_sym["timestamp"].min()) if not local_sym.empty else None
        local_max = int(local_sym["timestamp"].max()) if not local_sym.empty else None

        fetch_start = start_from_arg if start_from_arg is not None else int(local_min)
        fetch_end = end_from_arg if end_from_arg is not None else int(local_max)
        if local_min is not None:
            fetch_start = min(int(fetch_start), int(local_min) - int(lookback_bars) * interval_ms)
        if local_max is not None:
            fetch_end = max(int(fetch_end), int(local_max))
        if fetch_end < fetch_start:
            print(f"[{symbol}] binance backfill skipped: invalid range start={fetch_start} end={fetch_end}")
            sym_frames.append(local_sym)
            continue

        try:
            remote_sym = _fetch_binance_futures_klines(
                symbol=symbol,
                interval="15m",
                interval_ms=interval_ms,
                start_close_ms=int(fetch_start),
                end_close_ms=int(fetch_end),
                base_url=base_url,
                timeout_sec=timeout_sec,
                pause_sec=pause_sec,
            )
        except Exception as exc:
            print(f"[{symbol}] binance backfill error: {exc}")
            sym_frames.append(local_sym)
            continue

        if local_sym.empty:
            merged = remote_sym
            added = len(remote_sym)
        else:
            local_ts = set(local_sym["timestamp"].astype(np.int64).tolist())
            missing = remote_sym[~remote_sym["timestamp"].astype(np.int64).isin(local_ts)].copy()
            merged = pd.concat([local_sym, missing], ignore_index=True)
            added = len(missing)

        merged = merged.drop_duplicates(subset=["symbol", "timestamp"], keep="last")
        merged = merged.sort_values(["symbol", "timestamp"], kind="mergesort").reset_index(drop=True)
        total_added += int(added)
        print(f"[{symbol}] binance backfill: local={len(local_sym)} added={added} merged={len(merged)}")
        sym_frames.append(merged)

    if not sym_frames:
        raise SystemExit("Binance hydration produced no rows")

    out = pd.concat(sym_frames, ignore_index=True)
    out = out.drop_duplicates(subset=["symbol", "timestamp"], keep="last")
    out = out.sort_values(["symbol", "timestamp"], kind="mergesort").reset_index(drop=True)
    out = _recompute_segments(out, basis_tf_sec=900)
    print(f"Binance hydration total added rows: {total_added}")
    return out


def _load_md_amr_yaml(path: Path) -> Dict[str, Any]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or "md_amr" not in raw or not isinstance(raw["md_amr"], dict):
        raise SystemExit(f"Invalid md_amr strategy YAML (expected top-level 'md_amr'): {path}")
    return raw["md_amr"]


def _extract_base_params(md_amr_cfg: Dict[str, Any]) -> Dict[str, float]:
    required_keys = [
        "hysteresis_mult",
        "threshold_z",
        "volatility_dampening_factor",
        "thr_base",
        "alpha",
        "conf_min",
        "max_hold_bars",
        "fee_bps",
        "slippage_buffer_bps",
        "scaleout_fraction",
    ]
    missing = [k for k in required_keys if k not in md_amr_cfg]
    if missing:
        raise SystemExit(f"md_amr config missing required keys: {missing}")

    return {
        "hysteresis_mult": float(md_amr_cfg["hysteresis_mult"]),
        "threshold_z": float(md_amr_cfg["threshold_z"]),
        "volatility_dampening_factor": float(md_amr_cfg["volatility_dampening_factor"]),
        "thr_base": float(md_amr_cfg["thr_base"]),
        "alpha": float(md_amr_cfg["alpha"]),
        "conf_min": float(md_amr_cfg["conf_min"]),
        "max_hold_bars": int(md_amr_cfg["max_hold_bars"]),
        "fee_bps": float(md_amr_cfg["fee_bps"]),
        "slippage_buffer_bps": float(md_amr_cfg["slippage_buffer_bps"]),
        "scaleout_fraction": float(md_amr_cfg["scaleout_fraction"]),
    }


def _extract_baseline_weights(md_amr_cfg: Dict[str, Any]) -> Dict[str, float]:
    weights = md_amr_cfg.get("weights")
    if not isinstance(weights, dict):
        raise SystemExit("md_amr.weights missing/invalid in strategy profile")
    required = ("d1", "h1", "m30", "m15")
    missing = [k for k in required if k not in weights]
    if missing:
        raise SystemExit(f"md_amr.weights missing keys: {missing}")
    return {k: float(weights[k]) for k in required}


def _normalize_weights(raw: Dict[str, float]) -> Dict[str, float]:
    keys = ("d1", "h1", "m30", "m15")
    vals = np.array([max(0.0, float(raw[k])) for k in keys], dtype=float)
    total = float(np.sum(vals))
    if total <= 1e-12:
        vals = np.array([0.25, 0.25, 0.25, 0.25], dtype=float)
        total = 1.0
    vals = vals / total
    return {k: float(v) for k, v in zip(keys, vals)}


def _build_backtest_params(base: Dict[str, float], weights_norm: Dict[str, float]) -> Dict[str, Any]:
    p = dict(base)
    p["w_d1"] = float(weights_norm["d1"])
    p["w_h1"] = float(weights_norm["h1"])
    p["w_m30"] = float(weights_norm["m30"])
    p["w_m15"] = float(weights_norm["m15"])
    return p


def _objective(result: BacktestResult, cfg: SearchCfg) -> float:
    if result.max_dd > cfg.max_dd_limit or result.total_trades < cfg.min_trades:
        return -999.0
    return float(result.calmar_ratio * math.log(result.total_trades / cfg.min_trades + 1.0))


def _evaluate(
    df_features: pd.DataFrame,
    *,
    params: Dict[str, Any],
    cfg: SearchCfg,
) -> BacktestResult:
    return run_vector_backtest(
        df_features,
        params=params,
        basis_tf_sec=900,
        warmup_bars=cfg.warmup_bars,
    )


def _split_train_test(df: pd.DataFrame, train_frac: float) -> tuple[pd.DataFrame, pd.DataFrame]:
    if not (0.0 < train_frac < 1.0):
        raise SystemExit("--train-frac must be in (0,1)")
    if df.empty:
        return df.copy(), df.copy()

    tmp = df.copy()
    ts = pd.to_numeric(tmp["timestamp"], errors="coerce")
    tmp = tmp[np.isfinite(ts)].copy()
    tmp["day_utc"] = pd.to_datetime(ts.astype(np.int64), unit="ms", utc=True).dt.date.astype(str)

    days = sorted(tmp["day_utc"].unique().tolist())
    if len(days) < 2:
        return tmp, tmp.iloc[0:0].copy()

    split_idx = int(math.floor(len(days) * train_frac))
    split_idx = max(1, min(len(days) - 1, split_idx))
    train_days = set(days[:split_idx])
    test_days = set(days[split_idx:])

    train_df = tmp[tmp["day_utc"].isin(train_days)].copy()
    test_df = tmp[tmp["day_utc"].isin(test_days)].copy()
    return train_df, test_df


def _sample_weights(rng: np.random.Generator) -> Dict[str, float]:
    raw = rng.uniform(0.05, 0.70, size=4)
    return _normalize_weights(
        {
            "d1": float(raw[0]),
            "h1": float(raw[1]),
            "m30": float(raw[2]),
            "m15": float(raw[3]),
        }
    )


def _fmt_weights_yaml(weights: Dict[str, float], *, indent: int = 4) -> str:
    pad = " " * indent
    lines = ["weights:"]
    for k in ("d1", "h1", "m30", "m15"):
        lines.append(f"{pad}{k}: {weights[k]:.6f}")
    return "\n".join(lines)


def _per_symbol_eval(
    df_test: pd.DataFrame,
    *,
    base_params: Dict[str, Any],
    best_params: Dict[str, Any],
    cfg: SearchCfg,
) -> list[str]:
    lines: list[str] = []
    if df_test.empty:
        return lines
    for symbol in sorted(df_test["symbol"].astype(str).unique().tolist()):
        sdf = df_test[df_test["symbol"].astype(str) == symbol].copy()
        if sdf.empty:
            continue
        base_res = _evaluate(sdf, params=base_params, cfg=cfg)
        best_res = _evaluate(sdf, params=best_params, cfg=cfg)
        lines.append(
            f"  {symbol}: "
            f"baseline(calmar={base_res.calmar_ratio:.4f}, dd={base_res.max_dd:.4f}, trades={base_res.total_trades}) "
            f"-> calibrated(calmar={best_res.calmar_ratio:.4f}, dd={best_res.max_dd:.4f}, trades={best_res.total_trades})"
        )
    return lines


def main() -> int:
    ap = argparse.ArgumentParser(description="Calibrate MD-AMR weights from recorder 900s data")
    ap.add_argument("--md-amr-yaml", default="config/aurora/strategies/md_amr.yaml")
    ap.add_argument("--recorder-dir", default="data/recorder")
    ap.add_argument("--symbols", nargs="+", default=["BTCUSDT", "ETHUSDT", "SOLUSDT", "DOGEUSDT", "XRPUSDT"])
    ap.add_argument("--start", type=_parse_date, default=None)
    ap.add_argument("--end", type=_parse_date, default=None)
    ap.add_argument("--train-frac", type=float, default=0.7)
    ap.add_argument("--trials", type=int, default=800, help="Random search trials for weights")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--min-trades", type=int, default=20)
    ap.add_argument("--max-dd-limit", type=float, default=0.35)
    ap.add_argument("--warmup-bars", type=int, default=96)
    ap.add_argument(
        "--hydrate-from-binance",
        action="store_true",
        help="Backfill missing 15m candles from Binance Futures before calibration",
    )
    ap.add_argument("--binance-base-url", default="https://fapi.binance.com")
    ap.add_argument("--binance-timeout-sec", type=float, default=12.0)
    ap.add_argument("--binance-pause-sec", type=float, default=0.03)
    ap.add_argument(
        "--binance-lookback-bars",
        type=int,
        default=96,
        help="Extra bars fetched before first local timestamp per symbol (warmup support)",
    )
    args = ap.parse_args()

    md_amr_cfg = _load_md_amr_yaml(Path(args.md_amr_yaml))
    base = _extract_base_params(md_amr_cfg)
    baseline_weights = _normalize_weights(_extract_baseline_weights(md_amr_cfg))
    search_cfg = SearchCfg(
        min_trades=int(args.min_trades),
        max_dd_limit=float(args.max_dd_limit),
        warmup_bars=int(args.warmup_bars),
    )

    local_df_raw = load_recorder_900(
        Path(args.recorder_dir),
        symbols=[s.upper() for s in args.symbols],
        start=args.start,
        end=args.end,
        basis_tf_sec=900,
    )
    if local_df_raw.empty and not args.hydrate_from_binance:
        raise SystemExit("No recorder rows found for requested symbols/date range")
    df_raw = _maybe_hydrate_missing_from_binance(
        local_df=local_df_raw,
        symbols=[s.upper() for s in args.symbols],
        start=args.start,
        end=args.end,
        enable=bool(args.hydrate_from_binance),
        lookback_bars=max(1, int(args.binance_lookback_bars)),
        base_url=str(args.binance_base_url),
        timeout_sec=float(args.binance_timeout_sec),
        pause_sec=max(0.0, float(args.binance_pause_sec)),
    )
    if df_raw.empty:
        raise SystemExit("No rows after local+binance data assembly")
    df_feat = compute_md_amr_features(df_raw)
    if df_feat.empty:
        raise SystemExit("No rows after feature computation")

    sort_cols = ["symbol", "segment_id", "timestamp"] if "segment_id" in df_feat.columns else ["symbol", "timestamp"]
    df_feat = df_feat.sort_values(sort_cols, kind="mergesort").reset_index(drop=True)
    train_df, test_df = _split_train_test(df_feat, float(args.train_frac))
    if train_df.empty:
        raise SystemExit("Train split is empty after preprocessing")

    rng = np.random.default_rng(int(args.seed))

    baseline_params = _build_backtest_params(base, baseline_weights)
    baseline_train_res = _evaluate(train_df, params=baseline_params, cfg=search_cfg)
    baseline_train_score = _objective(baseline_train_res, search_cfg)

    best = EvalPoint(score=baseline_train_score, result=baseline_train_res, weights=baseline_weights)

    trials = max(1, int(args.trials))
    for _ in range(trials):
        w = _sample_weights(rng)
        params = _build_backtest_params(base, w)
        res = _evaluate(train_df, params=params, cfg=search_cfg)
        score = _objective(res, search_cfg)
        if score > best.score:
            best = EvalPoint(score=score, result=res, weights=w)

    best_params = _build_backtest_params(base, best.weights)
    best_test_res = _evaluate(test_df, params=best_params, cfg=search_cfg) if not test_df.empty else BacktestResult(0.0, 1.0, 0, 0, 0, 0.0)
    baseline_test_res = _evaluate(test_df, params=baseline_params, cfg=search_cfg) if not test_df.empty else BacktestResult(0.0, 1.0, 0, 0, 0, 0.0)
    best_test_score = _objective(best_test_res, search_cfg) if not test_df.empty else float("nan")
    baseline_test_score = _objective(baseline_test_res, search_cfg) if not test_df.empty else float("nan")

    print("=" * 90)
    print(
        f"MD-AMR calibration: rows_train={len(train_df):,} rows_test={len(test_df):,} "
        f"symbols={sorted(set(df_feat['symbol'].astype(str).tolist()))}"
    )
    print(
        f"search_cfg: trials={trials} min_trades={search_cfg.min_trades} "
        f"max_dd_limit={search_cfg.max_dd_limit} warmup_bars={search_cfg.warmup_bars}"
    )
    print("-" * 90)
    print(
        "TRAIN BASELINE: "
        f"score={baseline_train_score:.6f} calmar={baseline_train_res.calmar_ratio:.6f} "
        f"dd={baseline_train_res.max_dd:.6f} trades={baseline_train_res.total_trades} "
        f"net_profit={baseline_train_res.net_profit:.6f}"
    )
    print(
        "TRAIN CALIBR.:  "
        f"score={best.score:.6f} calmar={best.result.calmar_ratio:.6f} "
        f"dd={best.result.max_dd:.6f} trades={best.result.total_trades} "
        f"net_profit={best.result.net_profit:.6f}"
    )
    print("-" * 90)
    if not test_df.empty:
        print(
            "TEST  BASELINE: "
            f"score={baseline_test_score:.6f} calmar={baseline_test_res.calmar_ratio:.6f} "
            f"dd={baseline_test_res.max_dd:.6f} trades={baseline_test_res.total_trades} "
            f"net_profit={baseline_test_res.net_profit:.6f}"
        )
        print(
            "TEST  CALIBR.:  "
            f"score={best_test_score:.6f} calmar={best_test_res.calmar_ratio:.6f} "
            f"dd={best_test_res.max_dd:.6f} trades={best_test_res.total_trades} "
            f"net_profit={best_test_res.net_profit:.6f}"
        )
    else:
        print("TEST split is empty (not enough unique days).")
    print("-" * 90)
    print("Baseline weights (normalized):")
    print(_fmt_weights_yaml(baseline_weights, indent=6))
    print("-" * 90)
    print("Recommended weights for md_amr.weights:")
    print(_fmt_weights_yaml(best.weights, indent=6))
    print("-" * 90)

    per_symbol_lines = _per_symbol_eval(test_df, base_params=baseline_params, best_params=best_params, cfg=search_cfg)
    if per_symbol_lines:
        print("Per-symbol test diagnostics:")
        for line in per_symbol_lines:
            print(line)
        print("-" * 90)

    print("YAML patch snippet (config/aurora/strategies/md_amr.yaml):")
    print("md_amr:")
    for line in _fmt_weights_yaml(best.weights, indent=4).splitlines():
        print(f"  {line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
