"""
REGIME_CONFIDENCE_NEAR_THRESHOLD_REVIEW
Forensic audit of FIX-CONF-GATE-01 (min_regime_confidence=0.42) gate.

Extracts all blocked + admitted cases, buckets by confidence, runs counterfactual
replay for near-threshold blocked cases, compares with accepted-control group.
"""
import json, csv, re, os, sys
from datetime import datetime, timezone
from collections import Counter, defaultdict
from pathlib import Path
from decimal import Decimal

BASE = Path(__file__).resolve().parents[2]
LOGS = BASE / "logs"
DATA = BASE / "data" / "recorder"
REPORTS = BASE / "reports"

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT", "BNBUSDT"]
DATES = ["2026-03-22", "2026-03-23", "2026-03-24"]
WINDOWS_MIN = [15, 30, 45, 60, 120]
THRESHOLD = 0.42

# ─── Bucket definitions ────────────────────────────────────────
BUCKETS = {
    "DEEP_LOW":       (0.0,  0.34),
    "MID_LOW":        (0.34, 0.38),
    "NEAR_THRESHOLD": (0.38, 0.42),  # focus of this audit
}

def classify_bucket(conf):
    if conf is None:
        return "NULL_CONFIDENCE"
    for name, (lo, hi) in BUCKETS.items():
        if lo <= conf < hi:
            return name
    if conf >= THRESHOLD:
        return "ABOVE_THRESHOLD"
    return "UNKNOWN"


# ─── Bar data loader ──────────────────────────────────────────
def load_bars():
    bars = defaultdict(list)
    for sym in SYMBOLS:
        for d in DATES:
            path = DATA / d / f"{sym}_180.csv"
            if path.exists():
                with open(path, newline="") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        ts = int(row.get("timestamp", 0))
                        o = float(row.get("open") or 0)
                        h = float(row.get("high") or 0)
                        lo = float(row.get("low") or 0)
                        c = float(row.get("close") or 0)
                        if ts and c > 0:
                            bars[sym].append((ts, o, h, lo, c))
        bars[sym].sort()
    return bars


def find_price_at_time(bars_dict, symbol, ts_ms):
    sym_bars = bars_dict.get(symbol, [])
    if not sym_bars:
        return None
    lo_idx, hi_idx = 0, len(sym_bars) - 1
    while lo_idx < hi_idx:
        mid = (lo_idx + hi_idx + 1) // 2
        if sym_bars[mid][0] <= ts_ms:
            lo_idx = mid
        else:
            hi_idx = mid - 1
    if sym_bars[lo_idx][0] <= ts_ms:
        return sym_bars[lo_idx][4]
    return None


def compute_outcomes(bars_dict, symbol, entry_price, side, ts_ms):
    sym_bars = bars_dict.get(symbol, [])
    if not sym_bars or not entry_price or entry_price <= 0:
        return None
    results = {}
    for w in WINDOWS_MIN:
        end_ms = ts_ms + w * 60 * 1000
        window_bars = [b for b in sym_bars if ts_ms < b[0] <= end_ms]
        if not window_bars:
            results[f"{w}m"] = {"return_pct": None, "mfe_pct": None, "mae_pct": None, "status": "NO_BARS"}
            continue
        last_close = window_bars[-1][4]
        if side.upper() in ("SELL", "SHORT"):
            dir_ret = (entry_price - last_close) / entry_price * 100
            mfe = max((entry_price - b[3]) / entry_price * 100 for b in window_bars)
            mae = max((b[2] - entry_price) / entry_price * 100 for b in window_bars)
        else:
            dir_ret = (last_close - entry_price) / entry_price * 100
            mfe = max((b[2] - entry_price) / entry_price * 100 for b in window_bars)
            mae = max((entry_price - b[3]) / entry_price * 100 for b in window_bars)
        if abs(dir_ret) < 0.02:
            classif = "NEUTRAL"
        elif dir_ret > 0:
            classif = "PROFITABLE"
        else:
            classif = "LOSING"
        results[f"{w}m"] = {
            "return_pct": round(dir_ret, 4),
            "mfe_pct": round(mfe, 4),
            "mae_pct": round(mae, 4),
            "final_price": round(last_close, 6),
            "classification": classif,
            "bars_in_window": len(window_bars),
        }
    return results


# ─── Extract regime_confidence from why string ────────────────
RE_CONF = re.compile(r"regime_confidence=([0-9.eE+-]+)")

