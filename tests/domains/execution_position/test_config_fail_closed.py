import pytest
from decimal import Decimal
from unittest.mock import MagicMock
from apps.reference.domains.execution_position.flows.open.fsm_open import OpenFlowFSM
from apps.reference.config_models import AuroraConfig, InstrumentPrecisionSpec

class TestOpenFlowFSMConfigValidation:
    """
    Tests for ARCH-02: Silent Exception Swallow in _get_instrument_specs.
    Expectation: FSM should raise ValueError/TypeError on invalid config,
    instead of silently falling back to defaults.
    """

    def test_fsm_rejects_invalid_min_qty_type(self):
        """
        Scenario: Config has min_qty as a non-numeric string (e.g. "INVALID").
        Current Behavior (Bug): Swallows exception, uses default 0.001.
        Desired Behavior (Fix): Raises ValueError/InvalidOperation.
        """
        # 1. Setup invalid config
        # detailed mocking of AuroraConfig structure
        mock_config = MagicMock(spec=AuroraConfig)
        
        # Mocking instruments dict with an object that has invalid min_qty
        bad_specs = MagicMock()
        bad_specs.min_qty = "INVALID_NUMBER" # This will cause Decimal("INVALID_NUMBER") to fail
        bad_specs.step_size = "0.001"
        bad_specs.tick_size = "0.01"
        
        mock_config.instruments = {"BTCUSDT": bad_specs}

        # Mock domains config required for __init__
        mock_domains = MagicMock()
        mock_domains.execution_position.fsm_open.idempotency_window_sec = 60.0
        mock_config.domains = mock_domains
        
        # 2. Init FSM
        fsm = OpenFlowFSM(config=mock_config, guard_enabled=True)
        
        # 3. Trigger _get_instrument_specs via handle or internal call
        # _get_instrument_specs is called inside handle(), but we can test it directly or via side-effect
        # It's better to test via public API or check internal state if we can't trigger it easily.
        # Actually, _get_instrument_specs is called inside handle().
        # Let's call the private method directly for precise testing.
        
        # EXPECTATION: Should raise InvalidOperation or ValueError
        from decimal import InvalidOperation
        with pytest.raises((ValueError, TypeError, InvalidOperation, Exception)):
             fsm._get_instrument_specs("BTCUSDT")

    def test_fsm_rejects_invalid_step_size_type(self):
        """Scenario: Config has step_size="BAD"."""
        mock_config = MagicMock(spec=AuroraConfig)
        bad_specs = MagicMock()
        bad_specs.min_qty = "0.001"
        bad_specs.step_size = "BAD_STEP"
        bad_specs.tick_size = "0.01"
        mock_config.instruments = {"BTCUSDT": bad_specs}

        # Mock domains config required for __init__
        mock_domains = MagicMock()
        mock_domains.execution_position.fsm_open.idempotency_window_sec = 60.0
        mock_config.domains = mock_domains
        
        fsm = OpenFlowFSM(config=mock_config)
        
        with pytest.raises((ValueError, TypeError, Exception)):
             fsm._get_instrument_specs("BTCUSDT")
