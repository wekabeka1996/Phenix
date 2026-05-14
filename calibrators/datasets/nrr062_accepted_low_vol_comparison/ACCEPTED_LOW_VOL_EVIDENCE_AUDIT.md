# ACCEPTED_LOW_VOL_EVIDENCE_AUDIT

Authority caveat: CURRENT_WORKSPACE_REFERENCE_ONLY_NOT_RUNTIME_AUTHORITY

## Class Counts
| Class | Count | Notes |
| --- | --- | --- |
| CANONICAL_ACCEPTED_LOW_VOL_CLOSE | 0 | audit summary |
| ACCEPTED_LOW_VOL_DECISION_NO_CLOSE | 0 | audit summary |
| LOW_VOL_CLOSE_NON_CANONICAL | 0 | audit summary |
| LOW_VOL_SIDE_CAR_CLOSE_ONLY | 0 | audit summary |
| LOW_VOL_DIAGNOSTIC_ONLY | 1 | audit summary |
| NO_LOW_VOL_ACCEPTED_EVIDENCE | 0 | audit summary |

## Facts
| Metric | Value | Notes |
| --- | --- | --- |
| accepted_economics_low_vol_trade_count | 0 | from accepted_closed_trade_economics_deepdive.json by_regime |
| regime_confidence_audit_low_vol_rows | 1684 | ambient LOW_VOL regime rows in frozen audit surface |
| trade_lifecycle_scanned_for_candidate_lifecycle_ids | False | only scanned when a low-vol accepted candidate needed terminal close verification |

## Candidate Rows
| Class | RID | Symbol | Side | Strategy | Regime | Decision Status | Close Status | Realized Net | Data Quality |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| LOW_VOL_DIAGNOSTIC_ONLY | aurora_BTCUSDT_1778669703907 | BTCUSDT | short | aurora | LOW_VOLATILITY | CANONICAL_CLOSED | CANONICAL_CLOSED | 11.472229 | LOW_VOL_REFERENCE_INFERENCE_CONFLICTS_WITH_ACCEPTED_ECONOMICS_REGIME_SUMMARY |
