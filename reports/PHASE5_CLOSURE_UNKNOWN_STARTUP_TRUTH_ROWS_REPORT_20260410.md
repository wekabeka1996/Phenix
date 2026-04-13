# REPORT — Phase 5 Closure Unknown Startup Truth Rows

## 1. Executive Summary

This package closes the remaining Phase 5 closure blocker identified by the independent closure audit: degraded authoritative-startup cases no longer drop observed symbols into silence.

Startup truth now emits explicit per-symbol lifecycle `UNKNOWN` rows when:
- authoritative restore is attempted in `authoritative` mode,
- the restore envelope is `missing`, `corrupt`, `not_readable`, or `stale`,
- a symbol is still observed from startup inputs,
- and no exact restored row and no exact reconstructed row exist for that symbol.

No new authority path was introduced.
No replay behavior was introduced.
No portfolio-derived lifecycle guessing was introduced.

## 2. FACTS

- The prior startup-truth path already persisted:
  - `restore_authoritative`
  - `runtime_truth_records`
  - `execution_truth_cache`
- The prior gap was that `restore_authoritative.symbol_statuses` stayed empty when the artifact was unusable, and startup truth had no dedicated place to persist explicit lifecycle unknowns for observed symbols.
- The new model adds `unknown_truth_records` to the startup-truth artifact in [restore_artifact.py](/C:/Users/user/Music/Phenix/apps/reference/domains/execution_position/restore_artifact.py).
- The new finalization path builds unknown rows from:
  - `symbols_considered`
  - `position_symbols_observed`
  - `pre_cleanup_order_symbols_observed`
  - `guardian_symbols_observed`
  - `fresh_order_symbols_observed`
  and excludes symbols that already have exact restored or exact reconstructed truth in [fsm.py](/C:/Users/user/Music/Phenix/apps/reference/domains/execution_position/fsm.py).
- The runtime proof artifact was captured at:
  - [degraded_startup_truth_row.json](/C:/Users/user/Music/Phenix/reports/runtime_restore_unknown_startup_proof_20260410/degraded_startup_truth_row.json)
  - [summary.json](/C:/Users/user/Music/Phenix/reports/runtime_restore_unknown_startup_proof_20260410/summary.json)

## 3. INFERENCES

- The missing closure behavior was a startup-truth persistence omission, not an authoritative-restore bug.
- A dedicated `unknown_truth_records` section is the smallest additive-safe design because it keeps restored exact, reconstructed, unknown, and cache-only categories separate instead of overloading reconstruction rows.
- The package is sufficient to justify re-running the full Phase 5 closure audit because the prior blocker was specifically about degraded-startup explainability.

## 4. ASSUMPTIONS

- The startup-truth artifact is an operator-visible truth plane and therefore must carry explicit degraded lifecycle unknowns rather than leaving them implicit in empty arrays.
- `position_symbols_observed` is the strongest machine-visible evidence for `portfolio_present_without_restored_lifecycle_truth`.

## 5. UNKNOWNS

- Whether future work will want additional non-portfolio startup-input reason codes beyond the minimal set added here.
- Whether a future closure audit will want the unknown-truth count summarized at top level in addition to the explicit rows already persisted.

## 6. Startup Truth Gap Root Cause

### Symptom

In degraded authoritative-startup cases, startup truth could show:
- observed symbols in `symbols_considered` / `position_symbols_observed`,
- unusable authoritative artifact state,
- no restored rows,
- no reconstructed rows,

while still persisting no per-symbol lifecycle truth rows for those observed symbols.

### Root cause

The startup-truth artifact had no dedicated model for explicit lifecycle-unknown rows, and `_finalize_restore_authoritative_status()` only annotated existing authoritative rows. When `symbol_statuses` was empty, the degraded symbol set disappeared from lifecycle truth persistence.

### Contributing factors

- `restore_authoritative.symbol_statuses` is empty by design for unusable artifacts.
- `runtime_truth_records` only covered reconstructed or unresolved runtime bracket truth, not lifecycle unknown caused by unusable restore authority.

### Masking layer

The global artifact-state diagnostics (`missing`, `corrupt`, `not_readable`, `stale`) were present, which made the degraded condition visible globally, but not per symbol.

