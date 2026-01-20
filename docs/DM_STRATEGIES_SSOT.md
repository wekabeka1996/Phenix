# DM_STRATEGIES_SSOT (DM-STRATEGY-SSOT-AUDIT-01)

Це SSOT-опис того, **як реально (по коду/конфігах)** працюють стратегії в `DecisionMaking`: **підписки → залежності → фічі/дані → гейти → емісії → execution-інтеграція**, плюс знайдені невідповідності/легасі/“фантомні” зв’язки.

> Принцип: жодних “схоже/можливо” — тільки факти з репо + посилання `file:line`.

---

## 1) Overview: як працює bar-driven DecisionMaking

**Composition root / wiring**

- `DecisionMaking` створюється в `apps/reference/main.py:835`, і одразу підписується на події (зокрема на `EVT:STRATEGY_SIGNAL_PRODUCED`) в `apps/reference/domains/decision_making/decision_making.py:375`.
- Strategy plugins (allowlist) стартують після `DecisionMaking`: `apps/reference/main.py:837` → `apps/reference/main.py:841`.

**Канонічний цикл (T2B-03 / orchestrated cycle)**

1. `FeatureEngineering` емісить `EVT:FEATURES_CALCULATED` (payload включає `tf_sec`, `warmup`, `price_motion`, `bar`) у `apps/reference/domains/feature_engineering/feature_engineering.py:1002` та `apps/reference/domains/feature_engineering/feature_engineering.py:1019`.
2. `FeatureEngineering` емісить `CMD:PROCESS_STRATEGY` **тільки якщо**: є `bar_data`, `tf_sec >= 60`, `warmup.full_ready == True`, валідні `bar_close_ts` і OHLCV — `apps/reference/domains/feature_engineering/feature_engineering.py:1021` → `apps/reference/domains/feature_engineering/feature_engineering.py:1061`.
3. Стратегія(ї) отримують `CMD:PROCESS_STRATEGY` і (за умов) емісить `EVT:STRATEGY_SIGNAL_PRODUCED`:
   - Aurora: `apps/reference/domains/decision_making/aurora_handler.py:384` та `apps/reference/domains/decision_making/aurora_handler.py:1174`
   - Mean Reversion: `apps/reference/domains/decision_making/mean_reversion_handler.py:784` та `apps/reference/domains/decision_making/mean_reversion_handler.py:616`
4. `DecisionMaking` як “універсальний gateway” обробляє `EVT:STRATEGY_SIGNAL_PRODUCED` (`apps/reference/domains/decision_making/decision_making.py:385`) і, **тільки після проходження гейтів**, емісить `EVT:TRADE_INTENT_PROPOSED` (`apps/reference/domains/decision_making/decision_making.py:963` та `apps/reference/domains/decision_making/decision_making.py:3171`).

---

## 2) Strategy Catalog (Strategy Units)

| Strategy ID | Code location | Entry point (event → method) | TF contract | Emits |
|---|---|---|---|---|
| `aurora` | Plugin: `apps/reference/domains/strategies/plugins/aurora_builtin.py:68`; Handler: `apps/reference/domains/decision_making/aurora_handler.py:70` | `CMD:PROCESS_STRATEGY` → wrapper `_AuroraHandlerWrapper._on_process_strategy()` → `AuroraHandler.on_process_strategy()` (`apps/reference/domains/strategies/plugins/aurora_builtin.py:51`, `apps/reference/domains/decision_making/aurora_handler.py:384`) | **bar-only**: `cmd.tf_sec` must exist and must equal `config.strategies.aurora.timeframe_sec` (`apps/reference/domains/decision_making/aurora_handler.py:405`, `apps/reference/domains/decision_making/aurora_handler.py:443`) | `EVT:STRATEGY_SIGNAL_PRODUCED` (`apps/reference/domains/decision_making/aurora_handler.py:1174`), `EVT:STRATEGY_DECISION_BLOCKED` (`apps/reference/domains/decision_making/aurora_handler.py:351`) |
| `mean_reversion` | Plugin: `apps/reference/domains/strategies/plugins/mean_reversion.py:14`; Handler: `apps/reference/domains/decision_making/mean_reversion_handler.py:79` | `CMD:PROCESS_STRATEGY` → `MeanReversionHandler._on_process_strategy()` (`apps/reference/domains/decision_making/mean_reversion_handler.py:784`) | **bar-only**: `cmd.tf_sec` must exist and must equal `self.timeframe_sec` (`apps/reference/domains/decision_making/mean_reversion_handler.py:810`, `apps/reference/domains/decision_making/mean_reversion_handler.py:828`) | `EVT:STRATEGY_SIGNAL_PRODUCED` (`apps/reference/domains/decision_making/mean_reversion_handler.py:616`), `EVT:STRATEGY_DECISION_BLOCKED` (`apps/reference/domains/decision_making/mean_reversion_handler.py:451`); **LEGACY** `EVT:TRADE_INTENT_PROPOSED` direct (`apps/reference/domains/decision_making/mean_reversion_handler.py:582`) |

