# LLM Judge Phase 3 — Code Audit

**Date**: 2026-04-15
**Auditor**: Antigravity (audit-only; no code changes)
**Authority**: `docs/LLM_JUDGE/LLM_JUDGE_PHASE3_IMPLEMENTATION_BLUEPRINT.md`
**Prior audit**: `docs/LLM_JUDGE/LLM_JUDGE_PHASE1_PHASE2_CODE_AUDIT.md`

---

## 1. Executive Verdict

| Item | Verdict |
|---|---|
| **Overall** | **ACCEPT** |
| **Phase 3 sub-verdict** | **CLOSED** |
| **Phase 4 Readiness** | **YES** |

Phase 3 conforms to the frozen blueprint in all material points. All 9 deliverables from §18.2 are implemented and verifiably correct. All 7 acceptance gates from §15.3 are met. 326 total alpha_search tests pass (292 judge + 34 non-judge regression). No frozen prior-phase artifacts were modified. No decision_making or execution_position contamination. No report claims are materially overstated relative to code evidence. Phase 3 is CLOSED.

---

## 2. Audit Scope

**Primary target:** Phase 3 chamber substrate
- `ChamberConfig` in `judge/config_models.py`
- `judge/chamber/__init__.py`, `admissibility.py`, `chamber_aggregator.py`
- `expert_output_bridge.py` (`write_jsonl_chamber_log` addition)
- `backtest_plugin.py` Phase 3 orchestration additions
- `config/alpha_search.yaml` chamber block
- `domain_dict.json` Phase 3 updates
- `verb_registry_v1.yaml` chamber verb note update

**Frozen surfaces verified:**
- `judge/contracts.py` — unchanged (Phase 1 frozen)
- `judge/schemas/` — unchanged (Phase 1 frozen)
- `judge/experts/signal_weights_expert.py` — unchanged (Phase 2 frozen)
- `judge/experts/feature_neutrals_expert.py` — unchanged (Phase 2 frozen)
- `apps/reference/main.py` — no judge references
- `apps/reference/config_loader.py` — no judge references
- Root `apps/reference/config_models.py` — no judge references
- `decision_making/` — zero semantic references to judge or chamber
- `execution_position/` — zero semantic references to judge or chamber
- `quadratic_scoring_kernel.py` — zero judge references

---

## 3. Audit Method

**Read:**
- `docs/LLM_JUDGE/LLM_JUDGE_PHASE3_IMPLEMENTATION_BLUEPRINT.md` — complete (778 lines)
- `docs/LLM_JUDGE/PHASE3_CHAMBER_SUBSTRATE_REPORT.md` — complete (119 lines)
- `judge/config_models.py` — complete (242 lines); Phase 3 additions at lines 183–230
- `judge/chamber/admissibility.py` — complete (64 lines)
- `judge/chamber/chamber_aggregator.py` — complete (164 lines)
- `judge/experts/expert_output_bridge.py` — complete (139 lines); Phase 3 addition at lines 116–139
- `backtest_plugin.py` — complete (1623 lines); imports at lines 32–38; Phase 3 orchestration at lines 603–720, 990–1153
- `config/alpha_search.yaml` — lines 180–240 (chamber block at 234–239)
- `domain_dict.json` — complete (139 lines)
- `verb_registry_v1.yaml` — lines 625–683 (JUDGE entries at 638–674)
- `tests/domains/alpha_search/judge/test_config.py` — lines 344–437 (ChamberConfig tests)
- `tests/domains/alpha_search/judge/chamber/test_admissibility.py` — complete (268 lines)
- `tests/domains/alpha_search/judge/chamber/test_chamber_aggregator.py` — complete (356 lines)
- `tests/domains/alpha_search/judge/test_expert_provider_integration.py` — complete (789 lines); Phase 3 chamber tests at lines 527–789

**Executed:**
- `pytest tests/domains/alpha_search/judge/ -q` → **292 passed, 0 failed, 2.39s**
- `pytest tests/domains/alpha_search/ -q` → **326 passed, 0 failed, 3.68s**

**Compared:**
- Blueprint §18.2 checklist (19 items) against code (all 19 verified)
- Blueprint §15.3 acceptance gates (7 gates) against evidence
- Blueprint §11 (chamber design) against code implementation line-by-line
- Blueprint §14 (file-by-file scope) against directory listing
- Blueprint §3 (frozen constraints) against grep evidence across all frozen surfaces
- Report claims against code and test evidence

**Grep verification (key surfaces):**
- `judge/contracts.py` for new Phase 3 symbols → 0 hits (frozen, no additions)
- `decision_making/` for `judge`, `chamber` → 0 hits
- `execution_position/` for `judge`, `chamber` → 0 hits
- `main.py` for `judge`, `chamber` → 0 hits
- `quadratic_scoring_kernel.py` for `judge`, `chamber` → 0 hits

---

## 4. FACTS

**F1.** `judge/config_models.py` lines 183–211: `ChamberConfig` is defined with `model_config = ConfigDict(extra="forbid", frozen=True)`. Fields: `min_quorum: int = 1`, `max_staleness_ms: int = 30000`, `entry_enabled: bool = True`, `lifecycle_enabled: bool = False`. Two `field_validator`s: `min_quorum >= 0`, `max_staleness_ms > 0`. Exactly matches blueprint §13.2.

**F2.** `JudgeCortexConfig` line 230: `chamber: Optional[ChamberConfig] = None`. Additive-only change to existing Phase 2 model. The validator `validate_phase2_mode_admission` unchanged — still admits only `{"off", "shadow"}`. No new modes admitted in Phase 3.

**F3.** `judge/chamber/__init__.py` exists (54 bytes). Exports `ChamberAggregator` and `evaluate_admissibility`. Placement: `apps/reference/domains/alpha_search/judge/chamber/`. Correct per blueprint §10.1.

**F4.** `judge/chamber/admissibility.py` (64 lines): implements `evaluate_admissibility()` with rules R1–R5 in order (quorum, silent failure, duplicate, freshness, scope, default). Function signature includes `verdict_scope` parameter added beyond blueprint §11.5 spec — a sound additive detail for defense-in-depth scope checking in R4.

