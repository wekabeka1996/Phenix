"""
Test Suite for RegimeDetector Domain

Tests the regime detection logic that analyzes market features
and identifies trading regimes (TREND_UP, TREND_DOWN, etc.)

WHY: TDD approach - define expected behavior before implementation [FSMP-PORTING-T01B]
"""

import pytest
import sys
import importlib.util
from pathlib import Path
from unittest.mock import MagicMock
from decimal import Decimal
import time
from apps.reference.config_loader import ConfigLoader

# Direct import of regime_detector module
project_root = Path(__file__).parent.parent.parent
regime_detector_path = (
    project_root
    / "apps"
    / "reference"
    / "domains"
    / "regime_detector"
    / "regime_detector.py"
)

spec = importlib.util.spec_from_file_location(
    "regime_detector_module", regime_detector_path
)
regime_detector_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(regime_detector_module)

RegimeDetector = regime_detector_module.RegimeDetector

# Setup vfoundation path for Message import
vfoundation_root = project_root / "vfoundation" / "vfoundation"
if str(vfoundation_root) not in sys.path:
    sys.path.insert(0, str(vfoundation_root))

from vfoundation.core.protocol import Message


@pytest.fixture
def mock_fsm_core():
    """Provides a mock FSM core with an emit method."""
    fsm = MagicMock()
    fsm.emit = MagicMock()
    fsm.listen = MagicMock()
    return fsm


@pytest.fixture
def mock_config():
    """Load the real AuroraConfig for RegimeDetector (strict object config)."""
    return ConfigLoader().load_config()


def test_detects_trend_up_regime_on_clear_signal(mock_config, mock_fsm_core):
    """
    Verify that the detector correctly identifies an uptrend when the price
    and short-term moving average are above the long-term one.

    WHY: Test core functionality - SMA crossover indicates trend direction
    """
    # --- Arrange ---
    # Initialize our (not yet existing) domain
    regime_detector = RegimeDetector(config=mock_config, fsm=mock_fsm_core)
    regime_detector.logger = MagicMock()

    # Create an event with features clearly indicating an uptrend
    features_event = Message(
        op="EVT",
        verb="FEATURES_CALCULATED",
        pld={
            "ts": 1731234567000000,
            "symbol": "ETHUSDT",
            "features": {
                "price": "4100.0",
                "sma_short": "4050.0",  # Short SMA > Long SMA
                "sma_long": "3900.0",
            },
        },
        src="feature_engineering",
        dst="regime_detector",
        rid="RID-test-001",
    )

    # --- Act ---
    regime_detector.handle_event(features_event)

    # --- Assert ---
    # Verify that exactly one event was emitted
    mock_fsm_core.emit.assert_called_once()

    # Verify the name and content of the emitted event
    emitted_event_name = mock_fsm_core.emit.call_args[0][0]
    emitted_payload = mock_fsm_core.emit.call_args[0][1]

    assert emitted_event_name == "EVT:REGIME_DETECTED"
    assert emitted_payload["symbol"] == "ETHUSDT"
    assert emitted_payload["regime"] == "TREND_UP"
    assert Decimal(emitted_payload["confidence"]) > Decimal("0.7"), (
        "Confidence should be high for clear signal"
    )
    assert emitted_payload["source_model"] == "sma_trend_v1"

    # Verify timestamp is present
    assert "ts" in emitted_payload
    assert isinstance(emitted_payload["ts"], int)