`DecisionMaking` gateway (не стратегія, але критичний компонент для “strategy → execution”):

- Listener: `apps/reference/domains/decision_making/decision_making.py:382`
- Entry: `DecisionMaking._on_strategy_signal_gateway()` (`apps/reference/domains/decision_making/decision_making.py:385`)

---

## 3) Config Map (YAML → key paths → хто читає)

### 3.1. Strategy registry SSOT: assignments + arbitration

- **Файл**: `config/aurora/strategies.yaml`
- **Ключі**:
  - `assignments.<SYMBOL> = [strategy_id...]` (`config/aurora/strategies.yaml:24`)
  - `arbitration.mode/window_ms/priority/logging` (`config/aurora/strategies.yaml:57`)
- **Хто читає**:
  - Завантаження + runtime namespace: `apps/reference/config_loader.py:353` → `apps/reference/config_loader.py:416`
  - StrategyRuntime стартує plugin-и **по факту присутності strategy_id в assignments**: `apps/reference/domains/strategies/registry.py:62` → `apps/reference/domains/strategies/registry.py:99`
  - `DecisionMaking` використовує assignments/arbitration для reject/allow: `apps/reference/domains/decision_making/decision_making.py:1493` → `apps/reference/domains/decision_making/decision_making.py:1584`

### 3.2. Strategy profiles SSOT: policy per strategy_id

**Aurora profile**

- **Файл**: `config/aurora/strategies/aurora.yaml`
- **Ключі**:
  - `aurora.timeframe_sec` (`config/aurora/strategies/aurora.yaml:16`) → `AuroraHandler._load_config()` (`apps/reference/domains/decision_making/aurora_handler.py:127` → `apps/reference/domains/decision_making/aurora_handler.py:145`)
  - `aurora.execution.entry_order_type` / `aurora.execution.entry_tif` (`config/aurora/strategies/aurora.yaml:20`) → `DecisionMaking._propose_trade_intent()` order-policy (`apps/reference/domains/decision_making/decision_making.py:2891` → `apps/reference/domains/decision_making/decision_making.py:2993`)
  - `aurora.assets.<SYMBOL>.enabled` (наприклад `config/aurora/strategies/aurora.yaml:320`) → symbol enable filter в `AuroraHandler._is_symbol_enabled()` (`apps/reference/domains/decision_making/aurora_handler.py:779`)
  - `aurora.decision.*` (thresholds/weights/essential_features/gates/holding_period/anchor_shock_veto, тощо) → читається в `AuroraHandler._load_config()` (`apps/reference/domains/decision_making/aurora_handler.py:147`) і в runtime decision flow (`apps/reference/domains/decision_making/aurora_handler.py:555`)

**Mean Reversion profile**

- **Файл**: `config/aurora/strategies/mean_reversion.yaml`
- **Ключі**:
  - `mean_reversion.timeframe_sec` (`config/aurora/strategies/mean_reversion.yaml:20`) → `MeanReversionHandler._parse_config()` (`apps/reference/domains/decision_making/mean_reversion_handler.py:305`)
  - `mean_reversion.execution.*` (`config/aurora/strategies/mean_reversion.yaml:30`) → `DecisionMaking._propose_trade_intent()` order-policy (`apps/reference/domains/decision_making/decision_making.py:2895`)
  - `mean_reversion.strategy.*` / `mean_reversion.assets.*` / `mean_reversion.regime_thresholds` → стратегія-інстанси per symbol (`apps/reference/domains/decision_making/mean_reversion_handler.py:312` → `apps/reference/domains/decision_making/mean_reversion_handler.py:385`)

**Як profile-и підтягуються**

- `config/aurora/strategies/<strategy_id>.yaml` завантажується **тільки для strategy_id, які реально assigned у `strategies.yaml`**: `apps/reference/config_loader.py:382` → `apps/reference/config_loader.py:416`.

### 3.3. Domain policy, що впливає на стратегії/інтенти

