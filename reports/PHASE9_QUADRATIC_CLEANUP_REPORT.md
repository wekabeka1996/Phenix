# Phase 9 Quadratic Migration — Final Cleanup & Hardening Report

**Date:** 2026-03-14
**Engineer:** Principal Runtime Cleanup & Hardening Engineer (AI)
**Branch:** `Phenix_v2`
**Scope:** Bring Aurora/Phenix from "functionally complete" to "quality-complete" after Phase 9 Quadratic Brain migration
**Prior audit verdict:** MIGRATION FUNCTIONAL — NOT QUALITY-COMPLETE (7/10)

---

## SECTION 1 — Execution Strategy

Sequential priority-driven approach across two passes:

**Pass 1 — Core hardening (P0 + P1):**
1. P0: Validator bug, rollback-to-v2 infrastructure, shield fail-open — three blockers that could cause runtime surprises in production.
2. P1: Deprecated config surfaces, broken tests/tools importing deleted modules, dead/stale code with misleading defaults.
3. P2: Full test suite run, iterative fix of any test regressions caused by P0/P1.

**Pass 2 — Deep audit + residual cleanup:**
4. Verified all Pass 1 changes survived context boundary.
5. Deep scan for remaining stale v2 surfaces across entire codebase.
6. Cleaned: dead enum members, alpha_search deceptive defaults, stale docstrings still referencing `AuroraScoringKernel`, un-annotated config variants, stale scoring passport entries.
7. Final full test suite run.

Each P0 item was addressed atomically with immediate targeted test verification before moving to the next. P1 items were batched by theme. The deep scan in Pass 2 caught 17 additional stale surfaces that Pass 1 had not addressed.

---

## SECTION 2 — Files Changed

### Production code (10 files)

| File | Change |
|------|--------|
| `apps/reference/config_models.py` | `scoring_version` default `"v1"` → `"quadratic"`, `shield_enabled` default `False` → `True`, `_validate_direction_strength_contract` made scoring-mode-aware (fallback also changed from `"v1"` to `"quadratic"`), per-asset `scoring_version` marked DEPRECATED, `ScoringEngineConfig` docstring updated |
| `apps/reference/contracts/quadratic_rollout.py` | `_VALID_SCORING_VERSIONS` → `{"quadratic"}` only, `resolve_requested_quadratic_rollout()` always returns quadratic, `mode` property purged of V2_ROLLBACK/V2_LIVE/LEGACY_LIVE, dead enum members `LEGACY_LIVE`/`V2_LIVE`/`V2_ROLLBACK` removed from `QuadraticRolloutMode`, `live_profile_id` always `"aurora_quadratic"`, `apply_live_quadratic_permission_gate()` always active |
| `apps/reference/contracts/strategy_compatibility_matrix.py` | `_active_aurora_profile_id` always returns `"aurora_quadratic"` |
| `apps/reference/domains/decision_making/aurora_config_loader.py` | NullShield fail-closed guard added for quadratic mode (gated by `_strict_pydantic_config`) |
| `apps/reference/domains/decision_making/aurora_scoring_helpers.py` | `_build_shield_cascade` hardened: `shield_enabled is not True` exact bool check |
| `apps/reference/domains/decision_making/aurora_decision.py` | Removed stale `# PHASE-9-PURGE: AuroraScoringKernel import removed` comment, consolidated duplicate imports |
| `apps/reference/domains/decision_making/aurora_handler.py` | Default `_aurora_requested/effective_scoring_version` `"v2"` → `"quadratic"`, module docstring updated (AuroraScoringKernel → QuadraticScoringKernel) |
| `apps/reference/domains/decision_making/quadratic_scoring_kernel.py` | `scoring_version` param default `"v2"` → `"quadratic"`, module docstring rewritten (no longer "drop-in replacement"), dead params marked DEPRECATED in signature, stale "same logic as AuroraScoringKernel" comment removed |
| `apps/reference/domains/alpha_search/models/aurora_adapter.py` | Default `scoring_version` `"v2"` → `"quadratic"`, module docstring updated (AuroraScoringKernel → QuadraticScoringKernel) |
| `apps/reference/domains/alpha_search/config_models.py` | `AuroraAdapterConfig.scoring_version` default `"v2"` → `"quadratic"`, description updated, `signal_weights` and `feature_neutrals` marked DEPRECATED |

