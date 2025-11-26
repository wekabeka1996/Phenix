# CONFIG_REFERENCE.md
Актуальний орієнтир по конфігураційній системі Aurora (після міграції на config v2). Вказані файли лежать у `config/` та споживаються резольверами з `apps/reference/config_*.py`.

> **УВАГА (V2 Runtime):** Деякі секції конфігурації (зокрема `aggregated_oco`, `brackets`, `guardian`) описують функціонал, який **не реалізований** або працює в режимі **detect-only** у поточному `ExecPosRuntimeV2`. Див. `docs/EXEC_POS_V2_RUNTIME_SPEC.md` для деталей.

## 1. Профілі та режими (`config/modes.yaml`)
- `profiles.<name>.trading_mode` — канонічні режими (`full_testnet`, `shadow_live`, `full_live`, custom).
- `profiles.<name>.domains.<domain>` — доменні мапи (`market_data`, `execution_position`, `risk_management`, ...).
- Псевдоніми (`production`, `hybrid`) нормалізуються в `compute_effective_trading_modes`.
- Використовується `ConfigLoader` для побудови `_effective_modes_cache` і `AuroraConfig.get_domain_mode()`.

## 2. Інструменти та overrides (`config/instruments.yaml`, `config/overrides.yaml`, `config/symbols.yaml`)
- `instruments.instruments.<symbol>.limits.*` — `min_notional`, `min_qty`, `min_price`, `step_size`, `tick_size`, `max_position_size`, `max_leverage`.
- `instruments.instruments.<symbol>.precision.*` — `quantity`, `price` (для округлення у FSM/Adapters).
- `overrides.symbols.<symbol>.limits.*` — additive-only патчі поверх базового профілю.
- `symbols.watchlist`, `symbols.trade_cooldown_sec` — джерело для `get_trade_cooldown_sec_for_symbol`.
- `resolve_instrument_profile` повертає `InstrumentProfile` з полем `source="config_v2"` при валідних даних.

## 3. Виконання та Order Guardian (`config/domains/execution.yaml`)
- `manage.guardian.*` — `poll_interval_ms`, `emit_tidy_event`, `cleanup_ttl_ms`, `orphan_monitor.enabled`.
- `manage.watchdog.*` — `ack_ttl_ms`, `fill_ttl_ms`, `check_interval_ms`.
- `manage.brackets.*` — `keep_single_bracket_set`, `retry.max_attempts`, `retry.backoff_ms`.
- `manage.quick_profit.*`, `manage.brackets.oco_emulation` — додаткові прапорці для `ManageFlowFSM`.
- `execution.orders.default_ttl_seconds`, `execution.fallback.*` — підхоплюються `resolve_execution_manage_config` та `resolve_exposure_policy`.

### execution.manage.brackets.aggregated_oco

Логічний блок, який керує режимом Aggregated OCO v1 в execution_position-домені.

Поля:

- `enabled: bool` — вмикає агрегований TP/SL-набір на рівні позиції.
- `recalc_on_scale_in: bool` — якщо `true`, при кожному scale-in TP/SL перераховуються для нової aggregated-позиції.
- `recalc_on_partial_close: bool` — якщо `true`, partial-close також тригерить перерахунок TP/SL.
- `ttl_protect_new_bracket_ms: int` — TTL (мс), протягом якого новий `bracket_set` не може бути очищений Guardian.
- `allow_unprotected_position: bool` — експериментальний режим, який дозволяє позиціям існувати без SL (дефолт `false`).

Вплив на домени:
- ManageFlowFSM читає цей блок через `resolve_execution_manage_config`, визначає коли викликати `_recalc_aggregated_brackets` і яку `why`-метку ставити (`agg_scale_in_recalc`, `agg_partial_close_guard`).
- OrderGuardian отримує серіалізовану версію (`AggregatedOcoGuardianConfig`) і застосовує TTL/allow_unprotected_position правила в `ensure_single_bracket_set_for_position` та `rehydrate_bracket_set_for_position`.