- `config/aurora/domains.yaml:10` (`decision_making.*`) читається в `DecisionMaking.__init__` через `DomainConfigResolver` (`apps/reference/domains/decision_making/decision_making.py:242` → `apps/reference/domains/decision_making/decision_making.py:305`).
- EntryPlan (глобальний, застосовується в gateway до всіх strategy signals): `config/aurora/domains.yaml:20` → `apps/reference/domains/decision_making/decision_making.py:987`.
- Pending entry TTL для LIMIT (valid_for_ms): `config/aurora/domains.yaml:410` → `apps/reference/domains/decision_making/decision_making.py:3013`.
- Order capabilities (що execution підтримує): `config/aurora/domains.yaml:434` → `apps/reference/domains/decision_making/decision_making.py:2922`.
- FeatureEngineering timeframes (які TF рахуються): `config/aurora/domains.yaml:116`.
- FeatureEngineering readiness registry (декларовані warmup.ready ключі): `config/aurora/domains.yaml:182`.
- P0-0 валідація `strategies.aurora.decision.essential_features ⊆ feature_engineering.readiness_registry.declared_keys`: `apps/reference/config_loader.py:1171` → `apps/reference/config_loader.py:1215`.

### 3.4. System / MarketData policy (TTL для bar freshness)

- `config/aurora/system.yaml:21` (`system.market_data.bar_ttl_ms` + `bar_event_age_mode`) читається в TTL gate `DecisionMaking._on_strategy_signal_gateway()` (`apps/reference/domains/decision_making/decision_making.py:923` → `apps/reference/domains/decision_making/decision_making.py:938`).

### 3.5. Instruments SSOT (sizing + constraints)

- `config/aurora/instruments.yaml:7` (`instruments.<SYMBOL>.sizing.margin_pct`, `.execution.target_leverage`, `.step_size/.min_qty/.min_notional`) читається в `DecisionMaking._calculate_position_size()` (`apps/reference/domains/decision_making/decision_making.py:2435` → `apps/reference/domains/decision_making/decision_making.py:2440`).

### 3.6. Legacy cross-strategy coupling (timeframe precedence)

- `ConfigLoader._apply_timeframe_sec_ssot_precedence()` може переписати `strategies.mean_reversion.timeframe_sec` з `strategies.aurora.assets.<SYM>.timeframe_sec` для symbols, assigned до `mean_reversion` (`apps/reference/config_loader.py:1217` → `apps/reference/config_loader.py:1306`).

---

## 4) Input Contract Sheet (що реально доступно)

### 4.1. `EVT:FEATURES_CALCULATED` (FeatureEngineering → DM + RegimeDetector + Aurora wrapper)

- **Емісія**: `apps/reference/domains/feature_engineering/feature_engineering.py:1019`
- **Payload (факт з коду)**: `ts`, `symbol`, `tf_sec`, `features`, `warmup`, `price_motion`, `bar` (`apps/reference/domains/feature_engineering/feature_engineering.py:1002`).
- **Schema (заявлений)**: `apps/reference/domains/feature_engineering/schemas/features_calculated_v1.json:1`
- **Schema mismatch (факт)**: schema має `additionalProperties=false` на root (`apps/reference/domains/feature_engineering/schemas/features_calculated_v1.json:132`) і **не описує** поле `bar`, але code додає `bar` у payload (`apps/reference/domains/feature_engineering/feature_engineering.py:1009`).

### 4.2. `CMD:PROCESS_STRATEGY` (FeatureEngineering → strategies)

- **Gates на емісію (fail-closed)**: `apps/reference/domains/feature_engineering/feature_engineering.py:1021` → `apps/reference/domains/feature_engineering/feature_engineering.py:1046`.
- **Schema**: `apps/reference/domains/feature_engineering/schemas/cmd_process_strategy_v1.json:1`.
- **Фактичний payload**: `symbol`, `tf_sec`, `bar_close_ts`, `bar`, `features`, `warmup`, `regime` (`apps/reference/domains/feature_engineering/feature_engineering.py:1129` → `apps/reference/domains/feature_engineering/feature_engineering.py:1137`).
- **EP-01.1 snapshots (всередині cmd.features)**:
  - `features.volatility.{atr_14,atr_ready,...}` (`apps/reference/domains/feature_engineering/feature_engineering.py:1116`)
  - `features.liquidity.obi_close` (`apps/reference/domains/feature_engineering/feature_engineering.py:1125`)

### 4.3. `EVT:REGIME_DETECTED` (RegimeDetector → DM + FE cache + strategies)

- RegimeDetector працює **тільки на basis TF**: `tf_sec == basis_tf_sec` (`apps/reference/domains/regime_detector/regime_detector.py:208`).
- basis TF береться з `config/aurora/regime.yaml:1`.
- Наслідок (факт): regime snapshot, який FE інжектить у `CMD:PROCESS_STRATEGY` (`apps/reference/domains/feature_engineering/feature_engineering.py:1136`), походить з basis TF (за замовчуванням 300s), навіть якщо `CMD` для 180s.

