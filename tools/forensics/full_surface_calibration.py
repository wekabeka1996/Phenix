"""
Full-Surface Recorder-Based Calibration & Bounded Backtest Study v2
===================================================================
Fixed: regime resolution, MR SL calculation, schema handling.
"""
import os
import sys
import json
import glob
import warnings
import math
from pathlib import Path
from collections import defaultdict, Counter
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from apps.reference.shared.data_primitives.market_bar_contract import read_named_csv_rows
from apps.reference.shared.data_primitives.ohlc_validator import (
    GAP_RESET_STATES,
    compute_true_range,
    validate_ohlc,
)

warnings.filterwarnings("ignore")

REC = ROOT / "data" / "recorder"
OUT = ROOT / "reports" / "FULL_SURFACE_CALIBRATION_RESULTS.json"

SYMBOLS_5M = ["BTCUSDT", "ETHUSDT", "SOLUSDT",
              "DOGEUSDT", "XRPUSDT", "BNBUSDT", "1000PEPEUSDT"]
SYMBOLS_15M = ["BTCUSDT", "ETHUSDT", "SOLUSDT",
               "DOGEUSDT", "XRPUSDT", "BNBUSDT"]

REGISTRY = {
    "BTCUSDT": "aurora", "ETHUSDT": "aurora", "SOLUSDT": "aurora",
    "XRPUSDT": "md_amr", "BNBUSDT": "md_amr",
    "DOGEUSDT": "mean_reversion", "1000PEPEUSDT": "llm_microstructure"
}
STRATEGY_CONFIGS = {
    "BTCUSDT": ["aurora", "md_amr"],
    "ETHUSDT": ["aurora", "md_amr"],
    "SOLUSDT": ["aurora", "md_amr"],
    "DOGEUSDT": ["aurora", "mean_reversion", "md_amr"],
    "XRPUSDT": ["aurora", "md_amr"],
    "BNBUSDT": ["aurora", "md_amr"],
    "1000PEPEUSDT": ["llm_microstructure"],
}

# Base SL pct per (strategy, symbol) - from config files
BASE_SL_PCT = {
    ("aurora", "BTCUSDT"): 0.50, ("aurora", "ETHUSDT"): 1.90, ("aurora", "SOLUSDT"): 1.35,
    ("aurora", "DOGEUSDT"): 1.512, ("aurora", "XRPUSDT"): 1.512, ("aurora", "BNBUSDT"): 1.512,
    ("md_amr", "BTCUSDT"): 0.50, ("md_amr", "ETHUSDT"): 1.90, ("md_amr", "SOLUSDT"): 1.35,
    ("md_amr", "DOGEUSDT"): 1.30, ("md_amr", "XRPUSDT"): 1.30, ("md_amr", "BNBUSDT"): 1.30,
}
# MR uses ATR*1.5 / price as SL - will be computed dynamically
MR_ATR_MULT = 1.5

COST_LIMIT_RT = 10
COST_MARKET_RT = 16
COST_MR_RT = 14

SIGNAL_THRESH_GLOBAL = 0.162
SIGNAL_THRESH_LOW = {"DOGEUSDT": 0.09, "XRPUSDT": 0.09}

SL_MULTS = [0.75, 1.00, 1.25, 1.50]
TP_MULTS = [0.50, 0.75, 1.00, 1.25]
HOLD_VARS = [3, 6, 12, 24]

MICRO_TP_PCTS = [0.25, 0.50, 0.75]
MICRO_SL_PCTS = [0.50, 0.75, 1.00]
MICRO_HOLDS = [3, 6]


def pf(v):
    if v is None or v in ("", "None", "nan", "NaN"):
        return np.nan
    try:
        return float(v)
    except:
        return np.nan


