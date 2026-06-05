# NRR062_CURRENT_BOUNDARY_RECONSTRUCTION

## Failure Summary
| Failure Type | Rows | Notes |
| --- | --- | --- |
| direction_only_failure | 101 | direction/raw threshold fails while current regime threshold passes |
| regime+direction_failure | 52 | both current regime and raw threshold fail |
| geometry_failure | 0 | geometry / TP fee coverage / RR would fail |
| unknown | 0 | no requested classification matched |

## Boundary Facts
| Metric | Value | Notes |
| --- | --- | --- |
| Current Raw Threshold LOW_VOLATILITY | 0.25 | explicit min_raw_score_by_regime LOW_VOLATILITY value |
| Current Regime Threshold LOW_VOLATILITY | 0.39 | base regime threshold before strategy+symbol overrides |
| Max Raw Score Abs In Cohort | 0.053739 | requested sweep floor never goes below 0.15 |
| Min TP Fee Coverage Ratio | 9.921875 | all rows remain above current min_tp_fee_coverage |
| Min RR Ratio | 1.25 | all rows remain above current min_rr |
| Min Gross TP Bps | 79.375 | all rows remain above current required gross TP floor |
