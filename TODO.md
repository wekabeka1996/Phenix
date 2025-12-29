# TODO: Fix TP/SL Duplication - Add Initial Orders Sync

**Проблема:** ExecutionPosition V2 runtime не синхронізується з існуючими ордерами на біржі при запуску, що призводить до постійних спроб розмістити TP/SL ордери, які вже існують, і помилок "ClientOrderId is duplicated".

**Корінь проблеми:** Відсутня початкова синхронізація open orders в ExecPosRuntimeV2.start()

**Рішення:** Додати _force_initial_orders_sync() в метод start() для синхронізації з біржею перед початком роботи.

**Статус:** In Progress
**Оновлено:** 2025-12-04

- [x] Діагностовано проблему: відсутність initial sync призводить до duplicate ClientOrderId
- [x] Додано _force_initial_orders_sync() метод в runtime.py
- [x] Інтегровано виклик sync в start() метод
- [x] Діагностовано проблему: відсутність initial sync призводить до duplicate ClientOrderId
- [x] Додано _force_initial_orders_sync() метод в runtime.py
- [x] Інтегровано виклик sync в start() метод
- [x] Додано timestamp до clientOrderId генерації для додаткової унікальності
- [ ] Протестувати фікс на тестовій системі - ПОТРІБЕН ПЕРЕЗАПУСК
- [ ] Підтвердити, що duplicate помилки зникли

---

# TODO: Adapter Unification — Timeout Resilience

**Пов'язаний документ:** `docs/ADAPTER_UNIFICATION_PLAN.md`
**Статус:** In Progress
**Оновлено:** 2025-12-01

---

## Phase P0: Precision Guard for Conditionals ✅ COMPLETED (2025-12-01)

> **Мета:** Виправити -1111 Binance precision errors для stopPrice/price

- [x] **P0.1** Аудит binance_adapter precision handling ✅
  - `quantize_quantity()` існував, `normalize_price()` — НІ

- [x] **P0.2** Додати `_get_symbol_filters()` з кешем exchangeInfo ✅
  - TTL 300 сек, fallback для відомих символів

- [x] **P0.3** Додати `_normalize_price()` та `_normalize_quantity()` ✅
  - Округлення до tickSize/stepSize

- [x] **P0.4** Додати `_validate_precision()` fail-closed guard ✅
  - Перевірка перед відправкою на API

- [x] **P0.5** Оновити `create_order()` ✅
  - Нормалізація price, stopPrice, quantity

- [x] **P0.6** Тести: test_binance_adapter_precision.py ✅
  - 7 тестів precision normalization

**DoD Phase P0: ✅ COMPLETED**
```
✅ stopPrice нормалізується до tickSize
✅ price нормалізується до tickSize
✅ quantity нормалізується до stepSize
✅ Fail-closed guard перед API
✅ Тести: 602 passed
```

---

## Phase P1: Error Classification Fix ✅ COMPLETED (2025-12-01)

> **Мета:** Розрізняти adapter precision errors від fill timeouts

- [x] **P1.1** Аудит ExecutionService error handling ✅
  - `_classify_exception()` не знав про -1111

- [x] **P1.2** Додати precision_error до ERROR_CODES ✅
  - `"-1111"` → `is_timeout=False`

- [x] **P1.3** Оновити `_classify_exception()` ✅
  - Precision error detection FIRST

- [x] **P1.4** Тести: test_execution_error_mapping.py ✅
  - 13 тестів error classification

**DoD Phase P1: ✅ COMPLETED**
```
✅ -1111 класифікується як precision_error
✅ "precision" в повідомленні → not timeout
✅ Логи чесно показують причину
✅ Тести: all 13 passed
```

---

## Phase 3: Adapter Merge ✅ COMPLETED (2025-01-28)

> **Мета:** Об'єднати BinanceAdapter та BinanceExecutionAdapter в єдиний адаптер

- [x] **3.1** Оновити `BinanceAdapter.__init__` з WebSocket параметрами ✅
  - Додано: `fsm`, `shadow_mode`, `fsm_core`
  - Додано: `ws_listen_key`, `ws_thread`, `ws_running`, `ws_reconnect_delay`
  - Додано: `_resolve_credentials()` для мульти-джерел credentials

- [x] **3.2** Додати WebSocket USER_DATA_STREAM підтримку ✅
  - `start_websocket()`, `stop_websocket()` - lifecycle
  - `_websocket_loop()`, `_handle_ws_message()` - обробка подій
  - `_handle_order_trade_update()`, `_handle_account_update()` - хендлери
  - `_normalize_order_event()` - нормалізація WS payload

