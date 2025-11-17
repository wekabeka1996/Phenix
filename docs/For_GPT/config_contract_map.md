# Config Contract Map — SSOT v1.0

> TASK 7.7 (2025-11-15): runtime й тести читають **лише** config v2 (`config/domains/*.yaml`, `instruments.yaml`, `overrides.yaml`, `modes.yaml`). Legacy `config/aurora/{trading,system}.yaml` тепер зберігаються в `config/archive/v1/` і не підключаються резольверами (залишаються fallbackами лише для повної сумісності).

## Config Loader Pipeline (post-migration)

1. **Root detection & env bootstrapping.** `ConfigLoader` знаходить проєктний корінь, підтягує `.env`, читає тільки `config/` (включно з `config/domains/*`).
2. **Mode selection.** Порядок пріоритетів: змінні `AURORA_TRADING_MODE` / `TRADING_MODE` / `AURORA_TRADING_PROFILE`, потім `trading.mode` або `trading_mode` з YAML, потім `config/modes.yaml`. Усі псевдоніми (`shadow_live`, `hybrid_live_data_testnet_exec`, `full_testnet`, `production`) нормалізуються до канонічних режимів.
3. **Config v2 hydration.** `ConfigV2` об’єднує `core.yaml`, `symbols.yaml`, `instruments.yaml`, `domains/*.yaml`, `overrides.yaml`, `modes.yaml`. Legacy YAML застосовується лише як additive fallback, і лише коли розділ у v2 відсутній.
4. **Domain mapping cache.** Після валідації `AuroraConfig` кешує `compute_effective_trading_modes`, тому кожний домен звертається через `.get_domain_mode()` і не читає сирі поля.
5. **API contract defaults.** `_ensure_api_defaults` гарантує, що обидва блоки `binance_api.{live,testnet}` існують (auto-fill з ENV або дев-сурогатів), якщо профіль потребує відповідний середовище.

> ✅ Наслідок: будь-які нові резольвери мають працювати поверх `config_v2` та не торкатися `config/archive/v1`, окрім тестових сценаріїв деградації.

## Resolver Inventory

### `resolve_brackets_config`
- **Inputs:** `config: Any`, optional `symbol: str` for legacy warning scoping.
- **Primary path:** `trading.execution.manage.brackets` (canonical TP/SL section).
- **Fallbacks:** `trading.execution.brackets`, legacy keys `stop_loss_bps`, `take_profit_high_ratio`, `take_profit_low_ratio`.
- **Defaults:** `sl.fixed_bps=50`, `tp.fixed_bps=100`, `offset_bps=5`.
- **Domains consuming:**
  - `execution_position/ManageFlowFSM` — bracket placement & validation.
  - `execution_position/ExecPosFSM` — DEC:OPEN preview + guardian offsets.
  - `decision_making/DecisionMaking` — Kelly payoff computation.
- **Legacy closures:** direct reads of `trading.execution.brackets.*` or top-level `brackets.*` are forbidden; resolver is single entry-point for TP/SL data.
- **Runtime guarantees:** returns `Decimal` TP/SL values, sources (`sl_source`, `tp_source`) for telemetry, and integer `offset_bps`.

### `resolve_execution_manage_config`
- **Inputs:** `config: Any`.
- **Primary path:** `trading.execution.manage` (canonical manage SSOT).
- **Fallbacks:** `execution.manage`, `trading.execution.order_guardian`, `execution.order_guardian`, root `guardian` (for additive-only migration), `trading.execution.brackets` for metadata.
- **Defaults:** baked into dataclasses (`Guardian.poll_interval_ms=500`, `Watchdog.ack_ttl_ms=8000`, etc.).
- **Domains consuming:**
  - `execution_position/ExecPosFSM` — guardian flags, watchdog TTLs, cleanup toggles.
  - `execution_position/ManageFlowFSM` — bracket metadata (`keep_single_bracket_set`, retry policy).
  - `execution_position/brackets_config` — metadata fallback for resolver bridging.
