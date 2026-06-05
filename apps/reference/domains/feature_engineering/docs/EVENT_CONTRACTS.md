# Контракти подій домену Feature Engineering

## Вихідні події (Outbound)

### 1. EVT:FEATURES_CALCULATED
Основний контракт даних системи.

**Payload Схема:**
```json
{
  "ts": 1640995200000,
  "symbol": "BTCUSDT",
  "tf_sec": 60,
  "bar": {
    "open": "45000.0", "high": "45100.0", "low": "44950.0", "close": "45050.0", "volume": "10.5"
  },
  "features": {
    "obi": "0.15",
    "tfi": "-0.23",
    "ema_bias": "0.62",
    "volatility_state": "0.45",
    "liquidity_kappa": "0.82"
  },
  "warmup": {
    "full_ready": true,
    "reasons": []
  }
}
```

### 2. CMD:PROCESS_STRATEGY
Команда, що оркеструє початок прийняття рішень у `decision_making`. Емітується відразу після розрахунку ознак для актуального бару.

## Вхідні події (Consumed)

### 1. EVT:MARKET_TICK_RECEIVED
**Дані**: `price`, `volume`, `bid_size`, `ask_size`, `side`.
**Ефект**: Оновлення внутрішніх лічильників та індикаторів.
