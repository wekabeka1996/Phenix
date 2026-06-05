"""Exposure / sizing gate — GATE 4 in the strategy gateway pipeline.

Validates entry price, calculates position size, checks exposure precheck.
Extracted from strategy_gateway.py lines 714–801.
"""
from __future__ import annotations

import decimal
import logging
from typing import Any

from apps.reference.utils.accessors import aget

from apps.reference.domains.decision_making.gateway.protocol import GateContext, GateOutcome, GateResult

GATE_NAME = "exposure"
logger = logging.getLogger("domain_decision_making")


def check(ctx: GateContext) -> GateResult:
    dm = ctx.dm
    symbol = ctx.symbol
    pld = ctx.pld

    # --- Entry price validation ---
    price_ctx = pld.get("price_ctx") if isinstance(
        pld.get("price_ctx"), dict) else {}
    entry_price = price_ctx.get("entry_price")

    if entry_price in (None, "", "0", 0):
        return GateResult(
            outcome=GateOutcome.REJECT,
            gate_name=GATE_NAME,
            reason_code="MISSING_ENTRY_PRICE",
            reason="DECISION",
            context="strategy_signal_gateway:entry_price_missing",
        )

    try:
        entry_price_dec = decimal.Decimal(str(entry_price))
    except Exception:
        return GateResult(
            outcome=GateOutcome.REJECT,
            gate_name=GATE_NAME,
            reason_code="INVALID_ENTRY_PRICE",
            reason="DECISION",
            context="strategy_signal_gateway:entry_price_invalid",
        )

    if not dm.latest_portfolio:
        return GateResult(
            outcome=GateOutcome.REJECT,
            gate_name=GATE_NAME,
            reason_code="LATEST_PORTFOLIO_MISSING",
            reason="DECISION",
            context="strategy_signal_gateway:latest_portfolio_missing",
        )

    # --- Sizing ---
    sizing_ctx = {
        "portfolio": dm.latest_portfolio,
        "features": dm.symbol_states[symbol].get("features") if symbol in dm.symbol_states else {},
    }

    regime_name = None
    scoring = pld.get("scoring") if isinstance(
        pld.get("scoring"), dict) else None
    if isinstance(scoring, dict):
        regime_name = scoring.get("regime")

    margin_pct_mult: decimal.Decimal | None = None
    if ctx.strategy_id == "aurora" and regime_name:
        try:
            icfg = dm._get_aurora_instrument_cfg(symbol)
            rs = aget(icfg, "regime_sizing", None) if icfg else None
            if isinstance(rs, dict) and rs:
                mult_raw = rs.get(str(regime_name)) or rs.get("DEFAULT")
                if mult_raw is not None:
                    margin_pct_mult = decimal.Decimal(str(mult_raw))
        except Exception:
            pass

    # Phase 0.6: STRESS attenuation
    try:
        _stress_state = getattr(
            dm, "_system_stress_states", {}).get(symbol, "NORMAL")
        if _stress_state == "STRESS":
            _strat_cfg = getattr(dm.config.strategies, ctx.strategy_id, None)
            _sg_cfg = getattr(_strat_cfg, "safety_gates",
                              None) if _strat_cfg else None
            _policy = str(getattr(_sg_cfg, "system_stress_policy", "off"))
            if _policy == "attenuate":
                _factor = decimal.Decimal(
                    str(getattr(_sg_cfg, "stress_attenuation_factor", "0.5")))
                margin_pct_mult = (
                    margin_pct_mult if margin_pct_mult is not None
                    else decimal.Decimal("1")) * _factor
    except Exception:
        pass  # fail-open: attenuation errors must not block trades

    # PKG-3: Inception fractional sizing
    try:
        sizing_cfg = pld.get("sizing") if isinstance(
            pld.get("sizing"), dict) else None
        if sizing_cfg and "margin_pct_mult" in sizing_cfg:
            _inception_factor = decimal.Decimal(
                str(sizing_cfg["margin_pct_mult"]))
            margin_pct_mult = (
                margin_pct_mult if margin_pct_mult is not None
                else decimal.Decimal("1")) * _inception_factor
    except Exception:
        pass

    try:
        qty_dec, why_sizing, sizing_rej, _ = dm._calculate_position_size(
            symbol, entry_price_dec, ctx.side, sizing_ctx,
            margin_pct_mult=margin_pct_mult)
    except Exception as e:
        return GateResult(
            outcome=GateOutcome.REJECT,
            gate_name=GATE_NAME,
            reason_code="SIZING_ERROR",
            reason="DECISION",
            context=f"strategy_signal_gateway:sizing_exception:{type(e).__name__}",
            why_extra=["sizing_exception"],
            details={"error": str(e)},
        )

    if qty_dec is None:
        return GateResult(
            outcome=GateOutcome.REJECT,
            gate_name=GATE_NAME,
            reason_code="SIZING_QTY_NONE",
            reason="DECISION",
            context="strategy_signal_gateway:sizing_qty_none",
        )

    if not dm._precheck_exposure_cache(symbol, ctx.side, float(qty_dec * entry_price_dec)):
        return GateResult(
            outcome=GateOutcome.REJECT,
            gate_name=GATE_NAME,
            reason_code="EXPOSURE_PRECHECK_FAILED",
            reason="RISK",
            context="strategy_signal_gateway:exposure_precheck",
        )

    # Carry forward resolved sizing for downstream.
    ctx.accumulated["entry_price_dec"] = entry_price_dec
    ctx.accumulated["qty_dec"] = qty_dec
    ctx.accumulated["why_sizing"] = why_sizing
    ctx.accumulated["price_ctx"] = price_ctx

    return GateResult.passed(GATE_NAME)
