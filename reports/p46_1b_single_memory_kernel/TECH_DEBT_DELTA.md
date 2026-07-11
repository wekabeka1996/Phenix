# Tech Debt Delta

## FACTS

| Debt | Classification | Delta |
|---|---|---|
| Implicit memory filesystem root | RETIRED | canonical constructor requires an absolute root |
| Implicit/default agent identity | RETIRED | identity must match configured agent id/number |
| Silent overwrite of authoritative history | RETIRED | canonical records are append-only with duplicate rejection |
| Persisted summary as alternate truth | RETIRED | summary/carryover are read models only |
| Competing legacy runtime writer | DEFERRED_WITH_REASON | dashboard/harness cutover is outside this focused port; no dual-write added |
| Historical artifact migration | DEFERRED_WITH_REASON | requires explicit provenance/idempotency package |
| Whole P41X/P41Y execution-coupled import | REJECTED_UNSAFE | would couple memory to FSM/dispatch/dashboard surfaces |
| Multiprocess writer proof | REMAINS_UNPROVEN | not part of focused unit validation |

## INFERENCES

- The patch reduces new-memory ambiguity without concealing remaining legacy runtime debt.

## ASSUMPTIONS

- Coordinator schedules migration before declaring canonical runtime completion.

## UNKNOWNS

- Exact retirement release for legacy files is not assigned.

