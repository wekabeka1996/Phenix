# Regime Detector Domain

## Огляд

Домен `regime_detector` реалізує компонент аналізу ринкового режиму. Він обробляє характеристики ринку (features) та визначає поточний стан (TREND_UP, TREND_DOWN, MEAN_REVERSION, HIGH_VOLATILITY, LOW_VOLATILITY) з оцінкою впевненості (confidence).

## Архітектура

### Основні функції
- **Multi-model detection**: Пріоритетна логіка визначення режиму (Volatility > Mean Reversion > Trend).
- **Confidence scoring**: Динамічна оцінка впевненості для кожного режиму [0.5, 0.95].
- **Event-driven**: Реакція на `EVT:FEATURES_CALCULATED` події.
- **Warmup & Data Quality**: Вбудована перевірка готовності індикаторів та якості даних (TASK24).

### Підтримувані режими

#### Основні режими
- **TREND_UP**: Висхідний тренд (SMA Short > SMA Long & Price > SMA Short).
- **TREND_DOWN**: Низхідний тренд (SMA Short < SMA Long & Price < SMA Short).
- **MEAN_REVERSION**: Боковий рух, ціна та SMA знаходяться в межах порогу відхилення.
- **HIGH_VOLATILITY**: Період аномально високої волатильності (ATR > baseline * threshold).
- **LOW_VOLATILITY**: Період низької волатильності (ATR < baseline * low_mult).
- **UNCERTAIN**: Режим не визначений або дані недостатньої якості.

#### Додаткові режими (planned)
- **HMM States**: Приховані марковські моделі (згідно `regime.yaml`).

## Конфігурація (SSOT: config/aurora/regime.yaml)

```yaml
models:
  sma_trend:
    sma_short_period: 10
    sma_long_period: 50
  volatility:
    enabled: true
    atr_period: 14
    atr_sma_length: 100
  mean_reversion:
    threshold: 0.005
```

## Події

### Вхідні події
- `EVT:FEATURES_CALCULATED`: Характеристики ринку (price, high, low, sma_short, sma_long).

### Вихідні події
- `EVT:REGIME_DETECTED`: Визначений режим з деталями warmup та data_quality.

### Структура payload (v1)
```json
{
  "ts": 1640995200000,
  "symbol": "BTCUSDT",
  "regime": "TREND_UP",
  "confidence": "0.85",
  "source_model": "sma_trend_v1",
  "warmup": {
    "full_ready": true,
    "ticks_seen": 150,
    "ready": {"sma_short": true, "sma_long": true, "atr": true, "atr_baseline": true}
  },
  "data_quality": {"drops": [], "notes": []}
}
```


## Моделі визначення

### SMA Trend Model
**Логіка**: Порівняння швидкої та повільної SMA
```
trend_strength = (fast_sma - slow_sma) / slow_sma
if trend_strength > threshold: TREND_UP
if trend_strength < -threshold: TREND_DOWN
```

### Volatility Model
**Логіка**: ATR (Average True Range) аналіз
```
if atr > high_threshold: HIGH_VOLATILITY
if atr < low_threshold: LOW_VOLATILITY
```

### Mean Reversion Model
**Логіка**: Відхилення від SMA
```
deviation = abs(price - sma) / sma
if deviation < threshold: MEAN_REVERSION
```

## Тестування

- **5 тестів пройдено**: Різні сценарії визначення режимів
- **Покриття**: Основні моделі та edge cases
- **Типи тестів**: Unit тести для моделей визначення

## Залежності

- **decimal**: Точні розрахунки індикаторів
- **collections**: Deque для ковзних вікон, defaultdict для state
- **vFoundation**: FSM та event система
- **statistics**: Для розрахунку середніх значень
