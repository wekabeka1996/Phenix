#!/usr/bin/env python3
"""
WAL intent summary + quick virtual PnL from recorder bars.

Reads `ops/wal/*.jsonl` (date-named) and reports:
  - verb histogram
  - TRADE_INTENT_PROPOSED counts by strategy/symbol/side
  - TRADE_INTENT_REJECTED counts by reason_code/stage/symbol
  - simple "virtual PnL" for proposed intents using recorder close->close forward returns

Why this exists
---------------
WAL has the *truth* about what DecisionMaking tried to do (proposed/rejected),
but recorder has the *market bars + features*. Joining them lets us:
  - see if our gates are blocking too much,
  - estimate whether proposed intents had edge (even if limit orders didn’t fill),
  - pick calibration targets for weights/thresholds.
"""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd


def _parse_date(s: str) -> date:
    return date.fromisoformat(s)


def _norm_verb(v: Any) -> str:
    if not isinstance(v, str) or not v:
        return ""
    if ":" in v and v.split(":", 1)[0] in {"EVT", "CMD", "DEC", "UPD"}:
        return v.split(":", 1)[1]
    return v


def _iter_wal_files(wal_dir: Path, start: date | None, end: date | None) -> list[Path]:
    files = sorted(wal_dir.glob("*.jsonl"))
    out: list[Path] = []
    for p in files:
        # Expected naming: YYYY-MM-DD.jsonl
        try:
            d = _parse_date(p.stem)
        except ValueError:
            # Unknown naming -> include (best effort)
            out.append(p)
            continue

        if start and d < start:
            continue
        if end and d >= end:
            continue
        out.append(p)
    return out


