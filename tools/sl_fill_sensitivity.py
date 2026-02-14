#!/usr/bin/env python3
"""
SL Fill Sensitivity — Dual-run comparison tool.
================================================

Runs the same backtest twice (optimistic vs conservative SL fill model),
then generates:
  - sl_orders_band.csv        per-SL band rows
  - sl_fill_sensitivity.json   delta comparison summary

Usage:
    python tools/sl_fill_sensitivity.py \\
        --data-dir data/processed \\
        --symbol BTCUSDT \\
        --timeframe 5m \\
        --start 2023-08-01 \\
        --end 2023-08-31 \\
        --initial-balance 1000 \\
        --sl-min-bps 5 \\
        --out-dir reports/sensitivity

NOTE:
    This is a *standalone lightweight* runner that uses BacktestEngine + MockBroker
    directly (no full app domain orchestration).  It is designed for sensitivity
    analysis only.  For production backtests use ``apps.reference.main``.
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
from datetime import date, datetime
from pathlib import Path

# Ensure project root on sys.path
_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from backtest_engine.engine import BacktestEngine, BacktestResult
from backtest_engine.mock_broker import MockBroker
from backtest_engine.sl_fill_policy import SLBandRecord, summarize_sl_band

LOG = logging.getLogger("sl_fill_sensitivity")


# ---------------------------------------------------------------------------
#   Lightweight runner (engine-only, no full orchestration)
# ---------------------------------------------------------------------------

def _run_engine(
    *,
    symbol: str,
    timeframe: str,
    start: date,
    end: date,
    data_dir: str,
    initial_balance: float,
    sl_fill_model: str,
    sl_min_bps: float,
    slippage_bps: float,
) -> tuple[BacktestResult, list[SLBandRecord], MockBroker]:
    """Run BacktestEngine with given SL fill model and return results + band."""
    engine = BacktestEngine(
        start_date=start,
        end_date=end,
        symbol_list=[symbol],
        timeframe=timeframe,
        data_dir=data_dir,
        initial_balance=initial_balance,
    )
    # Replace broker with properly configured one
    engine.broker = MockBroker(
        initial_balance_usdt=initial_balance,
        slippage_bps=slippage_bps,
        sl_fill_model=sl_fill_model,
        sl_min_bps=sl_min_bps,
    )
    result = engine.run()
    band = list(engine.broker.sl_band_log)
    return result, band, engine.broker


# ---------------------------------------------------------------------------
#   Compare logic
# ---------------------------------------------------------------------------

def build_compare_json(
    res_opt: BacktestResult,
    res_con: BacktestResult,
    band_opt: list[SLBandRecord],
    band_con: list[SLBandRecord],
    run_id: str,
) -> dict:
    """Build the sl_fill_sensitivity.json payload."""

    def _summary(r: BacktestResult) -> dict:
        return {
            "start_balance": r.start_balance,
            "end_balance": round(r.end_balance, 4),
            "total_pnl": round(r.total_pnl, 4),
            "roi_pct": round(r.roi_pct, 4),
            "max_drawdown": round(r.max_drawdown, 6),
            "total_trades": r.total_trades,
            "win_rate": round(r.win_rate, 4),
        }

    s_opt = _summary(res_opt)
    s_con = _summary(res_con)

    delta = {
        "end_equity": round(s_opt["end_balance"] - s_con["end_balance"], 4),
        "roi_pct": round(s_opt["roi_pct"] - s_con["roi_pct"], 4),
        "max_dd": round(s_opt["max_drawdown"] - s_con["max_drawdown"], 6),
        "total_trades": s_opt["total_trades"] - s_con["total_trades"],
    }

    # Use whichever band has more records for summary
    band_for_summary = band_opt if len(band_opt) >= len(band_con) else band_con

    return {
        "run_id_base": run_id,
        "optimistic": s_opt,
        "conservative": s_con,
        "delta": delta,
        "sl_band": summarize_sl_band(band_for_summary),
    }


def write_band_csv(records: list[SLBandRecord], path: Path) -> None:
    """Write SL band records to CSV."""
    if not records:
        path.write_text("# no SL triggers\n")
        return
    fieldnames = list(records[0].to_dict().keys())
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in records:
            writer.writerow(r.to_dict())


# ---------------------------------------------------------------------------
#   CLI
# ---------------------------------------------------------------------------

def parse_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="SL Fill Sensitivity — dual-run comparison")
    parser.add_argument("--data-dir", default="data/processed", help="Data directory")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--timeframe", default="5m")
    parser.add_argument("--start", type=parse_date, required=True, help="Start date YYYY-MM-DD")
    parser.add_argument("--end", type=parse_date, required=True, help="End date YYYY-MM-DD")
    parser.add_argument("--initial-balance", type=float, default=1000.0)
    parser.add_argument("--sl-min-bps", type=float, default=5.0, help="Optimistic min slippage bps")
    parser.add_argument("--slippage-bps", type=float, default=2.0, help="General market slippage bps")
    parser.add_argument("--run-id", default=None, help="Run ID label (auto-generated if omitted)")
    parser.add_argument("--out-dir", default="reports/sensitivity", help="Output directory")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

    run_id = args.run_id or datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path(args.out_dir) / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    common = dict(
        symbol=args.symbol,
        timeframe=args.timeframe,
        start=args.start,
        end=args.end,
        data_dir=args.data_dir,
        initial_balance=args.initial_balance,
        sl_min_bps=args.sl_min_bps,
        slippage_bps=args.slippage_bps,
    )

    LOG.info("=== Run 1/2: OPTIMISTIC ===")
    res_opt, band_opt, _ = _run_engine(sl_fill_model="optimistic", **common)

    LOG.info("=== Run 2/2: CONSERVATIVE ===")
    res_con, band_con, _ = _run_engine(sl_fill_model="conservative", **common)

    # ---- Write artefacts ----
    compare = build_compare_json(res_opt, res_con, band_opt, band_con, run_id)

    json_path = out_dir / "sl_fill_sensitivity.json"
    json_path.write_text(json.dumps(compare, indent=2, default=str))
    LOG.info(f"Wrote {json_path}")

    # Band CSV — merge both lists with a "run_model" column
    all_band = band_opt + band_con
    csv_path = out_dir / "sl_orders_band.csv"
    write_band_csv(all_band, csv_path)
    LOG.info(f"Wrote {csv_path}")

    # Human-readable summary
    print("\n" + "=" * 60)
    print(f"SL FILL SENSITIVITY — {run_id}")
    print("=" * 60)
    print(f"  Optimistic  end_equity: {res_opt.end_balance:>12.2f}  ROI: {res_opt.roi_pct:>7.2f}%  DD: {res_opt.max_drawdown:>7.4f}")
    print(f"  Conservative end_equity: {res_con.end_balance:>12.2f}  ROI: {res_con.roi_pct:>7.2f}%  DD: {res_con.max_drawdown:>7.4f}")
    print(f"  Delta equity: {compare['delta']['end_equity']:>+12.2f}")
    print(f"  SL triggers: {compare['sl_band']['count_sl']}")
    if compare["sl_band"]["count_sl"] > 0:
        print(f"  p50 slip opt/cons: {compare['sl_band']['p50_slip_bps_opt']:.1f} / {compare['sl_band']['p50_slip_bps_cons']:.1f} bps")
        print(f"  p95 slip opt/cons: {compare['sl_band']['p95_slip_bps_opt']:.1f} / {compare['sl_band']['p95_slip_bps_cons']:.1f} bps")
    print(f"  Output: {out_dir}")
    print("=" * 60)


if __name__ == "__main__":
    main()
