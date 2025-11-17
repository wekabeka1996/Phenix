# API Dependencies Regime Detector Domain

## vFoundation FSM Integration

### FSM Base Classes
```python
from vfoundation.core.fsm import FSM
from vfoundation.core.events import EventEmitter
from vfoundation.core.config import ConfigManager
from vfoundation.core.logging import Logger
```

### FSM Lifecycle
```python
class RegimeDetector(FSM):
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.setup_event_handlers()
        self.initialize_models()

    def setup_event_handlers(self):
        self.on('EVT:FEATURES_CALCULATED', self.on_features_calculated)

    def initialize_models(self):
        # Ініціалізація моделей визначення режиму
        pass
```

## External Dependencies

### Python Standard Library
```python
import time
from collections import deque
from decimal import Decimal, ROUND_DOWN
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
```

### Third-party Libraries
```python
import statistics  # Для розрахунку mean/stdev (якщо потрібно)
```

## Configuration Schema

### JSON Schema (2020-12)
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "regime_detector_config.schema.json",
  "type": "object",
  "properties": {
    "models": {
      "type": "object",
      "properties": {
        "sma_trend": {
          "$ref": "#/$defs/sma_trend_config"
        },
        "volatility": {
          "$ref": "#/$defs/volatility_config"
        },
        "sideways": {
          "$ref": "#/$defs/sideways_config"
        }
      },
      "required": ["sma_trend", "volatility", "sideways"]
    },
    "max_period": {
      "type": "integer",
      "minimum": 1,
      "default": 100
    }
  },
  "$defs": {
    "sma_trend_config": {
      "type": "object",
      "properties": {
        "enabled": {"type": "boolean", "default": true},
        "fast_period": {"type": "integer", "minimum": 1, "default": 5},
        "slow_period": {"type": "integer", "minimum": 1, "default": 20},
        "threshold": {"type": "number", "minimum": 0, "default": 0.001}
      },
      "required": ["enabled", "fast_period", "slow_period", "threshold"]
    },
    "volatility_config": {
      "type": "object",
      "properties": {
        "enabled": {"type": "boolean", "default": true},
        "atr_period": {"type": "integer", "minimum": 1, "default": 14},
        "high_vol_threshold": {"type": "number", "minimum": 0, "default": 2.0},
        "low_vol_threshold": {"type": "number", "minimum": 0, "default": 0.5}
      },
      "required": ["enabled", "atr_period", "high_vol_threshold", "low_vol_threshold"]
    },
    "sideways_config": {
      "type": "object",
      "properties": {
        "enabled": {"type": "boolean", "default": true},
        "sma_period": {"type": "integer", "minimum": 1, "default": 50},
        "deviation_threshold": {"type": "number", "minimum": 0, "default": 0.02}
      },
      "required": ["enabled", "sma_period", "deviation_threshold"]
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
      "properties": {
        "price": {
          "type": "string",
          "pattern": "^\\d+\\.\\d{1,8}$",
          "description": "Current price as decimal string"
        },
        "ema_bias": {
          "type": "string",
          "description": "EMA bias indicator"
        },
        "volatility_state": {
          "type": "string",
          "description": "Volatility state indicator"
        },
        "delta_price": {
          "type": "string",
          "description": "Price change delta"
        }
      },
      "required": ["price"]
    }
  },
  "required": ["ts", "symbol", "features"]
}
```

### EVT:REGIME_DETECTED Output Schema
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "regime_detected_event.schema.json",
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
    "regime": {
      "type": "string",
      "enum": ["TREND_UP", "TREND_DOWN", "SIDEWAYS", "HIGH_VOLATILITY", "LOW_VOLATILITY"],
      "description": "Detected market regime"
    },
    "confidence": {
      "type": "number",
      "minimum": 0,
      "maximum": 1,
      "description": "Confidence score [0,1]"
    },
    "model": {
      "type": "string",
      "enum": ["sma_trend", "volatility", "sideways"],
      "description": "Model that detected the regime"
    },
    "source_model": {
      "type": "string",
      "description": "Legacy model identifier for backward compatibility"
    },
    "indicators": {
      "type": "object",
      "description": "Model-specific indicators used for detection"
    }
  },
  "required": ["ts", "symbol", "regime", "confidence", "model"]
}
```

## Data Structures

