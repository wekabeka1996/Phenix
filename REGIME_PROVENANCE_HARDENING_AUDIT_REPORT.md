# REGIME_PROVENANCE_HARDENING_AUDIT_REPORT

**Date:** 2026-04-16
**Auditor:** GitHub Copilot (Claude Sonnet 4.6)
**Subject:** Regime Provenance Hardening Package — Code Diff, Duplication, Test Adequacy, and Acceptance Gate

---

## 1. Executive Verdict

**VERDICT: REJECT**

The regime provenance hardening logic itself is technically sound and the focused tests are green. However, the package **cannot be accepted as submitted** for the following terminal reasons:

1. **The package is not committed.** All changes exist only in the working tree (unstaged + untracked). There is no verifiable commit boundary. Clean isolation is impossible.
2. **Major undeclared scope violation.** `apps/reference/domains/decision_making/aurora_decision.py` has a 627-line diff. Only ~25 lines are regime provenance. The remaining ~600 lines are an **objective engine refactoring** (replacing `evaluate_objective` + `build_*_input` with `evaluate_objective_gate` + adapter classes) that is **not mentioned anywhere in the report**.
3. **Second major undeclared scope violation.** `apps/reference/domains/decision_making/mean_reversion_handler.py` has a 720-line diff. Only ~50 lines are regime provenance. The remaining ~670 lines are a `runtime_readiness_builder` integration refactoring, also not mentioned.
4. **Two new modules are staged but not reported.** `objective_gate_evaluator.py` and `runtime_readiness_builder.py` are staged as new files (`A ` in git status) and are not mentioned in the report. These modules are imported by the "provenance" changes in `aurora_decision.py` and `mean_reversion_handler.py`.
5. **The report misrepresents the true scope.** Claiming "narrow additive hardening" while omitting the objective engine refactoring and runtime readiness builder changes is a material reporting failure.

The pure provenance components — `runtime_regime_layers.py`, `regime_detector.py`, and the provenance call in `feature_engineering.py` — are architecturally sound and could be cherry-picked into a legitimate, narrow package. But the submitted package as a whole is not narrow.

---

## 2. Evidence Inspected

| Source | Method | Status |
|--------|--------|--------|
| `REGIME_PROVENANCE_HARDENING_REPORT.md` | Read in full | Done |
| `git diff apps/reference/contracts/runtime_regime_layers.py` | Full diff read | Done |
| `git diff apps/reference/domains/regime_detector/regime_detector.py` | Full diff read | Done |
| `git diff apps/reference/domains/feature_engineering/feature_engineering.py` | Full diff read | Done |
| `git diff apps/reference/domains/decision_making/aurora_handler.py` | Full diff read | Done |
| `git diff apps/reference/domains/decision_making/aurora_decision.py` | Full diff read (627 lines) | Done |
| `git diff apps/reference/domains/decision_making/mean_reversion_handler.py` | Diff stat + partial read | Done |
| `git status --short` (all) | Full working tree status | Done |
| `pytest tests/sim/test_regime_timing_edge_cases.py tests/integration/test_regime_provenance_hardening.py tests/integration/test_pillars_quadratic_pipeline.py -v` | Executed | 16 passed, 0 failed |
| `pytest tests/domains/decision_making/test_aurora_handler.py test_cmd_process_strategy.py test_mr_bar_gating.py -v` | Executed | 35 passed, 3 skipped, 2 failed |
| `git diff tests/domains/decision_making/test_aurora_handler.py` | Full diff read | Done |
| `git status objective_gate_evaluator.py runtime_readiness_builder.py` | Staged files check | Done |

---

## 3. File-by-File Audit

### 3.1 `apps/reference/contracts/runtime_regime_layers.py`

**FACT:** +91 lines added. 100% provenance logic. New additions:
- Three string constants: `REGIME_SOURCE_SAME_BAR_DETECTOR`, `REGIME_SOURCE_CACHED_PREVIOUS_BAR`, `REGIME_SOURCE_MISSING_DETECTOR_HEARTBEAT`
- `_coerce_positive_int(value)` — safe int coercion helper
- `regime_event_ts_ms_of(payload)` — resolves ts priority chain: `regime_event_ts_ms → ts_ms → ts → bar_close_ts_ms`
- `build_regime_provenance_fields(payload, *, bar_close_ts_ms, missing_heartbeat)` — centralized provenance classifier
- `attach_regime_provenance(payload, ...)` — thin wrapper that merges provenance fields into a copied dict

