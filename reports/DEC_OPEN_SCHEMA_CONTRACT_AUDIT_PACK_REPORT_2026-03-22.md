# DEC_OPEN_SCHEMA_CONTRACT_AUDIT_PACK — REPORT

## 1. Executive Verdict

- DEC:OPEN contract status: SCHEMA_DRIFT_BREAKING
- Registry verdict: NO_REGISTRY_CHANGE_NEEDED
- Domain dict verdict: NO_DOMAIN_DICT_CHANGE_NEEDED
- LIMIT_SUBMIT_TRACE verdict: TRACE_ONLY

Narrow conclusion:
- Official DEC:OPEN contract is still the strict registered schema at apps/reference/domains/execution_position/schemas/dec_open_v1.json.
- Post-patch LIMIT DEC:OPEN payload now carries four extra top-level forensic fields that are not allowed by that schema.
- Those fields are not proven business-semantic parts of the adapter command contract; they are only used for observability in open_executor.
- LIMIT_SUBMIT_TRACE did not become a bus verb or registry contract. It is a structured observability record written through order_logger, not through FSMCore.emit().

## 2. Official DEC:OPEN Contract

### Registry entry

Canonical registry entry:
- apps/reference/dictionaries/verb_registry_v1.yaml:56

Registered meaning:
- op: DEC
- verb: OPEN
- owner: execution_position
- status: active
- schema: apps/reference/domains/execution_position/schemas/dec_open_v1.json

### Domain dict entry

Canonical domain surface:
- apps/reference/domains/execution_position/domain_dict.json:20

Declared export:
- DEC:OPEN -> target_domains: [adapter]

### Schema path

Authoritative payload schema:
- apps/reference/domains/execution_position/schemas/dec_open_v1.json

Schema facts:
- additionalProperties: false
- required: symbol, side, qty, order_type
- conditional LIMIT requirements: price, tif, valid_for_ms
- conditional MARKET rule: tif must be null

### Owner and semantic role

Owner:
- execution_position

Semantic role:
- execution-position decision payload for opening an order
- adapter-facing command surface according to registry and domain_dict

### Production payload builder

Canonical builder path:
- apps/reference/domains/execution_position/fsm_open.py:426-457

Observed production contract boundary:
- OpenFlowFSM validates CMD:OPEN and constructs Message(op=DEC, verb=OPEN, pld=dec_pld)
- ExecPosFSM then routes that decision into execution logic

## 3. Actual Post-Patch Payload

### Actual builder behavior

Post-patch payload is constructed in:
- apps/reference/domains/execution_position/fsm_open.py:426-441

Base top-level keys emitted for DEC:OPEN:
- symbol
- side
- qty
- order_type

Conditional top-level keys already compatible with schema:
- tif
- price
- valid_for_ms
- stop_price
- target_price
- sl_pct
- idempotent_key

### Newly added post-patch forensic fields

Added only for LIMIT orders:
- price_before_rounding
- price_after_rounding
- tick_size
- rounding_mode

Placement:
- top-level DEC:OPEN payload

Presence:
- conditional
- present for LIMIT orders when price_dec is available
- absent for MARKET orders

### Actual observed LIMIT payload after patch

Direct runtime generation against current code produced this key set:
- symbol
- side
- qty
- order_type
- tif
- price
- price_before_rounding
- price_after_rounding
- tick_size
- rounding_mode
- valid_for_ms
- idempotent_key

Concrete reproduced payload:

```text
{'symbol': 'BTCUSDT', 'side': 'SELL', 'qty': '0.02', 'order_type': 'LIMIT', 'tif': 'GTX', 'price': '10000.1', 'price_before_rounding': '10000.005', 'price_after_rounding': '10000.1', 'tick_size': '0.1', 'rounding_mode': 'ceil', 'valid_for_ms': 60000, 'idempotent_key': 'KEY-LIMIT-AUDIT'}
```

### Downstream use of new fields

Observed reader path:
- apps/reference/domains/execution_position/open_executor.py:66-69

Actual use:
- open_executor reads those fields only to build LIMIT_SUBMIT_TRACE
- no evidence was found that adapter placement logic, bracket logic, or any other business consumer reads them as contract fields