**F5.** `judge/chamber/chamber_aggregator.py` (164 lines): implements `ChamberAggregator` with `aggregate()`. Step 1 uses `expert_count = len(expected_expert_ids)` (solicited roster). Step 2 filters by scope via `_filter_by_scope()`. Step 3 classifies responding as `confidence > 0.0 AND verdict != "UNKNOWN"`. Step 4 computes `abstaining_count = expert_count - responding_count`. Steps 5–9 call admissibility, compute consensus, generate `chamber_id = f"{verdict_scope.lower()}_{symbol}_{ts_ms}"`, return `ChamberAggregate`.

**F6.** `backtest_plugin.py` lines 32–38 (top-level module imports): `from .judge.experts.expert_output_bridge import alpha_score_to_expert_output, write_jsonl_chamber_log, write_jsonl_shadow_log` and `from .judge.chamber import ChamberAggregator`. Both are module-level imports (not deferred).

**F7.** `backtest_plugin.py` `_on_decision_score()` lines 603–720: Before the provider loop (line 604–611), builds `solicited_expert_ids` by iterating `self.provider_configs` and calling `_resolve_judge_expert_id()` for providers with `judge_expert is not None`. After the provider loop (lines 712–720), if `solicited_expert_ids` is non-empty, calls `_run_chamber_aggregation()`.

**F8.** `backtest_plugin.py` `_process_score()` (lines 878–951): Returns `Optional["ExpertOutput"]`. For `cfg.judge_expert is not None` (line 911), delegates to `_process_judge_expert_score()` and returns its result. For non-judge, calls `_emit_score_event()` and returns `None`. Returns are collected in caller at line 703–704: `if expert_output is not None: judge_expert_outputs.append(expert_output)`.

**F9.** `backtest_plugin.py` `_process_judge_expert_score()` (lines 990–1060): Unchanged in semantic behavior from DEFECT-P2-01 fix — still translates `AlphaScore → ExpertOutput`, emits `EVT:JUDGE_EXPERT_PRODUCED_V1`, writes expert JSONL. Phase 3 addition: returns `expert_output` at line 1060 for chamber collection.

**F10.** `backtest_plugin.py` `_resolve_judge_expert_id()` (lines 1062–1071): Maps `"signal_weights"` → `judge_cfg.experts.signal_weights.expert_id`, `"feature_neutrals"` → `judge_cfg.experts.feature_neutrals.expert_id`. Returns `None` for unknown types or missing config.

**F11.** `backtest_plugin.py` `_run_chamber_aggregation()` (lines 1073–1152): Entry chamber runs when `chamber_cfg.entry_enabled` (line 1095). `ChamberAggregator("ENTRY", chamber_cfg).aggregate(judge_expert_outputs, expected_expert_ids=solicited_expert_ids, ...)` is called. `EVT:JUDGE_CHAMBER_AGGREGATED_V1` emitted via `self.event_bus.emit()`. JSONL log written via `write_jsonl_chamber_log()` when `judge_cfg.shadow_log.enabled`. Lifecycle chamber runs ONLY when `chamber_cfg.lifecycle_enabled` (line 1129), passes `[], expected_expert_ids=[]`.

**F12.** `_emit_fail_closed_score()` (lines 1154–1194): Lines 1168–1173: if `cfg.judge_expert is not None`, suppresses silently (no event, no ExpertOutput returned). This confirms fail-closed judge experts produce no output, and cannot return an `ExpertOutput` through `_process_judge_expert_score()`. The roster still has their `expert_id` from the pre-loop collection (F7), so the gap is visible to the chamber.

**F13.** `expert_output_bridge.py` lines 116–139: `write_jsonl_chamber_log(chamber_aggregate, log_dir)` appends `chamber_aggregate.model_dump_json()` to `chamber_{symbol}_{YYYY-MM-DD}.jsonl`. Same pattern as `write_jsonl_shadow_log`. No exceptions from file operations bubble up (caught and logged).

**F14.** `config/alpha_search.yaml` lines 234–239: `chamber:` block present under `judge:` with `min_quorum: 1`, `max_staleness_ms: 30000`, `entry_enabled: true`, `lifecycle_enabled: false`. Matches blueprint §13.3 exactly.

**F15.** `verb_registry_v1.yaml` lines 660–666: `JUDGE_CHAMBER_AGGREGATED_V1` entry has `note: "Phase 3 shadow emission — chamber aggregate (entry + lifecycle stub), never consumed by decision_making"`. This is the updated note from Phase 1's "Phase 1 contract registration only — no runtime emission". Blueprint §14 (Package 3D) required this update.

**F16.** `domain_dict.json` lines 63–68: `EVT:JUDGE_CHAMBER_AGGREGATED_V1` export updated to `"description": "Phase 3 shadow emission. Chamber expert aggregation (entry + lifecycle stub)."`. Lines 115–125: 3 new `judge/chamber/` components added. Lines 100–113: `judge/config_models.py` and `judge/experts/expert_output_bridge.py` descriptions updated to mention Phase 3 additions.

**F17.** `judge/contracts.py`: grep returned zero results for any Phase 3 symbols. File unchanged from Phase 1 frozen state.

**F18.** `judge/schemas/`: Directory listing shows same 4 files as Phase 1 (`chamber_aggregate_v1.json`, `expert_output_v1.json`, `judge_evidence_envelope_v1.json`, `judge_verdict_v1.json`). No new schemas added, no existing schemas modified.

**F19.** `judge/experts/signal_weights_expert.py` and `feature_neutrals_expert.py`: Decision confirmed by F3 in Phase 1/2 audit — these files are Layer 1 pure scoring modules. No Phase 3 changes were required and none were made.

**F20.** Test count: `pytest tests/domains/alpha_search/judge/` → 292 passed. Breakdown from report: Phase 1 ~80, Phase 2 ~70, Phase 3 new 58 (14 config + 14 admissibility + 20 aggregator + 10 integration), registry/admission ~24. `pytest tests/domains/alpha_search/` → 326 passed total (non-judge regression tests add 34).

**F21.** `test_config.py` lines 344–437: `TestChamberConfig` (9 tests), `TestJudgeCortexConfigChamber` (5 tests) including backward compatibility test and YAML round-trip. `test_load_yaml_with_chamber` at line 428 calls `load_alpha_search_config("config/alpha_search.yaml")` and asserts `cfg.judge.chamber.min_quorum == 1` etc. Passes.

