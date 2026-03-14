# AURORA MATH PASSPORT
## Aurora strategy math and decision semantics — code-driven sync snapshot

> AUDIT SUMMARY
> - Document path: config/docs/aurora_math_passport.md
> - Audit date: 2026-03-13
> - Audit mode: code-driven sync
> - Total claims checked: 28
> - Confirmed: 12
> - Corrected: 11
> - Removed as stale: 5
> - Added as missing: 9
> - Major drifts found:
>   1. The active consumer topology is no longer “one aurora_handler file”; current math path is split across aurora_handler.py, aurora_config_loader.py, aurora_scoring_helpers.py, aurora_decision.py, aurora_scoring_kernel.py, and quadratic_scoring_kernel.py.
>   2. Production config accepts only `signals.normalize_signals_mode = signed_v2`; `off` remains an offline scoring-function-only passthrough, not a YAML value.
>   3. Aurora live math is still linear `v2`; Quadratic math exists and is test-covered, but depends on explicit rollout activation.
>   4. `DecisionConfig.regime_thresholds` is typed but not used in Aurora math routing; active global threshold source is `regime_threshold_multipliers`.
>   5. `AuroraInstrumentConfig.scoring_version` is typed but not consumed by the current Aurora loader.
>   6. Runtime probes for per-symbol `neutral_threshold`, but strict Aurora instrument config does not expose that field.
>   7. `LiquidityGateConfig.failsafe_qty_check` is surfaced in diagnostics only; no qty enforcement path was found.
> - Overall confidence: HIGH

---

## 1. Scope

This passport covers the mathematical and behavioral semantics of Aurora strategy decision-making only.

It traces:

1. Signal normalization.
2. SignalScoreV2 centering and fail-closed behavior.
3. Linear `v2` direction/strength scoring.
4. Optional Quadratic transform and rollout math.
5. Threshold scaling, hysteresis, and side-bias penalties.
6. Liquidity gating and score-adjacent fail-closed behavior.
7. Per-symbol override resolution for math-affecting Aurora fields.
8. Event-visible math metadata emitted from Aurora runtime.

Authoritative sources traced for this passport:

- YAML: config/aurora/strategies/aurora.yaml.
- Pydantic: apps/reference/config_models.py.
- Runtime: apps/reference/domains/decision_making/aurora_handler.py, aurora_config_loader.py, aurora_scoring_helpers.py, aurora_decision.py, aurora_scoring_kernel.py, quadratic_scoring_kernel.py, scoring_direction_strength_v1.py, signal_score_v2.py.
- Contracts: apps/reference/contracts/quadratic_rollout.py.
- Tests: tests/domains/decision_making/test_aurora_scoring_kernel.py, tests/domains/decision_making/test_normalize_mode_ssot.py, tests/test_quadratic_scoring_kernel.py.

---

## 2. Runtime consumer map

### aurora_handler.py
- Type: stateful wrapper
- Logic Owner: decision_making domain
- Runtime Role: owns symbol state, warmup state, bias history, and delegates to decomposed math/gate mixins.
- Actual Runtime Semantics:
  - Still exists as the strategy state wrapper.
  - No longer acts as the sole math SSOT.
- Status: ACTIVE

### aurora_config_loader.py
- Type: config resolution layer
- Runtime Role: loads Aurora math/gate config into runtime fields and resolves live vs Quadratic rollout.
- Actual Runtime Semantics:
  - Reads `signal_threshold`, side-bias params, `regime_threshold_multipliers`, `signals.normalize_signals_mode`, `delta_price_cap_pct`, `holding_period`, `reentry_cooldown_sec`, and rollout state.
  - Activates `QuadraticScoringKernel` only when rollout resolves to live quadratic.
- Status: ACTIVE

### aurora_scoring_helpers.py
- Type: math-adjacent helper layer
- Runtime Role: resolves per-symbol weights, feature neutrals, effective regime thresholds, liquidity gate, and side-bias state.
- Actual Runtime Semantics:
  - Per-symbol `weights`, `feature_neutrals`, `essential_features`, `regime_thresholds`, and `liquidity_gate` all resolve here.
  - Shield cascade is also built here.
- Status: ACTIVE

### aurora_decision.py
- Type: orchestration layer
- Runtime Role: invokes the selected kernel, applies pre-score and post-score gates, and emits event-visible scoring payloads.
- Actual Runtime Semantics:
  - Applies liquidity gate before scoring.
  - Resolves per-symbol signal threshold overrides.
  - Emits `rollout_mode` and `quadratic_rollout` payloads in signal output.
