# Adapter Unification Plan: Консолідація двох паралельних ієрархій

**Автор:** Copilot
**Дата:** 2025-11-27
**Статус:** Draft
**Пріоритет:** P1 (Technical Debt)

---

## 1. Проблема

### 1.1 Поточний стан: Дві паралельні ієрархії адаптерів

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        vfoundation/core/adapters/base.py                    │
│                        ──────────────────────────────────                   │
│                        AbstractExchangeAdapter                              │
│                        • create_order(ExchangeOrderParams)                  │
│                        • cancel_order(symbol, order_id)                     │
│                        • get_open_orders() → List[ExchangeOrderResponse]    │
│                        • get_open_positions() → List[ExchangePosition]      │
│                        • get_mark_price(symbol)                             │
└──────────────────────────────────┬──────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    apps/reference/adapters/binance_adapter.py               │
│                    ──────────────────────────────────────────               │
│                    BinanceAdapter (1653 lines)                              │
│                    ✅ TimeoutConfig/RetryConfig                             │
│                    ✅ Exponential backoff                                   │
│                    ✅ _request() з retry                                    │
│                    ⚠️  НЕ ВИКОРИСТОВУЄТЬСЯ ExecPosRuntimeV2!               │
└─────────────────────────────────────────────────────────────────────────────┘


┌─────────────────────────────────────────────────────────────────────────────┐
│              apps/reference/domains/execution_position/                     │
│              execution_adapter.py                                           │
│              ────────────────────                                           │
│              AbstractExecutionAdapter                                       │
│              • place_order(msg: Message)                                    │
│              • cancel_order(msg: Message)                                   │
│              • get_open_orders(symbol) → List[Dict]                         │
│              • get_open_positions(symbol) → List[Dict]                      │
│              • get_status() → str                                           │
└──────────────────────────────────┬──────────────────────────────────────────┘
                                   │
          ┌────────────────────────┼────────────────────────┐
          ▼                        ▼                        ▼
┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐
│BinanceExecution  │    │Simulated         │    │SdkAdapterBinance │
│Adapter           │    │Adapter           │    │(python-binance)  │
│(3299 lines!)     │    │(mock/tests)      │    │                  │
│                  │    │                  │    │⚠️ Окремий SDK   │
│⚠️ Дублює httpx  │    │                  │    │⚠️ Не інтегрован │
│⚠️ Дублює sign   │    │                  │    └──────────────────┘
│⚠️ Дублює retry  │    │                  │
│⚠️ Дублює timeout│    │                  │
└────────┬─────────┘    └──────────────────┘
         │
         └──────────► ExecPosRuntimeV2 (PRODUCTION)
```

### 1.2 Конкретні проблеми

| # | Проблема | Файли | Наслідки |
|---|----------|-------|----------|
| P1 | **Дублювання low-level коду** | `binance_adapter.py` vs `binance_execution_adapter.py` | httpx клієнт, HMAC підпис, retry логіка реалізовані двічі |
| P2 | **Розбіжність TimeoutConfig** | Нещодавно додано в `binance_adapter.py`, відсутнє в `binance_execution_adapter.py` | ReadTimeout фікс не застосовується до production коду |
| P3 | **Дві різні сигнатури** | `create_order(ExchangeOrderParams)` vs `place_order(msg: Message)` | Неможливо просто замінити один адаптер іншим |
| P4 | **Три SDK шляхи** | httpx (2 місця) + python-binance | Різна семантика помилок, різне логування |
| P5 | **3299 рядків монолітного коду** | `binance_execution_adapter.py` | Складно підтримувати, тестувати, рефакторити |

### 1.3 Ризики поточного стану

```
┌────────────────────────────────────────────────────────────────┐
│ КРИТИЧНИЙ РИЗИК: ReadTimeout фікс НЕ працює в production!     │
│                                                                │
│ Ми додали TimeoutConfig/RetryConfig в binance_adapter.py,     │
│ але ExecPosRuntimeV2 використовує binance_execution_adapter.py│
│ який має власну жорстко закодовану логіку таймаутів.          │
└────────────────────────────────────────────────────────────────┘
```

---

## 2. Цільова архітектура

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        ЦІЛЬОВИЙ СТАН (після рефакторингу)                   │
└─────────────────────────────────────────────────────────────────────────────┘

                    ┌─────────────────────────────────────┐
                    │  apps/reference/adapters/           │
                    │  timeout_config.py (SHARED)         │
                    │  ─────────────────────────          │
                    │  • TimeoutConfig                    │
                    │  • RetryConfig                      │
                    │  • TIMEOUT_EXCEPTIONS tuple         │
                    │  • NETWORK_EXCEPTIONS tuple         │
                    └──────────────┬──────────────────────┘
                                   │
                    ┌──────────────┴──────────────┐
                    ▼                             ▼
     ┌─────────────────────────┐    ┌─────────────────────────┐
     │  binance_adapter.py     │    │  binance_execution_     │
     │  (low-level REST)       │    │  adapter.py             │
     │  ─────────────────      │    │  (domain adapter)       │
     │  BinanceAdapter         │    │  ─────────────────      │
     │  • _request() + retry   │    │  BinanceExecutionAdapter│
     │  • _sign()              │◄───│  • КОМПОЗИЦІЯ           │
     │  • httpx client         │    │  • place_order() → ...  │
     └─────────────────────────┘    │  • domain-specific logic│
                                    └─────────────────────────┘
                                              │
                                              ▼
                                    ┌─────────────────────────┐
                                    │  ExecPosRuntimeV2       │
                                    │  (production)           │
                                    └─────────────────────────┘
```

