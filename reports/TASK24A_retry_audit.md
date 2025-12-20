# TASK24A — RetryScheduler / AuroraBridge Forensic Audit (P0/P1)

Scope: `apps/reference/main.py` (RetryScheduler + AuroraBridge)

## Findings (P0)

### P0 — RetryScheduler does not own/increment `attempt` (contract gap)

- **File/line:** `apps/reference/main.py:137-195`
- **What breaks:** `register_deferred()` trusts `deferred_payload["attempt"]` and stores it as-is (`attempt = deferred_payload.get("attempt", 1)`), but **does not increment** it inside the scheduler before retry emission.
- **File/line:** `apps/reference/main.py:244-325`
- **What breaks:** `_execute_retry()` uses the stored `attempt` in logs/why and re-emits, but never increments for the next cycle; correctness relies on external producers to manage attempt.
- **Impact:** retry attempt semantics become inconsistent across producers; scheduler cannot guarantee bounded retry behavior by itself.

### P0 — Event loop contract: “no loop” silently leaves pending intents unscheduled

- **File/line:** `apps/reference/main.py:219-242`
- **What breaks:** if no running loop is available, scheduler logs an error but keeps `_pending` populated (“registered but retry NOT scheduled”).
- **Impact:** pending leak (never retried, never dropped), and system behavior depends on runtime loop availability without fail-fast.

### P0 — Direct `fsm.emit(...)` used in drop paths (bypasses emit_compat)

- **File/line:** `apps/reference/main.py:374-378` (`_drop_intent`)
- **File/line:** `apps/reference/main.py:427-446` (`clear_all_pending`)
- **What breaks:** direct `self.fsm.emit(...)` violates “emit_compat only” requirement; also bypasses consistent async safety/telemetry behaviors.

## Findings (P1)

### P1 — AuroraBridge hardcodes retry policy (`_retry_delay_sec=0.5`, `_max_retries=2`)

- **File/line:** `apps/reference/main.py:484-489`
- **What breaks:** hardcoded defaults are embedded in code despite the presence of `config.bridge.retry_scheduler`.
- **Impact:** policy drift and silent behavior changes; cannot be centrally controlled via config.

### P1 — Legacy local retry path exists alongside RetryScheduler (double policy surface)

- **File/line:** `apps/reference/main.py:722-755` (local `_retry_once()` uses `_retry_delay_sec/_max_retries`)
- **File/line:** `apps/reference/main.py:756-809` (drop/flush path uses `_max_retries`)
- **Impact:** mixed behavior: some deferrals use RetryScheduler, others use local retry loops → inconsistent boundedness and observability.

## Summary (“what breaks / why”)

- RetryScheduler currently depends on upstream payload correctness for attempt tracking and can leave intents pending forever when loop scheduling fails.
- Drop paths emit events via `fsm.emit` directly instead of `emit_compat`.
- AuroraBridge still contains hardcoded + duplicated retry behavior paths, making retry policy non-SSOT.

