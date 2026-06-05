"""
P0 Before/After Validation Script

Replays the same audited window with P0 config changes applied offline.

Changes being validated:
1. strategist sensitivity: 3.0 → 1.5 (reverse tanh from recorder, reapply)
2. DZ vol_threshold: 0.95 → 0.98
3. DZ FE volatility sma_length: 2 → 10, window_sec: 5 → 60 (cannot replay FE, estimate only)
4. regime hysteresis_bars: 3 → 2 (cannot replay detector, estimate from raw_regime in audit log)
5. uncertain_cutoff: 0.22 → 0.15 (cannot replay detector, estimate from audit log)

What CAN be replayed exactly:
- strategist sensitivity change (reverse+reapply tanh from recorded pillar_strategist)
- DZ vol_threshold change (use recorded volatility_state)
- full kernel math reconstruction with new pillar values

What CANNOT be replayed (estimated):
- FE volatility re-computation (would need raw tick data, not bar data)
- regime detector re-classification (would need full bar pipeline)

The FE volatility fix and regime changes are ESTIMATED ONLY:
- FE volatility fix: we estimate that restoring sma_length=10 reduces volatility_state saturation
  from 57% to ~15-20% (based on the bimodal distribution where the middle bucket 0.0-0.95 holds 42%)
- Regime changes: we estimate UNCERTAIN rate drops from ~38% to ~20% (hysteresis carry halved + cutoff demotion removed)
"""

import csv
import json
import math
import os
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
TIMEFRAME = 300

# ========================
# BEFORE config
# ========================
BEFORE = {
    "strategist_sensitivity": 3.0,
    "dz_vol_threshold": 0.95,
    "btc_signal_threshold": 0.162,
    "eth_signal_threshold": 0.0221,
    "sol_signal_threshold": 0.0232,
    "admission_shield_floor": 0.75,
    "score_multiplier": 1.0,
    "neutral_threshold": 0.05,
}

# ========================
# AFTER config
# ========================
AFTER = {
    "strategist_sensitivity": 1.5,
    "dz_vol_threshold": 0.98,
    "btc_signal_threshold": 0.162,
    "eth_signal_threshold": 0.0221,
    "sol_signal_threshold": 0.0232,
    "admission_shield_floor": 0.75,
    "score_multiplier": 1.0,
    "neutral_threshold": 0.05,
}

# Per-symbol regime thresholds (unchanged)
BTC_RT = {"HIGH_VOLATILITY": 0.18, "LOW_VOLATILITY": 0.14, "TREND_UP": 0.12,
          "TREND_DOWN": 0.12, "UNCERTAIN": 99.0, "MEAN_REVERSION": 0.075, "DEFAULT": 99.0}
ETH_RT = {"HIGH_VOLATILITY": 1.3, "LOW_VOLATILITY": 0.85,
          "MEAN_REVERSION": 1.05, "TREND_UP": 1.0, "TREND_DOWN": 1.0, "DEFAULT": 1.0}
SOL_RT = {"HIGH_VOLATILITY": 1.15, "LOW_VOLATILITY": 0.75,
          "MEAN_REVERSION": 1.0, "TREND_UP": 1.0, "TREND_DOWN": 1.0, "DEFAULT": 1.0}
GLOBAL_RT = {"HIGH_VOLATILITY": 0.18, "LOW_VOLATILITY": 0.14, "TREND_UP": 0.12,
             "TREND_DOWN": 0.12, "UNCERTAIN": 99.0, "MEAN_REVERSION": 0.075, "DEFAULT": 0.12}
SYM_RT = {"BTCUSDT": BTC_RT, "ETHUSDT": ETH_RT, "SOLUSDT": SOL_RT}
SYM_BT = {"BTCUSDT": 0.162, "ETHUSDT": 0.0221, "SOLUSDT": 0.0232}

CTX_MULTS = {"HIGH_VOLATILITY": 0.30, "UNCERTAIN": 0.55, "TREND_UP": 0.85,
             "TREND_DOWN": 0.85, "LOW_VOLATILITY": 1.0, "MEAN_REVERSION": 0.90}

RECORDER_DIR = Path("c:/Users/user/Music/Phenix/data/recorder")
OUTPUT_DIR = Path(
    "c:/Users/user/Music/Phenix/reports/p0_before_after_validation")


def safe_float(val, default=None):
    if val is None or val == "" or val == "None":
        return default
    try:
        v = float(val)
        return v if math.isfinite(v) else default
    except (ValueError, TypeError):
        return default


