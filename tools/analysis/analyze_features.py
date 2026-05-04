"""
Analyze real feature distributions from logs/features/*.log to calibrate
RegimeLabeler thresholds.

Reads feature logs, computes the derived metrics used by RegimeLabeler,
and prints percentiles + current label distribution.
"""

from apps.reference.domains.neocortex.logic.reward.regime_labeler import (
    RegimeLabeler, REGIME_NAMES, TREND_UP, TREND_DOWN,
    MEAN_REVERSION, HIGH_VOLATILITY, EXHAUSTION,
)
import json
import os
import sys
import numpy as np
from collections import Counter, defaultdict

sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")))


FEATURES_DIR = os.path.join(os.path.dirname(
    __file__), "..", "..", "logs", "features")
HORIZON = 5  # bars look-ahead


def load_features(symbol: str, max_lines: int = 60_000):
    """Load feature dicts from a symbol's log file."""
    path = os.path.join(FEATURES_DIR, f"{symbol}.log")
    rows = []
    with open(path, "r") as f:
        for i, line in enumerate(f):
            if i >= max_lines:
                break
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def safe_float(d, key, default=0.0):
    v = d.get(key, default)
    if v is None:
        return default
    return float(v)


def analyze_symbol(symbol: str, max_lines: int = 60_000):
    """Analyze feature distributions for a single symbol."""
    rows = load_features(symbol, max_lines)
    n = len(rows)
    print(f"\n{'='*70}")
    print(f"  {symbol}: {n} bars loaded")
    print(f"{'='*70}")

    # --- Check which features actually exist in the log ---
    sample = rows[0] if rows else {}
    labeler_features = [
        "volatility_atr_pct", "delta_price", "ema_bias",
        "volatility_range_pct", "volatility_state",
        "volume_spike", "spread_bps",
    ]
    print("\n  Feature presence in log:")
    for feat in labeler_features:
        present = feat in sample
        val = sample.get(feat, "MISSING")
        print(
            f"    {feat:30s} {'YES' if present else '*** MISSING ***':10s}  sample={val}")

    # --- Raw distributions of key features ---
    delta_prices = np.array([safe_float(r, "delta_price") for r in rows])
    ema_biases = np.array([safe_float(r, "ema_bias", 0.5) for r in rows])
    vol_states = np.array(
        [safe_float(r, "volatility_state", 0.5) for r in rows])
    vol_atr_pct = np.array([safe_float(r, "volatility_atr_pct") for r in rows])
    vol_range_pct = np.array(
        [safe_float(r, "volatility_range_pct") for r in rows])
    volume_spikes = np.array(
        [safe_float(r, "volume_spike", 0.5) for r in rows])

    pcts = [5, 10, 25, 50, 75, 90, 95]

    print("\n  Raw feature percentiles:")
    for name, arr in [
        ("delta_price", delta_prices),
        ("ema_bias", ema_biases),
        ("volatility_state", vol_states),
        ("volatility_atr_pct", vol_atr_pct),
        ("volatility_range_pct", vol_range_pct),
        ("volume_spike", volume_spikes),
    ]:
        if np.all(arr == 0):
            print(f"    {name:30s}  ALL ZEROS (feature missing from logs)")
            continue
        vals = np.percentile(arr, pcts)
        line = "  ".join(f"p{p}={v:+.6f}" for p, v in zip(pcts, vals))
        print(f"    {name:30s}  {line}")
        print(
            f"    {'':30s}  min={arr.min():+.6f}  max={arr.max():+.6f}  mean={arr.mean():+.6f}  std={arr.std():.6f}")

    # --- Derived metrics used by labeler (comparing t vs t+H) ---
    print(f"\n  Derived labeler metrics (horizon={HORIZON}):")

    # vol_ratio = atr_pct(t+H) / atr_pct(t)
    vol_ratios = []
    delta_price_futures = []
    ema_bias_futures = []
    range_pct_futures = []
    vol_state_ratios = []

    for i in range(n - HORIZON):
        t = rows[i]
        t_h = rows[i + HORIZON]

        atr_now = safe_float(t, "volatility_atr_pct")
        atr_fut = safe_float(t_h, "volatility_atr_pct")
        if atr_now > 1e-12:
            vol_ratios.append(atr_fut / atr_now)

        delta_price_futures.append(safe_float(t_h, "delta_price"))
        ema_bias_futures.append(safe_float(t_h, "ema_bias", 0.5))
        range_pct_futures.append(safe_float(t_h, "volatility_range_pct"))

        # Alternative: volatility_state ratio
        vs_now = safe_float(t, "volatility_state", 0.5)
        vs_fut = safe_float(t_h, "volatility_state", 0.5)
        if vs_now > 1e-12:
            vol_state_ratios.append(vs_fut / vs_now)

    for name, arr_list in [
        ("vol_ratio (atr_pct)", vol_ratios),
        ("vol_state_ratio", vol_state_ratios),
        ("delta_price(t+H)", delta_price_futures),
        ("ema_bias(t+H)", ema_bias_futures),
        ("range_pct(t+H)", range_pct_futures),
    ]:
        arr = np.array(arr_list) if arr_list else np.array([0.0])
        if len(arr_list) == 0 or np.all(arr == 0):
            print(f"    {name:30s}  NO DATA (source feature missing)")
            continue
        vals = np.percentile(arr, pcts)
        line = "  ".join(f"p{p}={v:+.6f}" for p, v in zip(pcts, vals))
        print(f"    {name:30s}  {line}")
        print(f"    {'':30s}  min={arr.min():+.6f}  max={arr.max():+.6f}  mean={arr.mean():+.6f}  std={arr.std():.6f}  n={len(arr_list)}")

    # --- Current labeler classification ---
    print(f"\n  Current labeler output (with CALIBRATED thresholds):")
    labeler = RegimeLabeler(
        high_vol_threshold=0.8,
        exhaustion_vol_now_threshold=0.5,
        exhaustion_vol_future_threshold=0.1,
        trend_delta_pct_threshold=0.0002,
        trend_ema_threshold=0.0008,
        mr_delta_pct_threshold=0.0001,
    )
    counts = Counter()
    for i in range(n - HORIZON):
        feat_t = {k: safe_float(rows[i], k) for k in rows[i]}
        feat_h = {k: safe_float(rows[i + HORIZON], k)
                  for k in rows[i + HORIZON]}
        label = labeler.compute_realized_regime(feat_t, feat_h)
        counts[label] += 1

    total = sum(counts.values())
    for regime_id in range(5):
        c = counts.get(regime_id, 0)
        pct = 100.0 * c / total if total > 0 else 0
        print(f"    {REGIME_NAMES[regime_id]:30s}  {c:6d}  ({pct:5.1f}%)")

    return rows, counts


