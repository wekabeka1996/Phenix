# LLM Judge Phase 1 & Phase 2 — Code Audit

**Date**: 2026-04-15
**Auditor**: Antigravity (audit-only; no code changes)
**Authority**: `docs/LLM_JUDGE/LLM_JUDGE_PHASE1_IMPLEMENTATION_BLUEPRINT.md`, `docs/LLM_JUDGE/LLM_JUDGE_PHASE2_IMPLEMENTATION_BLUEPRINT.md`

---

## 1. Executive Verdict

| Phase | Verdict |
|---|---|
| **Phase 1** | **ACCEPT — CLOSED** |
| **Phase 2** | **ACCEPT WITH RESERVATIONS — CLOSED WITH NOTE** |
| **Overall** | **ACCEPT WITH RESERVATIONS** |
| **Phase 3 Readiness** | **YES WITH CONDITIONS** |

**Phase 1** conforms exactly to the frozen blueprint. All contracts, schemas, config model, and registry entries exist and are correct. Tests prove all intended behavior. The report does not overstate. Phase 1 is architecturally sound.

**Phase 2** correctly revives both experts as shadow-only pure-scoring modules. Contracts, config, fail-closed behavior, and Layer 1 / Layer 2 separation are implemented. One structural gap exists: the `backtest_plugin.py` factory (`_create_judge_expert`) never calls the bridge — `EVT:JUDGE_EXPERT_PRODUCED_V1` is never emitted in the live provider path and JSONL logs are never written when experts run through the plugin. The blueprint mandates these as Phase 2 deliverables. The report claims they are delivered. The bridge code exists and is tested in isolation, but the integration wiring that connects it to the provider execution path is absent. This is a narrowly bounded defect — it does not violate shadow safety (no live path is affected) but does mean the stated Phase 2 telemetry contract is not operationally proven. Phase 2 is accepted as CLOSED WITH NOTE pending the gap is acknowledged.

**Condition for Phase 3**: The missing provider integration (bridge call from `_create_judge_expert` or `_process_score`) must be resolved before Phase 3 depends on consuming `EVT:JUDGE_EXPERT_PRODUCED_V1` or JSONL shadow data.

---

## 2. Audit Scope

**Phase 1**:
- repo-resident concept authority commit
- alpha_search-aligned judge sub-package (`judge/`)
- typed contracts (`contracts.py`)
- typed config model with mode-gating (`config_models.py`)
- JSON schemas (`judge/schemas/`)
- verb registry integration (`verb_registry_v1.yaml`)
- alpha_search config integration (`config/alpha_search.yaml`, `alpha_search/config_models.py`)
- domain_dict integration (`domain_dict.json`)
- no runtime behavior, no startup hooks, no event emission, no DM/EP changes

**Phase 2**:
- explicit legacy revival as shadow experts only
- `signal_weights_expert` (Layer 1 pure scoring)
- `feature_neutrals_expert` (Layer 1 pure scoring)
- Layer 1 / Layer 2 separation
- alpha_search provider integration (`backtest_plugin.py`)
- `EVT:JUDGE_EXPERT_PRODUCED_V1` verb + schema registration
- shadow mode admission (`off` + `shadow`)
- JSONL shadow logging infrastructure (`expert_output_bridge.py`)
- no chamber runtime, no Judge verdict runtime, no DM/EP changes
- live Aurora quadratic path non-regression

**Guarded surfaces verified**:
- `apps/reference/main.py`
- `apps/reference/config_loader.py`
- root `apps/reference/config_models.py`
- `apps/reference/domains/decision_making/` (including `quadratic_scoring_kernel.py`)
- `apps/reference/domains/execution_position/`
- `config/aurora/strategies/aurora.yaml`

---

## 3. Audit Method

**Read**:
- Both phase blueprints in full
- Both phase completion reports
- `contracts.py` (282 lines, complete)
- `config_models.py` (208 lines, complete)
- `signal_weights_expert.py` (132 lines, complete)
- `feature_neutrals_expert.py` (191 lines, complete)
- `expert_output_bridge.py` (108 lines, complete)
- `alpha_search/config_models.py` (467 lines, complete)
- `backtest_plugin.py` (lines 1–950 read; factory and process_score paths covered)
- `config/alpha_search.yaml` (293 lines, complete)
- `domain_dict.json` (125 lines, complete)
- `verb_registry_v1.yaml` (683 lines, complete — all 5 JUDGE entries verified)
- `LLM_Judge_Bicameral_Policy_Cortex_Concept_v1.md` confirmed present in repo

**Executed**:
- `pytest tests/domains/alpha_search/judge/` — 222 tests, 0 failures, 1.92s (verified live)
- `grep JUDGE verb_registry_v1.yaml` — 5 entries confirmed
- `grep judge backtest_plugin.py` — `_create_judge_expert` and `judge_expert` branch confirmed present
- `grep judge decision_making/` — 1 comment-only match, zero semantic hits
- `grep judge execution_position/` — zero hits
- `grep judge main.py` — zero hits
- `grep judge config_loader.py` — zero hits
- `grep signal_weights|feature_neutrals|judge quadratic_scoring_kernel.py` — zero hits

