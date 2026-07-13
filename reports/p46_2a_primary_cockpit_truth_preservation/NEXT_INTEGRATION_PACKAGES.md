# Next Integration Packages

## FACTS

1. **P46-2B Cockpit baseline review:** review the preserved 14-file package, isolate V1/EZE action surfaces, and define explicit runtime/cache configuration.
2. **P46-2C bounded context and memory projection:** expose Phenix source-bound context, canonical memory summaries, carryover, checkpoints, and instruction/context versions as read APIs.
3. **P46-2D session and lease presentation:** add typed Cockpit clients/views for canonical TradingSession, participant, lease, and freshness state.
4. **P46-2E V2 action client:** implement no-sizing `AgentTradeIntentV2`, remove/disable model-provided qty paths, and preserve one canonical ingress.
5. **P46-2F lifecycle/reconciliation projection:** render FSM/adapter/venue truth without local SQLite authority.
6. **P46-2G token ledger:** unify provider usage receipts and parent/subagent attribution while keeping estimates labelled.
7. **P46-2H runtime proof:** deterministic integration first; separately authorized Testnet proof only afterward.

## INFERENCES

This order removes authority ambiguity before enabling write controls.

## ASSUMPTIONS

The remote preservation branch becomes the review input for P46-2B.

## UNKNOWNS

API version naming and migration windows require coordinator approval.