def test_detects_trend_down_regime_on_clear_signal(mock_config, mock_fsm_core):
    """
    Verify that the detector correctly identifies a downtrend when the price
    and short-term moving average are below the long-term one.

    WHY: Test TREND_DOWN detection - SMA crossover down indicates bearish trend
    Scenario: Price 3700, SMA short 3750, SMA long 3900 → TREND_DOWN
    """
    # --- Arrange ---
    regime_detector = RegimeDetector(config=mock_config, fsm=mock_fsm_core)
    regime_detector.logger = MagicMock()

    # Create event with features clearly indicating a downtrend
    features_event = Message(
        op="EVT",
        verb="FEATURES_CALCULATED",
        pld={
            "ts": 1731235000000000,
            "symbol": "ETHUSDT",
            "features": {
                "price": "3700.0",  # Price below short SMA
                "sma_short": "3750.0",  # Short SMA < Long SMA
                "sma_long": "3900.0",
            },
        },
        src="feature_engineering",
        dst="regime_detector",
        rid="RID-test-002",
    )

    # --- Act ---
    regime_detector.handle_event(features_event)

    # --- Assert ---
    # Verify that exactly one event was emitted
    mock_fsm_core.emit.assert_called_once()

    # Verify the name and content of the emitted event
    emitted_event_name = mock_fsm_core.emit.call_args[0][0]
    emitted_payload = mock_fsm_core.emit.call_args[0][1]

    assert emitted_event_name == "EVT:REGIME_DETECTED"
    assert emitted_payload["symbol"] == "ETHUSDT"
    assert emitted_payload["regime"] == "TREND_DOWN", (
        "Expected TREND_DOWN for bearish signal"
    )
    assert Decimal(emitted_payload["confidence"]) > Decimal("0.7"), (
        "Confidence should be high for clear downtrend"
    )
    assert emitted_payload["source_model"] == "sma_trend_v1"

    # Verify timestamp is present
    assert "ts" in emitted_payload
    assert isinstance(emitted_payload["ts"], int)


def test_detects_mean_reversion_regime_when_price_is_close_to_smas(
    mock_config, mock_fsm_core
):
    """
    Verify that the detector identifies a mean-reverting regime when the price
    is very close to both short and long-term moving averages.

    WHY: Test MEAN_REVERSION detection - tight price range around SMAs indicates ranging market
    Scenario: Price 3898, SMA short 3900, SMA long 3902 → tight convergence → MEAN_REVERSION
    """
    # --- Arrange ---
    regime_detector = RegimeDetector(config=mock_config, fsm=mock_fsm_core)
    regime_detector.logger = MagicMock()

    # Create event with features showing price "squeezed" between moving averages
    features_event = Message(
        op="EVT",
        verb="FEATURES_CALCULATED",
        pld={
            "ts": 1731236000000000,
            "symbol": "ETHUSDT",
            "features": {
                "price": "3898.0",  # Price very close to both SMAs
                "sma_short": "3900.0",  # All three values tightly clustered
                "sma_long": "3902.0",  # Indicates ranging/sideways market
            },
        },
        src="feature_engineering",
        dst="regime_detector",
        rid="RID-test-003",
    )

    # --- Act ---
    regime_detector.handle_event(features_event)

    # --- Assert ---
    # Verify that exactly one event was emitted
    mock_fsm_core.emit.assert_called_once()

    # Verify the name and content of the emitted event
    emitted_event_name = mock_fsm_core.emit.call_args[0][0]
    emitted_payload = mock_fsm_core.emit.call_args[0][1]

    assert emitted_event_name == "EVT:REGIME_DETECTED"
    assert emitted_payload["symbol"] == "ETHUSDT"
    assert emitted_payload["regime"] == "MEAN_REVERSION", (
        "Expected MEAN_REVERSION for ranging market"
    )
    assert Decimal(emitted_payload["confidence"]) > Decimal("0.8"), (
        "Confidence should be very high for tight convergence"
    )
    assert emitted_payload["source_model"] == "mean_reversion_v2"

    # Verify timestamp is present
    assert "ts" in emitted_payload
    assert isinstance(emitted_payload["ts"], int)