def load_symbol_bars(symbol, tf):
    """Load all recorder CSVs for symbol at given timeframe, return structured arrays."""
    all_rows = []
    accounting = {"bad_lines": 0, "missing_columns": Counter()}
    requested_columns = (
        "timestamp",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "ready",
        "regime",
        "regime_conf",
        "gap_state",
        "feat_obi",
        "feat_tfi",
        "feat_delta_price",
        "feat_absorption",
        "feat_ema_bias",
        "feat_volume_spike",
        "feat_depth_imbalance",
        "feat_volatility_state",
    )
    for dd in sorted(glob.glob(str(REC / "*"))):
        fn = os.path.join(dd, f"{symbol}_{tf}.csv")
        if not os.path.exists(fn):
            continue
        try:
            rows, stats = read_named_csv_rows(fn, requested_columns=requested_columns)
            all_rows.extend(rows)
            accounting["bad_lines"] += int(stats.get("bad_lines", 0))
            for column in stats.get("missing_columns", []):
                accounting["missing_columns"][column] += 1
        except:
            continue
    if not all_rows:
        return None

    filtered_rows = []
    invalid_rows = 0
    for row in all_rows:
        valid_ohlc, _ = validate_ohlc(
            row.get("open", 0),
            row.get("high", 0),
            row.get("low", 0),
            row.get("close", 0),
        )
        if not valid_ohlc:
            invalid_rows += 1
            continue
        filtered_rows.append(row)
    n = len(filtered_rows)
    if n == 0:
        return None
    d = {
        "n": n,
        "ts": np.zeros(n), "o": np.zeros(n), "h": np.zeros(n),
        "l": np.zeros(n), "c": np.zeros(n), "v": np.zeros(n),
        "ready": np.zeros(n, dtype=bool),
        "regime": [""]*n, "regime_conf": np.zeros(n),
        "gap_state": [""]*n,
        "obi": np.full(n, np.nan), "tfi": np.full(n, np.nan),
        "dp": np.full(n, np.nan), "ab": np.full(n, np.nan),
        "eb": np.full(n, np.nan), "vs": np.full(n, np.nan),
        "di": np.full(n, np.nan), "vst": np.full(n, np.nan),
        "reader_accounting": {
            **accounting,
            "invalid_ohlc_rows": invalid_rows,
        },
    }
    for i, r in enumerate(filtered_rows):
        d["ts"][i] = pf(r.get("timestamp", 0))
        d["o"][i] = pf(r.get("open", 0))
        d["h"][i] = pf(r.get("high", 0))
        d["l"][i] = pf(r.get("low", 0))
        d["c"][i] = pf(r.get("close", 0))
        d["v"][i] = pf(r.get("volume", 0))
        d["gap_state"][i] = str(r.get("gap_state", "") or "")
        rd = r.get("ready", "")
        d["ready"][i] = rd in ("True", "true", "1")
        # regime: prefer feat_regime, fallback to regime column
        fr = r.get("feat_regime", "")
        rc = r.get("regime", "")
        if fr and fr not in ("", "None", "nan", "PENDING"):
            d["regime"][i] = fr
        elif rc and rc not in ("", "None", "nan", "PENDING"):
            d["regime"][i] = rc
        else:
            d["regime"][i] = "UNKNOWN"
        d["regime_conf"][i] = pf(r.get("regime_conf", 0))
        d["obi"][i] = pf(r.get("feat_obi"))
        d["tfi"][i] = pf(r.get("feat_tfi"))
        d["dp"][i] = pf(r.get("feat_delta_price"))
        d["ab"][i] = pf(r.get("feat_absorption"))
        d["eb"][i] = pf(r.get("feat_ema_bias"))
        d["vs"][i] = pf(r.get("feat_volume_spike"))
        d["di"][i] = pf(r.get("feat_depth_imbalance"))
        d["vst"][i] = pf(r.get("feat_volatility_state"))
    d["valid_rows"] = n
    return d


def calc_atr(h, l, c, gap_states=None, period=14):
    n = len(c)
    tr = np.zeros(n)
    tr[0] = h[0]-l[0]
    for i in range(1, n):
        gap_state = gap_states[i] if gap_states is not None else ""
        tr[i] = float(
            compute_true_range(
                high_price=h[i],
                low_price=l[i],
                prev_close=c[i-1],
                gap_state=gap_state,
            )
        )
    atr = np.full(n, np.nan)
    if n >= period:
        reset_idx = 0
        for i in range(n):
            gap_state = gap_states[i] if gap_states is not None else ""
            if i > 0 and str(gap_state or "") in GAP_RESET_STATES:
                reset_idx = i
            if i - reset_idx + 1 >= period:
                atr[i] = np.mean(tr[i - period + 1:i + 1])
    return atr, tr


