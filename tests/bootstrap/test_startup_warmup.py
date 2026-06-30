from pathlib import Path
from types import SimpleNamespace

from apps.reference.bootstrap.runtime_analytics_restore import (
    StartupAnalyticsRestoreReport,
)
from apps.reference.bootstrap.startup_warmup import (
    activate_startup_warmup_gate,
    apply_startup_warmup_permission_overlay,
    build_startup_warmup_report,
    partial_warmup_status,
    release_startup_warmup_gate,
    resolve_feature_engineering_backfill_plan,
    startup_warmup_gate_tokens,
    warmed_warmup_status,
)
from apps.reference.contracts.runtime_analytics_restore import (
    RuntimeAnalyticsRestoreScope,
    cold_restore_status,
    make_strategy_restore_snapshot,
    restored_restore_status,
)
from apps.reference.contracts.runtime_readiness import make_permissions


def _config() -> SimpleNamespace:
    return SimpleNamespace(
        pillars=SimpleNamespace(
            backfill=SimpleNamespace(
                enabled=False,
                d1_candles=1,
                h4_candles=2,
                m15_candles=3,
            )
        ),
        strategies_registry=SimpleNamespace(
            assignments={
                "BTCUSDT": ["aurora", "mean_reversion"],
                "XRPUSDT": ["md_amr"],
            }
        ),
        strategies=SimpleNamespace(
            aurora=SimpleNamespace(
                timeframe_sec=300,
                decision=SimpleNamespace(scoring_version="v2"),
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
                        enabled=True,
                        d1_candles=200,
                        h4_candles=100,
                        m15_candles=50,
                    ),
                )
            )
        ),
        instruments={
            "BTCUSDT": object(),
            "XRPUSDT": object(),
        },
    )


def test_resolve_feature_engineering_backfill_plan_uses_domains_path() -> None:
    plan = resolve_feature_engineering_backfill_plan(_config())

    assert plan.config_path == "domains.feature_engineering.pillars.backfill"
    assert plan.enabled is True
    assert plan.d1_candles == 200
    assert plan.h4_candles == 100
    assert plan.m15_candles == 50


def test_startup_warmup_gate_overlay_blocks_only_new_risk() -> None:
    release_startup_warmup_gate()
    activate_startup_warmup_gate(
        updated_at=1_700_000_000_000,
        source="startup:test",
    )
    try:
        permissions = apply_startup_warmup_permission_overlay(
            make_permissions(
                can_manage_existing_risk=True,
                can_open_new_risk=True,
            )
        )

        assert permissions.can_manage_existing_risk is True
        assert permissions.can_open_new_risk is False
        assert startup_warmup_gate_tokens() == ("startup_warmup_in_progress",)
    finally:
        release_startup_warmup_gate()


def test_startup_warmup_report_keeps_restore_and_warmup_separate() -> None:
    restore_snapshot = make_strategy_restore_snapshot(
        strategy_id="aurora",
        symbol="BTCUSDT",
        updated_at=1_700_000_000_000,
        scopes={
            RuntimeAnalyticsRestoreScope.EXECUTION_STATE.value: restored_restore_status(
                why=["execution_snapshot_loaded"],
                updated_at=1_700_000_000_000,
                source="execution_position:startup_restore",
                evidence_ref="execution:BTCUSDT:1700000000000",
            ),
            RuntimeAnalyticsRestoreScope.FEATURE_ENGINEERING_CACHE.value: cold_restore_status(
                why=["fe_cache_restore_missing"],
                updated_at=1_700_000_000_000,
                source="feature_engineering:startup_restore",
                evidence_ref="fe_cache:BTCUSDT:1700000000000",
            ),
        },
        source="startup:test",
        has_open_position=True,
    )
    restore_report = StartupAnalyticsRestoreReport(
        updated_at=1_700_000_000_000,
        source="startup:test",
        snapshots={"aurora:BTCUSDT": restore_snapshot},
    )

    activate_startup_warmup_gate(
        updated_at=1_700_000_030_000,
        source="startup:test",
    )
    try:
        report = build_startup_warmup_report(
            config=_config(),
            analytics_restore_report=restore_report,
            warmup_statuses={
                "BTCUSDT": {
                    "feature_engineering": warmed_warmup_status(
                        why=["pillar_backfill_complete"],
                        updated_at=1_700_000_010_000,
                        source="main:startup_warmup",
                        evidence_ref="feature_engineering:BTCUSDT:1700000010000",
                    ),
                    "regime_detector": partial_warmup_status(
                        why=["regime_backfill_partial"],
                        updated_at=1_700_000_020_000,
                        source="main:startup_warmup",
                        evidence_ref="regime_detector:BTCUSDT:1700000020000",
                    ),
                }
            },
            updated_at=1_700_000_030_000,
            source="main:startup_warmup_report",
            gate_active=True,
        )
    finally:
        release_startup_warmup_gate()

    payload = report.to_payload()
    record = payload["records"]["aurora:BTCUSDT"]

    assert record["restore"]["rollup_state"] == "PARTIAL"
    assert record["warmup"]["feature_engineering"]["state"] == "WARMED"
    assert record["warmup"]["regime_detector"]["state"] == "PARTIAL"
    assert "startup_warmup_in_progress" in record["effective_blockers"]


def test_main_starts_regime_detector_before_market_data() -> None:
    source = (
        Path(__file__).resolve().parents[2] / "apps" / "reference" / "main.py"
    ).read_text(encoding="utf-8")

    assert source.index("regime_detector.start()") < source.index(
        "market_data.start_async()"
    )
