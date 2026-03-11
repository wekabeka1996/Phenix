from decimal import Decimal
from types import SimpleNamespace

from apps.reference.bootstrap.runtime_analytics_restore import (
    build_startup_analytics_restore_report,
)
from apps.reference.contracts.runtime_analytics_restore import (
    RuntimeAnalyticsRestoreScope,
    restored_restore_status,
)


class _MDAMRRestoreStub:
    def describe_runtime_analytics_restore(self, symbol: str):
        return {
            RuntimeAnalyticsRestoreScope.STRATEGY_LOCAL_STATE.value: restored_restore_status(
                why=["md_amr_rest_hydration"],
                updated_at=1_700_000_000_000,
                source="decision_making:md_amr_rest_hydration",
                evidence_ref=f"md_amr_rest:{symbol}:1700000000000",
            ).to_payload()
        }


def _config():
    return SimpleNamespace(
        strategies_registry=SimpleNamespace(
            assignments={
                "BTCUSDT": ["aurora", "mean_reversion"],
                "XRPUSDT": ["md_amr"],
            }
        )
    )


def test_startup_report_marks_execution_restored_but_analytics_cold_as_protect_only() -> None:
    report = build_startup_analytics_restore_report(
        config=_config(),
        snapshot_data={"timestamp_utc": "2026-03-11T12:00:00+00:00"},
        positions={"BTCUSDT": {"quantity": Decimal("1.25")}},
        strategy_handlers={},
        snapshot_loaded=True,
        updated_at=1_700_000_000_000,
        source="startup:test",
    )

    snapshot = report.get_snapshot("aurora", "BTCUSDT")
    assert snapshot is not None
    assert snapshot.rollup_state.value == "PARTIAL"
    assert snapshot.permissions.mode == "PROTECT_ONLY"
    assert snapshot.scopes["execution_state"].state.value == "RESTORED"
    assert snapshot.scopes["feature_engineering_cache"].state.value == "COLD"
    assert "analytics_restore_partial" in snapshot.blocking_reason_chain


def test_startup_report_accepts_explicit_analytics_restore_payload() -> None:
    explicit_snapshot = {
        "strategy_id": "aurora",
        "symbol": "BTCUSDT",
        "updated_at": 1_700_000_000_000,
        "source": "startup:snapshot",
        "scopes": {
            scope.value: {
                "state": "RESTORED",
                "why": [f"{scope.value}_restored"],
                "updated_at": 1_700_000_000_000,
                "source": "startup:snapshot",
                "evidence_ref": f"{scope.value}:BTCUSDT:1700000000000",
            }
            for scope in RuntimeAnalyticsRestoreScope
        },
    }
    report = build_startup_analytics_restore_report(
        config=_config(),
        snapshot_data={"analytics_restore": {"snapshots": [explicit_snapshot]}},
        positions={},
        strategy_handlers={},
        snapshot_loaded=True,
        updated_at=1_700_000_000_000,
        source="startup:test",
    )

    snapshot = report.get_snapshot("aurora", "BTCUSDT")
    assert snapshot is not None
    assert snapshot.rollup_state.value == "RESTORED"
    assert snapshot.permissions.can_open_new_risk is True
    assert snapshot.scopes["pillar_state"].state.value == "RESTORED"


def test_startup_report_keeps_md_amr_local_restore_visible_but_partial() -> None:
    report = build_startup_analytics_restore_report(
        config=_config(),
        snapshot_data={"timestamp_utc": "2026-03-11T12:00:00+00:00"},
        positions={},
        strategy_handlers={"md_amr": _MDAMRRestoreStub()},
        snapshot_loaded=False,
        updated_at=1_700_000_000_000,
        source="startup:test",
    )

    snapshot = report.get_snapshot("md_amr", "XRPUSDT")
    assert snapshot is not None
    assert snapshot.rollup_state.value == "PARTIAL"
    assert snapshot.permissions.can_open_new_risk is False
    assert snapshot.scopes["strategy_local_state"].state.value == "RESTORED"
    assert snapshot.scopes["feature_engineering_cache"].state.value == "COLD"
