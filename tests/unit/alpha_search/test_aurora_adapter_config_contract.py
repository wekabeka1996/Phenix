"""
Contract test: AuroraAdapterConfig requires signal_weights, feature_neutrals, regime_thresholds.

ALPHA-CONFIG-CONTRACT-01:
These three fields were previously Optional[Dict] with default=None, enabling a silent
fallback to _FALLBACK_* constants when absent from YAML. Since they are now required,
Pydantic raises ValidationError at parse time if any is missing — fail-loud contract.

Tests cover:
  - Missing signal_weights raises ValidationError
  - Missing feature_neutrals raises ValidationError
  - Missing regime_thresholds raises ValidationError
  - All three present → valid config
"""
import pytest
from pydantic import ValidationError

from apps.reference.domains.alpha_search.config_models import AuroraAdapterConfig
from apps.reference.domains.alpha_search.models.aurora_adapter import (
    _FALLBACK_SIGNAL_WEIGHTS,
    _FALLBACK_FEATURE_NEUTRALS,
    _FALLBACK_REGIME_THRESHOLDS,
)


def _minimal_valid_kwargs():
    """Minimal kwargs that satisfy AuroraAdapterConfig required fields."""
    return {
        "signal_weights": _FALLBACK_SIGNAL_WEIGHTS,
        "feature_neutrals": _FALLBACK_FEATURE_NEUTRALS,
        "regime_thresholds": _FALLBACK_REGIME_THRESHOLDS,
    }


class TestAuroraAdapterConfigContract:
    """AuroraAdapterConfig.signal_weights/feature_neutrals/regime_thresholds are required."""

    def test_missing_signal_weights_raises(self):
        """
        AuroraAdapterConfig without signal_weights must raise ValidationError.
        Previously this silently used _FALLBACK_SIGNAL_WEIGHTS.
        """
        kwargs = _minimal_valid_kwargs()
        del kwargs["signal_weights"]
        with pytest.raises(ValidationError, match="signal_weights"):
            AuroraAdapterConfig(**kwargs)

    def test_missing_feature_neutrals_raises(self):
        """
        AuroraAdapterConfig without feature_neutrals must raise ValidationError.
        """
        kwargs = _minimal_valid_kwargs()
        del kwargs["feature_neutrals"]
        with pytest.raises(ValidationError, match="feature_neutrals"):
            AuroraAdapterConfig(**kwargs)

    def test_missing_regime_thresholds_raises(self):
        """
        AuroraAdapterConfig without regime_thresholds must raise ValidationError.
        """
        kwargs = _minimal_valid_kwargs()
        del kwargs["regime_thresholds"]
        with pytest.raises(ValidationError, match="regime_thresholds"):
            AuroraAdapterConfig(**kwargs)

    def test_all_required_fields_present_is_valid(self):
        """AuroraAdapterConfig with all required fields must not raise."""
        cfg = AuroraAdapterConfig(**_minimal_valid_kwargs())
        assert cfg.signal_weights == _FALLBACK_SIGNAL_WEIGHTS
        assert cfg.feature_neutrals == _FALLBACK_FEATURE_NEUTRALS
        assert cfg.regime_thresholds == _FALLBACK_REGIME_THRESHOLDS

    def test_signal_weights_value_is_propagated(self):
        """config.signal_weights must equal whatever was passed, not a hardcoded fallback."""
        custom_weights = {"obi": 0.99, "tfi": 0.01}
        kwargs = _minimal_valid_kwargs()
        kwargs["signal_weights"] = custom_weights
        cfg = AuroraAdapterConfig(**kwargs)
        assert cfg.signal_weights["obi"] == 0.99, (
            "signal_weights is returning a fallback constant instead of the passed value."
        )

    def test_no_silent_fallback_in_adapter_constructor(self):
        """
        AuroraAlphaAdapter with explicit signal_weights must use those weights,
        not the internal _FALLBACK_SIGNAL_WEIGHTS.
        """
        from apps.reference.domains.alpha_search.models.aurora_adapter import AuroraAlphaAdapter
        custom = {"obi": 0.77, "tfi": 0.23}
        adapter = AuroraAlphaAdapter(
            signal_weights=custom,
            feature_neutrals=_FALLBACK_FEATURE_NEUTRALS,
            regime_thresholds=_FALLBACK_REGIME_THRESHOLDS,
        )
        assert adapter._signal_weights["obi"] == 0.77, (
            "AuroraAlphaAdapter is not using the passed signal_weights."
        )
