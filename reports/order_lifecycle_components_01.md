# ORDER-LIFECYCLE-AUDIT-01 — Phase 3: Execution Core Components Inventory
Дата: 2026-01-12  
Домен-фокус: `apps/reference/domains/execution_position` (+ Bridge/DM/Adapter/WS для повного lifecycle)

Легенда:
- **State**: що зберігається між подіями
- **Timers/TTL**: які дедлайни/інтервали впливають на lifecycle
- **Inputs/Outputs**: op/verb або зовнішні API

---

## 1) Компоненти (таблиця)

| Компонент | Відповідальність | State (де/що) | Timers/TTL | Inputs → Outputs |
|---|---|---|---|---|
| **DecisionMaking** (`apps/reference/domains/decision_making/decision_making.py`) | Гейти (risk/QoS/exposure/readiness/TTL), формування `EVT:TRADE_INTENT_*` | `symbol_states`, `_qos_state`, кеш exposure summary, risk-skew state; **OrderIndex reservation** | `features_ttl_sec`, QoS cooldown/rate-limit, retry windows | `EVT:STRATEGY_SIGNAL_PRODUCED` → `EVT:TRADE_INTENT_PROPOSED` / `EVT:TRADE_INTENT_REJECTED` / `EVT:INTENT_DEFERRED` |
| **AuroraBridge** (`apps/reference/main.py`) | Конвертація intent → `CMD:OPEN`, portfolio freshness gate, capacity gate, retry/defer | `_last_portfolio_ts`, `_deferred` intents, `_qos_next_allowed_ts_per_symbol` | `positions_stale_ttl_sec` (freshness), retry scheduler delays | `EVT:TRADE_INTENT_PROPOSED` → `CMD:OPEN` (direct call into ExecPosFSM); також `EVT:INTENT_DROPPED` |
| **OrderIndex** (`apps/reference/domains/execution_position/order_index.py`) | Кореляція `rid ↔ idempotent_key ↔ clientOrderId ↔ exchangeOrderId`, one-open-order guard | `_by_rid/_by_client/_by_exchange` з `OrderRef` + `terminal` flag | `ttl_sec` (expiration), `entry_guard_ttl_sec` (best-effort guard TTL) | Used by: DM (reserve), Bridge (ENTRY_INTENT), WS client (correlate), ExecPosFSM (mark terminal) |
| **CmdOpenPayload (Pydantic)** (`apps/reference/domains/execution_position/fsm_open.py`) | Contract validation для `CMD:OPEN` (strict: forbid extra fields) | N/A (pure validation) | N/A | `CMD:OPEN` payload → validated struct |
| **OpenFlowFSM** (`apps/reference/domains/execution_position/fsm_open.py`) | `CMD:OPEN` guards + idempotency + emit `DEC:OPEN` | `idempotency_store` (in-memory), `last_open_ts` | `idempotency_window_sec`, `cooldown_sec` | `CMD:OPEN` → `DEC:OPEN` або `ERR:OPEN` |
| **ExecPosFSM** (`apps/reference/domains/execution_position/fsm.py`) | Оркестрація open/manage/close flows, фактичний REST placement/cancel, supersede, watchdog wiring | per-symbol FSM instances; `_supersede_queue/_supersede_canceling`; `_symbol_brackets`; `_pending_intent_data`; correlation store; guardian cfg | `cooldown_after_close_ms`, supersede wait timeout (5s), orphan cleanup periodic interval; uses Watchdog TTLs | `DEC:OPEN/DEC:CLOSE/DEC:PLACE_ORDER` → BinanceAdapter REST; consumes `EVT:TRADE_EXECUTED`, `EVT:ORDER_STATE_CHANGED`, `EVT:REGIME_DETECTED` |
| **OrderTimeoutWatchdog** (`apps/reference/domains/execution_position/watchdog.py`) | ACK/FILL timeout tracking + (optional) REST polling for fills/cancels when WS missing | `pending_orders`, `acked_orders`, `_poll_meta`, RPS counters | `ack_ttl_ms`, `fill_ttl_ms`, per-order `fill_ttl_override_ms`, `check_interval_ms`, RPS limit | `track_order_placed`/`on_order_ack`/`on_order_fill` + REST `get_order_fn` → emits `EVT:TRADE_EXECUTED`/`EVT:ORDER_STATE_CHANGED` (через hook) |
| **ExposureGuard** (`apps/reference/domains/execution_position/exposure_guard.py`) | Fail-closed exposure gating + soft-clip + post-fill hold | `ExposureState` (reservations/pending/postfill), fallback mode state | `pending_ttl_sec`, `post_fill_hold_ttl_sec`, `positions_stale_ttl_sec` | Consumes portfolio snapshots + open intents; emits `EVT:EXPOSURE_SUMMARY_UPDATED`, `EVT:FALLBACK_MODE_ENTERED` |
| **Qty normalizer** (`apps/reference/domains/execution_position/qty_normalizer.py`) | Fail-closed qty validation/rounding (step/min_qty/min_notional) | N/A | N/A | Used by ExecPosFSM before placement |
| **IdempotentCancelHelper** (`apps/reference/domains/execution_position/idempotent_cancel.py`) | Cancel with pre-check, absorb `-2011/-2013`, retry | internal counter for deterministic clientOrderId | max retries + backoff | Used by ExecPosFSM cancel paths / watchdog timeout actions |
| **OrderGuardian (domain wrapper)** (`apps/reference/domains/execution_position/order_guardian.py`) | Delegation to services guardian + optional ledger store | store backend (DB or in-memory) | poll_interval_ms (guardian), ledger TTL in DB layer | Called by ExecPosFSM for `register_entry`, `should_place_brackets`, `cleanup_orphans`, etc |
| **OrderGuardian (service)** (`apps/reference/services/order_guardian.py`) | Own “ownership map” entry↔brackets, orphan cleanup, tidy | store keys: `entry:*`, `client:*`, `order:*` | poll interval, cleanup cadence | Adapter calls: get_open_orders/get_open_positions/cancel/get_order; emits logs + optional `EVT:SYMBOL_TIDY` |
| **ManageFlowFSM** (`apps/reference/domains/execution_position/fsm_manage.py`) | Bracket placement on fill, trailing/partial exits, anti-race close window | per-symbol position state + bracket IDs | `anti_race_close_ms`, manage intervals; partial-exit params | consumes `EVT:TRADE_EXECUTED`/`EVT:PARTIAL_FILL`/`UPD:*` → emits `DEC:PLACE_ORDER`/`DEC:ADJUST` (brackets) |
| **CloseFlowFSM** (`apps/reference/domains/execution_position/fsm_close.py`) | Execute `CMD:CLOSE` by emitting `DEC:CLOSE` (soldier pattern) | `position_open_ts`, `position_active` | `max_hold_sec` default=86400 (**risk: fallback**) | `CMD:CLOSE` → `DEC:CLOSE` |
| **BinanceAdapter (REST)** (`apps/reference/adapters/binance_adapter.py`) | place/cancel/get orders, typed adapter interface | internal auth/session, optional order tracking | network timeouts, exchange rate limits | ExecPosFSM/Guardian/Watchdog call REST endpoints |
| **BinanceWSClient** (`apps/reference/adapters/binance_ws_client.py`) | Translate `ORDER_TRADE_UPDATE` → internal FSM events, maker-only reject detect | listens on user data stream, correlates via OrderIndex | listen-key refresh | WS events → emits `EVT:TRADE_EXECUTED` / `EVT:ORDER_STATE_CHANGED` / `EVT:ORDER_REJECTED` |

