# ДОСЛІДЖЕННЯ СИСТЕМИ ВИЯВЛЕННЯ РЕЖИМУ РИНКУ

## Огляд Архітектури

Система виявлення режиму ринку в проекті Phenix реалізована через окремий домен **RegimeDetector**, який аналізує ринкові індикатори та визначає поточний торговий режим.

## Основні Компоненти

### 1. RegimeDetector Domain
**Шлях:** `apps/reference/domains/regime_detector/regime_detector.py`

#### Архітектура Класу
```python
class RegimeDetector:
    def __init__(self, config: dict, fsm)
    def _calculate_confidence(self, sma_short: Decimal, sma_long: Decimal) -> Decimal
    def handle_event(self, event: Message) -> None
```

#### Підтримувані Моделі Виявлення

##### 1. **SMA Trend Detection (sma_trend_v1)**
- **Вхідні дані:** price, sma_short, sma_long
- **Логіка:**
  - TREND_UP: `sma_short > sma_long AND price > sma_short`
  - TREND_DOWN: `sma_short < sma_long AND price < sma_short`
- **Розрахунок впевненості:**
  ```python
  spread_ratio = (sma_short - sma_long) / sma_long
  confidence = spread_ratio * Decimal("20.0")  # Евристичний множник
  bounded_confidence = min(max(abs(confidence), Decimal("0.5")), Decimal("0.95"))
  ```

##### 2. **Volatility Regime Detection (volatility_v1)**
- **Вхідні дані:** atr_14, atr_14_sma_100
- **Конфігурація:**
  ```yaml
  volatility:
    enabled: true
    threshold_multiplier: 2.0      # HIGH_VOLATILITY: ATR > 2.0 × SMA(ATR_14)
    low_vol_multiplier: 0.5        # LOW_VOLATILITY: ATR < 0.5 × SMA(ATR_14)
  ```
- **Логіка:**
  - HIGH_VOLATILITY: `atr_14 / atr_14_sma_100 > 2.0`
  - LOW_VOLATILITY: `atr_14 / atr_14_sma_100 < 0.5`

##### 3. **Mean Reversion Detection (mean_reversion_v1)**
- **Вхідні дані:** price, sma_short, sma_long
- **Конфігурація:**
  ```yaml
  mean_reversion:
    threshold: 0.005  # ±0.5% від середніх
  ```
- **Логіка:**
  ```python
  sma_spread = abs(sma_short - sma_long) / sma_long
  price_deviation_short = abs(price - sma_short) / sma_short
  price_deviation_long = abs(price - sma_long) / sma_long

  if (sma_spread < 0.005 AND
      price_deviation_short < 0.005 AND
      price_deviation_long < 0.005):
      regime = "MEAN_REVERSION"
  ```

#### Пріоритети Виявлення
1. **Пріоритет 1:** Volatility Regime (якщо ATR дані доступні)
2. **Пріоритет 2:** Mean Reversion (якщо volatility не спрацював)
3. **Пріоритет 3:** Trend Detection (якщо попередні не спрацювали)

### 2. Конфігурація
**Шлях:** `config/aurora/trading.yaml`

```yaml
models:
  volatility:
    enabled: true
    atr_period: 14
    threshold_multiplier: 2.0
    low_vol_multiplier: 0.5
  mean_reversion:
    threshold: 0.005
```

### 3. Події та Інтерфейси

#### Вхідні Події
- **EVT:FEATURES_CALCULATED** - отримує розраховані індикатори

#### Вихідні Події
- **EVT:REGIME_DETECTED** - випромінює виявлений режим

#### Структура Payload EVT:REGIME_DETECTED
```json
{
  "ts": 1731234567000000,
  "symbol": "ETHUSDT",
  "regime": "TREND_UP",
  "confidence": "0.77",
  "source_model": "sma_trend_v1"
}
```

### 4. Інтеграція з DecisionMaking

**Шлях:** `apps/reference/domains/decision_making/decision_making.py`

#### Обробка Режимів
```python
def on_regime(self, event: Message) -> None:
    self.latest_regime = event.pld
```

#### Використання Режимів у Рішеннях

##### 1. **Regime-based Filtering**
```python
# Блокування контр-трендових сигналів
if current_regime == "TREND_UP" and side == "sell":
    # Блокувати SELL у TREND_UP
if current_regime == "TREND_DOWN" and side == "buy":
    # Блокувати BUY у TREND_DOWN
```

##### 2. **Regime-based Threshold Multipliers**
```yaml
regime_threshold_multipliers:
  HIGH_VOLATILITY: 1.20   # stricter in high vol
  LOW_VOLATILITY: 0.90    # easier in low vol
  MEAN_REVERSION: 1.05
  TREND_UP: 1.00
  TREND_DOWN: 1.00
  UNCERTAIN: 1.15
  DEFAULT: 1.00
```

