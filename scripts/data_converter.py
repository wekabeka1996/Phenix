#!/usr/bin/env python3
"""
Data ETL Phase 1: Raw CSV to Parquet Converter
==============================================

Strict Format Converter for Binance Data.
Decoupled from feature engineering.
"""

import os
import argparse
import glob
import logging
from typing import Optional
from pathlib import Path

import polars as pl

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
LOG = logging.getLogger("DataConverter")


class DataConverter:
    """
    Converts raw Binance CSV data to strict schema Parquet files.
    """

    def __init__(self, base_output_dir: str = "data/processed"):
        self.base_output_dir = Path(base_output_dir)
        self.base_output_dir.mkdir(parents=True, exist_ok=True)

    def convert(self, input_dir: str, symbol: str, timeframe: str, dataset_type: str = "klines"):
        """
        Convert a folder of CSV files to Parquet.
        
        Args:
            input_dir: Path to directory containing CSVs
            symbol: Asset symbol (e.g., BTCUSDT)
            timeframe: Timeframe (e.g., 5m, 1h) - used for directory structure
            dataset_type: Type of data ('klines', 'aggTrades', 'bookTicker', 'fundingRate')
        """
        input_path = Path(input_dir)
        if not input_path.exists():
            LOG.error(f"Input directory not found: {input_path}")
            return

        # Pattern matching for CSV files
        files = sorted(list(input_path.glob("*.csv"))) + sorted(list(input_path.glob("*.zip")))
        if not files:
            LOG.warning(f"No CSV/ZIP files found in {input_path}")
            return

        LOG.info(f"Submitting {len(files)} files for processing in {dataset_type} mode...")

        for file_path in files:
            try:
                self._process_single_file(file_path, symbol, timeframe, dataset_type)
            except Exception as e:
                LOG.error(f"Failed to process {file_path.name}: {e}")

    def convert_files(self, files: list[Path], symbol: str, timeframe: str, dataset_type: str = "klines"):
        """
        Convert a specific list of files to Parquet.
        """
        if not files:
            LOG.warning("No files provided to convert_files")
            return

        LOG.info(f"Submitting {len(files)} flat files for processing in {dataset_type} mode...")

        for file_path in files:
            try:
                self._process_single_file(file_path, symbol, timeframe, dataset_type)
            except Exception as e:
                LOG.error(f"Failed to process {file_path.name}: {e}")

    def _process_single_file(self, file_path: Path, symbol: str, timeframe: str, dataset_type: str):
        """Process a single CSV file and write to Parquet."""
        
        # 1. Read CSV (Lazy for larger files support, or eager for simple schema enforcement)
        # Using scan_csv for efficiency, but read_csv is safer for robust typing on small chunks
        # Binance monthly files are manageable (approx 50MB-500MB).
        
        # Define Schema based on dataset_type
        # Columns based on official Binance Data Collection format
        
        schema_overrides = {}
        new_columns = []
        
        if dataset_type == "klines":
            # Sniff header
            try:
                with open(file_path, "r") as f:
                    first_line = f.readline().strip()
            except Exception:
                first_line = ""
            
            has_header_row = "open_time" in first_line.lower() or "opentime" in first_line.lower()
            
            col_names = [
                "open_time", "open", "high", "low", "close", "volume", 
                "close_time", "quote_volume", "count", 
                "taker_buy_volume", "taker_buy_quote_volume", "ignore"
            ]
            
            try:
                if has_header_row:
                    LOG.info(f"Detected header in {file_path.name}, reading with header=True")
                    # If file has header, we read it with header=True. 
                    # If the header names map 1:1 to what we expect, great.
                    # If not, we might need to rename.
                    df = pl.read_csv(file_path, has_header=True, infer_schema_length=0) # 0 to read all as str first for safety? No, let auto inference work but check columns
                    
                    # Normalize column names if necessary
                    # For now assume standard binance header or map by index if strict
                    if len(df.columns) == len(col_names):
                        df.columns = col_names
                else:
                    df = pl.read_csv(
                        file_path, 
                        has_header=False,
                        new_columns=col_names,
                        infer_schema_length=10000
                    )
            except Exception as e:
                LOG.error(f"Read CSV failed: {e}")
                raise e
            
            # --- SCHEMA ENFORCEMENT ---
            # Cast using strptime if needed or strict cast
            # If timestamp is already int, cast to Int64 -> Datetime
            # If timestamp is '2023-01-01...', need strptime
            
            # Helper to cast column safely
            def safe_cast_ts(col_name):
                # Try strict cast to Int64 (unix ms)
                # If fail, assume string date
                return pl.col(col_name).cast(pl.Int64, strict=False).cast(pl.Datetime("ms")).fill_null(
                    pl.col(col_name).str.to_datetime("%Y-%m-%d %H:%M:%S", strict=False) # Fallback format?
                ) 
                # Actually, strictly enforcing Binance data: it is usually Unix MS (int)
                # But if we read as string, cast(pl.Int64) handles string "1600000" -> int
            
            df = df.select([
                pl.col("open_time").cast(pl.Int64).cast(pl.Datetime("ms")).alias("open_time"),
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
            
            # Add symbol categorical
            df = df.with_columns(pl.lit(symbol).cast(pl.Categorical).alias("symbol"))

        elif dataset_type == "bookTicker":
            # update_id,best_bid_price,best_bid_qty,best_ask_price,best_ask_qty,transaction_time,event_time
            # Standard binance bookTicker header usually present in recent data
            col_names = [
                "update_id", "best_bid_price", "best_bid_qty", 
                "best_ask_price", "best_ask_qty", "transaction_time", "event_time"
            ]
            
            # Simple read with auto-schema first, then enforce
            try:
                df = pl.read_csv(file_path, has_header=True, infer_schema_length=10000)
                # Rename if needed (e.g. if csv has camelCase headers vs snake_case expected)
                df.columns = [c.lower() for c in df.columns] 
                # Check mapping? For now rely on auto-match or positional if no header
                if len(df.columns) == len(col_names) and "update_id" not in df.columns:
                     df.columns = col_names
            except Exception:
                df = pl.read_csv(file_path, has_header=False, new_columns=col_names)

            df = df.select([
                pl.col("update_id").cast(pl.Int64),
                pl.col("best_bid_price").cast(pl.Float64),
                pl.col("best_bid_qty").cast(pl.Float64),
                pl.col("best_ask_price").cast(pl.Float64),
                pl.col("best_ask_qty").cast(pl.Float64),
                pl.col("transaction_time").cast(pl.Int64).cast(pl.Datetime("ms")),
                pl.col("event_time").cast(pl.Int64).cast(pl.Datetime("ms"))
            ])
            df = df.with_columns(pl.lit(symbol).cast(pl.Categorical).alias("symbol"))

        elif dataset_type == "fundingRate":
            # calc_time,funding_interval_hours,last_funding_rate
            col_names = ["calc_time", "funding_interval_hours", "last_funding_rate"]
            try:
                df = pl.read_csv(file_path, has_header=True, infer_schema_length=10000)
                df.columns = [c.lower() for c in df.columns]
                if len(df.columns) == len(col_names) and "calc_time" not in df.columns:
                     df.columns = col_names
            except Exception:
                df = pl.read_csv(file_path, has_header=False, new_columns=col_names)

            df = df.select([
                pl.col("calc_time").cast(pl.Int64).cast(pl.Datetime("ms")),
                pl.col("funding_interval_hours").cast(pl.Float64), # or Int but rate might imply float interval? usually int hours.
                pl.col("last_funding_rate").cast(pl.Float64)
            ])
            df = df.with_columns(pl.lit(symbol).cast(pl.Categorical).alias("symbol"))

        elif dataset_type == "aggTrades":
             # Sniff header
            try:
                with open(file_path, "r") as f:
                    first_line = f.readline().strip()
            except Exception:
                first_line = ""

            has_header_row = "agg_trade_id" in first_line.lower() or "price" in first_line.lower()

            col_names = [
                "agg_trade_id", "price", "quantity", "first_trade_id", 
                "last_trade_id", "trans_time", "is_buyer_maker", "best_match"
            ]
            
            if has_header_row:
                 df = pl.read_csv(file_path, has_header=True, infer_schema_length=10000)
                 if len(df.columns) >= 7:
                     # Assign first 7-8 names
                     limit = min(len(df.columns), len(col_names))
                     current_cols = df.columns
                     rename_map = {current_cols[i]: col_names[i] for i in range(limit)}
                     df = df.rename(rename_map)
            else:
                df = pl.read_csv(
                    file_path, 
                    has_header=False,
                    new_columns=col_names,
                    infer_schema_length=10000
                )
            
            df = df.select([
                pl.col("agg_trade_id").cast(pl.Int64),
                pl.col("price").cast(pl.Float64),
                pl.col("quantity").cast(pl.Float64),
                pl.col("first_trade_id").cast(pl.Int64),
                pl.col("last_trade_id").cast(pl.Int64),
                pl.col("trans_time").cast(pl.Int64).cast(pl.Datetime("ms")),
                pl.col("is_buyer_maker").cast(pl.Boolean)
            ])
            
            df = df.with_columns(pl.lit(symbol).cast(pl.Categorical).alias("symbol"))

        else:
            LOG.warning(f"Dataset type {dataset_type} not fully implemented yet. Skipping.")
            return

        # --- PARTITIONING & WRITE ---
        # Generate output filename
        # Strategy: partition by YYYY-MM based on the data content (robust)
        # Verify timestamps to determine partition
        
        # Just use the first timestamp to determine the partition name if we keep file:file mapping
        # Or re-partition entirely.
        # User requirement: "Output structure: data/processed/{symbol}/{timeframe}/{month}.parquet"
        
        # We can detect month from data
        if df.height > 0:
            if dataset_type == "klines":
                ts_col = "open_time"
            elif dataset_type == "aggTrades":
                ts_col = "trans_time"
            elif dataset_type == "bookTicker":
                ts_col = "transaction_time" # or event_time
            elif dataset_type == "fundingRate":
                ts_col = "calc_time"
            else:
                ts_col = df.columns[0] # Fallback
                
            ts_sample = df[ts_col][0]
            month_str = ts_sample.strftime("%Y-%m") # e.g. 2024-01
            
            output_subdir = self.base_output_dir / symbol / timeframe
            output_subdir.mkdir(parents=True, exist_ok=True)
            
            # Check if file covers multiple months (unlikely for Binance monthly CSVs, but possible for dump)
            # If strictly monthly CSVs, we can just save one parquet.
            
            output_file = output_subdir / f"{month_str}.parquet"
            
            LOG.info(f"Writing {output_file} ({df.height} rows)...")
            df.write_parquet(output_file, compression="snappy")
        else:
            LOG.warning(f"Empty dataframe for {file_path}")


def main():
    parser = argparse.ArgumentParser(description="Phenix Data Converter")
    parser.add_argument("--symbol", type=str, required=True, help="Asset symbol (e.g., BTCUSDT)")
    parser.add_argument("--timeframe", type=str, required=True, help="Timeframe (e.g., 5m)")
    parser.add_argument("--input_base", type=str, default="data/raw", help="Base directory for raw data")
    parser.add_argument("--output_base", type=str, default="data/processed", help="Base directory for processed outputs")
    parser.add_argument("--type", type=str, default="klines", choices=["klines", "aggTrades", "bookTicker", "fundingRate"], help="Dataset type")
    
    args = parser.parse_args()
    
    # Construct input path expectation
    # Try different common patterns
    possible_paths = [
        Path(args.input_base) / args.symbol / args.timeframe,
        Path(args.input_base) / args.timeframe / args.symbol,  # As per user hint
        Path(args.input_base) / f"{args.symbol}-{args.timeframe}" # Flattened
    ]
    
    target_dir = None
    files_to_process = []
    
    # Strategy 1: Look for specific subdirectories THAT CONTAIN CSV/ZIPs
    for p in possible_paths:
        if p.exists() and p.is_dir():
            # Check if it has content (files)
            if list(p.glob("*.csv")) or list(p.glob("*.zip")):
                target_dir = p
                break
            
    # Strategy 2: Look for flat files in input_base matching pattern
    if not target_dir: # Only if no valid directory found
        input_base_path = Path(args.input_base)
        if input_base_path.exists():
            # Pattern: symbol-timeframe-*.csv (e.g. BTCUSDT-5m-2023-05.csv)
            # Also support symbol-timeframe.csv
            pattern1 = f"{args.symbol}-*-{args.type}-*.csv" if args.type != "klines" else f"{args.symbol}-{args.timeframe}-*.csv"
            # Fallback for generic naming
            pattern2 = f"{args.symbol}-{args.timeframe}.csv"
            
            # Special case for non-timeframe specific datasets (aggTrades often just symbol-aggTrades-month)
            if args.type in ["aggTrades", "bookTicker", "fundingRate"]:
                 pattern3 = f"{args.symbol}-{args.type}-*.csv"
                 flat_files = sorted(list(input_base_path.glob(pattern3)))
            else:
                 flat_files = sorted(list(input_base_path.glob(pattern1))) + sorted(list(input_base_path.glob(pattern2)))

            if flat_files:
                LOG.info(f"Found {len(flat_files)} flat files in {input_base_path} matching pattern for {args.type}.")
                files_to_process = flat_files
                target_dir = input_base_path # Just for reference

    if not target_dir and not files_to_process:
        LOG.error(f"Could not find input directory or files for {args.symbol} {args.timeframe}. Checked: {possible_paths} and flat patterns in {args.input_base}")
        return

    converter = DataConverter(base_output_dir=args.output_base)
    
    if files_to_process:
         converter.convert_files(files_to_process, args.symbol, args.timeframe, args.type)
    else:
         converter.convert(str(target_dir), args.symbol, args.timeframe, args.type)
    
    LOG.info("Conversion complete.")


if __name__ == "__main__":
    main()
