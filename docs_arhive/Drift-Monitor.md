# Drift Monitor — Shadow-Mode Validation (FSMP-P1-T03)

## Overview

Drift Monitor обчи� лює **drift%** та **confusion matrix** між тіньовими рішеннями FSM (DEC:OPEN/CLOSE) та фактичними подіями від біржі (EVT:ORDER_PLACED/FILL/CANCELLED).

**Призначення**: валідація shadow-mode FSM перед переведенням у hot-path production.

## Методологія

### Confusion Matrix

- **TP (True Positive)**: DEC:OPEN/CLOSE має відповідний EVT у time-window
- **FP (False Positive)**: DEC:OPEN/CLOSE без відповідного EVT
- **FN (False Negative)**: EVT без відповідного DEC (� амовільна подія)
- **TN (True Negative)**: періоди без DEC і без EVT (stub: TN=0)

### Drift Formula

```
drift_pct = (FP + FN) / (TP + FP + FN + TN) * 100
```

**Інтерпретація**:
- `drift_pct < 1%` → FSM ready for canary (10%)
- `drift_pct < 5%` → FSM needs minor tuning
- `drift_pct > 10%` → FSM needs major review

### Matching Rules

**Індек� ація**: по `RID` (primary key), `symbol` ігноруєть� я якщо від� утній у DEC.

**Time window**: ±1s (default), налаштовуєть� я через `time_window_sec`.

**Правила звірки**:
1. `DEC:OPEN` → `EVT:ORDER_PLACED` або `EVT:FILL`
2. `DEC:CLOSE` → `EVT:CANCELLED` або `EVT:FILL` (reduce)
3. `DEC:ADJUST` → трактуєть� я як `CLOSE` для confusion

## API

### `compute_drift(decisions, events, time_window_sec=1.0) -> DriftReport`

Обчи� лює drift між � пи� ками decisions та events.

**Args**:
- `decisions`: List[Dict] — DEC messages (op="DEC", verb="OPEN"|"CLOSE")
- `events`: List[Dict] — EVT messages (op="EVT", verb="ORDER_PLACED"|"FILL"|"CANCELLED")
- `time_window_sec`: float — time window для matching (default: 1.0s)

**Returns**: `DriftReport` з полями:
- `confusion`: ConfusionMatrix (tp/fp/fn/tn, drift_pct, accuracy)
- `mismatches`: List[Mismatch] (обмежено до 5 для /debug)
- `computed_at`: timestamp
- `records_processed`: кількі� ть оброблених запи� ів

### `aggregate_drift_metrics(reports) -> Dict`

Агрегує кілька DriftReport у summary metrics для `/metrics`.

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

Додати агреговані метрики:
```python
from apps.reference.domains.execution_position.drift_monitor import aggregate_drift_metrics

# ... у /metrics handler:
drift_metrics = aggregate_drift_metrics(drift_reports)
metrics.update(drift_metrics)
```

### /debug/{rid} Endpoint

Додати `drift_report` � екцію (під RBAC):
```python
from apps.reference.domains.execution_position.drift_monitor import compute_drift

# ... у /debug/{rid} handler:
if rid in drift_cache:
    drift_report = drift_cache[rid].to_dict()
    response["drift_report"] = drift_report
```

## Performance

**Off-path computation**: обчи� лення не виконують� я у hot-path роутера.

**Benchmark**:
- 1k records: ~25ms (локально)
- Memory: O(n) для індек� ації events по RID

## Testing

**Unit tests** (`test_drift_unit.py`): 9 те� тів, 100% PASS
- Perfect match (drift=0)
- Only decisions (all FP)
- Only events (all FN)
- Partial overlap (mixed TP/FP/FN)
- Time window validation
- Edge cases (empty matrix, serialization)

**E2E tests** (`test_drift_roundtrip.py`): 5 те� тів, 100% PASS
- Open flow roundtrip (DEC→EVT match)
- Manage flow (trail trigger, no match)
- Close flow (max_hold_sec trigger, match)
- Multiple symbols
- Report serialization for /debug

**Coverage**: 98% (drift_monitor.py), 90% (repo)

## Limitations (STOP-scope)

- ✅ Only OPEN/CLOSE в confusion matrix
- ✅ No real-time streaming або алерти
- ✅ No нових ендпоінтів (лише розширення і� нуючих)
- ✅ No підключення реальних SDK (ACL-stub + WAL/fixtures)
- ⚠️ TN=0 (requires baseline tracking)

## Future Enhancements (not in scope)

- [ ] Real-time drift alerts (Prometheus/Grafana)
- [ ] Multi-symbol confusion matrices
- [ ] Drift trend analysis (time-series)
- [ ] Integration with ML feature store
- [ ] Advanced matching (fuzzy time windows, order states)

## References

- **ADR-001**: WAL Format (для replay drift scenarios)
- **ADR-003**: RBAC Model (для /debug protection)
- **FSMP-P1-T02**: 3 FSM flows (OPEN/MANAGE/CLOSE)
- **FSMP-P0-T04**: TTL Cache (для drift_report caching)
