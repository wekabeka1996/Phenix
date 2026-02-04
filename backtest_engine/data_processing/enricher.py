"""
Backtest Data Enricher
=====================

Fuses processed `klines` (OHLCV) with processed `aggTrades` and `bookTicker` (Order Book)
to create a high-fidelity dataset for backtests.

Why:
- FeatureEngineering warmup/readiness requires trade-flow inputs:
  buy/sell volumes + trade counts + notionals.
- OHLCV alone cannot provide these exactly.
- `aggTrades` contains the required microstructure signals (taker side).
- `bookTicker` contains the Order Book state (Spread, Depth).

Output:
- Writes enriched klines parquet alongside the original as: `YYYY-MM_enriched.parquet`
  to avoid losing the base file and to allow the engine to prefer enriched files.
"""

from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

import polars as pl

LOG = logging.getLogger(__name__)


@dataclass(frozen=True)
class EnrichmentResult:
    symbol: str
    timeframe: str
    month: str
    klines_in: Path
    aggtrades_in: Path
    bookticker_in: Optional[Path]
    klines_out: Path
    rows_klines: int
    rows_aggtrades: int
    rows_bookticker: int


def _month_key_from_path(p: Path) -> str:
    stem = p.stem
    if stem.endswith("_enriched"):
        stem = stem[: -len("_enriched")]
    return stem


