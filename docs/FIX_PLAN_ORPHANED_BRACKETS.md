# Orphaned Brackets Fix Plan

**Дата створення**: 5 листопада 2025
**Пов'язано з**: `reports/ORPHANED_BRACKETS_INVESTIGATION_REPORT.md`
**Мета**: Усунути висячі TP/SL ордери та timeout-скасування, що не синхронізовані з біржею

---

## Priority Matrix

| Task | Priority | Impact | Complexity | Estimated Effort |
|------|----------|--------|------------|------------------|
| Normalize WebSocket payload | P0 | 🔴 CRITICAL | Medium | 2-3h |
| Verify cancel results | P0 | 🔴 CRITICAL | Low | 1h |
| Sync _symbol_brackets | P0 | 🔴 CRITICAL | Medium | 2h |
| Cleanup after manual CLOSE | P1 | 🟠 HIGH | Low | 30min |
| Fix startup sync | P1 | 🟠 HIGH | Low | 1h |
| Integration tests | P2 | 🟡 MEDIUM | High | 4-5h |
| Retry logic | P2 | 🟡 MEDIUM | Medium | 2h |
| Reconciliation loop | P2 | 🟡 MEDIUM | High | 3h |

---

## Phase 1: Critical Fixes (P0) — Target: Day 1

### Task 1.1: Normalize WebSocket payload [RC3, RC4]

**Problem**: WebSocket events від Binance мають вкладену структуру `{"o": {"i": orderId, "X": status}}`, але ManageFlowFSM шукає `pld["orderId"]` на топ-рівні → OCO не спрацьовує.

