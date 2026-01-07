# Forensic Audit: Timers and Timeframes

**Auditor:** AI Systems Architect  
**Date:** 2026-01-07  
**Status:** 🚨 CRITICAL ISSUES FOUND

---

## SECTION A: TIMER DIAGNOSIS

### A.1: Holding Period (Exit Gate)

**Status:** ⚠️ PARTIALLY WORKING

**Evidence:**

Config is loaded in `aurora_handler.py` lines 134-149:
```python
hp_cfg = getattr(decision, "holding_period", None)
if hp_cfg and getattr(hp_cfg, "enabled", False):
    self.holding_period_enabled = True
    self.default_min_duration_sec = float(getattr(hp_cfg, "min_duration_sec", 30))
    ...
```

Logic exists in lines 378-394:
```python
# === [HOLDING PERIOD CHECK: ANTI-CHURN GATE] ===
if current_position_side and is_flip:
    if self._should_suppress_soft_exit(symbol, result, is_flip=True):
        return  # Flip suppressed
```

**🐛 BUG FOUND:** The check is ONLY applied to **flips** (`is_flip=True`).
- Normal exits (signal goes neutral) are NOT blocked by holding period!
- Line 390: `if current_position_side and is_flip:`

**Impact:** Holding period only prevents flips, NOT regular soft exits.

---

### A.2: Re-entry Cooldown (Entry Gate)

**Status:** ❌ **BROKEN / NOT IMPLEMENTED**

**Evidence:**

1. **AuroraHandler has NO re-entry cooldown logic:**
   - No `last_exit_timestamp` field in `SymbolState`
   - No check: `if (now - last_exit) < cooldown: BLOCK_ENTRY`
   - Searched for: `last_exit`, `exit_time`, `re_entry`, `reentry` → **No results**

2. **Execution FSM has cooldown_after_close (line 1148-1161 in fsm.py):**
   ```python
   if last_close > 0 and self._cooldown_after_close_sec > 0 and (now - last_close) < self._cooldown_after_close_sec:
       return Message(op="ERR", verb="OPEN", ..., pld={"reason": "cooldown_after_close active"})
   ```
   
   **But it NEVER triggers because:**
   - `_last_any_position_closed_ts` is set ONLY when position changes are detected via polling (line 766-769)
   - Log shows `[POSITION_CLOSED]` message is **never emitted**
   - The polling-based detection is failing silently

3. **Config exists but is dead:**
   ```yaml
   # trading.yaml line 112
   cooldown_after_close_ms: 60000  # 60 seconds
   ```

**Impact:** System immediately re-enters after position closes. "Ping-Pong" behavior observed.

---

## SECTION B: TIMEFRAME REALITY

### B.1: Aurora Strategy Timeframe

**Status:** ❌ **Acting on TICKS, not 5-minute bars**

**Evidence:**

1. **Config shows `timeframe_sec: null` for all Aurora symbols:**
   ```yaml
   # aurora.yaml lines 211, 271, 336, 400, 465
   timeframe_sec: null
   ```

2. **AuroraHandler.on_features_calculated processes EVERY EVT:FEATURES_CALCULATED event:**
   - No bar aggregation
   - No timeframe gating
   - Features are calculated on tick aggregator intervals (~5 seconds)

3. **FeatureEngineering sends events at tick rate:**
   - Log shows signals every 5 seconds (not 5 minutes)
   - Example: `17:56:57,927 → 17:57:02,919 → 17:57:07,927` (5-second intervals)

**Impact:** Aurora behaves like a **5-second scalper**, not a 5-minute strategy.

---

### B.2: Mean Reversion Strategy Timeframe

**Status:** ✅ **Correctly configured for 3-minute bars**

**Evidence:**

1. **Config (mean_reversion.yaml line 20):**
   ```yaml
   timeframe_sec: 180  # 3-minute bars
   ```

2. **Handler reads config (mean_reversion_handler.py line 283-285):**
   ```python
   timeframe_sec = self._mr_config.timeframe_sec
   if timeframe_sec <= 0:
       raise ValueError(...)
   ```

3. **Strategy is initialized with timeframe (line 346-348):**
   ```python
   self._strategies[symbol] = MeanReversion1mStrategy(
       config=config,
       timeframe_sec=timeframe_sec,  # ✅ Passed correctly
       ...
   )
   ```

**Note:** Despite the class name `MeanReversion1mStrategy`, the timeframe is configurable. The "1m" in the name is a misnomer from original design.

---

