# AURORA_AGENT_CONTROL_P2_RUNTIME_OBSERVATION_AND_EXECUTION_READINESS_SNAPSHOT

## Problem framing

P1 proved packet construction offline. P2 needed to distinguish the root runtime-boundary question from symptoms such as stale cards: does Cockpit actually obtain, validate, persist, and refresh bounded Aurora packets over approved HTTP, and can mechanical readiness be evidenced without execution authority?

The root issue was unproven cross-process observation and absent runtime-owned readiness publication. Stale/missing cards were symptoms and evidence of source ownership gaps, not transport failure.

## FACTS

- Aurora ran on `127.0.0.1:18080`; Cockpit ran on port 18081.
- Ten Cockpit→Aurora GET packet polls succeeded and produced ten unique packets.
- Cockpit persisted exactly ten validated rows.
- A deliberate Aurora outage produced visible HTTP 502 and no extra row.
- Cockpit remained disarmed and stopped.
- Fresh BTCUSDT/ETHUSDT feature snapshots were unavailable; bounded portfolio/warning/decision fallbacks were used.
- The standalone FastAPI process had no initialized `ExecPosFSM` object.
- No browser surface was available for rendered UI inspection.

## INFERENCES

- The HTTP bridge and persistence boundary work independently of shared filesystem access by Cockpit.
- Freshness classification is clock-trustworthy; source staleness is real.
- Runtime readiness cannot become ready merely by importing code or reading config. A publication/co-location seam is required.
- A 2.1-second packet path is acceptable for this bounded observation but should be profiled before tighter polling.

## ASSUMPTIONS

- Loopback on the same host is an approved P2 runtime boundary.
- Ten successful polls satisfy the specified minimum observation target.
- Secret isolation `ready` refers only to the new inspector's allowlisted behavior, not to a broader credential-security certification.

## UNKNOWNS

- Rendered six-card DOM behavior remains unobserved because the in-app browser backend was unavailable.
- Live snapshot file rollover was not observed.
- Runtime filter, precision, reduce-only, idempotency, lifecycle, bracket, mode, and correlation readiness remain unavailable in the standalone API process.
- The exact production transport for readiness publication between a separate trading process and read host is not selected.

## Runtime observation summary

Ten of ten GET polls succeeded. Packet metadata stayed within 11,629–11,632 bytes and 2,908 estimated tokens. Each packet reported three fresh, three stale, and two missing cards. Round trips ranged from 2,094 to 2,443 ms. The sample JSONL contains all ten observation envelopes.

## Host startup results

Aurora started directly with Uvicorn. Cockpit's first production attempt failed on missing `APP_URL`, then started successfully after supplying the required non-secret value. Provider profiles were not configured, but the read-only bridge did not require them. Ports 7102 and 8443 were not used.

## Polling results

Cockpit reached Aurora only through the GET packet path. Aurora access logs show ten packet GETs. A forced downstream outage returned 502 visibly and recovery health returned 200 after restart.

## Source ownership results

Portfolio and warnings were fresh bounded disk fallbacks. BTCUSDT/ETHUSDT regime evidence came from stale bounded decisions; prices and features were missing. Execution trace used bounded decision evidence while the runtime execution object was missing. No runtime-owned market snapshot was proven.

## Clock/freshness results

Direct host/client midpoint skew was +12 ms. Packet production happened near the end of the 2.1-second reducer duration and arrived 7–50 ms later. The roughly 345-million-ms oldest source age is genuine stale evidence.

## Cockpit persistence results

`agent_feed_packet_metadata` grew from 0 to 10 rows. Latest id matched the tenth packet. Malformed/over-budget payload rejection is test-proven. The live failed fetch did not change row count.

## UI refresh results

The production app built, `/economics` served, and its backing API returned ten advancing packets. The action flag remains false. Rendered DOM refresh is blocked only by the unavailable in-app browser surface and is not claimed.

## Mechanical invariant readiness results

`ExecutionReadinessSnapshotV0` was added and consumed by `ExecutionBodyCard`. It assigns explicit runtime owners and evidence fields while using a secret-safe allowlist. In the actual standalone host, eight runtime invariants were `missing`; inspector secret isolation was `ready`. No execution readiness is claimed.

## Implementation summary

P2 added one GET endpoint, one immutable readiness contract/inspector, packet integration, TypeScript typing, focused tests, reproducible host/poll scripts, and evidence reports. It did not alter execution behavior.

## Files changed

See `FILES_CHANGED.md`.

## Tests and validation

Focused Python and TypeScript checks pass. Actual health, packet, readiness, persistence, failure visibility, recovery, and production shell delivery were exercised. Final combined commands are recorded in `TEST_RESULTS.md`.

## What is proven

- Real Cockpit→Aurora GET transport on approved ports.
- Ten successful bounded polls and validated persistence.
- Visible failure without empty-packet fallback or failed-row persistence.
- Trustworthy host clock alignment.
- Explicit bounded source ownership and missingness.
- GET-only readiness inspection with no secret read or execution call.
- Cockpit remained disarmed; no order was placed.

## What remains unproven

- Fresh runtime-owned BTCUSDT/ETHUSDT feature snapshots.
- Live initialized execution readiness in the read host.
- Rendered DOM refresh.
- Live rotation across a file boundary.
- Production authentication/security posture.

## Risks

- The standalone API and trading runtime remain separate ownership domains.
- Local development security defaults are unsuitable for remote exposure.
- Packet latency is materially larger than pure loopback transport time.
- Missing filter/readiness state must not be interpreted as execution failure or readiness.

## P3 recommendation

Add only a bounded immutable runtime-readiness publication seam, fresh snapshot publication, latency profiling, and the deferred UI/rotation observations. Do not start execution authority. See `P3_RECOMMENDATION.md`.

## Final verdict

P2_RUNTIME_OBSERVATION_VALIDATED_READINESS_SNAPSHOT_ADDED