**Ключові принципи:**
1. **Single Source of Truth** — timeout/retry конфіг в одному місці
2. **Composition over Duplication** — `BinanceExecutionAdapter` делегує REST до `BinanceAdapter`
3. **Backward Compatibility** — зовнішній API `AbstractExecutionAdapter` не змінюється

---

## 3. План міграції (поетапний)

### Phase 0: Hotfix — Перенести TimeoutConfig в BinanceExecutionAdapter
**Терміновість:** КРИТИЧНА (перед Phase 1)
**Тривалість:** 1-2 години
**Ризик:** Низький

#### Завдання:
- [ ] 0.1 Імпортувати `TimeoutConfig`, `RetryConfig` з `binance_adapter.py` в `binance_execution_adapter.py`
- [ ] 0.2 Оновити `__init__` для читання timeout конфігу
- [ ] 0.3 Оновити всі `httpx` виклики для використання `TimeoutConfig.to_httpx_timeout()`
- [ ] 0.4 Додати retry wrapper до критичних REST викликів

#### DoD (Definition of Done):
```python
# binance_execution_adapter.py повинен:
from apps.reference.adapters.binance_adapter import TimeoutConfig, RetryConfig

class BinanceExecutionAdapter:
    def __init__(self, ..., rest_timeout_sec: float = 20.0):
        self._timeout_config = TimeoutConfig.testnet_defaults() if self._is_testnet else TimeoutConfig.live_defaults()
        self._retry_config = RetryConfig()
```

#### Тести:
```python
# test_binance_execution_adapter_timeout.py
def test_execution_adapter_uses_timeout_config():
    adapter = BinanceExecutionAdapter(...)
    assert adapter._timeout_config.read >= 20.0  # testnet

async def test_execution_adapter_retries_on_timeout():
    # Mock httpx.ReadTimeout, verify retry
```

---

### Phase 1: Extract Shared Config Module
**Тривалість:** 2-4 години
**Ризик:** Низький (additive only)

#### Завдання:
- [ ] 1.1 Створити `apps/reference/adapters/timeout_config.py`
- [ ] 1.2 Перенести `TimeoutConfig`, `RetryConfig` з `binance_adapter.py`
- [ ] 1.3 Перенести `TIMEOUT_EXCEPTIONS`, `NETWORK_EXCEPTIONS` tuples
- [ ] 1.4 Оновити імпорти в `binance_adapter.py`
- [ ] 1.5 Оновити імпорти в `binance_execution_adapter.py`
- [ ] 1.6 Оновити імпорти в `execution_service.py`

#### Контракт (timeout_config.py):
```python
"""
Shared timeout and retry configuration for exchange adapters.

This module provides unified timeout/retry settings used across:
- apps/reference/adapters/binance_adapter.py (low-level REST)
- apps/reference/domains/execution_position/binance_execution_adapter.py (domain)
- apps/reference/domains/execution_position/shadow_execpos/execution_service.py
"""
from dataclasses import dataclass
from typing import List, Tuple, Type
import httpx
import httpcore

@dataclass
class TimeoutConfig:
    connect: float = 5.0
    read: float = 15.0
    write: float = 5.0
    pool: float = 5.0

    def to_httpx_timeout(self) -> httpx.Timeout: ...

    @classmethod
    def testnet_defaults(cls) -> "TimeoutConfig": ...

    @classmethod
    def live_defaults(cls) -> "TimeoutConfig": ...

@dataclass
class RetryConfig:
    max_retries: int = 3
    initial_backoff_sec: float = 0.5
    max_backoff_sec: float = 8.0
    backoff_multiplier: float = 2.0
    retry_on_timeout: bool = True
    retry_on_network: bool = True

    def get_backoff_delays(self) -> List[float]: ...

# Exception tuples for classification
TIMEOUT_EXCEPTIONS: Tuple[Type[Exception], ...] = (
    httpx.ReadTimeout,
    httpx.ConnectTimeout,
    httpx.WriteTimeout,
    httpx.PoolTimeout,
    httpcore.ReadTimeout,
    httpcore.ConnectTimeout,
    httpcore.WriteTimeout,
)

NETWORK_EXCEPTIONS: Tuple[Type[Exception], ...] = (
    httpx.ConnectError,
    httpx.RemoteProtocolError,
    httpcore.ConnectError,
    httpcore.RemoteProtocolError,
    ConnectionError,
    OSError,
)
```

