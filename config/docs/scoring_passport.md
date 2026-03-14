# SCORING PASSPORT
## Aurora / Phenix — code-driven sync snapshot

> AUDIT SUMMARY
> - Document path: config/docs/scoring_passport.md
> - Audit date: 2026-03-13
> - Audit mode: code-driven sync
> - Total claims checked: 31
> - Confirmed: 12
> - Corrected: 13
> - Removed as stale: 6
> - Added as missing: 10
> - Major drifts found:
>   1. Active Aurora live scoring is still `v2`; Quadratic runtime exists but is not activated by current YAML.
>   2. Strategy ownership is resolved by config/aurora/strategies.yaml, not by aurora.assets or mean_reversion.assets.
>   3. Aurora kernels consume global `decision.regime_threshold_multipliers` and per-symbol `assets.<SYM>.regime_thresholds`; global `decision.regime_thresholds` is declared but not used by Aurora scoring.
>   4. `DecisionConfig.scoring_version` still allows `v1`, but rollout contract accepts only `v2|quadratic` and coerces any other value to `v2` with CRITICAL logging.
>   5. `ScoringEngineConfig.exposure_cap` and `min_pillar_confidence` are typed but not consumed by the current Aurora runtime path.
>   6. `trading.risk.daily.max_realized_loss_usd` is configured but not consumed by `DailyRiskState.can_open()`; current L1 runtime checks equity availability and drawdown only.
> - Overall confidence: HIGH

---

## 1. Runtime boundary

This passport covers only the active scoring surface for:

1. L1 portfolio risk gate.
2. L2 instrument risk score.
3. L3 strategy-level scoring for Aurora and Mean Reversion.
4. Post-score modulation and gating that materially changes emitted decisions.

The authoritative sources traced for this passport are:

