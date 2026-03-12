from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Mapping

from apps.reference.bootstrap.runtime_analytics_restore import (
    StartupAnalyticsRestoreReport,
)
from apps.reference.contracts.runtime_analytics_restore import (
    RuntimeAnalyticsRestoreScope,
    RuntimeAnalyticsRestoreState,
    StrategyAnalyticsRestoreSnapshot,
    lookup_restore_status,
)
from apps.reference.contracts.runtime_bar_identity import RuntimeBarSourceMode
from apps.reference.contracts.runtime_readiness import (
    RuntimePermissions,
    make_permissions,
)
from apps.reference.contracts.strategy_compatibility_matrix import (
    build_active_strategy_compatibility_profiles,
)


def _normalize_tokens(tokens: str | Iterable[str] | None) -> tuple[str, ...]:
    if tokens is None:
        return ()
    if isinstance(tokens, str):
        value = tokens.strip()
        return (value,) if value else ()
    normalized: list[str] = []
    for token in tokens:
        value = str(token).strip()
        if value:
            normalized.append(value)
    return tuple(normalized)


class StartupWarmupState(str, Enum):
    WARMED = "WARMED"
    PARTIAL = "PARTIAL"
    SKIPPED = "SKIPPED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class StartupWarmupStatus:
    state: StartupWarmupState
    why: tuple[str, ...] = field(default_factory=tuple)
    updated_at: int | None = None
    source: str = ""
    evidence_ref: str | None = None
    details: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "why", _normalize_tokens(self.why))
        object.__setattr__(self, "details", dict(self.details))

    def to_payload(self) -> dict[str, object]:
        return {
            "state": self.state.value,
            "why": list(self.why),
            "updated_at": self.updated_at,
            "source": self.source,
            "evidence_ref": self.evidence_ref,
            "details": dict(self.details),
        }


def make_startup_warmup_status(
    *,
    state: StartupWarmupState,
    why: str | Iterable[str] | None,
    updated_at: int | None,
    source: str,
    evidence_ref: str | None = None,
    details: Mapping[str, object] | None = None,
) -> StartupWarmupStatus:
    return StartupWarmupStatus(
        state=state,
        why=_normalize_tokens(why),
        updated_at=updated_at,
        source=str(source),
        evidence_ref=evidence_ref,
        details=dict(details or {}),
    )


def warmed_warmup_status(
    *,
    why: str | Iterable[str] | None,
    updated_at: int | None,
    source: str,
    evidence_ref: str | None = None,
    details: Mapping[str, object] | None = None,
) -> StartupWarmupStatus:
    return make_startup_warmup_status(
        state=StartupWarmupState.WARMED,
        why=why,
        updated_at=updated_at,
        source=source,
        evidence_ref=evidence_ref,
        details=details,
    )


def partial_warmup_status(
    *,
    why: str | Iterable[str] | None,
    updated_at: int | None,
    source: str,
    evidence_ref: str | None = None,
    details: Mapping[str, object] | None = None,
) -> StartupWarmupStatus:
    return make_startup_warmup_status(
        state=StartupWarmupState.PARTIAL,
        why=why,
        updated_at=updated_at,
        source=source,
        evidence_ref=evidence_ref,
        details=details,
    )


def skipped_warmup_status(
    *,
    why: str | Iterable[str] | None,
    updated_at: int | None,
    source: str,
    evidence_ref: str | None = None,
    details: Mapping[str, object] | None = None,
) -> StartupWarmupStatus:
    return make_startup_warmup_status(
        state=StartupWarmupState.SKIPPED,
        why=why,
        updated_at=updated_at,
        source=source,
        evidence_ref=evidence_ref,
        details=details,
    )


def failed_warmup_status(
    *,
    why: str | Iterable[str] | None,
    updated_at: int | None,
    source: str,
    evidence_ref: str | None = None,
    details: Mapping[str, object] | None = None,
) -> StartupWarmupStatus:
    return make_startup_warmup_status(
        state=StartupWarmupState.FAILED,
        why=why,
        updated_at=updated_at,
        source=source,
        evidence_ref=evidence_ref,
        details=details,
    )


