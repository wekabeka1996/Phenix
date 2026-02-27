# EP_IDEMPOTENT_CANCEL_2011_CONTEXT

**Domain:** `execution_position`
**Error:** `IDEMPOTENT_CANCEL: Exception on attempt N: [-2011] Unknown order sent.`
**Classification:** `CONCURRENT_DUPLICATE_CANCEL + EXCEPTION_ABSORPTION_GAP`
**Status:** Root cause confirmed. No code changes in this task.
**Date:** 2026-02-24

---

## Executive Summary

- **2 confirmed -2011 fails** in the observation window (`domain_execution_position.log`, lines 3709 and 3732), both against the same order (`1726744894`, BTCUSDT LIMIT SELL) on 2026-02-24 09:05:05.
- **Root cause #1 (structural bug):** `IdempotentCancelHelper.cancel_order_idempotent()` absorbs `-2011` only from the API response **dict** path (`result.get("code") == -2011`). When `adapter.cancel_order()` raises a `BinanceAPIError(code=-2011)`, the exception handler treats it as a **transient error** and retries, eventually returning `success=False`.
- **Root cause #2 (silent false-positive log):** The FSM's `_do_cancel()` coroutine logs `"✅ EP-01.3: Cancelled pending entry {oid} ({reason})"` unconditionally after `self._cancel_order()` returns, regardless of whether `res.success is True or False`. The FAILED result is silently swallowed and "✅" is emitted — misleading operators.
- **Root cause #3 (structural race):** One order receives **two independent cancel requests** (`CANCEL_STALE_REGIME` and `CANCEL_SUPERSEDED`) issued ~281 ms apart. Both schedule concurrent async tasks. The pre-check for the second cancel runs before the first cancel's API response arrives, so both see `before=NEW` and both attempt the Binance DELETE call. The first wins; the second gets `-2011`.
- **No orders were lost.** The -2011 scenario is benign: the order is provably absent from Binance in all observed cases. The desired state (order gone) is achieved.
- **`PRE_CHECK_TERMINAL_FILLED` path works correctly:** 4 occurrences in both log files where a LIMIT entry was FILLED before cancel; the pre-check correctly short-circuits with `success=True reason=PRE_CHECK_TERMINAL_FILLED`. No -2011 issued in those cases.
- **Existing tests cover the dict-path -2011 absorption** but NOT the exception-path. The regression gap corresponds exactly to the production failure.

---

## Evidence Table

| # | Log Line | Timestamp | Symbol | order_id | Flow / Trigger | `before` | `after` | Result |
|---|---|---|---|---|---|---|---|---|
| 1 | 3709 (`log`) | 09:05:05,082 | BTCUSDT | `1726744894` | `CANCEL_SUPERSEDED` attempt 1 | `NEW` | `None` | FAILED (exception) |
| 2 | 3732 (`log`) | 09:05:05,547 | BTCUSDT | `1726744894` | `CANCEL_SUPERSEDED` attempt 2 | `NEW` | `None` | FAILED (exception) |
| 3 | 3733 (`log`) | 09:05:05,549 | BTCUSDT | `1726744894` | `CANCEL_SUPERSEDED` audit | `NEW` | `None` | `status=FAILED reason=EXCEPTION_AFTER_2_RETRIES` |

### Normal (success) cancel events in the same period (`log`)

| Lines | Timestamp | Symbol | order_id | Reason | Before → After |
|---|---|---|---|---|---|
| 3697–3698 | 09:05:04,841–843 | BTCUSDT (SOLUSDT) | `1726744894` | `CANCEL_STALE_REGIME` | `NEW → CANCELED` ✅ |
| 4303–4304 | 09:25:06,021–023 | BTCUSDT | `12515510665` | `CANCEL_SUPERSEDED` | `FILLED → FILLED` (pre-check) ✅ |
| 4306–4307 | 09:25:06,071–071 | BTCUSDT | `12515510665` | `CANCEL_STALE_REGIME` | `FILLED → FILLED` (pre-check) ✅ |
| 4426–4427 | 09:30:05,414–420 | SOLUSDT | `1726844337` | `CANCEL_SUPERSEDED` | `NEW → CANCELED` ✅ |

