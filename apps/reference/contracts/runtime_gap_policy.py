from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Mapping

from apps.reference.contracts.runtime_bar_identity import (
    RuntimeBarSourceMode,
    extract_canonical_bar_identity,
    normalize_source_mode,
)
from apps.reference.contracts.runtime_readiness import (
    RuntimeReadinessState,
    RuntimeReadinessStatus,
    blocked_status,
    make_status,
    ready_status,
)


class RuntimeGapState(str, Enum):
    CLEAR = "CLEAR"
    GAP_DETECTED = "GAP_DETECTED"
    REPAIRED = "REPAIRED"
    INVALIDATED = "INVALIDATED"


class RuntimeGapPolicyAction(str, Enum):
    NONE = "NONE"
    REPAIR = "REPAIR"
    INVALIDATE = "INVALIDATE"
    DEGRADE_TO_NON_TRADING = "DEGRADE_TO_NON_TRADING"


def _normalize_why_tokens(why: str | Iterable[str] | None) -> tuple[str, ...]:
    if why is None:
        return ()
    if isinstance(why, str):
        value = why.strip()
        return (value,) if value else ()
    normalized: list[str] = []
    for token in why:
        value = str(token).strip()
        if value:
            normalized.append(value)
    return tuple(normalized)


def _first_int(*values: Any) -> int | None:
    for value in values:
        if value is None:
            continue
        try:
            return int(value)
        except Exception:
            continue
    return None


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


@dataclass(frozen=True)
class RuntimeGapStatus:
    state: RuntimeGapState
    policy_action: RuntimeGapPolicyAction
    gap_bars_skipped: int = 0
    is_gap_bar: bool = False
    why: tuple[str, ...] = field(default_factory=tuple)
    detected_at: int | None = None
    source: str = ""
    evidence_ref: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "why", _normalize_why_tokens(self.why))

    @property
    def is_clear(self) -> bool:
        return self.state == RuntimeGapState.CLEAR and self.policy_action == RuntimeGapPolicyAction.NONE

    def to_payload(self) -> dict[str, object]:
        return {
            "state": self.state.value,
            "policy_action": self.policy_action.value,
            "gap_bars_skipped": int(self.gap_bars_skipped),
            "is_gap_bar": bool(self.is_gap_bar),
            "why": list(self.why),
            "detected_at": self.detected_at,
            "source": self.source,
            "evidence_ref": self.evidence_ref,
        }


def build_gap_status(
    *,
    state: RuntimeGapState | str,
    policy_action: RuntimeGapPolicyAction | str,
    gap_bars_skipped: int = 0,
    is_gap_bar: bool = False,
    why: str | Iterable[str] | None = None,
    detected_at: int | None = None,
    source: str,
    evidence_ref: str | None = None,
) -> RuntimeGapStatus:
    state_value = state.value if isinstance(state, RuntimeGapState) else str(state)
    action_value = (
        policy_action.value
        if isinstance(policy_action, RuntimeGapPolicyAction)
        else str(policy_action)
    )
    return RuntimeGapStatus(
        state=RuntimeGapState(state_value),
        policy_action=RuntimeGapPolicyAction(action_value),
        gap_bars_skipped=max(0, int(gap_bars_skipped)),
        is_gap_bar=bool(is_gap_bar),
        why=_normalize_why_tokens(why),
        detected_at=detected_at,
        source=str(source),
        evidence_ref=evidence_ref,
    )


def default_gap_status(
    *,
    detected_at: int | None,
    source: str,
    evidence_ref: str | None = None,
) -> RuntimeGapStatus:
    return build_gap_status(
        state=RuntimeGapState.CLEAR,
        policy_action=RuntimeGapPolicyAction.NONE,
        gap_bars_skipped=0,
        is_gap_bar=False,
        why=["contiguous"],
        detected_at=detected_at,
        source=source,
        evidence_ref=evidence_ref,
    )


