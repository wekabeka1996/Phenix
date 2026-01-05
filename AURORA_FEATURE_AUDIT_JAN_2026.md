# Aurora HFT Feature Audit Report – January 2026

## 1. Full List of Features

The Aurora system utilizes a multi-layered feature set categorized into **Base Features** (microstructure) and **Phase 1/V2 Features** (derived/statistical metrics).

### 1.1. Base Microstructure Features

| Feature | Description | Exact Formula / Method | Code Location | Neutral Value | Observed Issues |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **obi** | Order Book Imbalance | `(bid_size - ask_size) / (bid_size + ask_size)` (normalized to [-1, 1]) | `feature_engineering.py:504` | 0.0 | High noise in low-liquid pairs. |
| **tfi** | Trade Flow Imbalance | `(buy_vol - sell_vol) / (buy_vol + sell_vol)` (normalized to [-1, 1]) | `feature_engineering.py:508` | 0.0 | Tendency to jitter around 0. |
| **delta_price** | Raw Price Delta | `price - prev_price` (Spike-filtered by `delta_price_spike_filter_ms`) | `feature_engineering.py:511` | 0.0 | **Critical Scale Issue:** Emitted in USD, causing BTC delta to dominate Alts. |
| **absorption** | Order Book Absorption | Placeholder returning `zero_value` | `feature_engineering.py:528` | 0.0 | **Dead Feature:** Always constant 0.0. |
| **liquidity_kappa** | Depth Saturation | `depth_usd / (depth_usd + depth_half)` (clamped to [0.1, 1.0]) | `feature_engineering.py:520` | ~1.0 | Saturated near 0.98-0.99 for BTC/ETH. |
| **depth_imbalance** | Bid/Ask Depth Ratio | `(ask + half) / (bid + half)` mapped to [0, 1] via Laplace smoothing | `calculation_engine.py:387` | 0.5 | Bearish interpretation (phi > 0.5 means Ask > Bid). |

### 1.2. Statistical & Phase 1+ Features

| Feature | Description | Exact Formula / Method | Code Location | Neutral Value | Observed Issues |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **ema_bias** | EMA Convergence | `(EMA_short - EMA_long) / EMA_long` normalized to [0, 1] | `calculation_engine.py:91` | 0.5 | Reliable trend indicator. |
| **volume_spike** | Volume Rate Relative | `current_rate / max(avg_rate, eps)` capped at 10.0 and normalized to [0, 1] | `calculation_engine.py:180` | 0.0 | Highly sensitive to `avg_rate` windows. |
| **volatility_state**| Relative Range | `current_range / max(avg_range, eps)` normalized to [0, 1] | `calculation_engine.py:292` | 0.0 | **Overflow:** Values like `0E+16` observed when `avg_range` hits 0. |
| **macro_sync** | Anchor Correlation | Pearson correlation with BTC/ETH returns, normalized to [0, 1] | `calculation_engine.py:497` | 0.5 | Always high (~0.95) for ETH/SOL, provides low alpha. |
| **volume_zscore** | Tanh Volume Z-Score | `(tanh(z_score) + 1) / 2` where z is rate-based Welford stats | `calculation_engine.py:202` | 0.5 | Efficient O(1) calculation using Welford. |
| **large_trade_imb**| Whale Imbalance | `(large_buy - large_sell) / (total_large + eps)` normalized to [0, 1] | `calculation_engine.py:342` | 0.5 | Often empty in thin markets. |
| **spread_bps** | Bid-Ask Spread | `(ask - bid) / mid_price * 10000` | `calculation_engine.py:329` | ~0.48 | **Stagnant:** Constant 0.48 bps observed on several assets. |

---

## 2. Feature Importance Hierarchy

Extracted from `aurora.yaml` (Global) and `ETHUSDT` (Optimized) profiles.

### 2.1. Global Weight Ranking (Absolute Magnitude)
1. **obi, tfi, ema_bias, depth_imbalance**: 0.15 (Primary Alpha)
2. **delta_price, volume_spike, volatility_state, macro_sync**: 0.10 (Secondary Alpha)

