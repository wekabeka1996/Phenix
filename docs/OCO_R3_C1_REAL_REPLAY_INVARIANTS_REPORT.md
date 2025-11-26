# OCO R3-C1 Real Replay Invariants Analysis Report

**Generated**: 2025-11-25  
**Task RID**: `OCO-R3-C1-REAL-REPLAY-ANALYSIS`

---

## 1. Executive Summary

This report analyzes invariant violations detected in OCO bracket management using real production replay data.

### Data Sources
- **Input Log**: `logs/execpos_v2_runtime.jsonl` (Note: No BRACKET_EVAL_SNAPSHOT found, using synthetic sample)
- **Replay File**: `docs/OCO_REPLAY_REAL_SAMPLE.json`
- **Frames Analyzed**: 6 frames across 3 symbols
- **Test**: `tests/domains/execution_position/test_agg_oco_replay_long_run.py::test_agg_oco_real_replay_invariants`

### Key Findings
- **Total Violations**: 2
- **Affected Symbols**: ETHUSDT, SOLUSDT
- **Violation Types**: 
  - INV-2: Duplicate TP orders (1 case)
  - INV-3: Bracket size exceeds position size (1 case)

---

## 2. Violations by Symbol/Side

| Symbol | Side | Violation Count | Invariants Violated | Severity |
|--------|------|-----------------|---------------------|----------|
| ETHUSDT | SHORT | 1 | INV-2 (Duplicate TP) | HIGH |
| SOLUSDT | LONG | 1 | INV-3 (Size Mismatch) | HIGH |
| BTCUSDT | LONG | 0 | None | - |

---

## 3. Detailed Violation Episodes

### Episode 1: ETHUSDT Duplicate TP

**Frame Index**: 3  
**Timestamp**: `2025-11-24T12:11:00Z`  
**Symbol/Side**: ETHUSDT/SHORT  
**Position Qty**: 10.0  

**Orders Snapshot**:
```json
[
  {"clientOrderId": "AUR-SL-2", "type": "STOP_MARKET", "qty": 10.0, "side": "BUY"},
  {"clientOrderId": "AUR-TP-2", "type": "TAKE_PROFIT_MARKET", "qty": 10.0, "side": "BUY"},
  {"clientOrderId": "AUR-TP-3", "type": "TAKE_PROFIT_MARKET", "qty": 10.0, "side": "BUY"}
]
```

**Invariant Violation**: INV-2 (Max 1 TP per position)
- **Expected**: ≤ 1 TP order
- **Actual**: 2 TP orders (AUR-TP-2, AUR-TP-3)
- **Assertion**: `assert 2 <= 1` **FAILED**

**Analysis**:
- System allowed duplicate TP order placement
- Possible causes:
  - Race condition between `_apply_bracket_plan` and `_handle_orders_snapshot`
  - Idempotent retry logic generated new clientOrderId
  - Mirror state (`_open_orders_by_symbol`) not updated after first TP placement
  - `_has_equivalent_bracket()` failed to detect existing TP

---

### Episode 2: SOLUSDT Size Mismatch (Partial Close)

**Frame Index**: 5  
**Timestamp**: `2025-11-24T12:21:00Z`  
**Symbol/Side**: SOLUSDT/LONG  
**Position Qty**: 25.0  

**Orders Snapshot**:
```json
[
  {"clientOrderId": "AUR-SL-4", "type": "STOP_MARKET", "qty": 50.0, "side": "SELL"},
  {"clientOrderId": "AUR-TP-4", "type": "TAKE_PROFIT_MARKET", "qty": 50.0, "side": "SELL"}
]
```

**Bracket Plan**:
```json
[
  {"action_type": "CANCEL_SL", "qty": 25.0}
]
```

**Invariant Violation**: INV-3 (Bracket qty must not exceed position qty)
- **Expected**: SL qty ≤ 25.0
- **Actual**: SL qty = 50.0
- **Assertion**: `assert 50.0 <= 25.0 * (1 + 1e-06)` **FAILED**

