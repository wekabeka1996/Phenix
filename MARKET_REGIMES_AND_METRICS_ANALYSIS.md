# Аналіз Режимів Ринків та Метрик у Системі Phenix

## Огляд

Цей документ містить повний аналіз всіх режимів ринків та метрик, які застосовуються в торговій системі Phenix. Інформація зібрана з конфігураційних файлів, коду доменів та документації.

## 1. Режими Ринків (Market Regimes)

### 1.1 Основні Режими (Реалізовані)

Система підтримує наступні режими ринків, які детектуються доменом `regime_detector`:

#### TREND_UP
- **Опис**: Висхідний тренд
- **Логіка детекції**: SMA Short > SMA Long та Price > SMA Short
- **Модель**: sma_trend_v1
- **Конфігурація**:
  ```yaml
  models:
    sma_trend:
      sma_short_period: 10
      sma_long_period: 50
      confidence_multiplier: 20.0
      confidence_min: 0.5
      confidence_max: 0.95
  ```

#### TREND_DOWN
- **Опис**: Низхідний тренд
- **Логіка детекції**: SMA Short < SMA Long та Price < SMA Short
- **Модель**: sma_trend_v1
- **Конфігурація**: Та сама, що й TREND_UP

#### HIGH_VOLATILITY
- **Опис**: Період аномально високої волатильності
- **Логіка детекції**: ATR > baseline * threshold_multiplier
- **Модель**: volatility_v2
- **Конфігурація**:
  ```yaml
  models:
    volatility:
      enabled: true
      atr_period: 14
      atr_sma_length: 100
      threshold_multiplier: 2.0
      high_vol_confidence_multiplier: 2.0
  ```

#### LOW_VOLATILITY
- **Опис**: Період низької волатильності
- **Логіка детекції**: ATR < baseline * low_vol_multiplier
- **Модель**: volatility_v2
- **Конфігурація**:
  ```yaml
  models:
    volatility:
      low_vol_multiplier: 0.5
      low_vol_confidence_multiplier: 3.0
  ```

#### MEAN_REVERSION
- **Опис**: Боковий рух, ціна та SMA знаходяться в межах порогу відхилення
- **Логіка детекції**: 
  - SMA spread < threshold
  - Price deviation from SMA < threshold
- **Модель**: mean_reversion_v2
- **Конфігурація**:
  ```yaml
  models:
    mean_reversion:
      threshold: 0.005
      confidence_multiplier: 100.0
  ```

#### UNCERTAIN
- **Опис**: Режим не визначений або дані недостатньої якості
- **Логіка детекції**: Default стан, коли інші умови не виконуються або є проблеми з якістю даних

### 1.2 Додаткові Режими (З Aurora Instruments)

У конфігурації `aurora_instruments.yaml` визначені додаткові режими для кожного інструменту:

#### FLAT_LOW, FLAT_NORMAL
- **Джерело**: aurora_instruments.yaml (allowed_regimes)
- **Приклад для ETHUSDT**:
  ```yaml
  allowed_regimes: ["TREND_UP", "TREND_DOWN", "FLAT_LOW", "FLAT_NORMAL", "LOW_VOLATILITY"]
  ```

### 1.3 Плановані Режими (HMM)

#### Hidden Markov Model States
- **Статус**: Конфігурація присутня, але реалізація відсутня
- **Конфігурація**:
  ```yaml
  hmm:
    enabled: true
    K: 3  # кількість прихованих станів
    emission:
      cov_kind: diag
    sticky_kappa: 0.15
    update_interval: 250
    history_hours: 48
    confidence_threshold: 0.75
  ```

### 1.4 Пріоритет Детекції Режимів

Режими детектуються в наступному порядку пріоритету:

1. **Volatility** (HIGH_VOLATILITY / LOW_VOLATILITY)
2. **Mean Reversion** (якщо volatility не визначена)
3. **Trend** (TREND_UP / TREND_DOWN) (якщо попередні не визначені)

### 1.5 Режим-залежні Модифікатори

#### Threshold Multipliers (trading.decision.regime_threshold_multipliers)
```yaml
regime_threshold_multipliers:
  HIGH_VOLATILITY: 1.2
  LOW_VOLATILITY: 0.9
  MEAN_REVERSION: 1.05
  TREND_UP: 1.0
  TREND_DOWN: 1.0
  UNCERTAIN: 1.15
  DEFAULT: 1.0
```

