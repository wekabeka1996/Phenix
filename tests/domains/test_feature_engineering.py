"""Unit tests for FeatureEngineering domain."""

from unittest.mock import Mock, patch
from apps.reference.domains.feature_engineering.feature_engineering_phase1 import FeatureEngineering as FeatureEngineeringPhase1
from apps.reference.domains.feature_engineering.config import (
    ConfigDefaults,
    EMAConfig,
    VolumeConfig,
    VolatilityConfig,
    LiquidityConfig,
    MacroSyncConfig,
    FeatureEngineeringConfig,
)
from apps.reference.domains.feature_engineering.feature_engineering import (
    FeatureEngineering,
)
import decimal
import time
from unittest import mock

import pytest

from vfoundation.core.protocol import Message


class FSMCoreMock:
    def __init__(self):
        self.listeners = {}
        self.emitted = []

    def listen(self, event_name: str, callback):
        self.listeners.setdefault(event_name, []).append(callback)

    def emit(self, event_name: str, payload: dict, why: str = ""):
        self.emitted.append((event_name, payload, why))


@pytest.fixture
def fsm():
    return FSMCoreMock()


@pytest.fixture
def config():
    return {}


def make_tick(
    ts=None,
    price="50000.00",
    bid_size="10",
    ask_size="8",
    buy_volume="50",
    sell_volume="30",
):
    if ts is None:
        ts = int(time.time() * 1000)
    return {
        "ts": ts,
        "symbol": "BTCUSDT",
        "price": decimal.Decimal(price),
        "bid": decimal.Decimal(price),
        "ask": decimal.Decimal(price),
        "mid": decimal.Decimal(price),
        "bid_size": decimal.Decimal(bid_size),
        "ask_size": decimal.Decimal(ask_size),
        "buy_volume": decimal.Decimal(buy_volume),
        "sell_volume": decimal.Decimal(sell_volume),
        "data_source": "test",
    }


def test_no_symbol_no_emit(fsm, config):
    from apps.reference.domains.feature_engineering.feature_engineering import (
        FeatureEngineering,
    )

    fe = FeatureEngineering(fsm=fsm, config=config)

    # Create a message without symbol
    msg = Message(op="EVT", verb="MARKET_TICK_RECEIVED",
                  src="test", dst="fe", pld={})
    # Should not raise and should not emit
    fe.on_market_tick(msg)
    assert len(fsm.emitted) == 0


def test_first_tick_only_stored(fsm, config):
    from apps.reference.domains.feature_engineering.feature_engineering import (
        FeatureEngineering,
    )

    fe = FeatureEngineering(fsm=fsm, config=config)

    tick = make_tick()
    msg = Message(op="EVT", verb="MARKET_TICK_RECEIVED",
                  src="test", dst="fe", pld=tick)
    fe.on_market_tick(msg)

    # No emission on first tick
    assert len(fsm.emitted) == 0


def test_calculate_and_emit_features_basic(fsm, config):
    from apps.reference.domains.feature_engineering.feature_engineering import (
        FeatureEngineering,
    )

    fe = FeatureEngineering(fsm=fsm, config=config)

    ts0 = int(time.time() * 1000)
    last = make_tick(
        ts=ts0,
        price="50000.00",
        bid_size="10",
        ask_size="8",
        buy_volume="50",
        sell_volume="30",
    )
    current = make_tick(
        ts=ts0 + 500,
        price="50050.00",
        bid_size="12",
        ask_size="6",
        buy_volume="60",
        sell_volume="20",
    )

    fe.last_tick_data["BTCUSDT"] = last

    msg = Message(
        op="EVT", verb="MARKET_TICK_RECEIVED", src="test", dst="fe", pld=current
    )
    fe.on_market_tick(msg)

    # One FEATURES_CALCULATED should be emitted
    assert len(fsm.emitted) == 1
    event_name, payload, why = fsm.emitted[0]
    assert event_name == "EVT:FEATURES_CALCULATED"
    assert payload["symbol"] == "BTCUSDT"
    features = payload["features"]
    # obi = (bid_size - ask_size) / (bid_size + ask_size) = (12-6)/(18)=6/18=0.333...
    assert float(features["obi"]) == pytest.approx(0.3333333, rel=1e-3)
    # tfi = (buy - sell)/(buy+sell) = (60-20)/(80)=40/80=0.5
    assert float(features["tfi"]) == pytest.approx(0.5, rel=1e-6)
    # delta_price = 50050 - 50000 = 50 (time_diff < 1000)
    assert float(features["delta_price"]) == pytest.approx(50.0, rel=1e-6)


