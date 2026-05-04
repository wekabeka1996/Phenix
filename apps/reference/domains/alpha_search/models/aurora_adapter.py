"""
Aurora Alpha Adapter

Wraps QuadraticScoringKernel.compute() as an AlphaModel for use in alpha_search ensemble.
Uses the same pure scoring kernel as live Aurora strategy.

ALPHA-A2: Aurora adapter for multi-provider alpha_search.
"""

import decimal
import logging
from typing import Dict, Any, Optional, List

from ..alpha_model import AlphaModel, AlphaScore
from apps.reference.shared.decision_primitives.scoring_kernel import (
    QuadraticScoringKernel,
    ScoringResult,
)

LOG = logging.getLogger(__name__)


class AuroraAlphaAdapter(AlphaModel):
    """
    Adapter that runs Aurora scoring logic as an AlphaModel.

    Uses the same pure scoring kernel as live Aurora strategy,
    ensuring consistency between shadow alpha_search and production signals.

    Note: This is read-only scoring. No side effects, no state mutation.
    """

    # Default essential features (from aurora.yaml:decision.essential_features)
    DEFAULT_ESSENTIAL_FEATURES = ["obi", "delta_price", "macro_resid"]

    # Default signal weights (from aurora.yaml:decision.signal_weights)
    DEFAULT_SIGNAL_WEIGHTS = {
        "obi": 0.15,
        "tfi": 0.15,
        "delta_price": 0.1,
        "ema_bias": 0.15,
        "volume_spike": 0.1,
        "volatility_state": 0.1,
        "depth_imbalance": -0.15,
        "macro_resid": 0.1,
        "absorption": 0.0,   # R2: disabled until Phase 2 calibration
    }

    # Default feature neutrals (from aurora.yaml:decision.feature_neutrals)
    DEFAULT_FEATURE_NEUTRALS = {
        "obi": 0.0,
        "tfi": 0.0,
        "delta_price": 0.0,
        "ema_bias": 0.5,
        "volume_spike": 0.0,
        "volatility_state": 0.0,
        "depth_imbalance": 0.5,
        "macro_sync": 0.5,
        "macro_resid": 0.0,
        "absorption": 0.0,   # R2: SIGNED feature, neutral is 0.0
    }

    # Default direction/strength config
    DEFAULT_DIRECTION_STRENGTH_CFG = {
        "directional_features": [
            "obi", "tfi", "delta_price", "ema_bias",
            "depth_imbalance", "macro_resid", "macro_sync",
            "absorption",   # R2: SIGNED [-1,1], neutral=0.0
        ],
        "strength_features": ["volume_spike", "volatility_state"],
        "strength_alpha": 0.5,
        "strength_cap": 1.0,
    }

    # Default regime thresholds
    DEFAULT_REGIME_THRESHOLDS = {
        "HIGH_VOLATILITY": 1.0,
        "LOW_VOLATILITY": 0.9,
        "MEAN_REVERSION": 0.75,
        "TREND_UP": 1.0,
        "TREND_DOWN": 1.0,
        "UNCERTAIN": 1.15,
        "DEFAULT": 1.0,
    }

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
        scoring_version: str = "quadratic",
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
            scoring_version: Scoring version (only "quadratic" is active)
        """
        # Set attributes BEFORE super().__init__() calls get_model_name()
        self._scoring_version = scoring_version

        self._essential_features = essential_features or self.DEFAULT_ESSENTIAL_FEATURES
        self._signal_weights = signal_weights or self.DEFAULT_SIGNAL_WEIGHTS
        self._feature_neutrals = feature_neutrals or self.DEFAULT_FEATURE_NEUTRALS
        self._direction_strength_cfg = direction_strength_cfg or self.DEFAULT_DIRECTION_STRENGTH_CFG
        self._regime_thresholds = regime_thresholds or self.DEFAULT_REGIME_THRESHOLDS
        self._base_threshold = decimal.Decimal(str(base_threshold))
        self._delta_price_cap_pct = decimal.Decimal(str(delta_price_cap_pct))

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

        # Run Quadratic kernel
        try:
            result: ScoringResult = QuadraticScoringKernel.compute(
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
