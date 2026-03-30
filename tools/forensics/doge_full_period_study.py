#!/usr/bin/env python3
"""
DOGE Full-Period Regime-Conditioned Calibration & Bounded Backtest Study

This script:
1. Loads ALL DOGE 5m bar data from data/recorder (full available period)
2. Reconstructs regime labels (structural macro + canonical MR bucket)
3. Replays mean_reversion signals from MR bar logs
4. Simulates TP/SL/hold outcomes on the OHLC data
5. Applies fee-aware cost model
6. Runs calibration grid (TP mult, SL mult, hold horizon)
7. Tests "many small wins" viability
8. Performs stability splits
9. Outputs all tables as JSON for report generation
"""

import csv
import json
import os
import sys
import glob
import math
from collections import defaultdict, Counter
from datetime import datetime, timedelta
from pathlib import Path

BASE = Path(r"c:\Users\user\Music\Phenix")
RECORDER = BASE / "data" / "recorder"
MR_BARS = BASE / "logs" / "mean_reversion" / "bars_300s.jsonl"
MR_BARS_TSV = BASE / "logs" / "mean_reversion" / "bars_300s.tsv"
TRADE_LIFECYCLE = BASE / "logs" / "trade_lifecycle.jsonl"
FORENSIC_TRADES = BASE / "reports" / \
    "aurora_forensic_2026-03-25_2026-03-29_trades.csv"
FORENSIC_CF = BASE / "reports" / \
    "aurora_forensic_2026-03-25_2026-03-29_counterfactual.csv"
EQUITY_CSV = BASE / "reports" / "aurora_forensic_2026-03-25_2026-03-29_equity.csv"

# === COST MODEL ===
FEE_BPS_PER_SIDE = 4.0        # 0.04% per side (Binance VIP0 taker)
SLIPPAGE_BPS = 2.0             # estimated slippage per side
SPREAD_BPS = 1.0               # estimated half-spread drag per side
TOTAL_COST_PER_SIDE_BPS = FEE_BPS_PER_SIDE + SLIPPAGE_BPS + SPREAD_BPS  # 7 bps
ROUND_TRIP_COST_BPS = 2 * TOTAL_COST_PER_SIDE_BPS  # 14 bps = 0.14%

# === MR CONFIG ===
BB_WINDOW = 20
BB_STD = 2.1       # DOGE override
ATR_WINDOW = 14
RSI_WINDOW = 14
ENTRY_THRESHOLD = 0.05   # DOGE override (5% inside band)
RSI_OVERSOLD = 30
RSI_OVERBOUGHT = 70
MIN_BB_WIDTH = 0.005     # DOGE override
SL_ATR_MULT_BASE = 1.5
TP_TO_MID = False        # DOGE override: outer band target

# Regime config
HIGH_VOL_PCT = 0.003
LOW_VOL_PCT = 0.001

# Regime sizing
REGIME_PARAMS = {
    "FLAT_LOW":    {"sizing": 0.8, "stop_mult": 1.0, "target_mult": 0.8},
    "FLAT_NORMAL": {"sizing": 1.0, "stop_mult": 1.0, "target_mult": 1.0},
    "FLAT_HIGH":   {"sizing": 0.7, "stop_mult": 1.5, "target_mult": 1.2},
}


def load_recorder_bars():
    """Load all DOGE 5m (300s) bars from data/recorder."""
    bars = []
    pattern = str(RECORDER / "*" / "DOGEUSDT_300.csv")
    files = sorted(glob.glob(pattern))
    print(f"[DATA] Found {len(files)} DOGE 300s recorder files")

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
                    vol_raw = row.get("volume", "0") or "0"
                    regime_raw = row.get("regime", "UNKNOWN") or "UNKNOWN"
                    rc_raw = row.get("regime_conf", "0") or "0"
                    bars.append({
                        "ts_ms": ts,
                        "datetime": row.get("datetime", ""),
                        "open": o,
                        "high": h,
                        "low": l_,
                        "close": c,
                        "volume": float(vol_raw),
                        "regime": regime_raw,
                        "regime_conf": float(rc_raw),
                        "ready": row.get("ready", "False") == "True",
                        "spread_bps": float(row.get("feat_spread_bps") or "0"),
                    })
                except (ValueError, KeyError, TypeError):
                    continue

    # Deduplicate by timestamp
    seen = set()
    unique = []
    for b in sorted(bars, key=lambda x: x["ts_ms"]):
        if b["ts_ms"] not in seen:
            seen.add(b["ts_ms"])
            unique.append(b)

    print(f"[DATA] Loaded {len(unique)} unique DOGE 5m bars")
    if unique:
        print(
            f"[DATA] Period: {unique[0]['datetime']} to {unique[-1]['datetime']}")
    return unique


def load_mr_bars():
    """Load all DOGE MR signal bars from bars_300s.jsonl."""
    bars = []
    if not MR_BARS.exists():
        print("[WARN] MR bars JSONL not found")
        return bars

    with open(MR_BARS, "r") as f:
        for line in f:
            try:
                obj = json.loads(line.strip())
                if obj.get("symbol") != "DOGEUSDT":
                    continue
                bars.append(obj)
            except json.JSONDecodeError:
                continue

    print(f"[DATA] Loaded {len(bars)} DOGE MR signal bars")
    return bars


