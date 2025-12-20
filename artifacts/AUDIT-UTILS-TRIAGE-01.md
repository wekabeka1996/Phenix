# [TASK] AUDIT-UTILS-TRIAGE-01 — execution_position utils triage

Дата: 2025-12-20

## 1) Reachability / доказ досяжності

### Модулі
- `apps/reference/domains/execution_position/order_index.py`
- `apps/reference/domains/execution_position/idempotent_cancel.py`
- (перенесено) `apps/monitoring/drift_monitor.py` (раніше було в execution_position)

### Фактичні імпорти/виклики (runtime)

**order_index**
- Composition root: `apps/reference/main.py` створює `OrderIndex` і підвішує його як `fsm.order_index` через `_init_order_index(...)`.
- WS consumer: `apps/reference/adapters/binance_ws_client.py` читає `fsm_core.order_index.get(...)` і на terminal-статусах викликає `mark_terminal(...)`.
- Domain producer: `apps/reference/domains/execution_position/fsm.py` робить `upsert_from_open(...)` + `attach_exchange_id(...)` при постановці ордера і викликає `expire()` на регулярному портфельному heartbeat.

**idempotent_cancel**
- Runtime-імпорти в composition root відсутні.
- Реальний cancel-path існує в `ExecPosFSM` і повтори можливі (manual close, timeout watchdog, bracket cleanup).
- З цього triage: інтегровано helper в єдиний cancel-шлях `ExecPosFSM._cancel_order(...)`.

**drift_monitor**
- Не імпортується runtime доменами.
- Використовується off-path: тести + `vfoundation` CLI/debug.
- Тому перенесено з execution_position домену в `apps/monitoring/drift_monitor.py`.

## 2) Короткий граф wiring

```
apps/reference/main.py
  ├─ FSMCore()
  │   └─ _init_order_index(...)  -> fsm.order_index = OrderIndex(...)
  ├─ ExecPosFSM(config=..., fsm=fsm)
  │   ├─ _cancel_order(...)      -> IdempotentCancelHelper.cancel_order_idempotent(...)
  │   ├─ upsert/attach (OPEN/PLACE_ORDER)
  │   └─ expire() на EVT:PORTFOLIO_STATE_UPDATED
  └─ BinanceWebSocketClient(..., fsm_core=fsm)
      └─ fsm_core.order_index.get(...) / mark_terminal(...)

apps/monitoring/drift_monitor.py
  └─ (off-path) використовується CLI/debug і тестами
```

Позначки:
- **WIRING є**: `order_index` — створюється в composition root, читається WS клієнтом.
- **WIRING є**: `idempotent_cancel` — входить в cancel-path `ExecPosFSM`.
- **WIRING нема і не треба**: `drift_monitor` — тільки off-path.

## 3) Тести / доказ роботи

- WS correlation (інтеграція): `tests/integration/test_binance_ws_order_index_correlation.py`
  - без `order_index` → WS update пропускається
  - з `order_index` → емісія EVT + `mark_terminal`

- Double cancel (-2011): `tests/unit/test_idempotent_cancel_logic.py`
  - перший cancel → `CANCELED`
  - другий cancel → `-2011 Unknown order` і все одно success

## 4) Примітка про drift_monitor

`drift_monitor` навмисно винесений з execution_position домену, щоб не плутати з hot-path кодом. Це аналітика/валідація shadow-mode.