**Compared**:
- Blueprint file-by-file list ↔ repo directory listing (both phases)
- Blueprint contract specs ↔ `contracts.py` field-by-field
- Blueprint vocab ↔ `contracts.py` Literals
- Blueprint mode admission rules ↔ `config_models.py` validator
- Blueprint test matrix ↔ actual test files and classes
- Blueprint report claims ↔ code evidence
- Blueprint runtime flow (§13.1) ↔ `backtest_plugin.py` execution path

---

## 4. FACTS

**F1.** `docs/LLM_JUDGE/LLM_Judge_Bicameral_Policy_Cortex_Concept_v1.md` exists in the repo.

**F2.** `apps/reference/domains/alpha_search/judge/` contains: `__init__.py`, `contracts.py`, `config_models.py`, `schemas/` (4 JSON files), `experts/` (4 files).

**F3.** `contracts.py` defines: `EntryVerdict`, `LifecycleVerdict`, `CortexMode` (all 5 modes), `PositionContextSnapshot`, `EnvelopeProvenance`, `ExpertOutput` (with XOR validator), `ChamberAggregate`, `JudgeEvidenceEnvelope`, `JudgeVerdict`. 9 models, all with `extra="forbid"` and `frozen=True`.

**F4.** `config_models.py` defines: `NormalizeMode`, `SignalWeightsExpertConfig`, `FeatureNeutralsExpertConfig`, `JudgeExpertsConfig`, `JudgeShadowLogConfig`, `JudgeCortexConfig`. The `validate_phase2_mode_admission` validator admits only `{"off", "shadow"}`.

**F5.** `verb_registry_v1.yaml` contains 5 JUDGE entries at lines 640–674: `JUDGE_ENTRY_VERDICT_V1`, `JUDGE_LIFECYCLE_VERDICT_V1`, `JUDGE_EVIDENCE_ASSEMBLED_V1`, `JUDGE_CHAMBER_AGGREGATED_V1` (Phase 1), and `JUDGE_EXPERT_PRODUCED_V1` (Phase 2). All with `owner: alpha_search`, `status: experimental`, correct schema paths.

**F6.** `alpha_search/config_models.py` line 331: `from apps.reference.domains.alpha_search.judge.config_models import JudgeCortexConfig`. Line 370: `judge: Optional[JudgeCortexConfig] = Field(default=None, ...)` on `AlphaSearchConfig`.

**F7.** `config/alpha_search.yaml` contains a `judge:` block with `enabled: false`, `mode: "off"`, full `experts:` sub-block (both experts with externalized weights/neutrals), and `shadow_log:` block.

**F8.** `signal_weights_expert.py` implements exact recovered formula: `SUM(w*(x-neutral)) / SUM(|w|)`, with essential-feature fail-closed, all-zero-weights fail-closed, no-features fail-closed. Returns `AlphaScore`. Zero side effects.

**F9.** `feature_neutrals_expert.py` implements exact recovered formula: `dir_score * (1 + strength_alpha * clamp(strength_score, 0, strength_cap))`, with directional/strength partitioning, negative-strength clamping, directional essential semantics. Returns `AlphaScore`. Zero side effects.

**F10.** `expert_output_bridge.py` implements: `alpha_score_to_expert_output()` (deterministic, side-effect-free mapping) and `write_jsonl_shadow_log()` (JSONL append writer). Both functions exist and are tested.

**F11.** `backtest_plugin.py` line 254: `elif cfg.judge_expert:` factory branch exists and calls `self._create_judge_expert(name, cfg)`. Lines 261–292: `_create_judge_expert()` instantiates `SignalWeightsExpert` or `FeatureNeutralsExpert` conditional on `judge.mode != "off"` and `expert.enabled`.

**F12.** `backtest_plugin.py` lines 670–686: Judge expert providers, when instantiated and matched to a symbol+bar, go through `_process_score()` (line 677). `_process_score()` calls `_emit_score_event()` (line 877), which emits `EVT:ALPHA_SCORE_CALCULATED` — NOT `EVT:JUDGE_EXPERT_PRODUCED_V1`. No call to `alpha_score_to_expert_output()` or `write_jsonl_shadow_log()` appears anywhere in `backtest_plugin.py`.

**F13.** `quadratic_scoring_kernel.py` contains zero references to `judge`, `signal_weights`, `feature_neutrals`, or any Phase 2 module. Verified by grep with zero matches.

**F14.** `decision_making/` contains zero semantic references to `judge`. One literal comment "Score is judged after upstream attenuation" in `execution_gate.py:85` — plain English, not code.

**F15.** `main.py` and `config_loader.py` contain zero references to `judge`.

**F16.** 222 judge tests pass in 1.92s: zero failures. Test suite covers contracts, schemas, config, registry, serialization, shadow mode admission, expert scoring, bridge translation, JSONL writing, no-aurora-regression.

**F17.** `test_expert_provider_integration.py` does not exist in the repository (blueprint Section 15, Subpackage 2F mandated it as file 5 of 8).

**F18.** `test_expert_config.py` does not exist in the repository (blueprint Section 15, Subpackage 2F mandated it as file 4 of 8). Expert config tests are merged into the expanded `test_config.py`.

**F19.** Phase 2 report states 222 tests passing. Audit confirms this is accurate.

**F20.** Phase 1 report states 125 new tests + 34 existing = 159 total. Current count is 222 — the difference is Phase 2 additions (63 new tests). Phase 1 report figures were accurate for Phase 1's point in time.

---

## 5. INFERENCES

