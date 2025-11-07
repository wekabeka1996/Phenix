# 🔴 КРИТИЧНА ПРОБЛЕМА: Сирітські Ордери TP/SL При Закритті Позицій

**Статус:** CRITICAL | **Пріоритет:** P0 | **Дата:** Листопад 2025

---

## 📋 ОПИС ПРОБЛЕМИ

### Проблема
При закритті позиції система **не скасовує** (не канселює) ордери **Take Profit (TP)** та **Stop Loss (SL)**, які залишаються **АКТИВНИМИ** на біржі. Це призводить до:

1. **Накопичення сирітських ордерів** - ордери без пов'язаної позиції
2. **Вичерпання лімітів біржі** - Binance має ліміт 200 відкритих ордерів на счету
3. **Блокування нових торгів** - коли лічильник досягне 200, нові ордери відхилятимуться
4. **Фінансові втрати** - застарілі TP/SL можуть активуватися неочікувано

### Приклад Сценарію

```
Час 10:00:
├─ Розміщена MARKET ордер (ENTRY): +1 ордер
├─ Розміщена STOP_MARKET ордер (SL): +1 ордер
├─ Розміщена TAKE_PROFIT_MARKET ордер (TP): +1 ордер
└─ Всього: 3 ордери на біржі

Час 10:01:
├─ ENTRY ордер заповнено → позиція открита
├─ SL і TP залишаються АКТИВНИМИ (чекають на срабатывание)
└─ Всього: 3 ордери (1 filled, 2 active)

Час 10:05: CloseFlow генерує DEC:CLOSE
├─ ExecPosFSM розміщує CLOSE ордер (reduce_only=true)
├─ CLOSE ордер виконується → позиція закривається
│
├─ ❌ PROBLEM: SL та TP ордери НЕ скасовані!
│  Вони залишаються АКТИВНИМИ на біржі
│
└─ Всього на біржі: 2 "сирітські" ордери (SL + TP)

Час 10:06 → 15:00: Це повторюється 100+ разів
└─ На біржі: ~200 сирітських ордерів

Час 15:01: Система намагається розмістити новий ордер
├─ Binance API повертає: "Too Many Open Orders" (код -3000)
├─ ❌ TRADE REJECTED
└─ Система не може торгувати!
```

### Чому Це Трапляється?

1. **Binance API розраховує ордери як окремі сутності:**
   - На UI виглядає як 1 ордер в дужках (bracket order)
   - В API це 3 окремих ордери
   - Ліміт: 200 ордерів = максимум 66 позицій * 3 ордери

2. **У коді НЕ гарантується скасування при закритті:**
   - `CloseFlowFSM` генерує DEC:CLOSE
   - Але НЕ генерує DEC:CANCEL_ORDER для TP/SL
   - OCO emulation в ManageFlowFSM тільки скасовує при заповненні (SL fills → cancel TP)
   - При manual close скасування не відбувається

3. **Відсутність mapping entry_order_id ↔ [sl_order_id, tp_order_id]:**
   - Система не знає які SL/TP належать якій позиції
   - Тяжко визначити які ордери можна скасувати

---

## 🔍 ТЕХНІЧ АНАЛІЗ КОДА

### Де розміщуються ордери (fsm.py:480-630)

```python
# 1️⃣ MARKET ордер на вхід
entry_resp = await self.adapter.place_market_entry(
    symbol, side, qty, entry_id
)
entry_order_id = str(entry_resp["orderId"])

# 2️⃣ STOP_MARKET ордер (Stop Loss)
sl_resp = await self.adapter.place_stop_market_close_position(
    symbol, sl_side, str(sl), new_client_order_id=sl_id
)
sl_order_id = str(sl_resp["orderId"])

# 3️⃣ TAKE_PROFIT_MARKET ордер (Take Profit)
tp_resp = await self.adapter.place_take_profit_market_close_position(
    symbol, tp_side, str(tp), new_client_order_id=tp_id
)
tp_order_id = str(tp_resp["orderId"])
```

