# P0 Reproduction Test Addendum

## Status Note (post-repair update, 2026-03-13)

The sections below remain the historical pre-fix evidence baseline that justified the repair package.

Those bug-demonstration scenarios were inverted in the implementation package and now live as fail-closed invariants in `tests/domains/execution_position/test_split_brain_repro.py` under these names:

- `test_invariant_local_open_blocked_while_manage_tracks`
- `test_invariant_stale_tracking_blocks_new_entry_fill_until_reconcile`
- `test_invariant_rest_flat_local_tracking_divergence_blocks_reopen`
- `test_invariant_orphan_cleanup_remains_tidy_only_and_not_business_close`
- `test_invariant_valid_tp_fill_matches_preack_client_id`

## Status Note (post-observability update, 2026-03-13)

The historical repro findings above are unchanged. P1 observability hardening added dedicated telemetry coverage in `tests/domains/execution_position/test_execution_observability_hardening.py` so that the already-proven split-brain failures are now easier to reconstruct in future incidents.

Observed pytest result for the observability suite:

```text
============================= test session starts =============================
platform win32 -- Python 3.11.0, pytest-8.4.2, pluggy-1.6.0
...
collected 7 items

tests\domains\execution_position\test_execution_observability_hardening.py . [ 14%]
......                                                                   [100%]

============================= 7 passed in 10.28s ==============================
```

New structured telemetry now covers:

- `EVT:EXECUTION_GUARD_BLOCKED`
- `EVT:EXECUTION_DIVERGENCE_DETECTED`
- `EVT:EXIT_MATCH_ATTEMPTED`
- `EVT:EXIT_MATCH_FAILED`
- `EVT:EXECUTION_TIDY_PERFORMED`
- `EVT:EXECUTION_CLOSE_RECONCILED`
- enriched `EVT:SYMBOL_TIDY` payloads with `business_close_reconciled=false`

## 1. Objective
Convert the 2026-03-13 split-brain research package into implementation-ready evidence by:

- verifying whether `tests/domains/execution_position/test_split_brain_repro.py` actually existed as runnable evidence,
- adding deterministic repo-local reproduction tests for the missing scenarios,
- capturing real `pytest` output against current runtime behavior,
- deciding which scenarios should become RED/GREEN invariants in the next repair package.

`tests/domains/execution_position/test_split_brain_repro.py` existed before this addendum, but only as a two-test stub with `pass` bodies. It was not evidence.

## 2. Test Inventory

| Test | Type | Current result | Primary invariant(s) |
| :--- | :--- | :--- | :--- |
| `test_repro_local_open_guard_missing_allows_cmd_open_while_manage_tracks` | behavior-demonstration | PASSED | INV-1, INV-6 |
| `test_repro_new_entry_fill_over_tracking_state_keeps_stale_brackets_and_places_none` | behavior-demonstration | PASSED | INV-3, INV-6 |
| `test_repro_rest_flat_vs_local_tracking_divergence_still_admits_reopen` | behavior-demonstration | PASSED | INV-2, INV-6 |
| `test_repro_orphan_cleanup_emits_symbol_tidy_but_does_not_reconcile_business_close` | behavior-demonstration | PASSED | INV-4 |
| `test_repro_valid_tp_fill_can_be_ignored_when_manage_tracks_client_id_before_ack` | behavior-demonstration | PASSED | INV-5 |

Pytest commands run:

```powershell
pytest tests/domains/execution_position/test_split_brain_repro.py -q
pytest tests/domains/execution_position/test_split_brain_repro.py -vv
```

Observed pytest result:

```text
============================= test session starts =============================
platform win32 -- Python 3.11.0, pytest-8.4.2, pluggy-1.6.0
...
collected 5 items

tests\domains\execution_position\test_split_brain_repro.py .....         [100%]

============================= 5 passed in 11.88s ==============================
```

```text
collecting ... collected 5 items

tests/domains/execution_position/test_split_brain_repro.py::test_repro_new_entry_fill_over_tracking_state_keeps_stale_brackets_and_places_none PASSED [ 20%]
tests/domains/execution_position/test_split_brain_repro.py::test_repro_local_open_guard_missing_allows_cmd_open_while_manage_tracks PASSED [ 40%]
tests/domains/execution_position/test_split_brain_repro.py::test_repro_rest_flat_vs_local_tracking_divergence_still_admits_reopen PASSED [ 60%]
tests/domains/execution_position/test_split_brain_repro.py::test_repro_orphan_cleanup_emits_symbol_tidy_but_does_not_reconcile_business_close PASSED [ 80%]
tests/domains/execution_position/test_split_brain_repro.py::test_repro_valid_tp_fill_can_be_ignored_when_manage_tracks_client_id_before_ack PASSED [100%]

============================== 5 passed in 7.85s ==============================
```