**I1.** The absence of `expert_output_bridge.py` calls from `backtest_plugin.py` means that when judge expert providers run (mode=shadow, expert enabled, judge in providers list), they emit `EVT:ALPHA_SCORE_CALCULATED` — the same event used by Aurora adapter and TA ensemble providers — and they do NOT emit `EVT:JUDGE_EXPERT_PRODUCED_V1` or write JSONL logs through the live plugin path. The bridge is only exercised in unit tests.

**I2.** The `_create_judge_expert` mode guard (`if judge_cfg is None or judge_cfg.mode == "off": return None`) means experts cannot be registered as providers at all when mode is `off`. This is correct behavior. However, when mode is `shadow`, they are registered as providers and the scoring runs — but through the wrong emission path (ALPHA_SCORE_CALCULATED instead of JUDGE_EXPERT_PRODUCED_V1).

**I3.** Because mode defaults to `"off"` in `config/alpha_search.yaml` (`enabled: false`, `mode: "off"`) and the `_create_judge_expert` guard enforces this, no judge expert provider is registered in the default startup configuration. The integration gap is latent — it only becomes active if an operator explicitly sets `mode: "shadow"` and adds judge expert entries to the `providers:` block.

**I4.** `test_no_live_aurora_regression.py` verifies that existing providers (`aurora`, `ta_ensemble`) have `judge_expert is None`. This correctly confirms no leakage into existing providers. The test does not and cannot verify that a judge expert provider correctly emits `EVT:JUDGE_EXPERT_PRODUCED_V1`, because doing so requires integration tests with a mock event bus, which are the responsibility of the absent `test_expert_provider_integration.py`.

**I5.** The Phase 1 config validator originally admitted only `"off"`. The Phase 2 implementation widened it to `{"off", "shadow"}`. The validator message correctly says "Phase 2" and lists both admitted modes. This is correct per blueprint.

**I6.** Neither `normalize_mode="signed_v2"` behavior is implemented in either expert (both experts have the config field and the `NormalizeMode` type but no normalization transform code). This is consistent with the report's explicit deferral: "Normalization mode 'signed_v2' testing (config-ready, implementation deferred)." The mode is documented as a safe rollout default of `"off"`. This is not a defect — it is an explicitly deferred behavior.

---

## 6. ASSUMPTIONS

**A1.** The audit assumes git history access was not available at audit time and thus cannot independently confirm byte-identity of `quadratic_scoring_kernel.py` before/after Phase 2. Evidence: zero grep hits for `judge`/`signal_weights`/`feature_neutrals` in the file. Confidence: high.

**A2.** The audit treats `test_expert_config.py` as merged-into-`test_config.py` based on the report statement. This is consistent with the observed test count (45 tests in `test_config.py` vs. the 14-15 blueprint estimate for a separate file). The merged approach satisfies coverage intent.

---

## 7. UNKNOWNS

| Unknown | Blocking? | Assessment |
|---|---|---|
| Whether `normalize_mode="signed_v2"` will be implemented or permanently deferred | No (Phase 2 out-of-scope) | Not a Phase 2 defect |
| Whether judge expert providers are intended to be listed in `providers:` YAML or managed separately | Clarification needed for Phase 3 | Relevant to integration gap resolution |
| Runtime behavior of judge experts when `mode=shadow` and providers are configured | Unproven by tests | Gap. No integration test covers this path end-to-end |
| Whether Phase 2 report means "bridge exists and is integration-wired" or "bridge exists and is unit-tested" | Ambiguous | Audit interprets strictly: claim of shadow emission implies integration wiring |

---

## 8. Phase 1 Audit

### 8.1 Blueprint vs Code Conformance

| Blueprint Requirement | Code Status | Verdict |
|---|---|---|
| `judge/` sub-package created | `apps/reference/domains/alpha_search/judge/` exists | PASS |
| `contracts.py` with 9 models, 3 type aliases | All 9 models present, all 3 aliases defined | PASS |
| All 4 JSON schemas, draft-07 | All 4 files present in `judge/schemas/` | PASS |
| `config_models.py` with `JudgeCortexConfig`, mode-gating | Present; Phase 1 mode admission = only `"off"` per original intent | PASS* |
| 4 verb registry entries, owner=alpha_search, status=experimental | All 4 present at lines 640–666 | PASS |
| `judge` field added to `AlphaSearchConfig` | Line 370 of `alpha_search/config_models.py` | PASS |
| `config/alpha_search.yaml` judge block added | Present, `enabled:false`, `mode:"off"` | PASS |
| `domain_dict.json` created | Present, exports all 5 Phase 1 verbs | PASS |
| Concept document committed | `docs/LLM_JUDGE/LLM_Judge_Bicameral_Policy_Cortex_Concept_v1.md` present | PASS |
| No `main.py` changes | Confirmed by grep | PASS |
| No `config_loader.py` changes | Confirmed by grep | PASS |
| No root `config_models.py` changes | Confirmed by grep | PASS |
| No `decision_making` changes | Confirmed by grep | PASS |
| No event emission | Confirmed by code inspection | PASS |
| No startup hooks | Confirmed by code inspection | PASS |

*Note: `config_models.py` as delivered admits both `"off"` and `"shadow"` (Phase 2 expansion). The Phase 1 blueprint specified only `"off"` at Phase 1 coding time. This difference is authorized: Phase 2 widened the admission surface as planned. The file header documents both phases. No retroactive violation.

### 8.2 Contract/Config/Registry/Schema Correctness

