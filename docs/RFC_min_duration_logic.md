# RFC: Minimum Holding Period Logic (Anti-Churn Gate)

**Author:** Senior Python Architect  
**Date:** 2025-01-07  
**Status:** Draft / Pending Review  
**Module:** `apps/reference/domains/decision_making/aurora_handler.py`  

---

## 1. Executive Summary

Aurora strategy страждає від "churn" — відкриття та закриття позицій протягом секунд через флуктуації alpha score навколо порогу. Цей RFC описує механізм **Minimum Holding Period** для запобігання передчасним виходам на основі сигналів, зберігаючи при цьому safety exits (Stop Loss, Risk Manager overrides).

### Ключові Вимоги

| Вимога | Опис |
|--------|------|
| **Anti-Churn** | Блокувати signal-based exits протягом `min_duration_sec` після entry |
| **Safety First** | НЕ блокувати SL/TP/Risk Manager exits |
| **Configurable** | Параметр `min_duration_sec` з `config/aurora/strategies.yaml` |
| **Per-Symbol** | Підтримка per-instrument override |
| **Stateful** | Трекінг `entry_timestamp` для кожного symbol |

---

## 2. Investigation Findings

### 2.1 Codebase Analysis: Signal Flow

```
EVT:FEATURES_CALCULATED
       │
       ▼
┌──────────────────────────────────────────┐
│ AuroraHandler.on_features_calculated()   │ ◄── aurora_handler.py:185
│   └── AuroraScoringKernel.compute()      │
│         ├── score >= thr_buy → "buy"     │
│         ├── score <= -thr_sell → "sell"  │
│         └── else → "" (neutral)          │
└──────────────────────────────────────────┘
       │
       ▼ (result.side != "")
┌──────────────────────────────────────────┐
│ AuroraHandler._emit_signal()             │ ◄── aurora_handler.py:464
│   └── emit_fn("EVT:STRATEGY_SIGNAL_PRODUCED", payload)
└──────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────┐
│ DecisionMaking._on_strategy_signal_gateway() │ ◄── decision_making.py:336
│   └── _handle_flip_orchestration()       │
│         ├── FLAT → allow OPEN            │
│         ├── same_side → BLOCK            │
│         └── opposite_side → FLIP (CLOSE + defer OPEN)
└──────────────────────────────────────────┘
```

### 2.2 Exit Signal Generation Points

**Критичне відкриття:** `AuroraScoringKernel.compute()` вже підтримує `current_side` параметр для hysteresis:

```python
# aurora_scoring_kernel.py:251-279
if current_side == "buy":
    # Currently LONG: check if we should hold or exit
    if signal_score <= -thr_sell:
        result.side = "sell"  # FLIP
        result.why_chain.append(f"flip:buy->sell:...")
    elif signal_score >= thr_neutral:
        result.side = "buy"   # HOLD
    else:
        result.side = ""       # EXIT ◄── ЦЕ І Є "SOFT EXIT"
```

**Інтеграційна точка:** EXIT (neutral) — це саме той момент, який треба заблокувати протягом `min_duration_sec`.

### 2.3 State Tracking Analysis

**Поточний стан `AuroraHandler`:**

```python
# aurora_handler.py:36-50
@dataclass
class SymbolState:
    regime: Optional[str] = None
    regime_confidence: float = 0.0
    regime_ts_ms: int = 0
    warmup_full_ready: bool = False
    warmup_ticks_seen: int = 0
    buy_timestamps: List[float] = field(default_factory=list)  # side bias history
    sell_timestamps: List[float] = field(default_factory=list)
    last_signal_ts_ms: int = 0
    last_signal_side: str = ""  # ◄── НАЯВНЕ! Можна використати для current_side
```

**Гіпотеза підтверджена:** Handler вже відстежує `last_signal_side`, але **НЕ відстежує `entry_timestamp`** для position.

### 2.4 Config Injection Path

**Existing config structure** (config/aurora/strategies.yaml):

```yaml
# strategies.yaml — decision section (global)
decision:
  signal_threshold: 0.12
  side_bias_window_sec: 420
  # ... other params
```

