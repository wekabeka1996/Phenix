"""
Tidy-gate smoke checker.

Scans logs for key markers and prints a compact report:
- EVT:TRADE_EXECUTED
- [BRK] preflight DECISION=allow
- POST of STOP/TP (STOP_MARKET/TAKE_PROFIT_MARKET)
- EVT:SYMBOL_TIDY
- [GATE] entry_(blocked|allowed)

Usage:
  python tools/smoke_tidy_gate.py [--logfile apps/logs/order_guardian.log] [--grep-all]
"""

from __future__ import annotations

import argparse
from pathlib import Path


PATTERNS = [
    "EVT:TRADE_EXECUTED",
    "preflight DECISION=allow",
    "STOP_MARKET",
    "TAKE_PROFIT_MARKET",
    "EVT:SYMBOL_TIDY",
    "[GATE] entry_blocked",
    "[GATE] entry_allowed",
]


def scan_file(path: Path, grep_all: bool = False) -> list[str]:
    if not path.exists():
        return [f"WARN: file not found: {path}"]
    out: list[str] = []
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception as e:
        return [f"ERROR: failed to read {path}: {e}"]

    for p in PATTERNS:
        matches = [ln for ln in lines if p in ln]
        if matches:
            if grep_all:
                out.extend([f"{p}: {m}" for m in matches[-10:]])
            else:
                out.append(f"{p}: {matches[-1]}")
        else:
            out.append(f"{p}: (no matches)")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--logfile",
        default=str(Path("apps") / "logs" / "order_guardian.log"),
        help="Log file to scan (default: apps/logs/order_guardian.log)",
    )
    ap.add_argument("--grep-all", action="store_true", help="Print several last matches for each pattern")
    args = ap.parse_args()

    p = Path(args.logfile)
    report = scan_file(p, grep_all=args.grep_all)
    print("\n".join(report))


if __name__ == "__main__":
    main()

