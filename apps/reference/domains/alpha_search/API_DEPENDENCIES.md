# API Dependencies Alpha Search Domain

## vFoundation FSM Integration

### FSM Base Classes
```python
from vfoundation.core.fsm import FSM
from vfoundation.core.events import EventEmitter
from vfoundation.core.config import ConfigManager
from vfoundation.core.logging import Logger
from vfoundation.core.decorators import event_handler
```

### Event System Integration
```python
class AlphaModelFSM(FSM):
    """FSM wrapper for alpha models"""

    def __init__(self, model: AlphaModel, config: Dict[str, Any]):
        super().__init__(config)
        self.model = model
        self.setup_event_handlers()

    @event_handler('EVT:FEATURES_CALCULATED')
    def on_features_calculated(self, event):
        """Handle features from feature_engineering domain"""
        if self.model.is_ready(event.payload.get('features', {})):
            score = self.model.calculate_alpha(
                symbol=event.payload['symbol'],
                market_data={},
                features=event.payload['features']
            )

            # Emit alpha score event
            self.emit('EVT:ALPHA_SCORE_CALCULATED', {
                'ts': event.payload['ts'],
                'model_name': score.model_name,
                'symbol': score.symbol,
                'score': float(score.score),
                'confidence': float(score.confidence),
                'features_used': score.features_used,
                'why': score.why
            })
```

## External Dependencies

### Python Standard Library
```python
import logging
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any, Tuple, cast
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from collections import deque
```

### Third-party Libraries
```python
import numpy as np
import pandas as pd
from pydantic import BaseModel, Field, ValidationError
```

## Configuration Schema

### JSON Schema (2020-12)
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "alpha_search_config.schema.json",
  "type": "object",
  "properties": {
    "models": {
      "type": "object",
      "properties": {
        "momentum": {
          "$ref": "#/$defs/momentum_config"
        },
        "mean_reversion": {
          "$ref": "#/$defs/mean_reversion_config"
        },
        "volatility": {
          "$ref": "#/$defs/volatility_config"
        },
        "ensemble": {
          "$ref": "#/$defs/ensemble_config"
        }
      }
    },
    "registry": {
      "$ref": "#/$defs/registry_config"
    }
  },
  "$defs": {
    "momentum_config": {
      "type": "object",
      "properties": {
        "enabled": {"type": "boolean", "default": true},
        "momentum_periods": {
          "type": "array",
          "items": {"type": "integer", "minimum": 1},
          "default": [5, 10]
        },
        "rsi_overbought": {"type": "number", "minimum": 50, "maximum": 100, "default": 70},
        "rsi_oversold": {"type": "number", "minimum": 0, "maximum": 50, "default": 30}
      }
    },
    "mean_reversion_config": {
      "type": "object",
      "properties": {
        "enabled": {"type": "boolean", "default": true},
        "sma_period": {"type": "integer", "minimum": 1, "default": 20},
        "deviation_threshold": {"type": "number", "minimum": 0, "default": 0.02},
        "rsi_period": {"type": "integer", "minimum": 1, "default": 14}
      }
    },
    "volatility_config": {
      "type": "object",
      "properties": {
        "enabled": {"type": "boolean", "default": true},
        "atr_period": {"type": "integer", "minimum": 1, "default": 14},
        "bb_period": {"type": "integer", "minimum": 1, "default": 20},
        "high_vol_threshold": {"type": "number", "minimum": 1, "default": 2.0},
        "low_vol_threshold": {"type": "number", "minimum": 0, "maximum": 1, "default": 0.5}
      }
    },
    "ensemble_config": {
      "type": "object",
      "properties": {
        "enabled": {"type": "boolean", "default": true},
        "rebalance_frequency_days": {"type": "integer", "minimum": 1, "default": 7},
        "min_weight": {"type": "number", "minimum": 0, "maximum": 1, "default": 0.0},
        "max_weight": {"type": "number", "minimum": 0, "maximum": 1, "default": 1.0},
        "performance_window_days": {"type": "integer", "minimum": 1, "default": 30},
        "risk_adjustment": {"type": "boolean", "default": true}
      }
    },
    "registry_config": {
      "type": "object",
      "properties": {
        "max_models": {"type": "integer", "minimum": 1, "default": 10},
        "auto_register": {"type": "boolean", "default": true},
        "model_timeout_seconds": {"type": "number", "minimum": 0, "default": 30}
      }
    }
  }
}
```

## Event Schema Dependencies

### EVT:FEATURES_CALCULATED Input Schema
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "features_calculated_event.schema.json",
  "type": "object",
  "properties": {
    "ts": {
      "type": "integer",
      "description": "Timestamp in milliseconds"
    },
    "symbol": {
      "type": "string",
      "pattern": "^[A-Z0-9]{1,20}$",
      "description": "Trading symbol"
    },
    "features": {
      "type": "object",
      "description": "Calculated features from feature_engineering",
      "properties": {
        "price": {"type": "string"},
        "momentum_5": {"type": "number"},
        "momentum_10": {"type": "number"},
        "rsi": {"type": "number"},
        "sma_20": {"type": "number"},
        "bb_position": {"type": "number"},
        "atr_ratio": {"type": "number"},
        "bb_width": {"type": "number"},
        "realized_volatility_1h": {"type": "number"}
      }
    }
  },
  "required": ["ts", "symbol", "features"]
}
```

