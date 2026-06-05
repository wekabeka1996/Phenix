# EXECUTION_POSITION FULL STATIC AUDIT — Research Plan Completion

Source archive: `/mnt/data/execution_position.zip`  
Extracted workspace: `/mnt/data/ep_full/execution_position`  
Audit mode: **read-only static / forensic**  
Code changes: **none**  
Runtime validation: **not run**  
Total Python source files: **69**  
Total Python non-comment LOC: **27904**  
Schemas: **28**  
Markdown docs: **9**  
PYC files: **136**, orphan pyc: **2**

## Coverage discipline

This audit has two coverage levels:

1. **Programmatic full scan** — AST/regex/token/schema scan over 100% of Python/schema/doc files in the extracted domain.
2. **Manual semantic read** — targeted line-level inspection of files and paths where scan or architecture indicated risk.

Do not treat this report as runtime proof. It is a static localization report that identifies defect candidates and exact proof surfaces for the next code/test phase.

---

## Global scan summary

```yaml
python_files: 69
python_ncloc: 27904
json_schema_files: 28
markdown_docs: 9
async_functions: 88
broad_excepts: 275
getattr_get_calls: 1672
Any_refs: 557
suspicious_numeric_literals: 215
event_tokens: 43
pyc_files: 136
orphan_pyc_files: 2
```

## Semantic group inventory

| Group | Files | Non-comment LOC | % of Python LOC |
|---|---:|---:|---:|
| G0_contracts_docs_schemas | 39 | 2983 | 10.7% |
| G10_support_config_watchdog_validation | 10 | 1811 | 6.5% |
| G1_composition_event_async_shell | 5 | 3571 | 12.8% |
| G2_intent_open_entry | 7 | 3398 | 12.2% |
| G3_order_truth_restore_restart | 9 | 4000 | 14.3% |
| G4_manage_brackets_lifecycle | 7 | 3946 | 14.1% |
| G5_close_cancel_guardian_cleanup | 15 | 5885 | 21.1% |
| G6_exposure_qty_leverage | 7 | 2194 | 7.9% |
| G7_position_policy_sidecar | 2 | 1573 | 5.6% |
| G9_observability_metrics_logging | 5 | 1137 | 4.1% |


---

# Phase 0 — SSOT / boundary / registry map

## Coverage

```yaml
programmatic_scan:
  domain_dict: 100%
  schemas: 100%
  source_event_tokens: 100%
  verb_registry_cross_check: 100%
manual_semantic_read:
  approx_loc: 1200
  focus:
    - domain_dict.json
    - README.md
    - BOUNDARY_POLICY.md
    - docs/EVENT_CONTRACTS.md
    - source event producers/listeners
```

## FACTS

- `domain_dict.json` says execution_position is an execution soldier and does **not** make trading decisions.
- `README.md` repeats that the domain owns order placement, lifecycle FSM, brackets, exposure, watchdog, guardian, leverage, but not signal generation or risk assessment.
- `BOUNDARY_POLICY.md` forbids peer modules from cross-calling private peer state through `self._fsm._...` except sanctioned/deferred surfaces.
- Source contains 43 event/command tokens.
- Three domain exports are not registered in `verb_registry_v1.yaml`:
  - `CMD:POSITION_POLICY_SIDECAR_CLOSE_REQUEST`
  - `EVT:BRACKET_PLACEMENT_FAILED`
  - `EVT:POSITION_POLICY_SIDECAR_CLOSE_REQUEST_STATE`
- Three execution-position-owned registry verbs are not represented in `domain_dict.json` import/export surface:
  - `CMD:EXTERNAL_OPEN_REQUEST_V1`
  - `EVT:EXTERNAL_OPEN_REQUEST_REJECTED_V1`
  - `UPD:TICK`
- `docs/EVENT_CONTRACTS.md` mentions `EVT:ORDER_CANCELED` and `EVT:DEC_CLOSE_COMPLETED`; source/registry/domain_dict use different surfaces.

## Findings

### P1 — Registry/domain/source drift for action-bearing sidecar close command

Evidence:
- `position_policy_sidecar.py:27` defines `CMD:POSITION_POLICY_SIDECAR_CLOSE_REQUEST`.
- `position_policy_sidecar.py:612` publishes that command in enable mode.
- `position_policy_mediator.py:35` consumes close requests.
- `verb_registry_v1.yaml` has no `CMD:POSITION_POLICY_SIDECAR_CLOSE_REQUEST` entry.
- `domain_dict.json` exports/imports the command, so docs know it exists but canonical registry does not.

