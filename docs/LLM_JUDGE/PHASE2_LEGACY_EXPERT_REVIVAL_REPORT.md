# LLM Judge Phase 2 — Legacy Expert Revival Report

**Date**: 2026-04-14
**Authority**: `docs/LLM_JUDGE/LLM_JUDGE_PHASE2_IMPLEMENTATION_BLUEPRINT.md`
**Branch**: `Phenix_v2`
**Verdict**: **DONE**

---

## Summary

Phase 2 revives two historically proven signal-scoring formulas as explicit shadow experts under the LLM Judge cortex:

1. **signal_weights_expert** — flat weighted-centering formula (`SUM(w*(x-n)) / SUM(|w|)`)
2. **feature_neutrals_expert** — direction-strength composite formula (`dir * (1 + α * clamp(str, 0, cap))`)

Both are AlphaModel subclasses that produce `AlphaScore` objects. A bridge translates `AlphaScore → ExpertOutput` (Phase 1 contract), emits `EVT:JUDGE_EXPERT_PRODUCED_V1` as shadow events, and writes JSONL logs.

**Shadow mode admitted.** Judge mode "shadow" is now accepted by config validation. Mode "off" remains the safe default. All non-shadow, non-off modes remain rejected.

---

## Test Results

| Category | File | Tests | Status |
|---|---|---|---|
| Signal Weights Expert | `test_signal_weights_expert.py` | 18 | PASS |
| Feature Neutrals Expert | `test_feature_neutrals_expert.py` | 16 | PASS |
| Expert Output Bridge | `test_expert_output_bridge.py` | 12 | PASS |
| Config (Phase 1 + Phase 2) | `test_config.py` | 45 | PASS |
| Shadow Mode Admission | `test_shadow_mode_admission.py` | 9 | PASS |
| No Live Aurora Regression | `test_no_live_aurora_regression.py` | 9 | PASS |
| Contracts (Phase 1) | `test_contracts.py` | 48 | PASS |
| Schemas (Phase 1) | `test_schemas.py` | 24 | PASS |
| Registry (Phase 1 + Phase 2) | `test_registry.py` | 29 | PASS |
| Serialization (Phase 1) | `test_serialization.py` | 12 | PASS |
| **Total** | | **222** | **0 failures** |

---

## Files Created

| File | Purpose |
|---|---|
| `judge/experts/__init__.py` | Sub-package init |
| `judge/experts/signal_weights_expert.py` | Layer 1: flat weighted-centering scoring |
| `judge/experts/feature_neutrals_expert.py` | Layer 1: direction-strength composite scoring |
| `judge/experts/expert_output_bridge.py` | Layer 2: AlphaScore→ExpertOutput, JSONL log writer |
| `tests/.../experts/__init__.py` | Test sub-package |
| `tests/.../experts/test_signal_weights_expert.py` | 18 tests |
| `tests/.../experts/test_feature_neutrals_expert.py` | 16 tests |
| `tests/.../experts/test_expert_output_bridge.py` | 12 tests |
| `tests/.../test_shadow_mode_admission.py` | 9 tests |
| `tests/.../test_no_live_aurora_regression.py` | 9 tests |

## Files Modified

| File | Change |
|---|---|
| `judge/config_models.py` | Added SignalWeightsExpertConfig, FeatureNeutralsExpertConfig, JudgeExpertsConfig, JudgeShadowLogConfig. Extended JudgeCortexConfig with experts/shadow_log fields. Phase 2 mode admission (off + shadow). |
| `alpha_search/config_models.py` | Added JudgeExpertProviderConfig. Extended ProviderConfig with judge_expert third option + updated mutual exclusion. |
| `alpha_search/backtest_plugin.py` | Added judge expert factory branch in `_create_provider_model()` + `_create_judge_expert()` method. |
| `dictionaries/verb_registry_v1.yaml` | Added EVT:JUDGE_EXPERT_PRODUCED_V1 (experimental, schema: expert_output_v1.json). |
| `alpha_search/domain_dict.json` | Added Phase 2 export, components, and SSOT notes. |
| `config/alpha_search.yaml` | Expanded judge block with experts (signal_weights, feature_neutrals) and shadow_log. |
| `tests/.../test_config.py` | Updated for Phase 2: shadow admitted, new expert config tests. |
| `tests/.../test_registry.py` | Added Phase 2 verb tests, removed deferred-in-phase1 assertion for EXPERT_PRODUCED. |

---

## Frozen Decisions Honored

1. No main.py changes
2. No config_loader.py changes
3. No root config_models.py changes
4. No decision_making changes
5. No execution_position changes
6. No quadratic_scoring_kernel.py changes
7. No chamber/verdict runtime
8. All constants externalized in config (weights, neutrals, thresholds, feature lists)
9. normalize_mode "off" as safe default
10. Layer separation: pure scoring (Layer 1) vs integration/emission (Layer 2)

---

## Architecture

```
EVT:FEATURES_CALCULATED → backtest_plugin → _create_judge_expert()
    → SignalWeightsExpert.calculate_alpha()  → AlphaScore
    → FeatureNeutralsExpert.calculate_alpha() → AlphaScore
    → expert_output_bridge.alpha_score_to_expert_output() → ExpertOutput
    → EVT:JUDGE_EXPERT_PRODUCED_V1 (shadow emission)
    → JSONL: logs/judge_experts/{expert_id}_{symbol}_{date}.jsonl
```

**No downstream consumption.** No chamber, no verdict, no gate. Output is observed and logged only.

---

## Deferred to Phase 3

- Chamber aggregation of expert outputs
- Evidence envelope assembly
- Judge verdict formation
- StrategyGateway gate insertion
- Shadow telemetry domain integration (formal)
- Normalization mode "signed_v2" testing (config-ready, implementation deferred)
