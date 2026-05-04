"""Core contracts for the decision-making shield pipeline.

This module defines the common result container, the abstract shield interface,
and the cascade that combines multiple shields multiplicatively. It does not
choose which shields are active; callers supply concrete shield instances.
"""
from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class ShieldResult:
    """Result of a single shield evaluation.

    Attributes:
        multiplier: Attenuation factor ∈ [0.0, 1.0].
                    1.0 = full pass, 0.0 = full veto.
        reasons: Human-readable explanation strings for XAI.
        shield_name: Name of the shield that produced this result.
        details: Optional structured metadata for downstream diagnostics.
    """
    multiplier: float = 1.0
    reasons: List[str] = field(default_factory=list)
    shield_name: str = ""
    details: Dict[str, Any] = field(default_factory=dict)


class BaseShield(abc.ABC):
    """Abstract base class for all shields.

    The primary contract is evaluate(), which returns ShieldResult. __call__ is
    a compatibility adapter for call sites that only consume
    (multiplier, reasons).

    Concrete shields may keep internal state, but failures at this boundary are
    treated as pass-through so the caller receives an explicit error reason
    instead of an exception.
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
        """Adapt ShieldResult to the tuple form consumed by legacy callers."""
        try:
            result = self.evaluate(symbol, features, pillar_sum, raw_exposure)
            mult = max(0.0, min(1.0, result.multiplier))
            return mult, result.reasons
        except Exception as e:
            # Keep the call surface exception-free and make the failure visible.
            return 1.0, [f"SHIELD_ERROR:{self.name}:{e}"]

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}()"


class ShieldCascade(BaseShield):
    """Combine shields in order and multiply their resulting multipliers.

    Evaluation order matters: the first shield that drives the aggregate to 0.0
    stops the cascade. Reasons are concatenated, and detail keys from later
    shields overwrite earlier keys with the same name.
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
                # The cascade needs the full ShieldResult, so it handles
                # clamping and exception isolation locally instead of routing
                # through BaseShield.__call__.
                result = shield.evaluate(
                    symbol, features, pillar_sum, raw_exposure)
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
