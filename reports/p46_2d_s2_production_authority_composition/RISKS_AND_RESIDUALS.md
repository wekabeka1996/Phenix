# Risks and Residuals

1. Context authority ownership across terminal-agent and Aurora main is unresolved.
2. Production TradingSession authority is constructed but not populated by an approved runtime API.
3. Lifecycle truth is spread across FSM, reconciliation, and logs without one bounded read model.
4. Account snapshot identity is absent even when portfolio content exists.
5. Exposure preview parity remains unproven until identical identity-bearing snapshots feed live and dry-run paths.
6. Full Cockpit approval and canonical context invalidation remain unproven.

Minimal next dependency package: select the context owner, add a read-only versioned projection API, publish session and snapshot identities through legitimate main runtime APIs, and add a synchronized lifecycle snapshot. Only then compose S1 query service.
