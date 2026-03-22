# FORENSIC_REPORT — LLM External Intent Path Break

**Case:** `rid=c4d939a0-bbbd-4ead-83f3-f3ddd6e6bea7`  
**Audit date:** 2026-03-20T22:05:51+02:00  
**Mode:** Forensic adversarial verifier. Fail-closed. No code changes.

---

## Executive Verdict

**FIRST PROVEN BREAK: `CMD:EXTERNAL_OPEN_REQUEST_V1` was emitted onto FSMCore at `21:56:02.520` and hit ZERO consumers. [ExecPosFSM](file:///c:/Users/user/Music/Phenix/apps/reference/domains/execution_position/fsm.py#161-2083) never registers a listener for this verb. `IntentRouter.on_external_open_request()` exists but is unwired.**

**Break classification: `LISTENER_NOT_REGISTERED`**

---

## Proven Timeline

| Timestamp | Event | Source | Evidence |
|---|---|---|---|
| `21:56:02,439` | `EVT:LLM_INTENT_ACCEPTED_V1` emitted | `LLMIntentIngressBridge._on_command()` | `aurora_core.log.1 L39592` (DEPRECATION warning + WAL) |
| `21:56:02,519` | `CMD:LLM_INTENT_SUBMIT_V1` emitted | `LLMIntentIngressBridge._on_command()` L195-199 | `aurora_core.log.1 L39593` (DEPRECATION warning) |
| `21:56:02,520` | `CMD:EXTERNAL_OPEN_REQUEST_V1` emitted | `main_bridge.py register_llm_command_mapper()._handler()` L230-232 | `aurora_core.log.1 L39594` (`AuroraCore.shadow_telemetry - INFO - LLM_EXTERNAL...`) |
| `21:56:02,520+` | **DEAD EMIT — no consumer** | `FSMCore.emit()` | No `execution_position` log entry for this rid anywhere in [domain_execution_position.log](file:///c:/Users/user/Music/Phenix/logs/domain_execution_position.log) or [aurora_core.log.1](file:///c:/Users/user/Music/Phenix/logs/aurora_core.log.1) |
| **Never** | `IntentRouter.on_external_open_request()` | **NEVER CALLED** | `grep -r "on_external_open_request" execution_position/fsm.py` → no results |
| **Never** | `CMD:OPEN` built | **NEVER CALLED** | No [domain_execution_position.log](file:///c:/Users/user/Music/Phenix/logs/domain_execution_position.log) entry |
| **Never** | `ORDER_PLACED / ORDER_REJECTED` | **NEVER CALLED** | No entry in any log |

---

## Findings

### FINDING-01: `CMD:EXTERNAL_OPEN_REQUEST_V1` Has No Registered Consumer

| Field | Value |
|---|---|
| **ID** | FINDING-01 |
| **Severity** | P0 — COMPLETE SILENCE: all external LLM trade intents are ignored |
| **Type** | `LISTENER_NOT_REGISTERED` |

**FACTS:**
- `main_bridge.py:register_llm_command_mapper()` (L240) calls `fsm.listen("CMD:LLM_INTENT_SUBMIT_V1", _handler)`. This is confirmed registered in `main.py L813`.
- [_handler()](file:///c:/Users/user/Music/Phenix/apps/reference/domains/shadow_telemetry/main_bridge.py#207-239) in [register_llm_command_mapper()](file:///c:/Users/user/Music/Phenix/apps/reference/domains/shadow_telemetry/main_bridge.py#202-242) calls `fsm.emit("CMD:EXTERNAL_OPEN_REQUEST_V1", ...)` (L230-232). This emit IS confirmed by the runtime log at `21:56:02.520`.
- `grep "EXTERNAL_OPEN_REQUEST" execution_position/fsm.py` → **no results**.
- `grep "listen" execution_position/fsm.py` → **no results**.
- `grep "on_external_open_request" execution_position/fsm.py` → **no results**.
- `IntentRouter.on_external_open_request()` method EXISTS at `intent_router.py L290` with full gate logic (GATE 1–6), CMD:OPEN construction, and [_emit_external_rejection()](file:///c:/Users/user/Music/Phenix/apps/reference/domains/execution_position/intent_router.py#492-526) — but is never called.

**INFERENCE:**
- The handler was implemented in isolation (intent_router.py) without the corresponding listener registration step in the component that owns the FSM bus (fsm.py or initialization).
- The design intent was: `fsm.listen("CMD:EXTERNAL_OPEN_REQUEST_V1", self.intent_router.on_external_open_request)` somewhere in ExecPosFSM's constructor or in main.py after initialization. This line was never written.

**Cause:** Missing `fsm.listen()` call for `CMD:EXTERNAL_OPEN_REQUEST_V1`.
**Mechanism:** FSMCore emits the command; no listener is in the registry; the event is dropped silently.
**Effect:** Every external LLM trade intent is silently discarded after the mapper stage.
**Operational risk:** All LLM-driven trades fail-silently. No `EVT:EXTERNAL_OPEN_REQUEST_REJECTED_V1` is emitted. No WAL record. No alerting.
**Evidence:** Log at `aurora_core.log.1 L39594`; `grep` across all execution_position code.

---

### FINDING-02: Schema Absent for Both `LLM_INTENT_ACCEPTED_V1` and `LLM_INTENT_SUBMIT_V1`

| Field | Value |
|---|---|
| **ID** | FINDING-02 |
| **Severity** | P2 — Contract Gap |
| **Type** | `OBSERVABILITY_GAP` (secondary) |

**FACTS:**
- `aurora_core.log.1 L39592`: `DEPRECATION: Emitting EVT:LLM_INTENT_ACCEPTED_V1 without JSON Schema validation.`
- `aurora_core.log.1 L39593`: `DEPRECATION: Emitting CMD:LLM_INTENT_SUBMIT_V1 without JSON Schema validation.`
- Neither verb has a schema registered in [verb_registry_v1.yaml](file:///c:/Users/user/Music/Phenix/apps/reference/dictionaries/verb_registry_v1.yaml).

**Cause:** Both verbs were not added to the schema registry.
**Effect:** No contract enforcement at emit time; payload shape drift is invisible.
**Risk for FINDING-01 fix:** when the listener is wired, payload validation will still be off.

---

### FINDING-03: [_emit_external_rejection()](file:///c:/Users/user/Music/Phenix/apps/reference/domains/execution_position/intent_router.py#492-526) Has Observability Gap

| Field | Value |
|---|---|
| **ID** | FINDING-03 |
| **Severity** | P2 — Observability |
| **Type** | `OBSERVABILITY_GAP` |

**FACTS:**
- `intent_router.py L508-510`: [_emit_external_rejection()](file:///c:/Users/user/Music/Phenix/apps/reference/domains/execution_position/intent_router.py#492-526) emits via `self._fsm.bus.emit(...)` only `if hasattr(self._fsm, "bus")`. If `self._fsm` is [ExecPosFSM](file:///c:/Users/user/Music/Phenix/apps/reference/domains/execution_position/fsm.py#161-2083) (which wraps [FSMCore](file:///c:/Users/user/Music/Phenix/vfoundation/core/fsm_core.py#18-179)), [bus](file:///c:/Users/user/Music/Phenix/apps/reference/domains/execution_position/fsm.py#1846-1866) may or may not be exposed as an attribute.
- No WAL write exists inside [_emit_external_rejection()](file:///c:/Users/user/Music/Phenix/apps/reference/domains/execution_position/intent_router.py#492-526). The reject event would only appear in the bus; if the bus listener for `EXTERNAL_OPEN_REQUEST_REJECTED_V1` is also absent, rejection is also silently dropped.

**INFERENCE:** Even after FINDING-01 is fixed, if a gate rejects the request, the rejection event silently fails unless `self._fsm.bus` exists and has a listener.

---

## First Proven Break

**File:** [apps/reference/main.py](file:///c:/Users/user/Music/Phenix/apps/reference/main.py) and/or [execution_position/fsm.py](file:///c:/Users/user/Music/Phenix/apps/reference/domains/execution_position/fsm.py) (ExecPosFSM constructor)  
**Function:** ExecPosFSM initialization / [main.py](file:///c:/Users/user/Music/Phenix/apps/reference/main.py) startup sequence  
**Stage:** Listener registration phase  
**Missing line:**
```python
# MISSING — never written:
fsm.listen("CMD:EXTERNAL_OPEN_REQUEST_V1", exec_pos_fsm.intent_router.on_external_open_request)
# OR equivalently in ExecPosFSM.__init__():
self.fsm.listen("CMD:EXTERNAL_OPEN_REQUEST_V1", self.intent_router.on_external_open_request)
```

---

## Alternate Hypotheses — Verified and Rejected

| Hypothesis | Status | Evidence |
|---|---|---|
| `CMD:LLM_INTENT_SUBMIT_V1` not emitted | **REJECTED** | `aurora_core.log.1 L39593` — DEPRECATION warning confirms emit occurred |
| Mapper ([register_llm_command_mapper](file:///c:/Users/user/Music/Phenix/apps/reference/domains/shadow_telemetry/main_bridge.py#202-242)) not active | **REJECTED** | `main.py L813` confirms it's called on startup; log at L39594 confirms mapper handler ran |
| `CMD:EXTERNAL_OPEN_REQUEST_V1` not emitted | **REJECTED** | `aurora_core.log.1 L39594` — explicit `LLM_EXTERNAL:...->CMD:EXTERNAL_OPEN_REQUEST_V1` log |
| Schema validation blocked the emit | **REJECTED** | DEPRECATION warnings = emit proceeded without schema; no blocking schema error logged |
| `LLM_INTENT_REJECTED_V1` emitted (mode=baseline or symbol not owned) | **REJECTED** | No such entry in WAL or logs; `LLM_INTENT_ACCEPTED_V1` was logged, not rejected |
| Handler crashed inside [on_external_open_request](file:///c:/Users/user/Music/Phenix/apps/reference/domains/execution_position/intent_router.py#290-491) | **REJECTED** — handler was never called | No `[1000PEPEUSDT] External open request` log, no `Failed to process CMD:EXTERNAL_OPEN_REQUEST_V1` error |
| Symbol not in allowlist causing reject before acceptance | **REJECTED** | `LLM_INTENT_ACCEPTED_V1` was emitted and WAL'd — acceptance occurred |

---

## Answers to Required Questions (A–E)

### A. Acceptance Boundary

**A1. What executes after `LLM_INTENT_ACCEPTED_V1`?**  
FACT: `LLMIntentIngressBridge._on_command()` L195-199 calls `self.fsm.emit("CMD:LLM_INTENT_SUBMIT_V1", payload=cmd.model_dump(), why="llm_intent_submit")`.

**A2. Is `CMD:LLM_INTENT_SUBMIT_V1` emitted?**  
FACT: YES. Confirmed by `aurora_core.log.1 L39593`.

**A3. Why does the path stop?**  
FACT: It doesn't stop at LLM_INTENT_SUBMIT_V1. The mapper runs and emits `CMD:EXTERNAL_OPEN_REQUEST_V1`. The path stops there because no listener is registered.

### B. Mapper Boundary

**B4. Is the mapper registered?**  
FACT: YES. `main.py L813` calls [register_llm_command_mapper(fsm, ...)](file:///c:/Users/user/Music/Phenix/apps/reference/domains/shadow_telemetry/main_bridge.py#202-242). Confirmed at runtime (log L39594 shows mapper produced the external open request).

**B5. Does it listen on `CMD:LLM_INTENT_SUBMIT_V1`?**  
FACT: YES. `main_bridge.py L240`: `fsm.listen("CMD:LLM_INTENT_SUBMIT_V1", _handler)`.

**B6. Does it emit `CMD:EXTERNAL_OPEN_REQUEST_V1`?**  
FACT: YES. Confirmed by `aurora_core.log.1 L39594`.

**B7. Blockers?**  
FACT: None in this case. The mapper ran to completion.

### C. Execution Boundary

**C8. Is there a listener for `CMD:EXTERNAL_OPEN_REQUEST_V1` in execution_position?**  
FACT: NO. `grep "EXTERNAL_OPEN_REQUEST" execution_position/fsm.py` → no results. `grep "listen" execution_position/fsm.py` → no results.

**C9. Does the route reach `_on_external_open_request()`?**  
FACT: NO. Not called.

**C10. Is `IntentRouter.on_external_open_request()` called?**  
FACT: NO. Never invoked.

**C11. Is a reject event emitted?**  
FACT: NO. No `EXTERNAL_OPEN_REQUEST_REJECTED_V1` in any log or WAL.

**C12. Is `CMD:OPEN` built?**  
FACT: NO.

**C13. First break point?**  
FACT: **FSMCore bus emits `CMD:EXTERNAL_OPEN_REQUEST_V1` at `21:56:02.520`. No listener is registered. Event is dropped by FSMCore.**

### D. Observability

**D14. Does absence of records mean the event didn't happen?**  
FACT: No for the mapper path — log confirms the emit happened. YES for the handler invocation — no handler log exists because the handler was never registered.

**D15. Log/WAL hooks on each path segment:**
- `LLM_INTENT_RECEIVED_V1`: WAL + FSMCore emission
- `LLM_INTENT_ACCEPTED_V1`: WAL + FSMCore emission (confirmed)
- `CMD:LLM_INTENT_SUBMIT_V1`: FSMCore emission only (no WAL)
- `CMD:EXTERNAL_OPEN_REQUEST_V1`: mapper stdout log at INFO level (confirmed); no WAL
- `IntentRouter.on_external_open_request()`: LOG.info at L434 ("External open request → CMD:OPEN") — but never called
- `EVT:EXTERNAL_OPEN_REQUEST_REJECTED_V1`: [_emit_external_rejection()](file:///c:/Users/user/Music/Phenix/apps/reference/domains/execution_position/intent_router.py#492-526) at L507 — never called

**D16. Observability hole?**  
FACT: YES. Once `CMD:EXTERNAL_OPEN_REQUEST_V1` is emitted by the mapper, there is no WAL write, no fallback log, no dead-letter queue. If no listener exists, the event is silently dropped without any observable artifact.

### E. Contract Integrity

**E17. Verb name match between producer and consumer?**  
FACT: Producer emits `"CMD:EXTERNAL_OPEN_REQUEST_V1"` (L231). Consumer method docstring says it handles `CMD:EXTERNAL_OPEN_REQUEST_V1`. Verb names match. The issue is missing wiring, not mismatch.

**E18. Schema registry activates the needed verbs?**  
FACT: `verb_registry_v1.yaml L163/170` registers `CMD:EXTERNAL_OPEN_REQUEST_V1` and `EVT:EXTERNAL_OPEN_REQUEST_REJECTED_V1`. Schema [cmd_external_open_request_v1.json](file:///c:/Users/user/Music/Phenix/apps/reference/domains/execution_position/schemas/cmd_external_open_request_v1.json) exists. Registry is active.

**E19. Payload drift between mapper and intake?**  
UNPROVEN: Mapper (`main_bridge.py L212-228`) builds: `rid, intent_id, symbol, side, qty, order_type, price, tif, stop_price, target_price, valid_for_ms, idempotent_key, source, snapshot_ref, why_short`. Intake (`intent_router.py L300`) reads these fields. Field names appear compatible for GATE checks. `valid_for_ms: None` is set by mapper — GATE 6 will resolve from config (`llm_microstructure.pending_entry_ttl_ms`). Whether that config key exists is UNPROVEN.

**E20. ID mismatch causing dedupe/routing issues?**  
FACT: Not applicable to this break — the event never reaches any consumer that could deduplicate.

---

## What Remains Unproven

1. Whether `config.strategies.llm_microstructure.pending_entry_ttl_ms` is set in `aurora.yaml` (affects GATE 6 after the listener is wired).
2. Whether `self._fsm.bus` is exposed by ExecPosFSM (affects [_emit_external_rejection()](file:///c:/Users/user/Music/Phenix/apps/reference/domains/execution_position/intent_router.py#492-526) observability).
3. Schema validation behavior for `CMD:EXTERNAL_OPEN_REQUEST_V1` payload once it reaches the schema validator (schema exists; whether it would pass with the mapper payload is unproven).
4. Test coverage for the full path `main_bridge → EXTERNAL_OPEN_REQUEST_V1 → on_external_open_request → CMD:OPEN`.

---

## Minimal Next Action

**One surgical fix:** Wire the missing listener at ExecPosFSM startup or in [main.py](file:///c:/Users/user/Music/Phenix/apps/reference/main.py) after `execution_position` is initialized:

```python
# In main.py after line 528 (execution_position assigned):
fsm.listen(
    "CMD:EXTERNAL_OPEN_REQUEST_V1",
    execution_position.intent_router.on_external_open_request,
)
```

**Or in ExecPosFSM constructor, add:**
```python
self.fsm.listen(
    "CMD:EXTERNAL_OPEN_REQUEST_V1",
    self.intent_router.on_external_open_request,
)
```

Do NOT do anything else until this single registration is confirmed and `EVT:EXTERNAL_OPEN_REQUEST_REJECTED_V1` or internal `CMD:OPEN` appears in logs for a test intent.

---

## Evidence Appendix

### Log Excerpts — Directly Relevant Lines

```
aurora_core.log.1:39592:
2026-03-20 21:56:02,439 - vfoundation.core.fsm_core - WARNING -
DEPRECATION: Emitting EVT:LLM_INTENT_ACCEPTED_V1 without JSON Schema validation.
Please define a schema in verb_registry_v1.yaml.

aurora_core.log.1:39593:
2026-03-20 21:56:02,519 - vfoundation.core.fsm_core - WARNING -
DEPRECATION: Emitting CMD:LLM_INTENT_SUBMIT_V1 without JSON Schema validation.
Please define a schema in verb_registry_v1.yaml.

aurora_core.log.1:39594:
2026-03-20 21:56:02,520 - AuroraCore.shadow_telemetry - INFO -
LLM_EXTERNAL: intent_id=c4d939a0-bbbd-4ead-83f3-f3ddd6e6bea7
rid=c4d939a0-bbbd-4ead-83f3-f3ddd6e6bea7
side=SELL qty=1.5 price=0.0034060 -> CMD:EXTERNAL_OPEN_REQUEST_V1
```

**What follows in the log:** Normal market data, balance updates, no execution_position activity for this rid.

### Grep Evidence

```
grep "EXTERNAL_OPEN_REQUEST" execution_position/fsm.py
# → NO RESULTS

grep "listen" execution_position/fsm.py
# → NO RESULTS

grep "on_external_open_request" execution_position/fsm.py
# → NO RESULTS

grep "on_external_open_request" execution_position/intent_router.py
# → L290: def on_external_open_request(self, msg: "Message") -> None:

grep -r "c4d939a0" logs/domain_execution_position.log
# → NO RESULTS
```

### Producer → Consumer Verb Map

| Producer | Verb | Consumer | Status |
|---|---|---|---|
| HTTP ingress | → `IPC socket` | `LLMIntentIngressBridge._on_command()` | **ACTIVE** |
| [_on_command()](file:///c:/Users/user/Music/Phenix/apps/reference/domains/shadow_telemetry/main_bridge.py#117-200) | `EVT:LLM_INTENT_ACCEPTED_V1` | WAL + FSMCore listeners | **ACTIVE** (confirmed) |
| [_on_command()](file:///c:/Users/user/Music/Phenix/apps/reference/domains/shadow_telemetry/main_bridge.py#117-200) | `CMD:LLM_INTENT_SUBMIT_V1` | [register_llm_command_mapper()._handler()](file:///c:/Users/user/Music/Phenix/apps/reference/domains/shadow_telemetry/main_bridge.py#202-242) | **ACTIVE** (confirmed) |
| [_handler()](file:///c:/Users/user/Music/Phenix/apps/reference/domains/shadow_telemetry/main_bridge.py#207-239) | `CMD:EXTERNAL_OPEN_REQUEST_V1` | **NOTHING** | **DEAD EMIT — FIRST BREAK** |
| [on_external_open_request()](file:///c:/Users/user/Music/Phenix/apps/reference/domains/execution_position/intent_router.py#290-491) | internal `CMD:OPEN` | `ExecPosFSM.handle()` | NEVER REACHED |
| [on_external_open_request()](file:///c:/Users/user/Music/Phenix/apps/reference/domains/execution_position/intent_router.py#290-491) | `EVT:EXTERNAL_OPEN_REQUEST_REJECTED_V1` | Bus | NEVER REACHED |

### Code References

| File | Line | Content |
|---|---|---|
| [main_bridge.py](file:///c:/Users/user/Music/Phenix/apps/reference/domains/shadow_telemetry/main_bridge.py) | 192–199 | [LLMIntentIngressBridge](file:///c:/Users/user/Music/Phenix/apps/reference/domains/shadow_telemetry/main_bridge.py#81-200): emit ACCEPTED then SUBMIT |
| [main_bridge.py](file:///c:/Users/user/Music/Phenix/apps/reference/domains/shadow_telemetry/main_bridge.py) | 230–236 | [_handler()](file:///c:/Users/user/Music/Phenix/apps/reference/domains/shadow_telemetry/main_bridge.py#207-239): emit `CMD:EXTERNAL_OPEN_REQUEST_V1` |
| [main_bridge.py](file:///c:/Users/user/Music/Phenix/apps/reference/domains/shadow_telemetry/main_bridge.py) | 240 | `fsm.listen("CMD:LLM_INTENT_SUBMIT_V1", _handler)` |
| [main.py](file:///c:/Users/user/Music/Phenix/apps/reference/main.py) | 813 | [register_llm_command_mapper(fsm, ...)](file:///c:/Users/user/Music/Phenix/apps/reference/domains/shadow_telemetry/main_bridge.py#202-242) called |
| [intent_router.py](file:///c:/Users/user/Music/Phenix/apps/reference/domains/execution_position/intent_router.py) | 290 | `def on_external_open_request(self, msg)` — NEVER REGISTERED AS LISTENER |
| [execution_position/fsm.py](file:///c:/Users/user/Music/Phenix/apps/reference/domains/execution_position/fsm.py) | (all) | No `EXTERNAL_OPEN_REQUEST` mention, no [listen()](file:///c:/Users/user/Music/Phenix/vfoundation/core/fsm_core.py#33-45) calls |
| [aurora_core.log.1](file:///c:/Users/user/Music/Phenix/logs/aurora_core.log.1) | 39592–39594 | Timeline proof |
