"""
Tests for per-symbol flip orchestration configuration.

Verifies STRICT SSOT Architecture:
1. Global Killswitch (domains.yaml) - if OFF, all flip disabled.
2. Per-symbol config (instruments.yaml) - REQUIRED if Global ON.
3. Crash (Fail-Closed) if per-symbol config missing.
4. No implicit defaults.
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
from apps.reference.config_contract import ConfigContractError


class TestFlipOrchestrationConfig:
    """Pydantic validation tests for FlipOrchestrationConfig."""

    def test_required_fields(self):
        """Fields are REQUIRED (no defaults)."""
        with pytest.raises(ValidationError) as exc_info:
            FlipOrchestrationConfig()
        err = str(exc_info.value)
        assert "enabled" in err
        assert "Field required" in err
        assert "hysteresis_mult" in err

    def test_valid_config(self):
        """Valid config with explicit values."""
        cfg = FlipOrchestrationConfig(enabled=False, hysteresis_mult=1.5)
        assert cfg.enabled is False
        assert cfg.hysteresis_mult == 1.5

    def test_hysteresis_mult_below_1_rejected(self):
        """hysteresis_mult < 1.0 should raise ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            FlipOrchestrationConfig(enabled=True, hysteresis_mult=0.5)
        assert "hysteresis_mult" in str(exc_info.value)

    def test_extra_keys_rejected(self):
        """Unknown keys should raise ValidationError (extra='forbid')."""
        with pytest.raises(ValidationError):
            FlipOrchestrationConfig(enabled=True, hysteresis_mult=1.0, unknown_key=123)


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

    def test_flip_is_required(self, base_instrument_data):
        """flip field is REQUIRED."""
        with pytest.raises(ValidationError) as exc_info:
            InstrumentPrecisionSpec(**base_instrument_data)
        assert "flip" in str(exc_info.value)
        assert "Field required" in str(exc_info.value)

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


class TestDecisionMakingGetFlipConfig:
    """Integration tests for _get_flip_config getter (Strict SSOT)."""

    @pytest.fixture
    def mock_dm(self):
        """Create a mock DecisionMaking instance."""
        dm = MagicMock()
        # Global killswitch enabled by default for testing per-symbol logic
        dm.flip_global_enabled = True
        dm.config = MagicMock()
        return dm

    def test_global_killswitch_off_returns_disabled(self, mock_dm):
        """If global killswitch is OFF, returns (False, 1.0) ignoring per-symbol."""
        from apps.reference.domains.decision_making.decision_making import DecisionMaking
        
        mock_dm.flip_global_enabled = False
        
        # Should NOT reach per-symbol config
        result = DecisionMaking._get_flip_config(mock_dm, "ANY")
        assert result == (False, 1.0)
        
        # Verify instrument config was NOT accessed (optimization)
        mock_dm.config.instruments.get.assert_not_called()

    def test_crash_when_no_instrument(self, mock_dm):
        """FAIL-CLOSED: When symbol not in instruments, RAISE ConfigContractError."""
        from apps.reference.domains.decision_making.decision_making import DecisionMaking
        
        mock_dm.config.instruments.get.return_value = None
        
        with pytest.raises(ConfigContractError) as exc:
            DecisionMaking._get_flip_config(mock_dm, "UKNUSDT")
        
        assert "Missing instruments config" in str(exc.value)

    def test_crash_when_flip_is_none(self, mock_dm):
        """FAIL-CLOSED: When instrument has no flip config, RAISE ConfigContractError."""
        from apps.reference.domains.decision_making.decision_making import DecisionMaking
        
        instr = MagicMock()
        instr.flip = None
        mock_dm.config.instruments.get.return_value = instr
        
        with pytest.raises(ConfigContractError) as exc:
            DecisionMaking._get_flip_config(mock_dm, "BTCUSDT")
            
        assert "Missing REQUIRED flip config" in str(exc.value)

    def test_per_symbol_valid_config(self, mock_dm):
        """Returns per-symbol config if valid."""
        from apps.reference.domains.decision_making.decision_making import DecisionMaking
        
        flip_cfg = MagicMock()
        flip_cfg.enabled = True
        flip_cfg.hysteresis_mult = 1.35
        
        instr = MagicMock()
        instr.flip = flip_cfg
        mock_dm.config.instruments.get.return_value = instr
        
        result = DecisionMaking._get_flip_config(mock_dm, "ETHUSDT")
        
        assert result == (True, 1.35)

    def test_per_symbol_override_disabled(self, mock_dm):
        """Per-symbol enabled=False works."""
        from apps.reference.domains.decision_making.decision_making import DecisionMaking
        
        flip_cfg = MagicMock()
        flip_cfg.enabled = False
        flip_cfg.hysteresis_mult = 1.0
        
        instr = MagicMock()
        instr.flip = flip_cfg
        mock_dm.config.instruments.get.return_value = instr
        
        result = DecisionMaking._get_flip_config(mock_dm, "DOGEUSDT")
        
        assert result == (False, 1.0)

    def test_hysteresis_mult_floor_at_1(self, mock_dm):
        """hysteresis_mult is floored at 1.0 even if config has lower value."""
        from apps.reference.domains.decision_making.decision_making import DecisionMaking
        
        flip_cfg = MagicMock()
        flip_cfg.enabled = True
        flip_cfg.hysteresis_mult = 0.5  # Invalid but passed (e.g. from dict access)
        
        instr = MagicMock()
        instr.flip = flip_cfg
        mock_dm.config.instruments.get.return_value = instr
        
        result = DecisionMaking._get_flip_config(mock_dm, "XRPUSDT")
        
        # max(1.0, 0.5) = 1.0
        assert result == (True, 1.0)
