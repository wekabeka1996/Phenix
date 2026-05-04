# EXECUTION_POSITION_CROSS_MODEL_REVIEW_1DE

## Scope
Input reviewed: external model `1De` summary.  
Method: read-only cross-check against `/mnt/data/execution_position.zip` extracted source.  
No code changes. No runtime logs. No tests.

## Verdict
`1De` is useful mostly as a **maintainability / decomposition-debt audit**, not as a pure runtime-defect report.

It correctly points to:
- schema duplication around sidecar `peak_giveback_snapshot`,
- open-command schema overlap,
- real BOUNDARY_POLICY deferred violations,
- real hardcoded instrument constants in `contracts.py`,
- weak typing via `Dict[str, Any]`,
- guardian-bridge duplication,
- dormant metrics infrastructure,
- `metrics_aggregator.py` not wired into the main FSM path.

But it overstates some claims:
- JSON schemas are 28 in this zip, not 29.
- `peak_giveback_snapshot` appears in 5 JSON schemas, not 7, by direct grep.
- `bracket_manager` TP widen bps and retry backoff are read from config, not pure hidden magic constants.
- `close_executor` tracked teardown cancel already uses `asyncio.gather(..., return_exceptions=True)`, so the blanket claim “sequential cancellation instead of gather” is not valid for the active tracked-teardown path.
- `Dict[str, Any]` is real debt, but not automatically P1 unless it crosses a money-impacting boundary without schema validation.

## Coverage
```yaml
zip_python_files: 69
json_files_found: 28
markdown_files_found: 9
runtime_logs_checked: 0%
tests_run: 0
code_changed: false
```

---

## Claim review

### 1. Contracts / JSON schemas

#### Confirmed
- There is repeated `peak_giveback_snapshot` schema structure across sidecar schemas.
- Direct grep found it in:
  - `position_policy_sidecar_scores_v1.json`
  - `position_policy_sidecar_suppressed_v1.json`
  - `cmd_position_policy_sidecar_close_request_v1.json`
  - `position_policy_sidecar_evaluated_v1.json`
  - `position_policy_sidecar_recommended_v1.json`
- `cmd_open_v1.json`, `dec_open_v1.json`, and `cmd_external_open_request_v1.json` are related open-command surfaces and should be checked for intentional divergence.

#### Correction
- 1De says 29 JSON schemas; zip contains 28 `.json` files.
- 1De says `peak_giveback_snapshot` repeats in 7 schemas; direct grep found 5 occurrences with that exact key.

#### Severity
- P2 maintainability / contract drift risk.
- Not an immediate runtime defect unless schema drift is demonstrated.

#### Recommendation
Add shared schema definitions via `$defs` / `$ref` for sidecar peak-giveback block, but do it as a contract package with snapshot tests.

---

### 2. Core execution managers

#### Confirmed
- `bracket_health.py` directly accesses `self._fsm._bracket_ownership.*` in several places.
- `startup_reconstruction.py` directly accesses `self._fsm._startup_truth_orchestrator._append_restart_truth_record`.
- `BOUNDARY_POLICY.md` explicitly forbids these cross-peer accesses and lists several deferred historical violations.
- `bracket_ownership.py` returns `Dict[str, Any]` for owner-resolution methods.
- `close_executor._resolve_close_position_truth()` uses `Decimal("0")` in no-position/unresolved branches, but it wraps this inside a classification object, so the real safety depends on whether all callers respect classification.
- `close_executor.py` uses fallback `rid = "manual-close"` and `idempotent_key or rid or "manual-close"`.

#### Partially confirmed / corrected
- `bracket_manager` TP widen bps and retry backoff are **not purely hidden constants**. The code reads:
  - `domains.execution_position.bracket_placement.tp_widen_first_bps`
  - `tp_widen_second_bps`
  - `retry_backoff_ms`
  This aligns with YAML/Pydantic SSOT better than 1De implies.
- The claim “sequential bracket cancellation instead of gather” is not valid for the tracked close teardown path: `close_executor._execute_tracked_close_teardown()` builds cancel tasks and executes them with `asyncio.gather(..., return_exceptions=True)`.

#### Severity
- Boundary violations: P2 architectural debt.
- `manual-close` fallback identity: P2, because fallback identity can collapse unrelated manual closes if idempotency is weak.
- close truth `Decimal("0")`: P2/P3, because classification may protect it, but tests should prove callers never treat unresolved as valid flat.

---

### 3. Adapters / bridges

#### Confirmed
- Guardian cancel bridge modules repeat the same pattern: request model, clean string helpers, trace-ref builder, `adapt_to_dec_cancel` function.
- There is real boilerplate duplication across:
  - `guardian_background_orphan_cancel_bridge.py`
  - `guardian_old_bracket_cleanup_bridge.py`
  - `guardian_old_entry_cleanup_bridge.py`
  - `tracked_close_teardown_cancel_bridge.py`
  - `reconcile_close_cancel_bridge.py`
- Contract path strings and trace status strings are hardcoded in the bridge modules.

#### Interpretation
This is a maintenance-risk finding, not necessarily a runtime defect. A generic base class could reduce duplication, but broad abstraction here may also make cancel contracts less explicit. Safer first step is shared helper functions + contract tests, not a large bridge framework.

#### Severity
- P3 unless a drift bug is demonstrated.
- P2 if registry/schema/source mismatch exists for one of these bridges.

---

### 4. Infrastructure and mixins

#### Confirmed
- `fsm_manage.py` has `_bar_ms = 15 * 60 * 1000` before trying to override from `aurora.decision.bar_gating.bar_ms`.
- `ConfigResolverMixin` uses hardcoded canonical config paths, but many of these are intentional fail-closed SSOT paths, not automatically bad.
- `metrics_aggregator.py` contains `MetricAggregator` and `StructuredMetricsLogger`; grep found no main FSM import/use for them.

