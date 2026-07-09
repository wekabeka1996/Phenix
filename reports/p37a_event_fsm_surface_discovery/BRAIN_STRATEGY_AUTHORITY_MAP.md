# Brain and Strategy Authority Map

We mapped how strategy mode admission gates protect the FSM execution boundary.

## 1. Strategy Modes
- **disabled**: The strategy will not run.
- **shadow**: Observe-only. Evaluated for telemetry comparisons but prevented from issuing orders.
- **testnet_candidate**: Allowed to run on testnet (capped at 0.02 Kelly bounds).
- **runtime**: Full execution mode.

## 2. Financial Reachability Blockers
- **Module**: `apps/reference/domains/strategies/authority.py`
- **Method**: `financial_contract_blockers()`
- **Logic**: Compiles blockers (e.g. `AUTHORITY_MODE_SHADOW`, `Kelly cap exceeded`) to evaluate if `financially_reachable` is True.
- **Registry**: `apps/reference/domains/strategies/registry.py` registers these snapshots during startup.
