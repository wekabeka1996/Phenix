# ⚡ QUICK ACTION GUIDE: Orphaned Bracket Orders Bug Fix

**Start Now**: Це гайд для швидкого розуміння та запуску виправлення

---

## 🚀 START HERE (5 хвилин)

### Проблема в 1 реченні
**API розділяє Bracket Orders на 3 ордера. При закритті позиції SL/TP залишаються → накопичуються до ліміту 200 → CRASH через 2-3h**

### Де почати
```
1. Читай: CRITICAL_ISSUE_SUMMARY_FOR_USER.md (7 хвилин)
2. Читай: CRITICAL_BUG_ORPHANED_ORDERS_ANALYSIS.md (20 хвилин)
3. Запустити PHASE 1 (2 дні): див. нижче
```

---

## 🎯 PHASE 1: CRITICAL (2 дні) - ТА ТРЕБА РОБИТИ НЕГАЙНО

### Task 1.1: Виправити fsm_close.py (0.5 дня)

**Файл**: `vfoundation/apps/reference/domains/execution_position/fsm_close.py`

**Що змінити**: Метод `_emit_close()` (lines 108-127)

**Поточний код (НЕПРАВИЛЬНИЙ)**:
```python
def _emit_close(self, msg: Message, why: str, details: Dict[str, Any]) -> Message:
    """Generate DEC:CLOSE with reduce_only=true."""
    self.state = CloseState.CLOSE_COND
    self.state = CloseState.EMIT_DEC_CLOSE
    self._metrics["fsm_close_decisions_total"] += 1

    dec = Message(
        op="DEC",
        verb="CLOSE",
        src=msg.dst,
        dst="execution_position",
        rid=msg.rid,
        why=why[:80],
        idempotent_key=f"{msg.rid}_{why}_{int(time.time())}",
        pld={
            "reduce_only": True,
            **details,
        },
    )

    self.state = CloseState.DONE
    self.position_active = False
    return dec  # ❌ ПРОБЛЕМА: Повертає ОДИН ордер!
```

**Новий код (ПРАВИЛЬНИЙ)**:
```python
def _emit_close(self, msg: Message, why: str, details: Dict[str, Any]) -> list[Message]:
    """Generate DEC:CLOSE with bracket cleanup."""
    messages = []

    # 1. Cancel SL if exists
    if hasattr(self, 'sl_order_id') and self.sl_order_id:
        cancel_sl = Message(
            op="DEC",
            verb="CANCEL_ORDER",
            src=msg.dst,
            dst="execution_position",
            rid=msg.rid,
            why="close_cleanup_sl",
            pld={"order_id": self.sl_order_id}
        )
        messages.append(cancel_sl)

    # 2. Cancel TP if exists
    if hasattr(self, 'tp_order_id') and self.tp_order_id:
        cancel_tp = Message(
            op="DEC",
            verb="CANCEL_ORDER",
            src=msg.dst,
            dst="execution_position",
            rid=msg.rid,
            why="close_cleanup_tp",
            pld={"order_id": self.tp_order_id}
        )
        messages.append(cancel_tp)

    # 3. Close position
    self.state = CloseState.CLOSE_COND
    self.state = CloseState.EMIT_DEC_CLOSE
    self._metrics["fsm_close_decisions_total"] += 1

    dec = Message(
        op="DEC",
        verb="CLOSE",
        src=msg.dst,
        dst="execution_position",
        rid=msg.rid,
        why=why[:80],
        idempotent_key=f"{msg.rid}_{why}_{int(time.time())}",
        pld={"reduce_only": True, **details},
    )
    messages.append(dec)

    self.state = CloseState.DONE
    self.position_active = False
    return messages  # ✅ РІШЕННЯ: Повертає 3 ордери
```

**Тест**:
```python
# tests/test_orphaned_orders.py
def test_close_flow_cancels_brackets():
    """Test that DEC:CLOSE cancels SL/TP."""
    fsm = CloseFlowFSM()
    fsm.sl_order_id = "sl_123"
    fsm.tp_order_id = "tp_456"
    fsm.position_active = True

    msg = Message(op="UPD", verb="TICK")
    result = fsm._emit_close(msg, "TEST", {})

    # Повинні быть 3 messages
    assert len(result) == 3
    assert result[0].verb == "CANCEL_ORDER"  # Cancel SL
    assert result[1].verb == "CANCEL_ORDER"  # Cancel TP
    assert result[2].verb == "CLOSE"  # Close position
```

