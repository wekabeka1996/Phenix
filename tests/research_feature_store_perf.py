
import time
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
import sys

# Add project root to path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from apps.reference.data.feature_store import FeatureStore

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("PerfTest")

def test_aggregation_performance():
    db_path = "data/perf_test_features.db"
    # Clean up previous test
    if Path(db_path).exists():
        Path(db_path).unlink()
        
    store = FeatureStore(db_path=db_path)
    symbol = "BTCUSDT"
    
    logger.info("Generating dummy data...")
    # Generate 1000 ticks
    start_time = datetime.now() - timedelta(hours=1)
    for i in range(1000):
        ts = start_time + timedelta(seconds=i)
        payload = {
            "ts": int(ts.timestamp() * 1000),
            "symbol": symbol,
            "features": {
                "price": 50000 + i,
                "obi": 0.5,
                "tfi": 0.1
            }
        }
        store.store_features(payload)
        
    logger.info("Data generated. Starting aggregation benchmark...")
    
    # Measure aggregation time
    start_bench = time.perf_counter()
    store.aggregate_all_timeframes(symbol)
    end_bench = time.perf_counter()
    
    duration_ms = (end_bench - start_bench) * 1000
    logger.info(f"Aggregation took {duration_ms:.2f} ms")
    
    if duration_ms > 100: # Arbitrary threshold, but >100ms per tick is definitely bad
        logger.warning("⚠️ Aggregation is SLOW!")
    else:
        logger.info("✅ Aggregation is fast enough.")

if __name__ == "__main__":
    test_aggregation_performance()
