# MD_AMR / MEAN_REVERSION IMPACT UNDER QUADRATIC ROLLOUT

Scope audited:

- mean_reversion_handler
- mean_reversion_strategy
- md_amr_handler
- regime_mapping
- CMD:PROCESS_STRATEGY trigger path
- FE warmup trigger conditions
- shared execution/risk/liquidity gates
- symbol assignments
- startup/bootstrap and hydration surfaces

## 1. Direct dependencies

Direct Quadratic impact: NO for both mean_reversion and md_amr.

Mean Reversion proof:

- MeanReversionHandler imports MeanReversion1mStrategy and regime_mapping only; there is no AuroraScoringKernel, QuadraticScoringKernel, SignalScoreV2, or Aurora decision import in its runtime path. Evidence: apps/reference/domains/decision_making/mean_reversion_handler.py line 30, apps/reference/domains/decision_making/mean_reversion_handler.py line 720, apps/reference/domains/decision_making/mean_reversion_handler.py line 859.
- MeanReversion1mStrategy computes Bollinger Bands, ATR, RSI, then maps regime through map_to_flat_regime; its signal path is local math, not shared Aurora scoring. Evidence: apps/reference/domains/feature_engineering/mean_reversion_strategy.py line 218, apps/reference/domains/feature_engineering/mean_reversion_strategy.py line 302, apps/reference/domains/feature_engineering/mean_reversion_strategy.py line 345, apps/reference/domains/feature_engineering/mean_reversion_strategy.py line 383, apps/reference/domains/feature_engineering/mean_reversion_strategy.py line 394.

MD-AMR proof:

- MDAMRHandler imports MDAMRStrategyV11 and MDAMRSignal only; it does not import the Aurora or Quadratic kernels. Evidence: apps/reference/domains/decision_making/md_amr_handler.py line 20, apps/reference/domains/decision_making/md_amr_handler.py line 443.
- MDAMRStrategyV11 is a standalone channel/ATR/dir-score engine. Its readiness path is local defer logic on channel_state, ATR, ATR statistics, and directional history; there is no Quadratic kernel call. Evidence: apps/reference/domains/feature_engineering/md_amr_strategy.py line 45, apps/reference/domains/feature_engineering/md_amr_strategy.py line 199, apps/reference/domains/feature_engineering/md_amr_strategy.py line 213, apps/reference/domains/feature_engineering/md_amr_strategy.py line 220, apps/reference/domains/feature_engineering/md_amr_strategy.py line 231.

Conclusion:

- Mean Reversion does not directly use Quadratic scoring.
- MD-AMR does not directly use Quadratic scoring.
- Any rollout impact is therefore indirect, through shared contracts and shared bootstrap surfaces.

## 2. Indirect dependencies

Indirect Quadratic impact: YES, through shared upstream and downstream contracts.

- Both MR variants are downstream of CMD:PROCESS_STRATEGY, which is emitted by FeatureEngineering only after bar construction and warmup gating. Evidence: apps/reference/dictionaries/verb_registry_v1.yaml entry for CMD:PROCESS_STRATEGY owner=strategies, apps/reference/domains/feature_engineering/feature_engineering.py line 1496, apps/reference/domains/feature_engineering/feature_engineering.py line 1545, apps/reference/domains/feature_engineering/feature_engineering.py line 1659, apps/reference/domains/feature_engineering/schemas/cmd_process_strategy_v1.json.
- FeatureEngineering computes warmup.full_ready from the global readiness registry and emits or blocks CMD accordingly. There is no live config evidence of a lighter MR-specific override in config/aurora/domains.yaml. Evidence: config/aurora/domains.yaml line 202, config/aurora/domains.yaml line 222, config/aurora/domains.yaml line 224, apps/reference/domains/feature_engineering/types.py line 531.
- The override mechanism exists in code and tests, but is not present in live config. This means DOGEUSDT, XRPUSDT, and BNBUSDT currently inherit the global FE readiness universe unless rollout adds explicit symbol-specific contracts. Evidence: apps/reference/domains/feature_engineering/types.py line 531, tests/domains/feature_engineering/test_warmup_requirements_required_keys.py line 38, tests/domains/feature_engineering/test_warmup_requirements_required_keys.py line 73, tests/domains/feature_engineering/test_warmup_requirements_required_keys.py line 86.
- StrategyGateway requires readiness.warmup_ok on strategy signals before trade intent emission. Both mean_reversion and md_amr emit readiness.warmup_ok=true once they decide to signal, so their real sensitivity is mostly upstream at FE emit time and then again at shared DM warmup gates. Evidence: apps/reference/domains/decision_making/mean_reversion_handler.py line 520, apps/reference/domains/decision_making/md_amr_handler.py line 1172, apps/reference/domains/decision_making/strategy_gateway.py line 285, apps/reference/domains/decision_making/strategy_gateway.py line 294, apps/reference/domains/decision_making/strategy_gateway.py line 649.
- MD-AMR is more deeply coupled than legacy mean_reversion because it also depends on Objective Engine fail-closed behavior, regime timestamps/confidence, exposure summary, and portfolio state. Evidence: apps/reference/domains/decision_making/md_amr_handler.py line 894, apps/reference/domains/decision_making/md_amr_handler.py line 1079, apps/reference/domains/decision_making/md_amr_handler.py line 1154.

