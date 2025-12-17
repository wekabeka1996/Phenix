# CFG-FEATURES-REGIME-SSOT-04-LIVE-OR-DEPRECATE: ВИКОНАНО

**TASK 06 DONE** ✅ (2024-12-30)

**Мета**: Закрити питання `regime.yaml` і `features.yaml` у стилі SSOT (Single Source of Truth).

---

## 📊 Результат

**features.yaml** → **ORPHANED (DEPRECATED)**
- ❌ НЕ завантажується ConfigLoader (0 matches у коді)
- ❌ Дублікат domains.yaml → створює "two sources of truth"
- ✅ Реалізовано deprecated detection (fail-closed у strict mode)

**regime.yaml** → **LIVE SSOT**
- ✅ Активно завантажується (config_loader.py L298)
- ✅ Використовується RegimeDetector domain
- ✅ Загартований з `extra='forbid'` на `RegimeModelsConfig`

---

## 🎯 Definition of Done (ВИКОНАНО)

### ✅ DoD 1: Документ-доказ наявності usage

**Створено**: [docs/CFG_USAGE_PROOF_FEATURES_REGIME.md](docs/CFG_USAGE_PROOF_FEATURES_REGIME.md) (~250 рядків)

**Зміст**:
- grep-результати: `regime_config = self._load_yaml("regime.yaml")` (L298)
- grep-результати: 0 matches для `_load_yaml("features.yaml")`
- Consumption proof: regime_detector.py L47 читає `config.models`
- Feature path analysis: domains.yaml (SSOT) vs features.yaml (orphaned)

### ✅ DoD 2: features.yaml → deprecated з crash у strict mode

**Реалізовано**: [apps/reference/config_loader.py](apps/reference/config_loader.py) L305-334

```python
# DEPRECATED FILE DETECTION (CFG-FEATURES-REGIME-SSOT-04)
features_yaml_path = self.config_dir / "features.yaml"
if features_yaml_path.exists():
    msg = (
        "⚠️  DEPRECATED: features.yaml detected! "
        "This file is NOT loaded by ConfigLoader (orphaned config). "
        "Feature engineering config is read from domains.yaml (SSOT). "
        "Action required: Remove features.yaml or migrate to domains.yaml."
    )
    
    if strict_mode:  # STRICT_CONFIG_CONFLICTS=1
        raise ValueError(msg)
    else:
        LOG.warning(msg)
```

**Поведінка**:
- `STRICT_CONFIG_CONFLICTS=1` → ValueError (fail-closed)
- Non-strict → WARNING log (migration path)

### ✅ DoD 3: regime.yaml → typed + extra='forbid'

**Реалізовано**: [apps/reference/config_models.py](apps/reference/config_models.py) L549-558

```python
class RegimeModelsConfig(BaseModel):
    """Container for all regime detection model configurations.
    
    Loaded from regime.yaml 'models' section.
    
    CFG-FEATURES-REGIME-SSOT-04: extra='forbid' for strict validation
    """
    model_config = ConfigDict(extra='forbid')  # ← Changed from 'allow'
    
    sma_trend: SMARegimeModelConfig = Field(...)
    volatility: VolatilityRegimeModelConfig = Field(...)
    mean_reversion: MeanReversionRegimeModelConfig = Field(...)
```

**Ефект**: Extra keys у `regime.yaml models` → Pydantic ValidationError

### ✅ DoD 4: Тести для strict validation

**Створено 6 тестів** (22/22 passed):

#### Test File 1: [tests/config/test_features_yaml_deprecated_strict.py](tests/config/test_features_yaml_deprecated_strict.py)

1. **test_features_yaml_exists_strict_mode_crashes** ✅
   - features.yaml exists + `STRICT_CONFIG_CONFLICTS=1` → ValueError
   - Перевірка: error message містить "deprecated" та "features.yaml"

2. **test_features_yaml_exists_non_strict_warns** ✅
   - features.yaml exists + non-strict → WARNING logged
   - Config завантажується успішно (migration path)

3. **test_features_yaml_missing_no_error** ✅
   - features.yaml відсутній → no error
   - Normal operation without orphaned file

