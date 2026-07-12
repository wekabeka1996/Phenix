# Existing Authority Inventory

## FACTS

| Surface | Location | Runtime/storage | Classification |
|---|---|---|---|
| Chat session store | `tools/deepseek-terminal-agent/.../sessions/store.py` | disk-backed Cockpit chat | not execution authority |
| P41 coordination policy | `coordination_config.py` | YAML model, terminal runtime | reusable policy evidence only |
| P41 `SymbolLease` | `collective_memory_models.py` | collective evidence snapshot | memory evidence, not authority |
| V2 provider seam | `agent_trade_intent_v2.py` | Aurora main process | reused |
| Position sizing | `PositionQueries` | Aurora decision-making | reused unchanged |
| V1/V2 IPC bridge | `main_bridge.py` | process-safe ingress | reused |

Decision: `EXISTING_AUTHORITY_REQUIRES_NARROW_ADAPTER`.

## INFERENCES

- Reusing a memory snapshot as lease authority would have created competing truth.

## ASSUMPTIONS

- Single-process ownership is sufficient for this package.

## UNKNOWNS

- Historical P41 leases are not migrated into runtime authority.