Conclusion:

- Quadratic rollout can affect MR without any direct scoring import.
- The main coupling points are FE warmup.full_ready, CMD:PROCESS_STRATEGY availability, shared DM readiness/risk gates, and startup hydration policy.

## 3. Warmup needs

Mean Reversion:

- Live assignment is DOGEUSDT only. Evidence: config/aurora/strategies.yaml line 31, config/aurora/strategies.yaml line 32.
- Runtime timeframe is 300 seconds. Evidence: config/aurora/strategies/mean_reversion.yaml line 22.
- The strategy self-warms on completed bars and needs at least min_bars=25 before any non-neutral decision path is possible; BB 20 and ATR 14 are both covered inside that minimum. Evidence: config/aurora/strategies/mean_reversion.yaml strategy.min_bars, apps/reference/domains/feature_engineering/mean_reversion_strategy.py line 329, apps/reference/domains/feature_engineering/mean_reversion_strategy.py line 383, apps/reference/domains/feature_engineering/mean_reversion_strategy.py line 394.
- There is no startup candle hydration in MeanReversionHandler; it relies on natural CMD bar flow. Evidence: apps/reference/domains/decision_making/mean_reversion_handler.py line 720 onward and no hydrate/hydration path in that file.
- Therefore legacy mean_reversion needs 25 x 5m bars, about 125 minutes, for immediate post-start readiness if no historical seed exists.

MD-AMR:

- Live assignments are XRPUSDT and BNBUSDT. Evidence: config/aurora/strategies.yaml line 34, config/aurora/strategies.yaml line 35, config/aurora/strategies.yaml line 41, config/aurora/strategies.yaml line 42.
- Runtime timeframe is 900 seconds. Evidence: config/aurora/strategies/md_amr.yaml line 5.
- MD-AMR explicitly performs REST startup hydration with a limit of 100 candles per symbol and then enforces a mandatory 2-hour live warmup window. Evidence: apps/reference/domains/decision_making/md_amr_handler.py line 59, apps/reference/domains/decision_making/md_amr_handler.py line 60, apps/reference/domains/decision_making/md_amr_handler.py line 274, apps/reference/domains/decision_making/md_amr_handler.py line 332.
- Its internal math requires: channel_window_bars=12, ATR window=14, ATR stats window=64, and directional history len(closes) >= 96. The dominant requirement is 96 bars of 15m data, about 24 hours. Evidence: config/aurora/strategies/md_amr.yaml line 5, apps/reference/domains/feature_engineering/md_amr_strategy.py line 102, apps/reference/domains/feature_engineering/md_amr_strategy.py line 199, apps/reference/domains/feature_engineering/md_amr_strategy.py line 213, apps/reference/domains/feature_engineering/md_amr_strategy.py line 220.
- The current 100-bar hydration budget is sufficient for the md_amr local strategy warmup, if the fetch succeeds. Evidence: apps/reference/domains/decision_making/md_amr_handler.py line 59, apps/reference/domains/feature_engineering/md_amr_strategy.py line 102.

Conclusion:

- Yes, MR needs startup candle hydration if the goal is immediate readiness after restart.
- Legacy mean_reversion needs 5m bars, minimum 25 bars.
- MD-AMR needs 15m bars, effectively 96 bars for full local readiness; current code already tries to hydrate 100.

## 4. Shared readiness risks

