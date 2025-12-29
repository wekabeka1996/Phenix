# 🔧 План міграції: Async → Sync для MarketData Pipeline

## 📋 Зміст
1. [Проблема](#проблема)
2. [Діагностика](#діагностика)
3. [Варіанти рішень](#варіанти-рішень)
4. [План реалізації](#план-реалізації)
5. [Патчі](#патчі)
6. [Тестування](#тестування)
7. [Rollback план](#rollback-план)

---

## 🚨 Проблема

### Симптоми
```
21:52:26 - 📊 BNBUSDT Tick (перші 4 тіки разом)
21:53:17 - 📊 SOLUSDT Tick [GAP: 46s]  ← 46 секунд затримки!
21:53:47 - 📊 ETHUSDT Tick [GAP: 30s]  ← потім 30 сек
21:54:18 - 📊 BTCUSDT Tick [GAP: 31s]  ← потім 31 сек
```

**Features приходять раз на 30-50 секунд замість кожні 5 секунд!**

### Наслідки
- `features_stale` warning в DecisionMaking (TTL = 5s, lag = 45s)
- Торгові рішення відкладаються через застарілі дані
- Помилка `-1021 Timestamp outside recvWindow` через затримки в request lifecycle

### Кореневі причини
1. **FSM.emit() є синхронним** — викликає всі listeners послідовно
2. **Event chain блокує async loop:**
   ```
   EVT:MARKET_TICK_RECEIVED (async context)
       └── FeatureEngineering.on_market_tick() [SYNC]
           └── emit EVT:FEATURES_CALCULATED [SYNC]
               ├── RiskManagement.on_features_calculated() [SYNC]
               └── DecisionMaking.on_features() [SYNC]
                   └── Complex calculations...
   ```
3. **Весь ланцюжок виконується в async callback**, блокуючи `asyncio.sleep()` в `periodic_emit`

---

## 🔬 Діагностика

### Запуск діагностики (опціонально)

```python
# В main.py перед запуском:
from scripts.diag_fsm_timing import patch_fsm_emit
patch_fsm_emit(fsm)
```

Це покаже час виконання кожного listener.

### Очікуваний результат діагностики
```
📤 emit(EVT:MARKET_TICK_RECEIVED)
  🟢 [0] feature_engineering.on_market_tick: 5.2ms
  📊 Total: 5.2ms

📤 emit(EVT:FEATURES_CALCULATED)
  🟡 [0] risk_management.on_features_calculated: 15.3ms
  🔴 [1] decision_making.on_features: 120.5ms  ← BOTTLENECK
  📊 Total: 135.8ms
```

---

## 🎯 Варіанти рішень

### Варіант 1: Sync Threading для MarketDataConnector ⭐ РЕКОМЕНДОВАНО

**Суть:** Замінити async `periodic_emit` на sync loop в окремому thread.

**Переваги:**
- ✅ Простий і передбачуваний код
- ✅ Незалежний від async event loop
- ✅ Легкий debugging
- ✅ Мінімальні зміни в існуючому коді

**Недоліки:**
- ⚠️ WebSocket все ще потребує async (aiohttp)
- ⚠️ Потрібна синхронізація між threads

**Складність:** 🟢 Низька

**Файли для зміни:**
- `apps/reference/domains/market_data/market_data_connector.py`
- `apps/reference/domains/market_data/websocket_aggregator.py`

---

### Варіант 2: Event Queue + Worker Thread

**Суть:** FSM.emit() кладе події в queue, окремий worker thread обробляє їх.

**Переваги:**
- ✅ Повна ізоляція event processing від async loop
- ✅ Можна контролювати throughput
- ✅ Backpressure handling

**Недоліки:**
- ⚠️ Додаткова складність
- ⚠️ Потенційна затримка через queue
- ⚠️ Зміни в FSMCore

**Складність:** 🟡 Середня

**Файли для зміни:**
- `vfoundation/core/fsm_core.py`

---

### Варіант 3: Повна sync архітектура (requests замість httpx async)

**Суть:** Замінити всі async компоненти на sync.

**Переваги:**
- ✅ Найпростіший debugging
- ✅ Передбачувана поведінка
- ✅ Немає race conditions

**Недоліки:**
- ⚠️ Великий обсяг змін
- ⚠️ WebSocket потребує окремого рішення (websocket-client замість aiohttp)
- ⚠️ Можлива втрата паралелізму

**Складність:** 🔴 Висока

**Файли для зміни:**
- Всі adapters
- MarketDataConnector
- BinanceAdapter

---

### Варіант 4: Hybrid — Async WebSocket + Sync Emit via Queue

**Суть:** WebSocket залишається async, але emit відбувається через thread-safe queue.

**Переваги:**
- ✅ Зберігає переваги async WebSocket
- ✅ Sync processing для стабільності

**Недоліки:**
- ⚠️ Складна архітектура
- ⚠️ Два контексти виконання

**Складність:** 🟡 Середня

---

## 📅 План реалізації

### Етап 1: Варіант 1 — Sync Threading (ПОТОЧНИЙ)

#### Крок 1.1: Створити SyncEmitLoop
```
Файл: market_data_connector.py
Зміни: Додати _sync_emit_thread та _sync_emit_loop()
```

#### Крок 1.2: Рефакторинг start()
```
Файл: market_data_connector.py
Зміни: start() запускає sync thread замість async task
```

#### Крок 1.3: WebSocket залишити async
```
WebSocket stream обробляє дані та оновлює aggregator.state
Sync thread періодично читає state та emittить
```

#### Крок 1.4: Тестування
```
- Unit tests для нового коду
- Integration test з реальним WebSocket
- Перевірка timing (тіки кожні 5 сек)
```

### Етап 2: Варіант 2 (якщо Етап 1 не допоможе)

#### Крок 2.1: Додати EventQueue в FSMCore
#### Крок 2.2: Worker thread для processing
#### Крок 2.3: Тестування

### Етап 3: Варіант 3 (крайній випадок)

#### Повна міграція на sync

---

## 🔨 Патчі

### PATCH 1.1: SyncEmitLoop для MarketDataConnector

**Файл:** `apps/reference/domains/market_data/market_data_connector.py`

```python
# BEFORE (async):
async def periodic_emit(self, interval_seconds: float = 1.0) -> None:
    while True:
        for symbol in self.symbols:
            tick = self.get_market_tick(symbol)
            if tick and self.on_tick_callback:
                await self.on_tick_callback(symbol, tick)
        await asyncio.sleep(interval_seconds)

# AFTER (sync thread):
def _sync_emit_loop(self) -> None:
    """Synchronous emit loop running in dedicated thread."""
    LOG.info("🚀 Sync emit loop started")
    while self.running:
        try:
            for symbol in self.symbols:
                tick = self.aggregator.get_market_tick(symbol)
                if tick:
                    self._emit_market_tick(symbol, tick)

            for anchor in self.anchors:
                if anchor in self.aggregator.state:
                    price = self.aggregator.state[anchor].get("latest_price")
                    if price and self.feature_engineering:
                        self.feature_engineering.update_anchor_price(anchor, str(price))

            time.sleep(self.poll_interval_sec)
        except Exception as e:
            LOG.error(f"Error in sync emit loop: {e}", exc_info=True)
            time.sleep(1)  # Backoff on error
    LOG.info("🛑 Sync emit loop stopped")
```

### PATCH 1.2: Зміна start() методу

**Файл:** `apps/reference/domains/market_data/market_data_connector.py`

```python
# BEFORE:
def start(self) -> None:
    loop = asyncio.get_running_loop()
    self._emit_task = loop.create_task(
        self.aggregator.periodic_emit(self.poll_interval_sec)
    )
    self._ws_task = loop.create_task(self._ws_loop())

# AFTER:
def start(self) -> None:
    if self.running:
        LOG.warning("MarketDataConnector already running.")
        return

    self.running = True

    # Start WebSocket in async context (if available)
    try:
        loop = asyncio.get_running_loop()
        self._ws_task = loop.create_task(self._ws_loop())
    except RuntimeError:
        LOG.warning("No async loop, WebSocket will not start")

    # Start sync emit loop in dedicated thread
    self._emit_thread = threading.Thread(
        target=self._sync_emit_loop,
        name="MarketDataEmitter",
        daemon=True
    )
    self._emit_thread.start()

    LOG.info("✅ MarketDataConnector started (hybrid: async WS + sync emit)")
```

### PATCH 1.3: Оновлення imports

**Файл:** `apps/reference/domains/market_data/market_data_connector.py`

```python
# Додати:
import threading
import time
```

### PATCH 1.4: Оновлення stop() методу

**Файл:** `apps/reference/domains/market_data/market_data_connector.py`

```python
def stop(self) -> None:
    """Stop the connector gracefully."""
    LOG.info("Stopping MarketDataConnector...")
    self.running = False

    # Stop emit thread
    if self._emit_thread and self._emit_thread.is_alive():
        self._emit_thread.join(timeout=5.0)
        if self._emit_thread.is_alive():
            LOG.warning("Emit thread did not stop gracefully")

    # Cancel async tasks
    if self._ws_task:
        self._ws_task.cancel()

    # Close session
    if self.session and not self.session.closed:
        asyncio.create_task(self.session.close())

    LOG.info("✅ MarketDataConnector stopped")
```

---

### PATCH 2.1: EventQueue для FSMCore (Варіант 2)

**Файл:** `vfoundation/core/fsm_core.py`

```python
import queue
import threading
from typing import Tuple

class FSMCore:
    def __init__(self):
        self.listeners: Dict[str, list] = {}
        self.domains: Dict[str, Any] = {}
        self.logger = logging.getLogger(self.__class__.__name__)

        # Event queue for async-safe emit
        self._event_queue: queue.Queue[Tuple[str, Dict, str, list]] = queue.Queue()
        self._worker_running = False
        self._worker_thread: Optional[threading.Thread] = None

    def start_event_worker(self) -> None:
        """Start background worker for event processing."""
        if self._worker_running:
            return
        self._worker_running = True
        self._worker_thread = threading.Thread(
            target=self._process_events,
            name="FSMEventWorker",
            daemon=True
        )
        self._worker_thread.start()
        self.logger.info("FSM event worker started")

    def stop_event_worker(self) -> None:
        """Stop background worker."""
        self._worker_running = False
        self._event_queue.put((None, None, None, None))  # Sentinel
        if self._worker_thread:
            self._worker_thread.join(timeout=5.0)

    def _process_events(self) -> None:
        """Background worker that processes events from queue."""
        while self._worker_running:
            try:
                item = self._event_queue.get(timeout=1.0)
                if item[0] is None:  # Sentinel
                    break
                event_name, payload, why, data_ref = item
                self._emit_sync(event_name, payload, why, data_ref)
            except queue.Empty:
                continue
            except Exception as e:
                self.logger.exception(f"Error processing event: {e}")

    def emit(self, event_name: str, payload: Dict[str, Any], why: str,
             data_ref: Optional[List[str]] = None) -> None:
        """Queue event for processing (non-blocking)."""
        self._event_queue.put((event_name, payload, why, data_ref or []))

    def _emit_sync(self, event_name: str, payload: Dict[str, Any],
                   why: str, data_ref: List[str]) -> None:
        """Synchronously emit event to listeners."""
        if event_name not in self.listeners:
            return

        message = Message(
            op="EVT",
            verb=event_name.split(":")[1],
            src="fsm_core",
            dst="any",
            pld=payload,
            why=why,
            data_ref=data_ref,
        )

        for callback in self.listeners[event_name]:
            try:
                callback(message)
            except Exception as e:
                self.logger.exception(
                    f"Error in listener for {event_name}: {e}"
                )
```

---

## 🧪 Тестування

### Unit Tests для Варіанту 1

```python
# tests/domains/test_market_data_sync_emit.py

import pytest
import time
import threading
from unittest.mock import Mock, patch

class TestSyncEmitLoop:
    """Tests for synchronous emit loop."""

    def test_sync_emit_loop_runs_at_interval(self):
        """Verify emit loop runs at configured interval."""
        connector = create_test_connector(poll_interval=1)
        emissions = []

        def capture_emit(symbol, tick):
            emissions.append((time.time(), symbol))

        connector._emit_market_tick = capture_emit
        connector.running = True

        # Run for 3 seconds
        thread = threading.Thread(target=connector._sync_emit_loop)
        thread.start()
        time.sleep(3.5)
        connector.running = False
        thread.join()

        # Should have ~3 emissions per symbol
        assert len(emissions) >= 8  # 4 symbols * 2-3 iterations

    def test_sync_emit_loop_handles_errors(self):
        """Verify loop continues after errors."""
        connector = create_test_connector()
        call_count = 0

        def failing_emit(symbol, tick):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception("Test error")

        connector._emit_market_tick = failing_emit
        connector.running = True

        thread = threading.Thread(target=connector._sync_emit_loop)
        thread.start()
        time.sleep(2)
        connector.running = False
        thread.join()

        assert call_count >= 3  # Continued despite errors

    def test_thread_stops_gracefully(self):
        """Verify thread stops when running=False."""
        connector = create_test_connector()
        connector.running = True

        thread = threading.Thread(target=connector._sync_emit_loop)
        thread.start()

        time.sleep(0.5)
        connector.running = False
        thread.join(timeout=2)

        assert not thread.is_alive()
```

### Integration Test

```python
# tests/integration/test_market_data_timing.py

import pytest
import time

class TestMarketDataTiming:
    """Integration tests for market data timing."""

    @pytest.mark.integration
    def test_ticks_arrive_at_expected_interval(self, live_connector):
        """Verify ticks arrive every poll_interval seconds."""
        tick_times = []

        def capture_tick(event):
            tick_times.append(time.time())

        fsm.listen("EVT:MARKET_TICK_RECEIVED", capture_tick)

        live_connector.start()
        time.sleep(20)  # Run for 20 seconds
        live_connector.stop()

        # Calculate gaps
        gaps = [tick_times[i+1] - tick_times[i]
                for i in range(len(tick_times)-1)]

        avg_gap = sum(gaps) / len(gaps)
        max_gap = max(gaps)

        # Should be close to poll_interval (5s)
        assert avg_gap < 7, f"Average gap {avg_gap}s too high"
        assert max_gap < 10, f"Max gap {max_gap}s too high"
```

---

## 🔙 Rollback план

### Якщо Варіант 1 не працює:

1. Revert changes:
   ```bash
   git checkout HEAD~1 -- apps/reference/domains/market_data/market_data_connector.py
   ```

2. Перейти до Варіанту 2

### Якщо Варіант 2 не працює:

1. Revert FSMCore changes
2. Перейти до Варіанту 3 (повна sync міграція)

---

## 📊 Метрики успіху

| Метрика | До | Ціль |
|---------|-----|------|
| Tick gap avg | 30-50s | < 6s |
| Tick gap max | 50s | < 10s |
| features_stale warnings | Багато | 0 |
| Error -1021 | Є | 0 |

---

## 📝 Changelog

| Дата | Версія | Зміни |
|------|--------|-------|
| 2025-11-28 | 1.0 | Початковий план |
| 2025-11-28 | 1.1 | ✅ **Варіант 1 РЕАЛІЗОВАНО** — sync threading для MarketDataConnector. Gap зменшено з 30-50s до 5s! |

---

## ✅ СТАТУС: ВАРІАНТ 1 УСПІШНО РЕАЛІЗОВАНО

**Результати тестування:**
- Tick gap: **~5 секунд** (було 30-50 сек)
- Всі 4 символи emitяться разом (було по одному)
- Архітектура: Hybrid (async WebSocket + sync emit thread)

**Файли змінено:**
- `apps/reference/domains/market_data/market_data_connector.py`

---

## 🔗 Пов'язані документи

- `scripts/diag_fsm_timing.py` — діагностика timing
- `scripts/analyze_timeline.py` — аналіз логів
- `JOURNAL.md` — журнал змін