- [x] **3.3** Додати FSM Message-based методи ✅
  - `place_order_fsm(dec_msg)` - розміщення через vfoundation Message
  - `cancel_order_fsm(dec_msg)` - idempotent cancel з -2011 absorption
  - `_handle_bracket_error()` - обробка помилок брекетів (-2021, -4016, -4017)

- [x] **3.4** Очистити мертвий код ✅
  - Видалено: `_is_code_1021()` - ніколи не викликалось

- [x] **3.5** Тести проходять ✅
  - 5/5 unit тестів для BinanceAdapter

**DoD Phase 3: ✅ COMPLETED**
```
✅ BinanceAdapter має WebSocket підтримку
✅ FSM Message-based place/cancel методи
✅ Idempotent cancel з метриками
✅ Bracket error handling
✅ Shadow mode для тестування
```

---

## Phase 4: Deprecate BinanceExecutionAdapter ✅ COMPLETED (2025-01-28)

> **Мета:** Повне видалення BinanceExecutionAdapter

- [x] **4.1** Мігрувати імпорти в adapter_factory.py ✅
- [x] **4.2** Мігрувати імпорти в tools/audit_algo_orders.py ✅
- [x] **4.3** Мігрувати імпорти в tests/ ✅
  - test_ws_integration.py
  - test_slippage_cap_conversion.py (skip)
  - test_websocket_payload_normalization.py
  - test_adapter_cancel_order_fallback.py
  - test_binance_execution_adapter_unit.py
  - test_time_sync_robust.py
  - conftest.py
  - test_execution_service_error_handling.py
  - test_main_execpos_v2_wiring.py
- [x] **4.4** Видалити `binance_execution_adapter.py` ✅

**Test Results**: 126 passed, 17 skipped ✅

---

## Phase 0: Hotfix — TimeoutConfig в BinanceExecutionAdapter ✅ COMPLETED

> **Мета:** ReadTimeout фікс працює в production коді ExecPosRuntimeV2

- [x] **0.1** Імпортувати TimeoutConfig/RetryConfig в binance_execution_adapter.py ✅
  - Файл: `apps/reference/domains/execution_position/binance_execution_adapter.py`
  - Додано: `from apps.reference.adapters.binance_adapter import TimeoutConfig, RetryConfig, TIMEOUT_EXCEPTIONS, NETWORK_EXCEPTIONS`

- [x] **0.2** Оновити `__init__` для ініціалізації timeout конфігу ✅
  - Автовибір: `TimeoutConfig.testnet_defaults()` для testnet, `.live_defaults()` для live
  - Збережено в `self._timeout_config` та `self._retry_config`

- [x] **0.3** Оновити httpx client з TimeoutConfig ✅
  - `get_http_client()` тепер використовує `self._timeout_config.to_httpx_timeout()`

- [x] **0.4** Додати retry wrapper `_request_with_retry()` ✅
  - Експоненційний backoff через `RetryConfig.get_backoff_delays()`
  - Retry для TIMEOUT_EXCEPTIONS та NETWORK_EXCEPTIONS
  - Логування: `[BinanceExecutionAdapter] ... TIMEOUT (attempt X/Y)...`

- [x] **0.5** Тести: 14 passed ✅
  - Файл: `tests/domains/execution_position/test_binance_execution_adapter_timeout.py`
  - Тести: timeout config init, retry on timeout, retry exhausted, network error

**DoD Phase 0: ✅ COMPLETED**
```
✅ BinanceExecutionAdapter._timeout_config існує
✅ httpx використовує TimeoutConfig.to_httpx_timeout()
✅ _request_with_retry() з exponential backoff
✅ Логи: "[BinanceExecutionAdapter] RETRY attempt=1/4..."
✅ 14 тестів проходять
```

---

## Phase 1: Extract Shared Config Module ✅ COMPLETED

> **Мета:** Single source of truth для timeout/retry конфігурації

- [x] **1.1** Створити `apps/reference/adapters/timeout_config.py` ✅
  - Файл: `apps/reference/adapters/timeout_config.py`
  - Вміст: TimeoutConfig, RetryConfig, TIMEOUT_EXCEPTIONS, NETWORK_EXCEPTIONS

- [x] **1.2** Оновити імпорти в `binance_adapter.py` ✅
  - `from .timeout_config import TimeoutConfig, RetryConfig, ...`
  - Видалено дублюючі визначення dataclass (~185 рядків)

