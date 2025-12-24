import pytest
import asyncio
import inspect
from unittest.mock import MagicMock
from apps.reference.config_models import AuroraConfig, DomainsConfig
from apps.reference.config_loader import ConfigLoader

def pytest_pyfunc_call(pyfuncitem):  # type: ignore[override]
    """Minimal async test runner (no pytest-asyncio dependency).

    Runs `async def` tests via `asyncio.run(...)` so the suite works in minimal envs.
    """
    testfunction = pyfuncitem.obj
    if inspect.iscoroutinefunction(testfunction):
        funcargs = {name: pyfuncitem.funcargs[name] for name in pyfuncitem._fixtureinfo.argnames}  # type: ignore[attr-defined]
        asyncio.run(testfunction(**funcargs))
        return True
    return None

@pytest.fixture
def mock_fsm():
    """Mock FSM Core."""
    fsm = MagicMock()
    fsm.listen = MagicMock()
    fsm.emit = MagicMock()
    return fsm

@pytest.fixture
def domains_config():
    """Load the real domains.yaml config."""
    loader = ConfigLoader()
    return loader.load_config()

class MockAuroraConfig:
    """Custom mock config to avoid MagicMock auto-creation issues."""
    def __init__(self, domains_config):
        self.domains = domains_config.domains
        
        # Legacy mocks
        self.trading = MagicMock()
        self.trading.risk = MagicMock()
        self.trading.risk.trading_allowed_thresholds = {}
        
        self.decision = MagicMock()
        self.decision.position_sizing.min_position_size_usd = "10"
        self.decision.position_sizing.liquidity_based_cap_usd = "10000"
        self.decision.qos.exposure_block_cooldown_sec = "10"
        self.decision.qos.symbol_cooldown_sec = "3"
        self.decision.qos.max_intents_per_minute_per_symbol = "6"
        self.decision.features.ttl_sec = "5"
        self.decision.bar_gating.bar_ms = "900000"
        self.decision.behavior_fsm.high_vol_multiplier = "2.0"
        self.decision.behavior_fsm.low_vol_multiplier = "0.5"
        
        self.tca_prefs = MagicMock()
        self.risk_budgets = MagicMock()
        
        self.execution = MagicMock()
        self.execution.max_equity_utilization_pct = "0.95"
        self.execution.max_portfolio_fraction = "0.95"
        self.execution.max_long_utilization_pct = "0.95"
        self.execution.max_short_utilization_pct = "0.95"
        self.execution.max_directional_ratio = "2.0"
        self.execution.max_concentration_pct = "0.10"
        self.execution.watchdog.ack_ttl_ms = "8000"
        self.execution.watchdog.fill_ttl_ms = "30000"
        self.execution.watchdog.rps_limit = "10"
        
        self.feature_engineering = MagicMock()
        self.feature_engineering.ema.period_short = 3
        self.feature_engineering.ema.period_long = 7
        self.feature_engineering.volume.sma_length = 5
        self.feature_engineering.volume.window_sec = 60
        self.feature_engineering.volatility.sma_length = 10
        self.feature_engineering.volatility.window_sec = 60
        self.feature_engineering.liquidity.depth_half = 1000
        self.feature_engineering.macro_sync.window = 60
        self.feature_engineering.macro_sync.anchors = ["BTCUSDT", "ETHUSDT"]
        
        self.risk_score_weights = {}

    def __contains__(self, key):
        return hasattr(self, key)

    def get(self, key, default=None):
        return getattr(self, key, default)

@pytest.fixture
def root_mock_config(domains_config):
    """Mock configuration object with domains loaded."""
    print("DEBUG: mock_config fixture in tests/conftest.py CALLED")
    return MockAuroraConfig(domains_config)