#### DoD:
- [ ] `timeout_config.py` створено
- [ ] Всі імпорти оновлено без breaking changes
- [ ] `pytest tests/` проходить без регресій

#### Тести:
```bash
# Існуючі тести повинні проходити
pytest tests/domains/execution_position/ -v
pytest tests/adapters/ -v
```

---

### Phase 2: Composition — BinanceExecutionAdapter делегує REST
**Тривалість:** 4-8 годин
**Ризик:** Середній (потребує ретельного тестування)

#### Завдання:
- [ ] 2.1 Додати `BinanceAdapter` як залежність в `BinanceExecutionAdapter.__init__`
- [ ] 2.2 Створити внутрішній `_rest_client: BinanceAdapter`
- [ ] 2.3 Делегувати `_signed_request()` до `_rest_client._request()`
- [ ] 2.4 Видалити дубльований код підпису/retry з `BinanceExecutionAdapter`
- [ ] 2.5 Зберегти domain-специфічну логіку (WS, listenKey, AlgoService)

#### Приклад коду:
```python
# binance_execution_adapter.py
class BinanceExecutionAdapter(AbstractExecutionAdapter):
    def __init__(self, fsm, config, ...):
        # ... existing init ...

        # NEW: Compose with low-level REST client
        self._rest_client = BinanceAdapter(
            api_key=self._api_key,
            api_secret=self._api_secret,
            base_url=self._base_url,
            timeout_config=self._timeout_config,
            retry_config=self._retry_config,
        )

    async def _signed_request(self, method: str, endpoint: str, params: dict) -> dict:
        """Delegate to composed REST client."""
        return await self._rest_client._request(method, endpoint, params, signed=True)
```

#### DoD:
- [ ] `BinanceExecutionAdapter` використовує `BinanceAdapter` для REST
- [ ] Видалено дубльований httpx/sign/retry код (~500-800 рядків)
- [ ] Всі існуючі тести проходять
- [ ] Логи показують retry при ReadTimeout

#### Тести:
```python
# test_execution_adapter_composition.py
async def test_execution_adapter_delegates_to_rest_client():
    adapter = BinanceExecutionAdapter(...)
    with patch.object(adapter._rest_client, '_request') as mock:
        mock.return_value = {"orderId": 123}
        result = await adapter._signed_request("POST", "/fapi/v1/order", {})
        mock.assert_called_once()

async def test_timeout_retry_works_through_composition():
    adapter = BinanceExecutionAdapter(...)
    # Mock to fail twice then succeed
    with patch.object(adapter._rest_client, '_request') as mock:
        mock.side_effect = [httpx.ReadTimeout(""), httpx.ReadTimeout(""), {"orderId": 123}]
        result = await adapter._signed_request(...)
        assert mock.call_count == 3
```

---

### Phase 3: Deprecate SdkAdapterBinance
**Тривалість:** 2-4 години
**Ризик:** Низький (ізольований код)

#### Завдання:
- [ ] 3.1 Додати deprecation warning в `sdk_adapter_binance.py`
- [ ] 3.2 Оновити документацію: "Use BinanceExecutionAdapter instead"
- [ ] 3.3 Знайти всі usage sites і замінити (якщо є)
- [ ] 3.4 Видалити з `adapter_factory.py` (якщо використовується)

#### DoD:
- [ ] `SdkAdapterBinance` має `@deprecated` decorator
- [ ] Немає активних usage sites
- [ ] CI проходить

---

### Phase 4: Уніфікація сигнатур (Optional/Future)
**Тривалість:** 8-16 годин
**Ризик:** Високий (breaking changes)

#### Опис:
Створити adapter layer для конвертації:
- `place_order(msg: Message)` ↔ `create_order(ExchangeOrderParams)`

#### Завдання:
- [ ] 4.1 Створити `OrderParamsConverter` utility
- [ ] 4.2 Оновити `AbstractExecutionAdapter` з optional typed methods
- [ ] 4.3 Міграція по одному методу

**Цей phase відкладено до завершення Phase 0-2.**

---

## 4. Checklist фінальної валідації