**Per-symbol override** (strategies.aurora.assets):

```yaml
assets:
  ETHUSDT:
    enabled: true
    weights: {...}
    # ◄── HERE: можна додати min_duration_sec
```

---

## 3. Logic Flow Design

### 3.1 High-Level Flow

```
                         ┌─────────────────────────────────────────────┐
                         │  EVT:POSITION_OPENED received              │
                         │  → Store entry_timestamp[symbol] = now()   │
                         └───────────────────┬─────────────────────────┘
                                             │
                                             ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                         AuroraHandler.on_features_calculated()           │
│                                                                          │
│   1. Get ScoringResult from kernel                                       │
│   2. IF result.side == "" (NEUTRAL/EXIT):                               │
│        └── Check: (now - entry_timestamp[symbol]) < min_duration_sec?   │
│              ├── YES → SUPPRESS exit signal (stay in position)          │
│              │         Log: "HOLDING_PERIOD_ACTIVE: blocking soft exit" │
│              └── NO  → Allow exit signal to flow                        │
│   3. IF result.side == opposite_side (FLIP):                            │
│        └── Check: is_emergency_override(score)?                         │
│              ├── YES → Allow FLIP (safety override)                      │
│              └── NO  → Apply min_duration check                          │
│   4. Emit signal if allowed                                              │
└──────────────────────────────────────────────────────────────────────────┘
```

### 3.2 Pseudo-code

```python
def _should_suppress_exit(self, symbol: str, result: ScoringResult) -> bool:
    """
    Check if exit signal should be suppressed due to minimum holding period.
    
    Returns True if:
    1. We are in an active position (entry_timestamp exists)
    2. Holding period has not elapsed
    3. This is NOT an emergency override
    """
    # 1. Check if we have entry timestamp
    entry_ts = self._entry_timestamps.get(symbol)
    if entry_ts is None:
        return False  # No position tracked, allow signal
    
    # 2. Check if holding period elapsed
    now = time.time()
    min_duration = self._get_min_duration_sec(symbol)
    time_in_position = now - entry_ts
    
    if time_in_position >= min_duration:
        return False  # Holding period elapsed, allow exit
    
    # 3. Check for emergency override
    if self._is_emergency_score(result.score, symbol):
        self.logger.warning(
            f"[{symbol}] EMERGENCY_OVERRIDE: Allowing exit despite holding period "
            f"(score={result.score:.4f}, time_in_position={time_in_position:.1f}s)"
        )
        return False  # Emergency exit allowed
    
    # 4. Suppress the exit
    self.logger.info(
        f"[{symbol}] HOLDING_PERIOD_ACTIVE: Suppressing soft exit "
        f"(time_in_position={time_in_position:.1f}s < min_duration={min_duration}s)"
    )
    return True
```

### 3.3 Emergency Override Logic

**Критичний edge case:** Що робити, якщо score падає до -0.9 (катастрофічний рівень)?

**Рішення:** Ввести `emergency_exit_threshold` — якщо |score| > threshold, дозволити вихід навіть у межах holding period.

```python
def _is_emergency_score(self, score: Decimal, symbol: str) -> bool:
    """
    Check if score indicates emergency conditions requiring immediate exit.
    
    Emergency conditions:
    1. Score drops below -emergency_exit_threshold (for LONG position)
    2. Score rises above +emergency_exit_threshold (for SHORT position)
    """
    emergency_threshold = self._get_emergency_exit_threshold(symbol)
    return abs(float(score)) >= emergency_threshold
```

**Рекомендовані значення:**

| Параметр | Default | Опис |
|----------|---------|------|
| `min_duration_sec` | 30 | Мінімальний час утримання позиції |
| `emergency_exit_threshold` | 0.7 | Score threshold для emergency override |

---

## 4. State Management Design

### 4.1 Entry Timestamp Tracking

**Проблема:** AuroraHandler не отримує `EVT:POSITION_OPENED` напряму — він лише emit'ує signals.

**Рішення A: Listener Pattern** (Рекомендовано)

