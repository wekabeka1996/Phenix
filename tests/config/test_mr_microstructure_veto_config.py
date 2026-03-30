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
import pytest
from pydantic import ValidationError

from apps.reference.config_models import (
    MRMicrostructureVetoConfig,
    MeanReversion1mStrategyConfig,
)


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
        MRMicrostructureVetoConfig(**_valid_veto_kwargs(tfi_adverse_threshold=0.0))


def test_tfi_threshold_above_one_rejected():
    with pytest.raises(ValidationError):
        MRMicrostructureVetoConfig(**_valid_veto_kwargs(tfi_adverse_threshold=1.5))


# ── Test: obi_adverse_threshold bounds ───────────────────────────────────────

def test_obi_threshold_zero_rejected():
    with pytest.raises(ValidationError):
        MRMicrostructureVetoConfig(**_valid_veto_kwargs(obi_adverse_threshold=0.0))


def test_obi_threshold_above_one_rejected():
    with pytest.raises(ValidationError):
        MRMicrostructureVetoConfig(**_valid_veto_kwargs(obi_adverse_threshold=1.5))


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


# ── Test: missing_policy only accepts valid literals ─────────────────────────

def test_missing_policy_invalid_value_rejected():
    with pytest.raises(ValidationError):
        MRMicrostructureVetoConfig(**_valid_veto_kwargs(missing_policy="ignore"))


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
    import yaml

    yaml_content = """
mean_reversion:
  enabled: true
  timeframe_sec: 300
  allowed_regimes: ["FLAT_LOW", "FLAT_NORMAL"]
  execution:
    entry_order_type: "MARKET"
    entry_tif: null
  safety_gates:
    enabled: false
    system_stress_policy: "off"
  strategy:
    bb_window: 20
    bb_num_std: 2.0
    atr_window: 14
    rsi_window: 14
    entry_threshold: 0.115
    rsi_oversold: 30
    rsi_overbought: 70
    min_bars: 25
    min_bb_width: 0.001
    max_bb_width: 0.15
    sl_atr_mult: 1.5
    tp_to_mid: true
    cooldown_sec: 60
  regime_thresholds:
    high_vol_pct: 0.003
    low_vol_pct: 0.001
  assets:
    DOGEUSDT:
      enabled: true
      position_mode: "STRICT"
      allowed_regimes: ["FLAT_LOW"]
  regime_sizing:
    FLAT_LOW:
      sizing_mult: 0.8
      stop_mult: 1.0
      target_mult: 0.8
  microstructure_veto:
    enabled: true
    tfi_ema_span: 5
    tfi_adverse_threshold: 0.3
    obi_confirm_enabled: false
    obi_adverse_threshold: 0.3
    price_reaction_lookback_sec: 60
    price_continuation_threshold: 0.001
    absorption_wick_ratio_min: 0.4
    absorption_rebound_threshold: 0.0005
    readiness_min_bars: 5
    missing_policy: "block"
"""
    data = yaml.safe_load(yaml_content)["mean_reversion"]
    cfg = MeanReversion1mStrategyConfig(**data)
    assert cfg.microstructure_veto is not None
    assert cfg.microstructure_veto.enabled is True
    assert cfg.microstructure_veto.tfi_adverse_threshold == 0.3


def test_yaml_load_without_microstructure_veto():
    """Config loads cleanly when microstructure_veto is absent (Optional)."""
    data = dict(
        enabled=True,
        timeframe_sec=300,
        allowed_regimes=["FLAT_LOW"],
        execution=dict(entry_order_type="MARKET", entry_tif=None),
        safety_gates=dict(enabled=False, system_stress_policy="off"),
        strategy=dict(
            bb_window=20, bb_num_std=2.0, atr_window=14, rsi_window=14,
            entry_threshold=0.115, rsi_oversold=30, rsi_overbought=70,
            min_bars=25, min_bb_width=0.001, max_bb_width=0.15,
            sl_atr_mult=1.5, tp_to_mid=True, cooldown_sec=60,
        ),
        regime_thresholds=dict(high_vol_pct=0.003, low_vol_pct=0.001),
        assets=dict(DOGEUSDT=dict(
            enabled=True, position_mode="STRICT", allowed_regimes=["FLAT_LOW"],
        )),
        regime_sizing=dict(FLAT_LOW=dict(sizing_mult=0.8, stop_mult=1.0, target_mult=0.8)),
    )
    cfg = MeanReversion1mStrategyConfig(**data)
    assert cfg.microstructure_veto is None


# ── Test: per-asset override wires correctly ─────────────────────────────────

def test_per_asset_microstructure_veto_override():
    """MRStrategyOverrideConfig accepts microstructure_veto as per-asset override."""
    from apps.reference.config_models import MRStrategyOverrideConfig

    override = MRStrategyOverrideConfig(
        microstructure_veto=MRMicrostructureVetoConfig(**_valid_veto_kwargs(
            enabled=True,
            tfi_adverse_threshold=0.5,
        )),
    )
    assert override.microstructure_veto is not None
    assert override.microstructure_veto.tfi_adverse_threshold == 0.5
