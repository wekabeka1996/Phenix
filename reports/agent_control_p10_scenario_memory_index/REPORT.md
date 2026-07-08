# AURORA_AGENT_CONTROL_P10_SCENARIO_MEMORY_QUERY_INDEX_AND_RETENTION

## Problem framing

P9 produced an append-only ActionReview ledger, but not a compact retrieval surface. P10 adds deterministic indexing, queries, retention accounting and bounded packet memory without model or execution authority.

## FACTS

- The production ledger contains 2 valid raw revisions and 1 latest completed BTCUSDT review.
- `ScenarioMemoryIndexV0` is 2,224 bytes, indexes only revision 2, and retains both raw rows unchanged.
- Four GET-only memory endpoints expose health, index, filtered queries and token-bounded summaries.
- Required latest/completed/unresolved/accuracy/confusion/lesson/packet queries are implemented.
- Ten Cockpit packet polls succeeded; SQLite rows increased 86 → 96.
- Packets used 4,168 of 4,400 estimated tokens with no truncation.
- Aurora main was not running and was not started or restarted, per operator instruction.

## INFERENCES

- The index is usable now, but one completed review is insufficient for calibration conclusions.
- Current packet freshness is stale because only persisted runtime publications were available; this is not a Scenario Memory defect.

## ASSUMPTIONS

- Latest valid revision is the canonical query row for each `review_id`.
- A completed review has an `outcome_review`; unresolved also includes `future_review_needed=true`.

## UNKNOWNS

- Fresh no-order behavior with Aurora main active remains unobserved in P10.
- Statistical stability across symbols and horizons is unknown with n=1.

## Root cause versus symptom

The root cause was absence of an index/query owner. Manual ledger inspection and packet bloat risk were symptoms.

## Implementation summary

Added typed index/query/summary/retention/calibration models, latest-revision parsing, invalid-row exclusion, SHA-256 source identity, atomic index persistence, local CLI, four GET routes and conservative packet refs/counts/lesson projection.

## Scenario-memory index design

The index reads but never modifies the ledger. It stores latest valid revisions, compact symbol lessons, scenario counts, expected-realized matrix, descriptive calibration, retention status and validation errors.

## Query API behavior

`latest`, `completed`, `unresolved`, `scenario_accuracy`, `confusion`, `lessons` and `packet` query types support bounded symbol/horizon/scenario filters. Missing ledger and invalid parameters return visible HTTP errors.

## Retention policy

All raw rows remain append-only. Invalid rows are excluded and counted. No deletion occurred. Archival becomes recommended at 3 MiB or 10,000 raw rows and must remain additive/report-backed.

## Calibration statistics

Completed=1; unresolved=0; expected labels=3; realized labels=1; expected-realized=1; unexpected=0; no-clear=1. `sample_size_warning=true`; statistics are descriptive only.

## Packet integration result

Packet memory adds the index ref and unresolved counts by requested symbol while retaining one short latest lesson/ref. Full index, matrix and reviews stay out of AgentFeedPacket.

## Cockpit display result

Cockpit source was unchanged. Its existing read-only ActionReview display accepted the additive packet fields; actions remained disabled.

## No-execution guard results

Static and runtime scans found no model providers, secret fields, signed endpoints, order/create/place/cancel/modify/amend clients or non-GET memory routes.

## Runtime observation results

Read host 18080 and Cockpit 18081 validated the new code without starting Aurora. Memory GETs succeeded; 10/10 stale-publication packet polls persisted. This does not satisfy fresh no-order-main observation and is recorded as a blocker rather than hidden.

## Latency and token budget

Memory GET latency was 2–70 ms. Cockpit packet latency was 24–42 ms, mean 32.6 ms. Packet size was 16,669–16,672 bytes and 4,168 tokens.

## Files changed

See `FILES_CHANGED.md`.

## Tests and validation

Changed modules compile; 38 focused Python tests and 3/3 Cockpit AgentFeed tests pass. All required samples validate against Pydantic contracts.

## What is proven

- Deterministic latest-revision indexing and all required query classes.
- Retention accounting, invalid-row exclusion and bounded summaries.
- GET-only operation, packet compatibility and no execution/model surface.

## What remains unproven

- Fresh active-Aurora no-order runtime observation.
- Calibration usefulness beyond the single completed review.

## Risks

- Packet headroom is only 232 tokens in the observed composition.
- A growing ledger requires scheduled index rebuilds and later archival policy.

## P11 recommendation

Collect more completed reviews across symbols/horizons and rebuild the index deterministically. Do not add embeddings, model summarization or execution authority.

## Final verdict

P10_PARTIAL_NEEDS_MORE_COMPLETED_REVIEWS