### No `-2011` occurrences found in `log.1` (2026-02-23 period)

All IDEMPOTENT_CANCEL events in `log.1` resolved via:
- `PRE_CHECK_TERMINAL_FILLED` (order 12495815602, 12502352941, 1724559552) — already FILLED
- `CANCEL_SUCCESS` at attempt 1 — order still NEW, canceled cleanly

---

## Log Context Blocks

### Block A — The -2011 Failure (BTCUSDT, 2026-02-24 09:05)

```text
09:05:04,163  EP-01 REGIME_ADAPTED: bucket=FLAT (regime_changed_to_MEAN_REVERSION)
09:05:04,168  EP-01.3: Cancelling 1 pending entries for SOLUSDT (reason=CANCEL_STALE_REGIME)
              ← First cancel for order 1726744894 (stale SOLUSDT entry, but actually BTCUSDT pending)
09:05:04,313  [SOLUSDT] Processing TRADE_INTENT → CMD:OPEN SELL LIMIT
09:05:04,442  EP-01.3: SOLUSDT has 1 pending entries, queueing new DEC:OPEN until cancel confirmed
09:05:04,449  EP-01.3: Cancelling 1 pending entries for SOLUSDT (reason=CANCEL_SUPERSEDED)
              ← Second cancel for the SAME order 1726744894 (new intent supersedes)
09:05:04,841  IDEMPOTENT_CANCEL: Successfully canceled order 1726744894 (attempt 1)
              ← CANCEL_STALE_REGIME wins the race (673ms RTT)
09:05:04,843  IDEMPOTENT_CANCEL_AUDIT: order_id=1726744894 status=SUCCESS reason=CANCEL_SUCCESS
              before=NEW after=CANCELED error_code=None idempotent_success=True
09:05:04,845  ✅ EP-01.3: Cancelled pending entry 1726744894 (CANCEL_STALE_REGIME)
              ← Order is now CANCELED on Binance
09:05:05,082  IDEMPOTENT_CANCEL: Exception on attempt 1: [-2011] Unknown order sent. (no-nrr)
              ← CANCEL_SUPERSEDED pre-check saw NEW (ran at ~09:05:04,750, before cancel completed at 841ms)
              ← Now tries DELETE → order already gone → BinanceAPIError(-2011) raised
09:05:05,547  IDEMPOTENT_CANCEL: Exception on attempt 2: [-2011] Unknown order sent. (no-nrr)
              ← Retry after backoff(100ms) → still -2011
09:05:05,549  IDEMPOTENT_CANCEL_AUDIT: order_id=1726744894 status=FAILED
              reason=EXCEPTION_AFTER_2_RETRIES: [-2011] Unknown order sent. (no-nrr)
              before=NEW after=None error_code=None idempotent_success=False
09:05:05,557  ✅ EP-01.3: Cancelled pending entry 1726744894 (CANCEL_SUPERSEDED)
              ← ⚠️ FALSE POSITIVE: success log fired despite res.success=False
```

**Inferred order lifecycle:**
1. Order `1726744894` placed as BTCUSDT LIMIT SELL (pending entry, watched by watchdog).
2. Regime change event triggers `CANCEL_STALE_REGIME` (09:05:04,168).
3. New SOLUSDT TRADE_INTENT triggers another `CANCEL_SUPERSEDED` for same order (09:05:04,449).
4. Both schedule concurrent async `_do_cancel()` coroutines.
5. Pre-check for CANCEL_SUPERSEDED runs at ~09:05:04,750 → sees `NEW` (first cancel not done yet).
6. CANCEL_STALE_REGIME completes at 09:05:04,841 → order is `CANCELED` on Binance.
7. CANCEL_SUPERSEDED cancel call arrives at 09:05:05,082 → order gone → `BinanceAPIError(-2011)`.
8. Exception is retried × 1, fails again, returns `FAILED`.
9. `_do_cancel()` logs `"✅ Cancelled"` incorrectly.

**Order final state:** GONE from Binance (CANCELED). No position risk. False-positive "✅" log only.

---

### Block B — PRE_CHECK_TERMINAL_FILLED (BTCUSDT order 12515510665, 09:25)

