# CANONICALIZATION_REPORT

## Summary
- close_rows_total: 65
- eligible_close_rows: 34
- exact_rid_matches: 4
- suffix_trim_matches: 30
- duplicate_close_candidates: 0
- blocker_duplicate_ambiguity_count: 0

## Rules
- Primary exact join key is decision_ledger rid to order_log POSITION_CLOSED rid.
- Close-event canonicalization allows a single trailing suffix trim at ':' for close rid values such as rid:TP.
- Only POSITION_CLOSED rows are eligible realized close evidence in v1.
- Duplicate close rows prefer realized_pnl_net + fees completeness, then resolved pnl_status, then latest timestamp.
- Duplicate close rows are never summed in v1.
- Entry enrichment uses exact ORDER_FILLED ENTRY rows keyed by decision rid through lifecycle_id or exact rid; missing entry data leaves exact_roundtrip false.