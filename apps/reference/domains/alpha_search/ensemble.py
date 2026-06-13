# apps/reference/domains/alpha_search/ensemble.py
"""
Ensemble Model for Alpha Search.

Combines multiple alpha models with optimized weights.
Supports dynamic weight adjustment based on performance metrics.
"""

import logging
from typing import Dict, List, Optional, Any, Tuple, cast
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
import numpy as np
import pandas as pd

# T2B-04: Time abstraction for deterministic testing
from apps.reference.core.time import get_clock

from .alpha_model import AlphaModel, AlphaScore


def _clock_datetime() -> datetime:
    """Get current datetime from clock abstraction (T2B-04 compliant)."""
    return datetime.fromtimestamp(get_clock().now_sec(), tz=timezone.utc)


@dataclass
class EnsembleWeights:
    """Weights for ensemble combination."""
    model_weights: Dict[str, float] = field(default_factory=dict)
    last_updated: Optional[datetime] = None
    performance_score: float = 0.0

    def normalize(self) -> None:
        """Normalize weights to sum to 1.0."""
        total = sum(self.model_weights.values())
        if total > 0:
            self.model_weights = {k: v/total for k,
                                  v in self.model_weights.items()}


@dataclass
class EnsembleConfig:
    """Configuration for ensemble model."""
    rebalance_frequency_days: int = 7  # Rebalance weights every 7 days
    min_weight: float = 0.0  # Minimum weight per model
    max_weight: float = 1.0  # Maximum weight per model
    performance_window_days: int = 30  # Lookback for performance calculation
    risk_adjustment: bool = True  # Adjust weights based on risk metrics
    objective_feedback_enabled: bool = False
    objective_feedback_window_trades: Optional[int] = None
    objective_feedback_rebalance_every_closed_trades: Optional[int] = None


