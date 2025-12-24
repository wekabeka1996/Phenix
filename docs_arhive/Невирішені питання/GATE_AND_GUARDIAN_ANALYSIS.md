# GATE and Guardian: Analysis and Open Questions

## Overview

The system has **two mechanisms** for handling orphan orders (brackets without positions):

1. **OrderGuardian** — Active cleanup (cancels orphan orders)
2. **GATE** — Passive protection (blocks new ENTRY until symbol is "tidy")

This document describes the functionality, logic, modules, and known issues.

---

## 1. OrderGuardian

### Purpose
Actively monitors and cancels "orphan" orders — bracket orders (TP/SL) that no longer have an associated position.

### Location
```
apps/reference/services/order_guardian.py
```

### Key Methods

| Method | Description |
|--------|-------------|
| `cleanup_orphans(symbol, hard)` | Cancels orphan brackets for a symbol (or all symbols) |
| `reconcile_symbol(symbol, rid)` | Reconciles orders for a specific symbol after position close |
| `poll_and_cleanup()` | Background polling loop that runs cleanup periodically |

### How It Works

1. **Polling Mode**: Guardian runs in background, polling every `poll_interval_ms` (default: 5000ms)
2. **Detection**: Compares open orders against open positions
3. **Cancellation**: If order exists but no position → cancel order
4. **Event Emission**: After cleanup, emits `EVT:SYMBOL_TIDY` via event bus

### Configuration
```yaml
# config/aurora/trading.yaml
execution:
  order_guardian:
    poll_interval_ms: 5000
```

### Event Flow
```
Guardian poll → cleanup_orphans() → cancel orders → emit EVT:SYMBOL_TIDY
```

---

## 2. GATE (Entry Tidy Gate)

### Purpose
Blocks new ENTRY orders until Guardian confirms the symbol is "clean" (no orphan orders).

### Location
```
apps/reference/domains/execution_position/fsm.py
```

### Key Methods

| Method | Description |
|--------|-------------|
| `_entry_tidy_gate_allow(symbol)` | Returns True if ENTRY is allowed |
| `_on_symbol_tidy_event(payload)` | Listens for `EVT:SYMBOL_TIDY` and updates timestamps |

### How It Works

1. **Listening**: FSM subscribes to `EVT:SYMBOL_TIDY` events from Guardian
2. **Timestamp Tracking**: Stores last tidy timestamp per symbol in `_symbol_last_tidy_ts`
3. **Gate Check**: Before placing MARKET entry, checks if symbol was "tidied" recently
4. **TTL Logic**: Entry allowed if `(now - last_tidy) <= ttl_ms` (default: 6000ms)

### Configuration
```yaml
# config/aurora/trading.yaml
execution:
  allow_trade_with_guardian_tidy_only: true  # Enable/disable GATE

# Guardian config (used by GATE)
guardian:
  cleanup_ttl_ms: 6000      # How long tidy is considered "fresh"
  symbol_cooldown_ms: 4000  # Cooldown after block before retry
```

### Gate Logic (Pseudocode)
```python
def _entry_tidy_gate_allow(symbol):
    if not allow_trade_with_guardian_tidy_only:
        return True  # GATE disabled
    
    last_tidy = _symbol_last_tidy_ts.get(symbol, 0.0)
    fresh = (now - last_tidy) * 1000 <= ttl_ms
    
    if fresh or (last_block > 0 and cooldown_ok):
        return True  # Allow entry
    else:
        return False  # Block entry
```

---

## 3. Interaction Between GATE and Guardian

```
┌─────────────────────────────────────────────────────────────────┐
│                         Event Flow                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Guardian (background)              FSM (on TRADE_INTENT)        │
│  ┌──────────────────┐              ┌──────────────────┐         │
│  │ poll_and_cleanup │              │ handle(CMD:OPEN) │         │
│  │        ↓         │              │        ↓         │         │
│  │ cleanup_orphans  │              │ _entry_tidy_gate │         │
│  │        ↓         │              │     _allow()     │         │
│  │ emit EVT:SYMBOL_ │──────────────│        ↓         │         │
│  │      TIDY        │   listens    │ Check timestamp  │         │
│  └──────────────────┘              │        ↓         │         │
│                                    │ Allow or Block   │         │
│                                    │ ENTRY order      │         │
│                                    └──────────────────┘         │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 4. Known Problem: Cold Start Blocking

### Issue Description

When the system starts (cold start), **no symbol has ever received a TIDY event**. The GATE logic uses `0.0` as default timestamp:

```python
last_tidy = self._symbol_last_tidy_ts.get(symbol, 0.0)  # Returns 0.0 if not found
fresh = (now - last_tidy) * 1000.0 <= ttl_ms  # (now - 0) * 1000 = huge number >> ttl_ms
```

This means:
- `fresh = False` (huge age)
- `last_block = 0.0` (no prior block)
- Condition `last_block > 0 and cooldown_ok` → `False and True` → `False`
- **Result: GATE blocks ALL entries indefinitely on cold start**

### Log Evidence
```
2025-12-02 17:06:48,410 - [GATE] entry_blocked: no_tidy_recent symbol=SOLUSDT age_ms=1764695208410 ttl_ms=6000 cooldown_ms=4000
```

The `age_ms=1764695208410` (~20 days in ms) shows the timestamp was `0.0` (epoch).

### Current Workaround

GATE is disabled in config:
```yaml
execution:
  allow_trade_with_guardian_tidy_only: false  # Disabled due to cold start bug