### Де ордери мають скасовуватися (але НЕ скасовуються!)

#### ❌ CloseFlowFSM (fsm_close.py:115)
```python
def _emit_close(self, msg: Message, why: str, details: Dict[str, Any]) -> Message:
    """Generate DEC:CLOSE with reduce_only=true."""
    self.state = CloseState.EMIT_DEC_CLOSE

    dec = Message(
        op="DEC",
        verb="CLOSE",  # ← Лише CLOSE, БЕЗ скасування SL/TP!
        src=msg.dst,
        dst="execution_position",
        rid=msg.rid,
        pld={
            "reduce_only": True,
            **details,
        },
    )

    # ❌ НЕ скасовує SL та TP!
    return dec
```

#### ❌ ExecPosFSM (fsm.py, на_close_executed)
```python
# Коли позиція закривається (close ордер заповнюється)
# Система НЕ має логіки для скасування SL/TP

# Тільки эта логіка існує:
if abs(position_amt) < 0.0001:
    # No position - cancel any orphaned orders for this symbol
    if symbol in orders_by_symbol:
        for order in orders_by_symbol[symbol]:
            try:
                await self.adapter.cancel_order(symbol, order["orderId"])
            except Exception as e:
                LOG.error(f"❌ Failed to cancel order {order['orderId']}: {e}")
```

Це тільки для sync під час перезавантаження! Не для активного закриття!

#### ✅ ManageFlowFSM має OCO emulation (fsm_manage.py:375-489)
```python
def _handle_bracket_fill(self, msg: Message) -> Optional[Message]:
    """Handle SL/TP bracket fills and perform OCO emulation."""

    # Якщо SL заповнено → скасувати TP
    if order_id == self.sl_order_id:
        if self.tp_order_id and self.config.get("brackets", {}).get("oco_emulation", False):
            print(f"[ManageFlowFSM] SL filled, cancelling TP: {self.tp_order_id}")
            return self._emit_cancel_order(msg, self.tp_order_id, "OCO_SL_filled")

    # Якщо TP заповнено → скасувати SL
    elif order_id == self.tp_order_id:
        if self.sl_order_id and self.config.get("brackets", {}).get("oco_emulation", False):
            print(f"[ManageFlowFSM] TP filled, cancelling SL: {self.sl_order_id}")
            return self._emit_cancel_order(msg, self.sl_order_id, "OCO_TP_filled")

    return None
```

**✅ РОБИТЬ:** Скасовує протилежний ордер коли один заповнюється
**❌ ПРОБЛЕМА:** Це НЕ скасовує ордери при manual close позиції!

---

## 🛠️ РІШЕННЯ (План Реалізації)

### Фаза 1: Atomicity для закриття позиції

#### 1.1. Додати Mapping: Entry → [SL, TP]
**Файл:** `fsm.py` (ExecPosFSM класс)

```python
class ExecPosFSM:
    def __init__(self, ...):
        # ... існуючий код ...
        # ✅ ДОДАТИ:
        self.bracket_order_tracking = {}  # {entry_order_id: {sl_order_id, tp_order_id, symbol, side}}
        self.bracket_tracking_lock = threading.Lock()

    def _track_bracket_orders(self, entry_order_id: str, sl_order_id: Optional[str],
                             tp_order_id: Optional[str], symbol: str, side: str):
        """Track which SL/TP belong to which entry order."""
        with self.bracket_tracking_lock:
            self.bracket_order_tracking[entry_order_id] = {
                "sl_order_id": sl_order_id,
                "tp_order_id": tp_order_id,
                "symbol": symbol,
                "side": side,
                "created_at": time.time()
            }

    def _get_brackets_for_entry(self, entry_order_id: str) -> Optional[dict]:
        """Get SL/TP orders for a given entry order."""
        with self.bracket_tracking_lock:
            return self.bracket_order_tracking.get(entry_order_id)

    def _remove_bracket_tracking(self, entry_order_id: str):
        """Clean up tracking after position closes."""
        with self.bracket_tracking_lock:
            self.bracket_order_tracking.pop(entry_order_id, None)
```

