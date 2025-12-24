# ✅ Pydantic Migration - Implementation Checklist

**Created**: 2025-11-06
**Sprint Duration**: 3 weeks estimated
**Current Phase**: 1.5 ✅ Complete → Phase 2 Ready

---

## Phase 1-1.5: ✅ COMPLETE

### ✅ Phase 0: Environment Setup (DONE)
- [x] Add pydantic==2.12.3 to requirements.txt
- [x] Verify installation: `python -c "import pydantic; print(pydantic.__version__)"`
- [x] No conflicts with other dependencies

**Commit**: `chore(config): add pydantic to requirements.txt`

### ✅ Phase 1: Pydantic Models (DONE)
- [x] Create `apps/reference/config_models.py` (700+ lines)
- [x] Define 15+ Pydantic V2 models:
  - [x] `AuroraConfig` (root model)
  - [x] `TradingConfig`
  - [x] `DecisionConfig`
  - [x] `PositionSizingConfig`
  - [x] `KellyConfig`
  - [x] `QosConfig`
  - [x] `SignalsConfig`
  - [x] `SignalWeights`
  - [x] `ExecutionConfig`
  - [x] `ManageConfig`
  - [x] `BracketsConfig`
  - [x] `SLConfig`
  - [x] `TPConfig`
  - [x] `ExposureConfig`
  - [x] `BinanceApiConfig`
  - [x] `BinanceApiEnv`
  - [x] `MarketDataConfig`
  - [x] `MacroSyncConfig`
  - [x] `FeatureEngineeringConfig`
  - [x] `AccountObserverConfig`
  - [x] `OpsConfig`
  - [x] `LoggingConfig`
  - [x] `SystemConfig`
  - [x] `InstrumentSpec`
  - [x] `BarGatingConfig`
  - [x] `BehaviorFsmConfig`
- [x] Add field validators:
  - [x] `trading_mode` ∈ {testnet, production, live}
  - [x] Kelly cap ≤ 1.0
  - [x] Percentages ≤ 1.0
- [x] Add create_aurora_config() helper
- [x] All models with docstrings

**Commit**: `feat(config): design pydantic models for config validation [FSMP-CFG-1]`

### ✅ Phase 1.5: ConfigLoader Migration (DONE)
- [x] Update `apps/reference/config_loader.py`
- [x] Create backward-compatible `AuroraConfig` wrapper:
  - [x] Inherits from Pydantic base
  - [x] Implements `.get()` method
  - [x] Implements `.to_dict()` method
  - [x] Implements `.get_domain_mode()` method
- [x] Update `load_config()`:
  - [x] Load YAML via PyYAML
  - [x] Resolve env vars
  - [x] Apply mode-overrides
  - [x] **Validate via Pydantic** ← STARTUP VALIDATION
  - [x] Return wrapped config
- [x] Error handling with field paths:
  ```python
  ❌ Configuration validation failed:
    trading.decision.kelly: invalid value
    trading.execution.exposure.max_equity_utilization_pct: must be ≤ 1.0
  ```
- [x] Preserve existing mode-override logic
- [x] Add INFO/ERROR logging

**Commit**: `feat(config): add pydantic validation to ConfigLoader [FSMP-CFG-2]`

**Verification**:
```bash
✅ python -c "from apps.reference.config_loader import get_config; cfg=get_config(); print('✅ Config loaded')"
✅ pytest tests/test_config_load.py -v
✅ grep -c "\.get(" apps/reference/config_loader.py  # Should be ~8 (legacy support only)
```

---

## ⏳ Phase 2: Refactor Critical Files (Tier 1 Priority)

### Priority Tier 1: Execute First (150+ `.get()` calls)

#### 2.1 Refactor fsm_manage.py (60 `.get()` calls)
**File**: `apps/reference/domains/execution_position/fsm_manage.py`

**Pre-Refactor**:
```python
# Lines 80-82: Bar gating config
bar_gate_cfg = (self.config.get("trading", {})
                            .get("decision", {})
                            .get("bar_gating", {}))

# Lines 87-89: Emergency config
em_cfg = (self.config.get("execution", {})
          .get("manage", {})
          .get("emergency", {}))
```

**Tasks**:
- [ ] Identify all 60 `.get()` calls:
  - [ ] Lines 80-82 (bar gating)
  - [ ] Lines 87-91 (execution manage)
  - [ ] Lines 98-102 (execution/trading override)
  - [ ] Lines 157-169 (more execution access)
  - [ ] Lines 217-219 (decision config)
  - [ ] Lines 296-319 (brackets config)
  - [ ] Lines 396-404 (emergency config)
  - [ ] Lines 486-532 (various configs)
  - [ ] Lines 564-568 (config access)
  - [ ] Lines 620-684 (extensive access)

