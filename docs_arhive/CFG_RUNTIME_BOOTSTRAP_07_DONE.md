# CFG-RUNTIME-BOOTSTRAP-07-MARKET-DATA-WORKER-CONFIG-PROOF: ВИКОНАНО

**TASK 07 DONE** ✅ (2025-12-17)

**Мета**: Прибрати ситуацію, коли `market_data_worker` стартує без symbols, і зробити **доказовий bootstrap**.

---

## 📊 Результат

**Bootstrap Proof Logging** ✅
- Worker логгує `config_name`, `config_dir`, `symbols_count`, `symbols_preview` при старті
- Видима трасованість звідки взявся config

**Enhanced Fail-Fast** ✅
- Empty symbols → ValueError з **діагностичною інформацією**:
  - config source (config_name, config_dir)
  - instruments.yaml existence check
  - Probable causes + Action required
- Прибрано "втемну" краш

**One Config Path** ✅
- `MarketDataProxy` отримує config через конструктор
- `MarketDataWorker` отримує серіалізований config_dict
- ConfigLoader додає metadata (`_config_name`, `_config_dir`)

---

## 🎯 Definition of Done (ВИКОНАНО)

### ✅ DoD 1: Worker завжди отримує канонічний AuroraConfig

**Verified**: 
- `main.py` L1532: `market_data = MarketDataProxy(fsm=fsm, config=config)`
- `config` отримується через `ConfigLoader().load_config()`
- `MarketDataProxy._get_config_dict()` серіалізує config для IPC
- `MarketDataWorker.__init__()` отримує `config_dict` через multiprocessing.Queue

**One path**: ✅ Немає альтернативних ініціалізацій

### ✅ DoD 2: Startup proof logging

**Implemented**: `apps/reference/domains/market_data/worker.py` L135-145

```python
# CFG-RUNTIME-BOOTSTRAP-07: Startup proof logging
config_name = config_dict.get("_config_name", "<unknown>")
config_dir = config_dict.get("_config_dir", "<unknown>")
symbols_count = len(self._symbols)
symbols_preview = self._symbols[:10] if symbols_count > 10 else self._symbols

self._logger.info(
    f"📋 BOOTSTRAP PROOF:\n"
    f"  config_name: {config_name}\n"
    f"  config_dir: {config_dir}\n"
    f"  symbols_count: {symbols_count}\n"
    f"  symbols_preview: {symbols_preview}\n"
    f"  anchors: {self._anchors}\n"
    f"  mode: {self._mode}"
)
```

**Output Example**:
```
📋 BOOTSTRAP PROOF:
  config_name: aurora
  config_dir: config/aurora
  symbols_count: 3
  symbols_preview: ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']
  anchors: ['BTCUSDT']
  mode: testnet
```

### ✅ DoD 3: Enhanced fail-fast error messages

**Implemented**: `apps/reference/domains/market_data/worker.py` L148-175

```python
if not self._symbols:
    # Diagnostic information for empty symbols
    import os
    from pathlib import Path
    
    instruments_yaml_path = Path(config_dir) / "instruments.yaml" if config_dir != "<unknown>" else None
    instruments_exists = instruments_yaml_path.exists() if instruments_yaml_path else "unknown"
    
    error_msg = (
        "❌ BOOTSTRAP FAILED: No symbols configured!\n\n"
        "Diagnostic information:\n"
        f"  config_name: {config_name}\n"
        f"  config_dir: {config_dir}\n"
        f"  config_dict['trading']['instruments']: {instruments}\n"
        f"  instruments.yaml exists: {instruments_exists}\n"
        f"  instruments.yaml path: {instruments_yaml_path}\n\n"
        "Probable causes:\n"
        "  1. config/aurora/instruments.yaml is empty or missing\n"
        "  2. instruments.yaml structure is invalid (check YAML syntax)\n"
        "  3. ConfigLoader failed to load instruments.yaml\n\n"
        "Action required:\n"
        "  - Check config/aurora/instruments.yaml exists and contains symbols\n"
        "  - Run: python -c 'from apps.reference.config_loader import get_config; c=get_config(); print(list(c.trading.instruments.keys()))'\n"
        "  - See docs/CFG_USAGE_PROOF_FEATURES_REGIME.md for SSOT structure"
    )
    
    self._logger.critical(error_msg)
    raise ValueError(error_msg)
```

**Before** (невидимо):
```
ValueError: No symbols configured! Please check config/aurora/instruments.yaml (SSOT).
```

