# Residuals

## FACTS

- Production V2 processor is not injected; all production V2 IPC attempts stop at `SIZING_AUTHORITY_UNAVAILABLE`.
- Canonical TradingSession/participant/main-agent/lease/context provider is absent from Aurora main composition.
- DecisionMaking portfolio and market state exist but have no reviewed freshness adapter for V2.
- Margin-first helper still contains an implicit `fee_buffer=0.001` default outside YAML/Pydantic SSOT.
- V1 remains compatibility-only and still accepts caller qty; it was not promoted or removed.
- V2 supports OPEN only.

## INFERENCES

- Next package should expose a read-only authority snapshot adapter and move fee buffer to SSOT before enabling V2 processor injection.

## ASSUMPTIONS

- V1 deprecation can occur only after V2 runtime authority is proven.

## UNKNOWNS

- Cross-process source and freshness contract for terminal session leases is undecided.