- Status: ACTIVE

### aurora_scoring_kernel.py
- Type: linear Aurora scoring kernel
- Runtime Role: computes live `v2` score, thresholds, hysteresis, and side decision.
- Status: ACTIVE

### quadratic_scoring_kernel.py
- Type: optional nonlinear scoring kernel
- Runtime Role: maps linear conviction into nonlinear exposure while preserving threshold and hysteresis semantics.
- Status: PARTIAL

---

## 3. Base scoring kernel: SignalScoreV2

### SignalScoreV2.calculate_score
- Type: shared centered weighted-score kernel
- Logic Owner: apps/reference/domains/decision_making/signal_score_v2.py
- Runtime Role: computes normalized directional and strength subscores.
- Mathematical / Behavioral Role:

  `score_raw = Σ w_i * (x_i - neutral_i)`

  `wabs = Σ |w_i|` only for active, present, ready, non-zero-weight features

  `score_norm = score_raw / wabs`

  `score = clamp(score_norm, -1, 1)`

- Actual Runtime Semantics:
  - Missing or not-ready essential features defer fail-closed.
  - Missing or malformed non-essential features are skipped.
  - A weighted feature without a neutral is treated as config error and is skipped at runtime after logging.
  - Features that are absent or not ready do not contribute to either numerator or denominator.
- Constraints / Invariants:
  - Every non-zero weighted Aurora feature should have a configured neutral.
  - `score` is always clamped to `[-1, 1]` at this kernel level.
- Status: ACTIVE

### feature_neutrals
- Type: centered-score offsets
- Logic Owner: DecisionConfig.feature_neutrals or per-symbol AuroraInstrumentConfig.feature_neutrals
- Runtime Role: defines the zero-contribution center for each weighted feature.
- Actual Runtime Semantics:
  - Current global neutrals in aurora.yaml:
    - `obi: 0.0`
    - `tfi: 0.0`
    - `delta_price: 0.0`
    - `ema_bias: 0.5`
    - `volume_spike: 0.0`
    - `volatility_state: 0.0`
    - `depth_imbalance: 0.5`
    - `macro_sync: 0.5`
    - `macro_resid: 0.0`
    - `absorption: 0.0`
  - Per-symbol override resolution is `assets.<SYM>.feature_neutrals -> decision.feature_neutrals`.
- Status: ACTIVE

---

## 4. Normalization path

### strategies.aurora.decision.signals.normalize_signals_mode
- Type: strict normalization contract
- Logic Owner: SignalsConfig + AuroraScoringKernel + compute_direction_strength_score
- Runtime Role: selects the Aurora directional-feature transform path.
- Mathematical / Behavioral Role:
  - For directional features with neutral `0.5`:

    `x_eval = 2 * clamp01(x) - 0.5`

    SignalScoreV2 then centers again using neutral `0.5`, so the effective centered term becomes:

    `x_eval - 0.5 = 2 * (x - 0.5)`

  - For directional features with neutral `0.0`:

    `x_eval = clamp(x, -1, 1)`

- Actual Runtime Semantics:
  - Strict YAML/Pydantic boundary accepts only `signed_v2`.
  - `compute_direction_strength_score()` still accepts `off`, but only as an explicit offline/function-level passthrough.
  - `AuroraScoringKernel.compute()` rejects anything except `signed_v2`.
- Event / Output Effect:
  - `normalize_mode_effective` is emitted into ORDER_INTENT metadata through intent_builder.
- Constraints / Invariants:
  - `off`, `net_zero`, and `legacy_v1` are not valid production config values.
- Status: ACTIVE

### strategies.aurora.decision.signals.delta_price_cap_pct
- Type: ratio cap
- Logic Owner: SignalsConfig + AuroraScoringKernel
- Runtime Role: converts raw `delta_price` into bounded signed feature input.
- Mathematical / Behavioral Role:

  `dp_pct = delta_price_raw / price`

  `dp_pct_cap = clamp(dp_pct, -cap, cap)`

  `delta_price_norm = dp_pct_cap / cap`

- Actual Runtime Semantics:
  - Current global YAML value is `0.02`.
  - If `price <= 0` or `cap <= 0`, kernel falls back to normalized `0` rather than exploding.
- Status: ACTIVE

---

## 5. Direction / strength split

