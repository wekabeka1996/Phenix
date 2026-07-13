# Authority And Sizing

## FACTS
- Authority validation uses the canonical session/participant/symbol/lease store.
- Lease version, context manifest, and instruction version are matched explicitly.
- Quantity comes only from `PositionQueriesSizingAdapterV2` over explicit account/market snapshots.
- Exposure is an injected pure preview and cannot reserve exposure.
- Full `AgentTradeIntentV2Processor` is not used because its accepted path emits a command.

## RESIDUAL
- Production exposure-preview composition is not yet wired.
