# Documentation Forensics Audit Report: Scoring Passport

**Date:** 2026-03-13
**Target Document:** config/docs/scoring_passport.md
**Auditor:** Principal Code Auditor / Documentation Forensics Engineer

## 1. Scope

This audit re-traced scoring from configuration to emitted decision effects for exactly one document: config/docs/scoring_passport.md.

The trace covered:

1. L1 portfolio gate.
2. L2 risk score.
3. Aurora L3 live scoring.
4. Quadratic / rollout / shield wiring.
5. Mean Reversion scoring.
6. Event / contract outputs touched by scoring state.

## 2. Files traced

### YAML
- config/aurora/trading.yaml
- config/aurora/domains.yaml
- config/aurora/strategies.yaml
- config/aurora/strategies/aurora.yaml
- config/aurora/strategies/mean_reversion.yaml

### Pydantic / config contracts
- apps/reference/config_models.py
- apps/reference/contracts/quadratic_rollout.py

### Runtime consumers
- apps/reference/domains/risk_management/daily_gate.py
- apps/reference/domains/risk_management/risk_management.py
- apps/reference/domains/decision_making/aurora_config_loader.py
- apps/reference/domains/decision_making/aurora_scoring_kernel.py
- apps/reference/domains/decision_making/quadratic_scoring_kernel.py
- apps/reference/domains/decision_making/aurora_scoring_helpers.py
- apps/reference/domains/decision_making/aurora_holding_period.py
- apps/reference/domains/decision_making/aurora_decision.py
- apps/reference/domains/decision_making/scoring_direction_strength_v1.py
- apps/reference/domains/objective_engine/pretrade_kernel.py
- apps/reference/domains/feature_engineering/mean_reversion_strategy.py
- apps/reference/domains/decision_making/mean_reversion_handler.py

### Schemas / contract tests
- apps/reference/domains/risk_management/schemas/risk_assessment_v1.json
- apps/reference/domains/decision_making/schemas/trade_intent_v1.json
- apps/reference/domains/decision_making/schemas/str_decision_blocked_v1.json
- tests/contracts/test_quadratic_rollout_contract.py
- tests/contracts/test_strategy_signal_produced_schema_additive.py
- tests/domains/decision_making/test_aurora_scoring_kernel.py
- tests/domains/decision_making/test_normalize_mode_ssot.py
- tests/test_quadratic_scoring_kernel.py
- tests/test_shield_system.py
- tests/integration/test_depth_imbalance_signal_contract.py

## 3. Critical runtime consumers

1. DailyRiskState.can_open()
2. RiskManagement._calculate_risk_parameters()
3. AuroraScoringKernel.compute()
4. QuadraticScoringKernel.compute()
5. AuroraDecisionMixin._process_decision()
6. AuroraDecisionMixin._emit_signal()
7. MeanReversion1mStrategy.on_bar()
8. MeanReversionHandler._on_process_strategy()
9. evaluate_pretrade_objective()

## 4. Confirmed claims

1. Aurora live scoring is fail-closed on essential feature readiness.
2. Aurora uses direction/strength split scoring for the live `v2` path.
3. Side-bias and hysteresis are active runtime behaviors, not doc-only ideas.
4. L2 risk score is clamped to `[0, 1]` and exposed in risk assessment output.
5. Mean Reversion runtime is Bollinger / `%B` driven and uses strict regime allowlists.
6. Objective Engine is genuinely wired into Aurora and MR scoring pipelines.
7. Aurora liquidity gate is real and fail-closed on missing `liquidity_kappa` readiness/data.
8. Holding period and re-entry cooldown are real runtime suppressors.
9. Quadratic rollout and shadow-evaluation contracts exist and are test-covered.
10. Strategy block surface is schema-backed via `EVT:STRATEGY_DECISION_BLOCKED`.
11. Trade intent payload carries scoring-adjacent fields like strategy, regime, and risk context.
12. Current MR registry ownership is not shared with Aurora on DOGEUSDT.

## 5. Corrected claims

1. Old passport overstated Quadratic as active live scoring. Current YAML keeps Aurora on `v2`.
2. Old passport described `aurora.assets` as the symbol router. Actual ownership comes from config/aurora/strategies.yaml.
3. Old passport mixed global `decision.regime_thresholds` with the runtime-consumed threshold map. Aurora kernels use global `regime_threshold_multipliers` and per-symbol `assets.<SYM>.regime_thresholds`.
4. Old passport treated Objective Engine as unconditional. It is conditional and fail-closed on explicit preconditions.
5. Old passport implied shield cascade as current live behavior. It is only live when Quadratic and shield config are explicitly activated.
6. Old passport did not reflect that `scoring_version=v1` is effectively coerced to `v2` by rollout logic.
7. Old passport did not separate L2 active `feature` absorption routing from supported-but-inactive proxy routing.
8. Old passport used stale MR examples for BTC/XRP/SOL as if they were active MR runtime owners.
9. Old passport did not capture that L1 daily gate is disabled in current YAML.
10. Old passport treated `max_realized_loss_usd` as part of active L1 open gating; no such runtime consumer was found.
11. Old passport did not document that production Aurora normalization is locked to `signed_v2`.
12. Old passport described shield/Quadratic math more broadly than the current YAML actually wires.
13. Old passport omitted the additive event surface for rollout/objective traces.

## 6. Removed stale claims

1. Quadratic as current Aurora production default.
2. Strategy routing via `aurora.assets`.
3. Global `decision.regime_thresholds` as the active Aurora threshold source.
4. `macro_sync` as an active weighted L3 signal driver.
5. BTC/XRP/SOL as active Mean Reversion scoring examples.
6. `max_realized_loss_usd` as an implemented L1 open-gate limiter.

## 7. Added missing sections

1. Strategy ownership and symbol assignment boundary.
2. Honest L1 state: code exists, current YAML disables it.
3. Real `signed_v2` transformation semantics.
4. Objective Engine formula and fail-closed seam.
5. Liquidity gate semantics including readiness requirements.
6. Holding period and re-entry cooldown runtime behavior.
7. Quadratic rollout state and startup/operator visibility.
8. Declared-but-unused config ledger.
9. Event / schema effects for risk, intent, and blocked decisions.
10. Mean Reversion runtime formula rather than config-only tables.

## 8. Dead / legacy / declared-but-unused fields

1. `DecisionConfig.scoring_version = v1` is legacy in practice; rollout coerces it to `v2`.
2. `strategies.aurora.decision.regime_thresholds` is declared but not used by Aurora kernels.
3. `ScoringEngineConfig.exposure_cap` is declared but not used in current Aurora runtime.
4. `ScoringEngineConfig.min_pillar_confidence` is declared but not used in current Aurora runtime.
5. `LiquidityGateConfig.failsafe_qty_check` is diagnostic only; qty enforcement was not found.
6. `trading.risk.daily.max_realized_loss_usd` is configured but not used in `DailyRiskState.can_open()`.
7. `macro_sync` remains compatibility/telemetry-only for Aurora L3 scoring because effective live weight is `0.0`.

## 9. Open questions

No open questions remain for the current passport sync. The remaining issues are runtime cleanup tasks, not evidence gaps.

## 10. Final verdict

The passport is now synchronized to the current code/config state.

The main correction is directional and important: the repository contains a substantial Quadratic / shield / rollout implementation, but the active Aurora live config is still linear `v2`. The previous passport collapsed “implemented in code” and “active in runtime” into one narrative. That drift has been removed.

**Status: DONE**
