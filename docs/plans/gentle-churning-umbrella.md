# Alpha Search Domain — Production Test Plan

## Overview

Comprehensive test suite for the `apps/reference/domains/alpha_search/runtime/` standalone domain (19 modules). Organized in 4 tiers by criticality, plus cross-cutting integration/regression/performance layers.

**Target:** ~250 tests across 22 test files.
**Framework:** pytest (existing `pytest.ini`), markers: `@pytest.mark.unit`, `@pytest.mark.integration`, `@pytest.mark.slow`, `@pytest.mark.asyncio`
**Coverage target:** 90%+ line coverage on runtime/ modules.

---

## Infrastructure: conftest.py and pytest.ini update

### `apps/reference/domains/alpha_search/tests/conftest.py`

Shared fixtures for the entire test suite:

```python
# Key fixtures to create:
snapshot_factory(symbol, price, features, regime, ...)  -> AlphaInputV1
scenario_spec_factory(strategy_type, config_mode, ...)  -> ScenarioSpec
matrix_config_factory(scenarios, runtime, ...)           -> ScenarioMatrixConfig
runtime_config_factory(parallelism, max_workers, ...)    -> RuntimeConfig
mock_bus()                                               -> LocalBus
tmp_session_dir(tmp_path)                                -> Path
base_features_aurora()                                   -> Dict  (obi, delta_price, macro_resid, etc)
base_features_mr()                                       -> Dict  (bb_position, rsi_14, etc)
base_features_full()                                     -> Dict  (union of aurora + mr + ensemble)
yaml_config_dir(tmp_path)                                -> creates alpha_search.yaml + alpha_search_system.yaml + aurora.yaml
```

### `pytest.ini` update

Add `apps/reference/domains/alpha_search/tests` to `testpaths`.

---

## TIER 1: Critical Path (96 tests)

These tests cover the data flow that MUST work for any score to be produced.

### File 1: `test_contracts.py` (~30 tests)

Validates all Pydantic models with `extra="forbid"`. One broken schema = zero scores.

| # | Test | What it validates |
|---|------|-------------------|
| 1 | `test_alpha_input_v1_valid_minimal` | Minimal valid snapshot parses |
| 2 | `test_alpha_input_v1_valid_full` | All fields populated parses |
| 3 | `test_alpha_input_v1_extra_field_rejected` | `extra="forbid"` enforced |
| 4 | `test_alpha_input_v1_missing_required_field` | `ts_ms`, `symbol`, `bar_close_ts`, `price`, `features` required |
| 5 | `test_alpha_input_v1_price_gt_zero` | `price=0` and `price=-1` rejected |
| 6 | `test_alpha_input_v1_symbol_min_length` | Empty symbol rejected |
| 7 | `test_alpha_input_v1_tf_sec_ge_1` | `tf_sec=0` rejected |
| 8 | `test_alpha_input_v1_defaults` | `regime="DEFAULT"`, `warmup_status={}`, `tf_sec=300` |
| 9 | `test_alpha_shadow_result_v1_valid` | Valid result parses |
| 10 | `test_alpha_shadow_result_v1_score_bounds` | `score` clamped to [-1, 1] |
| 11 | `test_alpha_shadow_result_v1_confidence_bounds` | `confidence` clamped to [0, 1] |
| 12 | `test_scenario_spec_override_mode_requires_base_refs` | Validator fires |
| 13 | `test_scenario_spec_full_config_requires_config_dir` | Validator fires |
| 14 | `test_scenario_spec_valid_override` | Happy path |
| 15 | `test_scenario_spec_valid_full_config` | Happy path |
| 16 | `test_scenario_spec_invalid_strategy_type` | Literal["aurora","mean_reversion","ensemble"] enforced |
| 17 | `test_scenario_spec_invalid_config_mode` | Literal["override","full_config"] enforced |
| 18 | `test_runtime_config_defaults` | All defaults correct |
| 19 | `test_runtime_config_max_scenarios_bounds` | `max_scenarios=0` rejected, `max_scenarios=51` rejected |
| 20 | `test_runtime_config_parallelism_literal` | Only "sequential" or "thread_pool" |
| 21 | `test_hot_reload_config_defaults` | `enabled=False`, `rollback_on_error=True` |
| 22 | `test_input_config_source_mode_literal` | Only "replay" or "live_tail" |
| 23 | `test_matrix_config_valid` | Full matrix with 3 scenarios |
| 24 | `test_matrix_config_duplicate_ids_rejected` | `validate_unique_ids` fires |
| 25 | `test_matrix_config_exceeds_max_scenarios` | `validate_scenario_count` fires |
| 26 | `test_matrix_config_zero_scenarios_rejected` | `min_length=1` on scenarios |
| 27 | `test_matrix_config_mixed_strategies` | aurora + mr + ensemble mix |
| 28-30 | `test_*_roundtrip_serialize` | `model_dump() -> model_validate()` idempotent for 3 key models |

