"""
Unit Tests for Execution Position Config (SSOT)

RID: EP-CONFIG-SSOT-S1

Test Coverage:
1. Happy-path: Valid config with all fields → ExecutionPositionConfig
2. Defaults: Missing fields use model defaults
3. Validation errors: Invalid values (sl_pct <= 0, tp_rr <= 0, etc.)
4. Nested structures: Watchdog, grace config
5. Path resolution: Primary vs. fallback paths
"""

import pytest
from pydantic import ValidationError

from apps.reference.domains.execution_position.config import (
    ExecutionPositionConfig,
    AggregatedOcoConfig,
    AggregatedOcoWatchdogConfig,
    AggregatedOcoWatchdogGraceConfig,
    TrailingConfig,
    CloseConfig,
)
from apps.reference.config.execution_position import resolve_execution_position_config


# ============================================================================
# Model Tests (Direct Instantiation)
# ============================================================================

def test_aggregated_oco_config_valid():
    """Test: Valid AggregatedOcoConfig with all fields"""
    cfg = AggregatedOcoConfig(
        enabled=True,
        aggregated_only_mode=True,
        sl_pct=0.02,
        tp_rr=2.0,
        recalc_on_scale_in=True,
        recalc_on_partial_close=True,
        ttl_protect_new_bracket_ms=5000,
        allow_unprotected_position=False,
        max_sl_legs=2,
        max_tp_legs=3,
    )

    assert cfg.enabled is True
    assert cfg.sl_pct == 0.02
    assert cfg.tp_rr == 2.0
    assert cfg.max_sl_legs == 2
    assert cfg.max_tp_legs == 3


def test_aggregated_oco_config_defaults():
    """Test: AggregatedOcoConfig with defaults"""
    cfg = AggregatedOcoConfig()

    # Check defaults match manage_config.py
    assert cfg.enabled is False
    assert cfg.aggregated_only_mode is False
    assert cfg.sl_pct == 0.02
    assert cfg.tp_rr == 2.0
    assert cfg.recalc_on_scale_in is True
    assert cfg.recalc_on_partial_close is False
    assert cfg.ttl_protect_new_bracket_ms == 3000
    assert cfg.allow_unprotected_position is False
    assert cfg.max_sl_legs == 1
    assert cfg.max_tp_legs == 1


def test_aggregated_oco_config_invalid_sl_pct():
    """Test: sl_pct <= 0 raises ValidationError"""
    with pytest.raises(ValidationError, match="greater than 0"):
        AggregatedOcoConfig(sl_pct=0.0, tp_rr=2.0)

    with pytest.raises(ValidationError, match="greater than 0"):
        AggregatedOcoConfig(sl_pct=-0.01, tp_rr=2.0)


def test_aggregated_oco_config_invalid_tp_rr():
    """Test: tp_rr <= 0 raises ValidationError"""
    with pytest.raises(ValidationError, match="greater than 0"):
        AggregatedOcoConfig(sl_pct=0.02, tp_rr=0.0)

    with pytest.raises(ValidationError, match="greater than 0"):
        AggregatedOcoConfig(sl_pct=0.02, tp_rr=-1.0)


def test_aggregated_oco_config_sl_pct_too_large():
    """Test: sl_pct > 1.0 (100%) raises ValidationError with custom message"""
    with pytest.raises(ValidationError, match="sl_pct=.* is > 100%"):
        AggregatedOcoConfig(sl_pct=2.0, tp_rr=2.0)


def test_aggregated_oco_config_tp_rr_too_small():
    """Test: tp_rr < 0.1 raises ValidationError"""
    with pytest.raises(ValidationError, match="tp_rr=.* is too small"):
        AggregatedOcoConfig(sl_pct=0.02, tp_rr=0.05)


def test_aggregated_oco_config_tp_rr_too_large():
    """Test: tp_rr > 100 raises ValidationError"""
    with pytest.raises(ValidationError, match="tp_rr=.* is too large"):
        AggregatedOcoConfig(sl_pct=0.02, tp_rr=150.0)


def test_trailing_config_valid():
    """Test: Valid TrailingConfig"""
    cfg = TrailingConfig(
        enabled=True,
        trail_distance_bps=200.0,
        activate_after_bps=50.0,
        breakeven_rr=1.5,
        hard_time_exit_sec=3600.0,
    )

    assert cfg.enabled is True
    assert cfg.trail_distance_bps == 200.0
    assert cfg.activate_after_bps == 50.0
    assert cfg.breakeven_rr == 1.5
    assert cfg.hard_time_exit_sec == 3600.0


def test_trailing_config_defaults():
    """Test: TrailingConfig with defaults"""
    cfg = TrailingConfig()

    assert cfg.enabled is False
    assert cfg.trail_distance_bps == 100.0
    assert cfg.activate_after_bps == 0.0
    assert cfg.breakeven_rr == 0.0
    assert cfg.hard_time_exit_sec is None
    assert cfg.activation_profit_atr_k == 1.0
    assert cfg.cooldown_sec == 0.0
    assert cfg.step_bps == 0.0