Interpretation:

- `passed as bug-demonstration`: 5
- `failed`: 0
- `xfailed`: 0

This package stays research-only. The tests intentionally prove the current buggy behavior rather than prematurely encoding the repaired behavior.

## 3. Test-by-Test Results

### 3.1 `test_repro_local_open_guard_missing_allows_cmd_open_while_manage_tracks`

- hypothesis: a new `CMD:OPEN` is admitted even when local `ManageFlowFSM.state != FLAT`, as long as no pending entry is tracked.
- setup: `ExecPosFSM` portfolio view is updated to `FLAT`; local `ManageFlowFSM` is forced to `TRACKING`; watchdog pending and acked entry sets are emptied.
- execution path: `ExecPosFSM.handle()` open branch in `apps/reference/domains/execution_position/fsm.py:1499-1534` routes into `OpenFlowFSM.handle()` in `apps/reference/domains/execution_position/fsm_open.py:239-496`.
- actual result: returned `DEC:OPEN` while local manage state stayed `TRACKING`.
- what it proves: no fail-closed local guard exists against `manage_state != FLAT`; pending-entry guard and local lifecycle guard are different things.
- what it does NOT prove: it does not prove any specific exchange-side event loss; only that local stale state does not block the reopen.

### 3.2 `test_repro_new_entry_fill_over_tracking_state_keeps_stale_brackets_and_places_none`

- hypothesis: once local manage state is stale `TRACKING`, a new entry fill does not re-enter the bracket-placement path.
- setup: `ManageFlowFSM` is primed with an old position, old bracket ids, and `TRACKING` state.
- execution path: `ExecPosFSM.handle()` routes `TRADE_EXECUTED` into `ManageFlowFSM.handle()`; in `apps/reference/domains/execution_position/fsm_manage.py:438-499`, `TRACKING` routes straight into `_check_rules()` instead of the FLAT-entry branch.
- actual result: no `DEC:BATCH` / `DEC:PLACE_ORDER` was emitted; stale bracket ids and old local position state survived unchanged.
- what it proves: a same-symbol new lifecycle can continue over stale local execution state; fresh bracket placement is suppressed before `_place_brackets()` is even reached.
- what it does NOT prove: it does not prove the older `_has_brackets()` mechanism from the research draft. Current code no longer has that suppressor; the actual suppressor is stale `TRACKING` state.

### 3.3 `test_repro_rest_flat_vs_local_tracking_divergence_still_admits_reopen`

- hypothesis: decision/orchestration flat truth comes from portfolio cache, not execution local FSM state.
- setup: `PositionQueries.check_symbol_is_flat()` reads an explicit `positionAmt=0` portfolio snapshot while local `ManageFlowFSM` remains `TRACKING`.
- execution path: `apps/reference/domains/decision_making/position_queries.py:126-173` returns `True`; `ExecPosFSM.handle()` still admits `CMD:OPEN` via `apps/reference/domains/execution_position/fsm.py:1499-1534`.
- actual result: REST/portfolio returned `FLAT=True` and the symbol still received `DEC:OPEN`.
- what it proves: divergence (`REST=FLAT`, `FSM=TRACKING`) is not fail-closed.
- what it does NOT prove: it does not prove which component emitted the real incident `CMD:OPEN`; it proves the architectural contract gap that would admit it.

### 3.4 `test_repro_orphan_cleanup_emits_symbol_tidy_but_does_not_reconcile_business_close`

- hypothesis: orphan cleanup is a maintenance/tidy path, not a valid close reconciliation path.
- setup: local `ManageFlowFSM` is left in `TRACKING`; a real `OrderGuardian` instance is given a fake adapter with no position and one reduce-only orphan bracket.
- execution path: `OrderGuardian.cleanup_orphans()` in `apps/reference/domains/execution_position/order_guardian.py:804-1078`.
- actual result: the orphan bracket was cancelled and `EVT:SYMBOL_TIDY` was emitted with `why="guardian:orphan_cleanup:tidy"`; local manage state stayed `TRACKING`.
- what it proves: cleanup/tidy is a symptom-path after divergence, not a business-valid close reconciliation.
- what it does NOT prove: it does not prove which earlier event broke the lifecycle; only that cleanup does not repair that break by itself.

