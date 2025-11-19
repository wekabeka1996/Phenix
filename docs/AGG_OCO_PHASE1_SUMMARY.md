# AGG_OCO Phase 1: Architecture Context Summary

**Дата:** 19 листопада 2025, 00:48-01:30
**Статус:** ✅ Completed

---

## 1. Аналіз логів виконання

### Timeline подій (з логів)

```
00:49:51 - ExecPosFSM ініціалізовано (aggregated_only_mode)
00:49:51 - OrderGuardian ініціалізовано
00:49:55 - Synchronization з Binance:
           - 3 open orders
           - 3 positions (SOLUSDT: -1.0, ETHUSDT: 0.06, BNBUSDT: 0.2)
00:49:55 - Aggregated OCO watchdog loop started (interval=5s)
00:49:55 - ❌ AGG_OCO_WATCHDOG: 3 WARNING (перше спрацювання)
00:50:01 - ❌ AGG_OCO_WATCHDOG: 3 WARNING
... (повторюється кожні 5-6 секунд)
00:54:05 - Новий ордер BNBUSDT BUY 0.20 розміщено
00:54:05 - ORDER_PLACED: ENTRY-39f3d38c62 (orderId: 1004861116)
```

### Ключові observations:

1. **Watchdog працює в циклі але детектує проблеми**
   - 3 WARNING на кожній ітерації → 3 позиції мають issues
   - Інтервал 5 сек (згідно конфігу)

2. **Exposure Guard працює коректно**
   - `CAN_OPEN_DEBUG` для BNBUSDT: ALLOWED
   - Margin breakdown: open=4.11, pending=0.00, postfill=0.00

3. **OrderGuardian startup reconciliation виконано**
   - Linked existing orders для 4 symbols
   - Cleanup all pending: No pending orders

---

## 2. Архітектура модулів

### Компоненти та зв'язки

```
┌──────────────────────────────────────────────────────────────┐
│                         ExecPosFSM                            │
│  (Orchestrator: координація між flows + watchdog)            │
└───────┬──────────────────────────────────┬──────────────────┘
        │                                   │
        ├─ OpenFlowFSM                      ├─ _agg_oco_watchdog_loop()
        │  (створення entry)                │   └─> validate_agg_oco_invariants()
        │                                   │
        ├─ ManageFlowFSM ◄─────────────────┤
        │  (brackets lifecycle)             │
        │  ├─ _place_brackets_aggregated()  │
        │  ├─ _recalc_aggregated_brackets() │
        │  └─ _on_trade_executed()          │
        │                                   │
        └─ CloseFlowFSM                     │
           (закриття позицій)               │
                                            │
        ┌───────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────────┐
│                      OrderGuardian                           │
│  (Domain wrapper → ServicesGuardian)                        │
│  ├─ register_bracket_set(symbol, side, sl/tp IDs)          │
│  ├─ cleanup_orphans(symbol)                                 │
│  └─ reconcile_symbol(symbol, rid)                           │
└─────────────────────────────────────────────────────────────┘
```

### Критичні контракти

#### 1. **AggOcoViolation** (agg_oco_watchdog.py)
```python
class AggOcoViolationKind:
    NO_SL_FOR_OPEN_POSITION       # Позиція без SL ✅ Це наша проблема!
    ORPHAN_SL_FOR_ZERO_POSITION   # SL без позиції
    MULTIPLE_META_SETS            # Дублі bracket sets
```

#### 2. **BracketSetMeta** (services/order_guardian)
```python
@dataclass
class BracketSetMeta:
    symbol: str
    side: str                # "LONG" | "SHORT"
    sl_order_id: Optional[str]
    tp_order_id: Optional[str]
    bracket_set_id: str
    version: int
    created_ts: float
```

#### 3. **ManageFlowFSM states** (fsm_manage.py)
```python
class ManageState(Enum):
    FLAT = "FLAT"                    # Немає позиції
    TRACKING = "TRACKING"             # Позиція є, brackets встановлено
    BRACKETS_PENDING = "BRACKETS_PENDING"  # Чекаємо ACK для brackets
```

---

## 3. Потік даних: Від Entry до Brackets

