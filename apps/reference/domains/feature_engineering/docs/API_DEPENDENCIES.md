# API Dependencies - Feature Engineering Domain

**Last Updated:** 2025-11-29

---

## Core Framework Dependencies

### vFoundation
```python
from vfoundation.core.protocol import Message
from vfoundation.core import FSMCore  # TYPE_CHECKING only
```

| Component | Usage |
|-----------|-------|
| `Message` | Event payload structure for tick data |
| `FSMCore` | FSM base class (type hints only) |
| `fsm.listen()` | Subscribe to `EVT:MARKET_TICK_RECEIVED` |
| `fsm.emit()` | Publish `EVT:FEATURES_CALCULATED` |

---

## Python Standard Library

### Decimal Precision
```python
import decimal
from decimal import Decimal
```

**Critical for:**
- Price calculations without floating-point errors
- EMA computations with precise arithmetic
- All feature values stored as string-encoded decimals

### Collections
```python
from collections import deque
```

**Usage:**
- Sliding windows for SMA calculations (`maxlen` parameter)
- Anchor price buffers for macro correlation
- Volume/volatility history buffers

### Statistics
```python
import statistics
```

**Usage:**
- `statistics.mean()` for averaging correlations
- Custom Pearson correlation implementation

### Typing
```python
from typing import Dict, Any, TYPE_CHECKING, Optional
```

---

## Configuration Dependencies

### Dual Config Support Pattern
The domain supports both Pydantic (`AuroraConfig`) and dict-based configs:

```python
# Pattern used throughout
try:
    # Try domains config first (Pydantic)
    if hasattr(self.config, 'domains') and hasattr(self.config.domains, 'feature_engineering'):
        value = self.config.domains.feature_engineering.ema.period_short
    # Fallback to trading config (Pydantic)
    elif hasattr(self.config.trading, 'feature_engineering'):
        value = self.config.trading.feature_engineering.ema.period_short
    # Fallback to dict config (tests)
    elif isinstance(self.config, dict):
        value = self.config.get("trading", {}).get("feature_engineering", {}).get("ema", {}).get("period_short", 3)
    else:
        value = 3  # default
except (AttributeError, TypeError):
    value = 3  # safe default
```

### Config Schema

```yaml
# Full config structure
domains:
  feature_engineering:
    ema:
      period_short: 3
      period_long: 7
    volume:
      window_sec: 60
      sma_length: 5
    volatility:
      window_sec: 60
      sma_length: 10
    liquidity:
      depth_half: 1000
    macro_sync:
      enabled: true
      anchors: ["BTCUSDT", "ETHUSDT"]
      window: 60

# Alternative path (legacy)
trading:
  feature_engineering:
    enable_new_metrics: true
    ema: {...}
    volume: {...}
    volatility: {...}
    liquidity: {...}
  market_data:
    macro_sync: {...}
```

---

## Event Contracts

### Input Event: EVT:MARKET_TICK_RECEIVED

```json
{
  "type": "EVT:MARKET_TICK_RECEIVED",
  "payload": {
    "symbol": "string (required)",
    "ts": "integer, ms epoch (required)",
    "price": "string, decimal-encoded (required)",
    "bid_size": "string, decimal-encoded (required)",
    "ask_size": "string, decimal-encoded (required)",
    "buy_volume": "string, decimal-encoded (required)",
    "sell_volume": "string, decimal-encoded (required)"
  }
}
```

### Output Event: EVT:FEATURES_CALCULATED

```json
{
  "type": "EVT:FEATURES_CALCULATED",
  "payload": {
    "ts": "integer, ms epoch",
    "symbol": "string",
    "features": {
      "obi": "string, decimal [-1,1]",
      "tfi": "string, decimal [-1,1]",
      "delta_price": "string, decimal",
      "absorption": "string, always '0.0' (placeholder)",
      "price": "string, decimal",
      "liquidity_kappa": "string, decimal [0.3,1.0]",
      "ema_bias": "string, decimal [0,1]",
      "volume_spike": "string, decimal [0,1]",
      "volatility_state": "string, decimal [0,1]",
      "depth_imbalance": "string, decimal [0,1]",
      "macro_sync": "string, decimal [0,1]"
    }
  }
}
```

---

## State Management

### Per-Symbol State Structure

```python
symbol_state[symbol] = {
    # EMA state
    "ema3": Optional[Decimal],        # Current EMA3 value
    "ema7": Optional[Decimal],        # Current EMA7 value
    "ema3_alpha": float,              # 2 / (period_short + 1)
    "ema7_alpha": float,              # 2 / (period_long + 1)
    
    # Volume spike state
    "vol_window_start_ts": Optional[int],  # Window start timestamp
    "vol_current_ts": Optional[int],       # Last update timestamp
    "vol_window_trades": float,            # Accumulated volume in window
    "vol_hist": deque[float],              # Historical volumes (maxlen=5)
    
    # Volatility state
    "range_window_start_ts": Optional[int],
    "range_min": Optional[Decimal],
    "range_max": Optional[Decimal],
    "range_hist": deque[Decimal],          # Historical ranges (maxlen=10)
    
    # Macro sync state
    "returns_buffer": deque[float],        # Symbol returns (maxlen=60)
    "prev_price": Optional[Decimal],       # Previous price for return calc
}
```

### Anchor Prices Buffer

```python
anchor_prices: Dict[str, deque] = {
    "BTCUSDT": deque(maxlen=60),
    "ETHUSDT": deque(maxlen=60)
}
```

---

## Optional Dependencies

### Feature Store Integration

```python
# Optional - passed during initialization
feature_store: Optional[Any] = None

# Used for:
if self.feature_store:
    self.feature_store.store_features(features_payload)
    self.feature_store.aggregate_all_timeframes(symbol)
```

---

## Testing Dependencies

### Mock Objects Pattern

```python
from unittest.mock import Mock, patch

# FSM mock
class FSMCoreMock:
    def __init__(self):
        self.listeners = {}
        self.emitted = []

    def listen(self, event_name: str, callback):
        self.listeners.setdefault(event_name, []).append(callback)

    def emit(self, event_name: str, payload: dict, why: str = ""):
        self.emitted.append((event_name, payload, why))

# Config mock for tests
config = {}  # Empty dict triggers all defaults
```

---

## Algorithm Dependencies

### Pearson Correlation (Custom Implementation)

```python
def _pearson_correlation(self, x: list, y: list) -> float:
    """Compute Pearson correlation coefficient."""
    if len(x) != len(y) or len(x) < 2:
        return 0.0

    mean_x = sum(x) / len(x)
    mean_y = sum(y) / len(y)

    numerator = sum((x[i] - mean_x) * (y[i] - mean_y) for i in range(len(x)))
    denominator = (
        sum((x[i] - mean_x) ** 2 for i in range(len(x))) ** 0.5
    ) * (
        sum((y[i] - mean_y) ** 2 for i in range(len(y))) ** 0.5
    )

    return numerator / denominator if denominator > 0 else 0.0
```

---

## Error Handling

All calculations wrapped in try/except:
- Config access: Falls back to defaults
- Calculations: Logs error, continues processing
- Feature store: Non-blocking, logs warnings
