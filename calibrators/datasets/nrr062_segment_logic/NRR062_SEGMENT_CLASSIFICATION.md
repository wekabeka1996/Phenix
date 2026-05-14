# NRR062_SEGMENT_CLASSIFICATION

## Summary
| Metric | Value | Notes |
| --- | --- | --- |
| Candidate Name | NRR062_LOW_VOL_SHORT_DIRECTION_ONLY_RAW_SIGNAL_CANDIDATE | offline-only deterministic segment rule |
| Total Rows | 153 | expected canonical reject cohort size |
| Candidate Rows | 79 | rows that the offline candidate would allow |
| Excluded Rows | 74 | rows retained as excluded risk surface |
| Missing Required Fields | 0 | rows excluded for data quality |

## Segment Classes
| Segment Class | Rows |
| --- | --- |
| EXCLUDED_BUY_OR_LONG | 39 |
| EXCLUDED_DUAL_FAILURE | 35 |
| NRR062_LOW_VOL_SHORT_DIRECTION_ONLY_RAW_SIGNAL_CANDIDATE | 79 |

## First Rows
| RID | Segment Class | Candidate? | Symbol | Side | Violation Pattern | Outcome Class | Exclusion Reason |
| --- | --- | --- | --- | --- | --- | --- | --- |
| aurora_ETHUSDT_1778520602841 | EXCLUDED_DUAL_FAILURE | False | ETHUSDT | SELL | regime_confidence_below_threshold+direction_confidence_below_threshold | COUNTERFACTUAL_TIMEOUT | dual_regime_and_direction_failure |
| aurora_ETHUSDT_1778520902840 | EXCLUDED_BUY_OR_LONG | False | ETHUSDT | BUY | direction_confidence_below_threshold | COUNTERFACTUAL_TIMEOUT | buy_or_long |
| aurora_ETHUSDT_1778521504355 | EXCLUDED_BUY_OR_LONG | False | ETHUSDT | BUY | regime_confidence_below_threshold+direction_confidence_below_threshold | COUNTERFACTUAL_TIMEOUT | buy_or_long |
| aurora_ETHUSDT_1778522701096 | EXCLUDED_BUY_OR_LONG | False | ETHUSDT | BUY | regime_confidence_below_threshold+direction_confidence_below_threshold | COUNTERFACTUAL_TIMEOUT | buy_or_long |
| aurora_ETHUSDT_1778523903005 | EXCLUDED_BUY_OR_LONG | False | ETHUSDT | BUY | regime_confidence_below_threshold+direction_confidence_below_threshold | COUNTERFACTUAL_TIMEOUT | buy_or_long |
| aurora_XRPUSDT_1778523903958 | EXCLUDED_BUY_OR_LONG | False | XRPUSDT | BUY | regime_confidence_below_threshold+direction_confidence_below_threshold | COUNTERFACTUAL_TIMEOUT | buy_or_long |
| aurora_ETHUSDT_1778524503918 | EXCLUDED_BUY_OR_LONG | False | ETHUSDT | BUY | direction_confidence_below_threshold | COUNTERFACTUAL_TIMEOUT | buy_or_long |
| aurora_XRPUSDT_1778526302761 | NRR062_LOW_VOL_SHORT_DIRECTION_ONLY_RAW_SIGNAL_CANDIDATE | True | XRPUSDT | SELL | direction_confidence_below_threshold | COUNTERFACTUAL_SL |  |
| aurora_XRPUSDT_1778526904878 | EXCLUDED_DUAL_FAILURE | False | XRPUSDT | SELL | regime_confidence_below_threshold+direction_confidence_below_threshold | COUNTERFACTUAL_TIMEOUT | dual_regime_and_direction_failure |
| aurora_ETHUSDT_1778527202990 | EXCLUDED_BUY_OR_LONG | False | ETHUSDT | BUY | direction_confidence_below_threshold | COUNTERFACTUAL_TIMEOUT | buy_or_long |
