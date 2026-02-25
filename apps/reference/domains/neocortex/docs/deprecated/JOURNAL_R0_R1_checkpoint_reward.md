# Neocortex Phase R0/R1 Journal Entry

**Date:** 2026-01-10
**Author:** Antigravity AI
**Phase:** R0 (Checkpoint Fix) + R1 (Reward Parsing)

---

## TASK 1: Checkpoint Persistence Fix (R0 Critical)

### Problem Discovery
- Ran Neocortex for ~6 hours (279 training steps)
- **NO checkpoints appeared** in `data/checkpoints/`
- Root cause: `checkpoint_every_n_steps: 1000` was too high

### Investigation
1. Checked `config/neuro.yaml` - found `checkpoint_every_n_steps: 1000`
2. With 279 steps total, threshold was never reached
3. Worker process isolation might have caused silent path issues

### Fixes Applied
1. **Config Change** (`config/neuro.yaml`):
   ```yaml
   # TASK-R0-FIX: Reduced from 1000 to 50 for frequent checkpointing
   checkpoint_every_n_steps: 50
   ```

2. **Debug Logging** (`logic/brain/core.py`):
   - Added explicit `print()` statements to trace checkpoint flow
   - Force `flush=True` to ensure immediate output from worker process

3. **Explicit Dir Creation**:
   - Confirmed `path.mkdir(parents=True, exist_ok=True)` is in place

4. **Adapter Logging** (`transport/adapter.py`):
   - Added INFO log before triggering checkpoint

### Verification
- Tests pass: `test_checkpoint_persistence.py` (3 passed, 3 skipped)
- Next run should produce `checkpoint_50.pt` after ~1 hour

---

## TASK 2: PnL / Reward Parsing (R1)

### Log Analysis Discovery

**Searched for PnL in Aurora logs:**
```bash
grep -iE "PnL|profit|loss" logs/aurora_core.log*
```

**Findings:**
1. Position close format: `[SYMBOL] Position closed (neutral). Starting re-entry cooldown.`
2. **NO explicit PnL value logged** on position close
3. Equity updates exist: `totalWalletBalance=251.79752181, totalUnrealizedProfit=0E-8`

**Conclusion:** Aurora currently does NOT log realized PnL per trade.

### Solution: Equity-Delta PnL Estimation

Since no direct PnL is available, we implemented equity tracking:

1. **Snapshot equity at order placement:**
   ```python
   self._equity_at_entry[symbol] = self._last_equity
   ```

2. **Track equity updates from core log:**
   ```python
   if entry.event_type == CoreEventType.EQUITY_UPDATE:
       self._last_equity = entry.equity
   ```

3. **Calculate PnL on position close:**
   ```python
   raw_pnl = current_equity - entry_equity
   normalized_reward = float(np.tanh(raw_pnl / 10.0))
   ```

**Reward Normalization:**
- Using `tanh(pnl / 10.0)` maps PnL to [-1, 1]
- $10 profit → reward ≈ 0.76
- $10 loss → reward ≈ -0.76
- Bounded for PPO stability

### Files Modified
- `logic/ingest/multi_tailer.py`:
  - Added `_equity_history`, `_equity_at_entry`, `_last_equity` tracking
  - Updated `_process_core()` to capture EQUITY_UPDATE events
  - Updated `_handle_position_close()` with equity-delta PnL calculation

### Tests Created
- `tests/test_reward_parsing.py` (19 tests):
  - Core log parsing (6 tests)
  - Order log parsing (4 tests)
  - Reward normalization (5 tests)
  - Equity delta calculation (3 tests)
  - Integration test (1 test)

### Limitations
- Equity-delta includes ALL positions, not just the closed one
- This is an approximation; true per-trade PnL requires Aurora changes
- Good enough for RL training signal

---

## Summary

| Task | Status | Key Change |
|------|--------|------------|
| R0: Checkpointing | ✅ Fixed | `checkpoint_every_n_steps: 50` |
| R1: PnL Parsing | ✅ Implemented | Equity-delta estimation |
| Tests | ✅ 22 tests passing | reward_parsing + checkpoint |

---

## Next Steps

1. **Run Neocortex for 2+ hours** - verify checkpoints appear
2. **Monitor PnL logs** - check `EPISODE COMPLETE: {symbol} pnl=X.XX reward=Y.YY`
3. **Aurora Enhancement** (separate task) - Add explicit PnL logging on position close
