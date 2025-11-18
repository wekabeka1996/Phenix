"""
Test Suite for RegimeDetector Domain

Tests the regime detection logic that analyzes market features
and identifies trading regimes (TREND_UP, TREND_DOWN, etc.)

WHY: TDD approach - define expected behavior before implementation [FSMP-PORTING-T01B]
"""

from apps.reference.domains.regime_detector.config import (
    SmaTrendConfig,
    VolatilityConfig,
    SidewaysConfig,
    RegimeModels,
    RegimeDetectorConfig,
)
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


# Tests for config.py coverage


def test_sma_trend_config_defaults():
    """Test SmaTrendConfig uses correct defaults."""
    config = SmaTrendConfig()
    assert config.enabled is True
    assert config.fast_period == 5
    assert config.slow_period == 20
    assert config.threshold == 0.001
    assert config.confidence_multiplier == 20.0
    assert config.confidence_min == 0.5
    assert config.confidence_max == 0.95


def test_sma_trend_config_custom():
    """Test SmaTrendConfig accepts custom values."""
    config = SmaTrendConfig(
        enabled=False,
        fast_period=10,
        slow_period=50,
        threshold=0.002,
        confidence_multiplier=25.0,
        confidence_min=0.3,
        confidence_max=0.9
    )
    assert config.enabled is False
    assert config.fast_period == 10
    assert config.slow_period == 50
    assert config.threshold == 0.002
    assert config.confidence_multiplier == 25.0
    assert config.confidence_min == 0.3
    assert config.confidence_max == 0.9


def test_sma_trend_config_validation_fast_period_zero():
    """Test SmaTrendConfig validation for fast_period <= 0."""
    with pytest.raises(ValueError, match="fast_period must be > 0"):
        SmaTrendConfig(fast_period=0)


def test_sma_trend_config_validation_slow_period_zero():
    """Test SmaTrendConfig validation for slow_period <= 0."""
    with pytest.raises(ValueError, match="slow_period must be > 0"):
        SmaTrendConfig(slow_period=0)


def test_sma_trend_config_validation_fast_greater_equal_slow():
    """Test SmaTrendConfig validation for fast_period >= slow_period."""
    with pytest.raises(ValueError, match="fast_period .* must be < slow_period"):
        SmaTrendConfig(fast_period=20, slow_period=10)


def test_sma_trend_config_validation_threshold_zero():
    """Test SmaTrendConfig validation for threshold <= 0."""
    with pytest.raises(ValueError, match="threshold must be > 0"):
        SmaTrendConfig(threshold=0)


def test_sma_trend_config_validation_confidence_multiplier_zero():
    """Test SmaTrendConfig validation for confidence_multiplier <= 0."""
    with pytest.raises(ValueError, match="confidence_multiplier must be > 0"):
        SmaTrendConfig(confidence_multiplier=0)


def test_sma_trend_config_validation_confidence_min_out_of_range():
    """Test SmaTrendConfig validation for confidence_min out of [0,1]."""
    with pytest.raises(ValueError, match="confidence_min must be in \\[0, 1\\]"):
        SmaTrendConfig(confidence_min=-0.1)

    with pytest.raises(ValueError, match="confidence_min must be in \\[0, 1\\]"):
        SmaTrendConfig(confidence_min=1.5)


def test_sma_trend_config_validation_confidence_max_out_of_range():
    """Test SmaTrendConfig validation for confidence_max out of [0,1]."""
    with pytest.raises(ValueError, match="confidence_max must be in \\[0, 1\\]"):
        SmaTrendConfig(confidence_max=-0.1)

    with pytest.raises(ValueError, match="confidence_max must be in \\[0, 1\\]"):
        SmaTrendConfig(confidence_max=1.5)


def test_sma_trend_config_validation_confidence_min_greater_equal_max():
    """Test SmaTrendConfig validation for confidence_min >= confidence_max."""
    with pytest.raises(ValueError, match="confidence_min .* must be < confidence_max"):
        SmaTrendConfig(confidence_min=0.8, confidence_max=0.7)


def test_volatility_config_defaults():
    """Test VolatilityConfig uses correct defaults."""
    config = VolatilityConfig()
    assert config.enabled is True
    assert config.atr_period == 14
    assert config.threshold_multiplier == 2.0
    assert config.low_vol_multiplier == 0.5
    assert config.atr_sma_length == 100
    assert config.high_vol_confidence_base == 0.5
    assert config.high_vol_confidence_multiplier == 2.0
    assert config.low_vol_confidence_base == 0.5
    assert config.low_vol_confidence_multiplier == 3.0
    assert config.confidence_max == 0.95


