# SIDECAR_CLOSE_USEFULNESS_DEEPDIVE_READONLY

## Summary

| Metric | Value | Notes |
| --- | --- | --- |
| sidecar_recommendations | 15 | from 03U sidecar summary |
| close_requests | 15 | from 03U sidecar summary |
| reconciled_close_runtime_ids | 15 | observed runtime ids |
| observed_position_closed_rows | 15 | order_log POSITION_CLOSED with ppsreq rid |
| canonical_realized_sidecar_closes | 0 | expected 0 in this window |
| observed_net_pnl | -92.866717 | observational only |
| observed_fees | 39.278717 | observational only |
| observed_implied_gross_pnl | -53.588 | net + fees when explicit gross absent |
| winner_count | 4 | observed closes only |
| loser_count | 11 | observed closes only |
| fee_dominated_count | 2 | observed closes only |

## Evidence Gaps

- canonical_realized_sidecar_closes=0, so usefulness remains observational-only
- no counterfactual baseline exists for avoided-loss or cut-winner claims
- peak_giveback snapshots are sidecar-time observations, not authoritative full path statistics
