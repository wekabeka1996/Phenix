"""Hard-veto shield for explicitly dangerous market conditions.

This implementation is binary: it returns 0.0 on the first proven trigger and
1.0 otherwise. Invalid, non-numeric, NaN, or infinite feature values are
ignored rather than treated as positive evidence of danger.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List

from apps.reference.domains.decision_making.shields.base import (
    BaseShield,
    ShieldResult,
)


class DangerZoneShield(BaseShield):
    """Veto signals when a danger metric crosses its configured threshold.

    The checks run in a fixed order: volatility_state, then spread_bps, then
    price_motion_norm. Only the first matching trigger contributes a reason.
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

        # This shield only vetoes on finite numeric evidence; parse failures are
        # treated like missing data and allow later checks to run.
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

        return ShieldResult(
            multiplier=1.0,
            reasons=[],
            shield_name=self.name,
        )
