from types import SimpleNamespace

from apps.reference.contracts.strategy_compatibility_matrix import (
    active_aurora_profile_id,
    build_active_strategy_compatibility_profiles,
    build_full_strategy_compatibility_matrix,
)


def _config(*, aurora_scoring_version: str = "v2"):
    return SimpleNamespace(
        strategies_registry=SimpleNamespace(
            assignments={
                "BTCUSDT": ["aurora", "mean_reversion"],
                "DOGEUSDT": ["mean_reversion"],
                "XRPUSDT": ["md_amr"],
            }
        ),
        strategies=SimpleNamespace(
            aurora=SimpleNamespace(
                timeframe_sec=300,
                decision=SimpleNamespace(
                    scoring_version=aurora_scoring_version),
            ),
            mean_reversion=SimpleNamespace(
                timeframe_sec=300,
                strategy=SimpleNamespace(min_bars=25),
            ),
            md_amr=SimpleNamespace(
                timeframe_sec=900,
                channel_window_bars=12,
                atr_window=14,
                atr_stats_window=64,
            ),
        ),
        regime=SimpleNamespace(
            models=SimpleNamespace(
                sma_trend=SimpleNamespace(sma_long_period=192),
                volatility=SimpleNamespace(atr_period=14, atr_sma_length=288),
            )
        ),
        domains=SimpleNamespace(
            feature_engineering=SimpleNamespace(
                pillars=SimpleNamespace(
                    enabled=True,
                    backfill=SimpleNamespace(
                        m15_candles=50,
                        h4_candles=100,
                        d1_candles=200,
                    ),
                )
            )
        ),
    )


def test_active_aurora_profile_is_always_quadratic() -> None:
    # Post Phase 9 cleanup: aurora is always quadratic regardless of config scoring_version
    assert active_aurora_profile_id(
        _config(aurora_scoring_version="v2")) == "aurora_quadratic"
    assert active_aurora_profile_id(
        _config(aurora_scoring_version="quadratic")) == "aurora_quadratic"


def test_mean_reversion_remains_quadratic_htf_free_when_aurora_quadratic_active() -> None:
    matrix = build_full_strategy_compatibility_matrix(
        _config(aurora_scoring_version="quadratic"))
    mr_profile = matrix["mean_reversion"]

    assert mr_profile.required_htf == ()
    assert mr_profile.quadratic_readiness_blocks_by_default is False
    assert mr_profile.active_symbols == ("BTCUSDT", "DOGEUSDT")


def test_md_amr_keeps_local_hydration_contract_and_protect_only_capability() -> None:
    matrix = build_full_strategy_compatibility_matrix(_config())
    profile = matrix["md_amr"]

    assert profile.local_hydration_contract == "md_amr_rest_hydration"
    assert profile.protect_only_capability is True
    assert profile.quadratic_readiness_blocks_by_default is False
    assert profile.active_symbols == ("XRPUSDT",)


def test_aurora_quadratic_profile_declares_explicit_htf_requirements() -> None:
    matrix = build_full_strategy_compatibility_matrix(
        _config(aurora_scoring_version="quadratic"))
    profile = matrix["aurora_quadratic"]

    assert profile.active is True
    assert profile.quadratic_readiness_blocks_by_default is True
    assert {(item.timeframe_sec, item.required_bars) for item in profile.required_htf} == {
        (900, 50),
        (14400, 100),
        (86400, 200),
    }


def test_active_profiles_keep_single_aurora_truth() -> None:
    profiles = build_active_strategy_compatibility_profiles(
        _config(aurora_scoring_version="quadratic"))

    assert set(profiles.keys()) == {"aurora", "mean_reversion", "md_amr"}
    assert profiles["aurora"].profile_id == "aurora_quadratic"
    assert profiles["mean_reversion"].profile_id == "mean_reversion"
    assert profiles["md_amr"].profile_id == "md_amr"


def test_regime_dependent_strategies_require_minimum_basis_bars() -> None:
    config = _config(aurora_scoring_version="quadratic")
    matrix = build_full_strategy_compatibility_matrix(config)
    
    # structural regime requires max(192, 14 + 288 - 1) = 301 bars
    expected_min_bars = 301
    
    for profile in matrix.values():
        if profile.needs_regime:
            assert profile.basis_required_bars >= expected_min_bars, (
                f"Profile {profile.profile_id} needs regime but only requests "
                f"{profile.basis_required_bars} bars (expected >= {expected_min_bars})"
            )
