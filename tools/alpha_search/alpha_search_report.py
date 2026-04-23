#!/usr/bin/env python3
"""
Alpha Search Performance Report Generator

Analyzes alpha_search signals from WAL/JSONL logs and computes:
- Per-model signal distribution (long/short/neutral)
- Hit rate vs actual price movement
- Virtual PnL (basis points)
- Confidence calibration (is 80% conf really 80% hit rate?)

Usage:
    python tools/alpha_search_report.py --run-dir reports/backtests/<run_id>
    python tools/alpha_search_report.py --wal-dir ops/wal
    python tools/alpha_search_report.py --run-dir reports/backtests/<run_id> --output-json out.json
    python tools/alpha_search_report.py --run-dir reports/backtests/<run_id> --output-md
"""

import argparse
import json
import math
import os
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class SignalRecord:
    """Parsed alpha signal from WAL."""
    ts_ms: int
    symbol: str
    provider_id: str
    model_name: str
    score: float
    confidence: float
    threshold: float
    signal_id: str
    bar_close_ts: int = 0
    shadow: bool = True


@dataclass
class ModelStats:
    """Aggregated stats for one model."""
    signals_total: int = 0
    signals_long: int = 0
    signals_short: int = 0
    signals_neutral: int = 0
    hits: int = 0
    misses: int = 0
    virtual_pnl_bps: float = 0.0
    confidence_sum: float = 0.0
    confidence_buckets: Dict[str, Dict[str, int]] = field(
        default_factory=lambda: defaultdict(lambda: {"total": 0, "hits": 0})
    )


# ---------------------------------------------------------------------------
# JSONL loading
# ---------------------------------------------------------------------------

def load_jsonl(path: str) -> List[Dict[str, Any]]:
    """Load JSONL file into list of dicts.  Skips malformed lines."""
    if not os.path.exists(path):
        return []
    records: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


def load_json_file(path: str) -> Optional[Dict[str, Any]]:
    """Load a single JSON file."""
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Event extraction
# ---------------------------------------------------------------------------

ALPHA_SCORE_WAL_VERBS = {"ALPHA_SCORE_CALCULATED", "ALPHA_SCORES_AGGREGATED"}


def extract_alpha_scores(wal_records: List[Dict[str, Any]]) -> List[SignalRecord]:
    """Extract provider-scoped alpha_search scores and DM aggregate alpha telemetry from WAL records."""
    signals: List[SignalRecord] = []
    for rec in wal_records:
        verb = rec.get("verb", "")
        op = rec.get("op", "")
        if verb not in ALPHA_SCORE_WAL_VERBS and not any(v in op for v in ALPHA_SCORE_WAL_VERBS):
            continue

        pld = rec.get("pld", rec)
        if not isinstance(pld, dict):
            continue

        # Unified schema: one signal per record
        if "model_name" in pld:
            try:
                sig = SignalRecord(
                    ts_ms=int(pld.get("ts_ms", rec.get("ts", 0))),
                    symbol=pld.get("symbol", ""),
                    provider_id=pld.get("provider_id", "unknown"),
                    model_name=pld.get("model_name", "unknown"),
                    score=float(pld.get("score", 0)),
                    confidence=float(pld.get("confidence", 0)),
                    threshold=float(pld.get("threshold", 0.1)),
                    signal_id=pld.get("signal_id", ""),
                    bar_close_ts=int(pld.get("bar_close_ts", 0)),
                    shadow=bool(pld.get("shadow", True)),
                )
                if sig.symbol:
                    signals.append(sig)
            except (ValueError, TypeError):
                continue

        # DecisionMaking aggregate telemetry format: {scores: [...]}
        elif "scores" in pld and isinstance(pld["scores"], list):
            symbol = pld.get("symbol", "")
            ts_ms = int(
                pld.get("timestamp", pld.get("ts_ms", rec.get("ts", 0))))
            for s in pld["scores"]:
                if not isinstance(s, dict):
                    continue
                try:
                    sig = SignalRecord(
                        ts_ms=ts_ms,
                        symbol=symbol,
                        provider_id="dm_aggregate",
                        model_name=s.get("model_name", "unknown"),
                        score=float(s.get("score", 0)),
                        confidence=float(s.get("confidence", 0)),
                        threshold=0.1,
                        signal_id="",
                    )
                    if sig.symbol:
                        signals.append(sig)
                except (ValueError, TypeError):
                    continue

    return signals


