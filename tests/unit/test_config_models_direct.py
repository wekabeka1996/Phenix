"""
Direct Unit Tests for apps.reference.config_models Pydantic Models.

PHASE 3: ASSURANCE — Direct Testing
These tests validate Pydantic models WITHOUT going through config_loader.

Purpose:
- Ensure fail-closed behavior (extra='forbid')
- Validate type coercion and rejection
- Test boundary values for numeric constraints

CFG-MODELS-DIRECT-TESTS-01
"""

import pytest
from pydantic import ValidationError

from apps.reference.config_models import (
    InstrumentSpec,
    InstrumentPrecisionSpec,
    InstrumentExecutionConfig,
    InstrumentSizingConfig,
    SignalWeights,
)


class TestInstrumentExecutionConfig:
    """Test InstrumentExecutionConfig validation."""

    def test_valid_execution_config(self):
        """Valid config should pass validation."""
        config = InstrumentExecutionConfig(
            margin_mode="isolated",
            target_leverage=10,
            leverage_policy="verify_only",
            max_notional_utilization=0.5
        )
        assert config.margin_mode == "isolated"
        assert config.target_leverage == 10
        assert config.leverage_policy == "verify_only"
        assert config.max_notional_utilization == 0.5

    def test_target_leverage_min_boundary(self):
        """target_leverage must be >= 1."""
        with pytest.raises(ValidationError) as exc_info:
            InstrumentExecutionConfig(
                margin_mode="isolated",
                target_leverage=0,  # Invalid: < 1
                leverage_policy="verify_only",
                max_notional_utilization=0.5
            )
        assert "target_leverage" in str(exc_info.value)

    def test_target_leverage_max_boundary(self):
        """target_leverage must be <= 125."""
        with pytest.raises(ValidationError) as exc_info:
            InstrumentExecutionConfig(
                margin_mode="isolated",
                target_leverage=126,  # Invalid: > 125
                leverage_policy="verify_only",
                max_notional_utilization=0.5
            )
        assert "target_leverage" in str(exc_info.value)

    def test_max_notional_utilization_boundaries(self):
        """max_notional_utilization must be between 0.0 and 1.0."""
        # Test below 0
        with pytest.raises(ValidationError) as exc_info:
            InstrumentExecutionConfig(
                margin_mode="isolated",
                target_leverage=10,
                leverage_policy="verify_only",
                max_notional_utilization=-0.1  # Invalid
            )
        assert "max_notional_utilization" in str(exc_info.value)

        # Test above 1
        with pytest.raises(ValidationError) as exc_info:
            InstrumentExecutionConfig(
                margin_mode="isolated",
                target_leverage=10,
                leverage_policy="verify_only",
                max_notional_utilization=1.5  # Invalid
            )
        assert "max_notional_utilization" in str(exc_info.value)

    def test_invalid_margin_mode_literal(self):
        """margin_mode must be 'isolated' or 'cross'."""
        with pytest.raises(ValidationError) as exc_info:
            InstrumentExecutionConfig(
                margin_mode="invalid_mode",  # Invalid
                target_leverage=10,
                leverage_policy="verify_only",
                max_notional_utilization=0.5
            )
        assert "margin_mode" in str(exc_info.value)

    def test_extra_field_forbidden(self):
        """Extra fields should raise ValidationError (extra='forbid')."""
        with pytest.raises(ValidationError) as exc_info:
            InstrumentExecutionConfig(
                margin_mode="isolated",
                target_leverage=10,
                leverage_policy="verify_only",
                max_notional_utilization=0.5,
                unknown_extra_field="should_fail"  # Extra field
            )
        error_str = str(exc_info.value)
        assert "unknown_extra_field" in error_str or "Extra inputs" in error_str


class TestInstrumentSizingConfig:
    """Test InstrumentSizingConfig validation."""

    def test_valid_sizing_config(self):
        """Valid config should pass validation."""
        config = InstrumentSizingConfig(margin_pct=0.1)
        assert config.margin_pct == 0.1

    def test_margin_pct_must_be_positive(self):
        """margin_pct must be > 0."""
        with pytest.raises(ValidationError) as exc_info:
            InstrumentSizingConfig(margin_pct=0.0)  # Invalid: not > 0
        assert "margin_pct" in str(exc_info.value)

        with pytest.raises(ValidationError) as exc_info:
            InstrumentSizingConfig(margin_pct=-0.1)  # Invalid: negative
        assert "margin_pct" in str(exc_info.value)

    def test_margin_pct_max_boundary(self):
        """margin_pct must be <= 1.0."""
        with pytest.raises(ValidationError) as exc_info:
            InstrumentSizingConfig(margin_pct=1.1)  # Invalid: > 1.0
        assert "margin_pct" in str(exc_info.value)

    def test_margin_pct_valid_edge_case(self):
        """margin_pct=1.0 should be valid (edge case)."""
        config = InstrumentSizingConfig(margin_pct=1.0)
        assert config.margin_pct == 1.0


class TestInstrumentSpec:
    """Test InstrumentSpec validation."""

    def test_valid_instrument_spec(self):
        """Valid InstrumentSpec should pass."""
        spec = InstrumentSpec(
            symbol="BTCUSDT",
            step_size="0.001",
            tick_size="0.01",
            min_qty="0.001",
            min_notional="10",
            quote="USDT"
        )
        assert spec.symbol == "BTCUSDT"

    def test_missing_required_field(self):
        """Missing required field should raise ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            InstrumentSpec(
                symbol="BTCUSDT",
                step_size="0.001",
                # tick_size missing
                min_qty="0.001",
                min_notional="10",
                quote="USDT"
            )
        assert "tick_size" in str(exc_info.value)

    def test_extra_field_forbidden(self):
        """Extra fields should raise ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            InstrumentSpec(
                symbol="BTCUSDT",
                step_size="0.001",
                tick_size="0.01",
                min_qty="0.001",
                min_notional="10",
                quote="USDT",
                bogus_field="should_fail"  # Extra field
            )
        error_str = str(exc_info.value)
        assert "bogus_field" in error_str or "Extra inputs" in error_str