```text
09:25:05,232  EP-01 REGIME_ADAPTED: MEAN_REVERSION → FLAT
09:25:05,239  EP-01.3: Cancelling 1 pending entries for BTCUSDT (reason=CANCEL_STALE_REGIME)
09:25:05,716  📌 [LIMIT-DEFERRED] Stored pending brackets for SOLUSDT 1726844337
09:25:05,726  EP-01.3: BTCUSDT has 1 pending entries, queueing new DEC:OPEN until cancel confirmed
09:25:05,730  EP-01.3: Cancelling 1 pending entries for BTCUSDT (reason=CANCEL_SUPERSEDED)
              ← Same pattern: two cancels for BTCUSDT order 12515510665
09:25:06,021  IDEMPOTENT_CANCEL: Order 12515510665 already FILLED (pre-check), treating as success
09:25:06,023  IDEMPOTENT_CANCEL_AUDIT: order_id=12515510665 status=SUCCESS
              reason=PRE_CHECK_TERMINAL_FILLED before=FILLED after=FILLED
09:25:06,071  IDEMPOTENT_CANCEL: Order 12515510665 already FILLED (pre-check), treating as success
09:25:06,071  IDEMPOTENT_CANCEL_AUDIT: order_id=12515510665 status=SUCCESS
              reason=PRE_CHECK_TERMINAL_FILLED before=FILLED after=FILLED
09:25:10,763  EP-01.3: BTCUSDT supersede cancel timeout, proceeding with queued open
```

**Inferred order lifecycle:**
- Order `12515510665` BTCUSDT LIMIT BUY was FILLED before either cancel was requested.
- Both cancels short-circuit via pre-check with `PRE_CHECK_TERMINAL_FILLED`. No Binance DELETE called.
- **This path works correctly.** The pre-check IS effective when order status is already terminal.

The 5-second timeout (`09:25:10,763`) fires because neither cancel confirmed a DELETE response (both short-circuited), and the supersede queue waits for cancel confirmation.

---

## Codepath Map

### Cancel issuance (EP-01.3)

```
ExecPosFSM.on_regime_changed()  → _cancel_pending_entries_for_symbol(reason=CANCEL_STALE_REGIME)
ExecPosFSM.on_trade_intent()    → _cancel_pending_entries_for_symbol(reason=CANCEL_SUPERSEDED)
                                    (when new intent supersedes existing pending entry)
```

### `_cancel_pending_entries_for_symbol()` (fsm.py)

```python
for order_id, deadline in orders_to_cancel:           # iterates watchdog.pending_orders + acked_orders
    async def _do_cancel(oid, sym, dl):
        try:
            await self._cancel_order(sym, oid)        # ← always a coroutine, never raises
            LOG.info(f"✅ EP-01.3: Cancelled {oid}")  # ← fires regardless of res.success ⚠️
            self.watchdog.on_order_cancel(oid)
        except Exception as e:
            if self._is_unknown_order_error(e):       # ← dead branch: _cancel_order absorbs exceptions
                LOG.info(f"✅ ... already absent")
            else:
                LOG.warning(f"... Failed to cancel {oid}: {e}")

    self._submit_async(_do_cancel(order_id, symbol, deadline), loop)
                                                      # ← fires-and-forgets; two concurrent tasks
                                                      # for the same order_id is possible
```

### `_cancel_order()` (fsm.py:1013)

```python
async def _cancel_order(self, symbol, order_id):
    helper = self._idempotent_cancel_helper           # IdempotentCancelHelper
    max_retries = self._idempotent_cancel_max_retries # 2 (from config/aurora/domains.yaml)
    if helper and max_retries > 0 and ...:
        res = await helper.cancel_order_idempotent(
            symbol=symbol,
            order_id=str(order_id),
            cancel_func=self.adapter.cancel_order,    # raises BinanceAPIError on error
            get_order_func=self.adapter.get_order,
            max_retries=max_retries,
        )
        helper.log_cancel_result(res, str(order_id))  # emits IDEMPOTENT_CANCEL_AUDIT
        return res                                     # returns IdempotentCancelResult always
    return await self.adapter.cancel_order(symbol, order_id)
```