**Де викликати:**

```python
# fsm.py:500 (після розміщення всіх 3 ордерів)
tp_order_id = str(tp_resp["orderId"])
self.correlation_store.put_sl_tp_ack(...)

# ✅ ДОДАТИ:
self._track_bracket_orders(
    entry_order_id=entry_order_id,
    sl_order_id=sl_order_id,
    tp_order_id=tp_order_id,
    symbol=symbol,
    side=side
)
```

#### 1.2. Генерувати DEC:CANCEL при CloseFlow
**Файл:** `fsm_close.py` (CloseFlowFSM класс)

```python
class CloseFlowFSM:
    def __init__(self, ...):
        # ... існуючий код ...
        self.exec_pos_fsm = None  # Reference to ExecPosFSM для доступу до tracking

    def _emit_close_with_bracket_cancellation(
        self,
        msg: Message,
        why: str,
        details: Dict[str, Any],
        entry_order_id: Optional[str] = None
    ) -> List[Message]:
        """
        Generate DEC:CLOSE + DEC:CANCEL_ORDER for SL/TP (ATOMIC).

        Returns list of messages: [DEC:CLOSE, DEC:CANCEL_ORDER_SL, DEC:CANCEL_ORDER_TP]
        """
        messages = []

        # 1️⃣ Основной DEC:CLOSE для закриття позиції
        dec_close = Message(
            op="DEC",
            verb="CLOSE",
            src=msg.dst,
            dst="execution_position",
            rid=msg.rid,
            why=why[:80],
            idempotent_key=f"{msg.rid}_close_{int(time.time())}",
            pld={
                "reduce_only": True,
                **details,
            },
        )
        messages.append(dec_close)

        # 2️⃣ Якщо є entry_order_id → отримати SL/TP
        if entry_order_id and self.exec_pos_fsm:
            brackets = self.exec_pos_fsm._get_brackets_for_entry(entry_order_id)

            if brackets:
                sl_order_id = brackets.get("sl_order_id")
                tp_order_id = brackets.get("tp_order_id")

                # ✅ Скасувати SL
                if sl_order_id:
                    dec_cancel_sl = Message(
                        op="DEC",
                        verb="CANCEL_ORDER",
                        src=msg.dst,
                        dst="execution_position",
                        rid=msg.rid,
                        why="close_with_bracket_cleanup_sl",
                        idempotent_key=f"cancel_sl_{sl_order_id}_{int(time.time())}",
                        pld={"orderId": sl_order_id},
                    )
                    messages.append(dec_cancel_sl)

                # ✅ Скасувати TP
                if tp_order_id:
                    dec_cancel_tp = Message(
                        op="DEC",
                        verb="CANCEL_ORDER",
                        src=msg.dst,
                        dst="execution_position",
                        rid=msg.rid,
                        why="close_with_bracket_cleanup_tp",
                        idempotent_key=f"cancel_tp_{tp_order_id}_{int(time.time())}",
                        pld={"orderId": tp_order_id},
                    )
                    messages.append(dec_cancel_tp)

        return messages
```

#### 1.3. Викликати атомарне закриття з скасуванням
**Файл:** `fsm.py` (де обробляється CLOSE рішення)

