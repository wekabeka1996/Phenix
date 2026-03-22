# TRACE_ONLY_RELOCATION_PATCH — REPORT

## 1. Executive Verdict

- Patch status: IMPLEMENTED
- DEC:OPEN contract status after patch: RESTORED_SCHEMA_VALID
- Registry verdict: NO_REGISTRY_CHANGE_NEEDED
- Domain dict verdict: NO_DOMAIN_DICT_CHANGE_NEEDED
- LIMIT_SUBMIT_TRACE verdict after patch: TRACE_ONLY_SCHEMA_ALIGNED

Narrow conclusion:
- The four forensic rounding fields were removed from top-level DEC:OPEN payload construction.
- Rounding observability was preserved by relocating those values into an envelope-only data_ref trace reference.
- LIMIT_SUBMIT_TRACE remained trace-only and was aligned with order_logger schema by using a valid order_logger event_type plus metadata.trace_kind=LIMIT_SUBMIT_TRACE.
- No verb registry or domain_dict change was required because no business contract surface was expanded.

## 2. Facts

### 2.1 Files changed

- apps/reference/domains/execution_position/fsm_open.py
- apps/reference/domains/execution_position/open_executor.py
- tests/domains/execution_position/test_open_flow_fsm_leverage_and_guards_v1.py
- tests/domains/execution_position/test_open_executor_submit_trace.py
- tests/domains/execution_position/test_dec_open_contract_audit.py

### 2.2 Producer change

In apps/reference/domains/execution_position/fsm_open.py:
- DEC:OPEN payload no longer emits:
  - price_before_rounding
  - price_after_rounding
  - tick_size
  - rounding_mode
- OpenFlowFSM now appends an envelope-only trace reference to data_ref for LIMIT decisions:
  - prefix: obs://execution_position/limit_rounding?
  - fields encoded in query params: before, after, tick, mode

### 2.3 Executor change

In apps/reference/domains/execution_position/open_executor.py:
- OpenExecutor now extracts rounding trace metadata from decision.data_ref instead of decision.pld.
- _collect_limit_submit_trace(...) now returns an order_logger-schema-valid record:
  - event_type: ORDER_INTENT
  - source_fsm: ExecPosFSM
  - quantity and price stay on allowed top-level fields
  - LIMIT_SUBMIT_TRACE identity moved to metadata.trace_kind
  - rounding and book context fields moved under metadata

### 2.4 Tests added/updated

- FSM rounding tests now assert that DEC:OPEN payload remains clean while data_ref carries the trace reference.
- Submit-trace tests now validate both observability content and direct conformance against apps/reference/schemas/order_logger_v1.json.
- A new LIMIT DEC:OPEN contract audit test now proves that a real LIMIT producer payload validates against the registered DEC:OPEN schema after relocation.

## 3. Inferences

- Relocating the forensic fields to data_ref preserves observability without widening the adapter-facing DEC:OPEN business contract.
- Using ORDER_INTENT with metadata.trace_kind=LIMIT_SUBMIT_TRACE preserves the trace classification while staying inside the existing logger schema boundary.
- This is the minimal localized fix because it changes only producer/executor/test code and leaves SSOT contract registries untouched.

## 4. Unproven / Not Changed

- No claim is made that data_ref is a durable long-term observability design standard for all future trace payloads.
- No registry/schema expansion was attempted for new trace types.
- No strategy math, order policy, or BUY floor / SELL ceil behavior was changed.

## 5. Validation

Focused validation command:

```text
C:/Users/user/Music/Phenix/.venv/Scripts/python.exe -m pytest tests/domains/execution_position/test_open_flow_fsm_leverage_and_guards_v1.py tests/domains/execution_position/test_open_executor_submit_trace.py tests/domains/execution_position/test_dec_open_contract_audit.py
```

Observed result:

```text
15 passed in 1.21s
```

What this proves:
- Real LIMIT DEC:OPEN payload is schema-valid again.
- Envelope-level trace relocation preserves rounding observability for executor submit tracing.
- order_logger schema accepts the submit trace record shape in test mode.
- Existing BUY floor / SELL ceil behavior remains intact.

## 6. Final Contract Position

### DEC:OPEN

- Official contract remains apps/reference/domains/execution_position/schemas/dec_open_v1.json.
- Payload drift is removed.
- No registry or domain_dict edits are justified.

### LIMIT_SUBMIT_TRACE

- Remains TRACE_ONLY.
- Not promoted to a bus verb.
- Not added to verb_registry_v1.yaml.
- Not added as a new order_logger event_type enum entry.
- Persisted as an ORDER_INTENT-class observability record with metadata.trace_kind=LIMIT_SUBMIT_TRACE.

## 7. One Narrow Next Action

- If the team wants first-class typed observability for submit-trace records later, define a dedicated observability contract deliberately instead of re-expanding DEC:OPEN or silently widening order_logger enums.
