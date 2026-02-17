"""
Shield Base — ABC and ShieldResult for Phase 9 Shield Cascade.

Architecture:
- Each shield is a callable implementing the ShieldFn protocol
- ShieldResult captures multiplier + reasons for explainability
- ShieldCascade chains multiple shields: final_mult = Π(shield_i.mult)

Shield types (Phase 3):
1. ContextShield  — regime-aware attenuation (risk-off regimes → lower mult)
2. MemoryShield   — drawdown memory (consecutive losses → lower mult)
3. DangerZoneShield — volatility circuit breaker (extreme vol → block)
"""
from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ShieldResult:
    """Result of a single shield evaluation.

    Attributes:
        multiplier: Attenuation factor ∈ [0.0, 1.0].
                    1.0 = full pass, 0.0 = full veto.
        reasons: Human-readable explanation strings for XAI.
        shield_name: Name of the shield that produced this result.
    """
    multiplier: float = 1.0
    reasons: List[str] = field(default_factory=list)
    shield_name: str = ""
    details: Dict[str, Any] = field(default_factory=dict)


class BaseShield(abc.ABC):
    """Abstract base class for all shields.

    Each shield is a callable that takes:
        (symbol, features, pillar_sum, raw_exposure)
    and returns:
        (multiplier: float, reasons: List[str])

    Shields MUST be stateless or manage their own state.
    They MUST NOT raise exceptions — degrade to pass-through on error.
    """

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Shield identifier for logging/XAI."""
        ...

    @abc.abstractmethod
    def evaluate(
        self,
        symbol: str,
        features: Dict[str, Any],
        pillar_sum: float,
        raw_exposure: float,
    ) -> ShieldResult:
        """Evaluate this shield and return result."""
        ...

    def __call__(
        self,
        symbol: str,
        features: Dict[str, Any],
        pillar_sum: float,
        raw_exposure: float,
    ) -> tuple[float, List[str]]:
        """ShieldFn protocol adapter: returns (multiplier, reasons)."""
        try:
            result = self.evaluate(symbol, features, pillar_sum, raw_exposure)
            mult = max(0.0, min(1.0, result.multiplier))
            return mult, result.reasons
        except Exception as e:
            # Fail-open: shield error → pass through (don't block trading)
            return 1.0, [f"SHIELD_ERROR:{self.name}:{e}"]

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}()"


class ShieldCascade(BaseShield):
    """
    Chains multiple shields. Final multiplier = product of all shields.

    If any shield returns 0.0, the entire cascade vetoes.
    Reasons from all shields are aggregated.

    Usage:
        cascade = ShieldCascade([ContextShield(cfg), MemoryShield(cfg)])
        mult, reasons = cascade(symbol, features, pillar_sum, raw_exposure)
    """

    def __init__(self, shields: List[BaseShield]):
        self._shields = list(shields)

    @property
    def name(self) -> str:
        return "ShieldCascade"

    def evaluate(
        self,
        symbol: str,
        features: Dict[str, Any],
        pillar_sum: float,
        raw_exposure: float,
    ) -> ShieldResult:
        final_mult = 1.0
        all_reasons: List[str] = []
        all_details: Dict[str, Any] = {}

        for shield in self._shields:
            try:
                result = shield.evaluate(symbol, features, pillar_sum, raw_exposure)
                mult = max(0.0, min(1.0, result.multiplier))
                final_mult *= mult
                if result.reasons:
                    all_reasons.extend(result.reasons)
                if result.details:
                    all_details.update(result.details)
                if final_mult <= 0.0:
                    all_reasons.append(f"VETOED_BY:{shield.name}")
                    break  # Early exit: further shields don't matter
            except Exception as e:
                all_reasons.append(f"SHIELD_ERROR:{shield.name}:{e}")
                # Fail-open: continue with mult unchanged

        return ShieldResult(
            multiplier=final_mult,
            reasons=all_reasons,
            shield_name=self.name,
            details=all_details,
        )

    def __repr__(self) -> str:
        names = [s.name for s in self._shields]
        return f"ShieldCascade({names})"