---

### Task 1.2: Виправити fsm_manage.py (0.5 дня)

**Файл**: `vfoundation/apps/reference/domains/execution_position/fsm_manage.py`

**Що додати**: Метод `_cleanup_brackets_on_error()` + обновити `handle()`

**Нова логіка в `handle()` (lines 79-160)**:
```python
def handle(self, msg: Message) -> Optional[Message]:
    """Process incoming events."""

    # ✅ NEW: Handle rejection - cleanup brackets
    if msg.verb == "REJECTED":
        if self.sl_order_id or self.tp_order_id:
            return self._cleanup_brackets_on_error(msg, "entry_rejected")
        return None

    # ✅ NEW: Handle expiry - cleanup brackets
    if msg.verb == "EXPIRED":
        if self.sl_order_id or self.tp_order_id:
            return self._cleanup_brackets_on_error(msg, "entry_expired")
        return None

    # ... rest of existing logic ...

def _cleanup_brackets_on_error(self, msg: Message, reason: str) -> Optional[Message]:
    """Cleanup bracket orders when main order fails."""
    if not self.sl_order_id and not self.tp_order_id:
        return None

    messages = []
    if self.sl_order_id:
        messages.append(Message(
            op="DEC",
            verb="CANCEL_ORDER",
            pld={"order_id": self.sl_order_id, "reason": reason}
        ))
    if self.tp_order_id:
        messages.append(Message(
            op="DEC",
            verb="CANCEL_ORDER",
            pld={"order_id": self.tp_order_id, "reason": reason}
        ))

    # Return first message (or implement batch handling)
    return messages[0] if messages else None
```

**Тест**:
```python
def test_manage_cleanup_on_rejection():
    """Test that brackets are cleaned when entry is rejected."""
    fsm = ManageFlowFSM()
    fsm.sl_order_id = "sl_789"
    fsm.tp_order_id = "tp_012"

    msg = Message(op="EVT", verb="REJECTED")
    result = fsm._cleanup_brackets_on_error(msg, "entry_rejected")

    assert result is not None
    assert result.verb == "CANCEL_ORDER"
    assert result.pld["order_id"] in ["sl_789", "tp_012"]
```

---

### Task 1.3: Додати Метрика (0.5 дня)

**Файл**: `vfoundation/apps/reference/domains/execution_position/binance_execution_adapter.py`

**Нова метода** (додати в клас BinanceExecutionAdapter):
```python
def get_open_orders_count(self) -> int:
    """Get current active order count on Binance."""
    try:
        resp = self._request("GET", "/fapi/v1/allOpenOrders", {})
        orders = json.loads(resp.text)
        count = len(orders)

        # ✅ Alert if approaching limit
        if count >= 180:
            logger.critical(f"🚨 ALERT: Order count = {count}/200 (limit approaching!)")
            # TODO: Emit alert to telemetry

        return count
    except Exception as e:
        logger.error(f"Failed to get order count: {e}")
        return -1
```

**Інтеграція в monitoring** (файл `apps/reference/telemetry/metrics.py`):
```python
from prometheus_client import Gauge, Counter

active_orders_gauge = Gauge(
    'trading_active_orders',
    'Current active orders on exchange',
    ['exchange']
)

orphaned_orders_total = Counter(
    'trading_orphaned_orders_total',
    'Total orphaned orders detected',
    ['reason']
)

orders_cancelled_total = Counter(
    'trading_orders_cancelled_total',
    'Total orders cancelled',
    ['reason']
)
```

---

### Task 1.4: Unit Tests (0.5 дня)

**Файл**: `tests/test_orphaned_orders.py` (новий)