### 4.4. `EVT:STRATEGY_SIGNAL_PRODUCED` (strategies → DecisionMaking gateway)

**Мінімальний контракт (вимога DecisionMaking)**

- `readiness.warmup_ok` must exist and must be `True` — інакше reject (`apps/reference/domains/decision_making/decision_making.py:428` → `apps/reference/domains/decision_making/decision_making.py:465`).
- `strategy_id`, `symbol`, `side` must exist — інакше reject (`apps/reference/domains/decision_making/decision_making.py:404` → `apps/reference/domains/decision_making/decision_making.py:419`).
- `price_ctx.entry_price` must exist and be > 0 — інакше reject (`apps/reference/domains/decision_making/decision_making.py:873` → `apps/reference/domains/decision_making/decision_making.py:880`).

**Aurora signal payload (факт)**

- `volatility` + `liquidity` пробрасываются из cmd.features (для EntryPlan): `apps/reference/domains/decision_making/aurora_handler.py:1163`.
- `tf_sec` проставляється як `self.timeframe_sec`: `apps/reference/domains/decision_making/aurora_handler.py:1166`.

**MeanReversion signal payload (факт)**

- `price_ctx.stop_price/target_price` є, але `volatility/liquidity` відсутні (`apps/reference/domains/decision_making/mean_reversion_handler.py:603` → `apps/reference/domains/decision_making/mean_reversion_handler.py:607`).

### 4.5. `EVT:TRADE_INTENT_PROPOSED` (DecisionMaking → ExecutionPosition)

- `DecisionMaking` емісить `EVT:TRADE_INTENT_PROPOSED` після gate pipeline (`apps/reference/domains/decision_making/decision_making.py:963`).
- Schema: `apps/reference/domains/decision_making/schemas/trade_intent_v1.json:1`.
- ORDER-POLICY-01 (schema): `order.order_type` REQUIRED (`apps/reference/domains/decision_making/schemas/trade_intent_v1.json:124`) і для LIMIT потрібні `tif` + `valid_for_ms` (`apps/reference/domains/decision_making/schemas/trade_intent_v1.json:279`).

---

## 5) Per-Strategy Deep Dive

### 5.1. `aurora`

**Purpose**

- Bar-driven scoring strategy на `timeframe_sec=300` (`config/aurora/strategies/aurora.yaml:16`) з emission `EVT:STRATEGY_SIGNAL_PRODUCED` (`apps/reference/domains/decision_making/aurora_handler.py:1174`).

**Subscriptions**

- `CMD:PROCESS_STRATEGY` (primary), `EVT:REGIME_DETECTED` (cache), `EVT:FEATURES_CALCULATED` (data-only warmup cache) — `apps/reference/domains/strategies/plugins/aurora_builtin.py:38` → `apps/reference/domains/strategies/plugins/aurora_builtin.py:49`.

**Signal Inputs (факти з коду)**

- `cmd.tf_sec`, `cmd.bar_close_ts` (strict validation): `apps/reference/domains/decision_making/aurora_handler.py:405` → `apps/reference/domains/decision_making/aurora_handler.py:467`.
- `cmd.features`:
  - must-have: `price` (`apps/reference/domains/decision_making/aurora_handler.py:548`)
  - used in veto: `macro_resid` (`apps/reference/domains/decision_making/aurora_handler.py:577`)
  - scoring consumes multiple features через kernel (`apps/reference/domains/decision_making/aurora_scoring_kernel.py:86`)
- `cmd.warmup.full_ready` (fail-closed): `apps/reference/domains/decision_making/aurora_handler.py:523` → `apps/reference/domains/decision_making/aurora_handler.py:545`.

**TF Contract**

- `cmd.tf_sec == config.strategies.aurora.timeframe_sec` (`apps/reference/domains/decision_making/aurora_handler.py:443`, `config/aurora/strategies/aurora.yaml:16`).

**Strategy-level gates (до gateway)**

- Warmup full_ready (hard block): `apps/reference/domains/decision_making/aurora_handler.py:523`.
- Kernel defers якщо missing readiness keys / essential not ready: `apps/reference/domains/decision_making/aurora_scoring_kernel.py:153` → `apps/reference/domains/decision_making/aurora_scoring_kernel.py:179` (обробка deferred далі в handler).
- Holding period / reentry cooldown: `apps/reference/domains/decision_making/aurora_handler.py:670` → `apps/reference/domains/decision_making/aurora_handler.py:725`.
- Anchor shock veto: `apps/reference/domains/decision_making/aurora_handler.py:562` → `apps/reference/domains/decision_making/aurora_handler.py:764`.
- Vol-adj gates (Anti-Flat/FOMO): `apps/reference/domains/decision_making/aurora_handler.py:727` → `apps/reference/domains/decision_making/aurora_handler.py:733`.

