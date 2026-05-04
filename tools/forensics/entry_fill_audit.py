"""
Entry/Fill Audit — аналіз entry lifecycle за WAL/order_log (7 днів).

Метрики на символ:
  - ENTRY_PLACED   : кількість ORDER_PLACED (ENTRY-* client_order_id)
  - ENTRY_FILLED   : кількість PENDING_BRACKETS_STORED (=fills confirmed)
  - fill_rate_%    : filled / placed × 100
  - avg_time_to_fill_s   : середній час від ORDER_PLACED → PENDING_BRACKETS_STORED
  - avg_time_to_cancel_s : при відсутності заповнення (ORDER_REJECTED / timeout proxy)
  - quick_exits    : позиції тривалістю < 120s (PENDING_BRACKETS_STORED → CLEARED)
  - flips          : CLOSE eventos з data_ref=flip_orchestration_close
  - fill_lag_p50/p95 : перцентилі латентності fill (мс)

Sources (пріоритет):
  1. ops/wal/2026-02-{11..18}.jsonl
  2. logs/order_log_v1.jsonl  (поточна сесія — для ORDER_CANCELLED/TIMEOUT)
"""

import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from collections import defaultdict
from statistics import median, mean
import math

BASE = Path(__file__).parent.parent

# ── date window ─────────────────────────────────────────────────────────────
TODAY = datetime.now(timezone.utc)
DAYS_BACK = 7
WAL_DIR = BASE / "ops" / "wal"
ORDER_LOG = BASE / "logs" / "order_log_v1.jsonl"

# ── helpers ──────────────────────────────────────────────────────────────────


def iter_jsonl(path: Path):
    """Yield dicts from a JSONL file; skip malformed rows."""
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def load_wal_window(days: int = 7) -> list[dict]:
    """Load WAL events from the last `days` days."""
    records: list[dict] = []
    for d in range(days, -1, -1):  # inclusive today
        dt = TODAY - timedelta(days=d)
        fname = WAL_DIR / f"{dt.date()}.jsonl"
        if fname.exists():
            cnt_before = len(records)
            for ev in iter_jsonl(fname):
                records.append(ev)
            loaded = len(records) - cnt_before
            print(
                f"  [{dt.date()}] {fname.name}: {loaded:,} records", file=sys.stderr)
        else:
            print(f"  [{dt.date()}] MISSING: {fname.name}", file=sys.stderr)
    return records


def load_order_log() -> list[dict]:
    if ORDER_LOG.exists():
        return list(iter_jsonl(ORDER_LOG))
    return []


# ── event extraction ─────────────────────────────────────────────────────────

