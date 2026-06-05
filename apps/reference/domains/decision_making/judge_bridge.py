from __future__ import annotations

import hashlib
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from apps.reference.config.domains.decision_making import (
    JudgeBridgeConfig,
    MANDATORY_JUDGE_BRIDGE_HARD_GATES,
)
from apps.reference.domains.alpha_search.judge.central_brain.verdict import (
    JudgePolicyVerdictV2,
)


SCHEMA_VERSION = "1.0.0"

BridgeAction = Literal["record_only", "allow", "suppress", "skip", "blocked"]


class JudgeBridgeCandidateContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    decision_id: str | None = None
    symbol: str = Field(min_length=1)
    side: str | None = None
    candidate_exists: bool
    hard_gate_results: dict[str, bool] = Field(default_factory=dict)
    hard_gate_blocking_reasons: list[str] = Field(default_factory=list)


class JudgeBridgeSourceRefs(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    envelope_id: str = Field(min_length=1)
    rid: str | None = None
    cycle_key: str | None = None


class JudgeBridgeDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0.0"] = SCHEMA_VERSION
    bridge_decision_id: str = Field(min_length=1)
    source_verdict_id: str = Field(min_length=1)
    decision_id: str | None = None
    symbol: str = Field(min_length=1)
    runtime_mode: str = Field(min_length=1)
    authority_mode: Literal["shadow", "advisory", "hybrid_gated", "live_gated"]
    bridge_action: BridgeAction
    applied: bool
    no_effect: bool
    reason_codes: list[str] = Field(min_length=1)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    confidence_band_label: str | None = None
    hard_gates_passed: bool
    hard_gate_blocking_reasons: list[str] = Field(default_factory=list)
    unknown_policy_applied: bool
    source_refs: JudgeBridgeSourceRefs


def _normalize_side(side: str | None) -> str | None:
    if side is None:
        return None
    normalized = str(side).strip().upper()
    if normalized in {"BUY", "LONG"}:
        return "BUY"
    if normalized in {"SELL", "SHORT"}:
        return "SELL"
    if normalized in {"NONE", "UNKNOWN", ""}:
        return None
    return normalized


def _bridge_decision_id(
    *,
    verdict: JudgePolicyVerdictV2,
    runtime_mode: str,
    action: str,
) -> str:
    raw = "|".join(
        [
            verdict.verdict_id,
            verdict.envelope_id,
            str(verdict.created_ts_ms),
            runtime_mode,
            action,
        ]
    )
    return "judge_bridge_v1_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _hard_gate_status(
    config: JudgeBridgeConfig,
    candidate_context: JudgeBridgeCandidateContext,
) -> tuple[bool, list[str]]:
    reasons = list(candidate_context.hard_gate_blocking_reasons)
    for gate in config.hard_gates.judge_cannot_override:
        if gate in MANDATORY_JUDGE_BRIDGE_HARD_GATES:
            value = candidate_context.hard_gate_results.get(gate)
            if value is not True:
                reason = f"hard_gate_blocked:{gate}"
                if reason not in reasons:
                    reasons.append(reason)
    return not reasons, reasons


def _confidence_in_band(
    confidence: float | None,
    bands: list,
) -> tuple[bool, str | None]:
    if confidence is None:
        return False, None
    for band in bands:
        if band.min <= confidence <= band.max:
            return True, f"{band.action}:{band.min:.2f}-{band.max:.2f}"
    return False, None


