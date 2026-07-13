# Runtime Composition

## FACTS
- `apps/reference/main.py` constructs `TradingSessionAuthorityStore` in the main execution process.
- Standalone `shadow_telemetry.main` constructs FastAPI without that store and without canonical context/lifecycle readers.
- Existing AgentBridge atomic publications contain market/readiness projections, not TradingSession authority or canonical memory manifest.
- Uncomposed read-model/dry-run routes return typed `503`; there is no fixture fallback and startup constructs no adapter.

## UNKNOWNS
- No approved process-safe authority/context projection currently closes this gap.

## Decision
Production composition is blocked rather than inferred from logs, reports, or duplicated state.
