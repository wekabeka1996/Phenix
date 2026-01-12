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
    # print("DEBUG: mock_config fixture in tests/conftest.py CALLED")
    return MockAuroraConfig(domains_config)


# MR Signal Factory for Tests
from decimal import Decimal
from apps.reference.domains.feature_engineering.mean_reversion_strategy import MRSignal, MRSignalType
from apps.reference.domains.feature_engineering.bar_resampler import Bar


def make_mr_signal(
    symbol="BTCUSDT",
    side="BUY",
    is_signal=True,
    signal_type=MRSignalType.LONG,
    confidence=Decimal("0.99"),
    entry_price=Decimal("100"),
    stop_price=Decimal("90"),
    target_price=Decimal("110"),
    timestamp_ms=1700000000000,
    bar=None,
    **kwargs
):
    """Factory for MRSignal with defaults for testing."""
    if bar is None:
        bar = Bar(
            symbol=symbol,
            timeframe_sec=60,
            open=Decimal("100"),
            high=Decimal("101"),
            low=Decimal("99"),
            close=Decimal("100"),
            volume=Decimal("10"),
            trade_count=5,
            start_ts_ms=timestamp_ms - 60000,
            end_ts_ms=timestamp_ms,
        )
    
    return MRSignal(
        signal_type=signal_type,
        symbol=symbol,
        price=Decimal("100"),
        confidence=confidence,
        entry_price=entry_price,
        stop_price=stop_price,
        target_price=target_price,
        timestamp_ms=timestamp_ms,
        bar=bar,
        **kwargs
    )


# Config Stubs for Tests (no MagicMock in numeric fields)
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class QosCfgStub:
    """Stub for QoS config."""
    exposure_block_cooldown_sec: int = 60
    max_intents_per_minute_per_symbol: int = 20
    mode: str = "enforce"
    symbol_cooldown_sec: int = 3
    enforce: bool = True


@dataclass
class PositionSizingCfgStub:
    """Stub for position sizing config."""
    min_position_size_usd: float = 10.0
    liquidity_based_cap_usd: float = 10000.0


@dataclass
class ArmingCfgStub:
    """Stub for arming config."""
    require_regime_warmup: bool = False
    retry_backoff_ms: int = 0
    max_attempts: int = 1


@dataclass
class FeaturesCfgStub:
    """Stub for features config."""
    ttl_sec: int = 30


@dataclass
class BarGatingCfgStub:
    """Stub for bar gating config."""
    enable: bool = False
    bar_ms: int = 60000


@dataclass
class BehaviorFsmCfgStub:
    """Stub for behavior FSM config."""
    enable: bool = False
    high_vol_multiplier: float = 2.0
    low_vol_multiplier: float = 0.5


@dataclass
class DecisionMakingCfgStub:
    """Stub for DecisionMaking config with real values."""
    flip_hysteresis_mult: float = 1.0
    qos: QosCfgStub = field(default_factory=QosCfgStub)
    position_sizing: PositionSizingCfgStub = field(default_factory=PositionSizingCfgStub)
    arming: ArmingCfgStub = field(default_factory=ArmingCfgStub)
    features: FeaturesCfgStub = field(default_factory=FeaturesCfgStub)
    bar_gating: BarGatingCfgStub = field(default_factory=BarGatingCfgStub)
    behavior_fsm: BehaviorFsmCfgStub = field(default_factory=BehaviorFsmCfgStub)


@dataclass
class DomainsCfgStub:
    """Stub for domains config."""
    decision_making: DecisionMakingCfgStub = field(default_factory=DecisionMakingCfgStub)


@dataclass
class TradingCfgStub:
    """Stub for trading config."""
    tca_prefs: dict = field(default_factory=dict)
    risk_budgets: dict = field(default_factory=dict)


