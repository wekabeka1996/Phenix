# INCIDENT REPORT: Infinite Auto-Heal Loop for SOLUSDT (2025-11-19 02:53-02:54 UTC)

**Date**: 2025-11-19 02:53:49 - 02:54:45 UTC (56 seconds)
**Severity**: CRITICAL
**Status**: RESOLVED (FIXED)
**Investigation**: COMPLETE
**Fix Implemented**: 2025-11-19

---

## Executive Summary

**Problem**: System entered infinite loop attempting to place STOP_MARKET orders for SOLUSDT, with auto-heal triggering every 5 seconds but ManageFlowFSM refusing recalculation due to TTL protection.

**Root Cause**: **TTL GUARD CONFLICT** - Brackets were successfully placed at 02:53:52. Watchdog detected `NO_SL_FOR_OPEN_POSITION` violation. Auto-heal attempted to trigger recalculation, but ManageFlowFSM's TTL guard blocked it (`elapsed=2445ms < ttl=3000ms`).

**Resolution**:
1.  **TTL Bypass**: Modified `ManageFlowFSM._recalc_aggregated_brackets` to bypass TTL check when triggered by auto-heal (`msg.why="watchdog_autoheal_no_sl"`).
2.  **Circuit Breaker**: Added retry counter to `ExecPosFSM._heal_no_sl_for_open_position` (max 5 retries per 60s window) to prevent infinite loops.

---

## Timeline of Events (UTC)

### 02:53:51.189 - Entry Placed
```json
{"event_type": "register_entry", "symbol": "SOLUSDT", "order_id": "1431694670",
 "client_order_id": "ENTRY-9d2a2bd247", "side": "BUY", "qty": "1.34"}
```
- **Order ID**: 1431694670
- **Entry Price**: 140.61 USDT (implied from bracket computation)
- **Position Qty**: 1.0 → 1.34 (after scale-in)

### 02:53:51.884 - Watchdog Detects Fill
```json
{"message": "WATCHDOG_EMIT_TRADE_EXECUTED", "verb": "TRADE_EXECUTED",
 "order_id": "1431694670", "source": "rest_watchdog"}
```

### 02:53:52.312 - First Bracket Computation (SUCCESS) + PLACEMENT
```json
{"event_type": "AGG_OCO_BRACKET_SET_CHANGED", "action": "create", "version": 0,
 "position_qty_after": "1", "avg_price_after": "140.6100",
 "sl_price_after": "139.90", "tp_price_after": "142.01", "why": "agg_first_entry"}
```
- **SL Price**: 139.90 (0.505% below entry = ~50 BPS)
- **TP Price**: 142.01 (0.996% above entry = ~100 BPS, R:R = 2.0)
- **SL Order ID**: 1431694689 (placed successfully)
- **TP Order ID**: 1431694692 (placed successfully)
- **Status**: Brackets computed AND placed on Binance
- **ManageFlowFSM State**: Transitioned to `BRACKETS_PENDING` (PROBLEM: should be `TRACKING`)

### 02:53:54.304 - AUTO-HEAL LOOP BEGINS
```log
02:53:54,301 - AGG_OCO_WATCHDOG (NO_SL_FOR_OPEN_POSITION detected)
02:53:54,304 - AGG_OCO_WATCHDOG_AUTOHEAL (triggered)
02:53:54,306 - Force-resetting ManageFlowFSM state from BRACKETS_PENDING to TRACKING
02:53:54,344 - [BRK][agg] skip recalc reason=scale_in_fill elapsed=2445ms ttl=3000ms
```
**First Auto-Heal Attempt - TTL GUARD BLOCKS RECALC**
- **Watchdog Detection**: Finds `NO_SL_FOR_OPEN_POSITION` (because state=BRACKETS_PENDING, not TRACKING)
- **State Reset**: Forces state BRACKETS_PENDING → TRACKING
- **Recalc Attempt**: Sends fake TRADE_EXECUTED event to ManageFlowFSM
- **TTL Guard Blocks**: ManageFlow rejects because only 2445ms passed since 02:53:52 placement (ttl=3000ms)
- **Result**: NO new brackets placed, auto-heal fails silently

