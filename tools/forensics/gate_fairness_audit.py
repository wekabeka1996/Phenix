"""
GATE_AND_POLICY_FAIRNESS_AUDIT_WITH_COUNTERFACTUAL_REPLAY
Full counterfactual replay engine for all blocked/rejected open attempts.
"""
import json, csv, os, sys
from datetime import datetime, timezone
from collections import Counter, defaultdict
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
LOGS = BASE / "logs"
DATA = BASE / "data" / "recorder"
REPORTS = BASE / "reports"

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT", "BNBUSDT"]
DATES = ["2026-03-22", "2026-03-23", "2026-03-24"]
WINDOWS_MIN = [15, 30, 45, 60, 120]


def load_bars():
    """Load all 3-min (180s) bar data for all symbols across 3 days."""
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


def normalize_family(why, nrr):
    """Normalize raw 'why' string into a canonical reason family."""
    if "uptrend blocks short" in why:
        return "DIRECTIONAL_SANITY:uptrend_blocks_short"
    if "downtrend blocks long" in why:
        return "DIRECTIONAL_SANITY:downtrend_blocks_long"
    if "flash up blocks short" in why:
        return "PRICE_MOTION_FLASH:flash_up_blocks_short"
    if "flash down blocks long" in why:
        return "PRICE_MOTION_FLASH:flash_down_blocks_long"
    if "bleed up blocks short" in why:
        return "PRICE_MOTION_BLEED:bleed_up_blocks_short"
    if "bleed down blocks long" in why:
        return "PRICE_MOTION_BLEED:bleed_down_blocks_long"
    if "price_motion flash insufficient" in why:
        return "PRICE_MOTION_DATA:flash_insufficient"
    if "FIX-CONF-GATE-01" in why:
        return "REGIME_CONFIDENCE:below_min"
    if "MAKER_ONLY_REJECT" in why:
        return "ADAPTER:MAKER_ONLY_REJECT"
    if "cooldown_after_close" in why:
        return "EXECUTION_GUARD:cooldown_after_close"
    if "local_manage_state_conflict" in why:
        return "EXECUTION_GUARD:local_state_conflict"
    if "ORPHANED_TTL" in why:
        return "PLACED_NOT_FILLED:ORPHANED_TTL"
    if "timeout" in why.lower():
        return "PLACED_NOT_FILLED:timeout"
    return f"OTHER:{nrr or why[:40]}"


def load_cases():
    """Load all blocked/rejected cases from order_log and trade_lifecycle."""
    cases = []

    # ORDER_REJECTED from order_log
    with open(LOGS / "order_log_v1.jsonl") as f:
        for line in f:
            if not line.strip():
                continue
            r = json.loads(line)
            if r.get("event_type") == "ORDER_REJECTED":
                why = r.get("why", "")
                nrr = r.get("nrr_code", "")
                fam = normalize_family(why, nrr)
                stage = "ADAPTER_REJECT" if "MAKER_ONLY" in why else "DM_POLICY_BLOCK"
                cases.append({
                    "ts_ms": r.get("timestamp", 0),
                    "symbol": r.get("symbol", ""),
                    "strategy_id": r.get("strategy_id", "aurora"),
                    "side": r.get("side", ""),
                    "rid": r.get("rid", ""),
                    "nrr_code": nrr,
                    "why": why,
                    "family": fam,
                    "stage": stage,
                    "order_price": r.get("price"),
                    "order_type": r.get("order_type"),
                })

    # Trade lifecycle for PLACED_NOT_FILLED and EXECUTION_GUARD_REJECT
    with open(LOGS / "trade_lifecycle.jsonl") as f:
        for line in f:
            if not line.strip():
                continue
            r = json.loads(line)
            status = r.get("status", "")
            close_reason = r.get("close_reason", "")

            if status in ("ORPHANED_TTL", "CANCELLED"):
                cases.append({
                    "ts_ms": r.get("intent_ts_ms") or r.get("order_ts_ms", 0),
                    "symbol": r.get("symbol", ""),
                    "strategy_id": r.get("strategy_id", ""),
                    "side": r.get("side", ""),
                    "rid": r.get("rid", ""),
                    "nrr_code": "",
                    "why": close_reason,
                    "family": f"PLACED_NOT_FILLED:{close_reason}",
                    "stage": "PLACED_NOT_FILLED",
                    "order_price": r.get("order_price") or r.get("entry_price"),
                    "order_type": r.get("order_type", "LIMIT"),
                })
            elif status == "REJECTED":
                cases.append({
                    "ts_ms": r.get("intent_ts_ms", 0),
                    "symbol": r.get("symbol", ""),
                    "strategy_id": r.get("strategy_id", ""),
                    "side": r.get("side", ""),
                    "rid": r.get("rid", ""),
                    "nrr_code": "",
                    "why": close_reason,
                    "family": f"EXECUTION_GUARD:{close_reason or 'unknown'}",
                    "stage": "EXECUTION_GUARD_REJECT",
                    "order_price": r.get("order_price"),
                    "order_type": r.get("order_type"),
                })

    return cases


