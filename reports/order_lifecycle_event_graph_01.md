# ORDER-LIFECYCLE-AUDIT-01 — Phase 2: Event Graph (intent → біржа) + state
Дата: 2026-01-12  
Фокус: bar-driven ланцюг, з явним розділенням MARKET vs LIMIT points

---

## 1) Mermaid (high-level graph)

```mermaid
flowchart TD
  %% ========= Market data =========
  MD[market_data\nBarAggregator] -->|EVT:BAR_CLOSED| FE[feature_engineering\nFeatureEngineering]

  %% ========= Feature engineering =========
  FE -->|EVT:FEATURES_CALCULATED| DM[decision_making\nDecisionMaking]
  FE -->|CMD:PROCESS_STRATEGY\n(bar-driven trigger)| STR[strategies\nAuroraBuiltinPlugin / MR plugin]

  %% ========= Strategies =========
  STR -->|EVT:STRATEGY_SIGNAL_PRODUCED| DM

  %% ========= Decision making =========
  DM -->|EVT:DECISION_TRACE_EMITTED\n(monitoring)| OBS[observability/WAL]
  DM -->|EVT:TRADE_INTENT_REJECTED| OBS
  DM -->|EVT:INTENT_DEFERRED| BR[bridge\nAuroraBridge]
  DM -->|EVT:TRADE_INTENT_PROPOSED| BR

  %% ========= Bridge =========
  BR -->|CMD:OPEN| OFSM[execution_position\nOpenFlowFSM]

  %% ========= Execution =========
  OFSM -->|DEC:OPEN| XFSM[execution_position\nExecPosFSM]
  XFSM -->|adapter.place_market_entry| EX[Binance REST]
  XFSM -->|adapter.place_limit_entry (tif=GTX/GTC)| EX
  XFSM -->|OrderTimeoutWatchdog\n(ack/fill TTL + REST polling)| EX

  %% ========= Exchange updates =========
  EX -->|WS ORDER_TRADE_UPDATE| WS[BinanceWSClient]
  WS -->|EVT:ORDER_STATE_CHANGED| XFSM
  WS -->|EVT:ORDER_REJECTED\n(MAKER_ONLY_REJECT)| XFSM
  WS -->|EVT:TRADE_EXECUTED| PT[position_tracking]
  WS -->|EVT:TRADE_EXECUTED| XFSM

  %% ========= Portfolio feedback loop =========
  PT -->|EVT:PORTFOLIO_STATE_UPDATED| DM
  PT -->|EVT:PORTFOLIO_STATE_UPDATED| BR
  PT -->|EVT:PORTFOLIO_STATE_UPDATED| XFSM

  %% ========= Brackets =========
  XFSM -->|place_stop_market / take_profit_market\n(closePosition=true)| EX
```

---

## 2) Вузли: input fields → gates → state (коротко)

### 2.1 `EVT:BAR_CLOSED` → FeatureEngineering
- Producer: `apps/reference/domains/market_data/bar_aggregator.py` (WAL + `emit_fn("EVT:BAR_CLOSED", ...)`)
- Schema SSOT: `schemas/bar_closed_v1.json` (strict)
- Мін-поля (schema required): `ts_ms`, `symbol`, `tf_sec`, `bar_close_ts`, `bar{...}`
- Gates/kill-switch: N/A (це “source-of-truth” подія)
- State:
  - WAL append (бар як подія)
  - BarAggregator internal caches (`_current_bars`, `_completed_bars`)

### 2.2 `EVT:FEATURES_CALCULATED` (+ `CMD:PROCESS_STRATEGY`) → Strategies / DecisionMaking
- Producer: `apps/reference/domains/feature_engineering/feature_engineering.py`
- `EVT:FEATURES_CALCULATED` schema (strict): `apps/reference/domains/feature_engineering/schemas/features_calculated_v1.json`
- `CMD:PROCESS_STRATEGY` schema (strict): `apps/reference/domains/feature_engineering/schemas/cmd_process_strategy_v1.json`
- Мін-поля (runtime payload): `symbol`, `tf_sec`, `features`, `warmup.full_ready`, `price_motion`, `ts`
- Gates (fail-closed перед CMD emission):
  - `bar_data` існує
  - `tf_sec >= 60`
  - `warmup.full_ready == True`
  - `bar_close_ts` присутній
  - OHLCV у барі присутні
- State:
  - warmup/readiness registry (SSOT): `config/aurora/domains.yaml` → `feature_engineering.readiness_registry`

### 2.3 `EVT:STRATEGY_SIGNAL_PRODUCED` → DecisionMaking gateway
- Producer:
  - `apps/reference/domains/decision_making/aurora_handler.py` (Aurora strategy)
  - `apps/reference/domains/decision_making/mean_reversion_handler.py` (MR strategy)
- Registry: schema **відсутня** (див. Phase1 report)
- Мін-поля (DecisionMaking expects): `strategy_id`, `symbol`, `side`, `rid`, `ts_ms`, `why_chain`, `tf_sec`, `readiness.warmup_ok`, `price_ctx.entry_price` (varies)
- Gates (DecisionMaking `_on_strategy_signal_gateway`):
  - readiness: `warmup_ok == True` (інакше `EVT:TRADE_INTENT_REJECTED`)
  - strategy arbitration: `config/aurora/strategies.yaml` (priority window)
  - risk-skew `until_refresh` → `EVT:INTENT_DEFERRED` (retry scheduler)
  - risk gate / QoS gate / exposure gate / features freshness gate (TTL)
  - EntryPlan validation (`require_atr` може fail-closed)
