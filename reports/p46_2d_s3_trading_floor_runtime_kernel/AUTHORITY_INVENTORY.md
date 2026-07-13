# Authority Inventory

## FACTS

| Surface | Production construction/writer | Process | Identity/version | Classification |
|---|---|---|---|---|
| FSM/execution | `apps/reference/main.py` | main | event/command IDs | canonical execution owner |
| Session authority | `main.py:966` constructs empty `TradingSessionAuthorityStore` | main | session/participant/lease IDs | candidate; unseeded |
| Canonical memory | dashboard `_get_canonical_memory_runtime()` | terminal-agent | session, agent, sequence, record ID | active P46-1C writer |
| Lifecycle harness memory | `agent_order_lifecycle_harness.py` | terminal-agent harness | same canonical model | explicit second consumer, not production-main owner |
| Context manifest | no complete production constructor | none proven | required version absent | unavailable |
| Account snapshot | `DecisionMaking.latest_portfolio` cache | main | `latest_portfolio_ref` read but no writer found | anonymous/incomplete |
| Market snapshot | `DecisionMaking.symbol_states` | main | optional `snapshot_ref` | conditional/incomplete |
| Lifecycle/reconciliation | FSM caches, inflight reconciliation, telemetry | main | fragmented | no bounded canonical projection |
| Exposure evaluation | `ExposureGuard.can_open()` | main | config-dependent | reusable non-reserving seam |
| Query service | class exists; no main construction | none | runtime generation | transport contract only |

Code and tests exist for all major contracts except a production composition root. Production runtime proof exists only for the already validated S1 transport, not for the proposed kernel.

## INFERENCES

Main is the natural future owner, but memory ownership cannot be inferred from execution ownership.

## ASSUMPTIONS

No external untracked service supplies the missing ownership contract.

## UNKNOWNS

Deployment-time process topology outside repository evidence.