**Assessment: CLEAN. Appropriate centralization. No duplication, no business constants hidden.**

Minor note: The ts priority chain (`regime_event_ts_ms → ts_ms → ts → bar_close_ts_ms`) is a silent fallback ladder. It is documented in the report but not annotated in code. At `ts_ms` and `ts`, the resolved value may be the FE bar timestamp rather than the detector event timestamp, which could misclassify `regime_same_bar` in edge cases. This is a known caveat acknowledged by the report (bar-end time domain correction). Risk: LOW.

### 3.2 `apps/reference/domains/regime_detector/regime_detector.py`

**FACT:** +11 lines. Two call sites for `attach_regime_provenance`:
- Line 479: UNCERTAIN emit path
- Line 914: Normal emit path

Both pass `bar_close_ts_ms=int(close_boundary_ts_ms)`.

**Assessment: CLEAN. Narrow, additive, correct.**

### 3.3 `apps/reference/domains/feature_engineering/feature_engineering.py`

**FACT:** +41 lines net. Changes:
- Line 765: `self.last_regime[symbol] = pld` → `self.last_regime[symbol] = dict(pld)` — **correctness fix** (prevents mutation of incoming payload)
- Lines 1970–1982: `features_close_boundary_ts_ms` computation + injected `close_boundary_ts_ms` field into `features_payload` — **provenance-supporting** (enables downstream consumers to reason about close boundary without re-deriving it)
- Lines 2237–2259: `regime_snapshot = attach_regime_provenance(regime_snapshot, bar_close_ts_ms=int(bar_close_ts))` — **core provenance call**
- Several whitespace-only reformatting changes

**Assessment: MOSTLY CLEAN.** The `dict(pld)` copy fix and `close_boundary_ts_ms` injection are not strictly provenance changes but are low-risk and defensible. The core provenance call is correct.

### 3.4 `apps/reference/domains/decision_making/aurora_handler.py`

**FACT:** ~50 effective lines for provenance. Changes:
- `SymbolState` gains 4 new fields: `regime_event_ts_ms`, `regime_source`, `regime_same_bar`, `regime_provenance_reason`
- `regime_confidence` default changed from `0.0` to `None` — **semantic change, not purely additive**
- `_validate_regime_liveness_guard`: enriches blocked details with provenance fields
- `on_regime_detected`: calls `build_regime_provenance_fields` to cache provenance in state
- Logger fix: guards `regime_confidence:.2f` with None check

**Assessment: MOSTLY CLEAN with one semantic concern.** Changing `regime_confidence` from `0.0` to `None` is a type-widening change that any downstream code doing arithmetic on `regime_confidence` without a None guard would break on. The `aurora_decision.py` adds a None guard for the objective engine path, but this means the semantic change and its guard are in two different places and tested partially. **Risk: LOW-MEDIUM.**

### 3.5 `apps/reference/domains/decision_making/aurora_decision.py`

**FACT:** 627-line diff. Only ~25 lines are regime provenance (the `build_regime_provenance_fields` call injected into features, plus `bar_close_ts_raw` variable extraction refactoring). The remaining ~600 lines are:

- **Objective engine refactoring:** Replaces `evaluate_objective(obj_input, domain_cfg, strategy_cfg)` with `evaluate_objective_gate(ObjectiveGateRequest(...))` using new adapter pattern (`ObjectiveBehaviorAdapter`, `ObjectiveSignalAdapter`, `ObjectiveSizingAdapter`, `ObjectiveStructureAdapter`, `ObjectiveGateStatus`)
- **Import surgery:** Removes `restore_execution_blocking_tokens`, `restore_status_to_readiness_status`, `apply_startup_warmup_permission_overlay`, `startup_warmup_gate_tokens`, `build_basis_bar_status_from_gap`, `build_trading_status_from_gap`, `gap_blocking_tokens`, `make_snapshot`, `partial_status`; adds `build_runtime_readiness`, `RestoreScopeSpec`, `RuntimeReadinessBuildRequest`, `RuntimePermissions`
- **`regime_confidence is None` guard** added as objective precondition — this is the only place `regime_confidence=None` is explicitly checked before objective evaluation

**Assessment: SCOPE VIOLATION. The objective engine refactoring is a separate package that was not declared in the report.** The provenance-specific change (~25 lines) is sound, but it is embedded in a much larger refactoring that changes Aurora's core decision logic path.

### 3.6 `apps/reference/domains/decision_making/mean_reversion_handler.py`