#### Sizing Modifiers (trading.decision.sizing_modifiers)
```yaml
sizing_modifiers:
  HIGH_VOLATILITY: 0.6    # Зменшити розмір в високій волатильності
  LOW_VOLATILITY: 1.2     # Збільшити розмір в низькій волатильності
  MEAN_REVERSION: 0.5     # Консервативний підхід
  UNCERTAIN: 0.5          # Консервативний підхід
```

#### Instrument-specific Regime Sizing (aurora_instruments.regime_sizing)
```yaml
# Для ETHUSDT
regime_sizing:
  HIGH_VOLATILITY: 0.3    # Дуже консервативно
  LOW_VOLATILITY: 1.9     # Агресивно
  MEAN_REVERSION: 0.8

# Для SOLUSDT
regime_sizing:
  HIGH_VOLATILITY: 0.6
  LOW_VOLATILITY: 2.0
```

#### Instrument-specific Allowed Regimes (aurora_instruments.allowed_regimes)
```yaml
# ETHUSDT
allowed_regimes: ["TREND_UP", "TREND_DOWN", "FLAT_LOW", "FLAT_NORMAL", "LOW_VOLATILITY"]

# SOLUSDT - не вказано, використовує всі
```

## 2. Метрики (Metrics)

### 2.1 Feature Engineering Metrics

Домен `feature_engineering` обчислює наступні метрики з ринкових даних:

#### Base Features (завжди активні)
| Метрика | Формула | Діапазон | Опис |
|---------|---------|----------|------|
| **OBI** | (bid_size - ask_size) / depth | [-1, 1] | Order Book Imbalance |
| **TFI** | (buy_vol - sell_vol) / total_flow | [-1, 1] | Trade Flow Imbalance |
| **Delta Price** | price - prev_price (якщо Δt < 5s) | ℝ | Зміна ціни з фільтром спайків |
| **Liquidity Kappa** | depth / (depth + depth_half) | [0.3, 1.0] | Нормалізована ліквідність |

#### Phase 1 Features (конфігурується)
| Метрика | Формула | Діапазон | Опис |
|---------|---------|----------|------|
| **EMA Bias** | (EMA3 - EMA7) / EMA7 → нормалізовано | [0, 1] | Індикатор короткострокового тренду |
| **Volume Spike** | current_vol / SMA(vol, 5) → обмежено 3x | [0, 1] | Детекція аномалій об'єму |
| **Volatility State** | current_range / SMA(range, 10) → обмежено 3x | [0, 1] | Поточна волатильність vs історична |
| **Depth Imbalance** | (asks + ε) / (bids + ε) → трансформовано | [0, 1] | Розподіл ліквідності |
| **Macro Sync** | Pearson(symbol_returns, anchor_returns) | [0, 1] | Кореляція з BTC/ETH |

#### V2 Features (enable_new_metrics: true)
- **volume_zscore**: Z-score об'єму
- **large_trade_imbalance**: Дисбаланс великих угод
- **spread_bps**: Спред в базисних пунктах

### 2.2 Telemetry Metrics (Prometheus)

#### Gauges (поточні значення)
- `exposure_equity_usd`: Вільний капітал (USDT-M) для розміру позицій
- `exposure_positions_usd`: Відкриті позиції в USD (ноціонал)
- `exposure_positions_margin_usd`: Відкриті позиції в USD (маржа)
- `exposure_pending_usd`: Очікуючі (зарезервовані) позиції в USD
- `exposure_pending_margin_usd`: Очікуюча маржа в USD
- `exposure_limit_usd`: Ліміт експозиції в USD
- `exposure_margin_limit_usd`: Ліміт маржі в USD
- `reservation_margin_usd`: Зарезервована маржа для очікуючих ордерів (по символу)

#### Counters (події)
- `fsm_guard_rejects_total`: Відхилення FSM guard (по типу guard)
- `pending_exposure_expired_total`: Прострочені резервації по TTL
- `manage_skipped_total`: Пропущені авто-менеджменти через bracket mode
- `orders_placed_total`: Розміщені ордери (вхід та брекети)
- `orders_filled_total`: Заповнені ордери
- `decision_rate_limited_total`: Rate-limited рішення (по символу)
- `decision_deferred_total`: Відкладені рішення (по причині та символу)
- `bridge_deferred_total`: Відкладені bridge (по причині та символу)
- `bridge_retry_total`: Повтори bridge (по символу)

#### Data Quality Metrics
- `warmup_block_total`: Блоки warmup/readiness (fail-closed)
- `data_quality_drop`: Падіння якості даних (inc_data_quality_drop)
- `config_contract_violation`: Порушення контракту конфігурації

