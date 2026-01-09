# TASK-ALPHA-FORENSIC-04: Input Dependencies

## Required Features (By Model)

1.  **Momentum (`momentum_v1`)**
    *   `rsi_14` (Relative Strength Index)
    *   `macd` (Moving Average Convergence Divergence)
    *   `macd_signal`
    *   `ema_50`
    *   `ema_200`
    *   `price` (Current Close Check)

2.  **Mean Reversion (`mean_reversion_v1`)**
    *   `bb_percent` (Bollinger Band %B)
    *   `price`
    *   `ma_50`
    *   `rsi_14`

3.  **Volatility (`volatility_v1`)**
    *   `atr_14`
    *   `atr_ratio`
    *   `bb_width`
    *   `bb_width_change`
    *   `realized_volatility_1h`
    *   `realized_volatility_1d`
    *   `volume_volatility_ratio`
    *   `price_range_ratio`

## Data Source
All inputs come from `features: Dict[str, Any]`, which originates from `FeatureEngineering` domain.
**Warmup:** If features are missing logic relies on *in-method defaults* (see Task 05).

---

# TASK-ALPHA-FORENSIC-05: Failure Modes & Edge Cases

## 1. Missing Features
**Behavior:** **Fail-Open (with defaults)**.
Code Evidence (`models/volatility.py`):
```python
atr_ratio = Decimal(str(features["atr_ratio"] if "atr_ratio" in features else 1))
bb_width = Decimal(str(features["bb_width"] if "bb_width" in features else 0.05))
```
**Risk:** If `FeatureEngineering` is cold (warmup), the Alpha models will calculate scores based on "phantom" default values (e.g., assuming perfectly average volatility).
**Mitigation:** `is_ready()` method exists but implementation in `AlphaModelRegistry.calculate_all_alpha` checks `model.is_ready(features)`.
**CRITICAL:** `AlphaModel.is_ready` checks:
```python
return all(feature in features for feature in required)
```
So, if features are missing, `calculate_alpha` is **NOT CALLED**. The defaults inside `calculate_alpha` are defensive coding against race conditions, but the primary gate is `is_ready`.
**Result:** **Fail-Closed (Skip).** If features are missing, no score is produced.

## 2. Calculation Errors (Exceptions)
**Behavior:** **Fail-Closed (Skip Model).**
Code Evidence (`alpha_model.py`):
```python
try:
    score = model.calculate_alpha(...)
    scores.append(score)
except Exception as e:
    # Log error but continue with other models
    print(f"Error calculating alpha for {model.name}: {e}")
    continue
```
**Result:** Single model failure does not crash the registry or the pipeline.

## 3. Numeric Instability (NaN/Inf)
**Behavior:** Unknown/Implicit.
Python `Decimal` handles strings. If `str(NaN)` is passed, `Decimal('nan')` is created.
Calculations with `Decimal('nan')` propagate `NaN`.
**Result:** Pydantic validation for `score` (`ge=-1, le=1`) will likely **fail** if `NaN` is returned (validation error). This triggers the `try-except` block in registry.
**Verdict:** **Fail-Closed** (via Pydantic validation error).

## Summary
The system is robustly **Fail-Closed**.
- Missing data -> Skip (via `is_ready`)
- Bad data (NaN) -> Skip (via Pydantic error -> catch)
- Logic error -> Skip (via catch)
It effectively implements a "Best Effort" availability.
