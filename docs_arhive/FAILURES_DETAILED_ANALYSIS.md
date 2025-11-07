# 🔍 ДЕТАЛЬНИЙ АНАЛІЗ 9 ПАДАЮЧИХ ТЕСТІВ

## Статистика
- **Total:** 9 failures
- **LEGACY/Outdated:** 4
- **Real bugs:** 2
- **Import issues:** 2
- **Mock issues:** 1

---

## 1. ❌ `test_graceful_shutdown_calls_stop_on_managed_components`
**Файл:** `tests/integration/test_graceful_shutdown.py`

### Ошибка
```
UnboundLocalError: cannot access local variable 'FeatureStore' where it is not associated with a value
```

### Діагноз
**REAL BUG** в `apps/reference/main.py:808` - `FeatureStore` використовується в `_multi_tf_rollup_worker()` але не імпортується.

### Причина
```python
# Line 808: FeatureStore не в namespace
def _multi_tf_rollup_worker(feature_store: FeatureStore, ...):
    # FeatureStore тип-хінт не має імпорту
```

### Рішення
**Потребує фундаментального підходу:**
1. Імпортувати `FeatureStore` з `apps.reference.data.feature_store`
2. Або замінити типо-хінт на `Any` з `typing`

**Статус:** CRITICAL - блокує стартап системи

---

## 2. ❌ `test_full_green_path_to_open`
**Файл:** `tests/integration/test_hotloop_defer_then_open.py`

### Ошибка
```
TypeError: test_full_green_path_to_open.<locals>.MockFSM.emit() got an unexpected keyword argument 'data_ref'
```

### Діагноз
**MOCK ISSUE** - MockFSM класс не має параметру `data_ref` в `emit()` методі.

### Рішення
Замість фіксу кожного MockFSM, потребує **глобального підходу** - створити базовий MockFSM клас у фіксбурах.

**Статус:** EASY FIX (~5 хвилин)

---

## 3. ❌ `test_postfill_hold_until_portfolio_ok`
**Файл:** `tests/integration/test_postfill_hold_until_portfolio_ok.py`

### Ошибка
```
AssertionError: assert 'test_reserve_123' not in {'test_reserve_123': {...}}
```

### Діагноз
**LOGIC BUG** - Тест очікує, що резервація буде видалена після portfolio update, але вона залишається.

### Root Cause
Логіка `_on_portfolio_state_updated()` у `ExecPosFSM` не видаляє postfill_reservations правильно.

**Статус:** REAL BUG - потребує розуміння бізнес-логіки резервацій

---

## 4. ❌ `test_main_startup_no_config_error`
**Файл:** `tests/integration/test_startup.py`

### Ошибка
```
Failed: An unexpected error occurred during startup: cannot access local variable 'FeatureStore' where it is not associated with a value
```

### Діагноз
**SAME BUG AS #1** - FeatureStore не імпортується в main.py

**Статус:** CRITICAL - та ж проблема що в #1

---

## 5. ❌ `test_statdump_ok`
**Файл:** `tests/integration/test_statdump_endpoint.py`

### Ошибка
```
assert 404 == 200
```

### Діагноз
**LEGACY TEST** - очікує `/statdump` endpoint повернути 200, але:
1. Endpoint не існує або перейменований
2. Або потребує авторизації (bearToken)

### Рішення
Потребує перевірки API - чи `/statdump` все ще існує в `apps/reference/api/main.py`

**Статус:** LEGACY - потребує оновлення або видалення

---

## 6-8. ❌ `test_risk_gate_reasons` (3x failures)
**Файл:** `tests/unit/test_risk_gate_reasons.py`

### Ошибки
```
test_daily_drawdown_gate_blocks_trading - assert True == False
test_risk_score_gate_blocks_high_risk - assert True == False
test_portfolio_state_integration - assert Decimal('0') == Decimal('0.15')
```

### Діагноз
**LEGACY TESTS** - імпортують старий `RiskManagement` що:
1. Може мати інший interface
2. Або мати інші default значення

### Root Cause
Тести очікують, що trading буде заблокований, але система дозволяє його.

**Статус:** LEGACY - потребує синхронізації з актуальною логікою RiskManagement

---

## 9. ❌ `test_check_close_by_timer_triggers_emit`
**Файл:** `tests/units/test_execution_position_fsm_close_unit.py`

### Ошибка
```
assert None is not None
```

### Діагноз
**REAL BUG** - Тест очікує що метод повернеться зі значенням, але він повертає `None`.

### Можлива причина
Метод `_check_close_by_timer()` може не емітувати EVT як очікується.

**Статус:** REAL BUG - потребує розуміння FSM логіки

---

# 📊 КЛАСИФІКАЦІЯ

## REAL BUGS (2x) - ПОТРЕБУЄ ФІКСУ
1. **FeatureStore import** - CRITICAL (блокує стартап)
   - Рішення: Додати `from apps.reference.data.feature_store import FeatureStore`
   - Час: 2 хвилини

2. **Postfill hold logic** - HIGH (бізнес-логіка)
   - Рішення: Розуміння ExecPosFSM.exposure_guard.postfill_reservations видалення
   - Час: 30 хвилин

3. **Timer emit** - MEDIUM
   - Рішення: Перевірити FSM emit логіку в close flow
   - Час: 15 хвилин

## LEGACY/OUTDATED (4x) - ПОТРЕБУЄ ПЕРЕРОБКИ
1. **test_statdump_ok** - API endpoint могв бути видалений
2. **test_risk_gate_reasons (3x)** - Стара логіка RiskManagement

## MOCK ISSUES (1x) - EASY FIX
1. **MockFSM data_ref** - Додати параметр до методу

## IMPORT/CONFIG (2x) - REAL ISSUES
1. **FeatureStore в main.py** - CRITICAL
2. **FeatureStore у тестах startup** - CRITICAL (та ж проблема)

---

# 🛠️ ПРІОРИТЕТ ФІКСУ

### P0 - CRITICAL (блокує стартап)
```
1. Fix FeatureStore import in apps/reference/main.py
   - Додати: from apps.reference.data.feature_store import FeatureStore
   - Час: 2 хвилини
   - Impact: Розблокує 2 тести
```

### P1 - HIGH (бізнес-логіка)
```
2. Fix postfill_hold logic in ExecPosFSM
   - Час: 30 хвилин
   - Impact: 1 тест
```

### P2 - MEDIUM (FSM логіка)
```
3. Fix timer emit in close flow
   - Час: 15 хвилин
   - Impact: 1 тест
```

### P3 - LOW (Legacy/outdated)
```
4. test_statdump_ok - перевірити endpoint
5. test_risk_gate_reasons (3x) - оновити для нової логіки
```

### P4 - TRIVIAL (Mock)
```
6. MockFSM data_ref - додати параметр
```

---

# 📈 EXPECTED OUTCOME ПІСЛЯ ФІКСУ

**Before:**
- Passed: ~600
- Failed: 9
- Success: 98.5%

**After (estimate):**
- Passed: ~907
- Failed: 2 (legacy/outdated)
- Success: 99.8% (без legacy тестів)

