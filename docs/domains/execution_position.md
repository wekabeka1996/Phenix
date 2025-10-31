# Домен Execution Position (Виконання Позицій)

## Загальна інформація

**Ідентифікатор домену:** `execution_position`  
**Вер� ія:** FSMP-P1-T02  
**Роль в � и� темі:** Виконання торгових операцій та управління позиціями

## Архітектурна роль

Домен `execution_position` є виконавчим ядром торгової � и� теми Aurora. Він реалізує � кладну FSM архітектуру з трьома окремими потоками (Open, Manage, Close) для кожного � имволу, забезпечуючи надійне виконання ордерів та управління життєвим циклом позицій.

### Відповідальні� ть
- Виконання торгових інтентів через Binance API
- Управління життєвим циклом позицій (відкриття/управління/закриття)
- Забезпечення ідемпотентно� ті та відновлення пі� ля збоїв
- Інтеграція з � и� темою WAL для disaster recovery

## Структура домену

### О� новні компоненти

#### ExecPosFSM (головний орке� тратор)
Головний кла�  домену, що управляє трьома FSM потоками на � имвол.

**Ініціалізація:**
- Налаштування BinanceAdapter залежно від доменного режиму
- Ініціалізація колекцій FSM потоків для кожного � имволу
- Налаштування логування та метрик

**Методи життєвого циклу:**
- `hydrate()` - відновлення � тану з snapshot
- `handle()` - маршрутизація повідомлень до відповідних FSM

#### Три FSM потоки на � имвол

##### OpenFlowFSM (`fsm_open.py`)
**Відповідальні� ть:** Відкриття нових позицій  
**Стани:** IDLE → OPENING → OPENED  
**Події:** OPEN → DEC:ORDER_OPEN

##### ManageFlowFSM (`fsm_manage.py`)
**Відповідальні� ть:** Управління відкритими позиціями  
**Стани:** MANAGING → ADJUSTING → MANAGED  
**Події:** PARTIAL_FILL, FILL, TRADE_EXECUTED → DEC:ORDER_ADJUST

##### CloseFlowFSM (`fsm_close.py`)
**Відповідальні� ть:** Закриття позицій  
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

#### А� инхронне виконання
```
DECISION made → _execute_decision()
    ├── Safety guardrail перевірка
    ├── Виклик adapter.create_order()
    ├── Обробка feedback
    └── Емі� ія EVT:ORDER_ACCEPTED або ERR:EXECUTION_FAILED
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
**Джерело:** ExecPosFSM пі� ля виконання  
**Тригер:** У� пішне � творення ордера через adapter  
**Payload:** Підтвердження від біржі

#### ERR:EXECUTION_FAILED
**Джерело:** ExecPosFSM при помилці  
**Тригер:** Помилка виконання через adapter  
**Payload:** Деталі помилки та оригінальна decision

### Споживані події

#### CMD:OPEN
**Джерело:** Execution Management  
**Викори� тання:** Ініціація відкриття позиції  
**Обробка:** Передача до OpenFlowFSM

#### CMD:ADJUST
**Джерело:** Execution Management  
**Викори� тання:** Коригування і� нуючої позиції  
**Обробка:** Передача до ManageFlowFSM

#### CMD:CLOSE
**Джерело:** Execution Management  
**Викори� тання:** Закриття позиції  
**Обробка:** Передача до CloseFlowFSM

#### EVT:TRADE_EXECUTED
**Джерело:** Account Observer  
**Викори� тання:** Підтвердження виконання трейду  
**Обробка:** Оновлення � тану в ManageFlowFSM

## Взаємодія з іншими доменами

### Синхронні зв'язки

#### Execution Management
- **Вхід:** CMD:OPEN, CMD:ADJUST, CMD:CLOSE
- **Вихід:** DEC:ORDER_OPEN, DEC:ORDER_ADJUST, DEC:ORDER_CLOSE
- **Викори� тання:** Отримання команд на виконання операцій
- **Ча� тота:** Подієво

#### Account Observer
- **Вхід:** EVT:TRADE_EXECUTED
- **Викори� тання:** Підтвердження виконання трейдів
- **Ча� тота:** Подієво при нових трейдах

#### Position Tracking
- **Вихід:** EVT:POSITION_UPDATED
- **Викори� тання:** Інформування про зміни позицій
- **Ча� тота:** Пі� ля кожного виконання

### А� инхронні залежно� ті
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
При від� утно� ті API ключів автоматично переходить в shadow mode (логування без виконання).

## Конфігурація

### О� новні параметри
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
- **testnet:** Виконання на те� товому рахунку
- **shadow:** Логування без виконання (при від� утно� ті API ключів)

## WAL та Disaster Recovery

### WAL Integration
```python
if result and result.op == "DEC":
    wal.append(result.model_dump())
```

**Мета:** Фік� ація в� іх рішень для відновлення пі� ля збоїв.

### Hydration
```python
hydrate(position_data) -> restore FSM states
```

**Мета:** Відновлення � тану позицій пі� ля перезапу� ку.

## Моніторинг та діагно� тика

### Метрики
- Кількі� ть відкритих/закритих позицій
- Success rate виконання ордерів
- Середній ча�  виконання
- Кількі� ть guardrail triggers

### Логування
- **Інформаційні:** Створення FSM, виконання рішень
- **Попередження:** Guardrail triggers, shadow mode
- **Помилки:** Execution failures, API errors

## Обробка помилок

### Стратегії відновлення
1. **API помилки:** Логування та продовження в shadow mode
2. **FSM помилки:** Ізоляція проблемного � имволу
3. **Config помилки:** Fallback до shadow mode

### Graceful degradation
При проблемах з окремими � имволами продовжує роботу з іншими.

## Те� тування

### Інтеграційні те� ти
- Валідація в� іх трьох FSM потоків
- Перевірка safety guardrails
- Те� тування WAL integration

### Модульні те� ти
- Перевірка кожного FSM окремо
- Валідація маршрутизації команд
- Те� тування error handling

## Архітектурні о� обливо� ті

### Per-Symbol FSM Instances
Кожен � имвол має вла� ний набір з 3 FSM, що забезпечує:
- Ізоляцію � тану між � имволами
- Незалежне ма� штабування
- Спрощення логіки управління

### Command Routing Pattern
Централізована маршрутизація команд до відповідних FSM на о� нові:
- Типу операції (OPEN/MANAGE/CLOSE)
- Поточного � тану позиції
- І� торії виконання

### Async Execution
А� инхронне виконання рішень для:
- Неблокуючої роботи о� новного потоку
- Паралельного виконання multiple � имволів
- Кращої responsiveness � и� теми