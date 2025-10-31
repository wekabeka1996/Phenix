# Домен Regime Detector (Виявлення Режимів Ринку)

## Загальна інформація

**Ідентифікатор домену:** `regime_detector`  
**Роль в � и� темі:** Аналіз ринкових режимів для адаптивної торгівлі

## Архітектурна роль

Домен `regime_detector` виконує функцію ринкового аналізатора, визначаючи поточний � тан ринку (тренд, волатильні� ть, ranging). Він аналізує технічні індикатори для кла� ифікації ринкових умов та забезпечення regime-aware торгових рішень.

### Відповідальні� ть
- Виявлення трендових режимів (TREND_UP, TREND_DOWN)
- Оцінка волатильно� ті (HIGH_VOLATILITY, LOW_VOLATILITY)
- Детекція ranging умов (MEAN_REVERSION)
- Розрахунок confidence scores для кожного режиму

## Структура домену

### О� новні компоненти

#### RegimeDetector
Головний кла�  домену, що реалізує аналіз режимів.

**Ініціалізація:**
- Завантаження конфігурації моделей виявлення
- Налаштування порогів та параметрів
- Підтримка multiple detection models

**Методи життєвого циклу:**
- `handle_event()` - обробка EVT:FEATURES_CALCULATED

### Внутрішня архітектура

#### Hierarchical Detection Logic
```
handle_event() -> detect regime
    ├── PRIORITY 1: Volatility regime (HIGH/LOW_VOLATILITY)
    ├── PRIORITY 2: Mean reversion (MEAN_REVERSION)
    └── PRIORITY 3: Trend detection (TREND_UP/TREND_DOWN)
```

#### Confidence Calculation
```
_calculate_confidence() -> confidence score
    ├── Spread ratio: (sma_short - sma_long) / sma_long
    ├── Heuristic scaling: spread_ratio × 20.0
    └── Bounding: [0.5, 0.95]
```

## FSM події

### Генеровані події

#### EVT:REGIME_DETECTED
**Ча� тота:** При отриманні EVT:FEATURES_CALCULATED  
**Направлення:** Decision Making  

**Payload � труктура:**
```json
{
  "ts": 1640995200000,
  "symbol": "BTCUSDT",
  "regime": "TREND_UP",
  "confidence": "0.77",
  "source_model": "sma_trend_v1"
}
```

**Опи� :** Передає виявлений ринковий режим з рівнем confidence.

### Споживані події

#### EVT:FEATURES_CALCULATED
**Джерело:** Feature Engineering  
**Викори� тання:** Отримання технічних індикаторів для аналізу режимів  
**Ча� тота:** Реального ча� у

## Взаємодія з іншими доменами

### Синхронні зв'язки

#### Feature Engineering
- **Вхід:** EVT:FEATURES_CALCULATED
- **Викори� тання:** SMA, ATR, price для detection algorithms
- **Ча� тота:** Реального ча� у

#### Decision Making
- **Вихід:** EVT:REGIME_DETECTED
- **Викори� тання:** Фільтрація контр-трендових � игналів
- **Ча� тота:** Реального ча� у

### А� инхронні залежно� ті
Додатковий фільтр для Decision Making domain.

## Алгоритми виявлення режимів

### Trend Detection (SMA-based)
```
TREND_UP: sma_short > sma_long AND price > sma_short
TREND_DOWN: sma_short < sma_long AND price < sma_short
```

### Volatility Regime
```
HIGH_VOLATILITY: atr_14 / atr_14_sma_100 > threshold_multiplier
LOW_VOLATILITY: atr_14 / atr_14_sma_100 < low_vol_multiplier
```

### Mean Reversion
```
MEAN_REVERSION: all values within 0.5% of each other
    ├── sma_spread < 0.005
    ├── price_deviation_short < 0.005
    └── price_deviation_long < 0.005
```

## Конфігурація

### О� новні параметри
```yaml
models:
  sma_trend:
    # Basic trend detection parameters
  volatility:
    enabled: true
    threshold_multiplier: 2.0
    low_vol_multiplier: 0.5
  mean_reversion:
    threshold: 0.005  # 0.5%
```

### Режими роботи
- **live:** Аналіз бойових ринкових даних
- **testnet:** Аналіз те� тових ринкових даних

## Моніторинг та діагно� тика

### Метрики
- Regime distribution по ча� у
- Confidence score statistics
- Model accuracy tracking
- Detection latency

### Логування
- **Інформаційні:** Виявлені режими з confidence
- **Debug:** Деталі розрахунків для кожного режиму
- **Попередження:** Missing features для detection

## Обробка помилок

### Стратегії відновлення
1. **Missing features:** Fallback до базових моделей
2. **Invalid data:** Conservative assumption (UNCERTAIN)
3. **Model failures:** Graceful degradation

### Graceful degradation
При від� утно� ті даних переходить до базових алгоритмів.

## Те� тування

### Інтеграційні те� ти
- Валідація в� іх detection algorithms
- Перевірка confidence calculations
- Те� тування різних ринкових � ценаріїв

### Модульні те� ти
- Перевірка кожного detection condition
- Валідація confidence formulas
- Те� тування edge cases

## Архітектурні о� обливо� ті

### Multi-Model Architecture
Підтримка різних моделей detection:
- **SMA Trend:** Кла� ичний trend following
- **Volatility:** Risk-based filtering
- **Mean Reversion:** Range-bound markets

### Hierarchical Priority
```
Volatility > Mean Reversion > Trend
```
Більш критичні режими мають вищий пріоритет.

### Confidence Scoring
Кожне виявлення включає confidence score для:
- Decision weighting
- Risk adjustment
- Performance tracking

## Розширення

### Майбутні моделі
- **Machine Learning:** ML-based regime classification
- **Multi-timeframe:** Cross-timeframe regime analysis
- **Inter-market:** Cross-asset regime detection
- **Sentiment analysis:** News-based regime detection