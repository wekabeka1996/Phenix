"""
CFG-STRATEGIES-SSOT-02-MR-HANDLER-STRICT-CONTRACT: MR Handler Strict Tests

Tests verify:
1. MR assigned but config missing → ValueError (strict fail-closed)
2. MR not assigned and config missing → handler disabled (no noise)
3. Missing position_size_usd → signal blocked (no default=100)
4. Handler only accepts typed Pydantic (no dict-fallback)
"""
import pytest
from unittest.mock import Mock, MagicMock
from decimal import Decimal

# Mock dependencies before import
import sys
sys.modules['apps.reference.telemetry.order_logger'] = MagicMock()

from apps.reference.domains.decision_making.mean_reversion_handler import MeanReversionHandler
from apps.reference.config_models import (
    AuroraConfig,
    MeanReversion1mStrategyConfig,
    MRStrategyParamsConfig,
    MRAssetConfig,
    MRRiskConfig,
    StrategiesRegistryConfig,
    StrategiesArbitrationConfig,
    StrategiesArbitrationLoggingConfig,
)


@pytest.fixture
def mock_fsm():
    """Create mock FSMCore."""
    fsm = Mock()
    fsm.emit = Mock()
    fsm.logger = Mock()
    return fsm


@pytest.fixture
def mock_decision_making():
    """Create mock DecisionMaking instance."""
    dm = Mock()
    dm.logger = Mock()
    return dm


@pytest.fixture
def strategies_registry_with_mr():
    """Create strategies_registry with MR assigned to DOGEUSDT."""
    return StrategiesRegistryConfig(
        version="1.0.0",
        assignments={
            "ETHUSDT": ["aurora"],
            "DOGEUSDT": ["mean_reversion_1m"],  # MR assigned
        },
        arbitration=StrategiesArbitrationConfig(
            mode="priority",
            priority={"aurora": 1, "mean_reversion_1m": 2},
            logging=StrategiesArbitrationLoggingConfig(
                rejected_why_prefix="ARBITRATION_REJECT",
                log_level="INFO"
            )
        )
    )


@pytest.fixture
def strategies_registry_without_mr():
    """Create strategies_registry with NO MR assignments."""
    return StrategiesRegistryConfig(
        version="1.0.0",
        assignments={
            "ETHUSDT": ["aurora"],
            "SOLUSDT": ["aurora"],
        },
        arbitration=StrategiesArbitrationConfig(
            mode="priority",
            priority={"aurora": 1},
            logging=StrategiesArbitrationLoggingConfig(
                rejected_why_prefix="ARBITRATION_REJECT",
                log_level="INFO"
            )
        )
    )


@pytest.fixture
def valid_mr_config():
    """Create valid MR config."""
    return MeanReversion1mStrategyConfig(
        enabled=True,
        timeframe_sec=60,
        strategy=MRStrategyParamsConfig(
            bb_window=20,
            bb_num_std=2.0,
            atr_window=14,
            rsi_window=14,
            min_bars=20,
            min_bb_width=0.001,
            max_bb_width=0.1,
            entry_threshold=0.8,
            rsi_oversold=30,
            rsi_overbought=70,
            sl_atr_mult=1.5,
            tp_to_mid=True,
            cooldown_sec=300
        ),
        assets={
            "DOGEUSDT": MRAssetConfig(
                enabled=True,
                sl_pct=0.02,
                strategy=None
            )
        },
        risk=MRRiskConfig(
            position_size_usd=50.0
        ),
        allowed_regimes=["TREND_UP", "TREND_DOWN"]
    )


def test_mr_assigned_but_config_missing_raises_error(
    mock_fsm, mock_decision_making, strategies_registry_with_mr
):
    """Test A: MR assigned in registry but config missing → ValueError (strict fail-closed)."""
    config = Mock(spec=AuroraConfig)
    config.strategies_registry = strategies_registry_with_mr
    config.mean_reversion_1m = None  # Missing MR config
    
    with pytest.raises(ValueError) as exc_info:
        MeanReversionHandler(
            fsm=mock_fsm,
            config=config,
            decision_making=mock_decision_making
        )
    
    error_msg = str(exc_info.value)
    assert "mean_reversion_1m assigned" in error_msg.lower(), \
        "Error should mention MR assigned to symbols"
    assert "dogeusdt" in error_msg.lower(), \
        "Error should mention specific symbol (DOGEUSDT)"
    assert "missing or invalid" in error_msg.lower(), \
        "Error should mention config missing"


def test_mr_not_assigned_and_config_missing_disabled_no_noise(
    mock_fsm, mock_decision_making, strategies_registry_without_mr
):
    """Test B: MR not assigned and config missing → handler disabled (no noise)."""
    config = Mock(spec=AuroraConfig)
    config.strategies_registry = strategies_registry_without_mr
    config.mean_reversion_1m = None  # Missing MR config
    
    # Should NOT raise error (fail-closed but silent)
    handler = MeanReversionHandler(
        fsm=mock_fsm,
        config=config,
        decision_making=mock_decision_making
    )
    
    # Verify handler is disabled
    assert handler.enabled is False, "Handler should be disabled"
    assert not handler._enabled_symbols, "No symbols should be enabled"
    assert not handler._strategies, "No strategies should be initialized"


