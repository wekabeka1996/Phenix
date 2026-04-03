"""Transparent shield implementation for no-op or fallback paths.

NullShield preserves the shield interface when the real cascade is disabled,
empty, or intentionally replaced in tests. It has no side effects and does not
inspect the incoming features.
"""
from __future__ import annotations

from typing import Any, Dict, List

from apps.reference.domains.decision_making.shields.base import (
    BaseShield,
    ShieldResult,
)


class NullShield(BaseShield):
    """Explicit no-op shield used where a shield object is still required."""

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
        """Return a pass-through result with no diagnostic reasons."""
        return ShieldResult(
            multiplier=1.0,
            reasons=[],
            shield_name=self.name,
        )

    def __repr__(self) -> str:
        return "NullShield()"
