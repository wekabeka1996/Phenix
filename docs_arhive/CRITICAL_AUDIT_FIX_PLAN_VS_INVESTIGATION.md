# КРИТИЧНИЙ АУДИТ: Актуальність FIX_PLAN після дослідження 2025-11-19
## Порівняння FIX_PLAN_EXECUTION_POSITION_FSM.md з INVESTIGATION_MISSING_TP_SL_2025-11-19.md

---

## 📊 EXECUTIVE SUMMARY

| Параметр | Значення |
|----------|----------|
| **FIX_PLAN створений** | До інциденту 2025-11-19 23:28 UTC |
| **INVESTIGATION виявив** | 3 нові критичні проблеми (BRACKETS_PENDING loop, entry_price missing, auto-heal broken) |
| **Пріоритети змінилися** | ✅ YES - нові P0 проблеми критичніші за memory leaks |
| **План застарілий** | ⚠️ ЧАСТКОВО - memory leak fixes досі актуальні, але missing critical AGG_OCO fixes |
| **Рекомендація** | 🔴 **ОНОВИТИ ПЛАН** - додати Phase 0 (AGG_OCO hotfixes) ПЕРЕД існуючими фазами |

---

## 🔍 АНАЛІЗ ПО КАТЕГОРІЯХ

### ✅ ЩО ЗАЛИШАЄТЬСЯ АКТУАЛЬНИМ (70% плану)

#### 1. P0: AttributeError при ініціалізації Watchdog ✅ АКТУАЛЬНО
**Статус**: Проблема досі існує (lines 323→4210 forward reference)
**FIX_PLAN рішення**: Lambda binding `lambda d: self._handle_order_timeout(d)`
**Актуальність**: ✅ **ВАЛІДНО** - це orthogonal issue, не пов'язане з AGG_OCO loop

---

#### 2. P1: Витоки пам'яті ✅ АКТУАЛЬНО (але знижено пріоритет)
**Статус**: Всі 6 типів витоків досі існують:
- `_processed_events` (Set) - unbounded growth ✅
- `idempotency_store` - cleanup only on CMD:OPEN ✅
- `_close_position_state` - no cleanup ✅
- `_aggregated_bracket_buffer` - no TTL ✅
- `_exec_error_history` - unbounded deque ✅
- `_autoheal_retry_counts` - no time-window reset ✅

**FIX_PLAN рішення**:
- ✅ **BLOCKER #1** (_processed_events_ts Dict) - ВАЛІДНА РЕАЛІЗАЦІЯ
- ✅ **BLOCKER #2** (idempotency cleanup strategy) - ВАЛІДНА РЕАЛІЗАЦІЯ
- ✅ Bounded deque maxlen=100 - ВАЛІДНО
- ✅ Event-driven cleanup - ВАЛІДНО

**⚠️ КРИТИЧНЕ ЗАУВАЖЕННЯ**:
Memory leaks НЕ є причиною AGG_OCO loop проблеми! Дослідження виявило, що **AGG_OCO infinite loop** критичніший за memory leaks:
- Memory leaks → crash через 7-30 днів
- AGG_OCO loop → **ЗАРАЗ** всі позиції незахищені

**Рекомендація**: Знизити пріоритет memory leak fixes з P1 → P2, підняти AGG_OCO fixes до P0.

---

#### 3. P1: Fire-and-Forget Tasks ✅ АКТУАЛЬНО
**Статус**: Проблема досі існує (lines 1367, 1380, 1405, 1409)
**FIX_PLAN рішення**: `_background_tasks` Set + asyncio.Lock
**Актуальність**: ✅ **ВАЛІДНО** - orthogonal issue

**⚠️ ВАЖЛИВО**: Thread-safety з asyncio.Lock правильна.

---

#### 4. P1: Decimal Unification ✅ АКТУАЛЬНО
**Статус**: 5 різних реалізацій досі існують
**FIX_PLAN рішення**: Incremental migration (Phase 1→2→3)
**Актуальність**: ✅ **ВАЛІДНО** - orthogonal issue

---

#### 5. P2: Shutdown Cleanup ✅ АКТУАЛЬНО
**Статус**: shutdown() не очищає структури
**FIX_PLAN рішення**: Явне `.clear()` після task cancellation
**Актуальність**: ✅ **ВАЛІДНО** - ортогональна проблема

---

### 🔴 ЩО MISSING (30% плану) - CRITICAL GAPS