Impact:
- This violates contract-first / registry-first law.
- It is action-bearing in `enable` mode, not mere telemetry.

Required next proof:
- Add registry/schema contract or prove this command is intentionally non-registry internal bus only.
- If internal-only, domain_dict must explicitly mark it as internal and not public command surface.

### P1 — `EVT:BRACKET_PLACEMENT_FAILED` schema/source exists but registry lacks it

Evidence:
- `schemas/bracket_placement_failed_v1.json` exists.
- `fsm.py:2521`, `bracket_manager.py:74`, `close_executor.py:359`, `fsm_manage.py:757` reference/emit the event.
- Registry does not list `EVT:BRACKET_PLACEMENT_FAILED`.

Impact:
- Protective-bracket failure is safety-critical telemetry.
- An unregistered safety event can disappear from contract validation and downstream consumers.

### P2 — Stale public docs still describe non-current events

Evidence:
- `docs/EVENT_CONTRACTS.md` emits `EVT:ORDER_CANCELED` and `EVT:DEC_CLOSE_COMPLETED`.
- Source emits/uses `EVT:ORDER_STATE_CHANGED`, `EVT:EXECUTION_CLOSE_RECONCILED`, and observability event type `DEC_CLOSE_COMPLETED`, not a registered `EVT:DEC_CLOSE_COMPLETED`.

Impact:
- Operator/agent can audit wrong surfaces.
- This is documentation drift, not runtime proof.

---

# Phase 1 — Duplication / mass duplication

## Coverage

```yaml
programmatic_scan:
  AST classes/functions/imports: 100% Python source
manual_semantic_read:
  approx_loc: 900
  focus:
    - OrderStatus enum layers
    - six cancel bridge modules
    - close producer vs max-hold close bridges
    - stop price helpers
```

## FACTS

- `OrderStatus` exists in three layers:
  - `contracts.py`
  - `idempotent_cancel.py`
  - `infra/order_ledger.py`
- README explicitly documents this as intentional.
- Six cancel bridge modules repeat almost the same model shape: `GuardianBackgroundOrphanCancelRequest`, `GuardianOldBracketCleanupRequest`, `GuardianPreCloseCleanupRequest`, `GuardianReconcileCancelRequest`, `ReconcileCloseCancelRequest`, `TrackedCloseTeardownCancelRequest`.
- Public method duplicates include:
  - `idempotent_key()` in 6 bridge classes
  - `why()` in 6 bridge classes
  - `to_dec_close_payload()` in close producer and max-hold bridges
- `contracts.py` has a `parse_stop_price` validator method; `stopprice_validation.py` defines standalone `parse_stop_price`, `is_valid_stop_price`, `format_ep1102_reason`.

## Findings

### P2 — Cancel bridge duplication is deliberate but fragile

Evidence:
- Every guardian/close cancel bridge claims a narrow seam into `DEC:CANCEL_ORDER`.
- Each repeats idempotent-key construction and why-path behavior.

Interpretation:
- This duplication is not automatically wrong; it preserves package boundaries.
- But it is a maintenance risk: one seam can evolve differently and create inconsistent cancel idempotency/reason semantics.

Required next proof:
- Contract regression across all six bridges:
  - same required identity fields,
  - same `DEC:CANCEL_ORDER` payload shape,
  - same idempotency stability,
  - same rejection behavior for malformed orders.

### P3 — `stopprice_validation.py` appears locally unused

Evidence:
- Static local import scan found no import of `stopprice_validation.py`.
- Search found no local uses of `is_valid_stop_price` or `format_ep1102_reason`.
- `contracts.py` has a separate stop-price parser/validator.

Scope:
- Local-domain only. Could be imported outside zip; not proven dead globally.

Required next proof:
- Repo-wide import scan outside zip.
- If unused globally, either wire it as SSOT or remove it.

---

# Phase 2 — Async / event causal chain

See previous phase report for full detail. Retained high-severity findings:

## P1 — `_cleanup_loop()` swallows `CancelledError`

Evidence:
- `fsm.py:2737-2749` catches `asyncio.CancelledError` but does not `raise` or `break`.