class TestInstrumentPrecisionSpec:
    """Test InstrumentPrecisionSpec validation."""

    def test_valid_precision_spec(self):
        """Valid InstrumentPrecisionSpec should pass."""
        spec = InstrumentPrecisionSpec(
            symbol="BTCUSDT",
            tick_size="0.01",
            step_size="0.001",
            min_qty="0.001",
            min_notional="10",
            execution=InstrumentExecutionConfig(
                margin_mode="isolated",
                target_leverage=10,
                leverage_policy="verify_only",
                max_notional_utilization=0.5
            ),
            sizing=InstrumentSizingConfig(margin_pct=0.1)
        )
        assert spec.symbol == "BTCUSDT"
        assert spec.execution.target_leverage == 10
        assert spec.sizing.margin_pct == 0.1

    def test_nested_validation_propagates(self):
        """Invalid nested config should raise ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            InstrumentPrecisionSpec(
                symbol="BTCUSDT",
                tick_size="0.01",
                step_size="0.001",
                min_qty="0.001",
                min_notional="10",
                execution=InstrumentExecutionConfig(
                    margin_mode="isolated",
                    target_leverage=200,  # Invalid: > 125
                    leverage_policy="verify_only",
                    max_notional_utilization=0.5
                ),
                sizing=InstrumentSizingConfig(margin_pct=0.1)
            )
        assert "target_leverage" in str(exc_info.value)


class TestSignalWeights:
    """Test SignalWeights validation."""

    def test_valid_signal_weights(self):
        """Valid SignalWeights should pass."""
        weights = SignalWeights(
            obi=1.0,
            tfi=0.5,
            delta_price=0.3,
            ema_bias=0.2,
            volume_spike=0.1,
            volatility_state=0.4,
            depth_imbalance=0.6,
            macro_resid=0.0
        )
        assert weights.obi == 1.0
        assert weights.macro_resid == 0.0

    def test_missing_required_field(self):
        """Missing required field should raise ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            SignalWeights(
                obi=1.0,
                tfi=0.5,
                delta_price=0.3,
                # ema_bias missing
                volume_spike=0.1,
                volatility_state=0.4,
                depth_imbalance=0.6,
                macro_resid=0.0
            )
        assert "ema_bias" in str(exc_info.value)

    def test_extra_field_forbidden(self):
        """Extra fields should raise ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            SignalWeights(
                obi=1.0,
                tfi=0.5,
                delta_price=0.3,
                ema_bias=0.2,
                volume_spike=0.1,
                volatility_state=0.4,
                depth_imbalance=0.6,
                macro_resid=0.0,
                unknown_signal="should_fail"  # Extra field
            )
        error_str = str(exc_info.value)
        assert "unknown_signal" in error_str or "Extra inputs" in error_str


class TestDataTypeValidation:
    """Test that wrong data types are rejected."""

    def test_string_instead_of_float_rejected(self):
        """String 'abc' instead of float should raise ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            InstrumentSizingConfig(margin_pct="not_a_number")
        error_str = str(exc_info.value)
        assert "margin_pct" in error_str

    def test_string_instead_of_int_rejected(self):
        """String 'abc' instead of int should raise ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            InstrumentExecutionConfig(
                margin_mode="isolated",
                target_leverage="not_an_int",  # Invalid type
                leverage_policy="verify_only",
                max_notional_utilization=0.5
            )
        error_str = str(exc_info.value)
        assert "target_leverage" in error_str

    def test_numeric_string_coercion_for_float(self):
        """Numeric string '0.5' should be coerced to float (Pydantic behavior)."""
        # Pydantic V2 allows coercion of numeric strings by default
        config = InstrumentSizingConfig(margin_pct="0.5")
        assert config.margin_pct == 0.5

    def test_numeric_string_coercion_for_int(self):
        """Numeric string '10' should be coerced to int (Pydantic behavior)."""
        config = InstrumentExecutionConfig(
            margin_mode="isolated",
            target_leverage="10",  # String, but coercible
            leverage_policy="verify_only",
            max_notional_utilization=0.5
        )
        assert config.target_leverage == 10


class TestExtraForbidBehavior:
    """Test that extra='forbid' is enforced across models."""

    def test_instrument_execution_config_forbids_extra(self):
        """InstrumentExecutionConfig should forbid extra fields."""
        with pytest.raises(ValidationError):
            InstrumentExecutionConfig(
                margin_mode="isolated",
                target_leverage=10,
                leverage_policy="verify_only",
                max_notional_utilization=0.5,
                typo_field="oops"
            )

    def test_instrument_sizing_config_forbids_extra(self):
        """InstrumentSizingConfig should forbid extra fields."""
        with pytest.raises(ValidationError):
            InstrumentSizingConfig(
                margin_pct=0.1,
                extra_sizing_param=100
            )

    def test_instrument_spec_forbids_extra(self):
        """InstrumentSpec should forbid extra fields."""
        with pytest.raises(ValidationError):
            InstrumentSpec(
                symbol="BTCUSDT",
                step_size="0.001",
                tick_size="0.01",
                min_qty="0.001",
                min_notional="10",
                quote="USDT",
                typo_key="error"
            )
