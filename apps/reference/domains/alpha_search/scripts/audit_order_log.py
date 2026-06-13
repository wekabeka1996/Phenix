#!/usr/bin/env python3
"""
audit_order_log.py — Diagnostic script to verify all strategies are actively
proposing trades by analyzing order_log_v1.jsonl and decision_ledger_v1.jsonl.

Usage:
    python audit_order_log.py
"""

import json
import csv
import re
import sys
from pathlib import Path
from collections import Counter, defaultdict
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

KNOWN_STRATEGIES = [
    "aurora",
    "mean_reversion",
    "alpha_mr_s01",
    "md_amr",
    "alpha_ta_ensemble",
    "llm_microstructure",
]

# Resolve paths relative to the script location
SCRIPT_DIR = Path(__file__).resolve().parent
DOMAIN_DIR = SCRIPT_DIR.parent  # alpha_search domain root
ORDER_LOG = DOMAIN_DIR / "logs" / "order_log_v1.jsonl"
DECISION_LEDGER = DOMAIN_DIR / "logs" / "shadow_telemetry" / "decision_ledger_v1.jsonl"
CSV_OUTPUT = DOMAIN_DIR / "logs" / "alpha_search_runtime" / "strategy_coverage_audit.csv"

# rid patterns → strategy_id inference
RID_PATTERNS = [
    (re.compile(r"^aurora[_-]", re.IGNORECASE), "aurora"),
    (re.compile(r"^mean_reversion[_-]", re.IGNORECASE), "mean_reversion"),
    (re.compile(r"^alpha_mr_s01[_-]", re.IGNORECASE), "alpha_mr_s01"),
    (re.compile(r"^mdamr[_-]", re.IGNORECASE), "md_amr"),
    (re.compile(r"^md_amr[_-]", re.IGNORECASE), "md_amr"),
    (re.compile(r"^alpha_ta_ensemble[_-]", re.IGNORECASE), "alpha_ta_ensemble"),
    (re.compile(r"^llm_microstructure[_-]", re.IGNORECASE), "llm_microstructure"),
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def read_jsonl(path: Path):
    """Yield parsed JSON objects from a JSONL file, skipping bad lines."""
    if not path.exists():
        print(f"[WARN] File not found: {path}")
        return
    with open(path, "r", encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, start=1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                yield json.loads(raw)
            except json.JSONDecodeError as exc:
                print(f"[WARN] Malformed JSON at {path.name}:{lineno} — {exc}")


def infer_strategy_from_rid(rid: str) -> str:
    """Try to guess the strategy_id from the rid field."""
    if not rid:
        return ""
    for pattern, strategy in RID_PATTERNS:
        if pattern.search(rid):
            return strategy
    return ""


def resolve_strategy(record: dict) -> str:
    """Return the strategy_id, falling back to rid-based inference."""
    sid = (record.get("strategy_id") or "").strip()
    if sid:
        return sid
    return infer_strategy_from_rid(record.get("rid", ""))


def ts_to_str(ts) -> str:
    """Best-effort conversion of a timestamp value to ISO string."""
    if ts is None:
        return "N/A"
    if isinstance(ts, str):
        return ts
    try:
        # Assume epoch millis if large, else epoch seconds
        if ts > 1e12:
            return datetime.fromtimestamp(ts / 1000, tz=timezone.utc).isoformat()
        return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
    except (OSError, ValueError, TypeError):
        return str(ts)


def extract_ts(record: dict):
    """Return a numeric timestamp from a record (millis or seconds)."""
    for key in ("ts", "timestamp", "created_at", "t"):
        val = record.get(key)
        if val is not None:
            try:
                return float(val)
            except (ValueError, TypeError):
                pass
    return None


def extract_reject_reason(record: dict) -> str:
    """Pull the rejection reason from known field locations."""
    reason = record.get("why", "")
    if reason:
        return str(reason)
    meta = record.get("metadata") or {}
    reason = meta.get("reject_reason", "")
    if reason:
        return str(reason)
    return "unknown"


# ---------------------------------------------------------------------------
# Order-log analysis
# ---------------------------------------------------------------------------


def analyse_order_log():
    """Parse order_log_v1.jsonl and return per-strategy statistics."""

    # Global event-type counts
    event_counts = Counter()

    # Per-strategy accumulators
    strat_intents = Counter()
    strat_rejected = Counter()
    strat_symbols = defaultdict(Counter)     # strategy -> symbol -> count
    strat_reject_reasons = defaultdict(Counter)
    strat_first_ts = {}                       # strategy -> earliest ts
    strat_last_ts = {}                        # strategy -> latest ts

    # Global counts for non-strategy events
    orders_placed = 0
    orders_filled = 0
    positions_closed = 0

    for rec in read_jsonl(ORDER_LOG):
        etype = rec.get("event_type", "")
        event_counts[etype] += 1

        if etype in ("ORDER_INTENT", "DECISION_INTENT_REJECTED"):
            sid = resolve_strategy(rec)
            symbol = rec.get("symbol", rec.get("pair", "UNKNOWN"))
            ts = extract_ts(rec)

            if etype == "ORDER_INTENT":
                strat_intents[sid] += 1
            else:
                strat_rejected[sid] += 1
                reason = extract_reject_reason(rec)
                strat_reject_reasons[sid][reason] += 1

            strat_symbols[sid][symbol] += 1

            if ts is not None:
                if sid not in strat_first_ts or ts < strat_first_ts[sid]:
                    strat_first_ts[sid] = ts
                if sid not in strat_last_ts or ts > strat_last_ts[sid]:
                    strat_last_ts[sid] = ts

        elif etype == "ORDER_PLACED":
            orders_placed += 1
        elif etype == "ORDER_FILLED":
            orders_filled += 1
        elif etype == "POSITION_CLOSED":
            positions_closed += 1

    return {
        "event_counts": event_counts,
        "strat_intents": strat_intents,
        "strat_rejected": strat_rejected,
        "strat_symbols": strat_symbols,
        "strat_reject_reasons": strat_reject_reasons,
        "strat_first_ts": strat_first_ts,
        "strat_last_ts": strat_last_ts,
        "orders_placed": orders_placed,
        "orders_filled": orders_filled,
        "positions_closed": positions_closed,
    }


# ---------------------------------------------------------------------------
# Decision-ledger analysis
# ---------------------------------------------------------------------------


def analyse_decision_ledger():
    """Parse decision_ledger_v1.jsonl and return per-strategy ledger stats."""

    strat_terminal = defaultdict(Counter)     # strategy -> terminal_status -> count
    strat_pnl = defaultdict(float)            # strategy -> sum of realized pnl
    strat_pnl_count = Counter()               # strategy -> number of pnl entries
    gate_failures = defaultdict(Counter)      # strategy -> gate_name -> fail count

    for rec in read_jsonl(DECISION_LEDGER):
        sid = resolve_strategy(rec)
        terminal = rec.get("terminal_status", "UNKNOWN")
        strat_terminal[sid][terminal] += 1

        # Realized PnL
        pnl = rec.get("realized_pnl", rec.get("pnl"))
        if pnl is not None:
            try:
                strat_pnl[sid] += float(pnl)
                strat_pnl_count[sid] += 1
            except (ValueError, TypeError):
                pass

        # Gate chain failure analysis
        gate_trace = rec.get("gate_trace_summary")
        if gate_trace:
            if isinstance(gate_trace, list):
                for gate in gate_trace:
                    if isinstance(gate, dict):
                        status = gate.get("status", gate.get("result", ""))
                        name = gate.get("gate", gate.get("name", "unknown_gate"))
                        if str(status).upper() in ("FAIL", "FAILED", "REJECTED", "BLOCKED"):
                            gate_failures[sid][name] += 1
            elif isinstance(gate_trace, dict):
                for name, info in gate_trace.items():
                    if isinstance(info, dict):
                        status = info.get("status", info.get("result", ""))
                        if str(status).upper() in ("FAIL", "FAILED", "REJECTED", "BLOCKED"):
                            gate_failures[sid][name] += 1

    return {
        "strat_terminal": strat_terminal,
        "strat_pnl": strat_pnl,
        "strat_pnl_count": strat_pnl_count,
        "gate_failures": gate_failures,
    }


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

SEPARATOR = "=" * 80
THIN_SEP = "-" * 80


def print_header(title: str):
    print(f"\n{SEPARATOR}")
    print(f"  {title}")
    print(SEPARATOR)


def report_order_log(data: dict):
    print_header("ORDER LOG ANALYSIS")

    # 1. Global event counts
    print(f"\n{'Event Type':<30} {'Count':>10}")
    print(THIN_SEP)
    for etype in ["ORDER_INTENT", "DECISION_INTENT_REJECTED", "ORDER_PLACED",
                   "ORDER_FILLED", "POSITION_CLOSED"]:
        print(f"  {etype:<28} {data['event_counts'].get(etype, 0):>10}")
    others = {k: v for k, v in data["event_counts"].items()
              if k not in {"ORDER_INTENT", "DECISION_INTENT_REJECTED",
                           "ORDER_PLACED", "ORDER_FILLED", "POSITION_CLOSED"}}
    for etype, cnt in sorted(others.items()):
        print(f"  {etype:<28} {cnt:>10}")

    # 2. Per-strategy breakdown
    all_sids = sorted(
        set(data["strat_intents"]) | set(data["strat_rejected"]) | set(KNOWN_STRATEGIES)
    )

    print_header("PER-STRATEGY INTENT BREAKDOWN")
    print(f"\n{'Strategy':<25} {'Intents':>10} {'Rejected':>10} {'Accept%':>10} {'First':>28} {'Last':>28}")
    print(THIN_SEP)

    for sid in all_sids:
        intents = data["strat_intents"].get(sid, 0)
        rejected = data["strat_rejected"].get(sid, 0)
        total = intents + rejected
        acc = f"{intents / total * 100:.1f}%" if total > 0 else "N/A"
        first = ts_to_str(data["strat_first_ts"].get(sid))
        last = ts_to_str(data["strat_last_ts"].get(sid))
        marker = " ⚠ MISSING" if total == 0 and sid in KNOWN_STRATEGIES else ""
        print(f"  {sid:<23} {intents:>10} {rejected:>10} {acc:>10} {first:>28} {last:>28}{marker}")

    # 3. Missing strategies
    missing = [s for s in KNOWN_STRATEGIES
               if data["strat_intents"].get(s, 0) + data["strat_rejected"].get(s, 0) == 0]
    if missing:
        print(f"\n  [ALERT] Strategies with ZERO activity: {', '.join(missing)}")

    # 4. Per-strategy symbol distribution
    print_header("PER-STRATEGY SYMBOL DISTRIBUTION")
    for sid in all_sids:
        symbols = data["strat_symbols"].get(sid)
        if not symbols:
            continue
        print(f"\n  {sid}:")
        for sym, cnt in symbols.most_common(10):
            print(f"    {sym:<20} {cnt:>8}")

    # 5. Top rejection reasons
    print_header("TOP REJECTION REASONS BY STRATEGY")
    for sid in all_sids:
        reasons = data["strat_reject_reasons"].get(sid)
        if not reasons:
            continue
        print(f"\n  {sid}:")
        for reason, cnt in reasons.most_common(10):
            print(f"    {reason:<50} {cnt:>8}")


def report_decision_ledger(data: dict):
    print_header("DECISION LEDGER ANALYSIS")

    all_sids = sorted(set(data["strat_terminal"]) | set(KNOWN_STRATEGIES))

    # 1. Terminal status distribution
    print(f"\n{'Strategy':<25} {'Terminal Status':<25} {'Count':>10}")
    print(THIN_SEP)
    for sid in all_sids:
        statuses = data["strat_terminal"].get(sid)
        if not statuses:
            print(f"  {sid:<23} {'(no entries)':<25}")
            continue
        first = True
        for status, cnt in statuses.most_common():
            label = sid if first else ""
            print(f"  {label:<23} {status:<25} {cnt:>10}")
            first = False

    # 2. Realized PnL
    print_header("REALIZED PnL SUMMARY")
    print(f"\n{'Strategy':<25} {'Total PnL':>15} {'# Trades':>10}")
    print(THIN_SEP)
    for sid in all_sids:
        pnl = data["strat_pnl"].get(sid, 0.0)
        cnt = data["strat_pnl_count"].get(sid, 0)
        print(f"  {sid:<23} {pnl:>15.4f} {cnt:>10}")

    # 3. Gate chain failures
    print_header("GATE CHAIN FAILURE ANALYSIS")
    any_gate = False
    for sid in all_sids:
        gates = data["gate_failures"].get(sid)
        if not gates:
            continue
        any_gate = True
        print(f"\n  {sid}:")
        for gate_name, cnt in gates.most_common(10):
            print(f"    {gate_name:<40} {cnt:>8} failures")
    if not any_gate:
        print("\n  No gate failures recorded.")


# ---------------------------------------------------------------------------
# CSV output
# ---------------------------------------------------------------------------


def write_csv(order_data: dict, ledger_data: dict):
    """Write a CSV summary combining order-log and ledger insights."""
    CSV_OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    all_sids = sorted(
        set(order_data["strat_intents"])
        | set(order_data["strat_rejected"])
        | set(ledger_data["strat_terminal"])
        | set(KNOWN_STRATEGIES)
    )

    fieldnames = [
        "strategy_id",
        "is_known",
        "total_intents",
        "total_rejected",
        "acceptance_rate",
        "symbols_traded",
        "top_reject_reason",
        "first_intent_ts",
        "last_intent_ts",
        "ledger_entries",
        "realized_pnl",
        "top_terminal_status",
        "gate_failures_total",
    ]

    with open(CSV_OUTPUT, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()

        for sid in all_sids:
            intents = order_data["strat_intents"].get(sid, 0)
            rejected = order_data["strat_rejected"].get(sid, 0)
            total = intents + rejected
            acc = f"{intents / total * 100:.1f}%" if total > 0 else "N/A"

            symbols = order_data["strat_symbols"].get(sid, Counter())
            top_reason_counter = order_data["strat_reject_reasons"].get(sid, Counter())
            top_reason = top_reason_counter.most_common(1)[0][0] if top_reason_counter else ""

            terminal_counts = ledger_data["strat_terminal"].get(sid, Counter())
            ledger_total = sum(terminal_counts.values())
            top_terminal = terminal_counts.most_common(1)[0][0] if terminal_counts else ""

            gate_total = sum(ledger_data["gate_failures"].get(sid, Counter()).values())

            writer.writerow({
                "strategy_id": sid,
                "is_known": sid in KNOWN_STRATEGIES,
                "total_intents": intents,
                "total_rejected": rejected,
                "acceptance_rate": acc,
                "symbols_traded": len(symbols),
                "top_reject_reason": top_reason,
                "first_intent_ts": ts_to_str(order_data["strat_first_ts"].get(sid)),
                "last_intent_ts": ts_to_str(order_data["strat_last_ts"].get(sid)),
                "ledger_entries": ledger_total,
                "realized_pnl": f"{ledger_data['strat_pnl'].get(sid, 0.0):.4f}",
                "top_terminal_status": top_terminal,
                "gate_failures_total": gate_total,
            })

    print(f"\n[INFO] CSV written to: {CSV_OUTPUT}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    print(SEPARATOR)
    print("  ALPHA SEARCH — STRATEGY COVERAGE AUDIT")
    print(f"  Generated: {datetime.now(timezone.utc).isoformat()}")
    print(SEPARATOR)

    print(f"\n  Order log:        {ORDER_LOG}")
    print(f"  Decision ledger:  {DECISION_LEDGER}")
    print(f"  CSV output:       {CSV_OUTPUT}")

    if not ORDER_LOG.exists() and not DECISION_LEDGER.exists():
        print("\n[ERROR] Neither log file exists. Nothing to analyse.")
        sys.exit(1)

    order_data = analyse_order_log()
    ledger_data = analyse_decision_ledger()

    report_order_log(order_data)
    report_decision_ledger(ledger_data)

    write_csv(order_data, ledger_data)

    # Final verdict
    print_header("VERDICT")
    missing = [s for s in KNOWN_STRATEGIES
               if order_data["strat_intents"].get(s, 0)
               + order_data["strat_rejected"].get(s, 0) == 0]
    if missing:
        print(f"\n  ❌ {len(missing)} known strategies have ZERO order-log activity:")
        for s in missing:
            print(f"     • {s}")
        print("\n  Action required: investigate why these strategies are silent.")
    else:
        print("\n  ✅ All known strategies have order-log activity.")

    ledger_missing = [s for s in KNOWN_STRATEGIES
                      if s not in ledger_data["strat_terminal"]]
    if ledger_missing:
        print(f"\n  ⚠  {len(ledger_missing)} known strategies missing from decision ledger:")
        for s in ledger_missing:
            print(f"     • {s}")

    print(f"\n{SEPARATOR}\n")


if __name__ == "__main__":
    main()
