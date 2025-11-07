# 🚀 Pydantic Configuration Migration Plan

**Project**: QuantumTraderX (Phenix)
**Status**: In Progress (Phases 0-1.5 ✅ Complete)
**Target**: Full type validation, startup error detection, IDE autocomplete
**Timeline**: 2-3 development sprints
**Last Updated**: 2025-11-06

---

## 📊 Executive Summary

### Current State
- **Framework**: vfoundation (core FSM, routing, idempotency)
- **App**: apps/reference (trading domains, adapters, telemetry)
- **Config System**: Dict-based `AuroraConfig` wrapper with `.get()` interface
- **Problem**: 677 `.get()` calls, no type validation, runtime config errors possible
- **Pydantic**: ✅ 2.12.3 already installed

### What We're Doing
Converting to Pydantic V2 models with:
- ✅ Startup validation (fail fast on config errors)
- ✅ Full type hints (IDE autocomplete)
- ✅ Backward compatibility (legacy `.get()` supported during migration)
- ✅ Zero breaking changes to API

### Success Criteria
- [ ] Config errors detected at startup (not runtime)
- [ ] All 677 `.get()` sites converted to typed attributes
- [ ] pytest suite passes 100% (existing + new validation tests)
- [ ] IDE provides autocomplete for all config paths
- [ ] Zero performance regression

---

## 🏗️ Architecture Overview

```
┌─────────────────────────────────────┐
│  YAML Files (config/aurora/)        │
│  ├── system.yaml                    │
│  └── trading.yaml                   │
└──────────────┬──────────────────────┘
               │ PyYAML.safe_load()
               ▼
┌─────────────────────────────────────┐
│  Dict[str, Any]                     │
│  + env var resolution               │
│  + mode-override resolution         │
└──────────────┬──────────────────────┘
               │ Pydantic(**dict)
               ▼ (VALIDATION HERE ✅)
┌─────────────────────────────────────┐
│  Pydantic Models (config_models.py) │
│  ├── AuroraConfig (root)            │
│  ├── TradingConfig                  │
│  ├── DecisionConfig                 │
│  ├── ExecutionConfig                │
│  └── ... (15+ models)               │
└──────────────┬──────────────────────┘
               │ Wrap in legacy-compat
               ▼
┌─────────────────────────────────────┐
│  AuroraConfig (config_loader.py)    │
│  - Pydantic fields + .get() support │
│  - get_config() singleton           │
└─────────────────────────────────────┘
```

---

## 📋 Phase Breakdown

### ✅ PHASE 0: Environment Setup
**Duration**: Done (1 commit)
**Owner**: ✅ Complete

**Deliverables**:
- [x] Add `pydantic==2.12.3` to `requirements.txt`
- [x] Verify installation in CI/local

**Commit Message**:
```
chore(config): add pydantic to requirements.txt for startup validation
```

---

### ✅ PHASE 1: Pydantic Model Design
**Duration**: Done (1 session)
**Owner**: ✅ Complete
**File**: `apps/reference/config_models.py` (700+ lines)

**Deliverables**:
- [x] Create 15+ Pydantic V2 models covering:
  - Root: `AuroraConfig`
  - Trading: `TradingConfig`, `DecisionConfig`, `PositionSizingConfig`, `KellyConfig`, `QosConfig`
  - Execution: `ExecutionConfig`, `ManageConfig`, `BracketsConfig`
  - Risk: `ExposureConfig`
  - Exchange: `BinanceApiConfig`, `BinanceApiEnv`
  - Market Data: `MarketDataConfig`, `MacroSyncConfig`
  - Instruments: `InstrumentSpec`
  - System: `LoggingConfig`, `SystemConfig`
- [x] Add mode-specific validators
- [x] Add field defaults matching current YAML
- [x] Document each model with docstrings

**Validation Rules**:
```python
- trading_mode: str ∈ {testnet, production, live}
- signal_threshold: float > 0
- kelly_cap: float ∈ [0, 1]
- max_equity_utilization_pct: float ∈ [0, 1]
- leverage_defaults["__default__"]: int > 0
```

**Commit Message**:
```
feat(config): design pydantic models for config validation [FSMP-CFG-1]

- Create 15+ Pydantic V2 models with full type hints
- Add field validators for trading_mode, percentages, etc.
- Support mode-specific overrides (testnet/production)
- Add create_aurora_config() helper function
```

---