Search result summary:
- app-level matches for price_before_rounding, price_after_rounding, tick_size, rounding_mode related to this patch are confined to fsm_open.py and open_executor.py
- test references exist, but no additional production consumer was found

## 4. Schema vs Payload Audit

### Exact audit result

Verdict:
- SCHEMA_DRIFT_BREAKING

### Why

Authoritative schema:
- apps/reference/domains/execution_position/schemas/dec_open_v1.json

Strict rule:
- additionalProperties: false

Schema does not define:
- price_before_rounding
- price_after_rounding
- tick_size
- rounding_mode

### Direct validation proof

A real post-patch LIMIT DEC:OPEN payload was generated from current OpenFlowFSM and validated against the registered DEC:OPEN validator.

Observed validator result:

```text
SCHEMA_VALIDATE ValidationError Additional properties are not allowed ('price_after_rounding', 'price_before_rounding', 'rounding_mode', 'tick_size' were unexpected)
```

### Practical impact

Fact pattern:
- Official DEC:OPEN schema rejects the current LIMIT producer payload.
- FSMCore.emit() performs schema validation before listener dispatch when a validator exists.
- tests/domains/execution_position/test_dec_open_contract_audit.py already proves that strict DEC:OPEN schema enforcement blocks payload drift such as payload-level rid enrichment.

Impact classification:
- Breaking against official contract surface
- Latent on direct runtime paths that do not re-emit DEC:OPEN through FSMCore
- Immediate on any schema-validated re-emit, test harness, or future bus-based DEC:OPEN dispatch path

### Why not SCHEMA_DRIFT_OPTIONAL

This is not a harmless optional extension because:
- the schema is strict
- the producer already emits those keys
- the official validator rejects them

## 5. Registry / DomainDict Audit

### Registry verdict

- NO_REGISTRY_CHANGE_NEEDED

Why:
- op/verb identity did not change
- owner did not change
- schema path did not change
- no evidence proves that DEC:OPEN business semantics intentionally expanded to include rounding forensic fields as official contract surface

What actually changed:
- implementation drifted away from the registered schema
- that is a producer/schema cleanliness problem, not a registry-definition problem

### Domain dict verdict

- NO_DOMAIN_DICT_CHANGE_NEEDED

Why:
- imports did not change
- exports did not change
- DEC:OPEN remains exported to adapter
- no new bus verb or target-domain surface was introduced by the patch

### What would justify registry/domain_dict updates

Only one of these would justify it:
- explicit decision to promote rounding forensic fields into official DEC:OPEN contract
- explicit decision to add a new bus-visible verb or target-domain surface

Current evidence proves neither.

## 6. LIMIT_SUBMIT_TRACE Classification

### Classification

- TRACE_ONLY

### Evidence

Definition site:
- apps/reference/domains/execution_position/open_executor.py:51-106

Write site:
- apps/reference/domains/execution_position/open_executor.py:428-448

Observed behavior:
- _collect_limit_submit_trace(...) builds a plain dict with event_type = LIMIT_SUBMIT_TRACE
- that dict is written via order_logger.write(submit_trace)
- a formatted LOG.info line is emitted
- no FSMCore.emit("EVT:..."), Message(op=..., verb=...), or verb_registry entry exists for LIMIT_SUBMIT_TRACE

Search result summary:
- app-level matches exist only in open_executor.py
- tests only validate the helper return dict
- no bus listeners or registry entries exist for LIMIT_SUBMIT_TRACE

### Important boundary note

LIMIT_SUBMIT_TRACE is not a bus contract.

However, it does create a separate observability-layer cleanliness issue:
- apps/reference/schemas/order_logger_v1.json event_type enum does not include LIMIT_SUBMIT_TRACE
- order_logger.write() validates against that schema in ENV=DEBUG or ENV=TEST

Direct proof:

```text
ORDER_LOG_VALIDATE ValueError Schema validation failed: 'LIMIT_SUBMIT_TRACE' is not one of [...]
```

So the correct classification is:
- TRACE_ONLY at architecture level
- latent order-log schema drift at observability layer

It is not an implicit event-like bus surface.

