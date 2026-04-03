# Bucket D DOGEUSDT Post-Watchdog Durable Truth Fix Implementation - 2026-04-01

## 1. Executive Summary
FACT: Implemented a minimal repair at the watchdog recovered-fill seam already proven by the 2026-04-01 Bucket D forensics.

FACT: Recovered `FILLED` and `PARTIALLY_FILLED` orders are no longer silently terminalized when canonical `EVT:TRADE_EXECUTED` emission is unavailable.

FACT: The watchdog now canonicalizes recovered-fill payloads before emission and fail-closes until canonical emission succeeds.

FACT: Focused validation passed for the changed watchdog path and the new downstream continuation proof.

INFERENCE: This closes the specific durable-truth loss mode where watchdog-recovered fill truth could die before canonical bus ingress and later collapse into `ORPHANED_TTL`.

## 2. Proven Repair Point
FACT: The narrowest safe repair point was the `FILLED` / `PARTIALLY_FILLED` branch inside `OrderTimeoutWatchdog._poll_order_statuses()` in `apps/reference/domains/execution_position/watchdog.py`.

FACT: Pre-fix, that branch could still local-terminalize and remove tracking even when `emit_fn` was missing, which matched the previously proven pre-wrapper seam.

FACT: `FSMCore.emit()` only creates durable bus-ingress proof after the event reaches the canonical emission path, so the correct repair point was upstream of wrapper/bus internals, not downstream consumers.

INFERENCE: Repairing deeper layers would have been broader than needed and would not have removed the watchdog-side silent-drop branch.

## 3. Files Changed
- `apps/reference/domains/execution_position/watchdog.py`
- `tests/domains/execution_position/test_watchdog.py`
- `tests/domains/test_watchdog_polling_fix.py`
- `tests/domains/execution_position/test_execution_truth_continuation_non_cmd_close_identity_restart.py`

## 4. Code Changes By File
- `apps/reference/domains/execution_position/watchdog.py`: added `_build_trade_executed_payload(...)` to construct a canonical watchdog payload via `normalize_trade_executed_payload(...)`; added `_emit_recovered_trade_executed(...)` with explicit attempt/success logging and fail-closed behavior when `emit_fn` is absent; changed the recovered-fill branch so tracking is removed only after canonical emission succeeds; on emission failure the watchdog logs an explicit failure marker and re-raises into the existing retry/backoff path.
- `tests/domains/execution_position/test_watchdog.py`: updated filled-path expectations to the canonical payload shape and added a regression proving that a missing emit hook no longer silently clears tracked orders.
- `tests/domains/test_watchdog_polling_fix.py`: aligned mock REST payloads and assertions with canonical watchdog emission, including normalized side and string quantity handling.
- `tests/domains/execution_position/test_execution_truth_continuation_non_cmd_close_identity_restart.py`: strengthened watchdog identity assertions and added integration-style coverage proving a watchdog-recovered fill reaches canonical bus ingress and downstream portfolio truth.

## 5. Why This Fix Is Narrow And Safe
FACT: The patch is confined to the watchdog recovered-fill path.

FACT: No websocket correlation logic, strategy policy, scoring, `ORPHANED_TTL` policy, or event-bus contract was changed.

FACT: Payload normalization reuses the existing canonical `TRADE_EXECUTED` helper instead of introducing a new schema or parallel contract.

FACT: The repaired behavior is fail-closed: if canonical emission cannot happen, the watchdog keeps the order tracked for retry instead of incorrectly treating local observation as durable truth.

INFERENCE: This is safer than the previous behavior because it preserves retryability and prevents false local completion from masking canonical truth failure.

## 6. Tests Added
- `test_poll_order_statuses_filled_without_emit_hook_keeps_tracking_for_retry`
- `test_watchdog_recovered_fill_reaches_canonical_bus_ingress_and_portfolio_truth`
- Strengthened existing watchdog payload identity/canonicalization assertions in the focused watchdog test suite.

## 7. Validation Evidence
FACT: Editor diagnostics reported no errors in the four changed implementation/test files.

FACT: Focused pytest validation passed for:
- `tests/domains/execution_position/test_watchdog.py`
- `tests/domains/test_watchdog_polling_fix.py`
- `tests/domains/execution_position/test_execution_truth_continuation_non_cmd_close_identity_restart.py`

FACT: Result: `20 passed in 10.22s`.

FACT: The new integration-style coverage proves the repaired seam end-to-end by asserting at least one watchdog-origin `EVT:TRADE_EXECUTED` journal ingress and downstream `EVT:PORTFOLIO_STATE_UPDATED` truth.

## 8. Regression Check Results
FACT: Adjacent regression coverage in `tests/domains/execution_position/test_late_ack_reject_race_and_fill_truth_reconciliation.py` passed.

FACT: Adjacent telemetry regression coverage in `tests/telemetry/test_shadow_critical_event_journal.py` exposed one failure in `test_shadow_journal_fail_open_and_duplicate_fill_marker`.

FACT: The failure reason was a test payload that emitted `EVT:TRADE_EXECUTED` without required `side`, which `FSMCore.emit()` correctly rejected with schema validation.

FACT: That telemetry failure was not changed by this fix and was left out of scope to keep the repair localized to the proven watchdog recovered-fill seam.

## 9. Remaining Risks / Unknowns
FACT: The websocket correlation miss that causes watchdog recovery remains out of scope and unfixed.

FACT: This repair closes the proven watchdog-side silent-loss path, but it does not prove that no other identity or lifecycle gaps exist elsewhere in the execution pipeline.

FACT: The adjacent telemetry test still needs its payload updated if that suite is expected to pass under the current strict `TRADE_EXECUTED` contract.

FACT: The repo instructions referenced `docs/ai/AGENT_REPORT_SCHEMA.md`, `docs/ai/DONE_CRITERIA.md`, and `docs/ai/VERB_EVENT_INSTRUCTIONS.md`, but those files were not present at the expected paths during final reporting; this artifact therefore follows the explicit 9-section task contract plus validated runtime/test evidence.
