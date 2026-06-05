# SCORING PASSPORT
## Aurora / Phenix — code-driven sync snapshot

> AUDIT SUMMARY
> - Document path: config/docs/scoring_passport.md
> - Audit date: 2026-05-28
> - Audit mode: code-driven sync
> - Major drifts found:
>   1. Active Aurora live scoring is now `quadratic` (Phase 9 Migration complete). Linear `v2` scoring kernel has been removed.
>   2. `scoring_engine.shield_enabled=true` is now mandatory in production for Quadratic scoring, effectively activating the Shield Cascade.
>   3. `direction_strength_scoring`, `feature_neutrals`, and `signal_weights` are deprecated/legacy; they are not consumed by the active quadratic path.
>   4. Strategy ownership is verified in `config/aurora/strategies.yaml` and is now Aurora-led across all seven configured instruments, with hybrid overlays on DOGEUSDT, BTCUSDT, ETHUSDT, and SOLUSDT.
>   5. `trading.risk.daily.max_realized_loss_usd` remains configured in YAML but is not consumed by the current L1 daily risk gate.
> - Overall confidence: HIGH

---

## 1. Runtime boundary

This passport covers only the active scoring surface for:

1. L1 portfolio risk gate.
2. L2 instrument risk score.
3. L3 strategy-level scoring for Aurora, Mean Reversion, MD AMR, etc.
4. Post-score modulation and gating that materially changes emitted decisions.

The authoritative sources traced for this passport are:

- YAML: config/aurora/trading.yaml, config/aurora/domains.yaml, config/aurora/strategies.yaml, config/aurora/strategies/aurora.yaml, config/aurora/strategies/mean_reversion.yaml.
- Pydantic: apps/reference/config_models.py.
- Runtime: apps/reference/domains/risk_management/*.py, apps/reference/domains/decision_making/*.py, apps/reference/domains/feature_engineering/mean_reversion_strategy.py, quadratic_scoring_kernel.py.

---

## 2. Strategy ownership and scoring responsibility

### strategy assignment
- Type: registry / assignment SSOT
- Logic Owner: config/aurora/strategies.yaml
- Runtime Role: determines which strategy is allowed to emit scoring-driven decisions for a symbol.
- Actual Runtime Semantics:
  - BTCUSDT, ETHUSDT, SOLUSDT, DOGEUSDT, XRPUSDT, BNBUSDT, and 1000PEPEUSDT are assigned to `aurora`.
  - DOGEUSDT also remains assigned to `mean_reversion`.
  - BTCUSDT, ETHUSDT, SOLUSDT, and DOGEUSDT are additionally assigned to `llm_microstructure`.
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
  - Because the gate is disabled globally in typical backtests, L1 daily blocking may be inactive. If enabled later, missing `equity_open` or `equity_now` is fail-closed and returns `NO_EQUITY`.
- Constraints / Invariants:
  - `max_drawdown_pct` and `reset_time_utc` are required when enabled.
- Status: PARTIAL

### trading.risk.daily.max_realized_loss_usd
- Type: YAML field
- Logic Owner: trading.yaml only
- Runtime Role: none in the traced L1 open gate.
- Actual Runtime Semantics:
  - Present in YAML. Not consumed by the active DailyGate open-risk decision.
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
    - `absorption_penalty_source: feature`
- Status: ACTIVE

### absorption_penalty_source
- Type: routing selector
- Logic Owner: RiskManagementDomainConfig + RiskManagement runtime
- Runtime Role: switches between proxy, feature, or both absorption penalties.
- Actual Runtime Semantics:
  - `proxy`: uses `|tfi|` and normalized delta-price impact.
  - `feature`: uses emitted `absorption` feature value.
  - Current YAML is `feature`.
- Status: ACTIVE

---

## 5. Aurora L3 live scoring

### strategies.aurora.decision.scoring_version
- Type: Pydantic enum + runtime rollout selector
- Logic Owner: DecisionConfig
- Runtime Role: selects the live Aurora kernel family.
- Actual Runtime Semantics:
  - Current YAML sets `scoring_version: "quadratic"`.
  - Linear `v2` scoring kernel has been entirely removed from the codebase.
- Status: ACTIVE

### strategies.aurora.decision.signal_weights
- Type: weighted feature config
- Actual Runtime Semantics:
  - DEPRECATED (Phase 9). Parsed for config combat, but NOT used by `QuadraticScoringKernel`.
- Status: LEGACY

### strategies.aurora.decision.feature_neutrals
- Type: centered scoring config
- Actual Runtime Semantics:
  - DEPRECATED (Phase 9). Not consumed by `QuadraticScoringKernel`.
- Status: LEGACY

### strategies.aurora.decision.direction_strength_scoring
- Type: feature split contract
- Actual Runtime Semantics:
  - DEPRECATED (Phase 9). Not consumed by `QuadraticScoringKernel`.
- Status: LEGACY

### strategies.aurora.decision.essential_features
- Type: readiness gate
- Logic Owner: AuroraScoringKernel + SignalScoreV2
- Runtime Role: fail-closed scoring precondition.
- Actual Runtime Semantics:
  - Determines if features are allowed into the `pillar_sum`.
  - Missing readiness keys produce `MISSING_READY_KEYS:...`.
- Status: ACTIVE

### strategies.aurora.decision.signal_threshold, neutral_threshold, regime_threshold_multipliers
- Type: threshold bounds
- Logic Owner: AuroraConfigLoaderMixin + QuadraticScoringKernel
- Runtime Role: Base thresholds and multipliers for entry, flip, and exit decisions.
- Actual Runtime Semantics:
  - Regime multipliers scale the base signal threshold.
  - Base values and hysteresis state machine are active in Quadratic math.
- Status: ACTIVE

### side bias
- Type: threshold penalty overlay
- Logic Owner: QuadraticScoringKernel / aurora_scoring_helpers.py
- Runtime Role: penalizes the overrepresented direction in the recent intent window.
- Status: ACTIVE

### hysteresis
- Type: behavioral state logic
- Logic Owner: QuadraticScoringKernel
- Runtime Role: separates `enter`, `hold`, `exit`, and `flip` semantics.
- Status: ACTIVE

### liquidity gate
- Type: hard pre-score gate
- Logic Owner: aurora_scoring_helpers.py
- Runtime Role: blocks Aurora scoring when liquidity readiness or liquidity_kappa is insufficient.
- Status: ACTIVE

---

## 6. Quadratic scoring path

### DecisionConfig.scoring_engine & shield cascade
- Type: typed Quadratic config container
- Logic Owner: ScoringEngineConfig + AuroraConfigLoaderMixin + shield builder
- Runtime Role: provides shield cascade config when Quadratic is active.
- Actual Runtime Semantics:
  - Required in production contexts. `NullShield` is rejected.
  - Cascade order is fixed: DangerZoneShield -> ContextShield -> MemoryShield.
- Status: ACTIVE

### QuadraticScoringKernel
- Type: Aurora L3 kernel (Phase 9)
- Logic Owner: apps/reference/domains/decision_making/quadratic_scoring_kernel.py
- Runtime Role: converts a linear conviction source (`pillar_sum`) into nonlinear exposure.
- Mathematical / Behavioral Role:
  `s_linear = linear_score argument or features["pillar_sum"]`
  `s_clamped = clamp(s_scaled_raw, -1, 1)`
  `raw_exposure = sign(s_clamped) * s_clamped^2`
  `final_score = raw_exposure * shield_multiplier`
- Status: ACTIVE

### ScoringEngineConfig.exposure_cap and min_pillar_confidence
- Type: typed config field
- Status: DECLARED BUT NOT USED

---

## 7. Post-score modulation and hard gates

### holding_period
- Type: anti-churn gate
- Logic Owner: AuroraHoldingPeriodMixin
- Runtime Role: suppresses soft exits and flips before minimum hold time elapses.
- Status: ACTIVE

### reentry_cooldown_sec
- Type: anti-ping-pong gate
- Logic Owner: AuroraHoldingPeriodMixin
- Runtime Role: blocks immediate re-entry after close.
- Status: ACTIVE

### gates (anti-flat / anti-fomo)
- Type: sigma-normalized motion gate
- Logic Owner: DecisionConfig.gates + Aurora runtime decision path
- Runtime Role: blocks entries in dead or extreme markets before final intent emission.
- Status: ACTIVE

### anchor_shock_veto
- Type: directional safety veto
- Logic Owner: DecisionConfig + AuroraDecisionMixin
- Runtime Role: blocks BUY when anchor crash condition is met (e.g. BTC plunging).
- Status: ACTIVE

### EntryPlan and Objective Engine
- Type: structural execution and modulation
- Logic Owner: domains.decision_making.entry_plan, objective_engine
- Runtime Role: computes technical Entry/SL/TP parameters, and Objective Engine applies post-score multiplier weighting.
- Status: ACTIVE

### ExecutionGate
- Type: final hard gate bundle
- Logic Owner: DecisionConfig.execution + AuroraDecisionMixin
- Runtime Role: final gate after scoring, EntryPlan, and Objective Engine.
- Status: ACTIVE

---

## 8. Mean Reversion scoring

### mean_reversion runtime ownership
- Type: strategy-specific runtime
- Logic Owner: feature_engineering/mean_reversion_strategy.py
- Runtime Role: independent L3 scoring path for symbols assigned to the MR strategy (e.g., DOGEUSDT).
- Status: ACTIVE

### mean_reversion.allowed_regimes
- Type: strict allowlist
- Logic Owner: MeanReversionHandler config resolution
- Runtime Role: fail-closed regime filter for MR signals.
- Status: ACTIVE

### mean_reversion signal formula
- Type: Bollinger/%B scoring
- Mathematical / Behavioral Role:
  - LONG when `pct_b < entry_threshold`
  - SHORT when `pct_b > 1 - entry_threshold`
  - RSI confirmation bonus applies to scaled confidence.
- Status: ACTIVE

---

## 9. Event and contract effects

### EVT:RISK_ASSESSMENT_COMPLETED
- Status: ACTIVE

### EVT:TRADE_INTENT_PROPOSED
- Status: ACTIVE

### EVT:STRATEGY_DECISION_BLOCKED
- Status: ACTIVE

### EVT:STRATEGY_SIGNAL_PRODUCED
- Status: ACTIVE

---

## 10. Legacy and drift ledger

### Linear v2 Math (`aurora_scoring_kernel.py`)
- Status: REMOVED (Deleted from codebase during Phase 9).

### DecisionConfig.scoring_version = v1 or v2
- Status: LEGACY (Aurora runs strictly on `quadratic` now).

### macro_sync
- Status: LEGACY

### decision.regime_thresholds
- Status: DECLARED BUT NOT USED

### trading.risk.daily.max_realized_loss_usd
- Status: DECLARED BUT NOT USED

---

## 11. Final verdict

Current scoring reality:

1. Aurora is fully live on **Quadratic Scoring (Phase 9)** with an active Shield Cascade (DangerZone, Context, Memory shields). Linear v2 has been removed entirely.
2. L2 risk scoring operates heavily on feature-level absorption penalties.
3. L1 daily gate code exists, but realized loss limits (`max_realized_loss_usd`) remain declared-but-unused in logic.
4. Mean Reversion and MD AMR control their own distinct scoring algorithms for assets explicitly assigned to them in `strategies.yaml`.

**Status**: Verified against current code/config. Legacy definitions updated.