##### 3. **Regime-adaptive Position Sizing**
```yaml
sizing_modifiers:
  HIGH_VOLATILITY: "0.60"   # -40% position size in high volatility regimes
  LOW_VOLATILITY: "1.20"    # +20% position size in low volatility (calm market)
  MEAN_REVERSION: "0.50"    # -50% position size in ranging/mean reversion
  UNCERTAIN: "0.50"         # -50% position size when regime confidence is low
```

### 5. Тестування

#### Unit Tests
**Шлях:** `tests/domains/test_regime_detector.py`
- Тестування виявлення TREND_UP/TREND_DOWN
- Тестування MEAN_REVERSION логіки
- Тестування HIGH_VOLATILITY/LOW_VOLATILITY

#### Contract Tests
**Шлях:** `tests/contracts/test_regime_detector_contract.py`
- Валідація JSON Schema compliance
- Тестування всіх типів режимів

### 6. Схеми Даних

#### Domain Dictionary
**Шлях:** `apps/reference/domains/regime_detector/domain_dict.json`
```json
{
  "domain": "regime_detector",
  "description": "Analyzes market features to detect the current trading regime",
  "imports": [{"event": "EVT:FEATURES_CALCULATED"}],
  "exports": [{"event": "EVT:REGIME_DETECTED", "schema": "regime_detected_v1.json"}]
}
```

#### JSON Schema
**Шлях:** `apps/reference/domains/regime_detector/schemas/regime_detected_v1.json`
```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "$id": "https://aurora-core.io/schemas/regime_detected_v1.json",
  "title": "RegimeDetectedEvent_v1",
  "description": "Signals the detection of a specific market regime.",
  "type": "object",
  "properties": {
    "ts": {
      "type": "integer",
      "description": "Event timestamp (microseconds).",
      "minimum": 0
    },
    "symbol": {
      "type": "string",
      "description": "The symbol for which the regime was detected, e.g., 'ETHUSDT'.",
      "pattern": "^[A-Z0-9]+$",
      "minLength": 2,
      "maxLength": 20
    },
    "regime": {
      "type": "string",
      "enum": [
        "TREND_UP",
        "TREND_DOWN",
        "MEAN_REVERSION",
        "HIGH_VOLATILITY",
        "LOW_VOLATILITY",
        "UNCERTAIN"
      ],
      "description": "The identified market regime."
    },
    "confidence": {
      "type": "string",
      "description": "A string-encoded Decimal representing the confidence in the detection (0.0 to 1.0).",
      "pattern": "^(0(\\.\\d+)?|1(\\.0+)?)$"
    },
    "source_model": {
      "type": "string",
      "description": "The name of the model used for detection, e.g., 'HMM_v1'.",
      "minLength": 1,
      "maxLength": 50
    }
  },
  "required": ["ts", "symbol", "regime", "confidence", "source_model"],
  "additionalProperties": false
}
```

## Архітектурні Особливості

### 1. **Модульна Архітектура**
- Окремий домен з чітко визначеними інтерфейсами
- Конфігуруємі моделі виявлення
- Пріоритетна система для різних типів аналізу

### 2. **Contract-First Design**
- JSON Schema для всіх подій
- Строга типізація та валідація
- Contract tests для забезпечення сумісності

### 3. **Інтеграція з FSM**
- Подієво-орієнтована архітектура
- Асинхронна обробка через FSMCore
- Tracing через event metadata

### 4. **Конфігураційна Гнучкість**
- Вмикач моделей через config
- Налаштовувані пороги та множники
- Різні режими роботи (live/testnet)

## Поточний Статус

### ✅ Реалізовано
- Базова архітектура RegimeDetector
- Три моделі виявлення (Trend, Volatility, Mean Reversion)
- Інтеграція з DecisionMaking
- Повне тестування (unit + contract)
- JSON Schema валідація

### ⚠️ Обмеження
- **Не ініціалізується в основній системі** - відсутня ініціалізація в bootstrap/main.py
- **Тільки SMA-based trend detection** - немає інших технічних індикаторів
- **Обмежена валідація вхідних даних** - мінімальні перевірки на якість індикаторів

### 🔄 Рекомендації для Покращення
1. **Додати ініціалізацію** в основну систему (main.py)
2. **Розширити набір індикаторів** (RSI, MACD, Bollinger Bands)
3. **Додати ML-based моделі** для складніших патернів
4. **Реалізувати confidence decay** з часом
5. **Додати backtesting** для моделей

## Висновки

Система виявлення режиму ринку має солідну архітектуру з чітким розділенням відповідальностей, контрактною орієнтованістю та гнучкою конфігурацією. Основні компоненти реалізовані та протестовані, але потребують інтеграції в основну систему для повноцінного функціонування.</content>
<parameter name="filePath">c:\Users\user\Music\Phenix\REGIME_DETECTION_ANALYSIS.md