def find_price_at_time(bars_dict, symbol, ts_ms):
    """Find closest bar close price at or just before ts_ms."""
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
    """Compute counterfactual outcomes at multiple time windows."""
    sym_bars = bars_dict.get(symbol, [])
    if not sym_bars or not entry_price or entry_price <= 0:
        return None

    results = {}
    for w in WINDOWS_MIN:
        end_ms = ts_ms + w * 60 * 1000
        window_bars = [b for b in sym_bars if ts_ms < b[0] <= end_ms]

        if not window_bars:
            results[f"{w}m"] = {
                "return_pct": None, "mfe_pct": None, "mae_pct": None,
                "status": "NO_BARS",
            }
            continue

        last_close = window_bars[-1][4]

        if side == "SELL":
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


def check_limit_fill(bars_dict, symbol, entry_price, side, ts_ms):
    """For LIMIT orders: did the market touch the limit price within 120m?"""
    sym_bars = bars_dict.get(symbol, [])
    end_ms = ts_ms + 120 * 60 * 1000
    window_bars = [b for b in sym_bars if ts_ms < b[0] <= end_ms]
    for b in window_bars:
        if side == "BUY" and b[3] <= entry_price:  # low touched bid
            return True
        if side == "SELL" and b[2] >= entry_price:  # high touched ask
            return True
    return False


def run_replay(bars_dict, cases):
    """Process all cases through counterfactual replay."""
    results = []
    for c in cases:
        symbol = c["symbol"]
        ts_ms = c["ts_ms"]
        side = c["side"]

        # Entry price reconstruction
        if c.get("order_price") and float(c["order_price"]) > 0:
            entry_price = float(c["order_price"])
            entry_conf = "EXACT"
        else:
            entry_price = find_price_at_time(bars_dict, symbol, ts_ms)
            entry_conf = "PROXY"

        # For LIMIT orders in PLACED_NOT_FILLED, check if price was touched
        order_type = c.get("order_type", "")
        limit_fill_cf = None
        if order_type == "LIMIT" and entry_price and c["stage"] == "PLACED_NOT_FILLED":
            limit_fill_cf = check_limit_fill(bars_dict, symbol, entry_price, side, ts_ms)

        # Compute outcomes
        outcomes = compute_outcomes(bars_dict, symbol, entry_price, side, ts_ms)

        ts_utc = ""
        if ts_ms:
            ts_utc = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).strftime(
                "%Y-%m-%d %H:%M:%S"
            )

        result = {
            "ts_ms": ts_ms,
            "ts_utc": ts_utc,
            "symbol": symbol,
            "strategy_id": c.get("strategy_id", ""),
            "side": side,
            "rid": c.get("rid", ""),
            "stage": c["stage"],
            "family": c["family"],
            "nrr_code": c.get("nrr_code", ""),
            "why": c["why"][:120],
            "order_type": order_type,
            "entry_price": entry_price,
            "entry_confidence": entry_conf,
            "replay_possible": outcomes is not None,
            "limit_fill_counterfactual": limit_fill_cf,
        }

        if outcomes:
            for w_key, w_val in outcomes.items():
                result[w_key] = w_val

        results.append(result)

    return results