def reverse_tanh_strategist(recorded_strat, old_sensitivity, new_sensitivity):
    """
    The recorded feat_pillar_strategist = tanh(deviation * old_sensitivity).
    This is the raw tanh output [-1, +1], NOT premultiplied by weight.
    deviation = atanh(recorded_strat) / old_sensitivity.
    new_strat = tanh(deviation * new_sensitivity).
    """
    if recorded_strat is None:
        return None

    # Clamp to valid atanh range
    clamped = max(-0.9999, min(0.9999, recorded_strat))

    try:
        deviation = math.atanh(clamped) / old_sensitivity
    except (ValueError, OverflowError):
        deviation = math.copysign(3.0 / old_sensitivity, clamped)

    new_strat = math.tanh(deviation * new_sensitivity)
    return new_strat


def estimate_shield(sym, vol_state, spread_bps, regime, dz_vol_threshold):
    """Estimate shield multiplier with given DZ threshold."""
    # DangerZone
    dz_veto = False
    if vol_state is not None and vol_state > dz_vol_threshold:
        dz_veto = True
    if spread_bps is not None and spread_bps > 50.0:
        dz_veto = True
    if dz_veto:
        return 0.0

    # Context shield
    ctx = CTX_MULTS.get(regime, 0.80)
    # Memory: unknown
    return max(0.0, min(1.0, ctx))


def resolve_factor(regime, regime_thresholds):
    if regime and regime in regime_thresholds:
        raw = regime_thresholds[regime]
    elif "DEFAULT" in regime_thresholds:
        raw = regime_thresholds["DEFAULT"]
    else:
        return None
    return float(raw) if raw and raw > 0 else None


def compute_kernel(sym, pillar_sum, regime, shield_mult, cfg):
    base_threshold = SYM_BT.get(sym, 0.162)
    regime_thresholds = SYM_RT.get(sym, GLOBAL_RT)

    if pillar_sum is None or not math.isfinite(pillar_sum):
        return {"deferred": True, "defer_reason": "INVALID"}

    s_clamped = max(-1.0, min(1.0, pillar_sum * cfg["score_multiplier"]))
    admission_pre = s_clamped  # linear mode

    if shield_mult == 0.0:
        adm_shield = 0.0
    else:
        adm_shield = max(shield_mult, cfg["admission_shield_floor"])

    decision_score = admission_pre * adm_shield

    factor = resolve_factor(regime, regime_thresholds)
    if factor is None:
        return {"deferred": True, "defer_reason": f"MISSING_REGIME:{regime}", "decision_score": decision_score}

    thr_buy = base_threshold * factor
    thr_sell = base_threshold * factor

    if decision_score >= thr_buy:
        side = "buy"
    elif decision_score <= -thr_sell:
        side = "sell"
    else:
        side = ""

    return {
        "deferred": False,
        "decision_score": decision_score,
        "thr_buy": thr_buy,
        "thr_sell": thr_sell,
        "distance_to_buy": thr_buy - decision_score,
        "side": side,
        "shield_mult": shield_mult,
    }


