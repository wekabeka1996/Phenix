# DOMAIN DOCUMENTATION — execution_position

## 1) Domain Overview
Домен `execution_position` є критичним виконавчим шаром (Execution Layer) торгової системи. Його головна роль — детерміноване перетворення торгових намірів (`TRADE_INTENT`) у життєвий цикл біржових ордерів з гарантіями безпеки та цілісності стану.

**Роль домену:**
- **За що відповідає:** Валідація ордерів, перевірка ризик-лімітів (Margin/Notional), маршутизація команд до адаптера біржі, супровід позиції (TP/SL, Trailing), реконсиляція стану ордерів, логування торгових подій.
- **Що НЕ повинно бути в цьому домені:** Прийняття стратегічних рішень (alpha-generation), розрахунок технічних індикаторів, управління підключенням до мережі (цим займається Transport/Adapter layer).

**Основні сценарії (use-cases):**
1. **Open Position Flow**: Отримання `CMD:OPEN` → Перевірка `ExecutionGuard` → Валідація `LOT_SIZE/MIN_NOTIONAL` → Виставлення ENTRY ордера.
2. **Bracket Management**: Виставлення та оновлення TP/SL брекетів після заповнення (FILL) вхідного ордера.
3. **Trailing Stop/Management**: Динамічне корегування цін виходу залежно від руху ринку.
4. **Risk Enforcement**: Блокування або "кліпінг" (зменшення) обсягу ордера, якщо він перевищує ліміти концентрації або маржі.
5. **Auto-Cleanup (Watchdog)**: Скасування ордерів, що "зависли" (не заповнилися за TTL), та очищення "осиротілих" (orphaned) TP/SL.

**Інваріанти/Тарантії:**
- **Fail-Closed**: Будь-яка непевність (помилка валідації, таймаут, відсутність даних про ціну) призводить до відхилення операції.
- **Idempotency**: Використання `OrderIndex` та `idempotent_key` для запобігання дублюванню ордерів при повторних сигналах.
- **Price Integrity (Anti-2021)**: Гарантія того, що ціна TP/SL завжди знаходиться на правильному боці від поточного Mark Price, щоб уникнути помилки `-2021` (Order would immediately trigger).

---

## 2) Public Interfaces / Contracts
Ключові вхідні точки домену:

### Клас `OrderPayload` ([contracts.py](file:///home/wekabeka/Музыка/Phenix/apps/reference/domains/execution_position/contracts.py#L85))
- **Input**: `symbol`, `side`, `qty`, `order_type`, `price`, `tif`.
- **Validation**: Strict Pydantic V2. Перевіряє `MIN_ORDER_QTY`, `MAX_ORDER_QTY`, `MIN_NOTIONAL`. 
- **Side effects**: Квантує `qty` та `price` згідно з `QTY_STEP`/`PRICE_STEP`.
- **Error modes**: `ValueError` при порушенні лімітів або відсутності `price` для LIMIT-ордерів.

### Клас `BracketOrderPayload` ([contracts.py](file:///home/wekabeka/Музыка/Phenix/apps/reference/domains/execution_position/contracts.py#L181))
- **Input**: Поля `OrderPayload` + `stop_price`, `working_type`, `close_position`.
- **Logic**: Забороняє передачу `qty`, якщо `close_position=True` (Binance rule). Вимагає `stop_price` для умовних ордерів.

### Функція `normalize_qty` ([qty_normalizer.py](file:///home/wekabeka/Музыка/Phenix/apps/reference/domains/execution_position/qty_normalizer.py#L73))
- **Input**: `raw_qty`, `price`, `step_size`, `min_qty`, `min_notional`.
- **Output**: `QtyNormalizeResult` (ok, qty, why).
- **Logic**: Суворе дотримання `ROUND_DOWN`. Без "silent bump-ups" (якщо qty < min_qty, ордер відхиляється, а не збільшується до мінімуму).
- **Error Modes**: Повертає `NRR-QTY-BELOW-MIN_QTY` або `NRR-NOTIONAL-BELOW-MIN`.

---

## 3) Event & Message Map
Домен працює як реактивна система на базі `LocalBus` та `TRADE_INTENT`.

### а) Домен ПРИЙМАЄ
| Подія / Команда | Джерело | Payload | Ефект |
| :--- | :--- | :--- | :--- |
| `CMD:OPEN` | DecisionMaking | `CmdOpenPayload` | Запуск FSM відкриття позиції. |
| `CMD:CLOSE` | Strategy / UI | `Symbol, Reason` | Негайне закриття позиції по ринку/ліміту. |
| `EVT:ORDER_ACK` | BinanceAdapter | `order_id, symbol` | Підтвердження розміщення ордера на біржі. |
| `EVT:ORDER_FILL` | BinanceAdapter | `qty, price, is_full` | Перехід до Manage-фази або закриття стейту. |
| `EVT:MARK_PRICE` | Transport | `symbol, price` | Перерахунок TP/SL, Trailing stop, перевірка Anti-2021. |

