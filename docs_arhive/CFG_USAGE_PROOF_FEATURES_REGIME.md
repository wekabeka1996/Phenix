# CFG-FEATURES-REGIME-SSOT-04: Usage Proof Analysis

**Date**: 2025-12-17  
**Purpose**: Determine if `features.yaml` and `regime.yaml` are actively used in runtime

---

## 🔍 Investigation Summary

### 1. **regime.yaml** - ✅ ACTIVELY USED (LIVE CONFIG)

**File**: `config/aurora/regime.yaml`

**Evidence of Usage**:

1. **config_loader.py L298**: Explicitly loads regime.yaml
   ```python
   regime_config = self._load_yaml("regime.yaml")
   ```

2. **config_loader.py L314**: Merges regime_config into final config
   ```python
   deep_merge(regime_config, merged_config)   # Overlay regime (models, hmm, etc.)
   ```

3. **config_models.py L1619**: Pydantic model for regime config
   ```python
   models: Optional[RegimeModelsConfig] = Field(default=None, description="Regime detection models from regime.yaml")
   ```

4. **regime_detector.py L47**: RegimeDetector reads config.models
   ```python
   if hasattr(self.config, 'models'):
       models_cfg = (self.config.models or {})
   ```

5. **main.py L1379, L1724**: RegimeDetector instantiated with config
   ```python
   regime_detector = RegimeDetector(config_dict, fsm)
   # ...
   regime_detector = RegimeDetector(config=config.to_dict(), fsm=fsm)
   ```

**Conclusion**: `regime.yaml` is LIVE and FUNCTIONAL
- Contains HMM parameters, model configs (sma_trend, volatility, mean_reversion)
- Loaded by ConfigLoader → merged into AuroraConfig
- Consumed by RegimeDetector domain

---

### 2. **features.yaml** - ❌ ORPHANED CONFIG (DEAD)

**File**: `config/aurora/features.yaml`

**Evidence of Non-Usage**:

1. **config_loader.py**: NO reference to `features.yaml` loading
   - Searched pattern: `features\.yaml` → **0 matches** in config_loader.py
   - NO `_load_yaml("features.yaml")` call

2. **grep search results**:
   ```bash
   grep -rn "features\.yaml" apps/reference/
   # Result: 0 matches
   ```

3. **Feature config is read from domains.yaml**:
   - `config/aurora/domains.yaml` L36-75: Contains `feature_engineering:` section
   - `apps/reference/domains/feature_engineering/types.py` L147-151: Reads from:
     ```python
     if 'domains' in config and 'feature_engineering' in config.get('domains', {}):
         fe_dict = config['domains']['feature_engineering']
     elif 'trading' in config and 'feature_engineering' in config.get('trading', {}):
         fe_dict = config['trading']['feature_engineering']
     ```

4. **Duplicate configs detected**:
   - `config/aurora/features.yaml` L10: `feature_engineering:` (129 lines)
   - `config/aurora/domains.yaml` L36: `feature_engineering:` (active SSOT)
   - `config/aurora/trading.yaml` L256: `feature_engineering:` (DEPRECATED mirror)

**Conclusion**: `features.yaml` is ORPHANED
- NOT loaded by ConfigLoader
- NOT referenced anywhere in runtime code
- Duplicate of `domains.yaml` feature_engineering section
- Creates "two sources of truth" confusion

---

## 📊 Grep Search Results

### Search 1: File references
```bash
grep -rn "regime\.yaml|features\.yaml" apps/reference/
```

**Results**:
- `apps/reference/config_loader.py:298`: regime_config = self._load_yaml("regime.yaml")
- `apps/reference/config_models.py:552`: (comment) "Loaded from regime.yaml"
- `apps/reference/config_models.py:1618`: (comment) "loaded from regime.yaml"
- **features.yaml**: 0 matches

### Search 2: Config attribute access
```bash
grep -rn "config\.regime|config\.features" apps/reference/
```

**Results**:
- `config.features`: 0 matches (features accessed via domains.feature_engineering)
- `config.regime`: 0 direct matches (regime accessed via config.models)

