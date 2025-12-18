# TASK23A Optional-null YAML Patch Plan

Plan for adding missing config keys into canonical YAML SSOT.
- `add_default`: add missing model default values (TASK21A compatibility)
- `add_null`: add explicit `null` for Optional-required fields (TASK23A)

| Key | Action | Value | File | Path |
|-----|--------|-------|------|------|
| BracketsConfig.sl | add_null | None | config/aurora/trading.yaml | trading.execution.brackets.sl |
| BracketsConfig.tp | add_null | None | config/aurora/trading.yaml | trading.execution.brackets.tp |
| ExecutionConfig.manage | skip | {'auto': True, 'brackets': {'oco_emulation': True, 'stop_loss_bps': 40, 'offset_bps': 5, 'sl': {'fixed_bps': 40}, 'tp': {'fixed_bps': 80}}, 'orphan_monitor': {'enabled': True}, 'emergency': None, 'failsafe': None} | config/aurora/trading.yaml | trading.execution.manage |
| ExecutionConfig.exposure | skip | {'max_equity_utilization_pct': 2.0, 'max_portfolio_fraction': 2.0, 'max_side_utilization_pct': {'long': 1.5, 'short': 1.5}, 'max_directional_ratio': 50.0, 'per_symbol_cap_pct': 0.08, 'count_pending_orders': True, 'exclude_reduce_only': True, 'pending_ttl_sec': 90, 'pending_reservation_ttl_sec': 45, 'post_fill_hold_ttl_sec': 5, 'positions_stale_ttl_sec': 15, 'leverage_defaults': {'BTCUSDT': 20, 'ETHUSDT': 20, 'SOLUSDT': 20, 'XRPUSDT': 20, 'DOGEUSDT': 20, '__default__': 20}} | config/aurora/trading.yaml | trading.execution.exposure |
| ExecutionConfig.watchdog | skip | {'ack_ttl_ms': 8000, 'fill_ttl_ms': 60000, 'check_interval_ms': 1000, 'rps_limit': 10} | config/aurora/trading.yaml | trading.execution.watchdog |
| ExecutionConfig.fallback | skip | None | config/aurora/trading.yaml | trading.execution.fallback |
| ExecutionConfig.limit_orders | skip | None | config/aurora/trading.yaml | trading.execution.limit_orders |
| ExecutionConfig.orders | skip | {'default_ttl_seconds': 15} | config/aurora/trading.yaml | trading.execution.orders |
| ExecutionConfig.open_order_type | skip | MARKET | config/aurora/trading.yaml | trading.execution.open_order_type |
| ExecutionConfig.order_params | skip | {'LIMIT': {'timeInForce': 'GTC'}, 'STOP_MARKET': {'workingType': 'MARK_PRICE'}, 'TAKE_PROFIT_MARKET': {'workingType': 'MARK_PRICE'}, 'TRAILING_STOP_MARKET': {'callbackRate': '0.5'}} | config/aurora/trading.yaml | trading.execution.order_params |
| ExecutionConfig.preflight_backoff_ms | skip | [120, 250, 400, 800, 1200, 1800] | config/aurora/trading.yaml | trading.execution.preflight_backoff_ms |
| ExecutionConfig.min_post_interval_per_symbol_ms | skip | 300 | config/aurora/trading.yaml | trading.execution.min_post_interval_per_symbol_ms |
| ExecutionConfig.allow_trade_with_guardian_tidy_only | skip | False | config/aurora/trading.yaml | trading.execution.allow_trade_with_guardian_tidy_only |
| ExecutionConfig.order_guardian | skip | {'unified': True, 'emit_tidy_event': True, 'cleanup_ttl_ms': 6000, 'symbol_cooldown_ms': 4000, 'poll_interval_ms': 5000, 'ledger_db_path': 'data/order_ledger.db'} | config/aurora/trading.yaml | trading.execution.order_guardian |
| ManageConfig.brackets | skip | {'oco_emulation': True, 'stop_loss_bps': 40, 'offset_bps': 5, 'sl': {'fixed_bps': 40}, 'tp': {'fixed_bps': 80}} | config/aurora/trading.yaml | trading.execution.manage.brackets |
| ManageConfig.emergency | skip | None | config/aurora/trading.yaml | trading.execution.manage.emergency |
| ManageConfig.orphan_monitor | skip | {'enabled': True} | config/aurora/trading.yaml | trading.execution.manage.orphan_monitor |
| ManageConfig.failsafe | skip | None | config/aurora/trading.yaml | trading.execution.manage.failsafe |
| DecisionConfig.testnet | skip | {'signal_threshold': None} | config/aurora/trading.yaml | trading.decision.testnet |
| DecisionConfig.production | skip | {'signal_threshold': None} | config/aurora/trading.yaml | trading.decision.production |
| DecisionConfig.cooldown_sec | skip | 10 | config/aurora/trading.yaml | trading.decision.cooldown_sec |
| DecisionConfig.side_bias_min_score | skip | None | config/aurora/trading.yaml | trading.decision.side_bias_min_score |
| DecisionConfig.side_bias_penalty_factor | skip | 0.5 | config/aurora/trading.yaml | trading.decision.side_bias_penalty_factor |
| DecisionConfig.side_bias_target_ratio | skip | 0.6 | config/aurora/trading.yaml | trading.decision.side_bias_target_ratio |
| DecisionConfig.side_bias_window_sec | skip | 60 | config/aurora/trading.yaml | trading.decision.side_bias_window_sec |
| DecisionConfig.bar_gating | skip | None | config/aurora/trading.yaml | trading.decision.bar_gating |
| DecisionConfig.behavior_fsm | skip | {'enable': False, 'high_vol_multiplier': 2.0, 'low_vol_multiplier': 0.5} | config/aurora/trading.yaml | trading.decision.behavior_fsm |
| DecisionConfig.roi_exit | skip | None | config/aurora/trading.yaml | trading.decision.roi_exit |
| DecisionConfig.mean_reversion | skip | None | config/aurora/trading.yaml | trading.decision.mean_reversion |
| DecisionConfig.symbols_to_track | skip | ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'DOGEUSDT', 'XRPUSDT'] | config/aurora/trading.yaml | trading.decision.symbols_to_track |
| DecisionConfig.neutral_threshold | skip | 0.18 | config/aurora/trading.yaml | trading.decision.neutral_threshold |
| PositionSizingConfig.risk_fraction_q | skip | 0.05 | config/aurora/trading.yaml | trading.decision.position_sizing.risk_fraction_q |
| PositionSizingConfig.liquidity_kappa_mode | skip | dynamic | config/aurora/trading.yaml | trading.decision.position_sizing.liquidity_kappa_mode |
| PositionSizingConfig.risk_contract_v1 | skip | None | config/aurora/trading.yaml | trading.decision.position_sizing.risk_contract_v1 |
| DecisionModeOverrideConfig.signal_threshold | add_null | None | config/aurora/trading.yaml | trading.decision.mode_override.signal_threshold |
| BinanceApiEnv.api_key | add_null | None | config/aurora/trading.yaml | binance_api.env.api_key |
| BinanceApiEnv.api_secret | add_null | None | config/aurora/trading.yaml | binance_api.env.api_secret |
| BinanceApiEnv.rest_url | add_null | None | config/aurora/trading.yaml | binance_api.env.rest_url |
| BinanceApiEnv.ws_url | add_null | None | config/aurora/trading.yaml | binance_api.env.ws_url |
| MarketDataConfig.macro_sync | skip | {'enabled': True, 'anchors': ['BTCUSDT', 'ETHUSDT'], 'window': 60, 'emit_abs': False, 'align_mode': 'tail_min_len', 'min_buffer_size': 3, 'time_diff_threshold_ms': 60000, 'anchor_update_from_ticks': False} | config/aurora/trading.yaml | trading.market_data.macro_sync |

Summary: 7 to add, 33 already exist
