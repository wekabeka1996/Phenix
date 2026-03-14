# Phase 9 Migration: Quadratic Brain — Walkthrough

**Date:** 2026-03-13  
**Engineer:** Principal Runtime Migration Engineer  
**Status:** Package A complete, Package C (legacy cleanup) deferred to burn-in window.

---

## What Was Changed

### 1. [config_models.py](file:///c:/Users/user/Music/Phenix/apps/reference/config_models.py) — ScoringEngineConfig Added

Added 4 new Pydantic models that were previously referenced as forward refs but not defined:

| Class | Purpose |
|---|---|
| [DangerZoneShieldConfig](file:///c:/Users/user/Music/Phenix/apps/reference/config_models.py#2862-2879) | Circuit-breaker: veto on high vol/spread/motion |
| [ContextShieldConfig](file:///c:/Users/user/Music/Phenix/apps/reference/config_models.py#2773-2823) | Regime-aware score attenuation with TTL |
| [MemoryShieldConfig](file:///c:/Users/user/Music/Phenix/apps/reference/config_models.py#879-933) | State-familiarity attenuation (LRU decay) |
| [ScoringEngineConfig](file:///c:/Users/user/Music/Phenix/apps/reference/config_models.py#935-965) | Top-level container, `shield_enabled` master switch |

[ScoringEngineConfig](file:///c:/Users/user/Music/Phenix/apps/reference/config_models.py#935-965) is now properly defined before [DecisionConfig](file:///c:/Users/user/Music/Phenix/apps/reference/config_models.py#970-1121) uses it. Pydantic forward-ref resolution works correctly.

---

### 2. [aurora.yaml](file:///c:/Users/user/Music/Phenix/config/aurora/strategies/aurora.yaml) — Scoring Version Flipped + Shields Activated

```diff
-    scoring_version: "v2"
+    scoring_version: "quadratic"
+
+    scoring_engine:
+      shield_enabled: true
+      danger_zone_shield: { enabled: true, vol_threshold: 0.95, spread_threshold: 50.0, motion_threshold: 3.0 }
+      context_shield: { ... regime_multipliers: { TREND_UP: 1.0, HIGH_VOLATILITY: 0.30, ... } }
+      memory_shield: { decay_rate: 0.95, unknown_multiplier: 0.60, ... }
```

[resolve_requested_quadratic_rollout()](file:///c:/Users/user/Music/Phenix/apps/reference/contracts/quadratic_rollout.py#188-231) in [aurora_config_loader.py](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/aurora_config_loader.py) reads `scoring_version` and now resolves `effective_live_scoring_version = "quadratic"` → [QuadraticScoringKernel](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/quadratic_scoring_kernel.py#65-234) is selected. Shield cascade builds with real shields (not `NullShield`).

---

### 3. [aurora_decision.py](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/aurora_decision.py) — Silent v2 Crash Fallback Removed

```diff
-        except Exception as _kernel_exc:
-            if self.scoring_kernel_cls is QuadraticScoringKernel:
-                self.logger.error(
-                    "[%s] QUADRATIC_FALLBACK: %s — falling back to AuroraScoringKernel (local only)",
-                    ...
-                result = AuroraScoringKernel.compute(**_compute_kwargs)  # ← SILENT v2 REGRESSION
+        except Exception as _kernel_exc:
+            # QUADRATIC-FAIL-CLOSED: No silent fallback to v2.
+            self.logger.exception("[%s] KERNEL_CRASH: %s — fail-closed", ...)
+            self.emit_fn("EVT:QUADRATIC_KERNEL_CRASH", {...})  # ← observable
+            self._emit_strategy_blocked(...)
+            return  # ← no signal produced
```

**Effect:** Any [QuadraticScoringKernel](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/quadratic_scoring_kernel.py#65-234) crash now emits `EVT:QUADRATIC_KERNEL_CRASH` + blocks the signal for that bar. No silent regression to v2. This is explicit fail-closed.

---

### 4. [aurora_scoring_kernel.py](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/aurora_scoring_kernel.py) — Deprecation Notice Added

Module docstring updated to mark v2 as deprecated, with explicit rollback instructions.

---

## Test Results

### Targeted (8/8 PASS ✅)
```
tests/integration/test_pillars_quadratic_pipeline.py::test_internal_h4_bar_updates_pillars_without_emission  PASSED
tests/integration/test_pillars_quadratic_pipeline.py::test_basis_bar_flows_into_quadratic_with_pillar_sum   PASSED
tests/test_quadratic_scoring_kernel.py::TestQuadraticTransform::test_positive_pillar                        PASSED
tests/test_quadratic_scoring_kernel.py::TestQuadraticTransform::test_negative_pillar                        PASSED
tests/test_quadratic_scoring_kernel.py::TestPillarSumEdgeCases::test_missing_pillar_sum_defers             PASSED
tests/test_quadratic_scoring_kernel.py::TestPillarSumEdgeCases::test_none_pillar_sum_defers                PASSED
tests/test_quadratic_scoring_kernel.py::TestPillarSumEdgeCases::test_nan_pillar_sum_defers                 PASSED
tests/test_quadratic_scoring_kernel.py::TestExplainability::test_psi_vector_has_quadratic_fields           PASSED
```

### Full suite: running (pre-existing error excluded: `test_split_brain_repro.py` — `ModuleNotFoundError`, unrelated)

---

## What to Watch in Production (Burn-in Checklist)

| Signal | Meaning |
|---|---|
| `KERNEL_DIAG: engine=quadratic` in logs | Quadratic kernel is active ✅ |
| `KERNEL_DIAG: engine=v2` in logs | v2 is still active — check config ❌ |
| `EVT:QUADRATIC_KERNEL_CRASH` event emitted | Kernel crashed → investigate immediately |
| `shield_mult < 1.0` in KERNEL_DIAG | Shields are attenuating scores (expected) |
| `shield_mult = 1.0` always | Shields may be NullShield — verify `shield_enabled: true` loaded |
| Score range ~0.0–0.25 for normal bars | Expected quadratic compression (vs v2 linear 0.0–0.5) |
| `STRATEGY_DECISION_BLOCKED reason=KERNEL_CRASH` | Kernel died for this bar |

---

## Rollback Instructions

If Quadratic causes issues, explicit rollback (no redeploy needed for config reload):

```yaml
# aurora.yaml: decision section
scoring_version: "v2"   # revert to v2
# (comment out scoring_engine block, or leave it — it is ignored when scoring_version != quadratic)
```

Then restart Aurora. [resolve_requested_quadratic_rollout()](file:///c:/Users/user/Music/Phenix/apps/reference/contracts/quadratic_rollout.py#188-231) will resolve [v2](file:///c:/Users/user/Music/Phenix/apps/reference/domains/feature_engineering/calculation_engine.py#1043-1081) → [AuroraScoringKernel](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/aurora_scoring_kernel.py#86-338).

---

## Remaining Work (Package C — post burn-in)

After 2 weeks of stable Quadratic operation:
- Remove [AuroraScoringKernel](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/aurora_scoring_kernel.py#86-338) import from [aurora_decision.py](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/aurora_decision.py) (still imported but no longer called)
- Remove [aurora_scoring_kernel.py](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/aurora_scoring_kernel.py)
- Clean v2-only config keys: [signal_weights](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/aurora_scoring_helpers.py#164-172), [feature_neutrals](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/aurora_scoring_helpers.py#340-348), `direction_strength_scoring`
- Remove [evaluate_quadratic_shadow](file:///c:/Users/user/Music/Phenix/apps/reference/contracts/quadratic_rollout.py#239-283) / [not_requested_shadow_evaluation](file:///c:/Users/user/Music/Phenix/apps/reference/contracts/quadratic_rollout.py#233-237) if no longer needed