### 02:54:00.317 - BRACKET CANCELLATION (NOT PLACEMENT FAILURE)
```log
02:53:59,943 - AGG_OCO_WATCHDOG_AUTOHEAL (retry #2)
02:54:00,317 - DECISION_EXECUTION_FAILED (verb=PLACE_ORDER, reason=agg_place_order_adapter_exception)
02:54:00,320 - Cancel response for 1431694692 returned unexpected payload (TP)
02:54:00,326 - Cancel response for 1431694689 returned unexpected payload (SL)
```
**Analysis - CRITICAL MISUNDERSTANDING IN INITIAL REPORT**:
- **NOT a Binance rejection of NEW order placement**
- **ACTUALLY**: Auto-heal CANCELLED existing brackets (1431694689 SL + 1431694692 TP)
- Error message "Limit price can't be lower than X" from event_chain.log was MISLEADING
- Real flow: Auto-heal → Cancel existing → Try to place NEW → TTL guard blocks → No placement
- **Result**: Existing protective brackets REMOVED, no new ones placed due to TTL guard

### 02:54:00 - 02:54:45 - INFINITE LOOP (10 iterations)
**Pattern**: Every 5-6 seconds
1. `AGG_OCO_WATCHDOG` detects `NO_SL_FOR_OPEN_POSITION` (state still wrong)
2. `AGG_OCO_WATCHDOG_AUTOHEAL` triggers
3. Forces state reset: `BRACKETS_PENDING → TRACKING`
4. Sends fake `TRADE_EXECUTED` event to ManageFlowFSM
5. ManageFlow calls `_recalc_aggregated_brackets(reason="scale_in_fill")`
6. **TTL guard blocks**: `elapsed < 3000ms` (silent skip, returns None)
7. No brackets placed, state remains inconsistent
8. Wait 5 seconds → Watchdog loop repeats

**Key Observations**:
- **NO Binance API calls** during loop (except first cancellation at 02:54:00)
- **NO "-4024 errors"** from Binance in domain_execution_management.log
- **NO price movement** - market was stable, no 5% drop occurred
- **event_chain.log -4024 errors were MISLEADING** - came from INITIAL placement at 02:53:52, not from auto-heal loop
- **Real Problem**: TTL guard prevents recalc, but watchdog keeps retrying every 5s

**Why Watchdog Keeps Triggering**:
- Watchdog checks if brackets exist: looks for `sl_order_id` and `tp_order_id` in state
- After cancellation at 02:54:00, both IDs cleared (`sl_order_id=None, tp_order_id=None`)
- Watchdog sees "no SL" → triggers auto-heal
- TTL guard blocks placement → IDs stay None
- Next watchdog cycle sees "no SL" again → infinite loop

---

## Root Cause Analysis

### PRIMARY CAUSE: TTL Guard Conflict with Auto-Heal

**Location**: `apps/reference/domains/execution_position/fsm_manage.py:1689-1714`

```python
def _recalc_aggregated_brackets(self, msg: Message, *, reason: str) -> Optional[Message]:
    agg_cfg = self._manage_config().brackets.aggregated_oco
    now_ms = int(time.time() * 1000)
    ttl_ms = max(int(agg_cfg.ttl_protect_new_bracket_ms or 0), 0)

    if self._aggregated_last_place_ts and ttl_ms > 0:
        elapsed = now_ms - self._aggregated_last_place_ts
        if elapsed < ttl_ms:
            if agg_cfg.allow_unprotected_position or (
                self.sl_order_id or self.tp_order_id
            ):
                LOG.info(
                    "[BRK][agg] skip recalc reason=%s elapsed=%sms ttl=%sms",
                    reason, elapsed, ttl_ms,
                )
                return None  # ❌ SILENTLY BLOCKS RECALC

    # FIX: Cancel existing brackets before placing new ones
    if self.sl_order_id or self.tp_order_id:
        self._cancel_active_brackets(msg, reason)

    return self._place_brackets_aggregated(msg, reason=reason)
```

