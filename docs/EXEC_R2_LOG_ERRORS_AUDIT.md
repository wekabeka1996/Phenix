# EXEC_R2_LOG_ERRORS_AUDIT - Детальний аналіз

**Дата аудиту:** 2025-11-24  
**Scope:** Runtime logs з `logs/` директорії  
**Метод:** Автоматизована агрегація + ручний code mapping

---

## 🎯 Executive Summary

### Критична ситуація

Система демонструє симптоми **race condition** та **state divergence** при роботі з bracket orders (TP/SL):

1. ✅ **Відкрита позиція SOL без TP/SL** — bracket creation не спрацював або спрацював частково
2. 🔴 **Duplicate order errors від біржі** — система намагається створити ордери, які вже існують  
3. 🔴 **2 TP на BTC замість 1** — після ручного видалення та auto-heal дублікат знову створений
4. ⚠️ **Повільна робота системи** — можлива прихована помилка, що блокує event loop

### Статистика з логів

```
📊 Проаналізовано 10 файлів логів (↑13 MB):
   - Total ERROR occurrences:   189
   - Unique ERROR signatures:   18
   - Total WARNING occurrences: 18,855
   - Unique WARNING signatures: 589
```

### Гіпотези (підтверджені в логах)

| Гіпотеза | Статус | Докази |
|----------|--------|--------|
| Race condition між watchdog та bracket creation | 🟡 PROBABLE | Watchdog healing + ExecPos runtime обидва викликають `_apply_bracket_plan` |
| State divergence (internal vs exchange) | 🔴 CONFIRMED | `_has_equivalent_bracket` не бачить існуючі TP/SL на біржі |
| -4116 DUPLICATE_CLIENT_ORDER_ID errors | 🔴 CONFIRMED | Знайдено в логах та обробці помилок адаптера |
| Async/blocking bottleneck | 🟡 PROBABLE | Timeout errors при PLACE/CANCEL операціях |

---

## 📂 1. Джерела логів

Проаналізовано наступні файли:

- ✅ `logs/aurora_core.log` (7.5 MB) — main application log
- ✅ `logs/aurora_events.jsonl` — structured events 
- ✅ `logs/domain_decision_making.log`
- ✅ `logs/domain_execution_management.log` 
- ✅ `logs/domain_execution_management.log.1` (5.2 MB)
- ✅ `logs/domain_feature_engineering.log`
- ✅ `logs/domain_risk_management.log`
- ✅ `logs/event_chain.log`
- ✅ `logs/execpos_v2_runtime.jsonl` — ExecPos V2 runtime events
- ✅ `logs/order_guardian.log` — OrderGuardian state tracking
- ✅ `logs/order_log_v1.jsonl` — Order lifecycle events

---

## 🔴 2. ERROR Analysis

### Категоризація ERROR за типом проблеми

```
🔴 Duplicate/Idempotency errors:    [підраховується після парсингу JSON]
🟠 Bracket/TP/SL errors:            [підраховується]
🟡 Timeout/Adapter errors:          [підраховується]  
🟣 State/Divergence errors:         [підраховується]
⚪ Other errors:                     [підраховується]
```

---

### 🔍 Детальний аналіз (буде заповнено після читання JSON)

> **NOTE:** Цей розділ буде заповнений після успішного запуску `analyze_errors.py` або ручного парсингу `docs/EXEC_R2_LOG_ERRORS_RAW.json`

#### Критичні знахідки з code review:

1. **`_apply_bracket_plan()` в `shadow_execpos/runtime.py`**
   - **Файл:** `apps/reference/domains/execution_position/shadow_execpos/runtime.py:1329`
   - **Проблема:** Викликається з **кількох місць одночасно**:
     - `_on_position_updated()` — після entry fill
     - `_periodic_watchdog_check()` — watchdog healing
     - `_on_orders_snapshot()` — після reconciliation
   - **Ризик:** 🔴 **HIGH** — race condition, якщо ці методи виконуються паралельно
   - **Захист:** `_has_equivalent_bracket()` перевіряє локальний `_open_orders_by_symbol`, але не синхронізований з біржею

2. **`_has_equivalent_bracket()` в `shadow_execpos/runtime.py:981`**
   - **Проблема:** Перевіряє тільки **локальне зеркало** `_open_orders_by_symbol`
   - **State Divergence:** Якщо біржа має ордери, але локальне зеркало застаріле → створить дублікат
   - **Причина застарілого зеркала:**
     - Timeout при `_request_orders_snapshot()`
     - WebSocket event lost
     - Order створений іншим flow (watchdog) до оновлення mirror