**Output Intent (що виходить зі стратегії)**

- Стратегія не формує `EVT:TRADE_INTENT_PROPOSED` напряму; вона формує `EVT:STRATEGY_SIGNAL_PRODUCED` з `price_ctx.entry_price` + `tf_sec` + readiness (`apps/reference/domains/decision_making/aurora_handler.py:1144` → `apps/reference/domains/decision_making/aurora_handler.py:1167`).

**Execution інтеграція (через DecisionMaking)**

- ORDER-POLICY-01: `strategy.execution.entry_order_type/tif` MUST be set (strategy SSOT) — `apps/reference/domains/decision_making/decision_making.py:2891` → `apps/reference/domains/decision_making/decision_making.py:2993`, source YAML `config/aurora/strategies/aurora.yaml:20`.
- `valid_for_ms` для LIMIT derived from `domains.execution_position.pending_entry_ttl.ttl_by_tf_sec[tf_sec]` — `apps/reference/domains/decision_making/decision_making.py:3013`, source YAML `config/aurora/domains.yaml:410`.

**Config Keys Used (мінімальний перелік, факт)**

- `strategies.aurora.timeframe_sec`: `config/aurora/strategies/aurora.yaml:16` → `apps/reference/domains/decision_making/aurora_handler.py:145`
- `strategies.aurora.execution.*`: `config/aurora/strategies/aurora.yaml:20` → `apps/reference/domains/decision_making/decision_making.py:2897`
- `strategies.aurora.assets.<SYMBOL>.enabled`: `config/aurora/strategies/aurora.yaml:320` → `apps/reference/domains/decision_making/aurora_handler.py:784`
- `strategies.aurora.decision.gates.motion_window_sec`: `config/aurora/strategies/aurora.yaml:145` → `apps/reference/domains/decision_making/aurora_handler.py:983`
- `strategies.aurora.decision.essential_features`: `config/aurora/strategies/aurora.yaml:116` → `apps/reference/config_loader.py:1206`

**Mismatch / Bugs**

- **S1 (P0): Vol-adj gates “фантомні”**: `AuroraHandler` шукає `features.price_motion.pm_norm_{motion_window_sec}s` (`apps/reference/domains/decision_making/aurora_handler.py:979` → `apps/reference/domains/decision_making/aurora_handler.py:985`), але:
  - `CMD:PROCESS_STRATEGY` schema не містить `price_motion` у `features` (`apps/reference/domains/feature_engineering/schemas/cmd_process_strategy_v1.json:76`)
  - фактичний `cmd_payload["features"]` не включає `price_motion` (`apps/reference/domains/feature_engineering/feature_engineering.py:1134`)
  - `motion_window_sec=900` (`config/aurora/strategies/aurora.yaml:145`), але легальний `price_motion` має тільки `pm_norm_{10,60,300}s` (`schemas/features_price_motion_v1.json:15`).
  - Результат по коду: gate завжди “skip” через `motion_norm_sigma is None` (`apps/reference/domains/decision_making/aurora_handler.py:1019` → `apps/reference/domains/decision_making/aurora_handler.py:1022`).
- **S2 (P1): Strategy assignment conflict (DOGE/XRP)**: `strategies.yaml` назначає `DOGEUSDT`/`XRPUSDT` тільки на `mean_reversion` (`config/aurora/strategies.yaml:33`), але `aurora.assets` має `DOGEUSDT.enabled=true` (`config/aurora/strategies/aurora.yaml:320`) і `XRPUSDT.enabled=true` (`config/aurora/strategies/aurora.yaml:385`). `AuroraHandler` фільтрує symbols через `aurora.assets`, а не через `strategies_registry.assignments` (`apps/reference/domains/decision_making/aurora_handler.py:779`). Це дає `EVT:STRATEGY_SIGNAL_PRODUCED` для не-assigned symbols, які потім відсікає arbitration в gateway (`apps/reference/domains/decision_making/decision_making.py:469` та `apps/reference/domains/decision_making/decision_making.py:1531`).
- **S3 (P2): `aurora.decision.symbols_to_track` не використовується кодом**: присутній у YAML (`config/aurora/strategies/aurora.yaml:32`), але відсутні будь-які читання в `apps/reference` (repowide grep дає тільки `trading.symbols_to_track` в `apps/reference/config_loader.py:546`).
- **S4 (P2): `strategies.aurora.enabled` не впливає на handler**: `AuroraHandler._is_symbol_enabled` не перевіряє `aurora.enabled` (`apps/reference/domains/decision_making/aurora_handler.py:781`).

