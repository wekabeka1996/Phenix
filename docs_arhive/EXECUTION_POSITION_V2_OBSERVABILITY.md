# ExecPosRuntimeV2 Observability Guide

## Overview

ExecPosRuntimeV2 is the **only active execution runtime** (as of 2025-11-21, EP-LEGACY-PURGE-S1).

It provides structured logging and metrics for transparent observability in live trading.

**Note:** The `runtime_mode` config key is no longer used. All execution flows through V2.

## Structured Logging

### Log File
- **Location**: `logs/execpos_v2_runtime.jsonl`
- **Format**: One JSON object per line (JSONL)
- **Fail-Closed**: Logging errors never crash trading logic

### Log Schema

All log entries contain:

```json
{
  "ts": "2025-11-20T21:00:00.123Z",       // ISO8601 timestamp
  "runtime": "ExecPosRuntimeV2",           // Always "ExecPosRuntimeV2"
  "symbol": "BTCUSDT",                     // Trading symbol
  "event_kind": "ENTRY_INTENT",            // Event type
  "action": "executed",                    // Action taken
  "result": "success",                     // Result of action
  "why": "order_placed"                    // Reason/explanation
}
```

**Optional fields** (depending on event):
- `order_id`, `client_order_id`
- `qty`, `price`, `side`
- `order_type`
- `watchdog_violation_kind`
- `error_code`, `error_message`

### Event Types Logged

| event_kind | action | result | Meaning |
|------------|--------|--------|---------|
| `ENTRY_INTENT` | `rejected` | `blocked` | Gatekeeper blocked entry |
| `ENTRY_INTENT` | `executed` | `success` | Order placed successfully |
| `ENTRY_INTENT` | `executed` | `failed` | Order placement failed |
| `WATCHDOG_ACTION` | `detected` | `success` | Violation detected |
| `WATCHDOG_ACTION` | `healed` | `success` | Violation auto-healed |

## Metrics

### get_metrics_snapshot()

Call `runtime.get_metrics_snapshot()` to get current metrics:

```python
snapshot = runtime.get_metrics_snapshot()
```

**Returns:**
```python
{
    "events_total": 1234,
    "events_by_kind": {
        "ENTRY_INTENT": 50,
        "TRADE_EXECUTED": 45,
        ...
    },
    "gatekeeper_allowed": 45,
    "gatekeeper_rejected": 5,
    "execution_success": 40,
    "execution_failed": 2,
    "fills_processed": 38,
    "fills_duplicate": 2,
    "watchdog_violations": 3,
    "watchdog_violations_by_kind": {
        "NO_SL_FOR_OPEN_POSITION": 2,
        "ORPHAN_SL_FOR_ZERO_POSITION": 1
    },
    "positions_tracked": 3,
    "symbols_active": ["BTCUSDT", "ETHUSDT", "BNBUSDT"]
}
```

### Global /metrics Integration

When `runtime_mode="v2"`, metrics are automatically included in `/metrics` endpoint under the `execpos_v2` section.

## Regression Guard Tool

### Usage

```bash
# Analyze recent logs
python -m tools.execpos_v2_guard --log-file logs/execpos_v2_runtime.jsonl --last-n 1000

# Analyze metrics snapshot
python -m tools.execpos_v2_guard --metrics-file metrics_snapshot.json
```

### Thresholds (Configurable)

- **Execution Failure Rate**: > 10% triggers ALERT
- **Watchdog Violation Rate**: > 5% triggers WARN
- **Duplicate Fill Rate**: > 20% triggers WARN

### Exit Codes

- **0**: OK - All checks passed
- **1**: WARN - Minor issues detected
- **2**: ALERT - Critical issues detected

### Example Output

```
✅ Status: OK
Message: All checks passed

Metrics:
  total_events: 1000
  executed_success: 950
  executed_failed: 50
  execution_failure_rate: 0.0500
  watchdog_events: 10
  watchdog_rate: 0.0100
```

## Integration Example

```python
from apps.reference.domains.execution_position.runtime_factory import build_execution_runtime

# Runtime is V2 by default
runtime = build_execution_runtime(config)

# Later, get metrics for monitoring
snapshot = runtime.get_metrics_snapshot()
print(f"Events processed: {snapshot['events_total']}")
print(f"Success rate: {snapshot['execution_success'] / (snapshot['execution_success'] + snapshot['execution_failed'])}")
```

## Testing

### Run Tests

```bash
# Logging tests
pytest tests/domains/execution_position/shadow_execpos/test_v2_logging_runtime.py -v

# Metrics tests
pytest tests/domains/execution_position/shadow_execpos/test_v2_metrics_snapshot.py -v

# Guard tool tests
pytest tests/tools/test_execpos_v2_guard.py -v
```

## Files

### New Files Created
- `apps/reference/domains/execution_position/shadow_execpos/logging_v2.py` - Logging module
- `tools/execpos_v2_guard.py` - Regression guard CLI
- `tests/domains/execution_position/shadow_execpos/test_v2_logging_runtime.py` - Logging tests
- `tests/domains/execution_position/shadow_execpos/test_v2_metrics_snapshot.py` - Metrics tests
- `tests/tools/test_execpos_v2_guard.py` - Guard tool tests

### Modified Files
- `apps/reference/domains/execution_position/shadow_execpos/runtime.py` - Added logging + `get_metrics_snapshot()`

## Safety

- **Fail-Closed**: All logging wrapped in try/except - errors logged as warnings and never crash trading
- **No Config Changes**: Works with existing config, no new settings required
- **No New Modes**: Uses existing V2 runtime (default since EP-RUNTIME-PROMOTION-CLEANUP-S1)
