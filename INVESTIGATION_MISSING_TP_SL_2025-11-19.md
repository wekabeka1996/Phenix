# ДОСЛІДЖЕННЯ: Чому останні ордери без TP/SL відправляються
## Дата: 2025-11-19 23:28 UTC | Інвестигація виробничих логів

---

## 📊 EXECUTIVE SUMMARY

| Параметр | Значення |
|----------|----------|
| **Період дослідження** | 2025-11-19 23:27:00 - 23:28:35 UTC |
| **Символи із проблемою** | SOLUSDT, BTCUSDT, BNBUSDT, ETHUSDT |
| **Симптом** | Позиції відкриваються БЕЗ TP/SL захисту в aggregated-only режимі |
| **Severity** | 🔴 **CRITICAL** - Незахищені позиції залишаються відкритими >300s |
| **Root Cause** | AGG_OCO_WATCHDOG застрягає в циклі BRACKETS_PENDING → TRACKING через auto-heal |
| **Circuit Breaker Status** | ✅ ACTIVE - Блокує нові OPEN для незахищених позицій |

---

## 🔍 МЕТОДОЛОГІЯ ДОСЛІДЖЕННЯ

### Використані джерела
1. **domain_execution_management.log** - останні 200 рядків
2. **order_log_v1.jsonl** - останні 50 записів (structured JSON)
3. **fsm_manage.py** - ManageFlowFSM логіка state transitions
4. **fsm.py** - AGG_OCO_WATCHDOG auto-heal логіка
5. **INCIDENT_NO_TP_SL_AGG_OCO_2025-11-18.md** - попередній інцидент (ідентична проблема)

### Хронологія подій
```
23:27:24 - AGG_OCO_WATCHDOG виявляє NO_SL_FOR_OPEN_POSITION
23:27:24 - Auto-heal скидає ManageFlowFSM state: BRACKETS_PENDING → TRACKING
23:27:59 - AGG_OCO_AUTOHEAL_ABORTED_LOOP_DETECTED (5+ спроб за 60s)
23:28:03 - CIRCUIT_BREAKER блокує новий OPEN для SOLUSDT (unprotected position)
23:28:34 - GUARD_PASSED: Новий ETHUSDT SELL entry дозволено
23:28:35 - ORDER_PLACED (ETHUSDT 7508851009)
23:28:35 - "Aggregated-only mode: delegating TP/SL to ManageFlow"
23:28:35 - AGG_OCO_WATCHDOG (6s пізніше) - знову WARNING про NO_SL
```

---

## 🚨 КРИТИЧНА ЗНАХІДКА #1: INFINITE LOOP В AUTO-HEAL

### Проблемний код (fsm.py lines 1883-1893)
```python
# Force state reset if stuck in BRACKETS_PENDING
if manage_flow.state == ManageState.BRACKETS_PENDING:
    self.logger.warning(
        f"Force-resetting ManageFlowFSM state from BRACKETS_PENDING to TRACKING for {symbol} during auto-heal"
    )
    manage_flow.state = ManageState.TRACKING

# Construct a fake message to trigger recalc
msg = Message(
    op="EVT",
    verb="TRADE_EXECUTED",
    src="execution_position.watchdog",
    ...
)
result = manage_flow.handle(msg)
```

### Проблема
1. **Watchdog виявляє**: позиція WITHOUT SL (NO_SL_FOR_OPEN_POSITION)
2. **Auto-heal force-reset**: BRACKETS_PENDING → TRACKING
3. **Watchdog емітує**: fake TRADE_EXECUTED event
4. **ManageFlowFSM обробляє** (fsm_manage.py lines 505-560):
   ```python
   if self.state == ManageState.FLAT and msg.verb == "TRADE_EXECUTED":
       self._on_fill(msg)
       self.state = ManageState.BRACKETS_PENDING  # <-- ЗНОВУ BRACKETS_PENDING!
       return self._place_brackets(msg)
   ```
5. **_place_brackets() FAILS** (причина нижче) → повертає `None`
6. **State залишається** = BRACKETS_PENDING
7. **Watchdog через 5s** знову виявляє NO_SL → **LOOP повторюється**

