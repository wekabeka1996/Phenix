"""
Tests for per-symbol flip orchestration configuration.

Verifies:
1. Per-symbol flip.enabled override from instruments.yaml
2. Per-symbol hysteresis_mult override  
3. Fallback to global config when no per-symbol config
4. Pydantic validation rejects invalid values
"""
import pytest
from decimal import Decimal
from unittest.mock import MagicMock, patch
from pydantic import ValidationError

from apps.reference.config_models import (
    FlipOrchestrationConfig,
    InstrumentPrecisionSpec,
    InstrumentExecutionConfig,
    InstrumentSizingConfig,
)


class TestFlipOrchestrationConfig:
    """Pydantic validation tests for FlipOrchestrationConfig."""

    def test_default_values(self):
        """Default: enabled=True, hysteresis_mult=1.0."""
        cfg = FlipOrchestrationConfig()
        assert cfg.enabled is True
        assert cfg.hysteresis_mult == 1.0

    def test_valid_config(self):
        """Valid config with custom values."""
        cfg = FlipOrchestrationConfig(enabled=False, hysteresis_mult=1.5)
        assert cfg.enabled is False
        assert cfg.hysteresis_mult == 1.5

    def test_hysteresis_mult_below_1_rejected(self):
        """hysteresis_mult < 1.0 should raise ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            FlipOrchestrationConfig(hysteresis_mult=0.5)
        assert "hysteresis_mult" in str(exc_info.value)

    def test_extra_keys_rejected(self):
        """Unknown keys should raise ValidationError (extra='forbid')."""
        with pytest.raises(ValidationError):
            FlipOrchestrationConfig(enabled=True, unknown_key=123)


class TestInstrumentPrecisionSpecFlip:
    """Tests for flip field in InstrumentPrecisionSpec."""

    @pytest.fixture
    def base_instrument_data(self):
        """Base valid instrument data without flip."""
        return {
            "symbol": "TESTUSDT",
            "tick_size": "0.01",
            "step_size": "0.001",
            "min_qty": "0.001",
            "min_notional": "5",
            "execution": {
                "margin_mode": "isolated",
                "target_leverage": 20,
                "leverage_policy": "set_and_verify",
                "max_notional_utilization": 0.8,
            },
            "sizing": {"margin_pct": 0.1},
        }

    def test_flip_optional_none(self, base_instrument_data):
        """flip field is optional and defaults to None."""
        spec = InstrumentPrecisionSpec(**base_instrument_data)
        assert spec.flip is None

    def test_flip_with_valid_config(self, base_instrument_data):
        """flip field accepts valid FlipOrchestrationConfig."""
        base_instrument_data["flip"] = {
            "enabled": False,
            "hysteresis_mult": 2.0,
        }
        spec = InstrumentPrecisionSpec(**base_instrument_data)
        assert spec.flip is not None
        assert spec.flip.enabled is False
        assert spec.flip.hysteresis_mult == 2.0

    def test_flip_enabled_only(self, base_instrument_data):
        """flip with only enabled field (hysteresis_mult defaults to 1.0)."""
        base_instrument_data["flip"] = {"enabled": False}
        spec = InstrumentPrecisionSpec(**base_instrument_data)
        assert spec.flip.enabled is False
        assert spec.flip.hysteresis_mult == 1.0


class TestDecisionMakingGetFlipConfig:
    """Integration tests for _get_flip_config getter."""

    @pytest.fixture
    def mock_dm(self):
        """Create a mock DecisionMaking instance."""
        dm = MagicMock()
        dm.flip_hysteresis_enabled = True
        dm.flip_hysteresis_mult = 1.3
        dm.config = MagicMock()
        return dm

    def test_fallback_to_global_when_no_instrument(self, mock_dm):
        """When symbol not in instruments, use global fallback."""
        from apps.reference.domains.decision_making.decision_making import DecisionMaking
        
        mock_dm.config.instruments.get.return_value = None
        
        # Call the actual method bound to mock
        result = DecisionMaking._get_flip_config(mock_dm, "UNKNOWNUSDT")
        
        assert result == (True, 1.3)

    def test_fallback_to_global_when_flip_is_none(self, mock_dm):
        """When instrument has no flip config, use global fallback."""
        from apps.reference.domains.decision_making.decision_making import DecisionMaking
        
        instr = MagicMock()
        instr.flip = None
        mock_dm.config.instruments.get.return_value = instr
        
        result = DecisionMaking._get_flip_config(mock_dm, "BTCUSDT")
        
        assert result == (True, 1.3)

    def test_per_symbol_override_disabled(self, mock_dm):
        """Per-symbol flip.enabled=False overrides global."""
        from apps.reference.domains.decision_making.decision_making import DecisionMaking
        
        flip_cfg = MagicMock()
        flip_cfg.enabled = False
        flip_cfg.hysteresis_mult = 1.0
        
        instr = MagicMock()
        instr.flip = flip_cfg
        mock_dm.config.instruments.get.return_value = instr
        
        result = DecisionMaking._get_flip_config(mock_dm, "DOGEUSDT")
        
        assert result == (False, 1.0)

    def test_per_symbol_hysteresis_mult_override(self, mock_dm):
        """Per-symbol hysteresis_mult overrides global."""
        from apps.reference.domains.decision_making.decision_making import DecisionMaking
        
        flip_cfg = MagicMock()
        flip_cfg.enabled = True
        flip_cfg.hysteresis_mult = 2.5
        
        instr = MagicMock()
        instr.flip = flip_cfg
        mock_dm.config.instruments.get.return_value = instr
        
        result = DecisionMaking._get_flip_config(mock_dm, "ETHUSDT")
        
        assert result == (True, 2.5)

    def test_hysteresis_mult_floor_at_1(self, mock_dm):
        """hysteresis_mult is floored at 1.0 even if config has lower value."""
        from apps.reference.domains.decision_making.decision_making import DecisionMaking
        
        flip_cfg = MagicMock()
        flip_cfg.enabled = True
        flip_cfg.hysteresis_mult = 0.5  # Invalid but somehow passed
        
        instr = MagicMock()
        instr.flip = flip_cfg
        mock_dm.config.instruments.get.return_value = instr
        
        result = DecisionMaking._get_flip_config(mock_dm, "XRPUSDT")
        
        # max(1.0, 0.5) = 1.0
        assert result == (True, 1.0)