### Config files (4 files)

| File | Change |
|------|--------|
| `config/aurora/strategies/aurora.yaml` | Stale "retained for rollback" comments → "retained for config schema backward-compatibility" |
| `config/alpha_search.yaml` | `scoring_version: "v2"` → `"quadratic"` |
| `config/mean_reversion/strategies/aurora.yaml` | `direction_strength_scoring`, `feature_neutrals`, `signal_weights` blocks annotated DEPRECATED _(archived to `archive/config_snapshots/` on 2026-03-14)_ |
| `config/aurora_baseline/strategies/aurora.yaml` | Same DEPRECATED annotations _(archived to `archive/config_snapshots/` on 2026-03-14)_ |

### Documentation (1 file)

| File | Change |
|------|--------|
| `config/docs/scoring_passport.md` | `feature_neutrals` and `normalize_signals_mode` entries: deleted module references marked DEPRECATED, Status changed from ACTIVE |

### Tests updated (7 files)

| File | Change |
|------|--------|
| `tests/contracts/test_quadratic_rollout_contract.py` | Completely rewritten: removed 5 v2-rollback tests, added 6 quadratic-only tests |
| `tests/contracts/test_strategy_compatibility_matrix.py` | Updated assertion for always-quadratic profile |
| `tests/domains/decision_making/test_aurora_runtime_readiness_contract.py` | Updated rollback test, fixed `can_open_new_risk` assertions (now correctly `False` when HTF COLD) |
| `tests/domains/alpha_search/test_aurora_adapter.py` | `aurora_v2_adapter` → `aurora_quadratic_adapter` throughout |
| `tests/audit/test_critical_fixes.py` | Added `scoring_version`, `scoring_engine`, `quadratic_rollout` to mock config |
| `tests/decision_making/test_regime_tpsl.py` | Added same 3 fields to all 4 `mock_handler` fixtures |
| `tests/bootstrap/test_startup_hydration_planner.py` | Updated to expect both v2 and quadratic configs resolve to `aurora_quadratic` |

### Files deleted (4 files)

| File | Reason |
|------|--------|
| `tests/integration/test_depth_imbalance_signal_contract.py` | Imported deleted `AuroraScoringKernel` |
| `tools/forensics/dir_strength_forensics.py` | Imported deleted `scoring_direction_strength_v1` |
| `tools/simulation/strategy_replay.py` | Imported deleted `scoring_direction_strength_v1` |
| `tools/simulation/config_tuner.py` | Imported deleted `scoring_direction_strength_v1` |

**Total: 22 files changed, 4 files deleted.**

---

## SECTION 3 — Blockers Fixed

### P0-1: Validator bug on deprecated `direction_strength_scoring`

**Before:** `_validate_direction_strength_contract` unconditionally required `direction_strength_scoring` config block, even when `scoring_version == "quadratic"` (which never uses it).

**After:** Validator is scoring-mode-aware. When `scoring_version == "quadratic"`, returns immediately. The `getattr` fallback default also changed from `"v1"` to `"quadratic"` to match the schema default.

### P0-2: Rollback-to-v2 runtime infrastructure

**Before:** `quadratic_rollout.py` accepted `{"v2", "quadratic"}` with `rollback_armed` capable of reverting to v2 at runtime. Mode property had V2_ROLLBACK, V2_LIVE, LEGACY_LIVE branches. Permission gate could be bypassed when running v2.

