"""
Bracket Coverage Report: TP/SL diagnostic for all positions.

Parses domain_execution_position.log* and order_log_v1.jsonl to determine
which positions had TP/SL brackets placed and which didn't.

Matching logic:
  - MARKET entries: SL/TP placed within 10s of same symbol = covered
  - LIMIT entries: track deferred flow (stored -> fill -> brackets_placed)
  - LIMIT entries that stored but never filled = CANCELLED (not a failure)
  - ORDER_CANCELLED/ORDER_TIMEOUT from order_log used for classification

Usage:
    python tools/bracket_coverage_report.py [--log-dir logs/]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional


def _parse_ts(ts_str: str) -> float:
    """Parse log timestamp to epoch seconds."""
    try:
        dt = datetime.strptime(ts_str[:23], "%Y-%m-%d %H:%M:%S,%f")
        return dt.timestamp()
    except (ValueError, IndexError):
        return 0.0


@dataclass
class EntryOrder:
    """Represents a single entry order (MARKET or LIMIT)."""
    timestamp: str
    ts_epoch: float
    symbol: str
    order_id: str
    client_order_id: str
    side: str
    order_type: str  # MARKET or LIMIT
    qty: str
    price: str
    rid: str = ""
    # Bracket status
    sl_placed: bool = False
    tp_placed: bool = False
    sl_order_id: str = ""
    tp_order_id: str = ""
    sl_price: str = ""
    tp_price: str = ""
    # Deferred bracket tracking (LIMIT orders)
    deferred_stored: bool = False
    deferred_stored_entry_id: str = ""  # Links to LIMIT-DEFERRED flow
    deferred_fill_received: bool = False
    deferred_brackets_placed: bool = False
    # Order outcome
    was_filled: bool = False  # True if known to have been filled
    was_cancelled: bool = False  # True if cancelled/expired/timed-out
    outcome: str = ""  # "FILLED", "CANCELLED", "TIMEOUT", "UNKNOWN"
    # Errors
    errors: list[str] = field(default_factory=list)
    # Source of bracket
    bracket_source: str = ""
    fill_ts: str = ""


@dataclass
class BracketEvent:
    """SL or TP placement event."""
    timestamp: str
    ts_epoch: float
    symbol: str
    order_id: str
    client_order_id: str
    price: str
    side: str
    bracket_type: str  # "SL" or "TP"
    matched: bool = False


def parse_domain_logs(log_paths: list[Path]) -> tuple[list[EntryOrder], list[BracketEvent], list[dict]]:
    """Parse domain_execution_position.log files."""
    entries: list[EntryOrder] = []
    brackets: list[BracketEvent] = []
    events: list[dict] = []

    # Regex patterns
    re_market_entry = re.compile(
        r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d+).*?MARKET entry placed.*?'orderId': (\d+).*?'symbol': '(\w+)'.*?"
        r"'clientOrderId': '(ENTRY-\w+)'.*?'origQty': '([\d.]+)'.*?'side': '(\w+)'"
    )
    re_limit_entry = re.compile(
        r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d+).*?LIMIT entry placed.*?'orderId': (\d+).*?'symbol': '(\w+)'.*?"
        r"'clientOrderId': '(ENTRY-\w+)'.*?'price': '([\d.]+)'.*?'origQty': '([\d.]+)'.*?'side': '(\w+)'"
    )
    # Field order in Binance response: orderId, symbol, clientOrderId, ..., side, ..., stopPrice
    re_sl_placed = re.compile(
        r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d+).*?SL placed.*?'orderId': (\d+).*?'symbol': '(\w+)'.*?"
        r"'clientOrderId': '(SL-\w+)'.*?'side': '(\w+)'.*?'stopPrice': '([\d.]+)'"
    )
    re_tp_placed = re.compile(
        r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d+).*?TP placed.*?'orderId': (\d+).*?'symbol': '(\w+)'.*?"
        r"'clientOrderId': '(TP-\w+)'.*?'side': '(\w+)'.*?'stopPrice': '([\d.]+)'"
    )
    re_deferred_stored = re.compile(
        r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d+).*?\[LIMIT-DEFERRED\] Stored pending brackets for (\w+) entry (\d+).*?SL=([\d.]+), TP=([\d.]+)"
    )
    re_deferred_fill = re.compile(
        r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d+).*?\[LIMIT-DEFERRED\] Fill received for (\w+) entry (\d+)"
    )
    re_deferred_placed = re.compile(
        r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d+).*?\[LIMIT-DEFERRED\] Brackets placed for (\w+): SL=(\w+), TP=(\w+)"
    )
    re_timeout_fill = re.compile(
        r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d+).*?\[TIMEOUT-FILL\] Placing deferred TP/SL brackets for (\w+) entry (\d+)"
    )
    re_error = re.compile(
        r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d+).*?(ERROR|CRITICAL).*?(BracketsConfig|Failed to deliver|Failed to place brackets)(.*)"
    )
    re_polling_fill = re.compile(
        r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d+).*?POLLING DETECTED FILL: (\d+) \((\w+)\) qty=([\d.]+)"
    )

    # Sort: log.1 (older) first, then log (current)
    sorted_paths = sorted(log_paths, key=lambda p: (
        0 if '.1' in p.name else 1, p.name))

    for log_path in sorted_paths:
        try:
            with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    # MARKET entry
                    m = re_market_entry.search(line)
                    if m:
                        ts = m.group(1)
                        entry = EntryOrder(
                            timestamp=ts, ts_epoch=_parse_ts(ts),
                            symbol=m.group(3), order_id=m.group(2),
                            client_order_id=m.group(4), side=m.group(6),
                            order_type="MARKET", qty=m.group(5), price="MARKET",
                            was_filled=True, outcome="FILLED",  # MARKET always fills
                        )
                        entries.append(entry)
                        events.append({"ts": ts, "type": "MARKET_ENTRY", "symbol": m.group(
                            3), "order_id": m.group(2)})
                        continue

                    # LIMIT entry
                    m = re_limit_entry.search(line)
                    if m:
                        ts = m.group(1)
                        entry = EntryOrder(
                            timestamp=ts, ts_epoch=_parse_ts(ts),
                            symbol=m.group(3), order_id=m.group(2),
                            client_order_id=m.group(4), side=m.group(7),
                            order_type="LIMIT", qty=m.group(6), price=m.group(5),
                        )
                        entries.append(entry)
                        events.append(
                            {"ts": ts, "type": "LIMIT_ENTRY", "symbol": m.group(3), "order_id": m.group(2)})
                        continue

                    # SL placed (groups: 1=ts, 2=orderId, 3=symbol, 4=clientOrderId, 5=side, 6=stopPrice)
                    m = re_sl_placed.search(line)
                    if m:
                        ts = m.group(1)
                        brackets.append(BracketEvent(
                            timestamp=ts, ts_epoch=_parse_ts(ts),
                            symbol=m.group(3), order_id=m.group(2),
                            client_order_id=m.group(4), price=m.group(6),
                            side=m.group(5), bracket_type="SL",
                        ))
                        events.append(
                            {"ts": ts, "type": "SL_PLACED", "symbol": m.group(3)})
                        continue

                    # TP placed (groups: 1=ts, 2=orderId, 3=symbol, 4=clientOrderId, 5=side, 6=stopPrice)
                    m = re_tp_placed.search(line)
                    if m:
                        ts = m.group(1)
                        brackets.append(BracketEvent(
                            timestamp=ts, ts_epoch=_parse_ts(ts),
                            symbol=m.group(3), order_id=m.group(2),
                            client_order_id=m.group(4), price=m.group(6),
                            side=m.group(5), bracket_type="TP",
                        ))
                        events.append(
                            {"ts": ts, "type": "TP_PLACED", "symbol": m.group(3)})
                        continue

                    # LIMIT-DEFERRED: stored
                    m = re_deferred_stored.search(line)
                    if m:
                        ts, sym, entry_id = m.group(1), m.group(2), m.group(3)
                        events.append(
                            {"ts": ts, "type": "DEFERRED_STORED", "symbol": sym, "entry_id": entry_id})
                        # Match to LIMIT entry by order_id
                        for e in reversed(entries):
                            if e.symbol == sym and e.order_type == "LIMIT" and e.order_id == entry_id:
                                e.deferred_stored = True
                                e.deferred_stored_entry_id = entry_id
                                break
                        continue

                    # LIMIT-DEFERRED: fill received
                    m = re_deferred_fill.search(line)
                    if m:
                        ts, sym, entry_id = m.group(1), m.group(2), m.group(3)
                        events.append(
                            {"ts": ts, "type": "DEFERRED_FILL", "symbol": sym, "entry_id": entry_id})
                        for e in reversed(entries):
                            if e.symbol == sym and e.deferred_stored_entry_id == entry_id:
                                e.deferred_fill_received = True
                                e.was_filled = True
                                e.outcome = "FILLED"
                                e.fill_ts = ts
                                break
                        continue

                    # TIMEOUT-FILL
                    m = re_timeout_fill.search(line)
                    if m:
                        ts, sym, entry_id = m.group(1), m.group(2), m.group(3)
                        events.append(
                            {"ts": ts, "type": "TIMEOUT_FILL", "symbol": sym, "entry_id": entry_id})
                        for e in reversed(entries):
                            if e.symbol == sym and e.deferred_stored_entry_id == entry_id:
                                e.deferred_fill_received = True
                                e.was_filled = True
                                e.outcome = "FILLED"
                                e.fill_ts = ts
                                e.bracket_source = "PathC-timeout"
                                break
                        continue

                    # LIMIT-DEFERRED: brackets placed
                    m = re_deferred_placed.search(line)
                    if m:
                        ts, sym, sl_status, tp_status = m.group(
                            1), m.group(2), m.group(3), m.group(4)
                        events.append(
                            {"ts": ts, "type": "DEFERRED_BRACKETS_OK", "symbol": sym})
                        for e in reversed(entries):
                            if e.symbol == sym and e.deferred_fill_received and not e.deferred_brackets_placed:
                                e.deferred_brackets_placed = True
                                if sl_status == "OK":
                                    e.sl_placed = True
                                if tp_status == "OK":
                                    e.tp_placed = True
                                if not e.bracket_source or e.bracket_source == "PathC-timeout":
                                    e.bracket_source = e.bracket_source or "PathC-deferred"
                                break
                        continue

                    # POLLING DETECTED FILL
                    m = re_polling_fill.search(line)
                    if m:
                        ts, oid, sym, qty = m.group(1), m.group(
                            2), m.group(3), m.group(4)
                        events.append(
                            {"ts": ts, "type": "POLLING_FILL", "symbol": sym, "order_id": oid, "qty": qty})
                        # Mark entry as filled
                        for e in reversed(entries):
                            if e.symbol == sym and e.order_id == oid:
                                e.was_filled = True
                                e.outcome = "FILLED"
                                e.fill_ts = e.fill_ts or ts
                                break
                        continue

                    # Errors
                    m = re_error.search(line)
                    if m:
                        ts, level, error_type, detail = m.group(
                            1), m.group(2), m.group(3), m.group(4)
                        events.append({"ts": ts, "type": "ERROR",
                                      "error": f"{error_type}{detail[:100]}"})
                        # Associate error with most recent entry in 60s window
                        ts_epoch = _parse_ts(ts)
                        for e in reversed(entries):
                            if ts_epoch - e.ts_epoch < 60:
                                e.errors.append(
                                    f"[{ts}] {error_type}{detail[:80]}")
                                break
                        continue

        except FileNotFoundError:
            print(f"  [WARN] Log file not found: {log_path}")

    return entries, brackets, events


def match_brackets_to_entries(entries: list[EntryOrder], brackets: list[BracketEvent]) -> None:
    """Match SL/TP bracket events to their entry orders by symbol + time proximity."""

    for b in brackets:
        best_entry: Optional[EntryOrder] = None
        best_delta = float("inf")

        for e in entries:
            if e.symbol != b.symbol:
                continue
            # SL/TP must come AFTER the entry (0 to 30 seconds window)
            delta = b.ts_epoch - e.ts_epoch
            if 0 <= delta < 30 and delta < best_delta:
                # Check it's not already matched to an earlier bracket of same type
                if b.bracket_type == "SL" and not e.sl_placed:
                    best_entry = e
                    best_delta = delta
                elif b.bracket_type == "TP" and not e.tp_placed:
                    best_entry = e
                    best_delta = delta

        if best_entry:
            b.matched = True
            if b.bracket_type == "SL":
                best_entry.sl_placed = True
                best_entry.sl_order_id = b.order_id
                best_entry.sl_price = b.price
                if not best_entry.bracket_source:
                    best_entry.bracket_source = "PathA-direct"
            elif b.bracket_type == "TP":
                best_entry.tp_placed = True
                best_entry.tp_order_id = b.order_id
                best_entry.tp_price = b.price
                if not best_entry.bracket_source:
                    best_entry.bracket_source = "PathA-direct"


def enrich_from_order_log(entries: list[EntryOrder], jsonl_path: Path) -> dict:
    """Enrich entries with cancel/timeout data from order_log_v1.jsonl."""
    stats = {"placed": 0, "cancelled": 0, "timeout": 0,
             "rejected": 0, "fill_discovered": 0}
    if not jsonl_path.exists():
        return stats

    # Build order_id lookup
    entry_by_oid: dict[str, EntryOrder] = {e.order_id: e for e in entries}
    # Build client_order_id lookup
    entry_by_coid: dict[str, EntryOrder] = {
        e.client_order_id: e for e in entries}

    with open(jsonl_path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            try:
                d = json.loads(line.strip())
                et = d.get("event_type", "")
                oid = str(d.get("order_id", ""))
                coid = d.get("client_order_id", "")

                if et == "ORDER_PLACED":
                    stats["placed"] += 1

                elif et == "ORDER_CANCELLED":
                    stats["cancelled"] += 1
                    entry = entry_by_oid.get(oid) or entry_by_coid.get(coid)
                    if entry and not entry.was_filled:
                        entry.was_cancelled = True
                        entry.outcome = "CANCELLED"

                elif et == "ORDER_TIMEOUT":
                    stats["timeout"] += 1
                    entry = entry_by_oid.get(oid) or entry_by_coid.get(coid)
                    if entry and not entry.was_filled:
                        entry.was_cancelled = True
                        entry.outcome = "TIMEOUT"

                elif et == "ORDER_REJECTED":
                    stats["rejected"] += 1

                elif et == "ORDER_FILL_DISCOVERED":
                    stats["fill_discovered"] += 1
                    # Note: ORDER_FILL_DISCOVERED does not reliably identify which
                    # entry was filled. We rely on domain log events (DEFERRED_FILL,
                    # POLLING_FILL) for fill classification instead.

            except json.JSONDecodeError:
                continue

    # Mark LIMIT entries without any outcome as UNKNOWN
    for e in entries:
        if e.order_type == "LIMIT" and not e.outcome:
            e.outcome = "UNKNOWN (probably cancelled)"

    return stats


def format_report(entries: list[EntryOrder], events: list[dict], wal_stats: dict) -> str:
    """Generate human-readable bracket coverage report."""
    lines: list[str] = []

    # Header
    lines.append("=" * 110)
    lines.append("  BRACKET COVERAGE REPORT  (TP/SL Diagnostic)")
    lines.append("=" * 110)
    lines.append("")

    # Classify entries
    filled_entries = [e for e in entries if e.was_filled]
    cancelled_entries = [
        e for e in entries if e.was_cancelled and not e.was_filled]
    unknown_entries = [
        e for e in entries if not e.was_filled and not e.was_cancelled]

    covered = sum(1 for e in filled_entries if e.sl_placed and e.tp_placed)
    uncovered_filled = [
        e for e in filled_entries if not e.sl_placed or not e.tp_placed]
    market_entries = sum(1 for e in entries if e.order_type == "MARKET")
    limit_entries = sum(1 for e in entries if e.order_type == "LIMIT")

    lines.append(f"  Total Entry Orders:       {len(entries)}")
    lines.append(f"    MARKET entries:          {market_entries}")
    lines.append(f"    LIMIT entries:           {limit_entries}")
    lines.append("")
    lines.append(f"  Outcomes:")
    lines.append(f"    FILLED (had position):   {len(filled_entries)}")
    lines.append(
        f"    CANCELLED/TIMEOUT:       {len(cancelled_entries)}  (no position, brackets N/A)")
    lines.append(f"    UNKNOWN:                 {len(unknown_entries)}")
    lines.append("")
    lines.append(f"  Bracket Coverage (FILLED orders only):")
    if filled_entries:
        lines.append(
            f"    SL + TP placed:          {covered}/{len(filled_entries)}  ({covered/len(filled_entries)*100:.0f}%)")
    else:
        lines.append(f"    SL + TP placed:          0/0")
    lines.append(
        f"    MISSING brackets:        {len(uncovered_filled)}  {'<-- NEEDS FIX' if uncovered_filled else '(none)'}")
    lines.append(
        f"    Errors in logs:          {sum(len(e.errors) for e in entries)}")
    lines.append("")

    # Per-symbol summary (FILLED only)
    symbols = sorted(set(e.symbol for e in entries))
    lines.append("-" * 110)
    lines.append("  PER-SYMBOL SUMMARY (FILLED entries)")
    lines.append("-" * 110)
    for sym in symbols:
        sym_filled = [e for e in filled_entries if e.symbol == sym]
        sym_cancelled = [e for e in cancelled_entries if e.symbol == sym]
        sym_covered = sum(1 for e in sym_filled if e.sl_placed and e.tp_placed)
        sym_uncov = len(sym_filled) - sym_covered
        if sym_filled:
            status = "OK" if sym_uncov == 0 else f"FAIL ({sym_uncov} missing brackets)"
        else:
            status = f"(no fills, {len(sym_cancelled)} cancelled)"
        lines.append(
            f"    {sym:<12}  filled={len(sym_filled):<4}  covered={sym_covered:<4}  cancelled={len(sym_cancelled):<4}  {status}")

    # ===== DETAILED TABLE: FILLED ENTRIES =====
    lines.append("")
    lines.append("-" * 110)
    lines.append(
        "  FILLED POSITIONS  (these HAD a position => brackets required)")
    lines.append("-" * 110)
    lines.append("")
    header = f"  {'Time':<24} {'Symbol':<12} {'Type':<8} {'Side':<6} {'OrderID':<16} {'SL':<6} {'TP':<6} {'Source':<18} {'Notes'}"
    lines.append(header)
    lines.append("  " + "-" * 106)

    for e in filled_entries:
        sl_status = "YES" if e.sl_placed else "NO"
        tp_status = "YES" if e.tp_placed else "NO"
        notes = []
        if e.errors:
            notes.append(f"{len(e.errors)}err")
        if e.sl_price:
            notes.append(f"SL@{e.sl_price}")
        if e.tp_price:
            notes.append(f"TP@{e.tp_price}")

        line = f"  {e.timestamp:<24} {e.symbol:<12} {e.order_type:<8} {e.side:<6} {e.order_id:<16} {sl_status:<6} {tp_status:<6} {e.bracket_source:<18} {' '.join(notes)}"
        lines.append(line)

        if e.errors:
            for err in e.errors:
                lines.append(f"      ERROR: {err[:100]}")

        if e.order_type == "LIMIT":
            deferred = []
            if e.deferred_stored:
                deferred.append("stored")
            if e.deferred_fill_received:
                deferred.append(f"fill@{e.fill_ts[:19]}")
            if e.deferred_brackets_placed:
                deferred.append("brackets_OK")
            if deferred:
                lines.append(f"      DEFERRED: {' -> '.join(deferred)}")

    # ===== CANCELLED ENTRIES (collapsed) =====
    if cancelled_entries:
        lines.append("")
        lines.append("-" * 110)
        lines.append(
            f"  CANCELLED/TIMEOUT ENTRIES ({len(cancelled_entries)})  (no position => brackets N/A)")
        lines.append("-" * 110)
        for e in cancelled_entries:
            lines.append(
                f"    {e.timestamp:<24} {e.symbol:<12} {e.order_type:<8} {e.side:<6} {e.order_id:<16} {e.outcome}")

    # ===== UNKNOWN ENTRIES =====
    if unknown_entries:
        lines.append("")
        lines.append("-" * 110)
        lines.append(
            f"  UNKNOWN OUTCOME ENTRIES ({len(unknown_entries)})  (probably cancelled, no fill seen)")
        lines.append("-" * 110)
        for e in unknown_entries:
            lines.append(
                f"    {e.timestamp:<24} {e.symbol:<12} {e.order_type:<8} {e.side:<6} {e.order_id:<16} {e.outcome}")

    # ===== CRITICAL: UNCOVERED FILLED POSITIONS =====
    if uncovered_filled:
        lines.append("")
        lines.append("=" * 110)
        lines.append(
            "  *** UNCOVERED POSITIONS (FILLED but MISSING TP/SL) ***")
        lines.append("=" * 110)
        for e in uncovered_filled:
            missing = []
            if not e.sl_placed:
                missing.append("SL")
            if not e.tp_placed:
                missing.append("TP")
            lines.append(
                f"  {e.timestamp}  {e.symbol:<12}  {e.order_type:<8}  OrderID={e.order_id}")
            lines.append(f"      Missing: {', '.join(missing)}")
            lines.append(
                f"      Side: {e.side}, Qty: {e.qty}, Outcome: {e.outcome}")
            if e.errors:
                for err in e.errors:
                    lines.append(f"      ROOT CAUSE: {err[:120]}")
            else:
                lines.append(
                    f"      ROOT CAUSE: Unknown (no error captured for this entry)")
            lines.append("")
    else:
        lines.append("")
        lines.append("=" * 110)
        lines.append("  ALL FILLED POSITIONS COVERED WITH TP/SL BRACKETS")
        lines.append("=" * 110)

    # Error timeline
    error_events = [ev for ev in events if ev["type"] == "ERROR"]
    if error_events:
        lines.append("")
        lines.append("-" * 110)
        lines.append("  ERROR TIMELINE")
        lines.append("-" * 110)
        for ev in error_events:
            lines.append(f"  [{ev['ts']}] {ev['error'][:100]}")

    # Order log stats
    lines.append("")
    lines.append("-" * 110)
    lines.append(f"  ORDER LOG STATS (order_log_v1.jsonl):")
    for k, v in wal_stats.items():
        lines.append(f"    {k}: {v}")
    lines.append("-" * 110)

    lines.append("")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Bracket Coverage Report: TP/SL diagnostic")
    parser.add_argument("--log-dir", default="logs",
                        help="Directory with log files")
    parser.add_argument("--output", default=None,
                        help="Write report to file (default: stdout)")
    args = parser.parse_args()

    log_dir = Path(args.log_dir)
    if not log_dir.is_absolute():
        project_root = Path(__file__).parent.parent
        log_dir = project_root / args.log_dir

    print(f"Scanning logs in: {log_dir}")

    # Find domain log files
    domain_logs = []
    for pattern in ["domain_execution_position.log", "domain_execution_position.log.*"]:
        domain_logs.extend(sorted(log_dir.glob(pattern)))

    if not domain_logs:
        print(
            f"  [ERROR] No domain_execution_position.log* files found in {log_dir}")
        sys.exit(1)

    print(
        f"  Found {len(domain_logs)} log files: {[p.name for p in domain_logs]}")

    # Parse domain logs
    entries, brackets, events = parse_domain_logs(domain_logs)
    print(
        f"  Parsed {len(entries)} entry orders, {len(brackets)} bracket events")

    # Match brackets to entries by time proximity
    match_brackets_to_entries(entries, brackets)
    print(
        f"  Matched {sum(1 for b in brackets if b.matched)} bracket events to entries")

    # Enrich from order log
    order_log_path = log_dir / "order_log_v1.jsonl"
    wal_stats = enrich_from_order_log(entries, order_log_path)
    print(f"  Order log: {wal_stats}")

    # Generate report
    report = format_report(entries, events, wal_stats)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"\n  Report written to: {args.output}")
    else:
        print(report)


if __name__ == "__main__":
    main()
