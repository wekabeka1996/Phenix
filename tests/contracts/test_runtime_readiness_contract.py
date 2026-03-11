from apps.reference.contracts.runtime_readiness import (
    READINESS_SCOPE_OWNERS,
    RuntimeReadinessScope,
    make_permissions,
    make_snapshot,
    ready_status,
)


def test_owner_map_covers_all_canonical_scopes() -> None:
    expected = {scope.value for scope in RuntimeReadinessScope}
    assert set(READINESS_SCOPE_OWNERS.keys()) == expected


def test_snapshot_serializes_permissions_and_reason_chain() -> None:
    permissions = make_permissions(
        can_manage_existing_risk=True,
        can_open_new_risk=False,
    )
    snapshot = make_snapshot(
        strategy_id="md_amr",
        symbol="BTCUSDT",
        updated_at=1_700_000_000_000,
        scopes={
            RuntimeReadinessScope.STRATEGY_READY_PER_SYMBOL.value: ready_status(
                why=["signal_emitted:full_close"],
                updated_at=1_700_000_000_000,
                source="decision_making:md_amr",
                evidence_ref="rid-1",
            )
        },
        source="decision_making:md_amr",
        permissions=permissions,
        blocking_reason_chain=["protect_only"],
    )

    payload = snapshot.to_payload()

    assert payload["permissions"]["can_manage_existing_risk"] is True
    assert payload["permissions"]["can_open_new_risk"] is False
    assert payload["permissions"]["mode"] == "PROTECT_ONLY"
    assert payload["blocking_reason_chain"] == ["protect_only"]
    assert payload["scopes"]["strategy_ready_per_symbol"]["why"] == ["signal_emitted:full_close"]
