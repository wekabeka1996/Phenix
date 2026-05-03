# EXECUTION_POSITION SSOT FREEZE & REFACTOR SPEC v1

**Status:** Engineering specification / implementation governance artifact  
**Scope:** `apps/reference/domains/execution_position`  
**Mode:** repair-first, refactor-second, folderization-after-safety  
**Code changes in this document:** none  
**Intended next use:** issue/task prompts for coding agents

---

## 0. Executive verdict

`execution_position` should not be repaired through a broad rewrite.

The real problem is not just “many files in one folder”. The real problem is that the domain currently mixes several different responsibilities in a flat namespace:

1. execution truth,
2. lifecycle orchestration,
3. exchange submission,
4. bracket protection,
5. guardian cleanup,
6. restart/restore truth,
7. exposure limits,
8. position-policy sidecar behavior,
9. telemetry/metrics,
10. schemas/contracts.

This creates three classes of risk:

- **runtime safety risk**: duplicate brackets, duplicate partial fills, stuck close state, bad exposure math;
- **contract risk**: event/schema/registry drift, `extra="ignore"`, untyped payloads, missing fail-closed config;
- **maintenance risk**: flat folder, peer-private access, schema duplication, dormant code.

Therefore the implementation must follow this order:

```text
contract freeze
  -> ingress/config fail-closed
  -> execution safety
  -> state/fill/restore consistency
  -> risk math
  -> sidecar action contract
  -> boundary/typing cleanup
  -> physical folder skeleton
  -> schema dedup/dead-code cleanup
  -> SSOT Freeze acceptance
```

Physical folderization is required, but **not before money-impacting defects are pinned with tests**.

---

## 1. Non-negotiable laws

These are implementation laws for every package.

### LAW-1 — No big-bang migration
Never refactor the whole domain at once. Each package touches one failure class.

### LAW-2 — Runtime truth before architecture aesthetics
Do not move files, rename abstractions, or introduce base classes before the hot-path behavior is protected by regression tests.

### LAW-3 — YAML + Pydantic are SSOT
No hidden execution constants. No generic fallback values for instrument precision, quantities, notional, TTL, sidecar thresholds, retry count, or live/testnet mode.

### LAW-4 — Contract-first
Any event/command that can be emitted must exist in:

- `verb_registry_v1.yaml`
- domain dictionary / exported surface
- JSON schema where applicable
- tests proving payload shape

### LAW-5 — Fail closed on unknown execution truth
Missing config, missing instrument, corrupt WAL, unknown close state, unknown bracket lineage, unknown idempotency key, or stale context must not silently proceed.

### LAW-6 — Restore is not replay
Authoritative restore may apply saved state, but must preserve exact / reconstructed / unknown boundaries. It must not pretend to be normal FSM transition history.

### LAW-7 — No split-brain lifecycle ownership
`execution_position` owns execution/order/bracket lifecycle truth. Sidecar may evaluate/recommend/request via bounded mediator, but must not become a hidden second execution owner.

### LAW-8 — Done means report + validation
A package is complete only with:

- changed files,
- exact test commands,
- outputs,
- what is proven,
- what remains unproven,
- rollback risk,
- follow-up debt.

---

## 2. Evidence-bounded consensus from all audits

### Strong consensus: must fix first

The following defects were repeatedly identified by multiple audits and by direct zip review:

1. **Bracket partial-success race**
   - SL succeeds, TP fails, fallback can retry both.
   - Risk: duplicate protective orders or orphan protective state.

2. **Watchdog repeated partial-fill emission**
   - `PARTIALLY_FILLED` with unchanged cumulative qty can emit repeated `TRADE_EXECUTED`.
   - Risk: false position/trade accounting.

3. **Open-intake `extra="ignore"`**
   - Unknown money-impacting fields can be silently dropped.
   - Risk: bad payload looks valid.

4. **Missing instrument config fallback**
   - Generic constants can act as fake instrument SSOT.
   - Risk: wrong qty/price/min-notional behavior.

5. **Exposure flip size blindness**
   - Opposite-side tiny order can be treated as full flip.
   - Risk: false exposure relief.

6. **Close `_closing_position` lifecycle fragility**
   - Early failure path can leave close-in-progress state stuck or clear too early.
   - Risk: blocked lifecycle or duplicate close pressure.

7. **Pending bracket WAL corruption is too quiet**
   - Corrupt rows cannot be silently skipped in restore-critical path.
   - Risk: startup with incomplete bracket truth.