**Post-Refactor Pattern**:
```python
# Use direct attribute access (Pydantic models)
bar_gate_cfg = self.config.trading.decision.bar_gating or BarGatingConfig()
em_cfg = self.config.execution.manage.emergency if self.config.execution and self.config.execution.manage else {}
```

**Checklist**:
- [ ] Create refactoring branch: `git checkout -b refactor/fsm-manage-typed-config`
- [ ] Replace all `.get()` chains with attribute access
- [ ] Add type hints to method signatures where needed
- [ ] Update docstrings with config structure
- [ ] Run tests: `pytest tests/domains/test_execution_position_fsm_manage.py -xvs`
- [ ] Check for new `.get()` calls: `grep "\.get(" apps/reference/domains/execution_position/fsm_manage.py`
- [ ] Verify behavior matches (manual smoke test):
  ```bash
  python -c "
  from apps.reference.domains.execution_position.fsm_manage import ManageFsm
  from apps.reference.config_loader import get_config
  config = get_config()
  fsm = ManageFsm(config=config)
  print('✅ ManageFsm initialized successfully')
  "
  ```
- [ ] Commit: `refactor(execution): migrate fsm_manage to typed config [FSMP-CFG-TIER1-A]`

---

#### 2.2 Refactor decision_making.py (80 `.get()` calls)
**File**: `apps/reference/domains/decision_making/decision_making.py`

**Lines to Refactor** (sample):
- [x] Lines 120-131: trading_config access
- [x] Lines 135-146: mode and sizing config
- [x] Lines 155-186: signals, qos, bar_gating, behavior
- [x] Lines 199-240+: extensive decision_config access
- [x] Lines 417-484: event payload feature/risk access
- [x] Lines 870-1420: signal calculation with config access

**Tasks**:
- [ ] Create branch: `git checkout -b refactor/decision-making-typed-config`
- [ ] Replace all 80 `.get()` calls
- [ ] Update all method signatures with proper types
- [ ] Add docstrings
- [ ] Run tests: `pytest tests/domains/test_decision_making.py -xvs`
- [ ] Commit: `refactor(decision): migrate decision_making to typed config [FSMP-CFG-TIER1-B]`

---

#### 2.3 Refactor exposure_guard.py (50 `.get()` calls)
**File**: `apps/reference/domains/execution_position/exposure_guard.py`

**Tasks**:
- [ ] Create branch: `git checkout -b refactor/exposure-guard-typed-config`
- [ ] Replace all 50 `.get()` calls
- [ ] Update type hints
- [ ] Run tests: `pytest tests/domains/test_exposure_guard_*.py -xvs`
- [ ] Commit: `refactor(exposure): migrate exposure_guard to typed config [FSMP-CFG-TIER1-C]`

---

#### 2.4 Refactor fsm.py (45 `.get()` calls)
**File**: `apps/reference/domains/execution_position/fsm.py`

**Tasks**:
- [ ] Create branch: `git checkout -b refactor/fsm-typed-config`
- [ ] Replace all 45 `.get()` calls
- [ ] Update type hints
- [ ] Run tests: `pytest tests/domains/test_execution_position_fsm.py -xvs`
- [ ] Commit: `refactor(execution): migrate fsm.py to typed config [FSMP-CFG-TIER1-D]`

---

### PHASE 2 SUMMARY
**Total `.get()` calls removed**: ~235 (60+80+50+45)
**Expected time**: 2-3 days
**Test status target**: 100% pass

**After Phase 2 Completion**:
```bash
# Verify Phase 2
pytest tests/domains/ -xvs
pytest tests/integration/test_e2e_smoke.py -v

# Count remaining .get() calls (should drop from 677 → ~442)
grep -r "\.get(" --include="*.py" apps/ | grep -v "\.pld\.get\|pydantic\|\.env\.get" | wc -l
```

---

## ⏳ Phase 3: Refactor Remaining Files (500+ Calls)

### Priority Tier 2: Execute Next (100+ `.get()` calls)

#### 3.1 Tier 2 - Adapters & Connectors
**Files** (Total ~100 calls):
- [ ] `binance_execution_adapter.py` (50 calls)
- [ ] `market_data_connector.py` (30 calls)
- [ ] `account_connector.py` (25 calls)