#### Test File 2: [tests/config/test_regime_yaml_strict_validation.py](tests/config/test_regime_yaml_strict_validation.py)

4. **test_valid_regime_yaml_loads_successfully** ✅
   - Valid regime.yaml (hmm + models) → loads successfully
   - Перевірка: config.models.sma_trend.sma_short_period == 10

5. **test_extra_key_in_regime_models_fails_validation** ✅
   - Extra key `unknown_model` in regime.yaml models → ValidationError
   - Перевірка: error містить "unknown_model" або "extra"

6. **test_minimal_regime_yaml_loads** ✅
   - Minimal regime.yaml (порожній models) → loads with defaults
   - Default factory values work correctly

---

## 🧪 Test Results

```bash
$ python -m pytest tests/config/ -q
===================================== test session starts ======================================
collected 22 items

tests/config/test_config_symbols_one_truth.py ......                                     [ 27%]
tests/config/test_features_yaml_deprecated_strict.py ...                                 [ 40%]
tests/config/test_regime_yaml_strict_validation.py ...                                   [ 54%]
tests/config/test_strategies_registry_strict.py ......                                   [ 81%]
tests/config/test_strategy_profiles_registry_load.py ....                                [100%]

====================================== 22 passed in 0.16s ======================================
```

**Статус**: ✅ 22/22 тестів пройшли (0 failed)

---

## 🔍 Evidence Summary

### regime.yaml (LIVE ✅)

**Load proof**:
```python
# apps/reference/config_loader.py L298
regime_config = self._load_yaml("regime.yaml")

# L337 - merged into final config
deep_merge(regime_config, merged_config)
```

**Consumption proof**:
```python
# vfoundation/domains/regime_detector.py L47
models_cfg = (self.config.models or {})
# Uses: sma_trend, volatility, mean_reversion models
```

**Structure** (config/aurora/regime.yaml):
```yaml
hmm:  # TOP-LEVEL (used by HMM detector)
  enabled: true
  K: 3

models:  # TOP-LEVEL (validated by RegimeModelsConfig)
  sma_trend:
    sma_short_period: 10
  volatility:
    atr_period: 14
  mean_reversion:
    threshold: 0.005
```

### features.yaml (ORPHANED ❌)

**Non-load proof**:
```bash
$ grep '_load_yaml.*features' apps/reference/config_loader.py
# 0 results → NOT loaded
```

**Duplication proof**:
```bash
$ grep -r 'feature_engineering:' config/aurora/
config/aurora/features.yaml:10:  feature_engineering:
config/aurora/domains.yaml:36:  feature_engineering:  # ← CANONICAL SSOT
```

**Decision**: DEPRECATE with fail-closed (strict mode crashes)

---

## 📝 Code Changes

### 1. Config Loader (deprecated detection)
**File**: `apps/reference/config_loader.py`  
**Lines**: L305-334  
**Change**: Added features.yaml deprecated file detection
```python
# Check if orphaned features.yaml exists
features_yaml_path = self.config_dir / "features.yaml"
if features_yaml_path.exists():
    if strict_mode:
        raise ValueError("⚠️  DEPRECATED: features.yaml detected!")
    else:
        LOG.warning(msg)
```

### 2. Config Models (strict validation)
**File**: `apps/reference/config_models.py`  
**Lines**: L549-558  
**Change**: RegimeModelsConfig → `extra='forbid'`
```python
class RegimeModelsConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')  # Changed from 'allow'
```

### 3. Documentation
**File**: `docs/CFG_USAGE_PROOF_FEATURES_REGIME.md` (NEW)  
**Size**: ~250 рядків  
**Content**: Grep results, consumption proof, structure analysis

### 4. Tests
**Files**: 
- `tests/config/test_features_yaml_deprecated_strict.py` (NEW, 3 tests)
- `tests/config/test_regime_yaml_strict_validation.py` (NEW, 3 tests)

### 5. Bug Fix
**File**: `tests/config/test_strategies_registry_strict.py`  
**Change**: Fixed `base_regime_yaml` fixture structure
```yaml
# BEFORE (wrong):
models:
  hmm:
    enabled: false

# AFTER (correct):
hmm:
  enabled: false
models:
  sma_trend: {...}
```

