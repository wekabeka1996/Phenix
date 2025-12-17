# Config System: SSOT Freeze Map

**Status**: 🔒 **FROZEN** (strict-by-default enforced, CI gates active)  
**Last Updated**: 2025-12-01  
**Related**: [PYDANTIC_PROJECT_COMPLETION.md](PYDANTIC_PROJECT_COMPLETION.md)

---

## 🎯 Design Principles

### Single Source of Truth (SSOT)
Each configuration concept has **exactly one** authoritative location. Duplicates are **forbidden** by default.

### Strict-by-Default
- **Default Mode**: `STRICT_CONFIG_CONFLICTS=1` (enforced)
- **Opt-Out**: `export STRICT_CONFIG_CONFLICTS=0` (migrations only, deprecated)
- **CI Gate**: Strict mode validation runs on every PR

### Deprecation Policy
- Orphaned/duplicate configs → **ValueError** in strict mode
- Legacy `extra='allow'` → audit complete, critical paths use `extra='forbid'`
- Sunset date for remaining `extra='allow'`: 2025-01-15

---

## 📁 SSOT Hierarchy

### 1. Instruments (`config/aurora/instruments.yaml`)
**SSOT for**: Trading pairs, contract specs, exchange-specific settings

```yaml
instruments:
  BTCUSDT:
    exchange: binance
    type: spot
    min_notional: 10.0
```

**Deprecated alternatives**:
- ❌ `trading.yaml: instruments` (use `instruments.yaml`)
- ❌ `aurora_instruments.yaml` (merged into `instruments.yaml`)

---

### 2. Domains (`config/aurora/domains.yaml`)
**SSOT for**: 
- Domain definitions (symbol groups)
- Feature engineering config (global)

```yaml
domains:
  default:
    name: default
    symbols: [BTCUSDT, ETHUSDT]

feature_engineering:  # SSOT (formerly in trading.yaml)
  enabled: true
  lookback_periods: [60, 300, 900]
```

**Deprecated alternatives**:
- ❌ `trading.yaml: domains` (use `domains.yaml`)
- ❌ `trading.yaml: feature_engineering` (use `domains.yaml`)

---

### 3. Regime Detection (`config/aurora/regime.yaml`)
**SSOT for**: HMM, ML models for market regime classification

```yaml
models:
  hmm_v1:
    type: gaussian_hmm
    n_states: 3

hmm:
  states: 3
  covariance_type: full
```

**Extra validation**: `extra='forbid'` (strictest, no unknown keys allowed)

**Deprecated alternatives**:
- ❌ `features.yaml` (orphaned file, removed in CFG-FEATURES-REGIME-SSOT-04)

---

### 4. Strategies (`config/aurora/strategies.yaml`)
**SSOT for**: Strategy registry, assignments, arbitration

```yaml
assignments:
  BTCUSDT:
    - mean_reversion_1m
    - aurora

arbitration:
  mode: priority  # or weighted, ensemble
  conflict_resolution: first_wins
```

**Strategy Profiles**: `config/aurora/strategies/*.yaml`
- Each strategy = standalone YAML profile
- Registered in `strategies.yaml: assignments`
- No inline config in `trading.yaml`

**Deprecated alternatives**:
- ❌ `trading.yaml: mean_reversion_1m` (use `strategies/mean_reversion_1m.yaml`)
- ❌ `trading.yaml: aurora` (use `strategies/aurora.yaml`)

---

### 5. Runtime Config (`config/aurora/trading.yaml`)
**SSOT for**: Runtime settings, exchange connection, logging, execution mode

```yaml
runtime:
  mode: live  # or backtest, testnet
  exchange: binance
  log_level: INFO
  testnet: false

execution:
  order_type: limit
  max_slippage_bps: 10
```

**Clean State**: All strategy/domain/feature engineering sections **removed** (strict mode enforces)

---

## 🚫 Deprecated Sections (Strict Mode → ValueError)

### Detected Patterns

| Deprecated Section | Location | SSOT Replacement | Task | Status |
|--------------------|----------|------------------|------|--------|
| `features.yaml` | `config/aurora/features.yaml` | `regime.yaml` | CFG-FEATURES-REGIME-SSOT-04 | ✅ DONE (22 tests) |
| `trading.yaml: domains` | `trading.yaml: domains` | `domains.yaml` | CFG-DOMAINS-STEP02 | ✅ DONE (prev) |
| `trading.yaml: mean_reversion_1m` | `trading.yaml: mean_reversion_1m` | `strategies/mean_reversion_1m.yaml` | CFG-STRATEGIES-SSOT-05 | ✅ DONE (27 tests) |
| `trading.yaml: feature_engineering` | `trading.yaml: feature_engineering` | `domains.yaml: feature_engineering` | CFG-FREEZE-SSOT-06 | ✅ DONE (this task) |

