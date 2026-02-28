#!/usr/bin/env python3
"""
Generate Config Default Path Mapping

Auto-generates tools/config_default_path_map.yaml based on inventory and heuristics.
"""

import json
import yaml
from pathlib import Path
from typing import Dict


def generate_mapping(inventory_file: Path) -> Dict[str, Dict[str, str]]:
    """Generate mapping based on heuristics."""
    with open(inventory_file, 'r', encoding='utf-8') as f:
        inventory = json.load(f)
    
    mapping = {}
    
    for item in inventory:
        key = f"{item['class']}.{item['field']}"
        
        # Heuristics for file and path
        file_path, yaml_path = infer_location(item['class'], item['field'])
        
        if file_path and yaml_path:
            mapping[key] = {
                'file': file_path,
                'path': yaml_path
            }
    
    return mapping


def infer_location(class_name: str, field_name: str) -> tuple[str, str]:
    """Infer YAML file and path based on class and field."""
    
    # Base mappings
    file_map = {
        'AuroraConfig': 'config/aurora/system.yaml',
        'TradingConfig': 'config/aurora/trading.yaml',
        'DecisionConfig': 'config/aurora/trading.yaml',
        'ExecutionConfig': 'config/aurora/trading.yaml',
        'DomainsConfig': 'config/aurora/domains.yaml',
        'DecisionMakingDomainConfig': 'config/aurora/domains.yaml',
        'FeatureEngineeringDomainConfig': 'config/aurora/domains.yaml',
        'RiskManagementDomainConfig': 'config/aurora/domains.yaml',
        'PositionTrackingDomainConfig': 'config/aurora/domains.yaml',
        # NOTE: AccountObserverDomainConfig removed (TASK-ACCOUNT-OBSERVER-REACHABILITY-DELETE-01)
        'ExecutionPositionDomainConfig': 'config/aurora/domains.yaml',
        'SystemConfig': 'config/aurora/system.yaml',
        'OpsConfig': 'config/aurora/system.yaml',
        # NOTE: BridgeConfig removed (BRIDGE-SUNSET-01)
        'BinanceApiConfig': 'config/aurora/trading.yaml',
        'StrategiesRegistryConfig': 'config/aurora/strategies.yaml',
        'MeanReversion1mStrategyConfig': 'config/aurora/strategies/mean_reversion.yaml',
        'RegimeDetectorConfig': 'config/aurora/regime.yaml',
        'RegimeModelsConfig': 'config/aurora/regime.yaml',
        'AuroraInstrumentConfig': 'config/aurora/aurora_instruments.yaml',
        'InstrumentPrecisionSpec': 'config/aurora/instruments.yaml',
        'InstrumentSpec': 'config/aurora/instruments.yaml',
        # Additional classes from errors
        'SignalWeights': 'config/aurora/trading.yaml',
        'BarGatingConfig': 'config/aurora/trading.yaml',
        'BehaviorFsmConfig': 'config/aurora/trading.yaml',
        'SignalsConfig': 'config/aurora/trading.yaml',
        'RegimeSizingSymbolConfig': 'config/aurora/trading.yaml',
        'RiskContractV1Config': 'config/aurora/trading.yaml',
        'PositionSizingConfig': 'config/aurora/trading.yaml',
        'KellyConfig': 'config/aurora/trading.yaml',
        'QosConfig': 'config/aurora/trading.yaml',
        'ROIExitConfig': 'config/aurora/trading.yaml',
        'FailsafeConfig': 'config/aurora/trading.yaml',
        'MeanReversionConfig': 'config/aurora/trading.yaml',
        'MRStrategyParamsConfig': 'config/aurora/strategies/mean_reversion.yaml',
        'MRRegimeThresholdsConfig': 'config/aurora/strategies/mean_reversion.yaml',
        'MRStrategyOverrideConfig': 'config/aurora/strategies/mean_reversion.yaml',
        'MRAssetRiskConfig': 'config/aurora/strategies/mean_reversion.yaml',
        'MRAssetConfig': 'config/aurora/strategies/mean_reversion.yaml',
        'MRRegimeSizingConfig': 'config/aurora/strategies/mean_reversion.yaml',
        'MRRiskConfig': 'config/aurora/strategies/mean_reversion.yaml',
        'StrategiesArbitrationLoggingConfig': 'config/aurora/strategies.yaml',
        'StrategiesArbitrationConfig': 'config/aurora/strategies.yaml',
        'DecisionModeOverrideConfig': 'config/aurora/trading.yaml',
        'SLConfig': 'config/aurora/trading.yaml',
        'TPConfig': 'config/aurora/trading.yaml',
        'BracketsConfig': 'config/aurora/trading.yaml',
        'EmergencyConfig': 'config/aurora/trading.yaml',
        'OrphanMonitorConfig': 'config/aurora/trading.yaml',
        'ManageConfig': 'config/aurora/trading.yaml',
        'ExposureConfig': 'config/aurora/trading.yaml',
        'WatchdogConfig': 'config/aurora/trading.yaml',
        'SMARegimeModelConfig': 'config/aurora/regime.yaml',
        'VolatilityRegimeModelConfig': 'config/aurora/regime.yaml',
        'MeanReversionRegimeModelConfig': 'config/aurora/regime.yaml',
        'RegimeModelConfig': 'config/aurora/regime.yaml',
        'OrdersConfig': 'config/aurora/trading.yaml',
        'MacroSyncConfig': 'config/aurora/trading.yaml',
        'KlinesConfig': 'config/aurora/trading.yaml',
        'ApiCallLimits': 'config/aurora/trading.yaml',
        'MarketDataConfig': 'config/aurora/trading.yaml',
        'FeatureEngineeringConfig': 'config/aurora/domains.yaml',
        'RiskSkewConfig': 'config/aurora/trading.yaml',
        'FeaturesTtlConfig': 'config/aurora/trading.yaml',
        'ArmingConfig': 'config/aurora/trading.yaml',
        'EmaConfigDetailed': 'config/aurora/domains.yaml',
        'VolumeConfigDetailed': 'config/aurora/domains.yaml',
        'VolatilityConfigDetailed': 'config/aurora/domains.yaml',
        'LiquidityConfigDetailed': 'config/aurora/domains.yaml',
        'EmaBiasConfig': 'config/aurora/domains.yaml',
        'VolumeSpikeConfig': 'config/aurora/domains.yaml',
        'MacroSyncMetricsConfig': 'config/aurora/domains.yaml',
        'VolatilityStateConfig': 'config/aurora/domains.yaml',
        'DepthImbalanceConfig': 'config/aurora/domains.yaml',
        'DeltaPriceConfig': 'config/aurora/domains.yaml',
        'FeatureDefaultsConfig': 'config/aurora/domains.yaml',
        'RiskScoreWeightsConfig': 'config/aurora/trading.yaml',
        'TradingAllowedThresholdsConfig': 'config/aurora/trading.yaml',
        'RiskValidationConfig': 'config/aurora/trading.yaml',
        'PrecisionConfig': 'config/aurora/instruments.yaml',
        'ThreadTimeoutsConfig': 'config/aurora/domains.yaml',
        'ExposureGuardConfig': 'config/aurora/trading.yaml',
        'FsmOpenConfig': 'config/aurora/trading.yaml',
        'OrderIndexConfig': 'config/aurora/trading.yaml',
        'MetricsCollectorConfig': 'config/aurora/trading.yaml',
        'IdempotentCancelConfig': 'config/aurora/trading.yaml',
        'ExecutionUtilsConfig': 'config/aurora/trading.yaml',
        'AuroraSideBiasConfig': 'config/aurora/aurora_instruments.yaml',
        'AuroraExitConfig': 'config/aurora/aurora_instruments.yaml',
        'AuroraTakeProfitConfig': 'config/aurora/aurora_instruments.yaml',
        'AuroraTrailingStopConfig': 'config/aurora/aurora_instruments.yaml',
        'AuroraExecutionConfig': 'config/aurora/aurora_instruments.yaml',
        'EmaClampConfig': 'config/aurora/trading.yaml',
        'SignalThresholdConfig': 'config/aurora/trading.yaml',
        'MaxRiskScoreConfig': 'config/aurora/trading.yaml',
        'DomainModeConfig': 'config/aurora/domains.yaml',
        'DomainConfigurationConfig': 'config/aurora/domains.yaml',
        'BinanceApiEnv': 'config/aurora/trading.yaml',
        'RetrySchedulerConfig': 'config/aurora/trading.yaml',
        'RiskManagementDataSourcesConfig': 'config/aurora/domains.yaml',
        'TradingRiskManagementConfig': 'config/aurora/domains.yaml',
        'AccountObserverConfig': 'config/aurora/domains.yaml',
        'LoggingConfig': 'config/aurora/system.yaml',
        'SystemMarketDataConfig': 'config/aurora/system.yaml',
        'SystemRuntimeMeta': 'config/aurora/system.yaml',
        'SystemMetaConfig': 'config/aurora/system.yaml',
    }
    
    file_path = file_map.get(class_name, None)
    if not file_path:
        return None, None
    
    # For path, usually the field name, but for nested, adjust
    if class_name == 'AuroraConfig':
        if field_name in ['trading_mode', 'system', 'system_meta', 'ops', 'bridge', 'logging', 'hmm', 'features', 'hotreload_whitelist', 'aurora', 'runtime']:
            yaml_path = field_name
        elif field_name in ['trading', 'binance_api', 'account_observer', 'decision', 'execution', 'brackets', 'trailing']:
            yaml_path = field_name
        elif field_name in ['domains', 'instruments', 'aurora_instruments', 'strategies_registry', 'mean_reversion', 'models']:
            yaml_path = field_name
        else:
            yaml_path = field_name
    elif class_name == 'TradingConfig':
        yaml_path = f"trading.{field_name}"
    elif class_name == 'DecisionConfig':
        yaml_path = f"trading.decision.{field_name}"
    elif class_name == 'ExecutionConfig':
        yaml_path = f"trading.execution.{field_name}"
    elif class_name == 'DomainsConfig':
        yaml_path = f"domains.{field_name}"
    elif class_name == 'DecisionMakingDomainConfig':
        yaml_path = f"domains.decision_making.{field_name}"
    elif class_name == 'FeatureEngineeringDomainConfig':
        yaml_path = f"domains.feature_engineering.{field_name}"
    elif class_name == 'RiskManagementDomainConfig':
        yaml_path = f"domains.risk_management.{field_name}"
    elif class_name == 'PositionTrackingDomainConfig':
        yaml_path = f"domains.position_tracking.{field_name}"
    # NOTE: AccountObserverDomainConfig removed (TASK-ACCOUNT-OBSERVER-REACHABILITY-DELETE-01)
    elif class_name == 'ExecutionPositionDomainConfig':
        yaml_path = f"domains.execution_position.{field_name}"
    elif class_name == 'SystemConfig':
        yaml_path = f"system.{field_name}"
    elif class_name == 'OpsConfig':
        yaml_path = f"ops.{field_name}"
    # NOTE: BridgeConfig removed (BRIDGE-SUNSET-01)
    elif class_name == 'BinanceApiConfig':
        yaml_path = f"binance_api.{field_name}"
    elif class_name == 'StrategiesRegistryConfig':
        yaml_path = f"strategies_registry.{field_name}"
    elif class_name == 'MeanReversion1mStrategyConfig':
        yaml_path = f"mean_reversion.{field_name}"
    elif class_name == 'RegimeDetectorConfig':
        yaml_path = f"models.{field_name}"
    elif class_name == 'RegimeModelsConfig':
        yaml_path = f"models.{field_name}"
    elif class_name == 'AuroraInstrumentConfig':
        yaml_path = f"aurora_instruments.{field_name}"
    elif class_name == 'InstrumentPrecisionSpec':
        yaml_path = f"instruments.{field_name}"
    elif class_name == 'InstrumentSpec':
        yaml_path = f"instruments.{field_name}"
    elif class_name == 'SignalWeights':
        yaml_path = f"trading.decision.signal_weights.{field_name}"
    elif class_name == 'BarGatingConfig':
        yaml_path = f"trading.decision.bar_gating.{field_name}"
    elif class_name == 'BehaviorFsmConfig':
        yaml_path = f"trading.decision.behavior_fsm.{field_name}"
    elif class_name == 'SignalsConfig':
        yaml_path = f"trading.decision.signals.{field_name}"
    elif class_name == 'RegimeSizingSymbolConfig':
        yaml_path = f"trading.decision.regime_sizing.{field_name}"
    elif class_name == 'RiskContractV1Config':
        yaml_path = f"trading.decision.position_sizing.risk_contract_v1.{field_name}"
    elif class_name == 'PositionSizingConfig':
        yaml_path = f"trading.decision.position_sizing.{field_name}"
    elif class_name == 'KellyConfig':
        yaml_path = f"trading.decision.position_sizing.kelly.{field_name}"
    elif class_name == 'QosConfig':
        yaml_path = f"trading.decision.qos.{field_name}"
    elif class_name == 'ROIExitConfig':
        yaml_path = f"trading.decision.roi_exit.{field_name}"
    elif class_name == 'FailsafeConfig':
        yaml_path = f"trading.execution.failsafe.{field_name}"
    elif class_name == 'MeanReversionConfig':
        yaml_path = f"trading.decision.mean_reversion.{field_name}"
    elif class_name == 'MRStrategyParamsConfig':
        yaml_path = f"mean_reversion.strategy.{field_name}"
    elif class_name == 'MRRegimeThresholdsConfig':
        yaml_path = f"mean_reversion.regime_thresholds.{field_name}"
    elif class_name == 'MRStrategyOverrideConfig':
        yaml_path = f"mean_reversion.strategy_override.{field_name}"
    elif class_name == 'MRAssetRiskConfig':
        yaml_path = f"mean_reversion.asset_risk.{field_name}"
    elif class_name == 'MRAssetConfig':
        yaml_path = f"mean_reversion.{field_name}"
    elif class_name == 'MRRegimeSizingConfig':
        yaml_path = f"mean_reversion.regime_sizing.{field_name}"
    elif class_name == 'MRRiskConfig':
        yaml_path = f"mean_reversion.risk.{field_name}"
    elif class_name == 'StrategiesArbitrationLoggingConfig':
        yaml_path = f"strategies_registry.arbitration.logging.{field_name}"
    elif class_name == 'StrategiesArbitrationConfig':
        yaml_path = f"strategies_registry.arbitration.{field_name}"
    elif class_name == 'DecisionModeOverrideConfig':
        yaml_path = f"trading.decision.mode_override.{field_name}"
    elif class_name == 'SLConfig':
        yaml_path = f"trading.execution.brackets.sl.{field_name}"
    elif class_name == 'TPConfig':
        yaml_path = f"trading.execution.brackets.tp.{field_name}"
    elif class_name == 'BracketsConfig':
        yaml_path = f"trading.execution.brackets.{field_name}"
    elif class_name == 'EmergencyConfig':
        yaml_path = f"trading.execution.manage.emergency.{field_name}"
    elif class_name == 'OrphanMonitorConfig':
        yaml_path = f"trading.execution.manage.orphan_monitor.{field_name}"
    elif class_name == 'ManageConfig':
        yaml_path = f"trading.execution.manage.{field_name}"
    elif class_name == 'ExposureConfig':
        yaml_path = f"trading.execution.exposure.{field_name}"
    elif class_name == 'WatchdogConfig':
        yaml_path = f"trading.execution.watchdog.{field_name}"
    elif class_name == 'SMARegimeModelConfig':
        yaml_path = f"models.sma.{field_name}"
    elif class_name == 'VolatilityRegimeModelConfig':
        yaml_path = f"models.volatility.{field_name}"
    elif class_name == 'MeanReversionRegimeModelConfig':
        yaml_path = f"models.mean_reversion.{field_name}"
    elif class_name == 'RegimeModelConfig':
        yaml_path = f"models.{field_name}"
    elif class_name == 'OrdersConfig':
        yaml_path = f"trading.execution.orders.{field_name}"
    elif class_name == 'MacroSyncConfig':
        yaml_path = f"trading.market_data.macro_sync.{field_name}"
    elif class_name == 'KlinesConfig':
        yaml_path = f"trading.market_data.klines.{field_name}"
    elif class_name == 'ApiCallLimits':
        yaml_path = f"trading.market_data.api_call_limits.{field_name}"
    elif class_name == 'MarketDataConfig':
        yaml_path = f"trading.market_data.{field_name}"
    elif class_name == 'FeatureEngineeringConfig':
        yaml_path = f"domains.feature_engineering.{field_name}"
    elif class_name == 'RiskSkewConfig':
        yaml_path = f"trading.decision.risk_skew.{field_name}"
    elif class_name == 'FeaturesTtlConfig':
        yaml_path = f"trading.features_ttl.{field_name}"
    elif class_name == 'ArmingConfig':
        yaml_path = f"trading.decision.arming.{field_name}"
    elif class_name == 'EmaConfigDetailed':
        yaml_path = f"domains.feature_engineering.ema.{field_name}"
    elif class_name == 'VolumeConfigDetailed':
        yaml_path = f"domains.feature_engineering.volume.{field_name}"
    elif class_name == 'VolatilityConfigDetailed':
        yaml_path = f"domains.feature_engineering.volatility.{field_name}"
    elif class_name == 'LiquidityConfigDetailed':
        yaml_path = f"domains.feature_engineering.liquidity.{field_name}"
    elif class_name == 'EmaBiasConfig':
        yaml_path = f"domains.feature_engineering.ema_bias.{field_name}"
    elif class_name == 'VolumeSpikeConfig':
        yaml_path = f"domains.feature_engineering.volume_spike.{field_name}"
    elif class_name == 'MacroSyncMetricsConfig':
        yaml_path = f"domains.feature_engineering.macro_sync.{field_name}"
    elif class_name == 'VolatilityStateConfig':
        yaml_path = f"domains.feature_engineering.volatility_state.{field_name}"
    elif class_name == 'DepthImbalanceConfig':
        yaml_path = f"domains.feature_engineering.depth_imbalance.{field_name}"
    elif class_name == 'DeltaPriceConfig':
        yaml_path = f"domains.feature_engineering.delta_price.{field_name}"
    elif class_name == 'FeatureDefaultsConfig':
        yaml_path = f"domains.feature_engineering.defaults.{field_name}"
    elif class_name == 'RiskScoreWeightsConfig':
        yaml_path = f"trading.decision.risk_score_weights.{field_name}"
    elif class_name == 'TradingAllowedThresholdsConfig':
        yaml_path = f"trading.decision.trading_allowed_thresholds.{field_name}"
    elif class_name == 'RiskValidationConfig':
        yaml_path = f"trading.decision.risk_validation.{field_name}"
    elif class_name == 'PrecisionConfig':
        yaml_path = f"instruments.precision.{field_name}"
    elif class_name == 'ThreadTimeoutsConfig':
        yaml_path = f"domains.account_observer.thread_timeouts.{field_name}"
    elif class_name == 'ExposureGuardConfig':
        yaml_path = f"trading.execution.exposure_guard.{field_name}"
    elif class_name == 'FsmOpenConfig':
        yaml_path = f"trading.execution.fsm_open.{field_name}"
    elif class_name == 'OrderIndexConfig':
        yaml_path = f"trading.execution.order_index.{field_name}"
    elif class_name == 'MetricsCollectorConfig':
        yaml_path = f"trading.execution.metrics_collector.{field_name}"
    elif class_name == 'IdempotentCancelConfig':
        yaml_path = f"trading.execution.idempotent_cancel.{field_name}"
    elif class_name == 'ExecutionUtilsConfig':
        yaml_path = f"trading.execution.utils.{field_name}"
    elif class_name == 'AuroraSideBiasConfig':
        yaml_path = f"aurora_instruments.side_bias.{field_name}"
    elif class_name == 'AuroraExitConfig':
        yaml_path = f"aurora_instruments.exit.{field_name}"
    elif class_name == 'AuroraTakeProfitConfig':
        yaml_path = f"aurora_instruments.take_profit.{field_name}"
    elif class_name == 'AuroraTrailingStopConfig':
        yaml_path = f"aurora_instruments.trailing_stop.{field_name}"
    elif class_name == 'AuroraExecutionConfig':
        yaml_path = f"aurora_instruments.execution.{field_name}"
    elif class_name == 'EmaClampConfig':
        yaml_path = f"trading.decision.ema_clamp.{field_name}"
    elif class_name == 'SignalThresholdConfig':
        yaml_path = f"trading.decision.signal_threshold.{field_name}"
    elif class_name == 'MaxRiskScoreConfig':
        yaml_path = f"trading.decision.max_risk_score.{field_name}"
    elif class_name == 'DomainModeConfig':
        yaml_path = f"domains.mode.{field_name}"
    elif class_name == 'DomainConfigurationConfig':
        yaml_path = f"domains.configuration.{field_name}"
    elif class_name == 'BinanceApiEnv':
        yaml_path = f"binance_api.env.{field_name}"
    elif class_name == 'RetrySchedulerConfig':
        yaml_path = f"trading.execution.retry_scheduler.{field_name}"
    elif class_name == 'RiskManagementDataSourcesConfig':
        yaml_path = f"domains.risk_management.data_sources.{field_name}"
    elif class_name == 'TradingRiskManagementConfig':
        yaml_path = f"domains.risk_management.trading.{field_name}"
    elif class_name == 'AccountObserverConfig':
        yaml_path = f"domains.account_observer.{field_name}"
    elif class_name == 'LoggingConfig':
        yaml_path = f"system.logging.{field_name}"
    elif class_name == 'SystemMarketDataConfig':
        yaml_path = f"system.market_data.{field_name}"
    elif class_name == 'SystemRuntimeMeta':
        yaml_path = f"system.runtime_meta.{field_name}"
    elif class_name == 'SystemMetaConfig':
        yaml_path = f"system.meta.{field_name}"
    else:
        # For other classes, assume they are nested somewhere
        yaml_path = field_name
    
    return file_path, yaml_path


def main():
    inventory_file = Path('reports/TASK20_defaults_inventory.json')
    mapping_file = Path('tools/config_default_path_map.yaml')
    
    if not inventory_file.exists():
        print(f"Inventory file not found: {inventory_file}")
        return
    
    mapping = generate_mapping(inventory_file)
    
    with open(mapping_file, 'w', encoding='utf-8') as f:
        yaml.dump(mapping, f, default_flow_style=False, sort_keys=True)
    
    print(f"Generated mapping with {len(mapping)} entries: {mapping_file}")


if __name__ == '__main__':
    main()