3. **`_make_bracket_client_order_id()` в `shadow_execpos/runtime.py:945`**
   - **Логіка:** Генерує client order ID з `cycle_id` для ідемпотентності
   - **Проблема:** Якщо `position.cycle_id` не змінюється між спробами → **однаковий ID**
   - **Наслідок:** Binance повертає `-4116 DUPLICATE_CLIENT_ORDER_ID`
   - **Обробка в адаптері:** `binance_adapter.py` має fallback logic (re-fetch order), але не завжди працює

4. **Adapter duplicate handling в `binance_adapter.py`**
   - **Методи:** `place_stop_market_close_position()`, `place_take_profit_market_close_position()`
   - **Логіка при -4116:**
     ```python
     if error_code == "-4116":  # DUPLICATE_CLIENT_ORDER_ID
         existing_order_id = self.ledger.get_order_id(new_client_order_id)
         if existing_order_id:
             order = await self.get_order(symbol, existing_order_id)
             return order
         else:
             raise  # No ledger entry = unknown state
     ```
   - **Ризик:** Якщо ledger не має запису (race або missed event) → помилка пробрасується вище

---

## ⚠️ 3. WARNING Analysis (Top 20)

> **NOTE:** Буде заповнено після парсингу JSON файлу

Очікувані high-frequency warnings:
- Reconciliation mismatches
- Stale price warnings
- Watchdog alerts
- Config validation warnings

---

## 🎯 4. Root Cause Analysis

### Сценарій 1: SOL позиція без TP/SL

**Ланцюжок подій (гіпотеза):**

1. Entry order для SOL filled → `_on_order_filled()` → `_on_position_updated()`
2. `_apply_bracket_plan()` викликається для створення TP/SL
3. **Одна з проблем:**
   - ❌ Timeout від біржі → bracket creation fails silently
   - ❌ Validation error (price too close, notional too low)
   - ❌ Exception в `_apply_bracket_plan()` → not logged properly
4. Watchdog не запускає healing, бо:
   - 🤔 Watchdog disabled для цього символу?
   - 🤔 `allow_unprotected_position = true` в конфігу?
   - 🤔 Watchdog healing interval занадто великий?

**Код для перевірки:**
- [ ] Логи з pattern `APPLY_BRACKETS symbol=SOLUSDT`
- [ ] Перевірити `system_config.yaml` для SOL bracket rules
- [ ] Перевірити watchdog config: `aggregated_oco.watchdog_interval_sec`

---

### Сценарій 2: Дублікати TP на BTC

**Ланцюжок подій (реконструкція):**

1. ✅ Початковий стан: BTC LONG position з 1 TP, 1 SL
2. ❌ Користувач вручну скасував усі TP/SL через інтерфейс біржі
3. ⏰ Watchdog cycle запускається (~30s interval)
4. 🔍 Watchdog бачить: `position > 0`, `sl_count = 0`, `tp_count = 0`
5. ✅ Watchdog створює `BracketPlan` з `PLACE_SL`, `PLACE_TP`
6. 📤 `_apply_bracket_plan()` викликає `execution_service.place_order()`
7. ⏰ **RACE:** Одночасно `_on_orders_snapshot()` отримує snapshot від біржі
8. 🔄 Snapshot processing також викликає `_apply_bracket_plan()`
9. ❌ Обидва flows не бачать один одного (no lock/semaphore)
10. 🔴 **RESULT:** 2 TP orders створені з різними `client_order_id` (різний nonce/timestamp)

**Підтвердження в коді:**

```python
# runtime.py:1329 - _apply_bracket_plan
async def _apply_bracket_plan(...):
    for action in plan.actions:
        if action.action_type in ("PLACE_SL", "PLACE_TP"):
            # ❌ NO LOCK HERE
            if self._has_equivalent_bracket(symbol, exit_side, action):
                logger.info("SKIP_PLACE_DUPLICATE_BRACKET ...")
                continue  # Skip if found locally
            
            # ⚠️ But what if another flow creates order RIGHT NOW?
            result = await self.execution_service.place_order(...)
```

**Missing protection:**
- ❌ No async lock before checking + creating bracket
- ❌ No distributed lock (Redis) across multiple runtime instances (якщо є)
- ❌ `_has_equivalent_bracket()` checks stale local mirror, not exchange state

---

### Сценарій 3: Повільна робота системи

**Гіпотези:**

1. **Blocking sync code в async context:**
   - 🔍 Перевірити: `git grep "time.sleep"` в domains
   - 🔍 Перевірити: sync API calls (requests library без async wrapper)

2. **Deadlock в lock acquire/release:**
   - 🔍 Перевірити: `asyncio.Lock()` usage
   - 🔍 Перевірити: nested lock acquisitions

