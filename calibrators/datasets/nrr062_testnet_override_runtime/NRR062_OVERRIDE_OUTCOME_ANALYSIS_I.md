# NRR062_OVERRIDE_OUTCOME_ANALYSIS_I

## Executive Summary
Override cohort currently contains 5 rid(s) with net_pnl_quote=70.33973751 and verdict=POSITIVE_BUT_SAMPLE_STILL_SMALL.

| Metric | Value | Notes |
| --- | --- | --- |
| override_count | 5 | distinct override-admitted rids |
| submitted_count | 5 | order submitted or downstream order event observed |
| filled_count | 4 | entry fill observed |
| closed_count | 4 | canonical realized close observed |
| exact_roundtrip_count | 4 | canonical realized rows |
| wins | 4 | realized_pnl_net > 0 |
| losses | 0 | realized_pnl_net < 0 |
| unresolved | 1 | no realized pnl sign |
| net_pnl_quote | 70.33973751 | sum over override cohort |
| gross_pnl_quote | 78.38716 | sum over canonical realized rows |
| fees_quote | 8.04742249 | sum over canonical realized rows |
| fee_drag_ratio_of_gross | 0.10266250863023997 | fees / gross when gross available |
| sidecar_observed_rids | 0 | rid count with lifecycle sidecar rows |
| verdict | POSITIVE_BUT_SAMPLE_STILL_SMALL | economics-only cohort verdict |

| Outcome Class | Count |
| --- | --- |
| OVERRIDE_CLOSED_OTHER | 4 |
| OVERRIDE_ORDER_SUBMITTED_NOT_FILLED | 1 |