def median(lst):
    if not lst:
        return 0
    s = sorted(lst)
    n = len(s)
    if n % 2 == 1:
        return s[n // 2]
    return (s[n // 2 - 1] + s[n // 2]) / 2


def compute_family_stats(results):
    """Compute detailed stats per reason family."""
    families = defaultdict(list)
    for r in results:
        families[r["family"]].append(r)

    stats = {}
    for fam, cases_list in sorted(families.items(), key=lambda x: -len(x[1])):
        n = len(cases_list)
        replay_ok = [c for c in cases_list if c.get("replay_possible")]

        sym_cnt = Counter(c["symbol"] for c in cases_list)
        side_cnt = Counter(c["side"] for c in cases_list)
        strat_cnt = Counter(c["strategy_id"] for c in cases_list)

        window_stats = {}
        for w in WINDOWS_MIN:
            key = f"{w}m"
            rets = [
                c[key]["return_pct"]
                for c in replay_ok
                if c.get(key) and c[key].get("return_pct") is not None
            ]
            mfes = [
                c[key]["mfe_pct"]
                for c in replay_ok
                if c.get(key) and c[key].get("mfe_pct") is not None
            ]
            maes = [
                c[key]["mae_pct"]
                for c in replay_ok
                if c.get(key) and c[key].get("mae_pct") is not None
            ]

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
                "median_mfe": round(median(mfes), 4) if mfes else None,
                "median_mae": round(median(maes), 4) if maes else None,
                "profitable_pct": round(profitable / len(rets) * 100, 1) if rets else None,
            }

        # Fairness interpretation
        r60 = window_stats.get("60m", {})
        if not r60.get("count"):
            interp = "UNPROVEN_DUE_TO_WEAK_ENTRY_RECONSTRUCTION"
        elif r60.get("profitable_pct", 0) > 55 and r60.get("mean_return", 0) > 0.05:
            interp = "SUSPICIOUSLY_OVER_TIGHT"
        elif r60.get("losing", 0) > r60.get("profitable", 0) * 1.3:
            interp = "DEFENSIVE_LIKELY_JUSTIFIED"
        else:
            interp = "MIXED"

        stats[fam] = {
            "count": n,
            "replay_eligible": len(replay_ok),
            "symbols": dict(sym_cnt.most_common()),
            "sides": dict(side_cnt.most_common()),
            "strategies": dict(strat_cnt.most_common()),
            "windows": window_stats,
            "interpretation": interp,
        }

    return stats


def compute_dimension_stats(results, dim_key):
    """Compute stats grouped by a single dimension (symbol/strategy/side)."""
    groups = defaultdict(list)
    for r in results:
        groups[r.get(dim_key, "UNKNOWN")].append(r)

    output = {}
    for grp_name, grp_cases in sorted(groups.items(), key=lambda x: -len(x[1])):
        replay_ok = [c for c in grp_cases if c.get("replay_possible")]
        rets_60 = [
            c["60m"]["return_pct"]
            for c in replay_ok
            if c.get("60m") and c["60m"].get("return_pct") is not None
        ]
        profitable = sum(1 for r in rets_60 if r > 0.02)
        losing = sum(1 for r in rets_60 if r < -0.02)

        output[grp_name] = {
            "total": len(grp_cases),
            "replay_ok": len(replay_ok),
            "returns_60m_count": len(rets_60),
            "profitable_60m": profitable,
            "losing_60m": losing,
            "mean_return_60m": round(sum(rets_60) / len(rets_60), 4) if rets_60 else None,
            "median_return_60m": round(median(rets_60), 4) if rets_60 else None,
            "stages": dict(Counter(c["stage"] for c in grp_cases).most_common()),
            "families": dict(Counter(c["family"] for c in grp_cases).most_common()),
        }
    return output


def main():
    print("Loading 3-min bar data...")
    bars_dict = load_bars()
    for sym in SYMBOLS:
        print(f"  {sym}: {len(bars_dict[sym])} bars")

    print("\nLoading blocked/rejected cases...")
    cases = load_cases()
    print(f"  Total cases: {len(cases)}")

    print("\nRunning counterfactual replay...")
    results = run_replay(bars_dict, cases)
    replay_ok = sum(1 for r in results if r["replay_possible"])
    print(f"  Replay possible: {replay_ok}/{len(results)}")

    print("\nComputing family-level stats...")
    family_stats = compute_family_stats(results)

    print("\nComputing dimension stats...")
    by_symbol = compute_dimension_stats(results, "symbol")
    by_strategy = compute_dimension_stats(results, "strategy_id")
    by_side = compute_dimension_stats(results, "side")

    # Stage summary
    stage_cnt = Counter(r["stage"] for r in results)

    # Save everything
    output = {
        "meta": {
            "generated": datetime.now(timezone.utc).isoformat(),
            "total_cases": len(results),
            "replay_possible": replay_ok,
            "time_range": {
                "start": min(r["ts_utc"] for r in results if r["ts_utc"]),
                "end": max(r["ts_utc"] for r in results if r["ts_utc"]),
            },
            "bar_resolution": "3min (180s)",
            "symbols": SYMBOLS,
            "windows": WINDOWS_MIN,
        },
        "population_summary": {
            "by_stage": dict(stage_cnt.most_common()),
            "by_symbol": {k: v["total"] for k, v in by_symbol.items()},
            "by_strategy": {k: v["total"] for k, v in by_strategy.items()},
            "by_side": {k: v["total"] for k, v in by_side.items()},
        },
        "family_stats": family_stats,
        "by_symbol": by_symbol,
        "by_strategy": by_strategy,
        "by_side": by_side,
        "case_level_results": results,
    }

    out_path = REPORTS / "GATE_FAIRNESS_AUDIT_FULL.json"
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nFull results saved to {out_path}")

    # Print summary
    print("\n" + "=" * 80)
    print("POPULATION SUMMARY")
    print("=" * 80)
    for stage, cnt in stage_cnt.most_common():
        print(f"  {stage}: {cnt}")

    print(f"\n  TOTAL: {len(results)}")

    print("\n" + "=" * 80)
    print("FAMILY-LEVEL FAIRNESS (60m window)")
    print("=" * 80)
    for fam, fs in sorted(family_stats.items(), key=lambda x: -x[1]["count"]):
        w60 = fs["windows"].get("60m", {})
        print(
            f"\n  {fam} (n={fs['count']}, replay={fs['replay_eligible']})"
        )
        if w60.get("count"):
            print(
                f"    60m: P={w60['profitable']} L={w60['losing']} N={w60['neutral']}"
                f"  mean={w60['mean_return']}% med={w60['median_return']}%"
                f"  MFE={w60['median_mfe']}% MAE={w60['median_mae']}%"
            )
        print(f"    Interpretation: {fs['interpretation']}")

    print("\n" + "=" * 80)
    print("BY SYMBOL (60m)")
    print("=" * 80)
    for sym, ss in sorted(by_symbol.items(), key=lambda x: -x[1]["total"]):
        print(
            f"  {sym}: total={ss['total']} P={ss['profitable_60m']} L={ss['losing_60m']}"
            f" mean={ss['mean_return_60m']}%"
        )

    print("\n" + "=" * 80)
    print("BY SIDE (60m)")
    print("=" * 80)
    for side, ss in sorted(by_side.items(), key=lambda x: -x[1]["total"]):
        print(
            f"  {side}: total={ss['total']} P={ss['profitable_60m']} L={ss['losing_60m']}"
            f" mean={ss['mean_return_60m']}%"
        )


if __name__ == "__main__":
    main()
