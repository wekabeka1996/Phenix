# NRR062_EXISTING_FIELD_CANDIDATE_RANKING

## Conservative Scoring
| Term | Definition |
| --- | --- |
| net_pnl_term | + estimated_net_pnl_quote |
| timeout_penalty | - timeout_share * 250.0 |
| buy_negative_penalty | - max(0, -buy_net_quote - 50.0) |
| dual_negative_penalty | - max(0, -dual_failure_net_quote - 50.0) |
| fee_drag_penalty | - estimated_fees_quote * 0.25 |

## Ranked Candidates
| Candidate | Score | Newly Admitted | Net Proxy | BUY Net | SELL Net | Timeout Share | Classification |
| --- | --- | --- | --- | --- | --- | --- | --- |
| BASELINE_CURRENT | 0 | 0 | 0 | 0 | 0 |  | NO_CHANGE_BEST |
| MIN_RR_1.0 | -0.001 | 0 | 0 | 0 | 0 |  | INSUFFICIENT_EDGE |
| MIN_RR_1.1 | -0.001 | 0 | 0 | 0 | 0 |  | INSUFFICIENT_EDGE |
| MIN_TP_FEE_COVERAGE_2.0 | -0.001 | 0 | 0 | 0 | 0 |  | INSUFFICIENT_EDGE |
| MIN_TP_FEE_COVERAGE_2.5 | -0.001 | 0 | 0 | 0 | 0 |  | INSUFFICIENT_EDGE |
| RAW_LOW_VOL_0.15 | -0.001 | 0 | 0 | 0 | 0 |  | INSUFFICIENT_EDGE |
| RAW_LOW_VOL_0.18 | -0.001 | 0 | 0 | 0 | 0 |  | INSUFFICIENT_EDGE |
| RAW_LOW_VOL_0.20 | -0.001 | 0 | 0 | 0 | 0 |  | INSUFFICIENT_EDGE |
| RAW_LOW_VOL_0.22 | -0.001 | 0 | 0 | 0 | 0 |  | INSUFFICIENT_EDGE |
| RAW_LOW_VOL_0.23 | -0.001 | 0 | 0 | 0 | 0 |  | INSUFFICIENT_EDGE |
