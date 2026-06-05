# NRR062_SEGMENT_VS_BROAD_REPLAY

## Broad vs Candidate
| Metric | Broad Package B | Candidate Segment | Interpretation |
| --- | --- | --- | --- |
| Rows | 153 | 79 | candidate is a strict subset of Package B replay surface |
| TP Count | 33 | 25 | candidate kept TP subset |
| SL Count | 13 | 2 | candidate retained SL subset |
| TIMEOUT Count | 107 | 52 | timeout concentration check |
| Estimated Net PnL Quote | 391.0476869715 | 825.2672997047 | positive signal retention check |
| Profit Factor | 1.4120756633 | 4.9243439044 | candidate quality vs broad quality |
| Timeout Share | 0.6993464052 | 0.6582278481 | timeout dominance check |

## Questions
| Question | Answer | Evidence |
| --- | --- | --- |
| Does the candidate retain the positive replay signal? | yes | candidate_net=825.2672997047 |
| Does it exclude most negative BUY exposure? | yes | excluded_buy_net=-452.7182366138 |
| Does it exclude dual-failure negative exposure? | yes | excluded_dual_failure_net=-194.77884318850002 |
| Is timeout share still too high? | no | candidate_timeout_share=0.6582278481012658, broad_timeout_share=0.6993464052287581 |
| Is candidate row count large enough to matter? | yes | candidate_rows=79, readiness_min_rows=20 |
| Would this be a reasonable future testnet implementation candidate? | yes | candidate_rows=79, candidate_net=825.2672997047 |