def extract_gap_status(
    payload: Mapping[str, Any] | None,
    *,
    default_source: str = "market_data",
    default_source_mode: RuntimeBarSourceMode = RuntimeBarSourceMode.LIVE,
) -> RuntimeGapStatus | None:
    if not isinstance(payload, Mapping):
        return None

    identity = extract_canonical_bar_identity(
        payload,
        default_source_mode=default_source_mode,
    )
    evidence_ref = identity.to_ref() if identity is not None else None
    detected_at = (
        int(identity.bar_end_ts_ms)
        if identity is not None
        else _first_int(payload.get("bar_close_ts"), payload.get("ts_ms"), payload.get("ts"))
    )

    raw_gap = payload.get("gap")
    if isinstance(raw_gap, Mapping):
        try:
            return build_gap_status(
                state=raw_gap.get("state", RuntimeGapState.CLEAR.value),
                policy_action=raw_gap.get("policy_action", RuntimeGapPolicyAction.NONE.value),
                gap_bars_skipped=int(raw_gap.get("gap_bars_skipped", 0) or 0),
                is_gap_bar=_coerce_bool(raw_gap.get("is_gap_bar", False)),
                why=raw_gap.get("why"),
                detected_at=_first_int(raw_gap.get("detected_at"), detected_at),
                source=str(raw_gap.get("source") or default_source),
                evidence_ref=str(raw_gap.get("evidence_ref") or evidence_ref) if (raw_gap.get("evidence_ref") or evidence_ref) else None,
            )
        except Exception:
            pass

    if "gap_state" in payload or "gap_policy_action" in payload:
        try:
            return build_gap_status(
                state=payload.get("gap_state", RuntimeGapState.CLEAR.value),
                policy_action=payload.get("gap_policy_action", RuntimeGapPolicyAction.NONE.value),
                gap_bars_skipped=int(payload.get("gap_bars_skipped", 0) or 0),
                is_gap_bar=_coerce_bool(payload.get("is_gap_bar", False)),
                why=payload.get("gap_why"),
                detected_at=detected_at,
                source=str(payload.get("gap_source") or default_source),
                evidence_ref=str(payload.get("gap_evidence_ref") or evidence_ref) if (payload.get("gap_evidence_ref") or evidence_ref) else None,
            )
        except Exception:
            pass

    bar_raw = payload.get("bar")
    bar = bar_raw if isinstance(bar_raw, Mapping) else {}
    nested_gap = bar.get("gap")
    if isinstance(nested_gap, Mapping):
        try:
            return build_gap_status(
                state=nested_gap.get("state", RuntimeGapState.CLEAR.value),
                policy_action=nested_gap.get("policy_action", RuntimeGapPolicyAction.NONE.value),
                gap_bars_skipped=int(nested_gap.get("gap_bars_skipped", 0) or 0),
                is_gap_bar=_coerce_bool(nested_gap.get("is_gap_bar", False)),
                why=nested_gap.get("why"),
                detected_at=_first_int(nested_gap.get("detected_at"), detected_at),
                source=str(nested_gap.get("source") or default_source),
                evidence_ref=str(nested_gap.get("evidence_ref") or evidence_ref) if (nested_gap.get("evidence_ref") or evidence_ref) else None,
            )
        except Exception:
            pass

    source_mode = normalize_source_mode(
        payload.get("source_mode") or bar.get("source_mode"),
        default=default_source_mode,
    )
    gap_bars_skipped = max(
        0,
        int(
            _first_int(
                payload.get("gap_bars_skipped"),
                bar.get("gap_bars_skipped"),
            )
            or 0
        ),
    )
    is_gap_bar = _coerce_bool(
        payload.get("is_gap_bar")
        if "is_gap_bar" in payload
        else bar.get("is_gap_bar", gap_bars_skipped > 0)
    )
    if gap_bars_skipped > 0 or is_gap_bar:
        policy_action = RuntimeGapPolicyAction.DEGRADE_TO_NON_TRADING
        state = RuntimeGapState.GAP_DETECTED
        if source_mode == RuntimeBarSourceMode.SYNTHETIC_REPAIR:
            policy_action = RuntimeGapPolicyAction.REPAIR
        why = ["gap_detected", f"gap_bars_skipped:{gap_bars_skipped}", policy_action.value.lower()]
        return build_gap_status(
            state=state,
            policy_action=policy_action,
            gap_bars_skipped=gap_bars_skipped,
            is_gap_bar=is_gap_bar,
            why=why,
            detected_at=detected_at,
            source=default_source,
            evidence_ref=evidence_ref,
        )

    if identity is None and not isinstance(bar_raw, Mapping):
        return None
    return default_gap_status(
        detected_at=detected_at,
        source=default_source,
        evidence_ref=evidence_ref,
    )