def test_detects_high_volatility_regime_on_atr_spike(mock_config, mock_fsm_core):
    """
    Verify that the detector identifies a HIGH_VOLATILITY regime when the
    Average True Range (ATR) is significantly above its long-term average.

    WHY: Enable volatility-adaptive position sizing [FSMP-PORTING-T01K]
    """
    # --- Arrange ---
    regime_detector = RegimeDetector(config=mock_config, fsm=mock_fsm_core)
    regime_detector.logger = MagicMock()

    symbol = "ETHUSDT"

    # Warm up ATR baseline with calm ticks (close-to-close ATR enabled in canonical config).
    for i in range(120):
        ts_ms = int(time.time() * 1000)
        e = Message(
            op="EVT",
            verb="FEATURES_CALCULATED",
            pld={"ts": ts_ms, "symbol": symbol, "features": {"price": str(1000 + i)}},
            src="feature_engineering",
            dst="regime_detector",
            rid=f"RID-warmup-{i}",
        )
        regime_detector.handle_event(e)

    # Spike: large jump should produce HIGH_VOLATILITY once baseline is ready.
    ts_ms = int(time.time() * 1000)
    features_event = Message(
        op="EVT",
        verb="FEATURES_CALCULATED",
        pld={"ts": ts_ms, "symbol": symbol, "features": {"price": "5000.0"}},
        src="feature_engineering",
        dst="regime_detector",
        rid="RID-test-004",
    )

    # --- Act ---
    regime_detector.handle_event(features_event)

    # --- Assert ---
    assert mock_fsm_core.emit.call_count >= 1
    emitted_event_name = mock_fsm_core.emit.call_args_list[-1][0][0]
    emitted_payload = mock_fsm_core.emit.call_args_list[-1][0][1]

    assert emitted_event_name == "EVT:REGIME_DETECTED"
    assert emitted_payload["regime"] == "HIGH_VOLATILITY"
    assert Decimal(emitted_payload["confidence"]) >= Decimal("0.5")
    assert emitted_payload["source_model"] == "volatility_v2"


def test_detects_low_volatility_regime_on_atr_calm(mock_config, mock_fsm_core):
    """
    Verify that the detector identifies a LOW_VOLATILITY regime when the
    Average True Range (ATR) is significantly below its long-term average.

    WHY: Enable calm market detection for adaptive strategies [FSMP-PORTING-T01L]
    """
    # --- Arrange ---
    regime_detector = RegimeDetector(config=mock_config, fsm=mock_fsm_core)
    regime_detector.logger = MagicMock()

    symbol = "ETHUSDT"

    # Warm up ATR baseline with volatile ticks (large TR), then calm down.
    price = 10_000
    for i in range(120):
        ts_ms = int(time.time() * 1000)
        price = price + 100 if (i % 2 == 0) else price - 100
        e = Message(
            op="EVT",
            verb="FEATURES_CALCULATED",
            pld={"ts": ts_ms, "symbol": symbol, "features": {"price": str(price)}},
            src="feature_engineering",
            dst="regime_detector",
            rid=f"RID-warmup-vol-{i}",
        )
        regime_detector.handle_event(e)

    for i in range(40):
        ts_ms = int(time.time() * 1000)
        price = price + 1
        e = Message(
            op="EVT",
            verb="FEATURES_CALCULATED",
            pld={"ts": ts_ms, "symbol": symbol, "features": {"price": str(price)}},
            src="feature_engineering",
            dst="regime_detector",
            rid=f"RID-calm-{i}",
        )
        regime_detector.handle_event(e)

    # One more tick to assert the final regime.
    ts_ms = int(time.time() * 1000)
    features_event = Message(
        op="EVT",
        verb="FEATURES_CALCULATED",
        pld={"ts": ts_ms, "symbol": symbol, "features": {"price": str(price + 1)}},
        src="feature_engineering",
        dst="regime_detector",
        rid="RID-test-005",
    )

    # --- Act ---
    regime_detector.handle_event(features_event)

    # --- Assert ---
    assert mock_fsm_core.emit.call_count >= 1
    emitted_event_name = mock_fsm_core.emit.call_args_list[-1][0][0]
    emitted_payload = mock_fsm_core.emit.call_args_list[-1][0][1]

    assert emitted_event_name == "EVT:REGIME_DETECTED"
    assert emitted_payload["regime"] == "LOW_VOLATILITY"
    assert emitted_payload["source_model"] == "volatility_v2"