def test_trailing_config_invalid_trail_distance():
    """Test: trail_distance_bps < 0 raises ValidationError"""
    with pytest.raises(ValidationError, match="greater than or equal to 0"):
        TrailingConfig(trail_distance_bps=-10.0)


def test_trailing_config_invalid_hard_time_exit():
    """Test: hard_time_exit_sec < 0 raises ValidationError"""
    with pytest.raises(ValidationError, match="greater than or equal to 0"):
        TrailingConfig(hard_time_exit_sec=-1.0)


def test_close_config_valid():
    """Test: Valid CloseConfig"""
    cfg = CloseConfig(
        max_hold_time_sec=7200,
        reason_policy="strict",
        allow_time_exit=False,
        allow_profit_exit=True,
    )

    assert cfg.max_hold_time_sec == 7200
    assert cfg.reason_policy == "strict"
    assert cfg.allow_time_exit is False
    assert cfg.allow_profit_exit is True


def test_close_config_defaults():
    """Test: CloseConfig with defaults"""
    cfg = CloseConfig()

    assert cfg.max_hold_time_sec == 0
    assert cfg.reason_policy == "default"
    assert cfg.allow_time_exit is True
    assert cfg.allow_profit_exit is True


def test_close_config_invalid_max_hold_time():
    """Test: max_hold_time_sec < 0 raises ValidationError"""
    with pytest.raises(ValidationError, match="greater than or equal to 0"):
        CloseConfig(max_hold_time_sec=-1)


def test_close_config_invalid_reason_policy():
    """Test: Unknown reason_policy raises ValidationError"""
    with pytest.raises(ValidationError, match="reason_policy='invalid' not in"):
        CloseConfig(reason_policy="invalid")


def test_execution_position_config_valid():
    """Test: Valid ExecutionPositionConfig with all nested configs"""
    cfg = ExecutionPositionConfig(
        aggregated_oco=AggregatedOcoConfig(sl_pct=0.03, tp_rr=3.0),
        trailing=TrailingConfig(trail_distance_bps=150.0),
        close=CloseConfig(max_hold_time_sec=3600),
    )

    assert cfg.aggregated_oco.sl_pct == 0.03
    assert cfg.aggregated_oco.tp_rr == 3.0
    assert cfg.trailing.trail_distance_bps == 150.0
    assert cfg.close.max_hold_time_sec == 3600


# ============================================================================
# Resolver Tests (YAML → ExecutionPositionConfig)
# ============================================================================

def test_resolver_happy_path():
    """Test: Resolver with valid YAML config"""
    raw_cfg = {
        "manage": {
            "brackets": {
                "aggregated_oco": {
                    "enabled": True,
                    "aggregated_only_mode": True,
                    "sl_pct": 0.025,
                    "tp_rr": 2.5,
                    "recalc_on_scale_in": False,
                    "recalc_on_partial_close": True,
                    "ttl_protect_new_bracket_ms": 4000,
                    "allow_unprotected_position": True,
                    "max_sl_legs": 3,
                    "max_tp_legs": 2,
                    "watchdog": {
                        "enabled": True,
                        "interval_sec": 10,
                        "auto_heal_orphans": False,
                        "grace": {
                            "enabled": True,
                            "period_sec": 3.0,
                            "kinds": ["NO_SL_FOR_OPEN_POSITION"],
                        },
                    },
                },
            },
            "trailing": {
                "enabled": True,
                "trail_distance_bps": 200.0,
                "activate_after_bps": 50.0,
                "breakeven_rr": 1.0,
                "hard_time_exit_sec": 7200.0,
            },
            "close": {
                "max_hold_time_sec": 10800,
                "reason_policy": "strict",
                "allow_time_exit": False,
            },
        },
    }

    ep_cfg = resolve_execution_position_config(raw_cfg)

    # Check aggregated_oco
    assert ep_cfg.aggregated_oco.enabled is True
    assert ep_cfg.aggregated_oco.sl_pct == 0.025
    assert ep_cfg.aggregated_oco.tp_rr == 2.5
    assert ep_cfg.aggregated_oco.max_sl_legs == 3
    assert ep_cfg.aggregated_oco.watchdog.enabled is True
    assert ep_cfg.aggregated_oco.watchdog.interval_sec == 10
    assert ep_cfg.aggregated_oco.watchdog.grace.enabled is True
    assert ep_cfg.aggregated_oco.watchdog.grace.period_sec == 3.0
    assert ep_cfg.aggregated_oco.watchdog.grace.kinds == [
        "NO_SL_FOR_OPEN_POSITION"]

    # Check trailing
    assert ep_cfg.trailing.enabled is True
    assert ep_cfg.trailing.trail_distance_bps == 200.0
    assert ep_cfg.trailing.hard_time_exit_sec == 7200.0

    # Check close
    assert ep_cfg.close.max_hold_time_sec == 10800
    assert ep_cfg.close.reason_policy == "strict"