## SECTION C: REMEDIATION PLAN

### C.1: Fix Re-entry Cooldown (Anti-Ping-Pong)

**Location:** `aurora_handler.py`

**Step 1: Add last_exit_timestamp to SymbolState**
```python
@dataclass
class SymbolState:
    ...
    # Re-entry cooldown (Anti-Ping-Pong)
    last_exit_timestamp: Optional[float] = None
```

**Step 2: Track exit in on_features_calculated (after neutral signal)**

After line 376 (`return` for neutral signal):
```python
if not result.side:
    # Track exit timestamp for re-entry cooldown
    if state.position_side:  # Was in position
        state.last_exit_timestamp = time.time()
        state.position_side = ""
        self._clear_entry(symbol)
    self.logger.debug(f"[{symbol}] Neutral signal (score={float(result.score):.4f})")
    return
```

**Step 3: Add re-entry block in on_features_calculated (before signal emit)**

Before line 428 (`self._emit_signal`):
```python
# === [RE-ENTRY COOLDOWN: ANTI-PING-PONG GATE] ===
if state.last_exit_timestamp and state.position_side == "":
    reentry_cooldown = self._get_reentry_cooldown_sec(symbol)  # Default 30s
    time_since_exit = time.time() - state.last_exit_timestamp
    if time_since_exit < reentry_cooldown:
        self.logger.info(
            f"[{symbol}] REENTRY_COOLDOWN: Blocking entry {time_since_exit:.1f}s < {reentry_cooldown}s"
        )
        self._emit_strategy_blocked(
            symbol=symbol,
            reason_code="REENTRY_COOLDOWN",
            reason="COOLDOWN",
            context="aurora_handler:reentry_cooldown",
            details={"time_since_exit": time_since_exit, "cooldown": reentry_cooldown},
            why_chain=["REENTRY_COOLDOWN", f"wait:{reentry_cooldown - time_since_exit:.1f}s"],
        )
        return
# === END RE-ENTRY COOLDOWN ===
```

**Step 4: Add config support for `reentry_cooldown_sec`**

In `aurora.yaml` under `decision`:
```yaml
decision:
  reentry_cooldown_sec: 30  # Default global
  ...
```

Per-symbol override:
```yaml
assets:
  BTCUSDT:
    reentry_cooldown_sec: 20  # Faster for BTC
```

---

### C.2: Fix Aurora Timeframe (Force 5-minute bars)

**Option A: Add bar gating in FeatureEngineering (Recommended)**

1. Aggregate features into 5-minute windows
2. Only emit EVT:FEATURES_CALCULATED on bar close
3. This requires changes in `feature_engineering.py`

**Option B: Add signal rate limiting in AuroraHandler (Quick fix)**

Add to `on_features_calculated` after getting state:
```python
# Rate limit to ~5 minute bars
MIN_SIGNAL_INTERVAL_SEC = 300  # 5 minutes
if state.last_signal_ts_ms > 0:
    elapsed_ms = event.get("ts", 0) - state.last_signal_ts_ms
    if elapsed_ms < MIN_SIGNAL_INTERVAL_SEC * 1000:
        return  # Skip until next bar window
```

**Recommendation:** Option A is cleaner but requires more work. Option B is a quick patch.

---

### C.3: Fix Holding Period for ALL Exits

**Location:** `aurora_handler.py` lines 389-393

**Current (buggy):**
```python
if current_position_side and is_flip:
    if self._should_suppress_soft_exit(symbol, result, is_flip=True):
        return
```

**Fixed:**
```python
# Check holding period for BOTH exits and flips
if current_position_side:  # We have a position
    is_exit = result.side == ""
    is_flip = result.side.lower() != current_position_side and result.side != ""
    
    if (is_exit or is_flip):
        if self._should_suppress_soft_exit(symbol, result, is_flip=is_flip):
            return
```

---

## SUMMARY

| Issue | Status | Fix Complexity |
|-------|--------|----------------|
| Holding Period (exits) | ⚠️ Partial | 🟡 Medium (add exit check) |
| Re-entry Cooldown | ❌ Missing | 🔴 High (new feature) |
| Aurora Timeframe | ❌ Wrong (tick-based) | 🔴 High (architecture change) |
| MR Timeframe | ✅ Correct (3m bars) | - |

**Priority Order:**
1. 🔴 Fix Re-entry Cooldown (most impactful for churn)
2. 🟡 Fix Holding Period for all exits
3. 🔴 Fix Aurora Timeframe (requires FeatureEngineering changes)