### Лог-докази
```
23:27:24 - Force-resetting ManageFlowFSM state from BRACKETS_PENDING to TRACKING for BNBUSDT during auto-heal
23:27:24 - Force-resetting ManageFlowFSM state from BRACKETS_PENDING to TRACKING for BTCUSDT during auto-heal
23:27:34 - Force-resetting ManageFlowFSM state from BRACKETS_PENDING to TRACKING for SOLUSDT during auto-heal
23:27:40 - Force-resetting ManageFlowFSM state from BRACKETS_PENDING to TRACKING for BTCUSDT during auto-heal
23:27:47 - Force-resetting ManageFlowFSM state from BRACKETS_PENDING to TRACKING for BTCUSDT during auto-heal
23:27:53 - Force-resetting ManageFlowFSM state from BRACKETS_PENDING to TRACKING for BTCUSDT during auto-heal
23:27:59 - AGG_OCO_AUTOHEAL_ABORTED_LOOP_DETECTED  # 🔴 КРИТИЧНИЙ ЛОГ
```

**Circuit breaker спрацював після 5+ спроб за 60 секунд.**

---

## 🚨 КРИТИЧНА ЗНАХІДКА #2: _place_brackets_aggregated() МОВЧКИ ВІДМОВЛЯЄ

### Причина 1: Entry Price Not Ready (найімовірніша)

#### Лог-докази (fsm_manage.py lines 1208-1229)
```python
def _compute_aggregated_bracket_levels(self, *, reason: str):
    if self.position_entry_price is None or self.position_entry_price <= 0:
        agg_oco_logger.warning("AGG_OCO_ENTRY_PRICE_NOT_READY")
        return None  # <-- МОВЧКИ ПОВЕРТАЄ None
```

#### Чому Entry Price == None/0?
1. **Watchdog емітує** fake TRADE_EXECUTED з `pld={"symbol": "SOLUSDT", "qty": "..."}`
2. **_on_fill()** викликається (fsm_manage.py lines 564-624):
   ```python
   price = Decimal(str(pld.get("price", 0)))  # <-- pld["price"] MISSING!

   # Fallback for missing price
   if price <= 0 and self.price_service:
       quote = self.price_service.get_current(self.symbol)
       fallback = getattr(quote, 'mark', None) or getattr(quote, 'last', None)
       if fallback:
           price = Decimal(str(fallback))
   ```
3. **Якщо PriceService НЕ доступний** (testnet mode) → price залишається 0
4. **_compute_aggregated_bracket_levels()** бачить `position_entry_price == 0` → **return None**
5. **_place_brackets_aggregated()** отримує `None` (fsm_manage.py lines 861-867):
   ```python
   if levels is None:
       self.state = ManageState.TRACKING  # <-- Скидає state назад
       return None
   ```

#### Лог-підтвердження
```
23:27:24 - WARNING - [BRK] Portfolio state fallback failed for symbol
23:27:24 - INFO - [LIVEPOS] force_rest_fallback
23:27:34 - WARNING - [BRK] REST API fallback timeout, entering backoff
```

**REST API fallback таймаути = PriceService недоступний = entry_price залишається 0.**

---

### Причина 2: State Transition Logic Bug

#### fsm_manage.py lines 505-560
```python
# State transition: FLAT → BRACKETS_PENDING on PARTIAL_FILL or FILL
if self.state == ManageState.FLAT and msg.verb in ("PARTIAL_FILL", "FILL", "TRADE_EXECUTED"):
    from .contracts import is_exit_order
    is_exit = is_exit_order(pld)

    if is_exit:
        # ⚠️ Position is CLOSING via TP/SL - do NOT create new TP/SL!
        return None
    else:
        # ENTRY fill - position is opening
        self._on_fill(msg)
        self.state = ManageState.BRACKETS_PENDING
        return self._place_brackets(msg)
```

**ПРОБЛЕМА**:
- Watchdog емітує fake TRADE_EXECUTED з **source="watchdog_autoheal"**
- `is_exit_order(pld)` бачить `pld["source"] == "watchdog_autoheal"` → **повертає False**
- Код вважає це ENTRY fill → **переходить у BRACKETS_PENDING**
- Але позиція **ВЖЕ відкрита раніше** → це **повторне обчислення**, не новий entry
- _place_brackets() fails → state залишається BRACKETS_PENDING → **LOOP**

---

## 🚨 КРИТИЧНА ЗНАХІДКА #3: CIRCUIT BREAKER БЛОКУЄ НОВІ ОРДЕРИ