8. **No-loop async DEC outcome**
   - WAL may record DEC while exchange action is not scheduled.
   - Risk: decision truth without terminal execution truth.

9. **Adapter mode/credential fallbacks**
   - Live-like config must not silently become `testnet` or `shadow_mode`.
   - Risk: operator thinks execution is live/testnet while actual mode differs.

10. **Contract registry drift**
    - Existing action-bearing surfaces must be registered and schema-backed.

### Strong consensus: important but second wave

1. Boundary policy violations.
2. `Dict[str, Any]` overuse.
3. Schema duplication.
4. Dormant metrics/aggregator code.
5. Guardian bridge duplication.
6. Broad folder reorganization.

These matter, but they should follow safety closure.

---

## 3. Target architecture skeleton

### 3.1 Current problem

The flat folder makes every module look peer-level even when responsibilities differ. This hides ownership boundaries and makes accidental private access easy.

### 3.2 Target folder tree

The final domain should look like this:

```text
apps/reference/domains/execution_position/
  __init__.py
  README.md
  BOUNDARY_POLICY.md

  contracts/
    __init__.py
    messages.py
    reasons.py
    numeric.py
    event_names.py
    registry_audit.py
    schemas/
      *.json
      common/
        peak_giveback_snapshot_v1.json
        base_order_identity_v1.json
        base_open_order_v1.json

  orchestration/
    __init__.py
    fsm.py
    flow_result.py
    async_scheduling.py
    lifecycle_facade.py
    startup_wiring.py

  flows/
    __init__.py

    open/
      __init__.py
      fsm_open.py
      trade_intent_open_intake.py
      intent_router.py
      entry_manager.py
      open_executor.py
      open_submission_adapter.py
      open_dispatch_adapter.py
      external_intent_intake.py

    manage/
      __init__.py
      fsm_manage.py
      bracket_manager.py
      bracket_math.py
      bracket_health.py
      bracket_ownership.py
      pending_brackets_wal.py
      manage_max_hold_close_bridge.py

    close/
      __init__.py
      fsm_close.py
      close_executor.py
      close_submission_adapter.py
      close_producer_bridge.py
      reconcile_close_cancel_bridge.py
      tracked_close_teardown_cancel_bridge.py

  guardian/
    __init__.py
    order_guardian.py
    idempotent_cancel.py
    cancel_submission_adapter.py
    cancel_bridge_utils.py
    guardian_background_orphan_cancel_bridge.py
    guardian_old_bracket_cleanup_bridge.py
    guardian_pre_close_cleanup_bridge.py

  state/
    __init__.py
    order_index.py
    order_ledger.py
    ledger_store_adapter.py
    restore_artifact.py
    authoritative_restore_apply.py
    startup_reconstruction.py
    startup_truth_orchestrator.py
    truth_hardening.py

  guards/
    __init__.py
    exposure_guard.py
    exposure_manager.py
    soft_clip.py
    qty_normalizer.py
    leverage_config.py
    leverage_service.py
    bootstrapping/
      __init__.py
      leverage_bootstrapper.py

  sidecar/
    __init__.py
    position_policy_sidecar.py
    position_policy_mediator.py
    schemas/

  telemetry/
    __init__.py
    aurora_log_adapter.py
    metrics_collector.py
    metrics_aggregator.py
    health_metrics.py
    drift_monitor.py
    intent_boundary_audit.py

  adapters/
    __init__.py
    adapter_init.py
    exchange_submission.py

  support/
    __init__.py
    stopprice_validation.py
```

Note: the accepted Phase 8/9 skeleton retained root `utils.py` as an intentional root anchor and moved `stopprice_validation.py` under `support/`. Do not create `execution_position/utils/`.

### 3.3 Ownership rules by folder

| Folder | Owns | Must not own |
|---|---|---|
| `contracts/` | schemas, event names, reason constants, numeric validators | runtime execution |
| `orchestration/` | top-level FSM routing, lifecycle sequencing, async task ownership | exchange-specific logic |
| `flows/open/` | intent intake to entry order | risk policy beyond execution guards |
| `flows/manage/` | active position management and brackets | entry decision-making |
| `flows/close/` | close command to close execution | strategy/policy reasoning |
| `guardian/` | cleanup/cancel/orphan reconciliation | bracket math ownership |
| `state/` | ledger, restore, restart truth, order index | business policy |
| `guards/` | exposure, qty, leverage, soft-clip | exchange submission |
| `sidecar/` | open-position policy evaluation + bounded request | execution truth mutation |
| `telemetry/` | metrics, drift, forensic logs | business decisions |
| `adapters/` | exchange adapter setup/submission seam | lifecycle policy |
| `utils/` | pure helpers only | stateful execution |