### ✅ PHASE 1.5: ConfigLoader Migration
**Duration**: Done (1 session)
**Owner**: ✅ Complete
**File**: `apps/reference/config_loader.py` (updated)

**Deliverables**:
- [x] Update `load_config()` to:
  1. Load YAML via PyYAML
  2. Resolve environment variables
  3. Apply mode-specific decision overrides
  4. **Validate through Pydantic** ← STARTUP VALIDATION
  5. Return legacy-compatible `AuroraConfig` wrapper
- [x] Create `AuroraConfig` wrapper class:
  - Inherits from `PydanticAuroraConfig`
  - Provides `.get()` method for backward compatibility
  - Provides `.to_dict()` for serialization
- [x] Add error handling with detailed error messages:
  ```
  ❌ Configuration validation failed:
    trading.decision.kelly: invalid value
    trading.execution.exposure.max_equity_utilization_pct: must be ≤ 1.0
  ```
- [x] Preserve existing mode-override logic
- [x] Add detailed logging at INFO level

**Error Handling Example**:
```python
try:
    pydantic_config = PydanticAuroraConfig(**resolved_config)
    LOG.info(f"✅ Configuration validated for trading_mode: '{pydantic_config.trading_mode}'")
    return AuroraConfig(**resolved_config)
except ValidationError as e:
    LOG.error("❌ Configuration validation failed:")
    for error in e.errors():
        loc = ".".join(str(x) for x in error["loc"])
        LOG.error(f"  {loc}: {error['msg']}")
    raise
```

**Commit Message**:
```
feat(config): add pydantic validation to ConfigLoader [FSMP-CFG-2]

- Update load_config() to validate through Pydantic
- Create backward-compatible AuroraConfig wrapper
- Implement startup validation (fail-fast on config errors)
- Add detailed error messages with field paths
- Preserve mode-override and env var resolution logic
```

---

### ⏳ PHASE 2: Refactor Critical Files (30+ Sites)
**Duration**: 2-3 days
**Owner**: @agent
**Target Files**: High-impact domains (100+ `.get()` calls combined)

**Priority Tier 1** (DO FIRST - 150+ calls):
```
1. apps/reference/domains/execution_position/fsm_manage.py      (60 .get() calls)
2. apps/reference/domains/decision_making/decision_making.py    (80 .get() calls)
3. apps/reference/domains/execution_position/exposure_guard.py  (50 .get() calls)
4. apps/reference/domains/execution_position/fsm.py             (45 .get() calls)
```

**Priority Tier 2** (NEXT - 100+ calls):
```
5. apps/reference/domains/execution_position/binance_execution_adapter.py (50 calls)
6. apps/reference/domains/market_data/market_data_connector.py  (30 calls)
7. apps/reference/domains/account_balance/account_connector.py  (25 calls)
8. apps/reference/adapters/binance_adapter.py                   (45 calls)
```

**Priority Tier 3** (THEN - 80+ calls):
```
9. vfoundation/obs/debug_api.py                (30 calls)
10. vfoundation/dr/wal.py                       (20 calls)
11. vfoundation/dr/replay.py                    (10 calls)
12. tools/ scripts (verify_config.py, etc.)     (15 calls)
```

**Refactoring Pattern**:

**BEFORE** (dict-based):
```python
# fsm_manage.py (line 80-82)
bar_gate_cfg = (self.config.get("trading", {})
                            .get("decision", {})
                            .get("bar_gating", {}))
em_cfg = (self.config.get("execution", {})
          .get("manage", {})
          .get("emergency", {}))
```

**AFTER** (Pydantic):
```python
# fsm_manage.py (refactored)
bar_gate_cfg = self.config.trading.decision.bar_gating or BarGatingConfig()
em_cfg = self.config.execution.manage.emergency

# Type is known: BarGatingConfig | None → IDE autocomplete works ✅
# self.config: AuroraConfig (known type)
#   .trading: TradingConfig
#     .decision: DecisionConfig
#       .bar_gating: Optional[BarGatingConfig]
```

**Refactoring Checklist**:
- [ ] Replace all `config.get("path", {})` chains with direct attribute access
- [ ] Replace all `config.get("key", default)` with direct attribute access (use `or default_value`)
- [ ] Update type hints in method signatures
- [ ] Add docstrings showing config structure
- [ ] Run pytest for each file after refactoring
- [ ] Verify no new `.get()` calls are added

**Testing Strategy**:
```bash
# After each file refactoring:
pytest tests/domains/test_<domain>.py -v
pytest tests/units/ -v
pytest tests/integration/ -v
```