- **Legacy closures:** direct `self.config.trading.execution.order_guardian.*` reads are replaced by resolver projection.
- **Runtime guarantees:** immutable dataclasses cached per-process; exposes guardian/watchdog/brackets state with typed values.

#### AggregatedOcoConfig (ManageFlowFSM)
- **Source:** `resolve_execution_manage_config.brackets.aggregated_oco` (dataclass `AggregatedOcoConfig`).
- **Fields:** `enabled`, `recalc_on_scale_in`, `recalc_on_partial_close`, `ttl_protect_new_bracket_ms`, `allow_unprotected_position`.
- **Consumers:** `execution_position/fsm_manage.py` (`_recalc_aggregated_brackets`, `_rehydrate_aggregated_brackets_on_startup`).
- **Contract:** ManageFlow must treat `enabled` as feature flag; other fields control whether recalcs fire and how `why` tags/logs are emitted.

#### AggregatedOcoGuardianConfig (OrderGuardian)
- **Source:** Projected from manage resolver via `OrderGuardian._resolve_aggregated_cfg()`.
- **Fields:** `enabled`, `ttl_protect_new_bracket_ms`, `allow_unprotected_position` (subset tailored for guardian cleanup logic).
- **Consumers:** `apps/reference/services/order_guardian.py` (`rehydrate_bracket_set_for_position`, `ensure_single_bracket_set_for_position`).
- **Contract:** TTL protects new sets, fail-closed guard uses `allow_unprotected_position`, guardian logs `AGG_OCO_BRACKET_GUARD` decisions with `decision`/`why` fields.

### `resolve_exposure_policy`
- **Inputs:** `config: Any`.
- **Primary path:** `trading.execution.exposure`.
- **Fallbacks:** `execution.exposure`, `trading.execution.fallback` (for fallback settings), `trading.orders.default_ttl_seconds` for watchdog TTL override.
- **Defaults:** ratios (`max_equity_utilization_pct=0.20`), TTLs (`pending_ttl_sec=90`), leverage default (`20x`) if unspecified.
- **Domains consuming:**
  - `execution_position/ExposureGuard` — exposure caps, pending TTLs.
  - `execution_position/PositionTracking` — leverage defaults.
  - `execution_position/adapters/binance` — fallback escalation policy.
- **Legacy closures:** no direct `config['trading']['execution']['exposure']` access permitted outside resolver.
- **Runtime guarantees:** returns immutable dataclasses, percent normalization (handles `0.30` or `30`).

### `resolve_instrument_profile`
- **Inputs:** `config: AuroraConfig`, `symbol: str`.
- **Primary path:** `config_v2.instruments.instruments[<symbol>]` merged with `config_v2.overrides.symbols[<symbol>]` (deep merge) and optional regime overrides.
- **Fallbacks:** `trading.instruments[<symbol>]` legacy dict (only when v2 record missing or invalid).
- **Defaults:** template with `precision.quantity=3`, `precision.price=2`, `limits.min_notional=10`, `limits.max_leverage=20`, `limits.max_position_size=5`.
- **Domains consuming:**
  - `execution_position` (precision + limits for rounding, bracket sizing).
  - `decision_making` (min_notional/min_qty for gating ideas).
  - `risk_management` (risk_fraction, drawdown multipliers when set).
- **Contract rules:**
  - Поля `max_leverage`, `max_position_size`, `min_notional`, `min_qty`, `min_price` **мають** знаходитись під `limits.*` у базових профілях та overrides (TASK 7.6 enforce).
  - Resolver повертає `InstrumentProfile.source="config_v2"` лише тоді, коли YAML + overrides валідні; інакше спрацьовує legacy fallback.
  - `tools/config_validator_v2` перевіряє overrides і фейлить, якщо знайде dead-fields типу `overrides.symbols.SOLUSDT.max_leverage`.