def enrich_month(
    *,
    klines_file: Path,
    aggtrades_file: Path,
    bookticker_file: Optional[Path] = None,
    timeframe: str,
    output_file: Path,
) -> EnrichmentResult:
    """
    Enrich one month of klines with one month of aggTrades and optional bookTicker.
    
    Performs a "Triple Merge":
    1. Klines (Base)
    2. AggTrades (Flow)
    3. BookTicker (Depth/Spread)
    """
    if not klines_file.exists():
        raise FileNotFoundError(f"Missing klines file: {klines_file}")
    if not aggtrades_file.exists():
        raise FileNotFoundError(f"Missing aggTrades file: {aggtrades_file}")
    if bookticker_file is not None and not bookticker_file.exists():
        bookticker_file = None

    # Lazy scanning for efficiency
    kl = pl.scan_parquet(str(klines_file))
    at = pl.scan_parquet(str(aggtrades_file))
    bt = pl.scan_parquet(str(bookticker_file)) if bookticker_file is not None else None

    def _normalize_time(lf: pl.LazyFrame, col: str) -> pl.LazyFrame:
        dtype = lf.collect_schema().get(col)
        if isinstance(dtype, pl.Datetime):
            return lf.with_columns(pl.col(col).cast(pl.Datetime("ms")).alias(col))
        if isinstance(dtype, pl.Date):
            return lf.with_columns(pl.col(col).cast(pl.Datetime("ms")).alias(col))

        col_expr = pl.col(col).cast(pl.Int64)
        # Normalize epoch to milliseconds based on magnitude
        ms_expr = (
            pl.when(col_expr >= 1_000_000_000_000_000_000)
            .then((col_expr / 1_000_000).cast(pl.Int64))
            .when(col_expr >= 1_000_000_000_000_000)
            .then((col_expr / 1_000).cast(pl.Int64))
            .when(col_expr >= 1_000_000_000_000)
            .then(col_expr)
            .otherwise((col_expr * 1_000).cast(pl.Int64))
        )

        return lf.with_columns(pl.from_epoch(ms_expr, time_unit="ms").alias(col))

    # Validate required columns early via parquet metadata (no collect yet).
    kl_cols = set(kl.collect_schema().names())
    at_cols = set(at.collect_schema().names())
    for c in ("open_time", "close_time", "open", "high", "low", "close", "volume"):
        if c not in kl_cols:
            raise ValueError(f"klines missing required column: {c} in {klines_file}")
    for c in ("trans_time", "price", "quantity", "is_buyer_maker"):
        if c not in at_cols:
            raise ValueError(f"aggTrades missing required column: {c} in {aggtrades_file}")

    if bt is not None:
        bt_cols = set(bt.collect_schema().names())
        # Support both 'best_bid_qty' (standard) and 'bidQty' (raw style) if needed
        # But we assume processed parquet has standardized names.
        # Checking for standard internal schema keys.
        required_bt = ["transaction_time", "best_bid_price", "best_bid_qty", "best_ask_price", "best_ask_qty"]
        missing_bt = [c for c in required_bt if c not in bt_cols]
        if missing_bt:
            LOG.warning(f"bookTicker missing columns {missing_bt} in {bookticker_file}; skipping bookTicker enrichment")
            bt = None

    # Normalize time columns to Datetime(ms)
    kl = _normalize_time(kl, "open_time")
    at = _normalize_time(at, "trans_time").sort("trans_time")
    if bt is not None:
        bt = _normalize_time(bt, "transaction_time").sort("transaction_time")

    # --- Aggregation: AggTrades ---
    # Aggregate trades into time buckets aligned to kline open_time.
    # BUY = taker buy => is_buyer_maker == False (seller is maker)
    is_taker_buy = ~pl.col("is_buyer_maker")
    notional = pl.col("price") * pl.col("quantity")

    agg = (
        at.select(
            [
                pl.col("trans_time"),
                pl.col("quantity").cast(pl.Float64),
                pl.col("price").cast(pl.Float64),
                pl.col("is_buyer_maker").cast(pl.Boolean),
            ]
        )
        .group_by_dynamic(
            index_column="trans_time",
            every=str(timeframe),
            period=str(timeframe),
            closed="left",
            label="left",
        )
        .agg(
            [
                pl.when(is_taker_buy).then(pl.col("quantity")).otherwise(0.0).sum().alias("buy_volume"),
                pl.when(~is_taker_buy).then(pl.col("quantity")).otherwise(0.0).sum().alias("sell_volume"),
                is_taker_buy.cast(pl.Int64).sum().alias("buy_count"),
                (~is_taker_buy).cast(pl.Int64).sum().alias("sell_count"),
                pl.when(is_taker_buy).then(notional).otherwise(0.0).sum().alias("buy_notional"),
                pl.when(~is_taker_buy).then(notional).otherwise(0.0).sum().alias("sell_notional"),
            ]
        )
        .rename({"trans_time": "open_time"})
    )

    # --- Aggregation: BookTicker ---
    # bookTicker is high-frequency; we do a dynamic group-by and join once per kline.
    if bt is not None:
        bt_agg = (
            bt.select(
                [
                    pl.col("transaction_time"),
                    pl.col("best_bid_qty").cast(pl.Float64),
                    pl.col("best_ask_qty").cast(pl.Float64),
                    pl.col("best_bid_price").cast(pl.Float64),
                    pl.col("best_ask_price").cast(pl.Float64),
                ]
            )
            .group_by_dynamic(
                index_column="transaction_time",
                every=str(timeframe),
                period=str(timeframe),
                closed="left",
                label="left",
            )
            .agg(
                [
                    # avg_bid_qty = Mean of bidQty within the window
                    pl.col("best_bid_qty").mean().alias("avg_bid_qty"),
                    # avg_ask_qty = Mean of askQty within the window
                    pl.col("best_ask_qty").mean().alias("avg_ask_qty"),
                    # last_bid_price = Last bidPrice in the window
                    pl.col("best_bid_price").last().alias("last_bid_price"),
                    # last_ask_price = Last askPrice in the window
                    pl.col("best_ask_price").last().alias("last_ask_price"),
                ]
            )
            .rename({"transaction_time": "open_time"})
        )
    else:
        bt_agg = None

    # --- Triple Merge ---
    # Join onto klines by open_time; fill nulls to 0 (no trades in interval).
    # 1. Start with Klines
    # 2. Left Join AggTrades
    # 3. Left Join BookTicker
    
    out_lf = (
        kl.join(agg, on="open_time", how="left")
        .with_columns(
            [
                pl.col("buy_volume").fill_null(0.0).cast(pl.Float64),
                pl.col("sell_volume").fill_null(0.0).cast(pl.Float64),
                pl.col("buy_notional").fill_null(0.0).cast(pl.Float64),
                pl.col("sell_notional").fill_null(0.0).cast(pl.Float64),
                pl.col("buy_count").fill_null(0).cast(pl.Int64),
                pl.col("sell_count").fill_null(0).cast(pl.Int64),
            ]
        )
        .with_columns(
            [
                (pl.col("buy_volume") - pl.col("sell_volume")).alias("tfi"),
            ]
        )
    )

    if bt_agg is not None:
        out_lf = (
            out_lf.join(bt_agg, on="open_time", how="left")
            .with_columns(
                [
                    pl.col("avg_bid_qty").fill_null(0.0).cast(pl.Float64),
                    pl.col("avg_ask_qty").fill_null(0.0).cast(pl.Float64),
                    pl.col("last_bid_price").fill_null(0.0).cast(pl.Float64),
                    pl.col("last_ask_price").fill_null(0.0).cast(pl.Float64),
                ]
            )
        )

    out = out_lf.collect(streaming=True)

    output_file.parent.mkdir(parents=True, exist_ok=True)
    out.write_parquet(str(output_file), compression="snappy")

    month = _month_key_from_path(klines_file)
    rows_bt = 0
    if bt is not None:
        # Quick count check for metadata
        try:
            rows_bt = int(pl.scan_parquet(str(bookticker_file)).select(pl.len()).collect().item())
        except Exception:
            pass

    return EnrichmentResult(
        symbol=str(klines_file.parents[2].name),
        timeframe=str(timeframe),
        month=month,
        klines_in=klines_file,
        aggtrades_in=aggtrades_file,
        bookticker_in=bookticker_file,
        klines_out=output_file,
        rows_klines=int(out.height),
        rows_aggtrades=int(pl.scan_parquet(str(aggtrades_file)).select(pl.len()).collect().item()),
        rows_bookticker=rows_bt
    )


