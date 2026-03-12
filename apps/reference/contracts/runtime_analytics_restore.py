from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Mapping

from apps.reference.contracts.runtime_readiness import (
    RuntimePermissions,
    RuntimeReadinessState,
    RuntimeReadinessStatus,
    cold_status,
    make_permissions,
    make_status,
    partial_status,
    ready_status,
)


class RuntimeAnalyticsRestoreState(str, Enum):
    RESTORED = "RESTORED"
    COLD = "COLD"
    PARTIAL = "PARTIAL"
    INVALIDATED_DUE_TO_GAP = "INVALIDATED_DUE_TO_GAP"


class RuntimeAnalyticsRestoreScope(str, Enum):
    BARS = "bars"
    PARTIAL_BAR = "partial_bar"
    FEATURE_ENGINEERING_LAST_BAR = "feature_engineering_last_bar"
    FEATURE_ENGINEERING_CACHE = "feature_engineering_cache"
    REGIME_DETECTOR_STATE = "regime_detector_state"
    PILLAR_STATE = "pillar_state"
    DECISION_CACHE = "decision_cache"
    STRATEGY_LOCAL_STATE = "strategy_local_state"
    EXECUTION_STATE = "execution_state"


def _normalize_why_tokens(why: str | Iterable[str] | None) -> tuple[str, ...]:
    if why is None:
        return ()
    if isinstance(why, str):
        value = why.strip()
        return (value,) if value else ()
    tokens: list[str] = []
    for token in why:
        value = str(token).strip()
        if value:
            tokens.append(value)
    return tuple(tokens)


def _count_states(scopes: Mapping[str, "RuntimeAnalyticsRestoreStatus"]) -> dict[str, int]:
    counts = {state.value: 0 for state in RuntimeAnalyticsRestoreState}
    for status in scopes.values():
        counts[status.state.value] = counts.get(status.state.value, 0) + 1
    return counts


def _resolve_rollup_state(
    scopes: Mapping[str, "RuntimeAnalyticsRestoreStatus"],
) -> RuntimeAnalyticsRestoreState:
    if not scopes:
        return RuntimeAnalyticsRestoreState.COLD
    states = [status.state for status in scopes.values()]
    if any(state == RuntimeAnalyticsRestoreState.INVALIDATED_DUE_TO_GAP for state in states):
        return RuntimeAnalyticsRestoreState.INVALIDATED_DUE_TO_GAP
    if all(state == RuntimeAnalyticsRestoreState.RESTORED for state in states):
        return RuntimeAnalyticsRestoreState.RESTORED
    if any(state in (RuntimeAnalyticsRestoreState.RESTORED, RuntimeAnalyticsRestoreState.PARTIAL) for state in states):
        return RuntimeAnalyticsRestoreState.PARTIAL
    return RuntimeAnalyticsRestoreState.COLD


def _default_blocking_reason_chain(
    *,
    rollup_state: RuntimeAnalyticsRestoreState,
    has_open_position: bool,
) -> tuple[str, ...]:
    tokens: list[str] = []
    if rollup_state == RuntimeAnalyticsRestoreState.COLD:
        tokens.append("analytics_restore_cold")
    elif rollup_state == RuntimeAnalyticsRestoreState.PARTIAL:
        tokens.append("analytics_restore_partial")
    elif rollup_state == RuntimeAnalyticsRestoreState.INVALIDATED_DUE_TO_GAP:
        tokens.append("analytics_restore_invalidated_gap")

    if rollup_state != RuntimeAnalyticsRestoreState.RESTORED:
        tokens.append("analytics_open_new_risk_blocked")
        if has_open_position:
            tokens.append("protect_only")
    return tuple(tokens)


@dataclass(frozen=True)
class RuntimeAnalyticsRestoreStatus:
    state: RuntimeAnalyticsRestoreState
    why: tuple[str, ...] = field(default_factory=tuple)
    updated_at: int | None = None
    source: str = ""
    evidence_ref: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "why", _normalize_why_tokens(self.why))

    def to_payload(self) -> dict[str, object]:
        return {
            "state": self.state.value,
            "why": list(self.why),
            "updated_at": self.updated_at,
            "source": self.source,
            "evidence_ref": self.evidence_ref,
        }