### 2.3 Guardian Metrics (Order Guardian)

У `order_guardian.py` ведеться облік метрик:
- `entries_registered`: Зареєстровані вхідні ордери
- `cleanup_errors`: Помилки очищення
- `brackets_registered`: Зареєстровані брекети
- `reconciles_attempted`: Спроби узгодження
- `orphans_cancelled`: Скасовані сирітські ордери

## 3. Конфігурація Режимів та Метрик

### 3.1 Основні Конфігураційні Файли

#### regime.yaml
- Налаштування моделей детекції режимів
- HMM конфігурація (планована)
- Параметри для SMA, ATR, Mean Reversion

#### trading.yaml
- `regime_threshold_multipliers`: Множники порогів по режимах
- `regime_thresholds`: Пороги сигналів по режимах
- `sizing_modifiers`: Модифікатори розміру позицій

#### aurora_instruments.yaml
- `allowed_regimes`: Дозволені режими для кожного інструменту
- `regime_sizing`: Інструмент-специфічні розміри по режимах
- `regime_thresholds`: Інструмент-специфічні пороги

#### domains.yaml
- `metrics_collector`: Налаштування збору метрик
  ```yaml
  metrics_collector:
    window_size_minutes: 60
    recent_rejections_minutes: 5
  ```

### 3.2 Як Будуються Режими

#### Процес Детекції
1. **Вхід**: EVT:FEATURES_CALCULATED з характеристиками ринку
2. **Валідація**: Перевірка якості даних (fail-closed)
3. **Розрахунок**: Обчислення індикаторів (SMA, ATR) якщо потрібно
4. **Детекція**: Пріоритетна логіка по моделях
5. **Вихід**: EVT:REGIME_DETECTED з режимом та впевненістю

#### Структура Події REGIME_DETECTED
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
    "ready": {
      "sma_short": true,
      "sma_long": true,
      "atr": true,
      "atr_baseline": true
    }
  },
  "data_quality": {
    "drops": [],
    "notes": []
  }
}
```

### 3.3 Як Будуються Метрики

#### Feature Engineering Pipeline
1. **Вхід**: EVT:MARKET_TICK_RECEIVED
2. **Розрахунок**: Stateful обчислення характеристик
3. **Нормалізація**: Перетворення в [0,1] або [-1,1]
4. **Вихід**: EVT:FEATURES_CALCULATED

#### Telemetry Collection
- **Gauges**: Оновлюються при змінах стану
- **Counters**: Інкрементуються при подіях
- **Data Quality**: Автоматичне інкрементування при проблемах

## 4. Висновки

### Підтримувані Режими
- **Реалізовані**: TREND_UP, TREND_DOWN, HIGH_VOLATILITY, LOW_VOLATILITY, MEAN_REVERSION, UNCERTAIN
- **Aurora-specific**: FLAT_LOW, FLAT_NORMAL (для окремих інструментів)
- **Плановані**: HMM states (3 прихованих стани)

### Підтримувані Метрики
- **Features**: 12 метрик (4 base + 5 phase1 + 3 V2)
- **Telemetry**: 15+ gauges/counters для моніторингу системи
- **Guardian**: 5 метрик для управління ордерами

### Ключові Особливості
- **Fail-closed**: Система блокує торги при проблемах якості даних
- **Priority-based**: Чітка ієрархія детекції режимів
- **Configurable**: Режим-залежні модифікатори для кожного інструменту
- **Stateful**: Метрики зберігають стан між тиками

### Рекомендації
1. **Реалізувати HMM**: Для більш точної детекції FLAT режимів
2. **Додати адаптивні пороги**: На основі поточної волатильності
3. **Синхронізувати з FeatureEngineering**: Використовувати готові індикатори замість 2025-12-22 00:21:55,667 - apps.reference.domains.feature_engineering.feature_engineering.FeatureEngineering - INFO - Calculated features for DOGEUSDT: {"obi": "0.9952304103807177905692799226", "tfi": "-0.1405738397983588471666357977", "delta_price": "-0.00002", "absorption": "0.0", "price": "0.13236", "liquidity_kappa": "0.9529590964648183331015565295", "ema_bias": "0.4983253436734139824212727092", "volume_spike": "0.5183679706034270556195428423", "volatility_state": "0.5", "depth_imbalance": "0.04709798373275706215556340415", "macro_sync": "0.5848608146154194", "volume_zscore": "0.90492635", "large_trade_imbalance": "0.4297130801008205764544156888", "spread_bps": "0.76"}
