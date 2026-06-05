"""Entry-plan calculation helpers for decision-making.

This module owns two related contracts:
1. Pure ATR/OBI-based computation of entry, stop-loss, and take-profit prices.
2. Strategy-gateway fallback logic that fills missing SL/TP from the validated
    decision-making domain config.

The module performs no I/O and accepts all runtime policy inputs explicitly.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Optional, Union


class ObiMissingPolicy(str, Enum):
    """Policy for when OBI is missing."""
    NEUTRAL = "neutral"


@dataclass(frozen=True)
class EntryPlanParams:
    """
    Configuration parameters for EntryPlan computation.

    Runtime callers are expected to hydrate these values from the validated
    decision-making domain config before invoking EntryPlan.
    """
    atr_period: int  # For documentation/tracing (e.g., 14)
    entry_k_atr: float  # Entry offset multiplier
    sl_k_atr: float  # Stop-loss ATR multiplier
    tp_k_atr: float  # Take-profit ATR multiplier
    obi_weight: float  # OBI modulation weight (0 = no modulation)
    obi_mod_clamp_min: float  # Clamp floor for OBI multiplier (e.g., 0.8)
    obi_mod_clamp_max: float  # Clamp ceiling for OBI multiplier (e.g., 1.2)
    require_atr: bool  # If True, reject if ATR not ready
    obi_missing_policy: ObiMissingPolicy

    # Phase 9: Structural Stop
    structural_stop_enabled: bool = False
    base_atr_mult: float = 1.5
    confidence_scale: float = 0.5
    min_stop_bps: int = 15


@dataclass(frozen=True)
class EntryPlanResult:
    """
    Result of EntryPlan computation.

    All prices are Decimal strings for schema compliance.
    """
    entry_price: str
    stop_loss_price: str
    take_profit_price: str
    # Tracing fields
    side: str
    ref_price: str
    atr: str
    obi: Optional[str]
    obi_multiplier: float  # Actual multiplier applied (after clamp)
    obi_policy_applied: bool  # True if neutral policy was applied
    atr_multiplier: float = 0.0  # Phase 9: Actual ATR multiplier used for SL


def _clamp(value: float, min_val: float, max_val: float) -> float:
    """Clamp value to [min_val, max_val]."""
    if value < min_val:
        return min_val
    if value > max_val:
        return max_val
    return value


def _to_decimal(value: Union[str, float, int, Decimal, None]) -> Optional[Decimal]:
    """Safely convert to Decimal or return None."""
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value if value.is_finite() else None
    try:
        d = Decimal(str(value))
        return d if d.is_finite() else None
    except (InvalidOperation, ValueError):
        return None


class EntryPlan:
    """
    Computes entry, stop-loss, and take-profit prices based on ATR and OBI.

    Formulas (deterministic):
    - Stop Loss (LONG): ref_price - sl_k_atr * atr
    - Stop Loss (SHORT): ref_price + sl_k_atr * atr
    - Take Profit (LONG): ref_price + tp_k_atr * atr
    - Take Profit (SHORT): ref_price - tp_k_atr * atr
    - Entry Offset: entry_k_atr * atr * obi_multiplier
    - Entry (LONG): ref_price - entry_offset (buy lower)
    - Entry (SHORT): ref_price + entry_offset (sell higher)

    OBI Modulation:
    - raw_mult = 1 + obi_weight * obi_factor
    - obi_factor for LONG: -obi (bullish OBI → smaller offset → closer to market)
    - obi_factor for SHORT: +obi (bullish OBI → larger offset → more cautious)
    - Final mult = clamp(raw_mult, obi_mod_clamp_min, obi_mod_clamp_max)
    """

    def __init__(self, params: EntryPlanParams):
        """
        Initialize EntryPlan with config parameters.

        Args:
            params: EntryPlanParams from config (strict, no fallbacks)
        """
        self.params = params

    @staticmethod
    def validate_inputs(
        side: str,
        ref_price: Union[str, float, Decimal, None],
        atr: Union[str, float, None],
        atr_ready: bool,
        params: EntryPlanParams,
    ) -> tuple[bool, Optional[str]]:
        """
        Validate inputs for EntryPlan computation.

        When ATR is optional, ``None`` and ``0`` are allowed soft-start inputs,
        but malformed or negative ATR values are still rejected explicitly.

        Returns:
            Tuple of (is_valid, error_reason)
        """
        side_upper = str(side).upper() if side else ""
        if side_upper not in ("BUY", "SELL", "LONG", "SHORT"):
            return False, f"ENTRY_PLAN_INVALID_SIDE:{side}"

        ref_dec = _to_decimal(ref_price)
        if ref_dec is None or ref_dec <= 0:
            return False, f"ENTRY_PLAN_INVALID_REF_PRICE:{ref_price}"

        if params.require_atr:
            if not atr_ready:
                return False, "ENTRY_PLAN_ATR_NOT_READY"
            atr_dec = _to_decimal(atr)
            if atr_dec is None or atr_dec <= 0:
                return False, f"ENTRY_PLAN_INVALID_ATR:{atr}"
        else:
            # Soft-start mode accepts a missing ATR, but an explicitly provided
            # ATR must still parse cleanly and may not be negative.
            if atr is not None:
                atr_dec = _to_decimal(atr)
                if atr_dec is None or atr_dec < 0:
                    return False, f"ENTRY_PLAN_INVALID_ATR:{atr}"

        return True, None

    def compute(
        self,
        side: str,
        ref_price: Union[str, float, Decimal],
        atr: Union[str, float, None],
        obi: Union[str, float, None] = None,
        pillar_confidence: Optional[float] = None,
        *,
        tick_size: Union[str, float, Decimal, None] = None,
    ) -> EntryPlanResult:
        """
        Compute entry, stop-loss, and take-profit prices.

        Args:
            side: Trade direction ("BUY"/"LONG" or "SELL"/"SHORT")
            ref_price: Reference price (typically bar close)
            atr: Average True Range value. ``None`` is allowed only when
                require_atr is False.
            obi: Order Book Imbalance [-1, 1] or None
            pillar_confidence: Confidence from pillars [0, 1] (optional)
            tick_size: Minimum price increment for safety floor (optional)

        Returns:
            EntryPlanResult with all computed prices

        Raises:
            ValueError: If inputs are invalid (should pre-validate)
        """
        side_upper = str(side).upper()
        is_long = side_upper in ("BUY", "LONG")

        ref_dec = _to_decimal(ref_price)
        if ref_dec is None:
            raise ValueError(f"Invalid ref_price: {ref_price}")

        atr_dec = _to_decimal(atr)
        if atr_dec is None:
            if self.params.require_atr:
                raise ValueError(
                    "ENTRYPLAN_ATR_MISSING: ATR is None but require_atr=True")
            else:
                # Soft-start keeps the contract explicit: missing ATR becomes a
                # zero-distance input and the price safety floors still apply.
                atr_dec = Decimal("0")
        elif atr_dec < 0:
            raise ValueError(f"Invalid ATR (negative): {atr}")

        obi_dec = _to_decimal(obi)

        obi_multiplier = 1.0
        obi_policy_applied = False

        if obi_dec is None:
            if self.params.obi_missing_policy == ObiMissingPolicy.NEUTRAL:
                obi_multiplier = 1.0
                obi_policy_applied = True
        else:
            obi_float = float(obi_dec)

            if is_long:
                obi_factor = -obi_float
            else:
                obi_factor = obi_float

            raw_mult = 1.0 + self.params.obi_weight * obi_factor

            obi_multiplier = _clamp(
                raw_mult,
                self.params.obi_mod_clamp_min,
                self.params.obi_mod_clamp_max,
            )

        atr_float = float(atr_dec)
        ref_float = float(ref_dec)

        # The minimum offset floor prevents degenerate zero-distance SL/TP when
        # ATR is unavailable or extremely small.
        if tick_size is not None:
            tick_dec = _to_decimal(tick_size)
            min_offset = tick_dec if tick_dec and tick_dec > 0 else Decimal(
                "0")
        else:
            min_offset = ref_dec * Decimal("0.0001")

        entry_offset_raw = Decimal(
            str(self.params.entry_k_atr * atr_float * obi_multiplier))
        entry_offset = max(entry_offset_raw, Decimal("0"))

        # Structural-stop mode changes only the stop-loss distance. Entry and TP
        # stay tied to the configured ATR multipliers.
        atr_mult_used = self.params.sl_k_atr

        if self.params.structural_stop_enabled and pillar_confidence is not None:
            conf = min(1.0, max(0.0, float(pillar_confidence)))
            dynamic_mult = self.params.base_atr_mult - \
                (self.params.confidence_scale * conf)
            atr_mult_used = max(dynamic_mult, 0.5)

            sl_offset_raw = Decimal(str(atr_mult_used * atr_float))

            min_dist_bps = ref_dec * \
                Decimal(str(self.params.min_stop_bps)) / Decimal("10000")
            sl_offset_raw = max(sl_offset_raw, min_dist_bps)
        else:
            sl_offset_raw = Decimal(str(self.params.sl_k_atr * atr_float))

        sl_offset = max(sl_offset_raw, min_offset)

        tp_offset_raw = Decimal(str(self.params.tp_k_atr * atr_float))
        tp_offset = max(tp_offset_raw, min_offset)

        if is_long:
            entry_price = ref_dec - entry_offset
            stop_loss_price = ref_dec - sl_offset
            take_profit_price = ref_dec + tp_offset
        else:
            entry_price = ref_dec + entry_offset
            stop_loss_price = ref_dec + sl_offset
            take_profit_price = ref_dec - tp_offset

        if entry_price <= 0:
            entry_price = ref_dec
        if stop_loss_price <= 0:
            stop_loss_price = Decimal("0.00000001")
        if take_profit_price <= 0:
            take_profit_price = ref_dec

        return EntryPlanResult(
            entry_price=str(entry_price),
            stop_loss_price=str(stop_loss_price),
            take_profit_price=str(take_profit_price),
            side=side_upper,
            ref_price=str(ref_dec),
            atr=str(atr_dec),
            obi=str(obi_dec) if obi_dec is not None else None,
            obi_multiplier=obi_multiplier,
            obi_policy_applied=obi_policy_applied,
            atr_multiplier=float(atr_mult_used),
        )


# ---------------------------------------------------------------------------
# Gateway helper: Strategy Primacy + EntryPlan fallback (Phase 14A STEP 10)
# ---------------------------------------------------------------------------

def resolve_strategy_entry_prices(
    *, symbol: str, strategy_id: str, side: str, rid: str,
    price_ctx: dict, pld: dict, entry_price_dec: Decimal,
    why_chain: list, config, logger, reject_fn,
) -> tuple:
    """Compute SL/TP with Strategy Primacy + EntryPlan fallback.

    Returns ``("REJECT", None, None)`` when rejection was emitted via *reject_fn*.
    Otherwise ``(stop_price, target_price, entry_plan_trace)``.
    """
    strategy_stop: Optional[str] = price_ctx.get("stop_price")
    strategy_target: Optional[str] = price_ctx.get("target_price")
    if strategy_stop is not None:
        strategy_stop = str(strategy_stop) if strategy_stop not in (
            "", "None") else None
    if strategy_target is not None:
        strategy_target = str(strategy_target) if strategy_target not in (
            "", "None") else None
    invalid: list[str] = []
    for label, val in [("stop_price", strategy_stop), ("target_price", strategy_target)]:
        if val is None:
            continue
        try:
            d = Decimal(str(val))
            if not d.is_finite() or d < 0:
                raise ValueError
        except Exception:
            invalid.append(label)
    if invalid:
        reject_fn(symbol=symbol, strategy_id=strategy_id, side=side, rid=rid,
                  reason_code="STRATEGY_INVALID_PRICES", reason="STRATEGY_SIGNAL",
                  context="strategy_signal_gateway:invalid_prices",
                  why_chain=(why_chain if isinstance(why_chain, list)
                             else []) + ["invalid_prices"],
                  details={"invalid_fields": invalid,
                           "stop_price": strategy_stop, "target_price": strategy_target})
        return "REJECT", None, None
    if strategy_stop or strategy_target:
        logger.info(
            f"[{symbol}] STRATEGY_PRIMACY: SL={strategy_stop}, TP={strategy_target}")
        if isinstance(why_chain, list):
            why_chain.append(
                f"strategy_prices:sl={strategy_stop},tp={strategy_target}")
    stop_price = strategy_stop
    target_price = strategy_target
    entry_plan_trace = None
    # EntryPlan fallback fills only missing values. The trace object must stay
    # schema-compatible because IntentBuilder embeds it directly into the trade
    # intent payload.
    ep_cfg = getattr(config.domains.decision_making, "entry_plan", None)
    if ep_cfg and ep_cfg.enabled and (stop_price is None or target_price is None):
        vol = pld.get("volatility") or {}
        liq = pld.get("liquidity") or {}
        atr_value = vol.get("atr_14") if isinstance(vol, dict) else None
        atr_ready = vol.get("atr_ready", False) if isinstance(
            vol, dict) else False
        obi_close = liq.get("obi_close") if isinstance(liq, dict) else None
        ep_params = EntryPlanParams(
            atr_period=ep_cfg.atr_period, entry_k_atr=ep_cfg.entry_k_atr,
            sl_k_atr=ep_cfg.sl_k_atr, tp_k_atr=ep_cfg.tp_k_atr,
            obi_weight=ep_cfg.obi_weight,
            obi_mod_clamp_min=ep_cfg.obi_mod_clamp_min,
            obi_mod_clamp_max=ep_cfg.obi_mod_clamp_max,
            require_atr=ep_cfg.require_atr,
            obi_missing_policy=ObiMissingPolicy(ep_cfg.obi_missing_policy))
        is_valid, error = EntryPlan.validate_inputs(
            side=side, ref_price=entry_price_dec,
            atr=atr_value, atr_ready=atr_ready, params=ep_params)
        if not is_valid:
            reject_fn(symbol=symbol, strategy_id=strategy_id, side=side, rid=rid,
                      reason_code=str(error), reason="ENTRY_PLAN_VALIDATION_FAILED",
                      context="strategy_signal_gateway:entry_plan",
                      why_chain=(why_chain if isinstance(
                          why_chain, list) else []) + [str(error)],
                      details={"atr_ready": atr_ready, "atr_value": atr_value})
            return "REJECT", None, None
        try:
            ep_result = EntryPlan(ep_params).compute(
                side=side, ref_price=entry_price_dec, atr=atr_value, obi=obi_close)
            if stop_price is None:
                stop_price = ep_result.stop_loss_price
            if target_price is None:
                target_price = ep_result.take_profit_price
            entry_plan_trace = {
                "ref_price": ep_result.ref_price, "atr": ep_result.atr,
                "obi": ep_result.obi, "obi_multiplier": ep_result.obi_multiplier,
                "obi_policy_applied": ep_result.obi_policy_applied}
            logger.info(
                f"[{symbol}] EntryPlan: SL={stop_price}, TP={target_price}, "
                f"OBI_mult={ep_result.obi_multiplier:.3f}")
            if isinstance(why_chain, list):
                why_chain.append(
                    f"entry_plan:sl={stop_price},tp={target_price}")
        except Exception as ep_err:
            logger.warning(
                f"[{symbol}] EntryPlan computation failed: {ep_err}")
            if strategy_stop is None:
                stop_price = None
            if strategy_target is None:
                target_price = None
            entry_plan_trace = None
    return stop_price, target_price, entry_plan_trace
