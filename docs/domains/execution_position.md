# Домен Execution Position (Виконання Позицій)

## Загальна інформація

**Ідентифікатор домену:** `execution_position`  
**Версія:** FSMP-P1-T02  
**Роль в системі:** Виконання торгових операцій та управління позиціями

## Архітектурна роль

Домен `execution_position` є виконавчим ядром торгової системи Aurora. Він реалізує складну FSM архітектуру з трьома окремими потоками (Open, Manage, Close) для кожного символу, забезпечуючи надійне виконання ордерів та управління життєвим циклом позицій.

### Відповідальність
- Виконання торгових інтентів через Binance API
- Управління життєвим циклом позицій (відкриття/управління/закриття)
- Забезпечення ідемпотентності та відновлення після збоїв
- Інтеграція з системою WAL для disaster recovery

## Структура домену

### Основні компоненти

#### ExecPosFSM (головний оркестратор)
Головний клас домену, що управляє трьома FSM потоками на символ.

**Ініціалізація:**
- Налаштування BinanceAdapter залежно від доменного режиму
- Ініціалізація колекцій FSM потоків для кожного символу
- Налаштування логування та метрик

**Методи життєвого циклу:**
- `hydrate()` - відновлення стану з snapshot
- `handle()` - маршрутизація повідомлень до відповідних FSM

#### Три FSM потоки на символ

##### OpenFlowFSM (`fsm_open.py`)
**Відповідальність:** Відкриття нових позицій  
**Стани:** IDLE → OPENING → OPENED  
**Події:** OPEN → DEC:ORDER_OPEN

##### ManageFlowFSM (`fsm_manage.py`)
**Відповідальність:** Управління відкритими позиціями  
**Стани:** MANAGING → ADJUSTING → MANAGED  
**Події:** PARTIAL_FILL, FILL, TRADE_EXECUTED → DEC:ORDER_ADJUST

##### CloseFlowFSM (`fsm_close.py`)
**Відповідальність:** Закриття позицій  
**Стани:** CLOSING → CLOSED  
**Події:** CLOSE → DEC:ORDER_CLOSE

### Внутрішня архітектура

#### Маршрутизація команд
```
handle(msg) -> route to appropriate flow
    ├── OPEN → open_flow.handle()
    ├── TRADE_EXECUTED/FILL → manage_flow.handle() + close_flow.handle()
    ├── CLOSE → close_flow.handle()
    └── інші → manage_flow.handle()
```

#### Асинхронне виконання
```
DECISION made → _execute_decision()
    ├── Safety guardrail перевірка
    ├── Виклик adapter.create_order()
    ├── Обробка feedback
    └── Емісія EVT:ORDER_ACCEPTED або ERR:EXECUTION_FAILED
```

## FSM події

### Генеровані події

#### DEC:ORDER_OPEN
**Джерело:** OpenFlowFSM  
**Тригер:** Команда OPEN з валідними параметрами  
**Payload:** Параметри ордера для відкриття позиції

#### DEC:ORDER_ADJUST
**Джерело:** ManageFlowFSM  
**Тригер:** Події FILL/PARTIAL_FILL для управління позицією  
**Payload:** Параметри коригувального ордера

#### DEC:ORDER_CLOSE
**Джерело:** CloseFlowFSM  
**Тригер:** Команда CLOSE або умови закриття  
**Payload:** Параметри ордера для закриття позиції

#### EVT:ORDER_ACCEPTED
**Джерело:** ExecPosFSM після виконання  
**Тригер:** Успішне створення ордера через adapter  
**Payload:** Підтвердження від біржі

#### ERR:EXECUTION_FAILED
**Джерело:** ExecPosFSM при помилці  
**Тригер:** Помилка виконання через adapter  
**Payload:** Деталі помилки та оригінальна decision

### Споживані події

#### CMD:OPEN
**Джерело:** Execution Management  
**Використання:** Ініціація відкриття позиції  
**Обробка:** Передача до OpenFlowFSM

#### CMD:ADJUST
**Джерело:** Execution Management  
**Використання:** Коригування існуючої позиції  
**Обробка:** Передача до ManageFlowFSM