def main():
    symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "DOGEUSDT", "XRPUSDT"]
    all_counts = Counter()

    for sym in symbols:
        path = os.path.join(FEATURES_DIR, f"{sym}.log")
        if not os.path.exists(path):
            print(f"  SKIP {sym} (file not found)")
            continue
        _, counts = analyze_symbol(sym, max_lines=50_000)
        all_counts.update(counts)

    print(f"\n{'='*70}")
    print(f"  AGGREGATE across all symbols")
    print(f"{'='*70}")
    total = sum(all_counts.values())
    for regime_id in range(5):
        c = all_counts.get(regime_id, 0)
        pct = 100.0 * c / total if total > 0 else 0
        print(f"    {REGIME_NAMES[regime_id]:30s}  {c:6d}  ({pct:5.1f}%)")
    print(f"    {'TOTAL':30s}  {total:6d}")

    # --- Diagnose WHY rules fail ---
    print(f"\n{'='*70}")
    print(f"  DIAGNOSIS: Why rules fail")
    print(f"{'='*70}")

    # Use BTCUSDT as reference
    rows = load_features("BTCUSDT", 50_000)
    n = len(rows)

    # Check Rule 4 TREND_DOWN failure
    rule4_delta_ok = 0
    rule4_ema_ok = 0
    rule4_both = 0
    for i in range(n - HORIZON):
        t_h = rows[i + HORIZON]
        dp = safe_float(t_h, "delta_price")
        eb = safe_float(t_h, "ema_bias", 0.5)
        if dp < -0.001:
            rule4_delta_ok += 1
        if eb < -0.0005:
            rule4_ema_ok += 1
        if dp < -0.001 and eb < -0.0005:
            rule4_both += 1

    total_pairs = n - HORIZON
    print(f"\n  Rule 4 (TREND_DOWN) diagnosis (BTCUSDT, n={total_pairs}):")
    print(
        f"    delta_price(t+H) < -0.001:  {rule4_delta_ok:6d}  ({100.0*rule4_delta_ok/total_pairs:.1f}%)")
    print(
        f"    ema_bias(t+H) < -0.0005:    {rule4_ema_ok:6d}  ({100.0*rule4_ema_ok/total_pairs:.1f}%)")
    print(
        f"    BOTH (rule fires):           {rule4_both:6d}  ({100.0*rule4_both/total_pairs:.1f}%)")

    # Check Rule 1 HIGH_VOL failure
    rule1_fires = 0
    atr_nonzero = 0
    for i in range(n - HORIZON):
        atr_now = safe_float(rows[i], "volatility_atr_pct")
        atr_fut = safe_float(rows[i + HORIZON], "volatility_atr_pct")
        if atr_now > 1e-12:
            atr_nonzero += 1
            vr = atr_fut / atr_now
            if vr > 1.0 / 0.75:
                rule1_fires += 1

    print(f"\n  Rule 1 (HIGH_VOLATILITY) diagnosis:")
    print(
        f"    volatility_atr_pct > 0:      {atr_nonzero:6d}  ({100.0*atr_nonzero/total_pairs:.1f}%)")
    print(
        f"    vol_ratio > 1.33:            {rule1_fires:6d}  ({100.0*rule1_fires/total_pairs:.1f}%)")

    # Check ema_bias distribution
    print(f"\n  ema_bias distribution (BTCUSDT, raw values):")
    ebs = [safe_float(rows[i], "ema_bias", 0.5) for i in range(n)]
    ebs = np.array(ebs)
    print(
        f"    min={ebs.min():.6f}  max={ebs.max():.6f}  mean={ebs.mean():.6f}")
    print(f"    count < 0:      {np.sum(ebs < 0):6d}")
    print(f"    count < 0.0005: {np.sum(ebs < 0.0005):6d}")
    print(f"    count > 0.4:    {np.sum(ebs > 0.4):6d}")
    print(f"    count > 0.5:    {np.sum(ebs > 0.5):6d}")
    print(f"    count < 0.5:    {np.sum(ebs < 0.5):6d}")


if __name__ == "__main__":
    main()
