# Feature And Data Inventory

Dry inventory of data names, feature names, payload fields, and strategy names that the system receives, calculates, emits, or records.

## Exchange / Market Data Input

### Binance `bookTicker`

- `e`
- `s`
- `b`
- `B`
- `a`
- `A`
- `E`

### Normalized `bookTicker`

- `symbol`
- `bid_price`
- `bid_size`
- `ask_price`
- `ask_size`
- `ts`

### Binance `trade` / `aggTrade`

- `e`
- `s`
- `p`
- `q`
- `m`
- `T`
- `E`
- `a`
- `t`

### Normalized trade

- `symbol`
- `price`
- `quantity`
- `is_buyer_maker`
- `ts`
- `trade_id`

### Aggregator state

- `bid_price`
- `bid_size`
- `ask_price`
- `ask_size`
- `bid_ask_time`
- `trades_window`
- `seen_trade_ids`
- `buy_trades`
- `sell_trades`
- `buy_qty`
- `sell_qty`
- `buy_notional`
- `sell_notional`
- `trades_dropped_out_of_order`
- `trades_dropped_missing_ts`
- `trades_dropped_bad_qty`
- `aggtrade_raw_seen`
- `aggtrade_route_attempted`
- `on_trade_called`
- `trade_accepted`
- `trade_dropped`
- `drop_reason_counts`
- `tick_emit_count`
- `prices`
- `latest_price`
- `last_book_ts_ms`
- `last_trade_ts_ms`
- `last_price_ts_ms`

### Trade drop reasons

- `missing_ts`
- `bad_qty`
- `duplicate_trade_id`
- `out_of_order`

### Trade flow states

- `unknown`
- `fresh`
- `degraded`
- `stale`

## Market Tick Output

### `EVT:MARKET_TICK_RECEIVED`

- `ts`
- `symbol`
- `price`
- `bid`
- `ask`
- `mid`
- `bid_size`
- `ask_size`
- `buy_volume`
- `sell_volume`
- `buy_count`
- `sell_count`
- `buy_notional`
- `sell_notional`
- `trades_dropped_out_of_order`
- `trade_flow_state`
- `trade_flow_age_ms`
- `trade_flow_last_trade_ts_ms`
- `trade_flow_window_sec`
- `data_type`
- `data_source`
- `debug_info`

### Market tick nested `features`

- `obi`
- `tfi`
- `delta_price`
- `absorption`

### Trade observability snapshot

- `symbol`
- `aggtrade_raw_seen`
- `aggtrade_route_attempted`
- `on_trade_called`
- `trade_accepted`
- `trade_dropped`
- `drop_reason_counts`
- `buy_count`
- `sell_count`
- `buy_volume`
- `sell_volume`
- `last_trade_ts_ms`
- `tick_emit_count`

### `EVT:ANCHOR_UPDATED`

- `anchor`
- `price`
- `ts_ms`

## Bars / OHLCV

### Bar fields

- `symbol`
- `tf_sec`
- `timeframe_sec`
- `timestamp`
- `datetime`
- `ts`
- `ts_ms`
- `bar_close_ts`
- `bar_close_ts_ms`
- `start_ts_ms`
- `end_ts_ms`
- `open_ts`
- `close_ts`
- `open`
- `high`
- `low`
- `close`
- `volume`
- `trade_count`
- `source_mode`
- `close_boundary_ts_ms`
- `bar_identity`
- `replay_identity`
- `replay_generation`

### Bar trade-flow fields

- `bid_size`
- `ask_size`
- `buy_volume`
- `sell_volume`
- `buy_count`
- `sell_count`
- `buy_notional`
- `sell_notional`
- `trades_dropped_out_of_order`
- `trade_flow_state`
- `trade_flow_age_ms`
- `trade_flow_last_trade_ts_ms`
- `trade_flow_window_sec`

### Gap fields

- `gap_state`
- `gap_policy_action`
- `gap_bars_skipped`
- `is_gap_bar`
- `gap`

## Feature Engineering

### FeatureSet V1

- `obi`
- `tfi`
- `delta_price`
- `price`
- `absorption`
- `liquidity_kappa`
- `ema_bias`
- `volume_spike`
- `volatility_state`
- `depth_imbalance`
- `macro_sync`

### FeatureSet V2 / extra

- `volume_zscore`
- `large_trade_imbalance`
- `spread_bps`
- `funding_rate_normalized`
- `oi_delta_pct`
- `funding_rate`
- `macro_resid`

