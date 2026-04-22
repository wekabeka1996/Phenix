"""Risk gate — GATE 1 in the strategy gateway pipeline.

Checks latest risk assessment: data presence, risk_score, trading_allowed,
and max_risk_score threshold.  Extracted from strategy_gateway.py lines 570–639.
"""
from __future__ import annotations

import logging
from typing import Any

from ..gate_protocol import GateContext, GateOutcome, GateResult

GATE_NAME = "risk"
logger = logging.getLogger("domain_decision_making")


def check(ctx: GateContext) -> GateResult:
    dm = ctx.dm
    symbol = ctx.symbol

    latest_risk = dm.symbol_states[symbol].get("risk")
    if not latest_risk:
        return GateResult(
            outcome=GateOutcome.DEFER,
            gate_name=GATE_NAME,
            reason_code="NRR-DATA-NOT-READY",
            reason="NRR-DATA-NOT-READY",
            context="strategy_signal_gateway:risk_not_ready",
            why_extra=["missing:risk", "fail_closed"],
        )

    risk_params = latest_risk.get("risk_parameters") or {}
    is_allowed = risk_params.get("is_trading_allowed", True)
    risk_score_raw = risk_params.get("risk_score")

    if risk_score_raw is None:
        logger.warning(
            "[%s] RISK_SCORE_MISSING: risk_score is None, deferring signal rid=%s",
            symbol, ctx.rid)
        return GateResult(
            outcome=GateOutcome.DEFER,
            gate_name=GATE_NAME,
            reason_code="RISK_SCORE_MISSING",
            reason="RISK_SCORE_MISSING",
            context="strategy_signal_gateway:risk_score_missing",
            why_extra=["missing:risk_score", "fail_closed"],
        )

    try:
        risk_score = float(risk_score_raw)
    except Exception:
        return GateResult(
            outcome=GateOutcome.DEFER,
            gate_name=GATE_NAME,
            reason_code="RISK_SCORE_INVALID",
            reason="RISK_SCORE_INVALID",
            context="strategy_signal_gateway:risk_score_invalid",
            why_extra=["invalid:risk_score", "fail_closed"],
        )

    if not is_allowed:
        return GateResult(
            outcome=GateOutcome.REJECT,
            gate_name=GATE_NAME,
            reason_code="RISK_TRADING_NOT_ALLOWED",
            reason="RISK",
            context="strategy_signal_gateway:risk_gate",
            details={"is_trading_allowed": False},
        )

    # Max risk score threshold (SSOT).
    used_override = False
    try:
        max_risk = float(
            ctx.config.domains.risk_management.trading_allowed_thresholds.max_risk_score)
        icfg = dm._get_aurora_instrument_cfg(symbol)
        mrs = icfg.max_risk_score if icfg is not None else None
        if mrs is not None and mrs.enabled:
            max_risk = float(mrs.value)
            used_override = True
    except Exception as e:
        logger.error("Config Contract Violation: %s", e)
        return GateResult(
            outcome=GateOutcome.REJECT,
            gate_name=GATE_NAME,
            reason_code="CONFIG_CONTRACT_ERROR",
            reason="DECISION",
            context=f"strategy_signal_gateway:risk_config_error:{e}",
        )

    if risk_score > max_risk:
        logger.warning(
            "[%s] STRATEGY_SIGNAL_GATEWAY: REJECT - risk_score %.3f > max %s used_override=%s",
            symbol, risk_score, max_risk, used_override)
        return GateResult(
            outcome=GateOutcome.REJECT,
            gate_name=GATE_NAME,
            reason_code="RISK_SCORE_TOO_HIGH",
            reason="RISK",
            context=f"strategy_signal_gateway:risk_score_{risk_score:.3f}_gt_{max_risk}",
        )

    # Carry forward for downstream consumers.
    ctx.accumulated["latest_risk"] = latest_risk
    ctx.accumulated["risk_score"] = risk_score
    return GateResult.passed(GATE_NAME)