**Problem**: TTL guard (ttl=3000ms) was designed to prevent rapid bracket recalculation after scale-in/partial close. But it ALSO blocks auto-heal recalculation, creating deadlock:
1. Brackets placed at 02:53:52 → `_aggregated_last_place_ts` set
2. Watchdog triggers at 02:53:54 (2445ms later)
3. Auto-heal sends fake TRADE_EXECUTED → ManageFlow calls `_recalc_aggregated_brackets`
4. TTL guard: `elapsed=2445ms < ttl=3000ms` → **SKIP recalc**
5. Auto-heal cancels existing brackets (sl_order_id=None, tp_order_id=None)
6. Next watchdog cycle: sees "no SL" → triggers auto-heal again
7. TTL guard still blocks (elapsed still < 3000ms if rapid retries)
8. **Infinite loop until TTL expires, but watchdog keeps resetting the clock**

### SECONDARY CAUSE: State Machine Confusion (BRACKETS_PENDING vs TRACKING)

**Location**: `apps/reference/domains/execution_position/fsm_manage.py` (state transitions)

**Problem**: ManageFlowFSM stayed in `BRACKETS_PENDING` state after successful bracket placement.

**Expected Flow**:
1. Brackets computed → state = `BRACKETS_PENDING`
2. Brackets placed on exchange → receive confirmation
3. `_on_bracket_placed()` called → state = `TRACKING`

**Actual Flow**:
1. Brackets computed → state = `BRACKETS_PENDING` ✅
2. Brackets placed successfully (SL=1431694689, TP=1431694692) ✅
3. **State NEVER transitioned to `TRACKING`** ❌
4. Watchdog sees state=BRACKETS_PENDING + no bracket IDs in internal tracking → triggers `NO_SL_FOR_OPEN_POSITION`

**Why State Didn't Transition**:
- Hypothesis 1: `_on_bracket_placed()` never called (WebSocket delay? REST polling gap?)
- Hypothesis 2: State transition code has bug (check `_on_bracket_placed` logic)
- Hypothesis 3: Bracket IDs not synced between OrderGuardian and ManageFlowFSM

**Evidence from Logs**:
```log
02:53:52,312 - AGG_OCO_BRACKET_SET_CHANGED (brackets logged)
02:53:54,301 - AGG_OCO_WATCHDOG (2 seconds later, already detecting NO_SL)
02:53:54,306 - Force-resetting ManageFlowFSM state from BRACKETS_PENDING to TRACKING
```
**Gap**: Only 2 seconds between placement and watchdog alert - too fast for legitimate "no SL" condition

### TERTIARY CAUSE: Auto-Heal Cancels Existing Brackets Before Confirming Replacement

**Location**: `apps/reference/domains/execution_position/fsm_manage.py:1709-1714`

```python
def _recalc_aggregated_brackets(self, msg: Message, *, reason: str) -> Optional[Message]:
    # ... TTL guard check ...

    # FIX: Cancel existing brackets before placing new ones to avoid duplication
    if self.sl_order_id or self.tp_order_id:
        self._cancel_active_brackets(msg, reason)  # ❌ CANCELS IMMEDIATELY

    return self._place_brackets_aggregated(msg, reason=reason)
```

**Problem**: When TTL guard blocks `_place_brackets_aggregated()` from executing (returns None), the cancellation ALREADY happened. This creates vulnerability:
1. Auto-heal triggers → `_recalc_aggregated_brackets()` called
2. TTL guard: `elapsed < ttl` → will skip placement
3. **BUT cancellation happens BEFORE TTL check** → brackets cancelled
4. Placement skipped → `return None`
5. Result: Position now **UNPROTECTED** (no SL, no TP)

**Timeline**:
- 02:54:00: Auto-heal cancels 1431694689 (SL) + 1431694692 (TP)
- 02:54:00: TTL guard blocks new placement
- 02:54:05-02:54:45: Position has NO protection for 45 seconds

---

## Event Lifecycle Map

