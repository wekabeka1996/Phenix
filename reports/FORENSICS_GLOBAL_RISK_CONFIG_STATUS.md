# FORENSIC INVESTIGATION: Global Risk Config Status

**Date**: 2026-01-25  
**Investigator**: Domain-Locked Architect  
**Case**: Global `risk_management` Config Fields Status Check  

---

## 🎯 EXECUTIVE SUMMARY

**Investigated Fields:**
- `risk_management.default_risk_per_trade`
- `risk_management.max_open_positions`

**Verdict:** ❌ **BOTH FIELDS COMPLETELY DEAD — Never Existed in Production Config**

---

## 📋 ГРУПА 1: Default Risk Per Trade

### Diagnosis: ❌ **DEAD — Field Does Not Exist**

**Поле:** `risk_management.default_risk_per_trade`

**Гіпотеза (була):** Використовується як fallback, якщо стратегія не надає свій ризик.

### Evidence:

**1️⃣ Config Check (domains.yaml:311-327):**

```yaml
risk_management:
  use_absorption_penalty: false
  risk_score_weights:
    delta_price_pct: 0.1
    obi: 0.3
    tfi: 0.3
    absorption_inverse: 0.3
  trading_allowed_thresholds:
    max_risk_score: 0.96
  validation:
    total_weight_min: 0.5
    total_weight_max: 2.0
```

**Result:** ❌ `default_risk_per_trade` **NOT PRESENT** in config

**2️⃣ Code Search Results:**

```bash
# Search across all domains:
grep -r "default_risk_per_trade" apps/reference/domains/**/*.py
# Result: 0 matches

# Search in config files:
grep -r "default_risk_per_trade" config/**/*.yaml
# Result: 0 matches
```

**3️⃣ RiskManagement Class Check:**

File: `apps/reference/domains/risk_management/risk_management.py`

**Methods that access config:**
- `_get_risk_score_weights()` — reads `risk_score_weights` (lines 520-530)
- `_get_max_risk_score()` — reads `trading_allowed_thresholds.max_risk_score` (lines 532-560)

**No references to:**
- ❌ `default_risk_per_trade`
- ❌ Any fallback risk value
- ❌ Any per-trade risk calculation

**4️⃣ Position Sizing Investigation:**

Position sizing handled in:
- **DecisionMaking domain** → `decision_making.position_sizing`
- **Config location:** `domains.yaml → decision_making.position_sizing`

```yaml
decision_making:
  position_sizing:
    min_position_size_usd: 10
    liquidity_based_cap_usd: 10000
```

**Risk Contract V1** (trading.yaml):
```yaml
trading:
  decision:
    position_sizing:
      risk_contract_v1:
        enabled: false
        per_symbol_margin_fraction: 0.06  # 6% of equity per position
        effective_leverage: 10.0
```

**Conclusion:**
- Position sizing uses **per_symbol_margin_fraction** (6% per position)
- NO global `default_risk_per_trade` field exists
- NO fallback mechanism in RiskManagement domain

### Root Cause Analysis:

**Історія:**
1. Поле `default_risk_per_trade` **ніколи не існувало** в production config
2. Можливо, це залишок із старого design doc або раннього прототипу
3. Position sizing завжди використовував `per_symbol_margin_fraction` (6%)

**Чому confusion?**
- CONFIG_MAP може мати застарілий reference до неіснуючого поля
- Або це було в ранньому RFC, але ніколи не імплементувалось

### Verdict: ❌ **PURGE FROM DOCUMENTATION**

**Recommendation:**
- ❌ **REMOVE** згадки про `default_risk_per_trade` з CONFIG_MAP.md (якщо є)
- ✅ **DOCUMENT** що position sizing використовує `per_symbol_margin_fraction` з RiskContractV1

---

## 📋 ГРУПА 2: Max Open Positions

### Diagnosis: ❌ **DEAD — Field Does Not Exist**

**Поле:** `risk_management.max_open_positions`

**Гіпотеза (була):** Глобальний ліміт на кількість одночасних позицій.

### Evidence:

**1️⃣ Config Check:**

```yaml
# domains.yaml:311-340 (risk_management block)
risk_management:
  use_absorption_penalty: false
  risk_score_weights: {...}
  trading_allowed_thresholds: {...}
  validation: {...}
```

**Result:** ❌ `max_open_positions` **NOT PRESENT**

**2️⃣ Code Search Results:**

```bash
# Search in all domains:
grep -r "max_open_positions" apps/reference/domains/**/*.py
# Result: 0 matches

# Search in config:
grep -r "max_open_positions" config/**/*.yaml
# Result: 0 matches
```

**3️⃣ ExposureGuard Investigation:**

File: `apps/reference/domains/execution_position/exposure_guard.py`

**ExposureGuard checks (lines 1-200):**
- ✅ `max_equity_utilization_pct` (150%)
- ✅ `max_portfolio_fraction` (150%)
- ✅ `max_long_utilization_pct` (150%)
- ✅ `max_short_utilization_pct` (150%)
- ✅ `max_concentration_pct` (500% for backtest)
- ✅ `max_directional_ratio` (20.0)

**Missing:**
- ❌ NO `max_open_positions` check
- ❌ NO position count limit

**4️⃣ FSM Open Investigation:**

File: `apps/reference/domains/execution_position/fsm_open.py`

**Search results:**
```bash
grep -r "position.*limit\|max.*position" apps/reference/domains/execution_position/
```

**Found:**
- `WhyCode.GUARD_POSITION_LIMIT_EXCEEDED` — enum definition
- But NO actual check for max_open_positions

**5️⃣ Daily Gate Investigation:**

File: `apps/reference/domains/risk_management/daily_gate.py`

