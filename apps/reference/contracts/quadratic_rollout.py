from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Mapping

from apps.reference.contracts.runtime_readiness import (
    RuntimePermissions,
    RuntimeReadinessState,
    RuntimeReadinessStatus,
    make_permissions,
)
from apps.reference.shared.decision_primitives.scoring_kernel import (
    QuadraticScoringKernel,
)

# Phase 9 cleanup: v2 scoring kernel is deleted — only "quadratic" is a valid runtime version.
_VALID_SCORING_VERSIONS = {"quadratic"}


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


class QuadraticRolloutMode(str, Enum):
    QUADRATIC_SHADOW = "quadratic_shadow"
    QUADRATIC_LIVE = "quadratic_live"


class QuadraticRollbackArmedStatus(str, Enum):
    # Phase 9: rollback is permanently disarmed. ARMED retained for schema backward-compat only.
    ARMED = "ARMED"
    DISARMED = "DISARMED"


class QuadraticShadowEvaluationState(str, Enum):
    NOT_REQUESTED = "NOT_REQUESTED"
    READY = "READY"
    DEFERRED = "DEFERRED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class RequestedQuadraticRollout:
    requested_scoring_version: str
    effective_live_scoring_version: str
    shadow_requested: bool
    rollback_armed: bool
    rollback_reason_chain: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "rollback_reason_chain",
            _normalize_tokens(self.rollback_reason_chain),
        )

    @property
    def mode(self) -> QuadraticRolloutMode:
        # Phase 9 cleanup: v2 kernel deleted, only quadratic paths are reachable.
        if self.effective_live_scoring_version == "quadratic":
            return QuadraticRolloutMode.QUADRATIC_LIVE
        if self.shadow_requested:
            return QuadraticRolloutMode.QUADRATIC_SHADOW
        # Fallback — should never be reached post-cleanup.
        return QuadraticRolloutMode.QUADRATIC_LIVE

    @property
    def rollback_armed_status(self) -> QuadraticRollbackArmedStatus:
        return (
            QuadraticRollbackArmedStatus.ARMED
            if self.rollback_armed
            else QuadraticRollbackArmedStatus.DISARMED
        )

    @property
    def live_profile_id(self) -> str:
        return "aurora_quadratic"

    def to_payload(self) -> dict[str, object]:
        return {
            "mode": self.mode.value,
            "requested_scoring_version": self.requested_scoring_version,
            "effective_live_scoring_version": self.effective_live_scoring_version,
            "shadow_requested": bool(self.shadow_requested),
            "rollback_armed": bool(self.rollback_armed),
            "rollback_armed_status": self.rollback_armed_status.value,
            "rollback_reason_chain": list(self.rollback_reason_chain),
            "live_profile_id": self.live_profile_id,
        }


@dataclass(frozen=True)
class QuadraticShadowEvaluation:
    state: QuadraticShadowEvaluationState
    score: float | None = None
    side: str | None = None
    thr_buy: float | None = None
    thr_sell: float | None = None
    defer_reason: str | None = None
    why_chain: tuple[str, ...] = field(default_factory=tuple)
    error: str | None = None
    psi_vector: Mapping[str, object] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "why_chain",
                           _normalize_tokens(self.why_chain))

    def to_payload(self) -> dict[str, object]:
        return {
            "state": self.state.value,
            "score": self.score,
            "side": self.side,
            "thr_buy": self.thr_buy,
            "thr_sell": self.thr_sell,
            "defer_reason": self.defer_reason,
            "why_chain": list(self.why_chain),
            "error": self.error,
            "psi_vector": dict(self.psi_vector or {}),
        }