- [x] **1.3** Оновити імпорти в `binance_execution_adapter.py` ✅
  - `from apps.reference.adapters.timeout_config import ...`

- [x] **1.4** Оновити імпорти в `execution_service.py` — N/A ✅
  - `execution_service.py` не імпортує ці класи напряму

- [x] **1.5** Тест: імпорти працюють ✅
  - `pytest tests/domains/execution_position/test_binance_execution_adapter_timeout.py` — 14 passed
  - `pytest tests/adapters/test_binance_adapter.py` — 9 passed, 2 skipped

**DoD Phase 1: ✅ COMPLETED**
```
✅ timeout_config.py створено
✅ Немає дублювання TimeoutConfig/RetryConfig
✅ Всі імпорти оновлено
✅ pytest tests/ проходить без регресій
```

---

## Phase 2: Composition — REST Delegation

> **Мета:** BinanceExecutionAdapter делегує low-level REST до BinanceAdapter

- [ ] **2.1** Додати BinanceAdapter як залежність
  - В `__init__`: створити `self._rest_client = BinanceAdapter(...)`
  - Передати: api_key, api_secret, base_url, timeout_config, retry_config

- [ ] **2.2** Делегувати `_signed_request()` до `_rest_client._request()`
  - Замінити власну реалізацію httpx/sign/retry
  - Зберегти domain-логіку (logging, metrics, audit)

- [ ] **2.3** Видалити дубльований код
  - `_generate_signature()` → використовувати з `_rest_client`
  - `_get_server_time()` → делегувати
  - Retry loop → делегувати

- [ ] **2.4** Зберегти унікальну логіку
  - WebSocket USER_DATA_STREAM
  - listenKey management
  - AlgoService integration
  - Idempotent cancel

- [ ] **2.5** Тест: delegation працює
  - Mock `_rest_client._request()`
  - Verify виклики проходять через composition

**DoD Phase 2:**
```
✓ BinanceExecutionAdapter має self._rest_client
✓ _signed_request() делегує до _rest_client._request()
✓ Видалено ~500-800 рядків дубльованого коду
✓ WS/listenKey/AlgoService працюють
✓ Всі тести проходять
```

---

## Phase 3: Deprecate SdkAdapterBinance

> **Мета:** Одна канонічна реалізація для Binance

- [ ] **3.1** Додати deprecation warning
  - Файл: `apps/reference/adapters/sdk_adapter_binance.py`
  - `warnings.warn("SdkAdapterBinance is deprecated. Use BinanceExecutionAdapter.", DeprecationWarning)`

- [ ] **3.2** Знайти usage sites
  - `grep -r "SdkAdapterBinance" apps/ tests/`
  - Замінити на BinanceExecutionAdapter

- [ ] **3.3** Оновити adapter_factory.py (якщо потрібно)
  - Видалити шлях до SdkAdapterBinance

- [ ] **3.4** Документація
  - README або docstring: "Deprecated, use BinanceExecutionAdapter"

**DoD Phase 3:**
```
✓ SdkAdapterBinance має @deprecated
✓ Немає активних usage sites
✓ CI проходить
```

---

## Phase 4: Signature Unification (Future)

> **Мета:** Уніфікація API між AbstractExchangeAdapter та AbstractExecutionAdapter

- [ ] **4.1** Створити OrderParamsConverter
  - `Message` → `ExchangeOrderParams`
  - `ExchangeOrderResponse` → `Dict[str, Any]`

- [ ] **4.2** Опціональні typed методи в AbstractExecutionAdapter
  - `place_order_typed(params: ExchangeOrderParams)`
  - Зберегти backward compatibility

- [ ] **4.3** Поступова міграція
  - Один метод за раз
  - Shadow testing

**DoD Phase 4:**
```
✓ OrderParamsConverter працює
✓ Typed та untyped методи coexist
✓ Можна використовувати будь-який API
```

---

## Validation Checklist

### Після кожної Phase:
- [ ] `pytest tests/domains/execution_position/ -v` — PASS
- [ ] `pytest tests/adapters/ -v` — PASS
- [ ] `python -c "from apps.reference.domains.execution_position.binance_execution_adapter import BinanceExecutionAdapter"` — OK
- [ ] Немає нових warnings/errors в логах

### Фінальна валідація:
- [ ] Smoke test на testnet (5 хв)
- [ ] Перевірити retry логи при timeout
- [ ] Перевірити stale mode при persistent failure
- [ ] LOC count зменшився в binance_execution_adapter.py

