# FSMP-P2-T07: Soft-limit Clipping, Risk Profiles, Idempotent Cancellations

**Session**: 7 November 2025
**Status**: 🚀 **PHASE 2 IN PROGRESS - Foundation Complete**
**Branch**: Test_MyPC

---

## 🎯 Objective

Implement **balanced risk management** with soft-limit order clipping, regime-adaptive directional ratios, and robust idempotent cancellation handling. Replace hard rejections with intelligent size reduction where safe.

---

## 📊 Design Overview

### PHASE 1: Configuration (✅ COMPLETE)

**File**: `config/aurora/trading.yaml`

#### Balanced Profile - Default Settings
```yaml
risk:
  profile: "balanced"
  soft_limits:
    mode: "clip"                         # Soft-limit clipping enabled
    clip_min_notional_usdt: 10           # Minimum after clipping
    directional_ratio_max: 3.0           # Base ratio (with regime adaptation)
    side_exposure_usdt: 600              # Per-side limit
    margin_exposure_usdt: 1100           # Total margin limit

  regime_adaptation:
    trend_up_delta: 0.30                 # +0.30 in uptrends
    trend_down_delta: 0.30               # +0.30 in downtrends
    flat_delta: -0.30                    # -0.30 in flat markets
    bounds: [2.0, 4.0]                   # Clamp to [min, max]

  feature_flags:
    dynamic_ratio: true
    clipping_enabled: true

trading:
  decision:
    neutral_threshold: 0.18              # Signal threshold for neutral market

execution:
  orders:
    default_ttl_seconds: 15              # Order time-to-live
    market:
      slippage_cap_bps: 10               # Slippage tolerance
    cancel:
      idempotent: true                   # Idempotent retry on -2011
      use_cancel_replace: true           # Use cancelReplace where supported
```

**Impact**: System now has higher risk tolerance on testnet (200% utilization) + framework for fine-grained control.

---

### PHASE 2: Soft-Clip Logic (🔧 FOUNDATION)

**New File**: `apps/reference/domains/execution_position/soft_clip.py`

#### Components

1. **SoftLimitConfig** (dataclass)
   - Configuration holder for all soft-limit thresholds
   - Loaded from `trading.risk.soft_limits`
   - Defaults: clip_min=10, dir_ratio_max=3.0, side_exp=600, margin_exp=1100

2. **ClipResult** (dataclass)
   - Result container: `allowed`, `reason`, `clipped_notional`, `clip_reasons`
   - Tracks why order was clipped (margin/side/directional)

3. **SoftClipEngine** (class)
   - Core clipping logic: calculates ΔV_margin, ΔV_side, ΔV_directional
   - Formula: V_new = min(V_req, ΔV_margin, ΔV_side, ΔV_directional)
   - Returns ClipResult with clipped size or rejection (below min)

#### Next: Integration with exposure_guard.py

- Import SoftClipEngine in `can_open()` method
- When NRR-011/012/013 would be triggered:
  1. Calculate clipped_notional using SoftClipEngine
  2. If >= clip_min: return allowed=True with clipped_notional
  3. Else: return allowed=False (reject with original NRR code)
- Log CLIPPED_* events to order_logger

**Timeline**: Integration in next session (Phase 3 activation).

---

### PHASE 3: Regime Adaptation (📋 TODO)

**File**: `apps/reference/domains/regime_detector/regime_detector.py` + `exposure_guard.py`

**Logic**:
1. RegimeDetector emits EVT:REGIME_CHANGED with regime type
2. ExposureGuard subscribes and updates `directional_ratio_max`:
   - HIGH_VOLATILITY / TREND_UP / TREND_DOWN → +0.30 (more lenient)
   - FLAT / UNCERTAIN → -0.30 (stricter)
   - Clamp to [2.0, 4.0]
3. Re-evaluate pending orders in queue with new ratio

**Example**:
```
Regime: TREND_UP → directional_ratio_max = 3.0 + 0.30 = 3.30
Regime: FLAT → directional_ratio_max = 3.0 - 0.30 = 2.70
```