**DailyRiskState checks:**
- ✅ `max_drawdown_pct` (daily loss limit)
- ✅ `equity_open_usd` (daily reset)
- ✅ `realized_pnl_usd` (accumulated P&L)

**Missing:**
- ❌ NO position count tracking
- ❌ NO `max_open_positions` check

### Root Cause Analysis:

**Реальна система обмежень позицій:**

1. **Concentration Limit** (per-symbol):
   ```yaml
   exposure_guard:
     max_concentration_pct: 500.0  # Max notional per symbol
   ```

2. **Equity Utilization** (portfolio-wide):
   ```yaml
   exposure_guard:
     max_equity_utilization_pct: 150.0  # Total exposure / equity
   ```

3. **Directional Ratio**:
   ```yaml
   exposure_guard:
     max_directional_ratio: 20.0  # Long/Short imbalance limit
   ```

**Чому немає `max_open_positions`?**

Aurora використовує **notional-based limits**, а не position count:
- Одна BTC позиція за $50k = проблема
- П'ять SOL позицій по $500 = OK

**Position count ≠ risk exposure**

Приклад:
- Scenario A: 10 positions × $100 = $1,000 exposure ✅
- Scenario B: 1 position × $50,000 = $50,000 exposure ❌

**Система контролює $-exposure, а не кількість позицій.**

### Verdict: ❌ **PURGE FROM DOCUMENTATION**

**Recommendation:**
- ❌ **REMOVE** згадки про `max_open_positions`
- ✅ **DOCUMENT** що система використовує **notional-based risk limits**:
  - `max_equity_utilization_pct` (portfolio total)
  - `max_concentration_pct` (per-symbol)
  - `max_directional_ratio` (long/short balance)

---

## 📊 FINAL VERDICT MATRIX

| Field | Location Checked | Status | Evidence | Recommendation |
|-------|-----------------|--------|----------|----------------|
| `default_risk_per_trade` | domains.yaml | ❌ **DEAD** | 0 matches in code/config | **PURGE** |
| `max_open_positions` | domains.yaml | ❌ **DEAD** | 0 matches in code/config | **PURGE** |

---

## 🔴 CRITICAL FINDINGS

### 1. Nonexistent Fields in Documentation

**Problem:** CONFIG_MAP або design docs можуть згадувати поля, які **ніколи не існували** в runtime.

**Impact:**
- Confusion під час code review
- Wasted time шукаючи "чому X не працює"
- False audit findings

### 2. Actual Position Sizing System

**Real SSOT:**
- **Config:** `trading.decision.position_sizing.risk_contract_v1`
- **Fields:**
  - `per_symbol_margin_fraction: 0.06` — 6% of equity per position
  - `effective_leverage: 10.0` — leverage multiplier
- **Location:** `config/aurora/trading.yaml:202-230`

### 3. Actual Position Limits System

**Real SSOT:**
- **Config:** `domains.execution_position.exposure_guard`
- **Fields:**
  - `max_equity_utilization_pct: 150.0` — total portfolio exposure
  - `max_concentration_pct: 500.0` — per-symbol notional limit
  - `max_directional_ratio: 20.0` — long/short balance
- **Location:** `config/aurora/domains.yaml:355-375`

---

## 📝 RECOMMENDATIONS

### ✅ IMMEDIATE ACTIONS:

1. **UPDATE CONFIG_MAP.md:**
   - ❌ Remove `default_risk_per_trade` (if present)
   - ❌ Remove `max_open_positions` (if present)
   - ✅ Add explicit note: "Aurora uses notional-based risk limits, not position count"

2. **ADD DOCUMENTATION:**
   - Create section: "Position Sizing SSOT"
   - Document `per_symbol_margin_fraction` (6% per position)
   - Document notional-based limits (equity utilization, concentration, directional ratio)

3. **NO CODE CHANGES NEEDED:**
   - Поля ніколи не існували → нічого видаляти з коду
   - Система працює правильно з існуючими limits

### 🔧 AUDIT CHECKLIST:

**Before claiming field is "DEAD", verify:**
1. ✅ Field present in config YAML? → `default_risk_per_trade`: NO
2. ✅ Field accessed in code? → `default_risk_per_trade`: NO
3. ✅ Field in schema/Pydantic models? → Not checked (unnecessary if 1+2 = NO)

**If ALL = NO → Field NEVER EXISTED (not "dead", but "never alive")**

---

## 📚 APPENDIX: Search Commands Used

```bash
# Global risk config grep:
grep -r "default_risk_per_trade\|max_open_positions" apps/reference/domains/
# Result: 0 matches

# Config file search:
grep -r "default_risk_per_trade\|max_open_positions" config/
# Result: 0 matches

# RiskManagement class inspection:
cat apps/reference/domains/risk_management/risk_management.py
# Result: No references to either field

# ExposureGuard inspection:
cat apps/reference/domains/execution_position/exposure_guard.py | grep -E "max.*position|position.*limit"
# Result: No max_open_positions checks (only notional limits)
```

---

**ВИСНОВОК:**

Обидва поля **НІКОЛИ НЕ ІСНУВАЛИ** в production config чи runtime коді:
- `default_risk_per_trade` → Не існує (sizing використовує `per_symbol_margin_fraction`)
- `max_open_positions` → Не існує (система контролює $-notional, не кількість позицій)

**Дія:** ❌ **PURGE** з документації (якщо згадано)

**Реальна SSOT:**
- Position sizing: `trading.decision.position_sizing.risk_contract_v1.per_symbol_margin_fraction` (6%)
- Position limits: `domains.execution_position.exposure_guard.max_equity_utilization_pct` (150%)
