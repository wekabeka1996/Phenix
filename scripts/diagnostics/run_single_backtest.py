#!/usr/bin/env python3
"""
Run a single A or B backtest side in isolation.

Usage:
    python scripts/diagnostics/run_single_backtest.py --side A --rung 2
    python scripts/diagnostics/run_single_backtest.py --side B --rung 2
    python scripts/diagnostics/run_single_backtest.py --side A --start 2023-06-01 --end 2023-07-31
    python scripts/diagnostics/run_single_backtest.py --side B --start 2023-06-01 --end 2023-07-31

Why a single-side script?
    Calling run_backtest_simulation() twice in the same process causes state leakage —
    the 2nd call produces 0 trades (warmup never clears).
    Running each side in a fresh process (one call per process) avoids this.

Outputs:
    reports/backtests/backtest_<run_id>.json   (standard report)
    Prints key metrics to stdout for copying into the ladder manual log.
"""

from __future__ import annotations

import argparse
import json
import sys
from calendar import monthrange
from pathlib import Path
from typing import Optional

import yaml

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

# ── Ladder definition (same as run_backtest_ladder.py) ────────────────────────
LADDER_RUNGS = [
    (1,  2023, 6,  2023, 6),
    (2,  2023, 6,  2023, 7),
    (3,  2023, 6,  2023, 8),
    (4,  2023, 6,  2023, 9),
    (5,  2023, 6,  2023, 10),
    (6,  2023, 6,  2023, 11),
    (7,  2023, 6,  2023, 12),
    (8,  2023, 6,  2024, 1),
    (9,  2023, 6,  2024, 2),
    (10, 2023, 6,  2024, 3),
]

CONFIG_DIRS = {
    "A": ROOT / "config" / "aurora_baseline",
    "B": ROOT / "config" / "aurora",
}


def rung_dates(rung_num: int):
    for r in LADDER_RUNGS:
        if r[0] == rung_num:
            _, sy, sm, ey, em = r
            last_day = monthrange(ey, em)[1]
            return f"{sy:04d}-{sm:02d}-01", f"{ey:04d}-{em:02d}-{last_day:02d}"
    raise ValueError(f"Rung {rung_num} not found. Valid: 1-10.")


def _parse_args(argv=None):
    p = argparse.ArgumentParser(description="Run single A or B backtest side")
    p.add_argument("--side", required=True, choices=["A", "B"],
                   help="A = aurora_baseline (current prod), B = aurora (patched)")
    p.add_argument("--rung", type=int, default=None,
                   help="Rung number 1-10 (auto-fills --start/--end)")
    p.add_argument("--start", default=None, help="Start date YYYY-MM-DD")
    p.add_argument("--end", default=None, help="End date YYYY-MM-DD")
    p.add_argument("--balance", type=float, default=1000.0,
                   help="Initial balance USDT (default: 1000)")
    p.add_argument("--overlay-yaml", default=None,
                   help="Optional YAML file with backtest-only overlay (raw dict or {meta, overlay})")
    return p.parse_args(argv)


def _load_overlay_yaml(path_str: str) -> dict:
    overlay_path = Path(path_str)
    if not overlay_path.exists():
        raise FileNotFoundError(f"Overlay file not found: {overlay_path}")

    with overlay_path.open("r", encoding="utf-8-sig", errors="replace") as handle:
        payload = yaml.safe_load(handle) or {}

    if not isinstance(payload, dict):
        raise ValueError(f"Overlay YAML must decode to a mapping: {overlay_path}")

    overlay = payload.get("overlay", payload)
    if not isinstance(overlay, dict):
        raise ValueError(f"Overlay payload must be a mapping: {overlay_path}")

    return overlay


