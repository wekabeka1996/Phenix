"""
Shadow-regime enrichment for symbols missing regime in recorder CSVs.
Loads shadow telemetry regime labels, pairs them with recorder bar timestamps,
and computes aurora regime-conditioned calibration for DOGE/XRP/BNB/PEPE.
"""
import json
import os
import csv
import glob
from collections import defaultdict

BASE = os.path.join(os.path.dirname(__file__), "..", "..")
SHADOW_BASE = os.path.join(BASE, "data", "shadow_telemetry", "snapshots")
RECORDER_BASE = os.path.join(BASE, "data", "recorder")
OUT_PATH = os.path.join(
    BASE, "reports", "SHADOW_REGIME_AURORA_CALIBRATION_RESULTS.json")

FEE_RT_BPS = 10

SYMBOLS = ["DOGEUSDT", "XRPUSDT", "BNBUSDT", "1000PEPEUSDT"]


def load_shadow_regimes(symbol):
    """Load regime labels keyed by ts_ms from shadow telemetry."""
    regimes = {}
    base = os.path.join(SHADOW_BASE, symbol)
    if not os.path.isdir(base):
        return regimes
    for d in sorted(os.listdir(base)):
        dpath = os.path.join(base, d)
        if not os.path.isdir(dpath):
            continue
        for fn in sorted(os.listdir(dpath)):
            if not fn.endswith(".jsonl"):
                continue
            fpath = os.path.join(dpath, fn)
            with open(fpath, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except:
                        continue
                    ts = obj.get("ts_ms", 0)
                    r = obj.get("regime", {})
                    if isinstance(r, dict):
                        label = r.get("regime", "UNKNOWN")
                    else:
                        label = "UNKNOWN"
                    if label and label != "MISSING":
                        regimes[ts] = label
    return regimes


def load_recorder_bars(symbol, tf="300"):
    """Load recorder bars for symbol, sorted by timestamp."""
    bars = []
    pattern = os.path.join(RECORDER_BASE, "*", "%s_%s.csv" % (symbol, tf))
    files = sorted(glob.glob(pattern))
    seen_ts = set()
    for fpath in files:
        with open(fpath, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Try multiple timestamp column names
                ts = row.get("timestamp") or row.get(
                    "close_time_ms") or row.get("close_time") or ""
                try:
                    ts_ms = int(float(ts))
                except:
                    continue
                # Normalize: if ts looks like seconds (< 1e12), convert to ms
                if ts_ms < 1e12:
                    ts_ms = int(ts_ms * 1000)
                if ts_ms in seen_ts:
                    continue
                seen_ts.add(ts_ms)
                try:
                    c = float(row.get("close", 0))
                    h = float(row.get("high", 0))
                    l = float(row.get("low", 0))
                    o = float(row.get("open", 0))
                except:
                    continue
                if c <= 0:
                    continue

                # Extract features for aurora signal reconstruction
                # Recorder uses feat_ prefix
                obi = safe_float(row.get("feat_obi") or row.get("obi"))
                tfi = safe_float(row.get("feat_tfi") or row.get("tfi"))
                ema_bias = safe_float(
                    row.get("feat_ema_bias") or row.get("ema_bias"))
                volume_spike = safe_float(
                    row.get("feat_volume_spike") or row.get("volume_spike"))
                depth_imbalance = safe_float(
                    row.get("feat_depth_imbalance") or row.get("depth_imbalance"))
                volatility_state = safe_float(
                    row.get("feat_volatility_state") or row.get("volatility_state"))
                absorption = safe_float(row.get("feat_absorption") or row.get(
                    "feat_absorption_ratio") or row.get("absorption_ratio"))
                delta_price = safe_float(row.get("feat_delta_price") or row.get(
                    "feat_delta_price_norm") or row.get("delta_price_norm"))

                bars.append({
                    "ts_ms": ts_ms,
                    "o": o, "h": h, "l": l, "c": c,
                    "obi": obi, "tfi": tfi, "ema_bias": ema_bias,
                    "volume_spike": volume_spike, "depth_imbalance": depth_imbalance,
                    "volatility_state": volatility_state, "absorption": absorption,
                    "delta_price": delta_price,
                })
    bars.sort(key=lambda x: x["ts_ms"])
    return bars


def safe_float(v):
    if v is None:
        return None
    try:
        return float(v)
    except:
        return None


def aurora_score(bar):
    """Compute aurora composite score from bar features."""
    weights = {
        "obi": 0.30, "tfi": 0.20, "delta_price": 0.15, "absorption": 0.10,
        "ema_bias": 0.10, "volume_spike": 0.05, "depth_imbalance": 0.05,
        "volatility_state": 0.05,
    }
    total = 0.0
    valid = 0
    for feat, w in weights.items():
        val = bar.get(feat)
        if val is not None:
            total += w * val
            valid += 1
    if valid < 4:
        return None
    return total


def enrich_and_calibrate(symbol, regime_map, bars, sl_pcts, tp_pcts, hold_bars_list):
    """Run aurora calibration with shadow regime enrichment."""
    fee_pct = FEE_RT_BPS / 10000.0
    threshold = 0.15

    # Pair bars with nearest regime (within 5min window)
    for bar in bars:
        ts = bar["ts_ms"]
        # Try exact match, then +/- 1 bar width (300000ms)
        for offset in [0, -300000, 300000, -600000, 600000]:
            r = regime_map.get(ts + offset)
            if r:
                bar["regime"] = r
                break
        else:
            bar["regime"] = "UNKNOWN"

    # Compute aurora scores
    for bar in bars:
        bar["score"] = aurora_score(bar)

    # Generate signals
    signals = []
    for i, bar in enumerate(bars):
        s = bar.get("score")
        if s is None:
            continue
        if abs(s) < threshold:
            continue
        direction = "LONG" if s > 0 else "SHORT"
        signals.append((i, direction, s, bar["regime"]))

    results = {
        "symbol": symbol,
        "total_bars": len(bars),
        "regime_enriched": sum(1 for b in bars if b.get("regime", "UNKNOWN") != "UNKNOWN"),
        "regime_distribution": {},
        "signals_generated": len(signals),
        "baselines": {},
        "regime_slices": {},
        "calibration_grid": [],
        "best_config": None,
        "stability": {},
    }

    # Regime distribution
    rdist = defaultdict(int)
    for b in bars:
        rdist[b.get("regime", "UNKNOWN")] += 1
    results["regime_distribution"] = dict(rdist)

    def sim_and_metrics(signal_list, sl_pct, tp_pct, hold_n, label=""):
        trades = []
        for (idx, direction, score, regime) in signal_list:
            entry_price = bars[idx]["c"]
            d = 1 if direction == "LONG" else -1
            exit_price = None
            exit_reason = "hold_expired"
            mae = 0.0
            mfe = 0.0
            for j in range(idx+1, min(idx+hold_n+1, len(bars))):
                fb = bars[j]
                fh, fl, fc = fb["h"], fb["l"], fb["c"]
                if d == 1:
                    exc_best = (fh - entry_price) / entry_price
                    exc_worst = (fl - entry_price) / entry_price
                else:
                    exc_best = (entry_price - fl) / entry_price
                    exc_worst = (entry_price - fh) / entry_price
                mfe = max(mfe, exc_best)
                mae = min(mae, exc_worst)
                # SL
                if d == 1 and fl <= entry_price * (1 - sl_pct):
                    exit_price = entry_price * (1 - sl_pct)
                    exit_reason = "sl"
                    break
                elif d == -1 and fh >= entry_price * (1 + sl_pct):
                    exit_price = entry_price * (1 + sl_pct)
                    exit_reason = "sl"
                    break
                # TP
                if d == 1 and fh >= entry_price * (1 + tp_pct):
                    exit_price = entry_price * (1 + tp_pct)
                    exit_reason = "tp"
                    break
                elif d == -1 and fl <= entry_price * (1 - tp_pct):
                    exit_price = entry_price * (1 - tp_pct)
                    exit_reason = "tp"
                    break

            if exit_price is None:
                end_idx = min(idx + hold_n, len(bars) - 1)
                exit_price = bars[end_idx]["c"]

            pnl_raw = d * (exit_price - entry_price) / entry_price
            pnl_net = pnl_raw - fee_pct
            trades.append({
                "pnl_net": pnl_net, "pnl_raw": pnl_raw,
                "exit_reason": exit_reason, "regime": regime,
                "mae": mae, "mfe": mfe,
            })

        if not trades:
            return {"label": label, "n": 0, "net_exp": 0, "win_rate": 0, "pf": 0}
        n = len(trades)
        wins = [t for t in trades if t["pnl_net"] > 0]
        losses = [t for t in trades if t["pnl_net"] <= 0]
        gw = sum(t["pnl_net"] for t in wins) if wins else 0
        gl = abs(sum(t["pnl_net"] for t in losses)) if losses else 0.001
        return {
            "label": label, "n": n,
            "net_exp": sum(t["pnl_net"] for t in trades) / n,
            "win_rate": len(wins) / n,
            "pf": gw / gl if gl > 0 else 0,
            "tp_count": sum(1 for t in trades if t["exit_reason"] == "tp"),
            "sl_count": sum(1 for t in trades if t["exit_reason"] == "sl"),
            "trades": trades,
        }

    # Baseline
    baseline = sim_and_metrics(signals, 0.005, 0.005, 12, "baseline")
    results["baselines"]["all"] = {k: v for k,
                                   v in baseline.items() if k != "trades"}

    # Regime slices
    for regime in sorted(rdist.keys()):
        rsigs = [(i, d, s, r) for (i, d, s, r) in signals if r == regime]
        if len(rsigs) < 3:
            continue
        m = sim_and_metrics(rsigs, 0.005, 0.005, 12,
                            "%s_%s" % (symbol, regime))
        results["regime_slices"][regime] = {
            k: v for k, v in m.items() if k != "trades"}

    # Calibration grid
    best_exp = -999
    best = None
    for sl in sl_pcts:
        for tp in tp_pcts:
            for hold in hold_bars_list:
                m = sim_and_metrics(signals, sl, tp, hold,
                                    "sl%.3f_tp%.3f_h%d" % (sl, tp, hold))
                entry = {"sl_pct": sl, "tp_pct": tp, "hold_bars": hold}
                entry.update({k: v for k, v in m.items() if k != "trades"})
                results["calibration_grid"].append(entry)
                if m["n"] >= 5 and m["net_exp"] > best_exp:
                    best_exp = m["net_exp"]
                    best = entry
    results["best_config"] = best

    # Stability (first half vs second half of signals)
    if len(signals) >= 10:
        mid = len(signals) // 2
        h1_sigs = signals[:mid]
        h2_sigs = signals[mid:]
        if best:
            m1 = sim_and_metrics(
                h1_sigs, best["sl_pct"], best["tp_pct"], best["hold_bars"], "h1")
            m2 = sim_and_metrics(
                h2_sigs, best["sl_pct"], best["tp_pct"], best["hold_bars"], "h2")
            results["stability"] = {
                "h1": {k: v for k, v in m1.items() if k != "trades"},
                "h2": {k: v for k, v in m2.items() if k != "trades"},
                "stable": m1["n"] >= 3 and m2["n"] >= 3 and m1["net_exp"] > 0 and m2["net_exp"] > 0,
            }

    return results


def main():
    all_results = {}
    sl_pcts = [0.003, 0.005, 0.007, 0.010]
    tp_pcts = [0.003, 0.005, 0.007, 0.010]
    hold_bars_list = [6, 12, 18, 24]

    for sym in SYMBOLS:
        print("Processing %s..." % sym)
        regime_map = load_shadow_regimes(sym)
        print("  Loaded %d shadow regime entries" % len(regime_map))
        bars = load_recorder_bars(sym)
        print("  Loaded %d recorder bars" % len(bars))
        if not bars:
            print("  SKIPPED (no bars)")
            continue
        res = enrich_and_calibrate(
            sym, regime_map, bars, sl_pcts, tp_pcts, hold_bars_list)
        all_results[sym] = res
        print("  Signals: %d, Regime enriched: %d/%d" % (
            res["signals_generated"], res["regime_enriched"], res["total_bars"]))
        bl = res["baselines"].get("all", {})
        print("  Baseline: n=%d, net_exp=%.4f%%, wr=%.1f%%, pf=%.2f" % (
            bl.get("n", 0), bl.get("net_exp", 0)*100, bl.get("win_rate", 0)*100, bl.get("pf", 0)))
        best = res.get("best_config")
        if best:
            print("  Best config: sl=%.3f tp=%.3f hold=%d -> net_exp=%.4f%% n=%d pf=%.2f" % (
                best["sl_pct"], best["tp_pct"], best["hold_bars"],
                best["net_exp"]*100, best["n"], best["pf"]))

        # Print regime slices
        for regime, m in sorted(res["regime_slices"].items()):
            print("    %s: n=%d, net_exp=%.4f%%" %
                  (regime, m["n"], m["net_exp"]*100))

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, default=str)
    print("\nResults written to %s" % OUT_PATH)


if __name__ == "__main__":
    main()