### TA pass-through features in FE payload

- `macd_line`
- `macd_signal`
- `macd_histogram`
- `stochastic_k`
- `stochastic_d`
- `price_momentum_5m`
- `price_momentum_1h`
- `price_momentum_1d`
- `volume_momentum_5m`
- `rsi_14`
- `atr_pct`
- `ema_bias`

### Price motion

- `ret_10s`
- `ret_60s`
- `ret_300s`
- `ret_900s`
- `vol_pct_10s`
- `vol_pct_60s`
- `vol_pct_300s`
- `vol_pct_900s`
- `pm_norm_10s`
- `pm_norm_60s`
- `pm_norm_300s`
- `pm_norm_900s`
- `pm_norm`
- `pm_raw`

### Pillars

- `pillar_sum`
- `pillar_tactician`
- `pillar_operator`
- `pillar_strategist`
- `pillar_contribs`

### Nested `features.volatility`

- `bar_range`
- `bar_body`
- `true_range`
- `atr_14`
- `range_pct`
- `atr_pct`
- `atr_ready`

### Nested `features.liquidity`

- `obi_close`

### Warmup names

- `full_ready`
- `ticks_seen`
- `ready`
- `reasons`

### Warmup feature keys

- `obi`
- `tfi`
- `delta_price`
- `depth_imbalance`
- `liquidity_kappa`
- `ema_bias`
- `volume_spike`
- `volatility_state`
- `macro_sync`
- `spread_bps`
- `large_trade_imbalance`
- `volume_zscore`
- `macro_resid`
- `absorption`

### `EVT:FEATURES_CALCULATED` / `EVT:TICK_FEATURES_CALCULATED`

- `ts`
- `symbol`
- `tf_sec`
- `features`
- `warmup`
- `price_motion`
- `bar`
- `source_mode`
- `diagnostics`
- `trade_flow_state`
- `trade_flow_age_ms`
- `trade_flow_last_trade_ts_ms`
- `trade_flow_window_sec`
- `data_quality`

### Bar features payload

- `ts`
- `symbol`
- `tf_sec`
- `features`
- `warmup`
- `price_motion`
- `bar`
- `source_mode`
- `regime`
- `diagnostics`
- `trade_flow_state`
- `trade_flow_age_ms`
- `trade_flow_last_trade_ts_ms`
- `trade_flow_window_sec`
- `bar_identity`
- `close_boundary_ts_ms`
- `replay_identity`
- `replay_generation`
- `gap_state`
- `gap_policy_action`
- `gap_bars_skipped`
- `is_gap_bar`
- `gap`

## TA Features

### `EVT:TA_FEATURES_CALCULATED`

- `ts`
- `symbol`
- `tf_sec`
- `bar_close_ts`
- `close`
- `features`
- `warm_up_bars`
- `required_warm_up_bars`
- `is_warm`
- `source`

### TA feature names

- `bb_position`
- `bb_width`
- `rsi_14`
- `price_sma_20_deviation`
- `volume_sma_ratio`
- `stoch_k`
- `stoch_d`
- `price_momentum_5m`
- `price_momentum_1h`
- `price_momentum_1d`
- `volume_momentum_5m`
- `macd_signal`
- `atr_14`
- `atr_ratio`
- `bb_width_change`
- `realized_volatility_1h`
- `realized_volatility_1d`
- `price_range_ratio`

### TA normalized / fallback names

- `range_pct`
- `realized_volatility`
- `volume_volatility_ratio`
- `volume_ratio`

## Decision Input

### `CMD:PROCESS_STRATEGY`

- `symbol`
- `tf_sec`
- `bar_close_ts`
- `bar`
- `features`
- `warmup`
- `regime`
- `structural_regime`
- `source_mode`
- `price_motion`
- `trade_flow_state`
- `trade_flow_age_ms`
- `trade_flow_last_trade_ts_ms`
- `trade_flow_window_sec`
- `bar_identity`
- `close_boundary_ts_ms`
- `replay_identity`
- `replay_generation`
- `gap_state`
- `gap_policy_action`
- `gap_bars_skipped`
- `is_gap_bar`
- `gap`

### Process strategy boundary

- `symbol`
- `tf_sec`
- `bar_close_ts`
- `rid`
- `features`
- `warmup`
- `raw`
- `price_motion`
- `regime`
- `structural_regime`
- `regime_ctx`
- `regime_snapshot`

