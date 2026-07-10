# Duplication And Debt Delta

## RETIRED

- Hidden coordination defaults: P41X values live in one package YAML validated by strict Pydantic models.
- Unattributed shared writes: every P41X mutation receives a stable event ID, sequence, identity where applicable, and idempotency key.
- Prompt/checkpoint ambiguity: active context and durable checkpoint metrics are reported separately.

## MITIGATED

- SessionStore has no cross-process append lock; P41X uses a separate locked ledger without rewriting legacy storage.
- Legacy agent trading memory rewrites one JSON document; P41X private memory uses append-only per-agent JSONL.
- Existing event models overlap; P41X uses one kernel event envelope and leaves legacy APIs compatible.
- Shadow harness labels can resemble real ACKs; reports now classify the harness explicitly.

## CONVERTED_TO_RUNTIME_CHECK

- Stale state, lease expiry, duplicate command, dispatch-in-doubt, portfolio emergency stop, and missing reconciliation are fail-closed runtime checks.

## DEFERRED_WITH_REASON

- Legacy `agent_cadence.py` and `agent_timer_runner.py` remain for compatibility; broad consolidation is outside P41X.
- Live exchange reconciliation wiring is deferred because this task forbids raw exchange access and did not authorize Aurora runtime changes.
- Network-filesystem distributed locking is unproven; the implemented lock targets the shared local worktree runtime.
