"""
Aurora Alpha Adapter

Wraps AuroraScoringKernel.compute() as an AlphaModel for use in alpha_search ensemble.
Uses the same pure scoring kernel as live Aurora strategy.

ALPHA-A2: Aurora adapter for multi-provider alpha_search.

All scoring parameters are config-driven via alpha_search.yaml (providers.aurora.adapter).
No hardcoded defaults — alpha_search is a self-contained independent domain.
"""

import decimal
import logging
from typing import Dict, Any, Optional, List

from ..alpha_model import AlphaModel, AlphaScore
from apps.reference.domains.decision_making.aurora_scoring_kernel import (
    AuroraScoringKernel,
    ScoringResult,
    SideBiasState,
)

LOG = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Last-resort fallback constants.
# These are used ONLY if AuroraAlphaAdapter is instantiated directly without
# config (e.g. in unit tests). In production the backtest_plugin always passes
# values loaded from alpha_search.yaml.  Do NOT use these as a config source.
# ---------------------------------------------------------------------------
_FALLBACK_ESSENTIAL_FEATURES = ["obi", "delta_price", "macro_resid"]

_FALLBACK_SIGNAL_WEIGHTS = {
    "obi": 0.42,
    "tfi": 0.15,
    "delta_price": 0.15,
    "absorption": 0.0,
    "ema_bias": 0.15,
    "depth_imbalance": -0.15,
    "macro_resid": 0.10,
    "macro_sync": 0.0,
    "volume_spike": 0.10,
    "volatility_state": 0.10,
}

_FALLBACK_FEATURE_NEUTRALS = {
    "obi": 0.0,
    "tfi": 0.0,
    "delta_price": 0.0,
    "absorption": 0.0,
    "ema_bias": 0.5,
    "volume_spike": 0.0,
    "volatility_state": 0.0,
    "depth_imbalance": 0.5,
    "macro_sync": 0.5,
    "macro_resid": 0.0,
}

_FALLBACK_DIRECTION_STRENGTH_CFG = {
    "directional_features": [
        "obi", "tfi", "delta_price", "absorption", "ema_bias",
        "depth_imbalance", "macro_resid", "macro_sync"
    ],
    "strength_features": ["volume_spike", "volatility_state"],
    "strength_alpha": 0.5,
    "strength_cap": 1.0,
}

_FALLBACK_REGIME_THRESHOLDS = {
    "HIGH_VOLATILITY": 1.0,
    "LOW_VOLATILITY": 0.9,
    "MEAN_REVERSION": 0.75,
    "TREND_UP": 1.0,
    "TREND_DOWN": 1.0,
    "UNCERTAIN": 1.15,
    "DEFAULT": 1.0,
}