### EVT:ALPHA_SCORE_CALCULATED Output Schema
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "alpha_score_calculated_event.schema.json",
  "type": "object",
  "properties": {
    "ts": {
      "type": "integer",
      "description": "Timestamp in milliseconds"
    },
    "model_name": {
      "type": "string",
      "description": "Name of the alpha model"
    },
    "symbol": {
      "type": "string",
      "pattern": "^[A-Z0-9]{1,20}$",
      "description": "Trading symbol"
    },
    "score": {
      "type": "number",
      "minimum": -1,
      "maximum": 1,
      "description": "Alpha score [-1.0, 1.0]"
    },
    "confidence": {
      "type": "number",
      "minimum": 0,
      "maximum": 1,
      "description": "Confidence in the score [0.0, 1.0]"
    },
    "features_used": {
      "type": "array",
      "items": {"type": "string"},
      "description": "Feature names used in calculation"
    },
    "why": {
      "type": "array",
      "items": {"type": "string"},
      "description": "Reasoning chain for the score"
    },
    "contributions": {
      "type": "object",
      "description": "Model contributions (for ensemble only)"
    }
  },
  "required": ["ts", "model_name", "symbol", "score", "confidence"]
}
```

## Data Structures

### AlphaScore Model
```python
class AlphaScore(BaseModel):
    """Pydantic model for alpha score results"""

    model_name: str = Field(..., description="Name of the alpha model")
    symbol: str = Field(..., description="Trading symbol")
    score: Decimal = Field(
        ..., ge=-1, le=1,
        description="Alpha score [-1.0, 1.0], higher = stronger signal"
    )
    confidence: Decimal = Field(
        ..., ge=0, le=1,
        description="Confidence in the score [0.0, 1.0]"
    )
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="Calculation timestamp"
    )
    features_used: List[str] = Field(
        default_factory=list,
        description="Feature names used in calculation"
    )
    why: List[str] = Field(
        default_factory=list,
        description="Reasoning chain for the score"
    )

    class Config:
        json_encoders = {
            Decimal: lambda v: float(v),
            datetime: lambda v: v.isoformat()
        }
```

### Ensemble Weights
```python
@dataclass
class EnsembleWeights:
    """Weights for ensemble combination"""
    model_weights: Dict[str, float] = field(default_factory=dict)
    last_updated: Optional[datetime] = None
    performance_score: float = 0.0

    def normalize(self) -> None:
        """Normalize weights to sum to 1.0"""
        total = sum(self.model_weights.values())
        if total > 0:
            self.model_weights = {
                k: v/total for k, v in self.model_weights.items()
            }
```

### Ensemble Configuration
```python
@dataclass
class EnsembleConfig:
    """Configuration for ensemble model"""
    rebalance_frequency_days: int = 7
    min_weight: float = 0.0
    max_weight: float = 1.0
    performance_window_days: int = 30
    risk_adjustment: bool = True
```

## Error Handling Dependencies

### Custom Exceptions
```python
class AlphaModelError(Exception):
    """Base exception for alpha model errors"""
    pass

class InvalidConfigurationError(AlphaModelError):
    """Invalid model configuration"""
    pass

class InsufficientFeaturesError(AlphaModelError):
    """Required features not available"""
    pass

class CalculationError(AlphaModelError):
    """Error during alpha calculation"""
    pass

class EnsembleError(AlphaModelError):
    """Error in ensemble operations"""
    pass
```

### Error Response Schema
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "alpha_model_error.schema.json",
  "type": "object",
  "properties": {
    "error_type": {
      "type": "string",
      "enum": ["INVALID_CONFIG", "INSUFFICIENT_FEATURES", "CALCULATION_ERROR", "ENSEMBLE_ERROR"]
    },
    "message": {
      "type": "string",
      "description": "Human-readable error message"
    },
    "model_name": {
      "type": "string",
      "description": "Name of the model that caused the error"
    },
    "symbol": {
      "type": "string",
      "description": "Symbol being processed"
    },
    "ts": {
      "type": "integer",
      "description": "Timestamp when error occurred"
    }
  },
  "required": ["error_type", "message"]
}
```

## Performance Dependencies

### Memory Management
- **Feature caching**: Avoid recalculation of expensive features
- **Model state**: Efficient storage of weights and performance data
- **Deque limits**: Bounded history for performance tracking

### Computational Complexity
- **Single model**: O(1) per calculation (simple arithmetic)
- **Ensemble**: O(n) where n = number of models
- **Rebalancing**: O(m log m) where m = number of models

