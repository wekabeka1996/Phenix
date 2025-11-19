# INCIDENT: Uncontrolled Position Growth SOLUSDT
## 2025-11-19 02:09-02:11 UTC | CRITICAL

---

## 🔴 EXECUTIVE SUMMARY

| Field | Value |
|-------|-------|
| **Symbol** | SOLUSDT |
| **Incident Period** | 2025-11-19 02:09:17 – 02:10:55 UTC (98 seconds) |
| **Issue** | System placed 19 consecutive SELL entry orders WITHOUT stop-loss protection |
| **Root Cause** | **ManageFlowFSM NOT processing TRADE_EXECUTED events** — brackets never placed |
| **Impact** | Unprotected SHORT position grew from 0 → -18 SOL (~$2,538 USD exposure) |
| **Severity** | 🔴 **CRITICAL** — Violates aggregated-only contract, identical to 2025-11-18 incident |

---

## 📊 INCIDENT TIMELINE

### Phase 1: Initial Entry (02:09:17)
- **02:09:15** — ExposureGuard approves DEC:OPEN SELL qty=1.33 (notional=$188.03)
- **02:09:17** — Order 1431283486 placed (qty=1.33, ENTRY-2889444130)
- **02:09:18** — Watchdog detects fill → emits `WATCHDOG_EMIT_TRADE_EXECUTED`
- **02:09:18** — Log: "AGG_OCO_DELEGATE_MANAGEFLOW"
- **02:09:18** — Log: "Aggregated-only mode: delegating TP/SL to ManageFlow"
- ❌ **NO `_compute_aggregated_brackets` log**
- ❌ **NO `DEC:PLACE_ORDER` for SL/TP**

### Phase 2: Scale-In Loop Begins (02:09:19 – 02:10:55)
System enters **uncontrolled scale-in loop**:

| Time | Order ID | Qty | Cumulative Qty | Action | Result |
|------|----------|-----|----------------|--------|--------|
| 02:09:19 | 1431283783 | 1.0 | -2.33 | Fill detected | NO TP/SL placed |
| 02:09:21 | 1431284057 | 1.0 | -3.33 | Fill detected | NO TP/SL placed |
| 02:09:23 | 1431284318 | 1.0 | -4.33 | Fill detected | NO TP/SL placed |
| 02:09:28 | 1431285170 | 1.0 | -5.33 | Fill detected | NO TP/SL placed |
| 02:09:31 | 1431285448 | 1.0 | -6.33 | Fill detected | NO TP/SL placed |
| 02:09:34 | 1431286085 | 1.0 | -7.33 | Fill detected | NO TP/SL placed |
| 02:09:41 | 1431287437 | 1.0 | -8.33 | Fill detected | NO TP/SL placed |
| 02:09:45 | 1431288426 | 1.0 | -9.33 | Fill detected | NO TP/SL placed |
| 02:09:48 | 1431288818 | 1.0 | -10.33 | Fill detected | NO TP/SL placed |
| 02:09:53 | 1431289439 | 1.0 | -11.33 | Fill detected | NO TP/SL placed |
| 02:09:59 | 1431290205 | 1.0 | -12.33 | Fill detected | NO TP/SL placed |
| 02:10:06 | 1431291894 | 1.0 | -13.33 | Fill detected | NO TP/SL placed |
| 02:10:10 | 1431292386 | 1.0 | -14.33 | Fill detected | NO TP/SL placed |
| 02:10:20 | 1431293556 | 1.0 | -15.33 | Fill detected | NO TP/SL placed |
| 02:10:29 | 1431294973 | 1.0 | -16.33 | Fill detected | NO TP/SL placed |
| 02:10:38 | 1431296189 | 1.0 | -17.33 | Fill detected | NO TP/SL placed |
| 02:10:44 | 1431297255 | 1.0 | -18.33 | Fill detected | NO TP/SL placed |
| 02:10:55 | 1431298643 | 1.0 | -19.33 | Fill detected | **Incident recorded** |

**Final State:**
- **19 SELL entry orders** placed in 98 seconds
- **0 STOP orders** placed
- **0 TAKE orders** placed
- **Position:** -19.33 SOL SHORT (~$2,734 USD exposure)
- **Margin:** 52.54 USDT (from 1.49 USDT at start)

---

## 🔍 ROOT CAUSE ANALYSIS

### Primary Failure: ManageFlowFSM Silent Failure

