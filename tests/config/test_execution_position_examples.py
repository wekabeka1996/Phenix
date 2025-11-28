"""
Roundtrip Tests for Execution Position Config Examples

RID: EP-CONFIG-SAMPLES-S3

Tests that example YAML configs (safe/moderate/aggressive) load correctly
into ExecutionPositionConfig and satisfy all invariants.

Coverage:
- Load YAML → resolve → ExecutionPositionConfig (no ValidationError)
- Verify all validators pass (sl_pct, tp_rr, bps >= 0, etc.)
- Check profile-specific properties (safe=conservative, aggressive=high RR)
"""

import pytest
import yaml
from pathlib import Path
from pydantic import ValidationError

from apps.reference.config.execution_position import resolve_execution_position_config
from apps.reference.domains.execution_position.config import ExecutionPositionConfig


# Path to example configs
# __file__ = tests/config/test_*.py → parents[2] = project root
EXAMPLES_DIR = Path(__file__).parents[2] / "config" / "examples"


def load_yaml_example(filename: str) -> dict:
    """Load YAML example file from config/examples/"""
    yaml_path = EXAMPLES_DIR / filename
    assert yaml_path.exists(), f"Example file not found: {yaml_path}"

    with open(yaml_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    return data if isinstance(data, dict) else {}


def test_safe_profile_loads_successfully():
    """Test: SAFE profile YAML loads without errors"""
    raw_cfg = load_yaml_example("execution_position_safe.yaml")

    # Should not raise ValidationError
    ep_cfg = resolve_execution_position_config(raw_cfg)

    assert isinstance(ep_cfg, ExecutionPositionConfig)
    assert ep_cfg.aggregated_oco is not None
    assert ep_cfg.trailing is not None
    assert ep_cfg.close is not None


def test_moderate_profile_loads_successfully():
    """Test: MODERATE profile YAML loads without errors"""
    raw_cfg = load_yaml_example("execution_position_moderate.yaml")

    ep_cfg = resolve_execution_position_config(raw_cfg)

    assert isinstance(ep_cfg, ExecutionPositionConfig)
    assert ep_cfg.aggregated_oco is not None
    assert ep_cfg.trailing is not None
    assert ep_cfg.close is not None


def test_aggressive_profile_loads_successfully():
    """Test: AGGRESSIVE profile YAML loads without errors"""
    raw_cfg = load_yaml_example("execution_position_aggressive.yaml")

    ep_cfg = resolve_execution_position_config(raw_cfg)

    assert isinstance(ep_cfg, ExecutionPositionConfig)
    assert ep_cfg.aggregated_oco is not None
    assert ep_cfg.trailing is not None
    assert ep_cfg.close is not None


# ==============================================================================
# Invariant Tests: Core Validators
# ==============================================================================

def test_safe_profile_satisfies_core_invariants():
    """Test: SAFE profile satisfies all core invariants"""
    raw_cfg = load_yaml_example("execution_position_safe.yaml")
    ep_cfg = resolve_execution_position_config(raw_cfg)

    # Aggregated OCO invariants
    assert 0 < ep_cfg.aggregated_oco.sl_pct < 1.0, "sl_pct must be in (0, 1.0)"
    assert 0.1 <= ep_cfg.aggregated_oco.tp_rr <= 100.0, "tp_rr must be in [0.1, 100]"
    assert ep_cfg.aggregated_oco.max_sl_legs >= 1, "max_sl_legs >= 1"
    assert ep_cfg.aggregated_oco.max_tp_legs >= 1, "max_tp_legs >= 1"
    assert ep_cfg.aggregated_oco.ttl_protect_new_bracket_ms >= 0, "ttl >= 0"

    # Trailing invariants
    assert ep_cfg.trailing.trail_distance_bps >= 0.0, "trail_distance_bps >= 0"
    assert ep_cfg.trailing.activate_after_bps >= 0.0, "activate_after_bps >= 0"
    if ep_cfg.trailing.hard_time_exit_sec is not None:
        assert ep_cfg.trailing.hard_time_exit_sec >= 0.0, "hard_time_exit_sec >= 0"

    # Close invariants
    assert ep_cfg.close.max_hold_time_sec >= 0, "max_hold_time_sec >= 0"


def test_moderate_profile_satisfies_core_invariants():
    """Test: MODERATE profile satisfies all core invariants"""
    raw_cfg = load_yaml_example("execution_position_moderate.yaml")
    ep_cfg = resolve_execution_position_config(raw_cfg)

    # Same invariants as safe
    assert 0 < ep_cfg.aggregated_oco.sl_pct < 1.0
    assert 0.1 <= ep_cfg.aggregated_oco.tp_rr <= 100.0
    assert ep_cfg.aggregated_oco.max_sl_legs >= 1
    assert ep_cfg.aggregated_oco.max_tp_legs >= 1
    assert ep_cfg.aggregated_oco.ttl_protect_new_bracket_ms >= 0

    assert ep_cfg.trailing.trail_distance_bps >= 0.0
    assert ep_cfg.trailing.activate_after_bps >= 0.0
    if ep_cfg.trailing.hard_time_exit_sec is not None:
        assert ep_cfg.trailing.hard_time_exit_sec >= 0.0

    assert ep_cfg.close.max_hold_time_sec >= 0


def test_aggressive_profile_satisfies_core_invariants():
    """Test: AGGRESSIVE profile satisfies all core invariants"""
    raw_cfg = load_yaml_example("execution_position_aggressive.yaml")
    ep_cfg = resolve_execution_position_config(raw_cfg)

    # Same invariants
    assert 0 < ep_cfg.aggregated_oco.sl_pct < 1.0
    assert 0.1 <= ep_cfg.aggregated_oco.tp_rr <= 100.0
    assert ep_cfg.aggregated_oco.max_sl_legs >= 1
    assert ep_cfg.aggregated_oco.max_tp_legs >= 1
    assert ep_cfg.aggregated_oco.ttl_protect_new_bracket_ms >= 0

    assert ep_cfg.trailing.trail_distance_bps >= 0.0
    assert ep_cfg.trailing.activate_after_bps >= 0.0
    if ep_cfg.trailing.hard_time_exit_sec is not None:
        assert ep_cfg.trailing.hard_time_exit_sec >= 0.0

    assert ep_cfg.close.max_hold_time_sec >= 0


# ==============================================================================
# Profile-Specific Characteristics
# ==============================================================================

def test_safe_profile_is_conservative():
    """Test: SAFE profile has conservative characteristics"""
    raw_cfg = load_yaml_example("execution_position_safe.yaml")
    ep_cfg = resolve_execution_position_config(raw_cfg)

    # Conservative: wider SL (> 1.2%), lower RR (< 2.0)
    assert ep_cfg.aggregated_oco.sl_pct >= 0.012, "SAFE should have wider SL (≥ 1.2%)"
    assert ep_cfg.aggregated_oco.tp_rr <= 2.0, "SAFE should have moderate RR (≤ 2.0)"

    # Strict bracket enforcement
    assert ep_cfg.aggregated_oco.allow_unprotected_position is False, "SAFE should not allow unprotected positions"

    # Conservative legs (1-2)
    assert ep_cfg.aggregated_oco.max_sl_legs <= 2, "SAFE should have max 2 SL legs"
    assert ep_cfg.aggregated_oco.max_tp_legs <= 2, "SAFE should have max 2 TP legs"


def test_moderate_profile_is_balanced():
    """Test: MODERATE profile has balanced characteristics"""
    raw_cfg = load_yaml_example("execution_position_moderate.yaml")
    ep_cfg = resolve_execution_position_config(raw_cfg)

    # Balanced: standard SL (1.5-2.5%), good RR (1.5-2.5)
    assert 0.015 <= ep_cfg.aggregated_oco.sl_pct <= 0.025, "MODERATE should have standard SL (1.5-2.5%)"
    assert 1.5 <= ep_cfg.aggregated_oco.tp_rr <= 2.5, "MODERATE should have good RR (1.5-2.5)"

    # Moderate legs (2-3)
    assert ep_cfg.aggregated_oco.max_sl_legs <= 3, "MODERATE should have max 3 SL legs"
    assert ep_cfg.aggregated_oco.max_tp_legs <= 4, "MODERATE should have max 4 TP legs"


def test_aggressive_profile_is_high_risk():
    """Test: AGGRESSIVE profile has high-risk characteristics"""
    raw_cfg = load_yaml_example("execution_position_aggressive.yaml")
    ep_cfg = resolve_execution_position_config(raw_cfg)

    # Aggressive: tight SL (< 1.5%), high RR (> 2.5)
    assert ep_cfg.aggregated_oco.sl_pct <= 0.015, "AGGRESSIVE should have tight SL (≤ 1.5%)"
    assert ep_cfg.aggregated_oco.tp_rr >= 2.5, "AGGRESSIVE should have high RR (≥ 2.5)"

    # Aggressive legs (3+)
    assert ep_cfg.aggregated_oco.max_sl_legs >= 2, "AGGRESSIVE should have ≥ 2 SL legs"
    assert ep_cfg.aggregated_oco.max_tp_legs >= 3, "AGGRESSIVE should have ≥ 3 TP legs"


# ==============================================================================
# Trailing-Specific Tests
# ==============================================================================

def test_safe_profile_trailing_is_tight():
    """Test: SAFE profile has tight trailing stop"""
    raw_cfg = load_yaml_example("execution_position_safe.yaml")
    ep_cfg = resolve_execution_position_config(raw_cfg)

    # Tight trailing (≤ 100 bps)
    assert ep_cfg.trailing.trail_distance_bps <= 100.0, "SAFE should have tight trailing (≤ 100 bps)"


def test_moderate_profile_trailing_is_balanced():
    """Test: MODERATE profile has balanced trailing stop"""
    raw_cfg = load_yaml_example("execution_position_moderate.yaml")
    ep_cfg = resolve_execution_position_config(raw_cfg)

    # Balanced trailing (80-120 bps)
    assert 80.0 <= ep_cfg.trailing.trail_distance_bps <= 120.0, "MODERATE should have balanced trailing (80-120 bps)"


def test_aggressive_profile_trailing_is_wide():
    """Test: AGGRESSIVE profile has wide trailing stop"""
    raw_cfg = load_yaml_example("execution_position_aggressive.yaml")
    ep_cfg = resolve_execution_position_config(raw_cfg)

    # Wide trailing (≥ 120 bps)
    assert ep_cfg.trailing.trail_distance_bps >= 120.0, "AGGRESSIVE should have wide trailing (≥ 120 bps)"


# ==============================================================================
# Watchdog Configuration Tests
# ==============================================================================

def test_all_profiles_have_watchdog_enabled():
    """Test: All profiles have watchdog enabled for safety"""
    for profile in ["safe", "moderate", "aggressive"]:
        raw_cfg = load_yaml_example(f"execution_position_{profile}.yaml")
        ep_cfg = resolve_execution_position_config(raw_cfg)

        assert ep_cfg.aggregated_oco.watchdog is not None, f"{profile}: watchdog should exist"
        assert ep_cfg.aggregated_oco.watchdog.enabled is True, f"{profile}: watchdog should be enabled"
        assert ep_cfg.aggregated_oco.watchdog.grace is not None, f"{profile}: watchdog grace should exist"
        assert ep_cfg.aggregated_oco.watchdog.grace.enabled is True, f"{profile}: watchdog grace should be enabled"


def test_aggressive_profile_has_shortest_watchdog_interval():
    """Test: AGGRESSIVE profile has the shortest watchdog interval"""
    safe_cfg = resolve_execution_position_config(
        load_yaml_example("execution_position_safe.yaml"))
    moderate_cfg = resolve_execution_position_config(
        load_yaml_example("execution_position_moderate.yaml"))
    aggressive_cfg = resolve_execution_position_config(
        load_yaml_example("execution_position_aggressive.yaml"))

    # Aggressive should have shortest interval (most frequent checks)
    assert aggressive_cfg.aggregated_oco.watchdog.interval_sec <= moderate_cfg.aggregated_oco.watchdog.interval_sec
    assert aggressive_cfg.aggregated_oco.watchdog.interval_sec <= safe_cfg.aggregated_oco.watchdog.interval_sec


# ==============================================================================
# Immutability Tests
# ==============================================================================

def test_all_profiles_are_immutable():
    """Test: All example configs produce immutable ExecutionPositionConfig"""
    for profile in ["safe", "moderate", "aggressive"]:
        raw_cfg = load_yaml_example(f"execution_position_{profile}.yaml")
        ep_cfg = resolve_execution_position_config(raw_cfg)

        # Try to mutate → should raise ValidationError
        with pytest.raises(ValidationError, match="Instance is frozen"):
            ep_cfg.aggregated_oco.sl_pct = 0.05  # type: ignore


# ==============================================================================
# Summary Test
# ==============================================================================

def test_all_profiles_summary():
    """Test: Summary of all profiles (for documentation)"""
    profiles = {}

    for profile_name in ["safe", "moderate", "aggressive"]:
        raw_cfg = load_yaml_example(f"execution_position_{profile_name}.yaml")
        ep_cfg = resolve_execution_position_config(raw_cfg)

        profiles[profile_name] = {
            "sl_pct": ep_cfg.aggregated_oco.sl_pct,
            "tp_rr": ep_cfg.aggregated_oco.tp_rr,
            "trail_distance_bps": ep_cfg.trailing.trail_distance_bps,
            "max_sl_legs": ep_cfg.aggregated_oco.max_sl_legs,
            "max_tp_legs": ep_cfg.aggregated_oco.max_tp_legs,
            "watchdog_interval_sec": ep_cfg.aggregated_oco.watchdog.interval_sec,
        }

    # Print summary for docs
    print("\n=== Execution Position Config Profiles ===")
    for name, props in profiles.items():
        print(f"\n{name.upper()}:")
        print(
            f"  SL: {props['sl_pct'] * 100:.1f}%, TP RR: {props['tp_rr']:.1f}x")
        print(f"  Trailing: {props['trail_distance_bps']:.0f} bps")
        print(f"  Legs: {props['max_sl_legs']} SL / {props['max_tp_legs']} TP")
        print(f"  Watchdog: {props['watchdog_interval_sec']}s interval")

    # All profiles should be distinct
    assert profiles["safe"]["sl_pct"] > profiles["aggressive"]["sl_pct"]
    assert profiles["safe"]["tp_rr"] < profiles["aggressive"]["tp_rr"]


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short", "-s"])
