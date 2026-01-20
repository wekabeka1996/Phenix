"""Диагностика типов и значений временных колонок в parquet."""
from __future__ import annotations

import argparse
from pathlib import Path

import polars as pl


def _print_info(label: str, file_path: Path, col: str) -> None:
    lf = pl.scan_parquet(str(file_path))
    schema = lf.collect_schema()
    dtype = schema.get(col)
    print(f"[{label}] file={file_path}")
    print(f"[{label}] col={col} dtype={dtype}")
    sample = (
        lf.select(pl.col(col).head(5))
        .collect()
        .get_column(col)
        .to_list()
    )
    print(f"[{label}] first5={sample}")
    if sample and isinstance(sample[0], (int, float)):
        print(f"[{label}] digits={len(str(int(sample[0])))}")
    print("-")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--processed", default="data/processed")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--timeframe", default="5m")
    parser.add_argument("--month", default="2023-05")
    args = parser.parse_args()

    processed = Path(args.processed)
    symbol = str(args.symbol).upper()
    timeframe = str(args.timeframe)
    month = str(args.month)

    klines = processed / symbol / "klines" / timeframe / f"{month}.parquet"
    agg = processed / symbol / "aggTrades" / f"{month}.parquet"
    bt = processed / symbol / "bookTicker" / f"{month}.parquet"

    if not klines.exists() or not agg.exists():
        raise FileNotFoundError("Missing required parquet files for diagnostic")

    _print_info("klines", klines, "open_time")
    _print_info("aggTrades", agg, "trans_time")

    if bt.exists():
        _print_info("bookTicker", bt, "transaction_time")
    else:
        print("[bookTicker] file missing")


if __name__ == "__main__":
    main()
