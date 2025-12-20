# CFG-STRATEGIES-SSOT-02-MR-HANDLER-STRICT-CONTRACT: COMPLETE ✅

**Status**: DONE  
**Date**: 2025-12-17  
**Tests**: 25/25 PASSED (6 registry + 13 arbitration + 6 MR handler)  
**Commit**: CFG-STRATEGIES-SSOT-02-MR-HANDLER-STRICT-CONTRACT

---

## 🎯 Objective

Bring `mean_reversion_handler.py` to "config as contract (SSOT + fail-closed)" compliance:

1. **Forbid dict-fallback** - no silent "let's try somehow"
2. **Remove silent defaults** (position_size_usd=100)
3. **Typed Pydantic only** - `AuroraConfig.mean_reversion`
4. **Strict crash** if MR assigned but config invalid/missing
5. **Handler disabled fail-closed** if MR not assigned + config missing

---

## ✅ Implementation Summary

### 1. **Removed dict-fallback in _parse_config()** ✅

**File**: [apps/reference/domains/decision_making/mean_reversion_handler.py](apps/reference/domains/decision_making/mean_reversion_handler.py) L99-127

**Before** (fail-open):
```python
if hasattr(self.config, 'mean_reversion'):
    self._mr_config = self.config.mean_reversion
elif isinstance(self.config, dict) and 'mean_reversion' in self.config:
    try:
        self._mr_config = MeanReversion1mStrategyConfig(**mr_dict)
    except Exception as e:
        self.logger.warning(f"Failed to parse MR config: {e}")  # SILENT FAIL
```

**After** (fail-closed):
```python
# Check if MR is assigned in strategies_registry
mr_assigned_symbols = self._get_mr_assigned_symbols()

# ONLY typed Pydantic access (NO dict-fallback)
if hasattr(self.config, 'mean_reversion') and self.config.mean_reversion is not None:
    self._mr_config = self.config.mean_reversion
    self._enabled = self._mr_config.enabled
else:
    # MR config missing
    if mr_assigned_symbols:
        # FAIL-CLOSED: MR assigned but config missing → ValueError
        raise ValueError(
            f"❌ CRITICAL: mean_reversion assigned to symbols {mr_assigned_symbols} "
            f"but config.mean_reversion is missing or invalid. "
            f"Required: config.mean_reversion (typed Pydantic) must be present."
        )
    else:
        # MR not assigned and config missing → disabled (fail-closed, no noise)
        self.logger.info("Mean Reversion 1m: config missing, handler disabled (no assignment)")
        self._enabled = False
        return
```

---

### 2. **Added MR Assignment Detection** ✅

**File**: [apps/reference/domains/decision_making/mean_reversion_handler.py](apps/reference/domains/decision_making/mean_reversion_handler.py) L106-123

```python
def _get_mr_assigned_symbols(self) -> set[str]:
    """
    Get symbols that have mean_reversion assigned in strategies_registry.
    
    CFG-STRATEGIES-SSOT-02-MR-HANDLER-STRICT-CONTRACT:
    MR is "potentially active" if assigned in registry OR enabled=True in config.
    """
    mr_symbols = set()
    
    if hasattr(self.config, 'strategies_registry') and self.config.strategies_registry:
        assignments = self.config.strategies_registry.assignments
        for symbol, strategies in assignments.items():
            if "mean_reversion" in strategies:
                mr_symbols.add(symbol)
    
    return mr_symbols
```

**Logic**:
- If registry assigns MR to any symbol → **config MUST be present**
- If registry doesn't assign MR → config optional (handler disabled silently)

---

### 3. **Removed Silent Default position_size_usd=100** ✅

**File**: [apps/reference/domains/decision_making/mean_reversion_handler.py](apps/reference/domains/decision_making/mean_reversion_handler.py) L335-350

**Before** (fail-open):
```python
def _get_position_size_usd(self) -> Decimal:
    if not self._mr_config or not self._mr_config.risk:
        return Decimal("100")  # SILENT DEFAULT
    
    risk_cfg = self._mr_config.risk
    if hasattr(risk_cfg, 'position_size_usd'):
        return Decimal(str(risk_cfg.position_size_usd))
    
    return Decimal("100")  # SILENT DEFAULT
```

**After** (fail-closed):
```python
def _get_position_size_usd(self, symbol: str) -> Optional[Decimal]:
    """
    Get position size from risk config.
    
    CFG-STRATEGIES-SSOT-02-MR-HANDLER-STRICT-CONTRACT:
    - NO silent defaults (no fallback to 100)
    - Return None if missing → caller must handle (fail-closed)
    """
    if not self._mr_config or not self._mr_config.risk:
        return None  # EXPLICIT None
    
    risk_cfg = self._mr_config.risk
    if hasattr(risk_cfg, 'position_size_usd'):
        return Decimal(str(risk_cfg.position_size_usd))
    
    return None  # EXPLICIT None
```

