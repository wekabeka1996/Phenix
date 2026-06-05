# NRR062_OVERRIDE_ROLLBACK_GATE_I

## Executive Summary
Rollback verdict: NO_ROLLBACK_SIGNAL_TESTNET_ONLY_CONTINUE_COLLECTION.

| Condition | Value | Notes |
| --- | --- | --- |
| override_observed | True | override-admitted rid present in frozen window |
| boundary_leak_detected | False | includes missing override on candidate-contract rows |
| override_outside_testnet_hybrid | False | live/production leakage |
| realized_positive | True | aggregate net positive |
| sl_or_adverse_close_dominates | False | SL or soft-close exceeds TP count |
| sidecar_fee_drag_spike | False | conservative fees>=gross check |
| metadata_missing_blocks_audit | False | required override metadata absent |
| objective_rows_preserve_override_token | False | canonical objective surface |
| decision_ledger_preserves_override_token | False | frozen ledger surface |
| sample_size_sufficient_for_promotion | False | explicitly not promotion-grade yet |