def _decision(
    *,
    verdict: JudgePolicyVerdictV2,
    candidate_context: JudgeBridgeCandidateContext,
    config: JudgeBridgeConfig,
    runtime_mode: str,
    action: BridgeAction,
    applied: bool,
    no_effect: bool,
    reason_codes: list[str],
    hard_gates_passed: bool,
    hard_gate_blocking_reasons: list[str],
    unknown_policy_applied: bool = False,
    confidence_band_label: str | None = None,
) -> JudgeBridgeDecision:
    return JudgeBridgeDecision(
        bridge_decision_id=_bridge_decision_id(
            verdict=verdict,
            runtime_mode=runtime_mode,
            action=action,
        ),
        source_verdict_id=verdict.verdict_id,
        decision_id=candidate_context.decision_id,
        symbol=candidate_context.symbol,
        runtime_mode=runtime_mode,
        authority_mode=config.authority_mode,
        bridge_action=action,
        applied=applied,
        no_effect=no_effect,
        reason_codes=reason_codes,
        confidence=verdict.confidence,
        confidence_band_label=confidence_band_label,
        hard_gates_passed=hard_gates_passed,
        hard_gate_blocking_reasons=hard_gate_blocking_reasons,
        unknown_policy_applied=unknown_policy_applied,
        source_refs=JudgeBridgeSourceRefs(
            envelope_id=verdict.source_refs.envelope_id,
            rid=verdict.source_refs.rid,
            cycle_key=verdict.source_refs.cycle_key,
        ),
    )


