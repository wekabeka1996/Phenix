# AURORA_AGENT_CONTROL_P4_NO_ORDER_RUNTIME_PUBLICATION_AND_READINESS_ACTIVATION

## Problem framing

P3 proved atomic relay publication but could not safely restart the hybrid-capable main runtime. The P4 root problem was missing execution-authority isolation at process composition; relay ownership and missing readiness were symptoms.

## FACTS

- `AURORA_RUNTIME_PROFILE=agent_bridge_observation_only` is a typed, fail-closed process profile.
- In that profile `ExecPosFSM` is composed with `shadow_mode=true`, `is_live_execution=false`, `adapter=None`, and no trade-intent/external-open/external-close/external-amend/position-policy-close listeners.
- Direct publisher `p4.v0` is active in Aurora PID 9092/7472 and owns market, readiness, and index publications.
- BTCUSDT and ETHUSDT 300s market/features are fresh and owned by `direct_main_publication`.
- Ten Cockpit polls succeeded; SQLite rows changed 20 to 30.
- Final-attempt runtime logs contained 394 HTTP requests, all GET. No order/create/place/cancel/modify signature was observed.
- Before each of three controlled launches, only `ops/wal/*.json` was targeted; zero matching files existed or were deleted.

## INFERENCES

- Omitting consequential listeners plus an absent adapter removes the reachable exchange-action path; method-level guards provide a second fail-closed boundary.
- Fresh card metadata proves current diagnostics, not trading authority or complete execution readiness.

## ASSUMPTIONS

- Existing public/authenticated GET telemetry is observational and does not create, cancel, or modify orders.
- Log absence is evidence for this bounded window, not a universal proof about future unrelated code changes.

## UNKNOWNS

- Exchange filter and precision/minimum readiness remain missing because no execution-owned filter cache exists in the no-order runtime.
- Reduce-only capability remains degraded because the owner exposes no explicit read-only capability flag.
- Rendered DOM was not observed because no in-app browser surface was available.

## Root cause versus symptom

The root cause was an execution-capable composition being the only way to activate the main publisher. P4 adds an explicit observation composition. P3 relay ownership, absent runtime readiness, and high decision-tail cost were downstream effects.

## No-order mode implementation summary

The launch profile is resolved before execution adapter construction. Unknown or empty explicit values fail. Authenticated startup filter validation, snapshot restore, and WAL replay are skipped. Execution adapter initialization and consequential listeners are unreachable, while market/features/regime and read-only publication remain active. Startup telemetry states the active profile.

## Direct publication behavior

The main event bus publishes atomic `p4.v0` market, readiness, and heartbeat/index files. Canonical 300s rows are retained before extra timeframes. Reducer ownership distinguishes direct main, relay, fallback, and missing.

## Execution readiness results

Ready: mode/no-order isolation, duplicate/idempotency owners, lifecycle owner, bracket owner, trace identity, and secret-isolated inspection. Missing: exchange filters and precision/minimum constraints. Degraded: reduce-only capability visibility. This is diagnostic readiness, not authority.

## Source ownership comparison P2/P3/P4

P2 used stale/missing bounded fallbacks. P3 used a fresh publication relay without execution runtime. P4 uses fresh direct-main market/features and direct execution-owner diagnostics. Position and warning cards remain bounded observational sources.

## Runtime observation results

Ten of ten GET polls returned 200 for BTCUSDT/ETHUSDT. Each packet had `fresh=8, stale=0, missing=0, unknown=0`; both market and feature cards reported `direct_main_publication`. Packet size was 11,293-11,295 bytes and 2,824 estimated tokens. No consequential Cockpit route was called and actions stayed disabled.

## Latency profile

Round trip was 9-40 ms, mean 19 ms. Card construction averaged 5.227 ms. The direct-current decision phase averaged 0.767 ms versus P3's 5.962 ms because the bounded decision tail is skipped while order-log warning visibility remains.

## UI refresh result

Cockpit lint, build, component contract, GET API, persistence, and `/economics` HTTP 200 were proven. The six-card component and disabled action constant were verified. Rendered DOM refresh is unproven because browser discovery returned no available in-app browser.

## Atomic publication result

Forty additional read-host polls crossed a natural market publication update from 12:06 to 12:09: 40/40 returned schema-valid direct ownership, failures were zero, and temporary residue was zero.

## Files changed

See `FILES_CHANGED.md`.

## Tests and validation

Focused startup/publication/API tests, compile, Cockpit lint/build/tests, schema validation, secret-field scan, and artifact validation passed. See `TEST_RESULTS.md`.

## What is proven

- Repository-owned no-order main activation.
- Direct main market/features/regime publication and current heartbeat.
- Runtime-owned partial mechanical readiness.
- GET-only Cockpit consumption, persistence, packet budget, and disabled actions.
- No observed exchange order/cancel/modify command.

## What remains unproven

- Complete exchange filter/precision and explicit reduce-only readiness.
- Rendered browser DOM.
- Any agent authority or execution capability.

## Risks

- The broader observation runtime still performs existing GET-only market/account reads; it is not a minimal standalone market-only process.
- Ownership selection depends on fixed publication schemas and configured symbol priority.
- Runtime logs prove only the bounded observation window.

## P5 recommendation

Add read-only execution-owner capability descriptors for filter constraints and reduce-only support. Do not add AgentIntent or any order gateway in that package.

## Final verdict

P4_NO_ORDER_DIRECT_PUBLICATION_VALIDATED_PARTIAL_READINESS
