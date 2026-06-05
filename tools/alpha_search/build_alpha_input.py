#!/usr/bin/env python3
"""
tools/build_alpha_input.py
--------------------------
Converts data/recorder/**/*.csv  →  logs/alpha_input/alpha_input_v1.jsonl

Sources:
    data/recorder/{YYYY-MM-DD}/{SYMBOL}_{TFSEC}.csv   (375 files, 17 days)

Output:
    logs/alpha_input/alpha_input_v1.jsonl  (old file → .bak)

Features generated per record:
    Aurora (from feat_* CSV columns) + 19 TA features computed from OHLCV

TA features computed:
    rsi_14, bb_position, bb_width, bb_width_change,
    price_sma_20_deviation, macd_signal, stoch_k, stoch_d,
    atr_14, atr_ratio,
    price_momentum_5m, price_momentum_1h, price_momentum_1d,
    volume_momentum_5m, volume_sma_ratio,
    realized_volatility_1h, realized_volatility_1d,
    volume_volatility_ratio, price_range_ratio
"""

import json
import shutil
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

# ── Project root ───────────────────────────────────────────────────────────────
# tools/alpha_search/build_alpha_input.py → 3 levels up to project root
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
warnings.filterwarnings("ignore")

OUTPUT = ROOT / "logs" / "alpha_input" / "alpha_input_v1.jsonl"
RECORDER_DIR = ROOT / "data" / "recorder"

# ── Aurora feature columns in CSV (feat_* → strip prefix) ─────────────────────
AURORA_FEAT_COLS = [
    "feat_obi", "feat_tfi", "feat_delta_price", "feat_absorption",
    "feat_price", "feat_liquidity_kappa", "feat_ema_bias", "feat_volume_spike",
    "feat_volatility_state", "feat_depth_imbalance", "feat_macro_sync",
    "feat_macro_resid", "feat_volume_zscore", "feat_large_trade_imbalance",
    "feat_spread_bps",
]

TA_FEATURE_COLS = [
    "rsi_14", "bb_position", "bb_width", "bb_width_change",
    "price_sma_20_deviation", "macd_signal", "stoch_k", "stoch_d",
    "atr_14", "atr_ratio",
    "price_momentum_5m", "price_momentum_1h", "price_momentum_1d",
    "volume_momentum_5m", "volume_sma_ratio",
    "realized_volatility_1h", "realized_volatility_1d",
    "volume_volatility_ratio", "price_range_ratio",
]


# ── TA helpers ─────────────────────────────────────────────────────────────────