def extract_prices(wal_records: List[Dict[str, Any]]) -> Dict[str, List[Tuple[int, float]]]:
    """Extract price data from WAL (BAR_CLOSED, MARKET_TICK, etc.)."""
    prices: Dict[str, List[Tuple[int, float]]] = defaultdict(list)

    for rec in wal_records:
        verb = rec.get("verb", "")
        pld = rec.get("pld", rec)
        if not isinstance(pld, dict):
            continue

        symbol = pld.get("symbol")
        ts = pld.get("ts_ms", pld.get("ts", rec.get("ts", 0)))

        price = None
        if verb in ("MARKET_TICK", "MARKET_TICK_RECEIVED"):
            price = pld.get("price") or pld.get("close") or pld.get("mid")
        elif verb == "BAR_CLOSED":
            bar = pld.get("bar", {})
            price = bar.get("close")
        elif verb == "FEATURES_CALCULATED":
            feats = pld.get("features", {})
            price = feats.get("close") or feats.get("price")

        if symbol and price and ts:
            try:
                prices[symbol].append((int(ts), float(price)))
            except (ValueError, TypeError):
                pass

    for sym in prices:
        prices[sym].sort(key=lambda x: x[0])
    return prices


# ---------------------------------------------------------------------------
# Price lookup helpers
# ---------------------------------------------------------------------------

def _find_price_at(prices: List[Tuple[int, float]], ts_ms: int,
                   tolerance_ms: int = 60_000) -> Optional[float]:
    """Find price closest to timestamp within tolerance."""
    best: Optional[float] = None
    best_diff = float("inf")
    for pts, p in prices:
        diff = abs(pts - ts_ms)
        if diff < best_diff and diff <= tolerance_ms:
            best = p
            best_diff = diff
        if pts > ts_ms + tolerance_ms:
            break
    return best


def _find_price_after(prices: List[Tuple[int, float]], ts_ms: int) -> Optional[float]:
    """Find first price at or after timestamp."""
    for pts, p in prices:
        if pts >= ts_ms:
            return p
    return None


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

