"""
Config for Mean Reversion Strategy (Alpha V1)
"""
from pathlib import Path

# Base paths
DATA_DIR = Path("apps/research/momentum_backtest/data")
REPORTS_DIR = Path("apps/research/new_alpha/reports")

# File Templates (Reuse existing ETL pipeline)
GOLDEN_DATASET_TEMPLATE = "{symbol}-1s-golden-{year}-{month}.csv"
FEATURES_DATASET_TEMPLATE = "{symbol}-features-mr-{year}-{month}.csv" # mr = mean reversion

# Default Parameters
DEFAULT_SYMBOL = "BNBUSDT"
DEFAULT_YEAR = "2024"
DEFAULT_MONTH = "03"

# Strategy Constants
TIMEFRAME_SEC = 5  # Base timeframe
