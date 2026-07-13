# Production Composition Inventory

| Dependency | Construction owner | Available at query time | Missing seam |
|---|---|---:|---|
| TradingSession authority | `apps/reference/main.py` | object exists | no production session/participant/lease publisher |
| Context manifest | terminal-agent dashboard only | no | no approved main-process reader/publisher |
| Lifecycle/FSM | `ExecPosFSM` in main | partial internal state | no bounded projection with identities/reconciliation sources |
| Account snapshot | `DecisionMaking.latest_portfolio` | conditional | no published canonical snapshot reference |
| Market snapshot | `DecisionMaking.symbol_states` | conditional | no guaranteed canonical identity/freshness projection |
| Position sizing | `PositionQueries` | yes after runtime data | reusable |
| Exposure evaluation | `ExposureGuard.can_open` | yes after FSM composition | reusable pure call, no reservation |
| Runtime query service | none | no | mandatory readers unavailable |

FACT: `RuntimeAuthorityQueryService(` has no production construction call.

FACT: `CanonicalMemoryStore(` appears outside tests only in terminal-agent `dashboard/app.py`, not Aurora main.