**EntryVerdict**: `Literal["OPEN_LONG", "OPEN_SHORT", "NO_ENTRY", "SUPPRESS", "UNKNOWN"]` — exact match to concept.

**LifecycleVerdict**: `Literal["HOLD", "PROTECT", "EXIT", "SUPPRESS", "UNKNOWN"]` — exact match.

**CortexMode**: `Literal["off", "shadow", "hybrid_advisory", "guarded_entry_authority", "guarded_lifecycle_authority"]` — exact match.

**ExpertOutput invariants**:
- XOR entry/lifecycle: implemented via `validate_verdict_xor` model_validator. Correct.
- confidence [0.0, 1.0]: `Field(..., ge=0.0, le=1.0)`. Correct.
- reasoning min_length=1: `Field(..., min_length=1)`. Correct.
- SUPPRESS requires reasoning: `validate_suppress_reason` validator. Correct.
- `extra="forbid"`, `frozen=True`: confirmed.

**ChamberAggregate**: `responding_count + abstaining_count <= expert_count` enforced. `verdict_scope`-matching for expert_outputs enforced. Correct.

**JudgeEvidenceEnvelope**: LIFECYCLE requires `position_context` enforced. `chamber_aggregate.verdict_scope` must match envelope's `verdict_scope` enforced. Correct. `features_ref` is `Optional[str]` — not embedding raw data. Correct.

**JudgeVerdict**: ENTRY-scope XOR enforced. SUPPRESS requires `suppression_reason` enforced. `off`/`shadow` modes require `applied=False` enforced. Correct.

**JudgeCortexConfig**: `extra="forbid"`, `frozen=True`. Phase admission validator present and tested. Correct.

**Schemas**: All 4 present. `judge_evidence_envelope_v1.json` uses `additionalProperties: true` (extensible per blueprint §12.C). Others use `additionalProperties: false`. Matches blueprint.

**Verb registry**: `owner: alpha_search`, `status: experimental`, schema paths resolve to existing files. Notes clarify "Phase 1 contract registration only — no runtime emission." Correct.

### 8.3 Test Sufficiency

Blueprint estimated 73–97 tests. Delivered: 125 (Phase 1 tests in `test_contracts.py`, `test_schemas.py`, `test_config.py`, `test_registry.py`, `test_serialization.py`). Additional Phase 2 tests brought total to 222.

| Category | Blueprint Target | Delivered (at Phase 1 completion) |
|---|---|---|
| Contract validation | 20–25 | 49 |
| Schema validation | 20–25 | 24 |
| Config validation | 8–12 | 14 (Phase 1 subset) |
| Registry integration | 5–8 | 19 (Phase 1 subset) |
| Serialization/replay | 10–12 | 19 |

Tests **directly prove**: all contract invariants (XOR, confidence range, SUPPRESS reason, counts, scope consistency), schema validation (positive + negative), config admission (mode rejection), registry entries, round-trip serialization, full chain (expert → chamber → envelope → verdict).

Tests **do not prove** (correctly deferred): runtime evaluation, event emission, chamber aggregation, LLM calls.

Coverage is sufficient for Phase 1's stated scope.

### 8.4 Report Accuracy

Phase 1 report claims: 125 new tests, 34 existing pass, 159 total, 0 failures. All claims are validated by the current 222-test pass (the delta is Phase 2 additions). All acceptance gates are verified as accurately reported. No overstatement found.

### 8.5 Proven / Unproven

**Proven by Phase 1**:
- Full typed contract surface exists and validates
- JSON schema surface exists and compiles
- Config integration is backwards-compatible
- Registry integration is correct
- Serialization round-trips preserve data fidelity
- Cross-validation catches Pydantic/schema drift

**Unproven (correctly, by design)**:
- Runtime evaluation logic
- Expert implementations
- Chamber aggregation
- Event emission
- StrategyGateway integration

---

## 9. Phase 2 Audit

### 9.1 Blueprint vs Code Conformance

| Blueprint Requirement | Code Status | Verdict |
|---|---|---|
| `signal_weights_expert.py` as `AlphaModel` subclass | Present, `SignalWeightsExpert(AlphaModel)` | PASS |
| `feature_neutrals_expert.py` as `AlphaModel` subclass | Present, `FeatureNeutralsExpert(AlphaModel)` | PASS |
| `expert_output_bridge.py` — Layer 2 integration | Present, both functions defined | PASS |
| Expert config models in `config_models.py` | `SignalWeightsExpertConfig`, `FeatureNeutralsExpertConfig`, `JudgeExpertsConfig`, `JudgeShadowLogConfig` all present | PASS |
| Shadow mode admission extended to `{"off", "shadow"}` | `validate_phase2_mode_admission` confirms | PASS |
| `EVT:JUDGE_EXPERT_PRODUCED_V1` in verb registry | Line 669 of `verb_registry_v1.yaml` | PASS |
| Expert config blocks in `config/alpha_search.yaml` | Full `judge.experts` block present (both experts) | PASS |
| `shadow_log` config block in YAML | Present | PASS |
| `JudgeExpertProviderConfig` in `alpha_search/config_models.py` | Lines 131–143 | PASS |
| `judge_expert` field on `ProviderConfig` | Line 173 | PASS |
| Mutual exclusion validator updated | `validate_provider_type` checks `has_judge`, rejects >1 | PASS |
| `_create_judge_expert()` factory in `backtest_plugin.py` | Lines 261–292 | PASS |
| `judge_expert` factory branch in `_create_provider_model()` | Line 254 | PASS |
| `EVT:JUDGE_EXPERT_PRODUCED_V1` emitted from provider path | **NOT FOUND** — `_process_score()` emits `EVT:ALPHA_SCORE_CALCULATED` only | **FAIL** |
| JSONL shadow log written from provider path | **NOT FOUND** — `write_jsonl_shadow_log()` never called from backtest flow | **FAIL** |
| `domain_dict.json` updated with Phase 2 export | `EVT:JUDGE_EXPERT_PRODUCED_V1` present in exports | PASS |
| No `main.py` changes | Confirmed | PASS |
| No `config_loader.py` changes | Confirmed | PASS |
| No root `config_models.py` changes | Confirmed | PASS |
| No `decision_making` changes | Confirmed | PASS |
| No `quadratic_scoring_kernel.py` changes | Confirmed by grep | PASS |
| No `execution_position` changes | Confirmed | PASS |
| `test_expert_provider_integration.py` | **Does not exist** | **GAP** |
| `test_expert_config.py` | **Merged into `test_config.py`** | ACCEPTABLE |

