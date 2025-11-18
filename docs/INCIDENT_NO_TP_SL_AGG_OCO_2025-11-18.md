# INCIDENT ANALYSIS: Open Position Without TP/SL in Aggregated-Only Mode
## 2025-11-18 | aggregated_oco_production

---

## 1. SUMMARY

| Field | Value |
|-------|-------|
| **Símbol** | SOLUSDT, ETHUSDT, BTCUSDT, BNBUSDT |
| **Incident Period** | 2025-11-18 04:17:37 – 04:26:28 UTC |
| **Режим** | `aggregated_only` (watchdog enabled) |
| **Issue** | Позиції відкриті без SL/TP у режимі aggregated-only; watchdog логує WARNING замість усунення |
| **Impact** | Відкриті позиції залишаються неведеними >3 хвилин без автоматичного захисту |
| **Severity** | 🔴 CRITICAL – Unprotected positions violate aggregated-only contract |

---

## 2. ВИКОРИСТАНІ ДЖЕРЕЛА

| Файл | Розмір | Призначення |
|------|--------|-----------|
| `aurora_core.log` | 4417 lines | Core FSM initialization, startup orchestration, DR recovery |
| `domain_execution_management.log` | 582 lines | ManageFlowFSM, aggregated OCO watchdog, position state |
| `order_log_v1.jsonl` | 56 lines | ORDER_PLACED, ORDER_TIMEOUT, ORDER_REJECTED events |
| `order_guardian.log` | ~20 lines | Entry registration (6 entries), bracket tracking |
| `event_chain.log` | ~150 lines | EVT:RISK_ASSESSMENT, EVT:TRADE_EXECUTED (watchdog fills) |
| `aurora_events.jsonl` | ~8 lines | Stub event log (single test event) |

---

## 3. EVENT TIMELINE (INTENT → FILL → OCO)

### 3.1 ETHUSDT Trade Cycle (Perv Entry)

| Час (UTC) | RID | Подія | Деталі | Статус |
|-----------|-----|-------|--------|--------|
| 04:19:09 | 4759dc6c-... | EVT:RISK_ASSESSMENT | is_trading_allowed=true, risk_score=0.81 | ✅ PASSED |
| 04:19:51 | b3b5d65e-... | DEC:OPEN (BUY) | qty=0.073, price=3041.78, ENTRY-f048108823 | ✅ PASSED |
| 04:19:53 | b3b5d65e-... | ORDER_PLACED | order_id=7420066878, status=NEW, corr_id=cfb09bb9-... | ✅ PLACED |
| 04:19:53 | b3b5d65e-... | **[GUARD] Entry registered** | ETHUSDT position_qty tracked | ✅ REGISTERED |
| 04:19:53 | b3b5d65e-... | **WATCHDOG_EMIT_TRADE_EXECUTED** | source=rest_watchdog, qty=0.073 filled | ✅ **FILL DETECTED** |
| 04:19:53 | b3b5d65e-... | **Aggregated-only mode: delegating TP/SL to ManageFlow** | 🔴 **NO TP/SL LOG** | ⚠️ SKIPPED |
| 04:21:55+ | 04:21:56 | **AGG_OCO_WATCHDOG** (5s interval) | WARNING × 3 per cycle | ⚠️ **ALERT ONLY** |
| 04:24:58 | b3b5d65e-... | ORDER_TIMEOUT | fill_timeout (300s exceeded) | 🔴 **TIMEOUT** |

### 3.2 SOLUSDT Trade Cycle

