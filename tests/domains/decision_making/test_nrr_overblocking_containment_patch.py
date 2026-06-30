from __future__ import annotations

import pytest
from pathlib import Path
from collections import deque
from unittest.mock import MagicMock
from pydantic import ValidationError

from apps.reference.config_loader import ConfigLoader
from apps.reference.config.domains.decision_making import PriceMotionSanityConfig
from apps.reference.domains.decision_making.gates.safety_gates import apply_safety_gates
from apps.reference.domains.decision_making.contracts.normalized_reject_reasons import NormalizedRejectReasons


def _fresh_config():
    return ConfigLoader(Path("config/aurora")).load_config()


def _regime_cache_snapshot(*, confidence: str, regime: str = "TREND_UP") -> dict:
    return {
        "regime": regime,
        "confidence": confidence,
        "cache_write_ts_ms": 1_700_000_000_456,
        "basis_tf_sec": 300,
        "bar_close_ts_ms": 1_700_000_000_000,
        "changed": False,
        "stable_confidence": confidence,
        "source_model": "sma_trend_v1",
        "pre_cutoff_source_model": "sma_trend_v1",
        "confidence_min": "0.15",
        "confidence_max": "0.85",
        "pre_cutoff_regime": regime,
        "pre_cutoff_confidence": confidence,
        "pre_cutoff_clamped_to_min": False,
        "pre_cutoff_clamped_to_max": False,
        "pre_cutoff_boundary_reason": None,
        "uncertain_cutoff": "0.22",
        "demoted_to_uncertain": False,
        "raw_regime": regime,
        "raw_confidence": confidence,
        "raw_boundary_reason": None,
        "hysteresis_bars": 3,
        "hysteresis_confirm_count": 3,
        "carried_previous_stable": False,
        "emitted_confidence_kind": "stable_heartbeat",
        "reason_summary": "pre_cutoff_source=sma_trend_v1; hysteresis_confirm=3/3",
        "regime_provenance": {
            "source_kind": "detector_cache",
            "detector_event": {
                "event_name": "EVT:REGIME_DETECTED",
                "rid": "rid-detector-audit-1",
                "ts_ms": 1_700_000_000_000,
                "last_update_ts_ms": 1_700_000_000_123,
                "structural_regime_ref": "structural:BTCUSDT:1700000000000",
                "basis_tf_sec": 300,
                "bar_close_ts_ms": 1_700_000_000_000,
                "changed": False,
                "regime": regime,
                "confidence": confidence,
                "stable_confidence": confidence,
                "source_model": "sma_trend_v1",
                "pre_cutoff_source_model": "sma_trend_v1",
                "confidence_min": "0.15",
                "confidence_max": "0.85",
                "pre_cutoff_regime": regime,
                "pre_cutoff_confidence": confidence,
                "pre_cutoff_clamped_to_min": False,
                "pre_cutoff_clamped_to_max": False,
                "pre_cutoff_boundary_reason": None,
                "uncertain_cutoff": "0.22",
                "demoted_to_uncertain": False,
                "raw_regime": regime,
                "raw_confidence": confidence,
                "raw_boundary_reason": None,
                "hysteresis_bars": 3,
                "hysteresis_confirm_count": 3,
                "carried_previous_stable": False,
                "emitted_confidence_kind": "stable_heartbeat",
                "reason_summary": "pre_cutoff_source=sma_trend_v1; hysteresis_confirm=3/3",
            },
            "cache_snapshot": {
                "cache_write_ts_ms": 1_700_000_000_456,
                "regime": regime,
                "confidence": float(confidence),
            },
        },
    }


def test_1_config_loads_with_target_gate_states() -> None:
    cfg = _fresh_config()
    dm_domain = cfg.domains.decision_making
    
    # NRR-026 remains enabled
    assert dm_domain.directional_sanity.nrr026_enabled is True
    # NRR-027 disabled (observe-only / non-enforced)
    assert dm_domain.directional_sanity.nrr027_enabled is False
    # NRR-028 enabled
    assert dm_domain.price_motion_sanity.nrr028_enabled is True
    # NRR-029 disabled
    assert dm_domain.price_motion_sanity.nrr029_enabled is False
    # NRR-030 disabled
    assert dm_domain.price_motion_sanity.nrr030_enabled is False


def test_2_nrr026_blocks_below_threshold() -> None:
    cfg = _fresh_config()
    cfg.strategies.aurora.safety_gates.enabled = True
    cfg.domains.decision_making.directional_sanity.enabled = True
    cfg.domains.decision_making.directional_sanity.min_regime_confidence = 0.35
    cfg.domains.decision_making.directional_sanity.min_regime_confidence_by_regime = {"DEFAULT": 0.35}
    cfg.domains.decision_making.price_motion_sanity.enabled = False

    result = apply_safety_gates(
        symbol="BTCUSDT",
        side="BUY",
        reduce_only=False,
        strategy_id="aurora",
        decision_ts_ms=1_700_000_000_999,
        why_chain=["regime_confidence_audit"],
        config=cfg,
        clock=MagicMock(now_ms=MagicMock(return_value=1_700_000_000_999)),
        symbol_states={"BTCUSDT": {"_delta_price_hist": deque([1.0], maxlen=20)}},
        per_symbol_regimes={"BTCUSDT": _regime_cache_snapshot(confidence="0.30")},
        system_stress_states={},
    )
    assert result.outcome == "DENY"
    assert result.deny_reason == NormalizedRejectReasons.INSUFFICIENT_TREND_CONFIRMATION