## 7. Unknown Row Design

Structure added:
- `unknown_truth_records[]`

Each row carries:
- `symbol`
- `lifecycle_truth_class = "unknown"`
- `authoritative_artifact_state`
- `portfolio_presence`
- `reconstructed_exact_truth_present`
- `observed_inputs[]`
- `reason_codes[]`

Truth class:
- explicit lifecycle `unknown`

Reason fields:
- `authoritative_artifact_missing`
- `authoritative_artifact_corrupt`
- `authoritative_artifact_not_readable`
- `authoritative_artifact_stale`
- `portfolio_present_without_restored_lifecycle_truth`

Why sufficient:
- It gives operators a machine-visible symbol row instead of silence.
- It does not invent `manage_phase`, `close_phase`, or bracket linkage.
- It keeps restored exact, reconstructed, unknown, and cache-only as separate categories.

## 8. Before vs After Startup Truth Behavior

### Degraded artifact case

Before:
- observed symbol could appear only in `symbols_considered` / `position_symbols_observed`
- no per-symbol lifecycle row was persisted

After:
- the same symbol gets an explicit `unknown_truth_records[]` row with artifact-state reason and portfolio-presence context

### Exact restore case

Behavior remains bounded:
- exact restored symbols stay in `restore_authoritative.symbol_statuses`
- no duplicate unknown row is emitted

### Reconstructed case

Behavior remains bounded:
- exact reconstructed symbols stay in `runtime_truth_records`
- no duplicate unknown row is emitted

## 9. Tests Added

- `test_degraded_authoritative_startup_emits_explicit_unknown_rows_for_observed_symbols`
  - proves `missing`, `corrupt`, and `stale` startup cases emit explicit per-symbol unknown rows
- `test_degraded_authoritative_startup_emits_unknown_row_for_not_readable_artifact`
  - proves the `not_readable` startup case emits an explicit unknown row
- `test_degraded_authoritative_startup_does_not_emit_unknown_row_when_runtime_reconstruction_is_exact`
  - proves no duplicate unknown row is emitted when exact runtime reconstruction exists
- existing degraded-startup tests were tightened to assert `unknown_truth_records`
  - proves missing/corrupt/stale with loaded cache still remain non-authoritative and explicit
- existing exact-restore / exact-runtime-override tests were tightened to assert `unknown_truth_records == []`
  - proves exact truth is not duplicated as unknown

## 10. Runtime Proof Artifact

Files:
- [degraded_startup_truth_row.json](/C:/Users/user/Music/Phenix/reports/runtime_restore_unknown_startup_proof_20260410/degraded_startup_truth_row.json)
- [summary.json](/C:/Users/user/Music/Phenix/reports/runtime_restore_unknown_startup_proof_20260410/summary.json)

Visible categories in the captured proof:
- restored exact: none in this degraded case
- reconstructed: `BTCUSDT`
- unknown: `ETHUSDT`
- cache-only: `execution_truth_cache.truth_class = cache_only`

## 11. Validation Evidence

Pytest command:

```text
python -m pytest tests/domains/execution_position/test_execution_restore_authoritative_read.py tests/domains/execution_position/test_restart_runtime_truth_reconstruction.py tests/domains/execution_position/test_execution_restore_dark_read.py tests/config/test_execution_position_restore_artifact_config_contract.py tests/domains/execution_position/test_execution_restore_artifact_writer.py tests/domains/execution_position/test_restart_seeded_execution_truth_warm_state.py -q
```

Result:

```text
63 passed in 186.93s (0:03:06)
```

## 12. Residual Risks

- This package does not itself declare Phase 5 closed; it closes the specific blocker required to re-run the closure audit.
- The explicit unknown plane currently relies on startup inputs already being collected correctly; it does not invent missing startup symbols.

## 13. Final Phase 5 Closure Readiness Note

This package should allow re-running the Phase 5 closure audit.

Reason:
- degraded authoritative-startup cases no longer collapse observed symbols into silence
- persisted startup truth now carries explicit per-symbol lifecycle unknowns with operator-visible reasons
- no exact restored or exact reconstructed truth is overwritten or duplicated
- no 5B.4 or 5B.5 authority boundary was weakened
