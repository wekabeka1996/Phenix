# trading.yaml Wiring Map (v2)

> 2025-11-15 (TASK 7.7): AuroraConfig і всі тести спираються на config v2 (domains/instruments/overrides/modes). Цей документ описує історичне розташування ключів у monolith `config/aurora/trading.yaml`, який тепер знаходиться лише в `config/archive/v1/` для референсу. Нові зміни потрібно вносити в модульні YAML і резольвери.

## I. Mode Resolution & Domain Overrides
- `apps/reference/config_loader.py` merges `system.yaml` + `trading.yaml`, resolves env variables, then `_resolve_mode_overrides` applies `trading.decision.<mode>` and `trading.risk.<mode>` overlays. Canonical mode comes from `trading_mode` (system) while legacy readers still inspect `trading.mode`.
- `apps/reference/utils/trading_modes.py::compute_effective_trading_modes` materializes domain-level `trading.domain_configuration.*.trading_mode` and caches the result via `AuroraConfig.get_domain_mode`. Execution and risk FSMs query this helper instead of reading raw YAML.
- Execution FSM (`apps/reference/domains/execution_position/fsm.py`, `ExecPosFSM._resolve_guardian_config` & `_get_domain_trading_mode`) consults `domain_configuration.execution_position`. When absent it falls back to global `trading_mode`, then to legacy `trading.mode`.
- Hybrid guard (`apps/reference/bootstrap/preflight.py::check_hybrid_coherence`) verifies market-data/feature domains run in `live` while execution/risk follow `testnet`. It reads `_resolved.risk_portfolio_source` (if present) or cascades through `trading.domain_configuration.risk_management.data_sources.portfolio_state` → `trading.risk_management.data_sources.portfolio_state` → top-level `risk_management.data_sources.portfolio_state`.
- `apps/reference/main.py` bootstraps domains using the computed effective modes. Risk/Execution domains reject inconsistent settings at startup (log `HYBRID_INCOHERENT`).

## II. Risk Management & Daily Limits
- `apps/reference/domains/risk_management/daily_gate.py` consumes `trading.risk.daily_limits.*` (percent scale 0–100) to build `DailyConfig`. Legacy keys under `trading.risk.daily.*` (`max_realized_loss_usd`, `max_drawdown_pct`) remain as fallbacks.
- `apps/reference/domains/risk_management/risk_management.py` reads:
  - `trading.risk.trading_allowed_thresholds.max_risk_score` (overridden per mode) to gate intents.
  - `trading.risk.score_weights.*` for composite risk scoring (equally consumed by `risk_engine.score_signal`).
  - `trading.risk.profile` and `trading.risk.soft_limits.*` to select clipping strategy and directional ratios.
- Exposure Guard (`apps/reference/domains/execution_position/exposure_guard.py`) uses:
  - `trading.execution.exposure.max_equity_utilization_pct`, `max_side_utilization_pct.{long,short}`, `per_symbol_cap_pct`, `max_directional_ratio` (all expressed as % 0–100, some allow >100 for testnet).
  - `trading.execution.exposure.leverage_defaults` with symbol override + `__default__` fallback; missing symbol triggers log + default leverage.
  - `trading.execution.exposure.count_pending_orders` + `pending_reservation_ttl_sec` to decide reservation handling.
- Soft clip path: `_load_soft_limit_config` maps `trading.risk.soft_limits` + `regime_adaptation` into runtime multipliers; missing entries revert to `directional_ratio_max` base.
- Risk portfolio feed selection surfaces via `trading.risk_management.data_sources.portfolio_state` (see Section V) and controls which ledger the risk FSM listens to.

## III. Instruments & Position Sizing
- `trading.instruments.<symbol>` defines canonical symbol metadata (`step_size`, `tick_size`, `min_notional`) used by:
  - `apps/reference/config_symbols.py::get_symbol_config` (runtime lookups with fallback to `__default__` if provided).
  - Execution FSM bracket quantization (`_quantize_price`, `_quantize_notional`).
- Position sizing tree lives under `trading.instruments.<symbol>.position_sizing`:
  - Decision Making (`apps/reference/domains/decision_making/decision_making.py::_calculate_position_size`) uses `min_position_size_usd`, `liquidity_based_cap_usd`, `risk_fraction_q`, `liquidity_kappa`, `liquidity_kappa_mode`.
  - Regime multipliers (`sizing_modifiers.*`) are applied if the regime detector publishes context.
  - Kelly block (`kelly.*`) is optional; if absent the code falls back to risk_fraction sizing.
- Behavior FSM toggles: optional `behavior_fsm.enable` gating feature flags for symbol-specific adjustments.
- Per-symbol thresholds: `regime_threshold_multipliers` feed directly into signal gating (Decision Making).

## IV. Execution, Brackets & Guardian Controls
- `trading.execution.manage.*` is consumed by `ExecPosFSM` and `ManageFlowFSM`:
  - `manage.auto`, `manage.brackets.enable/oco_emulation` toggle bracket lifecycle.
  - Legacy keys `stop_loss_bps`, `take_profit_low_ratio`, `take_profit_high_ratio` remain for Kelly compatibility; new structure `sl.fixed_bps`, `tp.fixed_bps`, `offset_bps` drives `_calculate_bracket_prices`.
  - `manage.brackets.retry.*`, `timeout_sec`, `price_protect`, `working_type_default` flow into order placement wrappers.
  - `manage.brackets.atomic_close`, `bracket_tracking` guard against orphaned orders (audited by `orphan_monitor.*`).
  - `manage.brackets.quick_profit.*` is read by `QuickProfitController` (disabled by default).
