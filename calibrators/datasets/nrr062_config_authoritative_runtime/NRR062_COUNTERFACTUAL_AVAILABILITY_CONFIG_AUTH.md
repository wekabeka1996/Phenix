# NRR062_COUNTERFACTUAL_AVAILABILITY_AUDIT

| Class | Count | Meaning |
| --- | --- | --- |
| COUNTERFACTUAL_AVAILABLE | 0 | causal future-path and identity surface both present |
| MARKET_PATH_AVAILABLE_ONLY | 227 | market bars only, no realized/joined outcome |
| TRACE_ONLY_NO_OUTCOME | 0 | order/decision traces present without causal outcome |
| INSUFFICIENT_TIMESTAMP | 0 | reject row missing usable timestamp |
| INSUFFICIENT_IDENTITY | 0 | reject row missing usable identity join keys |

## Summary
| Metric | Value | Notes |
| --- | --- | --- |
| Reject Rows | 227 | canonical NRR062 reject cohort |
| Decision Ledger Present | 227 | rows with frozen decision ledger trace |
| Objective Present | 0 | rows with objective stack row |
| Trade Lifecycle Hit Rows | 0 | rows with explicit trade_lifecycle string hits |
| Workspace Recorder Root Present | True | presence alone does not prove causal bar join |
| Market Path Available Rows | 227 | rows with later recorder bars available by symbol/timestamp |