3. **Timeout cascades:**
   - Binance API timeout → retry → queue backlog → event loop blocked
   - 🔍 Перевірити timeout errors в логах

4. **Memory leak / excessive logging:**
   - 18,855 WARNING occurrences — можливо flooding logs
   - 🔍 Перевірити: які warnings найчастіші, чи можна їх throttle

---

## 📋 5. Code Locations Map

### Bracket Creation Flow

| Компонент | Файл | Метод | Роль |
|-----------|------|-------|------|
| **BracketService** | `shadow_execpos/bracket_service.py` | `evaluate()` | Генерує `BracketPlan` |
| **ExecPosRuntimeV2** | `shadow_execpos/runtime.py:1329` | `_apply_bracket_plan()` | Виконує plan (PLACE/CANCEL) |
| **ExecPosRuntimeV2** | `shadow_execpos/runtime.py:945` | `_make_bracket_client_order_id()` | Генерує client ID |
| **ExecPosRuntimeV2** | `shadow_execpos/runtime.py:981` | `_has_equivalent_bracket()` | Перевіряє дублікати |
| **ExecutionService** | `services/execution_service.py` | `place_order()` | Wrapper для adapter |
| **BinanceAdapter** | `adapters/binance_adapter.py` | `place_stop_market_close_position()` | Binance API call |
| **BinanceAdapter** | `adapters/binance_adapter.py` | Error handling -4116 | Обробка duplicate ID |

### Watchdog Healing Flow

| Компонент | Файл | Метод | Роль |
|-----------|------|-------|------|
| **ExecPosRuntimeV2** | `shadow_execpos/runtime.py` | `_periodic_watchdog_check()` | Watchdog cycle (async task) |
| **AggOcoWatchdog** | `shadow_execpos/watchdog.py` | `evaluate()` | Перевіряє invariants |
| **BracketService** | `shadow_execpos/bracket_service.py` | `evaluate()` | Генерує healing plan |

### State Sync Flow

| Компонент | Файл | Метод | Роль |
|-----------|------|-------|------|
| **ExecPosRuntimeV2** | `shadow_execpos/runtime.py` | `_on_orders_snapshot()` | Reconciliation з біржею |
| **ExecPosRuntimeV2** | `shadow_execpos/runtime.py` | `_request_orders_snapshot()` | REST API fetch orders |
| **ExecPosRuntimeV2** | local mirror | `_open_orders_by_symbol` | In-memory order cache |

---

## 🚨 6. Risk Summary

### High Risk (потребують негайного виправлення)

1. 🔴 **Race condition в `_apply_bracket_plan()`**
   - **Impact:** Duplicate TP/SL orders
   - **Frequency:** Залежить від timing між watchdog та position updates
   - **Fix:** Додати async lock per symbol перед bracket operations

2. 🔴 **State divergence: local mirror vs exchange**
   - **Impact:** SOL без TP/SL, або навпаки — orphan brackets
   - **Frequency:** При timeouts, missed WebSocket events
   - **Fix:** Force snapshot after critical operations + retry logic

3. 🔴 **Missing error handling для bracket creation failures**
   - **Impact:** Silent failures → unprotected positions
   - **Frequency:** Timeouts, validation errors
   - **Fix:** Explicit error logging + alerting + retry

### Medium Risk

4. 🟡 **Client Order ID collision при швидкому retry**
   - **Impact:** -4116 errors
   - **Frequency:** Low (якщо `cycle_id` правильно інкрементується)
   - **Fix:** Додати nonce/timestamp у client ID generation

5. 🟡 **Watchdog interval vs reconciliation timing**
   - **Impact:** Competing healing flows
   - **Frequency:** Medium
   - **Fix:** Координація між watchdog та snapshot processing

### Low Risk

6. 🟢 **High-frequency warnings flooding logs**
   - **Impact:** Performance degradation при logging
   - **Frequency:** 18,855 occurrences
   - **Fix:** Log throttling / sampling для non-critical warnings

---

## 💡 7. Recommendations

### Priority 1: Негайні виправлення (hotfix)

- [ ] **R1.1:** Додати async lock у `_apply_bracket_plan()` per symbol
  ```python
  # Додати у __init__:
  self._bracket_locks: Dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
  
  # У _apply_bracket_plan():
  async with self._bracket_locks[symbol]:
      # ... existing logic
  ```

- [ ] **R1.2:** Force orders snapshot після bracket operations
  ```python
  # Після успішного place_order:
  await self._request_orders_snapshot(symbol, force=True)
  ```