def test_delta_price_suppressed_when_time_diff_large(fsm, config):
    from apps.reference.domains.feature_engineering.feature_engineering import (
        FeatureEngineering,
    )

    fe = FeatureEngineering(fsm=fsm, config=config)

    ts0 = int(time.time() * 1000)
    last = make_tick(ts=ts0, price="50000.00")
    # Changed: 2000 → 5100 to exceed the 5000ms threshold (code now uses 5s, not 1s)
    current = make_tick(ts=ts0 + 5100, price="50050.00")

    fe.last_tick_data["BTCUSDT"] = last
    msg = Message(
        op="EVT", verb="MARKET_TICK_RECEIVED", src="test", dst="fe", pld=current
    )
    fe.on_market_tick(msg)

    assert len(fsm.emitted) == 1
    _, payload, _ = fsm.emitted[0]
    features = payload["features"]
    assert float(features["delta_price"]) == pytest.approx(0.0, rel=1e-9)


"""
Integration test for feature_engineering domain.
"""


@pytest.fixture
def mock_config():
    """Mock configuration for feature engineering tests."""
    return {}


class FSMCore:
    """Simple FSM core interface for testing."""

    def __init__(self):
        self.listeners = {}

    def listen(self, event_name, callback):
        if event_name not in self.listeners:
            self.listeners[event_name] = []
        self.listeners[event_name].append(callback)

    def emit(self, event_name, payload, why):
        if event_name in self.listeners:
            for callback in self.listeners[event_name]:
                callback(
                    Message(
                        op="EVT",
                        verb=event_name.split(":")[1],
                        src="test",
                        dst="any",
                        pld=payload,
                        why=why,
                    )
                )


def test_feature_engineering_consumes_tick_and_emits_features(mock_config):
    """Test that feature_engineering consumes a tick and emits features."""
    fsm = FSMCore()
    mock_listener = mock.Mock()
    fsm.listen("EVT:FEATURES_CALCULATED", mock_listener)
    feature_component = FeatureEngineering(fsm=fsm, config=mock_config)

    # Send two ticks to get a delta_price
    tick1 = {
        "ts": int(time.time() * 1000) - 100,
        "symbol": "BTCUSDT",
        "price": "50000",
        "bid_size": "1",
        "ask_size": "1",
        "buy_volume": "1",
        "sell_volume": "1",
    }
    tick2 = {
        "ts": int(time.time() * 1000),
        "symbol": "BTCUSDT",
        "price": "50010",
        "bid_size": "1",
        "ask_size": "1",
        "buy_volume": "1",
        "sell_volume": "1",
    }

    feature_component.on_market_tick(
        Message(
            op="EVT", verb="MARKET_TICK_RECEIVED", src="test", dst="test", pld=tick1
        )
    )
    feature_component.on_market_tick(
        Message(
            op="EVT", verb="MARKET_TICK_RECEIVED", src="test", dst="test", pld=tick2
        )
    )

    mock_listener.assert_called_once()
    features = mock_listener.call_args[0][0].pld["features"]
    assert features["delta_price"] == "10"


# Tests for config.py coverage


def test_config_defaults():
    """Test ConfigDefaults has all expected default values."""
    defaults = ConfigDefaults()
    assert defaults.EMA_PERIOD_SHORT == 3
    assert defaults.EMA_PERIOD_LONG == 7
    assert defaults.VOLUME_SMA_LENGTH == 5
    assert defaults.VOLUME_WINDOW_SEC == 60
    assert defaults.VOLATILITY_SMA_LENGTH == 10
    assert defaults.VOLATILITY_WINDOW_SEC == 60
    assert defaults.LIQUIDITY_DEPTH_HALF == 1000.0
    assert defaults.MACRO_SYNC_ENABLED is False
    assert defaults.MACRO_SYNC_ANCHORS == ["BTCUSDT", "ETHUSDT"]
    assert defaults.MACRO_SYNC_WINDOW == 60
    assert defaults.ENABLE_NEW_METRICS is True
    assert defaults.EMA_BIAS_CLAMP == 0.02
    assert defaults.VOLUME_SPIKE_CAP == 3.0
    assert defaults.VOLATILITY_RATIO_CAP == 3.0
    assert defaults.LIQUIDITY_KAPPA_MIN == 0.3
    assert defaults.LIQUIDITY_KAPPA_MAX == 1.0


def test_ema_config_defaults():
    """Test EMAConfig uses correct defaults."""
    config = EMAConfig()
    assert config.period_short == 3
    assert config.period_long == 7
    assert config.bias_clamp == 0.02


def test_ema_config_custom():
    """Test EMAConfig accepts custom values."""
    config = EMAConfig(period_short=5, period_long=10, bias_clamp=0.05)
    assert config.period_short == 5
    assert config.period_long == 10
    assert config.bias_clamp == 0.05


def test_volume_config_defaults():
    """Test VolumeConfig uses correct defaults."""
    config = VolumeConfig()
    assert config.sma_length == 5
    assert config.window_sec == 60
    assert config.spike_cap == 3.0


