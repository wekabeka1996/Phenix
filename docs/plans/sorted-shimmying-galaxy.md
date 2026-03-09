# Plan: Fix LIMIT bracket placement + Bracket Health Check Safety Net

## Summary

Два фікси:
1. **FIX 1**: Watchdog polling fill payload — збагатити `side`/`qty`, виправити timeout emit
2. **FIX 2**: Periodic Bracket Health Check — моніторинг відкритих позицій без TP/SL

---

## FIX 1: Watchdog polling fill payload + timeout emit fix

### Проблема

1. `emit_watchdog_event` (fsm.py:506) вже викликає `self.handle(msg)` — маршрутизація OK
2. Але watchdog payload (watchdog.py:381-388) **не містить** `side` та `qty` полів
3. `ManageFlowFSM._on_fill()` (fsm_manage.py:503) читає `pld["qty"]` → отримує `0` (бо є тільки `quantity`)
4. `pld.get("side")` → `None` (бо absent)
5. Timeout fill emit (fsm.py) використовує `emit_compat(self.fsm, ...)` → bus без listener → повідомлення губиться

### Зміни

#### 1a. `apps/reference/domains/execution_position/watchdog.py` (lines 381-388)

Збагатити fill_payload:
```python
fill_payload = {
    "orderId": order_id,
    "symbol": symbol,
    "quantity": executed_qty,
    "qty": executed_qty,                                    # NEW
    "price": float(dget(order_status, "avgPrice", 0)),
    "side": str(dget(order_status, "side", "")),            # NEW
    "client_order_id": dget(order_status, "clientOrderId", ""),
    "clientOrderId": dget(order_status, "clientOrderId", ""),  # NEW
    "rid": None
}
```

#### 1b. `apps/reference/domains/execution_position/fsm.py` — timeout fill emit

Замінити `await emit_compat(self.fsm, fill_msg, logger=LOG)` на `self.handle(fill_msg)`.
Збагатити payload timeout fill з `qty` та `side` полями (з order_data).

---

## FIX 2: Periodic Bracket Health Check (Safety Net)

### Концепція

Фоновий async loop (кожні 45с) перевіряє:
1. Отримати всі відкриті позиції (`adapter.get_open_positions()`)
2. Для кожної позиції з `positionAmt != 0`:
   - Перевірити чи є SL/TP ордери на біржі (`adapter.get_open_orders(symbol)`)
   - Якщо SL або TP відсутні → розрахувати з SSOT конфіга (regime_tpsl з aurora.yaml)
   - Виставити відсутні бракети

### Файли для зміни

| Файл | Зміна |
|------|-------|
| `config/aurora/domains.yaml` | +секція `bracket_health_check` |
| `apps/reference/config_models.py` | +клас `BracketHealthCheckConfig`, +поле в `ExecutionPositionDomainConfig` |
| `apps/reference/domains/execution_position/fsm.py` | +loop, +check, +compute, +place методи |
| `tests/domains/execution_position/test_bracket_health_check.py` | Нові тести |

### Step 2.1: Config Model (`config_models.py`)

Додати після `GuardianConfig` (перед `ExecutionPositionDomainConfig`):
```python
class BracketHealthCheckConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')
    enabled: bool = True
    interval_sec: int = Field(..., ge=30, le=300)
    grace_period_ms: int = Field(..., ge=5000)
    max_placements_per_cycle: int = Field(default=2, ge=1, le=10)
```

Додати поле в `ExecutionPositionDomainConfig` (після `guardian`, line ~2190):
```python
bracket_health_check: Optional[BracketHealthCheckConfig] = Field(
    default=None,
    description="Safety net: periodic check for missing SL/TP on open positions"
)
```

### Step 2.2: YAML Config (`domains.yaml`)

Після секції `guardian:` (line ~492):
```yaml
bracket_health_check:
  enabled: true
  interval_sec: 45
  grace_period_ms: 15000
  max_placements_per_cycle: 2
```

### Step 2.3: FSM Methods (`fsm.py`)

#### 2.3a: Add `_last_regime_by_symbol` dict (init, line ~246)
```python
self._last_regime_by_symbol: Dict[str, str] = {}
```

#### 2.3b: Populate regime in `_on_regime_detected` (line ~1209)
```python
if symbol:
    self._last_regime_by_symbol[symbol] = regime_str
```

#### 2.3c: New method `_bracket_health_loop` (after `_cleanup_loop`)
```python
async def _bracket_health_loop(self) -> None:
    """BRACKET-HEALTH: Periodic safety net for missing SL/TP."""
    cfg = self.config.domains.execution_position.bracket_health_check
    if not cfg or not cfg.enabled:
        return
    while True:
        try:
            await get_clock().sleep_sec(cfg.interval_sec)
            await self._run_bracket_health_check(cfg)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            LOG.warning(f"[BRACKET-HEALTH] loop error: {e}")
```

