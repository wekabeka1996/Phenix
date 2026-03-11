from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from apps.reference.bootstrap.runtime_analytics_restore import (
    StartupAnalyticsRestoreReport,
)
from apps.reference.contracts.runtime_analytics_restore import (
    RuntimeAnalyticsRestoreScope,
    RuntimeAnalyticsRestoreState,
    StrategyAnalyticsRestoreSnapshot,
    lookup_restore_status,
)
from apps.reference.contracts.strategy_compatibility_matrix import (
    StrategyCompatibilityProfile,
    StrategyHTFRequirement,
    build_active_strategy_compatibility_profiles,
)


@dataclass(frozen=True)
class HTFRequirement:
    timeframe_sec: int
    required_bars: int
    scope: str
    source: str

    def to_payload(self) -> dict[str, object]:
        return {
            "timeframe_sec": int(self.timeframe_sec),
            "required_bars": int(self.required_bars),
            "scope": self.scope,
            "source": self.source,
        }


@dataclass(frozen=True)
class StrategyHydrationRequirement:
    compatibility_profile_id: str
    strategy_id: str
    symbol: str
    basis_tf_sec: int
    basis_required_bars: int
    required_htf: tuple[HTFRequirement, ...] = ()
    needs_regime: bool = False
    needs_microstructure: bool = False
    needs_execution_context: bool = False
    local_hydration_contract: str | None = None
    degraded_mode_allowance: str = "NON_TRADING_ONLY"
    protect_only_capability: bool = False
    quadratic_readiness_blocks_by_default: bool = False

    def to_payload(self) -> dict[str, object]:
        return {
            "compatibility_profile_id": self.compatibility_profile_id,
            "strategy_id": self.strategy_id,
            "symbol": self.symbol,
            "basis_tf_sec": int(self.basis_tf_sec),
            "basis_required_bars": int(self.basis_required_bars),
            "required_htf": [item.to_payload() for item in self.required_htf],
            "needs_regime": bool(self.needs_regime),
            "needs_microstructure": bool(self.needs_microstructure),
            "needs_execution_context": bool(self.needs_execution_context),
            "local_hydration_contract": self.local_hydration_contract,
            "degraded_mode_allowance": self.degraded_mode_allowance,
            "protect_only_capability": bool(self.protect_only_capability),
            "quadratic_readiness_blocks_by_default": bool(self.quadratic_readiness_blocks_by_default),
        }


@dataclass(frozen=True)
class HydrationAction:
    action: str
    owner: str
    scope: str
    reason: str
    timeframe_sec: int | None = None
    required_bars: int | None = None

    def to_payload(self) -> dict[str, object]:
        return {
            "action": self.action,
            "owner": self.owner,
            "scope": self.scope,
            "reason": self.reason,
            "timeframe_sec": self.timeframe_sec,
            "required_bars": self.required_bars,
        }


@dataclass(frozen=True)
class StrategyHydrationPlan:
    strategy_id: str
    symbol: str
    requirement: StrategyHydrationRequirement
    actions: tuple[HydrationAction, ...] = field(default_factory=tuple)
    analytics_rollup_state: str = RuntimeAnalyticsRestoreState.COLD.value

    def to_payload(self) -> dict[str, object]:
        return {
            "strategy_id": self.strategy_id,
            "symbol": self.symbol,
            "analytics_rollup_state": self.analytics_rollup_state,
            "requirement": self.requirement.to_payload(),
            "actions": [action.to_payload() for action in self.actions],
        }


@dataclass(frozen=True)
class StartupHydrationPlanReport:
    updated_at: int | None
    source: str
    plans: Mapping[str, StrategyHydrationPlan]

    def to_payload(self) -> dict[str, object]:
        return {
            "updated_at": self.updated_at,
            "source": self.source,
            "plan_count": len(self.plans),
            "plans": {
                key: plan.to_payload()
                for key, plan in self.plans.items()
            },
        }


def _plan_key(strategy_id: str, symbol: str) -> str:
    return f"{str(strategy_id)}:{str(symbol).upper()}"