```
1. CMD:OPEN (DecisionMaking)
   ├─> ExecPosFSM.handle()
   └─> OpenFlowFSM.handle()
       └─> DEC:OPEN (place market order)

2. EVT:TRADE_EXECUTED (BinanceAdapter WS)
   ├─> ExecPosFSM._on_trade_executed()
   └─> ManageFlowFSM._on_trade_executed()
       ├─ update position_qty, position_entry_price
       ├─ trigger: _place_brackets(reason="entry_fill")
       │   └─> _place_brackets_aggregated()
       │       ├─ _compute_aggregated_bracket_levels()
       │       └─ _place_or_update_bracket_set_from_levels()
       │           ├─ _emit_place_order(SL) → DEC:PLACE_ORDER
       │           ├─ _emit_place_order(TP) → DEC:PLACE_ORDER
       │           └─ _maybe_register_bracket_set()
       │               └─> OrderGuardian.register_bracket_set()
       └─ state = BRACKETS_PENDING

3. EVT:ORDER_ACK (для SL/TP)
   └─> ManageFlowFSM._on_bracket_placed()
       ├─ зберігає order IDs
       └─ state = TRACKING

4. Watchdog (кожні 5 сек)
   ├─ fetch positions + open_orders з біржі
   ├─ fetch bracket_metas з OrderGuardian
   └─ validate_agg_oco_invariants()
       └─> якщо position є але SL/TP нема → WARNING
```

---

## 4. Виявлені критичні точки

### 🔴 Critical Path Issues

#### Issue #1: Race Condition між bracket placement та watchdog
**Локація:** `fsm.py:1472` (`_run_agg_oco_watchdog_once`)

```python
async def _run_agg_oco_watchdog_once(self) -> None:
    # Fetch стану з біржі
    open_orders = await self._call_adapter_fn("get_open_orders", None)
    positions = await self._call_adapter_fn("get_open_positions")

    # Fetch metas з guardian
    metas = self._list_guardian_bracket_sets()

    # ⚠️ RACE: між моментом коли bracket set зареєстровано в guardian
    # та моментом коли ордери дійсно з'являються на біржі проходить 100-500ms
    violations = validate_agg_oco_invariants(...)
```

**Проблема:**
- `_maybe_register_bracket_set()` викликається СИНХРОННО після `_emit_place_order()`
- Але реальний ORDER_ACK приходить асинхронно через 200-500ms
- Watchdog може "побачити" meta БЕЗ відповідних ордерів на біржі

#### Issue #2: Missing bracket registration callback
**Локація:** `fsm_manage.py:1035` (`_maybe_register_bracket_set`)

```python
def _maybe_register_bracket_set(self) -> None:
    if not self._aggregated_only_mode or not self.order_guardian:
        return

    # ⚠️ Викликається одразу після _emit_place_order()
    # але НЕ ЧЕКАЄ на ORDER_ACK!
    meta = self.order_guardian.register_bracket_set(
        symbol=self.symbol,
        side=self._agg_side,
        sl_order_id=None,  # ← NONE! Order ID ще невідомий
        tp_order_id=None,  # ← NONE!
        ...
    )
```

**Проблема:**
- Bracket set реєструється БЕЗ order IDs
- Order IDs встановлюються пізніше в `_on_bracket_placed()`
- Але між цими моментами watchdog може детектувати NO_SL_FOR_OPEN_POSITION

#### Issue #3: Incomplete rehydration logic
**Локація:** `fsm.py:1494` (`_rehydrate_guardian_state`)

```python
def _rehydrate_guardian_state(
    normalized_positions, open_orders, metas, now_ts
) -> None:
    # ⚠️ Викликається watchdog-ом для sync стану
    # Але НЕ створює нові bracket sets якщо їх нема!
    # Тільки оновлює існуючі
```

**Проблема:**
- Watchdog може виявити позицію БЕЗ brackets
- Але auto-heal logic (`_auto_heal_watchdog_violation`) тільки для ORPHAN_SL
- Для NO_SL_FOR_OPEN_POSITION нема авто-виправлення!

#### Issue #4: State desync після partial fills
**Локація:** `fsm_manage.py:1595` (`_recalc_aggregated_brackets`)

```python
def _recalc_aggregated_brackets(self, msg, *, reason: str):
    # Trigger: коли position_qty змінюється

    # ⚠️ Логіка:
    # 1. Cancel старі TP/SL
    # 2. Place нові TP/SL

    # ПРОБЛЕМА: між cancel та place є gap 100-300ms
    # Watchdog може "побачити" позицію БЕЗ brackets
```

---

## 5. Mapping поточного стану на біржі

З логів `order_log_v1.jsonl`:

