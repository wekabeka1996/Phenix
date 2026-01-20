# ORDER-LIFECYCLE-AUDIT-01 — Phase 5: Observability / Logging Coverage
Дата: 2026-01-12  
Фокус: що реально пишеться по ордерах (WAL/JSONL/logs), де є розриви, і чому інколи видно “Orders Created: 0”

---

## 1) Основні стріми (де шукати правду)

### 1.1 WAL (event-sourcing evidence)
- Writer: `vfoundation/dr/wal.py` (`wal.append(record)`), chain `_prev/_hash`
- Path: `WAL_DIR/YYYY-MM-DD.jsonl` (директорія задається `vfoundation.config`)
- Producers (приклади):
  - `EVT:BAR_CLOSED`: `apps/reference/domains/market_data/bar_aggregator.py`
  - `EVT:TRADE_INTENT_PROPOSED`: `apps/reference/domains/decision_making/decision_making.py`
  - `CMD:OPEN`: `apps/reference/main.py` (AuroraBridge)
  - `DEC:*`: `apps/reference/domains/execution_position/fsm.py` (ExecPosFSM)

**Плюс:** WAL містить “не-акаунтні” події навіть якщо ордер не був поставлений (intent/cmd/dec).  
**Мінус:** payload shapes не строго за schema (registry schema coverage низька).

### 1.2 OrderLoggerV1 (`logs/order_log_v1.jsonl`)
- Writer: `apps/reference/telemetry/order_logger.py` (`OrderLoggerV1.write`)
- Schema: `apps/reference/schemas/order_logger_v1.json`
- Event types (enum у schema): `ORDER_INTENT`, `ORDER_PLACED`, `ORDER_FILLED`, `ORDER_CANCELLED`, `ORDER_TIMEOUT`, `ORDER_REJECTED`, `ORDER_STATE_CHANGED`
- Validation behavior:
  - `ENV in ("DEBUG","TEST")` → schema validate (може **падати**, якщо enum/shape не збігається)
  - prod/default → **не валідить** (пише як є)

**Це основний файл**, який читають аналітичні утиліти (`tools/log_audit.py`, `tools/analyze_health.py`) для підрахунків `ORDER_PLACED`.

### 1.3 Domain logs (людочитні)
- `logs/order_guardian.log` (services guardian)
- `logs/aurora_trades.log` (AuroraLogAdapter)
- `logs/domain_*` (execution_position/regime_detector/etc) — runtime traces

---

## 2) Що зараз логують компоненти (мінімальна карта)

### 2.1 DecisionMaking → `ORDER_INTENT` / `ORDER_REJECTED`
- `apps/reference/domains/decision_making/decision_making.py`:
  - `order_logger.write(event_type="ORDER_INTENT", quantity, price, metadata.idempotent_key)`
  - `order_logger.write(event_type="ORDER_REJECTED", nrr_code=deny_reason, metadata=gate context)`

Coverage: **добре для “чому не відкрили”** (deny reasons), але не гарантує, що downstream справді поставив ордер.

### 2.2 ExecPosFSM → `ORDER_PLACED` / cancel / reject / state-changes
- `apps/reference/domains/execution_position/fsm.py`:
  - `ORDER_PLACED` пишеться одразу після REST placement (є `order_id`, `client_order_id`, `rid`)
  - `ORDER_CANCELLED` пишеться на cancel paths (TTL/supersede/panic/manual close cleanup)
  - `ORDER_REJECTED` пишеться на fail-closed конфіг/guards (напр. `NRR-INSTRUMENT-CONFIG-MISSING`)
  - “fill handled” пишеться як `ORDER_STATE_CHANGED` з `fill_status="FILLED"` (не як `ORDER_FILLED`)

⚠️ **Schema drift risk:** для maker-only reject в одному місці використовується `event_type="MAKER_ONLY_REJECT"` (якого **нема** в enum `apps/reference/schemas/order_logger_v1.json`). У `ENV=DEBUG/TEST` це може зламати логування (ValueError).

