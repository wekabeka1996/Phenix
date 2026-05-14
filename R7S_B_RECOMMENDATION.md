# R7S-B Recommendation

## Final Decision

NOT_PROVEN

## FACTS

- Schema stability is strong: one top-level keyset and zero missing required fields on both sinks.
- Safety is clean: no fee-aware close requests, no authority mutation, no bracket mutation evidence, no exchange-action text hits, no event storm.
- Fee source coverage is strong: realized_lifecycle_fee was present on 24/24 active lifecycles and 660/660 evaluable fee-aware rows.
- Candidate quality is not strong enough: raw percent triggered 21 lifecycles with 6 helped proxies and 11 harmed proxies; each fee_x candidate triggered 20 lifecycles with 5 helped proxies and 11 harmed proxies.
- After subtracting actual realized lifecycle fees, positive_trigger_net_proxy_count was 0 for all six compared candidates.
- fee_x1.5 and fee_x2.0 did not reduce harmed proxies relative to raw percent, and they did not behave differently from fee_x1.0 on this bundle.

## INFERENCES

- READY_FOR_RECOMMENDATION_ONLY_REPLAY is not supported because the helped/harmed balance is not materially better than raw percent, despite strong safety and fee coverage.
- FEE_AWARE_REDUCES_NOISE_BUT_MORE_DATA_NEEDED is also not supported on this bundle because the observed noise reduction is only one fewer triggered lifecycle and zero fewer harmed proxies.
- fee_x1.0 remains too permissive after full fees, but the stricter fee multiples did not establish a cleaner action boundary yet.

## ASSUMPTIONS

- Trigger-net proxy uses authoritative realized lifecycle fees from execution_lifecycle_stats_v1.jsonl and current_edge_usd from the sidecar evaluation row.

## UNKNOWNS

- Whether a larger holdout window or explicit replay engine would reveal a fee multiple that meaningfully reduces harmed outcomes.

## Recommended Posture

- Keep observing passively on the frozen-evidence workflow used here.
- Do not enable live activation.
- Do not promote to recommendation-only replay from this evidence bundle alone.