def _to_htf_requirements(required_htf: tuple[StrategyHTFRequirement, ...]) -> tuple[HTFRequirement, ...]:
    return tuple(
        HTFRequirement(
            timeframe_sec=int(item.timeframe_sec),
            required_bars=int(item.required_bars),
            scope=str(item.scope),
            source=str(item.source),
        )
        for item in required_htf
    )


def _requirement_from_profile(
    profile: StrategyCompatibilityProfile,
    symbol: str,
) -> StrategyHydrationRequirement:
    return StrategyHydrationRequirement(
        compatibility_profile_id=profile.profile_id,
        strategy_id=profile.strategy_id,
        symbol=symbol,
        basis_tf_sec=int(profile.required_basis_tf_sec),
        basis_required_bars=int(profile.basis_required_bars),
        required_htf=_to_htf_requirements(profile.required_htf),
        needs_regime=bool(profile.needs_regime),
        needs_microstructure=bool(profile.needs_microstructure),
        needs_execution_context=bool(profile.needs_execution_context),
        local_hydration_contract=profile.local_hydration_contract,
        degraded_mode_allowance=str(profile.degraded_mode_allowance),
        protect_only_capability=bool(profile.protect_only_capability),
        quadratic_readiness_blocks_by_default=bool(profile.quadratic_readiness_blocks_by_default),
    )


def _status_state(
    snapshot: StrategyAnalyticsRestoreSnapshot | None,
    scope: RuntimeAnalyticsRestoreScope,
) -> RuntimeAnalyticsRestoreState | None:
    status = lookup_restore_status(snapshot, scope)
    return status.state if status is not None else None


def _append_action(
    actions: list[HydrationAction],
    *,
    action: str,
    owner: str,
    scope: str,
    reason: str,
    timeframe_sec: int | None = None,
    required_bars: int | None = None,
) -> None:
    candidate = HydrationAction(
        action=action,
        owner=owner,
        scope=scope,
        reason=reason,
        timeframe_sec=timeframe_sec,
        required_bars=required_bars,
    )
    if candidate not in actions:
        actions.append(candidate)


