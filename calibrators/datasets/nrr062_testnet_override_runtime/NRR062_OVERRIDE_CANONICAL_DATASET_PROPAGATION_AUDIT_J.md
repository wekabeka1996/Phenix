# NRR062_OVERRIDE_CANONICAL_DATASET_PROPAGATION_AUDIT_J

| metric | value | interpretation |
| --- | --- | --- |
| nrr062_reject_rows_order_log | 25 | raw rejected NRR-062 rows in the retained J order log |
| override_rows_order_log | 26 | distinct admitted override ORDER_INTENT rows |
| accepted_low_vol_order_intents | 26 | authoritative override admission surface |
| objective_rows_for_override_rids | 26 | canonical trade decision rows found for override rids |
| canonical_override_closes | 1 | canonical realized rows matched to override rids |
| exact_roundtrip_override_rows | 1 | exact roundtrips among canonical override closes |
| realized_match_coverage_pct | 12.9032 | diagnostics-only realized coverage |
| realized_coverage_grade | SPARSE_DIAGNOSTIC | realized dataset not promotion-grade |
| objective_coverage_grade | SPARSE_DIAGNOSTIC | objective dataset inherits diagnostic realized coverage |
| objective_rows_preserve_override_token | false | canonical objective rows do not preserve raw override truth |
| decision_ledger_preserves_override_token | false | frozen decision ledger also does not preserve the token |
| objective_warnings | Authority request journal not found: c:\Users\user\Music\Phenix\logs\frozen\nrr062_fresh_capture_20260517_080431\data\authority_request_journal_v1.jsonl; Authority response journal not found: c:\Users\user\Music\Phenix\logs\frozen\nrr062_fresh_capture_20260517_080431\data\authority_response_journal_v1.jsonl | frozen-bundle authority-journal limitation |
| realized_warning | TRADE_LIFECYCLE_JSON_ERRORS:1 | retained trade_lifecycle caveat |
