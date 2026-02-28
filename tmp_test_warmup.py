import sys
import logging
import asyncio
from datetime import datetime, date
import polars as pl
from pathlib import Path

project_root = Path("C:/Users/wekab/Music/Phenix")
sys.path.insert(0, str(project_root))

from apps.reference.config_loader import ConfigLoader
from backtest_engine.engine import BacktestEngine
from vfoundation.core.fsm_core import FSMCore

logging.basicConfig(level=logging.INFO)

def run_test():
    print("Loading config...")
    config_loader = ConfigLoader(config_dir=project_root / "config" / "aurora")
    config = config_loader.load_config()
    start_date = date(2024, 1, 1) # Jan 2024 ensures 210 days history is available from 2023-06
    end_date = date(2024, 1, 7)
    
    symbols = ["DOGEUSDT", "BTCUSDT"]
    print("Initializing engine...")
    engine = BacktestEngine(
        start_date=start_date,
        end_date=end_date,
        symbol_list=symbols,
        timeframe="5m",
        initial_balance=10000.0,
        event_bus=FSMCore(),
    )
    
    print("Calling load_data()...")
    engine.load_data()
    
    # DEBUG POLARS FILTERS
    dt_schema = engine.feed.schema["ts"]
    print(f"Schema type for ts: {dt_schema}")
    ts_val = engine.feed[0, "ts"]
    print(f"First ts value: {ts_val} (type {type(ts_val)})")
    
    try:
        start_dt = datetime.combine(start_date, datetime.min.time())
        print(f"start_dt python value: {start_dt} (type {type(start_dt)})")
        
        f1 = engine.feed.filter(pl.col("ts") < start_dt)
        print(f"Filter (< start_dt) length: {len(f1)}")
        
        f2 = engine.feed.filter(pl.col("ts") < pl.lit(start_dt))
        print(f"Filter (< pl.lit(start_dt)) length: {len(f2)}")
        
        f3 = engine.feed.filter(pl.col("ts").dt.cast_time_unit("ms") < pl.lit(start_dt).cast(pl.Datetime("ms")))
        print(f"Filter (< cast(ms)) length: {len(f3)}")
        
        f4 = engine.feed.filter(pl.col("ts") >= start_dt)
        print(f"Filter (>= start_dt) length: {len(f4)}")
        
    except Exception as e:
        print(f"Filter error: {e}")
        
    print(f"Warmup feed length: {len(engine.warmup_feed) if engine.warmup_feed is not None else 0}")
    print(f"Sim feed length: {len(engine.feed) if engine.feed is not None else 0}")
    
    print("Calling _warmup_pillars()...")
    engine._warmup_pillars()

if __name__ == "__main__":
    run_test()
