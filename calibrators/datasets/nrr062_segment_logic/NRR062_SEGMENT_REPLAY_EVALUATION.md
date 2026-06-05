# NRR062_SEGMENT_REPLAY_EVALUATION

## Candidate Summary
| Metric | Value | Notes |
| --- | --- | --- |
| Row Count | 79 | candidate_would_allow=true rows |
| TP Count | 25 | counterfactual TP rows |
| SL Count | 2 | counterfactual SL rows |
| TIMEOUT Count | 52 | counterfactual TIMEOUT rows |
| AMBIGUOUS Count | 0 | policy excludes ambiguous rows |
| Estimated Gross PnL Quote | 1122.7695276632 | sum across candidate rows |
| Estimated Net PnL Quote | 825.2672997047 | sum across candidate rows |
| Estimated Fees Quote | 238.0017823673 | sum across candidate rows |
| Win Rate | 70.8860759494 | positive estimated net / candidate rows |
| Profit Factor | 4.9243439044 | sum positive net / abs(sum negative net) |
| Timeout Share | 0.6582278481 | timeouts / candidate rows |
| Median Direction Confidence | -0.00991948 | signed raw value from structured metadata |
| Median Regime Confidence | 0.6384541511 | structured regime_confidence median |
| Symbol Distribution | {"BTCUSDT": 31, "ETHUSDT": 37, "XRPUSDT": 11} | candidate symbol counts |
| Side Distribution | {"SELL": 79} | candidate side counts |
| Fee Drag | 238.0017823673 | quote-denominated fee drag |

## Excluded Group Behavior
| Excluded Segment | Rows | Net Proxy | Timeout Share | TP Count | SL Count |
| --- | --- | --- | --- | --- | --- |
| BUY/LONG | 39 | -452.7182366138 | 0.8205128205 | 0 | 7 |
| Dual Regime+Direction Failure | 52 | -194.7788431885 | 0.6730769231 | 8 | 9 |
| All Non-Candidate Rows | 74 | -434.2196127332 | 0.7432432432 | 8 | 11 |