def test_volume_config_custom():
    """Test VolumeConfig accepts custom values."""
    config = VolumeConfig(sma_length=10, window_sec=120, spike_cap=5.0)
    assert config.sma_length == 10
    assert config.window_sec == 120
    assert config.spike_cap == 5.0


def test_volatility_config_defaults():
    """Test VolatilityConfig uses correct defaults."""
    config = VolatilityConfig()
    assert config.sma_length == 10
    assert config.window_sec == 60
    assert config.ratio_cap == 3.0


def test_volatility_config_custom():
    """Test VolatilityConfig accepts custom values."""
    config = VolatilityConfig(sma_length=20, window_sec=120, ratio_cap=5.0)
    assert config.sma_length == 20
    assert config.window_sec == 120
    assert config.ratio_cap == 5.0


def test_liquidity_config_defaults():
    """Test LiquidityConfig uses correct defaults."""
    config = LiquidityConfig()
    assert config.depth_half == 1000.0
    assert config.kappa_min == 0.3
    assert config.kappa_max == 1.0


def test_liquidity_config_custom():
    """Test LiquidityConfig accepts custom values."""
    config = LiquidityConfig(depth_half=2000.0, kappa_min=0.2, kappa_max=0.8)
    assert config.depth_half == 2000.0
    assert config.kappa_min == 0.2
    assert config.kappa_max == 0.8


def test_macro_sync_config_defaults():
    """Test MacroSyncConfig uses correct defaults."""
    config = MacroSyncConfig()
    assert config.enabled is False
    assert config.anchors == ["BTCUSDT", "ETHUSDT"]
    assert config.window == 60


def test_macro_sync_config_custom():
    """Test MacroSyncConfig accepts custom values."""
    config = MacroSyncConfig(enabled=True, anchors=["ADAUSDT"], window=120)
    assert config.enabled is True
    assert config.anchors == ["ADAUSDT"]
    assert config.window == 120


def test_feature_engineering_config_dict_config():
    """Test FeatureEngineeringConfig with dict config."""
    config = {
        "trading": {
            "feature_engineering": {
                "enable_new_metrics": False,
                "ema": {
                    "period_short": 5,
                    "period_long": 10,
                    "bias_clamp": 0.05
                },
                "volume": {
                    "sma_length": 10,
                    "window_sec": 120,
                    "spike_cap": 5.0
                },
                "volatility": {
                    "sma_length": 20,
                    "window_sec": 120,
                    "ratio_cap": 5.0
                },
                "liquidity": {
                    "depth_half": 2000.0,
                    "kappa_min": 0.2,
                    "kappa_max": 0.8
                }
            },
            "market_data": {
                "macro_sync": {
                    "enabled": True,
                    "anchors": ["ADAUSDT"],
                    "window": 120
                }
            }
        }
    }

    fe_config = FeatureEngineeringConfig(config)

    assert fe_config.enable_new_metrics is False
    assert fe_config.ema.period_short == 5
    assert fe_config.ema.period_long == 10
    assert fe_config.ema.bias_clamp == 0.05
    assert fe_config.volume.sma_length == 10
    assert fe_config.volume.window_sec == 120
    assert fe_config.volume.spike_cap == 5.0
    assert fe_config.volatility.sma_length == 20
    assert fe_config.volatility.window_sec == 120
    assert fe_config.volatility.ratio_cap == 5.0
    assert fe_config.liquidity.depth_half == 2000.0
    assert fe_config.liquidity.kappa_min == 0.2
    assert fe_config.liquidity.kappa_max == 0.8
    assert fe_config.macro_sync.enabled is True
    assert fe_config.macro_sync.anchors == ["ADAUSDT"]
    assert fe_config.macro_sync.window == 120


def test_feature_engineering_config_empty_dict():
    """Test FeatureEngineeringConfig with empty dict config."""
    config = {}

    fe_config = FeatureEngineeringConfig(config)

    # Should use all defaults
    assert fe_config.enable_new_metrics is True
    assert fe_config.ema.period_short == 3
    assert fe_config.ema.period_long == 7
    assert fe_config.ema.bias_clamp == 0.02
    assert fe_config.volume.sma_length == 5
    assert fe_config.volume.window_sec == 60
    assert fe_config.volume.spike_cap == 3.0
    assert fe_config.volatility.sma_length == 10
    assert fe_config.volatility.window_sec == 60
    assert fe_config.volatility.ratio_cap == 3.0
    assert fe_config.liquidity.depth_half == 1000.0
    assert fe_config.liquidity.kappa_min == 0.3
    assert fe_config.liquidity.kappa_max == 1.0
    assert fe_config.macro_sync.enabled is False
    assert fe_config.macro_sync.anchors == ["BTCUSDT", "ETHUSDT"]
    assert fe_config.macro_sync.window == 60


