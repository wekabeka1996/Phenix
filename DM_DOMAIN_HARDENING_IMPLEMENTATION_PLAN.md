# DecisionMaking Domain Hardening — План виправлення та тестування

Дата: 2025-12-23

Ціль: зафіксувати підтверджені проблеми в домені DecisionMaking (scheduler timebase, маскування missing-data через DecisionContext defaults, фрагментація reason taxonomy, thin schemas), обґрунтувати мінімальні безпечні правки та дати чіткий план тестування.

Файли у фокусі:
- [apps/reference/domains/decision_making/deferred_scheduler.py](apps/reference/domains/decision_making/deferred_scheduler.py)
- [apps/reference/domains/decision_making/decision_context.py](apps/reference/domains/decision_making/decision_context.py)
- [apps/reference/domains/decision_making/normalized_reject_reasons.py](apps/reference/domains/decision_making/normalized_reject_reasons.py)
- [apps/reference/domains/decision_making/sizing_margin_first.py](apps/reference/domains/decision_making/sizing_margin_first.py)
- [apps/reference/domains/decision_making/decision_making.py](apps/reference/domains/decision_making/decision_making.py)
- [apps/reference/domains/decision_making/schemas.py](apps/reference/domains/decision_making/schemas.py)

---

## 0) Evidence (що підтверджено кодом)

### P0-1: Scheduler time base mismatch (epoch vs monotonic)
- Контракт параметра `when_ts_ms` документовано як Unix epoch milliseconds.
- Реалізація рахує “now” через `loop.time()` (монотонний час), тобто порівнює **epoch-ms** з **monotonic-ms**.
- Наслідок: `delay` може стати величезним (або близьким до 0 не там де треба), і retry може “поїхати” на години/дні або практично ніколи не спрацювати.

