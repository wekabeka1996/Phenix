"""
PACK-1 Validation: MRMicrostructureVetoConfig contract tests.

Tests:
1. Valid config loads cleanly
2. extra='forbid' rejects unknown fields
3. tfi_adverse_threshold bounds enforced
4. obi_adverse_threshold bounds enforced
5. absorption_rebound < price_continuation invariant
6. missing_policy only accepts "block" or "skip"
7. readiness_min_bars >= 1
8. tfi_ema_span >= 2
9. Full YAML load path wires microstructure_veto into MeanReversion1mStrategyConfig
10. Per-asset override wires correctly
"""
from copy import deepcopy
from functools import lru_cache
from pathlib import Path

import pytest
from pydantic import ValidationError

from apps.reference.config_loader import ConfigLoader
from apps.reference.config_models import (
    MRMicrostructureVetoConfig,
    MeanReversion1mStrategyConfig,
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

def _valid_veto_kwargs(**overrides):
    base = dict(
        enabled=True,
        tfi_ema_span=5,
        tfi_adverse_threshold=0.3,
        obi_confirm_enabled=False,
        obi_adverse_threshold=0.3,
        price_reaction_lookback_sec=60,
        price_continuation_threshold=0.001,
        absorption_wick_ratio_min=0.4,
        absorption_rebound_threshold=0.0005,
        readiness_min_bars=5,
        missing_policy="block",
    )
    base.update(overrides)
    return base


# ── Test: valid config loads ─────────────────────────────────────────────────

def test_valid_config_loads():
    cfg = MRMicrostructureVetoConfig(**_valid_veto_kwargs())
    assert cfg.enabled is True
    assert cfg.tfi_ema_span == 5
    assert cfg.tfi_adverse_threshold == 0.3
    assert cfg.obi_confirm_enabled is False
    assert cfg.missing_policy == "block"


# ── Test: extra='forbid' rejects unknown fields ─────────────────────────────

def test_extra_field_rejected():
    with pytest.raises(ValidationError, match="extra"):
        MRMicrostructureVetoConfig(**_valid_veto_kwargs(bogus_field=42))


# ── Test: tfi_adverse_threshold bounds ───────────────────────────────────────

def test_tfi_threshold_zero_rejected():
    with pytest.raises(ValidationError):
        MRMicrostructureVetoConfig(
            **_valid_veto_kwargs(tfi_adverse_threshold=0.0))


def test_tfi_threshold_above_one_rejected():
    with pytest.raises(ValidationError):
        MRMicrostructureVetoConfig(
            **_valid_veto_kwargs(tfi_adverse_threshold=1.5))


# ── Test: obi_adverse_threshold bounds ───────────────────────────────────────

def test_obi_threshold_zero_rejected():
    with pytest.raises(ValidationError):
        MRMicrostructureVetoConfig(
            **_valid_veto_kwargs(obi_adverse_threshold=0.0))


def test_obi_threshold_above_one_rejected():
    with pytest.raises(ValidationError):
        MRMicrostructureVetoConfig(
            **_valid_veto_kwargs(obi_adverse_threshold=1.5))


# ── Test: absorption_rebound < price_continuation invariant ──────────────────

def test_absorption_rebound_equals_continuation_rejected():
    """Rebound must be strictly less than continuation threshold."""
    with pytest.raises(ValidationError, match="absorption_rebound_threshold"):
        MRMicrostructureVetoConfig(**_valid_veto_kwargs(
            absorption_rebound_threshold=0.001,
            price_continuation_threshold=0.001,
        ))


def test_absorption_rebound_exceeds_continuation_rejected():
    with pytest.raises(ValidationError, match="absorption_rebound_threshold"):
        MRMicrostructureVetoConfig(**_valid_veto_kwargs(
            absorption_rebound_threshold=0.005,
            price_continuation_threshold=0.001,
        ))


# ── Test: missing_policy only accepts "block" (skip removed in R1) ────────────

def test_missing_policy_invalid_value_rejected():
    with pytest.raises(ValidationError):
        MRMicrostructureVetoConfig(
            **_valid_veto_kwargs(missing_policy="ignore"))


def test_missing_policy_skip_rejected():
    """\"skip\" was removed in R1 hardening — no fail-open path allowed."""
    with pytest.raises(ValidationError):
        MRMicrostructureVetoConfig(**_valid_veto_kwargs(missing_policy="skip"))


# ── Test: readiness_min_bars >= 1 ────────────────────────────────────────────

def test_readiness_min_bars_zero_rejected():
    with pytest.raises(ValidationError):
        MRMicrostructureVetoConfig(**_valid_veto_kwargs(readiness_min_bars=0))


# ── Test: tfi_ema_span >= 2 ─────────────────────────────────────────────────

def test_tfi_ema_span_below_minimum_rejected():
    with pytest.raises(ValidationError):
        MRMicrostructureVetoConfig(**_valid_veto_kwargs(tfi_ema_span=1))


# ── Test: YAML load path integration ────────────────────────────────────────

def test_yaml_load_wires_microstructure_veto(tmp_path):
    """MeanReversion1mStrategyConfig accepts microstructure_veto at top level."""
    data = deepcopy(_canonical_mr_kwargs())
    data["microstructure_veto"] = _valid_veto_kwargs()
    cfg = MeanReversion1mStrategyConfig(**data)
    assert cfg.microstructure_veto is not None
    assert cfg.microstructure_veto.enabled is True
    assert cfg.microstructure_veto.tfi_adverse_threshold == 0.3


def test_yaml_load_without_microstructure_veto():
    """Config loads cleanly when microstructure_veto is explicit null."""
    data = deepcopy(_canonical_mr_kwargs())
    data["microstructure_veto"] = None
    cfg = MeanReversion1mStrategyConfig(**data)
    assert cfg.microstructure_veto is None


# ── Test: per-asset override wires correctly ─────────────────────────────────

def test_per_asset_microstructure_veto_override():
    """MRStrategyOverrideConfig accepts microstructure_veto as per-asset override."""
    from apps.reference.config_models import MRStrategyOverrideConfig

    payload = deepcopy(_canonical_mr_asset_override_kwargs())
    payload["microstructure_veto"] = _valid_veto_kwargs(
        enabled=True,
        tfi_adverse_threshold=0.5,
    )
    override = MRStrategyOverrideConfig(**payload)
    assert override.microstructure_veto is not None
    assert override.microstructure_veto.tfi_adverse_threshold == 0.5