**Time**: 1 day
**Commits**:
- `refactor(adapters): migrate binance_execution_adapter to typed config [FSMP-CFG-TIER2-A]`
- `refactor(connectors): migrate market_data to typed config [FSMP-CFG-TIER2-B]`
- `refactor(connectors): migrate account_balance to typed config [FSMP-CFG-TIER2-C]`

---

#### 3.2 Tier 3: Framework Observability & DR
**Files** (Total ~100 calls):
- [ ] `vfoundation/obs/debug_api.py` (30 calls)
- [ ] `vfoundation/obs/logger.py` (8 calls)
- [ ] `vfoundation/dr/wal.py` (20 calls)
- [ ] `vfoundation/dr/replay.py` (10 calls)
- [ ] `vfoundation/cli/vfound/__main__.py` (10 calls)

**Time**: 1.5 days
**Commits**:
- `refactor(obs): migrate debug_api to typed config [FSMP-CFG-FW-OBS]`
- `refactor(dr): migrate WAL/replay to typed config [FSMP-CFG-FW-DR]`
- `refactor(cli): migrate vfound to typed config [FSMP-CFG-FW-CLI]`

---

#### 3.3 Tests & Tools
**Files** (Total ~120 calls):
- [ ] `tests/test_config_*.py` (30 calls) → `test(config): use typed config [FSMP-CFG-TESTS]`
- [ ] `tests/domains/` (20 calls)
- [ ] `tests/integration/` (30 calls)
- [ ] `tools/verify_config.py` (5 calls) → `refactor(tools): use typed config [FSMP-CFG-TOOLS]`
- [ ] `tools/metrics_summary.py` (5 calls)

**Time**: 1 day
**Commits**:
- `test(config): migrate config tests to typed config [FSMP-CFG-TESTS-1]`
- `test(domains): migrate domain tests to typed config [FSMP-CFG-TESTS-2]`
- `refactor(tools): migrate tools to typed config [FSMP-CFG-TOOLS]`

---

#### 3.4 Adapters & Utilities
**Files** (Total ~50 calls):
- [ ] `binance_adapter.py` (45 calls)
- [ ] `sdk_adapter_binance.py` (5 calls)
- [ ] `config_symbols.py` (6 calls)

**Time**: 0.5 days
**Commits**:
- `refactor(adapters): migrate binance_adapter to typed config [FSMP-CFG-ADAPT]`
- `refactor(adapters): migrate config_symbols to typed config [FSMP-CFG-ADAPT-2]`

---

### PHASE 3 SUMMARY
**Total `.get()` calls removed**: ~370
**Expected time**: 3-4 days
**Cumulative progress**: 235 + 370 = **605/677** ✅

**After Phase 3**:
```bash
# Verify Phase 3
pytest tests/ -x --tb=short

# Count remaining .get() (should be ~72, mostly framework internals)
grep -r "\.get(" --include="*.py" apps/ vfoundation/ tests/ tools/

# Check our progress
echo "✅ 605 of 677 sites migrated (89% complete)"
```

---

## ⏳ Phase 4: Testing & Validation

### 4.1 Create Validation Tests
**New file**: `tests/test_config_pydantic_validation.py`

```python
# Checklist:
- [ ] Test invalid trading_mode raises ValidationError
- [ ] Test invalid kelly_cap (>1.0) raises ValidationError
- [ ] Test invalid exposure_pct (>1.0) raises ValidationError
- [ ] Test valid config loads successfully
- [ ] Test backward compat .get() method
- [ ] Test to_dict() works
- [ ] Test config from actual trading.yaml validates
```

**Commit**: `test(config): add pydantic validation tests [FSMP-CFG-TEST-1]`

---

### 4.2 Integration Test
**File**: `tests/integration/test_config_startup_validation.py`

```python
# Checklist:
- [ ] Test full config load pipeline
- [ ] Test config validator called on startup
- [ ] Test config errors prevent startup
- [ ] Test config with wrong trading_mode fails
- [ ] Test config with invalid percentages fails
```

**Commit**: `test(integration): add config validation integration tests [FSMP-CFG-TEST-2]`

---

### 4.3 Backward Compatibility Test
**File**: `tests/test_config_backward_compat.py`

```python
# Checklist:
- [ ] Old code using .get() still works
- [ ] Old code using attribute access works
- [ ] Mixed usage works
- [ ] Edge cases (None values, defaults) handled
```

**Commit**: `test(config): add backward compatibility tests [FSMP-CFG-TEST-3]`

---

### 4.4 Full Regression Testing

#### 4.4.1 Unit Tests
```bash
- [ ] pytest tests/units/ -xvs
- [ ] Result: 100% pass
```