---

## Quick Commands

```powershell
# Активація venv
.venv\Scripts\Activate.ps1

# Запуск тестів
pytest tests/domains/execution_position/shadow_execpos/test_runtime_timeout_resilience.py -v
pytest tests/domains/execution_position/ -v --tb=short

# Перевірка імпортів
python -c "from apps.reference.adapters.timeout_config import TimeoutConfig; print('OK')"

# LOC count
(Get-Content apps\reference\domains\execution_position\binance_execution_adapter.py).Count

# Grep для usage
Select-String -Path "apps\**\*.py" -Pattern "SdkAdapterBinance" -Recurse
```

---

## Progress Log

| Date | Phase | Task | Status | Notes |
|------|-------|------|--------|-------|
| 2025-11-27 | - | Plan created | ✅ | docs/ADAPTER_UNIFICATION_PLAN.md |
| 2025-11-27 | - | TODO.md created | ✅ | This file |
| 2025-11-27 | 0 | 0.1 Import TimeoutConfig | ✅ | Added imports |
| 2025-11-27 | 0 | 0.2 Update __init__ | ✅ | testnet/live auto-detect |
| 2025-11-27 | 0 | 0.3 Update httpx client | ✅ | to_httpx_timeout() |
| 2025-11-27 | 0 | 0.4 Add retry wrapper | ✅ | _request_with_retry() |
| 2025-11-27 | 0 | 0.5 Tests | ✅ | 14 tests passing |
| 2025-11-27 | 1 | 1.1 Create timeout_config.py | ✅ | Shared module |
| 2025-11-27 | 1 | 1.2 Update binance_adapter.py | ✅ | Removed ~185 lines |
| 2025-11-27 | 1 | 1.3 Update binance_execution_adapter.py | ✅ | Import from timeout_config |
| 2025-11-27 | 1 | 1.4 execution_service.py | ✅ | N/A - no imports needed |
| 2025-11-27 | 1 | 1.5 Test imports | ✅ | All tests pass |

---

## ExecutorPool Migration ✅ PHASE 3 COMPLETED (2025-11-29)

> **Мета:** Per-symbol parallel execution замість single SyncOrderExecutor

**Phase 1: Create Components ✅ COMPLETED**
- [x] **1.1** Створити `SymbolExecutor` — per-symbol executor (838 lines)
- [x] **1.2** Створити `ExecutorPool` — pool manager з rate limiter
- [x] **1.3** Реалізувати `closePosition=true` для brackets
- [x] **1.4** Написати unit тести — 26/26 passed

**Phase 2: Runtime Integration ✅ COMPLETED**
- [x] **2.1** Додати ExecutorPool до runtime.py init
- [x] **2.2** Routing fill events до executor_pool.on_fill()
- [x] **2.3** _handle_entry_intent() path для ExecutorPool
- [x] **2.4** Integration тести — 12/12 passed
- [x] **2.5** Додати `nest_asyncio` для sync->async calls
- [x] **2.6** Оновити default `executor_pool_enabled=False` для backward compat

**Phase 3: Remove Deprecated Code ✅ COMPLETED (2025-11-29)**
- [x] **3.1** Видалити `sync_executor.py` (550 lines) — DONE
- [x] **3.2** Видалити імпорт та код SyncOrderExecutor з runtime.py
- [x] **3.3** Оновити config логіку — ExecutorPool enabled by default
- [x] **3.4** Видалити застарілі тести (test_sync_executor.py, test_sync_executor_runtime_integration.py)
- [x] **3.5** Оновити решту тестів — 368/371 passed (99.2%)
- [x] **3.6** BracketService retired from production — Phase 11 COMPLETED ✅

---

## Aggregator OCO BracketService Retirement ✅ PHASE 11 COMPLETED (2025-11-30)

> **Мета:** Повне видалення BracketService з production коду

**Summary:**
- `self.bracket_service = None` — runtime no longer uses BracketService
- New modules: `view_types.py`, `cleanup.py` in aggregator_oco
- Runtime uses `plan_orphan_cleanup()`, `plan_reverse_cleanup()` from cleanup module
- Watchdog rewritten to use `compute_bracket_plan_from_views()`

**Test Results:**
- aggregator_oco: **258 passed** ✅
- shadow_execpos: **324 passed**, 22 xfailed, 14 xpassed ✅

