# NRR062_OVERRIDE_SAFETY_BOUNDARY_AUDIT_I

## Executive Summary
Observation scope is the post-last-BOOT tail before the first override in the retained window. Candidate-contract rows=5, missing_override=0.

## Proven Facts
- frozen nrr062 surface rows: 308
- post-boot nrr062 surface rows: 11
- observation boot boundary: line 1734 / ts_ms 1778842508184
- pre-boot candidate-contract rows excluded: 0
- override-applied rows in post-boot surface: 5
- candidate-contract rows in post-boot surface: 5
- candidate-contract rows without override admission: 0

| Boundary | Rows | Override Leakage | Status |
| --- | --- | --- | --- |
| buy_or_long_direction_only | 3 | 0 | PASS |
| dual_failure | 3 | 0 | PASS |
| geometry_invalid | 0 | 0 | PASS |
| live_or_production_candidate_like | 0 | 0 | PASS |
| missing_selected_metadata | 0 | 0 | PASS |
| sell_direction_only_noncandidate | 0 | 0 | PASS |
