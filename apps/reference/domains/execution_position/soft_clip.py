"""
PHASE 2: Soft-limit clipping logic for risk gates.
Instead of rejecting orders, reduce their size to fit within limits.
"""

from decimal import Decimal
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
import logging


@dataclass
class SoftLimitConfig:
    """Soft-limit clipping configuration."""
    mode: str = "clip"  # "clip" or "reject"
    clip_min_notional_usdt: Decimal = Decimal("10")
    directional_ratio_max: Decimal = Decimal("3.0")
    side_exposure_usdt: Decimal = Decimal("600")
    margin_exposure_usdt: Decimal = Decimal("1100")


@dataclass
class ClipResult:
    """Result of soft-limit clipping logic."""
    allowed: bool
    reason: str
    clipped_notional: Optional[Decimal] = None
    original_notional: Optional[Decimal] = None
    clip_reasons: List[str] = field(default_factory=list)


class SoftClipEngine:
    """
    Soft-limit clipping engine.
    Computes ΔV_dir, ΔV_side, ΔV_margin and clips order size instead of rejecting.
    """

    def __init__(self, config: SoftLimitConfig, logger: Optional[logging.Logger] = None):
        self.config = config
        self.logger = logger or logging.getLogger(__name__)

    def calculate_clipped_size(
        self,
        notional_usd: Decimal,
        symbol: str,
        order_side: str,
        long_margin: Decimal,
        short_margin: Decimal,
        total_margin_exposure: Decimal,
        symbol_leverage: Decimal,
        margin_limit: Decimal,
    ) -> ClipResult:
        """
        Calculate clipped order size.
        V_new = min(V_req, ΔV_margin, ΔV_side, ΔV_directional).

        Args:
            notional_usd: Requested notional
            symbol: Trading symbol
            order_side: BUY or SELL
            long_margin: Current long margin
            short_margin: Current short margin
            total_margin_exposure: Current total margin
            symbol_leverage: Symbol leverage
            margin_limit: Margin limit (max exposure)

        Returns:
            ClipResult with allowed=True/False, clipped_notional, clip_reasons
        """
        clip_reasons: List[str] = []
        deltas: List[Decimal] = [notional_usd]

        # ΔV_margin: how much notional can be added within margin limit?
        allowed_extra_margin = margin_limit - total_margin_exposure
        if allowed_extra_margin > Decimal("0"):
            delta_margin_notional = allowed_extra_margin * symbol_leverage
            deltas.append(delta_margin_notional)
            clip_reasons.append(
                f"MARGIN_AVAILABLE:{float(delta_margin_notional):.2f}")
        else:
            deltas.append(Decimal("0"))
            clip_reasons.append("MARGIN_LIMIT_REACHED")

        # ΔV_side: per-side exposure limit
        side_limit = self.config.side_exposure_usdt
        current_side_margin = long_margin if order_side == "BUY" else short_margin
        if current_side_margin < side_limit:
            allowed_extra_side = side_limit - current_side_margin
            delta_side_notional = allowed_extra_side * symbol_leverage
            deltas.append(delta_side_notional)
            clip_reasons.append(
                f"SIDE_AVAILABLE:{float(delta_side_notional):.2f}")
        else:
            deltas.append(Decimal("0"))
            clip_reasons.append("SIDE_LIMIT_REACHED")

        # ΔV_directional: directional ratio constraint
        # For now, simplified: if adding this order breaks ratio, reduce to 0
        # (Full impl: solve for max notional that keeps ratio <= max)
        new_long_margin = long_margin + \
            (notional_usd / symbol_leverage) if order_side == "BUY" else long_margin
        new_short_margin = short_margin + \
            (notional_usd / symbol_leverage) if order_side == "SELL" else short_margin

        min_margin = min(new_long_margin, new_short_margin)
        if min_margin > Decimal("0"):
            ratio = max(new_long_margin, new_short_margin) / min_margin
            if ratio <= self.config.directional_ratio_max:
                delta_dir_notional = notional_usd
                clip_reasons.append("DIRECTIONAL_OK")
            else:
                # Ratio violated: calculate max allowed
                delta_dir_notional = Decimal("0")
                clip_reasons.append("DIRECTIONAL_RATIO_EXCEEDED")
        else:
            delta_dir_notional = notional_usd
            clip_reasons.append("DIRECTIONAL_OK")
        deltas.append(delta_dir_notional)

        # Final clipped notional = min of all constraints
        clipped_notional = min(deltas)

        # Check minimum threshold
        if clipped_notional < self.config.clip_min_notional_usdt:
            return ClipResult(
                allowed=False,
                reason="BELOW_CLIP_MIN",
                clip_reasons=clip_reasons,
                original_notional=notional_usd,
            )

        return ClipResult(
            allowed=True,
            reason="CLIPPED" if clipped_notional < notional_usd else "OK",
            clipped_notional=clipped_notional,
            original_notional=notional_usd,
            clip_reasons=clip_reasons,
        )