Impact:
- Cleanup task can survive cancellation and continue orphan cleanup across shutdown/restart boundary.

## P1 — `DEC:*` can be WAL-recorded but not executed if no async loop exists

Evidence:
- `fsm.py:1618-1636` appends DEC to WAL before checking async loop.
- If loop is missing, it logs error and does not emit terminal failure.
- `BATCH` path is even weaker: `fsm.py:1607-1616` appends sub-message and only schedules if loop exists, with no else/error branch.

Impact:
- Truth plane can show a DEC while exchange action never happened.

## P1 — Parallel bracket placement can double-submit or race on partial success

Evidence:
- `bracket_manager.py:251-252` uses `asyncio.gather(..., return_exceptions=False)`.
- `bracket_manager.py:253-276` falls back to sequential SL/TP submission after one parallel path fails.
- If one coroutine already succeeded or is in-flight, fallback can repeat the same side.

Impact:
- Duplicate bracket submit, partial protective state, or orphan bracket.

---

# Phase 3 — Logic illusion / code that looks safer than it is

## Coverage

```yaml
programmatic_scan:
  fallback/shadow/best_effort/emit/exception patterns: 100% Python source
manual_semantic_read:
  approx_loc: 1600
  focus:
    - LocalBus
    - sidecar enable path
    - execution truth hardening attach
    - close flag lifecycle
    - event emit wrappers
```

## Findings

### P1 — `PositionPolicySidecar` in `enable` mode is action-bearing, not recommendation-only

Evidence:
- `position_policy_sidecar.py:588-612` publishes `EVT:POSITION_POLICY_SIDECAR_RECOMMENDED`, then publishes `CMD:POSITION_POLICY_SIDECAR_CLOSE_REQUEST` if mode is `ENABLE`.
- `position_policy_sidecar.py:692-717` does the same for peak giveback trigger.
- `position_policy_mediator.py:121-138` converts the request into `CMD:CLOSE` and calls `self._fsm.handle(close_msg)`.

Impact:
- Operationally, `enable` means sidecar can initiate close through the normal close seam.
- This is not wrong if configured intentionally, but any assumption that sidecar is always shadow/recommendation-only is false.

Required next proof:
- Inspect YAML mode.
- Test `disable`, `shadow`, `enable` behavior:
  - shadow must never publish command,
  - enable must only publish after all freshness/lifecycle/hardening gates.

### P2 — LocalBus swallows callback exceptions

Evidence:
- `utils_event_bus.py:50-59` logs callback exception and continues.

Impact:
- In shadow/test LocalBus mode, a critical callback may fail while the emitter sees no failure.
- Current `fsm.py:502-510` restricts LocalBus to shadow mode or raises in non-shadow, so runtime blast radius is bounded.

### P2 — `_emit_execution_bus_event()` silently drops bus/observability failures

Evidence:
- `fsm.py:2446-2458` catches and passes on `bus.emit`.
- `fsm.py:2459-2465` catches and passes on observability emit.

Impact:
- Safety telemetry like `EVT:BRACKET_PLACEMENT_FAILED` can be lost without escalation.
- In a forensic system, silent telemetry loss is a truth-plane defect.

---

# Phase 4 — Fallbacks / hardcoded params / silent defaults

## Coverage

```yaml
programmatic_scan:
  fallback/default/getattr/get/business literals: 100% Python source
manual_semantic_read:
  approx_loc: 1700
  focus:
    - fsm_open
    - watchdog
    - truth_hardening
    - adapter_init
    - exposure_guard
```

## Findings

### P1 — `OpenFlowFSM._get_instrument_specs()` silently falls back to hardcoded instrument constants

Evidence:
- `fsm_open.py:316-324` reads `config.instruments`, then defaults to:
  - `MIN_ORDER_QTY`
  - `QTY_STEP`
  - `PRICE_STEP`
  - `MIN_NOTIONAL`
- `fsm_open.py:326-352` only overrides values if specs exist.
- If symbol config is missing, no fail-closed error is raised.
- Constants are defined in `contracts.py:73-82`.

Impact:
- This violates instrument YAML SSOT.
- A live order can be normalized against generic constants instead of actual Binance filters.
- This directly matches the defect class that causes precision/min-notional rejects.

