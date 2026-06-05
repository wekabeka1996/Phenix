"""MR-RESTORE-002: runtime-ish proof probe.

Goal:
- Produce durable evidence that MeanReversionHandler receives EVT:MARKET_TICK_FORWARDED,
  processes ticks without reject, and closes at least one bar.

This script is intentionally minimal and safe:
- No network, no exchange calls
- In-process MiniFSM drives the handler
- Diagnostics are written into reports/ as JSONL + MD report

Usage:
  python scripts/mr_restore_002_probe.py

Optional env:
  AURORA_MR_DIAG=1
  AURORA_MR_DIAG_SAMPLE_EVERY=1
  AURORA_MR_DIAG_JSONL_PATH=reports/mr_restore_002_probe.jsonl
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List


# Ensure repository root is importable when running as a script.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from vfoundation.core.protocol import Message
from apps.reference.config_loader import ConfigLoader
from apps.reference.domains.strategies.runtimes.mean_reversion.handler import MeanReversionHandler


class MiniFSM:
    def __init__(self) -> None:
        self._listeners: Dict[str, List[Callable[[Message], None]]] = {}

    def listen(self, event_name: str, handler: Callable[[Message], None]) -> None:
        self._listeners.setdefault(event_name, []).append(handler)

    def emit(self, event_name: str, payload: Dict[str, Any], *, why: str = "") -> None:
        msg = Message(
            op="EVT",
            verb=event_name.split(":", 1)[-1],
            src="mr_restore_002_probe",
            dst="any",
            pld=payload,
            why=why[:80] if why else None,
        )
        for handler in self._listeners.get(event_name, []):
            handler(msg)


def main() -> int:
    reports_dir = Path(__file__).resolve().parents[1] / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    # Force diagnostics artifact paths for this probe.
    os.environ.setdefault("AURORA_MR_DIAG", "1")
    os.environ.setdefault("AURORA_MR_DIAG_SAMPLE_EVERY", "1")
    os.environ.setdefault(
        "AURORA_MR_DIAG_JSONL_PATH",
        str(reports_dir / "mr_restore_002_probe.jsonl"),
    )

    jsonl_path = Path(os.environ["AURORA_MR_DIAG_JSONL_PATH"]).resolve()
    if jsonl_path.exists():
        jsonl_path.unlink()

    fsm = MiniFSM()
    config = ConfigLoader().load_config(strict_mode=True, is_live_execution=False)
    mr = MeanReversionHandler(fsm=fsm, config=config)
    mr.register()

    # Emit a tick series spanning multiple minutes so the evidence artifact has >=20 lines.
    symbol = "DOGEUSDT"
    base_ts_ms = 1_700_000_000_000  # deterministic, ms

    ticks = [base_ts_ms + (i * 30_000) for i in range(25)]  # 25 ticks @ 30s (~12.5 min)

    for i, ts_ms in enumerate(ticks):
        fsm.emit(
            "EVT:MARKET_TICK_FORWARDED",
            {
                "symbol": symbol,
                "price": str(0.10 + (i * 0.0005)),
                "volume": "1",
                "timestamp_ms": ts_ms,
            },
            why="mr_restore_002_probe",
        )

    # Allow any buffered file flush (defensive; handler writes synchronously).
    time.sleep(0.01)

    # Produce a small human-readable report with concrete evidence lines.
    md_path = reports_dir / "mr_restore_002_report.md"
    lines: List[str] = []
    if jsonl_path.exists():
        raw = jsonl_path.read_text(encoding="utf-8", errors="replace").splitlines()
        lines = raw[:20]

    summary = {
        "symbol": symbol,
        "ticks_emitted": len(ticks),
        "diag_jsonl_path": str(jsonl_path),
        "diag_lines": len(lines),
    }

    md = [
        "# MR-RESTORE-002 — Local Probe Report",
        "",
        f"**Generated**: {time.strftime('%Y-%m-%d %H:%M:%S')} (local)",
        "",
        "## Evidence",
        "",
        "- Emitted `EVT:MARKET_TICK_FORWARDED` ticks into `MeanReversionHandler` (MiniFSM).",
        "- Collected durable diagnostic JSONL artifact.",
        "",
        "## Summary (machine)",
        "",
        "```json",
        json.dumps(summary, ensure_ascii=False, indent=2),
        "```",
        "",
        "## First 20 diagnostic lines (JSONL)",
        "",
    ]

    if lines:
        md.append("```jsonl")
        md.extend(lines)
        md.append("```")
    else:
        md.append("(no diagnostic lines found — check env AURORA_MR_DIAG* and MR enablement)")

    md_path.write_text("\n".join(md), encoding="utf-8")

    print(json.dumps({"report": str(md_path), "jsonl": str(jsonl_path)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