### `get_trade_cooldown_sec_for_symbol`
- **Inputs:** `config: Any`, `symbol: str`.
- **Primary path:** `trading.instruments[<symbol>].trade_cooldown_sec` (per-symbol); supports `__default__` bucket.
- **Fallbacks:** legacy `cooldown_sec` per instrument.
- **Defaults:** `0.0` seconds when unset.
- **Domains consuming:**
  - `execution_position/ExecPosFSM` — Manage/Close flow guard rails.
  - Integration tests under `tests/domains/test_trade_cooldown_integration.py`.
- **Legacy closures:** deprecates direct `trading.execution.cooldown_ms` lookups for symbol cadence.
- **Runtime guarantees:** returns non-negative float seconds; warns once per symbol on legacy path.

### Daily Limits Resolver (`DailyRiskState`)
- **Inputs:** trading-level config dict or model (expects `risk.*`).
- **Primary path:** `trading.risk.daily_limits` (SSOT), supports additive `trading.risk.daily`.
- **Fallbacks:**
  - `trading.risk.max_realized_loss_usd`,
  - `trading.risk.max_daily_drawdown_limit`,
  - legacy `daily.reset_time_utc` values.
- **Defaults:** `max_loss_usd=250`, `max_drawdown_pct=8%`, reset `00:00` UTC.
- **Domains consuming:**
  - `risk_management/DailyRiskState` (gate invoked by `risk_management` domain).
- **Legacy closures:** forbids ad-hoc reads of `risk.daily_limits.*`; gating must instantiate `DailyRiskState`.
- **Runtime guarantees:** normalizes drawdown percentages (accepts decimals or percents) and ensures reset schedule.

### Trading Mode Resolver (`compute_effective_trading_modes` / `get_domain_mode_from_mapping`)
- **Inputs:** full config object/dict.
- **Primary path:**
  - Profile: `trading.mode` or root `trading_mode`.
  - Domain overrides: `trading.domain_configuration.<domain>.trading_mode`.
- **Fallbacks:** legacy aliases (`shadow_live`, `hybrid_live_data_testnet_exec`, `hybrid`, `production`, etc.) mapped до `PROFILE_DEFAULTS` або до записів `config/modes.yaml`.
- **Defaults:** `full_testnet` profile → `testnet` for all domains.
- **Domains consuming:**
  - `execution_position/ExecPosFSM`, `market_data/MarketDataConnector`, other domain bootstraps.
  - `config_loader.AuroraConfig.get_domain_mode`.
- **Legacy closures:** domain init cannot read `config.trading_mode` blindly; must call resolver for accurate hybrid/shadow mapping.
- **Runtime guarantees:** returns profile descriptor plus per-domain mapping with `__default__` fallback.

## Domain Consumption Matrix

| Domain | Resolver(s) | Parameters Consumed | Notes |
| --- | --- | --- | --- |
| `execution_position.ExecPosFSM` | `resolve_execution_manage_config`, `resolve_brackets_config`, `resolve_exposure_policy`, `get_trade_cooldown_sec_for_symbol`, `compute_effective_trading_modes` | Guardian polling/TTL flags, bracket metadata, exposure policy, symbol cooldownи, domain trading mode | Guardian config проектується назад у legacy-вузли лише для сумісності з адаптерами; cooldown-и по символах перекривають глобальні обмеження. |
| `execution_position.ManageFlowFSM` | `resolve_execution_manage_config`, `resolve_brackets_config` | `brackets.keep_single_bracket_set`, retry/backoff tuple, TP/SL decimals | Забезпечує єдиний SSOT для інваріантів manage flow. |
| `execution_position.ExposureGuard` | `resolve_exposure_policy` | Caps (equity/utilization), leverage defaults, pending TTLs, fallback risk reduction | Результат кешується; підтримує overrides із `overrides.yaml`. |
| `execution_position.PositionTracking` | `resolve_exposure_policy` | `leverage_defaults`, reservation TTLs | Узгоджує leverage в PG та трекері. |
| `execution_position.adapters.Binance*` | `resolve_exposure_policy` | `fallback` policy (backoff sequence, risk reduction pct) | Адаптер отримує політику тільки через резольвер; прямі читання заборонені. |
| `decision_making.DecisionMaking` | `resolve_brackets_config`, `compute_effective_trading_modes` | TP/SL ratios для Kelly, доменний режим | Стежить, щоб прийняття рішень не розходилось з фактичним виконанням. |
| `market_data.MarketDataConnector` | `compute_effective_trading_modes` | Режим для market_data (live/testnet) | Визначає, який API-компонент (live reader чи testnet) активувати. |
| `risk_management.DailyRiskState` | Daily limits resolver (`DailyRiskState`) | Max loss USD, drawdown %, reset window | Gate використовує нормалізовані дані при кожному EVT. |
| `utils.trade_cooldowns` | `get_trade_cooldown_sec_for_symbol` | Symbol cooldown seconds | Постачає дані для будь-яких FSM з рейт-лімітами. |
| `config_loader.ConfigLoader` | `compute_effective_trading_modes`, `_ensure_api_defaults` | Кеш режимів та автоконфігурація `binance_api` | Форує `AuroraConfig` з готовими блоками `live/testnet` та expose'ить `.get_domain_mode()`. |

