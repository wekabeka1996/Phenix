# REVIEW: EP Brackets After Fill Fix

## Scope
- Reviewed delivered fix in:
  - `apps/reference/domains/execution_position/fsm.py`
  - `apps/reference/domains/execution_position/fsm_manage.py`
  - `tests/domains/execution_position/test_brackets_after_fill_recovery.py`
  - `docs/forensics/EP_BRACKETS_MISSING_AFTER_FILL_PLAN.md`
- Evidence sources:
  - Code paths and tests listed above.
  - Incident logs: `logs/domain_execution_position.log.1` and `logs/order_guardian.log`.
  - Commit workspace HEAD: `b78c31e`.

## Executive Verdict
- Overall: **FAIL** (safety-critical gaps remain).
- What is fixed correctly:
  - Cancel-path `PRE_CHECK_TERMINAL_FILLED` now calls the same deferred recovery helper used by timeout path.
  - Basic dedup works for single SL + single TP race.
- Why FAIL:
  - Fail-closed contract is still violated in several paths (notably pending-state clearing before successful placement and missing hard policy for naked positions).

## A1) Correctness vs Root Cause
- Answer:
  - **Yes (partially):** cancel-path now calls shared recovery used by timeout-path.
  - **No (fully safe):** deferred data is consumed early (before placement success), so failure windows can still leave unprotected positions.
- Evidence:
  - Cancel path recovery call: `fsm.py::_cancel_pending_entries_for_symbol` lines 1302-1308.
  - Timeout path recovery call: `fsm.py::_handle_order_timeout` lines 4367-4373.
  - Shared consume/pop before placement: `fsm.py::_recover_deferred_brackets_for_filled_entry` lines 1108-1131.
  - Early return without guardrail on preflight fail: `fsm.py::_place_deferred_brackets` lines 4999-5004.
  - Historical incident trace (pre-fix behavior): `logs/domain_execution_position.log.1` lines 19104-19106 (FILLED discovered in cancel path, no bracket recovery logged).

## A2) Dedup Safety & Completeness
- Answer:
  - Dedup key is insufficient for multi-TP.
  - Claim/release is not protected by `finally`; cancellation can leave stuck inflight claims.
  - No TTL/reset policy for inflight/completed maps.
- Evidence:
  - Dedup key includes only `symbol|parent|kind`: `fsm.py::_bracket_place_key` lines 1032-1033.
  - TP1+TP2 emission exists: `fsm_manage.py::_place_brackets` lines 770-793.
  - `parent_order_id` is same source field for both TP orders: `fsm_manage.py::_emit_place_order` lines 1030-1048.
  - Dedup classifier reduces both TP orders to `"TP"`: `fsm.py::_execute_decision` lines 2919-2922.
  - Claim/release not in `finally`:
    - `fsm.py::_execute_decision` lines 2930-2937, 3060-3074.
    - `fsm.py::_place_deferred_brackets` lines 5043-5068, 5072-5131.
- Finding F-01
  - Severity: **P1**
  - Symptom: TP2 may be skipped when TP1 already claimed/completed.
  - Root cause: dedup key lacks TP slot dimension.
  - Evidence: `fsm_manage.py` 770-793 + `fsm.py` 1032-1033, 2919-2922.
  - Risk: behavior regression for partial-exit strategies.
  - Minimal fix outline: add optional `bracket_slot` (e.g., `TP1`/`TP2`) into `DEC:PLACE_ORDER`; key = `symbol|parent|kind|slot`.
  - Minimal tests:
    - `test_multi_tp_dedup_allows_tp1_tp2_independently`.
- Finding F-02
  - Severity: **P1**
  - Symptom: dedup inflight claim can stick after coroutine cancellation.
  - Root cause: claim/release is exception-branch based; no `finally`.
  - Evidence: `fsm.py` 2930-2937, 3060-3074, 5043-5068, 5072-5131.
  - Risk: future bracket attempts may be permanently blocked for that key until restart.
  - Minimal fix outline: wrap claim lifecycle in `try/finally`; release on any non-success including `CancelledError`.
  - Minimal tests:
    - `test_inflight_released_on_exception_allows_retry`.
    - `test_inflight_released_on_cancelled_error`.

## A3) Guardrail Behavior
- Answer:
  - `FILLED_ENTRY_WITHOUT_BRACKETS` is emitted only in deferred placement path.
  - `missing_count` logic is accurate where executed, but coverage is incomplete.
  - Unsafe registry is in-memory only (not durable across restart).
  - `missing_count=2` has no enforcement policy beyond observability.
- Evidence:
  - Guardrail emit: `fsm.py::_emit_filled_entry_without_brackets` lines 1064-1090.
  - Guardrail call only in deferred path: `fsm.py::_place_deferred_brackets` lines 5171-5178.
  - No corresponding emit in `PLACE_ORDER` path: `fsm.py::_execute_decision` lines 2908-3075.
  - Registry only in-memory and no reader/consumer paths:
    - init: `fsm.py` lines 267-270.
    - writes: `fsm.py` line 1083.
    - `rg` shows no operational consumer outside tests.
- Finding F-03
  - Severity: **P1**
  - Symptom: manage-path bracket failures can bypass `FILLED_ENTRY_WITHOUT_BRACKETS`.
  - Root cause: guardrail is wired only in deferred path.
  - Evidence: `fsm.py` 5171-5178 vs 2908-3075.
  - Risk: partial protection may not be surfaced for non-deferred path.
  - Minimal fix outline: shared post-placement assessment helper used by both deferred and `PLACE_ORDER` paths.
  - Minimal tests:
    - `test_place_order_partial_failure_emits_guardrail`.