### 3.5 `test_repro_valid_tp_fill_can_be_ignored_when_manage_tracks_client_id_before_ack`

- hypothesis: a valid TP fill can be ignored if `ManageFlowFSM` still holds the pre-ACK client id instead of the exchange order id.
- setup: `ManageFlowFSM` is in `BRACKETS_PLACED`; `tp1_order_id` and `tp_order_id` hold a realistic generated client id `TP1-<hash>`.
- execution path: `ManageFlowFSM._handle_bracket_fill()` in `apps/reference/domains/execution_position/fsm_manage.py:1106-1207`.
- actual result: `TRADE_EXECUTED` with `orderId=<exchange-id>` and `clientOrderId=TP1-<hash>` returned `None`; TP tracking stayed untouched.
- what it proves: valid exit/update processing can be silently ignored due to matcher assumptions, even without proving any WebSocket loss.
- what it does NOT prove: it does not prove this exact matcher gap happened on DOGEUSDT in the incident window; it proves that the live code path exists today.

## 4. Updated Hypothesis Matrix

| Hypothesis | Updated verdict | Evidence |
| :--- | :--- | :--- |
| `H1: WS / ORDER UPDATE LOSS` | `LIKELY` | Still no raw event proof. Polling fallback in `watchdog.py:319-436` and split-brain symptoms are compatible with a missed exit update, but this addendum did not obtain incident-grade proof. |
| `H2: FSM MISSED TRANSITION / EXIT MATCHER GAP` | `PROVEN` | `test_repro_valid_tp_fill_can_be_ignored_when_manage_tracks_client_id_before_ack` plus `fsm_manage.py:1115-1207` shows a valid TP fill can be ignored when the matcher still tracks a pre-ACK client id. |
| `H3: OPEN-OVERWRITE / LOCAL OPEN GUARD MISSING` | `PROVEN` | `test_repro_local_open_guard_missing_allows_cmd_open_while_manage_tracks` and `test_repro_rest_flat_vs_local_tracking_divergence_still_admits_reopen` prove that `CMD:OPEN` is admitted while local manage state is still `TRACKING`. |
| `H4: SPLIT-BRAIN CACHING / PHANTOM BRACKET CARRY-OVER` | `PROVEN (REFRAMED)` | `test_repro_new_entry_fill_over_tracking_state_keeps_stale_brackets_and_places_none` proves stale bracket state survives and suppresses fresh bracket placement. Original sub-claim that `_has_brackets()` is the suppressor is `DISPROVEN` by code review: `_place_brackets()` clears phantoms in `fsm_manage.py:554-568`; the real suppressor is stale `TRACKING` state before `_place_brackets()` is entered. |
| `H5: ORPHAN CLEANUP / TTL CLEANUP AS CLOSE SUBSTITUTE` | `PROVEN AS SYMPTOM, NOT ROOT CAUSE` | `test_repro_orphan_cleanup_emits_symbol_tidy_but_does_not_reconcile_business_close` proves cleanup emits tidy/cancel side effects without reconciling local business state. |
| `H6: SAME-SYMBOL NEW LIFECYCLE CONTINUES OVER STALE EXECUTION STATE` | `PROVEN` | Tests 1-3 together prove that one symbol can reopen while the old local lifecycle remains active and the new fill does not repair it. |

## 5. Implementation Readiness

### Invariant Table

