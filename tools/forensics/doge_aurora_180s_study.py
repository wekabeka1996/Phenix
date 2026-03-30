#!/usr/bin/env python3
"""
DOGE x Aurora @ 180s Deep Follow-Up Study + Pipeline Method Audit

Surface Classification: NATIVE_RESEARCH_ONLY
  - 180s bars ARE natively recorded (50 files)
  - FE DOES compute features for 180s (enabled_timeframes_sec: [180, 300, 900])
  - BUT: No strategy handler consumes 180s (Aurora gates on 300s)
  - Regime detector gates on 300s, ignores 180s
  - Pillars use 900/14400/86400, not 180s

This study evaluates the SYNTHETIC analytical surface only.
No result from this study can be directly operationalized without code changes.

Signal tracks:
  Track A: Generic 8-feature proxy (same as full_surface_calibration.py)
  Track B: DOGE-configured weights (from aurora.yaml DOGEUSDT block)

Pipeline audit sections embedded throughout.
"""

import csv
import json
import os
import glob
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from datetime import datetime

BASE = Path(r"c:\Users\user\Music\Phenix")
RECORDER = BASE / "data" / "recorder"
ALPHA_INPUT = BASE / "logs" / "alpha_input" / "alpha_input_v1.jsonl"

# === DUAL COST MODEL ===
COST_MAKER_RT_BPS = 10.0   # maker limit: 2*(2+2+1)
COST_TAKER_RT_BPS = 14.0   # taker market: 2*(4+2+1)

# === AURORA DOGE CONFIG (from aurora.yaml DOGEUSDT block, lines 1011-1119) ===
AURORA_SL_PCT = 0.01512      # 1.512% base SL
AURORA_MAX_HOLD_SEC = 3000   # 50 min
# At 180s: 3000/180 = 16.67 -> 17 bars (round up to not cut short)
AURORA_MAX_HOLD_BARS_180 = 17
# At 300s equivalent for comparison: 3000/300 = 10
AURORA_MAX_HOLD_BARS_300 = 10
AURORA_SIGNAL_THRESHOLD = 0.09
AURORA_REENTRY_COOLDOWN_SEC = 120  # 120/180 = 0.67 -> 1 bar cooldown
AURORA_REENTRY_COOLDOWN_BARS = 1
AURORA_MIN_SL_PCT = 0.0025
AURORA_MAX_SL_PCT = 0.020
AURORA_MIN_TP_RR = 0.25
AURORA_MAX_TP_RR = 1.2
AURORA_MIN_DIST_BPS = 18
AURORA_TP_BASE_RR = 0.6

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

SL_MULTS = [0.75, 1.0, 1.25, 1.5]
TP_MULTS = [0.5, 0.75, 1.0, 1.25]
HOLD_GRID = [5, 10, 17, 25]  # 180s-appropriate: 15min, 30min, 51min, 75min

VALID_REGIMES = {"MEAN_REVERSION", "LOW_VOLATILITY", "TREND_UP",
                 "TREND_DOWN", "HIGH_VOLATILITY", "UNCERTAIN"}


# ============================================================
# DATA LOADING + DATA HYGIENE AUDIT (C2)
# ============================================================

