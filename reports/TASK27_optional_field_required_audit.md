# TASK27.1 — Optional / Field(required) Audit

Goal: confirm/disprove *real* “Optional + Field() ⇒ required” failures on current code + current `config/aurora/*` YAML (post-TASK21 autofill).

## Findings (code, no assumptions)
- Found `104` fields where annotation is `Optional[...]` **and** Pydantic marks them as **required** (`Field(...)`/`Field()` with no default).
- Of those, `62` are **reachable** in the currently-loaded config (we can delete the key from `model_dump()` using the repo `tools/config_default_path_map.yaml` path mapping and re-validate).
- For every reachable required-Optional field tested, deleting the key causes validation to fail (`ValidationError`). This confirms the *trap exists* in the models.
- No startup failure observed for the repo’s current config: `from apps.reference.config_loader import get_config; get_config()` succeeds.

## Evidence: Optional fields declared without defaults
- Example: `apps/reference/config_models.py:1490` (`domains: Optional[DomainsConfig] = Field(...)`)
- Example: `apps/reference/config_models.py:1522` (`aurora: Optional[Dict[str, Any]] = Field(...)`)
- Example: `apps/reference/config_models.py:1503` (`mean_reversion: Optional[...] = Field(...)`)

## Table (reachable required-Optional fields in current config)