- YAML: config/aurora/trading.yaml, config/aurora/domains.yaml, config/aurora/strategies.yaml, config/aurora/strategies/aurora.yaml, config/aurora/strategies/mean_reversion.yaml.
- Pydantic: apps/reference/config_models.py.
- Runtime: apps/reference/domains/risk_management/*.py, apps/reference/domains/decision_making/*.py, apps/reference/domains/feature_engineering/mean_reversion_strategy.py.
- Contracts: apps/reference/contracts/quadratic_rollout.py, apps/reference/domains/risk_management/schemas/risk_assessment_v1.json, apps/reference/domains/decision_making/schemas/trade_intent_v1.json, apps/reference/domains/decision_making/schemas/str_decision_blocked_v1.json.
- Tests: tests/contracts/test_quadratic_rollout_contract.py, tests/contracts/test_strategy_signal_produced_schema_additive.py, tests/domains/decision_making/test_aurora_scoring_kernel.py, tests/domains/decision_making/test_normalize_mode_ssot.py, tests/test_quadratic_scoring_kernel.py, tests/test_shield_system.py, tests/integration/test_depth_imbalance_signal_contract.py.

---

## 2. Strategy ownership and scoring responsibility

### strategy assignment
- Type: registry / assignment SSOT
- Logic Owner: config/aurora/strategies.yaml
- Runtime Role: determines which strategy is allowed to emit scoring-driven decisions for a symbol.
- Actual Runtime Semantics:
  - BTCUSDT, ETHUSDT, SOLUSDT are assigned to `aurora`.
  - DOGEUSDT is assigned to `mean_reversion`.
  - XRPUSDT and BNBUSDT are assigned to `md_amr`.
  - 1000PEPEUSDT is assigned to `llm_microstructure`.
- Constraints / Invariants:
  - `aurora.assets` and `mean_reversion.assets` tune parameters; they do not replace strategy assignment.
  - A symbol must satisfy both registry assignment and per-strategy `enabled` flags.
- Status: ACTIVE

### aurora.assets / mean_reversion.assets
- Type: per-symbol strategy tuning
- Logic Owner: strategy-specific YAML + Pydantic asset models
- Runtime Role: override weights, thresholds, holding periods, liquidity gates, and regime filters for symbols already assigned to that strategy.
- Actual Runtime Semantics:
  - These blocks are parameter overlays only.
  - Old passport text that treated `assets` as the symbol router was incorrect.
- Status: ACTIVE

---

## 3. L1 portfolio gate

### trading.risk.daily
- Type: YAML block
- Logic Owner: apps/reference/domains/risk_management/daily_gate.py
- Runtime Role: portfolio-level open-risk gate before strategy score can matter.
- Mathematical / Behavioral Role:
  - If enabled, `can_open()` blocks when equity data is missing or when intraday drawdown reaches the configured threshold.
  - Drawdown formula in runtime:

    `drawdown_pct = (1 - equity_now / equity_open) * 100`

- Actual Runtime Semantics:
  - Current YAML sets `trading.risk.daily.enabled: false`.
  - Because the gate is disabled, L1 daily blocking is inactive in the current config.
  - If enabled later, missing `equity_open` or `equity_now` is fail-closed and returns `NO_EQUITY`.
- Constraints / Invariants:
  - `max_drawdown_pct` and `reset_time_utc` are required when enabled.
  - Runtime persistence is disabled in backtest mode.
- Status: PARTIAL

### trading.risk.daily.max_realized_loss_usd
- Type: YAML field
- Logic Owner: trading.yaml only
- Runtime Role: none in the traced L1 open gate.
- Actual Runtime Semantics:
  - Present in YAML.
  - Not consumed by the active DailyGate open-risk decision.
- Status: DECLARED BUT NOT USED

---

## 4. L2 instrument risk score

### risk_management.risk_score_weights
- Type: Pydantic + YAML
- Logic Owner: apps/reference/domains/risk_management/risk_management.py
- Runtime Role: produces per-symbol `risk_score` and `is_trading_allowed` before strategy intent emission.
- Mathematical / Behavioral Role:

  `delta_price_pct = abs(delta_price) / price`

  `risk_score = delta_price_pct * w_dp + abs(obi) * w_obi + abs(tfi) * w_tfi + applied_toxicity + applied_feature`

  `risk_score = clamp(risk_score, 0, 1)`

- Actual Runtime Semantics:
  - Current YAML in config/aurora/domains.yaml:
    - `use_absorption_penalty: true`
    - `absorption_dp_cap_pct: 0.02`
    - `absorption_penalty_source: feature`
    - `risk_score_weights.delta_price_pct: 0.1`
    - `risk_score_weights.obi: 0.3`
    - `risk_score_weights.tfi: 0.3`
    - `risk_score_weights.absorption_inverse: 0.3`
    - `risk_score_weights.absorption_feature: 0.2`
    - `trading_allowed_thresholds.max_risk_score: 0.96`
  - Because source is `feature`, the active absorption term is:

    `applied_feature = clip(abs(absorption), clip_min, clip_max) * absorption_feature_weight`

  - The proxy term based on `|tfi| * clip(delta_price_pct / dp_cap)` is currently supported by runtime but is inactive under the current YAML source selection.
- Event / Schema Effect:
  - `EVT:RISK_ASSESSMENT_COMPLETED` includes `risk_score`, `is_trading_allowed`, and `risk_terms` in apps/reference/domains/risk_management/schemas/risk_assessment_v1.json.
- Constraints / Invariants:
  - `price <= 0` raises runtime error.
  - `absorption_dp_cap_pct` is required when `use_absorption_penalty=True`.
- Status: ACTIVE

### absorption_penalty_source
- Type: routing selector
- Logic Owner: RiskManagementDomainConfig + RiskManagement runtime
- Runtime Role: switches between proxy, feature, or both absorption penalties.
- Actual Runtime Semantics:
  - `proxy`: uses `|tfi|` and normalized delta-price impact.
  - `feature`: uses emitted `absorption` feature value.
  - `both`: adds both terms.
  - Current YAML is `feature`.
- Status: ACTIVE

---

## 5. Aurora L3 live scoring

### strategies.aurora.decision.scoring_version
- Type: Pydantic enum + runtime rollout selector
- Logic Owner: DecisionConfig + apps/reference/contracts/quadratic_rollout.py
- Runtime Role: selects the live Aurora kernel family.
- Actual Runtime Semantics:
  - Pydantic still allows `v1 | v2 | quadratic`.
  - Runtime rollout contract recognizes only `v2` and `quadratic` as valid live values.
  - Any unrecognized value, including `v1`, is coerced to `v2` with CRITICAL logging.
  - Current YAML sets `scoring_version: "v2"`.
- Constraints / Invariants:
  - This mismatch between model enum and rollout contract is real runtime drift.
- Status: ACTIVE

### strategies.aurora.decision.signal_weights
- Type: weighted feature config
- Logic Owner: AuroraScoringKernel + compute_direction_strength_score
- Runtime Role: directional and strength contribution weights for live Aurora `v2` scoring.
- Actual Runtime Semantics:
  - Current global YAML weights:
    - `obi: 0.42`
    - `tfi: 0.15`
    - `delta_price: 0.15`
    - `ema_bias: 0.15`
    - `volume_spike: 0.10`
    - `volatility_state: 0.10`
    - `depth_imbalance: -0.15`
    - `macro_resid: 0.10`
    - `absorption: 0.0`
    - `macro_sync` is omitted in YAML and defaults to `0.0` in Pydantic.
  - Per-symbol Aurora overrides live under `aurora.assets.<SYM>.weights`.
- Constraints / Invariants:
  - Every non-zero weighted feature must have a neutral in `feature_neutrals`.
  - `depth_imbalance` is intentionally negative-weighted.
- Status: DEPRECATED (Phase 9) — parsed for config compat, ignored by QuadraticScoringKernel

### strategies.aurora.decision.feature_neutrals
- Type: centered scoring config
- Logic Owner: DEPRECATED — SignalScoreV2 / scoring_direction_strength_v1.py (DELETED in Phase 9)
- Runtime Role: DEPRECATED — QuadraticScoringKernel does NOT read feature_neutrals. Retained for config schema only.
- Actual Runtime Semantics:
  - Current global neutrals:
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
- Mathematical / Behavioral Role:
  - `SignalScoreV2` computes `score_raw = Σ w_i * (x_i - neutral_i)` and normalizes by `Σ |w_i|`.
- Status: DEPRECATED (Phase 9) — feature_neutrals parsed for config compat, ignored by QuadraticScoringKernel

### strategies.aurora.decision.signals.normalize_signals_mode
- Type: normalization contract
- Logic Owner: DEPRECATED — SignalsConfig + AuroraScoringKernel + scoring_direction_strength_v1.py (DELETED in Phase 9)
- Runtime Role: DEPRECATED — QuadraticScoringKernel does not use normalize_signals_mode for scoring. Retained for config parsing only.
- Actual Runtime Semantics:
  - Pydantic YAML contract allows only `signed_v2`.
  - QuadraticScoringKernel accepts but ignores this parameter.
- Mathematical / Behavioral Role:
  - For directional features with neutral `0.5`, runtime transform is:

    `x_eval = 2 * clamp01(x) - 0.5`

    and SignalScoreV2 then centers again against neutral `0.5`, producing effective centered magnitude `2 * (x - 0.5)`.
  - For directional features with neutral `0.0`, runtime clamps to `[-1, 1]`.
- Constraints / Invariants:
  - Old passport text that described production support for multiple normalization modes was stale.
- Status: ACTIVE

### strategies.aurora.decision.direction_strength_scoring
- Type: feature split contract
- Logic Owner: compute_direction_strength_score
- Runtime Role: divides Aurora live scoring into directional and strength channels.
- Mathematical / Behavioral Role:

  `dir = ScoreV2(directional_features)`

  `strength = clamp(max(0, ScoreV2(strength_features)), 0, strength_cap)`

  `final = dir * (1 + strength_alpha * strength)`

- Actual Runtime Semantics:
  - Current global config:
    - directional: `obi, tfi, delta_price, ema_bias, depth_imbalance, macro_resid, macro_sync, absorption`
    - strength: `volume_spike, volatility_state`
    - `strength_alpha: 0.5`
    - `strength_cap: 1.0`
  - `macro_sync` remains in the directional list for compatibility, but with effective weight `0.0` it does not affect live score.
  - `absorption` is part of the directional set but has current live weight `0.0`.
- Constraints / Invariants:
  - `directional_features` must include all `essential_features`.
- Status: ACTIVE

### strategies.aurora.decision.essential_features
- Type: readiness gate
- Logic Owner: AuroraScoringKernel + SignalScoreV2
- Runtime Role: fail-closed scoring precondition.
- Actual Runtime Semantics:
  - Current global essentials are `obi`, `delta_price`, `macro_resid`.
  - Aurora kernel first requires readiness keys to exist.
  - Missing readiness keys produce `MISSING_READY_KEYS:...`.
  - Missing or not-ready essential directional features later produce deferred `NRR-FEATURES-MISSING` or `NRR-FEATURES-NOT-READY` outcomes.
- Status: ACTIVE

### strategies.aurora.decision.signal_threshold
- Type: base entry threshold
- Logic Owner: AuroraConfigLoaderMixin + AuroraDecisionMixin + AuroraScoringKernel
- Runtime Role: base threshold before regime and side-bias scaling.
- Actual Runtime Semantics:
  - Current global value is `0.162`.
  - Per-symbol override may exist under `aurora.assets.<SYM>.signal_threshold`.
- Status: ACTIVE

### strategies.aurora.decision.neutral_threshold
- Type: hysteresis exit/hold threshold
- Logic Owner: AuroraDecisionMixin + AuroraScoringKernel
- Runtime Role: defines the neutral hold/exit zone once already in a side.
- Actual Runtime Semantics:
  - Current global value is `0.05`.
  - Per-symbol override may exist under `aurora.assets.<SYM>.neutral_threshold`.
- Status: ACTIVE

### strategies.aurora.decision.regime_threshold_multipliers
- Type: global threshold factor map
- Logic Owner: AuroraConfigLoaderMixin + AuroraScoringKernel / QuadraticScoringKernel
- Runtime Role: scales the base threshold by regime.
- Actual Runtime Semantics:
  - Current global map:
    - `HIGH_VOLATILITY: 0.20`
    - `LOW_VOLATILITY: 0.12`
    - `MEAN_REVERSION: 0.16`
    - `TREND_UP: 0.14`
    - `TREND_DOWN: 0.14`
    - `UNCERTAIN: 0.18`
    - `DEFAULT: 0.16`
  - Effective threshold is:

    `signal_threshold_effective = base_threshold * regime_factor`

  - Per-symbol Aurora overrides are stored under `aurora.assets.<SYM>.regime_thresholds` despite the different field name.
- Status: ACTIVE

### strategies.aurora.decision.regime_thresholds
- Type: declared config block
- Logic Owner: DecisionConfig only
- Runtime Role: none in the traced Aurora kernel path.
- Actual Runtime Semantics:
  - Present in Pydantic and YAML.
  - AuroraConfigLoaderMixin loads `regime_threshold_multipliers`, not this block.
  - Aurora kernels consume per-symbol `assets.<SYM>.regime_thresholds` or global `decision.regime_threshold_multipliers`.
- Status: DECLARED BUT NOT USED

### side bias
- Type: threshold penalty overlay
- Logic Owner: AuroraScoringKernel / QuadraticScoringKernel / aurora_scoring_helpers.py
- Runtime Role: penalizes the overrepresented direction in the recent intent window.
- Mathematical / Behavioral Role:
  - If `buy_count + sell_count < min_intents`, no penalty applies.
  - Else compute sell share over the configured window.
  - If sell share exceeds `target_ratio`, increase sell threshold.
  - If buy share exceeds `target_ratio`, increase buy threshold.
  - Penalty scales linearly with excess share and is bounded by the configured `penalty_factor`.
- Actual Runtime Semantics:
  - Current global values:
    - `side_bias_window_sec: 420`
    - `side_bias_target_ratio: 0.72`
    - `side_bias_penalty_factor: 0.25`
    - `side_bias_min_intents: 18`
  - Per-symbol override exists under `aurora.assets.<SYM>.side_bias`.
- Status: ACTIVE

### hysteresis
- Type: behavioral state logic
- Logic Owner: AuroraScoringKernel and QuadraticScoringKernel
- Runtime Role: separates `enter`, `hold`, `exit`, and `flip` semantics.
- Actual Runtime Semantics:
  - Neutral state:
    - buy if `score >= thr_buy`
    - sell if `score <= -thr_sell`
    - else neutral
  - Existing long:
    - flip to sell if `score <= -thr_sell`
    - hold buy if `score >= neutral_threshold`
    - else exit to neutral
  - Existing short:
    - flip to buy if `score >= thr_buy`
    - hold sell if `score <= -neutral_threshold`
    - else exit to neutral
- Status: ACTIVE

### liquidity gate
- Type: hard pre-score gate
- Logic Owner: aurora_scoring_helpers.py
- Runtime Role: blocks Aurora scoring when liquidity readiness or liquidity_kappa is insufficient.
- Actual Runtime Semantics:
  - Resolution order:
    1. `aurora.assets.<SYM>.liquidity_gate`
    2. `aurora.decision.liquidity_gate`
    3. disabled gate
  - Current global gate is enabled with `kappa_min: 0.1`, `kappa_max: 1.0`.
  - Fail-closed requirements when enabled:
    - `warmup.ready.liquidity_kappa` must be `true`
    - `features.liquidity_kappa` must exist and be parseable
    - parsed `kappa >= kappa_min`
  - Returned reject reasons include `LIQUIDITY_NOT_READY`, `LIQUIDITY_MISSING`, `LIQUIDITY_INVALID`, `LIQUIDITY_LOW`.
- Constraints / Invariants:
  - `failsafe_qty_check` is carried through diagnostics only; no qty enforcement path was found in the gate logic.
- Status: ACTIVE

### liquidity_gate.failsafe_qty_check
- Type: parsed flag
- Logic Owner: LiquidityGateConfig
- Runtime Role: diagnostic echo only.
- Actual Runtime Semantics:
  - The field is returned in block context, but no runtime branch performs the promised qty cross-check.
- Status: DECLARED BUT NOT USED

---

## 6. Quadratic scoring path

### DecisionConfig.scoring_engine
- Type: typed Quadratic config container
- Logic Owner: ScoringEngineConfig + AuroraConfigLoaderMixin + shield builder
- Runtime Role: provides shield cascade config when Quadratic is explicitly requested.
- Actual Runtime Semantics:
  - Current active YAML does not define `scoring_engine`.
  - Because live `scoring_version` is `v2`, current production Aurora path does not use Quadratic runtime.
- Status: NOT WIRED

### DecisionConfig.quadratic_rollout
- Type: rollout / rollback config
- Logic Owner: resolve_requested_quadratic_rollout
- Runtime Role: supports shadow evaluation, explicit rollback arm, and startup/operator visibility.
- Actual Runtime Semantics:
  - Current active YAML does not define `quadratic_rollout`.
  - Without this block, no shadow request and no rollback arm are active.
  - Runtime still emits startup/operator-visible rollout state if configured later.
- Status: NOT WIRED

### QuadraticScoringKernel
- Type: optional Aurora L3 kernel
- Logic Owner: apps/reference/domains/decision_making/quadratic_scoring_kernel.py
- Runtime Role: converts a linear conviction source into nonlinear exposure when live Quadratic is selected or when Quadratic shadow is requested.
- Mathematical / Behavioral Role:

  `s_linear = linear_score argument or features["pillar_sum"]`

  `s_scaled_raw = s_linear * score_multiplier`

  `s_clamped = clamp(s_scaled_raw, -1, 1)`

  `raw_exposure = sign(s_clamped) * s_clamped^2`

  `final_score = raw_exposure * shield_multiplier`

  Thresholding and hysteresis then reuse the same regime-factor and side-bias semantics as the linear kernel.

- Actual Runtime Semantics:
  - If `pillar_sum` is absent and no explicit `linear_score` is provided, runtime defers with `PILLAR_WARMUP`.
  - Shadow evaluation and rollout snapshots are first-class runtime contracts and are covered by contract tests.
  - In the current live YAML this path is present in code but inactive.
- Event / Schema Effect:
  - Quadratic rollout payload is carried in `EVT:STRATEGY_SIGNAL_PRODUCED` additive contract coverage via tests/contracts/test_strategy_signal_produced_schema_additive.py.
- Status: PARTIAL

### shield cascade
- Type: optional attenuation / veto layer
- Logic Owner: aurora_scoring_helpers.py, shields/*
- Runtime Role: modifies Quadratic score before thresholding.
- Actual Runtime Semantics:
  - Cascade order is fixed:
    1. DangerZoneShield
    2. ContextShield
    3. MemoryShield
  - Cascade is built only when `scoring_engine.shield_enabled=True`.
  - Current active YAML does not provide `scoring_engine`, therefore live shield cascade is inactive.
  - Test coverage confirms expected attenuation and veto behavior, but that is not the current live configuration.
- Status: NOT WIRED

### ScoringEngineConfig.exposure_cap
- Type: typed config field
- Logic Owner: ScoringEngineConfig only
- Runtime Role: none in traced Aurora decision flow.
- Actual Runtime Semantics:
  - The field exists in Pydantic.
  - Current Aurora Quadratic kernel does not read it.
  - Aurora quantization calls `quantize_exposure()` without passing a config-driven exposure cap.
- Status: DECLARED BUT NOT USED

### ScoringEngineConfig.min_pillar_confidence
- Type: typed config field
- Logic Owner: ScoringEngineConfig only
- Runtime Role: none in traced Aurora decision flow.
- Actual Runtime Semantics:
  - The field exists in Pydantic.
  - No active consumer was found in Aurora Quadratic routing.
- Status: DECLARED BUT NOT USED

---

## 7. Post-score modulation and hard gates

### holding_period
- Type: anti-churn gate
- Logic Owner: AuroraHoldingPeriodMixin
- Runtime Role: suppresses soft exits and flips before minimum hold time elapses.
- Actual Runtime Semantics:
  - Global YAML is enabled with:
    - `min_duration_sec: 900`
    - `emergency_exit_threshold: 0.90`
    - `apply_to_flips: true`
  - Per-symbol overrides exist in Aurora assets.
  - Emergency override allows exit when `abs(score) >= emergency_exit_threshold`.
  - If no entry timestamp is known, runtime fails open for exit suppression.
- Status: ACTIVE

### reentry_cooldown_sec
- Type: anti-ping-pong gate
- Logic Owner: AuroraHoldingPeriodMixin
- Runtime Role: blocks immediate re-entry after close.
- Actual Runtime Semantics:
  - Global YAML value is `900` seconds.
  - Per-symbol overrides exist in Aurora assets.
  - Runtime stores last exit timestamp and scales cooldown by anti-churn time multipliers if those are enabled.
- Status: ACTIVE

### gates (anti-flat / anti-fomo)
- Type: sigma-normalized motion gate
- Logic Owner: DecisionConfig.gates + Aurora runtime decision path
- Runtime Role: blocks entries in dead or extreme markets before final intent emission.
- Actual Runtime Semantics:
  - Current global YAML is enabled with:
    - `anti_flat_sigma: 0.48`
    - `anti_fomo_sigma: 10.0`
    - `motion_window_sec: 300`
  - Config model constrains anti-fomo to `[1.0, 10.0]`.
- Status: ACTIVE

### anchor_shock_veto
- Type: directional safety veto
- Logic Owner: DecisionConfig + AuroraDecisionMixin
- Runtime Role: blocks BUY when anchor crash condition is met.
- Actual Runtime Semantics:
  - Current global YAML is enabled.
  - Anchor symbol is `BTCUSDT`.
  - Threshold is `-2.0` on `macro_resid`.
  - Logic only applies when the traded symbol is not the anchor itself.
- Status: ACTIVE

### EntryPlan
- Type: structural pre-execution calculator
- Logic Owner: domains.decision_making.entry_plan + AuroraDecisionMixin
- Runtime Role: computes entry, SL, TP, and confidence-derived structural values before Objective Engine and ExecutionGate.
- Actual Runtime Semantics:
  - Domain YAML enables EntryPlan.
  - Aurora Objective Engine depends on EntryPlan being present; if EntryPlan result is absent, Aurora blocks with `OBJECTIVE_ENTRY_PLAN_MISSING`.
- Status: ACTIVE

### Objective Engine seam
- Type: post-score multiplier and gate
- Logic Owner: objective_engine domain + strategy objective profiles + AuroraDecisionMixin
- Runtime Role: multiplies the already produced strategy score and can block the trade after structural preparation.
- Mathematical / Behavioral Role:

  `total_penalty = Σ regime_weight[c] * component_score[c]`

  `z = total_penalty * lambda_scale`

  `normalized_penalty = sigmoid_normalize(z, center=penalty_center, scale=penalty_scale)`

  `multiplier = clamp(m_min + normalized_penalty * (m_max - m_min), m_min, m_max)`

  `objective_score = signal_score * multiplier`

  `block if enforcement_mode == "GATE" and signal_direction != 0 and abs(objective_score) < min_objective_score`

- Actual Runtime Semantics:
  - Current domain YAML has `objective_engine.enabled: true` and enabled components.
  - Current Aurora strategy YAML has `objective.enabled: true` with regime-specific weights, multiplier bounds, and gate modes.
  - Aurora integrates Objective Engine after EntryPlan and before ExecutionGate.
  - Aurora fail-closes on missing preconditions: cost component, behavior component, portfolio snapshot, exposure summary, regime, regime timestamp, or EntryPlan result.
  - Objective trace is attached into `result.psi_vector["objective"]` and later validated by strategy gateway logic.
- Status: ACTIVE

### ExecutionGate
- Type: final hard gate bundle
- Logic Owner: DecisionConfig.execution + AuroraDecisionMixin
- Runtime Role: final gate after scoring, EntryPlan, and Objective Engine.
- Actual Runtime Semantics:
  - If gate check fails, runtime emits `EXECUTION_GATE_BLOCKED` and no intent is emitted.
- Status: ACTIVE

---

## 8. Mean Reversion scoring

### mean_reversion runtime ownership
- Type: strategy-specific runtime
- Logic Owner: config/aurora/strategies/mean_reversion.yaml + mean_reversion_handler.py + feature_engineering/mean_reversion_strategy.py
- Runtime Role: independent L3 scoring path for symbols assigned to the MR strategy.
- Actual Runtime Semantics:
  - Current registry assignment gives Mean Reversion only to DOGEUSDT.
  - BTCUSDT, XRPUSDT, SOLUSDT remain present in YAML as asset configs, but are not active MR scoring owners under current assignment and/or enabled flags.
- Status: ACTIVE

### mean_reversion.allowed_regimes
- Type: strict allowlist
- Logic Owner: MeanReversionHandler config resolution + MeanReversion1mStrategy.on_bar
- Runtime Role: fail-closed regime filter for MR signals.
- Actual Runtime Semantics:
  - Global default allowlist is `FLAT_LOW`, `FLAT_NORMAL`, `FLAT_HIGH`, `MEAN_REVERSION`.
  - Resolution order is global default, then per-asset override.
  - If mapped flat regime is not in the explicit allowlist, runtime returns neutral with `regime_not_allowed:<REGIME>`.
- Status: ACTIVE

### mean_reversion signal formula
- Type: Bollinger/%B scoring
- Logic Owner: feature_engineering/mean_reversion_strategy.py
- Runtime Role: generates LONG / SHORT / NEUTRAL MR signals from completed bars.
- Mathematical / Behavioral Role:
  - LONG when `pct_b < entry_threshold`
  - SHORT when `pct_b > 1 - entry_threshold`
  - Base confidence:

    `confidence = confidence_base + distance_from_entry_boundary * confidence_bb_slope`

  - RSI bonus:
    - add `confidence_rsi_bonus` for oversold confirmation on LONG
    - add `confidence_rsi_bonus` for overbought confirmation on SHORT
  - Confidence is clamped to `1.0`.
  - BB width too narrow or too wide returns neutral.
  - Cooldown and minimum bars are enforced before signal generation.
- Actual Runtime Semantics:
  - Global defaults in YAML:
    - `bb_window: 20`
    - `bb_num_std: 2.0`
    - `entry_threshold: 0.115`
    - `confidence_base: 0.5`
    - `confidence_bb_slope: 2.0`
    - `confidence_rsi_bonus: 0.2`
  - Active assigned asset DOGEUSDT overrides:
    - `bb_window: 40`
    - `bb_num_std: 2.5`
    - `entry_threshold: 0.05`
  - Current passport text that treated BTC/XRP/SOL as active MR scoring examples was stale.
- Status: ACTIVE

### mean_reversion liquidity gate
- Type: hard pre-emission gate
- Logic Owner: MeanReversionHandler._check_liquidity_gate
- Runtime Role: blocks MR signal emission if cached `liquidity_kappa` is missing or below threshold when gate is enabled.
- Actual Runtime Semantics:
  - Resolution order is per-asset gate, then global MR gate.
  - Missing `liquidity_kappa` while the gate is enabled raises runtime error instead of silently passing.
- Status: ACTIVE

### mean_reversion objective seam
- Type: post-signal multiplier and gate
- Logic Owner: MeanReversionHandler + objective_engine
- Runtime Role: same Objective Engine domain can downscale or block MR signals.
- Actual Runtime Semantics:
  - Unlike Aurora, MR raises hard failures on missing objective preconditions and then translates them to block/fail-closed behavior.
- Status: ACTIVE

---

## 9. Event and contract effects

### EVT:RISK_ASSESSMENT_COMPLETED
- Type: JSON schema-backed event
- Logic Owner: risk_management domain
- Runtime Role: exposes L2 outcome for downstream decision logic and observability.
- Actual Runtime Semantics:
  - Schema includes `risk_score`, `is_trading_allowed`, and `risk_terms`.
- Status: ACTIVE

### EVT:TRADE_INTENT_PROPOSED
- Type: JSON schema-backed event
- Logic Owner: intent_builder.py + trade_intent_v1.json
- Runtime Role: carries final decision intent to execution.
- Actual Runtime Semantics:
  - Payload includes `strategy`, `regime`, `regime_confidence`, `risk_context`, EntryPlan fields, and standard execution/sizing fields.
  - `risk_context` currently carries `risk_score` from decision-making intent assembly.
- Status: ACTIVE

### EVT:STRATEGY_DECISION_BLOCKED
- Type: JSON schema-backed event
- Logic Owner: Aurora / MR handlers + str_decision_blocked_v1.json
- Runtime Role: canonical block surface for gates, fail-closed paths, and precondition failures.
- Actual Runtime Semantics:
  - Used for liquidity, holding period, objective preconditions, objective gate, execution gate, and readiness failures.
- Status: ACTIVE

### EVT:STRATEGY_SIGNAL_PRODUCED additive scoring payload
- Type: test-backed additive contract
- Logic Owner: AuroraDecisionMixin + strategy gateway tests
- Runtime Role: exposes scoring trace, rollout state, readiness state, and optional objective trace.
- Actual Runtime Semantics:
  - `quadratic_rollout`, `rollout_mode`, and shadow-evaluation payload are contract-covered by tests.
  - Objective trace shape is validated in strategy gateway logic before downstream use.
  - No standalone JSON schema file was found for this additive surface; the contract is enforced by tests.
- Status: ACTIVE

---

## 10. Legacy and drift ledger

### macro_sync
- Type: feature / compatibility field
- Logic Owner: FeatureEngineering + SignalWeights backward compatibility
- Runtime Role: telemetry-compatible directional feature name with effective live L3 weight `0.0`.
- Actual Runtime Semantics:
  - Present in neutrals and directional feature list.
  - Omitted from current Aurora YAML weights and defaults to `0.0` in Pydantic.
  - Does not contribute to current Aurora live score.
- Status: LEGACY

### DecisionConfig.scoring_version = v1
- Type: model enum value
- Logic Owner: DecisionConfig legacy surface
- Runtime Role: none in current rollout contract.
- Actual Runtime Semantics:
  - Allowed by Pydantic.
  - Coerced to `v2` by rollout resolver.
- Status: LEGACY

### decision.regime_thresholds
- Type: stale/global config branch for Aurora scoring
- Actual Runtime Semantics: present in YAML and model, not consumed by Aurora kernels.
- Status: DECLARED BUT NOT USED

### scoring_engine.exposure_cap
- Type: typed but unused config
- Status: DECLARED BUT NOT USED

### scoring_engine.min_pillar_confidence
- Type: typed but unused config
- Status: DECLARED BUT NOT USED

### liquidity_gate.failsafe_qty_check
- Type: parsed but not enforced field
- Status: DECLARED BUT NOT USED

### trading.risk.daily.max_realized_loss_usd
- Type: configured but not consumed by can_open()
- Status: DECLARED BUT NOT USED

---

## 11. Final verdict

Current scoring reality is not “Phase 9 Quadratic live”. Current runtime is:

1. Aurora live on `v2` linear direction/strength scoring with hard fail-closed readiness, liquidity gating, side-bias, hysteresis, holding period, re-entry cooldown, Objective Engine modulation, and ExecutionGate.
2. Quadratic scoring, shield cascade, rollout state, and shadow evaluation are implemented and contract-tested, but not activated by the current Aurora YAML.
3. L2 risk scoring is active and currently uses absorption feature routing from domains.yaml.
4. L1 daily gate code exists, but the current YAML disables it, and realized-loss blocking is not implemented in the traced open gate.
5. Mean Reversion remains a separate Bollinger/%B scoring path, currently assigned only to DOGEUSDT.

This passport should be treated as the current SSOT for scoring behavior until runtime or YAML changes invalidate one of the statuses above.
