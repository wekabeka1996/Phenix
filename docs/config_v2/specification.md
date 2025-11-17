# Config v2 Specification

> Architectural specification for modular, additive-only configuration system (Phase 1+).

## 1. Ціль config v2

Нова система конфігурації спрямована на досягнення наступних цілей:

- **Модульність по доменах**: кожен домен (execution, risk, decision тощо) має власний конфіг-файл, що зменшує зв'язність і полегшує підтримку.
- **Additive-only еволюція**: всі зміни тільки додають нові ключі або файли; існуючі ключі не змінюються, щоб уникнути breaking changes.
- **Dual-mode (old+new) на перехідний період**: система підтримує паралельне читання старих (v1) і нових (v2) конфігів, з пріоритетом v1 до повної міграції.
- **Повна сумісність з існуючими резольверами через dual-path**: всі поточні резольвери продовжують працювати, але можуть використовувати v2 як джерело даних.

## 2. Нова структура файлів

```
config/
  core.yaml              # ARCHIVED: дублюється з system.yaml; ops можна додати до system.yaml
  symbols.yaml           # ARCHIVED: дублюється з instruments.yaml + overrides.yaml
  instruments.yaml       # Паспортні дані монет (precision, limits, defaults)
  domains/
    execution.yaml       # Execution-домен: manage, exposure, brackets, watchdog
    risk.yaml            # Risk-домен: limits, profiles, score weights
    decision.yaml        # Decision-домен: signals, qos, behavior fsm
    sizing.yaml          # Sizing-домен: position sizing, kelly, liquidity
    features.yaml        # Features-домен: ema, volume, volatility, macro_sync
    regimes.yaml         # Regimes-домен: hmm, features, hotreload
    tca.yaml             # TCA-домен: slippage, venue, priority
  overrides.yaml         # Пер-символьні та пер-профільні overrides
  modes.yaml             # Централізоване визначення trading_modes та domain_modes
```

### Опис файлів

- **core.yaml**: ARCHIVED - дублюється з system.yaml (logging, hardening, account_observer); ops можна додати до system.yaml.
- **symbols.yaml**: ARCHIVED - дублюється з instruments.yaml (профілі) + overrides.yaml (overrides).
- **instruments.yaml**: паспортні дані монет (на базі INSTRUMENT_TEMPLATE.md). Precision, tick_size, min_notional, leverage defaults, tp/sl defaults, regime multipliers.
- **domains/execution.yaml**: чисті доменні конфіги для execution-домену (manage, exposure, brackets, watchdog, open_order_type, order_params).
- **domains/risk.yaml**: чисті доменні конфіги для risk-домену (daily_limits, score_weights, soft_limits, regime_adaptation, feature_flags).
- **domains/decision.yaml**: чисті доменні конфіги для decision-домену (signals, qos, behavior_fsm, side_bias, cooldown).
- **domains/sizing.yaml**: чисті доменні конфіги для sizing-домену (min_position_size_usd, liquidity_based_cap_usd, risk_fraction_q, kelly, sizing_modifiers).
- **domains/features.yaml**: чисті доменні конфіги для features-домену (ema, volume, volatility, liquidity, macro_sync, enable_new_metrics).
- **domains/regimes.yaml**: чисті доменні конфіги для regimes-домену (hmm, features, hotreload_whitelist).
- **domains/tca.yaml**: чисті доменні конфіги для tca-домену (max_slippage_pct, preferred_venue, execution_priority).
- **overrides.yaml**: пер-символьні та пер-профільні overrides (монети, режими, risk-профілі). Наприклад, BTCUSDT має власні leverage або tp/sl.
- **modes.yaml**: централізоване визначення trading_modes, domain_modes, testnet/live/hybrid профілів. Замінює розмазаний trading_mode в trading.yaml.

  Структура:
  ```yaml
  profiles:
    full_testnet:
      trading_mode: full_testnet
      domains:
        market_data: testnet
        feature_engineering: testnet
        decision_making: testnet
        risk_management: testnet
        execution_position: testnet
        audit_trail: testnet
    shadow_live:
      trading_mode: shadow_live
      domains:
        market_data: live
        feature_engineering: live
        decision_making: live
        risk_management: testnet
        execution_position: testnet
        audit_trail: live
    full_live:
      trading_mode: full_live
      domains:
        market_data: live
        feature_engineering: live
        decision_making: live
        risk_management: live
        execution_position: live
        audit_trail: live
  ```

## Legacy schemas

- `_schemas/aurora_trading.schema.json` має `x-status: deprecated` і `x-notes` з поясненням, що це історична описка монолітного `trading.yaml`; цей файл більше не перевіряється в пайплайні config v2 і використовується лише в документації/архівах.
- `config_schema_v1.py` (SSOTConfig) зберігає frozen-моделі для `trading.*`, але має docstring `DEPRECATED: v1 monolith config, kept for historical reference` і імпортується лише з `tools/config_validate.py`.
- `tools/config_validate.py` залишається скриптом для ручної перевірки старої складеної конфігурації (`config/aurora/trading.yaml`, `config/system.yaml`), але не є частиною config v2 pipeline – він продовжує підтримувати legacy-моделі для архівів.