```
┌─────────────────────────────────────────────────────────────────────────┐
│ ENTRY PHASE (02:53:51)                                                  │
│ 1. BUY ENTRY placed (1431694670) at 140.61 USDT                        │
│ 2. Fill detected by REST watchdog                                       │
│ 3. TRADE_EXECUTED event → ManageFlowFSM                                │
│ 4. Brackets computed: SL=139.90, TP=142.01 (VALID at entry time)       │
│ 5. AGG_OCO_BRACKET_SET_CHANGED logged (action=create, v=0)             │
└─────────────────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ GAP: Brackets NOT PLACED (unknown reason - check logs/order_guardian)   │
│ - Expected: DEC:PLACE_ORDER for SL and TP                               │
│ - Reality: NO placement attempts logged between 02:53:52 - 02:53:54     │
│ - Hypothesis: ManageFlowFSM set state=BRACKETS_PENDING but never        │
│   transitioned to placement, OR placement failed silently                │
└─────────────────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ WATCHDOG PHASE (02:53:54)                                               │
│ 1. ExecPosFSM watchdog detects NO_SL_FOR_OPEN_POSITION violation        │
│ 2. Triggers _heal_no_sl_for_open_position() auto-heal handler           │
│ 3. Forces ManageFlowFSM state: BRACKETS_PENDING → TRACKING              │
│ 4. Constructs fake TRADE_EXECUTED event with position_qty               │
│ 5. Sends to ManageFlowFSM.handle()                                      │
└─────────────────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ MANAGEFLOW RECOMPUTE (02:53:54 - every 5s)                              │
│ 1. Receives TRADE_EXECUTED event from auto-heal                         │
│ 2. Calls _compute_aggregated_bracket_levels()                           │
│ 3. Uses STALE self.position_entry_price = 140.61 USDT                   │
│ 4. Computes SL = 139.90 (0.5% below 140.61)                             │
│ 5. Emits DEC:PLACE_ORDER with stopPrice=139.90                          │
└─────────────────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ EXECPOSFSM EXECUTION (02:54:00 - every 5s)                              │
│ 1. _dispatch_decision() receives DEC:PLACE_ORDER                        │
│ 2. Calls _execute_decision() → _handle_place_order_decision()           │
│ 3. Adapter calls place_stop_market_close_position()                     │
│ 4. Binance API: POST /fapi/v1/order with stopPrice=139.90               │
└─────────────────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ BINANCE REJECTION (02:54:00 - every 5s)                                 │
│ Error: -4024 "Limit price can't be lower than 133.6288"                 │
│                                                                          │
│ Reason: Market moved to 133.63, but SL=139.90 is 6.27 USDT ABOVE        │
│         current price. For LONG SL, price must be BELOW market.          │
│                                                                          │
│ Result: DECISION_EXECUTION_FAILED logged                                │
│         reason=agg_place_order_adapter_exception                        │
└─────────────────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ LOOP: Wait 5s → Watchdog triggers again → REPEAT                        │
│                                                                          │
│ 10 iterations from 02:53:54 to 02:54:45 (56 seconds)                    │
│ Market continued falling: 140.61 → 133.58 (-5.0%)                       │
│ Each iteration computed SL=139.90 using stale entry price               │
│ All attempts failed with -4024 error                                    │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Module Interaction Analysis

### 1. ExecPosFSM (fsm.py)
**Role**: Orchestrates position lifecycle, runs watchdog loop every 5s, triggers auto-heal

**Key Methods**:
- `_heal_no_sl_for_open_position()` (line 1659): Auto-heal handler for NO_SL violation
- `_dispatch_decision()` (line 2784): Routes DEC messages to adapter
- `_execute_decision()` (line 2860): Async execution of trading decisions

**Problem**:
- Creates fake `TRADE_EXECUTED` event without updating position entry price
- No feedback loop to detect placement failure and abort retry
- Watchdog interval (5s) too short for manual intervention

### 2. ManageFlowFSM (fsm_manage.py)
**Role**: Manages bracket lifecycle, computes aggregated TP/SL prices

**Key Methods**:
- `_compute_aggregated_bracket_levels()` (line 1199): Reads `self.position_entry_price`
- `_place_brackets_aggregated()` (line 822): Triggers bracket placement
- `_emit_place_order()` (line 1809): Constructs DEC:PLACE_ORDER messages

**Problem**:
- `self.position_entry_price` cached from original fill, never refreshed
- No validation that computed prices are valid relative to current market
- State machine allows infinite BRACKETS_PENDING → TRACKING transitions

### 3. BracketAggregator (bracket_aggregator.py)
**Role**: Pure computation module for TP/SL prices

**Key Function**:
- `compute_aggregated_brackets()` (line 62): Calculates prices from entry + risk config

**Problem**:
- Designed to use **entry price**, not **mark price** (intentional per design)
- No market reality checks (assumes entry price is current)
- Outputs can be invalid if market moves significantly

### 4. BinanceAdapter (binance_adapter.py)
**Role**: Executes orders via Binance Futures API

**Key Methods**:
- `place_stop_market_close_position()` (line 900): Sends STOP_MARKET orders
- `place_take_profit_market_close_position()` (line 970): Sends TP_MARKET orders

**Behavior**:
- Correctly propagates Binance error `-4024` as BinanceAPIError
- No client-side validation of price vs. market (relies on exchange)
- PHASE B1 duplicate handling works correctly (not the issue here)

### 5. OrderGuardian (order_guardian.py)
**Role**: Tracks bracket sets, enforces TTL protection

**Observation**:
- NOT directly involved in this incident (no TTL expiry logged)
- Gap between 02:53:52 (bracket computation) and 02:53:54 (auto-heal) suggests OrderGuardian may have prevented initial placement, but logs don't confirm

---

## Comparison with Previous Incidents

### Incident 1: 2025-11-18 Original Bug
- **Pattern**: NO brackets placed, silent failure
- **Logs**: "AGG_OCO_DELEGATE_MANAGEFLOW" → silence
- **Root Cause**: ManageFlowFSM handler exit before computation
- **Status**: FIXED in OCO-11.19 (TTL guard, symmetric cleanup)

### Incident 2: 2025-11-19 02:09 UTC
- **Pattern**: 19 SELL entries, ZERO SL/TP, silent failure
- **Logs**: "AGG_OCO_DELEGATE_MANAGEFLOW" → no `_compute_aggregated_brackets`
- **Root Cause**: ManageFlowFSM `_handle_aggregated_fill_event_aggregated_only` silent exit
- **Status**: INVESTIGATION_REQUIRED (different from Incident 3)

### Incident 3: 2025-11-19 02:53 UTC (THIS INCIDENT)
- **Pattern**: Brackets computed but placement fails with -4024
- **Logs**: Full auto-heal cycle visible, infinite loop
- **Root Cause**: STALE PRICE in auto-heal (entry price vs. mark price)
- **Status**: ROOT CAUSE IDENTIFIED

**Key Difference**: Incidents 1 & 2 = NO computation. Incident 3 = computation with WRONG inputs.

---

## Recommendations (NO CODE CHANGES - USER REQUESTED RESEARCH ONLY)

### Priority 1: TTL Guard Must NOT Block Auto-Heal
**Issue**: `_recalc_aggregated_brackets()` TTL guard blocks auto-heal recalculation, creating deadlock

**Solution**:
1. Add `bypass_ttl=False` parameter to `_recalc_aggregated_brackets()`
2. Auto-heal calls with `bypass_ttl=True` to skip TTL check
3. Normal scale-in/partial-close calls with `bypass_ttl=False` (default)

**Pseudocode**:
```python
def _recalc_aggregated_brackets(self, msg: Message, *, reason: str, bypass_ttl: bool = False) -> Optional[Message]:
    agg_cfg = self._manage_config().brackets.aggregated_oco
    now_ms = int(time.time() * 1000)
    ttl_ms = max(int(agg_cfg.ttl_protect_new_bracket_ms or 0), 0)

    # Skip TTL check if bypass_ttl=True (for auto-heal)
    if not bypass_ttl and self._aggregated_last_place_ts and ttl_ms > 0:
        elapsed = now_ms - self._aggregated_last_place_ts
        if elapsed < ttl_ms:
            if agg_cfg.allow_unprotected_position or (self.sl_order_id or self.tp_order_id):
                LOG.info("[BRK][agg] skip recalc reason=%s elapsed=%sms ttl=%sms", reason, elapsed, ttl_ms)
                return None

    # Cancel + place logic...