def test_mr_assigned_with_valid_config_initializes(
    mock_fsm, mock_decision_making, strategies_registry_with_mr, valid_mr_config
):
    """Test C: MR assigned + valid config → handler initializes successfully."""
    config = Mock(spec=AuroraConfig)
    config.strategies_registry = strategies_registry_with_mr
    config.mean_reversion_1m = valid_mr_config
    
    handler = MeanReversionHandler(
        fsm=mock_fsm,
        config=config,
        decision_making=mock_decision_making
    )
    
    assert handler.enabled is True, "Handler should be enabled"
    assert "DOGEUSDT" in handler._enabled_symbols, "DOGEUSDT should be enabled"
    assert "DOGEUSDT" in handler._strategies, "DOGEUSDT strategy should be initialized"


def test_missing_position_size_blocks_signal(
    mock_fsm, mock_decision_making, strategies_registry_with_mr, valid_mr_config
):
    """Test D: Missing position_size_usd → signal blocked (no default=100)."""
    # Use valid config but mock _get_position_size_usd to return None
    config = Mock(spec=AuroraConfig)
    config.strategies_registry = strategies_registry_with_mr
    config.mean_reversion_1m = valid_mr_config
    
    handler = MeanReversionHandler(
        fsm=mock_fsm,
        config=config,
        decision_making=mock_decision_making
    )
    
    # Mock _get_position_size_usd to return None (simulating missing config)
    original_method = handler._get_position_size_usd
    handler._get_position_size_usd = Mock(return_value=None)
    
    # Create mock MR signal
    mock_signal = Mock()
    mock_signal.symbol = "DOGEUSDT"
    mock_signal.is_signal = True
    mock_signal.signal_type = Mock(name="ENTRY_LONG")
    mock_signal.side = "BUY"
    mock_signal.entry_price = Decimal("0.10")
    mock_signal.stop_price = Decimal("0.095")
    mock_signal.target_price = Decimal("0.105")
    mock_signal.confidence = 0.8
    mock_signal.timestamp_ms = 1600000000000
    mock_signal.why = "BB_reversal"
    mock_signal.flat_regime = Mock(name="TREND_DOWN")
    mock_signal.mr_params = Mock(sizing_mult=1.0, stop_mult=1.0, target_mult=1.0)
    
    # Call _handle_signal (should block due to missing position_size)
    handler._handle_signal(mock_signal)
    
    # Verify NO event emitted (blocked)
    mock_fsm.emit.assert_not_called()
    
    # Verify method was called
    handler._get_position_size_usd.assert_called_once_with("DOGEUSDT")


def test_valid_position_size_allows_signal(
    mock_fsm, mock_decision_making, strategies_registry_with_mr, valid_mr_config
):
    """Test E: Valid position_size_usd → signal emitted successfully."""
    config = Mock(spec=AuroraConfig)
    config.strategies_registry = strategies_registry_with_mr
    config.mean_reversion_1m = valid_mr_config
    
    handler = MeanReversionHandler(
        fsm=mock_fsm,
        config=config,
        decision_making=mock_decision_making
    )
    
    # Create mock MR signal
    mock_signal = Mock()
    mock_signal.symbol = "DOGEUSDT"
    mock_signal.is_signal = True
    mock_signal.signal_type = Mock(name="ENTRY_LONG")
    mock_signal.side = "BUY"
    mock_signal.entry_price = Decimal("0.10")
    mock_signal.stop_price = Decimal("0.095")
    mock_signal.target_price = Decimal("0.105")
    mock_signal.confidence = 0.8
    mock_signal.timestamp_ms = 1600000000000
    mock_signal.why = "BB_reversal"
    mock_signal.flat_regime = Mock(name="TREND_DOWN")
    mock_signal.mr_params = Mock(sizing_mult=1.0, stop_mult=1.0, target_mult=1.0)
    
    # Call _handle_signal (should succeed)
    handler._handle_signal(mock_signal)
    
    # Verify event emitted
    mock_fsm.emit.assert_called_once()
    call_args = mock_fsm.emit.call_args
    assert call_args[0][0] == "EVT:TRADE_INTENT_PROPOSED"
    payload = call_args[1]["payload"]
    assert payload["symbol"] == "DOGEUSDT"
    assert Decimal(payload["position_size_usd"]) == Decimal("50.0")  # From config


def test_no_dict_fallback_accepted():
    """Test F: Handler does NOT accept dict config (only typed Pydantic)."""
    # This test verifies that dict-fallback code path is removed
    # by trying to pass dict config and expecting it to fail
    
    mock_fsm = Mock()
    mock_dm = Mock()
    
    # Pass dict config (should be ignored, handler disabled)
    dict_config = {
        "mean_reversion_1m": {
            "enabled": True,
            "timeframe_sec": 60,
            # ... other dict fields
        }
    }
    
    # Handler should NOT use dict (no strategies_registry → disabled)
    handler = MeanReversionHandler(
        fsm=mock_fsm,
        config=dict_config,
        decision_making=mock_dm
    )
    
    assert handler.enabled is False, \
        "Handler should be disabled when receiving dict (no typed Pydantic access)"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
