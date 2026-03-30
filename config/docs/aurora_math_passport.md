# AURORA MATH PASSPORT
## Aurora strategy math and decision semantics — code-driven sync snapshot

> AUDIT SUMMARY
> - Document path: config/docs/aurora_math_passport.md
> - Audit date: 2026-03-18
> - Audit mode: code-driven sync
> - Major drifts found:
>   1. Linear v2 (`aurora_scoring_kernel.py`) has been entirely removed from the codebase.
>   2. Quadratic math (`quadratic_scoring_kernel.py`) is now the **sole active scoring path** (Phase 9 Migration).
>   3. `direction_strength_scoring`, `signal_weights`, and `feature_neutrals` are marked as DEPRECATED legacy surfaces, no longer consumed by the active kernel.
>   4. `scoring_engine.shield_enabled=true` with an active shield cascade is now mandatory for production.
> - Overall confidence: HIGH

---

## 1. Scope

This passport covers the mathematical and behavioral semantics of Aurora strategy decision-making only.

It traces:

1. Signal normalization.
2. SignalScoreV2 centering and fail-closed behavior (LEGACY).
3. Linear `v2` direction/strength scoring (LEGACY).
4. Quadratic transform and shield cascade math (ACTIVE).
5. Threshold scaling, hysteresis, and side-bias penalties.
6. Liquidity gating and score-adjacent fail-closed behavior.
7. Per-symbol override resolution for math-affecting Aurora fields.
8. Event-visible math metadata emitted from Aurora runtime.

Authoritative sources traced for this passport:

- YAML: config/aurora/strategies/aurora.yaml.
- Pydantic: apps/reference/config_models.py.
- Runtime: apps/reference/domains/decision_making/aurora_handler.py, aurora_config_loader.py, aurora_scoring_helpers.py, aurora_decision.py, quadratic_scoring_kernel.py.

---

## 2. Runtime consumer map

### aurora_handler.py
- Type: stateful wrapper
- Logic Owner: decision_making domain
- Runtime Role: owns symbol state, warmup state, bias history, and delegates to decomposed math/gate mixins.
- Status: ACTIVE

### aurora_config_loader.py
- Type: config resolution layer
- Runtime Role: loads Aurora math/gate config into runtime fields and resolves Phase 9 quadratic routing.
- Actual Runtime Semantics:
  - Activates `QuadraticScoringKernel` as the sole math engine.
  - Required to mount an active shield cascade for production configurations.
- Status: ACTIVE

### aurora_scoring_helpers.py
- Type: math-adjacent helper layer
- Runtime Role: resolves effective regime thresholds, liquidity gate, and side-bias state.
- Status: ACTIVE

### aurora_decision.py
- Type: orchestration layer
- Runtime Role: invokes the selected kernel, applies pre-score and post-score gates, and emits event-visible scoring payloads.
- Status: ACTIVE

### aurora_scoring_kernel.py
- Type: linear Aurora scoring kernel
- Runtime Role: computed live `v2` score, thresholds, hysteresis, and side decision.
- Status: LEGACY / REMOVED (File deleted in Phase 9).

### quadratic_scoring_kernel.py
- Type: nonlinear scoring kernel
- Runtime Role: maps linear conviction (`pillar_sum`) into nonlinear exposure while preserving threshold and hysteresis semantics. Applies Shield Cascade.
- Status: ACTIVE (Sole active path)

---

## 3. Base scoring kernel: SignalScoreV2 (LEGACY)

### SignalScoreV2.calculate_score
- Type: shared centered weighted-score kernel
- Runtime Role: computed normalized directional and strength subscores in linear v2.
- Status: LEGACY / HISTORICAL

### feature_neutrals
- Type: centered-score offsets
- Logic Owner: DecisionConfig.feature_neutrals or per-symbol AuroraInstrumentConfig.feature_neutrals
- Actual Runtime Semantics:
  - Present in Pydantic and YAML for backward-compatibility but completely ignored by `QuadraticScoringKernel`.
- Status: LEGACY

---

## 4. Normalization path

### strategies.aurora.decision.signals.normalize_signals_mode
- Type: strict normalization contract
- Logic Owner: SignalsConfig
- Runtime Role: selects the Aurora directional-feature transform path during feature engineering logic.
- Actual Runtime Semantics:
  - Strict YAML/Pydantic boundary accepts only `signed_v2`.
- Status: ACTIVE

### strategies.aurora.decision.signals.delta_price_cap_pct
- Type: ratio cap
- Logic Owner: SignalsConfig
- Actual Runtime Semantics:
  - Current global YAML value is `0.02`.