### Optimization Strategies
```python
# Feature caching decorator
from functools import lru_cache

class CachedAlphaModel(AlphaModel):
    @lru_cache(maxsize=1000)
    def calculate_alpha(self, symbol: str, market_data: Dict[str, Any],
                       features: Dict[str, Any], context: Optional[Dict[str, Any]] = None):
        # Cache key based on features hash
        features_hash = hash(frozenset(features.items()))
        return self._calculate_alpha_cached(symbol, features_hash, features)
```

## Logging Dependencies

### Structured Logging Schema
```json
{
  "level": "INFO",
  "ts": "2024-01-15T10:30:00Z",
  "component": "alpha_search",
  "model_name": "momentum_model",
  "symbol": "BTCUSDT",
  "event": "alpha_calculated",
  "score": 0.75,
  "confidence": 0.85,
  "features_used": ["momentum_5", "rsi"],
  "why": ["Strong upward momentum detected"],
  "calculation_time_ms": 5.2
}
```

### Log Levels
- **DEBUG**: Detailed calculation steps, feature values
- **INFO**: Alpha score results, model performance
- **WARNING**: Missing features, low confidence scores
- **ERROR**: Calculation failures, invalid configurations

## Monitoring Dependencies

### Metrics Schema
```python
# Prometheus-style metrics
alpha_search_scores_total{model_name, symbol, score_range} - Counter
alpha_search_confidence_avg{model_name} - Gauge
alpha_search_calculation_time_seconds{model_name} - Histogram
alpha_search_errors_total{model_name, error_type} - Counter
alpha_search_features_missing_total{model_name, feature_name} - Counter
alpha_search_ensemble_weights{model_name} - Gauge
```

### Health Checks
```python
def health_check() -> Dict[str, Any]:
    """Health check for alpha search domain"""
    return {
        "status": "healthy",
        "models_loaded": len(registry.list_models()),
        "last_calculation": last_calculation_ts,
        "average_confidence": avg_confidence,
        "error_rate": error_count / total_calculations
    }
```

## Testing Dependencies

### Mock Objects
```python
class MockAlphaModel(AlphaModel):
    """Mock implementation for testing"""

    def __init__(self, name="mock", fixed_score=0.5):
        super().__init__()
        self._name = name
        self._fixed_score = fixed_score

    def get_model_name(self):
        return self._name

    def get_required_features(self):
        return ["mock_feature"]

    def calculate_alpha(self, symbol, market_data, features, context=None):
        return AlphaScore(
            model_name=self._name,
            symbol=symbol,
            score=Decimal(str(self._fixed_score)),
            confidence=Decimal("0.8"),
            features_used=["mock_feature"],
            why=[f"Mock score: {self._fixed_score}"]
        )

class MockEventEmitter:
    """Mock event emitter for testing"""

    def __init__(self):
        self.events = []

    def emit(self, event_type: str, payload: Dict[str, Any]):
        self.events.append({
            "event": event_type,
            "payload": payload,
            "ts": datetime.utcnow()
        })
```

## Deployment Dependencies

### Environment Variables
```bash
# Configuration
ALPHA_SEARCH_CONFIG_PATH=/path/to/config.yaml
ALPHA_SEARCH_MODELS_ENABLED=momentum,mean_reversion,volatility,ensemble

# Performance tuning
ALPHA_SEARCH_CACHE_SIZE=1000
ALPHA_SEARCH_MAX_CALCULATION_TIME=10.0

# Monitoring
ALPHA_SEARCH_METRICS_PORT=9091
ALPHA_SEARCH_LOG_LEVEL=INFO
```

### Docker Configuration
```dockerfile
FROM python:3.11-slim

# Install dependencies
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy alpha search domain
COPY apps/reference/domains/alpha_search/ ./alpha_search/

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD python -c "
from alpha_search.alpha_model import AlphaModelRegistry, MomentumAlphaModel
registry = AlphaModelRegistry()
registry.register(MomentumAlphaModel())
print('Alpha search healthy')
"

CMD ["python", "-m", "alpha_search"]
```

## Integration Dependencies

### Feature Engineering Integration
```python
# Dependency on feature_engineering domain
FEATURES_DEPENDENCY = {
    "momentum_model": ["momentum_5", "momentum_10", "rsi"],
    "mean_reversion_model": ["sma_20", "rsi", "bb_position"],
    "volatility_model": ["atr_ratio", "bb_width", "realized_volatility_1h"]
}
```

### Decision Making Integration
```python
# Alpha scores feed into decision_making
ALPHA_OUTPUT_SCHEMA = {
    "score": "number[-1,1]",
    "confidence": "number[0,1]",
    "model_name": "string",
    "features_used": "array[string]",
    "why": "array[string]"
}
```

### Risk Management Integration
```python
# Ensemble considers risk metrics
RISK_INTEGRATION = {
    "volatility_adjustment": True,
    "correlation_penalty": True,
    "drawdown_adjustment": False
}
```
