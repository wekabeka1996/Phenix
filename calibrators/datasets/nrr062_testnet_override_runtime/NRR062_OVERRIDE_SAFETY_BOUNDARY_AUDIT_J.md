# NRR062_OVERRIDE_SAFETY_BOUNDARY_AUDIT_J

- nrr062_total_rows: 51
- post_boot_nrr062_surface_rows: 26
- candidate_contract_rows: 26
- candidate_contract_without_override: 0

| surface | post_boot_rows | override_applied_rows | expected_behavior | verdict |
| --- | --- | --- | --- | --- |
| authoritative_candidate_contract | 26 | 26 | should be admitted | PASS |
| candidate_contract_without_override | 0 | 0 | should remain zero | PASS |
| buy_or_long_direction_only | 0 | 0 | no leakage allowed | PASS |
| dual_failure | 0 | 0 | no leakage allowed | PASS |
| geometry_invalid | 0 | 0 | no leakage allowed | PASS |
| live_or_production_candidate_like | 0 | 0 | no leakage allowed | PASS |
| missing_selected_metadata | 0 | 0 | fail closed | PASS |
| sell_direction_only_noncandidate | 0 | 0 | no leakage allowed | PASS |
