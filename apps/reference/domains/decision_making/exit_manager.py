"""
Phase 5: Exit Manager (Position Management).

Manages active positions by evaluating exit criteria:
- DangerZone (Priority 1): Force close or tighten stops
- Trailing Stop (Priority 1.5): Synthetic ATR-based trailing exit
- Time-based Exits (Priority 2): Stagnation / max hold
- Signal Reversal (Priority 3): Alpha flip

S2-TRAILING: Trailing stop logic uses MFE (max favorable excursion)
and ATR-based trail distance. It is a "synthetic exit" (not SL modify),
meaning if price drops below trail level → EXIT immediately.
"""
from typing import Optional, Tuple
from decimal import Decimal
import logging

from apps.reference.config_models import ExitManagerConfig, DangerZoneExitType


class ExitManager:
    """
    Orchestrates exit logic for open positions.
    Decides when to close a position or adjust its risk parameters.
    
    Priority chain:
        1. DangerZone CLOSE_POSITION  (highest)
        2. DangerZone TIGHTEN_STOPS
        3. Trailing Stop              (S2-TRAILING)
        4. Time-based Exit
        5. Signal Reversal            (lowest)
    """
    def __init__(
        self,
        config: ExitManagerConfig,
        *,
        trailing_enabled: bool = False,
        trailing_activation_pct: float = 0.003,
        trailing_atr_mult: Optional[float] = None,
        trailing_pct: Optional[float] = None,
    ):
        self.config = config
        self.logger = logging.getLogger(__name__)
        self._danger_zone_action = self._safe_danger_zone_action(
            getattr(config, "danger_zone_action", DangerZoneExitType.TIGHTEN_STOPS)
        )
        self._danger_zone_tighten_factor = self._safe_float(
            getattr(config, "danger_zone_tighten_factor", 0.5),
            default=0.5,
        )
        self._time_exit_enabled = self._safe_bool(
            getattr(config, "time_exit_enabled", False),
            default=False,
        )
        self._max_hold_time_sec = self._safe_float(
            getattr(config, "max_hold_time_sec", 3600 * 24),
            default=float(3600 * 24),
        )
        self._signal_exit_enabled = self._safe_bool(
            getattr(config, "signal_exit_enabled", True),
            default=True,
        )
        self._signal_reversal_threshold = self._safe_float(
            getattr(config, "signal_reversal_threshold", -0.1),
            default=-0.1,
        )
        # S2-TRAILING config (from AuroraTrailingStopConfig via handler)
        self._trailing_enabled = trailing_enabled
        self._trailing_activation_pct = trailing_activation_pct
        self._trailing_atr_mult = trailing_atr_mult  # ATR × mult (preferred)
        self._trailing_pct = trailing_pct              # % fallback

    @staticmethod
    def _safe_bool(value, *, default: bool) -> bool:
        if isinstance(value, bool):
            return value
        if value is None:
            return default
        try:
            return bool(value)
        except Exception:
            return default

    @staticmethod
    def _safe_float(value, *, default: float) -> float:
        try:
            return float(value)
        except Exception:
            return default

    @staticmethod
    def _safe_danger_zone_action(value) -> DangerZoneExitType:
        if isinstance(value, DangerZoneExitType):
            return value
        try:
            return DangerZoneExitType(str(value))
        except Exception:
            return DangerZoneExitType.TIGHTEN_STOPS

    def check_exit(
        self,
        symbol: str,
        current_position_side: str,  # "LONG"/"SHORT" or "BUY"/"SELL"
        entry_price: Decimal,
        current_price: Decimal,
        hold_time_sec: float,
        final_score: float,
        danger_zone_active: bool,
        current_stop_loss: Optional[Decimal] = None,
        *,
        mfe_price: Optional[Decimal] = None,
        atr: Optional[Decimal] = None,
    ) -> Tuple[bool, Optional[str], Optional[Decimal]]:
        """
        Evaluate exit criteria for a single position.

        Args:
            symbol: Trading pair symbol
            current_position_side: Side of the open position
            entry_price: Average entry price
            current_price: Current market price (mid or last)
            hold_time_sec: Duration position has been open (seconds)
            final_score: Current alpha score (post-shield)
            danger_zone_active: Whether DangerZone shield is active
            current_stop_loss: Current SL price (if any)
            mfe_price: Max favorable excursion price (highest for LONG)
            atr: Current ATR value for trail distance calculation

        Returns:
            (should_exit, reason, new_stop_loss)
            - should_exit (bool): True if position should be closed immediately.
            - reason (str): Human-readable reason for exit/adjustment.
            - new_stop_loss (Decimal): New SL price if adjustment needed, else None.
        """
        side_norm = str(current_position_side).upper()
        is_long = side_norm in ("LONG", "BUY")
        
        # 1. Danger Zone Logic (Priority 1 - highest)
        if danger_zone_active:
            action = self._danger_zone_action
            
            if action == DangerZoneExitType.CLOSE_POSITION:
                return True, "EXIT_DANGER_ZONE:ForceClose", None
                
            elif action == DangerZoneExitType.TIGHTEN_STOPS:
                # S2-R2: Profit guard — only tighten when position is profitable.
                if is_long:
                    unrealized = current_price - entry_price
                else:
                    unrealized = entry_price - current_price
                if unrealized <= 0:
                    return False, "DANGER_ZONE_TIGHTEN:skip_unprofitable", None

                # Tighten logic: Reduce distance from current price to SL by factor
                if current_stop_loss:
                    dist = abs(current_price - current_stop_loss)
                    new_dist = dist * Decimal(str(self._danger_zone_tighten_factor))
                    
                    if is_long:
                        proposed_sl = current_price - new_dist
                        if proposed_sl >= current_price:
                            return False, "DANGER_ZONE_TIGHTEN:skip_cross_price", None
                        if proposed_sl > current_stop_loss:
                            return False, f"DANGER_ZONE_TIGHTEN:{proposed_sl:.2f}", proposed_sl
                    else:
                        proposed_sl = current_price + new_dist
                        if proposed_sl <= current_price:
                            return False, "DANGER_ZONE_TIGHTEN:skip_cross_price", None
                        if proposed_sl < current_stop_loss:
                            return False, f"DANGER_ZONE_TIGHTEN:{proposed_sl:.2f}", proposed_sl

        # 1.5 Trailing Stop (S2-TRAILING: after DangerZone, before Time)
        if self._trailing_enabled and mfe_price is not None and entry_price > 0:
            trailing_result = self._check_trailing(
                symbol=symbol,
                is_long=is_long,
                entry_price=entry_price,
                current_price=current_price,
                mfe_price=mfe_price,
                atr=atr,
            )
            if trailing_result is not None:
                return trailing_result

        # 2. Time-Based Exit (Anti-Stagnation)
        if self._time_exit_enabled:
            if hold_time_sec > self._max_hold_time_sec:
                return True, f"EXIT_TIME_LIMIT:{hold_time_sec:.0f}s", None

        # 3. Signal Reversal (Alpha Flip)
        if self._signal_exit_enabled:
            threshold = self._signal_reversal_threshold
            
            if is_long:
                if final_score < threshold:
                    return True, f"EXIT_SIGNAL_REVERSAL:{final_score:.4f}<{threshold}", None
            else:
                if final_score > -threshold:
                    return True, f"EXIT_SIGNAL_REVERSAL:{final_score:.4f}>{-threshold}", None

        return False, None, None

    def _check_trailing(
        self,
        *,
        symbol: str,
        is_long: bool,
        entry_price: Decimal,
        current_price: Decimal,
        mfe_price: Decimal,
        atr: Optional[Decimal],
    ) -> Optional[Tuple[bool, str, Optional[Decimal]]]:
        """
        Check if trailing stop should trigger exit.
        
        Returns (should_exit, reason, new_sl) or None if no trailing action.
        
        Logic:
            1. Check if PnL% exceeds activation threshold
            2. Calculate trail distance (ATR × mult preferred, pct fallback)
            3. If price has retraced past trail level → EXIT
        
        Invariants:
            - Trail stop never crosses current price
            - Trail stop is always between entry and MFE
        """
        # Activation check: only trail when position has been profitable enough
        if is_long:
            pnl_pct = float((current_price - entry_price) / entry_price)
        else:
            pnl_pct = float((entry_price - current_price) / entry_price)

        if pnl_pct < self._trailing_activation_pct:
            return None  # Not activated yet

        # Calculate trail distance
        trail_dist = self._calc_trail_distance(mfe_price, atr)
        if trail_dist is None or trail_dist <= 0:
            return None

        # Calculate trail stop level
        if is_long:
            trail_stop = mfe_price - trail_dist
            # Invariant: trail stop must be above entry (we're in profit)
            if trail_stop <= entry_price:
                return None
            # Check if price dropped below trail
            if current_price < trail_stop:
                return (
                    True,
                    f"EXIT_TRAILING:price={current_price}<trail={trail_stop:.2f}"
                    f"(mfe={mfe_price},dist={trail_dist:.4f})",
                    None,
                )
        else:
            trail_stop = mfe_price + trail_dist
            # Invariant: trail stop must be below entry (we're in profit)
            if trail_stop >= entry_price:
                return None
            # Check if price rose above trail
            if current_price > trail_stop:
                return (
                    True,
                    f"EXIT_TRAILING:price={current_price}>trail={trail_stop:.2f}"
                    f"(mfe={mfe_price},dist={trail_dist:.4f})",
                    None,
                )

        return None  # Trailing active but not triggered

    def _calc_trail_distance(
        self,
        mfe_price: Decimal,
        atr: Optional[Decimal],
    ) -> Optional[Decimal]:
        """Calculate trail distance. Prefer ATR × mult, fall back to % of MFE."""
        # Prefer ATR-based distance
        if self._trailing_atr_mult is not None and atr is not None and atr > 0:
            return atr * Decimal(str(self._trailing_atr_mult))

        # Fallback: percentage of MFE price
        if self._trailing_pct is not None and mfe_price > 0:
            return mfe_price * Decimal(str(self._trailing_pct))

        return None
