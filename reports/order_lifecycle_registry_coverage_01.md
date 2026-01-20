# ORDER-LIFECYCLE-AUDIT-01 — Phase 1: Config & Registry Map (SSOT контракт)
Дата: 2026-01-12  
Scope: **audit-only** (жодних змін у прод-коді)

## 0) Відправні SSOT-файли (as requested)
- `config/aurora/domains.yaml`
- `config/aurora/strategies/aurora.yaml`, `config/aurora/strategies/mean_reversion.yaml`
- `apps/reference/dictionaries/verb_registry_v1.yaml`
- `schemas/*_v1.json`, `apps/reference/domains/**/schemas/*_v1.json`

---

## 1) SSOT таблиця (order policy / capabilities / TTL)

### 1.1 Global execution capabilities (domains.yaml)
Джерело: `config/aurora/domains.yaml` (секція `execution_position.order_capabilities`)

| SSOT ключ | Значення | Коментар |
|---|---|---|
| `supported_order_types` | `["LIMIT","MARKET"]` | Глобальна підтримка типів |
| `supported_tif` | `["GTC","GTX","IOC","FOK"]` | GTX = post-only/maker-only |

### 1.2 Strategy-level execution policy (strategies/*.yaml)
Джерела:  
- `config/aurora/strategies/aurora.yaml` → `aurora.execution`  
- `config/aurora/strategies/mean_reversion.yaml` → `mean_reversion.execution`

| Strategy | `entry_order_type` | `entry_tif` | Intended mode |
|---|---:|---:|---|
| `aurora` | `LIMIT` | `GTX` | LIMIT-first, maker-only style |
| `mean_reversion` | `MARKET` | `null` | MARKET-first, fast entry |

### 1.3 LIMIT pending-entry TTL by timeframe (domains.yaml)
Джерело: `config/aurora/domains.yaml` → `execution_position.pending_entry_ttl`

| `tf_sec` | `ttl_sec` | `valid_for_ms` |
|---:|---:|---:|
| 180 | 45 | 45000 |
| 300 | 60 | 60000 |
| 900 | 180 | 180000 |

Fail-closed контракт в конфізі:
- `reject_unknown_tf: true` (якщо tf не в мапі → reject intent, без дефолтів)

### 1.4 Maker-only entry policy switch (domains.yaml)
Джерело: `config/aurora/domains.yaml` → `execution_position.maker_only_entry`

| SSOT ключ | Значення | Коментар |
|---|---:|---|
| `enabled` | `false` | Але `aurora` strategy вже задає `GTX` на рівні policy |
| `tif_value` | `GTX` | Пост-онлі |
| `reject_on_fail` | `true` | Явно: **NO fallback to market** |

### 1.5 Watchdog TTLs (domains.yaml + trading.yaml) — SSOT risk
Є дублювання/переозначення TTL в різних місцях:
- `config/aurora/domains.yaml` → `execution_position.watchdog.fill_ttl_ms: 30000`
- `config/aurora/trading.yaml` → `trading.execution.watchdog.fill_ttl_ms: 60000`
- `config/aurora/trading.yaml` → `trading.orders.default_ttl_seconds: 15` (в коді може override’ити `fill_ttl_ms`)

Це **не SSOT** (див. ризики нижче): TTL для ордерів може змінюватися залежно від того, який шлях конфіга прочитав execution.

---

## 2) Контрактні поля (TradeIntent / CMD:OPEN)

### 2.1 EVT:TRADE_INTENT_PROPOSED — schema (існує, але НЕ підв’язана у verb registry)
Schema: `apps/reference/domains/decision_making/schemas/trade_intent_v1.json`

**Required (top-level)**:
- `instrument`, `side`, `p`, `payoff_ratio_r`, `tca_budget`, `risk_budget`, `size`, `order`, `why`, `dto_version`, `schema_ref`

**Required (`order` object)**:
- `price_ref`, `qty`, `reduce_only`, `order_type`

**Критичні прогалини контракту (schema-level):**
- `additionalProperties` **відсутній** (тобто schema **не strict**: прийме зайві поля).
- Немає conditional-логіки:
  - LIMIT **не вимагає** `order.price` на рівні schema (хоча downstream реально вимагає).
  - LIMIT **не вимагає** `order.tif`, і MARKET **не забороняє** `tif` (схема це лише описує текстом).
