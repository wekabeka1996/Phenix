# Drift Monitor ‚ î Shadow-Mode Validation (FSMP-P1-T03)

## Overview

Drift Monitor  æ ± á ∏   ª é î **drift%**  Ç   **confusion matrix**  º ñ ∂  Ç ñ Ω å æ ≤ ∏ º ∏    ñ à µ Ω Ω è º ∏ FSM (DEC:OPEN/CLOSE)  Ç    Ñ   ∫ Ç ∏ á Ω ∏ º ∏    æ ¥ ñ è º ∏  ≤ ñ ¥  ± ñ   ∂ ñ (EVT:ORDER_PLACED/FILL/CANCELLED).

** ü   ∏ ∑ Ω   á µ Ω Ω è**:  ≤   ª ñ ¥   Ü ñ è shadow-mode FSM    µ   µ ¥    µ   µ ≤ µ ¥ µ Ω Ω è º  É hot-path production.

##  ú µ Ç æ ¥ æ ª æ ≥ ñ è

### Confusion Matrix

- **TP (True Positive)**: DEC:OPEN/CLOSE  º   î  ≤ ñ ¥   æ ≤ ñ ¥ Ω ∏ π EVT  É time-window
- **FP (False Positive)**: DEC:OPEN/CLOSE  ± µ ∑  ≤ ñ ¥   æ ≤ ñ ¥ Ω æ ≥ æ EVT
- **FN (False Negative)**: EVT  ± µ ∑  ≤ ñ ¥   æ ≤ ñ ¥ Ω æ ≥ æ DEC (     º æ ≤ ñ ª å Ω      æ ¥ ñ è)
- **TN (True Negative)**:    µ   ñ æ ¥ ∏  ± µ ∑ DEC  ñ  ± µ ∑ EVT (stub: TN=0)

### Drift Formula

```
drift_pct = (FP + FN) / (TP + FP + FN + TN) * 100
```

** Ü Ω Ç µ       µ Ç   Ü ñ è**:
- `drift_pct < 1%` ‚Üí FSM ready for canary (10%)
- `drift_pct < 5%` ‚Üí FSM needs minor tuning
- `drift_pct > 10%` ‚Üí FSM needs major review

### Matching Rules

** Ü Ω ¥ µ ∫     Ü ñ è**:    æ `RID` (primary key), `symbol`  ñ ≥ Ω æ   É î Ç å   è  è ∫ â æ  ≤ ñ ¥   É Ç Ω ñ π  É DEC.

**Time window**: ¬±1s (default),  Ω   ª   à Ç æ ≤ É î Ç å   è  á µ   µ ∑ `time_window_sec`.

** ü     ≤ ∏ ª    ∑ ≤ ñ   ∫ ∏**:
1. `DEC:OPEN` ‚Üí `EVT:ORDER_PLACED`    ± æ `EVT:FILL`
2. `DEC:CLOSE` ‚Üí `EVT:CANCELLED`    ± æ `EVT:FILL` (reduce)
3. `DEC:ADJUST` ‚Üí  Ç     ∫ Ç É î Ç å   è  è ∫ `CLOSE`  ¥ ª è confusion

## API

### `compute_drift(decisions, events, time_window_sec=1.0) -> DriftReport`

 û ± á ∏   ª é î drift  º ñ ∂      ∏   ∫   º ∏ decisions  Ç   events.

**Args**:
- `decisions`: List[Dict] ‚ î DEC messages (op="DEC", verb="OPEN"|"CLOSE")
- `events`: List[Dict] ‚ î EVT messages (op="EVT", verb="ORDER_PLACED"|"FILL"|"CANCELLED")
- `time_window_sec`: float ‚ î time window  ¥ ª è matching (default: 1.0s)

