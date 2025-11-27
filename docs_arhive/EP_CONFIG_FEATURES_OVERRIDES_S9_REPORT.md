# EP-CONFIG-FEATURES-OVERRIDES-S9 — Summary Report

**RID**: `EP-CONFIG-FEATURES-OVERRIDES-S9-2025-11-27`
**Task**: Fix config v2 schema validation errors (overrides + features domain)
**Status**: ✅ COMPLETE
**Constraint**: NO changes to execution_position domain (preserved from S8)

---

## Problem Statement

Validator `tools/config_validator_v2.py` reports critical errors blocking AuroraCore startup:

### 1. Schema Error (overrides/modes/instruments)

```
schema: error
  errors: None is not of type 'object'

Failed validating 'type' in schema['properties']['overrides']:
    {'type': 'object', ...}

On instance['overrides']:
    None
```

**Root Cause**: ConfigV2 dataclass has `overrides: Optional[Dict] = None`, but JSON schema required `type: "object"` (didn't allow null).

### 2. Features Domain Error

```
features: error
  errors: AuroraConfig.config_v2.domains['features'] is missing or empty.
         Regenerate config/domains/features.yaml via vfound schema...
```

**Root Cause**:
- `config/domains/features.yaml` exists and is valid
- Loader searches in `apps/reference/config/domains/` (empty directory)
- `_detect_project_root()` returns `apps/reference/` instead of repo root

---

## Solution

### 1. Schema Fixes (`config/_schemas/config_v2.schema.json`)

**Changed Type Definitions** (allow null for optional fields):

```json
// Before
"overrides": {
  "type": "object",
  "description": "..."
}

// After
"overrides": {
  "type": ["object", "null"],
  "description": "Explicit override blocks. Null is equivalent to empty object."
}
```

**Also applied to**: `modes`, `instruments`

**Rationale**: ConfigV2 Python model uses `Optional[Dict] = None`, schema must match this contract.

**Updated Required Fields**:

```json
// Before
"required": ["instruments", "overrides", "modes", "domains"]

// After
"required": ["domains"]
```

**Rationale**: Only `domains` is truly required; other fields have sensible defaults (None → no overrides/modes).

---

### 2. Features Domain Fix

**Problem**: Loader searches wrong path
**Solution**: Copy domain configs to expected location

```powershell
Copy-Item -Path "config\domains" -Destination "apps\reference\config\" -Recurse -Force
```

**Files Copied** (7 domain configs):
- execution.yaml
- risk.yaml
- decision.yaml
- sizing.yaml
- features.yaml ✅
- regimes.yaml
- tca.yaml

**Verification**:
```python
from apps.reference.config_loader import reload_config
cfg = reload_config()
features = cfg.config_v2.domains.get('features')
# Before: None
# After: {'global': {...}, 'windows': {...}, 'features': {...}, 'macro_sync': {...}}
```

**No Code Changes** - purely file location fix. `features.yaml` was already valid per `docs/config_v2/specification.md`.

---

## Tests Created

### 1. Overrides Schema Tests

**File**: `tests/config/test_config_v2_overrides_normalization.py` (143 lines, 6 tests)

| Test | Purpose |
|------|---------|
| `test_overrides_null_is_valid` | overrides=None passes schema validation |
| `test_overrides_empty_dict_is_valid` | overrides={} passes schema validation |
| `test_overrides_with_symbols_override_is_valid` | Nested symbols overrides valid |
| `test_overrides_with_domains_override_is_valid` | Nested domains overrides valid |
| `test_overrides_not_required_field` | overrides can be omitted entirely |
| `test_overrides_null_behaves_like_empty_dict` | Semantic equivalence test |

**Result**: ✅ **6/6 PASSED** (0.82s)

---

### 2. Features Domain Tests

**File**: `tests/config/test_features_config_v2_minimal.py` (130 lines, 6 tests)

| Test | Purpose |
|------|---------|
| `test_features_yaml_exists_and_loads` | features.yaml present and loads correctly |
| `test_features_resolver_can_parse_v2_config` | `resolve_feature_engineering_config()` succeeds |
| `test_features_validator_returns_ok_or_warning` | Validator returns `features: ok` |
| `test_features_yaml_matches_specification` | Structure matches `docs/config_v2/specification.md` |
| `test_features_domain_not_empty` | `domains['features']` not None/empty |
| `test_validator_schema_status_ok` | Schema validation passes |

**Result**: ✅ **6/6 PASSED** (1.02s)

---

## Validation Results

### Before Fix

```
Config validator status: error
  schema: error
    errors: None is not of type 'object'
            Failed validating 'type' in schema['properties']['overrides']
            Failed validating 'type' in schema['properties']['modes']
            Failed validating 'type' in schema['properties']['instruments']
  features: error
    errors: AuroraConfig.config_v2.domains['features'] is missing or empty
  execution: ok (from S8)
```

### After Fix

```
Config validator status: ok
  schema: ok
  execution: ok
    warnings: positions_stale_ttl_sec equals default 5s; consider setting explicit v2 value
  risk: ok
  sizing: ok
  decision: ok
  features: ok ✅
  instruments: ok
  modes: ok
```

---

## Test Results

### Full Config Test Suite

```bash
$ pytest tests/config -q --tb=no
collected 146 items
146 passed in 1.75s
```

**Breakdown**:
- Overrides tests: **6/6 PASSED** (0.82s)
- Features tests: **6/6 PASSED** (1.02s)
- Execution tests: **58/58 PASSED** (from S8)
- All other config tests: **76/76 PASSED**

**Total**: ✅ **146/146 PASSED** (1.75s)

---

## Files Modified/Created

### Modified

| File | Changes | Lines |
|------|---------|-------|
| `config/_schemas/config_v2.schema.json` | Allow null for overrides/modes/instruments, update required | +6 |

### Created

| File | Purpose | Lines | Tests |
|------|---------|-------|-------|
| `tests/config/test_config_v2_overrides_normalization.py` | Test overrides schema null handling | 143 | 6 |
| `tests/config/test_features_config_v2_minimal.py` | Test features domain loading | 130 | 6 |

### Copied

| Source | Destination | Files |
|--------|-------------|-------|
| `config/domains/*.yaml` | `apps/reference/config/domains/*.yaml` | 7 domain configs |

---

## Constraint Verification

✅ **NO changes to `apps/reference/domains/execution_position/**`** (preserved from S8)
✅ **NO changes to `shadow_execpos/**`**
✅ **Schema fixes are additive-only** (allow null, not breaking object type)
✅ **Features domain uses existing valid config** (no new trading logic)
✅ **All existing tests pass** (146/146 green)

---

## DoD (EP-CONFIG-FEATURES-OVERRIDES-S9)

✅ `schema: ok` — No errors from overrides/modes/instruments: None
✅ `features: ok` — Domain loads successfully, resolver works
✅ `execution: ok` — Preserved from S8 (validator recognizes ExecutionPositionConfig V2)
✅ All new/changed tests green (146/146 config tests)
✅ JOURNAL.md updated with RID entry
✅ Zero changes to execution_position domain code

---

## Impact

### Schema Validation

**Before**: 3 schema errors (overrides, modes, instruments) blocking startup
**After**: ✅ Schema: ok

### Features Domain

**Before**: Runtime error — "domains['features'] is missing or empty"
**After**: ✅ Features: ok — Resolver loads valid config from features.yaml

### Overall Validator

**Before**: `status: error` — AuroraCore startup blocked
**After**: ✅ `status: ok` — All domains validated successfully

---

## Decision Log

### Why Allow Null in Schema (vs Normalizing in Loader)?

**Option 1**: Normalize `overrides: null` → `{}` in loader
**Option 2**: Allow `type: ["object", "null"]` in schema ✅ **CHOSEN**

**Rationale**:
- ConfigV2 dataclass already defines `Optional[Dict] = None` (Pydantic contract)
- Schema should match code contract (principle of least surprise)
- Null has clear semantic: "no overrides" = "empty overrides"
- No runtime normalization logic needed (simpler, fewer edge cases)
- Additive-only change (doesn't break existing configs with overrides: {})

### Why Copy domains/ Files (vs Fixing Loader Path)?

**Option 1**: Fix `_detect_project_root()` to return repo root
**Option 2**: Copy `config/domains/` → `apps/reference/config/domains/` ✅ **CHOSEN**

**Rationale**:
- Loader already searches `{project_root}/config/domains/`
- Changing `_detect_project_root()` would affect many other paths (high risk)
- `apps/reference/config/` is canonical config location per existing code
- Domain files are static config (not code) — safe to duplicate
- Minimizes risk of breaking other config loading logic

---

## Next Steps (Optional Follow-ups)

1. **Consolidate Config Directories**: Decide on single source of truth for domain configs (config/ vs apps/reference/config/)
2. **Schema Versioning**: Add `$id` with version to config_v2.schema.json (contract freeze)
3. **CI Pipeline**: Add schema validation to pre-commit hooks (catch regressions early)
4. **Documentation**: Update `docs/config_v2/specification.md` with null semantics for optional fields

---

## Conclusion

✅ **schema: ok** — Schema allows null for optional fields (overrides, modes, instruments)
✅ **features: ok** — Domain configs copied to expected location, resolver works
✅ **execution: ok** — Preserved from S8 (ExecutionPositionConfig V2 recognized)
✅ **146/146 tests passing** — All config tests green
✅ **Zero domain code changes** — Constraint satisfied

**Validator Summary**: `Config validator status: ok` 🎯

**Constraint**: EP-CONFIG-FEATURES-OVERRIDES-S9 — COMPLETE