@dataclass(frozen=True)
class QuadraticRolloutSnapshot:
    mode: QuadraticRolloutMode
    requested_scoring_version: str
    effective_live_scoring_version: str
    live_profile_id: str
    shadow_requested: bool
    shadow_evaluation: QuadraticShadowEvaluation
    quadratic_readiness_state: str
    quadratic_can_open_new_risk: bool
    protect_existing_risk_allowed: bool
    rollback_armed: bool
    rollback_armed_status: QuadraticRollbackArmedStatus
    rollback_reason_chain: tuple[str, ...] = field(default_factory=tuple)
    quadratic_blocking_reason_chain: tuple[str, ...] = field(
        default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "rollback_reason_chain",
            _normalize_tokens(self.rollback_reason_chain),
        )
        object.__setattr__(
            self,
            "quadratic_blocking_reason_chain",
            _normalize_tokens(self.quadratic_blocking_reason_chain),
        )

    def to_payload(self) -> dict[str, object]:
        return {
            "mode": self.mode.value,
            "requested_scoring_version": self.requested_scoring_version,
            "effective_live_scoring_version": self.effective_live_scoring_version,
            "live_profile_id": self.live_profile_id,
            "shadow_requested": bool(self.shadow_requested),
            "shadow_evaluation": self.shadow_evaluation.to_payload(),
            "quadratic_readiness_state": self.quadratic_readiness_state,
            "quadratic_can_open_new_risk": bool(self.quadratic_can_open_new_risk),
            "protect_existing_risk_allowed": bool(self.protect_existing_risk_allowed),
            "rollback_armed": bool(self.rollback_armed),
            "rollback_armed_status": self.rollback_armed_status.value,
            "rollback_reason_chain": list(self.rollback_reason_chain),
            "quadratic_blocking_reason_chain": list(self.quadratic_blocking_reason_chain),
        }


def resolve_requested_quadratic_rollout(decision_cfg: Any) -> RequestedQuadraticRollout:
    requested_scoring_version = str(
        getattr(decision_cfg, "scoring_version", "quadratic") or "quadratic"
    ).strip().lower()
    # Phase 9 cleanup: only "quadratic" is valid. Reject anything else loudly.
    if requested_scoring_version not in _VALID_SCORING_VERSIONS:
        import logging as _logging
        _logging.getLogger("quadratic_rollout").critical(
            "scoring_version=%r is not in %s — forcing 'quadratic' (v2 kernel deleted, rollback impossible)",
            requested_scoring_version,
            _VALID_SCORING_VERSIONS,
        )
        requested_scoring_version = "quadratic"

    # Rollback to v2 is permanently disabled — v2 kernel has been deleted.
    # rollback_armed is read for telemetry/observability only but has no runtime effect.
    rollout_cfg = getattr(decision_cfg, "quadratic_rollout", None)

    shadow_enabled_raw = getattr(rollout_cfg, "shadow_enabled", False)
    shadow_enabled = shadow_enabled_raw if isinstance(
        shadow_enabled_raw, bool) else False

    rollback_armed_raw = getattr(rollout_cfg, "rollback_armed", False)
    rollback_armed = rollback_armed_raw if isinstance(
        rollback_armed_raw, bool) else False

    rollback_reason_chain_raw = getattr(
        rollout_cfg, "rollback_reason_chain", ())
    if not isinstance(rollback_reason_chain_raw, (list, tuple, set)):
        rollback_reason_chain_raw = ()

    if rollback_armed:
        import logging as _logging
        _logging.getLogger("quadratic_rollout").warning(
            "rollback_armed=True in config but v2 kernel is deleted — "
            "rollback is non-operational. Proceeding with quadratic."
        )

    # effective_live_scoring_version is ALWAYS quadratic — no v2 fallback path.
    effective_live_scoring_version = "quadratic"

    shadow_requested = shadow_enabled

    return RequestedQuadraticRollout(
        requested_scoring_version=requested_scoring_version,
        effective_live_scoring_version=effective_live_scoring_version,
        shadow_requested=shadow_requested,
        rollback_armed=False,  # Always disarmed — v2 path deleted
        rollback_reason_chain=_normalize_tokens(rollback_reason_chain_raw),
    )


def not_requested_shadow_evaluation() -> QuadraticShadowEvaluation:
    return QuadraticShadowEvaluation(
        state=QuadraticShadowEvaluationState.NOT_REQUESTED,
    )