def test_feature_engineering_config_get_fe_config():
    """Test _get_fe_config method."""
    config = {
        "trading": {
            "feature_engineering": {
                "enable_new_metrics": False
            }
        }
    }

    fe_config = FeatureEngineeringConfig(config)
    fe_section = fe_config._get_fe_config()

    assert fe_section == {"enable_new_metrics": False}


def test_feature_engineering_config_load_enable_new_metrics():
    """Test _load_enable_new_metrics method."""
    config = {
        "trading": {
            "feature_engineering": {
                "enable_new_metrics": False
            }
        }
    }

    fe_config = FeatureEngineeringConfig(config)
    assert fe_config.enable_new_metrics is False


def test_feature_engineering_config_load_ema_config():
    """Test _load_ema_config method."""
    config = {
        "trading": {
            "feature_engineering": {
                "ema": {
                    "period_short": 5,
                    "period_long": 10,
                    "bias_clamp": 0.05
                }
            }
        }
    }

    fe_config = FeatureEngineeringConfig(config)
    assert fe_config.ema.period_short == 5
    assert fe_config.ema.period_long == 10
    assert fe_config.ema.bias_clamp == 0.05


def test_feature_engineering_config_load_volume_config():
    """Test _load_volume_config method."""
    config = {
        "trading": {
            "feature_engineering": {
                "volume": {
                    "sma_length": 10,
                    "window_sec": 120,
                    "spike_cap": 5.0
                }
            }
        }
    }

    fe_config = FeatureEngineeringConfig(config)
    assert fe_config.volume.sma_length == 10
    assert fe_config.volume.window_sec == 120
    assert fe_config.volume.spike_cap == 5.0


def test_feature_engineering_config_load_volatility_config():
    """Test _load_volatility_config method."""
    config = {
        "trading": {
            "feature_engineering": {
                "volatility": {
                    "sma_length": 20,
                    "window_sec": 120,
                    "ratio_cap": 5.0
                }
            }
        }
    }

    fe_config = FeatureEngineeringConfig(config)
    assert fe_config.volatility.sma_length == 20
    assert fe_config.volatility.window_sec == 120
    assert fe_config.volatility.ratio_cap == 5.0


def test_feature_engineering_config_load_liquidity_config():
    """Test _load_liquidity_config method."""
    config = {
        "trading": {
            "feature_engineering": {
                "liquidity": {
                    "depth_half": 2000.0,
                    "kappa_min": 0.2,
                    "kappa_max": 0.8
                }
            }
        }
    }

    fe_config = FeatureEngineeringConfig(config)
    assert fe_config.liquidity.depth_half == 2000.0
    assert fe_config.liquidity.kappa_min == 0.2
    assert fe_config.liquidity.kappa_max == 0.8


def test_feature_engineering_config_load_macro_sync_config():
    """Test _load_macro_sync_config method."""
    config = {
        "trading": {
            "market_data": {
                "macro_sync": {
                    "enabled": True,
                    "anchors": ["ADAUSDT"],
                    "window": 120
                }
            }
        }
    }

    fe_config = FeatureEngineeringConfig(config)
    assert fe_config.macro_sync.enabled is True
    assert fe_config.macro_sync.anchors == ["ADAUSDT"]
    assert fe_config.macro_sync.window == 120


# Tests for feature_engineering_phase1.py coverage


@pytest.fixture
def mock_config_phase1():
    """Mock config for Phase 1 testing."""
    return Mock()
    # Configure the mock to have the required structure
    mock_config.trading = Mock()
    mock_config.trading.feature_engineering = Mock()
    mock_config.trading.feature_engineering.enable_new_metrics = True
    mock_config.trading.feature_engineering.ema = Mock()
    mock_config.trading.feature_engineering.ema.period_short = 3
    mock_config.trading.feature_engineering.ema.period_long = 7
    mock_config.trading.feature_engineering.volume = Mock()
    mock_config.trading.feature_engineering.volume.sma_length = 5
    mock_config.trading.feature_engineering.volume.window_sec = 60
    mock_config.trading.feature_engineering.volatility = Mock()
    mock_config.trading.feature_engineering.volatility.sma_length = 10
    mock_config.trading.feature_engineering.volatility.window_sec = 60
    mock_config.trading.feature_engineering.liquidity = Mock()
    mock_config.trading.feature_engineering.liquidity.depth_half = 1000.0
    mock_config.trading.market_data = Mock()
    mock_config.trading.market_data.macro_sync = Mock()
    mock_config.trading.market_data.macro_sync.enabled = True
    mock_config.trading.market_data.macro_sync.anchors = ["BTCUSDT", "ETHUSDT"]
    mock_config.trading.market_data.macro_sync.window = 60
    return mock_config