def load_180s_bars():
    """Load all DOGE 180s bars from recorder with features."""
    bars = []
    pattern = str(RECORDER / "*" / "DOGEUSDT_180.csv")
    files = sorted(glob.glob(pattern))
    print(f"[DATA] Found {len(files)} DOGE 180s recorder files")

    feat_cols = [
        "feat_obi", "feat_tfi", "feat_delta_price", "feat_absorption",
        "feat_ema_bias", "feat_volume_spike", "feat_depth_imbalance",
        "feat_volatility_state", "feat_macro_resid", "feat_macro_sync",
        "feat_liquidity_kappa", "feat_spread_bps",
    ]

    raw_count = 0
    parse_errors = 0
    zero_price_count = 0
    missing_ts_count = 0
    bars_per_file = {}

    for f in files:
        fname = os.path.basename(os.path.dirname(f))
        file_count = 0
        with open(f, "r") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                raw_count += 1
                try:
                    ts_raw = row.get("timestamp")
                    if not ts_raw:
                        missing_ts_count += 1
                        continue
                    ts = int(float(ts_raw))
                    o = float(row.get("open") or 0)
                    h = float(row.get("high") or 0)
                    l_ = float(row.get("low") or 0)
                    c = float(row.get("close") or 0)
                    if o == 0 or c == 0:
                        zero_price_count += 1
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
                        "source_file": fname,
                    }

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
                    file_count += 1
                except (ValueError, KeyError, TypeError):
                    parse_errors += 1
                    continue
        bars_per_file[fname] = file_count

    print(f"[DATA] Raw rows: {raw_count}, Parse errors: {parse_errors}, "
          f"Missing TS: {missing_ts_count}, Zero price: {zero_price_count}")

    # Sort and deduplicate
    bars.sort(key=lambda x: x["ts_ms"])
    seen = set()
    unique = []
    dup_count = 0
    for b in bars:
        if b["ts_ms"] not in seen:
            seen.add(b["ts_ms"])
            unique.append(b)
        else:
            dup_count += 1

    print(f"[DATA] Loaded {len(unique)} unique bars (deduped {dup_count} duplicates from {raw_count} raw)")
    if unique:
        print(f"[DATA] Period: {unique[0]['datetime']} to {unique[-1]['datetime']}")

    ready_count = sum(1 for b in unique if b["ready"])
    not_ready_count = len(unique) - ready_count
    print(f"[DATA] Ready: {ready_count} ({ready_count/len(unique)*100:.1f}%), "
          f"Not-ready: {not_ready_count} ({not_ready_count/len(unique)*100:.1f}%)")

    # === DATA HYGIENE AUDIT (C2) ===
    print("\n[DATA HYGIENE AUDIT]")

    # Time gap analysis
    gaps = []
    for i in range(1, len(unique)):
        delta_ms = unique[i]["ts_ms"] - unique[i-1]["ts_ms"]
        expected_ms = 180_000  # 3 min
        if delta_ms > expected_ms * 2:  # gap > 6 min
            gaps.append({
                "from": unique[i-1]["datetime"],
                "to": unique[i]["datetime"],
                "gap_bars": delta_ms / expected_ms,
                "gap_sec": delta_ms / 1000,
            })

    print(f"  Time gaps > 6min: {len(gaps)}")
    if gaps:
        total_gap_bars = sum(g["gap_bars"] for g in gaps)
        print(f"  Total gap bars (missing): ~{total_gap_bars:.0f}")
        for g in gaps[:5]:
            print(f"    {g['from']} -> {g['to']} ({g['gap_bars']:.1f} bars, {g['gap_sec']:.0f}s)")
        if len(gaps) > 5:
            print(f"    ... and {len(gaps) - 5} more")

    # Out-of-order check
    out_of_order = 0
    for i in range(1, len(bars)):
        if bars[i]["ts_ms"] < bars[i-1]["ts_ms"]:
            out_of_order += 1
    print(f"  Out-of-order timestamps (pre-sort): {out_of_order}")

    # Day overlap audit
    overlap_dates = [d for d, c in bars_per_file.items() if c > 480]  # >480 = >24h of 3m bars
    print(f"  Days with >480 bars (session overlap): {len(overlap_dates)}")
    if overlap_dates[:3]:
        for d in overlap_dates[:3]:
            print(f"    {d}: {bars_per_file[d]} bars")

    # Duplicate count
    print(f"  Duplicate bars removed: {dup_count} ({dup_count/raw_count*100:.1f}% of raw)")

    # Feature completeness audit
    feat_missing = Counter()
    for b in unique:
        for fc in feat_cols:
            if b.get(fc) is None:
                feat_missing[fc] += 1
    print(f"\n  Feature completeness (of {len(unique)} bars):")
    for fc in feat_cols:
        missing = feat_missing.get(fc, 0)
        present = len(unique) - missing
        print(f"    {fc:30s}: {present:6d} ({present/len(unique)*100:.1f}%)")

    # Regime raw column check
    regime_raw_counts = Counter(b["regime_raw"] for b in unique)
    print(f"\n  Raw regime column values:")
    for r, c in sorted(regime_raw_counts.items(), key=lambda x: -x[1]):
        print(f"    {r:25s}: {c:6d} ({c/len(unique)*100:.1f}%)")

    hygiene = {
        "raw_rows": raw_count,
        "parse_errors": parse_errors,
        "missing_ts": missing_ts_count,
        "zero_price": zero_price_count,
        "unique_bars": len(unique),
        "duplicates_removed": dup_count,
        "ready_bars": ready_count,
        "not_ready_bars": not_ready_count,
        "time_gaps_gt_6min": len(gaps),
        "out_of_order": out_of_order,
        "session_overlap_days": len(overlap_dates),
    }

    return unique, hygiene


def load_alpha_regimes():
    """Load regime labels from alpha_input for DOGE. Try 180s first, then 300s nearest."""
    regimes_180 = {}
    regimes_300 = {}
    if not ALPHA_INPUT.exists():
        print("[REGIME] alpha_input file not found")
        return regimes_180, regimes_300
    with open(ALPHA_INPUT, "r") as f:
        for line in f:
            try:
                obj = json.loads(line.strip())
                if obj.get("symbol") != "DOGEUSDT":
                    continue
                ts = obj["ts_ms"]
                reg = obj.get("regime", "UNKNOWN")
                if not reg or reg == "DEFAULT" or reg not in VALID_REGIMES:
                    continue
                tf = obj.get("tf_sec")
                if tf == 180:
                    regimes_180[ts] = reg
                elif tf == 300:
                    regimes_300[ts] = reg
            except (json.JSONDecodeError, KeyError):
                continue
    print(f"[REGIME] Alpha: {len(regimes_180)} @180s, {len(regimes_300)} @300s")
    return regimes_180, regimes_300


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


