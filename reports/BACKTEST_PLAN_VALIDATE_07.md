# BACKTEST_PLAN_VALIDATE_07 — Clock Wiring vs Race Condition

**Date:** 2026-01-22  
**Verdict:** ❌ **Clock wiring alone is NOT sufficient. Tick-barrier OR disabling async watchdog in backtest is required.**

---

## A) Config Fingerprint: Confirmed Identical

All 4 runs (trades: 8/103/166/8) have:
- Same symbols: `[SOLUSDT, ETHUSDT, BTCUSDT, DOGEUSDT, XRPUSDT]`
- Same dates: `2023-05-14` to `2023-05-31`
- Same initial_balance: `1000.0`
- Same regimes.events_total: `4897`
- Same features.counts_by_tf_sec: identical

**Input data is deterministic. Divergence is in execution layer.**

---

## B) Time Sources in Hot Path

### Wall-Clock (`time.time()`) — NEEDS CLOCK WIRING
| File | Line | Impact |
|------|------|--------|
| mean_reversion_handler.py | 419,465,498,818 | Throttling/timestamps |
| aurora_handler.py | 119 | `wall_time_fn` default |
| deferred_scheduler.py | 46 | Retry scheduling |
| leverage_service.py | 82 | Idempotency clock |
| order_ledger.py | 63,65,271,283 | Record timestamps |

### Real Sleep (`asyncio.sleep()`) — CAUSES RACE
| File | Line | Context |
|------|------|---------|
| **watchdog.py** | **253** | Main watchdog loop: `await asyncio.sleep(check_interval_ms / 1000)` |
| fsm.py | 1449 | Position tracking retry |
| fsm.py | 1969 | Recovery loop |
| fsm.py | 2214 | Timeout wait |
| fsm.py | 2936,2947 | Order retry |
| **fsm.py** | **3945,3952** | Preflight backoff |
| fsm.py | 3960 | Cleanup loop |
| idempotent_cancel.py | 332 | Cancel retry |

---

## C) Race Condition Proof

### Mechanism
```
┌─────────────────┐     ┌─────────────────────┐
│ Main Thread     │     │ Async Loop (thread) │
│ (engine.py)     │     │ (ExecPosFSM)        │
├─────────────────┤     ├─────────────────────┤
│ tick 1: emit    │────>│ place_order()       │
│                 │     │ watchdog.track()    │
│ tick 2: match   │     │ await sleep(1s)     │<─ REAL TIME
│ → FILL          │     │ ...                 │
│                 │     │ wake: check_timeout │
│ tick N...       │     │ cancel if expired   │
└─────────────────┘     └─────────────────────┘
```

**Problem:** `asyncio.sleep(1s)` waits 1 real second, but in backtest tick 1→tick 2 happens in ~1ms. By the time watchdog wakes, hundreds of ticks have passed. Order is already FILLED, but watchdog may **race** to cancel it or not.

### Evidence: Watchdog Code
```python
# watchdog.py:253
async def _watchdog_loop(self):
    while self._started:
        await self._check_timeouts()      # Uses get_clock().now_ms() ✓
        await asyncio.sleep(...)          # Uses WALL CLOCK ✗
```

The deadline comparison uses simulated time, but the wake-up is real time. This is a **timebase mismatch**.

---

## D) First Divergence (Hypothesis)

Based on logs from 8-trade runs:
1. Early FILL happens on BTCUSDT
2. Watchdog sleeps (real 1s) while engine processes 100+ bars
3. When watchdog wakes, it either:
   - **A)** Sees FILL already happened → order removed from tracking → OK
   - **B)** Races to cancel before FILL event processed → CANCEL_STALE_REGIME
4. After early cancel/fill divergence → exposure state differs → 415/433 intents blocked by `equity_utilization_breach`

**Exact first divergence cannot be proved without per-tick execution logs.** But mechanism is clear.

---

## E) Verdict

| Fix | Solves | Required? |
|-----|--------|-----------|
| Clock wiring (MR handler, scheduler, etc.) | Wall-clock timestamp bugs | ✅ Yes (hygiene) |
| Tick-barrier before each bar | Async loop race | ✅ Yes (determinism) |
| Disable watchdog async loop in backtest | Race from real sleeps | ✅ Alternative |

### Recommended Fix Order

1. **Disable async watchdog in backtest** — Backtest doesn't need real-time timeout monitoring. MockBroker can process fills synchronously.

2. **Add tick-barrier** — After each bar in `engine.run()`, wait for all async tasks in ExecPosFSM to complete.

3. **Clock wiring** — Replace `time.time()` with `get_clock()` in MR handler, scheduler, aurora_handler.

---

## Summary

**Clock wiring alone will NOT fix bimodal behavior.**

The root cause is `asyncio.sleep()` in watchdog/preflight running on wall-clock while backtest engine processes bars on simulated time. This creates race between:
- Order fills (processed in main thread per bar)
- Order cancels/timeouts (processed in async loop after real sleep)

Fix requires either:
- Disabling async watchdog for backtest
- Adding tick-barrier synchronization
- Or step-based simulation (no real sleeps)