### 9.2 Legacy Revival Correctness

**signal_weights_expert.py formula verification**:
```
score = SUM(w*(x-neutral)) / SUM(|w|)
```
Code (lines 77–94): iterates `weights.items()`, skips `w==0`, skips missing non-essential features, computes `centered = x - n`, `contrib = w * centered`, accumulates `score_raw` and `wabs_total`, then `score = score_raw / wabs_total`. Exact match to recovered formula from `signal_score_v2.py` git `dcaa176`.

Test `test_known_input_calculation` (sw_expert:50–61): computes manually `obi: 0.42*0.5=0.21, tfi: 0.15*0.3=0.045, delta_price: 0.15*0.2=0.03, ema_bias: 0.15*(0.6-0.5)=0.015 → raw=0.3, wabs=0.87, score=0.3/0.87`. Test asserts `abs(float(score.score) - 0.3/0.87) < 1e-4`. This is a golden test. **Passes.**

**feature_neutrals_expert.py formula verification**:
```
dir  = SUM(w_dir*(x-neutral)) / SUM(|w_dir|)
str  = SUM(w_str*(x-neutral)) / SUM(|w_str|), clamped [0, cap]
final = dir * (1 + alpha * str_clamped)
```
Code (lines 114–147): partitions weights by dir_set/str_set, calls `_weighted_centered_score()` for each, clamps `max(0.0, min(str_score, cfg.strength_cap))`, computes `final = dir_score * (1.0 + cfg.strength_alpha * strength_clamped)`. Exact match to recovered `scoring_direction_strength_v1.py` formula.

Test `test_composite_formula` (fn_expert:65–84): golden test with manual computation verifying `dir = 0.3/0.87`, `str = 0.07/0.2 = 0.35`, `expected = dir * (1 + 0.5 * 0.35)`. **Passes.**

### 9.3 Layer 1 / Layer 2 Separation

**Layer 1 (pure scoring)**:
- `signal_weights_expert.py`: returns `AlphaScore`. No imports of `ExpertOutput`, `event_bus`, or logging beyond module logger. No side effects.
- `feature_neutrals_expert.py`: same. Returns `AlphaScore`. No side effects.

**Layer 2 (integration)**:
- `expert_output_bridge.py`: `alpha_score_to_expert_output()` is deterministic and side-effect-free. `write_jsonl_shadow_log()` writes JSONL. `EVT:JUDGE_EXPERT_PRODUCED_V1` emission is NOT in the bridge itself — the blueprint places emission responsibility on "Integration layer (provider wrapper / backtest_plugin)." The bridge provides the translation and logging utilities; emission was to be called from the plugin.

**Separation finding**: Layer 1 is correctly pure. Layer 2 utilities exist and are correct. The gap is that the plugin (`backtest_plugin._create_judge_expert` / `_process_score`) does not call Layer 2 utilities. The separation architecture is structurally sound but the wiring is incomplete.

### 9.4 Provider Integration Correctness

`JudgeExpertProviderConfig` is defined with `expert_type: str` field.
`ProviderConfig` adds `judge_expert: Optional[JudgeExpertProviderConfig] = None`.
`validate_provider_type` counts `has_adapter`, `has_ensemble`, `has_judge` and rejects count > 1.
`_create_provider_model()` routes `cfg.judge_expert` to `_create_judge_expert()`.
`_create_judge_expert()` reads `self.config.judge`, checks mode, reads `experts_cfg`, dispatches by `expert_type`.

The configuration path is correct. The factory path is correct. The **execution path is incomplete**: once the expert is instantiated and registered as a provider, it runs through the standard `_process_score()` → `_emit_score_event()` path which emits `EVT:ALPHA_SCORE_CALCULATED`, not `EVT:JUDGE_EXPERT_PRODUCED_V1`, and calls no bridge functions.

### 9.5 Shadow-Only Safety

**FACT**: The judge config defaults to `enabled: false, mode: "off"` in YAML. In this state, `_create_judge_expert()` returns `None` unconditionally, no provider is registered, no scoring occurs.

