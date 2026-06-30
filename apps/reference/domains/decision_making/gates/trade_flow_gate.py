"""Trade-flow degraded entry gate — wraps trade-flow freshness checks as a GateFunc.

Package 6, Task C3.
"""
from __future__ import annotations

import logging

from apps.reference.domains.decision_making.contracts.normalized_reject_reasons import (
    NormalizedRejectReasons,
)
from apps.reference.domains.decision_making.gateway.protocol import (
    GateContext,
    GateOutcome,
    GateResult,
)

GATE_NAME = "trade_flow"
logger = logging.getLogger("domain_decision_making")


def check(ctx: GateContext) -> GateResult:
    dm = ctx.dm
    symbol = ctx.symbol

    # 1. Config Resolution
    dm_cfg = getattr(ctx.config.domains, "decision_making", None)
    gate_cfg = getattr(dm_cfg, "trade_flow_gate", None) if dm_cfg else None

    if not gate_cfg or not gate_cfg.enabled:
        return GateResult.passed(GATE_NAME)

    # 2. Strategy Sensitivity Check
    if ctx.strategy_id not in gate_cfg.sensitive_strategies:
        return GateResult.passed(GATE_NAME)

    # 3. Action / Intent Classification
    intent_kind = str(ctx.pld.get("intent_kind") or "ENTRY").upper()
    reduce_only = bool(ctx.pld.get("reduce_only", False))
    is_reduce_path = bool(getattr(ctx, "is_reduce_path", False))

    # Determine if this is a position-opening or position-increasing action
    is_entry = (intent_kind in gate_cfg.apply_to) and (not reduce_only) and (not is_reduce_path)

    # Explicitly preserve risk-reducing / close actions
    if not is_entry or intent_kind in gate_cfg.preserve:
        return GateResult.passed(GATE_NAME)

    # 4. Check trade-flow freshness state
    features_data = dm.symbol_states[symbol].get("features") or {}
    state = features_data.get("trade_flow_state")

    # 5. Handle missing state
    if state is None:
        if gate_cfg.missing_state_behavior == "fail_closed":
            logger.warning(
                f"[{symbol}] trade_flow_gate: missing trade_flow_state, blocking (fail-closed)"
            )
            return GateResult(
                outcome=GateOutcome.BLOCK,
                gate_name=GATE_NAME,
                reason_code=NormalizedRejectReasons.TRADE_FLOW_DEGRADED_ENTRY_BLOCK,
                reason="TRADE_FLOW_DEGRADED_ENTRY_BLOCK",
                context="strategy_signal_gateway:trade_flow_gate",
            )
        return GateResult.passed(GATE_NAME)

    # 6. Handle unknown state
    if state == "unknown":
        if gate_cfg.unknown_state_behavior == "fail_closed":
            logger.warning(
                f"[{symbol}] trade_flow_gate: unknown trade_flow_state, blocking (fail-closed)"
            )
            return GateResult(
                outcome=GateOutcome.BLOCK,
                gate_name=GATE_NAME,
                reason_code=NormalizedRejectReasons.TRADE_FLOW_DEGRADED_ENTRY_BLOCK,
                reason="TRADE_FLOW_DEGRADED_ENTRY_BLOCK",
                context="strategy_signal_gateway:trade_flow_gate",
            )
        return GateResult.passed(GATE_NAME)

    # 7. Check block states
    if state in gate_cfg.block_states:
        logger.warning(
            f"[{symbol}] trade_flow_gate: trade_flow_state is '{state}', blocking new entry"
        )
        return GateResult(
            outcome=GateOutcome.BLOCK,
            gate_name=GATE_NAME,
            reason_code=NormalizedRejectReasons.TRADE_FLOW_DEGRADED_ENTRY_BLOCK,
            reason="TRADE_FLOW_DEGRADED_ENTRY_BLOCK",
            context="strategy_signal_gateway:trade_flow_gate",
        )

    return GateResult.passed(GATE_NAME)