**FACT:** 720-line diff. ~50 lines are provenance (4 new per-symbol provenance dicts, 3 calls to `build_regime_provenance_fields`). The remaining ~670 lines replace the readiness-building logic using `build_runtime_readiness` from `runtime_readiness_builder`.

**Assessment: SCOPE VIOLATION.** Same pattern as aurora_decision.py. The MR handler readiness path was refactored using a new module (`runtime_readiness_builder.py`) that is not documented in the provenance report.

### 3.7 New unreported staged files

**FACT:** Two new modules exist in git index (`A `), not mentioned in the report:
- `apps/reference/domains/decision_making/objective_gate_evaluator.py` — provides `ObjectiveGateRequest`, `evaluate_objective_gate`, `ObjectiveGateStatus`
- `apps/reference/domains/decision_making/runtime_readiness_builder.py` — provides `build_runtime_readiness`, `RestoreScopeSpec`, `RuntimeReadinessBuildRequest`

Both are imported by the "provenance hardening" changes in `aurora_decision.py` and `mean_reversion_handler.py`.

**Assessment: UNDECLARED SCOPE.** These are not part of provenance hardening. They represent a separate architectural package (objective gate evaluator + runtime readiness builder refactoring) that was co-mingled with the provenance package.

---

## 4. Duplication Audit

### 4.1 Provenance classification logic

**FINDING: Centralized — NO DUPLICATION for classification.**

`build_regime_provenance_fields` in `runtime_regime_layers.py` is the single place where `same_bar_detector` / `cached_previous_bar` / `missing_detector_heartbeat` classification happens. All callers defer to this function. This is correct centralization.

### 4.2 Call-site duplication

**FINDING: MEDIUM-RISK structural debt — 5 call sites with repeated input construction pattern.**

`build_regime_provenance_fields` is called at 5 sites:

| File | Line | Input pattern |
|------|------|---------------|
| `aurora_handler.py` | 466 | `{"regime": state.regime, "regime_event_ts_ms": state.regime_event_ts_ms or state.regime_ts_ms}` + `missing_heartbeat=True` |
| `aurora_handler.py` | 575 | Full event dict passed directly |
| `aurora_decision.py` | 484 | `{"regime": state.regime, "regime_event_ts_ms": state.regime_event_ts_ms or state.regime_ts_ms}` + `missing_heartbeat=state.last_regime_heartbeat_ms is None` |
| `mean_reversion_handler.py` | 1390 | `provenance_payload` (conditional dict or passthrough) |
| `mean_reversion_handler.py` | 1883 | `regime_data` dict direct |
| `mean_reversion_handler.py` | 1910 | `{"regime": regime, "regime_event_ts_ms": ...}` |

The pattern `{"regime": state.regime, "regime_event_ts_ms": state.regime_event_ts_ms or state.regime_ts_ms}` appears at aurora_handler:466, aurora_decision:484, and MR handler:1910. This is semantic duplication — the same provenance synthesis from cached state fields, repeated three times independently.

**Risk classification: MEDIUM. Not critical, but consolidation into a helper (e.g., `build_state_provenance_fields(state, bar_close_ts_ms)`) would reduce maintenance surface.**

### 4.3 `attach_regime_provenance` vs `build_regime_provenance_fields`

**FINDING: Intentional split, not duplication.**

`attach_regime_provenance` (wraps + merges into dict) is used where a snapshot dict needs enrichment in-place (detector emit, FE cache). `build_regime_provenance_fields` (returns plain dict) is used where provenance fields are injected selectively into state or features. The split is deliberate and does not constitute duplication.

---

## 5. Boundary / Architecture Audit

### 5.1 YAML + Pydantic + contract-first constraints

**FINDING: Respected for provenance logic.** No new YAML fields, no schema widening. Provenance fields are carried inside the existing `regime` snapshot (an untyped dict in CMD), which is the correct minimal-surface approach given that CMD top-level is schema-strict.

**FINDING: NOT respected for the objective engine refactoring.** The `aurora_decision.py` changes introduce new adapter classes that change how `domain_cfg.components` is consumed. This is inside the objective engine path, not provenance, but since the changes are co-mingled the boundary is blurred.

### 5.2 CMD top-level schema

**FINDING: No CMD top-level widening detected.** Provenance fields live inside `cmd["regime"]` (the regime snapshot dict), not at cmd root level.

### 5.3 FE ↔ DM boundary