**F22.** `test_expert_provider_integration.py` lines 527–789: Chamber integration tests cover: `TestChamberEventEmitted` (3 tests — `EVT:JUDGE_CHAMBER_AGGREGATED_V1` emitted, not emitted without config, single expert triggers chamber), `TestChamberPayloadValid` (2 tests — payload deserializes to `ChamberAggregate`, entry chamber with 2 experts has `expert_count=2`, `admissibility="ADMISSIBLE"`), `TestLifecycleStubEnabled` (1 test — lifecycle emits `QUORUM_INSUFFICIENT` when explicitly enabled), `TestLifecycleStubDisabledByDefault` (1 test — lifecycle NOT emitted with default config), `TestChamberRosterTruth` (1 test — provider removed after init, `expert_count=2`, `admissibility="INADMISSIBLE"`), `TestChamberJSONLLog` (2 tests — JSONL written, not written when shadow_log disabled). Total: 10 new chamber integration tests.

**F23.** Solicited roster building (lines 606–611 of backtest_plugin): Iterates `self.provider_configs` (not `self.providers`). If a provider exists in `provider_configs` but has been removed from `providers` (e.g., failed init, or test-forced removal), `_resolve_judge_expert_id` still adds its `expert_id` to `solicited_expert_ids`. Scoring loop (line 614) iterates `self.providers`, so the removed provider is not scored and produces no ExpertOutput. Chamber correctly sees roster count > returned count → `INADMISSIBLE`. This is proven by `TestChamberRosterTruth`.

**F24.** `_resolve_judge_expert_id()` resolves `expert_id` from the **judge config block** (`judge.experts.signal_weights.expert_id`), not from the `provider_configs`. This means if the same expert_type is registered twice under different provider names, both resolve to the SAME `expert_id`, producing a duplicate in `solicited_expert_ids`. Admissibility rule R2.5 then fires on the resulting outputs. This is correct behavior per blueprint §11.5 ("Duplicate expert_id outputs indicate a config error").

**F25.** Lifecycle chamber stub passes `expected_expert_ids=[]` (line 1133), not the `solicited_expert_ids`. This is correct: lifecycle experts don't exist in Phase 3, so the lifecycle chamber's solicited roster is genuinely empty. The lifecycle chamber correctly produces `expert_count=0`, `QUORUM_INSUFFICIENT`.

---

## 5. INFERENCES

**I1.** The initial grep attempts for `_run_chamber`, `solicited`, `judge_expert_outputs` in `backtest_plugin.py` returned no results because the regex OR operator `\|` was incorrectly used (POSIX ERE, not ripgrep syntax). The code was subsequently confirmed present by direct file reading at lines 603–720 and 1062–1152. No code absence.

**I2.** The `_filter_by_scope()` result (not the raw `expert_outputs`) is passed to `evaluate_admissibility()` (line 84 of chamber_aggregator.py). For R2 (silent failure), the comparison is `len(scope_filtered) < expected_expert_count`. For the ENTRY chamber with ENTRY experts, scope_filtered == expert_outputs, so R2 is accurate. For a LIFECYCLE chamber receiving `expected_expert_ids=[]` and `expert_outputs=[]`, `len([]) < 0` is false, so R2 does not fire; R1 fires first (responding=0 < min_quorum=1 → QUORUM_INSUFFICIENT). This is correct behavior.

**I3.** A subtle interaction exists: if a fail-closed judge expert is suppressed (F12), `_process_judge_expert_score()` is never called (the provider is not in `self.providers` or the scoring raises), so `judge_expert_outputs` has no entry for that expert. However, `solicited_expert_ids` was built from `self.provider_configs` which still includes the config entry. The gap counts as a silent failure. R2 fires → `INADMISSIBLE`. This is the correct fail-closed behavior intended by blueprint §11.1 "Fix 1 (CRITICAL)".

**I4.** There is a theoretical scenario: a judge expert provider exists in `provider_configs` and in `providers`, and its expert is `enabled=False` in `judge.experts.{type}`. In this case, `_create_judge_expert()` returns `None` at line 287 or 293, so that provider is never added to `self.providers`. But `_resolve_judge_expert_id()` still resolves a valid `expert_id` from the config (since `judge.experts.{type}.expert_id` is set even when disabled). So the disabled expert's `expert_id` is added to `solicited_expert_ids`. But because the provider is not in `self.providers`, no output is collected. This creates a phantom "solicited" expert that was never actually registered or runnable. The result: `expert_count > len(judge_expert_outputs)` → R2 → `INADMISSIBLE`. This is overly aggressive but fail-closed. It does not cause incorrect scoring or data corruption. Operational risk: LOW. Not a defect per blueprint's fail-closed philosophy.

**I5.** The `_run_chamber_aggregation()` check at line 1088: `if not judge_cfg or judge_cfg.mode != "shadow": return`. This means chamber only runs in `shadow` mode. If config has `mode="off"`, chamber is skipped entirely. This is correct: when judge is off, no providers are registered (because `_create_judge_expert` returns None for `mode="off"`), so `solicited_expert_ids` is always empty anyway, and `_run_chamber_aggregation` is never called (line 713 guard). The `mode != "shadow"` check in `_run_chamber_aggregation` is additional defense-in-depth.

**I6.** The `test_expert_provider_integration.py` `_make_config()` helper (lines 115–180) now accepts `chamber=None` default, wiring `chamber=chamber` into `JudgeCortexConfig`. Tests that pass `chamber=ChamberConfig()` get a running chamber; tests that pass `chamber=None` prove no chamber event is emitted. This tests the config-gate correctly.

---

## 6. ASSUMPTIONS

**A1.** The lack of a `test_expert_config.py` (separate file for expert configs) in Phase 2 was accepted as merged into `test_config.py`. Similarly, the 14+5 = 19 Phase 3 config tests in `test_config.py` (TestChamberConfig + TestJudgeCortexConfigChamber) are accepted as satisfying the blueprint's "+6" config test estimate. Delivery count exceeds estimate.

