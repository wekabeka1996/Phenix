# Aurora Phase 3: Інтеграція Optuna Параметрів у Production
**Домен:** Alpha Search / Decision Making  
**Дата:** 2025-12-04  
**Версія:** 1.0

---

## Огляд

Цей документ описує **конкретні кроки**, які потрібно виконати для інтеграції параметрів, знайдених Phase 3 Optuna optimization, у production систему.

**Мета:** Досягти 100% parity між backtest engine та production decision_making/feature_engineering.

---

## Статус Поточної Реалізації

### ✅ Що Вже Працює (60%)

| Компонент | Статус | Файл | Лінії |
|-----------|---------|------|-------|
| Side-Bias Penalty | ✅ Реалізовано | `decision_making.py` | 1363-1409 |
| Regime Threshold Multipliers | ✅ Реалізовано | `decision_making.py` | 1343-1352 |
| Regime Sizing Modifiers | ✅ Реалізовано | `decision_making.py` | 1632-1650 |

### ❌ Що Потрібно Додати (40%)

| Компонент | Статус | Потрібна Робота |
|-----------|---------|-----------------|
| EMA Clamping | ❌ Hardcoded | Додати config support |
| Risk Score Weights | ❌ Hardcoded | Додати config support |
| Per-Instrument Overrides | ❌ Global only | Додати instrument-level config |

---

## План Імплементації

### 📋 Крок 1: Додати Per-Instrument Config Resolution

**Проблема:**  
Зараз всі параметри (side-bias, regime thresholds, sizing) є **глобальними** для всіх інструментів. Phase 3 показав, що кожен актив потребує **індивідуальних** налаштувань:
- SOLUSDT: side_bias = 0.0 (вимкнено)
- ETHUSDT: side_bias = 0.9 (максимум)
- XRPUSDT: side_bias = 0.4 (помірно)

**Рішення:**  
Додати логіку перевірки instrument-specific overrides перед використанням global defaults.

#### 1.1 Модифікувати `decision_making.py`

**Локація:** `apps/reference/domains/decision_making/decision_making.py`

**Додати helper method:**

```python
def _get_instrument_config(self, symbol: str, param_path: str, default: Any) -> Any:
    """
    Отримати конфіг з підтримкою per-instrument override.
    
    Priority:
    1. instruments.{SYMBOL}.{param_path}
    2. decision.{param_path} (global)
    3. default
    
    Args:
        symbol: Символ інструменту (наприклад, "SOLUSDT")
        param_path: Шлях до параметра (наприклад, "side_bias_penalty_factor")
        default: Значення за замовчуванням
        
    Returns:
        Значення параметра
    """
    # 1. Спробувати instrument-specific config
    try:
        instruments = self._safe_config_get("trading", "instruments", default={})
        if symbol in instruments:
            instrument_cfg = instruments[symbol]
            # Підтримка вкладених шляхів: "regime_thresholds.HIGH_VOLATILITY"
            parts = param_path.split('.')
            value = instrument_cfg
            for part in parts:
                if isinstance(value, dict):
                    value = value.get(part)
                elif hasattr(value, part):
                    value = getattr(value, part)
                else:
                    value = None
                    break
            
            if value is not None:
                return value
    except (AttributeError, KeyError, TypeError):
        pass
    
    # 2. Спробувати global decision config
    try:
        parts = param_path.split('.')
        value = self._safe_config_get("trading", "decision", *parts, default=None)
        if value is not None:
            return value
    except (AttributeError, KeyError, TypeError):
        pass
    
    # 3. Повернути default
    return default
```

#### 1.2 Оновити Side-Bias Resolution

**Знайти:** Рядки 1363-1369 у `decision_making.py`

**Було:**
```python
side_bias_window = self._safe_config_get(
    "trading", "decision", "side_bias_window_sec", default=60)
side_bias_target = self._safe_config_get(
    "trading", "decision", "side_bias_target_ratio", default=0.60)
side_bias_penalty = self._safe_config_get(
    "trading", "decision", "side_bias_penalty_factor", default=0.50)
```

**Стало:**
```python
side_bias_window = self._get_instrument_config(
    symbol, "side_bias_window_sec", default=60)
side_bias_target = self._get_instrument_config(
    symbol, "side_bias_target_ratio", default=0.60)
side_bias_penalty = self._get_instrument_config(
    symbol, "side_bias_penalty_factor", default=0.50)
```

