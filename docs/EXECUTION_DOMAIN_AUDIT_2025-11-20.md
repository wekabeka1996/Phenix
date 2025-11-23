# Execution Position Domain Audit
**Date:** 2025-11-20
**Status:** DRAFT
**Auditor:** Antigravity

## 1. Executive Summary
This document presents the findings of a comprehensive audit of the `execution_position` domain. The audit focused on identifying logical errors, hidden failure modes, technical debt, and concurrency pitfalls.

**Overall Assessment:**
The domain is well-structured around FSM principles and includes robust error handling (circuit breakers, backoff). However, several **critical** issues were identified that could lead to production failures, particularly regarding hardcoded values and race conditions during position closure.

**Key Statistics:**
- **Critical Issues:** 7 (4 нові виявлені при повторній перевірці)
- **Major Issues:** 4
- **Minor Issues:** 5
- **Async/Concurrency Risks:** High

## 2. Domain Map
The execution domain is orchestrated by `ExecPosFSM`, which delegates to specialized sub-FSMs:

*   **`ExecPosFSM`**: Central coordinator. Manages `OpenFlowFSM`, `ManageFlowFSM`, `CloseFlowFSM`.
*   **`OpenFlowFSM`**: Handles `CMD:OPEN`. Guards: MinNotional, Cooldown, Idempotency.
*   **`ManageFlowFSM`**: Manages active positions. Handles TP/SL placement (Legacy & Aggregated OCO).
*   **`CloseFlowFSM`**: Handles `CMD:CLOSE` and auto-close rules (MaxHoldTime).
*   **`OrderGuardian`**: SSOT for bracket lifecycle. Wraps `ServicesGuardian`.
*   **`OrderTimeoutWatchdog`**: Proactive polling for order timeouts (ACK/FILL).

## 3. Critical Findings (High Priority)

### 3.1. Hardcoded Tick Size in Bracket Placement (ПІДТВЕРДЖЕНО + ГІРШЕ)
**Location:** `apps/reference/domains/execution_position/fsm_manage.py:727, 1308`
**Issue:**
```python
# Рядок 727 (legacy path):
tick_size = Decimal("0.01")

# Рядок 1308 (aggregated path):
tick_size = self._lookup_instrument_value("tick_size") or Decimal("0.01")
```
**Impact:**
🔴 **КРИТИЧНО:** Хардкод `0.01` присутній у **ДВОХ різних методах**:
- `_place_brackets_legacy()` - повністю хардкод
- Aggregated path - fallback до `0.01` якщо конфіг повертає `None`

Це означає:
- Дублювання логіки → подвійна підтримка
- Навіть якщо конфіг налаштовано, але він повертає `None`, отримаємо `0.01`
- Orders будуть відхилені для SHIBUSDT, DOGEUSDT та інших низькоцінових монет

**Recommendation:**
Unify tick_size resolution in a single helper. Never fallback to hardcoded value - fail loudly if tick_size unavailable.

### 3.2. Race Condition in Position Closing - Timeout Bug (ВИПРАВЛЕНИЙ АНАЛІЗ)
**Location:** `fsm_manage.py:796-805` & `fsm.py:3598, 3663, 3861`
**Issue (UPDATED):**
Повторна перевірка коду виявила **реальну проблему** - це не про скидання прапора, а про **таймаут**:
```python
# fsm_manage.py:796-798
if self._closing_position:
    elapsed_s = time.time() - self._closing_position_ts
    if elapsed_s < (self._anti_race_close_ms / 1000.0):  # Default 800ms
```

**ПРОБЛЕМА:**
1. Прапор встановлюється при `CMD:CLOSE` або `DEC:CLOSE`
2. Він автоматично **згасає через 800ms** (configurable)
3. Якщо close order виконується повільно (>800ms), bracket може **відразу ж з'явитися знову** після fill!

**Сценарій збою:**
- T+0ms: `CMD:CLOSE` → `_closing_position = True`
- T+900ms: Close order fills → position = 0
- T+901ms: WebSocket fill event → `ManageFlowFSM` бачить `_closing_position = False` (timeout) → намагається створити bracket для qty=0!

**Impact:**
Брекети можуть з'являтися для **нульової позиції** якщо мережа повільна.

**Recommendation:**
Не покладатися на timeout. Використовувати state-based approach: перевіряти `position_qty == 0` перед створенням brackets.

