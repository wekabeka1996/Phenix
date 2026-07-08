# AURORA_AGENT_CONTROL_P11_SCENARIO_MEMORY_CORPUS_EXPANSION_AND_FRESH_RUNTIME_REBUILD

## Problem framing

P10 indexing was structurally valid but backed by one completed review. P11 expands the corpus deterministically without model calls, execution or invented PnL.

## FACTS

- P11 generated 20 completed reviews as 40 append-only revisions.
- Corpus coverage is BTCUSDT/ETHUSDT and micro/scalp horizons, 10 completed reviews per symbol and per horizon.
- Production ledger now has 42 valid raw rows, 21 latest completed reviews and 0 unresolved reviews.
- P11 realized scenarios: 12 `no_clear_scenario`, 8 `data_stale_or_missing`.
- Index rebuild is valid, source-hashed and contains per-symbol/per-horizon statistics.
- Current offline packet projection is 4,170/4,400 tokens with one newest compact memory row.
- Aurora main was not running and was not started/restarted, honoring the operator constraint.

## INFERENCES

- The corpus is now large enough for baseline retrieval/filter testing, but not for predictive conclusions.
- Two realized scenario classes reflect the available archived packet evidence; manufacturing four classes would be misleading.

## ASSUMPTIONS

- Archived P9 packets are valid fresh direct-publication observations; P10 packets are valid stale-publication observations.
- Reusing a packet pair across two symbols and two horizons is acceptable because each review has a distinct deterministic rule scope.

## UNKNOWNS

- Fresh current-market scenario distribution is unknown until an operator starts Aurora no-order runtime.
- Directional and volatility scenario frequency remains unobserved.

## Root cause versus symptom

The root issue was insufficient completed packet-linked reviews. Thin calibration and sparse queries were symptoms, not a reason to add AgentIntent.

## Implementation summary

Added packet observation loading, fixed scenario heuristics, deterministic PreAction/Outcome revision generation, idempotent corpus tooling, multi-symbol/horizon tests and budget-safe newest-memory packet selection.

## Fresh runtime observation

Blocked by the operator instruction not to start/restart Aurora. No system process or reserved port was touched. Twenty archived packet observations were used instead: ten P9 fresh and ten P10 stale.

## Corpus generation policy

Each review uses only two linked packets, fixed thresholds, OBSERVE/WAIT/NO_ACTION, taxonomy labels, no-model identity, `submitted=false` and `no_trade_pnl_claim=true`. Re-running the tool appends zero duplicates.

## ActionReview corpus results

20 completed reviews were added: BTC=10, ETH=10; micro=10, scalp=10. Together with P9, the index has BTC=11, ETH=10 and includes the original next-packet horizon.

## Scenario distribution

Generated corpus: no-clear=12, stale/missing=8. Total index: no-clear=13, stale/missing=8. Continuation and volatility labels appear as expectations but were never falsely marked realized.

## Memory index rebuild result

Build completed in 12.8 ms. Index: 21 reviews, 21 completed, 0 unresolved, 42 valid raw rows, 0 invalid, ledger 126,542 bytes, archival not yet recommended.

## Query validation

Latest, completed, unresolved, accuracy, confusion, lessons and packet lookup remain valid. Three query sample types are included; measured queries took 13.5–14.3 ms.

## Packet budget result

Two per-symbol memory rows left only 63 tokens, so P11 deliberately retained one newest compact row and kept per-symbol lessons on GET summary/index. Current packet is 16,677 bytes, 4,170 tokens, no truncation, 230-token headroom.

## Cockpit display result

Cockpit source was unchanged. Existing parser compatibility is test-proven; no P11 live Cockpit process was started because Aurora main was unavailable.

## No-execution guard results

Static scans found zero provider, secret, signed endpoint or order/create/place/cancel/modify/amend clients. All 20 outcomes assert no PnL claim and all execution notes remain unsubmitted.

## Latency profile

Index rebuild: 12.8 ms. Memory queries: 13.5–14.3 ms. Corpus tooling completes in about one second on the current bounded ledger.

## Files changed

See `FILES_CHANGED.md`.

## Tests and validation

35 focused Python tests and 3/3 Cockpit AgentFeed tests pass. The 40-row corpus, index, three query results and 20 archived packet samples validate.

## What is proven

- Deterministic idempotent generation of 20 completed packet-linked reviews.
- Multi-symbol/multi-horizon index and descriptive matrix rebuild.
- Packet budget protection and absence of execution/model authority.

## What remains unproven

- Fresh P11 active-Aurora observation and Cockpit persistence.
- Four naturally realized scenario classes.
- Predictive quality, trading edge or PnL.

## Risks

- Archived stale observations account for 8 reviews.
- Sample size is still below the index warning threshold of 30 completed reviews.
- Packet headroom remains limited to about 230 tokens.

## P12 recommendation

Operator-start Aurora in no-order mode, collect current packet windows, and append only naturally realized directional/volatility scenarios. Do not add model or execution authority.

## Final verdict

P11_MEMORY_CORPUS_VALIDATED_RUNTIME_FRESHNESS_PARTIAL
