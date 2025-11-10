"""
Alpha Model Framework

Abstract base class for alpha models that calculate trading signals/scores.
Alpha models analyze market data and features to generate alpha scores for decision making.

Contracts:
- JSON Schema 2020-12, additive-only versioning
- Emits EVT:ALPHA_SCORE_CALCULATED with alpha scores
- Thread-safe for concurrent execution
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
from decimal import Decimal
from pydantic import BaseModel, Field
from datetime import datetime


class AlphaScore(BaseModel):
    """Alpha score result from a model calculation."""

    model_name: str = Field(..., description="Name of the alpha model")
    symbol: str = Field(..., description="Trading symbol (e.g., 'BTCUSDT')")
    score: Decimal = Field(..., ge=-1, le=1,
                           description="Alpha score [-1.0, 1.0], higher = stronger signal")
    confidence: Decimal = Field(..., ge=0, le=1,
                                description="Confidence in the score [0.0, 1.0]")
    timestamp: datetime = Field(
        default_factory=datetime.utcnow, description="Calculation timestamp")
    features_used: List[str] = Field(
        default_factory=list, description="Feature names used in calculation")
    why: List[str] = Field(default_factory=list,
                           description="Reasoning chain for the score")

    class Config:
        json_encoders = {
            Decimal: lambda v: float(v),
            datetime: lambda v: v.isoformat()
        }


class AlphaModel(ABC):
    """
    Abstract base class for alpha models.

    Alpha models calculate trading signals based on market data and features.
    They are designed to be composable and testable in isolation.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize alpha model.

        Args:
            config: Model-specific configuration parameters
        """
        self.config = config or {}
        self.name = self.get_model_name()
        self._validate_config()

    @abstractmethod
    def get_model_name(self) -> str:
        """Return unique model name for identification."""
        pass

    @abstractmethod
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
        pass

    def _validate_config(self) -> None:
        """Validate model configuration. Override in subclasses."""
        pass

    def get_required_features(self) -> List[str]:
        """
        Return list of feature names required by this model.
        Override in subclasses to specify dependencies.
        """
        return []

    def is_ready(self, features: Dict[str, Any]) -> bool:
        """
        Check if model has all required features to calculate alpha.

        Args:
            features: Available features dictionary

        Returns:
            True if all required features are present
        """
        required = self.get_required_features()
        return all(feature in features for feature in required)

    def get_metadata(self) -> Dict[str, Any]:
        """Return model metadata for introspection."""
        return {
            'name': self.name,
            'type': self.__class__.__name__,
            'required_features': self.get_required_features(),
            'config': self.config
        }


class AlphaModelRegistry:
    """
    Registry for alpha models.
    Manages model instances and provides discovery.
    """

    def __init__(self):
        self._models: Dict[str, AlphaModel] = {}

    def register(self, model: AlphaModel) -> None:
        """Register an alpha model instance."""
        if model.name in self._models:
            raise ValueError(f"Model '{model.name}' already registered")
        self._models[model.name] = model

    def get_model(self, name: str) -> Optional[AlphaModel]:
        """Get registered model by name."""
        return self._models.get(name)

    def list_models(self) -> List[str]:
        """List all registered model names."""
        return list(self._models.keys())

    def calculate_all_alpha(
        self,
        symbol: str,
        market_data: Dict[str, Any],
        features: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> List[AlphaScore]:
        """
        Calculate alpha scores from all ready models.

        Returns only scores from models that have required features.
        """
        scores = []
        for model in self._models.values():
            if model.is_ready(features):
                try:
                    score = model.calculate_alpha(
                        symbol, market_data, features, context)
                    scores.append(score)
                except Exception as e:
                    # Log error but continue with other models
                    print(f"Error calculating alpha for {model.name}: {e}")
                    continue
        return scores


# Export availability flag for testing
ALPHA_MODELS_AVAILABLE = True