- FeatureEngineering blocks CMD:PROCESS_STRATEGY when warmup is missing or warmup.full_ready is false under fail_fast mode. That gate is global and not strategy-aware. Evidence: apps/reference/domains/feature_engineering/feature_engineering.py line 1529, apps/reference/domains/feature_engineering/feature_engineering.py line 1545, config/aurora/domains.yaml line 224.
- Because config/aurora/domains.yaml defines one global readiness_registry and one global warmup.enforcement_mode, a Quadratic rollout that adds new required readiness keys to the global FE contract can block MR symbols before their handlers run. Evidence: config/aurora/domains.yaml line 202, config/aurora/domains.yaml line 222, apps/reference/domains/feature_engineering/types.py line 531.
- Legacy mean_reversion handler does not consume warmup in its own decision logic; it merely documents it in the payload contract. So FE emit-gating is the real readiness choke point for mean_reversion. Evidence: apps/reference/domains/decision_making/mean_reversion_handler.py line 733, apps/reference/domains/decision_making/mean_reversion_handler.py line 859.
- MD-AMR has three separate readiness layers: local strategy defer, mandatory live warmup timer, and FE warmup.full_ready. This makes it especially vulnerable to accidental double-gating in a unified startup design. Evidence: apps/reference/domains/decision_making/md_amr_handler.py line 332, apps/reference/domains/decision_making/md_amr_handler.py line 878, apps/reference/domains/decision_making/md_amr_handler.py line 894, apps/reference/domains/feature_engineering/md_amr_strategy.py line 192, apps/reference/domains/feature_engineering/md_amr_strategy.py line 220.
- The repo already carries evidence that symbol-specific readiness overrides are intended for MR-like cases, but live config does not currently use them. Evidence: tests/domains/feature_engineering/test_warmup_requirements_required_keys.py line 37, tests/domains/feature_engineering/test_warmup_requirements_required_keys.py line 52, tests/domains/feature_engineering/test_warmup_requirements_required_keys.py line 86.

Answer to question 6:

- Yes. MR depends on FE warmup/full_ready and CMD:PROCESS_STRATEGY.
- Legacy mean_reversion depends on them indirectly through FE emission.
- MD-AMR depends on them directly and also layers its own readiness on top.

Answer to question 7:

- Yes. A new Quadratic readiness key added to the global FE full_ready contract could block MR even when MR local math is ready, because FE would stop emitting CMD:PROCESS_STRATEGY before MR handlers see the bar.

## 5. Shared regime risks

- Both MR paths depend on the current global regime. MeanReversionHandler caches EVT:REGIME_DETECTED and also consumes the regime snapshot injected into CMD:PROCESS_STRATEGY. Evidence: apps/reference/domains/decision_making/mean_reversion_handler.py register/on_regime_detected/_on_process_strategy, apps/reference/domains/feature_engineering/feature_engineering.py line 1656.
- Legacy mean_reversion is tightly bound to regime_mapping semantics: TREND_UP and TREND_DOWN map to None, HIGH_VOLATILITY maps to None, LOW_VOLATILITY maps to FLAT_LOW, MEAN_REVERSION maps to ATR-based FLAT_LOW/FLAT_NORMAL/FLAT_HIGH, and UNCERTAIN maps to None. Evidence: apps/reference/domains/feature_engineering/regime_mapping.py line 77, apps/reference/domains/feature_engineering/regime_mapping.py line 109, apps/reference/domains/feature_engineering/regime_mapping.py line 113, apps/reference/domains/feature_engineering/regime_mapping.py line 117, apps/reference/domains/feature_engineering/regime_mapping.py line 121, apps/reference/domains/feature_engineering/regime_mapping.py line 130.
- That means any Quadratic rollout that changes regime semantics or label vocabulary can change legacy MR behavior even without touching MR code. If MEAN_REVERSION or LOW_VOLATILITY disappear or change meaning, legacy MR entry filtering changes immediately. Evidence: apps/reference/domains/feature_engineering/mean_reversion_strategy.py line 345, apps/reference/domains/feature_engineering/mean_reversion_strategy.py line 350.
- Legacy mean_reversion allowed_regimes are checked against flat_regime.name, not against the raw global regime label. Therefore config entries like MEAN_REVERSION inside mean_reversion.allowed_regimes are effectively documentary unless the mapped flat regime name is also allowed. Evidence: config/aurora/strategies/mean_reversion.yaml line 25, apps/reference/domains/feature_engineering/mean_reversion_strategy.py line 359.
- MD-AMR uses a different regime contract. It normalizes aliases and expands compatibility pairs such as FLAT_NORMAL <-> MEAN_REVERSION, FLAT_LOW <-> LOW_VOLATILITY, FLAT_HIGH <-> HIGH_VOLATILITY before applying RegimeAllowlistContract.is_regime_allowed. Evidence: apps/reference/domains/decision_making/md_amr_handler.py line 70, apps/reference/domains/decision_making/md_amr_handler.py line 211, apps/reference/domains/decision_making/md_amr_handler.py line 552.
- Therefore regime-semantic changes will affect the two MR implementations differently: legacy mean_reversion relies on flat remapping, while md_amr relies on alias expansion plus explicit allowlist. Evidence: apps/reference/domains/feature_engineering/regime_mapping.py line 77, apps/reference/domains/decision_making/md_amr_handler.py line 70.