```

---

## 5. Proposed Fix (Not Yet Implemented)

Add special handling for symbols with no prior TIDY event:

```python
def _entry_tidy_gate_allow(self, symbol: str) -> bool:
    # ... existing flag check ...
    
    last_tidy = self._symbol_last_tidy_ts.get(symbol)  # None if not found
    
    # FIX: If no tidy event yet for this symbol, allow entry (cold start)
    # Guardian will clean up orphans asynchronously anyway
    if last_tidy is None:
        LOG.info(f"[GATE] entry_allowed: no_prior_tidy (cold start) symbol={symbol}")
        return True
    
    # ... rest of existing logic ...
```

---

## 6. Open Questions

### Q1: Do we need both GATE and Guardian?

**Guardian alone** can handle orphan cleanup, but there's a race condition risk:

```
t=0ms:  TRADE_INTENT → place ENTRY order
t=1ms:  Old SL from previous position still exists
t=2ms:  Old SL triggers → closes new position with loss!
t=5000ms: Guardian poll → cancels old SL (too late)
```

**GATE prevents this** by blocking ENTRY until Guardian confirms no orphans.

### Q2: Alternative: Synchronous cleanup before ENTRY?

Instead of GATE + async Guardian, we could:
1. Call `Guardian.cleanup_orphans(symbol)` **synchronously** before placing ENTRY
2. Remove GATE entirely
3. One logic instead of two

**Pros:**
- Simpler architecture
- No race condition
- No cold start problem

**Cons:**
- Adds latency to ENTRY (cleanup takes time)
- May hit rate limits if many orphans

### Q3: Should GATE be removed entirely?

If Guardian runs frequently (5s) and cleans up orphans reliably, GATE may be redundant overhead.

**Recommendation**: Keep GATE but fix the cold start bug. GATE is cheap (just a timestamp check) and provides extra safety.

---

## 7. Files Involved

| File | Purpose |
|------|---------|
| `apps/reference/services/order_guardian.py` | Active orphan cleanup, emits `EVT:SYMBOL_TIDY` |
| `apps/reference/domains/execution_position/fsm.py` | GATE logic, listens for tidy events |
| `config/aurora/trading.yaml` | GATE enable/disable flag, TTL settings |
| `configs/master_config_v1.yaml` | Alternative config location |

---

## 8. Configuration Reference

```yaml
# execution section
execution:
  allow_trade_with_guardian_tidy_only: false  # GATE master switch
  fsm_periodic_cleanup_enabled: false
  order_guardian:
    poll_interval_ms: 5000  # How often Guardian polls

# guardian section (used by GATE)
guardian:
  cleanup_ttl_ms: 6000       # Tidy freshness TTL
  symbol_cooldown_ms: 4000   # Cooldown after block
```

---

## 9. Metrics

GATE exposes metrics via `/metrics` endpoint:

```json
{
  "gate_entry_blocked_tidy": 5,
  "gate_entry_allowed_tidy": 42,
  "symbol_last_tidy_ts": {
    "BTCUSDT": 1733150808.123,
    "ETHUSDT": 1733150805.456
  }
}
```

---

## 10. Action Items

- [ ] Decide: Keep GATE with fix or remove entirely
- [ ] If keeping: Implement cold start fix in `_entry_tidy_gate_allow()`
- [ ] If removing: Delete GATE code and related config
- [ ] Update tests accordingly
- [ ] Re-enable `allow_trade_with_guardian_tidy_only: true` after fix

---

*Document created: 2025-12-02*
*Status: Open Question*
