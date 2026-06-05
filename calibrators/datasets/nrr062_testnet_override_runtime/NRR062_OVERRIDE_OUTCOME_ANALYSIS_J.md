# NRR062_OVERRIDE_OUTCOME_ANALYSIS_J

| metric | value | notes |
| --- | --- | --- |
| override_count | 26 | distinct admitted override rids in Package J |
| decision_ledger_status_mix | INVALID_FOR_DATASET=2, REJECTED_UPSTREAM=24 | REJECTED_UPSTREAM dominates this retained window |
| canonical_closed_rows | 1 | canonical realized override rows in Package J |
| exact_roundtrip_rows | 1 | exact roundtrips among Package J canonical override closes |
| wins_losses_unresolved | 0 / 1 / 25 | Package J only |
| net_pnl_quote | -13.08771079 | aggregate Package J canonical override net |
| gross_pnl_quote | -11.28317 | aggregate Package J canonical override gross |
| fees_quote | 1.80454079 | aggregate Package J canonical override fees |
| fee_drag_ratio_of_abs_gross | 0.15993207494 | fees divided by absolute gross because Package J gross is negative |
| combined_current_total_i_plus_j | override=31, closes=5, net=57.25202672 | current total sample gate is reached exactly at 31 admitted and 5 canonical closes |
| runtime_verdict | RUNTIME_INSUFFICIENT_CLOSES | J-only close evidence remains too sparse for a contradiction-grade claim |
| outcome_verdict | NEGATIVE_J_WINDOW_SINGLE_CANONICAL_CLOSE | the only resolved J override close is a loss |