```python
class AuroraHandler:
    def __init__(self, ...):
        # ...existing code...
        self._entry_timestamps: Dict[str, float] = {}
        
        # Subscribe to position events
        self.emit_fn.listen("EVT:POSITION_OPENED", self._on_position_opened)
        self.emit_fn.listen("EVT:POSITION_CLOSED", self._on_position_closed)
    
    def _on_position_opened(self, event: Dict[str, Any]) -> None:
        """Track entry timestamp when position opens."""
        symbol = event.get("symbol")
        if not symbol:
            return
        self._entry_timestamps[symbol] = time.time()
        self.logger.info(f"[{symbol}] Position opened, tracking entry time")
    
    def _on_position_closed(self, event: Dict[str, Any]) -> None:
        """Clear entry timestamp when position closes."""
        symbol = event.get("symbol")
        if symbol and symbol in self._entry_timestamps:
            del self._entry_timestamps[symbol]
```

**Рішення B: Signal-Based Tracking** (Альтернатива)

Якщо `EVT:POSITION_OPENED` недоступний у Handler scope, використовувати момент emit'у BUY/SELL сигналу як proxy для entry time:

```python
def _emit_signal(self, symbol: str, result: ScoringResult, ...):
    # ...existing code...
    
    # Track entry timestamp when emitting entry signal (not exit)
    state = self._symbol_states[symbol]
    if result.side and result.side != state.last_signal_side:
        # Side changed → new entry
        self._entry_timestamps[symbol] = time.time()
```

### 4.2 Restart/Crash Recovery

**Проблема:** При restart entry timestamps втрачаються.

**Рішення:** Fail-safe behavior

```python
def _should_suppress_exit(self, symbol: str, ...) -> bool:
    entry_ts = self._entry_timestamps.get(symbol)
    if entry_ts is None:
        # FAIL-OPEN: Unknown position state → allow exit
        # Rationale: краще закрити позицію, ніж тримати unknown position
        return False
```

### 4.3 Concurrency Considerations

AuroraHandler працює в single-threaded event loop, тому Dict[str, float] є thread-safe для цього use case. Якщо в майбутньому буде multiprocessing, потрібно буде використати `threading.Lock` або Redis-based shared state.

---

## 5. Configuration Schema

### 5.1 YAML Configuration

**File:** `config/aurora/strategies.yaml`

```yaml
aurora:
  decision:
    # ... existing fields ...
    
    # === NEW: Minimum Holding Period (Anti-Churn) ===
    holding_period:
      enabled: true
      min_duration_sec: 30          # Minimum seconds to hold position
      emergency_exit_threshold: 0.7  # Score threshold for emergency override
      apply_to_flips: true          # Also apply to FLIP signals (not just exits)
    
  assets:
    ETHUSDT:
      enabled: true
      # Per-symbol override
      holding_period:
        min_duration_sec: 45        # ETH: longer holding period
        emergency_exit_threshold: 0.6
    
    BTCUSDT:
      enabled: true
      holding_period:
        min_duration_sec: 20        # BTC: shorter (more liquid)
```

### 5.2 Config Loading

```python
def _load_config(self) -> None:
    """Extract configuration parameters."""
    # ... existing code ...
    
    # Holding Period Config
    hp_cfg = getattr(decision, "holding_period", None)
    if hp_cfg:
        self.holding_period_enabled = bool(getattr(hp_cfg, "enabled", True))
        self.default_min_duration_sec = float(getattr(hp_cfg, "min_duration_sec", 30))
        self.default_emergency_threshold = float(getattr(hp_cfg, "emergency_exit_threshold", 0.7))
        self.holding_apply_to_flips = bool(getattr(hp_cfg, "apply_to_flips", True))
    else:
        self.holding_period_enabled = False
        self.default_min_duration_sec = 30.0
        self.default_emergency_threshold = 0.7
        self.holding_apply_to_flips = True

def _get_min_duration_sec(self, symbol: str) -> float:
    """Get min_duration_sec with per-symbol override."""
    instr_cfg = self._get_instrument_config(symbol)
    if instr_cfg:
        hp = getattr(instr_cfg, "holding_period", None)
        if hp and hasattr(hp, "min_duration_sec"):
            return float(hp.min_duration_sec)
    return self.default_min_duration_sec

def _get_emergency_threshold(self, symbol: str) -> float:
    """Get emergency_exit_threshold with per-symbol override."""
    instr_cfg = self._get_instrument_config(symbol)
    if instr_cfg:
        hp = getattr(instr_cfg, "holding_period", None)
        if hp and hasattr(hp, "emergency_exit_threshold"):
            return float(hp.emergency_exit_threshold)
    return self.default_emergency_threshold
```

