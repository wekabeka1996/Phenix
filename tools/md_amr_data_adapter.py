from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import logging
from pathlib import Path
from typing import Iterable, Optional

import numpy as np
import pandas as pd

LOG = logging.getLogger(__name__)


def _parse_date(s: str) -> date:
    return date.fromisoformat(s)


def load_recorder_900(
    recorder_root: Path,
    *,
    symbols: Iterable[str],
    start: Optional[date] = None,
    end: Optional[date] = None,
    basis_tf_sec: int = 900,
) -> pd.DataFrame:
    rows: list[pd.DataFrame] = []
    wanted = {str(s).upper() for s in symbols}
    if not recorder_root.exists():
        return pd.DataFrame()

    files_to_read: list[tuple[date, str, Path]] = []
    for day_dir in (p for p in recorder_root.iterdir() if p.is_dir()):
        try:
            d = _parse_date(day_dir.name)
        except ValueError:
            continue
        if start and d < start:
            continue
        if end and d >= end:
            continue
        for sym in wanted:
            p = day_dir / f"{sym}_{int(basis_tf_sec)}.csv"
            if not p.exists():
                continue
            files_to_read.append((d, sym, p))

    files_to_read.sort(key=lambda x: (x[0], x[2].name, str(x[2])))
    for _, sym, file_path in files_to_read:
        try:
            df = pd.read_csv(file_path)
        except pd.errors.ParserError as exc:
            LOG.warning(
                "MD_AMR CSV parse fallback file=%s err=%s (using on_bad_lines='skip')",
                str(file_path),
                str(exc),
            )
            df = pd.read_csv(file_path, engine="python", on_bad_lines="skip")
        if df.empty:
            continue
        if "symbol" not in df.columns:
            df["symbol"] = sym
        if "timestamp" in df.columns:
            df["timestamp"] = pd.to_numeric(df["timestamp"], errors="coerce")
            df = df.sort_values("timestamp", kind="mergesort")
        df["_source_file"] = str(file_path)
        rows.append(df)

    if not rows:
        return pd.DataFrame()

    out = pd.concat(rows, ignore_index=True)
    for col in ("timestamp", "open", "high", "low", "close", "volume"):
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    out["symbol"] = out["symbol"].astype(str).str.upper()
    out["tf_sec"] = pd.to_numeric(out.get("tf_sec", basis_tf_sec), errors="coerce").fillna(basis_tf_sec).astype(int)
    out = out[out["tf_sec"] == int(basis_tf_sec)].copy()
    out = out[np.isfinite(out["timestamp"])].copy()
    out["timestamp"] = out["timestamp"].astype(np.int64)
    out = out.sort_values(["symbol", "timestamp"], kind="mergesort").reset_index(drop=True)

    gap_threshold_ms = int(basis_tf_sec) * 2 * 1000
    out["_prev_ts"] = out.groupby("symbol")["timestamp"].shift(1)
    out["_gap_ms"] = out["timestamp"] - out["_prev_ts"]
    out["gap_reset"] = out["_gap_ms"] > gap_threshold_ms
    out["segment_id"] = out.groupby("symbol")["gap_reset"].cumsum().astype(int)

    gap_rows = out[out["gap_reset"] == True]
    for _, row in gap_rows.iterrows():
        prev_ts = int(row["_prev_ts"])
        cur_ts = int(row["timestamp"])
        gap_ms = int(row["_gap_ms"])
        LOG.warning(
            "MD_AMR data gap detected symbol=%s prev_ts=%s cur_ts=%s gap_sec=%.1f threshold_sec=%s",
            str(row["symbol"]),
            prev_ts,
            cur_ts,
            gap_ms / 1000.0,
            int(basis_tf_sec) * 2,
        )

    out = out.drop(columns=["_prev_ts", "_gap_ms"])
    return out


@dataclass(frozen=True)
class MDAMRFeatureConfig:
    channel_window: int = 12
    channel_robust_pct: float = 0.05
    atr_window: int = 14
    atr_stats_window: int = 64