@dataclass(frozen=True)
class FeatureEngineeringBackfillPlan:
    config_path: str
    enabled: bool
    symbols: tuple[str, ...]
    d1_candles: int
    h4_candles: int
    m15_candles: int
    regime_basis_candles: int
    source_mode: str = RuntimeBarSourceMode.WARMUP_IMPORT.value

    def to_payload(self) -> dict[str, object]:
        return {
            "config_path": self.config_path,
            "enabled": bool(self.enabled),
            "symbols": list(self.symbols),
            "counts": {
                "d1": int(self.d1_candles),
                "h4": int(self.h4_candles),
                "m15": int(self.m15_candles),
                "basis_tf_5m": int(self.regime_basis_candles),
            },
            "source_mode": self.source_mode,
        }


def resolve_feature_engineering_backfill_plan(
    config: Any,
) -> FeatureEngineeringBackfillPlan:
    config_path = "domains.feature_engineering.pillars.backfill"
    backfill_cfg = getattr(
        getattr(
            getattr(
                getattr(config, "domains", None),
                "feature_engineering",
                None,
            ),
            "pillars",
            None,
        ),
        "backfill",
        None,
    )
    instruments = getattr(config, "instruments", None)
    if isinstance(instruments, Mapping):
        symbols = tuple(sorted(str(symbol).upper() for symbol in instruments.keys()))
    else:
        assignments = getattr(getattr(config, "strategies_registry", None), "assignments", None)
        if isinstance(assignments, Mapping):
            symbols = tuple(sorted(str(symbol).upper() for symbol in assignments.keys()))
        else:
            symbols = ()
    return FeatureEngineeringBackfillPlan(
        config_path=config_path,
        enabled=bool(getattr(backfill_cfg, "enabled", False)),
        symbols=symbols,
        d1_candles=int(getattr(backfill_cfg, "d1_candles", 200) or 200),
        h4_candles=int(getattr(backfill_cfg, "h4_candles", 100) or 100),
        m15_candles=int(getattr(backfill_cfg, "m15_candles", 50) or 50),
        regime_basis_candles=320,
    )


_STARTUP_WARMUP_IN_PROGRESS = False
_STARTUP_WARMUP_UPDATED_AT: int | None = None
_STARTUP_WARMUP_SOURCE = ""


def activate_startup_warmup_gate(
    *,
    updated_at: int | None,
    source: str,
) -> None:
    global _STARTUP_WARMUP_IN_PROGRESS, _STARTUP_WARMUP_UPDATED_AT, _STARTUP_WARMUP_SOURCE
    _STARTUP_WARMUP_IN_PROGRESS = True
    _STARTUP_WARMUP_UPDATED_AT = updated_at
    _STARTUP_WARMUP_SOURCE = str(source)


def release_startup_warmup_gate() -> None:
    global _STARTUP_WARMUP_IN_PROGRESS, _STARTUP_WARMUP_UPDATED_AT, _STARTUP_WARMUP_SOURCE
    _STARTUP_WARMUP_IN_PROGRESS = False
    _STARTUP_WARMUP_UPDATED_AT = None
    _STARTUP_WARMUP_SOURCE = ""


def startup_warmup_gate_active() -> bool:
    return bool(_STARTUP_WARMUP_IN_PROGRESS)


def startup_warmup_gate_tokens() -> tuple[str, ...]:
    if not startup_warmup_gate_active():
        return ()
    return ("startup_warmup_in_progress",)


def apply_startup_warmup_permission_overlay(
    permissions: RuntimePermissions,
) -> RuntimePermissions:
    if not startup_warmup_gate_active():
        return permissions
    return make_permissions(
        can_manage_existing_risk=permissions.can_manage_existing_risk,
        can_open_new_risk=False,
    )


def _execution_restore_blocker(
    snapshot: StrategyAnalyticsRestoreSnapshot | None,
) -> str | None:
    restore_status = lookup_restore_status(
        snapshot,
        RuntimeAnalyticsRestoreScope.EXECUTION_STATE,
    )
    if restore_status is None or restore_status.state == RuntimeAnalyticsRestoreState.RESTORED:
        return None
    if restore_status.state == RuntimeAnalyticsRestoreState.INVALIDATED_DUE_TO_GAP:
        return "execution_context_restore_invalidated_gap"
    if restore_status.state == RuntimeAnalyticsRestoreState.PARTIAL:
        return "execution_context_restore_partial"
    return "execution_context_restore_cold"


def _warmup_blocker(
    owner: str,
    status: StartupWarmupStatus | None,
) -> str:
    suffix = "missing" if status is None else str(status.state.value).lower()
    return f"{owner}_warmup_{suffix}"