---

## 6. Draft Code Patch

### 6.1 SymbolState Extension

**File:** `aurora_handler.py` (lines 36-50)

```python
@dataclass
class SymbolState:
    """Per-symbol state for Aurora handler."""
    
    # ... existing fields ...
    
    # === NEW: Holding Period State ===
    entry_timestamp: Optional[float] = None  # Time when position was opened
    position_side: str = ""                   # Current position side ("buy"/"sell")
```

### 6.2 Config Loading Extension

**File:** `aurora_handler.py` (method `_load_config`)

```python
def _load_config(self) -> None:
    """Extract configuration parameters."""
    # ... existing code up to self.delta_price_cap_pct ...
    
    # === NEW: Holding Period Config ===
    hp_cfg = getattr(decision, "holding_period", None) if decision else None
    if hp_cfg and getattr(hp_cfg, "enabled", False):
        self.holding_period_enabled = True
        self.default_min_duration_sec = float(getattr(hp_cfg, "min_duration_sec", 30))
        self.default_emergency_threshold = float(getattr(hp_cfg, "emergency_exit_threshold", 0.7))
        self.holding_apply_to_flips = bool(getattr(hp_cfg, "apply_to_flips", True))
        self.logger.info(
            f"Holding period enabled: min_duration={self.default_min_duration_sec}s, "
            f"emergency_threshold={self.default_emergency_threshold}"
        )
    else:
        self.holding_period_enabled = False
        self.default_min_duration_sec = 30.0
        self.default_emergency_threshold = 0.7
        self.holding_apply_to_flips = True
```

### 6.3 Helper Methods

**File:** `aurora_handler.py` (new methods)

