# Домен Risk Management (Управління Ризиками)

## Загальна інформація

**Ідентифікатор домену:** `risk_management`  
**Роль в системі:** Оцінка та контроль торгових ризиків

## Архітектурна роль

Домен `risk_management` виконує функцію "gatekeeper" системи Aurora, оцінюючи ризики на рівні портфеля та окремих інструментів. Він аналізує ринкові умови, волатильність та стан портфеля для прийняття рішення про дозвіл торгівлі.

### Відповідальність
- Розрахунок композитного risk score з технічних індикаторів
- Моніторинг drawdown лімітів портфеля
- Контроль дозволу на торгівлю (circuit breaker)
- Оцінка волатильності та ринкових ризиків

## Структура домену

### Основні компоненти

#### RiskManagement
Головний клас домену, що реалізує оцінку ризиків.

**Ініціалізація:**
- Підписка на події features та portfolio updates
- Ініціалізація tracking для peak equity та drawdown
- Завантаження конфігурації ризиків

**Методи життєвого циклу:**
- `on_features_calculated()` - обробка технічних індикаторів
- `on_portfolio_state_updated()` - оновлення метрик портфеля

### Внутрішня архітектура

#### Двохрівнева оцінка ризиків
```
_calculate_risk_parameters()
    ├── Portfolio-level check (circuit breaker)
    │   └── Drawdown limit validation
    └── Instrument-level check (risk score)
        ├── Feature normalization
        ├── Risk score calculation
        └── Trading permission decision
```

#### Drawdown tracking
```
on_portfolio_state_updated()
    ├── Peak equity tracking
    ├── Current drawdown calculation
    └── Circuit breaker activation
```

## FSM події

### Генеровані події

#### EVT:RISK_ASSESSMENT_COMPLETED
**Частота:** При отриманні EVT:FEATURES_CALCULATED  
**Направлення:** Decision Making  

**Payload структура:**
```json
{
  "symbol": "BTCUSDT",
  "ts": 1640995200000,
  "risk_parameters": {
    "is_trading_allowed": true
  }
}
```

**Опис:** Передає рішення про дозвіл торгівлі на основі оцінки ризиків.

### Споживані події

#### EVT:FEATURES_CALCULATED
**Джерело:** Feature Engineering  
**Використання:** Отримання технічних індикаторів для розрахунку risk score  
**Частота:** Реального часу

#### EVT:PORTFOLIO_STATE_UPDATED
**Джерело:** Position Tracking  
**Використання:** Моніторинг equity для drawdown control  
**Частота:** Після кожного трейду

## Взаємодія з іншими доменами

### Синхронні зв'язки

#### Feature Engineering
- **Вхід:** EVT:FEATURES_CALCULATED
- **Використання:** OBI, TFI, delta_price для risk score
- **Частота:** Реального часу

#### Position Tracking
- **Вхід:** EVT:PORTFOLIO_STATE_UPDATED
- **Використання:** Equity tracking для drawdown limits
- **Частота:** Після трейдів

#### Decision Making
- **Вихід:** EVT:RISK_ASSESSMENT_COMPLETED
- **Використання:** is_trading_allowed для фільтрації сигналів
- **Частота:** Реального часу

### Асинхронні залежності
Критичний guardrail для всієї торгової логіки.

## Розрахунок Risk Score

### Композитний risk score
```
risk_score = delta_price_pct × w_delta +
             |obi| × w_obi +
             |tfi| × w_tfi +
             (1 - absorption) × w_absorption_inverse
```

**Нормалізація:**
- `delta_price_pct`: абсолютна зміна → відносна (%)
- `obi`, `tfi`: вже в діапазоні [-1, 1]
- `absorption`: інверсія (вища absorption = нижчий ризик)

### Trading permission
```
is_trading_allowed = risk_score ≤ max_risk_score_threshold
```

### Circuit Breaker (Portfolio-level)
```
if current_drawdown > max_daily_drawdown_limit:
    is_trading_allowed = False  # Для всіх символів
```

## Конфігурація

### Основні параметри
```yaml
risk:
  max_daily_drawdown_limit: 0.05  # 5%
  score_weights:
    delta_price: 0.05
    obi: 0.35
    tfi: 0.35
    absorption_inverse: 0.25
  trading_allowed_thresholds:
    max_risk_score: 0.8
```

### Режими роботи
- **live:** Оцінка ризиків на бойових даних
- **testnet:** Оцінка ризиків на тестових даних

## Circuit Breaker Logic

### Portfolio-level Protection
1. **Drawdown Monitoring:** Відстеження peak equity
2. **Threshold Breach:** Автоматичне блокування торгівлі
3. **Critical Logging:** Повідомлення про порушення лімітів

### Recovery
- Автоматичне відновлення при відновленні equity
- Ручне перезапуск можливий при потребі

## Моніторинг та діагностика

### Метрики
- Risk score distribution по символах
- Drawdown tracking over time
- Circuit breaker activation frequency
- Trading permission success rate

### Логування
- **Інформаційні:** Risk assessments, score calculations
- **Попередження:** High risk scores, approaching limits
- **Критичні:** Circuit breaker activations, drawdown breaches

## Обробка помилок

### Стратегії відновлення
1. **Invalid features:** Conservative assumption (high risk)
2. **Missing portfolio data:** Fallback до instrument-only checks
3. **Config errors:** Default thresholds

### Graceful degradation
При проблемах продовжує роботу з conservative settings.

## Тестування

### Інтеграційні тести
- Валідація circuit breaker логіки
- Перевірка risk score calculations
- Тестування різних ринкових умов

### Модульні тести
- Перевірка normalization функцій
- Валідація threshold logic
- Тестування drawdown calculations

## Архітектурні особливості

### Two-tier Risk Assessment
**Portfolio Level:** Circuit breaker для катастрофічних втрат  
**Instrument Level:** Risk score для оптимального sizing

### Conservative Defaults
При відсутності даних приймає conservative позицію (high risk), забезпечуючи безпеку.

### Real-time Adaptation
Risk parameters перераховуються при кожному новому features event, забезпечуючи актуальну оцінку.