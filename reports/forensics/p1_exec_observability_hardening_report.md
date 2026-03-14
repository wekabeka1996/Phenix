# P1 Execution Observability Hardening Report

## 1. Executive Summary

P1 added structured execution-domain observability around the P0 fail-closed guards without changing entry, exit, risk, or strategy semantics.

The hardening package now makes these incident paths explicit and forensic-readable:

- local reopen blocks via `EVT:EXECUTION_GUARD_BLOCKED`
- split-brain divergence via `EVT:EXECUTION_DIVERGENCE_DETECTED`
- exit matcher success/failure via `EVT:EXIT_MATCH_ATTEMPTED` and `EVT:EXIT_MATCH_FAILED`
- tidy-only maintenance via `EVT:EXECUTION_TIDY_PERFORMED` and enriched `EVT:SYMBOL_TIDY`
- authoritative close reconcile via `EVT:EXECUTION_CLOSE_RECONCILED`

What did **not** change:

- no strategy tuning
- no risk tuning
- no routing/open/close business-logic redesign
- no weakening of the P0 fail-closed repair

## 2. Scope

### Reused surfaces (no-duplication review)

- Reused the existing execution bus (`LocalBus` / injected bus) for new structured events.
- Reused `ExecPosFSM._emit_observability_event(...)` for logger-side structured telemetry.
- Reused `OrderGuardian` structured logging (`extra={"event_type": ...}`) instead of inventing a new logging channel.
- Reused the existing `EVT:SYMBOL_TIDY` gate event and enriched its payload instead of replacing it.

### Code paths covered

- `ExecPosFSM` local reopen guard and divergence block path
- `ManageFlowFSM` stale-lifecycle guard path
- `ManageFlowFSM` TP/SL matcher path
- `OrderGuardian.cleanup_orphans()` tidy path
- `OrderGuardian.reconcile_symbol()` authoritative close reconcile path
- verb registry / JSON schemas for the new event surface

### Deliberately out of scope

- changing open/close admission semantics beyond telemetry side effects
- changing `mean_reversion`, `risk`, or config tuning
- proving `H1` (`WS/order update loss`) beyond `LIKELY`

## 3. Event / Telemetry Contract Changes

### New or expanded structured events

- `EVT:EXECUTION_GUARD_BLOCKED`
  - now includes `ts_ms`, `symbol`, `rid`, `block_reason`, `current_local_state`, `portfolio_truth_state`, `divergence_detected`, `why`
- `EVT:EXECUTION_DIVERGENCE_DETECTED`
  - includes `ts_ms`, `symbol`, `current_rid`, `tracked_rid`, `local_manage_state`, `portfolio_state`, `divergence_type`, `why`
- `EVT:EXIT_MATCH_ATTEMPTED`
  - includes raw ids, normalized client id, inferred role, local expected ids snapshot, matched flag, match reason, local state before/after, `why`
- `EVT:EXIT_MATCH_FAILED`
  - includes raw ids, normalized client id, inferred role, mismatch reason, local expected ids snapshot, `why`
- `EVT:EXECUTION_TIDY_PERFORMED`
  - includes `tidy_reason`, `source`, `business_close_reconciled=false`, `why`
- `EVT:EXECUTION_CLOSE_RECONCILED`
  - includes `source`, `rid`, `business_close_reconciled=true`, `why`
- `EVT:SYMBOL_TIDY`
  - now explicitly carries `tidy_reason`, `business_close_reconciled=false`, and `why`

### Schema / registry changes

Added JSON schemas under `apps/reference/domains/execution_position/schemas/` for:

- `execution_guard_blocked_v1.json`
- `execution_divergence_detected_v1.json`
- `exit_match_attempted_v1.json`
- `exit_match_failed_v1.json`
- `execution_tidy_performed_v1.json`
- `execution_close_reconciled_v1.json`
- `symbol_tidy_v1.json`

Updated `apps/reference/dictionaries/verb_registry_v1.yaml` to register the new execution events and to correct `SYMBOL_TIDY` ownership/schema drift.

### `why` semantics

All new payloads now carry short, explicit `why` values:

- `execution:local_manage_state_conflict`
- `execution:stale_local_lifecycle_conflict`
- `execution:divergence_detected`
- `execution:exit_match_attempted`
- `execution:exit_match_failed`
- `guardian:orphan_cleanup:tidy`
- `guardian:close_reconciled`

## 4. Test Evidence

### RED baseline before implementation

Command:

```powershell
pytest tests/domains/execution_position/test_execution_observability_hardening.py -q
```

Observed output before the code changes:

```text
collected 6 items
5 failed, 1 passed in 8.67s
```

What the RED run proved:

- guard-block telemetry existed only in thin form (`rid` / structured contract missing)
- divergence had no standalone event
- stale local lifecycle conflict emitted no execution guard event
- unmatched exit-like events had no explicit matcher failure telemetry
- tidy lacked an explicit non-business-close marker

### GREEN after implementation + hardening

Commands:

