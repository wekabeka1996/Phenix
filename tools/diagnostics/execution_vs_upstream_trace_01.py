#!/usr/bin/env python3
"""
EXECUTION-VS-UPSTREAM-TRACE-01

Goal: decide whether "no orders" is caused by upstream gating (DecisionMaking)
or by execution wiring/adapter issues.

Inputs:
- ops/wal/*.jsonl (WAL stream; mixed schemas supported)
- logs/domain_feature_engineering.log* (for CMD:PROCESS_STRATEGY occurrences)
- logs/domain_decision_making.log* (for human-readable gate reasons)
- logs/domain_regime_detector.log (for start time + basis_tf hint)

Outputs:
- reports/execution_vs_upstream_trace_01.md
- reports/execution_vs_upstream_trace_01_counts.csv
"""

from __future__ import annotations

import argparse
import csv
import glob
import json
import os
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


BAR_TFS = (180, 300, 900)  # 3m/5m/15m


def _iter_lines(paths: list[Path]) -> Iterable[tuple[Path, int, str]]:
    for p in paths:
        try:
            with p.open("r", encoding="utf-8", errors="replace") as f:
                for i, line in enumerate(f, 1):
                    line = line.strip()
                    if line:
                        yield p, i, line
        except FileNotFoundError:
            continue


def _parse_start_ts_ms_from_regime_log(path: Path) -> int | None:
    """
    Parse first timestamp from regime detector log line:
      2026-01-12 21:23:54,595 - ... - INFO - ...
    Returns epoch milliseconds.
    """
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            m = re.match(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3})\b", line)
            if not m:
                continue
            dt = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S,%f")
            return int(dt.timestamp() * 1000)
    return None


def _to_ts_ms(obj: dict[str, Any]) -> int | None:
    """
    Normalize WAL timestamps to epoch-ms.
    Supports multiple schemas:
    - v1: {"ts": 1768262402720, ...}
    - legacy: {"timestamp": 1768262397.3941512, ...} (float seconds)
    - some payloads: {"pld": {"ts_ms": ...}}
    """
    ts = obj.get("ts")
    if isinstance(ts, (int, float)) and ts > 1e12:
        return int(ts)
    if isinstance(ts, (int, float)) and 1e9 < ts < 1e12:
        return int(ts * 1000)

    ts_s = obj.get("timestamp")
    if isinstance(ts_s, (int, float)):
        if ts_s > 1e12:
            return int(ts_s)
        return int(ts_s * 1000)

    pld = obj.get("pld")
    if isinstance(pld, dict):
        ts_ms = pld.get("ts_ms") or pld.get("ts")
        if isinstance(ts_ms, (int, float)) and ts_ms > 1e12:
            return int(ts_ms)
        if isinstance(ts_ms, (int, float)) and 1e9 < ts_ms < 1e12:
            return int(ts_ms * 1000)
    return None


def _get_symbol(obj: dict[str, Any]) -> str | None:
    pld = obj.get("pld")
    if isinstance(pld, dict):
        sym = pld.get("symbol") or pld.get("instrument")
        if isinstance(sym, str) and sym:
            return sym
    sym = obj.get("symbol")
    return sym if isinstance(sym, str) and sym else None


def _iter_jsonl(paths: list[Path]) -> Iterable[dict[str, Any]]:
    for p, _, line in _iter_lines(paths):
        try:
            obj = json.loads(line)
        except Exception:
            continue
        if isinstance(obj, dict):
            yield obj


@dataclass
class SymbolCounts:
    bar_180: int = 0
    bar_300: int = 0
    bar_900: int = 0
    process_strategy: int = 0
    intent_proposed: int = 0
    intent_rejected: int = 0
    open_cmd: int = 0
    order_placed: int = 0
    order_rejected: int = 0


def _load_feature_engineering_process_strategy_counts(paths: list[Path]) -> Counter:
    """
    Count occurrences of CMD:PROCESS_STRATEGY per symbol from FeatureEngineering text logs.
    """
    c = Counter()
    sym_re = re.compile(r"\[(\w+)\].*CMD:PROCESS_STRATEGY")
    for _, _, line in _iter_lines(paths):
        m = sym_re.search(line)
        if m:
            c[m.group(1)] += 1
    return c


