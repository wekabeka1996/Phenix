# Tech Debt Delta

We mapped blockades/debt resolved or carried over:

- **Action Auditor Safety Invariants**: `RETIRED` (FSM guards and `verify_handoff_safety` are fully unit tested and verify all invariants).
- **Runtime Handoff Wiring**: `MITIGATED` (Connected to FSM gateway; verified via mock tests in `p39e`).
- **Exchange Adapter Mock Validation**: `DEFERRED_WITH_REASON` (Simulated exchange validations are deferred because real testnet responses are required to verify raw client parsing).