### 3.4 Physical move policy

File moves happen only after safety packages are complete.

Migration method:

1. create target folders;
2. move one semantic group at a time;
3. leave compatibility re-export stubs at old import paths;
4. update imports within the domain;
5. run import graph tests;
6. remove stubs only after external call sites are updated.

---

## 4. Implementation phases

## Phase 0 — SSOT Freeze Baseline and issue ledger

### Goal
Create the single accepted defect ledger and freeze implementation order.

### Work
- Create `EXECUTION_POSITION_SSOT_FREEZE_PLAN.md`.
- Create `reports/execution_position_defect_ledger.md`.
- Classify findings:
  - P0 = cannot trade safely;
  - P1 = money-impacting defect candidate;
  - P2 = contract/architecture debt;
  - P3 = cleanup/maintenance.
- Mark which findings are:
  - proven by static code;
  - proven by failing test;
  - proven by runtime logs;
  - unproven theory.

### DoD
- One canonical ledger exists.
- No duplicated issue lists across chats/models.
- Every later package references ledger IDs.

### Validation
- No code validation.
- Review-only acceptance.

---

## Phase 1 — Contract Registry Closure

### Goal
No emitted command/event exists outside registry/domain dictionary/schema truth.

### Scope
- `verb_registry_v1.yaml`
- `domain_dict.json`
- `contracts/`
- `schemas/`
- sidecar close request surfaces
- bracket failure surfaces
- external intent surfaces

### Required fixes
- Register:
  - `CMD:POSITION_POLICY_SIDECAR_CLOSE_REQUEST`
  - `EVT:POSITION_POLICY_SIDECAR_CLOSE_REQUEST_STATE`
  - `EVT:BRACKET_PLACEMENT_FAILED`
- Reconcile:
  - source emitters,
  - schemas,
  - registry,
  - domain dictionary.
- Add a static test:
  - scan `execution_position` source for emitted `CMD:`, `EVT:`, `ERR:`, `DEC:`;
  - fail if emitted surface is missing from registry/domain dictionary.

### DoD
- No unregistered emitted action-bearing surface.
- Schemas load.
- Existing tests pass.

### Tests
- `test_execution_position_registry_surface_sync.py`
- `test_execution_position_schema_loads.py`

---

## Phase 2 — Ingress and Config Fail-Closed

### Goal
Bad payloads and missing execution config fail before exchange submission.

### Scope
- `trade_intent_open_intake.py`
- `open_submission_adapter.py`
- `fsm_open.py`
- `contracts/numeric.py`
- `adapter_init.py`
- `contracts.py`
- `reasons.py`

### Required fixes

#### 2.1 Strict open intake
- Change `extra="ignore"` to `extra="forbid"` on money-impacting Pydantic models.
- Unknown payload fields reject.

#### 2.2 Decimal parsing
- Replace brittle regex-only numeric validation with Decimal parser:
  - accept `"1E-7"` if finite and positive where allowed;
  - reject `NaN`, `Infinity`, negative qty, empty string.

#### 2.3 Instrument SSOT
- If `config.instruments.<symbol>` missing:
  - raise config contract error;
  - do not fallback to `MIN_ORDER_QTY`, `MIN_NOTIONAL`, `QTY_STEP`, `PRICE_STEP`.
- Keep generic constants only for tests or explicit legacy compatibility; not active execution.

#### 2.4 Adapter mode fail-closed
- No implicit `"testnet"` fallback in live-like modes.
- No silent `shadow_mode=True` unless config explicitly permits simulation/degraded mode.

#### 2.5 Idempotency
- If idempotent key is required for order submission, missing key rejects before adapter call.
- No fallback to timestamp as idempotency identity.

### DoD
- Typos in payload keys fail.
- Scientific numeric notation accepted when semantically valid.
- Missing instrument config fails closed.
- Live/hybrid missing credentials fails before trading.
- No exchange call occurs without required idempotency key.

### Tests
- `test_open_intake_extra_forbid.py`
- `test_decimal_numeric_contracts.py`
- `test_fsm_open_missing_instrument_fail_closed.py`
- `test_adapter_init_mode_fail_closed.py`
- `test_open_submission_idempotent_key_required.py`

