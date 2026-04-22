"""Arbitration gate — GATE 0 in the strategy gateway pipeline.

Checks whether the symbol+strategy combination is allowed by the
strategy arbitration system.  Extracted from strategy_gateway.py lines 402–414.
"""
from __future__ import annotations

from ..gate_protocol import GateContext, GateOutcome, GateResult

GATE_NAME = "arbitration"


def check(ctx: GateContext) -> GateResult:
    dm = ctx.dm
    arb = dm._check_strategy_arbitration(
        ctx.symbol, ctx.strategy_id,
        ts_ms=ctx.ts_ms,
        commit=False,
    )
    if not arb["allowed"]:
        return GateResult(
            outcome=GateOutcome.REJECT,
            gate_name=GATE_NAME,
            reason_code="ARBITRATION_BLOCKED",
            reason="ARBITRATION",
            context="strategy_signal_gateway:arbitration",
            details={"arbitration_reason": arb.get("reason")},
        )
    return GateResult.passed(GATE_NAME)