**Note:** `_cancel_order()` never raises when helper is active. It always returns `IdempotentCancelResult`. The `result.success` is NOT checked by the caller (`_do_cancel()`).

### `IdempotentCancelHelper.cancel_order_idempotent()` (idempotent_cancel.py)

```
Step 1: pre-check via get_order_before_cancel()
  → If status in {CANCELED,FILLED,EXPIRED,REJECTED,NOT_FOUND}: return success (short-circuit)
  → If status == NEW/PARTIALLY_FILLED: proceed

Step 2: for attempt in range(max_retries=2):
    try:
        result_dict = normalize(await cancel_func(symbol, order_id))
        # adapter.cancel_order() raises BinanceAPIError(-2011) → this never runs for -2011
        if result_dict.get("code") in (-2011, -2013):      ← ABSORPTION — dict path only
            return success (IDEMPOTENT_-2011_ABSORBED)
        if result_dict.get("status") == "CANCELED":
            return success (CANCEL_SUCCESS)
        ...
    except Exception as e:
        LOG.warning(f"Exception on attempt {attempt+1}: {e}")
        if attempt == max_retries - 1:
            return FAILED (EXCEPTION_AFTER_{N}_RETRIES)    ← -2011 exception → FAILED
        await _backoff_wait(attempt)   # 100ms, 200ms, …

```

### The absorption gap

```
BinanceAPIError(-2011) is raised → hits except Exception as e:
                                 → NOT absorbed as idempotent success
                                 → retried (100ms backoff)
                                 → hits exception again
                                 → returns IdempotentCancelResult(success=False)
```

```
BinanceAPIError(-2011) fields:
  e.code = -2011
  str(e) = "[-2011] Unknown order sent. (no-nrr)"
  No check for `e.code in (-2011, -2013)` in exception handler → gap
```

### Adapter `cancel_order()` (binance_adapter.py:604)

```python
async def cancel_order(self, symbol, order_id=None, client_order_id=None):
    ...
    try:
        result = await self._request("DELETE", "/fapi/v1/order", params, signed=True)
        return ExchangeOrderResponse(status=result.get("status"), ...)
    except BinanceAPIError:
        raise   # ← always re-raises; never returns dict with {"code": -2011}
```

`_request()` raises `_make_binance_error(r, err)` for HTTP 4xx, which creates `BinanceAPIError(code=err["code"], msg=err["msg"])`.
The response body `{"code": -2011, "msg": "Unknown order sent."}` is mapped to `BinanceAPIError(code=-2011)` and raised — never returned as a dict.

**Conclusion:** the absorption path `result.get("code") == -2011` is **unreachable** via `BinanceAdapter.cancel_order()`. The dict-path absorption only applies if `cancel_func` is a mock or alternative implementation that returns `{"code": -2011}` rather than raising.

---

## Root-Cause Classification (Ranked)

### #1 — Order already canceled (concurrent duplicate cancel) [CONFIRMED PRIMARY]

**Probability: 100% of observed -2011 occurrences**

One order triggers two independent cancel reasons simultaneously:
- `CANCEL_STALE_REGIME` (regime change event)
- `CANCEL_SUPERSEDED` (new intent arrival)

Both call `_cancel_pending_entries_for_symbol()` synchronously, which schedules async fire-and-forget tasks without deduplication. Both tasks call `cancel_order_idempotent()` for the same `order_id`. The pre-check runs concurrently; the one that completes first succeeds, the second gets `-2011`.

```
Timeline (ms from 09:05:04,000):
  T+168: CANCEL_STALE_REGIME issued → async task scheduled
  T+449: CANCEL_SUPERSEDED issued → async task scheduled (concurrent!)
  T+750: pre-check for SUPERSEDED → GET /fapi/v1/order → returns NEW (still active)
  T+841: STALE_REGIME cancel completes → order CANCELED ← winner
  T+1082: SUPERSEDED cancel arrives → DELETE → -2011 ← loser
  T+1547: retry attempt 2 → -2011 again
  T+1549: IDEMPOTENT_CANCEL_AUDIT FAILED
  T+1557: "✅ Cancelled" logged despite FAILED ← false positive
```

### #2 — Order already filled (cancel after fill, async race) [HANDLED CORRECTLY]