### File 2: `test_config_resolver.py` (~28 tests)

Config resolution is the next single point of failure after schema validation.

| # | Test | What it validates |
|---|------|-------------------|
| 1 | `test_override_mode_happy_path` | Base refs loaded, overrides applied, result validates |
| 2 | `test_override_mode_missing_base_ref` | `ConfigResolutionError` raised |
| 3 | `test_override_mode_disallowed_path_rejected` | Allowlist enforcement |
| 4 | `test_override_mode_yaml_unwrap_top_key` | `{"aurora": {...}}` unwrapped correctly |
| 5 | `test_override_mode_no_unwrap_flat_yaml` | Flat YAML not double-unwrapped |
| 6 | `test_full_config_mode_happy_path` | Loads all YAMLs from dir |
| 7 | `test_full_config_mode_missing_dir` | `ConfigResolutionError` raised |
| 8 | `test_full_config_mode_empty_dir` | Falls back to defaults |
| 9 | `test_dot_path_override_simple` | `a.b.c = 5` sets correctly |
| 10 | `test_dot_path_override_creates_intermediate_dicts` | `a.b.c` creates `b` if missing |
| 11 | `test_dot_path_override_path_too_short` | Single-segment path rejected |
| 12 | `test_dot_path_override_through_non_dict` | Trying to navigate through string raises error |
| 13 | `test_dot_path_override_creates_new_config_section` | New top-level key created |
| 14 | `test_build_alpha_search_config_forces_enabled_shadow` | `enabled=True`, `shadow_mode=True` always |
| 15 | `test_build_alpha_search_config_unwraps_nested_key` | Double-nested `{"alpha_search": {"alpha_search": {...}}}` handled |
| 16 | `test_build_system_config_defaults` | Empty dict -> valid defaults |
| 17 | `test_build_system_config_unwraps_nested_key` | Same unwrap pattern |
| 18 | `test_extract_strategy_config_aurora` | Returns deep copy of aurora dict |
| 19 | `test_extract_strategy_config_mr` | Returns deep copy of mean_reversion dict |
| 20 | `test_extract_strategy_config_ensemble_empty` | Returns `{}` |
| 21 | `test_persist_effective_config_writes_yaml` | File written, loadable, contains all sections |
| 22 | `test_persist_effective_config_creates_dirs` | Missing parent dirs created |
| 23 | `test_override_mode_aurora_threshold_override` | `aurora.decision.signal_threshold=0.12` applied |
| 24 | `test_override_mode_mr_rsi_override` | `mean_reversion.strategy.rsi_oversold=25` applied |
| 25 | `test_override_mode_ensemble_model_weight` | `alpha_search.providers.ta_ensemble.ensemble.models.*.weight` applied |
| 26 | `test_override_mode_partial_aurora_warns` | Threshold without neutrals -> warning logged |
| 27 | `test_override_deepcopy_no_mutation` | Overrides don't mutate base config dicts |
| 28 | `test_resolve_unknown_config_mode` | `ConfigResolutionError` for invalid mode |

### File 3: `test_override_allowlist.py` (~18 tests)

| # | Test | What it validates |
|---|------|-------------------|
| 1 | `test_aurora_allowlist_exact_match` | `aurora.decision.signal_threshold` allowed |
| 2 | `test_aurora_allowlist_wildcard_match` | `aurora.decision.signal_weights.obi` matched by `*.obi` |
| 3 | `test_aurora_allowlist_rejected_path` | `aurora.internal.secret` rejected |
| 4 | `test_mr_allowlist_exact_match` | Happy path |
| 5 | `test_mr_allowlist_per_asset_wildcard` | `mean_reversion.assets.BTCUSDT.strategy.rsi_oversold` matched |
| 6 | `test_ensemble_allowlist_model_wildcard` | Per-model enable/weight matched |
| 7 | `test_validate_overrides_empty_returns_empty` | No overrides = no rejections |
| 8 | `test_validate_overrides_unknown_strategy_rejects_all` | Unknown strategy = all rejected |
| 9 | `test_validate_overrides_mixed_allowed_rejected` | Partial match returns only rejected |
| 10 | `test_warn_partial_aurora_threshold_no_neutrals` | Warning generated |
| 11 | `test_warn_partial_aurora_weights_no_neutrals` | Warning generated |
| 12 | `test_warn_partial_aurora_all_present_no_warning` | No warning when all three present |
| 13 | `test_path_matches_pattern_exact` | `fnmatch` exact |
| 14 | `test_path_matches_pattern_wildcard_star` | `*.obi` matches `signal_weights.obi` |
| 15 | `test_path_matches_pattern_no_match` | Non-matching returns False |
| 16 | `test_strategy_allowlists_keys` | All 3 strategies present in mapping |
| 17 | `test_aurora_provider_threshold_in_allowlist` | `alpha_search.providers.aurora.threshold` allowed |
| 18 | `test_ensemble_system_model_tuning_wildcard` | `alpha_search_system.momentum.*` matched |

