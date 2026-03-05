from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Dict

import numpy as np
import pandas as pd

try:
    from tools.md_amr_data_adapter import load_recorder_900, compute_md_amr_features
except ModuleNotFoundError:  # pragma: no cover
    from md_amr_data_adapter import load_recorder_900, compute_md_amr_features


@dataclass(frozen=True)
class BacktestResult:
    net_profit: float
    max_dd: float
    total_trades: int
    partial_closes: int
    skipped_rows: int
    calmar_ratio: float


def _normalize_weights(w_raw: Dict[str, float]) -> Dict[str, float]:
    total = sum(max(0.0, float(v)) for v in w_raw.values())
    if total <= 1e-12:
        return {"d1": 0.25, "h1": 0.25, "m30": 0.25, "m15": 0.25}
    return {k: max(0.0, float(v)) / total for k, v in w_raw.items()}


def run_vector_backtest(
    df: pd.DataFrame,
    *,
    params: Dict[str, Any],
    basis_tf_sec: int = 900,
    warmup_bars: int = 96,
) -> BacktestResult:
    if df.empty:
        return BacktestResult(0.0, 1.0, 0, 0, 0, 0.0)

    data = df.copy()
    if "tf_sec" in data.columns:
        data = data[pd.to_numeric(data["tf_sec"], errors="coerce") == basis_tf_sec]
    if data.empty:
        return BacktestResult(0.0, 1.0, 0, 0, 0, 0.0)

    required = [
        "symbol",
        "timestamp",
        "open",
        "close",
        "avg_high_12",
        "avg_low_12",
        "avg_close_12",
        "atr_current",
        "atr_ma_n",
        "atr_std_n",
        "dir_d1",
        "dir_h1",
        "dir_m30",
        "dir_m15",
    ]
    missing = [c for c in required if c not in data.columns]
    if missing:
        raise ValueError(f"MD-AMR backtest missing columns: {missing}")

    hysteresis_mult = float(params["hysteresis_mult"])
    threshold_z = float(params["threshold_z"])
    damp_factor = float(params["volatility_dampening_factor"])
    thr_base = float(params["thr_base"])
    thr_floor = float(params.get("thr_floor", 0.10))
    alpha = float(params["alpha"])
    conf_min = float(params["conf_min"])
    max_hold_bars = int(params.get("max_hold_bars", 16))
    atr_zscore_clamp = float(params.get("atr_zscore_clamp", 10.0))
    atr_std_floor_pct = float(params.get("atr_std_floor_pct", 0.05))
    fee_bps = float(params.get("fee_bps", 4.0))
    slippage_buffer_bps = float(params.get("slippage_buffer_bps", 2.0))
    scaleout_fraction = float(params.get("scaleout_fraction", 0.5))
    scaleout_cost_model = params.get("scaleout_cost_model", "round_trip")

    w_raw = {
        "d1": float(params["w_d1"]),
        "h1": float(params["w_h1"]),
        "m30": float(params["w_m30"]),
        "m15": float(params["w_m15"]),
    }

    net_profit = 0.0
    total_trades = 0
    partial_closes = 0
    skipped_rows = 0
    equity_curve: list[float] = [1.0]
    sort_cols = ["symbol", "timestamp"]
    if "segment_id" in data.columns:
        sort_cols = ["symbol", "segment_id", "timestamp"]

    for _symbol, sdf in data.sort_values(sort_cols, kind="mergesort").groupby("symbol", sort=False):
        if "segment_id" in sdf.columns:
            segment_iter = sdf.groupby("segment_id", sort=False)
        else:
            segment_iter = [(0, sdf)]

        for _segment_id, segment_df in segment_iter:
            s = segment_df.reset_index(drop=True)
            open_ = s["open"].to_numpy(dtype=float)
            close = s["close"].to_numpy(dtype=float)
            avg_high = s["avg_high_12"].to_numpy(dtype=float)
            avg_low = s["avg_low_12"].to_numpy(dtype=float)
            avg_close = s["avg_close_12"].to_numpy(dtype=float)
            atr_current = s["atr_current"].to_numpy(dtype=float)
            atr_ma_n = s["atr_ma_n"].to_numpy(dtype=float)
            atr_std_n = s["atr_std_n"].to_numpy(dtype=float)
            dir_d1 = s["dir_d1"].to_numpy(dtype=float)
            dir_h1 = s["dir_h1"].to_numpy(dtype=float)
            dir_m30 = s["dir_m30"].to_numpy(dtype=float)
            dir_m15 = s["dir_m15"].to_numpy(dtype=float)

            # Gap-aware reset: each segment starts FLAT and requires a fresh warmup window.
            pos = 0  # -1 short, 0 flat, +1 long
            pos_size = 1.0
            entry = 0.0
            bars_held = 0
            pending_entry = None

            for i in range(len(s)):
                fields = [
                    close[i],
                    avg_high[i],
                    avg_low[i],
                    avg_close[i],
                    atr_current[i],
                    atr_ma_n[i],
                    atr_std_n[i],
                    dir_d1[i],
                    dir_h1[i],
                    dir_m30[i],
                    dir_m15[i],
                ]
                if np.any(~np.isfinite(fields)):
                    skipped_rows += 1
                    continue

                # Deterministic warmup simulation: first 96 bars per segment are no-trade bars.
                if i < int(warmup_bars):
                    equity_curve.append(1.0 + net_profit)
                    continue

                # Calculate backtest entry/exit fees
                costs = (fee_bps + slippage_buffer_bps) / 10_000.0

                if pending_entry is not None and pos == 0:
                    direction = pending_entry
                    pos = 1 if direction == "LONG" else -1
                    entry = open_[i] if np.isfinite(open_[i]) else close[i-1] * (1 + costs)
                    pos_size = 1.0
                    bars_held = 0
                    total_trades += 1
                    # Deduct entry fee immediately (one-way entry fee)
                    net_profit -= pos_size * costs
                    pending_entry = None

                std_floor = max(abs(atr_ma_n[i]) * atr_std_floor_pct, 1e-9)
                effective_std = max(atr_std_n[i], std_floor)
                atr_z = (atr_current[i] - atr_ma_n[i]) / effective_std
                atr_z = float(np.clip(atr_z, -atr_zscore_clamp, atr_zscore_clamp))

                w_eff = dict(w_raw)
                if atr_z > threshold_z:
                    w_eff["d1"] = w_eff["d1"] * damp_factor
                    w_eff["h1"] = w_eff["h1"] * damp_factor
                w_norm = _normalize_weights(w_eff)

                dir_score = (
                    dir_d1[i] * w_norm["d1"]
                    + dir_h1[i] * w_norm["h1"]
                    + dir_m30[i] * w_norm["m30"]
                    + dir_m15[i] * w_norm["m15"]
                )
                dir_score = float(np.clip(dir_score, -1.0, 1.0))

                bias = alpha * abs(dir_score)
                if dir_score >= 0:
                    thr_buy = np.clip(thr_base - bias, thr_floor, 0.99)
                    thr_sell = np.clip(thr_base + bias, thr_floor, 0.99)
                else:
                    thr_buy = np.clip(thr_base + bias, thr_floor, 0.99)
                    thr_sell = np.clip(thr_base - bias, thr_floor, 0.99)

                band = max(abs(avg_high[i] - avg_low[i]), abs(close[i]) * 1e-6, 1e-9)
                long_score = max(0.0, (avg_low[i] - close[i]) / band) * hysteresis_mult
                short_score = max(0.0, (close[i] - avg_high[i]) / band) * hysteresis_mult
                score = float(np.clip(long_score - short_score, -1.0, 1.0))

                if pos == 0:
                    if score >= thr_buy:
                        pending_entry = "LONG"
                    elif score <= -thr_sell:
                        pending_entry = "SHORT"
                else:
                    bars_held += 1
                    if pos > 0:
                        conf_ratio = max(0.0, score) / max(float(thr_buy), 1e-9)
                        reached_target = close[i] >= avg_close[i]
                        expected_edge_after_costs = max(0.0, (avg_high[i] - close[i]) / max(abs(close[i]), 1e-9))
                    else:
                        conf_ratio = max(0.0, -score) / max(float(thr_sell), 1e-9)
                        reached_target = close[i] <= avg_close[i]
                        expected_edge_after_costs = max(0.0, (close[i] - avg_low[i]) / max(abs(close[i]), 1e-9))

                    conf_ratio = float(np.clip(conf_ratio, 0.0, 2.0))
                    costs = (fee_bps + slippage_buffer_bps) / 10_000.0

                    action = None
                    if conf_ratio < conf_min:
                        action = "FULL"
                    elif bars_held > max_hold_bars:
                        action = "FULL"
                    else:
                        cost_mult = 2.0 if scaleout_cost_model == "round_trip" else 1.0
                        if reached_target and expected_edge_after_costs > (costs * cost_mult):
                            action = "PARTIAL"

                    if action == "PARTIAL" and pos_size > 1e-9:
                        close_frac = min(max(scaleout_fraction, 0.01), 1.0)
                        raw_return = pos * ((close[i] - entry) / max(entry, 1e-9))
                        pnl = raw_return * pos_size * close_frac
                        exit_fee = pos_size * close_frac * costs
                        net_profit += pnl - exit_fee
                        pos_size = max(0.0, pos_size * (1.0 - close_frac))
                        partial_closes += 1
                        if pos_size <= 1e-6:
                            pos = 0
                            pos_size = 1.0
                            bars_held = 0
                    elif action == "FULL":
                        raw_return = pos * ((close[i] - entry) / max(entry, 1e-9))
                        pnl = raw_return * pos_size
                        exit_fee = pos_size * costs
                        net_profit += pnl - exit_fee
                        pos = 0
                        pos_size = 1.0
                        bars_held = 0

                unrealized = 0.0
                if pos != 0:
                    unrealized = pos * ((close[i] - entry) / max(entry, 1e-9)) * pos_size
                equity_curve.append(1.0 + net_profit + unrealized)

            if pos != 0 and len(s) > 0:
                raw_return = pos * ((close[-1] - entry) / max(entry, 1e-9))
                pnl = raw_return * pos_size
                exit_fee = pos_size * costs
                net_profit += pnl - exit_fee
                equity_curve.append(1.0 + net_profit)

    eq = np.asarray(equity_curve, dtype=float)
    peak = np.maximum.accumulate(eq)
    dd = (peak - eq) / np.maximum(peak, 1e-9)
    max_dd = float(np.nanmax(dd)) if len(dd) else 0.0

    if max_dd <= 1e-9:
        calmar = net_profit
    else:
        calmar = net_profit / max_dd

    return BacktestResult(
        net_profit=float(net_profit),
        max_dd=float(max_dd),
        total_trades=int(total_trades),
        partial_closes=int(partial_closes),
        skipped_rows=int(skipped_rows),
        calmar_ratio=float(calmar),
    )