#### 4.4.2 Domain Tests
```bash
- [ ] pytest tests/domains/ -xvs
- [ ] Result: 100% pass
```

#### 4.4.3 Integration Tests
```bash
- [ ] pytest tests/integration/test_e2e_smoke.py -xvs
- [ ] Result: 100% pass
```

#### 4.4.4 Full Suite
```bash
- [ ] pytest tests/ -x --tb=short
- [ ] Coverage report: > 95%
- [ ] No warnings
```

**Commit**: `test(all): verify full regression after migration [FSMP-CFG-FINAL]`

---

### 4.5 Performance Testing

```bash
# Create test:
- [ ] Measure config load time before/after
- [ ] Target: <10% regression (or improvement!)
- [ ] Add to CI for regression detection

pytest tests/test_config_performance.py -v
```

**Result** (acceptance criteria):
- [x] Config load time: < 100ms (Pydantic adds ~5-10ms validation)

---

### 4.6 Type Checking

```bash
# Run mypy on updated files:
- [ ] mypy --strict apps/reference/config_models.py
- [ ] mypy --strict apps/reference/config_loader.py
- [ ] mypy --strict apps/reference/domains/ --no-error-summary 2>&1 | head -20

Result: 0 errors
```

**Commit**: `refactor: ensure strict type checking passes [FSMP-CFG-TYPE]`

---

### 4.7 IDE Autocomplete Verification (Manual)

```
Open apps/reference/domains/execution_position/fsm_manage.py in VS Code:

- [ ] Type "self.config." → autocomplete shows:
      trading, binance_api, account_observer, system, ops, decision, execution, ...

- [ ] Type "self.config.trading." → autocomplete shows:
      mode, decision, execution, instruments, market_data, feature_engineering

- [ ] Type "self.config.trading.decision." → autocomplete shows:
      testnet, production, signal_threshold, signal_weights, signals, position_sizing, kelly, qos, ...

- [ ] Type "self.config.trading.execution.manage.brackets." → autocomplete shows:
      sl, tp, oco_emulation, stop_loss_bps

- [ ] Hover over "self.config.trading.decision.kelly.kelly_cap" shows:
      "kelly_cap: float | None = ..."

✅ All autocomplete working
```

---

## Final Checklist: Definition of Done

### Code Quality
- [ ] All 677 `.get()` calls migrated to typed attributes
- [ ] grep "\.get(" shows only legitimate uses (env, dict, payload)
- [ ] Type hints added to all config-accessing methods
- [ ] Docstrings updated with config structure
- [ ] No new anti-patterns introduced

### Testing
- [ ] Unit tests: 100% pass
- [ ] Domain tests: 100% pass
- [ ] Integration tests: 100% pass
- [ ] Full test suite: 100% pass
- [ ] Coverage > 95% for config_models.py
- [ ] No flaky tests

### Validation
- [ ] Startup validation catches all config errors
- [ ] Pydantic models validate trading_mode, percentages, kelly_cap
- [ ] Error messages are clear and actionable
- [ ] Backward compat mode works (.get() still functional)

### Performance
- [ ] Config load time < 100ms
- [ ] No regression in FSM startup time
- [ ] No memory regression

### Documentation
- [ ] PYDANTIC_MIGRATION_PLAN.md completed
- [ ] CONFIG_REFERENCE.md generated
- [ ] Docstrings added to models
- [ ] Comments added to complex validations
- [ ] README updated with new config access pattern

### IDE & Developer Experience
- [ ] Autocomplete working in all editors
- [ ] Type checking passes (mypy --strict)
- [ ] Developers can `config.trading.decision.kelly_cap` directly
- [ ] No need to look up documentation for config structure

### Rollback
- [ ] Rollback procedure documented
- [ ] Test rollback successful
- [ ] Original functionality preserved if needed to revert

---

## Completion Sign-Off

```
✅ PHASE 1-1.5: COMPLETE (2 commits)
  - Pydantic models designed & validated
  - ConfigLoader updated with startup validation

⏳ PHASE 2: IN PROGRESS (4 commits target)
  - [ ] Tier 1: 4 critical domains (235 calls)

⏳ PHASE 3: PENDING (7 commits target)
  - [ ] Tier 2-4: All remaining files (370+ calls)

⏳ PHASE 4: PENDING (5 commits target)
  - [ ] Testing, validation, performance verification

GRAND TOTAL: ~16-18 commits over 3 weeks
TARGET: 100% completion by end of sprint 3
```

---

**Document Status**: Active Implementation Checklist
**Last Updated**: 2025-11-06
**Current Phase**: 2 Ready (Awaiting Execution)