def test_resolver_defaults():
    """Test: Resolver with empty config uses defaults"""
    raw_cfg = {}

    ep_cfg = resolve_execution_position_config(raw_cfg)

    # Should match model defaults
    assert ep_cfg.aggregated_oco.enabled is False
    assert ep_cfg.aggregated_oco.sl_pct == 0.02
    assert ep_cfg.aggregated_oco.tp_rr == 2.0
    assert ep_cfg.trailing.enabled is False
    assert ep_cfg.trailing.trail_distance_bps == 100.0
    assert ep_cfg.close.max_hold_time_sec == 0


def test_resolver_partial_config():
    """Test: Resolver with partial config (missing fields use defaults)"""
    raw_cfg = {
        "manage": {
            "brackets": {
                "aggregated_oco": {
                    "enabled": True,
                    "sl_pct": 0.03,
                    # tp_rr missing → should use default 2.0
                },
            },
            # trailing missing → should use all defaults
        },
    }

    ep_cfg = resolve_execution_position_config(raw_cfg)

    assert ep_cfg.aggregated_oco.enabled is True
    assert ep_cfg.aggregated_oco.sl_pct == 0.03
    assert ep_cfg.aggregated_oco.tp_rr == 2.0  # Default
    assert ep_cfg.trailing.enabled is False  # Default


def test_resolver_fallback_path():
    """Test: Resolver with fallback flat path (brackets.aggregated_oco instead of manage.brackets.aggregated_oco)"""
    raw_cfg = {
        "brackets": {
            "aggregated_oco": {
                "enabled": True,
                "sl_pct": 0.04,
                "tp_rr": 3.0,
            },
        },
        "trailing": {
            "enabled": True,
            "trail_distance_bps": 250.0,
        },
    }

    ep_cfg = resolve_execution_position_config(raw_cfg)

    assert ep_cfg.aggregated_oco.enabled is True
    assert ep_cfg.aggregated_oco.sl_pct == 0.04
    assert ep_cfg.trailing.enabled is True
    assert ep_cfg.trailing.trail_distance_bps == 250.0


def test_resolver_invalid_sl_pct():
    """Test: Resolver raises ValidationError for invalid sl_pct"""
    raw_cfg = {
        "manage": {
            "brackets": {
                "aggregated_oco": {
                    "sl_pct": 0.0,  # Invalid: must be > 0
                    "tp_rr": 2.0,
                },
            },
        },
    }

    with pytest.raises(ValidationError, match="greater than 0"):
        resolve_execution_position_config(raw_cfg)


def test_resolver_invalid_tp_rr():
    """Test: Resolver raises ValidationError for invalid tp_rr"""
    raw_cfg = {
        "manage": {
            "brackets": {
                "aggregated_oco": {
                    "sl_pct": 0.02,
                    "tp_rr": -1.0,  # Invalid: must be > 0
                },
            },
        },
    }

    with pytest.raises(ValidationError, match="greater than 0"):
        resolve_execution_position_config(raw_cfg)


def test_resolver_coercion():
    """Test: Resolver coerces string/int values to correct types"""
    raw_cfg = {
        "manage": {
            "brackets": {
                "aggregated_oco": {
                    "enabled": "true",  # String → bool
                    "sl_pct": "0.025",  # String → float
                    "tp_rr": 3,  # Int → float
                    "ttl_protect_new_bracket_ms": "5000",  # String → int
                },
            },
        },
    }

    ep_cfg = resolve_execution_position_config(raw_cfg)

    assert ep_cfg.aggregated_oco.enabled is True
    assert ep_cfg.aggregated_oco.sl_pct == 0.025
    assert ep_cfg.aggregated_oco.tp_rr == 3.0
    assert ep_cfg.aggregated_oco.ttl_protect_new_bracket_ms == 5000


# ============================================================================
# Immutability Tests
# ============================================================================

def test_config_immutability():
    """Test: All configs are immutable (frozen=True)"""
    cfg = ExecutionPositionConfig(
        aggregated_oco=AggregatedOcoConfig(),
        trailing=TrailingConfig(),
        close=CloseConfig(),
    )

    # Try to mutate → should raise ValidationError
    with pytest.raises(ValidationError, match="Instance is frozen"):
        cfg.aggregated_oco.sl_pct = 0.05  # type: ignore

    with pytest.raises(ValidationError, match="Instance is frozen"):
        cfg.trailing.enabled = True  # type: ignore


# ============================================================================
# Edge Cases
# ============================================================================

def test_watchdog_grace_empty_kinds():
    """Test: Watchdog grace with empty kinds list"""
    cfg = AggregatedOcoWatchdogGraceConfig(
        enabled=True,
        period_sec=2.0,
        kinds=[],
    )

    assert cfg.enabled is True
    assert cfg.kinds == []


def test_trailing_config_hard_time_exit_none():
    """Test: Trailing config with hard_time_exit_sec=None (disabled)"""
    cfg = TrailingConfig(hard_time_exit_sec=None)

    assert cfg.hard_time_exit_sec is None


def test_close_config_permissive_policy():
    """Test: CloseConfig with reason_policy='permissive'"""
    cfg = CloseConfig(reason_policy="permissive")

    assert cfg.reason_policy == "permissive"


# ============================================================================
# Summary
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
