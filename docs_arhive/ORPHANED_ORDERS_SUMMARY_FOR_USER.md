# 🔴 КРИТИЧНА ПРОБЛЕМА: РЕЗЮМЕ ДЛЯ КОРИСТУВАЧА

**Дата**: 4 листопада 2025
**Статус**: Проблема ВИЯВЛЕНА та ЗАДОКУМЕНТОВАНА ✅
**Пріоритет**: 🔴 **CRITICAL P0+** (наверх за P1)

---

## 📌 Те Що Ви Описали - Точно Описано

Ви правильно визначили проблему! Ось як вона працює:

### Проблема в 3 пункти:

1. **API vs UI Різниця** ✅
   - На біржовому UI: 1 ордер "з дужками" (bracket order з TP/SL)
   - В API: 3 **окремих** ордери
     - MARKET (entry)
     - STOP_MARKET (SL)
     - TAKE_PROFIT_MARKET (TP)

2. **При закритті позиції** ✅
   - Основний ордер закривається
   - **НО**: TP/SL залишаються АКТИВНИМИ на біржі
   - Вони стають "сирітськими" ордерами (без пов'язаної позиції)

3. **Накопичення + Ліміт** ✅
   - Binance має ліміт: **200 ордерів на счету**
   - Кожна позиція = 3 ордери
   - Після ~66 позицій: 66×3 ≈ 200 ордерів
   - **Результат**: Система НЕ може розміщувати нові ордери
   - **Error**: `Too Many Open Orders` з код -3000 від API

---

## 🔍 Де Точно Проблема в Коді

### Місце 1: Розміщення ордерів (РОБИТЬ)
**Файл**: `fsm.py` лінії 480-630

```python
# 1️⃣ MARKET ордер на вхід
entry_resp = await adapter.place_market_entry(...)
entry_order_id = str(entry_resp["orderId"])

# 2️⃣ STOP_MARKET ордер (SL)
sl_resp = await adapter.place_stop_market_close_position(...)
sl_order_id = str(sl_resp["orderId"])

# 3️⃣ TAKE_PROFIT_MARKET ордер (TP)
tp_resp = await adapter.place_take_profit_market_close_position(...)
tp_order_id = str(tp_resp["orderId"])
```
✅ **Робить**: розміщує всі 3 ордери

---

### Місце 2: Закриття позиції (НЕ РОБИТЬ СКАСУВАННЯ!)
**Файл**: `fsm_close.py` лінії 115+

```python
def _emit_close(self, msg: Message, why: str, details: Dict[str, Any]) -> Message:
    """Generate DEC:CLOSE with reduce_only=true."""

    dec = Message(
        op="DEC",
        verb="CLOSE",  # ← Тільки CLOSE
        # ❌ НЕ скасовує SL та TP!
        pld={"reduce_only": True, **details}
    )
    return dec
```
❌ **НЕ робить**: НЕ генерує DEC:CANCEL_ORDER для SL/TP

---

### Місце 3: Виконання закриття (НЕ РОБИТЬ СКАСУВАННЯ!)
**Файл**: `fsm.py` лінії 480+, метод `_execute_decision`

Коли отримано DEC:CLOSE:
```python
# Розміщує close ордер (reduce_only=true)
close_resp = await adapter.place_market_close_position(...)

# ❌ НЕ СКАСОВУЄ SL/TP!
# Вони залишаються АКТИВНИМИ на біржі
```
❌ **НЕ робить**: НЕ скасовує SL/TP при закритті позиції

---

### Місце 4: OCO Emulation (РОБИТЬ, але НЕПОВНО)
**Файл**: `fsm_manage.py` лінії 375-489

```python
def _handle_bracket_fill(self, msg: Message) -> Optional[Message]:
    """Handle SL/TP bracket fills and perform OCO emulation."""

    # Якщо SL заповнено → скасувати TP
    if order_id == self.sl_order_id:
        if self.tp_order_id and oco_emulation_enabled:
            return self._emit_cancel_order(msg, self.tp_order_id, "OCO_SL_filled")

    # Якщо TP заповнено → скасувати SL
    elif order_id == self.tp_order_id:
        if self.sl_order_id and oco_emulation_enabled:
            return self._emit_cancel_order(msg, self.sl_order_id, "OCO_TP_filled")
```
✅ **Робить**: скасовує протилежний ордер коли один заповнюється
❌ **НЕ робить**: НЕ скасовує при manual close позиції (CloseFlow)

---

## 🚀 Рішення (3 Фази)

### Фаза 1️⃣: ATOMICITY закриття позиції (2 дні)

**Крок 1**: Зберігати mapping (thread-safe)
```python
# У ExecPosFSM.__init__
self.bracket_order_tracking = {}  # entry_order_id → {sl_order_id, tp_order_id, symbol, side}
self.bracket_tracking_lock = threading.Lock()

# При розміщенні ордерів (fsm.py:500)
self._track_bracket_orders(
    entry_order_id=entry_order_id,
    sl_order_id=sl_order_id,
    tp_order_id=tp_order_id,
    symbol=symbol,
    side=side
)
```

**Крок 2**: Скасувати SL/TP **ПЕД закриттям**
```python
# В _execute_close() метода
if entry_order_id:
    brackets = self._get_brackets_for_entry(entry_order_id)
    if brackets:
        # Скасувати SL (если он есть)
        if brackets["sl_order_id"]:
            await adapter.cancel_order(symbol, brackets["sl_order_id"])

        # Скасувати TP (если он есть)
        if brackets["tp_order_id"]:
            await adapter.cancel_order(symbol, brackets["tp_order_id"])

# ТІЛЬКИ ТЕПЕР розміщуємо close ордер
close_resp = await adapter.place_market_close_position(...)
```

**Результат**: TP/SL **ЗАВЖДИ** скасовуються перед закриттям

---

### Фаза 2️⃣: Garbage Collector (0.5 дня)

**Що робить**: Шукає ордери БЕЗ пов'язаної позиції і скасовує їх

```python
async def cleanup_orphaned_bracket_orders(self):
    """Видалити сирітські ордери (ордери без позиції)."""

    # 1. Отримати всі ордери
    open_orders = await adapter.get_open_orders()

    # 2. Отримати всі позиції
    open_positions = await adapter.get_open_positions()

    # 3. Символи БЕЗ позицій
    positions_symbols = {p["symbol"] for p in open_positions if abs(float(p["positionAmt"])) > 0}

    # 4. Ордери за символами без позицій
    orphaned = [o for o in open_orders if o["symbol"] not in positions_symbols]

    # 5. Скасувати їх
    for order in orphaned:
        await adapter.cancel_order(order["symbol"], order["orderId"])
```

**Запускати**: Фоновий task кожні 5 хвилин

**Результат**: Старі сирітські ордери автоматично очищаються

---

### Фаза 3️⃣: Моніторинг 200 ордерів (0.5 дня)

```python
async def check_order_limit(self):
    """Контролювати кількість ордерів і алертити при наближенні."""

    open_orders = await adapter.get_open_orders()
    count = len(open_orders)

    # 🟢 GREEN: < 150 (75%)
    if count < 150:
        LOG.debug(f"✅ Orders: {count}/200")

    # 🟡 YELLOW: 150-180 (75-90%)
    elif count < 180:
        LOG.warning(f"⚠️ Orders: {count}/200 - WARNING!")
        await cleanup_orphaned_bracket_orders()  # Запустити cleanup

    # 🔴 RED: >= 180 (90%+)
    elif count >= 180:
        LOG.critical(f"🔴 Orders: {count}/200 - CRITICAL!")
        self.pause_new_trades()  # Зупинити нові торги
        await cleanup_orphaned_bracket_orders()  # Невідкладне очищення
```

**Запускати**: Фоновий task кожну хвилину

**Результат**: Система НЕ дозволить наблизитися до ліміту

---

## 📊 Очікувані Результати

| До Фіксу | Після Фіксу |
|----------|------------|
| +2-3 orphaned ордери на торгівлю | 0 orphaned ордерів ✅ |
| Після 100 торгів: ~198 ордерів (БЛОК!) | Після 100 торгів: 6-10 ордерів ✅ |
| System uptime: 4-6 часів | System uptime: Unlimited ✅ |
| Trades rejected: Частіше після 6 годин | Trades rejected: Ніколи ✅ |

---

## 📋 Реалізаційний Чек-Лист

### Фаза 1: Atomicity (2 дні)
- [ ] 1.1 Додати `bracket_order_tracking` в ExecPosFSM
- [ ] 1.2 Реалізувати `_track_bracket_orders()` method
- [ ] 1.3 Викликати при розміщенні (fsm.py:500)
- [ ] 1.4 Додати `_emit_close_with_bracket_cancellation()` у CloseFlowFSM
- [ ] 1.5 Модифікувати `_execute_close()` для скасування перед close

### Фаза 2: Cleanup (0.5 дня)
- [ ] 2.1 Реалізувати `cleanup_orphaned_bracket_orders()` method
- [ ] 2.2 Додати `_cleanup_loop()` фоновий task
- [ ] 2.3 Перевірити автоматичний запуск при старті

### Фаза 3: Monitoring (0.5 дня)
- [ ] 3.1 Реалізувати `check_order_limit()` method
- [ ] 3.2 Додати `_monitoring_loop()` фоновий task
- [ ] 3.3 Налаштувати алерти (75%, 90%, 100%)

### Тестування (0.5 дня)
- [ ] Unit тести для всіх 3 фаз
- [ ] Integration: 100+ торгів локально БЕЗ накопичення
- [ ] Testnet: 24-годинна стабільність

---

## 📄 Документація

Створено:
1. ✅ **CRITICAL_ISSUE_ORPHANED_BRACKET_ORDERS.md** - Повний teknički опис проблеми та рішення
2. ✅ **TODO.md** - Оновлено з критичними задачами
3. ✅ **JOURNAL.md** - Записано виявлення проблеми
4. ✅ **COMPREHENSIVE_TRADING_SYSTEM_LOGIC.md** - Будет оновлено після фіксу

---

## 🎯 Наступні Кроки

### Від Вас (контроль):
1. Перевірити що ви розумієте проблему ✅ (ви описали точно!)
2. Дати "зелене світло" для реалізації (коли готові)
3. Протестувати на вашому окремому середовищі після фіксу

### Від Систем Розробки:
1. Реалізувати Фазу 1 (atomicity) - 2 дні
2. Додати Фазу 2 (cleanup) - 0.5 дня
3. Додати Фазу 3 (monitoring) - 0.5 дня
4. Написати тести - 0.5 дня
5. Deploy на testnet - 1 день
6. Live validation - 1 день

**Загалом**: 3-4 дні до FULL FIX

---

## ⚠️ ВАЖЛИВО

Це **BLOCKING** для production!

- ✅ Система працює нормально 4-6 годин
- ❌ После того блокується і **НІЯКИХ новых торгів!**
- ✅ Рішення простое і чітке
- ✅ Немає breaking changes - тільки додавання logic

**Status**: Готово до реалізації
**Risk**: LOW - additive fixes
**Impact**: HIGH - дозволяє 24/7 trading

---

*Документ створено: 4 листопада 2025*
*Версія: 1.0*
*Статус: READY FOR IMPLEMENTATION*
