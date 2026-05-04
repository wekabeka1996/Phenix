"""
Strategist Polarity Lock Bar-Level Validation Script

Reads recorder CSVs for BTCUSDT, ETHUSDT, SOLUSDT across the full audit window
(2026-03-28 to 2026-04-08) and reconstructs the Aurora kernel math offline.

Columns directly extracted:
  - pillar_strategist, pillar_tactician, pillar_operator, pillar_sum
  - feat_regime, regime_conf
  - feat_volatility_state, feat_spread_bps, feat_macro_resid

Columns reconstructed from code + config:
  - decision_score (= pillar_sum * admission_shield_mult, admission_mode=linear)
  - thr_buy, thr_sell (= base_threshold * regime_factor * bias_mult)
  - distance_to_buy, distance_to_sell
  - side_verdict (3-zone hysteresis)

Columns NOT available (marked UNKNOWN):
  - actual shield_mult (requires full shield cascade state), estimated as admission_shield_floor=0.75
  - side_bias_state (requires runtime intent history), estimated as 1.0/1.0
  - current_side (hysteresis memory), estimated as "" (from neutral)

Output: CSV + summary statistics JSON
"""

import csv
import json
import math
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Config constants from aurora.yaml + domains.yaml
SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
TIMEFRAME = 300  # 5-minute bars

# Global base threshold
GLOBAL_SIGNAL_THRESHOLD = 0.162
GLOBAL_NEUTRAL_THRESHOLD = 0.05

# Per-symbol signal_threshold overrides
SYMBOL_SIGNAL_THRESHOLD = {
    "BTCUSDT": 0.162,   # uses global
    "ETHUSDT": 0.0221,
    "SOLUSDT": 0.0232,
}

# Per-symbol regime_thresholds (from aurora.yaml)
# BTC uses per-symbol absolute override (which are actually multipliers on base_threshold)
BTC_REGIME_THRESHOLDS = {
    "HIGH_VOLATILITY": 0.18,
    "LOW_VOLATILITY": 0.14,
    "TREND_UP": 0.12,
    "TREND_DOWN": 0.12,
    "UNCERTAIN": 99.0,
    "MEAN_REVERSION": 0.075,
    "DEFAULT": 99.0,
}

# ETH per-symbol regime_thresholds (multipliers)
ETH_REGIME_THRESHOLDS = {
    "HIGH_VOLATILITY": 1.3,
    "LOW_VOLATILITY": 0.85,
    "MEAN_REVERSION": 1.05,
    "TREND_UP": 1.0,
    "TREND_DOWN": 1.0,
    "DEFAULT": 1.0,
}

# SOL per-symbol regime_thresholds (multipliers)
SOL_REGIME_THRESHOLDS = {
    "HIGH_VOLATILITY": 1.15,
    "LOW_VOLATILITY": 0.75,
    "MEAN_REVERSION": 1.0,
    "TREND_UP": 1.0,
    "TREND_DOWN": 1.0,
    "DEFAULT": 1.0,
}

# Global regime_thresholds (fallback)
GLOBAL_REGIME_THRESHOLDS = {
    "HIGH_VOLATILITY": 0.18,
    "LOW_VOLATILITY": 0.14,
    "TREND_UP": 0.12,
    "TREND_DOWN": 0.12,
    "UNCERTAIN": 99.0,
    "MEAN_REVERSION": 0.075,
    "DEFAULT": 0.12,
}

SYMBOL_REGIME_THRESHOLDS = {
    "BTCUSDT": BTC_REGIME_THRESHOLDS,
    "ETHUSDT": ETH_REGIME_THRESHOLDS,
    "SOLUSDT": SOL_REGIME_THRESHOLDS,
}

# DangerZone thresholds (from aurora.yaml shields section)
DZ_VOL_THRESHOLD = 0.95
DZ_SPREAD_THRESHOLD = 50.0  # bps
DZ_MOTION_THRESHOLD = 3.0   # sigma

# Context shield regime multipliers
CTX_REGIME_MULTS = {
    "HIGH_VOLATILITY": 0.30,
    "UNCERTAIN": 0.55,
    "TREND_UP": 0.85,
    "TREND_DOWN": 0.85,
    "LOW_VOLATILITY": 1.0,
    "MEAN_REVERSION": 0.90,
}