- Status: ACTIVE

---

## 5. Direction / strength split (LEGACY)

### strategies.aurora.decision.direction_strength_scoring
- Type: split-score contract
- Logic Owner: DirectionStrengthScoringConfig
- Runtime Role: build the final linear Aurora score from two subscores.
- Actual Runtime Semantics:
  - Loaded by Pydantic but NO LONGER consumed by `QuadraticScoringKernel`.
- Status: LEGACY

### final score range in linear Aurora `v2`
- Status: LEGACY

---

## 6. Weights and active math inputs

### strategies.aurora.decision.signal_weights
- Type: weighted feature map
- Logic Owner: SignalWeights
- Actual Runtime Semantics:
  - Loaded by Pydantic but NO LONGER consumed by `QuadraticScoringKernel` directly as weights.
- Status: LEGACY

### essential_features
- Type: fail-closed readiness contract
- Logic Owner: DecisionConfig.essential_features
- Actual Runtime Semantics:
  - Current global essentials are `obi`, `delta_price`, `macro_resid`.
  - Determines if features are allowed into the `pillar_sum`.
- Status: ACTIVE

---

## 7. Threshold math

### strategies.aurora.decision.signal_threshold
- Type: base threshold
- Logic Owner: DecisionConfig + AuroraDecisionMixin
- Runtime Role: defines the pre-regime, pre-bias entry threshold.
- Actual Runtime Semantics:
  - Current global value is `0.162`.
- Status: ACTIVE

### strategies.aurora.decision.regime_threshold_multipliers
- Type: global threshold factor map
- Logic Owner: DecisionConfig + AuroraConfigLoaderMixin + kernels
- Runtime Role: scales the base signal threshold by regime.
- Mathematical / Behavioral Role:
  `thr0 = base_threshold * regime_factor`
- Actual Runtime Semantics:
  - Missing regime-specific key falls back to `DEFAULT`.
  - Missing `DEFAULT` fail-closes the kernel with `MISSING_REGIME_THRESHOLD:<regime>`.
- Status: ACTIVE

### strategies.aurora.decision.regime_thresholds
- Type: typed config block
- Logic Owner: DecisionConfig only
- Runtime Role: none in traced Aurora math routing.
- Actual Runtime Semantics:
  - Present in Pydantic and YAML.
  - Not loaded by AuroraConfigLoaderMixin for live threshold math.
- Status: DECLARED BUT NOT USED

### per-symbol neutral_threshold override
- Type: runtime probe without typed config boundary
- Runtime Role: legacy or mock-only neutral hysteresis override.
- Status: NOT WIRED

---

## 8. Side bias and hysteresis

### side bias
- Type: threshold-penalty overlay
- Logic Owner: QuadraticScoringKernel + AuroraScoringHelpersMixin
- Runtime Role: raises the threshold on the overrepresented side using recent intent history.
- Mathematical / Behavioral Role:
  - Penalty activates only when `buy_count + sell_count >= min_intents`.
  - Let `sell_share = sell_count / total_count`.
  - If `sell_share > target_ratio`, then:
    `sell_bias_mult = 1 + penalty_factor * ((sell_share - target_ratio) / (1 - target_ratio))`
- Actual Runtime Semantics:
  - Global values loaded from current YAML: `side_bias_window_sec: 420`, `side_bias_target_ratio: 0.72`, `side_bias_penalty_factor: 0.25`, `side_bias_min_intents: 18`.
- Status: ACTIVE

### hysteresis
- Type: 3-zone state machine
- Logic Owner: QuadraticScoringKernel
- Runtime Role: differentiates enter, hold, flip, and exit behavior.
- Mathematical / Behavioral Role:
  - Neutral:
    - BUY if `score >= thr_buy`
    - SELL if `score <= -thr_sell`
  - Existing buy:
    - flip to sell if `score <= -thr_sell`
    - hold buy if `score >= neutral_threshold`
    - else exit to neutral
  - Existing sell:
    - flip to buy if `score >= thr_buy`
    - hold sell if `score <= -neutral_threshold`
    - else exit to neutral
- Status: ACTIVE

---

## 9. Liquidity gate

### strategies.aurora.decision.liquidity_gate
- Type: hard gate config
- Logic Owner: LiquidityGateConfig
- Status: ACTIVE

### liquidity_gate.failsafe_qty_check
- Type: reserved flag
- Logic Owner: LiquidityGateConfig
- Actual Runtime Semantics:
  - Value is parsed, but NO wired runtime path performs the implied verification block yet.
