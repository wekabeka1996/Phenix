# NRR062_OVERRIDE_CANONICAL_DATASET_PROPAGATION_AUDIT

## Executive Summary
Canonical realized rows exist for part of the override cohort, while canonical objective decision rows and frozen decision-ledger rows still do not preserve the raw override token.

| Metric | Value | Notes |
| --- | --- | --- |
| total_decisions | 532 | objective dataset decision rows |
| nrr062_reject_rows_order_log | 303 | raw frozen order_log |
| override_rows_order_log | 5 | distinct override-admitted rids |
| accepted_low_vol_order_intents | 5 | raw ORDER_INTENT rows with LOW_VOL metadata |
| canonical_override_closes | 4 | override rids found in realized_trades.jsonl |
| exact_roundtrip_override_rows | 4 | override realized rows with exact_roundtrip=true |
| objective_rows_for_override_rids | 5 | trade_decisions.jsonl rows |
| objective_rows_preserve_override_token | False | schema surface |
| decision_ledger_preserves_override_token | False | frozen ledger surface |
| realized_dataset_diagnostics_only | True | realized manifest |
| objective_dataset_diagnostics_only | True | objective manifest |
| realized_dataset_promotion_grade | False | realized manifest |
| objective_dataset_promotion_grade | False | objective manifest |
