#!/usr/bin/env python3
"""
Dataset OHLCV visualization tool for regime inspection.

Usage examples:
    python3 tools/plot_dataset.py \
      --inputs data/BTCUSDT.parquet data/ETHUSDT.parquet \
      --symbol BTCUSDT \
      --start "2023-07-01" --end "2023-08-01" \
      --tf "3m" \
      --out plots/BTCUSDT_2023-07.png \
      --show \
      --max-bars 20000 \
      --regime-col regime_label \
      --confidence-col confidence

    python3 tools/plot_dataset.py \
      --inputs data/recorder/2026-01-15/BTCUSDT_180.csv \
      --out plots/btc_180.svg

Indicator formulas used when columns are missing:
    - True Range (TR):
      TR_t = max(high_t - low_t, abs(high_t - close_{t-1}), abs(low_t - close_{t-1}))
    - ATR (simple rolling):
      ATR_t = mean(TR_{t-N+1} ... TR_t), default N = 14
    - Bollinger Bands:
      MID_t = rolling_mean(close, W), STD_t = rolling_std(close, W)
      UPPER_t = MID_t + K * STD_t, LOWER_t = MID_t - K * STD_t
      BB_WIDTH_t = (UPPER_t - LOWER_t) / MID_t
      defaults: W = 20, K = 2.0
"""

from __future__ import annotations

import argparse
import math
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import numpy as np
import pandas as pd


SUPPORTED_INPUT_EXTS = {".csv", ".parquet", ".feather", ".jsonl", ".ndjson", ".json"}
DATE_ONLY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TIMEFRAME_RE = re.compile(r"^\s*(\d+)\s*([smhdSMHD])\s*$")

DEFAULT_TS_CANDIDATES = (
    "timestamp",
    "open_time",
    "openTime",
    "datetime",
    "date",
    "time",
    "ts",
)
DEFAULT_REGIME_CANDIDATES = ("regime_label", "regime", "market_regime", "state")
DEFAULT_CONF_CANDIDATES = (
    "confidence",
    "regime_confidence",
    "regime_conf",
    "shadow_confidence",
)
DEFAULT_VOLUME_CANDIDATES = ("volume", "vol", "qty", "quantity", "base_volume")
DEFAULT_SYMBOL_CANDIDATES = ("symbol", "ticker", "asset")
DEFAULT_TF_CANDIDATES = ("tf", "timeframe", "interval")
DEFAULT_TF_SEC_CANDIDATES = ("tf_sec", "timeframe_sec", "interval_sec", "bar_sec")

ATR_CANDIDATES = ("atr", "atr_14", "atr14")
BB_MID_CANDIDATES = ("bb_mid", "bb_middle", "bb_basis", "bollinger_mid")
BB_UPPER_CANDIDATES = ("bb_upper", "bollinger_upper")
BB_LOWER_CANDIDATES = ("bb_lower", "bollinger_lower")
BB_WIDTH_CANDIDATES = ("bb_width", "bollinger_width")
RETURNS_CANDIDATES = ("returns", "return", "ret", "log_return")
VOLATILITY_CANDIDATES = (
    "volatility_proxy",
    "volatility",
    "volatility_state",
    "realized_volatility",
    "rv",
    "vol_pct_300s",
    "vol_pct_60s",
    "vol_pct_10s",
)


class PlotDatasetError(RuntimeError):
    """Raised for user-actionable runtime errors."""


@dataclass(frozen=True)
class LoadedInput:
    """A standardized dataframe loaded from one input file."""

    path: Path
    frame: pd.DataFrame
    raw_rows: int


