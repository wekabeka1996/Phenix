# AURORA_AGENT_CONTROL_P1_MINIMAL_GET_ONLY_AGENT_FEED_BRIDGE

## Problem framing

Agents need compact, fresh trading context without reading huge logs or gaining execution authority. The root problem is the absence of a bounded, typed, observable HTTP read contract between Aurora runtime truth and Cockpit. Large JSONL files and inactive/ambiguous API surfaces are symptoms; treating shared files as the bridge would preserve the root defect.

## FACTS

- Aurora has an existing FastAPI read-model host at `apps/reference/api/main.py`.
- The current environment contains bounded-useful portfolio, decision, rejection, regime, and trace evidence; current shadow snapshots for requested symbols were unavailable.
- The critical event journal is hundreds of megabytes and cannot be scanned from byte zero on requests.
- Cockpit is a separate Node/TypeScript/React/Express workspace with SQLite persistence and a trading UI.
- Cockpit is not a Git repository in this environment.
- Ports 7102 and 8443 are not used by the implemented bridge.

## INFERENCES

- The existing FastAPI read host is the smallest justified Aurora integration seam.
- Runtime-owned snapshot objects should outrank bounded disk fallback.
- Execution-readiness fields without safe runtime evidence must remain unknown instead of being inferred from config or secrets.

## ASSUMPTIONS

- `PHENIX_CORE_API_URL` identifies the approved Aurora read-model host at deployment.
- A 15-second Cockpit polling interval is acceptable for P1 observation and does not define trading freshness.
- The byte/4 token estimator is conservative enough for transport reporting; exact provider tokenization is intentionally out of scope.

## UNKNOWNS

- Live runtime endpoint reachability and cross-process polling were not observed because the hosts were not started.
- Current runtime exchange-filter, precision, reduce-only, bracket-owner, mode, and secret-isolation readiness were not all safely exposed.
- Semantic coverage of every historical business-gate family is not proven by the bounded current window.

## Implementation summary

Implemented a typed `agent-feed/v0` contract, bounded latest-state reducer, three GET-only Aurora routes, a strict Cockpit parser/client, compact SQLite persistence, and a six-card polling surface. Token/byte caps, per-card freshness, missing fields, opaque refs, advisory warning policy, and mechanical invariant separation are explicit.

## Files changed

See `FILES_CHANGED.md`. The work is isolated to a new Aurora domain, one route-registration point, focused tests/reports, and a new Cockpit consumer surface.

## Aurora-side bridge behavior

The reducer prefers runtime state, otherwise seeks into only the bounded tail of allowed files. It emits partial cards honestly, records fallback diagnostics, and never embeds raw logs. Budget reduction is explicit; unsatisfied budgets fail visibly. Route registration adds no POST/PATCH/DELETE method.

## Cockpit-side consumer behavior

Cockpit fetches via GET, validates the full v0 envelope, rejects ports 7102/8443, persists successful packets, and renders six read-only cards. Missing/stale/error states and token/byte use are visible. The P1 action control is disabled and no dispatch call is reachable from this consumer.

## What is proven

- A bounded packet can be produced from available Aurora evidence.
- Missing market/features and degraded execution truth are explicit.
- The default packet fits below 4,400 estimated tokens.
- Aurora bridge routes are GET only and reducer tests do not invoke execution.
- Cockpit types compile, packet validation/persistence/client tests pass, forbidden ports are rejected, and P1 actions are disabled.
- The sample is valid, sanitized, and uses opaque refs.

## What is not proven

- Live multi-process polling on an operator-approved port.
- Fresh BTCUSDT/ETHUSDT snapshot availability in the current runtime.
- Completeness of all business-warning families.
- Readiness of mechanical execution invariants currently reported unknown/degraded.

## Validation results

Aurora compile and 4 focused tests pass. Cockpit typecheck passes and all 3 new bridge tests pass. The broader trading-agent suite has 38 passes and one unrelated pre-existing EZE direct-execution failure. No order or consequential route was called. Full evidence is in `TEST_RESULTS.md`.

## Risks

- Bounded tails may omit a relevant event older than the configured window; diagnostics disclose the fallback.
- File rotation is locally tolerant through newest-file selection but has not been stress-tested during simultaneous rotation.
- Polling without transport auth is suitable only on the already trusted deployment boundary.
- Existing Cockpit dependencies report npm audit findings unrelated to this bridge.

## P2 recommendation

Run a read-only operator observation window and expose a dedicated runtime execution-readiness snapshot. Do not add AgentIntent or execution in the next step. Details are in `P2_RECOMMENDATION.md`.

## Final verdict

P1_MINIMAL_BRIDGE_IMPLEMENTED_AND_VALIDATED