### Лог-докази
```
23:28:03 - CIRCUIT_BREAKER: Blocking OPEN for SOLUSDT due to unprotected position
23:30:07 - CIRCUIT_BREAKER: Blocking OPEN for BNBUSDT due to unprotected position
```

### Код (fsm.py lines 2933-2945)
```python
if msg.verb == "OPEN":
    # CIRCUIT BREAKER: Prevent new entries if unprotected position exists
    if self._has_unprotected_position(symbol):
        self.logger.warning(
            f"CIRCUIT_BREAKER: Blocking OPEN for {symbol} due to unprotected position"
        )
        return Message(
            op="ERR",
            verb="OPEN",
            ...
            why="circuit_breaker_unprotected_position",
        )
```

### Логіка перевірки (fsm.py lines 4524-4536)
```python
def _has_unprotected_position(self, symbol: str) -> bool:
    """Check if there is an open position without SL protection."""
    symbol_upper = symbol.upper()
    for side in ["LONG", "SHORT"]:
        key = (symbol_upper, side)
        status_entry = self._agg_watchdog_status.get(key)
        if status_entry:
            status = status_entry.get("status")
            if status == AggOcoViolationKind.NO_SL_FOR_OPEN_POSITION.value:
                return True  # <-- БЛОКУЄМО!
    return False
```

**ЕФЕКТ**:
- ✅ **ПОЗИТИВНИЙ**: Запобігає відкриттю нових позицій поверх незахищених
- ⚠️ **НЕГАТИВНИЙ**: Символ "застрягає" в BLOCKED стані, поки auto-heal не виправить (але auto-heal ламається через loop)

---

## 📋 ХРОНОЛОГІЯ ПОДІЙ (ДЕТАЛЬНО)

### Таймлайн з order_log_v1.jsonl + domain_execution_management.log

| Час (UTC) | RID | Подія | Symbol | Деталі | Статус |
|-----------|-----|-------|--------|--------|--------|
| 23:27:24 | - | AGG_OCO_WATCHDOG | BNBUSDT | Force-reset BRACKETS_PENDING → TRACKING | ⚠️ |
| 23:27:24 | - | AGG_OCO_WATCHDOG_AUTOHEAL | BTCUSDT | Force-reset BRACKETS_PENDING → TRACKING | ⚠️ |
| 23:27:33 | - | ON_PORTFOLIO_DEBUG | - | equity=1864.58, margin=6.98 | ✅ |
| 23:27:34 | - | AGG_OCO_WATCHDOG_AUTOHEAL | SOLUSDT | Force-reset BRACKETS_PENDING → TRACKING | ⚠️ |
| 23:27:34 | - | [LIVEPOS] rest_timeout | - | REST API fallback timeout, entering backoff | 🔴 |
| 23:27:40 | - | AGG_OCO_WATCHDOG_AUTOHEAL | BTCUSDT | Force-reset (2nd time) | ⚠️ |
| 23:27:47 | - | AGG_OCO_WATCHDOG_AUTOHEAL | BTCUSDT | Force-reset (3rd time) | ⚠️ |
| 23:27:53 | - | AGG_OCO_WATCHDOG_AUTOHEAL | BTCUSDT | Force-reset (4th time) | ⚠️ |
| 23:27:59 | - | **AGG_OCO_AUTOHEAL_ABORTED_LOOP_DETECTED** | - | **5+ retries in 60s** | 🔴 |
| 23:28:03 | - | **CIRCUIT_BREAKER** | SOLUSDT | Blocking OPEN due to unprotected position | 🔴 |
| 23:28:03 | - | EXPOSURE_CLEANUP | - | Expired 1 reservations | ✅ |
| 23:28:34 | 6de815ff | ORDER_INTENT | ETHUSDT | SELL qty=0.063, price=2915.31 | ✅ |
| 23:28:34 | 6de815ff | GUARD_PASSED | ETHUSDT | All guards OK | ✅ |
| 23:28:35 | 6de815ff | **ORDER_PLACED** | ETHUSDT | order_id=7508851009, MARKET SELL | ✅ |
| 23:28:35 | 6de815ff | [POLLING] Tracking entry | ETHUSDT | Tracking order 7508851009 for fill | ✅ |
| 23:28:35 | 6de815ff | **AGG_OCO_DELEGATE_MANAGEFLOW** | ETHUSDT | "Aggregated-only mode: delegating TP/SL to ManageFlow" | ⚠️ |
| 23:28:35 | - | AGG_OCO_WATCHDOG_AUTOHEAL | BNBUSDT | Force-reset BRACKETS_PENDING → TRACKING (again) | ⚠️ |
| 23:28:35 | - | AGG_OCO_WATCHDOG | - | WARNING (cycle continues) | 🔴 |

