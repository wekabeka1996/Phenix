#!/usr/bin/env python3
"""
SL Fill Sensitivity - Dual-run comparison tool.
================================================

Runs the same backtest twice (optimistic vs conservative SL fill model),
then generates:
  - sl_orders_band.csv        per-SL band rows
  - sl_fill_sensitivity.json  delta comparison summary

Usage:
    python tools/sl_fill_sensitivity.py \
        --data-dir data/processed \
        --symbol BTCUSDT \
        --timeframe 5m \
        --start 2023-08-01 \
        --end 2023-08-31 \
        --initial-balance 1000 \
        --sl-min-bps 5 \
        --out-dir reports/sensitivity

NOTE:
    This is a standalone lightweight runner that uses BacktestEngine + MockBroker
    directly (no full app domain orchestration). It is designed for sensitivity
    analysis only. For production backtests use apps.reference.main.
"""
from __future__ import annotations
from backtest_engine.sl_fill_policy import SLBandRecord, summarize_sl_band
from backtest_engine.mock_broker import MockBroker
from backtest_engine.engine import BacktestEngine, BacktestResult

import argparse
import csv
import json
import logging
import sys
from datetime import date, datetime
from pathlib import Path

# Ensure project root on sys.path.
_PROJECT_ROOT = str(Path(__file__).resolve().parents[2])
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


LOG = logging.getLogger("sl_fill_sensitivity")


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
    """Run BacktestEngine with given SL fill model and return results plus band."""
    engine = BacktestEngine(
        start_date=start,
        end_date=end,
        symbol_list=[symbol],
        timeframe=timeframe,
        data_dir=data_dir,
        initial_balance=initial_balance,
    )
    engine.broker = MockBroker(
        initial_balance_usdt=initial_balance,
        slippage_bps=slippage_bps,
        sl_fill_model=sl_fill_model,
        sl_min_bps=sl_min_bps,
    )
    result = engine.run()
    band = list(engine.broker.sl_band_log)
    return result, band, engine.broker


def build_compare_json(
    res_opt: BacktestResult,
    res_con: BacktestResult,
    band_opt: list[SLBandRecord],
    band_con: list[SLBandRecord],
    run_id: str,
) -> dict:
    """Build the sl_fill_sensitivity.json payload."""

    def _summary(result: BacktestResult) -> dict:
        return {
            "start_balance": result.start_balance,
            "end_balance": round(result.end_balance, 4),
            "total_pnl": round(result.total_pnl, 4),
            "roi_pct": round(result.roi_pct, 4),
            "max_drawdown": round(result.max_drawdown, 6),
            "total_trades": result.total_trades,
            "win_rate": round(result.win_rate, 4),
        }

    optimistic = _summary(res_opt)
    conservative = _summary(res_con)
    delta = {
        "end_equity": round(optimistic["end_balance"] - conservative["end_balance"], 4),
        "roi_pct": round(optimistic["roi_pct"] - conservative["roi_pct"], 4),
        "max_dd": round(optimistic["max_drawdown"] - conservative["max_drawdown"], 6),
        "total_trades": optimistic["total_trades"] - conservative["total_trades"],
    }
    band_for_summary = band_opt if len(band_opt) >= len(band_con) else band_con

    return {
        "run_id_base": run_id,
        "optimistic": optimistic,
        "conservative": conservative,
        "delta": delta,
        "sl_band": summarize_sl_band(band_for_summary),
    }


def write_band_csv(records: list[SLBandRecord], path: Path) -> None:
    """Write SL band records to CSV."""
    if not records:
        path.write_text("# no SL triggers\n")
        return
    fieldnames = list(records[0].to_dict().keys())
    with open(path, "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            writer.writerow(record.to_dict())


def parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="SL Fill Sensitivity - dual-run comparison")
    parser.add_argument(
        "--data-dir", default="data/processed", help="Data directory")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--timeframe", default="5m")
    parser.add_argument("--start", type=parse_date,
                        required=True, help="Start date YYYY-MM-DD")
    parser.add_argument("--end", type=parse_date,
                        required=True, help="End date YYYY-MM-DD")
    parser.add_argument("--initial-balance", type=float, default=1000.0)
    parser.add_argument("--sl-min-bps", type=float,
                        default=5.0, help="Optimistic min slippage bps")
    parser.add_argument("--slippage-bps", type=float,
                        default=2.0, help="General market slippage bps")
    parser.add_argument("--run-id", default=None,
                        help="Run ID label (auto-generated if omitted)")
    parser.add_argument(
        "--out-dir", default="reports/sensitivity", help="Output directory")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

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

    compare = build_compare_json(res_opt, res_con, band_opt, band_con, run_id)
    json_path = out_dir / "sl_fill_sensitivity.json"
    json_path.write_text(json.dumps(compare, indent=2, default=str))
    LOG.info(f"Wrote {json_path}")

    csv_path = out_dir / "sl_orders_band.csv"
    write_band_csv(band_opt + band_con, csv_path)
    LOG.info(f"Wrote {csv_path}")

    print("\n" + "=" * 60)
    print(f"SL FILL SENSITIVITY - {run_id}")
    print("=" * 60)
    print(
        f"  Optimistic  end_equity: {res_opt.end_balance:>12.2f}  ROI: {res_opt.roi_pct:>7.2f}%  DD: {res_opt.max_drawdown:>7.4f}")
    print(
        f"  Conservative end_equity: {res_con.end_balance:>12.2f}  ROI: {res_con.roi_pct:>7.2f}%  DD: {res_con.max_drawdown:>7.4f}")
    print(f"  Delta equity: {compare['delta']['end_equity']:>+12.2f}")
    print(f"  SL triggers: {compare['sl_band']['count_sl']}")
    if compare["sl_band"]["count_sl"] > 0:
        print(
            f"  p50 slip opt/cons: {compare['sl_band']['p50_slip_bps_opt']:.1f} / "
            f"{compare['sl_band']['p50_slip_bps_cons']:.1f} bps"
        )
        print(
            f"  p95 slip opt/cons: {compare['sl_band']['p95_slip_bps_opt']:.1f} / "
            f"{compare['sl_band']['p95_slip_bps_cons']:.1f} bps"
        )
    print(f"  Output: {out_dir}")
    print("=" * 60)


if __name__ == "__main__":
    main()