@dataclass(frozen=True)
class PreparedFrame:
    """A symbol-specific dataframe and diagnostics."""

    symbol: str
    frame: pd.DataFrame
    raw_rows: int
    downsample_factor: int
    computed_indicators: tuple[str, ...]
    applied_tf_filter: bool


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Visualize OHLCV datasets with regime and confidence overlays."
    )
    parser.add_argument(
        "--inputs",
        nargs="+",
        required=True,
        help="One or many input files: CSV/Parquet/Feather/JSONL/NDJSON/JSON.",
    )
    parser.add_argument(
        "--symbol",
        default=None,
        help="Symbol to plot (case-insensitive). If omitted, plots all detected symbols.",
    )
    parser.add_argument(
        "--start",
        default=None,
        help='Start datetime (ISO or date), e.g. "2023-07-01".',
    )
    parser.add_argument(
        "--end",
        default=None,
        help='End datetime (ISO or date), e.g. "2023-08-01".',
    )
    parser.add_argument(
        "--tf",
        default=None,
        help='Optional timeframe filter (e.g. "3m", "5m", "1h", "180s").',
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Output file path (.png/.svg). For multi-symbol runs, symbol suffix is appended.",
    )
    parser.add_argument(
        "--show",
        action="store_true",
        help="Display plot window after saving.",
    )
    parser.add_argument(
        "--max-bars",
        type=int,
        default=20_000,
        help="Maximum plotted bars per symbol before OHLC-preserving downsampling.",
    )
    parser.add_argument(
        "--regime-col",
        default="regime_label",
        help="Regime label column name (fallbacks are also tried if not found).",
    )
    parser.add_argument(
        "--confidence-col",
        default="confidence",
        help="Confidence column name (fallbacks are also tried if not found).",
    )
    parser.add_argument(
        "--atr-window",
        type=int,
        default=14,
        help="ATR window used when ATR must be computed.",
    )
    parser.add_argument(
        "--bb-window",
        type=int,
        default=20,
        help="Bollinger window used when BB must be computed.",
    )
    parser.add_argument(
        "--bb-num-std",
        type=float,
        default=2.0,
        help="Bollinger standard deviation multiplier.",
    )
    parser.add_argument(
        "--regime-style",
        choices=("background", "vlines", "none"),
        default="background",
        help="Regime rendering style on the chart.",
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=140,
        help="Figure DPI for saved output.",
    )
    parser.add_argument(
        "--figsize",
        default="16,10",
        help='Figure size as "width,height" in inches (default: 16,10).',
    )
    args = parser.parse_args(argv)
    if args.max_bars <= 0:
        raise PlotDatasetError("--max-bars must be > 0")
    if args.atr_window <= 0:
        raise PlotDatasetError("--atr-window must be > 0")
    if args.bb_window <= 1:
        raise PlotDatasetError("--bb-window must be > 1")
    if args.bb_num_std <= 0:
        raise PlotDatasetError("--bb-num-std must be > 0")
    return args


def parse_figsize(value: str) -> tuple[float, float]:
    """Parse --figsize value."""
    parts = [p.strip() for p in value.split(",")]
    if len(parts) != 2:
        raise PlotDatasetError('--figsize must look like "16,10"')
    try:
        w = float(parts[0])
        h = float(parts[1])
    except ValueError as exc:
        raise PlotDatasetError('--figsize must look like "16,10"') from exc
    if w <= 0 or h <= 0:
        raise PlotDatasetError("--figsize values must be positive")
    return (w, h)


def to_timestamp(value: str | None, *, is_end: bool) -> pd.Timestamp | None:
    """Parse timestamp bounds, with end-of-day handling for date-only values."""
    if value is None:
        return None
    try:
        ts = pd.to_datetime(value, utc=True)
    except Exception as exc:
        raise PlotDatasetError(f"Invalid datetime value: {value!r}") from exc
    ts = ts.tz_convert("UTC").tz_localize(None)
    if DATE_ONLY_RE.match(value.strip()) and is_end:
        ts = ts + pd.Timedelta(days=1) - pd.Timedelta(microseconds=1)
    return ts


def normalize_tf_to_seconds(value: str) -> int | None:
    """Normalize timeframe text to seconds."""
    txt = value.strip().lower()
    if txt.isdigit():
        return int(txt)
    match = TIMEFRAME_RE.match(value)
    if not match:
        return None
    count = int(match.group(1))
    unit = match.group(2).lower()
    mult = {"s": 1, "m": 60, "h": 3600, "d": 86_400}[unit]
    return count * mult


