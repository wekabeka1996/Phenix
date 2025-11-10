# Події Regime Detector Domain

## EVT:FEATURES_CALCULATED → EVT:REGIME_DETECTED

### Опис
Основний потік аналізу: від характеристик ринку до визначення режиму.

### Payload вхідний (FEATURES_CALCULATED)
```json
{
  "ts": 1640995200000,
  "symbol": "BTCUSDT",
  "features": {
    "price": "45000.50",
    "ema_bias": "0.65",
    "volatility_state": "0.78",
    "delta_price": "25.50"
  }
}
```

### Payload вихідний (REGIME_DETECTED)
```json
{
  "ts": 1640995200000,
  "symbol": "BTCUSDT",
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

## Деталі моделей визначення

### SMA Trend Detection

#### Логіка визначення
```python
# Розрахунок тренд strength
trend_strength = (fast_sma - slow_sma) / slow_sma

# Визначення режиму
if trend_strength > threshold:
    regime = "TREND_UP"
    confidence = min(trend_strength / threshold, 1.0)
elif trend_strength < -threshold:
    regime = "TREND_DOWN"
    confidence = min(abs(trend_strength) / threshold, 1.0)
else:
    regime = "SIDEWAYS"
    confidence = 1.0 - abs(trend_strength) / threshold
```

#### Конфігурація
```yaml
sma_trend:
  enabled: true
  fast_period: 5
  slow_period: 20
  threshold: 0.001  # 0.1% мінімальний тренд
```

#### Приклад розрахунку
```
fast_sma = 45123.45
slow_sma = 44890.12
trend_strength = (45123.45 - 44890.12) / 44890.12 = 0.0233
threshold = 0.001
confidence = min(0.0233 / 0.001, 1.0) = 1.0
regime = TREND_UP
```

### Volatility Regime Detection

#### ATR розрахунок
```python
def calculate_atr(highs, lows, closes, period=14):
    tr_values = []
    for i in range(1, len(highs)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i-1]),
            abs(lows[i] - closes[i-1])
        )
        tr_values.append(tr)

    # SMA of TR values
    atr = sum(tr_values[-period:]) / period
    return atr
```

#### Логіка визначення
```python
current_atr = calculate_atr(highs, lows, closes, atr_period)

if current_atr > high_vol_threshold * avg_atr:
    regime = "HIGH_VOLATILITY"
    confidence = min(current_atr / (high_vol_threshold * avg_atr), 1.0)
elif current_atr < low_vol_threshold * avg_atr:
    regime = "LOW_VOLATILITY"
    confidence = min((low_vol_threshold * avg_atr) / current_atr, 1.0)
```

#### Конфігурація
```yaml
volatility:
  enabled: true
  atr_period: 14
  high_vol_threshold: 2.0  # 2x average ATR
  low_vol_threshold: 0.5   # 0.5x average ATR
```

### Mean Reversion Detection

#### Логіка визначення
```python
# Відхилення від SMA
deviation = abs(current_price - sma) / sma

if deviation < deviation_threshold:
    regime = "MEAN_REVERSION"
    confidence = 1.0 - (deviation / deviation_threshold)
else:
    confidence = 0.0  # Не mean reversion
```

#### Конфігурація
```yaml
mean_reversion:
  enabled: true
  sma_period: 50
  deviation_threshold: 0.02  # 2% відхилення
```

## State Management

### Per-Symbol State
```python
symbol_state: Dict[str, Dict[str, Any]] = {
    "price_history": deque(maxlen=max_period),
    "high_history": deque(maxlen=max_period),
    "low_history": deque(maxlen=max_period),
    "close_history": deque(maxlen=max_period),
    "fast_sma": Optional[Decimal],
    "slow_sma": Optional[Decimal],
    "atr_values": deque(maxlen=atr_period),
    "current_atr": Optional[Decimal],
    "mean_reversion_sma": Optional[Decimal]
}
```

### Model State
```python
model_state: Dict[str, Any] = {
    "last_regime": str,
    "last_confidence": float,
    "last_update_ts": int,
    "regime_changes": int,
    "avg_atr": Optional[Decimal]  # Для volatility model
}
```

## Конфігурація залежностей

### Models Configuration
```yaml
models:
  sma_trend:
    enabled: true
    fast_period: 5
    slow_period: 20
    threshold: 0.001

  volatility:
    enabled: true
    atr_period: 14
    high_vol_threshold: 2.0
    low_vol_threshold: 0.5

  mean_reversion:
    enabled: true
    sma_period: 50
    deviation_threshold: 0.02
```

## Confidence Scoring

### Загальні правила
- **Confidence ∈ [0, 1]**: 0 = не впевнений, 1 = абсолютно впевнений
- **Threshold-based**: Впевненість базується на відхиленні від порогів
- **Normalized**: Значення нормалізуються до [0,1] діапазону

### Приклади розрахунку
```python
# TREND_UP з strength = 0.0233, threshold = 0.001
confidence = min(0.0233 / 0.001, 1.0) = 1.0

# HIGH_VOLATILITY з atr_ratio = 2.5
confidence = min(2.5 / 2.0, 1.0) = 1.0

# MEAN_REVERSION з deviation = 0.005, threshold = 0.02
confidence = 1.0 - (0.005 / 0.02) = 0.75
```

## Error Handling

### Graceful Degradation
- Якщо модель не може розрахувати: confidence = 0.0
- Якщо немає достатньо даних: пропуск визначення
- Якщо конфігурація невірна: логування warning, використання defaults

### Validation
```python
# Перевірка вхідних даних
if not features or 'price' not in features:
    self.logger.warning(f"Invalid features for {symbol}")
    return

# Перевірка періодів
if fast_period >= slow_period:
    self.logger.error("fast_period must be < slow_period")
    return
```