def _load_decision_making_gate_reasons(paths: list[Path]) -> Counter:
    """
    Extract top gate reasons from DecisionMaking logs.
    Examples:
      [SOLUSDT] WARMUP_NOT_READY:regime_not_ready ...
      [DOGEUSDT] STRATEGY_SIGNAL_GATEWAY: REJECT - ... ARBITRATION_REJECT:strategy_not_assigned_to_symbol
    """
    c = Counter()

    warmup_re = re.compile(r"\[\w+\]\s+WARMUP_NOT_READY:([^\s]+)")
    arb_re = re.compile(r"ARBITRATION_REJECT:([^\s]+)")
    qos_re = re.compile(r"\bQoS\b.*\bREJECT\b", re.IGNORECASE)

    for _, _, line in _iter_lines(paths):
        m = warmup_re.search(line)
        if m:
            c[f"warmup:{m.group(1)}"] += 1
            continue

        m = arb_re.search(line)
        if m:
            c[f"arbitration:{m.group(1)}"] += 1
            continue

        if qos_re.search(line):
            c["qos:reject"] += 1
    return c


def _scan_wal(
    wal_paths: list[Path],
    start_ts_ms: int | None,
) -> tuple[dict[str, SymbolCounts], Counter, dict[int, int], dict[int, int | None]]:
    """
    Returns:
    - per-symbol counts for the requested verbs
    - TRADE_INTENT_REJECTED reason_code histogram (overall)
    - bar counts by tf_sec (overall)
    - first bar_close_ts by tf_sec (epoch-ms) for BAR_TFS
    """
    by_symbol: dict[str, SymbolCounts] = defaultdict(SymbolCounts)
    reject_reasons = Counter()
    bar_counts_by_tf = Counter()
    first_bar_close_by_tf: dict[int, int | None] = {tf: None for tf in BAR_TFS}

    for obj in _iter_jsonl(wal_paths):
        ts_ms = _to_ts_ms(obj)
        if ts_ms is None:
            continue
        if start_ts_ms is not None and ts_ms < start_ts_ms:
            continue

        verb = obj.get("verb") or obj.get("event_type")
        if not isinstance(verb, str) or not verb:
            continue

        op = obj.get("op")
        if not isinstance(op, str):
            op = ""

        sym = _get_symbol(obj) or "UNKNOWN"
        pld = obj.get("pld") if isinstance(obj.get("pld"), dict) else {}

        # EVT:BAR_CLOSED (3m/5m/15m)
        if verb in ("BAR_CLOSED", "EVT:BAR_CLOSED"):
            tf_sec = pld.get("tf_sec")
            if isinstance(tf_sec, str) and tf_sec.isdigit():
                tf_sec = int(tf_sec)
            if isinstance(tf_sec, int):
                bar_counts_by_tf[tf_sec] += 1
                bar_close_ts = pld.get("bar_close_ts")
                if isinstance(bar_close_ts, int) and tf_sec in first_bar_close_by_tf:
                    prev = first_bar_close_by_tf[tf_sec]
                    if prev is None or bar_close_ts < prev:
                        first_bar_close_by_tf[tf_sec] = bar_close_ts
                if tf_sec == 180:
                    by_symbol[sym].bar_180 += 1
                elif tf_sec == 300:
                    by_symbol[sym].bar_300 += 1
                elif tf_sec == 900:
                    by_symbol[sym].bar_900 += 1
            continue

        # EVT:TRADE_INTENT_PROPOSED
        if verb in ("TRADE_INTENT_PROPOSED", "EVT:TRADE_INTENT_PROPOSED"):
            by_symbol[sym].intent_proposed += 1
            continue

        # EVT:TRADE_INTENT_REJECTED (+ reason_code)
        if verb in ("TRADE_INTENT_REJECTED", "EVT:TRADE_INTENT_REJECTED"):
            by_symbol[sym].intent_rejected += 1
            rc = pld.get("reason_code") or pld.get("nrr_code") or pld.get("reason")
            if isinstance(rc, str) and rc:
                reject_reasons[rc] += 1
            continue

        # CMD:OPEN
        if verb in ("OPEN", "CMD:OPEN") and op.upper() == "CMD":
            by_symbol[sym].open_cmd += 1
            continue

        # EVT:ORDER_* (if present in WAL)
        if verb in ("ORDER_PLACED", "EVT:ORDER_PLACED"):
            by_symbol[sym].order_placed += 1
            continue

        if verb in ("ORDER_REJECTED", "EVT:ORDER_REJECTED"):
            by_symbol[sym].order_rejected += 1
            continue

    return by_symbol, reject_reasons, dict(bar_counts_by_tf), first_bar_close_by_tf