#### ❌ GAP #1: AGG_OCO BRACKETS_PENDING Infinite Loop (NEW P0)
**Виявлено**: INVESTIGATION 2025-11-19
**Статус**: 🔴 **NOT COVERED** в FIX_PLAN
**Severity**: P0 (BLOCKER) - **критичніше за всі існуючі P0/P1**

**Проблема**:
- Auto-heal force-reset: BRACKETS_PENDING → TRACKING (line 1885)
- Емітує fake TRADE_EXECUTED → ManageFlowFSM.handle()
- State FLAT + verb=TRADE_EXECUTED → state = BRACKETS_PENDING (line 547)
- _place_brackets() fails (entry_price == 0) → state залишається BRACKETS_PENDING
- **LOOP кожні 5s → circuit breaker after 5 retries**

**Рішення** (з Investigation):
```python
# Variant A (рекомендується):
if manage_flow.state == ManageState.BRACKETS_PENDING:
    # EP-FIX-AUTOHEAL: Do NOT reset to TRACKING if position already exists
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

**Вплив**: 🔴 **CRITICAL** - без цього fix система залишається broken в production.

---

#### ❌ GAP #2: Entry Price Missing in Auto-Heal (NEW P0)
**Виявлено**: INVESTIGATION 2025-11-19
**Статус**: 🔴 **NOT COVERED** в FIX_PLAN
**Severity**: P0 (BLOCKER) - **співпричина AGG_OCO loop**

**Проблема**:
- REST API fallback timeout → PriceService недоступний
- Watchdog емітує fake TRADE_EXECUTED **БЕЗ** `pld["price"]`
- _on_fill() → `price = Decimal(str(pld.get("price", 0)))` → **price == 0**
- _compute_aggregated_bracket_levels() → `if entry_price <= 0: return None`
- _place_brackets_aggregated() → state = TRACKING (brackets NOT placed)
- **Позиція залишається unprotected**

**Рішення** (з Investigation):
```python
# fsm.py lines 1890-1910: BEFORE emitting fake TRADE_EXECUTED
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
    ...
    pld={
        "symbol": symbol,
        "qty": str(violation.details.get("position_amt", 0)),
        "price": str(entry_price),  # <-- ADD PRICE
        "source": "watchdog_autoheal"
    },
)
```

**Вплив**: 🔴 **CRITICAL** - без цього fix auto-heal завжди fails.

---

#### ❌ GAP #3: Auto-Heal Exponential Backoff (NEW P1)
**Виявлено**: INVESTIGATION 2025-11-19
**Статус**: 🔴 **NOT COVERED** в FIX_PLAN
**Severity**: P1 (HIGH) - **причина circuit breaker блокування**

**Проблема**:
- Auto-heal retry кожні 5s → 5 спроб за 30s → AGG_OCO_AUTOHEAL_ABORTED_LOOP_DETECTED
- Circuit breaker активується → блокує нові OPEN **назавжди**
- Символ "застрягає" в BLOCKED стані

**Рішення** (з Investigation):
```python
# fsm.py lines 1822-1863: Add exponential backoff
retry_key = f"autoheal_{symbol}"
now = time.time()
count, last_ts = self._autoheal_retry_counts.get(retry_key, (0, 0.0))

# Exponential backoff: 5s → 10s → 20s → 40s → 80s
backoff_sec = min(5 * (2 ** count), 80)
if now - last_ts < backoff_sec:
    self.logger.debug(f"[AUTOHEAL] Backoff active for {symbol} ({backoff_sec}s)")
    return  # Skip healing during backoff

# Reset counter if last attempt was > 60s ago
if now - last_ts > 60.0:
    count = 0

if count >= 5:
    self.logger.critical(
        "AGG_OCO_AUTOHEAL_ABORTED_LOOP_DETECTED",
        extra={
            "symbol": symbol,
            "retry_count": count,
            "reason": "too_many_retries",
            "last_state": manage_flow.state.value,  # <-- NEW
            "entry_price_present": bool(manage_flow.position_entry_price),  # <-- NEW
        }
    )
    return

next_count = count + 1
self._autoheal_retry_counts[retry_key] = (next_count, now)
```

**Вплив**: 🟡 **HIGH** - без цього fix символи blocked після 30s.

---

#### ⚠️ GAP #4: Observability для AGG_OCO Loop (NEW P2)
**Виявлено**: INVESTIGATION 2025-11-19
**Статус**: 🔴 **NOT COVERED** в FIX_PLAN
**Severity**: P2 (MEDIUM) - **діагностика проблеми**

**Проблема**: Немає explicit logging в `_compute_aggregated_bracket_levels()` → неможливо діагностувати чому brackets fails

**Рішення** (з Investigation):
```python
# fsm_manage.py line 1208
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
    # ... existing logic