def enrich_symbol_timeframe(
    *,
    processed_dir: Path,
    raw_dir: Path,
    symbol: str,
    timeframe: str,
    include_bookticker: bool = True,
    output_suffix: str = "_enriched",
    months: Optional[Iterable[str]] = None,
) -> list[EnrichmentResult]:
    """
    Enrich all months available for (symbol, timeframe) where both klines and aggTrades exist.
    Inputs can be located in data/processed or data/raw.
    Output is written to data/processed/{symbol}/{timeframe}/YYYY-MM_enriched.parquet
    """

    def _resolve_inputs(base_dir: Path) -> tuple[Path, Path, Path]:
        kl = base_dir / symbol / "klines" / timeframe
        at = base_dir / symbol / "aggTrades"
        bt = base_dir / symbol / "bookTicker"
        return kl, at, bt

    kl_dir, at_dir, bt_dir_standard = _resolve_inputs(processed_dir)
    if not kl_dir.exists() or not at_dir.exists():
        raw_kl, raw_at, raw_bt = _resolve_inputs(raw_dir)
        if raw_kl.exists() and raw_at.exists():
            kl_dir, at_dir, bt_dir_standard = raw_kl, raw_at, raw_bt
        else:
            if not kl_dir.exists():
                LOG.warning("No klines dir: %s", kl_dir)
            if not at_dir.exists():
                LOG.warning("No aggTrades dir: %s", at_dir)
            return []

    want = set(str(m) for m in months) if months is not None else None
    results: list[EnrichmentResult] = []

    for kl_file in sorted(kl_dir.glob("*.parquet")):
        month = _month_key_from_path(kl_file)
        if want is not None and month not in want:
            continue

        # Skip already-enriched inputs (idempotent)
        if kl_file.stem.endswith(output_suffix):
            continue

        at_file = at_dir / f"{month}.parquet"
        if not at_file.exists():
            LOG.warning("Skip %s %s %s: missing aggTrades month %s", symbol, timeframe, month, at_file)
            continue

        # Discovery Logic for BookTicker
        bt_file = None
        if include_bookticker:
            # 1. Check standard structure: symbol/bookTicker/YYYY-MM.parquet
            c1 = bt_dir_standard / f"{month}.parquet"
            if c1.exists():
                bt_file = c1
            else:
                # 2. Check for loose files in symbol dir or processed dir containing "bookTicker" and month
                # pattern: *bookTicker*2023-05*
                # Look in symbol root
                c2_list = list((processed_dir / symbol).glob(f"*{month}*bookTicker*.parquet"))
                if c2_list:
                    bt_file = c2_list[0]
        
        out_dir = processed_dir / symbol / timeframe
        out_file = out_dir / f"{month}{output_suffix}.parquet"
        
        bt_msg = f" + bookTicker({bt_file.name})" if bt_file else " (no bookTicker)"
        LOG.info("Enriching %s %s %s%s -> %s", symbol, timeframe, month, bt_msg, out_file.name)
        
        results.append(
            enrich_month(
                klines_file=kl_file,
                aggtrades_file=at_file,
                bookticker_file=bt_file,
                timeframe=timeframe,
                output_file=out_file,
            )
        )

    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Enrich processed klines with aggTrades and bookTicker")
    parser.add_argument("--processed", type=str, default="data/processed", help="Processed data dir")
    parser.add_argument("--symbol", type=str, required=True, help="Symbol, e.g. BTCUSDT")
    parser.add_argument("--timeframe", type=str, required=True, help="Kline timeframe, e.g. 5m")
    parser.add_argument("--month", type=str, default=None, help="Optional single month YYYY-MM")
    parser.add_argument(
        "--skip-bookticker",
        action="store_true",
        help="Skip bookTicker enrichment even if bookTicker parquet exists",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

    processed_dir = Path(args.processed)
    raw_dir = processed_dir.parent / "raw"
    months = [args.month] if args.month else None
    res = enrich_symbol_timeframe(
        processed_dir=processed_dir,
        raw_dir=raw_dir,
        symbol=str(args.symbol).upper(),
        timeframe=str(args.timeframe),
        include_bookticker=not args.skip_bookticker,
        months=months,
    )
    LOG.info("Enrichment complete: %d files", len(res))


if __name__ == "__main__":
    main()
