# AURORA_AGENT_CONTROL_P3_RUNTIME_PUBLICATION_SEAM_AND_FRESH_SNAPSHOT_PROOF

## Problem framing

P2 proved transport but exposed a source-ownership defect: the read host had no compact current runtime market/features or execution diagnostics. Stale/missing cards were symptoms. P3's root task was an immutable Aurora-internal publication seam, not more log scanning or execution authority.

## FACTS

- Aurora main continuously produced a fresh, main-owned feature mirror.
- Active main processes predated P3 code and no repository-owned no-order restart mode exists.
- P3 did not restart main; therefore the direct event-bus publisher is wired but not live-activated in those existing processes.
- A safe bounded relay published the same atomic schemas from the main-owned mirror.
- Ten Cockpit→read-host polls succeeded and persisted.
- BTC/ETH market and feature cards became fresh runtime publications.
- Live ExecPos readiness remained unavailable to the relay.

## INFERENCES

- Atomic publication resolves the market source-ownership and latency defects without changing Cockpit.
- Fresh diagnostic publication does not imply execution readiness.
- Direct main publication requires a future controlled restart; performing it now would violate the no-order guarantee.

## ASSUMPTIONS

- The existing `FeatureMirrorWriter` output is runtime-owned truth suitable as a temporary safe relay source because it is written by Aurora main from feature/regime events.
- Fifteen minutes remains the P1 market freshness corridor.
- A publication-only relay is preferable to restarting a hybrid execution runtime without a disarm mechanism.

## UNKNOWNS

- Direct `aurora_main_event_bus` publication is not live-observed yet.
- Runtime-owned exchange filters, precision, reduce-only, idempotency, lifecycle, bracket, and correlation readiness are not available through the relay.
- Rendered DOM refresh and natural source-log rotation remain unobserved.

## Root cause vs symptom

The missing cross-process publication seam was the root cause. Stale regimes, absent prices/features, long packet latency, and missing readiness were downstream symptoms. P3 fixes market publication and explicitly contains the remaining execution gap.

## Implementation summary

Added schema-backed compact publications, an atomic store, main event listeners, readiness heartbeat, a safe bounded relay, publication-first reducer priority, explicit source ownership, phase timing, focused tests, and runtime evidence. Cockpit code and all action/execution paths remain unchanged.

## Publication seam behavior

Writers atomically replace three fixed files under `ops/agent_bridge/runtime`; readers enforce fixed names, size caps, and schemas. Cockpit never reads the directory. Invalid/missing publication falls through to safe runtime object, bounded disk, then explicit missing.

## Market snapshot results

BTCUSDT and ETHUSDT prices, regimes, and compact features were published and consumed as fresh runtime publication. Every observed packet reported `fresh=8, stale=0, missing=0`.

## Execution readiness results

The readiness file is current and schema-valid, but its owner is `publication_relay_no_runtime`; eight runtime invariants remain missing and publisher secret isolation is ready. P3 does not claim execution readiness.

## Source ownership comparison versus P2

P2 market/regime came from stale bounded decisions and features were missing. P3 symbol/features come from runtime publication. Position and warnings remain bounded fallbacks. See `SOURCE_OWNERSHIP_COMPARISON.md`.

## Runtime observation results

Ten of ten GET polls succeeded. SQLite grew from 10 to 20 rows. Packets stayed below budget without truncation. Cockpit remained disarmed/stopped. No write route or order was used.

## Latency profile summary

Round trip fell from P2's 2.1–2.4 seconds to 14–48 ms. Reducer mean was 9.94 ms; decision tail at 5.96 ms was dominant. See `LATENCY_PROFILE.md`.

## UI refresh result

The production route and ten changing backing payloads are proven. Browser discovery returned no available surface, so rendered DOM refresh is not claimed.

## Rotation/tail result

Bounded EOF reading and atomic replace were live-observed with no temp residue. Natural source JSONL rotation was `not_observed`.

## Files changed

See `FILES_CHANGED.md`.

## Tests and validation

Focused Python tests pass; final Python/Cockpit/artifact checks are recorded in `TEST_RESULTS.md`. Runtime publications and ten packets validate against their schemas.

## What is proven

- Small atomic cross-process market publication works.
- Fresh BTC/ETH prices/regimes/features reach Cockpit over existing GET-only HTTP.
- Source ownership and fallback are explicit.
- Packet latency and missingness improved materially.
- Persistence, budgets, disabled actions, and no-order safety remain intact.

## What remains unproven

- Direct publisher activation inside a restarted main process.
- Live runtime execution-readiness evidence.
- Rendered DOM refresh and natural log rollover.

## Risks

- Relay truth is one publication hop behind the main event bus.
- Market freshness can expire if the mirror stops; cards will become stale visibly.
- Direct main wiring must not be activated through an unsafe restart.
- Concurrent publishers require operator ownership discipline despite atomic contention retry.

## P4 recommendation

Activate direct publication only during a safe operator restart, add a no-order observation composition and runtime-owned readiness capabilities, and optimize the decision tail. See `P4_RECOMMENDATION.md`.

## Final verdict

P3_RUNTIME_PUBLICATION_VALIDATED_WITH_PARTIAL_READINESS