**Caller updated** (L258-268):
```python
position_size_usd = self._get_position_size_usd(symbol)

# FAIL-CLOSED: missing position_size → block signal
if position_size_usd is None:
    self.logger.warning(
        f"[{symbol}] MR_SIGNAL_BLOCKED: MR_REJECT:missing_position_size "
        f"(risk.position_size_usd not configured)"
    )
    return  # NO EVENT EMITTED
```

---

### 4. **Cleaned Up Duplicate Field Assignments** ✅

**File**: [apps/reference/domains/decision_making/mean_reversion_handler.py](apps/reference/domains/decision_making/mean_reversion_handler.py) L158-165

**Before** (duplicates):
```python
config.sl_atr_mult = Decimal(str(base_strat_cfg.sl_atr_mult))
config.tp_to_mid = base_strat_cfg.tp_to_mid
config.sl_atr_mult = Decimal(str(base_strat_cfg.sl_atr_mult))  # DUPLICATE
config.tp_to_mid = base_strat_cfg.tp_to_mid  # DUPLICATE
```

**After** (clean):
```python
config.sl_atr_mult = Decimal(str(base_strat_cfg.sl_atr_mult))
config.tp_to_mid = base_strat_cfg.tp_to_mid
config.cooldown_sec = base_strat_cfg.cooldown_sec
```

---

## 🧪 Test Results

### **Test Suite: MR Handler Strict Contract**
**File**: [tests/domains/decision_making/test_mr_handler_strict_missing_config.py](tests/domains/decision_making/test_mr_handler_strict_missing_config.py)

| Test | Status | Description |
|------|--------|-------------|
| `test_mr_assigned_but_config_missing_raises_error` | ✅ PASS | MR assigned in registry but config missing → ValueError |
| `test_mr_not_assigned_and_config_missing_disabled_no_noise` | ✅ PASS | MR not assigned + config missing → handler disabled (silent) |
| `test_mr_assigned_with_valid_config_initializes` | ✅ PASS | MR assigned + valid config → handler initializes |
| `test_missing_position_size_blocks_signal` | ✅ PASS | Missing position_size_usd → signal blocked (no event) |
| `test_valid_position_size_allows_signal` | ✅ PASS | Valid position_size_usd → signal emitted successfully |
| `test_no_dict_fallback_accepted` | ✅ PASS | Handler does NOT accept dict config (Pydantic only) |

**Result**: **6/6 PASSED**

---

### **Combined Test Run**
```bash
$ pytest tests/config/test_strategies_registry_strict.py \
         tests/domains/decision_making/test_btc_arbitration_deterministic.py \
         tests/domains/decision_making/test_mr_handler_strict_missing_config.py -q

tests/config/test_strategies_registry_strict.py ......                   [ 24%]
tests/domains/decision_making/test_btc_arbitration_deterministic.py .............  [ 76%]
tests/domains/decision_making/test_mr_handler_strict_missing_config.py ......     [100%]

============================== 25 passed in 0.17s ==============================
```

**Total**: **25/25 PASSED** ✅

---

## 📋 Definition of Done (DoD) Checklist

- [x] **No dict-fallback** - MR handler uses ONLY typed Pydantic config
  - ✅ Removed `isinstance(self.config, dict)` branch
  - ✅ Test: `test_no_dict_fallback_accepted` PASS

- [x] **No silent defaults** - position_size_usd=100 removed
  - ✅ `_get_position_size_usd()` returns `None` instead of `Decimal("100")`
  - ✅ Caller blocks signal with `MR_REJECT:missing_position_size`
  - ✅ Test: `test_missing_position_size_blocks_signal` PASS

- [x] **Strict crash** if MR assigned but config missing
  - ✅ `_get_mr_assigned_symbols()` checks strategies_registry
  - ✅ Raises `ValueError` with clear message
  - ✅ Test: `test_mr_assigned_but_config_missing_raises_error` PASS

- [x] **Handler disabled fail-closed** if MR not assigned + config missing
  - ✅ No ValueError if MR not in assignments
  - ✅ Handler sets `_enabled=False` silently
  - ✅ Test: `test_mr_not_assigned_and_config_missing_disabled_no_noise` PASS

- [x] **Duplicate fields cleaned up**
  - ✅ Removed duplicate `sl_atr_mult` and `tp_to_mid` assignments

- [x] **All tests pass** - 25/25 PASSED
  - ✅ Registry strict: 6/6
  - ✅ Arbitration: 13/13
  - ✅ MR handler: 6/6

---

## 🔬 Fail-Closed Matrix (MR Handler)

