"""Tests for vfoundation.core.ttl — Phase 1.6."""
from __future__ import annotations

from vfoundation.core.ttl import TTL_PROFILES, DEFAULT_PROFILE


def test_profiles_contain_expected_keys() -> None:
    expected = {"critical", "fast", "normal", "ml_slow", "background"}
    assert expected == set(TTL_PROFILES.keys())


def test_profile_values_ascending() -> None:
    order = ["critical", "fast", "normal", "ml_slow", "background"]
    values = [TTL_PROFILES[k] for k in order]
    assert values == sorted(values), "TTL profiles should be in ascending order"


def test_all_values_positive() -> None:
    for name, ms in TTL_PROFILES.items():
        assert ms > 0, f"{name} TTL must be positive"


def test_default_profile_exists() -> None:
    assert DEFAULT_PROFILE in TTL_PROFILES


def test_critical_le_fast() -> None:
    assert TTL_PROFILES["critical"] <= TTL_PROFILES["fast"]
