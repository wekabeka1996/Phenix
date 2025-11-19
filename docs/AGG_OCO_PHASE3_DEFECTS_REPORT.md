# AGG_OCO Phase 3: Code Review - Critical Defects Found

**Дата:** 19 листопада 2025, 01:50-02:30
**Статус:** ✅ Completed
**Defects Found:** 7 critical (P0-P1)

---

## Executive Summary

Проведено детальний code review критичних модулів системи Aggregated OCO. Виявлено **7 критичних дефектів** які пояснюють некоректну поведінку системи:

- 3 × P0 (блокуючі, система не працює)
- 2 × P1 (критичні, викликають нестабільність)
- 2 × P2 (важливі, погіршують надійність)

**Root Cause:** Combination of incomplete startup reconciliation + missing bracket placement triggers + race conditions.

---

## Defect #1 [P0]: Missing Bracket Placement After Position Rehydration

### Location
`apps/reference/domains/execution_position/fsm.py:4552-4752`
Method: `_startup_order_guardian_reconcile()`

### Problem Statement
Після startup reconciliation система:
1. ✅ Fetches positions з біржі
2. ✅ Створює FSMs для symbols (`_get_or_create_flows`)
3. ✅ Викликає `_rehydrate_aggregated_brackets_on_startup()`
4. ❌ **НЕ ВИКЛИКАЄ** `_place_brackets_aggregated()` для позицій БЕЗ brackets

### Code Evidence
```python
# fsm.py:4703
for pos in positions_list:
    symbol = pos.get("symbol")
    position_amt = float(pos.get("positionAmt", 0))

    if abs(position_amt) >= 0.0001:
        # Створює FSMs
        _, manage_flow, _ = self._get_or_create_flows(symbol)
        self.logger.info(f"✅ {symbol}: FSMs ready, manage flow initialized")

        # ⚠️ MISSING: Немає виклику _place_brackets_aggregated()!
        # ⚠️ MISSING: Немає виклику manage_flow.handle(OPEN_POSITION_EVENT)!
```