def test_3_nrr027_not_enforced() -> None:
    cfg = _fresh_config()
    cfg.strategies.aurora.safety_gates.enabled = True
    cfg.domains.decision_making.directional_sanity.enabled = True
    cfg.domains.decision_making.directional_sanity.consecutive_bars = 2
    cfg.domains.decision_making.directional_sanity.hard_veto_consecutive_bars = 2
    cfg.domains.decision_making.price_motion_sanity.enabled = False

    # LONG side with DOWN trend, run length 5 -> would trigger NRR-027 if enabled
    # We use confidence 0.30 so that it is between min (0.20) and max (0.40) for TREND_DOWN
    result = apply_safety_gates(
        symbol="BTCUSDT",
        side="BUY",
        reduce_only=False,
        strategy_id="aurora",
        decision_ts_ms=1_700_000_000_999,
        why_chain=["directional_veto_audit"],
        config=cfg,
        clock=MagicMock(now_ms=MagicMock(return_value=1_700_000_000_999)),
        symbol_states={"BTCUSDT": {"_delta_price_hist": deque([-1.0, -1.0, -1.0, -1.0, -1.0], maxlen=20)}},
        per_symbol_regimes={"BTCUSDT": _regime_cache_snapshot(confidence="0.30", regime="TREND_DOWN")},
        system_stress_states={},
    )
    assert result.outcome == "ALLOW"
    assert result.nrr027_enabled is False
    assert result.nrr027_effective_enforced is False


def test_4_nrr028_enforces_when_enabled() -> None:
    cfg = _fresh_config()
    cfg.strategies.aurora.safety_gates.enabled = True
    cfg.domains.decision_making.directional_sanity.enabled = False
    cfg.domains.decision_making.price_motion_sanity.enabled = True
    cfg.domains.decision_making.price_motion_sanity.nrr028_enabled = True

    # Missing price motion data triggers NRR-028
    result = apply_safety_gates(
        symbol="BTCUSDT",
        side="BUY",
        reduce_only=False,
        strategy_id="aurora",
        decision_ts_ms=1_700_000_000_999,
        why_chain=["price_motion_audit"],
        config=cfg,
        clock=MagicMock(now_ms=MagicMock(return_value=1_700_000_000_999)),
        symbol_states={"BTCUSDT": {}}, # no features/price_motion sub-dict
        per_symbol_regimes={"BTCUSDT": _regime_cache_snapshot(confidence="0.30")},
        system_stress_states={},
    )
    assert result.outcome == "DENY"
    assert result.deny_reason == NormalizedRejectReasons.PRICE_MOTION_INSUFFICIENT
    assert result.nrr028_enabled is True
    assert result.nrr028_effective_enforced is True


def test_5_nrr029_not_enforced() -> None:
    cfg = _fresh_config()
    cfg.strategies.aurora.safety_gates.enabled = True
    cfg.domains.decision_making.directional_sanity.enabled = False
    cfg.domains.decision_making.price_motion_sanity.enabled = True
    cfg.domains.decision_making.price_motion_sanity.nrr028_enabled = True
    cfg.domains.decision_making.price_motion_sanity.nrr029_enabled = False # disabled NRR-029

    # Flash window return is -2.0, flash threshold is 1.0 -> flash block long
    # (Since NRR-029 is disabled, it should allow)
    result = apply_safety_gates(
        symbol="BTCUSDT",
        side="BUY",
        reduce_only=False,
        strategy_id="aurora",
        decision_ts_ms=1_700_000_000_999,
        why_chain=["price_motion_audit"],
        config=cfg,
        clock=MagicMock(now_ms=MagicMock(return_value=1_700_000_000_999)),
        symbol_states={
            "BTCUSDT": {
                "features": {
                    "price_motion": {
                        "pm_norm_10s": 0.0,
                        "pm_norm_60s": -2.0, # flash down blocks long
                        "pm_norm_300s": 0.0,
                        "vol_pct_10s": 0.01,
                        "vol_pct_60s": 0.01,
                        "vol_pct_300s": 0.01,
                        "ret_60s": -0.02,
                        "ret_300s": 0.0,
                    }
                }
            }
        },
        per_symbol_regimes={"BTCUSDT": _regime_cache_snapshot(confidence="0.30")},
        system_stress_states={},
    )
    assert result.outcome == "ALLOW"
    assert result.nrr029_enabled is False
    assert result.nrr029_effective_enforced is False


