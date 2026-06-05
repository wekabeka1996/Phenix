"""Pure-function builder for runtime readiness assembly.

Single callable: build_runtime_readiness(request) → RuntimeReadinessBuilderResult.

This module owns the shared 10-step readiness assembly sequence used by all
strategy handlers (Aurora, MD-AMR, Mean Reversion).  Strategy-specific alpha
semantics are injected through the request dataclass, not through switches
inside the builder.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Literal

from apps.reference.bootstrap.startup_warmup import (
    apply_startup_warmup_permission_overlay,
    startup_warmup_gate_tokens,
)
from apps.reference.contracts.runtime_analytics_restore import (
    RuntimeAnalyticsRestoreScope,
    StrategyAnalyticsRestoreSnapshot,
    lookup_restore_status,
    merge_restore_readiness_live_first,
    restore_execution_blocking_tokens,
    restore_status_to_readiness_status,
    combine_restore_permissions_live_first,
)
from apps.reference.contracts.runtime_bar_identity import CanonicalBarIdentity
from apps.reference.contracts.runtime_gap_policy import (
    RuntimeGapStatus,
    build_basis_bar_status_from_gap,
    build_trading_status_from_gap,
    gap_blocking_tokens,
    gap_blocks_open_new_risk,
)
from apps.reference.contracts.runtime_readiness import (
    RuntimePermissions,
    RuntimeReadinessScope,
    RuntimeReadinessState,
    RuntimeReadinessStatus,
    StrategyRuntimeReadinessSnapshot,
    cold_status,
    make_permissions,
    make_snapshot,
    partial_status,
    ready_status,
)

# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------

PermissionOverlay = Callable[
    [RuntimePermissions],
    tuple[RuntimePermissions, tuple[str, ...]],
]
"""Callback that receives current permissions and returns
(modified_permissions, extra_blocking_tokens).  Aurora uses this for
quadratic gating.  MR and MD-AMR pass None.
"""


@dataclass(frozen=True)
class RestoreScopeSpec:
    """Declarative mapping from a restore scope to a readiness target scope."""

    restore_scope: RuntimeAnalyticsRestoreScope
    target_scope: str
    mode: Literal["restore_only", "merge_live_first"]
    source: str
    evidence_ref: str | None
    restored_why: tuple[str, ...] = ()
    live_evidence_present: bool = True


@dataclass(frozen=True)
class RuntimeReadinessBuildRequest:
    """Everything the builder needs to produce a readiness snapshot."""

    strategy_id: str
    symbol: str
    updated_at: int
    source_prefix: str
    gap_status: RuntimeGapStatus | None
    restore_snapshot: StrategyAnalyticsRestoreSnapshot | None
    bar_identity: CanonicalBarIdentity | None
    base_can_open_new_risk: bool
    warmup_ready: bool
    regime_present: bool
    regime_ts_ms: int | None
    regime_ready_why: str
    regime_missing_why: str
    regime_live_source: str
    regime_ready_evidence_ref: str | None
    regime_missing_evidence_ref: str | None
    signal_evidence_ref: str | None
    strategy_ready_why: tuple[str, ...]
    restore_specs: tuple[RestoreScopeSpec, ...]
    extra_scopes: Mapping[str, RuntimeReadinessStatus] = field(
        default_factory=dict)
    permission_overlay: PermissionOverlay | None = None


@dataclass(frozen=True)
class RuntimeReadinessBuilderResult:
    """Immutable result of readiness assembly."""

    snapshot: StrategyRuntimeReadinessSnapshot
    permissions: RuntimePermissions
    blocking_reason_chain: tuple[str, ...]


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------

def build_runtime_readiness(
    request: RuntimeReadinessBuildRequest,
) -> RuntimeReadinessBuilderResult:
    """Shared readiness assembly — pure function, no side effects."""

    # ── 1. Base permissions ──────────────────────────────────────────
    base_permissions = make_permissions(
        can_manage_existing_risk=True,
        can_open_new_risk=(
            request.base_can_open_new_risk
            and not gap_blocks_open_new_risk(request.gap_status)
        ),
    )

    # ── 2. Merge with restore permissions (live-first) ───────────────
    runtime_permissions = combine_restore_permissions_live_first(
        base_permissions,
        request.restore_snapshot,
    )

    # ── 3. Blocking tokens from gap + restore ────────────────────────
    blocking: list[str] = list(gap_blocking_tokens(request.gap_status)) + list(
        restore_execution_blocking_tokens(request.restore_snapshot)
    )
    blocking = list(dict.fromkeys(blocking))

    # ── 4. Build live scopes ─────────────────────────────────────────
    scopes: dict[str, RuntimeReadinessStatus] = {}

    scopes[RuntimeReadinessScope.BASIS_BAR_READY.value] = (
        build_basis_bar_status_from_gap(
            request.gap_status,
            updated_at=request.updated_at,
            source="market_data:payload_bridge",
            evidence_ref=(
                request.bar_identity.to_ref()
                if request.bar_identity is not None
                else None
            ),
        )
    )

    scopes[RuntimeReadinessScope.MICROSTRUCTURE_READY.value] = (
        ready_status(
            why=["fe_warmup_full_ready"],
            updated_at=request.updated_at,
            source="feature_engineering:payload_bridge",
            evidence_ref=f"warmup:{request.symbol}:{request.updated_at}",
        )
        if request.warmup_ready
        else cold_status(
            why=["fe_warmup_not_ready"],
            updated_at=request.updated_at,
            source="feature_engineering:payload_bridge",
            evidence_ref=f"warmup:{request.symbol}:{request.updated_at}",
        )
    )

    scopes[RuntimeReadinessScope.STRATEGY_READY_PER_SYMBOL.value] = ready_status(
        why=list(request.strategy_ready_why),
        updated_at=request.updated_at,
        source=request.source_prefix,
        evidence_ref=request.signal_evidence_ref,
    )

    scopes[RuntimeReadinessScope.REGIME_READY.value] = (
        ready_status(
            why=[request.regime_ready_why],
            updated_at=request.regime_ts_ms if request.regime_ts_ms is not None else request.updated_at,
            source=request.regime_live_source,
            evidence_ref=request.regime_ready_evidence_ref,
        )
        if request.regime_present
        else partial_status(
            why=[request.regime_missing_why],
            updated_at=request.regime_ts_ms if request.regime_ts_ms is not None else request.updated_at,
            source=request.regime_live_source,
            evidence_ref=request.regime_missing_evidence_ref,
        )
    )

    # ── 5. Inject extra scopes (e.g. QUADRATIC_HTF_READY) ───────────
    for key, status in request.extra_scopes.items():
        scopes[key] = status

    # ── 6. Merge restore scopes ──────────────────────────────────────
    if request.restore_snapshot is not None:
        for spec in request.restore_specs:
            restore_st = lookup_restore_status(
                request.restore_snapshot,
                spec.restore_scope,
            )
            if spec.mode == "restore_only":
                scopes[spec.target_scope] = restore_status_to_readiness_status(
                    restore_st,
                    updated_at=request.updated_at,
                    source=spec.source,
                    evidence_ref=spec.evidence_ref,
                    restored_why=list(
                        spec.restored_why) if spec.restored_why else None,
                )
            else:  # merge_live_first
                scopes[spec.target_scope] = merge_restore_readiness_live_first(
                    restore_st,
                    live_status=scopes.get(spec.target_scope),
                    updated_at=request.updated_at,
                    source=spec.source,
                    evidence_ref=spec.evidence_ref,
                    restored_why=list(
                        spec.restored_why) if spec.restored_why else None,
                    live_evidence_present=spec.live_evidence_present,
                )

    # ── 7. Permission overlay (e.g. quadratic gate) ──────────────────
    if request.permission_overlay is not None:
        runtime_permissions, overlay_tokens = request.permission_overlay(
            runtime_permissions,
        )
        blocking.extend(overlay_tokens)
        blocking = list(dict.fromkeys(blocking))

    # ── 8. Startup warmup overlay ────────────────────────────────────
    runtime_permissions = apply_startup_warmup_permission_overlay(
        runtime_permissions,
    )
    blocking.extend(startup_warmup_gate_tokens())
    blocking = list(dict.fromkeys(blocking))

    # ── 9. protect_only dedup ────────────────────────────────────────
    if runtime_permissions.can_manage_existing_risk and not runtime_permissions.can_open_new_risk:
        blocking.append("protect_only")
        blocking = list(dict.fromkeys(blocking))

    # ── 10. Final TRADING_READY (uses final permissions) ─────────────
    scopes[RuntimeReadinessScope.TRADING_READY.value] = (
        build_trading_status_from_gap(
            request.gap_status,
            updated_at=request.updated_at,
            source=request.source_prefix,
            evidence_ref=request.signal_evidence_ref,
            allow_open_new_risk=runtime_permissions.can_open_new_risk,
            open_ready_why=["open_new_risk_allowed"],
            blocked_why=blocking,
        )
    )

    # ── 11. Build snapshot ───────────────────────────────────────────
    snapshot = make_snapshot(
        strategy_id=request.strategy_id,
        symbol=request.symbol,
        updated_at=request.updated_at,
        scopes=scopes,
        source=request.source_prefix,
        permissions=runtime_permissions,
        blocking_reason_chain=blocking,
    )

    return RuntimeReadinessBuilderResult(
        snapshot=snapshot,
        permissions=runtime_permissions,
        blocking_reason_chain=tuple(blocking),
    )