### File 4: `test_scenario_worker.py` (~20 tests)

Core execution unit — if this fails, zero scores.

| # | Test | What it validates |
|---|------|-------------------|
| 1 | `test_process_snapshot_produces_results` | Non-empty result list from valid snapshot |
| 2 | `test_process_snapshot_result_has_required_fields` | `scenario_id`, `score`, `side`, `provider_id`, `regime` present |
| 3 | `test_process_snapshot_enriches_with_scenario_metadata` | `scenario_id` and `strategy_type` injected |
| 4 | `test_process_snapshot_shadow_always_true` | All results have `shadow=True` |
| 5 | `test_process_snapshot_regime_passed_through` | Input regime appears in results |
| 6 | `test_self_triggering_caches_then_scores` | Verify 2-phase: feature cache + scoring |
| 7 | `test_bus_isolation_no_cross_worker` | Two workers on different buses don't share events |
| 8 | `test_inject_aurora_params_signal_weights` | `_signal_weights` overridden on adapter |
| 9 | `test_inject_aurora_params_base_threshold` | `_base_threshold` + `provider_configs` synced |
| 10 | `test_inject_aurora_params_regime_thresholds` | `_regime_thresholds` overridden |
| 11 | `test_inject_aurora_params_direction_strength` | `_direction_strength_cfg` overridden |
| 12 | `test_inject_aurora_params_no_aurora_provider` | No crash when provider missing |
| 13 | `test_determine_side_buy` | score > threshold -> BUY |
| 14 | `test_determine_side_sell` | score < -threshold -> SELL |
| 15 | `test_determine_side_neutral` | -threshold <= score <= threshold -> NEUTRAL |
| 16 | `test_get_summary_contains_stats` | Keys: `snapshots_processed`, `total_results`, etc |
| 17 | `test_process_snapshot_increments_stats` | `_snapshots_processed` incremented |
| 18 | `test_process_snapshot_error_returns_empty` | Exception in plugin -> empty list, `_snapshots_failed` incremented |
| 19 | `test_shutdown_calls_plugin_shutdown` | Plugin.shutdown() invoked |
| 20 | `test_threshold_sync_affects_side_determination` | Overridden threshold changes BUY/SELL/NEUTRAL boundary |

---

## TIER 2: Isolation & Correctness (38 tests)

### File 5: `test_scenario_manager.py` (~18 tests)

| # | Test | What it validates |
|---|------|-------------------|
| 1 | `test_initialize_all_enabled_scenarios` | 10/10 workers created for test matrix |
| 2 | `test_initialize_skips_disabled_scenarios` | `enabled=False` scenarios not initialized |
| 3 | `test_initialize_config_error_continues_others` | Bad scenario doesn't block rest |
| 4 | `test_fan_out_dispatches_to_all_workers` | All workers receive snapshot |
| 5 | `test_fan_out_error_isolation` | One worker error doesn't crash fan_out |
| 6 | `test_fan_out_writes_to_score_writers` | Per-scenario scores.jsonl populated |
| 7 | `test_fan_out_writes_to_aggregate` | Aggregate CSV populated |
| 8 | `test_get_aggregate_summary_structure` | Required keys present |
| 9 | `test_get_aggregate_summary_includes_shadow_metrics` | ShadowBook metrics merged |
| 10 | `test_shutdown_calls_all_workers` | All worker.shutdown() called |
| 11 | `test_shutdown_logs_final_summary` | Reporter.log_summary() called |
| 12 | `test_shutdown_tolerates_worker_error` | Worker shutdown error logged, not raised |
| 13 | `test_worker_count_property` | Returns len(workers) |
| 14 | `test_worker_ids_property` | Returns list of scenario IDs |
| 15 | `test_mixed_strategy_types` | Aurora + MR + Ensemble workers coexist |
| 16 | `test_per_scenario_log_dirs_created` | Each scenario gets its own directory |
| 17 | `test_effective_config_persisted` | config_effective.yaml written per scenario |
| 18 | `test_init_worker_creates_all_components` | Worker + ScoreWriter + ShadowBook created |

