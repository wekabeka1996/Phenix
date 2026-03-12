from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Iterable

import pandas as pd


def _parse_day(value: str) -> date | None:
    try:
        return date.fromisoformat(str(value))
    except Exception:
        return None


def load_recorder_rows(
    recorder_dir: Path,
    *,
    start: date | None,
    end: date | None,
    symbols: Iterable[str],
    tf_sec: int,
) -> pd.DataFrame:
    symbols_norm = {str(symbol).upper() for symbol in symbols}
    frames: list[pd.DataFrame] = []
    if not recorder_dir.exists():
        return pd.DataFrame()

    for day_dir in sorted(path for path in recorder_dir.iterdir() if path.is_dir()):
        day = _parse_day(day_dir.name)
        if day is None:
            continue
        if start is not None and day < start:
            continue
        if end is not None and day >= end:
            continue
        for symbol in symbols_norm:
            csv_path = day_dir / f"{symbol}_{int(tf_sec)}.csv"
            if not csv_path.exists():
                continue
            frame = pd.read_csv(csv_path)
            if frame.empty:
                continue
            frame["symbol"] = symbol
            frame["session_day"] = day.isoformat()
            frames.append(frame)

    if not frames:
        return pd.DataFrame()

    df = pd.concat(frames, ignore_index=True)
    df = df.rename(
        columns={
            "feat_price": "price",
            "feat_spread_bps": "spread_bps",
            "feat_liquidity_kappa": "liquidity_kappa",
            "feat_volatility_state": "volatility_state",
            "regime_conf": "regime_confidence",
        }
    )
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_numeric(df["timestamp"], errors="coerce")
    elif "datetime" in df.columns:
        dt = pd.to_datetime(df["datetime"], errors="coerce", utc=True)
        df["timestamp"] = (dt.view("int64") // 1_000_000).astype("float64")
    else:
        raise ValueError("Recorder data must contain timestamp or datetime column")

    if "tf_sec" in df.columns:
        df["tf_sec"] = pd.to_numeric(df["tf_sec"], errors="coerce")
        df = df[df["tf_sec"] == int(tf_sec)]
    else:
        df["tf_sec"] = int(tf_sec)

    for column in (
        "open",
        "high",
        "low",
        "close",
        "volume",
        "price",
        "spread_bps",
        "liquidity_kappa",
        "volatility_state",
        "regime_confidence",
    ):
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors="coerce")

    if "price" not in df.columns and "close" in df.columns:
        df["price"] = pd.to_numeric(df["close"], errors="coerce")

    df = df.dropna(subset=["timestamp", "symbol"]).copy()
    df["timestamp"] = df["timestamp"].astype("int64")
    df["symbol"] = df["symbol"].astype(str).str.upper()
    return df.sort_values(["symbol", "timestamp"], kind="mergesort").reset_index(drop=True)
