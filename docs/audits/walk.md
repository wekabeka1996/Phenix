# Phase 9 Quadratic Brain — Final Migration Report

**Date:** 2026-03-13 | **Status:** ✅ MIGRATION COMPLETE

---

## 1. Execution Strategy

Executed in two passes:
- **Package A** (prior session): config flip + fail-closed + Pydantic models
- **Package C** (this session): reality check first, then purge + fix + annotate

Reality check revealed the **compute_pillars bug** (worse than expected) which was fixed before any purge.

---

## 2. Files Changed

| File | Change |
|---|---|
| [config/aurora/strategies/aurora.yaml](file:///c:/Users/user/Music/Phenix/config/aurora/strategies/aurora.yaml) | `scoring_version → "quadratic"`, `scoring_engine` shields block, v2 surfaces annotated |
| [apps/reference/domains/decision_making/aurora_decision.py](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/aurora_decision.py) | Silent v2 crash fallback removed; [AuroraScoringKernel](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/aurora_scoring_kernel.py#86-338) import demoted to comment |
| [apps/reference/domains/feature_engineering/feature_engineering.py](file:///c:/Users/user/Music/Phenix/apps/reference/domains/feature_engineering/feature_engineering.py) | [compute_pillars](file:///c:/Users/user/Music/Phenix/apps/reference/domains/feature_engineering/calculation_engine.py#1226-1338) dual-path fixed — except TypeError removed, canonical (state) path always used, [update_pillar_candle](file:///c:/Users/user/Music/Phenix/apps/reference/domains/feature_engineering/calculation_engine.py#1174-1225) runs every bar (not just init) |
| [apps/reference/domains/decision_making/aurora_scoring_kernel.py](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/aurora_scoring_kernel.py) | Deprecation notice added |
| [apps/reference/domains/decision_making/scoring_direction_strength_v1.py](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/scoring_direction_strength_v1.py) | Deprecation notice added |
| [apps/reference/config_models.py](file:///c:/Users/user/Music/Phenix/apps/reference/config_models.py) | [ScoringEngineConfig](file:///c:/Users/user/Music/Phenix/apps/reference/config_models.py#935-965), [DangerZoneShieldConfig](file:///c:/Users/user/Music/Phenix/apps/reference/config_models.py#2862-2879), [ContextShieldConfig](file:///c:/Users/user/Music/Phenix/apps/reference/config_models.py#2773-2823), [MemoryShieldConfig](file:///c:/Users/user/Music/Phenix/apps/reference/config_models.py#2825-2860) added |
| [tests/integration/test_pillar_to_decision_e2e.py](file:///c:/Users/user/Music/Phenix/tests/integration/test_pillar_to_decision_e2e.py) | Updated expected `final_exposure` (0.64→0.384) to reflect real shield attenuation |

---

## 3. What Was Verified vs Changed

| Item | Result |
|---|---|
| `scoring_version = "quadratic"` in aurora.yaml | ✅ Verified live, confirmed via `KERNEL_DIAG: engine=quadratic_v1` log |
| [ShieldCascade(['DangerZoneShield', 'ContextShield', 'MEMORY'])](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/shields/base.py#86-142) activated | ✅ Confirmed in test log |
| Silent v2 crash fallback removed | ✅ Verified — no `QUADRATIC_FALLBACK` string in codebase |
| [AuroraScoringKernel](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/aurora_scoring_kernel.py#86-338) no longer imported as active runtime | ✅ Demoted to comment-only import of [ScoringResult](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/aurora_scoring_kernel.py#43-72) |
| [compute_pillars](file:///c:/Users/user/Music/Phenix/apps/reference/domains/feature_engineering/calculation_engine.py#1226-1338) canonical path | ✅ Fixed — was calling wrong signature first, always failing silently into TypeError cascade |
| [ExecutionGate](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/execution_gate.py#16-212) wiring | ✅ Verified wired in aurora_decision.py:716, 928 |
| [ExitManager](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/exit_manager.py#21-286) wiring | ✅ Verified wired in aurora_decision.py:590 |
| Startup / warmup / readiness | ✅ No regressions — `startup_warmup.py` path unchanged |
| MR / md_amr compatibility | ✅ 5213/5214 tests pass including all shared contracts |

---

## 4. Legacy v2 Surfaces Removed / Demoted

| Surface | Action |
|---|---|
| `aurora_decision.py:396-409` — silent v2 fallback | **REMOVED** — replaced with fail-closed |
| [AuroraScoringKernel](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/aurora_scoring_kernel.py#86-338) active import | **DEMOTED** — [ScoringResult](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/aurora_scoring_kernel.py#43-72) still imported for type annotations |
| `feature_engineering.py:955-957` — wrong [compute_pillars(bars, symbol, tf_sec)](file:///c:/Users/user/Music/Phenix/apps/reference/domains/feature_engineering/calculation_engine.py#1226-1338) call | **REMOVED** |
| `feature_engineering.py:962` — [update_pillar_candle](file:///c:/Users/user/Music/Phenix/apps/reference/domains/feature_engineering/calculation_engine.py#1174-1225) inside `if state is None` | **PROMOTED** — now runs every bar |
| [aurora_scoring_kernel.py](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/aurora_scoring_kernel.py) | **DEPRECATED** notice added, rollback instructions in module doc |
| [scoring_direction_strength_v1.py](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/scoring_direction_strength_v1.py) | **DEPRECATED** notice added |

---

## 5. Intentionally Retained Surfaces

| Surface | Reason |
|---|---|
| [aurora_scoring_kernel.py](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/aurora_scoring_kernel.py) (file kept) | 2-week explicit rollback scaffold — set `scoring_version: "v2"` to activate |
| [scoring_direction_strength_v1.py](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/scoring_direction_strength_v1.py) (file kept) | MR / md_amr uses this for mean-reversion scoring — separate from Aurora Quadratic path |
| [signal_weights](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/aurora_scoring_helpers.py#164-172) in aurora.yaml | v2 rollback scaffold — annotated DEPRECATED |
| [feature_neutrals](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/aurora_scoring_helpers.py#340-348) in aurora.yaml | v2 rollback scaffold — annotated DEPRECATED |
| `direction_strength_scoring` in aurora.yaml | v2 rollback scaffold — annotated DEPRECATED |
| `quadratic_rollout.py:evaluate_quadratic_shadow()` | MR/md_amr shadow mode still uses this — removing would break MR |

---

## 6. Threshold Recalibration Outcome

**No recalibration required.** Analysis:

```
signal_threshold = 0.162
score = sign(pillar_sum) × pillar_sum²
pillar_sum threshold = sqrt(0.162) = 0.4025  ← reasonable mid-bar conviction
neutral_threshold = 0.05 → pillar_sum = 0.224 (noise floor)
```

With [ContextShield(TREND_UP=1.0)](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/shields/context_shield.py#27-129) × [MemoryShield(known=1.0)](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/shields/memory_shield.py#138-473) → full signal pass-through for well-known trend bars.  
With [ContextShield(HIGH_VOLATILITY=0.30)](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/shields/context_shield.py#27-129) → effective score ×0.30 → signals blocked unless pillar_sum ≥ 0.73 in HV regime.

This is **intentional protection** — the shield IS the recalibrator. Thresholds are Phase 9 appropriate.

---

## 7. Shield / Startup / Readiness / Execution Impacts

- **Shields:** `DangerZoneShield → ContextShield → MemoryShield` cascade active. `shield_mult ≈ 0.6` in new/unknown states.
- **Startup:** pillar hydration via [update_pillar_candle](file:///c:/Users/user/Music/Phenix/apps/reference/domains/feature_engineering/calculation_engine.py#1174-1225) now runs on every bar (fixed bug where it only ran on first bar per symbol).
- **ExecutionGate:** Active whenever `self.execution_gate is not None` (wired in [aurora_config_loader.py](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/aurora_config_loader.py)).
- **ExitManager:** Active at `aurora_decision.py:590` — `self.exit_manager.check_exit()`.
- **Readiness:** No changes to warmup/readiness chain.

---

## 8. MR / md_amr Compatibility

✅ No regressions. [scoring_direction_strength_v1.py](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/scoring_direction_strength_v1.py) and [aurora_scoring_kernel.py](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/aurora_scoring_kernel.py) retained.  
[evaluate_quadratic_shadow()](file:///c:/Users/user/Music/Phenix/apps/reference/contracts/quadratic_rollout.py#239-283) contract unchanged.  
5213/5214 tests pass (1 pre-existing failure in `test_stale_features_do_not_update_buffers` — regime detector internals, unrelated).

---

## 9. Test Results

| Suite | Result |
|---|---|
| [test_quadratic_scoring_kernel.py](file:///c:/Users/user/Music/Phenix/tests/test_quadratic_scoring_kernel.py) (8 tests) | ✅ 8/8 PASS |
| [test_pillars_quadratic_pipeline.py](file:///c:/Users/user/Music/Phenix/tests/integration/test_pillars_quadratic_pipeline.py) (2 tests) | ✅ 2/2 PASS |
| [test_pillar_to_decision_e2e.py](file:///c:/Users/user/Music/Phenix/tests/integration/test_pillar_to_decision_e2e.py) (2 tests) | ✅ 2/2 PASS |
| [test_quadratic_rollout_contract.py](file:///c:/Users/user/Music/Phenix/tests/contracts/test_quadratic_rollout_contract.py) | ✅ PASS |
| `feature_engineering/` domain tests | ✅ 67/67 PASS |
| **Full suite (5377 tests)** | ✅ **5213 pass, 1 pre-existing fail, 165 skip** |

---

## 10. Remaining Open Risks

| Risk | Severity | Action |
|---|---|---|
| `test_stale_features_do_not_update_buffers` failure | LOW | Pre-existing regime detector test — unrelated to Phase 9 |
| [MemoryShield](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/shields/memory_shield.py#138-473) in-memory only (no persistence) | LOW | Shield state resets on restart → conservative (UNKNOWN mult=0.6) → safe |
| [compute_pillars](file:///c:/Users/user/Music/Phenix/apps/reference/domains/feature_engineering/calculation_engine.py#1226-1338) bug fix may slightly change pillar timing | LOW | Fixed behavior is MORE correct (updates every bar, not just init) |
| Legacy v2 files (aurora_scoring_kernel.py) still in codebase | INFO | Explicit rollback scaffold — remove 2026-03-27 if no rollback occurs |

---

## 11. Recommended Immediate Next Step

**Monitor live:**
```
KERNEL_DIAG: engine=quadratic_v1   ← Quadratic active
shield_mult = 0.6/1.0              ← Shields attenuating (0.6=unknown state, 1.0=known)
EVT:QUADRATIC_KERNEL_CRASH         ← Crash event (should be absent)
```

**In 2 weeks (2026-03-27):**
```bash
git rm apps/reference/domains/decision_making/aurora_scoring_kernel.py
git rm apps/reference/domains/decision_making/scoring_direction_strength_v1.py
# Remove signal_weights, feature_neutrals, direction_strength_scoring from aurora.yaml
```
