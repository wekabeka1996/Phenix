#!/usr/bin/env python3
"""
Backtest Data Preparation Script
================================

Scans a source directory (default: data/raw) for Binance-formatted CSV/ZIP files,
identifies symbols and data types, and uses DataConverter to convert them 
into Parquet format for the BacktestEngine.

Usage:
    python scripts/prepare_backtest_data.py [--source data/raw] [--target data/processed]

"""

import argparse
import logging
import re
import sys
from pathlib import Path
from collections import defaultdict
from typing import NamedTuple, Optional, List, Set, Dict

# Add project root to path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

try:
    from tqdm import tqdm
except ImportError:
    print("tqdm not found. Installing...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "tqdm", "--break-system-packages"])
    from tqdm import tqdm

from backtest_engine.data_processing.data_converter import DataConverter
from backtest_engine.data_processing.enricher import enrich_symbol_timeframe

# Configure Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
LOG = logging.getLogger("DataPrep")

class DataTask(NamedTuple):
    symbol: str
    data_type: str
    timeframe: Optional[str]
    source_dir: Path

def parse_filename(filename: str) -> Optional[tuple[str, str, Optional[str]]]:
    """
    Heuristic to parse filename into (symbol, data_type, timeframe).
    Supported patterns:
    1. SYMBOL-TIMEFRAME-MONTH.csv (Klines) -> BTCUSDT-1m-2023-01.csv
    2. SYMBOL-aggTrades-MONTH.csv (AggTrades) -> BTCUSDT-aggTrades-2023-01.csv
    3. SYMBOL-bookTicker-MONTH.csv (BookTicker)
    """
    # 1. AggTrades / BookTicker / FundingRate (Explicit type)
    for dtype in ["aggTrades", "bookTicker", "fundingRate"]:
        if f"-{dtype}-" in filename:
            parts = filename.split(f"-{dtype}-")
            symbol = parts[0]
            # Verify symbol structure (uppercase + alphanumeric)
            if re.match(r"^[A-Z0-9]+$", symbol):
                return symbol, dtype, None
    
    # 2. Klines (Implicit type, explicit timeframe)
    # Pattern: SYMBOL-TIMEFRAME-YEAR-MONTH...
    # Regex: ^([A-Z0-9]+)-([0-9]+[a-z])-\d{4}-\d{2}
    kline_match = re.match(r"^([A-Z0-9]+)-([0-9]+[mhdwMH])-\d{4}-\d{2}", filename)
    if kline_match:
        return kline_match.group(1), "klines", kline_match.group(2)

    return None

def scan_directory(source_root: Path) -> Dict[DataTask, List[Path]]:
    """
    Recursively scan directory for data files and group them by task.
    Returns: Dict[DataTask, List[Path]]
    """
    tasks = defaultdict(list)
    
    LOG.info(f"Scanning {source_root} for CSV/ZIP files...")
    
    files = list(source_root.rglob("*.csv")) + list(source_root.rglob("*.zip"))
    
    for file_path in files:
        # Check parent folder naming for hints if filename fails?
        # For now, rely on filename parsing logic primarily.
        
        parsed = parse_filename(file_path.name)
        
        if parsed:
            symbol, data_type, timeframe = parsed
            # We explicitly use the file's parent directory as the source_dir for the converter
            # This ensures the converter finds the file even if nested deeply.
            task = DataTask(symbol, data_type, timeframe, file_path.parent)
            tasks[task].append(file_path)
        else:
            # Fallback: check directory structure
            # Structure: .../BTCUSDT/klines/1m/file.csv
            parts = file_path.parts
            if len(parts) >= 3:
                # check for klines/1m
                if parts[-2] in ["klines"] and len(parts) >= 4:
                    # .../klines/1m/file.csv -> timeframe=1m
                    # parent of klines usually symbol?
                    # e.g. data/raw/BTCUSDT/klines/1m/x.csv
                    # symbol = parts[-4] ? No too fragile.
                    pass
            
            # Log skipped only if verbose?
            # LOG.debug(f"Skipping unrecognized file: {file_path.name}")
            pass
            
    return tasks

def main():
    parser = argparse.ArgumentParser(description="Prepare Backtest Data (CSV -> Parquet)")
    parser.add_argument("--source", type=str, default="data/raw", help="Source directory containing raw CSVs")
    parser.add_argument("--target", type=str, default="data/processed", help="Target directory for Parquet output")
    parser.add_argument("--max-date", type=str, default=None, help="Skip files/months after this date, e.g. 2024-03")
    args = parser.parse_args()
    
    source_root = Path(args.source)
    target_root = Path(args.target)
    
    if not source_root.exists():
        LOG.error(f"Source directory '{source_root}' does not exist!")
        # Heuristic check
        if Path("data/processed").exists() and list(Path("data/processed").glob("*.csv")):
            LOG.info("💡 Hint: I found CSV files in 'data/processed'. Did you mean '--source data/processed'?")
        sys.exit(1)
        
    # 1. Scan
    tasks_map = scan_directory(source_root)
    
    if not tasks_map:
        LOG.warning("No recognizable data files found.")
        sys.exit(0)
        
    unique_tasks = list(tasks_map.keys())
    LOG.info(f"Found {len(unique_tasks)} conversion tasks (Grouping by Symbol/Type/Dir).")
    
    # 2. Convert
    converter = DataConverter()
    
    # Collapse tasks: if multiple files map to same symbol/type/timeframe but different dirs, 
    # we might strictly strictly separate them or try to merge.
    # DataConverter._locate_files searches the dir.
    # If we pass specific source_dir, it works.
    
    success_count = 0
    fail_count = 0
    
    with tqdm(total=len(unique_tasks), desc="Converting Batches", unit="batch") as pbar:
        klines_pairs: set[tuple[str, str]] = set()
        has_aggtrades: set[str] = set()
        for task in unique_tasks:
            try:
                # Update description
                desc = f"{task.symbol} {task.data_type}"
                if task.timeframe:
                    desc += f" {task.timeframe}"
                pbar.set_description(f"Processing {desc}")
                
                # Execute Conversion
                # We point source_dir to the directory containing the files
                converter.convert(
                    symbol=task.symbol,
                    data_type=task.data_type,
                    source_dir=str(task.source_dir),
                    target_dir=str(target_root),
                    timeframe=task.timeframe,
                    max_date=args.max_date,
                )
                if task.data_type == "klines" and task.timeframe:
                    klines_pairs.add((task.symbol, task.timeframe))
                if task.data_type == "aggTrades":
                    has_aggtrades.add(task.symbol)
                success_count += 1
            except Exception as e:
                LOG.error(f"Task failed {task}: {e}")
                fail_count += 1
            finally:
                pbar.update(1)

    # 3. Enrich (klines + aggTrades -> high-fidelity klines)
    # This step is optional per symbol/timeframe/month: it runs only when both sources exist.
    LOG.info("=" * 60)
    LOG.info("Enriching processed klines with aggTrades (high-fidelity backtest inputs)...")
    enrich_total = 0
    raw_dir = target_root.parent / "raw"
    for symbol, timeframe in sorted(klines_pairs):
        if symbol not in has_aggtrades:
            continue
        try:
            # Limit enrichment to months <= max_date if specified
            months_filter = None
            if args.max_date:
                all_months = [f"{y}-{str(m).zfill(2)}"
                              for y in range(2020, 2030) for m in range(1, 13)
                              if f"{y}-{str(m).zfill(2)}" <= args.max_date]
                months_filter = all_months
            results = enrich_symbol_timeframe(
                processed_dir=target_root,
                raw_dir=raw_dir,
                symbol=symbol,
                timeframe=timeframe,
                months=months_filter,
            )
            enrich_total += len(results)
        except Exception as e:
            LOG.error(f"Enrichment failed for {symbol} {timeframe}: {e}")
                
    LOG.info("="*60)
    LOG.info(f"DONE. Success: {success_count}, Failed: {fail_count}")
    LOG.info(f"Enriched files: {enrich_total}")
    LOG.info(f"Output files located in: {target_root}")
    LOG.info("="*60)

if __name__ == "__main__":
    main()
