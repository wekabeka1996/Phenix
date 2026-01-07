# VOL-ADJ-GATES-01: Completion Report

**Date:** 2025-01-07  
**Status:** ✅ COMPLETE  
**Task:** Replace absolute % change with sigma-normalized motion gates for Aurora entries

---

## Summary

Implemented **Anti-Flat** and **Anti-FOMO** gates using sigma-normalized motion (`pm_norm`) from the `price_motion` feature domain.

### Gate Logic

| Gate | Condition | Reason | Action |
|------|-----------|--------|--------|
| Anti-Flat | `\|pm_norm\| < anti_flat_sigma` | Dead market → fee churn | Block ENTRY |
| Anti-FOMO | `\|pm_norm\| > anti_fomo_sigma` | Extreme impulse → snapback | Block ENTRY |

**Defaults:**
- `anti_flat_sigma: 0.5` (block if market dead)
- `anti_fomo_sigma: 4.0` (block if extreme impulse)
- `motion_window_sec: 900` (use 15-minute pm_norm)

---

## Phase Completion

### Phase 1: AUDIT ✅

- **Audit Report:** [reports/VOL-ADJ-GATES-01_AUDIT.md](VOL-ADJ-GATES-01_AUDIT.md)
- Found `price_motion.py` compute site
- Documented formula: `pm_norm = clip(ret_window / (k_vol * vol_window), -1, 1)`
- Identified 900s window missing → Phase 2

### Phase 2: Feature Support (pm_norm_900s) ✅

**Files Changed:**
- [apps/reference/domains/feature_engineering/price_motion.py](../apps/reference/domains/feature_engineering/price_motion.py)
  - Extended `windows_sec` tuple to include 900
  - Added keys: `ret_900s`, `vol_pct_900s`, `pm_norm_900s`

- [schemas/decision_trace_emitted_v1.json](../schemas/decision_trace_emitted_v1.json)
  - Added `pm_norm_900s` and `vol_pct_900s` fields

**Tests Created:**
- `tests/domains/feature_engineering/test_price_motion_math_v1.py` (+3 tests for 900s)

### Phase 3: Gate Implementation ✅

**Files Changed:**
- [apps/reference/domains/decision_making/aurora_handler.py](../apps/reference/domains/decision_making/aurora_handler.py)
  - Config loading: `vol_gates_enabled`, `anti_flat_sigma`, `anti_fomo_sigma`, `motion_window_sec`
  - `_get_motion_norm_sigma()`: Extract absolute motion sigma from features
  - `_apply_vol_adj_gates()`: Apply Anti-Flat/Anti-FOMO gates (entries only)
  - Integration in `on_features_calculated()` after re-entry cooldown

**Observability:**
- Counter: `aurora_vol_adj_gate_blocked_total{gate=anti_flat|anti_fomo}`
- Event: `EVT:AURORA_ENTRY_BLOCKED` with `reason_code`, `motion_sigma`, thresholds
- Log: INFO level with `[VOL-ADJ-GATE]` prefix

**Tests Created:**
- `tests/domains/decision_making/test_aurora_vol_adj_gates.py` (11 tests)
  - `TestAntiFlatGate` (2 tests)
  - `TestAntiFomoGate` (2 tests)
  - `TestGatePassThrough` (4 tests)
  - `TestGateDisabled` (1 test)
  - `TestBlockedEventDetails` (2 tests)

### Phase 4: Config Validation ✅

**Files Changed:**
- [apps/reference/config_models.py](../apps/reference/config_models.py)
  - Added `VolAdjGatesConfig` Pydantic model
  - Added `gates: Optional[VolAdjGatesConfig]` to `DecisionConfig`
  - Added `reentry_cooldown_sec` to `DecisionConfig` and `AuroraInstrumentConfig` (fix for pre-existing config)

- [config/aurora/strategies/aurora.yaml](../config/aurora/strategies/aurora.yaml)
  - Added `gates:` section with defaults

**Validation:**
```python
class VolAdjGatesConfig(BaseModel):
    enabled: bool = False
    anti_flat_sigma: float = 0.5   # ge=0.0, le=1.0
    anti_fomo_sigma: float = 4.0   # ge=1.0, le=10.0
    motion_window_sec: int = 900   # ge=10
```

---

## Test Results

```
pytest tests/domains/decision_making/test_aurora_vol_adj_gates.py \
       tests/domains/feature_engineering/test_price_motion_math_v1.py -v

======= 17 passed in 0.08s =======
```

**Full Suite:** 1186 passed, 49 skipped, 5 failed (pre-existing failures unrelated to VOL-ADJ-GATES)

---

## Config Example

```yaml
decision:
  gates:
    enabled: true
    anti_flat_sigma: 0.5   # Block ENTRY if |pm_norm| < 0.5
    anti_fomo_sigma: 4.0   # Block ENTRY if |pm_norm| > 4.0
    motion_window_sec: 900 # Use 15-minute window
```

---

## Usage Notes

1. **Entry-Only:** Gates do NOT affect exits, SL/TP, or risk management
2. **Missing Feature:** If `pm_norm_{window}s` is None (warmup), gate is skipped
3. **Disabled Config:** If `gates.enabled: false`, gate logic is bypassed
4. **Observability:** Check Prometheus counter `aurora_vol_adj_gate_blocked_total` for monitoring

---

## Files Modified (Summary)

| File | Changes |
|------|---------|
| `apps/reference/domains/feature_engineering/price_motion.py` | +900s window |
| `apps/reference/domains/decision_making/aurora_handler.py` | +gates logic (~100 LOC) |
| `apps/reference/config_models.py` | +VolAdjGatesConfig, +reentry_cooldown_sec |
| `config/aurora/strategies/aurora.yaml` | +gates section |
| `schemas/decision_trace_emitted_v1.json` | +pm_norm_900s, vol_pct_900s |
| `tests/domains/decision_making/test_aurora_vol_adj_gates.py` | NEW (11 tests) |
| `tests/domains/feature_engineering/test_price_motion_math_v1.py` | +3 tests |
| `reports/VOL-ADJ-GATES-01_AUDIT.md` | NEW (audit findings) |

---

**Sign-off:** VOL-ADJ-GATES-01 implemented per spec. Tests green. Ready for live testing.
