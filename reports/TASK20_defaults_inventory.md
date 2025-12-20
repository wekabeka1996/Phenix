# TASK20 Config Defaults Inventory

Inventory of all defaults and extra='allow' in config_models.py BaseModel classes.

| Class | Field | Type | Default | Line |
|-------|-------|------|---------|------|
| AccountObserverConfig | model_config | ConfigDict | extra=allow | 1714 |
| AccountObserverConfig | poll_interval | AnnAssign | Field(default=30, description='Polling interval in seconds') | 1715 |
| AccountObserverDomainConfig | poll_interval_sec | AnnAssign | Field(default=5) | 1227 |
| AccountObserverDomainConfig | symbols | AnnAssign | Field(default_factory=list) | 1229 |
| AccountObserverDomainConfig | thread_timeouts | AnnAssign | Field(default_factory=ThreadTimeoutsConfig) | 1230 |
| AccountObserverDomainConfig | trade_limit | AnnAssign | Field(default=10) | 1228 |
| ApiCallLimits | get_klines | AnnAssign | Field(default_factory=KlinesConfig) | 763 |
| ApiCallLimits | get_recent_trades | AnnAssign | Field(default=50) | 762 |
| ArmingConfig | max_attempts | AnnAssign | Field(default=120) | 824 |
| ArmingConfig | require_regime_warmup | AnnAssign | Field(default=False) | 822 |
| ArmingConfig | retry_backoff_ms | AnnAssign | Field(default=1000) | 823 |
| AuroraConfig | account_observer | AnnAssign | Field(default_factory=AccountObserverConfig) | 1791 |
| AuroraConfig | aurora | AnnAssign | Field(default=None, description='Aurora strategy global config') | 1846 |
| AuroraConfig | aurora_instruments | AnnAssign | Field(default_factory=dict, description='Per-symbol Aurora strategy overrides (weights, side_bias, exit, etc.)') | 1812 |
| AuroraConfig | binance_api | AnnAssign | Field(default_factory=BinanceApiConfig) | 1790 |
| AuroraConfig | brackets | AnnAssign | Field(default=None) | 1835 |
| AuroraConfig | bridge | AnnAssign | Field(Ellipsis) | 1800 |
| AuroraConfig | decision | AnnAssign | Field(default=None, description='Override trading.decision if set') | 1831 |
| AuroraConfig | domains | AnnAssign | Field(default=None, description='Domain-specific configurations') | 1803 |
| AuroraConfig | execution | AnnAssign | Field(default=None, description='Override trading.execution if set') | 1833 |
| AuroraConfig | features | AnnAssign | Field(default=None, description='Feature engineering config') | 1844 |
| AuroraConfig | hmm | AnnAssign | Field(default=None, description='HMM regime detector config') | 1843 |
| AuroraConfig | hotreload_whitelist | AnnAssign | Field(default=None, description='Hot-reload allowlist') | 1845 |
| AuroraConfig | instruments | AnnAssign | Field(default_factory=dict, description='Canonical instrument precision map (symbol -> tick_size/step_size)') | 1806 |
| AuroraConfig | logging | AnnAssign | Field(default=None, description='Logging configuration') | 1842 |
| AuroraConfig | mean_reversion | AnnAssign | Field(default=None, description='Mean Reversion 1m strategy config (loaded from strategy profile SSOT)') | 1825 |
| AuroraConfig | models | AnnAssign | Field(default=None, description='Regime detection models from regime.yaml') | 1839 |
| AuroraConfig | ops | AnnAssign | Field(default_factory=OpsConfig) | 1797 |
| AuroraConfig | runtime | AnnAssign | Field(default=None, description='Runtime configuration') | 1847 |
| AuroraConfig | strategies_registry | AnnAssign | Field(default=None, description='Strategy assignments + arbitration config (from strategies.yaml)') | 1819 |
| AuroraConfig | system | AnnAssign | Field(default_factory=SystemConfig) | 1795 |
| AuroraConfig | system_meta | AnnAssign | Field(default_factory=SystemMetaConfig) | 1796 |
| AuroraConfig | trading | AnnAssign | Field(default_factory=TradingConfig) | 1787 |
| AuroraConfig | trading_mode | AnnAssign | Field(default='testnet', description='Trading mode: testnet | production | live') | 1785 |
| AuroraConfig | trailing | AnnAssign | Field(default_factory=dict) | 1836 |
| AuroraExecutionConfig | max_slippage_bps | AnnAssign | Field(default=None, description='Max allowed slippage in basis points') | 1401 |
| AuroraExecutionConfig | model_config | ConfigDict | extra=allow | 1391 |
| AuroraExecutionConfig | order_type | AnnAssign | Field(default=None, description='Order type: LIMIT, MARKET') | 1393 |
| AuroraExecutionConfig | post_only | AnnAssign | Field(default=None, description='Use post-only orders for maker fees') | 1397 |
| AuroraExitConfig | max_hold_sec | AnnAssign | Field(default=None, description='Maximum position hold time in seconds') | 1343 |
| AuroraExitConfig | model_config | ConfigDict | extra=allow | 1337 |
| AuroraExitConfig | sl_pct | AnnAssign | Field(default=None, description='Stop-loss as percentage from entry (e.g., 0.005 = 0.5%)') | 1339 |
| AuroraInstrumentConfig | allowed_regimes | AnnAssign | Field(default=None, description='If set, only trade when current regime is in this list (Phase 3+ regime gating)') | 1525 |
| AuroraInstrumentConfig | cooldown_sec | AnnAssign | Field(default=None, description='Per-instrument cooldown in seconds (overrides global qos.symbol_cooldown_sec)') | 1519 |
| AuroraInstrumentConfig | ema_clamp | AnnAssign | Field(default=None, description='Per-asset EMA clamp range (Phase 3+)') | 1506 |
| AuroraInstrumentConfig | enabled | AnnAssign | Field(default=True, description='Enable Aurora strategy for this instrument (default: True for backward compat)') | 1447 |
| AuroraInstrumentConfig | execution | AnnAssign | Field(default=None, description='Order execution settings') | 1500 |
| AuroraInstrumentConfig | exit | AnnAssign | Field(default=None, description='Stop-loss and max hold time') | 1482 |
| AuroraInstrumentConfig | max_risk_score | AnnAssign | Field(default=None, description='Per-asset max risk score (Phase 3+)') | 1514 |
| AuroraInstrumentConfig | position_mode | AnnAssign | Field(default='DYNAMIC', description='STRICT = No pyramiding (1 trade only), DYNAMIC = Pyramiding allowed up to cap') | 1464 |
| AuroraInstrumentConfig | position_mode | AnnAssign | Field(default='ONE_SIDE', description="Position constraint mode: 'STRICT' (1 pos total), 'ONE_SIDE' (1 pos per side/allow reduce), 'HEDGE' (allow all)") | 1537 |
| AuroraInstrumentConfig | regime_sizing | AnnAssign | Field(default=None, description='Position size multipliers per regime') | 1476 |
| AuroraInstrumentConfig | regime_thresholds | AnnAssign | Field(default=None, description='Threshold multipliers per regime (TREND, VOLATILE, FLAT)') | 1470 |
| AuroraInstrumentConfig | side_bias | AnnAssign | Field(default=None, description='Side bias configuration') | 1459 |
| AuroraInstrumentConfig | signal_threshold | AnnAssign | Field(default=None, description='Per-asset signal threshold (Phase 3+)') | 1510 |
| AuroraInstrumentConfig | take_profit | AnnAssign | Field(default=None, description='TP1/TP2 partial exit settings') | 1488 |
| AuroraInstrumentConfig | timeframe_sec | AnnAssign | Field(default=None, description='Bar timeframe in seconds for this instrument. SOL=180 (3m), BTC/ETH=300 (5m)') | 1531 |
| AuroraInstrumentConfig | trailing_stop | AnnAssign | Field(default=None, description='Trailing stop settings') | 1494 |
| AuroraInstrumentConfig | weights | AnnAssign | Field(default=None, description='Per-feature signal weights from Optuna') | 1453 |
| AuroraSideBiasConfig | model_config | ConfigDict | extra=allow | 1319 |
| AuroraSideBiasConfig | penalty_factor | AnnAssign | Field(default=None, description='Penalty multiplier for counter-bias trades') | 1321 |
| AuroraSideBiasConfig | target_ratio | AnnAssign | Field(default=None, description='Target long/short ratio (e.g., 0.5 = balanced)') | 1329 |
| AuroraSideBiasConfig | window_sec | AnnAssign | Field(default=None, description='Rolling window in seconds for side bias calculation') | 1325 |
| AuroraTakeProfitConfig | model_config | ConfigDict | extra=allow | 1351 |
| AuroraTakeProfitConfig | partial_exit_pct | AnnAssign | Field(default=None, description='Percentage to exit at TP1 (e.g., 0.7 = 70%)') | 1361 |
| AuroraTakeProfitConfig | tp_high_ratio | AnnAssign | Field(default=None, description='TP2 as ratio to ATR or fixed percent') | 1357 |
| AuroraTakeProfitConfig | tp_low_ratio | AnnAssign | Field(default=None, description='TP1 as ratio to ATR or fixed percent') | 1353 |
| AuroraTrailingStopConfig | activation_pct | AnnAssign | Field(default=None, description='Activate trailing after this profit % (e.g., 0.003 = 0.3%)') | 1375 |
| AuroraTrailingStopConfig | enabled | AnnAssign | Field(default=None, description='Enable trailing stop') | 1371 |
| AuroraTrailingStopConfig | min_update_interval_sec | AnnAssign | Field(default=5, description='Minimum seconds between SL updates (rate limit)') | 1383 |
| AuroraTrailingStopConfig | model_config | ConfigDict | extra=allow | 1369 |
| AuroraTrailingStopConfig | trail_pct | AnnAssign | Field(default=None, description='Trail distance as % from high-water mark') | 1379 |
| BarGatingConfig | bar_ms | AnnAssign | Field(default=BinOp, description='Bar duration in milliseconds') | 61 |
| BarGatingConfig | enable | AnnAssign | Field(default=False) | 60 |
| BehaviorFsmConfig | enable | AnnAssign | Field(default=False) | 67 |
| BehaviorFsmConfig | high_vol_multiplier | AnnAssign | Field(default=2.0) | 68 |
| BehaviorFsmConfig | low_vol_multiplier | AnnAssign | Field(default=0.5) | 69 |
| BinanceApiConfig | live | AnnAssign | Field(default_factory=BinanceApiEnv) | 1678 |
| BinanceApiConfig | testnet | AnnAssign | Field(default_factory=BinanceApiEnv) | 1679 |
| BinanceApiEnv | api_key | AnnAssign | Field(default=None) | 1669 |
| BinanceApiEnv | api_secret | AnnAssign | Field(default=None) | 1670 |
| BinanceApiEnv | rest_url | AnnAssign | Field(default=None) | 1671 |
| BinanceApiEnv | ws_url | AnnAssign | Field(default=None) | 1672 |
| BracketsConfig | model_config | ConfigDict | extra=allow | 512 |
| BracketsConfig | oco_emulation | AnnAssign | Field(default=False, description='Emulate OCO orders') | 516 |
| BracketsConfig | offset_bps | AnnAssign | Field(default=5, description='Safety offset in bps') | 519 |
| BracketsConfig | sl | AnnAssign | Field(default=None) | 514 |
| BracketsConfig | stop_loss_bps | AnnAssign | Field(default=50) | 518 |
| BracketsConfig | tp | AnnAssign | Field(default=None) | 515 |
| BridgeConfig | retry_scheduler | AnnAssign | Field(Ellipsis) | 1694 |
| DecisionConfig | bar_gating | AnnAssign | Field(default=None) | 483 |
| DecisionConfig | behavior_fsm | AnnAssign | Field(default=None) | 484 |
| DecisionConfig | cooldown_sec | AnnAssign | Field(default=None, description='Global cooldown (deprecated, use per-instrument)') | 465 |
| DecisionConfig | kelly | AnnAssign | Field(default_factory=KellyConfig) | 480 |
| DecisionConfig | mean_reversion | AnnAssign | Field(default=None) | 486 |
| DecisionConfig | neutral_threshold | AnnAssign | Field(default=None, description='Neutral zone threshold') | 495 |
| DecisionConfig | position_sizing | AnnAssign | Field(default_factory=PositionSizingConfig) | 478 |
| DecisionConfig | production | AnnAssign | Field(default=None) | 461 |
| DecisionConfig | qos | AnnAssign | Field(default_factory=QosConfig) | 481 |
| DecisionConfig | regime_threshold_multipliers | AnnAssign | Field(default_factory=dict, description='Regime threshold multipliers') | 492 |
| DecisionConfig | regime_thresholds | AnnAssign | Field(default_factory=dict, description='Regime-specific signal thresholds') | 490 |
| DecisionConfig | retry_backoff_factor | AnnAssign | Field(default=2.0, description='Retry backoff multiplier') | 474 |
| DecisionConfig | retry_max_count | AnnAssign | Field(default=3, description='Max retry attempts') | 473 |
| DecisionConfig | retry_ttl_ms | AnnAssign | Field(default=300000, description='Retry TTL in ms') | 472 |
| DecisionConfig | roi_exit | AnnAssign | Field(default=None) | 485 |
| DecisionConfig | side_bias_min_score | AnnAssign | Field(default=None, description='Min score for side bias') | 466 |
| DecisionConfig | side_bias_penalty_factor | AnnAssign | Field(default=None, description='Side bias penalty factor') | 467 |
| DecisionConfig | side_bias_target_ratio | AnnAssign | Field(default=None, description='Side bias target ratio') | 468 |
| DecisionConfig | side_bias_window_sec | AnnAssign | Field(default=None, description='Side bias window (seconds)') | 469 |
| DecisionConfig | signal_threshold | AnnAssign | Field(default=0.2, description='Signal score threshold. PRODUCTION MUST OVERRIDE in trading.yaml!') | 464 |
| DecisionConfig | signal_weights | AnnAssign | Field(default_factory=SignalWeights) | 476 |
| DecisionConfig | signals | AnnAssign | Field(default_factory=SignalsConfig) | 477 |
| DecisionConfig | sizing_modifiers | AnnAssign | Field(default_factory=dict, description='Regime-specific multipliers') | 488 |
| DecisionConfig | symbols_to_track | AnnAssign | Field(default=None, description='DEPRECATED: Use instruments SSOT') | 494 |
| DecisionConfig | testnet | AnnAssign | Field(default=None) | 460 |
| DecisionMakingDomainConfig | arming | AnnAssign | Field(default_factory=ArmingConfig) | 838 |
| DecisionMakingDomainConfig | bar_gating | AnnAssign | Field(default_factory=BarGatingConfig) | 834 |
| DecisionMakingDomainConfig | behavior_fsm | AnnAssign | Field(default_factory=BehaviorFsmConfig) | 835 |
| DecisionMakingDomainConfig | features | AnnAssign | Field(default_factory=FeaturesTtlConfig) | 833 |
| DecisionMakingDomainConfig | position_sizing | AnnAssign | Field(default_factory=PositionSizingConfig) | 831 |
| DecisionMakingDomainConfig | qos | AnnAssign | Field(default_factory=QosConfig) | 832 |
| DecisionMakingDomainConfig | risk_skew | AnnAssign | Field(default_factory=RiskSkewConfig) | 837 |
| DecisionMakingDomainConfig | signals | AnnAssign | Field(default_factory=SignalsConfig) | 836 |
| DecisionModeOverrideConfig | model_config | ConfigDict | extra=allow | 445 |
| DecisionModeOverrideConfig | signal_threshold | AnnAssign | Field(default=None) | 448 |
| DeltaPriceConfig | spike_filter_ms | AnnAssign | Field(default=5000, ge=100, le=60000, description='Time gap (ms) above which delta_price is zeroed to filter spikes') | 1051 |
| DepthImbalanceConfig | use_laplace_smoothing | AnnAssign | Field(default=True, description='Use Laplace smoothing (depth_half) in calculation') | 1041 |
| DomainConfigurationConfig | audit_trail | AnnAssign | Field(default_factory=Lambda, description="Audit trail mode (usually 'live' for logging)") | 1616 |
| DomainConfigurationConfig | decision_making | AnnAssign | Field(default_factory=Lambda, description='Decision making mode (should match market_data)') | 1604 |
| DomainConfigurationConfig | execution_position | AnnAssign | Field(default_factory=Lambda, description="Execution mode (MUST be 'testnet' for testing!)") | 1612 |
| DomainConfigurationConfig | feature_engineering | AnnAssign | Field(default_factory=Lambda, description='Feature engineering mode (should match market_data)') | 1600 |
| DomainConfigurationConfig | market_data | AnnAssign | Field(default_factory=Lambda, description="Market data source mode (should be 'live' for real prices)") | 1596 |
| DomainConfigurationConfig | model_config | ConfigDict | extra=allow | 1594 |
| DomainConfigurationConfig | risk_management | AnnAssign | Field(default_factory=Lambda, description='Risk management mode (testnet for safety)') | 1608 |
| DomainModeConfig | model_config | ConfigDict | extra=allow | 1575 |
| DomainModeConfig | trading_mode | AnnAssign | Field(Ellipsis, description="Trading mode for this domain: 'live' or 'testnet'") | 1577 |
| DomainsConfig | account_observer | AnnAssign | Field(default_factory=AccountObserverDomainConfig) | 1309 |
| DomainsConfig | decision_making | AnnAssign | Field(default_factory=DecisionMakingDomainConfig) | 1305 |
| DomainsConfig | execution_position | AnnAssign | Field(default_factory=ExecutionPositionDomainConfig) | 1310 |
| DomainsConfig | feature_engineering | AnnAssign | Field(default_factory=FeatureEngineeringDomainConfig) | 1306 |
| DomainsConfig | position_tracking | AnnAssign | Field(default_factory=PositionTrackingDomainConfig) | 1308 |
| DomainsConfig | risk_management | AnnAssign | Field(default_factory=RiskManagementDomainConfig) | 1307 |
| EmaBiasConfig | clamp_max | AnnAssign | Field(default=0.02, ge=0.0, le=1.0, description='Maximum clamp for EMA bias (typically +2%)') | 946 |
| EmaBiasConfig | clamp_min | AnnAssign | Field(default=UnaryOp, ge=UnaryOp, le=0.0, description='Minimum clamp for EMA bias (typically -2%)') | 941 |
| EmaClampConfig | clamp_max | AnnAssign | Field(default=None, description='Override global ema_bias.clamp_max') | 1417 |
| EmaClampConfig | clamp_min | AnnAssign | Field(default=None, description='Override global ema_bias.clamp_min') | 1416 |
| EmaClampConfig | enabled | AnnAssign | Field(default=False, description='Enable per-asset clamp override') | 1415 |
| EmaConfigDetailed | period_long | AnnAssign | Field(default=7, ge=2, le=200, description='Long EMA period (EMA7 default). Must be > period_short.') | 854 |
| EmaConfigDetailed | period_short | AnnAssign | Field(default=3, ge=1, le=50, description='Short EMA period (EMA3 default). Must be < period_long.') | 849 |
| EmergencyConfig | enabled | AnnAssign | Field(default=False, description='Enable emergency SL') | 529 |
| EmergencyConfig | wait_mode_bars | AnnAssign | Field(default=2, description='Wait mode bars before resuming') | 530 |
| ExecutionConfig | allow_trade_with_guardian_tidy_only | AnnAssign | Field(default=None, description='DEPRECATED') | 718 |
| ExecutionConfig | anti_race_close_ms | AnnAssign | Field(default=800, description='Anti-race window (ms)') | 711 |
| ExecutionConfig | exposure | AnnAssign | Field(default=None) | 701 |
| ExecutionConfig | fallback | AnnAssign | Field(default=None) | 705 |
| ExecutionConfig | fsm_periodic_cleanup_enabled | AnnAssign | Field(default=True, description='FSM periodic cleanup') | 710 |
| ExecutionConfig | limit_orders | AnnAssign | Field(default=None) | 706 |
| ExecutionConfig | manage | AnnAssign | Field(default=None) | 700 |
| ExecutionConfig | min_post_interval_per_symbol_ms | AnnAssign | Field(default=None, description='DEPRECATED') | 717 |
| ExecutionConfig | open_order_type | AnnAssign | Field(default=None, description='DEPRECATED: No consumption found') | 714 |
| ExecutionConfig | order_guardian | AnnAssign | Field(default=None, description='DEPRECATED: Guardian not config') | 719 |
| ExecutionConfig | order_params | AnnAssign | Field(default=None, description='DEPRECATED: No consumption found') | 715 |
| ExecutionConfig | orders | AnnAssign | Field(default=None) | 707 |
| ExecutionConfig | preflight_backoff_ms | AnnAssign | Field(default=None, description='DEPRECATED: No consumption found') | 716 |
| ExecutionConfig | watchdog | AnnAssign | Field(default=None) | 702 |
| ExecutionPositionDomainConfig | exposure_guard | AnnAssign | Field(default_factory=ExposureGuardConfig) | 1292 |
| ExecutionPositionDomainConfig | fsm_open | AnnAssign | Field(default_factory=FsmOpenConfig) | 1293 |
| ExecutionPositionDomainConfig | idempotent_cancel | AnnAssign | Field(default_factory=IdempotentCancelConfig) | 1296 |
| ExecutionPositionDomainConfig | metrics_collector | AnnAssign | Field(default_factory=MetricsCollectorConfig) | 1295 |
| ExecutionPositionDomainConfig | order_index | AnnAssign | Field(default_factory=OrderIndexConfig) | 1294 |
| ExecutionPositionDomainConfig | utils | AnnAssign | Field(default_factory=ExecutionUtilsConfig) | 1297 |
| ExecutionPositionDomainConfig | watchdog | AnnAssign | Field(default_factory=WatchdogConfig) | 1291 |
| ExecutionUtilsConfig | basis_points_base | AnnAssign | Field(default=10000.0) | 1284 |
| ExecutionUtilsConfig | client_order_id_max_length | AnnAssign | Field(default=32) | 1283 |
| ExposureConfig | count_pending_orders | AnnAssign | Field(default=False, description='Count pending orders in exposure') | 578 |
| ExposureConfig | exclude_reduce_only | AnnAssign | Field(default=False, description='Exclude reduce-only from exposure') | 579 |
| ExposureConfig | leverage_defaults | AnnAssign | Field(default_factory=Lambda) | 576 |
| ExposureConfig | max_directional_ratio | AnnAssign | Field(default=2.0) | 570 |
| ExposureConfig | max_equity_utilization_pct | AnnAssign | Field(default=0.2) | 566 |
| ExposureConfig | max_portfolio_fraction | AnnAssign | Field(default=0.2) | 567 |
| ExposureConfig | max_side_utilization_pct | AnnAssign | Field(default_factory=Lambda) | 568 |
| ExposureConfig | pending_reservation_ttl_sec | AnnAssign | Field(default=45, description='Reservation TTL') | 573 |
| ExposureConfig | pending_ttl_sec | AnnAssign | Field(default=90) | 572 |
| ExposureConfig | per_symbol_cap_pct | AnnAssign | Field(default=0.08) | 571 |
| ExposureConfig | positions_stale_ttl_sec | AnnAssign | Field(default=120) | 575 |
| ExposureConfig | post_fill_hold_ttl_sec | AnnAssign | Field(default=30) | 574 |
| ExposureGuardConfig | max_concentration_pct | AnnAssign | Field(default=0.1) | 1246 |
| ExposureGuardConfig | max_directional_ratio | AnnAssign | Field(default=2.0) | 1245 |
| ExposureGuardConfig | max_equity_utilization_pct | AnnAssign | Field(default=0.2) | 1241 |
| ExposureGuardConfig | max_long_utilization_pct | AnnAssign | Field(default=0.2) | 1243 |
| ExposureGuardConfig | max_portfolio_fraction | AnnAssign | Field(default=0.2) | 1242 |
| ExposureGuardConfig | max_short_utilization_pct | AnnAssign | Field(default=0.2) | 1244 |
| ExposureGuardConfig | pending_timeout_sec | AnnAssign | Field(default=5) | 1247 |
| ExposureGuardConfig | pending_ttl_sec | AnnAssign | Field(default=90) | 1238 |
| ExposureGuardConfig | post_fill_ttl_sec | AnnAssign | Field(default=5) | 1239 |
| ExposureGuardConfig | stale_ttl_sec | AnnAssign | Field(default=5) | 1240 |
| FailsafeConfig | max_hold_sec | AnnAssign | Field(default=86400) | 171 |
| FeatureDefaultsConfig | correlation_default | AnnAssign | Field(default=0.0, ge=UnaryOp, le=1.0, description='Default correlation value when insufficient data') | 1081 |
| FeatureDefaultsConfig | ms_per_sec | AnnAssign | Field(default=1000, ge=1000, le=1000, description='Milliseconds per second (constant for clarity)') | 1086 |
| FeatureDefaultsConfig | neutral_value | AnnAssign | Field(default=0.5, ge=0.0, le=1.0, description='Default neutral value for all normalized features (0.5 = center of [0,1])') | 1071 |
| FeatureDefaultsConfig | zero_value | AnnAssign | Field(default=0.0, ge=0.0, le=1.0, description='Value for truly zero/absent features (absorption placeholder)') | 1076 |
| FeatureEngineeringConfig | ema | AnnAssign | Field(default_factory=dict) | 784 |
| FeatureEngineeringConfig | liquidity | AnnAssign | Field(default_factory=dict) | 787 |
| FeatureEngineeringConfig | macro_sync | AnnAssign | Field(default_factory=dict) | 788 |
| FeatureEngineeringConfig | volatility | AnnAssign | Field(default_factory=dict) | 786 |
| FeatureEngineeringConfig | volume | AnnAssign | Field(default_factory=dict) | 785 |
| FeatureEngineeringDomainConfig | defaults | AnnAssign | Field(default_factory=FeatureDefaultsConfig) | 1133 |
| FeatureEngineeringDomainConfig | delta_price | AnnAssign | Field(default_factory=DeltaPriceConfig) | 1127 |
| FeatureEngineeringDomainConfig | depth_imbalance | AnnAssign | Field(default_factory=DepthImbalanceConfig) | 1126 |
| FeatureEngineeringDomainConfig | ema | AnnAssign | Field(default_factory=EmaConfigDetailed) | 1117 |
| FeatureEngineeringDomainConfig | ema_bias | AnnAssign | Field(default_factory=EmaBiasConfig) | 1123 |
| FeatureEngineeringDomainConfig | enable_new_metrics | AnnAssign | Field(default=True, description='Enable Phase 1 metrics (ema_bias, volume_spike, etc.)') | 1104 |
| FeatureEngineeringDomainConfig | liquidity | AnnAssign | Field(default_factory=LiquidityConfigDetailed) | 1120 |
| FeatureEngineeringDomainConfig | macro_sync | AnnAssign | Field(default_factory=MacroSyncMetricsConfig) | 1130 |
| FeatureEngineeringDomainConfig | volatility | AnnAssign | Field(default_factory=VolatilityConfigDetailed) | 1119 |
| FeatureEngineeringDomainConfig | volatility_state | AnnAssign | Field(default_factory=VolatilityStateConfig) | 1125 |
| FeatureEngineeringDomainConfig | volume | AnnAssign | Field(default_factory=VolumeConfigDetailed) | 1118 |
| FeatureEngineeringDomainConfig | volume_input_mode | AnnAssign | Field(default='integrate', pattern='^(integrate|sample_window_total)$', description="Volume input mode: 'integrate' (sum ticks) or 'sample_window_total' (treat tick as pre-windowed sample)") | 1110 |
| FeatureEngineeringDomainConfig | volume_spike | AnnAssign | Field(default_factory=VolumeSpikeConfig) | 1124 |
| FeaturesTtlConfig | ttl_sec | AnnAssign | Field(default=5) | 812 |
| FsmOpenConfig | idempotency_window_sec | AnnAssign | Field(default=60) | 1254 |
| IdempotentCancelConfig | max_retries | AnnAssign | Field(default=2) | 1276 |
| InstrumentPrecisionSpec | model_config | ConfigDict | extra=allow | 34 |
| InstrumentPrecisionSpec | step_size | AnnAssign | Field(default=None) | 38 |
| InstrumentPrecisionSpec | symbol | AnnAssign | Field(default=None) | 36 |
| InstrumentPrecisionSpec | tick_size | AnnAssign | Field(default=None) | 37 |
| InstrumentSpec | min_notional | AnnAssign | Field(default='10.0', description='Minimum notional value in USDT') | 22 |
| InstrumentSpec | min_qty | AnnAssign | Field(default='0.001') | 21 |
| InstrumentSpec | quote | AnnAssign | Field(default='USDT') | 24 |
| InstrumentSpec | step_size | AnnAssign | Field(default='0.001', description='Quantity precision') | 19 |
| InstrumentSpec | symbol | AnnAssign | Field(Ellipsis) | 18 |
| InstrumentSpec | tick_size | AnnAssign | Field(default='0.01', description='Price precision') | 20 |
| KellyConfig | base_probability | AnnAssign | Field(default=0.5) | 145 |
| KellyConfig | kelly_alpha | AnnAssign | Field(default=0.8) | 147 |
| KellyConfig | kelly_cap | AnnAssign | Field(default=0.25) | 146 |
| KellyConfig | payoff_ratio_r | AnnAssign | Field(default=1.5) | 148 |
| KlinesConfig | interval | AnnAssign | Field(default='1m', description='Kline interval') | 751 |
| KlinesConfig | limit | AnnAssign | Field(default=2, description='Max klines to fetch') | 752 |
| LiquidityConfigDetailed | depth_half | AnnAssign | Field(default=1000.0, gt=0, le=1000000, description='Half-depth parameter for liquidity kappa and depth imbalance (USD)') | 911 |
| LiquidityConfigDetailed | kappa_max | AnnAssign | Field(default=1.0, ge=0.0, le=1.0, description='Maximum liquidity kappa value') | 921 |
| LiquidityConfigDetailed | kappa_min | AnnAssign | Field(default=0.3, ge=0.0, le=1.0, description='Minimum liquidity kappa value') | 916 |
| LoggingConfig | file | AnnAssign | Field(default='logs/aurora_core.log') | 1724 |
| LoggingConfig | format | AnnAssign | Field(default='json') | 1725 |
| LoggingConfig | level | AnnAssign | Field(default='INFO') | 1723 |
| LoggingConfig | model_config | ConfigDict | extra=allow | 1721 |
| LoggingConfig | rotation | AnnAssign | Field(default_factory=Lambda) | 1726 |
| MRAssetConfig | allowed_regimes | AnnAssign | Field(default_factory=Lambda, description='Regimes where trading is allowed') | 281 |
| MRAssetConfig | bb_window | AnnAssign | Field(default=None) | 277 |
| MRAssetConfig | enabled | AnnAssign | Field(default=False) | 262 |
| MRAssetConfig | min_vol_atr | AnnAssign | Field(default=None) | 278 |
| MRAssetConfig | position_mode | AnnAssign | Field(default='DYNAMIC', description='STRICT = No pyramiding (1 trade only), DYNAMIC = Pyramiding allowed up to cap') | 286 |
| MRAssetConfig | risk | AnnAssign | Field(default=None, description='Risk configuration for this symbol') | 271 |
| MRAssetConfig | sl_pct | AnnAssign | Field(default=None, description='SL as percent (e.g., 0.019 = 1.9%)') | 279 |
| MRAssetConfig | strategy | AnnAssign | Field(default=None, description='Strategy parameter overrides for this symbol') | 265 |
| MRAssetRiskConfig | max_risk_score | AnnAssign | Field(default=None, description='Max risk score threshold') | 252 |
| MRAssetRiskConfig | position_size_usd | AnnAssign | Field(default=None, description='Position size in USD') | 251 |
| MRRegimeSizingConfig | sizing_mult | AnnAssign | Field(default=1.0) | 299 |
| MRRegimeSizingConfig | stop_mult | AnnAssign | Field(default=1.0) | 300 |
| MRRegimeSizingConfig | target_mult | AnnAssign | Field(default=1.0) | 301 |
| MRRegimeThresholdsConfig | high_vol_pct | AnnAssign | Field(default=0.003, description='ATR% for FLAT_HIGH') | 224 |
| MRRegimeThresholdsConfig | low_vol_pct | AnnAssign | Field(default=0.001, description='ATR% for FLAT_LOW') | 225 |
| MRRiskConfig | daily_loss_limit_usd | AnnAssign | Field(default=50.0) | 313 |
| MRRiskConfig | expected_pnl_multiplier | AnnAssign | Field(default=1.5) | 314 |
| MRRiskConfig | fees_pct | AnnAssign | Field(default=0.0004) | 315 |
| MRRiskConfig | max_concurrent_positions | AnnAssign | Field(default=3) | 312 |
| MRRiskConfig | position_size_usd | AnnAssign | Field(default=100.0) | 311 |
| MRRiskConfig | slippage_pct | AnnAssign | Field(default=0.0002) | 316 |
| MRStrategyOverrideConfig | bb_num_std | AnnAssign | Field(default=None, description='BB std multiplier') | 236 |
| MRStrategyOverrideConfig | bb_window | AnnAssign | Field(default=None, description='BB window size') | 235 |
| MRStrategyOverrideConfig | cooldown_sec | AnnAssign | Field(default=None, description='Cooldown between trades') | 241 |
| MRStrategyOverrideConfig | entry_threshold | AnnAssign | Field(default=None, description='Entry distance threshold') | 238 |
| MRStrategyOverrideConfig | min_bb_width | AnnAssign | Field(default=None, description='Min BB width filter') | 237 |
| MRStrategyOverrideConfig | sl_atr_mult | AnnAssign | Field(default=None, description='SL ATR multiplier override') | 240 |
| MRStrategyOverrideConfig | tp_to_mid | AnnAssign | Field(default=None, description='TP to mid vs outer band') | 239 |
| MRStrategyParamsConfig | atr_window | AnnAssign | Field(default=14, description='ATR window for stops') | 201 |
| MRStrategyParamsConfig | bb_num_std | AnnAssign | Field(default=2.0, description='BB standard deviations') | 200 |
| MRStrategyParamsConfig | bb_window | AnnAssign | Field(default=20, description='Bollinger Bands window') | 199 |
| MRStrategyParamsConfig | cooldown_sec | AnnAssign | Field(default=60, description='Cooldown between signals') | 214 |
| MRStrategyParamsConfig | entry_threshold | AnnAssign | Field(default=0.05, description='%B threshold for entry') | 204 |
| MRStrategyParamsConfig | max_bb_width | AnnAssign | Field(default=0.05, description='Max BB width') | 210 |
| MRStrategyParamsConfig | min_bars | AnnAssign | Field(default=25, description='Min bars before trading') | 208 |
| MRStrategyParamsConfig | min_bb_width | AnnAssign | Field(default=0.001, description='Min BB width') | 209 |
| MRStrategyParamsConfig | rsi_overbought | AnnAssign | Field(default=70.0, description='RSI overbought level') | 206 |
| MRStrategyParamsConfig | rsi_oversold | AnnAssign | Field(default=30.0, description='RSI oversold level') | 205 |
| MRStrategyParamsConfig | rsi_window | AnnAssign | Field(default=14, description='RSI window') | 202 |
| MRStrategyParamsConfig | sl_atr_mult | AnnAssign | Field(default=1.5, description='SL as ATR multiplier') | 212 |
| MRStrategyParamsConfig | tp_to_mid | AnnAssign | Field(default=True, description='Target mid BB') | 213 |
| MacroSyncConfig | align_mode | AnnAssign | Field(default='strict_len', description="Alignment mode: 'strict_len' (exact match) or 'tail_min_len' (use min overlap tail)") | 731 |
| MacroSyncConfig | anchor_update_from_ticks | AnnAssign | Field(default=True, description='Update anchor buffers from symbol ticks (false = EVT:ANCHOR_UPDATED only)') | 739 |
| MacroSyncConfig | anchors | AnnAssign | Field(default_factory=list, description='Anchor symbols for macro alignment') | 725 |
| MacroSyncConfig | emit_abs | AnnAssign | Field(default=False, description='DEPRECATED: Not implemented. Planned removal: v2.0') | 728 |
| MacroSyncConfig | enabled | AnnAssign | Field(default=True, description='Enable macro sync (anchor subscription and events)') | 724 |
| MacroSyncConfig | min_buffer_size | AnnAssign | Field(default=10, description='Min samples in buffer for correlation') | 735 |
| MacroSyncConfig | time_diff_threshold_ms | AnnAssign | Field(default=5000, description='Max time diff (ms) between ticks for return calculation') | 736 |
| MacroSyncConfig | window | AnnAssign | Field(default=60, description='Window in seconds') | 727 |
| MacroSyncMetricsConfig | align_mode | AnnAssign | Field(default='strict_len', pattern='^(strict_len|tail_min_len)$', description="Alignment mode: 'strict_len' (require exact match) or 'tail_min_len' (use shorter tail)") | 1004 |
| MacroSyncMetricsConfig | anchor_update_from_ticks | AnnAssign | Field(default=True, description='Update anchor buffers from symbol ticks (set false to avoid double-count when anchor is also trade symbol)') | 1011 |
| MacroSyncMetricsConfig | anchors | AnnAssign | Field(default_factory=Lambda, min_length=1, description='Anchor symbols for correlation (market leaders)') | 997 |
| MacroSyncMetricsConfig | enabled | AnnAssign | Field(default=True, description='Enable macro sync correlation calculation') | 978 |
| MacroSyncMetricsConfig | min_buffer_size | AnnAssign | Field(default=3, ge=2, le=100, description='Minimum buffer size before computing correlation') | 987 |
| MacroSyncMetricsConfig | time_diff_threshold_ms | AnnAssign | Field(default=5000, ge=100, le=60000, description='Maximum time difference (ms) between ticks for return calculation') | 982 |
| MacroSyncMetricsConfig | window | AnnAssign | Field(default=60, ge=10, le=1000, description='Rolling window size for correlation calculation') | 992 |
| ManageConfig | auto | AnnAssign | Field(default=False) | 554 |
| ManageConfig | brackets | AnnAssign | Field(default=None) | 552 |
| ManageConfig | emergency | AnnAssign | Field(default=None) | 553 |
| ManageConfig | failsafe | AnnAssign | Field(default=None) | 556 |
| ManageConfig | orphan_monitor | AnnAssign | Field(default=None) | 555 |
| MarketDataConfig | api_call_limits | AnnAssign | Field(default_factory=ApiCallLimits) | 776 |
| MarketDataConfig | macro_sync | AnnAssign | Field(default=None) | 777 |
| MarketDataConfig | poll_interval_sec | AnnAssign | Field(default=2.0) | 773 |
| MarketDataConfig | use_multiprocessing | AnnAssign | Field(default=False, description='Enable multiprocessing') | 774 |
| MarketDataConfig | websocket_streams | AnnAssign | Field(default_factory=Lambda) | 775 |
| MaxRiskScoreConfig | enabled | AnnAssign | Field(default=False, description='Enable per-asset max_risk_score override') | 1432 |
| MaxRiskScoreConfig | value | AnnAssign | Field(default=None, description='Max risk score threshold for entry filtering') | 1433 |
| MeanReversion1mStrategyConfig | allowed_regimes | AnnAssign | Field(default_factory=Lambda, description='Whitelist of Flat regimes to trade in (global default)') | 346 |
| MeanReversion1mStrategyConfig | assets | AnnAssign | Field(default_factory=dict) | 340 |
| MeanReversion1mStrategyConfig | emit_trade_intent_directly | AnnAssign | Field(default=True, description='If true, MR emits trade intent directly (legacy). If false, emits MR_SIGNAL for DM gateway.') | 357 |
| MeanReversion1mStrategyConfig | enabled | AnnAssign | Field(default=False, description='Enable MR 1m strategy') | 328 |
| MeanReversion1mStrategyConfig | model_config | ConfigDict | extra=allow | 325 |
| MeanReversion1mStrategyConfig | regime_sizing | AnnAssign | Field(default_factory=dict) | 343 |
| MeanReversion1mStrategyConfig | regime_thresholds | AnnAssign | Field(default_factory=MRRegimeThresholdsConfig) | 337 |
| MeanReversion1mStrategyConfig | risk | AnnAssign | Field(default_factory=MRRiskConfig) | 352 |
| MeanReversion1mStrategyConfig | strategy | AnnAssign | Field(default_factory=MRStrategyParamsConfig) | 334 |
| MeanReversion1mStrategyConfig | timeframe_sec | AnnAssign | Field(default=60, description='Bar timeframe in seconds') | 331 |
| MeanReversionConfig | allowed_regimes | AnnAssign | Field(default_factory=Lambda) | 185 |
| MeanReversionConfig | bb_std_dev | AnnAssign | Field(default=2.0) | 183 |
| MeanReversionConfig | bb_window | AnnAssign | Field(default=20) | 182 |
| MeanReversionConfig | enabled | AnnAssign | Field(default=False) | 181 |
| MeanReversionConfig | min_vol_atr | AnnAssign | Field(default=0.001) | 184 |
| MeanReversionRegimeModelConfig | confidence_multiplier | AnnAssign | Field(default=100.0, ge=1.0, description='Confidence scaling factor') | 630 |
| MeanReversionRegimeModelConfig | model_config | ConfigDict | extra=allow | 627 |
| MeanReversionRegimeModelConfig | threshold | AnnAssign | Field(default=0.005, ge=0.0, description='Max price deviation from SMAs for MR regime') | 629 |
| MetricsCollectorConfig | recent_rejections_minutes | AnnAssign | Field(default=5) | 1269 |
| MetricsCollectorConfig | window_size_minutes | AnnAssign | Field(default=60) | 1268 |
| OpsConfig | allowlist_symbols | AnnAssign | Field(default_factory=list, description='If non-empty, only these symbols can trade. Empty = no restrictions') | 1560 |
| OpsConfig | metrics_url | AnnAssign | Field(default='http://127.0.0.1:8000/metrics') | 1566 |
| OpsConfig | model_config | ConfigDict | extra=allow | 1545 |
| OpsConfig | panic_killswitch | AnnAssign | Field(default=False, description='Emergency kill switch - blocks all new CMD:OPEN when True') | 1548 |
| OpsConfig | panic_ttl_sec | AnnAssign | Field(default=None, description='Optional TTL in seconds for panic_killswitch; if set, killswitch auto-expires after this many seconds') | 1552 |
| OpsConfig | quiet_hours_utc | AnnAssign | Field(default_factory=list, description="Time windows in UTC when trading is blocked (e.g., ['22:00-06:00'])") | 1556 |
| OpsConfig | reports_dir | AnnAssign | Field(default='reports') | 1567 |
| OrderIndexConfig | ttl_sec | AnnAssign | Field(default=3600) | 1261 |
| OrdersConfig | default_ttl_seconds | AnnAssign | Field(default=120, description='Default order TTL') | 690 |
| OrdersConfig | model_config | ConfigDict | extra=allow | 688 |
| OrphanMonitorConfig | enabled | AnnAssign | Field(default=False, description='Enable orphan monitoring') | 541 |
| OrphanMonitorConfig | model_config | ConfigDict | extra=allow | 539 |
| PositionSizingConfig | kappa_mode | AnnAssign | Field(default='passive') | 132 |
| PositionSizingConfig | liquidity_based_cap_usd | AnnAssign | Field(default=10000.0) | 129 |
| PositionSizingConfig | liquidity_kappa | AnnAssign | Field(default=1.0) | 131 |
| PositionSizingConfig | liquidity_kappa_mode | AnnAssign | Field(default=None, description='Alias for kappa_mode (legacy)') | 133 |
| PositionSizingConfig | min_position_size_usd | AnnAssign | Field(default=10.0) | 128 |
| PositionSizingConfig | risk_contract_v1 | AnnAssign | Field(default=None, description='Risk-Sizing V1 contract (ETAP1: disabled by default)') | 136 |
| PositionSizingConfig | risk_fraction_q | AnnAssign | Field(default=None) | 130 |
| PositionTrackingDomainConfig | enable_market_tick_subscription | AnnAssign | Field(default=False, description='Enable EVT:MARKET_TICK_RECEIVED subscription for mark-price PnL (optional)') | 1216 |
| PositionTrackingDomainConfig | positions_stale_ttl_sec | AnnAssign | Field(default=15, description='Portfolio freshness TTL for AuroraBridge gate') | 1215 |
| PositionTrackingDomainConfig | precision | AnnAssign | Field(default_factory=PrecisionConfig) | 1213 |
| PositionTrackingDomainConfig | thread_timeouts | AnnAssign | Field(default_factory=ThreadTimeoutsConfig) | 1214 |
| PrecisionConfig | decimal_places | AnnAssign | Field(default=2) | 1199 |
| PrecisionConfig | flat_position_threshold | AnnAssign | Field(default=1e-12) | 1198 |
| PrecisionConfig | quantity_min_threshold | AnnAssign | Field(default=1e-09) | 1197 |
| QosConfig | enforce | AnnAssign | Field(default=False) | 160 |
| QosConfig | exposure_block_cooldown_sec | AnnAssign | Field(default=60) | 155 |
| QosConfig | max_intents_per_minute_per_symbol | AnnAssign | Field(default=10) | 158 |
| QosConfig | mode | AnnAssign | Field(default='defer', description='defer | block') | 159 |
| QosConfig | symbol_cooldown_sec | AnnAssign | Field(default=3, description='Global fallback cooldown. Per-symbol config takes priority.') | 157 |
| ROIExitConfig | enabled | AnnAssign | Field(default=True) | 165 |
| ROIExitConfig | target_roi_pct | AnnAssign | Field(default=50.0) | 166 |
| RegimeDetectorConfig | model_config | ConfigDict | extra=allow | 658 |
| RegimeDetectorConfig | models | AnnAssign | Field(default_factory=RegimeModelsConfig, description='Regime detection models config') | 660 |
| RegimeModelConfig | confidence_max | AnnAssign | Field(default=0.95) | 653 |
| RegimeModelConfig | confidence_min | AnnAssign | Field(default=0.5) | 652 |
| RegimeModelConfig | confidence_multiplier | AnnAssign | Field(default=20.0) | 651 |
| RegimeModelConfig | model_config | ConfigDict | extra=allow | 649 |
| RegimeModelsConfig | mean_reversion | AnnAssign | Field(default_factory=MeanReversionRegimeModelConfig, description='Mean reversion model') | 644 |
| RegimeModelsConfig | sma_trend | AnnAssign | Field(default_factory=SMARegimeModelConfig, description='SMA trend model') | 642 |
| RegimeModelsConfig | volatility | AnnAssign | Field(default_factory=VolatilityRegimeModelConfig, description='Volatility model') | 643 |
| RegimeSizingSymbolConfig | enabled | AnnAssign | Field(default=False, description='Enable regime-based sizing for this symbol') | 90 |
| RegimeSizingSymbolConfig | high_vol_multiplier | AnnAssign | Field(default=1.0, description='Multiplier for HIGH_VOLATILITY regime (storm)') | 92 |
| RegimeSizingSymbolConfig | low_vol_multiplier | AnnAssign | Field(default=1.0, description='Multiplier for LOW_VOLATILITY regime (calm)') | 91 |
| RetrySchedulerConfig | max_attempts | AnnAssign | Field(Ellipsis, description='Max retry attempts for deferred intents') | 1686 |
| RetrySchedulerConfig | min_retry_delay_ms | AnnAssign | Field(Ellipsis, description='Minimum retry delay (ms)') | 1687 |
| RiskContractV1Config | effective_leverage | AnnAssign | Field(default=10.0, description='Assumed leverage for notional calculation') | 108 |
| RiskContractV1Config | enabled | AnnAssign | Field(default=False, description='Enable Risk-Sizing V1') | 107 |
| RiskContractV1Config | model_config | ConfigDict | extra=allow | 105 |
| RiskContractV1Config | per_symbol_margin_fraction | AnnAssign | Field(default_factory=dict, description='Target margin fraction per symbol (e.g., BTCUSDT: 0.04)') | 111 |
| RiskContractV1Config | regime_sizing | AnnAssign | Field(default_factory=dict, description='Per-symbol regime-based sizing config') | 117 |
| RiskManagementDataSourcesConfig | market_data | AnnAssign | Field(Ellipsis) | 1701 |
| RiskManagementDataSourcesConfig | portfolio_state | AnnAssign | Field(Ellipsis) | 1702 |
| RiskManagementDomainConfig | risk_score_weights | AnnAssign | Field(default_factory=RiskScoreWeightsConfig) | 1178 |
| RiskManagementDomainConfig | trading_allowed_thresholds | AnnAssign | Field(default_factory=TradingAllowedThresholdsConfig) | 1179 |
| RiskManagementDomainConfig | use_absorption_penalty | AnnAssign | Field(default=True, description='Whether to include absorption penalty in risk score. Set to False to disable deprecated absorption feature.') | 1185 |
| RiskManagementDomainConfig | validation | AnnAssign | Field(default_factory=RiskValidationConfig) | 1180 |
| RiskScoreWeightsConfig | absorption_inverse | AnnAssign | Field(default=0.3) | 1155 |
| RiskScoreWeightsConfig | delta_price_pct | AnnAssign | Field(default=0.1) | 1152 |
| RiskScoreWeightsConfig | obi | AnnAssign | Field(default=0.3) | 1153 |
| RiskScoreWeightsConfig | tfi | AnnAssign | Field(default=0.3) | 1154 |
| RiskSkewConfig | defer_cooldown_sec | AnnAssign | Field(default=2, description='Cooldown between deferred retries') | 805 |
| RiskSkewConfig | max_defer_count | AnnAssign | Field(default=3, description='Max DEFERs per symbol before NO_TRADE_UNTIL_REFRESH') | 804 |
| RiskSkewConfig | max_skew_sec | AnnAssign | Field(default=5, description='Max age difference between features.ts and risk.ts') | 803 |
| RiskValidationConfig | total_weight_max | AnnAssign | Field(default=2.0) | 1171 |
| RiskValidationConfig | total_weight_min | AnnAssign | Field(default=0.5) | 1170 |
| SLConfig | fixed_bps | AnnAssign | Field(default=50, description='Fixed basis points') | 501 |
| SLConfig | model_config | ConfigDict | extra=allow | 500 |
| SMARegimeModelConfig | confidence_max | AnnAssign | Field(default=0.95, ge=0.0, le=1.0, description='Maximum confidence value') | 603 |
| SMARegimeModelConfig | confidence_min | AnnAssign | Field(default=0.5, ge=0.0, le=1.0, description='Minimum confidence value') | 602 |
| SMARegimeModelConfig | confidence_multiplier | AnnAssign | Field(default=20.0, ge=1.0, description='Confidence scaling factor') | 601 |
| SMARegimeModelConfig | model_config | ConfigDict | extra=allow | 597 |
| SMARegimeModelConfig | sma_long_period | AnnAssign | Field(default=50, ge=5, description='Long SMA period for trend detection') | 600 |
| SMARegimeModelConfig | sma_short_period | AnnAssign | Field(default=10, ge=2, description='Short SMA period for trend detection') | 599 |
| SignalThresholdConfig | enabled | AnnAssign | Field(default=False, description='Enable per-asset threshold override') | 1424 |
| SignalThresholdConfig | value | AnnAssign | Field(default=None, description='Override global signal_threshold') | 1425 |
| SignalWeights | delta_price | AnnAssign | Field(default=0.2) | 50 |
| SignalWeights | depth_imbalance | AnnAssign | Field(default=0.05) | 54 |
| SignalWeights | ema_bias | AnnAssign | Field(default=0.15) | 51 |
| SignalWeights | macro_sync | AnnAssign | Field(default=0.05) | 55 |
| SignalWeights | obi | AnnAssign | Field(default=0.2) | 48 |
| SignalWeights | tfi | AnnAssign | Field(default=0.2) | 49 |
| SignalWeights | volatility_state | AnnAssign | Field(default=0.05) | 53 |
| SignalWeights | volume_spike | AnnAssign | Field(default=0.15) | 52 |
| SignalsConfig | enable_new_metrics | AnnAssign | Field(default=False) | 75 |
| SignalsConfig | normalize | AnnAssign | Field(default=True) | 74 |
| StrategiesArbitrationConfig | logging | AnnAssign | Field(default_factory=StrategiesArbitrationLoggingConfig) | 392 |
| StrategiesArbitrationConfig | mode | AnnAssign | Field(default='priority', description="Arbitration mode: 'priority' (only supported mode, lower number = higher priority)") | 384 |
| StrategiesArbitrationConfig | priority | AnnAssign | Field(default_factory=dict, description='Strategy priority ranks (lower = higher priority)') | 388 |
| StrategiesArbitrationLoggingConfig | log_level | AnnAssign | Field(default='INFO', description='Log level for arbitration events (INFO/WARNING/ERROR)') | 374 |
| StrategiesArbitrationLoggingConfig | rejected_why_prefix | AnnAssign | Field(default='ARBITRATION_REJECT', description='Prefix for why-codes when strategy intent is rejected') | 370 |
| StrategiesRegistryConfig | arbitration | AnnAssign | Field(default_factory=StrategiesArbitrationConfig, description='Arbitration policy for strategy conflicts') | 417 |
| StrategiesRegistryConfig | assignments | AnnAssign | Field(default_factory=dict, description='Per-symbol strategy assignments (symbol → list[strategy_id])') | 413 |
| StrategiesRegistryConfig | version | AnnAssign | Field(default='1.0.0', description='Strategies registry config version') | 409 |
| SystemConfig | logging | AnnAssign | Field(default_factory=LoggingConfig) | 1744 |
| SystemConfig | market_data | AnnAssign | Field(default=None, description='Market data system settings') | 1745 |
| SystemConfig | model_config | ConfigDict | extra=allow | 1742 |
| SystemMarketDataConfig | emit_workers | AnnAssign | Field(Ellipsis, description='Thread pool size for non-blocking FSM.emit()') | 1736 |
| SystemMarketDataConfig | local_queue_maxsize | AnnAssign | Field(Ellipsis, description='Max size of local queue (proxy internal)') | 1735 |
| SystemMarketDataConfig | model_config | ConfigDict | extra=allow | 1732 |
| SystemMarketDataConfig | queue_maxsize | AnnAssign | Field(Ellipsis, description='Max size of IPC queue (worker → proxy)') | 1734 |
| SystemMarketDataConfig | tick_ttl_ms | AnnAssign | Field(Ellipsis, description='Max age of tick data in ms — older ticks are DROPPED') | 1737 |
| SystemMetaConfig | calibrator | AnnAssign | Field(default_factory=dict) | 1767 |
| SystemMetaConfig | hardening | AnnAssign | Field(default_factory=dict) | 1770 |
| SystemMetaConfig | hawkes | AnnAssign | Field(default_factory=dict) | 1768 |
| SystemMetaConfig | hotreload_whitelist | AnnAssign | Field(default_factory=list) | 1769 |
| SystemMetaConfig | kelly | AnnAssign | Field(default_factory=dict) | 1766 |
| SystemMetaConfig | position_tracking | AnnAssign | Field(default_factory=dict) | 1771 |
| SystemMetaConfig | regime_config_version | AnnAssign | Field(default=None) | 1763 |
| SystemMetaConfig | risk_core | AnnAssign | Field(default_factory=dict) | 1765 |
| SystemMetaConfig | runtime | AnnAssign | Field(default_factory=SystemRuntimeMeta) | 1772 |
| SystemMetaConfig | sequential_tests | AnnAssign | Field(default_factory=dict) | 1764 |
| SystemMetaConfig | system_config_version | AnnAssign | Field(default=None) | 1762 |
| SystemRuntimeMeta | config_dir | AnnAssign | Field(default=None, description='Filesystem path of the config directory in use') | 1754 |
| SystemRuntimeMeta | config_name | AnnAssign | Field(default=None, description='Identifier of the loaded config profile') | 1753 |
| TPConfig | fixed_bps | AnnAssign | Field(default=100, description='Fixed basis points') | 507 |
| TPConfig | model_config | ConfigDict | extra=allow | 506 |
| ThreadTimeoutsConfig | join_timeout_sec | AnnAssign | Field(default=10) | 1206 |
| TradingAllowedThresholdsConfig | max_risk_score | AnnAssign | Field(default=0.8, description='Max risk score. PRODUCTION MUST OVERRIDE in domains.yaml!') | 1163 |
| TradingConfig | aurora_instruments | AnnAssign | Field(default_factory=dict, description='Per-instrument Aurora strategy configuration (Optuna results)') | 1631 |
| TradingConfig | decision | AnnAssign | Field(default_factory=DecisionConfig) | 1628 |
| TradingConfig | domain_configuration | AnnAssign | Field(default_factory=DomainConfigurationConfig, description='Domain-level trading mode configuration for hybrid mode (live data + testnet execution)') | 1659 |
| TradingConfig | domains | AnnAssign | Field(default_factory=DomainsConfig) | 1639 |
| TradingConfig | execution | AnnAssign | Field(default=None) | 1629 |
| TradingConfig | feature_engineering | AnnAssign | Field(default=None) | 1637 |
| TradingConfig | instruments | AnnAssign | Field(default_factory=dict) | 1630 |
| TradingConfig | market_data | AnnAssign | Field(default=None) | 1636 |
| TradingConfig | mode | AnnAssign | Field(default='testnet', description='testnet | production | live') | 1626 |
| TradingConfig | ops | AnnAssign | Field(default=None, description='Operations config (panic killswitch, quiet hours, allowlist)') | 1652 |
| TradingConfig | risk | AnnAssign | Field(default_factory=dict, description='Legacy risk configuration (daily gate, etc)') | 1642 |
| TradingConfig | risk_budgets | AnnAssign | Field(default_factory=dict, description='Risk Budgeting Configuration') | 1646 |
| TradingConfig | risk_management | AnnAssign | Field(Ellipsis) | 1649 |
| TradingConfig | symbols_to_track | AnnAssign | Field(default_factory=list, description='List of symbols to track for multi-TF aggregation') | 1635 |
| TradingConfig | tca_prefs | AnnAssign | Field(default_factory=dict, description='TCA Preferences') | 1645 |
| TradingRiskManagementConfig | data_sources | AnnAssign | Field(Ellipsis) | 1709 |
| VolatilityConfigDetailed | sma_length | AnnAssign | Field(default=10, ge=2, le=100, description='SMA length for volatility state calculation') | 895 |
| VolatilityConfigDetailed | window_sec | AnnAssign | Field(default=60, ge=1, le=3600, description='Range window for volatility calculation in seconds') | 900 |
| VolatilityRegimeModelConfig | atr_period | AnnAssign | Field(default=14, ge=1, description='ATR calculation period') | 614 |
| VolatilityRegimeModelConfig | atr_sma_length | AnnAssign | Field(default=100, ge=10, description='ATR SMA length for baseline') | 615 |
| VolatilityRegimeModelConfig | enabled | AnnAssign | Field(default=True, description='Enable volatility regime detection') | 613 |
| VolatilityRegimeModelConfig | high_vol_confidence_multiplier | AnnAssign | Field(default=2.0, ge=1.0, description='Confidence scaling for high vol') | 618 |
| VolatilityRegimeModelConfig | low_vol_confidence_multiplier | AnnAssign | Field(default=3.0, ge=1.0, description='Confidence scaling for low vol') | 619 |
| VolatilityRegimeModelConfig | low_vol_multiplier | AnnAssign | Field(default=0.5, ge=0.0, le=1.0, description='Low vol threshold (ATR < low_vol_mult * avg)') | 617 |
| VolatilityRegimeModelConfig | model_config | ConfigDict | extra=allow | 611 |
| VolatilityRegimeModelConfig | threshold_multiplier | AnnAssign | Field(default=2.0, ge=1.0, description='High vol threshold (ATR > threshold_mult * avg)') | 616 |
| VolatilityStateConfig | cap_max | AnnAssign | Field(default=3.0, gt=1.0, le=10.0, description='Maximum cap for volatility ratio normalization') | 1030 |
| VolumeConfigDetailed | min_window_volume_usd | AnnAssign | Field(default=0.0, ge=0.0, description='Minimum volume threshold for active signal (Commit 6)') | 884 |
| VolumeConfigDetailed | sma_length | AnnAssign | Field(default=5, ge=2, le=100, description='SMA length for volume spike calculation') | 874 |
| VolumeConfigDetailed | window_sec | AnnAssign | Field(default=60, ge=1, le=3600, description='Volume aggregation window in seconds') | 879 |
| VolumeSpikeConfig | cap_max | AnnAssign | Field(default=3.0, gt=1.0, le=10.0, description='Maximum cap for volume spike ratio (e.g., 3.0 = 300% of average)') | 967 |
| WatchdogConfig | ack_ttl_ms | AnnAssign | Field(default=8000) | 586 |
| WatchdogConfig | check_interval_ms | AnnAssign | Field(default=1000) | 588 |
| WatchdogConfig | fill_ttl_ms | AnnAssign | Field(default=30000) | 587 |
| WatchdogConfig | rps_limit | AnnAssign | Field(default=10) | 589 |

Total defaults found: 489