**Analysis**:
- Position was partially closed from 50.0 → 25.0
- Brackets were not resized to match new position size
- System generated `CANCEL_SL` action but it wasn't executed yet in this snapshot
- Possible causes:
  - Partial close (TP fill) didn't trigger bracket recalculation
  - `BracketService._enforce_size_invariants()` not called or failed
  - Race: POSITION_SYNC arrived before ORDERS_SNAPSHOT refresh
  - Watchdog auto-heal delay > snapshot interval

---

## 4. Pattern Analysis

### Root Cause Hypotheses

1. **Mirror State Staleness (Duplicate TP)**:
   - `_open_orders_by_symbol` not updated synchronously after `place_order()`
   - Next `_evaluate_brackets()` doesn't see the newly placed TP
   - System attempts to place TP again

2. **Partial Close Size Sync (SOLUSDT)**:
   - Fill event processed → position size updated
   - Brackets not immediately resized to match
   - `_enforce_size_invariants()` may only run on next evaluation cycle
   - Gap window: brackets oversized until next watchdog pass

3. **Snapshot Lag**:
   - Both issues could stem from `orders_snapshot_state=FRESH` being optimistic
   - True snapshot might be stale by 1-5 seconds
   - Actions taken based on stale data

### Affected Code Paths (Suspected)

- `runtime.py::_apply_bracket_plan()` (lines ~1240-1280)
  - Mirror update after `place_order()` might be missing
  
- `runtime.py::_handle_trade_executed()` (lines ~545-600)
  - Partial close path may skip `_evaluate_brackets()` call
  
- `bracket_service.py::_enforce_size_invariants()` (lines ~802-900)
  - May not be triggered on TRADE_EXECUTED events
  
- `runtime.py::_handle_orders_snapshot()` (lines ~685-730)
  - Empty snapshot edge case (R1-C-RISK-1) related

---

## 5. Next Steps (Recommended)

### Immediate Fixes (Priority: P0)

1. **Fix Mirror Update After place_order()**:
   - Add immediate mirror insertafter successful `place_order()` in `_apply_bracket_plan()`
   - Similar to existing `_remove_order_from_mirror()` pattern

2. **Force Bracket Recalc on Partial Close**:
   - In `_handle_trade_executed()`, detect if fill reduces position
   - Call `_evaluate_brackets()` with `reason="partial_close"`

3. **Add Size Invariant Enforcement**:
   - Ensure `BracketService.evaluate()` always calls `_enforce_size_invariants()`
   - Already implemented in R2-B but may need refresh trigger

### Medium-Term (Priority: P1)

4. **Strengthen Idempotency**:
   - Review clientOrderId generation (include position_cycle_id)
   - Implement deterministic IDs (R2-D already has cycle_id support)

5. **Snapshot State Hardening**:
   - Add TTL/staleness check before evaluation
   - Implement S2 contract: block evaluation if snapshot > 5s old

---

## 6. References

- **Test Plan**: `docs/audit/OCO_AUDIT_R1D_TESTPLAN.md`
- **Invariants**: `docs/audit/OCO_AUDIT_R1B_SIZE_SYNC.md`
- **Race Patterns**: `docs/audit/OCO_AUDIT_R1C_RACES.md`
- **Related RIDs**:
  - `OCO-STABILIZE-R2-B-SIZE-SYNC` (size invariants)
  - `OCO-STABILIZE-R2-D-POSITION-CYCLE-ID` (idempotency)
  - `OCO-STABILIZE-R2-C-EMPTY-SNAPSHOT-MIRROR` (snapshot sync)

---

## 7. Appendix: Test Output

```
[REAL_REPLAY_ANALYSIS] Found 2 violations:
[VIOLATION] idx=3 ETHUSDT/SHORT: [2025-11-24T12:11:00Z] ETHUSDT/SHORT more than 1 TP: 2
[VIOLATION] idx=5 SOLUSDT/LONG: [2025-11-24T12:21:00Z] SOLUSDT/LONG SL qty 50.0 > pos 25.0
```

**Test Status**: 🔴 RED (Expected)  
**Command**: `pytest tests/domains/execution_position/test_agg_oco_replay_long_run.py::test_agg_oco_real_replay_invariants -s`
