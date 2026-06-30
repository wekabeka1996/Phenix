from typing import Optional
from dataclasses import dataclass, field
from apps.reference.domains.feature_engineering.bar_resampler import Bar
from apps.reference.domains.feature_engineering.mean_reversion_strategy import MRSignal, MRSignalType
from decimal import Decimal
from apps.reference.config_loader import ConfigLoader
from apps.reference.config_models import AuroraConfig, DomainsConfig
import sys
import pytest
import asyncio
import inspect
import time
from collections import OrderedDict
from pathlib import Path
from unittest.mock import MagicMock

PROJECT_ROOT = str(Path(__file__).resolve().parents[1])
TESTS_ROOT = Path(__file__).resolve().parent


def _is_under(path_str: str, root: Path) -> bool:
    try:
        return Path(path_str).resolve().is_relative_to(root)
    except Exception:
        return False


def _ensure_project_root_import_precedence() -> None:
    if PROJECT_ROOT in sys.path:
        sys.path.remove(PROJECT_ROOT)
    sys.path.insert(0, PROJECT_ROOT)
    sema_atom_path = str(Path(PROJECT_ROOT) / "Sema_Atom")
    if sema_atom_path not in sys.path:
        sys.path.insert(1, sema_atom_path)

    tools_mod = sys.modules.get("tools")
    if tools_mod is None:
        return

    tools_file = getattr(tools_mod, "__file__", "") or ""
    tools_paths = [str(path) for path in getattr(tools_mod, "__path__", [])]
    shadowed = _is_under(tools_file, TESTS_ROOT) or any(
        _is_under(path, TESTS_ROOT) for path in tools_paths
    )
    if not shadowed:
        return

    for name in list(sys.modules):
        if name == "tools" or name.startswith("tools."):
            sys.modules.pop(name, None)


_ensure_project_root_import_precedence()


# Legacy standalone harnesses with global sys.modules shims pollute collection
# and break the real vfoundation package imports used by the core suite.
collect_ignore = [
    "apps/reference/tests/gauntlet_unit.py",
    "apps/reference/tests/test_phase9_wiring.py",
    "verify_fsm_sl_fix.py",
]


def pytest_sessionstart(session):  # type: ignore[override]
    _ensure_project_root_import_precedence()


def pytest_collectstart(collector):  # type: ignore[override]
    _ensure_project_root_import_precedence()


def pytest_pyfunc_call(pyfuncitem):  # type: ignore[override]
    """Minimal async test runner (no pytest-asyncio dependency).

    Runs `async def` tests via `asyncio.run(...)` so the suite works in minimal envs.
    """
    testfunction = pyfuncitem.obj
    if inspect.iscoroutinefunction(testfunction):
        # type: ignore[attr-defined]
        funcargs = {name: pyfuncitem.funcargs[name]
                    for name in pyfuncitem._fixtureinfo.argnames}
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


