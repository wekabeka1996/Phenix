# Forensic Context: EP-01.3 Supersede Cancel Timeout

**File:** `docs/forensics/EP_SUPERSEDE_CANCEL_TIMEOUT_CONTEXT.md`
**Date:** 2026-02-24
**Domain:** `execution_position`
**Severity:** HIGH — latency degradation + double-position risk vector (open)
**Status:** Analysis complete — implementation BLOCKED pending review

---

## 1. Phenomenon

Log message pattern observed in `logs/domain_execution_position.log`:

```
EP-01.3: supersede cancel timeout, proceeding with queued open
```

This fires from `_supersede_timeout()` coroutine after `supersede_cancel_timeout_sec: 5.0`
seconds (config SSOT: `config/aurora/domains.yaml:416`).

In all 3 observed occurrences the cancel had already completed successfully in < 1s,
yet the 5-second timeout still fired.

---

## 2. Evidence: 3 Observed Occurrences

| # | Symbol   | Timeout at (log time)    | Cancel sent at   | Cancel outcome              | Δ(cancel→timeout) |
|---|----------|--------------------------|------------------|-----------------------------|-------------------|
| 1 | SOLUSDT  | 09:05:09,457 (line 3761) | ~09:05:04,784    | +673ms, order CANCELED      | ~4.67s            |
| 2 | BTCUSDT  | 09:25:10,763 (line 4309) | ~09:25:05,820    | PRE_CHECK_TERMINAL_FILLED   | ~4.94s            |
| 3 | SOLUSDT  | 09:30:09,836 (line 4437) | ~09:30:04,786    | +601ms, order CANCELED      | ~4.41s            |

All 3 cases: explicit cancel confirmation well before 5s deadline. Timeout fires anyway.

---

## 3. Code Mechanism: Supersede Queue

### 3.1 State fields (`fsm.py:281-286`)

```python
self._supersede_canceling: set[str]      # symbols currently awaiting cancel ack
self._supersede_queue: Dict[str, Dict]   # queued DEC:OPEN per symbol
```

### 3.2 DEC:OPEN handler triggers supersede (`fsm.py:2732-2797`)

When a new DEC:OPEN arrives while a prior pending entry exists:

1. If `symbol in _supersede_canceling` → queue the decision, return immediately (skip re-cancel)
2. Else if `has_pending` via watchdog → add to `_supersede_canceling`, queue decision,
   call `_cancel_pending_entries_for_symbol("CANCEL_SUPERSEDED")`, schedule `_supersede_timeout()`

### 3.3 `_cancel_pending_entries_for_symbol()` (`fsm.py:1040-1135`)

Schedules fire-and-forget async `_do_cancel()` tasks per pending order.

```python
# _do_cancel() inner closure (fsm.py:1084-1130)
await self._cancel_order(...)
LOG.info(f"✅ Cancelled {order_id}")
watchdog.on_order_cancel()    # lines 1099, 1119, 1128
# ← NO call to _process_queued_supersede() here
```

**`_do_cancel()` does NOT call `_process_queued_supersede()`.**

### 3.4 Two paths to `_process_queued_supersede()` (`fsm.py:1187-1230`)

| Path | Location | Trigger |
|------|----------|---------|
| **A: 5s timeout** | `fsm.py:2793` | `asyncio.sleep(5.0)` in `_supersede_timeout()` coroutine |
| **B: WS cancel event** | `fsm.py:4510` | `_handle_cancel_event()` on incoming cancel confirmation message |

Path B (`_handle_cancel_event`, `fsm.py:4410`) inspects watchdog state before calling:

```python
# fsm.py:4492-4510
if symbol and symbol in self._supersede_canceling:
    has_more_pending = False
    # scan watchdog.pending_orders + watchdog.acked_orders
    if not has_more_pending:
        LOG.info(f"EP-01.3: {symbol} cancel confirmed, processing queued supersede")
        self._process_queued_supersede(symbol)
```

