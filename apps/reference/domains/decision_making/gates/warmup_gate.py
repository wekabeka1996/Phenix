"""Warmup gate — GATE 6 in the strategy gateway pipeline.

Checks warmup readiness before allowing trade intent emission.
Extracted from strategy_gateway.py lines 821–825.
"""
from __future__ import annotations

from ..gate_protocol import GateContext, GateOutcome, GateResult

GATE_NAME = "warmup"


def check(ctx: GateContext) -> GateResult:
    dm = ctx.dm

    # dm._warmup_gate_before_trade_intent returns True when trade SHOULD BE
    # blocked (i.e. warmup not ready).  It also handles its own defer emission
    # internally.  We return BLOCK so the chain stops but the gateway knows
    # the defer was already emitted.
    blocked = dm._warmup_gate_before_trade_intent(
        symbol=ctx.symbol, rid=ctx.rid,
        reduce_only=False,
        context="strategy_signal_gateway:pre_emit",
    )
    if blocked:
        return GateResult(
            outcome=GateOutcome.BLOCK,
            gate_name=GATE_NAME,
            reason_code="WARMUP_NOT_READY",
            context="strategy_signal_gateway:warmup_gate",
        )

    return GateResult.passed(GATE_NAME)