## Compatibility & Fallback Rules Snapshot

- **Additive-only evolution:** new config knobs must extend resolvers/dataclasses rather than altering existing fields.
- **Legacy aliases:** maintained via resolver fallbacks; direct reads of legacy paths outside resolvers violate SSOT.
- **Percent normalization:** exposure & daily risk resolvers accept both ratio (`0.30`) and percent (`30`) inputs.
- **Hybrid profiles:** `LEGACY_MODE_ALIASES` canonicalize historical strings into supported profiles before mapping.
- **Guardian projection:** manage resolver writes normalized guardian values back into legacy nodes for adapters expecting raw dicts, preventing divergent states.
- **Instrumentation:** resolvers emit one-time warnings when legacy keys are used, enabling cleanup without runtime spam.

## Runtime Invariants (Resolver Outputs)

- Instrument profile resolver гарантує наявність `limits.min_notional/min_qty/max_leverage` після merge та підтягує overrides лише з `limits.*` (інше блокує валідатор).
- TP/SL outputs are `Decimal` and strictly positive; offset is integer ≥ 0.
- Manage guardian TTL/cooldowns are non-negative integers; retry sequences default to `(120, 250, 400)` if invalid.
- Exposure caps ratios remain within `[0, 1]` after normalization; leverage defaults fall back to global value for unknown symbols.
- Trade cooldown resolver never returns negative durations; defaults to `0.0` when nothing is configured.
- Daily risk resolver returns finite loss/drawdown limits and ensures reset schedule is valid `HH:MM` string.
- Domain mode resolver always supplies `__default__` mapping matching profile baseline (no missing domains).
- `ConfigLoader` гарантує, що `binance_api.live` та `binance_api.testnet` завжди існують, якщо профіль потребує їх; браку ключів не викликає рантайм падіння.
- Env aliases (`TRADING_MODE`, `AURORA_TRADING_MODE`, `AURORA_TRADING_PROFILE`) перетворюються на канонічні значення ще до резольверів; тож домени ніколи не бачать `shadow_live` як режим середовища.
- `config_v2` залишається єдиним джерелом правди; увімкнені валідатори блокують «мертві» поля в overrides (`overrides.symbols.<sym>.max_leverage` тільки під `limits.*`).

## Legacy Access Paths Explicitly Closed

- `trading.execution.brackets.*` (use `resolve_brackets_config`).
- `trading.execution.order_guardian.*`, root `guardian.*` (use `resolve_execution_manage_config.guardian`).
- `trading.execution.exposure.*` (use `resolve_exposure_policy`).
- `trading.execution.cooldown_ms` for symbol cadence (use `get_trade_cooldown_sec_for_symbol`).
- `trading.risk.daily_limits.*` raw reads (instantiate `DailyRiskState`).
- Blind `config.trading_mode` reads for hybrid/shadow contexts (use `compute_effective_trading_modes` / `get_domain_mode_from_mapping`).
