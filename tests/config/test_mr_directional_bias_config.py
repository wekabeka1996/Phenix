"""
PACK-4 Validation: MRDirectionalBiasConfig contract tests.

Tests:
1. Valid config loads cleanly
2. extra='forbid' rejects unknown fields
3. base thresholds must be within clamp bounds
4. clamp_min must be < clamp_max
5. funding_shift_magnitude bounds
6. funding_normalization_scale > 0
7. funding_deadband bounds
8. YAML load path integration
9. Per-asset override wires correctly
10. Legacy symmetric threshold compat (both thresholds = old value)
"""
from copy import deepcopy
from functools import lru_cache
from pathlib import Path

import pytest
from pydantic import ValidationError

from apps.reference.config_loader import ConfigLoader
from apps.reference.config_models import (
    MRDirectionalBiasConfig,
    MeanReversion1mStrategyConfig,
    MRStrategyOverrideConfig,
)


CONFIG_DIR = Path("config/aurora")


@lru_cache(maxsize=1)
def _canonical_mr_kwargs() -> dict:
    cfg = ConfigLoader(CONFIG_DIR).load_config()
    assert cfg.strategies.mean_reversion is not None
    return cfg.strategies.mean_reversion.model_dump()


@lru_cache(maxsize=1)
def _canonical_mr_asset_override_kwargs() -> dict:
    cfg = ConfigLoader(CONFIG_DIR).load_config()
    assert cfg.strategies.mean_reversion is not None
    return cfg.strategies.mean_reversion.assets["DOGEUSDT"].strategy.model_dump()


# ── Helpers ──────────────────────────────────────────────────────────────────

def _valid_bias_kwargs(**overrides):
    base = dict(
        enabled=True,
        base_long_threshold=0.115,
        base_short_threshold=0.115,
        funding_shift_magnitude=0.02,
        funding_normalization_scale=0.0003,
        funding_deadband=0.1,
        threshold_clamp_min=0.01,
        threshold_clamp_max=0.3,
    )
    base.update(overrides)
    return base


# ── 1. Valid config loads ────────────────────────────────────────────────────

def test_valid_config_loads():
    cfg = MRDirectionalBiasConfig(**_valid_bias_kwargs())
    assert cfg.enabled is True
    assert cfg.base_long_threshold == 0.115
    assert cfg.base_short_threshold == 0.115
    assert cfg.funding_shift_magnitude == 0.02


# ── 2. extra='forbid' ───────────────────────────────────────────────────────

def test_extra_field_rejected():
    with pytest.raises(ValidationError, match="extra"):
        MRDirectionalBiasConfig(**_valid_bias_kwargs(bogus_field=42))


# ── 3. base thresholds within clamp bounds ───────────────────────────────────

def test_base_long_below_clamp_min_rejected():
    with pytest.raises(ValidationError, match="base_long_threshold"):
        MRDirectionalBiasConfig(**_valid_bias_kwargs(
            base_long_threshold=0.005,
            threshold_clamp_min=0.01,
        ))


def test_base_short_above_clamp_max_rejected():
    with pytest.raises(ValidationError, match="base_short_threshold"):
        MRDirectionalBiasConfig(**_valid_bias_kwargs(
            base_short_threshold=0.35,
            threshold_clamp_max=0.3,
        ))


# ── 4. clamp_min < clamp_max ────────────────────────────────────────────────

def test_clamp_min_equals_clamp_max_rejected():
    with pytest.raises(ValidationError, match="threshold_clamp_min"):
        MRDirectionalBiasConfig(**_valid_bias_kwargs(
            threshold_clamp_min=0.2,
            threshold_clamp_max=0.2,
        ))


def test_clamp_min_exceeds_clamp_max_rejected():
    with pytest.raises(ValidationError, match="threshold_clamp_min"):
        MRDirectionalBiasConfig(**_valid_bias_kwargs(
            threshold_clamp_min=0.3,
            threshold_clamp_max=0.1,
            base_long_threshold=0.15,
            base_short_threshold=0.15,
        ))


# ── 5. funding_shift_magnitude bounds ────────────────────────────────────────

def test_funding_shift_magnitude_negative_rejected():
    with pytest.raises(ValidationError):
        MRDirectionalBiasConfig(
            **_valid_bias_kwargs(funding_shift_magnitude=-0.01))


def test_funding_shift_magnitude_too_large_rejected():
    with pytest.raises(ValidationError):
        MRDirectionalBiasConfig(
            **_valid_bias_kwargs(funding_shift_magnitude=0.3))


# ── 6. funding_normalization_scale > 0 ───────────────────────────────────────

def test_funding_normalization_zero_rejected():
    with pytest.raises(ValidationError):
        MRDirectionalBiasConfig(
            **_valid_bias_kwargs(funding_normalization_scale=0.0))


# ── 7. funding_deadband bounds ───────────────────────────────────────────────

def test_funding_deadband_negative_rejected():
    with pytest.raises(ValidationError):
        MRDirectionalBiasConfig(**_valid_bias_kwargs(funding_deadband=-0.1))


def test_funding_deadband_above_one_rejected():
    with pytest.raises(ValidationError):
        MRDirectionalBiasConfig(**_valid_bias_kwargs(funding_deadband=1.5))


# ── 8. YAML load path integration ───────────────────────────────────────────

def test_yaml_wires_directional_bias():
    """MeanReversion1mStrategyConfig loads directional_bias at top level."""
    data = deepcopy(_canonical_mr_kwargs())
    data["directional_bias"] = _valid_bias_kwargs()
    cfg = MeanReversion1mStrategyConfig(**data)
    assert cfg.directional_bias is not None
    assert cfg.directional_bias.enabled is True
    assert cfg.directional_bias.base_long_threshold == 0.115


def test_yaml_without_directional_bias():
    """Config loads cleanly when directional_bias is explicit null."""
    data = deepcopy(_canonical_mr_kwargs())
    data["directional_bias"] = None
    cfg = MeanReversion1mStrategyConfig(**data)
    assert cfg.directional_bias is None


# ── 9. Per-asset override ────────────────────────────────────────────────────

def test_per_asset_directional_bias_override():
    payload = deepcopy(_canonical_mr_asset_override_kwargs())
    payload["directional_bias"] = _valid_bias_kwargs(
        base_long_threshold=0.05,
        base_short_threshold=0.08,
    )
    override = MRStrategyOverrideConfig(**payload)
    assert override.directional_bias is not None
    assert override.directional_bias.base_long_threshold == 0.05
    assert override.directional_bias.base_short_threshold == 0.08


# ── 10. Legacy compatibility: symmetric = both equal ─────────────────────────

def test_symmetric_thresholds_accepted():
    """Both thresholds equal to legacy entry_threshold works fine."""
    cfg = MRDirectionalBiasConfig(**_valid_bias_kwargs(
        base_long_threshold=0.115,
        base_short_threshold=0.115,
    ))
    assert cfg.base_long_threshold == cfg.base_short_threshold == 0.115


def test_asymmetric_thresholds_accepted():
    """Different long/short thresholds are valid."""
    cfg = MRDirectionalBiasConfig(**_valid_bias_kwargs(
        base_long_threshold=0.05,
        base_short_threshold=0.10,
    ))
    assert cfg.base_long_threshold == 0.05
    assert cfg.base_short_threshold == 0.10
