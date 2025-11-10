# API Dependencies - Feature Engineering Domain

## Core Dependencies

### vFoundation Framework
```python
from vfoundation.core.protocol import Message
from vfoundation.core import FSMCore
```

**Використання:**
- `Message`: Структура event'ів для tick даних
- `FSMCore`: Базовий клас для FSM компонентів
- `fsm.listen()`: Підписка на події
- `fsm.emit()`: Генерація подій з характеристиками

### Decimal Precision
```python
import decimal
from decimal import Decimal
```

**Використання:**
- Точні розрахунки фінансових показників
- EMA розрахунки з підтримкою decimal
- Price comparisons та arithmetic
- Запобігання помилкам округлення

### Collections & Data Structures
```python
from collections import deque
from typing import Dict, Any, Optional
```

**Використання:**
- `deque`: Кільцеві буфери для часових вікон (maxlen)
- `Dict[str, deque]`: Anchor prices buffers
- `Dict[str, Dict]`: Per-symbol state storage
- Type hints для кращої IDE підтримки

### Statistics & Math
```python
import statistics
```

**Використання:**
- `statistics.mean()`: Усереднення кореляцій
- `statistics.pstdev()`: Для статистичних розрахунків
- Pearson correlation coefficients

## Configuration Dependencies

### Hybrid Config Support
```python
# Pydantic-first з fallback
if hasattr(self.config.trading, 'feature_engineering'):
    fe_config = self.config.trading.feature_engineering
elif isinstance(self.config, dict):
    fe_config = self.config.get("trading", {}).get("feature_engineering", {})
```

**Використання:**
- Підтримка як Pydantic AuroraConfig, так і dict configs
- Graceful fallback для тестів та legacy код
- Safe attribute access з defaults

### Config Structure
```python
# EMA config
ema_config = {
    "period_short": 3,
    "period_long": 7
}

# Volume config
volume_config = {
    "window_sec": 60,
    "sma_length": 5
}

# Volatility config
volatility_config = {
    "window_sec": 60,
    "sma_length": 10
}

# Liquidity config
liquidity_config = {
    "depth_half": 1000
}

# Macro sync config
macro_sync_config = {
    "enabled": True,
    "anchors": ["BTCUSDT", "ETHUSDT"],
    "window": 60
}
```

## Event Processing Dependencies

### Input Event Schema
```json
{
  "type": "EVT:MARKET_TICK_RECEIVED",
  "payload": {
    "symbol": "string",
    "ts": "integer (ms)",
    "price": "string (decimal)",
    "bid_size": "string (decimal)",
    "ask_size": "string (decimal)",
    "buy_volume": "string (decimal)",
    "sell_volume": "string (decimal)"
  }
}
```

### Output Event Schema
```json
{
  "type": "EVT:FEATURES_CALCULATED",
  "payload": {
    "ts": "integer (ms)",
    "symbol": "string",
    "features": {
      "obi": "string (decimal)",
      "tfi": "string (decimal)",
      "delta_price": "string (decimal)",
      "liquidity_kappa": "string (decimal)",
      "ema_bias": "string (decimal)",
      "volume_spike": "string (decimal)",
      "volatility_state": "string (decimal)",
      "depth_imbalance": "string (decimal)",
      "macro_sync": "string (decimal)"
    }
  }
}
```

## State Management Dependencies

### Per-Symbol State Structure
```python
symbol_state: Dict[str, Dict[str, Any]] = {
    "ema3": Optional[Decimal],
    "ema7": Optional[Decimal],
    "ema3_alpha": float,
    "ema7_alpha": float,
    "vol_window_start_ts": Optional[int],
    "vol_current_ts": Optional[int],
    "vol_window_trades": float,
    "vol_hist": deque,
    "range_window_start_ts": Optional[int],
    "range_min": Optional[Decimal],
    "range_max": Optional[Decimal],
    "range_hist": deque,
    "returns_buffer": deque,
    "prev_price": Optional[Decimal]
}
```

### Anchor Prices Management
```python
anchor_prices: Dict[str, deque] = {}
for anchor in anchor_symbols:
    anchor_prices[anchor] = deque(maxlen=macro_window)
```

## Algorithm Dependencies

### EMA Calculation
```python
def _update_ema(self, symbol: str, price: Decimal) -> None:
    alpha = 2 / (period + 1)  # EMA alpha
    ema = price * alpha + prev_ema * (1 - alpha)
```

### Pearson Correlation
```python
def _pearson_correlation(self, x: list, y: list) -> float:
    # Statistics module або власна реалізація
    return statistics.correlation(x, y) if hasattr(statistics, 'correlation') else custom_impl
```

## Testing Dependencies

### Mock Objects
```python
from unittest.mock import Mock, patch

# FSM mock
fsm = Mock()
fsm.emit = Mock()
fsm.listen = Mock()

# Config mock для тестів
config = {
    "trading": {
        "feature_engineering": {
            "enable_new_metrics": False,
            "liquidity": {"depth_half": 1000}
        }
    }
}
```

### Test Data Generation
- Реалістичні tick дані з різними сценаріями
- Edge cases: нульові обсяги, extreme prices
- Time series для тестування віконних функцій

## Performance Considerations

### Memory Management
- **Deque maxlen**: Запобігає memory leaks для часових вікон
- **Per-symbol state**: Лінійний ріст з кількістю символів
- **Anchor buffers**: Фіксований розмір незалежно від кількості символів

### Computational Complexity
- **O(1)**: Основні розрахунки (EMA, OBI, TFI)
- **O(window_size)**: SMA розрахунки для volume/volatility
- **O(anchors × window)**: Macro sync кореляції

### Optimization Opportunities
- **Vectorization**: NumPy для масових розрахунків
- **Caching**: EMA значень для уникнення перерахунків
- **Async processing**: Для CPU-intensive macro sync