Observed in `log.1` (3 cases) and `log` (2 cases). When LIMIT entry fills before cancel is issued, `PRE_CHECK_TERMINAL_FILLED` correctly short-circuits. No `-2011` produced in these cases because the pre-check sees `FILLED` and returns `success=True` before any DELETE is attempted.

**This path is safe.**

### #3 — Order never existed / replaced (stale id) [NOT OBSERVED]

Would occur if `orderId` in watchdog refers to an order that was replaced by a Modify/Amend API call. Not observed. No Modify/Amend calls in the codebase for entry orders.

### #4 — Race / delayed WebSocket (status not updated) [SECONDARY CONTRIBUTOR]

Relevant for the pre-check: the FSM's local order state is populated via polling watchdog and REST. If WebSocket fill notification is delayed and the pre-check polled before fill propagated, `before=NEW` would appear even though the order was actually FILLED. This did not occur in the observed cases (which are CANCELED, not FILLED), but remains a theoretical risk for fills happening during the cancel window.

---

## State Transitions After -2011

```
BinanceAPIError(-2011) raised
  │
  ▼ cancel_order_idempotent() exception handler
  │  attempt < max_retries (1) → _backoff_wait(100ms) → retry
  │  attempt = max_retries (1) → return IdempotentCancelResult(success=False)
  │
  ▼ _cancel_order() returns res
  │
  ▼ helper.log_cancel_result(res, order_id)
  │   → LOG.warning("IDEMPOTENT_CANCEL_AUDIT: status=FAILED reason=EXCEPTION_AFTER_2_RETRIES")
  │
  ▼ _do_cancel() caller block (after await self._cancel_order())
  │   NO if-success check ← bug
  │   LOG.info("✅ EP-01.3: Cancelled pending entry {oid} ({reason})")  ← false positive ⚠️
  │   self.watchdog.on_order_cancel(oid)  ← order removed from tracking (correct outcome)
  │   order_logger.write(ORDER_CANCELLED)  ← logged as cancelled (misleading)
  │
  ▼ EP-01.3 supersede queue proceeds after cancel "confirmed"
      (cancel is considered done regardless of FAILED audit)
```

**Critical observation:** Despite the `FAILED` audit, the **behavioral outcome is correct**: `watchdog.on_order_cancel(oid)` is called, the order is removed from tracking, and the system continues. The "failure" is diagnostic only — not a safety concern for this specific type of -2011 (duplicate cancel of already-canceled order).

---

## Correct Fail-Closed Policy Options

### Option A — Treat -2011 as idempotent success ALWAYS (recommended for CANCEL context)

**Rationale:** In distributed execution, cancel is naturally idempotent. `-2011 Unknown order` by definition means the order does not exist on Binance — which is the desired postcondition of a cancel. Whether it was canceled by us, by a fill, or by another path is irrelevant.

**Implementation:** In `cancel_order_idempotent()` exception handler, add -2011 absorption:

```python
except Exception as e:
    code = getattr(e, "code", None)
    if code in (-2011, -2013) or "Unknown order" in str(e) or "Order does not exist" in str(e):
        self.logger.info(
            f"IDEMPOTENT_CANCEL: -2011 from exception for {order_id}, "
            f"treating as idempotent success"
        )
        return IdempotentCancelResult(
            success=True,
            reason="IDEMPOTENT_-2011_ABSORBED_EXC",
            order_status_before=pre_check_order.get("status") if pre_check_order else None,
            order_status_after="UNKNOWN",
            error_code=code or -2011,
            is_idempotent_success=True,
        )
    # transient errors
    self.logger.warning(f"IDEMPOTENT_CANCEL: Exception on attempt {attempt + 1}: {e}")
    ...
```

**Fail-closed implication:** Absorbed immediately on first exception. No retry. A genuinely unknown order (misrouted, wrong symbol) would also be absorbed — but the pre-check via `get_order_before_cancel()` would have already failed with -2011 in that case too, so absorption is still correct.

**Risk:** Low. More false-negatives (fewer FAILED audits) but outcomes are always safe.

---

### Option B — Treat -2011 as success only if local state says terminal (FILLED/CANCELED)

