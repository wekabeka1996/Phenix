# SIDECAR_IDENTITY_AND_CLOSE_CONTRACT_LEDGER

## Identity And Close Contract Ledger

| Field / identifier / contract surface | Owner | Scope | Stability across lifecycle | Status | Why |
| --- | --- | --- | --- | --- | --- |
| `symbol` on `CMD:CLOSE` / `DEC:CLOSE` | `execution_position` | symbol | stable | ACTIVE | executor requires symbol and selects current live exposure by symbol |
| `qty` on `CMD:CLOSE` / `DEC:CLOSE` | `execution_position` | request-specific | stable enough for partial reduce request | ACTIVE | partial reduce is supported when qty is less than current live position |
| `reason` on `CMD:CLOSE` / `DEC:CLOSE` | mixed initiator -> EP | request-specific | stable per request | ACTIVE | used for traceability, not target selection |
| `trace` on `CMD:CLOSE` / `DEC:CLOSE` | mixed initiator -> EP | request-specific | variable | ACTIVE | observability aid only |
| `retry_key` on close request | decision side | request-specific | variable | ACTIVE | used for orchestration/idempotency context, not target selection |
| `rid` | vfoundation / domain messaging | message/request | stable per message | ACTIVE | correlation and dedupe context; not an executable position selector |
| `idempotent_key` on open/intent surfaces | mixed, especially decision/open execution | request/order family | moderately stable | ACTIVE | used for idempotency, client id generation, and later observability correlation |
| `idempotent_key` as exact close target | none | supposed lifecycle target | not executable today | DECLARED-BUT-NOT-USED | present in payloads, but close executor does not use it to choose what to close |
| `clientOrderId` | exchange/order owners | individual order | stable per order | ACTIVE | used for order correlation and exit-match logic |
| `exchangeOrderId` / `orderId` | exchange/order owners | individual order | stable per order | ACTIVE | used for order correlation and cancel paths, not close target selection |
| `tradeId` | exchange fills / event handlers | individual fill | stable per fill | ACTIVE | cached for observability and closed-position correlation |
| `lifecycle_id` | execution-position observability | derived symbol-scoped correlation | partially stable, cache-derived | ACTIVE | emitted in logs/observability; not executable lifecycle truth |
| `position_id` | none proven | supposed position identity | unknown | UNPROVEN | no proven runtime contract or schema field was found |
| `entry_order_id` | `ManageFlowFSM` | local lifecycle cache | stable for first entry order | ACTIVE | local lifecycle observability and bracket matching |
| `entry_client_order_id` | `ManageFlowFSM` | local lifecycle cache | stable for first entry client order | ACTIVE | local lifecycle observability and bracket matching |
| `_closing_position` | `ManageFlowFSM` | local symbol lifecycle | stable only in-process | ACTIVE | internal close-in-progress flag; not a public contract |
| `CMD:CLOSE` verb | `execution_position` | command surface | stable current semantics | ACTIVE | means symbol-scoped close request that yields reduce-only close decision |
| `CMD:CLOSE` as close-by-order-id | none | imagined target mode | n/a | UNPROVEN | no runtime consumer was found |
| `CMD:CLOSE` as close-by-lifecycle-id | none | imagined target mode | n/a | UNPROVEN | not supported by executor or schema |
| `DEC:CLOSE` verb | `execution_position` | decision/execution surface | stable current semantics | ACTIVE | reduce-only execution decision against current symbol position |
| `DEC:CLOSE` schema | registry | contract metadata | null | ACTIVE | current official registry surface is schema-null |
| `DEC:CLOSE` exact-target contract | none | imagined target mode | n/a | DECLARED-BUT-NOT-USED | no structured target schema exists; executor still operates by symbol |
| `DEC:CANCEL_ORDER` by order id | `execution_position` | order-specific | stable | ACTIVE | cancel path does accept order identity; this does not extend to close path |
| `EXIT_MATCH_ATTEMPTED` identity payload | `ManageFlowFSM` | bracket forensic surface | stable per event | ACTIVE | helps explain whether incoming fill matched expected local exit ids |
| `EXECUTION_CLOSE_RECONCILED` `rid` | `OrderGuardian` | post-close reconcile | optional, partial | ACTIVE | useful for correlation, but emitted after close reconciliation rather than selecting target |

## Ledger Interpretation

- `ACTIVE` means the field/surface is live and materially consumed.
- `DECLARED-BUT-NOT-USED` means a field exists in payload flow or operator language but is not actually used for target selection in current runtime.
- `UNPROVEN` means no current runtime proof was found and it must not be assumed.

## Key Contract Truths

- Current executable close targeting is anchored on `symbol`, optionally `qty`.
- Current stable identifiers are mainly order correlation and observability surfaces.
- Order-specific control exists for cancel flow, not for close flow.
- Any future claim of "close exact lifecycle by ID" would require new proof or a new contract.