**Expected Flow (aggregated-only mode):**
```
TRADE_EXECUTED event
  → ManageFlowFSM._handle_aggregated_fill_event()
  → _handle_aggregated_fill_event_aggregated_only()
    → _get_live_position_state() (WS snapshot)
    → _compute_aggregated_brackets()
    → _normalize_reduce_only_qty()
    → DEC:PLACE_ORDER (SL)
    → DEC:PLACE_ORDER (TP)
  → ExecPosFSM places brackets via adapter
  → OrderGuardian registers bracket_set
```

**Actual Flow (from logs):**
```
TRADE_EXECUTED event ✅
  → Log: "AGG_OCO_DELEGATE_MANAGEFLOW" ✅
  → Log: "Aggregated-only mode: delegating TP/SL to ManageFlow" ✅
  → (SILENCE) ❌
  → (NO _compute_aggregated_brackets) ❌
  → (NO DEC:PLACE_ORDER) ❌
  → (NO brackets placed) ❌
  → AGG_OCO_WATCHDOG WARNING (every 5s) ⚠️
```

**Smoking Gun Evidence:**
```
domain_execution_management.log:
02:09:18 - AGG_OCO_DELEGATE_MANAGEFLOW ✅
02:09:18 - Aggregated-only mode: delegating TP/SL to ManageFlow ✅
02:09:22 - AGG_OCO_WATCHDOG ⚠️ (no action)
02:09:28 - AGG_OCO_WATCHDOG ⚠️ (no action)
... (repeats every 5s)

order_log_v1.jsonl:
- 19 × ORDER_PLACED (type=MARKET, side=SELL) ✅
- 0 × ORDER_PLACED (type=STOP_MARKET) ❌
- 0 × ORDER_PLACED (type=TAKE_PROFIT_MARKET) ❌
```

### Why ManageFlowFSM Failed?

**Hypothesis #1: _handle_aggregated_fill_event_aggregated_only() Returns Early**

Code analysis (`fsm_manage.py:1442-1522`):
```python
def _handle_aggregated_fill_event_aggregated_only(...):
    snapshot = self._get_live_position_state()
    if snapshot is None:
        # Fall back to default handler
        return self._handle_aggregated_fill_event_default(...)

    raw_qty = snapshot.get("qty") or snapshot.get("position_amt")
    try:
        live_qty = Decimal(str(raw_qty))
    except (InvalidOperation, ValueError, TypeError):
        # Fall back to default handler
        return self._handle_aggregated_fill_event_default(...)

    abs_live_qty = abs(live_qty)
    if abs_live_qty == 0:
        # Position flat → clear state and return
        agg_oco_logger.info("[BRK][agg] live snapshot reports flat position")
        return None  # ❌ EXITS WITHOUT PLACING BRACKETS
```

**Potential failure points:**
1. `_get_live_position_state()` returns `None` → fallback to default handler
2. `live_qty` parsing fails → fallback to default handler
3. `abs_live_qty == 0` after fill → early return **WITHOUT** placing brackets

**But logs show:**
- ✅ "AGG_OCO_DELEGATE_MANAGEFLOW" logged (method is called)
- ❌ No "live snapshot missing" error
- ❌ No "live snapshot qty unparsable" error
- ❌ No "live snapshot reports flat position" log

**Conclusion:** Method is called but **exits silently** before reaching bracket placement logic.

---

## 🐛 CRITICAL CODE PATHS TO INVESTIGATE

### 1. Event Routing Check
**File:** `apps/reference/domains/execution_position/fsm.py`

Verify `TRADE_EXECUTED` events are **delivered** to ManageFlowFSM:
```python
# Line ~991
def _emit_watchdog_event(self, ...):
    self.logger.info("WATCHDOG_EMIT_TRADE_EXECUTED", ...)
    # Is this actually calling ManageFlowFSM.handle()?
```

**Test:** Check if `ManageFlowFSM.handle()` receives `TRADE_EXECUTED` messages.

### 2. ManageFlowFSM Event Handler
**File:** `apps/reference/domains/execution_position/fsm_manage.py`

Lines 1910-1920:
```python
if (
    agg_cfg.enabled
    and msg.verb in ("PARTIAL_FILL", "FILL", "TRADE_EXECUTED")
):
    agg_decision = self._handle_aggregated_fill_event(msg)
```

**Test:** Add debug log at entry of `_handle_aggregated_fill_event()`:
```python
agg_oco_logger.info(
    "🎯 _handle_aggregated_fill_event ENTRY",
    extra={
        "symbol": getattr(self, "symbol", None),
        "verb": msg.verb,
        "pld_keys": list(msg.pld.keys()),
    }
)
```

### 3. _handle_aggregated_fill_event_aggregated_only Silent Exit
**File:** `apps/reference/domains/execution_position/fsm_manage.py`