**FINDING: No new hidden truth plane introduced.** The provenance fields follow the existing regime snapshot pathway (FE caches detector event → enriches at CMD emit → DM reads from CMD). This is correct.

### 5.4 `runtime_regime_layers.py` value

**FINDING: Legitimate shared contract.** The file was already the shared contract for `RuntimeRegimeLayer`, `RuntimeRegimeScope`, `RuntimeRegimeClock`. Adding provenance constants and builders here is the correct extension point. It is not gratuitous indirection.

### 5.5 FE ↔ DM boundary violation via `close_boundary_ts_ms` injection

**MINOR CONCERN:** FE now injects `close_boundary_ts_ms` into `features_payload` (line 1970-1982). While this is a low-risk additive field, it represents FE setting a bar-identity field that DM previously derived independently. If both paths derive the same value identically, this is harmless. If they diverge (e.g., when `bar_identity` is present vs absent), it could create an inconsistency. Risk: LOW.

---

## 6. Test Audit

### 6.1 Focused test suite (16 tests)

| Test file | Tests | Result |
|-----------|-------|--------|
| `tests/integration/test_regime_provenance_hardening.py` | 2 | PASSED |
| `tests/sim/test_regime_timing_edge_cases.py` | 12 | PASSED |
| `tests/integration/test_pillars_quadratic_pipeline.py` | 2 | PASSED |

**Provenance scenarios covered:**

| Scenario | Tested | Evidence |
|----------|--------|----------|
| Same-bar detector truth on real Detector→FE→Aurora stack | YES | `test_detector_fe_aurora_same_bar_regime_provenance_is_explicit` |
| Same-bar overrides previous cache (current bar) | YES | `test_detector_fe_aurora_current_bar_detector_truth_overrides_previous_cache` |
| Cached previous-bar (timing harness) | YES | `test_mr_one_bar_delayed_regime_event_uses_previous_cached_cmd_regime` |
| Explicit uncertain provenance | YES | `test_explicit_uncertain_regime_provenance_is_machine_readable` |
| Missing heartbeat fail-closed | YES | `test_aurora_missing_regime_without_cache_blocks_with_canonical_reason` |
| Aurora cached previous regime surfaces in features | YES | `test_aurora_missing_regime_payload_uses_cached_previous_regime_with_traceable_ts` |
| MR cached previous bar in signal payload | YES | `test_mr_cached_previous_bar_regime_surfaces_in_signal_payload` |
| Stale/alternating detector cadence | YES | `test_detector_alternating_stale_ready_cadence_is_explicit` |
| Delayed EVT ordering (MR path) | YES (timing harness) | `test_mr_one_bar_delayed_regime_event_uses_previous_cached_cmd_regime` |
| Delayed EVT ordering (Aurora path) | **PARTIAL** | Only via cached-regime test; real integration ordering not proven |
| Cross-symbol isolation | YES | `test_mr_cross_symbol_delays_are_isolated_per_symbol` |
| Replay determinism | YES | `test_mr_duplicate_and_skipped_regime_events_replay_deterministically` |

### 6.2 What the tests do NOT cover

1. **Aurora real integration cached-previous-bar**: The report explicitly admits `cached_previous_bar` is only proven in the timing harness for Aurora (not the real Detector→FE→Aurora wiring). This is an accepted gap with a known reason (synchronous delivery makes cache reuse non-observable in that path).
2. **Objective engine provenance propagation**: `regime_confidence is None` guard added to objective engine path in aurora_decision.py is not tested by any new test.
3. **Concurrent symbol provenance isolation in Aurora**: Only MR cross-symbol isolation is tested.
4. **Provenance serialization to telemetry / JSONL**: The report explicitly excludes this scope.
5. **The objective engine refactoring behavior** (the largest actual change) has **zero coverage** from the provenance test suite.

### 6.3 Adequacy judgment

**For the provenance-specific scope: ADEQUATE.**
**For the full working-tree scope (including objective engine refactoring): INADEQUATE.** The 627-line aurora_decision.py refactoring and 720-line MR handler refactoring have no dedicated tests.

---

## 7. Failed-Test Investigation

### 7.1 Failing test 1: `TestAuroraRunsOnCMD::test_aurora_runs_only_on_cmd_300`

**File:** `tests/domains/decision_making/test_cmd_process_strategy.py:119`

**Error:**
```
ValueError: <MagicMock name='mock.strategies.aurora.decision.operational_mode'
            id='1625736956288'> is not a valid OperationalMode
```