@dataclass(frozen=True)
class StrategyAnalyticsRestoreSnapshot:
    strategy_id: str
    symbol: str
    updated_at: int | None
    scopes: Mapping[str, RuntimeAnalyticsRestoreStatus]
    source: str
    permissions: RuntimePermissions
    rollup_state: RuntimeAnalyticsRestoreState
    blocking_reason_chain: tuple[str, ...] = field(default_factory=tuple)
    counts: Mapping[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "blocking_reason_chain", _normalize_why_tokens(self.blocking_reason_chain))

    def to_payload(self) -> dict[str, object]:
        return {
            "strategy_id": self.strategy_id,
            "symbol": self.symbol,
            "updated_at": self.updated_at,
            "source": self.source,
            "rollup_state": self.rollup_state.value,
            "scopes": {
                name: status.to_payload()
                for name, status in self.scopes.items()
            },
            "counts": dict(self.counts),
            "blocking_reason_chain": list(self.blocking_reason_chain),
            "permissions": self.permissions.to_payload(),
        }


def make_restore_status(
    *,
    state: RuntimeAnalyticsRestoreState,
    why: str | Iterable[str] | None,
    updated_at: int | None,
    source: str,
    evidence_ref: str | None = None,
) -> RuntimeAnalyticsRestoreStatus:
    return RuntimeAnalyticsRestoreStatus(
        state=state,
        why=_normalize_why_tokens(why),
        updated_at=updated_at,
        source=str(source),
        evidence_ref=evidence_ref,
    )


def restored_restore_status(
    *,
    why: str | Iterable[str] | None,
    updated_at: int | None,
    source: str,
    evidence_ref: str | None = None,
) -> RuntimeAnalyticsRestoreStatus:
    return make_restore_status(
        state=RuntimeAnalyticsRestoreState.RESTORED,
        why=why,
        updated_at=updated_at,
        source=source,
        evidence_ref=evidence_ref,
    )


def cold_restore_status(
    *,
    why: str | Iterable[str] | None,
    updated_at: int | None,
    source: str,
    evidence_ref: str | None = None,
) -> RuntimeAnalyticsRestoreStatus:
    return make_restore_status(
        state=RuntimeAnalyticsRestoreState.COLD,
        why=why,
        updated_at=updated_at,
        source=source,
        evidence_ref=evidence_ref,
    )


def partial_restore_status(
    *,
    why: str | Iterable[str] | None,
    updated_at: int | None,
    source: str,
    evidence_ref: str | None = None,
) -> RuntimeAnalyticsRestoreStatus:
    return make_restore_status(
        state=RuntimeAnalyticsRestoreState.PARTIAL,
        why=why,
        updated_at=updated_at,
        source=source,
        evidence_ref=evidence_ref,
    )


def invalidated_restore_status(
    *,
    why: str | Iterable[str] | None,
    updated_at: int | None,
    source: str,
    evidence_ref: str | None = None,
) -> RuntimeAnalyticsRestoreStatus:
    return make_restore_status(
        state=RuntimeAnalyticsRestoreState.INVALIDATED_DUE_TO_GAP,
        why=why,
        updated_at=updated_at,
        source=source,
        evidence_ref=evidence_ref,
    )


def make_strategy_restore_snapshot(
    *,
    strategy_id: str,
    symbol: str,
    updated_at: int | None,
    scopes: Mapping[str, RuntimeAnalyticsRestoreStatus],
    source: str,
    has_open_position: bool,
    blocking_reason_chain: str | Iterable[str] | None = None,
) -> StrategyAnalyticsRestoreSnapshot:
    scopes_dict = dict(scopes)
    rollup_state = _resolve_rollup_state(scopes_dict)
    if blocking_reason_chain is None:
        blocking_reason_chain = _default_blocking_reason_chain(
            rollup_state=rollup_state,
            has_open_position=bool(has_open_position),
        )
    permissions = make_permissions(
        can_manage_existing_risk=True,
        can_open_new_risk=rollup_state == RuntimeAnalyticsRestoreState.RESTORED,
    )
    return StrategyAnalyticsRestoreSnapshot(
        strategy_id=str(strategy_id),
        symbol=str(symbol),
        updated_at=updated_at,
        scopes=scopes_dict,
        source=str(source),
        permissions=permissions,
        rollup_state=rollup_state,
        blocking_reason_chain=_normalize_why_tokens(blocking_reason_chain),
        counts=_count_states(scopes_dict),
    )


