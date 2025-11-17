"""
Test Suite for RegimeDetector Domain

Tests the regime detection logic that analyzes market features
and identifies trading regimes (TREND_UP, TREND_DOWN, etc.)

WHY: TDD approach - define expected behavior before implementation [FSMP-PORTING-T01B]
"""

from vfoundation.core.protocol import Message
import pytest
import copy
from unittest.mock import MagicMock
from decimal import Decimal

# Direct import of regime_detector module
from apps.reference.domains.regime_detector.regime_detector import RegimeDetector


@pytest.fixture
def mock_fsm_core():
    """Provides a mock FSM core with an emit method."""
    fsm = MagicMock()
    fsm.emit = MagicMock()
    return fsm


@pytest.fixture
def mock_config():
    """Provides a mock configuration for the RegimeDetector."""
    from apps.reference.config_models import AuroraConfig, ConfigV2

    cfg = AuroraConfig()
    cfg.config_v2 = ConfigV2()
    cfg.config_v2.domains = {
        "regimes": {
            "detector": {
                "window_minutes": 2,
                "min_regime_duration_min": 15,
                "debounce_changes": True
            },
            "regimes": {
                "NORMAL": {"vol_std_bps_min": 0, "vol_std_bps_max": 100},
                "HIGH_VOLATILITY": {"vol_std_bps_min": 100, "vol_std_bps_max": 200},
                "CRISIS": {"vol_std_bps_min": 200, "vol_std_bps_max": 1000}
            },
            "hotreload": {
                "allowed": ["NORMAL", "HIGH_VOLATILITY", "CRISIS"]
            },
            "models": {
                "sma_trend": {
                    "enabled": True,
                    "fast_period": 10,
                    "slow_period": 50,
                    "confidence_multiplier": 20.0,
                    "confidence_min": 0.5,
                    "confidence_max": 0.95
                },
                "volatility": {
                    "enabled": False,  # Disabled by default for basic tests
                    "atr_period": 14,
                    "threshold_multiplier": 2.0,
                    "low_vol_multiplier": 0.5,
                    "atr_sma_length": 100,
                    "high_vol_confidence_base": 0.5,
                    "high_vol_confidence_multiplier": 2.0,
                    "low_vol_confidence_base": 0.5,
                    "low_vol_confidence_multiplier": 3.0,
                    "confidence_max": 0.95
                },
                "sideways": {
                    "enabled": True,
                    "deviation_threshold": 0.02,
                    "confidence_base": 0.5,
                    "confidence_multiplier": 100.0,
                    "confidence_max": 0.95
                }
            }
        }
    }
    return cfg


def test_detects_trend_up_regime_on_clear_signal(mock_config, mock_fsm_core):
    """
    Verify that the detector correctly identifies an uptrend when the price
    and short-term moving average are above the long-term one.

    WHY: Test core functionality - SMA crossover indicates trend direction
    """
    # --- Arrange ---
    # Initialize our (not yet existing) domain
    regime_detector = RegimeDetector(aurora_cfg=mock_config, fsm=mock_fsm_core)
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
    assert isinstance(emitted_payload["confidence"], str), (
        "Confidence should be string type to match schema"
    )
    assert emitted_payload["model"] == "sma_trend"
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
    regime_detector = RegimeDetector(aurora_cfg=mock_config, fsm=mock_fsm_core)
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
    assert emitted_payload["model"] == "sma_trend"
    assert emitted_payload["source_model"] == "sma_trend_v1"

    # Verify timestamp is present
    assert "ts" in emitted_payload
    assert isinstance(emitted_payload["ts"], int)


def test_detects_sideways_regime_when_price_is_close_to_smas(
    mock_config, mock_fsm_core
):
    """
    Verify that the detector identifies a sideways regime when the price
    is very close to both short and long-term moving averages.

    WHY: Test SIDEWAYS detection - tight price range around SMAs indicates ranging market
    Scenario: Price 3898, SMA short 3900, SMA long 3902 → tight convergence → SIDEWAYS
    """
    # --- Arrange ---
    regime_detector = RegimeDetector(aurora_cfg=mock_config, fsm=mock_fsm_core)
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
    assert emitted_payload["regime"] == "SIDEWAYS", (
        "Expected SIDEWAYS for ranging market"
    )
    assert Decimal(emitted_payload["confidence"]) > Decimal("0.8"), (
        "Confidence should be very high for tight convergence"
    )
    assert emitted_payload["model"] == "sideways"
    assert emitted_payload["source_model"] == "sideways_v1"

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
    # Enable volatility model for this test
    mock_config.config_v2.domains["regimes"]["models"]["volatility"]["enabled"] = True
    regime_detector = RegimeDetector(aurora_cfg=mock_config, fsm=mock_fsm_core)
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
    assert emitted_payload["model"] == "volatility"
    assert emitted_payload["source_model"] == "volatility_v1"