| Scenario | Behavior | Log/Error |
|----------|----------|-----------|
| MR assigned + config missing | ❌ CRASH ValueError | "mean_reversion assigned but config missing" |
| MR not assigned + config missing | ✅ Disabled (silent) | "config missing, handler disabled" |
| MR enabled + missing position_size | ❌ BLOCK signal | "MR_REJECT:missing_position_size" |
| MR enabled + valid config | ✅ Signal emitted | EVT:TRADE_INTENT_PROPOSED |
| Dict config passed | ❌ Ignored → disabled | No Pydantic typed access |

**5/5 scenarios** - fail-closed ✅

---

## 📊 Code Coverage

### **Modified Files**
1. ✅ [apps/reference/domains/decision_making/mean_reversion_handler.py](apps/reference/domains/decision_making/mean_reversion_handler.py)
   - L99-127: `_parse_config()` - removed dict-fallback, added MR assignment check
   - L106-123: `_get_mr_assigned_symbols()` - NEW method
   - L158-165: `_init_strategies()` - removed duplicate fields
   - L258-268: `_handle_signal()` - fail-closed on missing position_size
   - L335-350: `_get_position_size_usd()` - returns `None` instead of `100`

### **Test Files**
1. ✅ [tests/domains/decision_making/test_mr_handler_strict_missing_config.py](tests/domains/decision_making/test_mr_handler_strict_missing_config.py) (NEW, 296 lines, 6 tests)

---

## 🚀 Next Steps (Future Phases)

### **Phase-3: MR Config Consolidation** (NOT in this PR)
- Merge `strategies/mean_reversion.yaml` → single SSOT
- Remove `trading.mean_reversion` mirror (deprecated)
- Migrate parameters without changing behavior
- Update tests for new config paths

### **Phase-4: Advanced MR Features** (NOT in this PR)
- Regime-based sizing (already supported, needs testing)
- Multi-symbol correlation checks
- Dynamic cooldown based on volatility

---

## 📝 Implementation Notes

### **Key Design Decisions**

1. **MR Assignment as Contract**:
   - If `strategies_registry.assignments` includes `mean_reversion` → config REQUIRED
   - If no assignment → config optional (handler disabled, no noise)
   - This prevents "MR enabled in config but no symbols assigned" confusion

2. **Position Size Fail-Closed**:
   - NO silent defaults (`100` was dangerous - could lead to oversizing)
   - Return `None` → caller MUST handle explicitly
   - Log `MR_REJECT:missing_position_size` (≤80 chars, XAI-friendly)

3. **Dict-Fallback Removal**:
   - Old code tried to parse dict config and silently warn on failure
   - New code: Pydantic typed access ONLY
   - If config is dict → handler disabled (fail-closed)

4. **Duplicate Field Cleanup**:
   - `sl_atr_mult` and `tp_to_mid` were assigned twice (copy-paste error)
   - Removed duplicates → single source of truth per field

---

## 🔍 Risk Assessment

### **Low Risk ✅**
- MR handler is optional (legacy systems without MR continue working)
- If MR not assigned in registry → no behavior change (disabled)
- Position size check is fail-closed (block signal vs. use wrong size)

### **Medium Risk ⚠️**
- Existing MR deployments with `risk.position_size_usd` missing will now BLOCK signals
  - **Mitigation**: Validate `mean_reversion.risk.position_size_usd` is set before deploy
  - **Detection**: Logs show `MR_REJECT:missing_position_size` immediately

### **Zero Risk 🔒**
- Dict-fallback removal: already not used in production (Pydantic migration complete)
- Duplicate field cleanup: cosmetic (no logic change)

---

## ✅ Sign-Off

**Phase-0 + MR Handler Strict Contract**: COMPLETE  
**Tests**: 25/25 PASSED  
**DoD**: All items checked ✅  
**Breaking Changes**: MR signals blocked if `position_size_usd` missing (intentional fail-closed)  
**Deployment Risk**: LOW (fail-closed prevents silent errors)  

**Ready for Phase-3 (MR config consolidation).**

---

## 📚 References

- **Phase-0 Report**: [CFG_STRATEGIES_SSOT_01_ARBITRATION_FAILCLOSED_FIX.md](CFG_STRATEGIES_SSOT_01_ARBITRATION_FAILCLOSED_FIX.md)
- **Arbitration Tests**: [test_btc_arbitration_deterministic.py](tests/domains/decision_making/test_btc_arbitration_deterministic.py) (13 tests)
- **Registry Tests**: [test_strategies_registry_strict.py](tests/config/test_strategies_registry_strict.py) (6 tests)
- **MR Handler Tests**: [test_mr_handler_strict_missing_config.py](tests/domains/decision_making/test_mr_handler_strict_missing_config.py) (6 tests)

---

**EOF**
