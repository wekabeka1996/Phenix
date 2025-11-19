# AGG_OCO Phase 5: Integration Testing Report

**Дата:** 19 листопада 2025
**Статус:** ✅ Completed
**Test Suite:** `tests/domains/execution_position/test_agg_oco_integration.py`

---

## Executive Summary

Створено та виконано набір інтеграційних тестів для верифікації дефектів, виявлених під час Code Review (Phase 3). Тести підтвердили наявність критичних проблем у логіці **Startup Reconciliation** (Defect #1) та **Bracket Recalculation** (Defect #6).

Також верифіковано **Nominal Flow** (стандартне відкриття позиції), який працює коректно, що підтверджує валідність тестового оточення.

---

## Test Results

| Test Case | Result | Related Defect | Description |
|-----------|--------|----------------|-------------|
| `test_nominal_flow_open_position` | ✅ **PASSED** | N/A | Підтверджує, що базовий механізм створення брекетів працює коректно при відкритті нової позиції. |
| `test_startup_missing_brackets_bug` | ✅ **PASSED** | **Defect #1** | Тест успішно відтворив баг: при старті з існуючою позицією без ордерів, система **НЕ** створює нові брекети. |
| `test_recalc_duplication_bug` | ❌ **FAILED** | **Defect #6** | Тест підтвердив баг: при зміні розміру позиції (recalc) старі ордери **НЕ** скасовуються, хоча нові створюються. |

---

## Detailed Analysis

### 1. Defect #1: Startup Missing Brackets
**Test:** `test_startup_missing_brackets_bug`
**Behavior:**
- Mock adapter повертає відкриту позицію, але пустий список ордерів.
- Викликається `_startup_order_guardian_reconcile()`.
- **Очікування (Fix):** Система має виявити відсутність брекетів і створити їх.
- **Реальність (Bug):** Метод `place_stop_market_close_position` не викликається.
- **Висновок:** Логіка startup reconciliation лише лінкує існуючі ордери, але не ініціює створення нових для незахищених позицій.

### 2. Defect #6: Recalc Duplication
**Test:** `test_recalc_duplication_bug`
**Behavior:**
- Симулюється відкрита позиція з існуючими SL/TP.
- Надсилається подія `FILL` (scale-in), що тригерить перерахунок (recalc).
- **Очікування:** Старі ордери скасовуються, нові створюються.
- **Реальність:**
    ```
    E   AssertionError: Old brackets were not cancelled during recalc!
    E   assert 0 == 2
    ```
- **Висновок:** Метод `_recalc_aggregated_brackets` у `ManageFlowFSM` створює нові ордери, але пропускає крок скасування попередніх. Це призводить до накопичення дубльованих SL/TP ордерів на біржі.

### 3. Nominal Flow Verification
**Test:** `test_nominal_flow_open_position`
**Behavior:**
- Симулюється `FILL` подія для відкриття нової позиції.
- Система коректно генерує `DEC:PLACE_ORDER` для SL та TP.
- **Висновок:** Проблема не в механізмі відправки ордерів, а саме в логіці управління станом (startup/recalc).

---

## Root Cause Confirmation

Тести підтвердили гіпотези з Phase 3:

1.  **Defect #1 Root Cause:** Відсутність гілки коду в `_startup_order_guardian_reconcile`, яка б обробляла випадок `position > 0 AND no_brackets`.
2.  **Defect #6 Root Cause:** Відсутність виклику `cancel_order` (або еквівалентного механізму очищення) перед викликом `_place_or_update_bracket_set_from_levels` у методі `_recalc_aggregated_brackets`.

## Next Steps

Перехід до **Phase 7: Fix Implementation**:
1.  Додати логіку створення брекетів у `_startup_order_guardian_reconcile`.
2.  Додати логіку скасування старих брекетів у `_recalc_aggregated_brackets`.
3.  Використати створені тести для верифікації виправлень.
