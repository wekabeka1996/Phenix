from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from apps.reference.adapters.binance_adapter import BinanceAdapter
from apps.reference.shared.data_primitives.market_bar_contract import (
    RECORDER_STABLE_COLUMNS,
    build_stable_recorder_row,
    read_named_csv_rows,
)
from apps.reference.shared.data_primitives.ohlc_validator import validate_ohlc


TF_INTERVAL_MAP = {
    60: "1m",
    180: "3m",
    300: "5m",
    900: "15m",
    1800: "30m",
    3600: "1h",
    14400: "4h",
    86400: "1d",
}

DAY_MS = 86_400_000


@dataclass(frozen=True)
class FileInventory:
    path: Path
    symbol: str
    tf_sec: int
    date_str: str
    total_rows: int
    invalid_rows: int
    bad_lines: int


def _parse_date_folder(path: Path) -> str:
    return path.parent.name


def _inventory_file(path: Path) -> FileInventory:
    symbol, tf_part = path.stem.split("_", 1)
    tf_sec = int(tf_part)
    rows, accounting = read_named_csv_rows(
        path,
        requested_columns=("open", "high", "low", "close"),
    )
    invalid_rows = 0
    for row in rows:
        valid, _ = validate_ohlc(
            row.get("open"),
            row.get("high"),
            row.get("low"),
            row.get("close"),
        )
        if not valid:
            invalid_rows += 1
    return FileInventory(
        path=path,
        symbol=symbol,
        tf_sec=tf_sec,
        date_str=_parse_date_folder(path),
        total_rows=int(accounting.get("rows_returned", 0)),
        invalid_rows=invalid_rows,
        bad_lines=int(accounting.get("bad_lines", 0)),
    )


def _iter_target_files(recorder_root: Path, symbols: list[str] | None, dates: list[str] | None) -> list[Path]:
    out: list[Path] = []
    for date_dir in sorted(recorder_root.iterdir()):
        if not date_dir.is_dir():
            continue
        if dates and date_dir.name not in set(dates):
            continue
        for csv_path in sorted(date_dir.glob("*.csv")):
            symbol = csv_path.stem.split("_", 1)[0]
            if symbols and symbol not in set(symbols):
                continue
            out.append(csv_path)
    return out


def _date_window_ms(date_str: str) -> tuple[int, int]:
    start = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    end = start + timedelta(days=1) - timedelta(milliseconds=1)
    return int(start.timestamp() * 1000), int(end.timestamp() * 1000)


def _interval_ms(tf_sec: int) -> int:
    return int(tf_sec) * 1000


def _validate_kline_continuity(
    klines: list[list[Any]],
    *,
    tf_sec: int,
    start_ms: int,
) -> tuple[bool, dict[str, Any]]:
    interval_ms = _interval_ms(tf_sec)
    expected_rows = DAY_MS // interval_ms
    open_times: list[int] = []
    for row in klines:
        if not row:
            continue
        open_times.append(int(row[0]))
    if not open_times:
        return False, {
            "reason": "NO_KLINES",
            "expected_rows": expected_rows,
            "actual_rows": 0,
        }
    sorted_times = sorted(open_times)
    duplicates = len(sorted_times) - len(set(sorted_times))
    gaps = 0
    overlaps = 0
    for prev_open, next_open in zip(sorted_times, sorted_times[1:]):
        delta = next_open - prev_open
        if delta == interval_ms:
            continue
        if delta < interval_ms:
            overlaps += 1
        else:
            gaps += 1
    expected_last_open = int(start_ms) + (expected_rows - 1) * interval_ms
    summary = {
        "reason": "OK",
        "expected_rows": expected_rows,
        "actual_rows": len(sorted_times),
        "duplicates": duplicates,
        "gaps": gaps,
        "overlaps": overlaps,
        "first_open_ms": sorted_times[0],
        "last_open_ms": sorted_times[-1],
        "expected_first_open_ms": int(start_ms),
        "expected_last_open_ms": expected_last_open,
    }
    ok = (
        duplicates == 0
        and gaps == 0
        and overlaps == 0
        and len(sorted_times) == expected_rows
        and sorted_times[0] == int(start_ms)
        and sorted_times[-1] == expected_last_open
    )
    if not ok:
        summary["reason"] = "NON_CONTIGUOUS_KLINES"
    return ok, summary


async def _fetch_klines_for_day(
    *,
    symbol: str,
    tf_sec: int,
    date_str: str,
    base_url: str,
) -> list[list[Any]]:
    interval = TF_INTERVAL_MAP.get(tf_sec)
    if interval is None:
        raise ValueError(f"Unsupported tf_sec for repair: {tf_sec}")
    start_ms, end_ms = _date_window_ms(date_str)
    adapter = BinanceAdapter(api_key="", api_secret="", base_url=base_url)
    try:
        all_rows: list[list[Any]] = []
        next_start = start_ms
        interval_ms = _interval_ms(tf_sec)
        while next_start <= end_ms:
            batch = await adapter.get_klines(
                symbol,
                interval,
                limit=1500,
                start_ms=next_start,
                end_ms=end_ms,
            )
            if not batch:
                break
            all_rows.extend(batch)
            last_open_ms = int(batch[-1][0])
            if last_open_ms >= end_ms or len(batch) < 1500:
                break
            next_start = last_open_ms + interval_ms
        return all_rows
    finally:
        await adapter.aclose()


