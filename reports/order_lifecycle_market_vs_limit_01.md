# ORDER-LIFECYCLE-AUDIT-01 — Phase 4: MARKET vs LIMIT Conflict Matrix
Дата: 2026-01-12  
Goal: виділити MARKET-only припущення, LIMIT-required логіку, і конкретні точки конфлікту (з мінімальними правками + тестами)

---

## 0) SSOT baseline (що “має бути”)
- Global capabilities: `config/aurora/domains.yaml` → `execution_position.order_capabilities` supports `LIMIT/MARKET` + `GTC/GTX/IOC/FOK`.
- Strategy policies:
  - `aurora`: **LIMIT + GTX**
  - `mean_reversion`: **MARKET**
- LIMIT requires:
  - maker-only reject handling (REST + WS `EXPIRED` 0 fill)
  - pending-entry TTL (`valid_for_ms` derived from `tf_sec`)
  - supersede cancel-then-wait
  - partial fills (PARTIALLY_FILLED) as first-class

---

## 1) Conflict Matrix (конкретні місця)

| ID | Категорія | Evidence (code point) | Чому MARKET-only / LIMIT-required | Live risk (що станеться) | Мінімальна правка (де) | Як довести тестом |
|---:|---|---|---|---|---|---|
| 1 | **Contract break** | `apps/reference/domains/decision_making/decision_making.py` (~2829): `trade_intent['order']` не містить `order_type/tif` | LIMIT-first pipeline вимагає `order.order_type` (schema) і `CMD:OPEN.order_type` (Pydantic) | `CMD:OPEN` rejected як `CMD_OPEN_VALIDATION_FAIL` → **0 orders placed** (особливо видно в `ORDER_PLACED` counters) | Fail-closed: runtime emitter має **вставляти** `order_type/tif` з strategy policy, або не емісити intent | Integration: симулювати `EVT:STRATEGY_SIGNAL_PRODUCED` для aurora, очікувати `EVT:TRADE_INTENT_PROPOSED` з `order.order_type="LIMIT"` і `order.tif="GTX"` |
| 2 | **Silent fallback (to GTC)** | `apps/reference/domains/execution_position/fsm_open.py#L255-L256`: `tif = validated_pld.tif or \"GTC\"`; Bridge коментує “null means default GTC” (`apps/reference/main.py#L689-L692`) | Для LIMIT (особливо maker-only) `tif` має бути explicit policy, не дефолт | LIMIT може “тихо” піти як `GTC` → taker fill/fees/slippage, або behavior drift | Fail-closed: заборонити `tif is None` для LIMIT у CmdOpenPayload / OpenFlowFSM | Unit: `CmdOpenPayload(order_type=\"LIMIT\", tif=None)` повинно fail; Integration: aurora intent → cmd_open має tif=GTX |
| 3 | **Silent fallback (to MARKET)** | `apps/reference/domains/execution_position/fsm.py#L2156`: `order_type = decision.pld.get(\"order_type\", \"MARKET\")` | Missing order_type не має конвертуватися в MARKET | Потенційний “surprise MARKET order” якщо DEC:OPEN приходить без поля (або дрейф payload) | Fail-closed: якщо `order_type` missing → emit `EVT:ORDER_REJECTED` + stop execution | Unit: `_execute_decision(DEC:OPEN без order_type)` має не викликати adapter.place_market_entry |
| 4 | **LIMIT price contract not enforced at schema boundary** | `trade_intent_v1.json`: `order.price` не required; `CmdOpenPayload` price optional; OpenFlow rejects missing price only runtime | LIMIT price потрібен до placement | Intent може пройти “schema-ok”, але впасти пізніше → noisy failures + inconsistent reject reasons | Виносити правило в schema (if order_type==LIMIT then require price) + в bridge validation | Contract test: validate sample LIMIT trade_intent against schema; should fail if price missing |
| 5 | **Brackets placement assumes quick fill** | `apps/reference/domains/execution_position/fsm.py#L3288+`: `_preflight_position_check` робить backoff ~200–1800ms і потім “skip TP/SL” | Це логіка “MARKET fill lag”, не LIMIT pending | Для LIMIT: позиції може не бути хвилини → TP/SL не ставляться (або ставляться не тоді) | Для LIMIT: переносити bracket attach на fill/partial-fill event (WS/REST) | Integration: simulate LIMIT entry (NEW) → wait → FILLED, verify brackets placed on fill, not skipped |
| 6 | **Duplicate bracket engines / race** | ExecPosFSM ставить брекети “після place” (`apps/reference/domains/execution_position/fsm.py#L2328+`); ManageFlowFSM ставить брекети “на fill” (`apps/reference/domains/execution_position/fsm_manage.py#L427-L480`) | MARKET може пережити, LIMIT — ні (більше часу, більше шансів дублю) | Подвійні SL/TP, OCO emulation corruption, cancel storms | One SSOT: або тільки ExecPosFSM після fill, або тільки ManageFlowFSM; додати dedup ключі в OrderGuardian/ledger | Integration: feed duplicate TRADE_EXECUTED events; ensure only one set of brackets exists |
| 7 | **WS payload shape mismatch (qty/price)** | `BinanceWSClient` payload має `qty` але **нема `price`** (`apps/reference/adapters/binance_ws_client.py#L308-L322`); ExecPosFSM `_on_order_fill` читає `quantity` (`apps/reference/domains/execution_position/fsm.py#L1098-L1102`); ManageFlowFSM читає `qty`+`price` (`apps/reference/domains/execution_position/fsm_manage.py#L492-L499`) | LIMIT partial-fill/avg price критичні для bracket sizing | Manage може поставити брекети з `price=0` або не поставити; OrderIndex terminalization може не спрацювати (key mismatch) | SSOT schema для `EVT:TRADE_EXECUTED`/fill payload + нормалізація ключів (`qty` vs `quantity`, `price`) | Unit: WS update → emitted event must include required keys; Integration: simulate WS FILLED with avg price, ensure brackets use correct entry price |
| 8 | **Partial fills not first-class** | WS status `PARTIALLY_FILLED` мапиться → `EVT:ORDER_STATE_CHANGED` (`apps/reference/adapters/binance_ws_client.py#L261-L370`), але ManageFlowFSM очікує `EVT:PARTIAL_FILL` (`fsm_manage.py` docstring + branches) | LIMIT requires partial fill handling (position state updates, partial bracket attach) | Некоректний risk: брекети можуть не відповідати фактичній позиції; close logic incorrect | Emit `EVT:PARTIAL_FILL` (strict schema) on `PARTIALLY_FILLED` + update ManageFlowFSM accordingly | Integration: simulate partial then full fills; assert TP1/TP2 quantities consistent |
| 9 | **Maker-only reject path not integrated into ExecPosFSM routing** | WS detects maker-only reject and emits `EVT:ORDER_REJECTED` (`binance_ws_client.py#L363-L370`); ExecPosFSM.handle() не має special-case для `ORDER_REJECTED` (обробляє `ORDER_STATE_CHANGED`/`ORDER_CANCELLED`) | LIMIT-maker-only rejection is a normal outcome, must clear pending state/reservations | Pending TTL/supersede queue може зависнути; OrderIndex reservation може не terminalize → “ORDER-IN-FLIGHT” defers | Treat `ORDER_REJECTED` as terminal for entry: mark terminal, cancel watchdog tracking, emit consistent reason | Integration: simulate GTX EXPIRED 0 fill; ensure terminalization + no stuck reservation |
| 10 | **OrderGuardian market assumptions** | `apps/reference/services/order_guardian.py`: `register_entry()` writes `\"type\": \"MARKET\"` | LIMIT-first entry misclassified | Ownership logic / cleanup decisions можуть бути неправильні для LIMIT | Propagate actual order_type/tif/order_kind into guardian store | Unit: register_entry for LIMIT should store type=LIMIT and order_kind=ENTRY |
| 11 | **TTL semantics conflation (fill TTL vs pending TTL)** | trade_intent schema: `valid_for_ms null → global fill_ttl`; ExecPosFSM uses `valid_for_ms` as fill_ttl_override | Для MARKET `fill_ttl` — OK, але LIMIT pending TTL ≠ “fill TTL for all” | LIMIT order може жити довше бару; неправильний cancel policy або навпаки | Separate concepts: `pending_entry_ttl_ms` (LIMIT-only) vs `fill_ttl_ms` (market/overall) | Test: LIMIT entry uses per-tf TTL and cancels on expiry; MARKET ignores pending TTL |
| 12 | **Config SSOT drift (multiple watchdog sources)** | ExecPosFSM шукає watchdog config в декількох місцях (`apps/reference/domains/execution_position/fsm.py#L286-L350`) + `trading.orders.default_ttl_seconds` override | LIMIT behavior should be stable per tf | Непередбачувані timeouts → cancel storms або stuck entries | Single SSOT path for watchdog TTLs (domains.yaml) | Contract test: config loader must reject if duplicate TTL sources present |