### File 6: `test_shadow_book.py` (~12 tests)

| # | Test | What it validates |
|---|------|-------------------|
| 1 | `test_record_trade_buy_profit` | BUY profit calculates correctly |
| 2 | `test_record_trade_buy_loss` | BUY loss calculates correctly |
| 3 | `test_record_trade_sell_profit` | SELL profit (price decrease) |
| 4 | `test_record_trade_sell_loss` | SELL loss (price increase) |
| 5 | `test_cumulative_pnl_accumulates` | Multiple trades sum correctly |
| 6 | `test_max_drawdown_calculation` | Peak -> valley tracking |
| 7 | `test_sharpe_ratio_positive` | Consistent profits -> positive Sharpe |
| 8 | `test_sharpe_ratio_zero_variance` | All same PnL -> Sharpe=0 |
| 9 | `test_sharpe_ratio_insufficient_data` | < 2 trades -> Sharpe=0 |
| 10 | `test_get_metrics_complete_keys` | All expected keys present |
| 11 | `test_win_rate_calculation` | wins/total correct |
| 12 | `test_notional_size_scales_pnl` | Different notional produces proportional PnL |

### File 7: `test_backtest_plugin_integration.py` (~8 tests)

Integration tests for `_extract_payload` fix and multi-provider scoring.

| # | Test | What it validates |
|---|------|-------------------|
| 1 | `test_extract_payload_message_object` | `hasattr(event, "pld")` path works |
| 2 | `test_extract_payload_localbus_dict` | `isinstance(event, dict) and "pld" in event` path works |
| 3 | `test_extract_payload_raw_dict` | Fallback to `event` itself |
| 4 | `test_extract_payload_non_dict_returns_none` | String/int -> None |
| 5 | `test_feature_cache_populated_via_localbus` | Emitting via LocalBus populates cache |
| 6 | `test_scoring_produces_event` | CMD:PROCESS_STRATEGY triggers EVT:ALPHA_SCORE_CALCULATED |
| 7 | `test_fail_closed_on_missing_features` | Score=0 emitted when features not cached |
| 8 | `test_multi_provider_scoring` | Both aurora and ta_ensemble produce scores |

---

## TIER 3: Runtime & Resilience (50 tests)

### File 8: `test_executor.py` (~16 tests)

| # | Test | What it validates |
|---|------|-------------------|
| 1 | `test_sequential_execution_all_workers` | All workers called and results returned |
| 2 | `test_sequential_worker_error_isolated` | One error doesn't crash others |
| 3 | `test_sequential_timeout_warning` | Slow worker logged but not killed |
| 4 | `test_parallel_execution_all_workers` | Thread pool fans out and collects |
| 5 | `test_parallel_worker_error_isolated` | Exception contained per worker |
| 6 | `test_parallel_timeout_returns_timeout_error` | `TimeoutError` in results dict |
| 7 | `test_parallel_fallback_to_sequential` | No pool -> sequential fallback |
| 8 | `test_start_creates_pool` | ThreadPoolExecutor created for thread_pool mode |
| 9 | `test_start_sequential_no_pool` | No pool created for sequential mode |
| 10 | `test_shutdown_waits_for_completion` | `pool.shutdown(wait=True)` called |
| 11 | `test_stats_counters` | `total_dispatches`, `total_timeouts`, `total_errors` correct |
| 12 | `test_execute_all_increments_dispatch_counter` | Counter incremented per call |
| 13 | `test_parallel_respects_max_workers` | Pool created with correct max_workers |
| 14 | `test_parallel_mixed_success_failure` | Some succeed, some fail, all returned |
| 15 | `test_sequential_large_batch` | 20 workers processed without error |
| 16 | `test_shutdown_idempotent` | Double shutdown doesn't crash |

### File 9: `test_backpressure.py` (~14 tests)

| # | Test | What it validates |
|---|------|-------------------|
| 1 | `test_put_get_fifo` | Items dequeued in insertion order |
| 2 | `test_drop_oldest_policy` | Full queue drops oldest on put |
| 3 | `test_drop_oldest_stats` | `total_dropped` incremented |
| 4 | `test_drop_newest_policy` | Full queue rejects new item |
| 5 | `test_drop_newest_returns_false` | put() returns False for rejected |
| 6 | `test_block_policy_no_limit` | Block mode accepts unlimited items |
| 7 | `test_get_empty_returns_none` | Empty queue returns None |
| 8 | `test_get_batch_returns_up_to_max` | Batch dequeue respects max_items |
| 9 | `test_get_batch_empty_returns_empty_list` | Empty queue -> [] |
| 10 | `test_size_property` | Reflects current queue length |
| 11 | `test_stats_counters` | `total_put`, `total_get`, `total_dropped` correct |
| 12 | `test_utilization_pct` | Percentage calculation correct |
| 13 | `test_thread_safety_concurrent_put_get` | Multiple threads doing put/get simultaneously |
| 14 | `test_maxsize_respected` | Queue never exceeds maxsize for drop_oldest |