---

### 5.2. `mean_reversion`

**Purpose**

- Bar-based MR (BB+RSI+ATR) strategy instance per symbol (`apps/reference/domains/feature_engineering/mean_reversion_strategy.py:204`) з інтеграцією в DM через `EVT:STRATEGY_SIGNAL_PRODUCED` (`apps/reference/domains/decision_making/mean_reversion_handler.py:616`).

**Activation SSOT**

- Assigned symbols беруться з `config.strategies_registry.assignments` (`apps/reference/domains/decision_making/mean_reversion_handler.py:211` → `apps/reference/domains/decision_making/mean_reversion_handler.py:217`).
- Fail-closed якщо MR assigned, але `config.strategies.mean_reversion` missing або `mean_reversion.enabled=false` (`apps/reference/domains/decision_making/mean_reversion_handler.py:236` → `apps/reference/domains/decision_making/mean_reversion_handler.py:255`).

**Subscriptions**

- `CMD:PROCESS_STRATEGY` (primary), `EVT:BAR_CLOSED` (data-only), `EVT:REGIME_DETECTED` (cache) — `apps/reference/domains/decision_making/mean_reversion_handler.py:185` → `apps/reference/domains/decision_making/mean_reversion_handler.py:188`.

**Signal Inputs (факт)**

- `cmd.bar` (required) → будується `Bar` DTO (`apps/reference/domains/decision_making/mean_reversion_handler.py:849` → `apps/reference/domains/decision_making/mean_reversion_handler.py:888`).
- `cmd.regime` optional: якщо нема — бере cache з `EVT:REGIME_DETECTED` (`apps/reference/domains/decision_making/mean_reversion_handler.py:907` → `apps/reference/domains/decision_making/mean_reversion_handler.py:917`).
- `cmd.features.liquidity_kappa` optional: використовується для liquidity gate (`apps/reference/domains/decision_making/mean_reversion_handler.py:893` → `apps/reference/domains/decision_making/mean_reversion_handler.py:899` + gate `apps/reference/domains/decision_making/mean_reversion_handler.py:762` → `apps/reference/domains/decision_making/mean_reversion_handler.py:778`).
- `cmd.warmup` **не використовується** для readiness контракту; payload readiness завжди `warmup_ok=True` (`apps/reference/domains/decision_making/mean_reversion_handler.py:597`).

**TF Contract**

- `cmd.tf_sec` must exist (`apps/reference/domains/decision_making/mean_reversion_handler.py:810`) і must equal `self.timeframe_sec` (`apps/reference/domains/decision_making/mean_reversion_handler.py:828`), де `self.timeframe_sec = config.strategies.mean_reversion.timeframe_sec` (`apps/reference/domains/decision_making/mean_reversion_handler.py:305`, `config/aurora/strategies/mean_reversion.yaml:20`).

**Strategy-level gates (до gateway)**

- Strict required fields: `tf_sec`, `bar_close_ts`, `bar` — fail-closed з `TRADE_INTENT_REJECTED` WAL (`apps/reference/domains/decision_making/mean_reversion_handler.py:810` → `apps/reference/domains/decision_making/mean_reversion_handler.py:865`).
- Liquidity gate: `liquidity_kappa >= kappa_min` (`apps/reference/domains/decision_making/mean_reversion_handler.py:773` → `apps/reference/domains/decision_making/mean_reversion_handler.py:777`).
- Regime gate фактично всередині MR strategy через `map_to_flat_regime` (fail-closed на non-flat) (`apps/reference/domains/feature_engineering/regime_mapping.py:108` → `apps/reference/domains/feature_engineering/regime_mapping.py:127`).

**Output Intent**

- `EVT:STRATEGY_SIGNAL_PRODUCED` з `price_ctx.entry/stop/target` (`apps/reference/domains/decision_making/mean_reversion_handler.py:591` → `apps/reference/domains/decision_making/mean_reversion_handler.py:613`).

**Execution інтеграція (через DecisionMaking)**

- ORDER-POLICY-01 для MR береться з `strategies.mean_reversion.execution.entry_order_type` (`config/aurora/strategies/mean_reversion.yaml:30`) через `DecisionMaking._propose_trade_intent()` (`apps/reference/domains/decision_making/decision_making.py:2895`).
- Але перед формуванням trade intent gateway виконує EntryPlan, якщо `domains.decision_making.entry_plan.enabled=true` (`config/aurora/domains.yaml:21`) і може **reject** при `require_atr=true` (`config/aurora/domains.yaml:29`) коли `atr_ready=False` (`apps/reference/domains/decision_making/decision_making.py:1007` → `apps/reference/domains/decision_making/decision_making.py:1031`).

