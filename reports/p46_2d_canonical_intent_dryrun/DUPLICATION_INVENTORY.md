# Duplication Inventory

## FACTS
- `agent_intent_dry_run.py` is a legacy AgentIntentV0 classification ledger, not V2 authority/sizing preview; retained unchanged.
- `AgentTradeIntentV2Processor.process()` emits a downstream command on acceptance and is deliberately not called.
- Canonical P46-2D reuses `AgentTradeIntentV2`, `TradingSessionAuthorityStore`, and `PositionQueriesSizingAdapterV2` through read-only seams.
- Existing Cockpit approval/store surfaces are reused; no second database or approval system was introduced.