- Status: DECLARED BUT NOT USED

---

## 10. Quadratic math path

### strategies.aurora.decision.scoring_version
- Type: live engine selector
- Logic Owner: DecisionConfig
- Runtime Role: selects the requested Aurora scoring engine family.
- Actual Runtime Semantics:
  - Pydantic still allows `v1 | v2 | quadratic`.
  - Current live YAML value is explicitly `quadratic`.
- Status: ACTIVE

### QuadraticScoringKernel.compute
- Type: nonlinear mandatory kernel (Phase 9)
- Logic Owner: apps/reference/domains/decision_making/quadratic_scoring_kernel.py
- Runtime Role: transforms linear conviction (`pillar_sum`) into nonlinear exposure.
- Mathematical / Behavioral Role:
  `s_linear = linear_score argument or features["pillar_sum"]`
  `s_scaled_raw = s_linear * score_multiplier`
  `s_clamped = clamp(s_scaled_raw, -1, 1)`
  `raw_exposure = sign(s_clamped) * s_clamped^2`
  `final_score = raw_exposure * shield_multiplier`
- Actual Runtime Semantics:
  - Missing `pillar_sum` without explicit `linear_score` enters the aurora kernel's
    anomaly/fail-closed defer path (`PILLAR_WARMUP` raw reason, canonical
    `INTENT_DEFERRED` reason `NRR-DATA-NOT-READY`).
  - This is not the dominant live Aurora "cannot trade now" semantic. Normal live
    no-trade outcomes are expected to surface as `STRATEGY_DECISION_BLOCKED` through
    explicit policy gates outside the kernel.
  - Threshold factor, side bias, and hysteresis semantics are then applied to the squared score.
- Status: ACTIVE

### score_multiplier
- Type: linear-input sensitivity multiplier
- Logic Owner: DecisionConfig + QuadraticScoringKernel
- Runtime Role: scales `s_linear` before clamping and squaring.
- Actual Runtime Semantics:
  - Current global YAML value is `1.0`.
- Status: ACTIVE

### scoring_engine
- Type: typed Quadratic config block
- Logic Owner: ScoringEngineConfig + AuroraConfigLoaderMixin
- Runtime Role: provides shield cascade configuration for Quadratic math.
- Actual Runtime Semantics:
  - Configuration `shield_enabled: true` and associated shield profiles (danger_zone, context, memory) are fully active in `aurora.yaml`.
  - If a strictly-typed production setup tries to run `quadratic` with `NullShield` (effectively disabled shields), it will `ConfigContractError` (fail-closed validator).
- Status: ACTIVE

### quadratic_rollout
- Type: rollout / rollback control block
- Status: LEGACY / OFFLINE (now just fully switched to quadratic)

### AuroraInstrumentConfig.scoring_version
- Type: per-symbol typed override field
- Logic Owner: AuroraInstrumentConfig only
- Status: DECLARED BUT NOT USED

---

## 11. Event-visible math payloads

### ORDER_INTENT metadata.normalize_mode_effective
- Type: observability field
- Logic Owner: intent_builder.py
- Runtime Role: exposes the effective normalization mode used for Aurora intent generation.
- Status: ACTIVE

### EVT:STRATEGY_SIGNAL_PRODUCED rollout payload
- Type: additive signal payload
- Status: ACTIVE

---

## 12. Legacy and drift ledger

### DecisionConfig.regime_thresholds
- Status: DECLARED BUT NOT USED

### AuroraInstrumentConfig.scoring_version
- Status: DECLARED BUT NOT USED

### per-symbol neutral_threshold override
- Status: NOT WIRED

### LiquidityGateConfig.failsafe_qty_check
- Status: DECLARED BUT NOT USED

### DecisionConfig.direction_strength_scoring, feature_neutrals, signal_weights
- Actual Runtime Semantics:
  - Superseded by the `quadratic` Phase 9 migration. Still stored for compatibility but do not dictate math logic inside the kernel.
- Status: LEGACY

---

## 13. Final verdict

Current Aurora math SSOT is:

1. **Quadratic Math** (`scoring_version: "quadratic"`) is the sole active trajectory (Phase 9 Migration complete).
2. Linear `v2` kernel is entirely removed from code.
3. Production normalization is strictly `signed_v2`.
4. Thresholding is `signal_threshold * regime_threshold_multiplier`, then side-bias penalties, then hysteresis.
5. `scoring_engine.shield_enabled=true` must be active for the environment to run.

**Status**: Verified against current code/config. Legacy definitions accurately tagged.