---

### PHASE 4: Idempotent Cancellations (📋 TODO)

**Files**:
- `apps/reference/domains/execution_position/binance_execution_adapter.py`
- `vfoundation/adapters/binance_adapter.py`

**Implementation**:
1. **Stable clientOrderId**: Deterministic prefix + timestamp/counter
2. **Pre-cancel check**: Call getOrder before cancel
   - If status not NEW/PARTIALLY_FILLED → already handled (return success)
   - Else → cancel normally
3. **-2011 handling**: If "Unknown order" error
   - Treat as successful cancellation (order missing = already gone)
   - Log as "IDEMPOTENT_CANCEL_-2011_ABSORBED"
4. **cancelReplace**: Use where supported (Binance Futures)
   - Atomic: cancel + new in one RPC

**Benefits**:
- No timeout errors from retried cancellations
- Network reliability improved (safe retry semantics)
- Fewer orphaned orders due to cancel failures

---

### PHASE 5: Metrics & Observability (📋 TODO)

**New Metrics in logs**:
```
risk.clip.count                          # Total clips
risk.clip.notional_total                 # Total notional reduced
risk.reject.count                        # Total rejections
orders.cancel.idempotent_ok              # Successful idempotent cancels
orders.cancel.-2011_absorbed             # -2011 treated as success
```

**Integration**: `tools/metrics_summary.py` pulls these from structured logs

---

### PHASE 6: Tests (📋 TODO)

**Test Coverage**:
1. `tests/unit/test_soft_clip_engine.py` (NEW)
   - Test SoftClipEngine.calculate_clipped_size() with various scenarios
   - Edge cases: below clip_min, ratio violations, all constraints active

2. `tests/unit/test_risk_gate_reasons.py` (UPDATE)
   - Add clip test cases for NRR-011/012/013
   - Verify clip_min threshold enforcement

3. `tests/test_risk_validation.py` (UPDATE)
   - Load new config keys
   - Verify regime adaptation updates ratio correctly

4. `tests/units/test_idempotent_cancel.py` (NEW)
   - Mock -2011 error, verify absorption
   - Verify pre-cancel getOrder call

5. `tests/units/test_manage_flow_fsm_oco.py` (REGRESSION)
   - Ensure no side effects from new soft-clip logic

---

## 📁 File Changes Summary

### Modified
- ✅ `config/aurora/trading.yaml` - Balanced profile + soft-limits config
- 🔧 `apps/reference/domains/execution_position/exposure_guard.py` - Load soft_limit_config (partial)

### Created
- ✅ `apps/reference/domains/execution_position/soft_clip.py` - SoftClipEngine & ClipResult

### To Create (Next Session)
- `tests/unit/test_soft_clip_engine.py`
- `tests/units/test_idempotent_cancel.py`

---

## 🧪 Current Test Status

**Regression**: All existing tests should pass unchanged (soft-clip is opt-in)

```bash
pytest -xvs tests/ -k "not slow"
```

---

## 📈 Expected Outcomes

- **Fewer NRR-011/012/013 rejections**: ~60-70% fewer hard rejections
- **Clipped order logs**: 20-30% of orders clip at least one dimension
- **Higher throughput**: More orders execute (albeit smaller size)
- **Stable cancellations**: No -2011 cascade failures

---

## 🔗 Related Issues

- **FSMP-P2-T06**: Orphan cleanup + timeout fixes (prerequisite)
- **Aurora Core**: Risk-first execution model
- **vFoundation**: FSM event propagation for regime signals

---

## 📝 Notes

- **Backward compatible**: Old configs work with defaults (clip_min=10, ratio_max=3.0)
- **No API changes**: Existing `can_open()` signature unchanged
- **Gradual rollout**: Soft-clip is opt-in per profile
- **Future**: Conservative/Accelerated profiles in separate configs

---

**Next Action**: Integrate SoftClipEngine in `exposure_guard.can_open()` (Phase 3)