**Solution**:
1. **File**: `vfoundation/adapters/binance_adapter.py`
2. **Location**: `_parse_order_update()` method (or create if doesn't exist)
3. **Implementation**:
   ```python
   def _normalize_order_event(self, raw_event: dict) -> dict:
       """Normalize Binance WebSocket order event to flat structure."""
       if "o" in raw_event:  # ORDER_TRADE_UPDATE format
           order_data = raw_event["o"]
           return {
               "orderId": str(order_data.get("i")),  # Order ID
               "symbol": order_data.get("s"),
               "status": order_data.get("X"),  # Order status
               "side": order_data.get("S"),
               "type": order_data.get("o"),  # Order type
               "price": order_data.get("p"),
               "quantity": order_data.get("q"),
               "executedQty": order_data.get("z"),
               "avgPrice": order_data.get("ap"),
               "reduceOnly": order_data.get("R", False),
               "closePosition": order_data.get("cp", False),
               "timestamp": raw_event.get("E"),
               # Preserve raw for debugging
               "_raw": raw_event
           }
       return raw_event  # Already normalized or unknown format
   ```
4. **Integration**: У WebSocket callback перед емісією `EVT:ORDER_FILL` викликати `_normalize_order_event()`
5. **Testing**: Додати unit test з **real Binance payload** (з документації):
   ```python
   def test_normalize_binance_order_update():
       raw = {
           "e": "ORDER_TRADE_UPDATE",
           "E": 1568879465651,
           "o": {
               "s": "BTCUSDT",
               "i": 6375394853,
               "X": "FILLED",
               "o": "MARKET",
               "R": False,
               ...
           }
       }
       normalized = adapter._normalize_order_event(raw)
       assert normalized["orderId"] == "6375394853"
       assert normalized["status"] == "FILLED"
   ```

**Acceptance Criteria**:
- ✅ ManageFlowFSM._handle_bracket_fill отримує `pld["orderId"]` зі string value
- ✅ Unit test з real Binance payload проходить
- ✅ OCO emulation спрацьовує у staging (manual test)

**Dependencies**: None

**Estimated Effort**: 2-3 години

---

### Task 1.2: Verify cancel_order results [RC1, RC2]

**Problem**: `_handle_order_timeout` викликає `cancel_order()`, але **не перевіряє** статус відповіді біржі → якщо біржа відхиляє (наприклад, ордер вже виконується), система не дізнається.

**Solution**:
1. **File**: `apps/reference/domains/execution_position/fsm.py`
2. **Location**: `_handle_order_timeout()` method (lines ~844-862)
3. **Implementation**:
   ```python
   async def _handle_order_timeout(self, deadline):
       # ...existing log NRR-019...

       if self.adapter and not self.shadow_mode:
           try:
               self.watchdog.cancel_attempt_count += 1
               cancel_result = await self.adapter.cancel_order(
                   deadline.symbol, deadline.order_id
               )

               # ✅ NEW: Verify cancel status
               status = cancel_result.get("status", "").upper()
               if status == "CANCELED":
                   self.watchdog.cancel_success_count += 1
                   LOG.info(f"✅ Cancelled timed-out order {deadline.order_id}: {cancel_result}")
                   # Log to order_log
                   self.order_logger.write({
                       "rid": deadline.rid,
                       "event_type": "ORDER_CANCELLED",
                       "symbol": deadline.symbol,
                       "order_id": deadline.order_id,
                       "reason": "timeout_cancellation",
                       "timestamp": int(time.time() * 1000)
                   })
               else:
                   # Cancel rejected or ордер у non-cancelable state
                   LOG.error(
                       f"❌ Cancel rejected for timed-out order {deadline.order_id}: "
                       f"status={status}, result={cancel_result}"
                   )
                   self.order_logger.write({
                       "rid": deadline.rid,
                       "event_type": "ORDER_CANCELLATION_FAILED",
                       "symbol": deadline.symbol,
                       "order_id": deadline.order_id,
                       "reason": f"timeout_cancel_rejected_status_{status}",
                       "adapter_response": cancel_result,
                       "timestamp": int(time.time() * 1000)
                   })

           except Exception as e:
               LOG.warning(f"Failed to cancel timed-out order {deadline.order_id}: {e}")
               # Log exception
               self.order_logger.write({
                   "rid": deadline.rid,
                   "event_type": "ORDER_CANCELLATION_FAILED",
                   "symbol": deadline.symbol,
                   "order_id": deadline.order_id,
                   "reason": "timeout_cancel_exception",
                   "error": str(e),
                   "timestamp": int(time.time() * 1000)
               })
   ```

**Acceptance Criteria**:
- ✅ Якщо cancel успішний, логується `ORDER_CANCELLED` з reason="timeout_cancellation"
- ✅ Якщо cancel fail'иться, логується `ORDER_CANCELLATION_FAILED` з деталями помилки
- ✅ `cancel_success_count` інкрементується **тільки** при status="CANCELED"
- ✅ У логах order_log_v1.jsonl з'являються ORDER_CANCELLATION_FAILED події для проблемних ордерів

**Dependencies**: None

**Estimated Effort**: 1 година

---

### Task 1.3: Sync _symbol_brackets with ManageFlowFSM [RC5]

**Problem**: ExecPosFSM зберігає bracket IDs у `_symbol_brackets`, але ManageFlowFSM має **власні** `self.sl_order_id`/`self.tp_order_id` → якщо десинхронізовані, OCO не спрацьовує.

**Solution**:
1. **File**: `apps/reference/domains/execution_position/fsm_manage.py`
2. **Add method**:
   ```python
   def set_bracket_ids(self, sl_order_id: Optional[str], tp_order_id: Optional[str]) -> None:
       """Directly set bracket IDs from ExecPosFSM after placement."""
       self.sl_order_id = sl_order_id
       self.tp_order_id = tp_order_id
       LOG.debug(f"Synced bracket IDs: SL={sl_order_id}, TP={tp_order_id}")
   ```

3. **File**: `apps/reference/domains/execution_position/fsm.py`
4. **Location**: `_execute_decision()` after placing SL/TP (lines ~683, 705)
5. **Implementation**:
   ```python
   # After placing SL
   sl_order_id = sl_result.get("orderId")
   self._symbol_brackets.setdefault(symbol, {})["sl_order_id"] = sl_order_id

   # After placing TP
   tp_order_id = tp_result.get("orderId")
   self._symbol_brackets[symbol]["tp_order_id"] = tp_order_id

   # ✅ NEW: Sync with ManageFlowFSM
   if self.manage_flow:
       self.manage_flow.set_bracket_ids(
           sl_order_id=sl_order_id,
           tp_order_id=tp_order_id
       )
   ```

**Acceptance Criteria**:
- ✅ Після розміщення brackets ManageFlowFSM має `sl_order_id`/`tp_order_id` синхронізовані з `_symbol_brackets`
- ✅ OCO emulation спрацьовує навіть якщо ManageFlowFSM не отримав ORDER_UPDATED для brackets
- ✅ Логи показують "Synced bracket IDs" після кожного ENTRY fill

**Dependencies**: Task 1.1 (нормалізований payload)

**Estimated Effort**: 2 години

---

## Phase 2: High-Priority Fixes (P1) — Target: Day 2

### Task 2.1: Cleanup after manual CLOSE [RC6]

**Problem**: Коли користувач викликає manual CLOSE (або система емітує DEC:CLOSE), brackets скасовуються у `_execute_decision`, але `cleanup_orphaned_bracket_orders()` **не викликається** → якщо cancel failed, orphans залишаються.

**Solution**:
1. **File**: `apps/reference/domains/execution_position/fsm.py`
2. **Location**: `_execute_decision()` в секції `if decision.verb == "CLOSE"` (after line ~541)
3. **Implementation**:
   ```python
   # After place_market_reduce_only
   self._symbol_brackets.pop(symbol, None)

   # ✅ NEW: Ensure cleanup after close
   await asyncio.sleep(2.0)  # Give time for position to settle
   await self.cleanup_orphaned_bracket_orders(symbol)
   LOG.info(f"Cleanup after manual CLOSE for {symbol} completed")
   ```

**Acceptance Criteria**:
- ✅ Після manual CLOSE cleanup виконується автоматично через 2 секунди
- ✅ Якщо cancel у gather() failed, cleanup повторно спробує скасувати orphans
- ✅ Метрики `orphan_monitor.cancels` інкрементуються після manual CLOSE

**Dependencies**: None

**Estimated Effort**: 30 хвилин

---

### Task 2.2: Fix startup sync logic [RC7]

**Problem**: `sync_open_orders_and_positions` дублює логіку cleanup і не обробляє символи, які Binance **не повертає** у `get_open_positions()` (наприклад, позиції з zero amount).

**Solution**:
1. **File**: `apps/reference/domains/execution_position/fsm.py`
2. **Location**: `sync_open_orders_and_positions()` method (lines ~1279-1324)
3. **Implementation**:
   ```python
   async def sync_open_orders_and_positions(self) -> None:
       """Sync internal state with exchange on startup."""
       try:
           # Existing fetch positions/orders...

           # ✅ NEW: Use cleanup_orphaned_bracket_orders instead of duplicating logic
           LOG.info("Running orphan cleanup on startup...")
           await self.cleanup_orphaned_bracket_orders()  # Scans ALL symbols

           # Remove old duplicate code (lines 1298-1320)

       except Exception as e:
           LOG.error(f"sync_open_orders_and_positions failed: {e}")
   ```

**Acceptance Criteria**:
- ✅ Startup sync викликає `cleanup_orphaned_bracket_orders()` без аргументів (scan all)
- ✅ Не дублюється логіка cancel у sync методі
- ✅ Якщо біржа не повертає позицію для символу, cleanup все одно скасовує brackets

**Dependencies**: None

**Estimated Effort**: 1 година

---

## Phase 3: Medium-Priority Improvements (P2) — Target: Week 2

### Task 3.1: Integration tests with real WebSocket payloads [RC9]

**Problem**: Існуючі тести використовують FakeAdapter з синтетичними payloads → не покривають real Binance WebSocket shape.

**Solution**:
1. **File**: `tests/integration/test_binance_websocket_integration.py` (new)
2. **Implementation**:
   - Fixtures з **real Binance payloads** (з офіційної документації)
   - Mock WebSocket stream з послідовністю: ORDER_TRADE_UPDATE (NEW) → (FILLED) → (CANCELED)
   - Тест full lifecycle: place ENTRY → ACK → FILL → place SL/TP → SL FILL → verify TP CANCELED
3. **Coverage**:
   - Normalize payload
   - OCO emulation
   - Cleanup on fill
   - Timeout cancellation

**Acceptance Criteria**:
- ✅ Тести використовують exact Binance payload structure з `{"o": {"i": ...}}`
- ✅ Full lifecycle test проходить (entry → brackets → OCO → cleanup)
- ✅ Coverage для WebSocket integration збільшується до 80%+

**Dependencies**: Task 1.1, 1.3

**Estimated Effort**: 4-5 годин

---

### Task 3.2: Retry logic for cancel_order [RC1]

**Problem**: Якщо `cancel_order` fail'иться через тимчасову помилку (rate limit, network), система не повторює спробу.

**Solution**:
1. **File**: `vfoundation/adapters/binance_adapter.py`
2. **Add decorator**:
   ```python
   from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type

   @retry(
       stop=stop_after_attempt(3),
       wait=wait_fixed(1),
       retry=retry_if_exception_type((aiohttp.ClientError, asyncio.TimeoutError)),
       reraise=True
   )
   async def cancel_order(self, symbol: str, order_id: str) -> dict:
       # Existing implementation...
   ```
3. **Exception handling**: Ignore `-2011 Unknown order` (ордер вже не існує на біржі)

**Acceptance Criteria**:
- ✅ Cancel retry до 3 разів при network errors
- ✅ `-2011 Unknown order` не вважається помилкою (return success)
- ✅ Метрики `cancel_retry_count` додані

**Dependencies**: None

**Estimated Effort**: 2 години

---

### Task 3.3: Reconciliation loop [RC5, RC7]

**Problem**: `_symbol_brackets` може десинхронізуватися з реальними ордерами на біржі (manual cancel через UI, missed events).

**Solution**:
1. **File**: `apps/reference/domains/execution_position/fsm.py`
2. **Add method**:
   ```python
   async def _reconciliation_loop(self):
       """Periodically reconcile _symbol_brackets with exchange state."""
       while True:
           await asyncio.sleep(300)  # Every 5 minutes
           try:
               all_orders = await self.adapter.get_open_orders()
               exchange_brackets = {}  # {symbol: [order_ids]}

               for o in all_orders:
                   sym = o.get("symbol")
                   otype = o.get("type", "").upper()
                   if otype in ("STOP_MARKET", "TAKE_PROFIT_MARKET"):
                       exchange_brackets.setdefault(sym, []).append(o["orderId"])

               # Compare with tracked brackets
               for sym, tracked in self._symbol_brackets.items():
                   tracked_ids = {tracked.get("sl_order_id"), tracked.get("tp_order_id")}
                   exchange_ids = set(exchange_brackets.get(sym, []))

                   # Find stale tracked IDs (not on exchange)
                   stale = tracked_ids - exchange_ids - {None}
                   if stale:
                       LOG.warning(f"Reconciliation: stale tracked IDs for {sym}: {stale}")
                       # Clear stale IDs
                       if tracked.get("sl_order_id") in stale:
                           tracked.pop("sl_order_id", None)
                       if tracked.get("tp_order_id") in stale:
                           tracked.pop("tp_order_id", None)

           except Exception as e:
               LOG.error(f"Reconciliation loop error: {e}")
   ```
3. **Start in __init__**: `loop.create_task(self._reconciliation_loop())`

**Acceptance Criteria**:
- ✅ Кожні 5 хвилин порівнюється tracking з біржею
- ✅ Stale IDs видаляються з `_symbol_brackets`
- ✅ Метрики `reconciliation.stale_ids_cleared` додані

**Dependencies**: None

**Estimated Effort**: 3 години

---

## Implementation Order

**Day 1 (6-7 hours)**:
1. Task 1.1: Normalize WebSocket payload (2-3h)
2. Task 1.2: Verify cancel results (1h)
3. Task 1.3: Sync _symbol_brackets (2h)
4. Manual testing у testnet

**Day 2 (1.5-2 hours)**:
5. Task 2.1: Cleanup after CLOSE (30min)
6. Task 2.2: Fix startup sync (1h)
7. Regression testing

**Week 2 (9-10 hours)**:
8. Task 3.1: Integration tests (4-5h)
9. Task 3.2: Retry logic (2h)
10. Task 3.3: Reconciliation loop (3h)

---

## Success Metrics

**Before Fixes** (baseline з логів):
- Timeout cancels: 7+ events у order_log
- OCO emulation: 0% success rate (no CANCEL_ORDER після bracket fills)
- Orphan cleanup: 300s delay, no manual CLOSE cleanup

**After P0 Fixes** (targets):
- ✅ ORDER_CANCELLATION_FAILED events у логах (visibility)
- ✅ OCO emulation: 95%+ success rate (bracket fills → counterpart canceled within 2s)
- ✅ Orphan cleanup: immediate on manual CLOSE, verified у integration tests
- ✅ Zero stale brackets after 5min reconciliation

**After P1+P2 Fixes** (targets):
- ✅ Cancel retry success: 99%+ (network errors не призводять до orphans)
- ✅ Reconciliation drift: < 1% (tracking matches exchange state)
- ✅ Test coverage: 85%+ for WebSocket integration

---

## Rollback Plan

Якщо фікси призведуть до регресії:

1. **Revert commits**: Кожен task має окремий commit → можна revert individual fixes
2. **Feature flags**: Додати `config.fixes.normalize_payload: true` → можна вимкнути у production
3. **Shadow mode**: Протестувати фікси у shadow_mode (не надсилати реальні cancel на біржу)

---

## Notes

- Усі зміни покриваються unit/integration tests перед merge
- Manual testing у Binance Testnet після кожної фази
- Metrics dashboard для моніторингу cancel_success_rate, oco_success_rate, orphan_cleanup_latency
- Playbook оновлюється після завершення кожної фази з lessons learned

---

**Status**: Plan approved, ready for implementation
**Assignee**: GitHub Copilot + wekabeka1996
**Target Completion**: Phase 1-2 by end of Day 2, Phase 3 by Week 2
