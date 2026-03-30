#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from bisect import bisect_left
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.forensics.log_forensics_cancel_audit import (
    SourceStats,
    apply_execution_events,
    parse_execution_logs,
    parse_feature_logs,
    parse_order_log,
    rotated_log_files,
    update_order_terminal_status,
)


def any_touch(features_by_symbol, symbol: str, side: str, limit_price: float, start_ms: int, end_ms: int | None):
    series = features_by_symbol.get(symbol, [])
    if not series:
        return None
    ts_list = [item.ts_ms for item in series]
    idx = bisect_left(ts_list, start_ms)
    while idx < len(series):
        sample = series[idx]
        if end_ms is not None and sample.ts_ms > end_ms:
            break
        if side == "BUY" and sample.price <= limit_price:
            return {"ts_ms": sample.ts_ms, "price": sample.price}
        if side == "SELL" and sample.price >= limit_price:
            return {"ts_ms": sample.ts_ms, "price": sample.price}
        idx += 1
    return None


def main() -> int:
    repo_root = Path.cwd()
    logs_dir = repo_root / "logs"
    stats: dict[str, SourceStats] = {}

    records, _, _ = parse_order_log(logs_dir / "order_log_v1.jsonl", stats)
    exec_logs = rotated_log_files(logs_dir, "domain_execution_position.log")
    fills, timeouts, _, adv_logs = parse_execution_logs(exec_logs, stats)
    apply_execution_events(records, fills, timeouts, adv_logs)
    update_order_terminal_status(records)
    feature_logs = rotated_log_files(logs_dir, "domain_feature_engineering.log")
    features = parse_feature_logs(feature_logs, stats)

    placed_by_symbol = {}
    for record in records.values():
        placed_by_symbol.setdefault(record.symbol, []).append(record)
    for arr in placed_by_symbol.values():
        arr.sort(key=lambda item: item.placed_at_ms)

    same_side_supersedes = []
    for record in sorted(records.values(), key=lambda item: item.canceled_at_ms or 0):
        if record.cancel_reason != "CANCEL_SUPERSEDED" or record.canceled_at_ms is None:
            continue
        newer = [
            candidate
            for candidate in placed_by_symbol.get(record.symbol, [])
            if candidate.placed_at_ms > record.canceled_at_ms
            and candidate.placed_at_ms - record.canceled_at_ms <= 120_000
        ]
        if not newer:
            continue
        replacement = newer[0]
        if replacement.side != record.side:
            continue
        delta_bps = abs(replacement.limit_price - record.limit_price) / record.limit_price * 10_000.0
        old_touch = any_touch(
            features,
            record.symbol,
            record.side,
            record.limit_price,
            record.canceled_at_ms,
            replacement.filled_at_ms or (record.canceled_at_ms + 30 * 60_000),
        )
        new_touch = any_touch(
            features,
            replacement.symbol,
            replacement.side,
            replacement.limit_price,
            replacement.placed_at_ms,
            replacement.filled_at_ms or (replacement.placed_at_ms + 30 * 60_000),
        )
        same_side_supersedes.append(
            {
                "symbol": record.symbol,
                "old_order_id": record.order_id,
                "new_order_id": replacement.order_id,
                "side": record.side,
                "delta_bps": round(delta_bps, 2),
                "new_terminal_status": replacement.terminal_status,
                "new_fill_age_sec": None
                if replacement.filled_at_ms is None
                else round((replacement.filled_at_ms - replacement.placed_at_ms) / 1000.0, 2),
                "old_touch_before_new_terminal": old_touch is not None,
                "new_touch_before_terminal": new_touch is not None,
            }
        )

    threshold_summary = []
    for threshold_bps in (5.0, 10.0, 15.0):
        candidates = [row for row in same_side_supersedes if row["delta_bps"] <= threshold_bps]
        threshold_summary.append(
            {
                "threshold_bps": threshold_bps,
                "candidate_count": len(candidates),
                "old_touch_before_new_terminal_count": sum(
                    1 for row in candidates if row["old_touch_before_new_terminal"]
                ),
                "new_filled_count": sum(1 for row in candidates if row["new_terminal_status"] == "FILLED"),
            }
        )

    ttl_extension = []
    ttl_orders = [
        record for record in records.values() if record.cancel_reason == "CANCEL_TTL_EXPIRED" and record.canceled_at_ms
    ]
    for horizon_min in (10, 20, 30):
        touch_count = 0
        for record in ttl_orders:
            touch = any_touch(
                features,
                record.symbol,
                record.side,
                record.limit_price,
                record.canceled_at_ms,
                record.canceled_at_ms + horizon_min * 60_000,
            )
            if touch is not None:
                touch_count += 1
        ttl_extension.append(
            {
                "extra_ttl_min": horizon_min,
                "touched_limit_count": touch_count,
                "total_timeout_orders": len(ttl_orders),
            }
        )

    print(
        json.dumps(
            {
                "same_side_supersedes": same_side_supersedes,
                "same_side_threshold_summary": threshold_summary,
                "ttl_extension_touch_summary": ttl_extension,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
