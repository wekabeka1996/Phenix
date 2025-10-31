# Drift Monitor     Shadow-Mode Validation (FSMP-P1-T03)

## Overview

Drift Monitor                  **drift%**      **confusion matrix**                                              FSM (DEC:OPEN/CLOSE)                                                            (EVT:ORDER_PLACED/FILL/CANCELLED).

**                      **:                    shadow-mode FSM                                        hot-path production.

##                       

### Confusion Matrix

- **TP (True Positive)**: DEC:OPEN/CLOSE                               EVT    time-window
- **FP (False Positive)**: DEC:OPEN/CLOSE                                 EVT
- **FN (False Negative)**: EVT                                 DEC (                               )
- **TN (True Negative)**:                       DEC           EVT (stub: TN=0)

### Drift Formula

```
drift_pct = (FP + FN) / (TP + FP + FN + TN) * 100
```

**                          **:
- `drift_pct < 1%`     FSM ready for canary (10%)
- `drift_pct < 5%`     FSM needs minor tuning
- `drift_pct > 10%`     FSM needs major review

### Matching Rules

**                    **:      `RID` (primary key), `symbol`                                                       DEC.

**Time window**:   1s (default),                                         `time_window_sec`.

**                           **:
1. `DEC:OPEN`     `EVT:ORDER_PLACED`        `EVT:FILL`
2. `DEC:CLOSE`     `EVT:CANCELLED`        `EVT:FILL` (reduce)
3. `DEC:ADJUST`                                 `CLOSE`        confusion

## API

### `compute_drift(decisions, events, time_window_sec=1.0) -> DriftReport`

                 drift                         decisions      events.

**Args**:
- `decisions`: List[Dict]     DEC messages (op="DEC", verb="OPEN"|"CLOSE")
- `events`: List[Dict]     EVT messages (op="EVT", verb="ORDER_PLACED"|"FILL"|"CANCELLED")
- `time_window_sec`: float     time window        matching (default: 1.0s)

**Returns**: `DriftReport`                :
- `confusion`: ConfusionMatrix (tp/fp/fn/tn, drift_pct, accuracy)
- `mismatches`: List[Mismatch] (                      5        /debug)
- `computed_at`: timestamp
- `records_processed`:                                                       

### `aggregate_drift_metrics(reports) -> Dict`

                            DriftReport    summary metrics        `/metrics`.

**Returns**:
```python
{
    "confusion_tp_total": int,
    "confusion_fp_total": int,
    "confusion_fn_total": int,
    "confusion_tn_total": int,
    "drift_pct_last": float,
    "accuracy_last": float,
}
```

## Integration

### /metrics Endpoint

                                                :
```python
from apps.reference.domains.execution_position.drift_monitor import aggregate_drift_metrics

# ...    /metrics handler:
drift_metrics = aggregate_drift_metrics(drift_reports)
metrics.update(drift_metrics)
```

### /debug/{rid} Endpoint

             `drift_report`              (       RBAC):
```python
from apps.reference.domains.execution_position.drift_monitor import compute_drift

# ...    /debug/{rid} handler:
if rid in drift_cache:
    drift_report = drift_cache[rid].to_dict()
    response["drift_report"] = drift_report
```

## Performance

**Off-path computation**:                                                     hot-path               .

**Benchmark**:
- 1k records: ~25ms (                )
- Memory: O(n)                             events      RID

## Testing

**Unit tests** (`test_drift_unit.py`): 9             , 100% PASS
- Perfect match (drift=0)
- Only decisions (all FP)
- Only events (all FN)
- Partial overlap (mixed TP/FP/FN)
- Time window validation
- Edge cases (empty matrix, serialization)

**E2E tests** (`test_drift_roundtrip.py`): 5             , 100% PASS
- Open flow roundtrip (DEC   EVT match)
- Manage flow (trail trigger, no match)
- Close flow (max_hold_sec trigger, match)
- Multiple symbols
- Report serialization for /debug

**Coverage**: 98% (drift_monitor.py), 90% (repo)

## Limitations (STOP-scope)

-     Only OPEN/CLOSE    confusion matrix
-     No real-time streaming                    
-     No                                 (                                              )
-     No                                         SDK (ACL-stub + WAL/fixtures)
-        TN=0 (requires baseline tracking)

## Future Enhancements (not in scope)

- [ ] Real-time drift alerts (Prometheus/Grafana)
- [ ] Multi-symbol confusion matrices
- [ ] Drift trend analysis (time-series)
- [ ] Integration with ML feature store
- [ ] Advanced matching (fuzzy time windows, order states)

## References

- **ADR-001**: WAL Format (       replay drift scenarios)
- **ADR-003**: RBAC Model (       /debug protection)
- **FSMP-P1-T02**: 3 FSM flows (OPEN/MANAGE/CLOSE)
- **FSMP-P0-T04**: TTL Cache (       drift_report caching)