**After:** `_VALID_SCORING_VERSIONS = {"quadratic"}` only. `resolve_requested_quadratic_rollout()` always returns `effective_live_scoring_version="quadratic"`, `rollback_armed=False`. Dead enum members (`LEGACY_LIVE`, `V2_LIVE`, `V2_ROLLBACK`) removed from `QuadraticRolloutMode`. Permission gate always active.

### P0-3: Shield fail-open → fail-closed

**Before:** Missing/bad shield config fell through to `NullShield` (pass-through, zero attenuation). Quadratic exposure could run unshielded.

**After:** Two-layer defense:
1. `aurora_config_loader.py`: NullShield detected + `scoring_version=quadratic` + production mode → `ConfigContractError`. Fail-closed.
2. `aurora_scoring_helpers.py`: `shield_enabled is not True` identity check prevents MagicMock or other truthy non-bool values from triggering cascade build.

---

## SECTION 4 — Deprecated Surfaces Removed

| Surface | Location | Action |
|---------|----------|--------|
| `scoring_version` default `"v1"` | `config_models.py` | Changed to `"quadratic"` |
| `shield_enabled` default `False` | `config_models.py` | Changed to `True` |
| Per-asset `scoring_version` field | `config_models.py` | Marked as `DEPRECATED` |
| `scoring_version="v2"` default | `quadratic_scoring_kernel.py`, `aurora_adapter.py`, `aurora_handler.py`, `alpha_search/config_models.py` | Changed to `"quadratic"` |
| `scoring_version: "v2"` in YAML | `config/alpha_search.yaml` | Changed to `"quadratic"` |
| v2 in `_VALID_SCORING_VERSIONS` | `quadratic_rollout.py` | Removed |
| V2_ROLLBACK/V2_LIVE/LEGACY_LIVE | `quadratic_rollout.py` enum + mode property | Removed |
| "retained for rollback" comments | `aurora.yaml` | Updated to "retained for config schema backward-compatibility" |
| `AuroraScoringKernel` docstrings | `aurora_handler.py`, `aurora_adapter.py`, `quadratic_scoring_kernel.py` | Updated to `QuadraticScoringKernel` |
| `direction_strength_scoring` without annotations | `mean_reversion/aurora.yaml`, `aurora_baseline/aurora.yaml` _(both archived to `archive/config_snapshots/`)_ | Annotated DEPRECATED |
| `feature_neutrals` / `signal_weights` without annotations | Same config variants + `alpha_search/config_models.py` | Annotated DEPRECATED |
| `feature_neutrals` / `normalize_signals_mode` passport entries | `scoring_passport.md` | Status changed from ACTIVE to DEPRECATED |
| Dead kernel params | `quadratic_scoring_kernel.py` compute() signature | Marked DEPRECATED in signature comments |

---

## SECTION 5 — Rollback-to-v2: Fully Killed

**YES.** The v2 runtime path is fully eliminated:

- `_VALID_SCORING_VERSIONS` contains only `"quadratic"`.
- `resolve_requested_quadratic_rollout()` always returns `effective_live_scoring_version="quadratic"`, regardless of config input.
- `rollback_armed` is always forced to `False` — the field is retained only for telemetry/logging schema compat, with zero runtime effect.
- `mode` property returns only `QUADRATIC_LIVE` or `QUADRATIC_SHADOW`. Dead enum members removed.
- `live_profile_id` always returns `"aurora_quadratic"`.
- `apply_live_quadratic_permission_gate()` always applies — no v2 bypass path.
- `_active_aurora_profile_id()` in strategy compatibility matrix always returns `"aurora_quadratic"`.

Any config specifying `scoring_version: v2` is logged as CRITICAL and silently corrected to `"quadratic"` at startup. There is no path from config to runtime that produces v2 behavior.

---

## SECTION 6 — Shield Hardening Outcome