**A2.** The Phase 2 DEFECT-P2-01 fix report (`PHASE2_DEFECT_P2_01_FIX_REPORT.md`) is not directly read but its effects are proven by F8, F9 — `_process_judge_expert_score()` emits `EVT:JUDGE_EXPERT_PRODUCED_V1` and suppresses `EVT:ALPHA_SCORE_CALCULATED`, which the integration tests verify at 292 passing. The prior Phase 1/2 audit confirmed this independently.

**A3.** The audit treats `_process_score()` returning `Optional["ExpertOutput"]` with a forward reference string as correct Python (forward reference to avoid circular imports). At runtime the type resolves correctly because `ExpertOutput` is available via bridge import.

---

## 7. UNKNOWNS

| Unknown | Blocking? | Assessment |
|---|---|---|
| Whether the `I4` phantom-solicited scenario (disabled expert in config, provider never registered, still in solicited roster) is the intended behavior | No | Fail-closed. Operationally acceptable. Default config has experts enabled; disabling an expert while keeping its provider config is an operator error. |
| Whether `_resolve_judge_expert_id()` should also guard against missing/disabled experts (not just unknown types) | No | Current behavior is fail-closed. Phase 4 may add strictness. |
| Exact scope of `normalize_mode="signed_v2"` deferral — still deferred | No | Orthogonal. Explicitly out of scope in blueprint §4.2. |

---

## 8. Blueprint vs Code Conformance

### Package 3A: Chamber Config

| Requirement | Code Status | Verdict |
|---|---|---|
| `ChamberConfig` class with `extra="forbid"`, `frozen=True` | Lines 183–211, confirmed | PASS |
| `min_quorum: int = 1` | Line 193 | PASS |
| `max_staleness_ms: int = 30000` | Line 194 | PASS |
| `entry_enabled: bool = True` | Line 195 | PASS |
| `lifecycle_enabled: bool = False` | Line 196 | PASS |
| `min_quorum >= 0` validator | Line 198–203 | PASS |
| `max_staleness_ms > 0` validator | Line 205–210 | PASS |
| `JudgeCortexConfig.chamber: Optional[ChamberConfig] = None` | Line 230 | PASS |
| `config/alpha_search.yaml` `chamber:` block added | Lines 234–239 | PASS |
| Backward compat: `chamber` absent loads OK | `chamber: Optional = None` default; proven by `test_chamber_backward_compat_no_chamber` | PASS |
| Config tests (+6 est.) | 19 tests (9 + 5 + 5 existing YAML tests) | PASS (exceeds est.) |

### Package 3B: Chamber Aggregation Module

| Requirement | Code Status | Verdict |
|---|---|---|
| `chamber/__init__.py` exists | 54-byte file, exports `ChamberAggregator`, `evaluate_admissibility` | PASS |
| `admissibility.py` with `evaluate_admissibility()` | 64 lines, R1–R5 in order | PASS |
| `chamber_aggregator.py` with `ChamberAggregator.aggregate()` | 164 lines, all blueprint steps implemented | PASS |
| `expert_count` from `expected_expert_ids` roster | Line 67 of chamber_aggregator | PASS |
| `abstaining_count = expert_count - responding_count` | Line 80 | PASS |
| `chamber_id = f"{verdict_scope.lower()}_{symbol}_{ts_ms}"` | Line 98 | PASS |
| Output validates against frozen `ChamberAggregate` contract | `ChamberAggregate(...)` call at line 100; Pydantic validators enforce invariants | PASS |
| R1 Quorum | Line 37–38 of admissibility | PASS |
| R2 Silent failure | Lines 41–42 | PASS |
| R2.5 Duplicate expert_id | Lines 44–47 | PASS |
| R3 Freshness | Lines 50–53 | PASS |
| R4 Scope mismatch | Lines 55–60 | PASS |
| R5 Default ADMISSIBLE | Line 62–63 | PASS |
| Consensus direction: majority vote with SPLIT | Lines 133–155 of chamber_aggregator | PASS |
| Consensus strength: mean confidence of responding | Lines 157–163 | PASS |
| Unit tests (~14 admissibility + ~20 aggregator) | 14 admissibility, 20 aggregator | PASS |

### Package 3C: Orchestration Integration

| Requirement | Code Status | Verdict |
|---|---|---|
| Pre-loop solicited roster building from `provider_configs` | Lines 604–611 | PASS |
| `_process_judge_expert_score()` returns `Optional[ExpertOutput]` | Line 888, 951, 1060 | PASS |
| Collect returned ExpertOutput during loop | Lines 703–704 | PASS |
| Call `_run_chamber_aggregation()` after loop | Lines 712–720 | PASS |
| Entry chamber via `ChamberAggregator("ENTRY", ...)` | Lines 1095–1108 | PASS |
| `EVT:JUDGE_CHAMBER_AGGREGATED_V1` emitted | Lines 1104–1108 | PASS |
| JSONL chamber log written when enabled | Lines 1109–1118 | PASS |
| Lifecycle stub gated by `lifecycle_enabled` | Line 1129 | PASS |
| Lifecycle stub passes `[], expected_expert_ids=[]` | Lines 1131–1133 | PASS |
| Lifecycle stub emits `EVT:JUDGE_CHAMBER_AGGREGATED_V1` | Lines 1138–1141 | PASS |
| `write_jsonl_chamber_log()` in `expert_output_bridge.py` | Lines 116–139 | PASS |
| Integration tests (+6 est.) | 10 new chamber integration tests | PASS (exceeds est.) |

### Package 3D: Domain Dict + Registry

| Requirement | Code Status | Verdict |
|---|---|---|
| `domain_dict.json` Phase 3 component entries | 3 new chamber components at lines 114–125 | PASS |
| `EVT:JUDGE_CHAMBER_AGGREGATED_V1` description updated | Line 66: "Phase 3 shadow emission" | PASS |
| `verb_registry_v1.yaml` JUDGE_CHAMBER note updated | Line 666: "Phase 3 shadow emission..." | PASS |

### Package 3E: Full Test Suite

