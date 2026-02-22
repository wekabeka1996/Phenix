"""
Data Converter Module
=====================

Responsible for converting raw CSV data (Binance format) into optimized Parquet files
for the backtesting engine. Supports klines, aggTrades, bookTicker, and fundingRate.
"""

import logging
from pathlib import Path
from typing import Optional, List, Union

import polars as pl

LOG = logging.getLogger(__name__)


class DataConverter:
    """
    Converts raw Binance CSV data to strict schema Parquet files.
    """

    def __init__(self):
        # Configuration could be injected here if needed
        pass

    def convert(
        self,
        symbol: str,
        data_type: str,
        source_dir: str,
        target_dir: str,
        timeframe: Optional[str] = None,
        max_date: Optional[str] = None,
    ) -> None:
        """
        Convert raw CSV files to Parquet.

        Args:
            symbol: Asset symbol (e.g., "BTCUSDT")
            data_type: Type of data ("klines", "aggTrades", "bookTicker", "fundingRate")
            source_dir: Directory containing raw CSV/ZIP files
            target_dir: Base directory for output
            timeframe: Optional timeframe (required for "klines")
            max_date: Optional upper bound date string "YYYY-MM"; files with date > max_date are skipped
        """
        source_path = Path(source_dir)
        target_base = Path(target_dir)

        if not source_path.exists():
            LOG.error(f"Source directory not found: {source_path}")
            return

        # Locate files (flat or nested)
        files = self._locate_files(source_path, symbol, data_type, timeframe, max_date)
        if not files:
            LOG.warning(f"No files found for {symbol} {data_type} in {source_path}")
            return

        LOG.info(f"Processing {len(files)} files for {symbol} [{data_type}]...")

        for file_path in files:
            try:
                self._process_single_file(file_path, symbol, data_type, target_base, timeframe)
            except Exception as e:
                LOG.error(f"Failed to process {file_path.name}: {e}")

    def _locate_files(self, source_path: Path, symbol: str, data_type: str, timeframe: Optional[str], max_date: Optional[str] = None) -> List[Path]:
        """Locate files matching the pattern in the source directory."""
        import re

        def _extract_date(filename: str) -> Optional[str]:
            m = re.search(r'(\d{4}-\d{2})(?:\.zip|\.csv)$', filename)
            return m.group(1) if m else None

        # 1. Try finding pattern in the source_path directly (flat)
        valid_patterns = []
        
        if data_type == "klines" and timeframe:
             valid_patterns.append(f"{symbol}-{timeframe}-*.csv")
             valid_patterns.append(f"{symbol}-{timeframe}-*.zip")
        elif data_type in ["aggTrades", "bookTicker", "fundingRate"]:
             valid_patterns.append(f"{symbol}-{data_type}-*.csv")
             valid_patterns.append(f"{symbol}-{data_type}-*.zip")
             # Fallback for some non-standard naming if necessary
             valid_patterns.append(f"{symbol}-*-{data_type}-*.csv")

        files = []
        for pattern in valid_patterns:
            files.extend(sorted(source_path.glob(pattern)))

        # 2. If no flat files, check for nested directories (Symbol/Timeframe or DataType folders)
        if not files:
            # Common structure: source_dir/BTCUSDT/5m/*.csv
            if data_type == "klines" and timeframe:
                nested_path = source_path / symbol / timeframe
                if nested_path.exists():
                    files.extend(sorted(nested_path.glob("*.csv")) + sorted(nested_path.glob("*.zip")))
            
            # Or flattening variants?

        # Filter by max_date if specified
        if max_date:
            files = [f for f in files if (_extract_date(f.name) or "") <= max_date]

        return sorted(list(set(files)))

    def _process_single_file(
        self,
        file_path: Path,
        symbol: str,
        data_type: str,
        target_base: Path,
        timeframe: Optional[str]
    ) -> None:
        """Extract zip (if needed) to a temp file, scan lazily, stream to Parquet."""
        if file_path.stat().st_size < 100:
            LOG.warning(f"File too small, skipping: {file_path.name}")
            return

        temp_path: Optional[Path] = None
        try:
            result = self._read_and_enforce_schema(file_path, symbol, data_type)
            if result is None:
                return
            lf, temp_path = result

            ts_col = self._get_timestamp_col(data_type, lf)
            if not ts_col:
                LOG.warning(f"Could not determine timestamp column for {data_type}")
                return

            # Sample first row only to derive the month string for output filename
            try:
                sample_df = lf.select(pl.col(ts_col)).head(1).collect()
                if sample_df.height == 0:
                    return
                ts_sample = sample_df[ts_col][0]
                month_str = ts_sample.strftime("%Y-%m")
            except Exception as e:
                LOG.error(f"Failed to sample timestamp for filename generation: {e}")
                return

            if data_type == "klines":
                if not timeframe:
                    LOG.error("Timeframe required for klines output path")
                    return
                output_dir = target_base / symbol / "klines" / timeframe
            else:
                output_dir = target_base / symbol / data_type

            output_dir.mkdir(parents=True, exist_ok=True)
            output_file = output_dir / f"{month_str}.parquet"

            LOG.info(f"Converting {file_path.name} -> {output_file}...")
            try:
                # sink_parquet streams lazily — no full collect into memory
                lf.sink_parquet(str(output_file), compression="snappy")
                rows = pl.scan_parquet(str(output_file)).select(pl.len()).collect().item()
                LOG.info(f"Finished writing {output_file} ({rows} rows)")
            except Exception as e:
                LOG.error(f"Write failed: {e}")
        finally:
            if temp_path is not None and temp_path.exists():
                temp_path.unlink(missing_ok=True)

    def _read_and_enforce_schema(
        self, file_path: Path, symbol: str, data_type: str
    ) -> Optional[tuple]:
        """
        Returns (LazyFrame, Optional[temp_Path]).
        For ZIP sources, extracts inner CSV to a NamedTemporaryFile so scan_csv
        can stream it without loading the whole file into memory.
        The caller is responsible for deleting the temp file when done.
        """
        
        # 1. Define Schemas
        schemas = {
            "klines": [
                "open_time", "open", "high", "low", "close", "volume",
                "close_time", "quote_volume", "count",
                "taker_buy_volume", "taker_buy_quote_volume", "ignore"
            ],
            "aggTrades": [
                "agg_trade_id", "price", "quantity", "first_trade_id",
                "last_trade_id", "trans_time", "is_buyer_maker", "best_match"
            ],
            "bookTicker": [
                "update_id", "best_bid_price", "best_bid_qty",
                "best_ask_price", "best_ask_qty", "transaction_time", "event_time"
            ],
            "fundingRate": [
                "calc_time", "funding_interval_hours", "last_funding_rate"
            ]
        }

        if data_type not in schemas:
            LOG.error(f"Unsupported data_type: {data_type}")
            return None

        col_names = schemas[data_type]

        # 2. Sniff header — must handle both plain CSV and ZIP archives
        import zipfile

        def _read_first_line(fp: Path) -> str:
            try:
                if fp.suffix.lower() == ".zip":
                    with zipfile.ZipFile(fp) as zf:
                        inner = [n for n in zf.namelist() if n.lower().endswith(".csv")]
                        if not inner:
                            return ""
                        with zf.open(inner[0]) as f:
                            return f.readline().decode("utf-8", errors="replace").strip().lower()
                else:
                    with open(fp, "r", encoding="utf-8", errors="replace") as f:
                        return f.readline().strip().lower()
            except Exception:
                return ""

        first_line = _read_first_line(file_path)
        has_header_row = bool(first_line and col_names[0].lower() in first_line)

        # 3. Scan (Lazy) — extract zip to a temp file so scan_csv can stream it
        # without loading the entire compressed content into memory.
        import tempfile
        import shutil
        temp_path: Optional[Path] = None
        try:
            if file_path.suffix.lower() == ".zip":
                with zipfile.ZipFile(file_path) as zf:
                    inner = [n for n in zf.namelist() if n.lower().endswith(".csv")]
                    if not inner:
                        raise ValueError(f"No CSV inside zip: {file_path}")
                    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".csv")
                    tmp.close()
                    temp_path = Path(tmp.name)
                    # Stream-copy chunk by chunk — avoids loading whole file into RAM
                    with zf.open(inner[0]) as src, open(temp_path, "wb") as dst:
                        shutil.copyfileobj(src, dst)
                csv_path = temp_path
            else:
                csv_path = file_path

            lf = pl.scan_csv(csv_path, has_header=has_header_row, infer_schema_length=0)
            curr_cols = lf.collect_schema().names()
            take = min(len(curr_cols), len(col_names))
            lf = lf.select(curr_cols[:take])
            mapping = dict(zip(curr_cols[:take], col_names[:take]))
            lf = lf.rename(mapping)
        except Exception as e:
            LOG.error(f"Scan error {file_path}: {e}")
            if temp_path and temp_path.exists():
                temp_path.unlink(missing_ok=True)
            return None

        # 4. Enforce Schema & Cast
        try:
            if data_type == "klines":
                lf = lf.select([
                    pl.col("open_time").cast(pl.Int64).cast(pl.Datetime("ms")),
                    pl.col("open").cast(pl.Float64),
                    pl.col("high").cast(pl.Float64),
                    pl.col("low").cast(pl.Float64),
                    pl.col("close").cast(pl.Float64),
                    pl.col("volume").cast(pl.Float64),
                    pl.col("close_time").cast(pl.Int64).cast(pl.Datetime("ms")),
                    pl.col("quote_volume").cast(pl.Float64),
                    pl.col("count").cast(pl.UInt32),
                    pl.col("taker_buy_volume").cast(pl.Float64),
                    pl.col("taker_buy_quote_volume").cast(pl.Float64)
                ])
            elif data_type == "aggTrades":
                avail = set(lf.collect_schema().names())
                ts_name = "trans_time" if "trans_time" in avail else ("transact_time" if "transact_time" in avail else None)
                if ts_name is None:
                    raise ValueError(
                        "aggTrades missing timestamp column: expected 'trans_time' or 'transact_time'"
                    )

                # Some Binance exports encode booleans as strings ("true"/"false") or 0/1.
                # Polars cannot always cast Utf8View -> Boolean directly, so normalize explicitly.
                is_buyer_maker_bool = (
                    pl.when(pl.col("is_buyer_maker").is_null())
                    .then(None)
                    .when(
                        pl.col("is_buyer_maker")
                        .cast(pl.Utf8)
                        .str.to_lowercase()
                        .is_in(["true", "1", "t", "yes", "y"])
                    )
                    .then(True)
                    .otherwise(False)
                    .cast(pl.Boolean)
                )
                lf = lf.select([
                    pl.col("agg_trade_id").cast(pl.Int64),
                    pl.col("price").cast(pl.Float64),
                    pl.col("quantity").cast(pl.Float64),
                    pl.col("first_trade_id").cast(pl.Int64),
                    pl.col("last_trade_id").cast(pl.Int64),
                    # Some exports use 'transact_time'; normalize to 'trans_time'
                    pl.col(ts_name).cast(pl.Int64).cast(pl.Datetime("ms")).alias("trans_time"),
                    is_buyer_maker_bool.alias("is_buyer_maker"),
                ])
            elif data_type == "bookTicker":
                lf = lf.select([
                    pl.col("update_id").cast(pl.Int64),
                    pl.col("best_bid_price").cast(pl.Float64),
                    pl.col("best_bid_qty").cast(pl.Float64),
                    pl.col("best_ask_price").cast(pl.Float64),
                    pl.col("best_ask_qty").cast(pl.Float64),
                    pl.col("transaction_time").cast(pl.Int64).cast(pl.Datetime("ms")),
                    pl.col("event_time").cast(pl.Int64).cast(pl.Datetime("ms"))
                ])
            elif data_type == "fundingRate":
                lf = lf.select([
                    pl.col("calc_time").cast(pl.Int64).cast(pl.Datetime("ms")),
                    pl.col("funding_interval_hours").cast(pl.Float64),
                    pl.col("last_funding_rate").cast(pl.Float64)
                ])
                
            # Add metadata
            lf = lf.with_columns(pl.lit(symbol).cast(pl.Categorical).alias("symbol"))
            return lf, temp_path

        except Exception as e:
            LOG.error(f"Schema enforcement failed for {file_path}: {e}")
            if temp_path and temp_path.exists():
                temp_path.unlink(missing_ok=True)
            return None

    def _get_timestamp_col(self, data_type: str, lf: pl.LazyFrame) -> Optional[str]:
        """Return the primary timestamp column name."""
        if data_type == "klines": return "open_time"
        if data_type == "aggTrades": return "trans_time"
        if data_type == "bookTicker": return "transaction_time"
        if data_type == "fundingRate": return "calc_time"
        return lf.columns[0] # Fallback