### strategies.aurora.decision.direction_strength_scoring
- Type: split-score contract
- Logic Owner: DirectionStrengthScoringConfig + compute_direction_strength_score
- Runtime Role: builds the final linear Aurora score from two subscores.
- Mathematical / Behavioral Role:

  `dir = ScoreV2(directional_features)`

  `strength_base = ScoreV2(strength_features)`

  `strength = clamp(max(0, strength_base), 0, strength_cap)`

  `final_score = dir * (1 + strength_alpha * strength)`

- Actual Runtime Semantics:
  - Current global directional set:
    - `obi, tfi, delta_price, ema_bias, depth_imbalance, macro_resid, macro_sync, absorption`
  - Current global strength set:
    - `volume_spike, volatility_state`
  - Current live multipliers:
    - `strength_alpha: 0.5`
    - `strength_cap: 1.0`
  - `dir` and `strength_base` are each individually clamped by SignalScoreV2.
  - `final_score` is not clamped after multiplication.
  - If no active strength features remain, the function still returns non-deferred output with `strength = 0` and effectively falls back to `final_score = dir`.
- Constraints / Invariants:
  - `directional_features` must be non-empty.
  - Essential features are enforced only through the directional branch.
- Status: ACTIVE

### final score range in linear Aurora `v2`
- Type: derived invariant
- Logic Owner: compute_direction_strength_score
- Runtime Role: bounds the amplitude seen by thresholding/hysteresis.
- Mathematical / Behavioral Role:

  `|dir| <= 1`

  `0 <= strength <= strength_cap`

  `|final_score| <= 1 + strength_alpha * strength_cap`

- Actual Runtime Semantics:
  - With current live config `strength_alpha = 0.5` and `strength_cap = 1.0`, the theoretical linear score range is `[-1.5, 1.5]`.
  - Old docs that implied post-multiplication clamping were inaccurate.
- Status: ACTIVE

---

## 6. Weights and active math inputs

### strategies.aurora.decision.signal_weights
- Type: weighted feature map
- Logic Owner: SignalWeights + AuroraScoringHelpersMixin._get_signal_weights
- Runtime Role: defines directional and strength contributions for the linear Aurora kernel.
- Actual Runtime Semantics:
  - Current global live weights:
    - `obi: 0.42`
    - `tfi: 0.15`
    - `delta_price: 0.15`
    - `ema_bias: 0.15`
    - `volume_spike: 0.10`
    - `volatility_state: 0.10`
    - `depth_imbalance: -0.15`
    - `macro_resid: 0.10`
    - `absorption: 0.0`
    - `macro_sync: 0.0` via defaulted Pydantic compatibility field
  - Per-symbol override resolution is `assets.<SYM>.weights -> decision.signal_weights`.
- Constraints / Invariants:
  - `depth_imbalance` can legitimately be negative-weighted.
  - `macro_sync` remains compatibility-only unless a non-zero weight is reintroduced.
- Status: ACTIVE

### essential_features
- Type: fail-closed readiness contract
- Logic Owner: DecisionConfig.essential_features + AuroraScoringKernel
- Runtime Role: defines which Aurora features must have readiness and data before score calculation proceeds.
- Actual Runtime Semantics:
  - Current global essentials are `obi`, `delta_price`, `macro_resid`.
  - Missing readiness keys defer before score calculation with `MISSING_READY_KEYS:...`.
  - Present-but-not-ready essentials defer via SignalScoreV2.
  - Per-symbol override resolution is `assets.<SYM>.essential_features -> decision.essential_features`.
- Status: ACTIVE

---

## 7. Threshold math

### strategies.aurora.decision.signal_threshold
- Type: base threshold
- Logic Owner: DecisionConfig + AuroraDecisionMixin
- Runtime Role: defines the pre-regime, pre-bias entry threshold.
- Actual Runtime Semantics:
  - Current global value is `0.162`.
  - Strict typed per-symbol override exists as `assets.<SYM>.signal_threshold.enabled/value`.
  - Runtime also accepts direct numeric override for legacy/mock shapes, but that is not the strict Pydantic contract.
- Status: ACTIVE

### strategies.aurora.decision.regime_threshold_multipliers
- Type: global threshold factor map
- Logic Owner: DecisionConfig + AuroraConfigLoaderMixin + kernels
- Runtime Role: scales the base signal threshold by regime.
- Mathematical / Behavioral Role:

  `thr0 = base_threshold * regime_factor`