def evaluate_quadratic_shadow(
    *,
    requested_rollout: RequestedQuadraticRollout,
    compute_kwargs: Mapping[str, Any],
    shield_fn: Any = None,
    pillar_contribs: Mapping[str, float] | None = None,
    score_multiplier: float = 1.0,
    regime_smoother: Any = None,
) -> QuadraticShadowEvaluation:
    if not requested_rollout.shadow_requested:
        return not_requested_shadow_evaluation()

    shadow_kwargs = dict(compute_kwargs)
    try:
        result = QuadraticScoringKernel.compute(
            **shadow_kwargs,
            shield_fn=shield_fn,
            pillar_contribs=dict(pillar_contribs or {}),
            score_multiplier=float(score_multiplier),
            regime_smoother=regime_smoother,
        )
    except Exception as exc:
        return QuadraticShadowEvaluation(
            state=QuadraticShadowEvaluationState.FAILED,
            error=str(exc),
        )

    if bool(getattr(result, "deferred", False)):
        return QuadraticShadowEvaluation(
            state=QuadraticShadowEvaluationState.DEFERRED,
            defer_reason=str(getattr(result, "defer_reason", "") or ""),
            why_chain=getattr(result, "why_chain", ()),
            psi_vector=getattr(result, "psi_vector", {}) or {},
        )

    return QuadraticShadowEvaluation(
        state=QuadraticShadowEvaluationState.READY,
        score=float(getattr(result, "score", 0.0)),
        side=(str(getattr(result, "side", "") or "").upper() or None),
        thr_buy=float(getattr(result, "thr_buy", 0.0)),
        thr_sell=float(getattr(result, "thr_sell", 0.0)),
        why_chain=getattr(result, "why_chain", ()),
        psi_vector=getattr(result, "psi_vector", {}) or {},
    )


def build_quadratic_rollout_snapshot(
    *,
    requested_rollout: RequestedQuadraticRollout,
    quadratic_readiness: RuntimeReadinessStatus,
    runtime_permissions: RuntimePermissions,
    shadow_evaluation: QuadraticShadowEvaluation | None = None,
) -> QuadraticRolloutSnapshot:
    blocking_reason_chain: list[str] = []
    if requested_rollout.rollback_armed:
        blocking_reason_chain.append("quadratic_rollback_armed")
        blocking_reason_chain.extend(requested_rollout.rollback_reason_chain)
    if quadratic_readiness.state != RuntimeReadinessState.READY:
        blocking_reason_chain.append("quadratic_htf_not_ready")
        blocking_reason_chain.append(
            f"quadratic_htf_state:{quadratic_readiness.state.value}")
    if not runtime_permissions.can_open_new_risk:
        blocking_reason_chain.append("runtime_open_new_risk_blocked")
    blocking_reason_chain = list(dict.fromkeys(
        _normalize_tokens(blocking_reason_chain)))

    quadratic_can_open_new_risk = (
        (not requested_rollout.rollback_armed)
        and quadratic_readiness.state == RuntimeReadinessState.READY
        and runtime_permissions.can_open_new_risk
    )

    return QuadraticRolloutSnapshot(
        mode=requested_rollout.mode,
        requested_scoring_version=requested_rollout.requested_scoring_version,
        effective_live_scoring_version=requested_rollout.effective_live_scoring_version,
        live_profile_id=requested_rollout.live_profile_id,
        shadow_requested=requested_rollout.shadow_requested,
        shadow_evaluation=shadow_evaluation or not_requested_shadow_evaluation(),
        quadratic_readiness_state=quadratic_readiness.state.value,
        quadratic_can_open_new_risk=quadratic_can_open_new_risk,
        protect_existing_risk_allowed=runtime_permissions.can_manage_existing_risk,
        rollback_armed=requested_rollout.rollback_armed,
        rollback_armed_status=requested_rollout.rollback_armed_status,
        rollback_reason_chain=requested_rollout.rollback_reason_chain,
        quadratic_blocking_reason_chain=tuple(blocking_reason_chain),
    )


def apply_live_quadratic_permission_gate(
    permissions: RuntimePermissions,
    rollout: QuadraticRolloutSnapshot,
) -> RuntimePermissions:
    # Phase 9: always quadratic, always apply the gate.
    return make_permissions(
        can_manage_existing_risk=permissions.can_manage_existing_risk,
        can_open_new_risk=(
            permissions.can_open_new_risk and rollout.quadratic_can_open_new_risk
        ),
    )


def build_startup_quadratic_rollout_report(
    *,
    config: Any,
    updated_at: int,
    source: str,
) -> dict[str, object]:
    aurora_cfg = getattr(getattr(config, "strategies", None), "aurora", None)
    decision_cfg = getattr(aurora_cfg, "decision", None)
    requested_rollout = resolve_requested_quadratic_rollout(decision_cfg)
    payload = requested_rollout.to_payload()
    payload.update(
        {
            "updated_at": int(updated_at),
            "source": str(source),
            "strategy_id": "aurora",
        }
    )
    return payload
