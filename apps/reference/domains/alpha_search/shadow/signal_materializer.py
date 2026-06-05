"""
Shadow Signal Materializer
===========================

Converts raw alpha scores into shadow decisions with explicit reason codes.

AUTHORITY BOUNDARY:
  Output events carry shadow_only=True, authority_applied=False, no_effect=True.
  This module NEVER emits real ORDER_INTENT, CMD:OPEN, CMD:CLOSE.
  It NEVER writes to real WAL, real position FSM, or real risk paths.

Reason codes (why side is NEUTRAL or signal emitted):
  SCORE_BELOW_THRESHOLD   - |score| < threshold
  CONFIDENCE_ZERO_BUG     - score nonzero but confidence=0 (fail-closed upstream bug)
  MISSING_FEATURES        - required features absent → fail_closed upstream
  REGIME_NOT_ALLOWED      - regime blocked by scenario config
  SCENARIO_DISABLED       - scenario.enabled=False
  METRICS_ONLY_MODE       - scenario emits scores but not virtual decisions
  PROVIDER_DUPLICATE      - scenario is a known duplicate of another
  SIDE_MATERIALIZATION_FAILED - score-to-side conversion error
  SHADOW_SIGNAL_EMITTED   - BUY or SELL shadow decision produced
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Reason codes
# ---------------------------------------------------------------------------

class ShadowReasonCode(str, Enum):
    SCORE_BELOW_THRESHOLD = "SCORE_BELOW_THRESHOLD"
    CONFIDENCE_ZERO_BUG = "CONFIDENCE_ZERO_BUG"
    MISSING_FEATURES = "MISSING_FEATURES"
    REGIME_NOT_ALLOWED = "REGIME_NOT_ALLOWED"
    SCENARIO_DISABLED = "SCENARIO_DISABLED"
    METRICS_ONLY_MODE = "METRICS_ONLY_MODE"
    PROVIDER_DUPLICATE = "PROVIDER_DUPLICATE"
    SIDE_MATERIALIZATION_FAILED = "SIDE_MATERIALIZATION_FAILED"
    SHADOW_SIGNAL_EMITTED = "SHADOW_SIGNAL_EMITTED"


# ---------------------------------------------------------------------------
# Output event
# ---------------------------------------------------------------------------

@dataclass
class ShadowSignalEvent:
    """
    Shadow-only signal event.

    All fields required. shadow_only/authority_applied/no_effect are
    immutable constants enforced at construction.
    """

    # Mandatory identity
    scenario_id: str
    scenario_version: str
    provider_id: str
    symbol: str
    ts_ms: int

    # Score data
    raw_score: float
    confidence: float
    threshold: float
    regime: str

    # Decision
    side: str                          # BUY | SELL | NEUTRAL
    reason_codes: List[ShadowReasonCode]

    # Why chain from upstream model
    upstream_why: List[str] = field(default_factory=list)
    features_used: List[str] = field(default_factory=list)

    # Authority boundary — IMMUTABLE
    shadow_only: bool = field(default=True, init=False)
    authority_applied: bool = field(default=False, init=False)
    no_effect: bool = field(default=True, init=False)

    emit_ts: float = field(default_factory=time.time, init=False)

    def __post_init__(self) -> None:
        # Enforce immutable boundary
        object.__setattr__(self, "shadow_only", True)
        object.__setattr__(self, "authority_applied", False)
        object.__setattr__(self, "no_effect", True)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "scenario_version": self.scenario_version,
            "provider_id": self.provider_id,
            "symbol": self.symbol,
            "ts_ms": self.ts_ms,
            "raw_score": self.raw_score,
            "confidence": self.confidence,
            "threshold": self.threshold,
            "regime": self.regime,
            "side": self.side,
            "reason_codes": [r.value for r in self.reason_codes],
            "upstream_why": self.upstream_why,
            "features_used": self.features_used,
            "shadow_only": True,
            "authority_applied": False,
            "no_effect": True,
            "emit_ts": self.emit_ts,
        }


# ---------------------------------------------------------------------------
# Materializer
# ---------------------------------------------------------------------------

def materialize_shadow_signal(
    *,
    scenario_id: str,
    scenario_version: str,
    provider_id: str,
    symbol: str,
    ts_ms: int,
    raw_score: float,
    confidence: float,
    threshold: float,
    regime: str,
    upstream_why: Optional[List[str]] = None,
    features_used: Optional[List[str]] = None,
    allowed_regimes: Optional[List[str]] = None,
    scenario_enabled: bool = True,
) -> ShadowSignalEvent:
    """
    Convert a raw alpha score row into a ShadowSignalEvent with explicit reason codes.

    This is the authoritative score→side→reason conversion for shadow scenarios.
    It replaces silent NEUTRAL with explicit diagnostics.

    Args:
        allowed_regimes: If provided, current regime must be in this list to emit signal.
        scenario_enabled: If False, returns SCENARIO_DISABLED.

    Returns:
        ShadowSignalEvent with shadow_only=True, authority_applied=False, no_effect=True.
    """
    why_list = upstream_why or []
    feats = features_used or []
    reasons: List[ShadowReasonCode] = []

    # --- Check 1: scenario disabled ---
    if not scenario_enabled:
        return ShadowSignalEvent(
            scenario_id=scenario_id,
            scenario_version=scenario_version,
            provider_id=provider_id,
            symbol=symbol,
            ts_ms=ts_ms,
            raw_score=raw_score,
            confidence=confidence,
            threshold=threshold,
            regime=regime,
            side="NEUTRAL",
            reason_codes=[ShadowReasonCode.SCENARIO_DISABLED],
            upstream_why=why_list,
            features_used=feats,
        )

    # --- Check 2: missing features (fail-closed upstream) ---
    is_fail_closed = any(
        "fail_closed" in w or "ta_features_missing" in w or "missing_feature" in w
        for w in why_list
    )
    if is_fail_closed:
        reasons.append(ShadowReasonCode.MISSING_FEATURES)
        return ShadowSignalEvent(
            scenario_id=scenario_id,
            scenario_version=scenario_version,
            provider_id=provider_id,
            symbol=symbol,
            ts_ms=ts_ms,
            raw_score=raw_score,
            confidence=confidence,
            threshold=threshold,
            regime=regime,
            side="NEUTRAL",
            reason_codes=reasons,
            upstream_why=why_list,
            features_used=feats,
        )

    # --- Check 3: regime not allowed ---
    is_regime_blocked = any(
        "regime_not_allowed" in w or "Regime" in w and "not in allowed" in w
        for w in why_list
    )
    if allowed_regimes and regime not in allowed_regimes:
        reasons.append(ShadowReasonCode.REGIME_NOT_ALLOWED)
        return ShadowSignalEvent(
            scenario_id=scenario_id,
            scenario_version=scenario_version,
            provider_id=provider_id,
            symbol=symbol,
            ts_ms=ts_ms,
            raw_score=raw_score,
            confidence=confidence,
            threshold=threshold,
            regime=regime,
            side="NEUTRAL",
            reason_codes=reasons,
            upstream_why=why_list,
            features_used=feats,
        )
    if is_regime_blocked:
        reasons.append(ShadowReasonCode.REGIME_NOT_ALLOWED)
        return ShadowSignalEvent(
            scenario_id=scenario_id,
            scenario_version=scenario_version,
            provider_id=provider_id,
            symbol=symbol,
            ts_ms=ts_ms,
            raw_score=raw_score,
            confidence=confidence,
            threshold=threshold,
            regime=regime,
            side="NEUTRAL",
            reason_codes=reasons,
            upstream_why=why_list,
            features_used=feats,
        )

    # --- Check 4: confidence zero with nonzero score (CONFIDENCE_ZERO_BUG) ---
    score_is_nonzero = abs(raw_score) > 1e-8
    if score_is_nonzero and confidence == 0.0:
        # Diagnose: aurora dir=0 str=0 → known bug
        is_aurora_zero = any(
            "aurora_dir=0.0000" in w or "aurora_str=0.0000" in w
            for w in why_list
        )
        if is_aurora_zero:
            reasons.append(ShadowReasonCode.CONFIDENCE_ZERO_BUG)

    # --- Check 5: score-to-side + threshold ---
    if threshold <= 0.0:
        reasons.append(ShadowReasonCode.SIDE_MATERIALIZATION_FAILED)
        return ShadowSignalEvent(
            scenario_id=scenario_id,
            scenario_version=scenario_version,
            provider_id=provider_id,
            symbol=symbol,
            ts_ms=ts_ms,
            raw_score=raw_score,
            confidence=confidence,
            threshold=threshold,
            regime=regime,
            side="NEUTRAL",
            reason_codes=reasons,
            upstream_why=why_list,
            features_used=feats,
        )

    if raw_score > threshold:
        side = "BUY"
        reasons.append(ShadowReasonCode.SHADOW_SIGNAL_EMITTED)
    elif raw_score < -threshold:
        side = "SELL"
        reasons.append(ShadowReasonCode.SHADOW_SIGNAL_EMITTED)
    else:
        side = "NEUTRAL"
        reasons.append(ShadowReasonCode.SCORE_BELOW_THRESHOLD)

    return ShadowSignalEvent(
        scenario_id=scenario_id,
        scenario_version=scenario_version,
        provider_id=provider_id,
        symbol=symbol,
        ts_ms=ts_ms,
        raw_score=raw_score,
        confidence=confidence,
        threshold=threshold,
        regime=regime,
        side=side,
        reason_codes=reasons,
        upstream_why=why_list,
        features_used=feats,
    )


def derive_shadow_confidence(
    raw_score: float,
    threshold: float,
    regime: str,
    upstream_confidence: float,
    upstream_why: List[str],
) -> float:
    """
    Compute shadow confidence when upstream confidence is zero but score is valid.

    Rules:
    - If upstream fail_closed → 0.0
    - If upstream confidence > 0 → use it
    - If score nonzero and above threshold → derive from score magnitude
    - Otherwise → 0.0
    """
    if upstream_confidence > 0.0:
        return upstream_confidence

    # Check for genuine fail-closed
    if any("fail_closed" in w for w in upstream_why):
        return 0.0

    if abs(raw_score) < 1e-8:
        return 0.0

    # Derive from score / threshold ratio (capped)
    score_ratio = min(abs(raw_score) / max(threshold, 0.01), 2.0)

    # Regime confidence penalty
    regime_penalty = {
        "UNCERTAIN": 0.4,
        "HIGH_VOLATILITY": 0.7,
        "TREND_UP": 1.0,
        "TREND_DOWN": 1.0,
        "LOW_VOLATILITY": 0.85,
        "MEAN_REVERSION": 0.9,
    }.get(regime, 0.75)

    return round(min(1.0, 0.3 * score_ratio * regime_penalty), 4)