def main(argv=None) -> int:
    args = _parse_args(argv)

    # Resolve dates
    if args.rung is not None:
        start_date, end_date = rung_dates(args.rung)
        rung_label = f"R{args.rung}"
    elif args.start and args.end:
        start_date, end_date = args.start, args.end
        rung_label = "custom"
    else:
        print("ERROR: Provide either --rung N or --start + --end")
        return 1

    config_dir = CONFIG_DIRS[args.side]
    side_name = "aurora_baseline (A)" if args.side == "A" else "aurora (B-patched)"
    overlay = None
    if args.overlay_yaml:
        try:
            overlay = _load_overlay_yaml(args.overlay_yaml)
        except Exception as exc:
            print(f"ERROR: Failed to load overlay YAML: {exc}")
            return 1

    print("=" * 60)
    print(f"  AURORA SINGLE BACKTEST - side={args.side}, rung={rung_label}")
    print(f"  Config : {config_dir.name}")
    print(f"  Period : {start_date} -> {end_date}")
    print(f"  Balance: {args.balance:.2f} USDT")
    if args.overlay_yaml:
        print(f"  Overlay: {args.overlay_yaml}")
    print("=" * 60)

    if not config_dir.exists():
        print(f"ERROR: Config dir not found: {config_dir}")
        return 1

    # Load config
    from apps.reference.config_loader import ConfigLoader
    loader = ConfigLoader(config_dir=config_dir, optuna_overlay=overlay)
    config = loader.load_config()

    try:
        config.trading.backtest.start_date = start_date
        config.trading.backtest.end_date = end_date
        config.trading.backtest.initial_balance = args.balance
    except Exception as e:
        print(f"ERROR: Failed to set backtest dates: {e}")
        return 1

    # Setup full file logging (same as main.py:966) — without this only bootstrap
    # console logging is active and no log files are written (aurora_core.log etc.)
    logs_dir = ROOT / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    try:
        from apps.reference.logging_setup import setup_logging
        setup_logging(config, logs_dir=logs_dir, force_reconfigure=True)
        print(f"  Logs dir      : {logs_dir}")
    except Exception as e:
        print(f"WARNING: setup_logging failed: {e}. Continuing with console-only logging.")

    # Run backtest (single call = no leakage)
    from apps.reference.main import run_backtest_simulation
    result, report = run_backtest_simulation(config, return_result=True)

    if result is None:
        print("ERROR: Backtest returned None result.")
        return 1

    # Print summary for manual recording
    run_id = report.get("run_id", "unknown") if report else "unknown"
    report_path = ROOT / "reports" / "backtests" / f"backtest_{run_id}.json"

    print()
    print("=" * 60)
    print(f"  RESULT SUMMARY — side={args.side} | rung={rung_label}")
    print("=" * 60)
    print(f"  run_id        : {run_id}")
    print(f"  period        : {start_date} → {end_date}")
    print(f"  total_pnl     : {result.total_pnl:.4f} USDT")
    print(f"  roi_pct       : {result.roi_pct:.4f}%")
    print(f"  max_drawdown  : {result.max_drawdown * 100:.2f}%")
    print(f"  total_trades  : {result.total_trades}")
    print(f"  win_rate      : {result.win_rate:.4f}")
    print(f"  end_balance   : {result.end_balance:.4f} USDT")

    sharpe = getattr(result, "sharpe_ratio", None)
    if sharpe is not None:
        print(f"  sharpe_ratio  : {sharpe:.4f}")

    if report:
        pipeline = report.get("pipeline", {}) or {}
        print(f"  bar_count     : {pipeline.get('bar_count', 'N/A')}")
        blocked = pipeline.get("blocked_reason_counts", {})
        if blocked:
            print(f"  blocked_reasons:")
            for k, v in sorted(blocked.items()):
                print(f"    {k}: {v}")
        broker = report.get("broker", {}) or {}
        if broker.get("total_fees") is not None:
            print(f"  total_fees    : {broker.get('total_fees', 0):.4f} USDT")

    print(f"\n  Full report   : {report_path}")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