---

## 🚦 Migration Guide

### Для користувачів з features.yaml:

#### Option A: Remove orphaned file (recommended)
```bash
rm config/aurora/features.yaml
# domains.yaml є єдине джерело правди для feature_engineering
```

#### Option B: Migrate to domains.yaml
```bash
# Перевірити чи features.yaml містить унікальні параметри:
diff config/aurora/features.yaml config/aurora/domains.yaml

# Якщо є відмінності → скопіювати в domains.yaml:
# Edit domains.yaml feature_engineering section

# Видалити features.yaml:
rm config/aurora/features.yaml
```

#### Option C: Non-strict mode (temporary)
```bash
# Не встановлювати STRICT_CONFIG_CONFLICTS
# features.yaml буде ignored з WARNING log
# Use for gradual migration
```

### Для розробників:

**Strict mode testing**:
```bash
export STRICT_CONFIG_CONFLICTS=1
python -m pytest tests/config/test_features_yaml_deprecated_strict.py -v
```

**Regime validation testing**:
```bash
python -m pytest tests/config/test_regime_yaml_strict_validation.py -v
```

---

## 🎓 Architecture Decisions

### AD-1: features.yaml → ORPHANED (not loaded)

**Rationale**:
- Grep search: 0 matches для `_load_yaml("features.yaml")`
- Exact duplicate of domains.yaml feature_engineering
- Creates "two sources of truth" confusion
- **Decision**: DEPRECATE with fail-closed

**Implementation**:
- Detection block in config_loader.py L305-334
- Strict mode: ValueError (prevent silent ignore)
- Non-strict: WARNING (migration path)

### AD-2: regime.yaml → SSOT with extra='forbid'

**Rationale**:
- Actively loaded (config_loader.py L298)
- Consumed by RegimeDetector domain
- Contains critical HMM + models config
- **Decision**: Harden as SSOT with strict validation

**Implementation**:
- RegimeModelsConfig: `extra='forbid'` (L557)
- Extra keys → Pydantic ValidationError
- Fail-fast on typos/deprecated keys

### AD-3: Fail-closed principle

**Rationale**:
- Silent config ignore → runtime bugs
- Strict mode forces explicit migration
- Non-strict mode for gradual transition
- **Decision**: STRICT_CONFIG_CONFLICTS env var

**Implementation**:
- `STRICT_CONFIG_CONFLICTS=1` → ValueError on deprecated files
- `STRICT_CONFIG_CONFLICTS=0` (default) → WARNING log
- Clear error messages with migration instructions

---

## 📚 Related Tasks

- **TASK 05**: CFG-STRATEGIES-SSOT-03-REGISTRY-DRIVEN-LOADING ✅ (16/16 tests)
- **TASK 04**: CFG-TRADING-YAML-BURN-DOWN-02 ✅ (domains.yaml SSOT)
- **TASK 03**: CFG-DOMAINS-STEP-02-PROOF ✅ (domains mirror deprecation)

---

## ✅ Checklist

- [x] Інвентаризація usage (grep searches)
- [x] Документ-доказ (CFG_USAGE_PROOF_FEATURES_REGIME.md)
- [x] features.yaml deprecated detection (fail-closed)
- [x] regime.yaml strict validation (extra='forbid')
- [x] Тести для deprecated/strict scenarios (6 tests)
- [x] Всі config тести пройшли (22/22)
- [x] Bug fix (base_regime_yaml structure)
- [x] Фінальний звіт

---

## 🎉 Final Status

**TASK 06 COMPLETE**: CFG-FEATURES-REGIME-SSOT-04-LIVE-OR-DEPRECATE

**Test Results**: ✅ 22/22 passed (0 failed)

**Definition of Done**: ✅ 4/4 requirements met

**Next Steps**:
- Розглянути видалення config/aurora/features.yaml (якщо не використовується)
- Продовжити SSOT migrations (Phase-5+)

---

**Created**: 2025-12-17  
**Author**: Senior+ Staff Engineer (AI)  
**Phase**: Phase-4 (features/regime SSOT)
