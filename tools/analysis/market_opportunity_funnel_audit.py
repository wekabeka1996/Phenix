#!/usr/bin/env python3
"""Map ex-post market opportunities to the runtime strategy/order funnel.

This is a diagnostic, read-only audit. Opportunity labels use future prices and
must never be consumed by live trading logic. Their purpose is to localize where
historical market moves disappeared: strategy generation, decision gates, or
execution.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import mean, median
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RESEARCH_ROOT = ROOT / "reports" / "nrr_runtime_research_20260613"
DEFAULT_SNAPSHOT = DEFAULT_RESEARCH_ROOT / "source_snapshot"
DEFAULT_REPORT_ROOT = DEFAULT_RESEARCH_ROOT / "opportunity_funnel"
BAR_MS = 900_000
LOCAL_TZ = timezone(timedelta(hours=3))
TRACE_JSON_MARKERS = {
    "MD_AMR_BAR_DECISION_TRACE": "md_amr",
    "ALPHA_TA_ENSEMBLE_TRACE": "alpha_ta_ensemble",
    "ALPHA_MR_S01_TRACE": "alpha_mr_s01",
}
AURORA_RE = re.compile(
    r"\[(?P<symbol>[A-Z0-9]+)\] QUADRATIC_DECISION_TRACE "
    r"score=(?P<score>[-+0-9.eE]+).*?side=(?P<side>\S*) .*?regime=(?P<regime>\S+)"
)
PREFIX_TS_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3})")


@dataclass(frozen=True)
class Bar:
    close_ts_ms: int
    open: float
    high: float
    low: float
    close: float

    @property
    def start_ts_ms(self) -> int:
        return self.close_ts_ms - BAR_MS + 1


def number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def integer(value: Any) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def iso_utc(ts_ms: int | None) -> str | None:
    if ts_ms is None:
        return None
    return datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc).isoformat()


def prefix_ts_ms(line: str) -> int | None:
    match = PREFIX_TS_RE.match(line)
    if not match:
        return None
    parsed = datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S,%f").replace(tzinfo=LOCAL_TZ)
    return int(parsed.timestamp() * 1000)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line_no, raw in enumerate(handle, start=1):
            try:
                row = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                row = dict(row)
                row["source_line"] = line_no
                rows.append(row)
    return rows


def load_bars(root: Path, symbols: set[str], start_ms: int, end_ms: int) -> dict[str, list[Bar]]:
    indexed: dict[str, dict[int, Bar]] = defaultdict(dict)
    for path in sorted(root.rglob("*_900.csv")):
        symbol = path.stem.removesuffix("_900").upper()
        if symbol not in symbols:
            continue
        with path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
            for row in csv.DictReader(handle):
                ts_ms = integer(row.get("timestamp"))
                values = [number(row.get(key)) for key in ("open", "high", "low", "close")]
                if ts_ms is None or ts_ms < start_ms or ts_ms > end_ms or any(value is None for value in values):
                    continue
                indexed[symbol][ts_ms] = Bar(ts_ms, values[0], values[1], values[2], values[3])
    return {symbol: sorted(rows.values(), key=lambda bar: bar.close_ts_ms) for symbol, rows in indexed.items()}


def core_log_paths(logs_root: Path) -> list[Path]:
    paths = [path for path in logs_root.glob("aurora_core.log*") if path.is_file()]

    def order(path: Path) -> tuple[int, str]:
        suffix = path.name.removeprefix("aurora_core.log")
        return (-(int(suffix[1:]) if suffix.startswith(".") and suffix[1:].isdigit() else 0), path.name)

    return sorted(paths, key=order)


def normalized_side(value: Any) -> str:
    side = str(value or "").strip().upper()
    if side in {"LONG", "BUY"}:
        return "BUY"
    if side in {"SHORT", "SELL"}:
        return "SELL"
    return "NEUTRAL"


def parse_strategy_traces(logs_root: Path, start_ms: int, end_ms: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in core_log_paths(logs_root):
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for raw in handle:
                if not any(marker in raw for marker in (*TRACE_JSON_MARKERS, "QUADRATIC_DECISION_TRACE")):
                    continue
                row: dict[str, Any] | None = None
                for marker, strategy_id in TRACE_JSON_MARKERS.items():
                    token = marker + " "
                    if token not in raw:
                        continue
                    try:
                        payload = json.loads(raw.split(token, 1)[1])
                    except json.JSONDecodeError:
                        break
                    observed_at_ms = prefix_ts_ms(raw)
                    ts_ms = integer(
                        payload.get("bar_close_ts")
                        or payload.get("ts_ms")
                        or payload.get("timestamp")
                        or payload.get("source_ts")
                    ) or observed_at_ms
                    trace = payload.get("trace") if isinstance(payload.get("trace"), dict) else {}
                    status = str(payload.get("result_status") or payload.get("decision_route") or "").upper()
                    side = normalized_side(payload.get("side") or trace.get("side"))
                    reason = payload.get("no_signal_reason") or payload.get("suppression_reason") or payload.get("reason")
                    if status == "SIGNAL" or side in {"BUY", "SELL"}:
                        outcome = "SIGNAL"
                    elif "SUPPRESS" in status or reason:
                        outcome = "SUPPRESSED"
                    else:
                        outcome = "NEUTRAL"
                    row = {
                        "timestamp_ms": ts_ms,
                        "observed_at_ms": observed_at_ms,
                        "strategy_id": strategy_id,
                        "symbol": str(payload.get("symbol") or "").upper(),
                        "side": side,
                        "outcome": outcome,
                        "reason": reason,
                        "regime": payload.get("regime") or trace.get("regime"),
                        "score": number(payload.get("score") or payload.get("combined_score") or trace.get("score")),
                        "allowed_regime": payload.get("allowed_regime"),
                        "source_file": path.name,
                    }
                    break
                if row is None and "QUADRATIC_DECISION_TRACE" in raw:
                    match = AURORA_RE.search(raw)
                    if match:
                        side = normalized_side(match.group("side"))
                        row = {
                            "timestamp_ms": prefix_ts_ms(raw),
                            "observed_at_ms": prefix_ts_ms(raw),
                            "strategy_id": "aurora",
                            "symbol": match.group("symbol"),
                            "side": side,
                            "outcome": "SIGNAL" if side in {"BUY", "SELL"} else "NEUTRAL",
                            "reason": "score_below_or_inside_neutral_threshold" if side == "NEUTRAL" else None,
                            "regime": match.group("regime"),
                            "score": number(match.group("score")),
                            "allowed_regime": None,
                            "source_file": path.name,
                        }
                if row and row["timestamp_ms"] is not None and start_ms <= row["timestamp_ms"] <= end_ms and row["symbol"]:
                    rows.append(row)

    mean_reversion_log = logs_root / "domain_mean_reversion.log"
    if mean_reversion_log.exists():
        with mean_reversion_log.open("r", encoding="utf-8", errors="replace") as handle:
            for raw in handle:
                token = "MR_SIGNAL "
                if token not in raw:
                    continue
                try:
                    payload = json.loads(raw.split(token, 1)[1])
                except json.JSONDecodeError:
                    continue
                ts_ms = integer(payload.get("ts_ms")) or prefix_ts_ms(raw)
                if ts_ms is None or not (start_ms <= ts_ms <= end_ms):
                    continue
                rows.append(
                    {
                        "timestamp_ms": ts_ms,
                        "observed_at_ms": prefix_ts_ms(raw),
                        "strategy_id": "mean_reversion",
                        "symbol": str(payload.get("symbol") or "").upper(),
                        "side": normalized_side(payload.get("side")),
                        "outcome": "SIGNAL",
                        "reason": payload.get("why"),
                        "regime": payload.get("flat_regime"),
                        "score": number(payload.get("confidence")),
                        "allowed_regime": True,
                        "source_file": mean_reversion_log.name,
                    }
                )
    rows.sort(key=lambda row: row["timestamp_ms"])
    return rows


def contiguous(window: list[Bar]) -> bool:
    return all(current.close_ts_ms - previous.close_ts_ms == BAR_MS for previous, current in zip(window, window[1:]))


def build_candidates(
    bars_by_symbol: dict[str, list[Bar]],
    horizons: tuple[int, ...],
    cost_bps: float,
    threshold_bps: float,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    tier_counts: dict[str, Counter[str]] = defaultdict(Counter)
    for symbol, bars in sorted(bars_by_symbol.items()):
        for decision_index in range(len(bars) - 1):
            decision_bar = bars[decision_index]
            entry_index = decision_index + 1
            entry_price = bars[entry_index].open
            best: dict[str, Any] | None = None
            for horizon in horizons:
                end_index = entry_index + horizon - 1
                if end_index >= len(bars):
                    continue
                window = bars[entry_index : end_index + 1]
                if not contiguous(window):
                    continue
                exit_price = window[-1].close
                long_net = (exit_price / entry_price - 1.0) * 10_000.0 - cost_bps
                short_net = (entry_price / exit_price - 1.0) * 10_000.0 - cost_bps
                side = "BUY" if long_net >= short_net else "SELL"
                net_bps = max(long_net, short_net)
                if side == "BUY":
                    mfe = max(bar.high / entry_price - 1.0 for bar in window) * 10_000.0
                    mae = min(bar.low / entry_price - 1.0 for bar in window) * 10_000.0
                else:
                    mfe = max(entry_price / bar.low - 1.0 for bar in window) * 10_000.0
                    mae = min(entry_price / bar.high - 1.0 for bar in window) * 10_000.0
                if best is None or net_bps > best["best_net_bps"]:
                    best = {
                        "symbol": symbol,
                        "decision_ts_ms": decision_bar.close_ts_ms,
                        "entry_ts_ms": bars[entry_index].start_ts_ms,
                        "entry_price": entry_price,
                        "side": side,
                        "best_horizon_bars": horizon,
                        "best_net_bps": net_bps,
                        "mfe_bps": mfe,
                        "mae_bps": mae,
                        "exit_ts_ms": window[-1].close_ts_ms,
                        "exit_price": exit_price,
                    }
            if best is None:
                continue
            for tier in (25, 50, 100, 200):
                if best["best_net_bps"] >= tier:
                    tier_counts[symbol][str(tier)] += 1
            if best["best_net_bps"] >= threshold_bps:
                candidates.append(best)
    tier_summary = {symbol: dict(counts) for symbol, counts in sorted(tier_counts.items())}
    return candidates, tier_summary


def group_opportunity_episodes(candidates: list[dict[str, Any]], gap_bars: int = 2) -> list[dict[str, Any]]:
    episodes: list[dict[str, Any]] = []
    by_symbol: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in candidates:
        by_symbol[row["symbol"]].append(row)
    episode_id = 0
    for symbol, rows in sorted(by_symbol.items()):
        current: list[dict[str, Any]] = []
        for row in sorted(rows, key=lambda item: item["decision_ts_ms"]):
            if current and (
                row["side"] != current[-1]["side"]
                or row["decision_ts_ms"] - current[-1]["decision_ts_ms"] > gap_bars * BAR_MS
            ):
                episode_id += 1
                episodes.append(collapse_episode(episode_id, current))
                current = []
            current.append(row)
        if current:
            episode_id += 1
            episodes.append(collapse_episode(episode_id, current))
    return episodes


def collapse_episode(episode_id: int, rows: list[dict[str, Any]]) -> dict[str, Any]:
    representative = max(rows, key=lambda row: row["best_net_bps"])
    return {
        "opportunity_id": episode_id,
        "symbol": representative["symbol"],
        "side": representative["side"],
        "episode_start_ts_ms": rows[0]["decision_ts_ms"],
        "candidate_end_ts_ms": rows[-1]["decision_ts_ms"],
        "episode_end_ts_ms": max(row["exit_ts_ms"] for row in rows),
        "representative_decision_ts_ms": representative["decision_ts_ms"],
        "entry_ts_ms": representative["entry_ts_ms"],
        "entry_price": representative["entry_price"],
        "best_horizon_bars": representative["best_horizon_bars"],
        "best_net_bps": representative["best_net_bps"],
        "mfe_bps": representative["mfe_bps"],
        "mae_bps": representative["mae_bps"],
        "candidate_bars": len(rows),
    }


def event_side(row: dict[str, Any]) -> str:
    return normalized_side(row.get("side"))


def normalized_reason(value: Any) -> str:
    reason = str(value or "")
    if reason.startswith("regime_not_allowed"):
        return "regime_not_allowed"
    return reason


def attribute_episodes(
    episodes: list[dict[str, Any]],
    order_rows: list[dict[str, Any]],
    trace_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for episode in episodes:
        start = episode["episode_start_ts_ms"] - BAR_MS
        end = episode["candidate_end_ts_ms"] + BAR_MS
        symbol = episode["symbol"]
        side = episode["side"]
        orders = [
            row for row in order_rows
            if str(row.get("symbol") or "").upper() == symbol
            and (integer(row.get("timestamp")) or -1) >= start
            and (integer(row.get("timestamp")) or -1) <= end
        ]
        traces = [
            row for row in trace_rows
            if row["symbol"] == symbol and start <= row["timestamp_ms"] <= end
        ]
        aligned_rejects = [row for row in orders if row.get("event_type") == "DECISION_INTENT_REJECTED" and event_side(row) == side]
        opposite_rejects = [row for row in orders if row.get("event_type") == "DECISION_INTENT_REJECTED" and event_side(row) not in {side, "NEUTRAL"}]
        market_events = [row for row in orders if row.get("event_type") in {"ORDER_PLACED", "ORDER_FILLED"} and event_side(row) == side]
        aligned_signals = [row for row in traces if row["outcome"] == "SIGNAL" and row["side"] == side]
        opposite_signals = [row for row in traces if row["outcome"] == "SIGNAL" and row["side"] not in {side, "NEUTRAL"}]
        aligned_regime_blocked_signals = [
            row for row in aligned_signals
            if row["strategy_id"] == "md_amr" and row.get("allowed_regime") is False
        ]
        aligned_regime_allowed_signals = [
            row for row in aligned_signals
            if row["strategy_id"] != "md_amr" or row.get("allowed_regime") is not False
        ]
        neutral_traces = [row for row in traces if row["outcome"] != "SIGNAL"]
        if market_events:
            classification = "CAPTURED_TO_MARKET"
            missed_layer = "none"
        elif aligned_rejects:
            classification = "ALIGNED_SIGNAL_REJECTED"
            missed_layer = "decision_gate"
        elif aligned_signals and len(aligned_regime_blocked_signals) == len(aligned_signals):
            classification = "ALIGNED_SIGNAL_REGIME_BLOCKED"
            missed_layer = "strategy_regime_gate"
        elif aligned_signals:
            classification = "ALIGNED_POST_REGIME_SIGNAL_NO_ORDER"
            missed_layer = "intent_builder_or_telemetry"
        elif opposite_rejects or opposite_signals:
            classification = "DIRECTION_MISREAD"
            missed_layer = "strategy_direction"
        elif neutral_traces:
            classification = "STRATEGY_NEUTRAL_OR_SUPPRESSED"
            missed_layer = "strategy_generation"
        else:
            classification = "NO_STRATEGY_TELEMETRY"
            missed_layer = "telemetry_or_inactive_strategy"
        result = dict(episode)
        result.update(
            {
                "episode_start_utc": iso_utc(episode["episode_start_ts_ms"]),
                "episode_end_utc": iso_utc(episode["episode_end_ts_ms"]),
                "classification": classification,
                "missed_layer": missed_layer,
                "aligned_reject_count": len(aligned_rejects),
                "opposite_reject_count": len(opposite_rejects),
                "aligned_signal_count": len(aligned_signals),
                "aligned_regime_blocked_signal_count": len(aligned_regime_blocked_signals),
                "aligned_regime_allowed_signal_count": len(aligned_regime_allowed_signals),
                "opposite_signal_count": len(opposite_signals),
                "aligned_signal_strategies": sorted({row["strategy_id"] for row in aligned_signals}),
                "opposite_signal_strategies": sorted({row["strategy_id"] for row in opposite_signals}),
                "neutral_or_suppressed_trace_count": len(neutral_traces),
                "trace_strategies": sorted({row["strategy_id"] for row in traces}),
                "reject_nrr_codes": sorted({str(row.get("nrr_code")) for row in aligned_rejects}),
                "suppression_reasons": sorted({normalized_reason(row.get("reason")) for row in neutral_traces if row.get("reason")})[:20],
            }
        )
        results.append(result)
    return results


def trace_census(rows: list[dict[str, Any]], symbols: set[str]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str, str], int] = Counter()
    for row in rows:
        if row["symbol"] in symbols:
            reason = normalized_reason(row.get("reason"))
            grouped[(row["symbol"], row["strategy_id"], row["outcome"], reason)] += 1
    return [
        {"symbol": key[0], "strategy_id": key[1], "outcome": key[2], "reason": key[3], "count": count}
        for key, count in sorted(grouped.items(), key=lambda item: (-item[1], item[0]))
    ]


def summarize_opportunities(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(row["symbol"], row["classification"])].append(row)
    result = []
    for (symbol, classification), group in sorted(grouped.items()):
        result.append(
            {
                "symbol": symbol,
                "classification": classification,
                "episodes": len(group),
                "mean_best_net_bps": mean(row["best_net_bps"] for row in group),
                "median_best_net_bps": median(row["best_net_bps"] for row in group),
                "mean_mae_bps": mean(row["mae_bps"] for row in group),
            }
        )
    return result


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=True, sort_keys=True, default=str) + "\n")


def csv_value(value: Any) -> Any:
    if isinstance(value, (list, dict, tuple)):
        return json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)
    return value


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = sorted({field for row in rows for field in row})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_value(row.get(field)) for field in fields})


def render_report(
    summary: dict[str, Any],
    opportunity_summary: list[dict[str, Any]],
    trace_summary: list[dict[str, Any]],
) -> str:
    lines = [
        "# Market Opportunity Funnel Audit",
        "",
        "This report uses future prices only for historical diagnosis. It does not define a live signal.",
        "",
        "## Scope",
        "",
        f"- Window: {summary['start_utc']} to {summary['end_utc']}",
        f"- Symbols: {', '.join(summary['symbols'])}",
        f"- Primary opportunity threshold: {summary['opportunity_threshold_bps']} bps net after {summary['cost_bps']} bps costs.",
        f"- Opportunity episodes: {summary['opportunity_episodes']}",
        f"- Strategy traces available: {summary['strategy_trace_rows']}",
        "",
        "## Opportunity Attribution",
        "",
        "| Symbol | Classification | Episodes | Mean best net bps | Mean MAE bps |",
        "|---|---|---:|---:|---:|",
    ]
    for row in opportunity_summary:
        lines.append(
            f"| {row['symbol']} | {row['classification']} | {row['episodes']} | "
            f"{row['mean_best_net_bps']:.2f} | {row['mean_mae_bps']:.2f} |"
        )
    lines.extend(["", "## Dominant Strategy Outcomes", "", "| Symbol | Strategy | Outcome | Reason | Count |", "|---|---|---|---|---:|"])
    for row in trace_summary[:60]:
        reason = str(row["reason"]).replace("|", "\\|")[:100]
        lines.append(f"| {row['symbol']} | {row['strategy_id']} | {row['outcome']} | {reason} | {row['count']} |")
    lines.extend(
        [
            "",
            "## Reading",
            "",
            "- `ALIGNED_SIGNAL_REJECTED` means the strategy saw the eventual direction, but a decision gate stopped it.",
            "- `ALIGNED_SIGNAL_REGIME_BLOCKED` means MD-AMR produced the eventual direction but its own asset regime allowlist stopped the signal.",
            "- `ALIGNED_POST_REGIME_SIGNAL_NO_ORDER` means at least one aligned signal passed the MD-AMR regime allowlist but no order-log decision followed.",
            "- `STRATEGY_NEUTRAL_OR_SUPPRESSED` means the opportunity disappeared before NRR evaluation.",
            "- `DIRECTION_MISREAD` means the observed strategy/order direction opposed the eventual profitable move.",
            "- `NO_STRATEGY_TELEMETRY` is not evidence of neutrality; it marks unavailable or inactive telemetry.",
        ]
    )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Historical market opportunity to strategy/order funnel audit")
    parser.add_argument("--snapshot-root", type=Path, default=DEFAULT_SNAPSHOT)
    parser.add_argument("--logs-root", type=Path, default=ROOT / "logs")
    parser.add_argument("--report-root", type=Path, default=DEFAULT_REPORT_ROOT)
    parser.add_argument("--symbols", default="BTCUSDT,ETHUSDT,SOLUSDT")
    parser.add_argument("--horizons", default="1,2,4,8")
    parser.add_argument("--cost-bps", type=float, default=10.0)
    parser.add_argument("--opportunity-threshold-bps", type=float, default=50.0)
    args = parser.parse_args(argv)

    symbols = {value.strip().upper() for value in args.symbols.split(",") if value.strip()}
    horizons = tuple(sorted({int(value) for value in args.horizons.split(",") if int(value) > 0}))
    order_path = args.snapshot_root / "logs" / "order_log_v1.jsonl"
    order_rows = read_jsonl(order_path)
    timestamps = [integer(row.get("timestamp")) for row in order_rows]
    timestamps = [value for value in timestamps if value is not None]
    start_ms, end_ms = min(timestamps), max(timestamps)
    bars_by_symbol = load_bars(args.snapshot_root / "data" / "recorder", symbols, start_ms, end_ms + max(horizons) * BAR_MS)
    traces = parse_strategy_traces(args.logs_root, start_ms, end_ms)
    candidates, tier_counts = build_candidates(bars_by_symbol, horizons, args.cost_bps, args.opportunity_threshold_bps)
    episodes = group_opportunity_episodes(candidates)
    attributed = attribute_episodes(episodes, order_rows, traces)
    trace_summary = trace_census(traces, symbols)
    opportunity_summary = summarize_opportunities(attributed)

    root = args.report_root
    root.mkdir(parents=True, exist_ok=True)
    write_jsonl(root / "strategy_trace_rows.jsonl", traces)
    write_csv(root / "strategy_trace_census.csv", trace_summary)
    write_csv(root / "opportunity_episodes.csv", attributed)
    write_json(root / "opportunity_episodes.json", attributed)
    write_csv(root / "opportunity_summary.csv", opportunity_summary)
    summary = {
        "start_ts_ms": start_ms,
        "end_ts_ms": end_ms,
        "start_utc": iso_utc(start_ms),
        "end_utc": iso_utc(end_ms),
        "symbols": sorted(symbols),
        "horizons_15m_bars": horizons,
        "cost_bps": args.cost_bps,
        "opportunity_threshold_bps": args.opportunity_threshold_bps,
        "opportunity_candidate_bars": len(candidates),
        "opportunity_episodes": len(episodes),
        "strategy_trace_rows": len(traces),
        "strategy_trace_start_utc": iso_utc(min((row["timestamp_ms"] for row in traces), default=None)),
        "strategy_trace_end_utc": iso_utc(max((row["timestamp_ms"] for row in traces), default=None)),
        "tier_candidate_counts": tier_counts,
        "classification_counts": dict(Counter(row["classification"] for row in attributed)),
        "missed_layer_counts": dict(Counter(row["missed_layer"] for row in attributed)),
    }
    write_json(root / "summary.json", summary)
    (root / "MARKET_OPPORTUNITY_FUNNEL_AUDIT.md").write_text(
        render_report(summary, opportunity_summary, trace_summary), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