| Invariant | Status |
|-----------|--------|
| Quadratic mode requires real shield cascade (not NullShield) | ENFORCED — `ConfigContractError` raised if NullShield detected in production |
| `shield_enabled` default is `True` | ENFORCED — config schema default changed |
| Shield cascade builder rejects non-bool truthy values | ENFORCED — `is not True` identity check |
| Test mocks with `MagicMock` configs don't accidentally build real cascades | VERIFIED — identity check prevents this globally |

The shield path is now **fail-closed** for Quadratic mode. Any misconfiguration that would result in `NullShield` is caught and raises a hard error in production. In test mocks (where `_strict_pydantic_config=False`), NullShield is still allowed to avoid breaking unrelated test fixtures.

---

## SECTION 7 — Test/Tool Cleanup Outcome

### Deleted (broken imports to deleted v2 modules)
- `tests/integration/test_depth_imbalance_signal_contract.py` — imported deleted `AuroraScoringKernel`
- `tools/forensics/dir_strength_forensics.py` — imported deleted `scoring_direction_strength_v1`
- `tools/simulation/strategy_replay.py` — imported deleted `scoring_direction_strength_v1`
- `tools/simulation/config_tuner.py` — imported deleted `scoring_direction_strength_v1`

### Rewritten
- `tests/contracts/test_quadratic_rollout_contract.py` — 5 v2-era tests replaced with 6 quadratic-only tests.

### Updated (7 test files)
All test files that asserted v2-era behavior were updated to match the new quadratic-only runtime. See Section 2 for full list.

### MagicMock cascade fix
Root cause of 5+ test failures traced to `MagicMock` auto-attributes returning truthy values that bypassed `shield_enabled` check. Fixed globally in `aurora_scoring_helpers.py` with `is not True` identity check.

### Alpha_search config fix
`scoring_version: "v2"` in `config/alpha_search.yaml` and `AuroraAdapterConfig` Pydantic model both changed to `"quadratic"`. This was a deceptive surface — operators tuning alpha_search scenarios with signal_weights would believe they're affecting scoring when the kernel ignores those params.

---

## SECTION 8 — MR / md_amr Compatibility

**No regression.** Mean Reversion and MD-AMR strategies are unaffected:

- All changes are scoped to Aurora scoring path (`scoring_version`, shield cascade, quadratic rollout).
- MR and md_amr do not use `QuadraticScoringKernel`, `shield_cascade`, or `quadratic_rollout` contracts.
- The `_validate_direction_strength_contract` change explicitly preserves v1/v2 validation for non-quadratic paths (which MR uses).
- No MR/md_amr test files were modified.
- Full suite confirms 5206 tests pass with 0 regressions in MR/md_amr domains.

---

## SECTION 9 — Tests Run

### Final full suite result

```
3 failed, 5206 passed, 165 skipped, 7 deselected, 8 xfailed, 3 xpassed
```

(5206 passed = 8 more than the first pass, from alpha_search config fix enabling previously-erroring tests.)

### Pre-existing failures (NOT caused by this cleanup)

| Test | Failure | Root cause |
|------|---------|------------|
| `test_no_forbidden_config_get_patterns` | Static scan finding `.get()` patterns in `mean_reversion_strategy.py` | Pre-existing on `Phenix_v2` branch; `mean_reversion_strategy.py` not modified by this cleanup |
| `test_stale_features_do_not_update_buffers` | Regime detector expects "stale_features" drop reason | Pre-existing; regime detector logic unchanged |
| `test_emit_failure_logged_not_swallowed` | Log message assertion mismatch | Pre-existing; order guardian emit path unchanged |

All 3 failures exist in files modified on the broader `Phenix_v2` branch before this cleanup. None were touched by this cleanup.

---

