# Домен Risk Management (Управління Ризиками)

## Загальна інформація

**Ідентифікатор домену:** `risk_management`  
**Роль в � и� темі:** Оцінка та контроль торгових ризиків

## Архітектурна роль

Домен `risk_management` виконує функцію "gatekeeper" � и� теми Aurora, оцінюючи ризики на рівні портфеля та окремих ін� трументів. Він аналізує ринкові умови, волатильні� ть та � тан портфеля для прийняття рішення про дозвіл торгівлі.

### Відповідальні� ть
- Розрахунок композитного risk score з технічних індикаторів
- Моніторинг drawdown лімітів портфеля
- Контроль дозволу на торгівлю (circuit breaker)
- Оцінка волатильно� ті та ринкових ризиків

## Структура домену

### О� новні компоненти

#### RiskManagement
Головний кла�  домену, що реалізує оцінку ризиків.

**Ініціалізація:**
- Підпи� ка на події features та portfolio updates
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
**Ча� тота:** При отриманні EVT:FEATURES_CALCULATED  
**Направлення:** Decision Making  

**Payload � труктура:**
```json
{
  "symbol": "BTCUSDT",
  "ts": 1640995200000,
  "risk_parameters": {
    "is_trading_allowed": true
  }
}
```

**Опи� :** Передає рішення про дозвіл торгівлі на о� нові оцінки ризиків.

### Споживані події

#### EVT:FEATURES_CALCULATED
**Джерело:** Feature Engineering  
**Викори� тання:** Отримання технічних індикаторів для розрахунку risk score  
**Ча� тота:** Реального ча� у

#### EVT:PORTFOLIO_STATE_UPDATED
**Джерело:** Position Tracking  
**Викори� тання:** Моніторинг equity для drawdown control  
**Ча� тота:** Пі� ля кожного трейду

## Взаємодія з іншими доменами

### Синхронні зв'язки

#### Feature Engineering
- **Вхід:** EVT:FEATURES_CALCULATED
- **Викори� тання:** OBI, TFI, delta_price для risk score
- **Ча� тота:** Реального ча� у

#### Position Tracking
- **Вхід:** EVT:PORTFOLIO_STATE_UPDATED
- **Викори� тання:** Equity tracking для drawdown limits
- **Ча� тота:** Пі� ля трейдів

#### Decision Making
- **Вихід:** EVT:RISK_ASSESSMENT_COMPLETED
- **Викори� тання:** is_trading_allowed для фільтрації � игналів
- **Ча� тота:** Реального ча� у

### А� инхронні залежно� ті
Критичний guardrail для в� ієї торгової логіки.

## Розрахунок Risk Score

### Композитний risk score
```
risk_score = delta_price_pct × w_delta +
             |obi| × w_obi +
             |tfi| × w_tfi +
             (1 - absorption) × w_absorption_inverse
```

**Нормалізація:**
- `delta_price_pct`: аб� олютна зміна → відно� на (%)
- `obi`, `tfi`: вже в діапазоні [-1, 1]
- `absorption`: інвер� ія (вища absorption = нижчий ризик)

### Trading permission
```
is_trading_allowed = risk_score ≤ max_risk_score_threshold
```

### Circuit Breaker (Portfolio-level)
```
if current_drawdown > max_daily_drawdown_limit:
    is_trading_allowed = False  # Для в� іх � имволів
```

## Конфігурація

### О� новні параметри
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
- **testnet:** Оцінка ризиків на те� тових даних

## Circuit Breaker Logic

### Portfolio-level Protection
1. **Drawdown Monitoring:** Від� теження peak equity
2. **Threshold Breach:** Автоматичне блокування торгівлі
3. **Critical Logging:** Повідомлення про порушення лімітів

### Recovery
- Автоматичне відновлення при відновленні equity
- Ручне перезапу� к можливий при потребі

## Моніторинг та діагно� тика

### Метрики
- Risk score distribution по � имволах
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

## Те� тування

### Інтеграційні те� ти
- Валідація circuit breaker логіки
- Перевірка risk score calculations
- Те� тування різних ринкових умов

### Модульні те� ти
- Перевірка normalization функцій
- Валідація threshold logic
- Те� тування drawdown calculations

## Архітектурні о� обливо� ті

### Two-tier Risk Assessment
**Portfolio Level:** Circuit breaker для ката� трофічних втрат  
**Instrument Level:** Risk score для оптимального sizing

### Conservative Defaults
При від� утно� ті даних приймає conservative позицію (high risk), забезпечуючи безпеку.

### Real-time Adaptation
Risk parameters перераховують� я при кожному новому features event, забезпечуючи актуальну оцінку.