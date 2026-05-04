"""
Entry/Execution report (last N days).

Outputs per-symbol:
  - ENTRY_PLACED: count of entry ORDER_PLACED (client_order_id startswith ENTRY-)
  - ENTRY_FILLED (real): count of position opens from ACCOUNT_UPDATE (0 -> non-zero or flip open)
  - Fill-rate %: filled / placed
  - Avg time placement -> fill/cancel (seconds): per entry order rid, resolve via:
        PENDING_BRACKETS_STORED (fill) OR (MARKET order assumed immediate) OR
        ORDER_REJECTED / ORDER_CANCELLED / ORDER_TIMEOUT (cancel)
  - Quick exits: position segments with duration < threshold AND realized_pnl <= eps
        realized_pnl is approximated from wallet balance delta at the close/flip update,
        only when exactly 1 symbol position changed in that ACCOUNT_UPDATE interval.
  - Flips: close + immediate open opposite (direct sign-change or close->open within window)

Primary source: ops/wal/YYYY-MM-DD.jsonl
Secondary source (cancel/timeout): logs/order_log_v1.jsonl
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from statistics import mean


BASE = Path(__file__).resolve().parent.parent


def _safe_float(x) -> float | None:
    if x is None:
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _sign(x: float, *, eps: float = 1e-12) -> int:
    if x > eps:
        return 1
    if x < -eps:
        return -1
    return 0


def _event_ts_ms(ev: dict) -> int:
    ts = ev.get("ts")
    if isinstance(ts, (int, float)):
        return int(ts)
    ts = ev.get("timestamp")
    if isinstance(ts, (int, float)):
        return int(ts)
    pld = ev.get("pld") or {}
    ts = pld.get("ts_ms")
    if isinstance(ts, (int, float)):
        return int(ts)
    ts = pld.get("updateTime")
    if isinstance(ts, (int, float)):
        return int(ts)
    return 0


def _iter_jsonl(path: Path):
    with path.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def _wal_paths_for_window(wal_dir: Path, *, start_dt: datetime, end_dt: datetime) -> list[Path]:
    paths: list[Path] = []
    d = start_dt.date()
    while d <= end_dt.date():
        p = wal_dir / f"{d.isoformat()}.jsonl"
        if p.exists():
            paths.append(p)
        d += timedelta(days=1)
    return paths


@dataclass
class PosState:
    amt: float = 0.0
    open_ts_ms: int | None = None
    last_close_ts_ms: int | None = None
    last_close_sign: int | None = None


def _fmt_pct(num: int, denom: int) -> str:
    if denom <= 0:
        return "n/a"
    return f"{100.0 * num / denom:.1f}%"


def _fmt_s(ms_list: list[int]) -> str:
    if not ms_list:
        return "n/a"
    return f"{mean(ms_list) / 1000.0:.1f}s"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7, help="Trailing window in days (default: 7).")
    ap.add_argument("--wal-dir", type=Path, default=BASE / "ops" / "wal")
    ap.add_argument("--order-log", type=Path, default=BASE / "logs" / "order_log_v1.jsonl")
    ap.add_argument("--quick-exit-s", type=int, default=120)
    ap.add_argument("--flip-window-s", type=int, default=30)
    ap.add_argument("--pnl-eps", type=float, default=0.0, help="Count pnl <= eps as non-positive (default: 0.0).")
    args = ap.parse_args()

    end_dt = datetime.now(timezone.utc)
    start_dt = end_dt - timedelta(days=args.days)
    start_ms = int(start_dt.timestamp() * 1000)
    end_ms = int(end_dt.timestamp() * 1000)

    wal_paths = _wal_paths_for_window(args.wal_dir, start_dt=start_dt, end_dt=end_dt)
    if not wal_paths:
        print(f"No WAL files found in {args.wal_dir}", file=sys.stderr)
        return 2

    # ---- order_log (cancel/timeout) ----
    cancelled_ts: dict[str, int] = {}
    timeout_ts: dict[str, int] = {}
    if args.order_log.exists():
        for ev in _iter_jsonl(args.order_log):
            ts = ev.get("timestamp")
            if not isinstance(ts, (int, float)):
                continue
            ts_ms = int(ts)
            if ts_ms < start_ms or ts_ms > end_ms:
                continue
            et = ev.get("event_type")
            rid = ev.get("rid")
            if not isinstance(rid, str) or not rid:
                continue
            if et == "ORDER_CANCELLED":
                cancelled_ts[rid] = min(cancelled_ts.get(rid, ts_ms), ts_ms)
            elif et == "ORDER_TIMEOUT":
                timeout_ts[rid] = min(timeout_ts.get(rid, ts_ms), ts_ms)

    # ---- WAL aggregation ----
    placed_by_rid: dict[str, dict] = {}
    filled_ts_by_rid: dict[str, int] = {}
    rejected_ts_by_rid: dict[str, int] = {}

    placed_counts: dict[str, int] = defaultdict(int)
    resolution_lags_ms: dict[str, list[int]] = defaultdict(list)

    # Position-based metrics (from ACCOUNT_UPDATE_RECEIVED)
    filled_entries_real: dict[str, int] = defaultdict(int)
    quick_exits_nonpos: dict[str, int] = defaultdict(int)
    quick_exits_unknown_pnl: dict[str, int] = defaultdict(int)
    flips: dict[str, int] = defaultdict(int)

    pos_state: dict[str, PosState] = defaultdict(PosState)

    prev_positions: dict[str, float] | None = None
    prev_wb: float | None = None
    prev_ts: int | None = None

    flip_window_ms = int(args.flip_window_s * 1000)
    quick_exit_ms = int(args.quick_exit_s * 1000)

    for wal_path in wal_paths:
        for ev in _iter_jsonl(wal_path):
            verb = ev.get("verb")
            if not isinstance(verb, str):
                continue

            ts_ms = _event_ts_ms(ev)
            if ts_ms <= 0:
                continue

            # --- Order lifecycle (window-filtered) ---
            if verb == "ORDER_PLACED" and start_ms <= ts_ms <= end_ms:
                pld = ev.get("pld") or {}
                rid = ev.get("rid")
                if not isinstance(rid, str) or not rid:
                    continue
                sym = pld.get("symbol") or ev.get("symbol") or ""
                if not isinstance(sym, str) or not sym:
                    continue
                coid = pld.get("client_order_id") or ""
                if not isinstance(coid, str):
                    coid = str(coid)
                if not coid.startswith("ENTRY-"):
                    continue

                placed_by_rid[rid] = {
                    "symbol": sym,
                    "ts": ts_ms,
                    "side": pld.get("side") or "",
                    "client_order_id": coid,
                    "order_type": (pld.get("order_type") or "").upper(),
                }
                placed_counts[sym] += 1

            elif verb == "PENDING_BRACKETS_STORED" and start_ms <= ts_ms <= end_ms:
                pld = ev.get("pld") or {}
                rid = pld.get("rid") or ev.get("rid")
                if not isinstance(rid, str) or not rid:
                    continue
                filled_ts_by_rid[rid] = min(filled_ts_by_rid.get(rid, ts_ms), ts_ms)

            elif verb == "ORDER_REJECTED" and start_ms <= ts_ms <= end_ms:
                rid = ev.get("rid")
                if not isinstance(rid, str) or not rid:
                    continue
                rejected_ts_by_rid[rid] = min(rejected_ts_by_rid.get(rid, ts_ms), ts_ms)

            # --- Position lifecycle (account updates) ---
            if verb != "ACCOUNT_UPDATE_RECEIVED":
                continue

            # process account update even if slightly before start_ms (for baseline state)
            pld = ev.get("pld") or {}
            wb = _safe_float(pld.get("totalWalletBalance"))
            positions: dict[str, float] = {}
            for item in pld.get("positions") or []:
                sym = item.get("symbol")
                if not isinstance(sym, str) or not sym:
                    continue
                amt = _safe_float(item.get("positionAmt")) or 0.0
                if amt != 0.0:
                    positions[sym] = float(amt)

            if prev_positions is None:
                prev_positions = positions
                prev_wb = wb
                prev_ts = ts_ms
                continue

            # Ignore out-of-order updates
            if prev_ts is not None and ts_ms < prev_ts:
                continue

            # Identify which symbols changed position amount
            syms = set(prev_positions.keys()) | set(positions.keys())
            changed: list[str] = []
            for sym in syms:
                a = prev_positions.get(sym, 0.0)
                b = positions.get(sym, 0.0)
                if abs(a - b) > 1e-12:
                    changed.append(sym)

            wallet_delta = None
            if wb is not None and prev_wb is not None:
                wallet_delta = wb - prev_wb

            # Update metrics only inside the requested window
            in_window = start_ms <= ts_ms <= end_ms

            if in_window and changed:
                pnl_attrib = wallet_delta if (wallet_delta is not None and len(changed) == 1) else None

                for sym in changed:
                    prev_amt = prev_positions.get(sym, 0.0)
                    curr_amt = positions.get(sym, 0.0)
                    ps = pos_state[sym]

                    prev_sign = _sign(prev_amt)
                    curr_sign = _sign(curr_amt)

                    # direct flip: nonzero -> opposite nonzero
                    if prev_sign != 0 and curr_sign != 0 and prev_sign != curr_sign:
                        flips[sym] += 1

                        # close previous segment
                        if ps.open_ts_ms is not None:
                            dur = ts_ms - ps.open_ts_ms
                            if dur >= 0 and dur < quick_exit_ms:
                                if pnl_attrib is None:
                                    quick_exits_unknown_pnl[sym] += 1
                                elif pnl_attrib <= args.pnl_eps:
                                    quick_exits_nonpos[sym] += 1

                        # open new segment
                        filled_entries_real[sym] += 1
                        ps.open_ts_ms = ts_ms
                        ps.amt = curr_amt
                        ps.last_close_ts_ms = None
                        ps.last_close_sign = None
                        continue

                    # open: flat -> nonzero
                    if prev_sign == 0 and curr_sign != 0:
                        filled_entries_real[sym] += 1
                        ps.open_ts_ms = ts_ms
                        ps.amt = curr_amt

                        # close->open flip (within window)
                        if ps.last_close_ts_ms is not None and ps.last_close_sign is not None:
                            if (ts_ms - ps.last_close_ts_ms) <= flip_window_ms and ps.last_close_sign != curr_sign:
                                flips[sym] += 1
                            # only allow one match
                            ps.last_close_ts_ms = None
                            ps.last_close_sign = None
                        continue

                    # close: nonzero -> flat
                    if prev_sign != 0 and curr_sign == 0:
                        if ps.open_ts_ms is not None:
                            dur = ts_ms - ps.open_ts_ms
                            if dur >= 0 and dur < quick_exit_ms:
                                if pnl_attrib is None:
                                    quick_exits_unknown_pnl[sym] += 1
                                elif pnl_attrib <= args.pnl_eps:
                                    quick_exits_nonpos[sym] += 1

                        ps.last_close_ts_ms = ts_ms
                        ps.last_close_sign = prev_sign
                        ps.open_ts_ms = None
                        ps.amt = 0.0
                        continue

                    # size change
                    ps.amt = curr_amt

            # Advance baseline
            prev_positions = positions
            prev_wb = wb
            prev_ts = ts_ms

    # ---- Compute order resolution lags (placement -> fill/cancel) ----
    for rid, p in placed_by_rid.items():
        sym = p["symbol"]
        placed_ts = int(p["ts"])
        order_type = (p.get("order_type") or "").upper()

        end_ts: int | None = None
        fill_ts = filled_ts_by_rid.get(rid)
        if fill_ts is not None:
            end_ts = fill_ts
        elif order_type == "MARKET":
            # Market order is expected to execute immediately (or be rejected).
            # If we didn't observe a reject/cancel/timeout, treat as resolved at placement.
            if rid not in rejected_ts_by_rid and rid not in cancelled_ts and rid not in timeout_ts:
                end_ts = placed_ts

        if end_ts is None:
            candidates = [
                rejected_ts_by_rid.get(rid),
                cancelled_ts.get(rid),
                timeout_ts.get(rid),
            ]
            candidates = [c for c in candidates if isinstance(c, int) and c >= placed_ts]
            if candidates:
                end_ts = min(candidates)

        if end_ts is None:
            continue

        lag = end_ts - placed_ts
        if lag >= 0:
            resolution_lags_ms[sym].append(int(lag))

    # ---- Render report ----
    symbols = sorted(set(placed_counts) | set(filled_entries_real) | set(flips) | set(quick_exits_nonpos))
    if not symbols:
        print("No symbols found in the window.", file=sys.stderr)
        return 1

    print("=" * 88)
    print(
        f"Entry/Execution report | window: {start_dt.strftime('%Y-%m-%d %H:%M:%SZ')} -> "
        f"{end_dt.strftime('%Y-%m-%d %H:%M:%SZ')} | days={args.days}"
    )
    print("=" * 88)

    col_w = [12, 12, 12, 10, 16, 14, 10]
    headers = [
        "SYMBOL",
        "ENTRY_PLACED",
        "ENTRY_FILLED",
        "FILL-%",
        "AVG_PL->RES_s",
        "QUICK_EXITS",
        "FLIPS",
    ]
    sep = "+" + "+".join("-" * w for w in col_w) + "+"
    header_row = "|" + "|".join(h.center(w) for h, w in zip(headers, col_w)) + "|"

    print(sep)
    print(header_row)
    print(sep)

    total_placed = 0
    total_filled = 0
    total_quick = 0
    total_flips = 0
    all_lags: list[int] = []

    for sym in symbols:
        pl = int(placed_counts.get(sym, 0))
        fi = int(filled_entries_real.get(sym, 0))
        total_placed += pl
        total_filled += fi

        lags = resolution_lags_ms.get(sym, [])
        all_lags.extend(lags)

        qx = int(quick_exits_nonpos.get(sym, 0))
        total_quick += qx

        fl = int(flips.get(sym, 0))
        total_flips += fl

        row = [
            sym,
            str(pl),
            str(fi),
            _fmt_pct(fi, pl),
            _fmt_s(lags),
            str(qx),
            str(fl),
        ]
        print("|" + "|".join(v.center(w) for v, w in zip(row, col_w)) + "|")

    print(sep)

    totals = [
        "TOTAL",
        str(total_placed),
        str(total_filled),
        _fmt_pct(total_filled, total_placed),
        _fmt_s(all_lags),
        str(total_quick),
        str(total_flips),
    ]
    print("|" + "|".join(v.center(w) for v, w in zip(totals, col_w)) + "|")
    print(sep)

    unknown_qx = sum(int(quick_exits_unknown_pnl.get(s, 0)) for s in symbols)
    if unknown_qx:
        print(
            f"\nNote: {unknown_qx} quick-exit candidates had ambiguous PnL attribution "
            f"(multiple symbols changed in the same ACCOUNT_UPDATE interval) and were excluded."
        )

    print("\n" + "=" * 88)
    print(f"System-wide fill-rate (real): {_fmt_pct(total_filled, total_placed)}")
    print("=" * 88)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