def attach_gap_status_payload(
    payload: dict[str, Any],
    *,
    gap: RuntimeGapStatus,
    attach_nested_bar: bool = True,
) -> dict[str, Any]:
    payload["gap"] = gap.to_payload()
    payload["gap_state"] = gap.state.value
    payload["gap_policy_action"] = gap.policy_action.value
    payload["gap_bars_skipped"] = int(gap.gap_bars_skipped)
    payload["is_gap_bar"] = bool(gap.is_gap_bar)

    if attach_nested_bar:
        bar = payload.get("bar")
        if isinstance(bar, dict):
            bar["gap"] = gap.to_payload()
            bar["gap_state"] = gap.state.value
            bar["gap_policy_action"] = gap.policy_action.value
            bar["gap_bars_skipped"] = int(gap.gap_bars_skipped)
            bar["is_gap_bar"] = bool(gap.is_gap_bar)
    return payload


def gap_blocks_open_new_risk(gap: RuntimeGapStatus | None) -> bool:
    if gap is None:
        return False
    return gap.policy_action in {
        RuntimeGapPolicyAction.REPAIR,
        RuntimeGapPolicyAction.INVALIDATE,
        RuntimeGapPolicyAction.DEGRADE_TO_NON_TRADING,
    }


def gap_blocking_tokens(gap: RuntimeGapStatus | None) -> tuple[str, ...]:
    if gap is None or gap.is_clear:
        return ()
    tokens = ["basis_bar_gap", gap.state.value.lower(), gap.policy_action.value.lower()]
    if int(gap.gap_bars_skipped) > 0:
        tokens.append(f"gap_bars_skipped:{int(gap.gap_bars_skipped)}")
    return tuple(tokens)


def build_basis_bar_status_from_gap(
    gap: RuntimeGapStatus | None,
    *,
    updated_at: int | None,
    source: str,
    evidence_ref: str | None = None,
) -> RuntimeReadinessStatus:
    evidence_ref = evidence_ref or (gap.evidence_ref if gap is not None else None)
    if gap is None or gap.is_clear or gap.state == RuntimeGapState.REPAIRED:
        return ready_status(
            why=["basis_bar_contiguous"],
            updated_at=updated_at,
            source=source,
            evidence_ref=evidence_ref,
        )
    return make_status(
        state=RuntimeReadinessState.INVALIDATED_GAP,
        why=gap_blocking_tokens(gap),
        updated_at=updated_at,
        source=source,
        evidence_ref=evidence_ref,
    )


def build_trading_status_from_gap(
    gap: RuntimeGapStatus | None,
    *,
    updated_at: int | None,
    source: str,
    evidence_ref: str | None = None,
    allow_open_new_risk: bool = True,
    open_ready_why: str | Iterable[str] | None = None,
    blocked_why: str | Iterable[str] | None = None,
) -> RuntimeReadinessStatus:
    evidence_ref = evidence_ref or (gap.evidence_ref if gap is not None else None)
    if allow_open_new_risk and not gap_blocks_open_new_risk(gap):
        return ready_status(
            why=open_ready_why or ["open_new_risk_allowed"],
            updated_at=updated_at,
            source=source,
            evidence_ref=evidence_ref,
        )

    why_tokens = list(_normalize_why_tokens(blocked_why))
    if gap_blocks_open_new_risk(gap):
        for token in gap_blocking_tokens(gap):
            if token not in why_tokens:
                why_tokens.append(token)
    if not why_tokens:
        why_tokens.append("protect_only")
    return blocked_status(
        why=why_tokens,
        updated_at=updated_at,
        source=source,
        evidence_ref=evidence_ref,
    )