## 7. Minimal Cleanup Recommendation

- TRACE_ONLY_RELOCATION_PATCH

Why this is the minimal and sufficient action:
- The four new rounding fields are observability-only, not proven adapter command semantics.
- Keeping them inside top-level DEC:OPEN payload widens the official contract surface without evidence that the contract should widen.
- Updating dec_open_v1.json to accept them would canonize observability data into the adapter command contract.
- Registry and domain_dict do not need widening if the fields are relocated out of the official payload.

Minimal architectural target:
- restore DEC:OPEN payload to schema-defined business fields only
- keep rounding forensics in trace/meta-only machinery used by submit observability

## 8. FACTS

- DEC:OPEN is registered at apps/reference/dictionaries/verb_registry_v1.yaml:56 with schema apps/reference/domains/execution_position/schemas/dec_open_v1.json.
- execution_position exports DEC:OPEN to adapter in apps/reference/domains/execution_position/domain_dict.json:20.
- dec_open_v1.json is strict and sets additionalProperties: false.
- fsm_open.py currently adds price_before_rounding, price_after_rounding, tick_size, and rounding_mode into top-level DEC:OPEN payload for LIMIT orders.
- A real post-patch LIMIT DEC:OPEN payload fails validation against the registered DEC:OPEN schema.
- open_executor.py reads those four fields only to build LIMIT_SUBMIT_TRACE.
- No production bus verb registration or FSMCore.emit path was found for LIMIT_SUBMIT_TRACE.
- LIMIT_SUBMIT_TRACE is written through order_logger.write(), not through the event bus.
- order_logger_v1.json does not include LIMIT_SUBMIT_TRACE in event_type enum.
- In TEST mode, order_logger rejects LIMIT_SUBMIT_TRACE as schema-invalid.

## 9. INFERENCES

- The patch created real contract drift between DEC:OPEN producer payload and official DEC:OPEN schema.
- The drift is breaking at contract level even if the main direct execution path currently avoids bus re-emit.
- The four new fields are observability data, not proven business-semantic adapter command fields.
- Registry and domain_dict should remain unchanged unless the team intentionally decides to elevate those fields into official contract surface.
- LIMIT_SUBMIT_TRACE is an observability record, not a new implicit bus event contract.

## 10. ASSUMPTIONS

- Current direct runtime DEC:OPEN handling mainly consumes the returned Message object instead of bus-emitting it through FSMCore in production paths.
- Search coverage over apps/reference is sufficient to conclude there is no additional production consumer of the four forensic DEC:OPEN fields.
- The intended architectural goal of the patch was observability improvement, not expansion of adapter command semantics.

## 11. UNKNOWNS

- Whether any non-obvious production path outside the inspected execution flow re-emits DEC:OPEN through FSMCore.
- Whether the team intentionally wants to promote rounding forensic fields into the official DEC:OPEN contract despite their observability-only usage today.
- Whether LIMIT_SUBMIT_TRACE should eventually get a formal observability schema in the order log layer or move to a separate trace sink.

## 12. Risks

### Contract drift risk

- Official DEC:OPEN producer and DEC:OPEN schema are no longer aligned for LIMIT orders.
- Any schema-enforced DEC:OPEN re-emit path can fail closed.

### Observability confusion risk

- LIMIT_SUBMIT_TRACE looks structured enough to be mistaken for an event contract even though it is only a logger record.
- The same patch also introduced a separate order_logger schema mismatch for that trace record.

### Compatibility risk

- If downstream tools or tests begin to rely on strict DEC:OPEN schema validation for LIMIT orders, current payload shape will break them.
- If DEBUG or TEST environments exercise real order_logger validation, LIMIT_SUBMIT_TRACE can fail there independently of DEC:OPEN.

## 13. Next Action

- TRACE_ONLY_RELOCATION_PATCH

Why this is next:
- It fixes the primary contract cleanliness defect without widening DEC:OPEN official semantics.
- It preserves the useful observability intent of the patch.
- It avoids unnecessary registry/domain_dict churn.
- It is narrower and architecturally cleaner than schema-expanding DEC:OPEN just to carry debug fields.
