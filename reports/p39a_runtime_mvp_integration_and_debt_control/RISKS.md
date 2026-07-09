# Risks and Mitigations

We evaluated the combined P39 runtime surface for active execution hazards.

## Risk Assessment
1.  **Accidental Order Execution**:
    - Risk: If safety guards are bypassed, agent decisions could call adapter methods and place testnet orders.
    - Mitigation: The hardened `AgentActionAudit` intercepts all incoming agent command payloads and enforces `no_order_observation_mode = True`, logging action drops.
2.  **State Mismatches on Manifest Hot-reload**:
    - Risk: If instructions are hot-reloaded during active session, session context could experience drift.
    - Mitigation: Validation check checks hashes on preflight loop before applying changes.
