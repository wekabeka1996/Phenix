#!/usr/bin/env python3
"""
FEATURE-INTEGRITY-FULL-AUDIT-005: Minimal replay sanity check (post-run).

Goal (non-blocker):
1) SELL intents > 0 in WAL (TRADE_INTENT_PROPOSED).
2) macro_resid distribution is signed on real-ish noise:
   P05 < 0, P95 > 0, median ~= 0 (tolerance is informational).

Inputs:
- --wal: one or more WAL jsonl files (ops/wal/*.jsonl)
- --features: optional feature jsonl logs (logs/features/*.log) with macro_resid emitted

Writes JSON summary to --out (default: stdout).
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable


def _iter_jsonl(paths: Iterable[Path]) -> Iterable[dict[str, Any]]:
    for path in paths:
        try:
            with path.open("r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except Exception:
                        continue
                    if isinstance(rec, dict):
                        yield rec
        except FileNotFoundError:
            continue


def _percentile(sorted_vals: list[float], q: float) -> float:
    if not sorted_vals:
        raise ValueError("empty")
    if q <= 0:
        return sorted_vals[0]
    if q >= 1:
        return sorted_vals[-1]
    idx = (len(sorted_vals) - 1) * q
    lo = int(idx)
    hi = min(lo + 1, len(sorted_vals) - 1)
    w = idx - lo
    return (1 - w) * sorted_vals[lo] + w * sorted_vals[hi]


def summarize(vals: list[float]) -> dict[str, Any]:
    if not vals:
        return {
            "n": 0,
            "p05": None,
            "p50": None,
            "p95": None,
            "min": None,
            "max": None,
            "frac_pos": None,
            "frac_neg": None,
        }
    s = sorted(vals)
    n = len(s)
    pos = sum(1 for v in s if v > 0)
    neg = sum(1 for v in s if v < 0)
    return {
        "n": n,
        "p05": _percentile(s, 0.05),
        "p50": _percentile(s, 0.50),
        "p95": _percentile(s, 0.95),
        "min": s[0],
        "max": s[-1],
        "frac_pos": pos / n,
        "frac_neg": neg / n,
    }


def count_trade_intents(wal_paths: list[Path]) -> dict[str, Any]:
    counts: dict[str, Any] = {
        "total": 0,
        "buy": 0,
        "sell": 0,
        "by_strategy": defaultdict(lambda: {"total": 0, "buy": 0, "sell": 0}),
        "by_symbol": defaultdict(lambda: {"total": 0, "buy": 0, "sell": 0}),
    }

    for rec in _iter_jsonl(wal_paths):
        if rec.get("op") != "EVT":
            continue
        if rec.get("verb") != "TRADE_INTENT_PROPOSED":
            continue
        pld = rec.get("pld")
        if not isinstance(pld, dict):
            continue

        side = str(pld.get("side") or "").lower()
        symbol = str(pld.get("instrument") or "unknown")
        strategy = str(pld.get("strategy") or pld.get("strategy_id") or "unknown")

        counts["total"] += 1
        counts["by_symbol"][symbol]["total"] += 1
        counts["by_strategy"][strategy]["total"] += 1

        if side in ("buy", "long"):
            counts["buy"] += 1
            counts["by_symbol"][symbol]["buy"] += 1
            counts["by_strategy"][strategy]["buy"] += 1
        elif side in ("sell", "short"):
            counts["sell"] += 1
            counts["by_symbol"][symbol]["sell"] += 1
            counts["by_strategy"][strategy]["sell"] += 1

    counts["by_symbol"] = dict(counts["by_symbol"])
    counts["by_strategy"] = dict(counts["by_strategy"])
    return counts


def read_macro_resid_from_feature_logs(feature_paths: list[Path]) -> dict[str, Any]:
    vals_by_symbol: dict[str, list[float]] = defaultdict(list)

    for rec in _iter_jsonl(feature_paths):
        try:
            sym = str(rec.get("symbol") or rec.get("instrument") or "unknown")
            raw = rec.get("macro_resid")
            if raw is None:
                # Some logs have nested "features"
                feats = rec.get("features")
                if isinstance(feats, dict):
                    raw = feats.get("macro_resid")
            if raw is None:
                continue
            val = float(raw)
        except Exception:
            continue
        vals_by_symbol[sym].append(val)

    all_vals: list[float] = []
    for sym, vals in vals_by_symbol.items():
        all_vals.extend(vals)

    out: dict[str, Any] = {"__ALL__": summarize(all_vals), "by_symbol": {}}
    for sym in sorted(vals_by_symbol.keys()):
        out["by_symbol"][sym] = summarize(vals_by_symbol[sym])
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--wal", nargs="+", required=True, help="WAL jsonl paths (e.g. ops/wal/2026-01-*.jsonl)")
    ap.add_argument(
        "--features",
        nargs="*",
        default=[],
        help="Optional feature jsonl logs with macro_resid (e.g. logs/features/*.log).",
    )
    ap.add_argument("--out", default="-", help="Output JSON path (default: stdout)")
    ns = ap.parse_args()

    wal_paths = [Path(p) for p in ns.wal]
    feat_paths = [Path(p) for p in ns.features]

    intents = count_trade_intents(wal_paths)
    macro_resid = read_macro_resid_from_feature_logs(feat_paths) if feat_paths else {"note": "no --features provided"}

    inv = {
        "sell_intents_gt_zero": bool(intents.get("sell", 0) > 0),
        "macro_resid_signed_p05_lt_0": None,
        "macro_resid_signed_p95_gt_0": None,
    }
    all_dist = macro_resid.get("__ALL__") if isinstance(macro_resid, dict) else None
    if isinstance(all_dist, dict) and all_dist.get("n"):
        p05 = all_dist.get("p05")
        p95 = all_dist.get("p95")
        inv["macro_resid_signed_p05_lt_0"] = bool(p05 is not None and p05 < 0)
        inv["macro_resid_signed_p95_gt_0"] = bool(p95 is not None and p95 > 0)

    summary = {
        "task_id": "FEATURE-INTEGRITY-FULL-AUDIT-005",
        "replay_type": "post_run_log_check",
        "inputs": {"wal": [str(p) for p in wal_paths], "features": [str(p) for p in feat_paths]},
        "intent_counts": intents,
        "macro_resid_distribution": macro_resid,
        "invariants": inv,
    }

    payload = json.dumps(summary, indent=2, ensure_ascii=False) + "\n"
    if ns.out == "-":
        print(payload, end="")
        return 0
    out_path = Path(ns.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(payload, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

