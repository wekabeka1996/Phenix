"""Pure MD-AMR regime allowlist compatibility helper."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from apps.reference.domains.regime_allowlist.contract import RegimeAllowlistContract


REGIME_ALIAS_MAP: dict[str, str] = {
    "LOW_FLAT": "FLAT_LOW",
    "HIGH_FLAT": "FLAT_HIGH",
    "HIGHT_FLAT": "FLAT_HIGH",
    "NORMAL_FLAT": "FLAT_NORMAL",
    "HIGH_VOLATILYTY": "HIGH_VOLATILITY",
    "LOW_VOLATILYTY": "LOW_VOLATILITY",
    "HIGHT_VOLATILITY": "HIGH_VOLATILITY",
}

REGIME_COMPATIBILITY_MAP: dict[str, tuple[str, ...]] = {
    "FLAT_LOW": ("FLAT_LOW", "LOW_VOLATILITY"),
    "LOW_VOLATILITY": ("LOW_VOLATILITY", "FLAT_LOW"),
    "FLAT_NORMAL": ("FLAT_NORMAL", "MEAN_REVERSION"),
    "MEAN_REVERSION": ("MEAN_REVERSION", "FLAT_NORMAL"),
    "FLAT_HIGH": ("FLAT_HIGH", "HIGH_VOLATILITY"),
    "HIGH_VOLATILITY": ("HIGH_VOLATILITY", "FLAT_HIGH"),
}


@dataclass(frozen=True)
class RegimeAllowlistEvaluation:
    current_regime: str
    allowed_regimes: list[str]
    effective_allowed_regimes: list[str]
    allowed: bool


class MDAMRRegimeAllowlistEvaluator:
    def normalize(self, regime: Any) -> str:
        label = str(regime or "").strip().upper()
        return REGIME_ALIAS_MAP.get(label, label)

    def expand(self, allowed_regimes: list[str]) -> list[str]:
        expanded: list[str] = []
        seen: set[str] = set()
        for raw_regime in allowed_regimes:
            normalized = self.normalize(raw_regime)
            compatible = REGIME_COMPATIBILITY_MAP.get(normalized, (normalized,))
            for regime in compatible:
                if regime and regime not in seen:
                    seen.add(regime)
                    expanded.append(regime)
        return expanded

    def evaluate(self, *, current_regime: Any, allowed_regimes: list[str]) -> RegimeAllowlistEvaluation:
        normalized = self.normalize(current_regime)
        effective = self.expand(allowed_regimes)
        return RegimeAllowlistEvaluation(
            current_regime=normalized,
            allowed_regimes=list(allowed_regimes),
            effective_allowed_regimes=effective,
            allowed=RegimeAllowlistContract.is_regime_allowed(
                current_regime=normalized,
                allowed_regimes=effective,
            ),
        )


__all__ = [
    "MDAMRRegimeAllowlistEvaluator",
    "REGIME_ALIAS_MAP",
    "REGIME_COMPATIBILITY_MAP",
    "RegimeAllowlistEvaluation",
]
