# P9 ActionReviewV1 ledger and scenario memory foundation

## Problem framing

Aurora had compact market/execution context and parity governance but no consistent memory unit for a proposed no-execution action, its expected scenarios, a later observation, and a reusable lesson. P9 adds that structure without calling a model or enabling execution.

## FACTS

- `ActionReviewV1` has typed PreActionNote, no-submission ExecutionNote, and optional OutcomeReview layers.
- The scenario taxonomy is fixed to eleven small identifiers.
- The production ledger is append-only JSONL, idempotent by review id/revision, guarded in-process, fsynced, and bounded.
- Later revisions must increase by one, point to the preceding row, and preserve all pre-action/execution identity fields.
- The local lint checks schema, packet refs, secret patterns, forbidden execution identity keys, summary size, token estimate, and row size.
- No model API or provider was called; model id/ref are null by contract.
- Runtime revision 1 linked to real packet `afp_06cc5f9af7a5497695dd7698abac360d` and proposed `OBSERVE` only.
- Runtime revision 2 linked outcome packet `afp_f05b356f0de04ff492f236e879549536`; BTCUSDT close remained 59,634.25 over 1,049 ms, realizing `no_clear_scenario`.
- The outcome makes `no_trade_pnl_claim=true` and records no order/fill identity.
- Ten measured Cockpit GET polls succeeded; SQLite rows increased 75 → 85.
- Packets were 16,260-16,263 bytes and 4,065-4,066 estimated tokens, below 4,400 without truncation.

## INFERENCES

- Append-only revisions preserve the distinction between what was expected and what was learned later.
- The compact packet projection is sufficient for replay orientation while full review details remain in the ledger.

## ASSUMPTIONS

- Two-packet scenario classification is only a deterministic validation fixture, not trading analysis.
- `agent-feed://packet/<id>` is the stable local linkage convention for P9.

## UNKNOWNS

- No real model decision quality, long-horizon scenario accuracy, trade PnL, or lifecycle attribution is known.
- Cross-process file locking and archival rotation remain future hardening work.

## Root cause vs symptom

The symptom was isolated context/report text with no replayable learning unit. The root cause was absence of a versioned contract connecting observation, hypothetical intent, no-execution proof, scenario expectation, later outcome, and lesson. P9 supplies that contract and ledger.

## Implementation summary

Added typed ActionReviewV1 contracts, an eleven-id scenario taxonomy, append-only revision storage, deterministic token stabilization, safety lint/CLI, bounded packet memory projection, read-only Cockpit display, comprehensive tests, and a real-packet-linked no-model runtime sample with outcome revision.

## ActionReview contract design

Top-level mode is limited to `no_execution`, `hypothetical`, or `future_model_placeholder`. Proposed actions are the seven scoped enums. Execution status is limited to explicit non-submission states, `submitted` is literally false, and extra order/fill fields are forbidden. P9 model id and model-call ref are null.

## Scenario taxonomy

The fixed ids cover continuation, reversion, fakeout, chop/fee trap, late-entry failure, breakout followthrough, volatility expansion/compression, external/news, stale/missing data, and no clear scenario. Expected ids are unique and capped at three; outcome flags must agree with whether the realized scenario was expected.

## Ledger behavior

The runtime ledger contains two valid rows under one review id. Revision 2 explicitly supersedes revision 1; immutable pre-action and execution notes cannot change. Duplicate identical rows are idempotent; conflicting duplicates, skipped revisions, or wrong supersession fail closed. Concurrent in-process append is test-proven.

## No-execution guard results

Model-call claims, `submitted=true`, order/client/fill/trade ids, incompatible hypothetical statuses, secret-looking values, and malformed packet refs are rejected. Static/runtime scans found no execution or provider surface. ActionReview is not permission.

## Sample review case

The no-model source recorded `OBSERVE`, acknowledged missing BTCUSDT filter-parity acknowledgement and absent P9 authority, and expected `no_clear_scenario`, `volatility_expansion`, or `data_stale_or_missing`. It used only packet and deterministic tool refs.

## Outcome review results

The later packet had the same BTCUSDT close, so the fixed availability/0.2% threshold labeled `no_clear_scenario` with confidence 0.75. The expected scenario realized; the lesson preserves uncertainty and explicitly forbids converting memory into execution permission. No PnL is claimed.

## Packet integration

AgentFeedPacket includes only latest review ids by symbol, compact expected/realized scenario memory, unresolved count, review refs, and ledger ref. Full reviews are never embedded. All ten runtime packets projected revision 2 and unresolved count zero.

## Cockpit display result

The seventh read-only card shows symbol, proposed action, no-execution status, expected/realized scenario, lesson, unresolved count, and review ref. No mutation controls were added and global agent actions remain disabled.

## Runtime observation results

Aurora ran `agent_bridge_observation_only`; the read host used 18080; Cockpit used 18081 and stayed `armed=false`, `status=stopped`. Ten GET polls and ledger lint passed. Cockpit did not target 7102/8443. Runtime logs contained zero order/create/place/cancel/modify/amend or signed/authenticated request matches.

## Latency and token budget

Ten measured round trips were 13-39 ms, mean 25.9 ms. P9 packets used 4,065-4,066/4,400 estimated tokens, leaving at least 334 tokens of headroom. Full pre/outcome reviews are 542 and 815 estimated tokens respectively but remain outside packets.

## Files changed

See `FILES_CHANGED.md`. Pre-existing unrelated Neocortex/runtime-forensics changes were preserved.

## Tests and validation

Changed modules compile; 59 focused Aurora tests pass. Cockpit lint/build and three focused bridge tests pass. Two runtime ledger rows and ten runtime packets validate with their typed contracts and the offline lint command.

## What is proven

ActionReviewV1 is a bounded, append-safe, revisioned, packet-linked, no-model/no-execution memory unit with scenario outcome and read-only packet/Cockpit visibility.

## What remains unproven

No model reasoning, model quality, agent readiness, execution authority, intent routing, trade outcome, PnL, or autonomous learning is proven.

## Risks

- Only in-process concurrency is guarded; multi-process writers need a separate locking design.
- Packet headroom is now 334 estimated tokens, so future packet additions should prefer refs or defer integration.
- Deterministic two-packet outcomes are structural fixtures, not statistically meaningful scenario evaluation.

## P10 recommendation

Add a read-only scenario-memory query/index with retention and calibration statistics over completed reviews. Keep model invocation, AgentIntent, execution routing, and autonomous loops out of scope until a separate authority package.

## Final verdict

P9_ACTION_REVIEW_LEDGER_VALIDATED