def test_phase1_init_symbol_state():
    """Test _init_symbol_state method."""
    # Create a mock config with required attributes
    mock_config = Mock()
    mock_config.trading = Mock()
    mock_config.trading.feature_engineering = Mock()
    mock_config.trading.feature_engineering.ema = Mock()
    mock_config.trading.feature_engineering.ema.period_short = 3
    mock_config.trading.feature_engineering.ema.period_long = 7
    mock_config.trading.feature_engineering.volume = Mock()
    mock_config.trading.feature_engineering.volume.sma_length = 5
    mock_config.trading.feature_engineering.volatility = Mock()
    mock_config.trading.feature_engineering.volatility.sma_length = 10
    mock_config.trading.market_data = Mock()
    mock_config.trading.market_data.macro_sync = Mock()
    mock_config.trading.market_data.macro_sync.window = 60
    mock_config.trading.market_data.macro_sync.enabled = True
    mock_config.trading.market_data.macro_sync.anchors = ["BTCUSDT", "ETHUSDT"]

    fsm = Mock()
    fe = FeatureEngineeringPhase1(fsm=fsm, config=mock_config)

    # Test initialization
    fe._init_symbol_state("BTCUSDT")

    assert "BTCUSDT" in fe.symbol_state
    state = fe.symbol_state["BTCUSDT"]
    assert state["ema3"] is None
    assert state["ema7"] is None
    assert state["ema3_alpha"] == 2 / (3 + 1)  # 2/(period_short+1)
    assert state["ema7_alpha"] == 2 / (7 + 1)  # 2/(period_long+1)
    assert state["vol_hist"].maxlen == 5
    assert state["range_hist"].maxlen == 10
    assert state["returns_buffer"].maxlen == 60


def test_phase1_update_ema():
    """Test _update_ema method."""
    mock_config = Mock()
    mock_config.trading = Mock()
    mock_config.trading.feature_engineering = Mock()
    mock_config.trading.feature_engineering.ema = Mock()
    mock_config.trading.feature_engineering.ema.period_short = 3
    mock_config.trading.feature_engineering.ema.period_long = 7
    mock_config.trading.market_data = Mock()
    mock_config.trading.market_data.macro_sync = Mock()
    mock_config.trading.market_data.macro_sync.window = 60
    mock_config.trading.market_data.macro_sync.enabled = True
    mock_config.trading.market_data.macro_sync.anchors = ["BTCUSDT", "ETHUSDT"]

    fsm = Mock()
    fe = FeatureEngineeringPhase1(fsm=fsm, config=mock_config)
    fe._init_symbol_state("BTCUSDT")

    # First update should set initial values
    fe._update_ema("BTCUSDT", decimal.Decimal("50000"))
    state = fe.symbol_state["BTCUSDT"]
    assert state["ema3"] == decimal.Decimal("50000")
    assert state["ema7"] == decimal.Decimal("50000")

    # Second update should calculate EMA
    fe._update_ema("BTCUSDT", decimal.Decimal("50100"))
    alpha3 = decimal.Decimal("2") / decimal.Decimal("4")  # 2/(3+1)
    alpha7 = decimal.Decimal("2") / decimal.Decimal("8")  # 2/(7+1)
    expected_ema3 = decimal.Decimal(
        "50100") * alpha3 + decimal.Decimal("50000") * (1 - alpha3)
    expected_ema7 = decimal.Decimal(
        "50100") * alpha7 + decimal.Decimal("50000") * (1 - alpha7)

    assert state["ema3"] == expected_ema3
    assert state["ema7"] == expected_ema7


def test_phase1_compute_ema_bias():
    """Test _compute_ema_bias method."""
    mock_config = Mock()
    mock_config.trading = Mock()
    mock_config.trading.feature_engineering = Mock()
    mock_config.trading.feature_engineering.ema = Mock()
    mock_config.trading.market_data = Mock()
    mock_config.trading.market_data.macro_sync = Mock()
    mock_config.trading.market_data.macro_sync.window = 60
    mock_config.trading.market_data.macro_sync.enabled = True
    mock_config.trading.market_data.macro_sync.anchors = ["BTCUSDT", "ETHUSDT"]

    fsm = Mock()
    fe = FeatureEngineeringPhase1(fsm=fsm, config=mock_config)
    fe._init_symbol_state("BTCUSDT")

    # Set EMA values
    fe.symbol_state["BTCUSDT"]["ema3"] = decimal.Decimal("50100")
    fe.symbol_state["BTCUSDT"]["ema7"] = decimal.Decimal("50000")

    bias = fe._compute_ema_bias("BTCUSDT")
    expected_bias = (decimal.Decimal("50100") -
                     decimal.Decimal("50000")) / decimal.Decimal("50000")  # 0.02
    expected_phi = (expected_bias / decimal.Decimal("0.02") +
                    decimal.Decimal("1")) / decimal.Decimal("2")  # 1.0

    assert bias == expected_phi