def test_volatility_config_custom():
    """Test VolatilityConfig accepts custom values."""
    config = VolatilityConfig(
        enabled=False,
        atr_period=20,
        threshold_multiplier=3.0,
        low_vol_multiplier=0.3,
        atr_sma_length=200,
        high_vol_confidence_base=0.6,
        high_vol_confidence_multiplier=2.5,
        low_vol_confidence_base=0.4,
        low_vol_confidence_multiplier=4.0,
        confidence_max=0.9
    )
    assert config.enabled is False
    assert config.atr_period == 20
    assert config.threshold_multiplier == 3.0
    assert config.low_vol_multiplier == 0.3
    assert config.atr_sma_length == 200
    assert config.high_vol_confidence_base == 0.6
    assert config.high_vol_confidence_multiplier == 2.5
    assert config.low_vol_confidence_base == 0.4
    assert config.low_vol_confidence_multiplier == 4.0
    assert config.confidence_max == 0.9


def test_volatility_config_validation_atr_period_zero():
    """Test VolatilityConfig validation for atr_period <= 0."""
    with pytest.raises(ValueError, match="atr_period must be > 0"):
        VolatilityConfig(atr_period=0)


def test_volatility_config_validation_threshold_multiplier_too_low():
    """Test VolatilityConfig validation for threshold_multiplier <= 1.0."""
    with pytest.raises(ValueError, match="threshold_multiplier must be > 1.0"):
        VolatilityConfig(threshold_multiplier=1.0)


def test_volatility_config_validation_low_vol_multiplier_too_high():
    """Test VolatilityConfig validation for low_vol_multiplier >= 1.0."""
    with pytest.raises(ValueError, match="low_vol_multiplier must be < 1.0"):
        VolatilityConfig(low_vol_multiplier=1.0)


def test_volatility_config_validation_atr_sma_length_zero():
    """Test VolatilityConfig validation for atr_sma_length <= 0."""
    with pytest.raises(ValueError, match="atr_sma_length must be > 0"):
        VolatilityConfig(atr_sma_length=0)


def test_volatility_config_validation_confidence_base_out_of_range():
    """Test VolatilityConfig validation for confidence base values out of [0,1]."""
    with pytest.raises(ValueError, match="high_vol_confidence_base must be in \\[0, 1\\]"):
        VolatilityConfig(high_vol_confidence_base=-0.1)

    with pytest.raises(ValueError, match="low_vol_confidence_base must be in \\[0, 1\\]"):
        VolatilityConfig(low_vol_confidence_base=1.5)


def test_volatility_config_validation_confidence_multiplier_zero():
    """Test VolatilityConfig validation for confidence multiplier <= 0."""
    with pytest.raises(ValueError, match="high_vol_confidence_multiplier must be > 0"):
        VolatilityConfig(high_vol_confidence_multiplier=0)

    with pytest.raises(ValueError, match="low_vol_confidence_multiplier must be > 0"):
        VolatilityConfig(low_vol_confidence_multiplier=0)


def test_volatility_config_validation_confidence_max_out_of_range():
    """Test VolatilityConfig validation for confidence_max out of [0,1]."""
    with pytest.raises(ValueError, match="confidence_max must be in \\[0, 1\\]"):
        VolatilityConfig(confidence_max=1.5)


def test_sideways_config_defaults():
    """Test SidewaysConfig uses correct defaults."""
    config = SidewaysConfig()
    assert config.enabled is True
    assert config.sma_period == 50
    assert config.deviation_threshold == 0.02
    assert config.confidence_base == 0.5
    assert config.confidence_multiplier == 100.0
    assert config.confidence_max == 0.95


def test_sideways_config_custom():
    """Test SidewaysConfig accepts custom values."""
    config = SidewaysConfig(
        enabled=False,
        sma_period=100,
        deviation_threshold=0.05,
        confidence_base=0.6,
        confidence_multiplier=150.0,
        confidence_max=0.9
    )
    assert config.enabled is False
    assert config.sma_period == 100
    assert config.deviation_threshold == 0.05
    assert config.confidence_base == 0.6
    assert config.confidence_multiplier == 150.0
    assert config.confidence_max == 0.9


def test_sideways_config_validation_sma_period_zero():
    """Test SidewaysConfig validation for sma_period <= 0."""
    with pytest.raises(ValueError, match="sma_period must be > 0"):
        SidewaysConfig(sma_period=0)


def test_sideways_config_validation_deviation_threshold_zero():
    """Test SidewaysConfig validation for deviation_threshold <= 0."""
    with pytest.raises(ValueError, match="deviation_threshold must be > 0"):
        SidewaysConfig(deviation_threshold=0)


def test_sideways_config_validation_confidence_base_out_of_range():
    """Test SidewaysConfig validation for confidence_base out of [0,1]."""
    with pytest.raises(ValueError, match="confidence_base must be in \\[0, 1\\]"):
        SidewaysConfig(confidence_base=-0.1)

    with pytest.raises(ValueError, match="confidence_base must be in \\[0, 1\\]"):
        SidewaysConfig(confidence_base=1.5)