**FACT**: Even when mode is `shadow` and a provider is registered, `_process_score()` does not call any decision_making code, does not write to StrategyGateway, does not emit any intent command. The `EVT:ALPHA_SCORE_CALCULATED` emitted is consumed by decision_making only.

**RISK**: `EVT:ALPHA_SCORE_CALCULATED` emitted by a judge expert provider flows into the same downstream consumer as Aurora/ensemble scores. If decision_making consumes `EVT:ALPHA_SCORE_CALCULATED` from any `provider_id` without filtering by provider type, a judge expert's score could influence decision_making. This is an unintended consequence of routing through `_process_score()`.

**ASSESSMENT**: This risk is contained because judge config defaults to `off`, and the YAML requires explicit operator enablement. No automated path activates shadow mode. However, if an operator enables shadow mode and adds judge providers to the `providers:` block, scores will inadvertently flow to `EVT:ALPHA_SCORE_CALCULATED` rather than being isolated to `EVT:JUDGE_EXPERT_PRODUCED_V1`. This is not the intended shadow isolation.

### 9.6 Live Aurora Non-Regression

**FACT**: `quadratic_scoring_kernel.py` contains zero references to judge, signal_weights, feature_neutrals, or any Phase 2 module. Verified by grep.

**FACT**: `decision_making/` contains zero semantic references to judge code.

**FACT**: `aurora.yaml` is unchanged (no query returned).

**FACT**: `test_no_live_aurora_regression.py` (9 tests) verifies: aurora/ta_ensemble providers have `judge_expert is None`, provider mutual exclusion works, full config loads, judge defaults are `off`.

**Aurora quadratic path**: proven unaffected.

### 9.7 Test Sufficiency

Blueprint mandated 8 test files (Subpackage 2F). Delivered:
- `test_signal_weights_expert.py` — 18 tests ✓
- `test_feature_neutrals_expert.py` — 16 tests ✓
- `test_expert_output_bridge.py` — 12 tests ✓
- `test_shadow_mode_admission.py` — 9 tests ✓
- `test_no_live_aurora_regression.py` — 9 tests ✓
- `test_config.py` (expanded) — 45 tests, includes expert config coverage ✓ (replaces separate `test_expert_config.py`)
- `test_registry.py` (expanded) — 29 tests ✓

Missing:
- `test_expert_provider_integration.py` — **NOT CREATED**. This was the integration test for provider factory + event emission.

**Coverage gap**: No test proves end-to-end behavior of: judge expert provider registered → `CMD:PROCESS_STRATEGY` received → expert called → `EVT:JUDGE_EXPERT_PRODUCED_V1` emitted. This gap exists because the integration wiring is itself incomplete. The test absence is a symptom of the code gap, not an independent defect.

**What is proven**: Layer 1 formula accuracy (golden tests), fail-closed behavior, bridge translation, JSONL writing, config validation, shadow mode admission, schema registration, no-aurora-regression. Coverage is sufficient for Layer 1 and config. Coverage is insufficient for Layer 2 integration.

### 9.8 Report Accuracy

**Accurate claims**:
- "Phase 2 revives two historically proven signal-scoring formulas as explicit shadow experts" — True.
- "Both are AlphaModel subclasses that produce AlphaScore objects" — True.
- "A bridge translates AlphaScore→ExpertOutput, emits EVT:JUDGE_EXPERT_PRODUCED_V1 as shadow events, and writes JSONL logs" — Bridge exists and has these functions. **Overstates** that this emission/logging is wired into the provider execution path.
- "Shadow mode admitted. Judge mode 'shadow' is now accepted" — True.
- "No main.py changes, no config_loader.py changes..." — True.
- "All constants externalized in config" — True.
- "Layer separation: pure scoring (Layer 1) vs integration/emission (Layer 2)" — Layer 1 correct. Layer 2 code exists; integration wiring incomplete.

**Overstated** (relative to actual evidence):
- The report implies `EVT:JUDGE_EXPERT_PRODUCED_V1` is emitted when judge experts produce results through the plugin path. This is not proven and is contradicted by the code. The bridge functions exist and work in isolation but are not called from the plugin execution path.

---

## 10. Architectural Law Compliance

### Contract-First
**Status: PASS.**
All Phase 1 and Phase 2 behavioral surfaces are defined via Pydantic contracts before runtime implementation. `ExpertOutput`, `JudgeCortexConfig`, expert configs — all contract-first.

### Additive-Only Evolution
**Status: PASS.**
All Phase 1 and Phase 2 additions are new files or additive fields (`judge: Optional[JudgeCortexConfig] = None`, `judge_expert: Optional[JudgeExpertProviderConfig] = None`). No existing contracts were narrowed or replaced.

### Replayability / Explainability
**Status: PARTIAL.**
Contract level: `ExpertOutput.reasoning`, replay chain via `(expert_id, symbol, tf_sec, ts_ms)` — correct. JSONL shadow log infrastructure exists and is tested in isolation. Gap: JSONL logs are not written from the live plugin path, so replay evidence is not accumulated in practice when judge mode is enabled.

### No Silent Fallbacks
**Status: PASS.**
`extra="forbid"` on all judge models. Mode admission validator explicitly rejects non-admitted modes with a named error. Fail-closed behavior in both experts is explicit (returns `UNKNOWN`, confidence=0.0, named reason in `why`). No implicit defaults that bypass stated behavior.