Required next proof:
- Test `CMD:OPEN` for a symbol absent from `config.instruments`.
- Expected safe behavior: reject before DEC:OPEN.
- Current suspected behavior: generic constants allow path to continue.

### P1 — Execution truth hardening disables itself on config error

Evidence:
- `truth_hardening.py:882-934` catches any exception while resolving hardening config, logs `Execution truth hardening disabled`, and returns `None`.
- `truth_hardening.py:812-814` means `attach_execution_truth_hardening()` returns `None`.
- `fsm.py:514-517` attaches hardening during init but does not fail startup if attach returns None.

Impact:
- Duplicate fill/close guard layer can be absent because config resolution failed.
- The code logs, but runtime continues.
- This violates fail-closed expectations for lifecycle-critical hardening.

Required next proof:
- Startup test with malformed `domains.execution_position.event_dedup.warm_state.max_entries`.
- Expected: startup fails closed.
- Current suspected behavior: startup continues without hardening.

### P2 — Panic killswitch gate fails open on config access exception

Evidence:
- `fsm_open.py:411-424` reads `trading.ops.panic_killswitch`.
- On exception it `pass`es with comment `Fail-open for incomplete/mocked configs`.

Impact:
- If live config shape is malformed but startup did not catch it, open orders are not blocked.
- Could be acceptable for tests only, but production path should not silently fail open.

Required next proof:
- Confirm Pydantic startup makes this impossible in production.
- If not impossible, change to fail-closed except in explicit test/shadow mode.

### P3 — Watchdog class still contains hardcoded business defaults

Evidence:
- `watchdog.py:57-72` defaults:
  - `ack_ttl_ms=8000`
  - `fill_ttl_ms=30000`
  - `check_interval_ms=1000`
  - `rps_limit=10`
- Current `fsm.py:620-625` passes canonical values from config, so this may be non-live.

Impact:
- Low if only instantiated by `ExecPosFSM`.
- Future/direct instantiation can reintroduce silent defaults.

---

# Phase 5 — Types / schemas / payload quality

## Coverage

```yaml
programmatic_scan:
  schemas: 100%
  Any refs: 557
  getattr/get calls: 1672
  additionalProperties flags: 100%
manual_semantic_read:
  approx_loc: 1400
```

## Findings

### P2 — Many critical schemas permit payload drift with `additionalProperties: true`

Schemas with loose extras include:
- `bracket_placement_failed_v1.json`
- `cmd_position_policy_sidecar_close_request_v1.json`
- `exposure_summary_updated_v1.json`
- `order_fill_v1.json`
- `order_rejected_v1.json`
- `order_state_changed_v1.json`
- all sidecar telemetry schemas

Impact:
- This may be intentional for compatibility.
- But it weakens drift detection in exactly the surfaces used for forensic truth.

Required next proof:
- Decide which events are compatibility envelopes vs strict contracts.
- For strict surfaces, set `additionalProperties: false` or add explicit `metadata` bag.

### P2 — High use of `Any` and dict payload mutation remains

Evidence:
- AST scan: 557 `Any` refs.
- AST scan: 1672 `getattr` / `.get` style dynamic accesses.
- This is expected in event-boundary code but should be minimized at canonical seams.

Impact:
- Payload shape can be ambiguous.
- Runtime proof requires schema validation, not type hints alone.

---

# Phase 6 — Entry / open path

## Coverage

```yaml
programmatic_scan:
  G2_intent_open_entry: 100%
manual_semantic_read:
  approx_loc: 1800 / 3398
  files:
    - trade_intent_open_intake.py
    - intent_router.py
    - entry_manager.py
    - open_executor.py
    - fsm_open.py
    - open_dispatch_adapter.py
    - open_submission_adapter.py
```

## Findings

### P1 — Missing instrument config can still pass open preflight using generic constants

Same as Phase 4 P1. This is the highest entry-path issue.

### P2 — Maker-only config access fails open on exception

Evidence:
- `fsm_open.py:445-460` catches exception and passes.

Impact:
- If config is malformed and not caught at startup, maker-only enforcement can be skipped.
- Need production startup proof before accepting as safe.

### P2 — MARKET min-notional check only runs if `price_ref` exists

Evidence:
- `fsm_open.py:541-552` checks market notional only when `price_ref is not None`.

Impact:
- If MARKET order arrives without `price_ref`, min_notional guard is skipped in `OpenFlowFSM`.
- It may be checked later in sizing/adapter, but this local guard is incomplete.