### File 10: `test_health_monitor.py` (~12 tests)

| # | Test | What it validates |
|---|------|-------------------|
| 1 | `test_record_success_updates_heartbeat` | Last heartbeat timestamp updated |
| 2 | `test_record_success_resets_failures` | Consecutive failure counter reset to 0 |
| 3 | `test_record_success_recovers_degraded` | Degraded scenario removed from set |
| 4 | `test_record_failure_increments_counter` | Counter incremented |
| 5 | `test_degradation_after_threshold` | 3 consecutive failures -> degraded |
| 6 | `test_no_degradation_below_threshold` | 2 failures -> not degraded |
| 7 | `test_is_degraded_query` | Returns True for degraded, False for healthy |
| 8 | `test_check_health_healthy` | Recent heartbeat -> "healthy" |
| 9 | `test_check_health_stale` | Old heartbeat -> "stale" |
| 10 | `test_check_health_degraded` | Degraded scenario -> "degraded" |
| 11 | `test_check_health_unknown` | No heartbeat ever -> "unknown" |
| 12 | `test_stats_property` | All fields present and correct |

### File 11: `test_ingest_gateway.py` (~8 tests)

| # | Test | What it validates |
|---|------|-------------------|
| 1 | `test_replay_valid_jsonl` | All valid lines yielded as AlphaInputV1 |
| 2 | `test_replay_skips_invalid_json` | Malformed JSON skipped, counter incremented |
| 3 | `test_replay_skips_invalid_schema` | Valid JSON but bad schema skipped |
| 4 | `test_replay_empty_lines_skipped` | Blank lines ignored |
| 5 | `test_replay_missing_file` | No crash, zero snapshots yielded |
| 6 | `test_replay_stats` | `snapshots_read`, `snapshots_rejected`, `reject_rate_pct` correct |
| 7 | `test_live_tail_follows_growing_file` | New lines yielded after initial read |
| 8 | `test_live_tail_waits_on_no_data` | Polls without crashing when no new data |

---

## TIER 4: Operations (49 tests)

### File 12: `test_logger_factory.py` (~8 tests)

| # | Test | What it validates |
|---|------|-------------------|
| 1 | `test_create_scenario_logger_writes_to_file` | Log message appears in scenario.log |
| 2 | `test_scenario_logger_no_propagation` | `propagate=False`, no root logger pollution |
| 3 | `test_scenario_logger_creates_directory` | Missing dirs created |
| 4 | `test_create_aggregate_logger_writes_to_file` | Writes to aggregate/aggregate.log |
| 5 | `test_score_writer_writes_jsonl` | `write_score()` appends valid JSONL |
| 6 | `test_score_writer_trade_jsonl` | `write_trade()` appends valid JSONL |
| 7 | `test_score_writer_health_jsonl` | `write_health()` appends valid JSONL |
| 8 | `test_score_writer_count_property` | `scores_written` increments |

### File 13: `test_reporting.py` (~8 tests)

| # | Test | What it validates |
|---|------|-------------------|
| 1 | `test_log_result_writes_csv_row` | Row appended to aggregate_metrics.csv |
| 2 | `test_csv_header_written_once` | Header written on first call, not duplicated |
| 3 | `test_csv_columns_match_schema` | All CSV_COLUMNS present in header |
| 4 | `test_log_health_writes_jsonl` | JSON line appended to health.jsonl |
| 5 | `test_log_summary_writes_jsonl` | JSON line appended to summary.jsonl |
| 6 | `test_stats_property` | `csv_rows` counter correct |
| 7 | `test_multiple_results_accumulate` | 100 results -> 100 csv rows |
| 8 | `test_creates_aggregate_directory` | `aggregate/` dir created on init |

### File 14: `test_feature_mirror_writer.py` (~10 tests)