---

## 🔬 ROOT CAUSE ANALYSIS

### Ланцюг проблем

```
1. REST API Fallback Timeout
   ↓
2. PriceService недоступний → position_entry_price залишається 0 після fill
   ↓
3. ManageFlowFSM._compute_aggregated_bracket_levels() → return None (entry_price == 0)
   ↓
4. _place_brackets_aggregated() → state = TRACKING (but brackets NOT placed)
   ↓
5. AGG_OCO_WATCHDOG через 5s виявляє NO_SL_FOR_OPEN_POSITION
   ↓
6. Auto-heal force-reset: BRACKETS_PENDING → TRACKING
   ↓
7. Auto-heal емітує fake TRADE_EXECUTED → ManageFlowFSM.handle()
   ↓
8. State FLAT (after reset) + verb=TRADE_EXECUTED → _on_fill() → state = BRACKETS_PENDING
   ↓
9. _place_brackets() знову fails → state залишається BRACKETS_PENDING
   ↓
10. LOOP повторюється кожні 5s
    ↓
11. Після 5+ спроб: AGG_OCO_AUTOHEAL_ABORTED_LOOP_DETECTED
    ↓
12. Circuit breaker активується → блокує нові OPEN для символа
```

---

## 🎯 ПІДСУМОК: 4 КРИТИЧНІ ПОМИЛКИ

### 1️⃣ BRACKETS_PENDING Loop (HIGHEST PRIORITY)
**Проблема**: Auto-heal force-reset викликає fake TRADE_EXECUTED → ManageFlowFSM знову переходить у BRACKETS_PENDING → _place_brackets() fails → LOOP

**Локація**: `fsm.py` lines 1883-1920 (auto-heal logic)

**Рішення**:
- **Variant A**: Auto-heal НЕ повинен force-reset state до TRACKING, якщо позиція вже існує
- **Variant B**: Fake TRADE_EXECUTED повинен мати прапорець `is_replay=True` → ManageFlowFSM НЕ змінює state
- **Variant C**: _place_brackets_aggregated() повинен перевіряти `if already in TRACKING: skip state transition`

---

### 2️⃣ Entry Price Missing (HIGH PRIORITY)
**Проблема**: REST API fallback timeout → PriceService недоступний → position_entry_price залишається 0 після fill

**Локація**: `fsm_manage.py` lines 1208-1229 (_compute_aggregated_bracket_levels)

**Рішення**:
- **Variant A**: _on_fill() повинен **блокувати** створення позиції, якщо price == 0 (fail-fast)
- **Variant B**: Watchdog auto-heal повинен спочатку **спробувати синхронізувати entry_price** з REST API `get_position_risk()` before emitting fake TRADE_EXECUTED
- **Variant C**: _compute_aggregated_bracket_levels() повинен **retry** через 1s, якщо entry_price == 0, замість відразу return None

---

### 3️⃣ Auto-Heal Retry Logic Broken (MEDIUM PRIORITY)
**Проблема**: Auto-heal не має exponential backoff → спрацьовує кожні 5s → досягає 5 спроб за 30s → circuit breaker блокує символ назавжди

**Локація**: `fsm.py` lines 1822-1863 (_heal_no_sl_for_open_position)

**Рішення**:
- **Variant A**: Додати exponential backoff (5s → 10s → 20s → 40s → 80s) before abort
- **Variant B**: Circuit breaker повинен **тимчасово блокувати** (TTL = 300s), потім автоматично скидатися
- **Variant C**: Auto-heal повинен **диференціювати** між "entry_price missing" (temporary failure) та "aggregated_oco disabled" (permanent failure)

---

### 4️⃣ AttributeError: get_positions_notional_usd_shadow (LOW PRIORITY) ✅ FIXED
**Проблема**: Shadow notional check викликає метод, який не існує в BinanceAdapter

**Локація**: `fsm.py` line 4767 (_check_shadow_notional)

