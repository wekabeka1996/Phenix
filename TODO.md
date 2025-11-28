# TODO: Adapter Unification — Timeout Resilience

**Пов'язаний документ:** `docs/ADAPTER_UNIFICATION_PLAN.md`
**Статус:** In Progress
**Оновлено:** 2025-01-28

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

## Cleanup & Maintenance

- [x] **EP-CORE-SLIM-WATCHDOG-AND-OBS-CLEANUP** Remove legacy OrderTimeoutWatchdog and cleanup observability re-exports
  - Deleted pps/reference/domains/execution_position/watchdog.py
  - Deleted 	ests/domains/execution_position/test_watchdog.py
  - Deleted re-exports in pps/reference/domains/execution_position/
  - Updated tests to import from observability