| # | Test | What it validates |
|---|------|-------------------|
| 1 | `test_on_features_writes_jsonl` | Feature event -> JSONL record |
| 2 | `test_regime_cache_included` | Cached regime appears in output record |
| 3 | `test_symbol_filter_applied` | Unallowed symbols skipped |
| 4 | `test_empty_features_skipped` | No features -> no record |
| 5 | `test_on_regime_caches_per_symbol` | Different symbols have independent regime cache |
| 6 | `test_extract_price_priority` | `price` > `close` > `last_price` > `mark_price` |
| 7 | `test_extract_payload_dict` | Dict-based event handled |
| 8 | `test_extract_payload_object` | Object with `.pld` handled |
| 9 | `test_output_dir_created` | Output parent dir created on init |
| 10 | `test_stats_counters` | `snapshots_written`, `snapshots_skipped` correct |

### File 15: `test_hot_reload.py` (~11 tests)

| # | Test | What it validates |
|---|------|-------------------|
| 1 | `test_compute_hash_changes_on_write` | Hash before != hash after |
| 2 | `test_compute_hash_missing_file` | Returns "" for nonexistent file |
| 3 | `test_compute_diff_has_changes` | Added scenarios detected |
| 4 | `test_reload_diff_has_changes_property` | True when added/removed/changed non-empty |
| 5 | `test_reload_diff_no_changes` | False when all empty |
| 6 | `test_try_reload_valid_config` | Callback invoked, generation incremented |
| 7 | `test_try_reload_invalid_yaml_rollback` | Rollback counter incremented, hash unchanged |
| 8 | `test_try_reload_callback_returns_false` | Rollback counter incremented |
| 9 | `test_watch_loop_disabled_exits` | `enabled=False` -> immediate return |
| 10 | `test_stop_signal` | `_running = False` exits loop |
| 11 | `test_stats_property` | All fields present |

### File 16: `test_launcher.py` (~12 tests)

| # | Test | What it validates |
|---|------|-------------------|
| 1 | `test_load_matrix_config_valid` | Real scenario_matrix.yaml loads successfully |
| 2 | `test_load_matrix_config_missing_file` | FileNotFoundError raised |
| 3 | `test_load_matrix_config_invalid_yaml` | ValidationError raised |
| 4 | `test_setup_logging_creates_file_handler` | Log file created in session_dir |
| 5 | `test_setup_logging_console_handler` | Stdout handler present |
| 6 | `test_setup_logging_no_file` | `log_to_file=False` -> no file handler |
| 7 | `test_project_root_resolution` | `parents[5]` points to correct root |
| 8 | `test_session_dir_creation` | Session dir created with timestamp |
| 9 | `test_main_reactor_replay_processes_snapshots` | Integration: 5 snapshots -> 10 scenarios -> results |
| 10 | `test_main_reactor_zero_workers_exits` | 0 workers -> early return |
| 11 | `test_run_default_matrix_path` | Default path resolves correctly |
| 12 | `test_run_custom_matrix_path` | Absolute and relative paths handled |

---

## Cross-Cutting Tests (32 tests)

### File 17: `test_integration_flows.py` (~10 tests) `@pytest.mark.integration`

End-to-end flows through multiple modules.

| # | Test | What it validates |
|---|------|-------------------|
| 1 | `test_snapshot_to_score_full_pipeline` | Snapshot -> IngestGateway -> ScenarioWorker -> score result |
| 2 | `test_ten_scenario_matrix_all_produce_scores` | All 10 scenarios produce non-empty results |
| 3 | `test_aurora_score_differentiation` | S01 vs S02 produce different scores for same input |
| 4 | `test_mr_scenario_produces_scores` | MR scenarios produce valid scores |
| 5 | `test_ensemble_scenario_produces_scores` | Ensemble scenarios produce valid scores |
| 6 | `test_aggregate_csv_populated` | CSV has rows from all scenarios |
| 7 | `test_per_scenario_scores_jsonl` | Each scenario dir has scores.jsonl |
| 8 | `test_effective_config_contains_overrides` | Persisted config reflects applied overrides |
| 9 | `test_replay_to_shutdown_lifecycle` | Full lifecycle: init -> process -> shutdown |
| 10 | `test_mixed_regime_propagation` | Different regime values flow to scoring correctly |

### File 18: `test_regression.py` (~8 tests)

Guards against previously-fixed bugs.

| # | Test | What it validates |
|---|------|-------------------|
| 1 | `test_localbus_payload_extraction_dict` | _extract_payload handles LocalBus dict (Phase 6 fix) |
| 2 | `test_localbus_payload_extraction_message` | _extract_payload handles Message objects |
| 3 | `test_yaml_top_level_key_unwrap` | Config resolver unwraps `{"aurora": {...}}` |
| 4 | `test_yaml_no_double_unwrap` | Flat YAML not double-unwrapped |
| 5 | `test_threshold_sync_on_override` | `_base_threshold` + `provider_configs.threshold` synced |
| 6 | `test_project_root_parents_5` | `parents[5]` from launcher.py = project root |
| 7 | `test_ensemble_valid_override_paths` | S16/S17 override paths validate (no extra="forbid" errors) |
| 8 | `test_scenario_matrix_ten_scenarios_all_valid` | Full matrix parses and all 10 scenarios resolve |

