# Crash Matrix

| Scenario | Baseline | Final |
|---|---|---|
| Two spawn writers | pass | pass |
| Death after evidence append | injection boundary unproven | replay pass |
| Death while holding lock | pass | pass |
| Partial final JSONL line | failed; poisoned next append | quarantined and repaired |
| Duplicate idempotency after restart | pass | pass |
| Collective version conflict | pass | pass |
| Lease expires during turn | pass | pass, fail closed |
| Checkpoint interrupted before publish | pass | previous checkpoint retained |
| Events after checkpoint | pass | replay pass |
| Pending dispatch-in-doubt | pass | blocked without reconciliation |
| Reconciliation: not submitted | failed durable transition | retry-safe transition persisted |
| Reconciliation: externally submitted | failed durable transition | sourced transition persisted |
| Injectable disk-write failure | injector absent | recovery/dedupe pass |
| Instruction update during checkpoint | Windows lock race failure | waits, then replay pass |
| Peer cursor after crash | injection boundary unproven | replay pass |

Unrecoverable ambiguity test: an `externally_submitted` claim without source references is normalized to `ambiguous`; command state stays `dispatch_started` and collective recovery is `blocked`.