```python
def _get_min_duration_sec(self, symbol: str) -> float:
    """
    Get min_duration_sec with per-symbol override.
    
    Fallback chain:
    1. strategies.aurora.assets.<SYMBOL>.holding_period.min_duration_sec
    2. strategies.aurora.decision.holding_period.min_duration_sec
    3. self.default_min_duration_sec (30s)
    """
    instr_cfg = self._get_instrument_config(symbol)
    if instr_cfg:
        hp = getattr(instr_cfg, "holding_period", None)
        if hp and hasattr(hp, "min_duration_sec"):
            val = getattr(hp, "min_duration_sec", None)
            if val is not None:
                return float(val)
    return self.default_min_duration_sec

def _get_emergency_threshold(self, symbol: str) -> float:
    """
    Get emergency_exit_threshold with per-symbol override.
    
    Fallback chain:
    1. strategies.aurora.assets.<SYMBOL>.holding_period.emergency_exit_threshold
    2. strategies.aurora.decision.holding_period.emergency_exit_threshold
    3. self.default_emergency_threshold (0.7)
    """
    instr_cfg = self._get_instrument_config(symbol)
    if instr_cfg:
        hp = getattr(instr_cfg, "holding_period", None)
        if hp and hasattr(hp, "emergency_exit_threshold"):
            val = getattr(hp, "emergency_exit_threshold", None)
            if val is not None:
                return float(val)
    return self.default_emergency_threshold

def _is_emergency_exit(self, score: decimal.Decimal, symbol: str) -> bool:
    """
    Check if score indicates emergency conditions.
    
    Returns True if |score| >= emergency_threshold, allowing exit
    even within holding period.
    """
    threshold = self._get_emergency_threshold(symbol)
    return abs(float(score)) >= threshold

def _should_suppress_soft_exit(
    self,
    symbol: str,
    result: ScoringResult,
    is_flip: bool = False,
) -> bool:
    """
    Check if exit/flip signal should be suppressed due to minimum holding period.
    
    Returns True (suppress) if:
    1. Holding period feature is enabled
    2. We have an active entry timestamp
    3. Time in position < min_duration_sec
    4. This is NOT an emergency exit
    5. (for flips) holding_apply_to_flips is True
    
    Returns False (allow) otherwise.
    """
    # 0. Feature disabled?
    if not self.holding_period_enabled:
        return False
    
    # 1. Skip if this is a flip and we don't apply to flips
    if is_flip and not self.holding_apply_to_flips:
        return False
    
    # 2. Get state
    state = self._symbol_states[symbol]
    entry_ts = state.entry_timestamp
    
    if entry_ts is None:
        # No tracked entry → fail-open (allow exit)
        return False
    
    # 3. Check holding period
    now = time.time()
    min_duration = self._get_min_duration_sec(symbol)
    time_in_position = now - entry_ts
    
    if time_in_position >= min_duration:
        # Holding period elapsed → allow exit
        return False
    
    # 4. Check emergency override
    if self._is_emergency_exit(result.score, symbol):
        self.logger.warning(
            f"[{symbol}] EMERGENCY_OVERRIDE: Allowing exit despite holding period "
            f"(score={float(result.score):.4f}, time_in_position={time_in_position:.1f}s, "
            f"threshold={self._get_emergency_threshold(symbol)})"
        )
        return False
    
    # 5. Suppress the exit
    self.logger.info(
        f"[{symbol}] HOLDING_PERIOD_ACTIVE: Suppressing soft {'flip' if is_flip else 'exit'} "
        f"(time_in_position={time_in_position:.1f}s < min_duration={min_duration}s, "
        f"score={float(result.score):.4f})"
    )
    
    # Emit blocked event for observability
    self._emit_strategy_blocked(
        symbol=symbol,
        reason_code="HOLDING_PERIOD_ACTIVE",
        reason="HOLDING_PERIOD",
        context="aurora_handler:holding_period_check",
        details={
            "time_in_position_sec": round(time_in_position, 2),
            "min_duration_sec": min_duration,
            "score": float(result.score),
            "signal_type": "flip" if is_flip else "exit",
        },
        why_chain=["HOLDING_PERIOD", f"time:{time_in_position:.1f}s", f"min:{min_duration}s"],
    )
    
    return True

def _track_entry(self, symbol: str, side: str) -> None:
    """Track entry timestamp when position opens."""
    state = self._symbol_states[symbol]
    state.entry_timestamp = time.time()
    state.position_side = side.lower()
    self.logger.debug(f"[{symbol}] Entry tracked: side={side}, ts={state.entry_timestamp}")

def _clear_entry(self, symbol: str) -> None:
    """Clear entry tracking when position closes."""
    state = self._symbol_states[symbol]
    state.entry_timestamp = None
    state.position_side = ""
    self.logger.debug(f"[{symbol}] Entry tracking cleared")
```

### 6.4 Integration into `on_features_calculated`

**File:** `aurora_handler.py` (method `on_features_calculated`, after kernel.compute())

```python
# ... existing code: result = AuroraScoringKernel.compute(...) ...

if result.deferred:
    # ... existing defer handling ...
    return

if not result.side:
    self.logger.debug(f"[{symbol}] Neutral signal (score={float(result.score):.4f})")
    return

# === NEW: Check Holding Period for EXIT signals ===
state = self._symbol_states[symbol]
current_position_side = state.position_side

# Determine if this is an exit or flip
is_exit = (
    current_position_side != "" 
    and result.side == ""
)
is_flip = (
    current_position_side != "" 
    and result.side != "" 
    and result.side.lower() != current_position_side
)

if is_exit or is_flip:
    if self._should_suppress_soft_exit(symbol, result, is_flip=is_flip):
        # Exit suppressed, do not emit signal
        return

# ... existing ANCHOR SHOCK VETO code ...

# Emit signal
self._emit_signal(symbol, result, features, event)

# === NEW: Track entry on side change ===
if result.side and result.side.lower() != current_position_side:
    # New entry or flip → track entry time
    self._track_entry(symbol, result.side)

# Update side bias history
self._update_side_bias(symbol, result.side)
```