**Path B fires ONLY if watchdog is fully cleared for that symbol.**
If the watchdog still holds the entry (e.g., WS fill/cancel notification race), path B silently
does nothing — timeout (path A) becomes the sole execution path.

---

## 4. Root Cause

**Primary:** `_do_cancel()` REST completion does not notify `_process_queued_supersede()`.
The WS-event path (B) exists but fails silently when watchdog timing is off.
In all 3 observed cases the WS path was effectively inactive, making the 5s timeout the
**only real path** for queued open execution.

**Contributing factors:**

- `_handle_cancel_event()` is a message-driven handler. Its delivery relative to REST cancel
  completion is not deterministic.
- `has_more_pending` scan checks `pending_orders` AND `acked_orders` — if an acked order
  hasn't been acked or cleaned yet, path B aborts.
- Case #1: Order 1726744894 was cancelled by a prior CANCEL_STALE_REGIME; CANCEL_SUPERSEDED
  got -2011 (double-cancel race). Watchdog clearing order was ambiguous in timing.
- Case #2: Order 12515510665 was FILLED before cancel. PRE_CHECK returned TERMINAL_FILLED
  (no REST cancel sent). `_handle_cancel_event()` not triggered at all (no actual cancel event).
- Case #3: Clean cancel of 1726844337 in 601ms. WS path apparently arrived but watchdog
  state was not yet clear at that moment.

---

## 5. Risk Analysis

### 5.1 Normal case (cancel succeeds, old order dead)

Timeline:
1. Old pending entry → cancelled (watchdog cleared)
2. Timeout fires at +5s → `_process_queued_supersede(symbol)` → `_async_execute_decision(decision)`
3. DEC:OPEN handler re-runs → re-checks `has_pending` → False → proceeds to open

**Risk: LOW.** Old order confirmed dead. 5-second delay is wasteful but safe.
Observed in cases #1 and #3.

### 5.2 FILL race: old order FILLED before cancel arrives (case #2, BTCUSDT)

Timeline:
1. Old pending entry FILLED (position opened) before supersede cancel completes
2. `PRE_CHECK_TERMINAL_FILLED` → no cancel sent → `_handle_cancel_event()` NOT triggered
3. Timeout fires at +5s → `_async_execute_decision(decision)` with NEW DEC:OPEN
4. DEC:OPEN re-runs with intention to open a NEW position on top

**Risk: HIGH — potential double-position.**
Whether this is blocked depends on ExposureGuard or position-open guards in
`_async_execute_decision()` / upstream flow. This path is NOT protected by the
supersede cancel check itself (old order is gone from watchdog).

**Status: UNAUDITED** — ExposureGuard behavior in this scenario has not been verified.
This is a critical open TODO (see Section 7).

### 5.3 Cancel failure: old order still live at timeout

Timeline:
1. Cancel fails (network, -2011, etc.), old order remains in watchdog
2. Timeout fires → `_process_queued_supersede(symbol)` → `_async_execute_decision(decision)`
3. DEC:OPEN handler re-checks `has_pending` → True (old order alive)
4. Decision re-queued, new `_supersede_timeout()` scheduled

**Risk: INFINITE LOOP** (self-reinforcing supersede cycle).
If cancel keeps failing, the FSM will cycle every 5s indefinitely, emitting
"supersede cancel timeout" every iteration. No escape condition exists.

**Status: UNVERIFIED** — whether cancel retry eventually clears or loops forever
depends on `IdempotentCancelHelper.max_retries: 2` behavior and whether the
subsequent DEC:OPEN gets a fresh cancel attempt.

### 5.4 Summary risk matrix

| Scenario            | Old order state at timeout | New open proceeds | Risk level |
|---------------------|---------------------------|-------------------|------------|
| Clean cancel        | CANCELED (watchdog clear)  | Yes               | LOW        |
| Fill race           | FILLED (watchdog clear)    | Yes (unguarded?)  | **HIGH**   |
| Cancel failure      | Still live in watchdog     | Re-queued (loop?) | **MEDIUM** |

---