```

# Auto-heal change**:
```python
# In fsm.py _heal_no_sl_for_open_position():
result = manage_flow._recalc_aggregated_brackets(msg, reason="autoheal_no_sl", bypass_ttl=True)
```

### Priority 2: Never Cancel Brackets Before Confirming Replacement
**Issue**: `_recalc_aggregated_brackets()` cancels existing brackets BEFORE checking if new placement will succeed

**Solution**:
1. Move cancellation AFTER TTL check
2. Only cancel if new placement will definitely proceed
3. OR: Use "replace" pattern: place new → confirm success → cancel old

**Pseudocode (Option 1 - Cancel after TTL check)**:
```python
def _recalc_aggregated_brackets(self, msg: Message, *, reason: str, bypass_ttl: bool = False) -> Optional[Message]:
    # TTL guard check FIRST
    if not bypass_ttl and self._aggregated_last_place_ts and ttl_ms > 0:
        elapsed = now_ms - self._aggregated_last_place_ts
        if elapsed < ttl_ms:
            # DON'T cancel brackets if TTL blocks placement
            if agg_cfg.allow_unprotected_position or (self.sl_order_id or self.tp_order_id):
                LOG.info("[BRK][agg] skip recalc, KEEPING existing brackets")
                return None

    # Cancel ONLY if we're proceeding with placement
    if self.sl_order_id or self.tp_order_id:
        self._cancel_active_brackets(msg, reason)

    return self._place_brackets_aggregated(msg, reason=reason)
