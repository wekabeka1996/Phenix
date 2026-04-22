"""Risk-skew gate — GATE 1.5 in the strategy gateway pipeline.

Checks timestamp divergence between risk and features data, plus
degraded context check.  Extracted from strategy_gateway.py lines 641–660
and the until_refresh guard at lines 517–550.
"""
from __future__ import annotations

import logging
from typing import Any

from ..decision_context import create_decision_context
from ..gate_protocol import GateContext, GateOutcome, GateResult

GATE_NAME = "risk_skew"
logger = logging.getLogger("domain_decision_making")


def _rscfg(ctx: GateContext, key: str) -> Any:
    v = getattr(ctx.config.domains.decision_making.risk_skew, key, None)
    if v is None:
        raise ValueError(
            f"domains.decision_making.risk_skew.{key} required (SSOT)")
    return v


def check_pre_risk(ctx: GateContext) -> GateResult:
    """Phase 1: until-refresh latch.

    Runs BEFORE risk_gate in the pipeline to preserve original ordering.
    """
    dm = ctx.dm
    symbol = ctx.symbol
    clock = ctx.clock

    # --- Until-refresh latch (with auto-clear timeout) ---
    guard = dm.symbol_states[symbol].get("risk_skew_guard") or {}
    if guard.get("until_refresh"):
        now_ms = clock.now_ms()
        latched_at = guard.get("until_refresh_latched_at_ms", 0)
        max_hold_ms = int(_rscfg(ctx, "until_refresh_max_hold_sec") * 1000)
        if latched_at and (now_ms - latched_at) > max_hold_ms:
            dm.symbol_states[symbol]["risk_skew_guard"] = {
                "defer_count": 0,
                "window_start_ms": now_ms,
                "until_refresh": False,
            }
            logger.critical(
                "[%s] RISK_SKEW_GUARD: until_refresh AUTO-CLEARED after %dms (max_hold=%dms)",
                symbol, now_ms - latched_at, max_hold_ms,
            )
        else:
            logger.error(
                "[%s] STRATEGY_SIGNAL_GATEWAY: NO_TRADE_UNTIL_REFRESH (risk_skew_guard active)",
                symbol)
            retry_sec = _rscfg(ctx, "until_refresh_retry_sec")
            if not now_ms:
                now_ms = clock.now_ms()
            return GateResult(
                outcome=GateOutcome.DEFER,
                gate_name=GATE_NAME,
                reason_code="NRR-RISK-SKEW-UNTIL-REFRESH",
                reason="NRR-RISK-SKEW-UNTIL-REFRESH",
                context="strategy_signal_gateway:risk_skew_until_refresh",
                why_extra=["NO_TRADE_UNTIL_REFRESH", "risk_skew_guard"],
                context_update={"_defer_retry_sec": retry_sec},
            )

    return GateResult.passed(GATE_NAME)


def check_post_risk(ctx: GateContext) -> GateResult:
    """Phase 2: degraded context + risk-skew divergence.

    Runs AFTER risk_gate in the pipeline to preserve original ordering.
    """
    dm = ctx.dm
    symbol = ctx.symbol
    clock = ctx.clock

    # --- Degraded context gate ---
    latest_risk = ctx.accumulated.get(
        "latest_risk") or dm.symbol_states[symbol].get("risk")
    risk_ts = (latest_risk.get("ts", 0) if latest_risk else 0)
    features_data = dm.symbol_states[symbol].get("features") or {}
    features_ts = features_data.get(
        "ts", 0) if isinstance(features_data, dict) else 0

    if isinstance(features_data, dict):
        feats_pld = features_data.get("features") or {}
        if isinstance(feats_pld, dict):
            dc_ctx = create_decision_context(symbol, clock.now_ms(), feats_pld)
            if dm._degraded_context_gate_should_defer(
                    symbol=symbol, rid=ctx.rid, ctx=dc_ctx,
                    features_evt=features_data, strategy_id=ctx.strategy_id):
                return GateResult(
                    outcome=GateOutcome.DEFER,
                    gate_name=GATE_NAME,
                    reason_code="DEGRADED_CONTEXT",
                    reason="DEGRADED_CONTEXT",
                    context="strategy_signal_gateway:degraded_context",
                )

    # --- Risk-skew divergence check ---
    if risk_ts > 0 and features_ts > 0:
        skew_sec = abs(features_ts - risk_ts) / 1000
        max_skew = _rscfg(ctx, "max_skew_sec")
        if skew_sec > max_skew:
            max_defer = _rscfg(ctx, "max_defer_count")
            now_ms = clock.now_ms()
            window_sec = _rscfg(ctx, "defer_window_sec")
            state = dm.symbol_states[symbol].setdefault(
                "risk_skew_guard",
                {"defer_count": 0, "window_start_ms": now_ms, "until_refresh": False})
            try:
                ws = int(state.get("window_start_ms", now_ms))
            except Exception:
                ws = now_ms
                state["window_start_ms"] = now_ms
            if now_ms - ws > int(window_sec * 1000):
                state["defer_count"] = 0
                state["window_start_ms"] = now_ms
            try:
                state["defer_count"] = int(state.get("defer_count", 0)) + 1
            except Exception:
                state["defer_count"] = 1
            dc = int(state.get("defer_count", 1))
            if dc >= max_defer:
                state["until_refresh"] = True
                state["until_refresh_latched_at_ms"] = now_ms
                logger.error(
                    "[%s] STRATEGY_SIGNAL_GATEWAY: NO_TRADE_UNTIL_REFRESH "
                    "skew=%.1fs > max=%ss (%d/%d)",
                    symbol, skew_sec, max_skew, dc, max_defer)
                return GateResult(
                    outcome=GateOutcome.BLOCK,
                    gate_name=GATE_NAME,
                    reason_code="NRR-RISK-SKEW-UNTIL-REFRESH",
                    context="strategy_signal_gateway:risk_skew",
                    why_extra=["risk_skew", f"skew_sec:{skew_sec:.3f}",
                               f"defer_count:{dc}"],
                )
            else:
                cooldown = _rscfg(ctx, "defer_cooldown_sec")
                logger.warning(
                    "[%s] STRATEGY_SIGNAL_GATEWAY: DEFER NRR-RISK-STALE "
                    "skew=%.1fs > max=%ss (%d/%d)",
                    symbol, skew_sec, max_skew, dc, max_defer)
                return GateResult(
                    outcome=GateOutcome.DEFER,
                    gate_name=GATE_NAME,
                    reason_code="NRR-RISK-STALE",
                    reason="NRR-RISK-STALE",
                    context="strategy_signal_gateway:risk_skew",
                    why_extra=["risk_skew", f"skew_sec:{skew_sec:.3f}",
                               f"defer_count:{dc}"],
                    context_update={"_defer_cooldown_sec": cooldown,
                                    "_defer_attempt": dc,
                                    "_defer_max_attempts": max_defer},
                )

    return GateResult.passed(GATE_NAME)


def check(ctx: GateContext) -> GateResult:
    """Combined check (backward compatible — runs both phases sequentially)."""
    pre = check_pre_risk(ctx)
    if pre.outcome != GateOutcome.PASS:
        return pre
    return check_post_risk(ctx)