def _repair_rows_from_klines(symbol: str, tf_sec: int, klines: list[list[Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for raw in klines:
        close_ts_ms = int(raw[6])
        row, _ = build_stable_recorder_row(
            {
                "timestamp": close_ts_ms,
                "datetime": datetime.fromtimestamp(close_ts_ms / 1000.0, tz=timezone.utc).isoformat(),
                "symbol": symbol,
                "tf_sec": tf_sec,
                "open": raw[1],
                "high": raw[2],
                "low": raw[3],
                "close": raw[4],
                "volume": raw[5],
                "trade_count": raw[8],
                "source_mode": "synthetic_repair",
                "close_boundary_ts_ms": close_ts_ms,
                "ready": False,
                "not_ready_reasons": "repaired_ohlcv_only",
                "regime": "",
                "regime_conf": "",
                "regime_join_status": "REPAIRED_OHLC_ONLY",
                "regime_join_mode": "repair_backfill",
            }
        )
        rows.append(row)
    return rows


def _validate_rows(rows: list[dict[str, Any]]) -> tuple[bool, int]:
    invalid = 0
    for row in rows:
        valid, _ = validate_ohlc(row["open"], row["high"], row["low"], row["close"])
        if not valid:
            invalid += 1
    return invalid == 0, invalid


def _write_rows_atomic(target_path: Path, rows: list[dict[str, Any]], backup_root: Path) -> Path:
    backup_root.mkdir(parents=True, exist_ok=True)
    backup_path = backup_root / f"{target_path.name}.bak"
    temp_path = target_path.with_suffix(".repair.tmp")
    if target_path.exists():
        backup_path.write_bytes(target_path.read_bytes())
    with temp_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(RECORDER_STABLE_COLUMNS), extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    os.replace(temp_path, target_path)
    return backup_path


def _write_marker(target_path: Path, payload: dict[str, Any]) -> None:
    marker_path = target_path.with_suffix(target_path.suffix + ".repair.json")
    marker_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


async def _run(args: argparse.Namespace) -> int:
    recorder_root = Path(args.recorder_root).resolve()
    backup_root = Path(args.backup_root).resolve()
    files = _iter_target_files(
        recorder_root,
        symbols=args.symbols,
        dates=args.dates,
    )
    inventories = [_inventory_file(path) for path in files]
    flagged = [item for item in inventories if item.invalid_rows > 0 or item.bad_lines > 0]
    summary = {
        "recorder_root": str(recorder_root),
        "files_scanned": len(inventories),
        "files_flagged": len(flagged),
        "invalid_rows": sum(item.invalid_rows for item in inventories),
        "bad_lines": sum(item.bad_lines for item in inventories),
        "apply": bool(args.apply),
        "files": [
            {
                "path": str(item.path),
                "symbol": item.symbol,
                "tf_sec": item.tf_sec,
                "date": item.date_str,
                "total_rows": item.total_rows,
                "invalid_rows": item.invalid_rows,
                "bad_lines": item.bad_lines,
            }
            for item in flagged
        ],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if not args.apply:
        return 0

    for item in flagged:
        klines = await _fetch_klines_for_day(
            symbol=item.symbol,
            tf_sec=item.tf_sec,
            date_str=item.date_str,
            base_url=args.base_url,
        )
        start_ms, _ = _date_window_ms(item.date_str)
        continuity_ok, continuity = _validate_kline_continuity(
            klines,
            tf_sec=item.tf_sec,
            start_ms=start_ms,
        )
        if not continuity_ok:
            raise RuntimeError(
                f"Repair continuity failed for {item.path}: {json.dumps(continuity, ensure_ascii=False)}"
            )
        repaired_rows = _repair_rows_from_klines(item.symbol, item.tf_sec, klines)
        valid, invalid_count = _validate_rows(repaired_rows)
        if not valid:
            raise RuntimeError(
                f"Repair validation failed for {item.path} invalid_rows={invalid_count}"
            )
        backup_path = _write_rows_atomic(
            item.path,
            repaired_rows,
            backup_root / item.date_str,
        )
        _write_marker(
            item.path,
            {
                "repaired_at_utc": datetime.now(timezone.utc).isoformat(),
                "symbol": item.symbol,
                "tf_sec": item.tf_sec,
                "date": item.date_str,
                "source": "binance_public_klines",
                "base_url": args.base_url,
                "backup_path": str(backup_path),
                "repaired_rows": len(repaired_rows),
                "continuity": continuity,
            },
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--recorder-root", default="data/recorder")
    parser.add_argument("--backup-root", default="data/recorder_repairs/backups")
    parser.add_argument("--base-url", default="https://fapi.binance.com")
    parser.add_argument("--symbols", nargs="*", default=None)
    parser.add_argument("--dates", nargs="*", default=None)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
