# vFoundation Engineering Blueprint — Phase 14: Monolith Decomposition (Декомпозиція Монолітів)

**Дата:** 2026-02-24
**Статус:** Draft (Ready for Execution)
**Ціль:** Розбити доменні моноліти (`decision_making.py` та `execution_position/fsm.py`, по ~4500 рядків кожен) на модулі ≤ 500 LOC та усунути виявлені cross-domain залежності. Забезпечити строгу ізоляцію контрактів відповідно до `Constitution_FSM v2.2`.

---

## 1. Проблема та Обґрунтування (The Why)

Аудит показав критичний архітектурний борг у доменному шарі:
1. **Монолітизація логіки:** `decision_making.py` (4427 LOC) та `execution_position/fsm.py` (4645 LOC) порушують правило `vFoundtation_library.md`: "LLM-Friendly Modularity: modules ≤ 500 LOC, isolated context windows".
2. **Cross-Domain Coupling (верифікований стан):**
   - `decision_making.py` має **1 підтверджений** cross-domain import: `from apps.reference.domains.alpha_search import (...)` (line 85).
   - `execution_position/fsm.py` має **0 cross-domain imports** — всі імпорти є intra-domain (з `order_guardian`, `qty_normalizer`, `pending_brackets_wal`, `leverage_bootstrapper` — це під-модулі самого `execution_position`).
   - Можливі неявні cross-domain залежності через `strategies` — потребує додаткового grep-аудиту.

> **УВАГА:** Ситуація КРАЩA ніж «спагетті-код», але монолітизація (4.5K LOC x 2) залишається основною проблемою. Cross-domain decoupling — менший scope ніж декомпозиція.

---

## 2. RoadMap: Знищення Cross-Domain Імпортів (Decoupling Phase)

**Правило:** Жоден домен у `apps/reference/domains/*` не має права використовувати `from apps.reference.domains.<ІНШИЙ_ДОМЕН> import ...`.

### Крок 2.1: Розширення існуючого Shared Types Layer

> **Факт:** `apps/reference/shared/` **вже існує** з `types.py` та `__init__.py`. Не створюємо з нуля — розширюємо.

Усі DTO (Data Transfer Objects), Enum-и та базові структури, які зараз "належать" одному домену, але використовуються іншими, повинні бути винесені в `apps/reference/shared/`.
- **Дія:** Розширити існуючий `apps/reference/shared/types.py` або створити додаткові модулі в `apps/reference/shared/`.
- **Що переносимо:**
  - `Bar` (з `feature_engineering.bar_resampler`).
  - `NormalizedRejectReasons` (з `decision_making`).
  - `FlatRegimeThresholds` (з `feature_engineering`).

### Крок 2.2: Заміна прямих викликів на Message Passing
Будь-який імпорт *Handler-а* з іншого домену (наприклад, імпорт `MeanReversionHandler` у `strategies`) є архітектурним порушенням.
- **Дія:** Замість імпортування класу і виклику методу, відправник (Source Domain) формує повідомлення і робить `FSMCore.emit("CMD:EVALUATE_MEAN_REVERSION", pld={...})`.
- **Дія:** Отримувач (Target Domain) підписується на цей `verb` через `global_dict.yaml` або `domain_dict.json` і реагує на нього в своєму Event Loop.

---

## 3. RoadMap: Декомпозиція `apps/reference/domains/decision_making` (4428 LOC)

Поточний `decision_making.py` є "Богом-об'єктом" (God Object), який робить агрегацію фічей, оцінку ризику, сайзінг (position sizing), rate-limiting (QoS) і логування.

**План розбиття (на модулі ≤ 500 LOC):**

### Модуль 1: `dm_router.py` (Entrypoint)
- **Відповідальність:** Лише підписка на FSM-події (`EVT:FEATURE_CALC`, `EVT:STRATEGY_SIGNAL`) та маршрутизація викликів до внутрішніх сервісів домену.
- **Методи для виділення:** `__init__`, метод-роутер підписника.
- **Очікуваний розмір:** ~200 LOC.

### Модуль 2: `signal_gateway.py` (Гейтвей сигналів)
- **Відповідальність:** Прийом сигналів, базова нормалізація, валідація цін (`_validate_price_input`), перевірка на дублікати.
- **Методи для виділення:** `_on_strategy_signal_gateway`, `_safe_decimal`.
- **Очікуваний розмір:** ~300 LOC.

### Модуль 3: `qos_manager.py` (Quality of Service / Rate Limiting)
- **Відповідальність:** Throttle та rate-limiting торгових рішень (захист від split-brain та spam-сигналів).
- **Методи для виділення:** `_qos_allow`, `_update_symbol_cooldown`, `_update_intent_count`, `_calculate_next_allowed_time`, `_update_qos_state`, `_handle_exposure_block`.
- **Очікуваний розмір:** ~400 LOC.

### Модуль 4: `sizing_engine.py` (Position Sizing)
- **Відповідальність:** Розрахунок розміру позиції на основі маржі, балансу, risk tolerance та обмежень біржі.
- **Методи для виділення:** Усі математичні розрахунки (`compute_notional_target`, `compute_qty`), перевірка exposure.
- **Очікуваний розмір:** ~400-500 LOC.

### Модуль 5: `risk_evaluator.py` (Оцінка Ризиків)
- **Відповідальність:** Перевірка "щитів" (Shields) — `ContextShield`, `DangerZoneShield`, `MemoryShield`. Якщо щити блокують сигнал, генерується `NormalizedRejectReason`.
- **Методи для виділення:** Логіка `aurora_scoring_kernel`, взаємодія з `AlertManager`.
- **Очікуваний розмір:** ~400 LOC.