def _parse_date(s: str) -> date:
    return date.fromisoformat(s)


def _default_params() -> Dict[str, Any]:
    return {
        "hysteresis_mult": 1.20,
        "w_d1": 0.35,
        "w_h1": 0.30,
        "w_m30": 0.20,
        "w_m15": 0.15,
        "threshold_z": 2.20,
        "volatility_dampening_factor": 0.50,
        "thr_base": 0.55,
        "alpha": 0.25,
        "conf_min": 0.22,
        "max_hold_bars": 16,
        "fee_bps": 4.0,
        "slippage_buffer_bps": 2.0,
        "scaleout_fraction": 0.50,
    }


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Run MD-AMR vectorized backtest on recorder 900s data")
    ap.add_argument("--recorder-dir", default="data/recorder")
    ap.add_argument("--symbols", nargs="+", default=["BTCUSDT", "ETHUSDT", "SOLUSDT", "DOGEUSDT", "XRPUSDT"])
    ap.add_argument("--start", type=_parse_date, default=None)
    ap.add_argument("--end", type=_parse_date, default=None)
    args = ap.parse_args()

    raw = load_recorder_900(Path(args.recorder_dir), symbols=args.symbols, start=args.start, end=args.end)
    feats = compute_md_amr_features(raw)
    res = run_vector_backtest(feats, params=_default_params(), basis_tf_sec=900)

    print("net_profit:", res.net_profit)
    print("max_dd:", res.max_dd)
    print("total_trades:", res.total_trades)
    print("partial_closes:", res.partial_closes)
    print("skipped_rows:", res.skipped_rows)
    print("calmar_ratio:", res.calmar_ratio)
