# ALPHA_SEARCH_NEW_LOGS_AND_SCENARIO_HEALTH_AUDIT_V1

## Scope

- Selected newest timestamped runtime session: logs/alpha_search_runtime/20260517_171326
- Previous timestamped runtime session: logs/alpha_search_runtime/20260516_212203
- Runtime matrix_id observed: v6b_dedup_noflip_cooldown_20260307
- Registry file present: True

## Facts

- The newest timestamped alpha_search runtime session is logs/alpha_search_runtime/20260517_171326, starting at 2026-05-17 17:13:26.445000 and last logging at 2026-05-18 01:14:04.505000.
- The newest runtime session loaded 12 workers and created 12 scenario directories.
- The newest runtime session used matrix_id=v6b_dedup_noflip_cooldown_20260307, which matches scenario_matrix.yaml and not scenario_registry_v2.yaml.
- scenario_registry_v2.yaml contains 30 registered scenarios.
- scenario_matrix.yaml contains 12 configured scenarios, and the newest runtime loaded/evaluated 12/12 of that path.
- aggregate_metrics.csv for the newest session contains 384504 result rows across 14071 unique input snapshots.
- TA event-plane extractable rows in logs/alpha_input/alpha_input_v1.jsonl: 0 of 30521.
- Boundary scan found alpha_search real ORDER_INTENT=0, CMD:OPEN=0, CMD:CLOSE=0, ORDER_PLACED=0, exchange-order evidence=0.

## Inferences

- The expanded 25+/30-scenario registry exists on disk but is not the runtime path used by the newest session.
- The runtime remains on the old 12-scenario path, so new registry scenarios are not active in practice.
- TA-driven providers remain fail-closed because the newest alpha_input stream still does not yield a synthetic EVT:TA_FEATURES_CALCULATED plane.
- Signal materialization exists, but it is partial because evaluation rows are produced while major ta_ensemble branches stay neutral/fail-closed.
- The shadow authority boundary remains preserved because no alpha_search-originated execution-path artifacts were found in order/trade/WAL logs.

## Verdict Codes

- NEW_ALPHA_LOGS_HEALTHY
- ONLY_OLD_12_SCENARIOS_ACTIVE
- TA_FEATURE_FEED_STILL_MISSING
- SIGNAL_MATERIALIZATION_PARTIAL
- SCENARIO_DIVERSITY_COLLAPSED
- SHADOW_AUTHORITY_BOUNDARY_PRESERVED
- PARTIAL

## Questions

1. What is the newest alpha_search session? logs/alpha_search_runtime/20260517_171326
2. How many scenarios are registered? 30
3. How many scenarios are loaded? 12
4. How many scenarios are evaluated? 12
5. Are the new scenarios actually active? No; newest runtime still used scenario_matrix.yaml old 12-scenario path
6. Which scenarios produce BUY/SELL? S03_AURORA_15M_APPROX, S05_AURORA_MACRO_RESIDUAL, S06_AURORA_ETH_CALIBRATED, S20_AURORA_MICROSTRUCTURE_DEPTH
7. Which scenarios are still neutral and why? S01_MR_RSI_HEAVY/aurora: aurora_dir=0.0000; S01_MR_RSI_HEAVY/ta_ensemble: fail_closed:ta_features_missing_for_bar; S03_AURORA_15M_APPROX/ta_ensemble: fail_closed:ta_features_missing_for_bar; S05_AURORA_MACRO_RESIDUAL/ta_ensemble: fail_closed:ta_features_missing_for_bar; S06_AURORA_ETH_CALIBRATED/ta_ensemble: fail_closed:ta_features_missing_for_bar; S11_MR_BASELINE/aurora: aurora_dir=0.0000; S11_MR_BASELINE/ta_ensemble: fail_closed:ta_features_missing_for_bar; S12_MR_RSI_25_75/aurora: aurora_dir=0.0000; S12_MR_RSI_25_75/ta_ensemble: fail_closed:ta_features_missing_for_bar; S13_MR_BB_HEAVY/aurora: aurora_dir=0.0000; S13_MR_BB_HEAVY/ta_ensemble: fail_closed:ta_features_missing_for_bar; S15_ENSEMBLE_BALANCED/aurora: aurora_dir=0.0000; S15_ENSEMBLE_BALANCED/ta_ensemble: fail_closed:ta_features_missing_for_bar; S18_ENSEMBLE_MOMENTUM_AGGRESSIVE/aurora: aurora_dir=0.0000; S18_ENSEMBLE_MOMENTUM_AGGRESSIVE/ta_ensemble: fail_closed:ta_features_missing_for_bar; S19_ENSEMBLE_MR_SHORT_BIAS/aurora: aurora_dir=0.0000; S19_ENSEMBLE_MR_SHORT_BIAS/ta_ensemble: fail_closed:ta_features_missing_for_bar; S20_AURORA_MICROSTRUCTURE_DEPTH/ta_ensemble: fail_closed:ta_features_missing_for_bar; S21_ENSEMBLE_REGIME_ADAPTIVE/aurora: aurora_dir=0.0000; S21_ENSEMBLE_REGIME_ADAPTIVE/ta_ensemble: fail_closed:ta_features_missing_for_bar
8. Are TA features now present? False
9. Are MR/ensemble scenarios now evaluable? False
10. Are any scenarios duplicates? See diversity audit; runtime remains compressed to 12-path and registry_v2 is not evaluable in current session
11. Does alpha_search remain strictly shadow-only? True
12. What is the next recommended simulation package? Simulation package should first force launcher to consume scenario_registry_v2.yaml and add TA event-plane coverage proof before any 25+ scenario replay package