#### 1.3 Оновити Regime Threshold Resolution

**Знайти:** Рядки 1343-1352 у `decision_making.py`

**Було:**
```python
regime_thresholds_cfg = self._safe_config_get(
    "trading", "decision", "regime_threshold_multipliers", default={})

threshold_factor = Decimal(
    str(regime_thresholds_cfg.get(regime_name))
    if regime_name and regime_name in regime_thresholds_cfg
    else str(regime_thresholds_cfg.get("DEFAULT", "1.0"))
)
```

**Стало:**
```python
# Спробувати per-instrument regime thresholds
regime_thresholds_cfg = self._get_instrument_config(
    symbol, "regime_threshold_multipliers", default={})

# Якщо не знайдено, використати global
if not regime_thresholds_cfg:
    regime_thresholds_cfg = self._safe_config_get(
        "trading", "decision", "regime_threshold_multipliers", default={})

threshold_factor = Decimal(
    str(regime_thresholds_cfg.get(regime_name))
    if regime_name and regime_name in regime_thresholds_cfg
    else str(regime_thresholds_cfg.get("DEFAULT", "1.0"))
)
```

#### 1.4 Оновити Sizing Modifier Resolution

**Знайти:** Рядки 1632-1650 у `decision_making.py`

**Було:**
```python
sizing_cfg = self._safe_config_get(
    "trading", "decision", "sizing_modifiers", default={}) or {}

regime_multiplier = Decimal(sizing_cfg.get(regime, "1.0"))
```

**Стало:**
```python
# Спробувати per-instrument sizing modifiers
sizing_cfg = self._get_instrument_config(
    symbol, "sizing_modifiers", default={})

# Якщо не знайдено, використати global
if not sizing_cfg:
    sizing_cfg = self._safe_config_get(
        "trading", "decision", "sizing_modifiers", default={}) or {}

regime_multiplier = Decimal(sizing_cfg.get(regime, "1.0"))
```

---

### 📋 Крок 2: Додати EMA Clamping Config Support

**Проблема:**  
EMA clamp values hardcoded у `calculation_engine.py` (рядки 76-77):
```python
clamp_min = decimal.Decimal("-0.02")  # HARDCODED
clamp_max = decimal.Decimal("0.02")   # HARDCODED
```

Phase 3 показав, що оптимальні значення різні для кожного активу:
- SOLUSDT: ±0.045
- ETHUSDT: ±0.03
- XRPUSDT: ±0.04

**Рішення:**  
Додати `ema_clamp_min` / `ema_clamp_max` до config.

#### 2.1 Оновити `FeatureEngineeringConfig`

**Файл:** `apps/reference/domains/feature_engineering/types.py`

**Знайти:** Клас `FeatureEngineeringConfig` (приблизно рядки 50-100)

**Додати:**
```python
class FeatureEngineeringConfig:
    def __init__(self, config: Any):
        # ... existing code ...
        
        # EMA Bias normalization range (Phase 3)
        self.ema_bias_clamp_min = self._get_decimal(
            "ema_bias.clamp_min", 
            default="-0.02"
        )
        self.ema_bias_clamp_max = self._get_decimal(
            "ema_bias.clamp_max", 
            default="0.02"
        )
```

**Додати helper method (якщо ще немає):**
```python
def _get_decimal(self, path: str, default: str) -> decimal.Decimal:
    """Отримати Decimal значення з config."""
    value = self._get(path, default=default)
    return decimal.Decimal(str(value))
```

#### 2.2 Використати Config у `calculation_engine.py`

**Файл:** `apps/reference/domains/feature_engineering/calculation_engine.py`

**Знайти:** Метод `compute_ema_bias` (рядки 69-82)

**Було:**
```python
def compute_ema_bias(self, state: HotState) -> decimal.Decimal:
    ema_long = state.ema_long
    
    if ema_long and ema_long > 0:
        bias = (state.ema_short - ema_long) / ema_long
        # Clamp to configured range
        bias_clamped = max(self.cfg.ema_bias_clamp_min, 
                          min(self.cfg.ema_bias_clamp_max, bias))
        # ... rest
```