---

## Phase 3 — Execution Safety Guardrails

### Goal
Prevent duplicate protective orders, phantom fills, stuck close state, and unobserved async failure.

### Scope
- `bracket_manager.py`
- `watchdog.py`
- `close_executor.py`
- `fsm.py`
- `async_scheduling.py`
- `order_guardian.py`

### Required fixes

#### 3.1 Bracket partial-success handling
Current danger:
- `asyncio.gather(..., return_exceptions=False)` may throw on one side while the other side has succeeded or is in flight.
- Fallback may retry both.

Required behavior:
- use `return_exceptions=True`;
- classify SL and TP independently;
- if one side succeeded and the other failed:
  - either rollback successful sibling;
  - or reconcile by client order ID before retrying failed side only;
- never blindly retry both sides.

#### 3.2 Watchdog partial-fill incrementality
- Track last cumulative executed quantity per order.
- Emit `TRADE_EXECUTED` only for positive delta.
- If status unchanged and cumulative qty unchanged, suppress duplicate fill event.

#### 3.3 Close-in-progress lifecycle
- `_closing_position` must be set/cleared in one owner path.
- Any early return after setting it must clear it or record terminal close failure.
- Close flag should clear only after all required close/bracket terminal conditions are known.

#### 3.4 Cleanup task cancellation
- `asyncio.CancelledError` must be re-raised or break loop.
- No immortal cleanup loops.

#### 3.5 No-loop DEC terminal failure
- If WAL records DEC but async loop is unavailable, emit terminal failure/reject.
- Do not leave DEC-only truth.

### DoD
- SL success + TP fail does not create duplicate SL/TP.
- Repeated partial-fill poll emits no duplicate trade event.
- Close build failure clears/settles close-in-progress state.
- Cleanup loop cancellation terminates.
- No-loop DEC path has explicit terminal truth.

### Tests
- `test_bracket_parallel_partial_success_no_duplicate.py`
- `test_watchdog_partial_fill_delta_only.py`
- `test_close_executor_closing_flag_cleared_on_build_failure.py`
- `test_cleanup_loop_cancel_terminates.py`
- `test_process_flow_result_no_loop_terminal_failure.py`

---

## Phase 4 — Exposure and Risk Math

### Goal
Exposure math becomes size-aware and Decimal-safe.

### Scope
- `exposure_manager.py`
- `exposure_guard.py`
- `soft_clip.py`
- `qty_normalizer.py`

### Required fixes

#### 4.1 Size-aware flip
- `is_flip` cannot be side-only.
- Compute actual net exposure delta:
  - if opposite order smaller than current position, it reduces exposure only by its own size;
  - if larger, it closes current and opens residual opposite exposure.

#### 4.2 Directional ratio safety
- Clamp post-subtraction directional margin to zero.
- No negative denominator / skipped ratio check behavior.

#### 4.3 Decimal-only finance math
- Remove `float()` casts from notional/margin comparisons.
- Use Decimal end-to-end.

#### 4.4 Soft clip truth
Two allowed outcomes:
- implement true solver for maximum allowed qty;
- or rename/document current zeroing as hard directional clamp.

No pretending hard-zero is proportional soft clipping.

### DoD
- Tiny opposite-side order cannot free full exposure.
- Large flip over limit is blocked.
- Decimal tests pass without float drift.
- Soft-clip behavior is either mathematically proportional or honestly named.

### Tests
- `test_exposure_flip_tiny_opposite_does_not_free_full_margin.py`
- `test_exposure_flip_large_residual_checked.py`
- `test_exposure_decimal_no_float_shadow_notional.py`
- `test_soft_clip_solver_or_hard_clamp_contract.py`

---

## Phase 5 — State, Restore, and Fill Identity

### Goal
No silent restore corruption, partial-fill amnesia, or ledger abstraction leak.

### Scope
- `pending_brackets_wal.py`
- `order_guardian.py`
- `ledger_store_adapter.py`
- `event_handlers.py`
- `fill_ingress_coordinator.py`
- `authoritative_restore_apply.py`

### Required fixes

#### 5.1 Corrupt WAL visibility
- `json.JSONDecodeError` cannot be silent.
- Choose one policy:
  - fail startup with `CriticalStartupError`;
  - or quarantine corrupt WAL and emit degraded restore event.
- Policy must be YAML/Pydantic controlled if configurable.

