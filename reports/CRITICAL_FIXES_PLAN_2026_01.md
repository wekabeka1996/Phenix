# 🔧 CRITICAL FIXES PLAN — Decision Making Domain

**Дата створення:** 2026-01-26  
**Автор:** System Architect  
**Статус:** DRAFT → REVIEW → APPROVED  
**Пріоритет:** P0-P2  

---

## 📋 Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [P0: Critical Fixes (Immediate)](#2-p0-critical-fixes-immediate)
   - [P0-1: OrderGuardian emit() API Mismatch](#p0-1-orderguardian-emit-api-mismatch)
   - [P0-2: Aurora monotonic_fn Determinism](#p0-2-aurora-monotonic_fn-determinism)
   - [P0-3: Aurora Position Tracking Phantom State](#p0-3-aurora-position-tracking-phantom-state)
3. [P1: High Priority Fixes (This Sprint)](#3-p1-high-priority-fixes-this-sprint)
   - [P1-1: Aurora Warmup Source Unification](#p1-1-aurora-warmup-source-unification)
   - [P1-2: Features Snapshot TTL Validation](#p1-2-features-snapshot-ttl-validation)
4. [P2: Medium Priority (Roadmap)](#4-p2-medium-priority-roadmap)
   - [P2-1: FSMCore Thread Safety](#p2-1-fsmcore-thread-safety)
5. [Testing Strategy](#5-testing-strategy)
6. [Validation Checklist](#6-validation-checklist)
7. [Rollout Plan](#7-rollout-plan)

---

## 1. Executive Summary

### Виявлені критичні проблеми

| ID | Проблема | Severity | Impact |
|----|----------|----------|--------|
| P0-1 | OrderGuardian.emit() missing `why` argument | 🔴 CRITICAL | EVT:SYMBOL_TIDY мовчки не працює |
| P0-2 | Aurora `monotonic_fn` fallback на `time.monotonic` | 🔴 CRITICAL | Backtest non-determinism |
| P0-3 | Aurora position_side не синхронізований з реальними fills | 🔴 CRITICAL | Holding period phantom blocks |
| P1-1 | Aurora warmup перезаписується з 3 джерел | 🟠 HIGH | Split-brain readiness |
| P1-2 | Features TTL перевіряється по cached snapshot, не по signal | 🟠 HIGH | Valid signals rejected |
| P2-1 | FSMCore.emit() не thread-safe | 🟡 MEDIUM | Potential race conditions |

### Принципи виправлення

1. **NO SILENT FALLBACKS** — Кожен fallback має логуватись як WARNING або CRITICAL
2. **PYDANTIC VALIDATION** — Всі конфіги через typed models, не dict
3. **NO HARDCODED PARAMS** — Все з config YAML через DomainConfigResolver
4. **FAIL-CLOSED** — При невизначеності → block, не allow
5. **DETERMINISTIC TIME** — Всі clock calls через `get_clock()` abstraction

---

## 2. P0: Critical Fixes (Immediate)

### P0-1: OrderGuardian emit() API Mismatch

#### Problem Statement

**Location:** `apps/reference/services/order_guardian.py` lines 970, 1189

**Current (BROKEN):**
```python
self.bus.emit("EVT:SYMBOL_TIDY", {"symbol": tidy_symbol, "source": "guardian_poll"})
```

**FSMCore.emit() signature:**
```python
def emit(self, event_name: str, payload: Dict[str, Any], why: str, data_ref: Optional[List[str]] = None) -> None:
```

**Impact:** TypeError silently swallowed → EVT:SYMBOL_TIDY never delivered → ExecPosFSM._on_symbol_tidy_event never called.

#### Solution Design

```python
# BEFORE (silent failure):
try:
    self.bus.emit("EVT:SYMBOL_TIDY", {"symbol": tidy_symbol, "source": "guardian_poll"})
except Exception:
    pass  # SILENT SWALLOW!

# AFTER (correct API + explicit logging):
try:
    self.bus.emit(
        "EVT:SYMBOL_TIDY",
        {"symbol": tidy_symbol, "source": "guardian_poll"},
        why="guardian:orphan_cleanup:tidy",
    )
except Exception as e:
    LOG.error(f"[{tidy_symbol}] Failed to emit EVT:SYMBOL_TIDY: {e}")
```

#### Implementation Steps

| Step | Action | File | Lines |
|------|--------|------|-------|
| 1 | Add `why` parameter to first emit call | `order_guardian.py` | 970-971 |
| 2 | Add `why` parameter to second emit call | `order_guardian.py` | 1189-1190 |
| 3 | Replace silent `except: pass` with explicit logging | Both locations | |
| 4 | Add integration test for TIDY event delivery | `tests/integration/` | New file |

#### Code Changes

```python
# File: apps/reference/services/order_guardian.py
# Location 1: Line 970

# REPLACE:
                    try:
                        self.bus.emit("EVT:SYMBOL_TIDY", {
                                      "symbol": tidy_symbol, "source": "guardian_poll"})
                    except Exception:
                        pass

# WITH:
                    try:
                        self.bus.emit(
                            "EVT:SYMBOL_TIDY",
                            {"symbol": tidy_symbol, "source": "guardian_poll", "ts_ms": int(self.clock.time() * 1000)},
                            why="guardian:orphan_cleanup:tidy",
                        )
                    except Exception as e:
                        LOG.error(f"[{tidy_symbol}] CRITICAL: Failed to emit EVT:SYMBOL_TIDY: {e}")
```

```python
# Location 2: Line 1189

# REPLACE:
                        self.bus.emit("EVT:SYMBOL_TIDY", {
                                      "symbol": symbol, "rid": rid})
                    except Exception:
                        pass

# WITH:
                        self.bus.emit(
                            "EVT:SYMBOL_TIDY",
                            {"symbol": symbol, "rid": rid, "source": "guardian_reconcile", "ts_ms": int(self.clock.time() * 1000)},
                            why=f"guardian:reconcile:tidy:rid={rid}",
                        )
                    except Exception as e:
                        LOG.error(f"[{symbol}] CRITICAL: Failed to emit EVT:SYMBOL_TIDY: {e}")
```

#### Testing Strategy

##### Unit Test

```python
# tests/units/test_order_guardian_emit.py

import pytest
from unittest.mock import MagicMock, call
from apps.reference.services.order_guardian import OrderGuardian

class TestOrderGuardianEmit:
    """P0-1: Verify EVT:SYMBOL_TIDY emission uses correct FSMCore API."""
    
    def test_emit_symbol_tidy_includes_why_parameter(self):
        """CRITICAL: emit() must include 'why' parameter for FSMCore compatibility."""
        mock_bus = MagicMock()
        mock_adapter = MagicMock()
        mock_clock = MagicMock()
        mock_clock.time.return_value = 1705000000.0
        
        guardian = OrderGuardian(
            adapter=mock_adapter,
            clock=mock_clock,
            bus=mock_bus,
        )
        
        # Simulate orphan cleanup that triggers TIDY
        guardian._known_symbols = {"BTCUSDT"}
        # ... trigger cleanup ...
        
        # VERIFY: emit called with 3 positional args (event, payload, why)
        for call_args in mock_bus.emit.call_args_list:
            args, kwargs = call_args
            assert len(args) >= 3 or "why" in kwargs, \
                f"emit() missing 'why' parameter: {call_args}"
    
    def test_emit_failure_is_logged_not_swallowed(self, caplog):
        """CRITICAL: emit() failures must be logged, not silently swallowed."""
        mock_bus = MagicMock()
        mock_bus.emit.side_effect = TypeError("Missing argument 'why'")
        
        guardian = OrderGuardian(adapter=None, bus=mock_bus)
        
        # Trigger emit path
        # ... 
        
        # VERIFY: Error is logged
        assert "CRITICAL: Failed to emit EVT:SYMBOL_TIDY" in caplog.text
```

##### Integration Test

```python
# tests/integration/test_guardian_tidy_delivery.py

import pytest
from vfoundation.core import FSMCore
from apps.reference.services.order_guardian import OrderGuardian

class TestGuardianTidyDelivery:
    """P0-1: End-to-end verification of TIDY event delivery."""
    
    def test_tidy_event_reaches_exec_pos_fsm(self):
        """CRITICAL: EVT:SYMBOL_TIDY must be received by ExecPosFSM."""
        fsm = FSMCore()
        received_events = []
        
        def capture_tidy(event):
            received_events.append(event)
        
        fsm.listen("EVT:SYMBOL_TIDY", capture_tidy)
        
        guardian = OrderGuardian(adapter=None, bus=fsm, clock=MagicMock(time=lambda: 1705000000.0))
        
        # Manually trigger emit (simulate cleanup)
        guardian.bus.emit(
            "EVT:SYMBOL_TIDY",
            {"symbol": "BTCUSDT", "source": "test"},
            why="test:tidy",
        )
        
        # VERIFY: Event was delivered
        assert len(received_events) == 1
        assert received_events[0].pld["symbol"] == "BTCUSDT"
```

#### Validation Criteria

| Check | Method | Expected |
|-------|--------|----------|
| No TypeError on emit | Unit test | Pass |
| Event delivered to listener | Integration test | Pass |
| Error logged on failure | caplog assertion | Contains "CRITICAL" |
| grep for silent `except.*pass` near emit | Code review | Zero matches |

---

### P0-2: Aurora monotonic_fn Determinism

#### Problem Statement

**Location:** `apps/reference/domains/decision_making/aurora_handler.py` line 120

**Current (NON-DETERMINISTIC):**
```python
self.monotonic_fn: Callable[[], float] = monotonic_fn or time.monotonic
```

**Impact:** In backtest, if `monotonic_fn` not injected → `time.monotonic` used → holding periods, re-entry cooldowns are wall-clock based → non-deterministic replays.

#### Solution Design

```python
# BEFORE (non-deterministic fallback):
self.monotonic_fn: Callable[[], float] = monotonic_fn or time.monotonic

# AFTER (deterministic fallback via get_clock()):
from apps.reference.core.time import get_clock

self.monotonic_fn: Callable[[], float] = monotonic_fn or (lambda: get_clock().monotonic())
```

#### Implementation Steps

| Step | Action | File | Lines |
|------|--------|------|-------|
| 1 | Import `get_clock` at module level | `aurora_handler.py` | 21 (already exists) |
| 2 | Replace `time.monotonic` fallback with `get_clock().monotonic()` | `aurora_handler.py` | 120 |
| 3 | Remove direct `import time` if no longer needed | `aurora_handler.py` | Header |
| 4 | Add determinism test with MockClock | `tests/` | New file |

#### Code Changes

```python
# File: apps/reference/domains/decision_making/aurora_handler.py

# Line 120 - REPLACE:
        self.monotonic_fn: Callable[[], float] = monotonic_fn or time.monotonic

# WITH:
        # DET-BT-FIX-01: Use get_clock().monotonic() for deterministic backtest
        # NEVER fallback to time.monotonic directly - breaks replay determinism
        self.monotonic_fn: Callable[[], float] = monotonic_fn or (lambda: get_clock().monotonic())
```

#### Testing Strategy

##### Unit Test

```python
# tests/units/test_aurora_handler_determinism.py

import pytest
from unittest.mock import MagicMock
from apps.reference.core.time import MockClock, set_clock, reset_clock
from apps.reference.domains.decision_making.aurora_handler import AuroraHandler

class TestAuroraHandlerDeterminism:
    """P0-2: Verify Aurora uses deterministic clock in backtest."""
    
    def setup_method(self):
        reset_clock()
    
    def teardown_method(self):
        reset_clock()
    
    def test_monotonic_fn_uses_mock_clock_when_set(self):
        """CRITICAL: monotonic_fn must use get_clock() not time.monotonic."""
        mock_clock = MockClock(start_ms=1705000000000, start_monotonic=1000.0)
        set_clock(mock_clock)
        
        mock_config = MagicMock()
        mock_config.strategies.aurora.timeframe_sec = 300
        mock_config.strategies.aurora.decision = MagicMock()
        
        handler = AuroraHandler(
            config=mock_config,
            emit_fn=lambda *args: None,
            # NOT passing monotonic_fn - should use fallback
        )
        
        # Advance mock clock
        mock_clock.advance_sec(10.0)
        
        # VERIFY: Handler reads from mock clock, not wall clock
        result = handler.monotonic_fn()
        assert result == 1010.0, f"Expected 1010.0 from MockClock, got {result} (likely wall clock)"
    
    def test_holding_period_deterministic_in_backtest(self):
        """CRITICAL: Holding period check uses mock clock time."""
        mock_clock = MockClock(start_ms=1705000000000, start_monotonic=0.0)
        set_clock(mock_clock)
        
        handler = self._create_handler()
        symbol = "BTCUSDT"
        
        # Track entry
        handler._track_entry(symbol, "buy")
        entry_time = handler._symbol_states[symbol].entry_timestamp
        
        # Advance mock clock by 20 seconds (less than 30s holding period)
        mock_clock.advance_sec(20.0)
        
        # Should still be in holding period
        mock_result = MagicMock(score=0.3)  # Weak signal
        assert handler._should_suppress_soft_exit(symbol, mock_result) == True
        
        # Advance past holding period
        mock_clock.advance_sec(15.0)  # Total 35s
        
        # Should allow exit now
        assert handler._should_suppress_soft_exit(symbol, mock_result) == False
```

##### Backtest Determinism Test

```python
# tests/backtest/test_replay_determinism.py

def test_two_runs_produce_identical_results():
    """P0-2: Two backtest runs with same data must produce identical trades."""
    from backtest_engine.engine import BacktestEngine
    
    config = load_test_config()
    data = load_test_data("btcusdt_2024_01.parquet")
    
    # Run 1
    engine1 = BacktestEngine(config)
    result1 = engine1.run(data)
    trades1 = result1.trades
    
    # Run 2 (fresh engine)
    engine2 = BacktestEngine(config)
    result2 = engine2.run(data)
    trades2 = result2.trades
    
    # VERIFY: Identical trades
    assert len(trades1) == len(trades2), "Trade count mismatch"
    for t1, t2 in zip(trades1, trades2):
        assert t1.symbol == t2.symbol
        assert t1.side == t2.side
        assert t1.ts_ms == t2.ts_ms
        assert t1.qty == t2.qty
```

#### Validation Criteria

| Check | Method | Expected |
|-------|--------|----------|
| No `time.monotonic` direct calls in aurora_handler | `grep -n "time.monotonic" aurora_handler.py` | 0 matches |
| MockClock used when set_clock() called | Unit test | Pass |
| Two backtest runs identical | Replay test | 100% match |

---

### P0-3: Aurora Position Tracking Phantom State

#### Problem Statement

**Location:** `apps/reference/domains/decision_making/aurora_handler.py`

**Current (PHANTOM STATE):**
- Aurora tracks `position_side`, `entry_timestamp` locally
- State updated on signal emission (`_track_entry`)
- **NEVER updated on actual order fills/cancels**
- Result: Holding period blocks even when order was cancelled

**Missing Listeners:**
```python
# aurora_builtin.py registers only:
self.fsm.listen("CMD:PROCESS_STRATEGY", ...)
self.fsm.listen("EVT:REGIME_DETECTED", ...)
self.fsm.listen("EVT:FEATURES_CALCULATED", ...)

# MISSING:
# self.fsm.listen("EVT:TRADE_EXECUTED", ...)
# self.fsm.listen("EVT:PORTFOLIO_STATE_UPDATED", ...)
```

#### Solution Design

**Option A: Reactive (Listen to executions)** ✅ RECOMMENDED
- Aurora listens to `EVT:TRADE_EXECUTED`
- Updates `position_side` only on confirmed fills
- Clears `entry_timestamp` on exit (opposite-side trade)

**Option B: Query-based (Ask portfolio)**
- Aurora queries `DecisionMaking.latest_portfolio` before holding period check
- More accurate but adds coupling

**Selected: Option A** — Event-driven fits existing architecture.

#### Implementation Steps

| Step | Action | File | Lines |
|------|--------|------|-------|
| 1 | Add `on_trade_executed` handler | `aurora_handler.py` | New method |
| 2 | Register listener in wrapper | `aurora_builtin.py` | After line 47 |
| 3 | Remove speculative entry tracking | `aurora_handler.py` | ~845 |
| 4 | Add tests for execution-driven sync | `tests/` | New file |

#### Code Changes

```python
# File: apps/reference/domains/decision_making/aurora_handler.py

# Add new method after _clear_entry (around line 1085):

    def on_trade_executed(self, event: Dict[str, Any]) -> None:
        """
        P0-3-FIX: Sync position tracking with EVT:TRADE_EXECUTED.

        Entry tracking is updated ONLY on real trades, not on signal emission.
        """
        symbol = event.get("symbol")
        if not symbol:
            return

        state = self._symbol_states[symbol]
        side = str(event.get("side", "")).lower()
        if side not in ("buy", "sell"):
            return

        qty_raw = event.get("quantity")
        try:
            qty = float(qty_raw) if qty_raw is not None else 0.0
        except (TypeError, ValueError):
            qty = 0.0
        if qty == 0.0:
            return

        if state.position_side == "":
            state.entry_timestamp = float(self.monotonic_fn())
            state.position_side = side
            self.logger.info(
                f"[{symbol}] TRADE_EXECUTED: entry confirmed (side={side}, qty={qty})"
            )
            return

        if state.position_side == side:
            self.logger.debug(
                f"[{symbol}] TRADE_EXECUTED: add to position (side={side}, qty={qty})"
            )
            return

        prev_side = state.position_side
        state.last_exit_timestamp = float(self.monotonic_fn())
        state.entry_timestamp = None
        state.position_side = ""
        self.logger.info(
            f"[{symbol}] TRADE_EXECUTED: exit detected (prev={prev_side}, side={side}, qty={qty})"
        )
```

```python
# File: apps/reference/domains/strategies/plugins/aurora_builtin.py

# Add to _AuroraHandlerWrapper.register() after line 47:

    def register(self) -> None:
        """Register event listeners for Aurora handler."""
        logger.info("🚀 Aurora Strategy: Registering Event Listeners")
        
        # Primary trigger
        self.fsm.listen("CMD:PROCESS_STRATEGY", self._on_process_strategy)
        
        # State updates
        self.fsm.listen("EVT:REGIME_DETECTED", self._on_regime)
        self.fsm.listen("EVT:FEATURES_CALCULATED", self._on_features_data_only)
        
        # P0-3-FIX: Position state sync via canonical execution event
        self.fsm.listen("EVT:TRADE_EXECUTED", self._on_trade_executed)

        def _on_trade_executed(self, event: Any) -> None:
            """P0-3-FIX: Forward execution events to handler."""
            pld = event.pld if hasattr(event, "pld") else event
            self.handler.on_trade_executed(pld)
```

#### Critical Design Decision

**Speculative vs Confirmed Entry Tracking:**

```
Current (BROKEN):
Signal Emitted → _track_entry() → entry_timestamp SET
                                         ↓
                               Holding period ACTIVE
                                         ↓
                     Order Cancelled → entry_timestamp STILL SET ❌
                                         ↓
                         Next signal → BLOCKED by phantom hold


Fixed (P0-3):
Signal Emitted → (no immediate tracking)
    ↓
Real trade occurs
    ↓
EVT:TRADE_EXECUTED → on_trade_executed() → entry_timestamp SET ✅
```

**CRITICAL:** Remove speculative tracking from `_emit_signal`:

```python
# REMOVE from _process_decision() (around line 845):
# === [TRACK ENTRY FOR HOLDING PERIOD] ===
# if effective_side and effective_side.lower() != current_position_side:
#     self._track_entry(symbol, effective_side)  # ← DELETE THIS
# === END TRACK ENTRY ===
```

#### Testing Strategy

##### Unit Test

```python
# tests/units/test_aurora_position_sync.py

class TestAuroraPositionSync:
    """P0-3: Verify position state syncs with actual fills, not signal emission."""
    
    def test_entry_timestamp_not_set_on_signal_emission(self):
        """entry_timestamp must NOT be set when signal emitted (only on fill)."""
        handler = self._create_handler()
        
        # Emit signal (no fill yet)
        handler._emit_signal("BTCUSDT", mock_result, mock_features, mock_cmd)
        
        state = handler._symbol_states["BTCUSDT"]
        assert state.entry_timestamp is None, "entry_timestamp set before fill!"
    
    def test_entry_timestamp_set_on_trade_executed(self):
        """entry_timestamp MUST be set when EVT:TRADE_EXECUTED received."""
        handler = self._create_handler()
        
        handler.on_trade_executed({
            "symbol": "BTCUSDT",
            "side": "buy",
            "quantity": "0.1",
        })
        
        state = handler._symbol_states["BTCUSDT"]
        assert state.entry_timestamp is not None
        assert state.position_side == "buy"
    
    def test_entry_timestamp_cleared_on_opposite_trade(self):
        """entry_timestamp MUST be cleared on opposite-side trade."""
        handler = self._create_handler()
        
        # Simulate pending state (signal emitted but not filled)
        handler._symbol_states["BTCUSDT"].entry_timestamp = 1000.0
        handler._symbol_states["BTCUSDT"].position_side = "buy"
        
        handler.on_trade_executed({
            "symbol": "BTCUSDT",
            "side": "sell",
            "quantity": "0.1",
        })
        
        state = handler._symbol_states["BTCUSDT"]
        assert state.entry_timestamp is None
        assert state.position_side == ""
    
    def test_holding_period_not_blocking_after_cancel(self):
        """Holding period must NOT block new entries after previous order cancelled."""
        handler = self._create_handler()
        
        # Order 1: Emitted → Cancelled (never filled)
        handler.on_order_cancelled({"symbol": "BTCUSDT", "reduce_only": False})
        
        # Order 2: New signal should NOT be blocked by holding period
        mock_result = MagicMock(score=0.5, side="BUY")
        
        # Should return False (not suppressed)
        assert handler._should_suppress_soft_exit("BTCUSDT", mock_result) == False
```

##### Integration Test

```python
# tests/integration/test_aurora_fill_sync.py

def test_aurora_receives_trade_executed_events_from_fsm():
    """P0-3: Verify Aurora handler is wired to receive TRADE_EXECUTED."""
    from vfoundation.core import FSMCore
    from apps.reference.domains.strategies.plugins.aurora_builtin import AuroraBuiltinPlugin
    
    fsm = FSMCore()
    config = create_test_config(legacy_tick_path_enabled=False)
    
    plugin = AuroraBuiltinPlugin()
    handler_wrapper = plugin.create_handler(fsm=fsm, config=config)
    handler_wrapper.register()
    
    # VERIFY: Listener registered
    assert "EVT:TRADE_EXECUTED" in fsm.listeners

    # Emit trade executed event
    fsm.emit(
        "EVT:TRADE_EXECUTED",
        {"symbol": "BTCUSDT", "side": "buy", "quantity": "0.1", "price": "100", "ts": 1705000000000, "venue": "test"},
        why="test:trade",
    )
    
    # VERIFY: Handler state updated
    state = handler_wrapper.handler._symbol_states.get("BTCUSDT")
    assert state is not None
    assert state.position_side == "buy"
```

#### Validation Criteria

| Check | Method | Expected |
|-------|--------|----------|
| Listeners registered for ORDER_FILLED | Integration test | Pass |
| entry_timestamp not set on signal | Unit test | Pass |
| entry_timestamp set on fill | Unit test | Pass |
| entry_timestamp cleared on cancel | Unit test | Pass |
| No holding period phantom blocks | E2E test | Pass |

---

## 3. P1: High Priority Fixes (This Sprint)

### P1-1: Aurora Warmup Source Unification

#### Problem Statement

**Location:** `apps/reference/domains/decision_making/aurora_handler.py`

**Current (SPLIT-BRAIN):**
```python
# Source 1: EVT:REGIME_DETECTED (line 439-441)
warmup = event.get("warmup", {})
state.warmup_full_ready = bool(warmup.get("full_ready", False))

# Source 2: EVT:FEATURES_CALCULATED (line 553-555)
warmup = event.get("warmup", {})
state.warmup_full_ready = bool(warmup.get("full_ready", False))

# Source 3: CMD:PROCESS_STRATEGY (line 597-598)
warmup = cmd.get("warmup", {})
state.warmup_full_ready = bool(warmup.get("full_ready", False))
```

**Risk:** Race condition where events arrive out-of-order, last writer wins.

#### Solution Design

**SSOT Principle:** `CMD:PROCESS_STRATEGY.warmup` is the authoritative source.

```python
# REGIME_DETECTED: DO NOT update warmup_full_ready (regime only)
# FEATURES_CALCULATED: Cache for vol-gates only, no warmup update
# CMD:PROCESS_STRATEGY: AUTHORITATIVE warmup source
```

#### Code Changes

```python
# File: aurora_handler.py

# Line 439-441 - REMOVE warmup update from REGIME_DETECTED:
    def on_regime_detected(self, event: Dict[str, Any]) -> None:
        # ... existing code ...
        
        # P1-1-FIX: DO NOT update warmup from REGIME_DETECTED
        # SSOT: warmup comes from CMD:PROCESS_STRATEGY only
        # warmup = event.get("warmup", {})  # REMOVED
        # state.warmup_full_ready = bool(warmup.get("full_ready", False))  # REMOVED
        # state.warmup_ticks_seen = int(warmup.get("ticks_seen", 0))  # REMOVED

# Line 553-555 - REMOVE warmup update from FEATURES_CALCULATED:
    def on_features_data_only(self, event: Dict[str, Any]) -> None:
        # P1-1-FIX: DO NOT update warmup from FEATURES_CALCULATED
        # Only cache price_motion for vol-adj gates
        # warmup = event.get("warmup", {})  # REMOVED
        # state.warmup_full_ready = bool(warmup.get("full_ready", False))  # REMOVED
        # state.warmup_ticks_seen = int(warmup.get("ticks_seen", 0))  # REMOVED
```

#### Testing Strategy

```python
def test_warmup_only_from_cmd_process_strategy():
    """P1-1: warmup_full_ready must only update from CMD:PROCESS_STRATEGY."""
    handler = create_handler()
    
    # Initial state
    assert handler._symbol_states["BTCUSDT"].warmup_full_ready == False
    
    # REGIME_DETECTED with warmup=True - should NOT update
    handler.on_regime_detected({
        "symbol": "BTCUSDT",
        "regime": "TREND_UP",
        "warmup": {"full_ready": True, "ticks_seen": 100},
    })
    assert handler._symbol_states["BTCUSDT"].warmup_full_ready == False  # Unchanged!
    
    # FEATURES_CALCULATED with warmup=True - should NOT update
    handler.on_features_data_only({
        "symbol": "BTCUSDT",
        "warmup": {"full_ready": True, "ticks_seen": 100},
    })
    assert handler._symbol_states["BTCUSDT"].warmup_full_ready == False  # Unchanged!
    
    # CMD:PROCESS_STRATEGY with warmup=True - SHOULD update
    handler.on_process_strategy({
        "symbol": "BTCUSDT",
        "tf_sec": 300,
        "bar_close_ts": 1705000000000,
        "warmup": {"full_ready": True},
    })
    assert handler._symbol_states["BTCUSDT"].warmup_full_ready == True  # Updated!
```

---

### P1-2: Features Snapshot TTL Validation

#### Problem Statement

**Location:** `apps/reference/domains/decision_making/decision_making.py` line 956

**Current (SNAPSHOT MISMATCH):**
```python
# Gateway checks TTL against CACHED features:
features_data = self.symbol_states[symbol].get("features") or {}
features_ts = features_data.get("ts", 0)

# But signal was computed on CMD.features (different snapshot!)
```

#### Solution Design

**Option A: Use signal timestamp** ✅ RECOMMENDED
- Signal payload contains `ts_ms` from bar
- Gateway validates `ts_ms` against current time, not cached features

**Option B: Pass features_ts in signal**
- Strategy includes `features_ts` in signal payload
- Gateway uses that for TTL check

**Selected: Option A + B** — Use signal's `ts_ms` and add explicit `features_ts`.

#### Code Changes

```python
# File: decision_making.py - _on_strategy_signal_gateway

# Line 956-980 - REPLACE TTL check:

            # === GATE 5: TTL GATE (features freshness) ===
            # P1-2-FIX: Use signal's ts_ms as reference, not cached features
            # Signal was computed at ts_ms, that's what we validate
            signal_ts_ms = pld.get("ts_ms", 0)
            if signal_ts_ms <= 0:
                self.logger.warning(f"[{symbol}] STRATEGY_SIGNAL_GATEWAY: REJECT - Missing ts_ms in signal")
                self._record_blocked_intent(symbol)
                return
            
            current_ms = self._clock.now_ms()
            
            # BAR-TTL-REFORM-01: Use tf_sec from signal for bar-specific TTL
            tf_sec_val = int(pld.get("tf_sec") or 0)
            is_bar = tf_sec_val > 0
            
            if is_bar:
                # Bar TTL: signal valid for bar_duration + grace period
                bar_ttl_ms = tf_sec_val * 1000 * 2  # 2x bar duration as grace
                sys_md = getattr(self.config.system, "market_data", None)
                if sys_md:
                    bar_ttl_ms = float(getattr(sys_md, "bar_ttl_ms", bar_ttl_ms) or bar_ttl_ms)
                ttl_ms = bar_ttl_ms
            else:
                ttl_ms = self.features_ttl_sec * 1000
            
            signal_age_ms = current_ms - signal_ts_ms
            
            if signal_age_ms > ttl_ms:
                self.logger.info(
                    f"[{symbol}] STRATEGY_SIGNAL_GATEWAY: REJECT - Signal stale "
                    f"(age={signal_age_ms}ms > ttl={ttl_ms}ms, signal_ts={signal_ts_ms})"
                )
                self._record_blocked_intent(symbol)
                return
```

---

## 4. P2: Medium Priority (Roadmap)

### P2-1: FSMCore Thread Safety

#### Problem Statement

**Location:** `vfoundation/core/fsm_core.py` line 38

**Current (NO LOCKS):**
```python
def emit(self, event_name: str, payload: Dict[str, Any], why: str, ...):
    if event_name in self.listeners:
        for callback in self.listeners[event_name]:  # No lock!
            callback(message)
```

**Risk:** If listener list modified during iteration → RuntimeError or missed events.

#### Solution Design

```python
import threading

class FSMCore:
    def __init__(self):
        self.listeners: Dict[str, List[Callable]] = {}
        self._lock = threading.RLock()  # Reentrant for nested emits
    
    def listen(self, event_name: str, callback: Callable) -> None:
        with self._lock:
            if event_name not in self.listeners:
                self.listeners[event_name] = []
            self.listeners[event_name].append(callback)
    
    def emit(self, event_name: str, payload: Dict[str, Any], why: str, ...) -> None:
        with self._lock:
            callbacks = list(self.listeners.get(event_name, []))  # Copy under lock
        
        # Call outside lock to prevent deadlock
        for callback in callbacks:
            try:
                callback(message)
            except Exception as e:
                self.logger.exception(...)
```

**Status:** Implemented (thread-safe listener registry with copy-on-emit).

---

## 5. Testing Strategy

### Test Pyramid

```
                    ┌─────────────────┐
                    │   E2E Backtest  │  ← Determinism, full flow
                    │   (1-2 tests)   │
                    └────────┬────────┘
                             │
                    ┌────────┴────────┐
                    │   Integration   │  ← Event delivery, state sync
                    │   (5-10 tests)  │
                    └────────┬────────┘
                             │
           ┌─────────────────┴─────────────────┐
           │          Unit Tests               │  ← API contracts, logic
           │         (20-30 tests)             │
           └───────────────────────────────────┘
```

### Test Files to Create

| File | Coverage |
|------|----------|
| `tests/units/test_order_guardian_emit.py` | P0-1 |
| `tests/units/test_aurora_handler_determinism.py` | P0-2 |
| `tests/units/test_aurora_position_sync.py` | P0-3 |
| `tests/units/test_aurora_warmup_ssot.py` | P1-1 |
| `tests/units/test_signal_ttl_validation.py` | P1-2 |
| `tests/integration/test_guardian_tidy_delivery.py` | P0-1 |
| `tests/integration/test_aurora_trade_sync.py` | P0-3 |
| `tests/backtest/test_replay_determinism.py` | P0-2 |

### CI Gate Requirements

```yaml
# .github/workflows/critical_fixes.yml

name: Critical Fixes Validation

on:
  pull_request:
    paths:
      - 'apps/reference/services/order_guardian.py'
      - 'apps/reference/domains/decision_making/aurora_handler.py'
      - 'apps/reference/domains/decision_making/decision_making.py'
      - 'apps/reference/domains/strategies/plugins/aurora_builtin.py'

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Run P0 Tests
        run: |
          pytest tests/units/test_order_guardian_emit.py -v --tb=short
          pytest tests/units/test_aurora_handler_determinism.py -v --tb=short
          pytest tests/units/test_aurora_position_sync.py -v --tb=short
      
      - name: Run Integration Tests
        run: |
          pytest tests/integration/test_guardian_tidy_delivery.py -v
          pytest tests/integration/test_aurora_fill_sync.py -v
      
      - name: Verify No Silent Fallbacks
        run: |
          # Grep for dangerous patterns
          ! grep -rn "except.*:.*pass" apps/reference/services/order_guardian.py || exit 1
          ! grep -rn "time\.monotonic" apps/reference/domains/decision_making/aurora_handler.py || exit 1
      
      - name: Backtest Determinism Check
        run: |
          python -m pytest tests/backtest/test_replay_determinism.py -v
```

---

## 6. Validation Checklist

### Pre-Merge Checklist

| ID | Check | Command/Method | Pass Criteria |
|----|-------|----------------|---------------|
| V1 | No silent exception swallowing near emit | `grep -rn "except.*:.*pass" order_guardian.py` | 0 matches |
| V2 | No `time.monotonic` in aurora_handler | `grep -rn "time\.monotonic" aurora_handler.py` | 0 matches |
| V3 | TRADE_EXECUTED listener registered | Integration test | Pass |
| V4 | Unit tests pass | `pytest tests/units/test_aurora*.py -v` | 100% pass |
| V5 | Integration tests pass | `pytest tests/integration/ -v` | 100% pass |
| V6 | Backtest determinism | Run 2x, compare trades | Identical |
| V7 | mypy type check | `mypy apps/reference/services/order_guardian.py` | No errors |
| V8 | Pydantic validation | All configs through typed models | No dict access |

### Post-Deploy Validation

| Check | Method | Alert Threshold |
|-------|--------|-----------------|
| EVT:SYMBOL_TIDY delivered | Log grep | > 0 per hour |
| Backtest reproducibility | Nightly CI | 100% identical |
| Holding period phantom blocks | Metric `aurora_holding_block_no_position` | 0 |
| Warmup state consistency | Log grep for "warmup_source" | Single source |

---

## 7. Rollout Plan

### Phase 1: P0 Fixes (Day 1-2)

```
Day 1:
├── Morning
│   ├── P0-1: Fix OrderGuardian emit API
│   ├── Write unit tests
│   └── Code review
│
├── Afternoon
│   ├── P0-2: Fix Aurora monotonic fallback
│   ├── Write determinism tests
│   └── Code review
│
Day 2:
├── Morning
│   ├── P0-3: Add Aurora fill listeners
│   ├── Remove speculative entry tracking
│   └── Write position sync tests
│
├── Afternoon
│   ├── Integration tests
│   ├── Backtest determinism validation
│   └── Merge to main
```

### Phase 2: P1 Fixes (Day 3-4)

```
Day 3:
├── P1-1: Warmup SSOT unification
├── P1-2: Signal TTL validation fix
└── Tests

Day 4:
├── Full test suite
├── Shadow mode deployment
└── Monitor for 24h
```

### Phase 3: Validation (Day 5)

```
Day 5:
├── Production deployment
├── Monitor dashboards
├── Confirm fixes via logs
└── Close tickets
```

---

## Appendix A: Config Contract Enforcement

### Required Pydantic Models

All fixes must use typed config access:

```python
# CORRECT:
from apps.reference.domain_config import DomainConfigResolver

resolver = DomainConfigResolver(self.config)
dm_cfg = resolver.get_decision_making()
qos_cfg = dm_cfg.qos
cooldown_sec = int(qos_cfg.symbol_cooldown_sec)  # Typed access

# FORBIDDEN:
cooldown_sec = config.get("qos", {}).get("symbol_cooldown_sec", 3)  # Dict access!
```

### No Hardcoded Parameters

| Parameter | Source | Never Hardcode |
|-----------|--------|----------------|
| Cooldown durations | `domains.decision_making.qos.*` | ❌ |
| TTL thresholds | `domains.decision_making.features.ttl_sec` | ❌ |
| Holding period | `strategies.aurora.decision.holding_period.*` | ❌ |
| Timeframe | `strategies.aurora.timeframe_sec` | ❌ |

---

## Appendix B: Silent Fallback Prohibition

### Forbidden Patterns

```python
# FORBIDDEN: Silent fallback
value = config.get("key") or DEFAULT_VALUE

# FORBIDDEN: Silent exception
try:
    ...
except Exception:
    pass

# FORBIDDEN: Direct time access
import time
now = time.time()
```

### Required Patterns

```python
# CORRECT: Explicit fallback with logging
value = config.get("key")
if value is None:
    LOG.warning(f"Config 'key' missing, using default {DEFAULT_VALUE}")
    value = DEFAULT_VALUE

# CORRECT: Logged exception
try:
    ...
except Exception as e:
    LOG.error(f"Operation failed: {e}")
    raise  # Or handle explicitly

# CORRECT: Clock abstraction
from apps.reference.core.time import get_clock
now = get_clock().now_sec()
```

---

**Document Version:** 1.0  
**Last Updated:** 2026-01-26  
**Next Review:** After Phase 1 completion
