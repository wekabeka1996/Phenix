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
    return fsm


@pytest.fixture
def mock_config():
    """Provides a mock configuration for the RegimeDetector."""
    return {
        "models": {
            "sma_trend": {"enabled": True, "short_period": 10, "long_period": 50}
        }
    }


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
    assert emitted_payload["source_model"] == "sma_trend_v1"

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
    # Додамо конфігурацію для моделі волатильності
    mock_config["models"]["volatility"] = {
        "enabled": True,
        "atr_period": 14,
        "threshold_multiplier": 2.0,  # Вважаємо високою волатильністю, якщо ATR > 2 * SMA(ATR)
    }
    regime_detector = RegimeDetector(config=mock_config, fsm=mock_fsm_core)
    regime_detector.logger = MagicMock()

    # Створюємо подію, що вказує на сплеск волатильності
    features_event = Message(
        op="EVT",
        verb="FEATURES_CALCULATED",
        pld={
            "ts": 1731237000000000,
            "symbol": "ETHUSDT",
            "features": {
                "price": "4000.0",
                "sma_short": "4001.0",  # Ціни близькі, тренду немає
                "sma_long": "4002.0",
                "atr_14": "150.0",  # Поточний ATR
                "atr_14_sma_100": "70.0",  # Середній ATR за довгий період
            },
        },
        src="feature_engineering",
        dst="regime_detector",
        rid="RID-test-004",
    )

    # --- Act ---
    regime_detector.handle_event(features_event)

    # --- Assert ---
    mock_fsm_core.emit.assert_called_once()

    emitted_event_name = mock_fsm_core.emit.call_args[0][0]
    emitted_payload = mock_fsm_core.emit.call_args[0][1]

    assert emitted_event_name == "EVT:REGIME_DETECTED"
    assert emitted_payload["regime"] == "HIGH_VOLATILITY"
    assert Decimal(emitted_payload["confidence"]) > Decimal("0.7")
    assert emitted_payload["source_model"] == "volatility_v1"


def test_detects_low_volatility_regime_on_atr_calm(mock_config, mock_fsm_core):
    """
    Verify that the detector identifies a LOW_VOLATILITY regime when the
    Average True Range (ATR) is significantly below its long-term average.

    WHY: Enable calm market detection for adaptive strategies [FSMP-PORTING-T01L]
    """
    # --- Arrange ---
    # Використовуємо ту ж конфігурацію, що й для HIGH_VOLATILITY
    mock_config["models"]["volatility"] = {
        "enabled": True,
        "atr_period": 14,
        "threshold_multiplier": "2.0",
        "low_vol_multiplier": "0.5",  # Вважаємо низькою волатильністю, якщо ATR < 0.5 * SMA(ATR)
    }
    regime_detector = RegimeDetector(config=mock_config, fsm=mock_fsm_core)
    regime_detector.logger = MagicMock()

    # Створюємо подію, що вказує на низьку волатильність
    features_event = Message(
        op="EVT",
        verb="FEATURES_CALCULATED",
        pld={
            "ts": 1731238000000000,
            "symbol": "ETHUSDT",
            "features": {
                "price": "4000.0",
                "sma_short": "4001.0",
                "sma_long": "4002.0",
                "atr_14": "30.0",  # Поточний ATR дуже низький
                "atr_14_sma_100": "70.0",  # Середній ATR значно вищий
            },
        },
        src="feature_engineering",
        dst="regime_detector",
        rid="RID-test-005",
    )

    # --- Act ---
    regime_detector.handle_event(features_event)

    # --- Assert ---
    mock_fsm_core.emit.assert_called_once()

    emitted_event_name = mock_fsm_core.emit.call_args[0][0]
    emitted_payload = mock_fsm_core.emit.call_args[0][1]

    assert emitted_event_name == "EVT:REGIME_DETECTED"
    assert emitted_payload["regime"] == "LOW_VOLATILITY"
    assert Decimal(emitted_payload["confidence"]) > Decimal("0.7")
    assert emitted_payload["source_model"] == "volatility_v1"