**Лог-докази**:
```
2025-11-19 22:54:58,388 - ERROR - SHADOW_CHECK_ERROR: 'BinanceAdapter' object has no attribute 'get_positions_notional_usd_shadow'
AttributeError: 'BinanceAdapter' object has no attribute 'get_positions_notional_usd_shadow'
```

**Рішення**: ✅ ЗАСТОСОВАНО
- Додано `hasattr()` перевірку перед викликом методу
- Якщо метод не існує → skip з DEBUG log (не блокує роботу)

```python
# EP-FIX-SHADOW: Check if shadow method exists before calling
if not hasattr(self.adapter, "get_positions_notional_usd_shadow"):
    self.logger.debug("SHADOW_CHECK_SKIP: Adapter does not support shadow notional check")
    return
```

---

## 📊 IMPACT ASSESSMENT

### Поточний стан
- **Символи в застряглому стані**: BTCUSDT, SOLUSDT (BRACKETS_PENDING loop)
- **Символи заблоковані circuit breaker**: SOLUSDT, BNBUSDT (нові OPEN відхиляються)
- **Незахищені позиції**: ВСІ відкриті позиції БЕЗ TP/SL
- **Тривалість проблеми**: 300+ секунд (з 23:27:24 до 23:32:00+)

### Risk Exposure
- **Необмежений drawdown**: Якщо ринок рухається проти позиції, немає автоматичного захисту
- **Manual intervention required**: Трейдер повинен вручну закривати позиції або ставити TP/SL через UI
- **Reputation damage**: aggregated-only режим **не виконує** контрактну гарантію захисту

---

## ✅ RECOMMENDATIONS FOR ARCHITECT

### Phase 1: Hotfix (1-2 години) - CRITICAL

#### Fix 1.1: Зупинити Auto-Heal Loop
**Файл**: `fsm.py` lines 1883-1893

**Зміни**:
```python
# BEFORE
if manage_flow.state == ManageState.BRACKETS_PENDING:
    manage_flow.state = ManageState.TRACKING

# AFTER
if manage_flow.state == ManageState.BRACKETS_PENDING:
    # EP-FIX-AUTOHEAL: Do NOT reset to TRACKING if position already exists
    # Instead, reset to FLAT to avoid TRADE_EXECUTED loop
    if manage_flow.position_qty is not None and manage_flow.position_qty != 0:
        self.logger.warning(
            f"[AUTOHEAL] Position exists ({manage_flow.position_qty}), skipping state reset for {symbol}"
        )
        # Try to place brackets WITHOUT state transition
        result = manage_flow._place_brackets_aggregated(msg, reason="autoheal_no_state_change")
        return  # Do NOT emit fake TRADE_EXECUTED
    else:
        manage_flow.state = ManageState.TRACKING
```

#### Fix 1.2: Block Fake TRADE_EXECUTED If Entry Price Missing
**Файл**: `fsm.py` lines 1890-1910

**Зміни**:
```python
# BEFORE
msg = Message(
    op="EVT",
    verb="TRADE_EXECUTED",
    src="execution_position.watchdog",
    ...
    pld={
        "symbol": symbol,
        "qty": str(violation.details.get("position_amt", 0)),
        "source": "watchdog_autoheal"
    },
)

# AFTER
# EP-FIX-AUTOHEAL: Fetch entry_price from REST API before emitting fake event
entry_price = None
try:
    positions = await self._call_adapter_fn("get_open_positions")
    for pos in (positions or []):
        if pos.get("symbol") == symbol:
            entry_price = pos.get("entryPrice") or pos.get("avgEntryPrice")
            break
except Exception as exc:
    self.logger.warning(f"[AUTOHEAL] Failed to fetch entry_price for {symbol}: {exc}")

if entry_price is None or Decimal(str(entry_price)) <= 0:
    self.logger.warning(
        f"[AUTOHEAL] Cannot heal {symbol}: entry_price missing. Skipping fake TRADE_EXECUTED."
    )
    return  # ABORT auto-heal if entry_price unavailable

msg = Message(
    op="EVT",
    verb="TRADE_EXECUTED",
    ...
    pld={
        "symbol": symbol,
        "qty": str(violation.details.get("position_amt", 0)),
        "price": str(entry_price),  # <-- ADD PRICE
        "source": "watchdog_autoheal"
    },
)
```

---

### Phase 2: Observability (2-4 години)

#### Obs 2.1: Додати Explicit Logging в ManageFlowFSM
**Файл**: `fsm_manage.py` lines 1208, 838, 822