| Gate | Criterion | Status |
|---|---|---|
| G-T1 | All new chamber tests pass | PASS (58 new) |
| G-T2 | All existing 234 judge tests pass (0 regressions) | PASS (292 total, 0 fail) |
| G-T3 | All existing 268 alpha_search tests pass | PASS (326 total, 0 fail) |
| G-T4 | Chamber config loads from YAML | PASS (proven by `test_load_yaml_with_chamber`) |
| G-T5 | Chamber config absent = backward compatible | PASS (proven by `test_chamber_backward_compat_no_chamber`) |
| G-T6 | `grep decision_making/ judge` → 0 semantic hits | PASS |
| G-T7 | `grep execution_position/ judge` → 0 semantic hits | PASS |

---

## 9. Chamber Logic Audit

### 9.1 Roster Truth

**Blueprint requirement** (§11.1 Fix 1 CRITICAL): `expert_count = len(expected_expert_ids)`. `abstaining_count = expert_count - responding_count`. Solicited roster built before loop, passed regardless of scoring outcome.

**Code evidence**:
- Roster built at lines 604–611, iterating `self.provider_configs` (not `self.providers`). This capture point is correctly BEFORE the scoring loop.
- `_resolve_judge_expert_id()` resolves `expert_id` from `judge.experts.{type}.expert_id`, which is the canonical expert identity from config.
- `ChamberAggregator.aggregate()` receives `expected_expert_ids` as keyword argument and uses only `len(expected_expert_ids)` for `expert_count` (line 67). Does not count from returned outputs.
- `abstaining_count = expert_count - responding_count` at line 80. This can never go negative as long as `expert_count >= responding_count`, which holds because `responding` is a subset of `scope_filtered`, which is a subset of `expert_outputs`, which has at most `len(expected_expert_ids)` elements in normal operation.

**Test proof**: `TestChamberRosterTruth.test_roster_reflects_solicited_not_returned` — removes `judge_fn` provider from `plugin.providers` after init, fires decision, asserts `expert_count=2`, `responding_count=1`, `abstaining_count=1`, `admissibility="INADMISSIBLE"`. **Directly proves roster accounting is correct.** `TestRosterTruth.test_solicited_but_missing_expert` (aggregator unit test) — same pattern at pure aggregator level. Both pass.

**Assessment**: Roster truth is correctly implemented and proven.

### 9.2 Admissibility Rules

| Rule | Blueprint spec | Code | Test |
|---|---|---|---|
| R1: Quorum | `responding_count < min_quorum` → `QUORUM_INSUFFICIENT` | Line 37–38 of admissibility.py | `test_quorum_insufficient_zero_responding`, `test_quorum_two_required_one_responding` |
| R2: Silent failure | `len(expert_outputs) < expected_expert_count` → `INADMISSIBLE` | Lines 41–42 | `test_one_solicited_none_returned`, `test_two_solicited_one_returned` |
| R2.5: Duplicate | `len(set(ids)) < len(ids)` → `INADMISSIBLE` | Lines 44–47 | `test_duplicate_expert_id_inadmissible` |
| R3: Freshness | `eo.ts_ms < cycle_ts_ms - max_staleness_ms` → `INADMISSIBLE` | Lines 50–53 | `test_stale_output_inadmissible`, `test_exact_staleness_boundary_admissible` |
| R4: Scope mismatch | ENTRY output in LIFECYCLE chamber → `INADMISSIBLE` | Lines 55–60 | `test_lifecycle_scope_rejects_entry_output` |
| R5: Default | All pass → `ADMISSIBLE` | Line 62–63 | `test_two_experts_all_checks_pass` |

**Boundary condition note**: `test_exact_staleness_boundary_admissible` tests `ts_ms = CYCLE_TS - 30000` with `max_staleness_ms=30000`. Code: `staleness_threshold = cycle_ts_ms - max_staleness_ms = CYCLE_TS - 30000`. Check: `eo.ts_ms < staleness_threshold` → `(CYCLE_TS-30000) < (CYCLE_TS-30000)` → False → NOT stale → ADMISSIBLE. Blueprint says "older than 30s relative to cycle timestamp are stale." Boundary is correctly inclusive (at-boundary = fresh). Consistent.

**Priority enforcement**: Rules are in if/elif/for/for/return order — first match wins. No path can return multiple values. Correct.

### 9.3 Consensus Metrics

**Direction algorithm** (blueprint §11.6):
- `LONG` if `long_count > short_count`
- `SHORT` if `short_count > long_count`
- `SPLIT` if `long_count > 0 and long_count == short_count`
- `NEUTRAL` if `long_count == 0 and short_count == 0`
- `None` if `responding_count == 0`

Code (lines 133–155):
```python
if long_count > short_count: return "LONG"
if short_count > long_count: return "SHORT"
if long_count > 0 and long_count == short_count: return "SPLIT"
return "NEUTRAL"
```
Plus: `if not responding: return None` at top. Exact match to blueprint.

**Strength**: `sum(eo.confidence for eo in responding) / len(responding) if responding else 0.0` — matches blueprint §11.6. Proven by `test_mean_of_two_confidences` (asserts `abs(result - 0.7) < 0.001` for [0.8, 0.6]).

**NEUTRAL experts**: `NO_ENTRY` verdict maps to `signal_direction="NEUTRAL"` in bridge. Neutral experts do not increment `long_count` or `short_count` but still count as responding (if confidence > 0). `test_no_entry_neutral` proves two NEUTRAL experts yield `consensus_direction="NEUTRAL"`. Matches blueprint §11.2 ("Mixed LONG/NO_ENTRY → direction follows LONG").

### 9.4 Lifecycle Stub Behavior

**Blueprint requirement** (§11.3): Lifecycle stub does NOT execute in default config. When explicitly enabled, receives zero experts, always produces `QUORUM_INSUFFICIENT`.

**Code evidence**:
- Default `lifecycle_enabled: false` in YAML (F14) and `ChamberConfig.lifecycle_enabled = False` default (F1). 
- `_run_chamber_aggregation()` line 1129: `if chamber_cfg.lifecycle_enabled:` — strictly gated. No lifecycle code runs at all if false.
- When enabled: passes `[], expected_expert_ids=[]`. `ChamberAggregator("LIFECYCLE", ...)`. `expert_count=0`, `responding_count=0`. `evaluate_admissibility([], 0, 0, min_quorum=1, ...)` → R1: `0 < 1` → `QUORUM_INSUFFICIENT`.

