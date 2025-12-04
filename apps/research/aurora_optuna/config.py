"""
Config for Aurora Optuna Optimization
"""
from pathlib import Path

# Paths
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent  # Go up 4 levels from file
DATA_DIR = PROJECT_ROOT / "apps" / "research" / "momentum_backtest" / "data"

# Files (1m timeframe)
GOLDEN_DATASET_TEMPLATE = "{symbol}-60s-golden-{year}-{month}.csv"
FEATURES_DATASET_TEMPLATE = "{symbol}-features-aurora-1m-{year}-{month}.csv"
FEATURES_DATASET_TEMPLATE_3M = "{symbol}-features-aurora-3m-{year}-{month}.csv"
FEATURES_DATASET_TEMPLATE_5M = "{symbol}-features-aurora-5m-{year}-{month}.csv"

# Defaults
DEFAULT_SYMBOL = "BTCUSDT"
DEFAULT_YEAR = "2024"
DEFAULT_MONTH = "01"

def get_data_path(filename, symbol, year, month):
    """Get full path to data file"""
    fname = filename.format(symbol=symbol, year=year, month=month)
    return DATA_DIR / fname