**Стало:**
```python
def compute_ema_bias(self, state: HotState) -> decimal.Decimal:
    ema_long = state.ema_long
    
    if ema_long and ema_long > 0:
        bias = (state.ema_short - ema_long) / ema_long
        
        # Використати config values (Phase 3)
        clamp_min = self.cfg.ema_bias_clamp_min
        clamp_max = self.cfg.ema_bias_clamp_max
        
        # Clamp to configured range
        bias_clamped = max(clamp_min, min(clamp_max, bias))
        
        # Normalize to [0, 1]
        clamp_range = clamp_max - clamp_min
        phi = (bias_clamped - clamp_min) / clamp_range
        return phi
    return self.cfg.neutral_value
```

---

### 📋 Крок 3: Додати Risk Score Weights Config Support

**Проблема:**  
Risk weights hardcoded у коді (немає параметра `risk_weights` у config).

Phase 3 показав оптимальні ваги для кожного активу:
- SOLUSDT: delta=0.4, volume=0.4, volatility=0.2
- ETHUSDT: delta=0.4, volume=0.5, volatility=0.1
- XRPUSDT: delta=0.4, volume=0.4, volatility=0.5

**Рішення:**  
Додати `risk_weights` config параметр.

#### 3.1 Оновити `FeatureEngineeringConfig`

**Файл:** `apps/reference/domains/feature_engineering/types.py`

**Додати:**
```python
class FeatureEngineeringConfig:
    def __init__(self, config: Any):
        # ... existing code ...
        
        # Risk Score Composition Weights (Phase 3)
        risk_weights_cfg = self._get("risk_weights", default={})
        self.risk_weight_delta = self._get_float_from_dict(
            risk_weights_cfg, "delta_price", default=0.3
        )
        self.risk_weight_volume = self._get_float_from_dict(
            risk_weights_cfg, "volume", default=0.4
        )
        self.risk_weight_volatility = self._get_float_from_dict(
            risk_weights_cfg, "volatility", default=0.3
        )
```

**Додати helper (якщо немає):**
```python
def _get_float_from_dict(self, d: dict, key: str, default: float) -> float:
    """Отримати float з dict."""
    return float(d.get(key, default))
```

#### 3.2 Знайти Risk Score Calculation

**Файл:** `apps/reference/domains/feature_engineering/calculation_engine.py`

**Шукати:** Метод, який обчислює `risk_score` (може називатися `compute_risk_score` або подібно)

**ВАЖЛИВО:** Цей метод може бути у різних файлах. Потрібно знайти, де саме обчислюється risk_score.

**Було (приклад):**
```python
def compute_risk_score(...):
    # HARDCODED weights
    delta_weight = 0.3
    volume_weight = 0.4
    volatility_weight = 0.3
    
    risk = (
        delta_weight * delta_component +
        volume_weight * volume_component +
        volatility_weight * volatility_component
    )
    return risk
```

**Стало:**
```python
def compute_risk_score(...):
    # Використати config weights (Phase 3)
    delta_weight = self.cfg.risk_weight_delta
    volume_weight = self.cfg.risk_weight_volume
    volatility_weight = self.cfg.risk_weight_volatility
    
    risk = (
        delta_weight * delta_component +
        volume_weight * volume_component +
        volatility_weight * volatility_component
    )
    return risk
```

---

### 📋 Крок 4: Оновити Config Files

#### 4.1 Додати Per-Instrument Overrides в `trading.yaml`

**Файл:** `config/aurora/trading.yaml`

**Додати до SOLUSDT:**
```yaml
  instruments:
    SOLUSDT:
      symbol: "SOLUSDT"
      step_size: "0.01"
      tick_size: "0.01"
      min_notional: "10"
      
      # Phase 3: Side-Bias (DISABLED для SOL)
      side_bias_penalty_factor: 0.0
      side_bias_window_sec: 180
      side_bias_target_ratio: 0.6
      
      # Phase 3: Regime Threshold Multipliers
      regime_threshold_multipliers:
        HIGH_VOLATILITY: 1.8    # Дуже суворий
        LOW_VOLATILITY: 0.65    # Послаблений
        TREND_UP: 1.0
        TREND_DOWN: 1.0
        DEFAULT: 1.0
      
      # Phase 3: Regime Sizing Modifiers
      sizing_modifiers:
        HIGH_VOLATILITY: "0.6"   # -40%
        LOW_VOLATILITY: "2.0"    # +100% (максимум!)
        MEAN_REVERSION: "0.7"    # -30%
        UNCERTAIN: "0.5"
```