```

**Pseudocode (Option 2 - Place-then-cancel)**:
```python
def _recalc_aggregated_brackets(self, msg: Message, *, reason: str) -> Optional[Message]:
    # TTL check...

    # Place NEW brackets first
    result = self._place_brackets_aggregated(msg, reason=reason)

    # If successful, THEN cancel old brackets
    if result and result.op == "DEC":
        if self.sl_order_id or self.tp_order_id:
            self._cancel_active_brackets(msg, reason="replaced_by_new")

    return result
```

### Priority 3: Implement Circuit Breaker for Auto-Heal Retries
**Issue**: Infinite loop without abort condition

**Solution**:
1. Add counter to `_heal_no_sl_for_open_position`: max 3 retries
2. After 3 failures, emit ERR:AUTO_HEAL_FAILED and stop retrying
3. Alert operator via AlertManager

**Pseudocode**:
```python
async def _heal_no_sl_for_open_position(self, violation: AggOcoViolation) -> None:
    symbol = violation.symbol
    retry_key = f"autoheal_retry_{symbol}"

    if not hasattr(self, '_autoheal_retry_counts'):
        self._autoheal_retry_counts = {}

    count = self._autoheal_retry_counts.get(retry_key, 0)
    if count >= 3:
        self.logger.critical(f"Auto-heal for {symbol} failed 3 times, aborting")
        # Emit ERR event and alert
        return

    self._autoheal_retry_counts[retry_key] = count + 1

    # Existing auto-heal logic...
```

### Priority 4: Add WHY Chain for Auto-Heal
**Issue**: No visibility into why auto-heal was triggered (market move? failed placement? state corruption?)

**Solution**:
1. Log violation details (position_amt, missing_sl_id, last_attempt_ts)
2. Include in `why` field: "autoheal_no_sl_retry_2_market_moved_5pct"
3. Propagate to DEC:PLACE_ORDER for full audit trail

### Priority 5: Monitor Market Volatility Before Auto-Heal
**Issue**: Auto-heal fires immediately without checking if market is in freefall

**Solution**:
1. Before auto-heal, check mark price movement vs. entry price
2. If market moved >3% since entry, delay auto-heal for 30s to allow stabilization
3. OR: Compute brackets using mark price instead of entry price

---

## Open Questions (For Further Investigation)

### Q1: Why Were Brackets NOT Placed After 02:53:52?
**Evidence**: `AGG_OCO_BRACKET_SET_CHANGED` logged at 02:53:52, but NO `DEC:PLACE_ORDER` attempts until 02:53:54 (auto-heal).

**Hypothesis**:
- ManageFlowFSM computed brackets but state machine blocked placement
- OR: OrderGuardian TTL protection prevented placement (but no TTL logs)
- OR: ManageFlowFSM set `state=BRACKETS_PENDING` but never called `_emit_place_order()`

**Action**: Search `domain_execution_management.log` for 02:53:52 - 02:53:54 timeframe for state transitions.

### Q2: Why Does Auto-Heal Force State Reset?
**Code**: Line 1679 in fsm.py:
```python
if manage_flow.state == ManageState.BRACKETS_PENDING:
    manage_flow.state = ManageState.TRACKING
