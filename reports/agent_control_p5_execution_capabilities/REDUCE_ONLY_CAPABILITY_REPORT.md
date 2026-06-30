# Reduce-only capability report

| Capability | Status | Evidence owner |
|---|---|---|
| reduce-only request parameter | ready/runtime_owner | `BracketOrderPayload.reduce_only` |
| close-path enforcement | ready/runtime_owner | `CloseExecutor._submit_close_order` |
| protect-path enforcement | ready/runtime_owner | `BracketManager.place_brackets_parallel` |

The descriptor builder checks typed fields and callable ownership only. It never invokes these methods. `exchange_acceptance_confirmed=false` is explicit on every descriptor.