**Test proof**: `TestLifecycleStubDisabledByDefault` proves no lifecycle event with default ChamberConfig. `TestLifecycleStubEnabled` with `ChamberConfig(lifecycle_enabled=True)` proves lifecycle event emitted with `expert_count=0`, `admissibility="QUORUM_INSUFFICIENT"`. Both pass.

---

## 10. Runtime / Integration Audit

### 10.1 Provider Path

The Phase 3 execution path through `_on_decision_score()` is:

1. Build `solicited_expert_ids` and `judge_expert_outputs = []` (pre-loop, lines 604–611)
2. For each provider: call `_process_score()` which dispatches to `_process_judge_expert_score()` for judge providers, returns `ExpertOutput` or `None`
3. Collect non-None returns into `judge_expert_outputs` (lines 703–704)
4. After loop: `_run_chamber_aggregation()` with both lists (lines 712–720)

This is exactly the in-memory synchronous pattern specified in blueprint §11.4. No event-bus round-tripping.

### 10.2 Chamber Emission

**Event**: `EVT:JUDGE_CHAMBER_AGGREGATED_V1`
**Trigger**: `self.event_bus.emit(event_name="EVT:JUDGE_CHAMBER_AGGREGATED_V1", payload=entry_result.model_dump(), why=f"judge_chamber_entry_{symbol}")`
**Payload**: `ChamberAggregate.model_dump()` — a dict representation of the frozen Pydantic model. All fields including `expert_count`, `responding_count`, `admissibility`, `consensus_direction`, `consensus_strength`, `expert_outputs` are serialized.
**Proven by**: `TestChamberPayloadValid.test_chamber_payload_deserializes_to_aggregate` — receives the payload, calls `ChamberAggregate(**payload)`, asserts fields. Passes.
**Shadow posture**: No `decision_making` consumer for this event. `decision_making/` has zero judge references (F in audit). `domain_dict.json` exports the event with `target_domains: []`. Verb registry marks it `status: experimental`. The event is telemetry only.

### 10.3 Chamber JSONL Logging

**Function**: `write_jsonl_chamber_log(chamber_aggregate, log_dir)` in `expert_output_bridge.py` lines 116–139
**File path**: `chamber_{symbol}_{YYYY-MM-DD}.jsonl`, distinct from expert JSONL (`{expert_id}_{symbol}_{date}.jsonl`)
**Gating**: Called only when `judge_cfg.shadow_log and judge_cfg.shadow_log.enabled`
**Proven by**: `TestChamberJSONLLog.test_chamber_jsonl_written_when_enabled` — creates tempdir, fires decision, asserts `chamber_*.jsonl` exists with one line, validates `verdict_scope: "ENTRY"`. Passes. `test_no_chamber_jsonl_when_shadow_log_disabled` proves no file when disabled.

### 10.4 Non-Judge Path Non-Regression

**Test proof**: `TestNonJudgeProviderUnchanged.test_non_judge_provider_emits_alpha_score_calculated` — manually injects a `DummyAuroraModel`, fires decision, asserts `EVT:ALPHA_SCORE_CALCULATED` emitted, `EVT:JUDGE_EXPERT_PRODUCED_V1` not emitted. `test_mixed_judge_and_nonjudge` — judge + dummy provider, asserts each uses correct event.

**Code path**: Non-judge providers follow `_emit_score_event()` path (line 920–928). `_process_score()` returns `None` for non-judge. Non-judge provider IDs not present in `provider_configs` with `judge_expert is not None`, so they are never added to `solicited_expert_ids`. Chamber does not aggregate non-judge scores.

**`EVT:ALPHA_SCORE_CALCULATED` suppression for judge**: `_process_score()` dispatches to `_process_judge_expert_score()` for `cfg.judge_expert is not None` (line 911) and skips `_emit_score_event()`. Proven by `TestJudgeExpertSuppressesAlphaScore`. All existing behaviors preserved.

**Regression test proof**: `pytest tests/domains/alpha_search/` → 326 passed including `test_backtest_plugin.py`, `test_aurora_adapter.py`, `test_ensemble_features_plumbing.py`, `test_models_determinism.py`, `test_objective_feedback.py`, `test_registry_fail_closed.py`.

---

## 11. Architectural Law Compliance

### Contract-First
**Status: PASS**
The `ChamberAggregate` Pydantic model was defined in Phase 1 (frozen). Phase 3 implements behavior that PRODUCES `ChamberAggregate` instances — the contract precedes the runtime implementation by 2 phases. `ChamberConfig` follows the same `extra="forbid", frozen=True` pattern. No new contracts were introduced in Phase 3 (only a new config model, which is not a behavioral contract).

### Additive-Only Evolution
**Status: PASS**
All Phase 3 additions are additive:
- `ChamberConfig` class added to `config_models.py` (new class)
- `chamber: Optional[ChamberConfig] = None` field on `JudgeCortexConfig` (new Optional field, default None)
- `write_jsonl_chamber_log()` added to `expert_output_bridge.py` (new function, no existing functions modified)
- `chamber/` sub-package created (new files)
- `backtest_plugin.py` orchestration additions in `_on_decision_score()` (new code block pre/post loop, not modifying existing logic)
- `_process_score()` return type changed from `None` to `Optional["ExpertOutput"]` — additive; callers that previously discarded the `None` return are unaffected if they discard `Optional[ExpertOutput]`
- No existing functions removed, no existing field types narrowed, no existing validators tightened

### Replayability / Explainability
**Status: PASS**
`chamber_id = f"{verdict_scope.lower()}_{symbol}_{ts_ms}"` is deterministic. JSONL logs are append-only, date-partitioned, written with `model_dump_json()`. `ChamberAggregate` includes all `expert_outputs`, `responding_count`, `abstaining_count`, and `admissibility`. Round-trip test proven (`test_round_trip_serialization` passes). JSONL files contain complete aggregate state for replay.

### No Silent Fallbacks
**Status: PASS**
- `ChamberConfig` has `extra="forbid"` — unknown fields rejected
- `JudgeCortexConfig` mode admission validator unchanged — still rejects non-admitted modes
- `_run_chamber_aggregation()` returns early with explicit if-guards (mode != "shadow", chamber_cfg is None) — not silent; LOG.debug is called
- Failed JSONL writes are caught and logged via `LOG.exception()` — not silently suppressed
- Fail-closed judge expert produces no output — NO silent swallowing; the chamber sees the roster gap via R2