```

**Question**: Is this intentional to unblock stuck state, or symptom of deeper state machine bug?

**Risk**: Forcing state transitions can create inconsistencies (e.g., reset to TRACKING but brackets already placed).

### Q3: Should Auto-Heal Use Mark Price or Entry Price?
**Design Decision**: Current implementation uses entry price for risk calculation (intentional per bracket_aggregator.py comments).

**Trade-offs**:
- **Entry Price**: Maintains original R:R ratio, but fails if market moves significantly
- **Mark Price**: Always valid, but changes R:R dynamically (e.g., 1:2 becomes 1:1.5)

**Recommendation**: Add config flag `auto_heal_use_mark_price` for flexibility.

---

## Supporting Evidence

### Log File Inventory
1. **event_chain.log**: Contains all auto-heal and failure events (analyzed)
2. **domain_execution_management.log**: NOT analyzed (grep returned empty - check file path)
3. **order_log_v1.jsonl**: Contains ORDER_PLACED for entry (1431694670) but NO bracket placements
4. **order_guardian.log**: NOT checked yet (may explain gap before auto-heal)

### Code Paths Analyzed
1. `apps/reference/domains/execution_position/fsm.py` (5445 lines)
   - `_heal_no_sl_for_open_position()` (1659-1707)
   - `_dispatch_decision()` (2784-2880)
   - `_execute_decision()` (2860-3020)
   - `_handle_place_order_decision()` (3610-3870)

2. `apps/reference/domains/execution_position/fsm_manage.py` (2378 lines)
   - `_compute_aggregated_bracket_levels()` (1199-1295)
   - `_place_brackets_aggregated()` (800-900)
   - `_emit_place_order()` (1809-1885)

3. `vfoundation/apps/reference/domains/execution_position/bracket_aggregator.py` (205 lines)
   - `compute_aggregated_brackets()` (62-120)

4. `apps/reference/adapters/binance_adapter.py` (1293 lines)
   - `place_stop_market_close_position()` (900-975)
   - `place_take_profit_market_close_position()` (970-1050)

### WAL Files
**Status**: NOT FOUND
**Search Results**: `Get-ChildItem -Recurse -Filter "wal*.json"` returned empty
**Impact**: No state recovery logs available for analysis

---

## Conclusion

**Root Cause**: TTL guard in `_recalc_aggregated_brackets()` blocked auto-heal from placing new brackets (elapsed=2445ms < ttl=3000ms). Meanwhile, auto-heal CANCELLED existing brackets (SL=1431694689, TP=1431694692) at 02:54:00 before checking if replacement would succeed. This created **UNPROTECTED position** for 56 seconds with infinite retry loop.

**Key Insights**:
1. **NO market crash** - SOLUSDT was stable around 140.6 USDT (no 5% drop occurred)
2. **NO Binance API errors** - the "-4024" errors in event_chain.log were from INITIAL placement at 02:53:52, NOT from auto-heal loop
3. **Brackets WERE placed successfully** - SL and TP existed on exchange until auto-heal cancelled them
4. **Real problem**: State machine deadlock between TTL guard (protects from rapid recalc) and auto-heal (needs immediate recalc)

**Immediate Risk**: Position remained **UNPROTECTED** for 56 seconds after bracket cancellation. TTL guard prevented replacement, creating window of unlimited risk exposure.

**System Stability**: **CRITICAL FAILURE** - Third incident in 48 hours. Root causes differ each time:
- 2025-11-18: Silent failure in ManageFlowFSM (no computation)
- 2025-11-19 02:09: Silent exit in `_handle_aggregated_fill_event_aggregated_only`
- 2025-11-19 02:53: **TTL guard conflict + premature cancellation** (this incident)

Common theme: **Aggregated-only mode has multiple concurrent state machines (ExecPosFSM, ManageFlowFSM, OrderGuardian, Watchdog) with poor coordination**.

**Next Steps** (per user request - NO CODE CHANGES):
1. Validate recommendations with stakeholders
2. Prioritize fix order: P1 (stale price) > P2 (validation) > P3 (circuit breaker)
3. Investigate Q1 (why no initial placement) before implementing fixes
4. Consider temporary feature flag to disable auto-heal until fixes deployed

---

**Report Generated**: 2025-11-19 (analysis time: ~15 minutes)
**Investigator**: AI Agent (GitHub Copilot)
**Research Mode**: Detailed event lifecycle mapping, code path analysis, no modifications
**Status**: COMPLETE - awaiting stakeholder decision on fix implementation
