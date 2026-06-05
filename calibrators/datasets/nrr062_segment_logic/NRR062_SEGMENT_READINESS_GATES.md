# NRR062_SEGMENT_READINESS_GATES

Readiness classification: FUTURE_TESTNET_IMPLEMENTATION_CANDIDATE

## Gates
| Gate | Passed? | Evidence |
| --- | --- | --- |
| candidate_rows_gte_20 | True | candidate_rows=79 |
| candidate_estimated_net_positive | True | candidate_estimated_net_pnl_quote=825.2672997047 |
| candidate_profit_factor_gt_1_2 | True | candidate_profit_factor=4.92434390438585 |
| candidate_timeout_share_lte_broad | True | candidate_timeout_share=0.6582278481012658; broad_timeout_share=0.6993464052287581 |
| buy_excluded_net_negative | True | buy_excluded_net=-452.7182366138 |
| dual_failure_excluded_net_negative | True | dual_failure_excluded_net=-194.77884318850002 |
| required_structured_fields_complete | True | excluded_missing_required_fields=0 |
| no_yaml_or_runtime_mutation_needed | True | offline calibrator only; no config/runtime mutation paths in this package |