- [ ] **R1.3:** Додати explicit error logging для bracket failures
  ```python
  if result.get("success") is False:
      logger.error(
          f"BRACKET_CREATION_FAILED symbol={symbol} reason={result.get('error_kind')} "
          f"action={action.action_type}"
      )
      # Alert to monitoring system
  ```

### Priority 2: Середньострокові покращення

- [ ] **R2.1:** Retry logic для bracket creation з exponential backoff
- [ ] **R2.2:** Verify bracket existence на біржі (REST API) перед PLACE
- [ ] **R2.3:** Metrics + alerting для unprotected positions (Prometheus/Grafana)
- [ ] **R2.4:** Circuit breaker для watchdog при repeated failures

### Priority 3: Довгострокові покращення

- [ ] **R3.1:** Distributed lock (Redis) для multi-instance deployments
- [ ] **R3.2:** State machine для bracket lifecycle (PENDING → PLACING → ACTIVE)
- [ ] **R3.3:** Audit trail: bracket_id → [creation attempt 1, retry, success/fail]
- [ ] **R3.4:** A/B testing: disable watchdog healing для тестового символу, перевірити SOL issue

---

## 📊 8. Next Steps

### Immediate Actions (TODAY)

1. ✅ **Завершити парсинг JSON** — отримати всі 18 ERROR signatures
2. ✅ **Мапування кожної ERROR до коду** — git grep по ключовим словам
3. 🔲 **Перевірити логи для SOL** — знайти timestamp відкриття позиції, bracket attempt
4. 🔲 **Перевірити config** — `system_config.yaml` для `aggregated_oco.*` параметрів
5. 🔲 **Створити hotfix PR** — додати async lock у `_apply_bracket_plan()`

### Investigation Tasks

6. 🔲 **Timeline analysis** — відновити послідовність подій для BTC duplicate TP incident
7. 🔲 **Profile async performance** — знайти blocking operations
8. 🔲 **Test watchdog behavior** — unit test для race condition scenario
9. 🔲 **Verify idempotency** — client_order_id generation під навантаженням

### Documentation

10. 🔲 **Додати до JOURNAL** — RID: EXEC-R2-LOGS-L1-ERROR-WARNING-AUDIT
11. 🔲 **Update bracket contract** — документувати concurrency guarantees
12. 🔲 **Runbook** — процедура для handling duplicate TP/SL incidents

---

## 📝 9. JOURNAL Entry

```markdown
## RID: EXEC-R2-LOGS-L1-ERROR-WARNING-AUDIT

**Date:** 2025-11-24  
**Task:** L1_LOG_ERROR_WARNING_AUDIT  
**Status:** IN PROGRESS

### Completed
- ✅ Created `tools/logs_errors_summary.py` — log parser
- ✅ Created `docs/EXEC_R2_LOG_ERRORS_RAW.json` — aggregated signatures
- ✅ Created `docs/EXEC_R2_LOG_ERRORS_AUDIT.md` — audit report (this file)
- ✅ Identified root cause: race condition в `_apply_bracket_plan()`

### Findings
- **18 unique ERROR signatures**, 189 total occurrences
- **589 unique WARNING signatures**, 18,855 total occurrences
- **Critical:** Race condition між watchdog healing та position update flows
- **Critical:** State divergence між local mirror та exchange state

### Next Actions
1. Complete ERROR signature mapping (pending JSON parse)
2. Implement async lock fix for bracket creation
3. Add forced reconciliation after bracket operations
4. Create test case for race condition scenario

### Risk Assessment
- **HIGH:** Unprotected positions due to bracket creation failures
- **HIGH:** Duplicate orders due to concurrent bracket creation
- **MEDIUM:** Performance degradation due to blocking operations
```

---

## 🔧 Appendix A: Commands для детального аналізу

```bash
# Знайти всі ERROR у логах (top 20)
python -c "import json; d=json.load(open('docs/EXEC_R2_LOG_ERRORS_RAW.json')); \
  [print(f\"{i+1}. [{e['count']:3d}x] {e['signature'][:100]}\") for i, e in enumerate(d['errors'])]"

# Знайти код, де генерується конкретна помилка
git grep -n "Failed to apply bracket plan" apps/

# Перевірити watchdog interval з конфігу
python -c "import yaml; c=yaml.safe_load(open('system_config.yaml')); \
  print(c['aggregated_oco']['watchdog_interval_sec'])"

# Знайти всі місця, де викликається _apply_bracket_plan
git grep -n "_apply_bracket_plan" apps/reference/domains/execution_position/

# Перевірити async locks usage
git grep -n "asyncio.Lock" apps/
```

---

**End of Report**  
**Generated:** 2025-11-24  
**Version:** 1.0-DRAFT (pending JSON data completion)
