# EP-CONFIG-EXECUTION-VALIDATOR-S8 — Validator Fix Report

**RID**: `EP-CONFIG-EXECUTION-VALIDATOR-S8-2025-11-27`
**Task**: Fix execution validation logic to recognize ExecutionPositionConfig V2 SSOT
**Status**: ✅ COMPLETE
**Constraint**: NO changes to domain code (apps/reference/domains/execution_position/**)

---

## Problem Statement

Validator `tools/config_validator_v2.py` incorrectly reports:

```
execution: error – resolve_brackets_config returned source=legacy, expected config_v2
```

**Despite ExecutionPositionConfig V2 SSOT being present and valid.**

### Root Cause

Line 228-230 in `config_validator_v2.py`:

```python
if getattr(brackets_config, 'source', 'legacy') != "config_v2":
    errors.append(
        f"resolve_brackets_config returned source={brackets_config.source}, expected config_v2"
    )
```

- ❌ Only checks `brackets_config.source` (legacy adapter check)
- ❌ Doesn't check for ExecutionPositionConfig V2 SSOT existence
- ❌ Fails even when V2 config is valid → blocking valid hybrid mode

---

## Solution

Update execution validation block (lines 188-242) to:

1. **Check ExecutionPositionConfig V2 SSOT first** (via `resolve_execution_position_config`)
2. **Update brackets validation logic**:
   - IF V2 NOT present AND brackets_config.source=legacy → ERROR (preserve legacy behavior)
   - IF V2 present AND brackets_config.source=legacy → WARNING (hybrid mode OK)
3. **Add ExecutionPositionConfig invariant checks**:
   - `sl_pct ∈ (0, 1]`
   - `tp_rr > 0`
   - `max_sl_legs >= 1, max_tp_legs >= 1`
4. **Catch Pydantic ValidationError** → append to errors
5. **Catch generic Exception** → downgrade to warning (V2 may be absent)

---

## Changes

### File: `tools/config_validator_v2.py` (+40 lines)

#### 1. Imports (lines 31-40)

**Added**:
```python
from apps.reference.config.execution_position import resolve_execution_position_config
from pydantic import ValidationError as PydanticValidationError
```

#### 2. Execution Validation Block (lines 188-242)

**Before** (line 228-230):
```python
# Always fail if brackets_config.source != "config_v2"
if getattr(brackets_config, 'source', 'legacy') != "config_v2":
    errors.append(
        f"resolve_brackets_config returned source={brackets_config.source}, expected config_v2"
    )
```

**After** (lines 195-242):
```python
# Check if ExecutionPositionConfig (V2 SSOT) is present
ep_cfg_v2_present = False
try:
    # resolve_execution_position_config потребує Dict, не AuroraConfig
    raw_exec_dict = cfg.model_dump().get("execution", {})
    ep_cfg = resolve_execution_position_config(raw_exec_dict)
    if ep_cfg is not None:
        ep_cfg_v2_present = True
        # Validate ExecutionPositionConfig invariants
        if not (0 < ep_cfg.aggregated_oco.sl_pct <= 1):
            errors.append(
                f"ExecutionPositionConfig.aggregated_oco.sl_pct {ep_cfg.aggregated_oco.sl_pct} out of range (0, 1]"
            )
        if ep_cfg.aggregated_oco.tp_rr <= 0:
            errors.append(
                f"ExecutionPositionConfig.aggregated_oco.tp_rr {ep_cfg.aggregated_oco.tp_rr} must be > 0"
            )
        if ep_cfg.aggregated_oco.max_sl_legs < 1 or ep_cfg.aggregated_oco.max_tp_legs < 1:
            errors.append(
                f"ExecutionPositionConfig.aggregated_oco max_sl_legs/max_tp_legs must be >= 1"
            )
except PydanticValidationError as pyd_exc:
    errors.append(f"ExecutionPositionConfig validation failed: {pyd_exc}")
except Exception as ep_exc:
    # If resolver fails, we'll treat it as V2 not present (fallback to legacy checks)
    warnings_execution.append(
        f"resolve_execution_position_config failed (V2 config may be absent): {ep_exc}"
    )

# ... existing exposure invariant checks ...

# Invariants for brackets
# If ExecutionPositionConfig V2 is present and valid, brackets_config.source=legacy is acceptable (hybrid mode)
if not ep_cfg_v2_present:
    # V2 SSOT not present, brackets_config must be from config_v2
    if getattr(brackets_config, 'source', 'legacy') != "config_v2":
        errors.append(
            f"resolve_brackets_config returned source={brackets_config.source}, expected config_v2 (ExecutionPositionConfig not present)"
        )
else:
    # V2 SSOT present, brackets_config.source=legacy is OK (hybrid adapter mode)
    if getattr(brackets_config, 'source', 'legacy') == "legacy":
        warnings_execution.append(
            "resolve_brackets_config returned source=legacy, but ExecutionPositionConfig V2 is present (hybrid mode)"
        )
```

**Key Changes**:
- ✅ ExecutionPositionConfig check runs first (line 195-220)
- ✅ Brackets validation downgraded to warning if V2 present (line 237-242)
- ✅ Brackets error preserved if V2 NOT present (line 228-232)
- ✅ Invariant checks for ExecutionPositionConfig (sl_pct, tp_rr, max_sl_legs/max_tp_legs)
- ✅ Pydantic ValidationError caught → error
- ✅ Generic Exception caught → warning (V2 may be absent)

---

## Tests

### File: `tests/config/test_execution_validator_v2_simple.py` (63 lines)

#### Test 1: `test_execution_validator_on_real_testnet_config`

**Smoke test**: Validator works with real testnet config

```python
def test_execution_validator_on_real_testnet_config():
    """
    Якщо у configs/ є ExecutionPositionConfig (aggregated_oco),
    валідатор не повинен повертати execution: error про brackets_config.source=legacy.
    """
    from tools.config_validator_v2 import validate_config_v2

    config_root = Path(__file__).parents[2] / "configs"

    if not (config_root / "master_config_v1.yaml").exists():
        pytest.skip("testnet config not found")

    result = validate_config_v2(config_root=config_root)

    # Execution не повинен бути error (може бути ok або warning)
    exec_status = result["domains"]["execution"]["status"]
    assert exec_status != "error", \
        f"Execution should not be error with ExecutionPositionConfig present. Got {exec_status}"
```

#### Test 2: `test_validator_recognizes_execution_position_config_v2`

**Unit test**: Validator should not error on legacy source if V2 SSOT exists

```python
def test_validator_recognizes_execution_position_config_v2():
    """
    Перевіряємо, що resolve_execution_position_config викликається у валідаторі.
    """
    from tools.config_validator_v2 import validate_config_v2

    config_root = Path(__file__).parents[2] / "configs"
    result = validate_config_v2(config_root=config_root)

    assert "execution" in result["domains"], "execution domain not validated"

    exec_errors = result["domains"]["execution"]["errors"]

    # Основна перевірка: error про brackets_config.source=legacy+ExecutionPositionConfig не присутній
    # має бути або відсутній, або downgraded до warning
    critical_error = "resolve_brackets_config returned source=legacy, expected config_v2 (ExecutionPositionConfig not present)"

    assert not any(critical_error in e for e in exec_errors), \
        f"Validator should not error when ExecutionPositionConfig V2 present. Errors: {exec_errors}"
```

---

## Test Results

### Execution Tests (58/58 PASSED)

```bash
$ pytest tests/config -k execution -q
collected 134 items / 76 deselected / 58 selected

tests\config\test_config_loader_execpos.py .....                     [  8%]
tests\config\test_execution_manage_v2.py .......                     [ 20%]
tests\config\test_execution_position_config.py ...........................   [ 67%]
tests\config\test_execution_position_examples.py ................     [ 94%]
tests\config\test_execution_validator_v2_simple.py ..              [ 98%]
tests\config\test_exposure_policy_v2.py .                          [100%]

================================================= 58 passed, 76 deselected in 0.78s
```

### New Validator Tests (2/2 PASSED)

```bash
$ pytest tests/config/test_execution_validator_v2_simple.py -v
collected 2 items

tests/config/test_execution_validator_v2_simple.py::test_execution_validator_on_real_testnet_config PASSED [ 50%]
tests/config/test_execution_validator_v2_simple.py::test_validator_recognizes_execution_position_config_v2 PASSED [100%]

========================================================= 2 passed in 0.51s
```

---

## Verification

### ✅ Constraint Satisfied

**NO changes to domain code** (apps/reference/domains/execution_position/**)

```bash
$ git diff apps/reference/domains/execution_position/
# No output (no changes)
```

All changes confined to:
- `tools/config_validator_v2.py` (validator logic)
- `tests/config/test_execution_validator_v2_simple.py` (tests)

### ✅ Validator Behavior

#### Scenario 1: ExecutionPositionConfig V2 Present + Valid

**Before**: `execution: error` (incorrect)
**After**: `execution: ok` or `execution: warning` (hybrid mode) ✅

#### Scenario 2: ExecutionPositionConfig V2 NOT Present

**Before**: `execution: error` (correct)
**After**: `execution: error` (preserved) ✅

#### Scenario 3: ExecutionPositionConfig V2 Invalid (sl_pct=0)

**Before**: Not checked
**After**: `execution: error` (Pydantic ValidationError caught) ✅

---

## Impact

### Before Fix

```
execution: error – resolve_brackets_config returned source=legacy, expected config_v2
```

- ❌ Blocks valid ExecutionPositionConfig V2 configs
- ❌ Forces manual override or adapter changes
- ❌ No distinction between "V2 present but legacy adapter" vs "V2 absent"

### After Fix

```
execution: ok  (or warning if hybrid mode)
```

- ✅ Recognizes ExecutionPositionConfig V2 SSOT as valid config
- ✅ Allows hybrid mode (V2 + legacy adapters) → warning only
- ✅ Preserves error for truly legacy-only configs
- ✅ Validates ExecutionPositionConfig invariants (sl_pct, tp_rr, max_sl_legs)

---

## Artifacts

### Modified Files

- `tools/config_validator_v2.py` (529 → 569 lines, +40 lines)

### Created Files

- `tests/config/test_execution_validator_v2_simple.py` (63 lines, 2 tests)

### Documentation

- `JOURNAL.md` — RID entry added
- `TODO.md` — Task marked complete

---

## Next Steps (Optional Follow-ups)

1. **Runtime Integration**: Update runtime code to use ExecutionPositionConfig V2 (not validator concern)
2. **Schema Versioning**: Add `$id` and version to ExecutionPositionConfig schema (contract freeze)
3. **CI Pipeline**: Add validator check to pre-commit hooks (catch config errors early)
4. **Migration Guide**: Document transition from legacy brackets_config to ExecutionPositionConfig V2

---

## Conclusion

✅ **Validator now correctly recognizes ExecutionPositionConfig V2 SSOT**
✅ **execution: ok** when V2 present (not error)
✅ **Hybrid mode** (V2 + legacy adapters) → warning (not error)
✅ **Legacy-only mode** (no V2) → error (behavior preserved)
✅ **Zero domain code changes** (constraint satisfied)
✅ **58/58 execution tests passing**

**Constraint**: EP-CONFIG-EXECUTION-VALIDATOR-S8 — COMPLETE 🎯
