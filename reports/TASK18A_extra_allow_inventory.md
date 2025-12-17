# TASK18A — Inventory `extra='allow'` у `apps/reference/config_models.py`

Команда(и):
- `rg -n "ConfigDict\\(extra=['\\\"]allow['\\\"]|extra=['\\\"]allow['\\\"]" apps/reference/config_models.py`

Критичність за правилами SUBTASK 18.A3:
- **CRITICAL**: `AuroraConfig`, `TradingConfig`, `InstrumentSpec`, `BinanceApi*`
- **NONCRITICAL**: усе інше

## Hits

| file:line | model | criticality | snippet |
|---|---|---|---|
| `apps/reference/config_models.py:16` | `InstrumentSpec` | CRITICAL | `extra='allow')  # Allow additional fields from YAML` |
| `apps/reference/config_models.py:34` | `InstrumentPrecisionSpec` | NONCRITICAL | `model_config = ConfigDict(extra='allow')` |
| `apps/reference/config_models.py:105` | `RiskContractV1Config` | NONCRITICAL | `model_config = ConfigDict(extra='allow')` |
| `apps/reference/config_models.py:325` | `MeanReversion1mStrategyConfig` | NONCRITICAL | `model_config = ConfigDict(extra='allow')` |
| `apps/reference/config_models.py:443` | `DecisionModeOverrideConfig` | NONCRITICAL | `extra='allow' justified: config_loader merges ANY override key.` |
| `apps/reference/config_models.py:445` | `DecisionModeOverrideConfig` | NONCRITICAL | `model_config = ConfigDict(extra='allow')  # Justified: dynamic merge` |
| `apps/reference/config_models.py:500` | `SLConfig` | NONCRITICAL | `model_config = ConfigDict(extra='allow')` |
| `apps/reference/config_models.py:506` | `TPConfig` | NONCRITICAL | `model_config = ConfigDict(extra='allow')` |
| `apps/reference/config_models.py:512` | `BracketsConfig` | NONCRITICAL | `model_config = ConfigDict(extra='allow')` |
| `apps/reference/config_models.py:537` | `OrphanMonitorConfig` | NONCRITICAL | `extra='allow' temporary until consumption analysis complete.` |
| `apps/reference/config_models.py:539` | `OrphanMonitorConfig` | NONCRITICAL | `model_config = ConfigDict(extra='allow')  # TODO: Convert to forbid when keys known` |
| `apps/reference/config_models.py:597` | `SMARegimeModelConfig` | NONCRITICAL | `model_config = ConfigDict(extra='allow')` |
| `apps/reference/config_models.py:611` | `VolatilityRegimeModelConfig` | NONCRITICAL | `model_config = ConfigDict(extra='allow')` |
| `apps/reference/config_models.py:627` | `MeanReversionRegimeModelConfig` | NONCRITICAL | `model_config = ConfigDict(extra='allow')` |
| `apps/reference/config_models.py:649` | `RegimeModelConfig` | NONCRITICAL | `model_config = ConfigDict(extra='allow')` |
| `apps/reference/config_models.py:658` | `RegimeDetectorConfig` | NONCRITICAL | `model_config = ConfigDict(extra='allow')` |
| `apps/reference/config_models.py:688` | `OrdersConfig` | NONCRITICAL | `model_config = ConfigDict(extra='allow')  # Temporary: market/cancel sub-configs unknown` |
| `apps/reference/config_models.py:1315` | `AuroraSideBiasConfig` | NONCRITICAL | `model_config = ConfigDict(extra='allow')` |
| `apps/reference/config_models.py:1333` | `AuroraExitConfig` | NONCRITICAL | `model_config = ConfigDict(extra='allow')` |
| `apps/reference/config_models.py:1347` | `AuroraTakeProfitConfig` | NONCRITICAL | `model_config = ConfigDict(extra='allow')` |
| `apps/reference/config_models.py:1365` | `AuroraTrailingStopConfig` | NONCRITICAL | `model_config = ConfigDict(extra='allow')` |
| `apps/reference/config_models.py:1387` | `AuroraExecutionConfig` | NONCRITICAL | `model_config = ConfigDict(extra='allow')` |
| `apps/reference/config_models.py:1541` | `OpsConfig` | NONCRITICAL | `model_config = ConfigDict(extra='allow')` |
| `apps/reference/config_models.py:1571` | `DomainModeConfig` | NONCRITICAL | `model_config = ConfigDict(extra='allow')` |
| `apps/reference/config_models.py:1590` | `DomainConfigurationConfig` | NONCRITICAL | `model_config = ConfigDict(extra='allow')` |
| `apps/reference/config_models.py:1620` | `TradingConfig` | CRITICAL | `model_config = ConfigDict(extra='allow')` |
| `apps/reference/config_models.py:1666` | `BinanceApiEnv` | CRITICAL | `model_config = ConfigDict(extra='allow')` |
| `apps/reference/config_models.py:1682` | `AccountObserverConfig` | NONCRITICAL | `model_config = ConfigDict(extra='allow')` |
| `apps/reference/config_models.py:1689` | `LoggingConfig` | NONCRITICAL | `model_config = ConfigDict(extra='allow')` |
| `apps/reference/config_models.py:1700` | `SystemMarketDataConfig` | NONCRITICAL | `model_config = ConfigDict(extra='allow')` |
| `apps/reference/config_models.py:1710` | `SystemConfig` | NONCRITICAL | `model_config = ConfigDict(extra='allow')` |
| `apps/reference/config_models.py:1724` | `AuroraConfig` | CRITICAL | `extra='allow')  # Allow additional top-level fields` |

