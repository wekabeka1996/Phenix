# TASK-ALPHA-FORENSIC-01: Line-by-line Walkthrough

## 1. apps/reference/domains/alpha_search/alpha_model.py

**Role:** Core framework definition. Defines the contract (`AlphaModel` ABC) and the data structure (`AlphaScore`).
**Integrity:** High. Uses Pydantic for validation. Pure Functional core behavior.

### Code Analysis
- **Lines 13-42 (AlphaScore):** 
  - Standard Pydantic output model.
  - **Constraints:** `score` [-1..1], `confidence` [0..1].
  - **Fields:** `symbol`, `model_name`, `score`, `confidence`, `features_used`, `why`.
  - **Critical:** This is the *only* way Alpha models communicate with the outside world.

- **Lines 43-122 (AlphaModel ABC):**
  - **Interface:** `calculate_alpha`, `get_required_features`, `is_ready`.
  - **Design Pattern:** Strategy Pattern. Each model implements a specific alpha logic independent of execution.
  - **Invariant:** Models must be stateless regarding previous calculations (inputs explicitly passed).

- **Lines 123-174 (AlphaModelRegistry):**
  - **Role:** Dependeny Injection container / Service Locator for models.
  - **Method `calculate_all_alpha`:** Iterates, checks `is_ready`, calls `calculate_alpha`, catches Exceptions.
  - **Fail-Safe:** Wraps individual model calculations in `try-except` to prevent one bad model from crashing the registry (Line 161-168).

## 2. apps/reference/domains/alpha_search/ensemble.py

**Role:** Aggregates multiple AlphaScores into a single "Meta-Score".
**Status:** Probably unused in current `decision_making.py` integration (only `calculate_all_alpha` is called, not ensemble).

## 3. apps/reference/domains/alpha_search/models/*.py

### momentum.py
- **Logic:** Uses RSI, MACD, EMA Crossover.
- **Inputs:** `rsi_14`, `macd`, `macd_signal`, `ema_50`, `ema_200`, `price`.
- **Output:** Directional score based on trend strength.

### mean_reversion.py
- **Logic:** Uses Bollinger Bands %B, Price deviation from SMA.
- **Inputs:** `bb_percent`, `price`, `ma_50`.
- **Output:** Contrarian score (High %B -> Negative Score).

### volatility.py
- **Logic:** Uses ATR, BB Width expansion.
- **Inputs:** `atr_14`, `bb_width`, `realized_volatility_1h`.
- **Output:** Volatility Regime Score (not necessarily directional, but "magnitude" potential).

## Summary of Public API

1.  `AlphaModelRegistry` (Class): Entry point.
2.  `AlphaModelRegistry.calculate_all_alpha(...)` (Method): Main runtime hook.
3.  `AlphaScore` (DataClass): Output contract.
4.  `EVT:ALPHA_SCORE_CALCULATED`: System-wide event emitted by DecisionMaking containing the scores.

**Guarantee:**
The domain guarantees that if `calculate_all_alpha` is called with valid features, it returns a list of failure-resilient `AlphaScore` objects or an empty list. It does *not* guarantee that these scores are used for trading.
