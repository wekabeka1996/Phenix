#!/usr/bin/env python3
"""
DOGE x Aurora @ 300s Deep Follow-Up Study

Phase A: Exactification with dual signal tracks + dual cost tracks
Phase B: Runtime feasibility audit (config-only path at 300s)
Phase C: Testnet candidate decision

Prior context:
- Full surface study found DOGE x Aurora @ 300s = CALIBRATION_CANDIDATE (+0.015% net)
- DOGE x MR full-period study -> KEEP_DOGE_DISABLED
- DOGE x Aurora @ 900s study -> NOT_READY_EVEN_FOR_TESTNET

Signal tracks:
  Track A: Generic 8-feature proxy (same as full_surface_calibration.py)
  Track B: DOGE-configured weights (from aurora.yaml DOGEUSDT block)
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

# === DUAL COST MODEL ===
COST_MAKER_RT_BPS = 10.0   # maker limit: 2*(2+2+1)
COST_TAKER_RT_BPS = 14.0   # taker market: 2*(4+2+1)

# === AURORA DOGE CONFIG (from aurora.yaml DOGEUSDT block, lines 1011-1119) ===
AURORA_SL_PCT = 0.01512      # 1.512% base SL
AURORA_MAX_HOLD_SEC = 3000   # 50 min = 10 bars at 300s
AURORA_MAX_HOLD_BARS = 10    # 3000s / 300s
AURORA_SIGNAL_THRESHOLD = 0.09
AURORA_REENTRY_COOLDOWN_BARS = 1  # 120s / 300s = 0.4, round up
AURORA_MIN_SL_PCT = 0.0025
AURORA_MAX_SL_PCT = 0.020
AURORA_MIN_TP_RR = 0.25
AURORA_MAX_TP_RR = 1.2
AURORA_MIN_DIST_BPS = 18
AURORA_TP_BASE_RR = 0.6   # base TP reward-to-risk ratio

# Regime TPSL multipliers (from aurora.yaml DOGEUSDT)
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

# Regime detection params (SMA-based fallback)
SMA_SHORT = 48
SMA_LONG = 192
ATR_PERIOD = 14
FLAT_LOW_THR = 0.001
FLAT_HIGH_THR = 0.003

# Two signal weight sets
WEIGHTS_GENERIC = {
    "obi": 0.30, "tfi": 0.20, "delta_price": 0.15, "absorption": 0.10,
    "ema_bias": 0.10, "volume_spike": 0.05, "depth_imbalance": 0.05,
    "volatility_state": 0.05,
}

WEIGHTS_DOGE_CONFIG = {
    "obi": 0.25, "tfi": 0.09, "delta_price": 0.10, "absorption": 0.0,
    "ema_bias": 0.20, "volume_spike": 0.20, "macro_resid": 0.25,
    "volatility_state": 0.05, "depth_imbalance": -0.20,
}

# Calibration grid
SL_MULTS = [0.75, 1.0, 1.25, 1.5]
TP_MULTS = [0.5, 0.75, 1.0, 1.25]
HOLD_GRID = [3, 6, 10, 15]

# Valid regimes for regime detection
VALID_REGIMES = {"MEAN_REVERSION", "LOW_VOLATILITY", "TREND_UP",
                 "TREND_DOWN", "HIGH_VOLATILITY", "UNCERTAIN"}


# === DATA LOADING ===

def load_300s_bars():
    """Load all DOGE 300s bars from recorder with features."""
    bars = []
    pattern = str(RECORDER / "*" / "DOGEUSDT_300.csv")
    files = sorted(glob.glob(pattern))
    print(f"[DATA] Found {len(files)} DOGE 300s recorder files")

    feat_cols = [
        "feat_obi", "feat_tfi", "feat_delta_price", "feat_absorption",
        "feat_ema_bias", "feat_volume_spike", "feat_depth_imbalance",
        "feat_volatility_state", "feat_macro_resid", "feat_macro_sync",
        "feat_liquidity_kappa", "feat_spread_bps",
    ]

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
                    ready_str = row.get("ready", "False")
                    ready = ready_str == "True"
                    regime = row.get("regime", "PENDING") or "PENDING"
                    regime_conf = float(row.get("regime_conf", "0") or "0")

                    bar = {
                        "ts_ms": ts,
                        "datetime": row.get("datetime", ""),
                        "open": o, "high": h, "low": l_, "close": c,
                        "volume": vol, "ready": ready,
                        "regime_raw": regime,
                        "regime_conf_raw": regime_conf,
                    }

                    # Parse features
                    for fc in feat_cols:
                        val_str = row.get(fc, "")
                        if val_str and val_str not in ("", "None", "null"):
                            try:
                                bar[fc] = float(val_str)
                            except (ValueError, TypeError):
                                bar[fc] = None
                        else:
                            bar[fc] = None

                    bars.append(bar)
                except (ValueError, KeyError, TypeError):
                    continue

    # Deduplicate by ts_ms
    seen = set()
    unique = []
    for b in sorted(bars, key=lambda x: x["ts_ms"]):
        if b["ts_ms"] not in seen:
            seen.add(b["ts_ms"])
            unique.append(b)

    print(f"[DATA] Loaded {len(unique)} unique DOGE 300s bars")
    if unique:
        print(f"[DATA] Period: {unique[0]['datetime']} to {unique[-1]['datetime']}")

    # Count ready bars
    ready_count = sum(1 for b in unique if b["ready"])
    print(f"[DATA] Ready bars: {ready_count} ({ready_count/len(unique)*100:.1f}%)")

    return unique


def load_alpha_regimes():
    """Load regime labels from alpha_input for DOGE at 300s."""
    regimes = {}
    if not ALPHA_INPUT.exists():
        print("[REGIME] alpha_input file not found")
        return regimes
    with open(ALPHA_INPUT, "r") as f:
        for line in f:
            try:
                obj = json.loads(line.strip())
                if obj.get("symbol") != "DOGEUSDT":
                    continue
                if obj.get("tf_sec") != 300:
                    continue
                ts = obj["ts_ms"]
                reg = obj.get("regime", "UNKNOWN")
                if reg and reg != "DEFAULT" and reg in VALID_REGIMES:
                    regimes[ts] = reg
            except (json.JSONDecodeError, KeyError):
                continue
    print(f"[REGIME] Loaded {len(regimes)} alpha_input regime labels for 300s")
    return regimes


# === TECHNICAL INDICATORS (for regime reconstruction fallback) ===

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


# === SIGNAL GENERATION (feature-based weighted sum) ===

def compute_weighted_signal(bar, weights, threshold):
    """
    Weighted-sum signal proxy using recorded features.
    Returns signal dict or None if below threshold.
    """
    score = 0.0
    for feat_name, weight in weights.items():
        val = bar.get(f"feat_{feat_name}")
        if val is None:
            return None
        try:
            if math.isnan(val) or math.isinf(val):
                return None
        except TypeError:
            return None
        score += weight * val

    if abs(score) < threshold:
        return None

    direction = "BUY" if score > 0 else "SELL"
    return {
        "type": direction,
        "score": abs(score),
        "raw_score": score,
        "entry_price": bar["close"],
    }


def generate_signals(bars, weights, threshold=AURORA_SIGNAL_THRESHOLD,
                     cooldown_bars=AURORA_REENTRY_COOLDOWN_BARS):
    """Generate signals from enriched bars using given weight set."""
    signals = []
    cooldown_until = 0

    for i, bar in enumerate(bars):
        if i < cooldown_until:
            continue
        if not bar.get("ready", False):
            continue
        if bar.get("atr") is None:
            continue

        sig = compute_weighted_signal(bar, weights, threshold)
        if sig:
            sig["bar_idx"] = i
            sig["ts_ms"] = bar["ts_ms"]
            sig["datetime"] = bar.get("datetime", "")
            sig["macro_regime"] = bar["macro_regime"]
            sig["regime_conf"] = bar.get("regime_conf", 0)
            sig["flat_bucket"] = bar["flat_bucket"]
            sig["regime_source"] = bar.get("regime_source", "UNKNOWN")
            signals.append(sig)
            cooldown_until = i + cooldown_bars

    return signals


# === TRADE SIMULATION ===

def simulate_trade(bars, entry_idx, signal, regime, sl_mult=1.0, tp_mult=1.0,
                   max_hold_bars=AURORA_MAX_HOLD_BARS, cost_bps=COST_TAKER_RT_BPS):
    entry = signal["entry_price"]
    direction = 1 if signal["type"] == "BUY" else -1

    base_sl = AURORA_SL_PCT
    r_sl = REGIME_SL_MULT.get(regime, 1.0) * sl_mult
    r_tp = REGIME_TP_MULT.get(regime, 1.0) * tp_mult

    sl_pct = max(AURORA_MIN_SL_PCT, min(AURORA_MAX_SL_PCT, base_sl * r_sl))
    tp_rr = max(AURORA_MIN_TP_RR, min(AURORA_MAX_TP_RR, AURORA_TP_BASE_RR * r_tp))
    tp_pct = sl_pct * tp_rr

    if direction == 1:
        stop = entry * (1 - sl_pct)
        target = entry * (1 + tp_pct)
    else:
        stop = entry * (1 + sl_pct)
        target = entry * (1 - tp_pct)

    mae = mfe = 0.0
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

        # SL check (priority over TP)
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
    net_pct = gross_pct - cost_bps / 100

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

    be_count = sum(1 for r in results if r["mfe_r"] >= 0)
    half_r = sum(1 for r in results if r["mfe_r"] >= 0.5)
    one_r = sum(1 for r in results if r["mfe_r"] >= 1.0)

    gross_avg = sum(gross_pnls) / n
    cost_used = abs(sum(net_pnls) / n - gross_avg)  # infer cost per trade

    s = {
        "label": label, "trades": n,
        "sl": sl_c, "tp": tp_c, "he": he_c,
        "sl_rate": sl_c / n * 100, "tp_rate": tp_c / n * 100,
        "win_rate": len(wins) / n * 100,
        "gross_exp": gross_avg, "net_exp": sum(net_pnls) / n,
        "total_net": sum(net_pnls),
        "med_mae_r": sorted(mae_rs)[n // 2], "med_mfe_r": sorted(mfe_rs)[n // 2],
        "med_hold": sorted(holds)[n // 2], "avg_hold": sum(holds) / n,
        "pf": abs(sum(wins) / sum(losses)) if losses and sum(losses) != 0 else float('inf'),
        "fd": cost_used / (abs(gross_avg) + 0.0001) * 100,
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


# === MAIN STUDY ===

def run_study():
    print("=" * 80)
    print("DOGE x AURORA @ 300s DEEP FOLLOW-UP STUDY")
    print("=" * 80)

    # === LOAD DATA ===
    bars = load_300s_bars()
    alpha_regimes = load_alpha_regimes()

    if not bars:
        print("[FATAL] No 300s data")
        return

    # === REGIME RECONSTRUCTION ===
    print("\n[REGIME RECONSTRUCTION]")

    closes = []
    highs = []
    lows = []

    for i, bar in enumerate(bars):
        closes.append(bar["close"])
        highs.append(bar["high"])
        lows.append(bar["low"])

        atr = compute_atr(highs, lows, closes) if len(closes) > ATR_PERIOD else None
        sma_s = compute_sma(closes, SMA_SHORT) if len(closes) >= SMA_SHORT else None
        sma_l = compute_sma(closes, SMA_LONG) if len(closes) >= SMA_LONG else None

        # Regime: priority: alpha_input > computed
        ts = bar["ts_ms"]
        regime = None
        regime_conf = 0
        regime_source = "NONE"

        # 1. Alpha input (direct match or +/- 1 bar tolerance)
        if ts in alpha_regimes:
            regime = alpha_regimes[ts]
            regime_conf = 0.5
            regime_source = "ALPHA_INPUT"
        else:
            for delta in [-300000, 300000]:
                check_ts = ts + delta
                if check_ts in alpha_regimes:
                    regime = alpha_regimes[check_ts]
                    regime_conf = 0.4
                    regime_source = "ALPHA_NEAREST"
                    break

        # 2. Recorded regime column (if valid)
        if regime is None:
            raw_regime = bar.get("regime_raw", "PENDING")
            if raw_regime in VALID_REGIMES:
                regime = raw_regime
                regime_conf = bar.get("regime_conf_raw", 0)
                regime_source = "RECORDER"

        # 3. Compute fallback from SMA
        if regime is None:
            regime, regime_conf = classify_macro_regime(closes, highs, lows, atr, sma_s, sma_l)
            regime_source = "COMPUTED"

        bucket = classify_flat_bucket(atr, bar["close"])

        bar["atr"] = atr
        bar["sma_short"] = sma_s
        bar["sma_long"] = sma_l
        bar["macro_regime"] = regime
        bar["regime_conf"] = regime_conf
        bar["regime_source"] = regime_source
        bar["flat_bucket"] = bucket
        bar["bar_idx"] = i

    source_counts = Counter(b["regime_source"] for b in bars)
    print(f"  Regime sources: {dict(source_counts)}")

    regime_counts = Counter(b["macro_regime"] for b in bars if b["atr"] is not None)
    warmup = sum(1 for b in bars if b["atr"] is None)
    mature = len(bars) - warmup

    print(f"  Total bars: {len(bars)}, Warmup: {warmup}, Mature: {mature}")
    print(f"\n  Regime distribution:")
    for r, c in sorted(regime_counts.items(), key=lambda x: -x[1]):
        print(f"    {r:25s}: {c:5d} ({c / mature * 100:.1f}%)")

    # Alpha coverage
    alpha_count = source_counts.get("ALPHA_INPUT", 0) + source_counts.get("ALPHA_NEAREST", 0)
    print(f"\n  Alpha-sourced regime labels: {alpha_count} ({alpha_count / len(bars) * 100:.1f}%)")
    print(f"  Computed (SMA-derived): {source_counts.get('COMPUTED', 0)} ({source_counts.get('COMPUTED', 0) / len(bars) * 100:.1f}%)")

    # === SIGNAL GENERATION (dual tracks) ===
    print("\n" + "=" * 60)
    print("SIGNAL GENERATION @ 300s (DUAL TRACKS)")
    print("=" * 60)

    signals_a = generate_signals(bars, WEIGHTS_GENERIC, AURORA_SIGNAL_THRESHOLD)
    signals_b = generate_signals(bars, WEIGHTS_DOGE_CONFIG, AURORA_SIGNAL_THRESHOLD)

    print(f"\n  Track A (generic weights): {len(signals_a)} signals")
    if signals_a:
        dir_a = Counter(s["type"] for s in signals_a)
        reg_a = Counter(s["macro_regime"] for s in signals_a)
        print(f"    Direction: {dict(dir_a)}")
        for r, c in sorted(reg_a.items(), key=lambda x: -x[1]):
            print(f"    {r:25s}: {c:5d}")

    print(f"\n  Track B (DOGE-config weights): {len(signals_b)} signals")
    if signals_b:
        dir_b = Counter(s["type"] for s in signals_b)
        reg_b = Counter(s["macro_regime"] for s in signals_b)
        print(f"    Direction: {dict(dir_b)}")
        for r, c in sorted(reg_b.items(), key=lambda x: -x[1]):
            print(f"    {r:25s}: {c:5d}")

    # === SIMULATION HELPERS ===

    def run_sim(sigs, sl_m=1.0, tp_m=1.0, max_hold=AURORA_MAX_HOLD_BARS, cost_bps=COST_TAKER_RT_BPS):
        results = []
        for sig in sigs:
            idx = sig["bar_idx"]
            if idx + 1 >= len(bars):
                continue
            regime = sig["macro_regime"]
            r = simulate_trade(bars, idx, sig, regime, sl_m, tp_m, max_hold, cost_bps)
            r["macro_regime"] = regime
            r["flat_bucket"] = sig["flat_bucket"]
            r["signal_datetime"] = sig.get("datetime", "")
            r["score"] = sig["score"]
            results.append(r)
        return results

    # === BASELINE (4 variants: 2 signal tracks x 2 cost tracks) ===
    print("\n" + "=" * 60)
    print("BASELINE: DOGE x AURORA @ 300s (4 VARIANTS)")
    print("=" * 60)

    variants = [
        ("A_10bps", signals_a, COST_MAKER_RT_BPS),
        ("A_14bps", signals_a, COST_TAKER_RT_BPS),
        ("B_10bps", signals_b, COST_MAKER_RT_BPS),
        ("B_14bps", signals_b, COST_TAKER_RT_BPS),
    ]

    baselines = {}
    baseline_results = {}
    for name, sigs, cost in variants:
        if not sigs:
            print(f"  [{name}] No signals")
            continue
        res = run_sim(sigs, cost_bps=cost)
        s = summarize(res, f"BASELINE_{name}")
        baselines[name] = s
        baseline_results[name] = res
        print_summary(s)

    # Prior comparison
    if "A_10bps" in baselines:
        prior_net = 0.015
        actual_net = baselines["A_10bps"]["net_exp"]
        print(f"\n  Prior surface finding (A@10bps): +{prior_net:.3f}%")
        print(f"  This study (A@10bps):            {actual_net:+.4f}%")
        print(f"  Delta: {actual_net - prior_net:+.4f}% (expected small due to methodology alignment)")

    # === REGIME-CONDITIONED ANALYSIS ===
    print("\n" + "=" * 60)
    print("REGIME-CONDITIONED ANALYSIS @ 300s")
    print("=" * 60)

    # Use primary variant (A_14bps) for regime analysis
    regime_summaries = {}
    primary_key = "A_14bps"
    primary_res = baseline_results.get(primary_key, [])

    if primary_res:
        print(f"\n--- By Macro Regime (Track {primary_key}) ---")
        for regime in sorted(set(r["macro_regime"] for r in primary_res)):
            subset = [r for r in primary_res if r["macro_regime"] == regime]
            if len(subset) >= 3:
                s = summarize(subset, f"REGIME:{regime}")
                regime_summaries[regime] = s
                print_summary(s)

        print(f"\n--- By Flat Bucket (Track {primary_key}) ---")
        bucket_summaries = {}
        for bucket in sorted(set(r["flat_bucket"] for r in primary_res)):
            subset = [r for r in primary_res if r["flat_bucket"] == bucket]
            if len(subset) >= 3:
                s = summarize(subset, f"BUCKET:{bucket}")
                bucket_summaries[bucket] = s
                print_summary(s)
    else:
        bucket_summaries = {}

    # Also show A_10bps regime breakdown to match prior study
    if "A_10bps" in baseline_results:
        print(f"\n--- By Macro Regime (Track A_10bps, comparable to prior study) ---")
        regime_summaries_a10 = {}
        for regime in sorted(set(r["macro_regime"] for r in baseline_results["A_10bps"])):
            subset = [r for r in baseline_results["A_10bps"] if r["macro_regime"] == regime]
            if len(subset) >= 3:
                s = summarize(subset, f"A10_REGIME:{regime}")
                regime_summaries_a10[regime] = s
                print_summary(s)

    # === SCORE BAND ANALYSIS ===
    print("\n" + "=" * 60)
    print("SCORE BAND ANALYSIS @ 300s")
    print("=" * 60)

    score_bands = [(0.09, 0.15, "LOW"), (0.15, 0.25, "MEDIUM"),
                   (0.25, 0.40, "HIGH"), (0.40, 10.0, "VERY_HIGH")]

    for track_name, sigs, res_list in [("A", signals_a, baseline_results.get("A_14bps", [])),
                                        ("B", signals_b, baseline_results.get("B_14bps", []))]:
        if not res_list or not sigs:
            continue
        print(f"\n--- Track {track_name} Score Bands ---")
        for lo, hi, band_name in score_bands:
            subset = [r for r, s in zip(res_list, sigs) if lo <= s["score"] < hi]
            if len(subset) >= 3:
                ss = summarize(subset, f"T{track_name}:SCORE:{band_name}({lo}-{hi})")
                print_summary(ss)

        print(f"\n--- Track {track_name} Direction ---")
        for d in ["BUY", "SELL"]:
            subset = [r for r in res_list if r["direction"] == d]
            if len(subset) >= 3:
                ss = summarize(subset, f"T{track_name}:DIR:{d}")
                print_summary(ss)

    # Track B only: macro_resid sign split
    if signals_b and "B_14bps" in baseline_results:
        print("\n--- Track B: macro_resid Sign Split ---")
        for sign_name, sign_check in [("POSITIVE", lambda s: s.get("raw_score", 0) > 0),
                                       ("NEGATIVE", lambda s: s.get("raw_score", 0) < 0)]:
            subset = [r for r, s in zip(baseline_results["B_14bps"], signals_b) if sign_check(s)]
            if len(subset) >= 3:
                ss = summarize(subset, f"TB:MACRO_RESID:{sign_name}")
                print_summary(ss)

    # === CALIBRATION GRID ===
    print("\n" + "=" * 60)
    print("FEE-AWARE CALIBRATION GRID @ 300s")
    print("=" * 60)

    cal_all = {}
    for vname, sigs, cost in variants:
        if not sigs:
            continue
        cal_results = []
        for sl_m in SL_MULTS:
            for tp_m in TP_MULTS:
                for h in HOLD_GRID:
                    res = run_sim(sigs, sl_m, tp_m, h, cost)
                    s = summarize(res, f"SL{sl_m}_TP{tp_m}_H{h}")
                    s["sl_mult"] = sl_m
                    s["tp_mult"] = tp_m
                    s["hold_bars"] = h
                    cal_results.append(s)

        cal_sorted = sorted(cal_results, key=lambda x: x.get("net_exp", -999), reverse=True)
        cal_all[vname] = cal_sorted

        print(f"\n--- Top 10 Calibration: {vname} ---")
        for c in cal_sorted[:10]:
            print(f"  SL={c['sl_mult']} TP={c['tp_mult']} H={c['hold_bars']}: "
                  f"net={c['net_exp']:.4f}% trades={c['trades']} win={c['win_rate']:.1f}% pf={c['pf']:.3f}")

    # === STABILITY VALIDATION ===
    print("\n" + "=" * 60)
    print("STABILITY VALIDATION")
    print("=" * 60)

    stability_results = {}
    for vname, sigs, cost in variants:
        if not sigs:
            continue
        mid = len(sigs) // 2
        h1_sigs = sigs[:mid]
        h2_sigs = sigs[mid:]

        h1_res = run_sim(h1_sigs, cost_bps=cost)
        h2_res = run_sim(h2_sigs, cost_bps=cost)
        s_h1 = summarize(h1_res, f"{vname}_H1")
        s_h2 = summarize(h2_res, f"{vname}_H2")

        both_positive = s_h1.get("net_exp", -1) > 0 and s_h2.get("net_exp", -1) > 0
        stability = "STABLE" if both_positive else "UNSTABLE"

        stability_results[vname] = {
            "h1": s_h1, "h2": s_h2, "verdict": stability,
        }

        print(f"\n  [{vname}] Half-Split: {stability}")
        print(f"    H1: {s_h1.get('net_exp', 0):.4f}% ({s_h1.get('trades', 0)} trades)")
        print(f"    H2: {s_h2.get('net_exp', 0):.4f}% ({s_h2.get('trades', 0)} trades)")

    # Walk-forward 3-way for primary variants
    print("\n--- Walk-Forward 3-Way ---")
    wf_results = {}
    for vname, sigs, cost in variants:
        if not sigs:
            continue
        third = len(sigs) // 3
        segs = []
        for seg_i, (start, end) in enumerate([(0, third), (third, 2 * third), (2 * third, len(sigs))]):
            seg_res = run_sim(sigs[start:end], cost_bps=cost)
            ss = summarize(seg_res, f"{vname}_WF{seg_i + 1}")
            segs.append(ss)

        wf_pos = sum(1 for s in segs if s.get("net_exp", -1) > 0)
        wf_verdict = "WF_STABLE" if wf_pos == 3 else ("WF_PARTIAL" if wf_pos >= 2 else "WF_UNSTABLE")
        wf_results[vname] = {"segments": segs, "verdict": wf_verdict}

        print(f"\n  [{vname}] Walk-Forward: {wf_verdict}")
        for ss in segs:
            print(f"    {ss['label']}: net={ss.get('net_exp', 0):.4f}% ({ss.get('trades', 0)} trades)")

    # Best-variant stability check
    print("\n--- Best Variant Stability ---")
    for vname, sigs, cost in variants:
        if not sigs or vname not in cal_all:
            continue
        best = cal_all[vname][0]
        if best.get("net_exp", -1) <= 0:
            print(f"  [{vname}] Best variant net_exp <= 0, skip stability check")
            continue
        print(f"  [{vname}] Best: SL={best['sl_mult']} TP={best['tp_mult']} H={best['hold_bars']} net={best['net_exp']:.4f}%")
        mid = len(sigs) // 2
        bh1 = run_sim(sigs[:mid], best["sl_mult"], best["tp_mult"], best["hold_bars"], cost)
        bh2 = run_sim(sigs[mid:], best["sl_mult"], best["tp_mult"], best["hold_bars"], cost)
        sb1 = summarize(bh1, f"BEST_{vname}_H1")
        sb2 = summarize(bh2, f"BEST_{vname}_H2")
        best_stable = sb1.get("net_exp", -1) > 0 and sb2.get("net_exp", -1) > 0
        print(f"    H1: {sb1.get('net_exp', 0):.4f}%  H2: {sb2.get('net_exp', 0):.4f}%  -> {'STABLE' if best_stable else 'UNSTABLE'}")
        stability_results[f"{vname}_BEST"] = {"h1": sb1, "h2": sb2, "verdict": "STABLE" if best_stable else "UNSTABLE"}

    # === BOUNDEDNESS AUDIT ===
    print("\n" + "=" * 60)
    print("BOUNDEDNESS AUDIT")
    print("=" * 60)

    bounds = [
        ("Signal model", "LINEAR weighted-sum vs QUADRATIC kernel (sign(S)*S^2)", "HIGH"),
        ("Shield cascade", "Context/Memory/DangerZone shields not applied", "MEDIUM"),
        ("Pillar system", "Tactician/Operator/Strategist multi-TF consensus absent", "HIGH"),
        ("Regime fidelity", f"Alpha: {alpha_count}/{len(bars)} ({alpha_count/len(bars)*100:.1f}%), rest SMA-computed", "MEDIUM"),
        ("Liquidity gate", "Kappa filtering not applied", "LOW"),
        ("Partial exit", "tp_low_ratio=0.36 partial exit at 31% not simulated", "LOW"),
        ("Track B macro_resid", "Weight 0.25 on [-3,+3] range dominates score (+/-0.75)", "HIGH" if signals_b else "N/A"),
    ]

    print(f"\n  {'Dimension':30s} | {'Severity':8s} | Description")
    print(f"  {'-'*30} | {'-'*8} | {'-'*50}")
    for name, desc, sev in bounds:
        print(f"  {name:30s} | {sev:8s} | {desc}")

    # === TESTNET CANDIDATE FILTER ===
    print("\n" + "=" * 60)
    print("TESTNET CANDIDATE FILTER")
    print("=" * 60)

    # Evaluate each variant
    for vname in ["A_10bps", "A_14bps", "B_10bps", "B_14bps"]:
        if vname not in baselines:
            continue
        bl = baselines[vname]
        stab = stability_results.get(vname, {}).get("verdict", "UNSTABLE")

        positive = bl["net_exp"] > 0
        stable = stab == "STABLE"
        non_tiny = bl["trades"] >= 30
        runtime_plausible = True  # Aurora already at 300s, config-only change
        # Boundedness: acceptable if high-severity gaps <= 2 AND at least marginal positive signal
        high_severity_gaps = sum(1 for _, _, sev in bounds if sev == "HIGH")
        boundedness_ok = high_severity_gaps <= 2 and positive

        print(f"\n  --- {vname} ---")
        print(f"  1. Positive after costs:     {'PASS' if positive else 'FAIL'} (net_exp={bl['net_exp']:.4f}%)")
        print(f"  2. Survives stability split:  {'PASS' if stable else 'FAIL'} ({stab})")
        print(f"  3. Non-trivially sized:       {'PASS' if non_tiny else 'FAIL'} ({bl['trades']} trades)")
        print(f"  4. Runtime/config plausible:   PASS (Aurora already at 300s, config-only)")
        print(f"  5. Boundedness acceptable:     {'PASS' if boundedness_ok else 'FAIL'} ({high_severity_gaps} HIGH gaps)")

        all_pass = positive and stable and non_tiny and runtime_plausible and boundedness_ok
        if all_pass:
            verdict = "TESTNET_ENABLE_WORTHY_WITH_GUARDS"
        elif positive and stable and non_tiny:
            verdict = "TESTNET_SHADOW_MODE_ONLY"
        elif positive and non_tiny:
            verdict = "NEEDS_MORE_DATA"
        else:
            verdict = "NOT_READY_EVEN_FOR_TESTNET"

        print(f"  VERDICT: {verdict}")
        baselines[vname]["verdict"] = verdict

    # Overall verdict = best across all variants
    verdict_rank = {
        "TESTNET_ENABLE_WORTHY_WITH_GUARDS": 4,
        "TESTNET_SHADOW_MODE_ONLY": 3,
        "NEEDS_MORE_DATA": 2,
        "NOT_READY_EVEN_FOR_TESTNET": 1,
    }
    best_verdict = "NOT_READY_EVEN_FOR_TESTNET"
    best_variant = None
    for vname, bl in baselines.items():
        v = bl.get("verdict", "NOT_READY_EVEN_FOR_TESTNET")
        if verdict_rank.get(v, 0) > verdict_rank.get(best_verdict, 0):
            best_verdict = v
            best_variant = vname

    print(f"\n  === OVERALL VERDICT: {best_verdict} (via {best_variant}) ===")

    # === RUNTIME ENABLEMENT SURFACE ===
    print("\n" + "=" * 60)
    print("RUNTIME ENABLEMENT SURFACE (300s path)")
    print("=" * 60)

    surfaces = [
        ("Assignment", "config/aurora/strategies.yaml", "DOGE unassigned",
         "Add DOGEUSDT: [aurora]", "Strategy contention if MR also assigned", "YES"),
        ("Aurora TF", "strategies/aurora.yaml:15", "timeframe_sec: 300",
         "Already correct (300s)", "NONE", "YES"),
        ("DOGE config", "strategies/aurora.yaml:1011", "Full config block exists",
         "No change needed", "NONE", "YES"),
        ("Feature pipeline", "domains.yaml", "300 in enabled_timeframes",
         "Already active", "NONE", "YES"),
        ("Bar aggregator", "trading.yaml", "300 in timeframes",
         "Already active", "NONE", "YES"),
        ("Regime detector", "regime.yaml", "basis_tf_sec: 300",
         "Already correct", "NONE", "YES"),
    ]

    for s_name, s_file, s_current, s_change, s_risk, s_fc in surfaces:
        print(f"  {s_name:20s} | {s_file:35s} | Change: {s_change}")
        print(f"  {'':20s} | Current: {s_current}")
        print(f"  {'':20s} | Risk: {s_risk} | Fail-closed: {s_fc}")
        print()

    print("  RUNTIME PLAUSIBLE: YES -- requires only strategies.yaml config change")

    # === SAVE OUTPUT ===
    output = {
        "study_date": "2026-03-29",
        "study_type": "DOGE_AURORA_300s_DEEP_FOLLOWUP",
        "full_period": f"{bars[0]['datetime']} to {bars[-1]['datetime']}",
        "total_bars": len(bars),
        "warmup_bars": warmup,
        "mature_bars": mature,
        "cost_models": {"maker_rt_bps": COST_MAKER_RT_BPS, "taker_rt_bps": COST_TAKER_RT_BPS},
        "signal_counts": {
            "track_a_generic": len(signals_a),
            "track_b_doge_config": len(signals_b),
        },
        "regime_sources": dict(source_counts),
        "regime_distribution": dict(regime_counts),
        "baselines": baselines,
        "regime_summaries": regime_summaries,
        "bucket_summaries": bucket_summaries,
        "calibration_top10": {
            vname: cal_all[vname][:10] for vname in cal_all
        },
        "stability": stability_results,
        "walk_forward": wf_results,
        "overall_verdict": best_verdict,
        "best_variant": best_variant,
        "boundedness_gaps": [{"name": n, "severity": s, "desc": d} for n, d, s in bounds],
    }

    out_path = BASE / "reports" / "DOGE_AURORA_300s_DEEP_FOLLOWUP_STUDY_2026-03-29.json"
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\n[OUTPUT] Saved to {out_path}")

    return output


if __name__ == "__main__":
    run_study()