### How Detection Works

**config_loader.py** (`apps/reference/config_loader.py`):
```python
@staticmethod
def _get_strict_mode() -> bool:
    """Strict mode by default (opt-out for migrations)."""
    return os.getenv("STRICT_CONFIG_CONFLICTS", "1").strip() in ("1", "true", "True", "yes")
```

**Example Detection (feature_engineering)**:
```python
if feature_eng_found:
    msg = (
        f"⚠️  DEPRECATED: feature_engineering detected in trading.yaml at: {locations_str}! "
        "This section is IGNORED (domains.yaml has priority). "
        "SSOT for feature_engineering: config/aurora/domains.yaml."
    )
    if strict_mode:
        raise ValueError(msg)  # CI fails, user alerted
    else:
        LOG.warning(msg)  # Legacy mode (deprecated)
```

---

## 🧪 Testing Strategy

### Test Coverage
**File**: `tests/config/test_strict_default_and_ci_gates.py`

| Test | Scenario | Expected |
|------|----------|----------|
| T1 | Strict mode default active (no env) | `_get_strict_mode() == True` |
| T2 | Opt-out works (`STRICT_CONFIG_CONFLICTS=0`) | `_get_strict_mode() == False` |
| T3 | `trading.yaml` with `feature_engineering` + strict | `ValueError` |
| T4 | `trading.yaml` with `feature_engineering` + non-strict | `WARNING` |
| T5 | Clean config (no deprecated sections) + strict | Load success |
| T6a | Sanity: `features.yaml` + strict | `ValueError` (TASK 06 regression) |
| T6b | Sanity: `trading.yaml: mean_reversion_1m` + strict | `ValueError` (TASK 08 regression) |

### CI Gate
**File**: `.github/workflows/ci.yml`

```yaml
strict-config:
  name: Strict Config Validation (CFG-FREEZE-SSOT-06)
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
    - name: Set up Python 3.11
      uses: actions/setup-python@v5
      with:
        python-version: '3.11'
    - name: Install dependencies
      run: pip install -r requirements.txt
    - name: Run strict config load test
      run: |
        export STRICT_CONFIG_CONFLICTS=1
        python -c "from apps.reference.config_loader import ConfigLoader; loader = ConfigLoader(); print('✅ STRICT_LOAD_OK')"
```

**Failure Mode**: If deprecated section exists → CI fails → PR blocked

---

## 📊 Legacy Audit: `extra='allow'`

### Pattern Analysis
**File**: `apps/reference/config_models.py`  
**Count**: 20+ occurrences of `model_config = ConfigDict(extra='allow')`

### Categorization

#### Critical Paths (Changed to `extra='forbid'` or deprecated)
- ✅ `RegimeConfig` (regime.yaml) → `extra='forbid'` (strictest)
- ⏳ `TradingConfig` (trading.yaml) → audit in progress, deprecation warnings added
- ⏳ `StrategyProfileConfig` → review needed (may need allow for extensibility)

#### Non-Critical (Remaining `extra='allow'` with justification)
- `DomainConfig`: Allows custom domain metadata (extensibility needed)
- `InstrumentConfig`: Allows exchange-specific fields (justified)
- **Sunset Date**: 2025-01-15 (revisit after 6 weeks, convert to `extra='forbid'` if no custom fields used)

### Action Plan
1. ✅ Identify all `extra='allow'` locations (grep complete, 20+ found)
2. ⏳ Add deprecation warnings for critical paths (in progress)
3. ⏳ Convert critical paths to `extra='forbid'` (regime.yaml done, others pending)
4. 📅 Schedule sunset date (2025-01-15) for remaining `extra='allow'`

---

## 🔧 How to Add New Strategy

### Before (Deprecated)
```yaml
# config/aurora/trading.yaml (OLD WAY - FORBIDDEN)
mean_reversion_1m:  # ❌ ValueError in strict mode
  enabled: true
  lookback: 60
```

### After (SSOT Pattern)