@dataclass(frozen=True)
class StrategyStartupWarmupSnapshot:
    strategy_id: str
    symbol: str
    compatibility_profile_id: str
    updated_at: int | None
    source: str
    restore: Mapping[str, object]
    warmup: Mapping[str, StartupWarmupStatus]
    permissions: RuntimePermissions
    effective_blockers: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "effective_blockers",
            _normalize_tokens(self.effective_blockers),
        )
        object.__setattr__(self, "restore", dict(self.restore))
        object.__setattr__(self, "warmup", dict(self.warmup))

    def to_payload(self) -> dict[str, object]:
        return {
            "strategy_id": self.strategy_id,
            "symbol": self.symbol,
            "compatibility_profile_id": self.compatibility_profile_id,
            "updated_at": self.updated_at,
            "source": self.source,
            "restore": dict(self.restore),
            "warmup": {
                owner: status.to_payload()
                for owner, status in self.warmup.items()
            },
            "permissions": self.permissions.to_payload(),
            "effective_blockers": list(self.effective_blockers),
        }


@dataclass(frozen=True)
class StartupWarmupReport:
    updated_at: int | None
    source: str
    gate_active: bool
    records: Mapping[str, StrategyStartupWarmupSnapshot]

    def to_payload(self) -> dict[str, object]:
        return {
            "updated_at": self.updated_at,
            "source": self.source,
            "gate_active": bool(self.gate_active),
            "record_count": len(self.records),
            "records": {
                key: record.to_payload()
                for key, record in self.records.items()
            },
        }


def build_startup_warmup_report(
    *,
    config: Any,
    analytics_restore_report: StartupAnalyticsRestoreReport,
    warmup_statuses: Mapping[str, Mapping[str, StartupWarmupStatus]] | None,
    updated_at: int | None,
    source: str = "startup:warmup_report",
    gate_active: bool | None = None,
) -> StartupWarmupReport:
    profiles = build_active_strategy_compatibility_profiles(config)
    warmup_statuses = warmup_statuses if isinstance(warmup_statuses, Mapping) else {}
    gate_active = startup_warmup_gate_active() if gate_active is None else bool(gate_active)

    records: dict[str, StrategyStartupWarmupSnapshot] = {}
    for strategy_id, profile in profiles.items():
        for symbol in profile.active_symbols:
            symbol_key = str(symbol).upper()
            restore_snapshot = analytics_restore_report.get_snapshot(strategy_id, symbol_key)
            owner_statuses = {
                str(owner): status
                for owner, status in (
                    warmup_statuses.get(symbol_key) or {}
                ).items()
                if isinstance(status, StartupWarmupStatus)
            }

            blockers: list[str] = []
            if gate_active:
                blockers.extend(startup_warmup_gate_tokens())

            execution_blocker = _execution_restore_blocker(restore_snapshot)
            if execution_blocker is not None:
                blockers.append(execution_blocker)

            feature_engineering_status = owner_statuses.get("feature_engineering")
            regime_status = owner_statuses.get("regime_detector")

            if profile.needs_microstructure and (
                feature_engineering_status is None
                or feature_engineering_status.state != StartupWarmupState.WARMED
            ):
                blockers.append(_warmup_blocker("feature_engineering", feature_engineering_status))
            if profile.quadratic_readiness_blocks_by_default and (
                feature_engineering_status is None
                or feature_engineering_status.state != StartupWarmupState.WARMED
            ):
                blockers.append("quadratic_htf_not_ready")
            if profile.needs_regime and (
                regime_status is None
                or regime_status.state != StartupWarmupState.WARMED
            ):
                blockers.append(_warmup_blocker("regime_detector", regime_status))

            blockers = list(dict.fromkeys(_normalize_tokens(blockers)))
            permissions = make_permissions(
                can_manage_existing_risk=True,
                can_open_new_risk=not blockers,
            )
            record = StrategyStartupWarmupSnapshot(
                strategy_id=str(strategy_id),
                symbol=symbol_key,
                compatibility_profile_id=str(profile.profile_id),
                updated_at=updated_at,
                source=str(source),
                restore=(
                    restore_snapshot.to_payload()
                    if restore_snapshot is not None
                    else {}
                ),
                warmup=owner_statuses,
                permissions=permissions,
                effective_blockers=tuple(blockers),
            )
            records[f"{strategy_id}:{symbol_key}"] = record

    return StartupWarmupReport(
        updated_at=updated_at,
        source=str(source),
        gate_active=gate_active,
        records=records,
    )
