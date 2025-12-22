# TASK40-I — One-Open-Order Guard (Stop ORDER_PLACED storms)

## Summary (Before/After)

**Before**
- При швидких повторних сигналам/тіках система могла емітити кілька OPEN-інтентів до того, як біржа підтвердить перший ордер → “storm” `ORDER_PLACED`.
- Не було жорсткого універсального правила “на символ — 1 in-flight ENTRY”.

**After**
- Додано guard: **на символ не більше 1 активного ENTRY в польоті**.
- Якщо `OrderIndex` показує in-flight ENTRY для символа → `DEFER` з причиною `NRR-ORDER-IN-FLIGHT`.
- Guard розблоковується, коли ордер стає terminal (fill/cancel/error).
- Додатково (belt+suspenders): при конвертації trade intent → `CMD:OPEN` створюється ранній `ENTRY_INTENT` ref в `OrderIndex`, щоб блокувати шторм до exchange ACK.

---

## Implementation Notes

**DecisionMaking**
- `apps/reference/domains/decision_making/decision_making.py` — `_propose_trade_intent()` перевіряє `fsm.order_index.has_in_flight_entry(symbol)` для non-reduce_only OPEN.

**OrderIndex**
- `apps/reference/domains/execution_position/order_index.py` — додано `has_in_flight_entry(symbol)` (ENTRY intent / `clientOrderId` префікс `ENTRY-`).

**ExecutionPosition FSM**
- `apps/reference/domains/execution_position/fsm.py` — на terminal подіях (fill/cancel) ref позначається terminal (розблоковує guard).

**Bridge**
- `apps/reference/main.py` — при `_dispatch_open` створюється ранній ref `ENTRY_INTENT` в `OrderIndex` і використовується стабільний `rid` для кореляції; при `ERR` ref помічається terminal, щоб не “залипати” в блокі.

---

## Changed / Added Files

- `apps/reference/domains/decision_making/decision_making.py`
- `apps/reference/domains/execution_position/order_index.py`
- `apps/reference/domains/execution_position/fsm.py`
- `apps/reference/main.py`
- `tests/domains/decision_making/test_task40_one_open_order_guard.py`

---

## Test Outputs (required)

Command:
`pytest -q tests/domains/decision_making/test_task40_one_open_order_guard.py`

```text
============================= test session starts ==============================
platform linux -- Python 3.12.3, pytest-9.0.1, pluggy-1.6.0
rootdir: /home/wekabeka/Музыка/Phenix
configfile: pytest.ini
collected 3 items

tests/domains/decision_making/test_task40_one_open_order_guard.py ...    [100%]

============================== 3 passed in 0.13s ===============================
```