def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Wilder RSI normalized to [0, 1]."""
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_g = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_l = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_g / avg_l.replace(0, np.nan)
    return (100 - 100 / (1 + rs)) / 100  # [0, 1]


def _bollinger(close: pd.Series, period: int = 20, std_mult: float = 2.0):
    """Returns (bb_position [0,1], bb_width fractional, sma_deviation)."""
    sma = close.rolling(period).mean()
    std = close.rolling(period).std(ddof=0)
    upper = sma + std_mult * std
    lower = sma - std_mult * std
    band = (upper - lower).clip(lower=1e-9)
    pos = (close - lower) / band          # [0, 1]
    width = band / sma.clip(lower=1e-9)   # fractional band width
    dev = (close - sma) / sma.clip(lower=1e-9)
    return pos, width, dev


def _macd(close: pd.Series, fast: int = 12, slow: int = 26, sig: int = 9) -> pd.Series:
    """MACD signal line, normalized by price (scale-invariant)."""
    ema_f = close.ewm(span=fast, adjust=False).mean()
    ema_s = close.ewm(span=slow, adjust=False).mean()
    macd_line = ema_f - ema_s
    signal = macd_line.ewm(span=sig, adjust=False).mean()
    return signal / close.clip(lower=1e-9)


def _stochastic(close, high, low, k: int = 14, d: int = 3):
    """Returns (stoch_k, stoch_d) both in [0, 1]."""
    ll = low.rolling(k).min()
    hh = high.rolling(k).max()
    rng = (hh - ll).clip(lower=1e-9)
    stoch_k = (close - ll) / rng
    stoch_d = stoch_k.rolling(d).mean()
    return stoch_k, stoch_d


def _atr(high, low, close, period: int = 14):
    """Returns (atr_norm = ATR/close, atr_ratio = ATR/rolling_avg_ATR)."""
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    atr_raw = tr.ewm(alpha=1 / period, adjust=False).mean()
    atr_norm = atr_raw / close.clip(lower=1e-9)
    atr_avg = atr_raw.rolling(period * 2).mean()
    ratio = atr_raw / atr_avg.clip(lower=1e-9)
    return atr_norm, ratio


def _momentum(close: pd.Series, bars: int) -> pd.Series:
    """Tanh-squashed % change → ~[-1, 1]."""
    if bars < 1:
        return pd.Series(0.0, index=close.index)
    pct = close.pct_change(min(bars, max(len(close) - 1, 1)))
    return np.tanh(pct * 10)


def _vol_ratio(volume: pd.Series, period: int = 20) -> pd.Series:
    """Relative volume vs SMA, normalized to [0, 1]."""
    sma = volume.rolling(period).mean()
    ratio = volume / sma.clip(lower=1e-9)
    return ratio.clip(0, 3) / 3


def _realized_vol(close: pd.Series, bars: int) -> pd.Series:
    """Tanh-squashed rolling std of log-returns."""
    log_ret = np.log(close / close.shift(1))
    rv = log_ret.rolling(max(bars, 2)).std()
    return np.tanh(rv * 100)


def _vol_volatility_ratio(volume: pd.Series, period: int = 14) -> pd.Series:
    """CoV of volume, normalized to [0, 1]."""
    vol_std = volume.rolling(period).std()
    vol_mean = volume.rolling(period).mean().clip(lower=1e-9)
    return (vol_std / vol_mean).clip(0, 2) / 2


def _price_range_ratio(high, low, period: int = 14) -> pd.Series:
    """Current bar range vs rolling average range, clipped [0, 1]."""
    current = high - low
    avg = current.rolling(period).mean().clip(lower=1e-9)
    return (current / avg).clip(0, 3) / 3


# ── Main TA computation ────────────────────────────────────────────────────────

def compute_ta(df: pd.DataFrame, tf_sec: int) -> pd.DataFrame:
    """
    Compute all TA indicator columns in-place.
    df must be sorted by timestamp, single symbol+tf group.
    """
    bars_1h = max(1, 3600 // tf_sec)
    bars_1d = max(1, 86400 // tf_sec)
    bars_5m = max(1, 300 // tf_sec)

    c = df["close"].astype(float)
    h = df["high"].astype(float)
    lo = df["low"].astype(float)
    v = df["volume"].astype(float)

    df["rsi_14"] = _rsi(c, 14).fillna(0.5)

    bb_pos, bb_w, bb_dev = _bollinger(c)
    df["bb_position"] = bb_pos.fillna(0.5).clip(0, 1)
    df["bb_width"] = bb_w.fillna(0.0)
    df["bb_width_change"] = df["bb_width"].diff().fillna(0.0)
    df["price_sma_20_deviation"] = bb_dev.fillna(0.0)

    df["macd_signal"] = _macd(c).fillna(0.0)

    sk, sd = _stochastic(c, h, lo)
    df["stoch_k"] = sk.fillna(0.5).clip(0, 1)
    df["stoch_d"] = sd.fillna(0.5).clip(0, 1)

    atr_n, atr_r = _atr(h, lo, c)
    df["atr_14"] = atr_n.fillna(0.0)
    df["atr_ratio"] = atr_r.fillna(1.0)

    df["price_momentum_5m"] = _momentum(c, bars_5m).fillna(0.0)
    df["price_momentum_1h"] = _momentum(c, bars_1h).fillna(0.0)
    df["price_momentum_1d"] = _momentum(c, bars_1d).fillna(0.0)

    df["volume_momentum_5m"] = _vol_ratio(v, max(bars_5m, 3)).fillna(0.5)
    df["volume_sma_ratio"] = _vol_ratio(v, 20).fillna(0.5)

    df["realized_volatility_1h"] = _realized_vol(c, bars_1h).fillna(0.0)
    df["realized_volatility_1d"] = _realized_vol(c, bars_1d).fillna(0.0)

    df["volume_volatility_ratio"] = _vol_volatility_ratio(v).fillna(0.0)
    df["price_range_ratio"] = _price_range_ratio(h, lo).fillna(0.5)

    return df


# ── Record builder ─────────────────────────────────────────────────────────────

def build_records(df: pd.DataFrame) -> list:
    """Convert processed dataframe rows to AlphaInputV1 dicts."""
    records = []
    for _, row in df.iterrows():
        feats: dict = {}

        # Aurora features from feat_* columns
        for col in AURORA_FEAT_COLS:
            if col in row.index and pd.notna(row[col]):
                key = col[len("feat_"):]   # strip "feat_" prefix
                feats[key] = str(row[col])

        # TA features
        for col in TA_FEATURE_COLS:
            if col in row.index and pd.notna(row[col]):
                val = float(row[col])
                if not (val != val):   # not NaN
                    feats[col] = str(val)

        price = float(row.get("close", row.get("feat_price", 0.0)))
        regime = str(row.get("regime", "DEFAULT"))
        if regime in ("nan", "None", ""):
            regime = "DEFAULT"
        ts = int(row["timestamp"])

        records.append({
            "ts_ms": ts,
            "symbol": str(row["symbol"]),
            "tf_sec": int(row["tf_sec"]),
            "bar_close_ts": ts,
            "price": price,
            "features": feats,
            "regime": regime,
            "warmup_status": {},
            "source_verb": "FEATURES_CALCULATED",
            "source_trace_id": "",
        })
    return records


# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    csv_files = sorted(RECORDER_DIR.glob("**/*.csv"))
    if not csv_files:
        print(f"ERROR: No CSV files found in {RECORDER_DIR}")
        sys.exit(1)
    print(f"Found {len(csv_files)} CSV files in {RECORDER_DIR}")

    # Group dataframes by (symbol, tf_sec) to enable rolling TA computation
    groups: dict = {}
    skipped = 0
    for path in csv_files:
        try:
            df = pd.read_csv(path, dtype={"ready": str})
        except Exception as e:
            print(f"  SKIP {path}: {e}")
            skipped += 1
            continue

        # Filter ready rows only
        if "ready" in df.columns:
            df = df[df["ready"].str.strip().str.lower() == "true"]
        if df.empty:
            continue

        required = ["timestamp", "symbol", "tf_sec",
                    "close", "high", "low", "volume"]
        if not all(c in df.columns for c in required):
            print(
                f"  SKIP {path.name}: missing {[c for c in required if c not in df.columns]}")
            skipped += 1
            continue

        sym = str(df["symbol"].iloc[0])
        tf = int(df["tf_sec"].iloc[0])
        groups.setdefault((sym, tf), []).append(df)

    print(f"Groups: {sorted(groups.keys())}  (skipped {skipped} files)")

    all_records = []
    for (sym, tf), dfs in sorted(groups.items()):
        combined = pd.concat(dfs, ignore_index=True)
        combined = combined.sort_values("timestamp").drop_duplicates(
            subset=["timestamp"]
        ).reset_index(drop=True)

        print(f"  {sym}/{tf}s: {len(combined):>5} bars -> TA...",
              end="  ", flush=True)
        combined = compute_ta(combined, tf)
        recs = build_records(combined)
        all_records.extend(recs)
        print(
            f"{len(recs):>5} records  feat_count={len(recs[0]['features']) if recs else 0}")

    # Sort globally by timestamp
    all_records.sort(key=lambda r: r["ts_ms"])
    total = len(all_records)
    print(f"\nTotal: {total:,} records across {len(groups)} symbol/tf groups")

    # Backup old file
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    if OUTPUT.exists():
        bak = OUTPUT.with_suffix(".jsonl.bak")
        shutil.move(str(OUTPUT), str(bak))
        print(
            f"Backed up old file -> {bak.name}  ({bak.stat().st_size / 1e6:.1f} MB)")

    # Write
    print(f"Writing -> {OUTPUT} ...", end="  ", flush=True)
    with open(OUTPUT, "w", encoding="utf-8") as f:
        for rec in all_records:
            f.write(json.dumps(rec, default=str) + "\n")

    size_mb = OUTPUT.stat().st_size / 1e6
    print(f"done  ({size_mb:.1f} MB)")

    # Validate first record against AlphaInputV1 schema
    print("Validating schema...", end="  ")
    from apps.reference.domains.alpha_search.runtime.contracts import AlphaInputV1
    with open(OUTPUT, encoding="utf-8") as f:
        sample = json.loads(f.readline())
    v = AlphaInputV1(**sample)
    ta_present = [k for k in TA_FEATURE_COLS if k in v.features]
    aurora_present = [k for k in [c[len("feat_"):]
                                  for c in AURORA_FEAT_COLS] if k in v.features]
    print(f"OK")
    print(
        f"  symbol={v.symbol}  tf_sec={v.tf_sec}  total_features={len(v.features)}")
    print(f"  aurora features: {len(aurora_present)}/15")
    print(f"  TA features:     {len(ta_present)}/19  {ta_present}")

    # Stats by symbol/tf
    print("\nBreakdown:")
    from collections import Counter
    counts = Counter((r["symbol"], r["tf_sec"]) for r in all_records)
    for (sym, tf), cnt in sorted(counts.items()):
        print(f"  {sym:12s}  {tf:4d}s  {cnt:>6,} records")


if __name__ == "__main__":
    main()
