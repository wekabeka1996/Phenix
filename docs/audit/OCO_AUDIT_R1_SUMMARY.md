# PACK: OCO-AUDIT-R1 — Повний аудит Aggregated OCO / TP-SL Lifecycle

**Дата завершення:** 2025-11-23  
**Статус:** ✅ ЗАВЕРШЕНО  
**Час виконання:** ~3 години  
**Автор:** AI Auditor (Antigravity)

---

## 📋 Зміст

- [Огляд пакету](#огляд-пакету)
- [Основні висновки](#основні-висновки)
- [Артефакти](#артефакти)
- [Критичні знахідки](#критичні-знахідки)
- [Інваріанти](#інваріанти)
- [Ризики](#ризики)
- [Рекомендації](#рекомендації)
- [Наступні кроки](#наступні-кроки)

---

## Огляд пакету

### Мета

Виявити всі потенційно критичні місця в логіці Aggregated OCO (TP/SL) для ExecPosRuntimeV2 при:
- Зміні розміру відкритої позиції (часткові закриття, добори, реверси)
- Повному закритті позиції
- Одночасних сценаріях (новий лімітний ордер + фонове "очищення" TP/SL)

### Виконані завдання

| Завдання | Статус | Документ |
|----------|--------|----------|
| **R1-A: Архітектурна карта** | ✅ | [`OCO_AUDIT_R1A_ARCH_MAP.md`](audit/OCO_AUDIT_R1A_ARCH_MAP.md) |
| **R1-B: Синхронізація з розміром** | ✅ | [`OCO_AUDIT_R1B_SIZE_SYNC.md`](audit/OCO_AUDIT_R1B_SIZE_SYNC.md) |
| **R1-C: Race-condition аналіз** | ✅ | [`OCO_AUDIT_R1C_RACES.md`](audit/OCO_AUDIT_R1C_RACES.md) |
| **R1-D: Тестовий пакет** | ✅ | [`OCO_AUDIT_R1D_TESTPLAN.md`](audit/OCO_AUDIT_R1D_TESTPLAN.md) |

---

## Основні висновки

### ✅ Позитивні знахідки

**V2 Runtime (shadow_execpos):**
1. ✅ **Автоматична рекалькуляція** brackets при будь-якій зміні позиції
2. ✅ **Orphan detection** — виявляє "висячі" brackets при закритті позиції
3. ✅ **Throttling (3s)** — запобігає дублюванню bracket orders
4. ✅ **Snapshot freshness TTL** — відхиляє застарілі дані
5. ✅ **Guard loop (1s)** — постійний моніторинг активних позицій

**Архітектура:**
1. ✅ Логічне розділення: `BracketService` (pure computation) ⟷ `ExecutionService` (side effects)
2. ✅ Чіткі контракти між компонентами
3. ✅ XAI why-chains у всіх рішеннях

### ❌ Критичні проблеми

**Legacy FSM (fsm_manage.py):**
1. ❌ **`recalc_on_partial_close=false`** за замовчуванням → позиції без захисту після часткового закриття
2. ❌ **Немає очищення Guardian** при partial close → накопичення застарілих метаданих
3. ❌ **Відсутність throttling** → можливе дублювання brackets при швидких fill'ах
4. ❌ **Немає TTL для snapshot** → використання застарілих даних

**Обидві реалізації:**
1. ⚠️ **Bracket key = (symbol, side)** без position_id → можливі конфлікти при flip LONG→SHORT
2. ⚠️ **Watchdog poll (5s)** може пропустити швидкі транзієнтні стани

---

## Артефакти

### Документи (4 штуки, ~60 сторінок)

```
docs/audit/
├── OCO_AUDIT_R1A_ARCH_MAP.md       # Архітектурна карта, 11 компонентів, 10+ подій
├── OCO_AUDIT_R1B_SIZE_SYNC.md      # Аналіз 4 сценаріїв, 3 інваріанти, 4 gaps
├── OCO_AUDIT_R1C_RACES.md          # 4 race scenarios, 7 ризиків, sequence діаграми
└── OCO_AUDIT_R1D_TESTPLAN.md       # 48 тестів, фікстури, виконання план
```

### Діаграми створено

1. **State Machine Diagram** — 8 станів позиції/brackets
2. **Component Interaction Diagram** — V2 архітектура
3. **Sequence Diagrams** — 6 race scenarios:
   - Full close + immediate re-entry
   - Partial close + scale-in overlap
   - Position flip with stale snapshot
   - Watchdog cleanup vs new placement
   - Concurrent fills duplicate detection
   - Stale ORDERS_SNAPSHOT handling

---

## Критичні знахідки

### 🚨 P0 (Критичні — втрата даних / незахищена позиція)

| ID | Опис | Legacy | V2 | Рекомендація |
|----|------|--------|-----|--------------|
| **R1-B-GAP-1** | `recalc_on_partial_close=false` за замовчуванням | ❌ ТАК | ✅ Виправлено | Змінити default на `true` у config |
| **R1-C-RISK-1** | OrderGuardian cleanup до появи нової позиції | ❌ ТАК | ⚠️ Mitigated (TTL) | Додати TTL protection |
| **R1-C-RISK-3** | Concurrent fills → дублювання SL/TP | ❌ ТАК | ✅ Mitigated (throttling) | Enforce event serialization |

### ⚠️ P1 (Високі — тимчасова неконсистентність)

| ID | Опис | Legacy | V2 | Рекомендація |
|----|------|--------|-----|--------------|
| **R1-A-GAP-5** | `_clear_guardian_bracket_set()` НЕ викликається при partial close | ❌ ТАК | N/A | Виправити legacy |
| **R1-B-GAP-2** | Guardian metadata очищується без recalc | ❌ ТАК | N/A | Завжди викликати recalc |
| **R1-C-RISK-2** | Symbol-only cleanup key може зачепити чужу позицію | ❌ ТАК | ⚠️ Mitigated | Додати `position_id` |

### ℹ️ P2 (Середні — false positives / шум)

| ID | Опис | Legacy | V2 | Рекомендація |
|----|------|--------|-----|--------------|
| **R1-C-RISK-5** | Stale ORDERS_SNAPSHOT → false violations | ⚠️ Часто | ✅ Fixed | Force snapshot refresh |
| **R1-A-GAP-1** | Dual implementation (Legacy + V2) створює drift | ⚠️ Ongoing | N/A | Завершити міграцію на V2 |

---

## Інваріанти

### R1-B-INV-1: Bracket Quantity Constraint

**Визначення:**  
Для будь-якого `(symbol, side)` з `position_qty > 0`, сума всіх активних bracket orders (SL + TP) має задовольняти:

```
0 < sum(bracket_qty) ≤ position_qty
```

**Статус:**
- ❌ **Legacy:** Порушується при `recalc_on_partial_close=false`
- ✅ **V2:** Завжди виконується через `BracketService.evaluate()`

---

### R1-B-INV-2: Flat Position Cleanup

**Визначення:**  
Коли `position_qty ≈ 0`, всі активні SL/TP ордери мають бути скасовані або позначені як inactive протягом `N` подій.

**Параметр:** `N = 2` (одна fill подія + один orders snapshot)

**Статус:**
- ✅ **Legacy:** Виконується через `_clear_position_state()`
- ✅ **V2:** Виконується через `BracketService.evaluate()` → orphan detection

---

### R1-B-INV-3: No Hanging Brackets

**Визначення:**  
"Висячий bracket" — це bracket order, який:
- Пов'язаний зі старою/закритою позицією
- Не скасований
- Не захищений guardian metadata

**Статус:**
- ⚠️ **Legacy:** Ризик при пропущеній очищенні
- ✅ **V2:** Виконується через watchdog orphan detection + auto-cancel

---

## Ризики

### Race Conditions Catalog

| ID | Сценарій | Ймовірність | Impact | Mitigation (V2) |
|----|----------|-------------|--------|-----------------|
| **R1-C-RISK-1** | Guardian cleanup перед новою позицією | Середня | **Критичний** | TTL protection (30s) |
| **R1-C-RISK-2** | Symbol-only key при position flip | Висока | **Високий** | Side segregation |
| **R1-C-RISK-3** | Concurrent fills дублюють brackets | Висока | **Критичний** | Throttling (3s) + equivalence check |
| **R1-C-RISK-4** | Дублювання при успішних placements | Низька | **Середній** | Idempotent clientOrderId |
| **R1-C-RISK-5** | Stale snapshot → false positive | Висока | **Низький** | Force refresh + TTL |
| **R1-C-RISK-6** | Position flip без cleanup | Середня | **Високий** | Watchdog auto-cancel |
| **R1-C-RISK-7** | Watchdog + fill race | Низька | **Середній** | Throttling + suppression disabled |

---

## Рекомендації

### Негайні дії (P0) — Цей тиждень

#### Legacy (якщо ще використовується):
1. ✅ **Змінити default:** `recalc_on_partial_close: true` у всіх production configs
2. ✅ **Додати валідацію:** Після `_clear_guardian_bracket_set()` завжди викликати `_recalc_aggregated_brackets()` для `remaining > 0`
3. 📊 **Додати метрику:** `partial_close_no_recalc_count` для виявлення misconfigurations

#### V2 (поточна):
1. ✅ **Підтримувати інваріант:** `recalc_on_partial_close=true` як V2 контрактна вимога
2. 📊 **Моніторинг watchdog:** Відстежувати `ORPHAN_BRACKETS` violations для виявлення регресій

---

### Короткострокові дії (P1) — Цей місяць

1. 🧪 **Імплементувати тести:** 48 тестів з R1-D
   - Group 1: Position size changes (10 tests)
   - Group 2: Close + re-entry races (5 tests)
   - Group 3: Timeout/snapshot (6 tests)
   - Group 4: Manual cancel (4 tests)
   - Unit tests: Invariant validation (5 tests)
   - Integration tests: E2E flows (10+ tests)

2. 🔍 **Додати position_id:** Змінити bracket key з `(symbol, side)` на `(symbol, side, position_id)`

3. 📈 **Трекінг метрик:**
   - `brackets_evaluated` — скільки разів викликався evaluate()
   - `brackets_alerts` — кількість ALERT severity plans
   - `brackets_throttled` — скільки разів спрацював throttling

---

### Довгострокові дії (P2) — Наступний квартал

1. 🏗️ **Завершити міграцію:** Legacy FSM → V2 Runtime
2. 🧹 **Видалити legacy code:** Очистити `fsm_manage.py`, `agg_oco_watchdog.py` (legacy)
3. 📚 **Документувати V2 контракти:** Wiki зі spec's для всіх domain services

---

## Наступні кроки

### PACK: OCO-STABILIZE-R2 (Майбутня фаза реалізації)

На основі результатів OCO-AUDIT-R1, реалізувати:

#### Фаза 1: Критичні фікси (Тиждень 1)
- [ ] Fix R1-B-GAP-1: Set `recalc_on_partial_close=true` в production configs
- [ ] Fix R1-C-RISK-1: Add TTL protection for new brackets
- [ ] Fix R1-C-RISK-3: Enforce event serialization via async queue
- [ ] Add metrics tracking for invariant violations

#### Фаза 2: Тести (Тижні 2-3)
- [ ] Implement `test_agg_oco_size_sync.py` (10 tests)
- [ ] Implement `test_agg_oco_races_close_reopen.py` (5 tests)
- [ ] Implement `test_agg_oco_timeout_snapshot.py` (6 tests)
- [ ] Implement `test_agg_oco_manual_cancel.py` (4 tests)
- [ ] Implement `test_bracket_service_invariants.py` (5 tests)
- [ ] Implement `test_agg_oco_e2e_flows.py` (10+ tests)

#### Фаза 3: Моніторинг (Тиждень 4)
- [ ] Add Prometheus metrics for bracket lifecycle
- [ ] Create Grafana dashboard for watchdog violations
- [ ] Setup alerts for P0 invariant violations

#### Фаза 4: Production Validation (Тиждень 5-6)
- [ ] Deploy to testnet with enhanced logging
- [ ] Monitor for 2 weeks under real trading conditions
- [ ] Validate all 11 invariants in production
- [ ] Measure P99 latency for bracket operations

---

## Посилання

### Документи цього аудиту
- [R1-A: Архітектурна карта](audit/OCO_AUDIT_R1A_ARCH_MAP.md)
- [R1-B: Синхронізація розміру](audit/OCO_AUDIT_R1B_SIZE_SYNC.md)
- [R1-C: Race conditions](audit/OCO_AUDIT_R1C_RACES.md)
- [R1-D: Тестовий план](audit/OCO_AUDIT_R1D_TESTPLAN.md)

### Попередні роботи
- `INVESTIGATION_AGGREGATED_OCO.md` (2025-11-19)
- `INCIDENT_NO_TP_SL_AGG_OCO_2025-11-18.md`
- `AGG_OCO_PHASE1_SUMMARY.md`
- `EP_STAB_LIVEPOS_SL_SPAM_AUDIT.md`

### Код модулі
- `apps/reference/domains/execution_position/shadow_execpos/bracket_service.py`
- `apps/reference/domains/execution_position/shadow_execpos/runtime.py`
- `apps/reference/domains/execution_position/legacy/fsm_manage.py`
- `vfoundation/apps/reference/domains/execution_position/bracket_aggregator.py`

---

## Статистика

| Метрика | Значення |
|---------|----------|
| **Документів створено** | 4 |
| **Сторінок аналізу** | ~60 |
| **Компонентів проаналізовано** | 11 |
| **FSM подій ідентифіковано** | 10+ |
| **Інваріантів визначено** | 3 |
| **Ризиків каталогізовано** | 7 |
| **Gaps виявлено** | 11 |
| **Тестових сценаріїв запропоновано** | 48 |
| **Sequence діаграм** | 6 |
| **Час витрачено** | ~3 години |

---

**Аудит завершено:** 2025-11-23  
**Аудитор:** AI Auditor (Antigravity)  
**Статус:** ✅ ГОТОВО ДО ПЕРЕДАЧІ