Доказ:
- Docstring/args: [deferred_scheduler.py](apps/reference/domains/decision_making/deferred_scheduler.py#L27-L35)
- `now_ms = int(loop.time() * 1000)`: [deferred_scheduler.py](apps/reference/domains/decision_making/deferred_scheduler.py#L43)

### P0-2: DecisionContext defaults маскують missing features як нейтраль
- Частина критичних полів має дефолти “нейтральності” (`0.5`) або “0”, що з погляду downstream-логіки виглядає як валідний сигнал, хоча даних може не бути.
- Приклад: `ema_bias=0.5`, `volatility_state=0.5`, `depth_imbalance=0.5`.

Доказ:
- `ema_bias: Decimal = Decimal("0.5")`: [decision_context.py](apps/reference/domains/decision_making/decision_context.py#L85)
- `volatility_state: Decimal = Decimal("0.5")`: [decision_context.py](apps/reference/domains/decision_making/decision_context.py#L171)
- `depth_imbalance: Decimal = Decimal("0.5")`: [decision_context.py](apps/reference/domains/decision_making/decision_context.py#L213)

### P0-3: Фрагментація reason taxonomy (NRR vs ad-hoc strings)
- Є “офіційний” каталог `NormalizedRejectReasons` з `NRR-001..NRR-024` та regex-normalize для raw reasons.
- Паралельно в логіці decision-making зустрічаються причини, які виглядають як NRR, але не є частиною `NormalizedRejectReasons` (наприклад `NRR-DATA-NOT-READY`, `NRR-ARMING-*`, `NRR-REGIME-MISSING`).
- Додатково sizing повертає **не-NRR** строки (`MIN_QTY`, `MIN_NOTIONAL`, `ZERO_QUANTITY`) — ці коди не нормалізуються в NRR без окремого mapping.

Доказ:
- Наявний enum/normalize: [normalized_reject_reasons.py](apps/reference/domains/decision_making/normalized_reject_reasons.py#L15-L160)
- Ad-hoc reasons у decision_making:
  - `NRR-DATA-NOT-READY`: [decision_making.py](apps/reference/domains/decision_making/decision_making.py#L368-L380)
  - `NRR-ARMING-*`: [decision_making.py](apps/reference/domains/decision_making/decision_making.py#L1830)
  - `NRR-REGIME-MISSING`: [decision_making.py](apps/reference/domains/decision_making/decision_making.py#L1876)
- Sizing reasons:
  - `MIN_QTY`/`MIN_NOTIONAL`: [sizing_margin_first.py](apps/reference/domains/decision_making/sizing_margin_first.py#L61-L72)

### P0-4: “Fail-open guard on OrderIndex” — спростовано (для поточного коду)
- При збої order index guard відбувається fail-closed з reason `NRR-ORDER-INDEX-FAIL`.

Доказ:
- [decision_making.py](apps/reference/domains/decision_making/decision_making.py#L3036)

### P1-1: Thin schema (PortfolioStatePayload мінімальний)
- `PortfolioStatePayload` зараз містить лише `positions`.

Доказ:
- [schemas.py](apps/reference/domains/decision_making/schemas.py#L21-L22)

---

## 1) Мета та інваріанти

### I-A: Scheduler correctness (timebase contract)
- Планувальник має працювати детерміновано: `when_ts_ms` → чіткий `delay`, незалежно від event loop.
- Заборонено змішувати epoch-time та monotonic-time.

### I-B: No “silent neutral” при відсутніх даних
- DecisionMaking має мати спосіб відрізнити:
  - “фіча реально нейтральна”
  - “фічі нема, ми поставили дефолт”

### I-C: Єдиний SSOT для reject reason (NRR)
- Всі reject/defer причини повинні мати уніфікований код (NRR) + людський опис.
- Ad-hoc строки допускаються лише як `raw_reason`/`details`, але не як primary key для аналітики.

---

## 2) Non-goals (щоб не роздувати scope)

- Не міняємо стратегії та їх математику.
- Не робимо редизайн подій/шин.
- Не додаємо нові дашборди/метрики поза мінімально потрібними для форензики.

---

## 3) Рішення по неоднозначностях (фіксуємо наперед)

### 3.1 Вибір контракту часу для scheduler
Варіант A (рекомендований, мінімальний): **залишаємо `when_ts_ms` як epoch-ms**, а `now_ms` беремо з epoch (`time.time()`), не з `loop.time()`.
- Плюси: контракт вже задокументований як epoch-ms.
- Мінуси: потрібно імпортувати `time`, і unit-тести мають стабілізувати “now”.

Варіант B (альтернатива): міняємо контракт на monotonic-ms всюди (більш інвазивно) — **не робимо** в рамках цього плану.

### 3.2 Таксономія reason
- `NormalizedRejectReasons` лишається SSOT для NRR-кодів.
- Всі причини типу `MIN_NOTIONAL`/`MIN_QTY` мають мапитись у відповідні NRR (наприклад `NRR-006 QUANTITY_TOO_SMALL`), а “деталі” йдуть окремим полем.

### 3.3 Missing-data в DecisionContext
- Не ламаємо поточні dataclass-дефолти одразу.
- Додаємо **окремий сигнал якості** (наприклад `missing_fields` або `quality_flags`) та мінімальний gate в DecisionMaking (конфігурований fail-closed).

---

## 4) План змін (Implementation)

### P0 — обовʼязково (hard correctness)

#### P0-1: Fix DeferredIntentScheduler timebase
Файл: [apps/reference/domains/decision_making/deferred_scheduler.py](apps/reference/domains/decision_making/deferred_scheduler.py)
- Замінити `now_ms = int(loop.time() * 1000)` на epoch-ms (`int(time.time() * 1000)`).
- Додати мінімальний захист від “when_ts_ms в минулому”: `delay = max(0.0, ...)` з коректним epoch now.
- Лог: якщо `when_ts_ms` виглядає як monotonic (надто малий/надто великий) — warning (best-effort), але без крашу.

#### P0-2: Normalize sizing reasons → NRR
Файл: [apps/reference/domains/decision_making/normalized_reject_reasons.py](apps/reference/domains/decision_making/normalized_reject_reasons.py)
- Додати явне мапування коротких причин з sizing (`MIN_QTY`, `MIN_NOTIONAL`, `ZERO_QUANTITY`) у NRR:
  - `ZERO_QUANTITY` → `NRR-002 INVALID_ORDER_PARAMS` (або окремий новий NRR, якщо хочеш; але мінімально — NRR-002)
  - `MIN_QTY` → `NRR-006 QUANTITY_TOO_SMALL`
  - `MIN_NOTIONAL` → `NRR-006 QUANTITY_TOO_SMALL` (або `NRR-002`, але краще NRR-006 як “too small”)
- `normalize()` має вміти обробити ці “коди” як raw_reason.

> Примітка: тут важливо не зламати існуючу regex-логіку. Робимо early-return mapping перед regex.

### P1 — якість/форензика (але без сильного рефактору)

#### P1-1: DecisionContext quality сигнал (missing fields)
Файл: [apps/reference/domains/decision_making/decision_context.py](apps/reference/domains/decision_making/decision_context.py)
- Додати механізм, який при побудові view-ів фіксує, які поля були “missing/invalid” і були замінені дефолтом.
- Мінімальний API варіант:
  - `DecisionContext.missing_fields: set[str]` або `dict[str, str]` (field → причина: missing/invalid)

#### P1-2: DecisionMaking gate на degraded context (конфігурований)
Файл: [apps/reference/domains/decision_making/decision_making.py](apps/reference/domains/decision_making/decision_making.py)
- Якщо `DecisionContext.missing_fields` перетинає критичний список (конфіг), то fail-closed:
  - emit `EVT:INTENT_DEFERRED` або `EVT:INTENT_DROPPED` з reason, який нормалізується у NRR (наприклад `NRR-DATA-NOT-READY` → треба вирішити уніфікацію або перевести на `NRR-999` + details).

> Тут треба уважно: ми не хочемо “вбити торгівлю” через вторинні фічі. Критичний список має бути коротким.

### P2 — thin schema (опційно, якщо хочеш)

#### P2-1: Розширити PortfolioStatePayload мінімально для форензики
Файл: [apps/reference/domains/decision_making/schemas.py](apps/reference/domains/decision_making/schemas.py)
- Додати поля (без ламання сумісності):
  - `ts_ms: int | None = None`
  - `equity_usdt: Decimal | None = None`
  - `available_usdt: Decimal | None = None`
  - `schema_version: int = 1`

> Це не “повний портфель”, але вже зменшує кількість ситуацій “позиції є, але чому так — невідомо”.

---

## 5) План тестування

### 5.1 Unit tests (обовʼязково)

#### UT-1: Scheduler uses epoch time
- Arrange: зафіксувати `time.time()` через monkeypatch.
- Act: `schedule_once(symbol, when_ts_ms, cb)`.
- Assert: `loop.call_later()` отримує `delay`, який відповідає `when_ts_ms - now_epoch_ms`.

Файл (пропозиція): `tests/domains/decision_making/test_deferred_intent_scheduler_timebase_v1.py`

#### UT-2: Scheduler deduplication still works
- Arrange: двічі викликати `schedule_once()` для одного символа.
- Assert: другий виклик не створює новий handle.

#### UT-3: Normalize sizing codes
- Arrange/Act: `NormalizedRejectReasons.normalize("MIN_QTY")`, `...normalize("MIN_NOTIONAL")`, `...normalize("ZERO_QUANTITY")`.
- Assert: повертаються очікувані NRR.

Файл (пропозиція): `tests/domains/decision_making/test_normalized_reject_reasons_sizing_mapping_v1.py`

### 5.2 Integration / contract tests (мінімум)

#### IT-1: DecisionMaking defer reasons are NRR-normalizable
- Arrange: згенерувати кейс defer через sizing (MIN_QTY/MIN_NOTIONAL) або data-not-ready.
- Assert: у події/логу reason можна нормалізувати у валідний NRR (`NormalizedRejectReasons.normalize(...) != NRR-999`).

Файл (пропозиція): `tests/integration/test_decisionmaking_reason_taxonomy_contract_v1.py`

### 5.3 Regression tests (якщо робимо P1)

#### RT-1: Missing critical features triggers fail-closed
- Arrange: payload features без ключового поля (наприклад тренд/волатильність — залежить від обраного критичного списку).
- Assert: intent не переходить у open, а deferred/dropped з контрольованим reason.

---

## 6) Definition of Done (DoD)

- DoD-1: Scheduler рахує `delay` коректно для epoch-ms (unit).
- DoD-2: Deduplication по symbol збережена (unit).
- DoD-3: `MIN_QTY/MIN_NOTIONAL/ZERO_QUANTITY` нормалізуються в NRR (unit).
- DoD-4: Мінімум один інтеграційний тест гарантує “reasons SSOT” (integration).
- DoD-5 (якщо робимо P1): missing critical fields → deterministic fail-closed (regression).

---

## 7) Rollout / перевірка (smoke)

1) Запустити `pytest` на доменних/інтеграційних тестах.
2) На стенді зімітувати QoS defer (cooldown) і перевірити, що deferred retry спрацьовує “вчасно”, а не через години.
3) Зімітувати sizing reject і перевірити, що reason в логах/подіях лягає у NRR-аналітику.

---

## 8) Ризики та помʼякшення

- Ризик: зміна timebase може змінити фактичний момент retry (але це і є виправлення помилки).
- Ризик: агресивний missing-data gate може “задушити” торгівлю.
  - Мітігація: робити gate лише на короткий whitelist критичних полів, за конфігом, з прозорим reason.
- Ризик: mapping `MIN_NOTIONAL` → `NRR-006` може бути семантично грубим.
  - Мітігація: зберігати `raw_reason`/details поряд, не втрачаючи точність.

---

## 9) Відкриті питання (потребують твого рішення)

1) Який точний NRR для `ZERO_QUANTITY` і `MIN_NOTIONAL`?
   - Мінімально: `NRR-002` для `ZERO_QUANTITY`, `NRR-006` для `MIN_*`.
2) Якщо робимо P1 gate: які поля “критичні” (і чи це per-strategy)?
3) Для thin schema (P2): чи ок збільшити payload (сумісно) чи залишити як є?

---

## 10) Статус реалізації (2025-12-23)

- P0-1 (scheduler epoch-ms timebase): ✅ реалізовано + unit tests.
- P0-2 (sizing short-codes → NRR): ✅ реалізовано + unit tests.
- P1-1 (DecisionContext missing/invalid tracking): ✅ реалізовано + unit tests.
- P1-2 (degraded DecisionContext gate): ✅ реалізовано як opt-in (за замовчуванням вимкнено) + unit tests.
  - Увімкнення (канонічний конфіг):
    - `domains.decision_making.fail_closed_on_degraded_context: true`
    - (опційно) `domains.decision_making.degraded_context_critical_keys: ["price", ...]`
    - (опційно, per-strategy) `domains.decision_making.degraded_context_critical_keys_by_strategy: {"stratX": ["ema_bias", ...]}`
- IT-1 (integration contract: defer reasons нормалізуються в NRR): ✅ додано integration test.
- P2-1 (PortfolioStatePayload thin schema expansion): ✅ реалізовано (backward-compatible) + unit tests.
