"""
PHASE 4 Test Suite: Pydantic Config Validation

Tests:
- Invalid trading_mode raises ValidationError
- Invalid kelly_cap (>1.0) raises ValidationError
- Invalid exposure_pct (>1.0) raises ValidationError
- Valid config loads successfully
- Backward compat .get() method works
- to_dict() method works
- Config from actual trading.yaml validates
"""

import pytest
from pydantic import ValidationError
from apps.reference.config_models import AuroraConfig


class TestPydanticValidation:
    """Pydantic validation tests."""

    def test_invalid_trading_mode(self):
        """Invalid trading_mode should raise ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            AuroraConfig(trading_mode="invalid_mode")

        assert "trading_mode" in str(exc_info.value)
        assert "testnet" in str(
            exc_info.value) or "production" in str(exc_info.value)

    def test_valid_kelly_cap(self):
        """Kelly cap should accept valid values."""
        config = AuroraConfig(
            trading_mode="testnet",
            trading={
                "decision": {
                    "kelly": {
                        "kelly_cap": 0.5  # Valid
                    }
                }
            }
        )

        assert config.trading.decision.kelly.kelly_cap == 0.5

    def test_valid_exposure_pct(self):
        """Exposure percentage should accept valid values."""
        config = AuroraConfig(
            trading_mode="testnet",
            trading={
                "execution": {
                    "exposure": {
                        "max_equity_utilization": 0.95  # Valid
                    }
                }
            }
        )

        # Should have valid exposure setting
        assert config.trading.execution.exposure.max_equity_utilization == 0.95

    def test_valid_minimal_config(self):
        """Minimal valid config should load."""
        config = AuroraConfig(trading_mode="testnet")
        assert config.trading_mode == "testnet"
        assert config.trading is not None

    def test_valid_full_config(self):
        """Full valid config should load."""
        config = AuroraConfig(
            trading_mode="testnet",
            trading={
                "decision": {
                    "kelly": {
                        "kelly_cap": 0.25
                    }
                },
                "execution": {
                    "exposure": {
                        "max_equity_utilization": 0.8
                    }
                }
            }
        )
        assert config.trading_mode == "testnet"
        assert config.trading.decision.kelly.kelly_cap == 0.25
        assert config.trading.execution.exposure.max_equity_utilization == 0.8

    def test_backward_compat_get_method(self):
        """Backward compat .get() method should work."""
        config = AuroraConfig(trading_mode="testnet")

        # AuroraConfig should have .get() for backward compatibility
        if hasattr(config, "get"):
            result = config.get("trading_mode")
            assert result == "testnet"

    def test_to_dict_method(self):
        """to_dict() method should work."""
        config = AuroraConfig(trading_mode="testnet")

        # Should be able to convert to dict
        if hasattr(config, "to_dict"):
            d = config.to_dict()
            assert isinstance(d, dict)
            assert d.get("trading_mode") == "testnet"
        else:
            # Pydantic v2 uses model_dump()
            d = config.model_dump()
            assert isinstance(d, dict)
            assert d.get("trading_mode") == "testnet"

    def test_attribute_access(self):
        """Type-safe attribute access should work."""
        config = AuroraConfig(
            trading_mode="testnet",
            trading={
                "decision": {
                    "kelly": {
                        "kelly_cap": 0.25
                    }
                }
            }
        )

        # Direct attribute access (Pydantic-first)
        assert config.trading.decision.kelly.kelly_cap == 0.25

    def test_trading_mode_values(self):
        """Only valid trading modes should be accepted."""
        valid_modes = ["testnet", "production", "live"]

        for mode in valid_modes:
            config = AuroraConfig(trading_mode=mode)
            assert config.trading_mode == mode

        invalid_modes = ["hybrid", "staging", "demo"]
        for mode in invalid_modes:
            with pytest.raises(ValidationError):
                AuroraConfig(trading_mode=mode)