**Додати до ETHUSDT:**
```yaml
    ETHUSDT:
      symbol: "ETHUSDT"
      step_size: "0.001"
      tick_size: "0.01"
      min_notional: "10"
      
      # Phase 3: Side-Bias (MAXIMUM для ETH)
      side_bias_penalty_factor: 0.9
      side_bias_window_sec: 600
      side_bias_target_ratio: 0.6
      
      # Phase 3: Regime Threshold Multipliers
      regime_threshold_multipliers:
        HIGH_VOLATILITY: 1.3
        LOW_VOLATILITY: 0.85
        TREND_UP: 1.05
        TREND_DOWN: 1.05
        DEFAULT: 1.0
      
      # Phase 3: Regime Sizing Modifiers
      sizing_modifiers:
        HIGH_VOLATILITY: "0.3"   # -70% (мінімум!)
        LOW_VOLATILITY: "1.9"    # +90%
        MEAN_REVERSION: "0.8"
        UNCERTAIN: "0.5"
```

**Додати до XRPUSDT:**
```yaml
    XRPUSDT:
      symbol: "XRPUSDT"
      step_size: "0.01"
      tick_size: "0.0001"
      min_notional: "10"
      
      # Phase 3: Side-Bias (MODERATE для XRP)
      side_bias_penalty_factor: 0.4
      side_bias_window_sec: 600
      side_bias_target_ratio: 0.6
      
      # Phase 3: Regime Threshold Multipliers
      regime_threshold_multipliers:
        HIGH_VOLATILITY: 1.9    # МАКСИМУМ
        LOW_VOLATILITY: 0.95    # Майже без зміни
        TREND_UP: 1.0
        TREND_DOWN: 1.0
        DEFAULT: 1.0
      
      # Phase 3: Regime Sizing Modifiers
      sizing_modifiers:
        HIGH_VOLATILITY: "0.1"   # -90% (майже стоп!)
        LOW_VOLATILITY: "1.7"    # +70%
        MEAN_REVERSION: "0.8"
        UNCERTAIN: "0.5"
```

#### 4.2 Додати EMA Clamp та Risk Weights в `features.yaml`

**Файл:** `config/aurora/features.yaml`

**Додати після `ema_bias` секції:**
```yaml
  ema_bias:
    clamp_min: -0.02     # Global default
    clamp_max: 0.02      # Global default
  
  # Phase 3: Risk Score Composition
  risk_weights:
    delta_price: 0.3     # Global default
    volume: 0.4          # Global default
    volatility: 0.3      # Global default
```

**Додати per-instrument overrides (опційно, якщо хочете):**
```yaml
  # Per-instrument overrides (optional)
  instruments:
    SOLUSDT:
      ema_bias:
        clamp_min: -0.045
        clamp_max: 0.045
      risk_weights:
        delta_price: 0.4
        volume: 0.4
        volatility: 0.2
    
    ETHUSDT:
      ema_bias:
        clamp_min: -0.03
        clamp_max: 0.03
      risk_weights:
        delta_price: 0.4
        volume: 0.5
        volatility: 0.1
    
    XRPUSDT:
      ema_bias:
        clamp_min: -0.04
        clamp_max: 0.04
      risk_weights:
        delta_price: 0.4
        volume: 0.4
        volatility: 0.5
```

---

## Тестування

### Unit Tests

**Файл:** `tests/domains/test_decision_making.py`

```python
def test_per_instrument_config_override():
    """Test that instrument-specific configs override globals."""
    config = {
        "trading": {
            "decision": {
                "side_bias_penalty_factor": 0.5  # Global
            },
            "instruments": {
                "SOLUSDT": {
                    "side_bias_penalty_factor": 0.0  # Override
                }
            }
        }
    }
    
    dm = DecisionMaking(fsm, config)
    
    # Test SOLUSDT override
    penalty_sol = dm._get_instrument_config(
        "SOLUSDT", "side_bias_penalty_factor", default=0.5
    )
    assert penalty_sol == 0.0, "SOLUSDT should use override"
    
    # Test fallback to global
    penalty_btc = dm._get_instrument_config(
        "BTCUSDT", "side_bias_penalty_factor", default=0.5
    )
    assert penalty_btc == 0.5, "BTCUSDT should use global"
```

