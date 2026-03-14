# Documentation Forensics Audit Report: Aurora Math Passport

**Date:** 2026-03-13
**Target Document:** config/docs/aurora_math_passport.md
**Auditor:** Principal Code Auditor / Documentation Forensics Engineer

## 1. Scope

This audit re-traced exactly one passport: config/docs/aurora_math_passport.md.

The trace was limited to Aurora math and score-adjacent decision semantics:

1. Signal normalization.
2. SignalScoreV2 centering and fail-closed behavior.
3. Direction/strength split math.
4. Threshold scaling, side bias, and hysteresis.
5. Liquidity gate semantics.
6. Optional Quadratic transform and rollout wiring.
7. Per-symbol Aurora math overrides.
8. Event-visible math metadata.

## 2. Files traced

### YAML
- config/aurora/strategies/aurora.yaml

### Pydantic / config contracts
- apps/reference/config_models.py
- apps/reference/contracts/quadratic_rollout.py

### Runtime consumers
- apps/reference/domains/decision_making/aurora_handler.py
- apps/reference/domains/decision_making/aurora_config_loader.py
- apps/reference/domains/decision_making/aurora_scoring_helpers.py
- apps/reference/domains/decision_making/aurora_decision.py
- apps/reference/domains/decision_making/aurora_scoring_kernel.py
- apps/reference/domains/decision_making/quadratic_scoring_kernel.py
- apps/reference/domains/decision_making/scoring_direction_strength_v1.py
- apps/reference/domains/decision_making/signal_score_v2.py
- apps/reference/domains/decision_making/intent_builder.py

### Tests
- tests/domains/decision_making/test_aurora_scoring_kernel.py
- tests/domains/decision_making/test_normalize_mode_ssot.py
- tests/test_quadratic_scoring_kernel.py

## 3. Critical runtime consumers

1. AuroraScoringKernel.compute()
2. QuadraticScoringKernel.compute()
3. compute_direction_strength_score()
4. SignalScoreV2.calculate_score()
5. AuroraScoringHelpersMixin._check_liquidity_gate()
6. AuroraDecisionMixin._process_decision()
7. AuroraConfigLoaderMixin._load_config()

## 4. Confirmed claims

1. SignalScoreV2 uses centered net-zero scoring and clamps output to `[-1, 1]`.
2. Direction/strength split formula is `dir * (1 + alpha * strength)`.
3. Strength branch uses `max(0, score)` and then caps at `strength_cap`.
4. Final linear Aurora score is not clamped after the direction/strength multiplication.
5. `signed_v2` is strictly enforced at the production config boundary.
6. AuroraScoringKernel fails closed on missing readiness keys for essential features.
7. Delta-price normalization uses price-relative capping before score calculation.
8. Regime threshold scaling is driven by `regime_threshold_multipliers`.
9. Side bias penalties are real threshold multipliers, not post-score modifiers.
10. Hysteresis logic is shared conceptually across linear and Quadratic kernels.
11. Liquidity gate is fail-closed on readiness/data failure.
12. Quadratic math is implemented and test-covered.

## 5. Corrected claims

1. The passport no longer treats `aurora_handler.py` as the sole math owner; math routing is decomposed across mixins and kernels.
2. The passport no longer describes production support for `off` or `net_zero` normalization modes.
3. The passport no longer frames Quadratic math as the current live default.
4. The passport now distinguishes SignalScoreV2 clamping from unclamped post-multiply Aurora `v2` score amplitude.
5. The passport now documents that `DecisionConfig.regime_thresholds` is not the active global threshold source.
6. The passport now documents per-symbol override resolution exactly as implemented.
7. The passport now marks `failsafe_qty_check` as diagnostic-only instead of active qty enforcement.
8. The passport now captures shadow/live rollout payloads as event-visible math outputs.
9. The passport now documents that per-symbol `neutral_threshold` is probed by runtime but absent from strict Aurora instrument config.
10. The passport now marks `AuroraInstrumentConfig.scoring_version` as unused in the current loader path.
11. The passport now records the practical `v1 -> v2` coercion drift in rollout handling.

## 6. Removed stale claims

1. Monolithic `aurora_handler` as the single math SSOT.
2. Production `off` / `net_zero` normalization modes.
3. Quadratic as the implied current live engine.
4. `failsafe_qty_check` as an active liquidity/min-qty guard.
5. Global `decision.regime_thresholds` as the live Aurora threshold map.

## 7. Added missing sections

1. Runtime consumer map after Phase 14A decomposition.
2. Exact SignalScoreV2 fail-closed semantics.
3. Final linear score amplitude range.
4. Exact per-symbol override chain for weights, neutrals, thresholds, liquidity gate, and regime thresholds.
5. Event-visible math metadata surfaces.
6. Quadratic rollout vs active live math separation.
7. Legacy/dead field ledger specific to Aurora math.
8. The neutral-threshold typed/runtime mismatch.
9. The unused per-symbol scoring_version field.

## 8. Dead / legacy / declared-but-unused fields

1. `DecisionConfig.regime_thresholds` is declared but not used by Aurora math routing.
2. `AuroraInstrumentConfig.scoring_version` is declared but not consumed by the Aurora loader.
3. `LiquidityGateConfig.failsafe_qty_check` is diagnostic-only.
4. `DecisionConfig.scoring_version = v1` is legacy in practice because rollout coerces unknown values to `v2`.
5. `macro_sync` remains compatibility-only in current live math because effective weight is `0.0`.
6. `side_bias_min_score` is deprecated and has no traced Aurora math consumer.
7. Per-symbol `neutral_threshold` support is not wired at the typed config boundary.

## 9. Open questions

No open questions remain for this passport sync. The unresolved items are implementation cleanup tasks, not evidence gaps.

## 10. Final verdict

The passport is synchronized to current Aurora math behavior.

The main correction is structural: current live Aurora math is a strict `signed_v2` linear path wrapped by decomposed runtime mixins, while Quadratic math remains an optional rollout path. The previous passport mixed together historical intent, old monolithic topology, and optional code paths. That drift has been removed.

**Status: DONE**
