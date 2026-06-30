# P4 recommendation

Keep P4 read-only and narrow:

1. During the next operator-approved main restart, follow the operator rule to delete only `ops/wal/*.json` immediately before restart, then validate direct `aurora_main_event_bus` publication.
2. Provide an explicit repository-owned no-order observation composition before attempting live ExecPos readiness proof.
3. Publish a compact atomic recent-decision view to remove the measured 5.96 ms dominant reducer tail.
4. Attach runtime-owned exchange filter evidence and an explicit CloseExecutor reduce-only capability diagnostic; do not infer either from config.
5. Repeat rendered UI verification when the in-app browser is available and observe a natural source-log rollover.

Do not add AgentIntent, dry-run execution, action review, order routing, testnet orders, policy disabling, council, ranking/reputation, auto-loop, or provider arbitration.
