"""
Canonical runtime readiness contract for phased runtime standardization.

URS-A1 introduces this module as the shared additive schema for readiness
states and runtime permissions. It does not replace legacy `readiness.warmup_ok`
consumers yet.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, Mapping


class RuntimeReadinessState(str, Enum):
    READY = "READY"
    COLD = "COLD"
    PARTIAL = "PARTIAL"
    BLOCKED = "BLOCKED"
    INVALIDATED_GAP = "INVALIDATED_GAP"


class RuntimeReadinessScope(str, Enum):
    BASIS_BAR_READY = "basis_bar_ready"
    REGIME_READY = "regime_ready"
    QUADRATIC_HTF_READY = "quadratic_htf_ready"
    MICROSTRUCTURE_READY = "microstructure_ready"
    STRATEGY_READY_PER_SYMBOL = "strategy_ready_per_symbol"
    EXECUTION_CONTEXT_READY = "execution_context_ready"
    TRADING_READY = "trading_ready"


READINESS_SCOPE_OWNERS: dict[str, str] = {
    RuntimeReadinessScope.BASIS_BAR_READY.value: "market_data",
    RuntimeReadinessScope.REGIME_READY.value: "regime_detector",
    RuntimeReadinessScope.QUADRATIC_HTF_READY.value: "feature_engineering",
    RuntimeReadinessScope.MICROSTRUCTURE_READY.value: "feature_engineering",
    RuntimeReadinessScope.STRATEGY_READY_PER_SYMBOL.value: "decision_making",
    RuntimeReadinessScope.EXECUTION_CONTEXT_READY.value: "execution_position",
    RuntimeReadinessScope.TRADING_READY.value: "policy_arbiter",
}


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


@dataclass(frozen=True)
class RuntimeReadinessStatus:
    state: RuntimeReadinessState
    why: tuple[str, ...] = field(default_factory=tuple)
    updated_at: int | None = None
    source: str = ""
    evidence_ref: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "why", _normalize_why_tokens(self.why))

    @property
    def is_ready(self) -> bool:
        return self.state == RuntimeReadinessState.READY

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "state": self.state.value,
            "why": list(self.why),
            "updated_at": self.updated_at,
            "source": self.source,
            "evidence_ref": self.evidence_ref,
        }
        return payload


@dataclass(frozen=True)
class RuntimePermissions:
    can_manage_existing_risk: bool
    can_open_new_risk: bool

    @property
    def mode(self) -> str:
        if self.can_manage_existing_risk and self.can_open_new_risk:
            return "OPEN_AND_MANAGE"
        if self.can_manage_existing_risk and not self.can_open_new_risk:
            return "PROTECT_ONLY"
        if (not self.can_manage_existing_risk) and (not self.can_open_new_risk):
            return "FROZEN"
        return "INVALID"

    def to_payload(self) -> dict[str, object]:
        return {
            "can_manage_existing_risk": self.can_manage_existing_risk,
            "can_open_new_risk": self.can_open_new_risk,
            "mode": self.mode,
        }


@dataclass(frozen=True)
class StrategyRuntimeReadinessSnapshot:
    strategy_id: str
    symbol: str
    updated_at: int | None
    scopes: Mapping[str, RuntimeReadinessStatus]
    source: str
    permissions: RuntimePermissions
    blocking_reason_chain: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "blocking_reason_chain",
            _normalize_why_tokens(self.blocking_reason_chain),
        )

    def to_payload(self) -> dict[str, object]:
        return {
            "strategy_id": self.strategy_id,
            "symbol": self.symbol,
            "updated_at": self.updated_at,
            "source": self.source,
            "scopes": {
                name: status.to_payload()
                for name, status in self.scopes.items()
            },
            "blocking_reason_chain": list(self.blocking_reason_chain),
            "permissions": self.permissions.to_payload(),
        }


def make_status(
    *,
    state: RuntimeReadinessState,
    why: str | Iterable[str] | None,
    updated_at: int | None,
    source: str,
    evidence_ref: str | None = None,
) -> RuntimeReadinessStatus:
    return RuntimeReadinessStatus(
        state=state,
        why=_normalize_why_tokens(why),
        updated_at=updated_at,
        source=source,
        evidence_ref=evidence_ref,
    )


def make_permissions(
    *,
    can_manage_existing_risk: bool,
    can_open_new_risk: bool,
) -> RuntimePermissions:
    return RuntimePermissions(
        can_manage_existing_risk=bool(can_manage_existing_risk),
        can_open_new_risk=bool(can_open_new_risk),
    )


def make_snapshot(
    *,
    strategy_id: str,
    symbol: str,
    updated_at: int | None,
    scopes: Mapping[str, RuntimeReadinessStatus],
    source: str,
    permissions: RuntimePermissions,
    blocking_reason_chain: str | Iterable[str] | None = None,
) -> StrategyRuntimeReadinessSnapshot:
    return StrategyRuntimeReadinessSnapshot(
        strategy_id=str(strategy_id),
        symbol=str(symbol),
        updated_at=updated_at,
        scopes=dict(scopes),
        source=str(source),
        permissions=permissions,
        blocking_reason_chain=_normalize_why_tokens(blocking_reason_chain),
    )


def ready_status(
    *,
    why: str | Iterable[str] | None,
    updated_at: int | None,
    source: str,
    evidence_ref: str | None = None,
) -> RuntimeReadinessStatus:
    return make_status(
        state=RuntimeReadinessState.READY,
        why=why,
        updated_at=updated_at,
        source=source,
        evidence_ref=evidence_ref,
    )


def cold_status(
    *,
    why: str | Iterable[str] | None,
    updated_at: int | None,
    source: str,
    evidence_ref: str | None = None,
) -> RuntimeReadinessStatus:
    return make_status(
        state=RuntimeReadinessState.COLD,
        why=why,
        updated_at=updated_at,
        source=source,
        evidence_ref=evidence_ref,
    )


def partial_status(
    *,
    why: str | Iterable[str] | None,
    updated_at: int | None,
    source: str,
    evidence_ref: str | None = None,
) -> RuntimeReadinessStatus:
    return make_status(
        state=RuntimeReadinessState.PARTIAL,
        why=why,
        updated_at=updated_at,
        source=source,
        evidence_ref=evidence_ref,
    )


def blocked_status(
    *,
    why: str | Iterable[str] | None,
    updated_at: int | None,
    source: str,
    evidence_ref: str | None = None,
) -> RuntimeReadinessStatus:
    return make_status(
        state=RuntimeReadinessState.BLOCKED,
        why=why,
        updated_at=updated_at,
        source=source,
        evidence_ref=evidence_ref,
    )