Required next proof:
- Test MARKET `CMD:OPEN` without `price_ref`.
- Expected: reject or prove downstream fail-closed before adapter submit.

---

# Phase 7 — Manage / bracket lifecycle

## Coverage

```yaml
programmatic_scan:
  G4_manage_brackets_lifecycle: 100%
manual_semantic_read:
  approx_loc: 1900 / 3946
```

## Findings

### P1 — Parallel bracket partial-success race

See Phase 2.

### P1 — Bracket failure event not registered

See Phase 0.

### P2 — `BRACKET_PROTECTION_MISSING` close is generated from local position state, not live-position proof

Evidence:
- `fsm_manage.py:709-733` builds `DEC:CLOSE` if local position fields exist.
- Unlike `fsm.py:_handle_bracket_protection_missing`, this path does not require `live_position_proven=True`.

Impact:
- It may be acceptable because close executor re-reads exchange position before submitting.
- But the remediation intent is based on local lifecycle state.
- Needs test to prove close executor always fails closed when live position truth is unresolved.

### P2 — Anti-race closing flag has timeout-based self-clear

Evidence:
- `fsm_manage.py:1129-1143` skips bracket placement while `_closing_position` is true, but clears it after `_anti_race_close_ms`.

Impact:
- Useful containment.
- But if close is hung longer than the anti-race window, ManageFlow may resume bracket placement during unresolved close.

Required next proof:
- Test close path delayed longer than `anti_race_close_ms` with position still open/closing.
- Ensure bracket placement cannot resurrect unsafe auxiliaries.

---

# Phase 8 — Close / cancel / guardian

## Coverage

```yaml
programmatic_scan:
  G5_close_cancel_guardian_cleanup: 100%
manual_semantic_read:
  approx_loc: 2300 / 5885
```

## Findings

### P1 — `_closing_position` can remain stuck true after close submission build failure

Evidence:
- `close_executor.py:1279-1282` sets `manage._closing_position = True`.
- `close_executor.py:1351-1358` calls `_build_close_submission`; if it returns `None`, function returns without clearing `_closing_position`.
- `close_executor.py:1432-1438` clears only at successful end of the full-close path.

Impact:
- ManageFlow can remain in close-in-progress illusion.
- Bracket placement, sidecar mediation, and lifecycle checks can suppress forever or until some other reset.
- This is a direct state-leak defect candidate.

Required next proof:
- Unit test: force `_build_close_submission()` to return `None` after flag set.
- Assert `_closing_position` is cleared in `finally`.

### P1 — `_closing_position` can remain stuck if post-submit cleanup raises before final clear

Evidence:
- `close_executor.py:1429-1430` calls `order_guardian.cleanup_orphans()` and `reconcile_symbol()` outside the prior try block.
- If either raises, function exits before `close_executor.py:1432-1438` clears `_closing_position`.

Impact:
- Same stuck-close state.
- More likely than build failure during API degradation.

Required next proof:
- Unit test: close order submit succeeds; guardian cleanup raises.
- Assert close flag clears and failure is observable.

### P2 — Mass cancel bridge duplication needs contract-equivalence tests

See Phase 1.

---

# Phase 9 — Restart / restore / truth hardening

## Coverage

```yaml
programmatic_scan:
  G3_order_truth_restore_restart: 100%
manual_semantic_read:
  approx_loc: 1600 / 4000
```

## Findings

### P1 — Hardening attach fail-open

See Phase 4.

### P2 — Authoritative restore applier mutates FSM state through private internals

Evidence:
- `authoritative_restore_apply.py` directly calls:
  - `_get_or_create_manage_flow`
  - `_set_manage_truth_source`
  - `_get_or_create_close_flow`
  - `_clear_symbol_brackets`
  - `_pending_brackets`
  - `_set_symbol_brackets_snapshot`

Interpretation:
- This may be sanctioned by current implementation package.
- But it is a direct mutation seam and must stay explicitly bounded.

Required next proof:
- Cross-check against `BOUNDARY_POLICY.md`.
- Ensure every mutating call is either sanctioned or documented as deferred violation.

### P2 — Warm-state cache load failure is intentionally non-authoritative but still “fail-open empty seed”

Evidence:
- `truth_hardening.py:1028-1030` records notes `cache_only_load_failed`, `fail_open_empty_seed`.