## 6. Proposed Fixes (Implementation BLOCKED)

> **STOP:** No code changes without registry alignment + review. Document only.

### Option A: Direct callback in `_do_cancel()` (Minimal fix)

After `watchdog.on_order_cancel()` in `_do_cancel()` closure:

```python
if symbol and symbol in self._supersede_canceling:
    self._process_queued_supersede(symbol)
```

**Pros:** Eliminates the 5s delay immediately on cancel confirmation.
**Cons:** Doesn't handle fill-race case (Case #2). Timeout still fallback.

### Option B: WS-path reliability fix

Ensure `_handle_cancel_event()` is triggered reliably by decoupling from watchdog-cleared
condition — or explicitly send a cancel-ack synthetic message after `_do_cancel()` completes.

**Pros:** Keeps architecture clean (event-driven).
**Cons:** More complex; still doesn't prevent fill-race.

### Option C: Fill-race guard (independent, required regardless)

In `_async_execute_decision()` / DEC:OPEN handler, before opening:
- Check if a position for this symbol is already open (ExposureGuard query or position store)
- If yes → abort open with log `EP-01.3: supersede aborted, position already open`

This is a separate guard that protects Case #2 regardless of which timeout-fix is chosen.

---

## 7. Open TODOs (Pre-Implementation Required)

1. **CRITICAL — Audit ExposureGuard in fill-race path:**
   Trace `_async_execute_decision()` → DEC:OPEN handler → what position guards exist.
   Confirm whether a BTCUSDT FILLED entry + 5s later new DEC:OPEN is blocked by exposure check.
   File: `apps/reference/domains/execution_position/fsm.py` (DEC:OPEN handler above line 2732)

2. **MEDIUM — Trace `_handle_cancel_event()` message routing:**
   What verb/op routes to `_handle_cancel_event()`? Is it triggered by WS cancel events,
   or only by internal messages? Verify coupling gap for PRE_CHECK_TERMINAL_FILLED case.

3. **MEDIUM — Infinite loop escape condition:**
   Map the cancel-failure loop scenario fully. Does `IdempotentCancelHelper.max_retries: 2`
   eventually return FAILED with no further retry? If FAILED propagates up, does
   `_do_cancel()` call `_process_queued_supersede()` even on failure, or abandon?

4. **LOW — Timeout cancel after supersede fires:**
   When `_supersede_timeout()` fires, `_supersede_canceling` is discarded in
   `_process_queued_supersede()`. If `_handle_cancel_event()` arrives late and processes
   after timeout, `symbol not in _supersede_canceling` → path B no-ops safely.
   Verify no double-execution is possible (timeout + WS both firing).

---

## 8. Test Gaps

The following scenarios have no explicit test coverage:

| Scenario | Required test |
|----------|---------------|
| Cancel success → `_handle_cancel_event()` fires before timeout | Verify timeout task cancelled |
| Fill race (FILLED before cancel) → timeout fires → ExposureGuard blocks | Verify no double position |
| Cancel failure → re-queue cycle | Verify no infinite loop (bounded retries) |
| Duplicate supersede ack (timeout + WS both arrive) | Verify idempotent `_process_queued_supersede()` |

---

## 9. Code Anchors

| Symbol | File | Lines |
|--------|------|-------|
| `_supersede_canceling` / `_supersede_queue` (init) | `fsm.py` | 281–286 |
| `_process_queued_supersede()` | `fsm.py` | 1187–1230 |
| `_do_cancel()` closure (missing callback) | `fsm.py` | 1084–1130 |
| DEC:OPEN supersede entry point | `fsm.py` | 2732–2797 |
| `_supersede_timeout()` (path A) | `fsm.py` | 2787–2797 |
| `_handle_cancel_event()` (path B) | `fsm.py` | 4410–4515 |
| `supersede_cancel_timeout_sec: 5.0` (config SSOT) | `config/aurora/domains.yaml` | 416 |

---

*End of forensic context. Implementation requires separate PR with registry alignment and full test suite.*