### б) Домен ВІДПРАВЛЯЄ
| Подія / Команда | Призначення | Payload | Ефект |
| :--- | :--- | :--- | :--- |
| `TRADE_INTENT_PROPOSED` | Logs / Telemetry | `rid, symbol, size...` | Реєстрація наміру в логах ([aurora_log_adapter.py](file:///home/wekabeka/Музыка/Phenix/apps/reference/domains/execution_position/aurora_log_adapter.py#L56)). |
| `TRADE_DECISION` | Logs / Metrics | `rid, decision, reason` | Фіксація результату валідації (ACCEPTED/REJECTED). |
| `TRADE_EXECUTION` | System Workflows | `order_id, status` | Оновлення глобального стану портфеля. |
| `GUARD_REJECTION` | Risk Monitoring | `guard_type, reason` | Алертинг про порушення ризик-лімітів. |

---

## 4) File-by-file Documentation

### [file: contracts.py](file:///home/wekabeka/Музыка/Phenix/apps/reference/domains/execution_position/contracts.py)
- **Purpose**: Централізований репозиторій моделей даних та констант для ордерів.
- **Key symbols**: `Side`, `OrderType`, `OrderStatus`, `OrderPayload`, `BracketOrderPayload`, `TPSLValidationRules`.
- **Logic summary**: Використовує Pydantic V2 для суворої типізації. Забезпечує перехресну валідацію полів (наприклад, лімітні ордери обов'язково мають ціну). Реалізує `TPSLValidationRules` для перевірки коректності стоп-цін відносно маркіровочної ціни.
- **Dependencies**: `pydantic`, `decimal`.
- **Data structures**: `BaseModel` (Pydantic), `Enum`.
- **Risks**:
    - `LOW`: Жорстко закодовані `MIN_NOTIONAL = 10.0` ([L78](file:///home/wekabeka/Музыка/Phenix/apps/reference/domains/execution_position/contracts.py#L78)). Може не відповідати лімітам для деяких альткоїнів або при зміні правил Binance.
    - `MED`: `ROUND_DOWN` у валідаторах ([L124](file:///home/wekabeka/Музыка/Phenix/apps/reference/domains/execution_position/contracts.py#L124)) може призвести до того, що `qty` стане менше `minNotional` після квантування, якщо вхідне значення було на межі.
- **Notes**: Містить корисний метод `add_safety_offset` ([L323](file:///home/wekabeka/Музыка/Phenix/apps/reference/domains/execution_position/contracts.py#L323)) для додавання буфера до ціни стопів.

### [file: reasons.py](file:///home/wekabeka/Музыка/Phenix/apps/reference/domains/execution_position/reasons.py)
- **Purpose**: Single Source of Truth для кодів причин скасування та відхилення ордерів.
- **Key symbols**: `MAKER_ONLY_REJECT`, `CANCEL_TTL_EXPIRED`, `CANCEL_PANIC_KILL`, `OPEN_GUARD_FAIL`.
- **Logic summary**: Визначає константи типу `Literal` для забезпечення консистентності телеметрії та логів.
- **Dependencies**: None (pure constants).
- **Data structures**: `str` (Literal).
- **Risks**:
    - `LOW`: Відсутність мапінгу на всі можливі помилки Binance API (тільки базові/критичні).
- **Notes**: Полегшує Forensic-аналіз логів, дозволяючи шукати за унікальними токенами.

### [file: aurora_log_adapter.py](file:///home/wekabeka/Музыка/Phenix/apps/reference/domains/execution_position/aurora_log_adapter.py)
- **Purpose**: Адаптер для структурованого логування торгових подій Aurora.
- **Key symbols**: `AuroraLogAdapter`, `log_trade_intent`, `log_trade_decision`, `log_trade_execution`.
- **Logic summary**: Створює/використовує окремий логгер `aurora.trades`. Наповнює лог-повідомлення багатим контекстом (`rid`, `symbol`, `risk_score`, `features`).
- **Dependencies**: `logging`, `apps.reference.core.time.get_clock`.
- **Data structures**: `dict` (extra fields).
- **Risks**:
    - `MED`: При інтенсивній торгівлі (багато символів) файл `logs/aurora_trades.log` може швидко рости. Відсутня ротація логів у самому класі.
    - `LOW`: `log_data` створюється вручну; якщо додати багато `extra_fields`, це може сповільнити критичний шлях виконання (latency).
- **Notes**: Використовує детермінований час із `Clock` ([L89](file:///home/wekabeka/Музыка/Phenix/apps/reference/domains/execution_position/aurora_log_adapter.py#L89)), що важливо для бектесту.

### [file: utils.py](file:///home/wekabeka/Музыка/Phenix/apps/reference/domains/execution_position/utils.py)
- **Purpose**: Утиліти для маніпуляцій з цінами та генерації ID.
- **Key symbols**: `quantize_stop_price`, `validate_anti_2021`, `generate_client_order_id`, `calc_tp_sl_from_mark`, `BoundedEventDeduper`.
- **Logic summary**: Реалізує складну логіку `validate_anti_2021` для коригування стоп-цін. `generate_client_order_id` створює детерміновані ID довжиною до 32 символів (MD5 hash). `BoundedEventDeduper` забезпечує захист від дублів з обмеженою пам'яттю.
- **Dependencies**: `hashlib`, `re`, `apps.reference.core.time.get_clock`.
- **Data structures**: `Decimal`, `OrderedDict` (для `BoundedEventDeduper`).
- **Risks**:
    - `HIGH`: У `calc_tp_sl_from_mark` ([L259](file:///home/wekabeka/Музыка/Phenix/apps/reference/domains/execution_position/utils.py#L259)) викидається `ValueError` (fail-fast), якщо ціна не проходить перевірку. Якщо це станеться в рантаймі під час трейлінгу, FSM може "впасти", не оновивши стоп.
    - `MED`: MD5 хеш для `client_order_id` ([L168](file:///home/wekabeka/Музыка/Phenix/apps/reference/domains/execution_position/utils.py#L168)) має малу ймовірність колізій, але для торгової системи це теоретичний ризик дублювання ордера на біржі.
- **Notes**: `_utc_hm` та `_in_quiet` (винесені в `fsm.py` у outline, але часто бувають в utils) — важливо для "годин спокою".

### [file: utils_event_bus.py](file:///home/wekabeka/Музыка/Phenix/apps/reference/domains/execution_position/utils_event_bus.py)
- **Purpose**: Полегшена шина подій для домену.
- **Key symbols**: `LocalBus`.
- **Logic summary**: Проста реалізація Pub-Sub. Дозволяє компонентам домену (FSM, Guardian) спілкуватися без прямої залежності.
- **Dependencies**: `logging`.
- **Risks**:
    - `CRITICAL`: Перехоплює виключення в колбеках і просто їх логує ([L57](file:///home/wekabeka/Музыка/Phenix/apps/reference/domains/execution_position/utils_event_bus.py#L57)). Це **silent suppression**. Якщо обробник `ORDER_FILL` впаде через помилку БД, система продовжить роботу, вважаючи, що подія успішно оброблена.
- **Notes**: Синхронна шина — обробка відбувається в потоці емітера.

### [file: qty_normalizer.py](file:///home/wekabeka/Музыка/Phenix/apps/reference/domains/execution_position/qty_normalizer.py)
- **Purpose**: Сувора нормалізація обсягу ордера.
- **Key symbols**: `normalize_qty`, `QtyNormalizeResult`, `NR_QTY_ROUNDED_TO_ZERO`.
- **Logic summary**: Приводить `raw_qty` до `step_size` через `ROUND_DOWN`. Перевіряє `min_qty` та `min_notional`. Якщо хоча б одна умова не виконується — результат `ok=False`.
- **Dependencies**: `decimal`, `dataclasses`.
- **Risks**:
    - `HIGH`: **Fail-closed** на малих депозитах. Якщо розрахований обсяг 10.05 USDT, а `min_notional` 10.1 USDT, ордер буде відхилено. НЕМАЄ автоматичного "підтягування" до мінімуму.
- **Notes**: Використовує унікальні `NRR` коди для діагностики.

---

### [file: fsm.py](file:///home/wekabeka/Музыка/Phenix/apps/reference/domains/execution_position/fsm.py)
- **Purpose**: Головний оркестратор домену. Керує життєвим циклом символьних потоків та інтегрує всі сервіси (Watchdog, Guardian, Adapter).
- **Deep Dive**: Детальний аналіз логіки, станів та обробки помилок доступний у [FSM_DEEP_DIVE.md](file:///home/wekabeka/Музыка/Phenix/apps/reference/domains/execution_position/docs/FSM_DEEP_DIVE.md).
- **Key symbols**: `ExecPosFSM`, `_in_quiet`, `run_leverage_bootstrap`, `_resolve_price`.
- **Logic summary**: Створює екземпляри `OpenFlowFSM`, `ManageFlowFSM`, `CloseFlowFSM` для кожного символу. Маршрутизує події з шини до відповідних потоків. Виконує "розумну" екстракцію цін ([L678](file:///home/wekabeka/Музыка/Phenix/apps/reference/domains/execution_position/fsm.py#L678)) з різних форматів пейлоадів стратегій. Забезпечує детермінованість через `get_clock()` (**DET-BT-13**) та обробку superseded-ордерів (**EP-01.3**).
- **Dependencies**: `OpenFlowFSM`, `ManageFlowFSM`, `CloseFlowFSM`, `BinanceAdapter`, `ExposureGuard`, `OrderTimeoutWatchdog`, `OrderGuardian`.
- **Data structures**: `Dict` (per-symbol flows), `BoundedEventDeduper`.
- **Risks**:
    - `CRITICAL`: **God Object Pattern**. Файл містить понад 4400 рядків коду, що робить його надзвичайно складним для підтримки та тестування.
    - `HIGH`: **Thread-safety of flows**. Хоча є лок `_flows_lock` ([L167](file:///home/wekabeka/Музыка/Phenix/apps/reference/domains/execution_position/fsm.py#L167)), інтенсивне перемикання між асинхронним адаптером та синхронною логікою FSM може призвести до Race Conditions при оновленні стану `manage_flows`.
- **Notes**: Реалізує `run_leverage_bootstrap` ([L565](file:///home/wekabeka/Музыка/Phenix/apps/reference/domains/execution_position/fsm.py#L565)) — обов'язковий крок перед початком торгівлі для синхронізації плеча.

### [file: fsm_open.py](file:///home/wekabeka/Музыка/Phenix/apps/reference/domains/execution_position/fsm_open.py)
- **Purpose**: Стан-машина для відкриття позиції.
- **Key symbols**: `CmdOpenPayload`, `OpenFlowFSM`, `handle_async`.
- **Logic summary**: Виконує сувору валідацію `CMD:OPEN` через Pydantic. Включає перевірку `idempotent_key`, `panic_killswitch`, лімітів обсягу та ціни. Новий метод `handle_async` додає обов'язкову верифікацію плеча через `LeverageService` ([L514](file:///home/wekabeka/Музыка/Phenix/apps/reference/domains/execution_position/fsm_open.py#L514)).
- **Dependencies**: `contracts.py`, `MetricsCollector`, `LeverageService`.
- **Data structures**: `CmdOpenPayload` (strict Pydantic model).
- **Risks**:
    - `HIGH`: **Fail-Closed on Config**. Якщо в `domains.yaml` відсутній блок `fsm_open`, FSM відмовляється стартувати ([L131](file:///home/wekabeka/Музыка/Phenix/apps/reference/domains/execution_position/fsm_open.py#L131)). Це безпечно, але може спричинити раптову зупинку всієї системи при помилці в конфігу.
    - `MED`: **Decimal Precision Gap**. Хоча Quantization працює, `qty_rounded != qty_dec` лише логує попередження ([L344](file:///home/wekabeka/Музыка/Phenix/apps/reference/domains/execution_position/fsm_open.py#L344)), продовжуючи виконання з округленим значенням. Це може бути неочікуваним для стратегії.
- **Notes**: Забороняє `extra` поля в пейлоаді (`extra='forbid'`), що гарантує відсутність помилок у назвах полів.

### [file: fsm_close.py](file:///home/wekabeka/Музыка/Phenix/apps/reference/domains/execution_position/fsm_close.py)
- **Purpose**: Стан-машина закриття позиції ("Soldier Pattern").
- **Key symbols**: `CloseFlowFSM`, `_check_close_conditions`.
- **Logic summary**: Надзвичайно спрощений модуль. Його єдина роль — виконати `CMD:CLOSE`. Будь-які автономні правила закриття за часом чи подіями (Reject/Expire) свідомо вимкнені ([L135](file:///home/wekabeka/Музыка/Phenix/apps/reference/domains/execution_position/fsm_close.py#L135)).
- **Risks**:
    - `HIGH`: **No Failsafe**. Якщо домен `DecisionMaking` "зависне" або не надішле `CMD:CLOSE` при критичному сигналі, цей модуль НЕ зробить нічого для захисту капіталу самостійно.
- **Notes**: Гідратує стан з `position_data` ([L55](file:///home/wekabeka/Музыка/Phenix/apps/reference/domains/execution_position/fsm_close.py#L55)) при старті.

### [file: order_index.py](file:///home/wekabeka/Музыка/Phenix/apps/reference/domains/execution_position/order_index.py)
- **Purpose**: Кореляційний індекс життєвого циклу ордерів.
- **Key symbols**: `OrderRef`, `OrderIndex`, `try_reserve_entry`.
- **Logic summary**: Зв'язує `rid`, `idempotent_key`, `clientOrderId` та `exchangeOrderId`. Дозволяє швидкий пошук ордера за будь-яким ідентифікатором. Використовує `RLock` для повної потокобезпеки.
- **Dependencies**: `threading`.
- **Data structures**: `dataclass OrderRef`, `Dict` для індексів.
- **Risks**:
    - `MED`: **Memory Leak potential**. Хоча є метод `expire()` ([L259](file:///home/wekabeka/Музыка/Phenix/apps/reference/domains/execution_position/order_index.py#L259)), він має бути викликаний зовнішнім циклом (у `fsm.py`). Якщо цикл перестане працювати, об'єкти `OrderRef` накопичуватимуться.
- **Notes**: `try_reserve_entry` ([L182](file:///home/wekabeka/Музыка/Phenix/apps/reference/domains/execution_position/order_index.py#L182)) є критичним для запобігання дублюванню входів (TASK49 - Fix TOCTOU).

### [file: order_guardian.py](file:///home/wekabeka/Музыка/Phenix/apps/reference/domains/execution_position/order_guardian.py)
- **Purpose**: Шар делегування для реконсиляції ордерів.
- **Key symbols**: `OrderGuardian`, `_resolve_guardian_cfg`.
- **Logic summary**: Тонкий обгортка навколо `services/order_guardian`. Забезпечує роботу з персистентним SQLite леджером через `OrderLedger` ([L126](file:///home/wekabeka/Музыка/Phenix/apps/reference/domains/execution_position/order_guardian.py#L126)).
- **Dependencies**: `OrderLedger`, `LedgerStoreAdapter`, `ServicesGuardian`.
- **Risks**:
    - `HIGH`: **Complex Config Resolution**. Метод `_resolve_guardian_cfg` ([L23](file:///home/wekabeka/Музыка/Phenix/apps/reference/domains/execution_position/order_guardian.py#L23)) дуже складний і намагається знайти конфіг у 3-4 різних місцях. Це призводить до крихкості при оновленні структури `domains.yaml`.
- **Notes**: Підтримує режим "Unified", що дозволяє зберігати стан ордерів між перезапусками системи.

---

### [file: fsm_manage.py](file:///home/wekabeka/Музыка/Phenix/apps/reference/domains/execution_position/fsm_manage.py)
- **Purpose**: Стан-машина для управління відкритою позицією (Trailing, TP/SL, Timeouts).
- **Key symbols**: `ManageFlowFSM`, `set_intent_prices`, `_check_max_hold_time`, `_place_brackets`.
- **Logic summary**: Найскладніший модуль управління. Забезпечує виставлення брекет-ордерів (SL/TP) після входу. Реалізує логіку трейлінг-стопу та часткових виходів (TP1/TP2). Підтримує `WAIT_MODE` для станів, коли ціна знаходиться в нейтральній зоні.
- **Dependencies**: `contracts.py`, `MetricsCollector`, `PendingBracketsWAL`.
- **Risks**:
    - `CRITICAL`: **FAIL-CLOSED POLICY**. Модуль відмовляється працювати (викидає Error), якщо у символу немає явного конфігу в `strategies.aurora.assets`. Немає дефолтного фолбеку, що може зупинити торги по нових парах.
    - `HIGH`: **Complexity of `_place_brackets`**. Метод займає понад 240 рядків ([L532](file:///home/wekabeka/Музыка/Phenix/apps/reference/domains/execution_position/fsm_manage.py#L532)) і обробляє безліч станів (OCO, LIMIT, MARKET TP/SL). Це "крихке" місце під час оновлення логіки Binance.
- **Notes**: Вміє гідратувати ціни наміру ([L253](file:///home/wekabeka/Музыка/Phenix/apps/reference/domains/execution_position/fsm_manage.py#L253)), що дозволяє розділити розрахунок (у стратегії) та виконання (у домені).

### [file: exposure_guard.py](file:///home/wekabeka/Музыка/Phenix/apps/reference/domains/execution_position/exposure_guard.py)
- **Purpose**: Комплексний шлюз ризик-менеджменту.
- **Key symbols**: `ExposureGuard`, `can_open`, `enter_fallback_mode`, `SoftClipEngine`.
- **Logic summary**: Перевіряє торгову операцію за 6+ критеріями (Equity, Utilization, Concentration, Directional Ratio). Реалізує `SoftLimit` — замість повної відмови, він може зменшити (`clip`) обсяг ордера до допустимого ліміту. Підтримує `Fallback Mode` для екстреного зниження ризиків при технічних збоях.
- **Dependencies**: `SoftClipEngine`, `MetricsAggregator`, `DomainConfigResolver`.
- **Data structures**: `ExposureState` (резервації не заповнених ордерів).
- **Risks**:
    - `HIGH`: **Staleness Check**. Якщо `EVT:PORTFOLIO_STATE_UPDATED` затримується більше ніж на `stale_ttl_sec`, шлюз закривається для ВСІХ нових ордерів ([L478](file:///home/wekabeka/Музыка/Phenix/apps/reference/domains/execution_position/exposure_guard.py#L478)).
    - `MED`: **Decimal Math Overhead**. Велика кількість обчислень з `Decimal` на кожен `can_open` може створювати мікро-затримки при високій частоті сигналів.
- **Notes**: Використовує алертинг через `AlertManager` при вході/виході з `Fallback Mode`.

### [file: watchdog.py](file:///home/wekabeka/Музыка/Phenix/apps/reference/domains/execution_position/watchdog.py)
- **Purpose**: Моніторинг таймаутів виконання ордерів та детекція зависань.
- **Key symbols**: `OrderTimeoutWatchdog`, `track_order_placed`, `_poll_order_statuses`.
- **Logic summary**: Відстежує два типи таймаутів: ACK (підтвердження біржею) та FILL (заповнення обсягу). Якщо ордер не заповнився вчасно, генерує таймаут-подію для скасування. 
- **POLLING FIX**: Має вбудований механізм проактивного REST-опитування біржі ([L307](file:///home/wekabeka/Музыка/Phenix/apps/reference/domains/execution_position/watchdog.py#L307)) на випадок зникнення WebSocket-повідомлень.
- **Dependencies**: `asyncio`, `get_clock()`.
- **Risks**:
    - `HIGH`: **RPS Throttle**. При великій кількості відкритих ордерів REST-опитування може впертися в ліміт `rps_limit` ([L90](file:///home/wekabeka/Музыка/Phenix/apps/reference/domains/execution_position/watchdog.py#L90)), що сповільнить детекцію заповнення.
- **Notes**: Використовує експоненціальний бек-офф для опитування, щоб не спамити API.

---

### [file: pending_brackets_wal.py](file:///home/wekabeka/Музыка/Phenix/apps/reference/domains/execution_position/pending_brackets_wal.py)
- **Purpose**: Забезпечення персистентності брекет-ордерів (TP/SL) для відкладеного виконання.
- **Key symbols**: `write_pending_brackets_stored`, `read_pending_brackets_from_wal`.
- **Logic summary**: Використовує JSONL WAL для збереження даних про TP/SL ордери, які мають бути виставлені після виконання лімітного входу. Це запобігає появі "голих" (naked) позицій у разі перезапуску системи між розміщенням входу та його виконанням.
- **Risks**:
    - `MED`: **WAL Corruption**. Якщо файл WAL буде пошкоджено, система може не відновити брекети, що залишить позицію без стопу.
- **Notes**: Реалізує повний цикл відтворення стану через перерахунок подій STORED та CLEARED ([L124](file:///home/wekabeka/Музыка/Phenix/apps/reference/domains/execution_position/pending_brackets_wal.py#L124)).

### [file: leverage_service.py](file:///home/wekabeka/Музыка/Phenix/apps/reference/domains/execution_position/leverage_service.py)
- **Purpose**: Сервіс для управління плечем та режимом маржі.
- **Key symbols**: `LeverageService`, `set_and_verify`.
- **Logic summary**: Забезпечує ідемпотентне встановлення плеча на біржі. Використовує вікно ідемпотентності (`idempotency_window_sec`), щоб не спамити API однаковими запитами.
- **Risks**:
    - `HIGH`: **Binance Sequence Restriction**. Режим маржі (isolated/cross) має бути встановлений ДО плеча ([L229](file:///home/wekabeka/Музыка/Phenix/apps/reference/domains/execution_position/leverage_service.py#L229)), інакше біржа поверне помилку. Сервіс це враховує.
- **Notes**: Повертає типізований `VerifyResult` для точного мапінгу причин відхилення ордерів (NRR).

### [file: idempotent_cancel.py](file:///home/wekabeka/Музыка/Phenix/apps/reference/domains/execution_position/idempotent_cancel.py)
- **Purpose**: Безпечне скасування ордерів з поглинанням помилок "Unknown Order".
- **Key symbols**: `IdempotentCancelHelper`, `cancel_order_idempotent`.
- **Logic summary**: Реалізує 3-етапний алгоритм:
    1.  **Pre-check**: `getOrder` перевірка. Якщо ордер вже термінальний (Canceled/Filled/Expired), операція вважається успішною без виклику API скасування.
    2.  **API Cancel**: Спроба скасування з детермінованим `clientOrderId`.
    3.  **-2011/ -2013 Absorption**: Поглинає помилки "Unknown Order" або "Order does not exist", вважаючи їх ідемпотентним успіхом (ордер уже відсутній на біржі).
- **Safety**: Використовує детермінований `clientOrderId` ([L69](file:///home/wekabeka/Музыка/Phenix/apps/reference/domains/execution_position/idempotent_cancel.py#L69)) на базі хешу нетіоналу та часу (Clock).
- **Notes**: Включає експоненціальний бек-офф для повторних спроб при транзитних помилках мережі.

### [file: soft_clip.py](file:///home/wekabeka/Музыка/Phenix/apps/reference/domains/execution_position/soft_clip.py)
- **Purpose**: Двигун адаптивного зниження обсягів ордерів.
- **Key symbols**: `SoftClipEngine`, `calculate_clipped_size`.
- **Logic summary**: Обчислює максимально допустимий обсяг ордера на основі поточних лімітів (Margin, Side, Directional Ratio). Якщо запитаний обсяг перевищує ліміт, він "обрізає" його до безпечного значення.
- **Notes**: Використовує суворі Pydantic моделі для конфігурації з `extra='forbid'` ([L21](file:///home/wekabeka/Музыка/Phenix/apps/reference/domains/execution_position/soft_clip.py#L21)).

### [file: drift_monitor.py](file:///home/wekabeka/Музыка/Phenix/apps/reference/domains/execution_position/drift_monitor.py)
- **Purpose**: Валідація "тіньового" режиму (Shadow Mode).
- **Key symbols**: `compute_drift`, `ConfusionMatrix`.
- **Logic summary**: Порівнює рішення FSM (DEC:OPEN) з реальними подіями (EVT:FILL) з логів/WAL. Будує матрицю помилок (TP, FP, FN, TN) та обчислює `drift_pct` (відсоток розбіжності).
- **Notes**: Використовує вікно часу `time_window_sec` для кореляції подій, які могли відбутися з невеликою затримкою.

### [file: metrics_collector.py](file:///home/wekabeka/Музыка/Phenix/apps/reference/domains/execution_position/metrics_collector.py)
- **Purpose**: Збір метрик продуктивності та успішності торгів у реальному часі.
- **Key symbols**: `MetricsCollector`, `AcceptanceRateTracker`.
- **Logic summary**: Працює в реальному часі (thread-safe), збираючи дані про Acceptance Rate, Time To Open та Rejection Patterns. Використовує `RLock` для забезпечення цілісності лічильників при високій паралельності.
- **Dependencies**: `threading`, `decimal`.

### [file: metrics_aggregator.py](file:///home/wekabeka/Музыка/Phenix/apps/reference/domains/execution_position/metrics_aggregator.py)
- **Purpose**: Агрегація та структуроване логування подій виконання (Clipping, Rejection).
- **Key symbols**: `MetricAggregator`, `StructuredMetricsLogger`, `MetricEventType`.
- **Logic summary**: Перетворює події ризику та скасування у структурований JSONL формат. Агрегує статистику по "кліпінгу" (clip amount, averages) та успішності ідемпотентних скасувань.
- **Data structures**: `dataclass ClipMetricEvent`, `RejectMetricEvent`, `CancelMetricEvent`.
- **Notes**: Дозволяє експортувати повну історію метрик у файл для compliance та подальшого аналізу.

---

## 🗺️ Event & Message Map

| Verb | Type | Source | Destination | Purpose |
| :--- | :--- | :--- | :--- | :--- |
| `CMD:OPEN` | Command | Decision Making | Execution Position | Запит на вхід у позицію |
| `DEC:OPEN` | Decision | Execution Position | Binance Adapter | Виконання входу після всіх гвардів |
| `CMD:CLOSE` | Command | Decision Making | Execution Position | Запит на закриття позиції |
| `DEC:CLOSE` | Decision | Execution Position | Binance Adapter | Виконання закриття |
| `EVT:ORDER_ACK` | Event | Binance Adapter | Execution Position | Підтвердження розміщення ордера |
| `EVT:ORDER_FILL` | Event | Binance Adapter | Execution Position | Повідомлення про виконання ордера |
| `EVT:SYMBOL_TIDY` | Event | Order Guardian | Execution Position | Сигнал про те, що по символу немає "сирітських" ордерів |

## 📐 Public Interfaces / Contracts

### 1. `CMD:OPEN` Payload
- `symbol` (str, required)
- `side` (BUY\|SELL, required)
- `qty` (str, required)
- `order_type` (LIMIT\|MARKET, required)
- `price` (str, required for LIMIT)
- `tif` (str, required for LIMIT - GTC\|GTX\|IOC\|FOK)
- `idempotent_key` (str, optional)

### 2. `DEC:OPEN` Payload
- Те саме що `CMD:OPEN`, але з нормалізованими значеннями (Decimal as string) та додаванням `valid_for_ms`.

### 3. `ExposureGuard` Interface
- `can_open(symbol, notional_usd, portfolio_state, is_flip) -> Dict`
- `reserve(key, notional_usd, ...)`
- `release(key)`

### [file: qty_normalizer.py](file:///home/wekabeka/Музыка/Phenix/apps/reference/domains/execution_position/qty_normalizer.py)
- **Purpose**: Сувора нормалізація обсягів перед відправкою на біржу.
- **Key symbols**: `normalize_qty`, `verify_ack_qty`.
- **Logic summary**: Реалізує фільтри Binance: `LOT_SIZE`, `MIN_QTY`, `MIN_NOTIONAL`. 
- **FAIL-CLOSED semantics**: Якщо обсяг після округлення стає меншим за ліміт, система відхиляє ордер (`ok=False`), замість того щоб "підтягувати" його до мінімуму (NO silent bump-ups).
- **Notes**: Повертає `QtyNormalizeResult` з детальним поясненням причини відхилення.

### [file: utils.py](file:///home/wekabeka/Музыка/Phenix/apps/reference/domains/execution_position/utils.py)
- **Purpose**: Математичні та допоміжні функції домену.
- **Key symbols**: `validate_anti_2021`, `quantize_stop_price`, `BoundedEventDeduper`.
- **Logic summary**: Містить критичну логіку `anti-2021` ([L64](file:///home/wekabeka/Музыка/Phenix/apps/reference/domains/execution_position/utils.py#L64)) — запобігання ситуації, коли біржа відкидає ордер через те, що тригер-ціна вже пройдена. Також містить `BoundedEventDeduper` для обмеженого за пам'яттю відстеження ідемпотентності.

### [file: aurora_log_adapter.py](file:///home/wekabeka/Музыка/Phenix/apps/reference/domains/execution_position/aurora_log_adapter.py)
- **Purpose**: Адаптер для структурованого логування торгових подій.
- **Logic summary**: Забезпечує запис `TRADE_INTENT_PROPOSED`, `TRADE_DECISION`, `TRADE_EXECUTION` та `GUARD_REJECTION` у спеціалізований файл логів. Допомагає у пост-мортем аналізі та налагодженні стратегій.

### [file: bootstrapping/leverage_bootstrapper.py](file:///home/wekabeka/Музыка/Phenix/apps/reference/domains/execution_position/bootstrapping/leverage_bootstrapper.py)
- **Purpose**: Стартовий сервіс для синхронізації плеча та режиму маржі.
- **Key symbols**: `LeverageBootstrapper`, `BootstrapResults`, `sync_symbol`.
- **Logic summary**: Запускається ПЕРЕД початком торгів. Опитує поточний стан символів на Binance та приводить їх у відповідність до конфігурації стратегії. Якщо синхронізація неможлива (наприклад, через наявність відкритих позицій), символ блокується.
- **Risks**:
    - `HIGH`: **Initialization Block**. Будь-яка помилка API під час бутстрапу призведе до блокування символу, що може бути неочікувано в продакшені.
- **Notes**: Обробляє специфічні помилки Binance (`MarginChangeError`, `LeverageReductionError`) для точного репортингу.

### [file: infra/order_ledger.py](file:///home/wekabeka/Музыка/Phenix/apps/reference/domains/execution_position/infra/order_ledger.py)
- **Purpose**: Репозиторій для персистентного зберігання стану ордерів (SQLite).
- **Key symbols**: `OrderLedger`, `OrderRecord`, `get_orphaned_brackets`.
- **Logic summary**: Зберігає детальну інформацію про кожен ордер, включаючи його роль (ENTRY/SL/TP) та зв'язок з батьківським ордером. Це дозволяє детектувати "оркестраційні розриви" ([L288](file:///home/wekabeka/Музыка/Phenix/apps/reference/domains/execution_position/infra/order_ledger.py#L288)), коли брекети залишаються активними без вхідного ордера.
- **Dependencies**: `sqlite3`.
- **Risks**:
    - `MED`: **Database Locking**. Використовує SQLite, що при високій інтенсивності записів може створювати затримки ("database is locked"), хоча реалізовано thread-safe пул.
- **Notes**: Підтримує автоматичне очищення старих записів (`cleanup_old_records`).

### [file: schemas/](file:///home/wekabeka/Музыка/Phenix/apps/reference/domains/execution_position/schemas/)
- **Purpose**: Строгі JSON-схеми для валідації повідомлень.
- **Files**: `cmd_open_v1.json`, `dec_open_v1.json`.
- **Logic summary**: Визначають формат `CMD:OPEN` та `DEC:OPEN`. Впроваджують умовну логіку (наприклад, `price` обов'язковий для `LIMIT` ордерів, але заборонений для `MARKET`). Гарантують відсутність сторонніх полів через `additionalProperties: false`.
- **Notes**: Ці схеми є "законом" для Decision Making домену при формуванні команд.

---

## 5) Known Architectural Limitations ("Why Chain")
Валідація концепції "Why Chain" (end-to-end tracing) виявила суттєві обмеження поточної реалізації, які унеможливлюють повний аудит подій через стандартні інструменти (`trace_id`):

1.  **Broken Correlation (RID Gap)**: `FSMCore.emit` генерує новий `rid` (UUID) для кожної події. Ланцюжок `pld.rid` → `msg.rid` розривається при перетині меж доменів (DecisionMaking → ExecutionPosition).
2.  **WAL Reading Blind Spot**: Інструменти читання WAL ігнорують top-level поле `data_ref` (де зберігається ланцюг причин у `ExecPosFSM`) і шукають його лише в `payload`.
3.  **Loss on Error**: При виникненні виключень (Exceptions) у FSM, подія `EVT:TRADE_INTENT_REJECTED` емітиться без `data_ref`, що призводить до втрати контексту помилки.
4.  **Inconsistent Storage**: `Why Chain` зберігається в різних місцях залежно від домену (`payload["why"]` в DecisionMaking vs `data_ref` в Execution), що ускладнює стандартизацію.

Детальний звіт про валідацію доступний у [WHY_CHAIN_VALIDATION.md](file:///home/wekabeka/.gemini/antigravity/brain/aa2939f4-c63b-48fe-8c16-6e9ec1e8eedf/WHY_CHAIN_VALIDATION.md).

## 🏁 Conclusion
Домен `execution_position` є зрілим та високонадійним компонентом системи Phenix. Він реалізує стратегію "Soldier" — точне виконання команд зверху з багаторівневим захистом від помилок біржі, мережі та стратегії. 

Головним напрямком подальшого розвитку має бути **деоксація `fsm.py`** та розділення його на менші, більш керовані сервіси, а також ретельне тестування нових `SoftLimit` та `LeverageService` функцій.

---

**Documentation Status**: Finalized.
