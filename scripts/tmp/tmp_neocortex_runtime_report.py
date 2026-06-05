#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import re
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


def _read_lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    try:
        return path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return path.read_text(errors="replace").splitlines()


def _last_lines(lines: list[str], n: int) -> list[str]:
    if n <= 0:
        return []
    return lines[-n:]


def _extract_feature_counter(line: str) -> int | None:
    m = re.search(r"Feature #(\d+):", line)
    if not m:
        return None
    try:
        return int(m.group(1))
    except ValueError:
        return None


def _extract_epoch_ts(line: str) -> float | None:
    m = re.match(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),(\d{3})", line)
    if not m:
        return None
    dt_str = f"{m.group(1)}.{m.group(2)}"
    try:
        dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S.%f").replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except ValueError:
        return None


def _count_codes(lines: Iterable[str]) -> Counter:
    c = Counter()
    for line in lines:
        m = re.search(r"\[([A-Z0-9_]+)\]", line)
        if m:
            c[m.group(1)] += 1
    return c


def _metrics_rows(metrics_path: Path) -> int:
    if not metrics_path.exists():
        return 0
    try:
        with metrics_path.open("r", encoding="utf-8", errors="replace", newline="") as f:
            return max(0, sum(1 for _ in csv.reader(f)) - 1)
    except Exception:
        return 0


def build_report(repo_root: Path, tail: int = 120) -> str:
    log_path = repo_root / "data" / "neocortex.log"
    metrics_path = repo_root / "logs" / "neocortex_metrics.csv"
    shadow_path = repo_root / "data" / "shadow_intents.jsonl"

    lines = _read_lines(log_path)
    tail_lines = _last_lines(lines, tail)

    error_lines = [x for x in lines if "ERROR" in x or "CRITICAL" in x or "Traceback" in x]
    warning_lines = [x for x in lines if "WARNING" in x or "WARN:" in x or "[WARN" in x]

    has_torch_error = any("No module named 'torch'" in x for x in lines)
    brain_degraded = any("BRAIN_BRIDGE_UNAVAILABLE" in x for x in lines)

    feature_points: list[tuple[float, int]] = []
    for line in tail_lines:
        counter = _extract_feature_counter(line)
        ts = _extract_epoch_ts(line)
        if counter is not None and ts is not None:
            feature_points.append((ts, counter))

    feature_rate = None
    if len(feature_points) >= 2:
        dt = feature_points[-1][0] - feature_points[0][0]
        dc = feature_points[-1][1] - feature_points[0][1]
        if dt > 0:
            feature_rate = dc / dt

    metrics_rows = _metrics_rows(metrics_path)
    shadow_exists = shadow_path.exists()
    shadow_size = shadow_path.stat().st_size if shadow_exists else 0

    codes = _count_codes(lines)
    top_codes = ", ".join(f"{k}={v}" for k, v in codes.most_common(8)) if codes else "none"

    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    summary_status = "DEGRADED_INGESTION_ONLY" if brain_degraded else "HEALTHY_OR_UNKNOWN"

    out: list[str] = []
    out.append("# Neocortex Runtime Report")
    out.append("")
    out.append(f"- Generated: `{now_utc}`")
    out.append(f"- Status: `{summary_status}`")
    out.append("")
    out.append("## Key Signals")
    out.append(f"- Log path: `{log_path}` (lines: {len(lines)})")
    out.append(f"- Errors: {len(error_lines)}")
    out.append(f"- Warnings: {len(warning_lines)}")
    out.append(f"- Torch import error seen: {str(has_torch_error).lower()}")
    out.append(f"- Bridge degraded alert seen: {str(brain_degraded).lower()}")
    out.append(f"- Metrics rows (excluding header): {metrics_rows}")
    out.append(f"- Shadow intents file exists: {str(shadow_exists).lower()} (bytes={shadow_size})")
    if feature_rate is not None:
        out.append(f"- Estimated feature ingest rate (tail window): {feature_rate:.2f} events/sec")
    else:
        out.append("- Estimated feature ingest rate (tail window): n/a")
    out.append(f"- Top bracketed codes: {top_codes}")
    out.append("")
    out.append("## Recent Log Tail")
    out.append("```text")
    out.extend(tail_lines)
    out.append("```")
    out.append("")
    out.append("## Interpretation")
    if brain_degraded:
        out.append("- System is running in degraded mode: ingestion active, training disabled.")
        out.append("- This is expected fail-safe when BrainBridge cannot initialize.")
        out.append("- Main blocker to full R2 behavior is missing PyTorch runtime in current environment.")
    else:
        out.append("- No explicit bridge degraded signal found in logs.")
    if metrics_rows == 0:
        out.append("- Telemetry CSV has no data rows yet; either no training/intent flow, or logging path issue.")
    if not shadow_exists:
        out.append("- No shadow intent JSONL produced yet.")
    return "\n".join(out) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Neocortex runtime report from logs.")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--out", type=Path, default=Path("docs/Полатенту_ЛЛА_ПЛани/NEOCORTEX_RUNTIME_30MIN_REPORT.md"))
    parser.add_argument("--tail", type=int, default=120)
    parser.add_argument("--sleep-seconds", type=int, default=0)
    args = parser.parse_args()

    if args.sleep_seconds > 0:
        time.sleep(args.sleep_seconds)

    report = build_report(args.repo_root.resolve(), tail=args.tail)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(report, encoding="utf-8")
    safe_out = str(args.out).encode("ascii", "backslashreplace").decode("ascii")
    print(f"[ok] report written: {safe_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