**Failure path:**
```
AuroraHandler.__init__
  → _load_config()               [aurora_config_loader.py:_load_config]
    → ModeManager(op_mode)       [aurora_config_loader.py:107]
      → OperationalMode(mode)    [operational_mode.py:29]
        → ValueError (MagicMock not a valid enum value)
```

**Root cause:** The test's `mock_config` fixture uses `MagicMock()` for `cfg.strategies.aurora.decision` but does not set `decision.operational_mode`. When `_load_config()` tries to instantiate `OperationalMode(config.strategies.aurora.decision.operational_mode)`, it receives a `MagicMock` object instead of a valid string enum value.

**Relation to provenance package:** NONE. The stack does not enter any provenance code. Failure happens during `AuroraHandler.__init__` before any regime event is processed.

**Pre-existing?** YES. The `_load_config()` → `ModeManager(op_mode)` path exists in the committed code. The test was already broken before the provenance package changes because it doesn't mock `operational_mode` to a valid enum value.

**Verdict: CONFIRMED PRE-EXISTING, UNRELATED TO PROVENANCE HARDENING.**

### 7.2 Failing test 2: `TestNoDoubleExecution::test_duplicate_cmd_handling`

**File:** `tests/domains/decision_making/test_cmd_process_strategy.py:347`

**Error:** Identical to test 1 — same call path, same root cause, same `mock_config` pattern.

**Verdict: CONFIRMED PRE-EXISTING, UNRELATED TO PROVENANCE HARDENING.**

### 7.3 Impact assessment of two failures

These failures do not indicate any regression from the provenance package. They are a pre-existing test infrastructure debt: tests that use `MagicMock()` for `AuroraConfig` without specifying `operational_mode`. The mock was sufficient before `ModeManager` added strict enum validation but broke when that validation was added (in a prior commit, not this package).

---

## 8. Report Credibility Audit

### 8.1 Factual accuracy of claims

| Claim | Verdict | Evidence |
|-------|---------|----------|
| "narrow additive hardening package" | **FALSE** | aurora_decision.py 627-line diff; MR handler 720-line diff; both dominated by non-provenance refactoring |
| "8 files changed" | **MISLEADING** | 8 files include aurora_decision.py and MR handler, but those files have ~1300 lines of non-provenance changes combined |
| "16 focused tests passed" | **TRUE** | Confirmed by direct execution |
| "35 passed, 3 skipped, 2 failed in regression sweep" | **TRUE** | Confirmed by direct execution |
| "failures are unrelated to this package" | **TRUE** | Confirmed by stack trace analysis |
| "backward compatibility risk: LOW" | **PARTIALLY MISLEADING** | Additive provenance fields: LOW. But `regime_confidence = None` is a semantic change; objective engine refactoring changes Aurora's core decision path behavior |
| "runtime_readiness_builder and objective_gate_evaluator not mentioned" | **OMISSION** | Both are staged new files, imported by changes in the "provenance" files |

### 8.2 Does the report overclaim completion?

**YES.** The report is written as if the two large refactorings (objective gate evaluator, runtime readiness builder) either do not exist or are transparent to the package. They are materially different changes that affect runtime behavior, not just provenance observability.

### 8.3 Is "Status: COMPLETE" justified?

**NO.** The provenance sub-package is functionally complete and tested. The larger changes bundled into the same working-tree submission are untested within this package and undeclared.

---

## 9. Acceptance Decision

### Decision: REJECT

**Provenance logic core:** ACCEPTABLE on its own. Would merit ACCEPT WITH RESERVATIONS if isolated into a clean commit containing only:
- `runtime_regime_layers.py` additions
- `regime_detector.py` provenance call
- `feature_engineering.py` provenance call + `dict(pld)` fix
- `aurora_handler.py` provenance state caching
- The ~25-line provenance injection in `aurora_decision.py`
- The ~50-line provenance fields in `mean_reversion_handler.py`
- `tests/integration/test_regime_provenance_hardening.py`
- `tests/sim/test_regime_timing_edge_cases.py`

**Working tree as submitted:** REJECT, for the following reasons:

1. **No commit boundary.** Package cannot be verified, rolled back, or bisected.
2. **Undeclared major changes.** ~1300 lines of objective engine + runtime readiness builder refactoring are co-mingled and undeclared. These changes alter Aurora's core decision logic and MR handler readiness path — not provenance fields.
3. **Two new unreported modules staged.** `objective_gate_evaluator.py` and `runtime_readiness_builder.py` are dependencies of the "provenance" changes but not documented.
4. **Report misrepresents scope.** The submitting agent's report is inaccurate about what was changed, making acceptance-by-report impossible.
5. **Untested behavior.** The 1300+ lines of objective engine and readiness builder changes have no test coverage within this package submission.