def extract_wal_events(records: list[dict]):
    """
    Returns:
      placed         : {rid -> {symbol, ts, side}}
      brackets_stored: {rid -> {symbol, ts, entry_order_id}}
      brackets_cleared: {entry_order_id -> {symbol, ts, reason}}
      order_rejected : {rid -> {symbol, ts, nrr_code}}
      close_events   : list of {symbol, ts, is_flip, why}
      open_events    : list of {symbol, ts, corr_id, side, price}
    """
    placed: dict[str, dict] = {}
    brackets_stored: dict[str, dict] = {}
    brackets_cleared: dict[str, dict] = {}
    order_rejected: dict[str, dict] = {}
    close_events: list[dict] = []
    open_events: list[dict] = []

    for ev in records:
        verb = ev.get("verb", "")
        ts = ev.get("ts", ev.get("timestamp", 0))
        rid = ev.get("rid", "")

        if verb == "ORDER_PLACED":
            pld = ev.get("pld") or {}
            sym = pld.get("symbol") or ev.get("symbol", "")
            co_id = pld.get("client_order_id", "")
            # Filter only ENTRY-* orders (bracket/TP/SL orders are not ENTRY-)
            if co_id.startswith("ENTRY-") or ev.get("metadata", {}).get("order_type") == "MARKET_ENTRY":
                placed[rid] = {
                    "symbol": sym,
                    "ts": ts,
                    "side": pld.get("side", ev.get("side", "")),
                    "client_order_id": co_id,
                }

        elif verb == "PENDING_BRACKETS_STORED":
            pld = ev.get("pld") or {}
            sym = pld.get("symbol", "")
            entry_rid = pld.get("rid", rid)
            # rid of PENDING_BRACKETS_STORED == rid of ORDER_PLACED
            brackets_stored[entry_rid] = {
                "symbol": sym,
                "ts": ts,
                "entry_order_id": pld.get("entry_order_id", ""),
                "idem_key": pld.get("idem_key", ""),
                "oco_group_id": pld.get("oco_group_id", ""),
            }

        elif verb == "PENDING_BRACKETS_CLEARED":
            pld = ev.get("pld") or {}
            eo_id = pld.get("entry_order_id", "")
            brackets_cleared[eo_id] = {
                "symbol": pld.get("symbol", ""),
                "ts": ts,
                "reason": pld.get("reason", ""),
                "why": ev.get("why", ""),
            }

        elif verb == "ORDER_REJECTED":
            pld = ev.get("pld") or {}
            sym = pld.get("symbol") or ev.get("symbol", "")
            order_rejected[rid] = {
                "symbol": sym,
                "ts": ts,
                "nrr_code": ev.get("nrr_code") or pld.get("reason_code", ""),
            }

        elif verb == "CLOSE":
            pld = ev.get("pld") or {}
            data_ref = ev.get("data_ref") or []
            is_flip = "flip_orchestration_close" in data_ref
            close_events.append({
                "symbol": pld.get("symbol", ""),
                "ts": ts,
                "is_flip": is_flip,
                "why": ev.get("why", ""),
                "trigger": pld.get("trigger", ""),
            })

        elif verb == "OPEN":
            pld = ev.get("pld") or {}
            open_events.append({
                "symbol": pld.get("symbol", ""),
                "ts": ts,
                "corr_id": ev.get("corr_id", ""),
                "side": pld.get("side", ""),
                "price": pld.get("price", ""),
            })

    return placed, brackets_stored, brackets_cleared, order_rejected, close_events, open_events


def extract_orderlog_extras(order_log: list[dict]):
    """Extract ORDER_CANCELLED and ORDER_TIMEOUT from order_log (current session)."""
    cancelled: dict[str, dict] = {}
    timeout: dict[str, dict] = {}
    fills_orderlog: dict[str, dict] = {}  # rid → fill details

    for ev in order_log:
        et = ev.get("event_type", "")
        rid = ev.get("rid", "")
        ts = ev.get("timestamp", 0)
        sym = ev.get("symbol", "")

        if et == "ORDER_CANCELLED":
            cancelled[rid] = {"symbol": sym,
                              "ts": ts, "why": ev.get("why", "")}
        elif et == "ORDER_TIMEOUT":
            timeout[rid] = {"symbol": sym, "ts": ts}
        elif et == "ORDER_FILL_DISCOVERED":
            fills_orderlog[rid] = {
                "symbol": sym,
                "ts": ts,
                "fill_price": ev.get("fill_price") or ev.get("price"),
                "pnl": ev.get("realized_pnl") or ev.get("pnl"),
            }

    return cancelled, timeout, fills_orderlog


# ── analysis ─────────────────────────────────────────────────────────────────

def analyse(
    placed, brackets_stored, brackets_cleared, order_rejected,
    close_events, open_events, cancelled, timeout, fills_orderlog
):
    # Per-symbol accumulators
    per_sym: dict[str, dict] = defaultdict(lambda: {
        "placed": 0,
        "filled": 0,
        "fill_lags_ms": [],     # placed→filled в мс
        "cancel_lags_ms": [],   # placed→cancel/reject/timeout в мс
        "position_durations_ms": [],  # stored→cleared в мс
        "quick_exits": 0,       # duration < 120s
        "flips": 0,
    })

    # ── fill-lag analysis ────────────────────────────────────────────────────
    for rid, p in placed.items():
        sym = p["symbol"]
        per_sym[sym]["placed"] += 1

        bs = brackets_stored.get(rid)
        if bs:
            per_sym[sym]["filled"] += 1
            lag_ms = bs["ts"] - p["ts"]
            if lag_ms >= 0:
                per_sym[sym]["fill_lags_ms"].append(lag_ms)
        else:
            # Check cancel / reject / timeout
            end_ts = None
            if rid in order_rejected:
                end_ts = order_rejected[rid]["ts"]
            elif rid in cancelled:
                end_ts = cancelled[rid]["ts"]
            elif rid in timeout:
                end_ts = timeout[rid]["ts"]

            if end_ts:
                lag_ms = end_ts - p["ts"]
                if lag_ms >= 0:
                    per_sym[sym]["cancel_lags_ms"].append(lag_ms)

    # ── position duration analysis ───────────────────────────────────────────
    # Map: entry_order_id → BRACKETS_STORED info (stored has entry_order_id field)
    eo_to_stored: dict[str, dict] = {}
    for rid, bs in brackets_stored.items():
        eo_id = bs.get("entry_order_id", "")
        if eo_id:
            eo_to_stored[eo_id] = bs

    for eo_id, cleared in brackets_cleared.items():
        sym = cleared["symbol"]
        stored = eo_to_stored.get(eo_id)
        if stored:
            dur_ms = cleared["ts"] - stored["ts"]
            if dur_ms >= 0:
                per_sym[sym]["position_durations_ms"].append(dur_ms)
                if dur_ms < 120_000:  # < 120s
                    per_sym[sym]["quick_exits"] += 1

    # ── flips count ──────────────────────────────────────────────────────────
    for ce in close_events:
        if ce["is_flip"]:
            sym = ce["symbol"]
            per_sym[sym]["flips"] += 1

    return per_sym


