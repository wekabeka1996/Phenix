# 🚨 КРИТИЧНА ПРОБЛЕМА: Накопичення Сирітських TP/SL Ордерів
## Анаіліз та План Рішення

**Статус:** 🔴 CRITICAL | Kan привести до припинення торгівлі
**Дата:** 4 Листопада 2025
**RID:** ORPHANED-ORDERS-P0-T01
**Версія:** 1.0

---

## 📋 ЗМІСТ
1. [Резюме проблеми](#резюме-проблеми)
2. [Детальний опис](#детальний-опис)
3. [Корінь проблеми](#корінь-проблеми)
4. [Сценарії накопичення](#сценарії-накопичення)
5. [Вплив на систему](#вплив-на-систему)
6. [План рішення](#план-рішення)
7. [Деталі реалізації](#деталі-реалізації)

---

## РЕЗЮМЕ ПРОБЛЕМИ

### Одна фраза
**API Binance виокремлює Bracket Order (Market + TP + SL) на 3 окремих ордера. Коли позиція закривається, SL/TP залишаються активними і накопичуються до ліміту 200, блокуючи нові торгівлі.**

### Ключові факти

| Аспект | Деталь |
|--------|--------|
| **Ліміт Binance** | 200 активних ордерів на акаунт |
| **Ордери на торгівлю** | 3 окремих: 1 Market/Limit + 1 SL + 1 TP |
| **Проблема** | SL/TP залишаються після закриття позиції |
| **Наслідок** | Після ~65 позицій (195 ордерів) - нові торгівлі блокуються |
| **Критичність** | CRITICAL - система припиняє роботу |

---

## ДЕТАЛЬНИЙ ОПИС

### 1. Як Працює Ручний Інтерфейс

На веб-інтерфейсі Binance це виглядає як ONE ордер:

```
┌─────────────────────────┐
│   BRACKET ORDER         │
├─────────────────────────┤
│ Entry: Market BUY       │
│   └─ Quantity: 2.5 ETH  │
├─────────────────────────┤
│ Take Profit: SELL       │
│   └─ Price: $1,010      │
├─────────────────────────┤
│ Stop Loss: SELL         │
│   └─ Price: $995        │
└─────────────────────────┘

     [Place Bracket Order]

┌─────────────────────────┐
│  DISPLAY: 1 ORDER       │
│  Status: Brackets Set   │
│  SL: $995 | TP: $1,010  │
└─────────────────────────┘
```

**У вкладці "Orders" виглядає як 1 залежний ордер**

---

### 2. Як Працює API

Через REST API або WebSocket Binance приймає це як:

```
┌──────────────────────────────────┐
│  REQUEST: 3 Окремих Операцій     │
├──────────────────────────────────┤
│ 1. Market BUY 2.5 ETH            │
│    → order_id: "abc123"          │
│    Status: PENDING → FILLED       │
│                                   │
│ 2. Stop Loss SELL 2.5 ETH @ $995  │
│    → order_id: "def456"          │
│    Status: PENDING (waiting)     │
│                                   │
│ 3. Take Profit SELL 2.5 ETH @ $1010
│    → order_id: "ghi789"          │
│    Status: PENDING (waiting)     │
└──────────────────────────────────┘

┌──────────────────────────────────┐
│  BINANCE ACCOUNT STATUS           │
│  Active Orders Count: 3           │
│  ├─ abc123 (FILLED)              │
│  ├─ def456 (PENDING)    ← SL     │
│  └─ ghi789 (PENDING)    ← TP     │
└──────────────────────────────────┘
```

**У API це 3 ОКРЕМІ ОРДЕРИ**

---

### 3. Закриття Позиції: Проблемна Логіка

#### СЦЕНАРІЙ A: TP Заповнюється Перший

```
┌────────────────────────────────────────┐
│ Ціна досягає $1,010                    │
├────────────────────────────────────────┤
│ TP Ордер (ghi789): PENDING → FILLED ✅ │
├────────────────────────────────────────┤
│ BINANCE ROBUSTNESS: Автоматично        │
│ скасовує SL ордер (def456) ✅          │
├────────────────────────────────────────┤
│ РЕЗУЛЬТАТ ДОБРЕ: Обидва скасовані      │
│ Active Orders Now: 1 (збільшив за def456)
└────────────────────────────────────────┘
```

✅ **У цьому випадку Binance ОС скасовує залежний ордер**

---

#### СЦЕНАРІЙ B: Позиція Закривається DEC:CLOSE

```
┌────────────────────────────────────────┐
│ CloseFlowFSM емітує DEC:CLOSE          │
├────────────────────────────────────────┤
│ Система виконує: Закрити позицію       │
│                                        │
│ ЦЕ ОЗНАЧАЄ:                           │
│ → Основний ордер (abc123) уже FILLED  │
│   (позиція вже вищена за вхід)        │
│                                        │
│ → TP (ghi789): STILL PENDING ❌        │
│ → SL (def456): STILL PENDING ❌        │
├────────────────────────────────────────┤
│ ⚠️  ПРОБЛЕМА:                          │
│ DEC:CLOSE НЕ скасовує SL/TP!          │
│ Обидва залишаються в Active Orders     │
└────────────────────────────────────────┘
```

❌ **Система НЕ скасовує дужки при DEC:CLOSE**

---

#### СЦЕНАРІЙ C: Користувач Вручну Закриває

```
┌────────────────────────────────────────┐
│ Користувач на веб-інтерфейсі закриває  │
│ позицію ВРУЧНУ (тап на X)              │
├────────────────────────────────────────┤
│ Binance ОС:                            │
│ 1. Скасовує SL ордер                   │
│ 2. Скасовує TP ордер                   │
│ 3. Розміщує Market Close               │
│                                        │
│ РЕЗУЛЬТАТ: Все чисто ✅               │
└────────────────────────────────────────┘
```

✅ **Ручне закриття працює, але система з API - НІ**

---

### 4. Накопичення Сирітських Ордерів

```
Сесія з 100 торгівель:

Торгівля #1:  Market (✓) + SL (✓) + TP (✓) = 3 ордери
              Закривається: TP заповнюється → SL скасується ✅
              Залишилось: 0 orphaned

Торгівля #2:  Market (✓) + SL (✓) + TP (✓) = 3 ордери
              Закривається: DEC:CLOSE → SL/TP НЕ скасуються ❌
              Залишилось: 2 orphaned

Торгівля #3:  Market (✓) + SL (✓) + TP (✓) = 3 ордери
              Закривається: DEC:CLOSE → SL/TP НЕ скасуються ❌
              Залишилось: 4 orphaned (2+2)

...

Торгівля #65: Market (✓) + SL (✓) + TP (✓) = 3 ордери
              TOTAL ACTIVE: ~65×3 = 195 ордерів

Торгівля #66: СИСТЕМНА ПОМИЛКА! ❌
              → API повертає: "Order count limit exceeded"
              → НОВІ ТОРГІВЛІ НЕМОЖЛИВІ
              → СИСТЕМА ПРИПИНЯЄ РОБОТУ
```

**Крах після ~65-70 позицій!**

---

## КОРІНЬ ПРОБЛЕМИ

### Де Саме Проблема в Коді?

#### 1. `fsm_manage.py` - Розміщення Дужок

```python
def _place_brackets(self, msg: Message) -> Message:
    """Place SL and TP bracket orders after entry fill."""
    # Разміщує SL (order_id="def456")
    # Разміщує TP (order_id="ghi789")
    return Message(
        op="DEC",
        verb="PLACE_ORDER",
        pld={
            "symbol": "ETHUSDT",
            "sl_order_id": "def456",  # ← Зберігається локально
            "tp_order_id": "ghi789",  # ← Зберігається локально
        }
    )
```

**Дужки розміщуються і ID зберігається в FSM.**

---

#### 2. `fsm_manage.py` - Спроба OCO (НЕПОВНА)

```python
def _check_rules(self, msg: Message) -> Optional[Message]:
    """Проверить if SL/TP filled."""

    # Коли SL заповнюється
    if msg.verb == "ORDER_UPDATED" and msg.pld.get("order_id") == self.sl_order_id:
        if msg.pld.get("status") == "FILLED":
            # Скасовує TP ✅
            return self._emit_cancel_order(msg, self.tp_order_id, "OCO_SL_filled")

    # Коли TP заповнюється
    if msg.verb == "ORDER_UPDATED" and msg.pld.get("order_id") == self.tp_order_id:
        if msg.pld.get("status") == "FILLED":
            # Скасовує SL ✅
            return self._emit_cancel_order(msg, self.sl_order_id, "OCO_TP_filled")
```

**OCO логіка є, але НЕПОВНА:**
- ✅ Коли один з дужок заповнюється → скасовує іншу
- ❌ **Коли основна позиція закривається іншим способом → обидва залишаються**

---

#### 3. `fsm_close.py` - Закриття (НЕДОСТАТНЬО)

```python
def _emit_close(self, msg: Message, why: str, details: Dict[str, Any]) -> Message:
    """Generate DEC:CLOSE with reduce_only=true."""

    # Емітує DEC:CLOSE для закриття позиції
    dec = Message(
        op="DEC",
        verb="CLOSE",
        pld={"reduce_only": True, **details},
    )

    # ⚠️  ПРОБЛЕМА: НЕ скасовує SL/TP!
    # Коли позиція закривається, дужки залишаються висіти

    self.position_active = False
    return dec
```

**DEC:CLOSE емітується, але дужки не скасовуються!**

---

#### 4. `fsm.py` - Оркестрація (НЕ СИНХРОНІЗОВАНА)

```python
class ExecPosFSM:
    """Wrapper FSM for execution_position."""

    def __init__(self):
        self.open_flow = OpenFlowFSM()
        self.manage_flow = ManageFlowFSM()  # Розміщує дужки
        self.close_flow = CloseFlowFSM()    # Закриває позицію

        # ⚠️  ПРОБЛЕМА:
        # manage_flow знає про SL/TP ID
        # close_flow емітує DEC:CLOSE
        # НІ ОДИН НЕ СКАСОВУЄ ДУЖКИ!
```

**Жодна логіка не видаляє дужки при закритті.**

---

### Корінь Причини

| Компонент | Відповідальність | Факт | Результат |
|-----------|------------------|------|-----------|
| OpenFlow | Розмістити основний ордер | ✅ Делает | OK |
| ManageFlow | Розмістити дужки (SL/TP) | ✅ Делает | OK |
| ManageFlow | Скасувати одну дужку якщо інша заповнена | ✅ Делает (частково) | Partial |
| CloseFlow | Закрити позицію | ✅ Делает | OK |
| **??** | **Скасувати ОБИДВА дужки при закритті** | ❌ **НІКТО НЕ ДЕЛАЕТ** | **❌ BUG** |

---

## СЦЕНАРІЇ НАКОПИЧЕННЯ

### Сценарій 1: Норма з OCO (Рідко)

```
T=0:   DEC:OPEN → Market BUY
T=1:   Order FILLED → DEC:PLACE_ORDER (SL, TP)
T=2:   SL/TP розміщені
...
T=100: TP ціна досягнута → TP FILLED
       ManageFlow скасовує SL ✅
       Позиція закрита
Active Orders: -2 (SL+TP скасовані)
Накопичення: НІ ✅
```

✅ **Все добре, коли один з дужок заповнюється перший**

---

### Сценарій 2: Проблемний - DEC:CLOSE

```
T=0:   DEC:OPEN → Market BUY
T=1:   Order FILLED → DEC:PLACE_ORDER (SL, TP)
T=2:   SL/TP розміщені
...
T=50:  CloseFlowFSM: max_hold_sec досягнут
       → DEC:CLOSE еміітує
       → Позиція закривається

⚠️  ПРОБЛЕМА:
       SL (order_id: def456) - НЕ СКАСОВАНИЙ ❌
       TP (order_id: ghi789) - НЕ СКАСОВАНИЙ ❌

Active Orders: +2 (orphaned)
Накопичення: ЧЕ ЛІЧИЛОСЬ (+2 за торгівлю)
```

❌ **Дужки залишилися активними, ніхто їх не скасовує**

---

### Сценарій 3: TIMEOUT або ERROR

```
T=0:   DEC:OPEN → Market BUY
T=1:   Order Timeout (не заповнений за 60 сек)
       → Система скасовує основний ордер

⚠️  ПРОБЛЕМА:
       Розміщені дужки може не розміщені (бо основний не FILLED)
       АБО розміщені, але основний НИКОГДА не заповнився
       → SL/TP залишаються в бан ❌

Active Orders: +2 (orphaned)
Накопичення: ГІРШЕ - вони ніколи не будуть заповнені!
```

❌ **Дужки розміщені від основного ордера, який ніколи не заповнилося**

---

## ВПЛИВ НА СИСТЕМУ

### Часова Шкала Крашу

```
Час Роботи    Торгівель    Активних Ордерів    Статус
─────────────────────────────────────────────────────────
0 год         0            0                   ✅ OK
1 год         30           ~90                 ✅ OK (потоко від наслідків)
2 год         60           ~180                ⚠️  WARNING (близько до ліміту!)
2.5 год       70           ~210                🔴 CRASH! (Over limit)

После 2.5 часов безперерывной торгівлі: КОЛАПС
```

### Помилка, яка буде видна

```json
{
  "code": -1013,
  "msg": "Order count limit exceeded"
}
```

```
ERROR: Cannot place order - active order count = 210 (limit 200)
CRITICAL: Trading halted - system cannot place new orders
WARNING: 10 orphaned TP/SL orders detected
```

### Наслідки

1. **Імедіатні**:
   - ✅ Нові ордери НЕ можуть бути розміщені
   - ✅ Система випромінює помилку при DEC:OPEN
   - ✅ **Торгівля ПРИПИНЯЄТЬСЯ**

2. **Довгострокові**:
   - ✅ Потребує ручного втручання для скасування orphaned ордерів
   - ✅ Потребує рестарту системи
   - ✅ Потебує ручного очищення Binance акаунту

3. **Фінансові**:
   - ✅ Потенційні збитки від незакритих позицій
   - ✅ Упущена прибутковість під час простоїв

---

## ПЛАН РІШЕННЯ

### Фаза 1: Негайне (P0) - Запобігання

#### 1.1 Скасування Дужок при DEC:CLOSE

**Файл**: `fsm_close.py`
**Зміна**: `_emit_close()` метод

```python
def _emit_close(self, msg: Message, why: str, details: Dict[str, Any]) -> Message:
    """Generate DEC:CLOSE with bracket cleanup."""

    # ✅ NEW: Return TWO messages:
    # 1. Cancel SL
    if self.sl_order_id:
        cancel_sl = Message(
            op="DEC",
            verb="CANCEL_ORDER",
            pld={"order_id": self.sl_order_id, "reason": "position_closing"}
        )
        # emit or batch

    # 2. Cancel TP
    if self.tp_order_id:
        cancel_tp = Message(
            op="DEC",
            verb="CANCEL_ORDER",
            pld={"order_id": self.tp_order_id, "reason": "position_closing"}
        )
        # emit or batch

    # 3. Close position (reduce_only)
    dec_close = Message(
        op="DEC",
        verb="CLOSE",
        pld={"reduce_only": True, **details}
    )

    return [cancel_sl, cancel_tp, dec_close]  # ← Return all 3
```

---

#### 1.2 Скасування Дужок при ERROR

**Файл**: `fsm_manage.py`
**Місце**: `handle()` метод при REJECTED/EXPIRED основного ордера

```python
def handle(self, msg: Message) -> Optional[Message]:
    # Коли основний ордер REJECTED
    if msg.verb == "REJECTED":
        # ✅ NEW: Скасувати дужки якщо вони були розміщені
        if self.sl_order_id or self.tp_order_id:
            return self._emit_cleanup_brackets(msg)
```

---

#### 1.3 Метрика: Рахування Активних Ордерів

**Файл**: `binance_execution_adapter.py`
**Метод**: `get_open_orders_count()`

```python
def get_open_orders_count(self) -> int:
    """Get current active order count on Binance."""
    try:
        resp = self._request("GET", "/fapi/v1/allOpenOrders", {})
        orders = json.loads(resp.text)
        count = len(orders)

        # ✅ Alert если близко к лімиту
        if count >= 180:
            logger.critical(f"🚨 Order count WARNING: {count}/200")
            # Emit metric or alert

        return count
    except Exception as e:
        logger.error(f"Failed to get order count: {e}")
        return -1
```

---

### Фаза 2: Коротка (P0) - Моніторинг

#### 2.1 Watchdog для Orphaned Ордерів

**Файл**: `execution_position/watchdog.py` (новий)

```python
class OrphanedOrdersWatchdog:
    """Monitor and cleanup orphaned SL/TP orders."""

    async def run_cleanup_loop(self):
        """Run every 60 seconds."""
        while True:
            try:
                # Get all open orders
                all_orders = await self.adapter.get_open_orders()

                # Get all active positions
                positions = await self.adapter.get_positions()

                # Find orphaned orders
                orphaned = self._find_orphaned(all_orders, positions)

                if orphaned:
                    logger.warning(f"Found {len(orphaned)} orphaned orders")
                    # Cancel them
                    for order in orphaned:
                        await self.adapter.cancel_order(order["orderId"])
                        logger.info(f"Cancelled orphaned order {order['orderId']}")

                # Wait 60 seconds
                await asyncio.sleep(60)
            except Exception as e:
                logger.error(f"Watchdog error: {e}")
                await asyncio.sleep(10)

    def _find_orphaned(self, all_orders, positions) -> list:
        """Find orders that don't belong to active positions."""
        position_symbols = {p["symbol"] for p in positions}

        orphaned = []
        for order in all_orders:
            # If order is for a symbol with NO position, it's orphaned
            if order["symbol"] not in position_symbols:
                orphaned.append(order)

        return orphaned
```

---

#### 2.2 Метрики

**Файл**: `telemetry/metrics.py`

```python
# Track active order count
active_orders_gauge = Gauge(
    'trading_active_orders',
    'Current active orders on exchange',
    ['exchange']
)

# Track orphaned orders detected
orphaned_orders_total = Counter(
    'trading_orphaned_orders_total',
    'Total orphaned orders detected and cleaned',
    ['exchange']
)

# Track cancellations
orders_cancelled_total = Counter(
    'trading_orders_cancelled_total',
    'Total orders cancelled',
    ['reason']
)
```

---

### Фаза 3: Середня (P1) - Архітектурна Перебудова

#### 3.1 Bracket Order Управління як Атомарна Одиниця

**Концепція**: Замість управління SL/TP окремо, управляти їх як группу

```python
class BracketOrderGroup:
    """Represents a group of bracket orders (main + SL + TP)."""

    def __init__(self, main_order_id: str, sl_order_id: str, tp_order_id: str):
        self.main_order_id = main_order_id
        self.sl_order_id = sl_order_id
        self.tp_order_id = tp_order_id
        self.state = "PENDING"  # PENDING, PARTIAL_FILLED, ONE_FILLED, CLOSED

    def mark_closed(self):
        """Mark group as closed - cancels remaining orders."""
        # Cancel all remaining
        self.state = "CLOSED"
        return [self.sl_order_id, self.tp_order_id]  # Return IDs to cancel
```

**Файл**: `execution_position/bracket_group.py` (новий)

---

#### 3.2 OrderIndex Розширення

**Файл**: `execution_position/order_index.py`

```python
class OrderIndex:
    """Index for tracking orders and bracket relationships."""

    def __init__(self):
        self.order_to_symbol: Dict[str, str] = {}
        self.bracket_groups: Dict[str, BracketOrderGroup] = {}
        self.symbol_positions: Dict[str, list] = {}

    def register_bracket_group(self, symbol: str, group: BracketOrderGroup):
        """Register a new bracket group."""
        self.bracket_groups[group.main_order_id] = group
        self.order_to_symbol[group.sl_order_id] = symbol
        self.order_to_symbol[group.tp_order_id] = symbol

    def get_orphaned_orders(self, symbol: str) -> list:
        """Get all orphaned orders for a symbol."""
        return [
            order_id for order_id, sym in self.order_to_symbol.items()
            if sym == symbol and order_id not in active_positions
        ]
```

---

## ДЕТАЛІ РЕАЛІЗАЦІЇ

### Крок 1: Виправити fsm_close.py

```python
# BEFORE:
def _emit_close(self, msg: Message, why: str, details: Dict[str, Any]) -> Message:
    self._metrics["fsm_close_decisions_total"] += 1
    dec = Message(
        op="DEC",
        verb="CLOSE",
        src=msg.dst,
        dst="execution_position",
        rid=msg.rid,
        why=why[:80],
        idempotent_key=f"{msg.rid}_{why}_{int(time.time())}",
        pld={"reduce_only": True, **details},
    )
    self.state = CloseState.DONE
    self.position_active = False
    return dec

# AFTER:
def _emit_close(self, msg: Message, why: str, details: Dict[str, Any]) -> list[Message]:
    """Generate DEC:CLOSE with bracket cleanup."""
    messages = []

    # 1. Cancel SL if exists
    if hasattr(self, 'sl_order_id') and self.sl_order_id:
        cancel_sl = Message(
            op="DEC",
            verb="CANCEL_ORDER",
            src=msg.dst,
            dst="execution_position",
            rid=msg.rid,
            why=f"close_cleanup_sl",
            pld={"order_id": self.sl_order_id}
        )
        messages.append(cancel_sl)

    # 2. Cancel TP if exists
    if hasattr(self, 'tp_order_id') and self.tp_order_id:
        cancel_tp = Message(
            op="DEC",
            verb="CANCEL_ORDER",
            src=msg.dst,
            dst="execution_position",
            rid=msg.rid,
            why=f"close_cleanup_tp",
            pld={"order_id": self.tp_order_id}
        )
        messages.append(cancel_tp)

    # 3. Close position
    self._metrics["fsm_close_decisions_total"] += 1
    dec = Message(
        op="DEC",
        verb="CLOSE",
        src=msg.dst,
        dst="execution_position",
        rid=msg.rid,
        why=why[:80],
        idempotent_key=f"{msg.rid}_{why}_{int(time.time())}",
        pld={"reduce_only": True, **details},
    )
    messages.append(dec)

    self.state = CloseState.DONE
    self.position_active = False
    return messages
```

---

### Крок 2: Виправити fsm_manage.py

```python
def handle(self, msg: Message) -> Optional[Message]:
    """Process incoming events."""

    # Handle rejection - cleanup brackets
    if msg.verb == "REJECTED":
        if self.sl_order_id or self.tp_order_id:
            return self._cleanup_brackets_on_error(msg, "entry_rejected")
        return None

    # Handle expiry - cleanup brackets
    if msg.verb == "EXPIRED":
        if self.sl_order_id or self.tp_order_id:
            return self._cleanup_brackets_on_error(msg, "entry_expired")
        return None

    # ... rest of logic ...

def _cleanup_brackets_on_error(self, msg: Message, reason: str) -> Optional[Message]:
    """Cleanup bracket orders when main order fails."""
    if not self.sl_order_id and not self.tp_order_id:
        return None

    messages = []
    if self.sl_order_id:
        messages.append(Message(
            op="DEC",
            verb="CANCEL_ORDER",
            pld={"order_id": self.sl_order_id, "reason": reason}
        ))
    if self.tp_order_id:
        messages.append(Message(
            op="DEC",
            verb="CANCEL_ORDER",
            pld={"order_id": self.tp_order_id, "reason": reason}
        ))

    # Return first cancel (or batch if supported)
    return messages[0] if messages else None
```

---

### Крок 3: Додати Watchdog

Всередину `fsm.py` додати:

```python
class ExecPosFSM:
    def __init__(self, ...):
        # ... existing init ...
        self.watchdog_task = None

    async def start_watchdog(self):
        """Start orphaned order cleanup watchdog."""
        self.watchdog_task = asyncio.create_task(self._watchdog_loop())

    async def _watchdog_loop(self):
        """Periodically cleanup orphaned orders."""
        while self.running:
            try:
                # Every 60 seconds
                await asyncio.sleep(60)

                # Get all open orders from Binance
                all_orders = await self.adapter.get_open_orders()
                active_count = len(all_orders)

                # Log metric
                if active_count >= 180:
                    logger.critical(f"🚨 Order count critical: {active_count}/200")

                # Get all positions
                positions = await self.adapter.get_positions()
                position_symbols = {p["symbol"] for p in positions}

                # Find and cancel orphaned orders
                orphaned_count = 0
                for order in all_orders:
                    # If order is for a symbol without active position
                    if order["symbol"] not in position_symbols:
                        # Check if it's old enough to be orphaned (>2 minutes)
                        age = time.time() - order["time"] / 1000
                        if age > 120:
                            logger.warning(f"Cancelling orphaned order {order['orderId']}")
                            try:
                                await self.adapter.cancel_order(order["orderId"])
                                orphaned_count += 1
                            except Exception as e:
                                logger.error(f"Failed to cancel {order['orderId']}: {e}")

                if orphaned_count > 0:
                    logger.info(f"Cleaned up {orphaned_count} orphaned orders")

            except Exception as e:
                logger.error(f"Watchdog error: {e}")
```

---

## ТЕСТУВАННЯ

### Unit Tests

```python
def test_close_flow_cancels_brackets():
    """Test that DEC:CLOSE cancels SL/TP."""
    fsm = CloseFlowFSM()
    fsm.sl_order_id = "sl_123"
    fsm.tp_order_id = "tp_456"
    fsm.position_active = True

    # Trigger close
    msg = Message(op="UPD", verb="TICK")
    result = fsm._emit_close(msg, "TEST", {})

    # Should return 3 messages: cancel_sl, cancel_tp, close
    assert len(result) == 3
    assert result[0].verb == "CANCEL_ORDER"
    assert result[1].verb == "CANCEL_ORDER"
    assert result[2].verb == "CLOSE"
```

### Integration Test

```python
async def test_orphaned_orders_cleanup():
    """Test that orphaned orders are detected and cleaned."""
    # 1. Create 10 positions
    for i in range(10):
        await place_position()

    # 2. Close 5 of them without cleaning brackets
    for i in range(5):
        await close_position_without_cleanup()

    # 3. Run watchdog
    watchdog = OrphanedOrdersWatchdog()
    orphaned = await watchdog.find_orphaned()

    # Should find 10 orphaned orders (5 positions × 2 brackets)
    assert len(orphaned) == 10

    # 4. Cleanup
    await watchdog.cleanup(orphaned)

    # 5. Verify
    orphaned_after = await watchdog.find_orphaned()
    assert len(orphaned_after) == 0
```

---

## МЕТРИКИ УСПІХУ

| Метрика | Поточне | Цільове | Критерій |
|---------|---------|---------|----------|
| Active Orders (post-close) | +2 per trade | 0 | ✅ 0 orphaned |
| Ліміт Ордерів (при 100 торгівель) | ~300 (ERROR) | <50 | ✅ Under limit |
| Час до Крашу | 2.5 годин | Нескінченність | ✅ Never crash |
| Orphaned Orders Detected | 0 | ~100% | ✅ 100% detection |
| Cleanup Latency | N/A | <5 sec | ✅ Fast cleanup |

---

## ЧАСОВА ШКАЛА

| Фаза | Роботи | Часова Шкала | Пріоритет |
|------|--------|--------------|----------|
| **1** | fsm_close + fsm_manage fixes | 2 дні | P0 CRITICAL |
| **2** | Watchdog + metrics | 2 дні | P0 CRITICAL |
| **3** | Architecture refactor | 5 днів | P1 MEDIUM |
| **4** | Testing + staging | 3 дні | P0 CRITICAL |
| **5** | Deployment | 1 день | P0 CRITICAL |

**TOTAL: ~13 днів для повного рішення**

---

## РЕЗЮМЕ

### Що Відбувається
- API Binance розділяє Bracket Orders на 3 окремих ордера
- SL/TP залишаються активними після закриття позиції
- При ~65 позиціях досягається ліміт 200 ордерів
- Система припиняє роботу - КРАХ

### Рішення
1. **FSM Close**: Скасовує SL/TP при DEC:CLOSE
2. **FSM Manage**: Скасовує дужки при помилці основного ордера
3. **Watchdog**: Моніторить та очищає orphaned ордери кожні 60 сек
4. **Metrics**: Алерти при наближенні до ліміту 200

### Результат
- ✅ Zero orphaned orders
- ✅ Система може працювати нескінченно
- ✅ Нема критичних крашів від ліміту ордерів

---

**Рекомендація**: Почати з PHASE 1 НЕГАЙНО (дн1-2) перед запуском в production.