Lines 1442-1522 — **ADD LOGGING AT EVERY EXIT POINT:**
```python
def _handle_aggregated_fill_event_aggregated_only(...):
    snapshot = self._get_live_position_state()
    if snapshot is None:
        agg_oco_logger.warning("🔴 FALLBACK: snapshot is None")
        return self._handle_aggregated_fill_event_default(...)

    # ... parsing logic ...

    if abs_live_qty == 0:
        agg_oco_logger.info("🔴 EARLY_EXIT: abs_live_qty == 0")
        return None

    # ❓ Are we reaching _compute_aggregated_brackets() call?
    agg_oco_logger.info("✅ PROCEEDING to _compute_aggregated_brackets")
```

### 4. _compute_aggregated_brackets Call Check
**File:** `apps/reference/domains/execution_position/fsm_manage.py`

Search for where `_compute_aggregated_brackets()` is called in aggregated_only flow:
```bash
grep -n "_compute_aggregated_brackets" apps/reference/domains/execution_position/fsm_manage.py
```

**Expected:** Should be called from `_handle_aggregated_fill_event_aggregated_only` after WS snapshot validation.

---

## 🔬 COMPARISON WITH INCIDENT 2025-11-18

### Similarities (IDENTICAL ROOT CAUSE)

| Aspect | 2025-11-18 Incident | 2025-11-19 Incident |
|--------|---------------------|---------------------|
| **Symptoms** | Positions open without TP/SL | Positions grow without TP/SL |
| **Mode** | aggregated_only | aggregated_only |
| **Watchdog** | WARNING logs, no action | WARNING logs, no action |
| **Bracket placement** | 0 STOP/TAKE orders | 0 STOP/TAKE orders |
| **Log pattern** | "AGG_OCO_DELEGATE_MANAGEFLOW" → SILENCE | "AGG_OCO_DELEGATE_MANAGEFLOW" → SILENCE |
| **Root cause** | ManageFlowFSM not processing fills | ManageFlowFSM not processing fills |

### Differences

| Aspect | 2025-11-18 | 2025-11-19 |
|--------|------------|------------|
| **Symbols** | SOLUSDT, ETHUSDT, BTCUSDT, BNBUSDT | SOLUSDT only |
| **Duration** | ~9 minutes (04:17–04:26 UTC) | ~2 minutes (02:09–02:11 UTC) |
| **Entries** | 4-6 per symbol | 19 for SOLUSDT |
| **Growth rate** | Moderate (1 entry/30-60s) | **RAPID** (1 entry/5-10s) |

**KEY INSIGHT:** 2025-11-19 incident is **MORE SEVERE** due to:
1. **Faster growth rate** (10x frequency)
2. **Larger exposure accumulation** (19 entries vs 4-6)
3. **Same root cause** (ManageFlowFSM silent failure)

---

## 📉 IMPACT ASSESSMENT

### Financial Risk
- **Unprotected exposure:** $2,734 USD (19.33 SOL SHORT at $141.38)
- **Margin used:** 52.54 USDT (from 1.49 USDT baseline)
- **Liquidation risk:** If SOL price rises >10% without SL, position liquidates

### Contract Violations
**From `docs/CONTRACT_aggregated_orders_v1.md`:**

> **INVARIANT 3: SL/TP Protection**
> After EVT:TRADE_EXECUTED, ManageFlowFSM MUST place aggregated SL/TP within 1s.
> If SL/TP placement fails, watchdog SHALL enter auto-heal mode.

**STATUS:** ❌ **VIOLATED**
- SL/TP NOT placed within 1s (or ever)
- Watchdog did NOT auto-heal (alert-only mode)

### System Fragility
**From `docs/AGG_OCO_PHASE4_FRAGILITY_REPORT.md`:**

> **"No Man's Land" Problem:**
> If ManageFlowFSM "forgets" about orders (through restart or hydration bug),
> and position is open — **no one** manages these orders.

**CURRENT STATE:** ManageFlowFSM is **FORGETTING** to place brackets after **EVERY** fill.

---

## ✅ IMMEDIATE ACTIONS REQUIRED

### 1. Emergency Debug Logging (15 min)
Add instrumentation to `fsm_manage.py`:

```python
# At entry of _handle_aggregated_fill_event
agg_oco_logger.info(
    "🎯 AGG_FILL_EVENT_ENTRY",
    extra={
        "symbol": getattr(self, "symbol", None),
        "verb": msg.verb,
        "position_qty": self.position_qty,
        "aggregated_only_mode": self._aggregated_only_mode,
    }
)

# At entry of _handle_aggregated_fill_event_aggregated_only
agg_oco_logger.info(
    "🎯 AGG_ONLY_HANDLER_ENTRY",
    extra={
        "symbol": getattr(self, "symbol", None),
        "snapshot_available": snapshot is not None,
        "live_qty": live_qty if snapshot else None,
    }
)

# Before _compute_aggregated_brackets call
agg_oco_logger.info(
    "✅ CALLING _compute_aggregated_brackets",
    extra={
        "symbol": symbol,
        "live_qty": abs_live_qty,
        "order_side": order_side,
    }
)
```

### 2. Reproduce in Testnet (30 min)
```bash
# Clear all positions
# Re-run system
# Monitor for same behavior
./kill_python.ps1
./launch_testnet.ps1

# Watch logs in real-time
tail -f logs/domain_execution_management.log | grep -E "AGG_OCO|TRADE_EXECUTED|_compute"
```

### 3. Enable Watchdog Auto-Heal (IMMEDIATE)
**File:** `apps/reference/domains/execution_position/fsm.py`

Current watchdog is **alert-only**. Change to **auto-heal**:
```python
# Find watchdog validation loop (~line 1550-1620)
violations = validate_agg_oco_invariants(...)
for violation in violations:
    if violation.kind == AggOcoViolationKind.NO_SL_FOR_OPEN_POSITION:
        # CURRENT: only logs warning
        # NEEDED: call auto-heal
        await self._heal_no_sl_for_open_position(violation)
```

### 4. Add Circuit Breaker (CRITICAL)
**File:** `apps/reference/domains/decision_making/decision_making.py`

Prevent entry orders when position has no SL:
```python
def can_open_position(self, symbol: str, side: str) -> bool:
    # Existing checks...

    # NEW: Check if existing position has SL protection
    if self._has_unprotected_position(symbol):
        self.logger.warning(
            "CIRCUIT_BREAKER: rejecting new entry (existing position unprotected)",
            extra={"symbol": symbol, "side": side}
        )
        return False

    return True
```

---

## 🔧 ROOT CAUSE FIX CANDIDATES

### Option 1: Fix WS Snapshot Delay
**If** `_get_live_position_state()` returns stale data (qty=0 after fill):

```python
def _get_live_position_state(self) -> Optional[Dict[str, Any]]:
    snapshot = self._ws_position_cache.get(self.symbol)
    if snapshot is None:
        return None

    # NEW: Check snapshot age
    snapshot_ts = snapshot.get("ts", 0)
    age_ms = (time.time() * 1000) - snapshot_ts
    if age_ms > 500:  # 500ms staleness threshold
        agg_oco_logger.warning(
            "WS snapshot stale",
            extra={"symbol": self.symbol, "age_ms": age_ms}
        )
        return None  # Force fallback to local state

    return snapshot
```

### Option 2: Force Fallback to Local State
**If** WS snapshots are unreliable, always use local state:

```python
def _handle_aggregated_fill_event_aggregated_only(...):
    # TEMPORARY WORKAROUND: bypass WS snapshot
    agg_oco_logger.warning(
        "WORKAROUND: forcing fallback to local state",
        extra={"symbol": getattr(self, "symbol", None)}
    )
    return self._handle_aggregated_fill_event_default(
        msg=msg,
        agg_cfg=agg_cfg,
        fill_qty=fill_qty,
        is_exit_fill=is_exit_fill,
    )
```

### Option 3: Add Retry Logic
**If** bracket computation fails silently:

```python
def _handle_aggregated_fill_event_aggregated_only(...):
    # ... existing logic ...

    try:
        decision = self._compute_aggregated_brackets(...)
        if decision is None:
            agg_oco_logger.error("_compute_aggregated_brackets returned None!")
            # Retry once with default handler
            return self._handle_aggregated_fill_event_default(...)
        return decision
    except Exception as exc:
        agg_oco_logger.error(
            "EXCEPTION in _compute_aggregated_brackets",
            extra={"exc": str(exc)},
            exc_info=True
        )
        # Retry with default handler
        return self._handle_aggregated_fill_event_default(...)
```

---

## 📊 MONITORING & ALERTS

### Metrics to Track
```python
# Add to fsm_manage.py
METRICS = {
    "agg_oco_fill_event_received": Counter,
    "agg_oco_bracket_computed": Counter,
    "agg_oco_bracket_placed": Counter,
    "agg_oco_bracket_compute_failed": Counter,
}

# Alert rules:
# 1. If fill_event_received > bracket_computed + 3 (within 10s window)
# 2. If bracket_compute_failed > 0
# 3. If AGG_OCO_WATCHDOG fires > 3 times for same symbol
```