def fmt_seconds(ms_list: list[float]) -> str:
    if not ms_list:
        return "n/a"
    return f"{mean(ms_list)/1000:.1f}s"


def fmt_pct(num: int, denom: int) -> str:
    if denom == 0:
        return "n/a"
    return f"{100*num/denom:.1f}%"


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    print("=" * 70)
    print(
        f"  Entry/Fill Audit  |  window: last {DAYS_BACK} days  |  {TODAY.date()}")
    print("=" * 70)

    print("\n[1/3] Loading WAL files...", file=sys.stderr)
    records = load_wal_window(DAYS_BACK)
    print(f"  Total WAL records loaded: {len(records):,}", file=sys.stderr)

    print("\n[2/3] Loading order_log (current session)...", file=sys.stderr)
    order_log = load_order_log()
    print(f"  Total order_log records: {len(order_log):,}", file=sys.stderr)

    print("\n[3/3] Extracting events...", file=sys.stderr)
    placed, brackets_stored, brackets_cleared, order_rejected, close_events, open_events = \
        extract_wal_events(records)

    cancelled, timeout, fills_orderlog = extract_orderlog_extras(order_log)

    print(f"\n  ORDER_PLACED (ENTRY-*):       {len(placed):,}")
    print(f"  PENDING_BRACKETS_STORED:      {len(brackets_stored):,}")
    print(f"  PENDING_BRACKETS_CLEARED:     {len(brackets_cleared):,}")
    print(f"  ORDER_REJECTED (WAL):         {len(order_rejected):,}")
    print(f"  CLOSE events (WAL):           {len(close_events):,}")
    print(
        f"     of which FLIP:             {sum(1 for c in close_events if c['is_flip']):,}")
    print(f"  ORDER_CANCELLED (order_log):  {len(cancelled):,}")
    print(f"  ORDER_TIMEOUT (order_log):    {len(timeout):,}")
    print()

    per_sym = analyse(
        placed, brackets_stored, brackets_cleared, order_rejected,
        close_events, open_events, cancelled, timeout, fills_orderlog
    )

    # ── per-symbol table ─────────────────────────────────────────────────────
    col_w = [12, 8, 8, 10, 14, 16, 13, 8]
    headers = ["SYMBOL", "PLACED", "FILLED", "FILL-%",
               "AVG_FILL_s", "AVG_CANCEL_s", "QUICK_EXITS", "FLIPS"]

    sep = "+" + "+".join("-" * w for w in col_w) + "+"
    header_row = "|" + "|".join(h.center(w)
                                for h, w in zip(headers, col_w)) + "|"

    print(sep)
    print(header_row)
    print(sep)

    total_placed = 0
    total_filled = 0
    all_fill_lags: list[float] = []
    all_canon_lags: list[float] = []
    all_quick_exits = 0
    all_flips = 0

    for sym in sorted(per_sym.keys()):
        d = per_sym[sym]
        pl = d["placed"]
        fi = d["filled"]
        total_placed += pl
        total_filled += fi
        all_fill_lags.extend(d["fill_lags_ms"])
        all_canon_lags.extend(d["cancel_lags_ms"])
        all_quick_exits += d["quick_exits"]
        all_flips += d["flips"]

        fill_rate = fmt_pct(fi, pl)
        avg_fill = fmt_seconds(d["fill_lags_ms"])
        avg_cancel = fmt_seconds(d["cancel_lags_ms"])

        row = [sym, str(pl), str(fi), fill_rate, avg_fill, avg_cancel,
               str(d["quick_exits"]), str(d["flips"])]
        print("|" + "|".join(v.center(w) for v, w in zip(row, col_w)) + "|")

    print(sep)
    # Totals row
    totals = ["TOTAL",
              str(total_placed),
              str(total_filled),
              fmt_pct(total_filled, total_placed),
              fmt_seconds(all_fill_lags),
              fmt_seconds(all_canon_lags),
              str(all_quick_exits),
              str(all_flips)]
    print("|" + "|".join(v.center(w) for v, w in zip(totals, col_w)) + "|")
    print(sep)

    # ── fill latency distribution ─────────────────────────────────────────────
    print("\n── Fill Latency Distribution (all symbols) ──────────────────────────")
    if all_fill_lags:
        sl = sorted(all_fill_lags)
        n = len(sl)
        p50 = sl[int(n * 0.50)]
        p75 = sl[int(n * 0.75)]
        p95 = sl[min(int(n * 0.95), n-1)]
        p99 = sl[min(int(n * 0.99), n-1)]
        print(f"  Samples : {n}")
        print(f"  p50     : {p50/1000:.1f}s  ({p50:.0f}ms)")
        print(f"  p75     : {p75/1000:.1f}s  ({p75:.0f}ms)")
        print(f"  p95     : {p95/1000:.1f}s  ({p95:.0f}ms)")
        print(f"  p99     : {p99/1000:.1f}s  ({p99:.0f}ms)")
        print(f"  max     : {sl[-1]/1000:.1f}s  ({sl[-1]:.0f}ms)")
    else:
        print("  No fill lag samples in WAL window.")

    # ── position duration distribution ────────────────────────────────────────
    all_durations: list[float] = []
    for d in per_sym.values():
        all_durations.extend(d["position_durations_ms"])

    print("\n── Position Duration Distribution (all symbols) ────────────────────")
    if all_durations:
        sd = sorted(all_durations)
        n = len(sd)
        p50 = sd[int(n * 0.50)]
        p95 = sd[min(int(n * 0.95), n-1)]
        print(f"  Samples      : {n}")
        print(f"  p50 duration : {p50/1000:.0f}s  ({p50/60000:.1f} min)")
        print(f"  p95 duration : {p95/1000:.0f}s  ({p95/60000:.1f} min)")
        print(f"  Quick exits (<120s): {all_quick_exits}")
    else:
        print("  No position duration data in WAL window.")

    # ── unfilled ORDER_PLACED (no brackets, no reject/cancel in WAL) ─────────
    unfilled_no_trace: dict[str, int] = defaultdict(int)
    for rid, p in placed.items():
        bs = brackets_stored.get(rid)
        rej = order_rejected.get(rid)
        can = cancelled.get(rid)
        tmo = timeout.get(rid)
        if not bs and not rej and not can and not tmo:
            unfilled_no_trace[p["symbol"]] += 1

    if any(unfilled_no_trace.values()):
        print("\n── ORDER_PLACED with no fill/cancel/reject trace ────────────────────")
        print("  (likely pending at session end or expired silently)")
        for sym, cnt in sorted(unfilled_no_trace.items()):
            print(f"  {sym}: {cnt}")

    # ── flip detail ───────────────────────────────────────────────────────────
    print("\n── Flip Events Detail ───────────────────────────────────────────────")
    for ce in close_events:
        if ce["is_flip"]:
            ts_str = datetime.fromtimestamp(
                ce["ts"] / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            print(
                f"  {ts_str} UTC  {ce['symbol']:10s}  trigger={ce['trigger']}  why={ce['why']}")

    if all_flips == 0:
        print("  No flip events detected in window.")

    print("\n" + "=" * 70)
    print(f"  System-wide fill-rate: {fmt_pct(total_filled, total_placed)}")
    print("=" * 70)


if __name__ == "__main__":
    main()
