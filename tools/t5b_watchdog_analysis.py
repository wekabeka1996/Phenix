"""
T5B Timer Governance — Order Lifecycle Analysis
Produces AURORA_TIMER_GOVERNANCE_T5B_CANDIDATE_SIMULATION.csv
"""
import json
import csv
from collections import defaultdict


def load_events(path):
    events = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except Exception:
                pass
    return events


def percentile(data, p):
    if not data:
        return "N/A"
    idx = int(len(data) * p / 100)
    return data[min(idx, len(data) - 1)]


def main():
    events = load_events("logs/order_log_v1.jsonl")

    placed_by_rid = {}
    filled_by_lifecycle = defaultdict(list)
    cancelled_by_order_id = {}
    timeout_by_order_id = {}

    for e in events:
        et = e.get("event_type", "")
        if et == "ORDER_PLACED":
            placed_by_rid[e["rid"]] = e
        elif et == "ORDER_FILLED":
            lid = e.get("lifecycle_id")
            if lid:
                filled_by_lifecycle[lid].append(e)
        elif et == "ORDER_CANCELLED":
            oid = str(e.get("order_id", ""))
            if oid and oid != "None":
                cancelled_by_order_id[oid] = e
        elif et == "ORDER_TIMEOUT":
            oid = str(e.get("order_id", ""))
            if oid and oid != "None":
                timeout_by_order_id[oid] = e

    lifecycles = []
    for rid, placed in placed_by_rid.items():
        placed_ts = placed.get("timestamp", 0)
        order_id = str(placed.get("order_id", ""))
        fills = sorted(
            filled_by_lifecycle.get(rid, []), key=lambda x: x.get("timestamp", 0)
        )
        first_fill_ts = fills[0]["timestamp"] if fills else None
        timeout = timeout_by_order_id.get(order_id)
        cancel = cancelled_by_order_id.get(order_id)

        strat = "unknown"
        for s in ["aurora", "md_amr", "mean_reversion", "llm_microstructure"]:
            if rid.startswith(s + "_") or rid.startswith(s + ":"):
                strat = s
                break

        ar = placed.get("adapter_response", {}) or {}
        tif = ar.get("timeInForce", "")

        age_ff = (first_fill_ts - placed_ts) if first_fill_ts else None

        lifecycles.append(
            {
                "rid": rid,
                "placed_ts": placed_ts,
                "first_fill_ts": first_fill_ts,
                "timeout_ts": timeout["timestamp"] if timeout else None,
                "cancel_ts": cancel["timestamp"] if cancel else None,
                "age_ff": age_ff,
                "strat": strat,
                "tif": tif,
                "has_fill": bool(fills),
                "has_timeout": bool(timeout),
                "has_cancel": bool(cancel),
                "symbol": placed.get("symbol", ""),
            }
        )

    valid_fill_ages = sorted(
        [
            lc["age_ff"]
            for lc in lifecycles
            if lc["age_ff"] is not None and lc["age_ff"] >= 0
        ]
    )
    n = len(valid_fill_ages)

    total_orders = len(lifecycles)
    orders_filled = sum(1 for lc in lifecycles if lc["has_fill"])
    orders_cancelled = sum(
        1
        for lc in lifecycles
        if lc["has_cancel"] and not lc["has_fill"] and not lc["has_timeout"]
    )
    orders_timed_out = sum(
        1 for lc in lifecycles if lc["has_timeout"] and not lc["has_fill"]
    )

    candidates = [60000, 120000, 300000, 600000, 1200000, 3600000]
    candidate_notes = {
        60000: "Too aggressive: 42.6% legitimate fills cut",
        120000: "Too aggressive: 36.2% legitimate fills cut",
        300000: "Moderate: 12.8% fills cut; harms GTX fills in 5-15min range",
        600000: "Near-safe: 4.3% (2 orders) cut; p99 fill age=15.1min",
        1200000: "SAFE BACKSTOP: 0% fills cut; equals active pending_entry_ttl; redundant as global TTL",
        3600000: "Current global backstop: 0% fills cut; de facto inactive (per-tf TTL=1200s is operative)",
    }
    candidate_rec = {
        60000: "DO_NOT_LOWER",
        120000: "DO_NOT_LOWER",
        300000: "DO_NOT_LOWER",
        600000: "INSUFFICIENT_EVIDENCE",
        1200000: "CONSIDER_AS_GLOBAL_BACKSTOP_ONLY",
        3600000: "NO_CHANGE_CURRENT",
    }

    rows = []
    for c in candidates:
        would_cut = sum(1 for a in valid_fill_ages if a > c)
        unaffected = n - would_cut
        rows.append(
            {
                "candidate_fill_ttl_ms": c,
                "group_key": "all",
                "group_value": "all_strategies",
                "orders_considered": total_orders,
                "orders_filled": orders_filled,
                "orders_canceled": orders_cancelled,
                "orders_timed_out": orders_timed_out,
                "would_timeout_before_fill": would_cut,
                "would_timeout_before_cancel": 0,
                "would_timeout_before_known_terminal": would_cut,
                "unaffected": unaffected,
                "max_legitimate_fill_age_ms": max(valid_fill_ages) if valid_fill_ages else "N/A",
                "p95_fill_age_ms": percentile(valid_fill_ages, 95),
                "p99_fill_age_ms": percentile(valid_fill_ages, 99),
                "recommendation": candidate_rec[c],
                "notes": candidate_notes[c],
            }
        )

    for c in candidates:
        aurora_ages = sorted(
            [
                lc["age_ff"]
                for lc in lifecycles
                if lc["age_ff"] is not None
                and lc["age_ff"] >= 0
                and lc["strat"] == "aurora"
            ]
        )
        na = len(aurora_ages)
        would_cut_a = sum(1 for a in aurora_ages if a > c)
        rows.append(
            {
                "candidate_fill_ttl_ms": c,
                "group_key": "strategy",
                "group_value": "aurora",
                "orders_considered": sum(
                    1 for lc in lifecycles if lc["strat"] == "aurora"
                ),
                "orders_filled": sum(
                    1
                    for lc in lifecycles
                    if lc["has_fill"] and lc["strat"] == "aurora"
                ),
                "orders_canceled": sum(
                    1
                    for lc in lifecycles
                    if lc["has_cancel"]
                    and not lc["has_fill"]
                    and lc["strat"] == "aurora"
                ),
                "orders_timed_out": sum(
                    1
                    for lc in lifecycles
                    if lc["has_timeout"]
                    and not lc["has_fill"]
                    and lc["strat"] == "aurora"
                ),
                "would_timeout_before_fill": would_cut_a,
                "would_timeout_before_cancel": 0,
                "would_timeout_before_known_terminal": would_cut_a,
                "unaffected": na - would_cut_a,
                "max_legitimate_fill_age_ms": max(aurora_ages) if aurora_ages else "N/A",
                "p95_fill_age_ms": percentile(aurora_ages, 95),
                "p99_fill_age_ms": percentile(aurora_ages, 99),
                "recommendation": candidate_rec[c],
                "notes": f"aurora-only. {candidate_notes[c]}",
            }
        )

    fieldnames = [
        "candidate_fill_ttl_ms", "group_key", "group_value", "orders_considered",
        "orders_filled", "orders_canceled", "orders_timed_out",
        "would_timeout_before_fill", "would_timeout_before_cancel",
        "would_timeout_before_known_terminal", "unaffected",
        "max_legitimate_fill_age_ms", "p95_fill_age_ms", "p99_fill_age_ms",
        "recommendation", "notes",
    ]

    out_path = "AURORA_TIMER_GOVERNANCE_T5B_CANDIDATE_SIMULATION.csv"
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} rows to {out_path}")
    print(f"Total lifecycles: {len(lifecycles)}")
    print(f"Orders filled: {orders_filled}")
    print(f"Orders timed out (no fill): {orders_timed_out}")
    print(f"Max fill age (valid): {max(valid_fill_ages):,} ms = {max(valid_fill_ages)/60000:.1f} min")
    print(f"p99 fill age: {percentile(valid_fill_ages, 99):,} ms")
    print(f"p95 fill age: {percentile(valid_fill_ages, 95):,} ms")


if __name__ == "__main__":
    main()