def extract_conf_from_why(why: str):
    m = RE_CONF.search(why)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            return None
    return None


# ─── Load all cases ──────────────────────────────────────────
def load_all_cases():
    """
    Returns two lists:
    - blocked: all REGIME_CONFIDENCE:below_min (NRR-026 + FIX-CONF-GATE-01) cases
    - admitted: all ORDER_INTENT from DecisionMaking that passed gates (have regime_confidence field)
    """
    blocked = []
    admitted = []

    with open(LOGS / "order_log_v1.jsonl") as f:
        for line in f:
            if not line.strip():
                continue
            r = json.loads(line)

            # Blocked by regime confidence gate
            if r.get("event_type") == "ORDER_REJECTED" and "FIX-CONF-GATE-01" in r.get("why", ""):
                conf = extract_conf_from_why(r["why"])
                blocked.append({
                    "ts_ms": r.get("timestamp", 0),
                    "symbol": r.get("symbol", ""),
                    "strategy_id": r.get("strategy_id", "aurora"),
                    "side": r.get("side", ""),
                    "rid": r.get("rid", ""),
                    "nrr_code": r.get("nrr_code", "NRR-026"),
                    "regime_confidence": conf,
                    "bucket": classify_bucket(conf),
                    "why": r["why"],
                    "source": "order_log",
                })

            # Admitted intents (passed gates) from DecisionMaking
            elif (r.get("event_type") == "ORDER_INTENT"
                  and r.get("source_fsm") == "DecisionMaking"
                  and r.get("regime_confidence") is not None):
                conf = r["regime_confidence"]
                admitted.append({
                    "ts_ms": r.get("timestamp", 0),
                    "symbol": r.get("symbol", ""),
                    "strategy_id": r.get("strategy_id", "aurora"),
                    "side": r.get("side", ""),
                    "rid": r.get("rid", ""),
                    "regime": r.get("regime", ""),
                    "regime_confidence": conf,
                    "bucket": classify_bucket(conf),
                    "price": r.get("price"),
                    "source": "order_log",
                })

    # Also read trade_lifecycle for admitted intents with lifecycle data
    admitted_rids = {a["rid"] for a in admitted}
    lifecycle_data = {}
    with open(LOGS / "trade_lifecycle.jsonl") as f:
        for line in f:
            if not line.strip():
                continue
            r = json.loads(line)
            if r.get("record_kind") == "position_policy_sidecar":
                continue
            rid = r.get("rid", "")
            if rid and r.get("regime_confidence") is not None:
                lifecycle_data[rid] = {
                    "regime": r.get("regime"),
                    "regime_confidence": r.get("regime_confidence"),
                    "status": r.get("status"),
                    "close_reason": r.get("close_reason"),
                    "order_price": r.get("order_price"),
                }

    # Enrich admitted with lifecycle
    for a in admitted:
        lc = lifecycle_data.get(a["rid"], {})
        a["lifecycle_status"] = lc.get("status")
        a["close_reason"] = lc.get("close_reason")
        if a.get("price") is None:
            a["price"] = lc.get("order_price")

    return blocked, admitted