| model.field | optional | default | present_in_yaml | validation_passes | evidence |
|---|---:|---|---:|---:|---|
| `AuroraConfig.aurora` | yes | `PydanticUndefined` | no | no | `config/aurora/system.yaml :: aurora (missing)` |
| `AuroraConfig.domains` | yes | `PydanticUndefined` | no | no | `config/aurora/system.yaml :: domains (missing)` |
| `AuroraConfig.mean_reversion` | yes | `PydanticUndefined` | no | no | `config/aurora/system.yaml :: mean_reversion (missing)` |
| `AuroraConfig.models` | yes | `PydanticUndefined` | no | no | `config/aurora/system.yaml :: models (missing)` |
| `AuroraConfig.strategies_registry` | yes | `PydanticUndefined` | no | no | `config/aurora/system.yaml :: strategies_registry (missing)` |
| `AuroraInstrumentConfig.allowed_regimes` | yes | `PydanticUndefined` | no | no | `config/aurora/aurora_instruments.yaml :: aurora_instruments.allowed_regimes (missing)` |
| `AuroraInstrumentConfig.cooldown_sec` | yes | `PydanticUndefined` | no | no | `config/aurora/aurora_instruments.yaml :: aurora_instruments.cooldown_sec (missing)` |
| `AuroraInstrumentConfig.ema_clamp` | yes | `PydanticUndefined` | no | no | `config/aurora/aurora_instruments.yaml :: aurora_instruments.ema_clamp (missing)` |
| `AuroraInstrumentConfig.execution` | yes | `PydanticUndefined` | no | no | `config/aurora/aurora_instruments.yaml :: aurora_instruments.execution (missing)` |
| `AuroraInstrumentConfig.exit` | yes | `PydanticUndefined` | no | no | `config/aurora/aurora_instruments.yaml :: aurora_instruments.exit (missing)` |
| `AuroraInstrumentConfig.max_risk_score` | yes | `PydanticUndefined` | no | no | `config/aurora/aurora_instruments.yaml :: aurora_instruments.max_risk_score (missing)` |
| `AuroraInstrumentConfig.regime_sizing` | yes | `PydanticUndefined` | no | no | `config/aurora/aurora_instruments.yaml :: aurora_instruments.regime_sizing (missing)` |
| `AuroraInstrumentConfig.regime_thresholds` | yes | `PydanticUndefined` | no | no | `config/aurora/aurora_instruments.yaml :: aurora_instruments.regime_thresholds (missing)` |
| `AuroraInstrumentConfig.side_bias` | yes | `PydanticUndefined` | no | no | `config/aurora/aurora_instruments.yaml :: aurora_instruments.side_bias (missing)` |
| `AuroraInstrumentConfig.signal_threshold` | yes | `PydanticUndefined` | no | no | `config/aurora/aurora_instruments.yaml :: aurora_instruments.signal_threshold (missing)` |
| `AuroraInstrumentConfig.take_profit` | yes | `PydanticUndefined` | no | no | `config/aurora/aurora_instruments.yaml :: aurora_instruments.take_profit (missing)` |
| `AuroraInstrumentConfig.timeframe_sec` | yes | `PydanticUndefined` | no | no | `config/aurora/aurora_instruments.yaml :: aurora_instruments.timeframe_sec (missing)` |
| `AuroraInstrumentConfig.trailing_stop` | yes | `PydanticUndefined` | no | no | `config/aurora/aurora_instruments.yaml :: aurora_instruments.trailing_stop (missing)` |
| `AuroraInstrumentConfig.weights` | yes | `PydanticUndefined` | no | no | `config/aurora/aurora_instruments.yaml :: aurora_instruments.weights (missing)` |
| `DecisionConfig.bar_gating` | yes | `PydanticUndefined` | yes | no | `config/aurora/trading.yaml :: trading.decision.bar_gating` |
| `DecisionConfig.behavior_fsm` | yes | `PydanticUndefined` | yes | no | `config/aurora/trading.yaml :: trading.decision.behavior_fsm` |
| `DecisionConfig.cooldown_sec` | yes | `PydanticUndefined` | yes | no | `config/aurora/trading.yaml :: trading.decision.cooldown_sec` |
| `DecisionConfig.mean_reversion` | yes | `PydanticUndefined` | yes | no | `config/aurora/trading.yaml :: trading.decision.mean_reversion` |
| `DecisionConfig.neutral_threshold` | yes | `PydanticUndefined` | yes | no | `config/aurora/trading.yaml :: trading.decision.neutral_threshold` |
| `DecisionConfig.production` | yes | `PydanticUndefined` | yes | no | `config/aurora/trading.yaml :: trading.decision.production` |
| `DecisionConfig.roi_exit` | yes | `PydanticUndefined` | yes | no | `config/aurora/trading.yaml :: trading.decision.roi_exit` |
| `DecisionConfig.side_bias_min_score` | yes | `PydanticUndefined` | yes | no | `config/aurora/trading.yaml :: trading.decision.side_bias_min_score` |
| `DecisionConfig.side_bias_penalty_factor` | yes | `PydanticUndefined` | yes | no | `config/aurora/trading.yaml :: trading.decision.side_bias_penalty_factor` |
| `DecisionConfig.side_bias_target_ratio` | yes | `PydanticUndefined` | yes | no | `config/aurora/trading.yaml :: trading.decision.side_bias_target_ratio` |
| `DecisionConfig.side_bias_window_sec` | yes | `PydanticUndefined` | yes | no | `config/aurora/trading.yaml :: trading.decision.side_bias_window_sec` |
| `DecisionConfig.symbols_to_track` | yes | `PydanticUndefined` | yes | no | `config/aurora/trading.yaml :: trading.decision.symbols_to_track` |
| `DecisionConfig.testnet` | yes | `PydanticUndefined` | yes | no | `config/aurora/trading.yaml :: trading.decision.testnet` |
| `ExecutionConfig.allow_trade_with_guardian_tidy_only` | yes | `PydanticUndefined` | yes | no | `config/aurora/trading.yaml :: trading.execution.allow_trade_with_guardian_tidy_only` |
| `ExecutionConfig.exposure` | yes | `PydanticUndefined` | yes | no | `config/aurora/trading.yaml :: trading.execution.exposure` |
| `ExecutionConfig.fallback` | yes | `PydanticUndefined` | yes | no | `config/aurora/trading.yaml :: trading.execution.fallback` |
| `ExecutionConfig.limit_orders` | yes | `PydanticUndefined` | yes | no | `config/aurora/trading.yaml :: trading.execution.limit_orders` |
| `ExecutionConfig.manage` | yes | `PydanticUndefined` | yes | no | `config/aurora/trading.yaml :: trading.execution.manage` |
| `ExecutionConfig.min_post_interval_per_symbol_ms` | yes | `PydanticUndefined` | yes | no | `config/aurora/trading.yaml :: trading.execution.min_post_interval_per_symbol_ms` |
| `ExecutionConfig.open_order_type` | yes | `PydanticUndefined` | yes | no | `config/aurora/trading.yaml :: trading.execution.open_order_type` |
| `ExecutionConfig.order_guardian` | yes | `PydanticUndefined` | yes | no | `config/aurora/trading.yaml :: trading.execution.order_guardian` |
| `ExecutionConfig.order_params` | yes | `PydanticUndefined` | yes | no | `config/aurora/trading.yaml :: trading.execution.order_params` |
| `ExecutionConfig.orders` | yes | `PydanticUndefined` | yes | no | `config/aurora/trading.yaml :: trading.execution.orders` |
| `ExecutionConfig.preflight_backoff_ms` | yes | `PydanticUndefined` | yes | no | `config/aurora/trading.yaml :: trading.execution.preflight_backoff_ms` |
| `ExecutionConfig.watchdog` | yes | `PydanticUndefined` | yes | no | `config/aurora/trading.yaml :: trading.execution.watchdog` |
| `InstrumentPrecisionSpec.step_size` | yes | `PydanticUndefined` | yes | no | `config/aurora/instruments.yaml :: instruments.step_size (all)` |
| `InstrumentPrecisionSpec.symbol` | yes | `PydanticUndefined` | yes | no | `config/aurora/instruments.yaml :: instruments.symbol (all)` |
| `InstrumentPrecisionSpec.tick_size` | yes | `PydanticUndefined` | yes | no | `config/aurora/instruments.yaml :: instruments.tick_size (all)` |
| `MRAssetConfig.risk` | yes | `PydanticUndefined` | yes | no | `config/aurora/strategies/mean_reversion.yaml :: mean_reversion.risk` |
| `MRAssetConfig.strategy` | yes | `PydanticUndefined` | yes | no | `config/aurora/strategies/mean_reversion.yaml :: mean_reversion.strategy` |
| `ManageConfig.brackets` | yes | `PydanticUndefined` | yes | no | `config/aurora/trading.yaml :: trading.execution.manage.brackets` |
| `ManageConfig.emergency` | yes | `PydanticUndefined` | yes | no | `config/aurora/trading.yaml :: trading.execution.manage.emergency` |
| `ManageConfig.failsafe` | yes | `PydanticUndefined` | yes | no | `config/aurora/trading.yaml :: trading.execution.manage.failsafe` |
| `ManageConfig.orphan_monitor` | yes | `PydanticUndefined` | yes | no | `config/aurora/trading.yaml :: trading.execution.manage.orphan_monitor` |
| `MarketDataConfig.macro_sync` | yes | `PydanticUndefined` | yes | no | `config/aurora/trading.yaml :: trading.market_data.macro_sync` |
| `OpsConfig.panic_ttl_sec` | yes | `PydanticUndefined` | yes | no | `config/aurora/system.yaml :: ops.panic_ttl_sec` |
| `PositionSizingConfig.liquidity_kappa_mode` | yes | `PydanticUndefined` | yes | no | `config/aurora/trading.yaml :: trading.decision.position_sizing.liquidity_kappa_mode` |
| `PositionSizingConfig.risk_contract_v1` | yes | `PydanticUndefined` | yes | no | `config/aurora/trading.yaml :: trading.decision.position_sizing.risk_contract_v1` |
| `PositionSizingConfig.risk_fraction_q` | yes | `PydanticUndefined` | yes | no | `config/aurora/trading.yaml :: trading.decision.position_sizing.risk_fraction_q` |
| `SystemConfig.market_data` | yes | `PydanticUndefined` | yes | no | `config/aurora/system.yaml :: system.market_data` |
| `TradingConfig.execution` | yes | `PydanticUndefined` | yes | no | `config/aurora/trading.yaml :: trading.execution` |
| `TradingConfig.market_data` | yes | `PydanticUndefined` | yes | no | `config/aurora/trading.yaml :: trading.market_data` |
| `TradingConfig.ops` | yes | `PydanticUndefined` | yes | no | `config/aurora/trading.yaml :: trading.ops` |

## Notes
- `present_in_yaml` is checked structurally by parsing the mapped YAML file and verifying the mapped path exists (keys may exist with `null` values, which still counts as “present”).
- `validation_passes` answers: “If the key is removed from the config dict, does `AuroraConfig(**dict)` still validate?”
