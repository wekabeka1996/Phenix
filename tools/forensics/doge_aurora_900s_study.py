#!/usr/bin/env python3
"""
DOGE x Aurora @ 900s Deep Follow-Up Study

Phase A: Exactification - rebuild 900s evidence with reduced boundedness
Phase B: Runtime feasibility audit
Phase C: Testnet candidate decision

Uses all DOGE 900s bar data from recorder + regime reconstruction from 300s
recorded regimes (since 900s regime is always PENDING).
"""

import csv
import json
import os
import glob
import math
from collections import Counter, defaultdict
from pathlib import Path

BASE = Path(r"c:\Users\user\Music\Phenix")
RECORDER = BASE / "data" / "recorder"
ALPHA_INPUT = BASE / "logs" / "alpha_input" / "alpha_input_v1.jsonl"

# === COST MODEL (same as prior study) ===
FEE_BPS = 4.0
SLIPPAGE_BPS = 2.0
SPREAD_BPS = 1.0
ROUND_TRIP_BPS = 2 * (FEE_BPS + SLIPPAGE_BPS + SPREAD_BPS)  # 14 bps

# === AURORA DOGE CONFIG (from aurora.yaml DOGEUSDT block) ===
AURORA_SL_PCT = 0.01512      # 1.512% base SL
AURORA_MAX_HOLD_SEC = 3000   # 50 min
AURORA_SIGNAL_THRESHOLD = 0.09
AURORA_REENTRY_COOLDOWN = 120  # sec
AURORA_MIN_SL_PCT = 0.0025
AURORA_MAX_SL_PCT = 0.020
AURORA_MIN_TP_RR = 0.25
AURORA_MAX_TP_RR = 1.2
AURORA_MIN_DIST_BPS = 18

# Regime TPSL multipliers for DOGE (from aurora.yaml)
REGIME_SL_MULT = {
    "DEFAULT": 1.0, "FLAT_LOW": 0.60, "LOW_VOLATILITY": 0.65,
    "FLAT_NORMAL": 0.75, "MEAN_REVERSION": 0.85, "TREND_UP": 1.15,
    "TREND_DOWN": 1.15, "HIGH_VOLATILITY": 1.50, "UNCERTAIN": 1.00,
}
REGIME_TP_MULT = {
    "DEFAULT": 1.0, "FLAT_LOW": 0.65, "LOW_VOLATILITY": 0.70,
    "FLAT_NORMAL": 0.80, "MEAN_REVERSION": 0.75, "TREND_UP": 1.30,
    "TREND_DOWN": 1.30, "HIGH_VOLATILITY": 1.10, "UNCERTAIN": 1.00,
}

# Regime detection params
SMA_SHORT = 48
SMA_LONG = 192
ATR_PERIOD = 14
FLAT_LOW_THR = 0.001
FLAT_HIGH_THR = 0.003


def load_900s_bars():
    """Load all DOGE 900s bars from recorder."""
    bars = []
    pattern = str(RECORDER / "*" / "DOGEUSDT_900.csv")
    files = sorted(glob.glob(pattern))
    print(f"[DATA] Found {len(files)} DOGE 900s recorder files")

    for f in files:
        with open(f, "r") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                try:
                    ts_raw = row.get("timestamp")
                    if not ts_raw:
                        continue
                    ts = int(float(ts_raw))
                    o = float(row.get("open") or 0)
                    h = float(row.get("high") or 0)
                    l_ = float(row.get("low") or 0)
                    c = float(row.get("close") or 0)
                    if o == 0 or c == 0:
                        continue
                    vol = float(row.get("volume", "0") or "0")
                    ready = row.get("ready", "False") == "True"
                    bars.append({
                        "ts_ms": ts,
                        "datetime": row.get("datetime", ""),
                        "open": o, "high": h, "low": l_, "close": c,
                        "volume": vol, "ready": ready,
                        "spread_bps": float(row.get("feat_spread_bps") or "0"),
                    })
                except (ValueError, KeyError, TypeError):
                    continue

    # Deduplicate
    seen = set()
    unique = []
    for b in sorted(bars, key=lambda x: x["ts_ms"]):
        if b["ts_ms"] not in seen:
            seen.add(b["ts_ms"])
            unique.append(b)

    print(f"[DATA] Loaded {len(unique)} unique DOGE 900s bars")
    if unique:
        print(f"[DATA] Period: {unique[0]['datetime']} to {unique[-1]['datetime']}")
    return unique


