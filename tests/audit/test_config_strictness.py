import pytest
from decimal import Decimal
from pydantic import ValidationError

from apps.reference.config_models import (
    AuroraInstrumentConfig,
    FallbackConfig,
    LeverageConfig,
    MRAssetConfig,
)


def _error_types(exc: ValidationError) -> set[str]:
    return {str(e.get("type")) for e in exc.errors()}


def _assert_has_error_type(exc: ValidationError, expected_type: str) -> None:
    types = _error_types(exc)
    assert expected_type in types, f"Expected {expected_type!r}, got {sorted(types)}"


class TestConfigStrictness:
    def test_leverage_config_forbids_extra_fields(self):
        """Pydantic must reject typos in LeverageConfig."""
        with pytest.raises(ValidationError) as excinfo:
            LeverageConfig(target=20, mode="ISOLATED", typo_field="hack")
        _assert_has_error_type(excinfo.value, "extra_forbidden")

    def test_leverage_bounds(self):
        """Leverage must be between 1 and 125."""
        with pytest.raises(ValidationError):
            LeverageConfig(target=0)
        with pytest.raises(ValidationError):
            LeverageConfig(target=200)

    def test_leverage_mode_enum(self):
        """Invalid mode must fail (no coercion)."""
        with pytest.raises(ValidationError):
            LeverageConfig(target=20, mode="CROSS")  # must be CROSSED

    def test_fallback_config_requires_policy(self):
        """FallbackConfig must fail-fast when the explicit safety policy is omitted."""
        with pytest.raises(ValidationError) as excinfo:
            FallbackConfig()
        _assert_has_error_type(excinfo.value, "missing")

    def test_fallback_config_forbids_extra_fields(self):
        """Pydantic must reject typos in FallbackConfig."""
        with pytest.raises(ValidationError) as excinfo:
            FallbackConfig(
                policy="fail_closed",
                typo_field="oops",
            )
        _assert_has_error_type(excinfo.value, "extra_forbidden")

    def test_mr_asset_config_detects_leverage_typo(self):
        """Typo in 'leverage' field name MUST cause ValidationError."""
        with pytest.raises(ValidationError) as excinfo:
            MRAssetConfig(
                enabled=True,
                position_mode="STRICT",
                allowed_regimes=["FLAT_LOW"],
                laverage={"target": 10},  # TYPO! Should be 'leverage'
            )
        _assert_has_error_type(excinfo.value, "extra_forbidden")

    def test_aurora_instrument_config_detects_leverage_typo(self):
        """Typo in 'leverage' field name MUST cause ValidationError."""
        base = {
            name: None
            for name, field in AuroraInstrumentConfig.model_fields.items()
            if field.is_required()
        }
        base["enabled"] = True
        base["position_mode"] = "STRICT"

        with pytest.raises(ValidationError) as excinfo:
            AuroraInstrumentConfig.model_validate(
                {
                    **base,
                    "laverage": {"target": 20},  # TYPO! Should be 'leverage'
                }
            )
        _assert_has_error_type(excinfo.value, "extra_forbidden")
