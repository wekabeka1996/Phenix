# TASK21A YAML Patch Plan

Plan for adding default values to canonical YAML files.

| Key | Action | Value | File | Path |
|-----|--------|-------|------|------|
| InstrumentSpec.symbol | skip | Field(Ellipsis) | config/aurora/instruments.yaml | instruments.symbol |
| InstrumentSpec.step_size | skip | 0.001 | config/aurora/instruments.yaml | instruments.step_size |
| InstrumentSpec.tick_size | skip | 0.01 | config/aurora/instruments.yaml | instruments.tick_size |
| InstrumentSpec.min_qty | skip | 0.001 | config/aurora/instruments.yaml | instruments.min_qty |
| InstrumentSpec.min_notional | skip | 10.0 | config/aurora/instruments.yaml | instruments.min_notional |
| InstrumentSpec.quote | skip | USDT | config/aurora/instruments.yaml | instruments.quote |
| InstrumentPrecisionSpec.model_config | skip | extra=allow | config/aurora/instruments.yaml | instruments.model_config |
| InstrumentPrecisionSpec.symbol | skip | Field(Ellipsis) | config/aurora/instruments.yaml | instruments.symbol |
| InstrumentPrecisionSpec.tick_size | skip | 0.01 | config/aurora/instruments.yaml | instruments.tick_size |
| InstrumentPrecisionSpec.step_size | skip | 0.001 | config/aurora/instruments.yaml | instruments.step_size |
| SignalWeights.obi | skip | 0.15 | config/aurora/trading.yaml | trading.decision.signal_weights.obi |
| SignalWeights.tfi | skip | 0.15 | config/aurora/trading.yaml | trading.decision.signal_weights.tfi |
| SignalWeights.delta_price | skip | 0.1 | config/aurora/trading.yaml | trading.decision.signal_weights.delta_price |
| SignalWeights.ema_bias | skip | 0.15 | config/aurora/trading.yaml | trading.decision.signal_weights.ema_bias |
| SignalWeights.volume_spike | skip | 0.1 | config/aurora/trading.yaml | trading.decision.signal_weights.volume_spike |
| SignalWeights.volatility_state | skip | 0.1 | config/aurora/trading.yaml | trading.decision.signal_weights.volatility_state |
| SignalWeights.depth_imbalance | skip | 0.15 | config/aurora/trading.yaml | trading.decision.signal_weights.depth_imbalance |
| SignalWeights.macro_sync | skip | 0.1 | config/aurora/trading.yaml | trading.decision.signal_weights.macro_sync |
| BarGatingConfig.enable | skip | False | config/aurora/trading.yaml | trading.decision.bar_gating.enable |
| BarGatingConfig.bar_ms | skip | BinOp | config/aurora/trading.yaml | trading.decision.bar_gating.bar_ms |
| BehaviorFsmConfig.enable | skip | False | config/aurora/trading.yaml | trading.decision.behavior_fsm.enable |
| BehaviorFsmConfig.high_vol_multiplier | skip | 2.0 | config/aurora/trading.yaml | trading.decision.behavior_fsm.high_vol_multiplier |
| BehaviorFsmConfig.low_vol_multiplier | skip | 0.5 | config/aurora/trading.yaml | trading.decision.behavior_fsm.low_vol_multiplier |
| SignalsConfig.normalize | skip | True | config/aurora/trading.yaml | trading.decision.signals.normalize |
| SignalsConfig.enable_new_metrics | skip | False | config/aurora/trading.yaml | trading.decision.signals.enable_new_metrics |
| RegimeSizingSymbolConfig.enabled | skip | False | config/aurora/trading.yaml | trading.decision.regime_sizing.enabled |
| RegimeSizingSymbolConfig.low_vol_multiplier | skip | 1.0 | config/aurora/trading.yaml | trading.decision.regime_sizing.low_vol_multiplier |
| RegimeSizingSymbolConfig.high_vol_multiplier | skip | 1.0 | config/aurora/trading.yaml | trading.decision.regime_sizing.high_vol_multiplier |
| RiskContractV1Config.model_config | skip | extra=allow | config/aurora/trading.yaml | trading.decision.position_sizing.risk_contract_v1.model_config |
| RiskContractV1Config.enabled | skip | False | config/aurora/trading.yaml | trading.decision.position_sizing.risk_contract_v1.enabled |
| RiskContractV1Config.effective_leverage | skip | 10.0 | config/aurora/trading.yaml | trading.decision.position_sizing.risk_contract_v1.effective_leverage |
| RiskContractV1Config.per_symbol_margin_fraction | skip | {'BTCUSDT': 0.04, 'ETHUSDT': 0.055, 'XRPUSDT': 0.04, 'DOGEUSDT': 0.05, 'SOLUSDT': 0.06} | config/aurora/trading.yaml | trading.decision.position_sizing.risk_contract_v1.per_symbol_margin_fraction |
| RiskContractV1Config.regime_sizing | skip | {} | config/aurora/trading.yaml | trading.decision.position_sizing.risk_contract_v1.regime_sizing |
| PositionSizingConfig.min_position_size_usd | skip | 10 | config/aurora/trading.yaml | trading.decision.position_sizing.min_position_size_usd |
| PositionSizingConfig.liquidity_based_cap_usd | skip | 10000 | config/aurora/trading.yaml | trading.decision.position_sizing.liquidity_based_cap_usd |
| PositionSizingConfig.risk_fraction_q | skip | 0.05 | config/aurora/trading.yaml | trading.decision.position_sizing.risk_fraction_q |
| PositionSizingConfig.liquidity_kappa | skip | 1.0 | config/aurora/trading.yaml | trading.decision.position_sizing.liquidity_kappa |
| PositionSizingConfig.kappa_mode | skip | passive | config/aurora/trading.yaml | trading.decision.position_sizing.kappa_mode |
| PositionSizingConfig.liquidity_kappa_mode | skip | dynamic | config/aurora/trading.yaml | trading.decision.position_sizing.liquidity_kappa_mode |
| PositionSizingConfig.risk_contract_v1 | skip | {'enabled': False, 'effective_leverage': 10.0, 'per_symbol_margin_fraction': {'BTCUSDT': 0.04, 'ETHUSDT': 0.055, 'XRPUSDT': 0.04, 'DOGEUSDT': 0.05, 'SOLUSDT': 0.06}, 'fixed_notional_usd': {'BTCUSDT': 200.0, 'ETHUSDT': 250.0, 'XRPUSDT': 200.0, 'DOGEUSDT': 200.0}, 'sol_regime_multipliers': {'calm': 1.5, 'storm': 0.5}, 'model_config': 'extra=allow', 'regime_sizing': {}} | config/aurora/trading.yaml | trading.decision.position_sizing.risk_contract_v1 |
| KellyConfig.base_probability | skip | 0.5 | config/aurora/trading.yaml | trading.decision.position_sizing.kelly.base_probability |
| KellyConfig.kelly_cap | skip | 0.25 | config/aurora/trading.yaml | trading.decision.position_sizing.kelly.kelly_cap |
| KellyConfig.kelly_alpha | skip | 0.8 | config/aurora/trading.yaml | trading.decision.position_sizing.kelly.kelly_alpha |
| KellyConfig.payoff_ratio_r | skip | 1.5 | config/aurora/trading.yaml | trading.decision.position_sizing.kelly.payoff_ratio_r |
| QosConfig.exposure_block_cooldown_sec | skip | 30 | config/aurora/trading.yaml | trading.decision.qos.exposure_block_cooldown_sec |
| QosConfig.symbol_cooldown_sec | skip | 1 | config/aurora/trading.yaml | trading.decision.qos.symbol_cooldown_sec |
| QosConfig.max_intents_per_minute_per_symbol | skip | 60 | config/aurora/trading.yaml | trading.decision.qos.max_intents_per_minute_per_symbol |
| QosConfig.mode | skip | defer | config/aurora/trading.yaml | trading.decision.qos.mode |
| QosConfig.enforce | skip | False | config/aurora/trading.yaml | trading.decision.qos.enforce |
| ROIExitConfig.enabled | skip | True | config/aurora/trading.yaml | trading.decision.roi_exit.enabled |
| ROIExitConfig.target_roi_pct | skip | 50.0 | config/aurora/trading.yaml | trading.decision.roi_exit.target_roi_pct |
| FailsafeConfig.max_hold_sec | skip | 86400 | config/aurora/trading.yaml | trading.execution.failsafe.max_hold_sec |
| MeanReversionConfig.enabled | skip | False | config/aurora/trading.yaml | trading.decision.mean_reversion.enabled |
| MeanReversionConfig.bb_window | skip | 20 | config/aurora/trading.yaml | trading.decision.mean_reversion.bb_window |
| MeanReversionConfig.bb_std_dev | skip | 2.0 | config/aurora/trading.yaml | trading.decision.mean_reversion.bb_std_dev |
| MeanReversionConfig.min_vol_atr | skip | 0.001 | config/aurora/trading.yaml | trading.decision.mean_reversion.min_vol_atr |
| MeanReversionConfig.allowed_regimes | add | None | config/aurora/trading.yaml | trading.decision.mean_reversion.allowed_regimes |
| MRStrategyParamsConfig.bb_window | skip | 20 | config/aurora/strategies/mean_reversion_1m.yaml | mean_reversion_1m.strategy.bb_window |
| MRStrategyParamsConfig.bb_num_std | skip | 2.0 | config/aurora/strategies/mean_reversion_1m.yaml | mean_reversion_1m.strategy.bb_num_std |
| MRStrategyParamsConfig.atr_window | skip | 14 | config/aurora/strategies/mean_reversion_1m.yaml | mean_reversion_1m.strategy.atr_window |
| MRStrategyParamsConfig.rsi_window | skip | 14 | config/aurora/strategies/mean_reversion_1m.yaml | mean_reversion_1m.strategy.rsi_window |
| MRStrategyParamsConfig.entry_threshold | skip | 0.05 | config/aurora/strategies/mean_reversion_1m.yaml | mean_reversion_1m.strategy.entry_threshold |
| MRStrategyParamsConfig.rsi_oversold | skip | 30 | config/aurora/strategies/mean_reversion_1m.yaml | mean_reversion_1m.strategy.rsi_oversold |
| MRStrategyParamsConfig.rsi_overbought | skip | 70 | config/aurora/strategies/mean_reversion_1m.yaml | mean_reversion_1m.strategy.rsi_overbought |
| MRStrategyParamsConfig.min_bars | skip | 25 | config/aurora/strategies/mean_reversion_1m.yaml | mean_reversion_1m.strategy.min_bars |
| MRStrategyParamsConfig.min_bb_width | skip | 0.001 | config/aurora/strategies/mean_reversion_1m.yaml | mean_reversion_1m.strategy.min_bb_width |
| MRStrategyParamsConfig.max_bb_width | skip | 0.05 | config/aurora/strategies/mean_reversion_1m.yaml | mean_reversion_1m.strategy.max_bb_width |
| MRStrategyParamsConfig.sl_atr_mult | skip | 1.5 | config/aurora/strategies/mean_reversion_1m.yaml | mean_reversion_1m.strategy.sl_atr_mult |
| MRStrategyParamsConfig.tp_to_mid | skip | True | config/aurora/strategies/mean_reversion_1m.yaml | mean_reversion_1m.strategy.tp_to_mid |
| MRStrategyParamsConfig.cooldown_sec | skip | 60 | config/aurora/strategies/mean_reversion_1m.yaml | mean_reversion_1m.strategy.cooldown_sec |
| MRRegimeThresholdsConfig.high_vol_pct | skip | 0.003 | config/aurora/strategies/mean_reversion_1m.yaml | mean_reversion_1m.regime_thresholds.high_vol_pct |
| MRRegimeThresholdsConfig.low_vol_pct | skip | 0.001 | config/aurora/strategies/mean_reversion_1m.yaml | mean_reversion_1m.regime_thresholds.low_vol_pct |
| MRStrategyOverrideConfig.bb_window | add | None | config/aurora/strategies/mean_reversion_1m.yaml | mean_reversion_1m.strategy_override.bb_window |
| MRStrategyOverrideConfig.bb_num_std | add | None | config/aurora/strategies/mean_reversion_1m.yaml | mean_reversion_1m.strategy_override.bb_num_std |
| MRStrategyOverrideConfig.min_bb_width | add | None | config/aurora/strategies/mean_reversion_1m.yaml | mean_reversion_1m.strategy_override.min_bb_width |
| MRStrategyOverrideConfig.entry_threshold | add | None | config/aurora/strategies/mean_reversion_1m.yaml | mean_reversion_1m.strategy_override.entry_threshold |
| MRStrategyOverrideConfig.tp_to_mid | add | None | config/aurora/strategies/mean_reversion_1m.yaml | mean_reversion_1m.strategy_override.tp_to_mid |
| MRStrategyOverrideConfig.sl_atr_mult | add | None | config/aurora/strategies/mean_reversion_1m.yaml | mean_reversion_1m.strategy_override.sl_atr_mult |
| MRStrategyOverrideConfig.cooldown_sec | add | None | config/aurora/strategies/mean_reversion_1m.yaml | mean_reversion_1m.strategy_override.cooldown_sec |
| MRAssetRiskConfig.position_size_usd | add | None | config/aurora/strategies/mean_reversion_1m.yaml | mean_reversion_1m.asset_risk.position_size_usd |
| MRAssetRiskConfig.max_risk_score | add | None | config/aurora/strategies/mean_reversion_1m.yaml | mean_reversion_1m.asset_risk.max_risk_score |
| MRAssetConfig.enabled | skip | True | config/aurora/strategies/mean_reversion_1m.yaml | mean_reversion_1m.enabled |
| MRAssetConfig.strategy | skip | {'bb_window': 20, 'bb_num_std': 2.0, 'atr_window': 14, 'rsi_window': 14, 'entry_threshold': 0.05, 'rsi_oversold': 30, 'rsi_overbought': 70, 'min_bars': 25, 'min_bb_width': 0.001, 'max_bb_width': 0.05, 'sl_atr_mult': 1.5, 'tp_to_mid': True, 'cooldown_sec': 60} | config/aurora/strategies/mean_reversion_1m.yaml | mean_reversion_1m.strategy |
| MRAssetConfig.risk | skip | {'position_size_usd': 100, 'max_concurrent_positions': 3, 'daily_loss_limit_usd': 50, 'expected_pnl_multiplier': 1.5, 'fees_pct': 0.0004, 'slippage_pct': 0.0002} | config/aurora/strategies/mean_reversion_1m.yaml | mean_reversion_1m.risk |
| MRAssetConfig.bb_window | add | None | config/aurora/strategies/mean_reversion_1m.yaml | mean_reversion_1m.bb_window |
| MRAssetConfig.min_vol_atr | add | None | config/aurora/strategies/mean_reversion_1m.yaml | mean_reversion_1m.min_vol_atr |
| MRAssetConfig.sl_pct | add | None | config/aurora/strategies/mean_reversion_1m.yaml | mean_reversion_1m.sl_pct |
| MRAssetConfig.allowed_regimes | skip | [] | config/aurora/strategies/mean_reversion_1m.yaml | mean_reversion_1m.allowed_regimes |
| MRAssetConfig.position_mode | skip | DYNAMIC | config/aurora/strategies/mean_reversion_1m.yaml | mean_reversion_1m.position_mode |
| MRRegimeSizingConfig.sizing_mult | skip | 1.0 | config/aurora/strategies/mean_reversion_1m.yaml | mean_reversion_1m.regime_sizing.sizing_mult |
| MRRegimeSizingConfig.stop_mult | skip | 1.0 | config/aurora/strategies/mean_reversion_1m.yaml | mean_reversion_1m.regime_sizing.stop_mult |
| MRRegimeSizingConfig.target_mult | skip | 1.0 | config/aurora/strategies/mean_reversion_1m.yaml | mean_reversion_1m.regime_sizing.target_mult |
| MRRiskConfig.position_size_usd | skip | 100 | config/aurora/strategies/mean_reversion_1m.yaml | mean_reversion_1m.risk.position_size_usd |
| MRRiskConfig.max_concurrent_positions | skip | 3 | config/aurora/strategies/mean_reversion_1m.yaml | mean_reversion_1m.risk.max_concurrent_positions |
| MRRiskConfig.daily_loss_limit_usd | skip | 50 | config/aurora/strategies/mean_reversion_1m.yaml | mean_reversion_1m.risk.daily_loss_limit_usd |
| MRRiskConfig.expected_pnl_multiplier | skip | 1.5 | config/aurora/strategies/mean_reversion_1m.yaml | mean_reversion_1m.risk.expected_pnl_multiplier |
| MRRiskConfig.fees_pct | skip | 0.0004 | config/aurora/strategies/mean_reversion_1m.yaml | mean_reversion_1m.risk.fees_pct |
| MRRiskConfig.slippage_pct | skip | 0.0002 | config/aurora/strategies/mean_reversion_1m.yaml | mean_reversion_1m.risk.slippage_pct |
| MeanReversion1mStrategyConfig.model_config | skip | extra=allow | config/aurora/strategies/mean_reversion_1m.yaml | mean_reversion_1m.model_config |
| MeanReversion1mStrategyConfig.enabled | skip | True | config/aurora/strategies/mean_reversion_1m.yaml | mean_reversion_1m.enabled |
| MeanReversion1mStrategyConfig.timeframe_sec | skip | 60 | config/aurora/strategies/mean_reversion_1m.yaml | mean_reversion_1m.timeframe_sec |
| MeanReversion1mStrategyConfig.strategy | skip | {'bb_window': 20, 'bb_num_std': 2.0, 'atr_window': 14, 'rsi_window': 14, 'entry_threshold': 0.05, 'rsi_oversold': 30, 'rsi_overbought': 70, 'min_bars': 25, 'min_bb_width': 0.001, 'max_bb_width': 0.05, 'sl_atr_mult': 1.5, 'tp_to_mid': True, 'cooldown_sec': 60} | config/aurora/strategies/mean_reversion_1m.yaml | mean_reversion_1m.strategy |
| MeanReversion1mStrategyConfig.regime_thresholds | skip | {'high_vol_pct': 0.003, 'low_vol_pct': 0.001} | config/aurora/strategies/mean_reversion_1m.yaml | mean_reversion_1m.regime_thresholds |
| MeanReversion1mStrategyConfig.assets | skip | {'DOGEUSDT': {'enabled': False, 'bb_window': 20, 'min_vol_atr': 0.01, 'sl_pct': 0.0197, 'allowed_regimes': ['FLAT_LOW', 'FLAT_NORMAL', 'FLAT_HIGH']}, 'BTCUSDT': {'enabled': True, 'strategy': {'bb_window': 40, 'bb_num_std': 2.3, 'min_bb_width': 0.006, 'entry_threshold': 0.05, 'tp_to_mid': True, 'cooldown_sec': 0}, 'allowed_regimes': ['FLAT_LOW', 'FLAT_NORMAL'], 'risk': {'position_size_usd': 150}}, 'XRPUSDT': {'enabled': False, 'bb_window': 20, 'min_vol_atr': 0.01, 'sl_pct': 0.0144, 'allowed_regimes': ['FLAT_LOW', 'FLAT_NORMAL', 'FLAT_HIGH']}, 'ETHUSDT': {'enabled': False, 'bb_window': 120, 'min_vol_atr': 0.025, 'sl_pct': 0.0282, 'allowed_regimes': ['FLAT_LOW', 'FLAT_NORMAL', 'FLAT_HIGH']}, 'SOLUSDT': {'enabled': False, 'bb_window': 60, 'min_vol_atr': 0.02, 'sl_pct': 0.0156, 'allowed_regimes': ['FLAT_LOW', 'FLAT_NORMAL', 'FLAT_HIGH']}} | config/aurora/strategies/mean_reversion_1m.yaml | mean_reversion_1m.assets |
| MeanReversion1mStrategyConfig.regime_sizing | skip | {'FLAT_LOW': {'sizing_mult': 0.8, 'stop_mult': 0.6, 'target_mult': 0.8}, 'FLAT_NORMAL': {'sizing_mult': 1.0, 'stop_mult': 1.0, 'target_mult': 1.0}, 'FLAT_HIGH': {'sizing_mult': 0.7, 'stop_mult': 1.5, 'target_mult': 1.2}, 'sizing_mult': 1.0, 'stop_mult': 1.0, 'target_mult': 1.0} | config/aurora/strategies/mean_reversion_1m.yaml | mean_reversion_1m.regime_sizing |
| MeanReversion1mStrategyConfig.allowed_regimes | skip | [] | config/aurora/strategies/mean_reversion_1m.yaml | mean_reversion_1m.allowed_regimes |
| MeanReversion1mStrategyConfig.risk | skip | {'position_size_usd': 100, 'max_concurrent_positions': 3, 'daily_loss_limit_usd': 50, 'expected_pnl_multiplier': 1.5, 'fees_pct': 0.0004, 'slippage_pct': 0.0002} | config/aurora/strategies/mean_reversion_1m.yaml | mean_reversion_1m.risk |
| MeanReversion1mStrategyConfig.emit_trade_intent_directly | skip | True | config/aurora/strategies/mean_reversion_1m.yaml | mean_reversion_1m.emit_trade_intent_directly |
| StrategiesArbitrationLoggingConfig.rejected_why_prefix | skip | ARBITRATION_REJECT | config/aurora/strategies.yaml | strategies_registry.arbitration.logging.rejected_why_prefix |
| StrategiesArbitrationLoggingConfig.log_level | skip | INFO | config/aurora/strategies.yaml | strategies_registry.arbitration.logging.log_level |
| StrategiesArbitrationConfig.mode | skip | priority | config/aurora/strategies.yaml | strategies_registry.arbitration.mode |
| StrategiesArbitrationConfig.priority | skip | {} | config/aurora/strategies.yaml | strategies_registry.arbitration.priority |
| StrategiesArbitrationConfig.logging | skip | {'rejected_why_prefix': 'ARBITRATION_REJECT', 'log_level': 'INFO'} | config/aurora/strategies.yaml | strategies_registry.arbitration.logging |
| StrategiesRegistryConfig.version | skip | 1.0.0 | config/aurora/strategies.yaml | strategies_registry.version |
| StrategiesRegistryConfig.assignments | skip | {} | config/aurora/strategies.yaml | strategies_registry.assignments |
| StrategiesRegistryConfig.arbitration | skip | {'logging': {'rejected_why_prefix': 'ARBITRATION_REJECT', 'log_level': 'INFO'}, 'mode': 'priority', 'priority': {}} | config/aurora/strategies.yaml | strategies_registry.arbitration |
| DecisionModeOverrideConfig.model_config | skip | extra=allow | config/aurora/trading.yaml | trading.decision.mode_override.model_config |
| DecisionModeOverrideConfig.signal_threshold | add | None | config/aurora/trading.yaml | trading.decision.mode_override.signal_threshold |
| DecisionConfig.testnet | add | None | config/aurora/trading.yaml | trading.decision.testnet |
| DecisionConfig.production | add | None | config/aurora/trading.yaml | trading.decision.production |
| DecisionConfig.signal_threshold | skip | 0.1 | config/aurora/trading.yaml | trading.decision.signal_threshold |
| DecisionConfig.cooldown_sec | skip | 10 | config/aurora/trading.yaml | trading.decision.cooldown_sec |
| DecisionConfig.side_bias_min_score | add | None | config/aurora/trading.yaml | trading.decision.side_bias_min_score |
| DecisionConfig.side_bias_penalty_factor | skip | 0.5 | config/aurora/trading.yaml | trading.decision.side_bias_penalty_factor |
| DecisionConfig.side_bias_target_ratio | skip | 0.6 | config/aurora/trading.yaml | trading.decision.side_bias_target_ratio |
| DecisionConfig.side_bias_window_sec | skip | 60 | config/aurora/trading.yaml | trading.decision.side_bias_window_sec |
| DecisionConfig.retry_ttl_ms | skip | 300000 | config/aurora/trading.yaml | trading.decision.retry_ttl_ms |
| DecisionConfig.retry_max_count | skip | 3 | config/aurora/trading.yaml | trading.decision.retry_max_count |
| DecisionConfig.retry_backoff_factor | skip | 2.0 | config/aurora/trading.yaml | trading.decision.retry_backoff_factor |
| DecisionConfig.signal_weights | skip | {'obi': 0.15, 'tfi': 0.15, 'delta_price': 0.1, 'ema_bias': 0.15, 'volume_spike': 0.1, 'volatility_state': 0.1, 'depth_imbalance': 0.15, 'macro_sync': 0.1} | config/aurora/trading.yaml | trading.decision.signal_weights |
| DecisionConfig.signals | skip | {'normalize': True, 'enable_new_metrics': False} | config/aurora/trading.yaml | trading.decision.signals |
| DecisionConfig.position_sizing | skip | {'min_position_size_usd': 10, 'liquidity_based_cap_usd': 10000, 'risk_fraction_q': 0.05, 'liquidity_kappa': 1.0, 'liquidity_kappa_mode': 'dynamic', 'risk_contract_v1': {'enabled': False, 'effective_leverage': 10.0, 'per_symbol_margin_fraction': {'BTCUSDT': 0.04, 'ETHUSDT': 0.055, 'XRPUSDT': 0.04, 'DOGEUSDT': 0.05, 'SOLUSDT': 0.06}, 'fixed_notional_usd': {'BTCUSDT': 200.0, 'ETHUSDT': 250.0, 'XRPUSDT': 200.0, 'DOGEUSDT': 200.0}, 'sol_regime_multipliers': {'calm': 1.5, 'storm': 0.5}, 'model_config': 'extra=allow', 'regime_sizing': {}}, 'kappa_mode': 'passive', 'kelly': {'base_probability': 0.5, 'kelly_cap': 0.25, 'kelly_alpha': 0.8, 'payoff_ratio_r': 1.5}} | config/aurora/trading.yaml | trading.decision.position_sizing |
| DecisionConfig.kelly | skip | {'base_probability': 0.5, 'kelly_cap': 0.25, 'kelly_alpha': 0.8, 'payoff_ratio_r': 1.5} | config/aurora/trading.yaml | trading.decision.kelly |
| DecisionConfig.qos | skip | {'mode': 'defer', 'enforce': False, 'exposure_block_cooldown_sec': 30, 'symbol_cooldown_sec': 1, 'max_intents_per_minute_per_symbol': 60} | config/aurora/trading.yaml | trading.decision.qos |
| DecisionConfig.bar_gating | skip | {'enable': False, 'bar_ms': 'BinOp'} | config/aurora/trading.yaml | trading.decision.bar_gating |
| DecisionConfig.behavior_fsm | skip | {'enable': False, 'high_vol_multiplier': 2.0, 'low_vol_multiplier': 0.5} | config/aurora/trading.yaml | trading.decision.behavior_fsm |
| DecisionConfig.roi_exit | skip | {'enabled': True, 'target_roi_pct': 50.0} | config/aurora/trading.yaml | trading.decision.roi_exit |
| DecisionConfig.mean_reversion | skip | {'enabled': False, 'bb_window': 20, 'bb_std_dev': 2.0, 'min_vol_atr': 0.001, 'allowed_regimes': None} | config/aurora/trading.yaml | trading.decision.mean_reversion |
| DecisionConfig.sizing_modifiers | skip | {'HIGH_VOLATILITY': '0.60', 'LOW_VOLATILITY': '1.20', 'MEAN_REVERSION': '0.50', 'UNCERTAIN': '0.50'} | config/aurora/trading.yaml | trading.decision.sizing_modifiers |
| DecisionConfig.regime_thresholds | skip | {} | config/aurora/trading.yaml | trading.decision.regime_thresholds |
| DecisionConfig.regime_threshold_multipliers | skip | {'HIGH_VOLATILITY': 1.2, 'LOW_VOLATILITY': 0.9, 'MEAN_REVERSION': 1.05, 'TREND_UP': 1.0, 'TREND_DOWN': 1.0, 'UNCERTAIN': 1.15, 'DEFAULT': 1.0} | config/aurora/trading.yaml | trading.decision.regime_threshold_multipliers |
| DecisionConfig.symbols_to_track | skip | ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'DOGEUSDT', 'XRPUSDT'] | config/aurora/trading.yaml | trading.decision.symbols_to_track |
| DecisionConfig.neutral_threshold | skip | 0.18 | config/aurora/trading.yaml | trading.decision.neutral_threshold |
| SLConfig.model_config | skip | extra=allow | config/aurora/trading.yaml | trading.execution.brackets.sl.model_config |
| SLConfig.fixed_bps | skip | 50 | config/aurora/trading.yaml | trading.execution.brackets.sl.fixed_bps |
| TPConfig.model_config | skip | extra=allow | config/aurora/trading.yaml | trading.execution.brackets.tp.model_config |
| TPConfig.fixed_bps | skip | 100 | config/aurora/trading.yaml | trading.execution.brackets.tp.fixed_bps |
| BracketsConfig.model_config | skip | extra=allow | config/aurora/trading.yaml | trading.execution.brackets.model_config |
| BracketsConfig.sl | skip | {'model_config': 'extra=allow', 'fixed_bps': 50} | config/aurora/trading.yaml | trading.execution.brackets.sl |
| BracketsConfig.tp | skip | {'model_config': 'extra=allow', 'fixed_bps': 100} | config/aurora/trading.yaml | trading.execution.brackets.tp |
| BracketsConfig.oco_emulation | skip | False | config/aurora/trading.yaml | trading.execution.brackets.oco_emulation |
| BracketsConfig.stop_loss_bps | skip | 50 | config/aurora/trading.yaml | trading.execution.brackets.stop_loss_bps |
| BracketsConfig.offset_bps | skip | 5 | config/aurora/trading.yaml | trading.execution.brackets.offset_bps |
| EmergencyConfig.enabled | skip | False | config/aurora/trading.yaml | trading.execution.manage.emergency.enabled |
| EmergencyConfig.wait_mode_bars | skip | 2 | config/aurora/trading.yaml | trading.execution.manage.emergency.wait_mode_bars |
| OrphanMonitorConfig.model_config | skip | extra=allow | config/aurora/trading.yaml | trading.execution.manage.orphan_monitor.model_config |
| OrphanMonitorConfig.enabled | skip | True | config/aurora/trading.yaml | trading.execution.manage.orphan_monitor.enabled |
| ManageConfig.brackets | skip | {'enable': True, 'oco_emulation': True, 'stop_loss_bps': 40, 'take_profit_low_ratio': 0.5, 'take_profit_high_ratio': 1.0, 'sl': {'fixed_bps': 40}, 'tp': {'fixed_bps': 80}, 'offset_bps': 5, 'working_type_default': 'MARK_PRICE', 'price_protect': False, 'retry': {'max_attempts': 3, 'backoff_ms': [120, 250, 400], 'fallback_to_limit': True}, 'timeout_sec': 5, 'atomic_close': True, 'bracket_tracking': True} | config/aurora/trading.yaml | trading.execution.manage.brackets |
| ManageConfig.emergency | skip | {'enabled': False, 'wait_mode_bars': 2} | config/aurora/trading.yaml | trading.execution.manage.emergency |
| ManageConfig.auto | skip | True | config/aurora/trading.yaml | trading.execution.manage.auto |
| ManageConfig.orphan_monitor | skip | {'enabled': True, 'run_on_startup': True, 'periodic_interval_sec': 90, 'min_order_age_sec': 0, 'batch_cancel_limit': 50, 'rate_limit_per_min': 120, 'offset_bps': 30, 'model_config': 'extra=allow'} | config/aurora/trading.yaml | trading.execution.manage.orphan_monitor |
| ManageConfig.failsafe | add | None | config/aurora/trading.yaml | trading.execution.manage.failsafe |
| ExposureConfig.max_equity_utilization_pct | skip | 2.0 | config/aurora/trading.yaml | trading.execution.exposure.max_equity_utilization_pct |
| ExposureConfig.max_portfolio_fraction | skip | 2.0 | config/aurora/trading.yaml | trading.execution.exposure.max_portfolio_fraction |
| ExposureConfig.max_side_utilization_pct | skip | {'long': 1.5, 'short': 1.5} | config/aurora/trading.yaml | trading.execution.exposure.max_side_utilization_pct |
| ExposureConfig.max_directional_ratio | skip | 50.0 | config/aurora/trading.yaml | trading.execution.exposure.max_directional_ratio |
| ExposureConfig.per_symbol_cap_pct | skip | 0.08 | config/aurora/trading.yaml | trading.execution.exposure.per_symbol_cap_pct |
| ExposureConfig.pending_ttl_sec | skip | 90 | config/aurora/trading.yaml | trading.execution.exposure.pending_ttl_sec |
| ExposureConfig.pending_reservation_ttl_sec | skip | 45 | config/aurora/trading.yaml | trading.execution.exposure.pending_reservation_ttl_sec |
| ExposureConfig.post_fill_hold_ttl_sec | skip | 30 | config/aurora/trading.yaml | trading.execution.exposure.post_fill_hold_ttl_sec |
| ExposureConfig.positions_stale_ttl_sec | skip | 120 | config/aurora/trading.yaml | trading.execution.exposure.positions_stale_ttl_sec |
| ExposureConfig.leverage_defaults | skip | {'BTCUSDT': 20, 'ETHUSDT': 20, 'SOLUSDT': 20, 'XRPUSDT': 20, 'DOGEUSDT': 20, '__default__': 20} | config/aurora/trading.yaml | trading.execution.exposure.leverage_defaults |
| ExposureConfig.count_pending_orders | skip | True | config/aurora/trading.yaml | trading.execution.exposure.count_pending_orders |
| ExposureConfig.exclude_reduce_only | skip | True | config/aurora/trading.yaml | trading.execution.exposure.exclude_reduce_only |
| WatchdogConfig.ack_ttl_ms | skip | 8000 | config/aurora/trading.yaml | trading.execution.watchdog.ack_ttl_ms |
| WatchdogConfig.fill_ttl_ms | skip | 60000 | config/aurora/trading.yaml | trading.execution.watchdog.fill_ttl_ms |
| WatchdogConfig.check_interval_ms | skip | 1000 | config/aurora/trading.yaml | trading.execution.watchdog.check_interval_ms |
| WatchdogConfig.rps_limit | skip | 10 | config/aurora/trading.yaml | trading.execution.watchdog.rps_limit |
| SMARegimeModelConfig.model_config | skip | extra=allow | config/aurora/regime.yaml | models.sma.model_config |
| SMARegimeModelConfig.sma_short_period | skip | 10 | config/aurora/regime.yaml | models.sma.sma_short_period |
| SMARegimeModelConfig.sma_long_period | skip | 50 | config/aurora/regime.yaml | models.sma.sma_long_period |
| SMARegimeModelConfig.confidence_multiplier | skip | 20.0 | config/aurora/regime.yaml | models.sma.confidence_multiplier |
| SMARegimeModelConfig.confidence_min | skip | 0.5 | config/aurora/regime.yaml | models.sma.confidence_min |
| SMARegimeModelConfig.confidence_max | skip | 0.95 | config/aurora/regime.yaml | models.sma.confidence_max |
| VolatilityRegimeModelConfig.model_config | skip | extra=allow | config/aurora/regime.yaml | models.volatility.model_config |
| VolatilityRegimeModelConfig.enabled | skip | True | config/aurora/regime.yaml | models.volatility.enabled |
| VolatilityRegimeModelConfig.atr_period | skip | 14 | config/aurora/regime.yaml | models.volatility.atr_period |
| VolatilityRegimeModelConfig.atr_sma_length | skip | 100 | config/aurora/regime.yaml | models.volatility.atr_sma_length |
| VolatilityRegimeModelConfig.threshold_multiplier | skip | 2.0 | config/aurora/regime.yaml | models.volatility.threshold_multiplier |
| VolatilityRegimeModelConfig.low_vol_multiplier | skip | 0.5 | config/aurora/regime.yaml | models.volatility.low_vol_multiplier |
| VolatilityRegimeModelConfig.high_vol_confidence_multiplier | skip | 2.0 | config/aurora/regime.yaml | models.volatility.high_vol_confidence_multiplier |
| VolatilityRegimeModelConfig.low_vol_confidence_multiplier | skip | 3.0 | config/aurora/regime.yaml | models.volatility.low_vol_confidence_multiplier |
| MeanReversionRegimeModelConfig.model_config | skip | extra=allow | config/aurora/regime.yaml | models.mean_reversion.model_config |
| MeanReversionRegimeModelConfig.threshold | skip | 0.005 | config/aurora/regime.yaml | models.mean_reversion.threshold |
| MeanReversionRegimeModelConfig.confidence_multiplier | skip | 100.0 | config/aurora/regime.yaml | models.mean_reversion.confidence_multiplier |
| RegimeModelsConfig.sma_trend | skip | {'sma_short_period': 10, 'sma_long_period': 50, 'confidence_multiplier': 20.0, 'confidence_min': 0.5, 'confidence_max': 0.95} | config/aurora/regime.yaml | models.sma_trend |
| RegimeModelsConfig.volatility | skip | {'enabled': True, 'atr_period': 14, 'atr_sma_length': 100, 'threshold_multiplier': 2.0, 'low_vol_multiplier': 0.5, 'high_vol_confidence_multiplier': 2.0, 'low_vol_confidence_multiplier': 3.0, 'model_config': 'extra=allow'} | config/aurora/regime.yaml | models.volatility |
| RegimeModelsConfig.mean_reversion | skip | {'threshold': 0.005, 'confidence_multiplier': 100.0, 'model_config': 'extra=allow'} | config/aurora/regime.yaml | models.mean_reversion |
| RegimeModelConfig.model_config | skip | extra=allow | config/aurora/regime.yaml | models.model_config |
| RegimeModelConfig.confidence_multiplier | skip | 20.0 | config/aurora/regime.yaml | models.confidence_multiplier |
| RegimeModelConfig.confidence_min | skip | 0.5 | config/aurora/regime.yaml | models.confidence_min |
| RegimeModelConfig.confidence_max | skip | 0.95 | config/aurora/regime.yaml | models.confidence_max |
| RegimeDetectorConfig.model_config | skip | extra=allow | config/aurora/regime.yaml | models.model_config |
| RegimeDetectorConfig.models | add | None | config/aurora/regime.yaml | models.models |
| OrdersConfig.model_config | skip | extra=allow | config/aurora/trading.yaml | trading.execution.orders.model_config |
| OrdersConfig.default_ttl_seconds | skip | 15 | config/aurora/trading.yaml | trading.execution.orders.default_ttl_seconds |
| ExecutionConfig.manage | skip | {'auto': True, 'brackets': {'enable': True, 'oco_emulation': True, 'stop_loss_bps': 40, 'take_profit_low_ratio': 0.5, 'take_profit_high_ratio': 1.0, 'sl': {'fixed_bps': 40}, 'tp': {'fixed_bps': 80}, 'offset_bps': 5, 'working_type_default': 'MARK_PRICE', 'price_protect': False, 'retry': {'max_attempts': 3, 'backoff_ms': [120, 250, 400], 'fallback_to_limit': True}, 'timeout_sec': 5, 'atomic_close': True, 'bracket_tracking': True}, 'orphan_monitor': {'enabled': True, 'run_on_startup': True, 'periodic_interval_sec': 90, 'min_order_age_sec': 0, 'batch_cancel_limit': 50, 'rate_limit_per_min': 120, 'offset_bps': 30, 'model_config': 'extra=allow'}, 'emergency': {'enabled': False, 'wait_mode_bars': 2}, 'failsafe': None} | config/aurora/trading.yaml | trading.execution.manage |
| ExecutionConfig.exposure | skip | {'max_equity_utilization_pct': 2.0, 'max_portfolio_fraction': 2.0, 'max_side_utilization_pct': {'long': 1.5, 'short': 1.5}, 'max_directional_ratio': 50.0, 'per_symbol_cap_pct': 0.08, 'count_pending_orders': True, 'exclude_reduce_only': True, 'pending_reservation_ttl_sec': 45, 'leverage_defaults': {'BTCUSDT': 20, 'ETHUSDT': 20, 'SOLUSDT': 20, 'XRPUSDT': 20, 'DOGEUSDT': 20, '__default__': 20}, 'pending_ttl_sec': 90, 'post_fill_hold_ttl_sec': 30, 'positions_stale_ttl_sec': 120} | config/aurora/trading.yaml | trading.execution.exposure |
| ExecutionConfig.watchdog | skip | {'ack_ttl_ms': 8000, 'fill_ttl_ms': 60000, 'check_interval_ms': 1000, 'rps_limit': 10} | config/aurora/trading.yaml | trading.execution.watchdog |
| ExecutionConfig.fallback | add | None | config/aurora/trading.yaml | trading.execution.fallback |
| ExecutionConfig.limit_orders | add | None | config/aurora/trading.yaml | trading.execution.limit_orders |
| ExecutionConfig.orders | skip | {'default_ttl_seconds': 15, 'market': {'slippage_cap_bps': 10}, 'cancel': {'idempotent': True, 'use_cancel_replace': True}, 'model_config': 'extra=allow'} | config/aurora/trading.yaml | trading.execution.orders |
| ExecutionConfig.fsm_periodic_cleanup_enabled | skip | True | config/aurora/trading.yaml | trading.execution.fsm_periodic_cleanup_enabled |
| ExecutionConfig.anti_race_close_ms | skip | 800 | config/aurora/trading.yaml | trading.execution.anti_race_close_ms |
| ExecutionConfig.open_order_type | skip | MARKET | config/aurora/trading.yaml | trading.execution.open_order_type |
| ExecutionConfig.order_params | skip | {'LIMIT': {'timeInForce': 'GTC'}, 'STOP_MARKET': {'workingType': 'MARK_PRICE'}, 'TAKE_PROFIT_MARKET': {'workingType': 'MARK_PRICE'}, 'TRAILING_STOP_MARKET': {'callbackRate': '0.5'}} | config/aurora/trading.yaml | trading.execution.order_params |
| ExecutionConfig.preflight_backoff_ms | add | None | config/aurora/trading.yaml | trading.execution.preflight_backoff_ms |
| ExecutionConfig.min_post_interval_per_symbol_ms | add | None | config/aurora/trading.yaml | trading.execution.min_post_interval_per_symbol_ms |
| ExecutionConfig.allow_trade_with_guardian_tidy_only | add | None | config/aurora/trading.yaml | trading.execution.allow_trade_with_guardian_tidy_only |
| ExecutionConfig.order_guardian | add | None | config/aurora/trading.yaml | trading.execution.order_guardian |
| MacroSyncConfig.enabled | skip | True | config/aurora/trading.yaml | trading.market_data.macro_sync.enabled |
| MacroSyncConfig.anchors | skip | ['BTCUSDT', 'ETHUSDT'] | config/aurora/trading.yaml | trading.market_data.macro_sync.anchors |
| MacroSyncConfig.window | skip | 60 | config/aurora/trading.yaml | trading.market_data.macro_sync.window |
| MacroSyncConfig.emit_abs | skip | False | config/aurora/trading.yaml | trading.market_data.macro_sync.emit_abs |
| MacroSyncConfig.align_mode | skip | strict_len | config/aurora/trading.yaml | trading.market_data.macro_sync.align_mode |
| MacroSyncConfig.min_buffer_size | skip | 10 | config/aurora/trading.yaml | trading.market_data.macro_sync.min_buffer_size |
| MacroSyncConfig.time_diff_threshold_ms | skip | 5000 | config/aurora/trading.yaml | trading.market_data.macro_sync.time_diff_threshold_ms |
| MacroSyncConfig.anchor_update_from_ticks | skip | True | config/aurora/trading.yaml | trading.market_data.macro_sync.anchor_update_from_ticks |
| KlinesConfig.interval | skip | 1m | config/aurora/trading.yaml | trading.market_data.klines.interval |
| KlinesConfig.limit | skip | 2 | config/aurora/trading.yaml | trading.market_data.klines.limit |
| ApiCallLimits.get_recent_trades | skip | 50 | config/aurora/trading.yaml | trading.market_data.api_call_limits.get_recent_trades |
| ApiCallLimits.get_klines | skip | {'interval': '1m', 'limit': 2} | config/aurora/trading.yaml | trading.market_data.api_call_limits.get_klines |
| MarketDataConfig.poll_interval_sec | skip | 5.0 | config/aurora/trading.yaml | trading.market_data.poll_interval_sec |
| MarketDataConfig.use_multiprocessing | skip | True | config/aurora/trading.yaml | trading.market_data.use_multiprocessing |
| MarketDataConfig.websocket_streams | skip | ['bookTicker', 'trade'] | config/aurora/trading.yaml | trading.market_data.websocket_streams |
| MarketDataConfig.api_call_limits | skip | {'get_recent_trades': 50, 'get_klines': {'interval': '1m', 'limit': 2}} | config/aurora/trading.yaml | trading.market_data.api_call_limits |
| MarketDataConfig.macro_sync | skip | {'enabled': True, 'anchors': ['BTCUSDT', 'ETHUSDT'], 'window': 60, 'emit_abs': False, 'align_mode': 'strict_len', 'min_buffer_size': 10, 'time_diff_threshold_ms': 5000, 'anchor_update_from_ticks': True} | config/aurora/trading.yaml | trading.market_data.macro_sync |
| FeatureEngineeringConfig.ema | skip | {'period_short': 3, 'period_long': 7} | config/aurora/domains.yaml | domains.feature_engineering.ema |
| FeatureEngineeringConfig.volume | skip | {'sma_length': 5, 'window_sec': 60, 'min_window_volume_usd': 0.0} | config/aurora/domains.yaml | domains.feature_engineering.volume |
| FeatureEngineeringConfig.volatility | skip | {'sma_length': 10, 'window_sec': 60} | config/aurora/domains.yaml | domains.feature_engineering.volatility |
| FeatureEngineeringConfig.liquidity | skip | {'depth_half': 1000.0, 'kappa_min': 0.3, 'kappa_max': 1.0} | config/aurora/domains.yaml | domains.feature_engineering.liquidity |
| FeatureEngineeringConfig.macro_sync | skip | {'enabled': True, 'time_diff_threshold_ms': 5000, 'min_buffer_size': 3, 'window': 60, 'anchors': None, 'align_mode': 'strict_len', 'anchor_update_from_ticks': True} | config/aurora/domains.yaml | domains.feature_engineering.macro_sync |
| RiskSkewConfig.max_skew_sec | skip | 5 | config/aurora/trading.yaml | trading.decision.risk_skew.max_skew_sec |
| RiskSkewConfig.max_defer_count | skip | 3 | config/aurora/trading.yaml | trading.decision.risk_skew.max_defer_count |
| RiskSkewConfig.defer_cooldown_sec | skip | 2 | config/aurora/trading.yaml | trading.decision.risk_skew.defer_cooldown_sec |
| FeaturesTtlConfig.ttl_sec | skip | 5 | config/aurora/trading.yaml | trading.features_ttl.ttl_sec |
| ArmingConfig.require_regime_warmup | skip | False | config/aurora/trading.yaml | trading.decision.arming.require_regime_warmup |
| ArmingConfig.retry_backoff_ms | skip | 1000 | config/aurora/trading.yaml | trading.decision.arming.retry_backoff_ms |
| ArmingConfig.max_attempts | skip | 120 | config/aurora/trading.yaml | trading.decision.arming.max_attempts |
| DecisionMakingDomainConfig.position_sizing | add | None | config/aurora/domains.yaml | domains.decision_making.position_sizing |
| DecisionMakingDomainConfig.qos | add | None | config/aurora/domains.yaml | domains.decision_making.qos |
| DecisionMakingDomainConfig.features | add | None | config/aurora/domains.yaml | domains.decision_making.features |
| DecisionMakingDomainConfig.bar_gating | add | None | config/aurora/domains.yaml | domains.decision_making.bar_gating |
| DecisionMakingDomainConfig.behavior_fsm | add | None | config/aurora/domains.yaml | domains.decision_making.behavior_fsm |
| DecisionMakingDomainConfig.signals | add | None | config/aurora/domains.yaml | domains.decision_making.signals |
| DecisionMakingDomainConfig.risk_skew | add | None | config/aurora/domains.yaml | domains.decision_making.risk_skew |
| DecisionMakingDomainConfig.arming | add | None | config/aurora/domains.yaml | domains.decision_making.arming |
| EmaConfigDetailed.period_short | skip | 3 | config/aurora/domains.yaml | domains.feature_engineering.ema.period_short |
| EmaConfigDetailed.period_long | skip | 7 | config/aurora/domains.yaml | domains.feature_engineering.ema.period_long |
| VolumeConfigDetailed.sma_length | skip | 5 | config/aurora/domains.yaml | domains.feature_engineering.volume.sma_length |
| VolumeConfigDetailed.window_sec | skip | 60 | config/aurora/domains.yaml | domains.feature_engineering.volume.window_sec |
| VolumeConfigDetailed.min_window_volume_usd | skip | 0.0 | config/aurora/domains.yaml | domains.feature_engineering.volume.min_window_volume_usd |
| VolatilityConfigDetailed.sma_length | skip | 10 | config/aurora/domains.yaml | domains.feature_engineering.volatility.sma_length |
| VolatilityConfigDetailed.window_sec | skip | 60 | config/aurora/domains.yaml | domains.feature_engineering.volatility.window_sec |
| LiquidityConfigDetailed.depth_half | skip | 1000.0 | config/aurora/domains.yaml | domains.feature_engineering.liquidity.depth_half |
| LiquidityConfigDetailed.kappa_min | skip | 0.3 | config/aurora/domains.yaml | domains.feature_engineering.liquidity.kappa_min |
| LiquidityConfigDetailed.kappa_max | skip | 1.0 | config/aurora/domains.yaml | domains.feature_engineering.liquidity.kappa_max |
| EmaBiasConfig.clamp_min | skip | UnaryOp | config/aurora/domains.yaml | domains.feature_engineering.ema_bias.clamp_min |
| EmaBiasConfig.clamp_max | skip | 0.02 | config/aurora/domains.yaml | domains.feature_engineering.ema_bias.clamp_max |
| VolumeSpikeConfig.cap_max | skip | 3.0 | config/aurora/domains.yaml | domains.feature_engineering.volume_spike.cap_max |
| MacroSyncMetricsConfig.enabled | skip | True | config/aurora/domains.yaml | domains.feature_engineering.macro_sync.enabled |
| MacroSyncMetricsConfig.time_diff_threshold_ms | skip | 5000 | config/aurora/domains.yaml | domains.feature_engineering.macro_sync.time_diff_threshold_ms |
| MacroSyncMetricsConfig.min_buffer_size | skip | 3 | config/aurora/domains.yaml | domains.feature_engineering.macro_sync.min_buffer_size |
| MacroSyncMetricsConfig.window | skip | 60 | config/aurora/domains.yaml | domains.feature_engineering.macro_sync.window |
| MacroSyncMetricsConfig.anchors | add | None | config/aurora/domains.yaml | domains.feature_engineering.macro_sync.anchors |
| MacroSyncMetricsConfig.align_mode | skip | strict_len | config/aurora/domains.yaml | domains.feature_engineering.macro_sync.align_mode |
| MacroSyncMetricsConfig.anchor_update_from_ticks | skip | True | config/aurora/domains.yaml | domains.feature_engineering.macro_sync.anchor_update_from_ticks |
| VolatilityStateConfig.cap_max | skip | 3.0 | config/aurora/domains.yaml | domains.feature_engineering.volatility_state.cap_max |
| DepthImbalanceConfig.use_laplace_smoothing | skip | True | config/aurora/domains.yaml | domains.feature_engineering.depth_imbalance.use_laplace_smoothing |
| DeltaPriceConfig.spike_filter_ms | skip | 5000 | config/aurora/domains.yaml | domains.feature_engineering.delta_price.spike_filter_ms |
| FeatureDefaultsConfig.neutral_value | skip | 0.5 | config/aurora/domains.yaml | domains.feature_engineering.defaults.neutral_value |
| FeatureDefaultsConfig.zero_value | skip | 0.0 | config/aurora/domains.yaml | domains.feature_engineering.defaults.zero_value |
| FeatureDefaultsConfig.correlation_default | skip | 0.0 | config/aurora/domains.yaml | domains.feature_engineering.defaults.correlation_default |
| FeatureDefaultsConfig.ms_per_sec | skip | 1000 | config/aurora/domains.yaml | domains.feature_engineering.defaults.ms_per_sec |
| FeatureEngineeringDomainConfig.enable_new_metrics | skip | True | config/aurora/domains.yaml | domains.feature_engineering.enable_new_metrics |
| FeatureEngineeringDomainConfig.volume_input_mode | skip | integrate | config/aurora/domains.yaml | domains.feature_engineering.volume_input_mode |
| FeatureEngineeringDomainConfig.ema | skip | {'period_short': 3, 'period_long': 7} | config/aurora/domains.yaml | domains.feature_engineering.ema |
| FeatureEngineeringDomainConfig.volume | skip | {'sma_length': 5, 'window_sec': 60, 'min_window_volume_usd': 0.0} | config/aurora/domains.yaml | domains.feature_engineering.volume |
| FeatureEngineeringDomainConfig.volatility | skip | {'sma_length': 10, 'window_sec': 60} | config/aurora/domains.yaml | domains.feature_engineering.volatility |
| FeatureEngineeringDomainConfig.liquidity | skip | {'depth_half': 1000.0, 'kappa_min': 0.3, 'kappa_max': 1.0} | config/aurora/domains.yaml | domains.feature_engineering.liquidity |
| FeatureEngineeringDomainConfig.ema_bias | skip | {'clamp_min': 'UnaryOp', 'clamp_max': 0.02} | config/aurora/domains.yaml | domains.feature_engineering.ema_bias |
| FeatureEngineeringDomainConfig.volume_spike | skip | {'cap_max': 3.0} | config/aurora/domains.yaml | domains.feature_engineering.volume_spike |
| FeatureEngineeringDomainConfig.volatility_state | skip | {'cap_max': 3.0} | config/aurora/domains.yaml | domains.feature_engineering.volatility_state |
| FeatureEngineeringDomainConfig.depth_imbalance | skip | {'use_laplace_smoothing': True} | config/aurora/domains.yaml | domains.feature_engineering.depth_imbalance |
| FeatureEngineeringDomainConfig.delta_price | skip | {'spike_filter_ms': 5000} | config/aurora/domains.yaml | domains.feature_engineering.delta_price |
| FeatureEngineeringDomainConfig.macro_sync | skip | {'enabled': True, 'time_diff_threshold_ms': 5000, 'min_buffer_size': 3, 'window': 60, 'anchors': None, 'align_mode': 'strict_len', 'anchor_update_from_ticks': True} | config/aurora/domains.yaml | domains.feature_engineering.macro_sync |
| FeatureEngineeringDomainConfig.defaults | skip | {'neutral_value': 0.5, 'zero_value': 0.0, 'correlation_default': 0.0, 'ms_per_sec': 1000} | config/aurora/domains.yaml | domains.feature_engineering.defaults |
| RiskScoreWeightsConfig.delta_price_pct | skip | 0.1 | config/aurora/trading.yaml | trading.decision.risk_score_weights.delta_price_pct |
| RiskScoreWeightsConfig.obi | skip | 0.3 | config/aurora/trading.yaml | trading.decision.risk_score_weights.obi |
| RiskScoreWeightsConfig.tfi | skip | 0.3 | config/aurora/trading.yaml | trading.decision.risk_score_weights.tfi |
| RiskScoreWeightsConfig.absorption_inverse | skip | 0.3 | config/aurora/trading.yaml | trading.decision.risk_score_weights.absorption_inverse |
| TradingAllowedThresholdsConfig.max_risk_score | skip | 0.8 | config/aurora/trading.yaml | trading.decision.trading_allowed_thresholds.max_risk_score |
| RiskValidationConfig.total_weight_min | skip | 0.5 | config/aurora/trading.yaml | trading.decision.risk_validation.total_weight_min |
| RiskValidationConfig.total_weight_max | skip | 2.0 | config/aurora/trading.yaml | trading.decision.risk_validation.total_weight_max |
| RiskManagementDomainConfig.risk_score_weights | add | None | config/aurora/domains.yaml | domains.risk_management.risk_score_weights |
| RiskManagementDomainConfig.trading_allowed_thresholds | add | None | config/aurora/domains.yaml | domains.risk_management.trading_allowed_thresholds |
| RiskManagementDomainConfig.validation | add | None | config/aurora/domains.yaml | domains.risk_management.validation |
| RiskManagementDomainConfig.use_absorption_penalty | skip | True | config/aurora/domains.yaml | domains.risk_management.use_absorption_penalty |
| PrecisionConfig.quantity_min_threshold | skip | 1e-09 | config/aurora/instruments.yaml | instruments.precision.quantity_min_threshold |
| PrecisionConfig.flat_position_threshold | skip | 1e-12 | config/aurora/instruments.yaml | instruments.precision.flat_position_threshold |
| PrecisionConfig.decimal_places | skip | 2 | config/aurora/instruments.yaml | instruments.precision.decimal_places |
| ThreadTimeoutsConfig.join_timeout_sec | skip | 10 | config/aurora/domains.yaml | domains.account_observer.thread_timeouts.join_timeout_sec |
| PositionTrackingDomainConfig.precision | add | None | config/aurora/domains.yaml | domains.position_tracking.precision |
| PositionTrackingDomainConfig.thread_timeouts | add | None | config/aurora/domains.yaml | domains.position_tracking.thread_timeouts |
| PositionTrackingDomainConfig.positions_stale_ttl_sec | skip | 15 | config/aurora/domains.yaml | domains.position_tracking.positions_stale_ttl_sec |
| PositionTrackingDomainConfig.enable_market_tick_subscription | skip | False | config/aurora/domains.yaml | domains.position_tracking.enable_market_tick_subscription |
| AccountObserverDomainConfig.poll_interval_sec | skip | 5 | config/aurora/domains.yaml | domains.account_observer.poll_interval_sec |
| AccountObserverDomainConfig.trade_limit | skip | 10 | config/aurora/domains.yaml | domains.account_observer.trade_limit |
| AccountObserverDomainConfig.symbols | skip | [] | config/aurora/domains.yaml | domains.account_observer.symbols |
| AccountObserverDomainConfig.thread_timeouts | skip | {'join_timeout_sec': 10} | config/aurora/domains.yaml | domains.account_observer.thread_timeouts |
| ExposureGuardConfig.pending_ttl_sec | skip | 90 | config/aurora/trading.yaml | trading.execution.exposure_guard.pending_ttl_sec |
| ExposureGuardConfig.post_fill_ttl_sec | skip | 5 | config/aurora/trading.yaml | trading.execution.exposure_guard.post_fill_ttl_sec |
| ExposureGuardConfig.stale_ttl_sec | skip | 5 | config/aurora/trading.yaml | trading.execution.exposure_guard.stale_ttl_sec |
| ExposureGuardConfig.max_equity_utilization_pct | skip | 0.2 | config/aurora/trading.yaml | trading.execution.exposure_guard.max_equity_utilization_pct |
| ExposureGuardConfig.max_portfolio_fraction | skip | 0.2 | config/aurora/trading.yaml | trading.execution.exposure_guard.max_portfolio_fraction |
| ExposureGuardConfig.max_long_utilization_pct | skip | 0.2 | config/aurora/trading.yaml | trading.execution.exposure_guard.max_long_utilization_pct |
| ExposureGuardConfig.max_short_utilization_pct | skip | 0.2 | config/aurora/trading.yaml | trading.execution.exposure_guard.max_short_utilization_pct |
| ExposureGuardConfig.max_directional_ratio | skip | 2.0 | config/aurora/trading.yaml | trading.execution.exposure_guard.max_directional_ratio |
| ExposureGuardConfig.max_concentration_pct | skip | 0.1 | config/aurora/trading.yaml | trading.execution.exposure_guard.max_concentration_pct |
| ExposureGuardConfig.pending_timeout_sec | skip | 5 | config/aurora/trading.yaml | trading.execution.exposure_guard.pending_timeout_sec |
| FsmOpenConfig.idempotency_window_sec | skip | 60 | config/aurora/trading.yaml | trading.execution.fsm_open.idempotency_window_sec |
| OrderIndexConfig.ttl_sec | skip | 3600 | config/aurora/trading.yaml | trading.execution.order_index.ttl_sec |
| MetricsCollectorConfig.window_size_minutes | skip | 60 | config/aurora/trading.yaml | trading.execution.metrics_collector.window_size_minutes |
| MetricsCollectorConfig.recent_rejections_minutes | skip | 5 | config/aurora/trading.yaml | trading.execution.metrics_collector.recent_rejections_minutes |
| IdempotentCancelConfig.max_retries | skip | 2 | config/aurora/trading.yaml | trading.execution.idempotent_cancel.max_retries |
| ExecutionUtilsConfig.client_order_id_max_length | skip | 32 | config/aurora/trading.yaml | trading.execution.utils.client_order_id_max_length |
| ExecutionUtilsConfig.basis_points_base | skip | 10000.0 | config/aurora/trading.yaml | trading.execution.utils.basis_points_base |
| ExecutionPositionDomainConfig.watchdog | add | None | config/aurora/domains.yaml | domains.execution_position.watchdog |
| ExecutionPositionDomainConfig.exposure_guard | add | None | config/aurora/domains.yaml | domains.execution_position.exposure_guard |
| ExecutionPositionDomainConfig.fsm_open | add | None | config/aurora/domains.yaml | domains.execution_position.fsm_open |
| ExecutionPositionDomainConfig.order_index | add | None | config/aurora/domains.yaml | domains.execution_position.order_index |
| ExecutionPositionDomainConfig.metrics_collector | add | None | config/aurora/domains.yaml | domains.execution_position.metrics_collector |
| ExecutionPositionDomainConfig.idempotent_cancel | add | None | config/aurora/domains.yaml | domains.execution_position.idempotent_cancel |
| ExecutionPositionDomainConfig.utils | add | None | config/aurora/domains.yaml | domains.execution_position.utils |
| DomainsConfig.decision_making | skip | {'position_sizing': None, 'qos': None, 'features': None, 'bar_gating': None, 'behavior_fsm': None, 'signals': None, 'risk_skew': None, 'arming': None} | config/aurora/domains.yaml | domains.decision_making |
| DomainsConfig.feature_engineering | skip | {'ema': {'period_short': 3, 'period_long': 7}, 'volume': {'sma_length': 5, 'window_sec': 60, 'min_window_volume_usd': 0.0}, 'volatility': {'sma_length': 10, 'window_sec': 60}, 'liquidity': {'depth_half': 1000.0, 'kappa_min': 0.3, 'kappa_max': 1.0}, 'macro_sync': {'enabled': True, 'time_diff_threshold_ms': 5000, 'min_buffer_size': 3, 'window': 60, 'anchors': None, 'align_mode': 'strict_len', 'anchor_update_from_ticks': True}, 'ema_bias': {'clamp_min': 'UnaryOp', 'clamp_max': 0.02}, 'volume_spike': {'cap_max': 3.0}, 'volatility_state': {'cap_max': 3.0}, 'depth_imbalance': {'use_laplace_smoothing': True}, 'delta_price': {'spike_filter_ms': 5000}, 'defaults': {'neutral_value': 0.5, 'zero_value': 0.0, 'correlation_default': 0.0, 'ms_per_sec': 1000}, 'enable_new_metrics': True, 'volume_input_mode': 'integrate'} | config/aurora/domains.yaml | domains.feature_engineering |
| DomainsConfig.risk_management | skip | {'risk_score_weights': None, 'trading_allowed_thresholds': None, 'validation': None, 'use_absorption_penalty': True} | config/aurora/domains.yaml | domains.risk_management |
| DomainsConfig.position_tracking | skip | {'precision': None, 'thread_timeouts': None, 'positions_stale_ttl_sec': 15, 'enable_market_tick_subscription': False} | config/aurora/domains.yaml | domains.position_tracking |
| DomainsConfig.account_observer | skip | {'thread_timeouts': {'join_timeout_sec': 10}, 'poll_interval_sec': 5, 'trade_limit': 10, 'symbols': []} | config/aurora/domains.yaml | domains.account_observer |
| DomainsConfig.execution_position | skip | {'watchdog': None, 'exposure_guard': None, 'fsm_open': None, 'order_index': None, 'metrics_collector': None, 'idempotent_cancel': None, 'utils': None} | config/aurora/domains.yaml | domains.execution_position |
| AuroraSideBiasConfig.model_config | skip | extra=allow | config/aurora/aurora_instruments.yaml | aurora_instruments.side_bias.model_config |
| AuroraSideBiasConfig.penalty_factor | add | None | config/aurora/aurora_instruments.yaml | aurora_instruments.side_bias.penalty_factor |
| AuroraSideBiasConfig.window_sec | add | None | config/aurora/aurora_instruments.yaml | aurora_instruments.side_bias.window_sec |
| AuroraSideBiasConfig.target_ratio | add | None | config/aurora/aurora_instruments.yaml | aurora_instruments.side_bias.target_ratio |
| AuroraExitConfig.model_config | skip | extra=allow | config/aurora/aurora_instruments.yaml | aurora_instruments.exit.model_config |
| AuroraExitConfig.sl_pct | add | None | config/aurora/aurora_instruments.yaml | aurora_instruments.exit.sl_pct |
| AuroraExitConfig.max_hold_sec | add | None | config/aurora/aurora_instruments.yaml | aurora_instruments.exit.max_hold_sec |
| AuroraTakeProfitConfig.model_config | skip | extra=allow | config/aurora/aurora_instruments.yaml | aurora_instruments.take_profit.model_config |
| AuroraTakeProfitConfig.tp_low_ratio | add | None | config/aurora/aurora_instruments.yaml | aurora_instruments.take_profit.tp_low_ratio |
| AuroraTakeProfitConfig.tp_high_ratio | add | None | config/aurora/aurora_instruments.yaml | aurora_instruments.take_profit.tp_high_ratio |
| AuroraTakeProfitConfig.partial_exit_pct | add | None | config/aurora/aurora_instruments.yaml | aurora_instruments.take_profit.partial_exit_pct |
| AuroraTrailingStopConfig.model_config | skip | extra=allow | config/aurora/aurora_instruments.yaml | aurora_instruments.trailing_stop.model_config |
| AuroraTrailingStopConfig.enabled | add | None | config/aurora/aurora_instruments.yaml | aurora_instruments.trailing_stop.enabled |
| AuroraTrailingStopConfig.activation_pct | add | None | config/aurora/aurora_instruments.yaml | aurora_instruments.trailing_stop.activation_pct |
| AuroraTrailingStopConfig.trail_pct | add | None | config/aurora/aurora_instruments.yaml | aurora_instruments.trailing_stop.trail_pct |
| AuroraTrailingStopConfig.min_update_interval_sec | skip | 5 | config/aurora/aurora_instruments.yaml | aurora_instruments.trailing_stop.min_update_interval_sec |
| AuroraExecutionConfig.model_config | skip | extra=allow | config/aurora/aurora_instruments.yaml | aurora_instruments.execution.model_config |
| AuroraExecutionConfig.order_type | add | None | config/aurora/aurora_instruments.yaml | aurora_instruments.execution.order_type |
| AuroraExecutionConfig.post_only | add | None | config/aurora/aurora_instruments.yaml | aurora_instruments.execution.post_only |
| AuroraExecutionConfig.max_slippage_bps | add | None | config/aurora/aurora_instruments.yaml | aurora_instruments.execution.max_slippage_bps |
| EmaClampConfig.enabled | skip | False | config/aurora/trading.yaml | trading.decision.ema_clamp.enabled |
| EmaClampConfig.clamp_min | add | None | config/aurora/trading.yaml | trading.decision.ema_clamp.clamp_min |
| EmaClampConfig.clamp_max | add | None | config/aurora/trading.yaml | trading.decision.ema_clamp.clamp_max |
| SignalThresholdConfig.enabled | add | False | config/aurora/trading.yaml | trading.decision.signal_threshold.enabled |
| SignalThresholdConfig.value | add | None | config/aurora/trading.yaml | trading.decision.signal_threshold.value |
| MaxRiskScoreConfig.enabled | add | False | config/aurora/trading.yaml | trading.decision.max_risk_score.enabled |
| MaxRiskScoreConfig.value | add | None | config/aurora/trading.yaml | trading.decision.max_risk_score.value |
| AuroraInstrumentConfig.enabled | add | True | config/aurora/aurora_instruments.yaml | aurora_instruments.enabled |
| AuroraInstrumentConfig.weights | add | None | config/aurora/aurora_instruments.yaml | aurora_instruments.weights |
| AuroraInstrumentConfig.side_bias | skip | {'model_config': 'extra=allow', 'penalty_factor': None, 'window_sec': None, 'target_ratio': None} | config/aurora/aurora_instruments.yaml | aurora_instruments.side_bias |
| AuroraInstrumentConfig.position_mode | add | DYNAMIC | config/aurora/aurora_instruments.yaml | aurora_instruments.position_mode |
| AuroraInstrumentConfig.regime_thresholds | add | None | config/aurora/aurora_instruments.yaml | aurora_instruments.regime_thresholds |
| AuroraInstrumentConfig.regime_sizing | add | None | config/aurora/aurora_instruments.yaml | aurora_instruments.regime_sizing |
| AuroraInstrumentConfig.exit | skip | {'model_config': 'extra=allow', 'sl_pct': None, 'max_hold_sec': None} | config/aurora/aurora_instruments.yaml | aurora_instruments.exit |
| AuroraInstrumentConfig.take_profit | skip | {'model_config': 'extra=allow', 'tp_low_ratio': None, 'tp_high_ratio': None, 'partial_exit_pct': None} | config/aurora/aurora_instruments.yaml | aurora_instruments.take_profit |
| AuroraInstrumentConfig.trailing_stop | skip | {'model_config': 'extra=allow', 'enabled': None, 'activation_pct': None, 'trail_pct': None, 'min_update_interval_sec': 5} | config/aurora/aurora_instruments.yaml | aurora_instruments.trailing_stop |
| AuroraInstrumentConfig.execution | skip | {'model_config': 'extra=allow', 'order_type': None, 'post_only': None, 'max_slippage_bps': None} | config/aurora/aurora_instruments.yaml | aurora_instruments.execution |
| AuroraInstrumentConfig.ema_clamp | add | None | config/aurora/aurora_instruments.yaml | aurora_instruments.ema_clamp |
| AuroraInstrumentConfig.signal_threshold | add | None | config/aurora/aurora_instruments.yaml | aurora_instruments.signal_threshold |
| AuroraInstrumentConfig.max_risk_score | add | None | config/aurora/aurora_instruments.yaml | aurora_instruments.max_risk_score |
| AuroraInstrumentConfig.cooldown_sec | add | None | config/aurora/aurora_instruments.yaml | aurora_instruments.cooldown_sec |
| AuroraInstrumentConfig.allowed_regimes | add | None | config/aurora/aurora_instruments.yaml | aurora_instruments.allowed_regimes |
| AuroraInstrumentConfig.timeframe_sec | add | None | config/aurora/aurora_instruments.yaml | aurora_instruments.timeframe_sec |
| AuroraInstrumentConfig.position_mode | skip | DYNAMIC | config/aurora/aurora_instruments.yaml | aurora_instruments.position_mode |
| OpsConfig.model_config | add | extra=allow | config/aurora/system.yaml | ops.model_config |
| OpsConfig.panic_killswitch | add | False | config/aurora/system.yaml | ops.panic_killswitch |
| OpsConfig.panic_ttl_sec | add | None | config/aurora/system.yaml | ops.panic_ttl_sec |
| OpsConfig.quiet_hours_utc | add | [] | config/aurora/system.yaml | ops.quiet_hours_utc |
| OpsConfig.allowlist_symbols | add | [] | config/aurora/system.yaml | ops.allowlist_symbols |
| OpsConfig.metrics_url | add | http://127.0.0.1:8000/metrics | config/aurora/system.yaml | ops.metrics_url |
| OpsConfig.reports_dir | add | reports | config/aurora/system.yaml | ops.reports_dir |
| DomainModeConfig.model_config | add | extra=allow | config/aurora/domains.yaml | domains.mode.model_config |
| DomainModeConfig.trading_mode | add | Field(Ellipsis, description="Trading mode for this domain: 'live' or 'testnet'") | config/aurora/domains.yaml | domains.mode.trading_mode |
| DomainConfigurationConfig.model_config | add | extra=allow | config/aurora/domains.yaml | domains.configuration.model_config |
| DomainConfigurationConfig.market_data | add | None | config/aurora/domains.yaml | domains.configuration.market_data |
| DomainConfigurationConfig.feature_engineering | add | None | config/aurora/domains.yaml | domains.configuration.feature_engineering |
| DomainConfigurationConfig.decision_making | add | None | config/aurora/domains.yaml | domains.configuration.decision_making |
| DomainConfigurationConfig.risk_management | add | None | config/aurora/domains.yaml | domains.configuration.risk_management |
| DomainConfigurationConfig.execution_position | add | None | config/aurora/domains.yaml | domains.configuration.execution_position |
| DomainConfigurationConfig.audit_trail | add | None | config/aurora/domains.yaml | domains.configuration.audit_trail |
| TradingConfig.mode | skip | testnet | config/aurora/trading.yaml | trading.mode |
| TradingConfig.decision | skip | {'signal_threshold': {'enabled': False, 'value': None}, 'neutral_threshold': 0.18, 'symbols_to_track': ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'DOGEUSDT', 'XRPUSDT'], 'behavior_fsm': {'enable': False, 'high_vol_multiplier': 2.0, 'low_vol_multiplier': 0.5}, 'regime_threshold_multipliers': {'HIGH_VOLATILITY': 1.2, 'LOW_VOLATILITY': 0.9, 'MEAN_REVERSION': 1.05, 'TREND_UP': 1.0, 'TREND_DOWN': 1.0, 'UNCERTAIN': 1.15, 'DEFAULT': 1.0}, 'side_bias_window_sec': 60, 'side_bias_target_ratio': 0.6, 'side_bias_penalty_factor': 0.5, 'cooldown_sec': 10, 'position_sizing': {'min_position_size_usd': 10, 'liquidity_based_cap_usd': 10000, 'risk_fraction_q': 0.05, 'liquidity_kappa': 1.0, 'liquidity_kappa_mode': 'dynamic', 'risk_contract_v1': {'enabled': False, 'effective_leverage': 10.0, 'per_symbol_margin_fraction': {'BTCUSDT': 0.04, 'ETHUSDT': 0.055, 'XRPUSDT': 0.04, 'DOGEUSDT': 0.05, 'SOLUSDT': 0.06}, 'fixed_notional_usd': {'BTCUSDT': 200.0, 'ETHUSDT': 250.0, 'XRPUSDT': 200.0, 'DOGEUSDT': 200.0}, 'sol_regime_multipliers': {'calm': 1.5, 'storm': 0.5}, 'model_config': 'extra=allow', 'regime_sizing': {}}, 'kappa_mode': 'passive', 'kelly': {'base_probability': 0.5, 'kelly_cap': 0.25, 'kelly_alpha': 0.8, 'payoff_ratio_r': 1.5}}, 'sizing_modifiers': {'HIGH_VOLATILITY': '0.60', 'LOW_VOLATILITY': '1.20', 'MEAN_REVERSION': '0.50', 'UNCERTAIN': '0.50'}, 'kelly': {'base_probability': 0.5, 'kelly_cap': 0.25, 'kelly_alpha': 0.8, 'payoff_ratio_r': 1.5}, 'qos': {'mode': 'defer', 'enforce': False, 'exposure_block_cooldown_sec': 30, 'symbol_cooldown_sec': 1, 'max_intents_per_minute_per_symbol': 60}, 'signal_weights': {'obi': 0.15, 'tfi': 0.15, 'delta_price': 0.1, 'ema_bias': 0.15, 'volume_spike': 0.1, 'volatility_state': 0.1, 'depth_imbalance': 0.15, 'macro_sync': 0.1}, 'bar_gating': {'enable': False, 'bar_ms': 'BinOp'}, 'signals': {'normalize': True, 'enable_new_metrics': False}, 'regime_sizing': {'enabled': False, 'low_vol_multiplier': 1.0, 'high_vol_multiplier': 1.0}, 'roi_exit': {'enabled': True, 'target_roi_pct': 50.0}, 'mean_reversion': {'enabled': False, 'bb_window': 20, 'bb_std_dev': 2.0, 'min_vol_atr': 0.001, 'allowed_regimes': None}, 'mode_override': {'model_config': 'extra=allow', 'signal_threshold': None}, 'testnet': None, 'production': None, 'side_bias_min_score': None, 'retry_ttl_ms': 300000, 'retry_max_count': 3, 'retry_backoff_factor': 2.0, 'regime_thresholds': {}, 'risk_skew': {'max_skew_sec': 5, 'max_defer_count': 3, 'defer_cooldown_sec': 2}, 'arming': {'require_regime_warmup': False, 'retry_backoff_ms': 1000, 'max_attempts': 120}, 'risk_score_weights': {'delta_price_pct': 0.1, 'obi': 0.3, 'tfi': 0.3, 'absorption_inverse': 0.3}, 'trading_allowed_thresholds': {'max_risk_score': 0.8}, 'risk_validation': {'total_weight_min': 0.5, 'total_weight_max': 2.0}, 'ema_clamp': {'enabled': False, 'clamp_min': None, 'clamp_max': None}, 'max_risk_score': {'enabled': False, 'value': None}} | config/aurora/trading.yaml | trading.decision |
| TradingConfig.execution | skip | {'manage': {'auto': True, 'brackets': {'enable': True, 'oco_emulation': True, 'stop_loss_bps': 40, 'take_profit_low_ratio': 0.5, 'take_profit_high_ratio': 1.0, 'sl': {'fixed_bps': 40}, 'tp': {'fixed_bps': 80}, 'offset_bps': 5, 'working_type_default': 'MARK_PRICE', 'price_protect': False, 'retry': {'max_attempts': 3, 'backoff_ms': [120, 250, 400], 'fallback_to_limit': True}, 'timeout_sec': 5, 'atomic_close': True, 'bracket_tracking': True}, 'orphan_monitor': {'enabled': True, 'run_on_startup': True, 'periodic_interval_sec': 90, 'min_order_age_sec': 0, 'batch_cancel_limit': 50, 'rate_limit_per_min': 120, 'offset_bps': 30, 'model_config': 'extra=allow'}, 'emergency': {'enabled': False, 'wait_mode_bars': 2}, 'failsafe': None}, 'exposure': {'max_equity_utilization_pct': 2.0, 'max_portfolio_fraction': 2.0, 'max_side_utilization_pct': {'long': 1.5, 'short': 1.5}, 'max_directional_ratio': 50.0, 'per_symbol_cap_pct': 0.08, 'count_pending_orders': True, 'exclude_reduce_only': True, 'pending_reservation_ttl_sec': 45, 'leverage_defaults': {'BTCUSDT': 20, 'ETHUSDT': 20, 'SOLUSDT': 20, 'XRPUSDT': 20, 'DOGEUSDT': 20, '__default__': 20}, 'pending_ttl_sec': 90, 'post_fill_hold_ttl_sec': 30, 'positions_stale_ttl_sec': 120}, 'open_order_type': 'MARKET', 'order_params': {'LIMIT': {'timeInForce': 'GTC'}, 'STOP_MARKET': {'workingType': 'MARK_PRICE'}, 'TAKE_PROFIT_MARKET': {'workingType': 'MARK_PRICE'}, 'TRAILING_STOP_MARKET': {'callbackRate': '0.5'}}, 'watchdog': {'ack_ttl_ms': 8000, 'fill_ttl_ms': 60000, 'check_interval_ms': 1000, 'rps_limit': 10}, 'orders': {'default_ttl_seconds': 15, 'market': {'slippage_cap_bps': 10}, 'cancel': {'idempotent': True, 'use_cancel_replace': True}, 'model_config': 'extra=allow'}, 'failsafe': {'max_hold_sec': 86400}, 'brackets': {'sl': {'model_config': 'extra=allow', 'fixed_bps': 50}, 'tp': {'model_config': 'extra=allow', 'fixed_bps': 100}, 'model_config': 'extra=allow', 'oco_emulation': False, 'stop_loss_bps': 50, 'offset_bps': 5}, 'fallback': None, 'limit_orders': None, 'fsm_periodic_cleanup_enabled': True, 'anti_race_close_ms': 800, 'preflight_backoff_ms': None, 'min_post_interval_per_symbol_ms': None, 'allow_trade_with_guardian_tidy_only': None, 'order_guardian': None, 'exposure_guard': {'pending_ttl_sec': 90, 'post_fill_ttl_sec': 5, 'stale_ttl_sec': 5, 'max_equity_utilization_pct': 0.2, 'max_portfolio_fraction': 0.2, 'max_long_utilization_pct': 0.2, 'max_short_utilization_pct': 0.2, 'max_directional_ratio': 2.0, 'max_concentration_pct': 0.1, 'pending_timeout_sec': 5}, 'fsm_open': {'idempotency_window_sec': 60}, 'order_index': {'ttl_sec': 3600}, 'metrics_collector': {'window_size_minutes': 60, 'recent_rejections_minutes': 5}, 'idempotent_cancel': {'max_retries': 2}, 'utils': {'client_order_id_max_length': 32, 'basis_points_base': 10000.0}} | config/aurora/trading.yaml | trading.execution |
| TradingConfig.instruments | add | {} | config/aurora/trading.yaml | trading.instruments |
| TradingConfig.aurora_instruments | add | {} | config/aurora/trading.yaml | trading.aurora_instruments |
| TradingConfig.symbols_to_track | add | [] | config/aurora/trading.yaml | trading.symbols_to_track |
| TradingConfig.market_data | skip | {'poll_interval_sec': 5.0, 'websocket_streams': ['bookTicker', 'trade'], 'use_multiprocessing': True, 'api_call_limits': {'get_recent_trades': 50, 'get_klines': {'interval': '1m', 'limit': 2}}, 'macro_sync': {'enabled': True, 'anchors': ['BTCUSDT', 'ETHUSDT'], 'window': 60, 'emit_abs': False, 'align_mode': 'strict_len', 'min_buffer_size': 10, 'time_diff_threshold_ms': 5000, 'anchor_update_from_ticks': True}, 'klines': {'interval': '1m', 'limit': 2}} | config/aurora/trading.yaml | trading.market_data |
| TradingConfig.feature_engineering | add | None | config/aurora/trading.yaml | trading.feature_engineering |
| TradingConfig.domains | add | None | config/aurora/trading.yaml | trading.domains |
| TradingConfig.risk | skip | {'max_daily_drawdown_limit': 0.05, 'score_weights': {'delta_price': 0.05, 'obi': 0.35, 'tfi': 0.35, 'absorption_inverse': 0.25}, 'testnet': {'max_risk_score': 0.9}, 'production': {'max_risk_score': 0.8}, 'trading_allowed_thresholds': {'max_risk_score': 0.9}, 'daily': {'max_realized_loss_usd': 250.0, 'max_drawdown_pct': 8.0, 'reset_time_utc': '00:00'}, 'profile': 'balanced', 'soft_limits': {'mode': 'clip', 'clip_min_notional_usdt': 10, 'directional_ratio_max': 20.0, 'side_exposure_usdt': 600, 'margin_exposure_usdt': 1100}, 'regime_adaptation': {'trend_up_delta': 0.3, 'trend_down_delta': 0.3, 'flat_delta': -0.3, 'bounds': [2.0, 4.0]}, 'feature_flags': {'dynamic_ratio': True, 'clipping_enabled': True}, 'enable_new_metrics': True, 'compute_all': True} | config/aurora/trading.yaml | trading.risk |
| TradingConfig.tca_prefs | skip | {'max_slippage_pct': 0.5, 'preferred_venue': 'binance', 'execution_priority': 'speed'} | config/aurora/trading.yaml | trading.tca_prefs |
| TradingConfig.risk_budgets | skip | {'max_portfolio_risk_pct': 5.0, 'max_single_position_risk_pct': 1.0, 'max_daily_loss_pct': 2.0} | config/aurora/trading.yaml | trading.risk_budgets |
| TradingConfig.risk_management | skip | {'data_sources': {'portfolio_state': 'testnet', 'market_data': 'live'}} | config/aurora/trading.yaml | trading.risk_management |
| TradingConfig.ops | skip | {'panic_killswitch': True, 'quiet_hours_utc': ['22:00-06:00'], 'allowlist_symbols': []} | config/aurora/trading.yaml | trading.ops |
| TradingConfig.domain_configuration | skip | {'market_data': {'trading_mode': 'live'}, 'decision_making': {'trading_mode': 'live'}, 'risk_management': {'trading_mode': 'testnet'}, 'execution_position': {'trading_mode': 'testnet'}, 'audit_trail': {'trading_mode': 'live'}} | config/aurora/trading.yaml | trading.domain_configuration |
| BinanceApiEnv.api_key | add | None | config/aurora/trading.yaml | binance_api.env.api_key |
| BinanceApiEnv.api_secret | add | None | config/aurora/trading.yaml | binance_api.env.api_secret |
| BinanceApiEnv.rest_url | add | None | config/aurora/trading.yaml | binance_api.env.rest_url |
| BinanceApiEnv.ws_url | add | None | config/aurora/trading.yaml | binance_api.env.ws_url |
| BinanceApiConfig.live | skip | {'api_key': '${BINANCE_FUTURES_API_KEY_LIVE}', 'api_secret': '${BINANCE_FUTURES_API_SECRET_LIVE}', 'rest_url': '${BINANCE_FUTURES_BASE_URL_LIVE}', 'ws_url': 'wss://fstream.binance.com'} | config/aurora/trading.yaml | binance_api.live |
| BinanceApiConfig.testnet | skip | {'api_key': '${BINANCE_TESTNET_API_KEY}', 'api_secret': '${BINANCE_TESTNET_API_SECRET}', 'rest_url': 'https://testnet.binancefuture.com', 'ws_url': 'wss://stream.testnet.binancefuture.com'} | config/aurora/trading.yaml | binance_api.testnet |
| RetrySchedulerConfig.max_attempts | add | Field(Ellipsis, description='Max retry attempts for deferred intents') | config/aurora/trading.yaml | trading.execution.retry_scheduler.max_attempts |
| RetrySchedulerConfig.min_retry_delay_ms | add | Field(Ellipsis, description='Minimum retry delay (ms)') | config/aurora/trading.yaml | trading.execution.retry_scheduler.min_retry_delay_ms |
| BridgeConfig.retry_scheduler | skip | {'max_attempts': 5, 'min_retry_delay_ms': 500} | config/aurora/system.yaml | bridge.retry_scheduler |
| RiskManagementDataSourcesConfig.market_data | add | Field(Ellipsis) | config/aurora/domains.yaml | domains.risk_management.data_sources.market_data |
| RiskManagementDataSourcesConfig.portfolio_state | add | Field(Ellipsis) | config/aurora/domains.yaml | domains.risk_management.data_sources.portfolio_state |
| TradingRiskManagementConfig.data_sources | add | Field(Ellipsis) | config/aurora/domains.yaml | domains.risk_management.trading.data_sources |
| AccountObserverConfig.model_config | add | extra=allow | config/aurora/domains.yaml | domains.account_observer.model_config |
| AccountObserverConfig.poll_interval | add | 30 | config/aurora/domains.yaml | domains.account_observer.poll_interval |
| LoggingConfig.model_config | add | extra=allow | config/aurora/system.yaml | system.logging.model_config |
| LoggingConfig.level | add | INFO | config/aurora/system.yaml | system.logging.level |
| LoggingConfig.file | add | logs/aurora_core.log | config/aurora/system.yaml | system.logging.file |
| LoggingConfig.format | add | json | config/aurora/system.yaml | system.logging.format |
| LoggingConfig.rotation | add | None | config/aurora/system.yaml | system.logging.rotation |
| SystemMarketDataConfig.model_config | add | extra=allow | config/aurora/system.yaml | system.market_data.model_config |
| SystemMarketDataConfig.queue_maxsize | add | Field(Ellipsis, description='Max size of IPC queue (worker → proxy)') | config/aurora/system.yaml | system.market_data.queue_maxsize |
| SystemMarketDataConfig.local_queue_maxsize | add | Field(Ellipsis, description='Max size of local queue (proxy internal)') | config/aurora/system.yaml | system.market_data.local_queue_maxsize |
| SystemMarketDataConfig.emit_workers | add | Field(Ellipsis, description='Thread pool size for non-blocking FSM.emit()') | config/aurora/system.yaml | system.market_data.emit_workers |
| SystemMarketDataConfig.tick_ttl_ms | add | Field(Ellipsis, description='Max age of tick data in ms — older ticks are DROPPED') | config/aurora/system.yaml | system.market_data.tick_ttl_ms |
| SystemConfig.model_config | add | extra=allow | config/aurora/system.yaml | system.model_config |
| SystemConfig.logging | skip | {'model_config': 'extra=allow', 'level': 'INFO', 'file': 'logs/aurora_core.log', 'format': 'json', 'rotation': None} | config/aurora/system.yaml | system.logging |
| SystemConfig.market_data | skip | {'model_config': 'extra=allow', 'queue_maxsize': "Field(Ellipsis, description='Max size of IPC queue (worker → proxy)')", 'local_queue_maxsize': "Field(Ellipsis, description='Max size of local queue (proxy internal)')", 'emit_workers': "Field(Ellipsis, description='Thread pool size for non-blocking FSM.emit()')", 'tick_ttl_ms': "Field(Ellipsis, description='Max age of tick data in ms — older ticks are DROPPED')"} | config/aurora/system.yaml | system.market_data |
| SystemRuntimeMeta.config_name | add | None | config/aurora/system.yaml | system.runtime_meta.config_name |
| SystemRuntimeMeta.config_dir | add | None | config/aurora/system.yaml | system.runtime_meta.config_dir |
| SystemMetaConfig.system_config_version | add | None | config/aurora/system.yaml | system.meta.system_config_version |
| SystemMetaConfig.regime_config_version | add | None | config/aurora/system.yaml | system.meta.regime_config_version |
| SystemMetaConfig.sequential_tests | add | {} | config/aurora/system.yaml | system.meta.sequential_tests |
| SystemMetaConfig.risk_core | add | {} | config/aurora/system.yaml | system.meta.risk_core |
| SystemMetaConfig.kelly | add | {} | config/aurora/system.yaml | system.meta.kelly |
| SystemMetaConfig.calibrator | add | {} | config/aurora/system.yaml | system.meta.calibrator |
| SystemMetaConfig.hawkes | add | {} | config/aurora/system.yaml | system.meta.hawkes |
| SystemMetaConfig.hotreload_whitelist | add | [] | config/aurora/system.yaml | system.meta.hotreload_whitelist |
| SystemMetaConfig.hardening | add | {} | config/aurora/system.yaml | system.meta.hardening |
| SystemMetaConfig.position_tracking | add | {} | config/aurora/system.yaml | system.meta.position_tracking |
| SystemMetaConfig.runtime | add | None | config/aurora/system.yaml | system.meta.runtime |
| AuroraConfig.trading_mode | skip | hybrid_live_data_testnet_exec | config/aurora/system.yaml | trading_mode |
| AuroraConfig.trading | skip | {'symbols_to_track': ['SOLUSDT', 'ETHUSDT', 'DOGEUSDT', 'XRPUSDT', 'BTCUSDT'], 'market_data': {'websocket_streams': ['bookTicker', 'trade']}} | config/aurora/system.yaml | trading |
| AuroraConfig.binance_api | add | None | config/aurora/system.yaml | binance_api |
| AuroraConfig.account_observer | skip | {'poll_interval': 5, 'symbols': ['SOLUSDT', 'ETHUSDT', 'DOGEUSDT', 'XRPUSDT', 'BTCUSDT'], 'trade_limit': 50} | config/aurora/system.yaml | account_observer |
| AuroraConfig.system | skip | {'logging': {'model_config': 'extra=allow', 'level': 'INFO', 'file': 'logs/aurora_core.log', 'format': 'json', 'rotation': None}, 'market_data': {'model_config': 'extra=allow', 'queue_maxsize': "Field(Ellipsis, description='Max size of IPC queue (worker → proxy)')", 'local_queue_maxsize': "Field(Ellipsis, description='Max size of local queue (proxy internal)')", 'emit_workers': "Field(Ellipsis, description='Thread pool size for non-blocking FSM.emit()')", 'tick_ttl_ms': "Field(Ellipsis, description='Max age of tick data in ms — older ticks are DROPPED')"}, 'model_config': 'extra=allow', 'runtime_meta': {'config_name': None, 'config_dir': None}, 'meta': {'system_config_version': None, 'regime_config_version': None, 'sequential_tests': {}, 'risk_core': {}, 'kelly': {}, 'calibrator': {}, 'hawkes': {}, 'hotreload_whitelist': [], 'hardening': {}, 'position_tracking': {}, 'runtime': None}} | config/aurora/system.yaml | system |
| AuroraConfig.system_meta | add | None | config/aurora/system.yaml | system_meta |
| AuroraConfig.ops | skip | {'model_config': 'extra=allow', 'panic_killswitch': False, 'panic_ttl_sec': None, 'quiet_hours_utc': [], 'allowlist_symbols': [], 'metrics_url': 'http://127.0.0.1:8000/metrics', 'reports_dir': 'reports'} | config/aurora/system.yaml | ops |
| AuroraConfig.bridge | skip | {'retry_scheduler': {'max_attempts': 5, 'min_retry_delay_ms': 500}} | config/aurora/system.yaml | bridge |
| AuroraConfig.domains | add | None | config/aurora/system.yaml | domains |
| AuroraConfig.instruments | add | {} | config/aurora/system.yaml | instruments |
| AuroraConfig.aurora_instruments | add | {} | config/aurora/system.yaml | aurora_instruments |
| AuroraConfig.strategies_registry | add | None | config/aurora/system.yaml | strategies_registry |
| AuroraConfig.mean_reversion_1m | add | None | config/aurora/system.yaml | mean_reversion_1m |
| AuroraConfig.decision | add | None | config/aurora/system.yaml | decision |
| AuroraConfig.execution | add | None | config/aurora/system.yaml | execution |
| AuroraConfig.brackets | add | None | config/aurora/system.yaml | brackets |
| AuroraConfig.trailing | add | {} | config/aurora/system.yaml | trailing |
| AuroraConfig.models | add | None | config/aurora/system.yaml | models |
| AuroraConfig.logging | skip | {'level': 'DEBUG', 'file': 'logs/aurora_core.log', 'format': 'json', 'rotation': {'max_bytes': 10485760, 'backup_count': 5}} | config/aurora/system.yaml | logging |
| AuroraConfig.hmm | add | None | config/aurora/system.yaml | hmm |
| AuroraConfig.features | add | None | config/aurora/system.yaml | features |
| AuroraConfig.hotreload_whitelist | skip | ['sequential_tests.wald.mu1', 'sequential_tests.glr.min_samples', 'kelly.fraction_cap', 'hawkes.update_interval_ms', 'hawkes.window_ms', 'hawkes.eta_max'] | config/aurora/system.yaml | hotreload_whitelist |
| AuroraConfig.aurora | add | None | config/aurora/system.yaml | aurora |
| AuroraConfig.runtime | add | None | config/aurora/system.yaml | runtime |

Summary: 149 to add, 340 already exist