# === SIGNAL GENERATION ===

def compute_weighted_signal(bar, weights, threshold):
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
                   max_hold_bars=AURORA_MAX_HOLD_BARS_180, cost_bps=COST_TAKER_RT_BPS):
    entry = signal["entry_price"]
    direction = 1 if signal["type"] == "BUY" else -1

    r_sl = REGIME_SL_MULT.get(regime, 1.0) * sl_mult
    r_tp = REGIME_TP_MULT.get(regime, 1.0) * tp_mult

    sl_pct = max(AURORA_MIN_SL_PCT, min(AURORA_MAX_SL_PCT, AURORA_SL_PCT * r_sl))
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

        # SL check (priority over TP within same bar)
        if direction == 1 and bar["low"] <= stop:
            exit_reason = "SL"
            exit_price = stop
            break
        elif direction == -1 and bar["high"] >= stop:
            exit_reason = "SL"
            exit_price = stop
            break
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
    cost_used = abs(sum(net_pnls) / n - gross_avg)

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


# ============================================================
# MAIN STUDY
# ============================================================

def run_study():
    print("=" * 80)
    print("DOGE x AURORA @ 180s DEEP FOLLOW-UP STUDY")
    print("SURFACE CLASS: NATIVE_RESEARCH_ONLY (bars natively recorded, no runtime consumer)")
    print("=" * 80)

    # === A1: SURFACE IDENTITY ===
    print("\n" + "=" * 60)
    print("A1. SURFACE IDENTITY: 180s")
    print("=" * 60)
    print("  FACT: 180s bars are natively recorded (data/recorder/*/DOGEUSDT_180.csv)")
    print("  FACT: FE computes features for 180s (domains.yaml enabled_timeframes_sec: [180,300,900])")
    print("  FACT: Aurora handler gates on tf_sec=300 (aurora_handler.py:763) -> 180s REJECTED")
    print("  FACT: Regime detector gates on tf_sec=300 (regime_detector.py:331) -> 180s IGNORED")
    print("  FACT: Pillars use 900/14400/86400 -> 180s NOT USED")
    print("  FACT: No strategy handler claims 180s as basis TF")
    print("  FACT: pending_entry_ttl has 180:600 entry -> infrastructure ready, no consumer")
    print("  INFERENCE: 180s is a stage-1 (data+features) surface with no stage-2 (decision) consumer")
    print("  ASSUMPTION: Feature computation at 180s is identical in quality to 300s")
    print("  UNKNOWN: Why 180s was added to enabled_timeframes - planned future use or legacy")
    print()
    print("  VERDICT: NATIVE_RESEARCH_ONLY")
    print("    - Bars: NATIVE (natively recorded)")
    print("    - Features: NATIVE (natively computed by FE)")
    print("    - Strategy: ABSENT (no handler consumes)")
    print("    - Regime: ABSENT (detector ignores)")
    print("    - Runtime connect: REQUIRES CODE CHANGE (aurora_handler TF gate + regime basis)")

    # === LOAD DATA ===
    bars, hygiene = load_180s_bars()
    alpha_180, alpha_300 = load_alpha_regimes()

    if not bars:
        print("[FATAL] No 180s data")
        return

    # === A2: CONTRACT CROSS-CHECK ===
    print("\n" + "=" * 60)
    print("A2. NATIVE CONTRACT CROSS-CHECK FOR 180s")
    print("=" * 60)

    contracts = [
        ("Aurora TF", "aurora_handler.py:763", "300", "INCOMPATIBLE", "Handler rejects 180s silently"),
        ("Feature horizons", "domains.yaml:131", "[180,300,900]", "NATIVE", "180s in enabled list"),
        ("Price features", "recorder CSV", "All feat_* present", "NATIVE", "Same columns as 300s"),
        ("Regime basis", "regime.yaml:1", "300", "INCOMPATIBLE", "Detector ignores 180s"),
        ("Pillar basis", "FE pillar config", "900/14400/86400", "ABSENT", "No 180s pillar"),
        ("Holding period", "aurora.yaml", "3000 sec", "REQUIRES MAPPING",
         f"3000/180 = 16.7 -> 17 bars (vs 10 at 300s)"),
        ("Pending TTL", "domains.yaml:481", "180: 600", "NATIVE", "TTL entry exists"),
        ("Stale TTL", "N/A", "N/A", "UNKNOWN", "No explicit stale_ttl for 180s found"),
        ("Handler TF gate", "aurora_handler.py:763", "tf_sec != 300", "INCOMPATIBLE",
         "Would need per-symbol or multi-TF gate"),
        ("Signal threshold", "aurora.yaml:1023", "0.09 for DOGE", "ASSUMED PORTABLE",
         "Threshold tuned for 300s features, may not transfer"),
        ("SL/TP %", "aurora.yaml:1063", "1.512% SL", "ASSUMED PORTABLE",
         "Absolute % is TF-agnostic but ATR context differs at 180s"),
    ]

    print(f"\n  {'Contract':25s} | {'Source':25s} | {'Value':15s} | {'180s Status':20s}")
    print(f"  {'-'*25} | {'-'*25} | {'-'*15} | {'-'*20}")
    for name, source, val, status, note in contracts:
        print(f"  {name:25s} | {source:25s} | {val:15s} | {status}")
        print(f"  {'':25s} | {'':25s} | Note: {note}")

    incompatible = sum(1 for _, _, _, s, _ in contracts if s == "INCOMPATIBLE")
    print(f"\n  INCOMPATIBLE contracts: {incompatible}/11")
    print("  -> 180s is data-native but decision-incompatible with current Aurora architecture")

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

        ts = bar["ts_ms"]
        regime = None
        regime_conf = 0
        regime_source = "NONE"

        # Priority 1: alpha_input at 180s (direct)
        if ts in alpha_180:
            regime = alpha_180[ts]
            regime_conf = 0.5
            regime_source = "ALPHA_180"
        # Priority 2: alpha_input at 300s (nearest match within +/- 300s)
        if regime is None:
            for delta in [0, -180000, 180000, -300000, 300000]:
                check_ts = ts + delta
                if check_ts in alpha_300:
                    regime = alpha_300[check_ts]
                    regime_conf = 0.4
                    regime_source = "ALPHA_300_NEAREST"
                    break
        # Priority 3: Compute from SMA
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

    alpha_total = source_counts.get("ALPHA_180", 0) + source_counts.get("ALPHA_300_NEAREST", 0)
    computed = source_counts.get("COMPUTED", 0)
    print(f"\n  Alpha-sourced: {alpha_total} ({alpha_total / len(bars) * 100:.1f}%)")
    print(f"  Computed (SMA): {computed} ({computed / len(bars) * 100:.1f}%)")

    # === SIGNAL GENERATION ===
    print("\n" + "=" * 60)
    print("SIGNAL GENERATION @ 180s (DUAL TRACKS)")
    print("=" * 60)

    signals_a = generate_signals(bars, WEIGHTS_GENERIC, AURORA_SIGNAL_THRESHOLD)
    signals_b = generate_signals(bars, WEIGHTS_DOGE_CONFIG, AURORA_SIGNAL_THRESHOLD)

    for track_name, sigs in [("A (generic)", signals_a), ("B (DOGE-config)", signals_b)]:
        print(f"\n  Track {track_name}: {len(sigs)} signals")
        if sigs:
            dir_dist = Counter(s["type"] for s in sigs)
            reg_dist = Counter(s["macro_regime"] for s in sigs)
            print(f"    Direction: {dict(dir_dist)}")
            for r, c in sorted(reg_dist.items(), key=lambda x: -x[1]):
                print(f"    {r:25s}: {c:5d}")

    # === SIMULATION HELPERS ===
    def run_sim(sigs, sl_m=1.0, tp_m=1.0, max_hold=AURORA_MAX_HOLD_BARS_180,
                cost_bps=COST_TAKER_RT_BPS):
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

    # === BASELINE (4 variants) ===
    print("\n" + "=" * 60)
    print(f"BASELINE: DOGE x AURORA @ 180s (max_hold={AURORA_MAX_HOLD_BARS_180} bars = {AURORA_MAX_HOLD_BARS_180*180}s)")
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

    # Hold-mapping audit
    print(f"\n  [HOLD-MAPPING AUDIT]")
    print(f"    AURORA_MAX_HOLD_SEC = {AURORA_MAX_HOLD_SEC}")
    print(f"    At 180s bars: {AURORA_MAX_HOLD_SEC}/{180} = {AURORA_MAX_HOLD_SEC/180:.2f} -> {AURORA_MAX_HOLD_BARS_180} bars")
    print(f"    At 300s bars: {AURORA_MAX_HOLD_SEC}/{300} = {AURORA_MAX_HOLD_SEC/300:.2f} -> {AURORA_MAX_HOLD_BARS_300} bars")
    print(f"    FACT: 180s study uses 17 bars (51 min), 300s study used 10 bars (50 min)")
    print(f"    ASSUMPTION: Mapping is by rounding up to nearest bar boundary (fail-open)")
    print(f"    NOTE: 17*180=3060 vs 10*300=3000 -> 180s gets 60s MORE hold time (+2%)")

    # === REGIME-CONDITIONED ===
    print("\n" + "=" * 60)
    print("REGIME-CONDITIONED ANALYSIS @ 180s")
    print("=" * 60)

    regime_summaries = {}
    bucket_summaries = {}
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

        print(f"\n--- By Flat Bucket ---")
        for bucket in sorted(set(r["flat_bucket"] for r in primary_res)):
            subset = [r for r in primary_res if r["flat_bucket"] == bucket]
            if len(subset) >= 3:
                s = summarize(subset, f"BUCKET:{bucket}")
                bucket_summaries[bucket] = s
                print_summary(s)

    # === SCORE BANDS ===
    print("\n" + "=" * 60)
    print("SCORE BAND ANALYSIS @ 180s")
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
                ss = summarize(subset, f"T{track_name}:SCORE:{band_name}")
                print_summary(ss)

        print(f"\n--- Track {track_name} Direction ---")
        for d in ["BUY", "SELL"]:
            subset = [r for r in res_list if r["direction"] == d]
            if len(subset) >= 3:
                print_summary(summarize(subset, f"T{track_name}:DIR:{d}"))

    # === CALIBRATION GRID ===
    print("\n" + "=" * 60)
    print("FEE-AWARE CALIBRATION GRID @ 180s")
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

    # Any positive grid point?
    any_positive = False
    for vname, cal_sorted in cal_all.items():
        pos = sum(1 for c in cal_sorted if c.get("net_exp", -1) > 0)
        neg = len(cal_sorted) - pos
        print(f"\n  [{vname}] Positive: {pos}/{len(cal_sorted)}, Negative: {neg}/{len(cal_sorted)}")
        if pos > 0:
            any_positive = True

    # === STABILITY ===
    print("\n" + "=" * 60)
    print("STABILITY VALIDATION")
    print("=" * 60)

    stability_results = {}
    for vname, sigs, cost in variants:
        if not sigs:
            continue
        mid = len(sigs) // 2
        h1_res = run_sim(sigs[:mid], cost_bps=cost)
        h2_res = run_sim(sigs[mid:], cost_bps=cost)
        s_h1 = summarize(h1_res, f"{vname}_H1")
        s_h2 = summarize(h2_res, f"{vname}_H2")

        both_pos = s_h1.get("net_exp", -1) > 0 and s_h2.get("net_exp", -1) > 0
        verdict = "STABLE" if both_pos else "UNSTABLE"
        stability_results[vname] = {"h1": s_h1, "h2": s_h2, "verdict": verdict}

        print(f"\n  [{vname}] Half-Split: {verdict}")
        print(f"    H1: {s_h1.get('net_exp', 0):.4f}% ({s_h1.get('trades', 0)} trades)")
        print(f"    H2: {s_h2.get('net_exp', 0):.4f}% ({s_h2.get('trades', 0)} trades)")

    # Walk-forward 3-way
    print("\n--- Walk-Forward 3-Way ---")
    wf_results = {}
    for vname, sigs, cost in variants:
        if not sigs:
            continue
        third = len(sigs) // 3
        segs = []
        for seg_i, (start, end) in enumerate([(0, third), (third, 2*third), (2*third, len(sigs))]):
            seg_res = run_sim(sigs[start:end], cost_bps=cost)
            ss = summarize(seg_res, f"{vname}_WF{seg_i+1}")
            segs.append(ss)
        wf_pos = sum(1 for s in segs if s.get("net_exp", -1) > 0)
        wf_verdict = "WF_STABLE" if wf_pos == 3 else ("WF_PARTIAL" if wf_pos >= 2 else "WF_UNSTABLE")
        wf_results[vname] = {"segments": segs, "verdict": wf_verdict}

        print(f"\n  [{vname}] Walk-Forward: {wf_verdict}")
        for ss in segs:
            print(f"    {ss['label']}: net={ss.get('net_exp', 0):.4f}% ({ss.get('trades', 0)} trades)")

    # === TRADE SIMULATION SEMANTICS AUDIT (C3) ===
    print("\n" + "=" * 60)
    print("C3. TRADE SIMULATION SEMANTICS AUDIT")
    print("=" * 60)

    c3_items = [
        ("Entry timestamp", "Bar close timestamp (end of 180s bar)", "ASSUMPTION",
         "Real entry would be at next bar open + latency. Bias: OPTIMISTIC (favorable entry)"),
        ("Entry price", "bar['close'] of signal bar", "ASSUMPTION",
         "Assumes fill at close price. Bias: SMALL OPTIMISTIC (no slippage at entry)"),
        ("SL/TP precedence", "SL checked before TP within same bar", "DESIGN CHOICE",
         "Conservative: if both SL and TP could hit in same bar, SL wins. Bias: PESSIMISTIC"),
        ("Hold expiry", "After max_hold_bars, exit at last bar close", "DESIGN CHOICE",
         "Neutral: matches runtime hold semantics approximately"),
        ("Bar-internal fill", "SL/TP assumed to fill at exact level", "ASSUMPTION",
         "Real fills may gap through. Bias: slightly OPTIMISTIC for TP, slightly PESSIMISTIC for SL"),
        ("Cost application", "Round-trip cost deducted from PnL", "CORRECT",
         "Applied uniformly to all trades. No selective cost bias."),
        ("Maker vs taker", "10 bps (maker) and 14 bps (taker) tested", "CORRECT",
         "Dual-track prevents selective optimism"),
        ("Partial exit", "NOT SIMULATED", "MISSING",
         "Aurora has partial exit at tp_low_ratio=0.36. Bias: UNKNOWN"),
        ("Quantity/size", "NOT MODELED", "ASSUMPTION",
         "All trades equal notional. Real sizing uses regime_sizing multipliers"),
        ("Signal inflation", "1-bar cooldown prevents same-bar duplicates", "DESIGN CHOICE",
         "Cooldown = 1 bar (180s) vs runtime 120s. At 180s, 1 bar > 120s. Bias: CONSERVATIVE"),
    ]

    for name, value, classification, note in c3_items:
        print(f"  {name:25s} | {classification:15s} | {value}")
        print(f"  {'':25s} | Bias: {note}")

    # === RUNTIME FIDELITY AUDIT (C4) ===
    print("\n" + "=" * 60)
    print("C4. RUNTIME FIDELITY AUDIT")
    print("=" * 60)

    c4_items = [
        ("Signal model", "Linear weighted-sum proxy", "Quadratic kernel (sign(S)*S^2)",
         "HIGH", "Can inflate linear edge into quadratic noise or vice versa", "UNKNOWN"),
        ("Shield cascade", "ABSENT", "Context/Memory/DangerZone",
         "MEDIUM", "Shields attenuate real signals -> fewer trades in reality", "OPTIMISTIC"),
        ("Pillar system", "ABSENT", "Tactician/Operator/Strategist multi-TF",
         "HIGH", "Proxy uses single-TF features vs real multi-TF consensus", "UNKNOWN"),
        ("Regime fidelity", "94% SMA-computed", "Production regime detector",
         "MEDIUM", "SMA regime is coarser than production detector", "UNKNOWN"),
        ("Liquidity gate", "ABSENT", "Kappa >= 0.15 required",
         "LOW", "Would filter some signals in thin liquidity", "SLIGHTLY OPTIMISTIC"),
        ("Hold period", f"{AURORA_MAX_HOLD_BARS_180} bars (51 min)", "3000s runtime",
         "LOW", "17*180=3060 vs 3000 = +60s/+2% overshoot", "SLIGHTLY OPTIMISTIC"),
        ("TF gating", "180s (NOT runtime)", "300s (runtime gate)",
         "HIGH", "180s is not consumed by Aurora handler at all", "INCOMPATIBLE"),
        ("Threshold transfer", "0.09 (from 300s config)", "0.09 tuned for 300s features",
         "MEDIUM", "Feature distributions may differ at 180s", "UNKNOWN"),
    ]

    print(f"  {'Gap':25s} | {'Study':25s} | {'Runtime':25s} | Sev")
    print(f"  {'-'*25} | {'-'*25} | {'-'*25} | ---")
    for name, study, runtime, sev, mechanism, bias in c4_items:
        print(f"  {name:25s} | {study:25s} | {runtime:25s} | {sev}")
        print(f"  {'':25s} | Mechanism: {mechanism}")
        print(f"  {'':25s} | Bias direction: {bias}")

    # === LEAKAGE / OPTIMISM AUDIT (C5) ===
    print("\n" + "=" * 60)
    print("C5. LEAKAGE / OPTIMISM / FALSE-EDGE AUDIT")
    print("=" * 60)

    c5_items = [
        ("Hold duration", "17 bars = 3060s, 2% over runtime 3000s",
         "Allows 60s extra drift accumulation. At 180s scale, negligible.",
         "LOW", "Cannot flip negative to positive"),
        ("Non-ready bars", "Excluded via ready=True filter",
         "Correct: matches runtime behavior", "NONE", "Controlled"),
        ("Duplicate sessions", f"Removed {hygiene['duplicates_removed']} duplicates by ts_ms",
         "First-seen dedup is deterministic but arbitrary (session order depends on glob sort)",
         "LOW", "Unlikely to inject systematic bias"),
        ("Regime labeling", "94% computed from SMA, not production detector",
         "SMA regime is simpler: may merge distinct production regimes. Regime-conditioned results are unreliable.",
         "MEDIUM", "Cannot generate false edge; may hide real regime effects"),
        ("Lookahead in resampling", "N/A - bars are native 180s, not resampled",
         "No cross-timeframe reconstruction needed",
         "NONE", "Clean - this is a strength of 180s vs 900s"),
        ("Fill ordering", "SL before TP within bar (conservative)",
         "May undercount TP hits when both are possible",
         "LOW", "Pessimistic bias, cannot create false edge"),
        ("Cost selectivity", "10 bps and 14 bps tested in parallel",
         "No selective cost optimization. Both tracks reported.",
         "NONE", "Controlled"),
        ("Score compression", "Linear score directly from features",
         "Feature ranges: obi/tfi/absorption in [0,1], macro_resid in [-3,+3]. "
         "Track B macro_resid dominates signal.",
         "MEDIUM", "Track B results are effectively macro_resid-driven, not diversified"),
        ("180s feature transfer", "ASSUMPTION: 180s features have same semantics as 300s",
         "Feature engineering computes same indicators but shorter lookback in wall-clock time. "
         "BB(20) at 180s = 60 min vs BB(20) at 300s = 100 min lookback.",
         "MEDIUM", "Feature semantics may differ - threshold 0.09 may not transfer"),
    ]

    for name, finding, analysis, severity, conclusion in c5_items:
        print(f"  {name}:")
        print(f"    Finding: {finding}")
        print(f"    Analysis: {analysis}")
        print(f"    Severity: {severity} | {conclusion}")
        print()

    # === TESTNET CANDIDATE FILTER ===
    print("\n" + "=" * 60)
    print("TESTNET CANDIDATE FILTER")
    print("=" * 60)

    for vname in ["A_10bps", "A_14bps", "B_10bps", "B_14bps"]:
        if vname not in baselines:
            continue
        bl = baselines[vname]
        stab = stability_results.get(vname, {}).get("verdict", "UNSTABLE")

        positive = bl["net_exp"] > 0
        stable = stab == "STABLE"
        non_tiny = bl["trades"] >= 30
        runtime_plausible = False  # 180s is NOT consumed by Aurora handler
        high_sev_gaps = 3  # signal model, pillar, TF gating

        print(f"\n  --- {vname} ---")
        print(f"  1. Positive after costs:     {'PASS' if positive else 'FAIL'} (net_exp={bl['net_exp']:.4f}%)")
        print(f"  2. Survives stability split:  {'PASS' if stable else 'FAIL'} ({stab})")
        print(f"  3. Non-trivially sized:       {'PASS' if non_tiny else 'FAIL'} ({bl['trades']} trades)")
        print(f"  4. Runtime/config plausible:   FAIL (Aurora handler does NOT consume 180s)")
        print(f"  5. Boundedness acceptable:     FAIL ({high_sev_gaps} HIGH gaps, surface is synthetic)")

        if positive and stable and non_tiny:
            verdict = "BOUNDED_RESEARCH_CANDIDATE"
        elif positive and non_tiny:
            verdict = "BOUNDED_NEGATIVE"
        elif positive:
            verdict = "BOUNDED_NEGATIVE"
        else:
            verdict = "CLOSED_NEGATIVE"
        print(f"  VERDICT: {verdict}")
        baselines[vname]["verdict"] = verdict

    # Overall
    rank = {"CALIBRATION_CANDIDATE": 5, "BOUNDED_RESEARCH_CANDIDATE": 4,
            "BOUNDED_NEGATIVE": 3, "NOT_READY_FOR_TESTNET": 2, "CLOSED_NEGATIVE": 1}
    best_verdict = "CLOSED_NEGATIVE"
    best_variant = None
    for vn, bl in baselines.items():
        v = bl.get("verdict", "CLOSED_NEGATIVE")
        if rank.get(v, 0) > rank.get(best_verdict, 0):
            best_verdict = v
            best_variant = vn

    print(f"\n  === OVERALL 180s VERDICT: {best_verdict} (via {best_variant}) ===")

    # === METHOD TRUST SCORING (C6) ===
    print("\n" + "=" * 60)
    print("C6. METHOD TRUST SCORING")
    print("=" * 60)

    trust = {
        "DATA_TRUST": "HIGH",
        "DATA_TRUST_JUSTIFICATION": (
            "Native 180s recorder bars with all features computed by FE. "
            f"50 files, {hygiene['unique_bars']} unique bars after dedup. "
            f"Dedup removed {hygiene['duplicates_removed']} ({hygiene['duplicates_removed']/max(1,hygiene['raw_rows'])*100:.1f}%). "
            f"Ready-bar filtering applied ({hygiene['ready_bars']} ready). "
            "No synthetic resampling. No cross-TF reconstruction. "
            "This is the cleanest data path of any DOGE study."
        ),
        "SIMULATION_TRUST": "MEDIUM",
        "SIMULATION_TRUST_JUSTIFICATION": (
            "Standard bar-level SL/TP simulation with conservative SL-first precedence. "
            "Cost model is dual-track (10/14 bps), no selective optimization. "
            "Hold mapping is correct (17 bars for 3000s / 180s, +2% overshoot). "
            "Missing: partial exit, trailing stop, liquidity gate, position sizing. "
            "Entry at close price is slightly optimistic. "
            "Overall: simulation is structurally sound but simplified."
        ),
        "RUNTIME_FIDELITY": "LOW",
        "RUNTIME_FIDELITY_JUSTIFICATION": (
            "180s is NOT consumed by Aurora handler (hard gate at tf_sec=300). "
            "Signal model is linear proxy vs real quadratic kernel with shield cascade. "
            "Pillars (multi-TF consensus) absent. Regime detector doesn't operate at 180s. "
            "Even if results were positive, enabling this surface requires code changes to "
            "aurora_handler.py (TF gate), regime_detector.py (basis TF), and strategy_compatibility_matrix.py. "
            "Feature semantics may differ at 180s (shorter lookback windows). "
            "No operational conclusion should be drawn from this surface."
        ),
        "RESULT_TRUST": "LOW",
        "RESULT_TRUST_JUSTIFICATION": (
            "Combining HIGH data trust with MEDIUM simulation trust with LOW runtime fidelity "
            "yields LOW overall result trust. Even if the numbers are clean and the simulation "
            "is fair, the surface is not runtime-meaningful. Any positive or negative finding "
            "answers the question 'does a linear proxy on 180s features show edge?' but does NOT "
            "answer 'would DOGE on Aurora at 180s be profitable in production?'"
        ),
    }

    for key in ["DATA_TRUST", "SIMULATION_TRUST", "RUNTIME_FIDELITY", "RESULT_TRUST"]:
        print(f"  {key}: {trust[key]}")
        print(f"    {trust[key + '_JUSTIFICATION']}")
        print()

    # === RUNTIME ENABLEMENT SURFACE ===
    print("\n" + "=" * 60)
    print("RUNTIME ENABLEMENT SURFACE (180s path)")
    print("=" * 60)

    surfaces = [
        ("Assignment", "strategies.yaml", "DOGE unassigned",
         "Add DOGEUSDT: [aurora]", "Config contention", "YES"),
        ("Aurora TF gate", "aurora_handler.py:763", "Hardcoded tf_sec=300",
         "Must add 180s support or multi-TF dispatch", "CODE CHANGE needed", "NO"),
        ("Aurora config", "aurora.yaml:DOGEUSDT", "timeframe_sec: null (300)",
         "Set timeframe_sec: 180", "Untested parameter", "YES"),
        ("Regime detector", "regime_detector.py:331", "basis_tf_sec=300",
         "Must add 180s basis or cross-TF mapping", "CODE CHANGE needed", "NO"),
        ("Feature pipeline", "domains.yaml", "180 in enabled_timeframes",
         "Already active", "NONE", "YES"),
        ("Bar aggregator", "trading.yaml", "180 in timeframes_sec",
         "Already active", "NONE", "YES"),
        ("Pending TTL", "domains.yaml:481", "180: 600",
         "Already configured", "NONE", "YES"),
    ]

    code_changes_needed = sum(1 for _, _, _, _, _, fc in surfaces if fc == "NO")
    for s_name, s_file, s_current, s_change, s_risk, s_fc in surfaces:
        print(f"  {s_name:20s} | {s_file:30s} | Fail-closed: {s_fc}")
        print(f"  {'':20s} | Current: {s_current}")
        print(f"  {'':20s} | Needed: {s_change} | Risk: {s_risk}")
        print()

    print(f"  CODE CHANGES REQUIRED: {code_changes_needed}")
    print(f"  RUNTIME PLAUSIBLE: NO (requires aurora_handler + regime_detector changes)")

    # === SAVE OUTPUT ===
    output = {
        "study_date": "2026-03-29",
        "study_type": "DOGE_AURORA_180s_DEEP_FOLLOWUP",
        "surface_class": "NATIVE_RESEARCH_ONLY",
        "full_period": f"{bars[0]['datetime']} to {bars[-1]['datetime']}",
        "total_bars": len(bars),
        "warmup_bars": warmup,
        "mature_bars": mature,
        "cost_models": {"maker_rt_bps": COST_MAKER_RT_BPS, "taker_rt_bps": COST_TAKER_RT_BPS},
        "hold_mapping": {
            "aurora_max_hold_sec": AURORA_MAX_HOLD_SEC,
            "bars_at_180s": AURORA_MAX_HOLD_BARS_180,
            "actual_hold_sec": AURORA_MAX_HOLD_BARS_180 * 180,
            "overshoot_sec": AURORA_MAX_HOLD_BARS_180 * 180 - AURORA_MAX_HOLD_SEC,
        },
        "data_hygiene": hygiene,
        "signal_counts": {
            "track_a_generic": len(signals_a),
            "track_b_doge_config": len(signals_b),
        },
        "regime_sources": dict(source_counts),
        "regime_distribution": dict(regime_counts),
        "baselines": baselines,
        "regime_summaries": regime_summaries,
        "bucket_summaries": bucket_summaries,
        "calibration_top10": {vn: cal_all[vn][:10] for vn in cal_all},
        "any_positive_calibration": any_positive,
        "stability": stability_results,
        "walk_forward": wf_results,
        "overall_verdict": best_verdict,
        "best_variant": best_variant,
        "trust_scores": {k: v for k, v in trust.items() if not k.endswith("_JUSTIFICATION")},
        "trust_justifications": {k: v for k, v in trust.items() if k.endswith("_JUSTIFICATION")},
    }

    out_path = BASE / "reports" / "DOGE_AURORA_180s_DEEP_FOLLOWUP_STUDY_2026-03-29.json"
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\n[OUTPUT] Saved to {out_path}")

    return output


if __name__ == "__main__":
    run_study()
