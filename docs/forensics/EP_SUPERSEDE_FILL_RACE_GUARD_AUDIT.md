# Forensic Audit: EP-01.3 Fill-Race Guard Coverage

**Date:** 2026-02-24
**Package:** EP-01.3-FILL-RACE-GUARD-AUDIT (context only)
**Scope:** `apps/reference/domains/execution_position/fsm.py`, `apps/reference/domains/execution_position/exposure_guard.py`, `apps/reference/adapters/binance_adapter.py`

---

## 1) Supersede queued-open call chain

### Intended chain (from design/context)
1. `DEC:OPEN` detects existing pending entry and queues supersede (`fsm.py:2757-2773`).
2. Timeout coroutine fires after `supersede_cancel_timeout_sec` and calls `_process_queued_supersede(symbol)` (`fsm.py:2783-2794`).
3. `_process_queued_supersede()` re-submits queued decision via `_async_execute_decision(decision)` (`fsm.py:1187-1224`).
4. Decision returns to DEC:OPEN execution path (`fsm.py:2728+`) and proceeds to entry placement (`fsm.py:3262-3332`).

### Factual code state in this branchФ
- `ExecPosFSM` has no `_async_execute_decision` implementation.
- Callsite exists: `fsm.py:1224`.
- `_execute_decision` exists: `fsm.py:2327`.
- `rg`/runtime introspection confirms `_async_execute_decision` is absent.

Implication: queued supersede dispatch currently references a missing method; this is not a guard and should be treated as a separate defect.

---

## 2) Guards that could block open when position already exists

### A) ExposureGuard check (`_check_exposure_fail_closed`)
- Location: `fsm.py:2199-2212`, `fsm.py:4240-4408`.
- Trigger path: only inside `handle()` when processing `msg.verb == "OPEN"` (`fsm.py:2179-2212`), i.e. CMD path before DEC is produced.
- Not applied in queued supersede re-execution path inside `_process_queued_supersede` / `_execute_decision`.

### B) Watchdog pending/acked guard (supersede logic)
- Location: `fsm.py:2744-2755`, plus clear-check in cancel-event path `fsm.py:4492-4510`.
- Behavior: blocks/requeues only while watchdog has pending/acked entry orders for symbol.
- Gap: FILLED old entry removes pending condition; this guard does not check "already-open position", only "pending entry order exists".

### C) SYMBOL_TIDY entry gate
- Location: `fsm.py:3918-3954`, called at `fsm.py:3067-3071`.
- Behavior: timing/cleanup freshness gate.
- Gap: not a position/exposure guard; does not query or validate open position state.

### D) Live `positionRisk` preflight (`_preflight_position_check`)
- Location: helper `fsm.py:4616-4700`, uses `adapter.get_open_positions(symbol)` (`fsm.py:4652`).
- Callsites: bracket placement only (`fsm.py:3512-3517`, `fsm.py:4727-4732`, `fsm.py:5186-5189`).
- Gap: not used before DEC:OPEN entry placement path (`fsm.py:3073-3332`).

### E) OrderGuardian / OrderIndex / watchdog lifecycle hooks
- Entry registration is post-placement (`fsm.py:3360-3369`), not pre-open position block.
- Cancel event handler updates exposure summary and terminalization (`fsm.py:4410-4460`), but does not perform live position guard before queued open.

---

## 3) Guard data source + fail-closed behavior

### ExposureGuard
- Data source: local cached portfolio snapshot (`self._latest_portfolio_state` from EVT updates, `fsm.py:1550-1560`).
- In guard: `exposure_guard.can_open(..., portfolio_state, ...)` (`fsm.py:4295-4297`).
- Fail-closed behavior:
  - blocks on missing/non-positive equity (`exposure_guard.py:485-486`),
  - blocks on stale/missing portfolio timestamp (`exposure_guard.py:489-492`),
  - blocks on internal errors (`fsm.py:4382-4408`).
- Limitation: this check is not re-run in queued DEC supersede execution.

### Watchdog/guardian gates
- Data source: local in-memory watchdog/order guardian state (`fsm.py:2747-2755`, `fsm.py:4496-4505`, `fsm.py:3918-3954`).
- Fail mode: primarily state-based flow control; not fail-closed on exchange-state uncertainty.
- Limitation: no live position existence verification.

### Live exchange position query utility
- Source endpoint: `/fapi/v2/positionRisk` in adapter (`binance_adapter.py:674-702`).
- Used by `_preflight_position_check` with retry/backoff (`fsm.py:4652-4700`).
- Fail behavior there: returns `False` after retries for bracket flow (effectively fail-closed for TP/SL placement), but this is not connected to entry-open supersede path.

---

## 4) Verdict

## VERDICT: **UNGUARDED (unsafe for fill-race scenario)**

### Evidence summary
- Queued supersede path does not execute a live/open-position guard before entry placement (`fsm.py:1187-1224`, `fsm.py:2728-3332`).
- ExposureGuard is CMD-path only (`fsm.py:2179-2212`) and uses cached portfolio state (`fsm.py:1550-1560`), not a guaranteed pre-placement re-check in queued DEC execution.
- Existing supersede watchdog checks cover pending orders, not already-open positions (`fsm.py:2744-2755`).

Additional finding:
- `_process_queued_supersede()` currently calls missing `_async_execute_decision` (`fsm.py:1224`), indicating a dispatch defect separate from guard coverage.

---

## 5) Minimal guard insertion point + tests (names only)

### Minimal insertion point (recommended)
- Insert fill-race guard in `ExecPosFSM._execute_decision()` DEC:OPEN path, immediately after supersede queue/pending logic and before entry placement path begins (`fsm.py:2799` before market/limit placement).
- Guard contract:
  - query live position (`adapter.get_open_positions(symbol)`),
  - if non-zero position exists: abort queued supersede open,
  - if live query unavailable/errors: fail-closed for supersede path (abort, do not place entry).

### Regression tests to add (names only)
- `test_supersede_timeout_blocks_open_when_live_position_exists`
- `test_supersede_timeout_blocks_open_when_position_query_unavailable_fail_closed`
- `test_supersede_timeout_allows_open_when_no_live_position`
- `test_supersede_queued_dispatch_uses_existing_execute_method` (prevents missing `_async_execute_decision` regression)

---

## 6) Evidence index

- `apps/reference/domains/execution_position/fsm.py:1187-1224`
- `apps/reference/domains/execution_position/fsm.py:1550-1560`
- `apps/reference/domains/execution_position/fsm.py:2179-2212`
- `apps/reference/domains/execution_position/fsm.py:2327`
- `apps/reference/domains/execution_position/fsm.py:2728-2794`
- `apps/reference/domains/execution_position/fsm.py:3067-3071`
- `apps/reference/domains/execution_position/fsm.py:3073-3332`
- `apps/reference/domains/execution_position/fsm.py:3512-3517`
- `apps/reference/domains/execution_position/fsm.py:3918-3954`
- `apps/reference/domains/execution_position/fsm.py:4240-4408`
- `apps/reference/domains/execution_position/fsm.py:4492-4510`
- `apps/reference/domains/execution_position/fsm.py:4616-4700`
- `apps/reference/domains/execution_position/exposure_guard.py:447-492`
- `apps/reference/adapters/binance_adapter.py:674-702`