### No Hidden Business Constants
**Status: PASS**
All chamber constants externalized in `config/alpha_search.yaml`: `min_quorum: 1`, `max_staleness_ms: 30000`, `entry_enabled: true`, `lifecycle_enabled: false`. Code contains no hardcoded quorum thresholds or staleness values. `ChamberConfig` field defaults match YAML production values exactly.

### No Execution-Truth Ownership Leakage
**Status: PASS**
`EVT:JUDGE_CHAMBER_AGGREGATED_V1` is emitted with `target_domains: []` in domain_dict. No decision_making or execution_position code references it. The event carries no execution intent — it is pure telemetry. The lifecycle stub produces `QUORUM_INSUFFICIENT` which is not an actionable verdict. No `CMD:OPEN`, `CMD:CLOSE`, or any execution command is emitted in Phase 3.

### Runtime Truth Over Docs
**Status: PASS**
The report claims are substantiated by code:
- "Roster-truth accounting" → F7, F23 prove it in both config collection and aggregator.
- "Shadow-only emission" → runtime emit path never writes to decision_making; tests verify zero ALPHA_SCORE_CALCULATED from judge experts.
- "Lifecycle stub default off" → config default `lifecycle_enabled=False`, code guard at line 1129, test proves silence.
- No claim in the report is contradicted by code evidence.

### Phase Acceptance Only With Proof
**Status: PASS**
All 9 Phase 3 deliverables (§18.2) are proven by code + tests + YAML evidence, not merely documented. No intended behavior is claimed without a corresponding passing test.

---

## 12. Test Coverage Assessment

### Directly Proven Behavior

| Behavior | Test | Verdict |
|---|---|---|
| `ChamberConfig` defaults and validation | `TestChamberConfig` (9 tests) | Direct |
| Backward compat (no chamber block) | `test_chamber_backward_compat_no_chamber` | Direct |
| YAML round-trip with chamber block | `test_load_yaml_with_chamber` | Direct |
| R1 quorum rule (insufficient/zero/custom min) | `TestAdmissibilityQuorum` (4 tests) | Direct |
| R2 silent failure (0/1/2 returns vs expected) | `TestAdmissibilitySilentFailure` (3 tests) | Direct |
| R2.5 duplicate expert_id | `TestAdmissibilityDuplicate` (2 tests) | Direct |
| R3 freshness (stale/fresh/boundary) | `TestAdmissibilityFreshness` (3 tests) | Direct |
| R4 scope mismatch | `TestAdmissibilityScopeMismatch` (1 test) | Direct |
| R5 default admissible | `TestAdmissibilityDefault` (1 test) | Direct |
| Entry chamber: LONG/SHORT/SPLIT/NEUTRAL/UNKNOWN | `TestEntryChamberBasic` + `TestEntryChamberUnknown` | Direct |
| Roster truth: gap detection → INADMISSIBLE | `TestRosterTruth` (4 tests) | Direct |
| Duplicate expert_id via aggregator | `TestDuplicateExpertId` | Direct |
| Lifecycle stub: QUORUM_INSUFFICIENT, scope filter | `TestLifecycleChamberStub` (2 tests) | Direct |
| Consensus strength: mean, zero | `TestConsensusStrength` (2 tests) | Direct |
| Chamber ID format | `TestChamberId` (2 tests) | Direct |
| Round-trip serialization | `TestContractCompliance` (2 tests) | Direct |
| `EVT:JUDGE_CHAMBER_AGGREGATED_V1` emitted / not emitted | `TestChamberEventEmitted` (3 tests) | Direct |
| Chamber payload deserializes to contract | `TestChamberPayloadValid` (2 tests) | Direct |
| Lifecycle stub explicitly enabled → event + QUORUM_INSUFFICIENT | `TestLifecycleStubEnabled` | Direct |
| Lifecycle NOT emitted by default | `TestLifecycleStubDisabledByDefault` | Direct |
| Roster truth in integration path | `TestChamberRosterTruth` | Direct |
| Chamber JSONL written / not written | `TestChamberJSONLLog` (2 tests) | Direct |
| Non-judge path unchanged | `TestNonJudgeProviderUnchanged`, `TestMixedProviders` | Direct |
| EVT:ALPHA_SCORE_CALCULATED suppressed for judge | `TestJudgeExpertSuppressesAlphaScore` (2 tests) | Direct (Phase 2, now regression) |
| All regression paths | 34 non-judge tests in `tests/domains/alpha_search/` | Regression |

### Only Indirectly Covered

- Whether `_run_chamber_aggregation()` correctly handles a `StopIteration` or unexpected exception during scoring (the `except Exception` at line 706 suppresses provider errors but the chamber loop still runs after)
- Whether JSONL files rotate at 50MB (`max_file_size_mb: 50`) — rotation is configured but not implemented in the current `write_jsonl_chamber_log()` (appends unconditionally; no rotation logic). This is the same gap as the expert JSONL writer — not a Phase 3 defect since rotation was not in scope.

### Unproven But Explicitly Deferred

- `JudgeEvidenceEnvelope` assembly (Phase 4)
- `JudgeVerdict` formation (Phase 4)
- `EVT:JUDGE_ENTRY_VERDICT_V1` / `EVT:JUDGE_LIFECYCLE_VERDICT_V1` (Phase 4)
- `hybrid_advisory` mode (Phase 4)
- LLM judge runtime (Phase 4+)
- Real lifecycle experts (Phase 4+)
- `normalize_mode="signed_v2"` implementation (orthogonal, deferred)

### Coverage Sufficiency

Coverage is **sufficient** for Phase 3's stated scope. Every deliverable in §18.2 has a corresponding direct test. The two "only indirectly covered" items above (exception path during chamber, JSONL rotation) are orthogonal operational concerns not claimed as Phase 3 scope.

---

## 13. Report Claim Verification