**Commit Template**:
```
refactor(config): migrate {domain} to typed config attributes [FSMP-CFG-TIER{N}]

Files changed:
- apps/reference/domains/{domain}/{file}.py

Changes:
- Replaced {N} config.get() calls with typed attribute access
- Updated {N} method signatures with proper type hints
- Added {N} docstrings documenting config structure

Tests:
- ✅ All {domain} unit tests pass
- ✅ No .get() anti-patterns remain
- ✅ Type checking clean (mypy --strict)

Before: config.get("trading", {}).get("decision", {})
After: config.trading.decision
```

---

### ⏳ PHASE 3: Refactor All Remaining Sites (500+ Calls)
**Duration**: 3-4 days
**Owner**: @agent
**Target**: Remaining framework & test files

**Files by Category**:

**Tests/ (100+ calls)**:
- tests/test_config_*.py (10 files, ~30 calls)
- tests/domains/ (5 files, ~20 calls)
- tests/integration/ (5 files, ~30 calls)
- tests/units/ (10 files, ~20 calls)

**Tools/ (20+ calls)**:
- tools/metrics_summary.py (5 calls)
- tools/verify_config.py (5 calls)
- tools/validate_testnet.py (5 calls)

**Framework/ (100+ calls)**:
- vfoundation/obs/logger.py (8 calls)
- vfoundation/obs/debug_api.py (30 calls)
- vfoundation/dr/ (30 calls)
- vfoundation/cli/ (10 calls)

**App Adapters/ (50+ calls)**:
- apps/reference/adapters/sdk_adapter_binance.py (5 calls)
- apps/reference/config_symbols.py (6 calls)

**Refactoring Batch Strategy**:
```bash
# Group 1: Tests (40 calls)
# Commits: test(config): migrate to typed config [FSMP-CFG-TESTS-1,2,3]

# Group 2: Tools (20 calls)
# Commits: refactor(tools): use typed config [FSMP-CFG-TOOLS]

# Group 3: Framework Obs/DR (100+ calls)
# Commits: refactor(obs): use typed config [FSMP-CFG-OBS]
#          refactor(dr): use typed config [FSMP-CFG-DR]

# Group 4: Adapters (50+ calls)
# Commits: refactor(adapters): use typed config [FSMP-CFG-ADAPTERS]
```

**Final Validation**:
```bash
# Full test suite
pytest -xvs --cov=. --cov-report=term-missing

# Check for remaining .get() calls (should be <5)
grep -r "\.get(" --include="*.py" \
  --exclude-dir=__pycache__ \
  --exclude-dir=.git \
  apps/ vfoundation/ tests/ tools/ \
  | grep -v "pydantic\|dict\|msg.get\|env.get\|os.environ.get" \
  | wc -l

# Type checking
mypy --strict apps/ vfoundation/
```

---

### ⏳ PHASE 4: Testing & Validation
**Duration**: 1-2 days
**Owner**: @agent

**Deliverables**:

#### 4.1 Config Validation Tests
**File**: `tests/test_config_pydantic_validation.py` (NEW)

```python
import pytest
from pydantic import ValidationError
from apps.reference.config_models import AuroraConfig

class TestPydanticValidation:
    """Test config validation catches errors at startup."""

    def test_invalid_trading_mode_fails_at_load(self):
        """Invalid trading_mode should raise ValidationError on load."""
        with pytest.raises(ValidationError) as exc_info:
            AuroraConfig(trading_mode="invalid_mode", ...)
        assert "trading_mode" in str(exc_info.value)

    def test_invalid_kelly_cap_fails_at_load(self):
        """Kelly cap > 1.0 should raise ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            config_dict = {..., "trading": {"decision": {"kelly": {"kelly_cap": 1.5}}}}
            AuroraConfig(**config_dict)
        assert "kelly_cap" in str(exc_info.value)

    def test_invalid_exposure_pct_fails_at_load(self):
        """Exposure > 100% should raise ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            config_dict = {..., "trading": {"execution": {"exposure": {"max_equity_utilization_pct": 1.5}}}}
            AuroraConfig(**config_dict)
        assert "max_equity_utilization_pct" in str(exc_info.value)

    def test_valid_config_loads_successfully(self):
        """Valid config should load without errors."""
        valid_config = {...}  # Use current trading.yaml data
        config = AuroraConfig(**valid_config)
        assert config.trading_mode == "testnet"
        assert config.trading.decision.kelly.kelly_cap <= 1.0
```