class AuroraAlphaAdapter(AlphaModel):
    """
    Adapter that runs Aurora scoring logic as an AlphaModel.

    Uses the same pure scoring kernel as live Aurora strategy,
    ensuring consistency between shadow alpha_search and production signals.

    All scoring parameters come from alpha_search.yaml (providers.aurora.adapter).
    backtest_plugin passes the full AuroraAdapterConfig when constructing.

    Note: This is read-only scoring. No side effects, no state mutation.
    """

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        essential_features: Optional[List[str]] = None,
        signal_weights: Optional[Dict[str, float]] = None,
        feature_neutrals: Optional[Dict[str, float]] = None,
        direction_strength_cfg: Optional[Dict[str, Any]] = None,
        regime_thresholds: Optional[Dict[str, float]] = None,
        base_threshold: float = 0.12,
        delta_price_cap_pct: float = 0.02,
        normalize_mode: str = "signed_v2",
        scoring_version: str = "v2",
    ):
        """
        Initialize Aurora adapter.

        Args:
            config: Base model config (optional)
            essential_features: Required features for scoring
            signal_weights: Feature weights for scoring
            feature_neutrals: Neutral values for features
            direction_strength_cfg: Direction/strength scoring config
            regime_thresholds: Regime-based threshold multipliers
            base_threshold: Base signal threshold
            delta_price_cap_pct: Delta price cap for normalization
            normalize_mode: Feature normalization mode (strict). Only "signed_v2" is allowed.
            scoring_version: "v1" or "v2"
        """
        # Set attributes BEFORE super().__init__() calls get_model_name()
        self._scoring_version = scoring_version

        self._essential_features = essential_features or _FALLBACK_ESSENTIAL_FEATURES
        self._signal_weights = signal_weights if signal_weights is not None else _FALLBACK_SIGNAL_WEIGHTS
        self._feature_neutrals = feature_neutrals if feature_neutrals is not None else _FALLBACK_FEATURE_NEUTRALS
        self._direction_strength_cfg = direction_strength_cfg or _FALLBACK_DIRECTION_STRENGTH_CFG
        self._regime_thresholds = regime_thresholds if regime_thresholds is not None else _FALLBACK_REGIME_THRESHOLDS
        self._base_threshold = decimal.Decimal(str(base_threshold))
        self._delta_price_cap_pct = decimal.Decimal(str(delta_price_cap_pct))

        self._normalize_mode = str(normalize_mode)
        if self._normalize_mode != "signed_v2":
            raise ValueError(
                f"NRR-NORMALIZE-MODE-INVALID:{self._normalize_mode} (only 'signed_v2' is allowed)"
            )

        super().__init__(config or {})

    def get_model_name(self) -> str:
        return f"aurora_{self._scoring_version}_adapter"

    def get_required_features(self) -> List[str]:
        """Return essential features required for Aurora scoring."""
        return self._essential_features.copy()

    def calculate_alpha(
        self,
        symbol: str,
        market_data: Dict[str, Any],
        features: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> AlphaScore:
        """
        Calculate alpha using Aurora pure scoring kernel.

        Args:
            symbol: Trading pair (e.g., "BTCUSDT")
            market_data: Market data with 'close' price
            features: Pre-calculated features from FE
            context: Optional context with 'regime', 'warmup_readiness'

        Returns:
            AlphaScore with Aurora-computed signal
        """
        context = context or {}

        # Get price for normalization
        price = self._get_price(market_data, features)
        if price <= 0:
            return self._fail_closed_score(
                symbol,
                reason="missing_price",
                why=["No valid price in market_data or features"]
            )

        # Build warmup readiness (default all ready if not provided)
        warmup_readiness = context.get("warmup_readiness")
        if warmup_readiness is None:
            # Default: mark as ready if feature exists
            warmup_readiness = {
                feat: feat in features
                for feat in self._essential_features
            }

        # Check essential features
        missing_essential = [
            feat for feat in self._essential_features
            if feat not in features or features[feat] is None
        ]
        if missing_essential:
            return self._fail_closed_score(
                symbol,
                reason="missing_essential_features",
                why=[f"Missing essential features: {missing_essential}"]
            )

        # Get regime (default to "DEFAULT" if not provided)
        regime = context.get("regime", "DEFAULT")

        # Run Aurora kernel
        try:
            result: ScoringResult = AuroraScoringKernel.compute(
                symbol=symbol,
                features=features,
                warmup_readiness=warmup_readiness,
                price=decimal.Decimal(str(price)),
                signal_weights=self._signal_weights,
                feature_neutrals=self._feature_neutrals,
                essential_features=self._essential_features,
                base_threshold=self._base_threshold,
                regime_name=regime,
                regime_thresholds=self._regime_thresholds,
                side_bias_state=None,  # No side bias for alpha_search
                direction_strength_cfg=self._direction_strength_cfg,
                delta_price_cap_pct=self._delta_price_cap_pct,
                normalize_mode=self._normalize_mode,
                scoring_version=self._scoring_version,
                neutral_threshold=None,
                current_side="",
            )
        except Exception as e:
            LOG.warning(f"[{symbol}] Aurora kernel error: {e}")
            return self._fail_closed_score(
                symbol,
                reason="kernel_error",
                why=[f"Aurora kernel error: {str(e)}"]
            )

        # Handle deferred result
        if result.deferred:
            return self._fail_closed_score(
                symbol,
                reason=result.defer_reason or "deferred",
                why=[f"Aurora deferred: {result.defer_reason}"]
            )

        # Convert to AlphaScore
        # Aurora score is already in appropriate range, but clamp to [-1, 1] for safety
        score = max(decimal.Decimal("-1"),
                    min(decimal.Decimal("1"), result.score))

        # Calculate confidence from psi_vector
        confidence = self._calculate_confidence(result)

        # Build why chain
        why = self._build_why(result, regime)

        return AlphaScore(
            model_name=self.name,
            symbol=symbol,
            score=score,
            confidence=confidence,
            features_used=self._essential_features,
            why=why
        )

    def _get_price(self, market_data: Dict[str, Any], features: Dict[str, Any]) -> float:
        """Extract price from market_data or features."""
        # Try market_data first
        if market_data.get("close"):
            try:
                return float(market_data["close"])
            except (ValueError, TypeError):
                pass

        # Fallback to features
        for key in ["close", "price", "last_price"]:
            if features.get(key):
                try:
                    return float(features[key])
                except (ValueError, TypeError):
                    pass

        return 0.0

    def _fail_closed_score(
        self,
        symbol: str,
        reason: str,
        why: List[str]
    ) -> AlphaScore:
        """Return fail-closed score (0 with explanation)."""
        return AlphaScore(
            model_name=self.name,
            symbol=symbol,
            score=decimal.Decimal("0"),
            confidence=decimal.Decimal("0"),
            features_used=[],
            why=[f"fail_closed:{reason}"] + why
        )

    def _calculate_confidence(self, result: ScoringResult) -> decimal.Decimal:
        """Calculate confidence from Aurora result."""
        # Use absolute dir_score + strength_score as confidence proxy
        psi = result.psi_vector
        dir_score = abs(float(psi.get("dir_score", 0)))
        strength_score = float(psi.get("strength_score", 0))

        # Combine: higher absolute direction + higher strength = higher confidence
        raw_confidence = min(1.0, (dir_score + strength_score * 0.5))

        return decimal.Decimal(str(round(raw_confidence, 4)))

    def _build_why(self, result: ScoringResult, regime: str) -> List[str]:
        """Build why chain from Aurora result."""
        why = []

        # Core score info
        psi = result.psi_vector
        why.append(f"aurora_dir={psi.get('dir_score', 0):.4f}")
        why.append(f"aurora_str={psi.get('strength_score', 0):.4f}")
        why.append(f"regime={regime}")
        why.append(f"thr_factor={float(result.threshold_factor):.2f}")

        # Side determination
        if result.side:
            why.append(f"side={result.side}")
        else:
            why.append("side=neutral")

        # Add kernel why_chain (limited)
        for w in result.why_chain[:3]:
            why.append(w)

        return why