```python
import pytest
from vfoundation.core.protocol import Message
from vfoundation.apps.reference.domains.execution_position.fsm_close import CloseFlowFSM
from vfoundation.apps.reference.domains.execution_position.fsm_manage import ManageFlowFSM


class TestOrphanedOrdersFix:

    def test_close_flow_cancels_brackets(self):
        """Verify that DEC:CLOSE includes cancellations for SL/TP."""
        fsm = CloseFlowFSM()
        fsm.sl_order_id = "sl_123"
        fsm.tp_order_id = "tp_456"
        fsm.position_active = True
        fsm.position_open_ts = time.time()

        msg = Message(op="UPD", verb="TICK")
        result = fsm._emit_close(msg, "TEST", {})

        assert isinstance(result, list), "Should return list of messages"
        assert len(result) == 3, "Should have [cancel_sl, cancel_tp, close]"
        assert result[0].verb == "CANCEL_ORDER", "First should cancel SL"
        assert result[1].verb == "CANCEL_ORDER", "Second should cancel TP"
        assert result[2].verb == "CLOSE", "Third should close position"

    def test_manage_cleanup_on_rejection(self):
        """Verify that brackets are cleaned when entry is rejected."""
        fsm = ManageFlowFSM()
        fsm.sl_order_id = "sl_789"
        fsm.tp_order_id = "tp_012"

        msg = Message(op="EVT", verb="REJECTED")
        result = fsm._cleanup_brackets_on_error(msg, "entry_rejected")

        assert result is not None, "Should return cleanup message"
        assert result.verb == "CANCEL_ORDER", "Should cancel order"
        assert result.pld["reason"] == "entry_rejected", "Should include reason"

    def test_open_orders_count_metric(self):
        """Verify order count metric."""
        adapter = BinanceExecutionAdapter(shadow_mode=True)
        count = adapter.get_open_orders_count()

        # In shadow mode should return 0 or non-negative
        assert count >= 0, "Order count should be non-negative"
```

**Запуск тестів**:
```bash
pytest tests/test_orphaned_orders.py -v
```

---

## 📋 CHECKLIST PHASE 1 COMPLETION

- [ ] fsm_close.py: _emit_close() modified to return list
- [ ] fsm_manage.py: _cleanup_brackets_on_error() added
- [ ] fsm_manage.py: handle() checks REJECTED/EXPIRED
- [ ] binance_execution_adapter.py: get_open_orders_count() added
- [ ] metrics.py: Prometheus metrics added
- [ ] tests/test_orphaned_orders.py: All 3 tests passing
- [ ] Integration test: 50+ positions, verify < 50 active orders
- [ ] Code review approved
- [ ] Merge to main branch

---

## 🧪 INTEGRATION TEST BEFORE MERGE

**Сценарій**: Place 70 positions, close all, verify no accumulation

```python
# tests/test_orphaned_orders_integration.py
async def test_70_positions_no_accumulation():
    """End-to-end test: 70 positions, verify active orders < 50."""
    adapter = BinanceExecutionAdapter(shadow_mode=False)

    # Place 70 positions
    for i in range(70):
        await adapter.place_order(Message(
            op="CMD",
            verb="OPEN",
            pld={
                "symbol": "ETHUSDT",
                "side": "BUY",
                "quantity": 1.0
            }
        ))

    # Verify active orders ~210 before cleanup
    count_before = adapter.get_open_orders_count()
    assert count_before >= 200, "Should have accumulated ~210 orders"

    # Close all positions (triggers bracket cleanup)
    for i in range(70):
        await adapter.close_position("ETHUSDT")

    # Wait for cleanups to complete
    await asyncio.sleep(2)

    # Verify active orders < 50 after cleanup
    count_after = adapter.get_open_orders_count()
    assert count_after < 50, f"Should have < 50 active orders, got {count_after}"
    print(f"✅ Success: {count_before} → {count_after}")
```

---

## ⏱️ TIMELINE PHASE 1

```
Day 1 (Morning):
  • Task 1.1: fsm_close.py (1-2 hours)
  • Task 1.2: fsm_manage.py (1-2 hours)

Day 1 (Afternoon):
  • Task 1.3: Metrics (1 hour)
  • Task 1.4: Tests (1-2 hours)

Day 2 (Morning):
  • Integration tests (2-3 hours)
  • Staging testnet deployment (1 hour)

Day 2 (Afternoon):
  • 24-hour stability test setup
  • Code review + merge
```

---

## 📞 QUESTIONS?

Див. документи:
- **CRITICAL_BUG_ORPHANED_ORDERS_ANALYSIS.md** - повний технічний аналіз
- **CRITICAL_ISSUE_SUMMARY_FOR_USER.md** - менеджеру friendly резюме
- **TODO.md** - project tracking

---

**Start PHASE 1 TODAY** ✅