## Regime Data

### Regime event

- `symbol`
- `regime`
- `confidence`
- `ts`
- `ts_ms`
- `structural_regime_ref`
- `changed`
- `raw_confidence`
- `last_update_ts_ms`
- `raw`

### Regime boundary / cache fields

- `source_model`
- `warmup`
- `axes`
- `regime_layer`
- `regime_scope`
- `regime_clock`
- `basis_tf_sec`
- `bar_close_ts_ms`
- `pre_cutoff_source_model`
- `confidence_min`
- `confidence_max`
- `pre_cutoff_regime`
- `pre_cutoff_confidence`
- `pre_cutoff_clamped_to_min`
- `pre_cutoff_clamped_to_max`
- `pre_cutoff_boundary_reason`
- `uncertain_cutoff`
- `demoted_to_uncertain`
- `raw_regime`
- `raw_confidence`
- `raw_boundary_reason`
- `stable_confidence`
- `hysteresis_bars`
- `hysteresis_confirm_count`
- `cache_write_ts_ms`
- `carried_previous_stable`
- `emitted_confidence_kind`
- `reason_summary`
- `regime_provenance`
- `storm_rejected`

## Strategy Common Output

### `EVT:STRATEGY_SIGNAL_PRODUCED`

- `schema_version`
- `strategy_id`
- `source_scenario_id`
- `strategy_version`
- `symbol`
- `tf_sec`
- `side`
- `bar_close_ts`
- `readiness`
- `runtime_permissions`
- `score`
- `confidence`
- `why`
- `ts_ms`
- `rid`
- `valid_for_ms`
- `why_chain`
- `source_mode`
- `regime`
- `volatility`
- `liquidity`
- `scoring`
- `price_ctx`

### Strategy trace

- `strategy_id`
- `profile_id`
- `symbol`
- `timestamp`
- `source_ts`
- `feature_ts`
- `feature_freshness_ms`
- `required_features_present`
- `required_features_missing`
- `component_scores`
- `weights`
- `combined_score`
- `side`
- `threshold`
- `mode`
- `regime`
- `suppression_reason`
- `decision_route`
- `direct_execution_allowed`

## Strategy: `aurora`

### Timeframe

- `300`

### Config feature groups

- `signal_weights`
- `directional_features`
- `strength_features`
- `essential_features`
- `feature_neutrals`

### Aurora configured features

- `obi`
- `tfi`
- `delta_price`
- `ema_bias`
- `volume_spike`
- `volatility_state`
- `depth_imbalance`
- `macro_resid`
- `macro_sync`
- `absorption`

### Aurora runtime / decision names

- `price_motion`
- `price_motion_norm`
- `regime`
- `regime_confidence`
- `bar_close_ts`
- `pillar_sum`
- `pillar_tactician`
- `pillar_operator`
- `pillar_strategist`
- `pillar_contribs`
- `price`
- `macro_resid`
- `high`
- `low`
- `atr`
- `entry_price`
- `obi`
- `volatility`
- `liquidity`
- `regime_event_ts_ms`
- `regime_source`
- `regime_same_bar`
- `regime_provenance_reason`
- `ret_60s`
- `ret_300s`
- `spread_bps`
- `liquidity_kappa`
- `absorption`

### Aurora native expert evidence

- `obi`
- `tfi`
- `absorption`
- `liquidity_kappa`
- `spread_bps`
- `macro_resid`
- `delta_price`
- `volatility_state`
- `large_trade_imbalance`

### Aurora native expert output

- `schema_version`
- `expert_id`
- `strategy_id`
- `question_type`
- `symbol`
- `ts_ms`
- `side_opinion`
- `confidence`
- `confidence_source`
- `horizon`
- `authority_status`
- `microstructure_evidence`
- `evidence_freshness`
- `missingness`
- `regime_context_ref`
- `legacy_score_trace`
- `invalidates_if`
- `reason_codes`
- `source_refs`

### Aurora expert nested blocks

- `feature_ts_ms`
- `decision_ts_ms`
- `age_ms`
- `freshness_state`
- `per_field`
- `regime_label`
- `regime_confidence`
- `basis_tf_sec`
- `regime_age_ms`
- `raw_score`
- `decision_score`
- `sizing_score`
- `admission_mode`
- `sizing_mode`
- `score_lineage_present`
- `score_trace_authority_note`
- `decision_id`
- `trace_id`
- `source_event`