def test_6_nrr030_not_enforced() -> None:
    cfg = _fresh_config()
    cfg.strategies.aurora.safety_gates.enabled = True
    cfg.domains.decision_making.directional_sanity.enabled = False
    cfg.domains.decision_making.price_motion_sanity.enabled = True
    cfg.domains.decision_making.price_motion_sanity.nrr028_enabled = True
    cfg.domains.decision_making.price_motion_sanity.nrr030_enabled = False # disabled NRR-030

    # Bleed window return is -1.0, bleed threshold is 0.5 -> bleed block long
    # (Since NRR-030 is disabled, it should allow)
    result = apply_safety_gates(
        symbol="BTCUSDT",
        side="BUY",
        reduce_only=False,
        strategy_id="aurora",
        decision_ts_ms=1_700_000_000_999,
        why_chain=["price_motion_audit"],
        config=cfg,
        clock=MagicMock(now_ms=MagicMock(return_value=1_700_000_000_999)),
        symbol_states={
            "BTCUSDT": {
                "features": {
                    "price_motion": {
                        "pm_norm_10s": 0.0,
                        "pm_norm_60s": 0.0,
                        "pm_norm_300s": -1.0, # bleed down blocks long
                        "vol_pct_10s": 0.01,
                        "vol_pct_60s": 0.01,
                        "vol_pct_300s": 0.01,
                        "ret_60s": 0.0,
                        "ret_300s": -0.01,
                    }
                }
            }
        },
        per_symbol_regimes={"BTCUSDT": _regime_cache_snapshot(confidence="0.30")},
        system_stress_states={},
    )
    assert result.outcome == "ALLOW"
    assert result.nrr030_enabled is False
    assert result.nrr030_effective_enforced is False


def test_7_telemetry_fields_emitted_correctly() -> None:
    cfg = _fresh_config()
    cfg.strategies.aurora.safety_gates.enabled = True
    cfg.domains.decision_making.directional_sanity.enabled = True
    cfg.domains.decision_making.price_motion_sanity.enabled = True

    result = apply_safety_gates(
        symbol="BTCUSDT",
        side="BUY",
        reduce_only=False,
        strategy_id="aurora",
        decision_ts_ms=1_700_000_000_999,
        why_chain=[],
        config=cfg,
        clock=MagicMock(now_ms=MagicMock(return_value=1_700_000_000_999)),
        symbol_states={
            "BTCUSDT": {
                "_delta_price_hist": deque([1.0, 1.0], maxlen=20),
                "features": {
                    "price_motion": {
                        "pm_norm_10s": 0.0,
                        "pm_norm_60s": 0.0,
                        "pm_norm_300s": 0.0,
                        "vol_pct_10s": 0.01,
                        "vol_pct_60s": 0.01,
                        "vol_pct_300s": 0.01,
                        "ret_60s": 0.0,
                        "ret_300s": 0.0,
                    }
                }
            }
        },
        per_symbol_regimes={"BTCUSDT": _regime_cache_snapshot(confidence="0.30")},
        system_stress_states={},
    )
    assert result.nrr026_enabled is True
    assert result.nrr027_enabled is False
    assert result.nrr028_enabled is True
    assert result.nrr029_enabled is False
    assert result.nrr030_enabled is False


def test_8_missing_fields_validation_error() -> None:
    with pytest.raises(ValidationError):
        PriceMotionSanityConfig(
            enabled=True,
            k_vol=2.0,
            flash_window_sec=60,
            bleed_window_sec=300,
            flash_threshold_norm=1.0,
            bleed_threshold_norm=0.5,
            require_bleed_ready=True,
            pm_norm_clip_abs=10.0,
            # Missing new required fields
        )


def test_9_nrr063_unchanged() -> None:
    cfg = _fresh_config()
    cfg.strategies.aurora.safety_gates.enabled = True
    cfg.domains.decision_making.directional_sanity.enabled = True
    cfg.domains.decision_making.directional_sanity.max_regime_confidence_by_regime = {"TREND_UP": 0.43}
    cfg.domains.decision_making.price_motion_sanity.enabled = False

    # regime confidence 0.50 > max 0.43 -> NRR-063
    result = apply_safety_gates(
        symbol="BTCUSDT",
        side="BUY",
        reduce_only=False,
        strategy_id="aurora",
        decision_ts_ms=1_700_000_000_999,
        why_chain=[],
        config=cfg,
        clock=MagicMock(now_ms=MagicMock(return_value=1_700_000_000_999)),
        symbol_states={"BTCUSDT": {"_delta_price_hist": deque([1.0], maxlen=20)}},
        per_symbol_regimes={"BTCUSDT": _regime_cache_snapshot(confidence="0.50", regime="TREND_UP")},
        system_stress_states={},
    )
    assert result.outcome == "DENY"
    assert result.deny_reason == NormalizedRejectReasons.REGIME_CONFIDENCE_ABOVE_MAX
    assert result.nrr063_enabled is True
    assert result.nrr063_effective_enforced is True


def test_10_low_vol_cost_floor_unchanged() -> None:
    cfg = _fresh_config()
    # Default config has it disabled
    assert cfg.domains.decision_making.low_vol_cost_floor_gate.enabled is False
    assert cfg.domains.decision_making.low_vol_cost_floor_gate.decision_chain_enabled is False