### 6.5 Position Event Listeners (Alternative: If FSM events available)

**File:** `aurora_handler.py` (in `__init__` if emit_fn supports .listen)

```python
def __init__(self, *, config, emit_fn, strategy_id="aurora"):
    # ... existing init ...
    
    # Optional: Listen to position events for accurate entry tracking
    # (uncomment if FSM events are available to handler)
    # if hasattr(emit_fn, "listen"):
    #     emit_fn.listen("EVT:POSITION_OPENED", self._on_position_opened)
    #     emit_fn.listen("EVT:POSITION_CLOSED", self._on_position_closed)

def _on_position_opened(self, event: Dict[str, Any]) -> None:
    """Handle EVT:POSITION_OPENED for accurate entry tracking."""
    symbol = event.get("symbol")
    side = event.get("side", "")
    if symbol and self._is_symbol_enabled(symbol):
        self._track_entry(symbol, side)

def _on_position_closed(self, event: Dict[str, Any]) -> None:
    """Handle EVT:POSITION_CLOSED to clear entry tracking."""
    symbol = event.get("symbol")
    if symbol:
        self._clear_entry(symbol)
```

---

## 7. Test Plan

### 7.1 Unit Tests

**File:** `tests/domains/decision_making/test_aurora_holding_period.py`