#### 5.2 Guardian store protocol
- No private `store._data` access.
- Add `StoreProtocol.get_all_tracked_symbols()`.
- Implement for in-memory and SQLite/ledger store.

#### 5.3 Partial-fill metadata retention
- Do not `pop` pending entry metadata while fill status is `PARTIALLY_FILLED`.
- Clear only on terminal fill/cancel/reject/expire.

#### 5.4 Fill dedupe without tradeId
- If `tradeId` missing, dedupe key must include enough execution proof:
  - order id,
  - symbol,
  - cumulative qty or fill qty,
  - event timestamp / update time,
  - side/order role where needed.
- Do not collapse distinct partial fills.

#### 5.5 Restore apply doctrine
- Direct state assignment allowed only inside explicit restore-apply seam.
- Add comments/tests proving restore apply preserves exact/reconstructed/unknown.

### DoD
- Corrupt WAL startup behavior deterministic.
- Guardian symbol discovery works in both stores.
- Partial fills keep metadata.
- Multiple no-tradeId partial fills not collapsed.
- Restore apply does not pretend to be normal transition.

### Tests
- `test_pending_brackets_wal_corrupt_row_policy.py`
- `test_order_guardian_store_protocol_symbols.py`
- `test_partial_fill_keeps_pending_entry_meta.py`
- `test_fill_dedupe_without_trade_id_distinguishes_partials.py`
- `test_authoritative_restore_apply_exact_unknown_boundary.py`

---

## Phase 6 — Sidecar Action-Bearing Contract

### Goal
Sidecar action behavior becomes explicit, registered, bounded, and non-spammy.

### Scope
- `position_policy_sidecar.py`
- `position_policy_mediator.py`
- sidecar schemas
- registry/domain dictionary
- sidecar config

### Required fixes
- Ensure `disable`, `shadow`, `enable` semantics are tested.
- `shadow` must not emit close command.
- `enable` may emit close request only if:
  - freshness valid;
  - position active;
  - not close-in-progress;
  - duplicate signature not repeated;
  - mediator accepts ownership state.
- Sidecar close request must be registered/schema-backed.
- Sidecar must not mutate execution truth directly.

### DoD
- Operator can know from config whether sidecar is action-bearing.
- No repeated micro-event close spam.
- No close request during incumbent close lifecycle.
- Event registry and schemas match emitted payloads.

### Tests
- `test_sidecar_modes_disable_shadow_enable.py`
- `test_sidecar_no_close_when_close_in_progress.py`
- `test_sidecar_duplicate_close_suppression.py`
- `test_position_policy_mediator_contract.py`

---

## Phase 7 — Boundary Policy and Typing Hygiene

### Goal
Remove decomposition rot after hot-path safety is stabilized.

### Scope
- `BOUNDARY_POLICY.md`
- `bracket_health.py`
- `startup_reconstruction.py`
- `fill_ingress_coordinator.py`
- `bracket_ownership.py`
- `order_guardian.py`
- `exposure_guard.py`
- `close_executor.py`

### Required fixes

#### 7.1 Peer-private access
Replace direct peer private access with:
- FSM delegate methods;
- protocols;
- typed facades.

Examples:
- `self._fsm._bracket_ownership.*` -> FSM bracket ownership delegates.
- `self._fsm._startup_truth_orchestrator.*` -> FSM startup truth delegate.
- direct `_latest_portfolio_state` -> sanctioned read-only accessor.

#### 7.2 Typed structures
Replace highest-risk `Dict[str, Any]` returns with dataclasses/TypedDicts:
- `BracketOwnerResolution`
- `TerminalBracketContext`
- `ExposureCheckResult`
- `ClosePositionTruth`
- `StoreSymbolSnapshot`

#### 7.3 AST boundary test
Add static test that fails on new private peer access.

### DoD
- No new boundary policy violations.
- Deferred violations either closed or explicitly sanctioned.
- Changed surfaces typed.

### Tests
- `test_execution_position_boundary_policy_ast.py`
- mypy/pyright on changed modules if project supports it
- focused integration tests for affected delegates

---

## Phase 8 — Physical Architecture Skeleton Migration

### Goal
Move from flat folder to semantic folders without behavior changes.

### Scope
All source files, imports, tests.

### Migration rules
- No behavior changes in this phase.
- Move one folder group per PR.
- Preserve old import paths with compatibility re-export stubs.
- Update internal imports to new paths.
- Run full domain tests after each group.

