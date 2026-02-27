# EP Brackets Missing After Fill Plan

## Executive Summary
Issue: entry orders that were actually `FILLED` could pass through cancel handling (`PRE_CHECK_TERMINAL_FILLED`) without bracket recovery, so deferred TP/SL never got placed.

Secondary issue: bracket placement could be triggered by two independent paths (`deferred` and `DEC:PLACE_ORDER`), causing duplicate attempts and exchange conflicts (`-4130`).

Scope of fix is state-flow only:
- recover deferred brackets in cancel-path discovered fill
- preserve timeout-path as SSOT behavior
- deduplicate cross-path placement attempts before adapter call
- add fail-closed guardrail for partial/missing brackets
- reconcile pending deferred brackets on startup/WAL rehydrate

## SSOT Behavior Definition
1. If parent entry is `FILLED` and deferred bracket payload exists, system must attempt exactly one SL + one TP placement per parent entry.
2. Cancel-path discovered fill recovery is behaviorally equivalent to timeout-path fill recovery.
3. Dedup happens before adapter placement for `(symbol, parent_order_id, kind)` across all paths.
4. If fewer than 2 brackets are placed, system emits `FILLED_ENTRY_WITHOUT_BRACKETS` and marks entry unsafe; protected state is not silently claimed.
5. Startup reconcile checks pending deferred entries and recovers brackets for terminal `FILLED` parents.

## Test Matrix
| Scenario | Arrange | Trigger | Expected |
|---|---|---|---|
| A cancel-path recovery | pending deferred exists + cancel returns `PRE_CHECK_TERMINAL_FILLED` | `_cancel_pending_entries_for_symbol` | SL/TP placement attempted, guardian bracket registration, pending consumed via recovery (not plain cancel cleanup) |
| B timeout oracle | same pending deferred data | `_handle_order_timeout` | baseline timeout recovery remains intact, SL/TP placed, guardian registered |
| C double-trigger race | deferred path and manage `PLACE_ORDER` path both available | execute both paths | only one SL and one TP adapter call; duplicate path skipped pre-adapter |
| D partial brackets | one bracket fails (`-2021`) and other succeeds | deferred placement | `FILLED_ENTRY_WITHOUT_BRACKETS` emitted, unsafe registry updated |
| E WAL/startup replay | pending deferred restored after restart | `_startup_order_guardian_reconcile` | startup checks parent status, FILLED parents recover and consume pending |

## Proposed Minimal Code Changes
- `apps/reference/domains/execution_position/fsm.py`
  - `__init__`: add dedup and unsafe registries for bracket guardrails.
  - `_cancel_pending_entries_for_symbol`: on discovered fill in cancel-path, call shared deferred bracket recovery (parity with timeout path).
  - `_handle_order_timeout`: use shared recovery helper as SSOT.
  - `_place_deferred_brackets`: add dedup coordinator + fail-closed missing-bracket guardrail event.
  - `_execute_decision` (`PLACE_ORDER`): dedup by `(symbol,parent,kind)`, register bracket with guardian when parent is known.
  - `_startup_order_guardian_reconcile`: recover pending deferred brackets for parents confirmed as `FILLED`.
- `apps/reference/domains/execution_position/fsm_manage.py`
  - `_emit_place_order`: add optional `parent_order_id` in payload for downstream idempotent dedup linking.
- `tests/domains/execution_position/test_brackets_after_fill_recovery.py`
  - add non-regression imitation/integration tests A-E (tests-first contract).

## Risk Analysis
1. Double placement race: mitigated by pre-adapter dedup claim (`inflight/completed`).
2. Partial protection (`-2021`, etc.): fail-closed guardrail event + unsafe registry; no silent protected assumption.
3. Partial-fill/cancel parity: cancel-path now aligned with timeout discovered-fill recovery behavior.
4. WAL replay drops: startup reconcile now explicitly checks pending deferred entries and recovers only on confirmed `FILLED`.
5. Regression in manage bracket path: covered by timeout oracle and race tests.

## Rollback Plan
1. Revert only these files if needed:
   - `apps/reference/domains/execution_position/fsm.py`
   - `apps/reference/domains/execution_position/fsm_manage.py`
2. Keep tests in `tests/domains/execution_position/test_brackets_after_fill_recovery.py` as non-regression contract.
3. No schema migration required; rollback is code-only.
4. Timeout-path behavior remains the operational baseline oracle (`test_timeout_path_recovery_stays_intact`).