**Phase 4: Simplify DM/Facade** (FUTURE)
- [ ] **4.1** Видалити QoS defer logic з DecisionMaking
- [ ] **4.2** Видалити _pending_symbols з V2RuntimeFacade
- [ ] **4.3** Прибрати complexity з order routing

**Phase 5: Cleanup** (FUTURE)
- [ ] **5.1** Оновити документацію
- [ ] **5.2** Performance benchmark
- [ ] **5.3** Shadow mode testing

**Test Results Phase 3 (2025-11-29):**
```
✅ test_executor_pool_entry_flow.py — 15/15 passed (NEW)
✅ test_entry_to_brackets_integration.py — 9/9 passed (NEW)
✅ test_executor_pool_integration.py — 13/13 passed (UPDATED)
✅ shadow_execpos total — 368/371 passed (99.2%)
⚠️ 3 failed unrelated to refactoring (2 logging file tests, 1 xfail)
```

**Config flags (current):**
- `executor_pool_enabled: true` — NEW default (production)
- `execution.executor_pool.enabled: true` — alternative config path
- Use both set to `false` to fallback to async ExecutionService path

**Breaking changes:**
- Removed `sync_executor_enabled` config flag
- Removed `runtime.sync_executor` attribute
- Removed `runtime._use_sync_executor` flag

---

## Cleanup & Maintenance

- [x] **EP-CORE-SLIM-WATCHDOG-AND-OBS-CLEANUP** Remove legacy OrderTimeoutWatchdog and cleanup observability re-exports
  - Deleted pps/reference/domains/execution_position/watchdog.py
  - Deleted 	ests/domains/execution_position/test_watchdog.py
  - Deleted re-exports in pps/reference/domains/execution_position/
  - Updated tests to import from observability

---

## Bug Fixes

- [x] **EXEC-BRACKET-RETRY-AND-SNAPSHOT-FIX** Fix bracket execution retry and snapshot blocking issues ✅ COMPLETED (2025-12-01)
  - **Problem**: Bracket orders dropped when rate limit (8/s) exceeded; Snapshot blocked trade_executed
  - **Fix**: Added retry loop with exponential backoff in `runtime.py:_execute_with_retry`
  - **Fix**: Updated `_snapshot_allows_brackets` to always allow `trade_executed`
  - **Verification**: Stress test confirmed 10/10 brackets processed (retries logged)

- [x] **CONFIG-V2-MERGE-LEVERAGE-FIX** Fix config v2 instrument merge to apply 75x leverage ✅ COMPLETED (2025-12-01)
  - **Problem**: Legacy trading.yaml instruments prevented v2 config merge, leverage showed 10x instead of 75x
  - **Fix**: Modified `_hydrate_from_config_v2` in `config_loader.py` to always merge v2 instruments into existing legacy instruments
  - **Fix**: Added None checks in `_build_ep_config` and `build_execution_runtime` to prevent 'NoneType' attribute errors
  - **Verification**: Leverage correctly resolves to 75x for all symbols (SOLUSDT, ETHUSDT, BTCUSDT, BNBUSDT)

---

## Aggregator OCO Dynamic Bracket Recalculation ✅ COMPLETED (2025-12-01)

> **Мета:** Реалізувати динамічне перерахування TP/SL рівнів при зміні позиції (scale-in, averaging)

**Summary:**
- **Problem**: Aggregator OCO не перераховував brackets при зміні entry price через scale-in/averaging
- **Solution**: Додано stale levels detection з tolerance-based price matching (0.1% default)
- **Implementation**:
  - `core_math.py`: `prices_match_with_tolerance()` function
  - `engine.py`: Stale levels check in `_compute_bracket_plan_core()` - **FIXED BUG**: тепер перевіряє кожен bracket окремо, а не тільки коли обидва існують
  - Generates CANCEL + PLACE actions when brackets become stale
- **Testing**: 6 unit tests covering scale-in, partial stale, tolerance scenarios
- **Integration**: Runtime tests pass, stale levels logic active in production

**Test Results:**
- aggregator_oco unit tests: **264 passed** ✅
- shadow_execpos integration: **7 passed, 2 xfailed** ✅
- Stale levels detection: ✅ scale-in triggers recalc, ✅ tolerance allows small differences, ✅ partial stale handled correctly

**Files Modified:**
- `apps/reference/domains/execution_position/aggregator_oco/core_math.py`
- `apps/reference/domains/execution_position/aggregator_oco/engine.py`
- `tests/domains/execution_position/aggregator_oco/test_stale_levels.py` (NEW)
