import os
from pathlib import Path
from typing import Literal

# Strategy modes for inverse symmetry testing
StrategyMode = Literal["base", "score_flip", "side_flip"]

# Base paths
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
RESEARCH_DIR = Path(__file__).parent
DATA_DIR = RESEARCH_DIR / "data"
RAW_DATA_DIR = DATA_DIR

# Ensure data directory exists
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Default configuration
DEFAULT_SYMBOL = "BNBUSDT"
DEFAULT_YEAR = "2024"
DEFAULT_MONTH = "03"

# File templates
AGG_TRADES_TEMPLATE = "{symbol}-aggTrades-{year}-{month}.csv"
BOOK_TICKER_TEMPLATE = "{symbol}-bookTicker-{year}-{month}.csv"
FUNDING_RATE_TEMPLATE = "{symbol}-fundingRate-{year}-{month}.csv"
KLINES_1M_TEMPLATE = "{symbol}-1m-{year}-{month}.csv"

GOLDEN_DATASET_TEMPLATE = "{symbol}-1s-golden-{year}-{month}.csv"
FEATURES_DATASET_TEMPLATE = "{symbol}-features-{year}-{month}.csv"

# BASE_CONFIG from Optuna V3 Extended (Trial 207, Best Score 10.6688)
# Used as baseline for inverse symmetry comparison
BASE_CONFIG = {
    # 9 signal weights
    "w_tfi": 0.294,
    "w_tob": 0.839,
    "w_bs": 0.013,
    "w_bl": 0.622,
    "w_macro": 0.254,
    "w_delta_price": 0.290,
    "w_volume_spike": 0.386,
    "w_volatility_state": 0.033,
    "w_depth_imbalance": 0.938,
    # Entry threshold
    "threshold": 0.227,
    # Entry Gates (Depth Mode defaults)
    "depth_imbalance_phi_min": 0.6,
    "tob_phi_min": 0.6,
    "ema_bias_long_phi_min": 0.4,
    "vol_state_phi_min": 0.05,
    "vol_state_phi_max": 0.95,
    # Risk parameters
    "sl_pct": 0.0081,
    "sl_tp_ratio": 1.813,
    # Funding veto
    "funding_threshold_long": 0.0003,
    # Fixed parameters
    "max_holding_secs": 300,
    "position_size": 200.0,
    "commission": 0.0005,
    "slippage": 0.0001,
    "spread_half": 0.0001,
    # Strategy mode (default: base)
    "strategy_mode": "base",
}

# Target symbols for Cross-Asset Baseline
TARGET_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT"]

HISTORICAL_DATA_DIR = PROJECT_ROOT / "data" / "historical"

def get_raw_file_path(template: str, symbol: str = DEFAULT_SYMBOL, year: str = DEFAULT_YEAR, month: str = DEFAULT_MONTH) -> Path:
    filename = template.format(symbol=symbol, year=year, month=month)
    
    # 1. Check default location (apps/research/momentum_backtest/data)
    path = RAW_DATA_DIR / filename
    if path.exists():
        return path
        
    # 2. Check historical location (data/historical/{BASE}_01_02)
    # Heuristic: BTCUSDT -> BTC
    base_asset = symbol.replace("USDT", "")
    hist_folder = HISTORICAL_DATA_DIR / f"{base_asset}_01_02"
    
    path_hist = hist_folder / filename
    if path_hist.exists():
        return path_hist
        
    # Default return
    return path

def get_processed_file_path(template: str, symbol: str = DEFAULT_SYMBOL, year: str = DEFAULT_YEAR, month: str = DEFAULT_MONTH) -> Path:
    filename = template.format(symbol=symbol, year=year, month=month)
    return DATA_DIR / filename