def _fmt_dt(ms: int | None) -> str:
    if ms is None:
        return "n/a"
    return datetime.fromtimestamp(ms / 1000.0).strftime("%Y-%m-%d %H:%M:%S")


def _safe_load_tick_ttl_ms(system_yaml_path: Path) -> int | None:
    """
    Best-effort parse of config/aurora/system.yaml -> system.market_data.tick_ttl_ms.
    Avoid hard dependency on PyYAML (fallback to regex).
    """
    if not system_yaml_path.exists():
        return None

    try:
        import yaml  # type: ignore

        obj = yaml.safe_load(system_yaml_path.read_text(encoding="utf-8"))
        if isinstance(obj, dict):
            sys_cfg = obj.get("system")
            if isinstance(sys_cfg, dict):
                md = sys_cfg.get("market_data")
                if isinstance(md, dict):
                    ttl = md.get("tick_ttl_ms")
                    if isinstance(ttl, int):
                        return ttl
    except Exception:
        pass

    # Fallback: naive regex (assumes single occurrence)
    m = re.search(r"^\s*tick_ttl_ms:\s*(\d+)\s*$", system_yaml_path.read_text(encoding="utf-8", errors="replace"), re.M)
    if m:
        try:
            return int(m.group(1))
        except Exception:
            return None
    return None


def _median(values: list[int]) -> int | None:
    if not values:
        return None
    xs = sorted(values)
    n = len(xs)
    mid = n // 2
    if n % 2 == 1:
        return xs[mid]
    return int((xs[mid - 1] + xs[mid]) / 2)


def _pct(values: list[int], p: float) -> int | None:
    if not values:
        return None
    if p <= 0:
        return min(values)
    if p >= 100:
        return max(values)
    xs = sorted(values)
    k = int(round((p / 100.0) * (len(xs) - 1)))
    return xs[max(0, min(len(xs) - 1, k))]