**Mismatch / Bugs**

- **MR1 (P0): MR signals не несуть `volatility/atr_ready`, але EntryPlan в gateway вимагає ATR**:
  - gateway читає `pld.volatility.atr_ready` (`apps/reference/domains/decision_making/decision_making.py:979` → `apps/reference/domains/decision_making/decision_making.py:984`)
  - MR payload не містить `volatility` (`apps/reference/domains/decision_making/mean_reversion_handler.py:591`)
  - domain config: `entry_plan.enabled=true` + `require_atr=true` (`config/aurora/domains.yaml:21`, `config/aurora/domains.yaml:29`)
  - наслідок: `EntryPlan.validate_inputs(... atr_ready=False ...)` → REJECT (`apps/reference/domains/decision_making/decision_making.py:1007` → `apps/reference/domains/decision_making/decision_making.py:1031`).
- **MR2 (P1): MR depends on FE warmup.full_ready even when it doesn’t use most FE features**: FE не емісить `CMD:PROCESS_STRATEGY` поки `warmup.full_ready != True` (`apps/reference/domains/feature_engineering/feature_engineering.py:1042`), а MR trigger — це саме CMD (`apps/reference/domains/decision_making/mean_reversion_handler.py:784`).
- **MR3 (P2): Док-коментарі “1m vs 3m” не консистентні**:
  - `strategies.yaml` описує MR як “1m bars” (`config/aurora/strategies.yaml:22`)
  - MR profile каже “3m” і `timeframe_sec=180` (`config/aurora/strategies/mean_reversion.yaml:2`, `config/aurora/strategies/mean_reversion.yaml:20`)
  - MR strategy class name: `MeanReversion1mStrategy` (`apps/reference/domains/feature_engineering/mean_reversion_strategy.py:204`).
- **MR4 (P2): Частина risk-полів у `mean_reversion.risk` не використовується**: codepath читає тільки `position_size_usd` у direct mode (`apps/reference/domains/decision_making/mean_reversion_handler.py:534` → `apps/reference/domains/decision_making/mean_reversion_handler.py:543`), інші поля `MRRiskConfig` у handler/strategy не використовуються (repowide grep не знаходить `expected_pnl_multiplier`, `fees_pct`, `slippage_pct` тощо).

---

## 6) Symbol Assignment & Arbitration (Expected vs Actual)

**SSOT assignments (config)**

- `ETHUSDT` → `[aurora]` (`config/aurora/strategies.yaml:26`)
- `SOLUSDT` → `[aurora]` (`config/aurora/strategies.yaml:30`)
- `BTCUSDT` → `[aurora]` (`config/aurora/strategies.yaml:43`)
- `DOGEUSDT` → `[mean_reversion]` (`config/aurora/strategies.yaml:34`)
- `XRPUSDT` → `[mean_reversion]` (`config/aurora/strategies.yaml:38`)

**Arbitration rules (code)**

- Якщо `symbol` відсутній у registry → block (fail-closed) (`apps/reference/domains/decision_making/decision_making.py:1522` → `apps/reference/domains/decision_making/decision_making.py:1528`).
- Якщо `strategy_id` не в assignments[symbol] → block (`apps/reference/domains/decision_making/decision_making.py:1531` → `apps/reference/domains/decision_making/decision_making.py:1536`).
- priority + windowed “winner claim” (`apps/reference/domains/decision_making/decision_making.py:1545` → `apps/reference/domains/decision_making/decision_making.py:1578`), config: `config/aurora/strategies.yaml:60`.

**Чи DM генерує сигнали для не-assigned символів?**

- `DecisionMaking` генерує `EVT:TRADE_INTENT_PROPOSED` **тільки** через gateway і arbitration gate блокує не-assigned strategy (`apps/reference/domains/decision_making/decision_making.py:469` + `apps/reference/domains/decision_making/decision_making.py:1531`).
- Але `AuroraHandler` може емісити **strategy signal** для symbols, які є `aurora.assets.*.enabled=true` навіть якщо вони не assigned до aurora (див. `DOGEUSDT`/`XRPUSDT` у `config/aurora/strategies/aurora.yaml:320` та `config/aurora/strategies/aurora.yaml:385`).

Висновок (однозначно): **це SSOT-конфлікт/bug у прив’язках** (strategy handler не узгоджений з registry assignments), бо:
- MR handler прямо декларує assignment як activation SSOT (`apps/reference/domains/decision_making/mean_reversion_handler.py:17`),
- DM arbitration теж трактує registry як fail-closed SSOT (`apps/reference/domains/decision_making/decision_making.py:1522`),
- але AuroraHandler бере allowlist з `aurora.assets` (`apps/reference/domains/decision_making/aurora_handler.py:779`), що дозволяє “зайві” symbols.