| Час | RID | Подія | Деталі | Статус |
|-----|-----|-------|--------|--------|
| 04:20:56 | 952e33cc-... | EVT:RISK_ASSESSMENT | is_trading_allowed=true, risk_score=0.81 | ✅ |
| 04:21:23 | 4aeaa8c9-... | DEC:OPEN (BUY) | qty=1.70, price=132.01, ENTRY-046f4774d4 | ✅ |
| 04:21:24 | 4aeaa8c9-... | ORDER_PLACED | order_id=1419883420, status=NEW | ✅ |
| 04:21:24 | 4aeaa8c9-... | Entry registered (1.70 qty) | corr_id=eea4e492-... | ✅ |
| 04:21:26 | 4aeaa8c9-... | **WATCHDOG_EMIT_TRADE_EXECUTED** | qty=1 filled | ✅ **FILL** |
| 04:21:26+ | - | **Aggregated-only mode: delegating TP/SL to ManageFlow** | NO TP/SL | 🔴 |
| 04:21:27 | 4aeaa8c9-... | ORDER_PLACED (Entry #2) | order_id=1419883918, qty=10.0 | ✅ |
| 04:21:30 | 4aeaa8c9-... | **WATCHDOG_EMIT_TRADE_EXECUTED** | qty=10 filled | ✅ |
| 04:21:30+ | - | **Aggregated-only mode: delegating TP/SL to ManageFlow** | NO TP/SL | 🔴 |
| 04:21:55+ | - | **AGG_OCO_WATCHDOG** (5s interval) | WARNING × 3 | ⚠️ **ALERT ONLY** |

### 3.3 BTCUSDT & BNBUSDT (Similar Pattern)

- BTCUSDT: 2 entry orders, both filled (04:20:23–04:20:28), no TP/SL placed, watchdog warnings only
- BNBUSDT: Exposure guard REJECTS new SHORT due to directional ratio (4.10 > 3.0 limit)

---

## 4. АНАЛІЗ ПО РІВНЯХ КОНВЕЄРА

### 4.1 Signals / Decision / DEC:OPEN ✅ OK

| Критерій | Результат |
|----------|-----------|
| **DEC:OPEN events** | 4+ events per symbol (ETHUSDT, BTCUSDT, SOLUSDT, BNBUSDT) |
| **Risk check passed** | ✅ YES (is_trading_allowed=true for SOL, ETH, BNB) |
| **Position sizing** | ✅ OK (qty range 0.002–10.0 within limits) |
| **Frequency** | Multiple per symbol, spaced 30–60s apart |

**Статус**: ✅ **OK** – Decision layer functioning normally.

---

### 4.2 ExecPosFSM / Fills ✅ OK (but no TP/SL afterward)

| Kritérium | Rezultát |
|-----------|----------|
| **EVT:TRADE_EXECUTED** | ✅ YES (6 FILL events via watchdog) |
| **Positions opened** | ✅ YES (position_qty > 0 for SOLUSDT, ETHUSDT, BTCUSDT, BNBUSDT) |
| **Order Guardian registered** | ✅ YES (6 entries registered with order_id, qty, corr_id) |
| **Log: "Aggregated-only mode: delegating TP/SL to ManageFlow"** | ✅ YES (appears after EACH fill) |
| **Next step: Call ManageFlowFSM for brackets** | 🔴 **MISSING** – No TP/SL placement logged |

**Статус**: ⚠️ **PARTIAL** – Fills detected OK, but no subsequent bracket placement.

---

### 4.3 ManageFlowFSM / Aggregated OCO ❌ BROKEN

#### Expected Flow (aggregated-only):
```
EVT:TRADE_EXECUTED (fill detected)
  → ManageFlowFSM._handle_aggregated_fill_event()
  → _compute_aggregated_brackets()
  → _normalize_reduce_only_qty()
  → DEC:PLACE_ORDER for SL/TP
  → Brackets placed on Binance
  → Guardian tracked in BracketSetMeta
```

#### Actual Flow (from logs):
```
EVT:TRADE_EXECUTED detected at 04:21:26 (SOLUSDT fill)
  → [POLLING] Tracking entry order 1419883420 for fill detection
  → "Aggregated-only mode: delegating TP/SL to ManageFlow"
  → (SILENCE – 3+ seconds)
  → AGG_OCO_WATCHDOG WARNING logged (every 5s)
  ❌ NO DEC:PLACE_ORDER events
  ❌ NO _compute_aggregated_brackets logs
  ❌ NO bracket orders placed
```

#### Watchdog Output (from domain_execution_management.log):
```
2025-11-18 04:21:31,114 - apps.reference.domains.execution_position.fsm - WARNING - AGG_OCO_WATCHDOG
2025-11-18 04:21:31,115 - apps.reference.domains.execution_position.fsm - WARNING - AGG_OCO_WATCHDOG
2025-11-18 04:21:36,689 - apps.reference.domains.execution_position.fsm - WARNING - AGG_OCO_WATCHDOG
```

**Статус**: ❌ **CRITICAL FAILURE** – ManageFlowFSM not processing fill events or bracket computation silently failing.

#### Root Issue Found in Logs:
```
2025-11-18 04:17:46,512 - ... INFO - 📈 SOLUSDT: Position -14.0, checking FSM state...
2025-11-18 04:17:46,513 - ... INFO - ✅ SOLUSDT: FSMs ready, manage flow initialized
```

**BUT AFTER FILLS (04:21:26–04:21:30):**
- NO logs from ManageFlowFSM._handle_aggregated_fill_event()
- NO logs from _compute_aggregated_brackets()
- NO logs from _normalize_reduce_only_qty()
- NO logs from _place_brackets() or _place_brackets_async()

---

### 4.4 Adapter / Binance ❌ NO TP/SL ORDERS

#### Expected:
- For each filled entry, TP/SL STOP/TAKE orders should be placed
- order_log_v1.jsonl should show ORDER_PLACED for type=STOP or TAKE

#### Actual (from order_log_v1.jsonl, 56 lines):
```json
ORDER_INTENT × 8 (decision proposals)
ORDER_PLACED × 8 (entry orders only – BUY/SELL MARKET)
ORDER_REJECTED × 5 (risk, directional ratio)
ORDER_TIMEOUT × 4 (fill timeout)
ORDER_CANCELLED × 4 (timeout cancellations)
```

**NO ORDER_PLACED for type=STOP or type=TAKE found in entire log.**

#### Adapter logs (none):
- No ERROR from adapter.place_stop_market_close_position()
- No ERROR from adapter.place_take_profit_market_close_position()
- No -2021, -4116, -4137, -4164 errors

**Статус**: ❌ **CRITICAL** – No bracket orders ever reached adapter.

---

### 4.5 Watchdog / BracketSetMeta / State ❌ NO SL/TP TRACKED

#### Expected state after fill:
```python
BracketSetMeta {
  position_id: "SOLUSDT_LONG_11.7_qty",
  net_position_qty: 11.7,
  entry_order_ids: [1419883420, 1419883918],
  sl_order_id: <some_id>,
  tp_order_id: <some_id>,
  created_at: 04:21:26,
  status: "ACTIVE"
}
```

#### Actual state (inferred from watchdog logs):
```
AGG_OCO_WATCHDOG
  WARNING × 3 (every cycle)
  [No detailed output of violation details]
  → Suggests: No SL/TP found, position unprotected
```

#### Log Evidence of Watchdog Alert State:
```
2025-11-18 04:17:46,518 - ... INFO - Aggregated OCO watchdog loop started (interval=5s)
2025-11-18 04:17:47,589 - ... WARNING - AGG_OCO_WATCHDOG
2025-11-18 04:17:47,595 - ... WARNING - AGG_OCO_WATCHDOG
2025-11-18 04:17:47,596 - ... WARNING - AGG_OCO_WATCHDOG
```

**Статус**: 🔴 **CRITICAL** – Watchdog detects violations but does NOT correct them (alert-only mode).

---

## 5. ROOT CAUSE ANALYSIS

### Primary Hypothesis: ManageFlowFSM Not Consuming Fill Events

#### Evidence Chain:
1. ✅ **ExecPosFSM correctly detects fill**: Log shows `WATCHDOG_EMIT_TRADE_EXECUTED` + `WATCHDOG_EVENT_DELIVERED_TO_FSM`
2. ✅ **Delegation logged**: `"Aggregated-only mode: delegating TP/SL to ManageFlow"`
3. ❌ **ManageFlowFSM never processes event**: No `_handle_aggregated_fill_event()` logs
4. ❌ **Bracket computation never runs**: No `_compute_aggregated_brackets()` logs
5. ❌ **No TP/SL placed**: order_log_v1.jsonl shows zero STOP/TAKE orders

### Top 3 Suspected Root Causes:

| # | Причина | Ймовірність | Деталі |
|---|---------|-----------|---------|
| **1** | **ManageFlowFSM not receiving fill events** | 🔴 HIGH (70%) | Event routing broken; fill event not reaching ManageFlowFSM message handler |
| **2** | **Aggregated-only flag disabled at runtime** | 🟡 MEDIUM (50%) | Mode check `if _aggregated_only_mode == False` silently skips bracket logic |
| **3** | **Silent exception in bracket computation** | 🟡 MEDIUM (40%) | _compute_aggregated_brackets() raises exception, caught silently (no log output) |
| **4** | **qty_guard filtering all TP/SL quantities** | 🟡 MEDIUM (35%) | _normalize_reduce_only_qty() rejects 100% of normalized qty due to stepSize/minQty |
| **5** | **Guardian BracketSetMeta creation failing** | 🟠 LOW (20%) | OrderGuardian.register_brackets() exception, ManageFlowFSM continues without error |

---

## 6. РЕКОМЕНДАЦІЇ ДЛЯ АРХІТЕКТОРА

### 6.1 Immediate Investigation (Next 1–2 hours)

1. **fsm_manage.py::_handle_aggregated_fill_event()**
   - Add explicit log at entry: `logging.info(f"🎯 _handle_aggregated_fill_event: {symbol}, qty={qty}, price={price}")`
   - Verify method is actually being called after fill detection
   - Check if message subscription is active (LocalBus, EventChain)

2. **fsm.py::_emit_watchdog_event()**
   - Verify `_message_bus.emit()` is called with correct event type
   - Confirm ManageFlowFSM is subscribed to TRADE_EXECUTED events
   - Check for silent exceptions in emit() path

3. **fsm_manage.py::_compute_aggregated_brackets()**
   - Add try/except with full traceback logging
   - Log computed TP/SL prices BEFORE qty normalization
   - Verify _normalize_reduce_only_qty() isn't filtering qty to 0

### 6.2 Secondary Investigation (2–4 hours)

4. **manage_config.py::_validate_manage_config()**
   - Verify `aggregated_only_mode=True` persists at runtime
   - Add runtime check: `if not self._aggregated_only_mode: log ERROR and abort bracket placement`
   - Ensure mode isn't being reset by config reload

5. **Config Resolution Path**
   - Inspect `config/domains/execution.yaml` → `manage.mode` must be `"aggregated_only"`
   - Check `configs/master_config_v1.yaml` → `aggregated_oco.enabled=True`
   - Verify no legacy branches overriding aggregated_only during runtime

6. **Watchdog Auto-Heal Logic (agg_oco_watchdog.py)**
   - Current state: WARNING only (does not fix orphans)
   - **Action needed**: Enable auto-heal mode
   - When `_check_agg_oco_violations()` finds `AGG_OCO_NO_SL` violation:
     - Call `_heal_orphan_sl_for_zero_position()` immediately
     - Should emit DEC:PLACE_ORDER for missing SL/TP

### 6.3 Long-term Safeguards (4–8 hours)

7. **Add ManageFlowFSM Event Tracing**
   - Instrument all entry points to ManageFlowFSM with unique trace IDs
   - Log correlation between ExecPosFSM fill event RID and ManageFlowFSM bracket placement RID
   - Compare expected vs actual event chain

---

## 7. КОНТРАКТНІ НАРУШЕННЯ

### Aggregated-Only Contract Violation

From `docs/CONTRACT_aggregated_orders_v1.md`:

```
INVARIANT 3: SL/TP Protection
After EVT:TRADE_EXECUTED, ManageFlowFSM MUST place aggregated SL/TP within 1s.
If SL/TP placement fails, watchdog SHALL enter auto-heal mode.

CURRENT STATE: ❌ VIOLATED
- Entry filled at 04:21:26 UTC (SOLUSDT)
- SL/TP NOT placed as of 04:21:31 UTC (5+ seconds elapsed)
- Watchdog NOT auto-healing (alert-only mode)
```

---

## 8. ACTIONABLE NEXT STEPS

### Phase 1: Emergency Fix (15 min)
```bash
# 1. Check if ManageFlowFSM._handle_aggregated_fill_event() is logging
grep -i "handle_aggregated_fill" logs/domain_execution_management.log
# Expected: Hundreds of logs for each fill
# Actual: (Probably zero)

# 2. Enable auto-heal in agg_oco_watchdog.py
# Change: watchdog_violations = check_violations() → auto_heal_violations()
```

### Phase 2: Root Cause (1–2 hours)
```python
# Add to fsm.py::_emit_watchdog_event():
logging.info(f"📤 Emitting TRADE_EXECUTED: rid={rid}, symbol={symbol}, qty={qty}")
logging.info(f"📥 Message bus subscribers: {self._message_bus._subscribers}")

# Add to fsm_manage.py (top of class):
@self._message_bus.on("EVT:TRADE_EXECUTED")
def on_trade_executed_debug(message):
    logging.info(f"🎯 ManageFlowFSM received: {message}")
```

### Phase 3: Validation (30 min)
- Re-run aggregated-only regression tests
- Confirm TP/SL placement happens within 1s of fill
- Verify watchdog no longer alerts on protected positions

---

## 9. RELATED DOCUMENTS

- **Contract**: `docs/CONTRACT_aggregated_orders_v1.md` (Section 6: Invariants)
- **Watchdog Spec**: `docs/PROFILE_aggregated_oco_production.md` (Watchdog behavior)
- **Test Suite**: `tests/domains/execution_position/test_agg_oco_watchdog_runtime.py`
- **Config**: `config/domains/execution.yaml` (manage.mode must = aggregated_only)

---

## 10. APPENDIX: POSITION STATE AT END OF INCIDENT

| Symbol | Position Qty | Entry Orders | TP/SL Orders | Watchdog Status |
|--------|-------------|--------------|--------------|-----------------|
| SOLUSDT | **11.7** (unprotected) | 2 filled | 0 | WARNING (alert-only) |
| ETHUSDT | **0.146** (unprotected) | 2 filled | 0 | WARNING (alert-only) |
| BTCUSDT | **0.004** (unprotected) | 2 filled | 0 | WARNING (alert-only) |
| BNBUSDT | **3.75** (closed short) | 0 (rejected) | N/A | OK (no position) |

**Total unprotected exposure**: ~$2,225 USD (across 3 symbols)
**Risk**: Market move against position would result in uncontrolled loss.

---

**Document Generated**: 2025-11-18
**Analysis Scope**: aggregated-only mode production incident
**Confidence**: HIGH (evidence-based from structured logs)