**Rationale:** More conservative. Only absorb -2011 if we have local evidence the order is gone.

**Implementation:** After exception on cancel, do a post-cancel GET to confirm status before absorbing.

```python
except Exception as e:
    if getattr(e, "code", None) in (-2011, -2013) or "Unknown order" in str(e):
        # Confirm via GET
        confirm = await self.get_order_before_cancel(symbol, order_id, get_order_func)
        if confirm and str(confirm.get("status", "")).upper() in {
            "CANCELED", "FILLED", "EXPIRED", "REJECTED", "NOT_FOUND"
        }:
            return IdempotentCancelResult(success=True, reason="IDEMPOTENT_-2011_POST_CHECK", ...)
        # Status unknown or still NEW (should not happen) → fail
    ...
```

**Fail-closed implication:** Extra round-trip GET for every -2011. Slower but more auditable.

**Risk:** GET may also return -2011 for very stale orders, creating a confusing double exception. Not recommended.

---

### Option C — Trigger immediate reconcile (openOrders / positionRisk) and decide

**Rationale:** Maximally safe. On -2011, call `GET /fapi/v1/openOrders` to refresh full order state before proceeding.

**Fail-closed implication:** Correct but expensive. One extra GET per -2011 occurrence. Introduces additional latency in the cancel → supersede queue path.

**Risk:** A symbol-based openOrders call is fast (~50ms). Adds complexity. Over-engineered for a benign race condition.

**Recommendation:** Reserve for cases where -2011 is observed on NON-duplicate (unexpected) paths. Not needed for the current scenarios.

---

## Additional Bug: `_do_cancel()` logs "✅" unconditionally

**Location:** `fsm.py:_cancel_pending_entries_for_symbol()`, inner `_do_cancel()` async closure.

```python
try:
    await self._cancel_order(sym, oid)       # returns IdempotentCancelResult regardless
    LOG.info(f"✅ EP-01.3: Cancelled {oid} ({reason})")   # ← always fires
    self.watchdog.on_order_cancel(oid)       # ← always fires (correct for idempotent case)
```

**Fix needed:**

```python
res = await self._cancel_order(sym, oid)
if not isinstance(res, IdempotentCancelResult) or res.success:
    LOG.info(f"✅ EP-01.3: Cancelled {oid} ({reason})")
else:
    LOG.warning(f"⚠️ EP-01.3: Cancel FAILED for {oid} ({reason}): {res.reason}")
self.watchdog.on_order_cancel(oid)   # still correct: order gone regardless
```

**Note on watchdog removal:** Even when cancel "fails" with -2011 (meaning order is already gone), removing it from the watchdog is correct behavior. The watchdog should not track orders that no longer exist.

---

## Dedup Guard: Missing Pre-dispatch Check

The current implementation does not check whether a cancel task is already in-flight for a given `order_id` before scheduling another. When two triggers fire within the same event loop tick, both tasks are submitted via `_submit_async()`.

**Proposed guard (no-code, for implementation checklist):**

```python
# Before scheduling, check if a cancel is already in-flight
if order_id not in self._pending_cancel_tasks:  # set[str]
    self._pending_cancel_tasks.add(order_id)
    self._submit_async(_do_cancel_with_cleanup(order_id, ...), loop)
else:
    LOG.debug(f"EP-01.3: Cancel for {oid} already in-flight, skipping duplicate")
```

This eliminates the concurrent-duplicate-cancel race at the scheduling level, making the -2011 exception absorption the last line of defense rather than the first.

---

## Proposed Tests (Names + Assertions)

### Class A — Exception-path -2011 absorption (currently missing)

**`test_cancel_2011_exception_absorbed_as_success`**
```
cancel_func raises BinanceAPIError(code=-2011, msg="Unknown order sent.")
pre-check returns {"status": "NEW"}
assert result.success is True
assert result.reason == "IDEMPOTENT_-2011_ABSORBED_EXC"
assert result.is_idempotent_success is True
assert cancel_func.call_count == 1   # no retry
```

**`test_cancel_2013_exception_absorbed_as_success`**
```
cancel_func raises BinanceAPIError(code=-2013, msg="Order does not exist.")
assert result.success is True
assert result.error_code == -2013
```

