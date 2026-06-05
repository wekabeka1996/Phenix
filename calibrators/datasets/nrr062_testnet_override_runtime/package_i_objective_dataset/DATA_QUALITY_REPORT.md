# Data Quality Report: objective_stack

## Builder Execution Status

- Builder valid: True
- Schema valid: True
- Diagnostics only: True
- Promotion grade: False

## Dataset Availability

- Rows emitted: 566
- Rows valid: 566
- Rows invalid: 0
- Eligible input rows: 82
- Matched rows: 34
- Unmatched rows: 48
- Match coverage pct: 41.4634
- Has realized outcomes: True
- Exact roundtrips: 32
- Exact roundtrip coverage pct: 39.0244
- Min required rows: 30
- Min required coverage pct: 50.0
- Coverage grade: PARTIAL_DIAGNOSTIC

## Dataset Counts

- Decision rows: 532 (valid: 532)
- Realized trade rows: 34 (valid: 34)
- Exact roundtrips: 32

## Source Inventory

- Authority requests: 0
- Authority responses: 0
- Decision ledger entries: 532
- Executed trades: 0
- Canonical realized rows: 34
- Realized source: canonical_realized_outcome_dataset
- Realized source authority: CANONICAL_REALIZED_OUTCOME_DATASET
- Realized source path: C:\Users\user\Music\Phenix\calibrators\datasets\nrr062_testnet_override_runtime\package_i_realized_dataset\realized_trades.jsonl
- Source promotion grade: False
- Source coverage grade: PARTIAL_DIAGNOSTIC
- Realized source coverage pct: 41.4634

## Promotion Blockers (3)

- SOURCE_REALIZED_DATASET_NOT_PROMOTION_GRADE
- INSUFFICIENT_REALIZED_COVERAGE
- PARTIAL_EXACT_ROUNDTRIPS

## Warnings (2)

- Authority request journal not found: logs\frozen\nrr062_fresh_capture_20260516_101448\data\authority_request_journal_v1.jsonl
- Authority response journal not found: logs\frozen\nrr062_fresh_capture_20260516_101448\data\authority_response_journal_v1.jsonl