---

## 10. Required Follow-Up Actions Before Any Acceptance

### REQUIRED (blocking):
1. **Create a clean, isolated commit** for the true provenance hardening scope only (6 files, ~200 net lines).
2. **Declare and separately commit** the objective gate evaluator refactoring (`objective_gate_evaluator.py`, `runtime_readiness_builder.py`, objective engine path changes in `aurora_decision.py` and `mean_reversion_handler.py`) as a separate package with its own report, test suite, and acceptance gate.
3. **Add tests for `regime_confidence is None` guard** — the semantic change from `0.0` to `None` must be covered.
4. **Fix the two pre-existing failing tests** (`test_aurora_runs_only_on_cmd_300`, `test_duplicate_cmd_handling`) by adding `decision.operational_mode = "shadow"` (or equivalent valid enum) to the `mock_config` fixture. This is not caused by this package but should not be left broken.

### RECOMMENDED (not blocking):
5. **Consolidate repeated `build_regime_provenance_fields` call-site patterns** into a `build_state_provenance_fields(state, bar_close_ts_ms)` helper to reduce the 3-site duplication of input construction.
6. **Annotate `regime_event_ts_ms_of` ts fallback ladder** with inline comment about the bar-end time domain caveat.
7. **Add audit test** for `regime_confidence = None` propagation through aurora_decision objective precondition guard.

---

## 11. What Remains Unproven

| Gap | Risk | Notes |
|-----|------|-------|
| `cached_previous_bar` on real Detector→FE→Aurora wiring | LOW | By design; synchronous delivery makes it non-observable. Proven in harness only. |
| Aurora cross-symbol provenance isolation | LOW | MR tested; Aurora not |
| Objective engine refactoring correctness (`evaluate_objective_gate`) | **HIGH** | ~600 lines of behavior change, no dedicated tests |
| MR runtime readiness builder refactoring correctness | **HIGH** | ~670 lines of behavior change, no dedicated tests |
| `regime_confidence = None` propagation safety (all consumers) | MEDIUM | Guard added in aurora_decision, but not systematically checked elsewhere |
| Provenance propagation to telemetry / JSONL schemas | LOW | Explicitly out of scope; acceptable |
| End-to-end provenance round-trip in replay harness | LOW | Not tested; not in scope |

---

## 12. Mandatory Questions — Explicit Answers

**Q1: Did the agent add unnecessary code?**
YES. The objective engine refactoring and runtime readiness builder integration (~1300 lines combined) in `aurora_decision.py` and `mean_reversion_handler.py` is out of scope for a provenance hardening package and was not declared.

**Q2: Did the agent introduce any meaningful duplication?**
MEDIUM-RISK. The input-construction pattern `{"regime": state.regime, "regime_event_ts_ms": state.regime_event_ts_ms or state.regime_ts_ms}` is repeated at 3 call sites. The core classifier is correctly centralized.

**Q3: Is provenance logic centralized enough?**
YES for classification. The `build_regime_provenance_fields` function is the single classification truth. Call-site input construction has minor structural debt but is not a blocking issue.

**Q4: Are tests sufficient for acceptance?**
YES for the provenance sub-scope. NO for the full working-tree scope. The objective engine refactoring has no test coverage.

**Q5: Are the two failed regression tests truly unrelated?**
YES. Confirmed by stack trace. Both fail at `OperationalMode(MagicMock)` during `AuroraHandler.__init__`, before any provenance logic is reached. The root cause is a pre-existing mock setup deficiency in the test fixture.

**Q6: Is the package actually complete, or only partially proven?**
PARTIALLY PROVEN. The provenance components are complete and tested. The co-mingled non-provenance changes are incomplete (no tests) and undeclared.

**Q7: Is the implementation quality good enough to accept?**
The pure provenance implementation quality is GOOD. The working-tree submission quality is POOR due to undeclared scope, no commit boundary, and missing tests for the large non-provenance changes.

**Q8: What remains unproven after this audit?**
See Section 11. Critical gaps: objective engine refactoring (600+ lines, no tests); MR readiness builder refactoring (670+ lines, no tests); `regime_confidence = None` propagation safety beyond the aurora_decision guard.