## Strategy: `mean_reversion`

### Timeframe

- `300`

### Mean Reversion market / FE inputs

- `tfi`
- `obi`
- `liquidity_kappa`
- `price_motion`
- `bar`
- `regime`
- `structural_regime`
- `warmup`
- `volatility`
- `liquidity`
- `funding_rate`

### Mean Reversion config names

- `bb_window`
- `bb_num_std`
- `atr_window`
- `rsi_window`
- `rsi_oversold`
- `rsi_overbought`
- `min_bb_width`
- `max_bb_width`
- `sl_atr_mult`
- `confidence_bb_slope`
- `confidence_rsi_bonus`
- `score_multiplier`
- `tfi_ema_span`
- `tfi_adverse_threshold`
- `obi_confirm_enabled`
- `obi_adverse_threshold`
- `funding_shift_magnitude`
- `funding_normalization_scale`
- `funding_deadband`
- `liquidity_gate`

### Mean Reversion native expert evidence

- `rsi`
- `pct_b`
- `bb_width`
- `band_upper`
- `band_mid`
- `band_lower`
- `atr`
- `funding_rate`
- `funding_cost`
- `entry_boundary`
- `expected_reversion_target`
- `invalidation_level`

### Mean Reversion native expert output

- `schema_version`
- `expert_id`
- `strategy_id`
- `question_type`
- `symbol`
- `ts_ms`
- `side_opinion`
- `confidence`
- `confidence_source`
- `horizon`
- `authority_status`
- `mean_reversion_evidence`
- `regime_context_ref`
- `evidence_freshness`
- `missingness`
- `invalidates_if`
- `reason_codes`
- `source_refs`

### Mean Reversion emitted signal / log names

- `signal_type`
- `entry_price`
- `stop_price`
- `target_price`
- `flat_regime`
- `why`
- `bb_upper`
- `bb_mid`
- `bb_lower`
- `bb_width`
- `pct_b`
- `atr`
- `tf_sec`
- `bar_end_ts_ms`
- `source`
- `reason_code`
- `reason`
- `context`
- `why_chain`

## Strategy: `md_amr`

### Timeframe

- `900`

### MD-AMR runtime inputs

- `features`
- `bar`
- `regime`
- `overall_regime`
- `confidence`
- `positions`
- `exposure_summary`
- `reject_reason_normalized`
- `reject_reason`
- `reason`
- `reason_code`
- `reason_text`
- `warmup`
- `sentiment_state`
- `liquidity`
- `obi_close`
- `volatility`
- `atr`
- `channel_state`

### MD-AMR config names

- `channel_window_bars`
- `channel_robust_pct`
- `atr_window`
- `atr_stats_window`
- `threshold_z`
- `volatility_dampening_factor`
- `target_approach_pct`
- `atr_zscore_clamp`
- `atr_std_floor_pct`

### MD-AMR native expert evidence

- `sentiment_state`
- `entry_anchor`
- `progress_state`
- `setup_quality`
- `hold_quality`
- `context_validity`
- `obi_close`
- `target_approach_pct`
- `channel_position`
- `channel_width_pct`
- `volatility_z`
- `atr`
- `invalidation`

### MD-AMR native expert output

- `schema_version`
- `expert_id`
- `strategy_id`
- `question_type`
- `symbol`
- `ts_ms`
- `side_opinion`
- `lifecycle_opinion`
- `confidence`
- `confidence_source`
- `horizon`
- `authority_status`
- `md_amr_evidence`
- `regime_context_ref`
- `evidence_freshness`
- `missingness`
- `invalidates_if`
- `reason_codes`
- `source_refs`

## Strategy: `alpha_ta_ensemble`

### Timeframe

- `300`

### Subscribed inputs

- `EVT:TA_FEATURES_CALCULATED`
- `CMD:PROCESS_STRATEGY`

### Alpha TA Ensemble input features

- `bb_position`
- `bb_width`
- `rsi_14`
- `price_sma_20_deviation`
- `volume_sma_ratio`
- `stoch_k`
- `stoch_d`
- `price_momentum_5m`
- `price_momentum_1h`
- `price_momentum_1d`
- `volume_momentum_5m`
- `macd_signal`
- `atr_14`
- `atr_ratio`
- `bb_width_change`
- `realized_volatility_1h`
- `realized_volatility_1d`
- `price_range_ratio`
- `range_pct`
- `volume_volatility_ratio`
- `is_warm`