def lookup_restore_status(
    snapshot: StrategyAnalyticsRestoreSnapshot | None,
    scope: RuntimeAnalyticsRestoreScope | str,
) -> RuntimeAnalyticsRestoreStatus | None:
    if snapshot is None:
        return None
    key = scope.value if isinstance(scope, RuntimeAnalyticsRestoreScope) else str(scope)
    return snapshot.scopes.get(key)


def restore_status_to_readiness_status(
    restore_status: RuntimeAnalyticsRestoreStatus | None,
    *,
    updated_at: int | None,
    source: str,
    evidence_ref: str | None = None,
    restored_why: str | Iterable[str] | None = None,
    default_status: RuntimeReadinessStatus | None = None,
) -> RuntimeReadinessStatus:
    if restore_status is None:
        if default_status is None:
            return cold_status(
                why=["analytics_restore_missing"],
                updated_at=updated_at,
                source=source,
                evidence_ref=evidence_ref,
            )
        return default_status

    effective_updated_at = restore_status.updated_at if restore_status.updated_at is not None else updated_at
    effective_source = restore_status.source or source
    effective_evidence_ref = restore_status.evidence_ref or evidence_ref
    why = restore_status.why or _normalize_why_tokens(restored_why)

    if restore_status.state == RuntimeAnalyticsRestoreState.RESTORED:
        return ready_status(
            why=why or restored_why or ["analytics_restored"],
            updated_at=effective_updated_at,
            source=effective_source,
            evidence_ref=effective_evidence_ref,
        )
    if restore_status.state == RuntimeAnalyticsRestoreState.COLD:
        return cold_status(
            why=why or ["analytics_restore_cold"],
            updated_at=effective_updated_at,
            source=effective_source,
            evidence_ref=effective_evidence_ref,
        )
    if restore_status.state == RuntimeAnalyticsRestoreState.PARTIAL:
        return partial_status(
            why=why or ["analytics_restore_partial"],
            updated_at=effective_updated_at,
            source=effective_source,
            evidence_ref=effective_evidence_ref,
        )
    return make_status(
        state=RuntimeReadinessState.INVALIDATED_GAP,
        why=why or ["analytics_restore_invalidated_gap"],
        updated_at=effective_updated_at,
        source=effective_source,
        evidence_ref=effective_evidence_ref,
    )


def merge_restore_readiness_live_first(
    restore_status: RuntimeAnalyticsRestoreStatus | None,
    *,
    live_status: RuntimeReadinessStatus | None,
    updated_at: int | None,
    source: str,
    evidence_ref: str | None = None,
    restored_why: str | Iterable[str] | None = None,
    live_evidence_present: bool = True,
) -> RuntimeReadinessStatus:
    if live_status is not None:
        live_state = live_status.state
        if live_state in (
            RuntimeReadinessState.INVALIDATED_GAP,
            RuntimeReadinessState.BLOCKED,
            RuntimeReadinessState.READY,
            RuntimeReadinessState.PARTIAL,
        ):
            return live_status
        if live_state == RuntimeReadinessState.COLD and live_evidence_present:
            return live_status

    if restore_status is None:
        if live_status is not None:
            return live_status
        return cold_status(
            why=["analytics_restore_missing"],
            updated_at=updated_at,
            source=source,
            evidence_ref=evidence_ref,
        )

    return restore_status_to_readiness_status(
        restore_status,
        updated_at=updated_at,
        source=source,
        evidence_ref=evidence_ref,
        restored_why=restored_why,
        default_status=live_status,
    )


def combine_restore_permissions(
    base_permissions: RuntimePermissions,
    snapshot: StrategyAnalyticsRestoreSnapshot | None,
) -> RuntimePermissions:
    if snapshot is None:
        return base_permissions
    return make_permissions(
        can_manage_existing_risk=(
            bool(base_permissions.can_manage_existing_risk)
            and bool(snapshot.permissions.can_manage_existing_risk)
        ),
        can_open_new_risk=(
            bool(base_permissions.can_open_new_risk)
            and bool(snapshot.permissions.can_open_new_risk)
        ),
    )