| Invariant | Code owner | Current enforcement | Broken? | Test coverage |
| :--- | :--- | :--- | :--- | :--- |
| `INV-1: New CMD:OPEN must fail-closed if local execution manage-state is not FLAT.` | `ExecPosFSM.handle()` `apps/reference/domains/execution_position/fsm.py:1499-1534`; `OpenFlowFSM.handle()` `apps/reference/domains/execution_position/fsm_open.py:239-496` | No local manage-state check exists. | `YES` | `test_repro_local_open_guard_missing_allows_cmd_open_while_manage_tracks` |
| `INV-2: Divergence (REST=FLAT, FSM=TRACKING) must block, not admit, new open.` | `PositionQueries.check_symbol_is_flat()` `apps/reference/domains/decision_making/position_queries.py:126-173`; `IntentBuilder.build_and_emit()` `apps/reference/domains/decision_making/intent_builder.py:140-164`; `ExecPosFSM.handle()` `apps/reference/domains/execution_position/fsm.py:1499-1534` | Decision-side checks portfolio flatness and in-flight entry reservation only; no cross-check against local execution manage state. | `YES` | `test_repro_rest_flat_vs_local_tracking_divergence_still_admits_reopen` |
| `INV-3: Bracket ids from old lifecycle must not suppress new bracket placement.` | `ManageFlowFSM.handle()` `apps/reference/domains/execution_position/fsm_manage.py:438-499`; `_place_brackets()` `apps/reference/domains/execution_position/fsm_manage.py:536-572`; `_should_place_brackets()` `apps/reference/domains/execution_position/fsm_manage.py:779-783` | Phantom ids are only cleared if `_place_brackets()` is reached. Stale `TRACKING` state prevents reaching it. | `YES` | `test_repro_new_entry_fill_over_tracking_state_keeps_stale_brackets_and_places_none` |
| `INV-4: TTL cleanup must never substitute for proper execution close reconciliation.` | `ExecPosFSM._cleanup_loop()` `apps/reference/domains/execution_position/fsm.py:1841-1849`; `OrderGuardian.cleanup_orphans()` `apps/reference/domains/execution_position/order_guardian.py:804-1078`; `CloseExecutor.execute_close()` `apps/reference/domains/execution_position/close_executor.py:205-257`; `OrderGuardian.reconcile_symbol()` `apps/reference/domains/execution_position/order_guardian.py:1225-1259` | Cleanup/tidy runs independently from business close reconciliation. | `YES` | `test_repro_orphan_cleanup_emits_symbol_tidy_but_does_not_reconcile_business_close` |
| `INV-5: Exit/update processing must not silently ignore valid close events.` | `EPEventHandlers.on_order_fill()` `apps/reference/domains/execution_position/event_handlers.py:390-396`; `Watchdog._poll_order_statuses()` `apps/reference/domains/execution_position/watchdog.py:392-436`; `ManageFlowFSM._handle_bracket_fill()` `apps/reference/domains/execution_position/fsm_manage.py:1115-1207` | Matcher accepts exchange order id or hardcoded client-id substrings; realistic pre-ACK `TP1-<hash>` ids are not robustly matched. | `YES` | `test_repro_valid_tp_fill_can_be_ignored_when_manage_tracks_client_id_before_ack` |
| `INV-6: One symbol must not silently continue with a new lifecycle over stale execution state.` | `ExecPosFSM.handle()` `apps/reference/domains/execution_position/fsm.py:1499-1645`; `ManageFlowFSM.handle()` `apps/reference/domains/execution_position/fsm_manage.py:438-499` | Reopen is admitted and new fills can be ignored while stale local state survives. | `YES` | `test_repro_local_open_guard_missing_allows_cmd_open_while_manage_tracks`; `test_repro_new_entry_fill_over_tracking_state_keeps_stale_brackets_and_places_none`; `test_repro_rest_flat_vs_local_tracking_divergence_still_admits_reopen` |

### Which tests should become RED/GREEN basis in the repair package

The next implementation package should invert these bug-demonstration tests into fail-closed invariants:

1. `test_repro_local_open_guard_missing_allows_cmd_open_while_manage_tracks`
2. `test_repro_rest_flat_vs_local_tracking_divergence_still_admits_reopen`
3. `test_repro_new_entry_fill_over_tracking_state_keeps_stale_brackets_and_places_none`
4. `test_repro_valid_tp_fill_can_be_ignored_when_manage_tracks_client_id_before_ack`
5. `test_repro_orphan_cleanup_emits_symbol_tidy_but_does_not_reconcile_business_close`

Recommended repair-package naming after inversion:

- `test_open_blocked_when_manage_not_flat`
- `test_split_brain_rest_flat_and_fsm_tracking_blocks_reopen`
- `test_unexpected_new_entry_fill_forces_manage_reconcile_before_brackets`
- `test_tp_fill_matches_preack_client_id_or_exchange_id`
- `test_cleanup_tidy_does_not_count_as_close_reconciliation`

## 6. Remaining Unknowns

- No raw event trail was recovered to prove the real incident chronology for `DOGEUSDT`; `H1` stays `LIKELY`.
- This addendum proves a valid exit event can be ignored by current code, but it does not prove whether the incident used this matcher gap, a true WS drop, or both.
- The current repo evidence proves local lifecycle desync and reopen admission. It still does not prove which external component emitted the real production `CMD:OPEN` first.
- `_has_brackets()` was not found in current code. The earlier report's exact mechanism was stale. The reproduced failure is still real, but it happens earlier in the stale `TRACKING` route.
