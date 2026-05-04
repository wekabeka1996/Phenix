from apps.reference.contracts.runtime_analytics_restore import (
    RuntimeAnalyticsRestoreScope,
    RuntimeAnalyticsRestoreState,
    combine_restore_permissions_live_first,
    cold_restore_status,
    invalidated_restore_status,
    make_strategy_restore_snapshot,
    merge_restore_readiness_live_first,
    partial_restore_status,
    restored_restore_status,
    restore_status_to_readiness_status,
)
from apps.reference.contracts.runtime_readiness import (
    RuntimeReadinessState,
    make_permissions,
    make_status,
    ready_status,
)


def test_strategy_restore_snapshot_serializes_counts_and_protect_only_permissions() -> None:
    snapshot = make_strategy_restore_snapshot(
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

    payload = snapshot.to_payload()

    assert payload["rollup_state"] == "PARTIAL"
    assert payload["permissions"]["mode"] == "PROTECT_ONLY"
    assert payload["counts"]["RESTORED"] == 1
    assert payload["counts"]["COLD"] == 1
    assert "protect_only" in payload["blocking_reason_chain"]


def test_restore_status_maps_to_readiness_states() -> None:
    readiness_partial = restore_status_to_readiness_status(
        partial_restore_status(
            why=["decision_cache_partial"],
            updated_at=1_700_000_000_000,
            source="decision_making:startup_restore",
            evidence_ref="decision_cache:BTCUSDT:1700000000000",
        ),
        updated_at=1_700_000_000_000,
        source="decision_making:test",
        evidence_ref="decision_cache:test",
    )
    readiness_invalidated = restore_status_to_readiness_status(
        invalidated_restore_status(
            why=["analytics_gap_invalidated"],
            updated_at=1_700_000_000_000,
            source="startup:test",
            evidence_ref="gap:BTCUSDT:1700000000000",
        ),
        updated_at=1_700_000_000_000,
        source="decision_making:test",
        evidence_ref="gap:test",
    )

    assert readiness_partial.state.value == "PARTIAL"
    assert readiness_invalidated.state.value == "INVALIDATED_GAP"


def test_fully_restored_snapshot_allows_open_new_risk() -> None:
    scopes = {
        scope.value: restored_restore_status(
            why=[f"{scope.value}_restored"],
            updated_at=1_700_000_000_000,
            source="startup:test",
            evidence_ref=f"{scope.value}:BTCUSDT:1700000000000",
        )
        for scope in RuntimeAnalyticsRestoreScope
    }
    snapshot = make_strategy_restore_snapshot(
        strategy_id="mean_reversion",
        symbol="BTCUSDT",
        updated_at=1_700_000_000_000,
        scopes=scopes,
        source="startup:test",
        has_open_position=False,
    )

    assert snapshot.rollup_state == RuntimeAnalyticsRestoreState.RESTORED
    assert snapshot.permissions.can_open_new_risk is True
    assert snapshot.permissions.mode == "OPEN_AND_MANAGE"


def test_live_first_merge_preserves_ready_over_cold_restore() -> None:
    merged = merge_restore_readiness_live_first(
        cold_restore_status(
            why=["fe_cache_restore_missing"],
            updated_at=1_700_000_000_000,
            source="feature_engineering:startup_restore",
            evidence_ref="fe_cache:BTCUSDT:1700000000000",
        ),
        live_status=ready_status(
            why=["fe_warmup_full_ready"],
            updated_at=1_700_000_010_000,
            source="feature_engineering:payload_bridge",
            evidence_ref="warmup:BTCUSDT:1700000010000",
        ),
        updated_at=1_700_000_010_000,
        source="decision_making:test",
        evidence_ref="warmup:test",
        live_evidence_present=True,
    )

    assert merged.state.value == "READY"
    assert merged.why == ("fe_warmup_full_ready",)


def test_live_first_merge_preserves_invalidated_gap_over_restored() -> None:
    merged = merge_restore_readiness_live_first(
        restored_restore_status(
            why=["regime_restore_loaded"],
            updated_at=1_700_000_000_000,
            source="regime_detector:startup_restore",
            evidence_ref="regime:BTCUSDT:1700000000000",
        ),
        live_status=make_status(
            state=RuntimeReadinessState.INVALIDATED_GAP,
            why=["basis_bar_gap"],
            updated_at=1_700_000_020_000,
            source="market_data:payload_bridge",
            evidence_ref="gap:BTCUSDT:1700000020000",
        ),
        updated_at=1_700_000_020_000,
        source="decision_making:test",
        evidence_ref="gap:test",
        live_evidence_present=True,
    )

    assert merged.state.value == "INVALIDATED_GAP"
    assert merged.why == ("basis_bar_gap",)


def test_live_first_permissions_only_block_on_execution_restore() -> None:
    snapshot = make_strategy_restore_snapshot(
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

    permissions = combine_restore_permissions_live_first(
        make_permissions(
            can_manage_existing_risk=True,
            can_open_new_risk=True,
        ),
        snapshot,
    )

    assert permissions.can_manage_existing_risk is True
    assert permissions.can_open_new_risk is True
