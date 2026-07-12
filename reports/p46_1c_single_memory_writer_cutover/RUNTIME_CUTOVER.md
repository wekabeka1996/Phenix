# Runtime Cutover

## FACTS

Runtime flow is now:

```text
accepted dashboard/harness memory action
  -> CanonicalMemoryRuntime validation and deterministic record identity
  -> CanonicalMemoryStore.append
  -> one append-only records.jsonl ledger
  -> deterministic read/summary/carryover view
```

- Dashboard identity/read/ACK/rationale/FSM/finalize routes no longer import or construct `AgentMemoryLifecycle`.
- Lifecycle harness no longer calls legacy `load_or_create`, reflection mutation, or `_write_memory`.
- Canonical append failures propagate; dashboard classifies runtime failures as HTTP 503. There is no legacy fallback.
- Duplicate lifecycle commands do not create a second memory append.
- Summary and carryover endpoints return deterministic in-memory projections and create no files.
- FSM/exchange control flow was not changed by the memory adapter.

## INFERENCES

- Runtime ownership is cut over without dual-write because only the canonical adapter exposes mutation to these paths.

## ASSUMPTIONS

- The Python dashboard and lifecycle harness are the existing terminal-agent memory-writing runtime consumers identified by repository trace.

## UNKNOWNS

- React Cockpit remains outside this package.