### File 19: `test_scoring_parity.py` (~5 tests) `@pytest.mark.integration`

Ensures standalone domain produces equivalent results to embedded plugin.

| # | Test | What it validates |
|---|------|-------------------|
| 1 | `test_aurora_baseline_parity` | S01 standalone score == embedded plugin score for same input |
| 2 | `test_aurora_score_sign_matches_direction` | Positive features -> positive score, negative -> negative |
| 3 | `test_mr_score_range` | MR scores within [-1, 1] |
| 4 | `test_ensemble_score_is_weighted_combination` | Ensemble score reflects model weights |
| 5 | `test_score_determinism` | Same input -> same score (no random state) |

### File 20: `test_concurrency.py` (~5 tests) `@pytest.mark.slow`

| # | Test | What it validates |
|---|------|-------------------|
| 1 | `test_thread_pool_10_scenarios_no_deadlock` | 10 workers fan-out completes |
| 2 | `test_thread_pool_20_scenarios_no_deadlock` | 20 workers fan-out completes |
| 3 | `test_bounded_queue_concurrent_put_get` | Producer/consumer threads don't corrupt state |
| 4 | `test_no_cross_worker_state_leak` | Workers with mutable state don't share between threads |
| 5 | `test_executor_shutdown_during_execution` | Shutdown while threads running doesn't hang |

### File 21: `test_performance.py` (~4 tests) `@pytest.mark.slow`

| # | Test | What it validates |
|---|------|-------------------|
| 1 | `test_single_snapshot_10_scenarios_under_100ms` | p95 < 100ms per snapshot |
| 2 | `test_single_snapshot_20_scenarios_under_200ms` | p95 < 200ms per snapshot |
| 3 | `test_ingest_1000_lines_replay` | 1000 lines parsed in < 2s |
| 4 | `test_memory_10_scenarios_under_500mb` | RSS < 500MB for 10 scenarios |

---

## File Manifest

| # | File | Tests | Tier |
|---|------|-------|------|
| 0 | `conftest.py` | - | Infra |
| 1 | `test_contracts.py` | 30 | T1 |
| 2 | `test_config_resolver.py` | 28 | T1 |
| 3 | `test_override_allowlist.py` | 18 | T1 |
| 4 | `test_scenario_worker.py` | 20 | T1 |
| 5 | `test_scenario_manager.py` | 18 | T2 |
| 6 | `test_shadow_book.py` | 12 | T2 |
| 7 | `test_backtest_plugin_integration.py` | 8 | T2 |
| 8 | `test_executor.py` | 16 | T3 |
| 9 | `test_backpressure.py` | 14 | T3 |
| 10 | `test_health_monitor.py` | 12 | T3 |
| 11 | `test_ingest_gateway.py` | 8 | T3 |
| 12 | `test_logger_factory.py` | 8 | T4 |
| 13 | `test_reporting.py` | 8 | T4 |
| 14 | `test_feature_mirror_writer.py` | 10 | T4 |
| 15 | `test_hot_reload.py` | 11 | T4 |
| 16 | `test_launcher.py` | 12 | T4 |
| 17 | `test_integration_flows.py` | 10 | X-cut |
| 18 | `test_regression.py` | 8 | X-cut |
| 19 | `test_scoring_parity.py` | 5 | X-cut |
| 20 | `test_concurrency.py` | 5 | X-cut |
| 21 | `test_performance.py` | 4 | X-cut |
| **Total** | | **~265** | |

---

## Verification

```bash
# Run all alpha_search tests
pytest apps/reference/domains/alpha_search/tests/ -v --tb=short

# Run only fast unit tests
pytest apps/reference/domains/alpha_search/tests/ -v -m "unit" --tb=short

# Run integration tests
pytest apps/reference/domains/alpha_search/tests/ -v -m "integration" --tb=short

# Run with coverage
pytest apps/reference/domains/alpha_search/tests/ --cov=apps/reference/domains/alpha_search/runtime --cov-report=term-missing

# Skip slow tests
pytest apps/reference/domains/alpha_search/tests/ -v -m "not slow" --tb=short
```

---

## Critical & Objective Analysis of This Plan

### Strengths

1. **Tier structure mirrors failure criticality.** T1 tests cover the path from raw JSONL to score output. If T1 passes, the domain produces scores. This matches algorithmic system priorities where data pipeline correctness > operational features.

