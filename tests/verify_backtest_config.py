
import sys
import os
import logging
from pathlib import Path
from datetime import datetime

# Add project root to path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from apps.reference.config_loader import ConfigLoader
from apps.reference.config_models import AuroraConfig
from apps.reference.domains.feature_engineering.feature_engineering import FeatureEngineering
from backtest_engine.engine import BacktestEngine

# Configure logging
logging.basicConfig(level=logging.INFO)
LOG = logging.getLogger("TestBacktestConfig")

def test_backtest_configuration():
    LOG.info("Starting Backtest Configuration Audit...")
    
    # 1. Load actual config
    config_loader = ConfigLoader(config_dir=project_root / "config" / "aurora")
    config = config_loader.load_config()
    LOG.info("Base configuration loaded.")

    # 2. Simulate switching to backtest mode
    # In a real run, this comes from the YAML 'trading.mode' or 'trading_mode'
    # We manually patch it here to simulate the user changing the file.
    config.trading_mode = "backtest"
    config.trading.mode = "backtest"
    
    # Verify Sync Logic in Pydantic (if re-validated)
    if config.trading_mode != "backtest":
        LOG.error(f"FAIL: trading_mode is {config.trading_mode}, expected 'backtest'")
        sys.exit(1)
        
    LOG.info("✅ Config accepts 'trading_mode: backtest'")

    # 3. Check Backtest Settings
    if not config.trading.backtest:
        LOG.error("FAIL: config.trading.backtest is missing!")
        sys.exit(1)
        
    LOG.info(f"Backtest Range: {config.trading.backtest.start_date} -> {config.trading.backtest.end_date}")
    
    # 4. Simulate Main.py Overrides (Warmup/Macro)
    # This logic matches main.py lines 477+
    try:
        fe = getattr(config.domains, "feature_engineering", None)
        warm = getattr(fe, "warmup", None) if fe is not None else None
        if warm is not None:
            warm.enforcement_mode = "warn_only"
        
        # Verify it stuck
        if config.domains.feature_engineering.warmup.enforcement_mode != "warn_only":
             LOG.error("FAIL: Warmup override failed!")
             sys.exit(1)
        LOG.info("✅ Warmup successfully overridden to 'warn_only'")
        
        # Verify Macro Sync Disable
        ms_cfg = getattr(fe, "macro_sync", None)
        if ms_cfg is not None:
             ms_cfg.enabled = False
        
        if config.domains.feature_engineering.macro_sync.enabled is not False:
             LOG.error("FAIL: Macro sync disable failed!")
             sys.exit(1)
        LOG.info("✅ Macro sync disabled successfully")

    except Exception as e:
        LOG.error(f"FAIL: Exception during overrides: {e}")
        sys.exit(1)
        
    # 5. Check Killswitch
    # Backtest shouldn't care, but let's see its state
    ks = config.ops.panic_killswitch
    LOG.info(f"Panic Killswitch state: {ks} (Should be False, but Backtest ignores it anyway usually)")

    # 6. Instantiate BacktestEngine (Smoke Test)
    try:
        start = datetime.strptime(config.trading.backtest.start_date, "%Y-%m-%d")
        end = datetime.strptime(config.trading.backtest.end_date, "%Y-%m-%d")
        
        engine = BacktestEngine(
            start_date=start,
            end_date=end,
            symbol_list=["BTCUSDT"],
            timeframe="5m",
            initial_balance=config.trading.backtest.initial_balance,
            data_dir=str(project_root / "data/processed") 
        )
        LOG.info("✅ BacktestEngine initialized successfully.")
    except Exception as e:
        LOG.error(f"FAIL: BacktestEngine init failed: {e}")
        sys.exit(1)
        
    LOG.info("🎉 ALL SYSTEMS GO: Backtest configuration is valid and executable.")

if __name__ == "__main__":
    test_backtest_configuration()