### Search 3: Feature engineering access paths
```bash
grep -rn "feature_engineering:" config/aurora/
```

**Results**:
- `config/aurora/trading.yaml:256`: feature_engineering: (DEPRECATED)
- `config/aurora/trading.yaml:425`: feature_engineering: (DEPRECATED testnet)
- `config/aurora/trading.yaml:476`: feature_engineering: (DEPRECATED production)
- `config/aurora/features.yaml:10`: feature_engineering: (ORPHANED)
- `config/aurora/domains.yaml:36`: feature_engineering: (ACTIVE SSOT)

---

## 🎯 Conclusions

### regime.yaml Status: ✅ SSOT (Keep + Harden)

**Current State**:
- Actively loaded and used by runtime
- Contains HMM, models config (sma_trend, volatility, mean_reversion)
- Consumed by RegimeDetector domain

**Required Actions**:
1. ✅ Ensure Pydantic model has `extra='forbid'` (already done in RegimeModelsConfig)
2. ✅ Add strict validation test for extra keys
3. ✅ Document as SSOT in config docs

**Risk**: LOW (already working SSOT)

---

### features.yaml Status: ❌ DEPRECATED (Remove or Crash)

**Current State**:
- NOT loaded by ConfigLoader
- NOT referenced in runtime code
- Duplicate of domains.yaml feature_engineering section
- Creates confusion ("is this SSOT?")

**Required Actions**:
1. ❌ ConfigLoader: Detect features.yaml presence → **crash in strict mode**
2. ⚠️ ConfigLoader: Detect features.yaml presence → **WARNING in non-strict mode**
3. 📝 Update docs: "features.yaml is DEPRECATED, use domains.yaml"
4. 🧹 Future: Remove features.yaml entirely after migration period

**Risk**: ZERO (not used, removal is safe)

---

## 📋 Recommendations

### Immediate (This PR)

1. **regime.yaml**: Keep as SSOT
   - Add test: extra keys in regime.yaml → ValidationError (strict)
   - Document as canonical source for regime detection config

2. **features.yaml**: Deprecate with fail-closed
   - Add deprecated file detection in ConfigLoader
   - Strict mode: ValueError if features.yaml exists
   - Non-strict: WARNING log
   - Message: "features.yaml is deprecated/unused; migrate to domains.yaml"

### Future (Phase-5)

1. Remove features.yaml file after migration period
2. Consolidate trading.yaml feature_engineering mirrors → deprecate
3. Single SSOT: domains.yaml feature_engineering section

---

## 🧪 Test Plan

### A) regime.yaml strict validation
**File**: `tests/config/test_regime_yaml_strict_validation.py`

- Test 1: Valid regime.yaml → loads successfully
- Test 2: Extra key in regime.yaml → ValidationError (Pydantic extra='forbid')
- Test 3: Invalid HMM config → ValidationError

### B) features.yaml deprecated detection
**File**: `tests/config/test_features_yaml_deprecated_strict.py`

- Test 1: features.yaml exists + strict mode → ValueError "deprecated/unused"
- Test 2: features.yaml exists + non-strict → WARNING logged
- Test 3: features.yaml missing → no error (normal operation)

---

## 📚 References

**Config Files**:
- `config/aurora/regime.yaml` (ACTIVE SSOT - 100 lines)
- `config/aurora/features.yaml` (ORPHANED - 129 lines)
- `config/aurora/domains.yaml` (ACTIVE SSOT for feature_engineering)

**Code References**:
- `apps/reference/config_loader.py` L298, L314
- `apps/reference/config_models.py` L549, L1619
- `apps/reference/domains/regime_detector/regime_detector.py` L47
- `apps/reference/domains/feature_engineering/types.py` L147-151

**Detection Commands**:
```bash
# Verify regime.yaml usage
grep -rn "regime\.yaml" apps/reference/config_loader.py
grep -rn "config\.models" apps/reference/domains/regime_detector/

# Verify features.yaml non-usage
grep -rn "features\.yaml" apps/reference/config_loader.py  # 0 results
grep -rn "_load_yaml.*features" apps/reference/            # 0 results
```

---

**EOF**
