#!/usr/bin/env python3
"""
Витягує всі значення Cached equity_free_usdt з логів aurora_core.log*
Пише результати в файл і виводить статистику
"""
from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import datetime
import re
from pathlib import Path
from statistics import mean, stdev, median


TS_FMT = "%Y-%m-%d %H:%M:%S,%f"


@dataclass(frozen=True)
class EquityPoint:
    ts: datetime
    ts_raw: str
    value: float


def _default_logs_dir() -> Path:
    # tools/ -> repo root
    return Path(__file__).resolve().parents[1] / "logs"


def _numeric_rotated_logs(log_dir: Path, base_name: str) -> list[Path]:
    out: list[tuple[int, Path]] = []
    for p in log_dir.glob(f"{base_name}.*"):
        suffix = p.name.split(".")[-1]
        if suffix.isdigit():
            out.append((int(suffix), p))
    out.sort(key=lambda t: t[0])
    return [p for _, p in out]


def _iter_log_files(log_dir: Path) -> list[Path]:
    base = log_dir / "aurora_core.log"
    files: list[Path] = []
    if base.exists():
        files.append(base)
    files.extend(_numeric_rotated_logs(log_dir, "aurora_core.log"))
    return files


def _parse_ts(line: str) -> tuple[datetime, str] | None:
    m = re.match(r"(\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}:\d{2},\d+)", line)
    if not m:
        return None
    raw = m.group(1)
    try:
        return datetime.strptime(raw, TS_FMT), raw
    except ValueError:
        return None


def _dedup_points(points: list[EquityPoint]) -> list[EquityPoint]:
    """Keep points in time order, dropping pure duplicates and compressing unchanged runs."""
    if not points:
        return []

    out: list[EquityPoint] = []
    last: EquityPoint | None = None
    for p in points:
        if last is None:
            out.append(p)
            last = p
            continue

        # exact duplicate (same timestamp + same value)
        if p.ts == last.ts and p.value == last.value:
            continue

        # unchanged value run (keep only first occurrence)
        if p.value == last.value:
            continue

        out.append(p)
        last = p

    return out

def extract_equity_free_usdt() -> None:
    ap = argparse.ArgumentParser(
        description="Extract time-ordered equity_free_usdt points from aurora_core.log* with dedup."
    )
    ap.add_argument(
        "--logs-dir",
        default=str(_default_logs_dir()),
        help="Path to logs directory (default: repo_root/logs)",
    )
    ap.add_argument(
        "--output",
        default=None,
        help="Output CSV path (default: <logs-dir>/equity_free_usdt_values.txt)",
    )
    ap.add_argument(
        "--keep-all",
        action="store_true",
        help="Do not deduplicate; keep every matched line (still sorted by timestamp).",
    )
    args = ap.parse_args()

    log_dir = Path(args.logs_dir)
    log_files = _iter_log_files(log_dir)
    print(f"📋 Шукаю файли ({len(log_files)}): {[str(p) for p in log_files]}\n")

    pattern = re.compile(r"Cached equity_free_usdt:\s+([\d.]+)")
    raw_points: list[EquityPoint] = []
    scanned_lines = 0
    matched_lines = 0

    for log_file in log_files:
        try:
            with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    scanned_lines += 1
                    m = pattern.search(line)
                    if not m:
                        continue
                    ts_parsed = _parse_ts(line)
                    if not ts_parsed:
                        continue
                    ts, ts_raw = ts_parsed
                    try:
                        value = float(m.group(1))
                    except ValueError:
                        continue
                    matched_lines += 1
                    raw_points.append(EquityPoint(ts=ts, ts_raw=ts_raw, value=value))
        except Exception as e:
            print(f"❌ Помилка при читанні {log_file}: {e}")

    if not raw_points:
        print("❌ Не знайдено значень!")
        return

    raw_points.sort(key=lambda p: p.ts)
    points = raw_points if args.keep_all else _dedup_points(raw_points)

    output_file = Path(args.output) if args.output else (log_dir / "equity_free_usdt_values.txt")
    with open(output_file, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["timestamp", "value"])
        for p in points:
            w.writerow([p.ts_raw, f"{p.value:.15g}"])

    values = [p.value for p in points]
    print(f"✅ Зчитано рядків: {scanned_lines}")
    print(f"✅ Матчів (raw):  {matched_lines}")
    if args.keep_all:
        print(f"✅ Точок (sorted): {len(points)}")
    else:
        print(f"✅ Точок (dedup):  {len(points)}")

    print(f"\n📊 СТАТИСТИКА (по записаним точкам):")
    print(f"   Мінімум:    {min(values):.10f}")
    print(f"   Максимум:   {max(values):.10f}")
    print(f"   Середнє:    {mean(values):.10f}")
    print(f"   Медіана:    {median(values):.10f}")
    if len(values) > 1:
        print(f"   Стд. відхилення: {stdev(values):.10f}")
    print(f"\n💾 Результати записані в: {output_file}")

if __name__ == "__main__":
    extract_equity_free_usdt()