---

## 7) Order Policy Table (SSOT: no defaults)

| strategy_id | entry_order_type | entry_tif | Where enforced |
|---|---|---|---|
| `aurora` | `LIMIT` (`config/aurora/strategies/aurora.yaml:21`) | `GTX` (`config/aurora/strategies/aurora.yaml:22`) | `DecisionMaking._propose_trade_intent()` (missing order_type reject: `apps/reference/domains/decision_making/decision_making.py:2903`; LIMIT tif required: `apps/reference/domains/decision_making/decision_making.py:2944`) |
| `mean_reversion` | `MARKET` (`config/aurora/strategies/mean_reversion.yaml:31`) | `null` (`config/aurora/strategies/mean_reversion.yaml:32`) | `DecisionMaking._propose_trade_intent()` (MARKET requires tif=null: `apps/reference/domains/decision_making/decision_making.py:2977`) |

LIMIT-only `valid_for_ms`:

- `DecisionMaking` розраховує `valid_for_ms` **тільки для LIMIT** з `domains.execution_position.pending_entry_ttl.ttl_by_tf_sec` (`apps/reference/domains/decision_making/decision_making.py:2994` → `apps/reference/domains/decision_making/decision_making.py:3062`, config `config/aurora/domains.yaml:410`).

---

## 8) Known Issues / Mismatches (P0/P1/P2)

**P0**

1. Aurora vol-adj gates фактично не працюють: очікують `price_motion.pm_norm_900s` у `cmd.features`, але `CMD` не містить `price_motion` і немає 900s window у schema (`apps/reference/domains/decision_making/aurora_handler.py:983`, `apps/reference/domains/feature_engineering/feature_engineering.py:1134`, `schemas/features_price_motion_v1.json:15`, `config/aurora/strategies/aurora.yaml:145`).
2. MeanReversion signals у gateway конфліктують з EntryPlan(require_atr=true): MR не передає `pld.volatility.atr_ready`, тому `EntryPlan.validate_inputs` fail-closed → REJECT (`apps/reference/domains/decision_making/decision_making.py:1007`, `apps/reference/domains/decision_making/mean_reversion_handler.py:591`, `config/aurora/domains.yaml:29`).
3. EVT:FEATURES_CALCULATED schema mismatch: payload включає `bar`, але schema forbids unknown keys (`apps/reference/domains/feature_engineering/feature_engineering.py:1009`, `apps/reference/domains/feature_engineering/schemas/features_calculated_v1.json:132`).

**P1**

1. Aurora emits strategy signals for DOGE/XRP even though not assigned (SSOT conflict між `strategies.yaml` і `aurora.assets` enablelist): `config/aurora/strategies.yaml:33` vs `config/aurora/strategies/aurora.yaml:320`, причина — `AuroraHandler._is_symbol_enabled` не використовує registry (`apps/reference/domains/decision_making/aurora_handler.py:779`).
2. Global FE warmup.full_ready gate блокує `CMD:PROCESS_STRATEGY` для MR навіть якщо MR не потребує більшості FE features (`apps/reference/domains/feature_engineering/feature_engineering.py:1042`).
3. Risk schema drift: `risk_assessment_v1.json` не містить `risk_score`, але DM gateway очікує `risk_parameters.risk_score` і defer-ить при missing (`apps/reference/domains/risk_management/schemas/risk_assessment_v1.json:16`, `apps/reference/domains/decision_making/decision_making.py:561` → `apps/reference/domains/decision_making/decision_making.py:588`).

**P2**

1. Док/коментарі по MR TF (1m vs 3m) не узгоджені (див. MR3).
2. `ConfigLoader._apply_timeframe_sec_ssot_precedence` дозволяє задавати MR timeframe через `aurora.assets.<SYM>.timeframe_sec` (крос-стратегічна залежність) — `apps/reference/config_loader.py:1217`.
3. Частина MR risk параметрів не використовується в runtime (див. MR4).

---

## Appendix: reproducibility pointers (grep anchors)

- Стратегії/handlers: `rg -n \"StrategyRuntime|StrategyPluginRegistry|AuroraHandler|MeanReversionHandler\" apps/reference -S`
- Gateway: `rg -n \"EVT:STRATEGY_SIGNAL_PRODUCED\" apps/reference/domains/decision_making/decision_making.py -n`
- CMD emission gates: `rg -n \"CMD:PROCESS_STRATEGY rejected\" apps/reference/domains/feature_engineering/feature_engineering.py -n`
- Order policy: `rg -n \"ORDER-POLICY-01\" apps/reference/domains/decision_making/decision_making.py -n`