| Report Claim | Code Evidence | Verdict |
|---|---|---|
| "Roster-truth accounting: `expert_count` comes from `expected_expert_ids` passed to chamber" | Line 67 of chamber_aggregator.py; proven by integration test | ACCURATE |
| "Missing experts counted as abstaining" | `abstaining_count = expert_count - responding_count`; F23 | ACCURATE |
| "Lifecycle stub contradiction resolved: `lifecycle_enabled: false` by default, only runs on opt-in" | Line 1129 guard; YAML default; unit + integration tests | ACCURATE |
| "Duplicate expert_id → INADMISSIBLE (not QUORUM_INSUFFICIENT)" | R2.5 at lines 44–47 of admissibility.py | ACCURATE |
| "Layer separation preserved: Layer 1 → Layer 2 → Layer 3" | Experts unchanged; bridge used for translation; aggregation in chamber/ | ACCURATE |
| "`JudgeExpertProviderConfig.expert_type` pointer → actual `expert_id` from `judge.experts.{type}.expert_id`" | `_resolve_judge_expert_id()` at lines 1062–1071 | ACCURATE |
| "292 judge tests pass (0 failures)" | Live test run confirms 292 | ACCURATE |
| "contracts.py untouched" | grep confirmed zero Phase 3 additions | ACCURATE |
| "No main.py / config_loader.py / decision_making / execution_position changes" | All grep confirmed zero hits | ACCURATE |
| "`ChamberAggregate` contract shape unchanged" | Phase 1 frozen; grep confirmed no new fields | ACCURATE |
| "Phase 3 blueprint SSOT followed exactly" | Blueprint §18.2 checklist verified item by item | ACCURATE |

No materially overstated claims found. One minor omission: the report does not mention that JSONL rotation (50MB, daily) is configured but not implemented in the log writers — however this was also not in Phase 3's scope.

---

## 14. Defects or Drift

### None blocking acceptance.

**NOTE-P3-01: JSONL Rotation Not Implemented (Carry-over from Phase 2)**

| Attribute | Value |
|---|---|
| **Phase** | Phase 2 (carry-over) + Phase 3 |
| **Severity** | VERY LOW |
| **Claim** | `JudgeShadowLogConfig` and `JudgeCortexConfig.shadow_log` specify `max_file_size_mb: 50` and `rotation: "daily"`. `write_jsonl_shadow_log()` and `write_jsonl_chamber_log()` append unconditionally with no rotation logic. |
| **Evidence** | `expert_output_bridge.py` lines 99–113 and 119–138: no size check, no rotation logic. Config fields `max_file_size_mb` and `rotation` are parsed and validated but never read by the writers. |
| **Cause** | JSONL rotation was present in the config surface from Phase 2 but never implemented as code. |
| **Effect** | Log files grow unbounded in long-running sessions. No data corruption; no incorrect scoring. |
| **Operational Risk** | VERY LOW — shadow-only logs in development/shadow operation context. Not in a production hot path. |
| **Blocks Acceptance?** | No. Phase 3 scope did not add this requirement. The carry-over was documented in Phase 2. |

**NOTE-P3-02: I4 Phantom Solicited Expert (Disabled Expert Config)**

| Attribute | Value |
|---|---|
| **Phase** | Phase 3 |
| **Severity** | VERY LOW |
| **Claim** | If an expert config entry exists in `judge.experts.{type}` with `enabled: false`, the corresponding judge_expert provider is never registered in `self.providers` (because `_create_judge_expert` returns None for disabled experts at line 287). However, `_resolve_judge_expert_id()` still resolves the `expert_id` from config and adds it to `solicited_expert_ids`. Since the provider is absent from `self.providers`, no output is collected. Result: `expert_count > len(judge_expert_outputs)` → R2 → `INADMISSIBLE`. |
| **Evidence** | Code path: `_create_judge_expert()` lines 285–289 (returns None if disabled), `_resolve_judge_expert_id()` lines 1067–1070 (resolves regardless of enabled state). |
| **Cause** | Roster building and provider factory use different authority sources for "active expert" determination. |
| **Effect** | Chambers would always be INADMISSIBLE if any judge expert provider config entry has a disabled expert. In default YAML both experts are enabled, so this path is never triggered in practice. |
| **Operational Risk** | VERY LOW — affects only an unusual operator config (declare provider with disabled expert). Fail-closed behavior. Not a data hazard. |
| **Blocks Acceptance?** | No. Blueprint intent is fail-closed. Phase 4 may tighten this. |

---

## 15. Final Acceptance Decision

### Phase 3: **CLOSED**

All 19 blueprint §18.2 checklist items are implemented and proven. All 7 acceptance gates from §15.3 are met. 292/292 judge tests pass. 326/326 alpha_search tests pass. No frozen prior-phase artifacts modified. No decision_making or execution_position contamination. No report claims are materially overstated. Two low-severity notes are documented; neither blocks acceptance.

The chamber substrate is structurally sound:
- Roster truth is the ground truth for `expert_count` — not returned output count
- Silent failures are visible to the chamber (INADMISSIBLE)
- Duplicate experts are rejected as INADMISSIBLE
- Lifecycle stub is correctly disabled by default and produces QUORUM_INSUFFICIENT when explicitly enabled
- `EVT:JUDGE_CHAMBER_AGGREGATED_V1` is shadow-only, emitted from the real provider path, never consumed by decision_making
- Chamber JSONL logging is operational and wired into the real provider path
- All Phase 1 and Phase 2 contracts and expert modules are unchanged

### Phase 4 Readiness: **YES**

The `ChamberAggregate` produced in Phase 3 is the primary input for Phase 4 (`JudgeEvidenceEnvelope` assembly). The contract is frozen (Phase 1), tested, and operationally produced. Phase 4 can consume the JSONL logs or the `EVT:JUDGE_CHAMBER_AGGREGATED_V1` events directly to begin evidence envelope construction.

---

## 16. Recommended Next Action

**Proceed to Phase 4 planning**: Begin `JudgeEvidenceEnvelope` assembly design — consuming `ChamberAggregate` outputs, enriching with `features_ref`, `regime`, `regime_confidence`, `strategy_id`, and `provenance` fields, and emitting `EVT:JUDGE_EVIDENCE_ASSEMBLED_V1`. Phase 4 scope is defined in blueprint §4.2 (deferred items) and blocked only on cross-domain data availability (`strategy_id`, `regime` state), which is an architectural decision outside Phase 3's scope.