#### Correction
- Hardcoded config paths are not necessarily a defect. In this project, canonical YAML/Pydantic paths are expected. The defect exists only when there is fallback to legacy/non-SSOT paths or silent defaults.

#### Severity
- `_bar_ms` default: P2/P3 depending on whether aurora bar_gating can be missing in active configs.
- dormant metrics aggregator: P3 dead/dormant code.

---

### 5. Domain contracts / math helpers

#### Confirmed
- `contracts.py` defines global constants:
  - `MIN_ORDER_QTY = Decimal("0.001")`
  - `MIN_NOTIONAL = Decimal("10.0")`
  - `QTY_STEP = Decimal("0.001")`
  - `PRICE_STEP = Decimal("0.01")`
- These constants are used in `OrderPayload` validation/quantization.
- The project-level true instrument constraints should come from `instruments.yaml` / Pydantic SSOT, so these constants are dangerous if used in active open execution.
- `qty_normalizer.py` defines local NRR constants instead of importing all reason codes from a single canonical reason module.
- `soft_clip.py` Pydantic config fields are float, then converted to `Decimal(str(...))`.

#### Interpretation
This aligns with earlier finding: missing instrument config fallback / generic constants are a real P1/P2 risk if active path can use them.

#### Severity
- Global instrument constants as active fallback: P1/P2.
- local NRR constants: P2/P3 taxonomy drift risk.
- float config for soft limits: P3 unless precision-sensitive threshold defect is shown.

---

### 6. Ledger / persistence

#### Confirmed
- `ledger_store_adapter.py` `_upsert_order()` links brackets through `entry_client_id` or `parent_entry_id` if available.
- `OrderGuardian.register_bracket()` and `ledger.register_order()` provide other registration paths.

#### Interpretation
1De's “illusion” claim is plausible but not proven as a runtime defect. The system has multiple registration paths by design. The defect would be: same bracket registered through two paths with divergent parent identity and no reconciliation. That requires focused test/log proof.

#### Severity
- P2 unproven split-brain candidate.

---

### 7. Analytics / observability

#### Confirmed
- `metrics_collector.py` is wired into `fsm.py` / `fsm_open.py`.
- `metrics_aggregator.py` appears dormant in this zip; no direct main-flow imports found.
- `StructuredMetricsLogger` is defined but not found as integrated into main FSM flow.
- `defer_rate` and `block_rate` are computed inside `MetricsCollector`; direct downstream external consumption was not proven from this zip.
- `drift_monitor.py` appears not wired as a main active path in the extracted package.

#### Severity
- P3 dead/dormant observability code.
- P2 if operator dashboards depend on these metrics while they are not wired.

---

### 8. Boundary policy

#### Confirmed
`BOUNDARY_POLICY.md` is active and explicitly names deferred violations, including:
- `fill_ingress_coordinator -> self._fsm._evt_handlers`
- `fill_ingress_coordinator -> self._fsm._latest_portfolio_state`
- `fill_ingress_coordinator -> self._fsm._latest_portfolio_position_amt`
- `startup_truth_orchestrator -> internal portfolio event trace maps`
- all modules -> `_emit_execution_bus_event`

Direct code grep confirms current private back-ref reads in `fill_ingress_coordinator.py`, `bracket_health.py`, and `startup_reconstruction.py`.

#### Severity
- P2 architecture boundary debt.
- Not automatically P1 because the policy labels some accesses as historical/deferred and read-only, but it must be closed before further decomposition.

---

## What should be merged into master backlog

```yaml
Package Q:
  name: SCHEMA_DEDUP_REFS_SIDECAR
  goal:
    - factor repeated peak_giveback_snapshot into shared schema definitions
    - add schema snapshot tests

Package R:
  name: BOUNDARY_POLICY_DEFERRED_VIOLATIONS_CLOSURE
  goal:
    - replace direct self._fsm._bracket_ownership access with FSM-level delegators
    - replace startup_truth_orchestrator direct append access with public delegator
    - address fill_ingress_coordinator private cache reads or explicitly sanction read-only delegates

Package S:
  name: MANUAL_CLOSE_IDENTITY_HARDENING
  goal:
    - eliminate broad rid/idempotency fallback to "manual-close"
    - require explicit close intent identity or generate deterministic symbol-scoped idempotent key

Package T:
  name: CONTRACT_CONSTANTS_QUARANTINE
  goal:
    - ensure contracts.py generic constants are not used as active instrument SSOT
    - force execution paths to use instruments.yaml filters or fail closed

Package U:
  name: OBSERVABILITY_DORMANT_CODE_DECISION
  goal:
    - either wire metrics_aggregator / StructuredMetricsLogger deliberately
    - or mark/delete as dormant to reduce false confidence

Package V:
  name: LEDGER_REGISTRATION_PATH_CONSISTENCY_TESTS
  goal:
    - prove bracket registration via guardian, ledger adapter, and direct ledger paths cannot diverge on parent identity
```

## Updated priority impact
1De does **not** supersede the P1 runtime safety backlog from 1G/2G. It adds a second lane:

- Lane A: runtime safety defects — bracket race, watchdog partial fills, close flag, flip sizing, no-loop DEC, strict intake.
- Lane B: architecture/contract hygiene — schema refs, boundary policy closure, dormant metrics, generic contract constants, bridge duplication.

Recommended sequencing: finish Lane A first, then Lane B, except `CONTRACT_CONSTANTS_QUARANTINE` because it overlaps with active open-path safety.