### 4.1 Функціональні тести
```bash
# Unit tests
pytest tests/domains/execution_position/ -v --tb=short
pytest tests/adapters/ -v --tb=short

# Integration tests (якщо є)
pytest tests/integration/ -v -k "execution" --tb=short

# Timeout resilience tests
pytest tests/domains/execution_position/shadow_execpos/test_runtime_timeout_resilience.py -v
```

### 4.2 Smoke test на testnet
```powershell
# Запустити бота на testnet і перевірити:
.venv\Scripts\Activate.ps1; python -m apps.reference.main

# Очікувані логи при timeout:
# [BinanceAdapter] RETRY attempt=1/3 after ReadTimeout
# [BinanceAdapter] RETRY attempt=2/3 after ReadTimeout
# [BinanceAdapter] SUCCESS after 2 retries
```

### 4.3 Метрики для перевірки
| Метрика | До | Після | Очікування |
|---------|-----|-------|------------|
| `timeout_rate` | ~5-10% | <1% | Зменшення через retry |
| `retry_count` | 0 | >0 | Видимі retry в логах |
| `stale_mode_entries` | N/A | >0 | Runtime входить в stale mode |
| Рядків коду в `binance_execution_adapter.py` | 3299 | ~2500 | Видалення дублювання |

### 4.4 Контракти для оновлення

#### JSON Schema (якщо потрібно):
```yaml
# dictionaries/execution_position.yaml (якщо є)
adapters:
  binance:
    rest_timeout_sec:
      type: number
      default: 20.0
      description: "REST API read timeout in seconds"
    retry_max_attempts:
      type: integer
      default: 3
```

---

## 5. Ризики та мітигація

| Ризик | Ймовірність | Вплив | Мітигація |
|-------|-------------|-------|-----------|
| Регресія в order placement | Середня | Критичний | Extensive testing + shadow mode first |
| Breaking change в API | Низька | Високий | Зберігаємо зовнішній API незмінним |
| Timeout на testnet все ще трапляються | Висока | Середній | Retry + stale mode вже реалізовано |
| Merge conflicts з main | Середня | Низький | Невеликі PR, часті merge |

---

## 6. Timeline

```
Week 1:
├── Day 1-2: Phase 0 (Hotfix) — TimeoutConfig в BinanceExecutionAdapter
├── Day 3-4: Phase 1 — Extract timeout_config.py
└── Day 5:   Testing + Code Review

Week 2:
├── Day 1-3: Phase 2 — Composition refactoring
├── Day 4:   Phase 3 — Deprecate SdkAdapterBinance
└── Day 5:   Final validation + Documentation
```

---

## 7. Acceptance Criteria

### Must Have:
- [ ] `TimeoutConfig` використовується в `BinanceExecutionAdapter`
- [ ] Retry з exponential backoff працює для REST викликів
- [ ] Runtime входить в stale mode при timeout
- [ ] Всі існуючі тести проходять
- [ ] Немає дублювання timeout/retry логіки

### Should Have:
- [ ] Shared `timeout_config.py` module
- [ ] `BinanceExecutionAdapter` делегує REST до `BinanceAdapter`
- [ ] Зменшення LOC в `binance_execution_adapter.py` на 20%+

### Nice to Have:
- [ ] Deprecation warning для `SdkAdapterBinance`
- [ ] Unified error classification across all adapters

---

## Appendix A: Файли для модифікації

```
apps/reference/adapters/
├── timeout_config.py          # NEW (Phase 1)
├── binance_adapter.py         # UPDATE imports (Phase 1)
└── sdk_adapter_binance.py     # DEPRECATE (Phase 3)

apps/reference/domains/execution_position/
├── binance_execution_adapter.py  # UPDATE (Phase 0, 2)
├── execution_adapter.py          # NO CHANGE
├── simulated_adapter.py          # NO CHANGE
├── adapter_factory.py            # MINOR UPDATE (timeout config)
└── shadow_execpos/
    ├── execution_service.py      # UPDATE imports (Phase 1)
    └── runtime.py                # NO CHANGE (already has stale mode)

tests/
├── adapters/
│   └── test_timeout_config.py    # NEW (Phase 1)
└── domains/execution_position/
    └── shadow_execpos/
        └── test_runtime_timeout_resilience.py  # EXISTS (expand)
```

---

## Appendix B: Команди для перевірки

```powershell
# Перевірка імпортів
python -c "from apps.reference.adapters.timeout_config import TimeoutConfig, RetryConfig; print('OK')"

# Перевірка composition
python -c "from apps.reference.domains.execution_position.binance_execution_adapter import BinanceExecutionAdapter; print('OK')"

# Запуск тестів
.venv\Scripts\Activate.ps1
pytest tests/domains/execution_position/shadow_execpos/test_runtime_timeout_resilience.py -v
pytest tests/adapters/ -v

# Перевірка LOC
(Get-Content apps\reference\domains\execution_position\binance_execution_adapter.py).Count
```