---

## 2) Найкритичніші “LIMIT може поводитись неправильно” (короткий список)
1) **Brackets не ставляться** для LIMIT (бо preflight position check очікує fill за ~2s).
2) **Partial fill не обробляється** як position-open trigger → брекети/SL/TP не відповідають фактичній позиції.
3) **Maker-only reject** (GTX EXPIRED 0 fill) не чистить state/reservations → “order_in_flight” може зависати.
4) **Тихі дефолти** (`tif=GTC`, `order_type=MARKET`) можуть створити невідповідну політику.

---

## 3) Мінімальний test plan (без імплементації тут)
1) **Contract tests (schemas/Pydantic)**:
   - `trade_intent_v1.json` strict + conditional (LIMIT requires `price`/`tif`/`valid_for_ms`).
   - `cmd_open_v1.json` + `dec_open_v1.json` in registry.
2) **Integration (simulated adapter / WS replay)**:
   - LIMIT lifecycle: NEW → PARTIALLY_FILLED → FILLED, brackets placed correctly, no duplicates.
   - Maker-only: GTX placement leads to EXPIRED 0 fill, state cleared, no fallback.
3) **Regression for “0 orders created”**:
   - Ensure `DecisionMaking` emits intent with `order.order_type` and `tif` for both strategies according to config.