### 3.3. Potential None Division in Tick Size Quantization
**Location:** `apps/reference/domains/execution_position/fsm.py:4132-4172`
**Issue:**
```python
tick_size = None
try:
    # ... спроба отримати з конфігу ...
    tick_size = float(...)
except:
    pass

# Потім передається в utils.quantize_stop_price:
tp_q = quantize_stop_price(tp, tick_size, side="BUY")
```

**ПРОБЛЕМА:**
Якщо конфіг не містить `tick_size`, змінна залишається `None` і передається в функцію. У `utils.py:23`:
```python
t = Decimal(str(tick_size))  # Decimal('None') → InvalidOperation!
```

**Impact:**
- `InvalidOperation` exception при спробі квантування
- Bracket orders не будуть створені
- Позиція залишиться без захисту (no SL/TP)

**Recommendation:**
Validate `tick_size is not None` before calling quantize functions. Log error if missing.

### 3.4. Non-Atomic State Fetch in Aggregated Watchdog
**Location:** `apps/reference/domains/execution_position/agg_oco_watchdog.py:2032-2033`
**Issue:**
```python
open_orders = await self._call_adapter_fn("get_open_orders", None)
positions = await self._call_adapter_fn("get_open_positions")
```
**Impact:**
These two calls are not atomic. A fill could occur between them.
- **Scenario:** `get_open_orders` returns a TP order. *Fill occurs*. `get_open_positions` returns 0 position.
- **Result:** Watchdog sees "TP order exists" + "Position is 0" -> **ORPHAN_SL_FOR_ZERO_POSITION** (or similar violation).
- **Consequence:** Watchdog might aggressively cancel a valid order or flag a false positive violation.
**Recommendation:**
Accept that snapshots are fuzzy. Implement a "double-check" or "grace period" before acting on violations, or use a sequence-id based synchronization if the exchange supports it (unlikely for REST).

### 3.5. Clearing Flag on ENTRY While Closing (Логічна Помилка)
**Location:** `fsm_manage.py:538-542`
**Issue:**
```python
if self._closing_position:
    self._closing_position = False
    LOG.info("[BRK] ENTRY detected → closing_flag=False")
```

**ПРОБЛЕМА:**
Коментар каже "ENTRY detected", але це виконується **незалежно від того, чи це справді новий ENTRY**. Якщо:
1. Position існує (qty > 0)
2. `CMD:CLOSE` встановлює `_closing_position = True`
3. Partial fill від ENTRY ордера (який відкривав позицію раніше) приходить із затримкою
4. Прапор скидається → bracket може з'явитися під час закриття!

**Impact:**
Race condition: старий ENTRY fill може скинути closing flag під час активного закриття.

**Recommendation:**
Check `is_exit_order()` **before** clearing flag, або взагалі не чіпати цей прапор у `fsm_manage.py`.

### 3.6. Bracket Price Fallback Bug
**Location:** `fsm_manage.py:1307-1311`
**Issue:**
```python
tick_size = self._lookup_instrument_value("tick_size") or Decimal("0.01")
offset_bps = (
    self._lookup_instrument_value("bracket_offset_bps")
    or tick_size  # 🔴 BUG: uses tick_size as offset_bps!
)
```

**ПРОБЛЕМА:**
Якщо `bracket_offset_bps` відсутній у конфігу, код використовує **tick_size як offset_bps**!
- `tick_size = 0.01` (price step)
- `offset_bps` має бути basis points (наприклад, 5 = 0.05%)
- Використання `0.01` як offset_bps → offset буде **в 500 разів більший** ніж задумано!

**Impact:**
SL/TP ціни будуть дуже далеко від entry → неоптимальний R:R.

**Recommendation:**
Never use `tick_size` as `offset_bps`. Use explicit default like `5` bps.

### 3.7. Duplicated tick_size Logic Across Methods
**Location:** `fsm_manage.py` (legacy vs aggregated paths)
**Issue:**
Та сама логіка резолюції `tick_size` дублюється у:
1. `_place_brackets_legacy()` - хардкод `0.01`
2. `_place_brackets_aggregated()` - `_lookup_instrument_value()` або `0.01`
3. `fsm.py` - ще одна спроба з конфігу