Impact:
- This is acceptable only if duplicate/close protection does not depend on cache authority.
- It should not be treated as proof of restart safety.

---

# Phase 10 — Exposure / qty / leverage

## Coverage

```yaml
programmatic_scan:
  G6_exposure_qty_leverage: 100%
manual_semantic_read:
  approx_loc: 1300 / 2194
```

## Findings

### P2 — `ExposureGuard` fallback mode emits async alert events through local `create_task` helper without result accounting

Evidence:
- `exposure_guard.py:253-254`, `319-320` schedule `emit_compat`.
- `exposure_guard.py:1049-1075` creates tasks or closes coroutine if no loop.

Impact:
- Telemetry can be skipped without domain-level terminal event if no loop.
- Not money-actioning, but forensic visibility risk.

### P2 — Exposure fallback events are in domain_dict but not source-token exact public emission via bus token scan

Evidence:
- Domain exports include `EVT:FALLBACK_MODE_ENTERED` / `EVT:FALLBACK_MODE_EXITED`.
- Source emits `Message(op="EVT", verb="FALLBACK_MODE_ENTERED")`, which is valid but not captured as string token `EVT:FALLBACK_MODE_ENTERED`.

Interpretation:
- Not a bug. Just note that source-token scans must include op+verb constructions.

---

# Phase 11 — Position Policy Sidecar

## Coverage

```yaml
programmatic_scan:
  G7_position_policy_sidecar: 100%
manual_semantic_read:
  approx_loc: 1300 / 1573
```

## Findings

### P1 — Sidecar close command is action-bearing but not registry-registered

See Phase 0 and Phase 3.

### P2 — Mediator uses sidecar request schema normalization defaults

Evidence:
- `position_policy_mediator.py:198-212` sets defaults for missing `event_type`, `requested_action`, `target_mode`, `policy_source`, `allowed_action_scope`, etc.
- Schema requires many fields, but mediator can normalize missing ones.

Impact:
- This may be compatibility-hardening.
- But for an action-bearing command, defaulting policy fields can blur whether the producer actually supplied the contract.

Required next proof:
- Negative test: malformed sidecar command missing required governance fields.
- Expected: suppressed as invalid, not normalized into executable close request.

### P2 — Sidecar freshness gating exists and is strong, but exact config source not verified in this zip

Evidence:
- `position_policy_sidecar.py:768-774` suppresses stale portfolio/features/regime.
- `position_policy_sidecar.py:1305-1325` computes freshness against config thresholds.

Unproven:
- Whether YAML/Pydantic makes thresholds mandatory and strict.

---

# Phase 12 — Observability / forensic auditability

## Coverage

```yaml
programmatic_scan:
  G9 + event emit wrappers: 100%
manual_semantic_read:
  approx_loc: 1100
```

## Findings

### P1 — Safety telemetry events can be emitted through silent best-effort wrappers

Evidence:
- `fsm.py:2446-2465` swallows bus and observability exceptions.
- Several safety paths call `_emit_execution_bus_event()`, including bracket protection missing.

Impact:
- The domain can experience a protection failure and fail to publish the event without hard failure.

Required next proof:
- Test bus.emit raises during bracket placement failure.
- Expected: either lifecycle journal records failure or explicit degraded telemetry marker exists.

### P2 — `DEC_CLOSE_COMPLETED` is observability-only, not a registered event

Evidence:
- `close_executor.py:1268` and `1442` call `_emit_observability_event("DEC_CLOSE_COMPLETED", ...)`.
- Docs describe `EVT:DEC_CLOSE_COMPLETED`.

Impact:
- A reader may search wrong sink/event.
- Not necessarily runtime defect, but forensic naming drift.

---

# Phase 13 — Dead code / stale artifacts / pycache

## Coverage

```yaml
programmatic_scan:
  pyc/source matching: 100%
  local import graph: 100%
manual_semantic_read:
  approx_loc: 500
```

## Findings

### P2 — Orphan pyc exists for deleted `limit_order_monitor`

Evidence:
- `__pycache__/limit_order_monitor.cpython-311.pyc`
- `__pycache__/limit_order_monitor.cpython-314.pyc`
- no `limit_order_monitor.py` in archive.

Impact:
- Stale artifact can mislead audits.
- If package/import path accidentally uses pycache in unusual environments, this is dangerous; normal Python source import should not load it without source under normal package import rules.