@pytest.fixture(autouse=True)
def _isolate_runtime_observability_sinks(tmp_path, monkeypatch):
    """Keep synthetic test traffic out of repo-scoped WAL/JSONL sinks."""
    from apps.reference.domains.execution_position.fsm import ExecPosFSM
    from apps.reference.telemetry.order_logger import order_logger
    from apps.reference.telemetry.trade_lifecycle_logger import trade_lifecycle
    from vfoundation import config as vf_config
    from vfoundation.dr import wal as wal_mod

    original_cfg_wal_dir = vf_config.config.wal_dir
    original_wal_dir = wal_mod.WAL_DIR
    original_order_log_file = order_logger.log_file
    original_trade_log_file = trade_lifecycle._log_file
    original_trade_trades = OrderedDict(trade_lifecycle._trades)
    original_trade_recent_terminal = OrderedDict(
        trade_lifecycle._recent_terminal)
    original_trade_snapshots = dict(trade_lifecycle._snapshot_fingerprints)
    original_trade_next_sweep_at = trade_lifecycle._next_sweep_at

    wal_dir = tmp_path / "wal"
    log_dir = tmp_path / "logs"
    trade_lifecycle_path = log_dir / "trade_lifecycle.jsonl"
    order_log_path = log_dir / "order_log_v1.jsonl"

    wal_mod.set_wal_dir(wal_dir)
    vf_config.config.wal_dir = wal_dir
    wal_mod.reset()

    log_dir.mkdir(parents=True, exist_ok=True)
    order_logger.log_file = order_log_path
    trade_lifecycle._log_file = trade_lifecycle_path
    trade_lifecycle._trades = OrderedDict()
    trade_lifecycle._recent_terminal = OrderedDict()
    trade_lifecycle._snapshot_fingerprints = {}
    trade_lifecycle._next_sweep_at = time.time(
    ) + trade_lifecycle._auto_sweep_interval_sec

    monkeypatch.setattr(
        ExecPosFSM,
        "_trade_lifecycle_log_path",
        lambda self, _path=str(trade_lifecycle_path): _path,
    )
    monkeypatch.setenv("ENV", "")

    try:
        yield
    finally:
        order_logger.log_file = original_order_log_file
        trade_lifecycle._log_file = original_trade_log_file
        trade_lifecycle._trades = original_trade_trades
        trade_lifecycle._recent_terminal = original_trade_recent_terminal
        trade_lifecycle._snapshot_fingerprints = original_trade_snapshots
        trade_lifecycle._next_sweep_at = original_trade_next_sweep_at
        vf_config.config.wal_dir = original_cfg_wal_dir
        wal_mod.set_wal_dir(Path(original_wal_dir))
        wal_mod.reset()


@pytest.fixture(autouse=True)
def _restore_schema_validator_module_state():
    """Reset schema_validator import flags after reload/monkeypatch tests."""
    import vfoundation.core.schema_validator as sv

    def _reset() -> None:
        try:
            import jsonschema as _jsonschema  # type: ignore[import-untyped]
        except ImportError:
            sv.HAS_JSONSCHEMA = False
            if hasattr(sv, "jsonschema"):
                try:
                    delattr(sv, "jsonschema")
                except Exception:
                    pass
        else:
            sv.jsonschema = _jsonschema
            sv.HAS_JSONSCHEMA = True

        try:
            import yaml as _yaml  # type: ignore[import-untyped]
        except ImportError:
            sv.HAS_YAML = False
            if hasattr(sv, "yaml"):
                try:
                    delattr(sv, "yaml")
                except Exception:
                    pass
        else:
            sv.yaml = _yaml
            sv.HAS_YAML = True

    _reset()
    try:
        yield
    finally:
        _reset()


# MR Signal Factory for Tests


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
class FlipCfgStub:
    """Stub for global flip killswitch config."""
    enabled: bool = True


@dataclass
class DecisionMakingCfgStub:
    """Stub for DecisionMaking config with real values."""
    flip_hysteresis_mult: float = 1.0
    neocortex_enforcement_mode: str = "shadow"
    flip: FlipCfgStub = field(default_factory=FlipCfgStub)
    qos: QosCfgStub = field(default_factory=QosCfgStub)
    position_sizing: PositionSizingCfgStub = field(
        default_factory=PositionSizingCfgStub)
    arming: ArmingCfgStub = field(default_factory=ArmingCfgStub)
    features: FeaturesCfgStub = field(default_factory=FeaturesCfgStub)
    bar_gating: BarGatingCfgStub = field(default_factory=BarGatingCfgStub)
    behavior_fsm: BehaviorFsmCfgStub = field(
        default_factory=BehaviorFsmCfgStub)


@dataclass
class DomainsCfgStub:
    """Stub for domains config."""
    decision_making: DecisionMakingCfgStub = field(
        default_factory=DecisionMakingCfgStub)


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
    feature_engineering_macro_sync_anchors: list = field(
        default_factory=lambda: ["BTCUSDT", "ETHUSDT"])
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


def create_mock_mr_config():
    """Factory for mocked MeanReversion config with STRICT execution fields."""
    mr_config = MagicMock()
    mr_config.enabled = True
    mr_config.timeframe_sec = 180

    # REQUIRED FIELD for Pydantic strict validation
    mr_config.execution = MagicMock()
    mr_config.execution.entry_order_type = "MARKET"
    mr_config.execution.entry_tif = None
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