@dataclass
class AppCfgStub:
    """Stub for app config."""
    domains: DomainsCfgStub = field(default_factory=DomainsCfgStub)
    instruments: dict = field(default_factory=dict)
    decision: dict = field(default_factory=dict)
    trading: TradingCfgStub = field(default_factory=TradingCfgStub)
    trading_market_data_use_multiprocessing: bool = False
    trading_risk_trading_allowed_thresholds: dict = field(default_factory=dict)
    decision_position_sizing_min_position_size_usd: float = 10.0
    decision_position_sizing_liquidity_based_cap_usd: float = 10000.0
    tca_prefs: Optional[dict] = None
    risk_budgets: Optional[dict] = None
    execution_max_equity_utilization_pct: float = 0.95
    execution_max_portfolio_fraction: float = 0.95
    execution_max_long_utilization_pct: float = 0.95
    execution_max_short_utilization_pct: float = 0.95
    execution_max_directional_ratio: float = 2.0
    execution_max_concentration_pct: float = 0.1
    execution_watchdog_ack_ttl_ms: int = 8000
    execution_watchdog_fill_ttl_ms: int = 30000
    execution_watchdog_rps_limit: int = 10
    feature_engineering_ema_period_short: int = 3
    feature_engineering_ema_period_long: int = 7
    feature_engineering_volume_sma_length: int = 5
    feature_engineering_volume_window_sec: int = 60
    feature_engineering_volatility_sma_length: int = 10
    feature_engineering_volatility_window_sec: int = 60
    feature_engineering_liquidity_depth_half: int = 1000
    feature_engineering_macro_sync_window: int = 60
    feature_engineering_macro_sync_anchors: list = field(default_factory=lambda: ["BTCUSDT", "ETHUSDT"])
    risk_score_weights: dict = field(default_factory=dict)


def make_app_cfg_stub(**overrides):
    """Factory for AppCfgStub with overrides."""
    stub = AppCfgStub()
    for key, value in overrides.items():
        if hasattr(stub, key):
            setattr(stub, key, value)
        elif key.startswith('domains__decision_making__'):
            subkey = key[len('domains__decision_making__'):]
            obj = stub.domains.decision_making
            parts = subkey.split('__')
            for part in parts[:-1]:
                if hasattr(obj, part):
                    obj = getattr(obj, part)
                else:
                    break
            else:
                setattr(obj, parts[-1], value)
        # Add more if needed
    return stub

# ==============================================================================
# STRATEGY MOCK FACTORIES (Strict Config Fix)
# ==============================================================================

def create_mock_mr_config(emit_trade_intent_directly=False):
    """Factory for mocked MeanReversion config with STRICT execution fields."""
    mr_config = MagicMock()
    mr_config.enabled = True
    mr_config.timeframe_sec = 180
    
    # REQUIRED FIELD for Pydantic strict validation
    mr_config.execution = MagicMock()
    mr_config.execution.entry_order_type = "MARKET"
    mr_config.execution.entry_tif = None
    
    mr_config.emit_trade_intent_directly = emit_trade_intent_directly
    mr_config.allowed_regimes = ["FLAT_LOW", "FLAT_NORMAL", "FLAT_HIGH"]
    mr_config.regime_sizing = {}
    mr_config.liquidity_gate = None
    
    # Defaults
    mr_config.risk = MagicMock()
    mr_config.regime_thresholds = {"DEFAULT": 0.5}
    mr_config.assets = {}
    mr_config.strategy = MagicMock()
    
    return mr_config

def create_mock_aurora_config_simple():
    """Factory for basic mocked Aurora config."""
    aurora_config = MagicMock()
    aurora_config.execution = MagicMock()
    aurora_config.execution.entry_order_type = "LIMIT" 
    aurora_config.execution.entry_tif = "GTX"
    return aurora_config


class MockClock:
    """Helper for deterministic time testing (monotonic & wall)."""
    def __init__(self, start_ts=1000.0):
        self._ts = start_ts
        
    def __call__(self):
        """Behave like time.monotonic() when called directly."""
        return self._ts

    def now_sec(self) -> float:
        """Clock interface: wall time."""
        return self._ts
        
    def monotonic(self) -> float:
        """Clock interface: monotonic time."""
        return self._ts
        
    def advance(self, seconds: float):
        self._ts += seconds
        
    def set(self, ts: float):
        self._ts = ts

@pytest.fixture
def manual_clock():
    return MockClock()