**Returns**: `DriftReport`  ∑    æ ª è º ∏:
- `confusion`: ConfusionMatrix (tp/fp/fn/tn, drift_pct, accuracy)
- `mismatches`: List[Mismatch] ( æ ± º µ ∂ µ Ω æ  ¥ æ 5  ¥ ª è /debug)
- `computed_at`: timestamp
- `records_processed`:  ∫ ñ ª å ∫ ñ   Ç å  æ ±   æ ± ª µ Ω ∏ Ö  ∑     ∏   ñ ≤

### `aggregate_drift_metrics(reports) -> Dict`

 ê ≥   µ ≥ É î  ∫ ñ ª å ∫   DriftReport  É summary metrics  ¥ ª è `/metrics`.

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

 î æ ¥   Ç ∏    ≥   µ ≥ æ ≤   Ω ñ  º µ Ç   ∏ ∫ ∏:
```python
from apps.reference.domains.execution_position.drift_monitor import aggregate_drift_metrics

# ...  É /metrics handler:
drift_metrics = aggregate_drift_metrics(drift_reports)
metrics.update(drift_metrics)
```

### /debug/{rid} Endpoint

 î æ ¥   Ç ∏ `drift_report`    µ ∫ Ü ñ é (   ñ ¥ RBAC):
```python
from apps.reference.domains.execution_position.drift_monitor import compute_drift

# ...  É /debug/{rid} handler:
if rid in drift_cache:
    drift_report = drift_cache[rid].to_dict()
    response["drift_report"] = drift_report
```

## Performance

**Off-path computation**:  æ ± á ∏   ª µ Ω Ω è  Ω µ  ≤ ∏ ∫ æ Ω É é Ç å   è  É hot-path    æ É Ç µ    .

**Benchmark**:
- 1k records: ~25ms ( ª æ ∫   ª å Ω æ)
- Memory: O(n)  ¥ ª è  ñ Ω ¥ µ ∫     Ü ñ ó events    æ RID

## Testing

**Unit tests** (`test_drift_unit.py`): 9  Ç µ   Ç ñ ≤, 100% PASS
- Perfect match (drift=0)
- Only decisions (all FP)
- Only events (all FN)
- Partial overlap (mixed TP/FP/FN)
- Time window validation
- Edge cases (empty matrix, serialization)

**E2E tests** (`test_drift_roundtrip.py`): 5  Ç µ   Ç ñ ≤, 100% PASS
- Open flow roundtrip (DEC‚ÜíEVT match)
- Manage flow (trail trigger, no match)
- Close flow (max_hold_sec trigger, match)
- Multiple symbols
- Report serialization for /debug

**Coverage**: 98% (drift_monitor.py), 90% (repo)

## Limitations (STOP-scope)

- ‚úÖ Only OPEN/CLOSE  ≤ confusion matrix
- ‚úÖ No real-time streaming    ± æ    ª µ   Ç ∏
- ‚úÖ No  Ω æ ≤ ∏ Ö  µ Ω ¥   æ ñ Ω Ç ñ ≤ ( ª ∏ à µ    æ ∑ à ∏   µ Ω Ω è  ñ   Ω É é á ∏ Ö)
- ‚úÖ No    ñ ¥ ∫ ª é á µ Ω Ω è    µ   ª å Ω ∏ Ö SDK (ACL-stub + WAL/fixtures)
- ‚ö†Ô∏è TN=0 (requires baseline tracking)

## Future Enhancements (not in scope)

- [ ] Real-time drift alerts (Prometheus/Grafana)
- [ ] Multi-symbol confusion matrices
- [ ] Drift trend analysis (time-series)
- [ ] Integration with ML feature store
- [ ] Advanced matching (fuzzy time windows, order states)

## References

- **ADR-001**: WAL Format ( ¥ ª è replay drift scenarios)
- **ADR-003**: RBAC Model ( ¥ ª è /debug protection)
- **FSMP-P1-T02**: 3 FSM flows (OPEN/MANAGE/CLOSE)
- **FSMP-P0-T04**: TTL Cache ( ¥ ª è drift_report caching)