def calc_bb(c, w=20, ns=2.0):
    n = len(c)
    mid = np.full(n, np.nan)
    up = np.full(n, np.nan)
    lo = np.full(n, np.nan)
    for i in range(w-1, n):
        s = c[i-w+1:i+1]
        m = np.mean(s)
        sd = np.std(s, ddof=0)
        mid[i] = m
        up[i] = m+ns*sd
        lo[i] = m-ns*sd
    return mid, up, lo


def calc_rsi(c, p=14):
    n = len(c)
    rsi = np.full(n, np.nan)
    if n < p+1:
        return rsi
    d = np.diff(c)
    g = np.where(d > 0, d, 0)
    ls = np.where(d < 0, -d, 0)
    ag = np.mean(g[:p])
    al = np.mean(ls[:p])
    rsi[p] = 100-100/(1+ag/(al+1e-15))
    for i in range(p, len(d)):
        ag = (ag*(p-1)+g[i])/p
        al = (al*(p-1)+ls[i])/p
        rsi[i+1] = 100-100/(1+ag/(al+1e-15))
    return rsi


def vol_bucket(atr, c):
    pa = atr/np.where(c > 0, c, 1)*100
    n = len(pa)
    b = ["FLAT_NORMAL"]*n
    v = ~np.isnan(pa)
    if np.sum(v) < 20:
        return b
    p20 = np.nanpercentile(pa[v], 20)
    p80 = np.nanpercentile(pa[v], 80)
    for i in range(n):
        if np.isnan(pa[i]):
            continue
        if pa[i] < p20:
            b[i] = "FLAT_LOW"
        elif pa[i] > p80:
            b[i] = "FLAT_HIGH"
    return b


def aurora_signals(B, symbol):
    n = B["n"]
    th = SIGNAL_THRESH_LOW.get(symbol, SIGNAL_THRESH_GLOBAL)
    sigs = []
    for i in range(n):
        if not B["ready"][i]:
            continue
        vals = [B["obi"][i], B["tfi"][i], B["dp"][i], B["ab"]
                [i], B["eb"][i], B["vs"][i], B["di"][i], B["vst"][i]]
        if any(np.isnan(v) for v in vals):
            continue
        sc = 0.30*vals[0]+0.20*vals[1]+0.15*vals[2]+0.10*vals[3] + \
            0.10*vals[4]+0.05*vals[5]+0.05*vals[6]+0.05*vals[7]
        if abs(sc) < th:
            continue
        sigs.append({"i": i, "side": "LONG" if sc > 0 else "SHORT", "sc": abs(sc),
                     "entry": B["c"][i], "regime": B["regime"][i], "rc": B["regime_conf"][i]})
    return sigs


def mr_signals(B, symbol, bw=20, bns=2.1):
    """Generate MR signals. DOGE uses bb_std=2.1, entry_threshold=0.05."""
    n = B["n"]
    c = B["c"]
    mid, up, lo = calc_bb(c, bw, bns)
    rsi = calc_rsi(c, 14)
    sigs = []
    for i in range(max(bw, 15), n):
        if not B["ready"][i]:
            continue
        if np.isnan(lo[i]) or np.isnan(up[i]) or np.isnan(rsi[i]):
            continue
        bw_val = up[i]-lo[i]
        if bw_val < 1e-10:
            continue
        pct_b = (c[i]-lo[i])/bw_val
        side = None
        if pct_b < 0.05 and rsi[i] < 35:
            side = "LONG"  # oversold
        elif pct_b > 0.95 and rsi[i] > 65:
            side = "SHORT"  # overbought
        if side is None:
            continue
        sigs.append({"i": i, "side": side, "sc": abs(pct_b-0.5),
                     "entry": c[i], "regime": B["regime"][i], "rc": B["regime_conf"][i],
                     "bb_mid": mid[i], "bb_up": up[i], "bb_lo": lo[i]})
    return sigs


