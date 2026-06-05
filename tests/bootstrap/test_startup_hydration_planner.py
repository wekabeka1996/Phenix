from types import SimpleNamespace

from apps.reference.bootstrap.runtime_analytics_restore import (
    StartupAnalyticsRestoreReport,
    build_startup_analytics_restore_report,
)
from apps.reference.bootstrap.startup_hydration_planner import (
    build_startup_hydration_plan,
)
from apps.reference.contracts.runtime_analytics_restore import (
    RuntimeAnalyticsRestoreScope,
    make_strategy_restore_snapshot,
    restored_restore_status,
)


def _config(*, aurora_scoring_version: str = "v2"):
    return SimpleNamespace(
        strategies_registry=SimpleNamespace(
            assignments={
                "BTCUSDT": ["aurora", "mean_reversion"],
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


def _restore_report(config):
    return build_startup_analytics_restore_report(
        config=config,
        snapshot_data={"timestamp_utc": "2026-03-11T12:00:00+00:00"},
        positions={},
        strategy_handlers={},
        snapshot_loaded=False,
        updated_at=1_700_000_000_000,
        source="startup:test_restore",
    )


def test_planner_keeps_mean_reversion_isolated_from_quadratic_htf_requirements() -> None:
    config = _config(aurora_scoring_version="quadratic")
    report = _restore_report(config)

    plan_report = build_startup_hydration_plan(
        config=config,
        analytics_restore_report=report,
        updated_at=1_700_000_000_000,
        source="startup:test_planner",
    )
    mr_plan = plan_report.plans["mean_reversion:BTCUSDT"]

    assert mr_plan.requirement.strategy_id == "mean_reversion"
    assert mr_plan.requirement.compatibility_profile_id == "mean_reversion"
    assert mr_plan.requirement.required_htf == ()
    assert mr_plan.requirement.quadratic_readiness_blocks_by_default is False
    assert all(action.action != "IMPORT_HTF_BARS" for action in mr_plan.actions)


def test_planner_preserves_md_amr_local_hydration_contract() -> None:
    config = _config()
    report = _restore_report(config)

    plan_report = build_startup_hydration_plan(
        config=config,
        analytics_restore_report=report,
        updated_at=1_700_000_000_000,
        source="startup:test_planner",
    )
    md_plan = plan_report.plans["md_amr:XRPUSDT"]

    assert md_plan.requirement.compatibility_profile_id == "md_amr"
    assert md_plan.requirement.local_hydration_contract == "md_amr_rest_hydration"
    assert md_plan.requirement.restart_local_basis_counter is True
    assert md_plan.requirement.protect_only_capability is True
    assert any(action.action ==
               "USE_STRATEGY_LOCAL_HYDRATION" for action in md_plan.actions)
    assert any(action.action ==
               "SEED_HANDLER_BASIS_COUNTER" for action in md_plan.actions)
    assert all(action.action != "IMPORT_HTF_BARS" for action in md_plan.actions)


def test_planner_always_emits_htf_imports_for_quadratic_aurora() -> None:
    """Post Phase 9 cleanup: aurora profile is always quadratic, always needs HTF imports."""
    v2_config = _config(aurora_scoring_version="v2")
    quadratic_config = _config(aurora_scoring_version="quadratic")

    v2_plan = build_startup_hydration_plan(
        config=v2_config,
        analytics_restore_report=_restore_report(v2_config),
        updated_at=1_700_000_000_000,
        source="startup:test_planner",
    ).plans["aurora:BTCUSDT"]
    quadratic_plan = build_startup_hydration_plan(
        config=quadratic_config,
        analytics_restore_report=_restore_report(quadratic_config),
        updated_at=1_700_000_000_000,
        source="startup:test_planner",
    ).plans["aurora:BTCUSDT"]

    # Both resolve to aurora_quadratic (v2 kernel deleted)
    assert v2_plan.requirement.compatibility_profile_id == "aurora_quadratic"
    assert quadratic_plan.requirement.compatibility_profile_id == "aurora_quadratic"
    # Both need HTF imports
    assert {
        action.timeframe_sec
        for action in v2_plan.actions
        if action.action == "IMPORT_HTF_BARS"
    } == {900, 14400, 86400}
    assert {
        action.timeframe_sec
        for action in quadratic_plan.actions
        if action.action == "IMPORT_HTF_BARS"
    } == {900, 14400, 86400}


def test_planner_output_is_deterministic_for_identical_inputs() -> None:
    config = _config(aurora_scoring_version="quadratic")
    report = _restore_report(config)

    first = build_startup_hydration_plan(
        config=config,
        analytics_restore_report=report,
        updated_at=1_700_000_000_000,
        source="startup:test_planner",
    ).to_payload()
    second = build_startup_hydration_plan(
        config=config,
        analytics_restore_report=report,
        updated_at=1_700_000_000_000,
        source="startup:test_planner",
    ).to_payload()

    assert first == second


def test_planner_uses_only_active_strategy_symbols_from_compatibility_profiles() -> None:
    config = _config()
    config.strategies_registry.assignments = {
        "BTCUSDT": ["aurora"],
        "XRPUSDT": ["md_amr"],
    }
    report = _restore_report(config)

    plan_report = build_startup_hydration_plan(
        config=config,
        analytics_restore_report=report,
        updated_at=1_700_000_000_000,
        source="startup:test_planner",
    )

    assert set(plan_report.plans.keys()) == {
        "aurora:BTCUSDT", "md_amr:XRPUSDT"}


def test_planner_seeds_restart_local_basis_counter_even_when_bars_are_restored() -> None:
    config = _config(aurora_scoring_version="quadratic")
    restored = restored_restore_status(
        why=["test_restored"],
        updated_at=1_700_000_000_000,
        source="tests",
        evidence_ref="bars:test",
    )
    scopes = {
        scope.value: restored
        if scope == RuntimeAnalyticsRestoreScope.BARS
        else restored_restore_status(
            why=["test_restored"],
            updated_at=1_700_000_000_000,
            source="tests",
            evidence_ref=f"{scope.value}:test",
        )
        for scope in RuntimeAnalyticsRestoreScope
    }
    report = StartupAnalyticsRestoreReport(
        updated_at=1_700_000_000_000,
        source="startup:test_restore",
        snapshots={
            "aurora:BTCUSDT": make_strategy_restore_snapshot(
                strategy_id="aurora",
                symbol="BTCUSDT",
                updated_at=1_700_000_000_000,
                scopes=scopes,
                source="tests",
                has_open_position=False,
            ),
            "md_amr:XRPUSDT": make_strategy_restore_snapshot(
                strategy_id="md_amr",
                symbol="XRPUSDT",
                updated_at=1_700_000_000_000,
                scopes=scopes,
                source="tests",
                has_open_position=False,
            ),
            "mean_reversion:BTCUSDT": make_strategy_restore_snapshot(
                strategy_id="mean_reversion",
                symbol="BTCUSDT",
                updated_at=1_700_000_000_000,
                scopes=scopes,
                source="tests",
                has_open_position=False,
            ),
        },
    )

    plan_report = build_startup_hydration_plan(
        config=config,
        analytics_restore_report=report,
        updated_at=1_700_000_000_000,
        source="startup:test_planner",
    )

    aurora_actions = {action.action for action in plan_report.plans["aurora:BTCUSDT"].actions}
    md_actions = {action.action for action in plan_report.plans["md_amr:XRPUSDT"].actions}
    mr_actions = {action.action for action in plan_report.plans["mean_reversion:BTCUSDT"].actions}

    assert "RESTORE_OR_REPLAY_BASIS_BARS" not in aurora_actions
    assert "RESTORE_OR_REPLAY_BASIS_BARS" not in md_actions
    assert "SEED_HANDLER_BASIS_COUNTER" in aurora_actions
    assert "SEED_HANDLER_BASIS_COUNTER" in md_actions
    assert "SEED_HANDLER_BASIS_COUNTER" not in mr_actions
