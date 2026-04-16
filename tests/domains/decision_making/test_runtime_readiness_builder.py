"""Unit tests for runtime_readiness_builder — golden fixture matrix.

Covers:
  clear_gap, blocked_gap, restore_only, merge_live_first,
  startup_warmup_overlay, protect_only_dedup,
  aurora_quadratic_extension, md_amr_base_can_open_false,
  mr_bugfix_baseline (BUG-1 source, BUG-2 COLD).
"""
from __future__ import annotations

from unittest.mock import patch

from apps.reference.bootstrap.startup_warmup import (
    activate_startup_warmup_gate,
    release_startup_warmup_gate,
)
from apps.reference.contracts.runtime_analytics_restore import (
    RuntimeAnalyticsRestoreScope,
    cold_restore_status,
    make_strategy_restore_snapshot,
    restored_restore_status,
)
from apps.reference.contracts.runtime_bar_identity import (
    RuntimeBarSourceMode,
    build_canonical_bar_identity,
)
from apps.reference.contracts.runtime_gap_policy import (
    RuntimeGapPolicyAction,
    RuntimeGapState,
    RuntimeGapStatus,
)
from apps.reference.contracts.runtime_readiness import (
    RuntimePermissions,
    RuntimeReadinessScope,
    RuntimeReadinessState,
    cold_status,
    make_permissions,
    partial_status,
    ready_status,
)
from apps.reference.domains.decision_making.runtime_readiness_builder import (
    PermissionOverlay,
    RestoreScopeSpec,
    RuntimeReadinessBuildRequest,
    RuntimeReadinessBuilderResult,
    build_runtime_readiness,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TS = 1_700_000_000_000
SYMBOL = "BTCUSDT"


def _bar_identity():
    return build_canonical_bar_identity(
        symbol=SYMBOL,
        timeframe_sec=300,
        bar_start_ts_ms=TS - 300_000,
        close_boundary_ts_ms=TS,
        source_mode=RuntimeBarSourceMode.LIVE,
    )


def _base_request(**overrides) -> RuntimeReadinessBuildRequest:
    defaults = dict(
        strategy_id="aurora",
        symbol=SYMBOL,
        updated_at=TS,
        source_prefix="decision_making:aurora",
        gap_status=None,
        restore_snapshot=None,
        bar_identity=_bar_identity(),
        base_can_open_new_risk=True,
        warmup_ready=True,
        regime_present=True,
        regime_ts_ms=TS,
        regime_ready_why="regime_detected",
        regime_missing_why="regime_absent",
        regime_live_source="regime_detector:payload_bridge",
        regime_ready_evidence_ref=f"regime:{SYMBOL}:{TS}",
        regime_missing_evidence_ref=f"regime:{SYMBOL}:{TS}",
        signal_evidence_ref=f"rid:test:{TS}",
        strategy_ready_why=("signal_emitted",),
        restore_specs=(),
    )
    defaults.update(overrides)
    return RuntimeReadinessBuildRequest(**defaults)


def _make_restore_snapshot(
    *,
    strategy_id: str = "aurora",
    has_open_position: bool = False,
    scopes: dict | None = None,
) -> object:
    default_scopes = {
        RuntimeAnalyticsRestoreScope.EXECUTION_STATE.value: restored_restore_status(
            why=["execution_snapshot_loaded"],
            updated_at=TS,
            source="execution_position:startup_restore",
            evidence_ref=f"execution:{SYMBOL}:{TS}",
        ),
        RuntimeAnalyticsRestoreScope.FEATURE_ENGINEERING_CACHE.value: cold_restore_status(
            why=["fe_cache_restore_missing"],
            updated_at=TS,
            source="feature_engineering:startup_restore",
            evidence_ref=f"fe_cache:{SYMBOL}:{TS}",
        ),
        RuntimeAnalyticsRestoreScope.REGIME_DETECTOR_STATE.value: cold_restore_status(
            why=["regime_restore_missing"],
            updated_at=TS,
            source="regime_detector:startup_restore",
            evidence_ref=f"regime:{SYMBOL}:{TS}",
        ),
        RuntimeAnalyticsRestoreScope.STRATEGY_LOCAL_STATE.value: cold_restore_status(
            why=["strategy_local_restore_missing"],
            updated_at=TS,
            source="decision_making:startup_restore",
            evidence_ref=f"strategy_local:{SYMBOL}:{TS}",
        ),
    }
    if scopes is not None:
        default_scopes.update(scopes)
    return make_strategy_restore_snapshot(
        strategy_id=strategy_id,
        symbol=SYMBOL,
        updated_at=TS,
        scopes=default_scopes,
        source="startup:test",
        has_open_position=has_open_position,
    )


# ---------------------------------------------------------------------------
# Golden: clear_gap — happy path, no restore, no warmup gate
# ---------------------------------------------------------------------------


def test_clear_gap_happy_path():
    result = build_runtime_readiness(_base_request())

    assert isinstance(result, RuntimeReadinessBuilderResult)
    snap = result.snapshot
    assert snap.strategy_id == "aurora"
    assert snap.symbol == SYMBOL

    # Permissions: full open-and-manage
    assert result.permissions.can_open_new_risk is True
    assert result.permissions.can_manage_existing_risk is True
    assert result.permissions.mode == "OPEN_AND_MANAGE"

    # Scopes: all present and READY
    scopes = snap.scopes
    assert scopes[RuntimeReadinessScope.BASIS_BAR_READY.value].state == RuntimeReadinessState.READY
    assert scopes[RuntimeReadinessScope.MICROSTRUCTURE_READY.value].state == RuntimeReadinessState.READY
    assert scopes[RuntimeReadinessScope.STRATEGY_READY_PER_SYMBOL.value].state == RuntimeReadinessState.READY
    assert scopes[RuntimeReadinessScope.REGIME_READY.value].state == RuntimeReadinessState.READY
    assert scopes[RuntimeReadinessScope.TRADING_READY.value].state == RuntimeReadinessState.READY

    # No blocking
    assert "protect_only" not in result.blocking_reason_chain


# ---------------------------------------------------------------------------
# Golden: blocked_gap — basis invalidated, protect_only
# ---------------------------------------------------------------------------


def test_blocked_gap():
    gap = RuntimeGapStatus(
        state=RuntimeGapState.INVALIDATED,
        policy_action=RuntimeGapPolicyAction.DEGRADE_TO_NON_TRADING,
        gap_bars_skipped=5,
        is_gap_bar=True,
        why=["basis_bar_invalidated"],
        source="gap_detector:live",
    )
    result = build_runtime_readiness(_base_request(gap_status=gap))

    assert result.permissions.can_open_new_risk is False
    assert result.permissions.can_manage_existing_risk is True
    assert "protect_only" in result.blocking_reason_chain
    # protect_only appears exactly once
    assert result.blocking_reason_chain.count("protect_only") == 1

    scopes = result.snapshot.scopes
    assert scopes[RuntimeReadinessScope.TRADING_READY.value].state == RuntimeReadinessState.BLOCKED


# ---------------------------------------------------------------------------
# Golden: restore_only — execution restore, no live evidence for merged scope
# ---------------------------------------------------------------------------


def test_restore_only():
    snap = _make_restore_snapshot(has_open_position=True)
    req = _base_request(
        restore_snapshot=snap,
        restore_specs=(
            RestoreScopeSpec(
                restore_scope=RuntimeAnalyticsRestoreScope.EXECUTION_STATE,
                target_scope=RuntimeReadinessScope.EXECUTION_CONTEXT_READY.value,
                mode="restore_only",
                source="execution_position:startup_restore",
                evidence_ref=f"rid:test:{TS}",
            ),
        ),
    )
    result = build_runtime_readiness(req)

    scopes = result.snapshot.scopes
    assert RuntimeReadinessScope.EXECUTION_CONTEXT_READY.value in scopes
    exec_scope = scopes[RuntimeReadinessScope.EXECUTION_CONTEXT_READY.value]
    assert exec_scope.state == RuntimeReadinessState.READY


# ---------------------------------------------------------------------------
# Golden: merge_live_first — live readiness overrides cold restore
# ---------------------------------------------------------------------------


def test_merge_live_first():
    snap = _make_restore_snapshot(has_open_position=True)
    req = _base_request(
        warmup_ready=True,
        restore_snapshot=snap,
        restore_specs=(
            RestoreScopeSpec(
                restore_scope=RuntimeAnalyticsRestoreScope.FEATURE_ENGINEERING_CACHE,
                target_scope=RuntimeReadinessScope.MICROSTRUCTURE_READY.value,
                mode="merge_live_first",
                source="feature_engineering:startup_restore",
                evidence_ref=f"rid:test:{TS}",
                live_evidence_present=True,
            ),
            RestoreScopeSpec(
                restore_scope=RuntimeAnalyticsRestoreScope.REGIME_DETECTOR_STATE,
                target_scope=RuntimeReadinessScope.REGIME_READY.value,
                mode="merge_live_first",
                source="regime_detector:startup_restore",
                evidence_ref=f"rid:test:{TS}",
                live_evidence_present=True,
            ),
        ),
    )
    result = build_runtime_readiness(req)

    scopes = result.snapshot.scopes
    # Live READY overrides cold restore
    assert scopes[RuntimeReadinessScope.MICROSTRUCTURE_READY.value].state == RuntimeReadinessState.READY
    assert scopes[RuntimeReadinessScope.REGIME_READY.value].state == RuntimeReadinessState.READY


# ---------------------------------------------------------------------------
# Golden: startup_warmup_overlay — manage yes, open no
# ---------------------------------------------------------------------------


def test_startup_warmup_overlay():
    activate_startup_warmup_gate(updated_at=TS, source="startup:test")
    try:
        result = build_runtime_readiness(_base_request())
    finally:
        release_startup_warmup_gate()

    assert result.permissions.can_manage_existing_risk is True
    assert result.permissions.can_open_new_risk is False
    assert "startup_warmup_in_progress" in result.blocking_reason_chain


# ---------------------------------------------------------------------------
# Golden: protect_only_dedup — only one protect_only in chain
# ---------------------------------------------------------------------------


def test_protect_only_dedup():
    gap = RuntimeGapStatus(
        state=RuntimeGapState.INVALIDATED,
        policy_action=RuntimeGapPolicyAction.DEGRADE_TO_NON_TRADING,
        gap_bars_skipped=2,
        is_gap_bar=True,
        why=["basis_bar_invalidated"],
        source="gap_detector:live",
    )
    snap = _make_restore_snapshot(has_open_position=True)
    req = _base_request(
        gap_status=gap,
        restore_snapshot=snap,
        restore_specs=(
            RestoreScopeSpec(
                restore_scope=RuntimeAnalyticsRestoreScope.EXECUTION_STATE,
                target_scope=RuntimeReadinessScope.EXECUTION_CONTEXT_READY.value,
                mode="restore_only",
                source="execution_position:startup_restore",
                evidence_ref=f"rid:test:{TS}",
            ),
        ),
    )
    result = build_runtime_readiness(req)

    count = result.blocking_reason_chain.count("protect_only")
    assert count == 1, f"Expected exactly 1 protect_only, got {count}"


# ---------------------------------------------------------------------------
# Golden: aurora_quadratic_extension — overlay + extra scopes
# ---------------------------------------------------------------------------


def test_aurora_quadratic_extension():
    def quadratic_overlay(perms: RuntimePermissions):
        new_perms = make_permissions(
            can_manage_existing_risk=perms.can_manage_existing_risk,
            can_open_new_risk=False,
        )
        return new_perms, ("quadratic_htf_not_ready",)

    quad_htf_scope = ready_status(
        why=["pillar_state_live"],
        updated_at=TS,
        source="decision_making:aurora",
        evidence_ref=f"pillar:{SYMBOL}:{TS}",
    )

    req = _base_request(
        permission_overlay=quadratic_overlay,
        extra_scopes={
            RuntimeReadinessScope.QUADRATIC_HTF_READY.value: quad_htf_scope,
        },
    )
    result = build_runtime_readiness(req)

    assert result.permissions.can_open_new_risk is False
    assert "quadratic_htf_not_ready" in result.blocking_reason_chain
    assert "protect_only" in result.blocking_reason_chain

    scopes = result.snapshot.scopes
    assert RuntimeReadinessScope.QUADRATIC_HTF_READY.value in scopes


# ---------------------------------------------------------------------------
# Golden: md_amr_base_can_open_false — reduce-only signal
# ---------------------------------------------------------------------------


def test_md_amr_base_can_open_false():
    req = _base_request(
        strategy_id="md_amr",
        source_prefix="decision_making:md_amr",
        base_can_open_new_risk=False,
    )
    result = build_runtime_readiness(req)

    assert result.permissions.can_open_new_risk is False
    assert result.permissions.can_manage_existing_risk is True
    assert "protect_only" in result.blocking_reason_chain


# ---------------------------------------------------------------------------
# Golden: mr_bugfix_baseline — BUG-1 source, BUG-2 COLD
# ---------------------------------------------------------------------------


def test_mr_bugfix_regime_source():
    """BUG-1: regime source must be regime_live_source, not strategy source."""
    req = _base_request(
        strategy_id="mean_reversion",
        source_prefix="decision_making:mean_reversion",
        regime_live_source="regime_detector:payload_bridge",
        regime_present=True,
    )
    result = build_runtime_readiness(req)

    regime = result.snapshot.scopes[RuntimeReadinessScope.REGIME_READY.value]
    assert regime.source == "regime_detector:payload_bridge"


def test_mr_bugfix_cold_microstructure():
    """BUG-2: when warmup not ready, MICROSTRUCTURE_READY state is COLD."""
    req = _base_request(
        strategy_id="mean_reversion",
        source_prefix="decision_making:mean_reversion",
        warmup_ready=False,
    )
    result = build_runtime_readiness(req)

    micro = result.snapshot.scopes[RuntimeReadinessScope.MICROSTRUCTURE_READY.value]
    assert micro.state == RuntimeReadinessState.COLD


# ---------------------------------------------------------------------------
# Structural: frozen types
# ---------------------------------------------------------------------------


def test_result_is_frozen():
    result = build_runtime_readiness(_base_request())
    import pytest

    with pytest.raises(AttributeError):
        result.permissions = None  # type: ignore[misc]


def test_request_is_frozen():
    req = _base_request()
    import pytest

    with pytest.raises(AttributeError):
        req.strategy_id = "x"  # type: ignore[misc]


def test_restore_scope_spec_is_frozen():
    spec = RestoreScopeSpec(
        restore_scope=RuntimeAnalyticsRestoreScope.EXECUTION_STATE,
        target_scope="execution_context_ready",
        mode="restore_only",
        source="test",
        evidence_ref=None,
    )
    import pytest

    with pytest.raises(AttributeError):
        spec.mode = "merge_live_first"  # type: ignore[misc]
