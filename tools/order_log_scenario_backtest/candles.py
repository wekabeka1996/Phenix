from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from tools.analysis.order_reconstruction_tp_sl_common import (
    resolve_recorder_roots,
    try_parse_timestamp_ms,
    to_float,
    write_csv,
)

from .models import CandleSeries, CanonicalEntry

DEFAULT_REPLAY_HORIZON_MS = 24 * 60 * 60 * 1000


@dataclass
class CandleCoverageResult:
    strict_1m_ok: bool
    required_windows: list[dict[str, Any]]
    resolved_recorder_roots: list[Path]


class CandleCoverageError(RuntimeError):
    def __init__(self, result: CandleCoverageResult) -> None:
        super().__init__("strict 1m candle coverage failed")
        self.result = result


def _scan_1m_files(recorder_roots: list[Path]) -> dict[str, list[Path]]:
    by_symbol: dict[str, list[Path]] = {}
    for recorder_root in recorder_roots:
        if not recorder_root.exists():
            continue
        for path in sorted(recorder_root.rglob("*_60.csv")):
            symbol = path.name.split("_", 1)[0]
            by_symbol.setdefault(symbol, []).append(path)
    return by_symbol


def _scan_file_bounds(path: Path) -> tuple[int | None, int | None]:
    first_ts = None
    last_ts = None
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            ts_ms = try_parse_timestamp_ms(row.get("timestamp"))
            if ts_ms is None:
                continue
            if first_ts is None:
                first_ts = ts_ms
            last_ts = ts_ms
    return first_ts, last_ts


def _required_horizon_end(entry: CanonicalEntry) -> int:
    return max(entry.entry_ts_ms + DEFAULT_REPLAY_HORIZON_MS, entry.actual_close_ts_ms or 0)


def _ceil_to_minute_close_ts(ts_ms: int) -> int:
    remainder = ts_ms % 60000
    if remainder == 59999:
        return ts_ms
    return ((ts_ms // 60000) + 1) * 60000 - 1


def preflight_1m_coverage(
    workspace_root: Path,
    entries: list[CanonicalEntry],
    report_root: Path,
    recorder_roots: Iterable[Path | str] | None,
    *,
    strict: bool,
) -> CandleCoverageResult:
    resolved_roots = resolve_recorder_roots(workspace_root, recorder_roots)
    files_by_symbol = _scan_1m_files(resolved_roots)
    required_windows: list[dict[str, Any]] = []
    strict_ok = True

    grouped: dict[str, list[CanonicalEntry]] = {}
    for entry in entries:
        grouped.setdefault(entry.symbol, []).append(entry)

    for symbol, symbol_entries in sorted(grouped.items()):
        required_start = min(_ceil_to_minute_close_ts(entry.entry_ts_ms) for entry in symbol_entries)
        required_end = max(_required_horizon_end(entry) for entry in symbol_entries)
        available_start = None
        available_end = None
        for path in files_by_symbol.get(symbol, []):
            file_start, file_end = _scan_file_bounds(path)
            if file_start is None or file_end is None:
                continue
            if available_start is None or file_start < available_start:
                available_start = file_start
            if available_end is None or file_end > available_end:
                available_end = file_end
        usable = (
            available_start is not None
            and available_end is not None
            and available_start <= required_start
            and available_end >= required_end
        )
        if strict and not usable:
            strict_ok = False
        required_windows.append(
            {
                "symbol": symbol,
                "required_start_ts_ms": required_start,
                "required_end_ts_ms": required_end,
                "available_start_ts_ms": available_start or "",
                "available_end_ts_ms": available_end or "",
                "usable": "true" if usable else "false",
            }
        )

    write_csv(
        report_root / "required_1m_candle_windows.csv",
        [
            "symbol",
            "required_start_ts_ms",
            "required_end_ts_ms",
            "available_start_ts_ms",
            "available_end_ts_ms",
            "usable",
        ],
        required_windows,
    )
    result = CandleCoverageResult(
        strict_1m_ok=strict_ok,
        required_windows=required_windows,
        resolved_recorder_roots=resolved_roots,
    )
    if strict and not strict_ok:
        raise CandleCoverageError(result)
    return result


def load_1m_candles(
    workspace_root: Path,
    recorder_roots: Iterable[Path | str] | None,
) -> dict[str, CandleSeries]:
    resolved_roots = resolve_recorder_roots(workspace_root, recorder_roots)
    by_symbol: dict[str, list[dict[str, Any]]] = {}
    for recorder_root in resolved_roots:
        if not recorder_root.exists():
            continue
        for path in sorted(recorder_root.rglob("*_60.csv")):
            symbol = path.name.split("_", 1)[0]
            rows = by_symbol.setdefault(symbol, [])
            with path.open("r", encoding="utf-8", errors="replace") as handle:
                reader = csv.DictReader(handle)
                for raw in reader:
                    ts_ms = try_parse_timestamp_ms(raw.get("timestamp"))
                    open_price = to_float(raw.get("open"))
                    high = to_float(raw.get("high"))
                    low = to_float(raw.get("low"))
                    close = to_float(raw.get("close"))
                    if (
                        ts_ms is None
                        or open_price is None
                        or high is None
                        or low is None
                        or close is None
                    ):
                        continue
                    rows.append(
                        {
                            "timestamp": ts_ms,
                            "open": open_price,
                            "high": high,
                            "low": low,
                            "close": close,
                        }
                    )
    result: dict[str, CandleSeries] = {}
    for symbol, rows in by_symbol.items():
        rows.sort(key=lambda item: item["timestamp"])
        result[symbol] = CandleSeries(
            symbol=symbol,
            rows=rows,
            timestamps=[int(row["timestamp"]) for row in rows],
        )
    return result
