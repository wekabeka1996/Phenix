"""Safety gate adapter — wraps apply_safety_gates() as a GateFunc.

Package 4, Slice 4.2.  Thin adapter mapping SafetyGateResult → GateResult.
The underlying safety_gates.py module is NOT modified.
"""
from __future__ import annotations

import logging

from ..gate_protocol import GateContext, GateOutcome, GateResult
from ..safety_gates import apply_safety_gates, SafetyGateResult

GATE_NAME = "safety"
logger = logging.getLogger("domain_decision_making")


def check(ctx: GateContext) -> GateResult:
    dm = ctx.dm

    per_symbol_regimes = getattr(dm, "_per_symbol_regimes", {})
    system_stress_states = getattr(dm, "_system_stress_states", None)

    try:
        sg = apply_safety_gates(
            symbol=ctx.symbol,
            side=ctx.side,
            reduce_only=ctx.is_reduce_path,
            strategy_id=ctx.strategy_id,
            decision_ts_ms=ctx.ts_ms,
            why_chain=ctx.why_chain,
            config=ctx.config,
            clock=ctx.clock,
            symbol_states=ctx.symbol_states,
            per_symbol_regimes=per_symbol_regimes,
            system_stress_states=system_stress_states,
        )
    except Exception as exc:
        # Safety gates config is incomplete — treat as bypass (ALLOW).
        # This mirrors the old inline behavior where apply_safety_gates()
        # ran inside _propose_trade_intent() behind a try/except.
        logger.warning(
            "[%s] safety_gate: apply_safety_gates raised %s — bypassing",
            ctx.symbol, exc)
        sg = SafetyGateResult(outcome="ALLOW")

    # Carry the full SafetyGateResult forward — the dispatcher needs it
    # for decision_trace emission and intent builder context.
    ctx.accumulated["safety_gate_result"] = sg

    if sg.outcome == "CONFIG_ERROR":
        return GateResult(
            outcome=GateOutcome.REJECT,
            gate_name=GATE_NAME,
            reason_code=sg.deny_reason or "CONFIG_SAFETY_GATES_MISSING",
            reason="CONFIG_ERROR",
            context=sg.config_error_context or "safety_gates:config_error",
        )

    if sg.outcome == "DENY":
        return GateResult(
            outcome=GateOutcome.REJECT,
            gate_name=GATE_NAME,
            reason_code=sg.deny_reason or "SAFETY_GATE_DENIED",
            reason="DECISION",
            context=f"safety_gates:deny:{sg.why_short}",
        )

    return GateResult.passed(GATE_NAME)