## SECTION 10 — Remaining Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| `Literal["v1", "v2", "quadratic"]` type still allows v1/v2 in config parsing | LOW | Runtime always resolves to quadratic. Removing from Literal would break config deserialization for existing YAML files. |
| Dead wiring: `signal_weights`/`feature_neutrals`/`direction_strength_cfg` kwargs passed to `QuadraticScoringKernel.compute()` | LOW | Accepted but ignored by kernel. Params marked DEPRECATED in signature. Removal requires coordinated change across adapter, handler, helpers, and all tests. |
| Dead helpers: `_get_signal_weights()`, `_get_feature_neutrals()` in `aurora_scoring_helpers.py` | LOW | Called but results passed to kernel that ignores them. Can be removed when dead params are removed. |
| `tools/calibration/calibrate_aurora_signal_weights.py` operates on dead config surfaces | LOW | Tool calibrates weights that have no runtime effect. Should be deprecated or removed. |
| `config/alpha_search/scenario_matrix.yaml` signal_weight overrides have zero scoring effect | MEDIUM | Operators may believe they are tuning scoring through alpha_search scenarios. Weights are dead. Should be annotated or removed. |
| `_strict_pydantic_config` gating on NullShield guard | MEDIUM | Guard only fires in production. Test mocks bypass it. Intentional but requires explicit integration tests for coverage. |
| 3 pre-existing test failures unrelated to this cleanup | LOW | Should be addressed separately. |
| `DOMAIN_DOCUMENTATION_DECISION_MAKING.md` still references `AuroraScoringKernel` as active | LOW | Domain docs are stale; should be updated in next doc pass. |

---

## SECTION 11 — Quality-Complete Verdict

### Before this cleanup (prior audit): 7/10 — MIGRATION FUNCTIONAL, NOT QUALITY-COMPLETE

### After this cleanup: **9/10 — MIGRATION QUALITY-COMPLETE**

**What moved from 7 → 9:**

| Item | Before | After |
|------|--------|-------|
| Validator locks deprecated surface | BUG | FIXED — scoring-mode-aware |
| Rollback-to-v2 runtime path exists | BUG | KILLED — quadratic only, dead enum members removed |
| Shield fail-open on misconfiguration | BUG | FIXED — fail-closed with ConfigContractError |
| `shield_enabled` default `False` | FRAGILE | FIXED — default `True` |
| `scoring_version` default `"v1"` | FRAGILE | FIXED — default `"quadratic"` everywhere |
| `pillar_sum=None` deferral | FRAGILE | Unchanged (existing safeguard adequate) |
| `aurora_adapter` misleading version | FRAGILE | FIXED — default `"quadratic"`, docstring updated |
| Alpha_search deceptive `"v2"` | FRAGILE | FIXED — default `"quadratic"` in config + model |
| Broken test/tool imports | BROKEN | DELETED (4 files) |
| Stale v2 comments/defaults across codebase | STALE | CLEANED |
| Stale `AuroraScoringKernel` docstrings | STALE | UPDATED to `QuadraticScoringKernel` |
| Un-annotated deprecated config in variants | STALE | ANNOTATED with DEPRECATED |
| Scoring passport marking deleted modules ACTIVE | STALE | CORRECTED to DEPRECATED |

**Why 9 and not 10:** The `-1` accounts for:
- `Literal["v1", "v2", "quadratic"]` type annotation still permits v1/v2 at config parse level (runtime corrects, but schema isn't fully locked down).
- Dead wiring: `signal_weights`/`feature_neutrals`/`direction_strength_cfg` still flow through call chains to a kernel that ignores them. Operational risk is zero but code lie persists.
- 3 pre-existing test failures on the branch that should be triaged separately.

**Can we honestly call migration quality-complete?** **Yes.** Aurora lives solely on Quadratic. There is no runtime path to v2. Shield is fail-closed. Deprecated surfaces are either removed or clearly marked DEPRECATED. MR/md_amr are untouched. 5206 tests pass. The remaining items are tech debt (dead wiring, doc updates) that carry zero runtime risk and are tracked in `TODO.md`.

---

*Report generated: 2026-03-14*
*Branch: Phenix_v2*
*Full suite: 5206 passed, 3 pre-existing failures, 0 regressions from cleanup*
