"""Regime-based attenuation shield.

Behavior proven from this module:
- missing or None regime uses no_regime_multiplier;
- stale regime timestamps can override the configured regime multiplier;
- otherwise the regime lookup is an exact string match against
    regime_multipliers, with default_multiplier used as fallback.

Production configs use canonical uppercase regime names, but this class does
not normalize them beyond str(regime). Callers must provide keys that match the
expected runtime representation.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

from apps.reference.shared.decision_primitives.shields.base import (
    BaseShield,
    ShieldResult,
)


class ContextShield(BaseShield):
    """Apply a regime-aware multiplier to an already computed raw exposure.

    The shield reads only regime-related keys from features. Missing timestamps,
    a disabled TTL, or zero timestamps skip the staleness branch; stale data
    takes precedence over the per-regime lookup to avoid granting a
    fresh-regime multiplier to old state.
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
        # Clamp externally supplied multipliers once at construction time.
        self._regime_multipliers = dict(regime_multipliers or {})
        self._default_multiplier = max(0.0, min(1.0, default_multiplier))
        self._no_regime_multiplier = max(0.0, min(1.0, no_regime_multiplier))
        # TTL applies only when ttl_ms is enabled and both timestamps are
        # present and positive.
        self._ttl_ms = ttl_ms
        self._stale_mult_normal = max(0.0, min(1.0, stale_mult_normal))
        self._stale_mult_danger = max(0.0, min(1.0, stale_mult_danger))
        self._danger_regimes: Set[str] = set(
            danger_regimes or ["HIGH_VOLATILITY"])

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

        # A missing regime is treated separately from an unknown regime string.
        if regime is None:
            return ShieldResult(
                multiplier=self._no_regime_multiplier,
                reasons=[f"no_regime→mult={self._no_regime_multiplier}"],
                shield_name=self.name,
            )

        regime_str = str(regime)

        # Staleness is evaluated before the regime map lookup so old detector
        # output cannot inherit an optimistic fresh-regime multiplier.
        regime_ts_ms = features.get("regime_ts_ms", 0)
        bar_close_ts = features.get("bar_close_ts", 0)

        if (
            self._ttl_ms > 0
            and regime_ts_ms
            and bar_close_ts
            and regime_ts_ms > 0
            and bar_close_ts > 0
        ):
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

        # Matching is exact by string representation; no case normalization is
        # applied here.
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