def mdamr_signals(B, symbol, window=12, zthr=2.2):
    n = B["n"]
    c = B["c"]
    sigs = []
    for i in range(window, n):
        if not B["ready"][i]:
            continue
        seg = c[i-window:i]
        m = np.mean(seg)
        s = np.std(seg, ddof=0)
        if s < 1e-10:
            continue
        z = (c[i]-m)/s
        if abs(z) < zthr:
            continue
        sigs.append({"i": i, "side": "LONG" if z < -zthr else "SHORT", "sc": abs(z),
                     "entry": c[i], "regime": B["regime"][i], "rc": B["regime_conf"][i]})
    return sigs


def sim_trade(B, idx, side, sl_pct, tp_pct, max_hold, cost_bps):
    n = B["n"]
    entry = B["c"][idx]
    if entry <= 0 or sl_pct <= 0 or tp_pct <= 0:
        return None
    if side == "LONG":
        stop = entry*(1-sl_pct/100)
        tgt = entry*(1+tp_pct/100)
    else:
        stop = entry*(1+sl_pct/100)
        tgt = entry*(1-tp_pct/100)
    sl_d = abs(entry-stop)
    if sl_d < 1e-12:
        return None
    mae = 0.0
    mfe = 0.0
    ep = None
    et = "HOLD_EXPIRED"
    hb = 0
    for j in range(idx+1, min(idx+1+max_hold, n)):
        hb += 1
        bh = B["h"][j]
        bl = B["l"][j]
        if side == "LONG":
            adv = entry-bl
            fav = bh-entry
        else:
            adv = bh-entry
            fav = entry-bl
        mae = max(mae, adv)
        mfe = max(mfe, fav)
        if side == "LONG":
            if bl <= stop:
                ep = stop
                et = "SL"
                break
            if bh >= tgt:
                ep = tgt
                et = "TP"
                break
        else:
            if bh >= stop:
                ep = stop
                et = "SL"
                break
            if bl <= tgt:
                ep = tgt
                et = "TP"
                break
    if ep is None:
        last = min(idx+max_hold, n-1)
        ep = B["c"][last]
    if hb == 0:
        return None
    if side == "LONG":
        gp = (ep-entry)/entry*100
    else:
        gp = (entry-ep)/entry*100
    np_ = gp-cost_bps/100
    return {"et": et, "gp": gp, "np": np_, "r": gp/sl_pct, "nr": np_/sl_pct,
            "mae_r": mae/sl_d, "mfe_r": mfe/sl_d, "hb": hb}


def metrics(trades):
    if not trades:
        return {"trades": 0}
    n = len(trades)
    net = [t["np"] for t in trades]
    gro = [t["gp"] for t in trades]
    sl = sum(1 for t in trades if t["et"] == "SL")
    tp = sum(1 for t in trades if t["et"] == "TP")
    he = sum(1 for t in trades if t["et"] == "HOLD_EXPIRED")
    wins = sum(1 for x in net if x > 0)
    an = np.mean(net)
    ag = np.mean(gro)
    tw = sum(x for x in net if x > 0)
    tl = abs(sum(x for x in net if x < 0))
    pf_ = tw/tl if tl > 0 else (float('inf') if tw > 0 else 0)
    fd = abs((ag-an)/ag*100) if ag != 0 else 0
    return {"trades": n, "sl": sl, "tp": tp, "he": he,
            "sl_rate": round(sl/n*100, 2), "tp_rate": round(tp/n*100, 2),
            "win_rate": round(wins/n*100, 2),
            "net_exp": round(an, 4), "gross_exp": round(ag, 4),
            "total_net": round(sum(net), 2),
            "med_mae_r": round(float(np.median([t["mae_r"] for t in trades])), 4),
            "med_mfe_r": round(float(np.median([t["mfe_r"] for t in trades])), 4),
            "med_hold": round(float(np.median([t["hb"] for t in trades])), 1),
            "pf": round(pf_, 4), "fd": round(fd, 2)}


def verdict(m, min_n=20):
    if m["trades"] < min_n:
        return "INSUFFICIENT_EVIDENCE"
    if m["net_exp"] > 0 and m["pf"] > 1.2:
        return "KEEP_AS_IS"
    if m["net_exp"] > 0:
        return "CALIBRATION_CANDIDATE"
    if m["gross_exp"] > 0 and m["pf"] > 0.8:
        return "CALIBRATION_CANDIDATE"
    return "KEEP_DISABLED"