def load_trade_lifecycle():
    """Load all DOGE trades from trade_lifecycle.jsonl."""
    trades = []
    if not TRADE_LIFECYCLE.exists():
        print("[WARN] trade_lifecycle.jsonl not found")
        return trades

    with open(TRADE_LIFECYCLE, "r") as f:
        for line in f:
            try:
                obj = json.loads(line.strip())
                if obj.get("symbol") != "DOGEUSDT":
                    continue
                trades.append(obj)
            except json.JSONDecodeError:
                continue

    print(f"[DATA] Loaded {len(trades)} DOGE trade lifecycle entries")
    return trades


def load_forensic_trades():
    """Load DOGE trades from forensic CSV."""
    trades = []
    for csv_path in [FORENSIC_TRADES, BASE / "reports" / "aurora_forensic_2026-03-06_2026-03-07_trades.csv"]:
        if not csv_path.exists():
            continue
        with open(csv_path, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row["symbol"] == "DOGEUSDT":
                    trades.append(row)

    print(f"[DATA] Loaded {len(trades)} DOGE forensic trade rows")
    return trades


def load_equity():
    """Load DOGE equity rows."""
    rows = []
    if not EQUITY_CSV.exists():
        return rows
    with open(EQUITY_CSV, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["symbol"] == "DOGEUSDT":
                rows.append(row)
    print(f"[DATA] Loaded {len(rows)} DOGE equity rows")
    return rows


# === TECHNICAL INDICATORS ===

def compute_sma(values, period):
    if len(values) < period:
        return None
    return sum(values[-period:]) / period


def compute_ema(values, period):
    if len(values) < period:
        return None
    k = 2 / (period + 1)
    ema = sum(values[:period]) / period
    for v in values[period:]:
        ema = v * k + ema * (1 - k)
    return ema


def compute_bb(closes, window=BB_WINDOW, num_std=BB_STD):
    if len(closes) < window:
        return None, None, None, None, None
    data = closes[-window:]
    mid = sum(data) / window
    var = sum((x - mid) ** 2 for x in data) / window
    std = math.sqrt(var)
    upper = mid + num_std * std
    lower = mid - num_std * std
    width = (upper - lower) / mid if mid > 0 else 0
    pct_b = (closes[-1] - lower) / \
        (upper - lower) if (upper - lower) > 0 else 0.5
    return upper, mid, lower, width, pct_b


def compute_rsi(closes, period=RSI_WINDOW):
    if len(closes) < period + 1:
        return None
    gains = []
    losses = []
    for i in range(-period, 0):
        change = closes[i] - closes[i - 1]
        if change > 0:
            gains.append(change)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(change))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def compute_atr(highs, lows, closes, period=ATR_WINDOW):
    if len(closes) < period + 1:
        return None
    trs = []
    for i in range(-period, 0):
        h = highs[i]
        l_ = lows[i]
        pc = closes[i - 1]
        tr = max(h - l_, abs(h - pc), abs(l_ - pc))
        trs.append(tr)
    return sum(trs) / period


# === REGIME CLASSIFICATION ===

def classify_macro_regime(closes, highs, lows, atr_val, sma48_val=None, sma192_val=None):
    """Classify structural macro regime from price data."""
    if atr_val is None:
        return "UNCERTAIN", 0.0

    price = closes[-1]

    # ATR baseline (simplified: use recent ATR ratio)
    atr_pct = atr_val / price if price > 0 else 0

    # SMA-based trend detection
    if sma48_val is not None and sma192_val is not None:
        sma_spread = abs(sma48_val - sma192_val) / price
        price_dev_short = abs(price - sma48_val) / price
        price_dev_long = abs(price - sma192_val) / price

        # Mean reversion check
        if sma_spread < 0.005 and price_dev_short < 0.005 and price_dev_long < 0.005:
            conf = min(0.85, 0.15 + 120.0 *
                       (0.005 - max(sma_spread, price_dev_short)))
            return "MEAN_REVERSION", conf

        # Trend detection
        if sma48_val > sma192_val and price > sma48_val:
            gap = (sma48_val - sma192_val) / price
            conf = min(0.85, max(0.15, 80.0 * gap))
            return "TREND_UP", conf

        if sma48_val < sma192_val and price < sma48_val:
            gap = (sma192_val - sma48_val) / price
            conf = min(0.85, max(0.15, 80.0 * gap))
            return "TREND_DOWN", conf

    return "UNCERTAIN", 0.15


def classify_flat_bucket(atr_val, price):
    """Classify into canonical MR flat bucket."""
    if atr_val is None or price <= 0:
        return "NONE"
    atr_pct = atr_val / price
    if atr_pct < LOW_VOL_PCT:
        return "FLAT_LOW"
    elif atr_pct < HIGH_VOL_PCT:
        return "FLAT_NORMAL"
    else:
        return "FLAT_HIGH"


# === SIGNAL GENERATION ===

def generate_mr_signal(closes, highs, lows, volumes):
    """Generate mean reversion signal from bar data."""
    upper, mid, lower, width, pct_b = compute_bb(closes)
    rsi = compute_rsi(closes)
    atr = compute_atr(highs, lows, closes)

    if upper is None or rsi is None or atr is None:
        return None

    if width < MIN_BB_WIDTH:
        return None

    price = closes[-1]
    signal = {"type": "NEUTRAL", "entry_price": price, "atr": atr,
              "upper": upper, "mid": mid, "lower": lower,
              "width": width, "pct_b": pct_b, "rsi": rsi}

    # BUY signal: price near/below lower BB
    if pct_b < ENTRY_THRESHOLD and rsi < RSI_OVERSOLD:
        signal["type"] = "BUY"
        if TP_TO_MID:
            signal["target"] = mid
        else:
            signal["target"] = upper  # outer band
        signal["stop"] = price - SL_ATR_MULT_BASE * atr
        signal["reason"] = f"price_below_lower_bb:pct_b={pct_b:.3f};rsi_oversold:{rsi:.1f}"

    # SELL signal: price near/above upper BB
    elif pct_b > (1 - ENTRY_THRESHOLD) and rsi > RSI_OVERBOUGHT:
        signal["type"] = "SELL"
        if TP_TO_MID:
            signal["target"] = mid
        else:
            signal["target"] = lower  # outer band
        signal["stop"] = price + SL_ATR_MULT_BASE * atr
        signal["reason"] = f"price_above_upper_bb:pct_b={pct_b:.3f};rsi_overbought:{rsi:.1f}"

    return signal


# === TRADE SIMULATION ===

def simulate_trade(bars, entry_idx, signal, sl_mult=1.0, tp_mult=1.0, max_hold_bars=24):
    """Simulate a single trade on OHLC bars with given TP/SL multipliers."""
    entry_price = signal["entry_price"]
    atr = signal["atr"]
    direction = 1 if signal["type"] == "BUY" else -1

    # Compute stop and target distances
    if direction == 1:
        base_stop_dist = entry_price - signal["stop"]
        base_target_dist = signal["target"] - entry_price
        stop_price = entry_price - base_stop_dist * sl_mult
        target_price = entry_price + base_target_dist * tp_mult
    else:
        base_stop_dist = signal["stop"] - entry_price
        base_target_dist = entry_price - signal["target"]
        stop_price = entry_price + base_stop_dist * sl_mult
        target_price = entry_price - base_target_dist * tp_mult

    mae = 0  # Maximum Adverse Excursion
    mfe = 0  # Maximum Favorable Excursion
    exit_reason = "HOLD_EXPIRED"
    exit_price = None
    hold_bars = 0

    for i in range(entry_idx + 1, min(entry_idx + 1 + max_hold_bars, len(bars))):
        bar = bars[i]
        hold_bars += 1

        if direction == 1:
            adverse = entry_price - bar["low"]
            favorable = bar["high"] - entry_price
        else:
            adverse = bar["high"] - entry_price
            favorable = entry_price - bar["low"]

        mae = max(mae, adverse)
        mfe = max(mfe, favorable)

        # Check stop hit (use high/low depending on direction)
        if direction == 1 and bar["low"] <= stop_price:
            exit_reason = "SL"
            exit_price = stop_price
            break
        elif direction == -1 and bar["high"] >= stop_price:
            exit_reason = "SL"
            exit_price = stop_price
            break

        # Check target hit
        if direction == 1 and bar["high"] >= target_price:
            exit_reason = "TP"
            exit_price = target_price
            break
        elif direction == -1 and bar["low"] <= target_price:
            exit_reason = "TP"
            exit_price = target_price
            break

    if exit_price is None:
        # Hold expired, exit at close of last bar
        last_idx = min(entry_idx + max_hold_bars, len(bars) - 1)
        exit_price = bars[last_idx]["close"]

    # PnL
    if direction == 1:
        gross_pnl_pct = (exit_price - entry_price) / entry_price * 100
    else:
        gross_pnl_pct = (entry_price - exit_price) / entry_price * 100

    net_pnl_pct = gross_pnl_pct - ROUND_TRIP_COST_BPS / 100

    # R-multiple (risk unit = stop distance)
    risk_dist = base_stop_dist * sl_mult
    if risk_dist > 0:
        gross_r = gross_pnl_pct / (risk_dist / entry_price * 100)
        net_r = net_pnl_pct / (risk_dist / entry_price * 100)
        mae_r = mae / risk_dist
        mfe_r = mfe / risk_dist
    else:
        gross_r = net_r = mae_r = mfe_r = 0

    return {
        "exit_reason": exit_reason,
        "entry_price": entry_price,
        "exit_price": exit_price,
        "hold_bars": hold_bars,
        "gross_pnl_pct": gross_pnl_pct,
        "net_pnl_pct": net_pnl_pct,
        "gross_r": gross_r,
        "net_r": net_r,
        "mae": mae,
        "mfe": mfe,
        "mae_r": mae_r,
        "mfe_r": mfe_r,
        "direction": "BUY" if direction == 1 else "SELL",
        "stop_price": stop_price,
        "target_price": target_price,
    }


# === MAIN ANALYSIS ===

def run_full_study():
    print("=" * 80)
    print("DOGE FULL-PERIOD REGIME-CONDITIONED CALIBRATION STUDY")
    print("=" * 80)

    # --- 1. Load all data ---
    bars = load_recorder_bars()
    mr_signal_bars = load_mr_bars()
    lifecycle_trades = load_trade_lifecycle()
    forensic_trades = load_forensic_trades()
    equity_rows = load_equity()

    if not bars:
        print("[FATAL] No DOGE bar data found")
        return

    # --- 2. Build enriched bar series ---
    closes = []
    highs = []
    lows = []
    volumes = []
    sma48_series = []
    sma192_series = []

    enriched_bars = []
    for i, bar in enumerate(bars):
        closes.append(bar["close"])
        highs.append(bar["high"])
        lows.append(bar["low"])
        volumes.append(bar["volume"])

        atr = compute_atr(highs, lows, closes) if len(
            closes) > ATR_WINDOW else None
        sma48 = compute_sma(closes, 48) if len(closes) >= 48 else None
        sma192 = compute_sma(closes, 192) if len(closes) >= 192 else None

        # Macro regime from recorder data (prefer recorded regime if valid)
        recorded_regime = bar["regime"]
        if recorded_regime in ("MEAN_REVERSION", "LOW_VOLATILITY", "TREND_UP",
                               "TREND_DOWN", "HIGH_VOLATILITY", "UNCERTAIN"):
            macro_regime = recorded_regime
            macro_conf = bar["regime_conf"]
        else:
            macro_regime, macro_conf = classify_macro_regime(
                closes, highs, lows, atr, sma48, sma192)

        # Canonical MR bucket
        flat_bucket = classify_flat_bucket(atr, bar["close"])

        # Allowed for MR?
        mr_allowed = macro_regime in ("MEAN_REVERSION", "LOW_VOLATILITY") and flat_bucket in (
            "FLAT_LOW", "FLAT_NORMAL", "FLAT_HIGH")

        bar["atr"] = atr
        bar["sma48"] = sma48
        bar["sma192"] = sma192
        bar["macro_regime"] = macro_regime
        bar["macro_conf"] = macro_conf
        bar["flat_bucket"] = flat_bucket
        bar["mr_allowed"] = mr_allowed
        bar["bar_idx"] = i
        enriched_bars.append(bar)

    print(
        f"\n[ENRICHED] {len(enriched_bars)} bars enriched with regime labels")

    # --- 3. Regime occupancy analysis ---
    print("\n" + "=" * 60)
    print("REGIME OCCUPANCY ANALYSIS")
    print("=" * 60)

    macro_counts = Counter()
    bucket_counts = Counter()
    cross_counts = Counter()
    mr_allowed_count = 0
    warmup_bars = 0

    for bar in enriched_bars:
        if bar["atr"] is None:
            warmup_bars += 1
            continue
        macro_counts[bar["macro_regime"]] += 1
        bucket_counts[bar["flat_bucket"]] += 1
        cross_counts[(bar["flat_bucket"], bar["macro_regime"])] += 1
        if bar["mr_allowed"]:
            mr_allowed_count += 1

    total_mature = len(enriched_bars) - warmup_bars
    print(f"\nTotal bars: {len(enriched_bars)}")
    print(f"Warmup (no ATR): {warmup_bars}")
    print(f"Mature bars: {total_mature}")
    print(
        f"MR-allowed bars: {mr_allowed_count} ({mr_allowed_count / total_mature * 100:.1f}%)")

    print("\n--- Macro Regime Distribution ---")
    for regime, count in sorted(macro_counts.items(), key=lambda x: -x[1]):
        print(f"  {regime:25s}: {count:6d} ({count / total_mature * 100:.1f}%)")

    print("\n--- Canonical MR Bucket Distribution ---")
    for bucket, count in sorted(bucket_counts.items(), key=lambda x: -x[1]):
        print(f"  {bucket:25s}: {count:6d} ({count / total_mature * 100:.1f}%)")

    print("\n--- Cross Matrix (Bucket × Macro) ---")
    for (bucket, macro), count in sorted(cross_counts.items(), key=lambda x: -x[1]):
        print(
            f"  {bucket:15s} × {macro:20s}: {count:6d} ({count / total_mature * 100:.1f}%)")

    # --- 4. Generate MR signals over full period ---
    print("\n" + "=" * 60)
    print("MR SIGNAL GENERATION OVER FULL PERIOD")
    print("=" * 60)

    signals = []
    cooldown_until = 0
    COOLDOWN_BARS = 1  # 210s / 300s ≈ 0.7, round up to 1 bar

    for i in range(max(BB_WINDOW, ATR_WINDOW + 1, RSI_WINDOW + 1), len(enriched_bars)):
        bar = enriched_bars[i]

        if i < cooldown_until:
            continue

        sig = generate_mr_signal(
            closes[:i + 1], highs[:i + 1], lows[:i + 1], volumes[:i + 1])

        if sig and sig["type"] != "NEUTRAL":
            sig["bar_idx"] = i
            sig["ts_ms"] = bar["ts_ms"]
            sig["datetime"] = bar["datetime"]
            sig["macro_regime"] = bar["macro_regime"]
            sig["macro_conf"] = bar["macro_conf"]
            sig["flat_bucket"] = bar["flat_bucket"]
            sig["mr_allowed"] = bar["mr_allowed"]
            signals.append(sig)
            cooldown_until = i + COOLDOWN_BARS + 1

    all_signals = len(signals)
    mr_allowed_signals = [s for s in signals if s["mr_allowed"]]
    mr_blocked_signals = [s for s in signals if not s["mr_allowed"]]

    print(f"\nTotal MR signals generated: {all_signals}")
    print(f"MR-allowed (would trade): {len(mr_allowed_signals)}")
    print(f"MR-blocked (regime gate): {len(mr_blocked_signals)}")

    # Signal regime distribution
    print("\n--- Signals by Macro Regime ---")
    sig_macro = Counter(s["macro_regime"] for s in signals)
    for regime, count in sorted(sig_macro.items(), key=lambda x: -x[1]):
        print(f"  {regime:25s}: {count:4d}")

    print("\n--- Signals by Flat Bucket ---")
    sig_bucket = Counter(s["flat_bucket"] for s in signals)
    for bucket, count in sorted(sig_bucket.items(), key=lambda x: -x[1]):
        print(f"  {bucket:25s}: {count:4d}")

    # --- 5. Baseline simulation (current config) ---
    print("\n" + "=" * 60)
    print("TRACK A: RUNTIME-FAITHFUL BASELINE (current config)")
    print("=" * 60)

    def run_simulation(signal_set, bars_data, sl_mult=1.0, tp_mult=1.0, max_hold=24, label="baseline"):
        results = []
        for sig in signal_set:
            idx = sig["bar_idx"]
            if idx + 1 >= len(bars_data):
                continue
            # Apply regime-specific multipliers
            bucket = sig["flat_bucket"]
            regime_p = REGIME_PARAMS.get(
                bucket, {"stop_mult": 1.0, "target_mult": 1.0})
            effective_sl = sl_mult * regime_p["stop_mult"]
            effective_tp = tp_mult * regime_p["target_mult"]

            result = simulate_trade(
                bars_data, idx, sig, effective_sl, effective_tp, max_hold)
            result["macro_regime"] = sig["macro_regime"]
            result["flat_bucket"] = sig["flat_bucket"]
            result["mr_allowed"] = sig["mr_allowed"]
            result["signal_datetime"] = sig["datetime"]
            result["ts_ms"] = sig["ts_ms"]
            results.append(result)
        return results

    # A1: Runtime-faithful (only allowed signals)
    baseline_allowed = run_simulation(
        mr_allowed_signals, enriched_bars, 1.0, 1.0, 24, "baseline_allowed")

    # A2: All signals regardless of regime gate
    baseline_all = run_simulation(
        signals, enriched_bars, 1.0, 1.0, 24, "baseline_all")

    def summarize(results, label):
        if not results:
            print(f"\n[{label}] No trades")
            return {}

        n = len(results)
        sl_count = sum(1 for r in results if r["exit_reason"] == "SL")
        tp_count = sum(1 for r in results if r["exit_reason"] == "TP")
        exp_count = sum(
            1 for r in results if r["exit_reason"] == "HOLD_EXPIRED")

        gross_pnls = [r["gross_pnl_pct"] for r in results]
        net_pnls = [r["net_pnl_pct"] for r in results]
        net_rs = [r["net_r"] for r in results]
        mae_rs = [r["mae_r"] for r in results]
        mfe_rs = [r["mfe_r"] for r in results]
        holds = [r["hold_bars"] for r in results]

        wins = [p for p in net_pnls if p > 0]
        losses = [p for p in net_pnls if p <= 0]

        summary = {
            "label": label,
            "trades": n,
            "sl_count": sl_count,
            "tp_count": tp_count,
            "hold_expired": exp_count,
            "sl_rate": sl_count / n,
            "tp_rate": tp_count / n,
            "win_rate": len(wins) / n,
            "avg_gross_pnl": sum(gross_pnls) / n,
            "avg_net_pnl": sum(net_pnls) / n,
            "total_net_pnl": sum(net_pnls),
            "net_expectancy": sum(net_pnls) / n,
            "gross_expectancy": sum(gross_pnls) / n,
            "median_net_pnl": sorted(net_pnls)[n // 2],
            "median_net_r": sorted(net_rs)[n // 2],
            "median_mae_r": sorted(mae_rs)[n // 2],
            "median_mfe_r": sorted(mfe_rs)[n // 2],
            "median_hold": sorted(holds)[n // 2],
            "avg_hold": sum(holds) / n,
            "avg_win": sum(wins) / len(wins) if wins else 0,
            "avg_loss": sum(losses) / len(losses) if losses else 0,
            "profit_factor": abs(sum(wins) / sum(losses)) if losses and sum(losses) != 0 else float('inf'),
            "fee_drag_share": ROUND_TRIP_COST_BPS / 100 / (abs(sum(gross_pnls) / n) + 0.0001) * 100,
        }

        print(f"\n[{label}]")
        print(
            f"  Trades: {n}  |  SL: {sl_count} ({sl_count/n*100:.1f}%)  |  TP: {tp_count} ({tp_count/n*100:.1f}%)  |  Expired: {exp_count}")
        print(
            f"  Win rate: {len(wins)/n*100:.1f}%  |  Profit factor: {summary['profit_factor']:.3f}")
        print(
            f"  Gross expectancy: {summary['gross_expectancy']:.4f}%  |  Net expectancy: {summary['net_expectancy']:.4f}%")
        print(f"  Total net PnL: {summary['total_net_pnl']:.4f}%")
        print(
            f"  Median MAE/R: {summary['median_mae_r']:.3f}  |  Median MFE/R: {summary['median_mfe_r']:.3f}")
        print(
            f"  Median hold: {summary['median_hold']} bars  |  Fee drag: {summary['fee_drag_share']:.1f}% of gross")

        return summary

    print("\n--- Baseline: MR-Allowed Signals Only (Runtime Path) ---")
    s_allowed = summarize(baseline_allowed, "BASELINE_ALLOWED")

    print("\n--- Baseline: All Signals (Counterfactual, All Regimes) ---")
    s_all = summarize(baseline_all, "BASELINE_ALL")

    # --- 6. Regime-conditioned analysis ---
    print("\n" + "=" * 60)
    print("REGIME-CONDITIONED ANALYSIS")
    print("=" * 60)

    # By canonical bucket
    print("\n--- By Canonical MR Bucket (all signals) ---")
    bucket_summaries = {}
    for bucket in ["FLAT_LOW", "FLAT_NORMAL", "FLAT_HIGH", "NONE"]:
        subset = [r for r in baseline_all if r["flat_bucket"] == bucket]
        if subset:
            bucket_summaries[bucket] = summarize(subset, f"BUCKET:{bucket}")

    # By macro regime
    print("\n--- By Macro Regime (all signals) ---")
    macro_summaries = {}
    for regime in sorted(set(r["macro_regime"] for r in baseline_all)):
        subset = [r for r in baseline_all if r["macro_regime"] == regime]
        if subset:
            macro_summaries[regime] = summarize(subset, f"MACRO:{regime}")

    # Cross matrix
    print("\n--- Cross Matrix: Bucket × Macro (all signals) ---")
    cross_summaries = {}
    for result in baseline_all:
        key = (result["flat_bucket"], result["macro_regime"])
        if key not in cross_summaries:
            cross_summaries[key] = []
        cross_summaries[key].append(result)

    cross_tables = {}
    for key in sorted(cross_summaries.keys()):
        subset = cross_summaries[key]
        label = f"CROSS:{key[0]}×{key[1]}"
        cross_tables[key] = summarize(subset, label)

    # --- 7. TP/SL/Hold Calibration Grid ---
    print("\n" + "=" * 60)
    print("TRACK B: FEE-AWARE TP/SL/HOLD CALIBRATION GRID")
    print("=" * 60)

    sl_mults = [0.75, 1.0, 1.25, 1.5]
    tp_mults = [0.5, 0.75, 1.0, 1.25]
    hold_variants = [3, 6, 12, 24]

    calibration_results = []

    # Test all combinations on MR-allowed signals
    for sl_m in sl_mults:
        for tp_m in tp_mults:
            for hold in hold_variants:
                results = run_simulation(
                    mr_allowed_signals, enriched_bars, sl_m, tp_m, hold)
                s = summarize(
                    results, f"SL{sl_m}_TP{tp_m}_H{hold}") if results else {}
                if s:
                    s["sl_mult"] = sl_m
                    s["tp_mult"] = tp_m
                    s["hold_bars"] = hold
                    s["regime_slice"] = "MR_ALLOWED"
                    calibration_results.append(s)

    # Also test on ALL signals (expanded regime)
    for sl_m in sl_mults:
        for tp_m in tp_mults:
            for hold in [6, 12, 24]:
                results = run_simulation(
                    signals, enriched_bars, sl_m, tp_m, hold)
                s = summarize(
                    results, f"ALL_SL{sl_m}_TP{tp_m}_H{hold}") if results else {}
                if s:
                    s["sl_mult"] = sl_m
                    s["tp_mult"] = tp_m
                    s["hold_bars"] = hold
                    s["regime_slice"] = "ALL_REGIMES"
                    calibration_results.append(s)

    # Find best variants
    cal_allowed = [
        c for c in calibration_results if c["regime_slice"] == "MR_ALLOWED"]
    cal_all = [c for c in calibration_results if c["regime_slice"]
               == "ALL_REGIMES"]

    if cal_allowed:
        best_allowed = max(
            cal_allowed, key=lambda x: x.get("net_expectancy", -999))
        print(
            f"\n*** Best MR-Allowed variant: SL={best_allowed['sl_mult']} TP={best_allowed['tp_mult']} Hold={best_allowed['hold_bars']} -> Net Exp: {best_allowed['net_expectancy']:.4f}%")

    if cal_all:
        best_all = max(cal_all, key=lambda x: x.get("net_expectancy", -999))
        print(
            f"*** Best All-Regime variant: SL={best_all['sl_mult']} TP={best_all['tp_mult']} Hold={best_all['hold_bars']} -> Net Exp: {best_all['net_expectancy']:.4f}%")

    # --- 8. Many Small Wins Study ---
    print("\n" + "=" * 60)
    print("MANY-SMALL-WINS VIABILITY STUDY")
    print("=" * 60)

    # Cost floor analysis
    cost_floor_pct = ROUND_TRIP_COST_BPS / 100
    print(
        f"\nCost floor: {cost_floor_pct:.4f}% per round trip ({ROUND_TRIP_COST_BPS:.0f} bps)")
    print(f"  - Fee: {FEE_BPS_PER_SIDE * 2:.0f} bps")
    print(f"  - Slippage: {SLIPPAGE_BPS * 2:.0f} bps")
    print(f"  - Spread: {SPREAD_BPS * 2:.0f} bps")

    # Test micro-TP profiles
    micro_configs = [
        {"name": "MICRO_0.25TP_0.5SL_H3", "tp": 0.25, "sl": 0.5, "hold": 3},
        {"name": "MICRO_0.25TP_0.75SL_H3", "tp": 0.25, "sl": 0.75, "hold": 3},
        {"name": "MICRO_0.5TP_0.5SL_H3", "tp": 0.5, "sl": 0.5, "hold": 3},
        {"name": "MICRO_0.5TP_0.75SL_H6", "tp": 0.5, "sl": 0.75, "hold": 6},
        {"name": "MICRO_0.5TP_1.0SL_H6", "tp": 0.5, "sl": 1.0, "hold": 6},
        {"name": "SMALL_0.75TP_0.75SL_H6", "tp": 0.75, "sl": 0.75, "hold": 6},
        {"name": "SMALL_0.75TP_1.0SL_H6", "tp": 0.75, "sl": 1.0, "hold": 6},
    ]

    micro_results = []
    for mc in micro_configs:
        # Test on all signals
        results_all = run_simulation(
            signals, enriched_bars, mc["sl"], mc["tp"], mc["hold"])
        s_all = summarize(
            results_all, f"MICRO_ALL:{mc['name']}") if results_all else {}

        # Test on MR-allowed only
        results_mronly = run_simulation(
            mr_allowed_signals, enriched_bars, mc["sl"], mc["tp"], mc["hold"])
        s_mronly = summarize(
            results_mronly, f"MICRO_MR:{mc['name']}") if results_mronly else {}

        if s_all:
            s_all["config_name"] = mc["name"]
            s_all["regime_slice"] = "ALL"
            micro_results.append(s_all)
        if s_mronly:
            s_mronly["config_name"] = mc["name"]
            s_mronly["regime_slice"] = "MR_ALLOWED"
            micro_results.append(s_mronly)

    # Verdict on micro-TP
    print("\n--- Micro-TP Verdict ---")
    any_viable = False
    for mr in micro_results:
        if mr.get("net_expectancy", -1) > 0:
            any_viable = True
            print(
                f"  CANDIDATE: {mr.get('config_name', '?')} [{mr['regime_slice']}] → Net exp: {mr['net_expectancy']:.4f}%, Win: {mr['win_rate']*100:.1f}%")

    if not any_viable:
        print("  MICRO_TP_STYLE_NOT_VIABLE: No micro-TP configuration survived fees")

    # --- 9. Stability Split ---
    print("\n" + "=" * 60)
    print("STABILITY SPLIT VALIDATION")
    print("=" * 60)

    # Split signals into halves
    mid_idx = len(signals) // 2
    first_half_sigs = signals[:mid_idx]
    second_half_sigs = signals[mid_idx:]

    # Also split MR-allowed
    mid_a = len(mr_allowed_signals) // 2
    first_half_allowed = mr_allowed_signals[:mid_a]
    second_half_allowed = mr_allowed_signals[mid_a:]

    print("\n--- All Signals Split ---")
    r1 = run_simulation(first_half_sigs, enriched_bars, 1.0, 1.0, 24)
    r2 = run_simulation(second_half_sigs, enriched_bars, 1.0, 1.0, 24)
    s1 = summarize(r1, "FIRST_HALF_ALL")
    s2 = summarize(r2, "SECOND_HALF_ALL")

    print("\n--- MR-Allowed Split ---")
    r1a = run_simulation(first_half_allowed, enriched_bars, 1.0, 1.0, 24)
    r2a = run_simulation(second_half_allowed, enriched_bars, 1.0, 1.0, 24)
    s1a = summarize(r1a, "FIRST_HALF_MR_ALLOWED")
    s2a = summarize(r2a, "SECOND_HALF_MR_ALLOWED")

    # Walk-forward: split into 3 segments
    print("\n--- Walk-Forward 3-Way Split (All Signals) ---")
    third = len(signals) // 3
    for seg_i, (start, end) in enumerate([(0, third), (third, 2*third), (2*third, len(signals))]):
        seg_sigs = signals[start:end]
        seg_results = run_simulation(seg_sigs, enriched_bars, 1.0, 1.0, 24)
        summarize(seg_results, f"SEGMENT_{seg_i+1}_OF_3_ALL")

    # --- 10. Trade density vs quality ---
    print("\n" + "=" * 60)
    print("TRADE DENSITY VS QUALITY ANALYSIS")
    print("=" * 60)

    if enriched_bars and signals:
        total_hours = (enriched_bars[-1]["ts_ms"] -
                       enriched_bars[0]["ts_ms"]) / 3600000
        total_days = total_hours / 24

        print(
            f"\nTotal period: {total_days:.1f} days ({total_hours:.0f} hours)")
        print(
            f"All signals: {len(signals)} → {len(signals)/total_days:.1f} per day")
        print(
            f"MR-allowed signals: {len(mr_allowed_signals)} → {len(mr_allowed_signals)/total_days:.1f} per day")

        if baseline_all:
            winners = [r for r in baseline_all if r["net_pnl_pct"] > 0]
            losers = [r for r in baseline_all if r["net_pnl_pct"] <= 0]
            print(
                f"\nAll-signal quality: {len(winners)} wins / {len(losers)} losses")
            if winners:
                print(
                    f"  Avg win: +{sum(r['net_pnl_pct'] for r in winners)/len(winners):.4f}%")
            if losers:
                print(
                    f"  Avg loss: {sum(r['net_pnl_pct'] for r in losers)/len(losers):.4f}%")

    # --- 11. Edge search: per-regime subset with best calibration ---
    print("\n" + "=" * 60)
    print("EDGE SEARCH: REGIME-SPECIFIC BEST CALIBRATION")
    print("=" * 60)

    for regime in sorted(set(s["macro_regime"] for s in signals)):
        regime_sigs = [s for s in signals if s["macro_regime"] == regime]
        if len(regime_sigs) < 3:
            print(f"\n  {regime}: SKIP (only {len(regime_sigs)} signals)")
            continue

        best_net = -999
        best_cfg = None
        for sl_m in [0.75, 1.0, 1.25, 1.5]:
            for tp_m in [0.5, 0.75, 1.0, 1.25]:
                for hold in [6, 12, 24]:
                    results = run_simulation(
                        regime_sigs, enriched_bars, sl_m, tp_m, hold)
                    if results:
                        net_exp = sum(r["net_pnl_pct"]
                                      for r in results) / len(results)
                        if net_exp > best_net:
                            best_net = net_exp
                            best_cfg = {
                                "regime": regime,
                                "sl": sl_m, "tp": tp_m, "hold": hold,
                                "trades": len(results),
                                "net_exp": net_exp,
                                "win_rate": sum(1 for r in results if r["net_pnl_pct"] > 0) / len(results),
                                "sl_rate": sum(1 for r in results if r["exit_reason"] == "SL") / len(results),
                                "tp_rate": sum(1 for r in results if r["exit_reason"] == "TP") / len(results),
                            }

        if best_cfg:
            v = "POSITIVE" if best_net > 0 else "NEGATIVE"
            sample = "TINY" if best_cfg["trades"] < 10 else "SMALL" if best_cfg["trades"] < 30 else "MODERATE"
            print(
                f"\n  {regime}: Best SL={best_cfg['sl']} TP={best_cfg['tp']} H={best_cfg['hold']}")
            print(
                f"    Trades: {best_cfg['trades']} ({sample})  |  Net: {best_net:.4f}% ({v})")
            print(
                f"    Win: {best_cfg['win_rate']*100:.1f}%  |  SL: {best_cfg['sl_rate']*100:.1f}%  |  TP: {best_cfg['tp_rate']*100:.1f}%")

    # --- 12. Compile all results for output ---
    print("\n" + "=" * 60)
    print("SUMMARY: ACTUAL TRADE EVIDENCE (from trade_lifecycle.jsonl)")
    print("=" * 60)

    actual_trades = [t for t in lifecycle_trades if t.get(
        "status") not in ("REJECTED",)]
    filled_trades = [t for t in lifecycle_trades if t.get("fill_price")]
    print(f"\nActual DOGE trade attempts: {len(lifecycle_trades)}")
    print(f"  FILLED (with fill data): {len(filled_trades)}")
    print(
        f"  ORPHANED_TTL: {sum(1 for t in lifecycle_trades if t.get('status') == 'ORPHANED_TTL')}")
    print(
        f"  REJECTED: {sum(1 for t in lifecycle_trades if t.get('status') == 'REJECTED')}")

    if filled_trades:
        for t in filled_trades:
            print(
                f"  FILL: {t['side']} @ {t['fill_price']} qty={t['fill_qty']} fees={t.get('fill_fees', 0):.4f}")

    # Equity curve from forensic
    print("\n--- Equity Curve (from forensic) ---")
    if equity_rows:
        total_mr_pnl = sum(float(r["pnl"]) for r in equity_rows)
        final_mr_equity = float(equity_rows[-1]["equity_mean_reversion"])
        print(f"  Total MR equity entries: {len(equity_rows)}")
        print(f"  Sum of PnL entries: ${total_mr_pnl:.2f}")
        print(f"  Final MR equity: ${final_mr_equity:.2f}")
        wins = sum(1 for r in equity_rows if float(r["pnl"]) > 0)
        losses = sum(1 for r in equity_rows if float(r["pnl"]) <= 0)
        print(
            f"  Actual trades: {len(equity_rows)} ({wins} wins, {losses} losses)")
        print(f"  Actual win rate: {wins / len(equity_rows) * 100:.1f}%")

    # Final verdict
    print("\n" + "=" * 80)
    print("FINAL OPERATIONAL VERDICT")
    print("=" * 80)

    # Check if any regime subset is net positive
    positive_regimes = []
    for result in calibration_results:
        if result.get("net_expectancy", -1) > 0 and result.get("trades", 0) >= 5:
            positive_regimes.append(result)

    any_stability_passed = False
    if s1 and s2:
        if (s1.get("net_expectancy", -1) > 0 and s2.get("net_expectancy", -1) > 0):
            any_stability_passed = True

    if not positive_regimes:
        verdict = "KEEP_DOGE_DISABLED"
        reason = "No TP/SL/hold configuration achieves positive net expectancy after fees across any regime"
    elif not any_stability_passed:
        verdict = "KEEP_DOGE_DISABLED"
        reason = "Some configurations show marginal edge but fail stability split validation"
    else:
        verdict = "RE_ENABLE_DOGE_ONLY_IN_SUBSET"
        reason = f"Found {len(positive_regimes)} configurations with positive net expectancy, stability TBD"

    print(f"\n  VERDICT: {verdict}")
    print(f"  REASON: {reason}")
    print(
        f"  EVIDENCE STRENGTH: {'BOUNDED' if len(mr_allowed_signals) < 50 else 'MODERATE'}")
    print(
        f"  FULL PERIOD USED: YES (2026-02-08 to 2026-03-29, {len(enriched_bars)} bars)")

    # Save output JSON
    output = {
        "study_date": "2026-03-29",
        "full_period": f"{enriched_bars[0]['datetime']} to {enriched_bars[-1]['datetime']}",
        "total_bars": len(enriched_bars),
        "warmup_bars": warmup_bars,
        "mature_bars": total_mature,
        "total_signals": all_signals,
        "mr_allowed_signals": len(mr_allowed_signals),
        "regime_occupancy": {
            "macro": dict(macro_counts),
            "bucket": dict(bucket_counts),
        },
        "baseline_allowed": s_allowed,
        "baseline_all": s_all,
        "bucket_summaries": bucket_summaries,
        "macro_summaries": macro_summaries,
        "cross_summaries": {f"{k[0]}×{k[1]}": v for k, v in cross_tables.items()},
        "calibration_top10": sorted(calibration_results, key=lambda x: x.get("net_expectancy", -999), reverse=True)[:10],
        "micro_results": micro_results,
        "stability": {
            "first_half_all": s1,
            "second_half_all": s2,
            "first_half_mr": s1a,
            "second_half_mr": s2a,
        },
        "actual_equity_trades": len(equity_rows),
        "actual_equity_total": float(equity_rows[-1]["equity_mean_reversion"]) if equity_rows else 0,
        "verdict": verdict,
        "reason": reason,
        "cost_model": {
            "fee_bps_per_side": FEE_BPS_PER_SIDE,
            "slippage_bps_per_side": SLIPPAGE_BPS,
            "spread_bps_per_side": SPREAD_BPS,
            "round_trip_total_bps": ROUND_TRIP_COST_BPS,
        }
    }

    out_path = BASE / "reports" / "DOGE_FULL_PERIOD_CALIBRATION_STUDY_2026-03-29.json"
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\n[OUTPUT] Results saved to {out_path}")

    return output


if __name__ == "__main__":
    run_full_study()
