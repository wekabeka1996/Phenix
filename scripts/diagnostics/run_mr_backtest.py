#!/usr/bin/env python3
"""
Run a Mean Reversion backtest in an isolated process.

Usage:
    python scripts/diagnostics/run_mr_backtest.py --start 2023-06-01 --end 2023-09-30
    python scripts/diagnostics/run_mr_backtest.py --rung 2
    python scripts/diagnostics/run_mr_backtest.py --start 2023-06-01 --end 2023-06-30 --symbols DOGEUSDT
    python scripts/diagnostics/run_mr_backtest.py --start 2023-06-01 --end 2023-09-30 --balance 500

Why a separate script?
    Calling run_backtest_simulation() twice in the same process causes state leakage —
    the 2nd call produces 0 trades (warmup never clears).
    This script runs the MR backtest in a fresh process, so it can execute in parallel
    with the Aurora backtest (run_single_backtest.py).

Config:
    Uses config/mean_reversion/ — a dedicated config directory where strategies.yaml
    assigns only DOGEUSDT and 1000PEPEUSDT to the mean_reversion strategy.

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

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

# ── Ladder definition (same as run_single_backtest.py) ────────────────────────
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

CONFIG_DIR = ROOT / "config" / "mean_reversion"


def rung_dates(rung_num: int):
    for r in LADDER_RUNGS:
        if r[0] == rung_num:
            _, sy, sm, ey, em = r
            last_day = monthrange(ey, em)[1]
            return f"{sy:04d}-{sm:02d}-01", f"{ey:04d}-{em:02d}-{last_day:02d}"
    raise ValueError(f"Rung {rung_num} not found. Valid: 1-10.")


def _parse_args(argv=None):
    p = argparse.ArgumentParser(
        description="Run Mean Reversion backtest (DOGE / 1000PEPE)",
        epilog=(
            "Examples:\n"
            "  %(prog)s --start 2023-06-01 --end 2023-09-30\n"
            "  %(prog)s --rung 2\n"
            "  %(prog)s --start 2023-06-01 --end 2023-06-30 --symbols DOGEUSDT\n"
            "  %(prog)s --start 2023-06-01 --end 2023-09-30 --balance 500\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--rung", type=int, default=None,
                   help="Rung number 1-10 (auto-fills --start/--end)")
    p.add_argument("--start", default=None, help="Start date YYYY-MM-DD")
    p.add_argument("--end", default=None, help="End date YYYY-MM-DD")
    p.add_argument("--balance", type=float, default=1000.0,
                   help="Initial balance USDT (default: 1000)")
    p.add_argument("--symbols", nargs="+", default=None,
                   help="Optional: filter to specific symbols (e.g. DOGEUSDT 1000PEPEUSDT)")
    return p.parse_args(argv)


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

    print("=" * 60)
    print(f"  MEAN REVERSION BACKTEST — rung={rung_label}")
    print(f"  Config : {CONFIG_DIR.name}")
    print(f"  Period : {start_date} -> {end_date}")
    print(f"  Balance: {args.balance:.2f} USDT")
    if args.symbols:
        print(f"  Symbols: {', '.join(args.symbols)}")
    else:
        print(f"  Symbols: ALL from strategies.yaml (DOGEUSDT, 1000PEPEUSDT)")
    print("=" * 60)

    if not CONFIG_DIR.exists():
        print(f"ERROR: Config dir not found: {CONFIG_DIR}")
        return 1

    # Load config
    from apps.reference.config_loader import ConfigLoader
    loader = ConfigLoader(config_dir=CONFIG_DIR)
    config = loader.load_config()

    try:
        config.trading.backtest.start_date = start_date
        config.trading.backtest.end_date = end_date
        config.trading.backtest.initial_balance = args.balance
    except Exception as e:
        print(f"ERROR: Failed to set backtest dates: {e}")
        return 1

    # Optional symbol filter: override symbols_to_track if --symbols is given
    if args.symbols:
        try:
            config.trading.symbols_to_track = list(args.symbols)
        except Exception as e:
            print(f"WARNING: Could not set symbols_to_track: {e}")

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
    print(f"  MEAN REVERSION RESULT SUMMARY — rung={rung_label}")
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