```python
async def _execute_close(self, decision: Message):
    """Execute CLOSE decision with bracket order cleanup."""

    try:
        symbol = decision.pld["symbol"]
        entry_order_id = decision.pld.get("entry_order_id")  # ← Передати entry ID!

        # 1️⃣ Отримати SL/TP ордери які потрібно скасувати
        brackets = self._get_brackets_for_entry(entry_order_id) if entry_order_id else None

        # 2️⃣ Скасувати SL та TP **ПЕРЕД** закриттям позиції
        if brackets:
            sl_order_id = brackets.get("sl_order_id")
            tp_order_id = brackets.get("tp_order_id")

            cancel_tasks = []

            if sl_order_id:
                LOG.info(f"🔄 Cancelling SL order {sl_order_id} before closing position")
                cancel_tasks.append(
                    self.adapter.cancel_order(symbol, sl_order_id)
                )

            if tp_order_id:
                LOG.info(f"🔄 Cancelling TP order {tp_order_id} before closing position")
                cancel_tasks.append(
                    self.adapter.cancel_order(symbol, tp_order_id)
                )

            # ✅ Чекаємо скасування обох ордерів (але продовжуємо якщо один не скасувався)
            if cancel_tasks:
                results = await asyncio.gather(*cancel_tasks, return_exceptions=True)
                for i, result in enumerate(results):
                    if isinstance(result, Exception):
                        LOG.warning(f"⚠️ Failed to cancel bracket order: {result}")
                    else:
                        LOG.info(f"✅ Bracket order cancelled: {result}")

        # 3️⃣ Тепер закрити позицію
        close_qty = decision.pld.get("qty", "0")
        entry_id = generate_client_order_id("CLOSE", symbol)

        close_resp = await self.adapter.place_market_close_position(
            symbol=symbol,
            side=opposite_side(decision.pld["side"]),
            quantity=close_qty,
            reduce_only=True,
            new_client_order_id=entry_id
        )
        LOG.info(f"✅ Position closed: {close_resp}")

        # 4️⃣ Очистити tracking
        if entry_order_id:
            self._remove_bracket_tracking(entry_order_id)

    except Exception as e:
        LOG.error(f"❌ Close execution failed: {e}", exc_info=True)
        # Alert monitoring
```

---

### Фаза 2: Garbage Collector для Orphaned Orders

**Файл:** `fsm.py` (новий метод в ExecPosFSM)

```python
async def cleanup_orphaned_bracket_orders(self, symbol: Optional[str] = None):
    """
    Періодичний Garbage Collector для видалення сирітських ордерів.

    Сирітський ордер = ордер на біржі БЕЗ пов'язаної позиції.
    """
    try:
        LOG.info("🧹 Starting orphaned bracket order cleanup...")

        # 1️⃣ Отримати всі открытые ордери
        symbols = [symbol] if symbol else self._get_all_active_symbols()

        for sym in symbols:
            open_orders = await self.adapter.get_open_orders(sym)
            open_positions = await self.adapter.get_open_positions(sym)

            # 2️⃣ Визначити які позиції АКТИВНІ
            position_exists = any(
                abs(float(p.get("positionAmt", 0))) > 0.0001
                for p in open_positions
            )

            # 3️⃣ Якщо позиція НЕ існує, але є TP/SL ордери → скасувати
            if not position_exists and open_orders:
                bracket_orders = [
                    o for o in open_orders
                    if o.get("type") in ["STOP_MARKET", "TAKE_PROFIT_MARKET", "LIMIT"]
                    and (o.get("reduceOnly") == "true" or o.get("closePosition") == "true")
                ]

                if bracket_orders:
                    LOG.warning(
                        f"⚠️  Found {len(bracket_orders)} orphaned bracket orders for {sym}")

                    for order in bracket_orders:
                        try:
                            order_id = order["orderId"]
                            LOG.info(f"🔄 Cancelling orphaned order: {sym} {order_id}")

                            result = await self.adapter.cancel_order(sym, order_id)

                            LOG.info(f"✅ Cancelled orphaned order: {result}")
                        except Exception as e:
                            LOG.error(f"❌ Failed to cancel orphaned order: {e}")

        LOG.info("✅ Orphaned order cleanup complete")

    except Exception as e:
        LOG.error(f"❌ Cleanup failed: {e}", exc_info=True)
```

