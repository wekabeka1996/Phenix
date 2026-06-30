# Execution readiness before and after P5

| Invariant | P4 | P5 | Why |
|---|---|---|---|
| exchange filters | missing | degraded | complete typed constraints exist, exchange confirmation absent |
| precision/minimum | missing | ready | runtime-owned pure normalizers plus complete loaded symbol constraints |
| reduce-only close/protect | degraded | ready | explicit request, close, and protect owner evidence |
| idempotency | ready | ready | helper and order index unchanged |
| lifecycle reconciliation | ready | ready | startup truth owner unchanged |
| bracket ownership | ready | ready | bracket owner/maps unchanged |
| no-order isolation | ready | ready | shadow=true, live=false, adapter absent, listeners omitted |

P5 capability summary for BTCUSDT/ETHUSDT: ready 5, degraded 2, missing 0, unknown 0. Remaining reason: `exchange_filter_not_runtime_confirmed`.