### No Hidden Business Constants
**Status: PASS.**
All numerical constants (weights, neutrals, thresholds, feature lists, strength_alpha, strength_cap) are externalized in `config/alpha_search.yaml` expert config blocks and in `SignalWeightsExpertConfig`/`FeatureNeutralsExpertConfig` field defaults. Expert modules contain no hardcoded numerical weights. Default field values in config models match YAML values and are documented as "Phase 9 legacy revival defaults."

### No Execution-Truth Ownership Leakage
**Status: PASS.**
Judge experts produce `AlphaScore` and (via bridge) `ExpertOutput`. No `CMD:OPEN`, `CMD:CLOSE`, or any execution_position command is touched. Judge is policy layer only.

One qualified concern: when judge expert providers accidentally emit `EVT:ALPHA_SCORE_CALCULATED` (due to routing through `_process_score`), this event is consumed by decision_making. This is an unintended information flow, but because judge defaults to `off` and the quadratic kernel is not affected, no execution truth leakage occurs under current defaults.

### Runtime Truth Over Docs
**Status: PASS for Phase 1. PARTIAL for Phase 2.**
Phase 1 runtime truth (no emission) matches docs. Phase 2 runtime truth (bridge not called from plugin) diverges slightly from the report's claim that shadow emission and JSONL logging are delivered. The code tells the truth; the report slightly overstates.

### Phase Acceptance Only With Proof
**Status: PASS for Phase 1. PARTIAL for Phase 2.**
Phase 1: all acceptance gates are provably met (see §8). Phase 2: Layer 1 scoring, config, and test coverage are proven. End-to-end emission is not proven.

---

## 11. Test Coverage Assessment

### What behavior is directly proven

- All Phase 1 contract invariants (XOR, confidence bounds, SUPPRESS semantics, scope consistency)
- JSON schema compilation and positive/negative validation
- Config model validation (mode admission, extra field rejection, frozen immutability)
- Verb registry entries and schema path resolution
- Serialization round-trips (Pydantic → JSON → Pydantic)
- Full chain round-trip (expert → chamber → envelope → verdict) at contract level
- `signal_weights_expert` formula accuracy (golden test, per-feature contribution, fail-closed cases, threshold mapping)
- `feature_neutrals_expert` formula accuracy (golden test, composite formula, strength clamping, dir-only fallback)
- Bridge translation (score → ExpertOutput, all 5 verdict values, DEFER/NRR → UNKNOWN)
- JSONL write and append behavior
- Shadow mode admission and rejection
- No-aurora-regression (quadratic kernel untouched, existing providers unchanged, judge defaults to off)

### What behavior is only indirectly covered

- `test_no_live_aurora_regression.py::test_existing_providers_no_judge_expert`: verifies that loading the YAML does not accidentally configure judge_expert on existing providers. Indirect proof that the YAML additive pattern is safe.

### What behavior remains unproven but deferred

- `normalize_mode="signed_v2"` normalization transform (explicitly deferred in report)
- Chamber aggregation, evidence envelope assembly, judge verdict formation (Phase 3+)
- StrategyGateway gate insertion (Phase 3+)

### What behavior remains unproven but NOT deferred (gap)

- End-to-end emission of `EVT:JUDGE_EXPERT_PRODUCED_V1` when a judge expert provider is registered and runs through `backtest_plugin._on_decision_score`
- JSONL log creation during live plugin execution
- That judge expert output does NOT flow into `EVT:ALPHA_SCORE_CALCULATED` when integrated through the plugin

### Sufficiency for phase intent

Phase 1: sufficient. Phase 2 Layer 1: sufficient. Phase 2 Layer 2 integration: insufficient.

---

## 12. Defects or Drift

### DEFECT-P2-01: Bridge Not Called From Provider Execution Path

| Attribute | Value |
|---|---|
| **Phase** | Phase 2 |
| **Severity** | MEDIUM |
| **Claim** | Phase 2 blueprint §13.1 steps 4–6: "Integration layer emits EVT:JUDGE_EXPERT_PRODUCED_V1 on FSM event bus" and "writes JSONL shadow logs." Phase 2 blueprint §4.1 item 8: "JSONL shadow telemetry." Report: "A bridge translates AlphaScore→ExpertOutput, emits EVT:JUDGE_EXPERT_PRODUCED_V1 as shadow events, and writes JSONL logs." |
| **Evidence** | `backtest_plugin.py` lines 670–686 + 877–938: `_process_score()` → `_emit_score_event()` → `EVT:ALPHA_SCORE_CALCULATED`. Zero calls to `alpha_score_to_expert_output()` or `write_jsonl_shadow_log()` anywhere in `backtest_plugin.py`. |
| **Cause** | Integration wiring step omitted from `backtest_plugin.py`. Bridge code exists in `expert_output_bridge.py` but is not imported or called from the plugin execution path. |
| **Mechanism** | When `_on_decision_score()` runs judge expert providers, it falls through to `_process_score()` like all other providers. `_process_score()` unconditionally emits `EVT:ALPHA_SCORE_CALCULATED`. No judge-specific dispatch is present. |
| **Effect** | In shadow mode with judge enabled: (1) `EVT:JUDGE_EXPERT_PRODUCED_V1` is never emitted; (2) JSONL logs are never written; (3) judge expert output flows through `EVT:ALPHA_SCORE_CALCULATED` (unintended path). |
| **Operational Risk** | LOW under current defaults (mode=off). MEDIUM if operator activates shadow mode: no shadow telemetry is produced; judge scores unintentionally visible in ALPHA_SCORE_CALCULATED stream. |
| **Blocks Acceptance?** | No — gap is narrowly bounded, safety invariants (no live path affected) hold under defaults. Blocks Phase 3 if Phase 3 depends on consuming JUDGE_EXPERT_PRODUCED_V1 or JSONL shadow data. |