Answer to questions 3 and 4:

- Yes, MR is dependent on the current global regime.
- Changes to regime semantics will alter legacy mean_reversion through map_to_flat_regime, and alter md_amr through alias expansion and allowlist matching.
- Flat mapping is a hard dependency for legacy mean_reversion; allowlist compatibility mapping is a hard dependency for md_amr.

## 6. Execution/risk coupling

- After a strategy emits EVT:STRATEGY_SIGNAL_PRODUCED, StrategyGateway applies shared readiness, arbitration, risk, exposure, TTL, and warmup gates before TRADE_INTENT_PROPOSED. Evidence: apps/reference/domains/decision_making/strategy_gateway.py line 285, apps/reference/domains/decision_making/strategy_gateway.py line 316, apps/reference/domains/decision_making/strategy_gateway.py line 649.
- QoS is strategy-scoped and currently applies to aurora and md_amr, not to legacy mean_reversion. This is already a meaningful isolation boundary and should not be lost in rollout refactors. Evidence: config/aurora/domains.yaml line 45.
- Legacy mean_reversion has its own local liquidity gate on liquidity_kappa and fails closed if the feature is missing while the gate is enabled. Evidence: apps/reference/domains/decision_making/mean_reversion_handler.py line 706.
- MD-AMR is more coupled to shared execution and risk systems than legacy mean_reversion: objective engine, position queries, exposure summary, portfolio state, concentration guard, GTX retry/fallback, and regime allowlist all sit in its handler path. Evidence: apps/reference/domains/decision_making/md_amr_handler.py line 443, apps/reference/domains/decision_making/md_amr_handler.py line 552, apps/reference/domains/decision_making/md_amr_handler.py line 1079, apps/reference/domains/decision_making/md_amr_handler.py line 1154.

Conclusion:

- Shared execution/risk coupling is real for both strategies after signal emission.
- md_amr is materially more coupled than legacy mean_reversion.

## 7. Regression risks if Quadratic becomes active

- Risk 1: global FE readiness expansion. If Quadratic rollout adds pillar or Quadratic-only keys to the global readiness registry and required-ready set, MR symbols may stop receiving CMD:PROCESS_STRATEGY. Evidence: config/aurora/domains.yaml line 202, apps/reference/domains/feature_engineering/types.py line 531.
- Risk 2: startup bootstrap unification. The current repo has no confirmed shared startup caller for EVT:HTF_BARS_IMPORTED or pillar backfill, while FE is ready to consume that event. If rollout introduces a single startup planner optimized for Aurora pillars, it can accidentally become the new global readiness choke point. Evidence: apps/reference/domains/feature_engineering/feature_engineering.py line 222, apps/reference/domains/feature_engineering/feature_engineering.py line 727, apps/reference/domains/feature_engineering/pillar_backfill.py, docs/audits/current_warmup_quadratic_scoring_decision_lifecycle_audit_2026-03-10.md section 9.1-14.
- Risk 3: regime semantics drift. Legacy mean_reversion and md_amr interpret regime labels differently; a rollout that renames or repurposes labels can break only one side and create asymmetric regressions. Evidence: apps/reference/domains/feature_engineering/regime_mapping.py line 77, apps/reference/domains/decision_making/md_amr_handler.py line 70.
- Risk 4: reintroduction of non-strategy-aware shared gates. The repo already has unit tests documenting a past failure mode where Aurora regime gates blocked MR-only symbols because the symbol existed in aurora.assets. Evidence: tests/unit/test_strategy_aware_gates.py line 9, tests/unit/test_strategy_aware_gates.py line 10, tests/unit/test_strategy_aware_gates.py line 192, tests/unit/test_strategy_aware_gates.py line 199.
- Risk 5: md_amr already has local hydration and mandatory warmup. A unified Quadratic startup design that ignores those local contracts can either duplicate the warmup window or mark md_amr ready too early or too late. Evidence: apps/reference/domains/decision_making/md_amr_handler.py line 59, apps/reference/domains/decision_making/md_amr_handler.py line 60, apps/reference/domains/decision_making/md_amr_handler.py line 332, apps/reference/domains/decision_making/md_amr_handler.py line 878.