```json
{
  "rid": "4d520a48-1f48-4039-b0d9-e80ed44563bc",
  "event_type": "ORDER_PLACED",
  "symbol": "BNBUSDT",
  "side": "BUY",
  "quantity": 0.2,
  "client_order_id": "ENTRY-39f3d38c62",
  "order_id": "1004861116"
}
```

### Очікуваний стан (згідно дизайну):

| Symbol   | Position | Side  | Expected Orders         |
|----------|----------|-------|-------------------------|
| SOLUSDT  | -1.0     | SHORT | 1 SL (BUY) + 1 TP (BUY) |
| ETHUSDT  | 0.06     | LONG  | 1 SL (SELL) + 1 TP (SELL) |
| BNBUSDT  | 0.2      | LONG  | 1 SL (SELL) + 1 TP (SELL) |
| **TOTAL**| 3        | —     | **6 orders** |

### Фактичний стан (згідно опису користувача):

| Symbol   | Orders on Exchange       |
|----------|-------------------------|
| BNBUSDT  | 1 TP + 2 SL (❌ дублі?) |
| BTC      | 1 SL (❌ orphan?)       |
| **TOTAL**| **4 orders** |

### Гіпотези проблем:

1. ❌ **SOLUSDT (-1.0 SHORT):** Нема SL/TP взагалі
2. ❌ **ETHUSDT (0.06 LONG):** Нема SL/TP взагалі
3. ❌ **BNBUSDT (0.2 LONG):** Подвійні SL (чому 2?)
4. ❌ **BTC:** Orphan SL (позиція закрита але SL залишився)

---

## 6. Критичні компоненти для детального огляду

### Priority 0 (must investigate):

1. **`ManageFlowFSM._place_brackets_aggregated()`** (fsm_manage.py:818)
   - Чи завжди викликається після entry fill?
   - Чи може бути скіпнута через guards?

2. **`ManageFlowFSM._maybe_register_bracket_set()`** (fsm_manage.py:1035)
   - Timing registration vs ORDER_ACK
   - Order ID propagation

3. **`ExecPosFSM._run_agg_oco_watchdog_once()`** (fsm.py:1472)
   - Fetch sequence: orders → positions → metas
   - Race condition window

4. **`OrderGuardian.register_bracket_set()`** (order_guardian.py)
   - Persistence logic
   - Update vs Insert semantics

### Priority 1 (secondary):

5. **`ManageFlowFSM._recalc_aggregated_brackets()`** (fsm_manage.py:1595)
   - Partial fill trigger conditions
   - Cancel-before-place gap

6. **`OrderGuardian.cleanup_orphans()`**
   - Selection criteria для orphan detection
   - TTL enforcement

---

## 7. Виявлені design smells

### Smell #1: Synchronous registration in async flow
```python
# fsm_manage.py:940
sl_order = self._emit_place_order(...)  # Async via queue
tp_order = self._emit_place_order(...)
self._queue_decision(tp_order)

# Одразу після:
return sl_order  # Message повертається синхронно

# Пізніше (fsm_manage.py:1035):
self._maybe_register_bracket_set()  # Реєстрація БЕЗ order IDs!
```

**Smell:** Mixed sync/async patterns → race conditions

### Smell #2: Watchdog validation без retry logic
```python
# fsm.py:1509
violations = validate_agg_oco_invariants(...)
if not violations:
    return  # ✅ All OK

# ⚠️ Якщо violation знайдено → LOG WARNING
# Але немає back-off/retry для transient issues
```

**Smell:** False positives від timing issues → log spam

### Smell #3: Guardian state managed in two places
```python
# ManageFlowFSM має:
self.sl_price, self.tp_price, self._current_bracket_set_id

# OrderGuardian має:
BracketSetMeta(sl_order_id, tp_order_id, bracket_set_id)
```

**Smell:** Dual source of truth → sync issues

---

## 8. Next steps для Фази 2

1. Парсинг повних логів для відновлення ТОЧНОГО timeline
2. Читання REST API для поточного стану біржі
3. Dump bracket_metas з OrderGuardian memory
4. Correlation RID між ORDER_PLACED та WATCHDOG_WARNING

---

## Summary

✅ **Архітектура зрозуміла:** 3-tier (ExecPosFSM → ManageFlow → Guardian)
❌ **Root cause гіпотеза:** Race між bracket placement та watchdog validation
❌ **Missing auto-heal:** Watchdog детектує NO_SL але не створює brackets
⚠️ **Design weakness:** Mixed sync/async + dual state tracking

**Confidence level:** 70% (потребує верифікації через код та інтеграційні тести)
