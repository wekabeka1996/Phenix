# P1 Config Extraction — Review & Critique Report

**Дата**: 2025-01-22  
**Рецензент**: GitHub Copilot (Claude Opus 4.5)  
**Рівень**: Senior Python Architect  
**Статус**: ✅ APPROVED WITH CONDITIONS  

---

## 📋 Executive Summary

P1 Refactoring Plan ("Config Extraction") аналізує вилучення 3-х категорій hardcoded defaults до YAML SSOT:
1. **Fallback Config** — `exposure_guard.py:182`
2. **Aurora Handler Defaults** — `aurora_handler.py:254-280`
3. **Dynamic Anchors** — `feature_engineering.py`

### Verdict

| Item | Status | Risk | Recommendation |
|------|--------|------|----------------|
| Fallback Config Extraction | ✅ Ready | Low | Proceed |
| Aurora Handler Defaults | ⚠️ Conditional | Medium | Phased approach |
| Dynamic Anchors | ✅ **ALREADY DONE** | N/A | No work needed |

---

## 🔍 Detailed Analysis

### 1. FallbackConfig Schema Support

**Finding**: `FallbackConfig` вже існує в [config_models.py](../apps/reference/config_models.py#L825-L834)

```python
class FallbackConfig(BaseModel):
    """Fallback configuration for execution.
    
    CFG-TOPLEVEL-EXTRA-ALLOW-BURN-14: Typed (binance_adapter.py:1160, exposure_guard.py:205).
    """
    model_config = ConfigDict(extra='forbid')
    
    # Add fields when consumption patterns documented (currently used as empty dict)
```

**Проблема**: Модель існує, але поля **не визначені** (коментар "Add fields when consumption patterns documented").

**Solution**: Додати поля до `FallbackConfig`:

```python
class FallbackConfig(BaseModel):
    """Fallback configuration for execution."""
    model_config = ConfigDict(extra='forbid')
    
    policy: Literal["fail_closed", "reduce_exposure"] = Field(
        default="fail_closed",
        description="Fallback policy: fail_closed = block all, reduce_exposure = reduce by pct"
    )
    risk_reduction_pct: Decimal = Field(
        default=Decimal("0.5"),
        description="Exposure reduction percentage when policy=reduce_exposure"
    )
    backoff_ms: List[int] = Field(
        default=[200, 500, 1000],
        description="Backoff intervals for retry (ms)"
    )
```

**Risk Assessment**: LOW
- Pydantic model exists
- Only need to add field definitions
- Default values match existing hardcode at `exposure_guard.py:182`

---

### 2. YAML Config Location

**Finding**: `execution_position` секція існує в [domains.yaml](../config/aurora/domains.yaml#L364-L452)

**Поточний стан** (lines 364-452):
- ✅ `watchdog` — typed
- ✅ `exposure_guard` — typed  
- ✅ `fsm_open` — typed
- ❌ **`fallback` — MISSING**

**Required Addition** до `config/aurora/domains.yaml`:

```yaml
execution_position:
  # ... existing configs ...
  
  fallback:
    policy: fail_closed           # MUST match FallbackConfig.policy
    risk_reduction_pct: 0.5       # Decimal
    backoff_ms: [200, 500, 1000]
```

**Risk Assessment**: LOW
- Simple YAML addition
- Schema already supports via `ExecutionConfig.fallback: Optional[FallbackConfig]`

---

### 3. Aurora Handler Defaults Analysis

**Source**: [aurora_handler.py](../apps/reference/domains/decision_making/aurora_handler.py#L254-L280)

**Hardcoded Defaults Block** (lines 254-280):
```python
else:
    # Defaults
    self.signal_threshold = decimal.Decimal("0.1")
    self.side_bias_window_sec = 420.0
    self.side_bias_target_ratio = 0.72
    self.side_bias_penalty_factor = 0.25
    self.side_bias_min_intents = 18
    self.regime_thresholds = {"DEFAULT": 1.0}
    # ... 20+ more defaults ...
```

**Critical Discovery**: Конфіг `aurora.decision` **вже повністю визначений** у [strategies/aurora.yaml](../config/aurora/strategies/aurora.yaml#L24-L150):

```yaml
decision:
  signal_threshold: 0.12
  neutral_threshold: 0.05
  side_bias_window_sec: 420
  side_bias_target_ratio: 0.72
  side_bias_penalty_factor: 0.25
  side_bias_min_intents: 18
  # ... all fields present ...
```

**Проблема**: `aurora_handler.py` читає конфіг через `getattr(decision, "signal_threshold", "0.1")` з fallback на hardcode. Якщо `decision is None` (lines 168-169), весь блок else виконується.

### 🔴 Risk Assessment: MEDIUM

**Scenarios where `decision is None`**:

1. **Unit Tests without Config Mocking**
   - Tests що не мокають `cfg.strategies.aurora.decision`
   - **Impact**: Tests fail з AttributeError
   
2. **Shadow Mode / Partial Config**
   - Shadow replay без повного config loading
   - **Impact**: Handler не ініціалізується

3. **Config Loading Race**
   - Handler constructed before config fully loaded
   - **Impact**: Startup failure

**Recommendation: Phased Approach**

**Phase A (Safe)**: Keep `else:` block but log WARNING:
```python
else:
    self.logger.warning("CONFIG_FALLBACK_USED: decision is None, using hardcoded defaults")
    # ... existing defaults ...
```

**Phase B (After Test Audit)**: Convert to fail-closed:
```python
if not decision:
    from apps.reference.config_contract import ConfigContractError
    raise ConfigContractError(
        path="strategies.aurora.decision",
        why="decision config is mandatory. Check config/aurora/strategies/aurora.yaml"
    )
```

---

### 4. Dynamic Anchors (feature_engineering.py)

**🎉 ALREADY IMPLEMENTED — NO WORK NEEDED**

**Evidence**: [feature_engineering.py](../apps/reference/domains/feature_engineering/feature_engineering.py#L124-L128)
```python
self.macro_sync_anchors = self.cfg.macro_sync_anchors
```

**Config Location**: [domains.yaml](../config/aurora/domains.yaml#L177)
```yaml
macro_sync:
  anchors: ["BTCUSDT", "ETHUSDT"]
```

**Verification**: `macro_sync_anchors` properly flows through:
1. `domains.yaml:macro_sync.anchors`
2. `config_models.py:MacroSyncConfig`
3. `feature_engineering.py:self.cfg.macro_sync_anchors`

**P1 Impact**: NONE — цей пункт можна виключити з P1.

---

## 📊 Implementation Matrix

| Task | File | Lines | Schema Ready | YAML Ready | Risk | Priority |
|------|------|-------|--------------|------------|------|----------|
| Add FallbackConfig fields | `config_models.py` | 825-834 | ⚠️ Empty | N/A | Low | P1.1 |
| Add fallback YAML section | `domains.yaml` | ~405 | ✅ | ❌ Missing | Low | P1.2 |
| Wire exposure_guard to config | `exposure_guard.py` | 177-186 | ✅ | ✅ after P1.2 | Low | P1.3 |
| Aurora handler - add WARNING | `aurora_handler.py` | 254 | N/A | ✅ Complete | Medium | P1.4 |
| Dynamic anchors | `feature_engineering.py` | — | ✅ | ✅ | None | **SKIP** |

---

## 🧪 Test Impact Analysis

### Existing Guard Tests
- `tests/vfoundation/test_fail_closed_config.py` — P0 guards, **no changes needed**

### New Test Requirements for P1

```python
# tests/vfoundation/test_p1_config_extraction.py

def test_fallback_config_has_required_fields():
    """FallbackConfig Pydantic model has policy, risk_reduction_pct, backoff_ms."""
    from apps.reference.config_models import FallbackConfig
    cfg = FallbackConfig(policy="fail_closed", risk_reduction_pct=Decimal("0.5"), backoff_ms=[200, 500, 1000])
    assert cfg.policy == "fail_closed"

def test_exposure_guard_uses_config_fallback():
    """ExposureGuard reads fallback from config, not hardcode."""
    # Mock cfg.trading.execution.fallback
    # Verify _load_fallback_config reads from cfg
```

---

## ⚠️ Pre-Implementation Checklist

### Before P1.1 (FallbackConfig fields):
- [ ] Verify no tests rely on FallbackConfig being empty
- [ ] Confirm `Decimal` import available in config_models.py

### Before P1.3 (Wire exposure_guard):
- [ ] P1.1 and P1.2 complete
- [ ] `cfg.trading.execution.fallback` path is valid
- [ ] Run `pytest tests/vfoundation/ -q` to verify

### Before P1.4 (Aurora handler WARNING):
- [ ] Grep for tests that construct AuroraHandler without config
- [ ] Verify `strategies/aurora.yaml` loaded in all entry points

---

## 📝 Conclusions

1. **FallbackConfig Extraction**: LOW risk. Schema exists, just add fields + YAML.

2. **Aurora Handler Defaults**: MEDIUM risk. Config already in YAML, but removing `else:` block may break tests. Recommend phased approach (WARNING → fail-closed).

3. **Dynamic Anchors**: **ALREADY DONE**. `macro_sync_anchors` flows from config. Remove from P1 scope.

4. **Shadow Mode Compatibility**: Adding WARNING to aurora_handler preserves backward compatibility. Full fail-closed requires test audit.

---

## 🎯 Recommended P1 Execution Order

```
P1.1: Add fields to FallbackConfig (config_models.py)
   ↓
P1.2: Add fallback section to domains.yaml  
   ↓
P1.3: Wire exposure_guard._load_fallback_config() to use cfg
   ↓
P1.4: Add WARNING log to aurora_handler else block
   ↓
P1.5: Add P1 guard tests
   ↓
[FUTURE] P2: Full fail-closed for aurora_handler after test audit
```

---

**Report Generated**: 2025-01-22  
**File**: `reports/P1_CONFIG_EXTRACTION_REVIEW_REPORT_2025_01_22.md`
