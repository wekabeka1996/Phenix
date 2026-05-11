# AGENT_REPORT_V1

## Executive Summary
03T repaired a runtime observability gap where authoritative close reconciliation could reset execution_position local state without emitting canonical POSITION_CLOSED parity, leaving the dominant 03R unmatched cohort to degrade into trade_lifecycle ORPHANED_TTL evidence only.

## Proven Facts
- 03R left 13 close-expected unmatched rows, of which 8 were ORDER_LOG_MISSING_POSITION_CLOSED_BUT_TRADE_LIFECYCLE_CLOSED and 2 were ORDER_LOG_HAS_ALTERNATIVE_TERMINAL_EVENT.
- In the 03R auditor, trade_lifecycle terminal-close evidence is broader than on_close execution alone: rows with close_ts_ms or non-reject close_reason, including ORPHANED_TTL, count as terminal-close evidence.
- Before 03T, apps/reference/domains/execution_position/orchestration/event_handlers.py was the only canonical writer of trade_lifecycle.on_close, order_log POSITION_CLOSED, and EVT:POSITION_CLOSED, and it required the portfolio edge abs(prev_amt) >= epsilon and abs(now_amt) < epsilon.
- Before 03T, apps/reference/domains/execution_position/fsm.py handled EVT:EXECUTION_CLOSE_RECONCILED by calling _apply_authoritative_local_close_reset() but did not emit canonical POSITION_CLOSED parity.
- apps/reference/domains/execution_position/guardian/order_guardian.py emits EVT:EXECUTION_CLOSE_RECONCILED with symbol/rid/source/ts_ms but not the economic fields required for canonical close truth.
- apps/reference/domains/execution_position/orchestration/event_handlers.py already cached close-fill economics and lifecycle identity per symbol in _close_accounting_truth_by_symbol and related lifecycle caches.
- The 03T patch extracted canonical close emission into EPEventHandlers.emit_position_closed_observability() and reused it from ExecPosFSM._on_execution_close_reconciled() when cached close truth exists.
- Targeted validation passed:
  - tests/domains/execution_position/test_close_fill_truth_propagation.py -> 4 passed
  - tests/domains/execution_position/test_position_closed_event_contract.py, tests/domains/execution_position/test_lifecycle_id_propagation.py, tests/domains/execution_position/test_position_closed_identity.py -> 22 passed, 2 skipped
- Static diagnostics on the touched files reported no editor errors.

## Inferred Findings
- The dominant 8-row 03R cohort was more consistent with missed canonical close emission than with builder bridge drift, because ORPHANED_TTL terminal rows indicate lifecycle finalization after the fact rather than proof that on_close already ran successfully.
- The highest-value root cause was a split between the portfolio-edge producer and the authoritative reconcile path, not a generalized order_logger path failure.
- A bounded reconcile-path parity repair can improve canonical close coverage without changing close execution, config behavior, or terminal non-fill semantics.

## Contradictions / Evidence Gaps
- Copilot_Master_Roadmap.md did not contain an explicit 03T package entry, so package framing remained anchored to runtime evidence and the existing 03R artifact set.
- The 2 ORDER_TIMEOUT / ORDER_CANCELLED rows were not proven realized closes and were intentionally left outside the 03T patch scope.
- The single DECISION_LEDGER_REALIZED_ONLY row and the 2 INCONCLUSIVE rows remain unresolved by runtime code proof alone.
- No fresh live runtime replay was executed in this package, so improvement is proved by contract tests and code-path closure, not by new production logs.

## Root Cause Candidates
- Primary, proved enough to repair: RECONCILIATION_PATH_LACKS_POSITION_CLOSED_PARITY.
- Residual but unpatched: ALTERNATIVE_TERMINAL_EVENT_MISSING_CANONICAL_CLOSE_PARITY for non-fill/cancel rows.
- Residual and unproven: DECISION_LEDGER_REALIZED_FIELD_AUTHORITY_AUDIT for the single decision-ledger-only row.

## Operational Risk
Observability Gap

## Files / Areas Touched
- apps/reference/domains/execution_position/orchestration/event_handlers.py
- apps/reference/domains/execution_position/fsm.py
- tests/domains/execution_position/test_close_fill_truth_propagation.py
- calibrators/datasets/runtime_position_closed_emission_03t/position_closed_producer_map.json
- calibrators/datasets/runtime_position_closed_emission_03t/POSITION_CLOSED_PRODUCER_MAP.md
- calibrators/datasets/runtime_position_closed_emission_03t/position_closed_emission_flow.json
- calibrators/datasets/runtime_position_closed_emission_03t/POSITION_CLOSED_EMISSION_FLOW.md
- calibrators/datasets/runtime_position_closed_emission_03t/position_closed_missing_row_casebook.json
- calibrators/datasets/runtime_position_closed_emission_03t/POSITION_CLOSED_MISSING_ROW_CASEBOOK.md

## Validation Performed
- Configured the repo virtual environment and ran:
  - c:/Users/user/Music/Phenix/.venv/Scripts/python.exe -m pytest tests/domains/execution_position/test_close_fill_truth_propagation.py -q
  - c:/Users/user/Music/Phenix/.venv/Scripts/python.exe -m pytest tests/domains/execution_position/test_position_closed_event_contract.py tests/domains/execution_position/test_lifecycle_id_propagation.py tests/domains/execution_position/test_position_closed_identity.py -q
- Checked editor diagnostics for the touched files; no errors found.

## Residual Risk
- The patch intentionally emits reconcile-path canonical close only when close-fill truth is already cached. This avoids false positives on terminal non-fill/cancel flows but means purely decision-ledger or non-fill anomalies remain out of scope.
- Because the reconcile payload itself does not carry economics, the repair still depends on pre-existing cache population by close-fill handling.

## What Remains Unproven
- Exact post-patch reduction of the historical 03R unmatched cohort in a fresh runtime window.
- Whether the 2 alternative terminal rows should ever be canonicalized as POSITION_CLOSED under a separate policy package.
- Whether the 1 decision-ledger-only row is caused by logging loss, authority drift, or replay artifact sparsity.

## Minimal Safe Verdict
03T safely closes the proved runtime parity gap for authoritative closes that already have cached close-fill truth but miss the portfolio non-zero to zero detector. It does not change trading behavior, does not reinterpret terminal non-fill events as realized closes, and leaves the remaining mixed-cause rows explicitly unproven.