class EnsembleModel(AlphaModel):
    """
    Ensemble model that combines multiple alpha models with optimized weights.

    Features:
    - Dynamic weight optimization based on historical performance
    - Risk-adjusted weighting
    - Regular rebalancing
    - Model contribution tracking
    """

    def __init__(
        self,
        config: EnsembleConfig,
        models: Dict[str, AlphaModel],
        initial_weights: Optional[Dict[str, float]] = None,
        system_config: Optional[Dict[str, Any]] = None,
        logger: Optional[logging.Logger] = None
    ):
        self._ensemble_config: EnsembleConfig = config
        self.models = models
        super().__init__(system_config or {})
        self.weights = EnsembleWeights()
        self.logger = logger or logging.getLogger(__name__)

        # Initialize weights with optional overrides
        self._initialize_weights(initial_weights)

        # Performance tracking
        self.model_performance: Dict[str, List[float]] = {
            name: [] for name in models.keys()
        }
        self.ensemble_performance: List[float] = []

        self.logger.info(
            f"EnsembleModel initialized with {len(models)} models")

        # Set name after initialization
        self.name = self.get_model_name()
        
        # ALPHA-SEARCH: Track pending signals for PnL attribution
        # Maps signal_id -> (model_name, score, symbol, timestamp)
        self._pending_signals: Dict[str, Tuple[str, float, str, float]] = {}
        self._signal_counter: int = 0
        self._feedback_trade_count: int = 0

    def get_model_name(self) -> str:
        """Return unique model name for identification."""
        return f"ensemble_{len(self.models)}_models"

    def calculate_alpha(
        self,
        symbol: str,
        market_data: Dict[str, Any],
        features: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> AlphaScore:
        """
        Calculate alpha score for given symbol.

        Args:
            symbol: Trading symbol
            market_data: Current market data (OHLCV, orderbook, etc.)
            features: Pre-calculated features
            context: Additional context (regime, portfolio state, etc.)

        Returns:
            AlphaScore with calculated signal
        """
        # Convert market_data dict to DataFrame for generate_signal
        market_df = pd.DataFrame(
            [market_data]) if market_data else pd.DataFrame()
        portfolio_state = context.get("portfolio_state") if context else None

        # A1-FIX: Pass features to generate_signal
        return self.generate_signal(market_df, portfolio_state, symbol, features)

    def _initialize_weights(self, initial_weights: Optional[Dict[str, float]] = None) -> None:
        """Initialize weights, using overrides if available, otherwise equal weights."""
        num_models = len(self.models)
        if num_models == 0:
            return

        # Start with weights dict
        weights = {}
        for name in self.models.keys():
            # Check parameter
            if initial_weights and name in initial_weights:
                weights[name] = float(initial_weights[name])
            else:
                # Check config
                model_cfg = self.config.get(name)
                if isinstance(model_cfg, dict) and "weight" in model_cfg and model_cfg["weight"] is not None:
                    weights[name] = float(model_cfg["weight"])
                elif hasattr(model_cfg, "weight") and getattr(model_cfg, "weight") is not None:
                    weights[name] = float(getattr(model_cfg, "weight"))
                else:
                    # Default
                    weights[name] = 0.0

        total = sum(weights.values())
        if total > 0:
            self.weights.model_weights = {k: v / total for k, v in weights.items()}
        else:
            equal_weight = 1.0 / num_models
            self.weights.model_weights = {
                name: equal_weight for name in self.models.keys()
            }

        self.weights.last_updated = _clock_datetime()

    def generate_signal(
        self,
        market_data: pd.DataFrame,
        portfolio_state: Optional[Dict[str, Any]] = None,
        symbol: str = "",
        features: Optional[Dict[str, Any]] = None  # A1-FIX: Accept features from caller
    ) -> AlphaScore:
        """
        Generate ensemble signal by combining model predictions.

        Args:
            market_data: Current market data
            portfolio_state: Current portfolio state

        Returns:
            Combined alpha score
        """
        if not self.models:
            return AlphaScore(
                model_name=self.name,
                symbol=symbol,
                score=Decimal("0.0"),
                confidence=Decimal("0.0"),
                why=["no_models_available"]
            )

        # Get scores from all models
        model_scores = {}
        valid_scores = []

        for model_name, model in self.models.items():
            try:
                # Convert DataFrame to dict format expected by calculate_alpha
                market_dict = market_data.to_dict(
                    'records')[0] if not market_data.empty else {}
                # A1-FIX: Use features from caller, not empty dict
                model_features = features if features else {}
                context = {
                    "portfolio_state": portfolio_state} if portfolio_state else {}

                score = model.calculate_alpha(
                    symbol=symbol,  # A1-FIX: Pass actual symbol
                    market_data=market_dict,
                    features=model_features,  # A1-FIX: Pass actual features
                    context=context
                )
                model_scores[model_name] = score
                # Only consider confident scores
                if score.confidence > Decimal("0.1"):
                    valid_scores.append((model_name, score))
            except Exception as e:
                self.logger.warning(
                    f"Error getting score from {model_name}: {e}")
                continue

        if not valid_scores:
            return AlphaScore(
                model_name=self.name,
                symbol=symbol,
                score=Decimal("0.0"),
                confidence=Decimal("0.0"),
                why=["no_valid_scores"]
            )

        # Combine scores using weights
        combined_score = self._combine_scores(valid_scores, symbol)

        # Update performance tracking
        self._update_performance_tracking(valid_scores, combined_score)

        # Check if rebalancing is needed
        self._check_rebalance()
        
        # ALPHA-SEARCH: Track signal for PnL attribution
        self._signal_counter += 1
        signal_id = f"sig_{self._signal_counter}"
        combined_score.why.append(f"signal_id={signal_id}")
        self._pending_signals[signal_id] = (
            "ensemble", float(combined_score.score), symbol, get_clock().now_sec()
        )
        
        self.logger.debug(
            f"[{symbol}] Ensemble signal: score={combined_score.score:.4f} "
            f"conf={combined_score.confidence:.4f} models={len(valid_scores)} id={signal_id}"
        )

        return combined_score

    def _combine_scores(self, valid_scores: List[Tuple[str, AlphaScore]], symbol: str) -> AlphaScore:
        """Combine scores from multiple models using weights."""
        total_weighted_score = Decimal("0.0")
        total_weight = Decimal("0.0")
        total_confidence = Decimal("0.0")
        all_features = set()
        all_why = []

        contributions = {}

        for model_name, score in valid_scores:
            weight = Decimal(
                str(self.weights.model_weights[model_name] if model_name in self.weights.model_weights else 0.0))
            if weight > 0:
                weighted_score = score.score * weight
                total_weighted_score += weighted_score
                total_weight += weight
                total_confidence += score.confidence * weight
                contributions[model_name] = {
                    "score": float(score.score),
                    "weight": float(weight),
                    "contribution": float(weighted_score)
                }

                all_features.update(score.features_used)
                all_why.extend(score.why)

        # Normalize if total weight > 0
        if total_weight > 0:
            final_score = total_weighted_score / total_weight
            final_confidence = total_confidence / total_weight
        else:
            final_score = Decimal("0.0")
            final_confidence = Decimal("0.0")

        return AlphaScore(
            model_name=self.name,
            symbol=symbol,
            score=final_score,
            confidence=final_confidence,
            features_used=list(all_features),
            why=all_why[:10]  # Limit why chain length
        )

    def _update_performance_tracking(
        self,
        valid_scores: List[Tuple[str, AlphaScore]],
        combined_score: AlphaScore
    ) -> None:
        """Update performance tracking for weight optimization."""
        # This is a simplified version - in practice, you'd need actual P&L data
        # For now, we'll use score confidence as a proxy for performance

        for model_name, score in valid_scores:
            # Track model performance (using confidence as proxy)
            self.model_performance[model_name].append(float(score.confidence))

            # Keep only recent performance data
            max_history = 100
            if len(self.model_performance[model_name]) > max_history:
                self.model_performance[model_name] = self.model_performance[model_name][-max_history:]

        # Track ensemble performance
        self.ensemble_performance.append(float(combined_score.confidence))
        if len(self.ensemble_performance) > 100:
            self.ensemble_performance = self.ensemble_performance[-100:]

    def _check_rebalance(self) -> None:
        """Check if weights need rebalancing based on performance."""
        now = _clock_datetime()
        if (self.weights.last_updated and
                (now - self.weights.last_updated).days >= self._ensemble_config.rebalance_frequency_days):
            self._rebalance_weights()

    def _rebalance_weights(self) -> None:
        """Rebalance weights based on recent performance."""
        if not self.model_performance:
            return

        # Calculate performance scores for each model
        performance_scores = {}
        for model_name, performances in self.model_performance.items():
            if performances:
                # Use average performance as score
                score = float(np.mean(performances))
                # Apply risk adjustment if enabled
                if self._ensemble_config.risk_adjustment:
                    # Penalize models with high variance (risk)
                    if len(performances) > 1:
                        variance = float(np.var(performances))
                        score = score * (1 - min(variance, 0.5))  # Cap penalty
                performance_scores[model_name] = max(
                    float(score), 0.1)  # Minimum score
            else:
                performance_scores[model_name] = 0.1  # Default for new models

        # Normalize to get weights
        total_score = sum(performance_scores.values())
        if total_score > 0:
            new_weights = {
                model: score / total_score
                for model, score in performance_scores.items()
            }

            # Apply min/max constraints
            for model in new_weights:
                new_weights[model] = max(
                    self._ensemble_config.min_weight,
                    min(self._ensemble_config.max_weight,
                        float(new_weights[model]))
                )

            # Re-normalize after constraints
            total_weight = sum(new_weights.values())
            if total_weight > 0:
                new_weights = {k: v/total_weight for k,
                               v in new_weights.items()}

            self.weights.model_weights = new_weights
            self.weights.last_updated = _clock_datetime()
            self.weights.performance_score = total_score / \
                len(performance_scores)

            self.logger.info(f"Rebalanced ensemble weights: {new_weights}")

    def on_trade_result(
        self,
        signal_id: str,
        pnl: float,
        model_name: Optional[str] = None,
        *,
        feedback_score: Optional[float] = None,
        pnl_scale: Optional[float] = None,
        feedback_trace: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Callback for trade-result feedback.
        
        ALPHA-SEARCH: Called by BacktestPlugin after trade closes.
        Updates model performance based on an explicit composite feedback score
        or a normalized realized PnL when composite feedback is unavailable.
        
        Args:
            signal_id: ID from signal's why field (e.g. "signal_id=sig_123")
            pnl: Profit/loss in USD
            model_name: Optional specific model to attribute (else uses ensemble)
            feedback_score: Optional normalized feedback score in [-1, 1]
            pnl_scale: Explicit PnL normalization scale when feedback_score is absent
            feedback_trace: Optional realized-objective payload for observability
        """
        if feedback_score is None:
            if pnl_scale is None or float(pnl_scale) <= 0.0:
                raise ValueError("pnl_scale is required when feedback_score is not provided")
            composite_feedback = max(-1.0, min(1.0, float(pnl) / float(pnl_scale)))
        else:
            composite_feedback = max(-1.0, min(1.0, float(feedback_score)))

        if signal_id in self._pending_signals:
            source_model, score, symbol, ts = self._pending_signals.pop(signal_id)
            # Attribute to all models that contributed (if ensemble) or specific model
            if model_name and model_name in self.model_performance:
                self.model_performance[model_name].append(composite_feedback)
                self._trim_performance_history(model_name)
                self.logger.debug(
                    "Trade result: %s pnl=%.2f feedback=%.4f trace=%s",
                    model_name,
                    pnl,
                    composite_feedback,
                    bool(feedback_trace),
                )
            else:
                # Distribute to all models by weight
                for m_name, m_weight in self.weights.model_weights.items():
                    weighted_feedback = composite_feedback * m_weight
                    self.model_performance[m_name].append(weighted_feedback)
                    self._trim_performance_history(m_name)
                self.logger.debug(
                    "Trade result (ensemble): pnl=%.2f feedback=%.4f models=%d trace=%s",
                    pnl,
                    composite_feedback,
                    len(self.weights.model_weights),
                    bool(feedback_trace),
                )
            self._feedback_trade_count += 1
            self._maybe_rebalance_from_feedback()
        else:
            self.logger.warning(f"Unknown signal_id: {signal_id}")

    def _trim_performance_history(self, model_name: str) -> None:
        """Trim objective-feedback performance history to explicit config window."""
        window = self._ensemble_config.objective_feedback_window_trades
        if window is None or window <= 0:
            return
        history = self.model_performance.get(model_name)
        if history is None or len(history) <= window:
            return
        self.model_performance[model_name] = history[-window:]

    def _maybe_rebalance_from_feedback(self) -> None:
        """Rebalance on explicit closed-trade cadence when objective feedback is enabled."""
        if not self._ensemble_config.objective_feedback_enabled:
            return
        cadence = self._ensemble_config.objective_feedback_rebalance_every_closed_trades
        if cadence is None or cadence <= 0:
            return
        if self._feedback_trade_count % int(cadence) == 0:
            self._rebalance_weights()

    def get_model_contributions(self) -> Dict[str, Any]:
        """Get current model contributions and weights."""
        return {
            "weights": self.weights.model_weights,
            "performance_scores": {
                model: np.mean(perfs) if perfs else 0.0
                for model, perfs in self.model_performance.items()
            },
            "last_rebalance": self.weights.last_updated.isoformat() if self.weights.last_updated else None,
            "ensemble_performance": np.mean(self.ensemble_performance) if self.ensemble_performance else 0.0
        }

    def add_model(self, name: str, model: AlphaModel) -> None:
        """Add a new model to the ensemble."""
        if name in self.models:
            self.logger.warning(f"Model {name} already exists, replacing")
        else:
            self.logger.info(f"Adding new model {name} to ensemble")

        self.models[name] = model
        # Will be set during next rebalance
        self.weights.model_weights[name] = 0.0
        self.model_performance[name] = []

        # Trigger rebalance to include new model
        self._rebalance_weights()

    def remove_model(self, name: str) -> bool:
        """Remove a model from the ensemble."""
        if name not in self.models:
            self.logger.warning(f"Model {name} not found in ensemble")
            return False

        del self.models[name]
        if name in self.weights.model_weights:
            del self.weights.model_weights[name]
        if name in self.model_performance:
            del self.model_performance[name]

        # Rebalance remaining models
        self._rebalance_weights()
        self.logger.info(f"Removed model {name} from ensemble")
        return True

    def get_ensemble_stats(self) -> Dict[str, Any]:
        """Get comprehensive ensemble statistics."""
        return {
            "num_models": len(self.models),
            "active_models": [name for name, weight in self.weights.model_weights.items() if weight > 0],
            "weights": self.weights.model_weights,
            "performance": self.get_model_contributions(),
            "config": {
                "rebalance_frequency_days": self._ensemble_config.rebalance_frequency_days,
                "min_weight": self._ensemble_config.min_weight,
                "max_weight": self._ensemble_config.max_weight,
                "performance_window_days": self._ensemble_config.performance_window_days,
                "risk_adjustment": self._ensemble_config.risk_adjustment
            }
        }
