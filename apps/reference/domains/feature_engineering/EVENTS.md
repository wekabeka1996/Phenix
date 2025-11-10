# Події Feature Engineering Domain

## EVT:MARKET_TICK_RECEIVED → EVT:FEATURES_CALCULATED

### Опис
Основний потік обробки: від сирого tick даних до розрахованих характеристик.

### Payload вхідний (MARKET_TICK_RECEIVED)
```json
{
  "symbol": "BTCUSDT",
  "ts": 1640995200000,
  "price": "45000.50",
  "bid_size": "12.5",
  "ask_size": "8.3",
  "buy_volume": "2.1",
  "sell_volume": "1.8"
}
```

### Payload вихідний (FEATURES_CALCULATED)
```json
{
  "ts": 1640995200000,
  "symbol": "BTCUSDT",
  "features": {
    "obi": "0.2012",
    "tfi": "0.0769",
    "delta_price": "25.50",
    "liquidity_kappa": "0.8234",
    "ema_bias": "0.65",
    "volume_spike": "0.45",
    "volatility_state": "0.78",
    "depth_imbalance": "0.52",
    "macro_sync": "0.71"
  }
}
```

## Деталі розрахунку характеристик

### Order Book Imbalance (OBI)
```
depth = bid_size + ask_size
obi = (bid_size - ask_size) / depth if depth > 0 else 0
```
**Діапазон**: [-1, 1], де позитивні значення означають більший bid

### Trade Flow Imbalance (TFI)
```
total_flow = buy_volume + sell_volume
tfi = (buy_volume - sell_volume) / total_flow if total_flow > 0 else 0
```
**Діапазон**: [-1, 1], де позитивні значення означають переважання buy

### Delta Price
```
time_diff = current_ts - last_ts
delta_price = price - last_price if time_diff < 5000ms else 0
```
**Фільтр**: Ігнорує великі часовы скачки для уникнення спайків

### Liquidity Kappa
```
depth_half = config.depth_half (default: 1000)
ratio = depth / (depth + depth_half)
kappa = clamp(ratio, 0.3, 1.0)
```
**Нормалізація**: Мінімальна ліквідність = 0.3, максимальна = 1.0

## Phase 1 метрики

### EMA Bias
- **Періоди**: EMA3 та EMA7
- **Розрахунок**: `(EMA3 - EMA7) / EMA7`
- **Нормалізація**: Кламп до ±2%, потім до [0,1]
- **Інтерпретація**: >0.5 = bullish bias, <0.5 = bearish bias

### Volume Spike
- **Вікно**: 60 секунд накопичення
- **SMA**: 5 періодів для baseline
- **Розрахунок**: `current_volume / avg_volume`
- **Кап**: Максимум 3.0x для нормалізації

### Volatility State
- **Вікно**: 60 секунд діапазону
- **SMA**: 10 періодів діапазонів
- **Розрахунок**: `current_range / avg_range`
- **Кап**: Максимум 3.0x

### Depth Imbalance
```
ratio = (ask_size + depth_half) / (bid_size + depth_half)
imbalance = (ratio - 1) / (ratio + 1)
phi = (imbalance + 1) / 2
```
**Нормалізація**: З [-1,1] до [0,1]

### Macro Sync
- **Anchors**: BTCUSDT, ETHUSDT (за замовчуванням)
- **Вікно**: 60 періодів returns
- **Метод**: Pearson correlation з усередненням по anchors
- **Нормалізація**: З [-1,1] до [0,1]

## State Management

### Per-Symbol State
```python
{
    "ema3": Decimal,
    "ema7": Decimal,
    "ema3_alpha": float,
    "ema7_alpha": float,
    "vol_window_start_ts": int,
    "vol_current_ts": int,
    "vol_window_trades": float,
    "vol_hist": deque,
    "range_window_start_ts": int,
    "range_min": Decimal,
    "range_max": Decimal,
    "range_hist": deque,
    "returns_buffer": deque,
    "prev_price": Decimal
}
```

### Anchor Prices Buffer
```python
anchor_prices: Dict[str, deque]  # maxlen = macro_window
```

## Конфігурація залежностей

### EMA Config
```yaml
ema:
  period_short: 3
  period_long: 7
```

### Volume Config
```yaml
volume:
  window_sec: 60
  sma_length: 5
```

### Volatility Config
```yaml
volatility:
  window_sec: 60
  sma_length: 10
```

### Liquidity Config
```yaml
liquidity:
  depth_half: 1000
```

### Macro Sync Config
```yaml
macro_sync:
  enabled: true
  anchors: ["BTCUSDT", "ETHUSDT"]
  window: 60
```