## Config v2 JSON Schema

- `config/_schemas/config_v2.schema.json` описує високорівневу структуру modular v2 (core/symbols/instruments/overrides/modes/domains) і стає основою для JSON Schema кроку в `tools/config_validator_v2.py`.

## Config v2 Ops Gate

- `tools/config_validator_v2.py` became the canonical gate: it loads AuroraConfig (Pydantic-ingested), runs resolver invariants, validates `config_v2` payload against `_schemas/config_v2.schema.json`, emits a `schema` domain report, writes `docs/config_v2/validation_report.json`, prints the summary, and exits non-zero on failure.
- `tools/verify_config.py` now wraps that validator so operators can run a single command that fails fast when any config check has issues.
- AuroraCore bootstrap (`apps/reference/main.py`) invokes the same validator before spinning up FSM domains; any `status != "ok"` is logged as `CRITICAL` and aborts startup.
- GitHub Actions/CI executes `pytest tests/config -q` plus `python tools/config_validator_v2.py` (see `.github/workflows/ci.yml`), so schema and resolver regressions are caught pre-release.

## 3. Маппінг старих шляхів → нові

| Старий шлях (trading.yaml/system.yaml) | Новий шлях (v2) | Резольвер | Коментар |
|----------------------------------------|-----------------|-----------|----------|
| trading.execution.manage.quick_profit.target_usd | domains/execution.yaml: manage.quick_profit.target_usd | resolve_execution_manage_config | Execution-домен, quick profit |
| trading.execution.manage.orphan_monitor.enabled | domains/execution.yaml: manage.orphan_monitor.enabled | resolve_execution_manage_config | Execution-домен, orphan monitor |
| trading.execution.manage.brackets.enable | domains/execution.yaml: manage.brackets.enable | resolve_execution_manage_config | Execution-домен, brackets meta |
| trading.execution.manage.brackets.default_tp_bps | domains/execution.yaml: brackets.sl.fixed_bps, brackets.tp.fixed_bps | resolve_brackets_config | Execution-домен, TP/SL brackets |
| trading.execution.exposure.max_equity_utilization_pct | domains/execution.yaml: exposure.max_equity_utilization_pct | resolve_exposure_policy | Execution-домен, exposure limits |
| trading.execution.exposure.leverage_defaults.SOLUSDT | instruments.yaml: instruments.SOLUSDT.leverage_default + overrides.yaml | resolve_instrument_profile | Instruments + overrides |
| trading.decision.qos.symbol_cooldown_sec | domains/decision.yaml: qos.symbol_cooldown_sec | resolve_decision_config | Decision-домен, QoS |
| trading.decision.behavior_fsm.high_vol_multiplier | domains/decision.yaml: behavior_fsm.high_vol_multiplier | resolve_decision_config | Decision-домен, FSM |
| trading.risk.daily_limits.max_loss_usd | domains/risk.yaml: daily_limits.max_loss_usd | resolve_daily_risk_state | Risk-домен, daily limits |
| trading.risk.score_weights.delta_price | domains/risk.yaml: score_weights.delta_price | resolve_risk_config | Risk-домен, scoring |
| trading.instruments.BTCUSDT.symbol | instruments.yaml: instruments.BTCUSDT.symbol | resolve_instrument_profile | Instruments, base data |
| trading.instruments.BTCUSDT.regime_threshold_multipliers.HIGH_VOLATILITY | instruments.yaml: instruments.BTCUSDT.regime_multipliers.HIGH_VOLATILITY + overrides.yaml | resolve_instrument_profile | Instruments + overrides |
| trading.feature_engineering.ema.period_short | domains/features.yaml: ema.period_short | resolve_features_config | Features-домен, EMA |
| trading.feature_engineering.volatility.window_sec | domains/features.yaml: volatility.window_sec | resolve_features_config | Features-домен, volatility |
| trading.mode | modes.yaml: profiles.default | resolve_trading_modes | Modes, profile selection |
| trading.domain_configuration.market_data.trading_mode | modes.yaml: domain_modes.market_data | resolve_trading_modes | Modes, domain modes |
| system.logging.level | system.yaml: logging.level | ConfigLoader | Core, logging (kept in system.yaml) |
| system.hardening.ttl_config.entry_place_ttl_ms | system.yaml: hardening.ttl_config.entry_place_ttl_ms | ConfigLoader | Core, hardening (kept in system.yaml) |

## 4. Meta-resolvers (дизайн)

### resolve_execution_manage_config
- **Джерела**: `domains/execution.yaml: manage.*` (primary), `trading.execution.manage.*` (legacy-fallback).
- **Вихід**: ExecutionManageConfig з orphan_monitor, quick_profit, trailing, emergency, brackets, guardian, watchdog.
- **Споживачі**: ManageFlowFSM, ExecPosFSM.
- **Інваріанти**: Valid decimals for USD targets, positive TTLs, boolean flags.

