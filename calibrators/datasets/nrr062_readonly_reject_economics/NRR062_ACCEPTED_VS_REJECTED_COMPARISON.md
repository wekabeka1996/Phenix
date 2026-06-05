# NRR062_ACCEPTED_VS_REJECTED_COMPARISON

| Metric | Value | Notes |
| --- | --- | --- |
| Accepted Closed Trades | 12 | canonical realized cohort from 03V |
| NRR062 Reject Rows | 153 | canonical reject cohort from frozen order_log |
| Counterfactual Outcome | counterfactual_unavailable | rejected rows do not have realized pnl |
| Median Reject Required Gross TP Floor | 26 | reject-side geometry only |
| Median Reject Gross TP Bps | 79.375 | reject-side geometry only |
| Median Reject Min RR | 1.2 | reject-side geometry only |
| Accepted LOW_VOL Closes | 0 | canonical realized LOW_VOL closes if any |

## Dimension Comparison
| Dimension | Accepted Closed | NRR062 Rejected | Notes |
| --- | --- | --- | --- |
| symbol:BNBUSDT | 5 (41.666667%) | 0 (0.0%) |  |
| symbol:BTCUSDT | 4 (33.333333%) | 47 (30.718954%) |  |
| symbol:ETHUSDT | 1 (8.333333%) | 76 (49.673203%) |  |
| symbol:XRPUSDT | 2 (16.666667%) | 30 (19.607843%) |  |
| side:LONG | 4 (33.333333%) | 39 (25.490196%) |  |
| side:SHORT | 8 (66.666667%) | 114 (74.509804%) |  |
| strategy_id:aurora | 12 (100.0%) | 153 (100.0%) |  |
| regime:LOW_VOLATILITY | 0 (0.0%) | 153 (100.0%) | no canonical accepted LOW_VOL closes in current realized cohort |
| regime:MEAN_REVERSION | 6 (50.0%) | 0 (0.0%) |  |
| regime:TREND_DOWN | 4 (33.333333%) | 0 (0.0%) |  |
| regime:TREND_UP | 2 (16.666667%) | 0 (0.0%) |  |

## Accepted Close Reasons
| Dimension | Accepted Closed | NRR062 Rejected | Notes |
| --- | --- | --- | --- |
| accepted_close_reason:CLOSE | 2 (16.666667%) | 153 (100.0%) | counterfactual_unavailable for rejected rows; accepted outcome distribution shown for context only |
| accepted_close_reason:SL | 1 (8.333333%) | 153 (100.0%) | counterfactual_unavailable for rejected rows; accepted outcome distribution shown for context only |
| accepted_close_reason:TP | 9 (75.0%) | 153 (100.0%) | counterfactual_unavailable for rejected rows; accepted outcome distribution shown for context only |