def _iter_jsonl(paths: Iterable[Path]) -> Iterable[dict[str, Any]]:
    for p in paths:
        try:
            with p.open("r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except Exception:
                        continue
                    if isinstance(obj, dict):
                        yield obj
        except FileNotFoundError:
            continue


def _ts_ms(obj: dict[str, Any]) -> int | None:
    # Prefer payload timestamps when present.
    pld = obj.get("pld")
    if isinstance(pld, dict):
        for k in ("ts_ms", "timestamp", "ts"):
            v = pld.get(k)
            if isinstance(v, (int, float)) and v > 1e12:
                return int(v)
            if isinstance(v, (int, float)) and 1e9 < v < 1e12:
                return int(v * 1000)

    for k in ("ts", "timestamp"):
        v = obj.get(k)
        if isinstance(v, (int, float)) and v > 1e12:
            return int(v)
        if isinstance(v, (int, float)) and 1e9 < v < 1e12:
            return int(v * 1000)
    return None


def _symbol(obj: dict[str, Any]) -> str | None:
    pld = obj.get("pld")
    if isinstance(pld, dict):
        sym = pld.get("symbol") or pld.get("instrument")
        if isinstance(sym, str) and sym:
            return sym
    return None


def _strategy_id(obj: dict[str, Any]) -> str | None:
    pld = obj.get("pld")
    if isinstance(pld, dict):
        for k in ("strategy", "strategy_id"):
            v = pld.get(k)
            if isinstance(v, str) and v:
                return v
    return None


def _side(obj: dict[str, Any]) -> str | None:
    pld = obj.get("pld")
    if isinstance(pld, dict):
        v = pld.get("side")
        if isinstance(v, str) and v:
            return v.upper()
    return None


@dataclass(frozen=True)
class PriceIndex:
    ts: np.ndarray  # int64 ms
    close: np.ndarray  # float


def _load_recorder_index(*, recorder_dir: Path, start: date | None, end: date | None, symbols: set[str], tf_sec: int) -> dict[str, PriceIndex]:
    files: list[Path] = []
    for day_dir in sorted([p for p in recorder_dir.iterdir() if p.is_dir()]):
        try:
            d = _parse_date(day_dir.name)
        except ValueError:
            continue
        if start and d < start:
            continue
        if end and d >= end:
            continue
        for sym in symbols:
            p = day_dir / f"{sym}_{tf_sec}.csv"
            if p.exists():
                files.append(p)

    if not files:
        return {}

    frames = []
    for p in files:
        df = pd.read_csv(p, usecols=["timestamp", "symbol", "close"])
        frames.append(df)
    df_all = pd.concat(frames, ignore_index=True)
    df_all["timestamp"] = pd.to_numeric(df_all["timestamp"], errors="coerce").astype("Int64")
    df_all["close"] = pd.to_numeric(df_all["close"], errors="coerce").astype(float)
    df_all = df_all.dropna(subset=["timestamp", "close"])
    df_all["timestamp"] = df_all["timestamp"].astype("int64")

    out: dict[str, PriceIndex] = {}
    for sym, g in df_all.groupby("symbol", sort=False):
        g = g.sort_values("timestamp", kind="mergesort")
        out[str(sym)] = PriceIndex(ts=g["timestamp"].to_numpy(dtype="int64"), close=g["close"].to_numpy(dtype=float))
    return out


def _nearest_index(ts_arr: np.ndarray, t: int) -> int:
    # First index with ts >= t
    i = int(np.searchsorted(ts_arr, t, side="left"))
    if i <= 0:
        return 0
    if i >= ts_arr.size:
        return int(ts_arr.size - 1)
    # Pick closer between i-1 and i
    prev = ts_arr[i - 1]
    nxt = ts_arr[i]
    return (i - 1) if abs(t - prev) <= abs(nxt - t) else i


def main() -> int:
    ap = argparse.ArgumentParser(description="Summarize WAL intents and estimate virtual PnL from recorder bars")
    ap.add_argument("--wal-dir", default="ops/wal", help="WAL directory with *.jsonl")
    ap.add_argument("--recorder-dir", default="data/recorder", help="Recorder dir with daily subfolders")
    ap.add_argument("--start", type=_parse_date, default=None, help="Start date inclusive (YYYY-MM-DD)")
    ap.add_argument("--end", type=_parse_date, default=None, help="End date exclusive (YYYY-MM-DD)")
    ap.add_argument("--symbols", nargs="*", default=None, help="Symbols filter (default: all encountered)")
    ap.add_argument("--tf-sec", type=int, default=300, help="Recorder timeframe sec for price join")
    ap.add_argument("--horizon-bars", type=int, default=1, help="Forward horizon in bars for virtual PnL")
    ap.add_argument("--tolerance-ms", type=int, default=None, help="Max allowed ts distance when joining to recorder (default: tf_sec*1000)")
    args = ap.parse_args()

    wal_dir = Path(args.wal_dir)
    if not wal_dir.exists():
        raise SystemExit(f"WAL dir not found: {wal_dir}")

    wal_files = _iter_wal_files(wal_dir, args.start, args.end)
    if not wal_files:
        raise SystemExit("No WAL files found for the requested date window.")

    verbs = Counter()
    proposed = 0
    rejected = 0
    proposed_by = Counter()
    rejected_by = Counter()
    rejected_stage = Counter()
    rejected_symbol = Counter()

    # Collect intents first (so we can infer symbols if not provided)
    intents: list[tuple[int, str, str, str]] = []  # (ts_ms, symbol, strategy, side)
    for obj in _iter_jsonl(wal_files):
        verb = _norm_verb(obj.get("verb"))
        if verb:
            verbs[verb] += 1

        if verb == "TRADE_INTENT_PROPOSED":
            proposed += 1
            sym = _symbol(obj) or ""
            strat = _strategy_id(obj) or "unknown"
            side = _side(obj) or "UNKNOWN"
            proposed_by[(strat, sym, side)] += 1
            t = _ts_ms(obj)
            if t and sym:
                intents.append((t, sym, strat, side))

        elif verb == "TRADE_INTENT_REJECTED":
            rejected += 1
            pld = obj.get("pld") if isinstance(obj.get("pld"), dict) else {}
            code = str(pld.get("reason_code") or "UNKNOWN")
            stage = str(pld.get("stage") or "UNKNOWN")
            sym = str(pld.get("symbol") or pld.get("instrument") or "UNKNOWN")
            rejected_by[code] += 1
            rejected_stage[stage] += 1
            rejected_symbol[sym] += 1

    if args.symbols:
        sym_filter = {s.upper() for s in args.symbols}
        intents = [t for t in intents if t[1].upper() in sym_filter]
    else:
        sym_filter = {sym for _, sym, _, _ in intents}

    # Virtual PnL from recorder close->close
    recorder_dir = Path(args.recorder_dir)
    tolerance = int(args.tolerance_ms) if args.tolerance_ms is not None else int(args.tf_sec) * 1000
    prices = _load_recorder_index(recorder_dir=recorder_dir, start=args.start, end=args.end, symbols=set(sym_filter), tf_sec=int(args.tf_sec))

    pnl_bps: list[float] = []
    usable = 0
    horizon = int(args.horizon_bars)
    for t, sym, _, side in intents:
        idx = prices.get(sym)
        if not idx:
            continue
        i0 = _nearest_index(idx.ts, t)
        if abs(int(idx.ts[i0]) - int(t)) > tolerance:
            continue
        i1 = i0 + horizon
        if i1 >= idx.ts.size:
            continue
        p0 = float(idx.close[i0])
        p1 = float(idx.close[i1])
        if p0 <= 0:
            continue
        ret = ((p1 / p0) - 1.0) * 10_000.0
        sgn = 1.0 if side == "BUY" else (-1.0 if side == "SELL" else 0.0)
        pnl_bps.append(sgn * ret)
        usable += 1

    print("\n" + "=" * 80)
    print(f"WAL files: {len(wal_files)}  window=[{args.start or '-inf'} .. {args.end or '+inf'})")
    print(f"Total intents: proposed={proposed} rejected={rejected}")
    print("-" * 80)
    for verb, n in verbs.most_common(12):
        print(f"{verb:28s} {n:8d}")

    print("\nTRADE_INTENT_PROPOSED (top 15 by strategy/symbol/side):")
    for (strat, sym, side), n in proposed_by.most_common(15):
        print(f"  {strat:14s} {sym:10s} {side:6s}  {n:6d}")

    print("\nTRADE_INTENT_REJECTED (top 15 reason_code):")
    for code, n in rejected_by.most_common(15):
        print(f"  {code:24s} {n:8d}")

    print("\nTRADE_INTENT_REJECTED (by stage):")
    for stage, n in rejected_stage.most_common():
        print(f"  {stage:10s} {n:8d}")

    if pnl_bps:
        arr = np.array(pnl_bps, dtype=float)
        mu = float(np.mean(arr))
        sd = float(np.std(arr, ddof=1)) if arr.size > 1 else 0.0
        sr = (mu / sd) * math.sqrt((86_400.0 / float(args.tf_sec)) * 365.0) if sd > 1e-12 else 0.0
        print("\nVirtual PnL (proposed intents, close->close):")
        print(f"  usable={usable}/{len(intents)}  horizon_bars={horizon}  tf_sec={int(args.tf_sec)}  tol_ms={tolerance}")
        print(f"  mean_bps={mu:.4f}  std_bps={sd:.4f}  sharpe~={sr:.2f}  total_bps={float(arr.sum()):.2f}")
    else:
        print("\nVirtual PnL: no usable intents matched to recorder bars (check --tf-sec / --tolerance-ms).")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