def _scan_bar_emit_deltas(wal_paths: list[Path], start_ts_ms: int | None) -> dict[int, list[int]]:
    """
    Compute (emit_ts_ms - bar_close_ts) deltas per tf_sec for BAR_CLOSED from WAL.
    """
    deltas: dict[int, list[int]] = defaultdict(list)
    for obj in _iter_jsonl(wal_paths):
        ts_ms = _to_ts_ms(obj)
        if ts_ms is None:
            continue
        if start_ts_ms is not None and ts_ms < start_ts_ms:
            continue
        verb = obj.get("verb") or obj.get("event_type")
        if verb not in ("BAR_CLOSED", "EVT:BAR_CLOSED"):
            continue
        pld = obj.get("pld")
        if not isinstance(pld, dict):
            continue
        tf_sec = pld.get("tf_sec")
        if isinstance(tf_sec, str) and tf_sec.isdigit():
            tf_sec = int(tf_sec)
        if not isinstance(tf_sec, int):
            continue
        bar_close_ts = pld.get("bar_close_ts")
        if not isinstance(bar_close_ts, int):
            continue
        delta = int(ts_ms - bar_close_ts)
        # Only keep plausible positive deltas
        if 0 <= delta <= 60_000:
            deltas[tf_sec].append(delta)
    return deltas


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--wal-glob", default="ops/wal/*.jsonl")
    ap.add_argument("--fe-log-glob", default="logs/domain_feature_engineering.log*")
    ap.add_argument("--dm-log-glob", default="logs/domain_decision_making.log*")
    ap.add_argument("--regime-log", default="logs/domain_regime_detector.log")
    ap.add_argument("--system-yaml", default="config/aurora/system.yaml")
    ap.add_argument("--out-md", default="reports/execution_vs_upstream_trace_01.md")
    ap.add_argument("--out-csv", default="reports/execution_vs_upstream_trace_01_counts.csv")
    args = ap.parse_args()

    wal_paths = [Path(p) for p in sorted(glob.glob(args.wal_glob))]
    fe_paths = [Path(p) for p in sorted(glob.glob(args.fe_log_glob))]
    dm_paths = [Path(p) for p in sorted(glob.glob(args.dm_log_glob))]
    regime_log = Path(args.regime_log)
    system_yaml = Path(args.system_yaml)

    start_ts_ms = _parse_start_ts_ms_from_regime_log(regime_log)
    tick_ttl_ms = _safe_load_tick_ttl_ms(system_yaml)

    wal_counts, reject_reasons, bar_counts_by_tf, first_bar_close_by_tf = _scan_wal(
        wal_paths, start_ts_ms=start_ts_ms
    )
    bar_emit_deltas = _scan_bar_emit_deltas(wal_paths, start_ts_ms=start_ts_ms)
    fe_process_counts = _load_feature_engineering_process_strategy_counts(fe_paths)
    dm_gate_reasons = _load_decision_making_gate_reasons(dm_paths)

    # Merge process_strategy into per-symbol table
    all_symbols = set(wal_counts.keys()) | set(fe_process_counts.keys())
    for sym in all_symbols:
        wal_counts[sym].process_strategy += int(fe_process_counts.get(sym, 0))

    # Build sorted rows
    def key(sym: str) -> tuple[int, str]:
        tot = (
            wal_counts[sym].open_cmd
            + wal_counts[sym].intent_proposed
            + wal_counts[sym].intent_rejected
            + wal_counts[sym].bar_300
        )
        return (-tot, sym)

    rows = [(sym, wal_counts[sym]) for sym in sorted(all_symbols, key=key)]

    # Write CSV
    out_csv = Path(args.out_csv)
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "symbol",
                "BAR_CLOSED_180s",
                "BAR_CLOSED_300s",
                "BAR_CLOSED_900s",
                "CMD_PROCESS_STRATEGY",
                "TRADE_INTENT_PROPOSED",
                "TRADE_INTENT_REJECTED",
                "CMD_OPEN",
                "ORDER_PLACED",
                "ORDER_REJECTED",
            ]
        )
        for sym, c in rows:
            w.writerow(
                [
                    sym,
                    c.bar_180,
                    c.bar_300,
                    c.bar_900,
                    c.process_strategy,
                    c.intent_proposed,
                    c.intent_rejected,
                    c.open_cmd,
                    c.order_placed,
                    c.order_rejected,
                ]
            )

    total_open = sum(c.open_cmd for _, c in rows)
    total_orders = sum(c.order_placed + c.order_rejected for _, c in rows)

    # Determine root cause label (simple heuristic for this task)
    if total_open == 0:
        root_cause = "Upstream gate: DecisionMaking never emitted CMD:OPEN"
    elif total_open > 0 and total_orders == 0:
        root_cause = "Execution path: CMD:OPEN emitted but no ORDER_* observed"
    else:
        root_cause = "Inconclusive: non-zero opens/orders observed"

    out_md = Path(args.out_md)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    md: list[str] = []
    md.append("# EXECUTION-VS-UPSTREAM-TRACE-01")
    md.append("")
    md.append("## Window (derived)")
    md.append(f"- regime log: `{regime_log}` (exists={regime_log.exists()})")
    md.append(f"- start_ts_ms: `{start_ts_ms}` ({_fmt_dt(start_ts_ms)})")
    md.append(f"- wal files: `{len(wal_paths)}` (glob `{args.wal_glob}`)")
    md.append("")
    md.append("## Counts by symbol (all uptime window)")
    md.append(f"- CSV: `{out_csv}`")
    md.append("")
    md.append("| symbol | BAR 180s | BAR 300s | BAR 900s | CMD:PROCESS_STRATEGY | INTENT_PROPOSED | INTENT_REJECTED | CMD:OPEN | ORDER_PLACED | ORDER_REJECTED |")
    md.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for sym, c in rows:
        md.append(
            "| "
            + " | ".join(
                [
                    sym,
                    str(c.bar_180),
                    str(c.bar_300),
                    str(c.bar_900),
                    str(c.process_strategy),
                    str(c.intent_proposed),
                    str(c.intent_rejected),
                    str(c.open_cmd),
                    str(c.order_placed),
                    str(c.order_rejected),
                ]
            )
            + " |"
        )
    md.append("")
    md.append("## BAR_CLOSED totals (WAL)")
    for tf in BAR_TFS:
        md.append(
            f"- tf_sec={tf}: count={bar_counts_by_tf.get(tf, 0)}, first_bar_close_ts={first_bar_close_by_tf.get(tf)} ({_fmt_dt(first_bar_close_by_tf.get(tf))})"
        )
    md.append("")
    md.append("## Basis timeframe + warmup mechanics (code/config)")
    md.append("- basis TF: `config/aurora/regime.yaml:1` (`basis_tf_sec: 300` → 5m)")
    md.append("- bar-only filter: `apps/reference/domains/regime_detector/regime_detector.py:208` (requires `tf_sec == basis_tf_sec`)")
    md.append("- SMA long warmup (\"50 bars\"): `config/aurora/regime.yaml:27` + `apps/reference/domains/regime_detector/regime_detector.py:301`")
    md.append("- ATR baseline warmup (100 bars): `config/aurora/regime.yaml:34` + `apps/reference/domains/regime_detector/regime_detector.py:354`")
    md.append("- full_ready is strict: `apps/reference/domains/regime_detector/regime_detector.py:458` (needs all ready flags and no data_drops)")
    md.append("")
    md.append("## Warmup conclusion (explicit)")
    md.append(
        f"- now: regime warmup clocks on TF=`300s (5m)`; first observed 5m bar close in this uptime window = `{_fmt_dt(first_bar_close_by_tf.get(300))}`"
    )
    md.append(
        f"- first observed 15m bar close (tf_sec=900) in this uptime window = `{_fmt_dt(first_bar_close_by_tf.get(900))}`"
    )
    md.append("")
    md.append("## BAR_CLOSED emission delay vs bar_close_ts (WAL)")
    md.append("This approximates how late `BAR_CLOSED` arrives vs the bar boundary (ms).")
    for tf in BAR_TFS:
        ds = bar_emit_deltas.get(tf, [])
        if not ds:
            md.append(f"- tf_sec={tf}: _(no samples)_")
            continue
        md.append(
            f"- tf_sec={tf}: n={len(ds)}, min={min(ds)}ms, median={_median(ds)}ms, p95={_pct(ds, 95)}ms, max={max(ds)}ms"
        )
    md.append("")
    md.append("## Tick TTL (config)")
    md.append(f"- tick_ttl_ms (from `{system_yaml}`): `{tick_ttl_ms}`")
    if tick_ttl_ms is not None:
        ds_300 = bar_emit_deltas.get(300, [])
        p95_300 = _pct(ds_300, 95) if ds_300 else None
        if p95_300 is not None:
            md.append(f"- compare: p95(BAR_CLOSED 300s delay)={p95_300}ms vs tick_ttl_ms={tick_ttl_ms}ms")
            if p95_300 > tick_ttl_ms:
                md.append("- implication: bar-boundary timestamps will often be treated as stale by strict TTL checks")
    md.append("")
    md.append("## TRADE_INTENT_REJECTED top reasons (WAL)")
    if reject_reasons:
        for reason, cnt in reject_reasons.most_common(10):
            md.append(f"- `{reason}`: `{cnt}`")
    else:
        md.append("- _(none found in WAL window)_")
    md.append("")
    md.append("## Top gate reasons (DecisionMaking text logs)")
    if dm_gate_reasons:
        for reason, cnt in dm_gate_reasons.most_common(10):
            md.append(f"- `{reason}`: `{cnt}`")
    else:
        md.append("- _(no gate-reason patterns matched)_")
    md.append("")
    md.append("")
    md.append("## Gate that blocks CMD:OPEN (file/line)")
    md.append("- warmup gate call site: `apps/reference/domains/decision_making/decision_making.py:925`")
    md.append("- warmup deny: `apps/reference/domains/decision_making/decision_making.py:2301` (checks warmup.full_ready) + `apps/reference/domains/decision_making/decision_making.py:2241` (logs WARMUP_NOT_READY:*)")
    md.append("- arbitration deny: `apps/reference/domains/decision_making/decision_making.py:475` (emits reason_code=ARBITRATION_BLOCKED; details include ARBITRATION_REJECT:*)")
    md.append("- tick-level features fail-closed: `apps/reference/domains/decision_making/decision_making.py:1810` → `apps/reference/domains/decision_making/decision_making.py:1833` (writes NRR-046)")
    md.append("")
    md.append("## Execution wiring sanity (only relevant if CMD:OPEN > 0)")
    md.append("- bridge dispatch calls execution directly: `apps/reference/main.py:768`")
    md.append("- ExecPosFSM routes `msg.verb == \"OPEN\"`: `apps/reference/domains/execution_position/fsm.py:1365`")
    md.append("")
    md.append("## Conclusion")
    md.append(f"- Root cause = {root_cause}")
    md.append("")

    out_md.write_text("\n".join(md), encoding="utf-8")

    print(out_md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