**Step 1**: Create strategy profile
```yaml
# config/aurora/strategies/mean_reversion_1m.yaml
strategy:
  name: mean_reversion_1m
  version: v1.0.0
  enabled: true

parameters:
  lookback: 60
  entry_threshold: 2.0
  exit_threshold: 0.5
```

**Step 2**: Register in strategies.yaml
```yaml
# config/aurora/strategies.yaml
assignments:
  BTCUSDT:
    - mean_reversion_1m  # References strategies/mean_reversion_1m.yaml
```

**Step 3**: No changes needed in trading.yaml (clean runtime config only)

---

## 🚀 Migration Guide

### From Non-Strict to Strict

**Scenario**: You have legacy config with deprecated sections

**Step 1**: Audit deprecated sections
```bash
# Check for deprecated patterns
grep -r "feature_engineering" config/aurora/trading.yaml
grep -r "mean_reversion_1m" config/aurora/trading.yaml
ls config/aurora/features.yaml 2>/dev/null && echo "⚠️  features.yaml exists (orphaned)"
```

**Step 2**: Move to SSOT
```yaml
# Before: config/aurora/trading.yaml
feature_engineering:  # ❌ DEPRECATED
  enabled: true

# After: config/aurora/domains.yaml
feature_engineering:  # ✅ SSOT
  enabled: true
```

**Step 3**: Test with strict mode
```bash
export STRICT_CONFIG_CONFLICTS=1
python -c "from apps.reference.config_loader import ConfigLoader; ConfigLoader()"
# Should succeed or raise ValueError with clear fix instructions
```

**Step 4**: Remove deprecated sections from trading.yaml

**Step 5**: Re-run tests
```bash
pytest tests/config/test_strict_default_and_ci_gates.py -v
```

---

## 📈 Completion Metrics

| Task | Tests | Status | Completion |
|------|-------|--------|------------|
| CFG-INSTRUMENTS-SSOT-01 | N/A | ✅ DONE | 100% |
| CFG-DOMAINS-STEP02 | N/A | ✅ DONE | 100% |
| CFG-FEATURES-REGIME-SSOT-04 | 22/22 | ✅ DONE | 100% |
| CFG-RUNTIME-BOOTSTRAP-07 | 28/28 | ✅ DONE | 100% |
| CFG-STRATEGIES-SSOT-05 | 27/27 | ✅ DONE | 100% |
| CFG-FREEZE-SSOT-06 | 8/8 | ✅ DONE | 100% |

**Total**: 85+ tests passing, strict mode enforced, CI gates active

---

## 🔒 Freeze Enforcement Checklist

- ✅ Strict mode by default (`STRICT_CONFIG_CONFLICTS=1`)
- ✅ CI gate for strict validation (`.github/workflows/ci.yml`)
- ✅ All SSOT migrations complete (instruments, domains, regime, strategies)
- ✅ Deprecated section detection (features.yaml, MR, feature_engineering)
- ✅ Test coverage for strict-default behavior (8 scenarios)
- ⏳ Legacy `extra='allow'` audit (20+ identified, critical paths in progress)
- ✅ Documentation: SSOT map, migration guide, sunset dates

**Status**: 🎉 **Config system frozen at 95%** (legacy allow audit in progress, sunset 2025-01-15)

---

## 📚 Related Documentation

- [PYDANTIC_PROJECT_COMPLETION.md](PYDANTIC_PROJECT_COMPLETION.md) - Full migration history
- [SYMBOL_CONFIGURATION_GUIDE.md](SYMBOL_CONFIGURATION_GUIDE.md) - Instrument config patterns
- [FTR-08-CODEBASE-AUDIT-REPORT.md](../artifacts/FTR-08-CODEBASE-AUDIT-REPORT.md) - Codebase audit findings

---

## 🤝 Contributing

### Adding New Config Section
1. ✅ Identify SSOT location (which YAML file)
2. ✅ Add Pydantic model with `extra='forbid'` (prefer strict)
3. ✅ Add detection logic in `config_loader.py` for duplicates
4. ✅ Write tests (strict + non-strict scenarios)
5. ✅ Update this SSOT map

### Reporting Issues
If strict mode crashes unexpectedly:
1. Check error message for SSOT replacement path
2. Move config to correct YAML file
3. Remove deprecated section
4. Re-run with `STRICT_CONFIG_CONFLICTS=1`
5. If still failing → open issue with config snippet

---

**End of SSOT Freeze Map** 🔒