2. **Regression tests codify every bug found during implementation.** The 8 regression tests (File 18) directly encode the `_extract_payload` fix, YAML unwrap fix, threshold sync fix, and `parents[5]` fix. This is standard practice for trading systems where re-introducing a fixed bug can cause silent score corruption.

3. **Contract tests are exhaustive.** 30 tests for Pydantic models with `extra="forbid"` is justified because one missing validation = silent data corruption in downstream scoring. Trading systems require strict schema boundaries.

4. **Concurrency tests address the actual threading model.** ThreadPoolExecutor with 10-20 workers sharing mutable state (feature cache, plugin internals) needs explicit thread-safety testing. The plan includes cross-worker state leak and concurrent put/get tests.

5. **The plan reuses existing test infrastructure.** Follows neocortex test patterns (class-based organization, fixture factories, `@pytest.mark` markers, `tmp_path` for file I/O). No new test frameworks needed.

### Weaknesses and Honest Gaps

1. **No property-based testing.** For scoring functions that accept arbitrary float inputs and produce bounded outputs, Hypothesis-based property tests would catch edge cases (NaN, inf, very large/small values, Decimal precision) that handcrafted fixtures miss. The current plan only tests manually chosen values. **Cost:** Adding Hypothesis dependency + ~15 property tests for scoring models and ShadowBook PnL math.

2. **No chaos/fault injection testing.** The plan tests graceful degradation (health monitor, executor isolation) but doesn't simulate realistic failure modes: disk full during JSONL write, thread pool exhaustion, memory pressure, corrupted mid-write JSONL lines. Production algorithmic systems face these in practice. **Mitigation:** The plan's error-isolation tests (T3) partially cover this, but without real I/O failure injection (e.g., `monkeypatch` on `open()` to raise `OSError`).

3. **Performance tests have arbitrary thresholds.** "p95 < 100ms for 10 scenarios" and "RSS < 500MB" are guesses, not derived from production profiling. Without real hardware benchmarks, these thresholds will either be too lenient (pass but mask real degradation) or too tight (fail on CI but work in production). **Mitigation:** Run initial benchmarks, update thresholds, then use percentage regression detection instead of absolute values.

4. **Scoring parity tests (File 19) are fundamentally limited.** Testing "S01 standalone == embedded plugin" requires running the embedded plugin with identical config and input, which means mocking or standing up the full `main.py` event pipeline. The plan doesn't specify how to obtain the "reference" embedded plugin output. **Realistic fix:** Create a parity test harness that instantiates `AlphaSearchBacktestPlugin` directly (not via standalone pipeline) and compares outputs. This is partially what `test_backtest_plugin_integration.py` already does, making File 19 somewhat redundant.

5. **Hot reload tests (File 15) test mechanics but not safety invariants.** The critical property is: "no snapshot is scored against an inconsistent mix of old/new config." The current tests check hash detection, callback invocation, and rollback counters, but not the atomicity of the swap. In production, a config swap mid-fan-out could cause some workers to use old config and others new. **Mitigation:** Add a test that modifies config while a fan-out is in-progress and verifies all results in that batch use the same generation.

6. **No negative testing for security boundaries.** The system reads YAML and JSONL from disk. Path traversal in `scenario_config_dir`, YAML bombs (`&anchor` + `*merge`), or oversized JSONL lines are not tested. For a trading system on an internal machine this is lower priority, but `yaml.safe_load` should be verified.

7. **~265 tests may have maintenance cost.** Each test is a maintenance commitment. Some tests (especially T4 operational tests for logger, reporter) have low value-to-maintenance ratio since they test thin wrappers around stdlib. Counter-argument: the cost of a silent bug in log rotation or CSV header is hours of debugging when production data is missing.

8. **Missing snapshot: ensemble state isolation over time.** The plan tests bus isolation (T1 File 4 test 7) but not ensemble weight evolution isolation. EnsembleModel accumulates `model_performance` history. Two ensemble scenarios running in parallel could diverge over 1000 snapshots. The plan should include a multi-snapshot test where two ensemble scenarios receive identical input and verify their weight histories remain independent.

### Verdict

The plan is **production-adequate for a v1 trading shadow system** with the following priority additions:
- Add 3-5 Hypothesis property tests for ShadowBook PnL math and scoring boundaries (low effort, high value)
- Add 1 I/O fault injection test for JSONL write failure (OSError on disk full)
- Replace absolute performance thresholds with baseline + regression detection
- Add 1 ensemble state divergence test over 100+ snapshots

Overall test count would grow from ~265 to ~272, which is a reasonable scope increase.