def evaluate_judge_bridge(
    verdict: JudgePolicyVerdictV2,
    config: JudgeBridgeConfig,
    runtime_mode: str,
    candidate_context: JudgeBridgeCandidateContext,
) -> JudgeBridgeDecision:
    hard_gates_passed, hard_gate_reasons = _hard_gate_status(
        config,
        candidate_context,
    )
    if config.authority_mode == "shadow":
        return _decision(
            verdict=verdict,
            candidate_context=candidate_context,
            config=config,
            runtime_mode=runtime_mode,
            action="record_only",
            applied=False,
            no_effect=True,
            reason_codes=["mode:shadow", "record_only"],
            hard_gates_passed=hard_gates_passed,
            hard_gate_blocking_reasons=hard_gate_reasons,
        )
    if config.authority_mode == "advisory":
        return _decision(
            verdict=verdict,
            candidate_context=candidate_context,
            config=config,
            runtime_mode=runtime_mode,
            action="record_only",
            applied=False,
            no_effect=True,
            reason_codes=["mode:advisory", "recommendation_only"],
            hard_gates_passed=hard_gates_passed,
            hard_gate_blocking_reasons=hard_gate_reasons,
        )
    if not config.enabled:
        return _decision(
            verdict=verdict,
            candidate_context=candidate_context,
            config=config,
            runtime_mode=runtime_mode,
            action="skip",
            applied=False,
            no_effect=True,
            reason_codes=["bridge_disabled"],
            hard_gates_passed=hard_gates_passed,
            hard_gate_blocking_reasons=hard_gate_reasons,
        )
    if config.authority_mode == "live_gated":
        return _decision(
            verdict=verdict,
            candidate_context=candidate_context,
            config=config,
            runtime_mode=runtime_mode,
            action="blocked",
            applied=False,
            no_effect=True,
            reason_codes=["live_gated_blocked_in_phase_7"],
            hard_gates_passed=hard_gates_passed,
            hard_gate_blocking_reasons=hard_gate_reasons,
        )
    if runtime_mode in config.forbidden_runtime_modes:
        return _decision(
            verdict=verdict,
            candidate_context=candidate_context,
            config=config,
            runtime_mode=runtime_mode,
            action="blocked",
            applied=False,
            no_effect=True,
            reason_codes=["runtime_mode_forbidden"],
            hard_gates_passed=hard_gates_passed,
            hard_gate_blocking_reasons=hard_gate_reasons,
        )
    if runtime_mode not in config.allowed_runtime_modes:
        return _decision(
            verdict=verdict,
            candidate_context=candidate_context,
            config=config,
            runtime_mode=runtime_mode,
            action="blocked",
            applied=False,
            no_effect=True,
            reason_codes=["runtime_mode_not_allowed"],
            hard_gates_passed=hard_gates_passed,
            hard_gate_blocking_reasons=hard_gate_reasons,
        )
    if not candidate_context.candidate_exists:
        return _decision(
            verdict=verdict,
            candidate_context=candidate_context,
            config=config,
            runtime_mode=runtime_mode,
            action="skip",
            applied=False,
            no_effect=True,
            reason_codes=["candidate_missing", "bridge_cannot_create_candidate"],
            hard_gates_passed=hard_gates_passed,
            hard_gate_blocking_reasons=hard_gate_reasons,
        )
    if not hard_gates_passed:
        return _decision(
            verdict=verdict,
            candidate_context=candidate_context,
            config=config,
            runtime_mode=runtime_mode,
            action="blocked",
            applied=False,
            no_effect=True,
            reason_codes=["hard_gate_blocked"],
            hard_gates_passed=False,
            hard_gate_blocking_reasons=hard_gate_reasons,
        )

    if verdict.verdict == "UNKNOWN":
        return _decision(
            verdict=verdict,
            candidate_context=candidate_context,
            config=config,
            runtime_mode=runtime_mode,
            action="blocked",
            applied=False,
            no_effect=True,
            reason_codes=[f"unknown_policy:{config.confidence_policy.unknown_policy}"],
            hard_gates_passed=True,
            hard_gate_blocking_reasons=[],
            unknown_policy_applied=True,
        )
    if verdict.verdict == "NO_ENTRY":
        return _decision(
            verdict=verdict,
            candidate_context=candidate_context,
            config=config,
            runtime_mode=runtime_mode,
            action="blocked",
            applied=False,
            no_effect=True,
            reason_codes=["no_entry_policy_undefined_fail_closed"],
            hard_gates_passed=True,
            hard_gate_blocking_reasons=[],
        )
    if verdict.verdict in {"OPEN_LONG", "OPEN_SHORT"}:
        expected_side = "BUY" if verdict.verdict == "OPEN_LONG" else "SELL"
        candidate_side = _normalize_side(candidate_context.side)
        if candidate_side != expected_side:
            return _decision(
                verdict=verdict,
                candidate_context=candidate_context,
                config=config,
                runtime_mode=runtime_mode,
                action="blocked",
                applied=False,
                no_effect=True,
                reason_codes=["candidate_side_mismatch"],
                hard_gates_passed=True,
                hard_gate_blocking_reasons=[],
            )
        matched, label = _confidence_in_band(
            verdict.confidence,
            config.confidence_policy.open_bands,
        )
        if not matched:
            return _decision(
                verdict=verdict,
                candidate_context=candidate_context,
                config=config,
                runtime_mode=runtime_mode,
                action="blocked",
                applied=False,
                no_effect=True,
                reason_codes=["confidence_not_in_open_band"],
                hard_gates_passed=True,
                hard_gate_blocking_reasons=[],
            )
        return _decision(
            verdict=verdict,
            candidate_context=candidate_context,
            config=config,
            runtime_mode=runtime_mode,
            action="allow",
            applied=True,
            no_effect=False,
            reason_codes=["hybrid_gated_allow_existing_candidate"],
            hard_gates_passed=True,
            hard_gate_blocking_reasons=[],
            confidence_band_label=label,
        )
    if verdict.verdict == "SUPPRESS":
        matched, label = _confidence_in_band(
            verdict.confidence,
            config.confidence_policy.suppress_bands,
        )
        if not matched:
            return _decision(
                verdict=verdict,
                candidate_context=candidate_context,
                config=config,
                runtime_mode=runtime_mode,
                action="blocked",
                applied=False,
                no_effect=True,
                reason_codes=["confidence_not_in_suppress_band"],
                hard_gates_passed=True,
                hard_gate_blocking_reasons=[],
            )
        return _decision(
            verdict=verdict,
            candidate_context=candidate_context,
            config=config,
            runtime_mode=runtime_mode,
            action="suppress",
            applied=True,
            no_effect=False,
            reason_codes=["hybrid_gated_suppress_existing_candidate"],
            hard_gates_passed=True,
            hard_gate_blocking_reasons=[],
            confidence_band_label=label,
        )
    return _decision(
        verdict=verdict,
        candidate_context=candidate_context,
        config=config,
        runtime_mode=runtime_mode,
        action="blocked",
        applied=False,
        no_effect=True,
        reason_codes=["unsupported_verdict_fail_closed"],
        hard_gates_passed=hard_gates_passed,
        hard_gate_blocking_reasons=hard_gate_reasons,
    )
