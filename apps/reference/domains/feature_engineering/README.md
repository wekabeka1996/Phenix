# Feature Engineering Domain

## Огляд

Домен `feature_engineering` реалізує Signal компонент analyzer домену згідно roadmap. Це основний компонент для розрахунку технічних індикаторів та характеристик ринку в режимі реального часу.

## Архітектура

### Основні характеристики
- **Event-driven processing**: Обробка `EVT:MARKET_TICK_RECEIVED` подій
- **Stateful per symbol**: Окремий стан для кожного торгового символу
- **Phase 1 metrics**: Розширені метрики волатильності, ліквідності, кореляції
- **Real-time calculation**: Розрахунок характеристик на кожному tick

### Ключові метрики

#### Базові характеристики (завжди)
- **OBI (Order Book Imbalance)**: Дисбаланс між bid/ask розмірами
- **TFI (Trade Flow Imbalance)**: Дисбаланс між buy/sell обсягами
- **Delta Price**: Зміна ціни з фільтрацією спайків
- **Liquidity Kappa**: Нормалізована ліквідність order book

#### Phase 1 характеристики (опціонально)
- **EMA Bias**: Відношення EMA3/EMA7 як індикатор тренду
- **Volume Spike**: Спайки обсягу відносно SMA
- **Volatility State**: Діапазон ціни відносно SMA
- **Depth Imbalance**: Дисбаланс ліквідності
- **Macro Sync**: Кореляція з anchor символами (BTC, ETH)

## Конфігурація

```yaml
trading:
  feature_engineering:
    enable_new_metrics: true
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
  market_data:
    macro_sync:
      enabled: true
      anchors: ["BTCUSDT", "ETHUSDT"]
      window: 60
```

## Події

### Вхідні події
- `EVT:MARKET_TICK_RECEIVED`: Новий tick даних ринку

### Вихідні події
- `EVT:FEATURES_CALCULATED`: Розраховані характеристики для символу

### Структура payload
```json
{
  "ts": 1640995200000,
  "symbol": "BTCUSDT",
  "features": {
    "obi": "0.0234",
    "tfi": "-0.0123",
    "delta_price": "45.67",
    "liquidity_kappa": "0.85",
    "ema_bias": "0.72",
    "volume_spike": "0.34",
    "volatility_state": "0.56",
    "depth_imbalance": "0.78",
    "macro_sync": "0.91"
  }
}
```

## Алгоритми розрахунку

### EMA Bias
```
bias = (EMA3 - EMA7) / EMA7
bias_clamped = clamp(bias, -0.02, 0.02)
phi = (bias_clamped / 0.02 + 1) / 2  # Нормалізація до [0,1]
```

### Volume Spike
```
avg_volume = SMA(volume_windows, 5)
spike = current_volume / avg_volume
spike_capped = min(spike, 3.0)
phi = spike_capped / 3.0  # Нормалізація до [0,1]
```

### Macro Sync
```
correlations = [pearson(symbol_returns, anchor_returns) for anchor in anchors]
avg_corr = mean(correlations)
phi = (avg_corr + 1) / 2  # Нормалізація з [-1,1] до [0,1]
```

## Тестування

- **5 тестів пройдено**: Базові сценарії розрахунку характеристик
- **Покриття**: Основні метрики, edge cases, конфігурація
- **Типи тестів**: Unit тести для окремих функцій розрахунку

## Залежності

- **decimal**: Точні розрахунки фінансових показників
- **statistics**: Кореляції та статистичні функції
- **collections.deque**: Кільцеві буфери для часових вікон
- **vFoundation**: FSM та event система
