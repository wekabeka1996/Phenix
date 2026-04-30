# R7I Peak-Giveback Gap List

## Gap 1
- Exact remaining gap: no inspected portfolio snapshot row proves a non-null `markPrice`, `unrealizedPnl`, or `unrealizedPnlPct`.
- Category: runtime proof / economics propagation.
- Why it matters: without a non-null mark, Sidecar cannot economically reconstruct `current_edge_usd`, `giveback_pct`, or a threshold-crossing event.
- Smallest safe next step: collect one more read-only runtime slice while a live position is open and the mark feed is active, then re-run the same forensic audit against the new logs.

## Gap 2
- Exact remaining gap: the shadow journal uses `EVT:EXPOSURE_SUMMARY_UPDATED` for the payload-carrying snapshot, while `EVT:PORTFOLIO_STATE_UPDATED` is present as an empty shell row.
- Category: contract / observability alignment.
- Why it matters: the package asked for `EVT:PORTFOLIO_STATE_UPDATED` proof, so the authoritative carrier name should be unambiguous before anyone treats this as a complete contract validation.
- Smallest safe next step: confirm the intended runtime carrier in the docs or schema, then repeat the same read-only audit against that exact event.

