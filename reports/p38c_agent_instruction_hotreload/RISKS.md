# Risks

- Live hot reload cadence is not proven until an agent loop or scheduler invokes `agent_instruction_preflight()` on a timed cycle.
- ACK records are modeled but not persisted by this package.
- Refresh event payloads are produced but not yet registered into a shared event ledger.
- Missing required files are reported fail-closed, so callers must decide whether to block action or degrade session state.
- Target agent labels are contract strings only; no registry validation exists in P38C.

## Next Package Candidates

- Persist ACKs under session state.
- Register instruction refresh events in the arena event ledger.
- Call preflight from each agent cycle and enforce ACK-before-next-action policy.
- Add dashboard/operator visibility for active manifest version and stale ACKs.