- Finding F-04
  - Severity: **P1**
  - Symptom: naked position (`missing_count=2`) has no mandatory containment action.
  - Root cause: event + in-memory marker only; no action policy.
  - Evidence: `fsm.py` 1064-1090; no downstream policy consumer.
  - Risk: system can continue trading with unprotected open position.
  - Minimal fix outline: policy gate on `missing_count=2` (halt symbol opens, emergency close option, bounded retries).
  - Minimal tests:
    - `test_missing_count_two_triggers_symbol_halt_or_emergency_policy`.

## A4) Startup Reconcile
- Answer:
  - FILLED-only gate is correct.
  - Non-filled parents are skipped (good).
  - Idempotence is incomplete when stale WAL exists and brackets already exist (dedup resets on restart, guardian check is permissive).
- Evidence:
  - FILLED-only check: `fsm.py::_startup_order_guardian_reconcile` lines 5653-5657.
  - Recovery call: lines 5659-5665.
  - Recovery consumes pending before success: `fsm.py` lines 1108-1131.
  - Guardian permissive check (no existing-bracket open-order check): `services/order_guardian.py::should_place_brackets` lines 620-635.
- Finding F-05
  - Severity: **P2**
  - Symptom: startup replay can re-attempt placement against already existing brackets.
  - Root cause: no explicit pre-check for already-open SL/TP before consuming pending.
  - Evidence: `fsm.py` 5636-5665 + `services/order_guardian.py` 620-635.
  - Risk: duplicate/conflict (`-4130`) noise and incorrect guardrail signals.
  - Minimal fix outline: startup pre-check for existing open SL+TP; clear as `startup_already_protected` without placement.
  - Minimal tests:
    - `test_startup_reconcile_idempotent_no_double_brackets`.

## A5) WS reorder / late events resilience
- Answer:
  - Pending-pop dedup prevents many duplicate recoveries.
  - One unsafe reorder remains: cancel-event path clears pending as `cancelled` without fill-aware recovery.
- Evidence:
  - Cancel-event path unconditional pending clear: `fsm.py::_handle_cancel_event` lines 4698-4708.
  - Cancel-event router includes `ORDER_STATE_CHANGED` and `ORDER_CANCELLED`: `fsm.py` lines 2545-2551.
  - Shared recovery helper is not called from cancel-event path.
- Finding F-06
  - Severity: **P1**
  - Symptom: late cancel events can drop deferred brackets without recovery in partial-fill scenarios.
  - Root cause: cancel-event handler assumes all cancellations mean no bracket recovery needed.
  - Evidence: `fsm.py` 4698-4708, 2545-2551.
  - Risk: uncovered bracket loss in event reorder edge-cases.
  - Minimal fix outline: in cancel-event path, verify terminal order status/executedQty (or position presence) before clearing; call shared recovery when fill-discovered.
  - Minimal tests:
    - `test_late_cancel_event_does_not_duplicate_brackets`.
    - `test_late_cancel_partial_fill_routes_to_recovery`.

## A6) Scope & Architecture
- Answer:
  - No obvious new cross-domain imports were introduced by this patch.
  - Patch is additive, but it increases coordinator complexity inside `fsm.py` and duplicates one recovery-consume path.
  - New registries are not WAL-backed, which weakens restart safety for fail-closed monitoring.
- Evidence:
  - Duplicate consume path:
    - `fsm.py::_recover_deferred_brackets_for_filled_entry` lines 1108-1131.
    - `fsm.py::_on_order_fill` lines 2235-2258.
  - In-memory-only registries: `fsm.py` lines 267-270, 1083.
- Finding F-07
  - Severity: **P2**
  - Symptom: recovery logic split across two pop-and-clear implementations.
  - Root cause: `_on_order_fill` was not unified onto shared helper.
  - Evidence: `fsm.py` 1108-1131 vs 2235-2258.
  - Risk: future drift and asymmetric bug fixes.
  - Minimal fix outline: route `_on_order_fill` through `_recover_deferred_brackets_for_filled_entry`.
  - Minimal tests:
    - `test_fill_path_uses_same_recovery_ssot_as_cancel_and_timeout`.
- Finding F-08
  - Severity: **P2**
  - Symptom: unsafe bracket state disappears after restart.
  - Root cause: `_filled_entries_missing_brackets` is in-memory only.
  - Evidence: `fsm.py` 267-270, 1083; no WAL contract for unsafe state.
  - Risk: monitoring blind spot after process restart.
  - Minimal fix outline: WAL events for unsafe-marked/unsafe-cleared and startup rehydrate.
  - Minimal tests:
    - `test_unsafe_registry_persists_across_restart`.

## Mandatory Additional Tests (Not Yet Implemented)
- `test_multi_tp_dedup_allows_tp1_tp2_independently`
- `test_inflight_released_on_exception_allows_retry`
- `test_startup_reconcile_idempotent_no_double_brackets`
- `test_late_cancel_event_does_not_duplicate_brackets`

## Incident Evidence Notes
- `logs/domain_execution_position.log.1` confirms historical duplicate/conflict pattern:
  - Deferred + manage race around one fill: lines 18141-18160 (`PLACE_ORDER success` + deferred `-4130` failures).
  - Cancel-path fill-discovered without deferred placement in older behavior: lines 19104-19106.