### resolve_brackets_config
- **Джерела**: `domains/execution.yaml: brackets.*` (primary), `trading.execution.manage.brackets.*` або `trading.execution.brackets.*` (legacy-fallback).
- **Вихід**: ResolvedBrackets з sl_bps, tp_bps, offset_bps, sources.
- **Споживачі**: ManageFlowFSM, ExecPosFSM, DecisionMaking.
- **Інваріанти**: Positive BPS values, valid offset.

### resolve_daily_risk_state
- **Джерела**: `domains/risk.yaml: daily_limits.*` (primary), `trading.risk.daily_limits.*` (legacy-fallback).
- **Вихід**: DailyRiskState з max_realized_loss_usd, max_drawdown_pct, reset_time.
- **Споживачі**: ExecPosFSM, risk_management.
- **Інваріанти**: Positive USD limits, valid percent, valid time format.

### resolve_trading_modes()
- **Джерела**: modes.yaml: profiles.* (primary), trading.mode + trading.domain_configuration.* (legacy-fallback).
- **Вихід**: EffectiveTradingModes з profile та domain_modes маппінгом.
- **Споживачі**: всі домени через ConfigLoader.
- **Інваріанти**: profile в {"full_testnet", "shadow_live", "full_live"}; domain_modes в {"live", "testnet", "disabled"}.

## 5. Сумісність і dual-mode

- **Dual-path читання**: поки конфіги v2 не повністю заповнені, резольвери читатимуть старий формат як primary, а новий — як optional override (fallback).
- **Direct YAML-читання заборонено**: поза резольверами заборонено; всі доступи через meta-resolvers.
- **Legacy-файли як SSOT**: trading.yaml, system.yaml вважаються SSOT до Фази 8 (Freeze & Replace); v2 файли additive-only.

## 7. Поточний стан реалізації

Skeleton-файли для config v2 створені в `config/`:
- `config/core.yaml` - **ARCHIVED** (дублюється з system.yaml)
- `config/symbols.yaml` - **ARCHIVED** (дублюється з instruments.yaml + overrides.yaml)
- `config/instruments.yaml`
- `config/domains/execution.yaml`
- `config/domains/risk.yaml`
- `config/domains/decision.yaml`
- `config/domains/sizing.yaml`
- `config/domains/features.yaml`
- `config/domains/regimes.yaml`
- `config/domains/tca.yaml`
- `config/overrides.yaml`
- `config/modes.yaml`

Доти, доки секції (exposure/manage/brackets/daily_limits/profiles тощо) не заповнені, dual-mode резольвери працюють у режимі **legacy-first** (v2 → invalid → fallback).

## 8. Config Validator v2

### Огляд
Централізований валідаційний пайплайн для перевірки конфігурації v2. Завантажує повну AuroraConfig, проганяє всі основні резольвери по доменах, перевіряє базові інваріанти та формує JSON-звіт.

### Використання
```bash
python tools/config_validator_v2.py
python tools/config_validator_v2.py --config-root /path/to/config --output custom_report.json
```

### Структура звіту
Звіт зберігається в `docs/config_v2/validation_report.json`:
```json
{
  "status": "ok" | "error",
  "domains": {
    "execution": {"status": "ok", "errors": [], "warnings": []},
    "risk": {"status": "ok", "errors": [], "warnings": []},
    "sizing": {"status": "ok", "errors": [], "warnings": []},
    "decision": {"status": "ok", "errors": [], "warnings": []},
    "instruments": {"status": "ok", "errors": [], "warnings": []},
    "modes": {"status": "ok", "errors": [], "warnings": []}
  }
}
```

### Перевіряємі домени
- **execution**: resolve_exposure_policy, resolve_execution_manage_config, resolve_brackets_config + інваріанти exposure/brackets
- **risk**: resolve_daily_risk_state + інваріанти max_loss/max_drawdown
- **sizing**: resolve_sizing_policy + інваріанти risk_pct/notional
- **decision**: resolve_decision_policy + інваріанти thresholds
- **instruments**: resolve_instrument_profile для перших 5 символів + інваріанти limits/leverage
- **modes**: compute_effective_trading_modes + domain mode mapping

### Інваріанти
- **Exposure**: 0 < max_equity_utilization_ratio <= 10, 0 <= max_portfolio_fraction, max_directional_ratio >= 0
  - `max_portfolio_fraction`: дозволяє значення >1 (наприклад, 2.0 для 200% у тестнеті), після нормалізації розглядається як ratio.
- **Risk**: max_realized_loss_usd >= 0, 0 <= max_drawdown_pct <= 100
- **Sizing**: 0 < max_risk_pct <= 100, max_risk_usd >= 0, 0 < min_notional_usd <= max_notional_usd
- **Decision**: 0 <= signal_threshold <= 1, 0 <= neutral_threshold <= 1, neutral_threshold >= signal_threshold
- **Instruments**: min_notional > 0, min_qty > 0, min_price >= 0, max_leverage >= 1

### CI Інтеграція
Валідатор призначений для використання в CI пайплайнах. Exit code 0 при успішній валідації, 1 при помилках.
