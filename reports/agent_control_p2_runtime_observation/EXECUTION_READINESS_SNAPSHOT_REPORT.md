# ExecutionReadinessSnapshotV0 report

P2 added `ExecutionReadinessSnapshotV0`, exposed at:

- `GET /agent-feed/v0/execution-readiness?symbols=BTCUSDT,ETHUSDT`;
- `AgentFeedPacket.execution_body.readiness_snapshot`.

Each invariant includes status, evidence source, observation timestamp, detail, and opaque raw ref. The inspector reads a strict allowlist only. It never reads adapter credentials, calls filter refresh, reconciles state, invokes an executor, dispatches, or submits an order.

Clear runtime owners in `ExecPosFSM` were assigned for mode flags/adapter presence, idempotency helper/order index, startup truth/lifecycle state, bracket ownership, and correlation identity. An attached runtime filter cache would own exchange-filter and precision evidence. Reduce-only has a runtime `CloseExecutor` owner but no explicit read-only capability flag, so it is at most degraded when the owner is present.

Observed standalone-host result:

- `runtime_available=false`;
- mode/testnet visibility: missing;
- exchange filters: missing;
- precision/minimums: missing;
- reduce-only support visibility: missing;
- idempotency visibility: missing;
- lifecycle reconciliation: missing;
- bracket ownership: missing;
- trace/correlation runtime identity: missing;
- secret isolation of this inspector: ready, because secret-bearing attributes are excluded by construction.

This does not claim execution readiness. It proves the API process does not own initialized `ExecPosFSM` state. The exact remaining seam is runtime-to-read-host publication or co-location; starting the full trading runtime merely to populate diagnostics was rejected because it could widen into active strategy/exchange behavior.