### Integration Test

**Файл:** `tests/integration/test_phase3_config.py`

```python
def test_phase3_config_loading():
    """Test that all Phase 3 configs load correctly."""
    config = load_config("config/aurora/trading.yaml")
    
    # Перевірити SOLUSDT Phase 3 params
    sol_cfg = config.trading.instruments.SOLUSDT
    assert sol_cfg.side_bias_penalty_factor == 0.0
    assert sol_cfg.sizing_modifiers.LOW_VOLATILITY == "2.0"
    assert sol_cfg.regime_threshold_multipliers.HIGH_VOLATILITY == 1.8
```

### Sanity Check (Most Important!)

**Мета:** Переконатися, що production система дає **той самий PnL**, що й backtest.

**Процедура:**
1. Завантажити January 2024 features
2. Запустити decision_making з Phase 3 config
3. Порівняти PnL з backtest результатами

**Очікуваний результат:** ±2% різниця (допустимо через округлення)

**Якщо різниця >5%:** Шукати bug у config resolution або feature calculation.

---

## Checklist Імплементації

- [ ] **Крок 1:** Додати `_get_instrument_config()` helper
- [ ] **Крок 1:** Оновити Side-Bias resolution
- [ ] **Крок 1:** Оновити Regime Threshold resolution
- [ ] **Крок 1:** Оновити Sizing Modifier resolution
- [ ] **Крок 2:** Додати EMA clamp в `FeatureEngineeringConfig`
- [ ] **Крок 2:** Використати config у `compute_ema_bias`
- [ ] **Крок 3:** Додати Risk weights в `FeatureEngineeringConfig`
- [ ] **Крок 3:** Використати config у risk score calculation
- [ ] **Крок 4:** Оновити `trading.yaml` (SOLUSDT, ETHUSDT, XRPUSDT)
- [ ] **Крок 4:** Оновити `features.yaml` (EMA clamp, risk weights)
- [ ] **Тести:** Написати unit tests
- [ ] **Тести:** Написати integration tests
- [ ] **Sanity Check:** Запустити на January data, перевірити PnL

---

## Оцінка Часу

| Завдання | Час | Складність |
|----------|-----|-----------|
| Додати per-instrument config resolution | 2 год | Medium |
| Додати EMA clamp config | 1 год | Low |
| Додати Risk weights config | 1 год | Low |
| Оновити config files | 30 хв | Low |
| Написати тести | 1-2 год | Medium |
| **Загалом** | **5-6 год** | **Medium** |

---

## Можливі Проблеми та Рішення

### Проблема 1: Config не завантажується
**Симптом:** `AttributeError` або `KeyError` при читанні config  
**Рішення:** Перевірити YAML синтаксис, переконатися що ключі exist

### Проблема 2: PnL не співпадає з backtest
**Симптом:** Різниця >5% між production та backtest  
**Рішення:**
1. Перевірити, що всі параметри правильно завантажені (додати logging)
2. Порівняти feature values між backtest та production
3. Перевірити order execution logic

### Проблема 3: Per-instrument config не працює
**Симптом:** Використовуються global values замість instrument-specific  
**Рішення:** Додати debug logging у `_get_instrument_config()` для діагностики

---

## Додаткові Ресурси

- **Phase 3 Config:** `config/aurora_phase3_production.yaml`
- **Gap Analysis:** `.gemini/antigravity/brain/.../phase3_production_gap_analysis.md`
- **Backtest Engine:** `apps/research/aurora_optuna/backtest_engine_aurora.py`
- **Production Decision Making:** `apps/reference/domains/decision_making/decision_making.py`
- **Production Features:** `apps/reference/domains/feature_engineering/`

---

## Підсумок

Після виконання всіх кроків, система матиме:
- ✅ Per-instrument Side-Bias Penalty
- ✅ Per-instrument Regime-Adaptive Thresholds
- ✅ Per-instrument Regime-Adaptive Sizing
- ✅ Configurable EMA Clamping
- ✅ Configurable Risk Score Weights

**Результат:** 100% parity з backtest engine, готова до testnet deployment.