def analyze_signals(
    signals: List[SignalRecord],
    prices: Dict[str, List[Tuple[int, float]]],
    horizon_sec: int = 300,
) -> Dict[str, ModelStats]:
    """Analyze signal performance against actual price movements."""
    stats: Dict[str, ModelStats] = defaultdict(ModelStats)
    horizon_ms = horizon_sec * 1000

    for sig in signals:
        key = f"{sig.provider_id}:{sig.model_name}"
        ms = stats[key]
        ms.signals_total += 1
        ms.confidence_sum += sig.confidence

        is_long = sig.score > sig.threshold
        is_short = sig.score < -sig.threshold

        if is_long:
            ms.signals_long += 1
        elif is_short:
            ms.signals_short += 1
        else:
            ms.signals_neutral += 1
            continue

        sym_prices = prices.get(sig.symbol, [])
        if not sym_prices:
            continue

        entry_price = _find_price_at(sym_prices, sig.ts_ms)
        exit_price = _find_price_after(sym_prices, sig.ts_ms + horizon_ms)

        if entry_price is None or exit_price is None or entry_price == 0:
            continue

        ret_pct = (exit_price - entry_price) / entry_price
        ret_bps = ret_pct * 10_000

        is_hit = (is_long and ret_pct > 0) or (is_short and ret_pct < 0)
        if is_hit:
            ms.hits += 1
        else:
            ms.misses += 1

        signed_ret = ret_bps if is_long else -ret_bps
        ms.virtual_pnl_bps += signed_ret

        # Confidence calibration bucket (0.0, 0.2, 0.4, ...)
        bucket = f"{math.floor(sig.confidence * 5) / 5:.1f}"
        ms.confidence_buckets[bucket]["total"] += 1
        if is_hit:
            ms.confidence_buckets[bucket]["hits"] += 1

    return dict(stats)


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def generate_report(
    stats: Dict[str, ModelStats],
    run_id: Optional[str] = None,
    plugin_summary: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Generate JSON report from stats."""
    all_symbols: set[str] = set()
    # We can't easily get symbols from stats alone; use plugin_summary if available.

    report: Dict[str, Any] = {
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "run_id": run_id,
        "summary": {
            "total_signals": sum(s.signals_total for s in stats.values()),
            "total_models": len(stats),
        },
        "models": {},
        "confidence_calibration": {},
    }

    if plugin_summary:
        report["plugin_summary"] = plugin_summary

    for key, ms in sorted(stats.items()):
        directional = ms.hits + ms.misses
        hit_rate = ms.hits / directional if directional > 0 else 0.0
        avg_conf = ms.confidence_sum / ms.signals_total if ms.signals_total > 0 else 0.0

        report["models"][key] = {
            "signals_total": ms.signals_total,
            "signals_long": ms.signals_long,
            "signals_short": ms.signals_short,
            "signals_neutral": ms.signals_neutral,
            "directional_evaluated": directional,
            "hits": ms.hits,
            "misses": ms.misses,
            "hit_rate_pct": round(hit_rate * 100, 2),
            "virtual_pnl_bps": round(ms.virtual_pnl_bps, 2),
            "avg_confidence": round(avg_conf, 4),
        }

        conf_cal: Dict[str, Any] = {}
        for bucket, bs in sorted(ms.confidence_buckets.items()):
            if bs["total"] > 0:
                conf_cal[bucket] = {
                    "total": bs["total"],
                    "hits": bs["hits"],
                    "actual_hit_rate_pct": round(bs["hits"] / bs["total"] * 100, 2),
                }
        report["confidence_calibration"][key] = conf_cal

    return report


def generate_markdown(report: Dict[str, Any]) -> str:
    """Generate Markdown report from JSON."""
    lines = [
        "# Alpha Search Performance Report",
        "",
        f"**Generated:** {report['generated_at']}",
        f"**Run ID:** {report.get('run_id', 'N/A')}",
        f"**Total Signals:** {report['summary']['total_signals']}",
        f"**Total Models:** {report['summary']['total_models']}",
        "",
        "## Model Performance",
        "",
        "| Model | Signals | Long | Short | Neutral | Evaluated | Hits | Hit Rate | vPnL (bps) | Avg Conf |",
        "|-------|---------|------|-------|---------|-----------|------|----------|------------|----------|",
    ]

    for key, d in report["models"].items():
        lines.append(
            f"| {key} | {d['signals_total']} | {d['signals_long']} | "
            f"{d['signals_short']} | {d['signals_neutral']} | "
            f"{d['directional_evaluated']} | {d['hits']} | "
            f"**{d['hit_rate_pct']:.1f}%** | {d['virtual_pnl_bps']:.1f} | "
            f"{d['avg_confidence']:.3f} |"
        )

    lines.extend(["", "## Confidence Calibration", ""])
    lines.append("| Model | Bucket | Events | Actual Hit Rate |")
    lines.append("|-------|--------|--------|----------------|")

    for model, conf_data in report.get("confidence_calibration", {}).items():
        for bucket, data in sorted(conf_data.items()):
            lines.append(
                f"| {model} | {bucket} | {data['total']} | "
                f"{data['actual_hit_rate_pct']:.1f}% |"
            )

    if report.get("plugin_summary"):
        ps = report["plugin_summary"]
        lines.extend(["", "## Plugin Summary", ""])
        lines.append(f"- **Enabled:** {ps.get('enabled', 'N/A')}")
        lines.append(f"- **Mode:** {ps.get('mode', 'N/A')}")
        lines.append(f"- **Providers:** {ps.get('providers', [])}")
        cache = ps.get("cache", {})
        if cache:
            lines.append(
                f"- **Cache:** hits={cache.get('hits', 0)} "
                f"misses={cache.get('misses', 0)} "
                f"miss_rate={cache.get('miss_rate_pct', 0)}%"
            )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public API (for auto-run from backtest_plugin.shutdown)
# ---------------------------------------------------------------------------

def generate_alpha_report(run_dir: str, horizon_sec: int = 300) -> Dict[str, Any]:
    """
    Generate alpha report from a backtest run directory.

    Looks for WAL files in ops/wal/ and result.json in run_dir.
    Returns report dict suitable for JSON serialization.
    """
    run_path = Path(run_dir)
    run_id = run_path.name

    # Load WAL records
    wal_records: List[Dict[str, Any]] = []

    # Try WAL in run dir first
    wal_in_run = run_path / "wal"
    if wal_in_run.exists():
        for f in wal_in_run.glob("*.jsonl"):
            wal_records.extend(load_jsonl(str(f)))

    # Fall back to global WAL
    if not wal_records:
        global_wal = Path("ops/wal")
        if global_wal.exists():
            for f in global_wal.glob("*.jsonl"):
                wal_records.extend(load_jsonl(str(f)))

    # Get plugin summary from result.json
    result = load_json_file(str(run_path / "result.json"))
    plugin_summary = result.get("alpha_search") if result else None

    signals = extract_alpha_scores(wal_records)
    prices = extract_prices(wal_records)
    stats = analyze_signals(signals, prices, horizon_sec)

    return generate_report(stats, run_id, plugin_summary)


def save_report(run_dir: str, report: Dict[str, Any]) -> str:
    """Save report to <run_dir>/analysis/alpha_search_report.json."""
    analysis_dir = os.path.join(run_dir, "analysis")
    os.makedirs(analysis_dir, exist_ok=True)
    output_path = os.path.join(analysis_dir, "alpha_search_report.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    return output_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Alpha Search Performance Report Generator"
    )
    parser.add_argument(
        "--run-dir", help="Backtest run directory (reports/backtests/<id>)")
    parser.add_argument(
        "--wal-dir", help="WAL directory (alternative to --run-dir)")
    parser.add_argument("--horizon-sec", type=int, default=300,
                        help="Price horizon in seconds (default: 300)")
    parser.add_argument("--output-json", help="Write JSON report to file")
    parser.add_argument("--output-md", action="store_true",
                        help="Print Markdown table to stdout")
    args = parser.parse_args()

    wal_records: List[Dict[str, Any]] = []
    run_id: Optional[str] = None
    plugin_summary: Optional[Dict[str, Any]] = None

    if args.run_dir:
        run_path = Path(args.run_dir)
        run_id = run_path.name

        # WAL in run dir
        wal_in_run = run_path / "wal"
        if wal_in_run.exists():
            for f in wal_in_run.glob("*.jsonl"):
                wal_records.extend(load_jsonl(str(f)))

        # Global WAL
        if not wal_records:
            global_wal = Path("ops/wal")
            if global_wal.exists():
                for f in global_wal.glob("*.jsonl"):
                    wal_records.extend(load_jsonl(str(f)))

        # Plugin summary from result.json
        result = load_json_file(str(run_path / "result.json"))
        if result:
            plugin_summary = result.get("alpha_search")

    elif args.wal_dir:
        wal_dir = Path(args.wal_dir)
        if wal_dir.exists():
            for f in wal_dir.glob("*.jsonl"):
                wal_records.extend(load_jsonl(str(f)))
    else:
        print("ERROR: Specify --run-dir or --wal-dir", file=sys.stderr)
        sys.exit(1)

    if not wal_records:
        print("ERROR: No WAL records found", file=sys.stderr)
        sys.exit(1)

    print(f"Loaded {len(wal_records)} WAL records", file=sys.stderr)

    signals = extract_alpha_scores(wal_records)
    print(f"Found {len(signals)} alpha score events", file=sys.stderr)

    prices = extract_prices(wal_records)
    print(f"Found prices for {len(prices)} symbols", file=sys.stderr)

    stats = analyze_signals(signals, prices, args.horizon_sec)
    print(f"Analyzed {len(stats)} models", file=sys.stderr)

    report = generate_report(stats, run_id, plugin_summary)

    # Output
    if args.output_json:
        with open(args.output_json, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        print(f"JSON saved to: {args.output_json}", file=sys.stderr)

    if args.output_md:
        md = generate_markdown(report)
        print(md)
    elif not args.output_json:
        # Default: JSON to stdout
        print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