#### Запускати cleanup регулярно

```python
# fsm.py: __init__ або start()
async def start(self):
    """Start FSM with background cleanup."""
    # ... існуючий код ...

    # ✅ ДОДАТИ: Запустити cleanup кожні 5 хвилин
    asyncio.create_task(self._cleanup_loop())

async def _cleanup_loop(self):
    """Run cleanup periodically."""
    while True:
        try:
            await asyncio.sleep(300)  # 5 minutes
            await self.cleanup_orphaned_bracket_orders()
        except Exception as e:
            LOG.error(f"Cleanup loop error: {e}")
```

---

### Фаза 3: Моніторинг Лічильника Ордерів

**Файл:** `fsm.py` (новий метод в ExecPosFSM)

```python
async def check_order_limit(self) -> int:
    """
    Check current open order count and alert if approaching limit.

    Binance limit: 200 orders per account
    """
    try:
        open_orders = await self.adapter.get_open_orders()
        order_count = len(open_orders)

        # METRICS
        self.metrics_collector.record_gauge("open_orders_count", order_count)

        # 🟢 GREEN: < 150 orders (75%)
        if order_count < 150:
            LOG.debug(f"📊 Open orders: {order_count}/200 ✅")

        # 🟡 YELLOW: 150-180 orders (75-90%)
        elif order_count < 180:
            LOG.warning(f"⚠️  Open orders: {order_count}/200 (WARNING)")

            # Alert: дублюємо check orphaned
            orphaned_count = await self._estimate_orphaned_orders()
            if orphaned_count > 10:
                LOG.warning(f"⚠️  Estimated {orphaned_count} orphaned orders - running cleanup")
                await self.cleanup_orphaned_bracket_orders()

        # 🔴 RED: >= 180 orders (90%+)
        elif order_count >= 180:
            LOG.critical(f"🔴 CRITICAL: Open orders: {order_count}/200 - APPROACHING LIMIT!")

            # Halt new trading
            self.pause_new_trades()

            # Immediately run cleanup
            await self.cleanup_orphaned_bracket_orders()

            # Alert monitoring system
            if self.alert_manager:
                self.alert_manager.send_alert(
                    severity="CRITICAL",
                    message=f"Order limit critical: {order_count}/200"
                )

        return order_count

    except Exception as e:
        LOG.error(f"Failed to check order limit: {e}")
        return -1

async def _estimate_orphaned_orders(self) -> int:
    """Estimate how many orders are orphaned (no position)."""
    try:
        open_orders = await self.adapter.get_open_orders()
        open_positions = await self.adapter.get_open_positions()

        # Symbols with active positions
        active_symbols = {
            p.get("symbol")
            for p in open_positions
            if abs(float(p.get("positionAmt", 0))) > 0.0001
        }

        # Orders for symbols WITHOUT positions
        orphaned = [
            o for o in open_orders
            if o.get("symbol") not in active_symbols
        ]

        return len(orphaned)
    except Exception:
        return 0
```

#### Запускати моніторинг

```python
# fsm.py: в основному loop
async def _monitoring_loop(self):
    """Monitor order limits and health."""
    while True:
        try:
            await asyncio.sleep(60)  # Every minute
            await self.check_order_limit()
        except Exception as e:
            LOG.error(f"Monitoring loop error: {e}")
```

---

## 📋 РЕАЛІЗАЦІЙНИЙ CHECKLIST