```python
"""
Unit tests for Aurora Minimum Holding Period logic.

Tests:
1. Exit blocked within holding period
2. Exit allowed after holding period
3. Emergency override within holding period
4. Flip blocked within holding period
5. Flip allowed after holding period
6. Per-symbol config override
7. Feature disabled behavior
"""
import decimal
import time
from unittest.mock import MagicMock, patch

import pytest

from apps.reference.domains.decision_making.aurora_handler import AuroraHandler, SymbolState
from apps.reference.domains.decision_making.aurora_scoring_kernel import ScoringResult


@pytest.fixture
def mock_config():
    """Create mock config with holding period enabled."""
    config = MagicMock()
    config.strategies.aurora.decision.holding_period.enabled = True
    config.strategies.aurora.decision.holding_period.min_duration_sec = 30
    config.strategies.aurora.decision.holding_period.emergency_exit_threshold = 0.7
    config.strategies.aurora.decision.holding_period.apply_to_flips = True
    # ... other required config fields ...
    return config


class TestHoldingPeriodBlocking:
    """Test exit blocking within holding period."""
    
    def test_exit_blocked_at_t_plus_10s(self, mock_config):
        """
        Test that soft exit is blocked at T+10s (within 30s holding period).
        
        Scenario:
        - Entry at T=0
        - Exit signal at T=10s
        - Expected: BLOCKED (time_in_position=10s < min_duration=30s)
        """
        handler = AuroraHandler(config=mock_config, emit_fn=MagicMock())
        
        # Simulate entry
        handler._track_entry("ETHUSDT", "buy")
        
        # Advance time by 10 seconds
        with patch("time.time") as mock_time:
            entry_ts = handler._symbol_states["ETHUSDT"].entry_timestamp
            mock_time.return_value = entry_ts + 10  # T+10s
            
            result = ScoringResult(
                score=decimal.Decimal("0.05"),  # Below threshold → exit
                side="",
                thr_buy=decimal.Decimal("0.1"),
                thr_sell=decimal.Decimal("0.1"),
            )
            
            should_suppress = handler._should_suppress_soft_exit("ETHUSDT", result)
            
            assert should_suppress is True
    
    def test_exit_allowed_at_t_plus_31s(self, mock_config):
        """
        Test that soft exit is allowed at T+31s (after 30s holding period).
        
        Scenario:
        - Entry at T=0
        - Exit signal at T=31s
        - Expected: ALLOWED (time_in_position=31s >= min_duration=30s)
        """
        handler = AuroraHandler(config=mock_config, emit_fn=MagicMock())
        
        handler._track_entry("ETHUSDT", "buy")
        
        with patch("time.time") as mock_time:
            entry_ts = handler._symbol_states["ETHUSDT"].entry_timestamp
            mock_time.return_value = entry_ts + 31  # T+31s
            
            result = ScoringResult(
                score=decimal.Decimal("0.05"),
                side="",
                thr_buy=decimal.Decimal("0.1"),
                thr_sell=decimal.Decimal("0.1"),
            )
            
            should_suppress = handler._should_suppress_soft_exit("ETHUSDT", result)
            
            assert should_suppress is False
    
    def test_emergency_override_at_t_plus_5s(self, mock_config):
        """
        Test that emergency exit is allowed even at T+5s.
        
        Scenario:
        - Entry at T=0
        - Score drops to -0.85 (< -0.7 emergency threshold)
        - Exit signal at T=5s
        - Expected: ALLOWED (emergency override)
        """
        handler = AuroraHandler(config=mock_config, emit_fn=MagicMock())
        
        handler._track_entry("ETHUSDT", "buy")
        
        with patch("time.time") as mock_time:
            entry_ts = handler._symbol_states["ETHUSDT"].entry_timestamp
            mock_time.return_value = entry_ts + 5  # T+5s
            
            result = ScoringResult(
                score=decimal.Decimal("-0.85"),  # Emergency level!
                side="",
                thr_buy=decimal.Decimal("0.1"),
                thr_sell=decimal.Decimal("0.1"),
            )
            
            should_suppress = handler._should_suppress_soft_exit("ETHUSDT", result)
            
            assert should_suppress is False  # Emergency override


class TestFlipBehavior:
    """Test flip signal handling with holding period."""
    
    def test_flip_blocked_within_holding_period(self, mock_config):
        """
        Test that flip (buy→sell) is blocked within holding period.
        """
        handler = AuroraHandler(config=mock_config, emit_fn=MagicMock())
        
        handler._track_entry("BTCUSDT", "buy")
        
        with patch("time.time") as mock_time:
            entry_ts = handler._symbol_states["BTCUSDT"].entry_timestamp
            mock_time.return_value = entry_ts + 15  # T+15s
            
            result = ScoringResult(
                score=decimal.Decimal("-0.15"),  # Flip signal
                side="sell",
                thr_buy=decimal.Decimal("0.1"),
                thr_sell=decimal.Decimal("0.1"),
            )
            
            should_suppress = handler._should_suppress_soft_exit(
                "BTCUSDT", result, is_flip=True
            )
            
            assert should_suppress is True


class TestConfigOverride:
    """Test per-symbol configuration override."""
    
    def test_per_symbol_min_duration(self, mock_config):
        """
        Test that per-symbol min_duration_sec overrides global.
        
        Config:
        - Global: min_duration_sec = 30
        - ETHUSDT: min_duration_sec = 45
        
        At T+35s: global would allow, per-symbol should block.
        """
        # Setup per-symbol override
        mock_config.strategies.aurora.assets = {
            "ETHUSDT": MagicMock(
                holding_period=MagicMock(min_duration_sec=45)
            )
        }
        
        handler = AuroraHandler(config=mock_config, emit_fn=MagicMock())
        
        handler._track_entry("ETHUSDT", "buy")
        
        with patch("time.time") as mock_time:
            entry_ts = handler._symbol_states["ETHUSDT"].entry_timestamp
            mock_time.return_value = entry_ts + 35  # T+35s
            
            result = ScoringResult(
                score=decimal.Decimal("0.05"),
                side="",
                thr_buy=decimal.Decimal("0.1"),
                thr_sell=decimal.Decimal("0.1"),
            )
            
            should_suppress = handler._should_suppress_soft_exit("ETHUSDT", result)
            
            # Per-symbol: 45s, time_in_position: 35s → should block
            assert should_suppress is True


class TestFeatureDisabled:
    """Test behavior when holding period feature is disabled."""
    
    def test_exit_allowed_when_disabled(self):
        """Exit always allowed when holding_period.enabled = false."""
        config = MagicMock()
        config.strategies.aurora.decision.holding_period.enabled = False
        
        handler = AuroraHandler(config=config, emit_fn=MagicMock())
        
        handler._track_entry("ETHUSDT", "buy")
        
        result = ScoringResult(
            score=decimal.Decimal("0.05"),
            side="",
            thr_buy=decimal.Decimal("0.1"),
            thr_sell=decimal.Decimal("0.1"),
        )
        
        # Feature disabled → never suppress
        should_suppress = handler._should_suppress_soft_exit("ETHUSDT", result)
        
        assert should_suppress is False
```