def load_bars(symbol):
    bars = {}
    start = datetime(2026, 3, 28)
    end = datetime(2026, 4, 8)
    d = start
    while d <= end:
        ds = d.strftime("%Y-%m-%d")
        fp = RECORDER_DIR / ds / f"{symbol}_{TIMEFRAME}.csv"
        if fp.exists():
            with open(fp, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    ts = row.get("timestamp", "")
                    try:
                        int(ts)
                        bars[ts] = row
                    except:
                        pass
        d += timedelta(days=1)
    return [b for _, b in sorted(bars.items())]


def run_scenario(symbol, scenario_name, cfg, old_sensitivity=3.0, new_sensitivity=None):
    bars = load_bars(symbol)
    results = []
    dz_vol_threshold = cfg["dz_vol_threshold"]

    for row in bars:
        ts_utc = row.get("datetime", "")
        regime = row.get("feat_regime", "") or row.get("regime", "")

        strat_recorded = safe_float(row.get("feat_pillar_strategist"))
        tact = safe_float(row.get("feat_pillar_tactician"))
        op = safe_float(row.get("feat_pillar_operator"))

        if new_sensitivity is not None and strat_recorded is not None:
            # Reverse tanh and recompute
            strat_new = reverse_tanh_strategist(
                strat_recorded, old_sensitivity, new_sensitivity)
        else:
            strat_new = strat_recorded

        # Recompute pillar_sum with new strategist (weights: tact=0.60, op=0.25, strat=0.15)
        if strat_new is not None and tact is not None and op is not None:
            pillar_sum = 0.60 * tact + 0.25 * op + 0.15 * strat_new
        else:
            pillar_sum = safe_float(row.get("feat_pillar_sum"))

        vol_state = safe_float(row.get("feat_volatility_state"))
        spread_bps = safe_float(row.get("feat_spread_bps"))

        shield_mult = estimate_shield(
            symbol, vol_state, spread_bps, regime, dz_vol_threshold)
        kernel = compute_kernel(symbol, pillar_sum, regime, shield_mult, cfg)

        # Classification
        if kernel.get("deferred"):
            fc = "E_UNKNOWN"
        elif kernel.get("side") == "buy":
            fc = "D_BUY_EMITTED"
        elif kernel.get("side") == "sell":
            if kernel.get("decision_score", -999) >= kernel.get("thr_buy", 999):
                fc = "B_BUY_REACHABLE_NOT_SELECTED"
            else:
                fc = "A_BUY_UNREACHABLE"
        else:
            if kernel.get("decision_score", -999) >= kernel.get("thr_buy", 999):
                fc = "B_BUY_REACHABLE_NOT_SELECTED"
            else:
                fc = "A_BUY_UNREACHABLE"

        results.append({
            "ts_utc": ts_utc,
            "symbol": symbol,
            "regime": regime,
            "pillar_strategist": strat_new,
            "pillar_tactician": tact,
            "pillar_operator": op,
            "pillar_sum": pillar_sum,
            "decision_score": kernel.get("decision_score"),
            "thr_buy": kernel.get("thr_buy"),
            "distance_to_buy": kernel.get("distance_to_buy"),
            "side": kernel.get("side", ""),
            "shield_mult": shield_mult,
            "failure_class": fc,
            "dz_veto": 1 if shield_mult == 0.0 else 0,
            "uncertain": 1 if regime == "UNCERTAIN" else 0,
        })

    return results


def compute_summary(results, label):
    total = len(results)
    valid = [r for r in results if r["pillar_sum"] is not None]

    strats = [r["pillar_strategist"]
              for r in valid if r["pillar_strategist"] is not None]
    psums = [r["pillar_sum"] for r in valid if r["pillar_sum"] is not None]
    dscores = [r["decision_score"]
               for r in valid if r["decision_score"] is not None]
    dtbs = [r["distance_to_buy"]
            for r in valid if r["distance_to_buy"] is not None]

    fc = defaultdict(int)
    sides = defaultdict(int)
    for r in results:
        fc[r["failure_class"]] += 1
        sides[r.get("side", "") or "neutral"] += 1

    dz_veto = sum(r["dz_veto"] for r in results)
    unc = sum(r["uncertain"] for r in results)

    psum_pos = sum(1 for v in psums if v > 0)
    ds_pos = sum(1 for v in dscores if v > 0.0001)

    return {
        "label": label,
        "total_bars": total,
        "strat_min": min(strats) if strats else None,
        "strat_max": max(strats) if strats else None,
        "strat_mean": sum(strats)/len(strats) if strats else None,
        "strat_pct_below_0": sum(1 for s in strats if s < 0) / len(strats) * 100 if strats else 0,
        "strat_pct_below_neg03": sum(1 for s in strats if s < -0.3) / len(strats) * 100 if strats else 0,
        "strat_pct_below_neg05": sum(1 for s in strats if s < -0.5) / len(strats) * 100 if strats else 0,
        "psum_min": min(psums) if psums else None,
        "psum_max": max(psums) if psums else None,
        "psum_mean": sum(psums)/len(psums) if psums else None,
        "psum_pct_positive": psum_pos / len(psums) * 100 if psums else 0,
        "psum_positive_count": psum_pos,
        "ds_max": max(dscores) if dscores else None,
        "ds_pct_positive": ds_pos / len(dscores) * 100 if dscores else 0,
        "min_dtb": min(dtbs) if dtbs else None,
        "failure_class": dict(fc),
        "failure_pct": {k: round(v/total*100, 2) for k, v in fc.items()},
        "sides": dict(sides),
        "side_pct": {k: round(v/len(valid)*100, 2) for k, v in sides.items()} if valid else {},
        "dz_veto_count": dz_veto,
        "dz_veto_pct": round(dz_veto/total*100, 1),
        "uncertain_count": unc,
        "uncertain_pct": round(unc/total*100, 1),
    }


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    all_summaries = {}
    for sym in SYMBOLS:
        print(f"\n{'='*60}")
        print(f"Processing {sym}...")
        print(f"{'='*60}")

        # BEFORE scenario (original config)
        before = run_scenario(sym, "BEFORE", BEFORE,
                              old_sensitivity=3.0, new_sensitivity=None)
        bs = compute_summary(before, "BEFORE")

        # AFTER scenario (new config: sensitivity 1.5, DZ threshold 0.98)
        after = run_scenario(sym, "AFTER", AFTER,
                             old_sensitivity=3.0, new_sensitivity=1.5)
        asa = compute_summary(after, "AFTER")

        all_summaries[sym] = {"before": bs, "after": asa}

        # Print comparison
        print(f"\n  {'Metric':<35} {'BEFORE':>15} {'AFTER':>15} {'DELTA':>15}")
        print(f"  {'-'*80}")

        comparisons = [
            ("Strategist mean", bs["strat_mean"], asa["strat_mean"]),
            ("Strategist min", bs["strat_min"], asa["strat_min"]),
            ("Strategist max", bs["strat_max"], asa["strat_max"]),
            ("Strategist % < 0", bs["strat_pct_below_0"],
             asa["strat_pct_below_0"]),
            ("Strategist % < -0.3",
             bs["strat_pct_below_neg03"], asa["strat_pct_below_neg03"]),
            ("Pillar_sum mean", bs["psum_mean"], asa["psum_mean"]),
            ("Pillar_sum max", bs["psum_max"], asa["psum_max"]),
            ("Pillar_sum % > 0", bs["psum_pct_positive"],
             asa["psum_pct_positive"]),
            ("Pillar_sum positive bars",
             bs["psum_positive_count"], asa["psum_positive_count"]),
            ("Decision_score max", bs["ds_max"], asa["ds_max"]),
            ("Min distance to BUY", bs["min_dtb"], asa["min_dtb"]),
            ("DZ veto rate %", bs["dz_veto_pct"], asa["dz_veto_pct"]),
            ("UNCERTAIN rate %", bs["uncertain_pct"], asa["uncertain_pct"]),
        ]

        for name, bv, av in comparisons:
            if bv is not None and av is not None:
                delta = av - bv
                print(f"  {name:<35} {bv:>15.4f} {av:>15.4f} {delta:>+15.4f}")
            else:
                print(f"  {name:<35} {'N/A':>15} {'N/A':>15}")

        print(f"\n  Failure classification BEFORE: {bs['failure_class']}")
        print(f"  Failure classification AFTER:  {asa['failure_class']}")
        print(f"  Side distribution BEFORE: {bs['sides']}")
        print(f"  Side distribution AFTER:  {asa['sides']}")

        # Write after CSVs
        csv_path = OUTPUT_DIR / f"{sym}_after_bar_level.csv"
        if after:
            fieldnames = list(after[0].keys())
            with open(csv_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(after)

    # Write combined summary
    json_path = OUTPUT_DIR / "before_after_summary.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(all_summaries, f, indent=2, default=str)
    print(f"\nSummary written: {json_path}")

    # Print aggregate
    print(f"\n{'='*60}")
    print("AGGREGATE BEFORE/AFTER")
    print(f"{'='*60}")

    for label in ["before", "after"]:
        total_bars = sum(all_summaries[s][label]
                         ["total_bars"] for s in SYMBOLS)
        buy_unreachable = sum(all_summaries[s][label]["failure_class"].get(
            "A_BUY_UNREACHABLE", 0) for s in SYMBOLS)
        buy_emitted = sum(all_summaries[s][label]["failure_class"].get(
            "D_BUY_EMITTED", 0) for s in SYMBOLS)
        buy_reachable = sum(all_summaries[s][label]["failure_class"].get(
            "B_BUY_REACHABLE_NOT_SELECTED", 0) for s in SYMBOLS)
        buy_gate_blocked = sum(all_summaries[s][label]["failure_class"].get(
            "C_BUY_REACHABLE_GATE_BLOCKED", 0) for s in SYMBOLS)
        dz_total = sum(all_summaries[s][label]
                       ["dz_veto_count"] for s in SYMBOLS)
        unc_total = sum(all_summaries[s][label]
                        ["uncertain_count"] for s in SYMBOLS)
        sell_total = sum(all_summaries[s][label]["sides"].get(
            "sell", 0) for s in SYMBOLS)
        buy_total = sum(all_summaries[s][label]
                        ["sides"].get("buy", 0) for s in SYMBOLS)
        neutral_total = sum(all_summaries[s][label]["sides"].get(
            "neutral", 0) for s in SYMBOLS)

        print(f"\n  {label.upper()}:")
        print(f"    Total bars: {total_bars}")
        print(
            f"    Class A (BUY unreachable):          {buy_unreachable} ({buy_unreachable/total_bars*100:.1f}%)")
        print(
            f"    Class B (BUY reachable not chosen):  {buy_reachable} ({buy_reachable/total_bars*100:.1f}%)")
        print(
            f"    Class C (BUY gate blocked):          {buy_gate_blocked} ({buy_gate_blocked/total_bars*100:.1f}%)")
        print(
            f"    Class D (BUY emitted):               {buy_emitted} ({buy_emitted/total_bars*100:.1f}%)")
        print(f"    DZ veto:    {dz_total} ({dz_total/total_bars*100:.1f}%)")
        print(f"    UNCERTAIN:  {unc_total} ({unc_total/total_bars*100:.1f}%)")
        print(
            f"    Sides: buy={buy_total} sell={sell_total} neutral={neutral_total}")


if __name__ == "__main__":
    main()
