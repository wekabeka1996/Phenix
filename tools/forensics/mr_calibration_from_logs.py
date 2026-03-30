"""
Mean Reversion calibration using MR bar logs (bars_300s.jsonl).
Fixes the ATR artifact from recorder-based calibration.
Fee-aware, regime-conditioned, with calibration grid and stability splits.
"""
import json
import os
import sys
from collections import defaultdict

LOG_PATH = os.path.join(os.path.dirname(__file__), "..",
                        "..", "logs", "mean_reversion", "bars_300s.jsonl")
OUT_PATH = os.path.join(os.path.dirname(__file__), "..",
                        "..", "reports", "MR_CALIBRATION_FROM_LOGS_RESULTS.json")

FEE_RT_BPS = 10  # GTX maker round-trip
FEE_MARKET_RT_BPS = 16  # taker round-trip


def load_bars():
    bars_by_sym = defaultdict(list)
    with open(LOG_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            sym = obj.get("symbol", "")
            bars_by_sym[sym].append(obj)
    # Sort by ts_ms
    for sym in bars_by_sym:
        bars_by_sym[sym].sort(key=lambda x: x.get("ts_ms", 0))
    return bars_by_sym


def sim_trades(bars, sl_mult, tp_mult, hold_bars, fee_rt_bps=FEE_RT_BPS):
    """Simulate MR trades from signal bars using forward bars for exit."""
    fee_pct = fee_rt_bps / 10000.0
    trades = []
    sig_indices = []

    for i, bar in enumerate(bars):
        sig = bar.get("signal", {})
        stype = sig.get("type", "")
        if stype not in ("LONG", "SHORT"):
            continue
        sig_indices.append(i)

    for idx in sig_indices:
        bar = bars[idx]
        sig = bar.get("signal", {})
        stype = sig["type"]
        ind = bar.get("indicators", {})
        ohlcv = bar.get("ohlcv", {})
        params = bar.get("params") or {}

        entry_price = float(ohlcv.get("c", 0))
        if entry_price <= 0:
            continue

        atr_val = ind.get("atr")
        if atr_val is None:
            continue
        atr_val = float(atr_val)
        if atr_val <= 0:
            continue

        regime = sig.get("regime", "UNKNOWN")

        # Compute SL/TP from ATR
        p_stop_mult = params.get("stop_mult", 1.0)
        p_target_mult = params.get("target_mult", 1.0)

        raw_sl = atr_val * p_stop_mult * sl_mult
        raw_tp = atr_val * p_target_mult * tp_mult

        direction = 1 if stype == "LONG" else -1

        # Walk forward bars for exit
        exit_price = None
        exit_reason = "hold_expired"
        exit_bar_idx = min(idx + hold_bars, len(bars) - 1)
        mae = 0.0
        mfe = 0.0

        for j in range(idx + 1, min(idx + hold_bars + 1, len(bars))):
            fbar = bars[j]
            fohlcv = fbar.get("ohlcv", {})
            fh = float(fohlcv.get("h", 0))
            fl = float(fohlcv.get("l", 0))
            fc = float(fohlcv.get("c", 0))

            if fh <= 0 or fl <= 0:
                continue

            # Check extremes for MAE/MFE
            if direction == 1:  # LONG
                excursion_best = (fh - entry_price) / entry_price
                excursion_worst = (fl - entry_price) / entry_price
            else:  # SHORT
                excursion_best = (entry_price - fl) / entry_price
                excursion_worst = (entry_price - fh) / entry_price

            mfe = max(mfe, excursion_best)
            mae = min(mae, excursion_worst)

            # Check SL hit
            if direction == 1:
                if fl <= entry_price - raw_sl:
                    exit_price = entry_price - raw_sl
                    exit_reason = "sl"
                    exit_bar_idx = j
                    break
            else:
                if fh >= entry_price + raw_sl:
                    exit_price = entry_price + raw_sl
                    exit_reason = "sl"
                    exit_bar_idx = j
                    break

            # Check TP hit
            if direction == 1:
                if fh >= entry_price + raw_tp:
                    exit_price = entry_price + raw_tp
                    exit_reason = "tp"
                    exit_bar_idx = j
                    break
            else:
                if fl <= entry_price - raw_tp:
                    exit_price = entry_price - raw_tp
                    exit_reason = "tp"
                    exit_bar_idx = j
                    break

        if exit_price is None:
            # Hold expired - use close of last bar
            if exit_bar_idx < len(bars):
                fohlcv = bars[exit_bar_idx].get("ohlcv", {})
                exit_price = float(fohlcv.get("c", entry_price))
            else:
                exit_price = entry_price

        pnl_raw = direction * (exit_price - entry_price) / entry_price
        pnl_net = pnl_raw - fee_pct

        trades.append({
            "entry_ts": bar.get("ts_human", ""),
            "symbol": bar.get("symbol", ""),
            "direction": stype,
            "regime": regime,
            "entry": entry_price,
            "exit": exit_price,
            "exit_reason": exit_reason,
            "pnl_raw": pnl_raw,
            "pnl_net": pnl_net,
            "mae": mae,
            "mfe": mfe,
            "atr_pct": atr_val / entry_price,
            "sl_pct": raw_sl / entry_price,
            "tp_pct": raw_tp / entry_price,
            "hold_bars_used": exit_bar_idx - bars.index(bar) if bar in bars else 0,
        })

    return trades


def compute_metrics(trades, label=""):
    if not trades:
        return {"label": label, "n": 0, "net_exp": 0, "win_rate": 0, "avg_win": 0, "avg_loss": 0, "pf": 0, "max_dd": 0}

    n = len(trades)
    wins = [t for t in trades if t["pnl_net"] > 0]
    losses = [t for t in trades if t["pnl_net"] <= 0]

    net_pnl = sum(t["pnl_net"] for t in trades)
    gross_win = sum(t["pnl_net"] for t in wins) if wins else 0
    gross_loss = abs(sum(t["pnl_net"] for t in losses)) if losses else 0.001

    wr = len(wins) / n if n > 0 else 0
    avg_w = gross_win / len(wins) if wins else 0
    avg_l = -gross_loss / len(losses) if losses else 0
    pf = gross_win / gross_loss if gross_loss > 0 else 0

    # Max drawdown (cumulative)
    cum = 0
    peak = 0
    max_dd = 0
    for t in trades:
        cum += t["pnl_net"]
        if cum > peak:
            peak = cum
        dd = peak - cum
        if dd > max_dd:
            max_dd = dd

    # Fee drag
    fee_total = n * (FEE_RT_BPS / 10000.0)
    raw_pnl = sum(t["pnl_raw"] for t in trades)
    fee_drag = fee_total / \
        abs(raw_pnl) if abs(raw_pnl) > 0.0001 else float("inf")

    return {
        "label": label,
        "n": n,
        "net_exp": net_pnl / n if n > 0 else 0,
        "total_net": net_pnl,
        "win_rate": wr,
        "avg_win": avg_w,
        "avg_loss": avg_l,
        "pf": pf,
        "max_dd_pct": max_dd,
        "fee_drag_share": min(fee_drag, 99.9),
        "tp_count": sum(1 for t in trades if t["exit_reason"] == "tp"),
        "sl_count": sum(1 for t in trades if t["exit_reason"] == "sl"),
        "hold_expired": sum(1 for t in trades if t["exit_reason"] == "hold_expired"),
    }


def run_calibration():
    print("Loading MR bar logs...")
    bars_by_sym = load_bars()

    results = {
        "source": "logs/mean_reversion/bars_300s.jsonl",
        "symbols": {},
        "baselines": {},
        "regime_slices": {},
        "calibration_grid": [],
        "stability_splits": {},
        "verdicts": {},
    }

    # Per-symbol stats
    for sym in sorted(bars_by_sym.keys()):
        bars = bars_by_sym[sym]
        n_total = len(bars)
        n_signals = sum(1 for b in bars if b.get(
            "signal", {}).get("type") in ("LONG", "SHORT"))
        n_bb = sum(1 for b in bars if b.get("indicators", {}).get(
            "bb", {}).get("upper") is not None)

        regime_dist = defaultdict(int)
        for b in bars:
            r = b.get("signal", {}).get("regime", "UNKNOWN")
            regime_dist[r] += 1

        results["symbols"][sym] = {
            "total_bars": n_total,
            "signals": n_signals,
            "bb_populated": n_bb,
            "date_range": [bars[0].get("ts_human", ""), bars[-1].get("ts_human", "")] if bars else [],
            "regime_distribution": dict(regime_dist),
        }
        print("  %s: %d bars, %d signals, %d with BB" %
              (sym, n_total, n_signals, n_bb))

    # Baseline: current config (sl_mult=1.0, tp_mult=1.0, hold=12 bars = 1h at 5m)
    print("\nRunning baselines (current config)...")
    for sym in sorted(bars_by_sym.keys()):
        bars = bars_by_sym[sym]
        trades = sim_trades(bars, sl_mult=1.0, tp_mult=1.0, hold_bars=12)
        m = compute_metrics(trades, label="%s_baseline" % sym)
        results["baselines"][sym] = m
        print("  %s: n=%d, net_exp=%.4f%%, wr=%.1f%%, pf=%.2f" %
              (sym, m["n"], m["net_exp"]*100, m["win_rate"]*100, m["pf"]))

    # Regime slices
    print("\nRegime slices...")
    for sym in sorted(bars_by_sym.keys()):
        bars = bars_by_sym[sym]
        all_trades = sim_trades(bars, sl_mult=1.0, tp_mult=1.0, hold_bars=12)

        regime_trades = defaultdict(list)
        for t in all_trades:
            regime_trades[t["regime"]].append(t)

        sym_regimes = {}
        for regime in sorted(regime_trades.keys()):
            rtrades = regime_trades[regime]
            m = compute_metrics(rtrades, label="%s_%s" % (sym, regime))
            sym_regimes[regime] = m
            print("  %s/%s: n=%d, net_exp=%.4f%%" %
                  (sym, regime, m["n"], m["net_exp"]*100))

        results["regime_slices"][sym] = sym_regimes

    # Calibration grid
    print("\nCalibration grid...")
    sl_mults = [0.8, 1.0, 1.2, 1.5]
    tp_mults = [0.6, 0.8, 1.0, 1.2, 1.5]
    hold_options = [6, 12, 18, 24]  # 30m, 1h, 1.5h, 2h at 5m bars

    best_by_sym = {}

    for sym in sorted(bars_by_sym.keys()):
        bars = bars_by_sym[sym]
        best_net_exp = -999
        best_config = None

        for sl_m in sl_mults:
            for tp_m in tp_mults:
                for hold in hold_options:
                    trades = sim_trades(bars, sl_mult=sl_m,
                                        tp_mult=tp_m, hold_bars=hold)
                    m = compute_metrics(
                        trades, label="%s_sl%.1f_tp%.1f_h%d" % (sym, sl_m, tp_m, hold))

                    entry = {
                        "symbol": sym,
                        "sl_mult": sl_m,
                        "tp_mult": tp_m,
                        "hold_bars": hold,
                    }
                    entry.update(m)
                    results["calibration_grid"].append(entry)

                    if m["n"] >= 5 and m["net_exp"] > best_net_exp:
                        best_net_exp = m["net_exp"]
                        best_config = entry

        best_by_sym[sym] = best_config
        if best_config:
            print("  %s best: sl=%.1f tp=%.1f hold=%d -> net_exp=%.4f%% n=%d pf=%.2f" % (
                sym, best_config["sl_mult"], best_config["tp_mult"], best_config["hold_bars"],
                best_config["net_exp"]*100, best_config["n"], best_config["pf"]))

    # Stability splits (first half vs second half)
    print("\nStability splits...")
    for sym in sorted(bars_by_sym.keys()):
        bars = bars_by_sym[sym]
        mid = len(bars) // 2
        h1 = bars[:mid]
        h2 = bars[mid:]

        best = best_by_sym.get(sym)
        if not best:
            results["stability_splits"][sym] = {
                "h1": {"n": 0}, "h2": {"n": 0}, "stable": False}
            continue

        t1 = sim_trades(
            h1, sl_mult=best["sl_mult"], tp_mult=best["tp_mult"], hold_bars=best["hold_bars"])
        t2 = sim_trades(
            h2, sl_mult=best["sl_mult"], tp_mult=best["tp_mult"], hold_bars=best["hold_bars"])

        m1 = compute_metrics(t1, "%s_h1" % sym)
        m2 = compute_metrics(t2, "%s_h2" % sym)

        # Stability: both halves positive, or sign agreement
        stable = (m1["n"] >= 3 and m2["n"] >= 3 and
                  m1["net_exp"] > 0 and m2["net_exp"] > 0)

        results["stability_splits"][sym] = {
            "h1": m1,
            "h2": m2,
            "stable": stable,
        }
        print("  %s: H1 exp=%.4f%% (n=%d), H2 exp=%.4f%% (n=%d), stable=%s" % (
            sym, m1["net_exp"]*100, m1["n"], m2["net_exp"]*100, m2["n"], stable))

    # Verdicts
    print("\nVerdicts...")
    for sym in sorted(bars_by_sym.keys()):
        baseline = results["baselines"].get(sym, {})
        best = best_by_sym.get(sym)
        stability = results["stability_splits"].get(sym, {})

        n = baseline.get("n", 0)
        base_exp = baseline.get("net_exp", 0)

        if n < 10:
            verdict = "INSUFFICIENT_EVIDENCE"
            reason = "Only %d signals (need >=10)" % n
        elif best and best["net_exp"] > 0 and stability.get("stable"):
            verdict = "CALIBRATION_CANDIDATE"
            reason = "Best config net_exp=%.4f%%, stable across halves" % (
                best["net_exp"]*100)
        elif best and best["net_exp"] > 0 and not stability.get("stable"):
            verdict = "BOUNDED_POTENTIAL"
            reason = "Best config positive but unstable across halves"
        elif base_exp <= 0 and (not best or best["net_exp"] <= 0):
            verdict = "KEEP_DISABLED"
            reason = "No config produces positive net expectancy"
        else:
            verdict = "KEEP_DISABLED"
            reason = "Insufficient evidence of consistent edge"

        results["verdicts"][sym] = {
            "verdict": verdict,
            "reason": reason,
            "baseline_n": n,
            "baseline_net_exp": base_exp,
            "best_net_exp": best["net_exp"] if best else None,
            "best_config": {
                "sl_mult": best["sl_mult"],
                "tp_mult": best["tp_mult"],
                "hold_bars": best["hold_bars"],
            } if best else None,
        }
        print("  %s: %s - %s" % (sym, verdict, reason))

    # Write output
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, default=str)
    print("\nResults written to: %s" % OUT_PATH)

    return results


if __name__ == "__main__":
    run_calibration()