### Symbol State Schema
```python
@dataclass
class SymbolState:
    """Стан для одного символу"""
    price_history: deque[Decimal] = field(default_factory=lambda: deque(maxlen=100))
    high_history: deque[Decimal] = field(default_factory=lambda: deque(maxlen=100))
    low_history: deque[Decimal] = field(default_factory=lambda: deque(maxlen=100))
    close_history: deque[Decimal] = field(default_factory=lambda: deque(maxlen=100))

    # SMA Trend model
    fast_sma: Optional[Decimal] = None
    slow_sma: Optional[Decimal] = None

    # Volatility model
    atr_values: deque[Decimal] = field(default_factory=lambda: deque(maxlen=14))
    current_atr: Optional[Decimal] = None
    avg_atr: Optional[Decimal] = None

    # Sideways model
    sideways_sma: Optional[Decimal] = None

    # Metadata
    last_update_ts: int = 0
    regime_changes: int = 0
```

### Model Configuration Schema
```python
@dataclass
class SMAConfig:
    enabled: bool = True
    fast_period: int = 5
    slow_period: int = 20
    threshold: float = 0.001

@dataclass
class VolatilityConfig:
    enabled: bool = True
    atr_period: int = 14
    high_vol_threshold: float = 2.0
    low_vol_threshold: float = 0.5

@dataclass
class SidewaysConfig:
    enabled: bool = True
    sma_period: int = 50
    deviation_threshold: float = 0.02

@dataclass
class RegimeDetectorConfig:
    models: Dict[str, Any] = field(default_factory=dict)
    max_period: int = 100
```

## Error Handling Dependencies

### Custom Exceptions
```python
class RegimeDetectorError(Exception):
    """Base exception for regime detector errors"""
    pass

class InvalidConfigurationError(RegimeDetectorError):
    """Invalid configuration provided"""
    pass

class InsufficientDataError(RegimeDetectorError):
    """Not enough data for regime detection"""
    pass

class ModelCalculationError(RegimeDetectorError):
    """Error during model calculation"""
    pass
```

### Error Response Schema
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "regime_detector_error.schema.json",
  "type": "object",
  "properties": {
    "error_type": {
      "type": "string",
      "enum": ["INVALID_CONFIG", "INSUFFICIENT_DATA", "CALCULATION_ERROR"]
    },
    "message": {
      "type": "string",
      "description": "Human-readable error message"
    },
    "symbol": {
      "type": "string",
      "description": "Symbol that caused the error"
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
- **deque maxlen**: Обмежує використання пам'яті для часових рядів
- **Decimal precision**: ROUND_DOWN для консистентності розрахунків
- **State cleanup**: Видалення старих символів після періоду неактивності

### Computational Complexity
- **SMA calculation**: O(n) де n = period (rolling average)
- **ATR calculation**: O(n) де n = atr_period
- **State updates**: O(1) amortized для deque operations

## Logging Dependencies

### Structured Logging Schema
```json
{
  "level": "INFO",
  "ts": 1640995200000,
  "component": "regime_detector",
  "symbol": "BTCUSDT",
  "event": "regime_detected",
  "regime": "TREND_UP",
  "confidence": 0.85,
  "model": "sma_trend",
  "indicators": {
    "fast_sma": "45123.45",
    "slow_sma": "44890.12",
    "trend_strength": 0.0233
  }
}
```

### Monitoring Dependencies

### Metrics Schema
```python
# Prometheus-style metrics
regime_detector_events_total{event_type, symbol, regime} - Counter
regime_detector_confidence_avg{regime} - Gauge
regime_detector_processing_time_seconds - Histogram
regime_detector_errors_total{error_type} - Counter
regime_detector_memory_usage_bytes - Gauge
```

## Testing Dependencies

### Mock Objects
```python
class MockEventEmitter:
    def __init__(self):
        self.events = []

    def emit(self, event_type: str, payload: Dict[str, Any]):
        self.events.append({
            'event': event_type,
            'payload': payload,
            'ts': time.time()
        })

class MockConfigManager:
    def __init__(self, config: Dict[str, Any]):
        self.config = config

    def get(self, key: str, default=None):
        return self.config.get(key, default)
```

## Deployment Dependencies

### Environment Variables
```bash
# Configuration
REGIME_DETECTOR_CONFIG_PATH=/path/to/config.yaml
REGIME_DETECTOR_LOG_LEVEL=INFO

# Performance tuning
REGIME_DETECTOR_MAX_PERIOD=100
REGIME_DETECTOR_WORKER_THREADS=4

# Monitoring
REGIME_DETECTOR_METRICS_PORT=9090
```

### Docker Dependencies
```dockerfile
FROM python:3.11-slim

# Install dependencies
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy application
COPY apps/reference/domains/regime_detector/ ./regime_detector/

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD python -c "from regime_detector import RegimeDetector; print('OK')"

CMD ["python", "-m", "regime_detector"]
```