def test_phase1_compute_ema_bias_zero_division():
    """Test _compute_ema_bias with zero EMA7."""
    mock_config = Mock()
    mock_config.trading = Mock()
    mock_config.trading.feature_engineering = Mock()
    mock_config.trading.market_data = Mock()
    mock_config.trading.market_data.macro_sync = Mock()
    mock_config.trading.market_data.macro_sync.window = 60
    mock_config.trading.market_data.macro_sync.enabled = True
    mock_config.trading.market_data.macro_sync.anchors = ["BTCUSDT", "ETHUSDT"]

    fsm = Mock()
    fe = FeatureEngineeringPhase1(fsm=fsm, config=mock_config)
    fe._init_symbol_state("BTCUSDT")

    # Set EMA7 to zero
    fe.symbol_state["BTCUSDT"]["ema3"] = decimal.Decimal("50100")
    fe.symbol_state["BTCUSDT"]["ema7"] = decimal.Decimal("0")

    bias = fe._compute_ema_bias("BTCUSDT")
    assert bias == decimal.Decimal("0.5")  # Default when division by zero


def test_phase1_update_volume_spike():
    """Test _update_volume_spike method."""
    mock_config = Mock()
    mock_config.trading = Mock()
    mock_config.trading.feature_engineering = Mock()
    mock_config.trading.feature_engineering.volume = Mock()
    mock_config.trading.feature_engineering.volume.window_sec = 60
    mock_config.trading.market_data = Mock()
    mock_config.trading.market_data.macro_sync = Mock()
    mock_config.trading.market_data.macro_sync.window = 60
    mock_config.trading.market_data.macro_sync.enabled = True
    mock_config.trading.market_data.macro_sync.anchors = ["BTCUSDT", "ETHUSDT"]

    fsm = Mock()
    fe = FeatureEngineeringPhase1(fsm=fsm, config=mock_config)
    fe._init_symbol_state("BTCUSDT")

    # First tick initializes window
    tick1 = {"ts": 1000}
    fe._update_volume_spike("BTCUSDT", tick1, 0)
    state = fe.symbol_state["BTCUSDT"]
    assert state["vol_window_start_ts"] == 1000
    assert state["vol_window_trades"] == 1

    # Second tick in same window
    tick2 = {"ts": 2000}
    fe._update_volume_spike("BTCUSDT", tick2, 1000)
    assert state["vol_window_trades"] == 2

    # Tick that closes window (61 seconds later)
    tick3 = {"ts": 1000 + 61000}
    fe._update_volume_spike("BTCUSDT", tick3, 60000)
    assert state["vol_window_start_ts"] == 1000 + 61000
    assert state["vol_window_trades"] == 1  # Reset and counted new tick
    assert len(state["vol_hist"]) == 1
    assert state["vol_hist"][0] == 2  # Previous window had 2 trades


def test_phase1_compute_volume_spike():
    """Test _compute_volume_spike method."""
    mock_config = Mock()
    mock_config.trading = Mock()
    mock_config.trading.feature_engineering = Mock()
    mock_config.trading.market_data = Mock()
    mock_config.trading.market_data.macro_sync = Mock()
    mock_config.trading.market_data.macro_sync.window = 60
    mock_config.trading.market_data.macro_sync.enabled = True
    mock_config.trading.market_data.macro_sync.anchors = ["BTCUSDT", "ETHUSDT"]

    fsm = Mock()
    fe = FeatureEngineeringPhase1(fsm=fsm, config=mock_config)
    fe._init_symbol_state("BTCUSDT")

    # Not enough history
    spike = fe._compute_volume_spike("BTCUSDT")
    assert spike == decimal.Decimal("0.5")

    # Add history
    state = fe.symbol_state["BTCUSDT"]
    state["vol_hist"].extend([10, 20, 15])  # avg = 15
    state["vol_window_trades"] = 30  # current = 30

    spike = fe._compute_volume_spike("BTCUSDT")
    expected_spike = decimal.Decimal("30") / decimal.Decimal("15")  # 2.0
    # 2.0/3.0 = 0.666...
    expected_phi = min(expected_spike, decimal.Decimal(
        "3.0")) / decimal.Decimal("3.0")

    assert spike == expected_phi