- Actual Runtime Semantics:
  - Current global map:
    - `HIGH_VOLATILITY: 0.20`
    - `LOW_VOLATILITY: 0.12`
    - `MEAN_REVERSION: 0.16`
    - `TREND_UP: 0.14`
    - `TREND_DOWN: 0.14`
    - `UNCERTAIN: 0.18`
    - `DEFAULT: 0.16`
  - Per-symbol override source is `assets.<SYM>.regime_thresholds` even though the global field name is different.
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
- Logic Owner: AuroraDecisionMixin runtime branch only
- Runtime Role: legacy or mock-only neutral hysteresis override.
- Actual Runtime Semantics:
  - AuroraDecisionMixin probes `instr_cfg.neutral_threshold`.
  - Strict `AuroraInstrumentConfig` does not expose `neutral_threshold`.
  - Under typed live config, no per-symbol neutral-threshold override is available.
- Status: NOT WIRED

---

## 8. Side bias and hysteresis

### side bias
- Type: threshold-penalty overlay
- Logic Owner: AuroraScoringKernel + QuadraticScoringKernel + AuroraScoringHelpersMixin
- Runtime Role: raises the threshold on the overrepresented side using recent intent history.
- Mathematical / Behavioral Role:
  - Penalty activates only when `buy_count + sell_count >= min_intents`.
  - Let `sell_share = sell_count / total_count`.
  - If `sell_share > target_ratio`, then:

    `sell_bias_mult = 1 + penalty_factor * ((sell_share - target_ratio) / (1 - target_ratio))`

  - If buys are the overrepresented side, the symmetric formula applies to `buy_bias_mult`.
- Actual Runtime Semantics:
  - Global values loaded from current YAML:
    - `side_bias_window_sec: 420`
    - `side_bias_target_ratio: 0.72`
    - `side_bias_penalty_factor: 0.25`
    - `side_bias_min_intents: 18`
  - Per-symbol side-bias override supports only `penalty_factor`, `window_sec`, and `target_ratio`.
  - `min_intents` remains global in the current typed runtime path.
- Status: ACTIVE

### hysteresis
- Type: 3-zone state machine
- Logic Owner: AuroraScoringKernel + QuadraticScoringKernel
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
- Actual Runtime Semantics:
  - `thr_buy` and `thr_sell` already include regime-factor and side-bias multipliers.
  - `neutral_threshold` is global-only under strict typed config.
- Status: ACTIVE

---

## 9. Liquidity gate

### strategies.aurora.decision.liquidity_gate
- Type: hard gate config
- Logic Owner: LiquidityGateConfig + AuroraScoringHelpersMixin._check_liquidity_gate
- Runtime Role: blocks Aurora scoring when liquidity readiness or `liquidity_kappa` is insufficient.
- Actual Runtime Semantics:
  - Resolution order:
    1. `assets.<SYM>.liquidity_gate`
    2. `decision.liquidity_gate`
    3. disabled gate
  - Current global live values:
    - `enabled: true`
    - `kappa_min: 0.1`
    - `kappa_max: 1.0`
    - `failsafe_qty_check: true`
  - Fail-closed conditions when enabled:
    - `warmup.ready.liquidity_kappa` must be exactly `true`
    - `features.liquidity_kappa` must exist
    - `features.liquidity_kappa` must be parseable decimal
    - effective `kappa >= kappa_min`
  - `kappa_max` is a defensive clamp only.
  - Failure reasons emitted from helper include `LIQUIDITY_NOT_READY`, `LIQUIDITY_MISSING`, `LIQUIDITY_INVALID`, `LIQUIDITY_LOW`.
- Status: ACTIVE

### liquidity_gate.failsafe_qty_check
- Type: reserved flag
- Logic Owner: LiquidityGateConfig
- Runtime Role: diagnostic echo only.
- Actual Runtime Semantics:
  - Value is attached into gate-failure context.
  - No runtime branch performs the implied quantity/min_qty verification.
- Status: DECLARED BUT NOT USED

---

## 10. Quadratic math path

### strategies.aurora.decision.scoring_version
- Type: live engine selector
- Logic Owner: DecisionConfig + quadratic_rollout contract
- Runtime Role: selects the requested Aurora scoring engine family.
- Actual Runtime Semantics:
  - Pydantic still allows `v1 | v2 | quadratic`.
  - Quadratic rollout contract recognizes only `v2` and `quadratic`; any other token is coerced to `v2` with CRITICAL logging.
  - Current live YAML value is `v2`.
- Status: ACTIVE

