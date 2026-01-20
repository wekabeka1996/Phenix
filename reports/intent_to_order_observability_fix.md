# INTENT-TO-ORDER-TRACE-SSOT-01: Implementation Summary

**Date**: 2026-01-13
**Status**: ✅ COMPLETE

## Objective

> "Зробити так, щоб будь-який намір (intent), який доходить до execution, давав однозначні артефакти"

Full observability for intent→order chain, eliminating silent failures.

## Phase A: Forensic Analysis (✅ Complete)

### WAL Event Counts (ops/wal/2026-01-13.jsonl)
```
 11475 EVT:ACCOUNT_UPDATE_RECEIVED
  3085 EVT:BAR_CLOSED
  1417 EVT:TRADE_INTENT_REJECTED
     8 DEC:OPEN
     4 DEC:CLOSE
     0 EVT:TRADE_INTENT_PROPOSED ← never reached
     0 EVT:ORDER_PLACED          ← not written to WAL
```

### Root Cause
- `EVT:TRADE_INTENT_PROPOSED` not reached due to `ENTRY_PLAN_ATR_NOT_READY` rejections
- ORDER_PLACED/REJECTED were only written to order_log, not WAL
- No boot record in order_log to distinguish "no orders" from "logger not running"

### Report Created
- [reports/intent_to_order_trace_map.md](reports/intent_to_order_trace_map.md)

## Phase B: Implementation (✅ Complete)

### B1: EVT:ORDER_PLACED WAL Write
**File**: `apps/reference/domains/execution_position/fsm.py` (line ~2690)

Added WAL append after successful adapter.place_market_entry():
```python
placed_msg = Message(
    op="EVT", verb="ORDER_PLACED",
    src="execution_position", dst="*",
    pld={...adapter_response...},
    why="order placed via adapter.place_market_entry"
)
self.fsm.emit("EVT:ORDER_PLACED", placed_msg.pld, placed_msg.why)
wal.append(placed_msg.model_dump())  # WAL persistence
```

### B2: EVT:ORDER_REJECTED WAL Write
**File**: `apps/reference/domains/execution_position/fsm.py`

Two locations fixed:

1. **LIMIT rejection** (line ~2580):
   ```python
   reject_msg = Message(op="EVT", verb="ORDER_REJECTED", ...)
   self.fsm.emit("EVT:ORDER_REJECTED", reject_msg.pld, reject_msg.why)
   wal.append(reject_msg.model_dump())  # Added
   ```

2. **Adapter failure** (line ~2990):
   ```python
   reject_msg = Message(op="EVT", verb="ORDER_REJECTED", ...)
   self.fsm.emit("EVT:ORDER_REJECTED", reject_msg.pld, reject_msg.why)
   wal.append(reject_msg.model_dump())  # Added
   ```

### B3: Order Logger BOOT Record
**File**: `apps/reference/telemetry/order_logger.py`

Added `_write_boot_record()` method called in `__init__`:
```python
def _write_boot_record(self) -> None:
    boot_record = {
        "event_type": "BOOT",
        "timestamp": int(time.time() * 1000),
        "source_fsm": "OrderLoggerV1",
        "rid": f"boot-{int(time.time() * 1000)}",
        "symbol": "_SYSTEM_",
        "why": "order_logger session start marker",
    }
    # Write directly without schema validation
    with open(self.log_file, 'a', encoding='utf-8') as f:
        json.dump(boot_record, f, ensure_ascii=False)
        f.write('\n')
```

**File**: `apps/reference/schemas/order_logger_v1.json`

Added `BOOT` to event_type enum:
```json
"event_type": {
  "enum": ["BOOT", "ORDER_INTENT", "ORDER_PLACED", ...]
}
```

## Phase C: Tests (✅ Complete)

**New Test File**: `tests/domains/execution_position/test_order_observability_wal.py`

```
tests/domains/execution_position/test_order_observability_wal.py::TestOrderLoggerBoot::test_boot_record_written_on_init PASSED
tests/domains/execution_position/test_order_observability_wal.py::TestWALOrderObservability::test_order_placed_writes_to_wal PASSED
tests/domains/execution_position/test_order_observability_wal.py::TestWALOrderObservability::test_order_rejected_writes_to_wal PASSED
tests/domains/execution_position/test_order_observability_wal.py::TestWALOrderObservability::test_limit_rejection_writes_to_wal PASSED
tests/domains/execution_position/test_order_observability_wal.py::TestOrderLoggerSchemaValidation::test_boot_event_type_in_schema PASSED

============================== 5 passed in 0.06s ==============================
```

## Phase D: Runtime Verification (✅ Complete)

- vfoundation tests: 15 passed
- WAL module imports correctly with `append` function
- Message protocol works with model_dump()

## Observability Guarantees (Post-Fix)

| Scenario | WAL Artifact | Order Log Artifact |
|----------|--------------|-------------------|
| Order placed successfully | EVT:ORDER_PLACED | ORDER_PLACED |
| Order rejected (LIMIT policy) | EVT:ORDER_REJECTED | ORDER_REJECTED |
| Order rejected (adapter fail) | EVT:ORDER_REJECTED | ORDER_REJECTED |
| System start | - | BOOT |

## Files Modified

1. `apps/reference/domains/execution_position/fsm.py` - WAL writes for ORDER_PLACED/REJECTED
2. `apps/reference/telemetry/order_logger.py` - BOOT record on init
3. `apps/reference/schemas/order_logger_v1.json` - BOOT in event_type enum
4. `tests/domains/execution_position/test_order_observability_wal.py` - New test file

## Related Reports

- [reports/intent_to_order_trace_map.md](reports/intent_to_order_trace_map.md) - Forensic analysis
- [reports/dm_strategy_ssot_fixplan_01.md](reports/dm_strategy_ssot_fixplan_01.md) - SSOT fixes

## Remaining Notes

- ATR rejection (`ENTRY_PLAN_ATR_NOT_READY`) is now fixed by P0-1 (MR volatility propagation)
- Future intents reaching execution will now produce WAL artifacts
- Full RID tracing: bar → features → intent → decision → order → outcome
