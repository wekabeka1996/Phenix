"""
NullShield — Phase 9 Shield Stub.

A transparent shield that passes all signals through
without attenuation. Used as the default shield when
no shield cascade is configured (Phase 2).

Phase 3 replaces this with ContextShield, MemoryShield,
and DangerZoneShield in a cascade.

Contract:
- Input:  (symbol, features, pillar_sum, raw_exposure)
- Output: (multiplier: float ∈ [0,1], reasons: List[str])
- NullShield always returns (1.0, [])
"""
from __future__ import annotations

from typing import Any, Dict, List

from apps.reference.domains.decision_making.shields.base import (
    BaseShield,
    ShieldResult,
)


class NullShield(BaseShield):
    """
    Transparent shield — passes everything through.

    Extends BaseShield for cascade compatibility.
    Always returns multiplier=1.0, no reasons.
    """

    @property
    def name(self) -> str:
        return "NullShield"

    def evaluate(
        self,
        symbol: str,
        features: Dict[str, Any],
        pillar_sum: float,
        raw_exposure: float,
    ) -> ShieldResult:
        """Always returns full pass-through."""
        return ShieldResult(
            multiplier=1.0,
            reasons=[],
            shield_name=self.name,
        )

    def __repr__(self) -> str:
        return "NullShield()"
