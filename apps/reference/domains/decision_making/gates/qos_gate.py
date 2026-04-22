"""QoS gate — GATE 3 in the strategy gateway pipeline.

Rate-limiting per symbol/strategy.  Extracted from strategy_gateway.py
lines 684–712.
"""
from __future__ import annotations

import logging

from ..gate_protocol import GateContext, GateOutcome, GateResult

GATE_NAME = "qos"
logger = logging.getLogger("domain_decision_making")


def check(ctx: GateContext) -> GateResult:
    dm = ctx.dm
    symbol = ctx.symbol

    qos_enabled = dm._qos_enabled_for_strategy(ctx.strategy_id)
    if not qos_enabled:
        ctx.accumulated["_qos_enabled"] = False
        return GateResult.passed(GATE_NAME)

    ctx.accumulated["_qos_enabled"] = True

    qos_ok, qos_reason = dm._qos_allow(symbol, strategy_id=ctx.strategy_id)
    if qos_ok:
        return GateResult.passed(GATE_NAME)

    mode = dm.qos_mode
    if dm.qos_enforce and mode == "defer":
        mode = "enforce"

    if mode == "shadow":
        logger.warning(
            "[%s] STRATEGY_SIGNAL_GATEWAY: QoS shadow (reason: %s)",
            symbol, qos_reason)
        return GateResult.passed(GATE_NAME)

    if mode == "defer":
        next_ts = int(dm._calculate_next_allowed_time(
            symbol, strategy_id=ctx.strategy_id))
        return GateResult(
            outcome=GateOutcome.DEFER,
            gate_name=GATE_NAME,
            reason_code=str(qos_reason or "qos_defer"),
            reason=str(qos_reason or "qos_defer"),
            context="strategy_gateway_qos",
            why_extra=["qos", "defer"],
            context_update={"_defer_next_ts": next_ts},
        )

    # enforce mode
    return GateResult(
        outcome=GateOutcome.REJECT,
        gate_name=GATE_NAME,
        reason_code="QOS_RATE_LIMIT",
        reason="QOS",
        context=f"strategy_signal_gateway:qos_rejected:{qos_reason}",
    )