#### 4.2 Backward Compatibility Tests
**File**: `tests/test_config_backward_compat.py` (NEW)

```python
def test_get_method_backward_compatible(config):
    """Legacy .get() method should still work."""
    assert config.get("trading_mode") == "testnet"
    assert config.get("nonexistent", "default") == "default"

def test_attribute_access_works(config):
    """Direct attribute access should work."""
    assert config.trading.mode == "testnet"
    assert config.trading.decision.signal_threshold > 0

def test_to_dict_works(config):
    """to_dict() should return valid dict."""
    d = config.to_dict()
    assert isinstance(d, dict)
    assert "trading_mode" in d
```

#### 4.3 Integration Tests
**File**: `tests/integration/test_config_startup_validation.py` (NEW)

```python
def test_config_loaded_from_yaml_with_validation():
    """Full config load pipeline with validation."""
    from apps.reference.config_loader import get_config

    config = get_config()
    assert config.trading_mode in ("testnet", "production", "live")
    assert config.trading.decision.signal_threshold > 0

def test_config_load_fails_on_invalid_yaml():
    """Config load should raise ValidationError on invalid YAML."""
    # Temporarily corrupt trading.yaml
    # Load config
    # Should raise ValidationError
    # Restore YAML
    pass
```

#### 4.4 IDE Autocomplete Verification
**Manual Testing**:
- [ ] Open fsm_manage.py
- [ ] Type: `config.trading.` → should show all TradingConfig fields
- [ ] Type: `config.trading.decision.` → should show all DecisionConfig fields
- [ ] Type: `config.trading.execution.manage.brackets.` → should show sl, tp, oco_emulation, etc.
- [ ] All attributes should have type hints in hover tooltip

#### 4.5 Performance Tests
**File**: `tests/test_config_performance.py` (NEW)

```python
def test_config_load_performance():
    """Config load should complete in <100ms (was ~50ms before)."""
    import time
    start = time.time()
    config = get_config()
    elapsed = (time.time() - start) * 1000
    assert elapsed < 100  # milliseconds
    print(f"Config load time: {elapsed:.2f}ms")
```

#### 4.6 Coverage Report
```bash
pytest tests/ --cov=apps/reference/config_models --cov-report=html
# Target: >95% coverage of config_models.py
```

#### 4.7 Full Regression Test
```bash
# Run full test suite
pytest tests/ -xvs --tb=short

# Check for config-related errors
pytest tests/domains/ -k "config" -v
pytest tests/integration/test_e2e_smoke.py -v

# Verify startup validation catches bad configs
# (Create temporary bad YAML and verify error handling)
```

---

## 🎯 Success Metrics

### Before vs After

| Metric | Before | Target | Status |
|--------|--------|--------|--------|
| Config `.get()` calls | 677 | 0 | ⏳ |
| Startup validation | ❌ None | ✅ 100% | ⏳ |
| IDE autocomplete | ❌ None | ✅ Full | ⏳ |
| Config errors caught | Runtime | Startup | ⏳ |
| Type coverage | ~0% | >95% | ⏳ |
| Test suite pass rate | ~95% | 100% | ⏳ |
| Performance regression | - | <10% | ⏳ |

### Example Error Detection

**BEFORE** (dict-based, no validation):
```
# production trading.yaml has typo:
trading:
  decision:
    kelly:
      kelly_cap: 1.5  # ❌ Invalid (>1.0), but not caught!

$ python main.py
# Runs fine for 30 minutes...
# Then crashes when kelly calc is invoked:
#   KeyError: 'invalid kelly_cap format'
```

**AFTER** (Pydantic validation):
```
$ python main.py
❌ Configuration validation failed:
  trading.decision.kelly.kelly_cap: ensure this value is <= 1.0 (type=value_error.number.not_le)

Traceback (most recent call last):
  ...
pydantic.ValidationError: ...
# Fails immediately at startup ✅
```

---

## 📅 Timeline & Milestones

```
Week 1:
  ✅ Mon-Tue: Phases 0-1.5 (design models, update loader)
  ⏳ Wed-Fri: Phase 2 (refactor Tier 1: 150+ calls)

Week 2:
  ⏳ Mon-Tue: Phase 2 (refactor Tier 2: 100+ calls)
  ⏳ Wed-Thu: Phase 2 (refactor Tier 3: 80+ calls)
  ⏳ Fri: Phase 3 prep

Week 3:
  ⏳ Mon-Tue: Phase 3 (tests: 100+ calls)
  ⏳ Wed: Phase 3 (tools: 20+ calls, framework: 100+ calls)
  ⏳ Thu: Phase 3 (adapters: 50+ calls)
  ⏳ Fri: Phase 4 (validation, testing)

DELIVERABLE:
  ✅ All 677 sites migrated
  ✅ Startup validation enabled
  ✅ 100% test pass rate
  ✅ IDE autocomplete working
  ✅ Full migration documentation
```