**Impact:**
Три різні реалізації → три точки підтримки. Якщо фікс в одному місці, інші залишаються broken.

**Recommendation:**
Extract to `_resolve_tick_size(symbol)` helper. Use in all paths.

## 4. Major Findings (Medium Priority)

### 4.1. Fragile Exit Order Classification
**Location:** `apps/reference/domains/execution_position/contracts.py:367`
**Issue:**
`classify_exit_order` relies heavily on string matching:
```python
has_sl_pattern = client_order_id.endswith("_sl") or client_order_id.startswith("sl-")
```
**Impact:**
If `clientOrderId` generation logic changes (e.g., in `utils.py` or `fsm_manage.py`) without updating this contract, orders will be misclassified. This breaks `OrderGuardian` and `ManageFlowFSM` logic.
**Recommendation:**
Formalize `clientOrderId` structure in a shared builder/parser class. Do not rely on ad-hoc string suffixes.

### 4.2. Duplicate `clientOrderId` Logic
**Location:** `apps/reference/domains/execution_position/utils.py` vs `fsm_manage.py`
**Issue:**
`generate_client_order_id` exists in `utils.py`, but `fsm_manage.py` has its own `_generate_client_seed` and `_compose_client_order_id`.
**Impact:**
Inconsistency. If one is updated (e.g., to fix length limits), the other might remain broken.
**Recommendation:**
Unify usage to `utils.py`.

### 4.3. `_place_brackets_legacy` vs `_place_brackets_aggregated`
**Location:** `apps/reference/domains/execution_position/fsm_manage.py`
**Issue:**
Two parallel implementations for bracket placement. `_place_brackets_legacy` contains the hardcoded tick size bug. `_place_brackets_aggregated` delegates to `OrderGuardian`.
**Impact:**
Double maintenance burden. Legacy path is prone to bit-rot.
**Recommendation:**
Deprecate legacy path if Aggregated OCO is the standard. If legacy is needed, refactor to share calculation logic.

### 4.4. Hardcoded Timeouts
**Location:** `apps/reference/domains/execution_position/watchdog.py`
**Issue:**
Timeouts (ACK_TIMEOUT, FILL_TIMEOUT) appear to be hardcoded or have weak config fallbacks.
**Impact:**
Inability to tune for different market conditions (e.g., high latency).

## 5. Minor Findings (Low Priority)

*   **TODOs/FIXMEs:** Numerous TODOs found (e.g., "fetch from /exchangeInfo").
*   **Logging Noise:** `print()` statements found in `fsm_manage.py` (lines 520, 526, 544, 550). Should use `logger`.
*   **Type Hinting:** Some `Any` types used where specific types could be defined.

## 6. Async & Concurrency Analysis
*   **`asyncio.sleep`**: Used in `binance_execution_adapter.py` for backoff. Generally safe, but ensure it doesn't block the main FSM loop if called synchronously (it seems to be in async methods).
*   **Locks:** `_flows_lock` (threading) and `_agg_watchdog_lock` (asyncio) are used.
    *   **Risk:** `ExecPosFSM` uses `threading.Lock` but also manages `asyncio` tasks. Mixing threading and asyncio locks requires care. Ensure `_flows_lock` doesn't block the reactor.

## 7. Recommendations & Next Steps

1.  **IMMEDIATE (P0):** Create unified `_resolve_tick_size(symbol)` helper. Remove ALL hardcoded `0.01` values. Fail loudly if unavailable.
2.  **IMMEDIATE (P0):** Fix `offset_bps` fallback bug (line 1311) - never use `tick_size` as offset.
3.  **HIGH (P1):** Replace `_closing_position` timeout logic with state-based check: `if position_qty == 0: skip brackets`.
4.  **HIGH (P1):** Add `tick_size is not None` validation before quantization in `fsm.py:4169`.
5.  **HIGH (P1):** Fix clearing flag logic (line 539) - only clear on **new** ENTRY, not delayed fills.
6.  **MEDIUM (P2):** Add "double-check" grace period in `agg_oco_watchdog.py` before canceling orders.
7.  **MEDIUM (P2):** Unify `clientOrderId` generation.
8.  **CLEANUP:** Remove `print()` statements, address TODOs.

This audit concludes that while the core FSM logic is sound, the "glue" code (adapters, config, guards) contains fragile assumptions that must be addressed before scaling.