def test_sideways_config_validation_confidence_multiplier_zero():
    """Test SidewaysConfig validation for confidence_multiplier <= 0."""
    with pytest.raises(ValueError, match="confidence_multiplier must be > 0"):
        SidewaysConfig(confidence_multiplier=0)


def test_sideways_config_validation_confidence_max_out_of_range():
    """Test SidewaysConfig validation for confidence_max out of [0,1]."""
    with pytest.raises(ValueError, match="confidence_max must be in \\[0, 1\\]"):
        SidewaysConfig(confidence_max=1.5)


def test_regime_models_defaults():
    """Test RegimeModels uses correct defaults."""
    models = RegimeModels()
    assert isinstance(models.sma_trend, SmaTrendConfig)
    assert isinstance(models.volatility, VolatilityConfig)
    assert isinstance(models.sideways, SidewaysConfig)


def test_regime_detector_config_defaults():
    """Test RegimeDetectorConfig uses correct defaults."""
    config = RegimeDetectorConfig()
    assert isinstance(config.models, RegimeModels)
    assert config.max_period == 100


def test_regime_detector_config_custom():
    """Test RegimeDetectorConfig accepts custom values."""
    custom_models = RegimeModels()
    custom_models.sma_trend.fast_period = 15
    config = RegimeDetectorConfig(models=custom_models, max_period=200)
    assert config.models.sma_trend.fast_period == 15
    assert config.max_period == 200


def test_regime_detector_config_validation_max_period_zero():
    """Test RegimeDetectorConfig validation for max_period <= 0."""
    with pytest.raises(ValueError, match="max_period must be > 0"):
        RegimeDetectorConfig(max_period=0)


def test_regime_detector_config_from_dict_empty():
    """Test RegimeDetectorConfig.from_dict with empty dict."""
    config = RegimeDetectorConfig.from_dict({})
    assert config.max_period == 100
    assert config.models.sma_trend.fast_period == 5
    assert config.models.sma_trend.slow_period == 20


def test_regime_detector_config_from_dict_full():
    """Test RegimeDetectorConfig.from_dict with full config."""
    config_dict = {
        "models": {
            "sma_trend": {
                "enabled": False,
                "fast_period": 10,
                "slow_period": 40,
                "threshold": 0.002,
                "confidence_multiplier": 25.0,
                "confidence_min": 0.4,
                "confidence_max": 0.9
            },
            "volatility": {
                "enabled": True,
                "atr_period": 20,
                "threshold_multiplier": 3.0,
                "low_vol_multiplier": 0.4,
                "atr_sma_length": 150,
                "high_vol_confidence_base": 0.6,
                "high_vol_confidence_multiplier": 2.5,
                "low_vol_confidence_base": 0.4,
                "low_vol_confidence_multiplier": 3.5,
                "confidence_max": 0.9
            },
            "sideways": {
                "enabled": True,
                "sma_period": 75,
                "deviation_threshold": 0.03,
                "confidence_base": 0.6,
                "confidence_multiplier": 120.0,
                "confidence_max": 0.9
            }
        },
        "max_period": 150
    }

    config = RegimeDetectorConfig.from_dict(config_dict)

    # Check sma_trend
    assert config.models.sma_trend.enabled is False
    assert config.models.sma_trend.fast_period == 10
    assert config.models.sma_trend.slow_period == 40
    assert config.models.sma_trend.threshold == 0.002
    assert config.models.sma_trend.confidence_multiplier == 25.0
    assert config.models.sma_trend.confidence_min == 0.4
    assert config.models.sma_trend.confidence_max == 0.9

    # Check volatility
    assert config.models.volatility.enabled is True
    assert config.models.volatility.atr_period == 20
    assert config.models.volatility.threshold_multiplier == 3.0
    assert config.models.volatility.low_vol_multiplier == 0.4
    assert config.models.volatility.atr_sma_length == 150
    assert config.models.volatility.high_vol_confidence_base == 0.6
    assert config.models.volatility.high_vol_confidence_multiplier == 2.5
    assert config.models.volatility.low_vol_confidence_base == 0.4
    assert config.models.volatility.low_vol_confidence_multiplier == 3.5
    assert config.models.volatility.confidence_max == 0.9

    # Check sideways
    assert config.models.sideways.enabled is True
    assert config.models.sideways.sma_period == 75
    assert config.models.sideways.deviation_threshold == 0.03
    assert config.models.sideways.confidence_base == 0.6
    assert config.models.sideways.confidence_multiplier == 120.0
    assert config.models.sideways.confidence_max == 0.9

    # Check max_period
    assert config.max_period == 150