- `valid_for_ms: null` трактується як “use global fill_ttl_ms” → це **fallback** (див. ризики).

### 2.2 CMD:OPEN — JSON schema відсутня, але є strict Pydantic модель
Код-контракт: `apps/reference/domains/execution_position/fsm_open.py` → `CmdOpenPayload` (`extra='forbid'`)

**Required (Pydantic)**:
- `symbol`, `side` (`BUY|SELL`), `qty` (Decimal string), `order_type` (`MARKET|LIMIT`)

**Optional**:
- `price`, `tif`, `valid_for_ms`, `price_ref`, `stop_price`, `target_price`, `sl_pct`, `idempotent_key`, `rid`

**Важливо (fallbacks в коді):**
- `tif` якщо `None` → downstream робить `tif = "GTC"` (silent default).

---

## 3) Registry coverage (verbs ↔ schemas ↔ owners) — ордерний ланцюг

SSOT registry: `apps/reference/dictionaries/verb_registry_v1.yaml`

Легенда `strict?`:
- ✅ strict: root `additionalProperties: false`
- ⚠️ mixed: `oneOf`/перехідні схеми (частина strict, частина ні)
- ❌ non-strict: `additionalProperties` missing/true
- ∅ missing: registry не вказує schema

| op:verb | owner (registry) | schema (registry) | strict? | Producer (code) | Consumer (code) |
|---|---|---|---:|---|---|
| `EVT:BAR_CLOSED` | `market_data` | `schemas/bar_closed_v1.json` | ✅ | `apps/reference/domains/market_data/bar_aggregator.py` | `apps/reference/domains/feature_engineering/feature_engineering.py`, `apps/reference/domains/decision_making/mean_reversion_handler.py` |
| `EVT:FEATURES_CALCULATED` | `feature_engineering` | `apps/reference/domains/feature_engineering/schemas/features_calculated_v1.json` | ✅ | `apps/reference/domains/feature_engineering/feature_engineering.py` | `apps/reference/domains/decision_making/decision_making.py`, `apps/reference/domains/strategies/plugins/aurora_builtin.py` |
| `CMD:PROCESS_STRATEGY` | `strategies` | `apps/reference/domains/feature_engineering/schemas/cmd_process_strategy_v1.json` | ✅ | `apps/reference/domains/feature_engineering/feature_engineering.py` | `apps/reference/domains/strategies/plugins/aurora_builtin.py` |
| `EVT:STRATEGY_SIGNAL_PRODUCED` | `decision_making` | ∅ | ∅ | `apps/reference/domains/decision_making/aurora_handler.py`, `apps/reference/domains/decision_making/mean_reversion_handler.py` | `apps/reference/domains/decision_making/decision_making.py` |
| `EVT:TRADE_INTENT_PROPOSED` | `decision_making` | ∅ | ∅ | `apps/reference/domains/decision_making/decision_making.py` | `apps/reference/main.py` (AuroraBridge) |
| `EVT:TRADE_INTENT_REJECTED` | `decision_making` | `schemas/trade_intent_rejected_v1.json` | ✅ | `apps/reference/domains/decision_making/decision_making.py` | observability/WAL/tools |
| `EVT:INTENT_DEFERRED` | `decision_making` | `schemas/intent_deferred_v1.json` | ⚠️ | `apps/reference/domains/decision_making/decision_making.py`, `apps/reference/main.py` | `apps/reference/main.py` (AuroraBridge) |
| `CMD:OPEN` | `execution_position` | ∅ | ∅ | `apps/reference/main.py` (AuroraBridge) | `apps/reference/domains/execution_position/fsm_open.py` |
| `DEC:OPEN` | `execution_position` | ∅ | ∅ | `apps/reference/domains/execution_position/fsm_open.py` | `apps/reference/domains/execution_position/fsm.py` (ExecPosFSM) |
| `EVT:ORDER_PLACED` | `execution_position` | ∅ | ∅ | `apps/reference/domains/execution_position/fsm.py` (OrderLoggerV1 write) | tools/analytics (`tools/log_audit.py`, `tools/analyze_health.py`) |
| `EVT:ORDER_STATE_CHANGED` | `unknown` | ∅ | ∅ | `apps/reference/adapters/binance_ws_client.py` | `apps/reference/domains/execution_position/fsm.py` (cancel/expire handler) |
| `EVT:ORDER_REJECTED` | `unknown` | ∅ | ∅ | `apps/reference/domains/execution_position/fsm.py`, `apps/reference/adapters/binance_ws_client.py` | downstream DM + obs |
| `EVT:TRADE_EXECUTED` | `position_tracking` | `apps/reference/domains/position_tracking/schemas/trade_executed_v1.json` | ✅ | `apps/reference/adapters/binance_ws_client.py` (+ Watchdog polling hook) | `apps/reference/domains/position_tracking/position_tracking.py`, `apps/reference/domains/execution_position/fsm.py` (manage flow) |
| `EVT:REGIME_DETECTED` | `regime_detector` | `apps/reference/domains/regime_detector/schemas/regime_detected_v1.json` | ✅ | `apps/reference/domains/regime_detector/regime_detector.py` | `apps/reference/domains/decision_making/decision_making.py`, `apps/reference/domains/execution_position/fsm.py` |