def load_300s_bars():
    """Load DOGE 300s bars for regime reconstruction."""
    bars = []
    pattern = str(RECORDER / "*" / "DOGEUSDT_300.csv")
    files = sorted(glob.glob(pattern))

    for f in files:
        with open(f, "r") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                try:
                    ts_raw = row.get("timestamp")
                    if not ts_raw:
                        continue
                    ts = int(float(ts_raw))
                    c = float(row.get("close") or 0)
                    if c == 0:
                        continue
                    regime = row.get("regime", "UNKNOWN") or "UNKNOWN"
                    rc = float(row.get("regime_conf", "0") or "0")
                    bars.append({"ts_ms": ts, "close": c, "regime": regime, "regime_conf": rc})
                except (ValueError, KeyError, TypeError):
                    continue

    seen = set()
    unique = []
    for b in sorted(bars, key=lambda x: x["ts_ms"]):
        if b["ts_ms"] not in seen:
            seen.add(b["ts_ms"])
            unique.append(b)

    print(f"[REGIME] Loaded {len(unique)} DOGE 300s bars for regime source")
    return unique


def load_alpha_regimes():
    """Load regime labels from alpha_input (only source with resolved regimes at 900s)."""
    regimes = {}
    if not ALPHA_INPUT.exists():
        return regimes
    with open(ALPHA_INPUT, "r") as f:
        for line in f:
            try:
                obj = json.loads(line.strip())
                if obj.get("symbol") != "DOGEUSDT":
                    continue
                if obj.get("tf_sec") != 900:
                    continue
                ts = obj["ts_ms"]
                reg = obj.get("regime", "UNKNOWN")
                if reg and reg != "DEFAULT":
                    regimes[ts] = reg
            except (json.JSONDecodeError, KeyError):
                continue
    print(f"[REGIME] Loaded {len(regimes)} alpha_input regime labels for 900s")
    return regimes


# === TECHNICAL INDICATORS ===

def compute_sma(values, period):
    if len(values) < period:
        return None
    return sum(values[-period:]) / period


def compute_atr(highs, lows, closes, period=ATR_PERIOD):
    if len(closes) < period + 1:
        return None
    trs = []
    for i in range(-period, 0):
        tr = max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1]))
        trs.append(tr)
    return sum(trs) / period


def classify_macro_regime(closes, highs, lows, atr, sma_s, sma_l):
    if atr is None:
        return "UNCERTAIN", 0.0
    price = closes[-1]
    if sma_s is not None and sma_l is not None:
        spread = abs(sma_s - sma_l) / price
        dev_s = abs(price - sma_s) / price
        dev_l = abs(price - sma_l) / price
        if spread < 0.005 and dev_s < 0.005 and dev_l < 0.005:
            return "MEAN_REVERSION", min(0.85, 0.15 + 120 * (0.005 - max(spread, dev_s)))
        if sma_s > sma_l and price > sma_s:
            return "TREND_UP", min(0.85, max(0.15, 80 * (sma_s - sma_l) / price))
        if sma_s < sma_l and price < sma_s:
            return "TREND_DOWN", min(0.85, max(0.15, 80 * (sma_l - sma_s) / price))
    return "UNCERTAIN", 0.15


def classify_flat_bucket(atr, price):
    if atr is None or price <= 0:
        return "NONE"
    pct = atr / price
    if pct < FLAT_LOW_THR:
        return "FLAT_LOW"
    elif pct < FLAT_HIGH_THR:
        return "FLAT_NORMAL"
    return "FLAT_HIGH"


# === AURORA-LIKE COMPOSITE SIGNAL ===