def test_detects_low_volatility_regime_on_atr_calm(mock_config, mock_fsm_core):
    """
    Verify that the detector identifies a LOW_VOLATILITY regime when the
    Average True Range (ATR) is significantly below its long-term average.

    WHY: Enable calm market detection for adaptive strategies [FSMP-PORTING-T01L]
    """
    # --- Arrange ---
    # Enable volatility model for this test
    mock_config.config_v2.domains["regimes"]["models"]["volatility"]["enabled"] = True
    regime_detector = RegimeDetector(aurora_cfg=mock_config, fsm=mock_fsm_core)
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
    assert emitted_payload["model"] == "volatility"
    assert emitted_payload["source_model"] == "volatility_v1"


def test_does_not_emit_event_for_uncertain_regime(mock_config, mock_fsm_core):
    """
    Verify that the detector does NOT emit EVT:REGIME_DETECTED events when
    all models return UNCERTAIN regime (no clear market regime detected).

    WHY: Prevent noise from uncertain signals - only emit when regime is clear [FSMP-PORTING-T01]
    """
    # --- Arrange ---
    regime_detector = RegimeDetector(aurora_cfg=mock_config, fsm=mock_fsm_core)
    regime_detector.logger = MagicMock()

    # Create event with features that don't trigger any regime detection
    # Price and SMAs are not in clear trend or sideways patterns
    features_event = Message(
        op="EVT",
        verb="FEATURES_CALCULATED",
        pld={
            "ts": 1731239000000000,
            "symbol": "ETHUSDT",
            "features": {
                "price": "4000.0",
                "sma_short": "4100.0",  # Large gap prevents sideways detection
                "sma_long": "3900.0",   # Price not above short SMA, so no TREND_UP
                # No ATR features provided, so volatility models won't trigger
            },
        },
        src="feature_engineering",
        dst="regime_detector",
        rid="RID-test-006",
    )

    # --- Act ---
    regime_detector.handle_event(features_event)

    # --- Assert ---
    # Verify that NO event was emitted for UNCERTAIN regime
    mock_fsm_core.emit.assert_not_called()

    # Verify that debug log was written about no regime detected
    regime_detector.logger.debug.assert_called_with(
        "No regime detected for ETHUSDT - all models returned UNCERTAIN"
    )


def test_model_field_unversioned_source_model_versioned(mock_config, mock_fsm_core):
    """
    Verify that the 'model' field contains unversioned model names while
    'source_model' contains versioned names for backward compatibility.

    WHY: Guard against regressions in event schema versioning [FSMP-PORTING-T01]
    """
    # --- Arrange ---
    regime_detector = RegimeDetector(aurora_cfg=mock_config, fsm=mock_fsm_core)

    features_event = Message(
        op="EVT",
        verb="FEATURES_CALCULATED",
        pld={
            "ts": 1731239000000000,
            "symbol": "ETHUSDT",
            "features": {
                "price": "4000.0",
                "sma_short": "3950.0",  # Price > sma_short triggers TREND_UP
                "sma_long": "3900.0",
            },
        },
        src="feature_engineering",
        dst="regime_detector",
        rid="RID-test-007",
    )

    # --- Act ---
    regime_detector.handle_event(features_event)

    # --- Assert ---
    mock_fsm_core.emit.assert_called_once()
    emitted_payload = mock_fsm_core.emit.call_args[0][1]

    # Primary 'model' field should be unversioned
    assert emitted_payload["model"] == "sma_trend"
    # Backward compatibility 'source_model' field should be versioned
    assert emitted_payload["source_model"] == "sma_trend_v1"
    # Both should be present
    assert "model" in emitted_payload
    assert "source_model" in emitted_payload
