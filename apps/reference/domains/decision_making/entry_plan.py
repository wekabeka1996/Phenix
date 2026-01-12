"""
EntryPlan DTO - Calculates entry, stop-loss, and take-profit prices based on ATR and OBI.

EP-01.2-INT: Pure computation logic, no I/O.
All parameters come from config (no magic constants).
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
    
    All loaded from Pydantic config at runtime (no hardcoded defaults in logic).
    """
    atr_period: int  # For documentation/tracing (e.g., 14)
    entry_k_atr: float  # Entry offset multiplier
    sl_k_atr: float  # Stop-loss ATR multiplier
    tp_k_atr: float  # Take-profit ATR multiplier
    obi_weight: float  # OBI modulation weight (0 = no modulation)
    obi_mod_clamp_min: float  # Clamp floor for OBI multiplier (e.g., 0.8)
    obi_mod_clamp_max: float  # Clamp ceiling for OBI multiplier (e.g., 1.2)
    require_atr: bool  # If True, reject if ATR not ready
    obi_missing_policy: ObiMissingPolicy  # Explicit policy when OBI is None


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
        return value
    try:
        return Decimal(str(value))
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
        Validate inputs for EntryPlan computation (fail-closed).
        
        Returns:
            Tuple of (is_valid, error_reason)
        """
        # Validate side
        side_upper = str(side).upper() if side else ""
        if side_upper not in ("BUY", "SELL", "LONG", "SHORT"):
            return False, f"ENTRY_PLAN_INVALID_SIDE:{side}"
        
        # Validate ref_price
        ref_dec = _to_decimal(ref_price)
        if ref_dec is None or ref_dec <= 0:
            return False, f"ENTRY_PLAN_INVALID_REF_PRICE:{ref_price}"
        
        # Validate ATR (fail-closed if require_atr=True)
        if params.require_atr:
            if not atr_ready:
                return False, "ENTRY_PLAN_ATR_NOT_READY"
            atr_dec = _to_decimal(atr)
            if atr_dec is None or atr_dec <= 0:
                return False, f"ENTRY_PLAN_INVALID_ATR:{atr}"
        else:
            # Even if not required, if provided it must be valid
            if atr is not None:
                atr_dec = _to_decimal(atr)
                if atr_dec is not None and atr_dec <= 0:
                    return False, f"ENTRY_PLAN_INVALID_ATR:{atr}"
        
        return True, None
    
    def compute(
        self,
        side: str,
        ref_price: Union[str, float, Decimal],
        atr: Union[str, float],
        obi: Union[str, float, None] = None,
    ) -> EntryPlanResult:
        """
        Compute entry, stop-loss, and take-profit prices.
        
        Args:
            side: Trade direction ("BUY"/"LONG" or "SELL"/"SHORT")
            ref_price: Reference price (typically bar close)
            atr: Average True Range value
            obi: Order Book Imbalance [-1, 1] or None
            
        Returns:
            EntryPlanResult with all computed prices
            
        Raises:
            ValueError: If inputs are invalid (should pre-validate)
        """
        # Normalize side
        side_upper = str(side).upper()
        is_long = side_upper in ("BUY", "LONG")
        
        # Convert to Decimal
        ref_dec = _to_decimal(ref_price)
        if ref_dec is None:
            raise ValueError(f"Invalid ref_price: {ref_price}")
        
        atr_dec = _to_decimal(atr)
        if atr_dec is None or atr_dec <= 0:
            raise ValueError(f"Invalid ATR: {atr}")
        
        obi_dec = _to_decimal(obi)
        
        # === OBI Modulation ===
        obi_multiplier = 1.0
        obi_policy_applied = False
        
        if obi_dec is None:
            # Apply neutral policy (EXPLICIT, not silent!)
            if self.params.obi_missing_policy == ObiMissingPolicy.NEUTRAL:
                obi_multiplier = 1.0
                obi_policy_applied = True
        else:
            # Compute OBI factor based on side
            # LONG: bullish OBI (positive) → want closer to market → smaller offset
            # SHORT: bullish OBI (positive) → want more cautious → larger offset
            obi_float = float(obi_dec)
            
            if is_long:
                obi_factor = -obi_float  # Bullish OBI → negative factor → smaller mult
            else:
                obi_factor = obi_float  # Bullish OBI → positive factor → larger mult
            
            raw_mult = 1.0 + self.params.obi_weight * obi_factor
            
            # SAFETY: Clamp to prevent taker drift
            obi_multiplier = _clamp(
                raw_mult,
                self.params.obi_mod_clamp_min,
                self.params.obi_mod_clamp_max,
            )
        
        # === Compute Prices ===
        atr_float = float(atr_dec)
        ref_float = float(ref_dec)
        
        # Entry offset with OBI modulation
        entry_offset = Decimal(str(self.params.entry_k_atr * atr_float * obi_multiplier))
        
        # Stop-loss and take-profit offsets (no OBI modulation - pure ATR)
        sl_offset = Decimal(str(self.params.sl_k_atr * atr_float))
        tp_offset = Decimal(str(self.params.tp_k_atr * atr_float))
        
        if is_long:
            # LONG: entry below ref, SL below entry, TP above entry
            entry_price = ref_dec - entry_offset
            stop_loss_price = ref_dec - sl_offset
            take_profit_price = ref_dec + tp_offset
        else:
            # SHORT: entry above ref, SL above entry, TP below entry
            entry_price = ref_dec + entry_offset
            stop_loss_price = ref_dec + sl_offset
            take_profit_price = ref_dec - tp_offset
        
        # Ensure prices are positive (sanity)
        if entry_price <= 0:
            entry_price = ref_dec  # Fallback to ref
        if stop_loss_price <= 0:
            stop_loss_price = Decimal("0.00000001")
        if take_profit_price <= 0:
            take_profit_price = ref_dec  # Fallback to ref
        
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
        )