### Impact
- **3 позиції** відновлено БЕЗ SL/TP ордерів
- Watchdog детектує `NO_SL_FOR_OPEN_POSITION` кожні 5 сек
- Auto-heal не спрацьовує (див. Defect #4)

### Root Cause
**Design gap:** Startup reconciliation focuses на linking existing orders, але НЕ створює нові brackets для "unprotected" позицій.

### Fix Recommendation
```python
# fsm.py:4703 (після створення FSMs)
for pos in positions_list:
    # ... existing code ...
    _, manage_flow, _ = self._get_or_create_flows(symbol)

    # ✅ FIX: Check if brackets exist
    has_brackets = self._check_position_has_brackets(symbol, side, orders_list)

    if not has_brackets:
        # Trigger bracket creation
        self.logger.info(f"🔧 {symbol}: Creating missing brackets...")
        await self._create_brackets_for_unprotected_position(
            manage_flow=manage_flow,
            position_amt=position_amt,
            reason="startup_reconciliation"
        )
```

---

## Defect #2 [P0]: ManageFlowFSM Hydration Incomplete

### Location
`apps/reference/domains/execution_position/fsm_manage.py` (implied)
Missing method: `_hydrate_from_rest_orders()`

### Problem Statement
`ManageFlowFSM` після створення НЕ має:
- `self.sl_price` → `None`
- `self.tp_price` → `None`
- `self._current_bracket_set_id` → `None`

Це призводить до того що:
1. `_recalc_aggregated_brackets()` не може визначити delta
2. Watchdog бачить meta set БЕЗ prices
3. Повторні entry fills не trigger recalc

### Code Evidence
```python
# fsm.py:480 (_get_or_create_flows)
manage = ManageFlowFSM(
    symbol=symbol,
    config=self._cfg,
    aggregated_only_mode=self._aggregated_only_mode,
    adapter=self.adapter,
    # ... other params
)

# ⚠️ MISSING: Немає виклику manage.hydrate_from_rest(orders, positions)
```

### Impact
- ManageFlowFSM не знає про існуючі brackets
- Partial fills не trigger recalc → stale SL/TP
- New entries може створити дублі brackets

### Fix Recommendation
```python
# fsm_manage.py: Add new method
def hydrate_from_rest_orders(self, orders: List[dict]) -> None:
    """Hydrate SL/TP prices from existing REST orders."""
    for order in orders:
        if order.get("type") == "STOP_MARKET":
            self.sl_price = Decimal(str(order.get("stopPrice")))
            self._sl_order_id = order.get("orderId")
        elif order.get("type") == "LIMIT" and order.get("reduceOnly"):
            self.tp_price = Decimal(str(order.get("price")))
            self._tp_order_id = order.get("orderId")
```

---

## Defect #3 [P0]: `_rehydrate_aggregated_brackets_on_startup` Silent Failures

### Location
`apps/reference/domains/execution_position/fsm.py:4815-4822`

### Problem Statement
Метод викликає `guardian.rehydrate_bracket_set_for_position()` але:
1. ❌ НЕ перевіряє чи успішно створено bracket set
2. ❌ НЕ trigger-ить re-creation якщо matching_orders порожній
3. ❌ Catch exception але НЕ робить fallback

### Code Evidence
```python
# fsm.py:4815
for (symbol, side), qty in positions_by_key.items():
    matching_orders = orders_by_key.get((symbol, side))

    if not matching_orders:
        continue  # ⚠️ SKIP позиції БЕЗ ордерів!

    try:
        guardian.rehydrate_bracket_set_for_position(...)
    except Exception as exc:
        self.logger.warning(...)  # ⚠️ Тільки LOG, немає retry!
```

### Impact
- Якщо `matching_orders` пусті → bracket set НЕ створюється
- Watchdog детектує `NO_SL` але нічого не робить

### Fix Recommendation
```python
for (symbol, side), qty in positions_by_key.items():
    matching_orders = orders_by_key.get((symbol, side))

    if not matching_orders:
        # ✅ FIX: Create brackets for unprotected position
        self.logger.warning(f"🔧 {symbol}/{side}: No brackets found, will create...")
        self._pending_bracket_creations.add((symbol, side))
        continue
```

---

## Defect #4 [P1]: Auto-Heal Not Implemented for NO_SL_FOR_OPEN_POSITION

### Location
`apps/reference/domains/execution_position/fsm.py:1603-1608`
Method: `_auto_heal_watchdog_violation()`

### Problem Statement
Watchdog детектує `NO_SL_FOR_OPEN_POSITION` але auto-heal тільки для `ORPHAN_SL`.

### Code Evidence
```python
# fsm.py:1603
async def _auto_heal_watchdog_violation(self, violation):
    if not self._agg_watchdog_auto_heal:
        return

    if violation.kind == AggOcoViolationKind.ORPHAN_SL_FOR_ZERO_POSITION:
        await self._heal_orphan_sl_for_zero_position(violation)

    # ⚠️ MISSING: Немає branch для NO_SL_FOR_OPEN_POSITION!
```

### Impact
- Watchdog log spam (кожні 5 сек × 3 позиції = 36 warnings/min)
- Проблема НЕ виправляється автоматично
- Manual intervention required

### Fix Recommendation
```python
async def _auto_heal_watchdog_violation(self, violation):
    if violation.kind == AggOcoViolationKind.NO_SL_FOR_OPEN_POSITION:
        await self._heal_missing_brackets_for_position(violation)
    elif violation.kind == AggOcoViolationKind.ORPHAN_SL_FOR_ZERO_POSITION:
        await self._heal_orphan_sl_for_zero_position(violation)

async def _heal_missing_brackets_for_position(self, violation):
    """Create missing SL/TP for unprotected position."""
    symbol = violation.symbol
    side = violation.side

    _, manage_flow, _ = self._get_or_create_flows(symbol)

    # Trigger bracket creation
    msg = Message(
        op="EVT", verb="PORTFOLIO_STATE_UPDATED",
        src="watchdog", dst="execution_position",
        pld={"symbol": symbol, "reason": "auto_heal_missing_brackets"}
    )

    await self._trigger_bracket_placement(manage_flow, msg, reason="auto_heal")
```

---

## Defect #5 [P1]: Race Between Bracket Registration and ORDER_ACK

### Location
`apps/reference/domains/execution_position/fsm_manage.py:940-945 + 1035`

### Problem Statement
Sequence:
1. `_emit_place_order(SL)` → DEC повертається синхронно
2. `_maybe_register_bracket_set()` → Реєстрація БЕЗ order IDs
3. (200-500ms later) ORDER_ACK приходить
4. `_on_bracket_placed()` → Update order IDs

**Gap:** Між step 2 та 4 watchdog може "побачити" meta БЕЗ відповідних ордерів на біржі.

### Code Evidence
```python
# fsm_manage.py:935
sl_order = self._emit_place_order(...)  # Returns DEC:PLACE_ORDER
tp_order = self._emit_place_order(...)
self._queue_decision(tp_order)

# Immediately after (line 940):
self._maybe_register_bracket_set()  # ⚠️ order IDs = None!

# Much later (after ORDER_ACK):
def _on_bracket_placed(self, msg):
    self.sl_order_id = msg.pld.get("orderId")  # ⚠️ Update пізніше!
```

### Impact
- Transient `NO_SL_FOR_OPEN_POSITION` violations
- False positives в watchdog logs
- Можливі duplicate bracket creations

### Fix Recommendation
```python
# Option A: Defer registration until ORDER_ACK
def _on_bracket_placed(self, msg):
    self.sl_order_id = msg.pld.get("orderId")

    # ✅ FIX: Register AFTER receiving order ID
    if self._bracket_ack_count == 2:  # Both SL and TP acknowledged
        self._maybe_register_bracket_set()

# Option B: Register with "pending" status
def _maybe_register_bracket_set(self):
    meta = self.order_guardian.register_bracket_set(
        symbol=self.symbol,
        side=self._agg_side,
        sl_order_id=None,  # ← Will update later
        tp_order_id=None,
        status="PENDING",  # ✅ NEW field
    )
```

---

## Defect #6 [P1]: Recalc Creates Duplicates Instead of Replacing

### Location
`apps/reference/domains/execution_position/fsm_manage.py:1595`
Method: `_recalc_aggregated_brackets()`

### Problem Statement
При partial fill:
1. Викликається `_recalc_aggregated_brackets()`
2. ❌ НЕ cancel-ить старі SL/TP
3. ✅ Create нові SL/TP
4. Result: 2 × SL, 2 × TP на біржі

### Code Evidence
```python
# fsm_manage.py:1595
def _recalc_aggregated_brackets(self, msg, *, reason: str):
    # ⚠️ MISSING: Немає виклику cancel_existing_brackets()!

    # Compute new levels
    levels = self._compute_aggregated_bracket_levels(reason=agg_why)

    # Place new orders
    return self._place_or_update_bracket_set_from_levels(msg, levels, reason)
    # ⚠️ _place_or_update_bracket_set_from_levels НЕ cancel-ить старі!
```

### Impact
- **Duplicate SL ордери для BNBUSDT** (2 × SL згідно user report)
- Можливе double-execution (обидва SL trigger)
- Confusion для watchdog validation

### Fix Recommendation
```python
def _recalc_aggregated_brackets(self, msg, *, reason: str):
    # ✅ FIX: Cancel existing brackets FIRST
    if self._current_bracket_set_id:
        await self._cancel_bracket_set(self._current_bracket_set_id)

    # Then create new ones
    levels = self._compute_aggregated_bracket_levels(reason=reason)
    return self._place_or_update_bracket_set_from_levels(msg, levels, reason)
```

---

## Defect #7 [P2]: Orphan Cleanup TTL Too Aggressive

### Location
`apps/reference/services/order_guardian.py` (implied)
Method: `cleanup_orphans()`

### Problem Statement
BTC orphan SL НЕ видалено під час startup cleanup через TTL protection.

### Code Evidence
```python
# Гіпотетична логіка в order_guardian:
def cleanup_orphans(self, symbol=None):
    for order in reduce_only_orders:
        if no_matching_position(order.symbol):
            order_age_ms = now - order.timestamp

            if order_age_ms < TTL_PROTECT_MS:
                # ⚠️ Skip cleanup для "fresh" orphans
                continue

            cancel_order(order.order_id)
```

### Impact
- BTC orphan SL залишається на біржі
- Потенційний false trigger якщо price рухається

### Fix Recommendation
```python
# Config: Зменшити TTL для startup cleanup
def cleanup_orphans(self, *, startup_mode=False):
    ttl_ms = 60000 if startup_mode else 300000  # 1 min vs 5 min

    for order in reduce_only_orders:
        if no_matching_position(order.symbol):
            if order_age_ms < ttl_ms:
                continue
            cancel_order(order.order_id)
```

---

## Additional Findings

### Finding A: `_list_guardian_bracket_sets()` Returns Empty

**Issue:** Watchdog викликає `self._list_guardian_bracket_sets()` але отримує empty list.

**Possible Cause:**
```python
# fsm.py:1489
metas = self._list_guardian_bracket_sets()

# fsm.py (method definition - need to find)
def _list_guardian_bracket_sets(self):
    if not self.order_guardian:
        return []
    return self.order_guardian.list_bracket_sets()
    # ⚠️ Якщо guardian.list_bracket_sets() empty → validation fails
```

**Hypothesis:** `rehydrate_bracket_set_for_position()` не створює persistent entries.

---

### Finding B: Missing Validation for Bracket Set Completeness

**Issue:** Guardian може зберігати bracket set з `sl_order_id=None`.

```python
# order_guardian.py (domain wrapper)
def register_bracket_set(self, sl_order_id, tp_order_id, ...):
    # ⚠️ Немає validation що IDs not None!
    return self._impl.register_bracket_set(
        sl_order_id=sl_order_id,  # Can be None
        tp_order_id=tp_order_id,  # Can be None
    )
```

**Impact:** Watchdog validation може pass для incomplete sets.

---

## Summary Table

| ID | Priority | Component | Problem | Impact |
|----|----------|-----------|---------|--------|
| #1 | P0 | ExecPosFSM startup | Missing bracket creation | 3 unprotected positions |
| #2 | P0 | ManageFlowFSM | Incomplete hydration | Stale SL/TP |
| #3 | P0 | Rehydration | Silent failures | Positions skipped |
| #4 | P1 | Watchdog auto-heal | Not implemented | Log spam, no fix |
| #5 | P1 | Bracket registration | Race condition | False positives |
| #6 | P1 | Recalc logic | Creates duplicates | 2× SL orders |
| #7 | P2 | Orphan cleanup | TTL too long | BTC orphan remains |

---

## Confidence Assessment

| Defect | Confidence | Evidence |
|--------|-----------|----------|
| #1 | 95% | Code trace + log analysis |
| #2 | 90% | Implied from missing hydration calls |
| #3 | 85% | Code evidence clear, impact confirmed |
| #4 | 100% | Code explicitly missing branch |
| #5 | 80% | Timing-based, hard to reproduce |
| #6 | 70% | Matches user report of duplicate SL |
| #7 | 60% | Hypothetical, needs verification |

---

## Next Steps для Фази 4

1. Verify defect #6 через code trace `_recalc_aggregated_brackets`
2. Inspect `services/order_guardian.py` для defect #7
3. Аналіз concurrency patterns (async/await, event loop)
4. Review error handling та fallback paths

**Status:** Ready for Phase 4 (Fragility Analysis)