def _winsorized_mean(series: pd.Series, robust_pct: float) -> float:
    if robust_pct <= 0 or robust_pct >= 0.5:
        return series.mean()
    clip_count = max(1, int(len(series) * robust_pct))
    sorted_vals = np.sort(series.values)
    lower, upper = sorted_vals[clip_count], sorted_vals[-clip_count - 1]
    return np.clip(series.values, lower, upper).mean()


def _tanh_return(close: pd.Series, lag: int) -> pd.Series:
    ret = (close / close.shift(lag)) - 1.0
    return np.tanh(ret * 6.0)


def compute_md_amr_features(df: pd.DataFrame, cfg: MDAMRFeatureConfig = MDAMRFeatureConfig()) -> pd.DataFrame:
    if df.empty:
        return df.copy()

    required_cols = {"symbol", "timestamp", "open", "high", "low", "close"}
    missing = sorted(required_cols.difference(df.columns))
    if missing:
        raise ValueError(f"Recorder data missing required columns: {missing}")

    out_frames: list[pd.DataFrame] = []
    group_cols = ["symbol", "segment_id"] if "segment_id" in df.columns else ["symbol"]
    for group_key, sdf in df.groupby(group_cols, sort=False):
        if isinstance(group_key, tuple):
            symbol = str(group_key[0])
        else:
            symbol = str(group_key)
        s = sdf.sort_values("timestamp", kind="mergesort").copy()
        
        if cfg.channel_robust_pct > 0:
            s["avg_open_12"] = s["open"].rolling(cfg.channel_window, min_periods=cfg.channel_window).apply(lambda x: _winsorized_mean(x, cfg.channel_robust_pct), raw=False)
            s["avg_high_12"] = s["high"].rolling(cfg.channel_window, min_periods=cfg.channel_window).apply(lambda x: _winsorized_mean(x, cfg.channel_robust_pct), raw=False)
            s["avg_low_12"] = s["low"].rolling(cfg.channel_window, min_periods=cfg.channel_window).apply(lambda x: _winsorized_mean(x, cfg.channel_robust_pct), raw=False)
            s["avg_close_12"] = s["close"].rolling(cfg.channel_window, min_periods=cfg.channel_window).apply(lambda x: _winsorized_mean(x, cfg.channel_robust_pct), raw=False)
        else:
            s["avg_open_12"] = s["open"].rolling(cfg.channel_window, min_periods=cfg.channel_window).mean()
            s["avg_high_12"] = s["high"].rolling(cfg.channel_window, min_periods=cfg.channel_window).mean()
            s["avg_low_12"] = s["low"].rolling(cfg.channel_window, min_periods=cfg.channel_window).mean()
            s["avg_close_12"] = s["close"].rolling(cfg.channel_window, min_periods=cfg.channel_window).mean()

        tr_hl = (s["high"] - s["low"]).abs()
        tr_hc = (s["high"] - s["close"].shift(1)).abs()
        tr_lc = (s["low"] - s["close"].shift(1)).abs()
        s["true_range"] = np.maximum(tr_hl, np.maximum(tr_hc, tr_lc))
        s["atr_current"] = s["true_range"].rolling(cfg.atr_window, min_periods=cfg.atr_window).mean()
        s["atr_ma_n"] = s["atr_current"].rolling(cfg.atr_stats_window, min_periods=cfg.atr_stats_window).mean()
        s["atr_std_n"] = s["atr_current"].rolling(cfg.atr_stats_window, min_periods=cfg.atr_stats_window).std(ddof=0)

        s["dir_d1"] = _tanh_return(s["close"], 96)
        s["dir_h1"] = _tanh_return(s["close"], 4)
        s["dir_m30"] = _tanh_return(s["close"], 2)
        s["dir_m15"] = _tanh_return(s["close"], 1)

        out_frames.append(s)

    out = pd.concat(out_frames, ignore_index=True)
    out = out.sort_values(["symbol", "timestamp"], kind="mergesort").reset_index(drop=True)
    return out