---

## 🔄 Rollback Plan

If issues arise during Phase 2+, we can revert to old system:

```bash
# Rollback to Phase 1.5 state (backward compatible)
git checkout HEAD~N -- apps/reference/config_loader.py

# Keep Pydantic models but don't use them for validation
# (models remain available for documentation/future use)

# Revert individual files if specific domain breaks:
git checkout HEAD~M -- apps/reference/domains/execution_position/fsm_manage.py
```

**Key**: ConfigLoader has backward-compatible `.get()` method, so old code keeps working.

---

## 📝 Documentation Plan

### 1. Migration Guide (For Other Developers)
**File**: `docs/CONFIG_MIGRATION_GUIDE.md`
- How to access config (new typed way)
- How `.get()` still works
- Common patterns and examples

### 2. Config Reference (Auto-generated)
**File**: `docs/CONFIG_REFERENCE.md`
- All available config fields
- Default values
- Valid ranges for each field
- Examples from trading.yaml

### 3. Troubleshooting
**File**: `docs/CONFIG_TROUBLESHOOTING.md`
- Common validation errors
- How to read Pydantic error messages
- How to extend config (add new fields)

### 4. Architecture Decision Record (ADR)
**File**: `docs/ADR_PYDANTIC_CONFIG.md`
- Why Pydantic was chosen
- Alternatives considered
- Trade-offs and rationale

---

## 🛠️ Tools & Commands

### Verification Commands
```bash
# Count remaining .get() calls
grep -r "\.get(" --include="*.py" apps/ vfoundation/ tests/ tools/ | wc -l

# Verify Pydantic models are valid
python -c "from apps.reference.config_models import AuroraConfig; print('✅ Models OK')"

# Run type checking
mypy --strict apps/reference/config_models.py
mypy --strict apps/reference/config_loader.py

# Test config validation
pytest tests/test_config_pydantic_validation.py -v

# Full regression
pytest tests/ -x
```

### Pre-Commit Hook (Optional)
```bash
# .git/hooks/pre-commit
#!/bin/bash
# Fail if new .get() calls added to domains/
grep -r "\.get(" --include="*.py" apps/reference/domains/ | \
  grep -v "pydantic" && \
  echo "❌ New .get() calls found in domains/" && \
  exit 1
```

---

## 👥 Roles & Responsibilities

| Role | Task | Owner |
|------|------|-------|
| Design | Pydantic model structure | ✅ Complete |
| Implementation | Phase 2-3 refactoring | @agent |
| Testing | Validation tests, integration tests | @agent + CI |
| Review | Code review, type checking | Manual |
| Documentation | Migration guides, troubleshooting | @agent |
| Validation | Performance, regression tests | CI/Manual |

---

## 📖 References

- **Pydantic Docs**: https://docs.pydantic.dev/latest/
- **Pydantic V2 Migration**: https://docs.pydantic.dev/latest/concepts/migration/
- **Type Hints Best Practices**: https://docs.python.org/3/library/typing.html
- **vFoundation Docs**: `docs/ROADMAP_DELTA_EMPTY_BRANCH.md`

---

## 📞 Checkpoints & Sign-Offs

- [ ] **Phase 1.5 Sign-Off**: ConfigLoader passes validation tests
- [ ] **Phase 2 Checkpoint**: Tier 1 domains refactored, tests green
- [ ] **Phase 3 Checkpoint**: All 677 sites migrated, grep shows 0 old patterns
- [ ] **Phase 4 Sign-Off**: Full regression tests pass, IDE autocomplete verified

---

## 🎉 Definition of Done

```
✅ All 677 .get() calls migrated to typed attributes
✅ Pydantic validates config on startup (fail-fast)
✅ 100% test suite passes (existing + new validation tests)
✅ IDE autocomplete works for all config paths
✅ <5% performance regression (if any)
✅ Documentation updated for developers
✅ Rollback procedure tested
✅ Code review approval from tech lead
```

---

**Document Status**: Living Document
**Last Updated**: 2025-11-06
**Next Review**: After Phase 2 completion