**`test_cancel_2011_exception_not_retried`**
```
cancel_func raises BinanceAPIError(code=-2011) twice
assert cancel_func.call_count == 1   # absorbed on first attempt, no retry
```

### Class B — Concurrent duplicate cancel dedup

**`test_concurrent_cancel_same_order_both_idempotent`**
```
Two concurrent calls to cancel_order_idempotent for same order_id:
  call_1: cancel_func → {"status": "CANCELED"}
  call_2: cancel_func → raises BinanceAPIError(-2011)
Both asserts: result.success is True
```

### Class C — `_do_cancel()` result check

**`test_do_cancel_logs_warning_on_failed_result`**
```
_cancel_order mock returns IdempotentCancelResult(success=False, reason="EXCEPTION_AFTER_2_RETRIES")
assert LOG.warning called with "⚠️ EP-01.3: Cancel FAILED"
assert LOG.info("✅") NOT called
```

**`test_do_cancel_logs_success_on_success_result`**
```
_cancel_order mock returns IdempotentCancelResult(success=True, reason="CANCEL_SUCCESS")
assert LOG.info("✅ EP-01.3: Cancelled") called
```

### Class D — Pre-check timing / race

**`test_pre_check_sees_canceled_before_attempt`**
```
pre-check returns {"status": "CANCELED"}
cancel_func NOT called
result.reason == "PRE_CHECK_TERMINAL_CANCELED"
result.success is True
```

**`test_pre_check_new_but_already_gone_by_cancel_time`**
```
pre-check returns {"status": "NEW"}
cancel_func raises BinanceAPIError(-2011)
assert result.success is True (exception-path absorption)
assert cancel_func.call_count == 1
```

---

## Next Implementation Checklist (No Code)

| # | Item | File | Priority |
|---|---|---|---|
| 1 | Add BinanceAPIError(-2011/-2013) absorption in `cancel_order_idempotent()` exception handler | `idempotent_cancel.py` | P0 |
| 2 | Fix `_do_cancel()` to check `res.success` before logging "✅"; log WARNING on failure | `fsm.py` | P0 |
| 3 | Add `_pending_cancel_tasks: set[str]` dedup guard in `_cancel_pending_entries_for_symbol()` | `fsm.py` | P1 |
| 4 | Write Class A tests: exception-path -2011/-2013 absorption | `test_idempotent_cancel_logic.py` | P0 |
| 5 | Write Class B tests: concurrent cancel dedup | `test_idempotent_cancel_logic.py` | P1 |
| 6 | Write Class C tests: `_do_cancel()` result check | `test_fsm_cancel.py` (new) | P0 |
| 7 | Write Class D tests: pre-check race scenario | `test_idempotent_cancel_logic.py` | P1 |
| 8 | Update IDEMPOTENT_CANCEL_AUDIT schema to distinguish `ABSORBED_EXC` vs `ABSORBED_DICT` | `idempotent_cancel.py` | P2 |
| 9 | Confirm `max_retries=2` → reduce to `max_retries=1` for -2011 cancels (no retry = faster) | `config/aurora/domains.yaml` | P2 |

---

## SSOT / Registry Constraints

The `cancel_order` adapter path and `IdempotentCancelHelper` do NOT relate to any verb in `verb_registry_v1.yaml` (they are internal domain infrastructure, not bus verbs). No registry changes required for the fix.

Config SSOT: `config/aurora/domains.yaml:389 → execution_position.idempotent_cancel.max_retries: 2`.

---

## Related Errors and Cross-References

| Error | Description | Doc |
|---|---|---|
| `-2011` | This document: Unknown order (duplicate cancel race + exception absorption gap) | — |
| `-1102` | Missing stopPrice for conditional order | `EP_MISSING_STOPPRICE_1102_CONTEXT.md` |
| `-1111` | Price precision violation (bracket orders) | `EP_PRECISION_1111_CONTEXT.md` |
| `-4015` | clientOrderId too long (> 35 chars) | `EP_CLIENTORDERID_4015_CONTEXT.md` |
| `-4116` | Duplicate orderId on Binance side (different from -2011) | — |
| `-5022` | GTX MAKER_ONLY rejected (observed same session, different order) | — |