---

## 2) “Що вважається ENTRY ордером?” (SSOT vs fallback)
- SSOT: `OrderIndex._is_entry_ref()` prefers `OrderRef.order_kind == "ENTRY"`.
- Fallbacks:
  - `clientOrderId` startswith `"ENTRY-"` OR contains `"ENTRY"` (legacy hacks used in WS client fallback).
  - `order_type == "ENTRY_INTENT"` (reservation placeholder).

**Ризик:** в `apps/reference/services/order_guardian.py` `register_entry()` hardcodes `type: "MARKET"` для entry, що конфліктує з LIMIT-first політикою (Aurora). Це створює drift у “what is ENTRY” при LIMIT.

---

## 3) MARKET vs LIMIT (де компоненти “заточені” під MARKET)
Найвиразніші MARKET-припущення в execution core:
- `ExecPosFSM._preflight_position_check()` ретраї ~200–1800ms “після MARKET fill” перед постановкою брекетів → для LIMIT це невалидно (pending може жити хвилини).
- `OrderGuardian.register_entry()` зберігає entry як `type="MARKET"` (service-layer drift).
- WS path емісії fills: `BinanceWSClient` формує payload без fill price у `EVT:TRADE_EXECUTED` (ManageFlowFSM очікує `price` для bracket logic).
- Partial fills: WS status `PARTIALLY_FILLED` мапиться в `EVT:ORDER_STATE_CHANGED`, але ManageFlowFSM чекає `EVT:PARTIAL_FILL` як first-class trigger.