### 2.2. ETHUSDT Optimized Ranking
| Rank | Feature | Absolute Weight | Role |
| :--- | :--- | :--- | :--- |
| 1 | **depth_imbalance** | 0.256 | Essential (Bearish Indicator) |
| 2 | **volume_spike** | 0.241 | Strength (Momentum) |
| 3 | **obi** | 0.155 | Essential (Microstructure) |
| 4 | **macro_sync** | 0.131 | Context (Global Beta) |
| 5 | **tfi** | 0.093 | Noise Filter |
| 6 | **ema_bias** | 0.058 | Trend Anchor |
| 7 | **volatility_state** | 0.036 | Risk Filter |

*   **Essential Features (Blocking)**: `obi`, `delta_price`. If these are not marked ready, the entire score is deferred (NRR-031).

---

## 3. Signal Score Calculation (V2)

The system utilizes `SignalScoreV2` (from `signal_score_v2.py`) implementing a **Net-Zero Scoring** standard.

### 3.1. Methodology
- **Zero-Mean Normalization**: `score_raw = Σ w_i * (x_i - neutral_i)`. This ensures that a feature at its neutral point contributes exactly 0 to the sum.
- **Σ|w| Normalization**: `final_score = score_raw / Σ |w|`. This makes the score independent of the number of active features.
- **Readiness Guard**: `is_ready = readiness.get(feat, False)`. 
  - If **essential** (`obi`, `delta_price`) → **BLOCK** (NRR-031).
  - If **optional** → Skip (feature excluded from both numerator and denominator).
- **Incident Fix (2026-01-04)**: Basic instant features (obi, tfi, etc.) added to `ready_map` in `FeatureEngineering` to prevent false NRR-031 blocks.

### 3.2. Implementation Details
The `DecisionMaking` domain calculates `delta_price_norm` as a signed percentage of price clamped to `delta_price_cap_pct` before passing it to the scoring kernel. This prevents large USD price deltas (BTC) from overwhelming other features.

---

## 4. Decision Making Process

### 4.1. Step-by-Step Logic
1. **Feature Receiving**: `on_features()` triggers the chain.
2. **Asset Gating**: Checks `enabled` status and `symbols_to_track`.
3. **Warmup Check**: Ensures `warmup.full_ready` is True (essential for Phase 4).
4. **Regime Identification**: Retrieves current market regime (`TREND_UP`, `HIGH_VOLATILITY`, etc.).
5. **Score Calculation**: Computes `signal_score` using V2 Net-Zero logic.
6. **Threshold Application**: 
   - Base `signal_threshold` (e.g., 0.1).
   - Applied regime multiplier (e.g., HIGH_VOLATILITY = 1.2x).
7. **Side Bias Correction**:
   - If historical `long_ratio` > 0.72 (target), a linear ramp penalty is applied to the LONG score.
8. **Final Decision**:
   - `LONG`: `score > threshold`
   - `SHORT`: `score < -threshold`
   - `FLAT`: Otherwise

### 4.2. Active Guards & Filters
- **Liquidity Gate**: Blocks entry if `liquidity_kappa < kappa_min`.
- **Exhaustion Block**: (Planned) Prevents entry into extended trends.
- **Min Intents**: `side_bias_min_intents: 18` prevents bias application on small sample sizes.
- **Fail-Closed Execution**: Intents are rejected if any mandatory gate (Risk, Portfolio, Features) is not 100% satisfied.

---

## 5. Potential Issues and Recommendations

### 5.1. Identified Problems
- **Volatility State Overflow**: Values like `0E+16` observed when `avg_range` is near 0.
- **Redundant `macro_sync`**: Hypersaturates at ~0.95 for correlated assets (ETH/SOL).
- **Dead `absorption`**: Current implementation is a static constant 0.0.
- **Saturated `liquidity_kappa`**: Does not provide meaningful differentiation on high-liquid pairs (BTC/ETH).

### 5.2. Technical Recommendations
1. **Fix Volatility State**: Implement a stricter `eps` in the denominator or use `log(range)` to compress outliers.
2. **De-bias Macro Sync**: Transition to a lead-lag cross-correlation metric or use `Beta` against BTC.
3. **Dynamic Neutrals**: Calculate trailing window anchors for `feature_neutrals` to adapt to changing regimes.
4. **Clean up Dead Logic**: Remove `absorption` from the calculation pipeline to reduce technical debt.