#### CMD:CLOSE
**Джерело:** Execution Management  
**Використання:** Закриття позиції  
**Обробка:** Передача до CloseFlowFSM

#### EVT:TRADE_EXECUTED
**Джерело:** Account Observer  
**Використання:** Підтвердження виконання трейду  
**Обробка:** Оновлення стану в ManageFlowFSM

## Взаємодія з іншими доменами

### Синхронні зв'язки

#### Execution Management
- **Вхід:** CMD:OPEN, CMD:ADJUST, CMD:CLOSE
- **Вихід:** DEC:ORDER_OPEN, DEC:ORDER_ADJUST, DEC:ORDER_CLOSE
- **Використання:** Отримання команд на виконання операцій
- **Частота:** Подієво

#### Account Observer
- **Вхід:** EVT:TRADE_EXECUTED
- **Використання:** Підтвердження виконання трейдів
- **Частота:** Подієво при нових трейдах

#### Position Tracking
- **Вихід:** EVT:POSITION_UPDATED
- **Використання:** Інформування про зміни позицій
- **Частота:** Після кожного виконання

### Асинхронні залежності
Залежить від Execution Management для команд та Account Observer для підтверджень.

## Safety Guardrails

### Hybrid Mode Protection
```python
if mode == "hybrid_live_data_testnet_exec":
    if "testnet" not in adapter.base_url:
        # BLOCK ORDER EXECUTION
        emit ERR:FATAL_CONFIG_MISMATCH
```

**Мета:** Запобігання виконанню бойових ордерів в гібридному режимі.

### Shadow Mode
При відсутності API ключів автоматично переходить в shadow mode (логування без виконання).

## Конфігурація

### Основні параметри
```yaml
domain_configuration:
  execution_position:
    trading_mode: "testnet"  # Зазвичай testnet в гібридному режимі

binance_api:
  testnet:
    api_key: "${BINANCE_TESTNET_API_KEY}"
    api_secret: "${BINANCE_TESTNET_API_SECRET}"
    rest_url: "https://testnet.binancefuture.com"

trading:
  execution:
    cooldown_ms: 1000
    guard_enabled: true
```

### Режими роботи
- **live:** Виконання на бойовому рахунку
- **testnet:** Виконання на тестовому рахунку
- **shadow:** Логування без виконання (при відсутності API ключів)

## WAL та Disaster Recovery

### WAL Integration
```python
if result and result.op == "DEC":
    wal.append(result.model_dump())
```

**Мета:** Фіксація всіх рішень для відновлення після збоїв.

### Hydration
```python
hydrate(position_data) -> restore FSM states
```

**Мета:** Відновлення стану позицій після перезапуску.

## Моніторинг та діагностика

### Метрики
- Кількість відкритих/закритих позицій
- Success rate виконання ордерів
- Середній час виконання
- Кількість guardrail triggers

### Логування
- **Інформаційні:** Створення FSM, виконання рішень
- **Попередження:** Guardrail triggers, shadow mode
- **Помилки:** Execution failures, API errors

## Обробка помилок

### Стратегії відновлення
1. **API помилки:** Логування та продовження в shadow mode
2. **FSM помилки:** Ізоляція проблемного символу
3. **Config помилки:** Fallback до shadow mode

### Graceful degradation
При проблемах з окремими символами продовжує роботу з іншими.

## Тестування

### Інтеграційні тести
- Валідація всіх трьох FSM потоків
- Перевірка safety guardrails
- Тестування WAL integration

### Модульні тести
- Перевірка кожного FSM окремо
- Валідація маршрутизації команд
- Тестування error handling

## Архітектурні особливості

### Per-Symbol FSM Instances
Кожен символ має власний набір з 3 FSM, що забезпечує:
- Ізоляцію стану між символами
- Незалежне масштабування
- Спрощення логіки управління

### Command Routing Pattern
Централізована маршрутизація команд до відповідних FSM на основі:
- Типу операції (OPEN/MANAGE/CLOSE)
- Поточного стану позиції
- Історії виконання

### Async Execution
Асинхронне виконання рішень для:
- Неблокуючої роботи основного потоку
- Паралельного виконання multiple символів
- Кращої responsiveness системи