ADMISSION_SHIELD_FLOOR = 0.75
SCORE_MULTIPLIER = 1.0

# Allowed regimes per symbol
ALLOWED_REGIMES = {
    "BTCUSDT": {"TREND_UP", "TREND_DOWN", "HIGH_VOLATILITY", "MEAN_REVERSION", "LOW_VOLATILITY"},
    "ETHUSDT": {"TREND_UP", "TREND_DOWN", "HIGH_VOLATILITY", "MEAN_REVERSION", "LOW_VOLATILITY"},
    "SOLUSDT": {"TREND_UP", "TREND_DOWN", "HIGH_VOLATILITY", "MEAN_REVERSION", "LOW_VOLATILITY"},
}

# Anchor shock veto config
ANCHOR_SHOCK_THRESHOLD = -2.0
ANCHOR_SYMBOL = "BTCUSDT"

# Audit window
AUDIT_START = "2026-03-28"
AUDIT_END = "2026-04-08"

RECORDER_DIR = Path("c:/Users/user/Music/Phenix/data/recorder")
OUTPUT_DIR = Path(
    "c:/Users/user/Music/Phenix/reports/strategist_polarity_lock_validation")


def resolve_regime_factor(regime_name, regime_thresholds):
    """Mirrors _resolve_regime_factor from quadratic_scoring_kernel.py"""
    if regime_name and regime_name in regime_thresholds:
        raw = regime_thresholds[regime_name]
    elif "DEFAULT" in regime_thresholds:
        raw = regime_thresholds["DEFAULT"]
    else:
        return None
    if raw is None or raw <= 0:
        return None
    return float(raw)


def estimate_shield_mult(symbol, features):
    """
    Estimate shield multiplier from available features.
    This is an APPROXIMATION — we don't have the full shield state.

    DangerZone: if vol > 0.95 OR spread > 50bps OR |motion| > 3σ → 0.0
    Context: regime-based multiplier
    Memory: not estimatable (need visit counts) → assume 1.0
    """
    vol_state = features.get("feat_volatility_state")
    spread_bps = features.get("feat_spread_bps")

    # DangerZone check
    dz_veto = False
    if vol_state is not None:
        try:
            if float(vol_state) > DZ_VOL_THRESHOLD:
                dz_veto = True
        except (ValueError, TypeError):
            pass
    if spread_bps is not None:
        try:
            if float(spread_bps) > DZ_SPREAD_THRESHOLD:
                dz_veto = True
        except (ValueError, TypeError):
            pass
    # pm_norm would need to be checked but it's not a feat_ column; skip

    if dz_veto:
        return 0.0, "DANGER_ZONE_VETO"

    # Context shield
    regime = features.get("feat_regime", "")
    ctx_mult = CTX_REGIME_MULTS.get(regime, 0.80)  # safe default

    # Memory shield: unknown, assume 1.0
    mem_mult = 1.0

    raw_shield = ctx_mult * mem_mult
    return max(0.0, min(1.0, raw_shield)), f"ctx={ctx_mult:.2f},mem={mem_mult:.2f}"