### Alpha TA Ensemble price aliases

- `price`
- `close`
- `last_price`
- `mark_price`

### Alpha TA Ensemble scoring groups

- `mean_reversion`
- `momentum`
- `volatility`

## Strategy: `alpha_mr_s01`

### Timeframe

- `300`

### Subscribed inputs

- `EVT:TA_FEATURES_CALCULATED`
- `CMD:PROCESS_STRATEGY`

### Alpha MR S01 input features

- `bb_position`
- `bb_width`
- `rsi_14`
- `price_sma_20_deviation`
- `stoch_k`
- `stoch_d`
- `volume_sma_ratio`
- `price`
- `is_warm`

### Alpha MR S01 scorer config names

- `bb_weight`
- `rsi_weight`
- `sma_weight`
- `stoch_weight`
- `threshold`
- `rsi_oversold`
- `rsi_overbought`
- `sma_deviation_normalizer`
- `stoch_oversold_zone`
- `stoch_overbought_zone`
- `stoch_signal_strength`
- `volume_enabled`
- `volume_confirm_multiplier`
- `volume_contradict_multiplier`
- `volume_high_threshold`
- `volume_low_threshold`
- `bb_min_width`
- `bb_max_width`
- `bb_narrow_penalty_enabled`
- `bb_narrow_threshold`
- `bb_narrow_penalty`
- `bb_wide_boost_enabled`
- `bb_wide_threshold`
- `bb_max_multiplier`

### Alpha MR S01 scoring payload

- `score`
- `combined_score`
- `confidence`
- `side`
- `threshold`
- `reason`
- `regime`
- `source_scenario_id`
- `components`
- `weights`
- `multipliers`

## Config-Declared Feature Keys

### Readiness declared keys

- `obi`
- `tfi`
- `delta_price`
- `depth_imbalance`
- `liquidity_kappa`
- `absorption`
- `ema_bias`
- `volume_spike`
- `volatility_state`
- `macro_sync`
- `macro_resid`
- `spread_bps`
- `large_trade_imbalance`
- `volume_zscore`

### Feature sanity bounds

- `obi`
- `tfi`
- `absorption`
- `macro_resid`
- `ema_bias`
- `volatility_state`
- `liquidity_kappa`
- `depth_imbalance`
- `volume_spike`
- `volume_zscore`
- `macro_sync`
- `large_trade_imbalance`
- `spread_bps`

### Degraded context contract: `aurora`

- `price`
- `pillar_sum`

### Degraded context contract: `mean_reversion`

- `tfi`
- `obi`
- `price_motion`
- `liquidity_kappa`

### Degraded context contract: `md_amr`

- `price_ref`
- `sentiment_state`
- `atr`
- `liquidity`
- `obi_close`

### Degraded context contract: `alpha_ta_ensemble`

- `rsi_14`
- `bb_position`
- `bb_width`
- `atr_14`

### Risk score weights

- `delta_price_pct`
- `obi`
- `tfi`
- `absorption_inverse`
- `absorption_feature`

## Recorder Output

### Stable row fields

- `timestamp`
- `datetime`
- `symbol`
- `tf_sec`
- `open`
- `high`
- `low`
- `close`
- `volume`
- `trade_count`
- `source_mode`
- `close_boundary_ts_ms`
- `gap_state`
- `gap_policy_action`
- `gap_bars_skipped`
- `is_gap_bar`

### Feature row prefix

- `feat_`

### Price motion row fields

- `pm_norm`
- `pm_raw`
- `pm_norm_10s`
- `pm_norm_60s`
- `pm_norm_300s`
- `pm_norm_900s`

### Regime row fields

- `regime`
- `regime_conf`
- `regime_join_status`
- `regime_join_mode`
- `regime_event_ts_ms`
- `regime_last_update_ts_ms`
- `regime_age_ms`
- `regime_layer`
- `regime_scope`
- `regime_owner`
- `regime_source_model`
- `regime_structural_regime_ref`
- `regime_warmup_full_ready`
- `regime_warmup_reasons`
- `regime_data_drops`
- `regime_data_notes`

### Warmup row fields

- `ready`
- `not_ready_reasons`

## Active Timeframes Seen In Config

- `180`
- `300`
- `900`

## Strategy Names Seen

- `aurora`
- `mean_reversion`
- `md_amr`
- `alpha_ta_ensemble`
- `alpha_mr_s01`
