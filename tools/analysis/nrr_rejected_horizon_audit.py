#!/usr/bin/env python3
"""Causal 15-minute horizon audit for rejected NRR trade intents.

The audit is intentionally read-only. It enters at the open of the first full
900-second bar that starts after a rejected intent, then measures fixed-horizon
returns, MFE, and MAE without using future information in the entry price.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
from bisect import bisect_right
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ORDER_LOG = ROOT / "logs" / "order_log_v1.jsonl"
DEFAULT_RECORDER_ROOT = ROOT / "data" / "recorder"
DEFAULT_REPORT_ROOT = ROOT / "reports" / "nrr_runtime_research_20260613" / "horizon_15m"
DEFAULT_HORIZONS = (1, 2, 4, 8, 16, 32)
BAR_MS = 900_000


@dataclass(frozen=True)
class Bar:
    close_ts_ms: int
    open: float
    high: float
    low: float
    close: float
    source_file: str

    @property
    def start_ts_ms(self) -> int:
        return self.close_ts_ms - BAR_MS + 1


def iso_utc(ts_ms: int | None) -> str | None:
    if ts_ms is None:
        return None
    return datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc).isoformat()


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


def iter_jsonl(path: Path) -> Iterable[tuple[int, dict[str, Any]]]:
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line_no, raw in enumerate(handle, start=1):
            try:
                row = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                yield line_no, row


def load_rejects(path: Path) -> tuple[list[dict[str, Any]], list[int]]:
    rows: list[dict[str, Any]] = []
    boots: list[int] = []
    seen: set[tuple[Any, ...]] = set()
    for line_no, row in iter_jsonl(path):
        ts_ms = integer(row.get("timestamp"))
        if row.get("event_type") == "BOOT" and ts_ms is not None:
            boots.append(ts_ms)
            continue
        nrr = str(row.get("nrr_code") or "").strip().upper()
        if row.get("event_type") != "DECISION_INTENT_REJECTED" or not nrr.startswith("NRR-"):
            continue
        symbol = str(row.get("symbol") or "").strip().upper()
        side = str(row.get("side") or "").strip().upper()
        strategy = str(row.get("strategy_id") or "unknown").strip() or "unknown"
        if ts_ms is None or not symbol or side not in {"BUY", "SELL"}:
            continue
        key = (row.get("rid"), symbol, side, strategy, nrr, ts_ms)
        if key in seen:
            continue
        seen.add(key)
        rows.append(
            {
                "source_line": line_no,
                "rid": row.get("rid"),
                "timestamp_ms": ts_ms,
                "timestamp_utc": iso_utc(ts_ms),
                "symbol": symbol,
                "side": side,
                "strategy_id": strategy,
                "nrr_code": nrr,
                "why": row.get("why"),
                "regime": row.get("regime"),
                "regime_confidence": number(row.get("regime_confidence")),
            }
        )
    boots.sort()
    for row in rows:
        row["boot_session"] = bisect_right(boots, row["timestamp_ms"])
    return rows, boots


def load_bars(root: Path, symbols: set[str]) -> tuple[dict[str, list[Bar]], dict[str, Any]]:
    by_symbol: dict[str, dict[int, Bar]] = defaultdict(dict)
    for path in sorted(root.rglob("*_900.csv")):
        symbol = path.stem.removesuffix("_900").upper()
        if symbol not in symbols:
            continue
        with path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
            for row in csv.DictReader(handle):
                ts_ms = integer(row.get("timestamp"))
                values = [number(row.get(key)) for key in ("open", "high", "low", "close")]
                if ts_ms is None or any(value is None for value in values):
                    continue
                by_symbol[symbol][ts_ms] = Bar(ts_ms, values[0], values[1], values[2], values[3], path.as_posix())
    result: dict[str, list[Bar]] = {}
    coverage: dict[str, Any] = {}
    for symbol, indexed in sorted(by_symbol.items()):
        bars = sorted(indexed.values(), key=lambda item: item.close_ts_ms)
        result[symbol] = bars
        gaps = []
        for previous, current in zip(bars, bars[1:]):
            delta = current.close_ts_ms - previous.close_ts_ms
            if delta != BAR_MS:
                gaps.append({"after": previous.close_ts_ms, "before": current.close_ts_ms, "missing_bars": max(0, delta // BAR_MS - 1)})
        coverage[symbol] = {
            "bar_count": len(bars),
            "first_close_ts_ms": bars[0].close_ts_ms if bars else None,
            "last_close_ts_ms": bars[-1].close_ts_ms if bars else None,
            "gap_count": len(gaps),
            "missing_bars": sum(item["missing_bars"] for item in gaps),
            "gaps": gaps[:100],
        }
    return result, coverage


def side_return(side: str, entry: float, exit_price: float) -> float:
    raw = exit_price / entry - 1.0
    return raw if side == "BUY" else -raw


def replay_row(row: dict[str, Any], bars: list[Bar], horizons: tuple[int, ...], cost_bps: float) -> dict[str, Any]:
    starts = [bar.start_ts_ms for bar in bars]
    entry_index = bisect_right(starts, row["timestamp_ms"])
    output = dict(row)
    if entry_index >= len(bars):
        output["replay_status"] = "NO_FORWARD_BAR"
        return output
    entry_bar = bars[entry_index]
    entry = entry_bar.open
    entry_delay_ms = entry_bar.start_ts_ms - row["timestamp_ms"]
    output.update(
        {
            "replay_status": "REPLAYED",
            "entry_ts_ms": entry_bar.start_ts_ms,
            "entry_utc": iso_utc(entry_bar.start_ts_ms),
            "entry_price": entry,
            "entry_source_file": entry_bar.source_file,
            "entry_delay_sec": entry_delay_ms / 1000.0,
        }
    )
    if entry_delay_ms > BAR_MS:
        output["replay_status"] = "ENTRY_DATA_GAP"
        return output
    for horizon in horizons:
        end_index = entry_index + horizon - 1
        prefix = f"h{horizon}"
        if end_index >= len(bars):
            output[f"{prefix}_status"] = "INSUFFICIENT_FORWARD_BARS"
            continue
        window = bars[entry_index : end_index + 1]
        if any(current.close_ts_ms - previous.close_ts_ms != BAR_MS for previous, current in zip(window, window[1:])):
            output[f"{prefix}_status"] = "DATA_GAP"
            continue
        exit_bar = window[-1]
        gross = side_return(row["side"], entry, exit_bar.close)
        if row["side"] == "BUY":
            mfe = max(bar.high / entry - 1.0 for bar in window)
            mae = min(bar.low / entry - 1.0 for bar in window)
        else:
            mfe = max(entry / bar.low - 1.0 for bar in window)
            mae = min(entry / bar.high - 1.0 for bar in window)
        output.update(
            {
                f"{prefix}_status": "OK",
                f"{prefix}_exit_ts_ms": exit_bar.close_ts_ms,
                f"{prefix}_exit_price": exit_bar.close,
                f"{prefix}_gross_bps": gross * 10_000.0,
                f"{prefix}_net_bps": gross * 10_000.0 - cost_bps,
                f"{prefix}_mfe_bps": mfe * 10_000.0,
                f"{prefix}_mae_bps": mae * 10_000.0,
            }
        )
    return output


def assign_episodes(rows: list[dict[str, Any]], episode_gap_min: int) -> None:
    last_seen: dict[tuple[str, str, str, str], tuple[int, int]] = {}
    next_id = 0
    gap_ms = episode_gap_min * 60_000
    for row in sorted(rows, key=lambda item: item["timestamp_ms"]):
        key = (row["symbol"], row["side"], row["strategy_id"], row["nrr_code"])
        previous = last_seen.get(key)
        if previous is None or row["timestamp_ms"] - previous[0] > gap_ms:
            next_id += 1
            episode_id = next_id
        else:
            episode_id = previous[1]
        row["episode_id"] = episode_id
        last_seen[key] = (row["timestamp_ms"], episode_id)


def bootstrap_ci(values: list[float], seed: int, samples: int = 2000) -> tuple[float | None, float | None]:
    if len(values) < 2:
        return None, None
    rng = random.Random(seed)
    estimates = sorted(mean(rng.choices(values, k=len(values))) for _ in range(samples))
    return estimates[int(samples * 0.025)], estimates[min(samples - 1, int(samples * 0.975))]


def summarize(rows: list[dict[str, Any]], group_fields: tuple[str, ...], horizons: tuple[int, ...], episode_level: bool) -> list[dict[str, Any]]:
    source = rows
    if episode_level:
        first_by_episode: dict[int, dict[str, Any]] = {}
        for row in sorted(rows, key=lambda item: item["timestamp_ms"]):
            first_by_episode.setdefault(row["episode_id"], row)
        source = list(first_by_episode.values())
    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in source:
        groups[tuple(row.get(field) for field in group_fields)].append(row)
    output: list[dict[str, Any]] = []
    for group_key, group_rows in sorted(groups.items(), key=lambda item: tuple(str(value) for value in item[0])):
        summary = {field: value for field, value in zip(group_fields, group_key)}
        summary.update({"level": "episode" if episode_level else "raw", "rows": len(group_rows)})
        for horizon in horizons:
            key = f"h{horizon}_net_bps"
            values = [float(row[key]) for row in group_rows if row.get(f"h{horizon}_status") == "OK" and row.get(key) is not None]
            mfe_values = [float(row[f"h{horizon}_mfe_bps"]) for row in group_rows if row.get(f"h{horizon}_status") == "OK"]
            mae_values = [float(row[f"h{horizon}_mae_bps"]) for row in group_rows if row.get(f"h{horizon}_status") == "OK"]
            prefix = f"h{horizon}"
            summary[f"{prefix}_n"] = len(values)
            if not values:
                continue
            low, high = bootstrap_ci(values, seed=horizon * 100_003 + len(values))
            gains = sum(value for value in values if value > 0)
            losses = -sum(value for value in values if value < 0)
            summary.update(
                {
                    f"{prefix}_mean_net_bps": mean(values),
                    f"{prefix}_median_net_bps": median(values),
                    f"{prefix}_positive_rate_pct": sum(value > 0 for value in values) / len(values) * 100.0,
                    f"{prefix}_profit_factor": gains / losses if losses > 0 else None,
                    f"{prefix}_mean_mfe_bps": mean(mfe_values),
                    f"{prefix}_mean_mae_bps": mean(mae_values),
                    f"{prefix}_ci95_low_bps": low,
                    f"{prefix}_ci95_high_bps": high,
                }
            )
        output.append(summary)
    return output


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=True, sort_keys=True) + "\n")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = sorted({key for row in rows for key in row})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def build_report(summary: dict[str, Any], nrr_episode: list[dict[str, Any]], horizons: tuple[int, ...]) -> str:
    lines = [
        "# NRR Rejected 15m Horizon Audit",
        "",
        f"- Reject rows: {summary['reject_rows']}",
        f"- Replayed rows: {summary['replayed_rows']}",
        f"- Episodes: {summary['episodes']}",
        f"- Round-trip cost: {summary['cost_bps']} bps",
        f"- Horizons: {', '.join(str(value) for value in horizons)} x 15m",
        "- Entry contract: open of the first full 15m bar starting after the reject timestamp.",
        "",
        "## Episode-Level NRR Results",
        "",
    ]
    for row in nrr_episode:
        parts = [f"{row.get('nrr_code')}: episodes={row.get('rows')}"]
        for horizon in horizons:
            value = row.get(f"h{horizon}_mean_net_bps")
            count = row.get(f"h{horizon}_n", 0)
            if value is not None:
                parts.append(f"{horizon}b={value:+.2f}bps (n={count})")
        lines.append("- " + "; ".join(parts))
    lines.extend(
        [
            "",
            "## Interpretation Guardrails",
            "",
            "- Positive retrospective return does not prove executability or justify disabling a gate.",
            "- Episode-level results are primary because repeated intents inside one move are correlated.",
            "- Low-support buckets remain inconclusive until confidence intervals and day stability improve.",
        ]
    )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Causal 15-minute horizon audit for rejected NRR intents")
    parser.add_argument("--order-log", type=Path, default=DEFAULT_ORDER_LOG)
    parser.add_argument("--recorder-root", type=Path, default=DEFAULT_RECORDER_ROOT)
    parser.add_argument("--report-root", type=Path, default=DEFAULT_REPORT_ROOT)
    parser.add_argument("--cost-bps", type=float, default=10.0)
    parser.add_argument("--episode-gap-min", type=int, default=60)
    parser.add_argument("--horizons", default=",".join(str(value) for value in DEFAULT_HORIZONS))
    args = parser.parse_args(argv)
    horizons = tuple(sorted({int(value) for value in args.horizons.split(",") if int(value) > 0}))

    rejects, boots = load_rejects(args.order_log.resolve())
    bars_by_symbol, coverage = load_bars(args.recorder_root.resolve(), {row["symbol"] for row in rejects})
    outcomes = [replay_row(row, bars_by_symbol.get(row["symbol"], []), horizons, args.cost_bps) for row in rejects]
    assign_episodes(outcomes, args.episode_gap_min)

    summaries: dict[str, list[dict[str, Any]]] = {}
    for name, fields in {
        "by_nrr": ("nrr_code",),
        "by_symbol_nrr": ("symbol", "nrr_code"),
        "by_strategy_nrr": ("strategy_id", "nrr_code"),
        "by_regime_nrr": ("regime", "nrr_code"),
        "by_boot_nrr": ("boot_session", "nrr_code"),
    }.items():
        summaries[name] = summarize(outcomes, fields, horizons, episode_level=False) + summarize(outcomes, fields, horizons, episode_level=True)

    root = args.report_root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    write_jsonl(root / "counterfactual_outcomes.jsonl", outcomes)
    write_csv(root / "counterfactual_outcomes.csv", outcomes)
    write_json(root / "bar_coverage_900s.json", coverage)
    for name, rows in summaries.items():
        write_csv(root / f"summary_{name}.csv", rows)
        write_json(root / f"summary_{name}.json", rows)
    top_summary = {
        "order_log": args.order_log.resolve().as_posix(),
        "recorder_root": args.recorder_root.resolve().as_posix(),
        "reject_rows": len(rejects),
        "replayed_rows": sum(row.get("replay_status") == "REPLAYED" for row in outcomes),
        "episodes": len({row["episode_id"] for row in outcomes}),
        "boot_sessions": len(boots),
        "boot_timestamps_ms": boots,
        "cost_bps": args.cost_bps,
        "episode_gap_min": args.episode_gap_min,
        "horizons_15m_bars": horizons,
    }
    write_json(root / "summary.json", top_summary)
    nrr_episode = [row for row in summaries["by_nrr"] if row["level"] == "episode"]
    (root / "NRR_REJECTED_15M_HORIZON_AUDIT.md").write_text(build_report(top_summary, nrr_episode, horizons), encoding="utf-8")
    print(json.dumps(top_summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
