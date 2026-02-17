"""
ContextShield — Regime-Aware Signal Attenuation.

Attenuates exposure based on current market regime:
- Risk-off regimes (HIGH_VOLATILITY) → lower multiplier
- Neutral regimes (MEAN_REVERSION, LOW_VOLATILITY) → moderate multiplier
- Trending regimes (TREND_UP, TREND_DOWN) → full pass-through

REGIME-FIX-01: regime_multipliers keys MUST match RegimeDetector output
(UPPERCASE: TREND_UP, TREND_DOWN, HIGH_VOLATILITY, LOW_VOLATILITY,
MEAN_REVERSION, UNCERTAIN).

TTL-STALE-01: If regime data is older than ttl_ms (measured in ms,
using bar_close_ts as SSOT), apply stale penalty. Stale penalty depends
on whether the last known regime was dangerous or not.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

from apps.reference.domains.decision_making.shields.base import (
    BaseShield,
    ShieldResult,
)


class ContextShield(BaseShield):
    """
    Regime-aware attenuation shield.

    If the current regime is dangerous, reduce exposure.
    If regime is unknown and no default is set, fail-open (1.0).

    TTL-STALE-01:
    If regime_ts_ms is stale (bar_close_ts - regime_ts_ms > ttl_ms),
    apply a degraded multiplier. The degradation is more aggressive
    for danger regimes (e.g., HIGH_VOLATILITY).

    Config:
        regime_multipliers: {"TREND_UP": 1.0, "HIGH_VOLATILITY": 0.3, ...}
        default_multiplier: 1.0  (used for unknown regimes)
        no_regime_multiplier: 0.5  (used when regime is None/missing)
        ttl_ms: 14_400_000  (4h staleness threshold)
        stale_mult_normal: 0.7
        stale_mult_danger: 0.35
        danger_regimes: ["HIGH_VOLATILITY"]
    """

    def __init__(
        self,
        *,
        regime_multipliers: Optional[Dict[str, float]] = None,
        default_multiplier: float = 1.0,
        no_regime_multiplier: float = 0.5,
        ttl_ms: int = 14_400_000,
        stale_mult_normal: float = 0.7,
        stale_mult_danger: float = 0.35,
        danger_regimes: Optional[List[str]] = None,
    ):
        self._regime_multipliers = dict(regime_multipliers or {})
        self._default_multiplier = max(0.0, min(1.0, default_multiplier))
        self._no_regime_multiplier = max(0.0, min(1.0, no_regime_multiplier))
        # TTL-STALE-01
        self._ttl_ms = ttl_ms
        self._stale_mult_normal = max(0.0, min(1.0, stale_mult_normal))
        self._stale_mult_danger = max(0.0, min(1.0, stale_mult_danger))
        self._danger_regimes: Set[str] = set(danger_regimes or ["HIGH_VOLATILITY"])

    @property
    def name(self) -> str:
        return "ContextShield"

    def evaluate(
        self,
        symbol: str,
        features: Dict[str, Any],
        pillar_sum: float,
        raw_exposure: float,
    ) -> ShieldResult:
        regime = features.get("regime")

        # No regime at all → apply no_regime_multiplier
        if regime is None:
            return ShieldResult(
                multiplier=self._no_regime_multiplier,
                reasons=[f"no_regime→mult={self._no_regime_multiplier}"],
                shield_name=self.name,
            )

        regime_str = str(regime)

        # TTL-STALE-01: Check regime staleness BEFORE looking up multiplier.
        # Both bar_close_ts and regime_ts_ms are in milliseconds (SSOT).
        regime_ts_ms = features.get("regime_ts_ms", 0)
        bar_close_ts = features.get("bar_close_ts", 0)

        if regime_ts_ms and bar_close_ts and regime_ts_ms > 0 and bar_close_ts > 0:
            age_ms = bar_close_ts - regime_ts_ms
            if age_ms > self._ttl_ms:
                is_danger = regime_str in self._danger_regimes
                stale_mult = (
                    self._stale_mult_danger if is_danger else self._stale_mult_normal
                )
                age_hours = age_ms / 3_600_000
                ttl_hours = self._ttl_ms / 3_600_000
                return ShieldResult(
                    multiplier=stale_mult,
                    reasons=[
                        f"STALE:age={age_hours:.1f}h>{ttl_hours:.0f}h,"
                        f"regime={regime_str},danger={is_danger}"
                    ],
                    shield_name=self.name,
                )

        # Fresh regime → use configured multiplier
        if regime_str in self._regime_multipliers:
            mult = self._regime_multipliers[regime_str]
            mult = max(0.0, min(1.0, mult))
            reasons = [f"regime={regime_str}→mult={mult}"]
        else:
            mult = self._default_multiplier
            reasons = [f"regime={regime_str}→default_mult={mult}"]

        return ShieldResult(
            multiplier=mult,
            reasons=reasons,
            shield_name=self.name,
        )