def test_phase1_update_volatility_state():
    """Test _update_volatility_state method."""
    mock_config = Mock()
    mock_config.trading = Mock()
    mock_config.trading.feature_engineering = Mock()
    mock_config.trading.feature_engineering.volatility = Mock()
    mock_config.trading.feature_engineering.volatility.window_sec = 60
    mock_config.trading.market_data = Mock()
    mock_config.trading.market_data.macro_sync = Mock()
    mock_config.trading.market_data.macro_sync.window = 60
    mock_config.trading.market_data.macro_sync.enabled = True
    mock_config.trading.market_data.macro_sync.anchors = ["BTCUSDT", "ETHUSDT"]

    fsm = Mock()
    fe = FeatureEngineeringPhase1(fsm=fsm, config=mock_config)
    fe._init_symbol_state("BTCUSDT")

    # First price initializes window
    fe._update_volatility_state(
        "BTCUSDT", decimal.Decimal("50000"), {"ts": 1000})
    state = fe.symbol_state["BTCUSDT"]
    assert state["range_window_start_ts"] == 1000
    assert state["range_min"] == decimal.Decimal("50000")
    assert state["range_max"] == decimal.Decimal("50000")

    # Update with higher price
    fe._update_volatility_state(
        "BTCUSDT", decimal.Decimal("50100"), {"ts": 2000})
    assert state["range_min"] == decimal.Decimal("50000")
    assert state["range_max"] == decimal.Decimal("50100")

    # Update with lower price
    fe._update_volatility_state(
        "BTCUSDT", decimal.Decimal("49900"), {"ts": 3000})
    assert state["range_min"] == decimal.Decimal("49900")
    assert state["range_max"] == decimal.Decimal("50100")


def test_phase1_compute_volatility_state():
    """Test _compute_volatility_state method."""
    mock_config = Mock()
    mock_config.trading = Mock()
    mock_config.trading.feature_engineering = Mock()
    mock_config.trading.market_data = Mock()
    mock_config.trading.market_data.macro_sync = Mock()
    mock_config.trading.market_data.macro_sync.window = 60
    mock_config.trading.market_data.macro_sync.enabled = True
    mock_config.trading.market_data.macro_sync.anchors = ["BTCUSDT", "ETHUSDT"]

    fsm = Mock()
    fe = FeatureEngineeringPhase1(fsm=fsm, config=mock_config)
    fe._init_symbol_state("BTCUSDT")

    # Not enough history
    vol_state = fe._compute_volatility_state("BTCUSDT")
    assert vol_state == decimal.Decimal("0.5")

    # Add history
    state = fe.symbol_state["BTCUSDT"]
    state["range_hist"].extend([decimal.Decimal("100"), decimal.Decimal(
        "200"), decimal.Decimal("150")])  # avg = 150
    state["range_min"] = decimal.Decimal("50000")
    state["range_max"] = decimal.Decimal("50200")  # range = 200

    vol_state = fe._compute_volatility_state("BTCUSDT")
    # 1.333...
    expected_ratio = decimal.Decimal("200") / decimal.Decimal("150")
    # 1.333/3.0 = 0.444...
    expected_phi = min(expected_ratio, decimal.Decimal(
        "3.0")) / decimal.Decimal("3.0")

    assert vol_state == expected_phi


def test_phase1_compute_depth_imbalance():
    """Test _compute_depth_imbalance method."""
    mock_config = Mock()
    mock_config.trading = Mock()
    mock_config.trading.feature_engineering = Mock()
    mock_config.trading.feature_engineering.liquidity = Mock()
    mock_config.trading.feature_engineering.liquidity.depth_half = 1000.0
    mock_config.trading.market_data = Mock()
    mock_config.trading.market_data.macro_sync = Mock()
    mock_config.trading.market_data.macro_sync.window = 60
    mock_config.trading.market_data.macro_sync.enabled = True
    mock_config.trading.market_data.macro_sync.anchors = ["BTCUSDT", "ETHUSDT"]

    fsm = Mock()
    fe = FeatureEngineeringPhase1(fsm=fsm, config=mock_config)

    bid_size = decimal.Decimal("500")
    ask_size = decimal.Decimal("300")

    imbalance = fe._compute_depth_imbalance(bid_size, ask_size)

    # ratio = (300 + 1000) / (500 + 1000) = 1300/1500 = 0.866...
    # imbalance = (0.866 - 1) / (0.866 + 1) = (-0.134) / 1.866 = -0.0718...
    # phi = (-0.0718 + 1) / 2 = 0.9282 / 2 = 0.4641...

    expected_ratio = decimal.Decimal("1300") / decimal.Decimal("1500")
    expected_imbalance = (expected_ratio - decimal.Decimal("1")) / \
        (expected_ratio + decimal.Decimal("1"))
    expected_phi = (expected_imbalance + decimal.Decimal("1")
                    ) / decimal.Decimal("2")

    assert imbalance == expected_phi