def compute_kernel_offline(symbol, pillar_sum, regime, features):
    """
    Offline replay of QuadraticScoringKernel.compute() from recorded pillar_sum.
    Returns dict with all computed fields.
    """
    base_threshold = SYMBOL_SIGNAL_THRESHOLD.get(
        symbol, GLOBAL_SIGNAL_THRESHOLD)
    regime_thresholds = SYMBOL_REGIME_THRESHOLDS.get(
        symbol, GLOBAL_REGIME_THRESHOLDS)

    result = {}
    result["pillar_sum"] = pillar_sum
    result["base_threshold"] = base_threshold

    if pillar_sum is None or not math.isfinite(pillar_sum):
        result["deferred"] = True
        result["defer_reason"] = "PILLAR_INVALID"
        return result

    # Step 1: Scale and clamp
    s_scaled = pillar_sum * SCORE_MULTIPLIER
    s_clamped = max(-1.0, min(1.0, s_scaled))

    # Step 2: Transform (admission_mode=linear, sizing_mode=quadratic)
    admission_pre_shield = s_clamped  # linear: identity
    sizing_pre_shield = math.copysign(s_clamped ** 2, s_clamped)  # quadratic

    # Step 3: Shield
    shield_mult, shield_reason = estimate_shield_mult(symbol, features)

    if shield_mult == 0.0:
        admission_shield_mult = 0.0
    else:
        admission_shield_mult = max(shield_mult, ADMISSION_SHIELD_FLOOR)

    decision_score = admission_pre_shield * admission_shield_mult
    sizing_score = sizing_pre_shield * shield_mult

    # Step 4: Regime factor → threshold
    factor = resolve_regime_factor(regime, regime_thresholds)
    if factor is None:
        result["deferred"] = True
        result["defer_reason"] = f"MISSING_REGIME_THRESHOLD:{regime}"
        result["decision_score"] = decision_score
        result["shield_mult"] = shield_mult
        return result

    signal_threshold = base_threshold * factor

    # Step 5: Side bias — we don't have runtime state, assume 1.0/1.0
    buy_bias_mult = 1.0
    sell_bias_mult = 1.0

    thr_buy = signal_threshold * buy_bias_mult
    thr_sell = signal_threshold * sell_bias_mult

    # Step 6: Side determination (from neutral, no hysteresis memory)
    neutral_threshold = GLOBAL_NEUTRAL_THRESHOLD
    # From neutral: score >= thr_buy → buy, score <= -thr_sell → sell
    if decision_score >= thr_buy:
        side = "buy"
        side_why = f"enter:buy:score={decision_score:.6f}>=thr_buy={thr_buy:.6f}"
    elif decision_score <= -thr_sell:
        side = "sell"
        side_why = f"enter:sell:score={decision_score:.6f}<=-thr_sell={thr_sell:.6f}"
    else:
        side = ""
        side_why = f"neutral:score={decision_score:.6f} in (-{thr_sell:.6f}, {thr_buy:.6f})"

    # Gate checks (post-kernel)
    gates_blocked = []

    # Regime allowlist
    allowed = ALLOWED_REGIMES.get(symbol, set())
    if regime and regime not in allowed and regime != "PENDING":
        gates_blocked.append(f"REGIME_NOT_ALLOWLISTED:{regime}")

    # Anchor shock veto (BUY only, non-BTC only)
    if side == "buy" and symbol != ANCHOR_SYMBOL:
        macro_resid = features.get("feat_macro_resid")
        if macro_resid is not None:
            try:
                if float(macro_resid) < ANCHOR_SHOCK_THRESHOLD:
                    gates_blocked.append(
                        f"ANCHOR_SHOCK_VETO:macro_resid={macro_resid}")
            except (ValueError, TypeError):
                pass

    result.update({
        "deferred": False,
        "decision_score": decision_score,
        "sizing_score": sizing_score,
        "shield_mult": shield_mult,
        "shield_reason": shield_reason,
        "admission_shield_mult": admission_shield_mult,
        "regime_factor": factor,
        "signal_threshold": signal_threshold,
        "thr_buy": thr_buy,
        "thr_sell": thr_sell,
        "side": side,
        "side_why": side_why,
        "distance_to_buy": thr_buy - decision_score,
        "distance_to_sell": decision_score + thr_sell,
        "gates_blocked": "|".join(gates_blocked) if gates_blocked else "",
    })
    return result