def micro_v(m):
    if m["trades"] < 20:
        return "MICRO_INSUFFICIENT"
    if m["net_exp"] > 0 and m["fd"] < 80:
        return "MICRO_BOUNDED_CANDIDATE"
    if m["net_exp"] > 0:
        return "MICRO_VIABLE_IN_SUBSET"
    return "MICRO_NOT_VIABLE"


def cj(obj):
    if isinstance(obj, dict):
        return {k: cj(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [cj(v) for v in obj]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating, float)):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return round(float(obj), 6)
    if isinstance(obj, np.ndarray):
        return cj(obj.tolist())
    return obj


def main():
    R = {"meta": {"date": "2026-03-29", "study": "full_surface_calibration_v2"},
         "universe": [], "coverage": [], "baseline": [], "regime_slices": [],
         "calibration": [], "micro_tp": [], "stability": [], "ranking": [], "verdicts": []}
    surfaces = []

    for symbol in SYMBOLS_5M:
        print(f"\n{'='*60}\n  {symbol}\n{'='*60}")
        B5 = load_symbol_bars(symbol, 300)
        B15 = load_symbol_bars(symbol, 900) if symbol in SYMBOLS_15M else None
        if B5 is None:
            print("  No 5m data")
            continue

        atr5, _ = calc_atr(B5["h"], B5["l"], B5["c"], B5.get("gap_state"), period=14)
        buckets = vol_bucket(atr5, B5["c"])
        atr15 = None
        if B15:
            atr15, _ = calc_atr(B15["h"], B15["l"], B15["c"], B15.get("gap_state"), period=14)

        n5 = B5["n"]
        rdy = int(np.sum(B5["ready"]))
        # Regime distribution (ready bars only)
        rdist = Counter()
        for i in range(n5):
            if B5["ready"][i]:
                rdist[B5["regime"][i]] += 1
        print(f"  5m: {n5} bars, {rdy} ready")
        print(f"  Regimes: {dict(rdist.most_common(8))}")

        for strategy in STRATEGY_CONFIGS.get(symbol, []):
            print(f"\n  --- {symbol} x {strategy} ---")
            primary = REGISTRY.get(symbol, "") == strategy

            # Cost model
            if strategy == "mean_reversion":
                cost = COST_MR_RT
            else:
                cost = COST_LIMIT_RT

            # Generate signals
            if strategy == "aurora":
                sigs = aurora_signals(B5, symbol)
                use_B = B5
                use_atr = atr5
            elif strategy == "mean_reversion":
                sigs = mr_signals(B5, symbol)
                use_B = B5
                use_atr = atr5
            elif strategy == "md_amr":
                if B15:
                    sigs = mdamr_signals(B15, symbol)
                    use_B = B15
                    use_atr = atr15
                else:
                    sigs = []
                    use_B = B5
                    use_atr = atr5
            else:
                sigs = []
                use_B = B5
                use_atr = atr5

            nsig = len(sigs)
            print(f"  Signals: {nsig}")

            R["universe"].append({"symbol": symbol, "strategy": strategy,
                                  "assigned": "primary" if primary else "dormant",
                                  "replay_ok": nsig >= 5, "cal_ok": nsig >= 20,
                                  "signals": nsig, "note": f"{'PRIMARY' if primary else 'DORMANT'}"})

            R["coverage"].append({"symbol": symbol, "strategy": strategy,
                                  "full_period": f"{n5} bars (all dates in recorder)",
                                  "used_period": "ALL", "full_used": True,
                                  "ready_bars": rdy, "total_bars": n5, "signals": nsig,
                                  "dropped": n5-rdy, "drop_reason": "warmup/not_ready",
                                  "coverage_pct": round(rdy/n5*100, 1) if n5 > 0 else 0})

            if nsig < 5:
                print(f"  SKIP: {nsig} signals")
                R["baseline"].append(
                    {"symbol": symbol, "strategy": strategy, "trades": 0, "verdict": "INSUFFICIENT_EVIDENCE"})
                R["verdicts"].append({"symbol": symbol, "strategy": strategy,
                                      "baseline": "NO_DATA", "calibrated": "NO_DATA", "feasible": primary,
                                      "stability": "UNTESTABLE", "verdict": "INSUFFICIENT_EVIDENCE",
                                      "note": f"{nsig} signals"})
                continue

            # Base SL
            if strategy == "mean_reversion":
                # ATR-based: avg ATR / price * 100 * ATR_mult
                valid_atr = use_atr[~np.isnan(use_atr)]
                valid_c = use_B["c"][~np.isnan(use_atr)]
                valid_c = valid_c[valid_c > 0]
                if len(valid_atr) > 0 and len(valid_c) > 0:
                    base_sl = float(
                        np.mean(valid_atr/valid_c[:len(valid_atr)])*100*MR_ATR_MULT)
                else:
                    base_sl = 0.5
                base_tp = base_sl * 1.0  # RR=1 baseline
            else:
                base_sl = BASE_SL_PCT.get((strategy, symbol), 1.0)
                base_tp = base_sl  # 1:1 baseline

            print(f"  Base SL: {base_sl:.4f}%, TP: {base_tp:.4f}%")

            # Baseline trades
            bl_trades = []
            for s in sigs:
                t = sim_trade(use_B, s["i"], s["side"],
                              base_sl, base_tp, 24, cost)
                if t:
                    t["regime"] = s["regime"]
                    t["rc"] = s["rc"]
                    t["side"] = s["side"]
                    t["bkt"] = buckets[s["i"]] if strategy != "md_amr" and s["i"] < len(
                        buckets) else "FLAT_NORMAL"
                    bl_trades.append(t)

            bm = metrics(bl_trades)
            bv = verdict(bm)
            print(
                f"  Trades:{bm['trades']} NetExp:{bm.get('net_exp', '?')} WR:{bm.get('win_rate', '?')}% PF:{bm.get('pf', '?')} => {bv}")
            R["baseline"].append(
                {"symbol": symbol, "strategy": strategy, **bm, "verdict": bv})

            # Regime slices - MACRO
            macro = defaultdict(list)
            for t in bl_trades:
                macro[t["regime"]].append(t)
            for rg, trs in sorted(macro.items()):
                m = metrics(trs)
                ss = "SUFFICIENT" if len(trs) >= 20 else "SMALL" if len(
                    trs) >= 10 else "TINY"
                R["regime_slices"].append({"symbol": symbol, "strategy": strategy,
                                           "layer": "macro", "value": rg, **m, "strength": ss})

            # Bucket slices
            bkts = defaultdict(list)
            for t in bl_trades:
                bkts[t["bkt"]].append(t)
            for bk, trs in sorted(bkts.items()):
                m = metrics(trs)
                ss = "SUFFICIENT" if len(trs) >= 20 else "SMALL" if len(
                    trs) >= 10 else "TINY"
                R["regime_slices"].append({"symbol": symbol, "strategy": strategy,
                                           "layer": "bucket", "value": bk, **m, "strength": ss})

            # Cross matrix
            cross = defaultdict(list)
            for t in bl_trades:
                cross[f"{t['bkt']}x{t['regime']}"].append(t)
            for ck, trs in sorted(cross.items()):
                if len(trs) >= 5:
                    m = metrics(trs)
                    ss = "SUFFICIENT" if len(trs) >= 20 else "SMALL" if len(
                        trs) >= 10 else "TINY"
                    R["regime_slices"].append({"symbol": symbol, "strategy": strategy,
                                               "layer": "cross", "value": ck, **m, "strength": ss})

            # Calibration grid
            best_net = -999
            best_var = ""
            if nsig >= 20:
                for slm in SL_MULTS:
                    for tpm in TP_MULTS:
                        for hv in HOLD_VARS:
                            sl = base_sl*slm
                            tp = base_tp*tpm
                            ct = []
                            for s in sigs:
                                t = sim_trade(
                                    use_B, s["i"], s["side"], sl, tp, hv, cost)
                                if t:
                                    ct.append(t)
                            m = metrics(ct)
                            vn = f"SL{slm}_TP{tpm}_H{hv}"
                            ne = m.get("net_exp", -999)
                            if ne is not None and ne > best_net:
                                best_net = ne
                                best_var = vn
                            R["calibration"].append({"symbol": symbol, "strategy": strategy,
                                                     "variant": vn, "slm": slm, "tpm": tpm, "hold": hv, **m})
                print(f"  Best cal: {best_var} net={best_net:.4f}%")

            # Micro-TP
            if nsig >= 20:
                for mtp in MICRO_TP_PCTS:
                    for msl in MICRO_SL_PCTS:
                        for mh in MICRO_HOLDS:
                            ct = []
                            for s in sigs:
                                t = sim_trade(
                                    use_B, s["i"], s["side"], msl, mtp, mh, cost)
                                if t:
                                    ct.append(t)
                            m = metrics(ct)
                            mv = micro_v(m)
                            R["micro_tp"].append({"symbol": symbol, "strategy": strategy,
                                                  "name": f"MICRO_{mtp}TP_{msl}SL_H{mh}", **m, "verdict": mv})

            # Stability
            if len(bl_trades) >= 10:
                mid = len(bl_trades)//2
                m1 = metrics(bl_trades[:mid])
                m2 = metrics(bl_trades[mid:])
                stab = "STABLE" if (m1["net_exp"] > 0) == (
                    m2["net_exp"] > 0) else "UNSTABLE"
                R["stability"].append({"symbol": symbol, "strategy": strategy,
                                       "first": m1, "second": m2, "stability": stab})
                print(
                    f"  Stability: {stab} (H1:{m1['net_exp']:.4f} H2:{m2['net_exp']:.4f})")

            # Collect for ranking
            surfaces.append({"symbol": symbol, "strategy": strategy, "primary": primary,
                             "nsig": nsig, "net_exp": bm.get("net_exp"), "pf": bm.get("pf"),
                             "bv": bv, "best_cal_net": best_net if nsig >= 20 else None, "best_cal_var": best_var})

    # Rankings
    ranked = sorted(surfaces, key=lambda x: (
        x.get("net_exp") or -999), reverse=True)
    for i, s in enumerate(ranked, 1):
        R["ranking"].append({"rank": i, **s})

    # Final verdicts
    for s in surfaces:
        sym = s["symbol"]
        strat = s["strategy"]
        cal = [c for c in R["calibration"] if c["symbol"]
               == sym and c["strategy"] == strat]
        bc = max(cal, key=lambda x: x.get("net_exp", -999)) if cal else None
        bcs = "NO_DATA"
        if bc:
            ne = bc.get("net_exp", 0)
            if ne and ne > 0 and bc.get("pf", 0) > 1.0:
                bcs = "NET_POSITIVE"
            elif ne and ne > 0:
                bcs = "MARGINAL"
            else:
                bcs = "NET_NEGATIVE"

        st = [x for x in R["stability"] if x["symbol"]
              == sym and x["strategy"] == strat]
        stab = st[0]["stability"] if st else "UNTESTABLE"

        if s["nsig"] < 20:
            fv = "INSUFFICIENT_EVIDENCE"
        elif s["bv"] == "KEEP_AS_IS" and stab == "STABLE":
            fv = "KEEP_AS_IS"
        elif bcs in ("NET_POSITIVE", "MARGINAL") and stab == "STABLE":
            fv = "CALIBRATION_CANDIDATE"
        elif bcs == "NET_POSITIVE":
            fv = "REENABLE_ONLY_IN_SUBSET"
        elif s["bv"] == "KEEP_DISABLED":
            fv = "KEEP_DISABLED"
        else:
            fv = "CALIBRATION_CANDIDATE"

        note = f"Best: {bc['variant']} net={bc.get('net_exp', '?')}%" if bc else ""
        R["verdicts"].append({"symbol": sym, "strategy": strat,
                              "baseline": s["bv"], "calibrated": bcs, "feasible": s["primary"],
                              "stability": stab, "verdict": fv, "note": note})

    R = cj(R)
    with open(str(OUT), "w", encoding="utf-8") as f:
        json.dump(R, f, indent=2, default=str)
    print(f"\n\nDone. {OUT}")
    print(f"Surfaces: {len(surfaces)}, Cal grid: {len(R['calibration'])}")


if __name__ == "__main__":
    main()
