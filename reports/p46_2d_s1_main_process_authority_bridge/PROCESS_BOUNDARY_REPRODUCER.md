# Process Boundary Reproducer

## FACTS

Before repair, a real `TradingSessionAuthorityStore` existed in main PID `49352`, while a separate FastAPI pytest process returned typed `503 DRY_RUN_AUTHORITY_UNAVAILABLE` with no local authority and no fixture fallback.

```yaml
same_process: false
main_authority_present: true
fastapi_local_authority_present: false
fixture_fallback: false
exact_failure_surface: FastAPI proposal dry-run service lookup
```

No network venue, FSM, adapter, or provider call occurred.
