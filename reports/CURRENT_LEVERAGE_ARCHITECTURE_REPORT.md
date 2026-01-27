# Current Leverage Architecture Report

> **Дата:** 2026-01-22  
> **Автор:** Copilot Investigation Agent  
> **Мета:** Глибокий аналіз поточної архітектури leverage та margin_mode

---

## Executive Summary

| Аспект | Статус | Деталі |
|--------|--------|--------|
| **LeverageService** | 🟡 ГОТОВИЙ, НЕ WIRED | Повністю реалізований, але не підключений до рантайму |
| **Adapter Capability** | ✅ ГОТОВИЙ | BinanceAdapter має `set_leverage()`, `set_margin_mode()`, `get_*` методи |
| **Math Impact** | ✅ АКТИВНИЙ | Leverage використовується в sizing та exposure guards |
| **Production Wiring** | ❌ ВІДСУТНІЙ | LeverageService не ініціалізується в рантайм коді |

---

## 1. Leverage Service Status

### Файл: [leverage_service.py](apps/reference/domains/execution_position/leverage_service.py)

**Статус: 🟡 ГОТОВИЙ, НЕ WIRED (Недопідключений)**

#### Що робить LeverageService:

1. **`verify(symbol, leverage, margin_mode)`** — перевіряє поточні налаштування на біржі
2. **`set_and_verify(symbol, leverage, margin_mode)`** — встановлює і перевіряє
3. **Idempotency window** — уникає зайвих API-викликів (кеш на 60 сек)
4. **Fail-closed** — будь-яка помилка → reject order

#### Протокол адаптера (LeverageAdapterProtocol):

```python
class LeverageAdapterProtocol(Protocol):
    async def get_current_leverage(self, symbol: str) -> int: ...
    async def set_leverage(self, symbol: str, leverage: int) -> bool: ...
    async def get_margin_mode(self, symbol: str) -> str: ...
    async def set_margin_mode(self, symbol: str, mode: str) -> bool: ...
```

#### Виклик в коді:

| Місце | Статус |
|-------|--------|
| `fsm_open.py:handle_async()` | ✅ Готовий виклик (L535-L574) |
| Runtime ініціалізація | ❌ **НЕ WIRED** |

**Проблема:** FSM приймає `leverage_service=None` за замовчуванням і **пропускає** перевірку leverage:

```python
# fsm_open.py:L158
if leverage_service is None:
    LOG.warning(
        "TASK47c-E: OpenFlowFSM initialized without LeverageService. "
        "Leverage verification will be SKIPPED (shadow/dev mode only)."
    )
```

---

## 2. Adapter Capability

### Файл: [binance_adapter.py](apps/reference/adapters/binance_adapter.py)

**Статус: ✅ ПОВНІСТЮ РЕАЛІЗОВАНО**

#### Методи для leverage/margin:

| Метод | Endpoint | Статус |
|-------|----------|--------|
| `set_leverage(symbol, leverage)` | POST `/fapi/v1/leverage` | ✅ L1020-L1053 |
| `set_margin_mode(symbol, mode)` | POST `/fapi/v1/marginType` | ✅ L1154-L1190 |
| `get_margin_mode(symbol)` | GET `/fapi/v2/positionRisk` | ✅ L1090-L1150 |
| `get_current_leverage(symbol)` | GET `/fapi/v2/positionRisk` | ✅ L990-L1018 |

#### Особливості:

- **Hedge Mode Support:** Перевіряє консистентність leverage/margin_mode для LONG/SHORT сторін
- **Fail-closed:** Inconsistent values → NRR-024 помилка
- **-4046 handling:** "No need to change margin type" → Success (idempotent)

#### Де викликаються ці методи?

| Caller | Файл | Статус |
|--------|------|--------|
| LeverageService | leverage_service.py | ✅ Через protocol |
| **Виробничий код** | — | ❌ **НІДЕ** |

---

## 3. Math Impact — Де leverage впливає на розрахунки

### 3.1. Sizing (Decision Making)

**Файл:** [sizing_margin_first.py](apps/reference/domains/decision_making/sizing_margin_first.py)