def aurora_composite_signal(bar, atr, bb_upper, bb_mid, bb_lower, rsi, sma20_dev):
    """
    Proxy for Aurora quadratic composite signal.
    Uses feature-based scoring similar to what Aurora handler would produce.
    This is BOUNDED - not the actual Aurora signal model.
    """
    if atr is None or bb_upper is None:
        return None

    price = bar["close"]
    spread = bar.get("spread_bps", 0)

    # Score components (bounded proxy)
    bb_width = (bb_upper - bb_lower) / bb_mid if bb_mid > 0 else 0
    if bb_width < 0.001:
        return None  # Too narrow, no trade

    # Deviation from mean
    dev = (price - bb_mid) / (bb_upper - bb_mid) if (bb_upper - bb_mid) > 0 else 0

    # Base directional score
    if dev < -0.3 and rsi is not None and rsi < 40:
        direction = "BUY"
        score = min(1.0, abs(dev) * 0.4 + (40 - rsi) / 100 * 0.3 + bb_width * 5)
    elif dev > 0.3 and rsi is not None and rsi > 60:
        direction = "SELL"
        score = min(1.0, abs(dev) * 0.4 + (rsi - 60) / 100 * 0.3 + bb_width * 5)
    else:
        return None

    if score < AURORA_SIGNAL_THRESHOLD:
        return None

    return {
        "type": direction,
        "score": score,
        "entry_price": price,
        "atr": atr,
        "bb_mid": bb_mid,
        "bb_upper": bb_upper,
        "bb_lower": bb_lower,
        "bb_width": bb_width,
        "rsi": rsi,
        "dev": dev,
    }


def compute_bb(closes, window=20, std_mult=2.0):
    if len(closes) < window:
        return None, None, None, None
    data = closes[-window:]
    mid = sum(data) / window
    var = sum((x - mid)**2 for x in data) / window
    std = math.sqrt(var)
    return mid + std_mult * std, mid, mid - std_mult * std, (2 * std_mult * std / mid if mid > 0 else 0)


def compute_rsi(closes, period=14):
    if len(closes) < period + 1:
        return None
    gains, losses = [], []
    for i in range(-period, 0):
        ch = closes[i] - closes[i-1]
        gains.append(max(0, ch))
        losses.append(max(0, -ch))
    ag = sum(gains) / period
    al = sum(losses) / period
    if al == 0:
        return 100
    return 100 - 100 / (1 + ag / al)


# === TRADE SIMULATION ===

def simulate_trade(bars, entry_idx, signal, regime, sl_mult=1.0, tp_mult=1.0, max_hold_bars=24):
    entry = signal["entry_price"]
    direction = 1 if signal["type"] == "BUY" else -1

    # Aurora TP/SL with regime TPSL
    base_sl = AURORA_SL_PCT
    r_sl = REGIME_SL_MULT.get(regime, 1.0) * sl_mult
    r_tp = REGIME_TP_MULT.get(regime, 1.0) * tp_mult

    sl_pct = max(AURORA_MIN_SL_PCT, min(AURORA_MAX_SL_PCT, base_sl * r_sl))
    tp_rr = max(AURORA_MIN_TP_RR, min(AURORA_MAX_TP_RR, 0.6 * r_tp))
    tp_pct = sl_pct * tp_rr

    if direction == 1:
        stop = entry * (1 - sl_pct)
        target = entry * (1 + tp_pct)
    else:
        stop = entry * (1 + sl_pct)
        target = entry * (1 - tp_pct)

    mae = mfe = 0
    exit_reason = "HOLD_EXPIRED"
    exit_price = None
    hold_bars = 0

    for i in range(entry_idx + 1, min(entry_idx + 1 + max_hold_bars, len(bars))):
        bar = bars[i]
        hold_bars += 1
        if direction == 1:
            adv = entry - bar["low"]
            fav = bar["high"] - entry
        else:
            adv = bar["high"] - entry
            fav = entry - bar["low"]
        mae = max(mae, adv)
        mfe = max(mfe, fav)

        # SL check
        if direction == 1 and bar["low"] <= stop:
            exit_reason = "SL"
            exit_price = stop
            break
        elif direction == -1 and bar["high"] >= stop:
            exit_reason = "SL"
            exit_price = stop
            break
        # TP check
        if direction == 1 and bar["high"] >= target:
            exit_reason = "TP"
            exit_price = target
            break
        elif direction == -1 and bar["low"] <= target:
            exit_reason = "TP"
            exit_price = target
            break

    if exit_price is None:
        last = min(entry_idx + max_hold_bars, len(bars) - 1)
        exit_price = bars[last]["close"]

    if direction == 1:
        gross_pct = (exit_price - entry) / entry * 100
    else:
        gross_pct = (entry - exit_price) / entry * 100
    net_pct = gross_pct - ROUND_TRIP_BPS / 100

    risk = sl_pct * 100
    gross_r = gross_pct / risk if risk > 0 else 0
    net_r = net_pct / risk if risk > 0 else 0
    mae_r = (mae / entry * 100) / risk if risk > 0 else 0
    mfe_r = (mfe / entry * 100) / risk if risk > 0 else 0

    return {
        "exit_reason": exit_reason, "entry_price": entry, "exit_price": exit_price,
        "hold_bars": hold_bars, "gross_pnl_pct": gross_pct, "net_pnl_pct": net_pct,
        "gross_r": gross_r, "net_r": net_r, "mae": mae, "mfe": mfe,
        "mae_r": mae_r, "mfe_r": mfe_r, "direction": signal["type"],
        "stop_price": stop, "target_price": target, "sl_pct": sl_pct, "tp_pct": tp_pct,
    }