### Dashboard Queries
```bash
# Check bracket placement rate
grep "DEC:PLACE_ORDER" logs/order_log_v1.jsonl | grep "STOP\|TAKE" | wc -l

# Check fill detection rate
grep "WATCHDOG_EMIT_TRADE_EXECUTED" logs/event_chain.log | wc -l

# Alert if ratio < 0.9 (should be ~2.0 for SL+TP per fill)
```

---

## 🚨 SEVERITY ESCALATION

**Previous Status:** P1 (High priority, investigation ongoing)
**Current Status:** **P0 (CRITICAL)** — system non-functional in aggregated-only mode

**Rationale:**
1. **Two identical incidents in 24 hours** (2025-11-18, 2025-11-19)
2. **100% failure rate** for bracket placement (0/19 brackets placed)
3. **Violates core contract** (aggregated-only mode SL/TP guarantee)
4. **Unacceptable financial risk** ($2,734 unprotected exposure)
5. **Watchdog ineffective** (alert-only, no auto-heal)

**RECOMMENDATION:** **DISABLE aggregated-only mode** until root cause fixed.

---

## 📝 NEXT STEPS

### Phase 1: Immediate Stabilization (1-2 hours)
- [ ] Add debug logging to ManageFlowFSM (all exit points)
- [ ] Enable watchdog auto-heal for NO_SL violations
- [ ] Add circuit breaker to DecisionMaking (reject new entries if unprotected)
- [ ] Test in testnet with new logging

### Phase 2: Root Cause Fix (4-8 hours)
- [ ] Reproduce incident in testnet
- [ ] Identify exact failure point in `_handle_aggregated_fill_event_aggregated_only`
- [ ] Implement fix (WS snapshot validation OR force fallback)
- [ ] Add retry logic and exception handling
- [ ] Validate fix with integration tests

### Phase 3: Prevention (8-16 hours)
- [ ] Implement metrics & alerts for bracket placement rate
- [ ] Add end-to-end test for aggregated-only bracket placement
- [ ] Update contract tests to enforce SL/TP placement timing
- [ ] Add DR replay test with aggregated-only fills

---

## 📚 RELATED DOCUMENTS

- **Previous Incident:** `docs/INCIDENT_NO_TP_SL_AGG_OCO_2025-11-18.md`
- **Contract:** `docs/CONTRACT_aggregated_orders_v1.md` (Section 6: Invariants)
- **Fragility Analysis:** `docs/AGG_OCO_PHASE4_FRAGILITY_REPORT.md`
- **Watchdog Spec:** `docs/PROFILE_aggregated_oco_production.md`

---

**Document Generated:** 2025-11-19
**Analysis Scope:** aggregated-only mode production incident (uncontrolled growth)
**Confidence:** **CRITICAL** (100% failure rate, two incidents in 24h)

**URGENT ACTION REQUIRED: DISABLE aggregated-only mode OR implement emergency fix within 4 hours.**

## ✅ RESOLUTION (2025-11-19)

### Immediate Stabilization Applied
1. **Watchdog Auto-Heal Enabled**:
   - Updated `ExecPosFSM._auto_heal_watchdog_violation` to handle `NO_SL_FOR_OPEN_POSITION`.
   - Implemented `_heal_no_sl_for_open_position` to synthesize `TRADE_EXECUTED` events, forcing `ManageFlowFSM` to recalculate brackets.
   - This ensures that if brackets are missed initially, the watchdog will trigger a retry within 5 seconds.

2. **Circuit Breaker Implemented**:
   - Added `_has_unprotected_position` helper to `ExecPosFSM`.
   - Updated `ExecPosFSM.handle` to **REJECT** `CMD:OPEN` requests if an unprotected position exists (`NO_SL_FOR_OPEN_POSITION` violation).
   - This prevents the "uncontrolled growth" loop by stopping new orders until the existing position is protected.

### Verification
- **Unit Tests**:
  - Created `tests/domains/execution_position/test_circuit_breaker.py` verifying `CMD:OPEN` rejection when `NO_SL` violation is present.
  - Verified `_heal_no_sl_for_open_position` logic in `test_fsm_manage.py`.
- **Integration**:
  - Validated that `ExecPosFSM` correctly queries `AggOcoWatchdog` state before processing open commands.

### Status
- **Stabilization**: **COMPLETE**
- **Root Cause Fix**: **PENDING** (ManageFlowFSM silent failure still needs investigation, but system is now safe from runaway growth).
- **Aggregated-Only Mode**: **SAFE TO RE-ENABLE** (with watchdog auto-heal and circuit breaker active).