### Move order
1. `contracts/`
2. `guards/`
3. `guardian/`
4. `state/`
5. `flows/open/`
6. `flows/manage/`
7. `flows/close/`
8. `sidecar/`
9. `telemetry/`
10. `orchestration/`
11. remove compatibility stubs only after external import audit

### DoD
- Import graph passes.
- Domain tests unchanged.
- No changed runtime behavior.
- Folder README files document ownership.

### Tests
- `test_execution_position_imports.py`
- `test_no_old_path_imports_after_migration.py`
- existing domain regression suite

---

## Phase 9 — Schema Dedup and Dead Code Cleanup

### Goal
Clean technical debt only after safety and skeleton are stable.

### Scope
- JSON schemas
- dormant metrics modules
- dead comments/stubs
- bridge duplication

### Required fixes
- Shared `$defs` / `$ref` for repeated schema blocks.
- Remove true dead code only after import/call-site proof.
- Do not delete shadow-only tools unless intentionally retired.
- Bridge dedup only via small helpers first, not giant inheritance tree.

### DoD
- Schemas validate.
- Removed code has import graph proof.
- No behavior change unless intentionally documented.

### Tests
- schema validator tests
- import graph tests
- existing domain regression suite

---

## Phase 10 — SSOT Freeze Acceptance

### Goal
Declare `execution_position` structurally frozen enough for next MetaFSM2 cutover selection or formal contour modeling.

### Acceptance gates

#### Contract gate
- No emitted event/command missing registry/schema/domain dictionary.
- No active schema/runtime drift.

#### Config gate
- No active business fallback outside YAML/Pydantic.
- Missing critical config fails closed.

#### Execution gate
- Open path, bracket path, close path, guardian path, watchdog path have focused regression tests.

#### State gate
- Restore exact/reconstructed/unknown boundary preserved.
- WAL corruption behavior deterministic.
- Fill dedupe and partial fill semantics proven.

#### Risk gate
- Exposure flip size-aware.
- Decimal-only notional/margin math on touched surfaces.
- Soft-clip semantics truthful.

#### Architecture gate
- Folder skeleton installed.
- Boundary policy test active.
- No unsanctioned peer-private access.

#### Observability gate
- Every fail-closed branch has reason and forensic record.
- No critical `except Exception: pass`.

#### Report gate
- Final report lists:
  - packages completed;
  - tests;
  - remaining residual debt;
  - risks;
  - whether Phase 7 cutover target selection is now allowed.

### Final status values
Allowed final verdicts:

```yaml
SSOT_FREEZE_ACCEPTED:
  meaning: domain is ready for first contour cutover selection

SSOT_FREEZE_ACCEPTED_WITH_RESIDUALS:
  meaning: remaining debt is non-blocking and documented

SSOT_FREEZE_BLOCKED:
  meaning: at least one critical gate failed
```

---

## 5. First coding package prompt

Use this when starting implementation.

```text
You are repairing Aurora/Phenix `execution_position`.

Mode: Engineering / Forensic.
Do not perform broad refactor.
Do not move files.
Do not touch bracket/risk/sidecar behavior yet.

Package:
PHASE 1 — CONTRACT REGISTRY CLOSURE + PHASE 2.1 STRICT OPEN INTAKE ONLY

Goal:
1. Prove current emitted EP surfaces are registered/schema-backed or report drift.
2. Patch only the strict open-intake contract if tests prove `extra="ignore"` exists.

Required workflow:
1. Read current registry/domain_dict/schema/source emitters.
2. Build a small emitted-surface inventory for execution_position.
3. Add focused tests for unregistered emitted events/commands if feasible.
4. Add failing regression test for unknown extra field in TradeIntentOpenIntake/TradeIntentOpenOrder.
5. Patch to `extra="forbid"` only if test proves current permissiveness.
6. Run focused tests.
7. Do not change unrelated files.
8. Produce AGENT_REPORT.

Acceptance:
- unknown open-intake fields fail closed;
- no code claims are made without tests;
- any registry drift is documented or patched with schema/domain_dict sync;
- report includes files changed, tests run, proven facts, unproven risks.
```

---

## 6. What must not happen

- Do not start by deleting dead code.
- Do not start by moving files.
- Do not create a giant `BaseGuardianCancelBridge` before safety packages.
- Do not silently change close qty semantics without a test proving expected behavior.
- Do not make sidecar more action-capable while sidecar contract is unresolved.
- Do not claim “fixed” from static reading.
- Do not let folderization hide behavior changes.