**After** (діагностичне):
```
❌ BOOTSTRAP FAILED: No symbols configured!

Diagnostic information:
  config_name: aurora
  config_dir: config/aurora
  config_dict['trading']['instruments']: {}
  instruments.yaml exists: True
  instruments.yaml path: config/aurora/instruments.yaml

Probable causes:
  1. config/aurora/instruments.yaml is empty or missing
  2. instruments.yaml structure is invalid (check YAML syntax)
  3. ConfigLoader failed to load instruments.yaml

Action required:
  - Check config/aurora/instruments.yaml exists and contains symbols
  - Run: python -c '...'
  - See docs/CFG_USAGE_PROOF_FEATURES_REGIME.md for SSOT structure
```

### ✅ DoD 4: Тести для fail-fast scenarios

**Created**: `tests/runtime/test_market_data_worker_bootstrap.py` (6 tests)

#### Test Suite A: Worker Bootstrap

1. **test_empty_instruments_fails_with_diagnostic** ✅
   - Empty instruments → ValueError with diagnostic info
   - Verifies: "BOOTSTRAP FAILED", config_name, config_dir, "Probable causes", "Action required"

2. **test_valid_instruments_logs_bootstrap_proof** ✅
   - Valid instruments → bootstrap proof logged
   - Verifies: "BOOTSTRAP PROOF", config_name, config_dir, symbols_count, symbols list

3. **test_missing_config_metadata_uses_defaults** ✅
   - Missing `_config_name`/`_config_dir` → uses `<unknown>` defaults
   - Backward compatibility test

4. **test_large_symbols_list_truncated_in_log** ✅
   - 20 symbols → preview shows first 10 only
   - Avoids log spam

#### Test Suite B: Proxy Config Metadata

5. **test_proxy_adds_config_metadata** ✅
   - `MarketDataProxy._get_config_dict()` adds `_config_name`, `_config_dir`
   - Metadata propagation verified

6. **test_proxy_uses_defaults_if_metadata_missing** ✅
   - Missing metadata → uses defaults ("aurora", "config/aurora")
   - Backward compatibility

---

## 🧪 Test Results

```bash
$ python -m pytest tests/config/ tests/runtime/test_market_data_worker_bootstrap.py -q
============================= test session starts ======================================
collected 28 items

tests/config/test_config_symbols_one_truth.py ......                                     [ 21%]
tests/config/test_features_yaml_deprecated_strict.py ...                                 [ 32%]
tests/config/test_regime_yaml_strict_validation.py ...                                   [ 42%]
tests/config/test_strategies_registry_strict.py ......                                   [ 64%]
tests/config/test_strategy_profiles_registry_load.py ....                                [ 78%]
tests/runtime/test_market_data_worker_bootstrap.py ......                                [100%]

====================================== 28 passed in 0.21s ======================================
```

**Status**: ✅ 28/28 тестів пройшли (6 нових, 0 failed)

---

## 📝 Code Changes

### 1. Worker Bootstrap Proof Logging
**File**: `apps/reference/domains/market_data/worker.py`  
**Lines**: L135-145 (added), L148-175 (enhanced)

**Changes**:
- Added startup proof logging before fail-fast check
- Logs: config_name, config_dir, symbols_count, symbols_preview, anchors, mode
- Enhanced ValueError with diagnostic information:
  - Config source traceability
  - instruments.yaml existence check
  - Probable causes list
  - Actionable remediation steps

**Impact**: Worker краш → завжди показує чому і як виправити

### 2. Proxy Config Metadata
**File**: `apps/reference/domains/market_data/proxy.py`  
**Lines**: L83-104 (modified)

**Changes**:
- `_get_config_dict()` додає `_config_name` та `_config_dir` до серіалізованого config
- Uses `getattr()` з defaults для backward compatibility
- Metadata propagates from ConfigLoader → Proxy → Worker

**Impact**: Worker завжди знає звідки взявся config

### 3. ConfigLoader Metadata
**File**: `apps/reference/config_loader.py`  
**Lines**: L57-59 (added), L633-635 (added)

**Changes**:
- `__init__()`: додано `self.config_name = "aurora"`
- `load_config()`: додано metadata до resolved_config:
  ```python
  resolved_config['_config_name'] = self.config_name
  resolved_config['_config_dir'] = str(self.config_dir)
  ```

**Impact**: Config source трасується через весь pipeline

### 4. Tests
**File**: `tests/runtime/test_market_data_worker_bootstrap.py` (NEW)  
**Size**: 6 tests covering:
- Empty instruments fail-fast
- Bootstrap proof logging
- Metadata propagation
- Backward compatibility
- Large symbols list truncation

