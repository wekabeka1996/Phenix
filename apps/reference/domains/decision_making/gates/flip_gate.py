"""Flip gate — GATE 2 in the strategy gateway pipeline.

Checks for opposite-side position (flip) or same-side pyramiding.
Extracted from strategy_gateway.py lines 662–682.
"""
from __future__ import annotations

from apps.reference.domains.decision_making.gateway.protocol import GateContext, GateOutcome, GateResult

GATE_NAME = "flip"


def check(ctx: GateContext) -> GateResult:
    dm = ctx.dm

    flip_result = dm._handle_flip_orchestration(
        symbol=ctx.symbol, intent_side=ctx.side,
        original_pld=ctx.pld, source=ctx.strategy_id)

    if flip_result:
        if flip_result == "NRR-PORTFOLIO-UNKNOWN":
            stale_ttl = ctx.config.domains.position_tracking.positions_stale_ttl_sec
            if stale_ttl is None:
                raise ValueError("positions_stale_ttl_sec required (SSOT)")
            return GateResult(
                outcome=GateOutcome.DEFER,
                gate_name=GATE_NAME,
                reason_code="NRR-PORTFOLIO-UNKNOWN",
                reason="NRR-PORTFOLIO-UNKNOWN",
                context="strategy_gateway_flip_check",
                why_extra=["portfolio_unknown", "fail_closed"],
                context_update={"_defer_stale_ttl": stale_ttl},
            )
        # Any other flip_result means the flip was handled (close emitted
        # + intent deferred) or blocked.
        return GateResult(
            outcome=GateOutcome.REJECT,
            gate_name=GATE_NAME,
            reason_code=str(flip_result),
            reason=str(flip_result),
            context="strategy_signal_gateway:flip_unknown_state",
        )

    # Gate passed — check if this was a pyramiding add and carry forward metadata
    pyramiding_info = getattr(
        getattr(dm, "_flip", None), "_last_pyramiding_add_info", None
    )
    if pyramiding_info:
        return GateResult.passed(GATE_NAME, pyramiding_add_info=dict(pyramiding_info))

    return GateResult.passed(GATE_NAME)