def test_regime_detector_config_from_dict_legacy_sma_params():
    """Test RegimeDetectorConfig.from_dict with legacy SMA parameters."""
    import warnings

    config_dict = {
        "sma_short_period": 12,
        "sma_long_period": 48
    }

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        config = RegimeDetectorConfig.from_dict(config_dict)

        # Check that warning was issued
        assert len(w) == 1
        assert issubclass(w[0].category, DeprecationWarning)
        assert "deprecated config parameters" in str(w[0].message)

    # Check that legacy params were used
    assert config.models.sma_trend.fast_period == 12
    assert config.models.sma_trend.slow_period == 48


def test_regime_detector_config_from_dict_legacy_mean_reversion():
    """Test RegimeDetectorConfig.from_dict with legacy mean_reversion section."""
    import warnings

    config_dict = {
        "models": {
            "mean_reversion": {
                "sma_period": 60,
                "threshold": 0.025
            }
        }
    }

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        config = RegimeDetectorConfig.from_dict(config_dict)

        # Check that warning was issued
        assert len(w) == 1
        assert issubclass(w[0].category, DeprecationWarning)
        assert "deprecated config section 'mean_reversion'" in str(
            w[0].message)

    # Check that legacy params were mapped to sideways
    assert config.models.sideways.sma_period == 60
    assert config.models.sideways.deviation_threshold == 0.025


def test_regime_detector_config_from_object():
    """Test RegimeDetectorConfig.from_object with object config."""
    from types import SimpleNamespace

    config_obj = SimpleNamespace()
    config_obj.models = SimpleNamespace()
    config_obj.models.sma_trend = SimpleNamespace(
        enabled=False, fast_period=15, slow_period=60, threshold=0.003,
        confidence_multiplier=30.0, confidence_min=0.4, confidence_max=0.9
    )
    config_obj.models.volatility = SimpleNamespace(
        enabled=True, atr_period=25, threshold_multiplier=2.5,
        low_vol_multiplier=0.6, atr_sma_length=120,
        high_vol_confidence_base=0.7, high_vol_confidence_multiplier=2.2,
        low_vol_confidence_base=0.5, low_vol_confidence_multiplier=3.2,
        confidence_max=0.9
    )
    config_obj.models.sideways = SimpleNamespace(
        enabled=True, sma_period=80, deviation_threshold=0.04,
        confidence_base=0.7, confidence_multiplier=110.0, confidence_max=0.9
    )
    config_obj.max_period = 180

    config = RegimeDetectorConfig.from_object(config_obj)

    # Check sma_trend
    assert config.models.sma_trend.enabled is False
    assert config.models.sma_trend.fast_period == 15
    assert config.models.sma_trend.slow_period == 60
    assert config.models.sma_trend.threshold == 0.003
    assert config.models.sma_trend.confidence_multiplier == 30.0
    assert config.models.sma_trend.confidence_min == 0.4
    assert config.models.sma_trend.confidence_max == 0.9

    # Check volatility
    assert config.models.volatility.enabled is True
    assert config.models.volatility.atr_period == 25
    assert config.models.volatility.threshold_multiplier == 2.5
    assert config.models.volatility.low_vol_multiplier == 0.6
    assert config.models.volatility.atr_sma_length == 120
    assert config.models.volatility.high_vol_confidence_base == 0.7
    assert config.models.volatility.high_vol_confidence_multiplier == 2.2
    assert config.models.volatility.low_vol_confidence_base == 0.5
    assert config.models.volatility.low_vol_confidence_multiplier == 3.2
    assert config.models.volatility.confidence_max == 0.9

    # Check sideways
    assert config.models.sideways.enabled is True
    assert config.models.sideways.sma_period == 80
    assert config.models.sideways.deviation_threshold == 0.04
    assert config.models.sideways.confidence_base == 0.7
    assert config.models.sideways.confidence_multiplier == 110.0
    assert config.models.sideways.confidence_max == 0.9

    # Check max_period
    assert config.max_period == 180


def test_regime_detector_config_from_object_legacy_mean_reversion():
    """Test RegimeDetectorConfig.from_object with legacy mean_reversion."""
    import warnings
    from types import SimpleNamespace

    config_obj = SimpleNamespace()
    config_obj.models = SimpleNamespace()
    config_obj.models.mean_reversion = SimpleNamespace(
        sma_period=70, threshold=0.035
    )

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        config = RegimeDetectorConfig.from_object(config_obj)

        # Check that warning was issued
        assert len(w) == 1
        assert issubclass(w[0].category, DeprecationWarning)
        assert "deprecated config section 'mean_reversion'" in str(
            w[0].message)

    # Check that legacy params were mapped to sideways
    assert config.models.sideways.sma_period == 70
    assert config.models.sideways.deviation_threshold == 0.035