#### 2.3d: New method `_run_bracket_health_check(cfg)`
Логіка одного циклу:
1. `positions = await self.adapter.get_open_positions()`
2. Для кожної позиції де `position_amount != 0`:
   - Перевірити grace period (позиція відкрита > `grace_period_ms` тому)
   - `has_sl, has_tp = await self._check_brackets_on_exchange(symbol)`
   - Якщо `has_sl and has_tp` → skip (все ОК)
   - Інакше → обчислити TPSL, поставити відсутні бракети
   - Rate limit: `max_placements_per_cycle`

#### 2.3e: New method `_check_brackets_on_exchange(symbol)`
```python
async def _check_brackets_on_exchange(self, symbol: str) -> Tuple[bool, bool]:
    """Check if SL and TP orders exist on exchange for symbol."""
    try:
        orders = await self.adapter.get_open_orders(symbol)
        has_sl = any(
            o.get("type") == "STOP_MARKET" and o.get("reduceOnly", False)
            for o in orders
        )
        has_tp = any(
            o.get("type") == "TAKE_PROFIT_MARKET" and o.get("reduceOnly", False)
            for o in orders
        )
        return has_sl, has_tp
    except Exception as e:
        LOG.warning(f"[BRACKET-HEALTH] Failed to check orders for {symbol}: {e}")
        return True, True  # Fail-closed: assume brackets exist
```

#### 2.3f: New method `_compute_health_check_brackets(symbol, entry_price, side)`
Розрахунок з SSOT конфігу per-symbol:
- Отримати `config.strategies.aurora.instruments[symbol]`
- Витягнути `exit.sl_pct`, `tp.tp_low_ratio`
- Витягнути `regime_tpsl.sl_mult[regime]`, `regime_tpsl.tp_mult[regime]`
- `regime` з `self._last_regime_by_symbol.get(symbol, "DEFAULT")`
- Формула:
  - `sl_pct_eff = sl_pct × sl_mult[regime]`
  - `tp_ratio_eff = tp_low_ratio × tp_mult[regime]`
  - BUY: `SL = entry × (1 - sl_pct_eff)`, `TP = entry × (1 + tp_ratio_eff)`
  - SELL: `SL = entry × (1 + sl_pct_eff)`, `TP = entry × (1 - tp_ratio_eff)`
- Return `(sl_price, tp_price)`

#### 2.3g: New method `_place_health_check_brackets(symbol, side, sl, tp, only_sl, only_tp)`
Використовує існуючі adapter методи:
- `adapter.place_stop_market_close_position()` для SL
- `adapter.place_take_profit_close_position()` для TP
- Preflight check через `_preflight_position_check(symbol)`
- Логування `[BRACKET-HEALTH]` для всіх подій

#### 2.3h: Schedule loop
В `_schedule_fsm_cleanup_loop` або окремо:
```python
def _schedule_bracket_health_loop(self):
    loop = self._get_async_loop()
    if loop:
        self._submit_async(self._bracket_health_loop(), loop)
```

Виклик після `_schedule_fsm_cleanup_loop()` (line ~510 area, після adapter init).

### Step 2.4: adapter.get_open_orders type enrichment

`adapter.get_open_orders(symbol)` повертає raw dict — потрібно перевірити чи включає `type` поле.
Якщо `ExchangeOrderResponse` не має `type`, додати простий raw fallback або mapper.

---

## Verification

### Тести для FIX 1
1. Watchdog fill payload містить `qty`, `side`, `clientOrderId`
2. ManageFlowFSM._on_fill коректно обробляє збагачений payload
3. Timeout fill → self.handle() → brackets + ManageFlowFSM update

### Тести для FIX 2
1. Config validation: BracketHealthCheckConfig з коректними/некоректними значеннями
2. `_check_brackets_on_exchange`: mock orders з STOP_MARKET/TAKE_PROFIT_MARKET
3. `_compute_health_check_brackets`: BTC BUY @ 100000, verify SL/TP vs config
4. Grace period: позиція відкрита < grace → skip
5. Full flow: mock adapter, open position, health check → brackets placed
6. Idempotency: brackets вже є → health check skip

### Ручна верифікація
1. Перезапустити систему з новим кодом
2. Дочекатись LIMIT entry fill для BTC/SOL
3. Перевірити логи: `[BRACKET-HEALTH]` або `[LIMIT-DEFERRED]` → brackets placed
4. Перевірити на біржі: SL/TP ордери існують