**Функція:** `compute_notional_target()`

```python
def compute_notional_target(
    *,
    equity: Decimal,
    margin_pct: Decimal,
    leverage: int,
    ...
) -> tuple[Decimal, Decimal]:
    safe_equity = equity * (Decimal("1") - fee_buffer)
    margin_usdt = safe_equity * margin_pct
    notional_target = margin_usdt * Decimal(leverage)  # ← LEVERAGE IMPACT
    ...
```

**Формула:**
```
notional_target = (equity × (1 - fee_buffer) × margin_pct) × leverage
```

### 3.2. Exposure Guard

**Файл:** [exposure_guard.py](apps/reference/domains/execution_position/exposure_guard.py)

#### 3.2.1. Leverage Resolution (SSOT)

**Метод:** `resolve_symbol_leverage(symbol)` — L348-L400

**Пріоритет:**
1. `instruments.<SYM>.execution.target_leverage` (SSOT)
2. `trading.execution.exposure.leverage_defaults` (legacy fallback)

```python
def resolve_symbol_leverage(self, symbol: str) -> Decimal:
    # 1) SSOT: instruments.yaml
    spec = instruments.get(symbol)
    target = spec.execution.target_leverage
    if target is not None:
        return max(Decimal(str(target)), Decimal("1"))
    
    # 2) Legacy fallback
    return leverage_defaults[symbol] or leverage_defaults["__default__"]
```

#### 3.2.2. Margin Calculations

**Метод:** `reserve()` — L725-L777

```python
def reserve(...):
    symbol_leverage = self.resolve_symbol_leverage(symbol)
    reserve_margin = notional_usd / symbol_leverage  # ← LEVERAGE IMPACT
    ...
```

**Метод:** `can_open()` — L435-L700

```python
# For each position
sym_notional = abs(qty) * px
current_symbol_margin = sym_notional / ref_leverage  # ← LEVERAGE IMPACT

# For pending exposure
p_margin = p_notional / p_lev  # ← LEVERAGE IMPACT
```

**Формула (used_margin):**
```
used_margin = notional / leverage
```

---

## 4. Configuration SSOT

### Файл: [instruments.yaml](config/aurora/instruments.yaml)

Кожен інструмент має секцію `execution`:

```yaml
instruments:
  BTCUSDT:
    execution:
      margin_mode: "isolated"
      target_leverage: 50
      leverage_policy: "set_and_verify"
      max_notional_utilization: 0.8
```

| Параметр | Опис | Значення |
|----------|------|----------|
| `margin_mode` | Тип маржі | `"isolated"` (всюди) |
| `target_leverage` | Бажане плече | 20-50 (залежить від символу) |
| `leverage_policy` | Політика перевірки | `"set_and_verify"` / `"verify_only"` |
| `max_notional_utilization` | Max % від ліміту | 0.8 |

### Поточні значення:

| Symbol | target_leverage | margin_mode |
|--------|----------------|-------------|
| BTCUSDT | 50 | isolated |
| ETHUSDT | 41 | isolated |
| SOLUSDT | 20 | isolated |
| DOGEUSDT | 20 | isolated |
| XRPUSDT | 20 | isolated |

---

## 5. Gap Analysis — Чого не вистачає для Active Leverage Management

### 5.1. ❌ Critical Gaps

| Gap | Опис | Наслідки |
|-----|------|----------|
| **Runtime Wiring** | LeverageService не створюється/передається в OpenFlowFSM | Плече НІКОЛИ не синхронізується з біржею |
| **Startup Sync** | Немає "startup guard" що б'є тривогу якщо біржа має інше плече | Mismatch непоміченим |
| **Backtest Mode** | MockBroker не має leverage API | Backtest не перевіряє leverage |

### 5.2. 🟡 Moderate Gaps

| Gap | Опис | Наслідки |
|-----|------|----------|
| **Fallback policy** | Що робити якщо set_leverage fails? | Тільки reject, немає retry |
| **Drift Detection** | Немає periodic check що плече не змінилось ззовні | Ручна зміна на біржі не детектиться |
| **Telemetry** | Немає метрик leverage sync | Важко дебажити в production |

