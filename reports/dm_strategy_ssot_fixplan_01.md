# DM-STRATEGY-SSOT-FIXPLAN-01

**Date**: 2026-01-13  
**Author**: Copilot Audit Agent  
**Status**: Ready for Implementation  

---

## 1. Current State (Facts with file:line)

### 1.1. Schema Enforcement Status

| Schema | File | Runtime Validation | Evidence |
|--------|------|-------------------|----------|
| `features_calculated_v1.json` | [features_calculated_v1.json](apps/reference/domains/feature_engineering/schemas/features_calculated_v1.json) | **NOT ENFORCED** at emit time | `FeatureEngineering` emits directly without `jsonschema.validate()` ([feature_engineering.py#L1019](apps/reference/domains/feature_engineering/feature_engineering.py#L1019)) |
| `cmd_process_strategy_v1.json` | [cmd_process_strategy_v1.json](apps/reference/domains/feature_engineering/schemas/cmd_process_strategy_v1.json) | **NOT ENFORCED** | CMD emission has no schema validation ([feature_engineering.py#L1129](apps/reference/domains/feature_engineering/feature_engineering.py#L1129)) |
| Pydantic contracts | [contracts.py](apps/reference/domains/feature_engineering/contracts.py) | Optional Pydantic models exist but NOT called in emit path | `validate_features_payload_v1()` exists but not invoked by FE |
| `order_logger_v1.json` | [order_logger.py](apps/reference/telemetry/order_logger.py) | **CONDITIONAL** (DEBUG/TEST only) | `jsonschema.validate()` only when `ENV in ("DEBUG", "TEST")` ([order_logger.py#L73](apps/reference/telemetry/order_logger.py#L73)) |

**Conclusion A**: JSON schemas are documentation-only; no runtime enforcement exists for FSM event payloads. The `additionalProperties=false` in `features_calculated_v1.json` would reject `bar` field, but **validation never runs**.

### 1.2. MR1: ATR Requirement Mismatch

**Gateway EntryPlan configuration**:
- `entry_plan.enabled=true` ([domains.yaml#L21](config/aurora/domains.yaml#L21))
- `entry_plan.require_atr=true` ([domains.yaml#L29](config/aurora/domains.yaml#L29))

**Gateway validation code**:
```python
# apps/reference/domains/decision_making/decision_making.py:979-984
volatility_data = pld.get("volatility") or {}
atr_ready = volatility_data.get("atr_ready", False)
```

**MR signal payload (missing volatility)**:
```python
# apps/reference/domains/decision_making/mean_reversion_handler.py:591-613
pld = {
    "schema_version": 1,
    "strategy_id": "mean_reversion",
    "symbol": symbol,
    ...
    "price_ctx": {...},
    # NO volatility/liquidity fields!
}
```

**Aurora signal payload (has volatility)**:
```python
# apps/reference/domains/decision_making/aurora_handler.py:1163
"volatility": features.get("volatility"),
"liquidity": features.get("liquidity"),
```

**Result**: MR signals always fail EntryPlan validation: `atr_ready=False` → `REJECT - EntryPlan validation failed` ([decision_making.py#L1007-L1031](apps/reference/domains/decision_making/decision_making.py#L1007)).

### 1.3. S1: Aurora price_motion Phantom

**Aurora vol-adj gates expect**:
```python
# apps/reference/domains/decision_making/aurora_handler.py:976
window_key = f"pm_norm_{self.motion_window_sec}s"  # pm_norm_900s
val = pm.get(window_key)
```

**Config sets 900s window**:
```yaml
# config/aurora/strategies/aurora.yaml:145
motion_window_sec: 900  # Use 15-minute window (pm_norm_900s)
```

**Schema only defines 10/60/300s**:
```json
// schemas/features_price_motion_v1.json:12-14
"pm_norm_10s": {...},
"pm_norm_60s": {...},
"pm_norm_300s": {...}
// NO pm_norm_900s!
```

**CMD payload doesn't include price_motion in features**:
```python
# apps/reference/domains/feature_engineering/feature_engineering.py:1129-1137
cmd_payload = {
    "symbol": symbol,
    "tf_sec": tf_sec,
    "bar": bar_data,
    "features": {...},  # NO price_motion here
    "warmup": warmup,
    "regime": regime_snapshot,
}
```

**Result**: `_get_motion_norm_sigma()` always returns `None` → gates silently skipped ([aurora_handler.py#L1019-L1022](apps/reference/domains/decision_making/aurora_handler.py#L1019)).

### 1.4. S2: Assignments SSOT Conflict

**Registry assigns DOGE/XRP to MR only**:
```yaml
# config/aurora/strategies.yaml:33-38
DOGEUSDT:
  - mean_reversion
XRPUSDT:
  - mean_reversion
```

**Aurora assets have DOGE/XRP enabled**:
```yaml
# config/aurora/strategies/aurora.yaml:320,385
DOGEUSDT:
  enabled: true
XRPUSDT:
  enabled: true
```

**AuroraHandler uses assets, not registry**:
```python
# apps/reference/domains/decision_making/aurora_handler.py:779-788
def _is_symbol_enabled(self, symbol: str) -> bool:
    aurora = getattr(self.config.strategies, "aurora", None)
    assets = getattr(aurora, "assets", {})
    if symbol not in assets:
        return False
    asset_cfg = assets[symbol]
    return bool(getattr(asset_cfg, "enabled", True))
```

**Result**: Aurora emits signals for DOGE/XRP → gateway arbitration blocks them with `ARBITRATION_BLOCKED` (noise in logs).

## 2. Breakpoints (Where It Breaks)

| ID | Location | Symptom | Root Cause |
|----|----------|---------|------------|
| BP1 | [decision_making.py#L1007](apps/reference/domains/decision_making/decision_making.py#L1007) | MR signals REJECTED | `pld.volatility` missing → `atr_ready=False` → EntryPlan fail |
| BP2 | [aurora_handler.py#L982](apps/reference/domains/decision_making/aurora_handler.py#L982) | Vol-adj gates always skip | `features.price_motion` missing in CMD; 900s window doesn't exist |
| BP3 | [aurora_handler.py#L506](apps/reference/domains/decision_making/aurora_handler.py#L506) | DOGE/XRP signals emitted | `_is_symbol_enabled()` checks assets, not registry assignments |
| BP4 | [decision_making.py#L1531](apps/reference/domains/decision_making/decision_making.py#L1531) | ARBITRATION_BLOCKED noise | Aurora emits for non-assigned symbols |
| BP5 | [feature_engineering.py#L1009](apps/reference/domains/feature_engineering/feature_engineering.py#L1009) | Schema drift | Payload includes `bar` but schema forbids it (not enforced) |

---

## 3. Fix Plan

### P0: Critical Fixes (Must for Production)

#### P0-1: MR Adds Volatility Snapshot to Signal Payload

**Rationale**: Minimal change. MR already receives `cmd.features.volatility` from FE. Just propagate it.

**Change**:
```python
# File: apps/reference/domains/decision_making/mean_reversion_handler.py
# Location: ~line 591 (in _emit_signal method)

# BEFORE:
pld = {
    "schema_version": 1,
    "strategy_id": "mean_reversion",
    ...
}

# AFTER:
pld = {
    "schema_version": 1,
    "strategy_id": "mean_reversion",
    ...
    # P0-1: Add volatility/liquidity for EntryPlan compatibility
    "volatility": cmd_features.get("volatility") if cmd_features else None,
    "liquidity": cmd_features.get("liquidity") if cmd_features else None,
}
```

**Risk**: Low. Field already exists in cmd; just propagating.  
**DoD**: MR signal → gateway → intent without EntryPlan rejection.  
**Test**: `test_mr_signal_passes_entry_plan_with_atr`

#### P0-2: Fix Aurora motion_window_sec to Valid Value

**Rationale**: Config mistake. 900s doesn't exist; use 300s (5m).

**Change**:
```yaml
# File: config/aurora/strategies/aurora.yaml
# Location: ~line 145

# BEFORE:
motion_window_sec: 900

# AFTER:
motion_window_sec: 300  # FIXED: Use valid 5m window (pm_norm_300s)
```

**Risk**: Low. Aligns config with schema. Gates will work.  
**DoD**: Vol-adj gates actually execute (no more silent skip).  
**Test**: `test_aurora_vol_adj_gates_use_300s_window`

#### P0-3: Inject price_motion into CMD:PROCESS_STRATEGY

**Rationale**: Aurora handler expects `cmd.features.price_motion` but it's only in EVT payload.

**Option A (Recommended)**: Change aurora_handler to read from cached EVT payload (not cmd.features).

**Option B**: FE injects `price_motion` into cmd.features (requires schema update).

**Recommended Change (Option A)**:
```python
# File: apps/reference/domains/decision_making/aurora_handler.py
# Method: _get_motion_norm_sigma

# BEFORE:
pm = features.get("price_motion")

# AFTER:
# P0-3: Fall back to symbol_state cache if not in features
pm = features.get("price_motion")
if not pm:
    state = self._symbol_states.get(symbol)
    if state:
        pm = getattr(state, "_cached_price_motion", None)
```

Plus cache price_motion from EVT:FEATURES_CALCULATED:
```python
# In _on_features_calculated handler
state._cached_price_motion = pld.get("price_motion")
```

**Risk**: Medium. Adds state dependency.  
**DoD**: Vol-adj gates see pm_norm_300s from cache.  
**Test**: `test_aurora_vol_adj_gates_work_with_cached_price_motion`

### P1: Important Fixes

#### P1-1: Aurora Handler Uses Registry for Symbol Check

**Change**:
```python
# File: apps/reference/domains/decision_making/aurora_handler.py
# Method: _is_symbol_enabled (replace or augment)

def _is_symbol_enabled(self, symbol: str) -> bool:
    # P1-1: SSOT is registry assignments, not aurora.assets
    if hasattr(self.config, 'strategies_registry') and self.config.strategies_registry:
        assignments = self.config.strategies_registry.assignments or {}
        if symbol not in assignments:
            return False
        if "aurora" not in assignments[symbol]:
            return False
    
    # Then check aurora.assets.enabled as kill-switch
    aurora = getattr(self.config.strategies, "aurora", None)
    if not aurora:
        return False
    assets = getattr(aurora, "assets", {})
    if symbol not in assets:
        return False
    return bool(getattr(assets[symbol], "enabled", True))
```

**Risk**: Medium. Changes activation logic.  
**DoD**: No ARBITRATION_BLOCKED noise for DOGE/XRP.  
**Test**: `test_aurora_respects_registry_assignments`

#### P1-2: Update features_calculated Schema to Include bar

**Change**:
```json
// File: apps/reference/domains/feature_engineering/schemas/features_calculated_v1.json
// Add bar property before additionalProperties

"bar": {
  "description": "Raw OHLCV bar data (may be null for tick-level features)",
  "anyOf": [
    {"type": "object"},
    {"type": "null"}
  ]
}
```

**Risk**: Low. Schema now matches reality.  
**DoD**: Schema validation (if enabled) doesn't reject bar field.  
**Test**: Contract test with bar field.

### P2: Technical Debt

#### P2-2: Remove Unused aurora.assets for MR-only symbols

**Change**:
```yaml
# File: config/aurora/strategies/aurora.yaml
# Comment out or remove DOGEUSDT/XRPUSDT blocks (they're MR-only)
```

**Risk**: Low. Cleanup only.

---

## 4. PR-Style Diff List

### Diff 1: P0-1 (MR volatility propagation)

**File**: `apps/reference/domains/decision_making/mean_reversion_handler.py`  
**Lines**: 591-613  
**Action**: Add `volatility` and `liquidity` to signal payload  

```diff
         pld = {
             "schema_version": 1,
             "strategy_id": "mean_reversion",
             "symbol": symbol,
             "tf_sec": self.timeframe_sec,
             "side": side,
             "readiness": {"warmup_ok": True},
             "score": float(signal.confidence),
             "why": signal.why,
             "ts_ms": int(signal.timestamp_ms),
             "rid": rid,
             "why_chain": [signal.why],
             "price_ctx": {
                 "entry_price": str(signal.entry_price),
                 "stop_price": str(signal.stop_price) if signal.stop_price else None,
                 "target_price": str(signal.target_price) if signal.target_price else None,
             },
             "regime": signal.flat_regime.name if signal.flat_regime else "UNKNOWN",
+            # P0-1: Propagate volatility/liquidity for EntryPlan compatibility
+            "volatility": self._last_cmd_features.get("volatility") if self._last_cmd_features else None,
+            "liquidity": self._last_cmd_features.get("liquidity") if self._last_cmd_features else None,
             "mr_params": {
                 "sizing_mult": float(signal.mr_params.sizing_mult) if signal.mr_params else 1.0,
                 "stop_mult": float(signal.mr_params.stop_mult) if signal.mr_params else 1.0,
                 "target_mult": float(signal.mr_params.target_mult) if signal.mr_params else 1.0,
             },
         }
```

Also need to store cmd.features in handler:
```diff
# In _on_process_strategy, after extracting cmd:
+        self._last_cmd_features = cmd.get("features", {})
```

### Diff 2: P0-2 (Fix motion_window_sec)

**File**: `config/aurora/strategies/aurora.yaml`  
**Lines**: 145  

```diff
       gates:
         enabled: true
         anti_flat_sigma: 0.5
         anti_fomo_sigma: 4.0
-        motion_window_sec: 900
+        motion_window_sec: 300  # FIXED: Use valid 5m window
```

### Diff 3: P1-1 (Aurora registry check)

**File**: `apps/reference/domains/decision_making/aurora_handler.py`  
**Lines**: 779-788  

```diff
     def _is_symbol_enabled(self, symbol: str) -> bool:
         """Check if symbol is enabled for Aurora strategy."""
+        # P1-1: SSOT is registry assignments
+        if hasattr(self.config, 'strategies_registry') and self.config.strategies_registry:
+            assignments = getattr(self.config.strategies_registry, 'assignments', {}) or {}
+            if symbol not in assignments or "aurora" not in assignments.get(symbol, []):
+                return False
+        
         aurora = getattr(self.config.strategies, "aurora", None)
         if not aurora:
             return False
         assets = getattr(aurora, "assets", {})
         if symbol not in assets:
             return False
         asset_cfg = assets[symbol]
         return bool(getattr(asset_cfg, "enabled", True))
```

---

## 5. Test Package

### Test 1: MR signal → gateway → intent (no ATR conflict)

**File**: `tests/domains/decision_making/test_mr_entry_plan_compatibility.py`

```python
"""
Test: MR signal passes gateway EntryPlan when volatility is propagated.
DoD for P0-1.
"""
import pytest
from unittest.mock import MagicMock, patch
from decimal import Decimal

def test_mr_signal_passes_entry_plan_with_atr():
    """
    Given: MR handler emits signal with volatility snapshot
    When: Gateway processes signal with entry_plan.require_atr=true
    Then: Signal passes (no EntryPlan rejection)
    """
    # Setup mock config
    config = MagicMock()
    config.domains.decision_making.entry_plan.enabled = True
    config.domains.decision_making.entry_plan.require_atr = True
    
    # Mock signal with volatility
    signal_payload = {
        "strategy_id": "mean_reversion",
        "symbol": "DOGEUSDT",
        "side": "BUY",
        "readiness": {"warmup_ok": True},
        "price_ctx": {"entry_price": "0.12345"},
        "ts_ms": 1704067200000,
        "rid": "test_rid",
        "volatility": {
            "atr_14": 0.00123,
            "atr_ready": True,
        },
        "liquidity": {"obi_close": "0.05"},
    }
    
    # Expected: EntryPlan.validate_inputs returns (True, None)
    with patch('apps.reference.domains.decision_making.decision_making.EntryPlan') as MockEP:
        MockEP.validate_inputs.return_value = (True, None)
        # ... gateway invocation would pass
        MockEP.validate_inputs.assert_called_with(
            side="BUY",
            ref_price=pytest.approx(Decimal("0.12345")),
            atr=0.00123,
            atr_ready=True,
            params=pytest.ANY,
        )
```

### Test 2: Aurora signal → gateway → intent (no phantom price_motion)

**File**: `tests/domains/decision_making/test_aurora_vol_adj_gates_fixed.py`

```python
"""
Test: Aurora vol-adj gates work with correct 300s window.
DoD for P0-2 and P0-3.
"""
import pytest

def test_aurora_vol_adj_gates_use_300s_window():
    """
    Given: Config motion_window_sec=300
    And: features contain pm_norm_300s=0.8
    When: _get_motion_norm_sigma is called
    Then: Returns 0.8 (not None)
    """
    from apps.reference.domains.decision_making.aurora_handler import AuroraHandler
    from unittest.mock import MagicMock
    
    handler = MagicMock(spec=AuroraHandler)
    handler.motion_window_sec = 300
    
    features = {
        "price_motion": {
            "pm_norm_300s": 0.8,
        }
    }
    
    # Direct method test
    result = AuroraHandler._get_motion_norm_sigma(handler, "BTCUSDT", features)
    assert result == 0.8


def test_aurora_gates_not_silent_skip():
    """
    Given: motion_norm_sigma is available (0.8)
    And: anti_flat_sigma=0.5, anti_fomo_sigma=4.0
    When: _apply_vol_adj_gates is called for entry
    Then: Gate evaluates (returns False = passed)
    """
    # ... implementation
    pass
```

### Test 3: Assigned symbols only (Aurora doesn't emit for non-assigned)

**File**: `tests/domains/decision_making/test_aurora_respects_registry.py`

```python
"""
Test: Aurora doesn't emit signals for symbols not assigned in registry.
DoD for P1-1.
"""
import pytest
from unittest.mock import MagicMock

def test_aurora_respects_registry_assignments():
    """
    Given: DOGEUSDT assigned to mean_reversion only in strategies.yaml
    And: DOGEUSDT.enabled=true in aurora.assets
    When: Aurora handler checks _is_symbol_enabled("DOGEUSDT")
    Then: Returns False (registry takes precedence)
    """
    from apps.reference.domains.decision_making.aurora_handler import AuroraHandler
    
    config = MagicMock()
    config.strategies_registry.assignments = {
        "DOGEUSDT": ["mean_reversion"],  # NOT aurora
        "BTCUSDT": ["aurora"],
    }
    config.strategies.aurora.assets = {
        "DOGEUSDT": MagicMock(enabled=True),
        "BTCUSDT": MagicMock(enabled=True),
    }
    
    handler = MagicMock(spec=AuroraHandler)
    handler.config = config
    
    # After fix, DOGE should be disabled for aurora
    result = AuroraHandler._is_symbol_enabled(handler, "DOGEUSDT")
    assert result is False
    
    # BTC should be enabled
    result = AuroraHandler._is_symbol_enabled(handler, "BTCUSDT")
    assert result is True


def test_no_arbitration_blocked_noise_for_mr_only_symbols():
    """
    Given: Aurora respects registry
    When: Processing bar for DOGEUSDT
    Then: No EVT:STRATEGY_SIGNAL_PRODUCED emitted
    And: No ARBITRATION_BLOCKED logs
    """
    # ... integration test
    pass
```

---

## 6. Runbook: How to Verify on Live System

### Pre-Deployment Checks

```bash
# 1. Run all DM strategy tests
pytest tests/domains/decision_making/ -v -k "mr_entry_plan or aurora_vol_adj or registry"

# 2. Validate config
python -m vfoundation.cli.vfound dict validate --report ops/reports/dict_validate.json

# 3. Check verb registry consistency
pytest -q tests/vfoundation/test_verb_registry_warn_only.py
```

### Live System Monitoring

**Logs to watch**:
```bash
# MR signals passing gateway (should see EntryPlan success)
grep "EntryPlan:" logs/aurora_core.log | grep "mean_reversion"

# No more ARBITRATION_BLOCKED for DOGE/XRP
grep "ARBITRATION_BLOCKED" logs/aurora_core.log | grep -E "DOGE|XRP"
# Expected: 0 results after fix

# Vol-adj gates actually executing (not skipping)
grep "VOL_GATES:" logs/aurora_core.log
# Expected: "passed" or "Blocking entry" (not "skipping")
```

**Metrics to check**:
```python
# Counter: strategy_signals_rejected_total{reason="ENTRY_PLAN_VALIDATION_FAILED"}
# Expected: Near-zero for mean_reversion after fix

# Counter: arbitration_blocked_total{strategy="aurora", symbol=~"DOGE|XRP"}
# Expected: Zero after P1-1 fix
```

### Rollback Triggers

- MR signals consistently REJECTED after fix → Rollback P0-1
- Aurora gate false-positives (too many blocks) → Adjust anti_flat_sigma threshold
- Config validation fails → Check motion_window_sec value

---

## 7. Summary

| Priority | Fix ID | Description | Risk | Files Changed |
|----------|--------|-------------|------|---------------|
| P0 | P0-1 | MR adds volatility to signal | Low | mean_reversion_handler.py |
| P0 | P0-2 | Fix motion_window_sec 900→300 | Low | aurora.yaml |
| P0 | P0-3 | Cache price_motion for aurora | Medium | aurora_handler.py |
| P1 | P1-1 | Aurora uses registry for symbols | Medium | aurora_handler.py |
| P1 | P1-2 | Update schema to include bar | Low | features_calculated_v1.json |
| P2 | P2-2 | Remove unused aurora.assets | Low | aurora.yaml |

**Total files changed**: 5  
**Total lines changed**: ~50  
**Risk assessment**: Low-Medium (mostly additive, no breaking changes)

---

*Generated by DM-STRATEGY-SSOT-AUDIT-01*
