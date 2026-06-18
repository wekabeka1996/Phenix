#!/usr/bin/env python3
"""Chronological promotion audit for rejected NRR entry opportunities.

The tool is read-only. It replays each reject at the next complete 15m bar,
deduplicates correlated rejects into independent episodes, applies a 60/20/20
chronological split with a two-hour embargo, and evaluates 10/15 bps costs.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from apps.reference.telemetry.order_logger import iter_order_log_files
from tools.analysis.nrr_rejected_horizon_audit import (
    assign_episodes,
    integer,
    iso_utc,
    iter_jsonl,
    load_bars,
    number,
    replay_row,
    side_return,
)


DEFAULT_REPORT_ROOT = ROOT / "reports" / "profitability_recovery_replay"
DEFAULT_START = "2026-06-09T00:10:00+00:00"
DEFAULT_END = "2026-06-13T10:00:00+00:00"
DEFAULT_FORWARD_END = "2026-06-13T20:30:00+00:00"
HORIZONS = (1, 2, 4, 8)
COSTS_BPS = (10.0, 15.0)


def parse_utc(value: str) -> int:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return int(parsed.timestamp() * 1000)


def load_rejects(paths: list[Path], *, start_ms: int, end_ms: int) -> list[dict[str, Any]]:
    signal_geometry: dict[str, dict[str, Any]] = {}
    for path in paths:
        if not path.exists():
            continue
        for _, row in iter_jsonl(path):
            if row.get("event_type") != "STRATEGY_SIGNAL_PRODUCED":
                continue
            rid = str(row.get("rid") or "").strip()
            metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
            if rid:
                signal_geometry[rid] = {
                    "entry_price": number(row.get("price") or metadata.get("entry_price")),
                    "stop_price": number(row.get("stop_price") or metadata.get("stop_price")),
                    "target_price": number(row.get("target_price") or metadata.get("target_price")),
                }

    rows: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for path in paths:
        if not path.exists():
            continue
        for line_no, row in iter_jsonl(path):
            ts_ms = integer(row.get("timestamp"))
            nrr = str(row.get("nrr_code") or row.get("reason_code") or "").upper()
            if row.get("event_type") != "DECISION_INTENT_REJECTED":
                continue
            if ts_ms is None or not (start_ms <= ts_ms <= end_ms) or not nrr.startswith("NRR-"):
                continue
            symbol = str(row.get("symbol") or "").upper()
            side = str(row.get("side") or "").upper()
            strategy_id = str(row.get("strategy_id") or "unknown")
            if not symbol or side not in {"BUY", "SELL"}:
                continue
            key = (row.get("rid"), symbol, side, strategy_id, nrr, ts_ms)
            if key in seen:
                continue
            seen.add(key)
            metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
            low_vol = metadata.get("low_vol_cost_floor") \
                if isinstance(metadata.get("low_vol_cost_floor"), dict) else {}
            details = metadata.get("details") \
                if isinstance(metadata.get("details"), dict) else {}
            geometry = signal_geometry.get(str(row.get("rid") or ""), {})
            rows.append({
                "source_file": path.as_posix(),
                "source_line": line_no,
                "rid": row.get("rid"),
                "timestamp_ms": ts_ms,
                "timestamp_utc": iso_utc(ts_ms),
                "symbol": symbol,
                "side": side,
                "strategy_id": strategy_id,
                "nrr_code": nrr,
                "regime": str(row.get("regime") or "UNCERTAIN").upper(),
                "regime_confidence": number(row.get("regime_confidence")),
                "entry_price": number(
                    row.get("price") or metadata.get("entry_price")
                    or low_vol.get("entry_price") or details.get("entry_price")
                    or geometry.get("entry_price")
                ),
                "stop_price": number(
                    row.get("stop_price") or metadata.get("stop_price")
                    or low_vol.get("stop_price") or details.get("stop_price")
                    or geometry.get("stop_price")
                ),
                "target_price": number(
                    row.get("target_price") or metadata.get("target_price")
                    or low_vol.get("target_price") or details.get("target_price")
                    or geometry.get("target_price")
                ),
            })
    return sorted(rows, key=lambda item: item["timestamp_ms"])


def chronological_fold(
    ts_ms: int,
    *,
    start_ms: int,
    end_ms: int,
    embargo_ms: int,
    forward_end_ms: int | None = None,
) -> str:
    if ts_ms > end_ms:
        if forward_end_ms is not None and ts_ms <= forward_end_ms:
            return "post_forward"
        return "outside"
    span = end_ms - start_ms
    train_end = start_ms + int(span * 0.60)
    validation_end = start_ms + int(span * 0.80)
    if abs(ts_ms - train_end) < embargo_ms or abs(ts_ms - validation_end) < embargo_ms:
        return "embargo"
    if ts_ms < train_end:
        return "train"
    if ts_ms < validation_end:
        return "validation"
    return "forward"


def profit_factor(values: list[float]) -> float | None:
    gains = sum(value for value in values if value > 0.0)
    losses = abs(sum(value for value in values if value < 0.0))
    if losses == 0.0:
        return None if gains == 0.0 else float("inf")
    return gains / losses


def replay_tpsl(
    source: dict[str, Any],
    *,
    bars: list[Any],
    entry_ts_ms: int,
    entry_price: float,
    horizon_bars: int,
    cost_bps: float,
) -> dict[str, Any]:
    stop_price = number(source.get("stop_price"))
    target_price = number(source.get("target_price"))
    if stop_price is None or target_price is None:
        return {"tpsl_status": "GEOMETRY_UNAVAILABLE"}
    start_index = next(
        (index for index, bar in enumerate(bars) if bar.start_ts_ms == entry_ts_ms),
        None,
    )
    if start_index is None:
        return {"tpsl_status": "ENTRY_BAR_UNAVAILABLE"}
    window = bars[start_index:start_index + horizon_bars]
    if len(window) < horizon_bars:
        return {"tpsl_status": "INSUFFICIENT_FORWARD_BARS"}

    side = str(source.get("side") or "").upper()
    geometry_valid = (
        stop_price < entry_price < target_price
        if side == "BUY"
        else target_price < entry_price < stop_price
    )
    if not geometry_valid:
        return {"tpsl_status": "GEOMETRY_INVALID_AT_REPLAY_ENTRY"}
    for bar in window:
        if side == "BUY":
            target_hit = bar.high >= target_price
            stop_hit = bar.low <= stop_price
        else:
            target_hit = bar.low <= target_price
            stop_hit = bar.high >= stop_price
        if target_hit and stop_hit:
            exit_price = stop_price
            gross_bps = side_return(side, entry_price, exit_price) * 10_000.0
            return {
                "tpsl_status": "AMBIGUOUS_BOTH_TOUCHED_STOP_ASSUMED",
                "tpsl_exit_ts_ms": bar.close_ts_ms,
                "tpsl_exit_price": exit_price,
                "tpsl_gross_bps": gross_bps,
                "tpsl_net_bps": gross_bps - cost_bps,
            }
        if target_hit or stop_hit:
            exit_price = target_price if target_hit else stop_price
            gross_bps = side_return(side, entry_price, exit_price) * 10_000.0
            return {
                "tpsl_status": "TP_HIT" if target_hit else "SL_HIT",
                "tpsl_exit_ts_ms": bar.close_ts_ms,
                "tpsl_exit_price": exit_price,
                "tpsl_gross_bps": gross_bps,
                "tpsl_net_bps": gross_bps - cost_bps,
            }

    exit_bar = window[-1]
    gross_bps = side_return(side, entry_price, exit_bar.close) * 10_000.0
    return {
        "tpsl_status": "OPEN_AT_HORIZON",
        "tpsl_exit_ts_ms": exit_bar.close_ts_ms,
        "tpsl_exit_price": exit_bar.close,
        "tpsl_gross_bps": gross_bps,
        "tpsl_net_bps": gross_bps - cost_bps,
    }


def aggregate(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    keys = ("strategy_id", "symbol", "regime", "side", "nrr_code", "cost_bps", "horizon_bars", "fold")
    for row in rows:
        groups[tuple(row.get(key) for key in keys)].append(row)
    output: list[dict[str, Any]] = []
    for group_key, group_rows in sorted(groups.items(), key=lambda item: tuple(str(x) for x in item[0])):
        values = [float(row["net_bps"]) for row in group_rows]
        gross = [float(row["gross_bps"]) for row in group_rows]
        by_day: dict[str, float] = defaultdict(float)
        for row in group_rows:
            by_day[str(row["entry_utc"])[:10]] += float(row["net_bps"])
        positive_days = [value for value in by_day.values() if value > 0]
        gross_positive = sum(value for value in gross if value > 0)
        gross_positive_episodes = sum(value > 0 for value in gross)
        tpsl_values = [
            float(row["tpsl_net_bps"])
            for row in group_rows
            if row.get("tpsl_net_bps") is not None
        ]
        output.append({
            **dict(zip(keys, group_key)),
            "episodes": len(group_rows),
            "market_days": len(by_day),
            "market_dates": ",".join(sorted(by_day)),
            "daily_net_bps": dict(sorted(by_day.items())),
            "mean_net_bps": mean(values),
            "profit_factor": profit_factor(values),
            "win_rate": sum(value > 0 for value in values) / len(values),
            "max_profit_day_share": (
                max(positive_days) / sum(positive_days) if positive_days else None),
            "fee_gross_ratio": (
                float(group_key[5]) * gross_positive_episodes / gross_positive
                if gross_positive > 0 else None),
            "gross_positive_bps": gross_positive,
            "fee_bps_total": float(group_key[5]) * len(group_rows),
            "fee_bps_gross_positive": float(group_key[5]) * gross_positive_episodes,
            "tpsl_episodes": len(tpsl_values),
            "mean_tpsl_net_bps": mean(tpsl_values) if tpsl_values else None,
            "tpsl_profit_factor": profit_factor(tpsl_values) if tpsl_values else None,
        })
    return output


def promotion_candidates(summary: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cohort_fields = ("strategy_id", "symbol", "regime", "side", "nrr_code", "horizon_bars")
    grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in summary:
        grouped[tuple(row[field] for field in cohort_fields)].append(row)
    candidates: list[dict[str, Any]] = []
    for cohort, rows in sorted(grouped.items(), key=lambda item: tuple(str(x) for x in item[0])):
        reasons: list[str] = []
        by_cost_fold = {(row["cost_bps"], row["fold"]): row for row in rows}
        episode_count = sum(
            row["episodes"] for row in rows
            if row["cost_bps"] == COSTS_BPS[0])
        market_days = len({
            day
            for row in rows if row["cost_bps"] == COSTS_BPS[0]
            for day in str(row.get("market_dates") or "").split(",")
            if day
        })
        if episode_count < 30:
            reasons.append("independent_episodes<30")
        if market_days < 3:
            reasons.append("market_days<3")
        for cost in COSTS_BPS:
            fold_rows = [by_cost_fold.get((cost, fold)) for fold in ("train", "validation", "forward")]
            if any(row is None for row in fold_rows):
                reasons.append(f"missing_fold_at_{cost:g}bps")
                continue
            assert all(row is not None for row in fold_rows)
            typed_rows = [row for row in fold_rows if row is not None]
            if typed_rows[1]["mean_net_bps"] <= 0 or typed_rows[2]["mean_net_bps"] <= 0:
                reasons.append(f"validation_or_forward_nonpositive_at_{cost:g}bps")
            if sum(row["mean_net_bps"] > 0 for row in typed_rows) < 2:
                reasons.append(f"positive_folds<2_at_{cost:g}bps")
            post_forward = by_cost_fold.get((cost, "post_forward"))
            if post_forward is None:
                reasons.append(f"missing_post_forward_at_{cost:g}bps")
            elif post_forward["mean_net_bps"] <= 0:
                reasons.append(f"post_forward_nonpositive_at_{cost:g}bps")
            oos_values = [*typed_rows[1:], *([post_forward] if post_forward else [])]
            if any((row["profit_factor"] or 0.0) < 1.15 for row in oos_values):
                reasons.append(f"oos_profit_factor<1.15_at_{cost:g}bps")
            if cohort[1] == "ETHUSDT" and int(cohort[5]) == 4:
                if any(int(row.get("tpsl_episodes") or 0) == 0 for row in oos_values):
                    reasons.append(f"eth_1h_tpsl_missing_oos_at_{cost:g}bps")
                elif any(float(row.get("mean_tpsl_net_bps") or 0.0) <= 0.0 for row in oos_values):
                    reasons.append(f"eth_1h_tpsl_nonpositive_oos_at_{cost:g}bps")
                if any((row.get("tpsl_profit_factor") or 0.0) < 1.15 for row in oos_values):
                    reasons.append(f"eth_1h_tpsl_profit_factor<1.15_at_{cost:g}bps")
            all_cost_rows = [row for row in rows if row["cost_bps"] == cost]
            by_day: dict[str, float] = defaultdict(float)
            for row in all_cost_rows:
                for day, value in (row.get("daily_net_bps") or {}).items():
                    by_day[str(day)] += float(value)
            positive_days = [value for value in by_day.values() if value > 0]
            max_day_share = (
                max(positive_days) / sum(positive_days) if positive_days else 1.0)
            if max_day_share > 0.50:
                reasons.append(f"profit_concentration>50pct_at_{cost:g}bps")
            gross_positive = sum(float(row.get("gross_positive_bps") or 0.0) for row in all_cost_rows)
            fee_total = sum(
                float(row.get("fee_bps_gross_positive") or 0.0)
                for row in all_cost_rows
            )
            if gross_positive <= 0 or fee_total / gross_positive > 0.50:
                reasons.append(f"fee_gross_ratio>50pct_at_{cost:g}bps")
        candidates.append({
            **dict(zip(cohort_fields, cohort)),
            "eligible_for_testnet": not reasons,
            "blockers": sorted(set(reasons)),
        })
    return candidates


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = sorted({key for row in rows for key in row})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--order-log", type=Path, default=ROOT / "logs" / "order_log_v1.jsonl")
    parser.add_argument("--recorder-root", type=Path, default=ROOT / "data" / "recorder")
    parser.add_argument("--report-root", type=Path, default=DEFAULT_REPORT_ROOT)
    parser.add_argument("--start", default=DEFAULT_START)
    parser.add_argument("--end", default=DEFAULT_END)
    parser.add_argument("--forward-end", default=DEFAULT_FORWARD_END)
    parser.add_argument("--embargo-hours", type=float, default=2.0)
    parser.add_argument("--episode-gap-min", type=int, default=60)
    args = parser.parse_args()

    start_ms, end_ms = parse_utc(args.start), parse_utc(args.end)
    forward_end_ms = parse_utc(args.forward_end)
    if forward_end_ms < end_ms:
        raise ValueError("forward-end must be greater than or equal to end")
    rejects = load_rejects(
        iter_order_log_files(args.order_log), start_ms=start_ms, end_ms=forward_end_ms)
    assign_episodes(rejects, args.episode_gap_min)
    first_by_episode: dict[int, dict[str, Any]] = {}
    for row in rejects:
        first_by_episode.setdefault(int(row["episode_id"]), row)
    episodes = list(first_by_episode.values())
    bars_by_symbol, coverage = load_bars(
        args.recorder_root, {row["symbol"] for row in episodes})
    replayed: list[dict[str, Any]] = []
    embargo_ms = int(args.embargo_hours * 3_600_000)
    for cost in COSTS_BPS:
        for source in episodes:
            replay = replay_row(source, bars_by_symbol.get(source["symbol"], []), HORIZONS, cost)
            if replay.get("replay_status") != "REPLAYED":
                continue
            # Split on the executable next-bar entry, not the earlier reject.
            # This prevents a reject immediately before a boundary from leaking
            # its realized trade into the preceding fold.
            fold = chronological_fold(
                int(replay["entry_ts_ms"]), start_ms=start_ms, end_ms=end_ms,
                embargo_ms=embargo_ms, forward_end_ms=forward_end_ms)
            if fold in {"embargo", "outside"}:
                continue
            for horizon in HORIZONS:
                if replay.get(f"h{horizon}_status") != "OK":
                    continue
                tpsl = replay_tpsl(
                    source,
                    bars=bars_by_symbol.get(source["symbol"], []),
                    entry_ts_ms=int(replay["entry_ts_ms"]),
                    entry_price=float(replay["entry_price"]),
                    horizon_bars=horizon,
                    cost_bps=cost,
                )
                replayed.append({
                    **source,
                    "fold": fold,
                    "cost_bps": cost,
                    "horizon_bars": horizon,
                    "horizon_min": horizon * 15,
                    "entry_ts_ms": replay["entry_ts_ms"],
                    "entry_utc": replay["entry_utc"],
                    "gross_bps": replay[f"h{horizon}_gross_bps"],
                    "net_bps": replay[f"h{horizon}_net_bps"],
                    "mfe_bps": replay[f"h{horizon}_mfe_bps"],
                    "mae_bps": replay[f"h{horizon}_mae_bps"],
                    "tpsl_available": source.get("stop_price") is not None
                    and source.get("target_price") is not None,
                    **tpsl,
                })

    summary = aggregate(replayed)
    candidates = promotion_candidates(summary)
    report_root = args.report_root
    report_root.mkdir(parents=True, exist_ok=True)
    write_csv(report_root / "episode_replay.csv", replayed)
    write_csv(
        report_root / "eth_1h_tpsl_replay.csv",
        [
            row for row in replayed
            if row.get("symbol") == "ETHUSDT"
            and row.get("horizon_min") == 60
            and row.get("tpsl_available")
        ],
    )
    write_csv(report_root / "chronological_cohort_summary.csv", summary)
    write_csv(report_root / "promotion_candidates.csv", candidates)
    manifest = {
        "period": {"start": args.start, "end": args.end},
        "post_forward_window": {"start": args.end, "end": args.forward_end},
        "split": "60/20/20 + post_forward",
        "embargo_hours": args.embargo_hours,
        "costs_bps": list(COSTS_BPS),
        "horizons_min": [15, 30, 60, 120],
        "reject_rows": len(rejects),
        "independent_episodes": len(episodes),
        "replay_rows": len(replayed),
        "tpsl_coverage_episodes": sum(
            row.get("stop_price") is not None and row.get("target_price") is not None
            for row in episodes),
        "eligible_candidates": sum(row["eligible_for_testnet"] for row in candidates),
        "candles": {
            symbol: {
                key: details.get(key)
                for key in (
                    "bar_count", "first_close_ts_ms", "last_close_ts_ms",
                    "gap_count", "missing_bars")
            }
            for symbol, details in coverage.items()
        },
        "acceptance": {
            "net_positive_validation_and_forward_at_10_15_bps": True,
            "profit_factor_min": 1.15,
            "positive_folds_min": 2,
            "independent_episodes_min": 30,
            "market_days_min": 3,
            "max_profit_day_share": 0.50,
            "max_fee_gross_ratio": 0.50,
        },
    }
    (report_root / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