---

## 🔍 Bootstrap Flow

### Config Initialization Flow

```
1. main.py
   ├─> ConfigLoader().load_config()
   │   ├─> self.config_name = "aurora"
   │   ├─> self.config_dir = Path("config/aurora")
   │   ├─> Load YAML files (system, trading, regime, domains, instruments, strategies)
   │   ├─> Merge configs (deep_merge)
   │   ├─> Pydantic validation
   │   └─> Add metadata: _config_name, _config_dir
   └─> config: AuroraConfig (with metadata)

2. main.py L1532
   ├─> MarketDataProxy(fsm=fsm, config=config)
   │   ├─> self._config = config (store reference)
   │   └─> Extract symbols for logging (L77)

3. MarketDataProxy.start_async() L283
   ├─> config_dict = self._get_config_dict()
   │   ├─> config.model_dump() → dict
   │   ├─> Add _config_name (from config or default "aurora")
   │   └─> Add _config_dir (from config or default "config/aurora")
   ├─> Process.spawn(worker_entrypoint, args=(ipc_queue, config_dict, log_dir))

4. worker_entrypoint() L464
   ├─> logger = _configure_worker_logging(log_dir)
   ├─> worker = MarketDataWorker(ipc_queue, config_dict, logger)

5. MarketDataWorker.__init__() L107
   ├─> Parse config_dict['trading']['instruments'] → self._symbols
   ├─> Extract metadata: config_name, config_dir
   ├─> LOG: BOOTSTRAP PROOF (config_name, config_dir, symbols_count, symbols_preview)
   ├─> IF symbols empty → LOG: BOOTSTRAP FAILED (diagnostic error)
   └─> Initialize WebSocketAggregator
```

### Error Flow (Empty Symbols)

```
1. MarketDataWorker.__init__() detects empty symbols
2. Check instruments.yaml exists at config_dir/instruments.yaml
3. Build diagnostic error message:
   - Config source (config_name, config_dir)
   - instruments.yaml path and existence
   - trading.instruments content
   - Probable causes (3 scenarios)
   - Action required (verification commands)
4. logger.critical(error_msg)
5. raise ValueError(error_msg) → worker_entrypoint catches → logs "Failed to create worker"
6. Main process sees worker died → can diagnose from log
```

---

## 🎓 Architecture Decisions

### AD-1: Config metadata propagation

**Rationale**:
- Worker process має власний memory space (multiprocessing isolation)
- Config серіалізується через pickle/JSON для IPC
- Metadata (`_config_name`, `_config_dir`) потрібна для diagnostic logging
- **Decision**: Add metadata in ConfigLoader, propagate through Proxy → Worker

**Implementation**:
- ConfigLoader stores `config_name` as instance attribute
- `load_config()` adds metadata to final resolved_config
- Proxy `_get_config_dict()` ensures metadata present (uses defaults if missing)
- Worker reads metadata from config_dict for logging

**Benefits**:
- Full traceability: worker log shows exact config source
- Backward compatible: missing metadata → defaults
- Single source of truth: ConfigLoader → Proxy → Worker

### AD-2: Startup proof logging BEFORE fail-fast

**Rationale**:
- Empty symbols crash was "blind" (no context)
- Needed to prove: worker received config, parsed it, saw empty symbols
- **Decision**: Log bootstrap proof BEFORE checking symbols

**Implementation**:
- Parse config_dict (trading, instruments, market_data, etc.)
- Extract metadata (config_name, config_dir)
- Log bootstrap proof (config source + parsed state)
- THEN check if symbols empty → fail-fast with diagnostic

**Benefits**:
- Worker crash log shows: received config X, parsed Y symbols, failed at Z
- Diagnostic error has full context (config source, file paths, content)
- No more "No symbols configured" without knowing why

### AD-3: Enhanced diagnostic error messages

**Rationale**:
- Generic "No symbols configured" → user asks "why?"
- Bootstrap failure needs actionable remediation
- **Decision**: Build comprehensive diagnostic error with:
  - Config source (config_name, config_dir)
  - File existence check (instruments.yaml)
  - Content dump (trading.instruments value)
  - Probable causes (3 scenarios)
  - Action required (verification commands)

**Implementation**:
- Check `instruments_yaml_path.exists()` at runtime
- Include `config_dict['trading']['instruments']` in error
- List probable causes (missing file, invalid YAML, loader failure)
- Provide verification command (get_config() test)
- Reference SSOT documentation