- [ ] **1.1** Додати `bracket_order_tracking` mapping в ExecPosFSM
- [ ] **1.2** Реалізувати `_track_bracket_orders()` method
- [ ] **1.3** Викликати tracking при розміщенні ордерів (fsm.py:500)
- [ ] **1.4** Додати `_emit_close_with_bracket_cancellation()` в CloseFlowFSM
- [ ] **1.5** Модифікувати `_execute_close()` щоб скасовувати SL/TP перед close
- [ ] **2.1** Реалізувати `cleanup_orphaned_bracket_orders()` method
- [ ] **2.2** Додати `_cleanup_loop()` фоновий task
- [ ] **2.3** Запустити cleanup при старті системи
- [ ] **3.1** Реалізувати `check_order_limit()` method
- [ ] **3.2** Додати `_estimate_orphaned_orders()` method
- [ ] **3.3** Реалізувати `_monitoring_loop()` фоновий task
- [ ] **3.4** Додати логування та алерти для 75%+ лімітів
- [ ] **4.0** Написати unit-тести для всіх компонентів
- [ ] **5.0** Тестування на live/testnet з 100+ торгів
- [ ] **6.0** Оновити документацію COMPREHENSIVE_TRADING_SYSTEM_LOGIC.md

---

## 🧪 ТЕСТУВАННЯ

### Unit Test 1: Bracket Tracking
```python
def test_bracket_tracking():
    fsm = ExecPosFSM(...)

    # Track brackets
    fsm._track_bracket_orders(
        entry_order_id="entry_123",
        sl_order_id="sl_456",
        tp_order_id="tp_789",
        symbol="ETHUSDT",
        side="BUY"
    )

    # Retrieve
    brackets = fsm._get_brackets_for_entry("entry_123")
    assert brackets["sl_order_id"] == "sl_456"
    assert brackets["tp_order_id"] == "tp_789"

    # Clean
    fsm._remove_bracket_tracking("entry_123")
    assert fsm._get_brackets_for_entry("entry_123") is None
```

### Unit Test 2: Atomic Close
```python
async def test_atomic_close_with_cancellation():
    close_fsm = CloseFlowFSM()
    close_fsm.exec_pos_fsm = mock_exec_fsm

    messages = close_fsm._emit_close_with_bracket_cancellation(
        msg=mock_msg,
        why="test_close",
        details={},
        entry_order_id="entry_123"
    )

    # Should return: [DEC:CLOSE, DEC:CANCEL_SL, DEC:CANCEL_TP]
    assert len(messages) == 3
    assert messages[0].verb == "CLOSE"
    assert messages[1].verb == "CANCEL_ORDER"
    assert messages[2].verb == "CANCEL_ORDER"
```

### Integration Test: Live 100+ Trades
```bash
# Run system with monitoring
.venv/Scripts/python.exe -m apps.reference.main

# Monitor order counts
watch -n 5 'tail -20 logs/fsm.log | grep "Open orders"'

# After 100 trades
- Open orders should cycle between 0-6 (not accumulate)
- No orphaned orders reported
- No "Too Many Open Orders" errors
```

---

## 📊 ESPERENCE OUTCOMES

| Метрика | До Фіксу | Після Фіксу |
|---------|----------|------------|
| Accumulation Rate | +2-3 orders/trade | 0 orders/trade ✅ |
| Max Orders After 100 Trades | 180-200 | 6-10 ✅ |
| Cleanup Success Rate | N/A | >99% ✅ |
| System Uptime | ~4-6 hours | Unlimited ✅ |
| Trade Rejections | Frequent | None ✅ |

---

## 🚀 ДЕПЛОЙЄМЕНТ

1. **Local Testing** (1 день)
   - Unit tests 100%
   - Integration test 100+ trades locally

2. **Testnet** (2-3 дні)
   - Запустити систему 24 часа
   - Переконатися що orphaned cleanup дійсно працює
   - Перевірити моніторинг алертів

3. **Production** (rolling)
   - Розвести нову версію з feature flag
   - Моніторити ordem counts first 24h
   - Если все ОК → enable для всіх користувачів

---

**Status:** READY FOR IMPLEMENTATION
**Owner:** Trading Systems Team
**Affects:** All trading systems using bracket orders
**Risk:** LOW (additive, non-breaking)