## 8. Must-protect contracts for MR

- Protect contract 1: CMD:PROCESS_STRATEGY must remain available to MR symbols on their own readiness basis, not on Quadratic-only readiness. Evidence: apps/reference/domains/feature_engineering/schemas/cmd_process_strategy_v1.json, apps/reference/domains/feature_engineering/feature_engineering.py line 1659.
- Protect contract 2: FE warmup.full_ready must support strategy- or symbol-specific required-ready keys. The mechanism already exists in compute_warmup_full_ready_for_symbol and should be used rather than expanding one global gate for everyone. Evidence: apps/reference/domains/feature_engineering/types.py line 531, tests/domains/feature_engineering/test_warmup_requirements_required_keys.py line 38.
- Protect contract 3: legacy mean_reversion must keep its own regime_mapping semantics unless intentionally migrated; it should not inherit Quadratic regime assumptions by side effect. Evidence: apps/reference/domains/feature_engineering/regime_mapping.py line 77.
- Protect contract 4: md_amr must retain its own startup hydration and local mandatory warmup semantics even if a shared bootstrap coordinator is introduced. Evidence: apps/reference/domains/decision_making/md_amr_handler.py line 274, apps/reference/domains/decision_making/md_amr_handler.py line 332.
- Protect contract 5: shared gates must remain strategy-aware. The existing unit tests show why this matters for MR-only symbols. Evidence: tests/unit/test_strategy_aware_gates.py line 192, tests/unit/test_strategy_aware_gates.py line 199.

Answer to question 8:

- Yes. MR should remain on a separate readiness contract from Aurora Quadratic.
- Shared transport and execution plumbing can remain common, but readiness and startup sufficiency must be strategy-specific.

## 9. Recommendation: keep isolated / partially integrate / fully integrate

Recommendation: partially integrate.

- Do not fully integrate MR into Aurora Quadratic readiness. That would create unnecessary regressions because MR does not use the Quadratic kernel directly. Evidence: apps/reference/domains/decision_making/mean_reversion_handler.py line 30, apps/reference/domains/decision_making/md_amr_handler.py line 20.
- Do share the startup orchestration layer, but only as a coordinator that knows multiple readiness contracts:
  - aurora/quadratic contract
  - legacy mean_reversion contract
  - md_amr contract
- For legacy mean_reversion, immediate-start bootstrap should seed 5m bars up to at least 25 bars if startup immediacy is required.
- For md_amr, shared bootstrap should preserve or replace its current 100-bar 15m hydration without removing the local contract.
- For FE, rollout must explicitly avoid making Quadratic pillar readiness a global prerequisite for DOGEUSDT mean_reversion, XRPUSDT md_amr, and BNBUSDT md_amr unless the config declares that intent through required_ready_keys_by_symbol. Evidence: config/aurora/strategies.yaml line 31, config/aurora/strategies.yaml line 34, config/aurora/strategies.yaml line 41, apps/reference/domains/feature_engineering/types.py line 531.

Answer to question 9:

Changes required so Quadratic rollout does not regress MR:

- Keep FE full_ready strategy-aware or symbol-aware.
- Do not add Quadratic-only readiness keys to the global MR path by default.
- Preserve strategy-aware shared gates.
- Preserve md_amr local hydration semantics.
- Explicitly model mean_reversion 5m seed needs and md_amr 15m seed needs in bootstrap.

## 10. Final verdict: must include MR in rollout design? YES/NO and why

YES.

Why:

- Not because MR consumes Quadratic scoring directly. It does not.
- Because MR shares the same upstream trigger path, the same FE warmup/full_ready contract, the same global regime source, and the same downstream DecisionMaking gateway family.
- Because md_amr already has an explicit startup hydration contract that a new unified bootstrap can easily break if it is designed only around Aurora/Quadratic needs.
- Because the repo already contains evidence of past regressions where shared gates bled across strategy boundaries and blocked MR-only symbols.

Bottom line:

- Direct Quadratic impact on MR: NO.
- Indirect rollout impact on MR through shared contracts: YES.
- Rollout design must explicitly include MR requirements, or Quadratic activation can regress MR even while MR code itself remains unchanged.