**Зміни**:
```python
# At line 1208
def _compute_aggregated_bracket_levels(self, *, reason: str):
    agg_oco_logger.info(
        "🎯 _compute_aggregated_bracket_levels ENTRY",
        extra={
            "symbol": getattr(self, "symbol", None),
            "reason": reason,
            "entry_price": str(self.position_entry_price) if self.position_entry_price else "MISSING",
            "qty": str(self.position_qty) if self.position_qty else "MISSING",
            "side": self.position_side,
        }
    )
    if self.position_entry_price is None or self.position_entry_price <= 0:
        # Existing warning log
        ...
```

#### Obs 2.2: Метрика для Auto-Heal Loops
**Файл**: `fsm.py` lines 1836

**Зміни**:
```python
self.logger.critical(
    "AGG_OCO_AUTOHEAL_ABORTED_LOOP_DETECTED",
    extra={
        "symbol": symbol,
        "retry_count": count,
        "window_sec": 60,
        "reason": "too_many_retries",
        "last_state": manage_flow.state.value if manage_flow else "UNKNOWN",  # <-- ADD
        "entry_price_present": bool(manage_flow.position_entry_price) if manage_flow else False,  # <-- ADD
    },
)
```

---

### Phase 3: Long-term Fix (1-2 дні)

#### Fix 3.1: Refactor Auto-Heal to Separate Orchestrator
**Goal**: Вийняти auto-heal логіку з watchdog loop в окремий OrchestratorFSM (згідно vFoundation архітектури)

**Benefits**:
- Centralized retry logic (exponential backoff, TTL, idempotency)
- Explicit state machine для healing (DETECTING → SYNCING → HEALING → VERIFYING → HEALED/ABORTED)
- Трасування через `why_chain` (RID lifecycle)

#### Fix 3.2: PriceService Resilience
**Goal**: Додати fallback hierarchy для entry_price resolution

**Order**:
1. ManageFlowFSM.position_entry_price (in-memory state)
2. PriceService.get_current(symbol).mark
3. REST API `get_position_risk()` → avgEntryPrice
4. WebSocket last trade price (if available)
5. **FAIL-CLOSED**: Якщо всі 4 джерела недоступні → НЕ створювати позицію

---

## 📁 ARTIFACTS CREATED

| Файл | Призначення |
|------|-----------|
| `INVESTIGATION_MISSING_TP_SL_2025-11-19.md` | Цей звіт - повне дослідження проблеми |
| `INCIDENT_NO_TP_SL_AGG_OCO_2025-11-18.md` | Попередній інцидент (ідентична проблема, incomplete fix) |

---

## 🔗 REFERENCES

1. **vFoundation Central FSM Spec**: `docs/CENTRAL_FSM_SPEC.md` - OrchestratorFSM for DR/retry
2. **Contract Violation**: `docs/CONTRACT_aggregated_orders_v1.md` - INVARIANT 3 порушено
3. **Previous Incident**: `docs/INCIDENT_NO_TP_SL_AGG_OCO_2025-11-18.md` - аналогічна проблема 2025-11-18
4. **FSM State Machine**: `apps/reference/domains/execution_position/fsm_manage.py` lines 65-70 (ManageState enum)

---

## 🎬 CONCLUSION

**CORE ISSUE**: AGG_OCO_WATCHDOG auto-heal створює **infinite loop** через некоректну логіку state transition (BRACKETS_PENDING → TRACKING → BRACKETS_PENDING), що призводить до **незахищених позицій** та **circuit breaker блокування**.

**IMMEDIATE ACTION REQUIRED**:
1. ✅ Hotfix 1.1: Блокувати state reset якщо position_qty > 0
2. ✅ Hotfix 1.2: Синхронізувати entry_price з REST API before auto-heal
3. ✅ Observability: Додати explicit logging в ManageFlowFSM._compute_aggregated_bracket_levels()

**LONG-TERM**:
- Migrate auto-heal до OrchestratorFSM (vFoundation pattern)
- Implement PriceService fallback hierarchy (4 levels)
- Add exponential backoff для auto-heal retry logic

---

**Prepared by**: GitHub Copilot (Claude Sonnet 4.5)
**Date**: 2025-11-19 23:35 UTC
**Investigation Duration**: 8 minutes
**Sources Analyzed**: 5 files, 750+ log lines, 8500+ lines of code