### 3.1 “Schema exists but not wired in registry” (order-related)
В `schemas/` є strict схеми, але verb registry їх не використовує:
- `schemas/order_rejected_event_v1.json` (strict) — registry для `EVT:ORDER_REJECTED` має `schema: null`
- `schemas/order_clipped_event_v1.json` (strict) — registry для `EVT:ORDER_CLIPPED` має `schema: null`
- `schemas/portfolio_state_v1.json` (але вона **non-strict**, `additionalProperties: true`) — registry для `EVT:PORTFOLIO_STATE_UPDATED` має `schema: null`

---

## 4) Ризики (NO “silent fallbacks”)

### 4.1 Fallbacks, які прямо небезпечні для LIMIT
1) **`CMD:OPEN.tif` default → `GTC`**  
   - Bridge прямо каже: `tif: null means execution_position will apply default (GTC)` (`apps/reference/main.py`).  
   - OpenFlowFSM робить `tif = validated_pld.tif or "GTC"` (`apps/reference/domains/execution_position/fsm_open.py`).  
   Ризик: LIMIT-maker policy може “тихо” деградувати в GTC (taker fills/fees/slippage) без явного сигналу помилки.

2) **`DEC:OPEN.order_type` default → `MARKET`**  
   - В `_execute_decision`: `order_type = decision.pld.get("order_type", "MARKET")` (`apps/reference/domains/execution_position/fsm.py`).  
   Ризик: якщо десь загубився `order_type`, система може випадково поставити MARKET.

3) **TTL SSOT drift (multiple sources + overrides)**  
   - `domains.yaml` vs `trading.yaml` vs `trading.orders.default_ttl_seconds` override.  
   Ризик: LIMIT pending TTL може трактуватися як “fill TTL для всіх типів” і змінюватися неочікувано.

### 4.2 Contract gaps (registry/schema)
1) **`EVT:TRADE_INTENT_PROPOSED` не має schema у verb registry**  
   Ризик: відсутність contract-first контрольної точки на ключовому boundary (DM → Bridge).

2) **`CMD:OPEN` / `DEC:OPEN` не мають JSON schema у verb registry**  
   Ризик: відсутній SSOT контракт для найкритичніших команд/рішень; Pydantic-модель існує, але це не governance-level registry.

3) **`trade_intent_v1.json` не strict** (`additionalProperties` missing)  
   Ризик: “тихі” поля/формати можуть накопичувати дрейф і ламати downstream (особливо LIMIT-specific поля: `order_type`, `tif`, `valid_for_ms`, `price`).

---

## 5) Рекомендований fail-closed курс (без імплементації в цьому пакеті)
1) `EVT:TRADE_INTENT_PROPOSED`: додати `schema` у `apps/reference/dictionaries/verb_registry_v1.yaml` і зробити `trade_intent_v1.json` strict (`additionalProperties:false`) + conditional `if/then` для LIMIT/MARKET (price/tif/valid_for_ms).
2) `CMD:OPEN`, `DEC:OPEN`: завести `cmd_open_v1.json`, `dec_open_v1.json` (strict) + зареєструвати в verb registry.
3) Заборонити будь-який default для `order_type`, `tif`, `price`, `valid_for_ms` на межі доменів: **fail-closed** через Pydantic/JSON schema.

