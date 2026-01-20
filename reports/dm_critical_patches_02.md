# DM-CRITICAL-PATCHES-02: Implementation Report

**Date**: 2026-01-13
**Status**: ✅ COMPLETE

## Scope

1. **PATCH 1**: Arbitration - dedicated signal buffer with priority ranks
2. **PATCH 2A**: Regime Heartbeat emission with `changed` flag
3. **PATCH 2B**: Liveness guard based on heartbeat (not regime value)
4. **PATCH 3**: EntryPlan fail-closed sanitization

---

## PATCH 1: Arbitration (SSOT, dedicated buffer)

### File: `apps/reference/domains/decision_making/decision_making.py`

**Changes:**
1. Added `_arb_signal_buffer: Dict[str, Tuple[int, str, int]]` in `__init__` (symbol → ts_ms, strategy_id, rank)
2. Rewrote `_check_strategy_arbitration()`:
   - Gets rank from `arb.priority.get(strategy_id)`
   - Fail-closed: if rank is None → LOG ERROR + DROP signal
   - Within window_ms: higher priority (lower rank) overrides
   - Forensic logging: symbol, old_sid/new_sid, old_rank/new_rank, delta_ms

**Key Logic:**
```python
# Within window: compare ranks
if rank < last_rank:
    # Higher priority wins - overwrite buffer
    self._arb_signal_buffer[symbol] = (now_ms, strategy_id, rank)
    return {"allowed": True, "reason": ""}
elif rank >= last_rank:
    # Lower or equal priority - DROP
    return {"allowed": False, "reason": f"lower_priority_vs_{last_sid}"}
```

### SSOT Source: `config/aurora/strategies.yaml`
```yaml
arbitration:
  mode: priority
  window_ms: 1000
  priority:
    aurora: 1           # Higher priority
    mean_reversion: 2   # Lower priority
```

---

## PATCH 2A: Regime Heartbeat + Changed Flag

### File: `apps/reference/domains/regime_detector/regime_detector.py`

**Changes:**
- `EVT:REGIME_DETECTED` now emitted on EVERY basis bar close (not just on change)
- Added fields to payload:
  - `changed: bool` - True if regime transitioned, False if heartbeat only
  - `last_update_ts_ms: int` - Monotonic timestamp for liveness check

**Key Logic:**
```python
last_regime = self._last_emitted_regime.get(symbol)
changed = (last_regime is None) or (last_regime != regime)

payload = {
    ...
    "changed": changed,
    "last_update_ts_ms": now_ms,
}
```

### Schema Updated: `apps/reference/domains/regime_detector/schemas/regime_detected_v1.json`
```json
{
  "changed": {"type": "boolean"},
  "last_update_ts_ms": {"type": "integer", "minimum": 0}
}
```

---

## PATCH 2B: Liveness Guard

### File: `apps/reference/domains/decision_making/aurora_handler.py`

**Changes:**
1. Added `last_regime_heartbeat_ms: Optional[int]` to `SymbolState`
2. `on_regime_detected()` now updates heartbeat on EVERY event (even if changed=False)
3. Added `_check_regime_liveness()` method
4. Guard in `on_process_strategy()` before price check

**Key Logic:**
```python
def _check_regime_liveness(self, symbol: str, state: SymbolState) -> Optional[Dict]:
    if state.last_regime_heartbeat_ms is None:
        return {"reason_code": "NRR-REGIME-NO-HEARTBEAT", ...}
    
    max_delay_ms = basis_tf_sec * 1000 * liveness_factor
    delta_ms = now_ms - state.last_regime_heartbeat_ms
    
    if delta_ms > max_delay_ms:
        return {"reason_code": "NRR-REGIME-DETECTOR-DEAD", ...}
    
    return None  # OK
```

### Config Added: `config/aurora/regime.yaml`
```yaml
liveness_factor: 3  # Block if no heartbeat for 3 * basis_tf_sec
```

### Config Model: `apps/reference/config_models.py`
```python
liveness_factor: int = Field(default=3, ge=1, ...)
```

---

## PATCH 3: EntryPlan Fail-Closed

### File: `apps/reference/domains/decision_making/entry_plan.py`

**Changes to `compute()`:**
1. ATR=None handling:
   - If `require_atr=True` → raise `ValueError("ENTRYPLAN_ATR_MISSING")`
   - If `require_atr=False` → use `ATR=0` with safety guards
2. Added `tick_size` parameter for safety floor
3. Safety guards for SL/TP offsets:
   ```python
   min_offset = tick_size or (ref_price * 0.0001)  # 1 bp fallback
   sl_offset = max(sl_offset_raw, min_offset)
   tp_offset = max(tp_offset_raw, min_offset)
   ```

**Guarantees:**
- No TypeError on `Decimal(None)`
- No zero SL/TP even with ATR=0
- Clean reject when ATR required but missing

---

## Test Results

### `tests/audit_decision_verify.py` (5 tests)
```
test_audit_01_entry_plan_no_crash_on_none_atr_when_not_required PASSED
test_audit_01b_entry_plan_reject_on_none_atr_when_required PASSED
test_audit_02_strategy_arbitration_priority_buffer PASSED
test_audit_03_regime_liveness_heartbeat PASSED
test_audit_04_regime_changed_field PASSED
```

### Other Test Suites
- `tests/vfoundation`: 15 passed
- `tests/integration/test_ep01_2_entry_plan.py`: 22 passed
- `tests/domains/decision_making/test_aurora_respects_registry.py`: 11 passed
- Dictionary validation: OK

---

## Files Modified

| File | Change |
|------|--------|
| `apps/reference/domains/decision_making/decision_making.py` | Added `_arb_signal_buffer`, rewrote arbitration |
| `apps/reference/domains/regime_detector/regime_detector.py` | Added `changed`, `last_update_ts_ms` to emit |
| `apps/reference/domains/regime_detector/schemas/regime_detected_v1.json` | Added new fields to schema |
| `apps/reference/domains/decision_making/aurora_handler.py` | Added heartbeat tracking, liveness guard |
| `apps/reference/domains/decision_making/entry_plan.py` | ATR=None handling, safety guards |
| `apps/reference/config_models.py` | Added `liveness_factor` field |
| `config/aurora/regime.yaml` | Added `liveness_factor: 3` |
| `tests/audit_decision_verify.py` | Updated with new test scenarios |

---

## Acceptance Criteria

| Criteria | Status |
|----------|--------|
| Arbitration uses YAML priority (no hardcode) | ✅ |
| Flat market: regime events with `changed=False` | ✅ |
| Dead detector: BLOCK with `NRR-REGIME-DETECTOR-DEAD` | ✅ |
| EntryPlan: no crash on None ATR | ✅ |
| EntryPlan: clean reject when require_atr=True | ✅ |
| All tests pass | ✅ |
| No hardcoded priorities/timings | ✅ |

---

## NRR Codes (Normalized Reject Reasons)

| Code | When |
|------|------|
| `NRR-REGIME-NO-HEARTBEAT` | No regime event ever received |
| `NRR-REGIME-DETECTOR-DEAD` | Heartbeat stale > liveness_factor * basis_tf_sec |
| `ENTRYPLAN_ATR_MISSING` | ATR=None and require_atr=True |
| `ARBITRATION_REJECT:missing_priority:{sid}` | Strategy not in priority map |
| `ARBITRATION_REJECT:lower_priority_vs_{sid}` | Dropped due to lower priority |
