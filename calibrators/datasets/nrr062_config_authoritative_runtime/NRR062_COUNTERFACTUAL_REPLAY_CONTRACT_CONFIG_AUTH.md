# NRR062_COUNTERFACTUAL_REPLAY_CONTRACT

## Contract
| Item | Value | Notes |
| --- | --- | --- |
| Entry Price Source | reject_row_low_vol_cost_floor.entry_price | geometry anchor from frozen reject row |
| Entry Timestamp Alignment | replay begins at the first full recorder bar whose inferred open_time_ms is strictly greater than reject_ts_ms; mixed bars containing pre-reject time are excluded | partial bars containing pre-reject time are excluded |
| TP Level Source | reject_row target_price when present, else derived from entry_price and gross_tp_bps | raw target price preferred |
| SL Level Source | reject_row stop_price when present, else derived from entry_price and actual_sl_bps or gross_tp_bps/min_rr | raw stop price preferred |
| Max Horizon Minutes | 120 | explicit replay timeout window |
| Recorder Timeframe Preference | 180, 300, 900 | 180 preferred, then 300, then 900 |
| Fee Model | use structured round_trip_fee_bps from low_vol metadata | no silent cost defaults |
| Slippage Model | use structured slippage_buffer_bps from low_vol metadata | no silent cost defaults |
| Timeout Behavior | if neither TP nor SL hits before horizon end, close at the first recorder bar close with close_time_ms >= horizon_end_ts_ms | bar-close proxy only |
| Same-Bar TP/SL Policy | mark COUNTERFACTUAL_AMBIGUOUS_TP_SL and do not assign gross/net outcome | explicit conservative ambiguity handling |
| Missing Data Policy | fail_closed on missing timestamp, missing geometry, or missing recorder bars | fail closed |

## Coverage
| Metric | Value | Notes |
| --- | --- | --- |
| Reject Rows | 227 | canonical NRR062 reject cohort |
| Replay Ready Rows | 226 | rows with full geometry and recorder bars |
| Rows With Market Path | 227 | bars available after reject timestamp |
| Recorder Timeframe Distribution | {"180": 227} | chosen replay timeframe counts |