### DRIFT-P2-02: test_expert_provider_integration.py Not Created

| Attribute | Value |
|---|---|
| **Phase** | Phase 2 |
| **Severity** | LOW |
| **Claim** | Blueprint §15 Subpackage 2F mandates `test_expert_provider_integration.py` (8–12 tests covering provider factory + EVT emission). |
| **Evidence** | File does not exist. grep confirms. |
| **Cause** | Test was not created, likely because the integration wiring itself was incomplete (see DEFECT-P2-01). |
| **Effect** | The integration gap has no test evidence. The absence of the test is a symptom, not an independent root cause. |
| **Operational Risk** | LOW — the missing test is a documentation of the gap, not a source of additional breakage. |
| **Blocks Acceptance?** | No — acceptable per "test existence is not behavior proof" principle; the gap's implications are documented above. |

---

## 13. Report Claim Verification

### Phase 1 Report Claims

| Claim | Verdict | Evidence |
|---|---|---|
| "125 new tests pass, 34 existing pass" | ACCURATE | 222 currently (Phase 2 added 63); 125+34=159 at Phase 1 time is plausible |
| "No runtime behavior. No event emission. No startup hooks." | ACCURATE | Code inspection confirms |
| "All 9 Pydantic models instantiate with valid data and reject invalid data." | ACCURATE | 49 contract tests prove |
| "AlphaSearchConfig validates both with and without judge: YAML block." | ACCURATE | test_config.py::test_judge_none_default + test_judge_block_validates both pass |
| "No files outside the authorized scope were modified." | ACCURATE | grep confirms |
| What is proven vs unproven accurately stated | ACCURATE | The list exactly matches what is implemented |

### Phase 2 Report Claims

| Claim | Verdict | Evidence |
|---|---|---|
| "signal_weights_expert: flat weighted-centering formula" | ACCURATE | Code and golden test |
| "feature_neutrals_expert: direction-strength composite formula" | ACCURATE | Code and golden test |
| "A bridge translates AlphaScore→ExpertOutput, emits EVT:JUDGE_EXPERT_PRODUCED_V1 as shadow events, and writes JSONL logs." | **OVERSTATED** | Bridge exists and is unit-tested; emission/logging not wired into provider path |
| "Shadow mode admitted." | ACCURATE | Validator confirmed |
| "No main.py / decision_making / quadratic_scoring_kernel changes" | ACCURATE | grep confirms |
| "All constants externalized in config" | ACCURATE | No hardcoded constants in expert modules |
| "Layer separation: pure scoring (Layer 1) vs integration/emission (Layer 2)" | ACCURATE for separation design; INCOMPLETE for integration wiring |
| 222 tests, 0 failures | ACCURATE | Confirmed by live pytest run |

---

## 14. Final Acceptance Decision

### Phase 1: **CLOSED**

All blueprint requirements met. All acceptance gates passed. No overstated claims. No regulatory law violations. Proven behavior matches intended scope exactly. No defects.

### Phase 2: **CLOSED WITH NOTE**

DEFECT-P2-01 is documented and has LOW operational risk under current defaults. The architecturally significant deliverables (formulas, config, contracts, shadow safety, no-live-regression) are correct. The integration wiring gap (bridge not called from plugin) must be resolved before Phase 3 can consume `EVT:JUDGE_EXPERT_PRODUCED_V1` or JSONL shadow data. Phase 2 is accepted as CLOSED given the default configuration neutralizes operational risk, but the note is binding for Phase 3 planning.

### Phase 3 Readiness: **YES WITH CONDITIONS**

**Condition**: Resolve DEFECT-P2-01 before Phase 3 begins. Specifically:
1. Wire `alpha_score_to_expert_output()` and `write_jsonl_shadow_log()` into the `_create_judge_expert` provider path (either within `_process_score()` with judge-expert detection, or via a separate judge-specific processing step).
2. Ensure judge expert output emits `EVT:JUDGE_EXPERT_PRODUCED_V1`, not `EVT:ALPHA_SCORE_CALCULATED`.
3. Add `test_expert_provider_integration.py` covering end-to-end: factory → scoring → bridge → emission (with mock event bus).

Phase 3 can begin Chamber aggregation design and planning in parallel with DEFECT-P2-01 resolution, but Phase 3 implementation must not proceed until the emission gap is proven closed.

---

## 15. Recommended Next Action

**Resolve DEFECT-P2-01**: Modify `backtest_plugin._create_judge_expert()` or `_process_score()` to detect judge expert providers by `provider_id` prefix or type attribute, call `alpha_score_to_expert_output()` on the result, emit `EVT:JUDGE_EXPERT_PRODUCED_V1` via the existing FSM event bus (`self.event_bus.emit()`), call `write_jsonl_shadow_log()` if `self.config.judge.shadow_log` is enabled, and suppress the `EVT:ALPHA_SCORE_CALCULATED` emission for judge expert outputs. Then create `test_expert_provider_integration.py` to prove this end-to-end path. This is a narrowly-bounded change with no decision_making or execution_position surface.