```

**Вплив**: 🟡 **MEDIUM** - полегшує діагностику.

---

#### ✅ COVERED (але можна покращити): AttributeError get_positions_notional_usd_shadow
**Статус**: ✅ **ВИРІШЕНО** в Investigation (2025-11-19)
**FIX_PLAN**: НЕ покривав цю проблему
**Рішення**: Додано `hasattr()` перевірку (fsm.py line 4767)

```python
# EP-FIX-SHADOW: Check if shadow method exists before calling
if not hasattr(self.adapter, "get_positions_notional_usd_shadow"):
    self.logger.debug("SHADOW_CHECK_SKIP: Adapter does not support shadow notional check")
    return
```

**Вплив**: ✅ Minor - усунуто AttributeError spam в логах.

---

## 🎯 ВИСНОВКИ ТА РЕКОМЕНДАЦІЇ

### Актуальність FIX_PLAN

| Розділ | Актуальність | Пріоритет змін |
|--------|-------------|----------------|
| 2.1 AttributeError Watchdog | ✅ АКТУАЛЬНО | Keep P0 |
| 2.2 Memory Leaks (6 типів) | ✅ АКТУАЛЬНО | ⬇️ Знизити P1 → P2 |
| 2.3 Fire-and-Forget Tasks | ✅ АКТУАЛЬНО | Keep P1 |
| 2.4 Threading vs Asyncio Lock | ✅ АКТУАЛЬНО | Keep P1 |
| 2.5 Decimal Unification | ✅ АКТУАЛЬНО | Keep P1 |
| 2.6 Config Parsing | ✅ АКТУАЛЬНО | Keep P2 |
| 2.7 Optimistic Updates | ✅ АКТУАЛЬНО | Keep P2 |
| 2.8 Shutdown Cleanup | ✅ АКТУАЛЬНО | Keep P2 |
| **🔴 MISSING:** AGG_OCO Loop | ❌ НЕ ПОКРИТО | ⬆️ **ADD as NEW P0** |
| **🔴 MISSING:** Entry Price in Auto-Heal | ❌ НЕ ПОКРИТО | ⬆️ **ADD as NEW P0** |
| **🔴 MISSING:** Auto-Heal Backoff | ❌ НЕ ПОКРИТО | ⬆️ **ADD as NEW P1** |
| **⚠️ MISSING:** AGG_OCO Observability | ❌ НЕ ПОКРИТО | ⬆️ **ADD as NEW P2** |

---

### Оновлений Timeline (з AGG_OCO fixes)

#### Phase 0: AGG_OCO HOTFIXES (Day 0) 🔴 **NEW - CRITICAL**
1. **Fix GAP #1:** BRACKETS_PENDING loop (no state reset if position exists) - 1 година
2. **Fix GAP #2:** Entry price fetch before fake TRADE_EXECUTED - 1.5 години
3. **Fix GAP #3:** Exponential backoff для auto-heal - 1 година
4. **Fix GAP #4:** Observability logging - 30 хвилин
5. **Unit tests** для AGG_OCO loop prevention - 1 година
6. **Integration test** з mock REST API timeout - 1 година

**Phase 0 Total**: 6 годин (1 день)

#### Phase 1: P0 (Existing - Day 1)
1. ✅ AttributeError lambda fix - 5 хв
2. ⚠️ BLOCKER #1 (_processed_events_ts) - 30 хв
3. ⚠️ BLOCKER #2 (idempotency cleanup) - 20 хв
4. ✅ Unit tests - 1 година

#### Phase 2-5: (Existing - Day 2-6)
- Без змін (див. FIX_PLAN sections 4.2-4.5)

**Оновлений Total**: 6 днів → **7 днів** (через додавання Phase 0)

---

## 🚨 КРИТИЧНІ РЕКОМЕНДАЦІЇ

### 1. ТЕРМІНОВЕ ОНОВЛЕННЯ FIX_PLAN
**Дія**: Додати Phase 0 (AGG_OCO hotfixes) **ПЕРЕД** Phase 1
**Обґрунтування**:
- AGG_OCO loop → production система broken ЗАРАЗ
- Memory leaks → crash через 7-30 днів
- **AGG_OCO критичніший за memory leaks**

### 2. ПРІОРИТИЗАЦІЯ
**Дія**: Змінити пріоритети:
```
OLD FIX_PLAN:
P0: AttributeError Watchdog
P1: Memory Leaks, Fire-and-Forget, Decimal

