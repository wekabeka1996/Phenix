# Dispatch-In-Doubt Reconciliation

P41Y persists `DISPATCH_RECONCILED` as a critical event.

| Result | State transition | Recovery |
|---|---|---|
| `not_submitted` | `dispatch_started` → `not_dispatched`, status remains `pending_fsm` | ready for explicit retry |
| `externally_submitted` with source refs | → `fsm_accepted`, refs retained | ready; duplicate dispatch suppressed |
| `ambiguous` or invalid result | no command transition | blocked |
| no reconciliation hook | no command transition | blocked |

Recovery never calls the FSM gateway and never automatically retries. A later explicit dispatch is deduplicated for external/ambiguous states. The test reconciliation results are synthetic; they are not exchange proof.