- State:
  - `_qos_state` (cooldowns/rate limit per strategy)
  - `symbol_states` (features/regime/risk snapshots)
  - OrderIndex reservation: `order_index.try_reserve_entry(symbol, rid)` (atomic CAS)

### 2.4 `EVT:TRADE_INTENT_PROPOSED` / `EVT:TRADE_INTENT_REJECTED`
- Producer: `apps/reference/domains/decision_making/decision_making.py`
- Schema situation:
  - `EVT:TRADE_INTENT_REJECTED` має strict schema: `schemas/trade_intent_rejected_v1.json`
  - `EVT:TRADE_INTENT_PROPOSED` **не має schema у verb registry**, а файл `apps/reference/domains/decision_making/schemas/trade_intent_v1.json` **non-strict**.
- Мін-поля, які downstream реально потребує для OPEN:
  - `instrument/symbol`, `side`, `order.qty`, `order.order_type`, `order.tif`, `order.price` (для LIMIT), `valid_for_ms` (для LIMIT pending TTL)
- Критична невідповідність (root-cause для “0 orders”):
  - В поточній реалізації trade_intent payload, який збирає `DecisionMaking._propose_trade_intent`, **не включає** `order.order_type` і `order.tif` (а OpenFlowFSM вимагає `order_type` в CMD:OPEN).
  - Це означає: без додаткового “непомітного” enrichment десь downstream, `CMD:OPEN` буде rejected як `CMD_OPEN_VALIDATION_FAIL`.

### 2.5 AuroraBridge: `EVT:TRADE_INTENT_PROPOSED` → `CMD:OPEN`
- Consumer/producer: `apps/reference/main.py` (`AuroraBridge`)
- Gates/kill-switch:
  - portfolio freshness TTL (`positions_stale_ttl_sec`) + deferred retry queue
  - QoS next_allowed_ts per symbol (від `EVT:INTENT_DEFERRED`)
  - capacity gate (max_notional by free equity × leverage)
  - debug override: `disable_positions_stale_gate` (DEV/SHADOW only) — емісія `EVT:CONFIG_DEBUG_OVERRIDE_ACTIVE`
- State:
  - `_last_portfolio_ts` + `_deferred` intents + retry scheduler
  - OrderIndex early marker: `order_index.upsert_from_open(... order_type="ENTRY_INTENT")`
  - WAL append `CMD:OPEN`

### 2.6 OpenFlowFSM: `CMD:OPEN` → `DEC:OPEN`
- Consumer/producer: `apps/reference/domains/execution_position/fsm_open.py`
- Payload contract:
  - Pydantic `CmdOpenPayload` (strict: `extra='forbid'`)
  - Required: `symbol`, `side`, `qty`, `order_type`
- Gates/kill-switch:
  - `panic_killswitch` (blocks all new opens)
  - idempotency dedup via `idempotent_key`
  - maker-only enforcement (optional): if enabled and LIMIT → force `tif="GTX"`
  - guards: min_qty/step, LIMIT требует `price`, min_notional, cooldown
- State:
  - `idempotency_store` (in-memory window)

### 2.7 ExecPosFSM: `DEC:OPEN` → exchange placement → watchdog tracking
- Consumer/producer: `apps/reference/domains/execution_position/fsm.py`
- Key behaviors:
  - supersede queue (bar-over-bar): якщо є pending entry в Watchdog і `cancel_on_supersede` → cancel-then-wait, queue новий open
  - pending-entry TTL: `DecisionMaking.valid_for_ms` → `watchdog.track_order_placed(fill_ttl_override_ms=valid_for_ms)`
  - placement:
    - LIMIT: `adapter.place_limit_entry(... time_in_force=tif)`
    - MARKET: `adapter.place_market_entry(...)`
  - maker-only reject handling:
    - REST: codes `-5022/-1131` → emit `EVT:ORDER_REJECTED` (NO fallback)
    - WS: `GTX + EXPIRED + 0 fill` → emitted by WS client as `EVT:ORDER_REJECTED`
- State:
  - Watchdog (`pending_orders`, `acked_orders`, per-order TTL override)
  - `OrderIndex` (rid ↔ clientOrderId ↔ exchangeOrderId)
  - `_supersede_queue` / `_supersede_canceling`
  - `_symbol_brackets` + `OrderGuardian` tracking + orphan cleanup
  - `CorrelationStore` (entry ack corr_id/oco_group_id)

---

## 3) MARKET vs LIMIT “розвилка” у графі (де потрібна різна логіка)

### MARKET (MR strategy default)
- Assumption: швидкий fill (секунди/мс), після чого:
  - preflight position check проходить і можна ставити SL/TP “майже одразу”.
- Watchdog fill TTL є близьким до “fill timeout”.

### LIMIT (Aurora strategy default)
- Required behaviors:
  - maker-only (GTX) handling: reject can come як REST error або WS `EXPIRED` з 0 fill
  - pending_entry TTL (per tf) + cancel_on_supersede/cancel_on_regime_change
  - partial fills (PARTIALLY_FILLED) як перший клас подій
  - brackets placement: **прив’язати до fill/partial-fill**, а не до “після place + 1-2s REST lag”

Найважливіше: LIMIT не може покладатися на “preflight position exists within ~2s” як критерій постановки брекетів.