Required next proof:
- Repo cleanup: remove stale pyc from source/package artifacts.
- Registry/docs search for `LIMIT_ORDER_TIMEOUT` and `limit_order_monitor`.

### P2 — Potential locally unimported modules

Static local import graph found no local imports for:
- `drift_monitor.py`
- `leverage_service.py`
- `metrics_aggregator.py`
- `order_index.py`
- `stopprice_validation.py`

Scope:
- This is only within the uploaded domain zip.
- They may be imported by composition root outside the zip.

Highest concern:
- `stopprice_validation.py`, because no local references to its helper functions were found while `contracts.py` has another stop-price parser.

---

# Phase 14 — Final contradiction map

## Coverage

```yaml
programmatic_scan:
  docs/schemas/registry/source event tokens: 100%
manual_semantic_read:
  approx_loc: 1200
```

| Contradiction | Severity | Evidence | Required action |
|---|---:|---|---|
| Sidecar close command is action-bearing but not registry registered | P1 | `position_policy_sidecar.py:612`, `position_policy_mediator.py:35`, no registry entry | Register or explicitly mark internal-only |
| Bracket placement failure event has schema/source but no registry entry | P1 | schema exists; `fsm.py:2521`; no registry entry | Register event |
| Open path missing instrument config falls back to generic constants | P1 | `fsm_open.py:316-324` | fail closed on missing symbol config |
| Close path can leave `_closing_position` stuck | P1 | `close_executor.py:1279-1282`, `1357-1358`, `1429-1438` | use `try/finally` around full close flag |
| Execution truth hardening config errors disable hardening | P1 | `truth_hardening.py:882-934`, `fsm.py:514-517` | fail startup or explicit disabled config only |
| Async cleanup loop swallows cancellation | P1 | `fsm.py:2737-2749` | re-raise/break on `CancelledError` |
| DEC can be recorded without terminal no-loop failure | P1 | `fsm.py:1607-1636` | emit terminal failure if no loop |
| Parallel bracket placement can race partial success | P1 | `bracket_manager.py:251-276` | gather with result classification; retry only failed side |
| Docs mention event names not used/registered | P2 | `docs/EVENT_CONTRACTS.md` vs source/registry | update docs |
| Loose schemas allow drift on critical forensic events | P2 | `additionalProperties: true` in many schemas | strict schema or explicit metadata bag |
| LocalBus and execution event wrappers swallow exceptions | P2 | `utils_event_bus.py:57-59`, `fsm.py:2457-2465` | add failure visibility |
| Orphan `limit_order_monitor` pyc | P2 | pyc without source | remove artifact / verify references |

---

# Recommended next work order

No code changes were made in this audit. The next implementation should be narrow and test-first.

## Package A — contract registry closure

1. Register or explicitly internalize:
   - `CMD:POSITION_POLICY_SIDECAR_CLOSE_REQUEST`
   - `EVT:BRACKET_PLACEMENT_FAILED`
   - `EVT:POSITION_POLICY_SIDECAR_CLOSE_REQUEST_STATE`
2. Reconcile `CMD:EXTERNAL_OPEN_REQUEST_V1` / `EVT:EXTERNAL_OPEN_REQUEST_REJECTED_V1` into `domain_dict`.
3. Update stale docs.

Validation:
- registry/domain/source/schema consistency test.

## Package B — execution safety guardrails

Tests first:
1. missing instrument config rejects `CMD:OPEN`;
2. close submission build failure clears `_closing_position`;
3. guardian cleanup exception clears `_closing_position`;
4. no-loop DEC emits terminal failure;
5. cleanup loop cancels cleanly.

## Package C — bracket race hardening

Tests first:
1. SL success + TP failure under parallel gather;
2. TP success + SL failure;
3. in-flight sibling still running while fallback starts;
4. retry only failed/unknown side after reconcile.

## Package D — truth hardening config fail-closed

Tests first:
1. malformed hardening config fails startup or explicit disable required;
2. disabled hardening must be explicit config state, not exception side effect.

---

# Done / not done

```yaml
research_plan_static_phases_completed: true
code_changed: false
tests_run: false
runtime_logs_checked: false
root_causes_proven_by_runtime: false
defect_candidates_localized: true
next_step: test-first implementation packages
```
