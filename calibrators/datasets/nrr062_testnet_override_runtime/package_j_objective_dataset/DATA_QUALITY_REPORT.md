# Data Quality Report: objective_stack

## Builder Execution Status

- Builder valid: True
- Schema valid: True
- Diagnostics only: True
- Promotion grade: False

## Dataset Availability

- Rows emitted: 592
- Rows valid: 592
- Rows invalid: 0
- Eligible input rows: 31
- Matched rows: 4
- Unmatched rows: 27
- Match coverage pct: 12.9032
- Has realized outcomes: True
- Exact roundtrips: 3
- Exact roundtrip coverage pct: 9.6774
- Min required rows: 30
- Min required coverage pct: 50.0
- Coverage grade: SPARSE_DIAGNOSTIC

## Dataset Counts

- Decision rows: 588 (valid: 588)
- Realized trade rows: 4 (valid: 4)
- Exact roundtrips: 3

## Source Inventory

- Authority requests: 0
- Authority responses: 0
- Decision ledger entries: 588
- Executed trades: 0
- Canonical realized rows: 4
- Realized source: canonical_realized_outcome_dataset
- Realized source authority: CANONICAL_REALIZED_OUTCOME_DATASET
- Realized source path: c:\Users\user\Music\Phenix\calibrators\datasets\nrr062_testnet_override_runtime\package_j_realized_dataset\realized_trades.jsonl
- Source promotion grade: False
- Source coverage grade: SPARSE_DIAGNOSTIC
- Realized source coverage pct: 12.9032

## Promotion Blockers (4)

- SOURCE_REALIZED_DATASET_NOT_PROMOTION_GRADE
- INSUFFICIENT_REALIZED_ROWS
- INSUFFICIENT_REALIZED_COVERAGE
- PARTIAL_EXACT_ROUNDTRIPS

## Warnings (2)

- Authority request journal not found: c:\Users\user\Music\Phenix\logs\frozen\nrr062_fresh_capture_20260517_080431\data\authority_request_journal_v1.jsonl
- Authority response journal not found: c:\Users\user\Music\Phenix\logs\frozen\nrr062_fresh_capture_20260517_080431\data\authority_response_journal_v1.jsonl
