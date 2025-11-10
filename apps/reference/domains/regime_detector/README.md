# Regime Detector Domain

## Огляд

Домен `regime_detector` реалізує Regime компонент analyzer домену згідно roadmap. Це компонент для визначення поточного ринкового режиму на основі технічних індикаторів та характеристик.

## Архітектура

### Основні функції
- **Multi-model detection**: Підтримка різних моделей визначення режиму
- **Confidence scoring**: Оцінка впевненості для кожного режиму
- **Event-driven**: Реакція на `EVT:FEATURES_CALCULATED` події
- **Stateful analysis**: Аналіз трендів та волатильності з часом

### Підтримувані режими

#### Основні режими
- **TREND_UP**: Висхідний тренд з високою впевненістю
- **TREND_DOWN**: Низхідний тренд з високою впевненістю
- **MEAN_REVERSION**: Боковий рух, ціна близько до SMA
- **HIGH_VOLATILITY**: Період високої волатильності
- **LOW_VOLATILITY**: Період низької волатильності

#### Додаткові режими (planned)
- **BREAKOUT**: Прорив рівнів опору/підтримки
- **CONSOLIDATION**: Консолідація перед великим рухом
- **PANIC_SELLING**: Паніка та масові продажі

## Конфігурація

```yaml
trading:
  regime_detector:
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

## Події

### Вхідні події
- `EVT:FEATURES_CALCULATED`: Характеристики ринку для аналізу

### Вихідні події
- `EVT:REGIME_DETECTED`: Визначений режим з впевненістю

### Структура payload
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
