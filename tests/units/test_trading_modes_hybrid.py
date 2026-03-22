from types import SimpleNamespace

import pytest

from apps.reference.utils.trading_modes import (
    compute_effective_trading_modes,
    get_domain_mode_from_mapping,
)


def _make_hybrid_config() -> SimpleNamespace:
    return SimpleNamespace(
        trading_mode="hybrid_live_data_testnet_exec",
        trading=SimpleNamespace(mode="hybrid_live_data_testnet_exec"),
    )


@pytest.mark.parametrize(
    ("profile", "expected_mode"),
    [
        ("full_testnet", "testnet"),
        ("full_live", "live"),
        ("backtest", "backtest"),
    ],
)
def test_legacy_profiles_still_resolve(profile: str, expected_mode: str) -> None:
    config = SimpleNamespace(trading=SimpleNamespace(mode=profile))

    modes = compute_effective_trading_modes(config)

    assert modes.profile == profile
    assert modes.for_domain("market_data") == expected_mode
    assert get_domain_mode_from_mapping(config, "market_data") == expected_mode


def test_hybrid_profile_resolves_domain_specific_modes() -> None:
    config = _make_hybrid_config()

    modes = compute_effective_trading_modes(config)

    assert modes.profile == "hybrid_live_data_testnet_exec"
    assert modes.for_domain("market_data") == "live"
    assert modes.for_domain("feature_engineering") == "live"
    assert modes.for_domain("decision_making") == "live"
    assert modes.for_domain("risk_management") == "testnet"
    assert modes.for_domain("execution_position") == "testnet"
    assert modes.for_domain("audit_trail") == "live"
    assert get_domain_mode_from_mapping(config, "market_data") == "live"
    assert get_domain_mode_from_mapping(
        config, "execution_position") == "testnet"
