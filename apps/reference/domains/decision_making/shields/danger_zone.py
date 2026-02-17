"""
DangerZoneShield — Volatility Circuit Breaker.

Blocks or heavily attenuates signals during extreme market conditions:
- Extreme volatility spikes (vol > threshold)
- Spread blowouts (spread_bps > threshold)
- Price motion anomalies (|price_motion| > threshold)

This is a hard safety shield — returns 0.0 (full veto) for danger zone.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List

from apps.reference.domains.decision_making.shields.base import (
    BaseShield,
    ShieldResult,
)


class DangerZoneShield(BaseShield):
    """
    Volatility circuit breaker — vetoes signals in extreme conditions.

    Checks (in order, first trigger wins):
    1. volatility_state > vol_threshold → VETO
    2. spread_bps > spread_threshold → VETO
    3. |price_motion_norm| > motion_threshold → VETO

    If none triggered → full pass-through (1.0).

    Config:
        vol_threshold: 0.95     (volatility_state feature, 0-1 normalized)
        spread_threshold: 50.0  (spread in basis points)
        motion_threshold: 3.0   (|pm_norm| sigma-normalized)
    """

    def __init__(
        self,
        *,
        vol_threshold: float = 0.95,
        spread_threshold: float = 50.0,
        motion_threshold: float = 3.0,
    ):
        self._vol_threshold = vol_threshold
        self._spread_threshold = spread_threshold
        self._motion_threshold = motion_threshold

    @property
    def name(self) -> str:
        return "DangerZoneShield"

    def evaluate(
        self,
        symbol: str,
        features: Dict[str, Any],
        pillar_sum: float,
        raw_exposure: float,
    ) -> ShieldResult:
        reasons: List[str] = []

        # Check 1: Volatility
        vol = features.get("volatility_state")
        if vol is not None:
            try:
                vol_f = float(vol)
                if math.isfinite(vol_f) and vol_f > self._vol_threshold:
                    reasons.append(
                        f"DANGER_ZONE:vol={vol_f:.3f}>{self._vol_threshold}"
                    )
                    return ShieldResult(
                        multiplier=0.0,
                        reasons=reasons,
                        shield_name=self.name,
                    )
            except (TypeError, ValueError):
                pass

        # Check 2: Spread
        spread = features.get("spread_bps")
        if spread is not None:
            try:
                spread_f = float(spread)
                if math.isfinite(spread_f) and spread_f > self._spread_threshold:
                    reasons.append(
                        f"DANGER_ZONE:spread={spread_f:.1f}bps>{self._spread_threshold}"
                    )
                    return ShieldResult(
                        multiplier=0.0,
                        reasons=reasons,
                        shield_name=self.name,
                    )
            except (TypeError, ValueError):
                pass

        # Check 3: Price motion
        motion = features.get("price_motion_norm")
        if motion is not None:
            try:
                motion_f = float(motion)
                if math.isfinite(motion_f) and abs(motion_f) > self._motion_threshold:
                    reasons.append(
                        f"DANGER_ZONE:motion={motion_f:.2f}σ>{self._motion_threshold}"
                    )
                    return ShieldResult(
                        multiplier=0.0,
                        reasons=reasons,
                        shield_name=self.name,
                    )
            except (TypeError, ValueError):
                pass

        # All clear
        return ShieldResult(
            multiplier=1.0,
            reasons=[],
            shield_name=self.name,
        )