def load_recorder_bars(symbol):
    """Load all recorder bars for a symbol across the audit window, deduplicated by timestamp."""
    bars = {}  # keyed by timestamp for dedup

    start_dt = datetime.strptime(AUDIT_START, "%Y-%m-%d")
    end_dt = datetime.strptime(AUDIT_END, "%Y-%m-%d")

    d = start_dt
    while d <= end_dt:
        date_str = d.strftime("%Y-%m-%d")
        csv_path = RECORDER_DIR / date_str / f"{symbol}_{TIMEFRAME}.csv"

        if csv_path.exists():
            with open(csv_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    ts = row.get("timestamp", "")
                    if ts:
                        bars[ts] = row

        d += timedelta(days=1)

    # Sort by timestamp (skip malformed rows)
    valid_bars = []
    for b in bars.values():
        try:
            ts = int(b.get("timestamp", 0))
            valid_bars.append((ts, b))
        except (ValueError, TypeError):
            continue
    valid_bars.sort(key=lambda x: x[0])
    return [b for _, b in valid_bars]


def safe_float(val, default=None):
    if val is None or val == "" or val == "None":
        return default
    try:
        v = float(val)
        return v if math.isfinite(v) else default
    except (ValueError, TypeError):
        return default


def process_symbol(symbol):
    """Process all bars for one symbol, compute kernel math, return results."""
    bars = load_recorder_bars(symbol)
    results = []

    for row in bars:
        ts_ms = int(row.get("timestamp", 0))
        dt_str = row.get("datetime", "")

        pillar_sum = safe_float(row.get("feat_pillar_sum"))
        pillar_tact = safe_float(row.get("feat_pillar_tactician"))
        pillar_op = safe_float(row.get("feat_pillar_operator"))
        pillar_strat = safe_float(row.get("feat_pillar_strategist"))
        regime = row.get("feat_regime", "") or row.get("regime", "")
        regime_conf = safe_float(row.get("regime_conf"), 0.0)
        ready = row.get("ready", "")

        # Features for shield estimation
        features = {
            "feat_volatility_state": row.get("feat_volatility_state"),
            "feat_spread_bps": row.get("feat_spread_bps"),
            "feat_regime": regime,
            "feat_macro_resid": row.get("feat_macro_resid"),
        }

        # Skip bars where pillars are not ready
        if pillar_sum is None:
            results.append({
                "ts_ms": ts_ms,
                "ts_utc": dt_str,
                "symbol": symbol,
                "regime": regime,
                "regime_conf": regime_conf,
                "ready": ready,
                "pillar_tactician": pillar_tact,
                "pillar_operator": pillar_op,
                "pillar_strategist": pillar_strat,
                "pillar_sum": None,
                "deferred": True,
                "defer_reason": "PILLAR_NOT_READY",
                "decision_score": None,
                "thr_buy": None,
                "thr_sell": None,
                "distance_to_buy": None,
                "distance_to_sell": None,
                "side": "",
                "side_why": "",
                "gates_blocked": "",
                "shield_mult": None,
                "failure_class": "E_UNKNOWN",
            })
            continue

        kernel = compute_kernel_offline(symbol, pillar_sum, regime, features)

        # Classify BUY failure
        if kernel.get("deferred"):
            failure_class = "E_UNKNOWN"
        elif kernel.get("side") == "buy":
            if kernel.get("gates_blocked"):
                failure_class = "C_BUY_REACHABLE_GATE_BLOCKED"
            else:
                failure_class = "D_BUY_EMITTED"
        elif kernel.get("side") == "sell":
            # BUY was not selected; was it mathematically possible?
            if kernel.get("decision_score", -999) >= kernel.get("thr_buy", 999):
                failure_class = "B_BUY_REACHABLE_NOT_SELECTED"
            else:
                failure_class = "A_BUY_UNREACHABLE"
        else:
            # Neutral
            if kernel.get("decision_score", -999) >= kernel.get("thr_buy", 999):
                failure_class = "B_BUY_REACHABLE_NOT_SELECTED"
            else:
                failure_class = "A_BUY_UNREACHABLE"

        results.append({
            "ts_ms": ts_ms,
            "ts_utc": dt_str,
            "symbol": symbol,
            "regime": regime,
            "regime_conf": regime_conf,
            "ready": ready,
            "pillar_tactician": pillar_tact,
            "pillar_operator": pillar_op,
            "pillar_strategist": pillar_strat,
            "pillar_sum": pillar_sum,
            "deferred": kernel.get("deferred", False),
            "defer_reason": kernel.get("defer_reason", ""),
            "decision_score": kernel.get("decision_score"),
            "thr_buy": kernel.get("thr_buy"),
            "thr_sell": kernel.get("thr_sell"),
            "distance_to_buy": kernel.get("distance_to_buy"),
            "distance_to_sell": kernel.get("distance_to_sell"),
            "side": kernel.get("side", ""),
            "side_why": kernel.get("side_why", ""),
            "gates_blocked": kernel.get("gates_blocked", ""),
            "shield_mult": kernel.get("shield_mult"),
            "shield_reason": kernel.get("shield_reason", ""),
            "regime_factor": kernel.get("regime_factor"),
            "signal_threshold": kernel.get("signal_threshold"),
            "failure_class": failure_class,
        })

    return results


def compute_stats(results, symbol):
    """Compute summary statistics for one symbol."""
    valid = [r for r in results if r["pillar_sum"]
             is not None and not r.get("deferred")]
    all_bars = results

    if not valid:
        return {"symbol": symbol, "error": "no valid bars"}

    strat_vals = [r["pillar_strategist"]
                  for r in valid if r["pillar_strategist"] is not None]
    tact_vals = [r["pillar_tactician"]
                 for r in valid if r["pillar_tactician"] is not None]
    op_vals = [r["pillar_operator"]
               for r in valid if r["pillar_operator"] is not None]
    psum_vals = [r["pillar_sum"] for r in valid]
    dscore_vals = [r["decision_score"]
                   for r in valid if r["decision_score"] is not None]
    dtb_vals = [r["distance_to_buy"]
                for r in valid if r["distance_to_buy"] is not None]

    def percentiles(vals):
        s = sorted(vals)
        n = len(s)
        return {
            "min": s[0],
            "p5": s[int(n * 0.05)] if n > 20 else s[0],
            "p25": s[int(n * 0.25)],
            "median": s[int(n * 0.5)],
            "p75": s[int(n * 0.75)],
            "p95": s[int(n * 0.95)] if n > 20 else s[-1],
            "max": s[-1],
            "mean": sum(s) / n,
            "count": n,
        }

    def pct_below(vals, threshold):
        if not vals:
            return 0.0
        return sum(1 for v in vals if v < threshold) / len(vals) * 100

    def pct_above(vals, threshold):
        if not vals:
            return 0.0
        return sum(1 for v in vals if v >= threshold) / len(vals) * 100

    def longest_consecutive_below(vals, threshold):
        max_run = 0
        current_run = 0
        for v in vals:
            if v < threshold:
                current_run += 1
                max_run = max(max_run, current_run)
            else:
                current_run = 0
        return max_run

    # Failure classification counts
    fc = defaultdict(int)
    for r in all_bars:
        fc[r["failure_class"]] += 1

    # Side counts
    sides = defaultdict(int)
    for r in valid:
        sides[r["side"] or "neutral"] += 1

    # Regime distribution
    regimes = defaultdict(int)
    for r in valid:
        regimes[r["regime"]] += 1

    # BUY closest approach
    if dtb_vals:
        closest_buy = min(dtb_vals)
        closest_buy_bar = min((r for r in valid if r.get("distance_to_buy") is not None),
                              key=lambda r: r["distance_to_buy"])
    else:
        closest_buy = None
        closest_buy_bar = None

    stats = {
        "symbol": symbol,
        "total_bars": len(all_bars),
        "valid_bars": len(valid),
        "deferred_bars": sum(1 for r in all_bars if r.get("deferred")),
        "strategist": percentiles(strat_vals) if strat_vals else {},
        "strategist_pct_below_0": pct_below(strat_vals, 0),
        "strategist_pct_below_neg03": pct_below(strat_vals, -0.3),
        "strategist_pct_below_neg05": pct_below(strat_vals, -0.5),
        "strategist_longest_run_below_0": longest_consecutive_below(strat_vals, 0),
        "strategist_longest_run_below_neg03": longest_consecutive_below(strat_vals, -0.3),
        "tactician": percentiles(tact_vals) if tact_vals else {},
        "operator": percentiles(op_vals) if op_vals else {},
        "pillar_sum": percentiles(psum_vals) if psum_vals else {},
        "pillar_sum_pct_positive": pct_above(psum_vals, 0),
        "decision_score": percentiles(dscore_vals) if dscore_vals else {},
        "decision_score_pct_positive": pct_above(dscore_vals, 0),
        "distance_to_buy": percentiles(dtb_vals) if dtb_vals else {},
        "closest_buy_approach": closest_buy,
        "closest_buy_bar_ts": closest_buy_bar["ts_utc"] if closest_buy_bar else None,
        "closest_buy_bar_regime": closest_buy_bar["regime"] if closest_buy_bar else None,
        "closest_buy_bar_psum": closest_buy_bar["pillar_sum"] if closest_buy_bar else None,
        "closest_buy_bar_dscore": closest_buy_bar["decision_score"] if closest_buy_bar else None,
        "closest_buy_bar_thr_buy": closest_buy_bar["thr_buy"] if closest_buy_bar else None,
        "failure_class_counts": dict(fc),
        "failure_class_pct": {k: round(v / len(all_bars) * 100, 2) for k, v in fc.items()},
        "side_counts": dict(sides),
        "side_pct": {k: round(v / len(valid) * 100, 2) for k, v in sides.items()} if valid else {},
        "regime_distribution": dict(regimes),
    }
    return stats


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    all_stats = {}

    for symbol in SYMBOLS:
        print(f"\n{'='*60}")
        print(f"Processing {symbol}...")
        print(f"{'='*60}")

        results = process_symbol(symbol)
        print(f"  Total bars: {len(results)}")

        # Write per-bar CSV
        csv_path = OUTPUT_DIR / f"{symbol}_bar_level.csv"
        if results:
            fieldnames = list(results[0].keys())
            with open(csv_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(results)
            print(f"  Written: {csv_path}")

        # Compute stats
        stats = compute_stats(results, symbol)
        all_stats[symbol] = stats

        # Print summary
        print(f"  Valid bars: {stats.get('valid_bars', 0)}")
        print(f"  Deferred bars: {stats.get('deferred_bars', 0)}")

        strat = stats.get("strategist", {})
        if strat:
            print(f"  Strategist: min={strat.get('min', '?'):.4f} max={strat.get('max', '?'):.4f} "
                  f"mean={strat.get('mean', '?'):.4f} median={strat.get('median', '?'):.4f}")
            print(
                f"  Strategist <0: {stats.get('strategist_pct_below_0', '?'):.1f}%")
            print(
                f"  Strategist <-0.3: {stats.get('strategist_pct_below_neg03', '?'):.1f}%")
            print(
                f"  Strategist <-0.5: {stats.get('strategist_pct_below_neg05', '?'):.1f}%")
            print(
                f"  Strategist longest run below 0: {stats.get('strategist_longest_run_below_0', '?')}")

        psum = stats.get("pillar_sum", {})
        if psum:
            print(f"  Pillar_sum: min={psum.get('min', '?'):.6f} max={psum.get('max', '?'):.6f} "
                  f"mean={psum.get('mean', '?'):.6f}")
            print(
                f"  Pillar_sum >0: {stats.get('pillar_sum_pct_positive', '?'):.1f}%")

        dscore = stats.get("decision_score", {})
        if dscore:
            print(
                f"  Decision_score: min={dscore.get('min', '?'):.6f} max={dscore.get('max', '?'):.6f}")
            print(
                f"  Decision_score >0: {stats.get('decision_score_pct_positive', '?'):.1f}%")

        print(
            f"  Closest BUY approach: {stats.get('closest_buy_approach', '?')}")
        print(f"    at: {stats.get('closest_buy_bar_ts', '?')}")
        print(f"    regime: {stats.get('closest_buy_bar_regime', '?')}")

        print(f"  Failure classification:")
        for cls, cnt in sorted(stats.get("failure_class_counts", {}).items()):
            pct = stats.get("failure_class_pct", {}).get(cls, 0)
            print(f"    {cls}: {cnt} ({pct:.1f}%)")

        print(f"  Side distribution:")
        for s, cnt in sorted(stats.get("side_counts", {}).items()):
            pct = stats.get("side_pct", {}).get(s, 0)
            print(f"    {s}: {cnt} ({pct:.1f}%)")

        print(f"  Regime distribution:")
        for r, cnt in sorted(stats.get("regime_distribution", {}).items()):
            print(f"    {r}: {cnt}")

    # Write combined stats JSON
    json_path = OUTPUT_DIR / "validation_summary.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(all_stats, f, indent=2, default=str)
    print(f"\nSummary written: {json_path}")

    # Cross-validation with aurora_core.log QUADRATIC_DECISION_TRACE
    print(f"\n{'='*60}")
    print("Cross-validation: checking aurora_core.log for KERNEL_DIAG entries...")
    print(f"{'='*60}")
    validate_against_logs(all_stats)


def validate_against_logs(all_stats):
    """Cross-validate reconstructed values against actual KERNEL_DIAG from aurora_core.log."""
    import glob
    import re

    log_pattern = "c:/Users/user/Music/Phenix/logs/aurora_core.log*"
    log_files = sorted(glob.glob(log_pattern))

    kernel_entries = []
    trace_pattern = re.compile(
        r'\[(?P<symbol>\w+)\] QUADRATIC_DECISION_TRACE '
        r'score=(?P<score>[-\d.]+) '
        r'decision_score=(?P<dscore>[-\d.]+) '
        r'sizing_score=(?P<sscore>[-\d.]+) '
        r'side=(?P<side>\w*) '
        r'deferred=(?P<deferred>\w+) '
        r'regime=(?P<regime>\w+)'
    )
    diag_pattern = re.compile(
        r'\[(?P<symbol>\w+)\] KERNEL_DIAG.*?'
        r's_linear=(?P<s_linear>[-\d.]+).*?'
        r'decision_score=(?P<dscore>[-\d.]+).*?'
        r'shield_mult=(?P<shield_mult>[-\d.]+).*?'
        r'thr_buy=(?P<thr_buy>[-\d.]+).*?'
        r'thr_sell=(?P<thr_sell>[-\d.]+)'
    )

    for lf in log_files:
        try:
            with open(lf, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    m = trace_pattern.search(line)
                    if m and m.group("symbol") in SYMBOLS:
                        kernel_entries.append({
                            "source": "TRACE",
                            "symbol": m.group("symbol"),
                            "score": float(m.group("score")),
                            "decision_score": float(m.group("dscore")),
                            "side": m.group("side"),
                            "regime": m.group("regime"),
                        })
                    m2 = diag_pattern.search(line)
                    if m2 and m2.group("symbol") in SYMBOLS:
                        kernel_entries.append({
                            "source": "DIAG",
                            "symbol": m2.group("symbol"),
                            "s_linear": float(m2.group("s_linear")),
                            "decision_score": float(m2.group("dscore")),
                            "shield_mult": float(m2.group("shield_mult")),
                            "thr_buy": float(m2.group("thr_buy")),
                            "thr_sell": float(m2.group("thr_sell")),
                        })
        except Exception as e:
            print(f"  Error reading {lf}: {e}")

    if not kernel_entries:
        print("  No KERNEL_DIAG/TRACE entries found for cross-validation")
        return

    print(f"  Found {len(kernel_entries)} kernel entries for cross-validation")

    for sym in SYMBOLS:
        sym_entries = [e for e in kernel_entries if e["symbol"] == sym]
        if not sym_entries:
            continue

        traces = [e for e in sym_entries if e["source"] == "TRACE"]
        diags = [e for e in sym_entries if e["source"] == "DIAG"]

        print(f"\n  {sym}: {len(traces)} TRACE + {len(diags)} DIAG entries")

        if traces:
            scores = [e["decision_score"] for e in traces]
            sides = defaultdict(int)
            for e in traces:
                sides[e.get("side", "?")] += 1
            print(
                f"    TRACE decision_score: min={min(scores):.6f} max={max(scores):.6f} mean={sum(scores)/len(scores):.6f}")
            print(f"    TRACE sides: {dict(sides)}")

        if diags:
            shield_mults = [e["shield_mult"] for e in diags]
            thr_buys = [e["thr_buy"] for e in diags]
            s_linears = [e["s_linear"] for e in diags]
            print(
                f"    DIAG s_linear: min={min(s_linears):.6f} max={max(s_linears):.6f}")
            print(
                f"    DIAG shield_mult: min={min(shield_mults):.4f} max={max(shield_mults):.4f}")
            print(
                f"    DIAG thr_buy: min={min(thr_buys):.6f} max={max(thr_buys):.6f}")


if __name__ == "__main__":
    main()