def _build_actions(
    requirement: StrategyHydrationRequirement,
    snapshot: StrategyAnalyticsRestoreSnapshot | None,
) -> tuple[HydrationAction, ...]:
    actions: list[HydrationAction] = []

    bars_state = _status_state(snapshot, RuntimeAnalyticsRestoreScope.BARS)
    fe_last_bar_state = _status_state(snapshot, RuntimeAnalyticsRestoreScope.FEATURE_ENGINEERING_LAST_BAR)
    fe_cache_state = _status_state(snapshot, RuntimeAnalyticsRestoreScope.FEATURE_ENGINEERING_CACHE)
    regime_state = _status_state(snapshot, RuntimeAnalyticsRestoreScope.REGIME_DETECTOR_STATE)
    pillar_state = _status_state(snapshot, RuntimeAnalyticsRestoreScope.PILLAR_STATE)
    strategy_local_state = _status_state(snapshot, RuntimeAnalyticsRestoreScope.STRATEGY_LOCAL_STATE)

    if bars_state == RuntimeAnalyticsRestoreState.INVALIDATED_DUE_TO_GAP:
        _append_action(
            actions,
            action="REPAIR_GAP",
            owner="market_data",
            scope=RuntimeAnalyticsRestoreScope.BARS.value,
            reason="basis_bars_invalidated_gap",
            timeframe_sec=requirement.basis_tf_sec,
            required_bars=requirement.basis_required_bars,
        )
    elif bars_state != RuntimeAnalyticsRestoreState.RESTORED:
        _append_action(
            actions,
            action="RESTORE_OR_REPLAY_BASIS_BARS",
            owner="market_data",
            scope=RuntimeAnalyticsRestoreScope.BARS.value,
            reason="basis_bars_not_restored",
            timeframe_sec=requirement.basis_tf_sec,
            required_bars=requirement.basis_required_bars,
        )

    if fe_last_bar_state != RuntimeAnalyticsRestoreState.RESTORED:
        _append_action(
            actions,
            action="RESTORE_FEATURE_LAST_BAR",
            owner="feature_engineering",
            scope=RuntimeAnalyticsRestoreScope.FEATURE_ENGINEERING_LAST_BAR.value,
            reason="feature_last_bar_not_restored",
            timeframe_sec=requirement.basis_tf_sec,
            required_bars=requirement.basis_required_bars,
        )

    if fe_cache_state != RuntimeAnalyticsRestoreState.RESTORED and requirement.needs_microstructure:
        _append_action(
            actions,
            action="RESTORE_FEATURE_CACHE",
            owner="feature_engineering",
            scope=RuntimeAnalyticsRestoreScope.FEATURE_ENGINEERING_CACHE.value,
            reason="feature_cache_not_restored",
            timeframe_sec=requirement.basis_tf_sec,
            required_bars=requirement.basis_required_bars,
        )

    if regime_state != RuntimeAnalyticsRestoreState.RESTORED and requirement.needs_regime:
        _append_action(
            actions,
            action="RESTORE_REGIME_STATE",
            owner="regime_detector",
            scope=RuntimeAnalyticsRestoreScope.REGIME_DETECTOR_STATE.value,
            reason="regime_state_not_restored",
            timeframe_sec=requirement.basis_tf_sec,
            required_bars=requirement.basis_required_bars,
        )

    if requirement.local_hydration_contract == "md_amr_rest_hydration" and strategy_local_state != RuntimeAnalyticsRestoreState.RESTORED:
        _append_action(
            actions,
            action="USE_STRATEGY_LOCAL_HYDRATION",
            owner="decision_making",
            scope=RuntimeAnalyticsRestoreScope.STRATEGY_LOCAL_STATE.value,
            reason="strategy_local_state_not_restored",
            timeframe_sec=requirement.basis_tf_sec,
            required_bars=requirement.basis_required_bars,
        )
    elif strategy_local_state != RuntimeAnalyticsRestoreState.RESTORED:
        _append_action(
            actions,
            action="RESTORE_STRATEGY_LOCAL_STATE",
            owner="decision_making",
            scope=RuntimeAnalyticsRestoreScope.STRATEGY_LOCAL_STATE.value,
            reason="strategy_local_state_not_restored",
            timeframe_sec=requirement.basis_tf_sec,
            required_bars=requirement.basis_required_bars,
        )

    if requirement.required_htf and pillar_state != RuntimeAnalyticsRestoreState.RESTORED:
        for htf in requirement.required_htf:
            _append_action(
                actions,
                action="IMPORT_HTF_BARS",
                owner="feature_engineering",
                scope=htf.scope,
                reason="quadratic_htf_not_restored",
                timeframe_sec=htf.timeframe_sec,
                required_bars=htf.required_bars,
            )

    return tuple(actions)


def build_startup_hydration_plan(
    *,
    config: Any,
    analytics_restore_report: StartupAnalyticsRestoreReport,
    updated_at: int | None,
    source: str = "startup:hydration_planner",
) -> StartupHydrationPlanReport:
    profiles = build_active_strategy_compatibility_profiles(config)
    plans: dict[str, StrategyHydrationPlan] = {}

    for strategy_id, profile in profiles.items():
        for symbol in profile.active_symbols:
            requirement = _requirement_from_profile(profile, symbol)
            snapshot = analytics_restore_report.get_snapshot(strategy_id, symbol)
            plan = StrategyHydrationPlan(
                strategy_id=strategy_id,
                symbol=symbol,
                requirement=requirement,
                actions=_build_actions(requirement, snapshot),
                analytics_rollup_state=(
                    snapshot.rollup_state.value
                    if snapshot is not None
                    else RuntimeAnalyticsRestoreState.COLD.value
                ),
            )
            plans[_plan_key(strategy_id, symbol)] = plan

    return StartupHydrationPlanReport(
        updated_at=updated_at,
        source=source,
        plans=plans,
    )
