
import sys
import time
import logging
from pathlib import Path
from decimal import Decimal
import polars as pl
import numpy as np
from datetime import datetime, timedelta

# Add project root to path
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

# Configure logging to INFO to see what's happening (or not happening)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
# Suppress some noisy loggers if needed, but keep core ones
logging.getLogger("backtest_engine").setLevel(logging.INFO)
logging.getLogger("AuroraCore").setLevel(logging.INFO)
logging.getLogger("apps.reference").setLevel(logging.INFO) # ENABLE TRADING LOGS

from backtest_engine.engine import BacktestEngine
from vfoundation.core import FSMCore
from apps.reference.config_loader import ConfigLoader
from apps.reference.domains.strategies.plugins.mean_reversion import MeanReversionPlugin
from apps.reference.domains.decision_making.mean_reversion_handler import MeanReversionHandler

# Add Missing Imports
from apps.reference.domains.feature_engineering.feature_engineering import FeatureEngineering
from apps.reference.domains.regime_detector.regime_detector import RegimeDetector

# Mock MeanReversionStrategy Wrapper since we can't import the plugin directly to get the handler
class MeanReversionStrategy(MeanReversionHandler):
    def __init__(self, strategy_id, event_bus, config):
        if config is None:
            # Fallback mock config if needed, or error
            pass
        super().__init__(fsm=event_bus, config=config)


# Mock Clock
class MockClock:
    def __init__(self, start_date):
        self._ts = start_date.timestamp()
    
    def now_sec(self): return self._ts
    def now_ms(self): return int(self._ts * 1000)
    def advance_ms(self, ms): self._ts += ms / 1000.0
    def monotonic(self): return self._ts


def generate_synthetic_data(symbol: str, days: int = 5, timeframe: str = "5m") -> pl.DataFrame:
    """Generate synthetic OHLCV data for profiling."""
    start_date = datetime(2023, 1, 1)
    # 5m = 288 bars/day
    bars_per_day = 288
    total_bars = days * bars_per_day
    
    dates = [start_date + timedelta(minutes=5*i) for i in range(total_bars)]
    
    # Random walk price
    price = 100.0
    opens = []
    highs = []
    lows = []
    closes = []
    volumes = []
    
    for _ in range(total_bars):
        change = np.random.normal(0, 0.5)
        close = price + change
        high = max(price, close) + np.random.uniform(0, 0.2)
        low = min(price, close) - np.random.uniform(0, 0.2)
        
        opens.append(price)
        highs.append(high)
        lows.append(low)
        closes.append(close)
        volumes.append(np.random.uniform(100, 1000))
        
        price = close

    df = pl.DataFrame({
        "ts": dates,
        "symbol": [symbol] * total_bars,
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": volumes,
        # Enrich with zeros for extra fields
        "buy_volume": [v/2 for v in volumes],
        "sell_volume": [v/2 for v in volumes],
        "buy_notional": [v/2 * c for v, c in zip(volumes, closes)],
        "sell_notional": [v/2 * c for v, c in zip(volumes, closes)],
        "buy_count": [10] * total_bars,
        "sell_count": [10] * total_bars,
    })
    return df

