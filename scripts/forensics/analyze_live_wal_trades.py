#!/usr/bin/env python3
"""
Deep-dive live trading forensics from WAL + recorder bars.

Inputs:
- `ops/wal/*.jsonl` (structured events: op+verb+rids)
- `data/recorder/**/{SYMBOL}_{TF}.csv` (bars + feature columns)

Output:
- Markdown report in `reports/`
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import math
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import yaml


UTC = dt.timezone.utc


def _safe_float(x: Any) -> Optional[float]:
    if x is None:
        return None
    if isinstance(x, (int, float)):
        v = float(x)
        if math.isnan(v) or math.isinf(v):
            return None
        return v
    s = str(x).strip()
    if not s or s.lower() == "none":
        return None
    try:
        v = float(s)
    except Exception:
        return None
    if math.isnan(v) or math.isinf(v):
        return None
    return v


def _safe_int(x: Any) -> Optional[int]:
    if x is None:
        return None
    if isinstance(x, int):
        return int(x)
    s = str(x).strip()
    if not s or s.lower() == "none":
        return None
    try:
        return int(float(s))
    except Exception:
        return None


def _fmt_ts_ms(ts_ms: Optional[int]) -> str:
    if not ts_ms:
        return "n/a"
    try:
        return dt.datetime.fromtimestamp(ts_ms / 1000.0, tz=UTC).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(ts_ms)


def _fmt_f(x: Optional[float], digits: int = 4) -> str:
    if x is None:
        return "n/a"
    if math.isnan(x) or math.isinf(x):
        return "n/a"
    return f"{x:.{digits}f}"


def _fmt_money(x: Optional[float]) -> str:
    if x is None:
        return "n/a"
    if math.isnan(x) or math.isinf(x):
        return "n/a"
    if abs(x) < 1:
        return f"{x:.6f}".rstrip("0").rstrip(".")
    return f"{x:.4f}"


def _dir_from_qty(qty: float) -> str:
    return "long" if qty > 0 else "short"


def load_verb_registry(path: Path) -> set[Tuple[str, str]]:
    if not path.exists():
        return set()
    data = yaml.safe_load(path.read_text(encoding="utf-8", errors="replace")) or {}
    reg = data.get("registry") or []
    pairs: set[Tuple[str, str]] = set()
    for it in reg:
        if not isinstance(it, dict):
            continue
        op = str(it.get("op") or "").strip()
        verb = str(it.get("verb") or "").strip()
        if op and verb:
            pairs.add((op, verb))
    return pairs


def iter_wal_files(wal_dir: Path, explicit: Optional[Sequence[Path]]) -> List[Path]:
    if explicit:
        return [p for p in explicit if p.exists()]
    if not wal_dir.exists():
        return []
    files = sorted([p for p in wal_dir.glob("*.jsonl") if p.is_file()])
    return files[-2:] if len(files) >= 2 else files


def iter_wal_events(paths: Sequence[Path]) -> Iterable[Dict[str, Any]]:
    for p in paths:
        with p.open("r", encoding="utf-8", errors="replace") as f:
            for line_no, line in enumerate(f, start=1):
                s = line.strip()
                if not s:
                    continue
                try:
                    obj = json.loads(s)
                except Exception:
                    continue
                if not isinstance(obj, dict):
                    continue
                obj["_wal_file"] = str(p)
                obj["_wal_line"] = line_no
                yield obj


@dataclass(frozen=True)
class DecOpen:
    ts_ms: int
    rid: str
    symbol: str
    side: str  # BUY/SELL
    order_type: str  # LIMIT/MARKET
    qty: Optional[float]
    price: Optional[float]
    stop_price: Optional[float]
    target_price: Optional[float]
    valid_for_ms: Optional[int]
    data_ref: List[str]


@dataclass(frozen=True)
class DecClose:
    ts_ms: int
    rid: str
    symbol: str
    reason: Optional[str]
    trigger: Optional[str]
    why: Optional[str]
    data_ref: List[str]


@dataclass(frozen=True)
class PendingBracketsStored:
    ts_ms: int
    rid: str
    entry_order_id: str
    symbol: str
    side: str
    qty: Optional[float]
    sl: Optional[float]
    tp: Optional[float]


@dataclass(frozen=True)
class PendingBracketsCleared:
    ts_ms: int
    rid: str
    entry_order_id: str
    symbol: str
    reason: str


@dataclass(frozen=True)
class AccountPos:
    symbol: str
    qty: float
    entry_price: float
    mark_price: float
    unrealized_pnl: float


@dataclass(frozen=True)
class AccountUpdate:
    update_time_ms: int
    wallet: float
    cross_wallet: float
    unreal_total: float
    positions: Dict[str, AccountPos]


@dataclass
class PositionEpisode:
    symbol: str
    side: str  # long/short
    start_ms: int
    end_ms: int
    start_qty: float
    max_abs_qty: float
    last_qty: float
    avg_entry_price: float
    exit_mark_price: float
    exit_unrealized_pnl: float
    start_mark_price: float
    start_unrealized_pnl: float

    open_dec: Optional[DecOpen] = None
    close_dec: Optional[DecClose] = None
    pending_stored: Optional[PendingBracketsStored] = None
    pending_cleared: Optional[PendingBracketsCleared] = None

    entry_bar: Optional[Dict[str, Any]] = None
    exit_bar: Optional[Dict[str, Any]] = None
    post_exit_bars: List[Dict[str, Any]] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.post_exit_bars is None:
            self.post_exit_bars = []


def parse_dec_opens(events: Sequence[Dict[str, Any]]) -> List[DecOpen]:
    out: List[DecOpen] = []
    for e in events:
        if e.get("op") != "DEC" or e.get("verb") != "OPEN":
            continue
        pld = e.get("pld") if isinstance(e.get("pld"), dict) else {}
        ts_ms = _safe_int(e.get("ts") or e.get("timestamp")) or 0
        symbol = str(pld.get("symbol") or "")
        if not symbol:
            continue
        data_ref = e.get("data_ref") if isinstance(e.get("data_ref"), list) else []
        out.append(
            DecOpen(
                ts_ms=ts_ms,
                rid=str(e.get("rid") or ""),
                symbol=symbol,
                side=str(pld.get("side") or ""),
                order_type=str(pld.get("order_type") or ""),
                qty=_safe_float(pld.get("qty")),
                price=_safe_float(pld.get("price")),
                stop_price=_safe_float(pld.get("stop_price")),
                target_price=_safe_float(pld.get("target_price")),
                valid_for_ms=_safe_int(pld.get("valid_for_ms")),
                data_ref=[str(x) for x in data_ref],
            )
        )
    out.sort(key=lambda x: x.ts_ms)
    return out


def parse_dec_closes(events: Sequence[Dict[str, Any]]) -> List[DecClose]:
    out: List[DecClose] = []
    for e in events:
        if e.get("op") != "DEC" or e.get("verb") != "CLOSE":
            continue
        pld = e.get("pld") if isinstance(e.get("pld"), dict) else {}
        ts_ms = _safe_int(e.get("ts") or e.get("timestamp")) or 0
        symbol = str(pld.get("symbol") or "")
        if not symbol:
            continue
        data_ref = e.get("data_ref") if isinstance(e.get("data_ref"), list) else []
        out.append(
            DecClose(
                ts_ms=ts_ms,
                rid=str(e.get("rid") or ""),
                symbol=symbol,
                reason=str(pld.get("reason")) if pld.get("reason") is not None else None,
                trigger=str(pld.get("trigger")) if pld.get("trigger") is not None else None,
                why=str(e.get("why")) if e.get("why") is not None else None,
                data_ref=[str(x) for x in data_ref],
            )
        )
    out.sort(key=lambda x: x.ts_ms)
    return out


def parse_pending_brackets(
    events: Sequence[Dict[str, Any]],
) -> Tuple[List[PendingBracketsStored], List[PendingBracketsCleared]]:
    stored: List[PendingBracketsStored] = []
    cleared: List[PendingBracketsCleared] = []
    for e in events:
        if e.get("op") != "EVT":
            continue
        verb = e.get("verb")
        pld = e.get("pld") if isinstance(e.get("pld"), dict) else {}
        ts_ms = _safe_int(e.get("ts") or pld.get("ts_ms") or e.get("timestamp")) or 0
        if verb == "PENDING_BRACKETS_STORED":
            entry_order_id = str(pld.get("entry_order_id") or "")
            symbol = str(pld.get("symbol") or "")
            side = str(pld.get("side") or "")
            if not entry_order_id or not symbol or not side:
                continue
            stored.append(
                PendingBracketsStored(
                    ts_ms=ts_ms,
                    rid=str(e.get("rid") or pld.get("rid") or ""),
                    entry_order_id=entry_order_id,
                    symbol=symbol,
                    side=side,
                    qty=_safe_float(pld.get("qty")),
                    sl=_safe_float(pld.get("sl")),
                    tp=_safe_float(pld.get("tp")),
                )
            )
        elif verb == "PENDING_BRACKETS_CLEARED":
            entry_order_id = str(pld.get("entry_order_id") or "")
            symbol = str(pld.get("symbol") or "")
            reason = str(pld.get("reason") or "")
            if not entry_order_id or not symbol or not reason:
                continue
            cleared.append(
                PendingBracketsCleared(
                    ts_ms=ts_ms,
                    rid=str(e.get("rid") or ""),
                    entry_order_id=entry_order_id,
                    symbol=symbol,
                    reason=reason,
                )
            )
    stored.sort(key=lambda x: x.ts_ms)
    cleared.sort(key=lambda x: x.ts_ms)
    return stored, cleared


def parse_account_updates(events: Sequence[Dict[str, Any]]) -> List[AccountUpdate]:
    out: List[AccountUpdate] = []
    for e in events:
        if e.get("verb") != "ACCOUNT_UPDATE_RECEIVED":
            continue
        pld = e.get("pld") if isinstance(e.get("pld"), dict) else {}
        ut = _safe_int(pld.get("updateTime"))
        if not ut:
            continue
        wallet = _safe_float(pld.get("totalWalletBalance")) or 0.0
        cross = _safe_float(pld.get("totalCrossWalletBalance")) or 0.0
        unreal_total = _safe_float(pld.get("totalUnrealizedProfit")) or 0.0

        positions: Dict[str, AccountPos] = {}
        for pos in pld.get("positions") or []:
            if not isinstance(pos, dict):
                continue
            sym = str(pos.get("symbol") or "")
            qty = _safe_float(pos.get("positionAmt"))
            entry = _safe_float(pos.get("entryPrice"))
            mark = _safe_float(pos.get("markPrice"))
            unreal = _safe_float(pos.get("unRealizedProfit"))
            if not sym or qty is None or entry is None or mark is None or unreal is None:
                continue
            positions[sym] = AccountPos(sym, qty, entry, mark, unreal)

        out.append(AccountUpdate(ut, wallet, cross, unreal_total, positions))
    out.sort(key=lambda x: x.update_time_ms)
    return out


def build_position_episodes(
    updates: List[AccountUpdate], *, qty_threshold: float = 1e-9
) -> Tuple[List[PositionEpisode], Dict[str, AccountPos]]:
    open_eps: Dict[str, Dict[str, Any]] = {}
    closed: List[PositionEpisode] = []

    for u in updates:
        cur_syms = set(u.positions.keys())
        prev_syms = set(open_eps.keys())

        for sym in sorted(prev_syms - cur_syms):
            ep = open_eps.pop(sym)
            last: AccountPos = ep["last_pos"]
            closed.append(
                PositionEpisode(
                    symbol=sym,
                    side=ep["side"],
                    start_ms=ep["start_ms"],
                    end_ms=u.update_time_ms,
                    start_qty=ep["start_pos"].qty,
                    max_abs_qty=ep["max_abs_qty"],
                    last_qty=last.qty,
                    avg_entry_price=last.entry_price,
                    exit_mark_price=last.mark_price,
                    exit_unrealized_pnl=last.unrealized_pnl,
                    start_mark_price=ep["start_pos"].mark_price,
                    start_unrealized_pnl=ep["start_pos"].unrealized_pnl,
                )
            )

        for sym in sorted(prev_syms & cur_syms):
            pos = u.positions[sym]
            if abs(pos.qty) <= qty_threshold:
                ep = open_eps.pop(sym)
                last: AccountPos = ep["last_pos"]
                closed.append(
                    PositionEpisode(
                        symbol=sym,
                        side=ep["side"],
                        start_ms=ep["start_ms"],
                        end_ms=u.update_time_ms,
                        start_qty=ep["start_pos"].qty,
                        max_abs_qty=ep["max_abs_qty"],
                        last_qty=last.qty,
                        avg_entry_price=last.entry_price,
                        exit_mark_price=last.mark_price,
                        exit_unrealized_pnl=last.unrealized_pnl,
                        start_mark_price=ep["start_pos"].mark_price,
                        start_unrealized_pnl=ep["start_pos"].unrealized_pnl,
                    )
                )
                continue

            ep = open_eps[sym]
            prev_qty: float = ep["last_pos"].qty
            if prev_qty != 0 and pos.qty != 0 and (prev_qty * pos.qty) < 0:
                last: AccountPos = ep["last_pos"]
                closed.append(
                    PositionEpisode(
                        symbol=sym,
                        side=ep["side"],
                        start_ms=ep["start_ms"],
                        end_ms=u.update_time_ms,
                        start_qty=ep["start_pos"].qty,
                        max_abs_qty=ep["max_abs_qty"],
                        last_qty=last.qty,
                        avg_entry_price=last.entry_price,
                        exit_mark_price=last.mark_price,
                        exit_unrealized_pnl=last.unrealized_pnl,
                        start_mark_price=ep["start_pos"].mark_price,
                        start_unrealized_pnl=ep["start_pos"].unrealized_pnl,
                    )
                )
                open_eps.pop(sym, None)
                open_eps[sym] = {
                    "start_ms": u.update_time_ms,
                    "side": _dir_from_qty(pos.qty),
                    "start_pos": pos,
                    "last_pos": pos,
                    "max_abs_qty": abs(pos.qty),
                }
                continue

            ep["last_pos"] = pos
            ep["max_abs_qty"] = max(float(ep["max_abs_qty"]), abs(pos.qty))

        for sym in sorted(cur_syms - prev_syms):
            pos = u.positions[sym]
            if abs(pos.qty) <= qty_threshold:
                continue
            open_eps[sym] = {
                "start_ms": u.update_time_ms,
                "side": _dir_from_qty(pos.qty),
                "start_pos": pos,
                "last_pos": pos,
                "max_abs_qty": abs(pos.qty),
            }

    last_open_positions = {sym: ep["last_pos"] for sym, ep in open_eps.items()}
    closed.sort(key=lambda e: e.start_ms)
    return closed, last_open_positions


def load_recorder_series(recorder_dir: Path, symbol: str, tf_sec: int) -> Tuple[List[int], List[Dict[str, Any]]]:
    files = sorted([p for p in recorder_dir.glob(f"**/{symbol}_{tf_sec}.csv") if p.is_file()])
    rows: List[Dict[str, Any]] = []
    for p in files:
        with p.open("r", encoding="utf-8", errors="replace", newline="") as f:
            r = csv.DictReader(f)
            for row in r:
                ts = _safe_int(row.get("timestamp"))
                if ts is None:
                    continue
                if str(row.get("symbol") or symbol) != symbol:
                    continue
                rows.append(row)

    rows.sort(key=lambda x: int(x.get("timestamp") or 0))
    dedup: Dict[int, Dict[str, Any]] = {}
    for row in rows:
        dedup[int(row["timestamp"])] = row
    ts_list = sorted(dedup.keys())
    row_list = [dedup[t] for t in ts_list]
    return ts_list, row_list


def recorder_bar_at(ts_list: List[int], rows: List[Dict[str, Any]], ts_ms: int) -> Optional[Dict[str, Any]]:
    if not ts_list:
        return None
    if ts_ms < ts_list[0]:
        return None
    lo, hi = 0, len(ts_list) - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        if ts_list[mid] <= ts_ms:
            lo = mid + 1
        else:
            hi = mid - 1
    idx = max(0, lo - 1)
    return rows[idx]


def recorder_next_bars(ts_list: List[int], rows: List[Dict[str, Any]], base_bar_ts: int, n: int) -> List[Dict[str, Any]]:
    if not ts_list or n <= 0:
        return []
    lo, hi = 0, len(ts_list) - 1
    if base_bar_ts < ts_list[0]:
        return rows[: min(n, len(rows))]
    while lo <= hi:
        mid = (lo + hi) // 2
        if ts_list[mid] <= base_bar_ts:
            lo = mid + 1
        else:
            hi = mid - 1
    base_idx = max(0, lo - 1)
    start = base_idx + 1
    end = min(len(rows), start + n)
    return rows[start:end]


def _pick_close_dec(dec_closes: List[DecClose], symbol: str, end_ms: int, window_ms: int = 45_000) -> Optional[DecClose]:
    best: Optional[DecClose] = None
    lo = end_ms - window_ms
    hi = end_ms + window_ms
    for d in dec_closes:
        if d.symbol != symbol:
            continue
        if d.ts_ms < lo or d.ts_ms > hi:
            continue
        if best is None or d.ts_ms > best.ts_ms:
            best = d
    return best


def _pick_open_dec(dec_opens: List[DecOpen], symbol: str, side: str, start_ms: int, lookback_ms: int = 1_800_000) -> Optional[DecOpen]:
    best: Optional[DecOpen] = None
    lo = start_ms - lookback_ms
    for d in dec_opens:
        if d.symbol != symbol:
            continue
        if side == "long" and d.side != "BUY":
            continue
        if side == "short" and d.side != "SELL":
            continue
        if d.ts_ms > start_ms or d.ts_ms < lo:
            continue
        if best is None or d.ts_ms > best.ts_ms:
            best = d
    return best


def attach_correlations(
    episodes: List[PositionEpisode],
    *,
    dec_opens: List[DecOpen],
    dec_closes: List[DecClose],
    pending_stored: List[PendingBracketsStored],
    pending_cleared: List[PendingBracketsCleared],
) -> None:
    stored_by_order = {s.entry_order_id: s for s in pending_stored}
    cleared_sorted = sorted(pending_cleared, key=lambda x: x.ts_ms)

    for ep in episodes:
        ep.close_dec = _pick_close_dec(dec_closes, ep.symbol, ep.end_ms)

        candidate_cleared: Optional[PendingBracketsCleared] = None
        for c in cleared_sorted:
            if c.symbol != ep.symbol:
                continue
            if c.ts_ms < ep.start_ms - 60_000:
                continue
            if c.ts_ms > ep.end_ms + 60_000:
                continue
            if candidate_cleared is None or c.ts_ms < candidate_cleared.ts_ms:
                candidate_cleared = c

        if candidate_cleared:
            ep.pending_cleared = candidate_cleared
            ep.pending_stored = stored_by_order.get(candidate_cleared.entry_order_id)
            if ep.pending_stored:
                rid = ep.pending_stored.rid
                for d in dec_opens:
                    if d.rid == rid:
                        ep.open_dec = d
                        break

        if ep.open_dec is None:
            ep.open_dec = _pick_open_dec(dec_opens, ep.symbol, ep.side, ep.start_ms)


def attach_recorder_context(
    episodes: List[PositionEpisode],
    *,
    recorder_dir: Path,
    tf_sec: int,
    post_bars: int,
) -> None:
    cache: Dict[Tuple[str, int], Tuple[List[int], List[Dict[str, Any]]]] = {}

    def get_series(sym: str) -> Tuple[List[int], List[Dict[str, Any]]]:
        key = (sym, tf_sec)
        if key in cache:
            return cache[key]
        ts_list, rows = load_recorder_series(recorder_dir, sym, tf_sec)
        cache[key] = (ts_list, rows)
        return ts_list, rows

    for ep in episodes:
        ts_list, rows = get_series(ep.symbol)
        entry_anchor = ep.open_dec.ts_ms if ep.open_dec else ep.start_ms
        exit_anchor = ep.close_dec.ts_ms if ep.close_dec else ep.end_ms
        ep.entry_bar = recorder_bar_at(ts_list, rows, entry_anchor)
        ep.exit_bar = recorder_bar_at(ts_list, rows, exit_anchor)
        if ep.exit_bar:
            base = int(ep.exit_bar.get("timestamp") or 0)
            ep.post_exit_bars = recorder_next_bars(ts_list, rows, base, post_bars)
        else:
            ep.post_exit_bars = []


def _bar_dt(row: Optional[Dict[str, Any]]) -> str:
    if not row:
        return "n/a"
    # Recorder datetime is local-time encoded; keep it as-is.
    return str(row.get("datetime") or "n/a")


def _bar_num(row: Optional[Dict[str, Any]], key: str) -> Optional[float]:
    if not row:
        return None
    return _safe_float(row.get(key))


def _classify_close(ep: PositionEpisode, *, sl: Optional[float], tp: Optional[float]) -> str:
    if ep.close_dec:
        tags: List[str] = []
        if ep.close_dec.why:
            tags.append(str(ep.close_dec.why))
        if ep.close_dec.reason:
            tags.append(f"reason={ep.close_dec.reason}")
        if ep.close_dec.trigger:
            tags.append(f"trigger={ep.close_dec.trigger}")
        if ep.close_dec.data_ref:
            tags.append("ref=" + ",".join(ep.close_dec.data_ref[:2]))
        return "DEC:CLOSE " + " | ".join(tags)

    # Heuristics when there is no DEC:CLOSE:
    # 1) Prefer exit mark price vs SL/TP thresholds (closest to the actual trigger).
    # 2) Fallback to bar high/low touch.
    if sl is not None:
        if ep.side == "long" and ep.exit_mark_price <= sl:
            return "BRACKET:SL (exit_mark)"
        if ep.side == "short" and ep.exit_mark_price >= sl:
            return "BRACKET:SL (exit_mark)"
    if tp is not None:
        if ep.side == "long" and ep.exit_mark_price >= tp:
            return "BRACKET:TP (exit_mark)"
        if ep.side == "short" and ep.exit_mark_price <= tp:
            return "BRACKET:TP (exit_mark)"

    hi = _bar_num(ep.exit_bar, "high")
    lo = _bar_num(ep.exit_bar, "low")
    if sl is not None and hi is not None and lo is not None:
        if ep.side == "long" and lo <= sl:
            return "BRACKET:SL (heuristic)"
        if ep.side == "short" and hi >= sl:
            return "BRACKET:SL (heuristic)"
    if tp is not None and hi is not None and lo is not None:
        if ep.side == "long" and hi >= tp:
            return "BRACKET:TP (heuristic)"
        if ep.side == "short" and lo <= tp:
            return "BRACKET:TP (heuristic)"

    # If we only have the last mark snapshot before disappearance, we can miss a brief SL/TP touch.
    # Use a small proximity band as a final hint.
    near_bps = 10.0
    if sl is not None and ep.exit_unrealized_pnl < 0:
        if abs(ep.exit_mark_price - sl) <= abs(sl) * (near_bps / 10000.0):
            return "BRACKET:SL (near_exit_mark)"
    if tp is not None and ep.exit_unrealized_pnl > 0:
        if abs(ep.exit_mark_price - tp) <= abs(tp) * (near_bps / 10000.0):
            return "BRACKET:TP (near_exit_mark)"
    return "UNKNOWN (no DEC:CLOSE)"


def render_report(
    *,
    out_path: Path,
    wal_files: List[Path],
    registry_pairs: set[Tuple[str, str]],
    events: List[Dict[str, Any]],
    updates: List[AccountUpdate],
    episodes: List[PositionEpisode],
    last_open_positions: Dict[str, AccountPos],
    tf_sec: int,
    post_bars: int,
) -> None:
    now_utc = dt.datetime.now(tz=UTC).strftime("%Y-%m-%d %H:%M:%SZ")

    def post_metrics(ep: PositionEpisode, tp: Optional[float]) -> Tuple[Optional[float], Optional[float], Optional[float], Optional[bool]]:
        if not ep.post_exit_bars:
            return None, None, None, None

        highs = [_safe_float(b.get("high")) for b in ep.post_exit_bars]
        lows = [_safe_float(b.get("low")) for b in ep.post_exit_bars]
        highs = [h for h in highs if h is not None]
        lows = [l for l in lows if l is not None]
        if not highs or not lows:
            return None, None, None, None

        post_best = max(highs) if ep.side == "long" else min(lows)
        post_tp = None
        if tp is not None:
            post_tp = (post_best >= tp) if ep.side == "long" else (post_best <= tp)

        post_move = (post_best - ep.exit_mark_price) if ep.side == "long" else (ep.exit_mark_price - post_best)
        post_pnl = post_move * abs(ep.last_qty)
        return post_best, post_move, post_pnl, post_tp

    seen_pairs = Counter()
    unknown_pairs = Counter()
    for e in events:
        op = e.get("op")
        verb = e.get("verb")
        if not op or not verb:
            continue
        k = (str(op), str(verb))
        seen_pairs[k] += 1
        if registry_pairs and k not in registry_pairs:
            unknown_pairs[k] += 1

    start = updates[0] if updates else None
    end = updates[-1] if updates else None

    by_symbol: Dict[str, List[PositionEpisode]] = {}
    for ep in episodes:
        by_symbol.setdefault(ep.symbol, []).append(ep)

    # Entry micro alignment (OBI/TFI signs)
    def micro_align(dir_side: str, v: Optional[float]) -> Optional[bool]:
        if v is None:
            return None
        return (v > 0) if dir_side == "long" else (v < 0)

    obi_total = obi_ok = 0
    tfi_total = tfi_ok = 0
    for ep in episodes:
        obi = _safe_float((ep.entry_bar or {}).get("feat_obi"))
        tfi = _safe_float((ep.entry_bar or {}).get("feat_tfi"))
        ok = micro_align(ep.side, obi)
        if ok is not None:
            obi_total += 1
            obi_ok += int(ok)
        ok = micro_align(ep.side, tfi)
        if ok is not None:
            tfi_total += 1
            tfi_ok += int(ok)

    tp_hit_soon = 0
    favorable_move = 0
    for ep in episodes:
        tp = ep.pending_stored.tp if ep.pending_stored else (ep.open_dec.target_price if ep.open_dec else None)
        if not ep.post_exit_bars:
            continue
        best, _, _, post_tp = post_metrics(ep, tp)
        if best is None:
            continue
        if (best > ep.exit_mark_price) if ep.side == "long" else (best < ep.exit_mark_price):
            favorable_move += 1
        if post_tp:
            tp_hit_soon += 1

    # Intent filtering stats
    intent_proposed = 0
    intent_rejected = 0
    proposed_by_instr = Counter()
    rejected_by_sym = Counter()
    reject_reason_code = Counter()
    reject_stage = Counter()
    for e in events:
        if e.get("op") != "EVT":
            continue
        verb = e.get("verb")
        pld = e.get("pld") if isinstance(e.get("pld"), dict) else {}
        if verb == "TRADE_INTENT_PROPOSED":
            intent_proposed += 1
            instr = pld.get("instrument") or pld.get("symbol")
            if instr:
                proposed_by_instr[str(instr)] += 1
        elif verb == "TRADE_INTENT_REJECTED":
            intent_rejected += 1
            sym = pld.get("symbol")
            if sym:
                rejected_by_sym[str(sym)] += 1
            rc = pld.get("reason_code")
            if rc:
                reject_reason_code[str(rc)] += 1
            st = pld.get("stage")
            if st:
                reject_stage[str(st)] += 1

    # Close attribution stats
    close_kinds = Counter()
    dec_close_why = Counter()
    dec_close_reason = Counter()
    dec_close_data_ref = Counter()
    manual_close_tp_soon = 0
    manual_close_total = 0
    premature: List[Tuple[float, PositionEpisode, str, Optional[bool]]] = []
    for ep in episodes:
        sl = ep.pending_stored.sl if ep.pending_stored else (ep.open_dec.stop_price if ep.open_dec else None)
        tp = ep.pending_stored.tp if ep.pending_stored else (ep.open_dec.target_price if ep.open_dec else None)
        cr = _classify_close(ep, sl=sl, tp=tp)

        if cr.startswith("DEC:CLOSE"):
            close_kinds["DEC:CLOSE"] += 1
            manual_close_total += 1
            if ep.close_dec:
                if ep.close_dec.why:
                    dec_close_why[str(ep.close_dec.why)] += 1
                if ep.close_dec.reason:
                    dec_close_reason[str(ep.close_dec.reason)] += 1
                for tag in ep.close_dec.data_ref:
                    dec_close_data_ref[str(tag)] += 1

            _, _, post_pnl, post_tp = post_metrics(ep, tp)
            if post_tp:
                manual_close_tp_soon += 1
            if post_pnl is not None:
                premature.append((post_pnl, ep, cr, post_tp))
        elif cr.startswith("BRACKET:TP"):
            close_kinds["BRACKET:TP"] += 1
        elif cr.startswith("BRACKET:SL"):
            close_kinds["BRACKET:SL"] += 1
        else:
            close_kinds["UNKNOWN"] += 1

    lines: List[str] = []
    lines.append("# Live Trading Deep Dive (WAL + recorder)")
    lines.append("")
    lines.append(f"- Generated (UTC): {now_utc}")
    lines.append(f"- WAL: {', '.join(p.as_posix() for p in wal_files)}")
    lines.append(f"- Recorder TF: {tf_sec}s")
    lines.append(f"- Post-exit bars: {post_bars}")
    lines.append("")

    if start and end:
        lines.append("## Account Summary (ACCOUNT_UPDATE_RECEIVED)")
        lines.append("")
        lines.append(f"- Start: {_fmt_ts_ms(start.update_time_ms)} | wallet={_fmt_money(start.wallet)} | pos={len(start.positions)}")
        lines.append(f"- End:   {_fmt_ts_ms(end.update_time_ms)} | wallet={_fmt_money(end.wallet)} | pos={len(end.positions)}")
        lines.append(f"- Net wallet delta: {_fmt_money(end.wallet - start.wallet)}")
        lines.append("")

    if last_open_positions:
        lines.append("## Open Positions (end of range)")
        lines.append("")
        for sym, pos in sorted(last_open_positions.items()):
            lines.append(
                f"- {sym}: qty={_fmt_f(pos.qty, 6)} entry={_fmt_f(pos.entry_price, 6)} mark={_fmt_f(pos.mark_price, 6)} uPnL={_fmt_money(pos.unrealized_pnl)}"
            )
        lines.append("")

    lines.append("## Trades (position episodes)")
    lines.append("")
    lines.append(f"- Closed episodes: {len(episodes)}")
    lines.append(f"- By symbol: {', '.join(f'{s}={len(v)}' for s, v in sorted(by_symbol.items()))}")
    if obi_total:
        lines.append(f"- Entry OBI alignment: {obi_ok}/{obi_total} ({(100.0 * obi_ok / obi_total):.1f}%)")
    if tfi_total:
        lines.append(f"- Entry TFI alignment: {tfi_ok}/{tfi_total} ({(100.0 * tfi_ok / tfi_total):.1f}%)")
    lines.append(f"- Favorable move within next {post_bars} bars after close: {favorable_move}/{len(episodes)}")
    lines.append(f"- TP hit within next {post_bars} bars after close (heuristic): {tp_hit_soon}/{len(episodes)}")
    lines.append("")

    if intent_proposed or intent_rejected:
        lines.append("## Intent Filtering (TRADE_INTENT_*)")
        lines.append("")
        lines.append(f"- Proposed: {intent_proposed}")
        lines.append(f"- Rejected: {intent_rejected}")
        if proposed_by_instr:
            lines.append(f"- Proposed by instrument: {', '.join(f'{k}={v}' for k, v in proposed_by_instr.most_common(8))}")
        if rejected_by_sym:
            lines.append(f"- Rejected by symbol: {', '.join(f'{k}={v}' for k, v in rejected_by_sym.most_common(8))}")
        if reject_reason_code:
            lines.append("- Top reject reason_code:")
            for k, v in reject_reason_code.most_common(10):
                lines.append(f"  - {k} x {v}")
        if reject_stage:
            lines.append("- Top reject stage:")
            for k, v in reject_stage.most_common(10):
                lines.append(f"  - {k} x {v}")
        lines.append("")

    if close_kinds:
        lines.append("## Close Attribution")
        lines.append("")
        lines.append(f"- By kind: {', '.join(f'{k}={v}' for k, v in close_kinds.most_common())}")
        if dec_close_why:
            lines.append(f"- DEC:CLOSE why: {', '.join(f'{k}={v}' for k, v in dec_close_why.most_common(8))}")
        if dec_close_reason:
            lines.append(f"- DEC:CLOSE reason: {', '.join(f'{k}={v}' for k, v in dec_close_reason.most_common(8))}")
        if dec_close_data_ref:
            lines.append(f"- DEC:CLOSE data_ref top: {', '.join(f'{k}={v}' for k, v in dec_close_data_ref.most_common(8))}")
        lines.append("")

    if premature:
        lines.append(f"## Post-Exit Check (next {post_bars} bars)")
        lines.append("")
        if manual_close_total:
            lines.append(f"- Manual closes with TP reachable within next {post_bars} bars: {manual_close_tp_soon}/{manual_close_total}")
        lines.append("- Top 'premature' candidates (by post-exit best PnL):")
        for post_pnl, ep, cr, post_tp in sorted(premature, key=lambda t: t[0], reverse=True)[:10]:
            tp = ep.pending_stored.tp if ep.pending_stored else (ep.open_dec.target_price if ep.open_dec else None)
            post_tp_s = "n/a" if tp is None or post_tp is None else ("Y" if post_tp else "N")
            lines.append(
                f"  - {ep.symbol} {ep.side} {_fmt_ts_ms(ep.start_ms)} -> {_fmt_ts_ms(ep.end_ms)} | uPnL@Exit~{_fmt_money(ep.exit_unrealized_pnl)} | PostBestPnL~{_fmt_money(post_pnl)} | PostTP={post_tp_s} | {cr[:48]}"
            )
        lines.append("")

    if registry_pairs:
        lines.append("## Registry Coverage (verb_registry_v1.yaml)")
        lines.append("")
        lines.append(f"- Unique (op,verb) seen in WAL: {len(seen_pairs)}")
        lines.append(f"- Unknown (op,verb) not in registry: {len(unknown_pairs)}")
        if unknown_pairs:
            lines.append("- Top unknown pairs:")
            for (op, verb), c in unknown_pairs.most_common(12):
                lines.append(f"  - {op}:{verb} x {c}")
        lines.append("")

    headers = [
        "#",
        "Symbol",
        "Dir",
        "QtyMax",
        "Entry(UTC)",
        "Exit(UTC)",
        "DurMin",
        "EntryPx",
        "ExitMark",
        "uPnL@Exit",
        "SL",
        "TP",
        "CloseReason",
        "EntryBar(local)",
        "ExitBar(local)",
        "PostBest",
        "PostMove",
        "PostPnL",
        "PostTP?",
    ]

    rows: List[List[str]] = []
    for i, ep in enumerate(sorted(episodes, key=lambda x: x.start_ms), start=1):
        sl = ep.pending_stored.sl if ep.pending_stored else (ep.open_dec.stop_price if ep.open_dec else None)
        tp = ep.pending_stored.tp if ep.pending_stored else (ep.open_dec.target_price if ep.open_dec else None)
        close_reason = _classify_close(ep, sl=sl, tp=tp)

        post_best, post_move, post_pnl, post_tp_bool = post_metrics(ep, tp)
        post_tp = ""
        if tp is not None and post_tp_bool is not None:
            post_tp = "Y" if post_tp_bool else "N"

        rows.append(
            [
                str(i),
                ep.symbol,
                ep.side,
                _fmt_f(ep.max_abs_qty, 2),
                _fmt_ts_ms(ep.start_ms),
                _fmt_ts_ms(ep.end_ms),
                _fmt_f((ep.end_ms - ep.start_ms) / 60000.0, 1),
                _fmt_f(ep.avg_entry_price, 6),
                _fmt_f(ep.exit_mark_price, 6),
                _fmt_money(ep.exit_unrealized_pnl),
                _fmt_f(sl, 6) if sl is not None else "n/a",
                _fmt_f(tp, 6) if tp is not None else "n/a",
                close_reason,
                _bar_dt(ep.entry_bar),
                _bar_dt(ep.exit_bar),
                _fmt_f(post_best, 6) if post_best is not None else "n/a",
                _fmt_f(post_move, 6) if post_move is not None else "n/a",
                _fmt_money(post_pnl) if post_pnl is not None else "n/a",
                post_tp or "n/a",
            ]
        )

    def ascii_table(h: List[str], rws: List[List[str]]) -> List[str]:
        widths = [len(x) for x in h]
        for r in rws:
            for j, cell in enumerate(r):
                widths[j] = max(widths[j], len(cell))
        caps = {"CloseReason": 52, "EntryBar(local)": 23, "ExitBar(local)": 23, "Signal": 46}
        for j, name in enumerate(h):
            if name in caps:
                widths[j] = min(widths[j], caps[name])

        def cut(s: str, w: int) -> str:
            if len(s) <= w:
                return s
            if w <= 3:
                return s[:w]
            return s[: w - 3] + "..."

        hline = "+" + "+".join("-" * (w + 2) for w in widths) + "+"
        out: List[str] = []
        out.append("```")
        out.append(hline)
        out.append("| " + " | ".join(cut(n, widths[i]).ljust(widths[i]) for i, n in enumerate(h)) + " |")
        out.append(hline)
        for r in rws:
            out.append("| " + " | ".join(cut(str(c), widths[i]).ljust(widths[i]) for i, c in enumerate(r)) + " |")
        out.append(hline)
        out.append("```")
        return out

    lines.extend(ascii_table(headers, rows))
    lines.append("")

    lines.append("## Entry Microstructure (from recorder)")
    lines.append("")

    micro_headers = [
        "#",
        "Symbol",
        "Dir",
        "EntryBar(local)",
        "OBI",
        "TFI",
        "SpreadBps",
        "DeltaPx",
        "DepthImb",
        "LargeTradeImb",
        "VolState",
        "VolSpike",
        "VolZ",
        "Signal",
        "Regime",
    ]
    micro_rows: List[List[str]] = []

    def pick_signal(dec: Optional[DecOpen]) -> str:
        if not dec or not dec.data_ref:
            return "n/a"
        for s in dec.data_ref:
            if isinstance(s, str) and (s.startswith("flip:") or s.startswith("hold:")):
                return s
        return str(dec.data_ref[0])

    def pick_regime(dec: Optional[DecOpen]) -> str:
        if not dec or not dec.data_ref:
            return "n/a"
        for s in dec.data_ref:
            if isinstance(s, str) and s.startswith("tpsl:regime="):
                tail = s.split("tpsl:regime=", 1)[1]
                return tail.split()[0] if tail else "n/a"
        return "n/a"

    for i, ep in enumerate(sorted(episodes, key=lambda x: x.start_ms), start=1):
        eb = ep.entry_bar or {}
        micro_rows.append(
            [
                str(i),
                ep.symbol,
                ep.side,
                _bar_dt(ep.entry_bar),
                _fmt_f(_safe_float(eb.get("feat_obi")), 4),
                _fmt_f(_safe_float(eb.get("feat_tfi")), 4),
                _fmt_f(_safe_float(eb.get("feat_spread_bps")), 2),
                _fmt_f(_safe_float(eb.get("feat_delta_price")), 6),
                _fmt_f(_safe_float(eb.get("feat_depth_imbalance")), 4),
                _fmt_f(_safe_float(eb.get("feat_large_trade_imbalance")), 4),
                _fmt_f(_safe_float(eb.get("feat_volatility_state")), 4),
                _fmt_f(_safe_float(eb.get("feat_volume_spike")), 4),
                _fmt_f(_safe_float(eb.get("feat_volume_zscore")), 4),
                pick_signal(ep.open_dec),
                pick_regime(ep.open_dec),
            ]
        )

    lines.extend(ascii_table(micro_headers, micro_rows))
    lines.append("")

    lines.append("## Loss Leaderboard (by uPnL@Exit estimate)")
    lines.append("")
    ranked = sorted(episodes, key=lambda e: e.exit_unrealized_pnl)
    for ep in ranked[: min(10, len(ranked))]:
        lines.append(
            f"- {ep.symbol} {ep.side} {_fmt_ts_ms(ep.start_ms)} -> {_fmt_ts_ms(ep.end_ms)} | uPnL@Exit~{_fmt_money(ep.exit_unrealized_pnl)} | entry={_fmt_f(ep.avg_entry_price,6)} exitMark={_fmt_f(ep.exit_mark_price,6)}"
        )
    lines.append("")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--wal-dir", type=Path, default=Path("ops/wal"))
    ap.add_argument("--wal", type=Path, action="append", default=None)
    ap.add_argument("--registry", type=Path, default=Path("apps/reference/dictionaries/verb_registry_v1.yaml"))
    ap.add_argument("--recorder-dir", type=Path, default=Path("data/recorder"))
    ap.add_argument("--tf-sec", type=int, default=300)
    ap.add_argument("--post-bars", type=int, default=3)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--qty-threshold", type=float, default=1e-9)
    args = ap.parse_args()

    wal_files = iter_wal_files(args.wal_dir, list(args.wal) if args.wal else None)
    if not wal_files:
        print("No WAL files found.")
        return 2

    registry_pairs = load_verb_registry(args.registry)
    events = list(iter_wal_events(wal_files))

    updates = parse_account_updates(events)
    if not updates:
        print("No ACCOUNT_UPDATE_RECEIVED events found in WAL.")
        return 2

    episodes, last_open_positions = build_position_episodes(updates, qty_threshold=float(args.qty_threshold))
    dec_opens = parse_dec_opens(events)
    dec_closes = parse_dec_closes(events)
    pending_stored, pending_cleared = parse_pending_brackets(events)

    attach_correlations(
        episodes,
        dec_opens=dec_opens,
        dec_closes=dec_closes,
        pending_stored=pending_stored,
        pending_cleared=pending_cleared,
    )
    attach_recorder_context(
        episodes,
        recorder_dir=args.recorder_dir,
        tf_sec=int(args.tf_sec),
        post_bars=int(args.post_bars),
    )

    out_path = args.out
    if out_path is None:
        out_path = Path("reports") / f"live_trade_deep_dive_{wal_files[-1].stem}.md"

    render_report(
        out_path=out_path,
        wal_files=wal_files,
        registry_pairs=registry_pairs,
        events=events,
        updates=updates,
        episodes=episodes,
        last_open_positions=last_open_positions,
        tf_sec=int(args.tf_sec),
        post_bars=int(args.post_bars),
    )

    print(f"Wrote report: {out_path.as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
