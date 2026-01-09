# TASK TEST-TRIAGE-02: Full Test Failure Analysis

## Summary
- **Total Tests**: 1913 passed, 59 skipped, **25 failed**
- **Top Duration**: 24.02s (fsm delegation test)

## Failure Classification

### L (Legacy Tests) - 1 test
Tests that are obsolete due to intentional config/architecture changes:
- `test_task47_loader_effective_values_from_ssot`: Expects BTCUSDT to have both aurora+mean_reversion strategies, but config was updated to aurora-only to prevent conflicts (see config/aurora/strategies.yaml comment).

### R (Real Bugs) - 16 tests  
Actual bugs in code that need fixing:

#### Signal Weight Configuration Issues (5 tests)
Config has 9 metrics but expects 8, weights sum to 0.7 instead of 1.0 due to added macro_resid:
- `test_signal_weights_from_config_has_8_metrics`
- `test_signal_score_all_metrics_high` 
- `test_psi_vector_weights_completeness`
- `test_legacy_vs_new_metrics_composition`
- `test_signal_score_composition_formula`

#### P0 Policy Violations (2 tests)
Code uses forbidden fallback patterns (getattr with defaults):
- `test_no_forbidden_fallback_patterns[apps/reference/domains/decision_making/decision_making.py]`
- `test_p1_ast_decision_making`

#### Feature Engineering Issues (2 tests)
Events not emitted correctly, possibly due to feature_store removal:
- `test_bad_dt_drops_tick_no_state_update`
- `test_missing_bid_ask_sets_spread_not_ready`

#### Risk Management Config (1 test)
- `test_risk_management_contract_missing_weights`: ConfigContractError for missing daily.enabled

#### Other Config Issues (6 tests)
- `test_task47_btc_dual_strategy_can_emit_intents_in_different_windows`
- `test_log_bar_creation`: Unexpected bar logging
- `test_log_signal_generation`: Unexpected signal logging  
- `test_no_config_to_dict_in_domains`: config.to_dict() usage in neocortex config.py

### T (Test Bugs) - 8 tests
Tests with incorrect mocks/setup that need fixing:

#### Mean Reversion Signal Mocking Issues (8 tests)
Tests use SimpleNamespace for signals but code expects MRSignal with .bar attribute:
- `test_emits_strategy_signal_with_schema_version`
- `test_out_of_order_tick_does_not_emit_signal`
- `test_mean_reversion_logs_signal_with_indicators`
- `test_mean_reversion_e2e_tick_to_intent_chain`
- `test_mean_reversion_e2e_chain_with_real_margin_first_sizing_multi_symbol[case0-5]`

## Recommended Actions

### Immediate (P0)
1. Fix signal weight config to include macro_resid in expected keys and adjust weights to sum to 1.0
2. Remove forbidden getattr fallbacks in decision_making.py
3. Fix risk management config missing daily.enabled

### High Priority (Fix Tests)
4. Update mean reversion tests to use MRSignal objects instead of SimpleNamespace for mocks
5. Investigate feature engineering event emission issues

### Medium Priority (Legacy Quarantine)
6. Mark `test_task47_loader_effective_values_from_ssot` as legacy with @pytest.mark.legacy

### Low Priority (Investigate)
7. Review other config-related failures for intentional vs bug status</content>
<parameter name="filePath">/home/wekabeka/Музыка/Phenix/reports/test_triage_report.md