def test_phase1_update_macro_sync_buffer():
    """Test _update_macro_sync_buffer method."""
    mock_config = Mock()
    mock_config.trading = Mock()
    mock_config.trading.market_data = Mock()
    mock_config.trading.market_data.macro_sync = Mock()
    mock_config.trading.market_data.macro_sync.window = 60
    mock_config.trading.market_data.macro_sync.enabled = True
    mock_config.trading.market_data.macro_sync.anchors = ["BTCUSDT", "ETHUSDT"]

    fsm = Mock()
    fe = FeatureEngineeringPhase1(fsm=fsm, config=mock_config)
    fe._init_symbol_state("BTCUSDT")

    # First call sets prev_price
    fe._update_macro_sync_buffer(
        "BTCUSDT", decimal.Decimal("50000"), {"ts": 1000}, 1000)
    state = fe.symbol_state["BTCUSDT"]
    assert state["prev_price"] == decimal.Decimal("50000")
    assert len(state["returns_buffer"]) == 0

    # Second call calculates return
    fe._update_macro_sync_buffer(
        "BTCUSDT", decimal.Decimal("50100"), {"ts": 2000}, 1000)
    assert state["prev_price"] == decimal.Decimal("50100")
    assert len(state["returns_buffer"]) == 1
    assert state["returns_buffer"][0] == 0.002  # (50100-50000)/50000


def test_phase1_compute_macro_sync():
    """Test _compute_macro_sync method."""
    mock_config = Mock()
    mock_config.trading = Mock()
    mock_config.trading.market_data = Mock()
    mock_config.trading.market_data.macro_sync = Mock()
    mock_config.trading.market_data.macro_sync.enabled = True
    mock_config.trading.market_data.macro_sync.anchors = ["BTCUSDT", "ETHUSDT"]
    mock_config.trading.market_data.macro_sync.window = 60

    fsm = Mock()
    fe = FeatureEngineeringPhase1(fsm=fsm, config=mock_config)
    fe._init_symbol_state("ADAUSDT")

    # Not enough data
    sync = fe._compute_macro_sync("ADAUSDT")
    assert sync == decimal.Decimal("0.5")

    # Add returns buffer
    state = fe.symbol_state["ADAUSDT"]
    state["returns_buffer"].extend([0.01, 0.02, 0.03])

    # Add anchor prices
    fe.anchor_prices["BTCUSDT"].extend(
        [decimal.Decimal("50000"), decimal.Decimal("50100"), decimal.Decimal("50200")])
    fe.anchor_prices["ETHUSDT"].extend(
        [decimal.Decimal("3000"), decimal.Decimal("3010"), decimal.Decimal("3020")])

    sync = fe._compute_macro_sync("ADAUSDT")
    # Should compute correlation and map to [0,1]
    assert isinstance(sync, decimal.Decimal)
    assert 0 <= sync <= 1


def test_phase1_pearson_correlation():
    """Test _pearson_correlation method."""
    mock_config = Mock()
    mock_config.trading = Mock()
    mock_config.trading.market_data = Mock()
    mock_config.trading.market_data.macro_sync = Mock()
    mock_config.trading.market_data.macro_sync.window = 60
    mock_config.trading.market_data.macro_sync.enabled = True
    mock_config.trading.market_data.macro_sync.anchors = ["BTCUSDT", "ETHUSDT"]

    fsm = Mock()
    fe = FeatureEngineeringPhase1(fsm=fsm, config=mock_config)

    # Perfect positive correlation
    x = [1, 2, 3, 4, 5]
    y = [2, 4, 6, 8, 10]
    corr = fe._pearson_correlation(x, y)
    assert abs(corr - 1.0) < 0.001

    # Perfect negative correlation
    y_neg = [-2, -4, -6, -8, -10]
    corr_neg = fe._pearson_correlation(x, y_neg)
    assert abs(corr_neg - (-1.0)) < 0.001

    # No correlation
    y_zero = [1, 1, 1, 1, 1]
    corr_zero = fe._pearson_correlation(x, y_zero)
    assert abs(corr_zero) < 0.001

    # Edge cases
    corr_empty = fe._pearson_correlation([], [])
    assert corr_empty == 0.0

    corr_short = fe._pearson_correlation([1], [2])
    assert corr_short == 0.0


def test_phase1_start_stop():
    """Test start and stop methods."""
    mock_config = Mock()
    mock_config.trading = Mock()
    mock_config.trading.market_data = Mock()
    mock_config.trading.market_data.macro_sync = Mock()
    mock_config.trading.market_data.macro_sync.window = 60
    mock_config.trading.market_data.macro_sync.enabled = True
    mock_config.trading.market_data.macro_sync.anchors = ["BTCUSDT", "ETHUSDT"]

    fsm = Mock()
    fe = FeatureEngineeringPhase1(fsm=fsm, config=mock_config)

    # Test start
    fe.start()
    # Should not raise any exceptions

    # Test stop
    fe.stop()
    # Should not raise any exceptions
