# Execution readiness runtime report

Source owner: `aurora_main_execution_position`. Runtime available: true.

| Invariant | Status | Runtime evidence |
|---|---|---|
| testnet/no-order mode | ready | no-order=true, shadow=true, live=false, adapter absent |
| no-order execution isolation | ready | consequential listeners omitted, blocked action counter present |
| exchange filters | missing | no runtime filter cache |
| precision/minimum constraints | missing | no runtime filter snapshots |
| reduce-only close/protect | degraded | CloseExecutor exists; no explicit read-only capability flag |
| duplicate/idempotency | ready | idempotent helper and order index present |
| lifecycle reconciliation | ready | startup truth owner and managed-flow map present |
| bracket ownership | ready | bracket owner and maps present |
| trace/correlation | ready | correlation store and bounded trace present |
| secret isolation | ready | allowlisted inspector does not inspect credential attributes |

`ready` here is runtime-owned diagnostic evidence only. It grants no order authority.