def run_profiling():
    LOG = logging.getLogger("Profiler")
    LOG.info("Starting Profiling Run...")
    
    # 1. Load Config
    config_path = project_root / "config" / "aurora"
    loader = ConfigLoader(config_dir=config_path)
    config = loader.load_config()

    # Update config to disable heavy warmup gates for profiling
    if hasattr(config, 'feature_engineering'):
        config.feature_engineering.macro_sync_enabled = False # Completely disable to be sure
        config.feature_engineering.macro_resid_enabled = False
        config.feature_engineering.futures_enabled = False
        # Relax constraints if enabled (but we disabled it)
        config.feature_engineering.macro_sync_min_buffer = 0
        config.feature_engineering.macro_sync_window = 2
        # Also disable strict data quality if possible
        config.system.market_data.tick_ttl_ms = 0 # Disable TTL checking
        config.feature_engineering.warmup_enforcement_mode = "warn_only"

    
    # 2. Setup Components
    fsm = FSMCore() # Local synchronous bus
    start_date = datetime(2023, 1, 1)
    clock = MockClock(start_date)
    
    # Wire Regime Detector & Feature Engineering
    from apps.reference.domains.feature_engineering.feature_engineering import FeatureEngineering
    from apps.reference.domains.regime_detector.regime_detector import RegimeDetector
    
    LOG.info("Initializing FeatureEngineering...")
    fe = FeatureEngineering(fsm=fsm, config=config)
    # Monkeypatch to force execution (target underlying Pydantic model)
    if hasattr(fe.cfg._cfg, 'warmup') and fe.cfg._cfg.warmup:
        fe.cfg._cfg.warmup.enforcement_mode = "warn_only"
        # Also disable strict invariant check if possible
        fe.cfg._cfg.warmup.check_full_ready_invariant = False
    
    LOG.info(f"Monkeypatched fe.cfg.warmup_enforcement_mode = {fe.cfg.warmup_enforcement_mode}")
    
    LOG.info("Initializing RegimeDetector...")
    rd = RegimeDetector(config=config, fsm=fsm, clock=clock)
    rd.start()
    
    # 2.5 Setup Async Loop and ExecPosFSM
    LOG.info("Initializing ExecPosFSM...")
    import asyncio
    import threading
    from backtest_engine.wrappers import BacktestExecPosFSM

    loop = asyncio.new_event_loop()
    loop_thread = threading.Thread(target=lambda: asyncio.set_event_loop(loop) or loop.run_forever(), daemon=True)
    loop_thread.start()

    exec_pos = BacktestExecPosFSM(config=config, fsm=fsm, shadow_mode=False)
    exec_pos.set_async_loop(loop)
    
    # Wire Strategies (MeanReversion)
    strategy = MeanReversionStrategy(
        strategy_id="mean_reversion_profile",
        event_bus=fsm,
        config=config
    )
    
    # 3. Setup Engine
    engine = BacktestEngine(
        start_date=start_date,
        end_date=start_date + timedelta(days=10), # Match generated data
        symbol_list=["SOLUSDT"],
        timeframe="5m",
        event_bus=fsm,
        clock_advance_fn=lambda ms: clock.advance_ms(ms)
    )
    # Wire ExecPosFSM
    if exec_pos.adapter is not None:
        engine.broker = exec_pos.adapter
    engine.execpos_fsm = exec_pos

    # 3.5 Wire AlphaSearch Plugin
    LOG.info("Initializing AlphaSearch Plugin...")
    from apps.reference.domains.alpha_search.backtest_plugin import AlphaSearchBacktestPlugin
    from apps.reference.domains.alpha_search.config_models import AlphaSearchConfig, get_default_config
    
    try:
        # Create config and force enable
        as_config = get_default_config()
        as_config.enabled = True
        as_config.shadow_mode = True # Safe
        
        # Load providers if possible, or use default
        # (Assuming default has some mock providers or we need to add one?)
        
        alpha_plugin = AlphaSearchBacktestPlugin(event_bus=fsm, config=as_config)
        LOG.info(f"AlphaSearch Plugin initialized (enabled={alpha_plugin.enabled}).")
    except Exception as e:
        LOG.error(f"Failed to init AlphaSearch: {e}")



    
    # 4. Inject Data
    LOG.info("Generating Synthetic Data...")
    df = generate_synthetic_data("SOLUSDT", days=5)
    engine.feed = df.sort("ts")
    LOG.info(f"Data ready: {len(df)} rows")
    
    # 5. Run & Measure
    LOG.info("Run Engine (with MeanReversion attached)...")
    t0 = time.time()
    engine.run()
    t1 = time.time()
    
    duration = t1 - t0
    ticks = len(df)
    tps = ticks / duration
    
    LOG.info(f"DONE. Duration: {duration:.2f}s. Speed: {tps:.2f} ticks/sec")

if __name__ == "__main__":
    run_profiling()