Примітка: при `aggregated_oco.enabled=true` прапор `keep_single_bracket_set` розглядається як legacy та поступово буде виведений з експлуатації.

## 4. Exposure & Position Tracking (`config/domains/execution.yaml`, `config/domains/risk.yaml`)
- `execution.exposure.*` — `max_equity_utilization_pct`, `max_portfolio_fraction`, `max_directional_ratio`, `pending_ttl_sec`, `post_fill_hold_ttl_sec`, `positions_stale_ttl_sec`, `leverage_defaults`.
- `execution.exposure.fallback.*` — політика backoff/risk reduction для адаптера.
- `risk.data_sources.*`, `risk.daily_limits.*` — використовується `DailyRiskState` та `resolve_risk_config` (для FSM `risk_management`).

## 5. Прийняття рішень та сигнали (`config/domains/decision.yaml`, `config/domains/sizing.yaml`, `config/domains/regimes.yaml`)
- `decision.signal_threshold`, `decision.signal_weights.*`, `decision.signals.*`, `decision.qos.*`, `decision.behavior_fsm.*`.
- `decision.position_sizing.*` — мінімальні та максимальні розміри, `liquidity_kappa`, `risk_fraction_q`.
- `sizing.policies.*` — профілі ризику (Kelly, volatility multipliers) для майбутніх фаз.
- `regimes.models.*`, `regimes.transitions.*` — інкапсульовано в `config_regimes`/`config_features`.

## 6. TP/SL та керування позами (`config/domains/execution.yaml`)
- `execution.manage.brackets.sl.*`, `execution.manage.brackets.tp.*`, `execution.manage.brackets.offset_bps` — SSOT для `resolve_brackets_config`.
- `execution.manage.orders.default_ttl_seconds`, `execution.manage.brackets.retry.backoff_ms` — впливають на `ManageFlowFSM`.

## 7. Market Data & Feature Engineering (`config/domains/features.yaml`)
- `feature_engineering.enable_new_metrics`, `feature_engineering.ema.*`, `feature_engineering.volume.*`, `feature_engineering.volatility.*`.
- `feature_engineering.features.<name>.*` — деталізація по метриках (liquidity, ema_bias, volume_spike, volatility_ratio).
- `feature_engineering.macro_sync.*` — anchors, вікно, emit_abs; віддзеркалюється у `trading.market_data.macro_sync`.
- `market_data.poll_interval_sec`, `market_data.websocket_streams` (потрапляє через hydrator у корінь конфіга).

## 8. API та акаунт-обсервабіліті (`config/core.yaml`, `config/domains/risk.yaml`)
- `core.account_observer.poll_interval`, `core.account_observer.auto_start`.
- `core.binance_api.live|testnet.*` визначаються ENV + `_ensure_api_defaults`; конфіг гарантує наявність `api_key`, `api_secret`, `rest_url`.
- `core.ops.metrics_url`, `core.ops.reports_dir`, `system.logging.*` — керують телеметрією та журналами.

## 9. Disaster Recovery & Snapshot Scheduler (`config/domains/execution.yaml`, `core.yaml`)
- `core.dr.snapshot_interval_sec`, `core.dr.storage_path` — регламентує snapshot scheduler.
- `execution.watchdog.dr_recovery_mode`, `execution.watchdog.max_retry_attempts` — використовуються при рестарті FSM.
- WAL/DR логіка (`apps/reference/dr_loader.py`) очікує, що всі події мають коректні `timestamp` (мікросекунди, мілісекунди або ISO — див. `_coerce_timestamp_us`).

> 🔎 Примітка: усі вищеописані параметри мають споживатися через відповідні резольвери (`resolve_*`, `get_trade_cooldown_sec_for_symbol`, `compute_effective_trading_modes`). Прямий доступ до сирих YAML секцій заборонено згідно SSOT.