### Модуль 6: `trade_intent_builder.py` (Формування Наміру)
- **Відповідальність:** Фінальне створення пакету (Message payload) для `EVT:TRADE_INTENT_PROPOSED` або `EVT:TRADE_INTENT_REJECTED`.
- **Методи для виділення:** Генерація why_chain, упаковка payload.
- **Очікуваний розмір:** ~200 LOC.

---

## 4. RoadMap: Декомпозиція `apps/reference/domains/execution_position/fsm.py` (4646 LOC)

`fsm.py` є обгорткою, яка прямо взаємодіє з біржею (через адаптери), мапить локальні ордери на біржові, контролює circuit breakers, та тримає in-memory стейт.

**План розбиття (на модулі ≤ 500 LOC):**

### Модуль 1: `ep_orchestrator.py` (Entrypoint)
- **Відповідальність:** Реєстрація у `vfoundation FSM`, управління життєвим циклом (setup/teardown), перехоплення команд `CMD:OPEN_POSITION`, `CMD:CLOSE_POSITION`.
- **Методи для виділення:** `ExecPosFSM.__init__`, `set_async_loop`.
- **Очікуваний розмір:** ~300 LOC.

### Модуль 2: `leverage_bootstrapper.py` (Контроль Маржі)
- **Відповідальність:** Ініціалізація та контроль "плеча" (leverage) та margin mode на біржі (isolated vs cross).
- **Методи для виділення:** `run_leverage_bootstrap`, `_collect_leverage_configs`, `validate_leverage_ssot_consistency`.
- **Очікуваний розмір:** ~250 LOC.

### Модуль 3: `order_mapper.py` (Трансляція Ордерів)
- **Відповідальність:** Маппінг внутрішніх інтенцій на API специфіку (напр. Binance), розпізнавання ціни (`_resolve_price`).
- **Методи для виділення:** `_resolve_price`, мапери payload->exchange_format.
- **Очікуваний розмір:** ~300 LOC.

### Модуль 4: `time_windows.py` (Quiet Hours & Maintenance)
- **Відповідальність:** Перевірка тих годин і maintenance windows (відключення торгівлі у заданий час).
- **Методи для виділення:** `_utc_hm`, `_in_quiet`.
- **Очікуваний розмір:** ~150 LOC.

### Модуль 5: `position_state_manager.py` (Стейт Позицій)
- **Відповідальність:** Відстеження in-flight станів (Pending Brackets WAL), Guardian tracking, idempotency tokens.
- **Методи для виділення:** `_mark_processed_event`, `_collect_guardian_symbols`.
- **Очікуваний розмір:** ~400 LOC.

### Модуль 6: `exchange_adapter_facade.py` (Фасад Адаптерів)
- **Відповідальність:** Виключно комунікація з `vfoundation.core.adapters` (BinanceAdapter та інші). Контроль Circuit Breakers на рівні обміну з біржею.
- **Методи для виділення:** Усі виклики до бірж, обробка помилок `ExchangeError` -> перехід у fail-closed `DENY` стан.
- **Очікуваний розмір:** ~500 LOC.

---

## 5. Дорожня Карта Виконання (Execution Flow)

Щоб безпечно провести розбиття (без зупинки працюючого пайплайну), ми будемо застосовувати патерн **Strangler Fig**:

1. **Етап 1: Shared Models Extraction.**
   - Розширити існуючий `apps/reference/shared/` (він вже має `types.py`).
   - Перенести `Bar`, `NormalizedRejectReasons`, `FlatRegimeThresholds` в shared.
   - Змінити імпорти у всьому проекті на нове місце (без зміни логіки).
   - *Перевірка: Всі тести зеленого кольору (gate: ≥716 passed).*
2. **Етап 2: Decision Making Decomposition.**
   - Створити папку `apps/reference/domains/decision_making/components/`.
   - Поступово переносити методи з об'єкта `DecisionMaking` у нові класи/функції. `DecisionMaking` залишається лише як "Фасад" (Facade), що викликає ці компоненти.
   - *Перевірка: Всі тести зеленого кольору (gate: ≥716 passed).*
3. **Етап 3: Execution Position Decomposition.**
   - Аналогічний підхід: створення `apps/reference/domains/execution_position/components/`.
   - Перенесення логіки з `ExecPosFSM` у стратегічні мікро-модулі.
   - *Перевірка: Всі тести зеленого кольору (gate: ≥716 passed).*
4. **Етап 4: Cross-Domain Decoupling.**
   - Видалити єдиний підтверджений cross-domain import у `decision_making.py` (→ `alpha_search`).
   - Провести повний grep-аудит: `grep -rn "from apps.reference.domains." apps/reference/domains/ | grep -v "__pycache__"` для пошуку інших неявних порушень.
   - Заміна їх на `FSMCore.emit()` та реєстрація Handler-ів.
   - *Перевірка: Всі тести зеленого кольору (gate: ≥716 passed), повна відсутність небажаних імпортів у результатах grep.*

---
**Критерій успіху:**
- Розміри файлів `decision_making.py` та `execution_position/fsm.py` < 500 LOC.
- Команда `grep -r "from apps.reference.domains.* import" apps/reference/domains/` видає 0 результатів (або лише легальні імпорти зі спільних shared-пакетів чи в межах одного й того ж самого домену).