def summarize(results, label):
    if not results:
        return {"label": label, "trades": 0}
    n = len(results)
    sl_c = sum(1 for r in results if r["exit_reason"] == "SL")
    tp_c = sum(1 for r in results if r["exit_reason"] == "TP")
    he_c = sum(1 for r in results if r["exit_reason"] == "HOLD_EXPIRED")
    net_pnls = [r["net_pnl_pct"] for r in results]
    gross_pnls = [r["gross_pnl_pct"] for r in results]
    holds = [r["hold_bars"] for r in results]
    mae_rs = [r["mae_r"] for r in results]
    mfe_rs = [r["mfe_r"] for r in results]
    wins = [p for p in net_pnls if p > 0]
    losses = [p for p in net_pnls if p <= 0]

    # BE/+0.5R/+1R recovery
    be_count = sum(1 for r in results if r["mfe_r"] >= 0)
    half_r = sum(1 for r in results if r["mfe_r"] >= 0.5)
    one_r = sum(1 for r in results if r["mfe_r"] >= 1.0)

    s = {
        "label": label, "trades": n,
        "sl": sl_c, "tp": tp_c, "he": he_c,
        "sl_rate": sl_c / n * 100, "tp_rate": tp_c / n * 100,
        "win_rate": len(wins) / n * 100,
        "gross_exp": sum(gross_pnls) / n, "net_exp": sum(net_pnls) / n,
        "total_net": sum(net_pnls),
        "med_mae_r": sorted(mae_rs)[n//2], "med_mfe_r": sorted(mfe_rs)[n//2],
        "med_hold": sorted(holds)[n//2], "avg_hold": sum(holds) / n,
        "pf": abs(sum(wins) / sum(losses)) if losses and sum(losses) != 0 else float('inf'),
        "fd": ROUND_TRIP_BPS / 100 / (abs(sum(gross_pnls) / n) + 0.0001) * 100,
        "be_recovery": be_count / n * 100,
        "half_r_recovery": half_r / n * 100,
        "one_r_recovery": one_r / n * 100,
    }
    return s


def print_summary(s):
    if s["trades"] == 0:
        print(f"  [{s['label']}] No trades")
        return
    print(f"  [{s['label']}]")
    print(f"    Trades: {s['trades']}  SL: {s['sl']} ({s['sl_rate']:.1f}%)  TP: {s['tp']} ({s['tp_rate']:.1f}%)  HE: {s['he']}")
    print(f"    Win: {s['win_rate']:.1f}%  PF: {s['pf']:.3f}  Gross: {s['gross_exp']:.4f}%  Net: {s['net_exp']:.4f}%")
    print(f"    Total net: {s['total_net']:.2f}%  Fee drag: {s['fd']:.1f}%")
    print(f"    Med MAE/R: {s['med_mae_r']:.3f}  Med MFE/R: {s['med_mfe_r']:.3f}  Med hold: {s['med_hold']} bars")
    print(f"    BE: {s['be_recovery']:.1f}%  +0.5R: {s['half_r_recovery']:.1f}%  +1R: {s['one_r_recovery']:.1f}%")


def run_study():
    print("=" * 80)
    print("DOGE x AURORA @ 900s DEEP FOLLOW-UP STUDY")
    print("=" * 80)

    # === LOAD DATA ===
    bars_900 = load_900s_bars()
    bars_300 = load_300s_bars()
    alpha_regimes = load_alpha_regimes()

    if not bars_900:
        print("[FATAL] No 900s data")
        return

    # === REGIME RECONSTRUCTION ===
    # Strategy: For each 900s bar, find the closest 300s bar's regime (within 900s window)
    print("\n[REGIME RECONSTRUCTION]")

    regime_map_300 = {}
    for b in bars_300:
        if b["regime"] in ("MEAN_REVERSION", "LOW_VOLATILITY", "TREND_UP",
                           "TREND_DOWN", "HIGH_VOLATILITY", "UNCERTAIN"):
            regime_map_300[b["ts_ms"]] = (b["regime"], b["regime_conf"])

    print(f"  300s bars with resolved regime: {len(regime_map_300)}")
    print(f"  Alpha 900s regime labels: {len(alpha_regimes)}")

    # Enrich 900s bars
    closes = []
    highs = []
    lows = []
    enriched = []

    for i, bar in enumerate(bars_900):
        closes.append(bar["close"])
        highs.append(bar["high"])
        lows.append(bar["low"])

        atr = compute_atr(highs, lows, closes) if len(closes) > ATR_PERIOD else None
        sma_s = compute_sma(closes, SMA_SHORT) if len(closes) >= SMA_SHORT else None
        sma_l = compute_sma(closes, SMA_LONG) if len(closes) >= SMA_LONG else None

        # Regime: try alpha first, then 300s nearest, then compute
        ts = bar["ts_ms"]
        regime = None
        regime_conf = 0
        regime_source = "NONE"

        # 1. Alpha input (strongest)
        if ts in alpha_regimes:
            regime = alpha_regimes[ts]
            regime_conf = 0.5  # default conf
            regime_source = "ALPHA_INPUT"
        else:
            # 2. Nearest 300s bar within 900s window
            best_dist = 901000  # 901s in ms
            for delta in range(-900000, 901000, 300000):
                check_ts = ts + delta
                if check_ts in regime_map_300:
                    dist = abs(delta)
                    if dist < best_dist:
                        best_dist = dist
                        regime, regime_conf = regime_map_300[check_ts]
                        regime_source = "300S_NEAREST"

        # 3. Compute fallback
        if regime is None:
            regime, regime_conf = classify_macro_regime(closes, highs, lows, atr, sma_s, sma_l)
            regime_source = "COMPUTED"

        # Flat bucket
        bucket = classify_flat_bucket(atr, bar["close"])

        bar["atr"] = atr
        bar["sma_short"] = sma_s
        bar["sma_long"] = sma_l
        bar["macro_regime"] = regime
        bar["regime_conf"] = regime_conf
        bar["regime_source"] = regime_source
        bar["flat_bucket"] = bucket
        bar["bar_idx"] = i
        enriched.append(bar)

    # Regime source stats
    source_counts = Counter(b["regime_source"] for b in enriched)
    print(f"\n  Regime sources: {dict(source_counts)}")

    regime_counts = Counter(b["macro_regime"] for b in enriched if b["atr"] is not None)
    warmup = sum(1 for b in enriched if b["atr"] is None)
    mature = len(enriched) - warmup

    print(f"  Total bars: {len(enriched)}, Warmup: {warmup}, Mature: {mature}")
    print(f"\n  Regime distribution:")
    for r, c in sorted(regime_counts.items(), key=lambda x: -x[1]):
        print(f"    {r:25s}: {c:5d} ({c/mature*100:.1f}%)")

    # === SIGNAL GENERATION ===
    print("\n" + "=" * 60)
    print("AURORA-LIKE SIGNAL GENERATION @ 900s")
    print("=" * 60)

    signals = []
    cooldown_until = 0

    for i in range(max(20, ATR_PERIOD + 1, 15), len(enriched)):
        bar = enriched[i]
        if i < cooldown_until:
            continue
        if not bar.get("ready", True) and bar["atr"] is None:
            continue

        atr = bar["atr"]
        if atr is None:
            continue

        bb_u, bb_m, bb_l, bb_w = compute_bb(closes[:i+1])
        rsi = compute_rsi(closes[:i+1])
        sma20 = compute_sma(closes[:i+1], 20)
        sma20_dev = (bar["close"] - sma20) / sma20 if sma20 and sma20 > 0 else 0

        sig = aurora_composite_signal(bar, atr, bb_u, bb_m, bb_l, rsi, sma20_dev)
        if sig:
            sig["bar_idx"] = i
            sig["ts_ms"] = bar["ts_ms"]
            sig["datetime"] = bar["datetime"]
            sig["macro_regime"] = bar["macro_regime"]
            sig["regime_conf"] = bar["regime_conf"]
            sig["flat_bucket"] = bar["flat_bucket"]
            sig["regime_source"] = bar["regime_source"]
            signals.append(sig)
            cooldown_until = i + 1  # 1 bar cooldown (15 min)

    print(f"\n  Total signals: {len(signals)}")
    regime_dist = Counter(s["macro_regime"] for s in signals)
    for r, c in sorted(regime_dist.items(), key=lambda x: -x[1]):
        print(f"    {r:25s}: {c:5d}")
    dir_dist = Counter(s["type"] for s in signals)
    print(f"  Direction: {dict(dir_dist)}")

    # === BASELINE SIMULATION ===
    print("\n" + "=" * 60)
    print("BASELINE: DOGE x AURORA @ 900s (current config)")
    print("=" * 60)

    def run_sim(sigs, sl_m=1.0, tp_m=1.0, max_hold=24):
        results = []
        for sig in sigs:
            idx = sig["bar_idx"]
            if idx + 1 >= len(enriched):
                continue
            regime = sig["macro_regime"]
            r = simulate_trade(enriched, idx, sig, regime, sl_m, tp_m, max_hold)
            r["macro_regime"] = regime
            r["flat_bucket"] = sig["flat_bucket"]
            r["signal_datetime"] = sig["datetime"]
            r["score"] = sig["score"]
            results.append(r)
        return results

    baseline = run_sim(signals)
    s_base = summarize(baseline, "BASELINE_900")
    print_summary(s_base)

    # === REGIME-CONDITIONED ANALYSIS ===
    print("\n" + "=" * 60)
    print("REGIME-CONDITIONED ANALYSIS @ 900s")
    print("=" * 60)

    regime_summaries = {}
    for regime in sorted(set(r["macro_regime"] for r in baseline)):
        subset = [r for r in baseline if r["macro_regime"] == regime]
        if len(subset) >= 3:
            s = summarize(subset, f"REGIME:{regime}")
            regime_summaries[regime] = s
            print_summary(s)

    # Bucket analysis
    print("\n--- By Flat Bucket ---")
    bucket_summaries = {}
    for bucket in sorted(set(r["flat_bucket"] for r in baseline)):
        subset = [r for r in baseline if r["flat_bucket"] == bucket]
        if len(subset) >= 3:
            s = summarize(subset, f"BUCKET:{bucket}")
            bucket_summaries[bucket] = s
            print_summary(s)

    # === AURORA-NATIVE DIAGNOSTIC SLICES ===
    print("\n" + "=" * 60)
    print("AURORA-NATIVE DIAGNOSTIC SLICES")
    print("=" * 60)

    # Score bands
    score_bands = [(0.09, 0.2, "LOW"), (0.2, 0.4, "MEDIUM"), (0.4, 0.6, "HIGH"), (0.6, 1.0, "VERY_HIGH")]
    print("\n--- Score Bands ---")
    score_summaries = {}
    for lo, hi, name in score_bands:
        subset = [r for r, s in zip(baseline, signals) if lo <= s["score"] < hi]
        if len(subset) >= 3:
            ss = summarize(subset, f"SCORE:{name}({lo}-{hi})")
            score_summaries[name] = ss
            print_summary(ss)

    # Direction
    print("\n--- Direction ---")
    for d in ["BUY", "SELL"]:
        subset = [r for r in baseline if r["direction"] == d]
        if subset:
            ss = summarize(subset, f"DIR:{d}")
            print_summary(ss)

    # === CALIBRATION GRID ===
    print("\n" + "=" * 60)
    print("FEE-AWARE CALIBRATION GRID @ 900s")
    print("=" * 60)

    sl_mults = [0.75, 1.0, 1.25, 1.5]
    tp_mults = [0.5, 0.75, 1.0, 1.25]
    holds = [3, 6, 12, 24]

    cal_results = []
    for sl_m in sl_mults:
        for tp_m in tp_mults:
            for h in holds:
                res = run_sim(signals, sl_m, tp_m, h)
                s = summarize(res, f"SL{sl_m}_TP{tp_m}_H{h}")
                s["sl_mult"] = sl_m
                s["tp_mult"] = tp_m
                s["hold_bars"] = h
                cal_results.append(s)

    # Top 10
    cal_sorted = sorted(cal_results, key=lambda x: x.get("net_exp", -999), reverse=True)
    print("\n--- Top 10 Calibration Variants ---")
    for c in cal_sorted[:10]:
        print(f"  SL={c['sl_mult']} TP={c['tp_mult']} H={c['hold_bars']}: net={c['net_exp']:.4f}% trades={c['trades']} win={c['win_rate']:.1f}% pf={c['pf']:.3f}")

    # === STABILITY SPLIT ===
    print("\n" + "=" * 60)
    print("STABILITY VALIDATION")
    print("=" * 60)

    mid = len(signals) // 2
    h1_sigs = signals[:mid]
    h2_sigs = signals[mid:]

    h1_res = run_sim(h1_sigs)
    h2_res = run_sim(h2_sigs)
    s_h1 = summarize(h1_res, "FIRST_HALF")
    s_h2 = summarize(h2_res, "SECOND_HALF")
    print_summary(s_h1)
    print_summary(s_h2)

    both_positive = s_h1["net_exp"] > 0 and s_h2["net_exp"] > 0
    stability = "STABLE" if both_positive else "UNSTABLE"
    print(f"\n  Stability verdict: {stability}")
    print(f"    H1 net: {s_h1['net_exp']:.4f}%  H2 net: {s_h2['net_exp']:.4f}%")

    # Best calibrated stability
    if cal_sorted and cal_sorted[0]["net_exp"] > 0:
        best = cal_sorted[0]
        print(f"\n  Testing stability for best variant: SL={best['sl_mult']} TP={best['tp_mult']} H={best['hold_bars']}")
        bh1 = run_sim(h1_sigs, best["sl_mult"], best["tp_mult"], best["hold_bars"])
        bh2 = run_sim(h2_sigs, best["sl_mult"], best["tp_mult"], best["hold_bars"])
        sb1 = summarize(bh1, "BEST_H1")
        sb2 = summarize(bh2, "BEST_H2")
        print_summary(sb1)
        print_summary(sb2)
        best_stable = sb1["net_exp"] > 0 and sb2["net_exp"] > 0
        print(f"  Best variant stability: {'STABLE' if best_stable else 'UNSTABLE'}")

    # Walk-forward 3-way
    print("\n--- Walk-Forward 3-Way ---")
    third = len(signals) // 3
    wf_results = []
    for seg_i, (start, end) in enumerate([(0, third), (third, 2*third), (2*third, len(signals))]):
        seg = run_sim(signals[start:end])
        ss = summarize(seg, f"WF_SEG_{seg_i+1}")
        wf_results.append(ss)
        print_summary(ss)

    # === TESTNET CANDIDATE FILTER ===
    print("\n" + "=" * 60)
    print("TESTNET CANDIDATE FILTER")
    print("=" * 60)

    positive = s_base["net_exp"] > 0
    stable = stability == "STABLE"
    non_tiny = s_base["trades"] >= 30
    # Runtime plausible: Aurora doesn't support 900s without code change
    runtime_plausible = False  # aurora is hardcoded to 300s
    boundedness_reduced = source_counts.get("300S_NEAREST", 0) > source_counts.get("COMPUTED", 0)

    print(f"\n  1. Positive after costs:    {'PASS' if positive else 'FAIL'} (net_exp={s_base['net_exp']:.4f}%)")
    print(f"  2. Survives stability split: {'PASS' if stable else 'FAIL'}")
    print(f"  3. Non-trivially tiny:       {'PASS' if non_tiny else 'FAIL'} ({s_base['trades']} trades)")
    print(f"  4. Runtime/config plausible:  FAIL (Aurora hardcoded to 300s, requires code change)")
    print(f"  5. No hidden code hack:      {'PASS' if runtime_plausible else 'FAIL - needs aurora_handler.py TF gate change'}")
    print(f"  6. Boundedness reduced:       {'PARTIAL' if boundedness_reduced else 'MINIMAL'}")

    all_pass = positive and stable and non_tiny and runtime_plausible and boundedness_reduced
    if all_pass:
        verdict = "TESTNET_ENABLE_WORTHY_WITH_GUARDS"
    elif positive and non_tiny:
        verdict = "TESTNET_RESEARCH_ONLY_NO_RUNTIME_ENABLE"
    else:
        verdict = "NOT_READY_EVEN_FOR_TESTNET"

    print(f"\n  VERDICT: {verdict}")

    # === CHECK md_amr PATH (already at 900s) ===
    print("\n" + "=" * 60)
    print("ALTERNATIVE: DOGE via md_amr @ 900s (config-only path)")
    print("=" * 60)
    print("  md_amr already runs at 900s timeframe")
    print("  md_amr DOGE baseline from prior study: net_exp = -0.184%")
    print("  md_amr DOGE verdict: KEEP_DISABLED")
    print("  md_amr is not a viable path for DOGE at 900s")

    # === RUNTIME FEASIBILITY TABLE ===
    print("\n" + "=" * 60)
    print("RUNTIME ENABLEMENT SURFACES")
    print("=" * 60)

    surfaces = [
        ("Assignment", "config/aurora/strategies.yaml", "DOGE unassigned", "Add DOGEUSDT: [aurora]",
         "Strategy mismatch if aurora stays 300s", "YES"),
        ("Aurora TF gate", "aurora_handler.py:763", "Hardcoded tf_sec=300",
         "Add per-symbol TF override logic", "Non-trivial code change, risk of regression", "NO"),
        ("Aurora config", "aurora.yaml:DOGEUSDT", "timeframe_sec: null (falls back to 300)",
         "Set timeframe_sec: 900", "Config ready but handler ignores it", "YES"),
        ("Feature pipeline", "domains.yaml:131", "enabled_timeframes: [180,300,900]",
         "Already includes 900", "NONE - already active", "YES"),
        ("Bar aggregator", "trading.yaml:87", "timeframes: [180,300,900,14400,86400]",
         "Already includes 900", "NONE - already active", "YES"),
        ("Pending TTL", "domains.yaml:486", "900: 1800", "Already configured",
         "NONE", "YES"),
        ("Regime detector", "regime.yaml", "basis_tf_sec: 300",
         "Would need 900s basis or cross-TF regime", "Regime PENDING at 900s in recorder", "PARTIAL"),
    ]

    for s_name, s_file, s_current, s_change, s_risk, s_fc in surfaces:
        print(f"  {s_name:20s} | {s_file:30s} | Change: {s_change}")
        print(f"  {'':20s} | Current: {s_current}")
        print(f"  {'':20s} | Risk: {s_risk} | Fail-closed: {s_fc}")
        print()

    # === SAVE OUTPUT ===
    output = {
        "study_date": "2026-03-29",
        "study_type": "DOGE_AURORA_900s_DEEP_FOLLOWUP",
        "full_period": f"{enriched[0]['datetime']} to {enriched[-1]['datetime']}",
        "total_bars": len(enriched),
        "warmup_bars": warmup,
        "mature_bars": mature,
        "signals": len(signals),
        "regime_sources": dict(source_counts),
        "regime_distribution": dict(regime_counts),
        "baseline": s_base,
        "regime_summaries": regime_summaries,
        "bucket_summaries": bucket_summaries,
        "calibration_top10": cal_sorted[:10],
        "stability": {"h1": s_h1, "h2": s_h2, "verdict": stability},
        "testnet_filter": {
            "positive": positive, "stable": stable, "non_tiny": non_tiny,
            "runtime_plausible": runtime_plausible, "boundedness_reduced": boundedness_reduced,
        },
        "verdict": verdict,
        "cost_model": {"round_trip_bps": ROUND_TRIP_BPS},
    }

    out_path = BASE / "reports" / "DOGE_AURORA_900s_DEEP_FOLLOWUP_STUDY_2026-03-29.json"
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\n[OUTPUT] Saved to {out_path}")

    return output


if __name__ == "__main__":
    run_study()