### 5.3. Поточний Flow (Broken)

```
[Intent] → [Decision Making] → [CMD:OPEN] → [OpenFlowFSM] → ...
                                                    │
                                                    ▼
                                      (leverage_service=None)
                                                    │
                                                    ▼
                                        ⚠️ SKIP LEVERAGE CHECK
                                                    │
                                                    ▼
                                      [DEC:OPEN] → [Place Order]
```

### 5.4. Бажаний Flow (After Fix)

```
[Startup]
    │
    ▼
[LeverageService = LeverageService(adapter=binance_adapter)]
    │
    ▼
[OpenFlowFSM(leverage_service=leverage_service)]
    │
    ▼
[Intent] → [CMD:OPEN] → [OpenFlowFSM.handle_async()]
                               │
                               ▼
                    [leverage_service.set_and_verify()]
                               │
                     ┌─────────┴─────────┐
                     │                   │
                ❌ FAIL              ✅ PASS
                     │                   │
                     ▼                   ▼
             [REJECT ORDER]        [DEC:OPEN] → [Place Order]
```

---

## 6. Де шукати виправлення

### Файли що потребують змін:

1. **Runtime Bootstrap** (main.py або orchestrator):
   ```python
   leverage_service = LeverageService(adapter=binance_adapter)
   open_flow_fsm = OpenFlowFSM(
       ...,
       leverage_service=leverage_service,
       is_live_execution=True,  # Fail-closed if missing
   )
   ```

2. **Startup Guard** (новий файл або в main.py):
   ```python
   async def verify_leverage_on_startup(adapter, config):
       for symbol, spec in config.instruments.items():
           expected = spec.execution.target_leverage
           actual = await adapter.get_current_leverage(symbol)
           if actual != expected:
               raise StartupError(f"{symbol} leverage mismatch: {actual} != {expected}")
   ```

3. **MockBroker** (для backtest):
   ```python
   class MockBroker:
       def __init__(self, ..., leverage_per_symbol: dict[str, int] = None):
           self._leverage = leverage_per_symbol or {}
       
       async def get_current_leverage(self, symbol): ...
       async def set_leverage(self, symbol, lev): ...
   ```

---

## 7. Тести що покривають leverage

| Файл | Кількість | Coverage |
|------|-----------|----------|
| `test_leverage_service.py` | 12 tests | LeverageService logic |
| `test_leverage_fsm_integration.py` | 3 tests | FSM + LeverageService |
| `test_open_flow_fsm_leverage_and_guards_v1.py` | 4 tests | Policy routing |

**Всі тести використовують мок адаптер.** Інтеграційні тести з реальним BinanceAdapter відсутні.

---

## 8. Висновки та Рекомендації

### Поточний стан:

| Компонент | Статус |
|-----------|--------|
| BinanceAdapter методи | ✅ Готові |
| LeverageService | ✅ Готовий |
| FSM інтеграція | ✅ Код готовий |
| Runtime wiring | ❌ **ВІДСУТНЄ** |
| Startup validation | ❌ **ВІДСУТНЄ** |

### Пріоритетні дії для Active Leverage Management:

1. **P0:** Wiring LeverageService в runtime (main.py / orchestrator)
2. **P0:** Startup leverage validation guard
3. **P1:** MockBroker leverage API для backtest
4. **P2:** Periodic drift detection
5. **P2:** Telemetry/metrics для leverage sync

---

## Appendix: Key Code References

| Concept | File | Line(s) |
|---------|------|---------|
| LeverageService class | `leverage_service.py` | L57-267 |
| BinanceAdapter.set_leverage | `binance_adapter.py` | L1020-1053 |
| BinanceAdapter.set_margin_mode | `binance_adapter.py` | L1154-1190 |
| FSM leverage check | `fsm_open.py` | L535-574 |
| Leverage SSOT resolution | `exposure_guard.py` | L348-400 |
| Sizing formula | `sizing_margin_first.py` | L28-48 |
| Config SSOT | `instruments.yaml` | entire file |