- Order Guardian (`apps/reference/services/order_guardian.py`, invoked from Manage flow) reads `trading.execution.orders.*` for TTL, cancel idempotency, and market slippage guard.
- `trading.execution.watchdog.*` configures ACK/FILL timers for `OrderTimeoutWatchdog`.
- `trading.execution.order_params.<ORDER_TYPE>` (e.g., `LIMIT.timeInForce`) map 1:1 to Binance order payloads assembled in `apps/reference/adapters/binance_adapter.py`.

## V. QoS, Cooldowns, Exposure Blocks & Domain Data Sources
- Trade cooldowns:
  - `apps/reference/utils/trade_cooldowns.py` returns `trade_cooldown_sec` per symbol with warning fallback to deprecated `cooldown_sec`; missing values degrade to `trading.execution.cooldown_ms` (converted ms→s).
  - Decision QoS uses `trading.instruments.<symbol>.qos.symbol_intent_cooldown_sec`; legacy `symbol_cooldown_sec` remains for backward compatibility. Additional knobs: `qos.mode`, `enabled`, `enforce`, `exposure_block_cooldown_sec`, `max_intents_per_minute_per_symbol`.
- Exposure block TTL (`trading.instruments.<symbol>.qos.exposure_block_cooldown_sec`) is honored by Decision Making before intents reach Execution.
- Domain data sources:
  - `trading.domain_configuration.risk_management.data_sources.portfolio_state` overrides the ledger used by Risk domain. Execution defaults to follow-execution; hybrid preflight rewrites `follow_execution` → `testnet`.
  - Market data / feature / decision / execution domain entries define read/write environments; absent entries fall back to global `trading_mode`.

## VI. Signals, Features & Regime Models
- `trading.decision.signal_threshold`, `neutral_threshold`, and per-regime multipliers from `instruments.<symbol>.regime_threshold_multipliers` are accessed by `DecisionMakingFSM` to gate opens.
- Signal composition weights (`trading.instruments.<symbol>.signal_weights.*`) feed the feature aggregator; legacy weights remain additive.
- Feature engineering config (`trading.feature_engineering.*`) drives window lengths and toggles inside `apps/reference/domains/feature_engineering/feature_engineering.py`.
- Market data macro sync (`trading.market_data.macro_sync.*`) is used by market data collectors to align anchors.
- Regime detector (`apps/reference/domains/regime_detector/config.py`) reads `trading.models.volatility.*`, `trading.models.mean_reversion.*` to configure ATR thresholds and window sizes.

## VII. Observability & Safety Hooks
- `trading.ops.panic_killswitch`, `quiet_hours_utc`, `allowlist_symbols` are evaluated by Decision Making gate checks and Ops utilities.
- `apps/reference/bootstrap/preflight.check_hybrid_coherence` publishes Prometheus metrics reflecting any configuration drift vs expected hybrid contract.
- Journaling / WHY instrumentation in Execution & Decision domains include current config fragments (brackets, exposure, risk thresholds) in emitted events for forensic reconstruction.

## Risk Summary
- Percent scales: `trading.risk.daily_limits.*` and `trading.execution.exposure.*` expect values in human-readable percent (0–100). Conversions to fractions happen at call sites; providing `[0,1]`-scaled numbers would silently slash limits.
- Legacy compatibility: `cooldown_sec`, `risk.daily.*`, `manage.brackets.stop_loss_bps` remain live fallbacks. Removing them without updating all readers triggers KeyError, logging spam, or reverts to hardcoded defaults.
- Hybrid consistency: altering `domain_configuration.*.trading_mode` without updating risk portfolio source causes `HybridIncoherenceError` during bootstrap.
- Order safety: Disabling `manage.brackets.atomic_close` re-opens regression #A17 (orphaned TP/SL). Any schema change must retain defaults that keep `atomic_close=true`.

## Risks при изменении схемы
1. Breaking the `trade_cooldown_sec` schema or removing the legacy `cooldown_sec` fallback will freeze Decision QoS in deployments still writing the old key, leading to burst intents and guardian rate limits.
2. Renaming `trading.execution.exposure.leverage_defaults.__default__` or changing leverage type (int→str) breaks Exposure Guard bootstrap; it expects numeric values for Decimal arithmetic.
3. Moving `trading.risk.soft_limits` to a new namespace without aliasing would disable clipping, causing hard rejections and higher timeout rate.
4. Changing the structure of `trading.domain_configuration.risk_management.data_sources.portfolio_state` without updating preflight will mark hybrid configs incoherent and block startup.

## Config v2 Ops Gate

- `tools/config_validator_v2.py` is the canonical gate that runs Pydantic ingestion, resolver invariants, and JSON Schema, prints a concise summary of the `schema` + domain reports, writes `docs/config_v2/validation_report.json`, and exits non-zero on errors.
- `tools/verify_config.py` now wraps that validator to give operators a single-command (`python tools/verify_config.py`) pass/fail check before deployment.
- AuroraCore's bootstrap (`apps/reference/main.py`) invokes the validator before domain initialization; any failure is logged as `CRITICAL` and the process aborts.
- GitHub Actions/CI runs `pytest tests/config -q` plus `python tools/config_validator_v2.py`, so schema or resolver regressions cannot reach release (see `.github/workflows/ci.yml`).
