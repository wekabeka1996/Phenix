# NRR062_ACCEPTED_LOW_VOL_COMPARISON

| Metric | Value | Notes |
| --- | --- | --- |
| comparison_status | ACCEPTED_LOW_VOL_COMPARISON_BLOCKED | No accepted LOW_VOL close or accepted-decision evidence was found in canonical or runtime-adjacent surfaces. |
| rejected_low_vol_sell_segment | {"side": "SELL", "rows": 114, "tp_count": 33, "sl_count": 6, "timeout_count": 75, "estimated_net_pnl_quote": 843.7659235853} | package B replay segment |
| rejected_low_vol_buy_segment | {"side": "BUY", "rows": 39, "tp_count": 0, "sl_count": 7, "timeout_count": 32, "estimated_net_pnl_quote": -452.7182366138} | package B replay segment |
| direction_only_failure_segment | {"violation_pattern": "direction_confidence_below_threshold", "rows": 101, "tp_count": 25, "sl_count": 4, "timeout_count": 72, "estimated_net_pnl_quote": 585.82653016} | package B replay segment |
| dual_failure_segment | {"violation_pattern": "regime_confidence_below_threshold+direction_confidence_below_threshold", "rows": 52, "tp_count": 8, "sl_count": 9, "timeout_count": 35, "estimated_net_pnl_quote": -194.7788431885} | package B replay segment |
| accepted_low_vol_class_counts | {"CANONICAL_ACCEPTED_LOW_VOL_CLOSE": 0, "ACCEPTED_LOW_VOL_DECISION_NO_CLOSE": 0, "LOW_VOL_CLOSE_NON_CANONICAL": 0, "LOW_VOL_SIDE_CAR_CLOSE_ONLY": 0, "LOW_VOL_DIAGNOSTIC_ONLY": 1, "NO_LOW_VOL_ACCEPTED_EVIDENCE": 0} | package C accepted evidence audit counts |