NEW PRIORITIES (після Investigation):
P0: AGG_OCO Loop Fix (GAP #1)        ← NEW
P0: Entry Price in Auto-Heal (GAP #2) ← NEW
P0: AttributeError Watchdog           ← Existing
P1: Auto-Heal Backoff (GAP #3)        ← NEW
P1: Fire-and-Forget Tasks             ← Existing
P1: Decimal Unification               ← Existing
P2: Memory Leaks (6 типів)            ← DOWNGRADED від P1
P2: AGG_OCO Observability (GAP #4)    ← NEW
P2: Config Parsing, Optimistic Updates, Shutdown ← Existing
```

### 3. ТЕСТУВАННЯ
**Дія**: Додати 4 нові тести для AGG_OCO:
1. **test_agg_oco_loop_prevention**: Verify state NOT reset to FLAT when position exists
2. **test_entry_price_fetch_before_autoheal**: Mock REST API, verify price in fake TRADE_EXECUTED
3. **test_exponential_backoff**: Verify retry intervals: 5s → 10s → 20s → 40s → 80s
4. **test_circuit_breaker_recovery**: Verify BLOCKED symbols unblock after successful heal

### 4. DEPLOYMENT STRATEGY
**Дія**: Deploy Phase 0 окремо від Phase 1-5
**Обґрунтування**:
- Phase 0 (AGG_OCO) → **hotfix candidate** (deploy to production ASAP)
- Phase 1-5 (memory leaks, decimal) → **можуть чекати** до release cycle

---

## 📋 CHECKLIST ДЛЯ ОНОВЛЕННЯ FIX_PLAN

- [ ] ✅ Додати Phase 0 (AGG_OCO hotfixes) перед Phase 1
- [ ] ✅ Оновити пріоритети (AGG_OCO → P0, Memory Leaks → P2)
- [ ] ✅ Додати 4 нові тести для AGG_OCO
- [ ] ✅ Оновити Timeline (6 днів → 7 днів)
- [ ] ✅ Додати Deployment Strategy (hotfix vs release)
- [ ] ✅ Оновити Rollback Plan з AGG_OCO scenarios
- [ ] ✅ Додати Observability metrics для AGG_OCO loop detection
- [ ] ✅ Документувати entry_price fallback hierarchy (4 levels)

---

## 🔗 REFERENCES

1. **FIX_PLAN_EXECUTION_POSITION_FSM.md** - Оригінальний план (до Investigation)
2. **INVESTIGATION_MISSING_TP_SL_2025-11-19.md** - Дослідження 2025-11-19 (нові знахідки)
3. **INCIDENT_NO_TP_SL_AGG_OCO_2025-11-18.md** - Попередній інцидент (ідентична проблема)
4. **fsm.py lines 1883-1920** - AGG_OCO auto-heal logic (проблемний код)
5. **fsm_manage.py lines 505-560, 1208-1229** - State transitions + bracket computation

---

## 🎬 FINAL VERDICT

**FIX_PLAN статус**: ⚠️ **70% АКТУАЛЬНИЙ, 30% MISSING CRITICAL**

**Критичні прогалини**:
1. 🔴 AGG_OCO BRACKETS_PENDING loop (P0)
2. 🔴 Entry Price missing in auto-heal (P0)
3. 🔴 Auto-Heal exponential backoff (P1)
4. ⚠️ AGG_OCO observability logging (P2)

**Рекомендація**: 🔴 **ОНОВИТИ FIX_PLAN НЕГАЙНО**
- Додати Phase 0 з AGG_OCO hotfixes
- Знизити пріоритет memory leaks (P1 → P2)
- Deploy Phase 0 як hotfix ASAP
- Phase 1-5 можуть чекати до release cycle

**Ризик якщо НЕ оновити**: Production система залишається broken (unprotected positions, circuit breaker blocks)

---

**Prepared by**: GitHub Copilot (Claude Sonnet 4.5)
**Date**: 2025-11-19 23:45 UTC
**Analysis Duration**: 12 minutes
**Documents Analyzed**: 2 (FIX_PLAN + INVESTIGATION)
