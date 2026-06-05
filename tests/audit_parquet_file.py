"""
Audit freshly enriched parquet file for required columns and non-zero content.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import polars as pl


def _find_latest_enriched(processed_dir: Path, symbol: str, timeframe: str) -> Path:
    primary = processed_dir / symbol / timeframe
    fallback = processed_dir / symbol / "klines" / timeframe

    for base in (primary, fallback):
        if not base.exists():
            continue
        files = sorted(base.glob("*_enriched.parquet"))
        if files:
            return files[-1]

    raise FileNotFoundError(
        f"No _enriched.parquet found under {primary} or {fallback}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit enriched parquet for non-zero orderflow")
    parser.add_argument("--processed", default="data/processed", help="Processed data dir")
    parser.add_argument("--symbol", default="BTCUSDT", help="Symbol, e.g. BTCUSDT")
    parser.add_argument("--timeframe", default="5m", help="Timeframe, e.g. 5m")
    args = parser.parse_args()

    processed_dir = Path(args.processed)
    symbol = str(args.symbol).upper()
    timeframe = str(args.timeframe)

    target = _find_latest_enriched(processed_dir, symbol, timeframe)
    df = pl.read_parquet(str(target))

    required = {"avg_bid_qty", "tfi", "buy_volume"}
    missing = required.difference(df.columns)
    if missing:
        raise AssertionError(f"Missing required columns: {sorted(missing)} in {target}")

    avg_bid_qty_mean = float(df.select(pl.col("avg_bid_qty").mean()).item())
    avg_bid_qty_max = float(df.select(pl.col("avg_bid_qty").max()).item())
    buy_volume_mean = float(df.select(pl.col("buy_volume").mean()).item())
    buy_volume_max = float(df.select(pl.col("buy_volume").max()).item())

    print(f"File: {target}")
    print(f"avg_bid_qty mean={avg_bid_qty_mean:.6f} max={avg_bid_qty_max:.6f}")
    print(f"buy_volume mean={buy_volume_mean:.6f} max={buy_volume_max:.6f}")

    if avg_bid_qty_max == 0.0 or buy_volume_max == 0.0:
        raise ValueError("Data generation failed: max == 0 for avg_bid_qty or buy_volume")

    print("✅ Data Quality PASS")


if __name__ == "__main__":
    main()