### 2.3 BinanceWSClient → EVT-level updates (WS)
- `apps/reference/adapters/binance_ws_client.py`:
  - `FILLED` → emits `EVT:TRADE_EXECUTED`
  - `PARTIALLY_FILLED` → emits `EVT:ORDER_STATE_CHANGED` (а не `EVT:PARTIAL_FILL`)
  - maker-only reject (GTX EXPIRED 0 fill) → emits `EVT:ORDER_REJECTED`

⚠️ Payload поля для `EVT:TRADE_EXECUTED` зараз не узгоджені з ManageFlowFSM/ExecPosFSM expectations (див. Phase4 ID=7).

---

## 3) Чому інколи видно “Orders Created: 0”
Під “Orders Created” зазвичай мається на увазі `ORDER_PLACED` у `logs/order_log_v1.jsonl` (див. `tools/analyze_health.py` / `tools/log_audit.py`).

Найімовірніші причини **0 `ORDER_PLACED`** при наявності intent/decision логів:
1) **`CMD:OPEN` відхиляється до placement**  
   - Поточний trade_intent payload (DecisionMaking) не містить `order.order_type`, а OpenFlowFSM вимагає `CMD:OPEN.order_type` (Pydantic) → `CMD_OPEN_VALIDATION_FAIL` → placement не відбувається.
2) **Shadow-mode execution**  
   - `ExecPosFSM._initialize_adapter()` при відсутніх API creds переводить `shadow_mode=True` і **не виконує** REST placement → немає `ORDER_PLACED`.
3) **Guardrail / domain-mode mismatch**  
   - Якщо execution_position в `testnet`, а adapter URL не testnet → блок.
4) **OrderLogger schema validation crash (DEBUG/TEST)**  
   - Якщо `ENV=DEBUG/TEST` і пишеться `event_type`, якого нема в enum (напр. `MAKER_ONLY_REJECT`), logger може кинути `ValueError` і припинити запис (побічно може “обнулити” файл або зупинити pipeline).

---

## 4) Мінімальний набір полів для надійної кореляції (SSOT proposal)
Щоб будь-який lifecycle аналіз був детермінований, **кожна** подія/лог-рядок про ордер має містити мінімум:
- `symbol`
- `ts_ms` (або `timestamp_ms`)
- `rid` (business correlation ключ)
- `idempotent_key`
- `client_order_id` (canonical name; не змішувати з `clientOrderId`)
- `order_id` (exchange orderId; canonical name; не змішувати з `orderId`)
- `order_kind` (`ENTRY|TP|SL|EXIT|...`)
- `order_type` (`MARKET|LIMIT|STOP_MARKET|TAKE_PROFIT_MARKET|...`)
- `tif` (`GTC|GTX|...`) або `null` (але з явним reason)
- `price` (для LIMIT + fill avg price) і `qty` / `filled_qty`
- `status` (NEW/PARTIALLY_FILLED/FILLED/CANCELED/EXPIRED/REJECTED)
- `reason_code` (SSOT reasons, без “CANCEL_UNKNOWN” якщо можна)

---

## 5) Що додати як SSOT (без імплементації в цьому пакеті)
1) Завести strict schemas + registry wiring для ключових boundary-подій:
   - `EVT:TRADE_INTENT_PROPOSED` (strict + conditional LIMIT/MARKET)
   - `CMD:OPEN`, `DEC:OPEN`
   - `EVT:ORDER_STATE_CHANGED`, `EVT:ORDER_REJECTED`, `EVT:PARTIAL_FILL`
2) Вирівняти canonical naming у payload/логах: `client_order_id` vs `clientOrderId`, `order_id` vs `orderId`.
3) Уніфікувати “what counts as created”:
   - SSOT: `ORDER_PLACED` має означати **exchange accepted** (REST response has `orderId`)
   - окремо `ORDER_ACK`/`ORDER_STATE_CHANGED` для WS transitions