**Benefits**:
- Self-service debugging: user sees exact problem
- Reduces "ask for help" → "check file X, run command Y"
- Links to documentation (SSOT structure)

---

## 🚦 Troubleshooting Guide

### Symptom: Worker process dies with "No symbols configured"

**Before TASK 07** (невидимо):
```
ValueError: No symbols configured! Please check config/aurora/instruments.yaml (SSOT).
```

**After TASK 07** (діагностичне):
```
❌ BOOTSTRAP FAILED: No symbols configured!

Diagnostic information:
  config_name: aurora
  config_dir: config/aurora
  config_dict['trading']['instruments']: {}
  instruments.yaml exists: True
  instruments.yaml path: config/aurora/instruments.yaml

Probable causes:
  1. config/aurora/instruments.yaml is empty or missing
  2. instruments.yaml structure is invalid (check YAML syntax)
  3. ConfigLoader failed to load instruments.yaml

Action required:
  - Check config/aurora/instruments.yaml exists and contains symbols
  - Run: python -c 'from apps.reference.config_loader import get_config; c=get_config(); print(list(c.trading.instruments.keys()))'
  - See docs/CFG_USAGE_PROOF_FEATURES_REGIME.md for SSOT structure
```

### Verification Steps

1. **Check instruments.yaml exists**:
   ```bash
   ls -la config/aurora/instruments.yaml
   ```

2. **Check instruments.yaml content**:
   ```bash
   head -20 config/aurora/instruments.yaml
   ```

3. **Verify ConfigLoader reads instruments**:
   ```python
   from apps.reference.config_loader import get_config
   config = get_config()
   print(f"Symbols: {list(config.trading.instruments.keys())}")
   ```

4. **Check worker bootstrap log**:
   ```bash
   tail -100 logs/aurora_market_data.log | grep "BOOTSTRAP PROOF"
   ```

### Common Causes

1. **Empty instruments.yaml**:
   - File exists but contains no symbols
   - **Fix**: Add instruments (see config/aurora/instruments.yaml example)

2. **Invalid YAML syntax**:
   - YAML parse error → ConfigLoader falls back to empty dict
   - **Fix**: Validate YAML syntax (`yamllint config/aurora/instruments.yaml`)

3. **Wrong config_dir**:
   - ConfigLoader looking in wrong directory
   - **Fix**: Check `BOOTSTRAP PROOF` log shows correct `config_dir`

4. **Instruments under wrong key**:
   - instruments defined at wrong YAML level
   - **Fix**: instruments should be at root level (not nested)

---

## 📚 Related Tasks

- **TASK 06**: CFG-FEATURES-REGIME-SSOT-04 ✅ (regime.yaml SSOT, features.yaml deprecated)
- **TASK 05**: CFG-STRATEGIES-SSOT-03 ✅ (strategies registry SSOT)
- **TASK 04**: CFG-TRADING-YAML-BURN-DOWN-02 ✅ (domains.yaml SSOT)

---

## ✅ Checklist

- [x] Знайти entrypoint створення market_data_worker (main.py → MarketDataProxy)
- [x] Додати startup proof-лог (config_dir, symbols_count, symbols_preview)
- [x] Покращити помилку "No symbols configured" (diagnostic info)
- [x] ConfigLoader додає metadata (_config_name, _config_dir)
- [x] Proxy propagates metadata до worker
- [x] Worker logs bootstrap proof BEFORE fail-fast
- [x] Створити тести для fail-fast scenarios (6 tests)
- [x] Всі тести пройшли (28/28)
- [x] Фінальний звіт

---

## 🎉 Final Status

**TASK 07 COMPLETE**: CFG-RUNTIME-BOOTSTRAP-07-MARKET-DATA-WORKER-CONFIG-PROOF

**Test Results**: ✅ 28/28 passed (6 new tests, 0 failed)

**Definition of Done**: ✅ 4/4 requirements met

**Impact**:
- Worker більше не падає "втемну"
- Bootstrap proof logging → full traceability
- Enhanced error messages → self-service debugging
- One config path → no альтернативних ініціалізацій

**Next Steps**:
- **Phase-5**: Burn-down дубляжу MR параметрів у trading.yaml
- **Phase-6**: Strict mode by default + CI gates
- **Phase-7**: Config freeze + version tagging

---

**Created**: 2025-12-17  
**Author**: Senior+ Staff Engineer (AI)  
**Phase**: Phase-4 (runtime bootstrap proof)
