# 📊 РЕЗЮМЕ: Дослідження Критичної Проблеми Orphaned Bracket Orders

**Дата**: 4 листопада 2025
**Статус**: 🔴 CRITICAL | Блокувальна для production
**Документація**: `CRITICAL_BUG_ORPHANED_ORDERS_ANALYSIS.md` (повний звіт)

---

## ⚡ Зв'язок у Двох Реченнях

### ПРОБЛЕМА
API Binance розділяє Bracket Order (Market + SL + TP) на **3 окремих ордера**. Коли позиція закривається, **SL/TP залишаються активними** і не скасовуються → система накопичує ордери до ліміту 200 → **торгівля припиняється через 2-3 години безперервної роботи**.

### РІШЕННЯ
Три фази: **(1)** скасовувати дужки при DEC:CLOSE, **(2)** watchdog для cleanup orphaned ордерів, **(3)** архітектурна перебудова.

---

## 📈 Сценарій Крашу

```
Торгівля #1:   3 ордери (entry + SL + TP)      Total: 3
Торгівля #2:   3 ордери (entry + SL + TP)      Total: 6
...
Торгівля #65:  3 ордери (entry + SL + TP)      Total: 195
Торгівля #66:  КРАХ ❌ - "Too Many Open Orders" (limit 200)

Час до краху: ~2-3 години безперервної торгівлі
```

---

## 🔍 Де Проблема в Коді

| Компонент | Файл | Проблема | Статус |
|-----------|------|----------|--------|
| **OpenFlow** | fsm_open.py | Розміщує entry ордер | ✅ OK |
| **ManageFlow** | fsm_manage.py | Розміщує SL/TP дужки | ✅ OK |
| **ManageFlow OCO** | fsm_manage.py:386-395 | Скасовує одну дужку якщо інша заповнена | ✅ Partial |
| **CloseFlow** | fsm_close.py:115 | **НЕ скасовує SL/TP при DEC:CLOSE** | ❌ BUG |
| **Orchestration** | fsm.py | Жодна логіка не видаляє дужки | ❌ BUG |
| **Binance API** | binance_execution_adapter.py | Виконує скасування BUT немає виклику | ✅ Infrastructure OK |

---

## 💾 Файли Задіяні

### Що потребує виправлення (PHASE 1: 2-3 дні)

1. **`vfoundation/apps/reference/domains/execution_position/fsm_close.py`** (162 рядків)
   - Метод: `_emit_close()` (lines 108-127)
   - **Зміна**: Повертати список [cancel_sl, cancel_tp, dec_close] замість одного DEC:CLOSE
   - **Логіка**: Скасовувати обидва дужки ПЕРЕД закриттям позиції

2. **`vfoundation/apps/reference/domains/execution_position/fsm_manage.py`** (559 рядків)
   - Метод: `handle()` (lines 79-160)
   - **Зміна**: Додати `_cleanup_brackets_on_error()` коли основний ордер REJECTED/EXPIRED
   - **Логіка**: Емітувати DEC:CANCEL_ORDER для SL+TP при помилці

3. **`vfoundation/apps/reference/domains/execution_position/binance_execution_adapter.py`** (1192 рядків)
   - Метод: `get_open_orders_count()` (новий)
   - **Зміна**: Повернути кількість активних ордерів, ALERT при >= 180
   - **Логіка**: API запит до `/fapi/v1/allOpenOrders`, рахування

4. **`apps/reference/telemetry/metrics.py`**
   - **Додати метрики**: `active_orders_gauge`, `orphaned_orders_total`, `orders_cancelled_total`

### Що можна розробляти паралельно (PHASE 2-3)

5. **`apps/reference/domains/execution_position/watchdog.py`** (новий файл)
   - Клас: `OrphanedOrdersWatchdog`
   - **Логіка**: Кожні 60 сек знайти ордери без активної позиції → скасувати

6. **`apps/reference/domains/execution_position/bracket_group.py`** (новий файл)
   - Клас: `BracketOrderGroup`
   - **Логіка**: Управління main+SL+TP як атомарною одиницею

---

## ✅ Тестування

### Unit Tests (PHASE 1)
```python
test_close_flow_cancels_brackets()           # fsm_close.py
test_manage_cleanup_on_rejection()           # fsm_manage.py
test_binance_order_count_metric()            # binance_execution_adapter.py
```

### Integration Tests (PHASE 1)
```python
test_integration_no_orphaned_after_close()   # 70+ позицій, verify < 50 active orders
test_watchdog_cleanup()                      # Verify cleanup after 60 sec
```

### Load Test
```
Target: 100+ торгівель → active_orders < 50 (instead of ~300)
Metric: Time to crash → Never (instead of 2.5 hours)
```

---

## 📋 План Дій

### PHASE 1: CRITICAL (2-3 дні) ⚡ НЕГАЙНЕ

```
День 1:
- [ ] Виправити fsm_close.py (0.5д)
- [ ] Виправити fsm_manage.py (0.5д)
- [ ] Додати metrics (0.5д)

День 2:
- [ ] Написати unit тести (0.5д)
- [ ] Integration тестування (0.5д)
- [ ] Staging testnet deployment (0.5д)

День 3:
- [ ] 24-hour stability test (1д)
- [ ] Merge + Deploy to main branch
```

### PHASE 2: SECONDARY (1-1.5 дня)

```
- [ ] Watchdog implementation (1д)
- [ ] OrderIndex розширення (0.5д)
```

### PHASE 3: REFACTOR (1-2 дня)

```
- [ ] BracketOrderGroup (1д)
- [ ] Architecture cleanup (0.5д)
```

---

## 🚨 Блокуючі Чинники

| Чинник | Вплив | Час Блокування |
|--------|-------|----------------|
| **PHASE 1 не завершена** | Система краш через 2-3ч | Блокує production deployment |
| **Unit тести не написані** | Регресія непідхоплена | Блокує merge |
| **Testnet не валідований** | Невідомо чи рішення працює | Блокує mainnet deploy |

---

## 📊 Метрики Успіху

| Метрика | Поточне | Цільове | Критерій |
|---------|---------|---------|----------|
| Active Orders (per close) | +2 per trade | 0 | ✅ Zero accumulation |
| Max Orders (100 trades) | ~300 (ERROR) | <50 | ✅ Safe margin |
| Crash Time | 2.5h | Never | ✅ Infinite runtime |
| Watchdog Detection | N/A | >99% | ✅ Cleanup confidence |

---

## 🎯 Рекомендація

**НЕГАЙНО розпочати PHASE 1** перед будь-яким production deployment.

Проблема є **блокуючою** для безперервної торгівлі. Система може працювати тільки 2-3 години поспіль, потім припиняє роботу.

**Приблизна тривалість виправлення**: 3-5 днів (PHASE 1-2)
**Приблизна тривалість розширення**: 1-2 дні (PHASE 3)

---

**Документи**:
- 📄 **Повний аналіз**: `CRITICAL_BUG_ORPHANED_ORDERS_ANALYSIS.md`
- 📋 **TODO оновлено**: `TODO.md` (ORPHANED_BRACKET_ORDERS section)
- 📝 **JOURNAL запис**: `JOURNAL.md` (RID: ORPHANED_BRACKET_ORDERS_DISCOVERY)

**Статус**: 🔴 CRITICAL — In Analysis, Ready for Implementation