def normalize_tf_label(value: Any) -> str | None:
    """Normalize timeframe values to canonical labels like 3m/1h/180s."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    txt = str(value).strip()
    if not txt:
        return None
    sec = normalize_tf_to_seconds(txt)
    if sec is None:
        try:
            sec = int(float(txt))
        except ValueError:
            return txt.lower()
    if sec % 86_400 == 0:
        return f"{sec // 86_400}d"
    if sec % 3_600 == 0:
        return f"{sec // 3_600}h"
    if sec % 60 == 0:
        return f"{sec // 60}m"
    return f"{sec}s"


def _col_lookup(columns: Sequence[str]) -> dict[str, str]:
    return {c.lower(): c for c in columns}


def _resolve_col(columns: Sequence[str], *candidates: str) -> str | None:
    lookup = _col_lookup(columns)
    for candidate in candidates:
        if candidate in columns:
            return candidate
        key = candidate.lower()
        if key in lookup:
            return lookup[key]
    return None


def _resolve_preferred_then_fallback(
    columns: Sequence[str], preferred: str | None, fallback: Sequence[str]
) -> str | None:
    if preferred:
        col = _resolve_col(columns, preferred)
        if col is not None:
            return col
    return _resolve_col(columns, *fallback)


def infer_symbol_from_path(path: Path) -> str:
    """Infer a symbol label from a file path when symbol column is absent."""
    stem = path.stem
    token = stem.split("_")[0].split("-")[0].upper()
    if re.fullmatch(r"[A-Z0-9]{5,20}", token):
        return token
    for part in reversed(path.parts):
        up = part.upper()
        if re.fullmatch(r"[A-Z0-9]{5,20}", up):
            return up
    return "UNKNOWN"


def load_any(path: Path) -> pd.DataFrame:
    """Load input file based on extension."""
    ext = path.suffix.lower()
    if ext not in SUPPORTED_INPUT_EXTS:
        raise PlotDatasetError(
            f"Unsupported input extension: {path} (supported: {sorted(SUPPORTED_INPUT_EXTS)})"
        )
    if ext == ".csv":
        return pd.read_csv(path)
    if ext == ".parquet":
        try:
            return pd.read_parquet(path)
        except Exception as exc:
            return _load_with_polars_fallback(path, ext, exc)
    if ext == ".feather":
        try:
            return pd.read_feather(path)
        except Exception as exc:
            return _load_with_polars_fallback(path, ext, exc)
    if ext in {".jsonl", ".ndjson"}:
        return pd.read_json(path, lines=True)
    if ext == ".json":
        try:
            return pd.read_json(path, lines=True)
        except ValueError:
            return pd.read_json(path)
    raise PlotDatasetError(f"Unhandled extension: {ext}")


def _load_with_polars_fallback(path: Path, ext: str, initial_exc: Exception) -> pd.DataFrame:
    """Fallback loader for parquet/feather when pandas engine is unavailable."""
    try:
        import polars as pl
    except Exception as import_exc:
        raise PlotDatasetError(
            f"Failed to read {path} via pandas ({initial_exc}). "
            "Install pyarrow/fastparquet or polars to read this format."
        ) from import_exc
    try:
        if ext == ".parquet":
            return pl.read_parquet(path).to_pandas()
        if ext == ".feather":
            return pl.read_ipc(path).to_pandas()
    except Exception as fallback_exc:
        raise PlotDatasetError(
            f"Failed to read {path}: pandas error={initial_exc}; polars fallback failed={fallback_exc}"
        ) from fallback_exc
    raise PlotDatasetError(f"Polars fallback does not support extension {ext}")


def _numeric_epoch_to_datetime(series: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    finite = numeric[np.isfinite(numeric)]
    if finite.empty:
        return pd.to_datetime(numeric, errors="coerce", unit="ms", utc=True)
    median_abs = float(np.nanmedian(np.abs(finite.to_numpy(dtype=float))))
    if median_abs >= 1e17:
        unit = "ns"
    elif median_abs >= 1e14:
        unit = "us"
    elif median_abs >= 1e11:
        unit = "ms"
    else:
        unit = "s"
    return pd.to_datetime(numeric, errors="coerce", unit=unit, utc=True)


def parse_timestamp_series(series: pd.Series) -> pd.Series:
    """Parse timestamp column from numeric epoch or ISO strings into UTC-naive pandas timestamps."""
    if pd.api.types.is_datetime64_any_dtype(series):
        dt = pd.to_datetime(series, errors="coerce", utc=True)
    elif pd.api.types.is_numeric_dtype(series):
        dt = _numeric_epoch_to_datetime(series)
    else:
        numeric = pd.to_numeric(series, errors="coerce")
        # If object values are mostly numeric strings, treat them as epoch timestamps.
        numeric_ratio = float(numeric.notna().mean()) if len(numeric) else 0.0
        if numeric_ratio >= 0.8:
            as_num_dt = _numeric_epoch_to_datetime(numeric)
            non_numeric = series.where(numeric.isna())
            as_dt = pd.to_datetime(non_numeric, errors="coerce", utc=True)
            dt = as_num_dt.where(as_num_dt.notna(), as_dt)
        else:
            as_dt = pd.to_datetime(series, errors="coerce", utc=True)
            dt = as_dt
    return dt.dt.tz_convert("UTC").dt.tz_localize(None)


def standardize_input(
    raw: pd.DataFrame,
    path: Path,
    *,
    regime_col: str,
    confidence_col: str,
) -> LoadedInput:
    """Standardize raw dataframe to a canonical shape."""
    if raw.empty:
        return LoadedInput(path=path, frame=pd.DataFrame(), raw_rows=0)

    cols = list(raw.columns)
    ts_col = _resolve_col(cols, *DEFAULT_TS_CANDIDATES)
    if ts_col is None:
        raise PlotDatasetError(
            f"{path}: could not find timestamp/open_time column. "
            f"Supported names include: {DEFAULT_TS_CANDIDATES}"
        )

    open_col = _resolve_col(cols, "open")
    high_col = _resolve_col(cols, "high")
    low_col = _resolve_col(cols, "low")
    close_col = _resolve_col(cols, "close")
    missing = [
        name
        for name, col in (("open", open_col), ("high", high_col), ("low", low_col), ("close", close_col))
        if col is None
    ]
    if missing:
        raise PlotDatasetError(f"{path}: missing required OHLC columns: {missing}")

    frame = pd.DataFrame()
    frame["timestamp"] = parse_timestamp_series(raw[ts_col])
    frame["open"] = pd.to_numeric(raw[open_col], errors="coerce")
    frame["high"] = pd.to_numeric(raw[high_col], errors="coerce")
    frame["low"] = pd.to_numeric(raw[low_col], errors="coerce")
    frame["close"] = pd.to_numeric(raw[close_col], errors="coerce")

    volume_col = _resolve_col(cols, *DEFAULT_VOLUME_CANDIDATES)
    if volume_col is not None:
        frame["volume"] = pd.to_numeric(raw[volume_col], errors="coerce")

    symbol_col = _resolve_col(cols, *DEFAULT_SYMBOL_CANDIDATES)
    if symbol_col is not None:
        symbol_series = raw[symbol_col].astype("string").str.upper().str.strip()
        symbol_series = symbol_series.replace("", pd.NA).fillna(infer_symbol_from_path(path))
        frame["symbol"] = symbol_series
    else:
        frame["symbol"] = infer_symbol_from_path(path)

    tf_col = _resolve_col(cols, *DEFAULT_TF_CANDIDATES)
    if tf_col is not None:
        frame["tf"] = raw[tf_col]
    tf_sec_col = _resolve_col(cols, *DEFAULT_TF_SEC_CANDIDATES)
    if tf_sec_col is not None:
        frame["tf_sec"] = pd.to_numeric(raw[tf_sec_col], errors="coerce")

    regime_source = _resolve_preferred_then_fallback(cols, regime_col, DEFAULT_REGIME_CANDIDATES)
    if regime_source is not None:
        frame["regime"] = raw[regime_source]

    confidence_source = _resolve_preferred_then_fallback(cols, confidence_col, DEFAULT_CONF_CANDIDATES)
    if confidence_source is not None:
        frame["confidence"] = pd.to_numeric(raw[confidence_source], errors="coerce")

    for canonical, candidates in (
        ("atr", ATR_CANDIDATES),
        ("bb_mid", BB_MID_CANDIDATES),
        ("bb_upper", BB_UPPER_CANDIDATES),
        ("bb_lower", BB_LOWER_CANDIDATES),
        ("bb_width", BB_WIDTH_CANDIDATES),
        ("returns", RETURNS_CANDIDATES),
        ("volatility_proxy", VOLATILITY_CANDIDATES),
    ):
        source = _resolve_col(cols, *candidates)
        if source is None:
            continue
        frame[canonical] = pd.to_numeric(raw[source], errors="coerce")

    frame["source_file"] = str(path)
    raw_rows = len(frame)
    frame = frame.dropna(subset=["timestamp", "open", "high", "low", "close"])
    return LoadedInput(path=path, frame=frame, raw_rows=raw_rows)


def compute_atr(df: pd.DataFrame, window: int) -> pd.Series:
    """Compute rolling ATR."""
    prev_close = df["close"].shift(1)
    tr = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - prev_close).abs(),
            (df["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.rolling(window=window, min_periods=window).mean()


def compute_bollinger(df: pd.DataFrame, window: int, num_std: float) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series]:
    """Compute Bollinger bands and width."""
    mid = df["close"].rolling(window=window, min_periods=window).mean()
    std = df["close"].rolling(window=window, min_periods=window).std(ddof=0)
    upper = mid + (num_std * std)
    lower = mid - (num_std * std)
    width = (upper - lower) / mid.replace(0.0, np.nan)
    return mid, upper, lower, width


def ensure_indicators(df: pd.DataFrame, *, atr_window: int, bb_window: int, bb_num_std: float) -> tuple[pd.DataFrame, tuple[str, ...]]:
    """Ensure ATR/BB/volatility columns exist for plotting."""
    computed: list[str] = []
    out = df.copy()

    if "atr" not in out or out["atr"].notna().sum() == 0:
        out["atr"] = compute_atr(out, atr_window)
        computed.append(f"atr({atr_window})")
    else:
        out["atr"] = pd.to_numeric(out["atr"], errors="coerce")

    needs_bb = any(
        col not in out or out[col].notna().sum() == 0 for col in ("bb_mid", "bb_upper", "bb_lower")
    )
    if needs_bb:
        mid, upper, lower, width = compute_bollinger(out, bb_window, bb_num_std)
        out["bb_mid"] = mid
        out["bb_upper"] = upper
        out["bb_lower"] = lower
        computed.append(f"bollinger({bb_window},{bb_num_std})")

        if "bb_width" not in out or out["bb_width"].notna().sum() == 0:
            out["bb_width"] = width
            computed.append("bb_width")
    else:
        if "bb_width" not in out or out["bb_width"].notna().sum() == 0:
            out["bb_width"] = (
                (out["bb_upper"] - out["bb_lower"]) / out["bb_mid"].replace(0.0, np.nan)
            )
            computed.append("bb_width")

    if "returns" not in out or out["returns"].notna().sum() == 0:
        out["returns"] = out["close"].pct_change()
        computed.append("returns_pct_change")
    else:
        out["returns"] = pd.to_numeric(out["returns"], errors="coerce")

    if "volatility_proxy" not in out or out["volatility_proxy"].notna().sum() == 0:
        out["volatility_proxy"] = (
            out["returns"].rolling(window=bb_window, min_periods=2).std(ddof=0)
        )
        computed.append(f"volatility_proxy_std({bb_window})")
    else:
        out["volatility_proxy"] = pd.to_numeric(out["volatility_proxy"], errors="coerce")

    if "confidence" in out:
        out["confidence"] = pd.to_numeric(out["confidence"], errors="coerce").clip(lower=0.0, upper=1.0)

    return out, tuple(computed)


def downsample_ohlcv(df: pd.DataFrame, max_bars: int) -> tuple[pd.DataFrame, int]:
    """Downsample to max_bars while preserving OHLC bar structure."""
    n = len(df)
    if n <= max_bars:
        return df, 1

    factor = int(math.ceil(n / max_bars))
    groups = np.arange(n) // factor
    num_cols = set(df.select_dtypes(include=[np.number]).columns)
    agg: dict[str, str] = {}
    for col in df.columns:
        if col == "timestamp":
            agg[col] = "first"
        elif col == "open":
            agg[col] = "first"
        elif col == "high":
            agg[col] = "max"
        elif col == "low":
            agg[col] = "min"
        elif col == "close":
            agg[col] = "last"
        elif col == "volume":
            agg[col] = "sum"
        elif col in {"symbol", "source_file", "tf", "tf_sec"}:
            agg[col] = "first"
        elif col == "regime":
            agg[col] = "last"
        elif col == "confidence":
            agg[col] = "mean"
        elif col in {"atr", "bb_mid", "bb_upper", "bb_lower", "bb_width", "returns", "volatility_proxy"}:
            agg[col] = "mean"
        elif col in num_cols:
            agg[col] = "mean"
        else:
            agg[col] = "last"
    sampled = df.groupby(groups, sort=True, observed=False).agg(agg).reset_index(drop=True)
    return sampled, factor


def _try_import_matplotlib(show: bool):
    """Import matplotlib lazily with optional headless backend."""
    try:
        import matplotlib

        if not show:
            matplotlib.use("Agg")
        import matplotlib.dates as mdates
        import matplotlib.pyplot as plt
        from matplotlib.patches import Patch, Rectangle
    except Exception as exc:
        raise PlotDatasetError(
            "matplotlib is required for plotting. Install it in your venv (e.g. pip install matplotlib)."
        ) from exc
    return plt, mdates, Rectangle, Patch


def _build_regime_segments(labels: pd.Series) -> list[tuple[int, int, str]]:
    """Build contiguous regime segments as index ranges."""
    if labels.empty:
        return []
    clean = labels.fillna("NA").astype(str)
    changes = clean.ne(clean.shift(1))
    starts = np.flatnonzero(changes.to_numpy())
    segments: list[tuple[int, int, str]] = []
    for i, start_idx in enumerate(starts):
        end_idx = int(starts[i + 1] - 1) if i + 1 < len(starts) else (len(clean) - 1)
        label = str(clean.iloc[start_idx])
        segments.append((int(start_idx), end_idx, label))
    return segments


def _resolve_output_path(base_out: Path | None, symbol: str, multi_symbol: bool) -> Path:
    """Resolve output file path for a symbol."""
    if base_out is None:
        out_path = Path("plots") / f"{symbol}_dataset.png"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        return out_path

    if base_out.suffix:
        if multi_symbol:
            out_path = base_out.with_name(f"{base_out.stem}_{symbol}{base_out.suffix}")
        else:
            out_path = base_out
    else:
        out_path = base_out / f"{symbol}.png"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    return out_path


def plot_symbol_frame(
    prepared: PreparedFrame,
    *,
    out_path: Path,
    show: bool,
    figsize: tuple[float, float],
    dpi: int,
    regime_style: str,
) -> None:
    """Create and save a chart for one symbol."""
    plt, mdates, Rectangle, Patch = _try_import_matplotlib(show)

    df = prepared.frame
    has_conf = "confidence" in df and df["confidence"].notna().sum() > 0
    has_volume = "volume" in df and df["volume"].notna().sum() > 0
    has_regime = "regime" in df and df["regime"].notna().sum() > 0

    has_indicator = any(
        col in df and df[col].notna().sum() > 0
        for col in ("atr", "bb_width", "volatility_proxy")
    )

    heights: list[float] = [5.0]
    if has_indicator:
        heights.append(2.0)
    if has_conf:
        heights.append(1.8)
    if has_volume:
        heights.append(1.7)

    fig, axes = plt.subplots(
        nrows=len(heights),
        ncols=1,
        sharex=True,
        figsize=figsize,
        gridspec_kw={"height_ratios": heights},
    )
    if not isinstance(axes, np.ndarray):
        axes = np.array([axes])

    ax_price = axes[0]
    idx = 1
    ax_indicator = axes[idx] if has_indicator else None
    idx += int(has_indicator)
    ax_conf = axes[idx] if has_conf else None
    idx += int(has_conf)
    ax_volume = axes[idx] if has_volume else None

    x = mdates.date2num(df["timestamp"].dt.to_pydatetime())
    if len(x) > 1:
        x_step = float(np.nanmedian(np.diff(x)))
        if not np.isfinite(x_step) or x_step <= 0:
            x_step = 1.0 / (24.0 * 60.0)
    else:
        x_step = 1.0 / (24.0 * 60.0)
    bar_width = x_step * 0.72

    up_mask = df["close"] >= df["open"]
    body_colors = np.where(up_mask.to_numpy(), "#2ca02c", "#d62728")

    # Wicks.
    ax_price.vlines(x, df["low"], df["high"], color=body_colors, linewidth=0.7, alpha=0.9, zorder=2)

    # Bodies.
    global_range = float(df["high"].max() - df["low"].min()) if len(df) else 0.0
    body_min_height = max(global_range * 1e-4, 1e-8)
    for xi, o, c, color in zip(x, df["open"], df["close"], body_colors):
        lower = float(min(o, c))
        height = float(abs(c - o))
        if height <= 0:
            height = body_min_height
        rect = Rectangle(
            (float(xi) - (bar_width / 2.0), lower),
            bar_width,
            height,
            facecolor=color,
            edgecolor=color,
            linewidth=0.5,
            alpha=0.85,
            zorder=3,
        )
        ax_price.add_patch(rect)

    if all(col in df for col in ("bb_mid", "bb_upper", "bb_lower")):
        bb_ok = (
            df["bb_mid"].notna().sum() > 0
            and df["bb_upper"].notna().sum() > 0
            and df["bb_lower"].notna().sum() > 0
        )
        if bb_ok:
            ax_price.plot(df["timestamp"], df["bb_mid"], color="#1f77b4", linewidth=0.9, alpha=0.9, label="BB mid")
            ax_price.plot(df["timestamp"], df["bb_upper"], color="#1f77b4", linewidth=0.8, alpha=0.7, label="BB upper")
            ax_price.plot(df["timestamp"], df["bb_lower"], color="#1f77b4", linewidth=0.8, alpha=0.7, label="BB lower")
            ax_price.fill_between(
                x,
                df["bb_lower"].to_numpy(dtype=float),
                df["bb_upper"].to_numpy(dtype=float),
                color="#1f77b4",
                alpha=0.08,
                zorder=1,
            )

    regime_patches: list[Any] = []
    if has_regime and regime_style != "none":
        segments = _build_regime_segments(df["regime"])
        unique_labels = []
        seen = set()
        for _, _, lbl in segments:
            if lbl in seen:
                continue
            seen.add(lbl)
            unique_labels.append(lbl)

        cmap = plt.get_cmap("tab20")
        label_color = {lbl: cmap(i % 20) for i, lbl in enumerate(unique_labels)}
        regime_patches = [
            Patch(facecolor=label_color[lbl], alpha=0.18, edgecolor="none", label=f"regime:{lbl}")
            for lbl in unique_labels[:8]
        ]

        if regime_style == "background":
            for start_i, end_i, lbl in segments:
                x0 = float(x[start_i]) - (bar_width / 2.0)
                x1 = float(x[end_i]) + (bar_width / 2.0)
                for ax in axes:
                    ax.axvspan(x0, x1, color=label_color[lbl], alpha=0.07, zorder=0)
        elif regime_style == "vlines":
            for start_i, _, lbl in segments[1:]:
                for ax in axes:
                    ax.axvline(
                        float(x[start_i]),
                        color=label_color[lbl],
                        linestyle="--",
                        linewidth=0.8,
                        alpha=0.45,
                        zorder=1,
                    )

    if ax_indicator is not None:
        left_handles = []
        right_handles = []
        if "atr" in df and df["atr"].notna().sum() > 0:
            (h1,) = ax_indicator.plot(
                df["timestamp"], df["atr"], color="#ff7f0e", linewidth=1.0, label="ATR"
            )
            left_handles.append(h1)
            ax_indicator.set_ylabel("ATR")

        right_axis_needed = any(
            col in df and df[col].notna().sum() > 0 for col in ("bb_width", "volatility_proxy")
        )
        ax_indicator_right = ax_indicator.twinx() if right_axis_needed else None
        if ax_indicator_right is not None:
            if "bb_width" in df and df["bb_width"].notna().sum() > 0:
                (h2,) = ax_indicator_right.plot(
                    df["timestamp"], df["bb_width"], color="#1f77b4", linewidth=1.0, label="BB width"
                )
                right_handles.append(h2)
            if "volatility_proxy" in df and df["volatility_proxy"].notna().sum() > 0:
                (h3,) = ax_indicator_right.plot(
                    df["timestamp"],
                    df["volatility_proxy"],
                    color="#9467bd",
                    linewidth=0.9,
                    alpha=0.9,
                    label="vol proxy",
                )
                right_handles.append(h3)
            ax_indicator_right.set_ylabel("BB width / vol")

        legend_handles = left_handles + right_handles
        if legend_handles:
            ax_indicator.legend(
                legend_handles,
                [h.get_label() for h in legend_handles],
                loc="upper left",
                frameon=False,
                ncol=min(3, len(legend_handles)),
            )
        ax_indicator.set_title("Regime Indicators")

    if ax_conf is not None:
        ax_conf.plot(df["timestamp"], df["confidence"], color="#1f77b4", linewidth=1.0, label="confidence")
        for threshold, color in ((0.5, "#666666"), (0.85, "#ff7f0e"), (0.95, "#d62728")):
            ax_conf.axhline(threshold, color=color, linestyle="--", linewidth=0.8, alpha=0.9)
        ax_conf.set_ylim(-0.02, 1.02)
        ax_conf.set_ylabel("Conf")
        ax_conf.set_title("Regime Confidence")

    if ax_volume is not None:
        ax_volume.bar(
            df["timestamp"],
            df["volume"].fillna(0.0),
            width=bar_width,
            color=body_colors,
            alpha=0.35,
            align="center",
            linewidth=0.0,
        )
        ax_volume.set_ylabel("Volume")
        ax_volume.set_title("Volume")

    start_ts = df["timestamp"].iloc[0]
    end_ts = df["timestamp"].iloc[-1]
    title = (
        f"{prepared.symbol} | bars={len(df)} | range={start_ts.isoformat()} -> {end_ts.isoformat()} UTC"
    )
    ax_price.set_title(title)
    ax_price.set_ylabel("Price")

    price_handles, price_labels = ax_price.get_legend_handles_labels()
    if regime_patches:
        price_handles += regime_patches
        price_labels += [p.get_label() for p in regime_patches]
    if price_handles:
        ax_price.legend(
            price_handles,
            price_labels,
            loc="upper left",
            frameon=False,
            ncol=min(4, len(price_handles)),
        )

    for ax in axes:
        ax.grid(True, which="major", linestyle="--", linewidth=0.5, alpha=0.25)

    locator = mdates.AutoDateLocator(minticks=6, maxticks=12)
    formatter = mdates.ConciseDateFormatter(locator)
    axes[-1].xaxis.set_major_locator(locator)
    axes[-1].xaxis.set_major_formatter(formatter)
    axes[-1].set_xlabel("Time (UTC)")

    fig.tight_layout()
    fig.savefig(out_path, dpi=dpi, bbox_inches="tight")
    if show:
        plt.show()
    plt.close(fig)


def merge_inputs(loaded: Sequence[LoadedInput]) -> pd.DataFrame:
    """Merge loaded frames and deduplicate per symbol+timestamp."""
    non_empty = [x.frame.assign(_source_order=i) for i, x in enumerate(loaded) if not x.frame.empty]
    if not non_empty:
        return pd.DataFrame()

    merged = pd.concat(non_empty, ignore_index=True, sort=False)
    merged["symbol"] = (
        merged["symbol"]
        .astype("string")
        .str.upper()
        .str.strip()
        .replace("", pd.NA)
        .fillna("UNKNOWN")
    )
    merged = merged.sort_values(["symbol", "timestamp", "_source_order"])
    merged = merged.drop_duplicates(subset=["symbol", "timestamp"], keep="last")
    merged = merged.drop(columns=["_source_order"]).reset_index(drop=True)
    return merged


def apply_time_filter(df: pd.DataFrame, start_ts: pd.Timestamp | None, end_ts: pd.Timestamp | None) -> pd.DataFrame:
    """Apply datetime range filter."""
    out = df
    if start_ts is not None:
        out = out[out["timestamp"] >= start_ts]
    if end_ts is not None:
        out = out[out["timestamp"] <= end_ts]
    return out


def apply_timeframe_filter(df: pd.DataFrame, tf: str | None) -> tuple[pd.DataFrame, bool]:
    """Apply timeframe filter when tf metadata exists."""
    if tf is None:
        return df, False

    target_label = normalize_tf_label(tf)
    target_sec = normalize_tf_to_seconds(tf)
    out = df
    applied = False

    if "tf" in out and out["tf"].notna().sum() > 0 and target_label is not None:
        tf_norm = out["tf"].map(normalize_tf_label)
        mask = tf_norm == target_label
        if bool(mask.any()):
            out = out[mask]
            applied = True

    if (
        not applied
        and "tf_sec" in out
        and out["tf_sec"].notna().sum() > 0
        and target_sec is not None
    ):
        mask = pd.to_numeric(out["tf_sec"], errors="coerce") == float(target_sec)
        if bool(mask.any()):
            out = out[mask]
            applied = True

    return out, applied


def prepare_symbol_frame(
    symbol: str,
    merged: pd.DataFrame,
    *,
    start_ts: pd.Timestamp | None,
    end_ts: pd.Timestamp | None,
    tf: str | None,
    max_bars: int,
    atr_window: int,
    bb_window: int,
    bb_num_std: float,
) -> PreparedFrame:
    """Prepare one symbol dataframe for plotting."""
    symbol_df = merged[merged["symbol"] == symbol].copy()
    raw_rows = len(symbol_df)
    symbol_df = symbol_df.sort_values("timestamp")
    symbol_df = apply_time_filter(symbol_df, start_ts, end_ts)
    symbol_df, applied_tf = apply_timeframe_filter(symbol_df, tf)
    symbol_df = symbol_df.dropna(subset=["open", "high", "low", "close"])
    symbol_df = symbol_df[symbol_df["high"] >= symbol_df["low"]]
    symbol_df = symbol_df.reset_index(drop=True)

    if symbol_df.empty:
        raise PlotDatasetError(
            f"Symbol {symbol}: no rows left after filtering (start/end/tf or NA cleanup)."
        )

    symbol_df, factor = downsample_ohlcv(symbol_df, max_bars)
    symbol_df = symbol_df.sort_values("timestamp").reset_index(drop=True)
    symbol_df, computed = ensure_indicators(
        symbol_df,
        atr_window=atr_window,
        bb_window=bb_window,
        bb_num_std=bb_num_std,
    )
    return PreparedFrame(
        symbol=symbol,
        frame=symbol_df,
        raw_rows=raw_rows,
        downsample_factor=factor,
        computed_indicators=computed,
        applied_tf_filter=applied_tf,
    )


def print_summary(prepared: PreparedFrame) -> None:
    """Print concise run summary for one symbol."""
    df = prepared.frame
    start = df["timestamp"].iloc[0]
    end = df["timestamp"].iloc[-1]
    cols = ", ".join(sorted(df.columns))
    computed = ", ".join(prepared.computed_indicators) if prepared.computed_indicators else "none"
    tf_filter_txt = "yes" if prepared.applied_tf_filter else "no"

    print(f"[summary] symbol={prepared.symbol}")
    print(f"[summary] rows_raw={prepared.raw_rows} rows_plotted={len(df)}")
    print(f"[summary] time_range={start.isoformat()} -> {end.isoformat()} UTC")
    print(f"[summary] downsample_factor={prepared.downsample_factor}")
    print(f"[summary] tf_filter_applied={tf_filter_txt}")
    print(f"[summary] columns={cols}")
    print(f"[summary] computed_indicators={computed}")


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entrypoint."""
    args = parse_args(argv)
    figsize = parse_figsize(args.figsize)
    start_ts = to_timestamp(args.start, is_end=False)
    end_ts = to_timestamp(args.end, is_end=True)

    if start_ts is not None and end_ts is not None and start_ts > end_ts:
        raise PlotDatasetError("--start must be <= --end")

    input_paths = [Path(p) for p in args.inputs]
    missing = [p for p in input_paths if not p.exists()]
    if missing:
        raise PlotDatasetError(f"Input files do not exist: {missing}")

    loaded: list[LoadedInput] = []
    for path in input_paths:
        raw = load_any(path)
        standardized = standardize_input(
            raw,
            path,
            regime_col=args.regime_col,
            confidence_col=args.confidence_col,
        )
        loaded.append(standardized)
        print(f"[load] {path} rows_raw={len(raw)} rows_valid={len(standardized.frame)}")

    merged = merge_inputs(loaded)
    if merged.empty:
        raise PlotDatasetError("No valid OHLCV rows loaded from inputs.")

    symbol_filter = args.symbol.upper() if args.symbol else None
    if symbol_filter:
        merged = merged[merged["symbol"] == symbol_filter]
        if merged.empty:
            raise PlotDatasetError(
                f"Symbol filter {args.symbol!r} not found in loaded data."
            )

    symbols = sorted(s for s in merged["symbol"].dropna().astype(str).unique() if s)
    if not symbols:
        raise PlotDatasetError("No symbols detected after filtering.")

    base_out = Path(args.out) if args.out else None
    multi = len(symbols) > 1
    for symbol in symbols:
        prepared = prepare_symbol_frame(
            symbol,
            merged,
            start_ts=start_ts,
            end_ts=end_ts,
            tf=args.tf,
            max_bars=args.max_bars,
            atr_window=args.atr_window,
            bb_window=args.bb_window,
            bb_num_std=args.bb_num_std,
        )
        out_path = _resolve_output_path(base_out, symbol, multi_symbol=multi)
        plot_symbol_frame(
            prepared,
            out_path=out_path,
            show=args.show,
            figsize=figsize,
            dpi=args.dpi,
            regime_style=args.regime_style,
        )
        print_summary(prepared)
        print(f"[output] saved={out_path}")

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PlotDatasetError as exc:
        print(f"[error] {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
