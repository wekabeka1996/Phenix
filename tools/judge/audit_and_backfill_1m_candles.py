"""Judge 1m candle coverage audit + optional backfill (PKG-7).

Scans `logs/judge_experts/*.jsonl` for verdict ts_ms ranges per symbol, computes
required minute-aligned 1m candle coverage (last_verdict_ts + horizon*max_tf*1000),
indexes the raw Binance kline cache under `data/raw_binance_klines_1m/`, and
reports missing minute windows. In `--mode backfill`, emits a downloader-compatible
windows CSV and invokes the canonical downloader to fill gaps.

Truth boundary: this tool is READ-ONLY in `--mode audit`. It NEVER fabricates
candle data and NEVER marks missing minutes as covered. It does not create
`data/simulator/outcomes.json` (PKG-1 owns that). It does not modify
simulator/review/runtime code or production configs.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[2]
UTC = timezone.utc
MINUTE_MS = 60_000


@dataclass(frozen=True)
class JudgeWindow:
    symbol: str
    first_verdict_ts_ms: int
    last_verdict_ts_ms: int
    max_tf_sec: int
    tf_secs: tuple[int, ...]
    dates: tuple[str, ...]
    verdict_count: int


@dataclass(frozen=True)
class MissingRange:
    symbol: str
    start_close_ms: int
    end_close_ms: int
    missing_minutes: int


@dataclass
class CoverageRow:
    symbol: str
    required_minutes: int
    present_minutes: int
    missing_minutes: int
    missing_ranges: list[MissingRange] = field(default_factory=list)
    raw_cache_files: int = 0
    first_required_ms: int | None = None
    last_required_ms: int | None = None


def iso_utc(ts_ms: int) -> str:
    return datetime.fromtimestamp(ts_ms / 1000.0, tz=UTC).isoformat()


def ceil_to_close_ms(ts_ms: int) -> int:
    """Snap to the close timestamp of the 1m bar that contains ts_ms.

    A 1m bar opening at minute T occupies [T, T + 60_000); its close timestamp
    (Binance convention) is T + 60_000 - 1. Any ts_ms inside that bar must
    snap to that same close. We use mod-60_000 to find the offset from the
    floor minute boundary.
    """
    q, r = divmod(int(ts_ms), MINUTE_MS)
    if r == MINUTE_MS - 1:
        return int(ts_ms)
    return (q + 1) * MINUTE_MS - 1


def floor_to_open_ms(ts_ms: int) -> int:
    q, _ = divmod(int(ts_ms), MINUTE_MS)
    return q * MINUTE_MS


def date_str_utc(ts_ms: int) -> str:
    return datetime.fromtimestamp(ts_ms / 1000.0, tz=UTC).strftime("%Y-%m-%d")


def scan_judge_windows(judge_logs_root: Path, symbols_filter: set[str] | None = None) -> dict[str, JudgeWindow]:
    per_sym: dict[str, dict[str, Any]] = {}
    for path in sorted(judge_logs_root.glob("verdict_*.jsonl")):
        stem = path.stem
        body = stem[len("verdict_"):]
        try:
            symbol, date = body.rsplit("_", 1)
        except ValueError:
            continue
        if symbols_filter and symbol not in symbols_filter:
            continue
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                ts = row.get("ts_ms")
                tf = row.get("tf_sec")
                if ts is None or tf is None:
                    continue
                slot = per_sym.setdefault(
                    symbol,
                    {"first": ts, "last": ts, "tfs": set(), "dates": set(),
                     "count": 0},
                )
                slot["count"] += 1
                if ts < slot["first"]:
                    slot["first"] = ts
                if ts > slot["last"]:
                    slot["last"] = ts
                slot["tfs"].add(int(tf))
                slot["dates"].add(date)

    return {
        symbol: JudgeWindow(
            symbol=symbol,
            first_verdict_ts_ms=int(slot["first"]),
            last_verdict_ts_ms=int(slot["last"]),
            max_tf_sec=int(max(slot["tfs"])) if slot["tfs"] else 0,
            tf_secs=tuple(sorted(int(x) for x in slot["tfs"])),
            dates=tuple(sorted(slot["dates"])),
            verdict_count=int(slot["count"]),
        )
        for symbol, slot in per_sym.items()
    }


def required_close_ms_set(window: JudgeWindow, horizon_bars: int) -> tuple[int, int, set[int]]:
    """Required minute-aligned close timestamps for replay coverage.

    Start: close of the minute containing the first verdict (decision bar itself
    is needed for invariant checks).
    End:   close of (last_verdict_ts + horizon_bars * max_tf_sec * 1000).
    """
    start_close = ceil_to_close_ms(window.first_verdict_ts_ms)
    horizon_ms = horizon_bars * window.max_tf_sec * 1000
    end_close = ceil_to_close_ms(window.last_verdict_ts_ms + horizon_ms)
    required: set[int] = set()
    cursor = start_close
    while cursor <= end_close:
        required.add(cursor)
        cursor += MINUTE_MS
    return start_close, end_close, required


def index_raw_cache(raw_cache_root: Path, symbol: str) -> tuple[set[int], int]:
    """Return (set of present minute close_time_ms, number of raw files indexed)."""
    sym_dir = raw_cache_root / symbol
    if not sym_dir.exists():
        return set(), 0
    present: set[int] = set()
    file_count = 0
    for path in sorted(sym_dir.glob(f"{symbol}_1m_*.json")):
        file_count += 1
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        klines = payload.get("klines") if isinstance(
            payload, dict) else payload
        if not isinstance(klines, list):
            continue
        for row in klines:
            if not isinstance(row, list) or len(row) < 7:
                continue
            try:
                close_ms = int(row[6])
            except Exception:
                continue
            # Normalize to canonical minute close.
            present.add(ceil_to_close_ms(close_ms))
    return present, file_count


def collapse_missing(required: set[int], present: set[int]) -> list[tuple[int, int]]:
    missing = sorted(required - present)
    if not missing:
        return []
    ranges: list[tuple[int, int]] = []
    run_start = missing[0]
    run_end = missing[0]
    for ts in missing[1:]:
        if ts == run_end + MINUTE_MS:
            run_end = ts
        else:
            ranges.append((run_start, run_end))
            run_start = ts
            run_end = ts
    ranges.append((run_start, run_end))
    return ranges


def build_coverage_rows(
    judge_windows: dict[str, JudgeWindow],
    horizon_bars: int,
    raw_cache_root: Path,
) -> dict[str, CoverageRow]:
    out: dict[str, CoverageRow] = {}
    for symbol, jw in sorted(judge_windows.items()):
        start_close, end_close, required = required_close_ms_set(
            jw, horizon_bars)
        present, file_count = index_raw_cache(raw_cache_root, symbol)
        present_in_required = present & required
        missing_count = len(required) - len(present_in_required)
        ranges = collapse_missing(required, present)
        missing_ranges = [
            MissingRange(symbol=symbol, start_close_ms=a, end_close_ms=b,
                         missing_minutes=((b - a) // MINUTE_MS) + 1)
            for a, b in ranges
        ]
        out[symbol] = CoverageRow(
            symbol=symbol,
            required_minutes=len(required),
            present_minutes=len(present_in_required),
            missing_minutes=missing_count,
            missing_ranges=missing_ranges,
            raw_cache_files=file_count,
            first_required_ms=start_close,
            last_required_ms=end_close,
        )
    return out


def write_windows_csv(out_path: Path, rows: Iterable[MissingRange]) -> int:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    rows = list(rows)
    fieldnames = ["symbol", "required_start_ms",
                  "required_end_ms", "entries_covered", "reason"]
    with out_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for mr in rows:
            writer.writerow({
                "symbol": mr.symbol,
                "required_start_ms": mr.start_close_ms,
                "required_end_ms": mr.end_close_ms,
                "entries_covered": mr.missing_minutes,
                "reason": "pkg7_judge_coverage",
            })
    return len(rows)


def write_missing_jsonl(out_path: Path, rows: Iterable[MissingRange]) -> int:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with out_path.open("w", encoding="utf-8") as fh:
        for mr in rows:
            payload = {
                "symbol": mr.symbol,
                "start_close_ms": mr.start_close_ms,
                "end_close_ms": mr.end_close_ms,
                "start_iso": iso_utc(mr.start_close_ms),
                "end_iso": iso_utc(mr.end_close_ms),
                "missing_minutes": mr.missing_minutes,
            }
            fh.write(json.dumps(payload, sort_keys=True,
                     ensure_ascii=False) + "\n")
            count += 1
    return count


def write_manifest(out_path: Path, payload: dict[str, Any]) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(payload, sort_keys=True,
                   ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def render_report_md(
    *,
    mode: str,
    judge_logs_root: Path,
    raw_cache_root: Path,
    horizon_bars: int,
    judge_windows: dict[str, JudgeWindow],
    coverage: dict[str, CoverageRow],
    backfill_summary: dict[str, Any] | None,
) -> str:
    lines: list[str] = []
    lines.append("# PKG-7 Judge 1m candle coverage report")
    lines.append("")
    lines.append(f"**Mode**: `{mode}`  ")
    lines.append(f"**Judge logs root**: `{judge_logs_root.as_posix()}`  ")
    lines.append(f"**Raw cache root**: `{raw_cache_root.as_posix()}`  ")
    lines.append(f"**Horizon bars**: `{horizon_bars}` (× max tf_sec)  ")
    lines.append(f"**Generated at**: `{datetime.now(tz=UTC).isoformat()}`")
    lines.append("")
    lines.append("## Coverage matrix")
    lines.append("")
    lines.append(
        "| symbol | dates | verdicts | max tf_sec | required minutes | present | missing | raw files | status |")
    lines.append("|---|---|---:|---:|---:|---:|---:|---:|---|")
    total_required = 0
    total_present = 0
    total_missing = 0
    for symbol, cov in sorted(coverage.items()):
        jw = judge_windows[symbol]
        status = "COVERED" if cov.missing_minutes == 0 else "MISSING"
        total_required += cov.required_minutes
        total_present += cov.present_minutes
        total_missing += cov.missing_minutes
        lines.append(
            f"| {symbol} | {len(jw.dates)} | {jw.verdict_count} | {jw.max_tf_sec} | "
            f"{cov.required_minutes} | {cov.present_minutes} | {cov.missing_minutes} | "
            f"{cov.raw_cache_files} | {status} |"
        )
    lines.append(
        f"| **TOTAL** |  |  |  | **{total_required}** | **{total_present}** | **{total_missing}** |  |  |")
    lines.append("")
    lines.append("## Required window per symbol")
    lines.append("")
    lines.append(
        "| symbol | first_required_close | last_required_close | dates covered |")
    lines.append("|---|---|---|---|")
    for symbol, cov in sorted(coverage.items()):
        first = iso_utc(
            cov.first_required_ms) if cov.first_required_ms else "n/a"
        last = iso_utc(cov.last_required_ms) if cov.last_required_ms else "n/a"
        dates = ", ".join(judge_windows[symbol].dates)
        lines.append(f"| {symbol} | {first} | {last} | {dates} |")
    lines.append("")
    lines.append("## Missing windows (collapsed)")
    lines.append("")
    any_missing = False
    for symbol, cov in sorted(coverage.items()):
        if not cov.missing_ranges:
            continue
        any_missing = True
        lines.append(f"### {symbol}")
        lines.append("")
        lines.append(
            "| start_close (UTC) | end_close (UTC) | missing_minutes |")
        lines.append("|---|---|---:|")
        for mr in cov.missing_ranges:
            lines.append(
                f"| {iso_utc(mr.start_close_ms)} | {iso_utc(mr.end_close_ms)} | {mr.missing_minutes} |")
        lines.append("")
    if not any_missing:
        lines.append(
            "All Judge log windows are fully covered by the raw 1m kline cache.")
        lines.append("")
    if backfill_summary is not None:
        lines.append("## Backfill invocation")
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(backfill_summary, sort_keys=True,
                     ensure_ascii=False, indent=2))
        lines.append("```")
        lines.append("")
    lines.append("## Truth boundary")
    lines.append("")
    lines.append(
        "- This report is informational. It does not modify `data/simulator/`.")
    lines.append(
        "- Missing minutes are NEVER marked covered; backfill must succeed to clear them.")
    lines.append(
        "- 1000PEPEUSDT is reported alongside other symbols when present in Judge logs.")
    return "\n".join(lines) + "\n"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode", choices=("audit", "backfill"), default="audit")
    parser.add_argument("--judge-logs-root",
                        default=str(ROOT / "logs" / "judge_experts"))
    parser.add_argument("--raw-cache-root",
                        default=str(ROOT / "data" / "raw_binance_klines_1m"))
    parser.add_argument("--recorder-root",
                        default=str(ROOT / "data" / "recorder_backfill_1m"))
    parser.add_argument(
        "--format-contract",
        default=str(ROOT / "reports" / "order_log_forensic_sync" /
                    "recorder_1m_format_contract.json"),
    )
    parser.add_argument("--horizon-bars", type=int, default=12)
    parser.add_argument(
        "--report-out",
        default=str(ROOT / "reports" /
                    "PKG_7_JUDGE_1M_CANDLE_COVERAGE_REPORT.md"),
    )
    parser.add_argument(
        "--manifest-out",
        default=str(ROOT / "reports" / "pkg_7_candle_coverage_manifest.json"),
    )
    parser.add_argument(
        "--missing-windows-jsonl",
        default=str(ROOT / "reports" / "pkg_7_candle_missing_windows.jsonl"),
    )
    parser.add_argument(
        "--windows-csv",
        default=str(ROOT / "reports" / "pkg_7_backfill_windows.csv"),
    )
    parser.add_argument("--symbols", default="",
                        help="Optional CSV filter of symbols.")
    parser.add_argument("--downloader",
                        default=str(ROOT / "tools" / "data" / "download_binance_futures_1m_klines_for_replay.py"))
    parser.add_argument("--rate-limit-sleep-sec", type=float, default=0.2)
    parser.add_argument("--max-retries", type=int, default=3)
    return parser.parse_args(argv)


def _hash_inputs(judge_windows: dict[str, JudgeWindow], horizon_bars: int) -> str:
    serial = json.dumps(
        {
            symbol: {
                "first": jw.first_verdict_ts_ms,
                "last": jw.last_verdict_ts_ms,
                "max_tf": jw.max_tf_sec,
                "count": jw.verdict_count,
            }
            for symbol, jw in sorted(judge_windows.items())
        }
        | {"horizon_bars": horizon_bars},
        sort_keys=True,
    )
    return hashlib.sha256(serial.encode("utf-8")).hexdigest()


def run(args: argparse.Namespace) -> int:
    judge_logs_root = Path(args.judge_logs_root)
    raw_cache_root = Path(args.raw_cache_root)
    recorder_root = Path(args.recorder_root)
    symbols_filter = {s.strip().upper()
                      for s in args.symbols.split(",") if s.strip()} or None

    judge_windows = scan_judge_windows(judge_logs_root, symbols_filter)
    if not judge_windows:
        print(json.dumps({"status": "no_judge_windows",
              "judge_logs_root": str(judge_logs_root)}))
        return 2

    coverage = build_coverage_rows(
        judge_windows, args.horizon_bars, raw_cache_root)
    all_missing: list[MissingRange] = []
    for cov in coverage.values():
        all_missing.extend(cov.missing_ranges)

    missing_count = write_missing_jsonl(
        Path(args.missing_windows_jsonl), all_missing)
    windows_count = write_windows_csv(Path(args.windows_csv), all_missing)

    backfill_summary: dict[str, Any] | None = None
    if args.mode == "backfill" and all_missing:
        downloader_cmd = [
            sys.executable,
            str(args.downloader),
            "--windows", str(args.windows_csv),
            "--out-root", str(recorder_root),
            "--format-contract", str(args.format_contract),
            "--raw-root", str(raw_cache_root),
            "--rate-limit-sleep-sec", str(args.rate_limit_sleep_sec),
            "--max-retries", str(args.max_retries),
        ]
        proc = subprocess.run(
            downloader_cmd, capture_output=True, text=True, check=False)
        backfill_summary = {
            "cmd": downloader_cmd,
            "returncode": proc.returncode,
            "stdout_tail": proc.stdout[-2000:],
            "stderr_tail": proc.stderr[-2000:],
        }
        # Re-audit after backfill to get post-state.
        coverage = build_coverage_rows(
            judge_windows, args.horizon_bars, raw_cache_root)

    manifest = {
        "schema_version": "pkg7_v1",
        "mode": args.mode,
        "generated_at_utc": datetime.now(tz=UTC).isoformat(),
        "judge_logs_root": str(judge_logs_root),
        "raw_cache_root": str(raw_cache_root),
        "recorder_root": str(recorder_root),
        "horizon_bars": args.horizon_bars,
        "input_hash_sha256": _hash_inputs(judge_windows, args.horizon_bars),
        "symbols": {
            symbol: {
                "first_verdict_ts_ms": jw.first_verdict_ts_ms,
                "first_verdict_iso": iso_utc(jw.first_verdict_ts_ms),
                "last_verdict_ts_ms": jw.last_verdict_ts_ms,
                "last_verdict_iso": iso_utc(jw.last_verdict_ts_ms),
                "max_tf_sec": jw.max_tf_sec,
                "tf_secs": list(jw.tf_secs),
                "dates": list(jw.dates),
                "verdict_count": jw.verdict_count,
                "required_minutes": coverage[symbol].required_minutes,
                "present_minutes": coverage[symbol].present_minutes,
                "missing_minutes": coverage[symbol].missing_minutes,
                "raw_cache_files": coverage[symbol].raw_cache_files,
                "first_required_close_ms": coverage[symbol].first_required_ms,
                "last_required_close_ms": coverage[symbol].last_required_ms,
                "missing_ranges": [
                    {
                        "start_close_ms": mr.start_close_ms,
                        "end_close_ms": mr.end_close_ms,
                        "missing_minutes": mr.missing_minutes,
                    }
                    for mr in coverage[symbol].missing_ranges
                ],
            }
            for symbol, jw in sorted(judge_windows.items())
        },
        "totals": {
            "required_minutes": sum(c.required_minutes for c in coverage.values()),
            "present_minutes": sum(c.present_minutes for c in coverage.values()),
            "missing_minutes": sum(c.missing_minutes for c in coverage.values()),
            "missing_ranges": missing_count,
            "windows_csv_rows": windows_count,
        },
        "backfill_summary": backfill_summary,
    }
    write_manifest(Path(args.manifest_out), manifest)

    report = render_report_md(
        mode=args.mode,
        judge_logs_root=judge_logs_root,
        raw_cache_root=raw_cache_root,
        horizon_bars=args.horizon_bars,
        judge_windows=judge_windows,
        coverage=coverage,
        backfill_summary=backfill_summary,
    )
    report_path = Path(args.report_out)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")

    print(json.dumps({
        "mode": args.mode,
        "symbols": len(judge_windows),
        "missing_minutes_total": manifest["totals"]["missing_minutes"],
        "missing_ranges": missing_count,
        "report": str(report_path),
        "manifest": str(Path(args.manifest_out)),
        "windows_csv": str(Path(args.windows_csv)),
        "missing_jsonl": str(Path(args.missing_windows_jsonl)),
    }, sort_keys=True))

    if manifest["totals"]["missing_minutes"] == 0:
        return 0
    return 0 if args.mode == "audit" else (3 if backfill_summary and backfill_summary["returncode"] != 0 else 0)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