def combine_restore_permissions_live_first(
    base_permissions: RuntimePermissions,
    snapshot: StrategyAnalyticsRestoreSnapshot | None,
) -> RuntimePermissions:
    if snapshot is None:
        return base_permissions
    execution_status = lookup_restore_status(
        snapshot,
        RuntimeAnalyticsRestoreScope.EXECUTION_STATE,
    )
    if execution_status is None or execution_status.state == RuntimeAnalyticsRestoreState.RESTORED:
        return base_permissions
    return make_permissions(
        can_manage_existing_risk=bool(base_permissions.can_manage_existing_risk),
        can_open_new_risk=False,
    )


def restore_blocking_tokens(
    snapshot: StrategyAnalyticsRestoreSnapshot | None,
) -> tuple[str, ...]:
    if snapshot is None:
        return ()
    if snapshot.blocking_reason_chain:
        return tuple(snapshot.blocking_reason_chain)
    return _default_blocking_reason_chain(
        rollup_state=snapshot.rollup_state,
        has_open_position=snapshot.permissions.can_manage_existing_risk,
    )


def restore_execution_blocking_tokens(
    snapshot: StrategyAnalyticsRestoreSnapshot | None,
) -> tuple[str, ...]:
    if snapshot is None:
        return ()
    execution_status = lookup_restore_status(
        snapshot,
        RuntimeAnalyticsRestoreScope.EXECUTION_STATE,
    )
    if execution_status is None or execution_status.state == RuntimeAnalyticsRestoreState.RESTORED:
        return ()
    if execution_status.state == RuntimeAnalyticsRestoreState.INVALIDATED_DUE_TO_GAP:
        return ("execution_context_restore_invalidated_gap",)
    if execution_status.state == RuntimeAnalyticsRestoreState.PARTIAL:
        return ("execution_context_restore_partial",)
    return ("execution_context_restore_cold",)


def extract_strategy_restore_snapshot(
    payload: Mapping[str, Any] | None,
) -> StrategyAnalyticsRestoreSnapshot | None:
    if not isinstance(payload, Mapping):
        return None
    raw = payload.get("analytics_restore")
    if not isinstance(raw, Mapping):
        return None

    scopes_raw = raw.get("scopes")
    scopes: dict[str, RuntimeAnalyticsRestoreStatus] = {}
    if isinstance(scopes_raw, Mapping):
        for scope_name, status_raw in scopes_raw.items():
            if not isinstance(status_raw, Mapping):
                continue
            try:
                scopes[str(scope_name)] = make_restore_status(
                    state=RuntimeAnalyticsRestoreState(str(status_raw.get("state", RuntimeAnalyticsRestoreState.COLD.value))),
                    why=status_raw.get("why"),
                    updated_at=(int(status_raw["updated_at"]) if status_raw.get("updated_at") is not None else None),
                    source=str(status_raw.get("source") or "runtime:payload"),
                    evidence_ref=(str(status_raw.get("evidence_ref")) if status_raw.get("evidence_ref") is not None else None),
                )
            except Exception:
                continue

    permissions_raw = raw.get("permissions") if isinstance(raw.get("permissions"), Mapping) else {}
    permissions = make_permissions(
        can_manage_existing_risk=bool(permissions_raw.get("can_manage_existing_risk", False)),
        can_open_new_risk=bool(permissions_raw.get("can_open_new_risk", False)),
    )
    rollup_state_raw = str(raw.get("rollup_state") or _resolve_rollup_state(scopes).value)
    rollup_state = RuntimeAnalyticsRestoreState(rollup_state_raw)

    return StrategyAnalyticsRestoreSnapshot(
        strategy_id=str(raw.get("strategy_id") or payload.get("strategy_id") or ""),
        symbol=str(raw.get("symbol") or payload.get("symbol") or ""),
        updated_at=(int(raw["updated_at"]) if raw.get("updated_at") is not None else None),
        scopes=scopes,
        source=str(raw.get("source") or "runtime:payload"),
        permissions=permissions,
        rollup_state=rollup_state,
        blocking_reason_chain=_normalize_why_tokens(raw.get("blocking_reason_chain")),
        counts={
            str(key): int(value)
            for key, value in (
                raw.get("counts").items()
                if isinstance(raw.get("counts"), Mapping)
                else _count_states(scopes).items()
            )
        },
    )