def median(lst):
    if not lst:
        return 0
    s = sorted(lst)
    n = len(s)
    if n % 2 == 1:
        return s[n // 2]
    return (s[n // 2 - 1] + s[n // 2]) / 2


def percentile(lst, p):
    if not lst:
        return 0
    s = sorted(lst)
    k = (len(s) - 1) * p / 100
    lo = int(k)
    hi = min(lo + 1, len(s) - 1)
    frac = k - lo
    return s[lo] + frac * (s[hi] - s[lo])


# ─── Counterfactual replay ──────────────────────────────────
def run_replay(bars_dict, cases, case_type="blocked"):
    """Run counterfactual replay on a list of cases."""
    results = []
    for c in cases:
        symbol = c["symbol"]
        ts_ms = c["ts_ms"]
        side = c.get("side", "SELL")

        # Entry price: for blocked cases use proxy (market price at time of block)
        if c.get("price") and float(c["price"]) > 0:
            entry_price = float(c["price"])
            entry_conf = "EXACT"
        else:
            entry_price = find_price_at_time(bars_dict, symbol, ts_ms)
            entry_conf = "PROXY"

        outcomes = compute_outcomes(bars_dict, symbol, entry_price, side, ts_ms)

        ts_utc = ""
        if ts_ms:
            ts_utc = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        result = {
            "ts_ms": ts_ms,
            "ts_utc": ts_utc,
            "symbol": symbol,
            "strategy_id": c.get("strategy_id", ""),
            "side": side,
            "rid": c.get("rid", ""),
            "regime_confidence": c.get("regime_confidence"),
            "bucket": c.get("bucket", ""),
            "entry_price": entry_price,
            "entry_confidence": entry_conf,
            "case_type": case_type,
            "replay_possible": outcomes is not None,
        }
        if outcomes:
            for w_key, w_val in outcomes.items():
                result[w_key] = w_val
        results.append(result)
    return results


def compute_bucket_stats(replayed, bucket_name):
    """Compute stats for a single bucket of replayed cases."""
    cases = [r for r in replayed if r.get("bucket") == bucket_name]
    n = len(cases)
    if n == 0:
        return None

    replay_ok = [c for c in cases if c.get("replay_possible")]
    conf_vals = [c["regime_confidence"] for c in cases if c.get("regime_confidence") is not None]

    sym_cnt = Counter(c["symbol"] for c in cases)
    side_cnt = Counter(c["side"] for c in cases)
    strat_cnt = Counter(c["strategy_id"] for c in cases)

    window_stats = {}
    for w in WINDOWS_MIN:
        key = f"{w}m"
        rets = [c[key]["return_pct"] for c in replay_ok if c.get(key) and c[key].get("return_pct") is not None]
        mfes = [c[key]["mfe_pct"] for c in replay_ok if c.get(key) and c[key].get("mfe_pct") is not None]
        maes = [c[key]["mae_pct"] for c in replay_ok if c.get(key) and c[key].get("mae_pct") is not None]

        profitable = sum(1 for r in rets if r > 0.02)
        losing = sum(1 for r in rets if r < -0.02)
        neutral = len(rets) - profitable - losing

        window_stats[key] = {
            "count": len(rets),
            "profitable": profitable,
            "losing": losing,
            "neutral": neutral,
            "mean_return": round(sum(rets) / len(rets), 4) if rets else None,
            "median_return": round(median(rets), 4) if rets else None,
            "p25_return": round(percentile(rets, 25), 4) if rets else None,
            "p75_return": round(percentile(rets, 75), 4) if rets else None,
            "median_mfe": round(median(mfes), 4) if mfes else None,
            "median_mae": round(median(maes), 4) if maes else None,
            "mean_mfe": round(sum(mfes) / len(mfes), 4) if mfes else None,
            "mean_mae": round(sum(maes) / len(maes), 4) if maes else None,
            "profitable_pct": round(profitable / len(rets) * 100, 1) if rets else None,
            "win_loss_ratio": round(profitable / losing, 2) if losing > 0 else ("INF" if profitable > 0 else 0),
        }

    return {
        "count": n,
        "replay_eligible": len(replay_ok),
        "confidence_range": {
            "min": round(min(conf_vals), 6) if conf_vals else None,
            "max": round(max(conf_vals), 6) if conf_vals else None,
            "mean": round(sum(conf_vals) / len(conf_vals), 6) if conf_vals else None,
            "median": round(median(conf_vals), 6) if conf_vals else None,
        },
        "symbols": dict(sym_cnt.most_common()),
        "sides": dict(side_cnt.most_common()),
        "strategies": dict(strat_cnt.most_common()),
        "windows": window_stats,
    }


def compute_skew_analysis(replayed, dim_key):
    """Per-bucket, per-dimension cross-tabulation."""
    groups = defaultdict(lambda: defaultdict(list))
    for r in replayed:
        bucket = r.get("bucket", "UNKNOWN")
        dim_val = r.get(dim_key, "UNKNOWN")
        groups[bucket][dim_val].append(r)

    output = {}
    for bucket, dims in groups.items():
        output[bucket] = {}
        for dim_val, cases in dims.items():
            replay_ok = [c for c in cases if c.get("replay_possible")]
            rets_60 = [c["60m"]["return_pct"] for c in replay_ok
                        if c.get("60m") and c["60m"].get("return_pct") is not None]
            profitable = sum(1 for r in rets_60 if r > 0.02)
            losing = sum(1 for r in rets_60 if r < -0.02)
            output[bucket][dim_val] = {
                "count": len(cases),
                "profitable_60m": profitable,
                "losing_60m": losing,
                "mean_return_60m": round(sum(rets_60) / len(rets_60), 4) if rets_60 else None,
            }
    return output


def compute_contamination(blocked_replayed, admitted_replayed):
    """
    Contamination analysis: check if near-threshold blocked cases have
    systematically different outcomes vs. just-above-threshold admitted cases.
    """
    near_blocked = [r for r in blocked_replayed if r.get("bucket") == "NEAR_THRESHOLD"]
    # "just above threshold" = admitted with confidence in [0.42, 0.46)
    just_above = [r for r in admitted_replayed
                  if r.get("regime_confidence") is not None
                  and 0.42 <= r["regime_confidence"] < 0.46]

    def extract_rets(cases, window="60m"):
        return [c[window]["return_pct"] for c in cases
                if c.get("replay_possible") and c.get(window) and c[window].get("return_pct") is not None]

    result = {}
    for w in ["15m", "30m", "60m", "120m"]:
        blocked_rets = extract_rets(near_blocked, w)
        admitted_rets = extract_rets(just_above, w)

        b_prof = sum(1 for r in blocked_rets if r > 0.02) if blocked_rets else 0
        b_loss = sum(1 for r in blocked_rets if r < -0.02) if blocked_rets else 0
        a_prof = sum(1 for r in admitted_rets if r > 0.02) if admitted_rets else 0
        a_loss = sum(1 for r in admitted_rets if r < -0.02) if admitted_rets else 0

        result[w] = {
            "blocked_near_threshold": {
                "n": len(blocked_rets),
                "mean_return": round(sum(blocked_rets) / len(blocked_rets), 4) if blocked_rets else None,
                "profitable": b_prof,
                "losing": b_loss,
                "profitable_pct": round(b_prof / len(blocked_rets) * 100, 1) if blocked_rets else None,
            },
            "admitted_just_above": {
                "n": len(admitted_rets),
                "mean_return": round(sum(admitted_rets) / len(admitted_rets), 4) if admitted_rets else None,
                "profitable": a_prof,
                "losing": a_loss,
                "profitable_pct": round(a_prof / len(admitted_rets) * 100, 1) if admitted_rets else None,
            },
        }

        # Delta
        if blocked_rets and admitted_rets:
            result[w]["delta_mean_return"] = round(
                (result[w]["blocked_near_threshold"]["mean_return"] or 0) -
                (result[w]["admitted_just_above"]["mean_return"] or 0), 4)
            result[w]["delta_profitable_pct"] = round(
                (result[w]["blocked_near_threshold"]["profitable_pct"] or 0) -
                (result[w]["admitted_just_above"]["profitable_pct"] or 0), 1)

    return result


def derive_verdict(bucket_stats, contamination):
    """
    Decision logic:
    - If NEAR_THRESHOLD has >55% profitable at 60m AND mean_return > 0.05 → RUN_SAFE_RECALIBRATION_EXPERIMENT
    - If NEAR_THRESHOLD has clearly worse than admitted_just_above → KEEP_THRESHOLD_AS_IS
    - If insufficient data → UNPROVEN_DUE_TO_WEAK_EVIDENCE
    - If mixed / no clear signal → MONITOR_NEAR_THRESHOLD_ONLY
    """
    near = bucket_stats.get("NEAR_THRESHOLD")
    if near is None or near["count"] < 5:
        return "UNPROVEN_DUE_TO_WEAK_EVIDENCE", "Fewer than 5 near-threshold cases."

    w60 = near["windows"].get("60m", {})
    if not w60.get("count") or w60["count"] < 3:
        return "UNPROVEN_DUE_TO_WEAK_EVIDENCE", f"Only {w60.get('count', 0)} cases with 60m replay data."

    profit_pct = w60.get("profitable_pct", 0) or 0
    mean_ret = w60.get("mean_return", 0) or 0
    losing = w60.get("losing", 0) or 0
    profitable = w60.get("profitable", 0) or 0

    # Check contamination
    c60 = contamination.get("60m", {})
    delta_profit = c60.get("delta_profitable_pct", 0) or 0
    delta_mean = c60.get("delta_mean_return", 0) or 0

    reasons = []

    # Strong over-block signal
    if profit_pct > 55 and mean_ret > 0.05:
        reasons.append(f"60m profit_pct={profit_pct}% > 55%, mean_return={mean_ret}% > 0.05%")
        return "RUN_SAFE_RECALIBRATION_EXPERIMENT", "; ".join(reasons)

    # Near-threshold clearly worse than admitted
    if delta_mean < -0.10 and delta_profit < -15:
        reasons.append(f"Near-threshold underperforms admitted: delta_mean={delta_mean}%, delta_profit_pct={delta_profit}%")
        return "KEEP_THRESHOLD_AS_IS", "; ".join(reasons)

    # Near-threshold moderately profitable
    if profit_pct > 45 and mean_ret > 0.0:
        reasons.append(f"60m profit_pct={profit_pct}% > 45%, mean > 0, but not strongly over-blocked")
        return "MONITOR_NEAR_THRESHOLD_ONLY", "; ".join(reasons)

    # Near-threshold losing
    if losing > profitable:
        reasons.append(f"60m losing ({losing}) > profitable ({profitable}): gate appears justified")
        return "KEEP_THRESHOLD_AS_IS", "; ".join(reasons)

    reasons.append(f"Ambiguous: profit_pct={profit_pct}%, mean={mean_ret}%, delta_mean={delta_mean}%")
    return "MONITOR_NEAR_THRESHOLD_ONLY", "; ".join(reasons)


def main():
    print("=" * 80)
    print("REGIME_CONFIDENCE_NEAR_THRESHOLD_REVIEW — Forensic Audit")
    print("=" * 80)

    # Load bar data
    print("\n1. Loading 3-min bar data...")
    bars = load_bars()
    for sym in SYMBOLS:
        print(f"   {sym}: {len(bars[sym])} bars")

    # Load cases
    print("\n2. Loading all REGIME_CONFIDENCE cases...")
    blocked, admitted = load_all_cases()
    print(f"   Blocked by FIX-CONF-GATE-01: {len(blocked)}")
    print(f"   Admitted (passed gates): {len(admitted)}")

    # Bucket distribution
    print("\n3. Confidence bucket distribution (blocked):")
    blocked_buckets = Counter(c["bucket"] for c in blocked)
    for bname in ["DEEP_LOW", "MID_LOW", "NEAR_THRESHOLD", "NULL_CONFIDENCE"]:
        cnt = blocked_buckets.get(bname, 0)
        confs = [c["regime_confidence"] for c in blocked if c["bucket"] == bname and c["regime_confidence"] is not None]
        conf_range = f"[{min(confs):.4f} .. {max(confs):.4f}]" if confs else "N/A"
        print(f"   {bname:20s}: {cnt:4d}  range={conf_range}")

    print("\n   Admitted confidence distribution:")
    admitted_buckets = Counter(classify_bucket(c["regime_confidence"]) for c in admitted)
    for bname in ["NEAR_THRESHOLD", "ABOVE_THRESHOLD"]:
        cnt = admitted_buckets.get(bname, 0)
        confs = [c["regime_confidence"] for c in admitted if classify_bucket(c["regime_confidence"]) == bname]
        conf_range = f"[{min(confs):.4f} .. {max(confs):.4f}]" if confs else "N/A"
        print(f"   {bname:20s}: {cnt:4d}  range={conf_range}")

    # Run counterfactual replay on ALL blocked + admitted
    print("\n4. Running counterfactual replay on blocked cases...")
    blocked_replayed = run_replay(bars, blocked, case_type="blocked")
    replay_ok = sum(1 for r in blocked_replayed if r["replay_possible"])
    print(f"   Replay possible: {replay_ok}/{len(blocked_replayed)}")

    print("\n5. Running counterfactual replay on admitted (control) cases...")
    admitted_replayed = run_replay(bars, admitted, case_type="admitted")
    replay_ok_a = sum(1 for r in admitted_replayed if r["replay_possible"])
    print(f"   Replay possible: {replay_ok_a}/{len(admitted_replayed)}")

    # Bucket-level stats
    print("\n6. Computing per-bucket stats...")
    bucket_stats_blocked = {}
    for bname in ["DEEP_LOW", "MID_LOW", "NEAR_THRESHOLD"]:
        stats = compute_bucket_stats(blocked_replayed, bname)
        bucket_stats_blocked[bname] = stats
        if stats:
            w60 = stats["windows"].get("60m", {})
            print(f"   {bname:20s}  n={stats['count']:3d}  "
                  f"60m: P={w60.get('profitable','-')} L={w60.get('losing','-')} "
                  f"mean={w60.get('mean_return','-')}% "
                  f"win%={w60.get('profitable_pct','-')}")

    # Admitted control stats (just-above-threshold)
    print("\n   Admitted control groups:")
    admitted_control = compute_bucket_stats(admitted_replayed, "ABOVE_THRESHOLD")
    if admitted_control:
        w60 = admitted_control["windows"].get("60m", {})
        print(f"   {'ABOVE_THRESHOLD':20s}  n={admitted_control['count']:3d}  "
              f"60m: P={w60.get('profitable','-')} L={w60.get('losing','-')} "
              f"mean={w60.get('mean_return','-')}% "
              f"win%={w60.get('profitable_pct','-')}")

    # Skew analysis
    print("\n7. Computing skew analysis...")
    symbol_skew = compute_skew_analysis(blocked_replayed, "symbol")
    strategy_skew = compute_skew_analysis(blocked_replayed, "strategy_id")
    side_skew = compute_skew_analysis(blocked_replayed, "side")

    for bname in ["NEAR_THRESHOLD"]:
        if bname in symbol_skew:
            print(f"\n   {bname} by symbol:")
            for dim_val, stats in sorted(symbol_skew[bname].items(), key=lambda x: -x[1]["count"]):
                print(f"     {dim_val:12s} n={stats['count']}  P={stats['profitable_60m']} L={stats['losing_60m']}"
                      f"  mean={stats['mean_return_60m']}")
        if bname in side_skew:
            print(f"\n   {bname} by side:")
            for dim_val, stats in sorted(side_skew[bname].items(), key=lambda x: -x[1]["count"]):
                print(f"     {dim_val:12s} n={stats['count']}  P={stats['profitable_60m']} L={stats['losing_60m']}"
                      f"  mean={stats['mean_return_60m']}")
        if bname in strategy_skew:
            print(f"\n   {bname} by strategy:")
            for dim_val, stats in sorted(strategy_skew[bname].items(), key=lambda x: -x[1]["count"]):
                print(f"     {dim_val:12s} n={stats['count']}  P={stats['profitable_60m']} L={stats['losing_60m']}"
                      f"  mean={stats['mean_return_60m']}")

    # Contamination analysis
    print("\n8. Contamination analysis (NEAR_THRESHOLD blocked vs JUST_ABOVE admitted)...")
    contamination = compute_contamination(blocked_replayed, admitted_replayed)
    for w, c_data in contamination.items():
        b = c_data["blocked_near_threshold"]
        a = c_data["admitted_just_above"]
        print(f"   {w}: blocked n={b['n']} mean={b.get('mean_return','-')}% win%={b.get('profitable_pct','-')}  |  "
              f"admitted n={a['n']} mean={a.get('mean_return','-')}% win%={a.get('profitable_pct','-')}")
        if "delta_mean_return" in c_data:
            print(f"         delta_mean={c_data['delta_mean_return']}%  delta_win%={c_data['delta_profitable_pct']}")

    # Verdict
    print("\n9. Decision verdict...")
    verdict, reason = derive_verdict(bucket_stats_blocked, contamination)
    print(f"\n   VERDICT: {verdict}")
    print(f"   REASON:  {reason}")

    # Save full JSON report
    output = {
        "meta": {
            "tool": "regime_confidence_near_threshold_audit",
            "generated": datetime.now(timezone.utc).isoformat(),
            "threshold": THRESHOLD,
            "bucket_definitions": {k: {"min": v[0], "max_exclusive": v[1]} for k, v in BUCKETS.items()},
            "time_range_days": DATES,
            "symbols": SYMBOLS,
            "windows": WINDOWS_MIN,
        },
        "population": {
            "blocked_total": len(blocked),
            "admitted_total": len(admitted),
            "blocked_by_bucket": dict(blocked_buckets),
            "admitted_by_bucket": dict(admitted_buckets),
        },
        "bucket_stats_blocked": bucket_stats_blocked,
        "admitted_control": admitted_control,
        "skew": {
            "by_symbol": symbol_skew,
            "by_strategy": strategy_skew,
            "by_side": side_skew,
        },
        "contamination": contamination,
        "verdict": {
            "decision": verdict,
            "reason": reason,
        },
        "blocked_cases": blocked_replayed,
        "admitted_cases": admitted_replayed,
    }

    out_path = REPORTS / "REGIME_CONFIDENCE_NEAR_THRESHOLD_FORENSIC_AUDIT_2026-03-25.json"
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\n   Full JSON saved: {out_path}")

    return output


if __name__ == "__main__":
    main()
