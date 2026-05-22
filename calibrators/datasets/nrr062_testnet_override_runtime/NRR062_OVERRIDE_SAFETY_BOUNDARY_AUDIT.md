# NRR062_OVERRIDE_SAFETY_BOUNDARY_AUDIT

## Executive Summary
Runtime evidence shows exactly 1 override-applied order_log row in the post-deploy observation tail after the last BOOT boundary at line 1734 / ts_ms 1778842508184. All observed contrast sets that should remain blocked stayed blocked in that post-boot window.

## Proven Facts
- Frozen-window NRR-062 surface rows in order_log: 298
- Observation scope: post-last-BOOT-before-override
- Observation BOOT boundary: line 1734 / ts_ms 1778842508184
- Post-boot NRR-062 surface rows: 1
- Historical pre-boot candidate-contract rows excluded from post-deploy audit: 121
- trade_lifecycle malformed lines skipped: 7
- Candidate-contract rows in post-boot tail: 1
- Candidate-contract rows missing override admission in post-boot tail: 0
- BUY/LONG direction-only rows in post-boot tail: 0 (override leakage: 0)
- Dual-failure rows in post-boot tail: 0 (override leakage: 0)
- Geometry-invalid rows: 0 (override leakage: 0)
- SELL direction-only non-candidate rows in post-boot tail: 0 (override leakage: 0)

## Boundary Verdicts
| Boundary Set | Rows | Override Leakage | Verdict |
| --- | ---: | ---: | --- |
| BUY/LONG direction-only | 0 | 0 | PASS |
| Dual failure | 0 | 0 | PASS |
| Geometry invalid | 0 | 0 | PASS |
| SELL direction-only non-candidate | 0 | 0 | PASS |

## Inference
No post-deploy runtime evidence suggests widening beyond the intended SELL-only, direction-only, raw-signal contract. The larger frozen bundle still contains 121 pre-boot historical candidate rows that were rejected before this restart boundary; they are not evidence against the deployed override behavior under observation. Code-level tests remain required to prove the non-runtime boundaries that were not exercised in the post-boot tail.