### 7.2 Integration Tests

```python
"""
Integration tests for Minimum Holding Period in full signal flow.
"""

class TestHoldingPeriodIntegration:
    """Full integration tests with FSM events."""
    
    def test_full_flow_entry_then_early_exit_blocked(self, aurora_test_system):
        """
        Full flow test:
        1. Emit features → BUY signal
        2. Emit features (at T+10s) → neutral → should be BLOCKED
        3. Verify no EVT:STRATEGY_SIGNAL_PRODUCED for exit
        """
        pass  # Implementation depends on test harness
    
    def test_full_flow_stop_loss_not_blocked(self, aurora_test_system):
        """
        Verify that SL/TP from Risk Manager are NOT blocked.
        
        The holding period only affects signals from AuroraHandler.
        CMD:CLOSE from Risk Manager should always pass.
        """
        pass  # Implementation depends on test harness
```

---

## 8. Migration & Rollout Plan

### Phase 1: Shadow Mode (1-2 days)

1. Deploy with `holding_period.enabled: false`
2. Add logging for "would-block" events
3. Analyze logs to estimate churn reduction

### Phase 2: Conservative Rollout (3-5 days)

1. Enable for one low-volume symbol (e.g., DOGEUSDT)
2. Set conservative values:
   - `min_duration_sec: 15`
   - `emergency_exit_threshold: 0.5`
3. Monitor P&L and churn metrics

### Phase 3: Full Rollout

1. Enable for all symbols with tuned values
2. Per-symbol tuning based on volatility:
   - BTC/ETH: `min_duration_sec: 30`
   - ALTs: `min_duration_sec: 45`

---

## 9. Observability & Metrics

### 9.1 New Metrics

| Metric | Type | Description |
|--------|------|-------------|
| `aurora_holding_period_blocks_total` | Counter | Total exits blocked by holding period |
| `aurora_holding_period_emergency_overrides_total` | Counter | Emergency overrides triggered |
| `aurora_time_in_position_seconds` | Histogram | Time in position when exit attempted |

### 9.2 Log Patterns

```
INFO  [ETHUSDT] HOLDING_PERIOD_ACTIVE: Suppressing soft exit (time_in_position=12.3s < min_duration=30s, score=0.0523)
WARN  [ETHUSDT] EMERGENCY_OVERRIDE: Allowing exit despite holding period (score=-0.8234, time_in_position=8.1s, threshold=0.7)
```

---

## 10. Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Holding losing position too long | Medium | Medium | Emergency override + low threshold |
| Missing profitable exits | Medium | Low | Tune min_duration based on volatility |
| State corruption on restart | Low | Medium | Fail-open behavior (allow exit if unknown) |
| Config typo disables safety | Low | High | Config validation + alerts |

---

## 11. Decision Points for Review

1. **Entry Tracking Method:** Listener pattern vs Signal-based tracking?
2. **Emergency Threshold:** 0.7 достатньо консервативний?
3. **Flip Handling:** Чи застосовувати holding period до FLIPs?
4. **Per-Symbol Tuning:** Які symbols потребують custom values?

---

## 12. Appendix: Files to Modify

| File | Changes |
|------|---------|
| `aurora_handler.py` | +120 LOC (state, helpers, integration) |
| `config/aurora/strategies.yaml` | +10 LOC (new config section) |
| `tests/domains/decision_making/test_aurora_holding_period.py` | +200 LOC (new test file) |

---

**End of RFC**