```powershell
pytest tests/domains/execution_position/test_execution_observability_hardening.py -q
pytest tests/domains/execution_position/test_split_brain_repro.py -q
pytest tests/domains/execution_position/test_execpos_cooldown_after_close_v1.py -q
pytest tests/domains/execution_position/test_open_flow_fsm_leverage_and_guards_v1.py -q
pytest tests/domains/execution_position/test_execpos_manage_scenarios_v1.py -q
pytest tests/domains/execution_position -k "split_brain or tracking or bracket or observability" -q
```

Observed outputs:

```text
tests\domains\execution_position\test_execution_observability_hardening.py ....... [100%]
7 passed in 10.28s
```

```text
tests\domains\execution_position\test_split_brain_repro.py ..... [100%]
5 passed in 9.60s
```

```text
tests\domains\execution_position\test_execpos_cooldown_after_close_v1.py .. [100%]
2 passed in 5.13s
```

```text
tests\domains\execution_position\test_open_flow_fsm_leverage_and_guards_v1.py ........ [100%]
8 passed in 0.93s
```

```text
tests\domains\execution_position\test_execpos_manage_scenarios_v1.py ............ [100%]
12 passed in 25.56s
```

```text
63 passed, 292 deselected in 20.87s
```

### Test-by-test coverage

- `test_guard_block_emits_structured_event`
  - proves `local_manage_state_conflict` now emits a structured guard event with `rid`, local state, truth state, and `why`
- `test_divergence_block_emits_structured_divergence_event`
  - proves `REST=FLAT` / `FSM=TRACKING` emits a separate divergence signal
- `test_stale_lifecycle_conflict_emits_structured_guard_event`
  - proves stale local lifecycle conflicts now surface as execution guard telemetry instead of only an `ERR`
- `test_exit_match_success_emits_normalized_attempt`
  - proves successful TP matching now logs normalized id, role inference, match reason, and before/after local state
- `test_exit_match_failure_emits_clear_failed_event`
  - proves unmatched exit-like events now emit explicit failure telemetry instead of silently disappearing
- `test_tidy_event_is_explicitly_non_business_close`
  - proves tidy telemetry explicitly marks `business_close_reconciled=false`
- `test_close_reconcile_event_is_distinct_from_tidy`
  - proves authoritative close reconcile now has its own event and is no longer forced through tidy semantics

## 5. Doc Sync

Synced the post-P0 forensic docs with the runtime after P1 hardening:

- `reports/forensics/p0_exec_hypothesis_matrix.md`
  - kept `H1` at `LIKELY`
  - kept the `_has_brackets()` suppressor theory retired
  - documented the new observability surface
- `reports/forensics/p0_exec_split_brain_summary.md`
  - corrected the stale-bracket narrative to the real stale-`TRACKING` route
  - added a dedicated observability update section
- `reports/forensics/p0_exec_repro_tests_addendum.md`
  - preserved historical repro evidence
  - added a post-P1 observability status note and the new test evidence

## 6. Remaining Blind Spots

- `H1` (`WS/order update loss`) remains `LIKELY`, not `CONFIRMED`; no raw incident-grade payload trail was recovered.
- The new telemetry improves future forensic readiness but does not retroactively prove the original DOGEUSDT event chronology.
- `LocalBus` still logs-and-continues callback exceptions by design; this package improved visibility of execution decisions but did not rework the bus failure model.

## 7. Commands Run

```powershell
pytest tests/domains/execution_position/test_execution_observability_hardening.py -q
pytest tests/domains/execution_position/test_split_brain_repro.py -q
pytest tests/domains/execution_position/test_execpos_cooldown_after_close_v1.py -q
pytest tests/domains/execution_position/test_open_flow_fsm_leverage_and_guards_v1.py -q
pytest tests/domains/execution_position/test_execpos_manage_scenarios_v1.py -q
pytest tests/domains/execution_position -k "split_brain or tracking or bracket or observability" -q
```

## 8. Files Changed

- `apps/reference/domains/execution_position/fsm.py`
- `apps/reference/domains/execution_position/fsm_manage.py`
- `apps/reference/domains/execution_position/order_guardian.py`
- `apps/reference/domains/execution_position/schemas/execution_guard_blocked_v1.json`
- `apps/reference/domains/execution_position/schemas/execution_divergence_detected_v1.json`
- `apps/reference/domains/execution_position/schemas/exit_match_attempted_v1.json`
- `apps/reference/domains/execution_position/schemas/exit_match_failed_v1.json`
- `apps/reference/domains/execution_position/schemas/execution_tidy_performed_v1.json`
- `apps/reference/domains/execution_position/schemas/execution_close_reconciled_v1.json`
- `apps/reference/domains/execution_position/schemas/symbol_tidy_v1.json`
- `apps/reference/dictionaries/verb_registry_v1.yaml`
- `tests/domains/execution_position/test_execution_observability_hardening.py`
- `reports/forensics/p0_exec_hypothesis_matrix.md`
- `reports/forensics/p0_exec_split_brain_summary.md`
- `reports/forensics/p0_exec_repro_tests_addendum.md`
- `reports/forensics/p1_exec_observability_hardening_report.md`
- `JOURNAL.md`
- `TODO.md`

## 9. JOURNAL / TODO

- `JOURNAL.md` updated with the P1 observability hardening package summary and validation evidence.
- `TODO.md` updated to mark the P1 package complete and to leave only the remaining raw-signal blind-spot follow-up (`H1`) open.