### QuadraticScoringKernel.compute
- Type: nonlinear optional kernel
- Logic Owner: apps/reference/domains/decision_making/quadratic_scoring_kernel.py
- Runtime Role: transforms linear conviction into nonlinear exposure when live Quadratic is selected, and also powers shadow evaluation.
- Mathematical / Behavioral Role:

  `s_linear = linear_score argument or features["pillar_sum"]`

  `s_scaled_raw = s_linear * score_multiplier`

  `s_clamped = clamp(s_scaled_raw, -1, 1)`

  `raw_exposure = sign(s_clamped) * s_clamped^2`

  `final_score = raw_exposure * shield_multiplier`

- Actual Runtime Semantics:
  - Missing `pillar_sum` without explicit `linear_score` defers with `PILLAR_WARMUP`.
  - Invalid or NaN/Inf linear inputs defer fail-closed.
  - Threshold factor, side bias, and hysteresis semantics are then reused from the linear path.
- Status: PARTIAL

### score_multiplier
- Type: linear-input sensitivity multiplier
- Logic Owner: DecisionConfig + QuadraticScoringKernel
- Runtime Role: scales `s_linear` before clamping and squaring.
- Actual Runtime Semantics:
  - Current global YAML value is `1.0`.
  - Affects Quadratic math only.
  - Has no effect on live Aurora while `scoring_version` remains `v2`.
- Status: PARTIAL

### scoring_engine
- Type: typed Quadratic config block
- Logic Owner: ScoringEngineConfig + AuroraConfigLoaderMixin + shield builder
- Runtime Role: provides shield cascade configuration for live/shadow Quadratic.
- Actual Runtime Semantics:
  - Current active aurora.yaml does not define `scoring_engine`.
  - Without it, the shield builder returns NullShield.
  - `exposure_cap` and `min_pillar_confidence` are typed fields but no active consumer was found in the current Quadratic compute path.
- Status: NOT WIRED

### quadratic_rollout
- Type: rollout / rollback control block
- Logic Owner: QuadraticRolloutConfig + resolve_requested_quadratic_rollout
- Runtime Role: controls shadow evaluation and explicit rollback when Quadratic is requested.
- Actual Runtime Semantics:
  - Current active aurora.yaml does not define `quadratic_rollout`.
  - Shadow evaluation remains available in code but inactive in current YAML.
- Status: NOT WIRED

### AuroraInstrumentConfig.scoring_version
- Type: per-symbol typed override field
- Logic Owner: AuroraInstrumentConfig only
- Runtime Role: none in traced Aurora loader path.
- Actual Runtime Semantics:
  - Field exists in Pydantic with `Literal["v1", "v2"]`.
  - Current loader resolves scoring version only from `DecisionConfig.scoring_version` and rollout contract.
  - No per-symbol scoring-version consumer was found.
- Status: DECLARED BUT NOT USED

---

## 11. Event-visible math payloads

### ORDER_INTENT metadata.normalize_mode_effective
- Type: observability field
- Logic Owner: intent_builder.py
- Runtime Role: exposes the effective normalization mode used for Aurora intent generation.
- Actual Runtime Semantics:
  - Tests enforce that ORDER_INTENT metadata contains `normalize_mode_effective`.
- Status: ACTIVE

### EVT:STRATEGY_SIGNAL_PRODUCED rollout payload
- Type: additive signal payload
- Logic Owner: AuroraDecisionMixin + quadratic_rollout contract
- Runtime Role: exposes math-mode selection and rollout/shadow state to downstream consumers.
- Actual Runtime Semantics:
  - Payload includes `rollout_mode`, `rollback_armed_status`, and `quadratic_rollout` snapshot data.
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

### DecisionConfig.scoring_version = v1
- Actual Runtime Semantics:
  - Allowed by Pydantic.
  - Coerced to `v2` by rollout resolver.
- Status: LEGACY

### macro_sync
- Actual Runtime Semantics:
  - Still present in directional feature list and neutrals for compatibility.
  - Effective current weight is `0.0`.
- Status: LEGACY

### side_bias_min_score
- Actual Runtime Semantics:
  - Still typed in DecisionConfig as deprecated.
  - No Aurora math consumer was found in the traced path.
- Status: LEGACY

---

## 13. Final verdict

Current Aurora math SSOT is:

1. Linear `v2` direction/strength scoring is the active live path.
2. Production normalization is strictly `signed_v2`.
3. Thresholding is `signal_threshold * regime_threshold_multiplier`, then side-bias penalties, then hysteresis.
4. Liquidity gate is a real hard gate, but `failsafe_qty_check` is not implemented.
5. Quadratic math and rollout contracts are implemented and observable, but they are not active under the current Aurora YAML.

This passport supersedes the previous “Phase 9 math passport” narrative that blurred together implemented Quadratic code and currently active Aurora live math.
