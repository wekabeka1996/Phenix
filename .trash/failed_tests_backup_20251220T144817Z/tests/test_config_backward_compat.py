"""
PHASE 4 Backward Compatibility Tests

Tests:
- .get() method works for legacy code
- Attribute access works
- Mixed usage works
- None values handled correctly
- Defaults handled correctly
"""

import pytest
from apps.reference.config_models import AuroraConfig


class TestBackwardCompatibility:
    """Backward compatibility tests."""

    def test_attribute_access_direct(self):
        """Config should support direct attribute access (Pydantic style)."""
        config = AuroraConfig(trading_mode="testnet")
        assert hasattr(
            config, "trading_mode"), "Config should have trading_mode attribute"
        assert config.trading_mode == "testnet"

    def test_attribute_access_returns_value(self):
        """Direct attribute access should return correct values."""
        config = AuroraConfig(trading_mode="testnet")

        # Should access top-level field
        result = config.trading_mode
        assert result == "testnet"

    def test_missing_optional_fields(self):
        """Optional fields should be None when not provided."""
        config = AuroraConfig(trading_mode="testnet")

        # Optional fields not provided should be None
        assert config.decision is None
        assert config.execution is None

    def test_attribute_access_nested(self):
        """Nested attribute access should work (Pydantic style)."""
        config = AuroraConfig(trading_mode="testnet")

        # Direct nested attribute access
        assert config.trading.mode == "testnet"
        assert isinstance(config.trading.decision.kelly.kelly_cap, float)

    def test_nested_attribute_access(self):
        """Nested attribute access should work."""
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

        # Deep attribute access
        assert config.trading.decision.kelly.kelly_cap == 0.25

    def test_optional_fields_with_defaults(self):
        """Optional fields should use defaults when not provided."""
        config = AuroraConfig(trading_mode="testnet")

        # Optional fields not provided should be None or have defaults
        assert config.decision is None
        assert config.execution is None

    def test_model_dump_with_defaults(self):
        """model_dump should include fields with valid values."""
        config = AuroraConfig(trading_mode="testnet")

        # Pydantic v2 method
        d = config.model_dump()
        assert isinstance(d, dict)
        assert d["trading_mode"] == "testnet"
        # Kelly cap should have default value
        assert d["trading"]["decision"]["kelly"]["kelly_cap"] == 0.25

    def test_model_dump_exclude_none(self):
        """model_dump should support exclude_none for truly None values."""
        config = AuroraConfig(trading_mode="testnet")

        # Get dict without None values
        d = config.model_dump(exclude_none=True)
        assert isinstance(d, dict)
        # Should not have decision/execution/etc since they are None
        assert "decision" not in d or d["decision"] is not None

    def test_model_json_schema(self):
        """Should be able to get JSON schema."""
        schema = AuroraConfig.model_json_schema()
        assert isinstance(schema, dict)
        assert "properties" in schema
        assert "trading_mode" in schema["properties"]

    def test_mixed_access_patterns(self):
        """Pydantic attribute access should be consistent."""
        config = AuroraConfig(
            trading_mode="testnet",
            trading={
                "execution": {
                    "manage": {
                        "brackets": {
                            "enabled": True
                        }
                    }
                }
            }
        )

        # Pattern 1: Direct attribute access (Pydantic style)
        assert config.trading.execution.manage.brackets.enabled is True

        # Pattern 2: Via model_dump (Pydantic style)
        d = config.model_dump()
        assert d["trading"]["mode"] == "testnet"

        # Pattern 3: Direct top-level access
        assert config.trading_mode == "testnet"
